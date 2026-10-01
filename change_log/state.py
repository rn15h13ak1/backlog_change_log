"""その日の終わりの件名・担当者・種別・状態を、現在の値とその後の変更から逆算する。

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


def _name(issue: dict, key: str) -> str:
    """課題の応答から、担当者・種別・状態などの名前を取り出す"""
    return ((issue.get(key) or {}).get("name") or "") if isinstance(issue.get(key), dict) else ""


def _end_of_day(own: list[Event], issue: dict | None, field_name: str, issue_key: str,
                cutoff: datetime, empty: str) -> str:
    """
    changes の field_name で表される値の、cutoff 時点の値。

    その日より後の変更 → 現在の課題 → （後日削除された課題なら）その日までの最後の変更、の順に求める。
    どれでも分からなければ UNKNOWN。値が空なら empty。
    """
    later, value = _value_at(own, field_name, cutoff)
    if later:
        return value or empty
    if issue is not None:
        return _name(issue, issue_key) or empty
    known, value = _last_known(own, field_name, cutoff)
    return (value or empty) if known else UNKNOWN


def resolve_states(changes: Iterable[IssueChange], events: list[Event],
                   current: dict[int, dict], cutoff: datetime) -> None:
    """
    IssueChange の件名・担当者・種別・状態を、cutoff 時点の値で埋める（削除は件名だけ既に入っている）。

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

        ch.assignee = _end_of_day(own, issue, "assigner", "assignee", cutoff, UNASSIGNED)
        # 種別・状態は空にならない（必ずどれかが付く）。空なら分からないものとして扱う
        ch.issue_type = _end_of_day(own, issue, "issueType", "issueType", cutoff, UNKNOWN)
        ch.status = _end_of_day(own, issue, "status", "status", cutoff, UNKNOWN)
