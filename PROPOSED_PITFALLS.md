# Proposed entries for `dbo.MCP_Pitfalls`

Five findings from building the `automation-engineering` plugin on 2026-08-28. Each was proven with a
**control that behaved differently**, which is what `addPitfall` requires and rejects entries without.

**I could not submit these myself.** `POST /data/mcp/MCP_Tools` requires the `Authenticated` security
level and returns 403 anonymously; there is no API token available to this session. Submit them with
an authenticated MCP session, or hand them to someone with Designer access. They will land as
`status: "proposed"` until a human promotes them.

Entry 3 contradicts a rule currently stated in the gateway's own
`data/projects/CLAUDE.md`, so it is the one most worth a second opinion before promoting.

---

## 1. Unknown query parameter returns zero rows with HTTP 200

- **category** `silent-failure`
- **symptom** `List endpoint returns zero rows although the data exists`
- **cause** Ignition 8.3 list endpoints treat an unrecognised query parameter as an implicit field
  filter rather than rejecting it, so a typo produces an empty result set at HTTP 200 with no error.
- **fix** Send only parameter names the endpoint declares in `/openapi.json`. The tell is
  `metadata.matching == 0` while `metadata.total` stays at the real row count. With a *valid* filter
  that matches nothing, `total` drops to 0 as well — so a large `total` alongside `matching: 0` is
  specifically the misspelled-parameter case. The `filter` parameter is the common victim: it must be
  sent as a bare `fieldName[op]=value` parameter, not as `filter=fieldName[op]=value`.
- **evidence** On wa03593d 8.3.7: `GET /data/api/v1/logs?limit=1` returned 1 item with
  `total 54331, matching 54331`. The same request plus `&zzzBogus=1` returned 0 items with
  `total 54331, matching 0` — same total, no error, HTTP 200 both times. Reproduced on a second
  endpoint: `GET /data/api/v1/projects/names` returned 40 items, and `?zzzBogus=1` returned 0 with
  `total 40`. Control: `?logger=__nosuchlogger__` (a *declared* parameter matching nothing) returned
  0 items with `total 0`, proving the two cases are distinguishable by `total`.
- **keywords** `api,query parameter,matching,metadata,silent,empty,filter,8.3`
- **project** `MCP_Tools`

## 2. Node-RED `mqtt out` with an empty topic creates `undefined…` orphan tag trees

- **category** `silent-failure`
- **symptom** `MQTT Engine creates a tag folder literally named undefined`
- **cause** An `mqtt out` node with a blank `topic` publishes to whatever `msg.topic` an upstream
  function set. Those functions build the topic by string concatenation from
  `flow`/`global`/`msg` properties; when one is `undefined`, JavaScript concatenates the text
  `"undefined"` instead of failing. Because the MQTT Engine custom namespace `NonSparkplugTags`
  subscribes to the bare wildcard `#`, Ignition then auto-creates a tag tree under that bogus root.
- **fix** Set the topic on the `mqtt out` node wherever it is static. Where it must be dynamic,
  validate before publishing — reject the message if any component is falsy rather than concatenating
  it. Existing orphan roots should be deleted from the tag tree after the flow is fixed.
- **evidence** In `doc/backup_nodered/LC_R8_320-3-1_TFF` (latest backup), 2 of 30 `mqtt out` nodes
  have `topic: ""` (on tabs `Scilog` and `Feed Balance`). Independently, subscribing to `#` on the dev
  broker showed a live retained topic literally named `undefinedGlebsMood`, and the prod MQTT Engine
  tag tree carries 17+ such roots including `undefinedHMI_COM/TCU1/FB-01 (On)`, `undefinedSERIAL/…`,
  `undefinedHeartbeat` and `undefinedAPI`. Control: the 28 `mqtt out` nodes in the same flow that
  carry an explicit topic produced correctly-rooted topics such as
  `LC/R8/320-3-1/TFF/SERIAL/WT-01 (Source Weight)` in the same broker capture.
- **keywords** `node-red,mqtt out,topic,undefined,orphan tag,mqtt engine,custom namespace`
- **project** *(estate-wide — Node-RED / groov RIO)*

## 3. `lastModificationSignature` is not a content hash

- **category** `standard`
- **symptom** `Resource change is not detected although resource.json signature was updated`
- **cause** `attributes.lastModificationSignature` is widely assumed to be a hash of the payload the
  Gateway uses to detect drift. It is not. It does not track payload content, it is optional, and the
  Gateway recomputes it on export or save.
- **fix** When writing a resource programmatically, **omit** `lastModificationSignature` — write
  `"attributes": {}` — rather than inventing or copying one. Do not use it to detect drift between two
  copies of a project; compare the payload files instead. Do not use it as a cache key.
- **evidence** Across both gateway backups: of 3830 `resource.json` files, 68 omit the key entirely
  and 33 carry `""`, and those projects are live and enabled. Two resources with byte-different
  payloads share an identical signature — `PT` and `PT_Opt`
  `com.inductiveautomation.perspective/views/Page/history/`: `resource.json` md5 identical
  (`19a45b0a3233f2947574e0dd987a3b78`) while `view.json` differs
  (`f2fc2c7c…` 68589 bytes vs `1a8a998b…` 77789 bytes). Conversely, of 1320 distinct payload hashes,
  165 map to more than one signature. Control: the Gateway's own export regenerates the value — a
  backup resource with signature `""` came back from
  `GET /data/api/v1/projects/export/TFF_Parent` populated with a real hash, and payload files were
  byte-identical across that boundary.
- **keywords** `resource.json,lastModificationSignature,drift,export,hash,authoring`
- **project** *(estate-wide)*

## 4. Payload filename is fixed by resource type, so renaming it in `files[]` silently breaks the resource

- **category** `silent-failure`
- **symptom** `Perspective session properties have no effect after import`
- **cause** Each resource type reads one fixed payload filename — `session-props` reads `props.json`,
  views read `view.json`, named queries read `query.sql`. Listing a different name in
  `resource.json` `files[]` does not redirect the Gateway to it; the resource simply loads with no
  content and no error.
- **fix** Use the filename the type mandates and declare exactly that in `files[]`. A file present on
  disk but absent from `files[]` is ignored; a `files[]` entry with no file on disk does not stop the
  resource loading. A resource folder with no `resource.json` at all is not a resource.
- **evidence** `Martillac-Alarms/com.inductiveautomation.perspective/session-props/resource.json`
  declares `files: ["session-props.json"]` (actor `Claude`) and the directory contains **both**
  `session-props.json` and the real `props.json`. Control: all 52 production child projects declare
  `files: ["props.json"]` for the same resource type and their session custom properties resolve —
  which is what the indirect tag bindings in those projects depend on.
- **keywords** `resource.json,files,props.json,session-props,payload filename,import,silent`
- **project** `Martillac-Alarms`

## 5. A per-device API key is published to MQTT retained, in cleartext

- **category** `dead-end`
- **symptom** `Device API key is readable by any client connected to the broker`
- **cause** A Node-RED `function` node assigns a 32-character key literal to `msg.payload` and
  publishes it to the device's `…/API` topic with `retain: true`. Retained means the broker replays it
  to every new subscriber indefinitely, and the same literal is stored unencrypted in every device
  backup zip.
- **fix** Do not publish credentials over MQTT. If Ignition needs the key, put it in a Gateway secret
  provider or a Named Query against a protected table. Clear the retained message by publishing an
  empty retained payload to the same topic, then rotate every affected key. Note that clearing the
  retained copy does not undo prior exposure.
- **evidence** Of the 17 groov RIO device backups whose `node-red/flows.json` could be read from a
  top-level zip, **all 17** contain a function node (named `API`, `API KEY` or `function 4`) that
  assigns a 32-character opaque literal to `msg.payload` and wires it to an `mqtt out` on the
  device's `…/API` topic — for example `ABC/B5/2071-2-1/TFF/API`, `AWA/B830/3S047-3-A/TFF/API`,
  `LC/F3/309-3-1/TFF/API`. The 17 values are distinct per device (compared by SHA-256 prefix; values
  not recorded here deliberately). Control: no other `mqtt out` topic on those devices carries a
  high-entropy literal — every other publish carries a numeric or boolean process value — so this is
  a specific pattern, not an artefact of the detection.
- **keywords** `node-red,mqtt,retained,api key,credential,secret,groov rio,security`
- **project** *(estate-wide — Node-RED / groov RIO)*

> **Two related exposures found alongside this one**, worth raising with whoever owns the RIO fleet
> rather than filing as pitfalls, because they are not mistakes an engineer can avoid by knowing
> better — they are standing conditions:
>
> - `node-red/flows_cred.json` is **not encrypted** in any of the 17 backups. Node-RED encrypts that
>   file with a key in `settings.js`; `settings.js` is absent from these backups and the credential
>   files are plain `{nodeId: {user, password}}` / `{nodeId: {apiKey}}`.
> - `doc/backup_nodered/Backup Tool/get.py` and `getchron.py` hardcode nine devices' groov Manage
>   API keys in cleartext.
>
> No values from either were read or reproduced.

---

### Submitting

Each entry maps directly onto `addPitfall` arguments. `evidence` must survive the tool's 20-character
minimum (all do) and deduplication is on the exact `symptom` string — if one already exists, the call
returns `action: "duplicate"` and increments `occurrences`, which is a useful result rather than a
failure. Check `ok` in the response: these tools report errors **in-band** inside a normal-looking
success envelope.
