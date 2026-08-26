"""Mailing lists (Group/ContactGroup) — CRUD plus the bulk-import endpoint that
is the actual product entry point ("paste a spreadsheet, get a list").

The frontend parses CSV/pasted text into rows client-side; this module never
parses raw CSV, only already-structured {header: value} dicts.
"""

from __future__ import annotations

import re
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, EmailStr, Field, ValidationError
from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from packages.shared.audit import record
from packages.shared.authz import require_capability
from packages.shared.models import Contact, ContactGroup, Group, User

from ..deps import get_db, require_membership, require_user
from .contacts import ContactOut, _to_out

router = APIRouter(prefix="/api/organizations/{org_id}/groups", tags=["groups"])

MAX_IMPORT_ROWS = 5000

_FIELD_KEY_RE = re.compile(r"[^a-zA-Z0-9_]")


def _sanitize_field_key(raw: str) -> str:
    key = _FIELD_KEY_RE.sub("_", raw.strip().lower().replace(" ", "_").replace("-", "_"))
    key = key.strip("_")
    if not key or key[0].isdigit():
        key = f"_{key}"
    return key


class GroupIn(BaseModel):
    name: str = Field(min_length=1, max_length=120)


class GroupOut(BaseModel):
    id: str
    name: str
    contact_count: int


class GroupDetailOut(BaseModel):
    id: str
    name: str
    contacts: list[ContactOut]


@router.post("", response_model=GroupOut, status_code=status.HTTP_201_CREATED)
async def create_group(
    org_id: UUID,
    body: GroupIn,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_user),
) -> GroupOut:
    membership = await require_membership(org_id, db, user)
    require_capability(membership, "edit_contacts")

    existing = await db.execute(
        select(Group).where(Group.org_id == org_id, Group.name == body.name)
    )
    if existing.scalar_one_or_none() is not None:
        raise HTTPException(status.HTTP_409_CONFLICT, "a group with this name already exists")

    group = Group(org_id=org_id, name=body.name)
    db.add(group)
    await db.flush()

    await record(db, org_id=org_id, actor_user_id=user.id, action="group.created",
                 target_type="group", target_id=str(group.id))
    await db.commit()
    return GroupOut(id=str(group.id), name=group.name, contact_count=0)


@router.get("", response_model=list[GroupOut])
async def list_groups(
    org_id: UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_user),
) -> list[GroupOut]:
    await require_membership(org_id, db, user)

    stmt = (
        select(Group.id, Group.name, func.count(ContactGroup.contact_id))
        .outerjoin(ContactGroup, ContactGroup.group_id == Group.id)
        .where(Group.org_id == org_id)
        .group_by(Group.id, Group.name)
        .order_by(Group.name)
    )
    rows = (await db.execute(stmt)).all()
    return [GroupOut(id=str(gid), name=name, contact_count=count) for gid, name, count in rows]


async def _get_group_or_404(db: AsyncSession, org_id: UUID, group_id: UUID) -> Group:
    group = await db.get(Group, group_id)
    if group is None or group.org_id != org_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "group not found")
    return group


@router.get("/{group_id}", response_model=GroupDetailOut)
async def get_group(
    org_id: UUID,
    group_id: UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_user),
) -> GroupDetailOut:
    await require_membership(org_id, db, user)
    group = await _get_group_or_404(db, org_id, group_id)

    stmt = (
        select(Contact)
        .join(ContactGroup, ContactGroup.contact_id == Contact.id)
        .where(ContactGroup.group_id == group_id)
    )
    contacts = (await db.execute(stmt)).scalars().all()
    return GroupDetailOut(
        id=str(group.id), name=group.name,
        contacts=[await _to_out(db, c) for c in contacts],
    )


@router.delete("/{group_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_group(
    org_id: UUID,
    group_id: UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_user),
) -> None:
    membership = await require_membership(org_id, db, user)
    require_capability(membership, "edit_contacts")
    group = await _get_group_or_404(db, org_id, group_id)

    await db.execute(delete(ContactGroup).where(ContactGroup.group_id == group_id))
    await db.delete(group)
    await record(db, org_id=org_id, actor_user_id=user.id, action="group.deleted",
                 target_type="group", target_id=str(group_id))
    await db.commit()


# ─────────────────────────────────────────────────────────────────────────────
# Bulk import
# ─────────────────────────────────────────────────────────────────────────────

class ImportRow(BaseModel):
    values: dict[str, str]


class BulkImportRequest(BaseModel):
    email_column: str
    name_column: str | None = None
    rows: list[ImportRow] = Field(max_length=MAX_IMPORT_ROWS)


class ImportRowError(BaseModel):
    row_index: int
    reason: str


class BulkImportResult(BaseModel):
    created: int
    updated: int
    skipped: list[ImportRowError]
    group_contact_count: int


class _EmailCheck(BaseModel):
    email: EmailStr


@router.post("/{group_id}/import", response_model=BulkImportResult)
async def bulk_import(
    org_id: UUID,
    group_id: UUID,
    body: BulkImportRequest,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_user),
) -> BulkImportResult:
    membership = await require_membership(org_id, db, user)
    require_capability(membership, "edit_contacts")
    await _get_group_or_404(db, org_id, group_id)

    if len(body.rows) > MAX_IMPORT_ROWS:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY,
                             f"import capped at {MAX_IMPORT_ROWS} rows per request")

    skipped: list[ImportRowError] = []

    # parsed[i] = (email, name, fields) for every row that passed validation
    parsed: dict[int, tuple[str, str | None, dict[str, str]]] = {}

    for i, row in enumerate(body.rows):
        raw_email = row.values.get(body.email_column, "").strip()
        if not raw_email:
            skipped.append(ImportRowError(row_index=i, reason="missing email"))
            continue
        try:
            email = str(_EmailCheck(email=raw_email).email).lower()
        except ValidationError:
            skipped.append(ImportRowError(row_index=i, reason=f"invalid email: {raw_email!r}"))
            continue

        name = None
        if body.name_column:
            name = row.values.get(body.name_column, "").strip() or None

        field_keys: dict[str, str] = {}
        collision: str | None = None
        for raw_key in row.values:
            if raw_key in (body.email_column, body.name_column):
                continue
            key = _sanitize_field_key(raw_key)
            if key in field_keys and field_keys[key] != raw_key:
                collision = key
                break
            field_keys[key] = raw_key

        if collision is not None:
            skipped.append(ImportRowError(
                row_index=i,
                reason=f"ambiguous column mapping: multiple headers sanitize to '{collision}'",
            ))
            continue

        fields = {
            _sanitize_field_key(raw_key): value
            for raw_key, value in row.values.items()
            if raw_key not in (body.email_column, body.name_column)
        }
        parsed[i] = (email, name, fields)

    if not parsed:
        return BulkImportResult(
            created=0, updated=0, skipped=skipped,
            group_contact_count=await _group_contact_count(db, group_id),
        )

    emails = {email for email, _, _ in parsed.values()}
    existing_rows = (
        await db.execute(select(Contact).where(Contact.org_id == org_id, Contact.email.in_(emails)))
    ).scalars().all()
    existing_by_email = {c.email: c for c in existing_rows}

    created = 0
    updated = 0
    touched_contact_ids: set[UUID] = set()

    # Last row wins for a given email within one import batch — dedupe intra-batch
    # the same way we dedupe against the existing table.
    by_email: dict[str, tuple[str | None, dict[str, str]]] = {}
    for email, name, fields in parsed.values():
        by_email[email] = (name, fields)

    for email, (name, fields) in by_email.items():
        contact = existing_by_email.get(email)
        if contact is None:
            contact = Contact(org_id=org_id, email=email, name=name, fields=fields)
            db.add(contact)
            await db.flush()
            created += 1
        else:
            # suppressed/unsubscribed_at are never touched here — an existing
            # suppression must survive re-import untouched (CLAUDE.md, and the
            # invariant documented on Contact.suppressed in models.py).
            if name is not None:
                contact.name = name
            contact.fields = {**contact.fields, **fields}
            updated += 1
        touched_contact_ids.add(contact.id)

    if touched_contact_ids:
        existing_membership = (
            await db.execute(
                select(ContactGroup.contact_id).where(
                    ContactGroup.group_id == group_id,
                    ContactGroup.contact_id.in_(touched_contact_ids),
                )
            )
        ).scalars().all()
        already_in_group = set(existing_membership)
        to_add = touched_contact_ids - already_in_group
        for cid in to_add:
            db.add(ContactGroup(contact_id=cid, group_id=group_id))

    await record(db, org_id=org_id, actor_user_id=user.id, action="group.imported",
                 target_type="group", target_id=str(group_id),
                 metadata={"created": created, "updated": updated, "skipped": len(skipped)})
    await db.commit()

    return BulkImportResult(
        created=created, updated=updated, skipped=skipped,
        group_contact_count=await _group_contact_count(db, group_id),
    )


async def _group_contact_count(db: AsyncSession, group_id: UUID) -> int:
    result = await db.execute(
        select(func.count(ContactGroup.contact_id)).where(ContactGroup.group_id == group_id)
    )
    return result.scalar_one()
