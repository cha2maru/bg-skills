"""定義に対する機械的な操作：書き出し（SPC-002）、参照の確認（SPC-003）、版の差分（SPC-006）、逆引き（SPC-010）。"""
from __future__ import annotations

import re

import yaml

from .definition import Definition


class _Dumper(yaml.SafeDumper):
    pass


def _str(dumper, s):
    # 複数行の自然文は改行を保ったブロックで書く
    style = "|" if "\n" in s else None
    return dumper.represent_scalar("tag:yaml.org,2002:str", s, style=style)


_Dumper.add_representer(str, _str)


def dump(data) -> str:
    """キーの順を保ち、日本語をそのまま、複数行の文はブロックで書く。真偽値に読める文字列は引用符で囲まれる。"""
    return yaml.dump(data, Dumper=_Dumper, allow_unicode=True, sort_keys=False, width=1000)


def _pattern(ref: str):
    """'hand-{player}' のような型の参照を正規表現にする。"""
    return re.compile(re.sub(r"\\\{\w+\\\}", r"[^ ]+", re.escape(ref)) + r"\Z")


def _resolves(d: Definition, ref) -> bool:
    if not isinstance(ref, str):
        return False
    if ref in d.index or ref == "links":
        return True
    return "{" in ref and any(_pattern(ref).match(i) for i in d.index)


def check_refs(d: Definition) -> list[dict]:
    """参照先が存在しない参照の一覧。中身の正しさは見ない（RUL-001 #31）。"""
    bad = []

    def need(where, ref):
        if not _resolves(d, ref):
            bad.append({"where": where, "ref": ref})

    for r in d.data.get("rules") or []:
        for x in r.get("refs") or []:
            need(f"rule {r['id']}.refs", x)
    for name, t in d.terms.items():
        for x in t.get("refs") or []:
            need(f"term {name}.refs", x)
    for k, kd in d.kinds.items():
        if kd.get("base") not in (None, "area", "object"):
            need(f"kind {k}.base", kd["base"])
        if d.kinds[d.kind_chain(k)[-1]].get("base") not in ("area", "object"):  # 種類は原型（エリアかオブジェクト）の派生（RUL-005 #2）
            bad.append({"where": f"kind {k}.base", "ref": "area か object にたどり着かない"})
        for u in kd.get("uses") or []:
            for x in u.get("refs") or []:
                need(f"kind {k}.uses {u.get('id')}.refs", x)
    for pid, p in d.parts.items():
        need(f"object {pid}.kind", p.get("kind"))
        if "start" in p:
            need(f"object {pid}.start", p["start"])
        attrs = {}
        for k in d.kind_chain(p.get("kind")):
            attrs.update(d.kinds[k].get("attributes") or {})
        for an, av in (p.get("attributes") or {}).items():
            typ = (attrs.get(an) or {}).get("type", "")
            if typ == "area-ref":
                need(f"object {pid}.attributes.{an}", av)
            elif typ == "area-ref-list":
                for x in av or []:
                    need(f"object {pid}.attributes.{an}", x)
    for aid, a in d.areas.items():
        if a.get("kind"):
            need(f"area {aid}.kind", a["kind"])
        if a.get("owner"):
            need(f"area {aid}.owner", a["owner"])
    def step_refs(where, steps, local):
        """手順の置き場の参照（each・if の中も。each の as と let の名前は変数なので見ない）。"""
        for i, st in enumerate(steps or []):
            here = f"{where}.steps[{i}]"
            names = local | set(st.get("let") or {}) | ({st.get("as", "it")} if "each" in st else set())
            for key in ("do", "else"):
                step_refs(f"{here}.{key}", st.get(key), names)
            if "let" in st and len(st) == 1:
                local = names
            if "call" in st:  # ほかのアクションの手順を呼ぶ
                if st["call"] not in {a["id"] for a in d.data.get("actions") or []}:
                    bad.append({"where": f"{here}.call", "ref": st["call"]})
                continue
            if st.get("op") in ("advance", "progress", "end", "say"):  # to・value はエリアではない
                continue
            for key in ("to", "from", "area", "obj", "into"):
                v = st.get(key)
                if not isinstance(v, str) or set(re.findall(r"\{(\w+)\}", v)) & names:
                    continue
                v = v.split(":", 1)[1] if v.split(":", 1)[0] in ("top", "bottom", "random") and ":" in v else v
                need(f"{here}.{key}", v.replace("{actor}", "{player}"))

    fl = d.data.get("flow") or {}
    acts = {a["id"] for a in d.data.get("actions") or []}
    sids = {st["id"] for st in fl.get("stages") or []}
    for st in fl.get("stages") or []:
        for x in st.get("actions") or []:
            if x not in acts:
                bad.append({"where": f"flow.stages {st['id']}.actions", "ref": x})
        if st.get("turn") and st["turn"] not in (fl.get("turns") or {}):
            bad.append({"where": f"flow.stages {st['id']}.turn", "ref": st["turn"]})
        step_refs(f"flow.stages {st['id']}.on_start", st.get("on_start"), set())
    for tid, t in (fl.get("turns") or {}).items():
        refs = [(f"phases {p['id']}.main", x) for p in t.get("phases") or [] for x in p.get("main") or []]
        refs += [(key, x["action"]) for key in ("free", "reactions") for x in t.get(key) or []]
        bad += [{"where": f"flow.turns {tid}.{w}", "ref": x} for w, x in refs if x not in acts]
        pids = {p["id"] for p in t.get("phases") or []}
        bad += [{"where": f"flow.turns {tid}.free {x['action']}.phases", "ref": ph}
                for x in t.get("free") or [] for ph in x.get("phases") or [] if ph not in pids]
        step_refs(f"flow.turns {tid}.on_start", t.get("on_start"), set())
    for key in ("from", "to"):
        if fl.get("cycle") and fl["cycle"].get(key) not in sids:
            bad.append({"where": f"flow.cycle.{key}", "ref": fl["cycle"].get(key)})
    bad += check_exprs(d)
    for i, l in enumerate(d.data.get("links") or []):
        for x in l.get("between") or []:
            need(f"links[{i}].between", x)
    for g, gd in (d.data.get("groups") or {}).items():
        for m in gd.get("members") or []:
            for x in m if isinstance(m, list) else [m]:
                need(f"group {g}.members", x)
    for p in d.data["players"]:
        if p.get("team"):
            need(f"player {p['id']}.team", p["team"])
    for name, pr in (d.data.get("progress") or {}).items():
        for x in pr.get("refs") or []:
            need(f"progress {name}.refs", x)
    for a in d.data.get("actions") or []:
        if a.get("rule"):
            need(f"action {a['id']}.rule", a["rule"])
        params = {p["name"] for p in a.get("params") or []}
        for p in a.get("params") or []:
            for key in ("from", "in"):
                if p.get(key):
                    need(f"action {a['id']}.params.{p['name']}.{key}", p[key].replace("{actor}", "{player}"))
        step_refs(f"action {a['id']}", a.get("steps"), params)
        step_refs(f"action {a['id']}.cost", a.get("cost"), params)
    mids = {m["id"] for m in d.data.get("metrics") or []}
    for m in d.data.get("metrics") or []:
        conds = ([m["count"]] if "count" in m else []) + [t["count"] for t in m.get("sum") or [] if "count" in t]
        for c in conds:
            if c.get("in"):
                need(f"metric {m['id']}.in", c["in"])
            if c.get("kind"):
                need(f"metric {m['id']}.kind", c["kind"])
        for t in m.get("sum") or []:
            if "metric" in t and t["metric"] not in mids:
                bad.append({"where": f"metric {m['id']}.sum", "ref": t["metric"]})
        for x in m.get("refs") or []:
            need(f"metric {m['id']}.refs", x)
    from .definition import table_layout
    tl = table_layout(d)
    if tl:
        for x in tl["center"] + [a for ids in tl["per_player"].values() for a in ids] + list(tl["place"]):
            need("table", x)
    return bad


def check_exprs(d: Definition) -> list[dict]:
    """定義の中の式（expr・if・each・let の値）を、計算せずに確かめる。"""
    from .expr import context, problems
    known = set(context(d, {"places": {}, "states": {}, "progress": {}}))
    out = []

    def walk(x, where):
        if isinstance(x, list):
            for i, y in enumerate(x):
                walk(y, f"{where}[{i}]")
        elif isinstance(x, dict):
            for k, v in x.items():
                srcs = {}
                if k in ("expr", "if", "talk") or (k == "each" and v != "players"):
                    srcs = {k: v}
                elif k in ("let", "derived") and isinstance(v, dict):
                    srcs = {f"let.{n}": e for n, e in v.items()}
                for name, src in srcs.items():
                    if isinstance(src, str):
                        msg = problems(re.sub(r"\{(\w+)\}", r"\1", src), known) or _unknown_names(d, src)  # {引数} は値に置き換わる
                        if msg:
                            out.append({"where": f"{where}.{name}", "ref": f"{src}（{msg}）"})
                walk(v, f"{where}.{k}" if where else k)

    walk({k: v for k, v in d.data.items() if k in ("actions", "flow", "metrics", "functions")} | {"kinds": {k: {"derived": v["derived"]} for k, v in (d.data.get("kinds") or {}).items() if isinstance(v, dict) and v.get("derived")}}, "")
    return out


def _unknown_names(d, src: str) -> str | None:
    """式の中で文字列で書いた名前（progress・metric の鍵、state・attr・where の部品）が定義にあるかを確かめる。"""
    import ast
    try:
        tree = ast.parse(src, mode="eval")
    except SyntaxError:
        return None
    ids = {"progress": set(d.data.get("progress") or {}), "metric": {m["id"] for m in d.data.get("metrics") or []},
           "state": set(d.parts), "attr": set(d.parts), "where": set(d.parts)}
    bad = sorted({f"{n.func.id}('{n.args[0].value}')" for n in ast.walk(tree)
                  if isinstance(n, ast.Call) and isinstance(n.func, ast.Name) and n.func.id in ids and n.args
                  and isinstance(n.args[0], ast.Constant) and isinstance(n.args[0].value, str)
                  and "{" not in n.args[0].value and n.args[0].value not in ids[n.func.id]})
    return f"定義にない名前: {', '.join(bad)}" if bad else None


def rules_referencing(d: Definition, target: str) -> list[str]:
    """target（部品・種類・エリア・用語など）を参照するルール。部品は種類を、用語は用語が指すものを通じても引く。"""
    targets = {target, *d.kind_chain(d.kind_of(target) or target)}
    terms = {t for t, td in d.terms.items() if targets & set(td.get("refs") or [])}
    targets |= terms

    def hit(ref):
        return ref in targets or ("{" in ref and any(_pattern(ref).match(t) for t in targets))

    return [r["id"] for r in d.data.get("rules") or [] if any(hit(x) for x in r.get("refs") or [] if isinstance(x, str))]


def _flat(d: Definition) -> dict:
    return {i: el for i, (_, el) in d.index.items()}


def diff(a: Definition, b: Definition) -> dict:
    """2 つの版の要素の違い（展開した形で比べる）。"""
    fa, fb = _flat(a), _flat(b)
    changed = {}
    for i in fa.keys() & fb.keys():
        if fa[i] != fb[i]:
            ea, eb = fa[i], fb[i]
            if isinstance(ea, dict) and isinstance(eb, dict):
                changed[i] = {k: {"from": ea.get(k), "to": eb.get(k)} for k in ea.keys() | eb.keys() if ea.get(k) != eb.get(k)}
            else:
                changed[i] = {"from": ea, "to": eb}
    def counts(d):
        c = {}
        for pid, p in d.parts.items():
            n = 1 if d.distinct(pid) else p.get("count", 1)
            if isinstance(n, int):
                c[p.get("kind")] = c.get(p.get("kind"), 0) + n
        return c

    ca, cb = counts(a), counts(b)
    kinds = {k: {"from": ca.get(k, 0), "to": cb.get(k, 0)} for k in ca.keys() | cb.keys() if ca.get(k, 0) != cb.get(k, 0)}
    return {
        "versions": [a.data["game"].get("version"), b.data["game"].get("version")],
        "part_counts": dict(sorted(kinds.items())),
        "added": sorted(fb.keys() - fa.keys()),
        "removed": sorted(fa.keys() - fb.keys()),
        "changed": dict(sorted(changed.items())),
    }


def fuzz(path, players: int, games: int = 3, steps: int = 80, seed: int = 0) -> dict:
    """でたらめ実行：アクションと引数をでたらめに選んで行い、局面・見え方・指標・知らせを作る。
    受け付けない（OpError）のは普通。式の誤り（定義の誤り）と、それ以外の例外（エンジンの不具合）を集める。"""
    import json
    import random
    import tempfile
    from pathlib import Path
    import traceback
    from collections import Counter
    from .expr import ExprError
    from .flow import end_signals
    from .metrics import compute
    from .query import candidates
    from .session import OpError, Session
    from .view import view
    done, refused, expr_errors, crashes = Counter(), Counter(), {}, {}
    for g in range(games):
        rnd = random.Random(f"{seed}:{g}")
        # 厳格モード：条件・進行から外れた行為は手順の前に断る（手順の式の誤りは、行えるはずの局面で起きたものだけになる）
        s = Session.create(Path(tempfile.mkdtemp()) / "s", path, players, {}, seed + g, strict=True)
        # 対局を終える手順（op: end）のあるアクションは、でたらめに選ぶとすぐ終わるので最後の 1 割だけ
        ends = {a["id"] for a in s.defn.data.get("actions") or [] if '"op": "end"' in json.dumps(a.get("steps"))}
        acts_all = s.defn.data.get("actions") or []
        who = list(s.defn.players) + ["keeper"]
        for k in range(steps if acts_all else 0):
            if s.state()["result"] is not None:
                break
            if s.state().get("stack") and rnd.random() < 0.5:  # スタックがあれば、半分は見送る（解決を進める）
                try:
                    s.apply({"op": "pass", "by": rnd.choice(list(s.defn.players))})
                    done["(pass)"] += 1
                except OpError:
                    pass
                continue
            if s.state().get("flow") and rnd.random() < 0.15:  # ときどき進行を進める（段階・フェーズ・手番）
                try:
                    s.apply({"op": "advance", "by": "keeper", "to": rnd.choice(["phase", "phase", "turn", "stage"])})
                    done["(advance)"] += 1
                except OpError:
                    pass
                continue
            acts = [x for x in acts_all if x["id"] not in ends or k >= steps * 0.9]
            a, args = rnd.choice(acts), {}
            by = rnd.choice(a.get("by") or list(s.defn.players))  # 行える人（by）から。なければプレイヤー
            try:
                st = s.state()
                for prm in a.get("params") or []:
                    if prm.get("pick") == "first" or prm.get("free"):
                        continue
                    cs = candidates(s.defn, st, a["id"], by, prm["name"], args)
                    good = [c["id"] for c in cs if not c["problems"]] or [c["id"] for c in cs]
                    if good:
                        args[prm["name"]] = rnd.choice(good)
                s.act(a["id"], by, args)
                done[a["id"]] += 1
                st = s.state()
                view(s.defn, st, rnd.choice(who[:-1]))
                compute(s.defn, st, None)
                for key in ("end_when", "signals"):
                    for x in end_signals(s.defn, st, key):
                        if x.startswith("式を計算できない"):
                            expr_errors.setdefault(x, a["id"])
            except ExprError as e:
                expr_errors.setdefault(str(e), a["id"])
            except OpError as e:
                (expr_errors.setdefault(str(e), a["id"]) if "式の評価に失敗" in str(e) else None)
                refused[a["id"]] += 1
            except Exception as e:  # noqa: BLE001（エンジンの不具合として集める）
                crashes.setdefault(f"{a['id']}: {type(e).__name__}: {e}", traceback.format_exc(limit=3)[-600:])
    never = [a["id"] for a in s.defn.data.get("actions") or [] if not done[a["id"]]] if games else []
    return {"done": dict(done), "refused": dict(refused), "never_done": never,
            "expr_errors": [{"error": k, "action": v} for k, v in expr_errors.items()],
            "crashes": [{"error": k, "trace": v} for k, v in crashes.items()]}


def selfplay(path, players: int, games: int = 20, max_turns: int = 60, seed: int = 0) -> dict:
    """作品を問わない対戦（バランスの目安）：手番の人が、今行えるアクション（進行の available）から、条件を満たす候補で
    でたらめに選ぶ。行えるものがなければ手番を進める。スタックがあれば、見送り待ちの人が見送る。終わり（end_when の知らせか、
    op: end）で止め、結果ごとに数える。作品専用のボットより弱く、強い手を選ばない（偏りの目安で、強さの比較ではない）。"""
    import random
    import tempfile
    from collections import Counter
    from pathlib import Path
    from .flow import available, end_signals
    from .query import candidates
    from .session import OpError, Session, _stack_next
    outcomes, turns = Counter(), []
    for g in range(games):
        rnd = random.Random(f"{seed}:{g}")
        s = Session.create(Path(tempfile.mkdtemp()) / "s", path, players, {}, seed + g, strict=True)
        acts = {a["id"]: a for a in s.defn.data.get("actions") or []}
        result, staged = None, {}
        if not (s.defn.data.get("flow") or {}).get("stages"):
            return {"error": "進行（flow）のない定義は、手番の人が分からないので selfplay できない"}
        for _ in range(max_turns * 30):
            st = s.state()
            if st["result"] is not None:  # 自動で終わった（flow.auto_end）・終わらせるアクション
                r = st["result"]
                result = r.get("text") or "・".join(f"{p}:{v}" for p, v in (r.get("results") or {}).items())
                break
            sig = end_signals(s.defn, st)
            if sig:
                result = sig[0]
                break
            f = st.get("flow") or {}
            if f.get("turn_no", 0) > max_turns or not f.get("stage"):
                result = "決着なし"
                break
            if st.get("stack"):  # 見送り待ちの人が見送る（応じる手は打たない）
                nxt = _stack_next(s.defn, st)["by"]
                waiting = [p for p in s.defn.players if p != nxt and p not in (st.get("stack_passes") or [])]
                s.apply({"op": "pass", "by": waiting[0]}) if waiting else s.apply({"op": "resolve", "by": "keeper"})
                continue
            who = f.get("active") or "keeper"
            av = available(s.defn, f, who)
            stage_done = staged.setdefault(f.get("stage"), set())  # 手番のない段階（準備）のアクションは 1 回ずつ
            if f.get("active"):
                pairs = [(i, who) for k in ("main", "free") for i in av.get(k, [])]
            else:  # 手番のない段階（準備・人狼の昼夜）：キーパーと各プレイヤーを、行う人として試す。1 人 1 回ずつ
                pairs = [(i, p) for p in ["keeper"] + list(s.defn.players)
                         for i in available(s.defn, f, p).get("stage", []) if (i, p) not in stage_done]
            pairs = [(i, p) for i, p in pairs if "'op': 'end'" not in str(acts[i].get("steps"))]
            done = False
            for aid, actor in [x for x in rnd.sample(pairs, len(pairs)) for _ in range(6)]:  # 引数の選び直しも試す
                if done:
                    break
                a, args = acts[aid], {}
                try:
                    for prm in a.get("params") or []:
                        if prm.get("free") or prm.get("pick") == "first":
                            continue
                        good = [c["id"] for c in candidates(s.defn, s.state(), aid, actor, prm["name"], args) if not c["problems"]]
                        if not good:
                            raise OpError("候補がない")
                        args[prm["name"]] = rnd.choice(good)
                    s.act(aid, actor, args)
                    if not f.get("active"):
                        stage_done.add((aid, actor))
                    done = True
                except OpError:
                    continue
            if not done:
                for to in (("turn", "stage") if f.get("active") else ("stage", "phase")):
                    try:
                        s.apply({"op": "advance", "by": "keeper", "to": to})
                        break
                    except OpError:
                        continue
                else:
                    result = "進められない"
                    break
        outcomes[result or "打ち切り"] += 1
        turns.append((s.state().get("flow") or {}).get("turn_no", 0))
    return {"games": games, "outcomes": dict(outcomes.most_common()), "avg_turns": round(sum(turns) / max(1, len(turns)), 1)}


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
    used = {a.get("rule") for a in acts} | {c.get("rule") for c in (d.data.get("flow") or {}).get("end_when") or []}
    text_only = [r["id"] for r in rules if r["id"] not in used]
    fl = d.data.get("flow") or {}
    phases = sum(len(t.get("phases") or []) for t in (fl.get("turns") or {}).values())
    conds = sum(len(a.get("require") or []) + sum(len(p.get("require") or []) for p in a.get("params") or []) for a in acts)
    end = fl.get("end_when") or []
    return {
        "rules": len(rules), "rule_chars": sum(len(r.get("text") or "") for r in rules),
        "rules_text_only": {"count": len(text_only), "ids": text_only},  # どのアクション・終わりの条件にも結びつかないルール
        "actions": len(acts), "params": sum(len(a.get("params") or []) for a in acts), "conditions": conds,
        "steps": sum(len(a.get("steps") or []) for a in acts), "expressions": len(exprs), "expression_nodes": nodes,
        "stages": len(fl.get("stages") or []), "phases": phases,
        "end_conditions": {"count": len(end), "with_result": sum(1 for c in end if c.get("winners") or c.get("losers") or c.get("draw")),
                           "timed": sum(1 for c in end if c.get("timing") not in (None, "now"))},
        "scoring": bool(fl.get("scoring")), "kinds": len(d.kinds), "parts": len(d.parts), "areas": len(d.areas),
    }
