"""受入基準（specs/versions/v1/okf/specifications）の機械で確かめられるもの。テスト名に AC の ID を入れる。"""
import copy
from pathlib import Path

import pytest
import yaml

from bgskills.cli import stats
from bgskills.definition import Definition, DefinitionError, load
from bgskills.session import OpError, Session
from bgskills.tools import check_refs, diff, dump, rules_referencing
from bgskills.view import view

EX = Path(__file__).parent.parent / "examples"
TTT, KAG, HEX = EX / "tic-tac-toe.yaml", EX / "kagaribi.yaml", EX / "hex-skirmish.yaml"


def raw(p):
    return yaml.safe_load(p.read_text(encoding="utf-8"))


# 惨劇RoopeR の伏せ札と同じ形を試す、自作の小さな定義（既存ゲームの定義は公開しない：RUL-001 #37）
HIDDEN = {
    "game": {"id": "hidden", "version": 1, "players": {"min": 2, "max": 2}},
    "players": [{"id": "M"}, {"id": "A"}],
    "kinds": {"card": {"base": "object", "states": {"facing": {"up": "表向き", "down": "裏向き"}}},
              "figure": {"base": "object", "text": "人物"},
              "counter": {"base": "object", "distinct": False, "text": "不安"}},
    "areas": [{"id": "board", "visibility": {"face": "all"}}, {"id": "hand-M", "owner": "M", "visibility": {"face": "owner"}},
              {"id": "supply"}],
    "objects": [{"id": "doctor", "kind": "figure", "start": "board"},
                {"id": "M-PAR", "kind": "card", "start": "hand-M"},
                {"id": "par", "kind": "counter", "count": "unlimited", "start": "supply"}],
    "rules": [{"id": "R1", "text": "脚本家は手札から 1 枚を裏向きでセットする。", "refs": ["card"]}],
}


# ---------- 定義 ----------

def test_AC_001_1_read_by_id():
    d = load(TTT)
    assert d.players == ["X", "O"]
    assert {f"c{r}{c}" for r in "123" for c in "123"} <= set(d.areas)
    assert [r for r in d.rules] == ["R1", "R2", "R3", "R4"]


def test_AC_001_2_duplicate_id():
    r = raw(TTT)
    r["rules"].append(copy.deepcopy(r["rules"][0]))
    with pytest.raises(DefinitionError, match="R1"):
        Definition(r)


def test_AC_001_3_expand_for_players():
    d = load(KAG, players=2)
    assert d.players == ["P1", "P2"]
    assert {"hand-P1", "hand-P2", "fire-P1", "fire-P2"} <= set(d.areas) and "hand-P3" not in d.areas
    assert d.parts["W6-3"]["attributes"]["value"] == 6


def test_AC_002_1_roundtrip():
    d = load(KAG)
    again = yaml.safe_load(dump(d.raw))
    assert again == d.raw


def test_AC_002_2_multiline_block():
    r = raw(KAG)
    r["rules"][0]["text"] = "全カードを裏向きにして切る。\n各プレイヤーは 3 枚を引く。"
    assert "text: |" in dump(r)


def test_AC_002_3_no_stays_string():
    assert yaml.safe_load(dump({"v": "no"}))["v"] == "no"


def test_AC_003_1_no_missing():
    assert check_refs(load(KAG)) == []


def test_AC_003_2_missing_ref():
    r = raw(TTT)
    r["rules"][3]["refs"].append("line2")
    assert {"where": "rule R4.refs", "ref": "line2"} in check_refs(Definition(r))


def test_AC_004_link_and_shape():
    r = raw(TTT)
    r["links"] = [{"between": ["c11", "c12"], "type": "horizontal", "text": "横に隣り合う"}]
    r["areas"][0]["shape"] = {"path": "M0 0 L3 0 L3 3 L0 3 Z"}
    d = Definition(r)
    assert d.areas["c22"]["pos"] == [1, 1]  # AC-004-1：親（盤）の原点からの位置
    assert d.data["links"][0]["type"] == "horizontal"  # AC-004-2
    assert yaml.safe_load(dump(d.raw))["areas"][0]["shape"] == r["areas"][0]["shape"]  # AC-004-3


def test_AC_005_state_meaning_and_uses():
    d = load(KAG)
    assert "見えない" in d.states("wood")["facing"]["down"]["text"]  # AC-005-1（元の種類 card から継承）
    uses = d.uses("wind")
    assert [u["id"] for u in uses] == ["blow", "guard"] and uses[1]["refs"] == ["R5", "guard"]  # AC-005-2


def test_AC_006_diff():
    r1 = raw(KAG)
    r2 = copy.deepcopy(r1)
    r2["game"]["version"] = 2
    r2["objects"][0]["copies"] = 2  # 薪を各 2 枚に
    dd = diff(Definition(r1), Definition(r2))
    assert dd["part_counts"]["wood"] == {"from": 18, "to": 12}  # AC-006-1（r2：種類ごとの数）
    assert "W6-3" in dd["removed"] and len(dd["removed"]) == 6
    assert diff(Definition(r1), Definition(r1))["removed"] == [] and diff(Definition(r1), Definition(r1))["changed"] == {}  # AC-006-2


# ---------- 逆引き ----------

def test_AC_010_1_rules_for_kind():
    assert rules_referencing(load(KAG), "wood") == ["R3", "R4", "R5", "R8"]


def test_AC_010_2_no_rules():
    assert rules_referencing(load(TTT), "supply-X") == ["R2"]
    assert rules_referencing(load(KAG), "N1") == ["R4", "R5"]  # 部品は種類（風）を通じて引く
    assert rules_referencing(load(TTT), "X") == []


# ---------- 対局 ----------

@pytest.fixture
def kag(tmp_path):
    s = Session.create(tmp_path / "s1", KAG, 2, {"P1": "agent:a", "P2": "agent:b"}, 20261118)
    return s


def test_AC_014_1_create(kag):
    st = kag.state()
    assert kag.meta["version"] == 1 and kag.meta["seed"] == 20261118 and kag.meta["seats"]["P2"] == "agent:b"
    assert len(st["places"]["deck"]) == 24 and st["places"]["hand-P1"] == []


def test_AC_014_2_players_out_of_range(tmp_path):
    with pytest.raises(DefinitionError, match="人数 5"):
        Session.create(tmp_path / "s", KAG, 5, {}, 1)


def test_AC_015_move_and_attach(kag):
    kag.apply({"op": "move", "obj": "N4", "to": "hand-P2", "by": "keeper", "rule": "R1"})
    st = kag.apply({"op": "move", "obj": "N4", "to": "discard", "by": "P2", "rule": "R4"})
    assert st["places"]["discard"][-1] == "N4" and kag.log()[-1]["rule"] == "R4"  # AC-015-1
    kag.apply({"op": "move", "obj": "W6-1", "to": "fire-P1", "by": "P1", "rule": "R3"})
    kag.apply({"op": "attach", "obj": "N6", "to": "W6-1", "by": "P1", "rule": "R5"})
    st = kag.apply({"op": "set", "obj": "N6", "field": "turn", "value": "sideways", "by": "P1", "rule": "R5"})
    assert st["attached"]["N6"]["to"] == "W6-1" and st["states"]["N6"]["turn"] == "sideways"  # AC-015-2
    assert st["places"]["fire-P1"] == ["N6", "W6-1"]


def test_AC_016_1_wrong_place(kag):
    kag.apply({"op": "move", "obj": "N4", "to": "discard"})
    before = kag.log()
    with pytest.raises(OpError, match="discard"):
        kag.apply({"op": "move", "obj": "N4", "from": "hand-P2", "to": "fire-P1"})
    assert kag.log() == before


def test_AC_016_2_not_enough_counters(tmp_path):
    p = tmp_path / "hidden.yaml"
    p.write_text(yaml.safe_dump(HIDDEN, allow_unicode=True), encoding="utf-8")
    s = Session.create(tmp_path / "s", p, 2, {}, 1)
    s.apply({"op": "move", "obj": "par", "from": "supply", "to": "doctor", "n": 1})
    with pytest.raises(OpError, match="1 個"):
        s.apply({"op": "move", "obj": "par", "from": "doctor", "to": "supply", "n": 2})
    assert s.state()["places"]["doctor"] == [{"par": 1}]


def test_AC_017_shuffle_replay(kag, tmp_path):
    for i in range(30):
        kag.apply({"op": "shuffle", "area": "deck"} if i % 3 == 0 else {"op": "move", "obj": "N1", "to": "discard" if i % 2 else "deck"})
    end = kag.state()
    again = Session(kag.dir).state()  # 記録の再生だけで作り直す
    assert again == end  # AC-017-1・AC-017-2


def test_AC_018_end_blocks_ops(kag):
    kag.apply({"op": "end", "results": {"P1": "win", "P2": "lose"}, "rule": "R8"})
    assert kag.state()["result"]["rule"] == "R8"
    with pytest.raises(OpError, match="終了"):
        kag.apply({"op": "move", "obj": "N1", "to": "discard"})


def test_AC_019_ruling(kag):
    kag.apply({"op": "ruling", "question": "守り付きの薪が取り除かれたら守りは？", "decision": "一緒に捨て札へ置く",
               "reason": "人間のテーブルの慣習", "by": "keeper", "rules": ["R4"]})
    r = kag.state()["rulings"][0]
    assert r["decision"] == "一緒に捨て札へ置く" and r["rules"] == ["R4"] and r["time"]


# ---------- 見え方・意味 ----------

def _deal(kag):
    for o, to in [("W4-1", "hand-P1"), ("N2", "hand-P1"), ("W3-2", "hand-P1")]:
        kag.apply({"op": "move", "obj": o, "to": to, "by": "keeper", "rule": "R1"})
        kag.apply({"op": "flip", "obj": o})


def test_AC_011_1_other_hand(kag):
    _deal(kag)
    v = view(kag.defn, kag.state(), "P2")["areas"]["hand-P1"]
    assert v["shown"] == {"count": 3} and "持ち主（P1）" in v["hidden"]["face"]


def test_AC_011_2_own_hand(kag):
    _deal(kag)
    ids = [i["id"] for i in view(kag.defn, kag.state(), "P1")["areas"]["hand-P1"]["shown"]]
    assert ids == ["W4-1", "N2", "W3-2"]


def test_AC_011_2_drawn_face_down_card_visible_to_owner(kag):
    kag.apply({"op": "move", "obj": "W5-1", "to": "hand-P1"})  # 山札から裏向きのまま引く
    assert view(kag.defn, kag.state(), "P1")["areas"]["hand-P1"]["shown"][0]["id"] == "W5-1"
    assert view(kag.defn, kag.state(), "P2")["areas"]["hand-P1"]["shown"] == {"count": 1}


def test_AC_011_3_deck(kag):
    v = view(kag.defn, kag.state(), "P1")["areas"]["deck"]
    assert v["shown"] == {"count": 24} and set(v["hidden"]) == {"face", "order"}


def test_AC_011_4_5_known(tmp_path):
    p = tmp_path / "hidden.yaml"
    p.write_text(yaml.safe_dump(HIDDEN, allow_unicode=True), encoding="utf-8")
    s = Session.create(tmp_path / "s", p, 2, {}, 1)
    s.apply({"op": "move", "obj": "M-PAR", "to": "doctor", "by": "M", "rule": "R1"})
    s.apply({"op": "set", "obj": "M-PAR", "field": "facing", "value": "down"})
    s.apply({"op": "know", "obj": "M-PAR", "player": "M"})
    on_m = view(s.defn, s.state(), "M")["areas"]["board"]["shown"][0]["stacked"][0]
    on_a = view(s.defn, s.state(), "A")["areas"]["board"]["shown"][0]["stacked"][0]
    assert on_m["id"] == "M-PAR"  # AC-011-4
    assert "id" not in on_a and "裏向き" in on_a["hidden"]  # AC-011-5


def test_AC_009_1_meaning_attached(kag):
    kag.apply({"op": "move", "obj": "W3-1", "to": "fire-P1"})
    kag.apply({"op": "move", "obj": "W6-1", "to": "fire-P1"})
    for o in ("W3-1", "W6-1"):
        kag.apply({"op": "flip", "obj": o})
    kag.apply({"op": "attach", "obj": "N6", "to": "W6-1"})
    kag.apply({"op": "flip", "obj": "N6"})
    kag.apply({"op": "set", "obj": "N6", "field": "turn", "value": "sideways"})
    fire = view(kag.defn, kag.state(), None, meaning=True)["areas"]["fire-P1"]["shown"]
    n6 = next(i for i in fire if i.get("id") == "N6")
    assert n6["attached"]["to"] == "W6-1" and "守り" in n6["state"]["turn"]["meaning"] and "R5" in n6["rules"]


def test_AC_009_2_progress_rule(kag):
    kag.apply({"op": "progress", "key": "active", "value": "P1"})
    kag.apply({"op": "progress", "key": "step", "value": "act"})
    p = view(kag.defn, kag.state(), None, meaning=True)["progress"]
    assert p["active"]["value"] == "P1" and "R2" in p["step"]["rules"]


# ---------- 集計・オートマ ----------

def test_AC_022_stats(tmp_path):
    ss = []
    for i, (p1, p2) in enumerate([("win", "lose"), ("win", "lose"), ("lose", "win")]):
        s = Session.create(tmp_path / f"s{i}", KAG, 2, {}, i)
        s.apply({"op": "move", "obj": "N1", "to": "discard", "rule": "R4"})
        s.apply({"op": "end", "results": {"P1": p1, "P2": p2}, "rule": "R8"})
        ss.append(s)
    st = stats(ss)
    assert st["results"] == {"P1": {"win": 2, "lose": 1}, "P2": {"lose": 2, "win": 1}}  # AC-022-1
    assert "R6" in st["unused_rules"] and "R4" not in st["unused_rules"]  # AC-022-2


def test_AC_024_automa(tmp_path):
    r = raw(KAG)
    r["rules"] += [{"id": f"A{i}", "type": "automa", "seat": "P2", "text": f"オートマの手順 {i}"} for i in (1, 2, 3)]
    p = tmp_path / "k.yaml"
    p.write_text(dump(r), encoding="utf-8")
    d = load(p)
    assert [x["id"] for x in d.data["rules"] if x.get("seat") == "P2"] == ["A1", "A2", "A3"]  # AC-024-1
    s = Session.create(tmp_path / "s", p, 2, {"P2": "automa"}, 1)
    assert set(view(s.defn, s.state(), "P2", seats=s.meta["seats"])["automa_rules"]) == {"A1", "A2", "A3"}  # AC-024-2


# ---------- 画面のサーバー（さわった結果が bg op と同じ記録に残る） ----------

def test_server_api_and_cli_share_log(kag):
    import json, threading, urllib.request
    from http.server import ThreadingHTTPServer
    from bgskills.server import make_handler

    httpd = ThreadingHTTPServer(("127.0.0.1", 0), make_handler(kag.dir))
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    base = f"http://127.0.0.1:{httpd.server_address[1]}"
    try:
        req = urllib.request.Request(base + "/api/op", json.dumps({"op": "move", "obj": "N4", "to": "discard", "by": "P2"}).encode(),
                                     {"Content-Type": "application/json"})
        assert json.load(urllib.request.urlopen(req))["ok"]
        kag.apply({"op": "move", "obj": "N5", "to": "discard", "by": "P1"})  # エージェント側（bg op と同じ経路）
        log = json.load(urllib.request.urlopen(base + "/api/log"))
        assert [o["obj"] for o in log] == ["N4", "N5"]
        v = json.load(urllib.request.urlopen(base + "/api/view?meaning=1"))  # キーパー
        assert [i["id"] for i in v["areas"]["discard"]["shown"]] == ["N4", "N5"]
        v = json.load(urllib.request.urlopen(base + "/api/view?as=P1"))  # 捨て札に入ると表向き（on_enter）なので P1 にも見える
        assert [i["id"] for i in v["areas"]["discard"]["shown"]] == ["N4", "N5"]
        d = json.load(urllib.request.urlopen(base + "/api/def"))
        assert d["game"]["id"] == "kagaribi" and any(a["id"] == "deck" for a in d["areas"])
        assert b"<title>" in urllib.request.urlopen(base + "/").read()
        bad = urllib.request.Request(base + "/api/op", b'{"op":"move","obj":"nope","to":"deck"}', {"Content-Type": "application/json"})
        try:
            urllib.request.urlopen(bad)
            assert False
        except urllib.error.HTTPError as e:
            assert e.code == 400
    finally:
        httpd.shutdown()


def test_hand_shows_who_sees_not_facing(kag):
    kag.apply({"op": "move", "obj": "W5-1", "to": "hand-P1"})
    it = view(kag.defn, kag.state(), None)["areas"]["hand-P1"]["shown"][0]
    assert "facing" not in it["state"] and "P1" in it["visible_to"]


def test_move_with_facing(kag):
    kag.apply({"op": "move", "obj": "W5-1", "to": "hand-P1"})
    st = kag.apply({"op": "move", "obj": "W5-1", "to": "fire-P1", "facing": "up", "by": "P1", "rule": "R3"})
    assert st["states"]["W5-1"]["facing"] == "up"
    with pytest.raises(OpError, match="向き"):
        kag.apply({"op": "move", "obj": "W5-1", "to": "discard", "facing": "sideways"})


def test_tts_export(kag, tmp_path):
    import json
    from bgskills.tts import export
    kag.apply({"op": "shuffle", "area": "deck"})
    kag.apply({"op": "move", "obj": "W5-1", "to": "hand-P1"})
    kag.apply({"op": "move", "obj": "W6-1", "to": "fire-P1", "facing": "up"})
    kag.apply({"op": "set", "obj": "W6-1", "field": "turn", "value": "sideways"})
    top = kag.state()["places"]["deck"][-1]
    out = tmp_path / "kag.json"
    export(kag.defn, kag.state(), out)
    data = json.loads(out.read_text(encoding="utf-8"))
    objs = {o["GMNotes"]: o for o in data["ObjectStates"]}
    deck = next(o for o in data["ObjectStates"] if o["Name"] == "Deck")
    assert len(deck["ContainedObjects"]) == 22 and deck["ContainedObjects"][0]["GMNotes"] == top  # 先頭が山の上
    assert len(set(deck["DeckIDs"])) == 22 and all(str(i // 100) in deck["CustomDeck"] for i in deck["DeckIDs"])
    assert objs["W6-1"]["Transform"]["rotZ"] == 0 and objs["W6-1"]["Transform"]["rotY"] == 90  # 表・横向き
    assert any(o["Name"] == "HandTrigger" for o in data["ObjectStates"])
    assert len({o["GUID"] for o in data["ObjectStates"]}) == len(data["ObjectStates"])
    assert (tmp_path / "kag.png").exists() and "R1" in data["Rules"]


# ---------- 第二弾 ----------

def _hidden_def(tmp_path):
    h = copy.deepcopy(HIDDEN)
    h["objects"][1]["owner"] = "M"
    p = tmp_path / "hidden.yaml"
    p.write_text(yaml.safe_dump(h, allow_unicode=True), encoding="utf-8")
    return p


def test_AC_001_4_part_owner(tmp_path):
    assert load(_hidden_def(tmp_path)).parts["M-PAR"]["owner"] == "M"


def test_AC_009_3_legend_once(tmp_path):
    s = Session.create(tmp_path / "t", TTT, 2, {}, 1)
    v = view(s.defn, s.state(), None, meaning=True)
    assert "マス" in v["legend"]["kinds"]["cell"]["text"]
    assert all("meaning" not in v["areas"][f"c{r}{c}"] for r in "123" for c in "123")  # 各マスには繰り返さない
    assert "line" in v["legend"]["groups"]


def test_AC_009_4_parent_children(tmp_path):
    s = Session.create(tmp_path / "t", TTT, 2, {}, 1)
    v = view(s.defn, s.state(), None, meaning=True)
    assert len(v["areas"]["board"]["children"]) == 9 and v["areas"]["c22"]["parent"] == "board"


def test_AC_009_5_counted_kind(tmp_path):
    s = Session.create(tmp_path / "s", _hidden_def(tmp_path), 2, {}, 1)
    s.apply({"op": "move", "obj": "par", "from": "supply", "to": "doctor", "n": 1})
    it = view(s.defn, s.state(), None, meaning=True)["areas"]["board"]["shown"][0]["stacked"][0]
    assert it["kind"] == "counter" and it["count"] == 1


def test_AC_011_7_owner_from_back(tmp_path):
    s = Session.create(tmp_path / "s", _hidden_def(tmp_path), 2, {}, 1)
    s.apply({"op": "move", "obj": "M-PAR", "to": "doctor", "facing": "down"})
    it = view(s.defn, s.state(), "A")["areas"]["board"]["shown"][0]["stacked"][0]
    assert "id" not in it and it["owner"] == "M"


def test_AC_015_3_top_selector(kag):
    top = kag.state()["places"]["deck"][-1]
    st = kag.apply({"op": "move", "obj": "top:deck", "to": "hand-P1", "by": "P1", "rule": "R2"})
    assert st["places"]["hand-P1"] == [top] and len(st["places"]["deck"]) == 23
    assert kag.log()[-1]["obj"] == top  # 記録には実際に動かした部品の ID


def test_AC_015_4_placer_knows(tmp_path):
    s = Session.create(tmp_path / "s", _hidden_def(tmp_path), 2, {}, 1)
    st = s.apply({"op": "move", "obj": "M-PAR", "to": "doctor", "facing": "down", "by": "M", "rule": "R1"})
    assert st["known"]["M-PAR"] == ["M"] and st["states"]["M-PAR"]["facing"] == "down"


def test_AC_025_capacity_warning(tmp_path):
    s = Session.create(tmp_path / "t", TTT, 2, {}, 1)
    s.apply({"op": "move", "obj": "mark-X", "from": "supply-X", "to": "c22"})
    assert s.last_warnings == []  # AC-025-2
    s.apply({"op": "move", "obj": "mark-O", "from": "supply-O", "to": "c22"})
    assert s.last_warnings and "c22" in s.last_warnings[0] and len(s.log()) == 2  # AC-025-1（受け付けて警告）


def test_AC_026_reset(kag):
    kag.apply({"op": "progress", "key": "active", "value": "P2"})
    kag.apply({"op": "move", "obj": "W1-1", "to": "fire-P1", "facing": "up"})
    kag.apply({"op": "attach", "obj": "N1", "to": "W1-1"})
    kag.apply({"op": "know", "obj": "N2", "player": "P1"})
    st = kag.apply({"op": "reset", "by": "keeper"})
    assert len(st["places"]["deck"]) == 24 and st["states"]["W1-1"]["facing"] == "down"  # AC-026-1
    assert st["attached"] == {} and st["known"] == {}
    assert st["progress"]["active"] == "P2"  # AC-026-2


def test_AC_034_table_layout():
    from bgskills.definition import table_layout
    tl = table_layout(load(KAG, players=2))
    assert tl["seats"] == {"P1": "bottom", "P2": "top"} and tl["per_player"]["P2"] == ["player-P2"]  # AC-034-1
    r = raw(KAG)
    r["table"]["center"].append("deck2")
    assert {"where": "table", "ref": "deck2"} in check_refs(Definition(r))  # AC-034-2


def test_AC_035_hex_map():
    d = load(HEX)
    cells = d.areas["map"]["areas"]
    assert len(cells) == 19  # AC-035-1
    def deg(c):
        return sum(c in l["between"] for l in d.data["links"])
    assert deg("h0_0") == 6 and deg("h2_-2") == 3 and deg("h2_0") == 3  # 中心は 6、外周の角は 3（AC-035-2）
    assert {l["type"] for l in d.data["links"]} == {"e-w", "ne-sw", "nw-se"}
    assert check_refs(d) == []


def test_AC_037_tts_hex(tmp_path):
    import json, math
    from bgskills.tts import export
    s = Session.create(tmp_path / "h", HEX, 2, {}, 1)
    data = export(s.defn, s.state(), tmp_path / "h.json")
    pos = {o["GMNotes"][5:]: (o["Transform"]["posX"], o["Transform"]["posZ"]) for o in data["ObjectStates"]
           if o["GMNotes"].startswith("area:h")}
    assert len(pos) == 19
    dists = {round(math.dist(pos[a], pos[b]), 2) for a, b in (l["between"] for l in s.defn.data["links"])}
    assert len(dists) == 1  # 隣り合うマスの中心の距離がどれも等しい


def test_hex_play_and_tap(tmp_path):
    s = Session.create(tmp_path / "h", HEX, 2, {"R": "agent:a", "B": "agent:b"}, 1)
    s.apply({"op": "move", "obj": "top:reserve-R", "to": "h0_0", "by": "R", "rule": "R2"})
    st = s.apply({"op": "set", "obj": "R-3", "field": "posture", "value": "tapped", "by": "R", "rule": "R2"})
    assert st["places"]["h0_0"] == ["R-3"] and st["states"]["R-3"]["posture"] == "tapped"


# ---------- 表示方法（SPC-038）：回転 4 × 表裏 2 の 8 通り ----------

ORIENT = {
    "game": {"id": "orient", "version": 1, "players": {"min": 2, "max": 2}},
    "players": [{"id": "A"}, {"id": "B"}],
    "kinds": {"card": {"base": "object", "states": {"orientation": {
        f"{d}-{f}": {"text": f"{d}・{f}", "show": {"rotate": r, "face": "up" if f == "front" else "down"}}
        for f in ("front", "back") for d, r in (("up", 0), ("right", 90), ("down", 180), ("left", 270))}}}},
    "areas": [{"id": "table", "visibility": {"face": "all"}}],
    "objects": [{"id": "c1", "kind": "card", "start": "table"}],
}


@pytest.fixture
def orient(tmp_path):
    p = tmp_path / "o.yaml"
    p.write_text(yaml.safe_dump(ORIENT, allow_unicode=True, sort_keys=False), encoding="utf-8")  # 初期の状態は最初の値
    return Session.create(tmp_path / "s", p, 2, {}, 1)


def test_AC_038_1_display(orient):
    st = orient.apply({"op": "set", "obj": "c1", "field": "orientation", "value": "right-back"})
    assert orient.defn.display("card", st["states"]["c1"]) == {"rotate": 90, "face": "down"}


def test_AC_038_2_face_down_hidden(orient):
    orient.apply({"op": "set", "obj": "c1", "field": "orientation", "value": "right-back"})
    it = view(orient.defn, orient.state(), "A")["areas"]["table"]["shown"][0]
    assert "id" not in it and it["display"] == {"rotate": 90, "face": "down"}


def test_AC_038_3_tts_rotation(orient, tmp_path):
    from bgskills.tts import export
    orient.apply({"op": "set", "obj": "c1", "field": "orientation", "value": "right-back"})
    c = next(o for o in export(orient.defn, orient.state(), tmp_path / "o.json")["ObjectStates"] if o["Name"] == "Card")
    assert c["Transform"]["rotY"] == 90 and c["Transform"]["rotZ"] == 180


def test_rotate_and_flip_walk_eight_orientations(orient):
    seen = []
    for _ in range(4):
        seen.append(orient.apply({"op": "rotate", "obj": "c1"})["states"]["c1"]["orientation"])
    assert seen == ["right-front", "down-front", "left-front", "up-front"]  # 時計回りに 90 度ずつ
    assert orient.apply({"op": "flip", "obj": "c1"})["states"]["c1"]["orientation"] == "up-back"  # 回転は保つ
    assert orient.apply({"op": "rotate", "obj": "c1"})["states"]["c1"]["orientation"] == "right-back"


def test_rotate_tap_two_values(kag):
    kag.apply({"op": "move", "obj": "W1-1", "to": "fire-P1", "facing": "up"})
    assert kag.apply({"op": "rotate", "obj": "W1-1"})["states"]["W1-1"]["turn"] == "sideways"
    assert kag.apply({"op": "rotate", "obj": "W1-1"})["states"]["W1-1"]["turn"] == "upright"  # 90 → 0 に戻る


def test_AC_039_actions(kag):
    top = kag.state()["places"]["deck"][-1]
    st = kag.act("draw", "P1")
    assert st["places"]["hand-P1"] == [top] and kag.log()[-1]["action"] == "draw" and kag.log()[-1]["rule"] == "R2"  # AC-039-1
    kag.apply({"op": "move", "obj": "W5-2", "to": "hand-P1"})
    st = kag.act("stoke", "P1", {"card": "W5-2"})
    assert st["places"]["fire-P1"][-1] == "W5-2" and st["states"]["W5-2"]["facing"] == "up"  # AC-039-2
    n = len(kag.log())
    with pytest.raises(OpError):
        kag.act("guard", "P1", {"card": "N1", "wood": "nope"})  # 2 つ目以降が受け付けられない
    assert len(kag.log()) == n  # AC-039-3
    st = kag.act("discard", "P1", {"card": top})
    assert st["states"][top]["facing"] == "up"  # 捨て札は表向き
    r = raw(KAG)
    r["actions"][0]["rule"] = "R9"
    assert any(b["ref"] == "R9" for b in check_refs(Definition(r)))  # AC-039-4


# ---------- 箱・準備・入ったときの状態・手番と終了（SPC-043〜045） ----------

def test_AC_043_box_and_setup(tmp_path):
    from bgskills.session import compare_to_start
    assert "box" in load(TTT).areas  # AC-043-1
    s = Session.create(tmp_path / "b", KAG, 2, {}, 5, from_box=True)
    st = s.state()
    assert len(st["places"]["box"]) == 24 and st["places"]["deck"] == []  # AC-043-2
    st = s.act("setup", "P1")
    assert len(st["places"]["deck"]) == 18 and len(st["places"]["hand-P1"]) == 3 and len(st["places"]["hand-P2"]) == 3
    assert st["progress"]["active"] == "P1" and all(st["states"][o]["facing"] == "down" for o in st["places"]["deck"])  # AC-043-3
    cmp = compare_to_start(s.defn, st)
    assert not cmp["same"] and len(cmp["moved"]) == 6  # AC-043-4：手札に配った 6 枚
    assert "deck" in cmp["order_differs"]


def test_AC_044_on_enter(kag):
    st = kag.apply({"op": "move", "obj": "top:deck", "to": "hand-P1"})
    card = st["places"]["hand-P1"][0]
    assert st["states"][card]["facing"] == "down"
    st = kag.apply({"op": "move", "obj": card, "to": "discard", "by": "P1"})
    assert st["states"][card]["facing"] == "up"


def test_AC_045_end_turn_and_finish(kag):
    kag.apply({"op": "progress", "key": "active", "value": "P1"})
    st = kag.act("end-turn", "P1", {"next": "P2"})
    assert st["progress"] == {"active": "P2", "step": "draw"}  # AC-045-1
    st = kag.act("finish", "keeper", {"winner": "P1"})
    assert st["result"] == {"results": {"P1": "win", "P2": "lose"}, "rule": "R8"}  # AC-045-2


def test_kagaribi_full_game_by_actions(tmp_path):
    """かがり火を、箱から終了まで、アクションだけで遊べる（RUL-002 #22）。"""
    s = Session.create(tmp_path / "g", KAG, 2, {}, 11, from_box=True)
    s.act("setup", "P1")
    me, other = "P1", "P2"
    for turn in range(40):
        st = s.state()
        if not st["places"]["deck"]:
            break
        s.act("draw", me)
        hand = s.state()["places"][f"hand-{me}"]
        woods = [c for c in hand if c.startswith("W")]
        if woods:
            s.act("stoke", me, {"card": woods[0]})
        else:
            s.act("discard", me, {"card": hand[0]})
        s.act("end-turn", me, {"next": other})
        me, other = other, me
    s.act("finish", "keeper", {"winner": "P1"})
    assert s.state()["result"]["results"]["P1"] == "win" and not s.state()["places"]["deck"]


# ---------- 六角の頂点と辺・ダイス・ランダム・配布・並び順（SPC-046〜048） ----------

def _hex_with_corners(tmp_path):
    r = raw(HEX)
    r["areas"][0]["layout"]["hex"].update({"vertices": True, "edges": True, "vertex_kind": "corner", "edge_kind": "side"})
    r["kinds"]["corner"] = {"base": "area", "capacity": 1}
    r["kinds"]["side"] = {"base": "area", "capacity": 1}
    p = tmp_path / "hc.yaml"
    p.write_text(dump(r), encoding="utf-8")
    return p


def test_AC_046_vertices_edges(tmp_path):
    d = load(_hex_with_corners(tmp_path))
    kids = d.areas["map"]["areas"]
    assert sum(k.get("kind") == "corner" for k in kids) == 54 and sum(k.get("kind") == "side" for k in kids) == 72  # AC-046-1
    links = d.data["links"]
    def nb(a, t):
        return {x for l in links if l["type"] == t and a in l["between"] for x in l["between"] if x != a}
    assert len(nb("h0_0", "corner")) == 6 and len(nb("h0_0", "side")) == 6  # AC-046-2
    inner = next(v for v in (k["id"] for k in kids if k.get("kind") == "corner") if len(nb(v, "corner")) == 3)
    assert len(nb(inner, "end")) == 3 and len(nb(inner, "adjacent")) == 3  # AC-046-3
    assert check_refs(d) == []


DICE = {
    "game": {"id": "dice", "version": 1, "players": {"min": 2, "max": 2}},
    "players": [{"id": "A"}, {"id": "B"}],
    "kinds": {"die": {"base": "object", "states": {"face": {i: f"出目 {i}" for i in range(1, 7)}}},
              "card": {"base": "object"}, "tile": {"base": "object"}, "cell": {"base": "area"}},
    "areas": [{"id": "dice"}, {"id": "hand-A", "owner": "A", "visibility": {"face": "owner"}},
              {"id": "hand-B", "owner": "B", "visibility": {"face": "owner"}, "ordered": True},
              {"id": "grid", "areas": [{"id": f"g{i}", "kind": "cell"} for i in range(3)]}],
    "objects": [{"id": "d1", "kind": "die", "start": "dice"},
                {"id": "c{copy}", "kind": "card", "copies": 3, "start": "hand-B"},
                {"id": "gem", "kind": "card", "count": 2, "start": "hand-A"},
                {"id": "t{copy}", "kind": "tile", "copies": 3}],
}


@pytest.fixture
def dice(tmp_path):
    p = tmp_path / "d.yaml"
    p.write_text(yaml.safe_dump(DICE, allow_unicode=True, sort_keys=False), encoding="utf-8")
    return Session.create(tmp_path / "s", p, 2, {}, 99)


def test_AC_047_1_roll(dice):
    v = dice.apply({"op": "roll", "obj": "d1"})["states"]["d1"]["face"]
    assert v in range(1, 7) and Session(dice.dir).state()["states"]["d1"]["face"] == v  # 再生で同じ


def test_AC_047_2_random_pick(dice):
    st = dice.apply({"op": "move", "obj": "random:hand-B", "to": "hand-A", "by": "A"})
    assert len(st["places"]["hand-B"]) == 2 and dice.log()[-1]["obj"] in ("c1", "c2", "c3")
    st = dice.apply({"op": "move", "obj": "random:hand-A", "to": "hand-B", "by": "B"})  # 区別しない部品も 1 枚ずつ数える
    assert sum(1 if isinstance(o, str) else o.get("gem", 0) for o in st["places"]["hand-B"]) == 3


def test_AC_047_3_spread(dice):
    st = dice.apply({"op": "spread", "from": "box", "into": "grid", "kind": "tile", "into_kind": "cell"})
    assert all(len(st["places"][f"g{i}"]) == 1 for i in range(3)) and not [o for o in st["places"]["box"] if str(o).startswith("t")]


def test_AC_048_1_reorder(dice):
    st = dice.apply({"op": "move", "obj": "c3", "to": "hand-B", "at": 0, "by": "B"})
    assert st["places"]["hand-B"] == ["c3", "c1", "c2"]


def test_counted_hand_hidden_from_others(dice):
    v = view(dice.defn, dice.state(), "B")["areas"]["hand-A"]
    assert v["shown"] == {"count": 2} and "face" in v["hidden"]  # 資源の種類は見えず、枚数だけ


CATAN = Path(__file__).parent.parent / "local" / "catan.yaml"


@pytest.mark.skipif(not CATAN.exists(), reason="既存ゲームの検証用定義は公開しない（local/）")
def test_catan_reconstruction(tmp_path):
    s = Session.create(tmp_path / "c", CATAN, 3, {}, 2026, from_box=True)
    assert check_refs(s.defn) == []
    st = s.act("setup-board", "P1")
    tiles = {c: st["places"][c][0] for c in (a["id"] for a in s.defn.areas["map"]["areas"] if a.get("kind") == "hex")}
    assert len(tiles) == 19 and len(st["places"]["devdeck"]) == 25
    desert = next(c for c, t in tiles.items() if t == "T-desert")
    s.apply({"op": "move", "obj": "the-robber", "to": desert, "by": "keeper", "rule": "R1"})
    corners = [a["id"] for a in s.defn.areas["map"]["areas"] if a.get("kind") == "corner"]
    paths = [a["id"] for a in s.defn.areas["map"]["areas"] if a.get("kind") == "path"]
    for i, p in enumerate(["P1", "P2", "P3", "P3", "P2", "P1"]):  # 初期配置（往復）
        s.act("place-initial", p, {"piece": f"{p}-S{1 + (i >= 3)}", "corner": corners[i * 8]})
        s.act("place-initial-road", p, {"road": f"{p}-R{1 + (i >= 3)}", "path": paths[i * 11]})
    for _ in range(5):
        for res in ("brick", "lumber", "wool", "grain", "ore"):
            s.act("produce", "keeper", {"res": f"res-{res}", "to": "P1"})
    st = s.act("roll", "P1")
    assert {st["states"]["die-1"]["face"], st["states"]["die-2"]["face"]} <= set(range(1, 7))
    s.act("buy-dev", "P1")
    s.act("build-city", "P1", {"settlement": "P1-S1", "city": "P1-C1", "corner": corners[0]})
    s.act("trade-bank", "P1", {"give": "res-brick", "get": "res-ore"})
    s.act("steal", "P2", {"victim": "P1"})
    st = s.state()
    assert corners[0] in [c for c, items in st["places"].items() if "P1-C1" in items] and "P1-S1" in st["places"]["reserve-P1"]
    assert view(s.defn, st, "P3")["areas"]["hand-P1"]["shown"].keys() == {"count"}  # 他人の手札は枚数だけ
    s.act("finish", "keeper", {"winner": "P1"})
    assert s.state()["result"]["results"]["P1"] == "win"


# ---------- 指標（SPC-050） ----------

@pytest.mark.skipif(not CATAN.exists(), reason="既存ゲームの検証用定義は公開しない（local/）")
def test_AC_050_metrics_catan(tmp_path):
    s = Session.create(tmp_path / "c", CATAN, 3, {}, 3, from_box=True)
    s.act("setup-board", "P1")
    corners = [a["id"] for a in s.defn.areas["map"]["areas"] if a.get("kind") == "corner"]
    for i, piece in enumerate(["P1-S1", "P1-S2"]):
        s.apply({"op": "move", "obj": piece, "to": corners[i * 10]})
    s.apply({"op": "move", "obj": "P1-C1", "to": corners[30]})
    for k in ("D-knight-1", "D-knight-2"):
        s.apply({"op": "move", "obj": k, "to": "played-P1"})
    s.apply({"op": "move", "obj": "D-point-1", "to": "hand-P1"})
    m2 = view(s.defn, s.state(), "P2")["metrics"]
    assert m2["knights"]["values"]["P1"] == 2  # AC-050-1
    assert m2["cities"]["values"]["P1"] == 1 and m2["vp-public"]["values"]["P1"] == 4  # AC-050-2
    m1 = view(s.defn, s.state(), "P1")["metrics"]
    assert m1["vp-total"]["values"]["P1"] == 5 and "P1" not in m2["vp-total"]["values"]  # AC-050-3
    assert m2["hand-size"]["values"]["P1"] == 0  # 資源の枚数は全員に見える（needs: count。発展カードは数えない）


def test_AC_050_metrics_kagaribi_and_refs(kag):
    kag.apply({"op": "move", "obj": "W6-1", "to": "fire-P1", "facing": "up"})
    kag.apply({"op": "move", "obj": "W3-1", "to": "fire-P1", "facing": "up"})
    m = view(kag.defn, kag.state(), "P2")["metrics"]
    assert m["fire-total"]["values"]["P1"] == 9 and m["deck-size"]["value"] == 22
    r = raw(KAG)
    r["metrics"][0]["count"]["in"] = "fire2-{player}"
    assert any(b["ref"] == "fire2-{player}" for b in check_refs(Definition(r)))  # AC-050-4


# ---------- 進行の構造（SPC-051） ----------

FLOWDEF = {
    "game": {"id": "flow", "version": 1, "players": {"min": 3, "max": 3}},
    "players": [{"id": "A"}, {"id": "B"}, {"id": "C"}],
    "progress": {"active": {"text": "手番"}, "x": {"text": "印"}},
    "areas": [{"id": "t"}],
    "actions": [{"id": i, "steps": [{"op": "progress", "key": "x", "value": i}]} for i in ("place", "roll", "build", "dev", "react")],
    "flow": {
        "stages": [{"id": "init", "name": "初期配置", "order": "snake", "turn": "t1"},
                   {"id": "main", "name": "本番", "order": "seats", "turn": "t2"}],
        "turns": {"t1": {"phases": [{"id": "p", "main": ["place"], "max": 1}]},
                  "t2": {"phases": [{"id": "roll", "name": "ダイス", "main": ["roll"], "max": 1, "required": True},
                                    {"id": "build", "name": "建設", "main": ["build"]}],
                         "free": [{"action": "dev", "max": 1}], "reactions": [{"action": "react"}]}}},
}


@pytest.fixture
def fl(tmp_path):
    p = tmp_path / "f.yaml"
    p.write_text(yaml.safe_dump(FLOWDEF, allow_unicode=True, sort_keys=False), encoding="utf-8")
    return Session.create(tmp_path / "s", p, 3, {}, 1)


def test_AC_051_4_snake_then_main(fl):
    seen = []
    for _ in range(6):
        seen.append(fl.state()["flow"]["active"])
        fl.apply({"op": "advance"})
    assert seen == ["A", "B", "C", "C", "B", "A"]
    f = fl.state()["flow"]
    assert f["stage"] == "main" and f["active"] == "A" and f["phase"] == "roll" and fl.state()["progress"]["active"] == "A"


def _to_main(fl):
    for _ in range(6):
        fl.apply({"op": "advance"})


def test_AC_051_1_available(fl):
    _to_main(fl)
    av = view(fl.defn, fl.state(), "A")["flow"]["available"]
    assert av["main"] == ["roll"] and av["free"] == ["dev"]


def test_AC_051_2_over_limit_warns(fl):
    _to_main(fl)
    fl.act("roll", "A")
    assert fl.last_warnings == []
    fl.act("roll", "A")
    assert any("1 回まで" in w for w in fl.last_warnings) and fl.log()[-1]["action"] == "roll"


def test_AC_051_3_advance_to_next_turn(fl):
    _to_main(fl)
    fl.act("roll", "A")
    fl.apply({"op": "advance"})  # ダイス → 建設
    n = fl.state()["flow"]["turn_no"]
    fl.apply({"op": "advance"})  # 建設（最後） → 次の手番
    f = fl.state()["flow"]
    assert f["active"] == "B" and f["phase"] == "roll" and f["turn_no"] == n + 1


def test_AC_051_5_not_your_turn(fl):
    _to_main(fl)
    fl.act("build", "B")
    assert any("手番ではない" in w for w in fl.last_warnings) or any("フェーズ" in w for w in fl.last_warnings)
    fl.apply({"op": "advance"})  # 必須のフェーズを飛ばす
    assert any("必須" in w for w in fl.last_warnings)


# ---------- 条件と近傍（SPC-052） ----------

@pytest.mark.skipif(not CATAN.exists(), reason="既存ゲームの検証用定義は公開しない（local/）")
def test_AC_052_conditions_catan(tmp_path):
    from bgskills.query import candidates, neighbors
    s = Session.create(tmp_path / "c", CATAN, 3, {}, 4)
    d = s.defn
    center = next(a["id"] for a in d.areas["map"]["areas"] if a.get("pos") == [0, 0])
    corners = [o for o, _ in neighbors(d, center, "corner")]
    assert len(corners) == 6  # AC-052-3
    c0 = corners[0]
    s.act("place-initial", "P1", {"piece": "P1-S1", "corner": c0})
    assert s.last_warnings == []
    adj = next(o for o, _ in neighbors(d, c0, "adjacent"))
    s.act("place-initial", "P2", {"piece": "P2-S1", "corner": adj})
    assert any("距離の決まり" in w for w in s.last_warnings)  # AC-052-1
    good = {o for o, _ in neighbors(d, c0, "end")}
    cands = {c["id"]: c["problems"] for c in candidates(d, s.state(), "place-initial-road", "P1", "path")}
    assert all(cands[p] == [] for p in good)
    assert any("つながっていない" in m for p, ms in cands.items() if p not in good for m in ms)  # AC-052-2
    for res in ("brick", "lumber"):
        s.act("produce", "keeper", {"res": f"res-{res}", "to": "P1"})
    s.act("build-road", "P1", {"road": "P2-R1", "path": sorted(good)[0]})
    assert any("P1 の部品ではない" in w for w in s.last_warnings)  # AC-052-4


# ---------- 式・選択式・繰り返しの手順（SPC-053）：カタンの仕上げ ----------

@pytest.mark.skipif(not CATAN.exists(), reason="既存ゲームの検証用定義は公開しない（local/）")
def test_catan_full_rules(tmp_path):
    from bgskills.query import candidates, neighbors
    s = Session.create(tmp_path / "c", CATAN, 3, {}, 2026, from_box=True)
    d = s.defn
    st = s.act("setup-board", "keeper")
    hexes = [a["id"] for a in d.areas["map"]["areas"] if a.get("kind") == "hex"]
    nums = [c for c in hexes if any(str(o).startswith("num-") for o in st["places"][c])]
    assert len(nums) == 18 and not any(str(o).startswith("num-") for o in st["places"][s.state()["places"] and next(c for c in hexes if "T-desert" in st["places"][c])])
    assert sum(1 for a in d.areas if any(str(o).startswith("H-") for o in st["places"].get(a, []))) == 9  # 港 9 つ
    st = s.act("robber-to-desert", "keeper")
    desert = next(c for c in hexes if "T-desert" in st["places"][c])
    assert "the-robber" in st["places"][desert]
    s.apply({"op": "advance", "by": "keeper"})  # 準備 → 初期配置
    # 初期配置：条件を満たす候補から選ぶ（往復）
    for i, p in enumerate(["P1", "P2", "P3", "P3", "P2", "P1"]):
        cs = [c["id"] for c in candidates(d, s.state(), "place-initial", p, "corner") if not c["problems"]]
        corner = cs[len(cs) // 2]
        piece = next(o for o in s.state()["places"][f"reserve-{p}"] if o.startswith(f"{p}-S"))
        s.act("place-initial", p, {"piece": piece, "corner": corner})
        assert s.last_warnings == []
        road = next(o for o in s.state()["places"][f"reserve-{p}"] if o.startswith(f"{p}-R"))
        path = next(c["id"] for c in candidates(d, s.state(), "place-initial-road", p, "path") if not c["problems"])
        s.act("place-initial-road", p, {"road": road, "path": path})
        assert s.last_warnings == []
        if i >= 3:  # 2 つめの開拓地（フェーズは 2 回の配置で自動で次の手番へ進む）
            s.act("initial-resources", p, {"corner": corner})
    assert s.state()["flow"]["stage"] == "main"
    hand_total = lambda: sum(next(iter(o.values())) for p in d.players for o in s.state()["places"][f"hand-{p}"] if isinstance(o, dict))
    before = hand_total()
    for _ in range(6):  # 産出が起きるまで振る
        s.act("roll", s.state()["flow"]["active"])
        st = s.state()
        roll = st["states"]["die-1"]["face"] + st["states"]["die-2"]["face"]
        s.act("produce-all", "keeper")
        if roll != 7 and hand_total() > before:
            break
        s.apply({"op": "advance", "to": "turn", "by": "keeper"})
    assert hand_total() > before  # 出目で全員に産出された
    m = view(d, s.state(), None)["metrics"]
    assert all(m["longest-road"]["values"][p] >= 1 for p in d.players)
    # 奪う相手の条件：盗賊のタイルに建物がない人は警告
    cands = {c["id"]: c["problems"] for c in candidates(d, s.state(), "steal", "P1", "victim")}
    assert cands["P1"]  # 自分は選べない
    # 買った手番には使えない
    for res in ("wool", "grain", "ore"):
        s.act("produce", "keeper", {"res": f"res-{res}", "to": "P1"})
    s.act("buy-dev", "P1")
    card = next(o for o in s.state()["places"]["hand-P1"] if isinstance(o, str))
    s.act("play-dev", "P1", {"card": card})
    assert any("買った手番" in w or "勝利点" in w for w in s.last_warnings)
    # 勝利の検出
    for a in ("longest-road", "largest-army"):
        s.act("take-award", "keeper", {"award": a, "to": "P1"})
    empty = [c for c in (a["id"] for a in d.areas["map"]["areas"] if a.get("kind") == "corner") if not s.state()["places"][c]]
    for piece, corner in zip(["P1-S3", "P1-S4", "P1-S5", "P1-C2", "P1-C3"], empty):
        s.apply({"op": "move", "obj": piece, "to": corner})
    assert view(d, s.state(), None)["metrics"]["vp-total"]["values"]["P1"] >= 10
    assert view(d, s.state(), None)["flow"].get("end_signals")  # 10 点以上を知らせる


# ---------- 惨劇RoopeR（SPC-054）：周回・フェイズの行う人・知らせ ----------

TL = Path(__file__).parent.parent / "local" / "tragedy-looper.yaml"
TLS = Path(__file__).parent.parent / "local" / "tragedy-looper-scenario-s01.yaml"


@pytest.mark.skipif(not TL.exists(), reason="既存ゲームの検証用定義は公開しない（local/）")
def test_tragedy_looper_flow(tmp_path):
    s = Session.create(tmp_path / "t", TL, 4, {}, 1, scenario=TLS)
    f = lambda: s.state()["flow"]
    s.act("loop-reset", "M")
    s.apply({"op": "advance"})
    leaders = []
    for day in range(7):
        leaders.append(f()["active"])
        if day == 0:  # ターン開始は通り過ぎて、脚本家行動から
            s.act("set-on-board", "A", {"card": "A-INTX", "target": "SHR"})
            assert any("行うのは M" in w for w in s.last_warnings)  # AC-054-2
            s.undo()
        while f()["stage"] == "days" and f()["turn_in_stage"] == day:
            s.apply({"op": "advance"})
    assert leaders[:4] == ["A", "B", "C", "A"]  # AC-054-3
    assert f()["stage"] == "prep" and f()["cycle"] == 2  # AC-054-1
    for _ in range(2):  # 2・3 周目
        s.act("loop-reset", "M")
        s.apply({"op": "advance"})
        while f()["stage"] == "days":
            s.apply({"op": "advance"})
    assert f()["stage"] == "final"
    # AC-054-4：今日の事件（2 日目：女子学生 C02 の不安拡大、不安臨界 3）
    s2 = Session.create(tmp_path / "t2", TL, 4, {}, 1, scenario=TLS)
    s2.act("loop-reset", "M")
    s2.apply({"op": "advance"})
    while not (s2.state()["flow"]["turn_in_stage"] == 1 and s2.state()["flow"]["phase"] == "incident"):
        s2.apply({"op": "advance"})
    s2.act("add-counter", "M", {"counter": "paranoia", "n": "2", "target": "C02"})
    s2.act("add-counter", "M", {"counter": "paranoia", "n": "1", "target": "C02"})
    assert any("今日の事件" in x for x in view(s2.defn, s2.state(), None)["flow"].get("signals", []))
    assert "signals" not in view(s2.defn, s2.state(), "A")["flow"]


@pytest.mark.skipif(not CATAN.exists(), reason="既存ゲームの検証用定義は公開しない（local/）")
def test_catan_review_fixes(tmp_path):
    from bgskills.cli import _visible_ops
    from bgskills.expr import evaluate
    from bgskills.query import neighbors
    s = Session.create(tmp_path / "c", CATAN, 3, {}, 7, from_box=True)
    d = s.defn
    s.act("setup-board", "keeper")
    # 分かれ道：交点 x に 3 本の街道が集まる（Y 字）→ 最長は 2 本
    x = next(a["id"] for a in d.areas["map"]["areas"] if a.get("kind") == "corner" and len(neighbors(d, a["id"], "end")) == 3)
    for i, p in enumerate(o for o, _ in neighbors(d, x, "end")):
        s.apply({"op": "move", "obj": f"P1-R{i + 1}", "to": p})
    assert view(d, s.state(), None)["metrics"]["longest-road"]["values"]["P1"] == 2
    # 港は辺の空きに数えない
    harbor_path = next(a for a in d.areas if any(str(o).startswith("H-") for o in s.state()["places"].get(a, [])))
    assert evaluate("1", d, s.state()) == 1
    from bgskills.query import holds
    assert holds(d, s.state(), harbor_path, {"empty": True})
    # 奪った資源は第三者に見えない
    s.act("produce", "keeper", {"res": "res-ore", "to": "P1"})
    s.apply({"op": "move", "obj": "random:hand-P1", "kind": "resource", "to": "hand-P2", "by": "P2"})
    assert _visible_ops(s, s.state(), s.log()[-1:], "P3")[0]["obj"] == "（見えない部品）"
    assert _visible_ops(s, s.state(), s.log()[-1:], "P1")[0]["obj"] == "res-ore"
    # 区別しないコマは省ける（pick: first）、2 回の配置でフェーズが自動で進む
    s.act("robber-to-desert", "keeper")
    s.apply({"op": "advance"})
    free = lambda x: holds(d, s.state(), x, {"empty": True})
    corner = next(a["id"] for a in d.areas["map"]["areas"] if a.get("kind") == "corner" and free(a["id"])
                  and all(free(o) for o, _ in neighbors(d, a["id"], "adjacent")) and all(free(o) for o, _ in neighbors(d, a["id"], "end")))
    s.act("place-initial", "P1", {"corner": corner})
    path = next(o for o, _ in neighbors(d, corner, "end") if free(o))
    s.act("place-initial-road", "P1", {"path": path})
    assert s.state()["flow"]["active"] == "P2"



@pytest.mark.skipif(not TL.exists(), reason="既存ゲームの検証用定義は公開しない（local/）")
def test_tragedy_looper_resolution_and_rules(tmp_path):
    s = Session.create(tmp_path / "t", TL, 4, {}, 1, scenario=TLS)
    assert "role-C07" not in load(TL, 4).parts and "role-C07" in s.defn.parts  # 脚本はシナリオにだけある
    f = lambda: s.state()["flow"]
    s.act("loop-reset", "M")
    s.apply({"op": "advance"})
    assert f()["phase"] == "mm-action"  # ターン開始は通り過ぎる（pass）
    # 脚本家：神社に暗躍+1、医者に不安+1、情報屋（都市）に移動↑↓
    s.act("set-on-board", "M", {"card": "M-INT1", "target": "SHR"})
    s.act("set-on-character", "M", {"card": "M-PARp1", "target": "C08"})
    s.act("set-on-character", "M", {"card": "M-MV_V", "target": "C07"})
    assert f()["phase"] == "pc-action"  # 3 枚で自動で進む（auto）
    s.act("set-on-board", "B", {"card": "B-INTX", "target": "SHR"})
    assert any("順番は A" in w for w in s.last_warnings)  # リーダー（A）から
    s.undo()
    s.act("set-on-board", "A", {"card": "A-INTX", "target": "SHR"})
    s.act("set-on-character", "B", {"card": "B-MV_H", "target": "C07"})
    s.act("set-on-character", "C", {"card": "C-GW1", "target": "C04"})
    assert f()["phase"] == "resolve"
    s.act("reveal", "M")
    st = s.act("resolve-cards", "M")
    from bgskills.expr import evaluate
    assert evaluate("count_on('SHR', kind='intrigue')", s.defn, st) == 0  # 暗躍禁止で打ち消し
    assert evaluate("count_on('C08', kind='paranoia')", s.defn, st) == 1
    assert evaluate("where('C07')", s.defn, st) == "SHR"  # 都市から ↑↓＋←→＝斜め → 神社
    assert evaluate("count_on('C04', kind='goodwill')", s.defn, st) == 1
    s.act("return-cards", "M")
    assert "M-MV_V" in s.state()["places"]["hand-M"]
    s.act("kill", "A", {"char": "C01"})
    assert any("行うのは M" in w for w in s.last_warnings)  # 脚本家のアクション
    s.undo()
    # ループの終わり：勝敗と因果の糸の記憶
    s.act("loop-end", "M")
    st = s.state()
    assert st["progress"]["loop_results"] == ["protagonists"] and "C04" in st["progress"]["thread_prev"]
    view(s.defn, st, "A", meaning=True)  # 一覧の値の進行状態でも意味つきの局面を作れる
    assert f()["stage"] == "prep" and f()["cycle"] == 2
    s.act("loop-reset", "M")
    st = s.act("loop-start-effects", "M")
    assert evaluate("count_on('C04', kind='paranoia')", s.defn, st) == 2  # 因果の糸


@pytest.mark.skipif(not TL.exists(), reason="既存ゲームの検証用定義は公開しない（local/）")
def test_strict_mode_rejects(tmp_path):
    s = Session.create(tmp_path / "t", TL, 4, {}, 1, strict=True, scenario=TLS)
    s.act("loop-reset", "M")
    s.apply({"op": "advance"})
    n = len(s.log())
    with pytest.raises(OpError, match="厳格モード"):
        s.act("set-on-board", "A", {"card": "A-INTX", "target": "SHR"})  # 脚本家行動のフェイズに主人公
    assert len(s.log()) == n



@pytest.mark.skipif(not TL.exists(), reason="既存ゲームの検証用定義は公開しない（local/）")
def test_tragedy_looper_data_board(tmp_path):
    """データボードの目印は、日・ループに入ったときに動く（進行の on_start。記録には残らない）。"""
    s = Session.create(tmp_path / "t", TL, 4, {}, 1, scenario=TLS)
    where = lambda o: next(c for c, xs in s.state()["places"].items() if o in xs)
    assert where("day-marker") == "day-1" and where("loop-marker") == "loop-3"
    s.act("loop-reset", "M")
    s.apply({"op": "advance", "to": "stage"})  # 1 日目へ
    assert where("day-marker") == "day-1"
    n = len(s.log())
    s.apply({"op": "advance", "to": "turn"})
    assert where("day-marker") == "day-2" and len(s.log()) == n + 1  # 目印の移動は記録に足さない
    s.act("loop-end", "M")  # 次のループの準備へ
    assert where("loop-marker") == "loop-2"
    v = view(s.defn, s.state(), "A")["areas"]
    assert any(it.get("id", "").startswith("affair-marker") for it in v["affair-2"]["shown"])  # 事件の日は公開
