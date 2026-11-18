---
type: Game Framework
title: Ludii
description: ludeme（S 式）でゲームを書く汎用ゲームシステム。数千作品を収録し、評価・生成の研究基盤があるが BY-NC-ND。
resource: https://ludii.games/
tags: [ggp, ludeme, java, game-library, evaluation]
status: draft
generated: { by: claude-code/claude-opus-5-5, at: 2026-11-18T13:10:00Z }
sources:
  - id: ludii-site
    resource: https://ludii.games/
    title: Ludii 公式サイト
  - id: ludii-download
    resource: https://ludii.games/download.php
    title: Ludii ダウンロード（ライセンス）
  - id: ludii-tutorials
    resource: https://ludiitutorials.readthedocs.io/en/latest/
    title: Ludii チュートリアル（.lud の書き方・AI API）
  - id: ludii-repo
    resource: https://github.com/Ludeme/Ludii
    title: Ludeme/Ludii
    last_modified: 2026-10-21T23:13:24Z
---

# Overview

Digital Ludeme Project（古代遊戯の復元研究）発。ゲームを `(game … (players …) (equipment …) (rules (start …) (play …) (end …)))` の S 式で書く。例: `(play (move Add (to (sites Empty))))`。[^ludii-tutorials]

# 扱えるもの

盤は四角・六角・三角・トラック・盤なしなど。カード・ダイス・手札・隠れ情報・同時手番・多人数（言語リファレンスの目次による）。[^ludii-site]

# AI の窓口

Java の `util.AI` を継承し `selectAction(game, context, maxSeconds, maxIterations, maxDepth)` を実装。Python は jpy 経由（LudiiPythonAI、公式に「実験的」）。[^ludii-tutorials]

# 評価・生成

Evaluation / Features / Generation のモジュールがあり、ゲーム間距離などの研究がある。LLM による生成は [GAVEL](/frameworks/gavel.md)。[^ludii-repo]

# 弱いところ

- ライセンスは CC BY-NC-ND 4.0（非営利・改変禁止）。改変して組み込めない。[^ludii-download]
- Java 前提。LLM に文法を覚えさせる負担が重い（[Boardwalk](/frameworks/boardwalk.md) の論文の指摘）。
- 最終リリース 1.3.14。日付がダウンロードページ（2025-02-20）と GitHub（2025-06-08）で食い違う。

# 確認範囲

収録作品数と組み込み AI の種類は未確認。言語リファレンスは目次のみ。

[^ludii-site]: Ludii 公式サイト
[^ludii-download]: Ludii ダウンロード
[^ludii-tutorials]: Ludii チュートリアル
[^ludii-repo]: Ludeme/Ludii
