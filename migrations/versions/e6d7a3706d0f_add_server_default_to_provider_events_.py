"""add server default to provider_events.attempts

Revision ID: e6d7a3706d0f
Revises: 0bd39148ddf7
Create Date: 2026-08-25 20:21:00.529218

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'e6d7a3706d0f'
down_revision: Union[str, Sequence[str], None] = '0bd39148ddf7'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Add a DB-level default so the webhook ingest path's raw SQL INSERT
    (services/api/webhooks/ingest.py) does not violate the NOT NULL
    constraint on this column — the ORM's Python-side default=0 is only
    honored when inserting through the ORM, which that raw insert bypasses.
    Autogenerate does not reliably detect server_default changes, so this was
    written by hand rather than trusted from the generated diff.

    SQLite has no ALTER COLUMN ... SET DEFAULT; batch_alter_table works around
    that by rebuilding the table (Postgres uses the direct ALTER instead, via
    the same call)."""
    with op.batch_alter_table("provider_events") as batch_op:
        batch_op.alter_column(
            "attempts", existing_type=sa.Integer(), server_default="0", existing_nullable=False,
        )


def downgrade() -> None:
    with op.batch_alter_table("provider_events") as batch_op:
        batch_op.alter_column(
            "attempts", existing_type=sa.Integer(), server_default=None, existing_nullable=False,
        )
