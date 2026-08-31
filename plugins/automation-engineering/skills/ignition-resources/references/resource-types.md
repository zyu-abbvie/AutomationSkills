# Resource type catalogue

Every Ignition project resource type present in this estate: where its folder goes, what its payload
file must be called, and what `resource.json` has to say about it. Counts are from the two backups
under `$BACKUPS/` (DEV = WA03593D, 40 projects, 8.3.7; PROD = WZ02163D,
114 projects, 8.1.28).

> **Paths in this document.** `$DEV` and `$PROD` are the `projects/` directories inside an
> Ignition gateway backup, `$NODERED` a directory of groov RIO device backups. Set them to wherever
> you keep yours, or put `backups_dir` / `nodered_backups_dir` in `automation.local.yaml`:
>
> ```bash
> DEV=<backups>/Ignition-<DEVHOST>_Ignition-backup-<stamp>/projects
> PROD=<backups>/Ignition-<PRODHOST>_Ignition-backup-<stamp>/projects
> NODERED=<backups>/backup_nodered
> ```

## Four things that silently fail

| Mistake | What happens | Do instead |
|---|---|---|
| Renaming the payload file in `files[]` | Ignored. The payload filename is fixed by the resource *type*, not by `files[]`. DEV `Martillac-Alarms` declares `files:["session-props.json"]` and ships both that file and the real `props.json` | Use the canonical filename from the table below |
| Putting `resource.json` at the module folder level | Not a resource. DEV `FLEX01-R8-320-3-1/com.inductiveautomation.perspective/resource.json` declares `stylesheet.css` at module level; the correct path is `com.inductiveautomation.perspective/stylesheet/stylesheet.css` (see PROD `RecipeManager`) | Put `resource.json` at the leaf folder |
| Creating the payload folder with no `resource.json` | Invisible. `TFF_Parent/.../views/Framework/` exists on disk, is empty, and the gateway export omits it | Always write `resource.json` |
| Guessing `scope` or `version` | A named query with `scope:"G"` is invisible in the Designer; a script library with `G` instead of `A` does not load in session scope | Copy from a sibling of the same type (table below) |

## Path grammar

```
<projects>/<ProjectName>/<moduleFolder>/<resourceType>/[<nested>/…/<Name>]/{resource.json, <payload>}
```

`<moduleFolder>` is a reverse-DNS module id (`com.inductiveautomation.perspective`) or the literal
`ignition` for platform resources. **Singleton** types put `resource.json` directly under the type
folder. **Named** types nest arbitrarily deep before the leaf
(`views/Page/Embedded/Title/`, `sfc/charts/TFF/Fill/`, `script-python/shared/PumpControl/`).
Resource names may contain dots — `webdev/resources/PE_loading.gif/` is a legal folder name.

## Master table

Counts are resources (i.e. `resource.json` files) in DEV / PROD.

| Module folder | Resource type | Payload file(s) | Scope | Ver | Shape | DEV / PROD |
|---|---|---|---|---|---|---|
| `com.inductiveautomation.perspective` | `views` | `view.json` + `thumbnail.png` | G | 1 | named | 284 / 913 |
| | `style-classes` | `style.json` | G | 1 | named | 386 / 1081 |
| | `stylesheet` | `stylesheet.css` | G | 1 | singleton | 0 / 1 |
| | `page-config` | `config.json` | G | 1 | singleton | 38 / 113 |
| | `session-props` | `props.json` | G | 1 | singleton | 38 / 113 |
| | `session-scripts` | `data.bin` (**JSON**) | G | 1 | singleton | 2 / 11 |
| | `session-permissions` | `data.bin` (**JSON**) | G | 1 | singleton | 5 / 26 |
| | `inactivity-properties` | `data.bin` (**JSON**) | G | 1 | singleton | 2 / 7 |
| | `general-properties` | `data.bin` (**JSON**) | G | 1 | singleton | 2 / 6 |
| | `symbol-state-settings` | `data.bin` (**JSON**) | G | 1 | singleton | 0 / 4 |
| | `tag-drop-settings` | `data.bin` (**JSON**) | G | 1 | singleton | 0 / 3 |
| `ignition` | `named-query` | `query.sql` | **DG** | **2** | named | 49 / 266 |
| | `script-python` | `code.py` | **A** (66) or G (10) | 1 | named | 24 / 52 |
| | `timer` | `handleTimerEvent.py` | G | 1 | named | 13 / 0 |
| | `startup` | `onStartup.py` | G | 1 | singleton | 1 / 0 |
| | `shutdown` | `onShutdown.py` | G | 1 | singleton | 1 / 0 |
| | `update` | `onUpdate.py` | G | 1 | singleton | 1 / 0 |
| | `event-scripts` | `data.bin` (gzip) | G | 1 | singleton | 1 / 11 |
| | `global-props` | `data.bin` (gzip) | A | 1 | singleton | 32 / 86 |
| | `designer-properties` | `data.bin` (gzip) | **D** | 1 | singleton | 0 / 4 |
| `com.inductiveautomation.sfc` | `charts` | `sfc.xml` | G | 1 | named | 21 / 95 |
| `com.inductiveautomation.webdev` | `resources` | `config.json` + 8 `do<Method>.py`, or `file.bin` | G | 1 | named | 9 / 30 |
| `com.inductiveautomation.reporting` | `reports` | `data.bin` (gzip) | A | 1 | named | 6 / 28 |
| `com.inductiveautomation.alarm-notification` | `alarm-pipelines` | `data.bin` (gzip) | G | 1 | named | 4 / 2 |
| `com.inductiveautomation.mcp` | `tools` | `onToolCalled.py` | G | 1 | named | 19 / 0 |
| `com.inductiveautomation.eventstream` | `event-streams` | `config.json` | G | 1 | named | 1 / 0 |
| `com.inductiveautomation.vision` | `client-tags` | `data.bin` (gzip) | **C** | 1 | singleton | 10 / 4 |
| | `ui-properties` | `data.bin` (gzip) | **C** | 1 | singleton | 0 / 1 |
| | `launch-properties` | `data.bin` (gzip) | **CG** | 1 | singleton | 0 / 1 |
| `com.inductiveautomation.sqlbridge` | `transaction-groups` | — | — | — | — | 0 / 1 (empty) |

Notes on the sparse rows:

- `mcp/tools` and `eventstream/event-streams` are 8.3-only and exist in exactly one DEV project each
  (`MCP_Tools`, `Flow_Sensor_Tester`). `sqlbridge/transaction-groups` exists only on PROD
  (`Syringe_pump_comm`) and is an **empty directory with no `resource.json`** — there is no example
  to copy in either gateway.
- `stylesheet` has exactly one working instance estate-wide: PROD `RecipeManager`.
- `timer`/`startup`/`shutdown`/`update` are the 8.3 form only. See the version split below.
- Two DEV `LF_Parent_2` folders contain `data.bin` and `resource.json` as empty *directories*
  (`com.inductiveautomation.perspective/session-permissions/`,
  `com.inductiveautomation.reporting/reports/ExpReport/`). They are non-resources. Stat before read.

## Module folder presence

Projects containing each module folder (DEV / PROD), from
`find . -maxdepth 2 -mindepth 2 -type d | sed 's|.*/||' | sort | uniq -c`:

| Module folder | DEV | PROD |
|---|---|---|
| `com.inductiveautomation.perspective` | 39 | 113 |
| `ignition` | 35 | 86 |
| `com.inductiveautomation.vision` | 10 | 4 |
| `com.inductiveautomation.sfc` | 7 | 36 |
| `com.inductiveautomation.reporting` | 7 | 26 |
| `com.inductiveautomation.webdev` | 4 | 15 |
| `com.inductiveautomation.alarm-notification` | 4 | 2 |
| `com.inductiveautomation.mcp` | 1 | 0 |
| `com.inductiveautomation.eventstream` | 1 | 0 |
| `com.inductiveautomation.sqlbridge` | 0 | 1 |

The gateway tolerates unknown top-level folders inside a project. DEV carries three that are not
module ids at all and load fine: `LargeScaleFC/Node-Red/`,
`LargeScaleFC/LargeScaleFC_Project_2026-05-11_1428.zip`, and `MCP_Tools/MCP_Tools/` (a self-nested
extracted copy of the whole project). Do not treat their presence as corruption, and do not count
them — the self-nested `MCP_Tools/MCP_Tools/` copy inflates naive resource censuses by 20.

## resource.json

Exactly six top-level keys, in all 3830 files across both trees, no exceptions:

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

`restricted` is `false` in all 3830. `overridable` is `true` in 3823 and `false` in 7.
`version` is `1` for every type **except `ignition/named-query`, which is `2` in all 315**.

Scope values — six exist, and each type uses one consistently:

| Scope | Meaning | Count | Types |
|---|---|---|---|
| `G` | Gateway | 3275 | views, style-classes, stylesheet, page-config, session-*, sfc/charts, webdev, mcp/tools, eventstream, timer/startup/shutdown/update, event-scripts, alarm-pipelines |
| `A` | All | 219 | `ignition/global-props` (118), `reporting/reports` (34), 66 of 76 `script-python` |
| `DG` | Designer + Gateway | 315 | every `ignition/named-query` |
| `C` | Client | 16 | `vision/client-tags`, `vision/ui-properties` |
| `D` | Designer | 4 | `ignition/designer-properties` |
| `CG` | Client + Gateway | 1 | `vision/launch-properties` |

`ignition/script-python` is the only type that splits: `{G: 10, A: 66}`. The `A` variants also carry
`attributes.hintScope` (e.g. `2`). Prefer `A` for a shared script library.

`attributes` is type-specific. Fully-specified examples worth copying verbatim:
`$DEV/Ruben-Test-App/ignition/named-query/GetImage/resource.json`
(14-key named-query block: `useMaxReturnSize, autoBatchEnabled, fallbackValue, maxReturnSize,
cacheUnit, type, enabled, cacheAmount, cacheEnabled, database, fallbackEnabled, permissions` plus the
two `lastModification*` keys, plus optional `parameters`) and
`.../projects/LF_Parent/ignition/timer/WeightData/resource.json` (`sharedThread, delay, fixedDelay,
enabled`).

## lastModificationSignature is not a content hash

Do not compute one, do not trust one, do not diff on one.

- **Not a payload hash.** DEV `PT` and `PT_Opt` `views/Page/history/` have byte-identical
  `resource.json` (md5 `19a45b0a3233f2947574e0dd987a3b78` both) and byte-identical `thumbnail.png`,
  but different `view.json` (`f2fc2c7c…`, 68589 B vs `1a8a998b…`, 77789 B). Conversely, of 1320
  distinct payload hashes across 3729 signed resources, 165 map to more than one signature and 5
  signatures map to more than one payload.
- **Optional.** Of 3830 `resource.json`, 68 omit the key entirely (24 style-classes, 22 views, 8
  script-python, 5 timer, 4 global-props, 2 mcp/tools, …) and 33 more carry `""`. Those projects are
  enabled and running.
- **The gateway regenerates it.** `GET /data/api/v1/projects/export/TFF_Parent` emits
  `"attributes": {}` for `ignition/global-props`, and fills in every `""` signature with a fresh one.

**Rule when authoring: omit `lastModificationSignature`. Write `"attributes": {}` unless the type
needs real attributes.** If you write a `lastModification`, it goes *inside* `attributes` with an
ISO-8601 Z timestamp — DEV `FLEX01-R8-320-3-1/ignition/script-python/flex01/resource.json` has both a
stray top-level `lastModification` with epoch millis (`actor "claude"`, `1779382462369`) and a correct
one inside `attributes`. The top-level one is wrong.

Corollary: never diff `resource.json` between a live export and a backup. The export rewrites the
signature, sets `lastModification` to `{actor:"external", timestamp:<project load time>}`, and
normalizes key order and indentation. Payload files come out byte-identical. Diff payloads only.

## data.bin: two incompatible formats

"Never edit `data.bin`" is over-broad. Sniff the first two bytes:

```bash
python3 -c "
import glob,os,collections
c=collections.Counter()
for p in glob.glob('<projects>/**/*.bin',recursive=True):
    if os.path.isfile(p): c[open(p,'rb').read(2)]+=1
print(c)"
# Counter({b'\x1f\x8b': 192, b'{\n': 52, b'{\"': 13, b'GI': 5, b'{}': 3})
```

| Magic | Format | Editable | Types (file counts, both trees) |
|---|---|---|---|
| `1f 8b` | gzip-wrapped Ignition binary serialization | **No** | `ignition/global-props` 119, `reporting/reports` 34, `vision/client-tags` 13, `ignition/event-scripts` 12, `alarm-notification/alarm-pipelines` 6, `ignition/designer-properties` 4, `vision/launch-properties` 1, `vision/ui-properties` 1 |
| `{` | plain UTF-8 JSON | **Yes** | `perspective/session-permissions` 31, `session-scripts` 13, `inactivity-properties` 9, `general-properties` 8, `symbol-state-settings` 4, `tag-drop-settings` 3 |
| `GI` | binary asset, always named `file.bin` not `data.bin` | **No** | `webdev/resources/<Name>.gif/file.bin` (5 copies, PROD) |

Example editable one —
`.../TFF_Parent/com.inductiveautomation.perspective/session-scripts/data.bin`:
`{"onPageStartup":"\tpage.session.custom.loadCompleted = 0","onBarcodeDataReceived":"\t",…}`.

All 192 gzip files share the same 16-byte inner magic `98298faa43f74a4fb28dca3c4896afc9`, followed by
Ignition's class/method string table. You can *read* them without a gateway:

```bash
python3 -c "
import gzip,re
b=gzip.open('<path>/ignition/event-scripts/data.bin','rb').read()
print('\n'.join(s.decode() for s in re.findall(rb'[ -~\t\n]{25,}',b)))"
```

Do not decode `global-props/data.bin` to find a project's default DB, tag provider or user source.
`GET http://wa03593d:8088/data/api/v1/projects/find/<name>` returns them decoded and unauthenticated.

## Gateway event scripts: 8.3 vs 8.1

| | DEV 8.3.7 | PROD 8.1.28 |
|---|---|---|
| Timer scripts | `ignition/timer/<Name>/handleTimerEvent.py` (13 resources, 9 projects) | none |
| Startup / shutdown / update | `ignition/startup/onStartup.py`, `ignition/shutdown/onShutdown.py`, `ignition/update/onUpdate.py` | none |
| Storage | plain text, greppable, editable | all of the above packed into one gzip `ignition/event-scripts/data.bin` (11 projects) |

8.3 reads both forms: DEV `Bayesian_Platform_Alpha` still carries the legacy
`ignition/event-scripts/data.bin`. To read a PROD timer script, gunzip and scrape — the command above
on `.../TFF-Teller-BSL3-2-1/ignition/event-scripts/data.bin` recovers the Jython directly:

```
tagPaths = ["[MQTT Engine]IRVINE/Teller/BSL3-2-1/TFF/Calc_Val/FT-01 (Recirc Flow)", …]
data = system.tag.readBlocking(tagPaths)
```

## SFC charts (sfc.xml)

117 `sfc.xml` estate-wide (21 DEV / 95 PROD resources). Root element and the three lifecycle hooks,
from `.../WZ02163D…/projects/TFF_Parent/com.inductiveautomation.sfc/charts/TFF/Fill/sfc.xml`:

```xml
<?xml version="1.0" ?>
<sfc zoom="1.0" canvas="22 29" execution-mode="Callable" hot-editable="false" persist-state="true" redundant-sync="false">
	<onstart>def onStart(chart): # WARNING: This resource was generated in a newer version of Ignition. For the best editing experience, recreate it in the current version.
	pass</onstart>
	<onstop>def onStop(chart): # WARNING: …</onstop>
	<oncancel>def onCancel(chart): # WARNING: …</oncancel>
```

`onstart`/`onstop`/`oncancel` hold **tab-indented** Jython inline in the element text. The injected
`# WARNING: This resource was generated in a newer version of Ignition.` comment appears in **116 of
117** files, in both trees (95/95 PROD, 21/22 DEV). It is estate-normal, it is syntactically a Python
comment, and it is not a sign of corruption. Do not "clean it up". Do read it as a warning that SFC
round-tripping through `writeResource` is lossy: the 6 DEV `TFF_Parent` charts rewritten by actor
`mcp` on 2026-08-28 all came back with `lastModificationSignature: ""`.

## Webdev endpoints

`com.inductiveautomation.webdev/resources/<Name>/` holds `config.json` plus **all eight**
`do<Method>.py` files — `doGet, doPost, doPut, doDelete, doHead, doOptions, doTrace, doPatch` — even
when the verb is disabled (30 of each across both trees, against 39 webdev resources; the other 9 are
static assets with a different `resource-type`).

`config.json` gates each verb independently under `"resource-type": "python-resource"`:

```json
{
  "resource-type": "python-resource",
  "doGet":  {"enabled": true,  "max-retry-attempts": 3, "require-auth": false,
             "require-https": false, "required-roles": "", "user-source": ""},
  "doPost": {"enabled": false, "max-retry-attempts": 3, "require-auth": false, …}
}
```

Adding a POST handler means editing `doPost.py` **and** flipping `config.json.doPost.enabled` to
`true`. Editing only the `.py` leaves the endpoint returning 405 with no error anywhere.
`require-auth` defaults to `false` throughout the estate.

Return shapes (census over all `do*.py`: 23 `'json'`, 1 `'bytes'` + 1 `'contentType'`):

```python
return {'json': dataset}                                        # JSON body
return {'contentType': 'application/octet-stream',
        'bytes': file_bytes}                                    # binary body
```

Real examples: `.../TFF_Parent/com.inductiveautomation.webdev/resources/TFFReport/doGet.py` (reads
`request['params']['Site']` etc.) and `.../File_Transfer/…/resources/download/doGet.py` (bytes).
Binary static assets live at `resources/<Name.ext>/file.bin` — the folder carries the extension,
e.g. `Bayesian_Platform/.../resources/PE_loading.gif/file.bin` (GIF89a, 4421966 B).

## files[] semantics

`files[]` is a declaration, not an index, and the gateway is lenient in both directions:

| Situation | Behaviour | Real case |
|---|---|---|
| File on disk, not in `files[]` | Ignored, and preserved. Useful for sidecars. | DEV `FLEX01-R8-320-3-1/ignition/script-python/flex01/component_schemas.json` plus a `flow_templates/` subdir of 7 more JSONs — 3 undeclared files total across both trees |
| In `files[]`, missing on disk | Resource still loads. Silent. | 6 cases, all in DEV `FLEX01-R8-320-3-1`: `stylesheet.css`, 4 `thumbnail.png`, a vision `client-tags/data.bin` |
| Folder with payload but no `resource.json` | Not a resource; omitted from export | `TFF_Parent/.../views/Framework/` |
| Wrong filename declared | Resource reads the canonical name anyway, or nothing | `Martillac-Alarms/.../session-props` declares `session-props.json`, real payload is `props.json` |

## Validation checklist for anything you author

1. Payload filename matches the canonical name in the master table.
2. `resource.json` sits at the leaf folder, not the module folder.
3. Exactly the six top-level keys; `restricted: false`; `overridable: true`.
4. `scope` and `version` copied from a same-type sibling (`DG`/`2` for named queries, `A` for shared
   script libraries).
5. No `lastModificationSignature`. Any `lastModification` is inside `attributes` with an ISO-8601 Z
   timestamp.
6. `files[]` matches what is actually on disk.
7. For named queries: every `:param` in `query.sql` has a matching
   `{type, identifier, sqlType}` entry in `attributes.parameters` (259 of 315 `query.sql` use colon
   markers, 0 use `?`, 56 take no parameters).
8. For webdev: `config.json.<verb>.enabled` flipped alongside the `.py`.
