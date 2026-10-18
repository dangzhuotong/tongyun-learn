"""云芽英语：units / unit_words / type_events / coach_plans

Revision ID: 0003
Revises: 0002
Create Date: 2026-10-17 06:10:38.595524

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import mysql

revision: str = "0003"
down_revision: str | None = "0002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "coach_plans",
        sa.Column("id", sa.BigInteger().with_variant(sa.Integer(), "sqlite"), autoincrement=True, nullable=False),
        sa.Column("user_name", sa.String(length=16), nullable=False),
        sa.Column("created_at", sa.DateTime().with_variant(mysql.DATETIME(fsp=3), "mysql"), nullable=False),
        sa.Column("summary", sa.Text(), nullable=False),
        sa.Column("queue_json", sa.JSON(), nullable=False),
        sa.Column("until", sa.DateTime().with_variant(mysql.DATETIME(fsp=3), "mysql"), nullable=False),
        sa.Column("source", sa.String(length=16), nullable=False),
        sa.Column("weak_json", sa.JSON(), nullable=True),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_coach_plans")),
        mysql_charset="utf8mb4",
        mysql_collate="utf8mb4_0900_ai_ci",
        mysql_engine="InnoDB",
    )
    with op.batch_alter_table("coach_plans", schema=None) as batch_op:
        batch_op.create_index("ix_coach_plans_user_name_created_at", ["user_name", "created_at"], unique=False)

    op.create_table(
        "units",
        sa.Column("id", sa.BigInteger().with_variant(sa.Integer(), "sqlite"), autoincrement=True, nullable=False),
        sa.Column("track", sa.String(length=32), nullable=False),
        sa.Column("ord", sa.SmallInteger(), nullable=False),
        sa.Column("title", sa.String(length=255), nullable=False),
        sa.Column("kind", sa.String(length=16), nullable=False),
        sa.Column("graduate_rule_json", sa.JSON(), nullable=True),
        sa.Column("active", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime().with_variant(mysql.DATETIME(fsp=3), "mysql"), nullable=False),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_units")),
        sa.UniqueConstraint("track", "ord", name="uq_units_track_ord"),
        mysql_charset="utf8mb4",
        mysql_collate="utf8mb4_0900_ai_ci",
        mysql_engine="InnoDB",
    )
    with op.batch_alter_table("units", schema=None) as batch_op:
        batch_op.create_index("ix_units_track_ord", ["track", "ord"], unique=False)

    op.create_table(
        "unit_words",
        sa.Column("unit_id", sa.BigInteger(), nullable=False),
        sa.Column("card_id", sa.BigInteger(), nullable=False),
        sa.Column("ord", sa.SmallInteger(), nullable=False),
        sa.ForeignKeyConstraint(["card_id"], ["cards.id"], name=op.f("fk_unit_words_card_id_cards")),
        sa.ForeignKeyConstraint(["unit_id"], ["units.id"], name=op.f("fk_unit_words_unit_id_units")),
        sa.PrimaryKeyConstraint("unit_id", "card_id", name=op.f("pk_unit_words")),
        sa.UniqueConstraint("unit_id", "ord", name="uq_unit_words_unit_id_ord"),
        mysql_charset="utf8mb4",
        mysql_collate="utf8mb4_0900_ai_ci",
        mysql_engine="InnoDB",
    )
    with op.batch_alter_table("unit_words", schema=None) as batch_op:
        batch_op.create_index("ix_unit_words_card_id", ["card_id"], unique=False)

    op.create_table(
        "type_events",
        sa.Column("id", sa.BigInteger().with_variant(sa.Integer(), "sqlite"), autoincrement=True, nullable=False),
        sa.Column("card_id", sa.BigInteger(), nullable=False),
        sa.Column("unit_id", sa.BigInteger(), nullable=True),
        sa.Column("user_name", sa.String(length=16), nullable=False),
        sa.Column("phase", sa.String(length=1), nullable=False),
        sa.Column("correct", sa.Boolean(), nullable=False),
        sa.Column("typed", sa.Text(), nullable=False),
        sa.Column("expected", sa.Text(), nullable=True),
        sa.Column("duration_ms", sa.Integer(), nullable=True),
        sa.Column("error_shape", sa.String(length=32), nullable=True),
        sa.Column("sentence_index", sa.SmallInteger(), nullable=True),
        sa.Column("client_event_id", sa.String(length=64), nullable=True),
        sa.Column("review_id", sa.BigInteger(), nullable=True),
        sa.Column("created_at", sa.DateTime().with_variant(mysql.DATETIME(fsp=3), "mysql"), nullable=False),
        sa.CheckConstraint("phase IN ('A', 'B')", name=op.f("ck_type_events_phase_ab")),
        sa.ForeignKeyConstraint(["card_id"], ["cards.id"], name=op.f("fk_type_events_card_id_cards")),
        sa.ForeignKeyConstraint(["review_id"], ["review_log.id"], name=op.f("fk_type_events_review_id_review_log")),
        sa.ForeignKeyConstraint(["unit_id"], ["units.id"], name=op.f("fk_type_events_unit_id_units")),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_type_events")),
        sa.UniqueConstraint("client_event_id", name=op.f("uq_type_events_client_event_id")),
        mysql_charset="utf8mb4",
        mysql_collate="utf8mb4_0900_ai_ci",
        mysql_engine="InnoDB",
    )
    with op.batch_alter_table("type_events", schema=None) as batch_op:
        batch_op.create_index("ix_type_events_card_id_created_at", ["card_id", "created_at"], unique=False)
        batch_op.create_index("ix_type_events_user_name_created_at", ["user_name", "created_at"], unique=False)


def downgrade() -> None:
    # 只删表。MySQL 上先删索引会撞上外键所用的索引；删表时索引一起走。
    op.drop_table("type_events")
    op.drop_table("unit_words")
    op.drop_table("units")
    op.drop_table("coach_plans")
