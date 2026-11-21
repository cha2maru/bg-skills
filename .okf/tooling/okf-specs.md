---
type: Tool
title: okf-specs（jtcsdd）
description: ユーザーが用意した、要望から機能設計書までを OKF で管理するプラグイン。bg-skills 自体の要件定義に使う候補。
tags: [okf, requirements, design-docs]
status: draft
generated: { by: claude-code/claude-opus-5-5, at: 2026-11-18T13:10:00Z }
sources:
  - id: okf-specs-readme
    resource: file:///home/cha2maru/workspace/okf-spec/README.md
    title: okf-specs README / plugin/README.md
---

# Overview

裁定 → 要望 → 要求 → 要件 → 契約 → 開発オブジェクトの流れを OKF で管理し、機能設計書・Spec を書き出す。スキル13個（試験済み: ruling・match・breakdown・structure・detail・change・read・write、試験前: start・view・inquiry・constraint・publish）。[^okf-specs-readme]

# 導入の状態（2026-11-18）

- v0.3.0。ローカルのマーケットプレイスが開発用フォルダを直接指しているため、配布用 `release` ブランチ相当ではなく開発一式がキャッシュに入っている。
- フック `source-guard.sh` は `.okf/guard-roots.txt` がなければ何もしない。
- `okf_doctor.py` の基本項目（Python・PyYAML・git・jq）は OK。

# 使い分け

| 用途 | 使うもの | 置き場所 |
|---|---|---|
| 調査記録・知識 | okf@scaccogatto（[比較](/tooling/okf-plugins.md)） | `.okf/` |
| bg-skills 自体の要望 → 要件 → 設計 | okf-specs | `specs/versions/v2/okf/`（案） |

scaccogatto の `okf:okf` と名前が近く、曖昧な頼み方ではどちらが選ばれるか読みにくい。

# 確認範囲

README・配布案内・フック・ツールの外部呼び出しのみ。SKILL.md と `rules/` は未読。

[^okf-specs-readme]: okf-specs README
