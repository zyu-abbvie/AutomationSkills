# flows.json anatomy

`node-red/flows.json` is a **flat JSON array**. There is no nesting: tabs, subflows, wired nodes and
config nodes are all sibling objects in one list, and the structure is carried entirely by id
references. Every device in this estate stores it that way — 3636 objects across the 17 backups, the
largest single flow being `IRVINE_RD2_364-1_3CM` at 407.

```json
[
  { "id": "608a8bd55e5110b4", "type": "tab", "label": "Misc", "disabled": false, "info": "", "env": [] },
  { "id": "8d0683363050735e", "type": "mqtt-broker", "broker": "10.94.132.35", "port": "1883", … },
  { "id": "23c47a2f37cb1dd0", "type": "inject", "z": "608a8bd55e5110b4", … , "wires": [["4c60…"]] },
  … 
]
```

## The four kinds of object

| Kind | How to recognise it | Notes |
|---|---|---|
| **Tab** (flow) | `type: "tab"` | Has `label`, `disabled`, `info`, sometimes `env: []`. No `z`, no `wires`, no `x`/`y`. `disabled: true` means none of its nodes run — `LC_R8_320-3-1_TFF` has a disabled `Flow Meter` tab and `IRVINE_RD2_364-1_FILTER` a disabled `Scilog` tab. |
| **Subflow definition** | `type: "subflow"` | Has `in`/`out` arrays instead of `wires`. Its member nodes carry `z: <subflow id>`. An *instance* has `type: "subflow:<subflow id>"`. **No device in this estate uses subflows** — do not expect them. |
| **Wired node** | has both `z` and `wires` | The normal case: `function`, `inject`, `mqtt in`, `mqtt out`, `groov-io-write`, `switch`, `debug`, … |
| **Config node** | has **no `z`** and no `x`/`y`/`wires` | `mqtt-broker`, `serial-port`, `groov-io-device`, `modbus-client`, `tls-config`. Referenced by id from a property on the wired node: `broker`, `serial`, `device`, `server`. Deleting a config node without repointing its consumers breaks them silently. |

## Keys every wired node has

| Key | Meaning |
|---|---|
| `id` | 16 hex chars on modern nodes (`"8d0683363050735e"`), older ones are `"eb52473e.83e078"`. Both forms coexist in the same file. Must be unique across the whole array. |
| `type` | node type; for contrib nodes this is what `package.json` must provide |
| `z` | **id of the owning tab or subflow.** Absent on config nodes and tabs. |
| `name` | the editor label. Frequently `""`. On this estate the `function` node's `name` is often the topic suffix it builds (`"SERIAL/PT-04 (TM Pressure)"`) — useful, but not authoritative. |
| `x`, `y` | editor canvas coordinates. Cosmetic. Changing them is a real diff but has no runtime effect. |
| `wires` | the graph — see below |
| `d` | `true` = **this single node is disabled**, independently of its tab. Present on 29 nodes estate-wide (7 `mqtt out`, 7 `function`, 4 `inject`, 4 `modbus-read`, 2 `mqtt in`, 2 `modbus-write`, 1 each `OpcUa-Item`/`catch`/`debug`) and very easy to miss. |
| `g` | id of a `group` (visual grouping box). Cosmetic. |

## How `wires` encodes the graph

`wires` is an **array of output ports**, each port an **array of target node ids**:

```json
"wires": [ ["nodeA", "nodeB"], ["nodeC"] ]
```

- Port 0 sends to `nodeA` **and** `nodeB` — a fan-out. Both receive the *same message object*, so a
  downstream node that mutates `msg` affects the other branch. This is a real source of bugs.
- Port 1 sends to `nodeC`. A `function` reaches port 1 by returning `[msg1, msg2]` — the estate does
  this to write a value to `groov-io-write` and publish the readback in one node.
- `"wires": []` = a sink (`mqtt out`, `debug`). `"wires": [[]]` = one output port, nothing wired to it.
- Edges are **only** in `wires`. There is no reverse index; to find what feeds a node you must scan the
  whole array. A node whose id appears in nobody's `wires` and which is not an input node is dead code.

Only wired nodes participate. A `link out`/`link in` pair crosses tabs without a wire; `junction` is
purely visual and does not change routing.

## `function` node code

The code is a **single JSON string** in the `func` key, with real newlines escaped as `\n`:

```json
{
  "id": "80bd796c464dd38b", "type": "function", "z": "aec619bde17ca813",
  "name": "SERIAL/WT-01 (Source Weight)",
  "func": "var topic = global.get(\"MQTTPrefix\");\nmsg.topic = topic + \"SERIAL/WT-01 (Source Weight)\";\nreturn msg;",
  "outputs": 1, "noerr": 0,
  "initialize": "", "finalize": "", "libs": [],
  "x": 700, "y": 260, "wires": [["ed57591cc522316e"]]
}
```

- `outputs` must match the length of the array the code returns. Set `outputs: 2` and return
  `[msgA, msgB]` for the two-port pattern.
- `initialize` / `finalize` run on deploy and on stop. Empty on every node in this estate.
- `libs` is the npm-module import list for the node. Empty everywhere here.
- `noerr` is an editor artefact. Leave it. Newer Node-RED also writes `timeout` (present on 385 of the
  919 function nodes here); its absence is fine.
- Read code out of a flow without eyeballing escapes:

```bash
python3 -c "import json,sys;[print('###',n.get('name'),'\n'+n['func']) for n in json.load(open(sys.argv[1])) if n.get('type')=='function']" \
  /tmp/nr/LC_R8_320-3-1_TFF/node-red/flows.json
```

This is the Node-RED runtime — **Node.js, not Jython**. `node.warn`, `node.error(msg, msg)`,
`flow.get`/`flow.set` (per-tab), `global.get`/`global.set` (whole runtime), `context` (per-node). The
estate writes ES5: `var`, `==`, no arrow functions, no `let`. Match it.

## A minimal worked flow

One telemetry point published retained, and one command accepted, coerced and written to a rack
output, with the achieved state echoed on a separate readback topic. This is the whole estate pattern
in 9 objects. Ids here are placeholders — generate fresh 16-hex ids, and confirm none collide with an
existing node before merging.

```json
[
  { "id": "tab0000000000001", "type": "tab", "label": "Feed Pump", "disabled": false, "info": "" },

  { "id": "brk0000000000001", "type": "mqtt-broker", "name": "Chariot MQTT",
    "broker": "10.94.132.35", "port": "1883", "clientid": "", "protocolVersion": "4",
    "keepalive": "60", "cleansession": true, "usetls": false, "autoConnect": true,
    "birthTopic": "", "birthQos": "0", "birthPayload": "", "birthMsg": {},
    "closeTopic": "", "closeQos": "0", "closePayload": "", "closeMsg": {},
    "willTopic": "",  "willQos": "0",  "willPayload": "",  "willMsg": {},
    "userProps": "", "sessionExpiry": "" },

  { "id": "dev0000000000001", "type": "groov-io-device",
    "address": "localhost", "msgQueueFullBehavior": "DROP_OLD" },

  { "id": "inj0000000000001", "type": "inject", "z": "tab0000000000001", "name": "set topic prefix",
    "props": [{ "p": "payload" }], "payload": "LC/R8/320-3-1/TFF/", "payloadType": "str",
    "repeat": "", "once": true, "onceDelay": 0.1,
    "x": 140, "y": 60, "wires": [["fn00000000000001"]] },

  { "id": "fn00000000000001", "type": "function", "z": "tab0000000000001", "name": "Setting MQTT Path",
    "func": "global.set(\"MQTTPrefix\", msg.payload);\nreturn msg;",
    "outputs": 1, "noerr": 0, "initialize": "", "finalize": "", "libs": [],
    "x": 380, "y": 60, "wires": [[]] },

  { "id": "gii000000000001",  "type": "groov-io-input", "z": "tab0000000000001", "name": "Feed AI",
    "device": "dev0000000000001", "dataType": "channel-analog",
    "moduleIndex": "0", "channelIndex": "0",
    "mmpAddress": "", "mmpType": "float", "mmpLength": "1", "mmpEncoding": "ascii",
    "sendInitialValue": true, "deadband": "0.1", "scanTimeSec": "1.0",
    "x": 140, "y": 160, "wires": [["fn00000000000002"]] },

  { "id": "fn00000000000002", "type": "function", "z": "tab0000000000001", "name": "AI/ST-01 (Feed Speed)",
    "func": "var root = global.get(\"MQTTPrefix\");\nif (!root) { node.error(\"MQTT prefix unset\", msg); return null; }\nmsg.topic = root + \"AI/ST-01 (Feed Speed)\";\nreturn msg;",
    "outputs": 1, "noerr": 0, "initialize": "", "finalize": "", "libs": [],
    "x": 380, "y": 160, "wires": [["out000000000001"]] },

  { "id": "out000000000001",  "type": "mqtt out", "z": "tab0000000000001", "name": "",
    "topic": "", "qos": "0", "retain": "true", "broker": "brk0000000000001",
    "respTopic": "", "contentType": "", "userProps": "", "correl": "", "expiry": "",
    "x": 660, "y": 160, "wires": [] },

  { "id": "in0000000000001",  "type": "mqtt in", "z": "tab0000000000001", "name": "",
    "topic": "LC/R8/320-3-1/TFF/HMI_COM/Feed ON", "qos": "0", "datatype": "auto-detect",
    "broker": "brk0000000000001", "nl": false, "rap": true, "rh": 0, "inputs": 0,
    "x": 160, "y": 300, "wires": [["fn00000000000003"]] },

  { "id": "fn00000000000003", "type": "function", "z": "tab0000000000001", "name": "str->bool",
    "func": "var pay = msg.payload;\nif (pay == 'true')  { msg.payload = true;  }\nif (pay == 'false') { msg.payload = false; }\nvar readback = { payload: msg.payload, topic: global.get(\"MQTTPrefix\") + \"DO/PU-01 (Feed ON)\" };\nreturn [msg, readback];",
    "outputs": 2, "noerr": 0, "initialize": "", "finalize": "", "libs": [],
    "x": 420, "y": 300, "wires": [["giw000000000001"], ["out000000000001"]] },

  { "id": "giw000000000001",  "type": "groov-io-write", "z": "tab0000000000001", "name": "Feed ON",
    "device": "dev0000000000001", "dataType": "channel-digital",
    "moduleIndex": "0", "channelIndex": "6",
    "mmpAddress": "", "mmpType": "int32", "mmpLength": "1", "mmpEncoding": "ascii",
    "value": "", "valueType": "msg.payload",
    "x": 700, "y": 300, "wires": [[]] },

  { "id": "cat000000000001",  "type": "catch", "z": "tab0000000000001", "name": "",
    "scope": null, "uncaught": false, "x": 160, "y": 400, "wires": [["dbg000000000001"]] },

  { "id": "dbg000000000001",  "type": "debug", "z": "tab0000000000001", "name": "errors",
    "active": true, "tosidebar": true, "console": false, "tostatus": false,
    "complete": "true", "statusVal": "", "statusType": "auto",
    "x": 380, "y": 400, "wires": [] }
]
```

Notes on the above, all of them things the estate gets wrong somewhere:

- The `mqtt out` node's `topic` is `""` on purpose — one node serves both branches, and each upstream
  `function` sets `msg.topic`. **The guard in `fn…002` is the part the estate is missing**; without it a
  restart race publishes to `undefinedAI/ST-01 (Feed Speed)`.
- `retain: "true"` and `qos: "0"` are strings, not booleans/numbers. An empty string for either is
  accepted and means false / 0 — 106 nodes in the estate accidentally publish unretained that way.
- The command comes in as the **string** `"true"`, never a boolean. `if (msg.payload)` on `"false"` is
  true. Coerce first.
- The readback goes to `DO/PU-01 (Feed ON)`, **not** back to the `HMI_COM` topic. See
  `mqtt-integration` for why.

## Extracting the topic contract

The MQTT topic list is the interface between a RIO and Ignition, and it is only half-visible in
`flows.json`: 71 `mqtt out` nodes and all 107 dynamic `mqtt in` nodes have an empty `topic` field.
There are **three** ways a topic gets set, and a useful extractor must handle all three:

1. **Literal** — the `topic` field on the `mqtt out` / `mqtt in` node.
2. **`msg.topic` from a function** — `msg.topic = global.get("MQTTPrefix") + "SERIAL/PT-01"`.
3. **Dynamic subscription** — `mqtt in` with `inputs: 1` and no topic, fed by an `inject` whose
   `props` are `{"p":"action","v":"subscribe"}` plus a **JSONata** topic expression
   `$globalContext('GlobalPath') & "HMI_COM/AgitatorMode"`. All 107 empty-topic `mqtt in` nodes in the
   estate are this. They are correct, not broken.

```python
#!/usr/bin/env python3
"""List the MQTT topics a flows.json publishes and subscribes.

    python3 topics.py <flows.json> [expected-root]
    python3 topics.py /tmp/nr/LC_R8_320-3-1_TFF/node-red/flows.json 'LC/R8/320-3-1/'
"""
import json, re, sys, collections

path = sys.argv[1]
expect = sys.argv[2] if len(sys.argv) > 2 else None
nodes = json.load(open(path))
tabs_off = {n["id"] for n in nodes if n.get("type") == "tab" and n.get("disabled")}

# Topic prefixes: inject payloads that look like a root, and literal global.set() assignments.
# The estate uses three different global names -- GlobalPath, MQTTPath, MQTTPrefix -- so match any.
prefixes = set()
for n in nodes:
    if n.get("type") == "inject" and isinstance(n.get("payload"), str) \
       and n["payload"].endswith("/") and n["payload"].count("/") >= 3:
        prefixes.add(n["payload"])
    for m in re.finditer(r'global\.set\(\s*["\'][^"\']+["\']\s*,\s*["\']([^"\']+/)["\']',
                         n.get("func") or ""):
        prefixes.add(m.group(1))

upstream = collections.defaultdict(list)          # target id -> nodes feeding it
for n in nodes:
    for port in n.get("wires") or []:
        for tgt in port:
            upstream[tgt].append(n)

SUFFIX  = re.compile(r'msg\.topic\s*=\s*[^;\n]*?\+\s*["\']([^"\']+)["\']')
JSONATA = re.compile(r'\$globalContext\(\s*[\'"][^\'"]+[\'"]\s*\)\s*&\s*[\'"]([^\'"]+)[\'"]')

def resolve(node):
    if node.get("topic"):
        return [node["topic"]]                    # 1. literal on the node
    out = []
    for up in upstream[node["id"]]:
        for m in SUFFIX.finditer(up.get("func") or ""):          # 2. msg.topic in a function
            out.extend(p + m.group(1) for p in (prefixes or {"<PREFIX>/"}))
        for pr in up.get("props") or []:                         # 3. dynamic subscribe (JSONata)
            if pr.get("p") == "topic":
                for m in JSONATA.finditer(str(pr.get("v") or "")):
                    out.extend(p + m.group(1) for p in (prefixes or {"<PREFIX>/"}))
    return out or ["<UNRESOLVED msg.topic>"]

pub, sub = collections.Counter(), collections.Counter()
for n in nodes:
    if n.get("type") not in ("mqtt out", "mqtt in"):
        continue
    if n.get("z") in tabs_off or n.get("d"):      # disabled tab, or node-level "d": true
        continue
    for t in resolve(n):
        (pub if n["type"] == "mqtt out" else sub)[t] += 1

print("prefixes found:", sorted(prefixes) or "NONE")
for label, table in (("PUBLISH   (device -> Ignition)", pub),
                     ("SUBSCRIBE (Ignition -> device)", sub)):
    print("\n=== %s  (%d distinct)" % (label, len(table)))
    for topic, count in sorted(table.items()):
        flag = "   <-- CHECK BY HAND" if "<" in topic else \
               ("   <-- FOREIGN ROOT" if expect and not topic.startswith(expect) else "")
        print("  %dx  %s%s" % (count, topic, flag))
```

Verified output, zero unresolved on all four:

| Device | Prefixes found | Publish | Subscribe | Flagged |
|---|---|---|---|---|
| `LC_R8_320-3-1_TFF` | `LC/R8/320-3-1/TFF/` | 34 | 19 | — |
| `LC_R8_320-3-1_RX01` | `LC/R8/320-3-1/RX01/` | 12 | 11 | — |
| `IRVINE_RD2_364-1_3CM` | `IRVINE/RD2/364-1/3CM/` | 48 | 29 | — (cross-site topics are on the disabled `Scilog` tab) |
| `LC_R13_323-3-A_RX01` | `LC/R13/323-3-A/RX01/` **and** `…/RX02/` | 31 | 22 | rootless `SERIAL/AG-01 (Agitator Status)` |

Note that RX01 device: it carries two equipment roots, so the resolver emits both candidates for every
`msg.topic` suffix. Where a device has more than one prefix global, the output is a superset — read it
as "one of these", not "all of these".

The honest limits: a topic assembled across more than one `function` hop, or from an expression this
regex does not match, comes back `<UNRESOLVED msg.topic>` and must be read by hand — an unresolved
count is a signal to open the flow, not a clean bill of health. And this reports what the *flow*
declares, not what the broker actually sees. Confirm with
`${CLAUDE_PLUGIN_ROOT}/bin/mqtt-probe watch '<root>#' --seconds 20 --summary` from a host with broker
access.
