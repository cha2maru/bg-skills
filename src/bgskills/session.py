"""対局：局面、基本の操作、記録と再生（SPC-014〜019）。ルールの合法性は見ない（キーパーが判断する）。"""
from __future__ import annotations

import copy
import fcntl
import json
import random
from datetime import datetime, timezone
from pathlib import Path

import yaml

from . import flow as F
from .definition import BOX, Definition, fill, load

UNLIMITED = "unlimited"


class OpError(ValueError):
    pass


# ---------- 局面 ----------

def _default_states(d: Definition, part_id):
    st = {f: next(iter(vals)) for f, vals in d.states(d.parts[part_id].get("kind")).items() if isinstance(vals, dict) and vals}
    st.update(d.parts[part_id].get("start_state") or {})
    return st


def initial_state(d: Definition, from_box: bool = False) -> dict:
    """定義の初期の置き場（start。なければ箱）。from_box ならすべての部品が箱に、既定の状態で入る（SPC-043）。"""
    places = {a: [] for a in d.areas}
    states = {}
    for pid, p in d.parts.items():
        where = BOX if from_box else (p.get("start") or BOX)
        if d.distinct(pid):
            places.setdefault(where, []).append(pid)
            states[pid] = _default_states(d, pid) if not from_box else {
                f: next(iter(v)) for f, v in d.states(p.get("kind")).items() if isinstance(v, dict) and v}
        else:
            places.setdefault(where, []).append({pid: p.get("count", 1)})
    progress = {k: v.get("start") for k, v in (d.data.get("progress") or {}).items()}
    s = {"progress": progress, "places": places, "attached": {}, "states": states, "entered": {},
         "known": {}, "hints": {}, "talk": [], "rulings": [], "result": None, "flow": F.initial(d, from_box)}
    _sync_active(s)
    return s


def _sync_active(s):
    """進行の構造の手番のプレイヤーを、進行の状態 active に写す（SPC-051）。"""
    if s.get("flow") and s["flow"].get("active") and "active" in s["progress"]:
        s["progress"]["active"] = s["flow"]["active"]


def locate(state, obj):
    """区別する部品の置き場（エリアか部品）。1 か所にだけあるはず。"""
    found = [c for c, items in state["places"].items() if obj in items]
    if len(found) > 1:
        raise OpError(f"{obj} が 2 か所以上にある: {found}")
    return found[0] if found else None


def _count_entry(items, part):
    for it in items:
        if isinstance(it, dict) and part in it:
            return it
    return None


def _container_ok(d, state, c):
    return c in d.areas or (c in d.parts and d.distinct(c) and locate(state, c) is not None)


def _insert(items, obj, at):
    if at in (None, "top"):
        items.append(obj)
    elif at == "bottom":
        items.insert(0, obj)
    else:
        items.insert(int(at), obj)


# ---------- 操作 ----------

OFFER_OPS = {"move", "attach", "set", "flip", "rotate"}  # 提案に入れられる操作（物を動かす・状態を変える）


def position_key(s: dict) -> str:
    """局面の物（置き場・状態・付いた物）と手番の人から作る鍵。同じ局面が何度目かを数えるのに使う。"""
    import hashlib
    body = json.dumps([s["places"], s["states"], s.get("attached"), (s.get("flow") or {}).get("active")], sort_keys=True, ensure_ascii=False)
    return hashlib.sha1(body.encode()).hexdigest()[:16]


def _owner_at(d, x, s=None):
    """置き場（か部品）の持ち主。エリアは親をたどる。持ち主のない部品は、置かれている所の持ち主。"""
    if x in d.parts:
        if d.parts[x].get("owner") or s is None:
            return d.parts[x].get("owner")
        x = locate(s, x)
    while x:
        if (d.areas.get(x) or {}).get("owner"):
            return d.areas[x]["owner"]
        x = d.parent.get(x)
    return None


def offer_parties(d, s, offer, proposer, to=None):
    """提案の中身を確かめ、相手（提案者のほかに持ち物が動く人。いなければ None）を返す。
    提案は 2 人の約束：動く物の元と先は、提案者と相手の持ち物の置き場だけ（銀行や他人の物は入れられない）。"""
    owners = set()
    for o in offer:
        obj = o.get("obj")
        if obj not in d.parts:
            like = [p for p, v in d.parts.items() if v.get("kind") == obj][:3]
            raise OpError(f"提案の {obj} は部品の ID ではない" + (f"（{'・'.join(like)} のことか）" if like else ""))
        places = [o.get("from") or locate(s, obj), o.get("to")] if o.get("op") == "move" else [locate(s, obj) or obj]
        for x in places:
            if not x:
                continue
            who = _owner_at(d, x, s)
            if who is None:
                raise OpError(f"提案に持ち主のない置き場（{x}）は入れられない（銀行などとの交換はアクションで行う）")
            owners.add(who)
    others = owners - {proposer}
    if len(others) > 1:
        raise OpError(f"提案は 2 人の約束（持ち物が動く相手が {'・'.join(sorted(others))} の複数いる）")
    if others and to is not None and not others <= set(to):
        raise OpError(f"聞かせていない {next(iter(others))} の持ち物が入っている")
    return next(iter(others), None)


def offer_eligible(d, t):
    """提案に答えられる人（相手が決まっていればその人だけ）。"""
    return [t["with"]] if t.get("with") else (t.get("to") or [p for p in d.players if p != t["by"]])


def talk_index(talk: list, n):
    """発言の番号 n（取り消しても使い回さない通し番号）から、並びの位置を引く。"""
    return next((i for i, t in enumerate(talk) if t.get("n", i) == n), None)


def next_talk_n(talk: list) -> int:
    return max((t.get("n", i) for i, t in enumerate(talk) if isinstance(t.get("n", i), int)), default=-1) + 1


def _stack_next(d, s):
    """次に解決する行為（既定は後から積んだもの。flow.stack: fifo なら先に積んだもの）。"""
    return s["stack"][0] if (d.data.get("flow") or {}).get("stack") == "fifo" else s["stack"][-1]


def _resolve_stack(d, s, seed, seq):
    """次の行為の手順を行う（1 つずつ。後の式は結果を読む）。行えなければ立ち消え（何も変えずに外す）。"""
    e = _stack_next(d, s)
    before = copy.deepcopy(s)
    cur = {"s": s, "k": 0}

    def run(o):
        cur["k"] += 1
        o = {k: v for k, v in o.items() if k != "act"}  # 宣言のときに数えた
        if o["op"] != "note":
            cur["s"] = apply_op(d, cur["s"], o, seed, f"{seq}.r{cur['k']}")
        return cur["s"]
    try:
        s["stack"] = [x for x in s["stack"] if x is not e]  # 解決するものは先に外す（手順の中の cancel が自分を指さないように）
        cur["s"] = s
        action_ops(d, e["action"], e["by"], e["args"], s, apply=run)
        s, status = cur["s"], "resolved"
    except OpError:
        s, status = before, "fizzled"
        s["stack"] = [x for x in s["stack"] if x["n"] != e["n"]]
    s.setdefault("stack_done", []).append({**e, "status": status})
    s["stack_passes"] = []
    return s


def _open_offer(talk: list, n) -> dict:
    i = talk_index(talk, n) if isinstance(n, int) else None
    if i is None or "offer" not in talk[i]:
        raise OpError(f"発言 #{n} は提案ではない")
    if talk[i]["status"] != "open":
        raise OpError(f"提案 #{n} はもう閉じている（{talk[i]['status']}）")
    return talk[i]


def _unslot(d: Definition, op: dict) -> dict:
    """配置場所（area の slot: true。見栄えのための場所）を行き先・元にした操作は、意味を持つ親のエリアへの操作にする（RUL-026）。
    部品はいつも親に置き、画面が配置場所に 1 つずつ並べる。"""
    out = op
    for k in ("to", "from"):
        a = op.get(k)
        if isinstance(a, str) and (d.areas.get(a) or {}).get("slot"):
            while a and (d.areas.get(a) or {}).get("slot"):
                a = d.parent.get(a)
            out = {**out, k: a}
    return out


def apply_op(d: Definition, state: dict, op: dict, seed: int, seq: int) -> dict:
    """操作を 1 つ適用した新しい局面を返す。受け付けられない操作は OpError（局面は変えない）。"""
    s = copy.deepcopy(state)
    kind = op.get("op")
    if s["result"] is not None:
        raise OpError("対局は終了している")
    op = _resolve_selector(d, s, op, seed, seq)
    op = _unslot(d, op)
    if op.get("act") and s.get("flow"):  # アクションの最初の操作で、行った回数を数える
        s["flow"] = F.record(d, s["flow"], op["action"], op.get("by"))
    if kind == "move":
        _move(d, s, op)
    elif kind == "attach":
        _attach(d, s, op)
    elif kind in ("flip", "set", "rotate"):
        obj = op["obj"]
        if obj not in s["states"]:
            raise OpError(f"{obj} は状態を持つ区別された部品ではない")
        defs = d.states(d.kind_of(obj))
        if kind in ("flip", "rotate"):
            field, value = _turn(d, obj, s["states"][obj], kind)
        else:
            field, value = op["field"], op["value"]
        typ = d.state_type(d.kind_of(obj), field)
        if typ:  # 書き込む状態（命令書・投票用紙）。型だけ確かめる
            ok = {"text": isinstance(value, str), "number": isinstance(value, int) and not isinstance(value, bool),
                  "player": value in d.players, "area": value in d.areas}.get(typ, True)
            if not ok and value not in (None, ""):
                raise OpError(f"{obj} の {field} は {typ}（{value} は書けない）")
        elif field not in defs or not isinstance(defs[field], dict) or value not in defs[field]:
            raise OpError(f"{obj} の状態 {field}={value} は定義にない")
        s["states"][obj][field] = value
    elif kind == "shuffle":
        area = op["area"]
        if area not in s["places"]:
            raise OpError(f"{area} はない")
        random.Random(f"{seed}:{seq}").shuffle(s["places"][area])
        for o in s["places"][area]:  # 切り直すと中身との対応が消える（G24）
            if isinstance(o, str):
                s["known"].pop(o, None)
                s.setdefault("hints", {}).pop(o, None)
    elif kind == "know":
        if op["obj"] not in d.parts or op["player"] not in d.players:
            raise OpError("部品かプレイヤーが定義にない")
        if op.get("fields"):  # 一部だけ知る（花火のヒント：この札は赤）。属性か状態の項目の名前
            got = s.setdefault("hints", {}).setdefault(op["obj"], {}).setdefault(op["player"], [])
            got += [f for f in op["fields"] if f not in got]
        else:
            lst = s["known"].setdefault(op["obj"], [])
            if op["player"] not in lst:
                lst.append(op["player"])
    elif kind == "say":  # 発言（RUL-009）。局面の物は変えず、話したことを残す。to で聞かせる相手を絞る（内緒話）
        to = op.get("to")
        to = [to] if isinstance(to, str) else to
        if to is not None and set(to) - set(d.players):
            raise OpError(f"聞かせる相手が席にない: {sorted(set(to) - set(d.players))}")
        fl = s.get("flow") or {}
        entry = {"n": op.get("n", next_talk_n(s.get("talk") or [])), "by": op.get("by"), **({"to": to} if to is not None else {}),
                 "text": str(op.get("text", "")), "turn": fl.get("turn_no", 0),
                 **({"stage": fl["stage"]} if fl.get("stage") else {}), **({"cycle": fl["cycle"]} if fl.get("cycle") else {}),
                 **({"hidden": True} if op.get("hidden") and to is not None else {})}
        if op.get("offer") is not None:  # 提案（守られる約束）：受けたら、この操作をまとめて行う
            offer = op["offer"]
            if not isinstance(offer, list) or not offer or any(not isinstance(o, dict) or o.get("op") not in OFFER_OPS for o in offer):
                raise OpError(f"提案の中身は操作のリスト（{'・'.join(sorted(OFFER_OPS))}）")
            entry.update(offer=offer, status="open")
            if op.get("by") in d.players:
                w = offer_parties(d, s, offer, op["by"], to)
                if w:
                    entry["with"] = w
            act = op.get("action") or (d.data.get("flow") or {}).get("offer_action")  # 受けたら、このアクションを行ったことにする（手番・回数）
            if act:
                if act not in {a["id"] for a in d.data.get("actions") or []}:
                    raise OpError(f"提案のアクション {act} は定義にない")
                entry["action"] = act
        talk = s.setdefault("talk", [])
        if op.get("reply_to") is not None:  # 条件を変えて返す：元の提案は閉じる
            _open_offer(talk, op["reply_to"])["status"] = "countered"
            entry["reply_to"] = op["reply_to"]
        talk.append(entry)
    elif kind == "answer":  # 提案に答える。受ければ中身をすべて行うか、1 つも行わない。出した人が断れば取り下げ
        talk = s.setdefault("talk", [])
        t, by = _open_offer(talk, op.get("talk")), op.get("by")
        idx = talk_index(talk, op["talk"])
        if by == t["by"]:
            if op.get("accept"):
                raise OpError("自分の提案は受けられない（取り下げるなら bg answer --decline）")
            t["status"] = "withdrawn"
        else:
            if by != "keeper" and by not in offer_eligible(d, t):
                raise OpError(f"{by} はこの提案の相手ではない（答えられるのは {'・'.join(offer_eligible(d, t))}）")
            if op.get("accept"):
                for k, o in enumerate(t["offer"]):
                    try:
                        s = apply_op(d, s, {"by": t["by"], **o}, seed, f"{seq}.{k}")
                    except OpError:  # くわしい理由は相手の手札を明かすので出さない
                        raise OpError(f"提案 #{op['talk']} は今は行えない（どちらかの持ち物が足りないか、置き場が変わった）") from None
                talk = s["talk"]
                if t.get("action") and s.get("flow"):  # 進行の上では、出した人がそのアクションを行ったことにする
                    s["flow"] = F.record(d, s["flow"], t["action"], t["by"])
            talk[idx].update(status="accepted" if op.get("accept") else "declined", answered_by=by)
        talk.append({"n": op.get("n", next_talk_n(talk)), "by": by,
                     "text": str(op.get("text") or {"accepted": "受けた", "declined": "断った", "withdrawn": "取り下げた"}[talk[idx]["status"]]),
                     "answer": op["talk"], **({"to": t["to"] + [t["by"]]} if t.get("to") else {}),
                     "turn": (s.get("flow") or {}).get("turn_no", 0)})
    elif kind == "stack":  # スタックに積む（宣言した行為を、解決を待つ列に置く）
        acts = {a["id"]: a for a in d.data.get("actions") or []}
        if op.get("action") not in acts:
            raise OpError(f"アクション {op.get('action')} は定義にない")
        s["stack_next"] = s.get("stack_next", 0) + 1
        s.setdefault("stack", []).append({"n": s["stack_next"], "action": op["action"], "by": op.get("by"), "args": op.get("args") or {}})
        s["stack_passes"] = []
    elif kind == "pass":  # 見送る。積んだ人以外の全員が見送ったら、一番上（fifo なら一番下）を解決する
        if not s.get("stack"):
            raise OpError("スタックに解決待ちがない")
        if op.get("by") not in d.players:
            raise OpError("見送るのはプレイヤー")
        if op["by"] not in s.setdefault("stack_passes", []):
            s["stack_passes"].append(op["by"])
        if set(s["stack_passes"]) >= set(d.players) - {_stack_next(d, s)["by"]}:
            s = _resolve_stack(d, s, seed, seq)
    elif kind == "resolve":  # キーパーが解決を進める（見送りを待たない）
        if not s.get("stack"):
            raise OpError("スタックに解決待ちがない")
        s = _resolve_stack(d, s, seed, seq)
    elif kind == "cancel":  # 解決待ちの行為を打ち消す（解決せずに外す）
        n = int(op.get("target"))
        e = next((e for e in s.get("stack") or [] if e["n"] == n), None)
        if e is None:
            raise OpError(f"スタックに #{n} はない")
        s["stack"].remove(e)
        s.setdefault("stack_done", []).append({**e, "status": "canceled"})
    elif kind == "progress":
        if op["key"] not in s["progress"]:
            raise OpError(f"進行状態 {op['key']} は定義にない")
        if "expr" in op:  # 式の値を書き残す（記憶。例：前のループの終わりに友好のあったキャラクター）
            from .expr import evaluate
            s["progress"][op["key"]] = evaluate(op["expr"], d, s)
        else:
            s["progress"][op["key"]] = op["value"]
    elif kind == "ruling":
        s["rulings"].append({k: v for k, v in op.items() if k not in ("op",)})  # 知らないキー（text など）も捨てない
    elif kind == "advance":  # 次のフェーズ・手番・段階へ（SPC-051）
        if not s.get("flow"):
            raise OpError("定義に進行の構造（flow）がない")
        before_active = s["flow"].get("active")
        def step(to, player=None):
            nonlocal s
            before = s["flow"]
            after = F.advance(d, before, to, player)

            def run(o):
                nonlocal s
                if o["op"] != "note":
                    s = apply_op(d, s, o, seed, seq)
                return s
            for steps in F.on_end(d, before, after):  # 終わる手番・段階の手順（手番の人はまだ前の人。手札の上限まで捨てる、など）
                action_ops(d, {"id": "(on_end)", "steps": steps}, "keeper", {}, s, apply=run)
            s["flow"] = after
            _sync_active(s)
            for steps in F.on_start(d, before, s["flow"]):  # 段階・手番に入ったときの手順（エリアの on_enter の時間版）
                # 1 つずつ行い、後の式はその結果を読む（どくのダメージの後に HP を調べる）
                action_ops(d, {"id": "(on_start)", "steps": steps}, "keeper", {}, s, apply=run)
        step(op.get("to", "phase"), op.get("player"))
        for _ in range(64):  # until：そのフェーズ（か段階）に着くまで進める
            if not op.get("until") or op["until"] in (s["flow"].get("phase"), s["flow"].get("stage")) or not s["flow"].get("stage"):
                break
            step("phase")
        if s["flow"].get("active") != before_active:  # 手番が替わった局面を覚える（千日手・同じ局面の繰り返し）
            k = position_key(s)
            s.setdefault("seen", {})[k] = s.get("seen", {}).get(k, 0) + 1
    elif kind == "roll":  # ダイス：状態の項目を取りうる値からランダムに（SPC-047）
        obj = op["obj"]
        defs = d.states(d.kind_of(obj))
        field = op.get("field") or next((f for f, v in defs.items() if isinstance(v, dict)), None)
        if obj not in s["states"] or not isinstance(defs.get(field), dict):
            raise OpError(f"{obj} は振れない（状態の項目がない）")
        s["states"][obj][field] = random.Random(f"{seed}:{seq}").choice(list(defs[field]))
    elif kind == "spread":  # from の部品を into の子のエリアへ 1 つずつ配る（SPC-047）
        src, into = op["from"], op["into"]
        if src not in s["places"] or into not in d.areas:
            raise OpError(f"{src} か {into} がない")
        k, tk = op.get("kind"), op.get("into_kind")
        parts = [o for o in s["places"][src] if isinstance(o, str) and (not k or k in d.kind_chain(d.parts[o].get("kind")))]
        if op.get("parts"):  # 配る部品の順（G10）
            parts = [o for o in op["parts"] if o in s["places"][src]]
        cells = [c["id"] for c in d.areas[into].get("areas") or [] if not tk or tk in d.kind_chain(c.get("kind"))]
        if op.get("order"):  # 配る先の順（渦巻きなど。G10）
            cells = [c for c in op["order"] if c in cells]
        if op.get("skip_filled"):
            cells = [c for c in cells if not s["places"].get(c)]
        if op.get("skip"):  # 条件に合う先には配らない（砂漠など）
            from .query import holds
            cells = [c for c in cells if not holds(d, s, c, op["skip"])]
        for o, c in zip(parts, cells):
            _move(d, s, {"obj": o, "to": c, "facing": op.get("facing")})
    elif kind == "gather":  # あるエリアの部品を、種類を絞って、まとめて動かす（SPC-043）
        src, to, k = op["from"], op["to"], op.get("kind")
        if src not in s["places"] or not _container_ok(d, s, to):
            raise OpError(f"{src} か {to} がない")
        for it in list(s["places"][src]):
            pid = it if isinstance(it, str) else next(iter(it))
            if k and k not in d.kind_chain(d.parts[pid].get("kind")):
                continue
            if op.get("owner") and d.parts[pid].get("owner") != op["owner"]:  # 持ち主で絞る（プレイヤーごとのコマ）
                continue
            if isinstance(it, str):
                _move(d, s, {"obj": pid, "to": to, "facing": op.get("facing")})
            else:
                n = it[pid]
                s["places"][src].remove(it)
                _put(s, {pid: n}, to)
    elif kind == "reset":  # 部品を定義の初期の置き場と状態へ（to: box なら箱へ）。進行状態と裁定は残す（SPC-026）
        fresh = initial_state(d, op.get("to") == BOX)
        s.update(places=fresh["places"], states=fresh["states"], attached={}, known={})
    elif kind == "note":  # 何も変えない（繰り返しが 0 回だったアクションの記録）
        pass
    elif kind == "end":
        winners = op.get("winners") or ([op["winner"]] if op.get("winner") else None)  # 勝者（チームなら並び）。ほかは負け（SPC-045）
        if isinstance(winners, str):
            winners = [w.strip() for w in winners.split(",")]
        results = op.get("results") or ({p: ("win" if p in winners else "lose") for p in d.players} if winners else None)
        if not results and op.get("draw"):  # 引き分け（全員 draw）
            results = {p: "draw" for p in d.players}
        bad = set(results or {}) - set(d.players)
        if bad or not results:
            raise OpError(f"結果の席が不正: {sorted(bad) or '空'}")
        s["result"] = {"results": results, "rule": op.get("rule"), **({"text": op["text"]} if op.get("text") else {}),
                       **({"standings": op["standings"]} if op.get("standings") else {})}
    else:
        raise OpError(f"知らない操作: {kind}")
    return s


def _turn(d, obj, st, how):
    """表示方法（SPC-038）で、表裏を返す（flip）か時計回りに次の回転へ回す（rotate）状態の変更を 1 つ探す。"""
    k = d.kind_of(obj)
    now = d.display(k, st)
    want_face = {"up": "down", "down": "up"}[now["face"]] if how == "flip" else now["face"]
    cands = []
    for f, vals in d.states(k).items():
        for v in vals if isinstance(vals, dict) else {}:
            if v == st.get(f):
                continue
            disp = d.display(k, {**st, f: v})
            if disp["face"] != want_face:
                continue
            if how == "flip" and disp["rotate"] != now["rotate"]:
                continue
            step = (disp["rotate"] - now["rotate"]) % 360
            if how == "rotate" and step == 0:
                continue
            cands.append((step, f, v))
    if not cands:
        raise OpError(f"{obj} は{'表裏を返せない' if how == 'flip' else '回せない'}（状態の定義にない）")
    _, f, v = min(cands)  # 回すときは時計回りに最も近い向きへ
    return f, v


def _resolve_selector(d, s, op, seed=None, seq=None):
    """obj に "top:<エリア>" / "bottom:<エリア>" / "random:<エリア>" を書けば、そのエリアの一番上・下・ランダムな区別された部品にする。"""
    obj = op.get("obj")
    if isinstance(obj, str) and obj.split(":", 1)[0] in ("top", "bottom", "random") and ":" in obj:
        end, area = obj.split(":", 1)
        kind_ok = lambda pid: not op.get("kind") or op["kind"] in d.kind_chain(d.parts[pid].get("kind"))
        items = [o for o in s["places"].get(area, []) if isinstance(o, str) and kind_ok(o)]
        if end == "random":  # 区別しない部品も 1 枚ずつ数えて選ぶ（手札の資源からランダムに 1 枚）
            pool = items + [p for o in s["places"].get(area, []) if isinstance(o, dict)
                            for p, n in o.items() if isinstance(n, int) and kind_ok(p) for _ in range(n)]
            if not pool:
                raise OpError(f"{area} に部品がない")
            pick = random.Random(f"{seed}:{seq}:pick").choice(pool)
            return {**op, "obj": pick, "from": area, **({} if pick in items else {"n": 1})}
        if not items:
            raise OpError(f"{area} に部品がない")
        pick = items[-1] if end == "top" else items[0]
        return {**op, "obj": pick, "from": area}
    return op


def warnings(d: Definition, state: dict, op: dict) -> list[str]:
    """受け付けた操作の後の局面で、置き場の上限を超えたエリアを知らせる（拒否はしない。SPC-025）。"""
    to = op.get("to") if op.get("op") != "say" else None  # 発言の to は聞かせる相手
    cap = d.capacity(to) if isinstance(to, str) else None
    if cap is None:
        return []
    from .query import _fixture
    n = sum(0 if isinstance(o, str) and _fixture(d, o) else 1 if isinstance(o, str) else
            (o[next(iter(o))] if isinstance(o[next(iter(o))], int) else 0) for o in state["places"].get(to, []))
    return [f"{to} は上限 {cap} を超えている（{n}）"] if n > cap else []


def _take(d, s, op):
    """移す物を元の置き場から取り出し、(物, 元の置き場) を返す。"""
    obj = op["obj"]
    if obj not in d.parts:
        raise OpError(f"{obj} は定義にない")
    if d.distinct(obj):
        where = locate(s, obj)
        if where is None:
            raise OpError(f"{obj} は局面にない")
        if op.get("from") and op["from"] != where:
            raise OpError(f"{obj} は {op['from']} ではなく {where} にある")
        s["places"][where].remove(obj)
        s["attached"].pop(obj, None)
        return obj, where
    src, n = op.get("from"), int(op.get("n", 1))
    entry = _count_entry(s["places"].get(src, []), obj) if src else None
    if entry is None:
        raise OpError(f"{obj} は {src} にない")
    if entry[obj] != UNLIMITED:
        if entry[obj] < n:
            raise OpError(f"{src} の {obj} は {entry[obj]} 個で、{n} 個は動かせない")
        entry[obj] -= n
        if entry[obj] == 0:
            s["places"][src].remove(entry)
    return {obj: n}, src


def _put(s, thing, to, at=None):
    if isinstance(thing, str):  # 部品がエリアに入った手番を覚える（G5：買った手番には使えない、など）
        s.setdefault("entered", {})[thing] = (s.get("flow") or {}).get("turn_no", 0)
    items = s["places"].setdefault(to, [])
    if isinstance(thing, dict):
        (part, n), = thing.items()
        e = _count_entry(items, part)
        if e is None:
            items.append({part: n})
        elif e[part] != UNLIMITED:
            e[part] += n
    else:
        _insert(items, thing, at)


def _move(d, s, op):
    to = op["to"]
    if not _container_ok(d, s, to):
        raise OpError(f"置き場 {to} がない")
    if to == op["obj"]:
        raise OpError("自分の上には置けない")
    if op.get("facing") is not None and (op["obj"] not in s["states"] or op["facing"] not in (d.states(d.kind_of(op["obj"])).get("facing") or {})):
        raise OpError(f"{op['obj']} は向き {op['facing']} を取れない")
    thing, _ = _take(d, s, op)
    _put(s, thing, to, op.get("at"))
    if op.get("facing") is None and isinstance(thing, str):  # エリアに入ったときの状態（SPC-044）
        enter = (d.areas.get(to) or {}).get("on_enter") or {}
        defs = d.states(d.kind_of(thing))
        for f, v in enter.items():
            if isinstance(defs.get(f), dict) and v in defs[f]:
                s["states"][thing][f] = v
    if op.get("facing") is not None:  # 置くときに表で出すか裏で出すかを同じ操作で決める
        s["states"][op["obj"]]["facing"] = op["facing"]
        if op["facing"] == "down" and op.get("by") in d.players:  # 裏向きで置いた本人は中身を知っている
            lst = s["known"].setdefault(op["obj"], [])
            if op["by"] not in lst:
                lst.append(op["by"])


def _attach(d, s, op):
    obj, target = op["obj"], op["to"]
    if not (target in d.parts and d.distinct(target)):
        raise OpError(f"付き先 {target} は区別された部品ではない")
    where = locate(s, target)
    if where is None or obj == target:
        raise OpError(f"付き先 {target} は局面にない")
    thing, _ = _take(d, s, op)
    items = s["places"][where]
    i = items.index(target)
    items.insert(i if op.get("side", "under") == "under" else i + 1, thing)
    s["attached"][obj] = {"to": target, "side": op.get("side", "under")}


# ---------- アクション（SPC-039） ----------

def action_ops(d: Definition, action_id: str, actor: str, args: dict | None = None, state: dict | None = None,
               apply=None) -> list[dict]:
    """定義のアクションを、引数と行う人を埋めた基本の操作の並びにする。合法かどうかは見ない。

    手順には基本の操作のほか、let（式で値を決める）・each（式で選んだものごとに繰り返す。値 players も可）・
    if（式が真なら do、偽なら else）を書ける（SPC-053）。式はアクションを始めたときの局面で計算する。
    apply（操作を受けて新しい局面を返す）を渡すと、操作を 1 つ作るたびに行い、後の式はその結果の局面を読む
    （アクションの stepwise。コインの結果やダメージの後の HP を、続く手順で読む。RUL-011）。
    """
    from .expr import ExprError, context, evaluate
    acts = {a["id"]: a for a in d.data.get("actions") or []}
    if isinstance(action_id, dict):  # 定義の中の手順そのもの（進行の on_start など）
        a, action_id = action_id, action_id.get("id", "(手順)")
    elif action_id not in acts:
        raise OpError(f"アクション {action_id} は定義にない")
    else:
        a = acts[action_id]
    args = dict(args or {})
    missing = [p["name"] for p in a.get("params") or [] if p["name"] not in args]
    if missing:
        raise OpError(f"アクション {action_id} の選ぶものが足りない: {missing}")
    st = state if state is not None else initial_state(d)
    ctx = context(d, st)
    out = []

    def ev(src, env):
        try:
            return evaluate(src, d, st, env, ctx if apply is None else None)
        except ExprError as e:
            raise OpError(f"アクション {action_id}：{e}") from None

    def let(spec, env):
        env = dict(env)
        for k, src in (spec or {}).items():
            env[k] = ev(fill(src, env) if isinstance(src, str) and "{" in src and not src.startswith("[") else src, env)
        return env

    def expand(steps, env):
        for step in steps or []:
            if "let" in step and len(step) == 1:
                env = let(step["let"], env)
                continue
            if "if" in step:  # {引数} は値に置き換えてから計算する（let と同じ）
                cond = fill(step["if"], env) if isinstance(step["if"], str) and "{" in step["if"] else step["if"]
                expand(step.get("do") if ev(cond, env) else step.get("else"), let(step.get("let"), env))
                continue
            if "call" in step:  # ほかのアクションの手順をここで行う（args は {名前} で埋める。きぜつの処理を手番の初めからも呼ぶ）
                sub = acts.get(step["call"])
                if sub is None:
                    raise OpError(f"アクション {action_id}：call の {step['call']} は定義にない")
                depth[0] += 1
                if depth[0] > 20:
                    raise OpError(f"アクション {action_id}：call が深すぎる（{step['call']} を呼び続けている）")
                sub_env = let(sub.get("let"), {"actor": actor, "player": actor, **fill(step.get("args") or {}, env)})
                expand(sub.get("steps"), sub_env)
                depth[0] -= 1
                continue
            if "each" in step and "do" in step:  # 選んだものごとに繰り返す
                items = d.players if step["each"] == "players" else ev(step["each"], env)
                for x in items or []:
                    expand(step["do"], {**env, step.get("as", "it"): x, "player" if step["each"] == "players" else "_": x})
                continue
            bare = {k: v for k, v in step.items() if k not in ("each", "times")}
            who = d.players if step.get("each") == "players" else [env.get("player", actor)]  # プレイヤーごと（SPC-043）
            for p in who:
                for _ in range(int(fill(step.get("times", 1), env))):
                    emit({**fill(bare, {**env, "player": p}), "by": actor, "rule": a.get("rule"), "action": action_id})

    depth = [0]

    def emit(op):
        nonlocal st
        if not out:
            op["act"] = 1  # アクションの最初の操作（行った回数を数える）
        if apply is not None:
            st = apply(op)
        out.append(op)

    env = let(a.get("let"), {"actor": actor, "player": actor, **args})
    expand(a.get("steps"), env)
    if not out:  # 手順が 0 個でも、行ったことは記録に残す
        emit({"op": "note", "by": actor, "rule": a.get("rule"), "action": action_id})
    return out


def compare_to_start(d: Definition, state: dict) -> dict:
    """局面を、定義の初期の置き場と比べる（準備の手順の確かめ。SPC-043）。"""
    start = initial_state(d)
    loc = lambda st: {o: c for c, items in st["places"].items() for o in items if isinstance(o, str)}
    a, b = loc(state), loc(start)
    moved = {o: {"now": a.get(o), "start": b.get(o)} for o in d.parts if d.distinct(o) and a.get(o) != b.get(o)}
    states = {o: {"now": state["states"].get(o), "start": start["states"].get(o)}
              for o in start["states"] if state["states"].get(o) != start["states"].get(o)}
    def order_differs(c):  # 両方にある部品の並びが違う
        now, st = [o for o in state["places"].get(c, []) if isinstance(o, str)], [o for o in start["places"].get(c, []) if isinstance(o, str)]
        return [o for o in now if o in st] != [o for o in st if o in now]
    order = sorted(c for c in d.areas if (d.areas[c].get("ordered") or any(d.kinds[k].get("ordered") for k in d.kind_chain(d.areas[c].get("kind"))))
                   and order_differs(c))
    return {"same": not (moved or states or order), "moved": moved, "states": states, "order_differs": order}


# ---------- 対局（ファイル） ----------

def _hash(path) -> str:
    import hashlib
    return hashlib.sha1(Path(path).read_bytes()).hexdigest()[:12]


class Session:
    """sessions/<id>/session.yaml（版・人数・着席者・種）と log.jsonl（操作の列）。局面は記録から作り直す。"""

    def __init__(self, path):
        self.dir = Path(path)
        self.meta = yaml.safe_load((self.dir / "session.yaml").read_text(encoding="utf-8"))
        sc = self.dir / self.meta["scenario"] if self.meta.get("scenario") else None
        vs = [self.dir / v["file"] for v in self.meta.get("variants") or []]  # 案は対局のフォルダの写しを使う（CTR-F-007）
        self.defn = load(self.meta["definition"], self.meta["players"], sc, vs)
        if self.defn.data["game"].get("version") != self.meta["version"]:
            raise OpError(f"定義の版が対局と違う（対局 {self.meta['version']}）")
        h = _hash(self.meta["definition"])
        self.load_warnings = [] if self.meta.get("def_hash") in (None, h) else [
            "定義のファイルが対局を作ったときから変わっている（版は同じ）。版を上げるか、対局を作り直す"]
        self.last_warnings, self.last_ops = [], []

    @classmethod
    def create(cls, path, definition, players, seats, seed, from_box=False, strict=None, scenario=None, variants=None):
        variants = list(variants or [])
        d = load(definition, players, scenario, variants)  # 人数が範囲外なら DefinitionError
        if strict is None:  # 省いたら定義の既定（game.strict。隠れた情報のある作品は、外れた行為で情報が漏れるので厳格が既定）
            strict = bool(d.data["game"].get("strict"))
        bad = set(seats) - set(d.players)
        if bad:
            raise OpError(f"定義にない席: {sorted(bad)}")
        p = Path(path)
        if p.exists():
            raise OpError(f"{p} はすでにある")
        p.mkdir(parents=True)
        if scenario:  # シナリオは対局のフォルダに写す（定義は公開しても、脚本は対局の中にだけ置ける）
            (p / "scenario.yaml").write_bytes(Path(scenario).read_bytes())
        vmeta = []
        for i, v in enumerate(variants, 1):  # 案も写す（後で案のファイルを直しても、この対局は変わらない）
            (p / f"variant-{i}.yaml").write_bytes(Path(v).read_bytes())
            vmeta.append({"name": Path(v).stem, "file": f"variant-{i}.yaml"})
        meta = {"definition": str(Path(definition).resolve()), "def_hash": _hash(definition), "game": d.data["game"]["id"],
                "version": d.data["game"].get("version"), "players": players,
                "seats": {pl: seats.get(pl) for pl in d.players}, "seed": seed,
                **({"start": BOX} if from_box else {}), **({"strict": True} if strict else {}),
                **({"scenario": "scenario.yaml"} if scenario else {}), **({"variants": vmeta} if vmeta else {})}
        (p / "session.yaml").write_text(yaml.safe_dump(meta, allow_unicode=True, sort_keys=False), encoding="utf-8")
        (p / "log.jsonl").write_text("", encoding="utf-8")
        return cls(p)

    def _check_actor(self, who):
        if who is not None and who != "keeper" and who not in self.defn.players:
            raise OpError(f"{who} は席にない（{'・'.join(self.defn.players)}・keeper）")

    def act(self, action_id: str, actor: str, args: dict | None = None) -> dict:
        """アクションの手順をすべて行うか、1 つも行わない（途中で受け付けられなければ記録しない）。"""
        from .query import candidates, check_action, check_param
        self._check_actor(actor)
        a = next((x for x in self.defn.data.get("actions") or [] if x["id"] == action_id), None)
        if a is None:
            raise OpError(f"アクション {action_id} は定義にない")
        args = dict(args or {})
        now = datetime.now(timezone.utc).isoformat(timespec="seconds")
        # 画面と同時に書いても、手順は書き足す直前の局面から作る（古い局面の手順を記録しない）
        with (self.dir / "log.jsonl").open("a", encoding="utf-8") as f:
            fcntl.flock(f, fcntl.LOCK_EX)
            log = self.log()
            st, seq, done = self._replay(log), len(log), []
            if st.get("result") is not None:  # 終わった対局では、進行の理由より先に「終わっている」と返す
                raise OpError("対局は終了している（結果は bg show の result・flow.result）")
            for prm in a.get("params") or []:  # 区別しないコマなど、省いたら条件を満たす最初の候補（pick: first）
                if prm["name"] not in args and prm.get("pick") == "first":
                    ok = [c["id"] for c in candidates(self.defn, st, action_id, actor, prm["name"], args) if not c["problems"]]
                    if ok:
                        args[prm["name"]] = ok[0]
            _, pre = F.classify(self.defn, st.get("flow"), action_id, actor)  # 進行の構造から外れていれば警告
            if st.get("stack") and not a.get("stack") and not a.get("during_stack"):
                pre.append(f"スタックに解決待ちがある（{action_id} は、積む（stack）アクションか during_stack のアクションだけ）")
            env = {"actor": actor, "player": actor, **args}
            pre += check_action(self.defn, st, a, env)
            for prm in a.get("params") or []:  # 引数の条件（SPC-052）
                if args.get(prm["name"]) is not None:
                    pre += check_param(self.defn, st, prm, args[prm["name"]], env)

            if self.meta.get("strict") and pre:  # 厳格モード：条件・進行から外れていれば、手順を作る前に断る（手順の式を外れた局面で計算しない）
                raise OpError("厳格モードで受け付けない：" + "／".join(pre))

            def run(op):
                nonlocal st, seq
                seq += 1
                try:
                    op2 = _resolve_selector(self.defn, st, {**op, "time": now}, self.meta["seed"], seq)
                    st = apply_op(self.defn, st, op2, self.meta["seed"], seq)
                except OpError as e:  # どの手順で何が足りないかを示す（記録は残さない）
                    raise OpError(f"アクション {action_id} の手順 {len(done) + 1}（{op.get('op')} {op.get('obj', '')}）：{e}") from None
                done.append(op2)
                return st

            if a.get("stack"):  # スタックに積む（宣言）。手順は、全員が見送って解決するときに行う
                missing = [p["name"] for p in a.get("params") or [] if p["name"] not in args]
                if missing:  # 積む前に確かめる（解決のときに足りないと分かっても、払った後になる）
                    raise OpError(f"アクション {action_id} の選ぶものが足りない: {missing}")
                # cost：積むときにすぐ行う手順（ルーンを払う・カードを唱えている場所へ）。行えなければ積まない
                paid = action_ops(self.defn, {"id": action_id, "steps": a.get("cost"), "let": a.get("let"), "rule": a.get("rule")},
                                  actor, args, st, apply=run) if a.get("cost") else []
                run({"op": "stack", "action": action_id, "by": actor, "args": args, "rule": a.get("rule"),
                     **({} if paid else {"act": 1})})
            else:
                ops = action_ops(self.defn, action_id, actor, args, st, apply=run if a.get("stepwise") else None)
                if not a.get("stepwise"):
                    for op in ops:
                        run(op)
            if self.meta.get("strict"):  # 厳格モード：条件・進行から外れた行為は受け付けない（記録しない）
                post = [w for o in done for w in warnings(self.defn, st, o)]
                if pre or post:
                    raise OpError("厳格モードで受け付けない：" + "／".join(pre + post))
            if F.auto_advance(self.defn, st.get("flow")):  # 回数を使い切ったら次のフェーズへ（フェイズの auto）
                seq += 1
                # action を付けて、undo でアクションと一緒に取り消す
                adv = {"op": "advance", "by": "keeper", "auto": True, "action": action_id, "time": now}
                st = apply_op(self.defn, st, adv, self.meta["seed"], seq)
                done.append(adv)
            end = self._auto_end(self._replay(log), st, action_id)
            if end:
                seq += 1
                st = apply_op(self.defn, st, end, self.meta["seed"], seq)
                done.append(end)
            f.write("".join(json.dumps(o, ensure_ascii=False) + "\n" for o in done))
        self.last_warnings = pre + [w for o in done for w in warnings(self.defn, st, o)]
        self.last_ops = done
        return st

    def _auto_end(self, before: dict, after: dict, action_id=None) -> dict | None:
        """flow.auto_end：終わりの条件を満たし時機が来たら、結果を書いた end の操作を作る（記録に残る。undo で一緒に戻る）。"""
        if not (self.defn.data.get("flow") or {}).get("auto_end") or after.get("result") is not None:
            return None
        fb, fa = before.get("flow") or {}, after.get("flow") or {}
        timings = ["now"]
        if (fb.get("turn_no"), fb.get("stage")) != (fa.get("turn_no"), fa.get("stage")):
            timings.append("turn_end")
            if not fa.get("stage") or fa.get("stage") != fb.get("stage") or fa.get("turn_in_stage", 0) % len(self.defn.players) == 0:
                timings.append("round_end")  # 全員が同じ回数ずつ手番を終えた
        r = F.end_result(self.defn, after, tuple(timings))
        if not r or not r["results"]:
            return None
        return {"op": "end", "by": "keeper", "auto": True, "results": r["results"], "text": r["text"],
                **({"standings": r["standings"]} if r.get("standings") else {}), **({"rule": r["rule"]} if r.get("rule") else {}),
                **({"action": action_id} if action_id else {})}

    def rebase(self) -> int:
        """定義のファイルを直した後、記録が今の定義で最後まで再生できることを確かめ、定義の印（def_hash）を今のものにする。"""
        n = len(self.log())
        self.state()  # 再生できなければ OpError（記録は変えない）
        self.meta["def_hash"] = _hash(self.meta["definition"])
        (self.dir / "session.yaml").write_text(yaml.safe_dump(self.meta, allow_unicode=True, sort_keys=False), encoding="utf-8")
        return n

    def undo(self) -> list[dict]:
        """最後の操作（アクションなら、そのアクションの操作すべて）を記録から外す。"""
        with (self.dir / "log.jsonl").open("r+", encoding="utf-8") as f:
            fcntl.flock(f, fcntl.LOCK_EX)
            ops = [json.loads(l) for l in f.read().splitlines() if l]
            if not ops:
                raise OpError("取り消す操作がない")
            k = len(ops) - 1
            if ops[k].get("action"):
                while k > 0 and not ops[k].get("act") and ops[k - 1].get("action") == ops[k]["action"]:
                    k -= 1
            removed, ops = ops[k:], ops[:k]
            f.seek(0)
            f.truncate()
            f.write("".join(json.dumps(o, ensure_ascii=False) + "\n" for o in ops))
        return removed

    def log(self) -> list[dict]:
        return [json.loads(l) for l in (self.dir / "log.jsonl").read_text(encoding="utf-8").splitlines() if l]

    def _replay(self, log) -> dict:
        # 前回作った局面を覚え、記録がその続きなら増えた分だけ足す（取り消しで変わったら最初から）。記録が正本なのは同じ
        cached = getattr(self, "_cache", None)
        if cached and len(log) >= len(cached[0]) and log[:len(cached[0])] == cached[0]:
            start, s = len(cached[0]), cached[1]
        else:
            start, s = 0, initial_state(self.defn, self.meta.get("start") == BOX)
        for i, op in enumerate(log[start:], start + 1):
            s = apply_op(self.defn, s, op, self.meta["seed"], i)
        self._cache = (list(log), s)
        return copy.deepcopy(s)  # 呼ぶ側が書き換えても覚えた局面は変わらない

    def state(self) -> dict:
        return self._replay(self.log())

    def apply(self, op: dict) -> dict:
        op = {**op, "time": op.get("time") or datetime.now(timezone.utc).isoformat(timespec="seconds")}
        # 画面と bg op が同じ対局に同時に書いても、古い局面に対して受け付けないように読む・足すを 1 つにする
        with (self.dir / "log.jsonl").open("a", encoding="utf-8") as f:
            fcntl.flock(f, fcntl.LOCK_EX)
            self._check_actor(op.get("by"))
            log = self.log()
            st, seq = self._replay(log), len(log) + 1
            pre = F.advance_warnings(self.defn, st.get("flow")) if op.get("op") == "advance" else []
            if op.get("op") == "advance" and st.get("stack"):  # 解決待ちがあるうちは進めない（応じる機会が消える）
                pre.append("スタックに解決待ちがある（見送るか解決してから進める）")
            if op.get("op") == "advance" and op.get("by") in self.defn.players and op["by"] != (st.get("flow") or {}).get("active"):
                pre.append(f"{op['by']} の手番ではない（進めるのは手番の人かキーパー）")
            if op.get("op") in ("say", "answer"):
                pre += F.talk_warnings(self.defn, st, op)
            if op.get("op") == "say" and op.get("to") is not None and F.whispers_hidden(self.defn, st):
                op = {**op, "hidden": True}
            if op.get("op") in ("say", "answer") and "n" not in op:  # 発言の番号は取り消しても使い回さない（覚えた番号で別の提案を受けないように）
                op["n"] = (f"h{self.meta.get('hidden_next', 0)}" if op.get("hidden")  # 見せない内緒話は別の番号（通し番号の欠けで件数が分からないように）
                           else max(self.meta.get("talk_next", 0), next_talk_n(st.get("talk") or [])))
            op = _resolve_selector(self.defn, st, op, self.meta["seed"], seq)  # 記録には top:deck ではなく、実際に動かした部品の ID を残す
            s = apply_op(self.defn, st, op, self.meta["seed"], seq)
            w = pre + warnings(self.defn, s, op)
            if op.get("op") == "say" and op.get("offer") and op.get("by") in self.defn.players:  # 提案者の側が今は出せないなら知らせる（自分の持ち物だけ）
                tmp = st
                for k, o in enumerate(op["offer"]):
                    if o.get("op") == "move" and _owner_at(self.defn, o.get("from") or locate(tmp, o.get("obj")) or "", tmp) == op["by"]:
                        try:
                            tmp = apply_op(self.defn, tmp, {"by": op["by"], **o}, self.meta["seed"], f"{seq}.{k}")
                        except OpError as e:
                            w.append(f"今のあなたの持ち物では出せない：{e}")
            if op.get("op") == "answer" and op.get("accept"):  # 提案に指定したアクションの手番・条件（交換は手番の人と、など）
                i = talk_index(st.get("talk") or [], op.get("talk"))
                t = st["talk"][i] if i is not None else {}
                if t.get("action"):
                    from .query import check_action
                    a = next(x for x in self.defn.data["actions"] if x["id"] == t["action"])
                    w += F.classify(self.defn, st.get("flow"), t["action"], t["by"])[1]
                    w += check_action(self.defn, st, a, {"actor": t["by"], "player": t["by"]})
            if op.get("op") == "answer" and op.get("accept"):  # 受けた提案の中身（置き場の上限など）
                w += [x for o in s["talk"][talk_index(s["talk"], op["talk"])]["offer"] for x in warnings(self.defn, s, o)]
            if self.meta.get("strict") and w:
                raise OpError("厳格モードで受け付けない：" + "／".join(w))
            f.write(json.dumps(op, ensure_ascii=False) + "\n")
            end = self._auto_end(st, s)
            if end:
                s = apply_op(self.defn, s, end, self.meta["seed"], seq + 1)
                f.write(json.dumps(end, ensure_ascii=False) + "\n")
            if "n" in op and op.get("op") in ("say", "answer"):  # 受け付けた番号だけを使い切りにする
                if isinstance(op["n"], str):
                    self.meta["hidden_next"] = int(op["n"][1:]) + 1
                else:
                    self.meta["talk_next"] = op["n"] + 1
                (self.dir / "session.yaml").write_text(yaml.safe_dump(self.meta, allow_unicode=True, sort_keys=False), encoding="utf-8")
        self.last_warnings = w
        return s
