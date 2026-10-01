"""アクティビティの取得、課題ごとの出来事への展開、日ごとの集約。"""
from collections.abc import Iterable
from dataclasses import dataclass, field
from datetime import datetime

from change_log.core import (
    ACT_COMMENTED,
    ACT_CREATED,
    ACT_DELETED,
    ACT_MULTI_UPDATED,
    ACT_UPDATED,
    parse_api_datetime,
)

#: アクティビティの changes[].field を、画面での項目名に読み替える。
#: ここに無いもの（カスタム属性など）は、返ってきた名前をそのまま使う。
FIELD_LABELS = {
    "summary": "件名",
    "description": "詳細",
    "status": "状態",
    "assigner": "担当者",
    "issueType": "種別",
    "priority": "優先度",
    "startDate": "開始日",
    "limitDate": "期限日",
    "estimatedHours": "予定時間",
    "actualHours": "実績時間",
    "component": "カテゴリー",
    "version": "発生バージョン",
    "milestone": "マイルストーン",
    "resolution": "完了理由",
    "parentIssue": "親課題",
    "attachment": "添付ファイル",
    "sharedFile": "共有ファイル",
}

COMMENT_LABEL = "コメント"


@dataclass
class Event:
    """1 つの課題に起きた 1 つの出来事（一括更新は課題ごとに分ける）"""
    issue_id: int
    key_id: int | None
    summary: str
    type_id: int
    created: datetime
    fields: list[str]                       # 変わった項目名（画面の名前）
    changes: list[dict] = field(default_factory=list)  # 生の changes（値の逆算に使う）


@dataclass
class FetchResult:
    activities: list[dict]
    reached: bool                 # since まで遡れたか
    oldest: datetime | None       # 取得できた最も古いアクティビティの日時


def fetch_activities(activities_desc: Iterable[dict], since: datetime) -> FetchResult:
    """
    新しい順のアクティビティを、since より前に達するまで読む。

    ページの終わりまで読んでも since に届かなかった場合は reached=False を返す。
    それより前の日は、取得できる範囲の外にある可能性がある（不完全かもしれない）。
    """
    collected: list[dict] = []
    oldest: datetime | None = None
    for act in activities_desc:
        created = parse_api_datetime(act["created"])
        if created < since:
            return FetchResult(collected, True, oldest)
        collected.append(act)
        oldest = created
    return FetchResult(collected, False, oldest)


def _labels(changes: list[dict], comment: dict | None) -> list[str]:
    labels = [FIELD_LABELS.get(c.get("field", ""), c.get("field", "")) for c in changes if c.get("field")]
    if comment and (comment.get("content") or "").strip():
        labels.append(COMMENT_LABEL)
    return labels


def to_events(activities: Iterable[dict]) -> list[Event]:
    """アクティビティを課題ごとの出来事に展開する（古い順）"""
    events: list[Event] = []
    for act in activities:
        type_id = act.get("type")
        content = act.get("content") or {}
        created = parse_api_datetime(act["created"])

        if type_id == ACT_MULTI_UPDATED:
            changes = content.get("changes") or []
            for link in content.get("link") or []:
                comment = link.get("comment") or content.get("comment")
                events.append(Event(
                    issue_id=link["id"], key_id=link.get("key_id"), summary=link.get("title") or "",
                    type_id=ACT_UPDATED, created=created,
                    fields=_labels(changes, comment), changes=changes,
                ))
            continue

        if type_id not in (ACT_CREATED, ACT_UPDATED, ACT_COMMENTED, ACT_DELETED):
            continue
        changes = (content.get("changes") or []) if type_id == ACT_UPDATED else []
        if type_id == ACT_COMMENTED:
            fields = [COMMENT_LABEL]
        elif type_id == ACT_UPDATED:
            fields = _labels(changes, content.get("comment"))
        else:
            fields = []
        events.append(Event(
            issue_id=content["id"], key_id=content.get("key_id"), summary=content.get("summary") or "",
            type_id=ACT_UPDATED if type_id == ACT_COMMENTED else type_id, created=created,
            fields=fields, changes=changes,
        ))

    events.sort(key=lambda e: e.created)
    return events


@dataclass
class IssueChange:
    """1 日のうちの、1 つの課題の変更のまとめ"""
    issue_id: int
    key_id: int | None
    kind: str                      # "created" / "updated" / "deleted"
    fields: list[str]              # 更新のときだけ使う。最初に変わった順、重複なし
    summary: str = ""              # 削除のときは削除時点の件名。それ以外は後で埋める
    assignee: str | None = None    # 後で埋める（削除では使わない）
    created_same_day: bool = False


def summarize_day(events: Iterable[Event], start: datetime, end: datetime) -> list[IssueChange]:
    """[start, end) の出来事を課題ごとにまとめる"""
    by_issue: dict[int, IssueChange] = {}
    for ev in events:
        if not (start <= ev.created < end):
            continue
        ch = by_issue.get(ev.issue_id)
        if ch is None:
            ch = by_issue[ev.issue_id] = IssueChange(ev.issue_id, ev.key_id, "updated", [])
        if ev.key_id is not None:
            ch.key_id = ev.key_id
        if ev.type_id == ACT_CREATED:
            ch.kind = "created"
            ch.created_same_day = True
        elif ev.type_id == ACT_DELETED:
            ch.kind = "deleted"
            ch.summary = ev.summary
        for label in ev.fields:
            if label not in ch.fields:
                ch.fields.append(label)
    return sorted(by_issue.values(), key=lambda c: (c.key_id is None, c.key_id or 0, c.issue_id))
