---
type: Finding
title: bg-skills の設計への示唆
description: 先行事例の調査から導いた、bg-skills の核・ルール記述・情報公開・評価についての方針案（未決定）。
tags: [design, decision-candidate]
status: draft
generated: { by: claude-code/claude-opus-5-5, at: 2026-11-18T13:10:00Z }
sources:
  - id: comparison
    resource: /findings/framework-comparison.md
  - id: sangeki
    resource: /prior-art/sangeki.md
  - id: boardwalk
    resource: /frameworks/boardwalk.md
  - id: rg
    resource: /frameworks/regular-games.md
  - id: gavel
    resource: /frameworks/gavel.md
---

# 方針案（ユーザー未承認）

1. **核は sangeki の Decision / Env を一般化する。** 判断ごとに side・kind・view・options を出し、合法手はエンジンだけが出す。[^sangeki]
2. **ルールは Python で書けるようにする。** LLM が書きやすく（Boardwalk の結果）、ただし LLM はルールの細部で誤るので自動検証を前提にする。[^boardwalk]
3. **状態と情報公開は RG の考え方を借りる。** 運は `random`、情報公開は `keeper` という特別なプレイヤーに担わせ、見える範囲を窓口で作る。[^rg]
4. **評価は GAVEL の段階的なふるい分けを借りる。** コンパイル → 遊べる → バランス → 決着。[^gavel]
5. **既存のコードは流用しない。** Boardwalk・RG はライセンス表記なし、Ludii は改変禁止。[^comparison]

# 未決事項

- 方針案はいずれもユーザーの判断待ち。要件定義は [okf-specs](/tooling/okf-specs.md) で行う想定。

[^comparison]: 枠組みの比較
[^sangeki]: sangeki
[^boardwalk]: Boardwalk
[^rg]: Regular Games
[^gavel]: GAVEL
