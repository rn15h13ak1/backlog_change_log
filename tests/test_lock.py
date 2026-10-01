import subprocess
import sys
import textwrap

import pytest

from change_log.core import REPO_ROOT
from change_log.lock import AlreadyRunning, lock_path, single_run


def test_lock_path_is_per_record_issue(tmp_path):
    a = lock_path("x.backlog.com", "PROJ-1", tmp_path)
    assert a == lock_path("x.backlog.com", "PROJ-1", tmp_path)
    assert a != lock_path("x.backlog.com", "PROJ-2", tmp_path)
    assert a != lock_path("y.backlog.com", "PROJ-1", tmp_path)
    assert a.parent == tmp_path


def test_second_lock_in_same_process_is_refused(tmp_path):
    path = tmp_path / "t.lock"
    with single_run(path):
        with pytest.raises(AlreadyRunning):
            with single_run(path):
                pass
    with single_run(path):   # 解放後は取れる
        pass


def test_lock_is_refused_from_another_process(tmp_path):
    """別のプロセスが持っている間は取れない（実際の同時実行に近い形で確かめる）"""
    path = tmp_path / "t.lock"
    holder = subprocess.Popen([sys.executable, "-c", textwrap.dedent(f"""
        import sys, time
        sys.path.insert(0, {str(REPO_ROOT)!r})
        from change_log.lock import single_run
        from pathlib import Path
        with single_run(Path({str(path)!r})):
            print('locked', flush=True)
            sys.stdin.readline()
    """)], stdin=subprocess.PIPE, stdout=subprocess.PIPE, text=True)
    try:
        assert holder.stdout.readline().strip() == "locked"
        with pytest.raises(AlreadyRunning):
            with single_run(path):
                pass
    finally:
        holder.communicate("\n", timeout=10)
    with single_run(path):   # 相手が終われば取れる
        pass


def test_main_refuses_when_already_running(tmp_path, monkeypatch, capsys):
    import backlog_change_log as entry
    from change_log import lock

    config = tmp_path / "config.yaml"
    config.write_text('backlog:\n  space_host: "x.backlog.com"\ntarget:\n  issue_key: "ABC-1"\n', encoding="utf-8")
    monkeypatch.setenv("BACKLOG_API_KEY", "dummy")
    monkeypatch.setattr(lock.tempfile, "gettempdir", lambda: str(tmp_path))
    monkeypatch.setattr(entry, "run", lambda *a, **k: pytest.fail("ロック中に run を呼んだ"))

    with single_run(lock_path("x.backlog.com", "ABC-1", tmp_path)):
        assert entry.main(["--config", str(config)]) == 4
    assert "すでに実行中" in capsys.readouterr().err

    # --dry-run は投稿しないのでロックを取らない
    called = []
    monkeypatch.setattr(entry, "run", lambda *a, **k: called.append(k) or 0)
    with single_run(lock_path("x.backlog.com", "ABC-1", tmp_path)):
        assert entry.main(["--config", str(config), "--dry-run"]) == 0
    assert called == [{"project_keys": [], "dry_run": True}]
