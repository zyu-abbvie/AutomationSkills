# The Ignition 8.3 HTTP API

The working contract for driving the DEV gateway (`http://wa03593d:8088`, Ignition 8.3.7) over
`/data/api/v1`. Covers auth, the resources CRUD grammar, the read/write envelopes, the six ways this
API fails silently at HTTP 200, and what it cannot do at all.

## Auth: reads are open, writes are 401 with no body

| Call | Result with no credentials | Notes |
|---|---|---|
| Any `GET` under `/data/api/v1/**` on DEV | `200` | Includes `find/`, `list/`, `backup`, `projects/export/{name}` |
| Any `POST`/`PUT`/`DELETE` on a real route | `401`, **`Content-Length: 0`** | No JSON body at all |
| Same verb on a bogus `{module}/{type}` | `404` | Route resolution runs *before* auth |
| `POST /data/mcp/MCP_Tools` (correct Accept) | `403` + `{"message":"Forbidden",...}` | JSON body, unlike the 401 |
| `POST /data/mcp/MCP_Tools` (no Accept header) | `406` | Malformed transport, not an auth failure |
| Anything `/data/api/v1/*` on PROD `wz02163d` | `404` | 8.1.28 has no REST API |

1. **Never `json.loads()` a 401.** It is zero bytes. Branch on status first.
2. **404-vs-401 on a write is a free route spell-checker.** `PUT /resources/ignition/zzz-nosuchtype`
   → `404`; `DELETE /resources/ignition/database-connection/NoSuch/deadbeef` → `401`. A 404 means your
   `module/type` string is wrong; a 401 means the path is right and only the token is missing.
3. **The OpenAPI spec cannot tell you how to authenticate.** `GET /openapi.json` (14.7 MB, OpenAPI
   3.1.0, 740 paths / 860 operations, 549 of them under `/resources`) has no `servers` block, and
   `components` contains only `schemas` — zero `securitySchemes`, zero `security`. Any generated
   client will emit unauthenticated requests. The write credential for this gateway is out-of-band.

The only probe that answers on both versions is `GET /system/gwinfo` (plain text, semicolon-delimited):
DEV returns `ContextStatus=RUNNING;PlatformName=Ignition-WA03593D;Version=8.3.7;…`, PROD returns
`…PlatformName=Ignition-WZ02163D;Version=8.1.28;…`. Gate every script on
`GET /data/api/v1/gateway-info` (DEV: `{"ignitionVersion":"8.3.7 (b2026060908)","edition":"standard",
"jvmVersion":"17.0.18",…}`) and abort if it 404s. Pointing resources-API calls at PROD is harmless —
it cannot mutate anything — but none of this workflow exists there; PROD changes go through the
Designer.

## Resource identity and the CRUD grammar

A resource is the triple **(module, type, name)**. `module` is `ignition` (39 platform types) or a
reverse-DNS module id (`com.inductiveautomation.perspective`, `com.inductiveautomation.opcua`,
`com.inductiveautomation.historian`, `com.cirruslink.mqtt.engine.gateway`, …). There are 77 types:
57 **named** and 20 **singleton**. All 12 route shapes:

| Route | Verb | Count | Returns |
|---|---|---|---|
| `resources/names/{mod}/{type}` | GET | 57 | `{items:[{name,enabled,modes[]}], metadata}` — cheapest listing |
| `resources/list/{mod}/{type}` | GET | 57 | `{items:[full envelope], metadata}` |
| `resources/find/{mod}/{type}/{name}` | GET | 57 | one full envelope; `404` (HTML) if absent |
| `resources/singleton/{mod}/{type}` | GET | 20 | one full envelope, **no `name` key** |
| `resources/type/{mod}/{type}` | GET | 77 | schema/discovery (see below) |
| `resources/datafile/{mod}/{type}/{name}/{file}` | GET/PUT/DELETE | 14 paths | raw bytes, real Content-Type; only `opcua/device`, `perspective/{fonts,icons,themes}`, `ignition/{database-driver,service-connector,translations}` |
| `resources/{mod}/{type}` | POST | 76 | create — body is a JSON **array** |
| `resources/{mod}/{type}` | PUT | 76 | update — array, each item needs `signature` |
| `resources/{mod}/{type}/{name}/{signature}` | DELETE | 57 | named delete; `?collection=`, `?confirm=` |
| `resources/{mod}/{type}/{signature}` | DELETE | 20 | **singleton delete — no name segment** |
| `resources/delete/{mod}/{type}` | POST | 57 | bulk; body `[{name,signature,collection}]`, `?confirm=` |
| `resources/rename/{mod}/{type}/{name}` | POST | 55 | body `{name:<new>, references:…}` |
| `resources/copy` / `resources/move` | POST | 1 each | **collection-less paths**, everything in query params |

`copy` takes `?resourceType=&signature=` (both required) plus `fromName,toName,fromCollection,toCollection`;
`move` takes `?resourceType=&signature=&toCollection=` (required) plus `fromName,fromCollection`.
`resourceType` is the `"{module}/{type}"` string. They exist for cross-collection promotion; DEV has
exactly one collection (`core`; `GET /mode` returns zero deployment modes), so they are unexercised
here. There is no `resources/copy/{module}/{type}`, and no `resources/{mod}/{type}/{name}/{filename}` —
the `datafile` segment is mandatory (tested: 404).

## Call `type/` before you author anything

`GET /data/api/v1/resources/type/{module}/{type}` returns `{module, typeId, total, overrides,
singleton, allowDisableOnRestore, extensionPoint, extensionPoints[], defaultConfig, metrics,
healthchecks}` — the valid `typeId` enum, a ready-to-use settings skeleton, and the `singleton` flag
that tells you which DELETE shape to use.

```
$ curl -s .../resources/type/com.inductiveautomation.opcua/device
{"module":"com.inductiveautomation.opcua","typeId":"device","singleton":false,"extensionPoint":true,
 "extensionPoints":[{"typeId":"ModbusTcp","label":"Modbus TCP","canCreate":true,
   "defaultSettings":{"connectivity":{"hostname":"","port":502,"communicationTimeout":2000},
     "advanced":{"zeroBasedAddressing":false,"reverseWordOrder":false,"maxRetryCount":1}, ...}}, ...]}
```
28 driver typeIds for `device`; 9 for `historian-provider` (`CoreHistorian … WideDbHistorian`).

**Extension-point config is two-part and has no discriminator.** For these types
`config = {profile:{type:<typeId>, …}, settings:{…}}` and the spec models `settings` as a bare
`oneOf` whose branches carry `$id: "{module}/{type}/{typeId}"` with **no OpenAPI `discriminator`**.
Schema-driven codegen will pick the wrong branch — hand-select the one whose `$id` ends in your
`profile.type`. Non-extension-point types put fields directly in `config` (`database-connection` has
`config.driver`, `config.connectURL` at the top level). Whether a mismatched `profile.type`/`settings`
pair is rejected with 422 or silently half-applied is **unverified**; assume it is dangerous.

For "what exists on this gateway", one anonymous `GET /data/api/v1/entity/browse` returns all 82
configuration entity types with `resourceType`, `singleton`/`extensionPoint` flags, live metrics and
healthchecks — it replaces 77 `type/` calls. (`GET /entity/section/configuration` returns `[]`; valid
section names are unknown.)

## The read envelope

`find/`, `list/` items and `singleton/` all return the same envelope:

| Key | Always present? | Notes |
|---|---|---|
| `type` | yes | `"{module}/{type}"` |
| `name` | named types only | absent on all 20 singletons (31 of 51 sampled reads had it) |
| `description`, `enabled`, `version` | yes | |
| `collection`, `collections[]` | yes | `"core"` / `["core"]` on DEV |
| `signature` | yes | 64 hex chars — the value you echo on a write |
| `config` | yes | the authoring payload |
| `backupConfig` | **no — 5 of 51** | the 14th key; `com.cirruslink.mqtt.engine.gateway/server` has it, `ignition/database-connection` does not |
| `data[]` | yes | datafile filenames, e.g. `["config.json"]` |
| `attributes` | key present, contents vary | see below |
| `metrics`, `healthchecks` | yes (live) | **not in the spec's response schema**, like `names/`'s `modes[]` — do not validate responses against the spec |

### `attributes` has no fixed shape — always `.get()`, never index

Sampled live across all 51 types that have at least one instance (31 named + 20 singletons):
`lastModification` (`{actor,timestamp}`) and `lastModificationSignature` in **38/51**, `uuid` in
**24/51**, `enabled` in **19/51**, and `attributes == {}` for **7/51** —
`com.inductiveautomation.perspective/{fonts,icons,themes}`,
`com.inductiveautomation.sip-notification/script-settings`,
`ignition/{database-driver,schedule,security-zone}`. Some types add their own keys:
`ignition/translations` returns `caseInsensitive`, `ignorePunctuation`, `ignoreTags`,
`ignoreWhitespace`. `r["attributes"]["uuid"]` KeyErrors on 27 of 51 types. And note top-level
`signature` and `attributes.lastModificationSignature` are **different values**.

### find/ and list/ hand out secrets anonymously

`ignition/database-connection` returns `config.password` as a JWE blob
`{"type":"Embedded","data":{protected,encrypted_key,iv,ciphertext,tag}}`; `ignition/api-token` returns
`config.settings.tokenHash` in cleartext. Never paste raw `find/`/`list/` output into a chat log, a
commit, or a pitfall record. The spec annotates every field with `x-ignition-non-secret: true|false` —
use that as the machine-readable redaction rule. To PUT a resource back unchanged, echo the
`Embedded` blob verbatim; you never need the plaintext.

## The write body contract

`POST` and `PUT /data/api/v1/resources/{module}/{type}` take a **JSON array of envelopes** (batch
write). Sending a bare object is `400 Invalid request body`.

| | Item properties | Required |
|---|---|---|
| POST (create) | `name, collection, enabled, description, config, backupConfig` | `name` |
| PUT (update) | the same **plus `signature`** | `name, signature` |

**The 20 singleton types have no `name` property at all**, and their DELETE path omits the name
segment:

- `ignition/`: `cobranding`, `edge-system-properties`, `gateway-network-proxy-rules`,
  `gateway-network-queue-settings`, `gateway-network-settings`, `general-alarm-settings`,
  `local-system-properties`, `quickstart`, `security-levels`, `security-properties`,
  `system-properties`, `translations`
- MQTT: `com.cirruslink.mqtt.engine.gateway/{general,namespace-file}`,
  `com.cirruslink.mqtt.transmission.gateway/general`
- `com.inductiveautomation.`: `eam/event-thresholds`, `eam/module-settings`, `opcua/access-control`,
  `opcua/server-config`, `sfc/chart-settings`

`?allowInvalidReferences=` (default `false`) exists on only **33 of the 76** collection write
endpoints. It *is* available on `ignition/database-connection`, `ignition/tag-provider`,
`ignition/opc-connection`, `com.inductiveautomation.opcua/device`,
`com.inductiveautomation.historian/historian-provider` and the MQTT `server`/`transmitter` types.
It is **absent** on `ignition/api-token`, `ignition/secret-provider`, `ignition/security-zone`,
`ignition/store-and-forward-engine`, `ignition/service-connector`,
`com.inductiveautomation.mcp/server-config`, `com.inductiveautomation.perspective/{themes,icons,fonts}`,
MQTT Engine `{server-set, custom-namespace, default-namespace, cert-file, general}` and MQTT
Transmission `{server-set, record, history-store, file}`. Sending it there is not an override — it is
an unrecognised param and your invalid reference simply fails.

The safe round-trip: `GET find/` → keep only `{name, signature, config}` (drop `type`, `version`,
`collections`, `data`, `attributes`, `metrics`, `healthchecks`) → wrap in a one-element array → `PUT`
→ read `changes[0].newSignature` from the response for your next write.

## HTTP 200 does not mean the write worked

```json
{"success": true,
 "changes": [{"name":"SQLServer","type":"ignition/database-connection","collection":"core",
              "newSignature":"<64 hex>"}],
 "problem": {"message":"...","stacktrace":["..."]}}
```

`success` and `problem` live *inside* the 200 schema. Always read `body.success`, and always harvest
`changes[].newSignature` — that is the signature required for your **next** write to the same
resource. Other statuses: `422` = validation, with `problem.messages[]` and
`problem.fieldMessages[{fieldName,messages[]}]`; `409` = conflict (POST only); `500` = `problem.message`
plus `problem.stacktrace[]`.

## Signatures (optimistic concurrency)

`signature` is a 64-hex-char value on every read, stable across reads and across views:
`ignition/tag-provider/default` returned `1b30fdb52389a1c5071bdbf6be61abdadf465a652e5d0f0c3e0986785c21ad39`
on repeated calls hours apart, and `list/` and `find/` agree. Re-read immediately before a write; do
not cache signatures across a session, since any other actor's write invalidates them.

**The placement is inconsistent.** On the resource DELETE the signature is a **path segment**
(`DELETE /resources/ignition/database-connection/{name}/{signature}`). On the datafile routes it is a
**required query param** (`PUT /resources/datafile/com.inductiveautomation.perspective/themes/{name}/{filename}?signature=…`).
A helper that always appends it as a path segment will 404 on datafile writes and vice versa. The
signature guarding a datafile is the parent *resource's* signature.

What a signature **mismatch** returns (409? 412? 422?) is unverified — auth is enforced first, so
anonymously you always get 401 and can never distinguish a stale signature from a missing token.

## Silent failures: HTTP 200, no data, no error

Every one of these returns `200`. `metadata.total` is the unfiltered count and `metadata.matching`
is the filtered count — **`total` real while `matching` is 0 is the universal tell.**

| Mistake | Reproduction | Result |
|---|---|---|
| `filter` sent as a named param | `names/ignition/tag-provider?filter=name%5Bsw%5D=MQTT` | `items:[]`, `total:4`, `matching:0` |
| correct form | `names/ignition/tag-provider?name%5Bsw%5D=MQTT` | 2 items, `matching:2` |
| any unrecognised query param | `names/ignition/tag-provider?bogusParam=xyz` | `items:[]`, `total:4`, `matching:0` |
| `tags/export&recursive=false` at root | `tags/export?provider=default&type=json&recursive=false` | `{"name":"","tagType":"Provider"}` — 30 bytes |
| correct form | same URL without `recursive` (defaults true) | 702,175 bytes, 1,772 tags |
| `logger=` treated as a prefix | `logs?logger=martillac` | `total:0` |
| correct form (exact match) | `logs?logger=martillac.autoheal` | `matching:18224` |
| `search=` treated as AND | `logs?search=martillac%20zzznotaword` | `matching:21408` — same as `martillac` alone |

A typo'd param name and a wrongly-named `filter` are the *same* bug: unrecognised query params are
interpreted as filter keys, and an unparseable filter key matches nothing. Valid ops are
`eq, ne, cn, sw, ew, gt, gte, lt, lte, rgx`; `sortBy=desc(name)`, `limit`, `offset` and `search` work
as documented. To scope a tag export use `path=`, never `recursive=false`. `tags/export` **requires
both** `provider` and `type` — omit either and you get a hard `400`, not a default.

The `logs` route has the opposite trap: **its default `limit` is `-1`, meaning unlimited** — a bare
`GET /data/api/v1/logs` returns all **54,484** entries in one response. Always pass `limit`
(`limit=0` gives `metadata` only). It supports `minLevel` (`TRACE…OFF`), `startTime`/`endTime` in
epoch millis, `properties`, `allowedMarkers`, and `loggerName[sw]=` for prefix matching; items are
`{timestamp, loggerName, level, message, mdc, stack[]}`. `logs?minLevel=ERROR&startTime=…&limit=50`
is the first call to make when a project misbehaves. `logs/loggers` reports 1,831 loggers.

## Error bodies are not always JSON

| Status | Content-Type | Body |
|---|---|---|
| `401` (writes) | — | empty, `Content-Length: 0` |
| `404` (resource read, bad `?collection=`) | `text/html;charset=iso-8859-1` | Jetty HTML page, 464 bytes |
| `403` (MCP) | `application/json` | `{"message":"Forbidden","url":…,"status":"403"}` |
| `200`, `422`, `500` | `application/json` | documented shapes |

## What this API cannot do

| Not available | Use instead |
|---|---|
| Tag **value** read/write/browse — zero routes in all 860 operations | MCP server (`POST /data/mcp/MCP_Tools`) or a WebDev endpoint calling `system.tag.readBlocking`/`writeBlocking` |
| Perspective views, gateway/timer/tag-change scripts, named queries, UDT definitions, transaction groups, alarm pipeline editing — no project-resource routes at all | scan-lock → edit the project filesystem → `scan/projects`, or export/modify/import the zip |
| Tag config editing per-tag | `GET tags/export` / `POST tags/import` (whole subtree), or `ignition/tag-provider` resource CRUD for the provider itself |

The only tag-adjacent routes are `tags/export`, `tags/import`, `ignition/tag-provider` CRUD,
`PUT /managed-tag-provider` (toggles the Tag Reference Store property only) and
`GET /gateway-network/remote-tag-providers/{serverId}`. The alarm-notification, reporting, sfc,
event-stream and fsql module routes are runtime **status** plus cancel/pause/resume, not editing. Any
skill that promises "read a tag over REST" is wrong. Providers on DEV: `default` (1,772 tags),
`MQTT Engine`, `MQTT Transmission`, `System`.

## Project export: the zero-auth snapshot primitive

`GET /data/api/v1/projects/export/{name}` works anonymously and streams
`application/zip;charset=utf-8` (`Content-Disposition: attachment; filename="MCP_Tools_20260828154541.zip"`).
It is **byte-stable**: three consecutive exports of `MCP_Tools` gave identical md5 `5906b5bc…`,
80,031 bytes, 95 entries. The entry list is exactly the on-disk tree — 95 zip entries against 95 files
under `/home/admin/src/Automation_Skills2/doc/Ignition-WA03593D_Ignition-backup-20260828-1312/projects/MCP_Tools/`,
same relative paths, including the stale nested `MCP_Tools/MCP_Tools/…` subtree that project carries.

Take an export before every change — the cheapest rollback point available.
`GET /data/api/v1/backup` likewise streams a full `.gwbk` anonymously (that is how the backup dir
above was almost certainly produced); the anonymous-read posture on both is worth raising with the
gateway owner.

**Diff exports semantically, not textually.** Against the 13:12 backup, 83 of 95 files were
byte-identical (all `.py`, all `data.bin`) and all 12 differences were `resource.json` — real drift in
`attributes.actor/timestamp/lastModificationSignature`. But `resource.json` key order and trailing
whitespace also vary by writer (the gateway emits `scope` first with no trailing spaces; the MCP
`writeResource` tool and external editors leave trailing spaces and a different key order), so parse
the JSON and compare objects or you will chase phantom diffs.

## Project management routes

| Route | Verb | Body / params |
|---|---|---|
| `projects` | POST | `{name,description,title,enabled,parent,inheritable,…}` |
| `projects/copy` | POST | `{fromName,toName}` |
| `projects/rename/{name}` | POST | `{name:<new>}` |
| `projects/{name}` | PUT | `description,title,enabled,parent,inheritable,userSource,identityProvider,tagProvider` |
| `projects/{name}?confirm=true` | DELETE | without `confirm=true` it returns 200 and deletes nothing |
| `projects/export/{name}` | GET | zip stream, anonymous |
| `projects/import/{name}?overwrite=true` | POST | **`Content-Type: application/zip`**, not multipart — 415 otherwise |
| `projects/{names,list,find/{name},parents}` | GET | inventory |

Project objects have **no `signature`** (`find/MCP_Tools` →
`{"name":"MCP_Tools","enabled":true,"parent":"","inheritable":false,"mutable":true,"userSource":"default","tagProvider":"default","defaultDb":"testdb",…}`).
There is no optimistic-concurrency protection on `PUT /projects/{name}`: last write wins.

## Scan and scan-lock: picking up hand edits

| Route | Verb | Behaviour |
|---|---|---|
| `scan/{config,projects}` | GET | `{scanActive, lastScanTimestamp, lastScanDuration}` |
| `scan/{config,projects}` | POST | triggers a filesystem scan **and releases the scan lock** |
| `scan-lock/{config,projects}` | GET | `204` when no lock held; `200` + lock info when held |
| `scan-lock/{config,projects}` | POST | body `{acquireTimeout:10, holdTimeout:60}` (seconds); `200` acquired / `408` timeout / `409` already held / `400` bad body |

The spec is explicit: "While this lock is held, any other changes will be queued (block) until the
lock is released. While locked, it is safe to make external changes to the filesystem." So the
sequence for editing project or config files on disk is: `POST scan-lock/projects` with a
`holdTimeout` long enough for the edit → edit files → `POST scan/projects`, which both applies the
changes and releases the lock. Skipping the lock risks the gateway reading a half-written file. Both
POSTs require credentials.

## Writes that can damage the estate — require explicit human confirmation

Guard on **method + path**, never path alone: `GET /data/api/v1/backup` is a harmless snapshot while
`POST /data/api/v1/backup` is *Restore Gateway Backup* and overwrites the whole gateway.

| Call | Damage |
|---|---|
| `POST /backup` | restores a gwbk over the entire gateway |
| `POST /restart-tasks/restart` | restarts the gateway |
| `DELETE /projects/{name}?confirm=true` | destroys a project |
| `POST /projects/import/{name}?overwrite=true` | replaces project content |
| `POST /tags/import` with `collisionPolicy=Overwrite` | wipes tag configs |
| `POST /modules/install`, `DELETE /modules/uninstall`, `PUT /modules/toggle-state` | module state |
| `POST /redundancy/gwaction/{failover,resync}`, `PUT /redundancy/config` | failover |
| `PUT /activation/activate/{key}`, `POST /activation/unactivate/{key}` | licensing |
| `DELETE /data/perspective/api/v1/sessions` | terminates live operator sessions |
| `POST /api-token/generate`, `DELETE /scim/**/{Users,Groups}/{id}` | credentials and identity |
| `POST /sync/reset`, `POST /data/eam/api/v1/upgrade-agent/{group}/{serverid}` | sync and remote agents |
| the 57 `POST /resources/delete/{mod}/{type}` bulk deletes and 77 resource DELETEs | resource loss |

456 of the 860 operations are writes (247 POST, 104 PUT, 105 DELETE). Treat every one as requiring a
fresh `find/` read, explicit human confirmation, and a project export or gwbk taken first.
