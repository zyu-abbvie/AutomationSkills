# Automation engineering — Claude Code marketplace

This repository is a Claude Code **plugin marketplace**. It hosts one plugin,
[`automation-engineering`](plugins/automation-engineering/), which is the shared reference and working
toolkit for this estate's automation projects.

```
/plugin marketplace add /home/admin/src/Automation_Skills2
/plugin install automation-engineering@automation-engineering-marketplace
```

Then, in a session:

```bash
${CLAUDE_PLUGIN_ROOT}/bin/ign capabilities
```

See [plugins/automation-engineering/README.md](plugins/automation-engineering/README.md) for
configuration, the skill list and the tools.

## Layout

| Path | What it is |
|---|---|
| `.claude-plugin/marketplace.json` | The marketplace manifest. |
| `plugins/automation-engineering/` | The plugin. Skills, references, tools, an agent, a safety hook. |
| `doc/` | Source material: gateway backups, groov RIO device backups, Ignition manuals, `credential.yaml`. **Not committed** — see `.gitignore`. |
| `PROPOSED_PITFALLS.md` | Five findings from building the plugin, formatted for `addPitfall`, awaiting submission by someone with an authenticated MCP session. |

## What the plugin knows

Everything in it was verified against the live gateways, the live MQTT brokers and the on-disk backups
on 2026-08-28. The facts that shape it:

- The estate has **two Ignition gateways on different major versions** — dev `wa03593d` is **8.3.7**
  with an HTTP API and an MCP server; prod `wz02163d` is **8.1.28** with **no API at all**. They also
  store gateway event scripts in incompatible formats. Treating them as one system is the most
  expensive mistake available here.
- Dev API **reads are anonymous**; writes require a token. Prod is Designer-only.
- **Node-RED runs on Opto 22 groov RIO edge devices**, and every field device publishes to the
  **production** broker. The dev gateway's MQTT tag tree is therefore stale. `doc/backup_nodered/`
  holds 37 directories but only **17 contain a flow backup**; the rest are empty placeholders or
  unrelated tooling.
- The estate is **not** a Sparkplug estate: telemetry flows on a plain
  `SITE/BUILDING/ROOM-BENCH/EQUIP/CATEGORY/POINT` namespace, retained, QoS 0, with every
  MQTT-Engine tag typed `String`.
- Commands are **not** tag writes — they are `system.cirruslink.engine.publish` calls, and a momentary
  command must clear its own retained message or it re-fires when the device reconnects.

## For maintainers

The plugin is deliberately structured so it can be corrected. Each skill states the evidence behind
its load-bearing claims (real counts, real file paths, real commands), so a future reader can re-run
the check rather than trusting the text. Two claims were already corrected during the build when
live re-verification contradicted them — that is the intended workflow.

`bin/ign-validate` is calibrated: **zero findings across all 114 production projects**, while catching
every known-broken project on dev. If a change to it starts reporting findings on production
projects, the change is wrong, not the estate.
