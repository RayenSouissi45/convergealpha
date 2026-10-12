"""NYSE trading calendar (full-day closures) from rules, so future dates work offline."""

from __future__ import annotations

from datetime import date, datetime, timedelta
from functools import lru_cache

from convergealpha.config import DECISION_TIME, NEW_YORK


def _easter(year: int) -> date:
    # Anonymous Gregorian algorithm.
    a = year % 19
    b, c = divmod(year, 100)
    d, e = divmod(b, 4)
    f = (b + 8) // 25
    g = (b - f + 1) // 3
    h = (19 * a + b - d - g + 15) % 30
    i, k = divmod(c, 4)
    l_ = (32 + 2 * e + 2 * i - h - k) % 7
    m = (a + 11 * h + 22 * l_) // 451
    month, day = divmod(h + l_ - 7 * m + 114, 31)
    return date(year, month, day + 1)


def _nth_weekday(year: int, month: int, weekday: int, n: int) -> date:
    d = date(year, month, 1)
    d += timedelta(days=(weekday - d.weekday()) % 7)
    return d + timedelta(weeks=n - 1)


def _last_weekday(year: int, month: int, weekday: int) -> date:
    d = date(year, month + 1, 1) - timedelta(days=1) if month < 12 else date(year, 12, 31)
    return d - timedelta(days=(d.weekday() - weekday) % 7)


def _observed(d: date) -> date:
    if d.weekday() == 5:
        return d - timedelta(days=1)
    if d.weekday() == 6:
        return d + timedelta(days=1)
    return d


@lru_cache(maxsize=64)
def holidays(year: int) -> frozenset[date]:
    days = {
        _nth_weekday(year, 1, 0, 3),  # Martin Luther King Jr. Day
        _nth_weekday(year, 2, 0, 3),  # Washington's Birthday
        _easter(year) - timedelta(days=2),  # Good Friday
        _last_weekday(year, 5, 0),  # Memorial Day
        _observed(date(year, 7, 4)),
        _nth_weekday(year, 9, 0, 1),  # Labor Day
        _nth_weekday(year, 11, 3, 4),  # Thanksgiving
        _observed(date(year, 12, 25)),
    }
    new_year = date(year, 1, 1)
    if new_year.weekday() != 5:  # NYSE does not close Fri Dec 31 for a Saturday New Year
        days.add(_observed(new_year))
    if year >= 2022:
        days.add(_observed(date(year, 6, 19)))  # Juneteenth
    # One-off closures since 2010.
    special = {
        2012: [date(2012, 10, 29), date(2012, 10, 30)],  # Hurricane Sandy
        2018: [date(2018, 12, 5)],  # President Bush funeral
        2025: [date(2025, 1, 9)],  # President Carter funeral
    }
    days.update(special.get(year, []))
    return frozenset(days)


def is_trading_day(d: date) -> bool:
    return d.weekday() < 5 and d not in holidays(d.year)


def next_trading_day(d: date) -> date:
    d += timedelta(days=1)
    while not is_trading_day(d):
        d += timedelta(days=1)
    return d


def previous_trading_day(d: date) -> date:
    d -= timedelta(days=1)
    while not is_trading_day(d):
        d -= timedelta(days=1)
    return d


def add_trading_days(d: date, n: int) -> date:
    step = next_trading_day if n >= 0 else previous_trading_day
    for _ in range(abs(n)):
        d = step(d)
    return d


def trading_days_between(start: date, end: date) -> int:
    """Number of trading days in (start, end]; negative if end < start."""
    if end < start:
        return -trading_days_between(end, start)
    n, d = 0, start
    while d < end:
        d = next_trading_day(d)
        if d <= end:
            n += 1
    return n


def last_completed_session(now: datetime) -> date:
    """The latest trading day whose close is final at `now` (after the 16:15 decision time)."""
    local = now.astimezone(NEW_YORK)
    d = local.date()
    if is_trading_day(d) and local.time() >= DECISION_TIME:
        return d
    return previous_trading_day(d)
