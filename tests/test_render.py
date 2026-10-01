from datetime import date

from change_log.collect import IssueChange
from change_log.marker import parse_marker
from change_log.render import BACKLOG, MARKDOWN, render_day

D = date(2026, 9, 30)


def _changes():
    return [
        IssueChange(1, 123, "created", [], "ログイン画面", "山田"),
        IssueChange(2, 98, "updated", ["状態", "担当者"], "帳票|レイアウト", "山田"),
        IssueChange(3, 120, "deleted", [], "重複", created_same_day=True),
    ]


def test_markdown_layout():
    [body] = render_day(D, "PROJ", _changes(), MARKDOWN)
    assert body == "\n".join([
        "## 2026-09-30 の課題の変更",
        "",
        "作成 1 件 / 更新 1 件 / 削除 1 件",
        "",
        "### 作成",
        "",
        "| 課題 | 件名 | 担当者 |",
        "|---|---|---|",
        "| PROJ-123 | ログイン画面 | 山田 |",
        "",
        "### 更新",
        "",
        "| 課題 | 件名 | 変更した項目 | 担当者 |",
        "|---|---|---|---|",
        "| PROJ-98 | 帳票｜レイアウト | 状態、担当者 | 山田 |",
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
    [body] = render_day(D, "PROJ", _changes(), BACKLOG)
    assert "** 2026-09-30 の課題の変更" in body
    assert "|課題|件名|変更した項目|担当者|h" in body
    assert "|PROJ-98|帳票｜レイアウト|状態、担当者|山田|" in body
    assert body.endswith("----\n対象日: 2026-09-30")


def test_no_changes():
    [body] = render_day(D, "PROJ", [], MARKDOWN)
    assert "変更はありませんでした。" in body
    assert parse_marker(body) == D


def test_without_marker_for_today():
    [body] = render_day(D, "PROJ", _changes(), MARKDOWN, title_note="（0:00〜14:30 時点）", with_marker=False)
    assert "## 2026-09-30 の課題の変更（0:00〜14:30 時点）" in body
    assert parse_marker(body) is None


def test_long_day_is_split_with_marker_only_on_last():
    many = [IssueChange(i, i, "updated", ["状態"], "件名" * 20, "山田") for i in range(1, 200)]
    parts = render_day(D, "PROJ", many, MARKDOWN, max_chars=3000)
    assert len(parts) > 1
    assert all(len(p) <= 3000 for p in parts)
    assert [parse_marker(p) for p in parts] == [None] * (len(parts) - 1) + [D]
    assert parts[0].startswith(f"## 2026-09-30 の課題の変更（1/{len(parts)}）")
    assert "### 更新（続き）" in parts[1]
    assert sum(p.count("| PROJ-") for p in parts) == 199
