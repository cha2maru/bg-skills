"""ゲーム定義の形式の正本（CTR-F-001 v2）：置き場所ごとに使ってよい項目。

bg check はこれに無い項目（打ち間違い・古い書き方）を、似た項目の候補つきで知らせる。bg schema は同じ表から
JSON Schema を書き出す（エディタの補完・エージェントの読み物）。項目を足すときは、ここと CTR-F-001 を一緒に直す。
"""
from __future__ import annotations

import difflib

# 置き場所 → 項目（値の説明は CTR-F-001。ここは名前の正本）
FIELDS: dict[str, set[str]] = {
    "top": {"format", "game", "players", "teams", "kinds", "areas", "objects", "links", "groups", "actions", "rules", "rulings", "terms",
            "metrics", "flow", "functions", "progress", "table", "assets", "layout"},
    "game": {"id", "name", "summary", "version", "players", "open_questions", "sources", "strict"},
    "player": {"id", "name", "text", "color", "team", "for_each", "copies"},
    "team": {"name", "text"},
    "kind": {"base", "name", "text", "states", "show_state", "derived", "attributes", "capacity", "ordered", "fixture", "distinct",
             "uses", "image", "back_image", "shape", "source"},
    "area": {"id", "name", "text", "kind", "owner", "visibility", "capacity", "ordered", "areas", "for_each", "layout", "pos", "rect",
             "poly", "color", "aspect", "folded", "image", "on_enter"},
    "object": {"id", "name", "kind", "owner", "start", "start_state", "attributes", "count", "copies", "for_each", "image", "back_image"},
    "link": {"between", "type", "text"},
    "action": {"id", "name", "rule", "when", "by", "params", "require", "let", "steps", "cost", "secret", "stepwise", "stack",
               "during_stack", "text"},
    "param": {"name", "text", "from", "in", "kind", "owner", "players", "choices", "free", "stack", "pick", "require"},
    "require": {"expr", "text", "has", "empty", "linked", "any", "not"},
    "step": {"op", "let", "each", "as", "do", "if", "else", "times", "call", "args",
             # 操作ごとの項目（op の種類で使うものが違う）
             "obj", "from", "to", "at", "n", "area", "kind", "owner", "into", "into_kind", "parts", "facing", "field", "value", "expr",
             "key", "player", "fields", "text", "target", "winner", "winners", "results", "draw", "until", "order", "skip", "decision",
             "question", "rule", "offer", "reply_to", "draw"},
    "flow": {"stages", "turns", "cycle", "end_when", "signals", "auto_end", "scoring", "offer_action", "stack"},
    "stage": {"id", "name", "order", "turn", "turns", "actions", "on_start", "on_end", "talk", "talk_text", "whisper", "from_box_only"},
    "turn": {"phases", "free", "reactions", "on_start", "on_end"},
    "phase": {"id", "name", "main", "max", "each", "per_player", "sequence", "required", "auto", "pass", "by", "talk", "talk_text", "whisper"},
    "turn_entry": {"action", "max", "phases"},
    "end": {"expr", "text", "rule", "public", "winners", "losers", "draw", "timing"},
    "scoring": {"by", "tiebreak", "low"},
    "metric": {"id", "name", "per", "count", "sum", "expr", "needs", "visible", "badge", "refs"},
    "rule": {"id", "type", "text", "refs", "source", "seat"},
    "term": {"word", "text", "refs"},
    # 裁定（ルールの穴を埋める。RUL-017。sangeki の wiki/notes/rulings.md を参考）
    "ruling": {"id", "question", "decision", "reason", "rules", "refs", "principle", "status", "authority", "by", "date",
               "sources", "found_in", "supersedes", "engine"},
    "function": {"params", "expr"},
    "progress": {"text", "start", "refs"},
}


def unknown_keys(data: dict) -> list[dict]:
    """定義の中の、置き場所に無い項目（{where, ref}。ref に似た項目の候補）。"""
    out = []

    def check(x, ctx, where):
        if not isinstance(x, dict):
            return
        for k in x:
            if k not in FIELDS[ctx]:
                near = difflib.get_close_matches(k, FIELDS[ctx], n=1)
                out.append({"where": f"{where}.{k}" if where else k,
                            "ref": f"知らない項目 {k}" + (f"（{near[0]} のことか）" if near else f"（{ctx} に書ける項目ではない）")})

    def steps(xs, where):
        for i, st in enumerate(xs or []):
            check(st, "step", f"{where}[{i}]")
            if isinstance(st, dict):
                for key in ("do", "else"):
                    steps(st.get(key), f"{where}[{i}].{key}")

    check(data, "top", "")
    check(data.get("game"), "game", "game")
    for i, p in enumerate(data.get("players") or []):
        check(p, "player", f"players[{i}]")
    for k, v in (data.get("teams") or {}).items():
        check(v, "team", f"teams.{k}")
    for k, v in (data.get("kinds") or {}).items():
        check(v, "kind", f"kinds.{k}")

    def areas(xs, where):
        for i, a in enumerate(xs or []):
            check(a, "area", f"{where}[{i}]")
            if isinstance(a, dict):
                areas(a.get("areas"), f"{where}[{i}].areas")
    areas(data.get("areas"), "areas")
    for i, o in enumerate(data.get("objects") or []):
        check(o, "object", f"objects[{i}]")
    for i, x in enumerate(data.get("links") or []):
        check(x, "link", f"links[{i}]")
    for i, a in enumerate(data.get("actions") or []):
        w = f"actions[{i}]"
        check(a, "action", w)
        for j, p in enumerate(a.get("params") or []):
            check(p, "param", f"{w}.params[{j}]")
            for k, r in enumerate(p.get("require") or []):
                check(r, "require", f"{w}.params[{j}].require[{k}]")
        for k, r in enumerate(a.get("require") or []):
            check(r, "require", f"{w}.require[{k}]")
        steps(a.get("steps"), f"{w}.steps")
        steps(a.get("cost"), f"{w}.cost")
    fl = data.get("flow") or {}
    check(fl, "flow", "flow")
    check(fl.get("scoring"), "scoring", "flow.scoring")
    for i, st in enumerate(fl.get("stages") or []):
        check(st, "stage", f"flow.stages[{i}]")
        steps(st.get("on_start"), f"flow.stages[{i}].on_start")
        steps(st.get("on_end"), f"flow.stages[{i}].on_end")
    for tid, t in (fl.get("turns") or {}).items():
        check(t, "turn", f"flow.turns.{tid}")
        for i, ph in enumerate(t.get("phases") or []):
            check(ph, "phase", f"flow.turns.{tid}.phases[{i}]")
        for key in ("free", "reactions"):
            for i, e in enumerate(t.get(key) or []):
                check(e, "turn_entry", f"flow.turns.{tid}.{key}[{i}]")
        steps(t.get("on_start"), f"flow.turns.{tid}.on_start")
        steps(t.get("on_end"), f"flow.turns.{tid}.on_end")
    for key in ("end_when", "signals"):
        for i, e in enumerate(fl.get(key) or []):
            check(e, "end", f"flow.{key}[{i}]")
    for i, m in enumerate(data.get("metrics") or []):
        check(m, "metric", f"metrics[{i}]")
    for i, r in enumerate(data.get("rules") or []):
        check(r, "rule", f"rules[{i}]")
    for k, v in (data.get("terms") or {}).items():
        check(v, "term", f"terms.{k}")
    for i, r in enumerate(data.get("rulings") or []):
        check(r, "ruling", f"rulings[{i}]")
    for k, v in (data.get("functions") or {}).items():
        check(v, "function", f"functions.{k}")
    for k, v in (data.get("progress") or {}).items():
        check(v, "progress", f"progress.{k}")
    return out


def json_schema() -> dict:
    """FIELDS から JSON Schema（draft 2020-12）を作る。項目の名前と入れ子だけ（値の型は CTR-F-001 の文）。"""
    def obj(ctx, extra=None):
        props = {k: {} for k in sorted(FIELDS[ctx])}
        props.update(extra or {})
        return {"type": "object", "properties": props, "additionalProperties": False}
    step = {"$ref": "#/$defs/step"}
    steps = {"type": "array", "items": step}
    req = {"type": "array", "items": obj("require")}
    defs = {
        "step": obj("step", {"do": steps, "else": steps}),
        "area": obj("area", {"areas": {"type": "array", "items": {"$ref": "#/$defs/area"}}}),
    }
    turn = obj("turn", {"phases": {"type": "array", "items": obj("phase")}, "free": {"type": "array", "items": obj("turn_entry")},
                        "reactions": {"type": "array", "items": obj("turn_entry")}, "on_start": steps, "on_end": steps})
    flow = obj("flow", {"stages": {"type": "array", "items": obj("stage", {"on_start": steps, "on_end": steps})},
                        "turns": {"type": "object", "additionalProperties": turn}, "scoring": obj("scoring"),
                        "end_when": {"type": "array", "items": obj("end")}, "signals": {"type": "array", "items": obj("end")}})
    action = obj("action", {"params": {"type": "array", "items": obj("param", {"require": req})}, "require": req,
                            "steps": steps, "cost": steps})
    return {
        "$schema": "https://json-schema.org/draft/2020-12/schema", "title": "bg-skills game definition (CTR-F-001 v2)",
        "$defs": defs,
        **obj("top", {
            "game": obj("game"), "players": {"type": "array", "items": obj("player")},
            "teams": {"type": "object", "additionalProperties": obj("team")},
            "kinds": {"type": "object", "additionalProperties": obj("kind")},
            "areas": {"type": "array", "items": {"$ref": "#/$defs/area"}},
            "objects": {"type": "array", "items": obj("object")}, "links": {"type": "array", "items": obj("link")},
            "actions": {"type": "array", "items": action}, "flow": flow,
            "metrics": {"type": "array", "items": obj("metric")}, "rules": {"type": "array", "items": obj("rule")},
            "terms": {"type": "object", "additionalProperties": obj("term")},
            "rulings": {"type": "array", "items": obj("ruling")},
            "functions": {"type": "object", "additionalProperties": obj("function")},
            "progress": {"type": "object", "additionalProperties": obj("progress")},
        }),
    }
