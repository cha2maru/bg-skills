---
name: bg-balance
description: bg-skills のゲーム定義のバランス（先手の有利・勝率の偏り・局の長さ・使われないカードやルール）を、多数局で測り、案（variants/）で数値を 1 つずつ変えて、勝ちの割合の 95% の幅（win_ci）と符号検定で比べる。「バランスを調整して」「先手が強すぎないか」「このカードは強すぎる？」「balance my game」「is the first player too strong」と言われたとき、ルールがおおむね固まり数値を詰める段階で使う。ルールそのものを変えて試す段階は bg-iterate、強い手で比べるための思考ルーチンを作るのは bg-ai。
---

# bg-balance：測って、1 つ変えて、比べる

> **どこで使っても**：`bg` はプラグインが PATH に入れるコマンド（このリポジトリの中なら `uv run bg`）。コマンドの一覧は `<プラグインのルート>/docs/commands.md`、案の重ね方と試行の記録の形は `<プラグインのルート>/specs/versions/v2/okf/contracts/CTR-F-007.md`。作業場は bg-start（bg init）で作ったもの。

## 手順

1. **何を測るかを決める**：先手・後手の勝率、陣営（デッキ）ごとの勝率、局の長さ（手番数）、決着しない割合、使われないアクション・ルール（`bg stats` の未使用）。一度に 1 つ。
2. **今を測る**
   - `bg selfplay game.yaml --players N --games 30 --record experiments.jsonl --note "<問い>"`。でたらめの手なので、終わり方の偏り・長さ・決着しない穴の目安。
   - 戦略のある作品は思考ルーチンで（無ければ bg-ai で作る）：`bg league game.yaml --bot a=bots/a.py --bot b=bots/b.py --players N --games 20 --record experiments.jsonl`。席を回すので、方針の強さと席の有利を分けて読める。
3. **案を書く**：`variants/<名前>.yaml` に、変える数値 1 か所だけ（HP・コスト・枚数・得点など。同じ id の要素を書くと差し替わる）。ルールの文（rules）の数字も一緒に直す。`bg check game.yaml --with variants/<名前>.yaml` で通るか確かめる。
4. **比べる**
   - `bg compare game.yaml --variant <名前>=variants/<名前>.yaml --players N --games 30 --record experiments.jsonl --note "<何を確かめたいか>"`
   - 思考ルーチンがあれば `bg league game.yaml --bot ... --players N --games 20 --with variants/<名前>.yaml --record experiments.jsonl --note ...`
5. **差が偶然でないか読む**
   - `win_ci`（席ごと・方針ごとの勝ちの割合の 95% の幅 [下, 上]）を `win_rate` に添える。元と案の幅が大きく重なるなら「偏りは見えない」と報告する。局数を増やすと幅は狭まる。
   - league の `paired.sign_test_p`（同じ種の対局どうしで、どちらが多く勝ったか）。0.05 より大きければ差は偶然の範囲。
6. **取り込む**：採るなら bg-iterate の「取り込む」の手順（案を `game.yaml` に移し `game.version` を上げ、`journal.md` に根拠の試行を書く）。採らないなら、記録を残して次の 1 か所へ。

## 報告

表（案・変えた所・局数・win_rate と win_ci・avg_turns・undecided_rate、league なら sign_test_p）、推奨の変更 1 つと理由、測っていないこと（思考ルーチンの弱さ・偏った戦略など）。ルールの文も直したら bg-rules-audit で確かめる。

## 注意

- 思考ルーチンの偏りは、ゲームの偏りと区別できない。2 種（random と欲張りなど）で同じ傾向か確かめる。
- 数値を同時に 2 つ以上変えない。組み合わせるなら、共通の案を `--with` で重ね、比べる案だけを `--variant` にする。
- 試行の記録は追記だけ。比べるときは同じ種（`--seed`）・同じ局数で。
