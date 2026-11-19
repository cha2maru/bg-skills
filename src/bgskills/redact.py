"""プレイヤーに出すものを伏せる、ただ 1 つの場所（RUL-016 の 5）。

局面の見え方は view.view（エリア・部品・発言・知らせ）、操作の記録はこのモジュール。コマンド（cli）も画面（server）も
プレイヤーに出すときは必ずここか view を通す。出口を足したら tests/test_leaks.py にも足す。
"""
from __future__ import annotations


def visible_log(s, player) -> list[dict]:
    """記録を player の立場で。伏せるかは、その操作の直後の局面の見え方で決める（後で公開された札から昔の手札を明かさない）。"""
    if not player or player == "keeper":
        return s.log()
    from .session import apply_op, initial_state
    st, out = initial_state(s.defn, s.meta.get("start") == "box"), []
    for i, o in enumerate(s.log(), 1):
        st = apply_op(s.defn, st, o, s.meta["seed"], i)
        out += visible_ops(s, st, [o], player)
    return out


def visible_ops(s, state, ops, player):
    """操作の記録を、player から今見えない部品の ID を伏せて返す。出目などの結果を添える。"""
    from .metrics import _area_of, _face_visible
    out = []
    secret = {a["id"] for a in s.defn.data.get("actions") or [] if a.get("secret")}
    for o in ops:
        o = dict(o)
        if player and o.get("by") != player and o.get("action") in secret:  # 非公開の行為（人狼の夜の行動）は、あったことも件数も見せない
            continue
        if player and o.get("op") == "say" and o.get("to") is not None and o.get("by") != player and player not in (
                [o["to"]] if isinstance(o["to"], str) else o["to"]):
            if o.get("hidden"):  # 夜の内緒話など：あったことも見せない
                continue
            o["text"] = "（内緒話）"
            o.pop("offer", None)
        obj = o.get("obj")
        if player and isinstance(obj, str) and obj in s.defn.parts and s.defn.distinct(obj):
            where = next((c for c, items in state["places"].items() if obj in items), None)
            area = _area_of(s.defn, state, where) if where else None
            if area and not _face_visible(s.defn, state, obj, area, player):
                o["obj"] = "（見えない部品）"
                if "value" in o and o.get("op") in ("set", "flip", "rotate"):  # 伏せた紙に書いた値（封をした投票）も伏せる
                    o["value"] = "（見えない）"
        elif player and isinstance(obj, str) and obj in s.defn.parts and o.get("by") != player:
            # 区別しない部品（資源など）：移る元か先の表面が見えなければ種類を伏せる（取った札は当事者だけが知る）
            from .view import _allowed, visibility
            ends = [_area_of(s.defn, state, x) for x in (o.get("from"), o.get("to")) if x]
            if ends and not any(a in s.defn.areas and _allowed(visibility(s.defn, a)["face"], player, s.defn.areas[a].get("owner"))
                                for a in ends):
                o["obj"] = "（見えない部品）"
        if o.get("op") == "roll" and obj in state["states"]:
            o["result"] = state["states"][obj]
        out.append(o)
    return out
