"""add from_address/from_name/reply_to_address to organizations

Revision ID: b2c4e8f1a9d3
Revises: f0fd8acb14ac
Create Date: 2026-08-27 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'b2c4e8f1a9d3'
down_revision: Union[str, Sequence[str], None] = 'f0fd8acb14ac'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """NULL by default — an org that never configures a sending identity
    still sends, falling back to the global FROM_ADDRESS/FROM_NAME (see
    packages/shared/config.py). Never a NOT NULL default value here, since a
    non-NULL default would silently claim every existing org already chose
    an identity it never actually set."""
    with op.batch_alter_table("organizations") as batch_op:
        batch_op.add_column(sa.Column("from_address", sa.String(length=320), nullable=True))
        batch_op.add_column(sa.Column("from_name", sa.String(length=200), nullable=True))
        batch_op.add_column(sa.Column("reply_to_address", sa.String(length=320), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("organizations") as batch_op:
        batch_op.drop_column("reply_to_address")
        batch_op.drop_column("from_name")
        batch_op.drop_column("from_address")
