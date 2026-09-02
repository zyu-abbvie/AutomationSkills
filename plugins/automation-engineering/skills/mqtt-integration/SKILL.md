---
name: mqtt-integration
description: Work with the MQTT layer that connects the Node-RED and groov RIO edge devices to Ignition - the topic namespace and its channel vocabulary, payload conventions, how a topic becomes an Ignition tag through MQTT Engine custom namespaces, how a command reaches a device and how it is acknowledged, retained-message and heartbeat semantics, and broker connectivity checks. Use when publishing or subscribing, when a tag fed by MQTT is missing or stale, when a setpoint or command does not reach equipment, or when designing the topic contract for new equipment.
---

# The MQTT layer

```bash
${CLAUDE_PLUGIN_ROOT}/bin/mqtt-probe check                        # reach + authenticate
${CLAUDE_PLUGIN_ROOT}/bin/mqtt-probe watch '#' --seconds 20 --summary   # topic census
${CLAUDE_PLUGIN_ROOT}/bin/mqtt-probe watch 'LC/R8/320-3-1/TFF/#' --seconds 15
```

Set `MQTT_HOST`, `MQTT_USERNAME`, `MQTT_PASSWORD` from `doc/credential.yaml`. Both brokers speak
MQTT 3.1.1 on 1883, no TLS.

## Which broker

| | Broker | Reality |
|---|---|---|
| **prod** | `10.94.132.35:1883` | **Every groov RIO field device publishes here.** This is where the estate lives. |
| **dev** | `10.72.167.253:1883` | No field device publishes here. Traffic is training rigs and bench experiments. |

**Consequence:** the dev gateway's `[MQTT Engine]` tag tree is **stale** — it was populated when dev
pointed at a different broker. A dev tag under `LC/F3/309-3-2/…` will read a value that has not
changed in months. Do not use dev MQTT tags to test whether equipment is alive.

## Topic namespace

Six levels, plain and human-readable. **This estate is not a Sparkplug estate.**

```
{SITE}/{BUILDING}/{ROOM-FLOOR-BENCH}/{EQUIP}/{CATEGORY}/{POINT}
 ABC  /   B5     /    2071-2-1      /  TFF  /  SERIAL  / PT-04 (TM Pressure)
```

Level 5 is a closed vocabulary and it encodes **direction**:

| Category | Direction | Contents |
|---|---|---|
| `HMI_COM` | **Ignition → device** | commands and setpoints |
| `SERIAL` | device → Ignition | readings from serial instruments |
| `AI` / `AO` / `DO` | device → Ignition | analog and discrete I/O readback |
| `Calc_Val` | device → Ignition | values computed on the RIO |
| *(none — at equipment root)* | device → Ignition | `Heartbeat`, `IP_Address`, `CPU (Usage)`, `CPU (Temp)`, `API` |

Topics legitimately contain **spaces and parentheses** — `WT-01 (Source Weight)`. Quote them
everywhere, and never build a topic by splitting on whitespace.

Sparkplug B **is** subscribed (`spBv1.0/#`) but carries almost nothing: 105 of prod's 3850 MQTT tags,
in two groupIds (`Domain-001`, `GroovRIO`). The `spBv1.0/STATE/<host>` retained messages you will see
are host-online flags, not data. There is **no UNS/ISA-95 layer** configured anywhere.

## Payloads

Bare JSON scalars, not objects:

```
LU/B56/12-1/Training/TP-01 (Temp probe)     29.272674560546875
LU/B56/12-1/Training/HMI_COM/Button_ON      true
IRVINE/RD3/2201/LAI_Lab/PU02/ControlModeCommand    MANUAL      ← plain text, not JSON
```

**Everything is published `retain: true`, QoS 0** (or an empty QoS string, which Node-RED also treats
as 0). Retain is what makes Ignition's tag tree survive a gateway restart — and it is also why a
stale command can re-fire (see below).

### Every MQTT tag is a String

**Every** tag created by the custom namespace has `dataType: "String"` — pressures, flows,
temperatures, pump states, all of them. Booleans arrive as the literal strings `'true'` / `'false'`.

You must coerce on the Ignition side. Do not assume a numeric comparison works, and do not write
`if tagValue:` against the string `'false'` — that is true.

## How a topic becomes a tag

One MQTT Engine custom namespace, `NonSparkplugTags`, subscribes to the **bare wildcard `#`**:

```bash
ign res list com.cirruslink.mqtt.engine.gateway/custom-namespace
```

Because the subscription is `#`, MQTT Engine **auto-creates a tag for every topic on the shared
broker** — including other teams' traffic. Dev carries a junk tag
`[MQTT Engine]spBv1_0/STATE/lofstkx` for exactly this reason.

Two environment differences that will bite you:

| | dev | prod |
|---|---|---|
| `writableTags` | `false` → tags are `readOnly: true` | `true` → tags are writable |
| `.` → `_` token sanitisation | a convert record exists (`spBv1.0` → `spBv1_0`) | **no convert records** — a literal `spBv1.0` folder would be created |
| Sparkplug commands | allowed | **blocked** (`BLOCKNODECOMMANDS=1`, `BLOCKCOMMANDS=1`) |

## Commands: Ignition → device

**Commands are not tag writes.** They are direct publishes from a Perspective event script or an SFC
chart:

```python
system.cirruslink.engine.publish(serverName, topic, payload, qos, retain)
```

The topic is built by concatenating Perspective session custom props:

```python
topic = self.session.custom.Site + '/' + self.session.custom.Building + '/' \
        + self.session.custom.RoomFloorBench + '/TFF/HMI_COM/Feed ON'
```

### Momentary commands delete their own retained message

A retained command re-fires every time the device reconnects. The estate's fix is to publish the
value retained and then **immediately publish an empty retained payload to the same topic**, which
deletes the retained message:

```python
system.cirruslink.engine.publish(server, topic, 'true', 0, True)   # fire
system.cirruslink.engine.publish(server, topic, '',     0, True)   # clear the retained copy
```

Omit the second publish and the pump restarts itself the next time the RIO reboots.

### Acknowledgement is a readback echo on a different topic

There is no ack on the command topic. The chain is:

```
Ignition publishes  …/TFF/HMI_COM/Feed ON = "true"
   → RIO `mqtt in` → string→bool function → groov-io-write (the actual output)
   → RIO publishes the achieved state on a SEPARATE readback topic (AI/AO/DO/Calc_Val)
   → MQTT Engine updates that tag → Perspective shows it
```

So "did my command land?" is answered by **reading the readback topic**, never by the command topic.
Confirm with `mqtt-probe watch` on both.

### Liveness is an application heartbeat, not MQTT Last-Will

`{equipment}/Heartbeat` is driven by a 3-second inject and published retained; `IP_Address`
republishes every 300 s. There is **no** Last-Will/Testament and no Sparkplug NDEATH in use for the
plain namespace. A device is "silent" when its Heartbeat stops advancing — which you cannot see from
a retained value alone, because the retained message persists after the device dies. Watch it change:

```bash
mqtt-probe watch 'LC/R8/320-3-1/TFF/Heartbeat' --seconds 12
```

Two messages in 12 s means alive. One retained message and nothing after means dead.

## Known defects in the live namespace

These are real and present; do not replicate them, and expect to encounter them.

- **`undefined` topic roots, and their exact cause.** 17+ orphan tag roots exist in prod:
  `undefinedHMI_COM/TCU1/FB-01 (On)`, `undefinedSERIAL/Huber/TT-01`, `undefinedHeartbeat`,
  `undefinedAPI`. The mechanism is specific: each RIO holds its topic prefix in a Node-RED **global**,
  seeded once at deploy by an `inject` node with `onceDelay: 0.1`, and function nodes build every
  topic as `global.get(<prefix>) + '/…'`. If that inject has not fired, or the flow reads a different
  name than the one it set, `global.get` returns `undefined` and JavaScript concatenates the *text*
  `"undefined"`. The estate uses **four different names for the same global** — `GlobalPath` (140
  references), `MQTTPath` (78), `MQTTPrefix` (33), `GlobalPath2` (13) — which is what makes the
  mismatch easy. **Check which name a flow sets before you read one, and validate the prefix is
  non-empty before publishing.**
- **Leaked Ignition tag paths.** Topics such as `[default]P1/2-2-2/Training/Reactor Size` exist —
  someone published using an Ignition tag path as the topic string.
- **Cross-bench subscriptions from cloned flows.** The `309-3-2` flow subscribes to
  `LC/F3/309-3-1/TFF/HMI_COM/ZeroPBalance` — a *different* bench's command topic. Cloning a flow
  between rooms without rewriting every topic makes two benches command each other.
- **Two different concatenation schemes** address the same physical device, because `custom.Building`
  and `custom.RoomFloorBench` are split differently in different parent projects. Check what the
  parent actually sets before composing a topic.
- **Inconsistent casing and a site typo:** `LAI_Lab` (50 tags) vs `LAI_lab` (16) vs `LAI_Clinic`;
  `PolarBear` vs `polarbear`. Match the existing string exactly rather than normalising it.
- **A secret is published retained in cleartext.** A Node-RED function publishes an API key as a
  plain retained payload to a `…/TFF/API` topic, and the same value sits unencrypted in the flow
  backups. Treat broker traffic as readable by anyone on the network; do not add more of this, and
  raise it rather than quietly copying the pattern.

## Designing the topic contract for new equipment

1. Take the coordinates from the equipment name — `TFF-R8-320-3-1` → `LC/R8/320-3-1/TFF`.
2. Telemetry goes under `SERIAL`, `AI`, `AO`, `DO` or `Calc_Val`; commands under `HMI_COM`.
3. Name points after the P&ID tag with the description in parentheses: `PT-04 (TM Pressure)`.
4. Publish telemetry retained at QoS 0. Publish momentary commands retained, then clear them.
5. Give every command a distinct readback point — the command topic is not the state.
6. Add `Heartbeat`, `IP_Address`, `CPU (Usage)`, `CPU (Temp)` at the equipment root.
7. Verify with `mqtt-probe watch '<SITE>/<BLDG>/<ROOM>/<EQUIP>/#'` before wiring Ignition to it.

## Gateway-side configuration

```bash
ign res singleton com.cirruslink.mqtt.engine.gateway/general      # engine knobs
ign res list      com.cirruslink.mqtt.engine.gateway/server       # broker connections
ign res list      com.cirruslink.mqtt.engine.gateway/custom-namespace
ign res list      com.cirruslink.mqtt.engine.gateway/default-namespace
```

`list` is only valid for multi-instance types; `general` and `namespace-file` are singletons.

Birth/death knobs are identical on both gateways: `enableBdSeqChecking: true`,
`metricTimestampValidation: true`, `rebirthDebounceDelay: 5000`, `enableLatching: false`.

**MQTT Transmission** is installed on dev only and is a pristine placeholder (`groupId: "My MQTT
Group"`, `edgeNodeId: "Edge Node c15cf6"`) that publishes nothing. Do not cite it as the command
path — the command path is `system.cirruslink.engine.publish`. Ignition 8.3 **Event Streams** are a
second, newer publish path present on dev only.

## Client id

A duplicate client id makes the broker disconnect the older session, which presents as a flapping
device. `mqtt-probe` generates a unique id per run. When configuring a real client, make the id
identify the host and the purpose.

## One publisher on this broker is not a groov RIO

The PAT particle-sizing rig publishes under **`pat/psd/…`**, which does not follow the estate's
`SITE/BUILDING/ROOM-BENCH/EQUIP/CATEGORY/POINT` namespace at all — it is a flat, instrument-owned tree
with retained bare-float leaves (`…/d50`, `…/span`) beside JSON payloads, plus a QoS-1 retained
`…/status` with a Last-Will. It also carries a per-reading **`valid`** flag that a consumer is required
to honour by holding its last good output. Dev has two `pat/psd` tags provisioned and nothing reading
them. See the `pat-psd` skill before binding anything to that tree.
