# Lantern House core instruction: stay fail-safe, never leak debug or
# error text into the live chat, log recovered failures to
# logs/error.txt with context, and preserve hot-patch compatibility
# for uninterrupted long-running operation.
"""add house state and strategic brief tables

Revision ID: 20260321_0004
Revises: 20260321_0003
Create Date: 2026-03-21 23:10:00
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "20260321_0004"
down_revision = "20260321_0003"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "house_state",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("state_key", sa.String(length=50), nullable=False),
        sa.Column("capacity", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("occupied_rooms", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("vacancy_pressure", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("cash_on_hand", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("hourly_burn_rate", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("payroll_due_in_hours", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("repair_backlog", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("inspection_risk", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("guest_tension", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("weather_pressure", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("staff_fatigue", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("reputation_risk", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("active_pressures", sa.JSON(), nullable=False),
        sa.Column("metadata", sa.JSON(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("state_key"),
    )

    op.create_table(
        "strategic_briefs",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("source", sa.String(length=50), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("model_name", sa.String(length=80), nullable=True),
        sa.Column("title", sa.String(length=200), nullable=False),
        sa.Column("viewer_value_thesis", sa.Text(), nullable=False),
        sa.Column("urgency", sa.Integer(), nullable=False, server_default="5"),
        sa.Column("next_hour_focus", sa.JSON(), nullable=False),
        sa.Column("next_six_hours", sa.JSON(), nullable=False),
        sa.Column("recommendations", sa.JSON(), nullable=False),
        sa.Column("risk_alerts", sa.JSON(), nullable=False),
        sa.Column("house_pressure_actions", sa.JSON(), nullable=False),
        sa.Column("audience_rollout_actions", sa.JSON(), nullable=False),
        sa.Column("manager_biases", sa.JSON(), nullable=False),
        sa.Column("simulation_ranking", sa.JSON(), nullable=False),
        sa.Column("metadata", sa.JSON(), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )


def downgrade() -> None:
    op.drop_table("strategic_briefs")
    op.drop_table("house_state")
