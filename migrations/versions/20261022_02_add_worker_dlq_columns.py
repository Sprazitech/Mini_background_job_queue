"""Add worker error context columns required by DLQ archival.

Revision ID: 20261022_02
Revises: 20261022_01
Create Date: 2026-10-22
"""

from typing import Sequence, Union

from alembic import op


revision: str = "20261022_02"
down_revision: Union[str, None] = "20261022_01"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("ALTER TABLE jobs ADD COLUMN IF NOT EXISTS metadata JSONB NOT NULL DEFAULT '{}'::jsonb")
    op.execute("ALTER TABLE jobs ADD COLUMN IF NOT EXISTS error_message TEXT")
    op.execute("ALTER TABLE jobs ADD COLUMN IF NOT EXISTS error_stack TEXT")
    op.execute("ALTER TABLE jobs ADD COLUMN IF NOT EXISTS worker_id TEXT")


def downgrade() -> None:
    op.execute("ALTER TABLE jobs DROP COLUMN IF EXISTS worker_id")
    op.execute("ALTER TABLE jobs DROP COLUMN IF EXISTS error_stack")
    op.execute("ALTER TABLE jobs DROP COLUMN IF EXISTS error_message")
    op.execute("ALTER TABLE jobs DROP COLUMN IF EXISTS metadata")
