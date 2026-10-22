"""Create queue and worker heartbeat tables.

Revision ID: 20261022_01
Revises:
Create Date: 2026-10-22
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = "20261022_01"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "jobs",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
        sa.Column("type", sa.Text(), nullable=False),
        sa.Column(
            "payload",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
        sa.Column("status", sa.Text(), server_default=sa.text("'queued'"), nullable=False),
        sa.Column("attempts", sa.Integer(), server_default=sa.text("0"), nullable=False),
        sa.Column(
            "max_retries", sa.Integer(), server_default=sa.text("3"), nullable=False
        ),
        sa.Column(
            "next_attempt_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("last_error", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint(
            "type IN ('send_email', 'generate_report')", name="jobs_type_check"
        ),
        sa.CheckConstraint(
            "status IN ('queued', 'running', 'success', 'failed')",
            name="jobs_status_check",
        ),
        sa.PrimaryKeyConstraint("id", name="jobs_pkey"),
    )
    op.create_index(
        "idx_jobs_status_next_attempt",
        "jobs",
        ["status", "next_attempt_at"],
        unique=False,
        postgresql_where=sa.text("status = 'queued'"),
    )

    op.create_table(
        "worker_heartbeat",
        sa.Column("id", sa.Integer(), server_default=sa.text("1"), nullable=False),
        sa.Column(
            "last_seen",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id", name="worker_heartbeat_pkey"),
    )
    op.execute("ALTER TABLE jobs ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE worker_heartbeat ENABLE ROW LEVEL SECURITY")
    op.execute(
        "INSERT INTO worker_heartbeat (id, last_seen) VALUES (1, now()) "
        "ON CONFLICT (id) DO NOTHING"
    )


def downgrade() -> None:
    op.drop_table("worker_heartbeat")
    op.drop_index("idx_jobs_status_next_attempt", table_name="jobs")
    op.drop_table("jobs")
