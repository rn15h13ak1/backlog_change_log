"""API クライアントのテスト。urlopen を差し替え、実際には通信しない。"""
import io
import json
import urllib.error
import urllib.parse

import pytest

from change_log import client as client_module
from change_log.client import BacklogAPIError, BacklogClient, format_api_error

SECRET = "SECRET-KEY-123"


class FakeResponse:
    def __init__(self, body):
        self._body = json.dumps(body).encode("utf-8")

    def read(self):
        return self._body

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


def http_error(code, body=None, headers=None):
    raw = json.dumps(body or {"errors": [{"message": "だめ", "code": 7}]}).encode("utf-8")
    return urllib.error.HTTPError("https://x", code, "err", headers or {}, io.BytesIO(raw))


@pytest.fixture
def calls(monkeypatch):
    """urlopen に順に返すもの（応答 or 例外）を積む。呼ばれた Request は requests に残る"""
    state = {"queue": [], "requests": []}

    def fake_urlopen(req, timeout=None, context=None):
        state["requests"].append(req)
        item = state["queue"].pop(0)
        if isinstance(item, Exception):
            raise item
        return FakeResponse(item)

    monkeypatch.setattr(client_module.urllib.request, "urlopen", fake_urlopen)
    monkeypatch.setattr(client_module.time, "sleep", lambda s: None)
    return state


def _client(**kwargs):
    return BacklogClient("example.backlog.com", SECRET, **kwargs)


def _query(req):
    return urllib.parse.parse_qs(urllib.parse.urlsplit(req.full_url).query)


def test_get_retries_on_server_error_then_succeeds(calls):
    calls["queue"] = [http_error(503), urllib.error.URLError("切断"), {"id": 1}]
    assert _client().get_myself() == {"id": 1}
    assert len(calls["requests"]) == 3


def test_get_gives_up_after_max_retries(calls):
    calls["queue"] = [http_error(429)] * (client_module.API_MAX_RETRIES + 1)
    with pytest.raises(BacklogAPIError) as e:
        _client().get_myself()
    assert e.value.status_code == 429
    assert len(calls["requests"]) == client_module.API_MAX_RETRIES + 1


def test_get_does_not_retry_client_error(calls):
    calls["queue"] = [http_error(404)]
    with pytest.raises(BacklogAPIError) as e:
        _client().get_issue("PROJ-1")
    assert e.value.status_code == 404 and "だめ（code=7）" in e.value.detail
    assert len(calls["requests"]) == 1


@pytest.mark.parametrize("failure", [http_error(503), urllib.error.URLError("切断"), TimeoutError()])
def test_post_is_never_retried(calls, failure):
    """投稿済みかもしれない POST を再送すると、同じコメントが二重に残る"""
    calls["queue"] = [failure, {"id": 99}]
    with pytest.raises(BacklogAPIError):
        _client().add_comment(1000, "本文")
    assert len(calls["requests"]) == 1


def test_post_sends_content_in_body_not_url(calls):
    calls["queue"] = [{"id": 99}]
    _client().add_comment(1000, "対象日: 2026-09-30")
    req = calls["requests"][0]
    assert req.get_method() == "POST"
    assert urllib.parse.parse_qs(req.data.decode("utf-8")) == {"content": ["対象日: 2026-09-30"]}
    assert "content" not in _query(req)


def test_activities_paginate_with_max_id_and_stop_on_short_page(calls):
    page1 = [{"id": i} for i in range(300, 200, -1)]  # 100 件
    page2 = [{"id": 200}, {"id": 199}]
    calls["queue"] = [page1, page2]
    got = list(_client().iter_activities_desc(10, [1, 2]))
    assert [a["id"] for a in got] == [a["id"] for a in page1 + page2]
    first, second = (_query(r) for r in calls["requests"])
    assert "maxId" not in first and second["maxId"] == ["200"]
    assert first["activityTypeId[]"] == ["1", "2"] and first["order"] == ["desc"]


def test_activities_are_read_lazily(calls):
    """呼び出し側が途中で止めれば、次のページは取りに行かない"""
    calls["queue"] = [[{"id": i} for i in range(100, 0, -1)]]
    it = _client().iter_activities_desc(10, [1])
    next(it)
    assert len(calls["requests"]) == 1


def test_comments_paginate_with_max_id(calls):
    calls["queue"] = [[{"id": i} for i in range(500, 400, -1)], []]
    assert len(list(_client().iter_comments_desc(1000))) == 100
    assert _query(calls["requests"][1])["maxId"] == ["400"]


def test_issues_by_ids_are_chunked(calls):
    calls["queue"] = [[{"id": 1}], [{"id": 2}]]
    got = _client().get_issues_by_ids(10, list(range(1, 151)))
    assert got == [{"id": 1}, {"id": 2}]
    assert [len(_query(r)["id[]"]) for r in calls["requests"]] == [100, 50]


def test_base_path_is_normalized(calls):
    calls["queue"] = [{}]
    _client(base_path="/backlog/").get_myself()
    assert calls["requests"][0].full_url.startswith("https://example.backlog.com/backlog/api/v2/users/myself?")


def test_api_key_never_appears_in_debug_or_errors(calls, capsys):
    calls["queue"] = [http_error(401)]
    with pytest.raises(BacklogAPIError) as e:
        _client(debug=True).get_myself()
    printed = capsys.readouterr()
    assert SECRET not in printed.out + printed.err
    assert SECRET not in str(e.value) + format_api_error(e.value)
    assert "BACKLOG_API_KEY" in format_api_error(e.value)
