---
name: nodered-rio
description: Work on the Opto 22 groov RIO edge devices that run Node-RED and own the instruments - the whole-device backup layout under doc/backup_nodered, the flows.json node census, the acquire/transform/publish pipeline that produces every MQTT topic Ignition consumes, mqtt-broker and serial-port config node field values, groov-io read/write/input nodes, the Node-RED Admin API deploy routes, and the Auto_NodeRed flow generator. Use when reading or authoring a Node-RED flow, when a topic is missing or has an "undefined" or wrong root, when tracing which device publishes a tag, when decoding a backup directory name, when configuring serial or Modbus device comms on a RIO, or when asked to deploy or diff flows on an edge gateway.
---

# groov RIO edge devices and Node-RED

**You cannot reach these devices from this host.** Node-RED's editor and Admin API live on port 1880,
proxied by groov Manage at `https://<ip>/node-red`, and every attempt times out —
`curl --connect-timeout 4 http://10.246.116.140:1880/` returns HTTP `000`, `ping -c1 -W3 10.246.116.140`
loses 100%. The device subnets (`10.201.*`, `10.210.*`, `10.211.*`, `10.246.*`, `10.247.*`) and the prod
broker `10.94.132.35` are all unreachable while `http://wa03593d:8088/system/gwinfo` returns 200, so this
is routing, not a local fault. **All work here is offline, against `flows.json` inside a backup zip.** The
Admin API section is what to do from a host that *does* have access.

> **Paths in this document.** `$DEV` and `$PROD` are the `projects/` directories inside an
> Ignition gateway backup, `$NODERED` a directory of groov RIO device backups. Set them to wherever
> you keep yours, or put `backups_dir` / `nodered_backups_dir` in `automation.local.yaml`:
>
> ```bash
> DEV=<backups>/Ignition-<DEVHOST>_Ignition-backup-<stamp>/projects
> PROD=<backups>/Ignition-<PRODHOST>_Ignition-backup-<stamp>/projects
> NODERED=<backups>/backup_nodered
> ```

## What a device is, and what a backup holds

Every backup is a **GRV-R7 groov RIO** (`info.json` → `deviceModel`), firmware 3.5.0 to 4.0.3 across the 17
devices on disk. No EPIC appears anywhere. Node-RED comes from the firmware, not `package.json`, so **the
Node-RED version is not determinable from a backup** — read it from `GET /settings`. A zip is a
**whole-device backup**, not a flow export:

```
<ip>_<date>.zip
├── node-red/          flows.json · flows_cred.json · package.json · package-lock.json
│                      (lockfileVersion 3) · node_modules.tar.gz (~9.7 MB, exclude it)
├── io/MMPCFG.o22      I/O rack configuration — a SQLite 3 database, not text
├── accounts/auth.db   local device logins — SQLite, holds hashes. Do not read.
├── info.json  mmpSettings/mmp.json  network/{network.json,openvpn.json}  usb/usb.json
├── firewall/firewall.json  snmp/{snmpd.conf,snmp.json}  time/time.json
├── bluetooth/bluetooth.json  staticroutes/staticroutes.json  data-service/service.json
└── clientSsl/ userFiles/ data-service-mqtt-broker-{certs,keys}/  (empty in every sample)
```

```bash
unzip -o -q -x 'node-red/node_modules.tar.gz' \
  '$NODERED/LC_R8_320-3-1_TFF/'*.zip -d /tmp/nr/tff
```

`doc/backup_nodered/` has **37 directories and 181 zips, but only 17 directories contain a zip; 17 are
completely empty** — `ABA_ABA_120-6_AKTA`, all five `LC_R8_133-1-1_PC0*` pump cubes,
`LC_AP31_273-4_Camera`, `IRVINE_Teller_BSL3-2-1_TFF`, `LC_F3_Portable_FC01`, `IRVINE_RD2_TBD_LAI_lab`,
`Gantry`, `Camera Data` and more. **There is no AKTA, Camera, PC or Gantry flow on disk anywhere.**
Three directories hold no device backup: `Backup Tool/` (`get.py`, `getchron.py` — Dash apps that pull the
zips, and **both embed 9 devices' groov Manage API keys in cleartext**), `Label Tool/` (`labelData.xlsx`),
`EqSchVideo/` (a 30 MB `.mp4`). `LC_AP31_273-4_Camera.zip` at the root is misnamed: it is a snapshot of the
whole backup share, 34 top-level directories. `Backup Tool/get.py` is also where the zips come from, and it
explains the naming — `GET https://<ip>/manage/api/v1/maintenance/backup?components=io,mmpSettings,
accounts,networking,staticRoutes,firewall,time,nodeRed,sparkplug,clientSsl,files,usbSettings,bluetooth,
snmp,` with the key in an `apiKey` header and `verify=False`, saved to
`\\wz02163d\RioBackups\<Description>\<ip with dots as underscores>_<YYYY-MM-DD_HH-MM-SS>.zip`.

## Directory name → equipment coordinates

`<SITE>_<BUILDING>_<ROOM-FLOOR-BENCH>_<EQUIP>` — the **inverse token order** of the Ignition project name
for the same unit, so a mapping tool must reorder, not just re-delimit.

| Backup directory | Site | Bldg | Room-Floor-Bench | Equip | MQTT root | Ignition project |
|---|---|---|---|---|---|---|
| `LC_R8_320-3-1_TFF` | LC | R8 | 320-3-1 | TFF | `LC/R8/320-3-1/TFF/` | `TFF-R8-320-3-1` |
| `LC_R13_323-3-A_RX01` | LC | R13 | 323-3-A | RX01 | `LC/R13/323-3-A/RX01/` | `RX01-R13-323-3-A` |
| `ABC_B5_2071-2-1_TFF` | ABC | B5 | 2071-2-1 | TFF | `ABC/B5/2071-2-1/TFF/` | `TFF-B5-2071-2-1` |
| `AWA_B830_3S047-3-B_TFF` | AWA | B830 | 3S047-3-B | TFF | `AWA/B830/3S047-3-B/TFF/` | *(only the A bench exists in Ignition)* |
| `IRVINE_RD2_364-1_3CM` | IRVINE | RD2 | 364-1 | 3CM | `IRVINE/RD2/364-1/3CM/` | `IRVINE_RD2_364-1_3CM` (the one identical pair) |
| `LC_R13_220-2-1_ULT01` | LC | R13 | 220-2-1 | ULT01 | `LC/R13/220-2-1/ULT01/` | *(none — feeds `LabFreezers`)* |

`IRVINE_RD2_TBD_LAI_lab` has the literal `TBD` in the bench slot; site can equal building
(`ABA_ABA_120-6_*`). Do not assume room-floor-bench is numeric.

## Node census — 17 devices, 3636 nodes

`python3 -c "import json,sys,collections;print(collections.Counter(n['type'] for n in json.load(open(sys.argv[1]))).most_common())" <flows.json>`

| Count | Type | Role |
|---|---|---|
| 919 | `function` | **The logic, and it dominates.** Scaling, serial-frame parsing, string→type coercion, building `msg.topic`. Node.js in ES5 style, not Jython. |
| 467 | `inject` | Timers: polling, `Heartbeat` (3 s), `IP_Address` (300 s), the one-shot that sets the topic prefix, and dynamic MQTT subscribes. |
| 451 | `debug` | Sidebar output. **205 still enabled.** |
| 433 | `mqtt out` | Publish. 287 `retain:"true"`, 40 `"false"`, **106 left as `""`**. |
| 304 | `mqtt in` | Subscribe; every `HMI_COM` command lands here. `datatype: "auto-detect"`. |
| 122 | `groov-io-write` | The actuator on the command path — a rack output or an MMP address. |
| 119 | `tab` | One per functional area (`Feed Balance`, `Recirc Pump`, `TM Pressure Valve`, `Misc`). `"disabled": true` makes the whole tab inert. |
| 73 | `serial-port` | Config node: one physical RIO serial channel. |
| 65 | `catch` | Per-tab error trap. Wire one — an error thrown in a `function` otherwise only reaches the log. |
| 63 | `serial request` | Write a command, wait for the reply on the same port. |
| 34 / 14 / 6 | `modbus-read` / `-write` / `modbus-client` | Modbus TCP to third-party controllers (pumps, CellKraft humidifier). |
| 33 / 21 | `groov-io-input` / `groov-io-read` | Scanned input (`scanTimeSec` + `deadband`, emits on change) vs one-shot read on demand. |
| 26 / 10 | `mqtt-broker` / `groov-io-device` | Config nodes. The latter is the local rack: `{"address":"localhost","msgQueueFullBehavior":"DROP_OLD"}`. |
| 26 / 7 | `serial in` / `serial out` | Instruments that stream unprompted (balances). |
| 34 / 3 / 1 / 32 | `junction` / `link out` / `link in` / `trigger` | `junction` is cosmetic, `link` actually crosses tabs; `trigger` is watchdogs and pulse stretching. |

Also 126 `comment`, `OpcUa-Item`/`OpcUa-Client` (39/7, only `LC_F3_309-3-1_HUM1`), `calculator`,
`buffer-array`, `easing`, `cpu`, `ip`, `random`, `switch`, `split`, `delay`, `gate`, `exec`, a vestigial
`ui_*` Dashboard tab. **No device uses subflows.** Contrib modules: `node-red-contrib-groov-io ~1.0.3`,
`node-red-node-serialport ~2.0.3`, `node-red-contrib-modbus ~5.43.0`, `-cpu`, `-ip`, `-calc`,
`-buffer-array`, `-easing`, `-simple-gate`, `-opcua`, `node-red-node-random`.

## The pipeline

Every flow is these two half-pipelines, repeated per point:

```
TELEMETRY  inject(poll) | serial in | groov-io-input | modbus-read
              → function  parse / scale / compute
              → function  set msg.topic from the prefix global
              → mqtt out  qos 0, retain true
COMMAND    mqtt in  <root>/HMI_COM/<Point>    (payload is ALWAYS a string)
              → function  coerce the string to the type the hardware needs
              → groov-io-write | serial request | modbus-write
              → mqtt out  readback on a DIFFERENT topic (AI / AO / DO / Calc_Val)
```

The topic is rarely typed into the `mqtt out` node — it is built in a `function`, and the coercion on the
way back in is equally stereotyped:

```javascript
var topic = global.get("MQTTPrefix");                    // telemetry: build the topic
msg.topic = topic + "SERIAL/WT-01 (Source Weight)";
return msg;

var pay = msg.payload;                                   // command: string -> boolean
if (pay == 'true')  { msg.payload = true;  }
if (pay == 'false') { msg.payload = false; }
return msg;

msg.payload = parseFloat(msg.payload);                   // command: string -> number, gated on mode
if (global.get("PIDSelected") == "Valve") { return msg; }   // falls off the end -> no message
```

That gate is the estate's idiom: **a `function` that ends without `return msg` emits nothing.** It is
intentional; do not "fix" it with a trailing return. The prefix is seeded at startup by an `inject` with
`once: true, onceDelay: 0.1` whose payload is the literal root (`"LC/R8/320-3-1/TFF/"`), feeding
`global.set("MQTTPrefix", msg.payload)`. Momentary commands are cleared RIO-side by echoing an empty
payload back to the retained command topic once the instrument confirms —
`if (msg.payload == "ZI") { msg.payload = ""; return msg; }` into an `mqtt out` on
`…/HMI_COM/ZeroFBalance`. `mqtt-integration` has the Ignition-side half.

**107 of the 304 `mqtt in` nodes carry no topic either** — they are dynamic subscriptions (`inputs: 1`)
driven by an `inject` whose `props` are `{"p":"action","v":"subscribe"}` plus a **JSONata** topic
`$globalContext('GlobalPath') & "HMI_COM/AgitatorMode"`. Deliberate, not a defect: it is how one flow is
retargeted by changing one prefix. But an empty `mqtt in` topic tells you nothing until you read the
upstream inject, and **grepping for a command topic string misses all 107.** Six devices use it:
`IRVINE_RD2_364-1_3CM` (38), `IRVINE_RD2_364-1_TFF` (25), `LC_R13_323-3-A_RX01` (24),
`LC_R8_320-3-1_RX01` (12), `LC_R8_320-3-2_TFF` (6), `IRVINE_RD2_364-1_FILTER` (2).

## `mqtt-broker` config node

All 26 broker configs across all 17 devices are the same, and all point at prod:

| Field | Value |
|---|---|
| `broker` / `port` | `10.94.132.35` / `"1883"` — **every device, every site** |
| `clientid` | `""` on all 26 |
| `protocolVersion` / `keepalive` / `cleansession` / `usetls` | `"4"` (MQTT 3.1.1) / `"60"` / `true` / `false` |
| `birthTopic` / `closeTopic` / `willTopic` | all `""` — **no Last-Will anywhere.** Liveness is the application `Heartbeat` topic. |
| `name` | `"Chariot MQTT"`, `"Chariot Broker"` or `""` — cosmetic and inconsistent |
| credentials | not in `flows.json`; user/password sit in `flows_cred.json` |

`clientid: ""` means Node-RED generates a random id per connection, which is why nothing flaps today. An
explicit id must be unique per device: a duplicate makes the broker drop the older session, and the two
devices then knock each other offline in a loop. Several devices carry 2-3 broker configs identical apart
from `name`; consolidating is safe but not urgent.

## `serial-port` config node

73 nodes, 22 distinct paths. `/dev/ttySerX.Y[.Z]` is a physical RIO serial module channel: `ttySer0.1.4` =
rack 0, module 1, channel 4; `ttySer0.2` is a single-channel module.

| baud | data | parity | stop | Count | Typically |
|---|---|---|---|---|---|
| 9600 | 8 | none | 1 | 34 | general instruments |
| 9600 | **7** | **even** | 1 | 18 | balances |
| 19200 | 8 | none | **2** | 13 | pressure / conductivity transmitters |
| 9600 / 19200 / 115200 | 8 | none | 2 / 1 / 1 | 3 / 3 / 2 | the remainder |

`out: "char"` and `newline: "\n"` on almost all (a few `"\r\n"`, `"\r"`, `"/"`); `bin: "false"`; `addchar`
is appended to outgoing writes — `""`, `"\r\n"`, `"\r"`, and the suspicious `"\r \n"` / `" \r\n"` with
stray spaces; `responsetimeout` is `1000` or `10000` ms, occasionally `500`. Flow control
(`dtr`/`rts`/`cts`/`dsr`) is `"none"` everywhere. **Malformed paths exist:** `/dev/ttySer0.:1.2`,
`/dev/ttySer0.4:1.3`, `/dev/ttySer0.3:1.1`, `/dev/ttySer02`, plus one `/dev/ttyUSB0`. A colon is not valid
in this scheme, so those nodes cannot be opening a port. Treat them as dead branches — and check whether
the point they were meant to serve is published at all before "fixing" one.

All three `groov-io-*` nodes take `device` (the `groov-io-device` config id) and a `dataType` that selects
addressing: `channel-digital` and `channel-analog` use `moduleIndex` + `channelIndex` (a discrete point, or
a 4-20 mA / 0-10 V point); `mmp-address` uses `mmpAddress` (`"0xF0D81000"`), `mmpType` (`int32`/`float`)
and `mmpLength` for PID blocks, scratchpad, and anything that is not a plain channel — **57 of the 122
writes**. `groov-io-write` almost always has `value: ""` and `valueType: "msg.payload"`, so it writes
whatever the upstream `function` produced; `groov-io-input` adds `scanTimeSec` (`"1.0"`), `deadband`
(`"0.1"`–`"1"`) and `sendInitialValue: true`.

## Real defects to expect, and not to copy

- **`mqtt out` with an empty `topic` — 71 nodes on 9 of the 17 devices** (`IRVINE_RD2_364-1_TFF` 39,
  `IRVINE_RD2_364-1_3CM` 13). They publish to whatever `msg.topic` the upstream function set, which works
  until the prefix global is missing — then `undefined + "SERIAL/PT-01"` publishes to
  `undefinedSERIAL/PT-01`. **This is how prod's `undefined` topic roots were created.** The prefix is set by
  a one-shot `inject` with `onceDelay: 0.1`, so anything publishing in the first 100 ms after a restart goes
  to `undefined…`. Guard it: `if (!topic) { node.error("MQTT prefix unset", msg); return null; }`
- **Three names for the same global:** `GlobalPath` (78 uses), `MQTTPath` (74), `MQTTPrefix` (27), plus one
  `GlobalPath2` (a second equipment root, `RX02`, on the RX01 device). No convention — grep all four before
  concluding a flow has no prefix.
- **`qos: ""` on 279 of 433 `mqtt out` nodes, `retain: ""` on 106.** Node-RED reads empty as QoS 0 and
  retain false, so those 106 are **not** retained and their Ignition tags come back empty after a gateway
  restart until the next publish. Check this first when a tag is blank after a restart.
- **205 enabled `debug` nodes** on 1 s scan loops. Disable them before handing a flow back; leave `catch`.
- **Cloned flows keep the donor bench's topics.** `IRVINE_RD2_364-1_3CM` and `IRVINE_RD2_364-1_FILTER` both
  carry `mqtt out` nodes for `LC/R8/133-1-5/Filter/SERIAL/PT-05..PT-08` and
  `LC/R8/133-1-5/PCTE/HMI_COM/FT01(Totalizer Out)` — a different **site**. They sit on a `Scilog` tab with
  `"disabled": true` (plus one node with `"d": true`), so they are dormant, but enabling that tab makes an
  Irvine RIO write to an Illinois bench. Live and unguarded: `LC_F3_309-3-2_TFF` has an **enabled**
  `mqtt in` on `LC/F3/309-3-1/TFF/HMI_COM/ZeroPBalance`, its neighbour's command topic, so zeroing one
  bench's balance zeroes the other's. **Topic prefix does not identify the publisher.** After cloning, diff
  the topic list against the intended root (script in the reference) and check `disabled`/`d` before calling
  a bad topic harmless.
- **A topic with no root at all:** `LC_R13_323-3-A_RX01` has an `mqtt out` whose topic is the literal
  `SERIAL/AG-01 (Agitator Status)`, creating a top-level `SERIAL` folder in MQTT Engine.
- **An API key is published retained in cleartext** to `<root>/API` by a two-line `function` on several
  devices. Raise it; do not extend the pattern.

## `flows_cred.json` and secrets

Node-RED keeps config-node credentials out of `flows.json`, keyed by node id, and encrypts the file when
`credentialSecret` is set in `settings.js` (an encrypted one is a single `{"$": "<hex>"}` key). **In this
estate it is not encrypted.** All 17 backups hold a plain object shaped
`{"<nodeId>": {"user": …, "password": …}, "<nodeId>": {"apiKey": …}}` — the MQTT broker login and a device
API key, in the clear, on a Windows share. `settings.js` is not in the backup, so no key is recoverable
from here either way. **Never print, paste, quote or commit the contents of `flows_cred.json`.** Report
only that it exists, which node ids carry which field names, and that it is unencrypted.
`accounts/auth.db` and the API keys hardcoded in `Backup Tool/*.py` are the same class of exposure.

## Deploying, from a host with access

The Node-RED Admin API, on a groov RIO under `https://<ip>/node-red`, authenticated with the groov Manage
API key in an `apiKey` header (self-signed cert — you must allow it).

| Route | Purpose |
|---|---|
| `GET /settings` | version, `httpNodeRoot`. The reachability + auth probe. |
| `GET /flows` + `Node-RED-API-Version: v2` | `{rev, flows:[…]}`. v1 returns a bare array. |
| `POST /flows` + `Node-RED-API-Version: v2` | body `{flows, rev}` — **the whole flow array**, not a delta. Returns the new `rev`. |
| `GET /nodes` / `GET /serialports` | installed modules and their types / discovered serial ports. |
| `POST /auth/token` | generic Node-RED `adminAuth` only: form-encoded `client_id=node-red-admin`, `grant_type=password`, `scope=*`, `username`, `password` → `access_token` for `Authorization: Bearer`. Probe `GET /auth/login` first; 404 means adminAuth is off. groov uses the `apiKey` header instead. |

The `Node-RED-Deployment-Type` header on `POST /flows` selects restart scope: `full` (every flow),
`flows` (only modified tabs — the estate default), `nodes` (only modified nodes), `reload`. Passing `rev`
gives optimistic concurrency — a stale `rev` is rejected — so **always `GET /flows` immediately before
`POST /flows`** and send back the rev you got.

`GET /flow/:id`, `POST /flow`, `PUT /flow/:id`, `DELETE /flow/:id` are the upstream single-tab routes and
are the right shape for touching one equipment tab. **I could not verify them from here** (1880
unreachable), and `Auto_NodeRed` does not use them — it reads and rewrites the full array. Confirm them
against the version in `GET /settings` first.

## Auto_NodeRed — the flow generator

`<Auto_NodeRed checkout>/` — "RIO Flow Automator": an Express + vanilla-JS SPA (1522 lines under
`lib/`, one runtime dependency, `express`) that generates and deploys flows from an equipment spec instead
of hand-wiring nodes in the editor.

```bash
cd <Auto_NodeRed checkout> && cp .env.example .env   # RIO_TOOL_TOKEN gates the API
npm install && npm start     # http://localhost:3000
./scripts/run.sh             # or Docker on host port 8090 (no compose plugin on this host)
```

| File | What it does |
|---|---|
| `server.js` | REST API + static host. `/api/*` needs an `x-tool-token`; the token is auto-generated and logged if unset on a non-loopback bind. |
| `lib/noderedClient.js` | Admin API client. `authType` is `apikey` (groov), `bearer` (adminAuth grant via `/auth/token`), `basic` or `none`. `insecureTLS` is opt-in. |
| `lib/flowBuilder.js` | `buildFlow(spec)` → node array; `mergeManagedTab()` replaces the tab with the same label and drops config nodes only it referenced, so redeploys are idempotent. |
| `lib/connectivity.js` + `protocols/` | Dependency-free Modbus/TCP read and raw MQTT CONNECT probe. **Probes run from the server host, not the RIO** — a device on the RIO's private LAN looks unreachable. |
| `lib/aiAssist.js` | Device auto-fill via the AbbVie Iliad LLM gateway. Returns `null` plus a "needs verification" flag rather than inventing register addresses; treat output as a draft. `data/samples/current-flows.json` is a real captured `GET /flows` v2 response, useful as an offline fixture. |

Routes: `POST /api/connection/test`, `/api/serialports`, `/api/flows/current`, `/api/flows/generate`,
`/api/test/connectivity`, `/api/flows/deploy` (**needs `confirm: true`; writes to the live device**),
`/api/ai/autofill`, CRUD on `/api/projects`. Deploy sends `Node-RED-Deployment-Type: flows` unless the spec
overrides it. Two caveats before pointing it at a bench: it emits `modbus-flex-getter`/`modbus-flex-write`
and `serial request` shapes, **not** the `groov-io-*` nodes this estate uses for rack I/O, so its output is
a start for a serial or Modbus instrument and not for RIO channels; and it stores project credentials as
plain JSON under `data/projects/`.

[references/flow-anatomy.md](references/flow-anatomy.md) has the `flows.json` object model, how `wires`
encodes the graph, a worked minimal flow, and a verified script that extracts a flow's publish and
subscribe topics: the contract with Ignition.
