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


def test_candidates_without_from_hide_unseen_parts(tmp_path, capsys):
    """置き場（from）を書かず種類だけで選ぶ引数：候補を卓全体から探すが、相手の手札の ID は出さない（コマンドも画面の API も）。
    ふるよにの再現（RUL-024）で見つかった。"""
    import json
    import threading
    import urllib.request
    from http.server import ThreadingHTTPServer
    from bgskills.server import make_handler
    (tmp_path / "d.yaml").write_text("""
format: bg-def/0.1
game: {id: c, name: 候補, version: 1, players: {min: 2, max: 2}}
players: [{id: P1}, {id: P2}]
kinds: {card: {base: object}}
areas:
  - {id: "hand-{player}", for_each: {player: players}, owner: "{player}", visibility: {face: owner}}
  - {id: pile}
objects:
  - {id: "{player}-c{copy}", for_each: {player: players}, copies: 2, kind: card, owner: "{player}", start: "hand-{player}"}
actions:
  - {id: play, name: 出す, params: [{name: card, kind: card}], steps: [{op: move, obj: "{card}", to: pile}]}
rules: [{id: R1, type: action, text: 自分の手札を出す。}]
""", encoding="utf-8")
    s = Session.create(tmp_path / "s", tmp_path / "d.yaml", 2, {}, 1)
    capsys.readouterr()
    main(["candidates", str(s.dir), "play", "--by", "P1"])
    out = capsys.readouterr().out
    assert "P1-c1" in out and "P2-c" not in out
    httpd = ThreadingHTTPServer(("127.0.0.1", 0), make_handler(str(s.dir)))
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    try:
        url = f"http://127.0.0.1:{httpd.server_address[1]}/api/candidates?action=play&by=P1&param=card"
        ids = {c["id"] for c in json.loads(urllib.request.urlopen(url).read())}
    finally:
        httpd.shutdown()
    assert ids == {"P1-c1", "P1-c2"}
