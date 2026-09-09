"""index document evidence

Revision ID: 8c242f87bd4a
Revises: 30871e895922
Create Date: 2026-09-06 16:30:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "8c242f87bd4a"
down_revision: str | None = "30871e895922"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "call_document_chunks",
        sa.Column(
            "search_vector",
            postgresql.TSVECTOR(),
            sa.Computed("to_tsvector('simple', content)", persisted=True),
            nullable=False,
        ),
    )
    op.create_index(
        "ix_call_document_chunks_search_vector",
        "call_document_chunks",
        ["search_vector"],
        unique=False,
        postgresql_using="gin",
    )


def downgrade() -> None:
    op.drop_index(
        "ix_call_document_chunks_search_vector",
        table_name="call_document_chunks",
        postgresql_using="gin",
    )
    op.drop_column("call_document_chunks", "search_vector")
