---
name: bg-start
description: bg-skills のプラグインを入れた後に、自作のボードゲームの作業場を作り、最初の定義を確かめて 1 局回すところまで案内する。「ボードゲームを作り始めたい」「bg-skills を使い始めたい」「自分のゲームを定義にしたい（まだ何もない）」と言われたとき、プラグインを入れた直後に使う。定義を書き込むのは bg-design、改訂の繰り返しは bg-iterate。
---

# bg-start：入れてから最初の 1 局まで

> **どこで使っても**：`bg` はプラグインが PATH に入れるコマンド（このリポジトリの中なら `uv run bg`）。作業場は利用者のプロジェクトに作る（プラグインのフォルダには作らない）。形式の説明は `<プラグインのルート>/specs/versions/v2/okf/contracts/CTR-F-001.md`、作業場の形は同じフォルダの `CTR-F-007.md`（プラグインのルートは、このスキルのディレクトリから 2 つ上）。

## 手順

1. **入っているかを確かめる**：`bg --help` が動くか。動かなければ、uv が入っているか（`uv --version`）を確かめ、無ければ https://docs.astral.sh/uv/ の入れ方を案内する。プラグインが無ければ `/plugin marketplace add <bg-skills の git の URL かフォルダ>` と `/plugin install bg-skills@bg-skills` を案内する。
2. **作業場を作る**：ゲームの名前と人数を聞き（分からなければ仮の名前と 2-4）、`bg init games/<名前> --name <名前> --players <人数>`。できるもの：`game.yaml`（動く最小の雛形）・`variants/`（案の例）・`experiments.jsonl`（試行の記録）・`journal.md`（設計の日誌）・`.gitignore`（sessions/）。
3. **雛形のまま回す**（道具が動くことを見せる）：
   ```bash
   bg check games/<名前>/game.yaml
   bg selfplay games/<名前>/game.yaml --players 2 --games 10 --record games/<名前>/experiments.jsonl --note 雛形
   bg status games/<名前>/game.yaml --experiments games/<名前>/experiments.jsonl
   ```
4. **アイデアを聞く**：一言の概要、人数、部品（カード・駒・盤）、手番に何をするか、どう終わり誰が勝つか。決まっていないことは決まっていないままでよい（無理に決めない）。
5. **bg-design に渡す**：聞いたことを bg-design の手順で `game.yaml` に起こす。決まっていない点は `game.open_questions` と、`rulings` の `status: open`（問いだけ）に残す。決まった所だけを機械の層（アクション・進行・終わり）にする。
6. **最初の 1 局**：`bg check`・`bg fuzz` を通し、`bg selfplay` で終わりまで進むかを見る。人の目で見るなら `bg new sessions/s1 --def game.yaml --players 2` と `bg serve sessions/s1 --host 127.0.0.1`（認証が無いので外に公開しない）。仲間に渡す手引きは `bg rulebook game.yaml > RULES.md`。
7. **次へ**：改訂を始めるなら bg-iterate。エージェントに遊ばせるなら bg-playtest。

## 報告

作った作業場の場所、雛形の selfplay の結果、起こした定義の要点、決まっていないこと（open_questions・未決の裁定）、次にすること。

## 注意

- 既存の市販品を再現する定義は公開しない（作業場を公開するリポジトリに置かない）。
- 作業場は git で管理するとよい（試行の記録と日誌が改訂の根拠になる）。sessions/ は .gitignore 済み。
