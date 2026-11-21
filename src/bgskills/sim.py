"""でたらめに進める道具：でたらめ実行（bg fuzz）・でたらめの対戦（bg selfplay）・理解の小テスト（bg quiz）。
作品専用のボットを持たず、定義の進行と条件だけで手を選ぶ（RUL-016）。"""
from __future__ import annotations


def choose_args(s, rnd, action: dict, actor: str, prefer=lambda c: not c["problems"], fallback: bool = True) -> dict:
    """アクションの引数をでたらめに選ぶ（fuzz・selfplay・quiz で共通）。prefer を満たす候補から選び、無ければ fallback なら
    どの候補でも。先頭を選ぶ引数（pick: first）は、エンジンと同じく条件を満たす最初の候補にする（後の引数の条件が読むため）。
    自由に書く値（free）は選ばない。選べる候補が無ければ OpError。"""
    from .query import candidates
    from .session import OpError
    args = {}
    for prm in action.get("params") or []:
        if prm.get("free"):
            continue
        cs = candidates(s.defn, s.state(), action["id"], actor, prm["name"], args)
        if prm.get("pick") == "first":
            ok = [c["id"] for c in cs if not c["problems"]]
            if not ok:
                raise OpError(f"{prm['name']} の候補がない")
            args[prm["name"]] = ok[0]
            continue
        pool = [c["id"] for c in cs if prefer(c)] or ([c["id"] for c in cs] if fallback else [])
        if not pool:
            raise OpError(f"{prm['name']} の候補がない")
        args[prm["name"]] = rnd.choice(pool)
    return args


def _pick(s, rnd, acts):
    """でたらめ実行の 1 手：8 割は、進行の上で今行えるアクションと行う人の組から選ぶ（手番の人・解決待ちに応じる人・
    手番のない段階ならキーパーと各プレイヤー）。残りは、どのアクションでも誰でも（断られる行為も試す）。"""
    from .flow import available
    st = s.state()
    f = st.get("flow")
    ids = {a["id"]: a for a in acts}
    if f and rnd.random() < 0.8:
        if st.get("stack"):
            who = list(s.defn.players)
        elif f.get("active"):
            who = [f["active"]]
        else:
            who = ["keeper"] + list(s.defn.players)
        pairs = [(i, w) for w in who for xs in available(s.defn, f, w).values() for i in xs if i in ids]
        pairs = [(i, w) for i, w in pairs if not ids[i].get("by") or w in ids[i]["by"]]
        if pairs:
            i, w = rnd.choice(pairs)
            return ids[i], w
    a = rnd.choice(acts)
    return a, rnd.choice(a.get("by") or list(s.defn.players))


def fuzz(path, players: int, games: int = 3, steps: int = 80, seed: int = 0, variants=None) -> dict:
    """でたらめ実行：アクションと引数をでたらめに選んで行い、局面・見え方・指標・知らせを作る。
    受け付けない（OpError）のは普通。式の誤り（定義の誤り）と、それ以外の例外（エンジンの不具合）を集める。"""
    import json
    import random
    import tempfile
    from pathlib import Path
    import traceback
    from collections import Counter
    from .expr import ExprError
    from .flow import end_signals
    from .metrics import compute
    from .session import OpError, Session
    from .view import view
    done, refused, expr_errors, crashes = Counter(), Counter(), {}, {}
    for g in range(games):
        rnd = random.Random(f"{seed}:{g}")
        # 厳格モード：条件・進行から外れた行為は手順の前に断る（手順の式の誤りは、行えるはずの局面で起きたものだけになる）
        s = Session.create(Path(tempfile.mkdtemp()) / "s", path, players, {}, seed + g, strict=True, variants=variants)
        # 対局を終える手順（op: end）のあるアクションは、でたらめに選ぶとすぐ終わるので最後の 1 割だけ
        ends = {a["id"] for a in s.defn.data.get("actions") or [] if '"op": "end"' in json.dumps(a.get("steps"))}
        acts_all = s.defn.data.get("actions") or []
        who = list(s.defn.players) + ["keeper"]
        for k in range(steps if acts_all else 0):
            if s.state()["result"] is not None:
                break
            if s.state().get("stack") and rnd.random() < 0.5:  # スタックがあれば、半分は見送る（解決を進める）
                try:
                    s.apply({"op": "pass", "by": rnd.choice(list(s.defn.players))})
                    done["(pass)"] += 1
                except OpError:
                    pass
                continue
            f = s.state().get("flow")
            if f and rnd.random() < 0.15:  # ときどき進行を進める。手番のある段階ではフェーズ・手番だけ（段階ごと飛ばすと、その先を試せない）
                try:
                    s.apply({"op": "advance", "by": "keeper", "to": rnd.choice(["phase", "phase", "turn"]) if f.get("active") else "stage"})
                    done["(advance)"] += 1
                except OpError:
                    pass
                continue
            acts = [x for x in acts_all if x["id"] not in ends or k >= steps * 0.9]
            a, by = _pick(s, rnd, acts)
            try:
                s.act(a["id"], by, choose_args(s, rnd, a, by))
                done[a["id"]] += 1
                st = s.state()
                view(s.defn, st, rnd.choice(who[:-1]))
                compute(s.defn, st, None)
                for key in ("end_when", "signals"):
                    for x in end_signals(s.defn, st, key):
                        if x.startswith("式を計算できない"):
                            expr_errors.setdefault(x, a["id"])
            except ExprError as e:
                expr_errors.setdefault(str(e), a["id"])
            except OpError as e:
                (expr_errors.setdefault(str(e), a["id"]) if "式の評価に失敗" in str(e) else None)
                refused[a["id"]] += 1
            except Exception as e:  # noqa: BLE001（エンジンの不具合として集める）
                crashes.setdefault(f"{a['id']}: {type(e).__name__}: {e}", traceback.format_exc(limit=3)[-600:])
    never = [a["id"] for a in s.defn.data.get("actions") or [] if not done[a["id"]]] if games else []
    return {"done": dict(done), "refused": dict(refused), "never_done": never,
            "expr_errors": [{"error": k, "action": v} for k, v in expr_errors.items()],
            "crashes": [{"error": k, "trace": v} for k, v in crashes.items()]}


def random_step(s, rnd, staged: dict, max_turns: int = 60) -> str | None:
    """でたらめの 1 歩（selfplay・quiz で使う）：手番の人が今行える手から、条件を満たす候補で選んで行う。
    行えるものがなければ進行を進める。スタックがあれば見送る。終わったら終わり方の文を返す（続くなら None）。"""
    from .flow import available, end_signals
    from .session import OpError, _stack_next
    st = s.state()
    if st["result"] is not None:  # 自動で終わった（flow.auto_end）・終わらせるアクション
        r = st["result"]
        return r.get("text") or "・".join(f"{p}:{v}" for p, v in (r.get("results") or {}).items())
    sig = end_signals(s.defn, st)
    if sig and not (s.defn.data.get("flow") or {}).get("auto_end"):  # 自動で終える定義は、時機（巡の終わりなど）を待って結果が記録されるまで進める
        return sig[0]
    f = st.get("flow") or {}
    if f.get("turn_no", 0) > max_turns or not f.get("stage"):
        return "決着なし"
    if st.get("stack"):  # 見送り待ちの人が見送る（応じる手は打たない）
        nxt = _stack_next(s.defn, st)["by"]
        waiting = [p for p in s.defn.players if p != nxt and p not in (st.get("stack_passes") or [])]
        s.apply({"op": "pass", "by": waiting[0]}) if waiting else s.apply({"op": "resolve", "by": "keeper"})
        return None
    acts = {a["id"]: a for a in s.defn.data.get("actions") or []}
    who = f.get("active") or "keeper"
    av = available(s.defn, f, who)
    stage_done = staged.setdefault(f.get("stage"), set())  # 手番のない段階（準備）のアクションは 1 人 1 回ずつ
    if f.get("active"):
        pairs = [(i, who) for k in ("main", "free") for i in av.get(k, [])]
    else:  # 手番のない段階（準備・人狼の昼夜）：キーパーと各プレイヤーを、行う人として試す
        pairs = [(i, p) for p in ["keeper"] + list(s.defn.players)
                 for i in available(s.defn, f, p).get("stage", []) if (i, p) not in stage_done]
    pairs = [(i, p) for i, p in pairs if "'op': 'end'" not in str(acts[i].get("steps"))]
    for aid, actor in [x for x in rnd.sample(pairs, len(pairs)) for _ in range(6)]:  # 引数の選び直しも試す
        try:
            s.act(aid, actor, choose_args(s, rnd, acts[aid], actor, fallback=False))
            if not f.get("active"):
                stage_done.add((aid, actor))
            return None
        except OpError:
            continue
    for to in (("phase", "turn", "stage") if f.get("active") else ("stage", "phase")):  # 次のフェイズへ（手番ごと飛ばすとメインフェイズに入らない作品がある）
        try:
            s.apply({"op": "advance", "by": "keeper", "to": to})
            return None
        except OpError:
            continue
    return "進められない"


def selfplay(path, players: int, games: int = 20, max_turns: int = 60, seed: int = 0, variants=None) -> dict:
    """作品を問わない対戦（バランスの目安）：random_step を終わるまで繰り返し、終わり方ごとに数える。
    作品専用のボットより弱く、強い手を選ばない（偏りの目安で、強さの比較ではない）。"""
    import random
    import tempfile
    from collections import Counter
    from pathlib import Path
    from .session import Session
    outcomes, turns, seats = Counter(), [], {}
    for g in range(games):
        rnd = random.Random(f"{seed}:{g}")
        s = Session.create(Path(tempfile.mkdtemp()) / "s", path, players, {}, seed + g, strict=True, variants=variants)
        if not (s.defn.data.get("flow") or {}).get("stages"):
            return {"error": "進行（flow）のない定義は、手番の人が分からないので selfplay できない"}
        staged, result = {}, None
        for _ in range(max_turns * 30):
            result = random_step(s, rnd, staged, max_turns)
            if result:
                break
        outcomes[result or "打ち切り"] += 1
        st = s.state()
        turns.append((st.get("flow") or {}).get("turn_no", 0))
        for p, r in ((st.get("result") or {}).get("results") or {}).items():  # 席ごとの勝ち・負け・引き分け（先手の有利の目安）
            seats.setdefault(p, Counter())[r] += 1
    out = {"games": games, "outcomes": dict(outcomes.most_common()), "avg_turns": round(sum(turns) / max(1, len(turns)), 1)}
    if seats:
        out["seats"] = {p: dict(c) for p, c in seats.items()}
        out["win_rate"] = {p: round(c.get("win", 0) / games, 2) for p, c in seats.items()}
    return out


def quiz(path, players: int, n: int = 20, seed: int = 0, out=None) -> dict:
    """ルールの理解の小テスト：でたらめに進めた局面で「Pn は今、このアクションをこの引数で行えるか」を問う。
    正解はエンジン（厳格モード）の判定。問題ごとに局面を写した対局のフォルダを作る（bg show --as で見て答える。
    bg candidates は答えそのものなので使わせない）。答えは answers.yaml に分けて書く。"""
    import random
    import shutil
    import tempfile
    from pathlib import Path
    import yaml as _yaml
    from .session import OpError, Session
    out = Path(out or tempfile.mkdtemp())
    out.mkdir(parents=True, exist_ok=True)
    rnd = random.Random(seed)
    qs, answers = [], {}
    g = 0
    while len(qs) < n and g < n * 12:
        g += 1
        s = Session.create(out / f"_base{g}", path, players, {}, seed * 1000 + g, strict=True)
        acts = s.defn.data.get("actions") or []
        staged = {}
        for _ in range(rnd.randint(3, 120)):  # でたらめに進める（selfplay と同じ 1 歩）
            if random_step(s, rnd, staged):
                break
        fl = s.state().get("flow") or {}
        if s.state()["result"] is not None or (s.defn.data.get("flow") and not fl.get("stage")):
            continue  # 終わった局面・進行が終わった局面は問いにしない（答えがみな「行えない」になる）
        # 問い：プレイヤーのアクションと引数（行える問いと行えない問いを半々に）
        pa = [a for a in acts if "keeper" not in (a.get("by") or [])]
        if not pa:
            break
        okish = sum(v["answer"] == "yes" for v in answers.values()) < n / 2 and rnd.random() < 0.7
        act_now = fl.get("active")
        who = act_now if act_now and rnd.random() < 0.7 else rnd.choice(list(s.defn.players))  # 手番の人に寄せる（易しい問いを減らす）
        if okish and fl:  # 行えそうな問い：進行の上で今行えるアクションから選ぶ
            from .flow import available
            av = available(s.defn, fl, who)
            ids = {i for k in ("main", "free", "reaction", "stage") for i in av.get(k, [])}
            pa = [a for a in pa if a["id"] in ids] or pa
        a = rnd.choice(pa)
        try:
            args = choose_args(s, rnd, a, who, prefer=lambda c: bool(c["problems"]) != okish)
        except (OpError, ValueError):
            continue
        qid = f"q{len(qs) + 1:02d}"
        trial = out / f"_trial_{qid}"
        shutil.copytree(s.dir, trial)
        try:
            Session(trial).act(a["id"], who, args)
            truth, why = True, ""
        except OpError as e:
            truth, why = False, str(e).replace("厳格モードで受け付けない：", "")
        shutil.rmtree(trial)
        yes = sum(v["answer"] == "yes" for v in answers.values())
        if (truth and yes >= (n + 1) // 2) or (not truth and len(answers) - yes >= n // 2 + (n % 2 == 0 and 0)):
            if g < n * 8:  # 片方に偏ったら捨てて作り直す（作り直しが尽きたら偏りを受け入れる）
                continue
        qdir = out / qid
        shutil.copytree(s.dir, qdir)
        (qdir / "usage.jsonl").unlink(missing_ok=True)
        qs.append({"id": qid, "session": str(qdir), "as": who, "action": a["id"], "args": args,
                   "question": f"{who} は今、{a.get('name', a['id'])}（{a['id']}）を {args or '引数なし'} で行えるか（yes/no と理由）"})
        answers[qid] = {"answer": "yes" if truth else "no", "why": why}
    for p in out.glob("_base*"):
        shutil.rmtree(p)
    (out / "quiz.yaml").write_text(_yaml.safe_dump({"definition": str(path), "questions": qs}, allow_unicode=True, sort_keys=False), encoding="utf-8")
    (out / "answers.yaml").write_text(_yaml.safe_dump(answers, allow_unicode=True, sort_keys=False), encoding="utf-8")
    return {"out": str(out), "questions": len(qs), "yes": sum(v["answer"] == "yes" for v in answers.values())}


def quiz_grade(answers_path, responses_path) -> dict:
    """小テストの採点。responses は {qid: yes|no}（または {qid: {answer: yes|no}}）。"""
    import yaml as _yaml
    ans = _yaml.safe_load(open(answers_path, encoding="utf-8"))
    res = _yaml.safe_load(open(responses_path, encoding="utf-8")) or {}
    wrong = []
    for q, a in ans.items():
        r = res.get(q)
        r = (r or {}).get("answer") if isinstance(r, dict) else r
        r = {True: "yes", False: "no"}.get(r, r) if isinstance(r, bool) else r  # YAML の yes/no は真偽値になる
        if str(r).strip().lower() != a["answer"]:
            wrong.append({"id": q, "expected": a["answer"], "got": r, "why": a["why"]})
    return {"questions": len(ans), "correct": len(ans) - len(wrong), "accuracy": round((len(ans) - len(wrong)) / max(1, len(ans)), 3),
            "wrong": wrong}
