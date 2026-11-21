---
name: bg-iterate
description: 自作のボードゲームの定義を、回しながら改訂する 1 周（設計の状態を見る → 案を作る → 元と比べる → 試行を記録する → 取り込むか決めて版を上げ日誌に書く）を進める。「ルールを変えて試したい」「この数値はどっちがいい？」「改訂して」「シミュレーションしながら調整したい」と言われたとき、ルールがまだ固まっていない段階で使う。作業場は bg-start（bg init）で作ったもの。勝率の細かい調整は bg-balance、エージェントの試し遊びは bg-playtest。
---

# bg-iterate：回しながら改訂する 1 周

> **どこで使っても**：`bg` はプラグインが PATH に入れるコマンド（このリポジトリの中なら `uv run bg`）。案の重ね方と試行の記録の形は `<プラグインのルート>/specs/versions/v2/okf/contracts/CTR-F-007.md`。

## 1 周の手順

1. **状態を見る**：`bg status game.yaml --experiments experiments.jsonl`。決まっていないこと（未決の裁定・open_questions・文だけのルール）と、最近の試行を読む。今回決めること・試すことを 1 つ選ぶ（一度に 1 つ。比べた差が何から来たか分かるように）。
2. **案を書く**：`variants/<名前>.yaml` に、変えるところだけを書く（定義と同じ形式の断片）。
   - 数値・文を変える：同じ id の要素を書くと差し替わる（アクション・ルール・部品・裁定）。辞書（game・flow・kinds）は中まで重なる。
   - 足す：新しい id の要素を書く。消す：`remove: [id]`。
   - ルールの文（rules）も一緒に直す（文が正本。機械の層だけ変えない）。
   - `bg check game.yaml --with variants/<名前>.yaml` と `bg fuzz ... --with ...` で通るかを確かめる。
3. **比べる**：`bg compare game.yaml --variant <名前>=variants/<名前>.yaml --players N --games 30 --record experiments.jsonl --note "<何を確かめたいか>"`。人数を変えて数回。見るもの：
   - `win_rate`（席ごとの勝ちの割合。先手の有利）
   - `avg_turns`（長さ）
   - `undecided_rate`（決着しない割合。高ければ終わり方の穴）
   - `outcome_rates`（どの終わり方で終わるか）
   でたらめの手での目安なので、差が小さければ「差は無い」と読む。強い手での比較が要るなら bg-balance（作品のボット）。
4. **決める**：取り込む・やめる・別の案を試す、のどれか。決めきれない点は未決の裁定（status: open）に問いとして残す。
5. **取り込む**（取り込むと決めたら）：
   - 案の中身を `game.yaml` に移し、`game.version` を 1 上げる（版が対局と試行の記録の区切り）。
   - `journal.md` に「版 N：変えたこと・理由・根拠の試行（experiments.jsonl の日時）」を書く。
   - 決まった点は裁定（rulings）を decided にし、open_questions から消す。
   - 古い対局を続けるなら `bg rebase sessions/<対局>`（再生できなければ作り直す）。
   - 案のファイルは消すか、`variants/old/` に移す。
6. **次の 1 周へ**：`bg status` に戻る。人と遊んで確かめたくなったら `bg rulebook game.yaml > RULES.md` と `bg serve`。エージェントに遊ばせて穴を拾うなら bg-playtest。

## 報告

試したこと（案と問い）、比べた結果の表（案ごとの win_rate・avg_turns・undecided_rate）、決めたことと理由、版を上げたか、残った問い。

## 注意

- 試行の記録は追記だけ（消さない・書き換えない）。改訂の根拠になる。
- 一度に複数を変えると、差がどこから来たか分からない。どうしても組み合わせるなら `--with` で共通の案を重ね、比べる案だけを `--variant` にする。
- selfplay はでたらめの手なので、「戦略のあるゲームの強さ」は測れない。終わるか・長さ・明らかな偏り・決着しない穴を見る道具として使う。
