# automation-engineering

A Claude Code plugin that is the working toolkit and local reference for this estate's automation
projects: **Ignition** and **Node-RED** as co-equal pillars, with **MQTT** and **SQL** as the
connective tissue between them.

Everything in here was verified against the live gateways, the live brokers and the on-disk gateway
backups on 2026-08-28 — not assembled from general Ignition documentation. Where a fact is
environment-specific, the skill says which environment.

## Install

```
/plugin marketplace add zyu-abbvie/AutomationSkills
/plugin install automation-engineering@automation-engineering-marketplace
```

To have it register automatically for everyone who clones a project, put this in that project's
`.claude/settings.json`:

```json
{
  "extraKnownMarketplaces": {
    "automation-engineering-marketplace": {
      "source": { "source": "github", "repo": "zyu-abbvie/AutomationSkills" }
    }
  },
  "enabledPlugins": {
    "automation-engineering@automation-engineering-marketplace": true
  }
}
```

That also enables the bundled `PreToolUse` hook and the Ignition MCP server for anyone who trusts
the project, so agree it with the team before committing it.

## Configure

Nothing is required to read the dev gateway — its API is anonymous. Configuration matters for API
writes, MQTT, and the MCP server.

**Generate a local config file.** The generator seeds every field it can from
`doc/credential.yaml` and your environment, so you are not retyping connection details:

```bash
${CLAUDE_PLUGIN_ROOT}/bin/init-config         # writes automation.local.yaml, mode 600
${CLAUDE_PLUGIN_ROOT}/bin/ign config          # shows what resolved, and from where; secrets masked
```

`init-config --stdout` previews it with secrets masked; `--force` overwrites. Secrets are written to
the file — that is what it is for — but never printed to the terminal.

The file is gitignored and holds a `dev:` and a `prod:` section covering the gateway, its API token
and MCP server, the broker, SQL Server, and where the on-disk backups live. Pick a section per
command with `--env dev` / `--env prod`, or export `AUTOMATION_ENV`. Default is `dev`.

If you would rather not have a file at all, `doc/credential.yaml` is read directly — its
`mqtt dev:` / `sql prod:` / `Ignition dev:` sections are mapped automatically, including the bare
`host:port` lines. `ign config` tells you which file was picked up.

Resolution order, highest precedence first:

| | Example |
|---|---|
| 1. command-line flag | `ign capabilities --url http://wz02163d:8088` |
| 2. environment variable | `IGN_URL`, `IGN_API_TOKEN`, `IGN_PROD_HOSTS`, `MQTT_HOST`, `MQTT_PORT`, `MQTT_USERNAME`, `MQTT_PASSWORD` |
| 3. `automation.local.yaml`, else `doc/credential.yaml` | see the template |
| 4. built-in default | dev gateway, dev broker, `prod_hosts: wz02163d` |

So you can keep everything in the file and still override one value for a single command. Flags work
either before or after the subcommand. Values in the file may also indirect through the environment —
`api_token: ${IGNITION_TOKEN}` — which is what to use when a vault or CI injects the secret.

The plugin additionally declares these as `userConfig`, so `/plugin` can prompt for them and keep the
sensitive ones in Claude Code's own settings rather than in a file. Either mechanism works; the file
is usually easier for a team.

## Start here

```bash
${CLAUDE_PLUGIN_ROOT}/bin/ign capabilities
```

That one command tells you which gateway you are pointed at, its Ignition version, whether the HTTP
API exists, whether reads are anonymous, whether writes are authenticated, and which MCP servers are
mounted. The estate's two gateways run **different major versions** and have **different
capabilities**, and assuming otherwise is the most expensive mistake available here.

Then read the `estate-map` skill.

## Skills

| Skill | Use it for |
|---|---|
| `estate-map` | Orientation. The two gateways, the architecture, the addressing scheme, where everything lives. Read first. |
| `tff-platform` | Tangential Flow Filtration: the 20-bench platform, its 41-tag process model with units and physical meaning, the six SFC unit operations, the instruments, and how to debug a run. |
| `ignition-resources` | Authoring and editing views, scripts, named queries, tags, SFCs, inheritance — on disk. |
| `ignition-gateway` | Driving a live gateway: HTTP API, MCP tools, logs, project scan, export/import. |
| `nodered-rio` | Node-RED flows on the Opto 22 groov RIO edge devices. |
| `mqtt-integration` | Topics, payloads, commands and acknowledgements, the MQTT↔Ignition bridge. |
| `sql-historian` | Named queries, historian schema, process history, timezone handling. |
| `triage` | Something is broken and you do not know which of the four layers owns it. |
| `equipment-onboarding` | Standing up a new equipment instance end to end. |
| `pitfalls` | Check known traps before authoring; record what you learn afterwards. |

## Tools

All in `bin/`. **Zero dependencies** — Python 3 standard library only, so they run without a
`pip install` on any host in the estate.

| Tool | What it does |
|---|---|
| `ign` | Ignition gateway client. `capabilities`, `info`, `projects`, `project`, `res`, `logs`, `tags`, `scan`, `export`, `api`. Refuses writes to a production host, and requires `--confirm` for any non-GET. |
| `ign-validate` | Pre-flights an on-disk Ignition project for the defects that make the Gateway *silently* drop a resource. Calibrated against the whole estate: 0 findings across all 114 production projects, and it catches every known-broken project on dev. |
| `mqtt-probe` | MQTT 3.1.1 client written on a raw socket, because `paho-mqtt` is not installed here. `check` proves reachability and authentication, `watch` gives a live topic census, `pub` sends one message. Best-effort Sparkplug metric-name decode without a protobuf library. |
| `nr-inspect` | Reads a groov RIO device backup — straight from the zip, no extraction. `summary` for the node census, `topics` for the MQTT contract with Ignition, `devices` for serial/Modbus/groov I/O wiring, `lint` for the defects this estate actually has. Never prints a secret's value, only its location and length. |
| `init-config` | Writes a clean `automation.local.yaml` covering both environments, seeded from `doc/credential.yaml` and the environment. Mode 600, refuses to clobber, never prints a secret. |
| `plugin-selfcheck` | Validates the plugin before you publish it: manifests, skill frontmatter, dead reference links, script syntax, that secret-bearing files are gitignored, and that no credential has leaked into a committed file. |

## Agent

`ignition-reviewer` — reviews an Ignition resource change for the silent-failure defects. Invoke as
`@automation-engineering:ignition-reviewer`.

## Safety

- A `PreToolUse` hook asks for confirmation before anything writes inside a gateway **backup** tree
  (those trees are the only record of what production contains) or sends a write at the production
  gateway.
- `ign` refuses non-GET requests to any host in `IGN_PROD_HOSTS`, and requires `--confirm` for writes
  anywhere.
- Production has no HTTP API at all. Production changes go through the Designer, by a human.

## A note on what is *not* in here

No credentials, and no dump of live tag or topic names. Topic and tag inventories go stale within
days and contain individuals' names; `mqtt-probe watch` and `ign tags` regenerate them on demand,
which is more useful than a snapshot. What is committed here is the *structure* and the *traps*.
