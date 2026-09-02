# Automation engineering — Claude Code marketplace

This repository is a Claude Code **plugin marketplace**. It hosts one plugin,
[`automation-engineering`](plugins/automation-engineering/), the shared reference and working toolkit
for this estate's automation projects: **Ignition** and **Node-RED** as co-equal pillars, with
**MQTT** and **SQL** as the connective tissue between them.

## Install

``` config you git SSH or change to https first before execution. 
/plugin marketplace add git@github.com:zyu-abbvie/AutomationSkills.git
/plugin install automation-engineering@automation-engineering-marketplace
```

Then, in a session:

```bash
${CLAUDE_PLUGIN_ROOT}/bin/ign capabilities
```

That one command reports which gateway you are pointed at, its Ignition version, whether the HTTP API
exists, whether reads are anonymous, whether writes are authenticated, and which MCP servers are
mounted. Run it before anything else.

See [plugins/automation-engineering/README.md](plugins/automation-engineering/README.md) for
configuration, the twelve skills, and the seven bundled tools.

## Layout

| Path | What it is |
|---|---|
| `.claude-plugin/marketplace.json` | The marketplace manifest. |
| `plugins/automation-engineering/` | The plugin: 12 skills, 23 references, 7 tools, 1 review agent, 1 safety hook. |
| `automation.local.example.yaml` | Config template. Copy it, or generate a filled-in one with `bin/init-config`. |

## Not in this repository

Deliberately excluded, and listed in `.gitignore`:

- **`doc/`** — the source material this plugin was built from: 3.6 GB of Ignition gateway backups,
  groov RIO device backups, and vendor manuals, plus `credential.yaml`. It also holds a superseded
  `ignition-tooling` plugin with its own `marketplace.json`, which would confuse plugin discovery.
- **`automation.local.yaml`** — your resolved configuration, including secrets.
- **Working notes** from the build, including a security-findings write-up that belongs with the
  estate owners rather than in a repository.

The skills reference the backup trees as `$DEV`, `$PROD` and `$NODERED`. Point those at wherever you
keep them, or set `backups_dir` / `nodered_backups_dir` in your config file. Live dev-gateway work
needs none of it; prod inspection and all Node-RED work do.

## What the plugin knows

Everything in it was verified against the live gateways, the live MQTT brokers and the on-disk backups
on 2026-08-28 — not assembled from general Ignition documentation. The facts that shape it:

- The estate has **two Ignition gateways on different major versions** — dev is **8.3.7** with an HTTP
  API and an MCP server; prod is **8.1.28** with **no API at all**. They also store gateway event
  scripts in incompatible formats. Treating them as one system is the most expensive mistake
  available here.
- Dev API **reads are anonymous**; writes require a token. Prod is Designer-only.
- **Node-RED runs on Opto 22 groov RIO edge devices**, and every field device publishes to the
  **production** broker — so the dev gateway's MQTT tag tree is stale and must not be used to decide
  whether equipment is alive.
- The estate is **not** a Sparkplug estate: telemetry flows on a plain
  `SITE/BUILDING/ROOM-BENCH/EQUIP/CATEGORY/POINT` namespace, retained, QoS 0, with every
  MQTT-Engine tag typed `String`.
- Commands are **not** tag writes — they are `system.cirruslink.engine.publish` calls, and a momentary
  command must clear its own retained message or it re-fires when the device reconnects.
- The estate's **PAT instruments are not wired to its optimizers**. The twin-screw granulation line has
  a real extruder, a real Ax/BoTorch Bayesian optimizer, and a real in-line particle-sizing rig — but the
  PSD value the optimizer trains on is **typed into a text box by hand**, and the two `pat/psd` tags
  provisioned to receive the rig's telemetry are referenced by nothing. `pat-psd` documents both ends and
  what joining them requires.

## For maintainers

The plugin is structured so it can be corrected. Each skill states the evidence behind its
load-bearing claims — real counts, real paths, real commands — so a future reader can re-run the
check rather than trusting the text. Two claims were corrected during the build when live
re-verification contradicted them; that is the intended workflow, not an exception.

Before publishing a change:

```bash
plugins/automation-engineering/bin/plugin-selfcheck
```

It wraps the official `claude plugin validate`, checks skill frontmatter and reference links, and
verifies no credential has leaked into a committed file. `bin/ign-validate` is calibrated: **zero
findings across all 114 production projects**, while catching every known-broken project on dev. If a
change to it starts reporting findings on production projects, the change is wrong, not the estate.
