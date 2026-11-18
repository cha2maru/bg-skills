---
type: Game Framework
title: Boardwalk
description: ゲームのルールを Python のクラスで書かせる LLM 向けの汎用ゲーム API。完全情報・長方形盤のみ。
resource: https://github.com/LabCRAIG/boardwalk
tags: [ggp, python, llm-codegen, perfect-information]
status: draft
generated: { by: claude-code/claude-opus-5-5, at: 2026-11-18T13:10:00Z }
sources:
  - id: boardwalk-paper
    resource: https://arxiv.org/abs/2508.16447
    title: "Boardwalk: Towards a Framework for Creating Board Games with LLMs (SBGames 2025, Becker et al., UFRGS)"
  - id: boardwalk-code
    resource: https://github.com/LabCRAIG/boardwalk/blob/main/boardwalk.py
    title: boardwalk.py（182行）
    last_modified: 2026-01-16T12:47:08Z
---

# Overview

独自の記述言語（GDL）を覚えさせる負担を避け、ゲームを Python で定義させる。対象は完全情報・長方形のマス目の盤・人数は任意。六角／グラフ盤とカードゲームは今後の課題。[^boardwalk-paper]

# API

- `Board`: numpy の2次元配列に1文字の駒。手は文字列（置く `"X 1,2"`、動かす `"0,0 1,1"`）を正規表現で解釈。[^boardwalk-code]
- `Game` を継承して書く。必須: `validate_move`、`game_finished`、`get_winner`（引き分けは `None`）、`next_player`。任意: `perform_move`、`initial_player`、`turn_counter`、`possible_moves(state)`（既定は空）。[^boardwalk-code]
- AI: `Game(board, ai_players={player: agent})`、`agent.get_action(game, state)`、先読み用の `next_state(state, move)`（全体を deepcopy）。論文後に main に追加。[^boardwalk-code]

# 実験結果

12作品（Ludii のルールを流用）を DeepSeek V3 / Claude 3.7 Sonnet / GPT-4o に例なしで実装させた。誤りなしは Claude 20/36（55.6%）で最多、全体 38.9%、遊べないもの 24.1%。誤りはルールの細部（配置段階の欠落、チェッカーの強制取り、連続取り、`next_player` 未定義）に集中。評価は人手。[^boardwalk-paper]

# bg-skills から見て

- 取り入れたい: 「ルールはコード、エンジンは共通」「上書き点を少数に」。LLM がルールの細部で誤るという結果は、自動検証が要る根拠。
- 足りない: 合法手の列挙が任意（選択肢をエージェントに出せない）、隠れ情報・運・カード非対応、deepcopy で遅い。
- ライセンス表記なし。コードは流用せず設計の参考にとどめる。

# 確認範囲

`boardwalk.py` は全文を読んだ。論文は HTML 版をサブエージェントが読んだ要約で、数値は原文の表と照合していない。prompts リポジトリは未読。

[^boardwalk-paper]: Boardwalk 論文
[^boardwalk-code]: boardwalk.py
