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

    def h4(self, text: str) -> str:
        return f"#### {text}" if self.fmt == MARKDOWN else f"**** {text}"

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


#: 1 つのプロジェクトの、1 日分の変更（プロジェクトキー, 変更）
ProjectChanges = tuple[str, list[IssueChange]]


def render_day(d: date, groups: list[ProjectChanges], fmt: str,
               *, title_note: str = "", with_marker: bool = True,
               max_chars: int = MAX_COMMENT_CHARS) -> list[str]:
    """
    1 日分のコメント本文を返す。max_chars を超える場合は複数に分ける。

    プロジェクトが 1 つなら、プロジェクトの見出しを付けない（複数対応の前と同じ形）。
    複数なら、対象のプロジェクトを並べ、プロジェクトごとに見出しを分ける。

    目印は最後の 1 件にだけ付ける。途中で投稿に失敗しても、その日は次回に
    丸ごと出し直される（前半は重複するが、抜けはしない）。
    """
    syn = _Syntax(fmt)
    multi = len(groups) > 1
    all_changes = [c for _, changes in groups for c in changes]
    title = f"{d.isoformat()} の課題の変更{title_note}"
    footer = ["", syn.rule(), marker_line(d)] if with_marker else []
    intro = [syn.h2(title), ""]
    if multi:
        intro += [f"対象: {', '.join(key for key, _ in groups)}", ""]

    if not all_changes:
        return ["\n".join([*intro, "変更はありませんでした。", *footer])]

    # (継続時に繰り返す見出し, 表の見出し, 行) の並びに平らにする
    parts: list[list[str]] = []
    current: list[str] = [*intro, _counts_line(all_changes)]
    budget = max_chars - len("\n".join(footer)) - 40  # 見出しの「（続き）」の分を残す
    section_h = syn.h4 if multi else syn.h3

    def size(lines: list[str]) -> int:
        return len("\n".join(lines))

    def flush(restart: list[str]) -> None:
        nonlocal current
        parts.append(current)
        current = [syn.h2(title), *restart]

    for project_key, changes in groups:
        project_head: list[str] = []
        if multi:
            project_head = ["", syn.h3(project_key)]
            body = [*project_head, "", _counts_line(changes) if changes else "変更はありませんでした。"]
            if size(current + body) > budget and len(current) > 1:
                flush([])
            current.extend(body)
        for sec in build_sections(project_key, changes):
            head = ["", section_h(sec.title), "", *syn.table_head(sec.columns)]
            if size(current + head) > budget and len(current) > 1:
                flush(project_head)
            current.extend(head)
            for row in sec.rows:
                line = syn.row(row)
                if size(current + [line]) > budget:
                    flush([*project_head, "", section_h(f"{sec.title}（続き）"), "", *syn.table_head(sec.columns)])
                current.append(line)
    parts.append(current)

    if len(parts) > 1:
        for i, lines in enumerate(parts, start=1):
            lines[0] = syn.h2(f"{title}（{i}/{len(parts)}）")
    parts[-1].extend(footer)
    return ["\n".join(lines) for lines in parts]
