# The TFF instrument layer on the groov RIO

The device end of the TFF platform: which instrument is on which serial port, how weight becomes flow,
how a command from Ignition reaches a pump, and which published topic feeds which tag. Measured on
`LC_F3_309-3-2_TFF` (270 nodes, backup 2026-03-18), diffed against `LC_R8_320-3-1_TFF` and
`ABC_B5_2071-2-1_TFF`.

> **Paths in this document.** `$DEV` and `$PROD` are the `projects/` directories inside an Ignition
> gateway backup; `$NODERED` is a directory of groov RIO device backups. Set them to wherever you
> keep yours, or put `backups_dir` / `nodered_backups_dir` in `automation.local.yaml`.

```bash
${CLAUDE_PLUGIN_ROOT}/bin/nr-inspect devices $NODERED/LC_F3_309-3-2_TFF/*.zip   # serial + groov I/O
${CLAUDE_PLUGIN_ROOT}/bin/nr-inspect topics  $NODERED/LC_F3_309-3-2_TFF/*.zip   # the MQTT contract
${CLAUDE_PLUGIN_ROOT}/bin/nr-inspect lint    $NODERED/LC_F3_309-3-2_TFF/*.zip
unzip -o -q $NODERED/LC_F3_309-3-2_TFF/*.zip -d /tmp/tff node-red/flows.json    # read it yourself
```

There is no PLC. A groov RIO runs Node-RED, talks to instruments over six serial ports and to its own
I/O module via `groov-io-*` nodes against `groov-io-device address: localhost`, and publishes to the
**prod** broker `10.94.132.35:1883` (`mqtt-broker` node `Chariot Broker`, MQTT 3.1.1,
`cleansession: true`, **`willTopic`/`birthTopic` empty — no Last-Will**). Every number on a TFF screen
is a string that came off one of these ports.

## Tab layout

Nine live tabs, one empty — platform-standard. `LC_R8_320-3-1_TFF` has the same nine plus a disabled
`Flow Meter`; `ABC_B5_2071-2-1_TFF` has the same functions with `Misc` deleted, its housekeeping nodes
moved onto `Pressure PID`, plus a 3-node `pH Monitor`.

| Tab | Nodes | Owns |
|---|---|---|
| `Misc` | 17 | `global.MQTTPrefix` seed, Heartbeat, IP_Address, CPU usage + I/O board temp, the API-key publish |
| `Scilog` | 43 | all three `serial in` ports: PT-01…PT-04, CT-02, CT-03, TT-02, TT-03. **Every publish here is dynamic-topic** |
| `Feed Balance` | 26 | WT-01 poll over MT-SICS, `Calc_Val/FT-01`, `ZeroFBalance` |
| `Permeate Balance` | 25 | WT-02 poll over MT-SICS, `Calc_Val/FT-02`, `ZeroPBalance` |
| `Feed Pump` | 32 | `Feed ON` / `Feed Direction` / `Feed Set Speed` → groov DO+AO, speed readback |
| `Recirc Pump` | 37 | `Recirc ON` / `Direction`, AO speed, `Calc_Val/PU-02 (Speed)`, pump-side PID output |
| `Pressure PID` | 20 | the RIO's built-in PID **loop 0** when TMP is controlled by the recirc pump |
| `TM Pressure Valve` | 24 | the RIO's built-in PID **loop 1** when TMP is controlled by the pinch valve |
| `Stirrer` | 28 | IKA overhead stirrer over NAMUR, `AG-01` status + PV |
| `Flow 2` | 0 | empty. Present on this device only; delete-safe |

## Serial ports and what is on them

Resolved by following the `serial` id from each node to its config node and reading the downstream
function names — not guessed.

| Port | Baud | Data/Parity/Stop | Node | Instrument | Evidence |
|---|---|---|---|---|---|
| `/dev/ttySer0.1.1` | 19200 | 8N2 | `serial in` | SciLog retentate conductivity/temperature probe | `split` on `,` → `parts.index` 1→`CT-02 (Retentate Conductivity)`, 2→`TT-02` |
| `/dev/ttySer0.1.2` | 19200 | 8N2 | `serial in` | SciLog permeate conductivity/temperature probe | index 1→`CT-03 (Permeate Conductivity)`, 2→`TT-03` |
| `/dev/ttySer0.1.3` | 19200 | 8N2 | `serial in` | SciLog 4-channel pressure monitor | index 1→`PT-01 (Feed)`, 2→`PT-02 (Retentate)`, 3→`PT-03 (Permeate)`, 4→`PT-04 (TM)` |
| `/dev/ttySer0.1.4` | 9600 | **7E1** | `serial request` | IKA overhead stirrer, NAMUR protocol | tab comment lists the full NAMUR set; traffic is `IN_PV_4`, `OUT_SP_4`, `START_4`, `STOP_4` |
| `/dev/ttySer0.1.5` | 9600 | 8N1 | `serial request` | Mettler-Toledo **source/feed** balance, MT-SICS | polled `SI`, response parsed for `S S`/`S D`, published as `WT-01 (Source Weight)` |
| `/dev/ttySer0.1.6` | 9600 | 8N1 | `serial request` | Mettler-Toledo **permeate** balance, MT-SICS | same, published as `WT-02 (Permeate Weight)` |

All six use `newline: "\n"` and `out: "char"` — responses split on LF. Two knobs differ and both
matter. **`responsetimeout`** is `1000` ms on the SciLog ports and the IKA but **`10000` ms on both
balance ports**, so a balance that stops answering blocks its 1 Hz poll queue for ten seconds.
**`addchar`** is `"\r\n"` on the IKA port only, and the Stirrer function *also* appends `" \r\n"`, so
the IKA receives `IN_PV_4 \r\n\r\n`; the balance ports set `addchar: ""` and depend entirely on their
function appending `"\r\n"`.

Port *numbering* is not platform-standard. `LC_R8_320-3-1_TFF` matches F3 exactly; `ABC_B5_2071-2-1_TFF`
uses `ttySer0.3`, `ttySer0.3:1.1`, `ttySer0.4:1.3`, `ttySer0.1.3/.1.4/.1.6` for the same six instruments
and runs its pressure port at 9600 8N2. **Never carry a port name between benches.**

## The balances (MT-SICS)

Three commands, platform-wide. There is **no tare, no stable-zero `Z`, no unit query** — the parser
assumes grams.

| Command | Origin | Meaning |
|---|---|---|
| `SI` | `inject` "SI" (`once`) → `trigger` `duration: "-1000"` — a negative duration means *resend until reset*, so this is a **1 Hz free-run poll** | Send weight Immediately, stable or not |
| `ZI` | Ignition. SFC / Perspective does `system.cirruslink.engine.publish('Chariot', <prefix>+'HMI_COM/ZeroPBalance', 'ZI', 0, True)` then republishes `""` | Zero Immediately |
| `I3` | a manual `inject` (`once: false`) — an engineer's button in the Node-RED editor | Balance data / firmware version |

Request cycle, per balance:

```
trigger(1 Hz) → function: msg.payload = msg.payload + "\r\n"
              → serial request  (own port, 10 s timeout, FIFO queue)
              → function: drop responses containing "ES" or "ZI", or null
              → function "Trim wt response"  → [ WT-xx publish , flow value ]
```

Response parsing, verbatim from node `Trim wt response` (identical on both balance tabs):

```javascript
var sts = msg.payload;
if(sts.includes('S S')) {                          // stable
    var s  = sts.indexOf('S', sts.indexOf('S') + 1);
    var wt = sts.indexOf('g');                     // assumes the unit is grams
    msg.payload = sts.slice(s + 1, wt - 1).trim();
}
else if(sts.includes('S D')) { /* same slice, between 'D' and 'g' — dynamic/unstable */ }
```

**Both stable and unstable readings are published identically** — nothing downstream knows whether a
weight was settled, which is deliberate for a flowing process but means a swinging vessel shows up as
flow. What a bad read produces, verified against `node-red-node-serialport@2.0.3` `25-serial.js`:

| Case | What the node emits | Net effect |
|---|---|---|
| **Total timeout** (10 s, zero bytes) | `dequeue()` does `delete msg.payload`, then emits `{status:"ERR_TIMEOUT", request_payload:"SI\r\n"}` | the next function calls `msg.payload.includes("ES")` on `undefined` → TypeError → swallowed by the tab's `catch` node → **no publish**. The Ignition tag holds its last retained value and goes stale silently. |
| **Partial response** then timeout | the buffered fragment is sent as `msg.payload` | neither `S S` nor `S D` matches, so the fragment is published **verbatim** to `SERIAL/WT-0x`, and `\|fragment − previous\|` produces a garbage flow spike |
| **MT-SICS error reply** (`ES` syntax, `ET`, `EL`) | normal data message | filtered out by `if (msg.payload.includes("ES")) { }` — silently dropped. `ET`/`EL` are **not** filtered and fall through to the partial-response path |

Overload/underload replies (`S +`, `S -`) and `S I` are also unhandled and would be published as text —
general MT-SICS knowledge, not something observed on this bench.

## The pressure path, and why PT-01's publish is dynamic

`serial in` on `.1.3` → trim → `split` on `,` → `switch` on `msg.parts.index` → per-channel trim →
`buffer-array bufferLen: 6, startWhenFilled: false` → `calculator operation: "avg", round: false` →
a **named function that sets the topic** → one shared `mqtt out` whose `topic` is `""`.

```javascript
// function node literally NAMED "SERIAL/PT-01 (Feed Pressure)"
var topic = global.get("MQTTPrefix");
msg.topic = topic + "SERIAL/PT-01 (Feed Pressure)";
return msg;                     // the mqtt out node downstream has topic: ""
```

All eight SciLog points (`PT-01`…`PT-04`, `CT-02`, `CT-03`, `TT-02`, `TT-03`) share **one** `mqtt out`
node, id `63973b95…`, with an empty static topic:

- A grep of `mqtt out` topics on this device returns 26 topics and **misses eight**, including the one
  that feeds the P1 pressure alarm. The point name only exists in the *function node's `name` field*.
  `nr-inspect topics` resolves these; a `jq` over `.[] | select(.type=="mqtt out") | .topic` does not.
- The node inherits Node-RED defaults for `qos` and `retain` (both `""`), i.e. QoS 0 **not retained**,
  unlike every static publish on the device which sets `retain: "true"`. After an Ignition restart these
  eight tags are empty until the next serial frame, while weights and flows come back instantly from
  their retained copies. Averaging is 6 samples unrounded — 6 *frames*, not 6 seconds.

Units come from the Ignition side, not the device: `psig` for PT (`TFF_Full_Display` labels
`PT-1 (psig)`, `PT-TM (psig)`), `uS/cm` for CT, `C` for TT — see the `columnNames` in
`$DEV/TFF_Parent/ignition/script-python/TFFReport/code.py`.

`PT-01` is the whole expression of `[default]F3/309-3-2/TFF/P1 Value`
(`{[MQTT Engine]LC/F3/309-3-2/TFF/SERIAL/PT-01 (Feed Pressure)}`), which carries the `AboveValue` alarm
bound to `P1_Max`. `PT-04` is also **re-subscribed by the RIO itself** on two tabs as the PID process
variable — a value that leaves the device and comes back through the broker.

## Flow: weight differentiated over time

The most important calculation on the device, and it is four lines inside the balance parser.

```javascript
var Foldvalue = flow.get('Foldvalue');   // previous weight, grams
var dens      = flow.get('density');     // g/mL, from HMI_COM/Density
var delta     = Math.abs(pl - Foldvalue);        // g per poll interval
var gpermin   = delta * 60;                      // 1 s poll ⇒ ×60 ⇒ g/min
var mlpermin  = gpermin / dens;                  // mL/min
mlpermin = Number(mlpermin.toFixed(2));
flow.set('Foldvalue', msg.payload);
```

| Step | Unit |
|---|---|
| MT-SICS `SI` reply, sliced → published as `SERIAL/WT-01` / `WT-02` | g (String on the wire) |
| `delta` — change since the previous poll | g per 1 s |
| `× 60` | g/min |
| `÷ density` | mL/min |
| `buffer-array bufferLen: 10, startWhenFilled: false` → `calculator avg, round: true, decimals: 2` → published as `Calc_Val/FT-01` / `FT-02` | mL/min, **rolling mean of the last 10 samples ≈ 10 s**, 2 dp |

**The `×60` hardcodes the 1 Hz poll.** Change the trigger's `duration` and every flow reading is wrong
by that ratio, with nothing to indicate it — there is no timestamp arithmetic anywhere in the chain.
And because `FT-02` is what `Flux` and `TimeToCompletion` consume, a 10-second lag and a 10-second
smear are baked into flux before Ignition touches it. When an operator says flux "reacts slowly", this
is why — do not go looking in the expression tag.

Startup asymmetries between the otherwise-identical tabs: `Feed Balance` seeds `flow.density = 1.2` and
`flow.Foldvalue = 0.0`; `Permeate Balance` seeds `flow.density = 1` and **does not seed `Foldvalue`**, so
its first poll after a deploy computes `Math.abs(weight - undefined)` → `NaN`, which enters the
10-sample buffer and makes `FT-02` publish `NaN` for ~10 s after every deploy or reboot. `1.2 g/mL` is
not water; both defaults are overwritten as soon as Ignition publishes `HMI_COM/Density`
(`$DEV/TFF_Parent/.../views/Docks/RecipeParametersLG/view.json`), but a bench that has never had a
recipe loaded computes feed flow 20 % low.

### `Calc_Val/PU-02 (Speed)` is not a flow meter

Despite sitting under `Calc_Val` next to the FT tags, `PU-02 (Speed)` is the **recirc pump's commanded
speed** in mL/min, derived from the RIO PID output, not measured. Two producers on `Recirc Pump`:

| Path | Gate | Calc_Val payload | groov AO payload |
|---|---|---|---|
| `HMI_COM/TMPressurePID_Out` → `speed->V` | `PIDSelected == "Pump" && PID_Active == "Auto"` | `(max/10) * (out/10)` mL/min | `out/10` |
| `groov-io-input` on MMP `0xF210000C` → function | `PID_Active == "Manual"` | `(max/10) * (raw/10)` mL/min | `(mL/min / 480) * 10` |

`max` is `global.RecircMaxFlowRate`, set from `HMI_COM/RecircMaxFlowRate`. **The Manual path hardcodes
`480`** where the Auto path uses the global, so unless that bench's max recirc flow is exactly
480 mL/min the pump is driven differently in Manual than in Auto. Correct is one scaling function
reading `RecircMaxFlowRate` in both branches.

Feed speed readback is the mirror image, on `Feed Pump`: 1 Hz `trigger` → `groov-io-read` analog module
0 channel 0 → `V->Speed` = `raw * 60.0 * g / 600.0` (i.e. `raw * g / 10`) → `AI/ST-01 (Feed Speed)`,
mL/min, 2 dp; `speed->V` = `sp / (max/10)` on the way in.

## The stirrer

IKA overhead stirrer, NAMUR ASCII over `.1.4` at 9600 **7E1**. The tab comment carries the vendor's
full command table; only four commands are wired.

| Direction | Traffic | Trigger |
|---|---|---|
| poll | `IN_PV_4` (read stirring speed) | `inject repeat: "1"` — 1 Hz |
| setpoint | `"OUT_SP_4 " + payload` | `mqtt in HMI_COM/StirrerSP` |
| start/stop | `START_4` / `STOP_4` | `mqtt in HMI_COM/StirrerON`, on the strings `true`/`false` |

`Trim response` takes `payload.trim().split(" ")[0]` and `Number()`s it — the IKA answers
`"<value> 4"`, so the trailing channel byte is discarded. Then it forks: `SERIAL/AG-01 (Agitator PV)`
gets the numeric speed in **rpm**, gated by `if (!Number.isNaN(msg.payload))`; `SERIAL/AG-01 (Agitator
Status)` gets `if (msg.payload < 1) "false" else "true"`.

**`AG-01 (Agitator Status)` is inferred from the speed reading, not read from the instrument.** A
stirrer commanded on but stalled at 0 rpm reports `"false"`, and so does one turning at 0.5 rpm. All
five SFC charts gate on it with a transition `tag("[MQTT Engine]"+{Site}+"/"+{Building}+"/"+
{RoomFloorBench}+"/TFF/SERIAL/AG-01 (Agitator Status)") = "true"`
(`$DEV/TFF_Parent/com.inductiveautomation.sfc/charts/TFF/Filter/sfc.xml:316`) — against the **string**
`"true"`, correct because every MQTT-Engine tag is `dataType: String`. `ABC_B5_2071-2-1_TFF` publishes
the Status but **not** the PV; do not assume the PV exists.

## The command receive path

Twenty distinct topics across 24 `mqtt in` nodes — `Density`, `TMPressurePID_Mode`, `TMPressurePID_SP`
and `SERIAL/PT-04` are each subscribed on two tabs. Every payload arrives as a **String**
(`datatype: "auto-detect"`, `rap: true`), so each subscription is followed by a coercion function.

| Subscribed topic | Coercion | Actuates |
|---|---|---|
| `HMI_COM/Feed ON` | `'true'`/`'false'` → bool | `groov-io-write` digital mod 0 ch 0 → publishes `DO/PU-01 (Feed ON)` |
| `HMI_COM/Feed Direction` | `'true'`/`'false'` → bool | digital mod 0 ch 8 → `DO/PU-01 (Feed Direction)` |
| `HMI_COM/Feed Set Speed` | `speed->V`, `/(max/10)` | analog mod 0 ch 7 → `AO/ST-01 (Feed Set Speed)` |
| `HMI_COM/Recirc ON` | `'true'`/`'false'` → bool | digital mod 0 ch 1 → `DO/PU-02 (Recirc ON)`; on `false` also writes PID output 0 and publishes `TMPressurePID_Mode = "Manual"` |
| `HMI_COM/Recirc Direction` | `'true'`/`'false'` → bool | digital mod 0 ch 9 → `DO/PU-02 (Recirc Direction)` |
| `HMI_COM/FeedMaxFlowRate`, `RecircMaxFlowRate` | none | `global.set(...)` — scaling constants only, no actuation |
| `HMI_COM/Recirc Set Speed` | `/max*100` | PID loop 0 output, MMP `0xF210000C`, when `PID_Active == "Manual"` |
| `HMI_COM/TMPressurePID_Selected` | none | `global.set("PIDSelected")` — `"Pump"` or `"Valve"`, the loop selector |
| `HMI_COM/TMPressurePID_Mode` | `"Auto"`→0, else 1 | PID mode, MMP `0xF2100054` (pump) / `0xF21000D4` (valve) |
| `HMI_COM/TMPressurePID_SP` | `parseFloat` | PID setpoint `0xF2100004` / `0xF2100084` |
| `HMI_COM/TMPressurePID_Out` | `speed->V` | recirc AO speed + `Calc_Val/PU-02 (Speed)` |
| `HMI_COM/PV Set Out` | pass-through, `/10` | valve AO position, analog mod 0 ch 4 → `AO/PV-01 (Pinch Valve)` |
| `HMI_COM/StirrerON` | `true`→`START_4`, else `STOP_4` | IKA serial write |
| `HMI_COM/StirrerSP` | prefix `OUT_SP_4 ` | IKA serial write |
| `HMI_COM/Density` | none | `flow.set('density')` on both balance tabs |
| `HMI_COM/ZeroFBalance` / `ZeroPBalance` | append `\r\n` | balance serial write; a second branch publishes `""` back to the same topic to delete the retained command |
| `SERIAL/PT-04 (TM Pressure)` | `parseFloat` | PID process variable `0xF2100000` / `0xF2100080`, gated on `PIDSelected` |
| `LC/F3/**309-3-1**/TFF/HMI_COM/ZeroPBalance` | — | **wired to a debug node only.** See defects |

**Dynamic subscriptions on this device: zero.** All 24 `mqtt in` nodes have `inputs: 0` and a literal
topic string, so here a static grep sees every subscription. The *machinery* for a dynamic one is
present as dead code — `Feed Balance` / `function 12` builds
`global.get("MQTTPrefix") + "HMI_COM/Density"` with `msg.action = 'subscribe'`, but its only wire goes
to the density setter, not to an `mqtt in`. That is **not** true platform-wide, and it is the trap:

| Device | `mqtt in` | dynamic (`inputs: 1`) | prefix global |
|---|---|---|---|
| `LC_F3_309-3-2_TFF` | 24 | **0** | `MQTTPrefix` |
| `LC_R8_320-3-1_TFF` | 24 | 0 | `MQTTPrefix` |
| `ABC_B5_2071-2-1_TFF` | 23 | 0 | *(none — fully static)* |
| `LC_R8_320-3-2_TFF` | 11 | **6** | `MQTTPrefix` |
| `IRVINE_RD2_364-1_TFF` | 25 | **25** | `MQTTPath` |

On `IRVINE_RD2_364-1_TFF` a static grep finds **no subscriptions at all**. Check `inputs` before
concluding a device does not listen for a command.

## The topic-prefix global

This device uses **`MQTTPrefix`** — 10 references, in `Misc` and `Scilog` plus the dead `function 12`.
Neither `GlobalPath`, `MQTTPath` nor `GlobalPath2` appears. Seeded once:

```
inject { payload: "LC/F3/309-3-2/TFF/", payloadType: "str", once: true, onceDelay: 0.1 }
   → function "Setting MQTT Path":  global.set("MQTTPrefix", msg.payload)
```

Note the **trailing slash** — consumers concatenate `"SERIAL/PT-01 (Feed Pressure)"` directly. If that
inject has not fired, or a hand-edited function reads a different name, `global.get` returns `undefined`
and JavaScript stringifies it, producing exactly the orphan roots seen in prod:

```
undefinedSERIAL/PT-01 (Feed Pressure)
```

That is one publish per SciLog frame into a topic tree nobody reads, while the real tag stops updating
and the RIO looks perfectly healthy. Guard before publishing:

```javascript
var topic = global.get("MQTTPrefix");
if (!topic) { node.error("MQTTPrefix unset", msg); return null; }
msg.topic = topic + "SERIAL/PT-01 (Feed Pressure)";
```

The prefix inject and the 26 static topic strings are the **only** two places per-bench identity is
encoded on the device; they must agree, and `nr-inspect lint` reports it when they do not.

## Housekeeping

| Topic | Source | Interval | Payload |
|---|---|---|---|
| `TFF/Heartbeat` | `inject` → `random low:1 high:1000 inte:true` | **3 s** | a random integer, retained |
| `TFF/IP_Address` | `inject` → `ip` node, `internalIPv4` | **300 s** | the RIO's LAN address, retained |
| `TFF/CPU (Usage)` | `inject` → `cpu` node, `msgOverall` | **5 s** | percent, retained |
| `TFF/CPU (Temp)` | same inject → `groov-io-read` MMP `0xF180D120` → `Convert to F` | **5 s** | I/O board temperature in **°F** — the node is named "IO Board Temperature", not the CPU die |
| `TFF/API` | `inject` (300 s, shared with IP_Address) → function `API KEY` | **300 s** | a 32-character opaque literal, retained in cleartext. Treat as a leaked credential; do not copy the pattern |

Heartbeat carries no information in its *value* — the consumer is a liveness check on its **timestamp**:
`if(datediff(tag("[MQTT Engine]" + … + "/TFF/Heartbeat.Timestamp"), Now(), "second") > 10, true, false)`
in `$DEV/TFF_Parent/.../views/Page/Embedded/Title/view.json:318`. 3 s publish, 10 s threshold — three
missed beats mark the bench offline, and with no MQTT Last-Will this timestamp is the *only* offline
signal.

## Confirmed defects on this device

1. **`WeightDelta` reads another bench.** `[default]F3/309-3-2/TFF/WeightDelta` sums
   `[MQTT Engine]LC/**AP31/299-4**/TFF/SERIAL/WT-02` + `.../WT-01` (read live from dev), so the
   scale-fail alarm on this skid watches a different room's balances. Correct is `LC/F3/309-3-2/…`; the
   fix belongs in the expression, not the flow.
2. **The pipeline both TFF alarms notify through does not exist.** `TFF_Parent/TFF_Alarms` has no
   `com.inductiveautomation.alarm-notification` folder on either gateway, so `P1 Value` and
   `WeightDelta` raise alarms that reach nobody.
3. **Cross-bench subscription.** `Permeate Balance` subscribes to
   `LC/F3/**309-3-1**/TFF/HMI_COM/ZeroPBalance`, wired to a debug node only — inert today, but wire it
   to anything and 309-3-1's operator zeroes 309-3-2's balance. `LC_F3_309-3-1_TFF`'s own flow is a
   35-node stub with zero MQTT nodes, so the publisher would be the `TFF-F3-309-3-1` Ignition child.
4. **`Pressure PID` never publishes `TMPressurePID_Out`.** The setter does
   `global.set("PIDSelected", …)`; the publish gate reads `flow.get("PIDSelected")`, never set at flow
   scope, so the test is `undefined == "Pump"` and every message is dropped. The `TM Pressure Valve`
   tab's equivalent gate correctly uses `global.get`. One-word fix — verify on a pump-controlled bench.
5. **`PID_Active` is written at two scopes inconsistently** — `Pressure PID` sets `flow` and `global`,
   `TM Pressure Valve` sets only `flow`, `Recirc Pump` reads only `global`. With
   `PIDSelected == "Valve"` the recirc tab gates on a value the valve tab never updated.
6. **The Manual recirc AO path hardcodes 480 mL/min** while the Auto path uses `RecircMaxFlowRate`.
7. **`TimeToCompletion` multiplies and then divides by `Density`** — the factor cancels exactly. A
   no-op, not a unit conversion. Verified in the live expression on dev.

## The whole contract on one screen

Published by the RIO → consumed by Ignition. `TFF_Full_Display`, `Charts` and `PID_Faceplate` live under
`$DEV/TFF_Parent/com.inductiveautomation.perspective/views/Page/`.

| Published topic (`LC/F3/309-3-2/TFF/…`) | Retain | Consumed by |
|---|---|---|
| `SERIAL/PT-01 (Feed Pressure)` *(dyn)* | no | `[default]…/TFF/P1 Value` expr → P1 alarm; `TFF_Full_Display`; `TFFReport` history |
| `SERIAL/PT-02 (Retentate Pressure)`, `PT-03 (Permeate Pressure)` *(dyn)* | no | `TFF_Full_Display`; `TFFReport` |
| `SERIAL/PT-04 (TM Pressure)` *(dyn)* | no | `PID_Faceplate`, `TFF_Full_Display`, `TFFReport`, **and the RIO itself** (PID PV, 2 subscriptions) |
| `SERIAL/CT-02`, `CT-03`, `TT-02`, `TT-03` *(dyn)* | no | `TFF_Full_Display`; `TFFReport` |
| `SERIAL/WT-01 (Source Weight)`, `WT-02 (Permeate Weight)` | yes | `TFF_Full_Display`; `TFFReport`; `WeightDelta` — *but from AP31/299-4, defect 1* |
| `Calc_Val/FT-02 (Permeate Flow)` | yes | `Flux`, `TimeToCompletion`, `TFF_Full_Display`, `Charts`, `TFFReport` — **the most consumed topic on the bench** |
| `Calc_Val/FT-01 (Feed Flow)`, `Calc_Val/PU-02 (Speed)`, `AO/PV-01 (Pinch Valve)` | yes | `TFF_Full_Display`; `TFFReport` |
| `SERIAL/AG-01 (Agitator Status)` | yes | transitions in all 5 SFC unit-operation charts |
| `DO/PU-01 (Feed ON)`/`(Feed Direction)`, `DO/PU-02 (Recirc ON)`/`(Recirc Direction)` | yes | `TFF_Full_Display` expression bindings; the direction-toggle script reads `PU-01 (Feed Direction)` before publishing |
| `HMI_COM/TMPressurePID_Out`, `TMPressurePID_Mode` | yes | `PID_Faceplate`; `_Out` is also re-subscribed by `Recirc Pump` |
| `HMI_COM/ZeroFBalance` / `ZeroPBalance` (`""`) | yes | nothing — the empty payload exists to delete the retained command |
| `Heartbeat` | yes | `Embedded/Title` offline flag, via `.Timestamp` |
| `SERIAL/AG-01 (Agitator PV)`, `AI/ST-01 (Feed Speed)`, `AI/ST-02 (Recirculation Speed)`, `AO/ST-01 (Feed Set Speed)`, `IP_Address`, `CPU (Usage)`, `CPU (Temp)`, `API` | yes | **nothing** — no reference anywhere in `TFF_Parent` on either gateway |
| `HMI_COM/Feed Set Speed`, `HMI_COM/StirrerSP` | yes | published only by manual test `inject` nodes left in the flow; harmless, but they can re-fire a setpoint on deploy |

Tags and bindings that expect a topic **nobody on this device publishes**:

| Expected by Ignition | Reality |
|---|---|
| `TFF/TCP/TT-01 (Process Temp)`, `TCP/TT-02 (Chiller Internal Temp)`, `TCP/TT-03 (Chiller Set Point)` | this RIO has no chiller integration at all, yet `TFF-F3-309-3-2` has `Chiller: true`. If the bench really has one, the publisher is another device — check the broker before touching the flow. `TCP` is also outside the documented category vocabulary |
| `Calc_Val/FT-03 (Recirc Flow)` | no flow meter on this bench (`LC_R8_320-3-1_TFF` has one, on a **disabled** `Flow Meter` tab behind Modbus) |
| `AI/PH-01 (pH Meter)` | fitted only on `B5-2071-2-1` and `R14-120-1-L` |
| `HMI_COM/Flux` | not a device topic. Ignition publishes its own `Flux` value here so the MQTT-Engine historian logs it, then reads it back. Device-side silence is correct |

## Verified here vs general knowledge

Verified against the backup and the live dev gateway: every tab, port, baud/parity, node id, function
body, interval, buffer length and topic string; the Ignition-side consumer of each topic; the
`ERR_TIMEOUT` behaviour, read out of the vendored `node-red-node-serialport@2.0.3` in the same backup;
the three-device comparison; all seven defects. Engineering knowledge only, **not** measured here: that
MT-SICS `SI` returns stable or dynamic weight and `ZI` zeros immediately; that `ES`/`ET`/`EL` are the
MT-SICS error classes and `S +`/`S -` the overload replies; that the NAMUR set is IKA's; that LMH is
`L·m⁻²·h⁻¹`. **No normal operating range in this document was measured from this estate** — no pressure,
flow, weight or rpm band here is a spec for any bench.
