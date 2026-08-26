"""SQLAlchemy models — Phase 1 domain plus the tables the durable engine and
webhook processor already assume.

Conventions:
  - Every table has a UUID primary key (`gen_random_uuid()` on Postgres, a Python
    default on SQLite for tests).
  - Every tenant-scoped table carries `org_id` directly — never inferred through a
    join — so a query missing a WHERE org_id=... fails loudly instead of leaking
    cross-tenant data.
  - Status columns store the string values of the enums in transitions.py. The
    guarded UPDATE statements live in transitions.py, not here; this module is
    schema only.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import (
    Boolean,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship
from sqlalchemy.types import JSON, TypeDecorator


class GUID(TypeDecorator):
    """UUID that is a real UUID column on Postgres and a CHAR(36) on SQLite.

    Lets the same models run against Neon in production and SQLite in tests
    without two schemas to maintain.
    """

    impl = String(36)
    cache_ok = True

    def load_dialect_impl(self, dialect):
        if dialect.name == "postgresql":
            return dialect.type_descriptor(PG_UUID(as_uuid=True))
        return dialect.type_descriptor(String(36))

    def process_bind_param(self, value, dialect):
        if value is None:
            return value
        if dialect.name == "postgresql":
            return value
        return str(value)

    def process_result_value(self, value, dialect):
        if value is None:
            return value
        if isinstance(value, uuid.UUID):
            return value
        return uuid.UUID(value)


class JSONVariant(TypeDecorator):
    """JSONB on Postgres, JSON on SQLite."""

    impl = JSON
    cache_ok = True

    def load_dialect_impl(self, dialect):
        if dialect.name == "postgresql":
            return dialect.type_descriptor(JSONB())
        return dialect.type_descriptor(JSON())


def _uuid() -> uuid.UUID:
    return uuid.uuid4()


class Base(DeclarativeBase):
    pass


class TimestampMixin:
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


# ─────────────────────────────────────────────────────────────────────────────
# Identity & tenancy
# ─────────────────────────────────────────────────────────────────────────────

class User(Base, TimestampMixin):
    __tablename__ = "users"

    id: Mapped[uuid.UUID] = mapped_column(GUID(), primary_key=True, default=_uuid)
    email: Mapped[str] = mapped_column(String(320), unique=True, index=True)
    name: Mapped[str] = mapped_column(String(200))
    # Argon2 hash. Never store or log the raw password.
    password_hash: Mapped[str] = mapped_column(String(255))
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)

    memberships: Mapped[list[OrganizationMember]] = relationship(back_populates="user")


class Organization(Base, TimestampMixin):
    __tablename__ = "organizations"

    id: Mapped[uuid.UUID] = mapped_column(GUID(), primary_key=True, default=_uuid)
    name: Mapped[str] = mapped_column(String(200))
    slug: Mapped[str] = mapped_column(String(80), unique=True, index=True)

    members: Mapped[list[OrganizationMember]] = relationship(back_populates="organization")


# Role hierarchy, most to least privileged. Enforced by packages/shared/authz.py,
# not by database constraints — a CHECK constraint can't express "Editor may create
# campaigns but not manage billing."
class OrganizationMember(Base, TimestampMixin):
    __tablename__ = "organization_members"
    __table_args__ = (UniqueConstraint("org_id", "user_id", name="uq_org_member"),)

    id: Mapped[uuid.UUID] = mapped_column(GUID(), primary_key=True, default=_uuid)
    org_id: Mapped[uuid.UUID] = mapped_column(GUID(), ForeignKey("organizations.id"), index=True)
    user_id: Mapped[uuid.UUID] = mapped_column(GUID(), ForeignKey("users.id"), index=True)
    # owner | admin | editor | viewer
    role: Mapped[str] = mapped_column(String(20))

    organization: Mapped[Organization] = relationship(back_populates="members")
    user: Mapped[User] = relationship(back_populates="memberships")


class Session(Base, TimestampMixin):
    """Server-side session record backing the signed session cookie.

    Storing sessions server-side (rather than a stateless JWT) means sign-out and
    forced revocation actually work — you can delete the row.
    """

    __tablename__ = "sessions"

    id: Mapped[uuid.UUID] = mapped_column(GUID(), primary_key=True, default=_uuid)
    user_id: Mapped[uuid.UUID] = mapped_column(GUID(), ForeignKey("users.id"), index=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    user_agent: Mapped[str | None] = mapped_column(String(500), nullable=True)


# ─────────────────────────────────────────────────────────────────────────────
# Contacts
# ─────────────────────────────────────────────────────────────────────────────

class Tag(Base, TimestampMixin):
    __tablename__ = "tags"
    __table_args__ = (UniqueConstraint("org_id", "name", name="uq_tag_org_name"),)

    id: Mapped[uuid.UUID] = mapped_column(GUID(), primary_key=True, default=_uuid)
    org_id: Mapped[uuid.UUID] = mapped_column(GUID(), ForeignKey("organizations.id"), index=True)
    name: Mapped[str] = mapped_column(String(80))


class ContactTag(Base):
    __tablename__ = "contact_tags"

    contact_id: Mapped[uuid.UUID] = mapped_column(
        GUID(), ForeignKey("contacts.id"), primary_key=True
    )
    tag_id: Mapped[uuid.UUID] = mapped_column(GUID(), ForeignKey("tags.id"), primary_key=True)


class Group(Base, TimestampMixin):
    """A saved, named set of contacts. Distinct from a Tag: a tag is a property of
    a contact; a group is an explicit roster someone curated."""

    __tablename__ = "groups"
    __table_args__ = (UniqueConstraint("org_id", "name", name="uq_group_org_name"),)

    id: Mapped[uuid.UUID] = mapped_column(GUID(), primary_key=True, default=_uuid)
    org_id: Mapped[uuid.UUID] = mapped_column(GUID(), ForeignKey("organizations.id"), index=True)
    name: Mapped[str] = mapped_column(String(120))


class ContactGroup(Base):
    __tablename__ = "contact_groups"

    contact_id: Mapped[uuid.UUID] = mapped_column(
        GUID(), ForeignKey("contacts.id"), primary_key=True
    )
    group_id: Mapped[uuid.UUID] = mapped_column(GUID(), ForeignKey("groups.id"), primary_key=True)


class Contact(Base, TimestampMixin):
    __tablename__ = "contacts"
    __table_args__ = (
        UniqueConstraint("org_id", "email", name="uq_contact_org_email"),
        Index("ix_contacts_org_email", "org_id", "email"),
    )

    id: Mapped[uuid.UUID] = mapped_column(GUID(), primary_key=True, default=_uuid)
    org_id: Mapped[uuid.UUID] = mapped_column(GUID(), ForeignKey("organizations.id"), index=True)
    email: Mapped[str] = mapped_column(String(320))
    name: Mapped[str | None] = mapped_column(String(200), nullable=True)
    # Freeform per-contact fields ({{specialization}}, {{company}}, ...), resolved
    # into template variables at render time. Untrusted input — never treated as
    # instructions to an LLM. See CLAUDE.md invariant 8.
    fields: Mapped[dict] = mapped_column(JSONVariant(), default=dict)

    # Suppression is a first-class, permanent flag, not inferred from bounce
    # history at send time — a contact who unsubscribed must never be re-added to
    # a send list by a later "recover stale contacts" operation.
    unsubscribed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    suppressed: Mapped[bool] = mapped_column(Boolean, default=False)
    suppressed_reason: Mapped[str | None] = mapped_column(String(200), nullable=True)


class Event(Base, TimestampMixin):
    """An Event (e.g. "Hackathon 2026") that Jobs and Campaigns hang off of.
    Purely organizational — carries no execution semantics of its own."""

    __tablename__ = "events"

    id: Mapped[uuid.UUID] = mapped_column(GUID(), primary_key=True, default=_uuid)
    org_id: Mapped[uuid.UUID] = mapped_column(GUID(), ForeignKey("organizations.id"), index=True)
    name: Mapped[str] = mapped_column(String(200))
    starts_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class Job(Base, TimestampMixin):
    """A named outreach purpose ("Volunteer recruitment") under an Event.

    Not to be confused with the durable engine's `tasks` table — this Job is a
    user-facing organizational label; a `tasks` row is the unit of execution. The
    naming collision with the durability engine's own "job" language is
    unfortunate but matches the product vocabulary the frontend already uses.
    """

    __tablename__ = "jobs_"

    id: Mapped[uuid.UUID] = mapped_column(GUID(), primary_key=True, default=_uuid)
    org_id: Mapped[uuid.UUID] = mapped_column(GUID(), ForeignKey("organizations.id"), index=True)
    event_id: Mapped[uuid.UUID | None] = mapped_column(
        GUID(), ForeignKey("events.id"), nullable=True
    )
    name: Mapped[str] = mapped_column(String(200))


# ─────────────────────────────────────────────────────────────────────────────
# Templates
# ─────────────────────────────────────────────────────────────────────────────

class EmailTemplate(Base, TimestampMixin):
    __tablename__ = "email_templates"

    id: Mapped[uuid.UUID] = mapped_column(GUID(), primary_key=True, default=_uuid)
    org_id: Mapped[uuid.UUID] = mapped_column(GUID(), ForeignKey("organizations.id"), index=True)
    name: Mapped[str] = mapped_column(String(200))
    current_version: Mapped[int] = mapped_column(Integer, default=1)
    # Soft-delete only — a campaign pins template_id + template_version, so a
    # hard DELETE would orphan the history of any campaign that used this
    # template. Archived templates stay resolvable by id+version; they are
    # just excluded from the default list.
    archived: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false")


class TemplateVersion(Base, TimestampMixin):
    """Templates are versioned; a Campaign pins the exact version it launched
    with, so editing a template later never changes what a past campaign sent."""

    __tablename__ = "template_versions"
    __table_args__ = (UniqueConstraint("template_id", "version", name="uq_template_version"),)

    id: Mapped[uuid.UUID] = mapped_column(GUID(), primary_key=True, default=_uuid)
    template_id: Mapped[uuid.UUID] = mapped_column(
        GUID(), ForeignKey("email_templates.id"), index=True
    )
    version: Mapped[int] = mapped_column(Integer)
    subject: Mapped[str] = mapped_column(String(500))
    html_body: Mapped[str] = mapped_column(Text)
    text_body: Mapped[str | None] = mapped_column(Text, nullable=True)
    # Declared variable names, e.g. ["first_name","event_name"]. The render
    # pipeline validates against this allowlist rather than accepting any
    # {{...}} the template author typed. See docs/AI_SPEC.md.
    variables: Mapped[list[str]] = mapped_column(JSONVariant(), default=list)


# ─────────────────────────────────────────────────────────────────────────────
# Campaigns & jobs — the durable core
# ─────────────────────────────────────────────────────────────────────────────

class Campaign(Base, TimestampMixin):
    __tablename__ = "campaigns"

    id: Mapped[uuid.UUID] = mapped_column(GUID(), primary_key=True, default=_uuid)
    org_id: Mapped[uuid.UUID] = mapped_column(GUID(), ForeignKey("organizations.id"), index=True)
    name: Mapped[str] = mapped_column(String(200))
    event_id: Mapped[uuid.UUID | None] = mapped_column(
        GUID(), ForeignKey("events.id"), nullable=True
    )
    template_id: Mapped[uuid.UUID] = mapped_column(GUID(), ForeignKey("email_templates.id"))
    template_version: Mapped[int] = mapped_column(Integer)

    # See packages/shared/transitions.py CampaignStatus. Written only via
    # transitions.py's guarded UPDATE — never a bare UPDATE elsewhere.
    status: Mapped[str] = mapped_column(String(20), default="draft", index=True)

    send_rate_per_second: Mapped[int] = mapped_column(Integer, default=8)
    scheduled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    created_by: Mapped[uuid.UUID] = mapped_column(GUID(), ForeignKey("users.id"))


class EmailJob(Base, TimestampMixin):
    """One row per recipient. The unit the durability thesis is about.

    Two status columns, deliberately never collapsed — see CLAUDE.md invariant 2.
    `id` IS the idempotency key handed to the provider (cast to str), so it must
    never be regenerated for a retry of the same intended send; a deliberate
    resend creates a brand-new row instead.
    """

    __tablename__ = "email_jobs"
    __table_args__ = (
        Index("ix_email_jobs_campaign_status", "campaign_id", "send_status"),
        Index("ix_email_jobs_provider_message_id", "provider_message_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(GUID(), primary_key=True, default=_uuid)
    campaign_id: Mapped[uuid.UUID] = mapped_column(GUID(), ForeignKey("campaigns.id"), index=True)
    contact_id: Mapped[uuid.UUID] = mapped_column(GUID(), ForeignKey("contacts.id"), index=True)

    to_addr: Mapped[str] = mapped_column(String(320))
    subject: Mapped[str] = mapped_column(String(500))
    html_body: Mapped[str] = mapped_column(Text)
    text_body: Mapped[str | None] = mapped_column(Text, nullable=True)

    # send_status: queued|sending|sent|failed_transient|failed_permanent|cancelled|skipped
    send_status: Mapped[str] = mapped_column(String(20), default="queued", index=True)
    # delivery_status: NULL|deferred|delivered|bounced|complained — only meaningful
    # once send_status='sent'. See transitions.DELIVERY_RANK for the precedence
    # that makes applying these idempotent under duplicate/out-of-order webhooks.
    delivery_status: Mapped[str | None] = mapped_column(String(20), nullable=True)

    attempt: Mapped[int] = mapped_column(Integer, default=0)
    claimed_by: Mapped[str | None] = mapped_column(String(100), nullable=True)
    claimed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    provider_message_id: Mapped[str | None] = mapped_column(String(200), nullable=True, unique=True)
    sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_error: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Denormalized engagement counters for fast dashboard reads. The
    # authoritative per-event record lives in EmailEngagement; these are a
    # cache, updated by the same statement that inserts an engagement row.
    open_count: Mapped[int] = mapped_column(Integer, default=0)
    click_count: Mapped[int] = mapped_column(Integer, default=0)
    first_opened_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    first_clicked_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )


class ProviderEvent(Base):
    """A raw webhook event, deduplicated on provider_event_id.

    `email_job_id` is nullable ON PURPOSE: events routinely arrive before the send
    activity has recorded `provider_message_id`. See CLAUDE.md invariant 7 and
    services/api/webhooks/processor.py.
    """

    __tablename__ = "provider_events"
    __table_args__ = (
        Index("ix_provider_events_orphan", "provider_message_id", "email_job_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(GUID(), primary_key=True, default=_uuid)
    provider_event_id: Mapped[str] = mapped_column(String(200), unique=True)
    provider_message_id: Mapped[str] = mapped_column(String(200), index=True)
    event_type: Mapped[str] = mapped_column(String(30))
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    received_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    raw: Mapped[dict] = mapped_column(JSONVariant())
    email_job_id: Mapped[uuid.UUID | None] = mapped_column(
        GUID(), ForeignKey("email_jobs.id"), nullable=True, index=True
    )
    processed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    # server_default (not just Python-side default=0): the webhook ingest
    # path inserts this row via raw SQL (services/api/webhooks/ingest.py),
    # bypassing the ORM's INSERT default entirely — only a DB-level default
    # is honored there.
    attempts: Mapped[int] = mapped_column(Integer, default=0, server_default="0")


class EmailEngagement(Base):
    """opened/clicked events. NOT part of the delivery status machine — an email
    can be opened forty times, and a late open must never be able to clobber a
    bounce. See CLAUDE.md invariant 3."""

    __tablename__ = "email_engagements"

    id: Mapped[uuid.UUID] = mapped_column(GUID(), primary_key=True, default=_uuid)
    email_job_id: Mapped[uuid.UUID] = mapped_column(GUID(), ForeignKey("email_jobs.id"), index=True)
    kind: Mapped[str] = mapped_column(String(20))  # opened | clicked
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    user_agent: Mapped[str | None] = mapped_column(String(500), nullable=True)
    url: Mapped[str | None] = mapped_column(String(2000), nullable=True)


# ─────────────────────────────────────────────────────────────────────────────
# Audit
# ─────────────────────────────────────────────────────────────────────────────

class AuditLog(Base):
    """Append-only. Every consequential action a human or an AI agent takes,
    across the org. Required by CLAUDE.md invariant 8: the LLM never mutates the
    DB directly, and every irreversible action it proposes must be traceable to
    the human who approved it — this table is where that trail lives."""

    __tablename__ = "audit_log"
    __table_args__ = (Index("ix_audit_log_org_time", "org_id", "created_at"),)

    id: Mapped[uuid.UUID] = mapped_column(GUID(), primary_key=True, default=_uuid)
    org_id: Mapped[uuid.UUID] = mapped_column(GUID(), ForeignKey("organizations.id"), index=True)
    actor_user_id: Mapped[uuid.UUID | None] = mapped_column(
        GUID(), ForeignKey("users.id"), nullable=True
    )
    actor_kind: Mapped[str] = mapped_column(String(20), default="user")  # user | ai_agent | system
    action: Mapped[str] = mapped_column(String(100))
    target_type: Mapped[str | None] = mapped_column(String(50), nullable=True)
    target_id: Mapped[str | None] = mapped_column(String(100), nullable=True)
    metadata_: Mapped[dict] = mapped_column("metadata", JSONVariant(), default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
