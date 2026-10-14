from datetime import date, datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from tongyun_learn.config import get_settings
from tongyun_learn.timeutil import (
    day_bounds_utc,
    iso_local,
    local_date,
    today_local,
    to_utc_naive,
    tz,
    utcnow,
)


def test_tz_default():
    get_settings.cache_clear()
    assert tz() == ZoneInfo("Asia/Shanghai")


def test_utcnow_is_naive():
    now = utcnow()
    assert isinstance(now, datetime)
    assert now.tzinfo is None


def test_to_utc_naive_from_naive_local():
    get_settings.cache_clear()
    # naive datetime 默认为服务本地时区 (Asia/Shanghai, UTC+8)
    local_dt = datetime(2026, 10, 14, 10, 30, 0)
    utc_dt = to_utc_naive(local_dt)
    assert utc_dt.tzinfo is None
    # 10:30 UTC+8 -> 02:30 UTC
    assert utc_dt == datetime(2026, 10, 14, 2, 30, 0)

    # 跨天场景: 02:00 UTC+8 -> 前一天 18:00 UTC
    early_dt = datetime(2026, 10, 14, 2, 0, 0)
    assert to_utc_naive(early_dt) == datetime(2026, 10, 13, 18, 0, 0)


def test_to_utc_naive_from_aware_utc():
    aware_utc = datetime(2026, 10, 14, 12, 0, 0, tzinfo=timezone.utc)
    res = to_utc_naive(aware_utc)
    assert res.tzinfo is None
    assert res == datetime(2026, 10, 14, 12, 0, 0)


def test_to_utc_naive_from_aware_other_tz():
    # 东九区 Tokyo (UTC+9)
    tokyo_tz = timezone(timedelta(hours=9))
    aware_tokyo = datetime(2026, 10, 14, 11, 0, 0, tzinfo=tokyo_tz)
    res = to_utc_naive(aware_tokyo)
    assert res.tzinfo is None
    # 11:00 UTC+9 -> 02:00 UTC
    assert res == datetime(2026, 10, 14, 2, 0, 0)


def test_iso_local():
    get_settings.cache_clear()
    assert iso_local(None) is None

    # naive UTC 02:30:15 -> Asia/Shanghai 10:30:15+08:00
    dt_utc = datetime(2026, 10, 14, 2, 30, 15)
    s = iso_local(dt_utc)
    assert s == "2026-10-14T10:30:15+08:00"


def test_local_date_crossing_midnight():
    get_settings.cache_clear()
    # 2026-10-13 15:59:59 UTC -> 23:59:59 +08:00 -> date(2026, 10, 13)
    dt1 = datetime(2026, 10, 13, 15, 59, 59)
    assert local_date(dt1) == date(2026, 10, 13)

    # 2026-10-13 16:00:00 UTC -> 00:00:00 +08:00 -> date(2026, 10, 14)
    dt2 = datetime(2026, 10, 13, 16, 0, 0)
    assert local_date(dt2) == date(2026, 10, 14)


def test_today_local():
    get_settings.cache_clear()
    # 传入显式 now_utc
    ref_utc = datetime(2026, 10, 13, 16, 5, 0)
    assert today_local(ref_utc) == date(2026, 10, 14)

    # 默认无参返回合法 date
    cur = today_local()
    assert isinstance(cur, date)


def test_day_bounds_utc():
    get_settings.cache_clear()
    target_day = date(2026, 10, 14)
    start_utc, end_utc = day_bounds_utc(target_day)

    assert start_utc.tzinfo is None
    assert end_utc.tzinfo is None

    # 本地 2026-10-14 00:00:00 (+08:00) -> 2026-10-13 16:00:00 UTC
    assert start_utc == datetime(2026, 10, 13, 16, 0, 0)
    # 本地 2026-10-15 00:00:00 (+08:00) -> 2026-10-14 16:00:00 UTC
    assert end_utc == datetime(2026, 10, 14, 16, 0, 0)

    assert end_utc - start_utc == timedelta(days=1)
