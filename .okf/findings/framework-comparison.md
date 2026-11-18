---
type: Comparison
title: 汎用ゲーム記述の枠組みの比較
description: Boardwalk・Regular Games・Ludii・sangeki を、ルールの書き方・隠れ情報・合法手・LLM 適性・速さ・ライセンスで比べた表。
tags: [comparison, ggp]
status: draft
generated: { by: claude-code/claude-opus-5-5, at: 2026-11-18T13:10:00Z }
sources:
  - id: boardwalk
    resource: /frameworks/boardwalk.md
  - id: rg
    resource: /frameworks/regular-games.md
  - id: ludii
    resource: /frameworks/ludii.md
  - id: sangeki
    resource: /prior-art/sangeki.md
---

# 比較

| | [Boardwalk](/frameworks/boardwalk.md) | [RG](/frameworks/regular-games.md) | [Ludii](/frameworks/ludii.md) | [sangeki](/prior-art/sangeki.md) |
|---|---|---|---|---|
| ルールの書き方 | Python のクラス | オートマトン / HRG | ludeme（S 式） | Python と JSON |
| 隠れた情報・運 | なし | あり（理論上すべて） | あり | あり（view） |
| 合法手の列挙 | 任意（既定は空） | あり | あり | あり（options） |
| LLM が書きやすいか | 高い | 低い | 低い（GAVEL は学習が必要） | 中程度 |
| 速さ | 遅い（deepcopy） | 非常に速い | 中程度 | 中程度 |
| ライセンス | 表記なし | 表記なし | CC BY-NC-ND | 自作 |

評価（「書きやすさ」「速さ」）は調査時の Claude の判断で、計測していない。各行の根拠は各概念の本文と出典による。[^boardwalk][^rg][^ludii][^sangeki]

[^boardwalk]: Boardwalk
[^rg]: Regular Games
[^ludii]: Ludii
[^sangeki]: sangeki
