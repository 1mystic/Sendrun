"""scripts/audit_secrets.py's pattern matching — verified against known
real-shaped and known-safe strings, not just "it runs."""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

from audit_secrets import SECRET_PATTERNS  # noqa: E402


def _matches_any(text: str) -> str | None:
    for name, pattern in SECRET_PATTERNS:
        if pattern.search(text):
            return name
    return None


class TestSecretPatterns:
    def test_detects_an_anthropic_style_key(self):
        fake = "sk-ant-api03-abcdefghijklmnopqrstuvwxyz1234567890ABCD"
        assert _matches_any(fake) == "Anthropic API key"

    def test_detects_an_openrouter_style_key(self):
        fake = "sk-or-v1-abcdefghijklmnopqrstuvwxyz1234567890"
        assert _matches_any(fake) == "OpenRouter API key"

    def test_detects_a_resend_style_key(self):
        fake = "re_abcdefghijklmnopqrstuvwxyz123456"
        assert _matches_any(fake) == "Resend API key"

    def test_detects_an_aws_access_key(self):
        fake = "AKIAIOSFODNN7EXAMPLE"
        assert _matches_any(fake) == "AWS access key"

    def test_detects_a_private_key_block(self):
        fake = "-----BEGIN RSA PRIVATE KEY-----"
        assert _matches_any(fake) == "Generic private key block"

    def test_detects_a_postgres_url_with_credentials(self):
        fake = "postgresql://myuser:supersecret123@db.example.com:5432/mydb"
        assert _matches_any(fake) == "Postgres/DB URL with embedded credentials"

    def test_does_not_flag_a_postgres_url_without_credentials(self):
        """The connection-string pattern requires an embedded user:pass —
        a URL using IAM auth or a trust connection must not false-positive."""
        safe = "postgresql://db.example.com:5432/mydb"
        assert _matches_any(safe) is None

    def test_does_not_flag_an_ordinary_uuid(self):
        safe = "a1b2c3d4-e5f6-7890-abcd-ef1234567890"
        assert _matches_any(safe) is None

    def test_does_not_flag_the_env_example_placeholder_style(self):
        safe = "ANTHROPIC_API_KEY="
        assert _matches_any(safe) is None

    def test_does_not_flag_a_sha256_hash(self):
        """The kind of string legitimately all over this codebase
        (idempotency keys, event ids) — must not be caught as a false
        positive, or the audit would be too noisy to trust."""
        safe = "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855"
        assert _matches_any(safe) is None


class TestAuditRunsCleanAgainstThisRepo:
    def test_the_real_repo_has_no_findings(self):
        """The actual, load-bearing assertion: run the real audit against
        the real tracked files and confirm it reports clean. This is what
        would fail in CI if a secret were ever accidentally committed."""
        import subprocess

        repo_root = Path(__file__).resolve().parent.parent
        result = subprocess.run(
            [sys.executable, "scripts/audit_secrets.py"],
            cwd=repo_root, capture_output=True, text=True,
        )
        assert result.returncode == 0, result.stdout
        assert "no issues found" in result.stdout
