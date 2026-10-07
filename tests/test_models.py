from datetime import date

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import exc, inspect
from sqlalchemy.orm import Session

from tongyun_learn.db import get_engine
from tongyun_learn.models import AiCache, ApiUsage, Evidence

EXPECTED_TABLES = {
    "subjects",
    "stages",
    "points",
    "point_prereqs",
    "decks",
    "cards",
    "card_state",
    "review_log",
    "sessions",
    "session_points",
    "evidence",
    "blockers",
    "point_state",
    "point_state_log",
    "ai_cache",
    "api_usage",
    "map_imports",
}


def test_all_17_tables_exist() -> None:
    engine = get_engine()
    inspector = inspect(engine)
    tables = set(inspector.get_table_names())
    assert EXPECTED_TABLES.issubset(tables), f"Missing tables: {EXPECTED_TABLES - tables}"
    assert len(EXPECTED_TABLES) == 17


def test_ai_cache_and_api_usage_crud(db_session: Session) -> None:
    cache = AiCache(
        cache_key="k" * 64,
        kind="explain",
        model="gemini-3-8-flash-openai",
        prompt_ver="v1",
        content={"definition": "test content"},
        tokens_in=10,
        tokens_out=20,
    )
    db_session.add(cache)

    usage = ApiUsage(
        token_name="web",
        day=date(2026, 10, 7),
        ai_calls=2,
        requests=10,
    )
    db_session.add(usage)
    db_session.commit()

    cached_item = db_session.query(AiCache).filter_by(cache_key="k" * 64).first()
    assert cached_item is not None
    assert cached_item.kind == "explain"
    assert cached_item.content == {"definition": "test content"}

    usage_item = db_session.query(ApiUsage).filter_by(token_name="web", day=date(2026, 10, 7)).first()
    assert usage_item is not None
    assert usage_item.ai_calls == 2
    assert usage_item.requests == 10


def test_evidence_check_constraint_rejects_both_null(db_session: Session) -> None:
    invalid_evidence = Evidence(
        type="selftest",
        passed=True,
        point_id=None,
        stage_id=None,
    )
    db_session.add(invalid_evidence)
    with pytest.raises((exc.IntegrityError, exc.OperationalError))  # MySQL 8 reports CHECK violations as 3819 OperationalError:
        db_session.commit()
    db_session.rollback()


def test_alembic_downgrade_and_upgrade_cycle() -> None:
    cfg = Config("alembic.ini")
    command.downgrade(cfg, "base")

    engine = get_engine()
    inspector = inspect(engine)
    tables_after_down = inspector.get_table_names()
    assert "subjects" not in tables_after_down

    command.upgrade(cfg, "head")
    inspector = inspect(engine)
    tables_after_up = set(inspector.get_table_names())
    assert EXPECTED_TABLES.issubset(tables_after_up)


def test_migration_matches_models(setup_test_db: str) -> None:
    """The frozen 0001 migration must produce exactly what the models describe."""
    from alembic.autogenerate import compare_metadata
    from alembic.migration import MigrationContext
    from sqlalchemy import create_engine

    from tongyun_learn.models import Base

    engine = create_engine(setup_test_db)
    with engine.connect() as conn:
        diffs = compare_metadata(MigrationContext.configure(conn), Base.metadata)
    engine.dispose()
    assert diffs == []
