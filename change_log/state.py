"""その日の終わりの件名・担当者を、現在の値とその後の変更から逆算する。

現在の値から始めて、その日より後に起きた変更を新しい方から「変更前の値」へ
戻していくのと同じことを、**その日より後で最初に起きた変更の変更前の値**を
取ることで行う。その日より後に変更が無ければ、現在の値がそのまま答えになる。
"""
from collections.abc import Iterable
from datetime import datetime

from change_log.collect import Event, IssueChange

UNASSIGNED = "未設定"
UNKNOWN = "不明"


def _value_at(events: list[Event], field_name: str, cutoff: datetime) -> tuple[bool, str]:
    """
    cutoff 時点の値を、出来事の changes から求める。

    - cutoff より後で最初に field が変わった出来事があれば、その変更前の値
    - 無ければ (False, "")（現在の値を使う）
    """
    for ev in events:  # 古い順
        if ev.created < cutoff:
            continue
        for c in ev.changes:
            if c.get("field") == field_name:
                return True, c.get("old_value") or ""
    return False, ""


def _last_known(events: list[Event], field_name: str, cutoff: datetime) -> tuple[bool, str]:
    """cutoff より前で最後に field が変わった出来事の、変更後の値"""
    found = False
    value = ""
    for ev in events:
        if ev.created >= cutoff:
            break
        for c in ev.changes:
            if c.get("field") == field_name:
                found, value = True, c.get("new_value") or ""
    return found, value


def resolve_states(changes: Iterable[IssueChange], events: list[Event],
                   current: dict[int, dict], cutoff: datetime) -> None:
    """
    IssueChange の件名・担当者を、cutoff 時点の値で埋める（削除は件名だけ既に入っている）。

    current: 課題 ID → 現在の課題（GET /issues の応答）。削除済みの課題は含まれない。
    """
    for ch in changes:
        if ch.kind == "deleted":
            continue
        own = [ev for ev in events if ev.issue_id == ch.issue_id]  # 古い順
        issue = current.get(ch.issue_id)

        later, value = _value_at(own, "summary", cutoff)
        if later:
            ch.summary = value
        elif issue is not None:
            ch.summary = issue.get("summary") or ""
        else:
            # 後日に削除された課題。出来事に残っている最後の件名を使う
            ch.summary = next((ev.summary for ev in reversed(own) if ev.summary), "")

        later, value = _value_at(own, "assigner", cutoff)
        if later:
            ch.assignee = value or UNASSIGNED
        elif issue is not None:
            ch.assignee = (issue.get("assignee") or {}).get("name") or UNASSIGNED
        else:
            known, value = _last_known(own, "assigner", cutoff)
            ch.assignee = (value or UNASSIGNED) if known else UNKNOWN
