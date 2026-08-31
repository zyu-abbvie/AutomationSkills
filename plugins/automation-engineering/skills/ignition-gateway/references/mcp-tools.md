# The MCP_Tools server

The DEV gateway (`wa03593d`, Ignition 8.3.7) exposes an MCP server named `MCP_Tools` with 19 tools over streamable HTTP. This document is the tool-by-tool contract: how to connect, what each tool returns, where each tool hides its errors, and how to author a 20th tool.

Read this first: **every tool returns HTTP/JSON-RPC success even when it failed.** Errors come back in-band as data, and the key they live under differs per tool. If you write a generic "did it work?" check, you will report failures as successes. The per-tool map is in [Error keys](#errors-are-in-band-per-tool-key-map).

---

## Reaching the server

Transport is MCP streamable HTTP: a single `POST` endpoint, JSON-RPC 2.0 bodies.

```
POST http://wa03593d:8088/data/mcp/MCP_Tools
```

Two headers are mandatory and their failure modes look nothing alike:

| Request | Response | Meaning |
|---|---|---|
| `Accept: application/json` only | `406 Not Acceptable` — `{"message":"Client must accept both application/json and text/event-stream content types"}` | Client header bug. Not an auth problem. |
| `Accept: application/json, text/event-stream`, no credentials | `403 Forbidden` — `{"message":"Forbidden"}` | Missing auth. |
| Bogus token in `X-Ignition-API-Token`, `Authorization: Bearer`, or `Api-Token` | identical `403`, no `WWW-Authenticate` | The accepted header cannot be probed by guessing. |

Both responses reproduced live on 2026-08-28. Note there is no `401` anywhere in this path — Ignition returns `403` for both "no identity" and "wrong identity", so you cannot distinguish a bad token from an unsupported header name.

### Authorization

The server-config grants access at security level `Authenticated` only:

```json
"permissions": { "type": "AllOf", "securityLevels": [ { "name": "Authenticated", "children": [] } ] }
```
`.../config/resources/core/com.inductiveautomation.mcp/server-config/MCP_Tools/config.json`

No role or group is required. **Any authenticated identity on this gateway gets all 19 tools, including `evalScript` (arbitrary code execution) and `writeResource` (project mutation).** There is no per-tool allowlist: the same file maps tools as `"tools": {"project/MCP_Tools": "*"}`, so dropping a folder into the project exposes it with no config change, and you cannot hide a tool without editing server-config. That resource is scope `A` under `config/`, **not** under `projects/` — `writeResource` cannot reach it; only `evalScript` or the REST resources API can.

Two enabled api-token resources exist, `MCP-Key` and `Key_test`. `MCP-Key` is the intended credential; its secret is not recoverable from the backup (hash only) — get it from the user. Session defaults, live-only and absent from the backup: `maxSessions 100`, `maxLifetimeMinutes 120`, `idleTimeoutMinutes 30`.

### Handshake

```bash
curl -sS -X POST http://wa03593d:8088/data/mcp/MCP_Tools \
  -H 'Content-Type: application/json' \
  -H 'Accept: application/json, text/event-stream' \
  -H "X-Ignition-API-Token: $MCP_KEY" \
  -d '{"jsonrpc":"2.0","id":1,"method":"initialize","params":{
        "protocolVersion":"2025-06-18",
        "capabilities":{},
        "clientInfo":{"name":"automation-engineering","version":"1.0"}}}'
```

Then `notifications/initialized`, then `tools/list`, then calls:

```json
{"jsonrpc":"2.0","id":3,"method":"tools/call",
 "params":{"name":"readTags","arguments":{"paths":["[default]Portable/FC01/Experiment/Status"]}}}
```

`resources` and `prompts` are both declared empty — this server is tools-only. Do not implement resource or prompt round-trips against it.

---

## The 19 tools

Defaults below are the **Python handler defaults**, which are what actually apply; `default` in `resource.json` is documentation only and is not enforced.

| Tool | Parameters (type, default) | Returns (inner keys) |
|---|---|---|
| `evalScript` | `code` str "", `captureLevel` str "INFO", `captureLoggerSubstr` str "", `captureLimit` int 200 | `ok`, `result`, `stdout`, `stderr`, `error`, `logs[]`, `durationMs`, `kb?` |
| `validateScript` | `code` str "" | `ok`, `error?` `{type,message,line,col,text}` |
| `readTags` | `paths` array [] | `results[]` `{path,value,quality,good,timestamp}` |
| `writeTags` | `writes` array [] of `{path,value}` | `result.results[]`, `durationMs` |
| `browseTags` | `path` str "", `recursive` bool false, `limit` int 500 | `count`, `tags[]` `{name,fullPath,hasChildren,valueSource,dataType}` |
| `createTags` | `basePath` str "", `tags` array [], `collisionPolicy` str "o" | `result`, `durationMs` |
| `queryTagHistory` | `paths` array [], `startTime` int 0, `endTime` int 0, `returnSize` int 100, `aggregationMode` str "Average", `ignoreBadQuality` bool false | `result.{rows,columns}`, `durationMs` |
| `listTagHistoryProviders` | none | `result.{providers[],count}`, `durationMs` |
| `readResource` | `project` str "", `path` str "" | `project`, `path`, `result.{isDir,content\|files}` |
| `writeResource` | `project` str "", `path` str "", `content` str "", `refreshSignature` bool true, `scan` bool true | `result.{writtenBytes,path}`, `durationMs` |
| `listResources` | `project` str "", `typeFilter` str "" | `project`, `count`, `resources[]` |
| `listProjects` | none | `projectsDir`, `count`, `projects[]` |
| `createProject` | `name` str "", `title` str "", `description` str "", `parent` str "", `inheritable` bool false, `enabled` bool true | `result.{name,path,project.json}`, `durationMs` |
| `getGatewayLogs` | `minLevel` str "INFO", `sinceSeconds` int 300, `loggerSubstr` str "", `limit` int 100 | `count`, `events[]` `{ts,level,logger,thread,message}` |
| `searchLogs` | `pattern` str "", `sinceSeconds` int 600, `minLevel` str "INFO", `limit` int 100 | `count`, `events[]` |
| `tailWrapperLog` | `lines` int 200, `path` str "" | `path`, `lines`, `text` |
| `searchPitfalls` | `query` str "", `category` str "", `includeProposed` bool true, `limit` int 10 | `result.{count,totalInKnowledgeBase,query,terms,matchMode,category,pitfalls[],note}`, `durationMs` |
| `addPitfall` | `category`*, `symptom`*, `evidence`* str; `cause`, `fix`, `keywords`, `project`, `author` str | `result.{ok,action,id,status,note}`, `durationMs` |
| `getCurrentExperimentStatus` | none | `status`, `projectName`, `startTime` |

`*` = declared `"required": true`. Only `addPitfall`, `browseTags` and `searchPitfalls` (the three newest tools) use the `required` style; the other 16 use `"default": value`. Copy the `required` style for new work.

### Per-tool traps

- **`browseTags`**: recursion is unbounded-depth and `resource.json` declares no default for `limit` (handler default 500). `browseTags(path="", recursive=true)` walks the whole tag tree until it hits 500. A truncated result is indistinguishable from a complete one — `count` just equals your limit. Always pass an explicit `limit` and a non-empty `path`.
- **`writeTags`**: does an unguarded `w["path"]` / `w["value"]` on every element. Send `{"tagPath":...}` or omit `value` and you get an unhandled `KeyError` as an opaque MCP transport error, not a structured refusal. The keys are exactly `path` and `value`.
- **`createTags`**: `collisionPolicy` is coerced to its first lowercased character and silently falls back to `o` (overwrite) for anything not in `a/o/i/m`. A typo'd policy overwrites existing tags instead of aborting. `tags` is passed straight to `system.tag.configure` with no shape validation.
- **`queryTagHistory`**: default `returnSize=100` silently resamples and aggregates (`aggregationMode="Average"`). Pass `returnSize=-1` for native rows. Comparing default `queryTagHistory` output against `readTags` compares an average to an instantaneous value. Default window is `endTime - 3600000`.
- **`readResource` on a directory** reads every file in it and returns them all — text as utf-8, binary as base64, no size cap and no filter. Ignition resource folders routinely hold `thumbnail.png` and `data.bin`, so `readResource(project, "ignition/global-props")` can return megabytes. Always name the exact file, e.g. `com.inductiveautomation.perspective/views/Home/view.json`.
- **`readResource`/`writeResource`/`listResources` are confined to `<data>/projects/<project>`** (project names with `..`, `/`, `\` rejected; `..` segments rejected; normpath must stay under the project base). They **cannot touch `data/config/`** — tag providers, DB connections, historian providers, the MCP server-config. `listTagHistoryProviders` is the only tool that reads there (read-only); everything else config-scoped needs `evalScript` or the REST API.
- **`writeResource` skips the signature refresh when the file being written *is* `resource.json`** (`os.path.basename(full) != "resource.json"`). For a sibling it sets `attributes.lastModification = {actor:"mcp", timestamp:<UTC ISO>}` and blanks `lastModificationSignature` only if the key already exists. To add a brand-new resource you must write both files and author `resource.json` yourself with `lastModificationSignature` absent or `""` — a stale signature you hand it makes the gateway ignore the payload.
- **`writeResource` and `writeTags` both promise logs they never return.** `writeResource`'s description says "Response includes WARN+ logs emitted during the write/scan"; `writeTags`' says "plus any WARN+ logs". Neither implementation has any log-collection code or a `logs` key. After `writeResource`, a broken resource produces no feedback at all — call `getGatewayLogs`/`searchLogs` or `GET /data/api/v1/logs` separately to see whether the project scan accepted it.
- **`getGatewayLogs`' published description is wrong about its source.** It says `system.util.getLoggingDataset()`; the implementation seeks into the tail of `<user.dir>/logs/wrapper.log` and regex-parses the wrapper format. `searchLogs` and `evalScript` use the identical parser. Consequences: retention is whatever `wrapper.log` holds, not the in-memory ring buffer; the read window is `min(size, max(65536, sinceSeconds*4096))` bytes for `getGatewayLogs` and `max(131072, sinceSeconds*4096)` for `searchLogs`, so a large `sinceSeconds` silently truncates rather than erroring. The anonymous REST endpoint `GET /data/api/v1/logs` (verified 200 without auth) is a better log source for a plugin.
- **`createProject` resolves a different data dir than everything else.** `readResource`/`writeResource`/`listResources`/`listProjects` probe JVM properties in the order `("ignition.userlib", "ignition.data.dir")` before falling back to `<user.dir>/data`; `createProject` hardcodes `os.path.join(JSystem.getProperty("user.dir"), "data")`. If `ignition.userlib` is set (it normally points at `<install>/user-lib`, not `data/`), `createProject` creates a project the other four cannot see. Symptom: `createProject` reports ok with a path, then `listProjects` says "project not found". Resolve the real root once with `evalScript` before trusting either family.
- **`getCurrentExperimentStatus`** is hardcoded to three tag paths on the LargeScaleFC/Portable rig (`[default]Portable/FC01/Experiment/{Status,ProjectName,StartTime}`) and wraps every value in `str()`, so a missing tag returns the literal string `"None"`, not null. It is the only domain-specific tool of the 19 and does not generalise to other equipment.
- **`addPitfall` guardrails**, all enforced before any DB write: `symptom` non-empty; `category` in exactly `("silent-failure","schema-error","dead-end","designer-only","tooling","standard")`; `evidence` non-empty **and at least 20 characters**. Rows are always inserted with `status` hardcoded to `'proposed'` — the tool cannot create a `'verified'` row.
- **`addPitfall` dedupes on exact string equality of `symptom`** (`WHERE symptom = ?`). On a hit it increments `occurrences` and sets `updated`, and **silently discards the newly supplied cause, fix, evidence, keywords and project** while returning `ok=true, action="duplicate"`. Re-calling it to improve a fix throws your improvement away. Vary the symptom wording, or update the row directly via `evalScript` + `system.db`.
- **`addPitfall`'s dedupe SELECT is outside any try/except** (only the INSERT is guarded). If `SQLServer` is down or `dbo.MCP_Pitfalls` is missing, it raises rather than returning its structured envelope. A raw transport error from `addPitfall` means "DB unreachable", not "bad arguments" — do not retry with different arguments.
- **`searchPitfalls` returns confident-looking garbage for short queries.** It tokenises on whitespace and drops any token of length <= 2 or in a 20-word stop list. If zero tokens survive and no category is given, the WHERE clause reduces to `status <> 'superseded'` and you get the top N rows of the whole table with `matchMode` still reported as `"all-terms"`. Queries like `tz`, `db`, `no data`, `why is it not` match nothing. **Always inspect the returned `terms` array — if it is empty, the results are meaningless.** It searches AND-of-all-tokens over `(symptom, cause, fix, keywords)`, then silently retries as OR-of-any-token if that returns zero rows and there was more than one token, reporting `matchMode="any-term"` (precision dropped). `limit` clamps to 1..50.

---

## The return envelope: one wrapper, four inner shapes

Every tool returns `{"structuredContent": {...}}` — never a bare dict, never a list. The **inner** shape is inconsistent across four families. There is no output schema declared on any tool, so this table is the contract.

| Family | Inner shape | Tools |
|---|---|---|
| **(a)** `result` + `durationMs` | payload nested under `result` | `writeTags`, `createTags`, `queryTagHistory`, `listTagHistoryProviders`, `writeResource`, `createProject`, `searchPitfalls`, `addPitfall` (8) |
| **(b)** flat domain keys, no `durationMs` | payload at top level | `browseTags` `{count,tags}`, `readTags` `{results}`, `listResources` `{project,count,resources}`, `listProjects` `{projectsDir,count,projects}`, `getGatewayLogs`/`searchLogs` `{count,events}`, `tailWrapperLog` `{path,lines,text}`, `getCurrentExperimentStatus` `{status,projectName,startTime}` (8) |
| **(c)** hybrid | flat context keys **plus** a `result` | `readResource` `{project,path,result}` (1) |
| **(d)** `ok`-led | execution-status shape | `evalScript` `{ok,result,stdout,stderr,error,logs,durationMs[,kb]}`, `validateScript` `{ok[,error]}` (2) |

`durationMs` appears in only 9 of the 19 tools (family (a)'s 8, plus `evalScript`). Do not use its presence as a health signal.

**Never write a generic unwrapper.** A client that assumes `structuredContent.result` breaks on 8 of 19 tools; one that assumes flat keys breaks on the other 8. Branch per tool.

## Errors are in-band: per-tool key map

No tool raises an MCP protocol error for a refusal. A call that "succeeded" at the transport layer can still be a refusal, and the key differs:

| Error location | Tools | Example value |
|---|---|---|
| `structuredContent.error` (top level, string) | `createTags`, `queryTagHistory`, `readResource`, `listResources`, `createProject`, `searchLogs`, and `writeResource` **validation** failures | `"basePath is required (e.g. '[default]MyFolder')"`, `"path escapes project root"` |
| `structuredContent.error` + `traceback` | `queryTagHistory` on exception | `{error: str(e), traceback: ...}` |
| `structuredContent.result.error` | `writeResource` **write/IO** failures | `result = {"error": str(e)}` |
| `structuredContent.result.ok == false` + `result.error` | `addPitfall`, `searchPitfalls` | `{result:{ok:false,error:msg}}` |
| `structuredContent.ok == false` + structured `error` | `evalScript` `{type,message,traceback}`, `validateScript` `{type,message,line,col,text}` | — |
| `count: 0, events: [], error: ...` | `getGatewayLogs`, `searchLogs` when wrapper.log is missing | error sits alongside an empty-but-valid payload |
| raw transport error | `writeTags` (KeyError on malformed `writes`), `createTags` (bad tag shape), `addPitfall` (DB down) | no envelope at all |

Note `writeResource` has **two** error locations depending on failure stage. A caller checking only `structuredContent.error` treats a failed disk write as a success.

Minimum safe check for any tool call:

```python
sc = response["result"]["structuredContent"]
failed = ("error" in sc) or (sc.get("result") or {}).get("error") \
         or sc.get("ok") is False or (sc.get("result") or {}).get("ok") is False
```

---

## evalScript

### It does not sandbox. Treat it as a root shell on the gateway.

The exec globals are built at `tools/evalScript/onToolCalled.py:24`:

```python
__builtin__ = __import__('__builtin__')          # line 11
g = {"system": system, "__builtins__": __builtin__}   # line 24
```

`__builtins__` is the **full `__builtin__` module**, so `__import__`, `open`, `eval` and `file` are all reachable. Anything the gateway service account can do, an `evalScript` caller can do: `__import__('java.lang').lang.Runtime.getRuntime().exec(...)`, read or write any file on the host, reach any DB connection. There is **no allowlist, no denylist, no timeout, and no size cap on `code`**. Combined with the `Authenticated`-only permission, any valid identity on this gateway has arbitrary code execution.

Any skill or agent that generates `evalScript` payloads must supply its own guardrails, because the server supplies none. Default to read-only expressions; treat every write as a production change.

### Dual-mode compile: multi-statement scripts return `None` unless you set `_`

```python
compiled = compile(code, "<mcp-eval>", "eval")     # tried FIRST
value = eval(compiled, g)
except SyntaxError:
    compiled = compile(code, "<mcp-eval>", "exec") # fallback ONLY on SyntaxError
    exec(compiled) in g
    exec_result = {"ok": True, "result": g.get("_"), "error": None}
```
`tools/evalScript/onToolCalled.py:51-57`

A single expression returns its value. **Anything multi-statement falls to exec mode and returns whatever `g["_"]` holds — so without a `_` assignment you get `result: null` with `ok: true`,** a silent "it worked but returned nothing".

```python
rows = system.db.runQuery("SELECT TOP 5 id FROM dbo.MCP_Pitfalls", "SQLServer")
len(rows)      # WRONG -> ok=true, result=null
_ = len(rows)  # RIGHT
```

`exec(compiled) in g` is the Python-2 `exec` **statement** written to look like a function call. It is a syntax error under Python 3 — never lint these files with a py3 tool. Results are coerced by `coerce_result`, which passes `bool/int/long/float/str/unicode`, recurses into list/tuple/dict, and falls back to `repr(v)` for everything else. A Java object comes back as its `repr` string, not structured data.

### Log attachment is a byte-diff, and its timestamps are Chicago-local

`evalScript` records `os.path.getsize(<user.dir>/logs/wrapper.log)` before the run, then seeks to that offset afterwards and parses the new bytes. Timestamps are built with `time.mktime(...)` (line 92), which interprets `wrapper.log`'s local clock as local time. The gateway TZ is `America/Chicago` (live `gateway-info`: `"timeZoneId":"America/Chicago"`, `"ignitionVersion":"8.3.7 (b2026060908)"`). So `logs[].ts` epoch-ms values from `evalScript`, `getGatewayLogs` and `searchLogs` are Chicago-local-derived and are off by the client-vs-gateway offset, plus an hour across DST. **Do not correlate them with `queryTagHistory` epochs without converting.** Continuation lines (tab- or space-led) are appended to the previous entry's `message`.

### The `kb` block

Every response is enriched with a `kb` block matching `dbo.MCP_Pitfalls` keywords against `(code + error message + traceback + stderr).lower()`. Only comma-separated keywords of length >= 3 count; top 3 matches; `fix` truncated at 400 chars. The table is cached in `system.util.getGlobals()` under `_mcp_pitfall_cache` with a **60-second TTL**. A pitfall you just added will not surface for up to 60s, and **never** surfaces if its `keywords` column is empty — always populate `keywords` when calling `addPitfall`. The whole block ends with two handlers, and the in-code comment explains why:

```python
except Exception:
    kb = None
except:            # java.lang exceptions escape Jython's "except Exception"
    kb = None
```
`tools/evalScript/onToolCalled.py:189-192`

This is the estate's canonical Jython idiom. Any new Jython touching `system.db`, `system.net` or Java APIs needs either `except java.lang.Exception, e:` or a trailing bare `except:` — a lone `except Exception:` lets Java exceptions propagate and the tool call fails with an opaque MCP error instead of a structured one.

### The DB argument is not optional

The MCP_Tools project's `defaultDb` is `"testdb"`, **which does not exist** — the gateway has exactly one connection, `SQLServer` (live: `resources/names/ignition/database-connection` returns 1 item; target `jdbc:sqlserver://WQ01982D`, database `Ignition`, translator MSSQL). Every pitfall tool hardcodes `DB = "SQLServer"`. Any `system.db.runQuery(sql)` sent through `evalScript` without an explicit database argument resolves to `testdb` and fails — always pass it last: `_ = system.db.runQuery("SELECT COUNT(*) FROM dbo.MCP_Pitfalls", "SQLServer")`.

## validateScript: what `ok=true` actually proves

```python
compile(code, "<mcp-validate>", "exec")
return {"structuredContent": {"ok": True}}
except SyntaxError as e:
    ...  # {ok:false, error:{type,message,line,col,text}}
```
`tools/validateScript/onToolCalled.py:6-19`

| Does | Does not |
|---|---|
| Parses `code` as Jython 2.7 in **exec** mode | Execute, import, or resolve any name |
| Reports line/col/text for a `SyntaxError` | Detect a `NameError`, `AttributeError`, or wrong `system.*` signature |
| — | Catch anything but `SyntaxError` — a `java.lang` error from `compile` escapes as an unstructured MCP failure |

`ok=true` means **only** "this parses as Jython 2.7". It is not a type check and not an API check. Because it compiles in exec mode, it will also happily accept a multi-statement script that `evalScript` would return `null` for. The only real verification is `evalScript`. Its envelope is the odd one out: `{"ok": true}` with no `result` wrapper and no `durationMs`.

Corollary: these files are syntactically invalid Python 3 (`except JLang.Exception, je:` in `addPitfall`; `exec(x) in g` in `evalScript`; `long`/`unicode`/`StringIO`/`__builtin__` throughout). `python3 -m py_compile` on estate Jython fails and proves nothing. `validateScript` is the only correct parser.

---

## Authoring a tool

Tools are ordinary Ignition project resources. The authoring unit is a folder under `<project>/com.inductiveautomation.mcp/tools/<toolName>/` containing exactly two files.

```
MCP_Tools/com.inductiveautomation.mcp/tools/myNewTool/
├── resource.json
└── onToolCalled.py
```

All 19 tools are uniform: `scope="G"`, `files=["onToolCalled.py"]`, `version 1`, `restricted false`, `overridable true`, and no attribute keys beyond `title` / `description` / `parameters` / `lastModification` / `lastModificationSignature`. The exposed tool name is the **folder** name; `attributes.title` duplicates it in all 19 cases (whether the module reads the folder or the title is therefore untested — keep them identical).

`resource.json`:

```json
{
  "scope": "G",
  "version": 1,
  "restricted": false,
  "overridable": true,
  "files": ["onToolCalled.py"],
  "attributes": {
    "title": "myNewTool",
    "description": "What it does, and when the caller should reach for it.",
    "parameters": [
      { "name": "tagPath", "type": "string",  "required": true,  "description": "Fully-qualified tag path" },
      { "name": "limit",   "type": "integer", "required": false, "description": "Max rows" }
    ]
  }
}
```

`onToolCalled.py`:

```python
import system                      # the ONLY module-level import


def onToolCalled(builder, tagPath="", limit=50):
    os = __import__('os')          # everything else imported INSIDE the function
    time = __import__('time')
    JSystem = __import__('java.lang').lang.System

    started = int(time.time() * 1000)
    if not tagPath:
        return {"structuredContent": {"error": "tagPath is required"}}
    try:
        rows = system.db.runQuery("SELECT ...", "SQLServer")   # always name the DB
    except Exception as e:
        return {"structuredContent": {"error": str(e)}}
    except:                        # java.lang exceptions escape "except Exception"
        return {"structuredContent": {"error": "java exception"}}
    return {"structuredContent": {
        "result": {"rows": len(rows)},
        "durationMs": int(time.time() * 1000) - started,
    }}
```

Contract points:

- **`builder` is a mandatory first positional arg and is unused by all 19 implementations.** `grep -rn builder tools/` matches only the `def` lines.
- **Parameter names must match `resource.json` `parameters[].name` byte-for-byte** (camelCase), because the module passes them as keyword args. Rename in one file only and the handler silently receives its Python default instead of the caller's value.
- **Module-level imports are limited to `import system`.** No tool uses a module-level `import os`; all 19 use in-function `__import__('os')` / `__import__('java.lang').lang.System`. This is a strong enough convention (likely a hard constraint of how the module compiles the file) that a module-level `import os` risks the tool not loading.
- **Give the Python signature real defaults.** `resource.json`'s `default` is not enforced anywhere.
- **Declare `"required": bool`**, the newer style, since that is what the MCP JSON-Schema needs.
- Pick an envelope family and document it, since no tool declares an output schema. Family (a) (`result` + `durationMs`) is the most common.
- `scope "G"` is correct for a tool. Note that both `script-python` libraries in this project also use `G`, which contradicts the estate's own `projects/CLAUDE.md:64` (`A` — All scopes, for `script-python` libraries). A scope-`G` script library is invisible to Perspective and Vision client scope — if a new helper must be callable from a Perspective binding it needs scope `A`. Do not copy MCP_Tools' `G` for shared libraries.

### Two traps in this project's own source tree

**`ignition/script-python/mcp_helpers/code.py` is dead code.** 342 lines of `get_args`/`logs_since`/`safe_exec`/`read_resource`/`write_resource`/`feedback_envelope` helpers, and **not one of the 19 tools imports it** (`grep -rn "mcp_helpers" tools/` returns 0 matches). Every tool inlines its own copy. Editing `mcp_helpers` to fix a bug changes nothing at runtime — fixes must be applied per-tool. It also disagrees with the shipped tools: `mcp_helpers.logs_since()` uses `system.util.getLoggingDataset()` while every real tool parses `wrapper.log`, and it carries the same `ignition.userlib`-first data-dir bug. Do not treat it as a shared library.

**`projects/MCP_Tools/MCP_Tools/` is a stale self-copy — never read or edit it.** It is a copy of the project made 2026-05-18/19 sitting inside the live project. It has **no `project.json`**, so it is not a project. It holds 17 tool folders (missing `addPitfall` and `searchPitfalls`), no `script-python/maximo`, and an `evalScript/onToolCalled.py` that is the pre-KB version, ending at line 116 without the 79-line pitfalls block. Its `resource.json` files carry actors `admin`/`mcp`/`mcp-patch` dated 2026-05-18/19 against `QUINTRX` 2026-06-30 in the live tree. The other 17 tool `.py` files are byte-identical. It is most likely the product of a `writeResource` call with `path="MCP_Tools/..."`.

Practical consequence: `listResources(project="MCP_Tools")` returns **both** copies of every tool path. An agent that greps and takes the first match can read or patch the dead 2026-05 copy and conclude the KB tools do not exist. **Filter out any resource path starting with `MCP_Tools/`.**

Also worth flagging, not echoing: `ignition/script-python/maximo/code.py` hardcodes plaintext OAuth `client_secret` values for two environments in a dict literal (`ACTIVE_ENV = "qa"`). `readResource` exposes them to anyone with MCP auth, and they are in the doc backup. Do not put new secrets in `script-python` — use a secret provider. That file also documents a reusable estate pitfall: the DSMetadataProxy signals a rejected token as **HTTP 200 carrying `{"StatusCode":"401","result":"Unauthorized Access"}`**, not a real 401.

### Checklist for a new tool

1. `searchPitfalls(query=...)` first — and check the returned `terms` array is non-empty.
2. Create `com.inductiveautomation.mcp/tools/<toolName>/` in project `MCP_Tools` (**not** under the nested `MCP_Tools/MCP_Tools/`).
3. Write `resource.json`: `scope G`, `files ["onToolCalled.py"]`, `title == folder name`, `parameters[]` with `"required"`.
4. Write `onToolCalled.py`: `import system` only at module level; `def onToolCalled(builder, ...)` with defaults matching the parameter names exactly; in-function `__import__`; explicit `"SQLServer"` on every `system.db.*` call; `except Exception` **and** a bare `except:`.
5. `validateScript(code=...)` to confirm it parses as Jython 2.7 — remembering that this proves nothing beyond syntax.
6. `writeResource` both files. Omit `lastModificationSignature` or set it to `""`; never invent a hash. Writing `resource.json` itself skips the sibling refresh, so write both.
7. Check the write landed: `searchLogs(pattern="MCP_Tools|project", minLevel="WARN")` or `GET /data/api/v1/logs`. `writeResource` returns no logs despite its description.
8. `tools/list` to confirm the tool registered — no server-config change is needed, the mapping is `"*"`.
9. Exercise it and confirm the error path returns your envelope rather than a transport error.
10. `addPitfall(...)` for anything non-obvious you learned: `evidence` >= 20 chars naming the control that behaved differently, and **populate `keywords`** or it will never surface in `evalScript`'s `kb`.

---

## Unresolved

- **`dbo.MCP_Pitfalls` DDL.** Column set derived from the tools' SQL is `id, category, symptom, cause, fix, evidence, status, keywords, project, gateway, ign_version, author, occurrences, updated, supersedes`; status vocabulary is exactly `proposed`/`verified`/`superseded`. No DDL on disk. One `evalScript` against `INFORMATION_SCHEMA.COLUMNS WHERE TABLE_NAME='MCP_Pitfalls'` settles types and defaults.
- **Which header authenticates the POST.** All bogus variants return an identical 403 with no `WWW-Authenticate`. The `MCP-Key` secret must come from the user.
- **Whether `ignition.userlib`/`ignition.data.dir` are set** (decides whether `createProject` diverges): `_ = [JSystem.getProperty(p) for p in ('ignition.userlib','ignition.data.dir','user.dir')]`.
- **Whether the gateway indexes the nested `MCP_Tools/MCP_Tools/` subtree** or it is merely inert on disk. One authenticated `listResources(project="MCP_Tools")` settles it.
