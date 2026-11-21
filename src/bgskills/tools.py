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


def _texts(d: Definition):
    """人が読む文のある場所（場所, 文）：ゲームの概要、部品・置き場・種類の名前と説明、アクション、ルール、用語の説明、裁定、進行の名前。"""
    g = d.data.get("game") or {}
    for k in ("name", "summary"):
        if g.get(k):
            yield f"game.{k}", str(g[k])
    for kid, k in d.kinds.items():
        for f in ("name", "text"):
            if k.get(f):
                yield f"kinds.{kid}.{f}", str(k[f])
    for aid, a in d.areas.items():
        for f in ("name", "text"):
            if a.get(f):
                yield f"areas.{aid}.{f}", str(a[f])
    for pid, p in d.parts.items():
        t = (p.get("attributes") or {}).get("title")
        if isinstance(t, str):
            yield f"objects.{pid}.title", t
    for a in d.data.get("actions") or []:
        for f in ("name", "when", "text"):
            if a.get(f):
                yield f"actions.{a['id']}.{f}", str(a[f])
    for r in d.data.get("rules") or []:
        yield f"rules.{r['id']}", str(r.get("text") or "")
    for tid, t in d.terms.items():
        if t.get("text"):
            yield f"terms.{tid}.text", str(t["text"])
    for r in d.data.get("rulings") or []:
        for f in ("question", "decision", "reason"):
            if r.get(f):
                yield f"rulings.{r.get('id')}.{f}", str(r[f])
    fl = d.data.get("flow") or {}
    for st in fl.get("stages") or []:
        if st.get("name"):
            yield f"flow.stages.{st['id']}.name", str(st["name"])
    for tid, t in (fl.get("turns") or {}).items():
        for ph in t.get("phases") or []:
            if ph.get("name"):
                yield f"flow.turns.{tid}.{ph['id']}.name", str(ph["name"])
    for key in ("end_when", "signals"):
        for i, c in enumerate(fl.get(key) or []):
            if c.get("text"):
                yield f"flow.{key}[{i}].text", str(c["text"])


def check_wording(d: Definition) -> list[dict]:
    """用語の表記（RUL-029）：用語の avoid（使わない言葉）が人の読む文に出ていたら、言い換えの候補（用語の word）と場所を返す。
    ほかの用語の言葉・初出の表記の中に含まれる部分（「切札」の「札」など）は数えない。誤りではなく知らせ（bg check の wording）。"""
    words = sorted({str(x) for t in d.terms.values() for x in (t.get("word"), t.get("first")) if x}, key=len, reverse=True)
    avoid = [(str(w), t.get("word") or tid) for tid, t in d.terms.items() for w in (t.get("avoid") or [])]
    out = []
    if not avoid:
        return out
    for where, text in _texts(d):
        own = where.split(".")[1] if where.startswith("terms.") else None  # 用語の説明で、その用語が避ける言葉を挙げるのは数えない
        masked = text
        for w in words:  # 登録した用語の中の文字は数えない（「切札」が用語なら、その中の「札」は言い換えない）
            masked = masked.replace(w, "\0" * len(w))
        mine = set((d.terms.get(own) or {}).get("avoid") or []) if own else set()
        for bad, prefer in avoid:
            if bad and bad in masked and bad not in words and bad not in mine:
                i = masked.index(bad)
                out.append({"where": where, "word": bad, "prefer": prefer, "at": text[max(0, i - 8): i + len(bad) + 8]})
    return out


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


# でたらめに進める道具と物差しは、別のモジュールに分けた（リファクタ）。これまでどおり tools から読める
from .measure import ACTING, complexity, playstats  # noqa: E402,F401
from .sim import fuzz, quiz, quiz_grade, random_step, selfplay  # noqa: E402,F401
