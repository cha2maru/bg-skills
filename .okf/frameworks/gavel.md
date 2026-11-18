---
type: Research System
title: GAVEL
description: Ludii の記述を学習した LLM と進化計算（MAP-Elites）で新しいボードゲームを生成する研究（NeurIPS 2024）。
resource: https://arxiv.org/abs/2407.09388
tags: [game-generation, llm, quality-diversity, evaluation]
status: draft
generated: { by: claude-code/claude-opus-5-5, at: 2026-11-18T13:10:00Z }
sources:
  - id: gavel-paper
    resource: https://arxiv.org/html/2407.09388
    title: "GAVEL: Generating Games Via Evolution and Language Models (Todd et al.)"
---

# Overview

CodeLlama-13b を [Ludii](/frameworks/ludii.md) の記述で fill-in-the-middle 学習（約5万組）させ、ゲームの記述を変異・組み換えさせる。MAP-Elites でゲームの概念（concepts）を軸にした多様なアーカイブを保つ。[^gavel-paper]

# 評価の段階

候補を「コンパイルできる → 遊べる → バランス → 決着がつく」の順にふるい、点数を適応度にする。生成作の一部は Ludii ポータルで遊べる（Havabu、HopThrough、YavaGo）。[^gavel-paper]

# bg-skills から見て

段階的なふるい分けは、バランス調整・自動テストプレイの評価軸の雛形になる。限界として、意味のあるルールが実際に発動するか・不要な部品が残らないかの保証が難しいと著者が述べている。

# 確認範囲

検索結果の要約のみ。論文本文は未読。

[^gavel-paper]: GAVEL 論文
