"""API tokens can be read-only.

Revision ID: 0013_token_scope
Revises: 0012_workspace_invitations
Create Date: 2026-11-05
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0013_token_scope"
down_revision = "0012_workspace_invitations"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("auth_sessions", sa.Column("scope", sa.String(10), nullable=False, server_default="full"))


def downgrade() -> None:
    with op.batch_alter_table("auth_sessions") as b:
        b.drop_column("scope")
