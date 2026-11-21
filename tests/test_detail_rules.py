"""詳細ルール（RUL-024）：rules の detail: true は手引き（TTS の書き出し・画面のルール欄の初めの一覧）に出さず、定義には残す。
あわせて、引数を読むアクションの条件が、行えない理由の計算（見え方）を壊さないこと。"""
import json

from bgskills.session import Session
from bgskills.tools import complexity
from bgskills.view import view

DEF = """
format: bg-def/0.1
game: {id: dr, name: 詳細, version: 1, players: {min: 2, max: 2}}
players: [{id: P1}, {id: P2}]
kinds: {card: {base: object, attributes: {cost: {type: number}}}}
areas:
  - {id: "hand-{player}", for_each: {player: players}, owner: "{player}", visibility: {face: owner}}
  - {id: pile}
objects:
  - {id: "{player}-c{copy}", for_each: {player: players}, copies: 2, kind: card, owner: "{player}", start: "hand-{player}", attributes: {cost: 1}}
actions:
  - id: play
    name: 出す
    rule: R1
    params: [{name: card, from: "hand-{actor}"}]
    require: [{expr: "attr(card, 'cost') <= 1", text: 費用が 1 以下}]
    steps: [{op: move, obj: "{card}", to: pile}]
flow:
  stages: [{id: main, name: 本番, order: seats, turn: t}]
  turns: {t: {phases: [{id: p, name: 出す, main: [play]}]}}
rules:
  - {id: R1, type: action, text: 手札を 1 枚出す。}
  - {id: CR1, type: action, detail: true, source: 総合ルール 1, text: 出したカードは場で表向きになる。費用は出す前に確かめる。}
"""


def _s(tmp_path):
    (tmp_path / "d.yaml").write_text(DEF, encoding="utf-8")
    return Session.create(tmp_path / "s", tmp_path / "d.yaml", 2, {}, 1)


def test_detail_rules_kept_in_definition_but_not_in_manual(tmp_path):
    from bgskills.tts import export
    s = _s(tmp_path)
    assert complexity(s.defn)["rules_detail"] == 1
    out = tmp_path / "t.json"
    export(s.defn, s.state(), out)
    text = out.read_text(encoding="utf-8")
    assert "手札を 1 枚出す" in text and "費用は出す前に確かめる" not in text


def test_param_require_does_not_break_view(tmp_path):
    s = _s(tmp_path)
    v = view(s.defn, s.state(), "P1")  # 以前は require の card が未定義で失敗し、画面が前の見え方を出し続けた
    assert "play" not in (v["flow"].get("blocked") or {})
    json.dumps(v, ensure_ascii=False)
