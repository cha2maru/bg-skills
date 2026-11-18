# 汎用ゲーム記述の枠組み

* [Boardwalk](boardwalk.md) - ゲームのルールを Python のクラスで書かせる LLM 向けの汎用ゲーム API。完全情報・長方形盤のみ。
* [Regular Games（RG）](regular-games.md) - 有限オートマトンでルールを書く GGP 言語。不完全情報・運を含む有限ターン制ゲームを網羅し、Ludii より大幅に速い。
* [Ludii](ludii.md) - ludeme（S 式）でゲームを書く汎用ゲームシステム。数千作品を収録し、評価・生成の研究基盤があるが BY-NC-ND。
* [GAVEL](gavel.md) - Ludii の記述を学習した LLM と進化計算（MAP-Elites）で新しいボードゲームを生成する研究（NeurIPS 2024）。
