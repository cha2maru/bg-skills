---
type: functional-contract
id: CTR-F-006
revision: 1
title: TTS の Saved Object
provider: /structure/CMP-0107.md
format: file-format
thickness: thick
elements: [Saved Object, サムネイルと面の画像]
external_users: [Tabletop Simulator]
status: stable
tags: []
implementation: []
---

# CTR-F-006：TTS の Saved Object

## Parties

| 立場 | システム・開発オブジェクト | 責任者 |
|---|---|---|
| 提供 | CMP-0107 書き出し（OBJ-010701） | 記載なし |
| 利用 | Tabletop Simulator（Saves/Saved Objects に置く） | 記載なし |

## Files and Placement

`exports/<名前>.json` と同名の PNG（サムネイル）、無地の表裏の画像。

## Structure

ObjectStates に 1 つの Bag。中にエリアごとの Deck・Card・HandTrigger、六角の位置、状態の表示方法に合わせた回転。

## Validation Rules

実機で確かめていない点がある（山の上下など）。山の上は今の書き出しの順のまま。実機で逆と分かったら直す（推奨で決めた。RUL-018）

## Compatibility

TTS の Saved Object の形式に従う。
