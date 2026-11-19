---
type: functional-contract
id: CTR-F-002
revision: 1
title: 対局のフォルダの形式
provider: /structure/CMP-0102.md
format: file-format
thickness: thin
elements: [対局の情報, 操作の記録, シナリオの写し]
status: draft
tags: []
implementation: []
---

# CTR-F-002：対局のフォルダの形式

## Parties

| 立場 | システム・開発オブジェクト | 責任者 |
|---|---|---|
| 提供 | CMP-0102 局面と記録（OBJ-010201） | 記載なし |
| 利用 | OBJ-010401 bg コマンド、OBJ-010601〜06 画面の API、OBJ-010802 振り返りのスキル | 記載なし |

## Files and Placement

`sessions/<名前>/`（git 管理外）。`meta.json`（対局の情報）、`log.jsonl`（操作の記録。1 行 1 操作）、`scenario.yaml`（シナリオの写し。あれば）。

## Structure

局面は保存しない。局面＝定義の初期の置き場（箱から始めるなら箱）に、記録の操作を先頭から適用したもの。乱数は `seed:操作の通し番号`。

## Fields

| キー | 型 | 必須 | 値 | 意味 |
|---|---|---|---|---|
| meta.definition | 文字列 | ○ | 定義のパス | どの定義か |
| meta.def_hash | 文字列 | ○ | | 定義の版の確かめ（違えば警告） |
| meta.players・seats・seed | | ○ | | 人数・席ごとの着席者・乱数の種 |
| meta.start・strict・scenario | | | box・true・scenario.yaml | 箱から始める・厳格モード・シナリオ |
| log の各行 | 辞書 | ○ | op・by・rule・action・act・time と操作ごとのキー | 操作 1 件 |

## Validation Rules

- 置き場の決まりに反する操作は記録しない（SPC-016）。厳格モードでは警告のある操作も記録しない
- アクションの操作は、すべて記録するか、1 つも記録しない

## Example

```json
{"op": "move", "obj": "N4", "to": "discard", "by": "P2", "rule": "R4", "time": "2026-11-19T10:00:00"}
```

## Compatibility

記録は追記だけ。知らない操作の種類があれば読み込みを止める。
