---
name: equipment-onboarding
description: Stand up a new equipment instance across both pillars of this lab-automation estate - assign site/building/room-floor-bench coordinates and the project name, build the groov RIO Node-RED flow, define the MQTT topic contract, let MQTT Engine create the tags, create the child Ignition project from the right parent, set the Perspective session custom props that drive every indirect binding, enable history, wire alarms and email/Teams notification, and verify before handover. Use when adding a new TFF skid, reactor, pump cube, fraction collector, vacuum oven or any other bench to Ignition, when cloning an existing unit to a new room, when a newly created child project shows blank or bad-quality values everywhere, when deciding whether to inherit from a parent or go standalone, or when you need to know which equipment prefix and parent family a unit belongs to.
---

# Onboarding a new equipment instance

A new bench is **two builds that must agree on one string**: the RIO publishes
`{SITE}/{BUILDING}/{RFB}/{EQUIP}/…` and the Ignition child project declares the same coordinates in
three Perspective session custom props. Get those three wrong and every screen still renders, every
binding resolves to a nonexistent tag, nothing errors. That failure is live in prod (`Bartsch-R13-232-1-1`).

## The checklist, in order

| # | Step | Artifact created | Skill |
|---|---|---|---|
| 1 | Assign coordinates and the project name | the name itself — `TFF-B5-2071-2-1` | this skill |
| 2 | Build / clone the RIO flow | `backup_nodered/<SITE>_<BLDG>_<RFB>_<EQUIP>/<ip>_<date>.zip` | `nodered-rio` |
| 3 | Define the topic contract | topic list, one per point, `HMI_COM` vs telemetry | `mqtt-integration` |
| 4 | Confirm topics arrive at the broker | `mqtt-probe watch '<root>/#'` output | `mqtt-integration` |
| 5 | Confirm MQTT Engine created the tags | `[MQTT Engine]<SITE>/<BLDG>/<RFB>/<EQUIP>/…` | `mqtt-integration` |
| 6 | Create the child project from the right parent | 5 files (see below) | `ignition-resources` |
| 7 | Set `session-props` custom values | `session-props/props.json` `custom` block | this skill |
| 8 | Build the `[default]` derived tags | `[default]<BLDG>/<RFB>/<EQUIP>/…` expression + memory tags | `ignition-resources` |
| 9 | Verify indirect bindings resolve | a Perspective session with live values | this skill |
| 10 | Enable history on the points that need it | `historyEnabled` + `historyProvider: SQLServer` | `sql-historian` |
| 11 | Configure alarms and notification | tag `alarms[]` + an **existing** pipeline | this skill |
| 12 | Validate, then hand over | `ign-validate` clean + the transcript below | `ignition-resources` |

Steps 2–5 and 6–7 are independent. Do not start step 8 before step 5 succeeds: the derived tags
reference MQTT Engine tags by literal path, and a typo there is invisible.

## Addressing and naming

MQTT topic: `SITE/BUILDING/ROOM-FLOOR-BENCH/EQUIP/CATEGORY/POINT`. Ignition project name:
`<EQUIP><nn>-<BUILDING>-<ROOM>-<FLOOR>-<BENCH>`, site omitted when it is `LC`. Node-RED directory:
`<SITE>_<BUILDING>_<ROOM-FLOOR-BENCH>_<EQUIP>`.

| Unit | Project name | `Site` / `Building` / `RoomFloorBench` | Topic root | Node-RED dir |
|---|---|---|---|---|
| TFF, R8 lab 320 | `TFF-R8-320-3-1` | `LC` / `R8` / `320-3-1` | `LC/R8/320-3-1/TFF/` | `LC_R8_320-3-1_TFF` |
| TFF, ABC pilot plant | `TFF-B5-2071-2-1` | `ABC` / `B5` / `2071-2-1` | `ABC/B5/2071-2-1/TFF/` | `ABC_B5_2071-2-1_TFF` |
| Extruder, AP31 | `Extruder-AP31-4-273` | `LC` / `AP31` / **`273-4`** | `LC/AP31/273-4/…` | — |

- **The Node-RED directory is the inverse token order** of the project name. A mapper must reorder,
  not just re-delimit.
- **The project name is not a parser.** `Extruder-AP31-4-273` has `RoomFloorBench` `273-4` — floor
  before room. `Filter-Test-ABA-6-120` has `120-6`. `BWC-F3-Portable` reports `Building: R13,
  RoomFloorBench: 218-2`. **The session props are authoritative, always.**
- `RoomFloorBench` is free text, not a pattern: `Room 2024` (with a space), `126-1-CoC`,
  `120-1-L-100L`, `323-3-A`, `BSL3-2-1`, `3S047-3-A`, `2209H`, and the literal `RFB` all occur.

Site and building code tables, 12 worked decodings, and every equipment prefix with its parent and
instance count are in [references/equipment-taxonomy.md](references/equipment-taxonomy.md).

## Parent / child: what the parent gives you

Prod `TFF_Parent` is 150 files and 15 views. A child inherits **all** of it and overrides only the
identity. **All 52 prod children override exactly one pair:
`com.inductiveautomation.perspective/session-props` and `.../page-config`** — that pair *is* the
per-equipment customization mechanism. After it: `ignition/global-props` 25/52, `views/Page/Main`
22/52, `views/Page/Charts` 15/52, `views/Page/EquipmentDisplay` 14/52, `views/Docks/Menu Horizontal`
14/52.

The minimal child is therefore **five files** — and nothing else:

```
<ProjectName>/project.json
<ProjectName>/com.inductiveautomation.perspective/page-config/{config.json, resource.json}
<ProjectName>/com.inductiveautomation.perspective/session-props/{props.json, resource.json}
```

Real example: `doc/Ignition-WZ02163D_Ignition-backup-20260828-1137/projects/TFF-R8-320-3-1/` has 7 files
and **zero** child-only files; every one overrides a parent file (the two extras are
`ignition/global-props/{data.bin, resource.json}`). Its whole `project.json`, then the `custom` block of
`com.inductiveautomation.perspective/session-props/props.json`:

```json
{"title": "TFF-R8-320-3-1",
 "description": "TFF Unit in the 320 lab in R8.  Medium Scale Unit.",
 "parent": "TFF_Parent", "enabled": true, "inheritable": false}

"custom": {
  "Site": "LC", "Building": "R8", "RoomFloorBench": "320-3-1",
  "Chiller": true, "PinchValve": true, "FeedDir": true, "RecircDir": true,
  "MFM": false, "PH_Meter": false, "ConcentrationPAT": false, "ChartTime": 10 }
```

The first three are the coordinates. The rest are **capability flags** — how one parent's views serve
units with different hardware. They must match the RIO. `TFF-B5-2071-2-1` sets `PH_Meter: true` and
`Chiller: false`, and its flow does publish `ABC/B5/2071-2-1/TFF/AI/PH-01 (pH Meter)` and no chiller
topics. Set a flag true with no topic behind it and the operator gets a permanently blank widget.

**Do not hand-author `props.json` from the `custom` block alone.** It also carries `propConfig`, and in
every TFF child that includes an `onChange` script on `props.auth.user.userName` that calls the LDAP
search web API and writes `CurrentEmail`, `CurrentUser`, `CurrentUPI` and `ExperimentName` into
`[default]{Building}/{RoomFloorBench}/TFF/`. **Alarm notification reads `CurrentEmail`.** Copy a
sibling's `props.json` and change the `custom` values; do not synthesize the file. Two sentinels to
assert against:

- **Prod `TFF_Parent` ships `Site: "", Building: "", RoomFloorBench: ""`**, so a child that forgets the
  override inherits blanks and resolves every binding to `[default]//TFF/…`.
- **`CA_Template` ships the literal placeholders `Site: "Site"`, `Building: "Building"`,
  `RoomFloorBench: "RFB"`**, and its child `Bartsch-R13-232-1-1` never overrode them. That project is
  enabled and live in prod, resolving everything to `[default]Building/RFB/…`. Assert the three props
  are neither empty nor the sentinel strings.

## Parent families and their blast radius

| Parent | Children | Notes |
|---|---|---|
| `TFF_Parent` | **20** | editing it hits 20 live skids |
| `RX_Parent` | 9 | includes `IRVINE_RD2_364-1_3CM` ("Tropo 3CM") |
| `PC_Parent` | 7 | plus `Copy_of_PC_Parent` (1) and `PC_Parent_V2` (1) — three near-identical Pump Cube parents in service at once, 75 files each |
| `FC_Parent` | 5 | includes `Extruder-AP31-4-273`, which is not a fraction collector |
| `CA_Template` | 4 | both real PSM projects inherit this, not `PSM_Parent` |
| `VO_Parent` | 2 | |
| `CC_Parent`, `Creon_Parent`, `LF_Parent` | 1 each | |

52 children, 11 distinct parents, 13 inheritable projects. **Inheritance is exactly one level deep** —
no grandparent chains in either gateway. Then:

- **A `*_Parent` name does not mean `inheritable: true`.** Prod `BO_Parent`, `PSM_Parent` and
  `WM_Parent1` are all `false`, and a child pointing at a non-inheritable parent is invalid. Read
  `project.json`. `parent` is also an **optional key** — 28 of 114 prod files omit it, meaning the
  same as `""`, so use `d.get('parent') or ''`.
- **`FT_Parent` is a misnamed clone of `VO_Parent`** (title "VO Project Template", 88 files / 9 views)
  with zero children — as have `WM_Parent` and `BO_Parent`.
- Three TFF units are **standalone** despite `TFF_Parent` existing — `TFF-F3-415-4-1`,
  `TFF-R8-320-3-2`, `TFF-Teller-BSL3-2-1` — so a fleet-wide parent edit misses them. `FCS-R13-218-2`
  carries a full private view set and is a candidate for parentization.

## Two tag providers, and the hand-written bridge between them

There are **two** tag trees per piece of equipment, and this is the part most often got wrong.

| | `[MQTT Engine]` | `[default]` |
|---|---|---|
| Path | `SITE/BUILDING/RFB/EQUIP/CATEGORY/POINT` — **5–6 levels, site included** | `BUILDING/RFB/EQUIP/…` — **4 levels, site dropped** |
| Created by | MQTT Engine, automatically, from the `#` subscription | you, by hand, in the Designer |
| Data types | **every tag is `String`** | typed: `Float8`, `Float4`, `Int4`, `Boolean`, `DateTime`, `String` |
| Contents | raw telemetry and command echoes | `Status`, `Batch_*`, `Recipe Parameters/*`, `CurrentEmail`, `Flux`, `P1 Value`, `WeightDelta` |
| Referenced by | derived-tag expressions and history bindings | **every Perspective indirect binding** |

Indirect bindings only ever use `{1}` = `session.custom.Building` and `{2}` =
`session.custom.RoomFloorBench` against `[default]`. `session.custom.Site` is **not part of any tag
path** — it appears only when a script concatenates an MQTT topic. The bridge between the two trees is
an expression tag that re-adds the site **by hand**.

## Where the two pillars meet, for four real units

Each row exists in **both** `doc/backup_nodered/` and the prod projects directory:

| Node-RED dir | Topics | Ignition project | Parent | `[default]` root |
|---|---|---|---|---|
| `ABC_B5_2071-2-1_TFF` | 47 under `ABC/B5/2071-2-1/TFF/` | `TFF-B5-2071-2-1` | `TFF_Parent` | `B5/2071-2-1/TFF/` |
| `LC_R8_320-3-1_TFF` | 39 under `LC/R8/320-3-1/TFF/` | `TFF-R8-320-3-1` | `TFF_Parent` | `R8/320-3-1/TFF/` |
| `LC_R13_218-2_FCS` | 44 under `LC/R13/218-2/FCS/` | `FCS-R13-218-2` | **none** | `R13/218-2/FCS/` |
| `LC_R13_323-3-A_RX01` | 21, split `…/RX01/` **and** `…/RX02/` | `RX01-R13-323-3-A` **and** `RX02-R13-323-3-A` | `RX_Parent` | `R13/323-3-A/RX0n/` |

The full path for feed pressure on the first row:

```
transducer → serial into the groov RIO → Node-RED function → mqtt out (retain, QoS 0, 10.94.132.35)
  → topic   ABC/B5/2071-2-1/TFF/SERIAL/PT-01 (Feed Pressure)
  → MQTT Engine `#` subscription creates, dataType String:
            [MQTT Engine]ABC/B5/2071-2-1/TFF/SERIAL/PT-01 (Feed Pressure)
  → hand-built expr tag re-types and re-roots it, and carries the alarm:
            [default]B5/2071-2-1/TFF/P1 Value   Float4, AboveValue vs Recipe Parameters/P1_Max
  → Tag Historian, historyProvider SQLServer  →  TFF_Parent Page/Main tag-history binding
  → indirect binding [default]{1}/{2}/TFF/… ({1}=Building, {2}=RoomFloorBench) → browser
```

**Every literal in that expr tag is per-instance and hardcoded**, and the estate has already failed at
it: on dev, `[default]F3/309-3-2/TFF/WeightDelta` computes from
`{[MQTT Engine]LC/AP31/299-4/TFF/SERIAL/WT-01 (Source Weight)}` and `WT-02` — a *different building's*
scales, so its alarm fires on someone else's weight. When you clone, grep the new project's tag export
for the old coordinates before handover. Two more facts visible only at this level:
`LC_R13_323-3-A_RX01` proves **one RIO can serve two Ignition projects**, so the directory is not a
project key; and `IRVINE_RD2_364-1_3CM` publishes `LC/R8/133-1-5/Filter/SERIAL/PT-05…PT-08` and
`LC/R8/133-1-5/PCTE/HMI_COM/FT01(Totalizer Out)` — a different site and bench — so **topic prefix does
not identify the publishing device**.

## History

Enable history on the **typed `[default]` tags**, not on the MQTT strings: `historyEnabled: true`,
`historyProvider: "SQLServer"`. 148 of 1185 dev `[default]` tags carry history — `Status`, `Batch_*`,
`Flux`, and the whole `Recipe Parameters/` folder. MQTT Engine tags historize as `String`, so a
`MinMax` or `Average` aggregate over them returns nothing useful. Perspective chart bindings are type
`tag-history` and carry a fully-qualified provider literal, 74 occurrences in prod — note the baked-in
driver name `ignition-wz02163d` and provider `mqtt engine`:

```
histprov:SQLServer:/drv:ignition-wz02163d:mqtt engine:/tag:LC/R8/311-3-1/CAL01/SERIAL/PU-01 (Actual…
```

**A chart copied from prod to dev queries a driver that does not exist there and returns an empty
dataset with no error.** See `sql-historian` for the `sqlth_te` / `sqlth_annotations` lookups
(`Get_TagID`, `Get_Annotations`) the parents use.

## Alarms and notification

Alarms live on the `[default]` derived tags, in the tag's `alarms[]`, setpoint bound to a recipe
parameter beside it:

```json
{"name": "Alarm", "mode": "AboveValue",
 "activePipeline": "TFF_Parent/TFF_Alarms",
 "setpointA": {"bindType": "Tag", "value": "[.]Recipe Parameters/P1_Max"}}
```

`activePipeline` is `<ProjectName>/<PipelineName>`. **Confirm the pipeline exists before you name
it.** `TFF_Parent` contains no `com.inductiveautomation.alarm-notification` folder on either gateway,
so the two dev tags pointing at `TFF_Parent/TFF_Alarms` raise alarms that can never notify anyone.
Only **five distinct pipelines exist estate-wide**, and none is per-equipment-family:

| Project | Pipeline | Gateway | Scope |
|---|---|---|---|
| `Martillac-Alarms` | `Martillac_Alarms` | dev | Mobius 200 L bioreactor, Martillac (FR), via OPC UA `Martillac_BioReactor`, tags at `[default]Martillac/` — 85 alarmed tags, the largest consumer by far |
| `ABC-Alarms` | `ABC_Alarm` | dev | ABC pilot plant |
| `Glebs Pager` | `Email_Teams` | dev | the pager rig, 1 alarmed tag at `[default]LU/B56/12-1/Training/AngerLevel` |
| `LabFreezers` | `Alarms` | dev + prod | freezer monitoring |
| `DevSciLabs` | `AWA Alarms` | prod | AWA site |

Every one uses an **Email Notification block with Roster Type "Calculated"** — a Jython snippet inside
the pipeline returning `[{"username": …, "email": [ … ]}]`. Rosters are hardcoded lists of people plus
a Teams channel address, because **Teams delivery is email to a channel address**
(`<id>.abbvie.onmicrosoft.com@amer.teams.ms`); there is no Teams connector anywhere. The better pattern
is dev `TFF_Parent/ignition/script-python/TFFAlarm/code.py`, which derives the roster from the
equipment: it parses the alarm source tag path, reads `[default]<Building>/<RFB>/TFF/CurrentEmail`, and
falls back to a fixed pair on bad quality — one pipeline serving every skid with no per-skid config.
Wire it as `return TFFAlarm.roster(alarmEvents)`.

**SMTP**: one profile, `SMTP_ABBVIE`, hardcoded in 86 project files as `smtpProfile="SMTP_ABBVIE"`.
Config at `<dev backup>/config/resources/core/ignition/email-profile/SMTP_ABBVIE/config.json` — type
`smtp.classic`, relay `pikmrelay.abbvienet.com:2525`, `startTlsEnabled: false`,
`sslProtocols: TLSv1.2`. **That file holds the relay password as an encrypted JWE blob; do not copy it
anywhere.** Prod is 8.1 and keeps its profiles under `<prod backup>/email-profiles/` instead.

## Pre-handover verification

Run all five and paste the output into the handover note. `B=${CLAUDE_PLUGIN_ROOT}/bin`.

```bash
# 1. The project. The importer SILENTLY DROPS malformed resources.
$B/ign-validate <backup>/projects/TFF-B5-2071-2-1
# 2. Every point arriving, and the Heartbeat MOVING (two messages, not one retained one).
#    Quote the topics - they contain spaces and parentheses.
$B/mqtt-probe watch 'ABC/B5/2071-2-1/TFF/#' --seconds 20 --summary
$B/mqtt-probe watch 'ABC/B5/2071-2-1/TFF/Heartbeat' --seconds 12
# 3. Nothing in the gateway log names the new project.
$B/ign logs --search TFF-B5-2071-2-1 --limit 50 ; $B/ign logs --level ERROR --limit 30 --stack
# 4. Both tag trees exist: what MQTT Engine created, and the derived tags you built.
$B/ign tags --provider 'MQTT Engine' --path 'ABC/B5/2071-2-1/TFF' --recursive
$B/ign tags --provider default --path 'B5/2071-2-1/TFF' --recursive
# 5. Every command must MOVE ITS READBACK. The command topic is not state - the ack is an echo on a
#    different topic. Watch both while an operator presses the button, for each HMI_COM point.
$B/mqtt-probe watch 'ABC/B5/2071-2-1/TFF/HMI_COM/Feed ON' --seconds 30 &
$B/mqtt-probe watch 'ABC/B5/2071-2-1/TFF/DO/PU-01 (Feed ON)' --seconds 30
```

If the command moves and the readback does not, the fault is on the RIO, not in Ignition. Check too
that momentary commands publish an **empty retained payload** afterwards, or the pump restarts itself
the next time the RIO reboots — see `mqtt-integration`. Then confirm by eye in a real Perspective
session: no blank widgets, no bad-quality overlays, the chart draws, the header shows the right room.
Record which parent the project inherits and that parent's current child count, so the next person
knows the blast radius before editing it.
