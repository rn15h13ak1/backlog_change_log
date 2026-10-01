import io
from datetime import datetime

from change_log.core import JST
from change_log.marker import parse_marker
from change_log.runner import run
from tests.fakes import RECORD_ID, FakeClient, change, commented, created, issue, record_comment, updated

NOW = datetime(2026, 10, 1, 14, 30, tzinfo=JST)


def _run(client, **kwargs):
    out, err = io.StringIO(), io.StringIO()
    code = run(client, "PROJ-1", now=NOW, out=out, err=err, **kwargs)
    return code, out.getvalue(), err.getvalue()


def _base_activities():
    return [
        # 記録先の課題の作成（ここまで履歴が揃っている印になる）
        created("2026-09-01 09:00", RECORD_ID, 1, "変更記録"),
        # 古い日（初回では出力しない）
        updated("2026-09-28 10:00", 1, 98, "帳票", [change("status", "a", "b")]),
        # 前日
        created("2026-09-30 09:00", 2, 123, "ログイン"),
        updated("2026-09-30 10:00", 1, 98, "帳票", [change("assigner", "佐藤", "山田")]),
        # 記録先の課題そのもの（対象外）
        commented("2026-09-30 11:00", RECORD_ID, 1, "変更記録"),
        # 当日
        updated("2026-10-01 09:00", 3, 101, "調査", [change("limitDate", "a", "b")]),
    ]


def _issues():
    return [issue(1, 98, "帳票", "山田"), issue(2, 123, "ログイン", None), issue(3, 101, "調査", "鈴木")]


def test_first_run_posts_yesterday_only_and_prints_today():
    client = FakeClient(_base_activities(), _issues())
    code, out, _ = _run(client)
    assert code == 0   # 出力しなかった日は無い
    assert len(client.posted) == 1
    body = client.posted[0]
    assert parse_marker(body).isoformat() == "2026-09-30"
    assert "PROJ-123" in body and "PROJ-98" in body
    assert "PROJ-1 " not in body and "| PROJ-1 |" not in body   # 記録先は載らない
    assert "PROJ-101" not in body                               # 当日分は載らない
    # 当日分は標準出力だけ
    assert "2026-10-01 の課題の変更（0:00〜14:30 時点）" in out
    assert "| PROJ-101 | 調査 | 期限日 | 鈴木 |" in out


def test_second_run_on_same_day_posts_nothing():
    client = FakeClient(_base_activities(), _issues())
    _run(client)
    _run(client)
    assert len(client.posted) == 1


def test_catch_up_posts_each_missing_day_in_order():
    client = FakeClient(_base_activities(), _issues(), comments=[record_comment("x\n対象日: 2026-09-27")])
    _run(client)
    assert [parse_marker(b).isoformat() for b in client.posted] == ["2026-09-28", "2026-09-29", "2026-09-30"]
    assert "変更はありませんでした。" in client.posted[1]


def test_reads_only_until_latest_marker():
    old = [record_comment(f"対象日: 2026-09-{d:02d}") for d in range(1, 29)]
    client = FakeClient(_base_activities(), _issues(), comments=old + [record_comment("雑談")])
    _run(client)
    assert client.comments_read == 2


def test_more_than_seven_days_skips_older_and_does_not_revisit():
    client = FakeClient(_base_activities(), _issues(), comments=[record_comment("対象日: 2026-09-20")])
    code, _, err = _run(client)
    assert code == 3
    assert [parse_marker(b).isoformat() for b in client.posted] == [f"2026-09-{d}" for d in range(24, 31)]
    assert "2026-09-21〜2026-09-23 は上限 7 日を超えた" in err
    assert _run(client)[0] == 0   # 次の実行では出力しなかった日を持ち越さない
    assert len(client.posted) == 7


def test_dry_run_posts_nothing():
    client = FakeClient(_base_activities(), _issues())
    _, out, _ = _run(client, dry_run=True)
    assert client.posted == []
    assert "対象日: 2026-09-30" in out


def test_failure_stops_and_leaves_rest_for_next_run():
    client = FakeClient(_base_activities(), _issues(), comments=[record_comment("対象日: 2026-09-27")],
                        fail_post_at=1)
    code, _, err = _run(client)
    assert code == 1 and len(client.posted) == 1
    assert "2026-09-29 のコメントの投稿に失敗" in err
    client.fail_post_at = None
    _run(client)
    assert [parse_marker(b).isoformat() for b in client.posted] == ["2026-09-28", "2026-09-29", "2026-09-30"]


def test_days_beyond_available_activities_are_not_posted():
    # 記録先の課題の作成が見えない（履歴が途中で切れている）場合
    # 遡れる最古のアクティビティが 9/29 12:00。9/28 と 9/29 は不完全かもしれない
    acts = [updated("2026-09-29 12:00", 1, 98, "帳票", [change("status", "a", "b")]),
            updated("2026-09-30 10:00", 1, 98, "帳票", [change("status", "b", "c")])]
    client = FakeClient(acts, _issues(), comments=[record_comment("対象日: 2026-09-27")])
    code, _, err = _run(client)
    assert code == 3
    assert [parse_marker(b).isoformat() for b in client.posted] == ["2026-09-30"]
    assert "2026-09-28〜2026-09-29 はアクティビティを遡りきれず" in err


def test_backlog_formatting_rule():
    client = FakeClient(_base_activities(), _issues(), fmt="backlog")
    _run(client)
    assert client.posted[0].startswith("** 2026-09-30 の課題の変更")


def test_short_history_is_complete_when_record_creation_is_seen():
    # プロジェクトの履歴が短く、ページの端まで読み切った。記録先の作成が見えるので揃っている
    acts = [created("2026-09-29 08:00", RECORD_ID, 1, "変更記録"),
            updated("2026-09-30 10:00", 1, 98, "帳票", [change("status", "b", "c")])]
    client = FakeClient(acts, _issues(), comments=[record_comment("対象日: 2026-09-27")])
    _, _, err = _run(client)
    assert [parse_marker(b).isoformat() for b in client.posted] == ["2026-09-28", "2026-09-29", "2026-09-30"]
    assert err == ""


def test_day_with_malformed_activity_is_not_posted():
    from tests.fakes import act
    broken = act(2, "2026-09-29 12:00", {"key_id": 5, "summary": "x"})   # content.id が無い
    client = FakeClient(_base_activities() + [broken], _issues(), comments=[record_comment("対象日: 2026-09-27")])
    code, _, err = _run(client)
    assert code == 3
    assert [parse_marker(b).isoformat() for b in client.posted] == ["2026-09-28", "2026-09-30"]
    assert "想定と違う形のアクティビティが 1 件" in err
    assert "2026-09-29 は変更が欠けている可能性" in err


def test_undated_malformed_activity_stops_all_days():
    client = FakeClient(_base_activities(), _issues(), comments=[record_comment("対象日: 2026-09-27")])
    client.activities.append({"id": 9999, "type": 2, "created": "2099-01-01T00:00:00Z", "content": None})
    client.activities.append({"id": 9998, "type": 2, "content": {"id": 1}})  # 日時が無い
    code, out, err = _run(client)
    assert code == 3
    assert client.posted == []
    assert "2026-09-28〜2026-09-30 は変更が欠けている可能性" in err
    assert "当日の変更" in out   # 当日分の表示は続ける


def test_post_failure_wins_over_days_not_output():
    client = FakeClient(_base_activities(), _issues(), comments=[record_comment("対象日: 2026-09-20")],
                        fail_post_at=0)
    code, _, _ = _run(client)
    assert code == 1


OTHER_ID = 20


def _other(activities, issues=None):
    return {"OTHER": (OTHER_ID, activities, issues or [])}


def _other_issues():
    return [issue(501, 5, "問い合わせ", "鈴木")]


def test_multiple_projects_in_one_comment():
    other_acts = [created("2026-08-01 09:00", 500, 1, "最初の課題"),
                  commented("2026-09-30 15:00", 501, 5, "問い合わせ")]
    client = FakeClient(_base_activities(), _issues(), other_projects=_other(other_acts, _other_issues()))
    code, out, _ = _run(client, project_keys=["PROJ", "OTHER"])
    assert code == 0
    assert "追跡するプロジェクト: PROJ, OTHER" in out
    [body] = client.posted
    assert "対象: PROJ, OTHER" in body
    assert "### PROJ" in body and "### OTHER" in body
    assert "| OTHER-5 | 問い合わせ | コメント | 鈴木 |" in body
    assert "| PROJ-98 |" in body
    assert "| PROJ-1 |" not in body   # 記録先は載らない


def test_record_project_is_not_tracked_unless_listed():
    other_acts = [created("2026-08-01 09:00", 500, 1, "最初の課題"),
                  commented("2026-09-30 15:00", 501, 5, "問い合わせ")]
    client = FakeClient(_base_activities(), _issues(), other_projects=_other(other_acts, _other_issues()))
    _run(client, project_keys=["OTHER"])
    assert client.activity_requests == [OTHER_ID]
    [body] = client.posted
    assert "PROJ-" not in body and "### OTHER" not in body   # 1 つだけなら見出しは付けない
    assert "| OTHER-5 |" in body


def test_day_is_skipped_for_all_projects_if_one_is_incomplete():
    # OTHER は 9/29 12:00 より前を遡れず、最初の課題の作成も見えない
    other_acts = [commented("2026-09-29 12:00", 501, 5, "問い合わせ"),
                  commented("2026-09-30 15:00", 501, 5, "問い合わせ")]
    client = FakeClient(_base_activities(), _issues(), comments=[record_comment("対象日: 2026-09-27")],
                        other_projects=_other(other_acts, _other_issues()))
    code, _, err = _run(client, project_keys=["PROJ", "OTHER"])
    assert code == 3
    assert [parse_marker(b).isoformat() for b in client.posted] == ["2026-09-30"]
    assert "OTHER: 2026-09-28〜2026-09-29 はアクティビティを遡りきれず" in err


def test_project_without_any_activity_is_complete():
    client = FakeClient(_base_activities(), _issues(), comments=[record_comment("対象日: 2026-09-27")],
                        other_projects=_other([]))
    code, _, err = _run(client, project_keys=["PROJ", "OTHER"])
    assert code == 0 and err == ""
    assert len(client.posted) == 3


def test_first_issue_creation_proves_history_is_complete():
    other_acts = [created("2026-09-29 08:00", 500, 1, "最初の課題")]
    client = FakeClient(_base_activities(), _issues(), comments=[record_comment("対象日: 2026-09-27")],
                        other_projects=_other(other_acts, [issue(500, 1, "最初の課題", None)]))
    code, _, err = _run(client, project_keys=["PROJ", "OTHER"])
    assert code == 0 and err == ""
    assert [parse_marker(b).isoformat() for b in client.posted] == ["2026-09-28", "2026-09-29", "2026-09-30"]
    assert "| OTHER-1 | 最初の課題 | 未設定 |" in client.posted[1]


def test_malformed_in_one_project_skips_that_day():
    from tests.fakes import act
    other_acts = [created("2026-08-01 09:00", 500, 1, "最初の課題"),
                  act(2, "2026-09-29 12:00", {"key_id": 5})]   # content.id が無い
    client = FakeClient(_base_activities(), _issues(), comments=[record_comment("対象日: 2026-09-27")],
                        other_projects=_other(other_acts))
    code, _, err = _run(client, project_keys=["PROJ", "OTHER"])
    assert code == 3
    assert [parse_marker(b).isoformat() for b in client.posted] == ["2026-09-28", "2026-09-30"]
    assert "OTHER: 想定と違う形のアクティビティが 1 件" in err


def test_unknown_project_stops_before_posting():
    import pytest

    from change_log.client import BacklogAPIError
    client = FakeClient(_base_activities(), _issues())
    with pytest.raises(BacklogAPIError):
        _run(client, project_keys=["PROJ", "NOPE"])
    assert client.posted == []
