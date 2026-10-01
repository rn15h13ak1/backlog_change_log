# backlog_change_log

共通規約: [../ws-conventions/README.md](../ws-conventions/README.md) に従う（`~/ws` 配下の全リポジトリ共通）。

## 共通規約からの逸脱: 修正ごとに commit / push する

共通規約は「commit / push は、利用者が明示的に指示したときだけ実行する」としているが、
**本リポジトリでは修正のたびに、確認を取らずに commit / push する。** 2026-10-01 に
利用者から本リポジトリ限定の指示があったため。他のリポジトリには適用しない。

**確認を取らない分、手順を飛ばさないこと。** 次の順で行う。

1. 変更する
2. 下の「実装を変えたときに実行する」と「検査」を通す。**指摘が 0 件でなければコミットしない**
3. `CHANGELOG.md` に追記する（[規約 C](../ws-conventions/README.md#changelogmd-の更新) の「書く／書かない」で判断）
4. プレフィックスを選ぶ（[規約 A の表](../ws-conventions/README.md#コミットメッセージ)）
5. コミットする。**1 コミットに複数の修正を詰めない**
6. push して、ローカルとリモートが一致することを確かめ、短縮ハッシュを示す
7. 提案に関わる変更なら [`../proposals/`](../proposals/README.md) も更新する（対応の記録と索引の状態）。
   `proposals/` は Git 管理外で、コミットに含まれないぶん忘れやすい

他のリポジトリへの提案を書くことはあっても、そのリポジトリの履歴は変えない（規約 B）。

## 実装の置き場所

入口は `backlog_change_log.py`（引数と設定の読み込みだけ）。中身は `change_log/` に役割ごとに
分けてある。入口と同じ名前のパッケージにすると、setuptools と mypy が同名のモジュールを
取り違えるため、パッケージ名は `change_log` にしている。

入口（`backlog_change_log.py` / `check_api.py`）は、ほかの import より先に
`change_log/runtime.py` で Python の版と依存を確かめる。**`runtime.py` は 3.9 でも読める書き方に
保つ**（`str | None` などを使わない）。崩すと、古い Python で案内が出る前に落ちる。

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
