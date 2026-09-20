"""Add challenges

Revision ID: 0002_challenges
Revises: 0001_initial
Create Date: 2026-09-20 00:00:00.000000

"""

import sqlalchemy as sa
from alembic import op

revision = "0002_challenges"
down_revision = "0001_initial"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "challenges",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("couple_id", sa.Integer(), sa.ForeignKey("couples.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("created_by", sa.Integer(), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=False, index=True),
        sa.Column("title", sa.String(500), nullable=False),
        sa.Column("scope", sa.String(32), nullable=False),
        sa.Column("challenge_type", sa.String(32), nullable=False),
        sa.Column("start_date", sa.Date(), nullable=False, index=True),
        sa.Column("end_date", sa.Date(), nullable=False, index=True),
        sa.Column("daily_amount", sa.Numeric(12, 2), nullable=True),
        sa.Column("currency", sa.String(3), nullable=False, server_default="RUB"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
        sa.CheckConstraint("title <> ''", name="ck_challenge_title_nonempty"),
        sa.CheckConstraint("scope IN ('PERSONAL', 'COUPLE')", name="ck_challenge_scope"),
        sa.CheckConstraint("challenge_type IN ('SIMPLE', 'SAVINGS')", name="ck_challenge_type"),
        sa.CheckConstraint("end_date >= start_date", name="ck_challenge_period"),
        sa.CheckConstraint(
            "(challenge_type = 'SAVINGS' AND daily_amount IS NOT NULL AND daily_amount >= 0) "
            "OR (challenge_type = 'SIMPLE' AND daily_amount IS NULL)",
            name="ck_challenge_daily_amount",
        ),
    )
    op.create_table(
        "challenge_participants",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("challenge_id", sa.Integer(), sa.ForeignKey("challenges.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.UniqueConstraint("challenge_id", "user_id", name="uq_challenge_participant"),
    )
    op.create_table(
        "challenge_entries",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("challenge_id", sa.Integer(), sa.ForeignKey("challenges.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("entry_date", sa.Date(), nullable=False, index=True),
        sa.Column("status", sa.String(32), nullable=False),
        sa.Column("spent_amount", sa.Numeric(12, 2), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
        sa.CheckConstraint("status IN ('SUCCESS', 'MISSED')", name="ck_challenge_entry_status"),
        sa.CheckConstraint("spent_amount IS NULL OR spent_amount >= 0", name="ck_challenge_spent"),
        sa.UniqueConstraint("challenge_id", "user_id", "entry_date", name="uq_challenge_entry_day"),
    )


def downgrade() -> None:
    op.drop_table("challenge_entries")
    op.drop_table("challenge_participants")
    op.drop_table("challenges")
