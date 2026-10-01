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
    assert "✓ 担当者の変更は `assigner` として返っています" in out
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
    assert "✗ 更新の content.key_id が無いアクティビティが 1 件あります" in out
    assert "✗ 一括更新の content.link[].id が無いアクティビティが 1 件あります" in out
    assert "✗ 一括更新の content.changes が無いアクティビティが 1 件あります" in out
