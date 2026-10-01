"""Backlog API クライアント。

通信・リトライ・エラーの整形は backlog_report の client を基にしている。
コメントの投稿（POST）は冪等でないため再送しない。通信断や 5xx の後に再送すると、
投稿済みだった場合に同じコメントが二重に残る（excel_to_backlog と同じ判断）。
"""
import json
import random
import ssl
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from collections.abc import Iterator
from typing import Any

from change_log.core import (
    API_MAX_RETRIES,
    API_PAGE_SIZE,
    API_TIMEOUT,
    RETRY_MAX_DELAY,
    RETRYABLE_STATUS,
)


class BacklogAPIError(Exception):
    """Backlog API 呼び出しの失敗を表す例外"""

    def __init__(self, endpoint: str, status_code: int | None = None,
                 detail: str = "", raw_body: str = ""):
        self.endpoint = endpoint
        self.status_code = status_code
        self.detail = detail
        self.raw_body = raw_body
        super().__init__(f"{endpoint} (HTTP {status_code})" if status_code else f"{endpoint}: {detail}")


def format_api_error(err: BacklogAPIError) -> str:
    """BacklogAPIError を利用者向けの日本語メッセージに整形する（API キーを含む URL は出さない）"""
    if err.status_code is None:
        lines = [f"エラー: API へ接続できませんでした: {err.endpoint}"]
        if err.detail:
            lines.append(f"  詳細: {err.detail}")
        lines.append("  → space_host / base_path / ネットワーク接続を確認してください。")
        return "\n".join(lines)

    lines = [f"エラー: API 呼び出しに失敗しました（HTTP {err.status_code}）: {err.endpoint}"]
    if err.detail:
        lines.append(f"  詳細: {err.detail}")
    elif err.raw_body:
        lines.append(f"  レスポンス: {err.raw_body[:500]}")

    if err.status_code == 401:
        lines.append("  → API キー（BACKLOG_API_KEY）を確認してください。")
    elif err.status_code == 403:
        lines.append("  → API キーの権限を確認してください。")
    elif err.status_code == 404:
        lines.append("  → space_host / base_path / target.issue_key / target.project_keys を確認してください。")
    elif err.status_code in RETRYABLE_STATUS:
        lines.append(f"  → リトライ（{API_MAX_RETRIES} 回）しても回復しませんでした。時間をおいて再実行してください。")
    return "\n".join(lines)


def _flatten_params(params: dict) -> list[tuple[str, str]]:
    """リストの値を `key[]=v` の並びに展開する"""
    pairs: list[tuple[str, str]] = []
    for key, value in params.items():
        if isinstance(value, list):
            pairs.extend((f"{key}[]", str(v)) for v in value)
        else:
            pairs.append((key, str(value)))
    return pairs


class BacklogClient:
    def __init__(self, space_host: str, api_key: str, ssl_verify: bool = True,
                 base_path: str = "", debug: bool = False):
        base_path = "/" + base_path.strip("/") if base_path.strip("/") else ""
        self.base_url = f"https://{space_host}{base_path}/api/v2"
        self.api_key = api_key
        self.debug = debug
        if ssl_verify:
            self.ssl_context: ssl.SSLContext | None = None
        else:
            self.ssl_context = ssl.create_default_context()
            self.ssl_context.check_hostname = False
            self.ssl_context.verify_mode = ssl.CERT_NONE

    # ---------------- 低レベル HTTP ----------------

    def _url(self, endpoint: str, params: dict | None = None) -> str:
        pairs = _flatten_params(params or {})
        pairs.append(("apiKey", self.api_key))
        return f"{self.base_url}{endpoint}?" + urllib.parse.urlencode(pairs)

    def _debug(self, method: str, endpoint: str, params: dict | None) -> None:
        if self.debug:
            shown = urllib.parse.urlencode(_flatten_params(params or {}))
            print(f"  [DEBUG] {method} {endpoint} ?{shown}", file=sys.stderr)

    @staticmethod
    def _to_api_error(e: urllib.error.HTTPError, endpoint: str) -> BacklogAPIError:
        detail = ""
        raw_body = ""
        try:
            raw_body = e.read().decode("utf-8")
            errors = json.loads(raw_body).get("errors", [])
            if errors:
                detail = " / ".join(f"{err.get('message', '')}（code={err.get('code')}）" for err in errors)
        except Exception:
            pass
        return BacklogAPIError(endpoint, status_code=e.code, detail=detail, raw_body=raw_body)

    def _sleep_before_retry(self, attempt: int, retry_after: str | None) -> None:
        """指数バックオフ。Retry-After ヘッダがあればそれを下回らない"""
        base = 2 ** attempt
        if retry_after:
            try:
                base = max(base, min(float(retry_after), 60.0))
            except ValueError:
                pass
        delay = min(base + random.uniform(0, base / 2), RETRY_MAX_DELAY)
        if self.debug:
            print(f"  [DEBUG] {delay:.1f} 秒待機してリトライします（{attempt + 1}/{API_MAX_RETRIES}）",
                  file=sys.stderr)
        time.sleep(delay)

    def _open(self, req: urllib.request.Request) -> Any:
        with urllib.request.urlopen(req, timeout=API_TIMEOUT, context=self.ssl_context) as res:
            return json.loads(res.read().decode("utf-8"))

    def _get(self, endpoint: str, params: dict | None = None) -> Any:
        """GET。429 / 5xx / 接続エラーは最大 API_MAX_RETRIES 回リトライする"""
        self._debug("GET", endpoint, params)
        url = self._url(endpoint, params)
        for attempt in range(API_MAX_RETRIES + 1):
            try:
                return self._open(urllib.request.Request(url))
            except urllib.error.HTTPError as e:
                retry_after = e.headers.get("Retry-After") if e.headers else None
                err = self._to_api_error(e, endpoint)
                if err.status_code in RETRYABLE_STATUS and attempt < API_MAX_RETRIES:
                    self._sleep_before_retry(attempt, retry_after)
                    continue
                raise err from None
            except (urllib.error.URLError, TimeoutError) as e:
                if attempt < API_MAX_RETRIES:
                    self._sleep_before_retry(attempt, None)
                    continue
                raise BacklogAPIError(endpoint, detail=str(getattr(e, "reason", e))) from None
        raise BacklogAPIError(endpoint, detail="リトライ上限に達しました")

    def _post(self, endpoint: str, params: dict) -> Any:
        """POST。冪等でないため再送しない"""
        self._debug("POST", endpoint, None)
        body = urllib.parse.urlencode(_flatten_params(params)).encode("utf-8")
        req = urllib.request.Request(
            self._url(endpoint), data=body, method="POST",
            headers={"Content-Type": "application/x-www-form-urlencoded"},
        )
        try:
            return self._open(req)
        except urllib.error.HTTPError as e:
            raise self._to_api_error(e, endpoint) from None
        except (urllib.error.URLError, TimeoutError) as e:
            raise BacklogAPIError(endpoint, detail=str(getattr(e, "reason", e))) from None

    # ---------------- エンドポイント ----------------

    def get_myself(self) -> dict:
        """API キーの持ち主"""
        return self._get("/users/myself")

    def get_issue(self, issue_id_or_key: str | int) -> dict:
        return self._get(f"/issues/{issue_id_or_key}")

    def get_project(self, project_id_or_key: str | int) -> dict:
        return self._get(f"/projects/{project_id_or_key}")

    def iter_comments_desc(self, issue_id_or_key: str | int) -> Iterator[dict]:
        """課題のコメントを新しい順に返す。必要な分だけページを読む"""
        max_id: int | None = None
        while True:
            params: dict = {"count": API_PAGE_SIZE, "order": "desc"}
            if max_id is not None:
                params["maxId"] = max_id
            comments = self._get(f"/issues/{issue_id_or_key}/comments", params)
            yield from comments
            if len(comments) < API_PAGE_SIZE:
                return
            max_id = min(c["id"] for c in comments) - 1

    def iter_activities_desc(self, project_id: int, activity_type_ids: list[int]) -> Iterator[dict]:
        """プロジェクトのアクティビティを新しい順に返す。必要な分だけページを読む"""
        max_id: int | None = None
        while True:
            params: dict = {"activityTypeId": activity_type_ids, "count": API_PAGE_SIZE, "order": "desc"}
            if max_id is not None:
                params["maxId"] = max_id
            activities = self._get(f"/projects/{project_id}/activities", params)
            yield from activities
            if len(activities) < API_PAGE_SIZE:
                return
            max_id = min(a["id"] for a in activities) - 1

    def get_issues_by_ids(self, project_id: int, issue_ids: list[int]) -> list[dict]:
        """課題 ID を指定してまとめて取得する（削除済みの課題は返らない）"""
        found: list[dict] = []
        for i in range(0, len(issue_ids), API_PAGE_SIZE):
            chunk = issue_ids[i:i + API_PAGE_SIZE]
            found.extend(self._get("/issues", {"projectId": [project_id], "id": chunk, "count": API_PAGE_SIZE}))
        return found

    def add_comment(self, issue_id_or_key: str | int, content: str) -> dict:
        return self._post(f"/issues/{issue_id_or_key}/comments", {"content": content})
