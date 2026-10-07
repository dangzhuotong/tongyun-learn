from collections.abc import Generator
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import Engine, create_engine
from sqlalchemy.orm import Session, sessionmaker

from tongyun_learn.config import get_settings


def utcnow() -> datetime:
    """Return current naive UTC datetime."""
    return datetime.now(timezone.utc).replace(tzinfo=None)


_engine: Engine | None = None
_sessionmaker: sessionmaker[Session] | None = None


def get_engine() -> Engine:
    global _engine
    if _engine is None:
        settings = get_settings()
        kwargs: dict[str, Any] = {
            "pool_pre_ping": True,
            "pool_recycle": 3600,
            "future": True,
        }
        if settings.database_url.startswith("sqlite"):
            kwargs["connect_args"] = {"check_same_thread": False}
        _engine = create_engine(settings.database_url, **kwargs)
    return _engine


def get_sessionmaker() -> sessionmaker[Session]:
    global _sessionmaker
    if _sessionmaker is None:
        _sessionmaker = sessionmaker(
            bind=get_engine(),
            autoflush=False,
            expire_on_commit=False,
        )
    return _sessionmaker


def reset_engine() -> None:
    global _engine, _sessionmaker
    if _engine is not None:
        _engine.dispose()
    _engine = None
    _sessionmaker = None


class _SessionLocalFactory:
    def __call__(self, *args: Any, **kwargs: Any) -> Session:
        return get_sessionmaker()(*args, **kwargs)


SessionLocal = _SessionLocalFactory()


def get_db() -> Generator[Session, None, None]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def __getattr__(name: str) -> Any:
    if name == "engine":
        return get_engine()
    raise AttributeError(f"module '{__name__}' has no attribute '{name}'")
