"""Invitations: joining a team workspace now needs the invited person's consent.

Revision ID: 0012_workspace_invitations
Revises: 0011_database_blobs
Create Date: 2026-11-05
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0012_workspace_invitations"
down_revision = "0011_database_blobs"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "workspace_invitations",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("workspace_id", sa.Integer, sa.ForeignKey("workspaces.id"), nullable=False),
        sa.Column("email", sa.String(320), nullable=False), sa.Column("role", sa.String(20), nullable=False),
        sa.Column("invited_by", sa.Integer, nullable=True), sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("workspace_id", "email", name="uq_invitation"),
    )  # fmt: skip
    op.create_index("ix_workspace_invitations_workspace_id", "workspace_invitations", ["workspace_id"])
    op.create_index("ix_workspace_invitations_email", "workspace_invitations", ["email"])


def downgrade() -> None:
    op.drop_table("workspace_invitations")
