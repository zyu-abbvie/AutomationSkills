---
name: ignition-gateway
description: Interact with a live Ignition gateway - read gateway config resources over the HTTP API, inspect projects, read and filter gateway logs, export or import a project, request a project scan so on-disk edits are picked up, create tag providers or database connections or historian providers, and call the MCP_Tools server for tag reads and writes and script evaluation. Use when you need live gateway state rather than a backup on disk, when configuring gateway-level resources, or when an API call returns something unexpected.
---

# Driving a live Ignition gateway

**Establish which tier you are on before anything else.**

```bash
${CLAUDE_PLUGIN_ROOT}/bin/ign capabilities
```

| | DEV `wa03593d:8088` (8.3.7) | PROD `wz02163d:8088` (8.1.28) |
|---|---|---|
| `/data/api/v1/**` | present | **404 — does not exist** |
| Reads | **anonymous**, HTTP 200 | n/a |
| Writes | **401**, empty body, without a token | n/a |
| MCP | `MCP_Tools`, 403 anonymous | none |

`GET /system/gwinfo` is plain text and works on **both** versions — the only cross-version probe.
The bundled `ign` refuses non-GET requests to a host listed in `IGN_PROD_HOSTS`.

## What the API can and cannot do

This is the thing that wastes the most time. The `resources` grammar covers **gateway config only**.

| You want | Route exists? | Use instead |
|---|---|---|
| Tag provider, DB connection, historian, MQTT, OPC config | **yes** | `ign res` |
| Perspective views, named queries, scripts, UDT defs, pipelines | **no** — 404 | files on disk, `projects/export`, or MCP `readResource`/`writeResource` |
| Tag **values** — read/write/browse | **no** | MCP `readTags`/`writeTags`/`browseTags`, or a gateway script |
| Tag **configuration** | partly | `GET tags/export`, `POST tags/import` |
| A whole project in or out | **yes** | `ign export`, `POST projects/import/{name}` |

## Reading gateway config

```bash
ign res names   com.cirruslink.mqtt.engine.gateway/server      # just the names
ign res list    ignition/database-connection                   # full envelopes
ign res list    ignition/tag-provider default                  # one resource
ign res singleton com.cirruslink.mqtt.engine.gateway/general
ign res schema  com.inductiveautomation.historian/historian-provider
```

**`ign res schema` is what you call before authoring anything.** It returns the type's extension
points, their `typeId`s and their `defaultSettings` — the actual valid shape, rather than your guess.

Two traps in the read envelope:

- `attributes` has **no fixed shape**. Across 77 live resources: `uuid` on 53, `lastModification`
  on 44, `enabled` on 26, and `{}` on 20. **Always `.get()`** — `attributes["lastModification"]["timestamp"]`
  will `KeyError` on a quarter of the estate.
- There is a 14th key, `backupConfig`, present on the Cirrus Link MQTT resources. An exhaustive
  key list of 13 is wrong.

## Writing gateway config

`POST` creates, `PUT` updates. Both take a **JSON array** of envelopes — it is a batch API even for
one resource.

```bash
ign api PUT /data/api/v1/resources/ignition/database-connection --confirm --data '[{
  "name": "SQLServer", "signature": "<from the previous GET>", "config": { }
}]'
```

- **Named** types require `name` (POST) or `name` + `signature` (PUT).
- **Singleton** types (`ignition/system-properties`, `com.cirruslink.mqtt.engine.gateway/general`,
  `com.inductiveautomation.opcua/server-config`, and 17 others) have **no `name` property at all**,
  and their DELETE path omits the name segment.
- **HTTP 200 does not mean it worked.** The body is
  `{"success": bool, "changes": [{"name", "type", "collection", "newSignature"}], "problem": {…}}`.
  Check `success`. Take `newSignature` for your next call.
- `signature` is a **path segment** on the resource DELETE but a **required query parameter** on the
  `datafile` routes. Same concept, two placements.

Full contract: [references/http-api.md](references/http-api.md).

## Silent failures on read endpoints

Every one of these returns **HTTP 200** and no error:

| Mistake | What you get | The tell |
|---|---|---|
| Misspelled query parameter | `items: []`, HTTP 200 | `metadata.matching` is 0 while `metadata.total` stays at the real count |
| `filter=field[op]=value` | `items: []` | send it as a **bare** `field[op]=value` parameter instead |
| `tags/export?recursive=false` at a provider root | a 30-byte stub | `{"name":"","tagType":"Provider"}` |
| `tags/export` without `type` | HTTP 400 | it is a required parameter |
| `search=` with several words | *more* rows, not fewer | `search` is OR-tokenized; `logger=` is exact-match |
| `limit=0` | zero items | `matching` stays at the real count — this is "count only", not a filter |

With a **valid** filter that legitimately matches nothing, `total` drops to 0 too. So `total` large
+ `matching` 0 means **your parameter name is wrong**. `ign logs` warns you when it sees this.

**`limit` defaults to `-1`, which means unlimited, not "none".** A bare `GET /data/api/v1/logs`
returns every entry — 54,499 of them on dev today. Always pass `limit`; this is a
blow-out-your-context trap, not an empty-result one. `ign logs` defaults to 50.

Also: a 404 returns a **Jetty HTML page**, not JSON, and a 401 returns an **empty body**. Check the
status code before parsing.

## Logs

```bash
ign logs --level ERROR --limit 20 --stack        # what is actually broken right now
ign logs --logger martillac.autoheal --limit 50  # logger= is an EXACT match
ign logs --search history --level WARN
```

Timestamps come back as epoch **milliseconds**. `ign logs` renders them; raw callers must convert.

## Getting on-disk edits picked up

The gateway watches project folders, but a hand edit is not the supported path. After editing files:

```bash
ign api POST /data/api/v1/scan/projects --confirm     # needs a token
```

`GET /data/api/v1/scan/projects` reports `{scanActive, lastScanTimestamp, lastScanDuration}`. The
supported path remains a Designer save. Note that `lastModificationSignature` is **not** a content
hash, so a stale signature does not block a change — and inventing one achieves nothing.

## Reading live project state without credentials

```bash
ign export TFF_Parent --extract /tmp/tff
```

`GET /data/api/v1/projects/export/{name}` is **anonymous** and returns a zip whose layout is exactly
the on-disk tree. Two consecutive exports are byte-identical, so it is safe to cache and diff.

But the export rewrites most `resource.json` files (recomputed signature, `actor: "external"`,
normalized key order). Measured on `TFF_Parent`: of 138 files, all 100 payload files matched the
backup byte-for-byte and **all 38 differences were `resource.json`**. **Diff payload files only.**

## MCP_Tools

19 tools on dev at `POST /data/mcp/MCP_Tools`. This is the only route to tag **values** and to
running a script. It needs an `Accept` header listing both `application/json` and
`text/event-stream` (otherwise 406) and authentication (otherwise 403).

Two things to know before you call it:

- **Errors come back in-band as data, not as MCP errors**, and the error key differs per tool. A
  call can "succeed" while having failed. Check the payload, not the transport.
- **`evalScript` does not sandbox.** Its globals expose the full builtin module, so it is arbitrary
  code execution as the gateway process. It also compiles in `eval` mode first and only falls back
  to `exec` on `SyntaxError` — so a multi-statement script **returns `None` unless it assigns to the
  single-underscore variable**.
- **`validateScript` catches only `SyntaxError`.** It does not execute, import or resolve names, so
  it cannot detect a `NameError` or a wrong `system.*` signature. It proves the file parses. Nothing more.

Full contract: [references/mcp-tools.md](references/mcp-tools.md).

## Writes that can damage the estate

Require explicit human confirmation for every one of these. Never issue them to satisfy your own
plan:

- `POST /data/api/v1/backup` — **restores** a gateway backup, overwriting the whole gateway
- `POST /data/api/v1/restart-tasks/restart` — restarts the gateway
- `POST /data/api/v1/modules/install`, `PUT /data/api/v1/modules/toggle-state`
- `DELETE /data/api/v1/projects/{name}`
- `POST /data/api/v1/tags/import` with `overwrite` semantics

## References

- [references/http-api.md](references/http-api.md) — full CRUD grammar, envelopes, schema endpoint, silent failures
- [references/mcp-tools.md](references/mcp-tools.md) — all 19 tools, return families, authoring a new tool
