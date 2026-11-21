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

    for aid, a in d.areas.items():  # 形（path）は、祖先のどれかの viewbox の座標で描く（RUL-025）
        if a.get("path"):
            p = d.parent.get(aid)
            while p and not d.areas[p].get("viewbox"):
                p = d.parent.get(p)
            if not p:
                bad.append({"where": f"area {aid}.path", "ref": "祖先のエリアに viewbox がない（path の座標系が決まらない）"})
        if a.get("slot") and not d.parent.get(aid):
            bad.append({"where": f"area {aid}.slot", "ref": "配置場所は、意味を持つ親のエリアの中に置く"})
        if a.get("viewbox") and len(str(a["viewbox"]).replace(",", " ").split()) != 4:
            bad.append({"where": f"area {aid}.viewbox", "ref": f"{a['viewbox']}（「x y 幅 高さ」の 4 つの数）"})
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
    bad += check_rulings(d)
    bad += check_exprs(d)
    from .schema import unknown_keys
    bad += unknown_keys(d.raw if hasattr(d, "raw") else d.data)  # 形式に無い項目（打ち間違い）
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
                        if not msg and re.search(r"\{(\w+)\}", src):  # 式の中は変数をそのまま書く（{x} の置き換えと二通りにしない）
                            msg = "式の中では {" + re.search(r"\{(\w+)\}", src).group(1) + "} ではなく、そのまま " + re.search(r"\{(\w+)\}", src).group(1) + " と書く"
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


AUTHORITY = ["official", "author", "designer", "keeper"]  # 裁定の重み（上ほど強い。一次資料の明文が見つかれば、それが裁定より強い）


def check_rulings(d: Definition) -> list[dict]:
    """裁定の形：決まった裁定には decision、未決（status: open）には question。rules・refs・supersedes の参照先。"""
    bad = []
    rule_ids = {r["id"] for r in d.data.get("rules") or []}
    ruling_ids = {r.get("id") for r in d.data.get("rulings") or []}
    for i, r in enumerate(d.data.get("rulings") or []):
        w = f"rulings[{i}]"
        if not r.get("id"):
            bad.append({"where": w, "ref": "裁定に id がない"})
        if not r.get("question") and not r.get("principle"):
            bad.append({"where": w, "ref": "裁定に question（問い）がない"})
        if r.get("status", "decided") == "decided" and not r.get("decision"):
            bad.append({"where": w, "ref": "決まった裁定に decision（裁定）がない（未決なら status: open）"})
        if r.get("authority") and r["authority"] not in AUTHORITY:
            bad.append({"where": f"{w}.authority", "ref": f"{r['authority']}（{'・'.join(AUTHORITY)} のどれか）"})
        for x in r.get("rules") or []:
            if x not in rule_ids:
                bad.append({"where": f"{w}.rules", "ref": x})
        for x in r.get("refs") or []:
            if x not in d.index and x not in rule_ids:
                bad.append({"where": f"{w}.refs", "ref": x})
        if r.get("supersedes") and r["supersedes"] not in ruling_ids:
            bad.append({"where": f"{w}.supersedes", "ref": r["supersedes"]})
    return bad


def rulings_for(d: Definition, rule_ids=(), target=None) -> list[dict]:
    """ルール（か部品・種類）に関わる裁定（決まったもの・未決とも）。一般の原則（principle）は含めない。"""
    out = []
    targets = {target, *d.kind_chain(d.kind_of(target) or target)} if target else set()
    for r in d.data.get("rulings") or []:
        if set(r.get("rules") or []) & set(rule_ids) or targets & set(r.get("refs") or []):
            out.append({k: r[k] for k in ("id", "question", "decision", "status", "authority") if k in r})
    return out


def rulings_report(d: Definition, session=None) -> dict:
    """定義の裁定の一覧（決まった・未決・一般の原則）と、対局中の裁定のうち定義にまだ無いもの（持ち帰る候補。SPC-020）。"""
    rs = d.data.get("rulings") or []
    out = {"decided": [r["id"] for r in rs if r.get("status", "decided") == "decided" and not r.get("principle")],
           "open": [{"id": r["id"], "question": r.get("question")} for r in rs if r.get("status") == "open"],
           "principles": [{"id": r["id"], "decision": r.get("decision")} for r in rs if r.get("principle")]}
    if session is not None:
        decided = {(r.get("question") or "").strip() for r in rs if r.get("status", "decided") == "decided"}
        opened = {(r.get("question") or "").strip(): r["id"] for r in rs if r.get("status") == "open"}
        cand = []
        for k, r in enumerate(session.state().get("rulings") or [], 1):
            q = (r.get("question") or "").strip()
            if q in decided:
                continue
            # 定義で未決の問いなら、その id を決まった裁定に書き換える候補（穴を埋める）
            cand.append({"id": opened.get(q) or f"J-{session.dir.name}-{k}", "question": r.get("question"), "decision": r.get("decision"),
                         **({"reason": r["reason"]} if r.get("reason") else {}), **({"rules": r["rules"]} if r.get("rules") else {}),
                         "status": "decided", "authority": "keeper", "by": r.get("by", "keeper"),
                         "date": (r.get("time") or "")[:10], "found_in": session.dir.name})
        out["to_bring_back"] = cand  # 定義の rulings に貼れる形（了承を得てから書く。SPC-020）
    return out


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


def fuzz(path, players: int, games: int = 3, steps: int = 80, seed: int = 0, variants=None) -> dict:
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
        s = Session.create(Path(tempfile.mkdtemp()) / "s", path, players, {}, seed + g, strict=True, variants=variants)
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


def random_step(s, rnd, staged: dict, max_turns: int = 60) -> str | None:
    """でたらめの 1 歩（selfplay・quiz で使う）：手番の人が今行える手から、条件を満たす候補で選んで行う。
    行えるものがなければ進行を進める。スタックがあれば見送る。終わったら終わり方の文を返す（続くなら None）。"""
    from .flow import available, end_signals
    from .query import candidates
    from .session import OpError, _stack_next
    st = s.state()
    if st["result"] is not None:  # 自動で終わった（flow.auto_end）・終わらせるアクション
        r = st["result"]
        return r.get("text") or "・".join(f"{p}:{v}" for p, v in (r.get("results") or {}).items())
    sig = end_signals(s.defn, st)
    if sig and not (s.defn.data.get("flow") or {}).get("auto_end"):  # 自動で終える定義は、時機（巡の終わりなど）を待って結果が記録されるまで進める
        return sig[0]
    f = st.get("flow") or {}
    if f.get("turn_no", 0) > max_turns or not f.get("stage"):
        return "決着なし"
    if st.get("stack"):  # 見送り待ちの人が見送る（応じる手は打たない）
        nxt = _stack_next(s.defn, st)["by"]
        waiting = [p for p in s.defn.players if p != nxt and p not in (st.get("stack_passes") or [])]
        s.apply({"op": "pass", "by": waiting[0]}) if waiting else s.apply({"op": "resolve", "by": "keeper"})
        return None
    acts = {a["id"]: a for a in s.defn.data.get("actions") or []}
    who = f.get("active") or "keeper"
    av = available(s.defn, f, who)
    stage_done = staged.setdefault(f.get("stage"), set())  # 手番のない段階（準備）のアクションは 1 人 1 回ずつ
    if f.get("active"):
        pairs = [(i, who) for k in ("main", "free") for i in av.get(k, [])]
    else:  # 手番のない段階（準備・人狼の昼夜）：キーパーと各プレイヤーを、行う人として試す
        pairs = [(i, p) for p in ["keeper"] + list(s.defn.players)
                 for i in available(s.defn, f, p).get("stage", []) if (i, p) not in stage_done]
    pairs = [(i, p) for i, p in pairs if "'op': 'end'" not in str(acts[i].get("steps"))]
    for aid, actor in [x for x in rnd.sample(pairs, len(pairs)) for _ in range(6)]:  # 引数の選び直しも試す
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
            return None
        except OpError:
            continue
    for to in (("phase", "turn", "stage") if f.get("active") else ("stage", "phase")):  # 次のフェイズへ（手番ごと飛ばすとメインフェイズに入らない作品がある）
        try:
            s.apply({"op": "advance", "by": "keeper", "to": to})
            return None
        except OpError:
            continue
    return "進められない"


def selfplay(path, players: int, games: int = 20, max_turns: int = 60, seed: int = 0, variants=None) -> dict:
    """作品を問わない対戦（バランスの目安）：random_step を終わるまで繰り返し、終わり方ごとに数える。
    作品専用のボットより弱く、強い手を選ばない（偏りの目安で、強さの比較ではない）。"""
    import random
    import tempfile
    from collections import Counter
    from pathlib import Path
    from .session import Session
    outcomes, turns, seats = Counter(), [], {}
    for g in range(games):
        rnd = random.Random(f"{seed}:{g}")
        s = Session.create(Path(tempfile.mkdtemp()) / "s", path, players, {}, seed + g, strict=True, variants=variants)
        if not (s.defn.data.get("flow") or {}).get("stages"):
            return {"error": "進行（flow）のない定義は、手番の人が分からないので selfplay できない"}
        staged, result = {}, None
        for _ in range(max_turns * 30):
            result = random_step(s, rnd, staged, max_turns)
            if result:
                break
        outcomes[result or "打ち切り"] += 1
        st = s.state()
        turns.append((st.get("flow") or {}).get("turn_no", 0))
        for p, r in ((st.get("result") or {}).get("results") or {}).items():  # 席ごとの勝ち・負け・引き分け（先手の有利の目安）
            seats.setdefault(p, Counter())[r] += 1
    out = {"games": games, "outcomes": dict(outcomes.most_common()), "avg_turns": round(sum(turns) / max(1, len(turns)), 1)}
    if seats:
        out["seats"] = {p: dict(c) for p, c in seats.items()}
        out["win_rate"] = {p: round(c.get("win", 0) / games, 2) for p, c in seats.items()}
    return out


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


def quiz(path, players: int, n: int = 20, seed: int = 0, out=None) -> dict:
    """ルールの理解の小テスト：でたらめに進めた局面で「Pn は今、このアクションをこの引数で行えるか」を問う。
    正解はエンジン（厳格モード）の判定。問題ごとに局面を写した対局のフォルダを作る（bg show --as で見て答える。
    bg candidates は答えそのものなので使わせない）。答えは answers.yaml に分けて書く。"""
    import random
    import shutil
    import tempfile
    from pathlib import Path
    import yaml as _yaml
    from .query import candidates
    from .session import OpError, Session
    out = Path(out or tempfile.mkdtemp())
    out.mkdir(parents=True, exist_ok=True)
    rnd = random.Random(seed)
    qs, answers = [], {}
    g = 0
    while len(qs) < n and g < n * 12:
        g += 1
        s = Session.create(out / f"_base{g}", path, players, {}, seed * 1000 + g, strict=True)
        acts = s.defn.data.get("actions") or []
        staged = {}
        for _ in range(rnd.randint(3, 120)):  # でたらめに進める（selfplay と同じ 1 歩）
            if random_step(s, rnd, staged):
                break
        fl = s.state().get("flow") or {}
        if s.state()["result"] is not None or (s.defn.data.get("flow") and not fl.get("stage")):
            continue  # 終わった局面・進行が終わった局面は問いにしない（答えがみな「行えない」になる）
        # 問い：プレイヤーのアクションと引数（行える問いと行えない問いを半々に）
        pa = [a for a in acts if "keeper" not in (a.get("by") or [])]
        if not pa:
            break
        okish = sum(v["answer"] == "yes" for v in answers.values()) < n / 2 and rnd.random() < 0.7
        act_now = fl.get("active")
        who = act_now if act_now and rnd.random() < 0.7 else rnd.choice(list(s.defn.players))  # 手番の人に寄せる（易しい問いを減らす）
        if okish and fl:  # 行えそうな問い：進行の上で今行えるアクションから選ぶ
            from .flow import available
            av = available(s.defn, fl, who)
            ids = {i for k in ("main", "free", "reaction", "stage") for i in av.get(k, [])}
            pa = [a for a in pa if a["id"] in ids] or pa
        a = rnd.choice(pa)
        args = {}
        try:
            for prm in a.get("params") or []:
                if prm.get("free") or prm.get("pick") == "first":
                    continue
                cs = candidates(s.defn, s.state(), a["id"], who, prm["name"], args)
                pool = [c["id"] for c in cs if bool(c["problems"]) != okish] or [c["id"] for c in cs]
                if not pool:
                    raise OpError("候補がない")
                args[prm["name"]] = rnd.choice(pool)
        except (OpError, ValueError):
            continue
        qid = f"q{len(qs) + 1:02d}"
        trial = out / f"_trial_{qid}"
        shutil.copytree(s.dir, trial)
        try:
            Session(trial).act(a["id"], who, args)
            truth, why = True, ""
        except OpError as e:
            truth, why = False, str(e).replace("厳格モードで受け付けない：", "")
        shutil.rmtree(trial)
        yes = sum(v["answer"] == "yes" for v in answers.values())
        if (truth and yes >= (n + 1) // 2) or (not truth and len(answers) - yes >= n // 2 + (n % 2 == 0 and 0)):
            if g < n * 8:  # 片方に偏ったら捨てて作り直す（作り直しが尽きたら偏りを受け入れる）
                continue
        qdir = out / qid
        shutil.copytree(s.dir, qdir)
        (qdir / "usage.jsonl").unlink(missing_ok=True)
        qs.append({"id": qid, "session": str(qdir), "as": who, "action": a["id"], "args": args,
                   "question": f"{who} は今、{a.get('name', a['id'])}（{a['id']}）を {args or '引数なし'} で行えるか（yes/no と理由）"})
        answers[qid] = {"answer": "yes" if truth else "no", "why": why}
    for p in out.glob("_base*"):
        shutil.rmtree(p)
    (out / "quiz.yaml").write_text(_yaml.safe_dump({"definition": str(path), "questions": qs}, allow_unicode=True, sort_keys=False), encoding="utf-8")
    (out / "answers.yaml").write_text(_yaml.safe_dump(answers, allow_unicode=True, sort_keys=False), encoding="utf-8")
    return {"out": str(out), "questions": len(qs), "yes": sum(v["answer"] == "yes" for v in answers.values())}


def quiz_grade(answers_path, responses_path) -> dict:
    """小テストの採点。responses は {qid: yes|no}（または {qid: {answer: yes|no}}）。"""
    import yaml as _yaml
    ans = _yaml.safe_load(open(answers_path, encoding="utf-8"))
    res = _yaml.safe_load(open(responses_path, encoding="utf-8")) or {}
    wrong = []
    for q, a in ans.items():
        r = res.get(q)
        r = (r or {}).get("answer") if isinstance(r, dict) else r
        r = {True: "yes", False: "no"}.get(r, r) if isinstance(r, bool) else r  # YAML の yes/no は真偽値になる
        if str(r).strip().lower() != a["answer"]:
            wrong.append({"id": q, "expected": a["answer"], "got": r, "why": a["why"]})
    return {"questions": len(ans), "correct": len(ans) - len(wrong), "accuracy": round((len(ans) - len(wrong)) / max(1, len(ans)), 3),
            "wrong": wrong}
