"""見え方の切り出し（SPC-011）と意味つきの局面（SPC-009）。局面と定義の機械的な結合だけで、推論はしない。"""
from __future__ import annotations

from .definition import Definition
from .tools import rules_referencing, rulings_for

STAGES = ("exists", "count", "back", "face", "order")
_DEFAULT = {s: "all" for s in STAGES}



def visibility(d: Definition, area_id) -> dict:
    """エリアの公開範囲（未指定の段階は親のエリアから、根は全員に見せる）。"""
    chain, a = [], area_id
    while a:
        chain.append(a)
        a = d.parent.get(a)
    vis = dict(_DEFAULT)
    for a in reversed(chain):
        vis.update(d.areas[a].get("visibility") or {})
    return vis


def _allowed(spec, player, owner):
    if player is None or spec == "all":
        return True
    if spec == "owner":
        return player == owner
    if spec == "others":  # 持ち主以外（花火の手札：自分の札だけ見えない）
        return player != owner
    if isinstance(spec, list):
        return player in spec
    return False


def _who(spec, owner):
    return {"all": "全員に見える", "owner": f"持ち主（{owner}）だけに見える", "none": "誰にも見えない",
            "others": f"持ち主（{owner}）以外に見える"}.get(
        spec, f"{spec} だけに見える" if isinstance(spec, list) else str(spec))


def _meaning_of_states(d, obj, st):
    defs = d.states(d.kind_of(obj))
    out = {}
    for f, v in st.items():
        vals = defs.get(f)
        m = vals.get(v) if isinstance(vals, dict) else None
        out[f] = {"value": v, "meaning": m.get("text") if isinstance(m, dict) else m}
        if isinstance(m, dict) and m.get("show"):
            out[f]["show"] = m["show"]
    return out


def _item(d, state, obj, player, vis, owner, meaning):
    if isinstance(obj, dict):
        (part, n), = obj.items()
        it = {"id": part, "kind": d.parts[part].get("kind"), "count": n}  # 種類の名前を添える（意味は凡例）
        if d.image(part):
            it["image"] = d.image(part)
        if meaning and d.parts[part].get("text"):
            it["meaning"] = d.parts[part]["text"]
        return it
    st = state["states"].get(obj, {})
    disp = d.display(d.kind_of(obj), st)
    face_down = disp["face"] == "down"
    knows = player in state["known"].get(obj, [])
    # 卓上（face: all）では向きが効く。手札のように見せる相手を絞ったエリアでは、その相手は向きに関係なく見られる
    face_ok = player is None or knows or (_allowed(vis["face"], player, owner) and (not face_down or vis["face"] != "all"))
    if not face_ok:
        reason = "裏向き" if face_down else _who(vis["face"], owner)
        it = {"hidden": f"表面は見えない（{reason}）", "display": disp}
        chain = d.kind_chain(d.kind_of(obj))
        if chain and _allowed(vis["back"], player, owner):
            it["back"] = chain[-1]  # 裏から分かるのは最も元の種類まで
            if d.image(obj, st, "back_image"):
                it["back_image"] = d.image(obj, st, "back_image")  # 裏の絵（裏から見えるもの）
            if d.parts[obj].get("owner"):
                it["owner"] = d.parts[obj]["owner"]  # 誰の札かは裏からも分かる
        hint = ((state.get("hints") or {}).get(obj) or {}).get(player)
        if hint:  # 一部だけ知っている（花火のヒント）
            attrs = d.parts[obj].get("attributes") or {}
            it["known"] = {f: attrs[f] if f in attrs else st.get(f) for f in hint}
    else:
        part = d.parts[obj]
        it = {"id": obj, "kind": part.get("kind"), "display": disp}
        title = ((part.get("attributes") or {}).get("title") or (part.get("attributes") or {}).get("name")
                 or (d.kinds.get(part.get("kind")) or {}).get("name"))  # 種類の名前（駒の字など）
        if title:
            it["title"] = title
        attrs = {k: v for k, v in (part.get("attributes") or {}).items() if k not in ("title", "name")}
        if attrs:
            it["attributes"] = attrs  # 表から読める値（花火の札の色と数など）
        derived = {}
        for k in reversed(d.kind_chain(part.get("kind"))):  # 種類の derived：部品ごとに局面から計算する値（残り HP など）
            derived.update(d.kinds[k].get("derived") or {})
        if derived:
            from .expr import evaluate
            it["derived"] = {}
            for n, e in derived.items():
                try:
                    it["derived"][n] = evaluate(e, d, state, {"self": obj})
                except Exception:  # noqa: BLE001（式の誤りで局面を見られなくしない）
                    it["derived"][n] = "（計算できない）"
        shape = next((d.kinds[k]["shape"] for k in d.kind_chain(part.get("kind")) if d.kinds[k].get("shape")), None)
        if shape:
            it["shape"] = shape  # 形（round：丸いトークン）。表示方法の 1 つ
        img = d.image(obj, st, "back_image" if face_down and vis["face"] == "all" else "image")
        if img:
            it["image"] = img
        if vis["face"] != "all":  # 手札のように見せる相手を絞ったエリアでは向きは意味を持たない
            st = {k: v for k, v in st.items() if k not in d.face_fields(part.get("kind"))}
            it["display"] = {**disp, "face": "held"}  # 手に持っている（表裏は意味を持たない）
            it["visible_to"] = _who(vis["face"], owner)
        if st:
            it["state"] = _meaning_of_states(d, obj, st) if meaning else st
        if part.get("owner"):
            it["owner"] = part["owner"]
        if meaning:
            if part.get("text"):  # 種類の意味は凡例に 1 回だけ。部品ごとの文があるときだけ添える
                it["meaning"] = part["text"]
            uses = d.uses(part.get("kind"))
            if uses:
                it["uses"] = [{k: u.get(k) for k in ("id", "when", "text", "refs") if u.get(k)} for u in uses]
            it["rules"] = rules_referencing(d, obj)
            js = rulings_for(d, it["rules"], obj)
            if js:
                it["rulings"] = js  # ルールの穴を埋める裁定（未決も）
        if knows and player is not None and face_down:
            it["note"] = "裏向きだが、あなたは中身を知っている"
    att = state["attached"].get(obj)
    if att and face_ok:
        it["attached"] = att
    on = state["places"].get(obj)
    if on:
        it["stacked"] = [_item(d, state, o, player, vis, owner, meaning) for o in on]
    return it


def view(d: Definition, state: dict, player: str | None = None, meaning: bool = False, seats: dict | None = None) -> dict:
    """player=None はキーパー（すべて見える）。meaning=True で意味の文と関係するルールを添える。"""
    out = {"for": player or "keeper", "game": d.data["game"]["id"], "version": d.data["game"].get("version")}
    prog = {}
    for k, v in state["progress"].items():
        pd = (d.data.get("progress") or {}).get(k) or {}
        e = {"value": v}
        if meaning:
            e["meaning"] = pd.get("text")
            rules = list(pd.get("refs") or []) + ([v] if isinstance(v, str) and v in d.rules else [])
            if rules:
                e["rules"] = {r: d.rules[r]["text"] for r in rules if r in d.rules}
        prog[k] = e if meaning else v
    out["progress"] = prog
    if meaning:  # 凡例：種類と組の意味は 1 回だけ示す
        out["legend"] = {
            "kinds": {k: {"text": kd.get("text"), **({"states": d.states(k)} if d.states(k) else {})}
                      for k, kd in d.kinds.items()},
            **({"groups": {g: gd.get("text") for g, gd in (d.data.get("groups") or {}).items()}} if d.data.get("groups") else {}),
        }
    areas = {}
    for aid, a in d.areas.items():
        vis, owner = visibility(d, aid), a.get("owner")
        items = state["places"].get(aid, [])
        if not _allowed(vis["exists"], player, owner):
            continue
        e = {}
        if meaning and a.get("text"):
            e["meaning"] = a["text"]
        if meaning and a.get("kind"):
            e["kind"] = a["kind"]
        if d.parent.get(aid):
            e["parent"] = d.parent[aid]
        kids = [c["id"] for c in a.get("areas") or []]
        if kids:
            e["children"] = kids
        # 区別しない部品も枚数に数える（中身＝どの種類が何枚かは表面と同じく隠す）
        n = sum(1 if isinstance(i, str) else (next(iter(i.values())) if isinstance(next(iter(i.values())), int) else 0) for i in items)
        if not _allowed(vis["count"], player, owner):
            e["shown"] = {"exists": bool(items)}
            e["hidden"] = {"count": _who(vis["count"], owner)}
        elif not items:
            e["shown"] = []
        elif not _allowed(vis["face"], player, owner) and not any(
                isinstance(i, str) and (player in state["known"].get(i, []) or player in ((state.get("hints") or {}).get(i) or {}))
                for i in items):
            e["shown"] = {"count": n}
            e["hidden"] = {"face": _who(vis["face"], owner)}
            if not _allowed(vis["order"], player, owner):
                e["hidden"]["order"] = _who(vis["order"], owner)
        else:
            shown = [_item(d, state, i, player, vis, owner, meaning) for i in items]
            if not _allowed(vis["order"], player, owner):
                e["hidden"] = {"order": _who(vis["order"], owner)}
                shown = sorted(shown, key=lambda x: str(x.get("id", x)))
            e["shown"] = shown
        if meaning:
            e["rules"] = rules_referencing(d, aid)
        areas[aid] = e
    out["areas"] = areas
    if player and seats and str(seats.get(player, "")).startswith("automa"):
        out["automa_rules"] = {r["id"]: r["text"] for r in d.data.get("rules") or []
                               if r.get("type") == "automa" and r.get("seat") == player}
    if state.get("flow"):  # 進行の構造（SPC-051）
        from .flow import end_signals, summary
        out["flow"] = summary(d, state["flow"], player)
        if player is None and state["result"] is None:  # 終了の検出はキーパーにだけ（隠れた値を使うことがある）
            for key, name in (("end_when", "end_signals"), ("signals", "signals")):
                sig = end_signals(d, state, key)
                if sig:
                    out["flow"][name] = sig
        elif state["result"] is None:
            sig = end_signals(d, state, "signals", public_only=True)
            if sig:
                out["flow"]["signals"] = sig
    if state.get("flow") and state["result"] is None:
        from .flow import end_result, standings
        if player is None:  # キーパー：今満たしている終わりの条件と、その結果（時機を問わない）
            r = end_result(d, state, ("now", "turn_end", "round_end"))
            if r:
                out["flow"]["end_preview"] = r
        rows = standings(d, state, player)
        if rows:
            out["standings"] = rows  # 得点の順位（見えない得点があれば出さない）
    if d.data.get("metrics"):  # 指標（局面から数えて出す値。SPC-050）
        from .metrics import compute
        out["metrics"] = compute(d, state, player)
    if state.get("stack"):  # スタック（解決待ちの行為。公開）と、まだ見送っていない人
        names = {a["id"]: a.get("name", a["id"]) for a in d.data.get("actions") or []}
        from .session import _stack_next
        nxt = _stack_next(d, state)["n"]
        out["stack"] = [{**e, "name": names.get(e["action"], e["action"]), **({"next": True} if e["n"] == nxt else {})}
                        for e in state["stack"]]  # next：次に解決するもの（既定は最後＝一番上）
        out["stack_waiting"] = sorted(set(d.players) - {_stack_next(d, state)["by"]} - set(state.get("stack_passes") or []))
    if state.get("stack_done"):
        out["stack_done"] = state["stack_done"][-5:]
    talk = [t for t in state.get("talk") or []]
    if player in d.players:  # 自分が答える受付中の提案（番号）
        from .session import offer_eligible
        mine = [t.get("n", i) for i, t in enumerate(talk) if t.get("status") == "open" and t["by"] != player and player in offer_eligible(d, t)]
        if mine:
            out["offers_for_me"] = mine
    if talk:  # 発言（RUL-009）。内緒話は、聞いていない人には話したことだけ
        hears = lambda t: player is None or "to" not in t or player == t.get("by") or player in t["to"]
        out["talk"] = [t if hears(t) else {**{k: v for k, v in t.items() if k not in ("text", "offer")}, "text": "（内緒話）"}
                       for t in talk if hears(t) or not t.get("hidden")]  # whisper: hidden の段階の内緒話は、あったことも見せない
    if state["result"]:
        out["result"] = state["result"]
    return out
