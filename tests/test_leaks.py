"""漏れの自動の確かめ（RUL-016 の 5）：でたらめに進めた対局で、プレイヤーとして出せるすべての出力（見え方・記録・候補）に、
そのプレイヤーに一度も見えたことのない部品の ID が出ないこと。出口（コマンド）を足したら、ここに足す。"""
import random
import re
from pathlib import Path

import pytest
import yaml

from bgskills.cli import main
from bgskills.session import Session, apply_op, initial_state
from bgskills.tools import random_step
from bgskills.view import view

EX = Path(__file__).parent.parent / "examples"
GAMES = [("werewolf.yaml", 6, 11), ("rune-clash.yaml", 2, 4), ("beast-duel.yaml", 2, 5)]


def _seen_ids(v) -> set:
    """見え方の中で、ID が出ている部品（見えている）。"""
    out = set()

    def walk(x):
        if isinstance(x, dict):
            if isinstance(x.get("id"), str) and "hidden" not in x:
                out.add(x["id"])
            for i in x.get("ids") or []:
                out.add(i)
            for y in x.values():
                walk(y)
        elif isinstance(x, list):
            for y in x:
                walk(y)
    walk(v.get("areas"))
    return out


def _ever_seen(s, player) -> set:
    """記録を最初から再生し、各時点の見え方で一度でも見えた部品。"""
    st, seen = initial_state(s.defn, s.meta.get("start") == "box"), set()
    seen |= _seen_ids(view(s.defn, st, player))
    for i, op in enumerate(s.log(), 1):
        st = apply_op(s.defn, st, op, s.meta["seed"], i)
        seen |= _seen_ids(view(s.defn, st, player))
        if op.get("by") == player and isinstance(op.get("obj"), str):  # 自分が動かした物は知っている
            seen.add(op["obj"])
    return seen


@pytest.mark.parametrize("game,players,seed", GAMES)
def test_no_never_seen_part_ids_in_player_outputs(tmp_path, capsys, game, players, seed):
    s = Session.create(tmp_path / "s", EX / game, players, {}, seed, strict=True)
    rnd, staged = random.Random(seed), {}
    for _ in range(rnd.randint(40, 80)):
        if random_step(s, rnd, staged):
            break
    distinct = {p for p in s.defn.parts if s.defn.distinct(p)}
    token = re.compile("|".join(sorted(map(re.escape, distinct), key=len, reverse=True)))
    for p in s.defn.players:
        never = distinct - _ever_seen(s, p)
        outs = {}
        capsys.readouterr()
        for name, argv in [("show", ["show", str(s.dir), "--as", p]), ("show-compact", ["show", str(s.dir), "--as", p, "--compact"]),
                           ("log", ["log", str(s.dir), "--as", p])] + [
                (f"candidates {a['id']}", ["candidates", str(s.dir), a["id"], "--by", p]) for a in s.defn.data["actions"]
                if "keeper" not in (a.get("by") or [])]:
            main(argv)
            outs[name] = capsys.readouterr()
        for name, out in outs.items():
            found = {m.group(0) for m in token.finditer(out.out + out.err)} & never
            assert not found, f"{game} {p} の {name} に、見えたことのない部品 {sorted(found)[:5]}"


def test_server_log_is_redacted_for_viewer(tmp_path):
    """画面の記録（/api/log?as=P）も、見る立場で伏せる（以前は伏せない記録をそのまま返していた）。"""
    import json
    import threading
    import urllib.request
    from http.server import ThreadingHTTPServer
    from bgskills.server import make_handler
    s = Session.create(tmp_path / "w", EX / "werewolf.yaml", 6, {}, 11)
    s.act("setup", "keeper")
    httpd = ThreadingHTTPServer(("127.0.0.1", 0), make_handler(str(s.dir)))
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    url = f"http://127.0.0.1:{httpd.server_address[1]}"
    try:
        mine = json.loads(urllib.request.urlopen(url + "/api/log?as=P1").read())
        full = json.loads(urllib.request.urlopen(url + "/api/log").read())
    finally:
        httpd.shutdown()
    roles = {"W1", "W2", "SEER", "KNIGHT", "V1", "V2"}
    assert roles & {o.get("obj") for o in full} and not (roles - {s.state()["places"]["role-P1"][0]}) & {o.get("obj") for o in mine}
