#!/usr/bin/env python3
"""
Backlog の課題の変更（作成・更新・削除）を、1 日ごとに記録先の課題のコメントへ出力する。

前日以前で未出力の日（最大 7 日）を 1 日 1 件で投稿し、当日の変更は標準出力に表示する。
"""
import argparse
import sys

from change_log.client import BacklogAPIError, BacklogClient, format_api_error
from change_log.config import load_config
from change_log.core import REPO_ROOT
from change_log.runner import run


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Backlog の課題の変更を、1 日ごとに課題のコメントへ記録する")
    parser.add_argument("--config", default=str(REPO_ROOT / "config.yaml"),
                        help="設定ファイルのパス（既定: スクリプトと同じディレクトリの config.yaml）")
    parser.add_argument("--dry-run", action="store_true",
                        help="投稿するコメントを表示するだけで、投稿しない")
    parser.add_argument("--debug", action="store_true",
                        help="API リクエストを表示する（API キーは表示しない）")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    config = load_config(args.config)
    client = BacklogClient(config.space_host, config.api_key, ssl_verify=config.ssl_verify,
                           base_path=config.base_path, debug=args.debug)
    try:
        return run(client, config.issue_key, dry_run=args.dry_run)
    except BacklogAPIError as e:
        print(format_api_error(e), file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
