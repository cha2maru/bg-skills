"""第二版：自作のゲームを、回しながら改訂するための道具（RUL-028・CTR-F-007）。

作業場（bg init）、元と案の比べ（bg compare）、試行の記録（--record・bg experiments）、設計の状態（bg status）、
人が読む手引き（bg rulebook）。案（定義の断片）の重ね方は definition.overlay。
"""
from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

from .definition import Definition, load

# --- 作業場の雛形 ---------------------------------------------------------------------------------

TEMPLATE = """\
# ゲームの定義（bg-skills。形式は CTR-F-001。bg schema で項目の一覧）。
# この雛形は「動く最小のゲーム」：2 人、数のカードを引いて出し、山札が尽きたら出したカードの合計が大きい人の勝ち。
# 自分のゲームに書き換えていく。決まっていない点は open_questions と、rulings の status: open に残す。
format: bg-def/0.1
game:
  id: {gid}
  name: {name}
  version: 1
  summary: まだ決まっていない。アイデアの一文をここに書く。
  players: {{min: {pmin}, max: {pmax}}}
  open_questions:
    - 手札の上限はあるか（今は無し）

players:
  - {{id: "P{{n}}", for_each: {{n: [{plist}]}}}}

kinds:
  card:
    base: object
    name: 数のカード
    text: 1〜5 の数が書かれたカード（attributes の value）。
    attributes:
      value: {{type: number}}

areas:
  - {{id: deck, name: 山札, ordered: true, visibility: {{face: none, order: none}}}}
  - {{id: "hand-{{player}}", for_each: {{player: players}}, owner: "{{player}}", name: 手札, visibility: {{face: owner}}}}
  - {{id: "played-{{player}}", for_each: {{player: players}}, owner: "{{player}}", name: 出したカード}}

table:
  center: [deck]
  per_player: ["hand-{{player}}", "played-{{player}}"]

objects:
  - {{id: "c{{value}}-{{copy}}", kind: card, for_each: {{value: [1, 2, 3, 4, 5]}}, copies: 4, start: deck, attributes: {{value: "{{value}}", title: "{{value}}"}}}}

actions:
  - id: setup
    name: 準備（切って配る）
    rule: R1
    by: [keeper]
    steps:
      - {{op: shuffle, area: deck}}
      - {{op: move, obj: "top:deck", to: "hand-{{player}}", each: players, times: 3}}
  - id: draw
    name: 1 枚引く
    rule: R2
    require: [{{expr: "count_in('deck') > 0", text: 山札がない}}]
    steps: [{{op: move, obj: "top:deck", to: "hand-{{actor}}"}}]
  - id: play
    name: 手札を 1 枚出す
    rule: R2
    params: [{{name: card, from: "hand-{{actor}}"}}]
    steps: [{{op: move, obj: "{{card}}", to: "played-{{actor}}"}}]

functions:
  score: {{params: [p], expr: "sum(int(attr(c, 'value')) for c in on('played-' + p))"}}

flow:
  auto_end: true
  scoring: {{by: points}}
  stages:
    - {{id: setup, name: 準備, actions: [setup]}}
    - {{id: main, name: 本番, order: seats, turn: main}}
  turns:
    main:
      phases:
        - {{id: draw, name: 引く, main: [draw], max: 1}}
        - {{id: play, name: 出す, main: [play], max: 1}}
  end_when:
    - {{expr: "stage() == 'main' and count_in('deck') == 0", timing: round_end, winners: scoring, rule: R3, text: 山札が尽きた（その巡を終えて、合計で比べる）}}

metrics:
  - {{id: points, name: 合計, badge: true, per: player, expr: "score(player)", refs: [R3]}}

rules:
  - {{id: R1, type: setup, text: 20 枚のカードを切って山札にし、各自 3 枚引く。}}
  - {{id: R2, type: turn, text: 手番に、山札から 1 枚引き、手札を 1 枚出す。}}
  - {{id: R3, type: end, text: 山札が尽きたら、その巡を終えて終わる。出したカードの数の合計が大きい人の勝ち。}}

rulings:
  - {{id: J1, status: open, question: 合計が同じときはどうするか, rules: [R3], date: "{today}"}}
"""

VARIANT = """\
# 案：定義の断片（CTR-F-007）。bg compare game.yaml --variant hand-5=variants/hand-5.yaml のように重ねて比べる。
# 並びの要素は id が同じなら差し替え、無ければ足す。消すときは remove: [id]。
game: {version: 1}
actions:
  - id: setup
    name: 準備（切って 5 枚配る）
    rule: R1
    by: [keeper]
    steps:
      - {op: shuffle, area: deck}
      - {op: move, obj: "top:deck", to: "hand-{player}", each: players, times: 5}
rules:
  - {id: R1, type: setup, text: 20 枚のカードを切って山札にし、各自 5 枚引く。}
"""

JOURNAL = """\
# 設計の日誌：{name}

版ごとに、変えたこと・理由・根拠の試行（experiments.jsonl の日時）を書く（bg-iterate）。

## 版 1（{today}）

- 雛形から始めた（bg init）。
"""


def init(folder, name: str | None = None, players: str = "2-4") -> dict:
    """作業場を作る（CTR-F-007）。フォルダが空でなければ作らない。"""
    root = Path(folder)
    if root.exists() and any(root.iterdir()):
        raise ValueError(f"{root} は空ではない（作業場は空のフォルダに作る）")
    pmin, pmax = (int(x) for x in players.split("-")) if "-" in players else (int(players), int(players))
    gid = "".join(ch if ch.isalnum() else "-" for ch in (root.name or "game")).strip("-").lower() or "game"
    today = datetime.now(timezone.utc).date().isoformat()
    name = name or root.name or "新しいゲーム"
    files = {
        "game.yaml": TEMPLATE.format(gid=gid, name=name, pmin=pmin, pmax=pmax, plist=", ".join(map(str, range(1, pmax + 1))), today=today),
        "variants/hand-5.yaml": VARIANT,
        "experiments.jsonl": "",
        "journal.md": JOURNAL.format(name=name, today=today),
        ".gitignore": "sessions/\n",
    }
    for rel, text in files.items():
        f = root / rel
        f.parent.mkdir(parents=True, exist_ok=True)
        f.write_text(text, encoding="utf-8")
    (root / "sessions").mkdir(exist_ok=True)
    return {"created": sorted(files), "next": [f"bg check {root / 'game.yaml'}", f"bg selfplay {root / 'game.yaml'} --players {pmin} --games 10",
                                                f"bg compare {root / 'game.yaml'} --variant hand-5={root / 'variants/hand-5.yaml'} --players {pmin}"]}


# --- 比べる・記録する -------------------------------------------------------------------------------

UNDECIDED = ("打ち切り", "決着なし", "進められない")


def fingerprint(path, variants=None) -> str:
    """定義と重ねた案の中身の指紋（同じ中身なら同じ）。"""
    h = hashlib.sha256(Path(path).read_bytes())
    for v in variants or []:
        h.update(b"\0" + Path(v).read_bytes())
    return h.hexdigest()[:12]


def _summary(r: dict) -> dict:
    games = r.get("games") or 0
    out = dict(r)
    if games:
        out["undecided_rate"] = round(sum(n for k, n in (r.get("outcomes") or {}).items() if k in UNDECIDED) / games, 2)
        out["outcome_rates"] = {k: round(n / games, 2) for k, n in (r.get("outcomes") or {}).items()}
    return out


def compare(path, variants: dict, players: int, games: int = 20, max_turns: int = 60, seed: int = 0, common=None) -> dict:
    """元（base）と案を、同じ種・同じ局数で selfplay して並べる。variants は {名前: 案のファイル}。common は全部に重ねる案。"""
    from .sim import selfplay
    common = list(common or [])
    rows = {"base": _summary(selfplay(path, players, games, max_turns, seed, common))}
    for name, f in variants.items():
        rows[name] = _summary(selfplay(path, players, games, max_turns, seed, common + [f]))
    return {"players": players, "games": games, "seed": seed, "rows": rows}


def record(log, path, variants, tool: str, players: int, games: int, seed: int, max_turns: int, result: dict, note: str | None = None) -> dict:
    """試行の記録に 1 行足す（CTR-F-007。追記だけ）。"""
    d = load(path, players, None, variants)
    row = {"time": datetime.now(timezone.utc).isoformat(timespec="seconds"), "game": d.data["game"]["id"],
           "version": d.data["game"].get("version"), "def_hash": fingerprint(path, variants),
           "variants": [Path(v).stem for v in variants or []], "players": players, "games": games, "seed": seed,
           "max_turns": max_turns, "tool": tool, "result": result, **({"note": note} if note else {})}
    with Path(log).open("a", encoding="utf-8") as f:
        f.write(json.dumps(row, ensure_ascii=False) + "\n")
    return row


def experiments(log, last: int | None = None) -> list[dict]:
    """試行の記録を新しい順に（日時・版・案・局数・主な結果）。"""
    p = Path(log)
    rows = [json.loads(x) for x in p.read_text(encoding="utf-8").splitlines() if x.strip()] if p.exists() else []
    rows.reverse()
    out = []
    for r in rows[:last] if last else rows:
        res = r.get("result") or {}
        top = sorted((res.get("outcomes") or {}).items(), key=lambda kv: -kv[1])[:2]
        out.append({"time": r.get("time"), "version": r.get("version"), "variants": r.get("variants") or ["(元)"],
                    "games": r.get("games"), "players": r.get("players"), "avg_turns": res.get("avg_turns"),
                    **({"win_rate": res["win_rate"]} if res.get("win_rate") else {}),
                    "undecided_rate": res.get("undecided_rate"), "top_outcomes": dict(top), **({"note": r["note"]} if r.get("note") else {})})
    return out


# --- 設計の状態 ------------------------------------------------------------------------------------

def status(d: Definition, log=None) -> dict:
    """設計の状態の一覧（SPC-075）：版・ルール・決まっていないこと・機械の層・最近の試行。"""
    from .measure import complexity
    from .tools import check_refs
    g = d.data["game"]
    rules = d.data.get("rules") or []
    c = complexity(d)
    out = {
        "game": g.get("name") or g["id"], "version": g.get("version"),
        "rules": {"manual": sum(1 for r in rules if not r.get("detail")), "detail": sum(1 for r in rules if r.get("detail"))},
        "check_errors": len(check_refs(d)),
        "undecided": {
            "open_rulings": [{"id": r.get("id"), "question": r.get("question")} for r in d.data.get("rulings") or [] if r.get("status") == "open"],
            "open_questions": list(g.get("open_questions") or []),
            "rules_text_only": c["rules_text_only"]["ids"],
        },
        "size": {k: c[k] for k in ("rules", "actions", "conditions", "expression_nodes") if k in c},
    }
    if log:
        out["recent_experiments"] = experiments(log, 3)
    return out


# --- 手引き（ルールブック） -----------------------------------------------------------------------------

ORDER = ["setup", "turn", "action", "always", "end"]
TYPE_NAME = {"setup": "準備", "turn": "手番の流れ", "action": "行えること", "always": "いつでも", "end": "終わりと勝ち負け"}


def rulebook(d: Definition) -> str:
    """人が読む手引き（Markdown。SPC-076）。詳細ルール（detail: true）と未決の裁定は出さない。"""
    g = d.data["game"]
    pl = g.get("players") or {}
    out = [f"# {g.get('name') or g['id']}", ""]
    if g.get("summary"):
        out += [str(g["summary"]).strip(), ""]
    out += [f"- 人数：{pl.get('min')}〜{pl.get('max')} 人" if pl.get("min") != pl.get("max") else f"- 人数：{pl.get('min')} 人",
            f"- 版：{g.get('version')}", ""]
    # 部品：種類ごとの名前と数（区別しない部品は個数、unlimited は「必要なだけ」）
    counts: dict[str, int | str] = {}
    for pid, part in d.parts.items():
        k = part.get("kind") or pid
        n = part.get("count", 1)
        if n == "unlimited":
            counts[k] = "必要なだけ"
        elif counts.get(k) != "必要なだけ":
            counts[k] = int(counts.get(k, 0)) + int(n)
    if counts:
        out += ["## 部品", ""]
        for k, n in counts.items():
            kd = d.kinds.get(k) or {}
            name = kd.get("name") or k
            text = f"：{kd['text']}" if kd.get("text") else ""
            out.append(f"- {name} × {n}{text}")
        out.append("")
    manual = [r for r in d.data.get("rules") or [] if not r.get("detail")]
    if manual:
        out += ["## ルール", ""]
        for t in ORDER + sorted({r.get("type") for r in manual} - set(ORDER) - {None}):
            rs = [r for r in manual if r.get("type") == t]
            if rs:
                out += [f"### {TYPE_NAME.get(t, t)}", ""] + [f"- {str(r['text']).strip()}" for r in rs] + [""]
        rest = [r for r in manual if not r.get("type")]
        out += [f"- {str(r['text']).strip()}" for r in rest] + ([""] if rest else [])
    if d.terms:
        out += ["## 用語", ""] + [f"- **{t.get('word') or k}**：{t.get('text', '')}" for k, t in d.terms.items()] + [""]
    faq = [r for r in d.data.get("rulings") or [] if r.get("status") != "open" and r.get("decision")]
    if faq:
        out += ["## よくある質問", ""] + [f"- **{r.get('question')}** → {r.get('decision')}" for r in faq] + [""]
    return "\n".join(out).rstrip() + "\n"
