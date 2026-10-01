#!/usr/bin/env python3
"""
実際のスペースの応答で、本ツールが置いている前提を確かめる。読み取りだけで、投稿はしない。

  .venv/bin/python check_api.py
  .venv/bin/python check_api.py --days 30
"""
import sys

# 依存と Python の版を先に確かめる（backlog_change_log.py と同じ理由）
from change_log.runtime import ensure_runtime

ensure_runtime()

import argparse

from change_log.client import BacklogAPIError, BacklogClient, format_api_error
from change_log.config import load_config
from change_log.core import REPO_ROOT
from change_log.diagnose import diagnose


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Backlog API の応答が、本ツールの前提どおりかを確かめる")
    parser.add_argument("--config", default=str(REPO_ROOT / "config.yaml"),
                        help="設定ファイルのパス（既定: スクリプトと同じディレクトリの config.yaml）")
    parser.add_argument("--days", type=int, default=7, help="遡って読むアクティビティの日数（既定: 7）")
    parser.add_argument("--max", type=int, default=1000, dest="max_activities",
                        help="読むアクティビティの上限件数（既定: 1000）")
    parser.add_argument("--debug", action="store_true", help="API リクエストを表示する（API キーは表示しない）")
    args = parser.parse_args(argv)

    config = load_config(args.config)
    client = BacklogClient(config.space_host, config.api_key, ssl_verify=config.ssl_verify,
                           base_path=config.base_path, debug=args.debug)
    print(f"接続先: {client.base_url}")
    try:
        return diagnose(client, config.issue_key, days=args.days, max_activities=args.max_activities)
    except BacklogAPIError as e:
        print(format_api_error(e), file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
