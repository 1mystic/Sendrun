"""Attachment storage: presigned PUT to R2 (S3-compatible), never through our
own server. The API hands the browser a short-lived signed URL; the browser
uploads directly to R2; we store only the resulting key.

Deliberately NOT built: virus scanning, resumable multipart upload, arbitrary
file sizes. See PLAN.md's "explicitly not building" list — a 10MB cap and an
extension allowlist is the right amount of scope for a student project; a
scanning pipeline is a service in itself.
"""

from __future__ import annotations

import mimetypes
import uuid
from dataclasses import dataclass

MAX_ATTACHMENT_BYTES = 10 * 1024 * 1024  # 10MB

ALLOWED_EXTENSIONS = {
    ".pdf", ".doc", ".docx", ".xls", ".xlsx", ".ppt", ".pptx",
    ".png", ".jpg", ".jpeg", ".gif", ".webp",
    ".csv", ".txt", ".zip",
}


class AttachmentRejected(Exception):
    pass


@dataclass(frozen=True, slots=True)
class AttachmentRequest:
    filename: str
    content_type: str
    size_bytes: int


@dataclass(frozen=True, slots=True)
class PresignedUpload:
    storage_key: str
    upload_url: str
    upload_fields: dict[str, str]


def validate_attachment(req: AttachmentRequest) -> None:
    if req.size_bytes <= 0:
        raise AttachmentRejected("empty file")
    if req.size_bytes > MAX_ATTACHMENT_BYTES:
        raise AttachmentRejected(
            f"{req.filename}: {req.size_bytes:,} bytes exceeds the 10MB attachment limit"
        )

    ext = "." + req.filename.rsplit(".", 1)[-1].lower() if "." in req.filename else ""
    if ext not in ALLOWED_EXTENSIONS:
        raise AttachmentRejected(f"{req.filename}: file type {ext or '(none)'} is not allowed")

    guessed, _ = mimetypes.guess_type(req.filename)
    if guessed and guessed != req.content_type:
        # A mismatched extension/content-type pair is exactly how a disguised
        # executable gets through an extension allowlist — reject rather than
        # silently trust whichever of the two the client sent.
        raise AttachmentRejected(
            f"{req.filename}: declared type {req.content_type!r} does not match "
            f"the file extension (expected {guessed!r})"
        )


def storage_key_for(org_id: uuid.UUID, filename: str) -> str:
    """Namespaced by org so a listing or a leaked key from one tenant can never
    resolve into another tenant's object space."""
    safe_name = filename.replace("/", "_").replace("\\", "_")
    return f"orgs/{org_id}/attachments/{uuid.uuid4().hex}/{safe_name}"


class R2Client:
    """Presigning is isolated behind this seam so it can be swapped for a real
    boto3 R2 client with zero change to callers, matching the fake-first
    pattern used for the email provider."""

    def __init__(self, *, bucket: str, account_id: str, access_key: str, secret_key: str) -> None:
        self.bucket = bucket
        self._account_id = account_id
        self._access_key = access_key
        self._secret_key = secret_key

    def presign_put(self, req: AttachmentRequest, org_id: uuid.UUID) -> PresignedUpload:
        validate_attachment(req)
        # Real presigning (boto3 generate_presigned_post against the R2
        # endpoint, using storage_key_for(org_id, req.filename) as the key)
        # lands with the deploy step in Phase 8 once an R2 bucket exists to
        # sign against. Until then FakeR2Client below stands in.
        raise NotImplementedError("wire real R2 credentials before using R2Client")


class FakeR2Client:
    """Dev/test stand-in. 'Uploads' are simulated — callers get a key back and
    can round-trip it through the rest of the system without a network call."""

    def __init__(self) -> None:
        self.presigned: dict[str, AttachmentRequest] = {}

    def presign_put(self, req: AttachmentRequest, org_id: uuid.UUID) -> PresignedUpload:
        validate_attachment(req)
        key = storage_key_for(org_id, req.filename)
        self.presigned[key] = req
        return PresignedUpload(
            storage_key=key,
            upload_url=f"https://fake-r2.local/{key}",
            upload_fields={},
        )
