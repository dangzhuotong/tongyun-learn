from datetime import date, datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import (
    JSON,
    BigInteger,
    Boolean,
    CheckConstraint,
    Date,
    DateTime,
    Enum,
    Float,
    ForeignKey,
    Index,
    Integer,
    MetaData,
    Numeric,
    SmallInteger,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects import mysql
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

from tongyun_learn.db import utcnow

convention = {
    "ix": "ix_%(column_0_label)s",
    "uq": "uq_%(table_name)s_%(column_0_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}

metadata = MetaData(naming_convention=convention)


class Base(DeclarativeBase):
    metadata = metadata


MYSQL_TABLE_ARGS = {
    "mysql_engine": "InnoDB",
    "mysql_charset": "utf8mb4",
    "mysql_collate": "utf8mb4_0900_ai_ci",
}

DT3 = DateTime().with_variant(mysql.DATETIME(fsp=3), "mysql")
BIGINT_AI = BigInteger().with_variant(Integer, "sqlite")
TINYINT = SmallInteger().with_variant(mysql.TINYINT(), "mysql")
DOUBLE = Float().with_variant(mysql.DOUBLE(asdecimal=False), "mysql")  # 返回 float，别给 FSRS 传 Decimal
CHAR64 = String(64).with_variant(mysql.CHAR(64), "mysql")
MEDIUMTEXT = Text().with_variant(mysql.MEDIUMTEXT(), "mysql")

POINT_STATES = ("locked", "available", "learning", "learned", "mastered", "rusty")


class Subject(Base):
    __tablename__ = "subjects"
    __table_args__ = (MYSQL_TABLE_ARGS,)

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    prefix: Mapped[str] = mapped_column(String(16), nullable=False, unique=True)
    title: Mapped[str | None] = mapped_column(String(128), nullable=True)
    goal: Mapped[str | None] = mapped_column(Text, nullable=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    axue_area: Mapped[str | None] = mapped_column(String(32), nullable=True)
    map_version: Mapped[str | None] = mapped_column(String(32), nullable=True)
    active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DT3, default=utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DT3, default=utcnow, onupdate=utcnow, nullable=False)


class Stage(Base):
    __tablename__ = "stages"
    __table_args__ = (
        Index("ix_stages_subject_id_ord", "subject_id", "ord"),
        MYSQL_TABLE_ARGS,
    )

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    subject_id: Mapped[str] = mapped_column(String(64), ForeignKey("subjects.id"), nullable=False)
    ord: Mapped[int | None] = mapped_column(SmallInteger, nullable=True)
    title: Mapped[str | None] = mapped_column(String(255), nullable=True)
    weeks: Mapped[str | None] = mapped_column(String(16), nullable=True)
    goal: Mapped[str | None] = mapped_column(Text, nullable=True)
    deliverable: Mapped[str | None] = mapped_column(Text, nullable=True)
    exit_criteria: Mapped[str | None] = mapped_column(Text, nullable=True)
    active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DT3, default=utcnow, onupdate=utcnow, nullable=False)


class Point(Base):
    __tablename__ = "points"
    __table_args__ = (
        Index("ix_points_subject_id_active_stage_id_ord", "subject_id", "active", "stage_id", "ord"),
        MYSQL_TABLE_ARGS,
    )

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    subject_id: Mapped[str] = mapped_column(String(64), ForeignKey("subjects.id"), nullable=False)
    stage_id: Mapped[str] = mapped_column(String(64), ForeignKey("stages.id"), nullable=False)
    ord: Mapped[int | None] = mapped_column(SmallInteger, nullable=True)
    title: Mapped[str | None] = mapped_column(String(255), nullable=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    card_types: Mapped[Any | None] = mapped_column(JSON, nullable=True)
    effort_hours: Mapped[Decimal | None] = mapped_column(Numeric(4, 1), nullable=True)
    interview_weight: Mapped[int | None] = mapped_column(TINYINT, nullable=True)
    mastery_evidence: Mapped[Any | None] = mapped_column(JSON, nullable=True)
    tags: Mapped[Any | None] = mapped_column(JSON, nullable=True)
    sources: Mapped[Any | None] = mapped_column(JSON, nullable=True)
    example_cards: Mapped[Any | None] = mapped_column(JSON, nullable=True)
    active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    deactivated_at: Mapped[datetime | None] = mapped_column(DT3, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DT3, default=utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DT3, default=utcnow, onupdate=utcnow, nullable=False)


class PointPrereq(Base):
    __tablename__ = "point_prereqs"
    __table_args__ = (
        Index("ix_point_prereqs_prereq_id_kind", "prereq_id", "kind"),
        MYSQL_TABLE_ARGS,
    )

    point_id: Mapped[str] = mapped_column(String(64), ForeignKey("points.id"), primary_key=True)
    prereq_id: Mapped[str] = mapped_column(String(64), ForeignKey("points.id"), primary_key=True)
    kind: Mapped[str] = mapped_column(
        Enum("hard", "soft", native_enum=True, create_constraint=False, name="point_prereqs_kind"),
        nullable=False,
    )


class Deck(Base):
    __tablename__ = "decks"
    __table_args__ = (
        UniqueConstraint("subject_id", "kind", "name", name="uq_decks_subject_id_kind_name"),
        MYSQL_TABLE_ARGS,
    )

    id: Mapped[int] = mapped_column(BIGINT_AI, primary_key=True, autoincrement=True)
    subject_id: Mapped[str | None] = mapped_column(String(64), ForeignKey("subjects.id"), nullable=True)
    kind: Mapped[str | None] = mapped_column(String(16), nullable=True)
    name: Mapped[str | None] = mapped_column(String(128), nullable=True)
    source: Mapped[str | None] = mapped_column(
        Enum("builtin", "ai", "agent", "map", native_enum=True, create_constraint=False, name="decks_source"),
        nullable=True,
    )
    review_cap: Mapped[int | None] = mapped_column(SmallInteger, nullable=True)
    new_cap: Mapped[int | None] = mapped_column(SmallInteger, nullable=True)
    new_cap_deep: Mapped[int | None] = mapped_column(SmallInteger, nullable=True)
    meta: Mapped[Any | None] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DT3, default=utcnow, nullable=False)


class Card(Base):
    __tablename__ = "cards"
    __table_args__ = (
        UniqueConstraint("deck_id", "front_key", name="uq_cards_deck_id_front_key"),
        Index("ix_cards_point_id_active", "point_id", "active"),
        Index("ix_cards_deck_id_active", "deck_id", "active"),
        MYSQL_TABLE_ARGS,
    )

    id: Mapped[int] = mapped_column(BIGINT_AI, primary_key=True, autoincrement=True)
    deck_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("decks.id"), nullable=False)
    point_id: Mapped[str | None] = mapped_column(String(64), ForeignKey("points.id"), nullable=True)
    card_type: Mapped[str | None] = mapped_column(
        Enum(
            "memory",
            "understand",
            "handson",
            "express",
            native_enum=True,
            create_constraint=False,
            name="cards_card_type",
        ),
        nullable=True,
    )
    front: Mapped[str | None] = mapped_column(Text, nullable=True)
    front_key: Mapped[str | None] = mapped_column(CHAR64, nullable=True)
    back: Mapped[str | None] = mapped_column(MEDIUMTEXT, nullable=True)
    payload: Mapped[Any | None] = mapped_column(JSON, nullable=True)
    tags: Mapped[Any | None] = mapped_column(JSON, nullable=True)
    created_by: Mapped[str | None] = mapped_column(
        Enum(
            "web",
            "axue",
            "ai",
            "example",
            "migrate",
            native_enum=True,
            create_constraint=False,
            name="cards_created_by",
        ),
        nullable=True,
    )
    active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DT3, default=utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DT3, default=utcnow, onupdate=utcnow, nullable=False)


class CardState(Base):
    __tablename__ = "card_state"
    __table_args__ = (
        Index("ix_card_state_due", "due"),
        Index("ix_card_state_state", "state"),
        Index("ix_card_state_first_review", "first_review"),
        MYSQL_TABLE_ARGS,
    )

    card_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("cards.id"), primary_key=True)
    state: Mapped[int | None] = mapped_column(TINYINT, nullable=True)
    step: Mapped[int | None] = mapped_column(TINYINT, nullable=True)
    due: Mapped[datetime | None] = mapped_column(DT3, nullable=True)
    stability: Mapped[float | None] = mapped_column(DOUBLE, nullable=True)
    difficulty: Mapped[float | None] = mapped_column(DOUBLE, nullable=True)
    reps: Mapped[int | None] = mapped_column(Integer, nullable=True)
    lapses: Mapped[int | None] = mapped_column(Integer, nullable=True)
    first_review: Mapped[datetime | None] = mapped_column(DT3, nullable=True)
    last_review: Mapped[datetime | None] = mapped_column(DT3, nullable=True)
    last_rating: Mapped[int | None] = mapped_column(TINYINT, nullable=True)


class ReviewLog(Base):
    __tablename__ = "review_log"
    __table_args__ = (
        Index("ix_review_log_point_id_reviewed_at", "point_id", "reviewed_at"),
        Index("ix_review_log_card_id_reviewed_at", "card_id", "reviewed_at"),
        Index("ix_review_log_reviewed_at", "reviewed_at"),
        MYSQL_TABLE_ARGS,
    )

    id: Mapped[int] = mapped_column(BIGINT_AI, primary_key=True, autoincrement=True)
    card_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("cards.id"), nullable=False)
    point_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    rating: Mapped[int] = mapped_column(TINYINT, nullable=False)
    reviewer: Mapped[str] = mapped_column(
        Enum("self", "axue", native_enum=True, create_constraint=False, name="review_log_reviewer"),
        nullable=False,
    )
    client: Mapped[str | None] = mapped_column(String(16), nullable=True)
    answer_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    duration_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    errors: Mapped[int | None] = mapped_column(SmallInteger, nullable=True)
    reviewed_at: Mapped[datetime] = mapped_column(DT3, nullable=False)
    applied: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    stability_after: Mapped[float | None] = mapped_column(DOUBLE, nullable=True)
    due_after: Mapped[datetime | None] = mapped_column(DT3, nullable=True)
    client_review_id: Mapped[str | None] = mapped_column(String(64), nullable=True, unique=True)
    voided_at: Mapped[datetime | None] = mapped_column(DT3, nullable=True)
    void_reason: Mapped[str | None] = mapped_column(String(500), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DT3, default=utcnow, nullable=False)


class StudySession(Base):
    __tablename__ = "sessions"
    __table_args__ = (
        Index("ix_sessions_date", "date"),
        MYSQL_TABLE_ARGS,
    )

    id: Mapped[int] = mapped_column(BIGINT_AI, primary_key=True, autoincrement=True)
    subject_id: Mapped[str | None] = mapped_column(String(64), ForeignKey("subjects.id"), nullable=True)
    date: Mapped[date] = mapped_column(Date, nullable=False)
    minutes: Mapped[int | None] = mapped_column(SmallInteger, nullable=True)
    lesson_ref: Mapped[str | None] = mapped_column(String(64), nullable=True)
    cues: Mapped[Any | None] = mapped_column(JSON, nullable=True)
    summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    stuck: Mapped[str | None] = mapped_column(Text, nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    source: Mapped[str | None] = mapped_column(
        Enum("axue", "migrate", native_enum=True, create_constraint=False, name="sessions_source"),
        nullable=True,
    )
    legacy_ref: Mapped[str | None] = mapped_column(String(64), nullable=True, unique=True)
    voided_at: Mapped[datetime | None] = mapped_column(DT3, nullable=True)
    void_reason: Mapped[str | None] = mapped_column(String(500), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DT3, default=utcnow, nullable=False)


class SessionPoint(Base):
    __tablename__ = "session_points"
    __table_args__ = (
        Index("ix_session_points_point_id", "point_id"),
        MYSQL_TABLE_ARGS,
    )

    session_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("sessions.id"), primary_key=True)
    point_id: Mapped[str] = mapped_column(String(64), ForeignKey("points.id"), primary_key=True)


class Evidence(Base):
    __tablename__ = "evidence"
    __table_args__ = (
        CheckConstraint("point_id IS NOT NULL OR stage_id IS NOT NULL", name="evidence_point_or_stage"),
        Index("ix_evidence_point_id_type_observed_at", "point_id", "type", "observed_at"),
        Index("ix_evidence_stage_id", "stage_id"),
        MYSQL_TABLE_ARGS,
    )

    id: Mapped[int] = mapped_column(BIGINT_AI, primary_key=True, autoincrement=True)
    point_id: Mapped[str | None] = mapped_column(String(64), ForeignKey("points.id"), nullable=True)
    stage_id: Mapped[str | None] = mapped_column(String(64), ForeignKey("stages.id"), nullable=True)
    session_id: Mapped[int | None] = mapped_column(BigInteger, ForeignKey("sessions.id"), nullable=True)
    card_id: Mapped[int | None] = mapped_column(BigInteger, ForeignKey("cards.id"), nullable=True)
    # 带 card_id 记证据时同时写的那条复习；作废/恢复证据时一起作废/恢复并重放 FSRS
    review_id: Mapped[int | None] = mapped_column(BigInteger, ForeignKey("review_log.id"), nullable=True)
    type: Mapped[str] = mapped_column(
        Enum(
            "selftest",
            "feynman",
            "express",
            "handson",
            native_enum=True,
            create_constraint=False,
            name="evidence_type",
        ),
        nullable=False,
    )
    score: Mapped[Decimal | None] = mapped_column(Numeric(5, 2), nullable=True)
    max_score: Mapped[Decimal | None] = mapped_column(Numeric(5, 2), nullable=True)
    passed: Mapped[bool] = mapped_column(Boolean, nullable=False)
    rubric: Mapped[Any | None] = mapped_column(JSON, nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    reviewer: Mapped[str | None] = mapped_column(
        Enum("axue", "migrate", native_enum=True, create_constraint=False, name="evidence_reviewer"),
        nullable=True,
    )
    observed_at: Mapped[datetime | None] = mapped_column(DT3, nullable=True)
    legacy_ref: Mapped[str | None] = mapped_column(String(64), nullable=True, unique=True)
    voided_at: Mapped[datetime | None] = mapped_column(DT3, nullable=True)
    void_reason: Mapped[str | None] = mapped_column(String(500), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DT3, default=utcnow, nullable=False)


class Blocker(Base):
    __tablename__ = "blockers"
    __table_args__ = (
        Index("ix_blockers_status_point_id", "status", "point_id"),
        MYSQL_TABLE_ARGS,
    )

    id: Mapped[int] = mapped_column(BIGINT_AI, primary_key=True, autoincrement=True)
    point_id: Mapped[str | None] = mapped_column(String(64), ForeignKey("points.id"), nullable=True)
    session_id: Mapped[int | None] = mapped_column(BigInteger, ForeignKey("sessions.id"), nullable=True)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    detail: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(
        Enum("open", "resolved", "dropped", native_enum=True, create_constraint=False, name="blockers_status"),
        default="open",
        nullable=False,
    )
    resolution: Mapped[str | None] = mapped_column(Text, nullable=True)
    legacy_ref: Mapped[str | None] = mapped_column(String(64), nullable=True, unique=True)
    created_at: Mapped[datetime] = mapped_column(DT3, default=utcnow, nullable=False)
    resolved_at: Mapped[datetime | None] = mapped_column(DT3, nullable=True)


class PointState(Base):
    __tablename__ = "point_state"
    __table_args__ = (
        Index("ix_point_state_state", "state"),
        MYSQL_TABLE_ARGS,
    )

    point_id: Mapped[str] = mapped_column(String(64), ForeignKey("points.id"), primary_key=True)
    state: Mapped[str] = mapped_column(
        Enum(*POINT_STATES, native_enum=True, create_constraint=False, name="point_state_state"),
        nullable=False,
    )
    since: Mapped[datetime] = mapped_column(DT3, default=utcnow, nullable=False)
    learned_at: Mapped[datetime | None] = mapped_column(DT3, nullable=True)
    ever_mastered: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    needs_recheck: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    override_state: Mapped[str | None] = mapped_column(
        Enum(*POINT_STATES, native_enum=True, create_constraint=False, name="point_state_override_state"),
        nullable=True,
    )
    override_reason: Mapped[str | None] = mapped_column(String(500), nullable=True)
    stats: Mapped[Any | None] = mapped_column(JSON, nullable=True)
    computed_at: Mapped[datetime] = mapped_column(DT3, default=utcnow, onupdate=utcnow, nullable=False)


class PointStateLog(Base):
    __tablename__ = "point_state_log"
    __table_args__ = (
        Index("ix_point_state_log_point_id_created_at", "point_id", "created_at"),
        Index("ix_point_state_log_created_at", "created_at"),
        MYSQL_TABLE_ARGS,
    )

    id: Mapped[int] = mapped_column(BIGINT_AI, primary_key=True, autoincrement=True)
    point_id: Mapped[str] = mapped_column(String(64), ForeignKey("points.id"), nullable=False)
    from_state: Mapped[str | None] = mapped_column(
        Enum(*POINT_STATES, native_enum=True, create_constraint=False, name="point_state_log_from_state"),
        nullable=True,
    )
    to_state: Mapped[str] = mapped_column(
        Enum(*POINT_STATES, native_enum=True, create_constraint=False, name="point_state_log_to_state"),
        nullable=False,
    )
    cause: Mapped[str | None] = mapped_column(String(32), nullable=True)
    cause_ref: Mapped[str | None] = mapped_column(String(64), nullable=True)
    note: Mapped[str | None] = mapped_column(String(500), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DT3, default=utcnow, nullable=False)


class AiCache(Base):
    __tablename__ = "ai_cache"
    __table_args__ = (
        Index("ix_ai_cache_kind", "kind"),
        MYSQL_TABLE_ARGS,
    )

    cache_key: Mapped[str] = mapped_column(CHAR64, primary_key=True)
    kind: Mapped[str] = mapped_column(String(32), nullable=False)
    model: Mapped[str] = mapped_column(String(64), nullable=False)
    prompt_ver: Mapped[str] = mapped_column(String(16), nullable=False)
    content: Mapped[Any] = mapped_column(JSON, nullable=False)
    tokens_in: Mapped[int | None] = mapped_column(Integer, nullable=True)
    tokens_out: Mapped[int | None] = mapped_column(Integer, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DT3, default=utcnow, nullable=False)


class ApiUsage(Base):
    __tablename__ = "api_usage"
    __table_args__ = (MYSQL_TABLE_ARGS,)

    token_name: Mapped[str] = mapped_column(String(16), primary_key=True)
    day: Mapped[date] = mapped_column(Date, primary_key=True)
    ai_calls: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    requests: Mapped[int] = mapped_column(Integer, default=0, nullable=False)


class MapImport(Base):
    __tablename__ = "map_imports"
    __table_args__ = (MYSQL_TABLE_ARGS,)

    id: Mapped[int] = mapped_column(BIGINT_AI, primary_key=True, autoincrement=True)
    subject_id: Mapped[str] = mapped_column(String(64), ForeignKey("subjects.id"), nullable=False)
    map_version: Mapped[str | None] = mapped_column(String(32), nullable=True)
    file_sha256: Mapped[str | None] = mapped_column(CHAR64, nullable=True)
    dry_run: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    diff: Mapped[Any | None] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DT3, default=utcnow, nullable=False)
