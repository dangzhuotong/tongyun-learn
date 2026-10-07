import math
import threading
import time
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from tongyun_learn.config import Settings, get_settings
from tongyun_learn.errors import ApiError
from tongyun_learn.models import ApiUsage


def today_local(settings: Settings | None = None) -> date:
    if settings is None:
        settings = get_settings()
    tz = ZoneInfo(settings.tz)
    return datetime.now(tz).date()


class RateLimiter:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._tokens: dict[str, float] = {}
        self._last_time: dict[str, float] = {}

    def reset(self) -> None:
        with self._lock:
            self._tokens.clear()
            self._last_time.clear()

    def check(self, name: str, settings: Settings | None = None) -> tuple[bool, int]:
        if settings is None:
            settings = get_settings()
        limit = settings.rate_web_per_min if name == "web" else settings.rate_axue_per_min
        if limit <= 0:
            return False, 60

        capacity = float(limit)
        refill_rate = capacity / 60.0  # tokens per second
        now = time.monotonic()

        with self._lock:
            if name not in self._tokens:
                self._tokens[name] = capacity
                self._last_time[name] = now

            elapsed = now - self._last_time[name]
            self._tokens[name] = min(capacity, self._tokens[name] + elapsed * refill_rate)
            self._last_time[name] = now

            if self._tokens[name] >= 1.0:
                self._tokens[name] -= 1.0
                return True, 0
            else:
                needed = 1.0 - self._tokens[name]
                retry_after = max(1, math.ceil(needed / refill_rate))
                return False, retry_after


rate_limiter = RateLimiter()


def reset_rate_limiter() -> None:
    rate_limiter.reset()


def bump_requests(db: Session, name: str, settings: Settings | None = None) -> None:
    day = today_local(settings)
    for attempt in range(2):
        try:
            usage = (
                db.query(ApiUsage)
                .with_for_update()
                .filter(ApiUsage.token_name == name, ApiUsage.day == day)
                .first()
            )
            if usage is None:
                usage = ApiUsage(token_name=name, day=day, requests=1, ai_calls=0)
                db.add(usage)
            else:
                usage.requests += 1
            db.commit()
            return
        except IntegrityError:
            db.rollback()
            if attempt == 1:
                raise


def bump_ai_calls(db: Session, name: str, settings: Settings | None = None) -> None:
    day = today_local(settings)
    for attempt in range(2):
        try:
            usage = (
                db.query(ApiUsage)
                .with_for_update()
                .filter(ApiUsage.token_name == name, ApiUsage.day == day)
                .first()
            )
            if usage is None:
                usage = ApiUsage(token_name=name, day=day, requests=0, ai_calls=1)
                db.add(usage)
            else:
                usage.ai_calls += 1
            db.commit()
            return
        except IntegrityError:
            db.rollback()
            if attempt == 1:
                raise


def ai_calls_today(db: Session, name: str, settings: Settings | None = None) -> int:
    day = today_local(settings)
    usage = (
        db.query(ApiUsage)
        .filter(ApiUsage.token_name == name, ApiUsage.day == day)
        .first()
    )
    return usage.ai_calls if usage else 0


def check_ai_cap(db: Session, name: str, settings: Settings | None = None) -> None:
    if settings is None:
        settings = get_settings()
    cap = settings.ai_daily_web if name == "web" else settings.ai_daily_axue
    calls = ai_calls_today(db, name, settings)
    if calls >= cap:
        tz = ZoneInfo(settings.tz)
        now_local = datetime.now(tz)
        tomorrow = now_local.date() + timedelta(days=1)
        next_midnight = datetime(tomorrow.year, tomorrow.month, tomorrow.day, 0, 0, 0, tzinfo=tz)
        seconds_until_midnight = max(1, int((next_midnight - now_local).total_seconds()))
        raise ApiError(
            status=429,
            code="ai_daily_cap",
            message="今日 AI 次数已用完",
            headers={"Retry-After": str(seconds_until_midnight)},
        )
