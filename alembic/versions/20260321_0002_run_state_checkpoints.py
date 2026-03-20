"""add run state checkpoints

Revision ID: 20260321_0002
Revises: 20260321_0001
Create Date: 2026-03-21 20:15:00
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "20260321_0002"
down_revision = "20260321_0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "run_state", sa.Column("last_checkpoint_at", sa.DateTime(timezone=True), nullable=True)
    )


def downgrade() -> None:
    op.drop_column("run_state", "last_checkpoint_at")
