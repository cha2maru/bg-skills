---
type: functional-contract
id: CTR-F-003
revision: 1
title: 読み取りの出力の形式（見え方・候補・指標・進行）
provider: /structure/CMP-0103.md
format: file-format
thickness: thick
elements: [局面の見え方, 意味つきの局面, 候補, 指標, 進行の要約, 操作の結果]
external_users: [エージェント（bg コマンドの JSON を読む）]
status: stable
tags: []
implementation: []
---

# CTR-F-003：読み取りの出力の形式（見え方・候補・指標・進行）

エージェントが局面を読む窓口。見え方を守る（見えないものは理由とともに伏せる）。

## Parties

| 立場 | システム・開発オブジェクト | 責任者 |
|---|---|---|
| 提供 | CMP-0103 読み取り（OBJ-010301〜03） | 記載なし |
| 利用 | OBJ-010401 bg コマンド、OBJ-010601〜06 画面の API、エージェント | 記載なし |

## Files and Placement

ファイルにはせず、bg コマンドの標準出力と画面の API の応答（JSON、UTF-8）。

## Structure

局面の見え方：`{viewer, areas{<id>: {parent, shown, hidden}}, flow{stage, phase, active, available, signals, end_signals}, metrics{<id>: {value|values}}, legend}`。候補：`{<引数>: [{id, problems}], action_problems}`。操作の結果：`{ok, seq, done, warnings, flow}`。

## Fields

| キー | 型 | 必須 | 値 | 意味 |
|---|---|---|---|---|
| areas.<id>.shown | 並びか {count} | ○ | | 見えるもの（見えなければ枚数だけ） |
| areas.<id>.hidden | 辞書 | | | 見えないものと理由 |
| flow.signals・end_signals | 並び | | | キーパーにだけ出す知らせ |
| candidates[].problems | 並び | ○ | | 条件を満たさない理由（空なら満たす） |

## Validation Rules

- プレイヤーの見え方には、そのプレイヤーに見えない部品の ID・種類を出さない（記録・指標も同じ）

## Example

`uv run bg show sessions/s1 --as P1 --compact`

## Compatibility

キーの追加は同じ版で行う。
