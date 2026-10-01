"""同じ記録先への同時実行を防ぐロック。

2 つの実行が同時に「出力済みの最新の日」を読むと、同じ日を二重に投稿しうる。記録先ごとに
ロックファイルを取り、取れなければ実行しない。

ロックは OS のファイルロック（fcntl / msvcrt）で取るため、プロセスが異常終了しても残らない。
同じ端末の中でしか効かない（別の端末からの同時実行は防げない）。
"""
import hashlib
import os
import sys
import tempfile
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path


class AlreadyRunning(Exception):
    """同じ記録先に対する実行が、すでに動いている"""


def lock_path(space_host: str, issue_key: str, directory: Path | None = None) -> Path:
    """記録先ごとのロックファイルの場所（一時フォルダ）。リポジトリには置かない"""
    digest = hashlib.sha256(f"{space_host}/{issue_key}".encode()).hexdigest()[:16]
    return (directory or Path(tempfile.gettempdir())) / f"backlog_change_log-{digest}.lock"


def _try_lock(fd: int) -> bool:
    if sys.platform == "win32":
        import msvcrt
        try:
            msvcrt.locking(fd, msvcrt.LK_NBLCK, 1)
            return True
        except OSError:
            return False
    import fcntl
    try:
        fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        return True
    except OSError:
        return False


def _unlock(fd: int) -> None:
    if sys.platform == "win32":
        import msvcrt
        os.lseek(fd, 0, os.SEEK_SET)
        msvcrt.locking(fd, msvcrt.LK_UNLCK, 1)
    else:
        import fcntl
        fcntl.flock(fd, fcntl.LOCK_UN)


@contextmanager
def single_run(path: Path) -> Iterator[None]:
    """path のロックを取る。取れなければ AlreadyRunning"""
    fd = os.open(path, os.O_RDWR | os.O_CREAT, 0o600)
    try:
        if not _try_lock(fd):
            raise AlreadyRunning(str(path))
        try:
            yield
        finally:
            _unlock(fd)
    finally:
        os.close(fd)
