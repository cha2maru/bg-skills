---
type: functional-contract
id: CTR-F-005
revision: 1
title: 卓の画面定義
provider: /structure/CMP-0105.md
format: ui
thickness: thick
elements: [OBJ-010501]
status: draft
tags: []
---

# CTR-F-005：卓の画面定義

## Parties

| 立場 | コンポーネント・開発オブジェクト | 使う要素 |
|---|---|---|
| 提供 | CMP-0105 卓の画面 | 全画面 |
| 利用 | ゲーム設計者・エージェント | OBJ-010501 |

## Screens

1 画面（卓）。見る立場（`?as=`）を切り替える。

## Common Rules

- 部品のドラッグ・キー操作（F 表裏、T・ダブルクリック 回転、Shift 重ねる、Alt 下に差し込む）は bg op と同じ記録に入る
- 表示の切り替え（ID・状態・公開範囲など）とたたみは表示だけで、局面と記録を変えない
