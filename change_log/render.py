"""コメント本文の生成と分割。マークダウンと Backlog 記法の 2 種類を出せる。"""
from dataclasses import dataclass
from datetime import date

from change_log.collect import IssueChange
from change_log.core import MAX_COMMENT_CHARS
from change_log.marker import marker_line

MARKDOWN = "markdown"
BACKLOG = "backlog"


@dataclass
class Section:
    title: str
    columns: list[str]
    rows: list[list[str]]


def _cell(text: str) -> str:
    """表のセルを壊す文字を置き換える"""
    return (text or "").replace("|", "｜").replace("\r", " ").replace("\n", " ").strip() or "-"


def _issue_key(project_key: str, ch: IssueChange) -> str:
    return f"{project_key}-{ch.key_id}" if ch.key_id is not None else f"(ID {ch.issue_id})"


def build_sections(project_key: str, changes: list[IssueChange]) -> list[Section]:
    created = [c for c in changes if c.kind == "created"]
    updated = [c for c in changes if c.kind == "updated"]
    deleted = [c for c in changes if c.kind == "deleted"]
    sections = []
    if created:
        sections.append(Section("作成", ["課題", "件名", "担当者"], [
            [_issue_key(project_key, c), c.summary, c.assignee or ""] for c in created
        ]))
    if updated:
        sections.append(Section("更新", ["課題", "件名", "変更した項目", "担当者"], [
            [_issue_key(project_key, c), c.summary, "、".join(c.fields), c.assignee or ""] for c in updated
        ]))
    if deleted:
        sections.append(Section("削除", ["課題", "件名"], [
            [_issue_key(project_key, c), c.summary + ("（当日作成）" if c.created_same_day else "")]
            for c in deleted
        ]))
    return sections


def _counts_line(changes: list[IssueChange]) -> str:
    n = {k: sum(1 for c in changes if c.kind == k) for k in ("created", "updated", "deleted")}
    return f"作成 {n['created']} 件 / 更新 {n['updated']} 件 / 削除 {n['deleted']} 件"


class _Syntax:
    def __init__(self, fmt: str):
        self.fmt = fmt

    def h2(self, text: str) -> str:
        return f"## {text}" if self.fmt == MARKDOWN else f"** {text}"

    def h3(self, text: str) -> str:
        return f"### {text}" if self.fmt == MARKDOWN else f"*** {text}"

    def table_head(self, columns: list[str]) -> list[str]:
        if self.fmt == MARKDOWN:
            return ["| " + " | ".join(columns) + " |", "|" + "---|" * len(columns)]
        return ["|" + "|".join(columns) + "|h"]

    def row(self, cells: list[str]) -> str:
        cells = [_cell(c) for c in cells]
        if self.fmt == MARKDOWN:
            return "| " + " | ".join(cells) + " |"
        return "|" + "|".join(cells) + "|"

    def rule(self) -> str:
        return "---" if self.fmt == MARKDOWN else "----"


def render_day(d: date, project_key: str, changes: list[IssueChange], fmt: str,
               *, title_note: str = "", with_marker: bool = True,
               max_chars: int = MAX_COMMENT_CHARS) -> list[str]:
    """
    1 日分のコメント本文を返す。max_chars を超える場合は複数に分ける。

    目印は最後の 1 件にだけ付ける。途中で投稿に失敗しても、その日は次回に
    丸ごと出し直される（前半は重複するが、抜けはしない）。
    """
    syn = _Syntax(fmt)
    title = f"{d.isoformat()} の課題の変更{title_note}"
    footer = ["", syn.rule(), marker_line(d)] if with_marker else []

    if not changes:
        return ["\n".join([syn.h2(title), "", "変更はありませんでした。", *footer])]

    sections = build_sections(project_key, changes)
    parts: list[list[str]] = []
    current: list[str] = [syn.h2(title), "", _counts_line(changes)]
    budget = max_chars - len("\n".join(footer)) - 40  # 見出しの「（続き）」の分を残す

    def size(lines: list[str]) -> int:
        return len("\n".join(lines))

    for sec in sections:
        head = ["", syn.h3(sec.title), "", *syn.table_head(sec.columns)]
        if size(current + head) > budget and len(current) > 1:
            parts.append(current)
            current = [syn.h2(title)]
        current.extend(head)
        for row in sec.rows:
            line = syn.row(row)
            if size(current + [line]) > budget:
                parts.append(current)
                current = [syn.h2(title), "", syn.h3(f"{sec.title}（続き）"), "", *syn.table_head(sec.columns)]
            current.append(line)
    parts.append(current)

    if len(parts) > 1:
        for i, lines in enumerate(parts, start=1):
            lines[0] = syn.h2(f"{title}（{i}/{len(parts)}）")
    parts[-1].extend(footer)
    return ["\n".join(lines) for lines in parts]
