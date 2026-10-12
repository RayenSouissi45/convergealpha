from datetime import UTC, date, datetime

from convergealpha.util import calendar as C


def test_2026_holidays() -> None:
    h = C.holidays(2026)
    for d in [
        date(2026, 1, 1),
        date(2026, 1, 19),  # MLK
        date(2026, 2, 16),  # Presidents
        date(2026, 4, 3),  # Good Friday
        date(2026, 5, 25),  # Memorial
        date(2026, 6, 19),  # Juneteenth
        date(2026, 7, 3),  # Independence Day observed (July 4 is a Saturday)
        date(2026, 9, 7),  # Labor
        date(2026, 11, 26),  # Thanksgiving
        date(2026, 12, 25),
    ]:
        assert d in h, d
    assert date(2026, 10, 12) not in h  # Columbus Day: markets open


def test_saturday_new_year_is_not_observed_on_friday() -> None:
    assert date(2021, 12, 31) not in C.holidays(2022)
    assert C.is_trading_day(date(2021, 12, 31))


def test_trading_day_arithmetic() -> None:
    assert C.next_trading_day(date(2026, 7, 2)) == date(2026, 7, 6)
    assert C.add_trading_days(date(2026, 10, 9), 5) == date(2026, 10, 16)
    assert C.trading_days_between(date(2026, 10, 9), date(2026, 10, 16)) == 5
    assert C.trading_days_between(date(2026, 10, 16), date(2026, 10, 9)) == -5


def test_last_completed_session_respects_1615_new_york() -> None:
    assert C.last_completed_session(datetime(2026, 10, 12, 15, 0, tzinfo=UTC)) == date(2026, 10, 9)
    assert C.last_completed_session(datetime(2026, 10, 12, 20, 16, tzinfo=UTC)) == date(
        2026, 10, 12
    )
    assert C.last_completed_session(datetime(2026, 10, 11, 12, 0, tzinfo=UTC)) == date(2026, 10, 9)
