"""Password hashing and session issuance.

Sessions are server-side rows (see models.Session), referenced by an opaque,
signed cookie value — not a JWT carrying claims. That trade means every request
costs a DB lookup, but sign-out and forced revocation are then a single DELETE
instead of "wait for the token to expire," which matters for a product whose
whole pitch is trustworthy state.
"""

from __future__ import annotations

import secrets
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from uuid import UUID

from argon2 import PasswordHasher
from argon2.exceptions import VerifyMismatchError
from itsdangerous import BadSignature, URLSafeTimedSerializer
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from .config import get_settings
from .models import Session as SessionRow
from .models import User

_hasher = PasswordHasher()

COOKIE_NAME = "sendrun_session"


def hash_password(raw: str) -> str:
    return _hasher.hash(raw)


def verify_password(raw: str, hashed: str) -> bool:
    try:
        return _hasher.verify(hashed, raw)
    except VerifyMismatchError:
        return False


def _serializer() -> URLSafeTimedSerializer:
    return URLSafeTimedSerializer(get_settings().session_secret, salt="sendrun-session")


def sign_session_id(session_id: UUID) -> str:
    return _serializer().dumps(str(session_id))


def unsign_session_id(token: str) -> UUID | None:
    """Returns None on a bad or tampered signature rather than raising — callers
    treat an invalid cookie exactly like a missing one."""
    try:
        raw = _serializer().loads(token, max_age=get_settings().session_ttl_hours * 3600)
        return UUID(raw)
    except (BadSignature, ValueError):
        return None


@dataclass(frozen=True, slots=True)
class AuthResult:
    user: User
    session_id: UUID
    cookie_value: str


async def create_session(
    db: AsyncSession, user: User, *, user_agent: str | None = None
) -> AuthResult:
    settings = get_settings()
    row = SessionRow(
        user_id=user.id,
        expires_at=datetime.now(UTC) + timedelta(hours=settings.session_ttl_hours),
        user_agent=user_agent,
    )
    db.add(row)
    await db.flush()
    return AuthResult(user=user, session_id=row.id, cookie_value=sign_session_id(row.id))


async def resolve_session(db: AsyncSession, cookie_value: str | None) -> User | None:
    """The auth dependency's core. Any failure mode returns None, never raises —
    an expired or forged cookie is simply "not logged in," not a 500."""
    if not cookie_value:
        return None
    session_id = unsign_session_id(cookie_value)
    if session_id is None:
        return None

    row = await db.get(SessionRow, session_id)
    if row is None or row.revoked_at is not None:
        return None
    if row.expires_at.replace(tzinfo=UTC) < datetime.now(UTC):
        return None

    return await db.get(User, row.user_id)


async def revoke_session(db: AsyncSession, cookie_value: str | None) -> None:
    if not cookie_value:
        return
    session_id = unsign_session_id(cookie_value)
    if session_id is None:
        return
    row = await db.get(SessionRow, session_id)
    if row is not None and row.revoked_at is None:
        row.revoked_at = datetime.now(UTC)


async def get_user_by_email(db: AsyncSession, email: str) -> User | None:
    result = await db.execute(select(User).where(User.email == email.lower().strip()))
    return result.scalar_one_or_none()


def generate_slug_suffix() -> str:
    """A short random suffix for de-duplicating an organization slug collision."""
    return secrets.token_hex(3)
