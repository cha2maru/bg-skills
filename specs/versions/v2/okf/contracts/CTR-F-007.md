---
type: functional-contract
id: CTR-F-007
revision: 2
title: 設計の作業場の形式（ゲームのフォルダ・案の重ね方・試行の記録）
provider: /structure/CMP-0104.md
format: file-format
thickness: thin
elements: [ゲームの作業場, 案, 試行の記録, 思考ルーチン]
status: stable
tags: [v2]
implementation: []
---

# CTR-F-007：設計の作業場の形式（ゲームのフォルダ・案の重ね方・試行の記録）

## Parties

| 立場 | システム・開発オブジェクト | 責任者 |
|---|---|---|
| 提供 | CMP-0104 コマンド（OBJ-010401 bg コマンド・OBJ-010102 定義の道具） | 記載なし |
| 利用 | ゲーム設計者、OBJ-010803 導入と改訂のスキル、OBJ-010802 振り返りとバランスのスキル | 記載なし |

## Files and Placement

`bg init <フォルダ>` が作る。利用者のプロジェクトの中に置く（プラグインのフォルダではない）。

| パス | 中身 |
|---|---|
| `game.yaml` | ゲームの定義（CTR-F-001）。雛形のまま bg check・bg selfplay が通る |
| `variants/<名前>.yaml` | 案：定義の断片（CTR-F-001 と同じ形式の一部）。`--with` で重ねる |
| `experiments.jsonl` | 試行の記録（1 行 1 試行。追記だけ） |
| `journal.md` | 設計の日誌（版ごとに、変えたこと・理由・根拠の試行） |
| `bots/<名前>.md`・`bots/<名前>.py` | 思考ルーチン：考える順番（人が読む表）と、`choose(ctx)` を持つ Python（r2、RUL-030） |
| `sessions/` | 対局のフォルダ（CTR-F-002）。`.gitignore` で git の外 |

## 案の重ね方

定義に案を順に重ね、最後にシナリオ（CTR-F-002）を重ねる。

- 辞書（game・kinds・flow など）は中まで重ねる（案の値が勝つ）。
- 並び（areas・objects・actions・rules・rulings など）の要素は、`id` が同じなら案の要素で差し替え、無ければ足す。`id` の無い要素（links など）は足す。
- 要素を消すときは、トップの `remove: [id…]`（重ねた後に、その id の要素を並びから除く）。
- 対局は、重ねた案を対局のフォルダに `variant-<n>.yaml` として写し、`session.yaml` の `variants` に名前を残す（定義を直しても、その対局の案は変わらない）。

## 試行の記録（1 行）

| キー | 意味 |
|---|---|
| time | 記録した日時（UTC） |
| game・version | 定義の game.id・game.version |
| def_hash | 定義と重ねた案の指紋（中身が同じなら同じ） |
| variants | 重ねた案の名前の並び（元だけなら空） |
| players・games・seed・max_turns | 回した条件 |
| tool | selfplay・compare・league（league の result は方針ごとの結果と paired） |
| result | 結果（終わり方ごとの数、平均の手番数） |
| note | 利用者の書き添え（`--note`） |
