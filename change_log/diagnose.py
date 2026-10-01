"""実際のスペースの応答で、本ツールが置いている前提を確かめる（読み取りだけ。投稿はしない）。

確かめる前提:
- 担当者・状態・種別の変更が、アクティビティの changes[].field に `assigner` / `status` / `issueType`
  として現れること（その日の終わりの値の逆算に使う）
- コメントが content.comment.content に入ること
- 一括更新（種別 14）が content.link[] と content.changes[] を持つこと
- 作成・更新・コメント・削除が content.id / key_id / summary を持つこと

課題の件名やコメントの本文は表示しない。表示するのは項目名と件数だけ。
"""
import sys
from collections import Counter
from datetime import datetime, timedelta
from typing import TextIO

from change_log.client import BacklogAPIError
from change_log.collect import FIELD_LABELS, activity_created
from change_log.core import (
    ACT_COMMENTED,
    ACT_CREATED,
    ACT_DELETED,
    ACT_MULTI_UPDATED,
    ACT_UPDATED,
    JST,
    MAX_COMMENT_CHARS,
    TARGET_ACTIVITY_TYPES,
)
from change_log.marker import find_latest_recorded
from change_log.runner import Client

TYPE_NAMES = {
    ACT_CREATED: "作成",
    ACT_UPDATED: "更新",
    ACT_COMMENTED: "コメント",
    ACT_DELETED: "削除",
    ACT_MULTI_UPDATED: "一括更新",
}
SINGLE_ISSUE_KEYS = ("id", "key_id", "summary")

#: その日の終わりの値を逆算する項目（changes[].field の名前, 表示名）
REVERSED_FIELDS = (("assigner", "担当者"), ("status", "状態"), ("issueType", "種別"))


def diagnose(client: Client, issue_key: str, *, project_keys: list[str] | None = None,
             now: datetime | None = None, days: int = 7,
             max_activities: int = 1000, out: TextIO = sys.stdout) -> int:
    """終了コードを返す（0: 前提どおり、1: 前提と違う応答があった）"""
    now = (now or datetime.now(JST)).astimezone(JST)
    since = now - timedelta(days=days)
    problems: list[str] = []
    notes: list[str] = []

    def p(text: str = "") -> None:
        print(text, file=out)

    # 接続と記録先
    myself = client.get_myself()
    p(f"API キーの持ち主: {myself.get('name', '?')}（ID {myself.get('id')}）")
    record = client.get_issue(issue_key)
    project = client.get_project(record["projectId"])
    rule = project.get("textFormattingRule")
    p(f"記録先の課題: {record.get('issueKey')}（ID {record.get('id')}）")
    p(f"記録先のプロジェクト: {project.get('projectKey')}（ID {project.get('id')}、記法: {rule}）")
    if rule not in ("markdown", "backlog"):
        problems.append(f"記法 textFormattingRule が想定外の値です: {rule!r}（Backlog 記法として扱います）")

    latest = find_latest_recorded(client.iter_comments_desc(record["id"]), myself["id"])
    p(f"出力済みの最新の日: {latest.isoformat() if latest else 'なし（初回の扱いになります）'}")
    p()

    # アクティビティ（追跡するプロジェクトごとに読み、判定は合算で行う）
    keys = list(project_keys or [project["projectKey"]])
    type_counts: Counter[int] = Counter()
    field_counts: Counter[str] = Counter()
    comment_with_text = 0
    missing_keys: Counter[str] = Counter()
    multi_shapes: list[str] = []
    for key in keys:
        try:
            target = project if key == project.get("projectKey") else client.get_project(key)
        except BacklogAPIError as e:
            problems.append(f"追跡するプロジェクト {key} を取得できません（{e}）")
            continue
        read = 0
        oldest: datetime | None = None
        reached = False
        own_types: Counter[int] = Counter()
        for act in client.iter_activities_desc(target["id"], TARGET_ACTIVITY_TYPES):
            created = activity_created(act)
            if created is None:
                missing_keys["created（日時）"] += 1
                continue
            if created < since:
                reached = True
                break
            if read >= max_activities:
                break
            read += 1
            oldest = created
            type_id = act.get("type")
            type_counts[type_id] += 1
            own_types[type_id] += 1
            content = act.get("content") or {}

            if type_id == ACT_MULTI_UPDATED:
                links = content.get("link")
                if not isinstance(links, list) or not all("id" in link for link in links):
                    missing_keys["一括更新の content.link[].id"] += 1
                if not isinstance(content.get("changes"), list):
                    missing_keys["一括更新の content.changes"] += 1
                if len(multi_shapes) < 1:
                    link_keys = sorted({k for link in (links or []) for k in link})
                    multi_shapes.append(f"content: {sorted(content)} / link[]: {link_keys}")
            else:
                for k in SINGLE_ISSUE_KEYS:
                    if k not in content:
                        missing_keys[f"{TYPE_NAMES.get(type_id, type_id)}の content.{k}"] += 1

            for c in content.get("changes") or []:
                if c.get("field"):
                    field_counts[c["field"]] += 1
            if ((content.get("comment") or {}).get("content") or "").strip():
                comment_with_text += 1

        p(f"アクティビティ（{target.get('projectKey')}、ID {target.get('id')}）: 直近 {days} 日分を {read} 件読みました"
          + ("" if reached else f"（{'上限' if read >= max_activities else '履歴の端'}で止まりました）"))
        if oldest:
            p(f"  最も古いもの: {oldest.astimezone(JST).strftime('%Y-%m-%d %H:%M')}")
        for type_id in TARGET_ACTIVITY_TYPES:
            p(f"  {TYPE_NAMES[type_id]}（種別 {type_id}）: {own_types.get(type_id, 0)} 件")
    p(f"本文のあるコメント（content.comment.content）: {comment_with_text} 件")
    p()

    p("変更された項目（changes[].field）:")
    if not field_counts:
        p("  （ありません）")
    for name, count in field_counts.most_common():
        label = FIELD_LABELS.get(name)
        shown = f"→ {label}" if label else "→ そのまま表示（カスタム属性なら正しい）"
        p(f"  {name}: {count} 件 {shown}")
    p()

    # 前提ごとの判定
    p("前提の確認:")
    for field_name, label in REVERSED_FIELDS:
        if field_counts.get(field_name):
            p(f"  OK {label}の変更は `{field_name}` として返っています")
        else:
            notes.append(f"{label}の変更が期間内に 1 件もありませんでした。`{field_name}` で返るかは確かめられて"
                         f"いません。--days を延ばすか、{label}を変えてから再実行してください")
    if type_counts.get(ACT_COMMENTED) or comment_with_text:
        if comment_with_text:
            p("  OK コメントの本文は content.comment.content に入っています")
        else:
            problems.append("コメントのアクティビティはあるのに、content.comment.content に本文がありません")
    else:
        notes.append("コメントが期間内に 1 件もなく、コメントの形は確かめられていません")
    if type_counts.get(ACT_MULTI_UPDATED):
        p(f"  OK 一括更新の形: {multi_shapes[0]}")
    else:
        notes.append("一括更新が期間内に 1 件もなく、その形は確かめられていません")
    for what, count in missing_keys.items():
        problems.append(f"{what} が無いアクティビティが {count} 件あります")
    notes.append(f"コメントの文字数の上限は、読み取りだけでは確かめられません（本ツールは "
                 f"{MAX_COMMENT_CHARS} 字で分けています）")

    for line in notes:
        p(f"  - {line}")
    for line in problems:
        p(f"  NG {line}")
    p()
    p("結果: " + ("前提と違う応答があります" if problems else "前提と違う応答はありませんでした"))
    return 1 if problems else 0
