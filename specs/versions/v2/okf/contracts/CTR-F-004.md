---
type: functional-contract
id: CTR-F-004
revision: 1
title: 画面の API
provider: /structure/CMP-0106.md
format: openapi
thickness: thin
elements: [GET /api/def, GET /api/view, GET /api/log, GET /api/candidates, POST /api/op, POST /api/action]
status: stable
tags: []
implementation: []
---

# CTR-F-004：画面の API

## Parties

| 立場 | システム・開発オブジェクト | 責任者 |
|---|---|---|
| 提供 | CMP-0106 画面の API | 記載なし |
| 利用 | OBJ-010501 卓の画面 | 記載なし |

## Approach

`bg serve` が WSL の内側のアドレスで待ち受ける。認証なし。画面は 1.5 秒ごとに view と log を読み直す。

## Compatibility

画面と同じリポジトリで配るので、版は持たない。

## Definition

```yaml
openapi: 3.1.0
info: {title: bg serve, version: "0.1"}
paths:
  /api/def: {get: {parameters: [{name: as, in: query}], responses: {"200": {description: 定義（エリアの木・種類・部品・ルール・用語・卓・アクション・指標・進行）}}}}
  /api/view: {get: {parameters: [{name: as, in: query}], responses: {"200": {description: 局面の見え方（CTR-F-003）}}}}
  /api/log: {get: {parameters: [{name: as, in: query}], responses: {"200": {description: 見え方を守った記録}}}}
  /api/candidates: {get: {parameters: [{name: action, in: query}, {name: by, in: query}, {name: param, in: query}], responses: {"200": {description: 候補（CTR-F-003）}}}}
  /api/op: {post: {responses: {"200": {description: "{ok, seq, warnings}"}, "400": {description: "{ok: false, error}"}}}}
  /api/action: {post: {responses: {"200": {description: "{ok, done, warnings}"}, "400": {description: "{ok: false, error}"}}}}
```
