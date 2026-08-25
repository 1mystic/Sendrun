"""Attachment validation: size cap, extension allowlist, and the
extension/content-type mismatch check that catches a disguised file."""

from __future__ import annotations

import uuid

import pytest

from packages.shared.attachments import (
    MAX_ATTACHMENT_BYTES,
    AttachmentRejected,
    AttachmentRequest,
    FakeR2Client,
    validate_attachment,
)


def test_accepts_a_normal_pdf():
    validate_attachment(AttachmentRequest("invitation.pdf", "application/pdf", 500_000))


def test_rejects_a_file_over_the_size_cap():
    with pytest.raises(AttachmentRejected, match="exceeds"):
        validate_attachment(
            AttachmentRequest("huge.pdf", "application/pdf", MAX_ATTACHMENT_BYTES + 1)
        )


def test_rejects_an_empty_file():
    with pytest.raises(AttachmentRejected, match="empty"):
        validate_attachment(AttachmentRequest("empty.pdf", "application/pdf", 0))


def test_rejects_a_disallowed_extension():
    with pytest.raises(AttachmentRejected, match="not allowed"):
        validate_attachment(AttachmentRequest("payload.exe", "application/octet-stream", 1000))


def test_rejects_a_content_type_mismatched_with_the_extension():
    """The classic disguise: an .exe renamed to .pdf but sent with its real
    content-type still attached is exactly what this must catch."""
    with pytest.raises(AttachmentRejected, match="does not match"):
        validate_attachment(
            AttachmentRequest("totally-a.pdf", "application/x-msdownload", 1000)
        )


def test_fake_r2_client_returns_a_usable_key():
    client = FakeR2Client()
    result = client.presign_put(
        AttachmentRequest("invitation.pdf", "application/pdf", 500_000), uuid.uuid4()
    )
    assert result.storage_key.endswith("invitation.pdf")
    assert result.storage_key in client.presigned


def test_storage_key_is_namespaced_per_org():
    client = FakeR2Client()
    org_a, org_b = uuid.uuid4(), uuid.uuid4()
    req = AttachmentRequest("file.pdf", "application/pdf", 1000)
    key_a = client.presign_put(req, org_a).storage_key
    key_b = client.presign_put(req, org_b).storage_key
    assert str(org_a) in key_a
    assert str(org_b) in key_b
    assert key_a != key_b
