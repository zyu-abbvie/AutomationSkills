# Named queries

On-disk anatomy, parameter binding, and invocation of `ignition/named-query` resources in this
estate, measured over the 315 named queries in the DEV and PROD backups. Read this before you
author, edit, or fan out a named query.

## The four things people get wrong

| Mistake | What actually happens | Do this instead |
|---|---|---|
| `"version": 1` in resource.json | named-query is the ONLY resource type at version 2 (all 315) | copy `"version": 2` |
| `"scope": "G"` | named query is invisible in the Designer | `"scope": "DG"` (all 315 are DG) |
| `?` positional params in query.sql | binding fails at runtime, not at save | `:name` colon markers (259/315 use them, 0 use `?`) |
| `sqlType: 12` from `java.sql.Types` habit | parameter mis-typed | sqlType is Ignition's own DataType ordinal — see table below |
| Add `:newParam` to query.sql only | runtime failure, silent until the query runs | also add `{type,identifier,sqlType}` to `attributes.parameters` |

## Directory shape

```
<project>/ignition/named-query/[<folder>/]<Name>/
    resource.json      # 6 top-level keys, version 2, scope DG
    query.sql          # the payload; filename is fixed by resource type
```

The payload filename is `query.sql` regardless of the query name. Renaming it in `files[]` does not
make Ignition read a different file. Named queries may nest in folders before the leaf, like any
named resource type.

## resource.json: the complete key set

Real file, copied verbatim from
`/home/admin/src/Automation_Skills2/doc/Ignition-WZ02163D_Ignition-backup-20260828-1137/projects/TFF_Parent/ignition/named-query/Get_Annotations/resource.json`:

```json
{
  "scope": "DG",
  "version": 2,
  "restricted": false,
  "overridable": true,
  "files": [
    "query.sql"
  ],
  "attributes": {
    "useMaxReturnSize": false,
    "autoBatchEnabled": false,
    "fallbackValue": "",
    "maxReturnSize": 100,
    "cacheUnit": "SEC",
    "type": "Query",
    "enabled": true,
    "cacheAmount": 1,
    "cacheEnabled": false,
    "database": "SQLServer",
    "fallbackEnabled": false,
    "lastModificationSignature": "208491701e508a5777b36ae6ed7819defd1e16ad3c87f84eec9c8f90a54d4493",
    "permissions": [
      {
        "zone": "",
        "role": ""
      }
    ],
    "lastModification": {
      "actor": "SUTHEDJ",
      "timestamp": "2026-08-14T19:07:07Z"
    },
    "parameters": [
      {
        "type": "Parameter",
        "identifier": "Path",
        "sqlType": 7
      }
    ]
  }
}
```

`attributes` is a fixed 14-key set plus optional `parameters`. Copy the whole block; a missing key
like `autoBatchEnabled` or `fallbackEnabled` is a schema hole. `permissions` is
`[{"zone":"","role":""}]` in all 315 files. When you write a resource programmatically, omit
`lastModificationSignature` or set `""` — it is not a content hash and the gateway regenerates it.

### attributes.type

| type | count | use |
|---|---|---|
| `Query` | 283 | returns a dataset |
| `UpdateQuery` | 31 | INSERT/UPDATE/DELETE/MERGE; returns row count |
| `ScalarQuery` | 1 | single value |

The only `ScalarQuery` in the estate is
`.../Ignition-WA03593D_Ignition-backup-20260828-1312/projects/Ruben-Test-App/ignition/named-query/GetImage`
(`SELECT Image FROM CameraImages WHERE imageID = :ID`). If you write an UpdateQuery, `type` must say
so — an UpdateQuery declared as `Query` fails on execution.

### attributes.database

| value | count | meaning |
|---|---|---|
| `"SQLServer"` | 268 | the one canonical JDBC connection name estate-wide |
| `""` | 46 | inherit the project's `defaultDb` — the portable idiom for `*_Parent` children |
| `"SQLite_Database"` | 1 | do not use |

Prefer `""` for anything that lives in an inheritable parent, so children stay portable. Hardcoding
`"SQLServer"` is safe but note DEV and PROD `SQLServer` point at different physical servers.

The single `SQLite_Database` query is `DevSciLabs/SaveDashboard` on PROD, and that connection is a
broken placeholder: its URL is the unedited `jdbc:sqlite:C:/Path/To/File.db` and it is still
ENABLED. The query itself is also broken (`SET  WidgetJson` with no `= value`). Treat both as dead;
never copy that resource as a template.

### Caching

Off in 312 of 315. Write:

```json
"cacheEnabled": false, "cacheAmount": 1, "cacheUnit": "SEC"
```

The only exceptions are PT_Opt's `Get_AuditData`, `Get_BatchStatus`, `Get_Annotations`, at
`cacheEnabled: true, cacheAmount: 300, cacheUnit: "SEC"`. Enable caching only for a query that a
Perspective view polls and whose staleness of minutes is acceptable — audit/annotation history
qualifies, live batch state generally does not.

## Parameter binding

Bind with `:name` inside query.sql; declare each one in `attributes.parameters` as
`{"type":"Parameter","identifier":"<name>","sqlType":<int>}`. Measured: 259 of 315 query.sql use
colon markers, 0 use `?`, 56 take no parameters. `?` positional binding belongs only to raw
`system.db.runPrepQuery`/`runPrepUpdate` SQL in Jython, never inside a named query.

Complete real example — `.../Ignition-WZ02163D_Ignition-backup-20260828-1137/projects/TFF_Parent/ignition/named-query/Get_AuditData/`:

`query.sql`
```sql
SELECT DISTINCT EVENT_TIMESTAMP, ACTOR, ACTION, ACTION_TARGET, ACTION_VALUE
FROM AUDIT_EVENTS WHERE ORIGINATING_SYSTEM LIKE :Project AND EVENT_TIMESTAMP BETWEEN :Start AND :End AND ACTION <> 'tag write'
```

`resource.json` (attributes.parameters only; rest as in the block above, `type: "Query"`)
```json
"parameters": [
  {"type": "Parameter", "identifier": "Project", "sqlType": 7},
  {"type": "Parameter", "identifier": "Start",   "sqlType": 8},
  {"type": "Parameter", "identifier": "End",     "sqlType": 8}
]
```

Parameter order in resource.json need NOT match order of first use in query.sql — binding is by
name. Proof: `.../RIO_IP_Tracker/ignition/named-query/UpdateIP/` declares `IP, Name, API, backup`
while `query.sql` is `INSERT INTO dbo.RIO (IP, API, IS_BACKUP, Name) VALUES ( :IP, :API, :backup, :Name)`.
Keep them in SQL order anyway for readability.

Many query.sql files in the backups have CRLF line endings (Get_Annotations, Get_TagID). Do not
normalize them as a side effect of an edit — it produces a whole-file diff.

### sqlType is Ignition's DataType ordinal, not java.sql.Types

| sqlType | Ignition DataType | params observed | real identifier names at that type |
|---|---|---|---|
| 7 | String | 428 | `Path` (57), `Project` (44), `PATH` (39), `path` (28), `project_name` (23), `recipe` (19), `usrid` (19), `parameter_name` (14), `expid` (12), `equipment_name` (12) |
| 8 | DateTime | 96 | `Start` (44), `End` (44), `eventSDate`, `eventEDate`, `startDate`, `endDate` |
| 5 | Float8 | 33 | `version` (19), `lower_bound` (7), `upper_bound` (7) |
| 3 | Int8 | 16 | `refresh` (4), `eventID` (4), `equipmentId` (3), `equipmentID` (2), `percentDone` (2), `ID` (1) |
| 2 | Int4 | 8 | `myValueY` (6), `equipment_name` (2) |
| 6 | Boolean | 6 | `enabled` (2), `backup`, `Value`, `notification`, `Notification` |

If you reach for `java.sql.Types` values you get silently wrong types: `12` (VARCHAR there) is not a
string here, `4` (INTEGER there) is not an integer here, `93` (TIMESTAMP there) is out of range.
The failure mode is a coercion error or a wrong-typed comparison at execution, and the resource
saves cleanly, so it survives review. Use 7 / 8 / 3 / 6 / 5 / 2 as above.

Two live inconsistencies to not copy: `version` is declared Float8 (5) although recipe versions are
integers, and PROD `Bayesian_Platform_Alpha/delete_config` declares `equipment_name` as sqlType 2
(Int4) for a string column — that is why Int4 shows a string-looking name in the table above.

## Invocation

Single-arg, project-scoped, plain dict. No project prefix.

```python
params = {"Path": "%309-3-2%"}
dataset = system.db.runNamedQuery("Get_Annotations", params)
```

Call site: `.../Ignition-WA03593D_Ignition-backup-20260828-1312/projects/FC_Parent/ignition/script-python/Report/code.py:26`.
Webdev variant: `.../File_Transfer/com.inductiveautomation.webdev/resources/download/doGet.py:14`
`system.db.runNamedQuery("download", {"name": filename})`.

From a Perspective view, a `query` binding references a named query by bare name via
`config.queryPath`. Top values across 1197 view.json: `Get_Annotations` 75, `Get_BatchStatus` 42,
`Get_AuditData` 42, `Get_RecipeValues` 28, `Get_Recipes` 14.

There is no HTTP API route for project resources on 8.3 DEV — `/data/api/v1/resources/*` covers
gateway config only. To read live named-query text without auth, use
`GET /data/api/v1/projects/export/{project}` and pull `ignition/named-query/<Name>/query.sql` out of
the zip.

## Named queries are copy-pasted, not shared

There is no shared library. Each equipment project carries its own copy of the same query. Folder
counts across both backups:

| Name | folders | query.sql present |
|---|---|---|
| `Get_Annotations` | 48 | 47 |
| `Get_AuditData` | 45 | 44 |
| `Get_BatchStatus` | 40 | 39 |
| `Get_TagID` | 29 | 28 |

315 parseable resource.json / 318 query.sql paths total, but only a few dozen distinct queries. The
largest single library is PROD `ExpMetadata` with 28 named queries.

Consequences for any change:

- A "fix Get_TagID" task is a 29-copy fan-out decision, not a one-file edit. Decide explicitly:
  fix all copies, or fix only the project in scope and say so in the change note.
- If the query lives in an inheritable parent, edit the parent and the children inherit. PROD
  `TFF_Parent` has 20 children; DEV `TFF_Parent` has 1. Check the blast radius before editing a
  parent.
- Only 8 of the 40 DEV projects inherit at all, so most DEV named-query edits are genuinely local.
- Before you add a new query, grep for the name across both backups. If it already exists somewhere,
  copy that resource wholesale (resource.json + query.sql) instead of writing new SQL.

## Real defects to guard against

**The ExperimentRecall stub has a wrong join key.** In
`.../Ignition-WZ02163D_Ignition-backup-20260828-1137/projects/TFF_Parent/ignition/named-query/ExperimentRecall/query.sql`,
lines 1-4 are a commented draft:

```sql
--SELECT * --sqlt_data_1_2024_8.stringvalue
--FROM sqlt_data_1_2024_8
--  INNER JOIN sqlth_te ON sqlt_data_1_2024_8.tagid = sqlth_te.tagid
--WHERE sqlth_te.tagpath LIKE :Path
```

`sqlth_te` has no `tagid` column; its PK is `id`. The live SELECT below the comment in the same file
gets it right (`ON sqlth_annotations.tagid = sqlth_te.id`), as does every `Get_Annotations` copy.
Always join `<other>.tagid = sqlth_te.id`. Copy the live SELECT, never the commented stub.

**DEV LF_Parent_2 has named-query payloads that are empty DIRECTORIES.** In
`/home/admin/src/Automation_Skills2/doc/Ignition-WA03593D_Ignition-backup-20260828-1312/projects/LF_Parent_2/ignition/named-query/`,
`Get_TagID`, `Get_AuditData`, and `Get_BatchStatus` each contain `query.sql/` and `resource.json/`
as empty directories; `Get_Annotations` has `resource.json/` as a directory. Any tooling that globs
and opens dies with `IsADirectoryError: [Errno 21] Is a directory`.

```python
import os, glob, json
for r in glob.glob(root + "/*/projects/*/ignition/named-query/**/resource.json", recursive=True):
    if not os.path.isfile(r):        # LF_Parent_2 hits this
        continue
    attrs = json.load(open(r))["attributes"]
```

Same guard for `query.sql`. The 315-vs-318 gap in the counts above is exactly this.

## Named query vs runPrepQuery

The estate's actual split, from `grep -rn "system.db." doc | grep -oP "system\.db\.[a-zA-Z]+"`:

| API | calls |
|---|---|
| `runPrepUpdate` | 349 |
| `runNamedQuery` | 90 |
| `runPrepQuery` | 76 |
| `beginTransaction` | 17 |
| `runScalarPrepQuery` | 13 |
| `runQuery` | 9 |
| `runScalarQuery` | 1 |

Raw SQL outnumbers named queries roughly 5:1. That is not a pattern to emulate — it is why SQL text
is scattered across Jython, SFC XML, and webdev handlers where it cannot be found or reviewed.

House rule:

- Anything a Perspective view binds to: named query. A `query` binding cannot call
  `runPrepQuery` at all.
- Any read whose SQL text you would otherwise write twice: named query.
- `runPrepUpdate` / `runPrepQuery` with `?` params: acceptable for one-off writes inside a script
  that already owns the logic (annotation insert, scheduler tables), and required when you need an
  explicit transaction (`beginTransaction` / `commit` / `closeTransaction`) or dynamic SQL that
  cannot be parameterized.
- Never build SQL by string concatenation of user or tag values in either path.
- Never use `system.db.runQuery` / `runScalarQuery` (no parameters at all) — 10 calls exist and all
  of them should be prepared or named.
