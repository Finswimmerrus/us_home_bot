"""Initial tables

Revision ID: 0001_initial
Revises:
Create Date: 2026-09-17 00:00:00.000000

"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0001_initial"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS \"uuid-ossp\"")

    op.create_table(
        "users",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("telegram_id", sa.BigInteger(), unique=True, nullable=False, index=True),
        sa.Column("username", sa.String(255), nullable=True),
        sa.Column("first_name", sa.String(255), nullable=True),
        sa.Column("display_name", sa.String(255), nullable=True),
        sa.Column("timezone", sa.String(64), nullable=False, server_default="UTC"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
    )

    op.create_table(
        "couples",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("invite_code", sa.String(32), unique=True, nullable=True, index=True),
        sa.Column("invite_expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
    )

    op.create_table(
        "couple_members",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("couple_id", sa.Integer(), sa.ForeignKey("couples.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("joined_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("couple_id", "user_id", name="uq_couple_member"),
        sa.UniqueConstraint("user_id", name="uq_couple_member_user"),
    )

    op.execute(
        """
        CREATE OR REPLACE FUNCTION check_couple_member_limit()
        RETURNS TRIGGER AS $$
        BEGIN
            IF (SELECT COUNT(*) FROM couple_members WHERE couple_id = NEW.couple_id) >= 2 THEN
                RAISE EXCEPTION 'A couple can have at most 2 members';
            END IF;
            RETURN NEW;
        END;
        $$ LANGUAGE plpgsql;
        """
    )

    op.execute(
        """
        CREATE TRIGGER trg_couple_member_limit
        BEFORE INSERT OR UPDATE ON couple_members
        FOR EACH ROW EXECUTE FUNCTION check_couple_member_limit();
        """
    )

    op.create_table(
        "trips",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("couple_id", sa.Integer(), sa.ForeignKey("couples.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("start_date", sa.Date(), nullable=True, index=True),
        sa.Column("end_date", sa.Date(), nullable=True, index=True),
        sa.Column("created_by", sa.Integer(), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
        sa.CheckConstraint("name <> ''", name="ck_trip_name_nonempty"),
    )

    op.create_table(
        "tasks",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("couple_id", sa.Integer(), sa.ForeignKey("couples.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("created_by", sa.Integer(), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=False),
        sa.Column("assigned_to", sa.Integer(), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("assignment_type", sa.String(32), nullable=False, server_default="CREATOR"),
        sa.Column("title", sa.String(500), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("status", sa.String(32), nullable=False, server_default="TODO"),
        sa.Column("priority", sa.String(32), nullable=False, server_default="NORMAL"),
        sa.Column("due_at", sa.DateTime(timezone=True), nullable=True, index=True),
        sa.Column("completed_by", sa.Integer(), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("trip_id", sa.Integer(), sa.ForeignKey("trips.id", ondelete="SET NULL"), nullable=True, index=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
        sa.CheckConstraint("assignment_type IN ('CREATOR', 'PARTNER', 'BOTH')", name="ck_task_assignment_type"),
        sa.CheckConstraint("status IN ('TODO', 'IN_PROGRESS', 'DONE', 'CANCELLED')", name="ck_task_status"),
        sa.CheckConstraint("priority IN ('LOW', 'NORMAL', 'HIGH')", name="ck_task_priority"),
    )

    op.create_table(
        "movies",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("couple_id", sa.Integer(), sa.ForeignKey("couples.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("title", sa.String(500), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("type", sa.String(32), nullable=False, server_default="MOVIE"),
        sa.Column("status", sa.String(32), nullable=False, server_default="WANT_TO_WATCH"),
        sa.Column("added_by", sa.Integer(), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=False),
        sa.Column("watched_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
        sa.CheckConstraint("type IN ('MOVIE', 'SERIES')", name="ck_movie_type"),
        sa.CheckConstraint("status IN ('WANT_TO_WATCH', 'WATCHING', 'WATCHED')", name="ck_movie_status"),
    )

    op.create_table(
        "movie_ratings",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("movie_id", sa.Integer(), sa.ForeignKey("movies.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("couple_id", sa.Integer(), sa.ForeignKey("couples.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("rating", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
        sa.CheckConstraint("rating BETWEEN 1 AND 5", name="ck_movie_rating_range"),
        sa.UniqueConstraint("movie_id", "user_id", name="uq_movie_rating"),
    )

    op.create_table(
        "lists",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("couple_id", sa.Integer(), sa.ForeignKey("couples.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("created_by", sa.Integer(), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
        sa.CheckConstraint("name <> ''", name="ck_list_name_nonempty"),
        sa.UniqueConstraint("couple_id", "name", name="uq_list_couple_name"),
    )

    op.create_table(
        "list_items",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("list_id", sa.Integer(), nullable=False, index=True),
        sa.Column("couple_id", sa.Integer(), sa.ForeignKey("couples.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("title", sa.String(500), nullable=False),
        sa.Column("created_by", sa.Integer(), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=False),
        sa.Column("completed_by", sa.Integer(), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
        sa.CheckConstraint("title <> ''", name="ck_list_item_title_nonempty"),
        sa.ForeignKeyConstraint(
            ["list_id", "couple_id"],
            ["lists.id", "lists.couple_id"],
            name="fk_list_item_list_couple",
            ondelete="CASCADE",
        ),
    )

    op.create_table(
        "trip_places",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("trip_id", sa.Integer(), sa.ForeignKey("trips.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("couple_id", sa.Integer(), sa.ForeignKey("couples.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("name", sa.String(500), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("address", sa.String(1000), nullable=True),
        sa.Column("url", sa.String(2000), nullable=True),
        sa.Column("visit_date", sa.Date(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
        sa.CheckConstraint("name <> ''", name="ck_trip_place_name_nonempty"),
    )

    op.create_table(
        "wishlist_items",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("couple_id", sa.Integer(), sa.ForeignKey("couples.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("owner_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True),
        sa.Column("title", sa.String(500), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("url", sa.String(2000), nullable=True),
        sa.Column("price", sa.Numeric(10, 2), nullable=True),
        sa.Column("priority", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("status", sa.String(32), nullable=False, server_default="WANTED"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
        sa.CheckConstraint("title <> ''", name="ck_wishlist_title_nonempty"),
        sa.CheckConstraint("status IN ('WANTED', 'PURCHASED', 'ARCHIVED')", name="ck_wishlist_status"),
        sa.CheckConstraint(
            "(url LIKE 'http://%' OR url LIKE 'https://%' OR url IS NULL)",
            name="ck_wishlist_url_scheme",
        ),
        sa.CheckConstraint("priority >= 0", name="ck_wishlist_priority"),
    )

    op.create_table(
        "notes",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("couple_id", sa.Integer(), sa.ForeignKey("couples.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("trip_id", sa.Integer(), sa.ForeignKey("trips.id", ondelete="SET NULL"), nullable=True, index=True),
        sa.Column("title", sa.String(255), nullable=False),
        sa.Column("content", sa.Text(), nullable=True),
        sa.Column("created_by", sa.Integer(), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
        sa.CheckConstraint("title <> ''", name="ck_note_title_nonempty"),
        sa.Index("ix_note_title", "title"),
        sa.Index("ix_note_content", "content"),
    )


def downgrade() -> None:
    op.drop_table("notes")
    op.drop_table("wishlist_items")
    op.drop_table("trip_places")
    op.drop_table("tasks")
    op.drop_table("list_items")
    op.drop_table("lists")
    op.drop_table("movie_ratings")
    op.drop_table("movies")
    op.drop_table("trips")
    op.execute("DROP TRIGGER IF EXISTS trg_couple_member_limit ON couple_members")
    op.execute("DROP FUNCTION IF EXISTS check_couple_member_limit()")
    op.drop_table("couple_members")
    op.drop_table("couples")
    op.drop_table("users")
