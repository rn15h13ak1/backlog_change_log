"""通しの処理。API の呼び出しはクライアント経由に限り、テストでは偽のクライアントを渡す。"""
import sys
from datetime import date, datetime, timedelta
from typing import Protocol, TextIO

from change_log.collect import Event, fetch_activities, summarize_day, to_events
from change_log.core import ACT_CREATED, JST, MAX_CATCHUP_DAYS, TARGET_ACTIVITY_TYPES, day_start, jst_date
from change_log.marker import decide_target_dates, find_latest_recorded
from change_log.render import BACKLOG, MARKDOWN, render_day
from change_log.state import resolve_states


class Client(Protocol):
    def get_myself(self) -> dict: ...
    def get_issue(self, issue_id_or_key: str | int) -> dict: ...
    def get_project(self, project_id_or_key: str | int) -> dict: ...
    def iter_comments_desc(self, issue_id_or_key: str | int): ...
    def iter_activities_desc(self, project_id: int, activity_type_ids: list[int]): ...
    def get_issues_by_ids(self, project_id: int, issue_ids: list[int]) -> list[dict]: ...
    def add_comment(self, issue_id_or_key: str | int, content: str) -> dict: ...


def _fmt_dates(days: list[date]) -> str:
    if len(days) == 1:
        return days[0].isoformat()
    return f"{days[0].isoformat()}〜{days[-1].isoformat()}"


def _render(d: date, start: datetime, end: datetime, events: list[Event], current: dict[int, dict],
            project_key: str, fmt: str, **kwargs) -> list[str]:
    changes = summarize_day(events, start, end)
    resolve_states(changes, events, current, end)
    return render_day(d, project_key, changes, fmt, **kwargs)


#: 終了コード。1 は投稿や API の失敗、2 は実行環境の不足（change_log.runtime）
EXIT_OK = 0
EXIT_FAILED = 1
EXIT_DAYS_NOT_OUTPUT = 3   # 出力しなかった日がある（上限超え・遡りきれない・形の違う応答）
EXIT_ALREADY_RUNNING = 4   # 同じ記録先への実行が、すでに動いている（change_log.lock）


def run(client: Client, issue_key: str, *, now: datetime | None = None,
        dry_run: bool = False, out: TextIO = sys.stdout, err: TextIO = sys.stderr) -> int:
    """
    終了コードを返す。

    出力しなかった日があれば EXIT_DAYS_NOT_OUTPUT を返す。警告を表示するだけだと、定期実行で
    誰も見ないまま記録が抜けるため。投稿に失敗したときは EXIT_FAILED を優先する。
    """
    now = (now or datetime.now(JST)).astimezone(JST)
    today = now.date()

    myself = client.get_myself()
    record = client.get_issue(issue_key)
    project = client.get_project(record["projectId"])
    project_id = project["id"]
    project_key = project["projectKey"]
    fmt = MARKDOWN if project.get("textFormattingRule") == "markdown" else BACKLOG
    print(f"記録先: {record['issueKey']} {record.get('summary', '')}（記法: {fmt}）", file=out)

    # 1〜2. 出力済みの最新の日と、出力する日
    latest = find_latest_recorded(client.iter_comments_desc(record["id"]), myself["id"])
    dates, skipped = decide_target_dates(latest, today)
    print(f"出力済みの最新の日: {latest.isoformat() if latest else 'なし（初回）'}", file=out)
    not_output = bool(skipped)
    if skipped:
        print(f"⚠ {_fmt_dates(skipped)} は上限 {MAX_CATCHUP_DAYS} 日を超えたため出力しません。", file=err)

    # 3. 変更を取る（出力する最初の日の 0:00 まで。無ければ当日の 0:00 まで）
    since = day_start(dates[0]) if dates else day_start(today)
    fetched = fetch_activities(client.iter_activities_desc(project_id, TARGET_ACTIVITY_TYPES), since)
    all_events, malformed = to_events(fetched.activities)
    events = [ev for ev in all_events if ev.issue_id != record["id"]]

    # ページの端まで読んでも since に届かなかった場合、プロジェクトの履歴がそこで
    # 終わっているのか、取得できる範囲の外にあるのかは区別できない。記録先の課題の
    # 作成が見えていれば、少なくともそこまでの履歴は揃っているとみなす。
    record_created_seen = any(ev.type_id == ACT_CREATED and ev.issue_id == record["id"] for ev in all_events)
    if not fetched.reached and not record_created_seen:
        # 取得できる範囲の端に達した。それより前に始まる日は不完全かもしれないので出力しない
        limit = fetched.oldest or now
        incomplete = [d for d in dates if day_start(d) < limit]
        if incomplete:
            print(f"⚠ {_fmt_dates(incomplete)} はアクティビティを遡りきれず、不完全な可能性があるため"
                  "出力しません。", file=err)
            dates = [d for d in dates if d not in incomplete]
            not_output = True

    # 形の違うアクティビティがあった日は、変更が欠けているので出力しない。
    # 日時も読めなかったものがあれば、どの日のものか分からないため、すべての日を止める。
    if malformed:
        print(f"⚠ 想定と違う形のアクティビティが {len(malformed)} 件あり、読み飛ばしました"
              "（check_api.py で応答の形を確かめてください）。", file=err)
        if None in malformed:
            broken_days = list(dates)
        else:
            broken_dates = {jst_date(t) for t in malformed if t is not None}
            broken_days = [d for d in dates if d in broken_dates]
        if broken_days:
            print(f"⚠ {_fmt_dates(broken_days)} は変更が欠けている可能性があるため出力しません。", file=err)
            dates = [d for d in dates if d not in broken_days]
            not_output = True

    # 4〜5. 担当者・件名の逆算に使う、現在の課題
    issue_ids = sorted({ev.issue_id for ev in events})
    current = {i["id"]: i for i in client.get_issues_by_ids(project_id, issue_ids)} if issue_ids else {}

    # 6. 古い日から 1 日ずつ投稿する
    if not dates:
        print("コメントに出力する日はありません。", file=out)
    for d in dates:
        start, end = day_start(d), day_start(d + timedelta(days=1))
        bodies = _render(d, start, end, events, current, project_key, fmt)
        if dry_run:
            for body in bodies:
                print(f"\n===== {d.isoformat()} に投稿するコメント（--dry-run のため投稿しません）=====", file=out)
                print(body, file=out)
            continue
        for body in bodies:
            try:
                client.add_comment(record["id"], body)
            except Exception as e:  # noqa: BLE001 - どの失敗でも残りの日は次回に回す
                print(f"エラー: {d.isoformat()} のコメントの投稿に失敗しました: {e}", file=err)
                print("  残りの日は次回の実行で出力されます。", file=err)
                return EXIT_FAILED
        print(f"{d.isoformat()} のコメントを投稿しました。", file=out)

    # 7. 当日分は標準出力のみ
    note = f"（0:00〜{now.strftime('%H:%M')} 時点）"
    today_bodies = _render(today, day_start(today), now, events, current, project_key, fmt,
                           title_note=note, with_marker=False, max_chars=10**9)
    print("\n===== 当日の変更（コメントには書きません）=====", file=out)
    print(today_bodies[0], file=out)
    return EXIT_DAYS_NOT_OUTPUT if not_output else EXIT_OK
