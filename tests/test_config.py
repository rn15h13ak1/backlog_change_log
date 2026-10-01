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


def _write(tmp_path, target_extra=""):
    p = tmp_path / "config.yaml"
    p.write_text('backlog:\n  space_host: "x.backlog.com"\n'
                 f'target:\n  issue_key: "ABC-12"\n{target_extra}', encoding="utf-8")
    return str(p)


def test_project_keys_default_to_empty(tmp_path):
    assert load_config(_write(tmp_path), api_key="k").project_keys == []


def test_project_keys_are_read(tmp_path):
    cfg = load_config(_write(tmp_path, "  project_keys: [ABC, OTHER]\n"), api_key="k")
    assert cfg.project_keys == ["ABC", "OTHER"]


@pytest.mark.parametrize("value", ['"ABC"', "[ABC, 1]", '[ABC, ""]', "{a: 1}"])
def test_project_keys_must_be_a_list_of_keys(tmp_path, value, capsys):
    with pytest.raises(SystemExit):
        load_config(_write(tmp_path, f"  project_keys: {value}\n"), api_key="k")
    assert "プロジェクトキーの一覧" in capsys.readouterr().err


def test_project_keys_must_not_repeat(tmp_path, capsys):
    with pytest.raises(SystemExit):
        load_config(_write(tmp_path, "  project_keys: [ABC, OTHER, ABC]\n"), api_key="k")
    assert "重複しています: ABC" in capsys.readouterr().err


def test_config_errors_exit_with_2(tmp_path):
    """設定の誤りは、API のエラー（1）と区別して 2 で止める"""
    with pytest.raises(SystemExit) as e:
        load_config(str(tmp_path / "none.yaml"), api_key="k")
    assert e.value.code == 2
