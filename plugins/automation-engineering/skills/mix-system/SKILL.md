---
name: mix-system
description: Work on a continuous-mixing skid in this estate - the LNP (lipid nanoparticle) mix systems and the LAI and MSP benches that reuse the same convention, the mRNA/lipid ratio and D1/D2 dilution setpoint maths, the pump flow and volume ceilings in mL/min, the Chariot MQTT command and readback contract with its retained-setpoint and QoS rules, the PU4 HMI_COM dialect, the PRODUCT/CLEAN/REFILL valve modes, and the naming and addressing traps that let one bench drive another. Use when reading or authoring anything on an LNP, LAI or MSP mix bench, when a pump setpoint reaches the device with the wrong value or not at all, when derived flows look wrong, when a command is ignored, when standing up a new mix instance from an existing one, or when asked what a mix tag or ratio actually means.
---

# The mix system

A continuous mix skid meets two or more liquid streams at a controlled ratio and immediately dilutes
the product to arrest the reaction. On the LNP benches an **mRNA (aqueous) stream and a lipid stream
meet at a fixed ratio**, and the mixer outlet is then quenched by two further dilution stages. The
same convention is reused, with different pump inventories, for LAI and for new MSP benches.

**This is a convention, not a platform.** Unlike `TFF_Parent`, there is no parent project and no
inheritance anywhere in the family: every instance has `parent: ""` and carries its own 75–92
resources. Two instances that look alike are alike because somebody copied one to make the other.
`LNP_beta` and `Mix_Demo` differ by **2 bytes** in a 244 KB view.

```bash
${CLAUDE_PLUGIN_ROOT}/bin/ign capabilities
MQTT_HOST=10.94.132.35 ${CLAUDE_PLUGIN_ROOT}/bin/mqtt-probe watch 'LC/R13/418-1-1/LNP/#' --seconds 15
${CLAUDE_PLUGIN_ROOT}/bin/ign-validate $PROD/LNP_418
```

> **Paths in this document.** `$DEV` and `$PROD` are the `projects/` directories inside an Ignition
> gateway backup. Set them to wherever you keep yours, or put `backups_dir` in
> `automation.local.yaml`.

The worked example throughout is **`LNP_418`** — `Site=LC`, `Path=R13/418-1-1/LNP`. Its
`ignition/script-python/LNP/code.py` is the **only fully documented implementation in the family**
and the right thing to read first and to copy from.

## Where the logic actually lives

| Instance | Gateway | Addressing | Logic in | Files |
|---|---|---|---|---|
| `LNP_418` | prod | `Site` + `Path` `R13/418-1-1/LNP` | **`LNP/code.py`** | 89 |
| `LNP_AP31` | prod | `Site` + `Path` `AP31/276-4-1/LNP` | view bindings only | 87 |
| `LNP_beta` | prod | `Site` + `Path` `R13/228-1-1/LNP` | view bindings only | 87 |
| `LNP` | dev | `Site` + `Path` `R13/228-1-1/LNP` | view bindings only | 87 |
| `Mix_Demo` | dev | `Site` + `Path` `R13/228-1-1/LNP` | view bindings only | 87 |
| `LNP_opt` | dev | `Site`/`Building`/`RoomFloorBench` | `shared/PumpControl`, `ValveControl`, `SafetyChecks` | 92 |
| `LAI_Lab` | dev | `Site`/`Building`/`RoomFloorBench` | view bindings only | 84 |
| `LAI` | prod | — | **3-file stub** | 3 |

Only two instances extract logic into scripts. In the other five, **every setpoint calculation and
every publish lives inside `views/main/view.json` event handlers and bindings** — a 5,000-line JSON
file. That is why the same arithmetic is implemented five times with five sets of rounding bugs.

### LAI is a skeleton and MSP does not exist yet

Be precise about this before promising anything:

- **`LAI_Lab`'s entire live tag surface is one value** — `IRVINE/RD3/2201/LAI_Lab/Chiller01/TT-01
  (Process Temp)`. It references `PU01/PumpStatus`, `PU01/PumpVolumeSP`, `PU02/DO`, `PU02/HMI_COM`
  and nothing more. Prod `LAI` is a 3-file stub described only as "LAI for Irvine".
- **Both LAI Node-RED backups are empty directories**, and they are named `IRVINE_RD2_TBD_LAI_lab`
  and `IRVINE_RD2_TBD_LAI_clinic` — `TBD` because the bench address is not assigned. They also say
  `RD2` while `LAI_Lab`'s `session-props` says `RD3`. **Resolve that disagreement before wiring
  anything.**
- **No MSP mix project exists in either gateway.** `SM_DPD_microsphere` is not one — its only view is
  `Cam_Replay`. Standing up MSP means creating a new instance from this convention, not editing an
  existing one. See [references/instances.md](references/instances.md).

## The two addressing conventions

Every topic and every tag path is built by concatenating session props, so the convention an instance
uses decides what its strings look like. **There are two, and they are incompatible.**

**Convention A — `Site` + `Path`** (`LNP_418`, `LNP_AP31`, `LNP_beta`, `LNP`, `Mix_Demo`):

```python
def base(session):
    site = str(session.custom.Site).strip('/')
    path = str(session.custom.Path).strip('/')
    return site + '/' + path          # 'LC/R13/418-1-1/LNP'
```

**Convention B — `Site` + `Building` + `RoomFloorBench`** (`LNP_opt`, `LAI_Lab`), plus `PumpQty` and,
where a pump lives in another building, a parallel `PC01_Site` / `PC01_Building` /
`PC01_RoomFloorBench` triple. `LNP_opt`'s `PC01` is in **R8** while the bench is in **R13**.

Readback is always the same transform: prefix the published topic with the `[MQTT Engine]` provider.

```python
def tag_root(session):
    return '[MQTT Engine]' + base(session)
```

Two traps in convention B:

- **`LAI_Lab`'s `RoomFloorBench` is the integer `2201`**, where every other instance uses a string.
  It survives `"{}".format(...)` but not anything that assumes `.strip()`.
- **`LNP_opt`'s `PumpControl` reads `session.custom.LNP_BasePath` and `session.custom.PC01_BasePath`,
  which its own `session-props` does not define.** As exported it defines `Site`, `Building`,
  `RoomFloorBench` and the `PC01_*` triple instead. Verify those props are set at runtime before
  relying on `buildMQTTTopic` — otherwise it raises `AttributeError`.

## The command and readback contract

One transport, one direction each way:

```
Perspective panel ──▶ project script ──▶ system.cirruslink.engine.publish('Chariot', …) ──▶ device
                                                                                              │
        panel bindings ◀── [MQTT Engine] tag provider ◀── retained readback ◀───────────────────┘
```

```python
def publish(topic, value, qos=0, retain=True):
    system.cirruslink.engine.publish(MQTT_SERVER, topic, str(value).encode('utf-8'), qos, retain)
```

Five rules that are not obvious and that break things when broken:

| Rule | Detail |
|---|---|
| **Every payload is a string** | `str(value).encode('utf-8')`. `PumpStatus` is compared to `"1"` / `"0"`, never to `1` / `0`. |
| **Direction is a string boolean** | `DIR_FORWARD = "false"`, `DIR_REVERSE = "true"`. Reverse *also* means publishing a **negative** flow and volume. |
| **Setpoints are retained, commands are not** | Flow/volume/ratio publish with `retain=True` so the panel and historian can read them back. `PumpCommand` publishes `retain=False` — a retained start would re-fire on reconnect. |
| **Command QoS is 1, setpoint QoS is mostly 0** | `VERB_QOS = 1` because "a dropped start or stop is a process/safety event" and commands are idempotent. |
| **`PU3` setpoints are QoS 1, uniquely** | `SP_QOS = {'PU1': 0, 'PU2': 0, 'PU3': 1, 'PU4': 0}`. The source warns the Node-RED bridge in front of the Levitronix may depend on it — **confirm before changing.** |

### PU4 speaks a different dialect

Most pumps take a verb on `/<PU>/PumpCommand` (`'start'`, `'stop'`). `PU4` is a MasterFlex behind an
`HMI_COM` block and takes a **boolean on a different topic**, with spaces and parentheses in the name:

```
/PU4/HMI_COM/DI(Pump On Off)      'true' | 'false'      run/stop
/PU4/HMI_COM/SP01 (Setpoint)      flow setpoint         note the space before '('
/PU4/HMI_COM/FeedMaxFlowRate      tubing-dependent ceiling, read at runtime
```

`PU4`'s ceiling is **not** a constant: it depends on installed tubing, so it is read from
`FeedMaxFlowRate` with a `3400.0` mL/min fallback. `PU1`–`PU3` are fixed at `200.0` mL/min by loop
hydraulics. Full topic and limit tables: [references/command-contract.md](references/command-contract.md).

## The setpoint maths

Everything the operator types is six numbers; everything the skid receives is derived from them.

```
mRNA_flow ──▶ PU1                                    (the mRNA leg, as entered)
              PU2 = mRNA_flow / ratio                (the lipid leg)
              ─────────────────────────────
              mixer_outlet = PU1 + PU2               (what leaves the mixer)
                    │
                    ├──▶ PU3 = mixer_outlet / ratio_d1                        (first quench)
                    └──▶ PU4 = mixer_outlet × (1 + 1/ratio_d1) / ratio_d2     (second quench)

              volumes:  PU1 = mRNA_vol      PU2 = mRNA_vol / ratio
```

All flows are **mL/min**, volumes **mL**. Panel defaults: `ratio` 3, `ratio_d1` 1, `ratio_d2` 0.5,
`compensate` 0.

Note that **`PU4` scales with `mixer_outlet × (1 + 1/ratio_d1)`, not with `PU3`** — it dilutes the
combined mixer-plus-first-quench stream. Getting this wrong is the most common arithmetic error when
reimplementing the panel.

**Guards, and why they exist:**

- `ratio`, `ratio_d1`, `ratio_d2` must all be `> 0` — they are divisors. Raises a `ValueError` whose
  message is written for the operator.
- `mRNA_flow` and `mRNA_vol` cannot be negative.
- Every derived flow is checked against its pump ceiling *before* anything is published, and the whole
  apply is abandoned if any pump is over. **Setpoints are applied as a set or not at all.**
- **One rounding rule, `DECIMALS = 3`, for every published setpoint.** This is load-bearing: before it
  existed the master panel published `round(value, 3)`, the PU2 field `round(value, 2)` and the PU3
  field `int(round(value))`, so the same setpoint reached the device as **58.667, 58.67 or 59**
  depending on which control the operator touched last.

Worked examples and the unit derivation: [references/process-math.md](references/process-math.md).

## Staggered starts: `compensate`

`compensate` is a **stagger in seconds**, not a flow. It exists because the two mix legs must not
necessarily arrive together:

- `compensate > 0` → `PU1` leads `PU2` by that many seconds
- `compensate < 0` → `PU2` leads `PU1`
- `0` → both start together

The delay is clamped to `MAX_STAGGER_S = 60` so a mistyped value cannot park a Gateway thread for
hours, and the sleep runs under `system.util.invokeAsynchronous` so the session stays responsive.

**`start_all` issues the quench pumps from inside that same async sequence.** It used to publish them
synchronously alongside an async mix start, which let quench lead the mix pumps whenever `compensate`
was non-zero. If you refactor this, preserve the ordering.

## Valve modes

`LNP_opt` adds a three-valve manifold under an **`MF` (microfluidics) subsystem at the room level** —
note it hangs off `Site/Building/RoomFloorBench`, *not* off the LNP path:

```
{Site}/{Building}/{RoomFloorBench}/MF/{Inner_Valve|Outer_Valve|Waste_Valve}
```

| Mode | Inner | Outer | Waste |
|---|---|---|---|
| `PRODUCT` | 0 | 0 | 0 |
| `CLEAN` | 0 | 0 | 1 |
| `REFILL` | 1 | 1 | 0 |

States publish as strings `"0"` / `"1"`, with a **50 ms delay between valve commands to avoid driver
overload**. `PRODUCT` and `CLEAN` differ only in the waste valve.

## The safety layer is mostly unimplemented

`SafetyChecks` is written fail-safe — if it cannot verify state, it blocks. But **three of its four
checks are `TODO` stubs that return safe unconditionally**:

| Check | Real? |
|---|---|
| `checkPumpConflict` | **Yes** — reads `PumpStatus`, blocks double-start, double-stop, and direction change while running |
| `checkSystemInterlock` | No — returns `(True, [])`; the E-stop read is commented out |
| `checkFlowRateCompatibility` | No — returns compatible |
| `checkValveConfiguration` | No — returns safe |

`validateOperation` calls all four and therefore **looks** comprehensive. In practice the only
enforced interlock is pump conflict. Do not describe this system as interlocked, and do not add a
mode change that depends on `checkValveConfiguration` meaning anything.

## When something is wrong

The fast triage:

| Symptom | Look first at |
|---|---|
| Setpoint arrives with wrong precision | mixed rounding — is the publish going through the single `DECIMALS = 3` path? |
| Setpoint arrives at the wrong bench | `Site`/`Path` vs `Site`/`Building`/`RoomFloorBench` — and see the shared-`Path` hazard below |
| Command ignored, pump never starts | `PU4`/`PU04` needs `HMI_COM/DI(Pump On Off)`, not `PumpCommand` |
| Command works once, then re-fires on reconnect | a command published with `retain=True` |
| Derived flow wrong by a factor | `PU4` scales off `mixer_outlet × (1 + 1/ratio_d1)`, not off `PU3` |
| Nothing applies, no error visible | one pump over ceiling aborts the whole set — check `view.custom.Status` |
| Readback never updates | wrong `[MQTT Engine]` prefix, or topic-name drift (`FlowRateSP` vs `PumpFlowRateSP`) |
| `AttributeError` on a base path | `LNP_opt`'s `LNP_BasePath` / `PC01_BasePath` are not in its `session-props` |

### Three projects address the same bench

**`LNP_beta` (prod), `LNP` (dev) and `Mix_Demo` (dev) all carry `Path` = `R13/228-1-1/LNP`.** They
build byte-identical topics for one physical bench, and setpoints are retained. Whether a dev session
can move prod hardware depends on which physical broker `Chariot` resolves to on each gateway — that
is gateway config, not project config. Check it in the `mqtt-integration` skill before testing
anything on a dev copy, and prefer `Mix_Demo` only after confirming its broker.

### Pump identifiers are not consistent

Zero-padding is part of the topic, not cosmetics:

| Instance | Pumps |
|---|---|
| `LNP_418` | `PU1` `PU2` `PU3` `PU4` |
| `LNP_AP31`, `LNP_beta`, `LNP_opt` | `PU1` `PU2` `PU04` — plus `PC01` on `LNP_opt` |
| `LAI_Lab` | `PU01` `PU02` |

`LNP_beta` additionally carries **competing duplicate topics for the same quantity** —
`Pump_Diameter` *and* `PumpDiameter`, `Pump_FlowUnits` *and* `PumpFlowUnits`, `FlowRateSP` *and*
`PumpFlowRateSP` — and `LNP_opt` adds `FlowRateWrite`. Before binding to one, probe the broker and
see which the device actually publishes.

## References

- [references/process-math.md](references/process-math.md) — setpoint derivation, units, ceilings, rounding, worked examples
- [references/command-contract.md](references/command-contract.md) — full topic map per instance, QoS, retain, payload types, `HMI_COM`
- [references/instances.md](references/instances.md) — every instance's config, the divergences, and standing up a new bench (MSP)

Related skills: `mqtt-integration` for the broker and topic layer, `nodered-rio` for the device end,
`ignition-resources` for authoring views and scripts, `estate-map` for orientation, `pitfalls` for the
estate-wide traps, `triage` for faults that are not mix-specific.
