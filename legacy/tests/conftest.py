import os
import sys
from collections.abc import Generator
from pathlib import Path

# Ensure repository root is on sys.path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pytest
from alembic import command
from alembic.config import Config
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from tongyun_learn.config import get_settings
from tongyun_learn.db import SessionLocal, reset_engine
from tongyun_learn.main import create_app
from tongyun_learn.models import Base


@pytest.fixture(scope="session", autouse=True)
def setup_test_db(tmp_path_factory: pytest.TempPathFactory) -> Generator[str, None, None]:
    test_db_url = os.environ.get("LEARN_TEST_DATABASE_URL")
    if not test_db_url:
        db_file = tmp_path_factory.mktemp("db") / "test.db"
        test_db_url = f"sqlite:///{db_file}"

    os.environ["LEARN_DATABASE_URL"] = test_db_url
    get_settings.cache_clear()
    reset_engine()

    cfg = Config("alembic.ini")

    engine = create_engine(test_db_url)
    Base.metadata.drop_all(bind=engine)
    with engine.begin() as conn:
        # a previously migrated DB (e.g. the CI MySQL job) keeps alembic_version; reset it so upgrade really runs
        conn.exec_driver_sql("DROP TABLE IF EXISTS alembic_version")
    engine.dispose()

    command.upgrade(cfg, "head")

    yield test_db_url

    reset_engine()
    get_settings.cache_clear()


@pytest.fixture
def app(setup_test_db: str) -> FastAPI:
    get_settings.cache_clear()
    reset_engine()
    return create_app()


@pytest.fixture
def client(app: FastAPI) -> Generator[TestClient, None, None]:
    with TestClient(app) as c:
        yield c


@pytest.fixture
def db_session(setup_test_db: str) -> Generator[Session, None, None]:
    session = SessionLocal()
    # MySQL default is REPEATABLE READ. This session only observes rows committed by
    # request handlers (those sessions stay on the engine default). A snapshot opened
    # by an earlier SELECT would hide those commits, so a later get()/expire_all()
    # still reads the old rows. READ COMMITTED makes each statement here see them.
    # Reset before the connection goes back to the pool.
    mysql = session.get_bind().dialect.name == "mysql"
    if mysql:
        session.connection().exec_driver_sql("SET SESSION TRANSACTION ISOLATION LEVEL READ COMMITTED")
        session.rollback()
    try:
        yield session
    finally:
        if mysql:
            session.rollback()
            session.connection().exec_driver_sql("SET SESSION TRANSACTION ISOLATION LEVEL REPEATABLE READ")
            session.rollback()
        session.close()
