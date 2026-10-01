"""
Windows 環境への対応を守るテスト
================================
macOS では気付けない退行を検出する（規約 E、../ws-conventions/guides/windows.md）。

Windows の日本語コンソールは既定で CP932 のため、CP932 に無い文字を print すると
文字化けではなく UnicodeEncodeError で落ちる。menu.bat をダブルクリックした場合、
メニューの最初の画面すら出ない。

流用元は ../backlog_issue_cloner/tests/test_windows.py。ここでは次の 2 点を足している。
- 画面に出すソースを、名前の一覧ではなくフォルダから集める（足したモジュールが漏れない）
- ソースの文字だけでなく、実際に動かした出力が CP932 に収まるかも見る
"""
import io
import re
import sys
from datetime import datetime
from pathlib import Path

import pytest

from change_log.core import JST
from change_log.runner import run
from change_log.runtime import MIN_PYTHON, make_console_safe
from tests.fakes import RECORD_ID, FakeClient, change, commented, created, deleted, issue, record_comment, updated

ROOT = Path(__file__).resolve().parent.parent

#: 画面（cmd.exe のコンソール）に出るソース。tests/ は画面に出さないので対象外。
CONSOLE_SOURCES = sorted([*ROOT.glob("*.py"), *(ROOT / "change_log").glob("*.py"), *(ROOT / "scripts").glob("*.py")])


def _unencodable(text: str) -> set[str]:
    bad = set()
    for ch in set(text):
        if ord(ch) < 128:
            continue
        try:
            ch.encode("cp932")
        except UnicodeEncodeError:
            bad.add(ch)
    return bad


# ---------------- 画面に出す文字 ----------------

def test_console_sources_are_collected():
    """対象が 0 件だと、下の検査は何も見ずに通る"""
    names = {p.name for p in CONSOLE_SOURCES}
    assert {"backlog_change_log.py", "check_api.py", "menu.py", "runner.py", "render.py", "diagnose.py"} <= names


@pytest.mark.parametrize("path", CONSOLE_SOURCES, ids=lambda p: str(p.relative_to(ROOT)))
def test_sources_are_cp932_safe(path):
    bad = _unencodable(path.read_text(encoding="utf-8"))
    assert bad == set(), (
        f"{path.name} に CP932 で表現できない文字があります: "
        + ", ".join(f"U+{ord(c):04X} {c!r}" for c in sorted(bad))
        + "。Windows の日本語コンソールで UnicodeEncodeError になります。"
    )


def test_detects_a_known_bad_character():
    """検査自体が機能していることを確かめる（em dash と、以前使っていた記号は CP932 に無い）"""
    assert _unencodable("作成完了 — 件名") == {"—"}
    assert _unencodable("⚠ ✓ ✗") == {"⚠", "✓", "✗"}


def test_common_symbols_are_safe():
    """実際に使っている記号が CP932 にあること"""
    assert _unencodable("←※【】―〜｜（）、。") == set()


def test_actual_output_is_cp932_safe():
    """
    ソースの文字だけでは分からない、組み立てた後の出力を見る。
    投稿する日・当日分・警告・複数のプロジェクトを、すべて通る形で動かす。
    """
    acts = [
        created("2026-09-01 09:00", RECORD_ID, 1, "変更記録"),
        created("2026-09-30 09:00", 2, 123, "ログイン画面"),
        updated("2026-09-30 10:00", 1, 98, "帳票|レイアウト", [change("status", "未対応", "処理中")]),
        commented("2026-09-30 11:00", 3, 105, "問い合わせ"),
        created("2026-09-30 12:00", 4, 120, "重複"),
        deleted("2026-09-30 12:05", 4, 120, "重複"),
        updated("2026-10-01 09:00", 1, 98, "帳票|レイアウト", [change("assigner", "", "山田")]),
    ]
    issues = [issue(1, 98, "帳票|レイアウト", "山田"), issue(2, 123, "ログイン画面", None),
              issue(3, 105, "問い合わせ", "佐藤")]
    other = {"OTHER": (20, [commented("2026-09-29 12:00", 501, 5, "x")], [])}
    client = FakeClient(acts, issues, comments=[record_comment("対象日: 2026-09-20")], other_projects=other)
    out, err = io.StringIO(), io.StringIO()
    run(client, "PROJ-1", project_keys=["PROJ", "OTHER"], now=datetime(2026, 10, 1, 14, 30, tzinfo=JST),
        dry_run=True, out=out, err=err)
    text = out.getvalue() + err.getvalue()
    assert "警告:" in text and "当日の変更" in text   # 警告の経路も通っていること
    assert _unencodable(text) == set()


# ---------------- Backlog から来る文字 ----------------

def _cp932_stream() -> io.TextIOWrapper:
    return io.TextIOWrapper(io.BytesIO(), encoding="cp932", errors="strict")


def test_unencodable_data_crashes_without_the_guard():
    """前提の確認: CP932 のコンソールに絵文字を出すと落ちる"""
    stream = _cp932_stream()
    with pytest.raises(UnicodeEncodeError):
        print("件名 🚀 リリース", file=stream)
        stream.flush()


def test_console_safe_replaces_unencodable_data():
    """課題の件名など Backlog から来る文字は、ソースの検査では防げない。落ちずに「?」になる"""
    stream = _cp932_stream()
    make_console_safe([stream])
    print("件名 🚀 リリース", file=stream)
    stream.flush()
    assert stream.buffer.getvalue().decode("cp932") == "件名 ? リリース\n"


def test_console_safe_leaves_utf8_alone():
    stream = io.TextIOWrapper(io.BytesIO(), encoding="utf-8", errors="strict")
    make_console_safe([stream])
    assert stream.errors == "strict"


def test_console_safe_ignores_streams_without_reconfigure():
    make_console_safe([io.StringIO()])   # 例外にならない


# ---------------- menu.bat ----------------

@pytest.fixture(scope="module")
def bat() -> bytes:
    return (ROOT / "menu.bat").read_bytes()


def test_menu_bat_line_endings_are_crlf(bat):
    """LF だけだと cmd.exe が誤動作する"""
    assert bat.count(b"\n") - bat.count(b"\r\n") == 0, "CRLF でない行があります（.gitattributes を確認）"


def test_menu_bat_is_ascii_only(bat):
    """コンソールのコードページに依存しないよう ASCII に限る"""
    assert all(b < 128 for b in bat), "menu.bat に非 ASCII 文字が含まれています"


def test_menu_bat_uses_pushd_not_cd(bat):
    """cd はネットワーク共有（UNC パス）で失敗する"""
    text = bat.decode("ascii")
    assert 'pushd "%~dp0"' in text and "cd /d" not in text


def test_menu_bat_falls_back_when_py_launcher_is_missing(bat):
    text = bat.decode("ascii")
    assert "py -3" in text and "python --version" in text


def test_menu_bat_passes_arguments_to_the_menu(bat):
    assert "menu.py %*" in bat.decode("ascii")


def test_menu_bat_pauses_only_when_double_clicked(bat):
    """
    ダブルクリック起動では窓が閉じる前にエラーを読ませたい。引数付き（タスクスケジューラなど）
    では pause が永遠に待つ。最後の pause は引数が無いときだけにする
    """
    lines = [line.strip() for line in bat.decode("ascii").splitlines()]
    end = len(lines) - 1 - lines[::-1].index("popd")   # 最後の popd より後が終わりの処理
    tail = lines[end:]
    assert 'if "%~1"=="" pause' in tail
    assert "pause" not in tail, "引数があっても止まる pause が残っています"


def test_menu_bat_names_the_same_python_version_as_the_tool(bat):
    need = ".".join(str(n) for n in MIN_PYTHON)
    assert f"Python {need} or later" in bat.decode("ascii")


def test_bat_is_pinned_to_crlf_in_gitattributes():
    """Git が menu.bat を LF に正規化しないこと。作業ツリーが CRLF でも、Git の中身は別になりうる"""
    text = (ROOT / ".gitattributes").read_text(encoding="utf-8")
    assert re.search(r"^\*\.bat\s+.*eol=crlf", text, re.M), "*.bat に eol=crlf の指定がありません"


def test_runtime_guard_stays_python39_compatible():
    """runtime.py は古い Python で案内を出すために読み込まれる。3.10 以上の書き方を使うと案内の前に落ちる"""
    import ast
    source = (ROOT / "change_log" / "runtime.py").read_text(encoding="utf-8")
    tree = ast.parse(source, feature_version=(3, 9))
    # `str | None` は構文としては 3.9 でも通るが、関数を定義した時点で評価されて TypeError になる
    # （実際に落ちた形）。注釈の中の | を探す
    annotations = []
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            annotations += [a.annotation for a in node.args.args + node.args.kwonlyargs if a.annotation]
            annotations += [node.returns] if node.returns else []
        elif isinstance(node, ast.AnnAssign):
            annotations.append(node.annotation)
    uses_union = [ast.unparse(a) for a in annotations
                  if any(isinstance(n, ast.BinOp) and isinstance(n.op, ast.BitOr) for n in ast.walk(a))]
    assert uses_union == [], f"runtime.py の注釈に | があります（3.9 で落ちる）: {uses_union}"
    assert sys.version_info >= MIN_PYTHON   # テスト自体は対応版で動いていること
