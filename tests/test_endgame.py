"""終わり方の複雑なルール：勝ち・負け・引き分けの結果、終わる時機（その巡の終わりまで続ける）、終わりの得点計算と同点の比べ方、
手番の終わりの手順（手札の上限まで捨てる）。"""
from bgskills.flow import end_result, standings
from bgskills.session import Session
from bgskills.tools import complexity
from bgskills.view import view

RACE = """
format: bg-def/0.1
game: {id: race, name: 競争, version: 1, players: {min: 3, max: 3}}
players: [{id: P1}, {id: P2}, {id: P3}]
kinds:
  vp: {base: object, distinct: false}
  coin: {base: object, distinct: false}
  card: {base: object}
areas:
  - {id: supply}
  - {id: deck, ordered: true}
  - {id: "score-{player}", for_each: {player: players}, owner: "{player}"}
  - {id: "purse-{player}", for_each: {player: players}, owner: "{player}"}
  - {id: "hand-{player}", for_each: {player: players}, owner: "{player}"}
  - {id: discard}
objects:
  - {id: vps, kind: vp, count: unlimited, start: supply}
  - {id: coins, kind: coin, count: unlimited, start: supply}
  - {id: "c{copy}", kind: card, copies: 30, start: deck}
actions:
  - id: score
    name: 点を取る
    params: [{name: n, choices: ["1", "3", "5"]}]
    steps:
      - {op: move, obj: vps, from: supply, to: "score-{actor}", n: "{n}"}
  - id: earn
    name: お金を得る
    steps:
      - {op: move, obj: coins, from: supply, to: "purse-{actor}", n: 1}
  - id: draw
    name: 2 枚引く
    steps:
      - {op: move, obj: "top:deck", to: "hand-{actor}", times: 2}
flow:
  auto_end: true
  scoring: {by: points, tiebreak: [money]}
  stages:
    - {id: main, name: 本番, order: seats, turn: main}
  turns:
    main:
      phases:
        - {id: act, name: 行う, main: [score, earn, draw]}
      on_end:  # 手番の終わり：手札は 3 枚まで（多い分を捨てる）
        - each: "on('hand-' + active())[3:]"
          as: c
          do:
            - {op: move, obj: "{c}", to: discard}
  end_when:
    - {expr: "[p for p in players() if count_in('score-' + p, kind='vp') >= 10]", timing: round_end, winners: scoring, rule: R2,
       text: "{value} が 10 点に届いた（その巡を終えてから、得点の多い人の勝ち。R2）"}
metrics:
  - {id: points, name: 点, per: player, count: {in: "score-{player}", kind: vp}}
  - {id: money, name: お金, per: player, count: {in: "purse-{player}", kind: coin}}
rules:
  - {id: R1, type: turn, text: 手番に 1 つ行う。手番の終わりに、手札は 3 枚まで。, refs: [card]}
  - {id: R2, type: end, text: 誰かが 10 点に届いたら、その巡（全員が同じ回数）を終えて終わる。得点が多い人の勝ち。同点ならお金が多い人。, refs: [vp, coin]}
"""


def _s(tmp_path):
    (tmp_path / "race.yaml").write_text(RACE, encoding="utf-8")
    return Session.create(tmp_path / "s", tmp_path / "race.yaml", 3, {}, 1)


def turn(s, who, action, args=None):
    s.act(action, who, args or {})
    s.apply({"op": "advance", "to": "turn", "by": who})


def test_round_end_scoring_and_tiebreak(tmp_path):
    s = _s(tmp_path)
    turn(s, "P1", "score", {"n": "5"}); turn(s, "P2", "score", {"n": "5"}); turn(s, "P3", "earn")
    turn(s, "P1", "score", {"n": "5"})  # P1 が 10 点：まだ終わらない（巡の途中）
    assert s.state()["result"] is None and view(s.defn, s.state(), None)["flow"]["end_preview"]["text"].startswith("P1")
    turn(s, "P2", "score", {"n": "5"})  # P2 も 10 点
    assert s.state()["result"] is None
    turn(s, "P3", "score", {"n": "1"})  # 巡が終わる → 終わる。P1・P2 は 10 点で同点、お金も 0 で同じ → 2 人の勝ち
    r = s.state()["result"]
    assert r["results"] == {"P1": "win", "P2": "win", "P3": "lose"} and [x["rank"] for x in r["standings"]] == [1, 1, 3]


def test_tiebreak_decides(tmp_path):
    s = _s(tmp_path)
    for p in ("P1", "P2", "P3"):
        s.apply({"op": "move", "obj": "vps", "from": "supply", "to": f"score-{p}", "n": 9, "by": "keeper"})
    s.apply({"op": "move", "obj": "coins", "from": "supply", "to": "purse-P2", "n": 2, "by": "keeper"})
    rows = standings(s.defn, s.state())
    assert [(r["player"], r["rank"]) for r in rows][0] == ("P2", 1)
    turn(s, "P1", "score", {"n": "1"}); turn(s, "P2", "score", {"n": "1"}); turn(s, "P3", "score", {"n": "1"})
    assert s.state()["result"]["results"] == {"P1": "lose", "P2": "win", "P3": "lose"}  # 同点はお金で


def test_turn_on_end_hand_limit(tmp_path):
    s = _s(tmp_path)
    s.act("draw", "P1"); s.act("draw", "P1")  # 4 枚
    assert len(s.state()["places"]["hand-P1"]) == 4
    s.apply({"op": "advance", "to": "turn", "by": "P1"})
    st = s.state()
    assert len(st["places"]["hand-P1"]) == 3 and len(st["places"]["discard"]) == 1


def test_end_result_preview_and_complexity(tmp_path):
    s = _s(tmp_path)
    assert end_result(s.defn, s.state(), ("now", "round_end")) is None
    c = complexity(s.defn)
    assert c["end_conditions"] == {"count": 1, "with_result": 1, "timed": 1} and c["scoring"] and c["rules_text_only"]["ids"] == ["R1"]


def test_playstats_and_quiz(tmp_path, capsys):
    """目的の物差し（RUL-016）：bg playstats はコマンドと拒否を数え、bg quiz は「行えるか」の問いと正解（エンジンの判定）を作る。"""
    from pathlib import Path
    import yaml
    from bgskills.cli import main
    ex = Path(__file__).parent.parent / "examples" / "rune-clash.yaml"
    d = str(tmp_path / "s")
    main(["new", d, "--def", str(ex), "--players", "2", "--seed", "1"])
    main(["act", d, "setup"]); main(["advance", d, "--to", "stage"])
    main(["act", d, "cast-bolt", "--by", "P1", "--arg", "card=P1-bolt-1"])  # 引く前・ルーンなし → 拒否
    capsys.readouterr()
    main(["playstats", d])
    st = yaml.safe_load(capsys.readouterr().out)
    assert st["acting"] == 3 and st["rejected"] == 1 and st["per_seat"]["P1"]["rejected"] == 1
    main(["quiz", str(ex), "--players", "2", "--n", "4", "--seed", "1", "--out", str(tmp_path / "q")])
    capsys.readouterr()
    ans = yaml.safe_load((tmp_path / "q" / "answers.yaml").read_text(encoding="utf-8"))
    assert len(ans) == 4 and all(v["answer"] in ("yes", "no") for v in ans.values())
    (tmp_path / "r.yaml").write_text(yaml.safe_dump({k: v["answer"] for k, v in ans.items()}), encoding="utf-8")
    main(["quiz-grade", str(tmp_path / "q" / "answers.yaml"), str(tmp_path / "r.yaml")])
    assert yaml.safe_load(capsys.readouterr().out)["accuracy"] == 1.0


def test_schema_unknown_keys_and_expr_braces(tmp_path, capsys):
    """形式の正本（schema.py）：bg check は知らない項目を似た項目つきで、式の中の {x} を指摘する。bg schema は JSON Schema。"""
    import json
    from bgskills.cli import main
    from bgskills.definition import load
    from bgskills.tools import check_refs
    (tmp_path / "race.yaml").write_text(RACE.replace("  auto_end: true", "  auto_ends: true").replace(
        "on('hand-' + active())[3:]", "on('hand-{player}')[3:]"), encoding="utf-8")
    refs = [r["ref"] for r in check_refs(load(tmp_path / "race.yaml", 3))]
    assert any("知らない項目 auto_ends（auto_end のことか）" in r for r in refs)
    assert any("{player} ではなく" in r for r in refs)
    capsys.readouterr()
    main(["schema"])
    sch = json.loads(capsys.readouterr().out)
    assert "auto_end" in sch["properties"]["flow"]["properties"] and sch["additionalProperties"] is False


def test_quiz_findings_stage_binding_and_flow_end(tmp_path):
    """小テスト（RUL-016）で見つけた穴：進行のどこかに書いたアクションは、ほかの段階では行えない（準備だけの引き直し）。
    進行が終わったら（段階がない）、進行に書いたアクションは行えない。採点は YAML の yes/no（真偽値）も受ける。"""
    from pathlib import Path
    from bgskills.flow import classify
    from bgskills.tools import quiz_grade
    ex = Path(__file__).parent.parent / "examples"
    s = Session.create(tmp_path / "d", ex / "beast-duel.yaml", 2, {}, 3)
    s.act("setup", "keeper")
    s.apply({"op": "advance", "to": "stage", "by": "keeper"})
    assert any("段階「" in w for w in classify(s.defn, s.state()["flow"], "mulligan", "P1")[1])
    f = {**s.state()["flow"], "stage": None}
    assert any("進行が終わっている" in w for w in classify(s.defn, f, "attack", "P1")[1])
    (tmp_path / "a.yaml").write_text("q01: {answer: 'yes', why: ''}\nq02: {answer: 'no', why: x}\n", encoding="utf-8")
    (tmp_path / "r.yaml").write_text("q01: yes\nq02: no\n", encoding="utf-8")
    assert quiz_grade(tmp_path / "a.yaml", tmp_path / "r.yaml")["accuracy"] == 1.0
