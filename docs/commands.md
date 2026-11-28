# bg コマンドの手引き

`bg` はプラグインが PATH に入れるコマンド（このリポジトリの中なら `uv run bg`）。ここに無い引数は `bg <コマンド> --help` で見る。例の `examples/` はプラグインのルートの中の手本の定義。作る定義・対局は、自分のプロジェクトに置く。

## 始める

```bash
bg init games/mygame --name 私のゲーム --players 2-4   # 作業場（game.yaml・variants/・experiments.jsonl・journal.md）
bg schema > bg-def.schema.json                         # 定義の形式（JSON Schema）。エディタの補完に
```

## 定義を確かめる

```bash
bg check examples/kagaribi.yaml                 # 参照・式・形式・言葉（wording）の確認
bg fuzz examples/beast-duel.yaml --players 2    # でたらめ実行：式の誤り・エンジンの不具合・一度も行えないアクション（--steps で長さ）
bg expand examples/kagaribi.yaml --players 2    # 略記（for_each・copies・layout）を展開した形
bg refs examples/kagaribi.yaml <ID>             # その ID を参照するルール
bg diff 古い.yaml 新しい.yaml                    # 2 つの版の違い
bg complexity examples/kagaribi.yaml            # ルールの複雑さの目安。machine_layer（ルールごとの機械の層）と rules_text_only（文だけのルール）
bg rulings examples/rune-clash.yaml             # 定義の裁定（決まった・未決・一般の原則）
bg quiz examples/tic-tac-toe.yaml --players 2 --out quiz/   # 「今この手を行えるか」の小テスト（quiz.yaml と、別に answers.yaml）
bg quiz-grade quiz/answers.yaml 答え.yaml                     # 小テストの採点（答えは {問の id: yes|no}）
```

`check`・`new`・`fuzz`・`selfplay`・`complexity`・`status`・`rulebook` は `--with 案.yaml`（何枚でも）で案を重ねられる。

## 対局

```bash
bg new sessions/s1 --def examples/kagaribi.yaml --players 2 --seat P1=agent:a --seed 1
bg new sessions/b1 --def examples/kagaribi.yaml --players 2 --from-box   # 箱から始める（準備の手順を確かめる）
# 定義の game.strict（人狼など）は厳格モードが既定。試し遊びで警告だけにするなら --lenient
bg act sessions/b1 setup --by P1                # 定義のアクション（手順をすべて行うか、1 つも行わない）。引数は --arg card=W5-2
bg setup-check sessions/b1                      # 定義の初期の置き場と比べる
bg candidates sessions/s1 <アクション> --by P1 --param <引数>   # 引数の候補と条件（--param を省くと全部の引数）
bg op sessions/s1 '{"op":"move","obj":"N4","to":"discard","by":"P2","rule":"R4"}'   # 基本の操作を 1 つ
bg advance sessions/s1 --to turn                # 進行を次へ（phase・turn・stage）。ワザを使わずに手番を終えるなど
bg undo sessions/s1                             # 最後の操作（アクションなら全部）を取り消す
bg pass sessions/s1 --by P2                     # スタックの解決を見送る
bg resolve sessions/s1                          # スタックの一番上を解決する（キーパー。見送りを待たない）
bg rebase sessions/s1                           # 定義を直した後、記録が再生できれば対局を今の定義に合わせる
```

発言と提案：

```bash
bg say sessions/s1 "こんにちは" --by P1 --to P2   # 発言（--to を省くと全員。付けると内緒話）
bg say sessions/s1 "木 2 と鉱石 1" --by P1 --to P2 --offer '[{"op":"move","obj":"res-lumber","from":"hand-P1","to":"hand-P2","n":2}]'   # 提案（受けたらまとめて行う）
bg answer sessions/s1 3 --by P2                 # 提案（bg show の talk の n）を受ける。--decline で断る・出した人なら取り下げ
# 提案に --action trade-players（か定義の flow.offer_action）を付けると、成立したとき手番・条件を確かめる
```

## 見え方

```bash
bg show sessions/s1 --as P2 --meaning           # P2 の見え方（--as を省くとキーパー）
bg show sessions/s1 --as P1 --compact --links   # 短い局面（エージェント向け）とリンク。発言は最後の 10 件、--talk-since N で番号から
bg show sessions/s1 --as P1 --compact --only hand-P1,talk,offers_for_me   # 一部だけ（エリアと局面の部分）
bg near sessions/s1 <エリア> --type corner        # リンク先と中身
bg log sessions/s1 --as P1                      # 操作の記録（P1 に見える形）
bg serve sessions/s1 --host 127.0.0.1           # 卓の画面（http://127.0.0.1:8765/）。画面の「見る立場」で席を選ぶ
```

画面（`bg serve`）は部品をさわれる卓で、ゲームエンジンではない。画面の操作も `bg op` も同じ記録に入る。認証が無いので、外に公開しない。

## 改訂と比べる

```bash
bg status games/mygame/game.yaml --experiments games/mygame/experiments.jsonl   # 設計の状態（決まっていないこと・最近の試行）
bg selfplay examples/rune-clash.yaml --players 2 --games 30   # でたらめの対戦（終わり方の偏りと局の長さの目安）。--record で記録
bg compare games/mygame/game.yaml --variant hand-5=games/mygame/variants/hand-5.yaml --players 2 --games 30 --record games/mygame/experiments.jsonl --note "何を確かめるか"   # 元と案を比べて記録
bg experiments games/mygame/experiments.jsonl --last 5   # 試行の記録（新しい順）
bg stats sessions/s1 sessions/s2                # 対局の記録の集計（使われなかったルールなど）
bg playstats sessions/s1                        # 対局の物差し：拒否された回数・手番あたりのコマンド数
```

## 思考ルーチン

```bash
bg league examples/harvest-road.yaml --bot greedy=examples/bots/harvest-greedy.py --bot random --players 2 --games 20 --trace trace.jsonl   # リーグ戦（席を回す。符号検定）
```

- `bg bot-step sessions/s1 --human P1 --bot P2=bots/greedy.py`：P1 の番が来るか対局が終わるまで、ほかの席を思考ルーチンが進める（`--bot P3=random`、`--max N`。印のない席はでたらめ）。P1 は画面か `bg act` で指し、手番を終えたら（行えるアクションが残っていなければ `bg advance --to turn --by P1`）また bot-step。出力：止まった理由（human・ended・stuck・max）、足した手の数、人の席が 1 つなら足した手（`moves`。その席に見える形）、終わったら `result`。画面と同時に書いても、古い局面で選んだ手は記録しない。

## 手引きと書き出し

```bash
bg rulebook games/mygame/game.yaml > RULES.md   # 人が読む手引き（詳細ルール・未決の裁定は出さない）
bg tts sessions/s1 --out exports/s1.json        # Tabletop Simulator の Saved Object に書き出す（Saves/Saved Objects に置く）
```
