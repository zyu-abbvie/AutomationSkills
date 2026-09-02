# The Ignition side: the TSWG line, the optimizer, and the gap

Verified against both gateway backups. **The single most important fact: there is no PSD instrument
integrated into the TSWG rig on either gateway.** The rig itself is real and fully instrumented. The PSD
measurement — the thing this whole project exists for — is **a text box an operator types a number into.**

## `TSWG` (dev) — and it is not called TSWG internally

```json
{ "title": "Extruder-AP31-4-273", "description": "Extruder in AP31-4-273",
  "parent": "FC_Parent", "enabled": true, "inheritable": false }
```

A copy of prod's `Extruder-AP31-4-273`, inheriting from **`FC_Parent` — the Fraction Collector
template.** The folder was renamed; the title and parent were not. 134 files, **56 resources** (41
Perspective, 10 ignition, 3 SFC, 1 reporting, 1 WebDev). **No alarm configuration at all.**

### It uses both addressing conventions at once

```json
"Site": "LC", "Building": "AP31", "RoomFloorBench": "273-4", "EquipmentNum": "01",
"Path": "AP31/273-4/TSWG", "Title": "TSWG AP31-273-4",
"AnnotationsTag": 2430, "BatchStatusID": 5,
"TableStarttime": 1728497585, "TableEndtime": 1728584326
```

- `[default]` tags use **Building/RoomFloorBench/TSWG** — no Site.
- `[MQTT Engine]` tags use **Site/Building/RoomFloorBench/Equipment**.
- `Path` omits Site; the BO code rebuilds the MQTT path from `Site + "/" + Building + "/" +
  RoomFloorBench` separately.
- `TableStarttime`/`TableEndtime` are hardcoded epochs from **October 2024** — a stale saved session.

### The tags it actually reads

Thermo Fisher **Process 11** twin-screw extruder over a **FINS-UDP** driver:

```
[default]GWF/_Process 11 UDP_/Tags/Extruder_Actual_Speed   Extruder_Setpoint
                                  Extruder_Torque_Nm       Extruder_Torque__
                                  F1_Throughput  F1_Actual_Value  F1_Setpoint_kg  F1_Weight_kg
                                  DIE_ACT  DIE_SET   ZONE_2.._8 _ACT / _SET
```

Liquid pump and two temperature-control units over MQTT:

```
[MQTT Engine]LC/AP31/273-4/TSWG/Pump/AI/{PT-01, SP-01, SP-01 Volume}
[MQTT Engine]LC/AP31/273-4/TSWG/Pump/DI/{Control Status, Problem Status, Pump Status}
[MQTT Engine]LC/AP31/273-4/TSWG/TCU/Accel/{RO,RS,RT,SS}
[MQTT Engine]LC/AP31/273-4/TSWG/TCU/PolyStat/{RO,RS,RT,SS}
[MQTT Engine]LC/AP31/273-4/Camera_SFTP/image
```

Derived: `[default]GWF/L-SRatio`, `GWF/Volume`, `GWF/TareVolume`,
`[default]AP31/273-4/TSWG/{Density, L_S-Control}`. Direct OPC:
`ns=1;s=[Process 11 UDP]D11500` / `D11501`.

Unit operations named on screen: three gravimetric feeders, the twin-screw extruder (speed, setpoint,
**torque in Nm and %**, power kW), seven barrel zones plus die, die pressure, the liquid pump (flow SP,
`PT-01`, volume dispensed/remaining), two TCUs, L/S ratio, density, solid flow rate.

**No dryer. No NIR. No moisture. No PSD.**

### What is real and what is debris

**Real:** `Page/EquipmentDisplay` (354 KB, the P&ID mimic), `Page/history` (audit trail + annotations),
six named queries, `Page/BO` (139 KB).

**Broken, and each in a way worth recognising elsewhere:**

1. **`Page/Camera` cannot ever show an image.** Its binding transform is literally:
   ```python
   import json
   return "data:image/png;base64,"
   ```
   The data-URI prefix with **no data**. And it is bound to `Camera_SFTP/image`, which prod's tag config
   shows is a **String** tag carrying only `{"filename": …, "timestamp": …}`. No image bytes ever exist
   on that tag.
2. **`cameraFeed/doGet.py` has a placeholder hostname** — `system.net.httpGet("http://<camera-ip>/mjpeg")`,
   literal angle brackets. It also omits `contentType`. Never commissioned.
3. **All three SFC charts are copy-paste debris from a TFF bench.** `TakeRunData/sfc.xml` opens
   `SFCName = "R14-120-1-PL"`, `Building = "R14"`, and **11 of its 13 tag paths still say `/TFF/`** —
   only the `Start` step was updated. `Collect_Fractions` builds `"/FC" + chart.EquipmentNum` in
   `onCancel`/`onAbort` but `"/TSWG"` in `finish`, so **cancel and completion write to different tag
   trees**. Its body is three annotation inserts and an `EXP_STATUS` update; it **collects no data and
   touches no extruder tag.** `Report.Report(...)` is called with 3 args against a 4-parameter signature.
4. **Every `[default]` binding in dev TSWG is dangling.** Dev's tag providers contain no `AP31` and no
   `GWF` folder — those tags exist only on prod.
5. **Prod's own `AP31/273-4/TSWG` `[default]` folder is half TFF leftovers**: `Recipe Parameters/` holds
   `Num_Diavolumes`, `Total_Membrane_Area`, `Max_Scale_Delta`, `Sel_Method` — filtration parameters,
   meaningless for granulation. See the `tff-platform` skill for what those actually mean.
6. `Page/Charts` is one PowerChart whose tag-browser root is hardcoded to the **prod** gateway.
   `named-query/test` is `SELECT * FROM sqlth_annotations where tagid = 1287` with `"database": ""`.

## Where the PSD number comes from today

`Page/BO/view.json`. Four buttons publish over Cirrus Link (`system.cirruslink.engine.publish('Chariot',
…)`, 13 call sites). The result publisher:

```python
tag_prefix       = "LC/AP31/273-4/BO/"
tag_result_topic = tag_prefix + "experiment/result"
tag_suggestion   = tag_prefix + "experiment/suggestion"
...
PARAMS_APPLIED = {
    "screw_speed":        float(self.getSibling("ScewSpeed").props.text),  #"[default]GWF/…/Extruder_Actual_Speed",
    "liquid_solid_rate":  float(self.getSibling("L_s").props.text),        #"[MQTT Engine]…/Pump/AI/SP-01",
    "solid_feed_rate":    float(self.getSibling("SolidRate").props.text),  #"[default]GWF/…/F1_Throughput",
}

METRICS = {
    "PSD_D50_um":  float(self.getSibling("PAT").props.text)       # ditto
}
```

`PAT` is a plain input component labelled **"PAT Feed"**. `PSD_D50_um` is **hand-keyed**, and so are the
three process parameters — **the real tag paths are commented out**, so even screw speed and feed rate
are typed rather than read back from the extruder.

Other literal labels in that view: **`"Record Exp(fake test)"`**, `"Start Optimizer"`, `"Stop
Optimizer"`, `"Push to Hardware"`, `"Optimization Mode"`, `"Strady State Wait Time (min)"` [sic],
`"Scew Speed"` [sic].

**`"Push to Hardware"` is uncommissioned.** It MQTT-publishes the pump SP to `…/TSWG/Pump/HMI_COM/SP-01`,
then writes the solid rate as a split 32-bit float to `D11500`/`D11501` via `system.opc.writeValue`, with
`WORD_ORDER`/`BYTE_ORDER` left as *"flip if values look wrong"* and
`# Map to REAL physical registers (EDIT these to your PLC addresses)`.

### Prod's `Extruder-AP31-4-273_BO` has diverged from dev

Same `session-props` custom block, same `AnnotationsTag: 2430`, same page set. Its `Page/BO` is **newer**
and adds validation dev lacks:

```python
METRIC_TYPES = { "PSD_D50_um": float, }
"""
Prevent publishing bad payloads like:
    "PSD_D50_um": null
This avoids optimizer-side crash:
    TypeError: float() argument must be a string or a real number, not NoneType
"""
```

But dev has `PSD_D50_um__target_score`, which prod does not. **Neither is a superset of the other.**
Three near-duplicate copies of this project exist across the estate (`TSWG`, `Extruder-AP31-4-273`,
`Extruder-AP31-4-273_BO`).

## The optimizer: Ax / BoTorch, outside Ignition

`Bayesian_Platform_Alpha` (dev), `Bayesian_Platform` and `BO_Parent` (prod). **Zero Python script
libraries on dev** — no optimization code runs in Ignition.

**Design-space generation is an LLM agent over HTTP.** `session-props`:
`"backendUrl": "http://10.72.167.251:80/analyze"`. The home view POSTs prose with a 180 s timeout:

```python
payload = {"description": "Use bayesian_agent for the following prompt: " + description}
...
bayesian_settings     = result.get("bayesian_settings", "")
design_space          = result.get("design_space", [])
assumptions_and_prompts = result.get("assumptions_and_prompts", [])
```

**The optimizer itself is driven purely over MQTT:**

```
publish    LC/AP31/273-4/bay/python              'True' | 'False'   start/stop
publish    <projectPath>/data_in                                    edited trial table
publish    LC/AP31/273-4/BO/control/trigger      'True' | 'False'
publish    LC/AP31/273-4/BO/control/session
publish    LC/AP31/273-4/BO/experiment/result
subscribe  [MQTT Engine]LC/AP31/273-4/bay/{data, platform_status}
subscribe  [MQTT Engine]LC/AP31/273-4/BO/experiment/history
subscribe  [MQTT Engine]LC/AP31/273-4/BO/status/platform
```

Full prod namespace, **all `String`**: `BO/{_probe, data, analysis/result, control/{analyze, constraints,
hyperparameters, session, status, tagmap, trigger}, experiment/{history, result, suggestion},
status/{platform, runtime}}` and `bay/{python, control/analyze, analysis/result}`.

**The library is Meta's Ax (BoTorch)**, stated outright in prod's `BO/code.py` (560 lines):

> `Mirrors bo_platform.core.constraints.is_constraint_safe_name.` … *"True if name can appear in an Ax
> constraint expression. … `bay_opt` stores free-text parameter names, so "Screw Speed" is a real row an
> operator may try to constrain — but Ax's parser splits on whitespace and would see two unknown
> tokens."*

The status renderer parses `best_arm_name`, `best_trial_index`, `trial_index`, `trial_status`,
`generation_node`, `model_used_in_best_estimation`, and `best_estimation` as `[mean, std]`. Prod carries
the Ax `GenerationStrategyConfig` block verbatim in session props (`acquisition_function`, `method`,
`initialization_budget`, `initialize_with_center`, `torch_device`, …).

Wire contract, from the same file: `control/analyze <- {description, current_design_space,
current_objectives}`; `analysis/result -> {bayesian_settings, design_space, objectives,
assumptions_and_prompts} | {error}`; `control/constraints <- {parameter_constraints,
outcome_constraints}`.

**No Dotmatics involvement** — the `Dotmatics_*` projects are unrelated and share nothing with these.

### The decision variables and the objective

`equipment_name: "Twin Screw Granulator"`:

| Parameter | Range | Units | Bound to a tag? |
|---|---|---|---|
| Screw Speed | 50–300 | RPM | **`"tag": null`** |
| Liquid Feed Rate | 1–10 | mL/min | **`"tag": null`** |
| Powder Feed Rate | 10–50 | g/min | **`"tag": null`** |

The objective, from the seeded prompt text — dev's version:

> *"Set up a Bayesian optimization loop for a Twin Screw Wet Granulation (TSWG) process in a
> pharmaceutical R&D environment. The design space includes only 3 key parameters: screw speed, liquid
> feed rate, and powder feed rate. The objective function to be optmized is particle size distribution
> (PSD)."*

Prod is more specific: **"particle size distribution (PSD D50) in the 40-50 um band."**

### Where trial data lives — and does not

One table, **`bay_opt`** on connection `SQLServer`: `project_name, equipment_name, parameter_name,
parameter_type, lower_bound, upper_bound, units, options, tag, timestamp`. Named queries `fetch_config`
(SELECT), `update_config` (MERGE upsert), `delete_config`, `test`. `project_name` is
`re.sub(r'\W+','_', name).lower()` → `extruder_ap31_4_273`. Prod adds `bo_projects` for a project
registry, self-described as optional.

**It stores design-space bounds only — never results, never a PSD.** Trial results live **only in MQTT
`String` tags, which are not historized.** So today there is no queryable record of any optimizer trial.

`webdev/resources/extruderPage.html` in the dev project is a 3-second redirect to the **prod** gateway's
Perspective client — the dev project's only web entry point points at production.

## The landing pad for this rig exists, and is unused

Dev, `config/resources/core/ignition/tag-definition/MQTT Engine/pat/psd/tags.json`:

```json
[ { "usr": {"readOnly": true, "dataType": "String", "enabled": true},
    "name": "heartbeat", "tagType": "AtomicTag" },
  { "usr": {"readOnly": true, "dataType": "String", "enabled": true},
    "name": "metrics", "tagType": "AtomicTag" } ]
```

`grep -rn 'pat/psd'` across **both entire backups returns nothing** — no project, view, script or query
reads them.

Two mismatches to fix before relying on them:

- **They are `String`.** `pat+gv` publishes `pat/psd/d50` and friends as **retained bare floats**
  (`"%.3f"`), which is a String on an MQTT-Engine tag anyway — but the two provisioned names are
  `heartbeat` and `metrics`, i.e. **only the JSON topics**, not the scalar leaves a binding would
  actually want.
- **They are `readOnly: true`**, which is correct for telemetry — but note the same gateway declares
  `LC/AP31/273-4/BO/control/{trigger,session}` read-only while the BO view **publishes to them**. Those
  two are the only BO tags provisioned on dev; prod has the full fifteen.

## The one real particle instrument — wrong bench, orphaned

Prod has two Mettler-Toledo AutoChem OPC-UA connections, `FBRM_test`
(`opc.tcp://10.248.64.80:62552/iCOpcUaServer`) and `Blaze Computer#2 OPC`. **68 tags** hang off them under
`[default]PAT/FBRM_from_OPC/`. This is **iC FBRM** — Focused Beam Reflectance Measurement, i.e. **chord
length distribution**, not ECD:

```
PAT/FBRM_from_OPC/Connection_Status
PAT/FBRM_from_OPC/Start_Experiment___{Trigger, Experiment_Name, Probe_Number, Template_File_Path}
PAT/FBRM_from_OPC/Experiment_{1,2}/Last_Sample_Distribution__{Default,Alternate}_CSM
PAT/FBRM_from_OPC/Experiment_{1,2}/Last_Sample_{Binned,Averaged}_Distribution__…_CSM
PAT/FBRM_from_OPC/Experiment_{1,2}/Control/{Stop,Pause,Resume,SetSamplingInterval}___Trigger
PAT/FBRM_from_OPC/Experiment_1/Trends/Mean__Sqr_Wt__Primary/Value
PAT/FBRM_from_OPC/Experiment_1/Trends/counts__No_Wt___10__Primary/Value       ← fines, <10 um
PAT/FBRM_from_OPC/Experiment_1/Trends/counts__No_Wt__10-100__Primary/Value
PAT/FBRM_from_OPC/Experiment_1/Trends/counts__No_Wt__100-1000__Primary/Value
```

**Exactly four tags are historized** — the mean square-weighted chord length and three count bands. The
distribution arrays are live-read only.

Its **sole consumer is `SM_DPD_microsphere`** (panels labelled "FBRM Control" / "FBRM Status") — a
microsphere process on a different bench. **No TSWG, Extruder, BO or Bayesian resource in either gateway
references `PAT/FBRM` — not one string.**

Two things follow. First, that instrument is the closest thing the estate has to a validated PSD feed,
and it is **not** on the granulation line. Second, if anyone proposes comparing its numbers against
`pat+gv`'s: **chord length is not ECD.** An FBRM counts chords across particles in suspension; this rig
measures projected-area equivalent diameters of free-falling particles. They will not agree, and should
not be expected to.

The vendors the knowledge pack lists as evaluated — **Parsum, Eyecon, Malvern, Sympatec, Insitec,
Canty — have zero hits in either gateway.** None is integrated.

## Projects whose names invite a wrong guess

Checked, because each one looks like a link in the TSWG chain and is not:

| Project | Actually | Bench |
|---|---|---|
| `FD-F3-309-3-1` (prod) | *"LC NC F3 **FilterDryer** 309"* — 129 files, no parent. A **filter dryer**: a batch unit operation for isolating and drying a crystal cake, **not** the continuous dryer in the granulation chain. Publishes on `LC/F3/309-3-1/{HUM, RX}` | F3/309-3-1 |
| `FDHum-F3-309-3-1` (prod) | *"FilterDryer and **CellKraft Humidifier**"* — 84 files. Humidity **control**, not moisture **measurement**. Zero literal hits for `moisture` or `NIR` | F3/309-3-1 |
| `PSM_Parent`, `PSM-R8-*` (prod) | **Power Supply Monitoring Parent Project.** Nothing to do with particle size | — |
| `PT`, `PT_Opt` (dev) | **Pressure Transmitters** — every apparent "PAT" hit is the substring in `PATH` | R13/228-1-1 |
| `ExpMetadata` (prod) | *"Table with Feedback"* — manual experiment metadata. Its only `moisture` hit is a dropdown option in a picklist, not a sensor | — |

**Neither dryer project references `TSWG` or `AP31/273-4` anywhere.** So the chain's dryer and NIR links
are genuinely unbuilt — there is no existing project to extend, and standing them up is new work.

## The camera projects, for reference

- **`camera_2025-10-13_1106`** (prod) — **not PAT.** 12 files. One `ia.display.image` polling an IP camera
  every 5 s with a cache-busting expression. No analysis, no DB, no PSD. A dated throwaway snapshot.
- **`Camera_Demo`** (prod) — **real and well-engineered, but frame archiving only.** A gateway-timer
  archiver that stores JPEG bytes into `uploaded_files` (`filedata varbinary(max)`) and reads them back.
  Bench `LC/R8/133-1-10`. **This is the mature pattern TSWG's `Page/Camera` is a broken stub of** — but it
  has no particle detection, no D50 and no calibration. Two live defects flagged in its own comments: a
  hardcoded credential (`_FALLBACK_PASSWORD`, marked `TODO(security)`, also plaintext in its WebDev
  handler), and an older path where *"archiving is a SIDE EFFECT of serving the live image… the operator
  MUST KEEP THE PERSPECTIVE PAGE OPEN."*
- **`PT` / `PT_Opt`** (dev) — **not PAT. Pressure Transmitters.** Every apparent "PAT" grep hit in them is
  the substring in `PATH`. `PT_Opt` additionally has ~25 loose `.md`/`.txt`/`.py` files committed into the
  project root, which are not Ignition resources.

## The historian gap

| Table | Written by | Holds a PSD? |
|---|---|---|
| `sqlth_te`, `sqlth_data_*` | tag historian | only the 4 FBRM trend values, from another bench |
| `sqlth_annotations` | `Annotation.InsertAnnotation`, and an SFC with a **hardcoded `tagid`** | no |
| `EXP_STATUS` | SFC `finish`/`onCancel`/`onAbort`, raw `UPDATE` | no — run metadata only |
| `AUDIT_EVENTS` | audit profile | no |
| `bay_opt` / `bo_projects` | the BO config views | **bounds only** |
| `uploaded_files` | `Camera_Demo` timer | JPEGs, unanalysed |

**No table anywhere stores a PSD result, a D10/D50/D90, a distribution array, a camera calibration
version or an algorithm version.**

One connection to be careful with: **`SQLite_Database` → `jdbc:sqlite:C:/Path/To/File.db`** — an
unedited template path, still `ENABLED=1`, and still named as the `historyProvider` on live tags
(`Feed_Tubing_Size_Sel`, `CurrentUPI`, `CurrentUser`). **Those tags historize nowhere.**

## Closing the loop

The integration is a topic subscription and a binding, not a development project — but do it
deliberately.

1. **Confirm which broker `Chariot` resolves to on each gateway** before testing anything. Every field
   device publishes to the **prod** broker, and `pat+gv`'s own broker is configured separately in
   `config.yaml`. See the `mqtt-integration` skill.
2. **Provision the scalar leaves, not just the JSON.** A PID or a Perspective binding wants
   `pat/psd/run/<source>/<engine>/d50`, retained and bare. The two existing tags (`heartbeat`, `metrics`)
   are the JSON topics.
3. **Gate on `valid`.** `pat/psd/…/valid` is `"1"`/`"0"`, and the consumer contract is **hold the last
   good output whenever it is false** — not chase noise, and not substitute zero. `valid` is computed
   three different ways depending on the tree; [api-mqtt.md](api-mqtt.md) has all three.
4. **Decide which D50 the optimizer gets, and say so.** The per-frame tree (`…/src/…`) uses PAT's step
   percentile convention on purpose, so an existing PID's tag does not shift. The run tree (`…/run/…`)
   uses interpolated percentiles over the accumulated population. **For a Bayesian trial the run-level
   number is the right one** — it is the population of the experiment, not of one frame.
5. **Replace the `PAT` text box with a binding**, and uncomment the three parameter tag paths while you
   are there — an optimizer fed hand-typed parameters is not recording what the process did.
6. **Historize it.** `pat/psd/run/…/d50` and `…/span` at minimum, plus the run ID, or no trial is
   reconstructable afterwards. There is currently nowhere to put a distribution; a `varbinary` or a JSON
   column keyed on `run_id` would do, and `pat+gv` already exports `hist_*.csv` and a reservoir sample
   per run.
7. **Give a run a Sample ID and a reference measurement.** Neither exists in `pat+gv` or in the estate,
   and the validation strategy in the knowledge pack is built on comparing against laser diffraction.
8. **Do not describe the loop as closed** until `"Push to Hardware"` is commissioned. Its register
   mapping and byte order are still marked as guesses.

Everything on the Ignition side of this is ordinary work covered by the other skills — `ignition-resources`
for the tags and bindings, `mqtt-integration` for the topic layer and the retained-message rules,
`sql-historian` for the storage, `equipment-onboarding` for standing up the instance.
