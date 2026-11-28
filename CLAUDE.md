# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## プロジェクトの目的

ボードゲームを構成する情報（コンポーネント、状態、ルール、手番進行など）を抽象化し、それを操作できる汎用環境を開発する。
この環境をエージェントが使い、次のことを行えるようにするのが目標。

- 新しいボードゲームの設計とテストプレイ
- 既存ボードゲームのテストプレイ
- シミュレーション結果にもとづくバランス調整

特定のゲーム専用の実装ではなく、複数のゲームを同じ抽象で表現できる設計を優先すること。

概念の一覧と、再現できないもの・必要な概念の整理は `specs/versions/v2/okf/notes/concept-review.md`。概念モデル（原型 8 つと派生）と構造は `contracts/CTR-F-001.md` と `structure/`。定義に現れるものは、できる限りエリアとオブジェクトの派生（kinds の base）で表す（RUL-005）。

形の盤（RUL-025）：親のエリアの `viewbox`（座標系）と子の `path`（SVG のパス。曲線・円弧・飛び地）で、ボードの絵の上の領域や実物の地図の州を描く（中身は `xy` に置く）。見栄えのための配置場所は子に `slot: true`（部品は親に置き、画面が 1 つずつ並べる。RUL-026）。画像：定義の `assets.root`（画像の置き場）と、エリアの `image`（背景）、部品・種類の `image`・`back_image`（`{default, "状態=値"}` で状態ごとに替えられる）。画面は `/assets/` で root の下だけを配る。惨劇RoopeR の再現（`local/tragedy-looper.yaml`、生成は `local/gen_tl.py`）は sangeki の惨劇コモンズ5th を指す（利用は惨劇RoopeR 関連に限る。公開時は「惨劇コモンズ作成：BakaFire・紺ノ玲」とリンクを表記）。

サンプル：`examples/` に三目並べ・かがり火・六角・オセロ・チェス（名前つきの式 `functions` でチェック）・将棋・麻雀・人狼・精霊獣デュエル（架空。カードの効果とステータス、アクションの `stepwise`）・ルーン決闘（架空。スタックで割り込む、アクションの `cost`）・収穫の道（架空。得点の道・即時得点・巡の終わりの得点・終わりの得点）（古典は公開してよい）。`local/` に花火・ディプロマシー（生成 `local/gen_dip.py`。州の形は jDip の地図 `local/dip/standard.svg`、GPL）・新幕 桜降る代に決闘を（生成 `local/gen_furuyoni.py`。総合ルールを詳細ルールに。ボードはふるよにコモンズの board.png に形を重ねる。出典『桜降る代に決闘を』BakaFire Party を明記し非営利に限る。画像は使っていない。コモンズの画像を使うなら「ふるよにコモンズ/BakaFire,TOKIAME」と rule.html へのリンク）など市販品の再現。デモの対局は `local/social-demos.py` で作り直す。

終わり方（RUL-015、notes/endgame/gates.md）：`flow.end_when` の各件に `winners`・`losers`（式）・`draw`・`winners: scoring` と `timing`（now・turn_end・round_end）、`flow.auto_end` で結果を記録して終える、`flow.scoring`（by・tiebreak）で順位、手番の `on_end` で手番の終わりの処理。`bg complexity` でルールの複雑さの目安。

割り込み（RUL-013）：アクションの `stack: true` は解決待ちの列に積み、ほかの人が応じて積むか `bg pass` で見送ると、後から積んだもの（`flow.stack: fifo` なら先）から解決する。打ち消しは手順の `cancel`（引数の `stack: true`）。例は `tests/test_stack.py`。

発言と隠れた情報（RUL-009）：発言は操作 `say`（`bg say`。`--to` で内緒話。`offer` で提案、`answer` で受ける・断る＝守られる約束）、話せない時間は進行の `talk`。書き込む状態（種類の状態に型 text・player）、公開範囲 `others`、`know` の `fields`（一部だけの知識）、アクションの `secret`。

目的の中心は「エージェントが不足なく読めるゲームの定義」（`specs/` の RUL-001 #25・#28）。物差しは `bg quiz`（定義と見え方だけを読んで「今この手を行えるか」に答えられるか）と `bg playstats`（対局で拒否された回数・手番あたりのコマンド数）。

ルールの層（RUL-016。#31 を改めた）：
- **ルールの文（`rules`）が正本**。エージェントもキーパーもまず文を読む。
- **詳細ルール**（RUL-024）：審判用の総合ルールのように手引きには出さないが定義には要る文は、`rules` に `detail: true`。画面のルール欄ではたたみ、TTS には出さない。強さは詳細ルール＞手引きのルール＞裁定＞機械の層。整理は `specs/versions/v2/okf/notes/detail-rules/gates.md`。
- **機械の層は、作品が選んで書いた分だけ**：条件（`require`・進行の区分と回数）、手順（`steps`・`on_start`・`on_end`・スタック）、終わり（`end_when` の結果・`scoring`）。参照・置き場・乱数・見え方は、どの作品でも機械で行う。
- **裁定（`rulings`、RUL-017）は、文で決まらない点（ルールの穴）を決める**。1 件ごとに問い・裁定・理由・関わるルール・出典・重み（`authority`：official＞author＞designer＞keeper）・日付・見つかった対局を書く。決まっていない穴も `status: open` で書く（分かっている穴）。一般の原則は `principle: true`。sangeki の `wiki/notes/rulings.md` の書き方にならった。
- 強さの順：ルールの文＞裁定＞機械の層。機械の層が文や裁定と食い違ったら、機械の層の不具合として直す。一次資料で明文が見つかったら、裁定のほうを直す。機械の層も裁定もない点は、キーパーが文で裁き、対局の裁定（`bg op` の ruling）に残す。`bg rulings <対局>` で定義へ持ち帰る候補が出る。`bg complexity` の `machine_layer` でルールごとの機械の層、`rules_text_only` で文だけのルールが分かる。
- **形式を膨らませない**（RUL-016 の 6）：形式の項目の正本は `src/bgskills/schema.py`（CTR-F-001 r2、確定）。項目を足すのは、既存の項目では書けないと示せたときだけで、足すときは CTR-F-001 の版を上げる。新しい作品は、項目を足さずに書けるかの試験として使う。
- プレイヤーに出すものは、局面なら `view.py`、記録なら `redact.py` を必ず通す。出口（コマンド・画面の API）を足したら `tests/test_leaks.py` に足す。
- 機械の層をどれだけ強く効かせるかは対局ごとに選ぶ：警告だけ（既定）か、厳格モード（外れた行為を記録しない。`game.strict` で作品の既定にできる）。

Python なしで使える範囲と考え方は `docs/without-python.md`、形式の JSON Schema は `docs/bg-def.schema.json`（`uv run bg schema > docs/bg-def.schema.json` で作り直す。形式を変えたら作り直す）。

## スキル（skills/。.claude/skills はそのリンク）

Claude Code のプラグインとして配る（RUL-021。`.claude-plugin/`、`bin/bg`、README.md）。確かめ：`claude plugin validate .`。

自作のゲームを始めるとき：`bg-start`（`bg init` で作業場 → 最初の 1 局）。改訂の 1 周：`bg-iterate`（`bg status` → 案 `variants/*.yaml` → `bg compare --record` → 取り込んで版を上げ `journal.md`。第二版、RUL-028・CTR-F-007）。思考ルーチン：`bg-ai`（考える順番を `bots/<名前>.md` に書き、`choose(ctx)` の `bots/<名前>.py` にして `bg league` で測る。思考ルーチンは合法手とその席の見え方だけを受け取る。sangeki の流れ、RUL-030）。新しいゲームを作るとき：`bg-design`（アイデア → 定義、bg check・bg fuzz まで）→ `bg-playtest`（エージェントに席ごとに遊ばせる）→ `bg-balance`（多数局で測り、数値を 1 つずつ変えて比べる）。点検：`bg-hidden-info-audit`（隠れた情報の漏れのチェック表）、`bg-rules-audit`（ルール文と定義の突き合わせ）。

利用者向けのコマンドの手引きは `docs/commands.md`（スキルはこれを指す。プラグインでは CLAUDE.md は読まれない）。下の「コマンド」の節を変えたら、開発者向けの例・local/ を除いて手引きもそろえる。

## 仕様と記録

- `specs/versions/v2/okf/`：okf-specs のバンドル（裁定 RUL、要望 WSH、要求 REQ、要件 SPC）。チェック：`python3 <okf-spec>/tools/okf_check.py specs/versions/v2/okf`
- 版：`specs/versions/v1` は固めた版（`okf.yaml` の `frozen: true`。読むだけ・直さない）。作業中は `v2`（`base: ../../v1/okf`。差は `okf_check.py specs/versions/v2/okf changes`）
- `specs/versions/v2/okf/notes/*/gates.md`：推奨案で決めた判断の記録
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
uv run bg serve sessions/s1 --host <WSL の内側のアドレス>   # 画面（Windows から http://<WSL の内側のアドレス>:8765/ ）
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
uv run bg init games/mygame --name 私のゲーム --players 2-4   # 作業場（game.yaml・variants/・experiments.jsonl・journal.md）
uv run bg compare games/mygame/game.yaml --variant hand-5=games/mygame/variants/hand-5.yaml --players 2 --games 30 --record games/mygame/experiments.jsonl  # 元と案を比べて記録
uv run bg status games/mygame/game.yaml --experiments games/mygame/experiments.jsonl   # 設計の状態（決まっていないこと・最近の試行）
uv run bg experiments games/mygame/experiments.jsonl --last 5   # 試行の記録（新しい順）
uv run bg rulebook games/mygame/game.yaml > RULES.md   # 人が読む手引き（詳細ルール・未決の裁定は出さない）
uv run bg league examples/harvest-road.yaml --bot greedy=examples/bots/harvest-greedy.py --bot random --players 2 --games 20 --trace trace.jsonl  # 思考ルーチンのリーグ戦（席を回す。符号検定。RUL-030）
uv run bg bot-step sessions/s1 --human P1 --bot P2=examples/bots/harvest-greedy.py   # P1 の番まで、ほかの席を思考ルーチンで進める（目隠しの対戦・人と遊ぶ）
# check・new・fuzz・selfplay・complexity・status・rulebook は --with 案.yaml（何枚でも）で案を重ねる
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
