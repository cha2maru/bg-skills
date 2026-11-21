"""物差し：ルールの複雑さ（bg complexity）と、対局の手間（bg playstats）。"""
from __future__ import annotations

import re

from .definition import Definition


def complexity(d: Definition) -> dict:
    """ルールの複雑さの目安：数（ルール・アクション・引数・条件・式の大きさ・進行）と、機械で確かめられないルールの割合。
    設計の比較（版ごと）に使う。数が多いほど、エージェントも人も読む量・覚えることが増える。"""
    import ast
    acts = d.data.get("actions") or []
    rules = d.data.get("rules") or []
    exprs = []

    def walk(x):
        if isinstance(x, dict):
            for k, v in x.items():
                if k in ("expr", "if", "each", "talk") and isinstance(v, str) and v != "players":
                    exprs.append(v)
                elif k in ("let", "derived") and isinstance(v, dict):
                    exprs.extend(e for e in v.values() if isinstance(e, str))
                walk(v)
        elif isinstance(x, list):
            for y in x:
                walk(y)
    walk({k: d.data.get(k) for k in ("actions", "flow", "metrics", "functions", "kinds")})
    nodes = 0
    for e in exprs:
        try:
            nodes += sum(1 for _ in ast.walk(ast.parse(e.replace("{", "").replace("}", ""), mode="eval")))
        except SyntaxError:
            pass
    fl = d.data.get("flow") or {}
    layer = {r["id"]: [] for r in rules}  # ルールごとの機械の層（どのアクション・終わりの条件・指標・知らせがそのルールを行うか）
    for a in acts:
        if a.get("rule") in layer:
            n = len(a.get("require") or []) + sum(len(p.get("require") or []) for p in a.get("params") or [])
            layer[a["rule"]].append(f"action {a['id']}" + (f"（条件 {n}）" if n else ""))
    for key in ("end_when", "signals"):
        for c in fl.get(key) or []:
            if c.get("rule") in layer:
                layer[c["rule"]].append(key)
            for rid in re.findall(r"R\d+", c.get("text") or ""):
                if rid in layer and key not in layer[rid]:
                    layer[rid].append(key)
    for m in d.data.get("metrics") or []:
        for rid in m.get("refs") or []:
            if rid in layer:
                layer[rid].append(f"metric {m['id']}")
    for r in d.data.get("rulings") or []:
        for rid in r.get("rules") or []:
            if rid in layer:
                layer[rid].append(f"ruling {r.get('id')}" + ("（未決）" if r.get("status") == "open" else ""))
    for r in rules:  # 手引きのルールが詳細ルールを指し、その詳細ルールに機械の層があれば、それを通じて機械の層を持つ（RUL-024）
        if not r.get("detail") and not layer[r["id"]]:
            layer[r["id"]] += [f"via {x}" for x in r.get("refs") or [] if x in layer and layer[x] and (d.rules.get(x) or {}).get("detail")]
    text_only = [rid for rid, xs in layer.items() if not xs]
    phases = sum(len(t.get("phases") or []) for t in (fl.get("turns") or {}).values())
    conds = sum(len(a.get("require") or []) + sum(len(p.get("require") or []) for p in a.get("params") or []) for a in acts)
    end = fl.get("end_when") or []
    return {
        "rules": len(rules), "rule_chars": sum(len(r.get("text") or "") for r in rules),
        "rules_detail": sum(1 for r in rules if r.get("detail")),  # 詳細ルール（手引きに出さない。RUL-024）
        "rules_text_only": {"count": len(text_only), "ids": text_only},  # 機械の層がないルール（キーパーが文で裁く）
        "machine_layer": {rid: xs for rid, xs in layer.items() if xs},  # ルールごとに、機械で行う部分
        "actions": len(acts), "params": sum(len(a.get("params") or []) for a in acts), "conditions": conds,
        "steps": sum(len(a.get("steps") or []) for a in acts), "expressions": len(exprs), "expression_nodes": nodes,
        "stages": len(fl.get("stages") or []), "phases": phases,
        "end_conditions": {"count": len(end), "with_result": sum(1 for c in end if c.get("winners") or c.get("losers") or c.get("draw")),
                           "timed": sum(1 for c in end if c.get("timing") not in (None, "now"))},
        "rulings": {"count": len(d.data.get("rulings") or []), "open": sum(1 for r in d.data.get("rulings") or [] if r.get("status") == "open"),
                    "principles": sum(1 for r in d.data.get("rulings") or [] if r.get("principle"))},
        "scoring": bool(fl.get("scoring")), "kinds": len(d.kinds), "parts": len(d.parts), "areas": len(d.areas),
    }


ACTING = {"act", "op", "say", "answer", "pass", "resolve", "advance", "undo"}


def playstats(s) -> dict:
    """エージェントが対局でどれだけ迷ったかの物差し（目的「定義を不足なく読める」を測る）。
    コマンドの数（調べる・行う）、受け付けなかった行為（厳格モードの拒否・条件や引数の誤り）、手番あたり、プレイヤーごと。"""
    import json
    from collections import Counter
    path = s.dir / "usage.jsonl"
    rows = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line] if path.exists() else []
    turns = max(1, ((s.state().get("flow") or {}).get("turn_no") or 1))
    acting = [r for r in rows if r["cmd"] in ACTING]
    rejected = [r for r in acting if r.get("error")]
    per = {}
    for r in rows:
        w = r.get("who") or "-"
        p = per.setdefault(w, {"commands": 0, "acting": 0, "rejected": 0})
        p["commands"] += 1
        p["acting"] += r["cmd"] in ACTING
        p["rejected"] += r["cmd"] in ACTING and bool(r.get("error"))
    reasons = Counter(r["error"].split("：", 1)[-1][:40] for r in rejected)
    return {"turns": turns, "commands": len(rows), "by_command": dict(Counter(r["cmd"] for r in rows).most_common()),
            "acting": len(acting), "rejected": len(rejected),
            "rejected_rate": round(len(rejected) / max(1, len(acting)), 3),
            "commands_per_turn": round(len(rows) / turns, 1), "per_seat": per,
            "top_rejections": dict(reasons.most_common(8))}
