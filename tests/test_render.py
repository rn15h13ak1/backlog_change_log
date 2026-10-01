from datetime import date

from change_log.collect import IssueChange
from change_log.marker import parse_marker
from change_log.render import BACKLOG, MARKDOWN, render_day

D = date(2026, 9, 30)


def _changes():
    return [
        IssueChange(1, 123, "created", [], "ログイン画面", "山田", "バグ", "未対応"),
        IssueChange(2, 98, "updated", ["状態", "担当者"], "帳票|レイアウト", "山田", "タスク", "処理済み"),
        IssueChange(3, 120, "deleted", [], "重複", created_same_day=True),
    ]


def test_markdown_layout():
    [body] = render_day(D, [("PROJ", _changes())], MARKDOWN)
    assert body == "\n".join([
        "## 2026-09-30 の課題の変更",
        "",
        "作成 1 件 / 更新 1 件 / 削除 1 件",
        "",
        "### 作成",
        "",
        "| 課題 | 件名 | 種別 | 状態 | 担当者 |",
        "|---|---|---|---|---|",
        "| PROJ-123 | ログイン画面 | バグ | 未対応 | 山田 |",
        "",
        "### 更新",
        "",
        "| 課題 | 件名 | 種別 | 状態 | 変更した項目 | 担当者 |",
        "|---|---|---|---|---|---|",
        "| PROJ-98 | 帳票｜レイアウト | タスク | 処理済み | 状態、担当者 | 山田 |",
        "",
        "### 削除",
        "",
        "| 課題 | 件名 |",
        "|---|---|",
        "| PROJ-120 | 重複（当日作成） |",
        "",
        "---",
        "対象日: 2026-09-30",
    ])


def test_backlog_syntax():
    [body] = render_day(D, [("PROJ", _changes())], BACKLOG)
    assert "** 2026-09-30 の課題の変更" in body
    assert "|課題|件名|種別|状態|変更した項目|担当者|h" in body
    assert "|PROJ-98|帳票｜レイアウト|タスク|処理済み|状態、担当者|山田|" in body
    assert body.endswith("----\n対象日: 2026-09-30")


def test_no_changes():
    [body] = render_day(D, [("PROJ", [])], MARKDOWN)
    assert "変更はありませんでした。" in body
    assert parse_marker(body) == D


def test_without_marker_for_today():
    [body] = render_day(D, [("PROJ", _changes())], MARKDOWN, title_note="（0:00〜14:30 時点）", with_marker=False)
    assert "## 2026-09-30 の課題の変更（0:00〜14:30 時点）" in body
    assert parse_marker(body) is None


def test_long_day_is_split_with_marker_only_on_last():
    many = [IssueChange(i, i, "updated", ["状態"], "件名" * 20, "山田") for i in range(1, 200)]
    parts = render_day(D, [("PROJ", many)], MARKDOWN, max_chars=3000)
    assert len(parts) > 1
    assert all(len(p) <= 3000 for p in parts)
    assert [parse_marker(p) for p in parts] == [None] * (len(parts) - 1) + [D]
    assert parts[0].startswith(f"## 2026-09-30 の課題の変更（1/{len(parts)}）")
    assert "### 更新（続き）" in parts[1]
    assert sum(p.count("| PROJ-") for p in parts) == 199


def test_multiple_projects_are_grouped():
    other = [IssueChange(9, 5, "updated", ["コメント"], "問い合わせ", "鈴木", "質問", "処理中")]
    [body] = render_day(D, [("PROJ", _changes()), ("OTHER", other), ("EMPTY", [])], MARKDOWN)
    assert body == "\n".join([
        "## 2026-09-30 の課題の変更",
        "",
        "対象: PROJ, OTHER, EMPTY",
        "",
        "作成 1 件 / 更新 2 件 / 削除 1 件",
        "",
        "### PROJ",
        "",
        "作成 1 件 / 更新 1 件 / 削除 1 件",
        "",
        "#### 作成",
        "",
        "| 課題 | 件名 | 種別 | 状態 | 担当者 |",
        "|---|---|---|---|---|",
        "| PROJ-123 | ログイン画面 | バグ | 未対応 | 山田 |",
        "",
        "#### 更新",
        "",
        "| 課題 | 件名 | 種別 | 状態 | 変更した項目 | 担当者 |",
        "|---|---|---|---|---|---|",
        "| PROJ-98 | 帳票｜レイアウト | タスク | 処理済み | 状態、担当者 | 山田 |",
        "",
        "#### 削除",
        "",
        "| 課題 | 件名 |",
        "|---|---|",
        "| PROJ-120 | 重複（当日作成） |",
        "",
        "### OTHER",
        "",
        "作成 0 件 / 更新 1 件 / 削除 0 件",
        "",
        "#### 更新",
        "",
        "| 課題 | 件名 | 種別 | 状態 | 変更した項目 | 担当者 |",
        "|---|---|---|---|---|---|",
        "| OTHER-5 | 問い合わせ | 質問 | 処理中 | コメント | 鈴木 |",
        "",
        "### EMPTY",
        "",
        "変更はありませんでした。",
        "",
        "---",
        "対象日: 2026-09-30",
    ])


def test_multiple_projects_backlog_syntax():
    [body] = render_day(D, [("PROJ", _changes()), ("OTHER", [])], BACKLOG)
    assert "*** PROJ" in body and "**** 更新" in body and "*** OTHER" in body


def test_multiple_projects_without_any_change():
    [body] = render_day(D, [("PROJ", []), ("OTHER", [])], MARKDOWN)
    assert "対象: PROJ, OTHER" in body
    assert body.count("変更はありませんでした。") == 1


def test_split_repeats_project_heading():
    many = [IssueChange(i, i, "updated", ["状態"], "件名" * 20, "山田") for i in range(1, 120)]
    parts = render_day(D, [("PROJ", many), ("OTHER", many)], MARKDOWN, max_chars=3000)
    assert all(len(p) <= 3000 for p in parts)
    continued = [p for p in parts if "#### 更新（続き）" in p]
    assert continued and all(("### PROJ" in p) or ("### OTHER" in p) for p in continued)
    assert sum(p.count("| PROJ-") for p in parts) == 119
    assert sum(p.count("| OTHER-") for p in parts) == 119
    assert [parse_marker(p) for p in parts].count(D) == 1
