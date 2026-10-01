import pytest

from change_log.config import load_config, resolve_api_key


def test_api_key_from_env_wins(tmp_path):
    (tmp_path / ".env").write_text("BACKLOG_API_KEY=from-dotenv\n", encoding="utf-8")
    assert resolve_api_key({"BACKLOG_API_KEY": "from-env"}, tmp_path / ".env") == "from-env"


def test_api_key_from_dotenv(tmp_path):
    (tmp_path / ".env").write_text("# memo\nBACKLOG_API_KEY='abc'\n", encoding="utf-8")
    assert resolve_api_key({}, tmp_path / ".env") == "abc"


def test_api_key_missing_or_placeholder(tmp_path):
    (tmp_path / ".env").write_text("BACKLOG_API_KEY=YOUR_API_KEY_HERE\n", encoding="utf-8")
    with pytest.raises(SystemExit):
        resolve_api_key({}, tmp_path / ".env")


def test_example_config_is_rejected_until_edited(tmp_path):
    from change_log.core import REPO_ROOT
    with pytest.raises(SystemExit):
        load_config(str(REPO_ROOT / "config.example.yaml"), api_key="k")


def test_config_loads(tmp_path):
    p = tmp_path / "config.yaml"
    p.write_text('backlog:\n  space_host: "x.backlog.com"\ntarget:\n  issue_key: "ABC-12"\n', encoding="utf-8")
    cfg = load_config(str(p), api_key="k")
    assert (cfg.space_host, cfg.issue_key, cfg.ssl_verify, cfg.base_path) == ("x.backlog.com", "ABC-12", True, "")
