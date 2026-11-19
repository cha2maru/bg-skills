"""スタック（割り込み）：宣言した行為を積み、ほかのプレイヤーが応じて積み、全員が見送ったら後から積んだものから解決する。"""
import pytest

from bgskills.query import candidates
from bgskills.session import OpError, Session
from bgskills.view import view

SPELLS = """
format: bg-def/0.1
game: {id: spells, name: 呪文, version: 1, players: {min: 2, max: 3}}
players: [{id: P1}, {id: P2}, {id: P3}]
kinds:
  token: {base: object, distinct: false}
areas:
  - {id: supply}
  - {id: "life-{player}", for_each: {player: players}, owner: "{player}"}
objects:
  - {id: hp, kind: token, count: unlimited, start: supply}
actions:
  - id: bolt
    name: 雷（相手に 3 ダメージ）
    stack: true
    params: [{name: target, players: true}]
    steps:
      - {op: move, obj: hp, from: supply, to: "life-{target}", n: 3}
  - id: counter
    name: 打ち消し
    stack: true
    params: [{name: spell, stack: true}]
    steps:
      - {op: cancel, target: "{spell}"}
  - id: heal
    name: 回復（自分のダメージを 1 取る）
    stack: true
    steps:
      - {op: move, obj: hp, from: "life-{actor}", to: supply, n: 1}
  - id: draw
    name: 引く（スタックが空のときだけ）
    steps: []
"""


def _s(tmp_path, n=2):
    (tmp_path / "d.yaml").write_text(SPELLS, encoding="utf-8")
    return Session.create(tmp_path / "s", tmp_path / "d.yaml", n, {}, 1)


def dmg(st, p):
    return sum(next(iter(i.values())) for i in st["places"][f"life-{p}"])


def test_respond_and_resolve_lifo(tmp_path):
    s = _s(tmp_path)
    s.act("bolt", "P1", {"target": "P2"})
    st = s.state()
    assert dmg(st, "P2") == 0 and [e["action"] for e in st["stack"]] == ["bolt"]  # 積んだだけ
    assert view(s.defn, st, "P2")["stack_waiting"] == ["P2"]
    assert [c["id"] for c in candidates(s.defn, st, "counter", "P2", "spell", {})] == ["1"]
    s.act("counter", "P2", {"spell": "1"})  # 割り込む
    s.apply({"op": "pass", "by": "P1"})  # 積んだ P2 以外（P1）が見送る → 打ち消しが解決し、雷は外れる
    st = s.state()
    assert st["stack"] == [] and dmg(st, "P2") == 0
    assert [(e["action"], e["status"]) for e in st["stack_done"]] == [("bolt", "canceled"), ("counter", "resolved")]


def test_all_pass_resolves_and_order(tmp_path):
    s = _s(tmp_path, 3)
    s.act("bolt", "P1", {"target": "P2"})
    s.act("heal", "P2")  # 応じて積む（後から積んだ回復が先に解決する：まだダメージがないので立ち消え）
    s.apply({"op": "pass", "by": "P1"})
    assert len(s.state()["stack"]) == 2  # P3 がまだ見送っていない
    s.apply({"op": "pass", "by": "P3"})
    st = s.state()
    assert [(e["action"], e["status"]) for e in st["stack_done"]] == [("heal", "fizzled")] and len(st["stack"]) == 1
    s.apply({"op": "pass", "by": "P2"}); s.apply({"op": "pass", "by": "P3"})  # 雷：積んだ P1 以外が見送る
    st = s.state()
    assert st["stack"] == [] and dmg(st, "P2") == 3


def test_normal_action_waits_for_empty_stack_and_undo(tmp_path):
    s = _s(tmp_path)
    s.act("bolt", "P1", {"target": "P2"})
    s.act("draw", "P2")
    assert any("スタックに解決待ちがある" in w for w in s.last_warnings)
    s.undo()
    s.apply({"op": "resolve", "by": "keeper"})
    assert dmg(s.state(), "P2") == 3
    s.undo()  # 解決を取り消すと、雷は積まれたまま
    assert [e["action"] for e in s.state()["stack"]] == ["bolt"] and dmg(s.state(), "P2") == 0
    with pytest.raises(OpError, match="解決待ちにない|スタックに #9"):
        s.apply({"op": "cancel", "target": 9, "by": "keeper"})


def test_rune_clash_cast_cost_and_ward(tmp_path):
    """ルーン決闘（examples/rune-clash.yaml。bg-design で作った架空のゲーム）：唱えるときに cost（ルーンを払う・カードを
    唱えている場所へ）をすぐ行い、雷撃に守りの紋で応じると雷撃は打ち消されて捨て札へ。"""
    from pathlib import Path
    ex = Path(__file__).parent.parent / "examples" / "rune-clash.yaml"
    s = Session.create(tmp_path / "r", ex, 2, {}, 3)
    s.act("setup", "keeper")
    s.apply({"op": "advance", "to": "stage", "by": "keeper"})
    for p in ("P1", "P2"):
        s.apply({"op": "move", "obj": "rune-pool", "from": "supply", "to": f"pool-{p}", "n": 2, "by": "keeper"})
        s.apply({"op": "move", "obj": f"{p}-bolt-1", "to": f"hand-{p}", "by": "keeper"})
        s.apply({"op": "move", "obj": f"{p}-ward-1", "to": f"hand-{p}", "by": "keeper"})
    s.act("draw", "P1")
    s.act("cast-bolt", "P1", {"card": "P1-bolt-1"})
    st = s.state()
    assert "P1-bolt-1" in st["places"]["casting"] and dmg_runes(st, "P1") == 2  # 2 ＋引いて 1 − 払って 1
    s.act("cast-ward", "P2", {"card": "P2-ward-1", "spell": "1"})  # 相手の手番に応じる
    s.apply({"op": "pass", "by": "P1"})
    st = s.state()
    assert st["stack"] == [] and "P1-bolt-1" in st["places"]["discard-P1"] and not st["places"]["life-P2"]
    assert [(e["action"], e["status"]) for e in st["stack_done"]] == [("cast-bolt", "canceled"), ("cast-ward", "resolved")]


def dmg_runes(st, p):
    return sum(next(iter(i.values())) for i in st["places"][f"pool-{p}"])


def test_advance_waits_for_stack(tmp_path):
    """解決待ちがあるうちは進行を進めない（厳格なルーン決闘では断る）。"""
    from pathlib import Path
    s = Session.create(tmp_path / "r", Path(__file__).parent.parent / "examples" / "rune-clash.yaml", 2, {}, 3)
    s.act("setup", "keeper")
    s.apply({"op": "advance", "to": "stage", "by": "keeper"})
    s.apply({"op": "move", "obj": "P1-bolt-1", "to": "hand-P1", "by": "keeper"})
    s.act("draw", "P1")
    s.act("cast-bolt", "P1", {"card": "P1-bolt-1"})
    with pytest.raises(OpError, match="解決待ち"):
        s.apply({"op": "advance", "to": "turn", "by": "P1"})


def _rune(tmp_path):
    from pathlib import Path
    s = Session.create(tmp_path / "r", Path(__file__).parent.parent / "examples" / "rune-clash.yaml", 2, {}, 3)
    s.act("setup", "keeper")
    s.apply({"op": "advance", "to": "stage", "by": "keeper"})
    return s


def test_rune_clash_playtest_fixes(tmp_path, capsys):
    """bg-playtest（ルーン決闘）で見つけた点：if の {card} が埋まらず雷撃が効かない、席の中の手札が持ち主にも見えない、
    記録で昔の手札が分かる、選ぶものが足りない呪文が積める、スタックの候補が番号だけ。"""
    import yaml
    from bgskills.cli import main
    s = _rune(tmp_path)
    hand = s.state()["places"]["hand-P1"]
    v = view(s.defn, s.state(), "P1")["areas"]["hand-P1"]["shown"]
    assert [x["id"] for x in v] == hand  # 持ち主には見える（親の席の owner を引き継ぐ）
    assert view(s.defn, s.state(), "P2")["areas"]["hand-P1"]["shown"] == {"count": 4}  # 相手には枚数だけ
    s.apply({"op": "move", "obj": "P1-bolt-1", "to": "hand-P1", "by": "keeper"})
    s.apply({"op": "move", "obj": "P2-ward-1", "to": "hand-P2", "by": "keeper"})
    s.apply({"op": "move", "obj": "rune-pool", "from": "supply", "to": "pool-P2", "n": 1, "by": "keeper"})
    s.act("draw", "P1")
    with pytest.raises(OpError, match="選ぶものが足りない"):
        s.act("cast-ward", "P2", {"card": "P2-ward-1"})
    s.act("cast-bolt", "P1", {"card": "P1-bolt-1"})
    capsys.readouterr()
    main(["candidates", str(s.dir), "cast-ward", "--by", "P2", "--param", "spell"])
    (c,) = yaml.safe_load(capsys.readouterr().out)["spell"]
    assert "P1 の 雷撃を唱える（P1-bolt-1）" == c["title"]
    s.apply({"op": "pass", "by": "P2"})
    assert sum(next(iter(i.values())) for i in s.state()["places"]["life-P2"]) == 3  # 雷撃が効く
    main(["log", str(s.dir), "--as", "P2"])
    log = yaml.safe_load(capsys.readouterr().out)
    early = [o for o in log if o.get("op") == "move" and o.get("to") == "hand-P1" and o.get("by") == "keeper" and "P1-bolt" not in str(o.get("obj"))]
    assert all(o["obj"] == "（見えない部品）" for o in early)  # 配った札は、後で唱えても配った時点では伏せる


def test_replay_cache_matches_fresh_replay(tmp_path):
    """局面を覚えて増えた分だけ足す作り（ループ 29）：取り消しや別の書き手のあとも、最初から作り直した局面と同じ。"""
    s = _rune(tmp_path)
    s.act("draw", "P1")
    a = s.state()
    a["places"]["hand-P1"].clear()  # 呼ぶ側が書き換えても、覚えた局面は変わらない
    assert s.state()["places"]["hand-P1"]
    s.undo()
    other = Session(s.dir)  # 別の書き手（画面など）
    other.act("draw", "P1")
    assert s.state() == Session(s.dir)._replay(s.log()) == other.state()


def test_pyxel_sample_table_plays_to_the_end(tmp_path):
    """samples/pyxel/rune_clash.py の進行役（Pyxel なしで動く部分）：両方の席をボットにして最後まで遊べる。"""
    import importlib.util
    from pathlib import Path
    spec = importlib.util.spec_from_file_location("rc", Path(__file__).parent.parent / "samples" / "pyxel" / "rune_clash.py")
    rc = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(rc)
    t = rc.Table(seed=5, path=tmp_path)
    for _ in range(3000):
        if t.winner():
            break
        if not t.bot_step(rc.BOT) and not t.bot_step(rc.ME):
            break
    assert t.winner() in ("P1", "P2", "DRAW") and t.st()["result"]["text"].endswith("（相手の勝ち。R5）")


def test_selfplay_generic_random_games():
    """bg selfplay：作品専用のボットなしで、今行える手からでたらめに選んで最後まで回し、終わり方を数える。"""
    from pathlib import Path
    from bgskills.tools import selfplay
    ex = Path(__file__).parent.parent / "examples"
    r = selfplay(ex / "rune-clash.yaml", 2, games=4)
    assert sum(r["outcomes"].values()) == 4 and all("ダメージ" in k for k in r["outcomes"])
    r = selfplay(ex / "beast-duel.yaml", 2, games=3)
    assert "進められない" not in r["outcomes"]  # 山札切れの負け（R8）が end_when にある
