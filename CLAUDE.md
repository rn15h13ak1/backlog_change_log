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
`bin/` にも `scripts/` にも検査スクリプトを置いていないため、`check-commands.sh` も対象外になる。
