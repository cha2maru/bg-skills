"""カードセット（基本・拡張）を 1 つの定義に複数持ち、準備で選んで混ぜる（RUL-027）。形式に項目を足さずに書けることの確かめ。
セットは部品の属性 set、全部の部品は箱から始め、準備のアクションで選んだセットだけを山札へ移して切る。混ぜ方の制約は条件（require）。"""
import pytest

from bgskills.session import OpError, Session

SETS = """
format: bg-def/0.1
game: {id: sets, name: セットを混ぜる, version: 1, players: {min: 1, max: 1}, strict: true}
players: [{id: P1}]
kinds:
  card: {base: object, text: "カード。attributes の set が属するセット（base・exp-a・exp-b）。"}
  set-tile: {base: object, name: セットの札, text: 準備で使うセットを示す札。}
areas:
  - {id: sets-available, name: 持っているセット}
  - {id: sets-chosen, name: 使うセット}
  - {id: deck, name: 山札, ordered: true, visibility: {face: none, order: none}}
objects:
  - {id: "set-{s}", for_each: {s: [base, exp-a, exp-b]}, kind: set-tile, start: sets-available, attributes: {set: "{s}"}}
  - {id: "base-{copy}", kind: card, copies: 6, start: box, attributes: {set: base}}
  - {id: "expa-{copy}", kind: card, copies: 3, start: box, attributes: {set: exp-a}}
  - {id: "expb-{copy}", kind: card, copies: 3, start: box, attributes: {set: exp-b}}
actions:
  - id: choose-set
    name: 使うセットを選ぶ
    rule: R1
    by: [keeper]
    params: [{name: tile, from: sets-available}]
    require:
      - {expr: "attr(tile, 'set') == 'base' or 'set-base' in on('sets-chosen')", text: 基本セットを先に選ぶ}
      - {expr: "attr(tile, 'set') == 'base' or count_in('sets-chosen') < 2", text: 拡張は 1 つまで}
    steps: [{op: move, obj: "{tile}", to: sets-chosen}]
  - id: mix
    name: 選んだセットを混ぜて山札にする
    rule: R1
    by: [keeper]
    require: [{expr: "'set-base' in on('sets-chosen')", text: 基本セットは必ず使う}]
    steps:
      - each: "[c for c in on('box') if attr(c, 'set') in [attr(t, 'set') for t in on('sets-chosen')]]"
        as: c
        do: [{op: move, obj: "{c}", to: deck}]
      - {op: shuffle, area: deck}
flow:
  stages: [{id: setup, name: 準備, actions: [choose-set, mix]}]
rules:
  - {id: R1, type: setup, text: 基本セットに、拡張を 1 つまで混ぜて使う。使わないセットのカードは箱に残す。}
"""


def _s(tmp_path):
    (tmp_path / "d.yaml").write_text(SETS, encoding="utf-8")
    return Session.create(tmp_path / "s", tmp_path / "d.yaml", 1, {}, 3, strict=True)


def test_choose_sets_and_mix(tmp_path):
    s = _s(tmp_path)
    s.act("choose-set", "keeper", {"tile": "set-base"})
    s.act("choose-set", "keeper", {"tile": "set-exp-b"})
    with pytest.raises(OpError, match="拡張は 1 つまで"):
        s.act("choose-set", "keeper", {"tile": "set-exp-a"})
    s.act("mix", "keeper")
    st = s.state()
    sets = {s.defn.parts[c]["attributes"]["set"] for c in st["places"]["deck"]}
    assert sets == {"base", "exp-b"} and len(st["places"]["deck"]) == 9
    assert all(s.defn.parts[c]["attributes"]["set"] == "exp-a" for c in st["places"]["box"] if isinstance(c, str))
    assert st["places"]["deck"] != sorted(st["places"]["deck"])  # 混ぜて切った


def test_base_set_required(tmp_path):
    s = _s(tmp_path)
    with pytest.raises(OpError, match="基本セットを先に選ぶ"):
        s.act("choose-set", "keeper", {"tile": "set-exp-a"})
    with pytest.raises(OpError, match="基本セットは必ず使う"):
        s.act("mix", "keeper")
