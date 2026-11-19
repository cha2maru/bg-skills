"""進行の構造：段階・巡・手番・フェーズと、アクションの区分（メイン・フリー・手番外の対応）と回数（SPC-051）。

ルールの合法性は判定しない。定義の進行の構造から外れた行為には警告を返すだけ。
"""
from __future__ import annotations

from .definition import Definition


def _flow(d: Definition) -> dict | None:
    return d.data.get("flow")


def _order(d: Definition, stage: dict) -> list:
    order = stage.get("order", "seats")
    if isinstance(order, list):  # 席の一部を決まった順に（例：主人公 3 人でリーダーが回る）
        return list(order)
    if order == "reverse":
        return list(reversed(d.players))
    if order == "snake":  # 往復（初期配置など）
        return d.players + list(reversed(d.players))
    return list(d.players)


def _limit(d: Definition, stage: dict):
    """段階の手番の数。None は終わりなし（終わりはルールの自然文で決まる）。"""
    if not stage.get("turn"):
        return 0
    if stage.get("turns"):  # 手番の数を直接（例：脚本の日数）
        return stage["turns"]
    seq = _order(d, stage)
    if stage.get("order") == "snake":
        return len(seq) * stage.get("rounds", 1)
    return len(seq) * stage["rounds"] if stage.get("rounds") else None


def _phases(d: Definition, stage: dict) -> list:
    t = (_flow(d).get("turns") or {}).get(stage.get("turn")) or {}
    return t.get("phases") or []


def _first_phase(d: Definition, stage: dict):
    """最初のフェーズ（行うことのない pass のフェーズは飛ばす）。"""
    ph = _phases(d, stage)
    return next((p["id"] for p in ph if not p.get("pass")), ph[0]["id"] if ph else None)


def _turn(d: Definition, stage: dict) -> dict:
    return (_flow(d).get("turns") or {}).get(stage.get("turn")) or {}


def _enter_stage(d: Definition, i: int, turn_no: int) -> dict:
    stages = _flow(d)["stages"]
    if i >= len(stages):
        return {"stage": None, "stage_index": i, "turn_in_stage": 0, "turn_no": turn_no, "active": None, "phase": None,
                "counts": {"turn": {}, "phase": {}}}
    st = stages[i]
    has_turns = bool(st.get("turn"))
    ph = _phases(d, st)
    return {"stage": st["id"], "stage_index": i, "turn_in_stage": 0, "turn_no": turn_no + (1 if has_turns else 0),
            "active": _order(d, st)[0] if has_turns else None, "phase": _first_phase(d, st) if ph else None,
            "counts": {"turn": {}, "phase": {}}, "cycle": 1}


def initial(d: Definition, from_box: bool = False) -> dict | None:
    """最初の段階。from_box_only の段階（箱からの準備）は、箱から始めた対局のときだけ通る。"""
    if not _flow(d):
        return None
    i = 0
    while not from_box and i < len(_flow(d)["stages"]) and _flow(d)["stages"][i].get("from_box_only"):
        i += 1
    return _enter_stage(d, i, 0)


def _stage(d: Definition, f: dict) -> dict:
    stages = _flow(d)["stages"]
    return stages[f["stage_index"]] if f["stage_index"] < len(stages) else {}


def advance(d: Definition, f: dict, to: str = "phase", player: str | None = None) -> dict:
    """次のフェーズへ。最後のフェーズからは次の手番へ、段階の手番が尽きたら次の段階へ。
    player：その人の手番まで飛ぶ（麻雀の鳴き。以後の順はその人から続く）。"""
    if player and to == "turn" and _stage(d, f).get("turn"):
        seq = _order(d, _stage(d, f))
        g = advance(d, f, "turn")
        while g.get("stage") == f["stage"] and g.get("active") != player and g["turn_in_stage"] < f["turn_in_stage"] + len(seq):
            g = {**g, "turn_in_stage": g["turn_in_stage"] + 1, "active": seq[(g["turn_in_stage"] + 1) % len(seq)]}
        return g
    f = {**f, "counts": {"turn": dict(f["counts"]["turn"]), "phase": dict(f["counts"]["phase"])}}
    st = _stage(d, f)
    ph = [p["id"] for p in _phases(d, st)]
    if to == "phase" and f["phase"] in ph and ph.index(f["phase"]) < len(ph) - 1:
        nxt = {**f, "phase": ph[ph.index(f["phase"]) + 1], "counts": {**f["counts"], "phase": {}, "phase_by": {}}}
        if next((p for p in _phases(d, st) if p["id"] == nxt["phase"]), {}).get("pass"):  # 行うことのないフェーズは通り過ぎる
            return advance(d, nxt, "phase")
        return nxt
    if to in ("phase", "turn") and st.get("turn"):
        n = f["turn_in_stage"] + 1
        lim = _limit(d, st)
        if lim is None or n < lim:
            seq = _order(d, st)
            return {**f, "turn_in_stage": n, "turn_no": f["turn_no"] + 1, "active": seq[n % len(seq)],
                    "phase": _first_phase(d, st) if ph else None, "counts": {"turn": {}, "phase": {}, "phase_by": {}}}
    return _next_stage(d, f)


def _next_stage(d: Definition, f: dict) -> dict:
    """次の段階へ。周回（flow.cycle：from〜to の段階を times 回）の終わりなら from に戻る。"""
    cyc = _flow(d).get("cycle")
    stages = _flow(d)["stages"]
    n = f.get("cycle", 1)
    if cyc and f["stage"] == cyc["to"] and n < cyc["times"]:
        i = next(k for k, s in enumerate(stages) if s["id"] == cyc["from"])
        return {**_enter_stage(d, i, f["turn_no"]), "cycle": n + 1}
    return {**_enter_stage(d, f["stage_index"] + 1, f["turn_no"]), "cycle": n}


def on_start(d: Definition, before: dict, after: dict) -> list[list]:
    """進んだことで入った段階・手番の on_start（手順の並び）。局面から導く操作で、記録には残さない。"""
    out = []
    if not after or not after.get("stage"):
        return out
    st = _stage(d, after)
    if (before.get("stage"), before.get("cycle")) != (after.get("stage"), after.get("cycle")) and st.get("on_start"):
        out.append(st["on_start"])
    turn = _turn(d, st) if st.get("turn") else {}
    if turn.get("on_start") and (before.get("turn_no") != after.get("turn_no") or before.get("stage") != after.get("stage")):
        out.append(turn["on_start"])
    return out


def on_end(d: Definition, before: dict, after: dict) -> list[list]:
    """進んだことで終わる手番・段階の on_end（手順の並び）。手番の終わりの処理（手札の上限まで捨てる、など）。
    進む前の局面（手番の人はまだ前の人）で行う。"""
    out = []
    if not before or not before.get("stage"):
        return out
    st = _stage(d, before)
    turn = _turn(d, st) if st.get("turn") else {}
    if turn.get("on_end") and (after.get("turn_no") != before.get("turn_no") or after.get("stage") != before.get("stage")):
        out.append(turn["on_end"])
    if st.get("on_end") and (after.get("stage"), after.get("cycle")) != (before.get("stage"), before.get("cycle")):
        out.append(st["on_end"])
    return out


def standings(d: Definition, state: dict, viewer=None) -> list[dict] | None:
    """終わりの得点計算（flow.scoring：by＝得点の指標、tiebreak＝同点のときに比べる指標の並び、low＝少ないほうが上）。
    順位（同じなら同じ順位）。viewer から見えない値があれば None（隠れた得点から順位を漏らさない）。"""
    sc = _flow(d).get("scoring")
    if not sc:
        return None
    from .metrics import compute
    m = compute(d, state, viewer)
    keys = [sc["by"]] + list(sc.get("tiebreak") or [])
    rows = []
    for p in d.players:
        vals = [((m.get(k) or {}).get("values") or {}).get(p) for k in keys]
        if any(v is None for v in vals):
            return None
        rows.append({"player": p, "score": vals[0], **({"tiebreak": vals[1:]} if len(vals) > 1 else {})})
    sign = 1 if sc.get("low") else -1
    rows.sort(key=lambda r: [sign * v for v in [r["score"]] + r.get("tiebreak", [])])
    for i, r in enumerate(rows):
        same = i and [rows[i - 1]["score"]] + rows[i - 1].get("tiebreak", []) == [r["score"]] + r.get("tiebreak", [])
        r["rank"] = rows[i - 1]["rank"] if same else i + 1
    return rows


def end_result(d: Definition, state: dict, timings=("now",)) -> dict | None:
    """終わりの条件（end_when）のうち、満たして、時機（timing：now・turn_end・round_end）も来た最初のもの。
    winners（式）・losers（式）・winners: scoring（得点の順位の 1 位）・draw: true から結果（席ごとの win・lose・draw）を作る。
    結果の書き方がなければ results は None（キーパーが決める）。並びが優先の順（同時に満たしたら上のもの）。"""
    from .expr import evaluate
    for c in _flow(d).get("end_when") or []:
        if (c.get("timing") or "now") not in timings:
            continue
        try:
            v = evaluate(c["expr"], d, state)
        except Exception:  # noqa: BLE001
            continue
        if not v:
            continue
        shown = "・".join(map(str, v)) if isinstance(v, (list, tuple, set)) else str(v)
        out = {"text": (c.get("text") or c["expr"]).replace("{value}", shown), "results": None, "rule": c.get("rule")}
        if c.get("draw"):
            out["results"] = {p: "draw" for p in d.players}
        elif c.get("winners") == "scoring":
            rows = standings(d, state) or []
            top = [r["player"] for r in rows if r["rank"] == 1]
            out["results"] = {p: ("win" if p in top else "lose") for p in d.players} if top else None
            out["standings"] = rows
        elif c.get("winners") or c.get("losers"):
            env = {"value": v}
            w = evaluate(c.get("winners") or c["losers"], d, state, env)
            w = [w] if isinstance(w, str) else list(w or [])
            win = set(w) if c.get("winners") else set(d.players) - set(w)
            out["results"] = {p: ("win" if p in win else "lose") for p in d.players}
        return out
    return None


def auto_advance(d: Definition, f: dict | None) -> bool:
    """今のフェーズが auto で、メインアクションを max 回行い終えたか。"""
    if not f or not f.get("phase"):
        return False
    p = next((p for p in _phases(d, _stage(d, f)) if p["id"] == f["phase"]), {})
    return bool(p.get("auto") and p.get("max") is not None and sum(f["counts"]["phase"].values()) >= p["max"])


def advance_warnings(d: Definition, f: dict | None) -> list[str]:
    if not f or not f.get("phase"):
        return []
    p = next((p for p in _phases(d, _stage(d, f)) if p["id"] == f["phase"]), {})
    if p.get("required") and not f["counts"]["phase"]:
        return [f"必須のフェーズ「{p.get('name', p['id'])}」で、まだ何もしていない"]
    return []


def whispers_hidden(d: Definition, state: dict) -> bool:
    """今の段階（かフェーズ）が whisper: hidden か（夜の内緒話は、聞いていない人にはあったことも見せない）。"""
    f = state.get("flow")
    if not f:
        return False
    st = _stage(d, f)
    ph = next((p for p in _phases(d, st) if p["id"] == f.get("phase")), {}) if st.get("turn") else {}
    return (ph.get("whisper") or st.get("whisper")) == "hidden"


def talk_warnings(d: Definition, state: dict, op: dict) -> list[str]:
    """発言の縛り（段階かフェーズの talk：true・false・式。式は speaker・to で書く）から外れていれば警告（RUL-009）。
    例：花火は話さない（ヒントだけ）、人狼の夜は人狼どうしだけ、ディプロマシーは命令を書く間は話さない。"""
    f = state.get("flow")
    if not f or op.get("by") in (None, "keeper"):
        return []
    st = _stage(d, f)
    ph = next((p for p in _phases(d, st) if p["id"] == f.get("phase")), {}) if st.get("turn") else {}
    rule, where = (ph, ph.get("name", ph.get("id"))) if "talk" in ph else (st, st.get("name", st.get("id")))
    talk = rule.get("talk", True)
    if isinstance(talk, str):
        from .expr import evaluate
        to = op.get("to")
        talk = evaluate(talk, d, state, {"speaker": op.get("by"), "to": d.players if to is None else ([to] if isinstance(to, str) else to)})
    return [] if talk else [rule.get("talk_text") or f"「{where}」では話せない"]


def classify(d: Definition, f: dict | None, action: str, actor: str) -> tuple[str, list[str]]:
    """アクションの区分（main・free・reaction・stage・other）と、進行の構造から外れていれば警告。"""
    if not f:
        return "other", []
    act = next((a for a in d.data.get("actions") or [] if a["id"] == action), {})
    if act.get("by") and actor not in act["by"]:  # アクションを行える人（例：拒否・死亡の処理は脚本家）
        return "other", [f"「{act.get('name', action)}」を行うのは {'・'.join(act['by'])}"]
    st = _stage(d, f)
    bound = action in flow_actions(d)  # 進行のどこか（段階・フェーズ・free・reactions）に書いたアクション
    if not f.get("stage"):  # 進行が終わった（巡の上限を超えた・最後の段階の後）
        return "other", ([f"進行が終わっている（段階がない）。「{act.get('name', action)}」は行えない"] if bound else [])
    if not st.get("turn"):
        ok = action in (st.get("actions") or [])
        return ("stage" if ok else "other"), ([] if ok or not st.get("actions") else
                                               [f"段階「{st.get('name', st.get('id'))}」のアクションではない"])
    t = _turn(d, st)
    phase = next((p for p in t.get("phases") or [] if p["id"] == f["phase"]), {})
    warns = []
    by = phase.get("by")  # フェーズの行う人（席の並び。省くと手番のプレイヤー）
    turn_actor = (lambda a: a in by) if by else (lambda a: a == f["active"])
    free = {x["action"]: x for x in t.get("free") or []}
    reactions = {x["action"]: x for x in t.get("reactions") or []}
    if action in reactions and action in (phase.get("main") or []) and not turn_actor(actor):
        cls = "reaction"  # メインにも手番外の対応にもあるアクションは、手番の人でなければ対応（相手の手番に打ち消しで応じる）
    elif action in (phase.get("main") or []):
        cls = "main"
        if not turn_actor(actor):
            warns.append(f"{actor} の手番ではない（行うのは {', '.join(by) if by else f['active']}）")
        done = sum(f["counts"]["phase"].values())
        if phase.get("max") is not None and done >= phase["max"]:
            warns.append(f"フェーズ「{phase.get('name', phase['id'])}」のメインアクションは {phase['max']} 回まで")
        if phase.get("each") is not None and f["counts"]["phase"].get(action, 0) >= phase["each"]:  # アクションごとの回数（開拓地 1 つと街道 1 本）
            warns.append(f"「{action}」はこのフェーズで {phase['each']} 回まで")
        mine = (f["counts"].get("phase_by") or {}).get(actor, 0)
        if phase.get("per_player") is not None and mine >= phase["per_player"]:  # 1 人あたりの回数
            warns.append(f"{actor} はこのフェーズで {phase['per_player']} 回まで")
        if phase.get("sequence") == "from_active" and by:  # 手番のプレイヤーから順に（例：リーダーから時計回り）
            seq = by[by.index(f["active"]):] + by[:by.index(f["active"])] if f["active"] in by else by
            nxt = next((p for p in seq if (f["counts"].get("phase_by") or {}).get(p, 0) < (phase.get("per_player") or 1)), None)
            if nxt and actor != nxt:
                warns.append(f"順番は {nxt}（{'→'.join(seq)}）")
    elif action in free:
        cls = "free"
        if actor != f["active"]:
            warns.append(f"{actor} の手番ではない（フリーアクションは手番のあいだ）")
        if free[action].get("max") is not None and f["counts"]["turn"].get(action, 0) >= free[action]["max"]:
            warns.append(f"「{action}」は手番に {free[action]['max']} 回まで")
        if free[action].get("phases") and f["phase"] not in free[action]["phases"]:  # 行えるフェーズを絞る（引いた後だけ、など）
            names = {p["id"]: p.get("name", p["id"]) for p in t.get("phases") or []}
            warns.append(f"「{action}」は {'・'.join(names.get(x, x) for x in free[action]['phases'])} のフェーズだけ")
    elif action in reactions:
        cls = "reaction"
    else:
        cls = "other"
        if any(action in (p.get("main") or []) for p in t.get("phases") or []):
            warns.append(f"今のフェーズ（{phase.get('name', f['phase'])}）のアクションではない")
        elif bound:  # ほかの段階・手番のアクション（準備だけの引き直しを、対戦中に行う）
            warns.append(f"段階「{st.get('name', st.get('id'))}」のアクションではない")
    return cls, warns


def flow_actions(d: Definition) -> set:
    """進行の構造に書かれたアクション。どこにも書かれていないアクション（キーパーの道具など）は進行で縛らない。"""
    fl = _flow(d) or {}
    out = set()
    for st in fl.get("stages") or []:
        out |= set(st.get("actions") or [])
    for t in (fl.get("turns") or {}).values():
        for p in t.get("phases") or []:
            out |= set(p.get("main") or [])
        out |= {x["action"] for key in ("free", "reactions") for x in t.get(key) or []}
    return out


def record(d: Definition, f: dict | None, action: str, actor: str) -> dict | None:
    """アクションを 1 回行ったことを数える（記録の再生で同じに数え直す）。"""
    if not f:
        return f
    cls, _ = classify(d, f, action, actor)
    c = {"turn": dict(f["counts"]["turn"]), "phase": dict(f["counts"]["phase"]), "phase_by": dict(f["counts"].get("phase_by") or {})}
    c["turn"][action] = c["turn"].get(action, 0) + 1
    if cls == "main":
        c["phase"][action] = c["phase"].get(action, 0) + 1
        c["phase_by"][actor] = c["phase_by"].get(actor, 0) + 1
    return {**f, "counts": c}


def available(d: Definition, f: dict | None, actor: str | None) -> dict:
    """今行えるアクションを区分ごとに（警告なしで行えるもの）。"""
    if not f:
        return {}
    out = {"main": [], "free": [], "reaction": [], "stage": []}
    for a in d.data.get("actions") or []:
        cls, warns = classify(d, f, a["id"], actor or f.get("active"))
        if cls in out and not warns:
            out[cls].append(a["id"])
    return out


def summary(d: Definition, f: dict | None, viewer: str | None) -> dict | None:
    if not f:
        return None
    st = _stage(d, f)
    ph = _phases(d, st)
    return {"stage": f["stage"], "stage_name": st.get("name"), **({"cycle": f.get("cycle", 1)} if _flow(d).get("cycle") else {}),
            "turn_no": f["turn_no"],
            "turn_in_stage": f["turn_in_stage"] + 1 if st.get("turn") else None, "active": f["active"],
            "phase": f["phase"], "phases": [{"id": p["id"], "name": p.get("name", p["id"])} for p in ph],
            "available": available(d, f, viewer)}


def end_signals(d: Definition, state: dict, key: str = "end_when", public_only: bool = False) -> list[str]:
    """終了の条件（end_when）か知らせ（signals）の式を満たしたものの文（G7・G8）。文の {value} に式の値（一覧なら・でつなぐ）。"""
    from .expr import evaluate
    out = []
    for c in (_flow(d) or {}).get(key) or []:
        if public_only and not c.get("public"):  # プレイヤーには、公開の情報だけで書いた知らせ（public: true）だけ
            continue
        try:
            v = evaluate(c["expr"], d, state)
        except Exception:  # noqa: BLE001（式の誤りで局面を見られなくしない）
            out.append(f"式を計算できない: {c['expr']}")
            continue
        if v:
            shown = "・".join(map(str, v)) if isinstance(v, (list, tuple, set)) else str(v)
            out.append((c.get("text") or c["expr"]).replace("{value}", shown))
    return out
