"""Role-based access control and tenant isolation.

Two separate concerns, both enforced here so they cannot drift apart across
routers:

1. **Role hierarchy** — Owner > Admin > Editor > Viewer. A capability check is a
   single function call (`require_role`), not a scattered `if role == "admin" or
   role == "owner"` repeated per-endpoint.

2. **Tenant isolation** — every scoped query goes through `scoped()`, which
   forces a `WHERE org_id = :org_id` onto the statement. A handler that forgets
   to scope a query fails to compile (missing argument) rather than silently
   returning another organization's rows.
"""

from __future__ import annotations

from enum import IntEnum
from uuid import UUID

from fastapi import HTTPException, status
from sqlalchemy import Select, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import DeclarativeBase

from .models import Organization, OrganizationMember, User


class Role(IntEnum):
    """Ordered so `Role.EDITOR >= Role.VIEWER` reads naturally as a permission
    check, and a new role only needs one line to slot into the hierarchy."""

    VIEWER = 0
    EDITOR = 1
    ADMIN = 2
    OWNER = 3

    @classmethod
    def parse(cls, value: str) -> Role:
        return cls[value.upper()]


# Capability matrix, spelled out rather than derived, so "can X" is grep-able and
# a reviewer can see the whole policy in one place instead of reconstructing it
# from role math scattered across routers.
CAPABILITIES: dict[str, Role] = {
    "view_campaigns": Role.VIEWER,
    "view_contacts": Role.VIEWER,
    "view_analytics": Role.VIEWER,
    "create_campaign": Role.EDITOR,
    "launch_campaign": Role.EDITOR,
    "edit_template": Role.EDITOR,
    "edit_contacts": Role.EDITOR,
    "manage_members": Role.ADMIN,
    "manage_settings": Role.ADMIN,
    "manage_billing": Role.OWNER,
    "delete_organization": Role.OWNER,
}


class Membership:
    __slots__ = ("org_id", "user_id", "role")

    def __init__(self, org_id: UUID, user_id: UUID, role: Role) -> None:
        self.org_id = org_id
        self.user_id = user_id
        self.role = role

    def can(self, capability: str) -> bool:
        required = CAPABILITIES.get(capability)
        if required is None:
            raise KeyError(f"unknown capability: {capability!r}")
        return self.role >= required


async def get_membership(db: AsyncSession, user: User, org_id: UUID) -> Membership | None:
    # OrganizationMember's primary key is its own `id`, not the (org_id, user_id)
    # pair — that pair is only a unique constraint (uq_org_member) — so this has
    # to be a WHERE query, not db.get() with a composite key.
    result = await db.execute(
        select(OrganizationMember).where(
            OrganizationMember.org_id == org_id, OrganizationMember.user_id == user.id
        )
    )
    row = result.scalar_one_or_none()
    if row is None:
        return None
    return Membership(org_id=org_id, user_id=user.id, role=Role.parse(row.role))


def require_capability(membership: Membership | None, capability: str) -> Membership:
    """Raise the right HTTP error for the two distinct failure cases: not a
    member at all (404 — do not reveal the org exists) vs a member without
    enough privilege (403)."""
    if membership is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "organization not found")
    if not membership.can(capability):
        raise HTTPException(
            status.HTTP_403_FORBIDDEN,
            f"role '{membership.role.name.lower()}' cannot '{capability}'",
        )
    return membership


def scoped(stmt: Select, model: type[DeclarativeBase], org_id: UUID) -> Select:
    """Force `WHERE org_id = :org_id` onto a query. The mandatory `org_id`
    argument is the point: a call site that omits it is a TypeError at import
    time, not a cross-tenant leak discovered in production."""
    return stmt.where(model.org_id == org_id)  # type: ignore[attr-defined]


async def org_for_slug(db: AsyncSession, slug: str) -> Organization | None:
    result = await db.execute(select(Organization).where(Organization.slug == slug))
    return result.scalar_one_or_none()
