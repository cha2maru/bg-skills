"""式と問い合わせ（G1 選択式・G2 値と式。SPC-053）。

局面の構造だけを読む小さな式の言語。Python の式の一部（比較・算術・条件式・内包表記）と、決まった関数だけを使える。
アクションの let・each・if、条件の expr、指標の expr、進行の終了の検出（end_when）で使う。ルールの合法性を判定するものではなく、
定義に書いた手順・条件・値を計算するだけ。

関数：
  state(obj, field) attr(obj, name) kind(obj) owner(obj)      部品の状態・属性・種類（最も具体的なもの）・持ち主
  where(obj)                                                  部品のあるエリア（部品の上なら下の部品のエリア）
  children(area, kind=None)                                   子のエリア（種類で絞る）
  linked(area, type=None)                                     リンクでつながるエリア
  parts_in(area_or_areas, kind=None, owner=None, attr=None)   置かれた部品（区別しない部品はその ID を 1 回）
  count_in(area_or_areas, kind=None, owner=None, attr=None)   置かれた部品の数（区別しない部品は個数）
  metric(id, player=None) players() active() turn() entered(obj)
  seat(player, k)                                             席の順で k 人先のプレイヤー（-1 は 1 つ前。麻雀の上家）
  pos(area) step(area, dx, dy) ray(area, dx, dy)            位置（pos）による隣と、向きの並び（チェスの走り・オセロの挟み）
  on1(area) first(xs)                                         エリアに直接置かれた最初の部品、並びの最初
  longest_path(nodes, via, blocked=())                        nodes の間を、via のリンクで共有するエリア（blocked を除く）を通る最長の路の長さ
  join(xs, sep="・")                                           並びを文字列でつなぐ（発言の文を組み立てる）
  len min max sum any all sorted abs
"""
from __future__ import annotations

import ast

from .definition import Definition

_ALLOWED = (ast.Expression, ast.BoolOp, ast.And, ast.Or, ast.BinOp, ast.Add, ast.Sub, ast.Mult, ast.FloorDiv, ast.Mod,
            ast.UnaryOp, ast.Not, ast.USub, ast.Compare, ast.Eq, ast.NotEq, ast.Lt, ast.LtE, ast.Gt, ast.GtE, ast.In, ast.NotIn,
            ast.Call, ast.Name, ast.Load, ast.Constant, ast.List, ast.Tuple, ast.Dict, ast.IfExp, ast.keyword,
            ast.ListComp, ast.GeneratorExp, ast.comprehension, ast.Store, ast.Subscript, ast.Slice)


class ExprError(ValueError):
    pass


def _check(tree):
    for node in ast.walk(tree):
        if not isinstance(node, _ALLOWED):
            raise ExprError(f"式に使えない書き方: {type(node).__name__}")
        if isinstance(node, ast.Call) and not isinstance(node.func, ast.Name):
            raise ExprError("関数は名前で呼ぶ")


def context(d: Definition, state: dict) -> dict:
    """式から呼べる関数。"""
    from .metrics import _area_of, compute
    from .query import _contents, _part_ok, neighbors

    def where(obj):
        c = next((c for c, items in state["places"].items()
                  if obj in items or any(isinstance(i, dict) and obj in i for i in items)), None)
        return _area_of(d, state, c) if c else None

    def _kinds(k):
        return None if k is None else (k if isinstance(k, (list, tuple)) else [k])

    def _match(pid, kind, owner, attr):
        return _part_ok(d, pid, {"kind": kind, "owner": owner, "attr": attr})

    def _areas(a):  # 子のエリアも含める（盤 → 病院・神社…）。直接置かれた物だけなら on・count_on
        out, stack = [], [a] if isinstance(a, str) else list(a or [])
        while stack:
            x = stack.pop(0)
            out.append(x)
            stack += [c["id"] for c in (d.areas.get(x) or {}).get("areas") or []]
        return out

    def parts_in(areas, kind=None, owner=None, attr=None):
        out = []
        for a in _areas(areas):
            out += [p for p in _contents(state, a) if _match(p, kind, owner, attr)]
        return out

    def count_in(areas, kind=None, owner=None, attr=None):
        n = 0
        for a in _areas(areas):
            stack = list(state["places"].get(a, []))
            while stack:
                it = stack.pop()
                pid = it if isinstance(it, str) else next(iter(it))
                k = 1 if isinstance(it, str) else it[pid]
                if isinstance(k, int) and _match(pid, kind, owner, attr):
                    n += k
                if isinstance(it, str):
                    stack += state["places"].get(it, [])
        return n

    def count_on(target, kind=None, owner=None, attr=None):
        """target（エリアか部品）に直接置かれた部品の数（その上の部品は数えない）。"""
        n = 0
        for it in state["places"].get(target, []):
            pid = it if isinstance(it, str) else next(iter(it))
            k = 1 if isinstance(it, str) else it[pid]
            if isinstance(k, int) and _match(pid, kind, owner, attr):
                n += k
        return n

    def children(area, kind=None):
        ks = _kinds(kind)
        return [c["id"] for c in d.areas[area].get("areas") or [] if not ks or set(ks) & set(d.kind_chain(c.get("kind")))]

    def metric(mid, player=None):
        m = compute(d, state, None).get(mid) or {}
        return (m.get("values") or {}).get(player) if player else m.get("value")

    def longest_path(nodes, via, blocked=()):
        nodes, blocked = list(nodes), set(blocked)
        hubs = {n: {h for h, _ in neighbors(d, n, via)} for n in nodes}
        best = 0

        def dfs(n, came_by, seen):  # 入ってきた端とは別の端から先へ（分かれ道で折り返さない）
            nonlocal best
            best = max(best, len(seen))
            for h in hubs[n] - {came_by} - blocked:
                for m in nodes:
                    if m not in seen and h in hubs[m]:
                        dfs(m, h, seen | {m})

        for n in nodes:
            dfs(n, None, {n})
        return best

    def step(a, dx, dy):  # 同じ親の中で、位置（pos）が (dx, dy) ずれたエリア。盤の外なら None
        p = (d.areas.get(a) or {}).get("pos")
        if p is None:
            return None
        sib = (d.areas.get(d.parent.get(a)) or {}).get("areas") or []
        return next((c["id"] for c in sib if c.get("pos") == [p[0] + dx, p[1] + dy]), None)

    def ray(a, dx, dy):  # (dx, dy) の向きに、盤の端までのエリアの並び（a は含めない）
        out, x = [], step(a, dx, dy)
        while x:
            out.append(x)
            x = step(x, dx, dy)
        return out

    f = state.get("flow") or {}
    out = {
        "pos": lambda a: (d.areas.get(a) or {}).get("pos"), "step": step, "ray": ray,
        "first": lambda xs: next(iter(xs), None), "on1": lambda t: next((it for it in state["places"].get(t, []) if isinstance(it, str)), None),
        "state": lambda o, fld: (state["states"].get(o) or {}).get(fld),
        # 物がない（まだ配っていない役職など）ときは None を返し、条件は満たさないだけにする
        "attr": lambda o, name: ((d.parts.get(o) or {}).get("attributes") or {}).get(name),
        "kind": lambda o: (d.parts.get(o) or {}).get("kind"),
        "owner": lambda o: (d.parts.get(o) or d.areas.get(o) or {}).get("owner"),
        "where": where, "children": children,
        "linked": lambda a, type=None: [o for o, _ in neighbors(d, a, type)],
        "parts_in": parts_in, "count_in": count_in, "count_on": count_on, "metric": metric, "int": int, "str": str,
        "on": lambda t, kind=None, owner=None: [it for it in state["places"].get(t, []) if isinstance(it, str) and _match(it, kind, owner, None)],
        "count_of": lambda xs, x: list(xs).count(x), "set": set,
        "players": lambda: list(d.players), "seat": lambda p, k: d.players[(d.players.index(p) + k) % len(d.players)], "active": lambda: f.get("active"), "turn": lambda: f.get("turn_no", 0),
        "progress": lambda k: state["progress"].get(k), "cycle": lambda: f.get("cycle", 1), "stage": lambda: f.get("stage"),
        "turn_in_stage": lambda: f.get("turn_in_stage", 0) + 1, "phase": lambda: f.get("phase"),
        "entered": lambda o: (state.get("entered") or {}).get(o, 0), "longest_path": longest_path,
        "stack": lambda: list(state.get("stack") or []),  # 解決待ちの行為（{n, action, by, args}。最後が一番上）
        "repeats": lambda: (state.get("seen") or {}).get(_position_key(state), 0),  # 今の局面（手番の人を含む）が手番の替わり目に現れた回数
        "len": len, "min": min, "max": max, "sum": sum, "any": any, "all": all, "sorted": sorted, "abs": abs,
        "join": lambda xs, sep="・": sep.join(map(str, xs)), "range": range, "enumerate": enumerate, "zip": zip, "next": next, "iter": iter,
    }
    for name, fd in (d.data.get("functions") or {}).items():  # 名前つきの式（定義の functions）。どの式からも呼べる
        out[name] = _named(name, fd, d, state, out)
    return out


_DEPTH = [0]


def _position_key(state):
    from .session import position_key
    return position_key(state) if "places" in state and "states" in state else ""


def _named(name, fd, d, state, ctx):
    params = list(fd.get("params") or [])

    def call(*args):
        if len(args) != len(params):
            raise ExprError(f"{name} の引数は {len(params)} 個（{', '.join(params)}）")
        if _DEPTH[0] > 50:
            raise ExprError(f"{name} の呼び出しが深すぎる（自分を呼び続けている）")
        _DEPTH[0] += 1
        try:
            return evaluate(fd["expr"], d, state, dict(zip(params, args)), ctx)
        finally:
            _DEPTH[0] -= 1
    return call


def problems(src: str, known: set) -> str | None:
    """式を計算せずに確かめる（読めるか・使えない書き方・知らない関数）。定義の確認（bg check）で使う。"""
    try:
        tree = ast.parse(src, mode="eval")
        _check(tree)
    except SyntaxError as e:
        return f"式が読めない（{e.msg}）"
    except ExprError as e:
        return str(e)
    bad = sorted({n.func.id for n in ast.walk(tree) if isinstance(n, ast.Call) and n.func.id not in known})
    return f"知らない関数: {', '.join(bad)}" if bad else None


def evaluate(src, d: Definition, state: dict, env: dict | None = None, ctx: dict | None = None):
    """式を評価する。src が文字列でなければそのまま返す。"""
    if not isinstance(src, str):
        return src
    try:
        tree = ast.parse(src, mode="eval")
    except SyntaxError as e:
        raise ExprError(f"式が読めない: {src}（{e.msg}）") from None
    _check(tree)
    names = {**(ctx or context(d, state)), **(env or {})}
    try:
        # 内包表記の中からも見えるように、名前は globals に置く（関数と名前を限った式だけ）
        return eval(compile(tree, "<expr>", "eval"), {"__builtins__": {}, **names})  # noqa: S307
    except ExprError:
        raise
    except Exception as e:  # noqa: BLE001
        raise ExprError(f"式の評価に失敗: {src}（{type(e).__name__}: {e}）") from None
