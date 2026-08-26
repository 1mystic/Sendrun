"""add unique org_id+name to groups

Revision ID: f0fd8acb14ac
Revises: f19b6a2d7c83
Create Date: 2026-08-26 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'f0fd8acb14ac'
down_revision: Union[str, Sequence[str], None] = 'f19b6a2d7c83'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """A mailing-list name is how a user picks it out of a dropdown at campaign
    launch — two groups named "Q3 Prospects" in the same org is a UX trap, not a
    valid state. No existing rows are expected to collide since groups.py is new,
    but batch_alter_table keeps this consistent with the rest of the chain."""
    with op.batch_alter_table("groups") as batch_op:
        batch_op.create_unique_constraint("uq_group_org_name", ["org_id", "name"])


def downgrade() -> None:
    with op.batch_alter_table("groups") as batch_op:
        batch_op.drop_constraint("uq_group_org_name", type_="unique")
