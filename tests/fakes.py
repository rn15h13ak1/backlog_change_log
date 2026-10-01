"""テスト用の偽の API 応答と、偽のクライアント。"""
from datetime import datetime, timezone

from change_log.client import BacklogAPIError
from change_log.core import JST

PROJECT_ID = 10
PROJECT_KEY = "PROJ"
RECORD_ID = 1000
ME = 7


def utc(jst_text: str) -> str:
    """JST の 'YYYY-MM-DD HH:MM' を、API と同じ UTC の文字列にする"""
    dt = datetime.strptime(jst_text, "%Y-%m-%d %H:%M").replace(tzinfo=JST)
    return dt.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


_next_id = [0]


def _aid() -> int:
    _next_id[0] += 1
    return _next_id[0]


def act(type_id: int, when: str, content: dict) -> dict:
    return {"id": _aid(), "type": type_id, "created": utc(when), "content": content}


def created(when: str, issue_id: int, key_id: int, summary: str) -> dict:
    return act(1, when, {"id": issue_id, "key_id": key_id, "summary": summary})


def updated(when: str, issue_id: int, key_id: int, summary: str,
            changes: list[dict] | None = None, comment: str = "") -> dict:
    return act(2, when, {"id": issue_id, "key_id": key_id, "summary": summary,
                         "changes": changes or [], "comment": {"id": 1, "content": comment}})


def commented(when: str, issue_id: int, key_id: int, summary: str) -> dict:
    return act(3, when, {"id": issue_id, "key_id": key_id, "summary": summary,
                         "comment": {"id": 1, "content": "コメント本文"}})


def deleted(when: str, issue_id: int, key_id: int, summary: str) -> dict:
    return act(4, when, {"id": issue_id, "key_id": key_id, "summary": summary})


def change(field: str, old: str, new: str) -> dict:
    return {"field": field, "old_value": old, "new_value": new, "type": "standard"}


def issue(issue_id: int, key_id: int, summary: str, assignee: str | None,
          issue_type: str = "タスク", status: str = "処理中") -> dict:
    return {"id": issue_id, "issueKey": f"{PROJECT_KEY}-{key_id}", "summary": summary,
            "assignee": {"name": assignee} if assignee else None,
            "issueType": {"name": issue_type}, "status": {"name": status}}


def record_comment(content: str, user_id: int = ME) -> dict:
    return {"id": _aid(), "content": content, "createdUser": {"id": user_id}}


class FakeClient:
    def __init__(self, activities: list[dict], issues: list[dict], comments: list[dict] | None = None,
                 fmt: str = "markdown", fail_post_at: int | None = None,
                 other_projects: dict[str, tuple[int, list[dict], list[dict]]] | None = None):
        self.activities = activities          # 任意の順で渡してよい
        self.issues = {i["id"]: i for i in issues}
        self.comments = list(comments or [])  # 古い順
        self.fmt = fmt
        self.posted: list[str] = []
        self.fail_post_at = fail_post_at
        self.comments_read = 0
        # 記録先以外のプロジェクト: キー → (プロジェクト ID, アクティビティ, 現在の課題)
        self.other_projects = other_projects or {}
        self.activity_requests: list[int] = []
        for _, _, other_issues in self.other_projects.values():
            self.issues.update({i["id"]: i for i in other_issues})

    def get_myself(self) -> dict:
        return {"id": ME}

    def get_issue(self, issue_id_or_key):
        return {"id": RECORD_ID, "issueKey": f"{PROJECT_KEY}-1", "summary": "変更記録", "projectId": PROJECT_ID}

    def get_project(self, project_id_or_key):
        if project_id_or_key in (PROJECT_ID, PROJECT_KEY):
            return {"id": PROJECT_ID, "projectKey": PROJECT_KEY, "textFormattingRule": self.fmt}
        if project_id_or_key in self.other_projects:
            return {"id": self.other_projects[project_id_or_key][0], "projectKey": project_id_or_key,
                    "textFormattingRule": "markdown"}
        raise BacklogAPIError(f"/projects/{project_id_or_key}", status_code=404)

    def iter_comments_desc(self, issue_id_or_key):
        for c in reversed(self.comments):
            self.comments_read += 1
            yield c

    def iter_activities_desc(self, project_id, activity_type_ids):
        self.activity_requests.append(project_id)
        for pid, acts, _ in self.other_projects.values():
            if pid == project_id:
                yield from sorted(acts, key=lambda a: a.get("created") or "9999", reverse=True)
                return
        yield from sorted(self.activities, key=lambda a: a.get("created") or "9999", reverse=True)

    def get_issues_by_ids(self, project_id, issue_ids):
        return [self.issues[i] for i in issue_ids if i in self.issues]

    def add_comment(self, issue_id_or_key, content):
        if self.fail_post_at is not None and len(self.posted) == self.fail_post_at:
            raise RuntimeError("通信断")
        self.posted.append(content)
        self.comments.append(record_comment(content))
        return {}
