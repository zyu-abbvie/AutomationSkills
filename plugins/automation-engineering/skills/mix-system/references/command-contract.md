# The mix command and readback contract

One transport in each direction. Commands leave Ignition as MQTT publishes to the `Chariot` server;
state comes back through the `[MQTT Engine]` tag provider on retained topics.

```
Perspective panel
      │  event handler
      ▼
project script  ──▶  system.cirruslink.engine.publish('Chariot', topic, payload, qos, retain)
                                                                                    │
                                                                                    ▼
                                                                              broker / device
                                                                                    │ retained
      panel bindings  ◀──  [MQTT Engine]<base>/<pump>/<param>  ◀────────────────────┘
```

`Chariot` is a **gateway-level MQTT server name**, configured outside `data/projects/` and present on
both gateways. Which physical broker it resolves to is gateway config — see the `mqtt-integration`
skill. This matters: see "the shared-Path hazard" in `instances.md`.

## The publish helper

```python
MQTT_SERVER = 'Chariot'

def publish(topic, value, qos=0, retain=True):
    system.cirruslink.engine.publish(MQTT_SERVER, topic, str(value).encode('utf-8'), qos, retain)
```

`LNP_opt`'s two copies differ slightly and are worth knowing about: `PumpControl.publishMQTT` encodes
to UTF-8 bytes like the above, while `ValveControl.publishMQTT` publishes a **bare `str`** without
encoding. Both wrap the call in `try/except` and return `(success, error_message)`; `LNP_418`'s does
not — a transport failure there propagates to the caller.

## Payload typing

**Everything on the wire is a string.** There are no numeric or boolean MQTT payloads in this family.

| Quantity | Wire form | Read back as |
|---|---|---|
| Flow / volume setpoint | `'58.667'` | string, parsed by the device |
| Pump verb | `'start'` / `'stop'` | — |
| `PU4` run | `'true'` / `'false'` | — |
| Pump status | — | `'1'` running, `'0'` stopped — **compare as strings** |
| Direction | `'false'` forward, `'true'` reverse | string |
| Valve state | `'0'` closed, `'1'` open | string |

Two consequences:

- `if status == 1:` never matches. `getPumpStatus` returns `result.value` unconverted and callers
  compare to `"1"` / `"0"`.
- **Direction is an inverted-looking string boolean:** `DIR_FORWARD = "false"`,
  `DIR_REVERSE = "true"`. Reading it as a Python bool makes forward truthy.

## Direction and sign

Setting reverse is two coupled operations, not one:

```python
publish(base + '/<PU>/PumpDirectionCommand', direction)      # 'true' | 'false'
signedFlow = -abs(flowRateValue) if direction == DIR_REVERSE else abs(flowRateValue)
publish(base + '/<PU>/PumpFlowRateSP', signedFlow)
```

The direction topic alone does not reverse the pump — **the flow setpoint must also carry a negative
sign.** `setPumpDirection(..., updateFlowRate=True)` does both; with `updateFlowRate=False` you get a
direction flag that disagrees with the signed setpoint.

`setVolume` reads the *current* `PumpDirectionCommand` back off the tag and signs the volume to match,
so volume inherits direction rather than taking it as an argument.

## QoS and retain

| Class | QoS | Retain | Why |
|---|---|---|---|
| Flow/volume setpoints, `PU1` `PU2` `PU4` | 0 | **true** | Panel and historian read them back; last value wins. |
| Flow setpoint, `PU3` | **1** | true | `SP_QOS = {'PU1': 0, 'PU2': 0, 'PU3': 1, 'PU4': 0}`. Carried over verbatim from the original handlers. The source warns the Node-RED bridge in front of the Levitronix may depend on it — **confirm before changing.** |
| Ratio / compensate context | 0 | true | Recipe context for historian recall. |
| Pump verbs (`PumpCommand`) | **1** | **false** | `VERB_QOS = 1`: "a dropped start or stop is a process/safety event, and every command in this project is idempotent so redelivery is harmless." |
| `PU4` run boolean | 0 | **false** | Same reasoning as verbs. |
| Valve states (`LNP_opt`) | 0 | true | — |

**Never publish a command retained.** A retained `'start'` re-delivers to any subscriber that
reconnects, including after a device power cycle.

## Topic map — `LNP_418` (convention A)

Base is `Site + '/' + Path` = `LC/R13/418-1-1/LNP`.

```
FLOW_SP_TOPIC = {
    'PU1': '/PU1/PumpFlowRateSP',
    'PU2': '/PU2/PumpFlowRateSP',
    'PU3': '/PU3/PumpFlowRateSP',
    'PU4': '/PU4/HMI_COM/SP01 (Setpoint)',
}
VOLUME_SP_TOPIC = {
    'PU1': '/PU1/PumpVolumeSP',
    'PU2': '/PU2/PumpVolumeSP',
}
PU4_RUN_TOPIC   = '/PU4/HMI_COM/DI(Pump On Off)'
verbs           = '/<PU>/PumpCommand'
recipe context  = '/PU1/Ratio', '/PU1/Ratio_D1', '/PU1/Ratio_D2', '/PU1/Compensate'
```

Only `PU1` and `PU2` have volume setpoints — they are the dosing legs. `PU3` and `PU4` run
continuously as quench and take flow only.

### Readback topics seen in `LNP_418` views

```
/PU1/PumpFlowRate               actual flow, mL/min
/PU1/PumpStatus                 '1' | '0'
/PU1/PumpStatusText             human-readable state
/PU1/PumpPressure               pump pressure
/PU1/ActualVol                  dispensed volume
/PU1/PumpInitializationStatus   init state
/PU1/PumpInitializeCommand      init trigger
```

`getActualFlowRate` deliberately **returns `0.0` when the pump reads stopped**, rather than the last
retained flow, so a stopped pump does not display a stale non-zero rate. A displayed `0.0` therefore
means "stopped or unreadable", not necessarily "flow is zero" — it also returns `0.0` on bad quality
and on exception.

## The `HMI_COM` dialect

`PU4` (and `PU04`, `PC01`, `PU02` on other instances) sits behind an `HMI_COM` block instead of taking
verbs directly:

```
/PU4/HMI_COM/DI(Pump On Off)     'true' | 'false'    run / stop
/PU4/HMI_COM/SP01 (Setpoint)     numeric string      flow setpoint
/PU4/HMI_COM/FeedMaxFlowRate     numeric string      tubing-dependent ceiling (read-only)
```

**These topic names contain spaces and parentheses.** `SP01 (Setpoint)` has a space before the
parenthesis; `DI(Pump On Off)` does not. They are not interchangeable and neither is guessable — copy
them exactly. Anything that URL-encodes, trims or normalises a topic string will break them.

`LNP_opt`'s `buildMQTTTopic` special-cases this by string membership:

```python
if pumpId == "PC01" and "HMI_COM" in parameter:
    return basePath + "/HMI_COM/" + parameter
```

so the *parameter* argument carries the `HMI_COM` marker rather than the function knowing which pumps
use the dialect. Passing `"HMI_COM/SP01 (Setpoint)"` for a non-`PC01` pump silently produces the wrong
topic.

## Topic-name drift between instances

The same physical quantity has different topic names on different benches. Probe before binding:

| Quantity | Names observed |
|---|---|
| Flow setpoint | `PumpFlowRateSP` · `FlowRateSP` · `FlowRateWrite` (`LNP_opt`) · `SP01 (Setpoint)` (`HMI_COM`) |
| Syringe diameter | `Pump_Diameter` · `PumpDiameter` |
| Flow units | `Pump_FlowUnits` · `PumpFlowUnits` |
| Volume setpoint | `PumpVolumeSP` · `Pump_VolumeSP` (`PU04`) |
| Dispensed volume | `ActualVol` · `DispensedAmount` (`LNP_opt`) |
| Dilution ratio | `Ratio_D1` / `Ratio_D2` · `Ratio_D` |

**`LNP_beta` carries both spellings of three of these at once** (`Pump_Diameter` and `PumpDiameter`,
`Pump_FlowUnits` and `PumpFlowUnits`, `FlowRateSP` and `PumpFlowRateSP`). Only one is live. Watch the
broker to find out which:

```bash
MQTT_HOST=10.94.132.35 ${CLAUDE_PLUGIN_ROOT}/bin/mqtt-probe watch 'LC/R13/228-1-1/LNP/#' --seconds 20
```

## Valve topics (`LNP_opt` only)

Valves hang off the **room**, not the LNP path — a different base from every pump on the same bench:

```python
topic = "{}/{}/{}/MF/{}".format(session.custom.Site,
                                session.custom.Building,
                                session.custom.RoomFloorBench,
                                valveName)
```

`MF` is the microfluidics subsystem. Valve names: `Inner_Valve`, `Outer_Valve`, `Waste_Valve`.

```
PRODUCT   Inner 0   Outer 0   Waste 0
CLEAN     Inner 0   Outer 0   Waste 1
REFILL    Inner 1   Outer 1   Waste 0
```

`setValveMode` writes all three with a **50 ms `sequentialDelay` between commands "to prevent driver
overload"**, skipping the delay after the last valve. `PRODUCT` and `CLEAN` differ only in `Waste_Valve`.

Two caveats:

- The delay is implemented as `system.util.invokeLater(lambda: None, delay)`, which **schedules an
  empty callback and returns immediately** — it does not block the publishing loop. The three valve
  publishes are effectively back-to-back regardless of `sequentialDelay`. If real spacing matters,
  this needs `invokeAsynchronous` with a `time.sleep`, as `LNP_418` does for its start stagger.
- `setValveMode` collects per-valve errors and returns them all, but **does not roll back** valves that
  succeeded. A partial failure leaves the manifold in a mixed state.

## Ordering: `start_all`

```python
def run():
    publish(root + '/' + first  + '/PumpCommand', 'start', VERB_QOS, False)
    if delay > 0:
        time.sleep(delay)
    publish(root + '/' + second + '/PumpCommand', 'start', VERB_QOS, False)
    publish(root + '/PU3/PumpCommand',            'start', VERB_QOS, False)
    publish(root + PU4_RUN_TOPIC,                 'true',  SP_QOS['PU4'], False)

system.util.invokeAsynchronous(run)
```

Quench is issued **inside** the async sequence so the order is deterministic. The docstring records the
bug this fixed: quench was previously published synchronously alongside an async mix start, so it led
the mix pumps whenever `compensate` was non-zero. Preserve this if you refactor.

`stop()` sends each command in its own `try`, so one transport failure cannot leave the remaining pumps
running; it reports `'STOP FAILED for … - stop at the pump.'` and returns `False`.
