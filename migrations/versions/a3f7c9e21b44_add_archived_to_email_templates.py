"""add archived to email_templates

Revision ID: a3f7c9e21b44
Revises: e6d7a3706d0f
Create Date: 2026-08-26 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'a3f7c9e21b44'
down_revision: Union[str, Sequence[str], None] = 'e6d7a3706d0f'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Soft-delete flag for templates. A campaign pins template_id +
    template_version, so a hard DELETE would orphan any campaign's history —
    archiving instead just excludes the template from the default list.

    server_default keeps every existing row non-archived without a separate
    backfill statement; the Python-side default=False only applies to new
    ORM inserts."""
    with op.batch_alter_table("email_templates") as batch_op:
        batch_op.add_column(
            sa.Column("archived", sa.Boolean(), nullable=False, server_default="false")
        )


def downgrade() -> None:
    with op.batch_alter_table("email_templates") as batch_op:
        batch_op.drop_column("archived")
