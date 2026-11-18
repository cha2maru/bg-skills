---
type: Game Framework
title: Regular Games（RG）
description: 有限オートマトンでルールを書く GGP 言語。不完全情報・運を含む有限ターン制ゲームを網羅し、Ludii より大幅に速い。
resource: https://github.com/radekmie/rg
tags: [ggp, automaton, imperfect-information, stochastic, performance]
status: draft
generated: { by: claude-code/claude-opus-5-5, at: 2026-11-18T13:10:00Z }
sources:
  - id: rg-paper
    resource: https://arxiv.org/abs/2511.10593
    title: "Regular Games – an Automata-Based General Game Playing Language (AAAI 2026 full version, Miernik et al.)"
  - id: rg-repo
    resource: https://github.com/radekmie/rg
    title: radekmie/rg
    last_modified: 2026-11-07T00:57:06Z
---

# Overview

Regular Boardgames（RBG）の後継。3層構成: 低水準 RG（ルール＝ラベル付き有向グラフの NFA）、人が書く高水準 HRG、分野ごとのフレームワーク（例: Python で HRG を生成する LineGames、23作品）。盤・算術・手の形といった組み込み概念を持たず、状態は有限集合型と写像型の変数、手はタグの列。[^rg-paper]

# 隠れ情報・運・同時手番

- 特別なプレイヤー `random`（一様選択。辺の複製で任意の有理確率）と `keeper`（実プレイヤーでない状態変更・情報公開）。
- `visible[p]` を切り替え、見えない部分を伏せた手（obfuscated move）を相手に伝える。同時手番は不完全情報で表す。
- 不完全情報と運を含む有限ターン制ゲームに対して普遍（GDL-II・Ludii と同じ範囲）。[^rg-paper]

# 速さとツール

- flat MC の playout/秒: Connect Four 約130万（Ludii 5.6万）、チェス 1,572（Ludii 113）。C++ にコンパイルし `getAllMoves` / `apply` / `isTerminal` を直接呼べる。[^rg-paper]
- Rust インタプリタ、LSP 対応エディタ、オートマトン可視化、変換デバッガ、ベンチマーク。[^rg-repo]

# 弱いところ

組み込み AI なし（開発中）、Python のエージェント窓口なし、LLM への言及なし。ライセンス表記なし（GitHub API で license=null）。

# bg-skills から見て

最小の核＋分野ごとの高水準層、という分け方と、`random`/`keeper` による運・情報公開の一般的な扱いが参考になる（sangeki の view と同じ問題）。

# 確認範囲

論文は arXiv HTML 版の前半を逐語、後半は要約で読んだ（サブエージェント経由）。AAAI 版は取得不可。表の数値は抜粋。

[^rg-paper]: Regular Games 論文
[^rg-repo]: radekmie/rg
