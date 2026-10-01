import io
from datetime import datetime

from change_log.core import JST
from change_log.diagnose import diagnose
from tests.fakes import FakeClient, act, change, commented, created, deleted, updated

NOW = datetime(2026, 10, 1, 14, 30, tzinfo=JST)


def _diagnose(activities):
    out = io.StringIO()
    code = diagnose(FakeClient(activities, []), "PROJ-1", now=NOW, out=out)
    return code, out.getvalue()


def test_all_assumptions_hold():
    code, out = _diagnose([
        created("2026-09-30 09:00", 2, 123, "a"),
        updated("2026-09-30 10:00", 1, 98, "b", [change("assigner", "x", "y"), change("対応チーム", "A", "B")]),
        commented("2026-09-30 11:00", 1, 98, "b"),
        deleted("2026-09-30 12:00", 3, 120, "c"),
        act(14, "2026-09-30 13:00", {"changes": [change("status", "a", "b")],
                                     "link": [{"id": 4, "key_id": 110, "title": "d"}]}),
        updated("2026-09-20 10:00", 1, 98, "古い", [change("milestone", "", "v1")]),  # 期間外
    ])
    assert code == 0
    assert "OK 担当者の変更は `assigner` として返っています" in out
    assert "OK 状態の変更は `status` として返っています" in out     # 一括更新の中の変更
    assert "種別の変更が期間内に 1 件もありませんでした" in out
    assert "assigner: 1 件 → 担当者" in out
    assert "対応チーム: 1 件 → そのまま表示" in out
    assert "milestone" not in out
    assert "前提と違う応答はありませんでした" in out


def test_missing_assigner_is_a_note_not_a_failure():
    code, out = _diagnose([updated("2026-09-30 10:00", 1, 98, "b", [change("status", "a", "b")])])
    assert code == 0
    assert "`assigner` で返るかは確かめられていません" in out
    assert "一括更新が期間内に 1 件もなく" in out


def test_unexpected_shape_is_a_failure():
    broken = act(2, "2026-09-30 10:00", {"id": 1, "changes": []})            # key_id と summary が無い
    bad_multi = act(14, "2026-09-30 11:00", {"link": [{"key_id": 1}]})       # link[].id と changes が無い
    code, out = _diagnose([broken, bad_multi])
    assert code == 1
    assert "NG 更新の content.key_id が無いアクティビティが 1 件あります" in out
    assert "NG 一括更新の content.link[].id が無いアクティビティが 1 件あります" in out
    assert "NG 一括更新の content.changes が無いアクティビティが 1 件あります" in out


def test_each_tracked_project_is_read():
    other = {"OTHER": (20, [updated("2026-09-30 10:00", 501, 5, "x", [change("assigner", "a", "b")])], [])}
    client = FakeClient([updated("2026-09-30 10:00", 1, 98, "b", [change("status", "a", "b")])], [],
                        other_projects=other)
    out = io.StringIO()
    code = diagnose(client, "PROJ-1", project_keys=["PROJ", "OTHER"], now=NOW, out=out)
    text = out.getvalue()
    assert code == 0
    assert "アクティビティ（PROJ、ID 10）: 直近 7 日分を 1 件" in text
    assert "アクティビティ（OTHER、ID 20）: 直近 7 日分を 1 件" in text
    assert "OK 担当者の変更は `assigner` として返っています" in text   # OTHER の分も合算で判定


def test_unknown_project_is_a_failure():
    out = io.StringIO()
    code = diagnose(FakeClient([], []), "PROJ-1", project_keys=["PROJ", "NOPE"], now=NOW, out=out)
    assert code == 1
    assert "NG 追跡するプロジェクト NOPE を取得できません" in out.getvalue()


def test_status_and_type_are_checked():
    code, out = _diagnose([updated("2026-09-30 10:00", 1, 98, "b",
                                   [change("status", "a", "b"), change("issueType", "タスク", "バグ")])])
    assert code == 0
    assert "OK 状態の変更は `status` として返っています" in out
    assert "OK 種別の変更は `issueType` として返っています" in out
