"""soft void columns (sessions, evidence, review_log)

Revision ID: 0002
Revises: 0001
Create Date: 2026-10-07 21:45:00.000000

"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import mysql

# revision identifiers, used by Alembic.
revision: str = "0002"
down_revision: str | None = "0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    dt3 = sa.DateTime().with_variant(mysql.DATETIME(fsp=3), "mysql")
    op.add_column("sessions", sa.Column("voided_at", dt3, nullable=True))
    op.add_column("sessions", sa.Column("void_reason", sa.String(length=500), nullable=True))
    op.add_column("evidence", sa.Column("voided_at", dt3, nullable=True))
    op.add_column("evidence", sa.Column("void_reason", sa.String(length=500), nullable=True))
    op.add_column("review_log", sa.Column("voided_at", dt3, nullable=True))
    op.add_column("review_log", sa.Column("void_reason", sa.String(length=500), nullable=True))


def downgrade() -> None:
    op.drop_column("review_log", "void_reason")
    op.drop_column("review_log", "voided_at")
    op.drop_column("evidence", "void_reason")
    op.drop_column("evidence", "voided_at")
    op.drop_column("sessions", "void_reason")
    op.drop_column("sessions", "voided_at")
