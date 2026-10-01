from datetime import date

from change_log.marker import decide_target_dates, find_latest_recorded, marker_line, parse_marker
from tests.fakes import ME, record_comment

TODAY = date(2026, 10, 1)


def test_marker_round_trip():
    assert parse_marker("本文\n\n---\n" + marker_line(date(2026, 9, 30))) == date(2026, 9, 30)


def test_marker_must_be_its_own_line():
    assert parse_marker("前回は 対象日: 2026-09-30 でした") is None
    assert parse_marker(None) is None


def test_latest_ignores_other_users_and_stops_at_first_hit():
    comments_desc = iter([
        record_comment("対象日: 2026-09-30", user_id=99),   # 他人が書いた
        record_comment("ふつうのコメント"),
        record_comment("対象日: 2026-09-28"),
        record_comment("対象日: 2026-09-27"),
    ])
    assert find_latest_recorded(comments_desc, ME) == date(2026, 9, 28)
    assert next(comments_desc)["content"] == "対象日: 2026-09-27"  # 読み進めていない


def test_first_run_outputs_yesterday_only():
    assert decide_target_dates(None, TODAY) == ([date(2026, 9, 30)], [])


def test_already_up_to_date():
    assert decide_target_dates(date(2026, 9, 30), TODAY) == ([], [])


def test_catch_up_from_day_after_latest():
    dates, skipped = decide_target_dates(date(2026, 9, 28), TODAY)
    assert dates == [date(2026, 9, 29), date(2026, 9, 30)]
    assert skipped == []


def test_exactly_seven_days_are_all_output():
    dates, skipped = decide_target_dates(date(2026, 9, 23), TODAY)
    assert dates[0] == date(2026, 9, 24) and len(dates) == 7
    assert skipped == []


def test_more_than_seven_days_keeps_latest_seven():
    dates, skipped = decide_target_dates(date(2026, 9, 20), TODAY)
    assert dates == [date(2026, 9, d) for d in range(24, 31)]
    assert skipped == [date(2026, 9, 21), date(2026, 9, 22), date(2026, 9, 23)]
