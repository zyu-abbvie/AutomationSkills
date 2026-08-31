---
name: ignition-resources
description: Author, edit and review Ignition project resources on disk - Perspective views and style classes, script-python libraries, named queries, tag and UDT configuration, SFC charts, webdev HTTP endpoints, timer and startup scripts, page-config and session-props, and parent/child project inheritance. Use when creating or changing anything inside an Ignition project folder, when reviewing an Ignition resource for the defects that make the Gateway silently drop it, or when you need the exact on-disk shape of a resource.json, view.json or query.sql.
---

# Ignition project resources

There is **no HTTP API for project resources**. `/data/api/v1/resources/**` covers gateway *config*
only; requests for views, named queries or scripts 404. Your three routes in are:

1. **Files on disk** — a gateway backup, or the live `data/projects/` tree. Primary.
2. **`GET /data/api/v1/projects/export/{name}`** — works **unauthenticated** on dev, returns a zip
   whose layout is exactly the on-disk tree. The zero-auth way to read live state.
3. **MCP `readResource` / `writeResource` / `listResources`** — needs auth. See `ignition-gateway`.

The Designer owns these files. **Default to read-only**; edit only when asked.

```bash
${CLAUDE_PLUGIN_ROOT}/bin/ign export TFF_Parent -o /tmp/tff.zip   # live state, no credentials
${CLAUDE_PLUGIN_ROOT}/bin/ign-validate /path/to/project           # before you hand it back
```

## The shape of every resource

```
<Project>/<moduleId>/<resourceType>/[<nested folders>/]<Name>/
    resource.json          ← the manifest, always
    <payload>              ← filename is FIXED BY THE TYPE, not chosen by you
```

`moduleId` is a reverse-DNS module name (`com.inductiveautomation.perspective`) or the literal
`ignition` for platform resources. Singleton types (`page-config`, `session-props`, `global-props`,
`startup`, `shutdown`, `update`, `stylesheet`) put `resource.json` directly under the type folder
with no `<Name>` level.

**The payload filename is fixed per type.** Renaming it in `files[]` does not make Ignition read it.

| Type | Payload |
|---|---|
| `com.inductiveautomation.perspective/views/<path>/<Name>` | `view.json` (+ `thumbnail.png`) |
| `com.inductiveautomation.perspective/style-classes/<Name>` | `style.json` |
| `com.inductiveautomation.perspective/page-config` | `config.json` |
| `com.inductiveautomation.perspective/session-props` | `props.json` |
| `ignition/named-query/<Name>` | `query.sql` |
| `ignition/script-python/<Lib>` | `code.py` |
| `ignition/timer/<Name>` | `handleTimerEvent.py` |
| `ignition/startup` / `shutdown` / `update` | `onStartup.py` / `onShutdown.py` / `onUpdate.py` |
| `com.inductiveautomation.sfc/charts/<path>/<Name>` | `sfc.xml` |
| `com.inductiveautomation.webdev/resources/<Name>` | `config.json` + `do<Method>.py` ×8 |
| `com.inductiveautomation.mcp/tools/<Name>` | `onToolCalled.py` |

### `resource.json` — exactly six keys

```json
{
  "scope": "G",
  "version": 1,
  "restricted": false,
  "overridable": true,
  "files": ["view.json", "thumbnail.png"],
  "attributes": {}
}
```

- **`scope`** is per-type and consistent: `G` gateway (views, style-classes, page-config,
  session-props, sfc, webdev, timer, mcp/tools), `A` all scopes (global-props, reports, most
  script-python), `DG` designer+gateway (**every** named-query), `C`/`D`/`CG` for legacy Vision and
  designer-properties. Match the sibling of the same type.
- **`version`** is `1` for every type **except `ignition/named-query`, which is `2`**.
- **`files[]`** must list every payload file. A file on disk but absent from `files[]` is ignored.
- **Omit `lastModificationSignature`.** It is **not** a content hash — resources with
  byte-different `view.json` carry identical signatures, and 68 of 3830 resource.json files omit it
  entirely while loading fine. Set `"attributes": {}` and let the gateway fill it in. Never invent one.

A resource folder with **no `resource.json` is not a resource** and is silently omitted.

## Perspective views

`view.json` has four keys that are always present and three optional ones:

```json
{
  "custom": {},
  "params": {},
  "props": {},
  "root": { "meta": { "name": "root" }, "type": "ia.container.coord" }
}
```

That 141-byte document is a valid view. `propConfig`, `events` and `permissions` are optional.

Inside the tree:

- A component is an object with **`meta.name`** and **`type`**; children nest under **`children[]`**.
- **Static values** go in `props`.
- **Bindings do not live next to the prop.** They go in a **sibling `propConfig` map keyed by the
  dotted prop path** — `"props.text"`, `"custom.TagID"`, `"params.icon"`. This is the single most
  common structural mistake.
- **Event handlers** go under `events.<category>.<name>`, category being `dom`, `component` or
  `system` (`component.onActionPerformed`, `dom.onClick`, `system.onStartup`).

Only **six binding types** exist anywhere in this estate — use one of them:
`expr`, `property`, `tag`, `query`, `tag-history`, `expr-struct`; with transforms `script`,
`expression`, `format`, `map`. A `query` binding names a named query by bare name in
`config.queryPath`.

The **indirect tag binding** is how one parent view serves every bench:

```json
{"type": "tag", "config": {
  "mode": "indirect", "bidirectional": true, "fallbackDelay": 2.5,
  "references": {"1": "{session.custom.Building}", "2": "{session.custom.RoomFloorBench}"},
  "tagPath": "[default]{1}/{2}/TFF/CurrentEmail"}}
```

See [references/perspective.md](references/perspective.md) for the full binding/transform/event
census and a worked view.

## Named queries

- Parameters are **named colon markers** — `:paramName` matching
  `attributes.parameters[].identifier`. **Never JDBC `?`.** 259 of 315 queries use colon markers;
  zero use `?`.
- **`sqlType` is Ignition's own DataType ordinal, not `java.sql.Types`**:
  `7`=String, `8`=DateTime, `5`=Float8, `3`=Int8, `2`=Int4, `6`=Boolean.
- `database` is `"SQLServer"` (the canonical connection) or `""` meaning "use the project default".
- `version` is `2`. Caching is off in 312 of 315.

```sql
SELECT Image FROM CameraImages WHERE imageID = :ID
```
```json
{"type": "Query", "database": "SQLServer", "enabled": true,
 "parameters": [{"type": "Parameter", "identifier": "ID", "sqlType": 3}]}
```

Invoke as `system.db.runNamedQuery("GetImage", {"ID": 42})`. Details in
[references/named-queries.md](references/named-queries.md).

## Project inheritance

`project.json` has exactly five fields, and `parent` is **optional** (28 of 114 prod projects omit
it, which means the same as `""`):

```json
{"title": "", "description": "", "enabled": true, "inheritable": false, "parent": "TFF_Parent"}
```

Inheritance is **exactly one level deep** — no grandparent chains. A `*_Parent` **name does not mean
`inheritable: true`** (prod `BO_Parent`, `PSM_Parent`, `WM_Parent1` are all `false`). Read the file.

**The per-equipment customization mechanism is `session-props` + `page-config`** — all 52 prod child
projects override exactly that pair. Next most common: `global-props` (25), `views/Page/Main` (22),
`views/Page/Charts` (15). Before editing a resource in a child, check whether the parent has the same
path: the child copy is probably a deliberate override.

## Binary files

`data.bin` is **two mutually incompatible formats**. Sniff the first two bytes:

- **`0x1f8b`** — gzipped Java serialization. **Never hand-edit.** All of `ignition/global-props`,
  `ignition/event-scripts`, `reporting/reports`, `alarm-notification/alarm-pipelines`,
  `ignition/designer-properties`, `vision/*`.
- **`{`** — plain UTF-8 JSON, **safe to edit**: Perspective `session-scripts`,
  `session-permissions`, `inactivity-properties`, `general-properties`, `symbol-state-settings`,
  `tag-drop-settings`.

"Never touch `data.bin`" is the common advice and it is over-broad — but check the magic bytes
before you rely on that.

To read an 8.1 project's gateway event scripts (they are inside the gzip blob):

```bash
python3 -c "import gzip,sys; print(gzip.open(sys.argv[1],'rb').read().decode('utf-8','replace'))" \
  <backup>/projects/<Proj>/ignition/event-scripts/data.bin | grep -a 'def \|system\.'
```

Also binary: every view `thumbnail.png`, and webdev static assets stored as `file.bin`.

## Jython 2.7, not Python 3

Every `.py` under a project runs in the gateway JVM. No f-strings, `print x`, integer division,
`long`. **Java exceptions escape `except Exception`** — the estate's canonical idiom is to catch
`java.lang.Exception` as well. See `ignition-gateway` for the scripting conventions and
`sql-historian` for DB access patterns.

## Before you hand work back

Run the validator — it catches the defects that make the Gateway **silently drop** a resource:

```bash
${CLAUDE_PLUGIN_ROOT}/bin/ign-validate /path/to/project
```

These are real defects found in this estate, authored by earlier agents:

- `Martillac-Alarms/…/session-props/resource.json` declares `files: ["session-props.json"]` and the
  directory holds both `session-props.json` and the real `props.json`. The payload filename is fixed
  by the type — renaming it in `files[]` does not make Ignition read it.
- `FLEX01-R8-320-3-1` has a `resource.json` at `com.inductiveautomation.perspective/` level
  declaring `stylesheet.css`, where the correct location is
  `com.inductiveautomation.perspective/stylesheet/stylesheet.css` — and the CSS file is missing.
- The same project has a `resource.json` with **both** a stray top-level `lastModification` holding
  an epoch-millis number and a correct ISO one inside `attributes`.

Two more things that will confuse a diff:

- The Designer writes JSON with **Gson HTML-safe escaping** — `=` becomes `=`, `'` becomes
  `'`, also `<`, `>`, `&`. 800 of 7003 JSON files contain these. Do not "fix" them.
- `projects/export/{name}` **rewrites most `resource.json` files** — recomputed signature,
  `actor: "external"`, normalized key order. Measured on `TFF_Parent`: of 138 files, all 100 payload
  files were byte-identical to the backup and **every one of the 38 differences was a `resource.json`**
  (13 of 51 happened to match). So **diff payload files only**; compare `resource.json` as parsed JSON
  if you must compare it at all.

## References

- [references/perspective.md](references/perspective.md) — view.json anatomy, bindings, events, styles
- [references/named-queries.md](references/named-queries.md) — parameters, sqlType, caching, invocation
- [references/resource-types.md](references/resource-types.md) — every type, scope, payload, and counts
