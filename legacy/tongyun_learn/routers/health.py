from datetime import datetime
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Response
from sqlalchemy import text

from tongyun_learn import __version__
from tongyun_learn.config import get_settings
from tongyun_learn.db import get_engine

router = APIRouter(tags=["health"])


@router.get("/health")
def health_check(response: Response) -> dict[str, str]:
    settings = get_settings()
    now_str = datetime.now(ZoneInfo(settings.tz)).isoformat()

    try:
        with get_engine().connect() as conn:
            conn.execute(text("SELECT 1"))
        db_ok = True
    except Exception:
        db_ok = False

    if not db_ok:
        response.status_code = 503
        return {
            "status": "degraded",
            "version": __version__,
            "db": "error",
            "time": now_str,
        }

    return {
        "status": "ok",
        "version": __version__,
        "db": "ok",
        "time": now_str,
    }


@router.get("/healthz")
def liveness() -> dict[str, str]:
    return {"status": "ok"}
