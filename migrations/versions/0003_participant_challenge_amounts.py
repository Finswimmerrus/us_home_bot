"""Add participant challenge amounts

Revision ID: 0003_participant_challenge_amounts
Revises: 0002_challenges
Create Date: 2026-09-20 00:00:00.000000

"""

import sqlalchemy as sa
from alembic import op

revision = "0003_participant_challenge_amounts"
down_revision = "0002_challenges"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("challenge_participants") as batch_op:
        batch_op.add_column(sa.Column("daily_amount", sa.Numeric(12, 2), nullable=True))
        batch_op.create_check_constraint(
            "ck_challenge_participant_daily_amount",
            "daily_amount IS NULL OR daily_amount >= 0",
        )
    op.execute(
        """
        UPDATE challenge_participants
        SET daily_amount = (
            SELECT challenges.daily_amount
            FROM challenges
            WHERE challenges.id = challenge_participants.challenge_id
              AND challenges.challenge_type = 'SAVINGS'
        )
        WHERE EXISTS (
            SELECT 1
            FROM challenges
            WHERE challenges.id = challenge_participants.challenge_id
              AND challenges.challenge_type = 'SAVINGS'
              AND challenges.daily_amount IS NOT NULL
        )
        """
    )


def downgrade() -> None:
    with op.batch_alter_table("challenge_participants") as batch_op:
        batch_op.drop_constraint(
            "ck_challenge_participant_daily_amount",
            type_="check",
        )
        batch_op.drop_column("daily_amount")
