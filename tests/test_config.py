import pytest

from change_log import config as config_module
from change_log.config import load_config, resolve_api_key


@pytest.fixture
def places(tmp_path, monkeypatch):
    """設定ファイルの場所・リポジトリ直下・作業ディレクトリを、別々の一時フォルダにする"""
    dirs = {name: tmp_path / name for name in ("conf", "repo", "cwd")}
    for d in dirs.values():
        d.mkdir()
    monkeypatch.setattr(config_module, "REPO_ROOT", dirs["repo"])
    return dirs


def _resolve(places, env=None):
    return resolve_api_key(env or {}, config_path=places["conf"] / "config.yaml", cwd=places["cwd"])


def _dotenv(d, value):
    (d / ".env").write_text(f"# memo\nBACKLOG_API_KEY='{value}'\n", encoding="utf-8")


def test_api_key_from_env_wins(places):
    _dotenv(places["conf"], "from-dotenv")
    assert _resolve(places, {"BACKLOG_API_KEY": "from-env"}) == "from-env"


def test_dotenv_next_to_config_comes_first(places):
    for name in ("conf", "repo", "cwd"):
        _dotenv(places[name], name)
    assert _resolve(places) == "conf"


def test_dotenv_falls_back_to_repo_then_cwd(places):
    _dotenv(places["cwd"], "cwd")
    assert _resolve(places) == "cwd"
    _dotenv(places["repo"], "repo")
    assert _resolve(places) == "repo"


def test_placeholder_is_skipped(places):
    _dotenv(places["conf"], "YOUR_API_KEY_HERE")
    _dotenv(places["cwd"], "real")
    assert _resolve(places, {"BACKLOG_API_KEY": "YOUR_API_KEY_HERE"}) == "real"


def test_api_key_missing_lists_searched_places(places, capsys):
    with pytest.raises(SystemExit):
        _resolve(places)
    err = capsys.readouterr().err
    assert all(str(places[n] / ".env") in err for n in ("conf", "repo", "cwd"))


def test_same_place_is_listed_once(places):
    from change_log.config import dotenv_candidates
    assert len(dotenv_candidates(places["repo"] / "config.yaml", places["repo"])) == 1


def test_example_config_is_rejected_until_edited(tmp_path):
    from change_log.core import REPO_ROOT
    with pytest.raises(SystemExit):
        load_config(str(REPO_ROOT / "config.example.yaml"), api_key="k")


def test_config_loads(tmp_path):
    p = tmp_path / "config.yaml"
    p.write_text('backlog:\n  space_host: "x.backlog.com"\ntarget:\n  issue_key: "ABC-12"\n', encoding="utf-8")
    cfg = load_config(str(p), api_key="k")
    assert (cfg.space_host, cfg.issue_key, cfg.ssl_verify, cfg.base_path) == ("x.backlog.com", "ABC-12", True, "")
