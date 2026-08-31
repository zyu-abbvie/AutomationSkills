# TFF unit operations and the SFC model

The six SFC charts under `TFF_Parent/com.inductiveautomation.sfc/charts/TFF/` are the whole batch engine of the TFF
platform. All 20 PROD child projects inherit all six; a child adds nothing. This is the step-by-step contract: what
each chart does, what it writes, what it waits for, and how the operator handshake and the command pattern work.

> **Paths in this document.** `$DEV` and `$PROD` are the `projects/` directories inside an Ignition
> gateway backup; `$NODERED` is a directory of groov RIO device backups. Set them to wherever you
> keep yours, or put `backups_dir` / `nodered_backups_dir` in `automation.local.yaml`:
>
> ```bash
> DEV=<backups>/Ignition-<DEVHOST>_Ignition-backup-<stamp>/projects
> PROD=<backups>/Ignition-<PRODHOST>_Ignition-backup-<stamp>/projects
> NODERED=<backups>/backup_nodered
> ```
>
> Every chart quotation is from `$PROD/TFF_Parent/com.inductiveautomation.sfc/charts/TFF/<Chart>/sfc.xml`.
> Worked bench: `TFF-F3-309-3-2` — `Site=LC`, `Building=F3`, `RoomFloorBench=309-3-2`.

Each chart is a directory holding `resource.json` (`{"scope":"G","version":1,…,"files":["sfc.xml"]}`) and `sfc.xml`.
Unlike named queries, SFC charts are **version 1, scope G** — all six — and all are `execution-mode="Callable"`,
`persist-state="true"`, `hot-editable="false"`. PROD line counts: `TakeRunData` 138, `Fill` 328, `Filter` 409,
`DiaFiltration` 617, `FillandFilter` 627, `FillthenFilterwMakeup` 747.

**DEV and PROD charts are not the same generation.** All six differ. PROD added the operator Continue prompt
everywhere; DEV auto-advances — in `$DEV/.../Fill/sfc.xml` the transition out of `FinishingUP` is literally `true`
where PROD has `tag(… "/TFF/Prompt-Continue")`, and DEV says `"Target Volume Reached - Ending Batch"` instead of
`"- Press Continue to End Batch"`. Never promote a DEV chart to PROD: it deletes every operator hold in the sequence.

## How a chart is launched

Single call site — the Start button in
`$PROD/TFF_Parent/com.inductiveautomation.perspective/views/Docks/RecipeParametersLG/view.json` (`onClick`; same
script on `$DEV`):
```python
projectname = "TFF-" + self.session.custom.Building + "-" + self.session.custom.RoomFloorBench
path = "TFF/" + self.parent.parent.getChild("RecipeParameters").getChild("CoordinateContainer") \
                    .getChild("Method_DropDown").props.value
sfcname = self.session.custom.Building + "-" + self.session.custom.RoomFloorBench
args = {"SFCName": sfcname, "Building": self.session.custom.Building,
        "Site": self.session.custom.Site, "RoomFloorBench": self.session.custom.RoomFloorBench,
        "Chiller": self.session.custom.Chiller}
sfcID = system.sfc.startChart(projectname, path, args)
system.tag.writeAsync("[default]" + Building + "/" + RoomFloorBench + "/TFF/SFC-ID", sfcID)
```

**`path` is `"TFF/" + <dropdown value>`** — the dropdown value *is* the chart name, and that is the whole
method-dispatch mechanism; no lookup table, no `if`. **`projectname` must be the child project** (`TFF-F3-309-3-2`);
started against the parent name the chart will not resolve. The dropdown is **bidirectionally bound** to
`[default]{Building}/{RoomFloorBench}/TFF/Recipe Parameters/Sel_Method`, so choosing a method writes `Sel_Method` and
selects the chart in one gesture.

### Sel_Method values, verbatim

From `Method_DropDown` `props.options` in that view — the only six legal values:

| `Sel_Method` (= chart name) | Operator label |
|---|---|
| `Fill` | Fill Only |
| `FillandFilter` | Fill then Filter |
| `FillthenFilterwMakeup` | Fill then Filter with Makeup |
| `DiaFiltration` | DiaFiltration |
| `Filter` | Filter Only |
| `TakeRunData` | Take Run Data |

Live on dev: `[default]F3/309-3-2/TFF/Recipe Parameters/Sel_Method` = `"FillthenFilterwMakeup"`, `String`.
**`Sel_Method` is what makes the derived tags behave differently, and no chart reads it** — `grep Sel_Method
*/sfc.xml` returns nothing. Only tag expressions consume it: `TimeToCompletion` branches on `Sel_Method =
"DiaFiltration"` (target mass `Start_Volume * Num_Diavolumes * Density`, otherwise `Target_Volume * Density`), and
`WeightDelta` is non-zero **only** when `Sel_Method` is `DiaFiltration` or `FillthenFilterwMakeup` — the two
makeup-feed methods — else `0`. So `Fill` / `Filter` / `FillandFilter` run with `WeightDelta` pinned at 0, and their
scale-delta alarm can never fire even though `AlarmCheck` reads it.

### Chart parameter contract

`__begin` declares nine parameters in every chart; `SFCName` is the key parameter (`key="true"`).

| Parameter | Passed by launcher | Used for |
|---|---|---|
| `SFCName` | yes | logger name only (`getLogger("SFC Logger " + chart.SFCName)`, commented out everywhere) |
| `Site` | yes | first level of every MQTT topic and `[MQTT Engine]` tag path |
| `Building` | yes | first level of every `[default]` path, second of every topic |
| `RoomFloorBench` | yes | second level of `[default]`, third of every topic |
| `Chiller` | yes | **declared in all six, referenced by none** — `grep chart.Chiller */sfc.xml` = 0 |
| `zeroftries` | no, default 0 | balance-zero retry counter |
| `zeroptries` | no, default 0 | **never assigned anywhere** — see defects |
| `Alarm` | no, default 0 | latch set by `AlarmCheck`, cleared by `cClearingAlarm` |
| `Recirculation_Complete` | no, default 0 | set to 1 by `FinishingUP`/`FinishingUP2` to break the parallel |

`__begin` defaults are hardcoded to a real bench — `Site "LC"`, `Building "R14"`, `RoomFloorBench "120-1-PL"`. With no
args the chart drives `LC/R14/120-1-PL`. Never start a chart without arguments to "see what it does". Every path is
one of two shapes:
```python
"[default]" + chart.Building + '/' + chart.RoomFloorBench + "/TFF/<tag>"                # Ignition tag
chart.Site + '/' + chart.Building + '/' + chart.RoomFloorBench + "/TFF/HMI_COM/<point>" # MQTT topic
```

`[default]` paths **omit `Site`**; MQTT topics **include it** — reverse that and you create a tag folder `LC`.

## Fill

Charge the retentate vessel to a target starting mass. Feed pump only, no permeate flow. Chosen to prime a rig or load
material before a separate `Filter` run. Steps in order: `__begin`, `Start`, `ZeroFBalance`, `Sleep`, `Feeding`,
`FinishingUP`, `Sleep`, `Clear_Prompt`, `__end1`, plus `ScaleFail` off the retry jump.

| Step | Writes | Transition out |
|---|---|---|
| `Start` | `SFC-Msg` = `"Fill Sequence Starting"`; `Status` = `"Initializing"`; publishes `HMI_COM/StirrerSP` = `str(StirrerSP)`, `HMI_COM/StirrerON` = `"true"` | `tag("[MQTT Engine]…/TFF/SERIAL/AG-01 (Agitator Status)") = "true"` |
| `ZeroFBalance` | publishes `HMI_COM/ZeroFBalance` = `"ZI"` then `""`; `chart.zeroftries += 1`; `SFC-Msg` = `"Zeroing feed balance for fill - Attempt=" + str(chart.zeroftries)` | three-way, below |
| `Feeding` | `chart.zeroftries = 0`; `SFC-Msg` = `"Starting Feed Pump"`; `Status` = `"Filling"`; publishes `HMI_COM/Feed Set Speed` = `str(FPumpSP)`, `HMI_COM/Feed ON` = `"true"`. 3000 ms `timer-script` rewrites `SFC-Msg` = `"Waiting for Feed Mass to reach -<TargetMass> g"` | mass reached, 1 h timeout |
| `FinishingUP` | publishes `Feed ON` = `"false"`; `SFC-Msg` = `"Target Volume Reached - Press Continue to End Batch"`; `Status` = `"Completed"`; `Prompt-Continue` = `"false"`, `Continue_Visible` = `"true"`; `Batch_End` = `system.date.now()`; `TFFReport.Report(...)` | `tag("[default]…/TFF/Prompt-Continue")` |
| `Clear_Prompt` | publishes `StirrerON` = `"false"`; `SFC-Msg` = `""`; `Status` = `"Completed"`, sleep 3, `Status` = `""`, sleep 2, `ElapsedTime` = 0; both prompt tags `"false"` | unconditional → `__end1` |

Transitions out of `Sleep`, and the fill target (`timeout-delay="3600000"`, 1 h), quoted:
```
4 8   tag("[MQTT Engine]"+{Site}+"/"+{Building}+"/"+{RoomFloorBench}+"/TFF/SERIAL/WT-01 (Source Weight)") <= 0.5
   && tag(… "WT-01 (Source Weight)") >= -0.5                    → Feeding
5 8   tag(… "WT-01 (Source Weight)") >= 0.5 || tag(…) <= -0.5    → back to ZeroFBalance
3 8   {zeroftries} >= 3                                         → jump A → ScaleFail
4 11  abs(tag("[MQTT Engine]"+…+"/TFF/SERIAL/WT-01 (Source Weight)"))
        >= (tag("[default]"+{Building}+"/"+{RoomFloorBench}+"/TFF/Recipe Parameters/Start_Volume")
            * tag("[default]"+…+"/TFF/Recipe Parameters/Density"))                → FinishingUP
```

Reads `StirrerSP`, `FPumpSP`, `Start_Volume`, `Density`. Terminates at `Clear_Prompt` or `ScaleFail` → `__end1`, or at
`onCancel` / `onAbort`.

## Filter

Concentrate: recirculate retentate across the membrane and let permeate leave until the permeate balance reaches
target mass. Vessel volume falls. Chosen when the rig is already charged. Steps in order: `__begin`, `Start`,
`ZeroPBalance`, `Sleep`, `Recirculating`, `FinishingUP`, `AlarmCheck`, then `cClearingAlarm` or `Clear_Prompt`,
`__end1`, plus `ScaleFail`.

| Step | Writes | Transition out |
|---|---|---|
| `Start` | `SFC-Msg` = `"Filter Sequence Starting"`; `Status` = `"Initializing"`; publishes `StirrerSP`, `StirrerON` = `"true"` | `AG-01 (Agitator Status) = "true"` |
| `ZeroPBalance` | publishes `HMI_COM/ZeroPBalance` = `"ZI"` then `""`; `chart.zeroftries += 1`. **No message write** — `SFC-Msg` stays on `"Filter Sequence Starting"` for the whole loop | three-way on `WT-02`, ±0.5 g band as in `Fill` |
| `Recirculating` | `SFC-Msg` = `"Starting Recirc Pump"`; `Status` = `"Filtering"`; publishes `HMI_COM/Recirc Set Speed` = `str(RPumpSP)`, `HMI_COM/Recirc ON` = `"true"`. 3 s timer rewrites `SFC-Msg` = `"Waiting for Permeate Mass to reach <TargetMass> g"` | two ways, below |
| `FinishingUP` | publishes `TMPressurePID_Mode` = `"Manual"`, `Recirc ON` = `"false"`, sleep 1, re-publishes `Recirc Set Speed`, then `StirrerON` = `"false"`; `Status` = `"Completed"`; `Continue_Visible` = `"true"`; `chart.Recirculation_Complete = 1`; `Batch_End`; `TFFReport.Report` | unconditional → `AlarmCheck` |
| `AlarmCheck` | publishes `TMPressurePID_Mode` = `"Manual"`; reads `P1 Value/Alarms.HasActive` and `WeightDelta/Alarms.HasActive`. If P1 active: `SFC-Msg` = `"Alarm Max Pressure Reached at PT-1 - Press Continue to Restart Batch"`, `chart.Alarm = 1`, `Status` = `"Stopped"`, stops both pumps, `Continue_Visible` = `"True"` | two ways on `Prompt-Continue` and `{Alarm}` |
| `cClearingAlarm` | `chart.Alarm = 0`; both prompt tags `"false"` | `{Alarm} = 0` → **loops back to `Recirculating`** |

```
3 13  tag("[default]"+{Building}+"/"+{RoomFloorBench}+"/TFF/P1 Value/Alarms.HasActive")  → AlarmCheck (bypasses FinishingUP)
4 13  abs(tag(…"/TFF/SERIAL/WT-02 (Permeate Weight)")) >= tag(…Target_Volume) * tag(…Density)  → FinishingUP  [timeout 1 h]
3 20 / 4 20  tag(…"/TFF/Prompt-Continue") & {Alarm} → cClearingAlarm ; & !{Alarm} → Clear_Prompt
3 22  {Alarm} = 0  → Recirculating      (Clear_Prompt is as in Fill and exits to __end1)
```

The P1-alarm branch enters `AlarmCheck` **without** running `FinishingUP`, so on a pressure trip no `Batch_End` is
stamped and no report is generated until the operator ends the batch another way. Reads `StirrerSP`, `RPumpSP`,
`Target_Volume`, `Density`, plus `P1_Max` and `Max_Scale_Delta` indirectly via the two `Alarms.HasActive` properties.

## FillandFilter

`Fill` and `Filter` welded together with an operator valve change between them. The ordinary concentration run from an
uncharged rig.

Order: `__begin` → `Start` → `ZeroFBalance` ⇄ `Sleep` → `Feeding` → `FComplete` → `StatUpdate` → **parallel
(`ZeroFBalance` ‖ `ZeroPBalance`, each with its own `Sleep`)** → `Recirculating` → `FinishingUP` → `AlarmCheck` →
`cClearingAlarm` | `Clear_Prompt` → `__end1`, with `ScaleFail` off the retry-limit jump. New here:

- **`FComplete`** — `SFC-Msg` = `"Reactor Filled - Please open the permeate valve and close the product recovery
  valve"`, `Status` = `"Filling"`, publishes `Feed ON` = `"false"`, `Prompt-Continue` = `"false"`, `Continue_Visible`
  = `"true"`. A physical-action hold: the operator must move two valves. Out on `tag(…"/TFF/Prompt-Continue")`.
- **`StatUpdate`** — `Status` = `"Initializing"`, `Continue_Visible` = `"false"`; hides the button again.
- **The parallel block** — `<parallel … enable-cancel-condition="true" cancel-condition="{zeroftries} >=3 ||
  {zeroptries} >=3">` — the `WT-01` ±0.5 pair on the feed branch, the `WT-02` ±0.5 pair on the permeate branch.
  `Feeding` resets `chart.zeroftries = 0` beforehand so it starts on a fresh counter.
- Reads `StirrerSP`, `FPumpSP`, `RPumpSP`, `Start_Volume`, `Target_Volume`, `Density`.

## DiaFiltration

Constant-volume buffer exchange. Both balances are zeroed, then feed (buffer) and recirculation run concurrently: the
feed pump replaces exactly the mass leaving as permeate, holding vessel volume while `Num_Diavolumes` volumes of
buffer wash through. Chosen for buffer exchange / desalting, not concentration. Two `<parallel>` blocks, no
single-balance prologue:
```
__begin → Start
  → parallel 1 (2 5, cancel on {zeroftries}>=3 || {zeroptries}>=3)
        ZeroFBalance → Sleep (WT-01 ±0.5 band, else retry)  ‖  ZeroPBalance → Sleep (WT-02 ±0.5 band, else retry)
  → 4 16  {zeroftries} >= 3 || {zeroptries} >= 3  → jump A → ScaleFail
    5 16  {zeroftries} <  3 && {zeroptries} <  3  → parallel 2
  → parallel 2 (2 19, cancel-condition=" " — disabled)
        FeedingStart → Feeding → FeedingDone  (makeup)  ‖  Recirculating → FinishingUP2 → Sleep  (filtration)
  → AlarmCheck → cClearingAlarm | Clear_Prompt → __end1
```

The **makeup control law** is the two feed-branch transitions — a mass balance, not a level sensor:
```
2 2   tofloat(tag(…"WT-02 (Permeate Weight)")) + tofloat(tag(…"WT-01 (Source Weight)")) >  0   → Feeding     (feed ON)
2 5   tofloat(tag(…"WT-02 (Permeate Weight)")) + tofloat(tag(…"WT-01 (Source Weight)")) <= 0   → FeedingDone (feed OFF)
```

Both balances start zeroed, so `WT-01` goes negative as source is consumed and `WT-02` positive as permeate
accumulates. A positive sum means more has left as permeate than was drawn from source — the vessel is losing volume —
so feed on. This is the only place in the estate where the two balances are summed for control, and the reason
`WeightDelta` exists.

`FeedingStart` publishes `Feed Set Speed` only; `Feeding` publishes `Feed ON` = `"true"` with the setpoint publish
commented out, and its 1 s timer writes `Status` = `"Filtering"`. `Recirculating` sets `chart.Recirculation_Complete =
0`, publishes `Recirc Set Speed` and `Recirc ON` = `"true"`; its 1 s timer writes `SFC-Msg` = `"Waiting for Permeate
Mass to reach <Start_Volume * Num_Diavolumes * Density> g"`. End of filtration, 1 h timeout: `abs(tag(…"WT-02
(Permeate Weight)")) >= tag(…Start_Volume) * tag(…Num_Diavolumes) * tag(…Density)`. Inside parallel 2, `4 4`
short-circuits the recirc branch on `tag(…WeightDelta/Alarms.HasActive) || tag(…P1 Value/Alarms.HasActive)` and `0 6`
/ `1 6` end the makeup branch on `{Recirculation_Complete} ||` either alarm — `Recirculation_Complete` is the normal
exit, the alarm terms the abnormal one. `AlarmCheck` here is the full version: it names **both** alarms, and its
`else` branch writes `"Target DiaVolumes Reached - Press Continue to End Batch"` and `Status` = `"Completed"`.
`Filter` and `FillandFilter` test only P1 and have no `else`. Reads `StirrerSP`, `FPumpSP`, `RPumpSP`, `Start_Volume`,
`Num_Diavolumes`, `Density`.

## FillthenFilterwMakeup

Fill to `Start_Volume`, hold for the valve change, then the same constant-volume makeup filtration as `DiaFiltration`
but stopping on `Target_Volume * Density` permeate mass instead of diavolumes. Chosen when one run must both charge
the rig and buffer-exchange it.

```
__begin → Start → ZeroFBalance ⇄ Sleep → Feeding → FComplete → Sleep → jump F → anchor F
  → parallel 1 (double balance zero, 9 3) → 11 14 tries>=3 → jump A → ScaleFail
                                            12 14 both<3   → parallel 2 (9 17, makeup filtration)
  → AlarmCheck → cClearingAlarm | Clear_Prompt → __end1
```

Identical to `DiaFiltration` from parallel 1 on, except: `Recirculating`'s timer and `FeedingDone` compute `TargetMass
= Target_Volume * Density` (both also read `Start_Volume` and `Num_Diavolumes` into locals and never use them — dead
code from the `DiaFiltration` copy); the completion transition drops the `abs()` — `tag(…"WT-02 (Permeate Weight)") >=
(tag(…Target_Volume) * tag(…Density))`; `FinishingUP2` says `"Target Permeate Mass Reached - Press Continue to End
Batch"`; and parallel 2 has **no** `cancel-condition` attribute at all where `DiaFiltration` has a blank one. Reads
`StirrerSP`, `FPumpSP`, `RPumpSP`, `Start_Volume`, `Target_Volume`, `Density`.

## TakeRunData

Not a unit operation — a historian bracket. Start it, run the rig manually, press Continue, and the report covers
`Batch_Start`..`Batch_End`. Four steps: `__begin` → `Start` →
[`tag("[default]"+{Building}+"/"+{RoomFloorBench}+"/TFF/Prompt-Continue")`] → `Clear_Prompt` → `__end1`. `Start`
writes `SFC-Msg` = `"Collecting Run Data, Press Continue to Finish"`, `Status` = `"Running"`, `Prompt-Continue` =
`"false"`, `Continue_Visible` = `"true"`. `Clear_Prompt` is the standard terminal step: blank `SFC-Msg`, `Status` =
`"Completed"`, both prompt tags `"false"`, `Batch_End`, `TFFReport.Report`, sleep 3, `Status` = `""`, sleep 2,
`ElapsedTime` = 0. It publishes **nothing** to MQTT, reads no recipe parameter, and has no `ScaleFail`, `AlarmCheck`
or pump handling; its `onAbort` stops no pumps, which is the only chart where that is correct. `Status` = `"Running"`
is unique to this chart.

## The Status / SFC-Msg / SFC-ID / prompt handshake

Five tags under `[default]{Building}/{RoomFloorBench}/TFF/`, types read live from dev:

| Tag | Type | Written by | Read by |
|---|---|---|---|
| `SFC-ID` | String | Start button, from the `system.sfc.startChart` return | Stop / Pause / Resume buttons; `TFFHeader` for `system.sfc.getVariables` |
| `Status` | String | every chart step, `onCancel`, `onAbort`, Pause/Resume | `Flux`, `TimeToCompletion`, `WeightDelta` expressions; HMI colour and enable bindings |
| `SFC-Msg` | String | every chart step and every 1–3 s timer script | one HMI label |
| `Prompt-Continue` | Boolean | chart steps write `"false"`; Continue button writes `1` then `0` | chart transitions |
| `Continue_Visible` | Boolean | chart steps; Continue button writes `0` | `meta.visible` of the Continue button |

`Status` vocabulary, exhaustive: `Initializing`, `Filling`, `Filtering`, `Running` (TakeRunData only), `Completed`,
`Stopped` (alarm), `Stopping` (ScaleFail), `Cancelled` (`onCancel`), `Paused` / `Restarted` (HMI buttons), `""`
(idle), and `"Sequence aborted on Error"`. `Status = ""` and `Status = "Completed"` are load-bearing: `Flux`,
`TimeToCompletion` and `PercentComplete` all return `0.0` on those two values and `WeightDelta` returns 0 on `""`. Any
other terminal string leaves those tags live after the batch ends — exactly what `onAbort`'s sentence does. The prompt
round trip:
```
chart step        Prompt-Continue = "false" ; Continue_Visible = "true"   (button appears)
operator          onClick: Prompt-Continue = 1 ; sleep(1) ; Prompt-Continue = 0 ; Continue_Visible = 0
chart transition  tag("[default]…/TFF/Prompt-Continue")            → advances
next step         Prompt-Continue = "false" ; Continue_Visible = "false"
```
Two real hazards. **The pulse is one second wide** — the button holds `Prompt-Continue` true for `time.sleep(1)` then
clears it, so a transition that misses the window leaves the chart parked on a step whose Continue button has already
hidden itself; recovery is Resume, or re-showing `Continue_Visible` by hand. And **booleans are written as strings**:
steps write `"false"` / `"true"`, and `AlarmCheck` writes `Continue_Visible, "True"`. Ignition coerces all three.

## The command pattern

Commands are never tag writes — every one is a direct publish on the `Chariot` broker connection:
```python
system.cirruslink.engine.publish('Chariot', topic, value, 0, True)   # QoS 0, retain True
system.cirruslink.engine.publish('Chariot', topic, "",    0, True)   # delete the retained copy
```

The second publish is **mandatory for momentary commands**: an empty retained payload deletes the retained message at
the broker. Without it the last command stays on the topic and is redelivered on every RIO reconnect — a retained
`ZeroFBalance` = `"ZI"` re-zeroes the feed balance mid-run after a reboot, a retained `Feed ON` = `"true"` restarts
the pump. The charts apply it **only** to `ZeroPBalance` / `ZeroFBalance`. Level commands — `Feed ON`, `Recirc ON`,
`StirrerON`, `Feed Set Speed`, `Recirc Set Speed`, `StirrerSP`, `TMPressurePID_Mode` — are published retained and left
retained, which is right for a level. Decide momentary vs level before deciding whether to clear. `DiaFiltration` is
off-pattern twice: its `Feeding` and `FeedingDone` publish `Feed ON` at **QoS 1** where everything else in the estate
is QoS 0, and it is the one chart whose clearing publish is commented out (defect 2).

## The balance-zero retry loop

Every chart except `TakeRunData` starts by zeroing one or both balances.

1. The step publishes `"ZI"` to `{Site}/{Building}/{RoomFloorBench}/TFF/HMI_COM/ZeroPBalance` (or `ZeroFBalance`),
   then `""`, then increments `chart.zeroftries`.
2. On the RIO an `mqtt in` on that topic fans out to a `function` that appends `"\r\n"` and hands the string to a
   `serial request` node. Verified in `$NODERED/LC_F3_309-3-2_TFF/`: `ZeroFBalance` → `/dev/ttySer0.1.5` @ 9600,
   `ZeroPBalance` → `/dev/ttySer0.1.6` @ 9600.
3. `"ZI"` is the Mettler-Toledo **MT-SICS "Zero Immediately"** command — zero without waiting for a stable reading
   *(general instrument knowledge, not measured here)*; the appended `\r\n` is the MT-SICS terminator.
4. A second `function` on the same `mqtt in` does `if (msg.payload == "ZI") { msg.payload = ""; }` and republishes to
   the topic retained — **the device clears the retained command too**, which is why the commented-out clear in
   `DiaFiltration` has not caused an incident, but it only helps while the RIO is online.
5. After a 2 s `Sleep` the transition checks the weight is inside ±0.5 g: in band → proceed; out of band → back to the
   zero step; retry limit → `ScaleFail`.

`ScaleFail` is the same in all five charts that have it: `"Scale fail to Zero"` (`"Scale failed to Zero"` in
`Filter`), `Status` = `"Stopping"`, stamp `Batch_End`, run `TFFReport.Report`, sleep 3, blank `Status` and `SFC-Msg`,
sleep 2, zero `ElapsedTime`, then `true` → `__end1`. It does **not** stop the pumps — acceptable only because no pump
has started at that point in the sequence. The band check compares a `String` tag against a number —
`tag("[MQTT Engine]…WT-01 (Source Weight)") <= 0.5` — and every MQTT Engine tag is `dataType: String`. The `Flux` and
`TimeToCompletion` expressions explicitly guard `toString(...) = ""`; these transitions do not, and `abs()` of an empty
string throws. A balance that has not published since gateway restart stalls or aborts the chart here rather than
timing out cleanly.

## Confirmed defects in the SFC layer

Verified on both gateways.

1. **`chart.zeroptries` is never incremented** — `grep -c "chart.zeroptries" */sfc.xml` = 0 for all six, while
   `chart.zeroftries += 1` appears once in `Fill` and `Filter`, twice in `DiaFiltration`, three times in
   `FillandFilter` and `FillthenFilterwMakeup`. So **`Filter` can never reach `ScaleFail`**: its `ZeroPBalance`
   increments `zeroftries` while the escape transition is `{zeroptries} >= 3`, so a permeate balance that will not zero
   loops `ZeroPBalance → Sleep → ZeroPBalance` forever, publishing `"ZI"` every 2 s with no operator message. And in
   every parallel double-zero block both branches increment the same counter, so `cancel-condition="{zeroftries} >=3 ||
   {zeroptries} >=3"` fires after 3 attempts *combined*, not 3 each. Correct: one counter per balance, each transition
   testing the counter its own step increments.
2. **`DiaFiltration` does not clear its retained zero commands.** Lines 255 and 280 on `$PROD` (240 and 265 on `$DEV`)
   are `#system.cirruslink.engine.publish('Chariot', tagname, "", 0, True)` — commented out in both `ZeroFBalance` and
   `ZeroPBalance`. Uncomment both; the device-side self-clear only masks it.
3. **`onAbort` writes a sentence into `Status`** (`writeAsync(Status, "Sequence aborted on Error")`), defeating the
   `Status = ""` / `"Completed"` guards and leaving `Flux` computing against a dead run. The message belongs in
   `SFC-Msg`, which the same handler already sets.
4. **`TFFReport` hardcodes its own gateway name** — `$PROD/…/script-python/TFFReport/code.py` builds history paths as
   `"[SQLServer/ignition-wz02163d:default]" + …`, the `$DEV` copy says `ignition-wa03593d`. Move it between gateways
   and it silently reads the wrong historian.

Three defects documented in the parent skill also change how these charts behave, and are re-stated here because
`AlarmCheck` depends on all three: **`WeightDelta` on `F3/309-3-2` sums `[MQTT Engine]LC/AP31/299-4/TFF/SERIAL/WT-01`
and `WT-02`** — a different bench, so every `AlarmCheck` scale-delta decision on this skid is driven by another skid's
balances; **the pipeline `TFF_Parent/TFF_Alarms` does not exist** (no `com.inductiveautomation.alarm-notification`
folder in `TFF_Parent` on either gateway), so the two alarms raise and drive `Alarms.HasActive` but notify nobody; and
**`TimeToCompletion` multiplies then divides by `Density`**, which cancels exactly and is a no-op.

## Writing a new unit operation

**Skeleton.** Every chart is `__begin → Start → <zero> → <do work> → <finish + prompt> → Clear_Prompt → __end1`, plus
`ScaleFail` off the retry limit and `cClearingAlarm` off the alarm branch. Keep those step names: the HMI and the audit
trail read like the chart. **Mandatory parts:** `__begin` with all nine parameters in the order above; `Start`; at
least one balance zero with its 2 s `Sleep`; a terminal step that stamps `Batch_End` and calls
`TFFReport.Report(chart.Site, chart.Building, chart.RoomFloorBench)`; `Clear_Prompt`; `__end1`; `ScaleFail`. `onCancel`
and `onAbort` are not optional — copy `Fill`'s, which stop the stirrer and both pumps, stamp `Batch_End`, report, and
blank `Status` / `SFC-Msg` / `ElapsedTime`.

**Tags to maintain.**

| Tag | Rule |
|---|---|
| `Status` | a value from the existing vocabulary; `"Completed"` on the success path, `""` at the end |
| `SFC-Msg` | say what the chart is waiting for, in units; `""` at the end |
| `Prompt-Continue` | false before you show the button; never leave it true |
| `Continue_Visible` | true only while a prompt is genuinely pending; false on every exit |
| `Batch_End` | `system.date.now()` on **every** terminal path, including `ScaleFail` and the alarm path |
| `ElapsedTime` | `0` after the final `Status` write, with the 2 s gap the existing charts use |

**Mistakes to avoid.**

- Reading `Sel_Method` in a chart — the launcher already dispatched on it, and reading it again lets the tag and the
  running chart disagree.
- Putting `Site` in a `[default]` path, or leaving it out of an MQTT topic; publishing a momentary command without the
  paired `""` publish.
- Testing a counter your step does not increment, or sharing one retry counter between two parallel branches. Use
  `zeroftries` for the feed balance and **actually increment** `zeroptries` for the permeate balance.
- Comparing an `[MQTT Engine]` tag to a number without `tofloat()`, or without guarding `""`.
- Leaving `AlarmCheck` with no `else` branch when the chart can complete normally through it — `Filter` and
  `FillandFilter` have that hole and fall through with a stale `SFC-Msg`.
- Adding a `Sleep` to solve a race; the 1–3 s sleeps are already why the Continue pulse is fragile. Use a transition
  on a readback tag instead.
- Forgetting the blast radius: `TFF_Parent` has 20 children on PROD, and all 20 inherit the change when it is saved.
