# backlog_change_log

共通規約: [../ws-conventions/README.md](../ws-conventions/README.md) に従う（`~/ws` 配下の全リポジトリ共通）。

## 実装の置き場所

入口は `backlog_change_log.py`（引数と設定の読み込みだけ）。中身は `change_log/` に役割ごとに
分けてある。入口と同じ名前のパッケージにすると、setuptools と mypy が同名のモジュールを
取り違えるため、パッケージ名は `change_log` にしている。

API を呼ぶのは `change_log/client.py` だけ。通しの処理（`runner.py`）はクライアントを
引数で受け取り、テストでは `tests/fakes.py` の偽のクライアントを渡す。

## 実装を変えたときに実行する

```bash
.venv/bin/python -m pytest -q
.venv/bin/ruff check .
.venv/bin/mypy
```

## 検査

Markdown を編集したら、コミット前に次を実行する（[規約 D](../ws-conventions/README.md#d-編集後の検査)）。

```bash
../ws-conventions/bin/check-markdown.sh .
../ws-conventions/bin/check-privacy.sh .
```

ADR は使っていないため、`check-terms.sh` と `gen-decision-index.py` は対象外。

`scripts/` に実行例のスクリプトを置いたため、手順の検査も行う。

```bash
../ws-conventions/bin/check-commands.sh .
```

## 実行例を確かめる

本物の Backlog に接続せずに、画面の出力を確かめる。偽の Backlog（`tests/fakes.py` の
`FakeClient`）につなぎ、「今」を固定して動かす。リポジトリには何も書かない。

```bash
.venv/bin/python scripts/demo.py run
.venv/bin/python scripts/demo.py main
.venv/bin/python scripts/demo.py main post
```

`run` は通しの処理だけ、`main` は入口から設定の読み込みまで通す。`post` を付けると
`--dry-run` を外し、偽物への投稿まで通す。経緯は
[`../proposals/backlog-change-log-fake-backlog-demo.md`](../proposals/backlog-change-log-fake-backlog-demo.md)。
