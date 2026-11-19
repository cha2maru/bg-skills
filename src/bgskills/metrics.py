"""指標：局面から数えて出す値（使った騎士の数、都市の数、勝利点など。SPC-050）。局面には保存しない。"""
from __future__ import annotations

from .definition import Definition, fill
from .query import _part_ok, _under
from .view import _allowed, visibility


def _area_of(d: Definition, state: dict, container: str) -> str | None:
    """置き場（エリアか部品）から、それを含むエリアをたどる（部品の上の部品は、下の部品のエリア）。"""
    seen = set()
    while container and container not in d.areas and container not in seen:
        seen.add(container)
        container = next((c for c, items in state["places"].items() if container in items), None)
    return container


def _face_visible(d, state, pid, area, viewer):
    if viewer is None:
        return True
    vis, owner = visibility(d, area), d.areas[area].get("owner")
    if viewer in state["known"].get(pid, []):
        return True
    down = d.display(d.kind_of(pid), state["states"].get(pid, {}))["face"] == "down" if pid in state["states"] else False
    return _allowed(vis["face"], viewer, owner) and (not down or vis["face"] != "all")


def count(d: Definition, state: dict, cond: dict, viewer=None, needs="face"):
    """条件に合う部品の数と、viewer から見えない部品を数えたか（隠れているか）。"""
    total, hidden = 0, False
    for container, items in state["places"].items():
        area = _area_of(d, state, container)
        if area is None or (cond.get("in") and not _under(d, area, cond["in"])):
            continue
        for it in items:
            pid = it if isinstance(it, str) else next(iter(it))
            n = 1 if isinstance(it, str) else it[pid]
            if not isinstance(n, int):
                continue
            p = d.parts[pid]
            if not _part_ok(d, pid, cond):
                continue
            if any(state["states"].get(pid, {}).get(f) != v for f, v in (cond.get("state") or {}).items()):
                continue
            if cond.get("sum_attr"):  # 部品の数ではなく属性の値を足す（例：火の薪の数値の合計）
                n *= int((p.get("attributes") or {}).get(cond["sum_attr"]) or 0)
            total += n
            if needs == "face" and not _face_visible(d, state, pid, area, viewer):
                hidden = True
    if needs == "face" and viewer is not None and cond.get("in") and cond["in"] in d.areas:
        vis = visibility(d, cond["in"])  # 見えないエリアを数える指標は、中身が空でも示さない（空であることも漏れる）
        if not _allowed(vis["face"], viewer, d.areas[cond["in"]].get("owner")):
            hidden = True
    if needs == "count" and viewer is not None and cond.get("in"):
        vis = visibility(d, cond["in"])
        hidden = not _allowed(vis["count"], viewer, d.areas[cond["in"]].get("owner"))
    return total, hidden


def compute(d: Definition, state: dict, viewer=None) -> dict:
    """すべての指標。per: player の指標はプレイヤーごと。viewer から見えない値は示さない（None のときはキーパー）。"""
    defs = {m["id"]: m for m in d.data.get("metrics") or []}
    memo = {}

    def value(mid, player):
        key = (mid, player)
        if key not in memo:
            memo[key] = (None, False)  # 指標が自分を（回り回って）引いても止まる
            m = defs[mid]
            env = {"player": player} if player else {}
            if "expr" in m:  # 式の指標（最長の路など。G6）。見え方は visible で決める
                from .expr import ExprError, evaluate
                try:
                    # ほかの指標は、この計算の中の値を使う（compute を呼び直すと、自分を含めて計算し直し続ける）
                    local = {"metric": lambda i, p=None: value(i, p)[0], **env}
                    v, hid = evaluate(m["expr"], d, state, local), False
                except ExprError as e:  # 1 つの式の誤りで局面を見られなくしない（bg check でも見つかる）
                    v, hid = f"（{e}）", False
            elif "count" in m:
                v, hid = count(d, state, fill(m["count"], env), viewer, m.get("needs", "face"))
            else:
                v, hid = 0, False
                for t in m.get("sum") or []:
                    if "metric" in t:
                        sv, sh = value(t["metric"], player)
                    else:
                        sv, sh = count(d, state, fill(t["count"], env), viewer, t.get("needs", "face"))
                    v, hid = v + t.get("weight", 1) * sv, hid or sh
            if m.get("visible") == "owner" and viewer is not None and viewer != player:
                hid = True
            if m.get("visible") == "keeper" and viewer is not None:  # キーパーにだけ（脚本の存在をほのめかす値など）
                hid = True
            memo[key] = (v, hid)
        return memo[key]

    out = {}
    for mid, m in defs.items():
        e = {"name": m.get("name", mid)}
        if m.get("per") == "player":
            vals = {p: value(mid, p) for p in d.players}
            e["values"] = {p: v for p, (v, hid) in vals.items() if not hid}
            if any(hid for _, hid in vals.values()):
                e["hidden_for"] = [p for p, (_, hid) in vals.items() if hid]
        else:
            v, hid = value(mid, None)
            if hid:
                e["hidden"] = True
            else:
                e["value"] = v
        out[mid] = e
    return out
