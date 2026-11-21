"""古典のサンプル（RUL-005 #1）：定義だけで、置ける・動ける場所の候補と、局面の変化が正しく出るか。"""
from pathlib import Path

import pytest

from bgskills.definition import load
from bgskills.query import candidates
from bgskills.session import Session
from bgskills.tools import check_refs
from bgskills.view import view

EX = Path(__file__).parent.parent / "examples"


def ok(s, action, actor, param, args=None):
    return [c["id"] for c in candidates(s.defn, s.state(), action, actor, param, args) if not c["problems"]]


@pytest.mark.parametrize("name,n", [("othello", 2), ("chess", 2), ("shogi", 2), ("mahjong", 4)])
def test_classic_refs(name, n):
    assert check_refs(load(EX / f"{name}.yaml", n)) == []


def test_othello(tmp_path):
    s = Session.create(tmp_path / "o", EX / "othello.yaml", 2, {}, 1)
    s.act("setup", "keeper")
    s.apply({"op": "advance"})
    assert sorted(ok(s, "place", "black", "cell")) == ["s34", "s43", "s56", "s65"]  # 最初に置ける 4 マス
    st = s.act("place", "black", {"cell": "s43"})
    assert view(s.defn, st, None)["metrics"]["discs"]["values"] == {"black": 4, "white": 1}  # 1 つ裏返った
    assert st["flow"]["active"] == "white"


def test_chess(tmp_path):
    s = Session.create(tmp_path / "c", EX / "chess.yaml", 2, {}, 1)
    assert ok(s, "move", "white", "to", {"piece": "wP5"}) == ["s55", "s56"]  # 最初は 2 マスも
    assert ok(s, "move", "white", "to", {"piece": "wN2"}) == ["s66", "s86"]
    assert ok(s, "move", "white", "to", {"piece": "wQ"}) == []  # 囲まれている
    s.act("move", "white", {"piece": "wP5", "to": "s55"})
    s.act("move", "black", {"piece": "bP4", "to": "s44"})
    s.act("move", "white", {"piece": "wP5", "to": "s44"})  # 斜めに取る
    assert s.state()["places"]["taken-white"] == ["bP4"] and not s.last_warnings


def test_shogi(tmp_path):
    s = Session.create(tmp_path / "s", EX / "shogi.yaml", 2, {}, 1)
    assert ok(s, "move", "sente", "to", {"piece": "sG4"}) == ["s38", "s48", "s58"]
    s.act("move", "sente", {"piece": "sP3", "to": "s36"})
    s.apply({"op": "advance"})
    s.act("move", "gote", {"piece": "gP4", "to": "s44"})
    s.apply({"op": "advance"})
    s.act("move", "sente", {"piece": "sB", "to": "s73"})  # 角で歩を取る
    st = s.state()
    assert st["places"]["stand-sente"] == ["gP7"] and st["states"]["gP7"]["side"] == "sente"  # 向きを変えて持ち駒に
    s.act("promote", "sente", {"piece": "sB"})
    assert s.state()["states"]["sB"]["status"] == "promoted"
    assert ok(s, "drop", "sente", "to", {"piece": "gP7"}) == []  # どの列にも自分の歩（二歩）


def test_mahjong(tmp_path):
    s = Session.create(tmp_path / "m", EX / "mahjong.yaml", 4, {}, 3)
    s.act("setup", "keeper")
    s.apply({"op": "advance"})
    st = s.state()
    assert len(st["places"]["wall"]) == 70 and len(st["places"]["hand-N"]) == 13
    s.act("draw", "E")
    s.act("discard", "E", {"tile": s.state()["places"]["hand-E"][0]})
    h = s.state()["places"]["hand-W"]
    s.act("pon", "W", {"giver": "E", "t1": h[0], "t2": h[1]})  # 鳴くと W の打牌へ飛ぶ
    f = s.state()["flow"]
    assert (f["active"], f["phase"]) == ("W", "discard")
    s.act("discard", "W", {"tile": s.state()["places"]["hand-W"][0]})
    assert s.state()["flow"]["active"] == "N"
    assert view(s.defn, s.state(), "S")["areas"]["hand-E"]["shown"] == {"count": 13}  # 他人の手牌は枚数だけ


def test_kind_must_derive_from_primitive(tmp_path):
    import yaml
    raw = yaml.safe_load((EX / "tic-tac-toe.yaml").read_text(encoding="utf-8"))
    raw["kinds"]["orphan"] = {"text": "原型の派生でない種類"}
    raw["kinds"]["child"] = {"base": "orphan"}
    p = tmp_path / "d.yaml"
    p.write_text(yaml.safe_dump(raw, allow_unicode=True), encoding="utf-8")
    bad = {b["where"] for b in check_refs(load(p))}
    assert {"kind orphan.base", "kind child.base"} <= bad


def test_images_and_assets_route(tmp_path):
    """画像は原型の表示方法（image・back_image・状態で替わる絵）。画面は assets.root の下だけを配る。"""
    import json
    import threading
    import urllib.error
    import urllib.request
    import yaml
    from bgskills.server import make_handler
    from http.server import ThreadingHTTPServer
    (tmp_path / "img").mkdir()
    (tmp_path / "img" / "board.png").write_bytes(b"\x89PNG\r\n\x1a\nboard")
    (tmp_path / "secret.png").write_bytes(b"\x89PNG\r\n\x1a\nsecret")
    raw = yaml.safe_load((EX / "kagaribi.yaml").read_text(encoding="utf-8"))
    raw["assets"] = {"root": "img", "credit": "テスト"}
    raw["areas"][0]["image"] = "board.png"
    raw["kinds"]["card"]["back_image"] = "back.png"
    raw["kinds"]["wood"]["image"] = {"default": "wood.png", "facing=down": "never.png"}
    p = tmp_path / "d.yaml"
    p.write_text(yaml.safe_dump(raw, allow_unicode=True), encoding="utf-8")
    s = Session.create(tmp_path / "s", p, 2, {}, 1)
    d = s.defn
    assert d.image("deck") == "board.png" and d.image("W1-1", {}) == "wood.png" and d.image("N1", {}, "back_image") == "back.png"
    s.apply({"op": "move", "obj": "W1-1", "to": "fire-P1", "facing": "up"})
    s.apply({"op": "move", "obj": "W2-1", "to": "fire-P1", "facing": "down"})
    fire = view(d, s.state(), "P2")["areas"]["fire-P1"]["shown"]
    assert fire[0]["image"] == "wood.png"  # 表の絵
    assert fire[1]["back_image"] == "back.png" and "image" not in fire[1]  # 裏向きは裏の絵だけ（中身は伏せる）
    httpd = ThreadingHTTPServer(("127.0.0.1", 0), make_handler(tmp_path / "s"))
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    base = f"http://127.0.0.1:{httpd.server_address[1]}"
    try:
        assert urllib.request.urlopen(base + "/assets/board.png").read().endswith(b"board")
        for bad in ("/assets/../secret.png", "/assets/%2e%2e/secret.png", "/assets/nothing.png"):
            with pytest.raises(urllib.error.HTTPError):
                urllib.request.urlopen(base + bad)
        summary = json.loads(urllib.request.urlopen(base + "/api/def").read())
        assert summary["assets"]["credit"] == "テスト" and summary["areas"][0]["image"] == "board.png"
    finally:
        httpd.shutdown()


def test_flow_on_start(tmp_path):
    """進行の on_start：手番に入ったときの手順（エリアの on_enter の時間版）。記録には足さず、再生で同じ局面になる。"""
    import yaml
    raw = yaml.safe_load((EX / "kagaribi.yaml").read_text(encoding="utf-8"))
    raw["areas"].append({"id": "turn-track", "name": "手番の目印の置き場", "areas": [{"id": f"t{i}"} for i in range(1, 6)]})
    raw["objects"].append({"id": "turn-marker", "kind": "card", "start": "t1"})
    raw["flow"]["turns"]["main"]["on_start"] = [{"let": {"to": "'t' + str(min(turn_in_stage(), 5))"}},
                                                {"op": "move", "obj": "turn-marker", "to": "{to}"}]
    p = tmp_path / "d.yaml"
    p.write_text(yaml.safe_dump(raw, allow_unicode=True), encoding="utf-8")
    s = Session.create(tmp_path / "s", p, 2, {}, 1)
    s.apply({"op": "advance", "to": "turn"})
    s.apply({"op": "advance", "to": "turn"})
    assert "turn-marker" in s.state()["places"]["t3"] and len(s.log()) == 2
    assert Session(tmp_path / "s").state()["places"]["t3"] == ["turn-marker"]  # 再生しても同じ


# ---- レビュー（RUL-008）で見つけた不具合 ----

def test_undo_takes_back_action_with_auto_advance(tmp_path):
    s = Session.create(tmp_path / "o", EX / "othello.yaml", 2, {}, 1)
    s.act("setup", "keeper")
    s.apply({"op": "advance"})
    s.act("place", "black", {"cell": "s43"})  # フェーズの auto で白の手番へ進む
    assert s.undo()[0]["action"] == "place"  # 自動の advance だけでなく、アクションごと取り消す
    st = s.state()
    assert st["flow"]["active"] == "black" and not st["places"]["s43"]
    assert "s43" in ok(s, "place", "black", "cell")  # もう一度置ける（回数が戻っている）


def test_unknown_actor_is_rejected(tmp_path):
    from bgskills.session import OpError
    s = Session.create(tmp_path / "o", EX / "othello.yaml", 2, {}, 1)
    with pytest.raises(OpError, match="席にない"):
        s.act("setup", "P1")
    with pytest.raises(OpError, match="席にない"):
        s.apply({"op": "advance", "by": "P9"})
    assert s.log() == []


def test_chess_material_and_view(tmp_path):
    s = Session.create(tmp_path / "c", EX / "chess.yaml", 2, {}, 1)
    s.act("move", "white", {"piece": "wP5", "to": "s55"})
    s.act("move", "black", {"piece": "bP4", "to": "s44"})
    s.act("move", "white", {"piece": "wP5", "to": "s44"})
    assert view(s.defn, s.state(), None)["metrics"]["material"]["values"] == {"white": 1, "black": 0}


def test_mahjong_chi_takes_from_kamicha(tmp_path):
    s = Session.create(tmp_path / "m", EX / "mahjong.yaml", 4, {}, 3)
    s.act("setup", "keeper")
    s.apply({"op": "advance"})
    s.act("draw", "E")
    s.act("discard", "E", {"tile": s.state()["places"]["hand-E"][0]})
    discarded = s.state()["places"]["river-E"][-1]
    h = s.state()["places"]["hand-S"]
    s.act("chi", "S", {"t1": h[0], "t2": h[1]})  # 上家は E（seat(S, -1)）
    assert discarded in s.state()["places"]["melds-S"]


def test_check_finds_exprs_flow_and_nested_steps(tmp_path):
    import yaml
    raw = yaml.safe_load((EX / "othello.yaml").read_text(encoding="utf-8"))
    raw["metrics"][0]["expr"] = "{'a': 1}.get('a')"  # メソッドは呼べない
    raw["flow"]["turns"]["main"]["phases"][0]["main"].append("no-such-action")
    raw["actions"][1]["steps"][2]["do"][2]["do"][0]["do"].append({"op": "move", "obj": "{disc}", "to": "nowhere"})
    raw["actions"][1]["steps"][2]["do"][1]["let"]["n"] = "nexxt(1)"
    p = tmp_path / "d.yaml"
    p.write_text(yaml.safe_dump(raw, allow_unicode=True), encoding="utf-8")
    refs = {b["ref"] for b in check_refs(load(p))}
    assert "no-such-action" in refs and "nowhere" in refs
    assert any("関数は名前で呼ぶ" in r for r in refs) and any("知らない関数: nexxt" in r for r in refs)


# ---- カードの効果とオブジェクトのステータス（RUL-011） ----

def _duel(tmp_path):
    s = Session.create(tmp_path / "b", EX / "beast-duel.yaml", 2, {}, 3)
    s.act("setup", "keeper")
    s.apply({"op": "move", "obj": "P1-hibana-1", "to": "active-P1", "by": "keeper"})
    s.apply({"op": "move", "obj": "P2-shizuku-1", "to": "active-P2", "by": "keeper"})
    s.apply({"op": "move", "obj": "P2-shizuku-2", "to": "bench-P2", "by": "keeper"})
    s.apply({"op": "advance"})
    return s


def test_duel_attack_knocks_out_in_same_action(tmp_path):
    assert check_refs(load(EX / "beast-duel.yaml")) == []
    s = _duel(tmp_path)
    s.act("draw", "P1")
    for e in ("P1-fire-1", "P1-fire-2"):
        s.apply({"op": "move", "obj": e, "to": "P1-hibana-1", "by": "keeper"})
    s.apply({"op": "move", "obj": "counter-pool", "from": "supply", "to": "P2-shizuku-1", "n": 4, "by": "keeper"})
    assert ok(s, "attack", "P1", "move") == ["1", "2"]
    prizes = len(s.state()["places"]["prizes-P1"])
    st = s.act("attack", "P1", {"move": "2"})  # 火の粉 20：40 + 20 = HP 60 → きぜつ（ダメージの後の局面を読む）
    assert "P2-shizuku-1" in st["places"]["discard-P2"] and st["places"]["active-P2"] == []
    assert len(st["places"]["prizes-P1"]) == prizes - 1 and "きぜつ" in st["talk"][-1]["text"]
    assert st["places"].get("P2-shizuku-1") in (None, [])  # カウンターは補給へ戻る
    assert st["flow"]["active"] == "P2"  # ワザで手番が終わる


def test_duel_coin_poison_and_cost(tmp_path):
    s = _duel(tmp_path)
    s.act("draw", "P1")
    assert ok(s, "attack", "P1", "move") == []  # エネルギーがない
    s.apply({"op": "set", "obj": "P2-shizuku-1", "field": "condition", "value": "poisoned", "by": "keeper"})
    s.apply({"op": "advance", "to": "turn"})  # 手番の間：どくで 10
    st = s.state()
    assert {"counter-pool": 1} in st["places"]["P2-shizuku-1"]
    s.act("draw", "P2")
    for e in ("P2-water-1", "P2-water-2"):
        s.apply({"op": "move", "obj": e, "to": "P2-shizuku-1", "by": "keeper"})
    st = s.act("attack", "P2", {"move": "2"})  # あわ：コインでマヒ
    heads = st["states"]["the-coin"]["face"] == "heads"
    assert (st["states"]["P1-hibana-1"]["condition"] == "paralyzed") == heads


def test_named_functions_chess_check(tmp_path):
    """名前つきの式（functions）：チェスの届くマス・攻撃・チェックを 1 か所に書き、条件・指標・知らせから呼ぶ。"""
    from bgskills.flow import end_signals
    from bgskills.metrics import compute
    s = Session.create(tmp_path / "c", EX / "chess.yaml", 2, {}, 1)
    for who, pc, to in [("white", "wP6", "s66"), ("black", "bP5", "s54"), ("white", "wP7", "s75"), ("black", "bQ", "s85")]:
        s.act("move", who, {"piece": pc, "to": to})  # フールズメイト
    st = s.state()
    assert compute(s.defn, st, None)["check"]["values"] == {"white": True, "black": False}
    assert end_signals(s.defn, st, "signals") == ["white のキングがチェックされている（外す手しか指せない。R3）"]
    assert sorted(c["id"] for c in candidates(s.defn, st, "move", "white", "to", {"piece": "wN1"}) if not c["problems"]) == ["s16", "s36"]


def test_named_function_errors(tmp_path):
    from bgskills.expr import ExprError, evaluate
    d = load(EX / "chess.yaml", 2)
    d.data["functions"]["loop"] = {"params": ["x"], "expr": "loop(x)"}
    st = Session.create(tmp_path / "c", EX / "chess.yaml", 2, {}, 1).state()
    with pytest.raises(ExprError, match="引数は 1 個"):
        evaluate("in_check()", d, st)
    with pytest.raises(ExprError, match="深すぎる"):
        evaluate("loop(1)", d, st)


def test_repeated_position(tmp_path):
    """局面の履歴：手番の替わり目に局面を覚え、repeats() で今の局面が何回目かを読む（チェスの 3 回、将棋の千日手）。"""
    from bgskills.flow import end_signals
    s = Session.create(tmp_path / "c", EX / "chess.yaml", 2, {}, 1)
    for n in range(3):
        for who, pc, to in [("white", "wN1", "s36"), ("black", "bN1", "s33"), ("white", "wN1", "s28"), ("black", "bN1", "s21")]:
            s.act("move", who, {"piece": pc, "to": to})
        assert ("同じ局面が 3 回目（引き分けを申し出られる。R7）" in end_signals(s.defn, s.state(), "signals")) == (n == 2)


def test_check_finds_unknown_names_in_exprs():
    """bg check：式の中で文字列で書いた進行状態・指標・部品の名前が定義にないと指摘する（打ち間違い）。"""
    from bgskills.tools import check_exprs
    d = load(EX / "werewolf.yaml", 5)
    assert check_exprs(d) == []
    d.data["actions"][0]["require"] = [{"expr": "progress('runof') and metric('vote', 'P1') and state('fangs', 'target')", "text": "x"}]
    (bad,) = check_exprs(d)
    assert "progress('runof')" in bad["ref"] and "metric('vote')" in bad["ref"] and "state('fangs')" in bad["ref"]


def test_duel_playtest_fixes(tmp_path, capsys):
    """エージェントの試し遊び（ループ 8）で見つけた点：knock-out のサイド、プレイヤーに出す知らせ、candidates・act・advance の使い勝手。"""
    import yaml
    from bgskills.cli import main
    from bgskills.view import view
    s = _duel(tmp_path)
    s.apply({"op": "move", "obj": "counter-pool", "from": "supply", "to": "P2-shizuku-2", "n": 6, "by": "keeper"})
    sig = view(s.defn, s.state(), "P1")["flow"].get("signals") or []
    assert any("HP が 0" in x for x in sig)  # public: true の知らせはプレイヤーにも出る
    p1, p2 = (len(s.state()["places"][f"prizes-{p}"]) for p in ("P1", "P2"))
    main(["act", str(s.dir), "knock-out", "--arg", "target=P2-shizuku-2"])  # --by を省くとキーパー
    st = s.state()
    assert len(st["places"]["prizes-P1"]) == p1 - 1 and len(st["places"]["prizes-P2"]) == p2  # 取るのは相手だけ
    capsys.readouterr()
    main(["candidates", str(s.dir), "attack", "--by", "P1"])  # --param を省くと全部の引数
    assert "move" in yaml.safe_load(capsys.readouterr().out)
    main(["candidates", str(s.dir), "promote", "--by", "keeper", "--param", "card"])  # 行えない人には候補を出さないのでキーパーで
    c = yaml.safe_load(capsys.readouterr().out)["card"]
    assert all("title" in x for x in c)
    from bgskills.query import check_param
    prm = next(p for a in s.defn.data["actions"] if a["id"] == "promote" for p in a["params"] if p["name"] == "card")
    assert any("にない" in m for m in check_param(s.defn, s.state(), prm, "P2-shizuku-1", {"actor": "P2", "player": "P2"}))  # from に合わない
    main(["advance", str(s.dir), "--to", "turn"])
    assert s.state()["flow"]["active"] == "P2"


def test_compact_groups_by_owner_and_lists_ids(tmp_path):
    from bgskills.cli import _group
    g = _group([{"id": "a1", "kind": "k", "owner": "P1"}, {"id": "a2", "kind": "k", "owner": "P1"}, {"id": "b1", "kind": "k", "owner": "P2"}])
    assert [x.get("ids") or x.get("id") for x in g] == [["a1", "a2"], "b1"]


def test_derived_values_and_compact_catalog(tmp_path, capsys):
    """種類の derived（部品ごとに計算する値：残り HP）と、--compact の catalog（ワザの一覧は名前ごとに 1 回）。"""
    import yaml
    from bgskills.cli import main
    s = _duel(tmp_path)
    s.apply({"op": "move", "obj": "counter-pool", "from": "supply", "to": "P2-shizuku-1", "n": 2, "by": "keeper"})
    capsys.readouterr()
    main(["show", str(s.dir), "--as", "P1", "--compact"])
    v = yaml.safe_load(capsys.readouterr().out)
    (sh,) = [x for x in v["areas"]["active-P2"]["shown"] if x.get("id") == "P2-shizuku-1"]
    assert sh["derived"]["hp_left"] == sh["attributes"]["hp"] - 20 and "attacks" not in sh["attributes"]
    assert "attacks" in v["catalog"][sh["title"]]


def test_duel_poison_knock_out_at_turn_start(tmp_path):
    """手番の初めの手順は 1 つずつ行い（stepwise）、どくのダメージで HP が 0 になれば call で knock-out を行う。"""
    s = _duel(tmp_path)
    s.apply({"op": "set", "obj": "P2-shizuku-1", "field": "condition", "value": "poisoned", "by": "keeper"})
    hp = s.defn.parts["P2-shizuku-1"]["attributes"]["hp"]
    s.apply({"op": "move", "obj": "counter-pool", "from": "supply", "to": "P2-shizuku-1", "n": hp // 10 - 1, "by": "keeper"})
    p1 = len(s.state()["places"]["prizes-P1"])
    s.apply({"op": "advance", "to": "turn"})  # P2 の手番の初め：どくで 10 → HP 0 → きぜつ
    st = s.state()
    assert "P2-shizuku-1" in st["places"]["discard-P2"] and len(st["places"]["prizes-P1"]) == p1 - 1
    assert "きぜつ" in st["talk"][-1]["text"]


def test_check_unknown_call():
    from bgskills.tools import check_refs
    d = load(EX / "beast-duel.yaml")
    d.data["actions"][0]["steps"].append({"call": "no-such"})
    assert any(r["ref"] == "no-such" for r in check_refs(d))


def test_free_action_limited_to_phase(tmp_path):
    """フリーアクションの phases：引く前（draw）はエネルギーを付けられず、引いた後（play）は付けられる。"""
    from bgskills.flow import available
    s = _duel(tmp_path)
    assert s.state()["flow"]["phase"] == "draw" and "attach" not in available(s.defn, s.state()["flow"], "P1")["free"]
    s.act("draw", "P1")
    assert "attach" in available(s.defn, s.state()["flow"], "P1")["free"]


def test_duel_from_box(tmp_path):
    """箱から始めた精霊獣デュエル：準備で各自のカードを山札へ、カウンターとコインを補給へ置いてから配る。"""
    counts = []
    for box in (True, False):
        s = Session.create(tmp_path / f"b{box}", EX / "beast-duel.yaml", 2, {}, 3, from_box=box)
        st = s.act("setup", "keeper")
        counts.append({k: len(v) for k, v in st["places"].items() if v})
        assert all(s.defn.parts[c]["owner"] == "P1" for c in st["places"]["deck-P1"])
    assert counts[0] == counts[1]


def test_phase_each_limits_each_main_action(tmp_path):
    """フェーズの each：メインアクションごとの回数（初期配置の開拓地 1 つと街道 1 本）。超えたら警告。"""
    from bgskills.flow import classify
    s = _duel(tmp_path)
    s.act("draw", "P1")
    d, f = s.defn, s.state()["flow"]
    ph = next(p for p in d.data["flow"]["turns"]["main"]["phases"] if p["id"] == f["phase"])
    ph.update(each=1, main=["attack", "potion"], max=None)
    f["counts"]["phase"]["attack"] = 1
    assert any("1 回まで" in w for w in classify(d, f, "attack", "P1")[1])
    assert not any("1 回まで" in w for w in classify(d, f, "potion", "P1")[1])


def test_fuzz_finds_definition_errors(tmp_path):
    """bg fuzz：でたらめ実行で、条件の式の誤り（バトル場が空のときに読む）を見つける。直した定義では出ない。"""
    from bgskills.tools import fuzz
    assert fuzz(EX / "beast-duel.yaml", 2, games=2, steps=100)["expr_errors"] == []
    broken = (EX / "beast-duel.yaml").read_text(encoding="utf-8").replace(
        "on1('active-' + actor) and len(on(on1('active-' + actor), kind='energy')) >= attr(on1('active-' + actor), 'retreat')",
        "len(on(on1('active-' + actor), kind='energy')) >= attr(on1('active-' + actor), 'retreat')")
    (tmp_path / "d.yaml").write_text(broken, encoding="utf-8")
    r = fuzz(tmp_path / "d.yaml", 2, games=6, steps=150)
    assert any(e["action"] == "retreat" for e in r["expr_errors"]) and r["crashes"] == []


def test_check_path_needs_viewbox(tmp_path):
    """形（path）は祖先の viewbox の座標で描く。viewbox がなければ bg check が知らせる（RUL-025）。"""
    import yaml
    from bgskills.definition import Definition
    from bgskills.tools import check_refs
    d = {"format": "bg-def/0.1", "game": {"id": "p", "name": "p", "version": 1, "players": {"min": 1, "max": 1}},
         "players": [{"id": "P1"}], "areas": [{"id": "board", "areas": [{"id": "a", "path": "M0 0 L1 1 Z"}]},
                                               {"id": "b2", "viewbox": "0 0 10", "areas": [{"id": "c", "path": "M0 0 L1 1 Z"}]}],
         "objects": [], "rules": [{"id": "R1", "type": "always", "text": "x"}]}
    (tmp_path / "p.yaml").write_text(yaml.safe_dump(d, allow_unicode=True), encoding="utf-8")
    bad = {x["where"] for x in check_refs(Definition(d))}
    assert bad == {"area a.path", "area b2.viewbox"}


def test_fuzz_reaches_turn_actions():
    """bg fuzz の「一度も行えないアクション」が当てになる（全体レビューの指摘）：手番の人・今行えるアクションから選び、
    手番のある段階を飛ばさない。以前は、かがり火の全アクション・人狼のほぼ全部が「行えない」と出た。"""
    from bgskills.sim import fuzz
    k = fuzz(EX / "kagaribi.yaml", 2, games=2, steps=120)
    assert {"draw", "stoke", "discard"}.isdisjoint(k["never_done"]) and k["expr_errors"] == [] and k["crashes"] == []
    w = fuzz(EX / "werewolf.yaml", 5, games=2, steps=150)
    assert {"setup", "attack", "divine"}.isdisjoint(w["never_done"]) and w["crashes"] == []
    m = fuzz(EX / "mahjong.yaml", 4, games=2, steps=120)
    assert m["expr_errors"] == []  # 捨て牌が無いときのポン・チー
