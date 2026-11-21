# bg-skills

ボードゲームを構成する情報（部品・置き場・状態・ルール・手番の進行・隠れた情報）を YAML の定義に書き、その定義を `bg` コマンドで操作できる汎用の環境。エージェントが、新しいゲームの設計とテストプレイ、既存のゲームの試し遊び、多数局のシミュレーションによるバランス調整を行えるようにする。Claude Code のプラグインとして入れると、スキルと `bg` コマンドがどのプロジェクトでも使える。

## 入れる

このリポジトリがマーケットプレイスになっている。Claude Code で次を実行する（ローカルの clone なら、URL の代わりにフォルダのパス）。

```
/plugin marketplace add <このリポジトリの git の URL か、clone したフォルダ>
/plugin install bg-skills@bg-skills
```

- 1 回だけ試すなら `claude --plugin-dir <clone したフォルダ>`。
- 要るもの：[uv](https://docs.astral.sh/uv/)（Python 3.11 以上は uv が用意する）。最初の `bg` の実行で、プラグインのフォルダに依存（PyYAML）が入る。
- 画面のテストを動かすときだけ playwright（`uv run --with playwright ...`）。

## 自分のゲームを作る（導入から改訂まで）

ルールが固まっていないうちから定義にし、回しながら改訂していく流れ（第二版）。Claude に「ボードゲームを作り始めたい」と言えば bg-start が案内する。

1. **作業場を作る**：`bg init games/mygame --name 私のゲーム --players 2-4`。動く最小の雛形 `game.yaml`、案の置き場 `variants/`、試行の記録 `experiments.jsonl`、設計の日誌 `journal.md` ができる。
2. **アイデアを定義にする**（bg-design）。決まっていないことは `game.open_questions` と、未決の裁定（`rulings` の `status: open`）に残してよい。
3. **状態を見る**：`bg status games/mygame/game.yaml --experiments games/mygame/experiments.jsonl`（決まっていないこと・機械の層の無いルール・最近の試行）。
4. **案を試して比べる**（bg-iterate）：変えるところだけを `variants/<案>.yaml` に書き、
   `bg compare games/mygame/game.yaml --variant 案=games/mygame/variants/案.yaml --players 3 --games 30 --record games/mygame/experiments.jsonl --note "何を確かめるか"`。
   席ごとの勝ちの割合・長さ・決着しない割合が並ぶ。
5. **取り込む**：良ければ案を `game.yaml` に移して `game.version` を上げ、`journal.md` に理由と根拠の試行を書く。
6. **人と遊ぶ**：`bg rulebook games/mygame/game.yaml > RULES.md`（手引き）と `bg serve`（卓の画面）。エージェントに遊ばせるなら bg-playtest。

## 使う

| スキル | 使うとき |
|---|---|
| `bg-start` | プラグインを入れた後、作業場を作って最初の 1 局を回すまで |
| `bg-design` | ゲームのアイデアを定義（YAML）に起こし、`bg check`・`bg fuzz` を通す |
| `bg-iterate` | 案を作って元と比べ、試行を記録し、取り込んで版を上げる（改訂の 1 周） |
| `bg-playtest` | エージェントに席ごとの見え方だけで遊ばせ、詰まり・不具合・ルールの穴を報告させる |
| `bg-balance` | 多数局で勝率・局の長さを測り、数値を 1 つずつ変えて比べる |
| `bg-rules-audit` | ルールの文と定義の食い違い・穴を洗い出す |
| `bg-hidden-info-audit` | 隠れた情報が出力から漏れないかをチェック表で確かめる |

`bg` コマンドの例：

```bash
bg check examples/kagaribi.yaml                       # 参照・式・形式の確認
bg new sessions/s1 --def examples/kagaribi.yaml --players 2 --seed 1
bg show sessions/s1 --as P1 --compact                 # P1 の見え方
bg act sessions/s1 setup --by keeper                  # 定義のアクション
bg serve sessions/s1 --host 127.0.0.1                 # 卓の画面（認証なし。外に公開しない）
bg selfplay examples/rune-clash.yaml --players 2 --games 30
```

コマンドの全体は [CLAUDE.md](CLAUDE.md) の「コマンド」の節、定義の形式は `specs/versions/v2/okf/contracts/CTR-F-001.md` と `bg schema`、手本の定義は `examples/`（三目並べ・オセロ・チェス・将棋・麻雀・人狼・架空のカードゲームなど）。

## 開発

```bash
uv sync
uv run pytest -q
uv run --with playwright pytest -q tests/test_ui.py
claude plugin validate .
```

リポジトリの中では、スキルは `.claude/skills`（`skills/` へのリンク）から読まれる。
