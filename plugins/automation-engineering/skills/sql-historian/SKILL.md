---
name: sql-historian
description: Work with the SQL layer behind this estate - the Ignition tag historian schema and its monthly partitions, named queries and their parameter binding, the application tables that hold experiment status recipes audit events and the pitfall knowledge base, the timezone convention that silently corrupts data when mixed, and how to run SQL at all from a host with no database driver. Use when writing or fixing a named query, when a history or trend query returns nothing, when reporting on process history, when adding a table, or when a timestamp comes back shifted by hours.
---

# SQL and the tag historian

**You cannot query SQL Server directly from this host.** There is no `pyodbc` and no `pymssql`, and
the database is not exposed to it. Every query goes through Ignition:

| Route | How |
|---|---|
| A named query in a project | `system.db.runNamedQuery("Get_Annotations", {"Path": p})` |
| Ad-hoc SQL | the MCP `evalScript` tool, running `system.db.runPrepQuery(sql, args, "SQLServer")` |
| Tag history specifically | the MCP `queryTagHistory` tool, or `system.tag.queryTagHistory` |

If you have no authenticated MCP session, you cannot execute SQL. Say so rather than presenting
untested SQL as verified.

## The connections are not the same database

One connection **name** — `SQLServer` — but it points somewhere different on each gateway:

| Gateway | Server | Database |
|---|---|---|
| dev `wa03593d` (8.3.7) | `WQ01982D` | `Ignition` |
| prod `wz02163d` (8.1.28) | `WA06015P` | `Ignition` |

The two also authenticate as **different logins**. Read them from the gateway rather than from here:
`ign res list ignition/database-connection` shows `username`; the password comes back as an encrypted
blob and should stay where it is.

**A query validated on dev has seen none of production's history.** Row counts, tag ids and partition
tables all differ. Never reason about prod data from a dev result.

Prod also has a second connection, `SQLite_Database`, which is **enabled with an unedited placeholder
URL** — `jdbc:sqlite:C:/Path/To/File.db`. Exactly one named query targets it
(`DevSciLabs/SaveDashboard`), and that query is itself broken. Treat it as dead.

```bash
ign res list ignition/database-connection      # dev, anonymous; do not copy the password blob
```

## Historian configuration

A single `SqlHistorian` provider named `SQLServer`, **byte-identical on both gateways**:
partitioning enabled at **1 MONTH**, optimised partitions off, **pruning disabled**, `trackSce` true,
`staleMultiplier` 2. Nothing is ever pruned, so the oldest data is still there.

```bash
ign res list com.inductiveautomation.historian/historian-provider
```

## The schema, as actually used

Only **three** historian objects appear anywhere in this estate's SQL:

| Object | Purpose | Hits in estate SQL |
|---|---|---|
| `sqlth_te` | tag entry — maps a tag path to a numeric `id` | 371 |
| `sqlth_annotations` | operator notes pinned to a tag and time | 347 |
| `sqlt_data_1_<YYYY>_<M>` | the monthly value partitions | the only value source |

`sqlth_partitions`, `sqlth_sce`, `sqlth_drv` and `sqlth_scinfo` appear **zero** times — partition
discovery here goes through `sys.tables` instead of the catalogue tables.

Partition names are `sqlt_data_<driverId>_<YYYY>_<M>` with a **non-zero-padded month** and
`driverId = 1` in this estate: August 2024 is `sqlt_data_1_2024_8`, not `..._2024_08`. Any code that
zero-pads will find no table.

### The join everyone gets wrong

The primary key of `sqlth_te` is **`id`**, not `tagid`:

```sql
-- correct, and what Get_Annotations does in ~30 projects
SELECT a.* FROM sqlth_annotations a JOIN sqlth_te t ON a.tagid = t.id WHERE t.tagpath = :Path
```

The `ExperimentRecall` stub sitting in the same folder joins `... = sqlth_te.tagid` and returns
nothing, silently. It has been copied. Check the join before trusting an inherited query.

## Reading a tag's values over a time range

**There is no hand-written SQL in this estate that does this.** No live query references
`floatvalue`, `intvalue`, `stringvalue` or `t_stamp BETWEEN`. The de facto answer is the scripting API,
which handles partition spanning and interpolation for you:

```python
data = system.tag.queryTagHistory(
    paths=["[default]B5/2071-2-1/TFF/P1 Value"],
    startDate=system.date.addHours(system.date.now(), -8),
    endDate=system.date.now(),
    returnSize=500, aggregationMode="Average", returnFormat="Wide")
```

Reach for raw SQL only when you need something the API will not give you — a cross-partition scan, or
a join against an application table. The one real example in the estate builds it dynamically: put the
tag ids from `sqlth_te` in a temp table, then generate one `INSERT … SELECT` per partition into an
`NVARCHAR(MAX)` and `EXEC sp_executesql`. It joins on `sqlt_data_*.tagid = sqlth_te.id`.

See [references/historian-schema.md](references/historian-schema.md) for the column lists and the
partition-discovery query.

## Timezone: the silent corruption

This is the defect most likely to reach a report without anyone noticing.

| Where | Storage |
|---|---|
| `sqlt_data_*.t_stamp`, `sqlth_annotations.start_time` / `end_time` | epoch **milliseconds**, interpreted as **UTC** |
| Application tables (`EXP_STATUS.ENDTIME`, scheduler tables) | gateway-**local** `datetime`, from `system.date.now()` |

Join one to the other without converting and every row shifts by the UTC offset — five or six hours
here, and the size of the error changes across a DST boundary, so it will not look like a constant
offset.

The estate's one correct implementation is `Camera_Demo/Select_Photo`:

```sql
CAST((utc_dt AT TIME ZONE 'UTC') AT TIME ZONE 'Central Standard Time' AS datetime2(0))
```

`AT TIME ZONE 'Central Standard Time'` handles DST despite the name. The cruder form seen elsewhere,
`DATEADD(SECOND, t_stamp/1000, '1970-01-01')`, yields **UTC** — correct only if you then convert.

Also: passing **seconds** where milliseconds are expected is silently accepted and lands the query in
1970, which returns either nothing or the entire table. Check the magnitude of your bounds.

## Named queries

Full detail in [references/named-queries.md](../ignition-resources/references/named-queries.md).
The essentials:

- `:paramName` colon binding only. **Zero** of 315 queries use JDBC `?`.
- `sqlType` is Ignition's own DataType ordinal, **not `java.sql.Types`**: `7`=String, `8`=DateTime,
  `5`=Float8, `3`=Int8, `2`=Int4, `6`=Boolean.
- `scope` is `DG` and `version` is `2` — the only resource type with version 2.
- Caching is off in 312 of 315.
- Invoke with the bare name: `system.db.runNamedQuery("Get_BatchStatus", {"Path": p})`.

**Named queries are copy-pasted per equipment project, not shared.** `Get_AuditData` exists in ~40
projects, `Get_Annotations` in ~30. Fixing one fixes one bench. Decide explicitly whether you are
fixing every copy, and say which you changed.

Raw SQL actually dominates: `runPrepUpdate` 349 call sites, `runNamedQuery` 90, `runPrepQuery` 76,
`beginTransaction` 17, `runQuery` 9. Use a named query when Perspective binds to it directly; use
`runPrepQuery` inside a script library. Never use `runQuery` with a concatenated string.

## Application tables

| Table | What it holds |
|---|---|
| `EXP_STATUS` | one row per run: `EXPID, EXPNAME, PROJECTID, SAMPLEID, BYEMAIL, STARTTIME, ENDTIME, EXPSTATUS, EQUIPMENT_PATH`. Also the basis of equipment-utilisation reporting. |
| `Recipes` | `RECIPE_NAME, version, …` — recipe definitions, read by `Get_Recipes` / `Get_RecipeValues` |
| `AUDIT_EVENTS` | Ignition audit trail: `AUDIT_EVENTS_ID, EVENT_TIMESTAMP, ACTOR, ACTOR_HOST, ACTION, ACTION_TARGET, ACTION_VALUE, …` |
| `MCP_Pitfalls` | the shared pitfall KB — see the `pitfalls` skill |
| `*_sch` tables | equipment scheduler: `ScheduledEvents_sch`, `Equipment_sch`, `SchedulerConfig_sch`, … |
| `bay_opt` | per-bench optimisation parameters, keyed `(project_name, equipment_name, parameter_name)` |

The audit profile `AuditTrail` declares retention 90 days but has `PRUNEENABLED = 0`, so **retention
is not actually enforced** and the table grows without bound.

The house upsert idiom is a MSSQL `MERGE`:

```sql
MERGE bay_opt AS target
USING (SELECT :project_name AS project_name, :equipment_name AS equipment_name,
              :parameter_name AS parameter_name, :value AS value) AS source
   ON  target.project_name = source.project_name
   AND target.equipment_name = source.equipment_name
   AND target.parameter_name = source.parameter_name
WHEN MATCHED THEN UPDATE SET value = source.value, updated_at = SYSUTCDATETIME()
WHEN NOT MATCHED THEN INSERT (...) VALUES (...);
```

### Scheduler join hazard

`ScheduledEvents_sch.equipmentID` is stored as **text** while `Equipment_sch.ID` is an integer, so the
join needs a cast and a non-numeric value must not blow up the query:

```sql
JOIN Equipment_sch eq ON TRY_CAST(se.equipmentID AS INT) = eq.ID
```

## Migrations

There is **no migration tooling**. The only DDL anywhere in the estate is a **commented-out**
`CREATE TABLE` / `CREATE INDEX` block inside the `EquipmentScheduler` script library, covering
`NotificationsSent_sch`, `EventResponses_sch`, `SchedulerConfig_sch` and `ManagerNotes_sch`. Schema
changes are applied by hand by someone with database access.

If you add a table: write the DDL, keep it in the project as a comment next to the code that uses it
the way the estate already does, and hand it to a DBA. Do not attempt to apply DDL yourself.

## One anti-pattern to know about

`EquipmentScheduler` bypasses Ignition's JDBC pool entirely: it `URLClassLoader`-loads the MSSQL
driver JAR out of Ignition's `temp/jdbc` folder and opens **its own** connection to a *third* SQL
Server (`10.94.132.35:1433`, `encrypt=false;trustServerCertificate=true`). That connection is not
pooled, not monitored, not covered by store-and-forward, and its driver path breaks on upgrade. Do not
copy it. If a script needs a database Ignition does not have, add a database connection.

## Detecting that a tag stopped historizing

1. Confirm the tag is configured for history at all:
   `ign tags --provider default --path <folder>` and check `historyEnabled` and `historyProvider`.
   A missing `historyProvider` with `historyEnabled: true` logs
   `History is enabled, but history provider is not defined.` and stores nothing.
2. Check the store-and-forward engine and the database connection are healthy:
   `ign api GET /data/api/v1/overview/connections`. The Store and Forward card also carries the
   **quarantined** count.
3. Confirm the *source* still produces. A historised tag whose OPC connection is disabled or whose
   MQTT device went silent stops recording with no error on the history side — see `triage`
   branches (b) and (c).
