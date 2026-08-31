#!/usr/bin/env python3
"""PreToolUse guard for the automation-engineering plugin.

Two things in this estate are easy to damage by accident and hard to undo:

  1. The gateway backup trees under doc/Ignition-W*-backup-*/ are the only record of what the
     production gateway contains. Production runs Ignition 8.1.28 and exposes no API, so if you
     edit the backup you have destroyed the evidence and gained nothing.
  2. Production itself. It has no HTTP API, so a write aimed at it cannot succeed - but a command
     that names the prod host is a sign the operator believes it can, which is worth stopping to
     confirm.

This hook does not block. It asks, so a human decides. Reads are never questioned.
"""

import json
import os
import re
import sys

PROD_HOSTS = [h.strip().lower() for h in
              os.environ.get("IGN_PROD_HOSTS", "wz02163d").split(",") if h.strip()]
BACKUP_DIR_RE = re.compile(r"Ignition-W[A-Z0-9]+_Ignition-backup-\d{8}-\d{4}", re.I)
MUTATING_CURL = re.compile(
    r"""\b(?:curl|wget|http)\b[^\n|;&]*?
        (?:-X\s*(?:POST|PUT|DELETE|PATCH)|--data|--upload-file|-d\s)""",
    re.I | re.X)
IGN_WRITE = re.compile(r"\bign\b[^\n|;&]*--confirm", re.I)


def ask(reason):
    json.dump({"hookSpecificOutput": {
        "hookEventName": "PreToolUse",
        "permissionDecision": "ask",
        "permissionDecisionReason": reason,
    }}, sys.stdout)
    sys.exit(0)


def main():
    try:
        ev = json.load(sys.stdin)
    except (ValueError, OSError):
        sys.exit(0)

    tool = ev.get("tool_name") or ""
    inp = ev.get("tool_input") or {}

    if tool in ("Write", "Edit", "NotebookEdit"):
        path = str(inp.get("file_path") or "")
        if BACKUP_DIR_RE.search(path):
            ask("This path is inside a gateway backup tree, which is the only record of what that "
                "gateway contains - production has no API to re-read it from. Copy it somewhere "
                "else and edit the copy instead of modifying the backup.")
        sys.exit(0)

    if tool == "Bash":
        cmd = str(inp.get("command") or "")
        low = cmd.lower()
        host = next((h for h in PROD_HOSTS if h in low), None)
        if host and (MUTATING_CURL.search(cmd) or IGN_WRITE.search(cmd)):
            ask("This command looks like a write and it names the production gateway %r. Production "
                "runs Ignition 8.1.28 and exposes no HTTP API, so this cannot succeed - and if it "
                "could, production changes belong in the Designer. Confirm this is really what you "
                "want." % host)
        if BACKUP_DIR_RE.search(cmd) and re.search(
                r"\b(rm|mv|truncate|dd|tee|sed\s+-i|>\s*/)\b", cmd):
            ask("This command modifies or removes files inside a gateway backup tree. Those trees "
                "are the only record of the production gateway's contents. Confirm before proceeding.")

    sys.exit(0)


if __name__ == "__main__":
    main()
