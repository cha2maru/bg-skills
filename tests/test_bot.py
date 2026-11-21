"""思考ルーチンの枠組み（RUL-030）：合法手は、その席に見える部品だけ。思考ルーチンは見えない部品の定義を引けない。
リーグ戦は席を回して多数局を回し、方針ごとの勝ちの割合と、同じ種どうしを比べた符号検定を出す。"""
from pathlib import Path

import pytest

from bgskills.bot import Ctx, league, legal_moves, load_policy, play_game, sign_test
from bgskills.session import Session
from bgskills.view import view

EX = Path(__file__).parent.parent / "examples"


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
