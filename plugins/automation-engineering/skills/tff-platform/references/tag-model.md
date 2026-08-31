# TFF tag model and physical meaning

Every number on a TFF skid, what it physically is, what unit it is in, and where it came from.
Measured on the **dev gateway** tag provider `[default]`, folder `F3/309-3-2/TFF` — 41 tags — plus
the label and report text in `TFF_Parent` that is the only place several units are written down.

> **Paths in this document.** `$DEV` and `$PROD` are the `projects/` directories inside an Ignition
> gateway backup; `$NODERED` is a directory of groov RIO device backups. Set them to wherever you
> keep yours, or put `backups_dir` / `nodered_backups_dir` in `automation.local.yaml`.

```bash
${CLAUDE_PLUGIN_ROOT}/bin/ign tags --provider default --path F3/309-3-2/TFF --recursive
${CLAUDE_PLUGIN_ROOT}/bin/ign tags --provider "MQTT Engine" --path LC/F3/309-3-2/TFF --recursive
```

**Provenance.** Tags live in the *gateway* tag provider, not in the project, so this model is the
**dev** gateway's. Prod exposes no HTTP API — to confirm a prod bench, open the Designer. The tag
*folder* path is `[default]{Building}/{RoomFloorBench}/TFF/` (no `Site`); MQTT topics are
`{Site}/{Building}/{RoomFloorBench}/TFF/…` (with `Site`). That asymmetry is deliberate and every
indirect binding in `TFF_Parent` follows it.

**Only three tags declare an `engUnit`** — `Flux` (`LMH`), `TimeToCompletion` (`min`),
`PercentComplete` (`%`). Every other unit below is evidenced from an HMI label or a report column
name, cited per row. Nothing here is a measured operating range; where a unit is not written down
anywhere, this document says so.

## The 41 tags

`H` = history enabled (all 28 historised tags go to the `SQLServer` provider).

### Recipe Parameters/ — the model inputs (13 tags)

Operator-entered, memory tags, written from `$DEV/TFF_Parent/…/views/Docks/RecipeParametersLG/view.json`.

| Tag path | Type | Source | Unit | H | Physical meaning |
|---|---|---|---|---|---|
| `Recipe Parameters/Total_Membrane_Area` | Float8 | memory | **m²** (label `Total Filter Membrane Area (m^2)`) | H | Effective filtration area of the installed cassette, from the membrane datasheet. Sole denominator of `Flux`. Live value `0.2`. |
| `Recipe Parameters/Density` | Float8 | memory | **g/mL** (label `Density (g/ml):`) | H | Density of the permeate, used to convert balance grams to millilitres. Live value `1.0`. Also published to `HMI_COM/Density`, where the RIO uses it for the weight→flow conversion. Inside `TimeToCompletion` it cancels — see below. |
| `Recipe Parameters/Start_Volume` | Float8 | memory | **mL** (label `Starting Reactor Volume (ml):`) | H | Retentate volume in the feed vessel at the start of the run. Basis of the diafiltration target (one diavolume = one `Start_Volume`). Live value `300`. |
| `Recipe Parameters/Target_Volume` | Float8 | memory | **mL** (label `Target Permeate Volume (ml):`) | H | Permeate volume to collect for every non-diafiltration method. Live value `0.0` — unset, which drives `TimeToCompletion` to 0 arithmetically. |
| `Recipe Parameters/Num_Diavolumes` | Float8 | memory | dimensionless | H | Number of retentate volumes of buffer to exchange in a diafiltration. Live value `8` (≈99.97 % theoretical exchange for a fully permeable solute — general TFF arithmetic, not measured here). |
| `Recipe Parameters/P1_Max` | Float8 | memory | **psi, gauge** (label `P1 Max (psi):`; report column `Feed Pressure (psi)`; `TFF_Full_Display` labels `PT-1 (psig)`) | H | Feed-pressure trip point. Carries the `P1 Value` alarm setpoint. Live value `41` (default `40`). Read this as psig: 41 bar across a bench cassette is outside any membrane rating. |
| `Recipe Parameters/Max_Scale_Delta` | Float8 | memory | **g** *(inferred — the HMI label `Feed/Permeate Difference:` states no unit)* | H | Largest tolerated mass imbalance between the two balances before the run is treated as leaking. Unit follows from its comparand: both balance readings are grams (report columns `Source Weight (g)` / `Permeate Weight (g)`). Live value `2.5`. |
| `Recipe Parameters/FPumpSP` | Float8 | memory | **mL/min** (label `Feed Pump Flow (mL/min):`; report column `Feed SP (mL/min)`) | H | Feed-pump flow setpoint. **A flow, not a percentage** — the RIO scales it to a 0-10 V analog output by dividing by `FeedMaxFlowRate`. Live value `35`. |
| `Recipe Parameters/RPumpSP` | Float8 | memory | **mL/min** (label `Recirculation Pump Flow (mL/min):`) | H | Recirculation (crossflow) pump flow setpoint — sets the shear rate across the membrane. Live value `50`. |
| `Recipe Parameters/StirrerSP` | **String** | memory | **rpm** (label `Stir Speed (rpm)`) | H | Overhead-agitator speed setpoint, forwarded verbatim to the IKA stirrer as `OUT_SP_4 <value>`. Live value `'200'`. String while every other setpoint is Float8 — coerce explicitly. |
| `Recipe Parameters/Sel_Method` | String | memory | — | H | Selects the unit operation, one of `Fill`, `Filter`, `FillandFilter`, `DiaFiltration`, `FillthenFilterwMakeup`, `TakeRunData`. Also branches `TimeToCompletion` and gates `WeightDelta`. Live value `FillthenFilterwMakeup`. |
| `Recipe Parameters/Residence_Time` | Float8 | memory | **cannot be determined** | H | Live value `55`. **Zero references anywhere in either gateway backup** — no HMI label, no chart, no script, no report column. Seconds is the obvious reading for a hold time but nothing in the estate states it. Treat as dead configuration until a chart consumes it. |
| `Recipe Parameters/test` | Boolean | memory | — | — | Scratch tag, live value `true`, no `defaultValue`. Only match for `Recipe Parameters/test` estate-wide is `Ruben-Test-App/…/testview`. Not part of the model. |

### Derived process values (6 tags)

| Tag path | Type | Source | Unit | H | Physical meaning |
|---|---|---|---|---|---|
| `Flux` | Float8 | **expr** | **LMH** = L·m⁻²·h⁻¹ (`engUnit`) | H | Permeate throughput per unit membrane area — the primary TFF performance number. Falling flux at constant TMP is fouling. Inherits the RIO's 10-sample rolling average on `FT-02`, so it is not instantaneous. |
| `P1 Value` | **Float4** | **expr** | **psig** | — | Feed-line pressure at the cassette inlet. Straight pass-through of `PT-01`. Carries the pressure alarm. Only Float4 in the folder; not historised (the trend and report read the MQTT tag's history instead). |
| `WeightDelta` | Float8 | **expr** | **g** | — | Mass-balance closure: how far the two balances disagree. Should stay near zero once both are zeroed; a rising value is a leak, a spill, tubing pulling on a pan, evaporation, or a dropped balance. Carries the scale-fail alarm. **Reads the wrong bench — defect 1.** |
| `TimeToCompletion` | Float8 | **expr** | **min** (`engUnit`) | — | Full-run estimate: minutes to remove the recipe's target permeate mass at the current permeate flow. **Not a countdown** — it does not subtract permeate already collected. |
| `ElapsedTime` | Int4 | **derived** | **min** (`dateDiff(…, "minute")`) | H | Minutes since `Batch_Start`, or 0 once `Batch_End` is set. The report column labels it `Elapsed Time (s)` — that label is wrong. |
| `PercentComplete` | Float8 | **expr** | **%** (`engUnit`) | — | Elapsed-vs-estimate progress bar, clamped 0-100. Not mass actually removed. |

### Batch record (7 tags)

Written once per run; all historised, so a completed batch can be reconstructed from history alone.

| Tag path | Type | Source | Unit | H | Physical meaning |
|---|---|---|---|---|---|
| `Batch_Start` | DateTime | memory | epoch ms, `yyyy-MM-dd h:mm:ss aa` | H | Timestamp the SFC started. Sole basis of `ElapsedTime`; also the report's history start bound. |
| `Batch_End` | DateTime | memory | epoch ms | H | Timestamp the run finished. Non-null forces `ElapsedTime` to 0 and bounds the report window. |
| `Batch_ExperimentName` | String | memory | — | H | Experiment name frozen at batch start (vs. the live `ExperimentName` below). |
| `Batch_ProjectName` | String | memory | — | H | Scientific project / programme name frozen at batch start. |
| `Batch_Started_by_User` | String | memory | — | H | Display name of the operator who pressed Start. |
| `Batch_Started_by_UPI` | String | memory | — | H | That operator's numeric personnel id. |
| `Batch_Started_by_email` | String | memory | — | H | That operator's email. **Lowercase `email`.** Three bindings in `TFF_Parent` spell it `Batch_Started_by_Email`; Ignition tag paths are case-insensitive so it resolves, but match the tag's own casing in new work. |

### SFC interface (5 tags)

The only channel between a running chart and the HMI.

| Tag path | Type | Source | Unit | H | Physical meaning |
|---|---|---|---|---|---|
| `SFC-ID` | String | memory | — | H | UUID of the running chart instance, written at Start. `system.sfc.getVariables(<this>)` is how the header reads chart-scope variables such as `runningTime`. Stale value here means chart lookups fail. |
| `SFC-Msg` | String | memory | — | H | Free-text operator message the chart writes at each step ("Target Volume Reached - Ending Batch", "Max Scale Delta Reached - Restarting…"). Set to `""` to clear. |
| `Status` | String | memory | — | H | Run state. Values written by the charts: `Initializing`, `Filling`, `Filtering`, `Running`, `Stopping`, `Stopped`, `Cancelled`, `Completed`, then `""`. **`Flux` and `TimeToCompletion` only guard on `""` and `"Completed"`** — see the guard tables. |
| `Prompt-Continue` | Boolean | memory | — | H | Operator acknowledgement of a chart prompt. Written by the **prod** `TFF_Parent` charts (3-8 references each); the **dev** `TFF_Parent` charts reference it zero times. The two parents have diverged — check which one your bench inherits. |
| `Continue_Visible` | Boolean | memory | — | H | Shows/hides the Continue button. Same dev/prod divergence as above. |

### Session / user (5 tags)

Live values, overwritten every session. History disabled, but their `historyProvider` is
`SQLite_Database` — the broken placeholder connection. Do not enable history on these without
repointing the provider.

| Tag path | Type | Source | Unit | H | Physical meaning |
|---|---|---|---|---|---|
| `CurrentUser` | String | memory | — | — | Display name of whoever has the HMI open now. Copied into `Batch_Started_by_User` at Start. |
| `CurrentUPI` | String | memory | — | — | That user's personnel id. |
| `CurrentEmail` | String | memory | — | — | That user's email. |
| `ExperimentName` | String | memory | — | — | Experiment name being typed into the recipe dock; copied to `Batch_ExperimentName` at Start. |
| `ProjectName` | String | memory | — | — | Programme name, same lifecycle. |

### Hardware configuration (5 tags)

| Tag path | Type | Source | Unit | H | Physical meaning |
|---|---|---|---|---|---|
| `Feed_Tubing_Size_Sel` | Int4 | memory | **mL/min** | — | **Not a tubing size — the maximum flow the fitted peristaltic pump-head tubing can deliver.** The dropdown shows tubing numbers and stores flows: `13→36`, `14→130`, `16→480`, `25/15→1000`, `17/24→1700`, `18/35→2300`, `36→3400`. Its `onChange` publishes the value to `HMI_COM/FeedMaxFlowRate`, which is the RIO's mL/min → volts scaling constant. Live value `480` (size 16 tubing). Get it wrong and every feed flow is off by the ratio of the two maxima. |
| `Recirc_Tubing_Size_Sel` | Int4 | memory | **mL/min** | — | Same for the recirculation pump; same option list; live value `480`. Publishes `HMI_COM/RecircMaxFlowRate`. Note its `onChange` publishes at **QoS 2** where the feed one uses QoS 0 — cosmetic, but do not copy. |
| `Sample_Rate` | *(no dataType declared)* | memory | **s** (label `Report Sample Rate (seconds)`) | — | Report/trend sampling interval. `TFFReport` computes `sampleSize = secondsBetween(Batch_Start, Batch_End) / Sample_Rate` and asks the historian for that many rows, so this sets report resolution, not logging rate. Live value `10`. The only tag in the folder with **no `dataType`**, while the dropdown offers `0.1` and `0.5` — sub-second choices that cannot survive an integer tag. |
| `DeviceID` | String | memory | — | H | Bench identity string stamped into the batch record and the report. Built by `TFFHeader` as `Site + "/" + Building + "/" + RoomFloorBench + "-TFF"` → `LC/F3/309-3-2-TFF`. **Note the hyphen before `TFF`** — this is a label, *not* an MQTT topic prefix (that would be `LC/F3/309-3-2/TFF`). Do not build topics from it. |
| `TMP_Control_Mode` | String | memory | — | H | Which element is controlling transmembrane pressure. Live value `None`; read by `PID_Faceplate` on every TFF child. Not part of the six-category enumeration most TFF docs quote — it is the 41st tag. |

## The derived tags, one at a time

Expressions are verbatim from the dev gateway (`ign tags`), reformatted for line width only.

### Flux — LMH

```
if(isNull({[.]Status}) || isNull({[MQTT Engine]LC/F3/309-3-2/TFF/Calc_Val/FT-02 (Permeate Flow)})
   || isNull({[.]Recipe Parameters/Total_Membrane_Area})
   || toString({[.]Status}) = "" || toString({[.]Status}) = "Completed"
   || toString({[MQTT Engine]LC/F3/309-3-2/TFF/Calc_Val/FT-02 (Permeate Flow)}) = ""
   || toDouble({[.]Recipe Parameters/Total_Membrane_Area}) <= 0,
   0.0,
   toDouble({[MQTT Engine]LC/F3/309-3-2/TFF/Calc_Val/FT-02 (Permeate Flow)}) * 0.06
     / toDouble({[.]Recipe Parameters/Total_Membrane_Area}))
```

Algebra: permeate volumetric flow divided by membrane area, with one unit conversion.

| Step | Quantity | Unit |
|---|---|---|
| `FT-02` | permeate volumetric flow | mL/min |
| `× 60 min/h` | | mL/h |
| `÷ 1000 mL/L` | | L/h |
| `× 0.06` = `× 60 / 1000`, both steps at once | | L/h |
| `÷ Total_Membrane_Area` | | L·h⁻¹·m⁻² = **LMH** |

The factor is exactly right **provided** flow is mL/min and area is m². Both hold here: the RIO
publishes `Calc_Val/FT-02` in mL/min (`$NODERED/LC_F3_309-3-2_TFF`, balance parser: `Δg × 60 ÷
density`), and the area label says m². Substituting cm² for m² inflates flux by 10 000; L/min for
mL/min inflates it by 1000.

| Guard | Reads |
|---|---|
| `Status` null, `""`, or `"Completed"` | `0.0` |
| `FT-02` null or `""` (topic never published, or MQTT Engine tag absent) | `0.0` |
| `Total_Membrane_Area` null or `≤ 0` | `0.0` |
| `Status` = `Stopped` / `Cancelled` / `Stopping` | **not guarded** — keeps computing from whatever `FT-02` last held. Because MQTT is retained, a dead RIO leaves a non-zero flux on screen. |

**A zero flux usually means a guard tripped, not that filtration stopped.** Check `Status` first.

### There are two different Flux numbers on a TFF bench

`[default]…/TFF/Flux` above is instantaneous. Every *consumer* — `TFFReport`, `Charts`, `Main`,
`TFF_Full_Display` — reads a different one: `[MQTT Engine]{Site}/{Building}/{RoomFloorBench}/TFF/HMI_COM/Flux`,
published by a session script in `$DEV/TFF_Parent/…/views/Header/TFFHeader/view.json`:

```python
Liters      = float(Permeate_Val) / float(Density) / 1000       # g → mL → L
elapse_time = float(chartvars["runningTime"]) / 3600            # runningTime is SECONDS → hours
Flux        = Liters / elapse_time / float(FilterArea)          # L / h / m² = LMH
```

Same unit, different physical quantity: this is a **cumulative average** flux over the whole run
(total permeate collected ÷ total elapsed time ÷ area), from `WT-02` rather than `FT-02`. It is
smoother and always lags the instantaneous value. Two further problems with it: it is published to
`HMI_COM`, which the topic contract reserves for Ignition→device commands, and it is a *derived
process value on a command channel*; and the `Flux` tag's own documentation says it "replaces the
per-session flux calc formerly in `Header/TFFHeader`" — the replacement was made but the consumers
were never moved. **When someone disputes a flux number, establish which of the two they are looking
at before anything else.**

### TimeToCompletion — minutes

Guards (all return `0.0`): `Status` null/`""`/`"Completed"`; `FT-02` null/`""`/`≤ 0`; any of
`Sel_Method`, `Density`, `Start_Volume`, `Num_Diavolumes`, `Target_Volume` null; `Density ≤ 0`.
Otherwise:

```
(if(toString({[.]Recipe Parameters/Sel_Method}) = "DiaFiltration",
    Start_Volume * Num_Diavolumes * Density,
    Target_Volume * Density))
  / Density
  / FT-02
```

| Step | Quantity | Unit |
|---|---|---|
| `Start_Volume × Num_Diavolumes` or `Target_Volume` | volume of permeate to remove | mL |
| `× Density` | mass to remove | g |
| `÷ Density` | back to volume | mL |
| `÷ FT-02` | | mL ÷ (mL/min) = **min** |

**The `Density` factor cancels itself out exactly. It is a no-op, not a unit conversion.** Changing
`Density` on the recipe dock has zero effect on the estimate, whatever an operator expects. The
`× Density` step exists to mirror the `Final_Mass` HMI field ("Calculated Mass to Remove", same
expression in `RecipeParametersLG`), which genuinely is a mass in grams. Effectively the tag is
`volume_to_remove / permeate_flow`.

Live consequence on this bench: `Sel_Method = FillthenFilterwMakeup` takes the `else` branch, and
`Target_Volume = 0.0`, so the numerator is 0 and the tag reads `0.0` — **not** via a guard, just
arithmetic. `PercentComplete` then also reads 0. A blank progress bar on a running bench is normally
an unset `Target_Volume`.

### PercentComplete — percent

```
if(isNull({[.]TimeToCompletion}) || isNull({[.]ElapsedTime})
   || toDouble({[.]TimeToCompletion}) <= 0, 0.0,
   min(100.0, max(0.0, toDouble({[.]ElapsedTime}) / toDouble({[.]TimeToCompletion}) * 100.0)))
```

Both inputs are minutes, so the ratio is dimensionless and `× 100` makes it a percent. `min(100, …)`
means an overrunning run shows a full bar rather than 140 %; `max(0, …)` catches a negative
`ElapsedTime` from a `Batch_Start` in the future. Reads `0.0` for every case `TimeToCompletion`
itself zeroes, which is why an idle bench shows an empty bar. It measures elapsed-vs-estimate, **not
mass removed** — a fouling run sits at 100 % long before it is done.

### WeightDelta — grams

```
if({[.]Status} != "" && ({[.]Recipe Parameters/Sel_Method} = "DiaFiltration"
                      || {[.]Recipe Parameters/Sel_Method} = "FillthenFilterwMakeup"),
   abs(tofloat({[MQTT Engine]LC/AP31/299-4/TFF/SERIAL/WT-02 (Permeate Weight)})
     + tofloat({[MQTT Engine]LC/AP31/299-4/TFF/SERIAL/WT-01 (Source Weight)})),
   0)
```

Both balances are zeroed at the start of the operation (`ZeroPBalance` / `ZeroFBalance`), so
thereafter the source balance reads **negative** grams removed and the permeate balance reads
**positive** grams gained. Their **sum** is the mass that left the system without arriving — hence
`+`, not `-`, and `abs()` to make it a magnitude. Unit: g + g = g.

| Guard | Reads |
|---|---|
| `Status` = `""` | `0` |
| `Sel_Method` not `DiaFiltration` and not `FillthenFilterwMakeup` | `0` — so a `Filter`-only or `Fill`-only run has **no mass-balance check at all** |
| `Status` = `"Completed"` | **not guarded** (unlike `Flux`), so the delta persists after the run |
| either balance null / `""` | `tofloat` of null → the tag goes to error/null; there is no `isNull` guard here, unlike `Flux` |

Only makes sense for methods that add make-up buffer, which is why it is gated — but the gate also
silently disables the leak check on the two most common concentration methods.

### P1 Value — psig

```
{[MQTT Engine]LC/F3/309-3-2/TFF/SERIAL/PT-01 (Feed Pressure)}
```

No conversion, no guard. It exists only to give the string-typed MQTT tag a numeric `[default]` home
that an alarm can bind to. Physically: feed pressure at the cassette inlet, from the SciLog 4-channel
monitor, published as a 6-sample unrounded average, **not retained** — so after a gateway restart it
is empty until the next serial frame, and the alarm cannot evaluate. `Float4` here vs `Float8`
everywhere else; a bare tag reference with no `toDouble`, so a non-numeric payload makes the tag go
to error rather than to a guarded default.

### ElapsedTime — minutes

```
sourceTagPath          [~]Universal/Current_Time      (expression tag, now(1000))
deriveExpressionGetter if(isNull({[.]Batch_End}),
                          dateDiff({[.]Batch_Start}, {[~]Universal/Current_Time}, "minute"), 0)
deriveExpressionSetter {value}
```

A **derived** tag, not an expression tag: it re-evaluates every second because its source ticks at
1 Hz, but only changes value once a minute. Unit is minutes, fixed by `dateDiff(…, "minute")`.

The setter matters. `{value}` writes straight through to `sourceTagPath`, i.e. to
`[~]Universal/Current_Time`, which is an **expression** tag and therefore not writable. So both
attempts to drive this tag fail silently: `Clear_Prompt` does `system.tag.writeAsync(ElapsedTime, 0)`
and `TFFHeader` does `system.tag.writeAsync(ElapsedTime_tag, chartvars["runningTime"])` — the latter
in **seconds**, which is where the report's `Elapsed Time (s)` column name comes from. What you
actually read is always the getter, in minutes. The reset to 0 comes from `Batch_End` being written,
not from those writes.

## Instrument tag map

Physical device → MQTT topic → Ignition tag. Flow internals, serial ports and protocols are in
[instrument-layer.md](instrument-layer.md); this is only the bridge.

| Physical device | MQTT point under `LC/F3/309-3-2/TFF/` | Retained | `[default]` tag that consumes it |
|---|---|---|---|
| SciLog 4-ch pressure monitor, feed channel | `SERIAL/PT-01 (Feed Pressure)` | **no** | `P1 Value` (→ pressure alarm) |
| same, retentate / permeate / TM channels | `SERIAL/PT-02`, `PT-03`, `PT-04 (TM Pressure)` | no | none — display and report only; `PT-04` is also the RIO's own PID PV |
| Mettler-Toledo balance, feed vessel | `SERIAL/WT-01 (Source Weight)` | yes | `WeightDelta` (**from the wrong bench** — defect 1) |
| Mettler-Toledo balance, permeate vessel | `SERIAL/WT-02 (Permeate Weight)` | yes | `WeightDelta`; the `HMI_COM/Flux` session script; chart zero-confirmation transitions (`\|WT-02\| ≤ 0.5 g`) |
| permeate balance, differentiated on the RIO | `Calc_Val/FT-02 (Permeate Flow)` | yes | `Flux`, `TimeToCompletion` — the most consumed point on the bench |
| feed balance, differentiated on the RIO | `Calc_Val/FT-01 (Feed Flow)` | yes | none — display and report only |
| recirculation pump, commanded speed | `Calc_Val/PU-02 (Speed)` | yes | none. Despite the `Calc_Val` folder it is **not measured** — it is the PID output scaled to mL/min |
| IKA overhead stirrer | `SERIAL/AG-01 (Agitator PV)` (rpm) | yes | none |
| same, inferred from PV `< 1 rpm` | `SERIAL/AG-01 (Agitator Status)` | yes | SFC transitions, compared against the **string** `"true"` |
| pumps, valve, discrete/analog readback | `DO/PU-01…`, `DO/PU-02…`, `AO/PV-01 (Pinch Valve)`, `AI/ST-01 (Feed Speed)` | yes | display bindings only |

### The bridging step

`MQTT Engine` subscribes `#` through the `NonSparkplugTags` custom namespace and auto-creates one
tag per topic under the `[MQTT Engine]` provider, path-identical to the topic. Nothing copies those
into `[default]` — the expression tags reach across providers with a **hardcoded absolute path**
including `Site`, e.g. `{[MQTT Engine]LC/F3/309-3-2/TFF/Calc_Val/FT-02 (Permeate Flow)}`. That
hardcoding, per bench, per expression, is exactly what defect 1 is made of.

**Every `[MQTT Engine]` tag is `dataType: "String"`** — pressures, weights, flows, booleans, all of
them. So the expression tags are also the estate's type conversion layer:

| Expression | Conversion |
|---|---|
| `Flux`, `TimeToCompletion`, `PercentComplete` | `toDouble(...)` on every input |
| `WeightDelta` | `tofloat(...)` on both weights |
| `P1 Value` | **none** — bare tag reference, the Float4 tag type does the coercion |
| SFC transitions | none — compare to the string `"true"` / `"false"`, which is correct here |

On the **dev** gateway `[MQTT Engine]LC/F3/309-3-2/TFF` contains only eight `HMI_COM` tags — no
`SERIAL`, no `Calc_Val` — and `LC/AP31/299-4` does not exist at all. Verified with `ign tags`. Every
expression tag above therefore reads null on dev; their exported values are empty. **No field device
publishes to the dev broker.** Do not conclude a calculation is broken from a dev reading.

## Reading a value safely

The pattern the estate uses, and the reason it needs three separate tests:

```
if(isNull({[MQTT Engine]<topic>})            // tag missing, or never received a message
   || toString({[MQTT Engine]<topic>}) = ""  // topic exists but payload is "" (a cleared retained command)
   || toDouble({[.]<divisor>}) <= 0,         // numeric floor: no divide-by-zero, no negative area
   0.0,
   toDouble({[MQTT Engine]<topic>}) * k / toDouble({[.]<divisor>}))
```

Why all three are needed:

1. **`isNull`** — MQTT Engine creates a tag only when a message arrives. A topic that has never been
   published has no tag, and the reference is null.
2. **`toString(x) = ""`** — the datatype is String, so "no value" is representable *as a value*. The
   estate deliberately publishes `""` to clear retained commands, so empty payloads are normal
   traffic. `isNull` does not catch them, and `toDouble("")` is not a number.
3. **A numeric floor on every divisor** — an unset `Total_Membrane_Area` or a zero `FT-02` is a
   division by zero, and a negative one is physically impossible, so `<= 0` is the right test, not
   `= 0`.

In Jython the equivalent trap is truthiness: `if tagValue:` against the string `'false'` is **true**.
Compare explicitly (`== 'true'`) or coerce first. And when reading history rather than live values,
note that historian tag paths are stored lowercase — `TFFReport` mixes
`Calc_Val/FT-02 (Permeate Flow)` and `calc_val/pu-02 (speed)` in the same call and both resolve.

## Three confirmed defects

**1. `WeightDelta` on `F3/309-3-2` reads another bench's balances.**
Evidence: the live expression on the dev gateway references
`[MQTT Engine]LC/AP31/299-4/TFF/SERIAL/WT-01 (Source Weight)` and `…/WT-02 (Permeate Weight)` —
building AP31, room 299-4. `TFF-AP31-299-4` is a real prod bench, so this is a clone that was never
re-pointed. Consequence: this skid's mass-balance number, and the scale-fail alarm bound to it,
describe a different room's balances; a leak here is invisible and a spill there stops this run. On
dev it is worse — `LC/AP31/299-4` has no MQTT tags at all, so the tag is simply null.
Fix: rewrite both references to `LC/F3/309-3-2/…`. Then grep every TFF bench's expression tags for
coordinates that do not match their own folder, because the same clone will have happened elsewhere.

**2. Both alarms notify through a pipeline that does not exist.**
Evidence: `P1 Value` and `WeightDelta` each carry one `AboveValue` alarm with
`activePipeline: "TFF_Parent/TFF_Alarms"` (setpoint bound to `[.]Recipe Parameters/P1_Max` as a Tag
binding, and to `{[.]Recipe Parameters/Max_Scale_Delta}` as an Expression binding). `TFF_Parent` has
**no** `com.inductiveautomation.alarm-notification` folder on either gateway — verified in both
backups; the only projects that own pipelines are `LabFreezers` and `DevSciLabs` (prod, pipelines
`Alarms` and `AWA Alarms`) plus `ABC-Alarms`, `Glebs Pager`, `Martillac-Alarms`, `LabFreezers` on dev.
Consequence: overpressure and scale-fail alarms raise, latch and display in the Perspective alarm
table, and **notify nobody**. Anyone who believes they are on call for a TFF bench is not.
Fix: create `com.inductiveautomation.alarm-notification/alarm-pipelines/TFF_Alarms` in `TFF_Parent`
so the 20 children inherit it, or repoint both alarms at an existing pipeline. Editing the parent is
a 20-bench change — see the blast-radius note in `ignition-resources`.

**3. `TimeToCompletion` multiplies and then divides by `Density`.**
Evidence: the verbatim expression above — `… * toDouble({[.]Recipe Parameters/Density})` in both
branches of the inner `if`, then `/ toDouble({[.]Recipe Parameters/Density})`. Consequence: the
estimate is insensitive to `Density`, so an operator who corrects density to fix a wrong ETA sees no
change, concludes the tag is broken, and stops trusting it. The `Density <= 0` guard is still load-
bearing, which disguises the cancellation. Fix: drop both factors and compute
`volume_to_remove / FT-02` directly, or keep the mass form and divide by a **permeate** density that
is genuinely a separate quantity from the retentate density on the recipe dock. Either way, say in
the tag documentation which it is.
