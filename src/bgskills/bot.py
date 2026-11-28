"""思考ルーチン（ボット）を動かす道具：合法手の一覧、席ごとの見え方だけで手を選ぶ枠組み、リーグ戦（RUL-030）。

sangeki の流れにならう：ルールの処理はエンジン、判断は差し替えられる思考ルーチン。思考ルーチンは Python のファイル
（bots/<名前>.py）に `choose(ctx)` を書き、ctx.moves（今行える手）から 1 つを返す。ctx には、その席の見え方（ctx.view）と、
見えている部品の定義の値（ctx.part）と、その席に見える記録（ctx.log）だけを渡す。局面そのもの（隠れた情報）は渡さない。

    bg league <定義> --bot greedy=bots/greedy.py --bot random --players 2 --games 20 [--record experiments.jsonl] [--trace trace.jsonl]
    bg bot-step <対局> --human P1 --bot P2=bots/greedy.py [--max N]   # 人（Claude）の席の番まで、ほかの席を進める
"""
from __future__ import annotations

import importlib.util
import json
import math
import random
import tempfile
from collections import Counter
from functools import cached_property
from pathlib import Path

MAX_MOVES = 400  # 1 つの局面で並べる手の上限（引数の組み合わせが多い作品の保険）


class Ctx:
    """思考ルーチンに渡すもの。view はその席の見え方、moves は今行える手。part(id) は見えている部品の定義の値。"""

    def __init__(self, s, player, view, moves, rnd):
        self._s, self.player, self.view, self.moves, self.rnd = s, player, view, moves, rnd
        self.game = s.defn.data["game"]
        self._seen = _ids(view) | {str(v) for m in moves for v in (m.get("args") or {}).values()}

    def part(self, pid) -> dict:
        """部品の定義（種類・属性・持ち主）。この席から見えている部品だけ（見えない手札・山札の中身は引けない）。"""
        if pid not in self._seen:
            raise KeyError(f"{pid} はこの席から見えていない")
        p = self._s.defn.parts.get(pid) or {}
        return {"id": pid, "kind": p.get("kind"), "owner": p.get("owner"), "attributes": dict(p.get("attributes") or {})}

    def area(self, aid) -> list:
        """置き場の中身（見え方のまま。区別しない部品は {id, count}、見えない物は hidden）。"""
        v = (self.view.get("areas") or {}).get(aid) or {}
        sh = v.get("shown")
        return sh if isinstance(sh, list) else []

    def count(self, aid, kind=None) -> int:
        n = 0
        for it in self.area(aid):
            if kind and it.get("kind") != kind:
                continue
            n += it.get("count", 1) if isinstance(it.get("count", 1), int) else 0
        v = (self.view.get("areas") or {}).get(aid) or {}
        if isinstance(v.get("shown"), dict) and "count" in v["shown"] and not kind:
            n = v["shown"]["count"]
        return n

    @cached_property
    def log(self) -> list:
        """記録を、この席に見える形で（bg log --as と同じく伏せる。読んだときに 1 回だけ作る）。"""
        from .redact import visible_log
        return visible_log(self._s, self.player)

    def find(self, action=None, **args) -> list:
        """条件に合う手（action と引数の値で絞る）。"""
        return [m for m in self.moves if (action is None or m.get("action") == action)
                and all((m.get("args") or {}).get(k) == v for k, v in args.items())]


def _ids(view) -> set:
    out = set()

    def walk(x):
        if isinstance(x, dict):
            if isinstance(x.get("id"), str) and "hidden" not in x:
                out.add(x["id"])
            for y in x.values():
                walk(y)
        elif isinstance(x, list):
            for y in x:
                walk(y)
    walk(view.get("areas"))
    return out


def legal_moves(s, player, view_=None) -> list[dict]:
    """player が今行える手：{"action": id, "args": {...}}（進行の上で行え、条件を満たす引数の組）と、
    {"advance": "phase"|"turn"}（手番の人）、{"pass": True}（解決待ちがあるとき）。引数の候補は、その席に見えるものだけ。"""
    from .flow import available
    from .query import candidates, check_action
    from .redact import seen_ids, visible_candidates
    st = s.state()
    if player in s.defn.players:
        if view_ is None:
            from .view import view
            view_ = view(s.defn, st, player)
        seen = seen_ids(view_.get("areas"))
    else:
        seen = None
    if st.get("result") is not None:
        return []
    f = st.get("flow")
    acts = {a["id"]: a for a in s.defn.data.get("actions") or []}
    ids = []
    for xs in (available(s.defn, f, player) or {}).values():
        ids += [i for i in xs if i in acts and i not in ids]
    out = []
    for aid in ids:
        a = acts[aid]
        if a.get("by") and player not in a["by"]:
            continue
        if check_action(s.defn, st, a, {"actor": player, "player": player}):
            continue
        params = [p for p in a.get("params") or []]
        if any(p.get("free") for p in params):
            continue
        combos = [{}]
        for prm in params:
            nxt = []
            for args in combos:
                cs = visible_candidates(s.defn, st, player, candidates(s.defn, st, aid, player, prm["name"], args), seen)
                good = [c["id"] for c in cs if not c["problems"]]
                if prm.get("pick") == "first":
                    good = good[:1]
                nxt += [{**args, prm["name"]: g} for g in good]
                if len(nxt) > MAX_MOVES:
                    break
            combos = nxt[:MAX_MOVES]
        for args in combos:
            if not check_action(s.defn, st, a, {"actor": player, "player": player, **args}):
                out.append({"action": aid, "args": args})
    if st.get("stack"):
        out.append({"pass": True})
    elif f and f.get("active") == player:
        out += [{"advance": "phase"}, {"advance": "turn"}]
    return out


def random_policy(ctx):
    """でたらめ：行為があれば行為から選ぶ（進めるのは行為が無いときだけ）。"""
    acts = [m for m in ctx.moves if "action" in m]
    return ctx.rnd.choice(acts or ctx.moves) if ctx.moves else None


def load_policy(spec):
    """'random' か Python のファイル（choose(ctx) を持つ）。"""
    if spec in (None, "", "random"):
        return random_policy
    path = Path(spec)
    mod_spec = importlib.util.spec_from_file_location(f"bgbot_{path.stem.replace('-', '_')}", path)
    mod = importlib.util.module_from_spec(mod_spec)
    mod_spec.loader.exec_module(mod)
    if not hasattr(mod, "choose"):
        raise ValueError(f"{spec} に choose(ctx) が無い")
    return mod.choose


def _apply(s, player, m):
    if "action" in m:
        s.act(m["action"], player, m.get("args") or {})
    elif "advance" in m:
        s.apply({"op": "advance", "by": player, "to": m["advance"]})
    elif "pass" in m:
        s.apply({"op": "pass", "by": player})


def step(s, seats: dict, rnd, staged: set, humans=(), trace=None, seed=None) -> tuple:
    """1 手：今動く人（解決待ちがあれば応じる人、手番の人、手番のない段階ではキーパーのアクション、それから各席）が選んで行う。
    だれも動けなければキーパーが進行を進める。seats は {席: 方針}（無い席はでたらめ）。staged は手番のない段階で行った
    （行う人, アクション）で、ここで足す。返すのは (起きたこと, 席, 断られた手の数)。起きたことは ended・stuck・
    human（humans の席の番。何もしない）・seat（席が 1 手行った）・keeper（キーパーが準備のアクションか進行を行った）。"""
    from .session import OpError, _stack_next
    from .view import view
    st = s.state()
    f = st.get("flow") or {}
    if st.get("result") is not None or (f and not f.get("stage")):
        return "ended", None, 0
    if not f.get("stage"):
        return "stuck", None, 0
    if st.get("stack"):
        nxt = _stack_next(s.defn, st)["by"]
        who = [p for p in s.defn.players if p != nxt and p not in (st.get("stack_passes") or [])]
    elif f.get("active"):
        who = [f["active"]]
    else:  # 手番のない段階（準備）：キーパーのアクションをでたらめに、それから各席
        ka = [m for m in legal_moves(s, "keeper") if "action" in m and ("keeper", m["action"]) not in staged]
        if ka:
            m = rnd.choice(ka)
            staged.add(("keeper", m["action"]))
            try:
                _apply(s, "keeper", m)
                return "keeper", "keeper", 0
            except OpError:
                return step(s, seats, rnd, staged, humans, trace, seed)  # 行えなかったアクションは除いた（staged）ので、次を試す
        who = list(s.defn.players)
    refused = 0
    for p in sorted(who, key=lambda x: x in humans):  # 人の席は最後（準備で人が止まる前に、思考ルーチンの席が済ませる）
        v = view(s.defn, st, p)
        moves = legal_moves(s, p, v)
        if not f.get("active") and not st.get("stack"):
            moves = [m for m in moves if "action" in m and (p, m["action"]) not in staged]
        if not moves:
            continue
        if p in humans:
            return "human", p, refused
        ctx = Ctx(s, p, v, moves, rnd)
        for _ in range(5):  # 断られたら、その手を除いて選び直す
            choice = (seats.get(p) or random_policy)(ctx)
            note = margin = None
            if isinstance(choice, tuple):  # (手, 理由) か (手, 理由, 1 番目と 2 番目の差)
                choice, note, margin = (*choice, None, None)[:3]
            if choice is None:
                break
            try:
                _apply(s, p, choice)
            except OpError:
                refused += 1
                ctx.moves = [m for m in ctx.moves if m != choice]
                if not ctx.moves:
                    break
                continue
            if not f.get("active") and "action" in choice:
                staged.add((p, choice["action"]))
            if trace is not None:
                trace.append({"seed": seed, "turn": f.get("turn_no"), "player": p, "n_moves": len(moves), "move": choice,
                              **({"note": note} if note else {}), **({"margin": margin} if margin is not None else {})})
            return "seat", p, refused
    try:
        s.apply({"op": "advance", "by": "keeper", "to": "turn" if f.get("active") else "stage"})
        return "keeper", "keeper", refused
    except OpError:
        return "stuck", None, refused


def play_game(path, seats: dict, players: int, seed: int = 0, max_turns: int = 80, variants=None, trace=None) -> dict:
    """1 局：seats は {席: 方針（choose）}。手番の人（解決待ちがあれば応じる人、手番のない段階ではキーパーと各席）が選ぶ。
    キーパーだけが行うアクション（準備など）はでたらめに行う。返すのは結果（席ごとの勝ち負け・得点の順位）と、断られた手の数。"""
    from .session import Session
    s = Session.create(Path(tempfile.mkdtemp()) / "s", path, players, {}, seed, strict=True, variants=variants)
    rnd = random.Random(f"bot:{seed}")
    refused = decisions = 0
    staged = set()
    for _ in range(max_turns * 60):
        if (s.state().get("flow") or {}).get("turn_no", 0) > max_turns:
            break
        what, _, n = step(s, seats, rnd, staged, trace=trace, seed=seed)
        refused += n
        decisions += what == "seat"
        if what in ("ended", "stuck"):
            break
    st = s.state()
    r = st.get("result") or {}
    return {"seed": seed, "turns": (st.get("flow") or {}).get("turn_no", 0), "end": r.get("text") or ("打ち切り" if not r else ""),
            "results": r.get("results") or {}, "standings": r.get("standings") or [], "refused": refused, "decisions": decisions}


def _staged(s) -> set:
    """今の手番のない段階のうちに行った（行う人, アクション）。記録から作る（bot-step を何度呼んでも、準備を繰り返さない）。"""
    from .session import apply_op, initial_state

    def key(st):
        f = st.get("flow") or {}
        return f.get("stage_index"), f.get("cycle"), f.get("turn_no")
    st, done = initial_state(s.defn, s.meta.get("start") == "box"), {}
    for i, o in enumerate(s.log(), 1):
        if o.get("action"):
            done.setdefault(key(st), set()).add((o.get("by"), o["action"]))
        st = apply_op(s.defn, st, o, s.meta["seed"], i)
    return done.get(key(st), set())


def bot_step(s, humans=(), bots=None, max_moves: int = 500) -> dict:
    """bg bot-step（SPC-084）：humans の席の番が来るか、終わるか、だれも動けないか、max_moves 手を足すまで、ほかの席
    （bots に書かない席はでたらめ）とキーパーの準備を進める。手は通常の操作で記録に足す（画面にもそのまま出る）。
    出すのは止まった理由と手番の人と足した数だけ（どの手を指したかは bg log --as で、その席に見える形で読む）。"""
    from .session import OpError
    bots = bots or {}
    bad = sorted((set(humans) | set(bots)) - set(s.defn.players))
    if bad:
        raise OpError(f"定義にない席: {bad}")
    seats = {p: load_policy(b) for p, b in bots.items() if p not in humans}
    rnd = random.Random(f"bot-step:{s.meta['seed']}:{len(s.log())}")
    staged, applied, who = _staged(s), 0, None
    while applied < max_moves:
        what, who, _ = step(s, seats, rnd, staged, humans)
        if what in ("ended", "stuck", "human"):
            break
        applied += 1
    else:
        what = "max"
    out = {"stopped": what, "active": (s.state().get("flow") or {}).get("active"), "applied": applied}
    return {**out, "human": who} if what == "human" else out


def sign_test(a: int, b: int) -> float:
    n = a + b
    if n == 0:
        return 1.0
    k = min(a, b)
    return min(1.0, 2 * sum(math.comb(n, i) for i in range(k + 1)) / 2 ** n)


def league(path, bots: dict, players: int, games: int = 10, seed: int = 0, max_turns: int = 80, variants=None, trace=None) -> dict:
    """リーグ戦：方針を席に回して割り当て（席の有利を打ち消す）、同じ種で多数局。方針ごとの勝ちの割合・平均の順位・席ごとの勝ちと、
    方針が 2 つなら、同じ種の対局どうしを比べた符号検定（どちらが多く勝ったか）を出す。"""
    from .sim import wilson
    names = list(bots)
    pol = {n: load_policy(b) for n, b in bots.items()}
    seats = None
    stat = {n: Counter() for n in names}
    seat_win = {n: Counter() for n in names}
    ranks = {n: [] for n in names}
    per_seed = []
    ends = Counter()
    refused = 0
    for g in range(games):
        sd = seed + g
        for rot in range(len(names)):  # 方針を席に回す
            from .definition import load
            seats = load(path, players, None, variants).players if seats is None else seats
            assign = {p: names[(i + rot) % len(names)] for i, p in enumerate(seats)}
            r = play_game(path, {p: pol[n] for p, n in assign.items()}, players, sd, max_turns, variants, trace)
            ends[r["end"]] += 1
            refused += r["refused"]
            rk = {x["player"]: x["rank"] for x in r["standings"]}
            wins_here = Counter()
            for p, n in assign.items():
                res = r["results"].get(p, "none")
                stat[n][res] += 1
                if res == "win":
                    seat_win[n][p] += 1
                    wins_here[n] += 1
                if p in rk:
                    ranks[n].append(rk[p])
            per_seed.append(wins_here)
    out = {"games": games * len(names), "players": players, "ends": dict(ends), "refused_moves": refused, "bots": {}}
    total = games * len(names)
    for n in names:
        seats_played = sum(stat[n].values())
        out["bots"][n] = {"win_rate": round(stat[n].get("win", 0) / max(1, seats_played), 3),
                          "win_ci": wilson(stat[n].get("win", 0), seats_played), "results": dict(stat[n]),
                          "mean_rank": round(sum(ranks[n]) / max(1, len(ranks[n])), 2) if ranks[n] else None,
                          "wins_by_seat": dict(seat_win[n])}
    if len(names) == 2:
        a, b = names
        aw = sum(1 for w in per_seed if w[a] > w[b])
        bw = sum(1 for w in per_seed if w[b] > w[a])
        out["paired"] = {"games": total, f"{a}_more": aw, f"{b}_more": bw, "sign_test_p": round(sign_test(aw, bw), 4)}
    return out


def record_league(log, path, bots, players, games, seed, max_turns, result, variants=None, note=None):
    """試行の記録（CTR-F-007）に、リーグ戦の 1 行を足す。"""
    from .design import record
    r = {"bots": {n: str(b) for n, b in bots.items()}, **result}
    return record(log, path, variants or [], "league", players, games, seed, max_turns, r, note)


def dumps(x) -> str:
    return json.dumps(x, ensure_ascii=False)
