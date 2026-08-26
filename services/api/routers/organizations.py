"""Organization creation, membership listing, and invites.

Creating an org and making the creator its Owner happen in one transaction — an
org with zero members would be unreachable by anyone, including its creator.
"""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, EmailStr, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from packages.shared.audit import record
from packages.shared.authz import Role, get_membership, org_for_slug, require_capability
from packages.shared.models import (
    AuditLog,
    EmailTemplate,
    Organization,
    OrganizationMember,
    TemplateVersion,
    User,
)
from packages.shared.starter_templates import STARTER_TEMPLATES

from ..deps import get_db, require_membership, require_user
from .auth import slugify

router = APIRouter(prefix="/api/organizations", tags=["organizations"])


class CreateOrgRequest(BaseModel):
    name: str = Field(min_length=1, max_length=200)


class OrgOut(BaseModel):
    id: str
    name: str
    slug: str
    role: str


class MemberOut(BaseModel):
    user_id: str
    name: str
    email: str
    role: str


class InviteRequest(BaseModel):
    email: EmailStr
    role: str = "editor"


class UpdateOrgRequest(BaseModel):
    name: str = Field(min_length=1, max_length=200)


class AuditLogOut(BaseModel):
    id: str
    actor_user_id: str | None
    actor_kind: str
    action: str
    target_type: str | None
    target_id: str | None
    metadata: dict
    created_at: str


async def _seed_starter_templates(db: AsyncSession, org_id: UUID) -> None:
    """Every new org gets a small set of ready-to-send templates rather than
    an empty list — real EmailTemplate + TemplateVersion rows, valid under
    render.validate_template's declared-variable rules."""
    for starter in STARTER_TEMPLATES:
        template = EmailTemplate(org_id=org_id, name=starter.name, current_version=1)
        db.add(template)
        await db.flush()
        db.add(TemplateVersion(
            template_id=template.id, version=1, subject=starter.subject,
            html_body=starter.html_body, text_body=starter.text_body,
            variables=starter.variables,
        ))


async def _unique_slug(db: AsyncSession, base: str) -> str:
    slug = slugify(base)
    candidate = slug
    suffix = 1
    while await org_for_slug(db, candidate) is not None:
        suffix += 1
        candidate = f"{slug}-{suffix}"
    return candidate


@router.post("", response_model=OrgOut, status_code=status.HTTP_201_CREATED)
async def create_organization(
    body: CreateOrgRequest,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_user),
) -> OrgOut:
    slug = await _unique_slug(db, body.name)
    org = Organization(name=body.name.strip(), slug=slug)
    db.add(org)
    await db.flush()

    db.add(OrganizationMember(org_id=org.id, user_id=user.id, role=Role.OWNER.name.lower()))
    await _seed_starter_templates(db, org.id)
    await record(db, org_id=org.id, actor_user_id=user.id, action="organization.created",
                 target_type="organization", target_id=str(org.id))
    await db.commit()
    return OrgOut(id=str(org.id), name=org.name, slug=org.slug, role=Role.OWNER.name.lower())


@router.get("", response_model=list[OrgOut])
async def list_my_organizations(
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_user),
) -> list[OrgOut]:
    result = await db.execute(
        select(Organization, OrganizationMember.role)
        .join(OrganizationMember, OrganizationMember.org_id == Organization.id)
        .where(OrganizationMember.user_id == user.id)
    )
    return [
        OrgOut(id=str(org.id), name=org.name, slug=org.slug, role=role)
        for org, role in result.all()
    ]


@router.get("/{org_id}/members", response_model=list[MemberOut])
async def list_members(
    org_id: UUID,
    db: AsyncSession = Depends(get_db),
    membership=Depends(require_membership),
) -> list[MemberOut]:
    result = await db.execute(
        select(User, OrganizationMember.role)
        .join(OrganizationMember, OrganizationMember.user_id == User.id)
        .where(OrganizationMember.org_id == org_id)
    )
    return [
        MemberOut(user_id=str(u.id), name=u.name, email=u.email, role=role)
        for u, role in result.all()
    ]


@router.post("/{org_id}/invites", status_code=status.HTTP_202_ACCEPTED)
async def invite_member(
    org_id: UUID,
    body: InviteRequest,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_user),
) -> dict[str, str]:
    membership = await get_membership(db, user, org_id)
    require_capability(membership, "manage_members")

    try:
        Role.parse(body.role)
    except KeyError as exc:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT, f"unknown role: {body.role}"
        ) from exc

    # Phase 1: record the invite in the audit log; actually creating a
    # pending-invite row + sending the email is Phase 5 (notifications).
    await record(
        db, org_id=org_id, actor_user_id=user.id, action="member.invited",
        target_type="invite", target_id=body.email,
        metadata={"role": body.role},
    )
    await db.commit()
    return {"status": "invited", "email": body.email, "role": body.role}


@router.patch("/{org_id}", response_model=OrgOut)
async def update_organization(
    org_id: UUID,
    body: UpdateOrgRequest,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_user),
) -> OrgOut:
    membership = require_capability(await get_membership(db, user, org_id), "manage_settings")

    org = await db.get(Organization, org_id)
    if org is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "organization not found")

    org.name = body.name.strip()
    await record(db, org_id=org_id, actor_user_id=user.id, action="organization.updated",
                 target_type="organization", target_id=str(org_id))
    await db.commit()
    return OrgOut(id=str(org.id), name=org.name, slug=org.slug, role=membership.role.name.lower())


@router.get("/{org_id}/audit-log", response_model=list[AuditLogOut])
async def list_audit_log(
    org_id: UUID,
    limit: int = 50,
    offset: int = 0,
    db: AsyncSession = Depends(get_db),
    membership=Depends(require_membership),
) -> list[AuditLogOut]:
    """The notification feed's data source — AuditLog is already an
    append-only, actor-attributed, org-scoped event trail (CLAUDE.md
    invariant 8), so notifications are a read over it rather than a new
    model."""
    result = await db.execute(
        select(AuditLog)
        .where(AuditLog.org_id == org_id)
        .order_by(AuditLog.created_at.desc())
        .limit(min(limit, 200))
        .offset(offset)
    )
    return [
        AuditLogOut(
            id=str(a.id), actor_user_id=str(a.actor_user_id) if a.actor_user_id else None,
            actor_kind=a.actor_kind, action=a.action, target_type=a.target_type,
            target_id=a.target_id, metadata=a.metadata_, created_at=a.created_at.isoformat(),
        )
        for a in result.scalars().all()
    ]
