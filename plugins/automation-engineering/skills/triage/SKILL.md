---
name: triage
description: Diagnose a fault in this lab-automation estate when you do not yet know which layer is at fault - routes a symptom into one of five ordered playbooks covering a Perspective view with no data, a tag that is stale or bad quality, a silent MQTT/groov RIO device, a gateway script that throws without surfacing, and a history or trend query that comes back empty. Use when something is broken and the layer is unknown, when a screen is blank or a value frozen, when a chart or trend has gaps, when a setpoint or command appears not to land, when a timer or tag-change script seems dead, or when you need the log, script-diagnostic and tag-export endpoints and their silent-failure traps.
---

# Triage: find the layer before you fix anything

A value crosses five layers between the instrument and the screen — RIO/Node-RED, MQTT, Ignition
tags, the historian, Perspective. Any of them can be the fault and four will look innocent. Route
first, then run one branch. **Every diagnostic endpoint here is DEV (`wa03593d:8088`, 8.3.7) only**;
PROD 8.1.28 404s all of them, see the last section.

```bash
DEV=http://wa03593d:8088
curl -s "$DEV/data/api/v1/overview/connections"            # per-subsystem cards — the honest one
curl -s "$DEV/data/api/v1/overview/problems"               # items:[] when "clean"
curl -s "$DEV/data/api/v1/diagnostics/threads/deadlocks"   # literally {} when clean — an object, not []
```

**`/overview/problems` lies by omission.** Right now it returns `items:[]` while 302 tags are dead
and 38 history series have stopped. `/overview/connections` is where the truth is — check every
card's `lines[].error`. Live on dev: `OPC Connections` = `2/6 healthy resources` +
`4 items require attention`, `error: true`; `Store and Forward Engine` = `511 quarantined` with
**`error: false`**. A card that is not flagged is not a card that is fine.

## Which branch?

Ask in order, stop at the first yes.

| # | Question | Branch |
|---|---|---|
| 1 | Is the browser even still talking? `lastComm` large or `activePages: 0` in `/data/perspective/api/v1/sessions/` | **(a)** client/websocket, not data |
| 2 | Is the widget a chart, table or trend fed by `tag-history` or a named query? | **(e)** history |
| 3 | Is the value produced by a timer / tag-change / update script or an SFC? | **(d)** script |
| 4 | Is the backing tag under `[MQTT Engine]…`? | **(c)** device / MQTT |
| 5 | Is the backing tag under `[default]…` with `valueSource: "opc"`? | **(b)** tag quality |
| 6 | You do not know the backing tag yet | **(a)**, which ends by handing you to (b) or (e) |

Branches chain deliberately: (b) can end in (c) for an MQTT-sourced tag, and (e) almost always ends
in (b) or (c), because a dead source produces empty history silently.

## (z) Log guard rails — apply to every `/logs` call below

The two ways `/logs` wastes an hour:

1. **Always pass `limit=N`.** The default is `limit=-1`, which means *count only*: HTTP 200,
   `metadata.total: 54494`, `items: []`. It looks like "no matching logs". It is not.
2. **Read `metadata` before `items`.** `total` = real count with `matching: 0` means **your
   parameter NAME is wrong** — unknown params are silently treated as no-match filters, at HTTP 200
   (`?zzzbogus=xyz&limit=2` → `{'total': 54494, 'matching': 0}`). Both 0 means your filter is valid
   and genuinely matched nothing.

The only valid params are `properties, minLevel, allowedMarkers, startTime, endTime, logger, limit,
offset, sortBy, search, filter`. There is no `level`, `maxLevel`, `project` or `message` — those all
fall into the trap above.

| Param | Tested behaviour |
|---|---|
| `logger=` | **Exact full-name match.** `ExtensionFunctionTimerScriptTask` → `total 0`; the fully qualified name → `total 3198`. A partial name looks exactly like a typo'd param. |
| `search=` | **Whitespace-tokenized OR**, so extra words *widen*. `Martillac` → 21419; `Martillac zzznotarealtoken` → 21419, unchanged. Use one distinctive token. |
| `startTime`/`endTime` | Epoch **milliseconds**. Seconds are not rejected — read as 1970, they return the whole log (12 rows for a 10-min window; 54467 for the same instant in seconds). |
| `minLevel=` | Enum **values** fail loudly, unlike param names: `minLevel=error` → HTTP 500. Uppercase only. `TRACE`/`DEBUG`/`INFO` return identical counts, so the store holds INFO and above. |

`${CLAUDE_PLUGIN_ROOT}/bin/ign logs --level ERROR --limit 20 --stack` sets `limit`, renders the epoch
millis, and warns on `total`≫`matching`. Prefer it; drop to `curl` for the params it does not expose
(`startTime`, `endTime`, `offset`, `sortBy`, `filter`, `properties`).

## (a) Perspective view shows no data

- **a1** — Confirm a client is connected: `curl -s "$DEV/data/perspective/api/v1/sessions/"`. **Use the
  trailing slash** — that is the GET route in the spec; the bare `/sessions` path is the **DELETE**
  route that terminates sessions. Check `project` matches what the user says, `lastComm` is small (ms
  since last client comm — 8317 on a live session), and `activePages > 0`. A large `lastComm` means the
  browser or websocket is gone and nothing downstream is broken.
- **a2** — Get the view path rather than guessing:
  `curl -s "$DEV/data/perspective/api/v1/session/{sessionId}/pages"` then
  `.../session/{sessionId}/page/{pageId}/views`.
- **a3** — Rule out gateway-wide sickness with the three commands at the top of this file, plus
  `ign logs --logger Perspective.Routes --level ERROR --limit 10` —
  `Could not find project 'X'. Verify url is correct and project is published.` means the URL is
  wrong, not the view.
- **a4** — Read the binding in `view.json` (it lives in `propConfig`, not next to the prop — see
  `ignition-resources`) to find what actually feeds it. `tag` → **(b)**; `tag-history` or `query` →
  **(e)**.

## (b) Tag stale or bad quality

- **b1** — Read the tag's own config; historization and OPC wiring are readable anonymously.
  ```bash
  curl -s "$DEV/data/api/v1/tags/export?provider=default&path=Martillac&type=json&recursive=true"
  ```
  `type` is **required** — omit it and you get HTTP 400 `type parameter missing`, not a 200 — and
  `recursive=false` at a provider root returns a 41-byte stub, `{"name":"","tagType":"Provider"}`,
  with no tags in it. Note the leaf's `valueSource`, `opcServer`, `opcItemPath`, `historyEnabled`,
  `historyProvider`, `dataType`.
- **b2** — If `valueSource` is `opc`, check the connection is actually enabled:
  `ign res names ignition/opc-connection`. Live dev: `Ignition OPC UA Server` and
  `Sartorius MFCS_ABC` true; **`Martillac_BioReactor`, `Osmometer_ABC-4340-1`,
  `Osmometer_R14-120-1`, `VICellBlu1` all `enabled: false`**. A disabled connection produces
  bad-quality tags, `getServerState() == "UNKNOWN"`, and **nothing** in `/overview/problems`.
- **b3** — Quantify the blast radius before escalating. Save the b1 export and count leaves by
  `(opcServer, historyEnabled)`:
  ```bash
  python3 -c 'import json,collections,sys; c=collections.Counter()
def walk(o):
    if isinstance(o,dict):
        if "opcServer" in o: c[(o["opcServer"],bool(o.get("historyEnabled")))]+=1
        for t in o.get("tags") or []: walk(t)
walk(json.load(open(sys.argv[1]))); print(c)' /tmp/mart.json
  ```
  → `{('Martillac_BioReactor', False): 264, ('Martillac_BioReactor', True): 38}`: 302 dead tags and 38
  dead history series from one config flag.
- **b4** — If the connection **is** enabled, pull driver-side errors with a single token:
  `ign logs --level WARN --search Martillac_BioReactor --limit 50`.
- **b5** — If the tag is `[MQTT Engine]…` its `valueSource` is not OPC, so none of the above
  applies. Go to **(c)**.

## (c) MQTT device silent

- **c1** — Broker connection exists and is enabled:
  `ign res names com.cirruslink.mqtt.engine.gateway/server` → dev has exactly one, `Chariot`,
  `enabled: true`.
- **c2** — Use the estate's own convention: a **retained per-instrument `Status` topic** under
  `SERIAL`, whose value must be the literal string `ok` —
  `[MQTT Engine]<SITE>/<BLDG>/<ROOM-FLOOR-BENCH>/<EQUIP>/SERIAL/<INSTR>/Status`, with `AG-02`
  stir/heat and stir plate, `WT-01` weight scale, `TC-01` chiller. Require **good quality AND
  `str(value).strip() == "ok"`**; anything else, including `error: …`, means the Node-RED serial port
  on the RIO is down. Reference implementation at lines 584-596 of
  `doc/Ignition-WA03593D_Ignition-backup-20260828-1312/projects/FLEX01-R8-320-3-1/ignition/script-python/flex01/code.py`,
  which reports as `LastHTTPError = "Device offline: <names>"` and never touches `Status` itself.
- **c3** — Confirm the watchdog that normally reports this is itself alive. In
  `curl -s "$DEV/data/api/v1/scripts/diagnostics/TIMER"` the `checkLiveDevices` entry for
  `FLEX01-R8-320-3-1` should read `enabled: true` with a recent `lastExecution` (live: rate `5000`,
  `duration: 1`). Then `ign logs --logger flex01.liveMonitor --limit 50`.
- **c4** — Separate "device silent" from "gateway cannot publish":
  `ign logs --logger com.cirruslink.mqtt.engine.gateway.EngineRPCHandler --level ERROR --limit 20`.
  Outbound `HMI_COM` command failures read `Can't publish to the 'Chariot' on topic: <topic>. Make sure
  supplied name is either a valid MQTT Server or server set name` — an Ignition-side failure, not a
  dead edge device.
- **c5** — Confirm at the wire. A retained value persists after the device dies, so read the heartbeat
  *changing*, not its current value. Two messages in 12 s means alive.
  ```bash
  MQTT_HOST=10.94.132.35 ${CLAUDE_PLUGIN_ROOT}/bin/mqtt-probe watch 'LC/R8/320-3-1/TFF/Heartbeat' --seconds 12
  ```
  **Watch the PROD broker `10.94.132.35`** — every field device publishes there and the dev
  `[MQTT Engine]` tree is stale. Then cross-check the edge flow in
  `doc/backup_nodered/<SITE_BLDG_ROOM_EQUIP>/<ip>_<date>.zip` (`node-red/flows.json`).

## (d) A script throws but nothing surfaces

- **d1** — Check for a **wedged** execution first: `curl -s "$DEV/data/api/v1/scripts"` lists what is
  executing *right now* as `{threadId, executionStart, elapsedMillis, description}`. Any entry whose
  `elapsedMillis` exceeds its own rate is stuck, and `sharedThread: true` in `resource.json` means
  one wedged script starves every other shared timer.
- **d2** — Sweep every script diagnostic type with
  `for t in TIMER TAG_CHANGE STARTUP SHUTDOWN UPDATE; do curl -s "$DEV/data/api/v1/scripts/diagnostics/$t"; done`.
  That enum is exact (case-insensitive); anything else — `MESSAGE`, `ALARM`, `SESSION`, `tag-change` —
  is **HTTP 500**. This is the only place a **compile/parse** failure shows up, and such a script never
  ran at all, which is why the log is silent. Live on dev, `PC01-`, `PC02-` and `PC08-R8-133-1-1` all
  carry `SyntaxError: mismatched input '\n\n' expecting INDENT (<<[PC02-R8-133-1-1] Update Script>>, line 4)`.
- **d3** — **`error: {}` does not mean healthy.** The `error` object reflects only the **most recent
  execution**. On the live failing `OpcAutoHeal`: at `lastExecution 1787957544330` (the tick that
  threw) it held the full Jython traceback; 60 s later at `1787957604333` (a cooldown-skip tick) the
  same entry read `error: {}`. A throttled failure is invisible here four ticks out of five, so always
  corroborate against the log and read the `<<TimerScript:Project/Name @rate>>` frame and line number
  out of the stack:
  ```bash
  ign logs --logger com.inductiveautomation.ignition.common.script.ExtensionFunctionTimerScriptTask \
           --level ERROR --limit 20 --stack
  ```
- **d4** — Then read the source and its schedule —
  `doc/Ignition-WA03593D_Ignition-backup-20260828-1312/projects/<Proj>/ignition/timer/<Name>/handleTimerEvent.py`
  plus the sibling `resource.json` (`delay`, `fixedDelay`, `sharedThread`, `enabled`) — and widen the
  log to the script's own logger name, whatever it passes to `system.util.getLogger`.
  **Beware the throttle:** a cooldown constant means the error cadence is *not* the timer cadence.
  `OpcAutoHeal` fires every 60 s and errors every 300 s, so a 2-minute window misses it entirely.
- **d5** — **Ignition self-suppresses repeats.** The ERROR message ends
  `Repeat errors of this type will be logged as 'debug' messages.` A quiet log is not a fixed script;
  always corroborate with d1 and d2.

## (e) History query returns empty

- **e1** — Is the tag even historized? Run the b1 export and confirm `historyEnabled: true` **and** a
  `historyProvider` (estate default `SQLServer`). Absent or false means your query is correct and there
  is no data. That misconfiguration is live and logged — `tags.execution.actors.history`:
  `[[default]LU/B56/12-1/Training/AngerLevel] History is enabled, but history provider is not defined.`
- **e2** — Provider and DB up: `ign res names ignition/store-and-forward-engine` (expect `SQLServer`,
  `enabled: true`) and the `Database Connection` card reading `1/1 healthy resources`.
- **e3** — **Is the source still producing?** A live history series with a dead source stops silently.
  Run (b2): if `opcServer` is disabled, history stopped when the connection did. If the tag is
  `[MQTT Engine]…`, run (c).
- **e4** — Rule out clock skew and time-window bugs, the two commonest false "empty history".
  `curl -s "$DEV/data/api/v1/overview"` gives `timezone` (dev `America/Chicago [GMT-6:00]`) and
  `driftRate` (dev `0.0`). Confirm your own bounds are epoch **milliseconds**.
- **e5** — Pull history errors with one distinctive token. The dev gateway's single largest ERROR
  logger is a history one, 180 of the last 400 ERRORs:
  `ign logs --logger tags.history.query.dataloader.DB --level ERROR --limit 20` → `mqtt engine No
  information could be found for historical system 'ignition-wz02163d'. Please verify that the system
  is correctly storing data to the specified database ('SQLServer').` That is a **dev** query asking
  for a **prod** system's data, which no amount of DB tuning will fix.
- **e6** — Quarantine: 8.3.7 has **no store-and-forward runtime endpoint**, only config CRUD under
  `/data/api/v1/resources/**/ignition/store-and-forward-engine`. The *count* is on the
  `Store and Forward Engine` card of `/overview/connections` (dev: `511 quarantined`). For the records
  themselves, use the gateway web UI or read `[System]Gateway/StoreAndForward` tags from a script.

## Worked example: the live dev failure, symptom to fix

**Symptom.** Nothing reported it. `/overview/problems` was `items: []`. It was found only because
`/overview/connections` read `OPC Connections — 2/6 healthy resources, 4 items require attention`,
`error: true`.

**(d1) Is anything wedged?**

```
$ curl -s "$DEV/data/api/v1/scripts"
{"items":[{"threadId":567811,"executionStart":1787694454226,"elapsedMillis":263106957,
 "description":"TimerScript - project:Martillac-Alarms OpcAutoHeal @60,000ms "}], ...}
```

One script executing, `elapsedMillis` 263106957 ≈ **73 hours** for a timer whose rate is 60 s, on a
`sharedThread: true` timer that therefore starves every other shared timer.

**(d2/d3) What is it throwing?** `scripts/diagnostics/TIMER` shows `OpcAutoHeal`,
`projectName: Martillac-Alarms`, `enabled: true`, `details.rate: "60000"`, and on the tick that threw,
`error.message`:

```
File "<<TimerScript:Martillac-Alarms/OpcAutoHeal @60,000ms >>", line 42, in handleTimerEvent
  at com.inductiveautomation.ignition.gateway.opc.OpcConnectionManagerImpl.setServerEnabled(...:372)
java.lang.Exception: java.lang.Exception: unknown server: Martillac_BioReactor
```

3198 of these sit in the log under
`com.inductiveautomation.ignition.common.script.ExtensionFunctionTimerScriptTask` at ERROR — **not**
under the script's own `martillac.autoheal` logger, which is the tell that the exception escaped the
script's `except`.

**(d4) The source**, at
`doc/Ignition-WA03593D_Ignition-backup-20260828-1312/projects/Martillac-Alarms/ignition/timer/OpcAutoHeal/handleTimerEvent.py`:

```python
SERVER = "Martillac_BioReactor"
COOLDOWN_S = 300
state = str(system.opc.getServerState(SERVER))   # line 14 — returns "UNKNOWN", does not throw
if state == "CONNECTED":
    return                                       # ← blacklist, not whitelist
...
try:
    system.opc.setServerEnabled(SERVER, False)   # line 42 — throws here
    time.sleep(2)
    system.opc.setServerEnabled(SERVER, True)
except Exception, e:                             # ← misses java.lang.Exception
    logger.error("Martillac OPC auto-heal FAILED: " + str(e))
# resource.json: {"delay":60000,"fixedDelay":true,"sharedThread":true,"enabled":true}
```

**(b2) Why it fails.** `ign res names ignition/opc-connection` shows
`{"name":"Martillac_BioReactor","enabled":false}`. An **administratively disabled** connection is not
registered in the runtime `OpcConnectionManager`, so `setServerEnabled` cannot resolve the name and
throws. Three things compound:

1. `getServerState()` does **not** throw for a disabled connection — it returns the string
   `"UNKNOWN"`, which `!= "CONNECTED"`, so the heal path runs on a connection that is off on purpose.
   Live: `ign logs --logger martillac.autoheal --limit 3` →
   `Martillac OPC state=UNKNOWN cooldown (240s remaining) - skipping`.
2. The `java.lang.Exception` **escapes `except Exception, e`** in Jython 2.7, so the intended
   `logger.error` never runs and it surfaces as a gateway-level `JythonExecException` instead.
3. `COOLDOWN_S = 300` means the timer fires every 60 s but only errors every 300 s — verified from
   three consecutive events exactly 300 s apart. The other four ticks log INFO, and on those ticks the
   diagnostic `error` object is empty.

**(b3) Blast radius.** `tags/export?provider=default&path=Martillac&type=json&recursive=true`
(159788 bytes) → **302** OPC leaf tags, every one `opcServer: "Martillac_BioReactor"`, of which **38**
have `historyEnabled: true`. So 302 tags read bad quality and 38 history series have been silently
dead-ended, and `/overview/problems` reported `items: []` throughout.

**The fix.** In order of what actually matters:

1. **Re-enable the `Martillac_BioReactor` OPC connection in gateway config**, if Martillac is meant to
   be running. The script cannot do that itself — that is the whole reason it throws. Also decide
   whether `Osmometer_ABC-4340-1`, `Osmometer_R14-120-1` and `VICellBlu1` are intentionally disabled.
2. **Whitelist recoverable states instead of blacklisting `CONNECTED`** —
   `if state not in ("FAULTED", "DISCONNECTED", "RECONNECTING"): return`, so `UNKNOWN`/`DISABLED`
   reads as "intentionally off, do not heal".
3. **Catch `java.lang.Exception` too**, so a driver-side failure lands in `martillac.autoheal` rather
   than escaping to the timer task.

Do not apply 2 or 3 by hand-editing the file — project resources belong to the Designer (`ignition-resources`).

## PROD triage

PROD `wz02163d:8088` (8.1.28) has **none** of this: every `/data/api/v1/**` route 404s and only
`GET /system/gwinfo` works. Prod triage is three things.

1. **Read the backup on disk** — `doc/Ignition-WZ02163D_Ignition-backup-20260828-1137/projects/`. 8.1
   packs all gateway event scripts into one gzipped Java-serialized blob at
   `ignition/event-scripts/data.bin`, so the timer script that was a plain `.py` above has to be
   inflated first (`ignition-resources` has the one-liner).
2. **Read `data/logs/wrapper.log` on the gateway host** — there is no `/logs` endpoint.
3. **Use the Designer** for tag quality, the script console and history queries.

The MQTT side is the exception: the prod broker `10.94.132.35` is where every field device publishes,
so `mqtt-probe watch` against it is the real observability layer for branch (c) on either tier.
