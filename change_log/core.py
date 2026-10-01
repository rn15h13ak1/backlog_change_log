"""定数と、日時の小物。ほかのモジュールはここだけに依存する。"""
from datetime import date, datetime, time, timedelta, timezone
from pathlib import Path

#: リポジトリの根。`config.yaml` と `.env` を、実行位置ではなくここを基準に探す。
REPO_ROOT = Path(__file__).resolve().parent.parent

# Backlog API は UTC で日時を返す。日の区切りは JST で判定する。
JST = timezone(timedelta(hours=9))

API_TIMEOUT = 30        # 1 リクエストのタイムアウト（秒）
API_MAX_RETRIES = 3     # GET の一時的な失敗に対する最大リトライ回数
API_PAGE_SIZE = 100     # Backlog API の 1 回あたりの最大取得件数
RETRYABLE_STATUS = {429, 500, 502, 503, 504}
RETRY_MAX_DELAY = 60.0  # リトライ 1 回あたりの最大待機秒数

#: 補って出力する日数の上限。これより古い日は出力しない（警告だけ出す）。
MAX_CATCHUP_DAYS = 7

#: 1 件のコメントに載せる本文の上限（文字数）。Backlog の上限は公開されていないため、
#: 余裕を持たせた値にしている。超える日は複数のコメントに分ける。
MAX_COMMENT_CHARS = 20000

# アクティビティの種別
ACT_CREATED = 1
ACT_UPDATED = 2
ACT_COMMENTED = 3
ACT_DELETED = 4
ACT_MULTI_UPDATED = 14
TARGET_ACTIVITY_TYPES = [ACT_CREATED, ACT_UPDATED, ACT_COMMENTED, ACT_DELETED, ACT_MULTI_UPDATED]


def parse_api_datetime(value: str) -> datetime:
    """API の日時（例: 2026-09-30T01:23:45Z）を、タイムゾーン付きの datetime にする"""
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def day_start(d: date) -> datetime:
    """JST でのその日の 0:00"""
    return datetime.combine(d, time.min, tzinfo=JST)


def jst_date(dt: datetime) -> date:
    """日時を JST の日付にする"""
    return dt.astimezone(JST).date()
