"""収穫の道の欲張りの思考ルーチン（考える順番は harvest-greedy.md）。bg league examples/harvest-road.yaml --bot greedy=examples/bots/harvest-greedy.py --bot random"""
COLORS = ("wheat", "bean", "fruit")


def choose(ctx):
    me = ctx.player
    picks = ctx.find("harvest")
    if not picks:  # 取れるものが無い（準備など）：行為があれば行う、なければ進める
        acts = [m for m in ctx.moves if "action" in m]
        return (acts or ctx.moves or [None])[0]
    fields = {a[len("field-"):]: [ctx.part(it["id"])["attributes"]["color"] for it in ctx.area(a)]
              for a in (ctx.view.get("areas") or {}) if a.startswith("field-")}
    mine = fields.get(me, [])

    def sets(cols):
        return min(cols.count(c) for c in COLORS)

    def lead(cols_by_player, c, p):
        n = cols_by_player[p].count(c)
        return all(n > v.count(c) for q, v in cols_by_player.items() if q != p)

    scored = []
    for m in picks:
        at = ctx.part(m["args"]["card"])["attributes"]
        c, v = at["color"], int(at["value"])
        after = {**fields, me: mine + [c]}
        new_set = sets(mine + [c]) > sets(mine)
        new_lead = lead(after, c, me) and not lead(fields, c, me)
        scored.append(((new_set, new_lead, v, ctx.rnd.random()), m, f"組{int(new_set)}・一番{int(new_lead)}・数{v}"))
    best = max(scored, key=lambda x: x[0])
    return best[1], best[2]
