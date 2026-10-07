"""时间工具：库里一律存 naive UTC；对外输出带 +08:00；“今天”按 settings.tz 切日。"""

from datetime import date, datetime, time, timedelta, timezone
from zoneinfo import ZoneInfo

from tongyun_learn.config import get_settings


def tz() -> ZoneInfo:
    return ZoneInfo(get_settings().tz)


def utcnow() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def to_utc_naive(dt: datetime) -> datetime:
    """带时区的转成 naive UTC；不带时区的按本地时区（Asia/Shanghai）理解。"""
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=tz())
    return dt.astimezone(timezone.utc).replace(tzinfo=None)


def iso_local(dt: datetime | None) -> str | None:
    if dt is None:
        return None
    return dt.replace(tzinfo=timezone.utc).astimezone(tz()).isoformat(timespec="seconds")


def local_date(dt_utc: datetime) -> date:
    return dt_utc.replace(tzinfo=timezone.utc).astimezone(tz()).date()


def today_local(now_utc: datetime | None = None) -> date:
    return local_date(now_utc or utcnow())


def day_bounds_utc(day: date) -> tuple[datetime, datetime]:
    """本地某天 [00:00, 次日 00:00) 对应的 naive UTC 区间。"""
    start = datetime.combine(day, time(0, 0), tzinfo=tz())
    end = start + timedelta(days=1)
    return to_utc_naive(start), to_utc_naive(end)
