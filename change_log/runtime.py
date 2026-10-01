"""実行環境の確認。入口で、ほかのモジュールより先に呼ぶ。

ほかのモジュールは Python 3.10 以上の書き方（`str | None` など）を使っているため、
古い Python で読み込むと、何が足りないのか分からないエラーで落ちる。このファイルだけは
3.9 でも読める書き方に保ち、先に確かめて案内を出す。
"""
import importlib
import sys

MIN_PYTHON = (3, 10)

#: (import 名, pip でのパッケージ名)
REQUIRED_PACKAGES = (("yaml", "pyyaml"),)

#: 案内を出して止めるときの終了コード（backlog_report と揃える）
EXIT_ENVIRONMENT = 2


def check_runtime(version_info=None, importer=None):
    """足りないものを案内の文言で返す。足りていれば空のリスト"""
    version_info = sys.version_info if version_info is None else version_info
    importer = importlib.import_module if importer is None else importer

    if tuple(version_info[:2]) < MIN_PYTHON:
        need = ".".join(str(n) for n in MIN_PYTHON)
        have = ".".join(str(n) for n in version_info[:3])
        return [
            f"Python {need} 以上が必要です（実行中: {have}）。",
            f"実行中の Python: {sys.executable}",
            "リポジトリの venv の Python で実行してください:",
            f"    .venv/bin/python {sys.argv[0] if sys.argv and sys.argv[0] else 'backlog_change_log.py'}",
        ]

    missing = []
    for module, package in REQUIRED_PACKAGES:
        try:
            importer(module)
        except ModuleNotFoundError:
            missing.append(package)
    if missing:
        return [
            f"必要なライブラリが入っていません: {', '.join(missing)}",
            f"実行中の Python: {sys.executable}",
            "次のコマンドでインストールしてください:",
            f"    {sys.executable} -m pip install {' '.join(missing)}",
        ]
    return []


def make_console_safe(streams=None):
    """
    UTF-8 でないコンソールで、表せない文字を「?」に置き換えて出すようにする。

    Windows の日本語コンソールは既定で CP932 で、CP932 に無い文字を print すると
    UnicodeEncodeError で落ちる。ソースの文字は tests/test_windows.py で CP932 に収めているが、
    課題の件名など Backlog から来る文字（絵文字など）は防げない。落ちるよりは、その文字だけ
    「?」になる方がよい。コードページ（chcp）は変えない。同じ窓で次に動かすものに影響するため。
    """
    for stream in (sys.stdout, sys.stderr) if streams is None else streams:
        encoding = (getattr(stream, "encoding", None) or "").lower().replace("-", "").replace("_", "")
        if encoding in ("", "utf8") or not hasattr(stream, "reconfigure"):
            continue
        try:
            stream.reconfigure(errors="replace")
        except (ValueError, OSError):
            pass


def ensure_runtime():
    """足りないものがあれば案内を出して終了する。あわせてコンソールへの出力を安全にする"""
    make_console_safe()
    problems = check_runtime()
    if problems:
        for line in problems:
            print(line, file=sys.stderr)
        sys.exit(EXIT_ENVIRONMENT)
