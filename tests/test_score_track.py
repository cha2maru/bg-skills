"""得点の表し方（RUL-023）：道の駒の位置が得点。即時得点（取ったらすぐ進む）、決まった時機の得点計算（巡の終わりの色の一番）、
終わりの得点計算（道では進めない組の得点を足して比べる）。手本は examples/harvest-road.yaml。"""
from pathlib import Path

from bgskills.session import Session
from bgskills.view import view

EX = Path(__file__).parent.parent / "examples"


def _score(s, p):
    return view(s.defn, s.state(), None)["metrics"]["score"]["values"][p]


def test_immediate_round_end_and_final_scoring(tmp_path):
    s = Session.create(tmp_path / "h", EX / "harvest-road.yaml", 2, {}, 5)
    s.act("setup", "keeper")
    s.apply({"op": "advance", "to": "turn", "by": "keeper"})
    st = s.state()
    a = st["places"]["market"][0]
    v = int(s.defn.parts[a]["attributes"]["value"])
    s.act("harvest", "P1", {"card": a})
    assert _score(s, "P1") == v and s.state()["places"]["s" + str(v)] == ["marker-P1"]  # 取ったらすぐ進む
    s.apply({"op": "advance", "to": "turn", "by": "P1"})
    color = s.defn.parts[a]["attributes"]["color"]
    b = next(x for x in s.state()["places"]["market"] if s.defn.parts[x]["attributes"]["color"] != color)
    w = int(s.defn.parts[b]["attributes"]["value"])
    s.act("harvest", "P2", {"card": b})
    s.apply({"op": "advance", "to": "turn", "by": "P2"})  # 巡の終わり：P1・P2 はそれぞれ別の色の一番で 2 進む
    assert (_score(s, "P1"), _score(s, "P2")) == (v + 2, w + 2)
    m = view(s.defn, s.state(), None)["metrics"]
    assert m["final"]["values"]["P1"] == v + 2 + 3 * m["sets"]["values"]["P1"]
