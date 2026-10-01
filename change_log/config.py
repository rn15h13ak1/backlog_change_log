"""設定ファイルと API キーの読み込み。

API キーは設定ファイルに書かない（規約 C「設定ファイル」）。環境変数
BACKLOG_API_KEY か、リポジトリ直下の `.env` から読む。
"""
import os
import sys
from collections.abc import Mapping
from dataclasses import dataclass, field
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
    #: 追跡するプロジェクトのキー。空なら記録先の課題のプロジェクトだけを追跡する
    project_keys: list[str] = field(default_factory=list)


#: 設定の誤りで止めるときの終了コード。実行する前に人が直すものなので、実行環境の不足
#: （change_log.runtime）と同じ 2 にする。1 は API / ネットワークのエラーに使う。
EXIT_CONFIG = 2


def _fail(message: str) -> None:
    print(f"エラー: {message}", file=sys.stderr)
    sys.exit(EXIT_CONFIG)


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


def dotenv_candidates(config_path: Path | None = None, cwd: Path | None = None) -> list[Path]:
    """
    .env を探す場所（重複は除く）。

    設定ファイルと同じ場所 → リポジトリ直下 → 作業ディレクトリ。設定ファイルを別の場所に
    置いたとき、その隣の .env が読まれないと気付きにくいため、まずそこを見る（backlog_issue_sheet
    と同じ順）。リポジトリ直下は、従来の置き場所として残す。
    """
    places = [config_path.resolve().parent] if config_path else []
    places += [REPO_ROOT, (cwd or Path.cwd()).resolve()]
    seen: list[Path] = []
    for place in places:
        candidate = place / ".env"
        if candidate not in seen:
            seen.append(candidate)
    return seen


def find_api_key(env: Mapping[str, str] | None = None, config_path: Path | None = None,
                 cwd: Path | None = None) -> str | None:
    """環境変数 → .env（dotenv_candidates の順）で探す。例の値のままのものは無いものとして扱う"""
    source: Mapping[str, str] = os.environ if env is None else env
    key = source.get(API_KEY_ENV, "")
    if key and key not in PLACEHOLDERS:
        return key
    for path in dotenv_candidates(config_path, cwd):
        key = read_dotenv(path).get(API_KEY_ENV, "")
        if key and key not in PLACEHOLDERS:
            return key
    return None


def resolve_api_key(env: Mapping[str, str] | None = None, config_path: Path | None = None,
                    cwd: Path | None = None) -> str:
    """find_api_key と同じ順で探し、見つからなければ探した場所を表示して終了する"""
    key = find_api_key(env, config_path, cwd)
    if key:
        return key
    places = "\n".join(f"    {path}" for path in dotenv_candidates(config_path, cwd))
    _fail(f"API キーがありません。環境変数 {API_KEY_ENV} か、次のいずれかの .env に設定してください:\n{places}")
    return ""  # _fail は終了する


def _project_keys(raw: object) -> list[str]:
    """target.project_keys を検証する。省略・空は空のリスト（記録先のプロジェクトだけを追跡）"""
    if raw is None:
        return []
    if not isinstance(raw, list) or not all(isinstance(k, str) and k.strip() for k in raw):
        _fail("config.yaml の target.project_keys は、プロジェクトキーの一覧で書いてください（例: [PROJ, OTHER]）")
        return []  # _fail は終了する
    keys = [str(k).strip() for k in raw]
    duplicated = sorted({k for k in keys if keys.count(k) > 1})
    if duplicated:
        _fail(f"config.yaml の target.project_keys に同じキーが重複しています: {', '.join(duplicated)}")
    return keys


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

    project_keys = _project_keys(target.get("project_keys"))

    return Config(
        project_keys=project_keys,
        space_host=space_host,
        base_path=str(backlog.get("base_path") or ""),
        ssl_verify=bool(backlog.get("ssl_verify", True)),
        issue_key=issue_key,
        api_key=api_key if api_key is not None else resolve_api_key(config_path=p),
    )
