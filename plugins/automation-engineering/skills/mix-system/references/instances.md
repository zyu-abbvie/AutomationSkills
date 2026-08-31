# Mix instances, their divergences, and standing up a new bench

There is no parent project in this family. Every instance below has `parent: ""` in `project.json` and
carries its own copy of every resource. **Nothing propagates.** A fix to `LNP_418` does not reach
`LNP_beta`.

## Inventory

### prod — `$PROD` (Ignition 8.1.28, `wz02163d`)

| Project | `title` | Addressing | Resources | Notes |
|---|---|---|---|---|
| `LNP_418` | `LNP_R13_418` | `Site=LC`, `Path=R13/418-1-1/LNP` | 89 | **Canonical.** Only instance with the arithmetic in a script (`ignition/script-python/LNP/`). Has `views/charts` and `views/main`. |
| `LNP_AP31` | `LNP_AP31` | `Site=LC`, `Path=AP31/276-4-1/LNP` | 87 | Logic in view bindings. Largest `main` view (323 KB, 6560 lines). |
| `LNP_beta` | `LNP_beta` | `Site=LC`, `Path=R13/228-1-1/LNP` | 87 | Logic in view bindings. Carries duplicate competing topic names. |
| `LAI` | — | none | **3** | Stub. `description: "LAI for Irvine "`. Contains only an `ignition/` folder. Not a working project. |

`LNP_418`'s description reads `"LNP automation system for $18"` — a truncation of `R13 418`, not a
currency value.

### dev — `$DEV` (Ignition 8.3.7, `wa03593d`)

| Project | Addressing | Resources | Notes |
|---|---|---|---|
| `LNP` | `Site=LC`, `Path=R13/228-1-1/LNP` | 87 | Logic in view bindings. |
| `Mix_Demo` | `Site=LC`, `Path=R13/228-1-1/LNP` | 87 | **A copy of `LNP_beta`** — the two `main` views differ by 2 bytes in 244 KB. |
| `LNP_opt` | `Site=LC`, `Building=R13`, `RoomFloorBench=228-1-1`, `PumpQty=3`, `PC01_Site=LC`, `PC01_Building=R8`, `PC01_RoomFloorBench=133-1-1` | 92 | **The refactor.** Three shared script libraries. `views/main` only — no `charts`. |
| `LAI_Lab` | `Site=IRVINE`, `Building=RD3`, `RoomFloorBench=2201`, `PumpQty=3` | 84 | Skeleton — see below. |
| `Archive_LNP_beta_2026-03-26_1625` | — | — | Snapshot. Do not edit, do not assume current. |

## The shared-`Path` hazard

**`LNP_beta` (prod), `LNP` (dev) and `Mix_Demo` (dev) all carry `Path` = `R13/228-1-1/LNP`.**

All three therefore build the identical topic root `LC/R13/228-1-1/LNP` and the identical readback root
`[MQTT Engine]LC/R13/228-1-1/LNP`. Setpoints are published **retained**, so a value written by any of
them persists on the broker for whoever subscribes next.

Whether a dev session can move prod hardware depends entirely on which physical broker `Chariot`
resolves to on each gateway, which is gateway configuration and is **not** visible in a project backup.
Per the `mqtt-integration` skill the dev broker is `10.72.167.253` and prod is `10.94.132.35`, and
every field device publishes to prod. Confirm the `Chariot` mapping on the dev gateway before you
touch `Mix_Demo` or `LNP` with a pump connected. Do not assume "it's the dev project so it's safe".

Related: `LNP_opt` uses convention B but points at the **same bench** (`R13` + `228-1-1`), so it is a
fourth project addressing `R13/228-1-1` — with a different topic shape.

## `LAI_Lab` is a skeleton

Do not describe LAI as implemented. Verified state:

- Its **entire live MQTT surface is one tag**: `IRVINE/RD3/2201/LAI_Lab/Chiller01/TT-01 (Process Temp)`,
  bound through `[MQTT Engine]`.
- The only pump topics referenced anywhere in its views are `PU01/PumpStatus`, `PU01/PumpVolumeSP`,
  `PU02/DO`, `PU02/HMI_COM`. There is no setpoint arithmetic and no command path.
- `RoomFloorBench` is the **integer** `2201`. Every other instance uses a string. It formats fine but
  breaks anything calling `.strip()` or `.split('-')` on it.
- Its `main` view is 112 KB / 2756 lines — roughly half the size of a working LNP view.

### The LAI address disagreement

| Source | Address |
|---|---|
| `LAI_Lab` `session-props` | `IRVINE` / `RD3` / `2201` |
| Node-RED backup directories | `IRVINE_RD2_TBD_LAI_lab`, `IRVINE_RD2_TBD_LAI_clinic` |

`RD3` vs `RD2`, and `TBD` for the bench. **Both Node-RED directories are empty** — no flow export at
all, so there is no device-side contract to read. Resolve the building and get a bench number assigned
before wiring anything; a wrong `Building` silently addresses a different room.

## MSP does not exist yet

There is no MSP mix project on either gateway. `SM_DPD_microsphere` (prod, 75 resources) is **not** one
— its only Perspective view is `Cam_Replay`, i.e. camera replay, and it has no pump topics or setpoint
logic. Do not use it as a template.

Standing up MSP means creating a new instance from this convention.

## Standing up a new mix instance

Ordered, with the traps that actually bite.

1. **Pick the template deliberately.** Copy `LNP_418` if you want the arithmetic in a script — it is
   the only instance with it in one place, and it is documented. Copy `LNP_opt` if you need the valve
   manifold or a cross-building pump. Copying `LNP_beta`/`Mix_Demo` inherits their duplicate topic
   names and their view-embedded arithmetic. Do not copy `LAI_Lab` expecting a working system.

2. **Choose one addressing convention and use it throughout.** Convention A (`Site` + `Path`) or
   convention B (`Site` + `Building` + `RoomFloorBench`) — see `SKILL.md`. Mixing them within one
   project is how you get a panel that reads one bench and writes another. If you use B, keep
   `RoomFloorBench` a **string**.

3. **Set the coordinates before anything else, and verify them against the broker.** Every topic is
   built by concatenation, so a wrong coordinate is silent:

   ```bash
   MQTT_HOST=10.94.132.35 ${CLAUDE_PLUGIN_ROOT}/bin/mqtt-probe watch '<Site>/<Path>/#' --seconds 20
   ```

   **Confirm the address is not already in use.** Three projects already collide on
   `R13/228-1-1/LNP`; do not make it four.

4. **Fix the pump identifiers up front.** `PU1` vs `PU01` and `PU4` vs `PU04` are topic strings, not
   cosmetics, and the family is inconsistent. Decide the padding, write it down, and make every topic
   and every binding agree. Then check which of the drifted names the device actually publishes
   (`command-contract.md`) — bind to the live one and delete the other.

5. **Establish the pump inventory and its ceilings.** `LNP_418` assumes four pumps with `PU1`–`PU3`
   fixed at 200 mL/min and `PU4` tubing-dependent. `LNP_opt` assumes syringe pumps capped at 50 and a
   peristaltic at 600, with minimums. Neither table transfers. Get the real limits for the installed
   hardware, and if a pump's ceiling depends on consumables, publish it as a tag the way
   `FeedMaxFlowRate` is rather than hardcoding.

6. **Route every publish through one module with one rounding rule.** The `DECIMALS = 3` history in
   `process-math.md` is what happens otherwise. A `publish()` call written directly into a view handler
   is the defect, not a shortcut.

7. **Get retain and QoS right per class.** Setpoints retained, commands not retained and QoS 1. A
   retained command re-fires on reconnect.

8. **Do not inherit the safety theatre.** `SafetyChecks` has three stub checks that return safe
   unconditionally, and `validateOperation` calls all four so it reads as comprehensive. If you copy it,
   either implement the stubs or delete them so the next engineer is not misled. The E-stop read in
   `checkSystemInterlock` is commented out.

9. **Verify the whole path per pump before handover.** For each pump: publish a setpoint, confirm the
   readback tag moves, send start, confirm `PumpStatus` goes to `'1'`, send stop, confirm `'0'`. A
   `PU4`-style pump needs `HMI_COM/DI(Pump On Off)`, not `PumpCommand` — that is the single most common
   "the command does nothing" cause.

   ```bash
   ${CLAUDE_PLUGIN_ROOT}/bin/ign-validate $DEV/<NewProject>
   ${CLAUDE_PLUGIN_ROOT}/bin/plugin-selfcheck
   ```

10. **Point alarms at a pipeline that exists**, and record the bench in `estate-map` so the next person
    can find it.

See the `equipment-onboarding` skill for the parts common to every equipment type, and `pitfalls` for
the estate-wide traps that are not mix-specific.

## Divergences summary

What differs between instances that look interchangeable:

| Dimension | Spread |
|---|---|
| Addressing | `Site`+`Path` (5) vs `Site`+`Building`+`RoomFloorBench` (2) |
| Pump IDs | `PU1`–`PU4` · `PU1`/`PU2`/`PU04`/`PC01` · `PU01`/`PU02` |
| Flow ceilings | 200 mL/min fixed · 50/600/500 with minimums · runtime from tubing tag |
| Logic location | project script (2) · view bindings (5) |
| `views/charts` | present on `LNP_418`, `LNP_AP31`, `LNP_beta`, `LNP`, `Mix_Demo`; absent on `LNP_opt`, `LAI_Lab` |
| Valve manifold | `LNP_opt` only |
| Cross-building pump | `LNP_opt` only (`PC01` in R8) |
| Publish error handling | `(success, error)` tuples in `LNP_opt`; raises in `LNP_418` |
| `RoomFloorBench` type | string, except integer on `LAI_Lab` |
