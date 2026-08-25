"""Contacts, tags, groups, and the smart-filter query builder.

Every query here is tenant-scoped via authz.scoped() — see that module for why
the org_id argument is mandatory rather than optional.
"""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, EmailStr, Field
from sqlalchemy import and_, delete, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from packages.shared.audit import record
from packages.shared.authz import require_capability
from packages.shared.models import Contact, ContactGroup, ContactTag, Tag, User

from ..deps import get_db, require_membership, require_user

router = APIRouter(prefix="/api/organizations/{org_id}/contacts", tags=["contacts"])


class ContactIn(BaseModel):
    email: EmailStr
    name: str | None = None
    fields: dict[str, str] = Field(default_factory=dict)
    tags: list[str] = Field(default_factory=list)


class ContactOut(BaseModel):
    id: str
    email: str
    name: str | None
    fields: dict[str, str]
    tags: list[str]
    suppressed: bool


async def _to_out(db: AsyncSession, contact: Contact) -> ContactOut:
    result = await db.execute(
        select(Tag.name).join(ContactTag, ContactTag.tag_id == Tag.id)
        .where(ContactTag.contact_id == contact.id)
    )
    return ContactOut(
        id=str(contact.id), email=contact.email, name=contact.name,
        fields=contact.fields, tags=[t for (t,) in result.all()] if result else [],
        suppressed=contact.suppressed,
    )


@router.post("", response_model=ContactOut, status_code=status.HTTP_201_CREATED)
async def create_contact(
    org_id: UUID,
    body: ContactIn,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_user),
) -> ContactOut:
    membership = await require_membership(org_id, db, user)
    require_capability(membership, "edit_contacts")

    contact = Contact(
        org_id=org_id, email=str(body.email).lower(), name=body.name, fields=body.fields
    )
    db.add(contact)
    await db.flush()

    for tag_name in body.tags:
        existing = await db.execute(
            select(Tag).where(Tag.org_id == org_id, Tag.name == tag_name)
        )
        tag = existing.scalar_one_or_none()
        if tag is None:
            tag = Tag(org_id=org_id, name=tag_name)
            db.add(tag)
            await db.flush()
        db.add(ContactTag(contact_id=contact.id, tag_id=tag.id))

    await record(db, org_id=org_id, actor_user_id=user.id, action="contact.created",
                 target_type="contact", target_id=str(contact.id))
    await db.commit()
    return await _to_out(db, contact)


class SmartFilter(BaseModel):
    """AND of these conditions. Each condition is itself an OR over its values —
    e.g. tags=["speaker","alumni"] matches either tag. This mirrors the query
    language sketched in PLAN.md ("organization = XYZ AND role = recruiter")."""

    tags: list[str] = Field(default_factory=list)
    group_id: UUID | None = None
    exclude_suppressed: bool = True
    search: str | None = None


@router.get("", response_model=list[ContactOut])
async def list_contacts(
    org_id: UUID,
    tag: list[str] | None = None,
    group_id: UUID | None = None,
    search: str | None = None,
    limit: int = 100,
    offset: int = 0,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_user),
) -> list[ContactOut]:
    await require_membership(org_id, db, user)

    stmt = select(Contact).where(Contact.org_id == org_id)
    if tag:
        stmt = stmt.join(ContactTag, ContactTag.contact_id == Contact.id).join(
            Tag, and_(Tag.id == ContactTag.tag_id, Tag.name.in_(tag))
        )
    if group_id:
        stmt = stmt.join(ContactGroup, and_(
            ContactGroup.contact_id == Contact.id, ContactGroup.group_id == group_id
        ))
    if search:
        like = f"%{search.lower()}%"
        stmt = stmt.where(or_(Contact.email.ilike(like), Contact.name.ilike(like)))
    stmt = stmt.distinct().limit(min(limit, 500)).offset(offset)

    contacts = (await db.execute(stmt)).scalars().all()
    return [await _to_out(db, c) for c in contacts]


@router.post("/resolve", response_model=list[str])
async def resolve_recipients(
    org_id: UUID,
    filt: SmartFilter,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_user),
) -> list[str]:
    """Resolve a SmartFilter to contact ids. This is what a campaign's recipient
    picker calls before fan-out — the campaign launch endpoint re-resolves at
    launch time rather than trusting a client-supplied id list, so a contact
    unsubscribing between preview and launch is honored."""
    await require_membership(org_id, db, user)

    stmt = select(Contact.id).where(Contact.org_id == org_id)
    if filt.tags:
        stmt = stmt.join(ContactTag, ContactTag.contact_id == Contact.id).join(
            Tag, and_(Tag.id == ContactTag.tag_id, Tag.name.in_(filt.tags))
        )
    if filt.group_id:
        stmt = stmt.join(ContactGroup, and_(
            ContactGroup.contact_id == Contact.id, ContactGroup.group_id == filt.group_id
        ))
    if filt.exclude_suppressed:
        stmt = stmt.where(Contact.suppressed.is_(False))
    if filt.search:
        like = f"%{filt.search.lower()}%"
        stmt = stmt.where(or_(Contact.email.ilike(like), Contact.name.ilike(like)))

    result = await db.execute(stmt.distinct())
    return [str(cid) for (cid,) in result.all()]


@router.delete("/{contact_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_contact(
    org_id: UUID,
    contact_id: UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_user),
) -> None:
    membership = await require_membership(org_id, db, user)
    require_capability(membership, "edit_contacts")

    contact = await db.get(Contact, contact_id)
    if contact is None or contact.org_id != org_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "contact not found")

    await db.execute(delete(ContactTag).where(ContactTag.contact_id == contact_id))
    await db.execute(delete(ContactGroup).where(ContactGroup.contact_id == contact_id))
    await db.delete(contact)
    await record(db, org_id=org_id, actor_user_id=user.id, action="contact.deleted",
                 target_type="contact", target_id=str(contact_id))
    await db.commit()
