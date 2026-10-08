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


def _sqlite() -> bool:
    return op.get_bind().dialect.name == "sqlite"


def _add_evidence_review_fk() -> None:
    # SQLite has no ALTER for foreign keys. Rebuild that table only there.
    # MySQL 8.0 adds the nullable column with ALGORITHM=INSTANT and the FK as a short index op.
    name = op.f("fk_evidence_review_id_review_log")
    if _sqlite():
        with op.batch_alter_table("evidence") as batch_op:
            batch_op.create_foreign_key(name, "review_log", ["review_id"], ["id"])
    else:
        op.create_foreign_key(name, "evidence", "review_log", ["review_id"], ["id"])


def _drop_evidence_review_fk() -> None:
    name = op.f("fk_evidence_review_id_review_log")
    if _sqlite():
        with op.batch_alter_table("evidence") as batch_op:
            batch_op.drop_constraint(name, type_="foreignkey")
    else:
        op.drop_constraint(name, "evidence", type_="foreignkey")


def upgrade() -> None:
    # Nullable columns with no default: MySQL 8.0 appends them with ALGORITHM=INSTANT
    # (metadata only, existing rows stay NULL = not voided). review_id is not backfilled.
    dt3 = sa.DateTime().with_variant(mysql.DATETIME(fsp=3), "mysql")
    op.add_column("sessions", sa.Column("voided_at", dt3, nullable=True))
    op.add_column("sessions", sa.Column("void_reason", sa.String(length=500), nullable=True))
    op.add_column("evidence", sa.Column("voided_at", dt3, nullable=True))
    op.add_column("evidence", sa.Column("void_reason", sa.String(length=500), nullable=True))
    op.add_column("review_log", sa.Column("voided_at", dt3, nullable=True))
    op.add_column("review_log", sa.Column("void_reason", sa.String(length=500), nullable=True))
    op.add_column("evidence", sa.Column("review_id", sa.BigInteger(), nullable=True))
    _add_evidence_review_fk()


def downgrade() -> None:
    _drop_evidence_review_fk()
    op.drop_column("evidence", "review_id")
    op.drop_column("review_log", "void_reason")
    op.drop_column("review_log", "voided_at")
    op.drop_column("evidence", "void_reason")
    op.drop_column("evidence", "voided_at")
    op.drop_column("sessions", "void_reason")
    op.drop_column("sessions", "voided_at")
