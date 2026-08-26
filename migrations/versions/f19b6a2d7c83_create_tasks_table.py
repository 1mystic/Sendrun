"""create tasks table

Revision ID: f19b6a2d7c83
Revises: a3f7c9e21b44
Create Date: 2026-08-26 00:05:00.000000

"""
from typing import Sequence, Union

from alembic import op

from packages.durable.queue import CREATE_TASKS_TABLE

# revision identifiers, used by Alembic.
revision: str = 'f19b6a2d7c83'
down_revision: Union[str, Sequence[str], None] = 'a3f7c9e21b44'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """The durable engine's own task table (packages/durable/queue.py) had no
    migration backing it — `enqueue_task` and the worker's DEQUEUE/REAP_EXPIRED
    statements were assuming a table nothing ever created. Executed verbatim
    from CREATE_TASKS_TABLE so this migration and the engine's own
    documentation of its schema never drift apart.

    Postgres-only, like every other statement in queue.py (UUID/JSONB column
    types, partial indexes) — SQLite (local dev / the test suite) never runs
    the durable engine's real SQL at all; see queue.py's module docstring and
    enqueue.py's tests, which monkeypatch this table out entirely on SQLite.
    """
    if op.get_bind().dialect.name != "postgresql":
        return
    op.execute(CREATE_TASKS_TABLE)


def downgrade() -> None:
    if op.get_bind().dialect.name != "postgresql":
        return
    op.execute("DROP TABLE IF EXISTS tasks")
