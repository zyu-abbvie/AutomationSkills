# Perspective view anatomy

The on-disk shape of `com.inductiveautomation.perspective/views/<Path>/<Name>/view.json` and its
siblings (`style.json`, `stylesheet.css`, `thumbnail.png`), measured against all 1197 view.json files
in the two gateway backups. Read this before hand-authoring or patching a view.

Path shorthand used throughout (both read-only):

```bash
DEV=$DEV
PROD=$PROD
```

## Get this wrong and nothing happens: bindings do not live next to the prop

A binding is **not** a member of `props`. It goes in a **sibling** `propConfig` map on the same
component node, keyed by the dotted path to the prop. Put a binding object inside `props` and
Perspective treats it as a static value: the view loads, the component renders, and the value never
updates. No error anywhere. Across all 1197 views there are 10423 bindings and **zero** cases of a
`binding` key inside a `props` object. The estate has never made this mistake; don't be first.

Real pair, both from
`$DEV/TFF_Parent/com.inductiveautomation.perspective/views/Page/Embedded/Title/view.json`.
Static text (`Label_10`) — value in `props`, no `propConfig` entry:

```json
{ "meta": { "name": "Label_10" },
  "props": { "text": "Email:", "textStyle": { "fontSize": 14 } },
  "type": "ia.display.label" }
```

Bound text (`Label`) — `props.text` is **absent from `props`**, and the binding sits under the dotted
key `"props.text"` in `propConfig`:

```json
{ "meta": { "hasDelegate": true, "name": "Label" },
  "position": { "basis": "200px", "grow": 1 },
  "propConfig": {
    "props.text": { "binding": { "config": { "path": "view.params.text" }, "type": "property" } } },
  "props": { "style": { "classes": "Title/Text" } },
  "type": "ia.display.label" }
```

Leaving a stale static value in `props` alongside a `propConfig` binding for the same path is legal —
the binding wins — but the file then lies about what the component shows. Remove it.

## view.json top-level keys

Exactly 7 keys exist. Four are always present, three optional.

| Key | Files (of 1197) | Notes |
|---|---|---|
| `custom` | 1197 | view-scoped custom props; `{}` is normal |
| `params` | 1197 | view input/output params; `{}` is normal |
| `props` | 1197 | view props, mainly `defaultSize` |
| `root` | 1197 | the single root component node |
| `propConfig` | 549 | **view-level** propConfig, for `params.*` / `custom.*` |
| `events` | 11 | view-level; all 11 use only the `system` category |
| `permissions` | 6 | e.g. `{"securityLevels": [], "type": "AllOf"}` |

`root.meta.name` must be the literal string `"root"` and `root.type` must be a container:
`ia.container.flex` 907, `ia.container.coord` 217, `ia.container.breakpt` 69, `ia.container.tab` 3,
`ia.container.column` 1.

The smallest valid view in the estate is 141 bytes —
`$PROD/DevSciLabs/com.inductiveautomation.perspective/views/Page/OvenTest/view.json`, verbatim:

```json
{
  "custom": {},
  "params": {},
  "props": {},
  "root": {
    "meta": {
      "name": "root"
    },
    "type": "ia.container.coord"
  }
}
```

Use that as the skeleton. The largest is 632042 bytes
(`$PROD/IRVINE_RD2_364-1_3CM/.../views/Page/EquipmentDisplay/view.json`) — never round-trip one that
size through a JSON library (see Gson escaping).

Gotcha: `$DEV/LF_Parent_2/com.inductiveautomation.perspective/views/` contains 8 **empty directories
named `view.json`** (`Page/Main/view.json/`, `Page/history/view.json/`, ...). Any tool doing
`glob('**/view.json')` and opening the results throws `IsADirectoryError`; filter with
`os.path.isfile`. That project is a half-written skeleton, not a working view set.

## Component node shape

Every component node — root included — is an object with:

| Field | Count | Meaning |
|---|---|---|
| `meta.name` | 20117 | required, unique among siblings; how `self.getSibling("X")` resolves |
| `type` | 20117 | `ia.display.label` 6232, `ia.container.flex` 4611, `ia.input.button` 1630, `ia.shapes.svg` 821, `ia.display.led-display` 736, `ia.input.text-field` 704 |
| `children` | containers | array of the same node shape, arbitrarily deep |
| `props` | optional | static prop values **only** |
| `propConfig` | optional | bindings + per-prop config, keyed by dotted path |
| `position` | optional | layout in the *parent's* system (`basis`/`grow`/`shrink` for flex; `x`/`y`/`width`/`height` for coord) |
| `events` | optional | see Events |

Other `meta` keys: `hasDelegate` 622, `visible` 242, `tooltip` 186, `contextMenu` 33.

`propConfig` keys are dotted paths rooted at one of five namespaces — `props.*` 8200, `params.*` 2219,
`meta.*` 1377, `custom.*` 813, `position.*` 265 — with array indices inline
(`props.items[0].style.fontWeight`, `props.series[0].data`). Each entry value may carry:

| Entry key | Count | Purpose |
|---|---|---|
| `binding` | 10423 | the binding object |
| `paramDirection` | 2219 | `input` / `output`; view-level `params.*` only |
| `persistent` | 1996 | `true` for params/custom that serialize with the view |
| `onChange` | 499 | `{"enabled": null, "script": "..."}` — Jython run when the value changes |
| `access` | 43 | prop access control |

## The 6 binding types

These are all of them; there is no seventh anywhere in the estate. The counts sum exactly to the
10423 `binding` entries above.

| `type` | Count | Required `config` |
|---|---|---|
| `expr` | 4691 | `expression` |
| `property` | 2979 | `path` |
| `tag` | 2216 | `tagPath`, `mode`, `fallbackDelay` |
| `query` | 262 | `queryPath` (bare named-query name), optional `parameters`, `returnFormat` |
| `tag-history` | 209 | `tags[]`, `dateRange`, `aggregate`, `returnFormat`, `returnSize` |
| `expr-struct` | 66 | `struct` (object of sub-expressions), `waitOnAll` |

Real config for each, copied from the backups:

```json
// expr      $DEV/LNP_opt/.../views/Header/Header/view.json  ->  "position.display"
{"config": {"expression": "{view.params.size} = \"small\""}, "type": "expr"}

// property  $DEV/LNP_opt/.../views/Docks/Menu Vertical/view.json  ->  "props.items[0].style.fontWeight"
{"config": {"path": "page.props.path"},
 "transforms": [{"expression": "if ({value} = {this.props.items[0].target}, \"bold\", \"normal\")",
                 "type": "expression"}], "type": "property"}

// tag       $DEV/PolarBear_Controller/.../views/Page/PolarBear/view.json  ->  "props.value"
{"config": {"fallbackDelay": 2.5, "mode": "direct", "publishInitial": false,
            "tagPath": "[MQTT Engine]LC/R8/133-4/polarbear/telemetry/tempPV"}, "type": "tag"}

// query     $DEV/Ruben-Test-App/.../views/ViewImages/view.json  ->  "props.source"
{"config": {"parameters": {"ID": "{this.custom.ID}"}, "queryPath": "GetImage",
            "returnFormat": "scalar"},
 "transforms": [{"code": "    import base64\n    ...", "type": "script"}], "type": "query"}

// tag-history  $DEV/PolarBear_Controller/.../views/Page/PolarBear/view.json  ->  "props.series[0].data"
{"config": {"aggregate": "MinMax", "avoidScanClassValidation": true, "enableValueCache": true,
            "dateRange": {"mostRecent": "1", "mostRecentUnits": "HOUR"},
            "ignoreBadQuality": false, "polling": {"enabled": true, "rate": "1"},
            "preventInterpolation": false, "returnFormat": "Wide",
            "returnSize": {"numRows": "100", "type": "FIXED"},
            "tags": [{"path": "[MQTT Engine]LC/R8/133-4/polarbear/telemetry/tempPV"}],
            "valueFormat": "DATASET"}, "type": "tag-history"}

// expr-struct  $DEV/LNP_opt/.../views/main/view.json  ->  "custom.SelectedFlowUnits"
{"config": {"struct": {"index": "{this.props.value}", "options": "{this.props.options}"},
            "waitOnAll": true},
 "transforms": [{"expression": "{value}['options'][{value}['index']]['label']",
                 "type": "expression"}], "type": "expr-struct"}
```

`query.config.queryPath` is a **bare** name — no project prefix, no leading slash. Top values:
`Get_Annotations` 75, `Get_BatchStatus` 42, `Get_AuditData` 42, `Get_RecipeValues` 28, `Get_Recipes`
14. The named query must exist in this project or its parent; a typo fails silently at runtime, never
at save. `parameters` keys must match the `:paramName` markers in that query's `query.sql`.

## Transforms

`binding.transforms` is an ordered array; each element has a `type` plus its own fields.

| `type` | Count | Shape |
|---|---|---|
| `script` | 660 | `{"code": "...Jython, indented as a function body..."}` |
| `expression` | 597 | `{"expression": "..."}` with `{value}` as the input |
| `format` | 122 | `{"formatType": "datetime", "formatValue": {"date": "medium", "time": "medium"}}` |
| `map` | 54 | `{"inputType": "scalar", "outputType": "scalar", "fallback": null, "mappings": [{"input": "Mode: 0", "output": "Stopped"}, ...]}` |

Real `map` at `$DEV/LNP_opt/.../views/main/view.json` (`props.text`); real `format` at
`$DEV/Ruben-Test-App/.../views/Dock/Camera/view.json`. Script bodies are Jython 2.7 in the gateway
JVM and the stored string **starts with whitespace** because it is a function body
(`"    import base64\n    if value:\n\t..."`). Mixed tab/4-space indent inside one body is common
here and works; do not introduce more of it.

## Indirect tag bindings: how one parent view serves 20 benches

The most important pattern in the estate. Of 2216 tag bindings, 1565 are `mode: "indirect"`, 516
`direct`, 29 `expression`, 106 omit `mode`. 1509 indirect ones carry a non-empty `references` map;
662 are `bidirectional: true`.

```json
{
  "config": {
    "bidirectional": true,
    "fallbackDelay": 2.5,
    "mode": "indirect",
    "references": {
      "1": "{session.custom.Building}",
      "2": "{session.custom.RoomFloorBench}"
    },
    "tagPath": "[default]{1}/{2}/TFF/CurrentEmail"
  },
  "type": "tag"
}
```

Verbatim from `$PROD/TFF_Parent/com.inductiveautomation.perspective/views/Page/Embedded/Title/view.json`,
component `Username` (`ia.input.text-field`), prop `props.text`. The mechanism end to end:

1. The parent project (`TFF_Parent`) owns the views. No tag path in them names a bench.
2. Each `{n}` in `tagPath` is substituted from `references["n"]`, which is itself an expression —
   almost always a `session.custom` prop.
3. Every child project overrides exactly
   `com.inductiveautomation.perspective/session-props/props.json` plus `page-config/config.json`
   (52/52 PROD children do). That props.json is the identity, e.g.
   `$DEV/TFF-F3-309-3-2/com.inductiveautomation.perspective/session-props/props.json`:
   `{"Building": "F3", "RoomFloorBench": "309-3-2", "Site": "LC", "ChartTime": 10, "Chiller": false, ...}`.
4. PROD `TFF_Parent` therefore drives 20 inheriting children from one view set. Editing
   `$PROD/TFF_Parent/.../views/Page/TFF_Full_Display/view.json` (124840 bytes, 67 bindings, 25
   indirect) touches 20 live instruments.

Reference-value census: `{session.custom.Building}` 1202, `{session.custom.RoomFloorBench}` 1200,
`{session.custom.Site}` 649, `{session.custom.Path}` 279, `{session.custom.EquipmentNum}` 167,
`{session.custom.PumpCubeNum}` 77, `{view.params.name}` 16.

Gotchas, all load-bearing:

- `mode` **must** be `"indirect"` for `{n}` to resolve. A `{1}` left in a `direct` tagPath binds to a
  literal tag named `{1}` — no error, permanently null.
- Reference keys are arbitrary strings, not required to be numbers.
  `$DEV/TSWG/.../views/Page/Menu/view.json` uses
  `"references": {"Building": "{session.custom.Building}", "RoomFloorBench": "..."}` with
  `"tagPath": "[default]{Building}/{RoomFloorBench}/TSWG/ExperimentName"`. Both styles work; match
  the file you are editing.
- 8 bindings have the reference value `"{session.custom.Site} "` — **trailing space**, which lands in
  the tag path. It is a bug; strip it if you touch those bindings.
- `references: {}` with a tagPath containing no `{n}` is a no-op indirect binding and is common
  (`$DEV/LNP_opt/.../views/main/view.json`). Harmless, but prefer `direct`.
- Adding a new `session.custom` key means adding it to the parent's props.json **and** to every child
  override that needs a non-default value. Children do not inherit keys they redeclare.

## Events

`events.<category>.<name>` on a component node, or `events.system.*` at view level. Three categories:
`dom` (raw browser), `component` (component-specific), `system` (lifecycle).

| Event | Count |
|---|---|
| `component.onActionPerformed` | 1411 |
| `dom.onClick` | 997 |
| `dom.onKeyUp` | 139 |
| `system.onStartup` | 132 |
| `component.onSelectionChange` | 49 |
| `dom.onDoubleClick` | 34 |
| `component.onEditCellCommit` | 21 |
| `component.onSubviewExpand` | 14 |

A handler is not always a script. Handler `type`: `script` 2537, `nav` 153, `dock` 94, `popup` 56.
`scope` is `G` (2534, all script handlers) or `C` (306, the declarative actions).

Real script handler — `$DEV/PolarBear_Controller/.../views/Page/PolarBear/view.json`, component
`apply_temp_btn` (`ia.input.button`), quoted with the exact `\u003d` / `\u0027` escaping the gateway
wrote (see Gson escaping below):

```json
"events": { "component": { "onActionPerformed": {
  "config": { "script": "    target \u003d self.getSibling(\u0027Set_temp_field\u0027).props.value\n    mode \u003d self.getSibling(\u0027ramp_q\u0027).props.value\n    if mode \u003d\u003d \u0027ramp\u0027:\n        ...\n        system.cirruslink.engine.publish(\u0027Chariot\u0027, \u0027LC/R8/133-4/polarbear/cmd/ramp\u0027, payload, 0, True)" },
  "scope": "G", "type": "script" } } }
```

Read as Jython that is `target = self.getSibling('Set_temp_field').props.value`, etc.

Declarative handlers, same wrapper, no Jython:

```json
{"config": {"page": "/"}, "scope": "C", "type": "nav"}
{"config": {"id": "menu", "type": "toggle"}, "scope": "C", "type": "dock"}
{"config": {"viewPath": "Page/PID_Faceplate", "id": "VlUvD91J", "type": "open",
            "title": "PID Control", "modal": false, "draggable": true,
            "positionType": "relative"}, "scope": "C", "type": "popup"}
```

(`$DEV/LNP_opt/.../views/Header/Header/view.json`;
`$DEV/TFF_Parent_Copy/.../views/Page/TFF_Full_Display/view.json`.) `popup.config.id` is an opaque
generated string — reuse the same id to close the popup you opened. `popup.config.viewPath` is the
view's resource path with no leading slash and no `views/` prefix. Guard `dom.onKeyUp` scripts on
`event.key` the way `$DEV/TSWG/.../views/Page/EquipmentDisplay/view.json` does (`if(event.key ==
"Enter"):`), or they fire on every keystroke.

Component custom methods and message handlers live in a separate `scripts` key on the node (15 views):
`{"customMethods": [], "extensionFunctions": null, "messageHandlers": [{"messageType": "refresh",
"pageScope": true, "sessionScope": true, "viewScope": false, "script": "\tself.refreshBinding('props.data')"}]}`
— `$DEV/PT/com.inductiveautomation.perspective/views/Page/history/view.json`.

## Style classes and the stylesheet resource

Two separate mechanisms. **style-classes** — 1467 `style.json` files at
`com.inductiveautomation.perspective/style-classes/<Group>/<Name>/style.json`, with exactly two
top-level keys: `base` (1467) and `variants` (153).

```json
{ "base": { "style": { "backgroundColor": "var(--neutral-20)", "color": "var(--neutral-80)",
                       "fontSize": "14px", "textTransform": "uppercase" } },
  "variants": [ { "pseudo": "last-child", "style": { "borderBottomWidth": "1px" } },
                { "pseudo": "hover", "style": { "backgroundColor": "var(--callToActionHighlight)" } } ] }
```

`$DEV/LNP_opt/com.inductiveautomation.perspective/style-classes/Menu/Item_Vertical/style.json`.
`base` can also hold non-`style` sub-objects — `base.animation.keyframes` in
`$DEV/TFF_Parent/com.inductiveautomation.perspective/style-classes/Header/Alarm_Active/style.json`.

A view references a class by its slash-separated resource path in `props.style.classes`:
`"Page/Text"` 1006 uses, `"Header/Icon"` 186. Multiple classes are **space**-separated in one string
(`"Header/Header Header/Icon"`, `"ia_pipe ia_pipeIsolate"`). 7984 nodes carry `"classes": ""`, which
is Designer noise, not a reference.

**stylesheet** — raw project CSS, a singleton resource. The only correct location:

```
<Project>/com.inductiveautomation.perspective/stylesheet/resource.json   # files: ["stylesheet.css"]
<Project>/com.inductiveautomation.perspective/stylesheet/stylesheet.css
```

There is exactly one in the estate,
`$PROD/RecipeManager/com.inductiveautomation.perspective/stylesheet/`, targeting DOM ids directly
(`#reactorContainer { border: 2px solid #4caf50; ... }`).

Defect to recognize and not copy: `$DEV/FLEX01-R8-320-3-1/com.inductiveautomation.perspective/resource.json`
is a `resource.json` at the **module** level — not inside a `stylesheet/` folder — declaring
`"files": ["stylesheet.css"]`, actor `mcp`, signature `""`, and the CSS file does not exist on disk.
It loads nothing and reports nothing. The same project declares a `thumbnail.png` in 4 more
`resource.json` files that are also absent. A `resource.json` must sit at the leaf folder for its
resource, and `files[]` must match disk.

## Gson HTML-safe escaping: leave it alone

The Designer and Gateway serialize with Gson's HTML-safe escaping on, so script strings and
expressions store as:

| Char | Stored in the JSON as | Occurrences (all JSON, both trees) |
|---|---|---|
| `=` | `\u003d` | 39029 |
| `'` | `\u0027` | 33996 |
| `>` | `\u003e` | 3757 |
| `<` | `\u003c` | 2895 |
| `&` | `\u0026` | 231 |

683 of 1197 view.json contain these; 800 of 7003 JSON files estate-wide. This is correct,
gateway-native output. It is not corruption and it is not yours to normalize.

Consequence: `json.load()` then `json.dump()` on a view.json un-escapes every one of these and
reflows the whole file, turning a one-prop change into a multi-thousand-line diff that hides whatever
you actually did. Read with `json.load` to *inspect*; make changes as surgical text edits against the
exact stored bytes, or accept the churn deliberately and say so. Python's `json.dump` cannot
reproduce Gson's escaping — there is no flag for it.

## thumbnail.png

Binary PNG preview generated by the Designer. 1174 of 1197 view `resource.json` list
`["view.json", "thumbnail.png"]`; the other 23 list `["view.json"]` only and work fine
(`$DEV/Glebs Pager/com.inductiveautomation.perspective/views/Embedded/Header/`,
`$DEV/LargeScaleFC/.../views/Embedded/ConfirmMarkComplete/`).

Authoring a view programmatically: omit `thumbnail.png` from disk **and** from `files[]`. Never
fabricate one, never open one expecting text. Declaring it without creating it is the FLEX01 mistake
above — loading still works, but `files[]` becomes a lie and defeats later validation.

## Reviewing a view: what silently breaks

Nothing below produces an error. Each produces a view that renders and is wrong.

| Check | Failure if wrong |
|---|---|
| Every binding under `propConfig["<dotted.path>"].binding`, never inside `props` | prop frozen at its static value |
| `root.meta.name == "root"`, `root.type` is an `ia.container.*` | view fails to lay out |
| Indirect tag bindings have `"mode": "indirect"` | `{1}` binds to a literal tag named `{1}`, always null |
| Every `{n}` in `tagPath` has a matching `references` key | that path segment resolves empty |
| No leading/trailing whitespace in `references` values | space injected into the tag path |
| `queryPath` names a query in this project or its parent | binding returns null forever |
| `query.config.parameters` keys match the `:markers` in `query.sql` | runtime failure, not save-time |
| `meta.name` unique among siblings | `self.getSibling("X")` returns the wrong node |
| `props.style.classes` values exist under `style-classes/` (slash path, space-separated) | styling silently absent |
| Script transform / event `config.script` indented as a function body | fails only at first evaluation |
| `paramDirection` set on every view-level `params.*` in `propConfig` | param not writable from the parent |
| `files[]` matches disk; `resource.json` at the leaf, not the module level | undeclared files ignored, missing ones skipped |
| No stale static value in `props` for a path that now has a binding | file misrepresents runtime behaviour |
| Gson `\u003d` / `\u0027` escapes preserved, file not reflowed | unreviewable diff |
| For a `*_Parent` view: child count known before saving | PROD `TFF_Parent` = 20 live instruments |
