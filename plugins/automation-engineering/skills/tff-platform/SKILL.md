---
name: tff-platform
description: Work on a Tangential Flow Filtration skid in this estate - the TFF_Parent platform and its 20 child projects, the 41-tag process model with every tag's physical meaning and unit, the Flux and TimeToCompletion and WeightDelta calculations, the six SFC unit operations (Fill, Filter, FillandFilter, DiaFiltration, FillthenFilterwMakeup, TakeRunData), the balance and pressure and pump instruments on the groov RIO, the HMI_COM command and readback contract, and how to debug a run that is producing wrong numbers or has stalled. Use when reading or authoring anything on a TFF bench, when flux or time-to-completion looks wrong, when a scale-fail or pressure alarm fires, when a command does not reach the skid, when standing up a new TFF instance, or when asked what a TFF tag actually measures.
---

# The TFF platform

Tangential Flow Filtration concentrates or buffer-exchanges a liquid by pumping it across a membrane.
Retentate recirculates; permeate passes through. The estate runs this as a **platform**: one
`TFF_Parent` project and **20 child projects** on prod, which is the largest family in the estate.

**A child project is configuration and nothing else.** `TFF-F3-309-3-2` contains exactly four things:
`page-config`, `session-props`, `global-props`, `project.json`. Every view, script, chart and query is
inherited. The whole per-bench difference lives in `session-props` `custom`.

```bash
${CLAUDE_PLUGIN_ROOT}/bin/ign capabilities
${CLAUDE_PLUGIN_ROOT}/bin/ign tags --provider default --path F3 --recursive   # the tag model
${CLAUDE_PLUGIN_ROOT}/bin/nr-inspect topics $NODERED/LC_F3_309-3-2_TFF/*.zip  # the device contract
```

> **Paths in this document.** `$DEV` and `$PROD` are the `projects/` directories inside an Ignition
> gateway backup; `$NODERED` is a directory of groov RIO device backups. Set them to wherever you keep
> yours, or put `backups_dir` / `nodered_backups_dir` in `automation.local.yaml`.

The worked example throughout is **`TFF-F3-309-3-2`** — `Site=LC`, `Building=F3`,
`RoomFloorBench=309-3-2` — paired with the RIO backup `$NODERED/LC_F3_309-3-2_TFF/`.

## The configuration contract: coordinates plus fitted options

`session-props/props.json` `custom` carries two different kinds of thing, and conflating them is the
main way a new bench comes out wrong.

**Coordinates** — `Site`, `Building`, `RoomFloorBench`. Every tag path, every MQTT topic and every
indirect binding is built by concatenating these. Get one wrong and the bench silently drives, or
reads, a different skid.

**Fitted-hardware flags** — the option model. The same inherited views and charts serve benches with
different physical hardware by testing these:

| Flag | Meaning | Fitted on |
|---|---|---|
| `PinchValve` | a pinch valve is fitted, so **TMP control is possible** | 18 of 20 — **not** `TFF-F3-309-3-1` or `TFF-R14-120-1-L` |
| `Chiller` | temperature control loop present | 4: `F3-309-3-2`, `R14-120-1-L`, `R8-320-3-1`, `RD2-364-1` |
| `PH_Meter` | inline pH probe | 2: `B5-2071-2-1`, `R14-120-1-L` |
| `MFM` | mass flow meter | 1: `RD2-364-1` |
| `FeedDir` / `RecircDir` | pump direction is switchable | `FeedDir` on all 20; `RecircDir` off on `RD2-364-1` |
| `ConcentrationPAT` | concentration PAT instrument | `false` everywhere — provisioned, never fitted |
| `ChartTime` | HMI trend window, minutes | `10` on 19, `20` on `R14-120-1-PL` |

Two consequences worth internalising:

- **`PinchValve: false` means the `TMPressurePID_Mode` and `TMPressurePID_Out` commands have nothing
  to actuate.** Do not write TMP control logic for a bench without checking this flag first.
- **`PH_Meter` is absent — not `false` — on 13 of the 20.** A missing prop reads as null, which is not
  the same as `false` in an expression binding. Test for truthiness, never `= false`.

### Three TFF projects are not on the platform

`TFF-F3-415-4-1`, `TFF-R8-320-3-2` and `TFF-Teller-BSL3-2-1` have **no parent** and carry 39, 39 and
61 of their own resources. Their `custom` block is a different contract entirely — `AnnotationsTag`,
`BatchStatusID`, `TableStarttime`, `Path`, `Title`, `EquipmentNum` — with no `Site`/`Building`/
`RoomFloorBench` and none of the option flags. **Nothing in this skill applies to them.** Check
`project.json` for `parent: "TFF_Parent"` before assuming you are on the platform.

## The physical system

```
   feed vessel  ──▶ [WT-01 Source Weight]  balance, serial
        │
        ▼  feed pump (FPumpSP)                    ┌── retentate returns to the vessel
   ┌─────────────┐   [PT-01 Feed Pressure]  ──────┤
   │  membrane   │◀── recirc pump (RPumpSP) ──────┘
   │  cassette   │
   └──────┬──────┘   Total_Membrane_Area, m²
          │ permeate
          ▼
   permeate vessel ──▶ [WT-02 Permeate Weight]  balance, serial
                            │
                            ▼  differentiate + rolling average
                       FT-02 (Permeate Flow), mL/min
                            │
                            ▼  × 0.06 ÷ area
                       Flux, LMH
```

Also on the skid: an agitator (`AG-01`, status + PV) and a pump speed readback (`PU-02`).

## Three layers, one contract

| Layer | Owns | Where |
|---|---|---|
| **groov RIO / Node-RED** | the instruments, serial protocols, and the weight→flow derivation | `$NODERED/LC_F3_309-3-2_TFF/` |
| **MQTT** | the contract between them, retained, QoS 0, **all values are strings** | `LC/F3/309-3-2/TFF/…` |
| **Ignition** | the tag model, the process calculations, sequencing, HMI, history, alarms | `TFF_Parent` + child |

`FT-02` is computed **on the RIO**, not in Ignition. Ignition receives a flow, not a weight rate. And
because the RIO averages it (`calculator` node, `avg`, 2 decimals), `Flux` inherits that smoothing —
it is not an instantaneous number.

## The process model

Everything the platform "knows" lives in six expression tags. These are the model.

**Flux** — the primary TFF performance metric:

```
FT-02 (Permeate Flow) × 0.06 / Total_Membrane_Area
```

`0.06` converts mL/min → L/h (`60 min/h ÷ 1000 mL/L`). With area in m², the result is **LMH
(L·m⁻²·h⁻¹)**. Reads `0.0` whenever `Status` is null/empty/`"Completed"`, or the flow or area is null,
or area ≤ 0 — so **a zero flux usually means a guard tripped, not that filtration stopped.**

**WeightDelta** — the mass-balance / scale-fail check:

```
abs( WT-02 (Permeate Weight) + WT-01 (Source Weight) )
```

Permeate gains what source loses, so once both balances are zeroed the sum should stay near zero. A
growing delta means a leak, a spill, tubing pulling on a pan, evaporation, or a balance that dropped
out. Only evaluated when `Sel_Method` is `DiaFiltration` or `FillthenFilterwMakeup`; otherwise `0`.

**TimeToCompletion**, and `PercentComplete = ElapsedTime / TimeToCompletion × 100` clamped to 0–100:

```
(Sel_Method == "DiaFiltration" ? Start_Volume × Num_Diavolumes × Density
                              : Target_Volume × Density) / Density / FT-02
```

Note the algebra: it multiplies by `Density` and then divides by it. **`Density` is a no-op here.**
Changing it has no effect on the estimate, whatever an operator expects. Effectively
`volume_to_remove / permeate_flow`.

**P1 Value** passes `PT-01 (Feed Pressure)` straight through, and carries the pressure alarm.

Full derivations, unit analysis and guard behaviour: [references/tag-model.md](references/tag-model.md).

## Recipe parameters

The model inputs. Values below are what is **actually stored on `F3/309-3-2`** on the dev gateway —
read your own bench rather than assuming these.

| Parameter | Type | Example | Unit | Drives |
|---|---|---|---|---|
| `Total_Membrane_Area` | Float8 | `0.2` | **m²** | Flux denominator |
| `Start_Volume` | Float8 | `300.0` | **mL** | DiaFiltration target |
| `Target_Volume` | Float8 | `0.0` | mL | non-DF target |
| `Num_Diavolumes` | Float8 | `8.0` | — (dimensionless) | DiaFiltration target |
| `Density` | Float8 | `1.0` | g/mL | nothing — cancels out |
| `P1_Max` | Float8 | `41.0` | **PSI** | pressure alarm setpoint |
| `Max_Scale_Delta` | Float8 | `2.5` | **g** | WeightDelta alarm setpoint |
| `FPumpSP` / `RPumpSP` | Float8 | `35.0` / `50.0` | pump % | feed / recirc pump speed |
| `StirrerSP` | **String** | `'200'` | RPM | agitator speed |
| `Residence_Time` | Float8 | `55.0` | s | hold timing |
| `Sel_Method` | String | `'FillthenFilterwMakeup'` | — | **selects the unit operation** |

`StirrerSP` is a String while every other setpoint is `Float8`. That is an inconsistency in the
platform, not a subtlety — coerce it explicitly.

`P1_Max = 41` is PSI: 41 bar across a bench cassette would be far outside any membrane's rating.
`Total_Membrane_Area = 0.2` m² is consistent with a bench cassette, and makes the Flux arithmetic land
in the normal LMH range.

## The six unit operations

SFC charts under `$PROD/TFF_Parent/com.inductiveautomation.sfc/charts/TFF/`. `Sel_Method` picks one.

| Chart | What it does |
|---|---|
| `Fill` | fill the retentate loop from the feed vessel |
| `Filter` | concentrate: recirculate and remove permeate to a target |
| `FillandFilter` | fill and concentrate in one sequence |
| `DiaFiltration` | buffer exchange at constant volume, for `Num_Diavolumes` |
| `FillthenFilterwMakeup` | fill, then concentrate with make-up buffer added |
| `TakeRunData` | capture a data point / snapshot into the batch record |

Charts receive `chart.Site`, `chart.Building`, `chart.RoomFloorBench` and build every tag path and MQTT
topic by string concatenation. `Filter` steps, in order: `__begin`, `Start`, `ZeroPBalance`, `Sleep`,
`Recirculating`, `FinishingUP`, `AlarmCheck`, `ScaleFail`, `cClearingAlarm`, `Clear_Prompt`, `__end1`.

Step detail, transitions and the operator-prompt handshake:
[references/unit-operations.md](references/unit-operations.md).

## Commands: how the sequence drives the skid

**Not tag writes.** Every command is a retained publish, immediately followed by an empty publish to
clear the retained copy:

```python
system.cirruslink.engine.publish('Chariot', topic, 'ZI', 0, True)   # fire
system.cirruslink.engine.publish('Chariot', topic, '',   0, True)   # clear the retained message
```

Omit the second publish and the command **re-fires every time the RIO reconnects** — a pump can restart
itself after a device reboot.

`"ZI"` to `…/TFF/HMI_COM/ZeroPBalance` is a Mettler-Toledo **MT-SICS "Zero Immediately"**. The chart
retries and counts attempts in `chart.zeroftries`, falling through to `ScaleFail`.

HMI_COM points on a TFF bench: `ZeroPBalance`, `ZeroFBalance`, `Density`, `Feed ON`, `Feed Direction`,
`Feed Set Speed`, `FeedMaxFlowRate`, `Recirc ON`, `Recirc Set Speed`, `StirrerON`, `StirrerSP`,
`TMPressurePID_Mode`, `TMPressurePID_Out`.

**Acknowledgement is a readback on a different topic.** The command topic never tells you whether the
skid acted. Confirm on the `AI`/`AO`/`DO`/`Calc_Val` point instead.

## Three defects that are live right now

Confirmed against both gateways. Do not reproduce them, and expect to hit them.

1. **`WeightDelta` on `F3/309-3-2` reads another bench's balances.** The expression references
   `[MQTT Engine]LC/AP31/299-4/TFF/SERIAL/WT-01` and `WT-02` — building AP31, room 299-4. Its
   scale-fail alarm therefore watches a different skid. When cloning a bench, grep the new project's
   tags for the old coordinates before handover.
2. **The alarm pipeline `TFF_Parent/TFF_Alarms` does not exist.** Both TFF alarms — `P1 Value` above
   `P1_Max`, and `WeightDelta` above `Max_Scale_Delta` — name it as their `activePipeline`, but
   `TFF_Parent` has no `com.inductiveautomation.alarm-notification` folder on either gateway. **These
   alarms raise and notify nobody.**
3. **`TimeToCompletion` cancels its own `Density` term** (above). Harmless arithmetically, misleading
   to anyone tuning it.

## Standing up a new TFF bench

1. Assign coordinates and name the project `TFF-<Building>-<Room-Floor-Bench>`.
2. Create the child with `parent: "TFF_Parent"` and **only** `page-config` + `session-props`. Set the
   coordinates *and* the fitted-hardware flags — copy the `custom` block from the most similar
   existing bench rather than writing it from scratch, then correct each flag against the actual
   skid. Do not copy views.
3. Build or clone the RIO flow, then **rewrite every topic** to the new coordinates.
4. Confirm the device is publishing before touching Ignition:
   `mqtt-probe watch 'LC/F3/309-3-2/TFF/#' --seconds 20 --summary` against the **prod** broker.
5. Create the `[default]{Building}/{RoomFloorBench}/TFF/` tags. The expression tags reference
   `[MQTT Engine]` paths **hardcoded per instance** — this is where defect 1 comes from.
6. Set `Total_Membrane_Area` (m²) and `P1_Max` (PSI) before the first run; Flux and the pressure alarm
   are meaningless without them.
7. Point the alarms at a pipeline **that exists**.
8. `ign-validate` the project, then verify each command's readback moves.

See the `equipment-onboarding` skill for the parts common to every equipment type.

## When something is wrong

[references/troubleshooting.md](references/troubleshooting.md) has ordered playbooks. The fast triage:

| Symptom | Look first at |
|---|---|
| Flux reads 0 | the guard clauses — `Status`, `FT-02`, `Total_Membrane_Area` |
| Flux off by a constant factor | units — area in cm² not m², flow in L/min not mL/min |
| Time-to-completion nonsense | `Sel_Method`, `FT-02` ≤ 0, and remember `Density` does nothing |
| Scale-fail with no cause | defect 1 — whose balances is the expression actually reading? |
| Alarm did not notify | defect 2 — the pipeline is missing |
| Command ignored | the readback topic, not the command topic |
| Everything frozen | `Heartbeat` advancing? Retained values persist after a device dies |

**One constraint shapes all of it:** every field device publishes to the **prod** broker, and prod
Ignition has **no HTTP API**. The dev `[MQTT Engine]` tree is stale. Live prod values come from the
Designer or a Perspective session, not from `ign`.

## References

- [references/tag-model.md](references/tag-model.md) — all 41 tags, units, physical meaning, expressions
- [references/unit-operations.md](references/unit-operations.md) — the six SFC charts step by step
- [references/instrument-layer.md](references/instrument-layer.md) — balances, transducer, pumps, the RIO flow
- [references/troubleshooting.md](references/troubleshooting.md) — ordered debug playbooks

Related skills: `mqtt-integration` for the topic layer, `ignition-resources` for authoring,
`sql-historian` for trends and batch history, `triage` for faults that are not TFF-specific.
