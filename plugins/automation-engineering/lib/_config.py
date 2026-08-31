"""Shared configuration resolution for the automation-engineering tools.

Settings come from four places, highest precedence first:

  1. a command-line flag        --url / --token / --host ...
  2. an environment variable    IGN_URL, IGN_API_TOKEN, MQTT_HOST, ...
  3. a local config file        automation.local.yaml  (NOT committed)
  4. a built-in default         the dev gateway and dev broker

The config file exists so a team does not have to export half a dozen variables in every shell.
It is deliberately never committed - see automation.local.example.yaml for the template.

Search order for the file (first that exists wins):
    $AUTOMATION_CONFIG
    ./automation.local.yaml
    <plugin>/../../automation.local.yaml        (repo root, next to .claude-plugin/)
    ~/.config/automation-engineering/config.yaml
    <repo>/doc/credential.yaml                 (the estate's existing file, read as a fallback)

The parser handles the small YAML subset these files use - one level of nesting, scalar values,
comments, and ${VAR:-default} interpolation - so the tools keep their zero-dependency property.
If PyYAML happens to be installed it is used instead, which is strictly more permissive.
"""

import os
import re

DEFAULTS = {
    # Ignition gateway
    "gateway_url": "http://wa03593d:8088",
    "prod_hosts": "wz02163d",
    "api_token": "",
    "mcp_server": "MCP_Tools",
    # MQTT broker
    "mqtt_host": "10.72.167.253",
    "mqtt_port": "1883",
    "mqtt_username": "",
    "mqtt_password": "",
    "mqtt_keepalive": "60",
    "mqtt_tls": "false",
    # SQL Server. No driver is installed on most hosts here, so these are informational for
    # skills and for anyone who does have a driver - the tools route SQL through Ignition.
    "sql_server": "",
    "sql_database": "Ignition",
    "sql_uid": "",
    "sql_password": "",
    "sql_driver": "{ODBC Driver 17 for SQL Server}",
    # Where the on-disk reference material lives. Teammates who clone the repo without doc/
    # can point these at a share instead of symlinking.
    "backups_dir": "",
    "nodered_backups_dir": "",
}

# Environment variable per setting. These keep working; the file is an alternative, not a replacement.
ENV = {
    "gateway_url": "IGN_URL",
    "api_token": "IGN_API_TOKEN",
    "prod_hosts": "IGN_PROD_HOSTS",
    "mcp_server": "IGN_MCP_SERVER",
    "mqtt_host": "MQTT_HOST",
    "mqtt_port": "MQTT_PORT",
    "mqtt_username": "MQTT_USERNAME",
    "mqtt_password": "MQTT_PASSWORD",
    "sql_server": "SQL_SERVER",
    "sql_database": "SQL_DATABASE",
    "sql_uid": "SQL_UID",
    "sql_password": "SQL_PASSWORD",
    "backups_dir": "AUTOMATION_BACKUPS_DIR",
    "nodered_backups_dir": "AUTOMATION_NODERED_DIR",
}

SECRET_KEYS = ("api_token", "mqtt_password", "password", "pwd", "psw", "secret", "token")

_INTERP = re.compile(r"\$\{([A-Za-z_][A-Za-z0-9_]*)(?::-([^}]*))?\}")


def _interp(value):
    """Resolve ${VAR} and ${VAR:-default} against the real environment."""
    def sub(m):
        return os.environ.get(m.group(1)) or (m.group(2) or "")
    return _INTERP.sub(sub, value)


def _parse_scalar(raw):
    raw = raw.strip()
    if len(raw) >= 2 and raw[0] == raw[-1] and raw[0] in "\"'":
        raw = raw[1:-1]
    return _interp(raw)


def _parse_yaml_subset(text):
    """One level of nesting, scalars only. Enough for these config files."""
    out, section = {}, None
    for line in text.splitlines():
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        line = line.split(" #", 1)[0].rstrip() if " #" in line else line.rstrip()
        indented = line[:1] in (" ", "\t")
        if ":" not in line:
            continue
        key, _, val = line.strip().partition(":")
        key = key.strip()
        if not val.strip():
            # a section header
            section = key
            out.setdefault(section, {})
            continue
        if indented and section:
            out[section][key] = _parse_scalar(val)
        else:
            out[key] = _parse_scalar(val)
            section = None
    return out


def _load_file(path):
    try:
        text = open(path, encoding="utf-8", errors="replace").read()
    except OSError:
        return {}
    try:
        import yaml  # optional; the subset parser below is the guaranteed path
        doc = yaml.safe_load(text)
        if isinstance(doc, dict):
            return {k: ({kk: _interp(str(vv)) for kk, vv in v.items()}
                        if isinstance(v, dict) else _interp(str(v)))
                    for k, v in doc.items() if v is not None}
    except Exception:
        pass
    return _parse_yaml_subset(text)


def candidate_paths(plugin_root=None):
    root = plugin_root or os.path.dirname(os.path.dirname(os.path.realpath(__file__)))
    repo = os.path.dirname(os.path.dirname(root))
    paths = []
    if os.environ.get("AUTOMATION_CONFIG"):
        paths.append(os.environ["AUTOMATION_CONFIG"])
    paths += [
        os.path.join(os.getcwd(), "automation.local.yaml"),
        os.path.join(repo, "automation.local.yaml"),
        os.path.expanduser("~/.config/automation-engineering/config.yaml"),
        os.path.join(repo, "doc", "credential.yaml"),
    ]
    return paths


def _from_credential_yaml(doc, env):
    """Map the estate's existing credential.yaml shape onto our setting names.

    That file is organised as `mqtt dev:` / `mqtt prod:` / `sql dev:` sections, so a team that
    already maintains it does not have to duplicate anything.
    """
    out = {}
    m = doc.get("mqtt %s" % env)
    if isinstance(m, dict):
        for src, dst in (("host", "mqtt_host"), ("port", "mqtt_port"),
                         ("username", "mqtt_username"), ("password", "mqtt_password"),
                         ("keepalive", "mqtt_keepalive"), ("tls", "mqtt_tls")):
            if m.get(src) not in (None, ""):
                out[dst] = str(m[src])
    s = doc.get("sql %s" % env)
    if isinstance(s, dict):
        for src, dst in (("server", "sql_server"), ("database", "sql_database"),
                         ("uid", "sql_uid"), ("pwd", "sql_password"), ("driver", "sql_driver")):
            if s.get(src) not in (None, ""):
                out[dst] = str(s[src])
    # `Ignition dev:` / `Ignition Prod:` hold a bare `host:port` line, which the parser sees as a
    # nested key. Recover it rather than making the reader restructure their file.
    for key in ("Ignition %s" % env, "Ignition %s" % env.capitalize()):
        g = doc.get(key)
        if isinstance(g, dict) and g:
            host = next(iter(g))
            port = g[host] or "8088"
            out["gateway_url"] = "http://%s:%s" % (host, port)
            break
    return out


def load(env=None, config_path=None, overrides=None):
    """Resolve every setting. Returns (settings dict, provenance dict, config file path or None)."""
    env = (env or os.environ.get("AUTOMATION_ENV") or "dev").strip().lower()
    settings = dict(DEFAULTS)
    why = {k: "default" for k in settings}

    path = None
    for p in ([config_path] if config_path else candidate_paths()):
        if p and os.path.isfile(p):
            path = p
            break

    if path:
        doc = _load_file(path)
        # An explicit section for this environment wins over top-level keys.
        merged = {k: v for k, v in doc.items() if not isinstance(v, dict)}
        if isinstance(doc.get(env), dict):
            merged.update(doc[env])
        merged.update(_from_credential_yaml(doc, env))
        for k, v in merged.items():
            key = k.strip().replace("-", "_")
            if key in settings and str(v) != "":
                settings[key] = str(v)
                why[key] = os.path.basename(path)

    for key, var in ENV.items():
        if os.environ.get(var):
            settings[key] = os.environ[var]
            why[key] = "$" + var

    for key, val in (overrides or {}).items():
        if val:
            settings[key] = str(val)
            why[key] = "flag"

    # Derived, so callers never have to build it and get the path wrong. A production gateway in
    # this estate runs 8.1 and has neither the REST API nor an MCP server, so advertising an
    # endpoint for it would be a lie.
    host = settings["gateway_url"].split("//")[-1].split(":")[0].strip().lower()
    prod = {h.strip().lower() for h in settings["prod_hosts"].split(",") if h.strip()}
    if host in prod:
        settings["mcp_url"] = ""
        why["mcp_url"] = "n/a - production has no MCP server"
    else:
        settings["mcp_url"] = "%s/data/mcp/%s" % (settings["gateway_url"].rstrip("/"),
                                                 settings["mcp_server"])
        why["mcp_url"] = "derived"

    return settings, why, path


def truthy(value):
    """YAML writers emit true/false/True/False/yes/1 - accept all of them."""
    return str(value).strip().lower() in ("1", "true", "yes", "on")


def mask(key, value):
    if not value:
        return ""
    if any(s in key.lower() for s in SECRET_KEYS):
        return "*" * 8 + (" (%d chars)" % len(value))
    return value


GROUPS = (
    ("Ignition gateway", ("gateway_url", "api_token", "prod_hosts", "mcp_server", "mcp_url")),
    ("MQTT broker", ("mqtt_host", "mqtt_port", "mqtt_username", "mqtt_password",
                     "mqtt_keepalive", "mqtt_tls")),
    ("SQL Server", ("sql_server", "sql_database", "sql_uid", "sql_password", "sql_driver")),
    ("Reference material on disk", ("backups_dir", "nodered_backups_dir")),
)


def describe(env=None, config_path=None, overrides=None):
    """Human-readable resolved configuration, with secrets masked."""
    settings, why, path = load(env, config_path, overrides)
    env_name = env or os.environ.get("AUTOMATION_ENV") or "dev"
    lines = ["config file : %s" % (path or "none found - using defaults and environment"),
             "environment : %s" % env_name]
    for title, keys in GROUPS:
        lines += ["", "  %s" % title, "  " + "-" * len(title)]
        for k in keys:
            if k not in settings:
                continue
            lines.append("    %-20s %-38s [%s]"
                         % (k, mask(k, settings[k]) or "(unset)", why.get(k, "default")))
    extra = sorted(set(settings) - {k for _, ks in GROUPS for k in ks})
    if extra:
        lines += ["", "  Other", "  -----"]
        for k in extra:
            lines.append("    %-20s %-38s [%s]"
                         % (k, mask(k, settings[k]) or "(unset)", why.get(k, "default")))
    if not path:
        lines += ["", "No config file found. Generate one from what you already have:",
                  "    <plugin>/bin/init-config"]
    return "\n".join(lines)
