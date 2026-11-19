"""発言・交渉・隠れた情報（RUL-009）：人狼（公開）、花火・ディプロマシー（local/。公開しない）。"""
from pathlib import Path

import pytest

from bgskills.cli import _visible_ops
from bgskills.definition import load
from bgskills.query import neighbors
from bgskills.session import OpError, Session
from bgskills.tools import check_refs
from bgskills.view import view

ROOT = Path(__file__).parent.parent
WEREWOLF = ROOT / "examples" / "werewolf.yaml"
HANABI = ROOT / "local" / "hanabi.yaml"
DIPLOMACY = ROOT / "local" / "diplomacy.yaml"
LOCAL = "既存ゲームの検証用定義は公開しない（local/）"


def role_of(s, st, p):
    return s.defn.parts[st["places"]["role-" + p][0]]["kind"]


def test_werewolf_night_and_day(tmp_path):
    assert check_refs(load(WEREWOLF, 6)) == []
    s = Session.create(tmp_path / "w", WEREWOLF, 6, {}, 4, strict=False)
    s.act("setup", "keeper")
    s.act("wolves-meet", "keeper")
    st = s.state()
    roles = {p: role_of(s, st, p) for p in s.defn.players}
    wolves = [p for p, r in roles.items() if r == "werewolf"]
    seer = next(p for p, r in roles.items() if r == "seer")
    knight = next(p for p, r in roles.items() if r == "knight")
    village = [p for p in s.defn.players if p not in wolves]
    assert len(wolves) == 2
    # 自分の役職は見え、ほかの村人の役職は見えない。人狼どうしは互いを知る
    v = view(s.defn, st, village[0])
    assert v["areas"]["role-" + village[0]]["shown"][0]["kind"] == roles[village[0]]
    assert "hidden" in v["areas"]["role-" + village[1]]
    vw = view(s.defn, st, wolves[0])
    assert vw["areas"]["role-" + wolves[1]]["shown"][0]["kind"] == "werewolf"

    s.apply({"op": "advance"})  # 夜
    s.apply({"op": "say", "by": wolves[0], "to": [wolves[1]], "text": "占い師を狙おう"})
    assert not s.last_warnings  # 夜は人狼どうしだけ話せる
    s.apply({"op": "say", "by": village[0], "text": "眠れない"})
    assert s.last_warnings and "人狼どうし" in s.last_warnings[0]
    talk = view(s.defn, s.state(), village[1])["talk"]
    assert talk[0]["text"] == "眠れない" and all(t["by"] != wolves[0] for t in talk)  # 夜（whisper: hidden）の内緒話は、あったことも見えない
    assert not any(o.get("op") == "say" and o.get("by") == wolves[0] for o in _visible_ops(s, s.state(), s.log(), village[1]))
    assert view(s.defn, s.state(), wolves[1])["talk"][0]["text"] == "占い師を狙おう"

    victim = next(p for p in village if p not in (seer, knight))
    s.act("attack", wolves[0], {"target": victim})
    s.act("guard", knight, {"target": seer})
    s.act("divine", seer, {"target": wolves[1]})
    # 占い師は陣営だけを知る（役職の名前は分からない）
    card = view(s.defn, s.state(), seer)["areas"]["role-" + wolves[1]]["shown"][0]
    assert card["known"] == {"side": "wolf"} and "kind" not in card
    # 夜の行動は、ほかの人の記録では中身も相手も見えない
    seen = _visible_ops(s, s.state(), s.log(), village[1])
    assert not any(o.get("action") in ("attack", "guard", "divine") for o in seen)  # あったことも件数も見えない（ループ 21）
    assert any(o.get("action") == "divine" for o in _visible_ops(s, s.state(), s.log(), seer))  # 本人には見える
    s.act("dawn", "keeper")
    st = s.state()
    assert st["states"]["life-" + victim]["status"] == "dead"
    assert "無残" in st["talk"][-1]["text"]

    s.apply({"op": "advance"})  # 昼
    s.apply({"op": "say", "by": victim, "text": "犯人は…"})
    assert s.last_warnings  # 死んだ人は話せない
    alive = [p for p in s.defn.players if p != victim]
    for p in alive:
        s.act("vote", p, {"target": wolves[0] if p != wolves[0] else seer})
    # 開く前は、自分の票だけが見える（封をした選択）
    v = view(s.defn, s.state(), village[0])
    mine = next(i for i in v["areas"]["ballots"]["shown"] if i.get("id") == "ballot-" + village[0])
    assert mine["state"]["target"] == wolves[0]
    assert sum("hidden" in i for i in v["areas"]["ballots"]["shown"]) == 5
    s.act("open-votes", "keeper")
    m = view(s.defn, s.state(), village[0])["metrics"]["votes"]["values"]
    assert m[wolves[0]] == 4 and m[seer] == 1
    s.act("execute", "keeper", {"target": wolves[0]})
    assert s.state()["states"]["life-" + wolves[0]]["status"] == "dead"


def test_free_state_types(tmp_path):
    s = Session.create(tmp_path / "w", WEREWOLF, 5, {}, 1)
    with pytest.raises(OpError, match="player"):
        s.apply({"op": "set", "obj": "ballot-P1", "field": "target", "value": "P9"})
    with pytest.raises(OpError, match="聞かせる相手"):
        s.apply({"op": "say", "by": "P1", "to": ["P9"], "text": "x"})


@pytest.mark.skipif(not HANABI.exists(), reason=LOCAL)
def test_hanabi_hidden_own_hand_and_hints(tmp_path):
    assert check_refs(load(HANABI, 3)) == []
    s = Session.create(tmp_path / "h", HANABI, 3, {}, 2)
    s.act("setup", "keeper")
    s.apply({"op": "advance"})
    st = s.state()
    assert [len(st["places"]["hand-" + p]) for p in s.defn.players] == [5, 5, 5]
    v = view(s.defn, st, "P1")
    assert v["areas"]["hand-P1"]["shown"] == {"count": 5}  # 自分の手札だけ見えない
    assert v["areas"]["hand-P2"]["shown"][0]["attributes"]["number"] in range(1, 6)
    s.apply({"op": "say", "by": "P1", "text": "P2 の 1 枚目を出して"})
    assert s.last_warnings  # ヒント以外で手札のことを話さない
    color = s.defn.parts[st["places"]["hand-P2"][0]]["attributes"]["color"]
    s.act("hint", "P1", {"target": "P2", "clue": color})
    v = view(s.defn, s.state(), "P2")["areas"]["hand-P2"]["shown"]
    assert v[0]["known"] == {"color": color} and "attributes" not in v[0]
    assert "左から 1" in s.state()["talk"][-1]["text"]
    # 自分が引いた札は、記録でも伏せる
    s.act("discard", "P2", {"slot": "2"})
    seen = _visible_ops(s, s.state(), s.last_ops, "P2")
    assert any(o.get("to") == "hand-P2" and o["obj"] == "（見えない部品）" for o in seen)


@pytest.mark.skipif(not DIPLOMACY.exists(), reason=LOCAL)
def test_diplomacy_map_and_spring_1901(tmp_path):
    d = load(DIPLOMACY)
    assert check_refs(d) == []
    prov = [a["id"] for a in d.areas["board"]["areas"]]
    kinds = {p: d.areas[p]["kind"] for p in prov}
    assert len(prov) == 75 and sorted(kinds.values()).count("sea") == 19
    assert len([o for o in d.parts if o.startswith("sc-")]) == 34
    nb = lambda a, t: sorted(o for o, _ in neighbors(d, a, t))
    assert nb("mun", "army") == ["ber", "boh", "bur", "kie", "ruh", "sil", "tyr"]
    assert nb("nth", "fleet") == ["bel", "den", "edi", "eng", "hel", "hol", "lon", "nwg", "nwy", "ska", "yor"]
    assert all(not nb(p, "fleet") for p in prov if kinds[p] == "inland")
    assert all(not nb(p, "army") for p in prov if kinds[p] == "sea")

    s = Session.create(tmp_path / "d", DIPLOMACY, 7, {}, 1)
    v = view(s.defn, s.state(), "france")
    assert v["metrics"]["centers"]["values"]["russia"] == 4 and v["metrics"]["year"]["value"] == 1901
    s.apply({"op": "say", "by": "france", "to": ["england"], "text": "海峡には入らない"})  # 外交：内緒話
    assert not s.last_warnings
    assert view(s.defn, s.state(), "germany")["talk"][0]["text"] == "（内緒話）"
    s.apply({"op": "advance"})  # 春・命令
    s.act("write-orders", "france", {"text": "A par-bur; A mar-spa; F bre-mao"})
    s.act("write-orders", "germany", {"text": "A mun-bur; A ber-kie; F kie-den"})
    s.apply({"op": "say", "by": "germany", "text": "やっぱり"})
    assert s.last_warnings  # 命令を書いている間は話さない
    v = view(s.defn, s.state(), "germany")
    assert v["areas"]["orders-germany"]["shown"][0]["state"]["text"].startswith("A mun")
    assert "hidden" in v["areas"]["orders-france"]  # ほかの国の命令は見えない
    s.act("reveal-orders", "keeper")
    v = view(s.defn, s.state(), "germany")
    texts = {i["id"]: i["state"].get("text") for i in v["areas"]["open-orders"]["shown"]}  # 書かなかった国は空（維持）
    assert texts["sheet-france"].startswith("A par-bur")
    s.apply({"op": "advance"})  # 春・解決（par-bur と mun-bur はにらみ合い。キーパーが規則で解決する）
    s.act("move-unit", "keeper", {"unit": "fra-A2", "to": "spa"})
    s.act("move-unit", "keeper", {"unit": "fra-F1", "to": "mao"})
    assert not s.last_warnings
    s.act("move-unit", "keeper", {"unit": "ger-F1", "to": "swe"})
    assert s.last_warnings  # キールからスウェーデンは隣でない
    s.undo()
    s.act("return-orders", "keeper")
    assert view(s.defn, s.state(), "france")["areas"]["orders-france"]["shown"][0]["state"]["text"] == ""


TRADE = """
format: bg-def/0.1
game: {id: trade, name: 交換, version: 1, players: {min: 3, max: 3}}
players: [{id: P1}, {id: P2}, {id: P3}]
kinds:
  res: {base: object, distinct: false}
  wood: {base: res}
  ore: {base: res}
areas:
  - {id: "hand-{player}", for_each: {player: players}, owner: "{player}"}
  - {id: bank}
objects:
  - {id: w1, kind: wood, count: 3, start: hand-P1}
  - {id: o1, kind: ore, count: 1, start: hand-P2}
"""


def test_offer_and_answer(tmp_path):
    """守られる約束（RUL-009 D6）：提案は受けたらまとめて行い、断る・取り下げ・条件を変えて返すで閉じる。"""
    (tmp_path / "trade.yaml").write_text(TRADE, encoding="utf-8")
    s = Session.create(tmp_path / "t", tmp_path / "trade.yaml", 3, {}, 1)
    give = [{"op": "move", "obj": "w1", "from": "hand-P1", "to": "hand-P2", "n": 2},
            {"op": "move", "obj": "o1", "from": "hand-P2", "to": "hand-P1", "by": "P2"}]
    s.apply({"op": "say", "by": "P1", "to": ["P2"], "text": "木 2 と鉱石 1", "offer": give})       # 0
    with pytest.raises(OpError, match="相手ではない"):
        s.apply({"op": "answer", "by": "P3", "talk": 0, "accept": True})
    s.apply({"op": "say", "by": "P2", "to": ["P1"], "text": "木 3 なら", "reply_to": 0,          # 1（0 は閉じる）
             "offer": [{**give[0], "n": 3}, give[1]]})
    with pytest.raises(OpError, match="閉じている"):
        s.apply({"op": "answer", "by": "P2", "talk": 0, "accept": True})
    s.apply({"op": "answer", "by": "P1", "talk": 1, "accept": True})                           # 2
    st = s.state()
    assert st["places"]["hand-P1"] == [{"o1": 1}] and st["places"]["hand-P2"] == [{"w1": 3}]
    assert [t.get("status") for t in st["talk"]] == ["countered", "accepted", None]
    assert view(s.defn, st, "P3")["talk"][1]["text"] == "（内緒話）" and "offer" not in view(s.defn, st, "P3")["talk"][1]
    # 果たせない提案は、受けても何も動かない
    s.apply({"op": "say", "by": "P1", "text": "鉱石 5 あげる", "offer": [{**give[1], "obj": "o1", "from": "hand-P1", "to": "hand-P3", "n": 5}]})
    with pytest.raises(OpError, match="行えない"):
        s.apply({"op": "answer", "by": "P3", "talk": 3, "accept": True})
    s.apply({"op": "answer", "by": "P1", "talk": 3, "accept": False})  # 取り下げ
    assert s.state()["talk"][3]["status"] == "withdrawn" and s.state()["places"]["hand-P1"] == [{"o1": 1}]


def test_compact_talk_tail(tmp_path, capsys):
    """長い議論：--compact は最後の 10 件と受付中の提案だけ。番号（n）は bg answer に使える。"""
    import yaml
    from bgskills.cli import main
    (tmp_path / "trade.yaml").write_text(TRADE, encoding="utf-8")
    s = Session.create(tmp_path / "t", tmp_path / "trade.yaml", 3, {}, 1)
    s.apply({"op": "say", "by": "P1", "text": "交換", "offer": [{"op": "move", "obj": "w1", "from": "hand-P1", "to": "hand-P2"}]})
    for i in range(30):
        s.apply({"op": "say", "by": "P2", "text": f"議論 {i}"})
    main(["show", str(s.dir), "--as", "P3", "--compact"])
    v = yaml.safe_load(capsys.readouterr().out)
    assert [t["n"] for t in v["talk"]] == [0] + list(range(21, 31)) and "20 件" in v["talk_omitted"]
    main(["show", str(s.dir), "--talk-since", "29"])
    assert [t["n"] for t in yaml.safe_load(capsys.readouterr().out)["talk"]] == [0, 29, 30]


def test_condition_before_setup_is_unmet_not_error(tmp_path):
    """配る前（役職の札がない）に条件を読んでも式の誤りにせず、条件を満たさないだけにする（ループ 4 のでたらめ実行で見つけた）。"""
    from bgskills.expr import evaluate
    s = Session.create(tmp_path / "w", WEREWOLF, 6, {}, 1)
    assert evaluate("kind(on1('role-P1')) == 'knight'", s.defn, s.state()) is False
    assert evaluate("attr(on1('role-P1'), 'side')", s.defn, s.state()) is None


def test_werewolf_runoff(tmp_path):
    """決選投票（R8）：最多票が同数なら同数の人の中で投票し直し、なお同数なら誰も処刑しない（条件は候補と警告で示す）。"""
    from bgskills.query import candidates
    s = Session.create(tmp_path / "w", WEREWOLF, 5, {}, 1, strict=False)
    s.act("setup", "keeper")

    def vote(pairs):
        for a, b in pairs:
            s.act("vote", a, {"target": b})
        s.act("open-votes", "keeper")

    def ok(action, who, prm):
        return [c["id"] for c in candidates(s.defn, s.state(), action, who, prm, {}) if not c["problems"]]

    vote([("P1", "P2"), ("P2", "P1"), ("P3", "P1"), ("P4", "P2"), ("P5", "P3")])
    assert ok("execute", "keeper", "target") == []  # 同数なので処刑できる人はいない
    s.act("runoff", "keeper")
    assert s.state()["progress"]["runoff"] == ["P1", "P2"] and "決選投票：P1・P2" in s.state()["talk"][-1]["text"]
    assert ok("vote", "P5", "target") == ["P1", "P2"]
    vote([("P1", "P2"), ("P2", "P1"), ("P3", "P1"), ("P4", "P2"), ("P5", "P1")])
    assert ok("execute", "keeper", "target") == ["P1"]
    s.act("execute", "keeper", {"target": "P1"})
    st = s.state()
    assert st["states"]["life-P1"]["status"] == "dead" and st["progress"]["runoff"] == []


def test_offer_is_between_two_players(tmp_path):
    """カタンの試し遊び（ループ 13）で見つけた穴：提案は 2 人の約束。持ち主のない置き場（銀行）・3 人目の物は入れられず、
    答えられるのは持ち物が動く相手だけ。受けられないときの理由は相手の手札を明かさない。"""
    (tmp_path / "trade.yaml").write_text(TRADE, encoding="utf-8")
    s = Session.create(tmp_path / "t", tmp_path / "trade.yaml", 3, {}, 1)
    take = {"op": "move", "obj": "o1", "from": "hand-P2", "to": "hand-P1"}
    with pytest.raises(OpError, match="持ち主のない置き場"):
        s.apply({"op": "say", "by": "P1", "text": "銀行から", "offer": [{"op": "move", "obj": "w1", "from": "bank", "to": "hand-P1"}]})
    with pytest.raises(OpError, match="部品の ID ではない（w1 のことか）"):
        s.apply({"op": "say", "by": "P1", "text": "x", "offer": [{**take, "obj": "wood"}]})
    with pytest.raises(OpError, match="聞かせていない P2"):
        s.apply({"op": "say", "by": "P1", "to": ["P3"], "text": "x", "offer": [take]})
    s.apply({"op": "say", "by": "P1", "text": "鉱石ちょうだい", "offer": [take]})  # 0：相手は P2（to なしでも）
    assert s.state()["talk"][0]["with"] == "P2"
    assert view(s.defn, s.state(), "P2").get("offers_for_me") == [0] and "offers_for_me" not in view(s.defn, s.state(), "P3")
    with pytest.raises(OpError, match="答えられるのは P2"):
        s.apply({"op": "answer", "by": "P3", "talk": 0, "accept": True})
    s.apply({"op": "say", "by": "P1", "text": "木 5 あげる", "offer": [{"op": "move", "obj": "w1", "from": "hand-P1", "to": "hand-P2", "n": 5}]})
    assert any("出せない" in w for w in s.last_warnings)  # 出した人には自分の持ち物の不足を知らせる
    s.apply({"op": "say", "by": "P1", "text": "鉱石 3 ちょうだい", "offer": [{**take, "n": 3}]})
    with pytest.raises(OpError) as e:
        s.apply({"op": "answer", "by": "P2", "talk": 2, "accept": True})
    assert "今は行えない" in str(e.value) and "1 個" not in str(e.value)


def test_offer_checks_flow_via_action(tmp_path):
    """提案に action（か flow.offer_action）を書くと、受けたときに出した人がそのアクションを行ったことにして、手番と条件を確かめる。"""
    yaml_text = TRADE + """
actions:
  - {id: trade, name: 交換, require: [{expr: "actor == active()", text: 手番の人だけが交換できる}], steps: []}
flow:
  offer_action: trade
  stages:
    - {id: main, name: 本番, order: seats, turn: main}
  turns:
    main:
      phases:
        - {id: build, name: 交易, main: [trade]}
"""
    (tmp_path / "trade.yaml").write_text(yaml_text, encoding="utf-8")
    s = Session.create(tmp_path / "t", tmp_path / "trade.yaml", 3, {}, 1)
    take = {"op": "move", "obj": "o1", "from": "hand-P2", "to": "hand-P1"}  # 手番は P1
    s.apply({"op": "say", "by": "P3", "text": "x", "offer": [{**take, "to": "hand-P3"}]})  # P3 は手番ではない
    s.apply({"op": "answer", "by": "P2", "talk": 0, "accept": True})
    assert any("手番" in w for w in s.last_warnings)
    s.apply({"op": "say", "by": "P1", "text": "y", "offer": [{**take, "from": "hand-P3"}]})
    s.apply({"op": "answer", "by": "P3", "talk": 2, "accept": True})
    assert s.last_warnings == [] and s.state()["flow"]["counts"]["turn"].get("trade") == 2  # 警告つきの 1 回目も数える


def test_talk_numbers_not_reused_after_undo(tmp_path):
    """undo した発言の番号は使い回さない（覚えた番号で別の提案を受けないように。ループ 13 の試し遊び）。"""
    (tmp_path / "trade.yaml").write_text(TRADE, encoding="utf-8")
    s = Session.create(tmp_path / "t", tmp_path / "trade.yaml", 3, {}, 1)
    take = {"op": "move", "obj": "o1", "from": "hand-P2", "to": "hand-P1"}
    s.apply({"op": "say", "by": "P1", "text": "a", "offer": [take]})            # 0
    s.apply({"op": "say", "by": "P1", "text": "b", "offer": [take]})            # 1
    s.undo()
    s.apply({"op": "say", "by": "P1", "text": "c", "offer": [{**take, "n": 1}]})  # 2（1 は使わない）
    assert [t["n"] for t in s.state()["talk"]] == [0, 2]
    with pytest.raises(OpError, match="#1 は提案ではない"):
        s.apply({"op": "answer", "by": "P2", "talk": 1, "accept": True})
    s.apply({"op": "answer", "by": "P2", "talk": 2, "accept": True})
    assert s.state()["talk"][1]["status"] == "accepted" and s.state()["talk"][-1]["answer"] == 2


def test_show_only_parts(tmp_path, capsys):
    """bg show --only：エリアのほかに、局面の部分（talk・flow・offers_for_me など）だけを出せる。"""
    import yaml
    from bgskills.cli import main
    (tmp_path / "trade.yaml").write_text(TRADE, encoding="utf-8")
    s = Session.create(tmp_path / "t", tmp_path / "trade.yaml", 3, {}, 1)
    s.apply({"op": "say", "by": "P1", "text": "鉱石ちょうだい", "offer": [{"op": "move", "obj": "o1", "from": "hand-P2", "to": "hand-P1"}]})
    capsys.readouterr()
    main(["show", str(s.dir), "--as", "P2", "--only", "hand-P2,talk,offers_for_me"])
    v = yaml.safe_load(capsys.readouterr().out)
    assert set(v) == {"for", "game", "version", "areas", "talk", "offers_for_me"} and list(v["areas"]) == ["hand-P2"]
    main(["show", str(s.dir), "--as", "P2", "--only", "talk"])
    assert "areas" not in yaml.safe_load(capsys.readouterr().out)


def test_rebase_after_definition_edit(tmp_path):
    """bg rebase：定義を直した後、記録が今の定義で再生できれば対局を今の定義に合わせ、できなければ何も変えない。"""
    p = tmp_path / "trade.yaml"
    p.write_text(TRADE, encoding="utf-8")
    s = Session.create(tmp_path / "t", p, 3, {}, 1)
    s.apply({"op": "move", "obj": "w1", "from": "hand-P1", "to": "hand-P2", "n": 2})
    p.write_text(TRADE.replace("name: 交換", "name: 交換（改）"), encoding="utf-8")
    assert Session(s.dir).load_warnings
    assert Session(s.dir).rebase() == 1 and not Session(s.dir).load_warnings
    p.write_text(TRADE.replace("count: 3", "count: 1"), encoding="utf-8")  # 木が 1 本では記録の 2 本を動かせない
    with pytest.raises(OpError):
        Session(s.dir).rebase()
    assert Session(s.dir).load_warnings  # 印は変えない


def test_werewolf_leaks_closed(tmp_path, capsys):
    """人狼の試し遊び（ループ 19）で見つけた漏れ：行えない人に引数の条件を見せない、封をした投票の値を記録で伏せる、
    取り消しの出力は取り消した人の見え方、全員が書くまで開票できない。"""
    import yaml
    from bgskills.cli import main
    s = Session.create(tmp_path / "w", WEREWOLF, 6, {}, 11, strict=False)
    s.act("setup", "keeper")
    st = s.state()
    village = [p for p in s.defn.players if role_of(s, st, p) == "villager"]
    capsys.readouterr()
    main(["candidates", str(s.dir), "attack", "--by", village[0]])
    out = yaml.safe_load(capsys.readouterr().out)
    assert "target" not in out and out["action_problems"]  # 人狼の名前が引数の条件から漏れない
    s.act("vote", village[0], {"target": village[1]})
    seen = _visible_ops(s, s.state(), s.log(), village[1])
    assert all(o.get("value") != village[1] for o in seen if o.get("action") == "vote")
    from bgskills.query import check_action
    oa = next(a for a in s.defn.data["actions"] if a["id"] == "open-votes")
    assert check_action(s.defn, s.state(), oa, {"actor": "keeper", "player": "keeper"})  # まだ書いていない人がいる


def test_werewolf_is_strict_by_default(tmp_path):
    """人狼の定義は game.strict（外れた行為は記録しない）。夜に村人が話す・村人が占うは受け付けない。"""
    s = Session.create(tmp_path / "w", WEREWOLF, 5, {}, 1)
    assert s.meta.get("strict")
    s.act("setup", "keeper"); s.act("wolves-meet", "keeper"); s.apply({"op": "advance", "by": "keeper"})
    st = s.state()
    villager = next(p for p in s.defn.players if role_of(s, st, p) == "villager")
    with pytest.raises(OpError, match="厳格モード"):
        s.apply({"op": "say", "by": villager, "text": "誰か起きてる？"})
    with pytest.raises(OpError, match="厳格モード"):
        s.act("divine", villager, {"target": next(p for p in s.defn.players if p != villager)})
    assert not Session.create(tmp_path / "l", WEREWOLF, 5, {}, 1, strict=False).meta.get("strict")


def test_hidden_whisper_numbers_do_not_leave_gaps(tmp_path):
    """夜（whisper: hidden）の内緒話は別の番号 hN。ほかの人の通し番号に欠けが出ず、件数が分からない。"""
    s = Session.create(tmp_path / "w", WEREWOLF, 6, {}, 4)
    s.act("setup", "keeper"); s.act("wolves-meet", "keeper"); s.apply({"op": "advance", "by": "keeper"})  # 夜
    st = s.state()
    wolves = [p for p in s.defn.players if role_of(s, st, p) == "werewolf"]
    village = [p for p in s.defn.players if p not in wolves]
    s.apply({"op": "say", "by": wolves[0], "to": [wolves[1]], "text": "占い師を狙おう"})
    s.apply({"op": "say", "by": "keeper", "text": "夜が明ける"})
    assert [t["n"] for t in s.state()["talk"]] == ["h0", 0]
    assert [t["n"] for t in view(s.defn, s.state(), village[0])["talk"]] == [0]
