"""近傍の問い合わせと条件（SPC-052）。

条件は、エリアの中身とリンクのつながりだけで決まる構造の述語。アクションの引数が満たすべきことを宣言し、
満たさなければ警告（拒否しない）、候補の絞り込み、分かりやすい文に使う。ルールの自動実行ではない。

条件の書き方（すべて同じエリアについて）：
  {empty: true}                               何も置かれていない
  {has: {kind, owner, attr}}                  条件に合う部品が置かれている（kind はリストも可）
  {linked: {type, <条件>...}}                 リンク（種類 type）でつながるエリアのどれかが <条件> を満たす
  {not: 条件} / {any: [条件...]} / {all: [条件...]}
  text: 満たさないときに示す文
"""
from __future__ import annotations

import re

from .definition import Definition, fill


def neighbors(d: Definition, area: str, type_: str | None = None) -> list[tuple[str, str]]:
    """リンクでつながるエリアと、リンクの種類。"""
    out = []
    for l in d.data.get("links") or []:
        a, b = (l.get("between") or [None, None])[:2]
        if type_ and l.get("type") != type_:
            continue
        if a == area:
            out.append((b, l.get("type")))
        elif b == area:
            out.append((a, l.get("type")))
    return out


def _contents(state, area):
    """エリアに置かれた部品（部品の上の部品も含む）の ID。"""
    out, stack = [], list(state["places"].get(area, []))
    while stack:
        it = stack.pop()
        pid = it if isinstance(it, str) else next(iter(it))
        out.append(pid)
        if isinstance(it, str):
            stack += state["places"].get(it, [])
    return out


def _fixture(d, pid):
    """場所の性質の部品（港など。種類の fixture: true）。空き・上限の判定に数えない。"""
    return any(d.kinds[k].get("fixture") for k in d.kind_chain(d.parts[pid].get("kind")))


def _part_ok(d, pid, cond):
    p = d.parts[pid]
    kinds = cond.get("kind")
    if kinds:
        kinds = kinds if isinstance(kinds, (list, tuple)) else [kinds]
        if not set(kinds) & set(d.kind_chain(p.get("kind"))):
            return False
    if cond.get("owner") and p.get("owner") != cond["owner"]:
        return False
    return all((p.get("attributes") or {}).get(k) == v for k, v in (cond.get("attr") or {}).items())


def holds(d: Definition, state: dict, area: str, cond: dict, env: dict | None = None) -> bool:
    """エリア（またはプレイヤー・部品）が条件を満たすか。expr は式（value に対象、ほかに actor・引数）。"""
    if not cond:
        return True
    if "expr" in cond:  # 式の条件（G4：ほかの引数の位置、プレイヤー、行う人への条件）
        from .expr import evaluate
        if not evaluate(cond["expr"], d, state, {**(env or {}), "value": area}):
            return False
        if set(cond) <= {"expr", "text"}:
            return True
    if "all" in cond and not all(holds(d, state, area, c, env) for c in cond["all"]):
        return False
    if "any" in cond and not any(holds(d, state, area, c, env) for c in cond["any"]):
        return False
    if "not" in cond and holds(d, state, area, cond["not"], env):
        return False
    if "empty" in cond and (not [p for p in _contents(state, area) if not _fixture(d, p)]) != bool(cond["empty"]):
        return False
    if "has" in cond and not any(_part_ok(d, p, cond["has"]) for p in _contents(state, area)):
        return False
    if "linked" in cond:
        sub = {k: v for k, v in cond["linked"].items() if k != "type"}
        if not any(holds(d, state, other, sub, env) for other, _ in neighbors(d, area, cond["linked"].get("type"))):
            return False
    return True


def check_param(d: Definition, state: dict, param: dict, value: str, env: dict) -> list[str]:
    """引数の値が、引数の条件（require・owner）を満たさないときの文。"""
    msgs = []
    if param.get("kind") and value in d.parts and param["kind"] not in d.kind_chain(d.parts[value].get("kind")):
        msgs.append(f"{param['name']}={value} は {param['kind']} ではない")
    if param.get("from") and value in d.parts:  # 選ぶ元の置き場（の下）にない
        root = fill(param["from"], env)
        at = next((a for a in d.areas if _under(d, a, root) and value in _contents(state, a)), None)
        if at is None:
            msgs.append(f"{param['name']}={value} は {root} にない")
    if param.get("stack") and str(value) not in [str(e["n"]) for e in state.get("stack") or []]:
        msgs.append(f"{param['name']}={value} はスタックの解決待ちにない")
    if param.get("choices") and value not in param["choices"]:
        msgs.append(f"{param['name']}={value} は選択肢（{'・'.join(map(str, param['choices']))}）にない")
    if param.get("owner") and value in d.parts and d.parts[value].get("owner") != fill(param["owner"], env):
        msgs.append(f"{param['name']}={value} は {fill(param['owner'], env)} の部品ではない")
    for c in param.get("require") or []:
        c = fill(c, env)
        if (value in d.areas or "expr" in c) and not holds(d, state, value, c, env):
            msgs.append(f"{param['name']}={value}：{c.get('text') or '条件を満たさない'}")
    return msgs


def check_action(d: Definition, state: dict, action: dict, env: dict) -> list[str]:
    """アクション全体の条件（行う人への条件など。require の expr）。"""
    from .expr import ExprError, evaluate
    out = []
    for c in action.get("require") or []:
        try:
            ok = evaluate(c["expr"], d, state, {**env, "value": env.get("actor")})
        except ExprError:
            if any(re.search(rf"\b{re.escape(p['name'])}\b", c["expr"]) for p in action.get("params") or []):
                continue  # 引数（選ぶもの）を読む条件は、選ぶまで判断できない（行えない理由に出さない）
            raise
        if not ok:
            out.append(c.get("text") or "アクションの条件を満たさない")
    return out


def candidates(d: Definition, state: dict, action_id: str, actor: str, param_name: str, args: dict | None = None) -> list[dict]:
    """引数の候補と、条件を満たすか（キーパーの局面で数える。見え方は呼ぶ側で守る）。args はすでに選んだ引数。"""
    a = next((x for x in d.data.get("actions") or [] if x["id"] == action_id), None)
    p = next((x for x in (a or {}).get("params") or [] if x["name"] == param_name), None)
    if p is None:
        raise ValueError(f"アクション {action_id} に引数 {param_name} はない")
    env = {"actor": actor, "player": actor, **(args or {})}
    if p.get("free"):  # 自由に書く値（命令の文など）。候補はない
        return []
    if p.get("players"):
        ids = list(d.players)
    elif p.get("stack"):  # スタックの解決待ち（打ち消す対象など）。値は番号
        ids = [str(e["n"]) for e in state.get("stack") or []]
    elif p.get("choices"):  # 選択肢から選ぶ（資源の種類など）
        ids = list(p["choices"])
    elif p.get("in"):
        root = fill(p["in"], env)
        ids = [c["id"] for c in d.areas[root].get("areas") or []
               if not p.get("kind") or p["kind"] in d.kind_chain(c.get("kind"))]
    else:
        root = fill(p.get("from", ""), env)
        areas = [x for x in d.areas if not root or _under(d, x, root)]
        ids = []
        for ar in areas:
            for pid in _contents(state, ar):
                if pid not in ids and (not p.get("kind") or p["kind"] in d.kind_chain(d.parts[pid].get("kind"))):
                    ids.append(pid)
    return [{"id": i, "problems": check_param(d, state, p, i, env)} for i in ids]


def _under(d, area, root):
    while area:
        if area == root:
            return True
        area = d.parent.get(area)
    return False
