# Equipment taxonomy, site and building codes

Every count below is from
`doc/Ignition-WZ02163D_Ignition-backup-20260828-1137/projects/` (prod, 114 projects) unless marked
DEV, which is `doc/Ignition-WA03593D_Ignition-backup-20260828-1312/projects/` (40 projects).
"Instances" counts real equipment projects and excludes the parent/template itself.

## How to read a project name

```
<EQUIP><nn> - <BUILDING> - <ROOM> - <FLOOR> - <BENCH>        site omitted when LC
   TFF        R8            320      3        1              -> TFF-R8-320-3-1
   RX02       R13           323      3        A              -> RX02-R13-323-3-A
```

The name is a label, not a parser. `Extruder-AP31-4-273` and `Filter-Test-ABA-6-120` list floor
before room. `DU-LC-R13-416-4-1` is the only project that inserts the site explicitly.
`BWC-F3-Portable` says F3 and its session props say `Building: R13`. **Read
`com.inductiveautomation.perspective/session-props/props.json` → `custom` for the truth.**

## Equipment prefixes

| Prefix | What it is | Measures / controls | Parent | Instances |
|---|---|---|---|---|
| `TFF` | Tangential Flow Filtration skid | feed/retentate/permeate pressure `PT-01…04`, source + permeate weight `WT-01/02`, conductivity `CT-02/03`, temperature `TT-02/03`, agitator `AG-01`; controls feed and recirc peristaltic pumps (speed + direction), pinch valve `PV-01`, stirrer, TM-pressure PID | `TFF_Parent` (20 of them) | **23** — 3 are standalone: `TFF-F3-415-4-1`, `TFF-R8-320-3-2`, `TFF-Teller-BSL3-2-1` |
| `RX` | Reactor skid | temperature control unit `TCU1` (`TT-01` process, `TT-02` internal, `TT-03` setpoint + feedback, `FB-01/02`), agitator `AG-01` PV/Status, dosing pumps `PU1`/`PU2` (`ActualVol`, `Pump_FlowRate`) | `RX_Parent` (9 children incl. `IRVINE_RD2_364-1_3CM`) | 8 |
| `PC` | Pump Cube | peristaltic pump control cubes; `PCTE` and `PCdHA` are named variants at `R8/133-1-5` for the Tropoelastin 3CM (holding the TE and the dHA) | `PC_Parent` (7), `Copy_of_PC_Parent` (1 — `PC03`), `PC_Parent_V2` (1 — `PC07`) | 9 |
| `FC` | Fraction Collector | fraction collection for chromatography and for the MPDD | `FC_Parent` (5 children — one is `Extruder-AP31-4-273`, which is not a fraction collector) | 4 |
| `VO` | Vacuum Oven | oven temperature / vacuum | `VO_Parent` (2); `VO01-F3-309-3-1` is standalone | 3 |
| `FCS` | Flow Chemistry Skid | Equilibar back-pressure regulator `PR-01`, two pumps with flow + pressure, J-Kem temperature controller `TT-01`, balance `WT-01`, two chiller subtrees `TCU1`/`TCU2` | none — **standalone**, carries its own full view set | 1 |
| `LF` | Leaf Filter | filtration test rig (PDST-API) | `LF_Parent` | 1 (DEV also has `LF01-R13-218-2-1`, plus a childless `LF_Parent_2`) |
| `CC` | Chiller Control skid | chiller process / internal temperature and setpoint | `CC_Parent` | 1 |
| `Chiller` | chiller control, not on `CC_Parent` | `Chiller01-R14-212-2-1`; `ACX-ACX-Room2024-ChillerControl` is the ACX-site chiller on `CA_Template` | none / `CA_Template` | 2 |
| `WM` | Wetmill — IKA Magiclab, with peristaltic pump communication | wet milling | `WM_Parent` is inheritable with **zero** children; `WM_Parent1` is a dated import, `inheritable: false` | 0 |
| `CAL` | gas/liquid flow **calibration station**, not a generic calibration project | Alicat mass flow controller (`Gas Type`, `Flow Range (sccm)`, `Accumulated (scc)`, volumetric flow) plus a syringe pump (`Diameter (mm)`, `Tare`, `Delayed Start`); recipe tags at `R8/311-3-1/CAL01/Recipe Parameters/` | none — standalone, own `Header/CalHeader` | 1 |
| `AM` | Acoustic Mixer | "Accoustic Mixer Application" (sic, in the description) | none | 1 |
| `PSM` | Power Supply Monitoring | power supply state | **`CA_Template`**, not `PSM_Parent` — `PSM_Parent` is `inheritable: false` and childless | 2 |
| `DU` | MPDD Syringe-pump Dosing Unit | syringe-pump dosing | none | 1 |
| `BWC` | Bead Washing Column | bead wash steps | none | 1 |
| `FD` / `FDHum` | Filter Dryer / Filter Dryer + CellKraft humidifier, both at F3 309-3-1 | drying; `FDHum` adds humidification | none | 1 each |
| `TP` | Temperature Probe project | standalone probe logging | none | 1 |
| `PT` | Pressure Transmitter monitoring | transmitter readings; prod `PT_01`, DEV `PT` and `PT_Opt` | none | 1 (2 in DEV) |
| `Extruder` | extruder at AP31-4-273 | screw speed, throughput, solid/liquid flow; tags live at `[default]GWF/_Process 11 UDP_/Tags/` — **not** the site/building scheme | `FC_Parent` | 1 + `Extruder-AP31-4-273_BO` |
| `OscRXPump` | Oscillatory Baffled Reactor pump | pump for the OBR at `R8/133-1-20` | none | 1 |
| `AKTA` | Cytiva AKTA chromatography pump control box (`ABA_AKTA`) | AKTA pump control at the ABA site | none | 1 |
| `Mobius` | single-use bioreactor | `Mobius_100L` at `R14/120-1-L-100L`; the 200 L unit at Martillac (FR) is monitored by `Martillac-Alarms` over OPC UA, tags at `[default]Martillac/` | none | 1 |
| `Creon` | a reactor family | `Creon_F3-416_Reactors` and `Creon_R8-133_Reactors` ("Creon R8-133 reactor control"). **`Creon_R8-133_Reactors` is the only `enabled: false` project in either gateway.** The word "Creon" is never expanded anywhere in the backups | `Creon_Parent` (1 child) | 2 |
| `Filter` / `Filter2` / `Vmax_Filter-Test` / `Filter_Trender` | filter test and trending rigs | `Filter-Test-ABA-6-120`, `Filter2-Test-ABA-6-120` (ABA 6th-floor lab 120), `Vmax_Filter-Test-R8-133-1-20` (title "Vmax Filter Tester"), `Filter_Trender-RD2-364-1` ("TFF filter trender for Tropoelastin") | none | 4 |
| `Syringe_pump_comm` | ChemX syringe pump communications test | serial comms trial at `R13/231-2-1` | none | 1 |
| `Laser_Reactor_Simon` | laser reactor rig at `R8/133-1-10` | tags include `UA`, `UA_loss`, `T_reactor`, `chiller/hex01(InternalTemp)`, `hex07(ProcessTemp)` | none | 1 |
| `FLEX01` (DEV) | "Component-based experiment builder for FLEX01 reactor (R8, 320 mL, 3-zone)" | holds per-RIO config tags at `[default]R8/FLEX01/RIOs/RIO_01/*` and live tags under `R8/FLEX01/Live/` | none | 1 |
| `PolarBear_Controller` (DEV) | "Automated controller for Polarbear Plus temp controller" at `R8/133-1-4` | jacket temperature control | none | 1 |

### Prefixes that are not physical equipment

| Prefix | What it actually is |
|---|---|
| `BO` | **Bayesian Optimizer.** `BO_Parent` (107 files, 4 views, root view `Page/BO`) is a closed-loop DoE UI — `Start Optimizer`, `Optimization Mode`, `Push to Hardware`, `Steady State Wait Time (min)`, `L/S Ratio`, `Screw Speed`, `Solid Flow Rate`, `Liquid Flow Rate`, `PAT Feed`. It reads Extruder tags, has `inheritable: false`, and zero children. `Extruder-AP31-4-273_BO` is its companion instance; `Bayesian_Platform` and `Bayesian_Platform_Alpha` are the same family |
| `CA_Template` | "Custom Automation template project" — the generic parent for one-off units (4 children). Ships placeholder sentinels `Site: "Site"`, `Building: "Building"`, `RoomFloorBench: "RFB"` |
| `FT_Parent` | Not an equipment class. Title "VO Project Template", description "Vacuum Oven Parent Project" — a copy of `VO_Parent` (both 88 files / 9 views) whose name no longer matches its content. Zero children |
| Tool projects | `DevSciLabs`, `Equipment_Scheduler` + `EquipmentScheduler`, `ExpMetadata`, `File_Transfer` + `File_Transfer_archive` ("Totally Legal"), `LabFreezers`, `LabelPrinterTool`, `RecipeManager`, `RIO_IP_Tracker`, `Tag_Viewer`, `Camera_Demo`, `camera_2025-10-13_1106`. DEV adds `MCP_Tools`, `Dotmatics_connector`, `Dotmatics_Ignition_API` (+`_old`), `ABC-Alarms`, `Martillac-Alarms`, `Glebs Pager`, `Alarm_system_setpoint`, `Flow_Sensor_Tester`, `Ruben-Test-App` |

### Prefixes that cannot be decoded from the backups — do not guess

| Token | What is actually known |
|---|---|
| `FPT` | `FPT01-R13-Portable`, empty description, 5 views (`Main`, `Embedded/Title`, `Header/Header`, two `Framework/Breakpoint`). Appears as tag segments `FPT` (28 hits) and `FPT01` (26). Meaning unknown |
| `3CM` | `IRVINE_RD2_364-1_3CM`, title "Tropo 3CM", inherits `RX_Parent`, so it is reactor-family work for Tropoelastin. The letters themselves are unexplained |
| `LNP` | `LNP_418`, `LNP_AP31`, `LNP_beta` (DEV: `LNP`, `LNP_opt`). Only text is "LNP automation system for $18 / AP31 / beta". Very likely Lipid NanoParticle, but that expansion appears nowhere in the estate |
| `SM_DPD_microsphere` | `IRVINE`/`RD3`/`2209H`. Microsphere work; `SM_DPD` is unexplained |
| `LAI` | prod `LAI` ("LAI for Irvine", **zero views**), DEV `LAI_Lab` ("LAI lab automation system", `IRVINE/RD3/2201`). Edge dirs `IRVINE_RD2_TBD_LAI_clinic` and `..._LAI_lab`. Expansion unknown. Casing is inconsistent in the tag tree: `LAI_Lab` (50 tags) vs `LAI_lab` (16) vs `LAI_Clinic` |
| `TSWG` | DEV only, `parent: FC_Parent`, description "Extruder in AP31-4-273" — the DEV name for the AP31 extruder work. Probably twin-screw granulation, never written out |
| `Bartsch` | `Bartsch-R13-232-1-1`, "Bartsch tester", child of `CA_Template`, never overrode the placeholder props. Person or vendor name; unknown |
| `GWF`, `_Process 11 UDP_` | the tag namespace the Extruder actually publishes into. Origin undocumented |
| `OsmoTECHPRO`, `Universal`, `pat` | folders present in the DEV tag providers with no matching project. Unknown |

### Tokens that exist only on the edge, never as an Ignition project prefix

| Token | Directory | Ignition counterpart |
|---|---|---|
| `ULT01` | `LC_R13_220-2-1_ULT01` | ultra-low-temperature freezer; feeds the `LabFreezers` project |
| `HUM1` | `LC_F3_309-3-1_HUM1` | `FDHum-F3-309-3-1` |
| `VOVEN1` | `LC_F3_309-3-1_VOVEN1` | `VO01-F3-309-3-1` |
| `FILTER` | `IRVINE_RD2_364-1_FILTER` | `Filter_Trender-RD2-364-1` |
| `Camera`, `Gantry` | `LC_AP31_273-4_Camera`, `Camera Data`, `Gantry` | vision rigs; `Camera_Demo` at `R8/133-1-10` |

### What is actually in `doc/backup_nodered/`

37 directories. **17 hold real groov RIO backup zips** (181 zips total, dated series per device, 17
distinct device IPs, named `<ip-with-underscores>_<date>.zip`). **17 directories are empty
placeholders** — including all five `LC_R8_133-1-1_PC0*`, `LC_R8_133-1-7_TFF`,
`IRVINE_Teller_BSL3-2-1_TFF`, `LC_F3_Portable_FC01`, `LC_F3_416-4-2_TFF`, the three
`ABA_ABA_120-6_*` and both `IRVINE_RD2_TBD_LAI_*` (note the literal `TBD` in the RFB slot). The
remaining 3 hold unrelated tooling (`Backup Tool`, `Label Tool`, `EqSchVideo`). Of the 17 with zips,
17 yield an extractable `node-red/flows.json`, but `IRVINE_RD2_364-1_TFF` and `LC_R8_320-3-1_RX01`
contain no topics at 4+ levels. **An empty directory does not mean no device — it means no backup.**

## Site codes

| Site | Projects | Buildings seen | Notes |
|---|---|---|---|
| `LC` | 77 | `R8`, `R13`, `R14`, `F3`, `AP10`, `AP31` | the main campus; site omitted from project names |
| `IRVINE` | 5 | `RD2`, `RD3`, `Teller` | `Teller` is a building name, not a room |
| `ABA` | 3 | `ABA` | **site == building** |
| `AWA` | 2 | `B830` | |
| `ABC` | 2 | `B5`, `BIO4` | the pilot plant; `ABC-Alarms` monitors it |
| `ACX` | 1 | `ACX` | site == building; `RoomFloorBench` is the literal `Room 2024`, with a space |
| `LU` | 0 prod projects | `B56` | exists only in the tag/topic tree — `LU/B56/12-1/Training/*`, the bench used by `Glebs Pager` |
| `Site` | 2 | `Building` | the `CA_Template` placeholder sentinel. Never valid |

`P1` appears only as a leaked tag root (`[default]P1/2-2-2/Training/Reactor Size`, a topic published
using an Ignition tag path as the topic string). It is not a live building in the project set.

## Building codes

| Building | Site | Projects | Building | Site | Projects |
|---|---|---|---|---|---|
| `R8` | LC | 31 | `B830` | AWA | 2 |
| `R13` | LC | 24 | `B5` | ABC | 1 |
| `F3` | LC | 7 | `BIO4` | ABC | 1 |
| `R14` | LC | 6 | `Teller` | IRVINE | 1 |
| `AP31` | LC | 5 | `ACX` | ACX | 1 |
| `RD2` | IRVINE | 3 | `RD3` | IRVINE | 1 |
| `ABA` | ABA | 3 | `AP10` | LC | 1 |

`Portable` also appears in the room slot rather than the building slot (`BWC-F3-Portable`,
`FPT01-R13-Portable`, edge dir `LC_F3_Portable_FC01`).

## Worked address decodings

| # | Project name | `Site` | `Building` | `RoomFloorBench` | MQTT topic root | `[default]` tag root |
|---|---|---|---|---|---|---|
| 1 | `TFF-R8-320-3-1` | `LC` | `R8` | `320-3-1` | `LC/R8/320-3-1/TFF/` | `R8/320-3-1/TFF/` |
| 2 | `TFF-F3-309-3-2` | `LC` | `F3` | `309-3-2` | `LC/F3/309-3-2/TFF/` | `F3/309-3-2/TFF/` |
| 3 | `RX02-R13-323-3-A` | `LC` | `R13` | `323-3-A` | `LC/R13/323-3-A/RX02/` | `R13/323-3-A/RX02/` |
| 4 | `Extruder-AP31-4-273` | `LC` | `AP31` | **`273-4`** | `LC/AP31/273-4/` | *(uses `GWF/_Process 11 UDP_/Tags/` instead)* |
| 5 | `Filter-Test-ABA-6-120` | `ABA` | `ABA` | **`120-6`** | `ABA/ABA/120-6/` | `ABA/120-6/` |
| 6 | `TFF-B5-2071-2-1` | `ABC` | `B5` | `2071-2-1` | `ABC/B5/2071-2-1/TFF/` | `B5/2071-2-1/TFF/` |
| 7 | `TFF-B830-3S047-3-A` | `AWA` | `B830` | `3S047-3-A` | `AWA/B830/3S047-3-A/TFF/` | `B830/3S047-3-A/TFF/` |
| 8 | `TFF-Teller-BSL3-2-1` | `IRVINE` | `Teller` | `BSL3-2-1` | `IRVINE/Teller/BSL3-2-1/TFF/` | `Teller/BSL3-2-1/TFF/` |
| 9 | `TFF-BIO4-3502-3-1` | `ABC` | `BIO4` | `3502-3-1` | `ABC/BIO4/3502-3-1/TFF/` | `BIO4/3502-3-1/TFF/` |
| 10 | `SM_DPD_microsphere` | `IRVINE` | `RD3` | `2209H` | `IRVINE/RD3/2209H/` | `RD3/2209H/` — no floor or bench at all |
| 11 | `ACX-ACX-Room2024-ChillerControl` | `ACX` | `ACX` | `Room 2024` | `ACX/ACX/Room 2024/` | `ACX/Room 2024/` — contains a space |
| 12 | `DU-LC-R13-416-4-1` | `LC` | `R13` | `416-4-1` | `LC/R13/416-4-1/DU/` | `R13/416-4-1/DU/` — the only name with the site spelled out |

Rows 4, 5 and 11 are why you never parse the project name. **The MQTT topic keeps the site segment;
the `[default]` tag path drops it.** Never build a tag path by string-replacing `/` in a topic.
`IRVINE_RD2_364-1_3CM` is the one unit whose Ignition project name and Node-RED directory name are
identical.
