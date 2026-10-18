import hashlib
from pathlib import Path

import pytest

from tongyun_learn.config import get_settings
from tongyun_learn.db import SessionLocal
from tongyun_learn.limits import reset_rate_limiter
from tongyun_learn.models import Base

WEB_TOKEN = "web-test-token"
AXUE_TOKEN = "axue-test-token"
WEB = {"Authorization": f"Bearer {WEB_TOKEN}"}
AXUE = {"Authorization": f"Bearer {AXUE_TOKEN}"}
MAPS = Path(__file__).resolve().parent.parent / "maps"


def map_texts() -> list[str]:
    return [(MAPS / "english.yaml").read_text(encoding="utf-8"), (MAPS / "java-fde.yaml").read_text(encoding="utf-8")]


def wipe() -> None:
    with SessionLocal() as db:
        for t in reversed(Base.metadata.sorted_tables):
            db.execute(t.delete())
        db.commit()


@pytest.fixture
def learn_env(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("LEARN_TOKEN_WEB_SHA256", hashlib.sha256(WEB_TOKEN.encode()).hexdigest())
    monkeypatch.setenv("LEARN_TOKEN_AXUE_SHA256", hashlib.sha256(AXUE_TOKEN.encode()).hexdigest())
    monkeypatch.setenv("LEARN_RATE_WEB_PER_MIN", "100000")
    monkeypatch.setenv("LEARN_RATE_AXUE_PER_MIN", "100000")
    get_settings.cache_clear()
    reset_rate_limiter()
    wipe()
    yield
    wipe()
    get_settings.cache_clear()
    reset_rate_limiter()
