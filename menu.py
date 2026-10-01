#!/usr/bin/env python3
"""
Backlog 変更記録 対話メニュー
=============================
投稿内容の確認・記録・応答の確認を、番号を選ぶだけで実行する。

  python3 menu.py                  # メニューを表示
  python3 menu.py --config my.yaml # 設定ファイルを指定

本体（backlog_change_log.py / check_api.py）は別のプロセスとして呼ぶ。
無人実行（定期実行）はこのメニューではなく本体を直接呼ぶこと:
  .venv/bin/python backlog_change_log.py

作りは ../backlog_issue_cloner/menu.py に揃えている。
"""
import sys

# 依存と Python の版を先に確かめる（backlog_change_log.py と同じ理由）。
# menu.bat のダブルクリック起動で足りない場合に、トレースバックではなく対処を表示する。
from change_log.runtime import ensure_runtime

ensure_runtime()

import argparse
import json
import subprocess
from pathlib import Path

import yaml

from change_log.config import PLACEHOLDERS, find_api_key

WIDTH = 60
TOOL_DIR = Path(__file__).resolve().parent
MAIN_SCRIPT = TOOL_DIR / "backlog_change_log.py"
CHECK_SCRIPT = TOOL_DIR / "check_api.py"
HISTORY_PATH = Path.home() / ".backlog_change_log_menu.json"

ACTION_DRY_RUN = "dry_run"
ACTION_POST = "post"
ACTION_CHECK = "check"

ACTIONS = [
    (ACTION_DRY_RUN, "投稿内容を確認する", "投稿するコメントを表示するだけ（投稿しません）"),
    (ACTION_POST, "記録する", "前日までの未出力の日を、記録先の課題にコメントとして投稿する"),
    (ACTION_CHECK, "API の応答を確かめる", "応答が本ツールの前提どおりかを確かめる（読み取りだけ）"),
]

#: check_api.py で遡る日数の選択肢
CHECK_DAYS = [7, 30, 90]

#: 本体の終了コードの意味（README の Exit code と揃える）
EXIT_MEANINGS = {
    0: "正常終了",
    1: "API / ネットワークエラー、または投稿に失敗（残りの日は次回に出力されます）",
    2: "実行する前に直すものがあります（設定ファイル、API キー、Python の版、PyYAML）",
    3: "出力しなかった日があります（理由は上の警告を見てください）",
    4: "同じ記録先への実行が、すでに動いています",
    127: "本体が見つかりません",
    130: "中断しました",
}
CHECK_EXIT_MEANINGS = {
    0: "前提と違う応答はありませんでした",
    1: "前提と違う応答があります（または API / ネットワークエラー）",
    2: "実行する前に直すものがあります（設定ファイル、API キー、Python の版、PyYAML）",
    127: "本体が見つかりません",
    130: "中断しました",
}

# 終了コード（tool_launcher / backlog_issue_cloner のメニューと揃える）
EXIT_OK = 0
EXIT_EOF = 1
EXIT_INTERRUPTED = 130


# ===========================================================================
# 表示・入力
# ===========================================================================


def hr(char: str = "=") -> None:
    print(char * WIDTH)


def print_menu(title: str, items: list[str], back_label: str = "戻る",
               default: int | None = None, default_mark: str = "既定") -> int:
    """
    メニューを表示して選択番号を返す。0 = 戻る / 終了。
    default_mark は既定値の由来を示すラベル（前回の選択なら「前回」）。
    """
    while True:
        print()
        hr()
        print(f"  {title}")
        hr()
        for i, item in enumerate(items, 1):
            mark = f" ←{default_mark}" if default == i else ""
            print(f"  {i}. {item}{mark}")
        hr("-")
        print(f"  0. {back_label}")
        hr()
        prompt = "番号を入力してください" + (f" [Enter={default}]: " if default else ": ")
        choice = input(prompt).strip()
        if not choice and default:
            return default
        if choice == "0":
            return 0
        if choice.isdigit() and 1 <= int(choice) <= len(items):
            return int(choice)
        print("  ※ 無効な入力です。もう一度入力してください。")


def confirm(prompt: str) -> bool:
    """y/N で確認する。y / yes 以外はすべて「いいえ」"""
    return input(f"  {prompt} [y/N]: ").strip().lower() in ("y", "yes")


# ===========================================================================
# 前回値の記憶
# ===========================================================================


def load_history() -> dict:
    """前回の選択を読む。壊れていても既定値で続行する。"""
    try:
        with open(HISTORY_PATH, encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, dict) else {}
    except (OSError, ValueError):
        return {}


def save_history(data: dict) -> None:
    """選択を保存する。書けなくても実行は妨げない。"""
    try:
        with open(HISTORY_PATH, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
    except OSError:
        pass


# ===========================================================================
# 設定の表示
# ===========================================================================


def describe_setup(config_path: str, env: dict | None = None) -> list[str]:
    """
    メニューの見出しに出す、接続先・記録先・追跡するプロジェクト・API キーの状態。

    本体の読み込み（change_log.config.load_config）は足りないものがあると終了するため、
    ここでは自前で読み、足りないものは「※」で示す。API キーの値は表示しない。
    """
    path = Path(config_path)
    try:
        with open(path, encoding="utf-8") as f:
            raw = yaml.safe_load(f)
    except OSError:
        return [f"※ 設定ファイルがありません: {path}（config.example.yaml をコピーして作成してください）"]
    except yaml.YAMLError:
        return [f"※ 設定ファイルを読めません: {path}"]
    if not isinstance(raw, dict):
        return ["※ 設定ファイルの内容が空です"]

    backlog = raw.get("backlog") or {}
    target = raw.get("target") or {}
    host = str(backlog.get("space_host") or "")
    issue_key = str(target.get("issue_key") or "")
    keys = target.get("project_keys")

    lines = [
        f"接続先    : {host if host and host not in PLACEHOLDERS else '※ backlog.space_host が未設定です'}",
        f"記録先    : {issue_key if issue_key and issue_key not in PLACEHOLDERS else '※ target.issue_key が未設定です'}",
    ]
    if isinstance(keys, list) and keys:
        lines.append(f"追跡      : {', '.join(str(k) for k in keys)}")
    else:
        lines.append("追跡      : 記録先の課題のプロジェクト")
    found = find_api_key(env, config_path=path, config_value=backlog.get("api_key"))
    lines.append(f"API キー  : {'設定済み' if found else '※ 見つかりません（config.yaml の backlog.api_key）'}")
    return lines


# ===========================================================================
# 実行
# ===========================================================================


def build_args(action: str, *, config_path: str = "", days: int | None = None) -> list[str]:
    """本体に渡すコマンドライン引数を組み立てる。"""
    args = ["--config", config_path] if config_path else []
    if action == ACTION_DRY_RUN:
        args.append("--dry-run")
    elif action == ACTION_CHECK and days:
        args += ["--days", str(days)]
    return args


def script_for(action: str) -> Path:
    return CHECK_SCRIPT if action == ACTION_CHECK else MAIN_SCRIPT


def run_script(script: Path, args: list[str]) -> int:
    """本体を実行して終了コードを返す。"""
    if not script.is_file():
        print(f"\n  ※ 本体が見つかりません: {script}")
        return 127
    print()
    hr("-")
    try:
        completed = subprocess.run([sys.executable, str(script), *args], cwd=TOOL_DIR)
    except KeyboardInterrupt:
        print("\n  中断しました。")
        return EXIT_INTERRUPTED
    return completed.returncode


def describe_exit(action: str, code: int) -> str:
    meanings = CHECK_EXIT_MEANINGS if action == ACTION_CHECK else EXIT_MEANINGS
    return f"終了コード: {code}（{meanings.get(code, '想定外の終了コードです')}）"


def choose_days(history: dict) -> int | None:
    """check_api.py で遡る日数を選ぶ。戻る場合は None。"""
    last = history.get("check_days")
    default = CHECK_DAYS.index(last) + 1 if last in CHECK_DAYS else 1
    choice = print_menu("遡る日数", [f"{d} 日" for d in CHECK_DAYS], default=default,
                        default_mark="前回" if last in CHECK_DAYS else "既定")
    return None if choice == 0 else CHECK_DAYS[choice - 1]


def run_action(action: str, label: str, config_path: str, history: dict) -> int | None:
    """1 つの操作を実行する。戻る場合は None。"""
    print()
    hr()
    print(f"  {label}")
    hr()

    days = None
    if action == ACTION_CHECK:
        days = choose_days(history)
        if days is None:
            return None
        history["check_days"] = days
    elif action == ACTION_POST:
        # 本体には確認が無い（定期実行で使うため）。取り消せない操作なので、ここで 1 回確認する。
        print("  前日までの未出力の日を、記録先の課題にコメントとして投稿します。")
        print("  投稿したコメントは、このツールでは取り消せません。")
        print("  先に「投稿内容を確認する」で内容を見ておくことを勧めます。")
        if not confirm("投稿しますか？"):
            print("  投稿しませんでした。")
            return None

    history["action"] = action
    save_history(history)
    return run_script(script_for(action), build_args(action, config_path=config_path, days=days))


# ===========================================================================
# エントリポイント
# ===========================================================================


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Backlog 変更記録 対話メニュー",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="無人実行（定期実行）には backlog_change_log.py を直接使ってください。",
    )
    parser.add_argument("--config", default=str(TOOL_DIR / "config.yaml"),
                        help="設定ファイルのパス（既定: config.yaml）")
    return parser


def main() -> None:
    args = build_parser().parse_args()
    history = load_history()
    last_action = history.get("action")
    default_choice = next((i for i, (key, _, _) in enumerate(ACTIONS, 1) if key == last_action), None)
    # 前回が「記録する」でも、既定にはしない（Enter だけで投稿の確認まで進まないように）
    if last_action == ACTION_POST:
        default_choice = None
    items = [f"{label} ― {desc}" for _, label, desc in ACTIONS]

    try:
        while True:
            print()
            hr()
            print("  Backlog 変更記録")
            hr()
            for line in describe_setup(args.config):
                print(f"  {line}")
            choice = print_menu("操作を選択", items, back_label="終了",
                                default=default_choice, default_mark="前回")
            if choice == 0:
                print("  終了します。")
                sys.exit(EXIT_OK)

            action, label, _ = ACTIONS[choice - 1]
            rc = run_action(action, label, args.config, history)
            if rc is not None:
                print()
                hr("-")
                print(f"  {describe_exit(action, rc)}")
                if action != ACTION_POST:
                    default_choice = choice
                input("\n  Enter キーでメニューに戻ります...")
    except EOFError:
        print("\n  入力が終了しました。")
        sys.exit(EXIT_EOF)
    except KeyboardInterrupt:
        print("\n  中断しました。")
        sys.exit(EXIT_INTERRUPTED)


if __name__ == "__main__":
    main()
