"""思考ルーチンの枠組み（RUL-030）：合法手は、その席に見える部品だけ。思考ルーチンは見えない部品の定義を引けない。
リーグ戦は席を回して多数局を回し、方針ごとの勝ちの割合と、同じ種どうしを比べた符号検定を出す。"""
import json
from pathlib import Path

import pytest
import yaml

from bgskills.bot import Ctx, league, legal_moves, load_policy, play_game, sign_test
from bgskills.cli import main
from bgskills.session import Session
from bgskills.view import view

EX = Path(__file__).parent.parent / "examples"
GREEDY = str(EX / "bots" / "harvest-greedy.py")


def test_AC_079_1_moves_and_ctx_hide_unseen(tmp_path):
    s = Session.create(tmp_path / "r", EX / "rune-clash.yaml", 2, {}, 3, strict=True)
    s.act("setup", "keeper")
    s.apply({"op": "advance", "to": "stage", "by": "keeper"})
    st = s.state()
    p = st["flow"]["active"]
    moves = legal_moves(s, p)
    other = [x for x in s.defn.players if x != p][0]
    their_hand = set(st["places"][f"hand-{other}"])
    assert moves and not ({str(v) for m in moves for v in (m.get("args") or {}).values()} & their_hand)
    ctx = Ctx(s, p, view(s.defn, st, p), moves, None)
    with pytest.raises(KeyError):
        ctx.part(next(iter(their_hand)))
    mine = st["places"][f"hand-{p}"][0]
    assert ctx.part(mine)["kind"]


def test_AC_079_2_play_game_with_policy_ends():
    g = load_policy(str(EX / "bots" / "harvest-greedy.py"))
    r = play_game(EX / "harvest-road.yaml", {"P1": g}, 2, seed=1)
    assert r["end"].startswith("山札が尽きた") and r["refused"] == 0 and r["standings"]


def test_AC_080_1_league_rotates_and_compares():
    out = league(EX / "harvest-road.yaml", {"greedy": str(EX / "bots" / "harvest-greedy.py"), "random": "random"}, 2, games=4, seed=0)
    assert out["games"] == 8 and set(out["bots"]) == {"greedy", "random"}
    assert out["bots"]["greedy"]["win_rate"] >= out["bots"]["random"]["win_rate"]
    assert set(out["paired"]) >= {"greedy_more", "random_more", "sign_test_p"}
    assert sign_test(10, 0) < 0.01 and sign_test(3, 3) == 1.0


def _cli(capsys, *argv):
    capsys.readouterr()
    assert main(list(argv)) == 0
    return yaml.safe_load(capsys.readouterr().out)


def _harvest_at_p1(tmp_path):
    s = Session.create(tmp_path / "h", EX / "harvest-road.yaml", 2, {}, 1)
    s.act("setup", "keeper")
    s.apply({"op": "advance", "to": "stage", "by": "keeper"})
    return s


def test_AC_084_1_bot_step_plays_bot_seat_until_human(tmp_path, capsys):
    s = _harvest_at_p1(tmp_path)
    s.act("harvest", "P1", {"card": s.state()["places"]["market"][0]})
    s.apply({"op": "advance", "to": "turn", "by": "P1"})
    n = len(s.log())
    out = _cli(capsys, "bot-step", str(s.dir), "--human", "P1", "--bot", f"P2={GREEDY}")
    assert {k: out[k] for k in ("stopped", "active", "applied", "human")} == {"stopped": "human", "active": "P1", "applied": 2, "human": "P1"}
    assert [o.get("by") for o in out["moves"]] == [o.get("by") for o in s.log()[n:]]  # 人の席に見える形で、足した手
    assert any(o.get("by") == "P2" and o.get("action") == "harvest" for o in s.log()[n:])


def test_AC_084_2_human_turn_adds_nothing(tmp_path, capsys):
    s = _harvest_at_p1(tmp_path)
    n = len(s.log())
    assert _cli(capsys, "bot-step", str(s.dir), "--human", "P1", "--bot", f"P2={GREEDY}")["stopped"] == "human"
    assert len(s.log()) == n
    # 手番のない段階（準備）で人の席が止まっても、呼び直したときにキーパーの準備を繰り返さない
    b = Session.create(tmp_path / "b", EX / "beast-duel.yaml", 2, {}, 2)
    assert _cli(capsys, "bot-step", str(b.dir), "--human", "P1")["human"] == "P1"
    acts = [(o["by"], o["action"]) for o in b.log() if "act" in o]
    assert acts[0] == ("keeper", "setup") and any(by == "P2" for by, _ in acts)  # 人の席より先に、思考ルーチンの席が準備を済ませる
    assert _cli(capsys, "bot-step", str(b.dir), "--human", "P1") == {"stopped": "human", "active": None, "applied": 0, "human": "P1", "moves": []}
    assert [(o["by"], o["action"]) for o in b.log() if "act" in o] == acts


def test_AC_084_3_ended_game_stops_as_ended(tmp_path, capsys):
    s = Session.create(tmp_path / "h", EX / "harvest-road.yaml", 2, {}, 1)
    assert _cli(capsys, "bot-step", str(s.dir))["stopped"] == "ended"  # 書かない席はでたらめ
    assert s.state()["result"]["results"]
    out = _cli(capsys, "bot-step", str(s.dir), "--human", "P1")
    assert (out["stopped"], out["applied"]) == ("ended", 0)


def test_AC_085_1_margin_reaches_trace(tmp_path, capsys):
    bot = tmp_path / "half.py"
    bot.write_text("def choose(ctx):\n    return ctx.moves[0], 'first', 0.5\n", encoding="utf-8")
    tr = tmp_path / "trace.jsonl"
    _cli(capsys, "league", str(EX / "harvest-road.yaml"), "--bot", f"half={bot}", "--bot", "random", "--players", "2",
         "--games", "1", "--trace", str(tr))
    lines = [json.loads(x) for x in tr.read_text(encoding="utf-8").splitlines()]
    mine = [x for x in lines if x.get("note") == "first"]
    assert mine and all(x["margin"] == 0.5 for x in mine)
    assert all("margin" not in x for x in lines if x.get("note") != "first")


def test_AC_085_2_ctx_log_hides_what_bg_log_hides(tmp_path, capsys):
    s = Session.create(tmp_path / "r", EX / "rune-clash.yaml", 2, {}, 3, strict=True)
    s.act("setup", "keeper")
    s.apply({"op": "advance", "to": "stage", "by": "keeper"})
    st = s.state()
    p = st["flow"]["active"]
    other = next(x for x in s.defn.players if x != p)
    their_hand = set(st["places"][f"hand-{other}"])
    assert their_hand & {o.get("obj") for o in s.log()}  # 記録そのものには相手の手札の ID がある
    ctx = Ctx(s, p, view(s.defn, st, p), legal_moves(s, p), None)
    assert ctx.log == _cli(capsys, "log", str(s.dir), "--as", p)
    assert not their_hand & {o.get("obj") for o in ctx.log}


def test_AC_083_2_league_has_win_ci_per_bot():
    out = league(EX / "harvest-road.yaml", {"greedy": GREEDY, "random": "random"}, 2, games=2, seed=0)
    for b in out["bots"].values():
        lo, hi = b["win_ci"]
        assert 0 <= lo <= b["win_rate"] <= hi <= 1


def test_AC_084_4_stale_log_is_retried_and_moves_are_reported(tmp_path):
    """画面などが先に書いたら、古い局面で選んだ手は記録しない（StaleLog）。bot-step は読み直して進め、人の席に見える形で足した手を出す。"""
    from bgskills.bot import _apply, bot_step
    from bgskills.session import StaleLog
    s = Session.create(tmp_path / "h", EX / "harvest-road.yaml", 2, {}, 1, strict=True)
    n = len(s.log())
    with pytest.raises(StaleLog):
        _apply(s, "keeper", {"action": "setup", "args": {}}, n + 1)
    assert len(s.log()) == n
    out = bot_step(s, ["P1"], {"P2": str(EX / "bots" / "harvest-greedy.py")})
    assert out["stopped"] == "human" and out["moves"] and len(out["moves"]) == len(s.log()) - n
