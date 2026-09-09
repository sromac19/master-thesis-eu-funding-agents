"""Create funding calls table.

Revision ID: 20260905_01
Revises:
Create Date: 2026-09-05
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "20260905_01"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


funding_call_status = postgresql.ENUM(
    "open",
    "forthcoming",
    "closed",
    "unknown",
    name="funding_call_status",
    create_type=False,
)


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")
    funding_call_status.create(op.get_bind(), checkfirst=True)
    op.create_table(
        "funding_calls",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("source_call_id", sa.String(length=255), nullable=False),
        sa.Column("programme", sa.String(length=255), nullable=False),
        sa.Column("title", sa.String(length=1000), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("status", funding_call_status, nullable=False),
        sa.Column("opening_date", sa.Date(), nullable=True),
        sa.Column("deadline", sa.Date(), nullable=True),
        sa.Column("budget_eur", sa.Numeric(precision=18, scale=2), nullable=True),
        sa.Column("official_url", sa.String(length=2048), nullable=False),
        sa.Column("source", sa.String(length=100), nullable=False),
        sa.Column("fetched_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("document_checksum", sa.String(length=64), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "source",
            "source_call_id",
            "fetched_at",
            name="uq_funding_calls_source_snapshot",
        ),
    )


def downgrade() -> None:
    op.drop_table("funding_calls")
