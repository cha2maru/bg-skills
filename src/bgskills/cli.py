"""bg コマンド：スキルから呼ぶスクリプト（SPC-003・006・010・014〜019・022）。結果は YAML で標準出力に出す。"""
from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from pathlib import Path

import yaml

from .definition import load
from .session import OpError, Session
from .tools import check_refs, diff, dump, rules_referencing
from .view import view


def _out(data):
    sys.stdout.write(dump(data))


def stats(sessions: list[Session]) -> dict:
    """席ごとの勝敗・使われなかったルール・対局ごとの操作数（SPC-022）。"""
    tally, used, ops = {}, set(), {}
    rules = set()
    for s in sessions:
        log = s.log()
        rules |= set(s.defn.rules)
        used |= {o.get("rule") for o in log if o.get("rule")}
        for o in log:
            used |= set(o.get("rules") or [])
        ops[s.dir.name] = len(log)
        res = s.state()["result"]
        for seat, r in ((res or {}).get("results") or {}).items():
            tally.setdefault(seat, Counter())[r] += 1
    return {"sessions": len(sessions), "results": {k: dict(v) for k, v in sorted(tally.items())},
            "unused_rules": sorted(rules - used), "ops": ops}



def _group(items):
    """同じ種類・名前・状態で、上に何もない部品を「名前 ×n（ID の範囲）」にまとめる。"""
    out, seen = [], {}
    for it in items:
        if "id" in it and "count" not in it and not it.get("stacked") and not it.get("attached"):
            key = (it.get("kind"), it.get("title"), it.get("owner"), json.dumps([it.get("state"), it.get("attributes")], sort_keys=True))
            if key in seen:
                g = seen[key]
                g["count"] = g.get("count", 1) + 1
                g["ids"].append(it["id"])
                continue
            g = {**it, "ids": [it["id"]]}
            seen[key] = g
            out.append(g)
        else:
            out.append(it)
    def slim(x):  # 既定の表示（回転 0・表）と、局面の持ち主の重複・画像は省く
        if x.get("display") == {"rotate": 0, "face": "up"}:
            x.pop("display")
        x.pop("image", None)
        x.pop("shape", None)
        x.pop("back_image", None)
        for y in x.get("stacked") or []:
            slim(y)
    for g in out:
        slim(g)
        if "ids" in g:
            if len(g["ids"]) == 1:
                g.pop("ids")
            else:
                g.pop("id", None)  # ID は全部並べる（2 枚目以降を選ぶのに candidates を引かずに済む）
    return out


TALK_TAIL = 10


def _title(d, i):
    x = d.parts.get(i) or d.areas.get(i)
    return x and ((x.get("attributes") or {}).get("title") or x.get("name"))


from .redact import visible_log, visible_ops as _visible_ops  # noqa: E402（伏せる処理は redact に 1 か所）


def main(argv=None):
    p = argparse.ArgumentParser(prog="bg", description="ボードゲームの定義と対局を扱う")
    sub = p.add_subparsers(dest="cmd", required=True)
    c = sub.add_parser("check", help="参照先が存在するかを確かめる")
    c.add_argument("definition")
    c.add_argument("--with", dest="variants", action="append", default=[], help="案（定義の断片）を重ねる。何枚でも、順に（CTR-F-007）")
    c = sub.add_parser("expand", help="略記を展開した形を出す")
    c.add_argument("definition")
    c.add_argument("--players", type=int)
    c = sub.add_parser("refs", help="ID を参照するルールを引く")
    c.add_argument("definition")
    c.add_argument("id")
    c = sub.add_parser("diff", help="2 つの版の違い")
    c.add_argument("old")
    c.add_argument("new")
    c = sub.add_parser("new", help="対局を作る")
    c.add_argument("session")
    c.add_argument("--def", dest="definition", required=True)
    c.add_argument("--players", type=int, required=True)
    c.add_argument("--seat", action="append", default=[], help="P1=agent:a のように席と着席者")
    c.add_argument("--seed", type=int, default=0)
    c.add_argument("--from-box", action="store_true", help="すべての部品が箱に入った状態から始める（準備の手順を確かめる）")
    c.add_argument("--with", dest="variants", action="append", default=[], help="案（定義の断片）を重ねる。何枚でも、順に（CTR-F-007）")
    c.add_argument("--strict", action="store_true", default=None, help="厳格モード：条件・進行から外れた行為を受け付けない（省くと定義の game.strict）")
    c.add_argument("--lenient", dest="strict", action="store_false", help="定義が厳格を既定にしていても、警告だけにする（試し遊び・キーパーの手直し）")
    c.set_defaults(strict=None)
    c.add_argument("--scenario", help="対局ごとの非公開の設定（脚本など）。対局のフォルダに写す")
    c = sub.add_parser("setup-check", help="局面を定義の初期の置き場と比べる")
    c.add_argument("session")
    c = sub.add_parser("op", help="操作を 1 つ行い記録する。JSON で渡す")
    c.add_argument("session")
    c.add_argument("json", help='例: {"op":"move","obj":"N4","to":"discard","by":"P2","rule":"R4"}')
    c = sub.add_parser("act", help="定義のアクションを行う（手順をすべて行うか、1 つも行わない）")
    c.add_argument("session")
    c.add_argument("action")
    c.add_argument("--by", help="行う人（プレイヤー）。キーパーだけが行うアクションなら省ける")
    c.add_argument("--arg", action="append", default=[], help="card=W5-2 のように選ぶもの")
    c = sub.add_parser("advance", help="進行を次へ（フェーズ・手番・段階）。ワザを使わずに手番を終えるときなど")
    c.add_argument("session")
    c.add_argument("--to", default="phase", choices=["phase", "turn", "stage"])
    c.add_argument("--by", default="keeper")
    c = sub.add_parser("say", help="発言する（記録に残る。--to で聞かせる相手を絞る＝内緒話）")
    c.add_argument("session")
    c.add_argument("text")
    c.add_argument("--by", required=True, help="話す人（プレイヤーか keeper）")
    c.add_argument("--to", help="聞かせる相手（カンマ区切り）。省くと全員")
    c.add_argument("--offer", help='提案（守られる約束）：受けたらまとめて行う操作の JSON のリスト。例 \'[{"op":"move","obj":"wood","from":"hand-P1","to":"hand-P2","n":2}]\'')
    c.add_argument("--reply-to", type=int, help="条件を変えて返す元の提案（発言の番号）。元の提案は閉じる")
    c.add_argument("--action", help="提案が成立したら、出した人がこのアクションを行ったことにする（手番・回数・条件を確かめる。省くと flow.offer_action）")
    c = sub.add_parser("answer", help="提案に答える（受けると中身をすべて行う。出した人が --decline すると取り下げ）")
    c.add_argument("session")
    c.add_argument("talk", type=lambda x: int(x) if x.isdigit() else x, help="提案の発言の番号（bg show の talk の n。夜の内緒話は h0 など）")
    c.add_argument("--by", required=True)
    c.add_argument("--decline", action="store_true", help="断る（出した人なら取り下げる）")
    c = sub.add_parser("show", help="局面を出す")
    c.add_argument("session")
    c.add_argument("--as", dest="player", help="このプレイヤーの見え方（省略時はキーパー）")
    c.add_argument("--meaning", action="store_true", help="意味の文と関係するルールを添える")
    c.add_argument("--compact", action="store_true", help="空のエリアを省く")
    c.add_argument("--links", action="store_true", help="各エリアのリンク（つながる先と種類）を添える")
    c.add_argument("--only", help="出すエリア（子のエリアも）と局面の部分（talk・flow・metrics・progress・offers_for_me・catalog など）をカンマ区切りで")
    c.add_argument("--talk-since", type=int, help="この番号からの発言だけ出す（--compact の既定は最後の 10 件と受付中の提案）")
    c = sub.add_parser("log", help="操作の記録")
    c.add_argument("session")
    c.add_argument("--as", dest="player", help="このプレイヤーから見えない部品の ID を伏せる")
    c = sub.add_parser("near", help="エリアのリンク先と、その中身")
    c.add_argument("session")
    c.add_argument("id")
    c.add_argument("--type", help="リンクの種類で絞る")
    c.add_argument("--as", dest="player")
    c = sub.add_parser("candidates", help="アクションの引数の候補と、条件を満たすか")
    c.add_argument("session")
    c.add_argument("action")
    c.add_argument("--by", required=True)
    c.add_argument("--param", help="省くと全部の引数")
    c.add_argument("--arg", action="append", default=[], help="先に決めた引数（char=C01 など）")
    c = sub.add_parser("rulings", help="定義の裁定（決まった・未決・一般の原則）と、対局中の裁定のうち定義に持ち帰る候補")
    c.add_argument("target", help="定義のファイルか対局のフォルダ")
    c = sub.add_parser("schema", help="ゲーム定義の形式（JSON Schema）を書き出す。エディタの補完・エージェントの読み物（正本は src/bgskills/schema.py）")
    c = sub.add_parser("quiz", help="ルールの理解の小テストを作る（局面ごとに「行えるか」。正解はエンジンの判定。answers.yaml は別）")
    c.add_argument("definition")
    c.add_argument("--players", type=int, required=True)
    c.add_argument("--n", type=int, default=20)
    c.add_argument("--seed", type=int, default=0)
    c.add_argument("--out", required=True)
    c = sub.add_parser("quiz-grade", help="小テストを採点する（answers.yaml と、{問の id: yes|no} の答え）")
    c.add_argument("answers")
    c.add_argument("responses")
    c = sub.add_parser("playstats", help="対局の物差し：コマンドの数・受け付けなかった数（拒否）・手番あたり（usage.jsonl と記録から）")
    c.add_argument("session")
    c = sub.add_parser("complexity", help="ルールの複雑さの目安（ルール・アクション・条件・式の大きさ・機械で確かめないルール）")
    c.add_argument("definition")
    c.add_argument("--players", type=int)
    c.add_argument("--with", dest="variants", action="append", default=[], help="案（定義の断片）を重ねる。何枚でも、順に（CTR-F-007）")
    c = sub.add_parser("selfplay", help="作品を問わないでたらめの対戦（今行える手から選ぶ）で、終わり方の偏りと局の長さの目安を出す")
    c.add_argument("definition")
    c.add_argument("--players", type=int, required=True)
    c.add_argument("--games", type=int, default=20)
    c.add_argument("--max-turns", type=int, default=60)
    c.add_argument("--seed", type=int, default=0)
    c.add_argument("--with", dest="variants", action="append", default=[], help="案（定義の断片）を重ねる。何枚でも、順に（CTR-F-007）")
    c.add_argument("--record", help="試行の記録（experiments.jsonl）に 1 行足す")
    c.add_argument("--note", help="試行の記録への書き添え")
    c = sub.add_parser("compare", help="元の定義と案を同じ条件で多数局回し、終わり方と長さを並べる（第二版）")
    c.add_argument("definition")
    c.add_argument("--variant", action="append", default=[], help="名前=案のファイル（何個でも）")
    c.add_argument("--players", type=int, required=True)
    c.add_argument("--games", type=int, default=20)
    c.add_argument("--max-turns", type=int, default=60)
    c.add_argument("--seed", type=int, default=0)
    c.add_argument("--with", dest="variants", action="append", default=[], help="案（定義の断片）を重ねる。何枚でも、順に（CTR-F-007）")
    c.add_argument("--record", help="試行の記録（experiments.jsonl）に 1 行足す")
    c.add_argument("--note", help="試行の記録への書き添え")
    c = sub.add_parser("league", help="思考ルーチンどうしを、席を回して多数局戦わせる（RUL-030）")
    c.add_argument("definition")
    c.add_argument("--bot", action="append", default=[], help="名前=ファイル（choose(ctx) を持つ Python）か random。2 つ以上")
    c.add_argument("--players", type=int, required=True)
    c.add_argument("--games", type=int, default=10, help="種の数（それぞれ方針の数だけ席を回す）")
    c.add_argument("--max-turns", type=int, default=80)
    c.add_argument("--seed", type=int, default=0)
    c.add_argument("--with", dest="variants", action="append", default=[], help="案を重ねる")
    c.add_argument("--record", help="試行の記録（experiments.jsonl）に 1 行足す")
    c.add_argument("--note", help="試行の記録への書き添え")
    c.add_argument("--trace", help="判断の記録（1 行 1 手）を書き出す")
    c = sub.add_parser("bot-step", help="人か Claude の席の番が来るか対局が終わるまで、ほかの席を思考ルーチンで進める（記録に足す。SPC-084）")
    c.add_argument("session")
    c.add_argument("--human", action="append", default=[], help="人か Claude が遊ぶ席（何度でも）。この席の番が来たら止まる")
    c.add_argument("--bot", action="append", default=[], help="席=ファイル（choose(ctx) を持つ Python）か 席=random。書かない席はでたらめ")
    c.add_argument("--max", type=int, default=500, help="足す手の上限（キーパーの準備・進行も 1 手と数える）")
    c = sub.add_parser("experiments", help="試行の記録を新しい順に出す")
    c.add_argument("log")
    c.add_argument("--last", type=int)
    c = sub.add_parser("init", help="ゲームの作業場（定義の雛形・案・試行の記録・設計の日誌）を作る（第二版）")
    c.add_argument("folder")
    c.add_argument("--name")
    c.add_argument("--players", default="2-4", help="人数（2-4 のように）")
    c = sub.add_parser("status", help="設計の状態：版・ルール・決まっていないこと・機械の層・最近の試行")
    c.add_argument("definition")
    c.add_argument("--players", type=int)
    c.add_argument("--experiments", help="試行の記録（experiments.jsonl）")
    c.add_argument("--with", dest="variants", action="append", default=[], help="案（定義の断片）を重ねる。何枚でも、順に（CTR-F-007）")
    c = sub.add_parser("rulebook", help="人が読む手引き（Markdown）を書き出す。詳細ルールと未決の裁定は出さない")
    c.add_argument("definition")
    c.add_argument("--players", type=int)
    c.add_argument("--with", dest="variants", action="append", default=[], help="案（定義の断片）を重ねる。何枚でも、順に（CTR-F-007）")
    c = sub.add_parser("pass", help="スタックの解決を見送る（積んだ人以外の全員が見送ると一番上を解決する）")
    c.add_argument("session")
    c.add_argument("--by", required=True)
    c = sub.add_parser("resolve", help="スタックの一番上を解決する（キーパー。見送りを待たない）")
    c.add_argument("session")
    c.add_argument("--by", default="keeper")
    c = sub.add_parser("fuzz", help="でたらめ実行：アクションと引数をでたらめに選んで、式の誤り・エンジンの不具合・一度も行えないアクションを探す")
    c.add_argument("definition")
    c.add_argument("--players", type=int, required=True)
    c.add_argument("--games", type=int, default=3)
    c.add_argument("--steps", type=int, default=80)
    c.add_argument("--seed", type=int, default=0)
    c.add_argument("--with", dest="variants", action="append", default=[], help="案（定義の断片）を重ねる。何枚でも、順に（CTR-F-007）")
    c = sub.add_parser("rebase", help="定義を直した後、記録が今の定義で再生できるか確かめ、対局を今の定義に合わせる")
    c.add_argument("session")
    c = sub.add_parser("undo", help="最後の操作（アクションならその全部）を取り消す")
    c.add_argument("session")
    c = sub.add_parser("serve", help="対局を画面で見て、さわる（http://127.0.0.1:8765/）")
    c.add_argument("session")
    c.add_argument("--host", default="127.0.0.1")
    c.add_argument("--port", type=int, default=8765)
    c = sub.add_parser("tts", help="局面を Tabletop Simulator の Saved Object（JSON）に書き出す")
    c.add_argument("session")
    c.add_argument("--out", required=True, help="例: .../Tabletop Simulator/Saves/Saved Objects/kagaribi.json")
    c = sub.add_parser("stats", help="対局の記録を集計する")
    c.add_argument("sessions", nargs="+")
    a = p.parse_args(argv)
    try:
        if a.cmd == "check":
            d = load(a.definition, None, None, a.variants)
            bad = check_refs(d)
            opens = [r["id"] for r in d.data.get("rulings") or [] if r.get("status") == "open"]
            from .tools import check_wording
            wording = check_wording(d)  # 用語の表記（使わない言葉）。知らせで、誤りではない（RUL-029）
            _out({"missing_refs": bad, **({"open_rulings": opens} if opens else {}), **({"wording": wording} if wording else {})})  # 未決の裁定＝分かっている穴（誤りではない）
            return 1 if bad else 0
        if a.cmd == "expand":
            _out(load(a.definition, a.players).data)
        elif a.cmd == "refs":
            _out({a.id: rules_referencing(load(a.definition), a.id)})
        elif a.cmd == "diff":
            _out(diff(load(a.old), load(a.new)))
        elif a.cmd == "new":
            seats = dict(s.split("=", 1) for s in a.seat)
            s = Session.create(a.session, a.definition, a.players, seats, a.seed, a.from_box, a.strict, a.scenario, a.variants)
            _out({"session": str(s.dir), **s.meta})
        elif a.cmd == "op":
            s = Session(a.session)
            st = s.apply(json.loads(a.json))
            from .flow import summary
            fl = summary(s.defn, st.get("flow"), None)
            _out({"ok": True, "seq": len(s.log()), **({"warnings": s.last_warnings} if s.last_warnings else {}), **({"flow": fl} if fl else {})})
        elif a.cmd == "advance":
            s = Session(a.session)
            s.apply({"op": "advance", "to": a.to, "by": a.by})
            from .flow import summary
            _out({"ok": True, **({"warnings": s.last_warnings} if s.last_warnings else {}), "flow": summary(s.defn, s.state().get("flow"), None)})
        elif a.cmd == "say":
            s = Session(a.session)
            s.apply({"op": "say", "by": a.by, "text": a.text, **({"to": a.to.split(",")} if a.to else {}),
                     **({"offer": json.loads(a.offer)} if a.offer else {}), **({"reply_to": a.reply_to} if a.reply_to is not None else {}), **({"action": a.action} if a.action else {})})
            _out({"ok": True, "talk": s.state()["talk"][-1].get("n"), **({"warnings": s.last_warnings} if s.last_warnings else {})})
        elif a.cmd == "answer":
            s = Session(a.session)
            s.apply({"op": "answer", "by": a.by, "talk": a.talk, "accept": not a.decline})
            _out({"ok": True, **({"warnings": s.last_warnings} if s.last_warnings else {})})
        elif a.cmd == "setup-check":
            from .session import compare_to_start
            s = Session(a.session)
            _out(compare_to_start(s.defn, s.state()))
        elif a.cmd == "act":
            s = Session(a.session)
            if not a.by:  # キーパーだけが行うアクションなら --by を省ける
                act = next((x for x in s.defn.data.get("actions") or [] if x["id"] == a.action), {})
                if act.get("by") != ["keeper"]:
                    raise OpError("--by（行う人）がいる")
                a.by = "keeper"
            st = s.act(a.action, a.by, dict(x.split("=", 1) for x in a.arg))
            done = _visible_ops(s, st, s.last_ops, None if a.by == "keeper" else a.by)  # 結果（出目・引いたもの）を、行った人の見え方で返す
            from .flow import summary
            fl = summary(s.defn, st.get("flow"), a.by if a.by in s.defn.players else None)
            _out({"ok": True, "seq": len(s.log()), "done": done, **({"warnings": s.last_warnings} if s.last_warnings else {}),
                  **({"flow": fl} if fl else {})})
        elif a.cmd == "show":
            s = Session(a.session)
            v = view(s.defn, s.state(), a.player, a.meaning, s.meta["seats"])
            if a.links:
                from .query import neighbors
                for aid, e in v["areas"].items():
                    nb = neighbors(s.defn, aid)
                    if nb:
                        e["links"] = [f"{o}（{t}）" for o, t in nb]
            parts = None
            if a.only:
                want = [w for w in a.only.split(",") if w in s.defn.areas]
                parts = {w for w in a.only.split(",") if w not in s.defn.areas}  # 局面の部分（talk・flow など）
                bad = parts - set(v) - {"catalog", "offers_for_me", "talk_omitted", "talk", "flow", "metrics", "progress", "stack", "stack_waiting", "stack_done", "empty", "standings"}
                if bad:
                    raise OpError(f"--only の {', '.join(sorted(bad))} はエリアでも局面の部分でもない（部分：{', '.join(k for k in v if k not in ('for', 'game', 'version'))}）")
                under = lambda x: any(x == w or s.defn.parent.get(x) == w or s.defn.parent.get(s.defn.parent.get(x) or "") == w for w in want)
                if want:  # エリアを指定しなければ、ここでは絞らない（空のエリアの一覧などを作れるように。最後に areas ごと外す）
                    v["areas"] = {k: e for k, e in v["areas"].items() if under(k)}
            if a.compact:  # 空で子もリンクもないエリアを省き、同じ種類・状態の部品をまとめる
                empty = sorted(k for k, e in v["areas"].items() if e.get("shown") == [] and not e.get("children"))
                v["areas"] = {k: {**e, **({"shown": _group(e["shown"])} if isinstance(e.get("shown"), list) else {})}
                              for k, e in v["areas"].items() if e.get("shown") not in ([], None) or e.get("children")}
                if empty:
                    v["empty"] = empty  # 省いた空のエリア（空だと読めるように。見落としと区別する）
                for e in v["areas"].values():
                    e.pop("children", None)
                catalog = {}  # 表や一覧の属性（ワザの全文など）は、名前ごとに 1 回だけ catalog に出す

                def lift(x, parent_owner=None):
                    kind = x.get("kind")
                    if isinstance(x.get("state"), dict) and kind in s.defn.kinds:  # 表裏の項目が既定（最初に書いた値＝表）なら省く
                        faces, defs = s.defn.face_fields(kind), s.defn.states(kind)
                        x["state"] = {f: val for f, val in x["state"].items()
                                      if f not in faces or not isinstance(defs.get(f), dict) or val != next(iter(defs[f]), None)}
                        if not x["state"]:
                            x.pop("state")
                    if parent_owner and x.get("owner") == parent_owner:
                        x.pop("owner")  # 上に重ねた物の持ち主が、下の物と同じなら省く
                    big = {k: val for k, val in (x.get("attributes") or {}).items() if isinstance(val, (list, dict))}
                    if big:
                        catalog.setdefault(x.get("title") or x.get("kind"), big)
                        x["attributes"] = {k: val for k, val in x["attributes"].items() if k not in big}
                        if not x["attributes"]:
                            x.pop("attributes")
                    for y in x.get("stacked") or []:
                        lift(y, x.get("owner") or parent_owner)
                for e in v["areas"].values():
                    for x in e.get("shown") or [] if isinstance(e.get("shown"), list) else []:
                        lift(x)
                if catalog:
                    v["catalog"] = catalog
            if v.get("talk") and (a.compact or a.talk_since is not None):  # 発言が長い対局（人狼の議論）で毎回全件を出さない
                T = v["talk"]
                if a.talk_since is None:
                    start = max(0, len(T) - TALK_TAIL)
                else:  # 番号 N 以降（見せない内緒話の番号 hN は、並びの位置で含める）
                    start = next((i for i, t in enumerate(T) if isinstance(t.get("n", i), int) and t.get("n", i) >= a.talk_since), len(T))
                last_keeper = max((i for i, t in enumerate(v["talk"]) if t.get("by") in (None, "keeper")), default=None)  # 最後の告知（朝になった、など）は残す
                keep = [{"n": i, **t} for i, t in enumerate(T) if i >= start or t.get("status") == "open" or i == last_keeper]
                if len(keep) < len(v["talk"]):
                    v["talk_omitted"] = f"{len(v['talk']) - len(keep)} 件を省いた（--talk-since 0 で全件）"
                v["talk"] = keep
            if parts is not None:  # --only：頭（for・game・version）と、指定したエリア・部分だけ
                if "stack" in parts:
                    parts |= {"stack_waiting", "stack_done"}
                v = {k: x for k, x in v.items() if k in ("for", "game", "version") or k in parts
                     or (k == "areas" and (want or not parts)) or (k == "talk_omitted" and "talk" in parts)}
            _out(v)
        elif a.cmd == "log":
            s = Session(a.session)
            _out(visible_log(s, a.player))
        elif a.cmd == "near":
            from .query import neighbors
            s = Session(a.session)
            v = view(s.defn, s.state(), a.player)
            _out({a.id: [{"to": o, "type": t, "shown": (v["areas"].get(o) or {}).get("shown")} for o, t in neighbors(s.defn, a.id, a.type)]})
        elif a.cmd == "candidates":
            from .query import candidates, check_action
            from .redact import visible_candidates
            s = Session(a.session)
            act = next((x for x in s.defn.data.get("actions") or [] if x["id"] == a.action), None)
            if act is None:
                raise OpError(f"アクション {a.action} は定義にない")
            args = dict(x.split("=", 1) for x in a.arg)
            st = s.state()
            ap = check_action(s.defn, st, act, {"actor": a.by, "player": a.by, **args})
            names = [a.param] if a.param else [p["name"] for p in act.get("params") or [] if p["name"] not in args]
            if ap and a.by in s.defn.players:  # 行えない人には引数の条件を見せない（条件は隠れた情報を読むことがある：人狼の襲撃先）
                names = []
            out = {}
            acts = {x["id"]: x.get("name", x["id"]) for x in s.defn.data.get("actions") or []}
            stk = {str(e["n"]): f"{e['by']} の {acts.get(e['action'], e['action'])}" + (f"（{'・'.join(map(str, e['args'].values()))}）" if e["args"] else "")
                   for e in st.get("stack") or []}
            for n in names:  # 候補に名前（title）を添える。スタックの番号には、誰の何か
                out[n] = [{**c, **({"title": t} if (t := stk.get(c["id"]) or _title(s.defn, c["id"])) else {})}
                          for c in visible_candidates(s.defn, st, a.by, candidates(s.defn, st, a.action, a.by, n, args))]
                prm = next(p for p in act.get("params") or [] if p["name"] == n)
                if not out[n] and not prm.get("free"):
                    ap = ap + [f"{n} の候補がない"]
            _out({**out, "action_problems": ap})
        elif a.cmd in ("pass", "resolve"):
            s = Session(a.session)
            before = s.state()
            st = s.apply({"op": a.cmd, "by": getattr(a, "by", None) or "keeper"})
            if a.cmd == "pass" and len(st.get("stack_done") or []) == len(before.get("stack_done") or []):
                from .session import _stack_next
                if st.get("stack") and _stack_next(s.defn, st)["by"] == a.by:
                    s.last_warnings = (s.last_warnings or []) + ["積んだ本人なので、見送りは要らない（相手の見送りを待つ）"]
            _out({"ok": True, **({"warnings": s.last_warnings} if s.last_warnings else {}),
                  "stack": [{"n": e["n"], "action": e["action"], "by": e["by"]} for e in st.get("stack") or []],
                  **({"resolved": st["stack_done"][-1]} if a.cmd == "resolve" or not st.get("stack_passes") and st.get("stack_done") else {})})
        elif a.cmd == "rulings":
            from .tools import rulings_report
            if Path(a.target).is_dir():
                s = Session(a.target)
                _out(rulings_report(s.defn, s))
            else:
                _out(rulings_report(load(a.target)))
        elif a.cmd == "schema":
            from .schema import json_schema
            print(json.dumps(json_schema(), ensure_ascii=False, indent=1))
        elif a.cmd == "quiz":
            from .sim import quiz
            _out(quiz(a.definition, a.players, a.n, a.seed, a.out))
        elif a.cmd == "quiz-grade":
            from .sim import quiz_grade
            _out(quiz_grade(a.answers, a.responses))
        elif a.cmd == "playstats":
            from .measure import playstats
            _out(playstats(Session(a.session)))
        elif a.cmd == "complexity":
            from .measure import complexity
            _out(complexity(load(a.definition, a.players, None, a.variants)))
        elif a.cmd == "selfplay":
            from .sim import selfplay
            r = selfplay(a.definition, a.players, a.games, a.max_turns, a.seed, a.variants)
            if a.record and "error" not in r:
                from .design import _summary, record
                record(a.record, a.definition, a.variants, "selfplay", a.players, a.games, a.seed, a.max_turns, _summary(r), a.note)
            _out(r)
        elif a.cmd == "compare":
            from .design import compare, record
            vs = dict(x.split("=", 1) for x in a.variant)
            r = compare(a.definition, vs, a.players, a.games, a.max_turns, a.seed, a.variants)
            if a.record:
                for name, row in r["rows"].items():
                    record(a.record, a.definition, a.variants + ([vs[name]] if name in vs else []), "compare", a.players, a.games,
                           a.seed, a.max_turns, row, a.note)
            _out(r)
        elif a.cmd == "league":
            from .bot import league, record_league
            bots = dict((x.split("=", 1) if "=" in x else (x, x)) for x in a.bot)
            if len(bots) < 2:
                raise OpError("--bot を 2 つ以上（名前=ファイル か random）")
            tr = [] if a.trace else None
            r = league(a.definition, bots, a.players, a.games, a.seed, a.max_turns, a.variants, tr)
            if a.record:
                record_league(a.record, a.definition, bots, a.players, a.games, a.seed, a.max_turns, r, a.variants, a.note)
            if a.trace:
                Path(a.trace).write_text("".join(json.dumps(t, ensure_ascii=False) + "\n" for t in tr), encoding="utf-8")
            _out(r)
        elif a.cmd == "bot-step":
            from .bot import bot_step
            bots = dict(x.split("=", 1) if "=" in x else (x, "random") for x in a.bot)
            _out(bot_step(Session(a.session), a.human, bots, a.max))
        elif a.cmd == "experiments":
            from .design import experiments
            _out(experiments(a.log, a.last))
        elif a.cmd == "init":
            from .design import init
            _out(init(a.folder, a.name, a.players))
        elif a.cmd == "status":
            from .design import status
            _out(status(load(a.definition, a.players, None, a.variants), a.experiments))
        elif a.cmd == "rulebook":
            from .design import rulebook
            sys.stdout.write(rulebook(load(a.definition, a.players, None, a.variants)))
        elif a.cmd == "fuzz":
            from .sim import fuzz
            r = fuzz(a.definition, a.players, a.games, a.steps, a.seed, a.variants)
            _out(r)
            if r["crashes"] or r["expr_errors"]:
                sys.exit(1)
        elif a.cmd == "rebase":
            _out({"ok": True, "replayed": Session(a.session).rebase()})
        elif a.cmd == "undo":
            s = Session(a.session)
            removed = s.undo()
            by = next((o.get("by") for o in removed if o.get("by") in s.defn.players), None)
            _out({"undone": _visible_ops(s, s.state(), removed, by)})  # 取り消した人の見え方で（隠れた部品を明かさない）
        elif a.cmd == "serve":
            from .server import serve
            Session(a.session)  # 開けない対局なら画面を立てる前に止める
            serve(a.session, a.host, a.port)
        elif a.cmd == "tts":
            from .tts import export
            s = Session(a.session)
            data = export(s.defn, s.state(), Path(a.out), s.meta["seats"])
            _out({"out": a.out, "objects": len(data["ObjectStates"])})
        elif a.cmd == "stats":
            _out(stats([Session(x) for x in a.sessions]))
        if getattr(a, "session", None) and a.cmd != "new":
            for w in Session(a.session).load_warnings:
                sys.stderr.write(f"warning: {w}\n")
    except (ValueError, KeyError, FileNotFoundError, yaml.YAMLError) as e:  # DefinitionError・OpError・式の誤り・JSON の誤りも ValueError
        sys.stderr.write(f"error: {e}\n")
        _usage(a, str(e))
        return 2
    _usage(a, None)
    return 0


def _usage(a, error):
    """対局で使ったコマンドと、受け付けなかったもの（拒否）を usage.jsonl に残す（目的の物差し：bg playstats）。
    局面の記録（log.jsonl）とは別。記録の再生には使わない。"""
    d = getattr(a, "session", None)
    if not d or a.cmd in ("new", "playstats") or not (Path(d) / "session.yaml").exists():
        return
    try:
        n = sum(1 for _ in (Path(d) / "log.jsonl").open(encoding="utf-8"))
        who = getattr(a, "by", None) or getattr(a, "player", None)
        rec = {"cmd": a.cmd, **({"who": who} if who else {}), "ops": n, **({"error": error[:200]} if error else {})}
        with (Path(d) / "usage.jsonl").open("a", encoding="utf-8") as f:
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")
    except OSError:
        pass


if __name__ == "__main__":
    sys.exit(main())
