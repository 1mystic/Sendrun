#!/usr/bin/env python3
"""Hard-block `git push` and remote-mutating git commands.

Invoked from .claude/settings.json as "$CLAUDE_PROJECT_DIR/.claude/hooks/block_push.py".
The absolute path matters: a relative path resolves against the shell's cwd, so the hook
silently fails (and stops guarding) as soon as a command runs from a subdirectory.

Project rule: commits are allowed, pushing is the user's action alone.
Exit code 2 tells Claude Code to deny the tool call and show stderr to the model.
"""
import json
import re
import sys

# Matches `git push`, `git remote add`, and push-by-other-means, allowing for
# leading env vars, flags between `git` and the subcommand, and chained commands.
PATTERNS = [
    r"\bgit\b[^;|&]*\bpush\b",
    r"\bgit\b[^;|&]*\bremote\b[^;|&]*\badd\b",
    r"\bgit\b[^;|&]*\bremote\b[^;|&]*\bset-url\b",
    r"\bgh\b\s+(repo\s+create|pr\s+create)\b",
]


def main() -> int:
    try:
        payload = json.load(sys.stdin)
    except (json.JSONDecodeError, ValueError):
        return 0

    command = payload.get("tool_input", {}).get("command", "")
    if not command:
        return 0

    for pattern in PATTERNS:
        if re.search(pattern, command, re.IGNORECASE):
            sys.stderr.write(
                "BLOCKED by project rule: this repository must never be pushed to a "
                "remote by an agent.\n"
                f"Refused command: {command}\n"
                "Local git (init/add/commit/status/log/diff/branch/checkout) is allowed. "
                "Pushing and remote creation are the user's action alone. Do not retry "
                "or attempt a workaround; tell the user to push manually if needed.\n"
            )
            return 2

    return 0


if __name__ == "__main__":
    sys.exit(main())
