from datetime import date, timedelta

from change_log.collect import summarize_day, to_events
from change_log.core import day_start, jst_date
from change_log.state import resolve_states
from tests.fakes import act, change, commented, created, deleted, issue, updated

D = date(2026, 9, 30)
START, END = day_start(D), day_start(D + timedelta(days=1))


def _day(activities, issues=()):
    events, malformed = to_events(activities)
    assert malformed == []
    changes = summarize_day(events, START, END)
    resolve_states(changes, events, {i["id"]: i for i in issues}, END)
    return {c.key_id: c for c in changes}


def test_multiple_updates_in_a_day_become_one_row():
    rows = _day([
        updated("2026-09-30 10:00", 1, 98, "帳票", [change("status", "未対応", "処理中")]),
        updated("2026-09-30 13:00", 1, 98, "帳票", [change("assigner", "佐藤", "山田")]),
        updated("2026-09-30 17:00", 1, 98, "帳票", [change("status", "処理中", "処理済み"),
                                                   change("limitDate", "", "2026-10-03")]),
    ], [issue(1, 98, "帳票", "山田")])
    assert rows[98].kind == "updated"
    assert rows[98].fields == ["状態", "担当者", "期限日"]
    assert rows[98].assignee == "山田"


def test_comment_only_counts_as_update():
    rows = _day([commented("2026-09-30 10:00", 2, 105, "問い合わせ")], [issue(2, 105, "問い合わせ", "佐藤")])
    assert rows[105].kind == "updated" and rows[105].fields == ["コメント"]


def test_update_with_comment_adds_comment_label():
    rows = _day([updated("2026-09-30 10:00", 3, 101, "調査", [change("limitDate", "a", "b")], comment="延期")],
                [issue(3, 101, "調査", "鈴木")])
    assert rows[101].fields == ["期限日", "コメント"]


def test_custom_field_uses_its_own_name():
    rows = _day([updated("2026-09-30 10:00", 3, 101, "調査", [change("対応チーム", "A", "B")])],
                [issue(3, 101, "調査", None)])
    assert rows[101].fields == ["対応チーム"]
    assert rows[101].assignee == "未設定"


def test_multi_update_expands_to_each_issue():
    rows = _day([act(14, "2026-09-30 10:00", {
        "tx_id": 1, "changes": [change("status", "未対応", "完了")],
        "link": [{"id": 4, "key_id": 110, "title": "A"}, {"id": 5, "key_id": 111, "title": "B"}],
    })], [issue(4, 110, "A", "佐藤"), issue(5, 111, "B", "山田")])
    assert rows[110].fields == ["状態"] and rows[111].fields == ["状態"]


def test_created_then_updated_is_created_only():
    rows = _day([
        created("2026-09-30 09:00", 6, 123, "ログイン"),
        updated("2026-09-30 12:00", 6, 123, "ログイン", [change("assigner", "", "山田")]),
    ], [issue(6, 123, "ログイン", "山田")])
    assert rows[123].kind == "created" and rows[123].assignee == "山田"


def test_created_then_deleted_is_deleted_with_note():
    rows = _day([
        created("2026-09-30 09:00", 7, 120, "重複"),
        deleted("2026-09-30 11:00", 7, 120, "重複（テスト）"),
    ])
    assert rows[120].kind == "deleted" and rows[120].created_same_day
    assert rows[120].summary == "重複（テスト）"


def test_other_days_are_ignored():
    rows = _day([updated("2026-09-29 23:59", 1, 98, "x", [change("status", "a", "b")]),
                 updated("2026-10-01 00:00", 1, 98, "x", [change("status", "b", "c")])])
    assert rows == {}


def test_assignee_is_end_of_day_value_when_changed_later():
    rows = _day([
        updated("2026-09-30 10:00", 1, 98, "帳票", [change("assigner", "佐藤", "山田")]),
        updated("2026-10-01 09:00", 1, 98, "帳票", [change("assigner", "山田", "鈴木")]),
        updated("2026-10-01 10:00", 1, 98, "帳票", [change("assigner", "鈴木", "")]),
    ], [issue(1, 98, "帳票", None)])
    assert rows[98].assignee == "山田"


def test_summary_is_end_of_day_value_when_changed_later():
    rows = _day([
        updated("2026-09-30 10:00", 1, 98, "旧名", [change("status", "a", "b")]),
        updated("2026-10-01 09:00", 1, 98, "旧名", [change("summary", "旧名", "新名")]),
    ], [issue(1, 98, "新名", "山田")])
    assert rows[98].summary == "旧名"


def test_assignee_after_later_deletion_uses_last_known_value():
    rows = _day([
        updated("2026-09-30 10:00", 1, 98, "帳票", [change("assigner", "", "山田")]),
        deleted("2026-10-01 09:00", 1, 98, "帳票"),
    ])
    assert rows[98].assignee == "山田" and rows[98].summary == "帳票"


def test_assignee_unknown_after_later_deletion_without_history():
    rows = _day([
        updated("2026-09-30 10:00", 1, 98, "帳票", [change("status", "a", "b")]),
        deleted("2026-10-01 09:00", 1, 98, "帳票"),
    ])
    assert rows[98].assignee == "不明"


def test_malformed_activities_are_skipped_and_reported():
    good = updated("2026-09-30 10:00", 1, 98, "帳票", [change("status", "a", "b")])
    no_id = act(2, "2026-09-30 11:00", {"key_id": 5, "summary": "x", "changes": []})
    bad_changes = act(2, "2026-09-29 11:00", {"id": 2, "changes": "壊れた値"})
    bad_link = act(14, "2026-09-28 11:00", {"changes": [], "link": [{"key_id": 1}]})
    no_content = act(1, "2026-09-27 11:00", None)
    no_created = {"id": 999, "type": 1, "content": {"id": 3}}
    events, malformed = to_events([good, no_id, bad_changes, bad_link, no_content, no_created])
    assert [e.issue_id for e in events] == [1]
    assert sorted(jst_date(t).isoformat() for t in malformed if t) == [
        "2026-09-27", "2026-09-28", "2026-09-29", "2026-09-30"]
    assert malformed.count(None) == 1   # 日時の読めないもの
