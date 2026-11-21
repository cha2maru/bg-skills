---
type: Prior Project
title: sangeki（惨劇RoopeR エンジン）
description: 惨劇RoopeR 1作品向けのルールエンジン・自動プレイヤー・自己対戦環境。bg-skills の汎用化の直接の先行事例。
resource: file://<workspace>/sangeki
tags: [prior-art, engine, agent-api, hidden-information]
status: draft
generated: { by: claude-code/claude-opus-5-5, at: 2026-11-18T13:10:00Z }
sources:
  - id: sangeki-claude-md
    resource: file://<workspace>/sangeki/CLAUDE.md
    title: sangeki CLAUDE.md
  - id: sangeki-engine-api
    resource: file://<workspace>/sangeki/plan/engine-api.md
    title: 対戦エンジンの API 化と惨劇セットのデータ化（計画）
---

# Overview

隣のディレクトリにある、ユーザー自身の先行プロジェクト。読み取りのみ許可されている（2026-11-18）。ルールの根拠は `originals/` の一次資料に置き、知識は `wiki/` に OKF v0.2 で記録する。`old/` は失敗した前回の試みで、正しいとみなさない。[^sangeki-claude-md]

# 窓口の設計（Decision / Env）

判断1件を `{seq, side, kind, view, options|schema, context}` で表し、`env.reset()` と `env.step(choice)` で外から1手ずつ進める。片側だけ自動プレイヤーにできる。[^sangeki-engine-api]

- 合法手（options）はエンジンだけが出す。盤面 UI や進行役が独自に判定してずれた不具合の反省から。
- 見えてはいけない情報（役職・犯人・伏せ札）は窓口側で view から外す。
- 記録（record）は判断の列。再生・途中再開は「記録を流し込んでから窓口を開く」。
- 札は1枚ずつ選ばせる（組み合わせは列挙できないため判断を分割する）。
- `env.fork()` による先読みを構想（当面は copy_state）。

# ルールのデータ化（計画段 D 以降）

能力を「いつ × 条件 × 効果 × 回数」の部品で書き、拡張セットごとに JSON（`play/engine/data/sets/BTX.json`、`FS.json`）を持つ。役職は配役に条件で変わる分を重ねて毎回計算する「導かれる値」とする。[^sangeki-engine-api]

# 作り替えの確かめ方

記録のある試合を新しい作りで再生し、公開ログの照合値（crc）が一致することを確かめる。[^sangeki-engine-api]

# 確認範囲

CLAUDE.md、plan/engine-api.md、ファイル一覧のみ。`play/engine/` のコードは未読。段 A〜C は実装済み、段 D 以降は計画書上未完了（計画書の「進み具合」による）。

[^sangeki-claude-md]: sangeki CLAUDE.md
[^sangeki-engine-api]: 対戦エンジンの API 化と惨劇セットのデータ化（計画）
