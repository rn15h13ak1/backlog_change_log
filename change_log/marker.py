"""目印（`対象日: YYYY-MM-DD`）の書式、出力済みの最新の日の探索、出力する日の決定。"""
import re
from collections.abc import Iterable
from datetime import date, timedelta

from change_log.core import MAX_CATCHUP_DAYS

MARKER_PREFIX = "対象日: "
_MARKER_RE = re.compile(r"^対象日: (\d{4}-\d{2}-\d{2})\s*$", re.MULTILINE)


def marker_line(d: date) -> str:
    return f"{MARKER_PREFIX}{d.isoformat()}"


def parse_marker(content: str | None) -> date | None:
    """コメント本文から目印の日付を取り出す。複数あれば最後のもの"""
    found = _MARKER_RE.findall(content or "")
    if not found:
        return None
    try:
        return date.fromisoformat(found[-1])
    except ValueError:
        return None


def find_latest_recorded(comments_desc: Iterable[dict], my_user_id: int) -> date | None:
    """
    新しい順のコメントから、自分が投稿した目印付きのコメントを探し、その日付を返す。

    最初の 1 件で止める（それより古いコメントは読まない）。日を古い順に投稿して
    いるため、最も新しい目印が出力済みの最新の日になる。
    """
    for comment in comments_desc:
        if (comment.get("createdUser") or {}).get("id") != my_user_id:
            continue
        recorded = parse_marker(comment.get("content"))
        if recorded is not None:
            return recorded
    return None


def decide_target_dates(latest: date | None, today: date) -> tuple[list[date], list[date]]:
    """
    コメントに出力する日と、上限を超えて出力しない日を返す（どちらも古い順）。

    - 初回（latest が無い）は前日だけ
    - 2 回目からは latest の翌日から前日まで
    - MAX_CATCHUP_DAYS 日を超える分は古い方を出力しない
    """
    yesterday = today - timedelta(days=1)
    if latest is None:
        return [yesterday], []

    days: list[date] = []
    d = latest + timedelta(days=1)
    while d <= yesterday:
        days.append(d)
        d += timedelta(days=1)

    if len(days) > MAX_CATCHUP_DAYS:
        return days[-MAX_CATCHUP_DAYS:], days[:-MAX_CATCHUP_DAYS]
    return days, []
