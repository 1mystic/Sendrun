"""Shared FastAPI dependencies: DB session, current user, and org membership."""

from __future__ import annotations

from uuid import UUID

from fastapi import Cookie, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from packages.shared.auth import COOKIE_NAME, resolve_session
from packages.shared.authz import Membership, get_membership
from packages.shared.db import get_db
from packages.shared.models import User

__all__ = ["get_db", "get_current_user", "require_user", "require_membership"]


async def get_current_user(
    db: AsyncSession = Depends(get_db),
    session_cookie: str | None = Cookie(default=None, alias=COOKIE_NAME),
) -> User | None:
    return await resolve_session(db, session_cookie)


async def require_user(user: User | None = Depends(get_current_user)) -> User:
    if user is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "not authenticated")
    return user


async def require_membership(
    org_id: UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_user),
) -> Membership:
    membership = await get_membership(db, user, org_id)
    if membership is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "organization not found")
    return membership
