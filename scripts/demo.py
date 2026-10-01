#!/usr/bin/env python3
"""
偽の Backlog（tests/fakes.py の FakeClient）につないで、実行例を確かめる。

本物の Backlog には接続しない。リポジトリには何も書かない（設定ファイルは一時フォルダに作る）。

  .venv/bin/python scripts/demo.py run          # run() に偽物を直接渡す（--dry-run）
  .venv/bin/python scripts/demo.py main         # 入口の main() から通す（--dry-run）
  .venv/bin/python scripts/demo.py main post    # --dry-run を外して「投稿」まで通す（投稿先は偽物）

経緯は ../proposals/backlog-change-log-fake-backlog-demo.md（提案元 ../backlog_issue_sheet）。
"""
import argparse
import functools
import os
import sys
import tempfile
from datetime import datetime
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))

import backlog_change_log as entry  # noqa: E402
from change_log.core import JST  # noqa: E402
from change_log.runner import run  # noqa: E402
from tests.fakes import RECORD_ID, FakeClient, change, created, issue, updated  # noqa: E402

# 「今」を固定する。出力する日が日付で決まるため、固定しないと実行のたびに結果が変わる
NOW = datetime(2026, 10, 1, 14, 30, tzinfo=JST)


def make_fake() -> FakeClient:
    """偽の Backlog の中身。場面を変えるときは tests/test_runner.py を参考にここを変える"""
    return FakeClient(
        activities=[
            created("2026-09-01 09:00", RECORD_ID, 1, "変更記録"),  # 記録先の作成（履歴が揃っている印）
            created("2026-09-30 09:00", 2, 123, "ログイン画面の設計"),
            updated("2026-09-30 10:00", 1, 98, "帳票の設計", [change("status", "未対応", "処理中")]),
            updated("2026-10-01 09:00", 3, 101, "障害の調査", [change("limitDate", "2026-10-03", "2026-10-10")]),
        ],
        issues=[
            issue(1, 98, "帳票の設計", "山田太郎"),
            issue(2, 123, "ログイン画面の設計", None),
            issue(3, 101, "障害の調査", "佐藤花子"),
        ],
    )


def main() -> int:
    parser = argparse.ArgumentParser(description="偽の Backlog につないで実行例を確かめる")
    parser.add_argument("mode", choices=["run", "main"], nargs="?", default="run")
    parser.add_argument("post", choices=["post"], nargs="?", help="--dry-run を外して投稿まで通す")
    args = parser.parse_args()
    dry_run = args.post is None
    fake = make_fake()

    if args.mode == "run":
        code = run(fake, "PROJ-1", now=NOW, dry_run=dry_run)
    else:
        with tempfile.TemporaryDirectory() as work:
            config = Path(work) / "config.yaml"
            # PROJ-1 は例の値として拒否されるため別の値にする（偽物は値を見ずに PROJ-1 を返す）
            config.write_text('backlog:\n  space_host: "example.backlog.com"\n'
                              'target:\n  issue_key: "DEMO-1"\n', encoding="utf-8")
            os.environ["BACKLOG_API_KEY"] = "dummy"  # 偽物は使わないが、読み込みで必須
            entry.BacklogClient = lambda *a, **k: fake  # type: ignore[assignment,misc]
            entry.run = functools.partial(run, now=NOW)  # type: ignore[assignment]
            code = entry.main(["--config", str(config)] + (["--dry-run"] if dry_run else []))

    print(f"\n[demo] 終了コード: {code} / 偽の Backlog に投稿されたコメント: {len(fake.posted)} 件")
    return code


if __name__ == "__main__":
    sys.exit(main())
