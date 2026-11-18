---
type: Tool Survey
title: OKF 用 Claude Code プラグインの比較
description: OKF で調査記録を管理する Claude Code プラグインの候補と、採用した scaccogatto/okf-skills の中身。
tags: [okf, plugins, knowledge-management]
status: draft
generated: { by: claude-code/claude-opus-5-5, at: 2026-11-18T13:10:00Z }
sources:
  - id: scaccogatto
    resource: https://github.com/scaccogatto/okf-skills
    title: scaccogatto/okf-skills
    last_modified: 2026-11-04T00:00:00Z
  - id: jamditis
    resource: https://github.com/jamditis/claude-skills-journalism
    title: jamditis/claude-skills-journalism (okf-wiki)
  - id: okf-official
    resource: https://github.com/GoogleCloudPlatform/knowledge-catalog
    title: GoogleCloudPlatform/knowledge-catalog
---

# 候補（★は 2026-11-18 の GitHub API の値）

| リポジトリ | ★ | ライセンス | 中身 |
|---|---|---|---|
| scaccogatto/okf-skills | 453 | MIT | 作成・保守・検証・可視化・backfill 一式[^scaccogatto] |
| jamditis の okf-wiki | 457（リポジトリ全体） | MIT | 雛形と検証。研究アトラスの雛形。`okf_spec: v1` 表記[^jamditis] |
| aws-samples/sample-okf-llm-wiki | 36 | MIT-0 | データ資産を OKF にして MCP で配る |
| pumblus/okf-harness | 38 | Apache-2.0 | LLM Wiki 用のローカルの仕組み |
| briareus-io/okf / eltmon/okf ほか | 0〜9 | MIT など | 実績が少ない |

公式（Google / Anthropic）の Claude Code プラグインはない。[^okf-official]

# 採用: okf@scaccogatto v0.12.0（2026-11-18、プロジェクト単位で導入）

- スキル: `okf`（produce / maintain / consume）、`validate`（§11 の機械検証）、`visualize`（グラフ HTML。CDN を SRI 付きで読む）、`backfill`（git 履歴とセッション記録から再構成）。
- Stop フックは `.okf/index.md` に `upkeep: enforced` を書いたときだけ働く（このバンドルでは書いていない）。`OKF_HOOK=off` で無効。
- MCP は `./.okf` の読み取り専用。外部プログラムは backfill の git 読み取りのみ。backfill は既定でセッション記録も読む（`--no-sessions` で外す）。

使い分けは [okf-specs](/tooling/okf-specs.md) を参照。

[^scaccogatto]: scaccogatto/okf-skills
[^jamditis]: jamditis/claude-skills-journalism
[^okf-official]: GoogleCloudPlatform/knowledge-catalog
