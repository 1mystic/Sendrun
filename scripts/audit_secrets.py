"""A secrets audit: fails loudly if anything that looks like a real secret is
about to be committed. Run manually before a commit, or wire into a
pre-commit hook / CI step.

Two checks, both real:

1. **Tracked files matching a secret-shaped pattern** (API keys, private
   keys, connection strings with embedded credentials) — scans file
   CONTENTS, not just filenames, since a secret can be pasted into any file.
2. **`.env` (or any real env file) is not tracked by git** — the template
   `.env.example` is fine; a literal `.env` being tracked means a real
   secret probably already leaked into history.

This is deliberately a pattern-matching heuristic, not a cryptographic
secret scanner (tools like gitleaks/truffleHog do that properly and should
be the real CI gate for a production system) — but it catches the common,
careless case: an API key pasted into a script during debugging and never
removed.

Run: uv run python scripts/audit_secrets.py
"""

from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent

# Each pattern names what it catches. Deliberately narrow and specific
# rather than a generic "20+ char random string" heuristic, which would
# false-positive on every UUID and hash already legitimately in the codebase.
SECRET_PATTERNS: list[tuple[str, re.Pattern]] = [
    ("Anthropic API key", re.compile(r"sk-ant-[a-zA-Z0-9\-_]{20,}")),
    ("OpenAI API key", re.compile(r"sk-[a-zA-Z0-9]{20,}(?!-ant)")),
    ("OpenRouter API key", re.compile(r"sk-or-[a-zA-Z0-9\-_]{20,}")),
    ("Resend API key", re.compile(r"re_[a-zA-Z0-9]{20,}")),
    ("AWS access key", re.compile(r"AKIA[0-9A-Z]{16}")),
    ("Generic private key block", re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----")),
    (
        "Postgres/DB URL with embedded credentials",
        re.compile(r"postgres(?:ql)?://[^:\s]+:[^@\s]+@"),
    ),
]

# Files where a match is expected and NOT a leak — this file's own patterns,
# and .env.example's deliberately-empty placeholder lines.
ALLOWLIST_FILES = {"scripts/audit_secrets.py", ".env.example"}


def scan_tracked_files() -> list[tuple[str, str, int]]:
    """Returns (file, pattern_name, line_number) for every match found in
    git-tracked files. Scans git's OWN view of tracked content, not the
    working directory — a secret already staged is exactly what this
    should catch before commit."""
    result = subprocess.run(
        ["git", "ls-files"], cwd=REPO_ROOT, capture_output=True, text=True, check=True,
    )
    tracked_files = result.stdout.splitlines()

    findings: list[tuple[str, str, int]] = []
    for rel_path in tracked_files:
        if rel_path in ALLOWLIST_FILES:
            continue
        path = REPO_ROOT / rel_path
        if not path.is_file():
            continue
        try:
            text = path.read_text(errors="ignore")
        except (UnicodeDecodeError, OSError):
            continue

        for line_no, line in enumerate(text.splitlines(), start=1):
            for name, pattern in SECRET_PATTERNS:
                if pattern.search(line):
                    findings.append((rel_path, name, line_no))
    return findings


def check_env_file_not_tracked() -> list[str]:
    """`.env` itself must never be tracked — only `.env.example`. If it is,
    a real secret has likely already been committed, which needs history
    rewriting to fully fix (out of scope for this script — it just flags it)."""
    result = subprocess.run(
        ["git", "ls-files"], cwd=REPO_ROOT, capture_output=True, text=True, check=True,
    )
    tracked = set(result.stdout.splitlines())
    problems = []
    for candidate in (".env", ".env.local", ".env.production"):
        if candidate in tracked:
            problems.append(candidate)
    return problems


def main() -> None:
    findings = scan_tracked_files()
    env_problems = check_env_file_not_tracked()

    if not findings and not env_problems:
        print("Secrets audit: no issues found.")
        return

    if findings:
        print(f"Secrets audit: {len(findings)} potential secret(s) found in tracked files:\n")
        for rel_path, name, line_no in findings:
            print(f"  {rel_path}:{line_no}  — looks like a {name}")

    if env_problems:
        print(f"\nSecrets audit: real env file(s) are TRACKED by git: {env_problems}")
        print("  Only .env.example should be tracked. Remove these with `git rm --cached`.")

    sys.exit(1)


if __name__ == "__main__":
    main()
