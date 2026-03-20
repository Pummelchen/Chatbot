"""add character cultural context fields

Revision ID: 20260321_0003
Revises: 20260321_0002
Create Date: 2026-03-21 21:10:00
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "20260321_0003"
down_revision = "20260321_0002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "characters",
        sa.Column("cultural_background", sa.String(length=120), nullable=True),
    )
    op.add_column("characters", sa.Column("family_expectations", sa.Text(), nullable=True))
    op.add_column("characters", sa.Column("conflict_style", sa.Text(), nullable=True))
    op.add_column("characters", sa.Column("privacy_boundaries", sa.Text(), nullable=True))
    op.add_column("characters", sa.Column("value_instincts", sa.Text(), nullable=True))
    op.add_column("characters", sa.Column("emotional_expression", sa.Text(), nullable=True))

    op.execute(
        """
        UPDATE characters
        SET
            cultural_background = 'unspecified',
            family_expectations = 'Context not backfilled; reseed the story bible.',
            conflict_style = 'Context not backfilled; reseed the story bible.',
            privacy_boundaries = 'Context not backfilled; reseed the story bible.',
            value_instincts = 'Context not backfilled; reseed the story bible.',
            emotional_expression = 'Context not backfilled; reseed the story bible.'
        """
    )

    op.alter_column("characters", "cultural_background", existing_type=sa.String(length=120), nullable=False)
    op.alter_column("characters", "family_expectations", existing_type=sa.Text(), nullable=False)
    op.alter_column("characters", "conflict_style", existing_type=sa.Text(), nullable=False)
    op.alter_column("characters", "privacy_boundaries", existing_type=sa.Text(), nullable=False)
    op.alter_column("characters", "value_instincts", existing_type=sa.Text(), nullable=False)
    op.alter_column("characters", "emotional_expression", existing_type=sa.Text(), nullable=False)


def downgrade() -> None:
    op.drop_column("characters", "emotional_expression")
    op.drop_column("characters", "value_instincts")
    op.drop_column("characters", "privacy_boundaries")
    op.drop_column("characters", "conflict_style")
    op.drop_column("characters", "family_expectations")
    op.drop_column("characters", "cultural_background")
