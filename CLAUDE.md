# backlog_change_log

共通規約: [../ws-conventions/README.md](../ws-conventions/README.md) に従う（`~/ws` 配下の全リポジトリ共通）。

## 共通規約からの逸脱: 修正ごとに commit / push する

共通規約は「commit / push は、利用者が明示的に指示したときだけ実行する」としているが、
**本リポジトリでは修正のたびに、確認を取らずに commit / push する。** 2026-10-01 に
利用者から本リポジトリ限定の指示があったため。他のリポジトリには適用しない。

**確認を取らない分、手順を飛ばさないこと。** 次の順で行う。

1. 変更する
2. 下の「実装を変えたときに実行する」と「検査」を通す。 **指摘が 0 件でなければコミットしない**
   検査とコミットは `&&` でつなぐ。`;` でつなぐと、検査が失敗しても止まらずにコミットまで進む
   （2026-10-01、`check-privacy.sh` の指摘を残したまま push した）
3. `CHANGELOG.md` に追記する（[規約 C](../ws-conventions/README.md#changelogmd-の更新) の「書く／書かない」で判断）
4. プレフィックスを選ぶ（[規約 A の表](../ws-conventions/README.md#コミットメッセージ)）
5. コミットする。 **1 コミットに複数の修正を詰めない**
6. push して、ローカルとリモートが一致することを確かめ、短縮ハッシュを示す
7. 提案に関わる変更なら [`../proposals/`](../proposals/README.md) も更新する（対応の記録と索引の状態）。
   `proposals/` は Git 管理外で、コミットに含まれないぶん忘れやすい

他のリポジトリへの提案を書くことはあっても、そのリポジトリの履歴は変えない（規約 B）。

## API キーを config.yaml に書ける理由

共通規約 C は「資格情報は設定ファイルに書かない」としているが、本リポジトリは `config.yaml` の
`backlog.api_key` を読む。 **規約の意図は値を Git に入れないことで、`config.yaml` は `.gitignore` で
除外している。** 利用者の指示（2026-10-01）による。文言の見直しは
[`../proposals/ws-conventions-config-api-key.md`](../proposals/ws-conventions-config-api-key.md) で提案した。
規約が直ったら、この節は消してよい。

## 文書の分担

[`../backlog_issue_cloner`](../backlog_issue_cloner/README.md) の文書の作りに揃えている。

| 文書 | 書くこと |
|---|---|
| `README.md` | 使い方・設定項目・Exit code など、使う人が引くもの |
| `docs/DESIGN.md` | なぜそうなっているか、どこを触ればよいか、落とし穴。 **使い方は再掲しない** |
| `docs/EXAMPLES.md` | 偽の Backlog で動かした実際の出力 |

**設計判断は `docs/DESIGN.md` に集約する。** 実装の置き場所や依存の向き、`runtime.py` を 3.9 でも
読める書き方に保つことなども、そちらに書いてある。改修する前に読むこと。

出力の形式を変えたら、`docs/EXAMPLES.md` の出力も作り直す（`scripts/demo.py` か、
`tests/fakes.py` を使った使い捨てのスクリプトで出す）。

`**` による強調の両端は半角スペースにする（[`docs/DESIGN.md`](docs/DESIGN.md#md-を書くときの体裁)）。

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
