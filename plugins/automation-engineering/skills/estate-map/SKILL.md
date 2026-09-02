---
name: estate-map
description: Orient yourself in this lab-automation estate before touching anything. Explains the two Ignition gateways and their different versions, which one you can drive programmatically and which you cannot, the Ignition/Node-RED/MQTT/SQL architecture and how a value travels from a sensor to a Perspective screen, the site/building/room/bench addressing scheme, and where every artifact lives on disk. Use at the start of any Ignition, Node-RED, MQTT, groov RIO, historian or equipment-integration task, when a question spans more than one of those components, or whenever you are unsure which gateway or environment you are working against.
---

# Estate map

Read this before acting. The single most expensive mistake in this estate is assuming the two
gateways are the same system. They are not: they run **different major versions of Ignition** and
expose **different capabilities**.

## Run this first

```bash
${CLAUDE_PLUGIN_ROOT}/bin/ign capabilities                          # dev (default)
IGN_URL=http://wz02163d:8088 ${CLAUDE_PLUGIN_ROOT}/bin/ign capabilities   # prod
```

It reports version, OS, JVM, whether the REST API exists, whether reads are anonymous, whether
writes are authenticated, and which MCP servers are mounted. One call replaces a page of guessing.

## The two gateways

| | **DEV — `wa03593d:8088`** | **PROD — `wz02163d:8088`** |
|---|---|---|
| Ignition | **8.3.7** (Win Server 2022, JRE 17) | **8.1.28** (Win Server 2019, JRE 11) |
| Projects | 40 | 114 |
| HTTP REST API | Yes, `/data/api/v1/**` | **None — every route 404s** |
| MCP server | Yes, `MCP_Tools` (19 tools) | No |
| Reads | **anonymous** (HTTP 200, no credentials) | n/a |
| Writes | **401** without a token | n/a |
| How you change it | API (gateway config only), Designer, project import | **Designer only** |
| How you inspect it | live API, or the on-disk backup | **on-disk backup only** |

`GET /system/gwinfo` is plain text, unauthenticated, and present on **both** versions — it is the
only reliable cross-version fingerprint. `/data/api/v1/gateway-info` exists only from 8.3.

### What the version split means in practice

- Every `/data/api/v1/**` recipe works on dev and **404s on prod**. Do not write a script that
  "works" and then point it at prod.
- **Gateway event scripts are stored differently.** 8.1 packs all of a project's timer/startup/
  shutdown scripts into one gzipped Java-serialized blob at `ignition/event-scripts/data.bin`.
  8.3 stores plain text at `ignition/timer/<Name>/handleTimerEvent.py`,
  `ignition/startup/onStartup.py`, etc. A tool that only looks for `.py` reports zero scripts for
  every prod project. 8.3 also still carries legacy `data.bin` for un-migrated imported projects
  (e.g. dev `Bayesian_Platform_Alpha`), so check both shapes.
- Promoting dev → prod crosses a major version boundary. Treat it as a migration, not a copy.

## Architecture: how a value actually travels

```
  instrument (balance, pressure transducer, chiller, pump)
      │  RS-232/485  ·  Modbus TCP  ·  discrete + analog I/O
      ▼
  Opto 22 groov RIO / EPIC edge device  ──  runs Node-RED
      │   groov-io-read/write, serial in/request, modbus-client
      │   function nodes hold the logic
      ▼   mqtt out   (retain=true, QoS 0)
  MQTT broker      dev 10.72.167.253:1883   ·   prod 10.94.132.35:1883
      ▼
  Ignition MQTT Engine (Cirrus Link), custom namespace subscribed to `#`
      ▼   auto-creates one tag per topic, ALWAYS dataType String
  [MQTT Engine]ABC/B5/2071-2-1/TFF/SERIAL/PT-01 (Feed Pressure)
      ▼   a hand-built expression tag re-types and re-roots it, and carries the alarm
  [default]B5/2071-2-1/TFF/P1 Value        Float4
      ├──▶ Tag Historian  ──▶  SQL Server (provider "SQLServer", 1-month partitions)
      └──▶ Perspective, via an indirect binding [default]{1}/{2}/TFF/…  ──▶  browser
                │
                │  operator presses a button
                ▼
  system.cirruslink.engine.publish(server, '…/HMI_COM/Feed ON', 'true', 0, True)
      ▼   NOT a tag write
  RIO `mqtt in` ──▶ coerce the string ──▶ groov-io-write ──▶ publish the readback on AI/AO/DO
```

The `[MQTT Engine]` → `[default]` step is where most of the per-instance wiring lives, and **every
literal in that expression tag is hardcoded per bench**. The estate has already got this wrong: on
dev, `[default]F3/309-3-2/TFF/WeightDelta` computes from
`[MQTT Engine]LC/AP31/299-4/TFF/SERIAL/WT-01` — a *different building's* scales — so its alarm fires
on someone else's weight. When cloning a bench, grep the new project's tag export for the old
coordinates before handover.

The two pillars are **co-equal**: the RIO owns the device and the control logic; Ignition owns the
tag model, history, HMI, and alarming. MQTT and SQL are the connective tissue. A fault can live in
any of the four, which is why triage crosses all of them — see the `triage` skill.

## Addressing: one scheme, used everywhere

```
SITE / BUILDING / ROOM-FLOOR-BENCH / EQUIPMENT / [CHANNEL /] TAG (Description)
 LC  /   R8    /      320-3-1       /   TFF    /   SERIAL   / WT-01 (Source Weight)
```

The same coordinates appear as an MQTT topic, an Ignition project name (`TFF-R8-320-3-1`), a tag
path, and a Node-RED backup directory (`LC_R8_320-3-1_TFF`). Learn it once.

- **SITE** — `LC`, `IRVINE`, `ABA`, `ABC`, `AWA`, `LU`
- **BUILDING** — `R8`, `R13`, `R14`, `F3`, `P1`, `B56`, `RD2`, `RD3`, `AP31`, `B830`, `B5`, `BIO4`, `Teller`
- **CHANNEL** — the sub-namespace, and it carries meaning:
  - `SERIAL/` — readings from serial instruments
  - `HMI_COM/` — **bidirectional**: commands in, state back out, on the same topic
  - `Calc_Val/` — values computed on the RIO
  - housekeeping at equipment root: `Heartbeat`, `IP_Address`, `CPU (Usage)`, `CPU (Temp)`, `API`

Tag paths mirror it: `[default]F3/309-3-1/FD1/Batch_Running`, or
`[MQTT Engine]LC/R8/320-3-1/TFF/SERIAL/PT-01 (Feed Pressure)`. Per-equipment identity is carried in
Perspective `session-props/props.json` under `custom`: `Site`, `Building`, `RoomFloorBench`,
`EquipmentNum` — which is how one parent project serves many benches through indirect bindings.

## Project inheritance

Exactly **one level deep** — there are no grandparent chains. On prod: `TFF_Parent` has 20
children, `RX_Parent` 9, `PC_Parent` 7, `FC_Parent` 5, `CA_Template` 4.

**A `*_Parent` name does not mean it is inheritable.** Prod `BO_Parent`, `PSM_Parent` and
`WM_Parent1` all have `"inheritable": false`. Always read `project.json` rather than trusting the
name. `parent` is optional — 28 of 114 prod projects omit the key entirely, which means the same as
`""`.

## Where things live

| What | Where |
|---|---|
| Connection details for the estate | `doc/credential.yaml` — **read it, never copy secrets into code** |
| Prod gateway backup (source of truth for prod) | `doc/Ignition-WZ02163D_Ignition-backup-20260828-1137/` |
| Dev gateway backup | `doc/Ignition-WA03593D_Ignition-backup-20260828-1312/` |
| Ignition projects inside a backup | `<backup>/projects/<ProjectName>/` |
| Node-RED / groov RIO device backups | `doc/backup_nodered/<SITE_BLDG_ROOM_EQUIP>/<ip>_<date>.zip` |
| Ignition 8.1 reference manuals (PDF) | `doc/Ignition_Manual/DOC-81-*.pdf` |
| Live OpenAPI spec (860 operations) | `http://wa03593d:8088/openapi.json` |
| Shared pitfall knowledge base | SQL Server `dbo.MCP_Pitfalls`, via the `pitfalls` skill |

## Credentials

Run `${CLAUDE_PLUGIN_ROOT}/bin/ign config` to see what is configured and where each value came from,
with secrets masked. The tools read, highest precedence first: a command-line flag, an environment
variable (`IGN_URL`, `IGN_API_TOKEN`, `IGN_PROD_HOSTS`, `MQTT_HOST`, `MQTT_USERNAME`,
`MQTT_PASSWORD`), then `automation.local.yaml` at the repo root, then the estate's existing
`doc/credential.yaml`, then a dev-pointing default.

`--env dev` / `--env prod` selects which section of the config file is used. Both config files are
gitignored. **Never paste a credential into a file you create, and never into a command line** — put
it in `automation.local.yaml`, or indirect it through the environment with `${VAR}`.

Two things to know:
- Dev API **reads are anonymous**, and `GET .../resources/find/ignition/database-connection/…`
  returns the DB password as an encrypted JWE blob to any unauthenticated caller. Do not widen
  that exposure, and do not paste those blobs into files or transcripts.
- The `evalScript` MCP tool **does not sandbox** — it executes with the full `__builtin__` module
  available, as the gateway process. Treat it as arbitrary code execution on the gateway.

## Where to go next

| Task | Skill |
|---|---|
| Anything on a **TFF** skid — the estate's most standardised platform, 20 benches | `tff-platform` |
| Anything on a **mix** bench — LNP, and the LAI/MSP instances built on the same convention | `mix-system` |
| The **in-line particle-sizing PAT rig** for twin-screw wet granulation, and the Bayesian optimizer it is meant to feed | `pat-psd` |
| Author or edit views, scripts, named queries, tags, UDTs, SFCs | `ignition-resources` |
| Drive a live gateway: API, MCP tools, scan, export/import | `ignition-gateway` |
| Node-RED flows on groov RIO devices | `nodered-rio` |
| Topics, payloads, commands, the MQTT↔Ignition bridge | `mqtt-integration` |
| Named queries, historian schema, process history | `sql-historian` |
| Something is broken and you do not know which layer | `triage` |
| Stand up a new equipment instance end to end | `equipment-onboarding` |
| Check known traps before building; record what you learn | `pitfalls` |

## Non-negotiables

1. **Default to read-only.** The Designer owns project files. Read, explain, document — modify only
   when asked.
2. **Never write to prod.** It has no API; the bundled tools refuse writes to `wz02163d`. Prod
   changes go through the Designer, by a human.
3. **Check `pitfalls` before authoring** a view, tag, alarm or script. The estate has already paid
   for these lessons.
4. **Jython 2.7, not Python 3** — every `.py` under a project runs in the gateway JVM.
5. **`data.bin` is two different formats.** Sniff the first two bytes: `0x1f8b` = gzipped Java
   serialization, never hand-edit; `{` = plain JSON, safe to edit.
