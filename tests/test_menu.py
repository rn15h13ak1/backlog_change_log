"""対話メニューのテスト。input と subprocess を差し替え、本体は実行しない。"""
import builtins
import json

import pytest

import backlog_change_log as entry
import check_api
import menu


@pytest.fixture
def answers(monkeypatch):
    """input に順に返す答えを積む"""
    queue: list[str] = []

    def fake_input(prompt=""):
        if not queue:
            raise EOFError
        return queue.pop(0)

    monkeypatch.setattr(builtins, "input", fake_input)
    return queue


@pytest.fixture
def history_file(tmp_path, monkeypatch):
    path = tmp_path / "history.json"
    monkeypatch.setattr(menu, "HISTORY_PATH", path)
    return path


@pytest.fixture
def runs(monkeypatch):
    """run_script に渡されたもの（本体は実行しない）"""
    calls: list[tuple] = []
    monkeypatch.setattr(menu, "run_script", lambda script, args: calls.append((script.name, args)) or 0)
    return calls


# ---------------- 表示・入力 ----------------

def test_print_menu_returns_choice(answers, capsys):
    answers += ["x", "9", "2"]
    assert menu.print_menu("t", ["a", "b"]) == 2
    assert capsys.readouterr().out.count("無効な入力") == 2


def test_print_menu_default_and_back(answers, capsys):
    answers += ["", "0"]
    assert menu.print_menu("t", ["a", "b"], default=2, default_mark="前回") == 2
    assert "2. b ←前回" in capsys.readouterr().out
    assert menu.print_menu("t", ["a"]) == 0


def test_print_menu_without_default_reprompts_on_empty(answers):
    answers += ["", "1"]
    assert menu.print_menu("t", ["a"]) == 1


@pytest.mark.parametrize("answer,expected", [("y", True), ("YES", True), ("", False), ("n", False), ("はい", False)])
def test_confirm(answers, answer, expected):
    answers.append(answer)
    assert menu.confirm("?") is expected


# ---------------- 引数 ----------------

def test_build_args():
    assert menu.build_args(menu.ACTION_DRY_RUN) == ["--dry-run"]
    assert menu.build_args(menu.ACTION_POST) == []
    assert menu.build_args(menu.ACTION_CHECK, days=30) == ["--days", "30"]
    assert menu.build_args(menu.ACTION_POST, config_path="c.yaml") == ["--config", "c.yaml"]


def test_built_args_are_accepted_by_the_tools():
    """メニューが組み立てた引数を、本体の引数解析がそのまま受け付ける"""
    args = entry.build_parser().parse_args(menu.build_args(menu.ACTION_DRY_RUN, config_path="c.yaml"))
    assert args.dry_run and args.config == "c.yaml"
    args = entry.build_parser().parse_args(menu.build_args(menu.ACTION_POST))
    assert not args.dry_run
    args = check_api.build_parser().parse_args(menu.build_args(menu.ACTION_CHECK, days=90))
    assert args.days == 90


def test_script_for():
    assert menu.script_for(menu.ACTION_CHECK).name == "check_api.py"
    assert menu.script_for(menu.ACTION_POST).name == "backlog_change_log.py"


def test_scripts_exist():
    assert menu.MAIN_SCRIPT.is_file() and menu.CHECK_SCRIPT.is_file()


def test_exit_meanings_cover_runner_codes():
    from change_log import runner
    for code in (runner.EXIT_OK, runner.EXIT_FAILED, runner.EXIT_DAYS_NOT_OUTPUT, runner.EXIT_ALREADY_RUNNING):
        assert "想定外" not in menu.describe_exit(menu.ACTION_POST, code)
    assert "想定外" in menu.describe_exit(menu.ACTION_POST, 99)
    assert "前提と違う応答があります" in menu.describe_exit(menu.ACTION_CHECK, 1)


# ---------------- 操作 ----------------

def test_dry_run_runs_without_confirmation(answers, history_file, runs):
    assert menu.run_action(menu.ACTION_DRY_RUN, "確認", "c.yaml", {}) == 0
    assert runs == [("backlog_change_log.py", ["--config", "c.yaml", "--dry-run"])]


def test_post_needs_confirmation(answers, history_file, runs, capsys):
    answers.append("n")
    assert menu.run_action(menu.ACTION_POST, "記録", "c.yaml", {}) is None
    assert runs == []
    assert "投稿しませんでした" in capsys.readouterr().out
    answers.append("y")
    assert menu.run_action(menu.ACTION_POST, "記録", "c.yaml", {}) == 0
    assert runs == [("backlog_change_log.py", ["--config", "c.yaml"])]


def test_check_asks_days_and_remembers(answers, history_file, runs):
    history: dict = {}
    answers.append("2")   # 30 日
    menu.run_action(menu.ACTION_CHECK, "応答", "", history)
    assert runs == [("check_api.py", ["--days", "30"])]
    assert json.loads(history_file.read_text(encoding="utf-8")) == {"check_days": 30, "action": "check"}
    answers.append("")    # 前回の 30 日が既定
    menu.run_action(menu.ACTION_CHECK, "応答", "", history)
    assert runs[-1] == ("check_api.py", ["--days", "30"])


def test_check_back_returns_none(answers, history_file, runs):
    answers.append("0")
    assert menu.run_action(menu.ACTION_CHECK, "応答", "", {}) is None
    assert runs == []


def test_broken_history_is_ignored(history_file):
    history_file.write_text("{壊れた", encoding="utf-8")
    assert menu.load_history() == {}
    history_file.write_text("[1, 2]", encoding="utf-8")
    assert menu.load_history() == {}


def test_main_does_not_default_to_post(answers, history_file, runs, monkeypatch, tmp_path, capsys):
    """前回が「記録する」でも、Enter だけで投稿へ進まない"""
    history_file.write_text(json.dumps({"action": "post"}), encoding="utf-8")
    monkeypatch.setattr(menu.sys, "argv", ["menu.py", "--config", str(tmp_path / "none.yaml")])
    answers += ["", "0"]   # 既定が無いので空 Enter は無効 → 0 で終了
    with pytest.raises(SystemExit) as e:
        menu.main()
    assert e.value.code == 0
    assert runs == []
    assert "←前回" not in capsys.readouterr().out


def test_main_runs_and_shows_exit_meaning(answers, history_file, runs, monkeypatch, tmp_path, capsys):
    monkeypatch.setattr(menu.sys, "argv", ["menu.py", "--config", str(tmp_path / "none.yaml")])
    answers += ["1", "", "0"]
    with pytest.raises(SystemExit):
        menu.main()
    out = capsys.readouterr().out
    assert runs and runs[0][1][-1] == "--dry-run"
    assert "終了コード: 0（正常終了）" in out


def test_main_eof_exits_1(answers, history_file, monkeypatch, tmp_path):
    monkeypatch.setattr(menu.sys, "argv", ["menu.py", "--config", str(tmp_path / "none.yaml")])
    with pytest.raises(SystemExit) as e:
        menu.main()
    assert e.value.code == menu.EXIT_EOF


# ---------------- 設定の表示 ----------------

def _config(tmp_path, body):
    p = tmp_path / "config.yaml"
    p.write_text(body, encoding="utf-8")
    return str(p)


def test_describe_setup(tmp_path):
    path = _config(tmp_path, 'backlog:\n  space_host: "x.backlog.com"\n'
                             'target:\n  issue_key: "ABC-1"\n  project_keys: [ABC, OTHER]\n')
    (tmp_path / ".env").write_text("BACKLOG_API_KEY=real-secret\n", encoding="utf-8")
    lines = menu.describe_setup(path, env={})
    assert lines == ["接続先    : x.backlog.com", "記録先    : ABC-1", "追跡      : ABC, OTHER", "API キー  : 設定済み"]
    assert "real-secret" not in "".join(lines)


def test_describe_setup_shows_what_is_missing(tmp_path, monkeypatch):
    from change_log import config
    monkeypatch.setattr(config, "REPO_ROOT", tmp_path / "repo")
    monkeypatch.chdir(tmp_path)
    path = _config(tmp_path, 'backlog:\n  space_host: "yourcompany.backlog.com"\ntarget: {}\n')
    lines = menu.describe_setup(path, env={})
    assert "※ backlog.space_host が未設定です" in lines[0]
    assert "※ target.issue_key が未設定です" in lines[1]
    assert lines[2] == "追跡      : 記録先の課題のプロジェクト"
    assert "※ 見つかりません" in lines[3]


def test_describe_setup_without_file(tmp_path):
    assert "設定ファイルがありません" in menu.describe_setup(str(tmp_path / "none.yaml"))[0]
    assert "内容が空" in menu.describe_setup(_config(tmp_path, ""))[0]
    assert "読めません" in menu.describe_setup(_config(tmp_path, "a: [b"))[0]


def test_describe_setup_finds_api_key_in_config(tmp_path, monkeypatch):
    from change_log import config
    monkeypatch.setattr(config, "REPO_ROOT", tmp_path / "repo")
    monkeypatch.chdir(tmp_path)
    path = _config(tmp_path, 'backlog:\n  space_host: "x.backlog.com"\n  api_key: "secret-in-config"\n'
                             'target:\n  issue_key: "ABC-1"\n')
    lines = menu.describe_setup(path, env={})
    assert lines[3] == "API キー  : 設定済み"
    assert "secret-in-config" not in "".join(lines)
