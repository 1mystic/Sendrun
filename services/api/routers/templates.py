"""EmailTemplate CRUD, versioning, and per-contact preview.

Saving a template always creates a new TemplateVersion — templates are never
edited in place. A Campaign pins the exact version it launched with (see
Campaign.template_version), so editing a template later can never change what
a past campaign actually sent.
"""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from packages.shared.audit import record
from packages.shared.authz import require_capability
from packages.shared.models import Contact, EmailTemplate, TemplateVersion, User
from packages.shared.render import (
    LinkCheck,
    RenderedEmail,
    TemplateValidationError,
    render_for_contact,
    validate_template,
)

from ..deps import get_db, require_membership, require_user

router = APIRouter(prefix="/api/organizations/{org_id}/templates", tags=["templates"])


class TemplateIn(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    subject: str = Field(min_length=1, max_length=500)
    html_body: str
    text_body: str | None = None
    variables: list[str] = Field(default_factory=list)


class TemplateVersionOut(BaseModel):
    version: int
    subject: str
    html_body: str
    text_body: str | None
    variables: list[str]


class TemplateOut(BaseModel):
    id: str
    name: str
    current_version: int
    latest: TemplateVersionOut


async def _latest_version(db: AsyncSession, template_id: UUID, version: int) -> TemplateVersion:
    result = await db.execute(
        select(TemplateVersion).where(
            TemplateVersion.template_id == template_id, TemplateVersion.version == version
        )
    )
    row = result.scalar_one_or_none()
    if row is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "template version not found")
    return row


def _to_out(template: EmailTemplate, version: TemplateVersion) -> TemplateOut:
    return TemplateOut(
        id=str(template.id),
        name=template.name,
        current_version=template.current_version,
        latest=TemplateVersionOut(
            version=version.version, subject=version.subject, html_body=version.html_body,
            text_body=version.text_body, variables=version.variables,
        ),
    )


@router.post("", response_model=TemplateOut, status_code=status.HTTP_201_CREATED)
async def create_template(
    org_id: UUID,
    body: TemplateIn,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_user),
) -> TemplateOut:
    membership = await require_membership(org_id, db, user)
    require_capability(membership, "edit_template")

    try:
        validate_template(body.subject, body.html_body, body.text_body, body.variables)
    except TemplateValidationError as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, str(exc)) from exc

    template = EmailTemplate(org_id=org_id, name=body.name.strip(), current_version=1)
    db.add(template)
    await db.flush()

    version = TemplateVersion(
        template_id=template.id, version=1, subject=body.subject,
        html_body=body.html_body, text_body=body.text_body, variables=body.variables,
    )
    db.add(version)

    await record(db, org_id=org_id, actor_user_id=user.id, action="template.created",
                 target_type="template", target_id=str(template.id))
    await db.commit()
    return _to_out(template, version)


@router.get("", response_model=list[TemplateOut])
async def list_templates(
    org_id: UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_user),
) -> list[TemplateOut]:
    await require_membership(org_id, db, user)

    templates = (
        await db.execute(select(EmailTemplate).where(EmailTemplate.org_id == org_id))
    ).scalars().all()

    out: list[TemplateOut] = []
    for t in templates:
        version = await _latest_version(db, t.id, t.current_version)
        out.append(_to_out(t, version))
    return out


@router.put("/{template_id}", response_model=TemplateOut)
async def update_template(
    org_id: UUID,
    template_id: UUID,
    body: TemplateIn,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_user),
) -> TemplateOut:
    """Always creates a new version. There is no in-place edit — see module docstring."""
    membership = await require_membership(org_id, db, user)
    require_capability(membership, "edit_template")

    template = await db.get(EmailTemplate, template_id)
    if template is None or template.org_id != org_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "template not found")

    try:
        validate_template(body.subject, body.html_body, body.text_body, body.variables)
    except TemplateValidationError as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, str(exc)) from exc

    template.name = body.name.strip()
    template.current_version += 1
    version = TemplateVersion(
        template_id=template.id, version=template.current_version, subject=body.subject,
        html_body=body.html_body, text_body=body.text_body, variables=body.variables,
    )
    db.add(version)

    await record(db, org_id=org_id, actor_user_id=user.id, action="template.versioned",
                 target_type="template", target_id=str(template.id),
                 metadata={"version": template.current_version})
    await db.commit()
    return _to_out(template, version)


class PreviewRequest(BaseModel):
    contact_id: UUID
    # Optional overrides so the compose screen can preview edits before saving.
    subject: str | None = None
    html_body: str | None = None
    text_body: str | None = None
    variables: list[str] | None = None


class LinkCheckOut(BaseModel):
    url: str
    ok: bool
    reason: str = ""

    @classmethod
    def from_check(cls, c: LinkCheck) -> LinkCheckOut:
        return cls(url=c.url, ok=c.ok, reason=c.reason)


class PreviewOut(BaseModel):
    subject: str
    html_body: str
    text_body: str | None
    missing_variables: list[str]
    is_complete: bool
    links: list[LinkCheckOut]

    @classmethod
    def from_rendered(cls, r: RenderedEmail) -> PreviewOut:
        return cls(
            subject=r.subject, html_body=r.html_body, text_body=r.text_body,
            missing_variables=list(r.missing_variables), is_complete=r.is_complete,
            links=[LinkCheckOut.from_check(link) for link in r.links],
        )


@router.post("/{template_id}/preview", response_model=PreviewOut)
async def preview_template(
    org_id: UUID,
    template_id: UUID,
    body: PreviewRequest,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_user),
) -> PreviewOut:
    """Render this template for one specific contact. This is what the compose
    screen's "preview as recipient" calls on every keystroke/selection change —
    it must never hit the network (see render.check_link's docstring) so it
    stays fast enough for that."""
    await require_membership(org_id, db, user)

    template = await db.get(EmailTemplate, template_id)
    if template is None or template.org_id != org_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "template not found")

    contact = await db.get(Contact, body.contact_id)
    if contact is None or contact.org_id != org_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "contact not found")

    if body.subject is not None:
        subject, html_body, text_body, variables = (
            body.subject, body.html_body or "", body.text_body, body.variables or [],
        )
    else:
        version = await _latest_version(db, template.id, template.current_version)
        subject, html_body, text_body, variables = (
            version.subject, version.html_body, version.text_body, version.variables,
        )

    contact_context = {**contact.fields}
    if "first_name" in variables and "first_name" not in contact_context and contact.name:
        contact_context["first_name"] = contact.name.split(" ")[0]

    try:
        rendered = render_for_contact(
            subject=subject, html_body=html_body, text_body=text_body,
            declared_variables=variables, contact_fields=contact_context,
        )
    except TemplateValidationError as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, str(exc)) from exc

    return PreviewOut.from_rendered(rendered)
