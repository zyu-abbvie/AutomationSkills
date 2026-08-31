# Ignition historian schema, as used in this estate

Column lists, the partition-discovery query, and the canonical queries. Everything here reflects the
`SQLServer` SqlHistorian provider on both gateways (1-month partitions, `driverId = 1`, pruning
disabled).

Remember there are two different physical servers behind the one connection name: dev `WQ01982D`,
prod `WA06015P`. Tag ids are **not** the same on both.

## `sqlth_te` — tag entry

Maps a tag path to the numeric id every other table joins on.

| Column | Notes |
|---|---|
| `id` | **primary key.** This is what `sqlth_annotations.tagid` and `sqlt_data_*.tagid` reference. Not `tagid`. |
| `tagpath` | the historised tag path, lower-cased, without the provider bracket |
| `scid` | scan class / history group id |
| `datatype` | Ignition datatype ordinal |
| `querymode` | |
| `created_ms` / `retired` | `retired` is non-null once the tag stops being historised. A path can appear **more than once** with different ids as it is retired and recreated. |

Because a path can have several ids, a query that assumes one row per path will silently drop history
across a rename or a re-creation:

```sql
-- resolve a path to every id it has ever had
SELECT id, created_ms, retired FROM sqlth_te
WHERE tagpath = :Path ORDER BY created_ms;
```

`tagpath` is stored **lower-case** and without the `[provider]` prefix. Compare accordingly.

## `sqlt_data_<driverId>_<YYYY>_<M>` — the value partitions

One table per month. `driverId` is `1` here, and the month is **not zero-padded**:
`sqlt_data_1_2024_8`, `sqlt_data_1_2026_1`.

| Column | Notes |
|---|---|
| `tagid` | joins `sqlth_te.id` |
| `intvalue` | populated for integer and boolean tags |
| `floatvalue` | populated for float tags |
| `stringvalue` | populated for string tags |
| `datevalue` | populated for date tags |
| `dataintegrity` | quality code. `192` is good. Rows with other values are bad-quality samples and are still stored. |
| `t_stamp` | epoch **milliseconds**, **UTC** |

Only one of the four value columns is non-null per row, so a generic read has to coalesce:

```sql
COALESCE(CAST(floatvalue AS FLOAT), CAST(intvalue AS FLOAT)) AS value
```

Filtering on `dataintegrity = 192` is what turns "why does my average look wrong" into a correct
number — bad-quality samples are in the table.

### Discovering the partitions you need

The estate does this through `sys.tables` rather than `sqlth_partitions`:

```sql
SELECT name FROM sys.tables
WHERE name LIKE 'sqlt_data_1_%'
ORDER BY name;
```

To span a range you generate one statement per matching month and union them. The pattern used in the
estate: create a temp table of tag ids from `sqlth_te`, build an `NVARCHAR(MAX)` of
`INSERT … SELECT … FROM sqlt_data_1_<y>_<m> …` per partition, then `EXEC sp_executesql`. Prefer
`system.tag.queryTagHistory` unless you specifically need this.

## `sqlth_annotations` — operator notes

| Column | Notes |
|---|---|
| `id` | primary key |
| `tagid` | joins `sqlth_te.id` |
| `start_time` / `end_time` | epoch **milliseconds**, **UTC**. For a point note both are set to the same value. |
| `type` | `'note'` in practice |
| `datavalue` | the note text |
| `deleted` | soft-delete flag where present |

The canonical query, replicated in ~30 projects as `Get_Annotations`:

```sql
SELECT a.start_time, a.end_time, a.type, a.datavalue
FROM sqlth_annotations a
JOIN sqlth_te t ON a.tagid = t.id
WHERE t.tagpath = :Path
  AND a.start_time BETWEEN :Start AND :End
ORDER BY a.start_time;
```

`:Start` and `:End` are `sqlType` 8 (DateTime) and must arrive as epoch **milliseconds**.

Annotations are written from Jython rather than through a named query — a short shared script does:

```python
system.db.runPrepUpdate(
    "INSERT INTO sqlth_annotations (tagid, start_time, end_time, type, datavalue) "
    "VALUES (?,?,?,?,?)",
    [tagid, ts, ts, 'note', text], "SQLServer")   # ts = int(time.time() * 1000)
```

Note it writes `int(time.time() * 1000)` — a **UTC** epoch, consistent with how the historian stores
time. Application tables in the same database do not follow this convention.

## Tables that are absent

`sqlth_partitions`, `sqlth_sce`, `sqlth_drv`, `sqlth_scinfo` are referenced **nowhere** in this
estate's SQL. They exist in the Ignition schema; the estate simply does not use them. If you write a
query against one, you are the first, and nothing else will corroborate your result — verify it
against a `sys.tables` count before relying on it.

## `system.tag.queryTagHistory` return shape

```python
data = system.tag.queryTagHistory(
    paths=["[default]B5/2071-2-1/TFF/P1 Value"],
    startDate=start, endDate=end,
    returnSize=500,               # 0 = raw samples, -1 = one row, N = N evenly spaced rows
    aggregationMode="Average",    # Average MinMax LastValue SimpleAverage Range Count ...
    returnFormat="Wide")          # Wide = one column per tag; Tall = path/value/timestamp rows
```

Returns a Dataset. `returnFormat="Wide"` gives `t_stamp` plus one column per path; the house idiom for
turning it into rows:

```python
cols = [str(data.getColumnName(i)) for i in range(data.getColumnCount())]
rows = [dict(zip(cols, [data.getValueAt(r, c) for c in range(len(cols))]))
        for r in range(data.getRowCount())]
```

`returnSize=0` gives raw samples, which is what you want when investigating a gap — an aggregated
query interpolates over the gap and hides it.

Timestamps come back as `java.util.Date` in gateway-local time, not epoch millis. Format with
`system.date.format`, and do not compare them directly against a `t_stamp` bigint.
