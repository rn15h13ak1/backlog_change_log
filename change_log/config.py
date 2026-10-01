"""設定ファイルと API キーの読み込み。

API キーは設定ファイルに書かない（規約 C「設定ファイル」）。環境変数
BACKLOG_API_KEY か、リポジトリ直下の `.env` から読む。
"""
import os
import sys
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path

import yaml

from change_log.core import REPO_ROOT

API_KEY_ENV = "BACKLOG_API_KEY"
PLACEHOLDERS = {"yourcompany.backlog.com", "PROJ-1", "YOUR_API_KEY_HERE"}


@dataclass
class Config:
    space_host: str
    base_path: str
    ssl_verify: bool
    issue_key: str
    api_key: str


def _fail(message: str) -> None:
    print(f"エラー: {message}", file=sys.stderr)
    sys.exit(1)


def read_dotenv(path: Path) -> dict[str, str]:
    """`KEY=VALUE` 形式の .env を読む（# の行と空行は無視、値の前後の引用符は外す）"""
    values: dict[str, str] = {}
    if not path.exists():
        return values
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        values[key.strip()] = value.strip().strip("'\"")
    return values


def resolve_api_key(env: Mapping[str, str] | None = None, dotenv_path: Path | None = None) -> str:
    source: Mapping[str, str] = os.environ if env is None else env
    key = source.get(API_KEY_ENV) or read_dotenv(dotenv_path or REPO_ROOT / ".env").get(API_KEY_ENV, "")
    if not key or key in PLACEHOLDERS:
        _fail(f"API キーがありません。環境変数 {API_KEY_ENV} か、.env に設定してください。")
    return key


def load_config(path: str, api_key: str | None = None) -> Config:
    p = Path(path)
    if not p.exists():
        _fail(f"設定ファイルが見つかりません: {path}（config.example.yaml をコピーして作成してください）")
    with open(p, encoding="utf-8") as f:
        raw = yaml.safe_load(f) or {}

    backlog = raw.get("backlog") or {}
    target = raw.get("target") or {}
    space_host = str(backlog.get("space_host") or "")
    issue_key = str(target.get("issue_key") or "")
    if not space_host or space_host in PLACEHOLDERS:
        _fail("config.yaml の backlog.space_host を設定してください")
    if not issue_key or issue_key in PLACEHOLDERS or "-" not in issue_key:
        _fail("config.yaml の target.issue_key を設定してください（例: MYPROJ-123）")

    return Config(
        space_host=space_host,
        base_path=str(backlog.get("base_path") or ""),
        ssl_verify=bool(backlog.get("ssl_verify", True)),
        issue_key=issue_key,
        api_key=api_key if api_key is not None else resolve_api_key(),
    )
