"""Files kept in the database, for hosts without a disk or object store (GC_BLOB_BACKEND=database).

Revision ID: 0011_database_blobs
Revises: 0010_terms_acceptance
Create Date: 2026-11-02
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0011_database_blobs"
down_revision = "0010_terms_acceptance"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "blobs",
        sa.Column("key", sa.String(80), primary_key=True), sa.Column("namespace", sa.String(32), nullable=False),
        sa.Column("size", sa.BigInteger, nullable=False), sa.Column("data", sa.LargeBinary, nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True)),
    )  # fmt: skip
    op.create_index("ix_blobs_namespace", "blobs", ["namespace"])


def downgrade() -> None:
    op.drop_index("ix_blobs_namespace", table_name="blobs")
    op.drop_table("blobs")
