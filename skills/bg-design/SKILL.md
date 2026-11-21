---
name: bg-design
description: 新しいボードゲーム（カードゲーム・盤のゲーム・会話のゲーム）のアイデアを、bg-skills のゲーム定義（YAML）に起こし、bg check と bg fuzz を通すまで仕上げる。「ゲームを作りたい」「このルールを定義にして」「定義を書いて」と言われたときに使う。試し遊びは bg-playtest、勝率の調整は bg-balance の担当。
---

# bg-design：アイデア → ゲーム定義

> **どこで使っても**：`bg` はプラグインが PATH に入れるコマンド（入れていない、このリポジトリの中なら `uv run bg`）。下の `examples/`・`specs/`・`src/`・`tests/`・`CLAUDE.md` は**プラグインのルート**（このスキルのディレクトリから 2 つ上）の中のファイル。コマンドの一覧は `<プラグインのルート>/CLAUDE.md` の「コマンド」の節。作る定義・対局は、利用者のプロジェクトに置く。

ゲームのアイデアから、エージェントが不足なく読めるゲーム定義（`examples/*.yaml` と同じ形式）を書く。ルールの中身は自然文が正本で、機械化するのは参照・置き場・乱数・見え方・進行だけ（CLAUDE.md、RUL-001 #31）。

## 前提

- 形式の正本は `specs/versions/v1/okf/contracts/CTR-F-001.md`（フィールドの表と「派生」の表）。書く前に読む。
- 似た作品の定義を 1 つ開いて手本にする：カードの効果とステータス `examples/beast-duel.yaml`、隠れた役職と発言 `examples/werewolf.yaml`、盤と駒 `examples/chess.yaml`、割り込み `tests/test_stack.py` の SPELLS、最小 `examples/tic-tac-toe.yaml`。
- 既存の商用ゲームは `local/` に置き、公開しない（RUL-001 #37）。名前やキャラクターを写した作り直しはしない。

## 手順

1. **アイデアを確かめる**（足りなければ利用者に 1 回だけまとめて聞き、答えがなければ仮定を `game.open_questions` に書いて進める）
   - 人数、勝ち負け、1 手番にすること、部品（カード・駒・トークン・ボード）、隠れた情報の有無、話し合い・交渉・割り込みの有無。
2. **原型に当てはめる**（新しい仕組みを作る前に、CTR-F-001 の「派生」の表で表せないか探す）
   - 置き場 → `areas`（手札は `owner` と公開範囲、山札は `ordered`、上限は `capacity`）
   - 部品 → `kinds`（`base` で area か object にたどり着く）と `objects`（`copies`・`for_each`・数える部品は `distinct: false`、尽きない山は `count: unlimited`）
   - 状態（向き・状態異常・書き込む値）→ 種類の `states`、いつも出すものは `show_state`、計算する値（残り HP など）は `derived`
   - 時間 → `flow`（段階・手番・フェーズ、`main`・`free`（`phases` で絞る）・`reactions`、フェーズの `max`・`each`、手番の初めの `on_start`）
   - 行為 → `actions`（`params` の `from`・`kind`・`require`、`steps` の `op`・`let`・`each`・`if`・`call`。結果を読む効果は `stepwise: true`）
   - 割り込み → アクションの `stack: true`、打ち消しは `cancel`。会話 → `say`（`--to`）、守られる約束 → `offer`。隠れた行為 → `secret: true`、夜の内緒話 → 段階の `whisper: hidden`
   - 何度も使う式 → `functions`。数える値 → `metrics`。知らせ → `signals`（プレイヤーに見せるなら `public: true`）
   - 終わり → `flow.end_when` に `winners`・`losers`（式）か `draw` か `winners: scoring`（`flow.scoring` の得点と同点の比べ方）、`timing`（その巡を終えてからなら round_end）。自動で終えるなら `flow.auto_end: true`。手番の終わりの処理（手札の上限など）は手番の `on_end`。型ごとの書き方は `specs/versions/v1/okf/notes/endgame/gates.md`。得点の道（マスを進む駒）・即時得点・決まった時機の得点計算は `examples/harvest-road.yaml`。トークン（駒・キューブ・円盤）は種類の `shape`（round・disc・cube・pawn・tile）
   - 遊ぶ人の手引きより細かい文（大会の総合ルール・審判用の決まり）は、`rules` に `detail: true` で書く（手引きに出さない。CTR-F-001 r4）。アクションの `rule` は、実装した詳細ルールの節を指す。手本は `specs/versions/v1/okf/notes/detail-rules/gates.md`
   - 隠れた情報のある作品は `game.strict: true`（外れた行為を記録しない）
3. **ルールを書く**：`rules` に自然文で、ID（R1…）と `refs`（関係する部品・エリア・用語）を付ける。アクションの `rule` で結ぶ。機械で決めない判断（効果の解釈・裁定）は自然文に残す。
4. **確かめる**（すべて通るまで直す）
   ```bash
   bg check <定義>                         # 参照・式・名前の打ち間違い
   bg fuzz <定義> --players N --steps 150   # 式の誤り・エンジンの不具合・一度も行えないアクション
   bg new /tmp/... --def <定義> --players N --seed 1 && bg act ... setup   # 準備が通るか
   ```
   - `never_done` に残るアクションは、条件が厳しすぎるか、進行の `flow` に入っていない。意図どおりか確かめる。
   - `expr_errors` は、物がない局面（配る前・場が空）で式が読めないことが多い。`on1(...) and ...` のように守る。
5. **報告**：作った定義の場所、原型への当てはめ（表）、自然文に残したもの、`open_questions`、`bg fuzz` の結果。次は bg-playtest。

## 形式の項目が足りないと思ったら

- まず既存の項目（CTR-F-001 の「派生」の表、`src/bgskills/schema.py`）で書けないかを確かめる。`bg check` は形式に無い項目を似た項目つきで知らせる。
- 書けないと示せたときだけ、どこが書けないかを報告する（形式を足すのは CTR-F-001 の版を上げる変更。RUL-016）。

## やらないこと

- 既存の作品の名前・キャラクター・カードを写すこと。
- ルールの中身を自動で裁くエンジンを作ること（効果は手順で書き、解釈は自然文とキーパー）。
- エンジン（`src/bgskills`）を直すこと。定義で書けないと分かったら、どこが書けないかを報告する（RUL-005：派生で表せないものだけ原型に足す）。
