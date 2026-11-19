# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## プロジェクトの目的

ボードゲームを構成する情報（コンポーネント、状態、ルール、手番進行など）を抽象化し、それを操作できる汎用環境を開発する。
この環境をエージェントが使い、次のことを行えるようにするのが目標。

- 新しいボードゲームの設計とテストプレイ
- 既存ボードゲームのテストプレイ
- シミュレーション結果にもとづくバランス調整

特定のゲーム専用の実装ではなく、複数のゲームを同じ抽象で表現できる設計を優先すること。

概念の一覧と、再現できないもの・必要な概念の整理は `specs/versions/v1/okf/notes/concept-review.md`。概念モデル（原型 8 つと派生）と構造は `contracts/CTR-F-001.md` と `structure/`。定義に現れるものは、できる限りエリアとオブジェクトの派生（kinds の base）で表す（RUL-005）。

画像：定義の `assets.root`（画像の置き場）と、エリアの `image`（背景）、部品・種類の `image`・`back_image`（`{default, "状態=値"}` で状態ごとに替えられる）。画面は `/assets/` で root の下だけを配る。惨劇RoopeR の再現（`local/tragedy-looper.yaml`、生成は `local/gen_tl.py`）は sangeki の惨劇コモンズ5th を指す（利用は惨劇RoopeR 関連に限る。公開時は「惨劇コモンズ作成：BakaFire・紺ノ玲」とリンクを表記）。

サンプル：`examples/` に三目並べ・かがり火・六角・オセロ・チェス（名前つきの式 `functions` でチェック）・将棋・麻雀・人狼・精霊獣デュエル（架空。カードの効果とステータス、アクションの `stepwise`）・ルーン決闘（架空。スタックで割り込む、アクションの `cost`）（古典は公開してよい）。`local/` に花火・ディプロマシー（生成 `local/gen_dip.py`）など市販品の再現。デモの対局は `local/social-demos.py` で作り直す。

終わり方（RUL-015、notes/endgame/gates.md）：`flow.end_when` の各件に `winners`・`losers`（式）・`draw`・`winners: scoring` と `timing`（now・turn_end・round_end）、`flow.auto_end` で結果を記録して終える、`flow.scoring`（by・tiebreak）で順位、手番の `on_end` で手番の終わりの処理。`bg complexity` でルールの複雑さの目安。

割り込み（RUL-013）：アクションの `stack: true` は解決待ちの列に積み、ほかの人が応じて積むか `bg pass` で見送ると、後から積んだもの（`flow.stack: fifo` なら先）から解決する。打ち消しは手順の `cancel`（引数の `stack: true`）。例は `tests/test_stack.py`。

発言と隠れた情報（RUL-009）：発言は操作 `say`（`bg say`。`--to` で内緒話。`offer` で提案、`answer` で受ける・断る＝守られる約束）、話せない時間は進行の `talk`。書き込む状態（種類の状態に型 text・player）、公開範囲 `others`、`know` の `fields`（一部だけの知識）、アクションの `secret`。

目的の中心は「エージェントが不足なく読めるゲームの定義」（`specs/` の RUL-001 #25・#28）。ルールの自動実行はしない。ルールの中身は自然文が正本で、機械化するのは参照の整合・物の置き場・乱数・見え方だけ（#31・#35）。

## スキル（.claude/skills）

新しいゲームを作るとき：`bg-design`（アイデア → 定義、bg check・bg fuzz まで）→ `bg-playtest`（エージェントに席ごとに遊ばせる）→ `bg-balance`（多数局で測り、数値を 1 つずつ変えて比べる）。点検：`bg-hidden-info-audit`（隠れた情報の漏れのチェック表）、`bg-rules-audit`（ルール文と定義の突き合わせ）。

## 仕様と記録

- `specs/versions/v1/okf/`：okf-specs のバンドル（裁定 RUL、要望 WSH、要求 REQ、要件 SPC）。チェック：`python3 <okf-spec>/tools/okf_check.py specs/versions/v1/okf`
- `specs/versions/v1/okf/notes/*/gates.md`：推奨案で決めた判断の記録
- `.okf/`：調査記録（OKF。okf プラグイン）
- 既存の商用ゲームの定義は公開しない（RUL-001 #37）。`local/` に置く（git 管理外）

## コマンド

```bash
uv sync                                   # 依存を入れる
uv run pytest -q                          # テスト（受入基準 AC ごと）
uv run pytest -q -k AC_011                # 1 つの受入基準だけ
uv run bg check examples/kagaribi.yaml    # 参照の確認
uv run bg new sessions/s1 --def examples/kagaribi.yaml --players 2 --seat P1=agent:a --seed 1
uv run bg op sessions/s1 '{"op":"move","obj":"N4","to":"discard","by":"P2","rule":"R4"}'
uv run bg show sessions/s1 --as P2 --meaning   # P2 の見え方（--as 省略でキーパー）
uv run bg serve sessions/s1 --host 172.29.127.192   # 画面（Windows から http://172.29.127.192:8765/ ）
uv run bg tts sessions/s1 --out exports/s1.json      # TTS の Saved Object に書き出す（Saves/Saved Objects に置く）
uv run bg new sessions/b1 --def examples/kagaribi.yaml --players 2 --from-box   # 箱から始める
# 定義の game.strict（人狼など）は厳格モードが既定。試し遊びで警告だけにするなら bg new --lenient
uv run bg act sessions/b1 setup --by P1                # 定義のアクション（手順をすべて行うか、1 つも行わない）
uv run bg setup-check sessions/b1                      # 定義の初期の置き場と比べる
uv run --with playwright pytest -q tests/test_ui.py    # 画面の受入基準（playwright は依存に入れていない）
uv run bg show sessions/s1 --as P1 --compact --only hand-P1,talk,offers_for_me  # 一部だけ（エリアと局面の部分）
uv run bg show sessions/s1 --as P1 --compact --links  # 短い局面（エージェント向け。発言は最後の 10 件、--talk-since N で番号から。一覧の属性は catalog に 1 回）とリンク
uv run bg near sessions/s1 <エリア> --type corner       # リンク先と中身
uv run bg candidates sessions/s1 <アクション> --by P1 --param corner   # 引数の候補と条件（--param を省くと全部の引数）
uv run bg advance sessions/s1 --to turn                # 進行を次へ（phase・turn・stage）。ワザを使わずに手番を終えるなど
uv run bg undo sessions/s1                             # 最後の操作（アクションなら全部）を取り消す
uv run bg pass sessions/s1 --by P2                     # スタックの解決を見送る（bg resolve はキーパーが解決を進める）
uv run bg selfplay examples/rune-clash.yaml --players 2 --games 30   # 作品を問わないでたらめの対戦（終わり方の偏りと局の長さの目安）
uv run bg fuzz examples/beast-duel.yaml --players 2   # でたらめ実行：式の誤り・エンジンの不具合・一度も行えないアクションを探す
uv run bg rebase sessions/s1                           # 定義を直した後、記録が再生できれば対局を今の定義に合わせる
uv run bg say sessions/s1 "こんにちは" --by P1 --to P2  # 発言（--to を省くと全員）
uv run bg say sessions/s1 "木 2 と鉱石 1" --by P1 --to P2 --offer '[{"op":"move","obj":"res-lumber","from":"hand-P1","to":"hand-P2","n":2}]'  # 提案（受けたらまとめて行う）
uv run bg answer sessions/s1 3 --by P2               # 提案（bg show の talk の n）を受ける
# 提案に --action trade-players（か定義の flow.offer_action）を付けると、成立したとき手番・条件を確かめる（--decline で断る・出した人なら取り下げ）
uv run --with pyxel python samples/pyxel/rune_clash.py  # ルーン決闘を Pyxel で遊ぶ（あなた対ボット。WSLg なら DISPLAY=:0）
uv run python local/duel-bot.py 12                     # 精霊獣デュエルをボットで 12 局（定義だけで最後まで回るか・勝率）
```

画面（`bg serve`。止めるときは `pkill -f "[b]g serve"`）はゲームエンジンではなく、TTS のように部品をさわれる卓。画面の操作も `bg op` も同じ `log.jsonl` に入り、画面は 1.5 秒ごとに記録を読み直す。認証はないので、公開する IP は WSL の内側のアドレスに限る。

## 構成（src/bgskills）

- `definition.py`：YAML の定義を読み、略記（`for_each`・`copies`・`layout`）を人数に合わせて展開し、全要素を 1 つの ID 空間で索引する（ID は種類をまたいで一意）
- `tools.py`：YAML の書き出し、参照の確認、版の差分、ルールの逆引き（部品 → 種類 → 用語の参照を通じて引く）
- `session.py`：局面と基本の操作（move・attach・flip・set・shuffle・know・progress・ruling・end）。局面は保存せず、`log.jsonl` の操作を最初から再生して作る。乱数は `seed:操作の通し番号` で決まる
- `view.py`：プレイヤーごとの見え方（公開範囲の段階 × 向き × 既知）と意味つきの局面
- `flow.py`：進行の構造（段階・手番・フェーズ、アクションの区分と回数。外れたら警告だけ）
- `query.py`：近傍の問い合わせと条件（引数の require。警告と候補）
- `metrics.py`：指標（局面から数えて出す値。見え方を守る）
- `cli.py`：`bg` コマンド（スキルから呼ぶスクリプト）
- `tts.py`：局面を Tabletop Simulator の Saved Object に書き出す（実機では未確認の点がある：山の上下など）
- `server.py`・`ui.html`：`bg serve` の HTTP（`/api/def`・`/api/view`・`/api/log`・`POST /api/op`）と、依存なしの 1 ファイルの画面（ポインタ操作でドラッグ。マウスとタッチの両方）

## 開発環境

- WSL2 上の Ubuntu。
- Python を使う場合は uv で管理する（`uv run` / `uv add` / `uvx`）。
- Node.js を使う場合は nvm 管理の WSL 側のものを使う。
