"""ルーン決闘（examples/rune-clash.yaml）を Pyxel で遊ぶサンプル。あなた（P1）とボット（P2）の対戦。

  uv run --with pyxel python samples/pyxel/rune_clash.py      # 遊ぶ（WSLg なら DISPLAY=:0）

ゲームの中身（置き場・ルーン・スタック・条件・勝敗）はすべて bg-skills の定義とエンジン（Session）が持ち、
このファイルは「局面を描く」「クリックをアクションにする」「ボットの手を選ぶ」だけ。定義を直せばそのまま遊びが変わる。
Pyxel の内蔵フォントは英数字だけなので、カード名は英語の短い名前で描く。
"""
from __future__ import annotations

import tempfile
from pathlib import Path

from bgskills.query import candidates
from bgskills.session import OpError, Session
from bgskills.view import view

DEF = Path(__file__).resolve().parents[2] / "examples" / "rune-clash.yaml"
LABEL = {"bolt": "BOLT", "ward": "WARD", "dispel": "DISPEL", "mend": "MEND"}
CAST = {"bolt": "cast-bolt", "ward": "cast-ward", "dispel": "cast-dispel", "mend": "cast-mend"}
ME, BOT = "P1", "P2"


class Table:
    """定義とエンジンの上の、遊ぶための薄い進行役（Pyxel に依存しない。テストから使える）。"""

    def __init__(self, seed: int = 1, path=None):
        self.s = Session.create(Path(path or tempfile.mkdtemp()) / "game", DEF, 2, {}, seed)
        self.s.act("setup", "keeper")
        self.s.apply({"op": "advance", "to": "stage", "by": "keeper"})
        self.msg = ["YOUR TURN", "click a card to cast", "END to finish the turn"]
        self._start_turn()

    # ---- 読む ----
    def st(self):
        return self.s.state()

    def me_view(self):
        return view(self.s.defn, self.st(), ME)

    def count(self, area, kind):
        return sum(next(iter(i.values())) for i in self.st()["places"].get(area, []) if isinstance(i, dict)
                   and self.s.defn.parts[next(iter(i))]["kind"] == kind)

    def kind(self, card):
        return self.s.defn.parts[card]["kind"]

    def hand(self, p=ME):
        return list(self.st()["places"][f"hand-{p}"])

    def active(self):
        return self.st()["flow"]["active"]

    def waiting(self):
        return self.me_view().get("stack_waiting") or []

    def winner(self):
        r = self.st()["result"]  # 定義の flow.auto_end で、終わりの条件を満たすとエンジンが結果を書く
        if not r:
            return None
        win = [p for p, v in (r.get("results") or {}).items() if v == "win"]
        return win[0] if len(win) == 1 else "DRAW"

    def say(self, text):
        self.msg = (self.msg + [text])[-4:]

    # ---- 行う ----
    def _start_turn(self):
        p = self.active()
        try:
            self.s.act("draw", p)
        except OpError:
            self.say(f"{p} cannot draw")

    def _target(self, who):
        """打ち消す対象：相手が積んだ一番上の呪文。"""
        top = next((e for e in reversed(self.st().get("stack", [])) if e["by"] != who), None)
        return str(top["n"]) if top else None

    def cast(self, card, who=ME) -> bool:
        k = self.kind(card)
        args = {"card": card}
        if k in ("ward", "dispel"):
            t = self._target(who)
            if not t:
                self.say(f"{LABEL[k]}: no target on the stack")
                return False
            args["spell"] = t
        try:
            self.s.act(CAST[k], who, args)
        except OpError as e:
            self.say(_short(str(e)))
            return False
        self.say(f"{who} casts {LABEL[k]}")
        return True

    def pass_(self, who=ME):
        n = len(self.st().get("stack_done") or [])
        try:
            self.s.apply({"op": "pass", "by": who})
        except OpError as e:
            self.say(_short(str(e)))
            return
        for e in (self.st().get("stack_done") or [])[n:]:  # 見送りで解決したもの
            self.say(f"{e['by']} {e['action'].replace('cast-', '').upper()}: {e['status']}")

    def end_turn(self, who=ME) -> bool:
        if self.st().get("stack", []):
            self.say("resolve the stack first")
            return False
        try:
            self.s.apply({"op": "advance", "to": "turn", "by": who})
        except OpError as e:
            self.say(_short(str(e)))
            return False
        self._start_turn()
        return True

    # ---- ボット（候補と条件だけで選ぶ。local/rune-bot.py と同じ考え） ----
    def bot_step(self, BOT=BOT) -> bool:
        """ボット（既定は P2）が 1 つ行う。行うことがなければ False。"""
        if self.winner():
            return False
        st = self.st()
        if st.get("stack", []):
            if BOT not in self.waiting():
                return False
            top = st.get("stack", [])[-1]
            if top["by"] != BOT and top["action"] == "cast-bolt":
                for k in ("ward", "dispel"):
                    cards = [c for c in self.hand(BOT) if self.kind(c) == k]
                    if cards and self.cast(cards[0], BOT):
                        return True
            self.pass_(BOT)
            return True
        if self.active() != BOT:
            return False
        dmg = self.count(f"life-{BOT}", "wound")
        for k in (["mend"] if dmg >= 4 else []) + ["bolt"]:
            cards = [c for c in self.hand(BOT) if self.kind(c) == k]
            ok = [c["id"] for c in candidates(self.s.defn, st, CAST[k], BOT, "card", {}) if not c["problems"]]
            if cards and ok and self.cast(ok[0], BOT):
                return True
        self.end_turn(BOT)
        self.say("YOUR TURN" if BOT != ME else "BOT TURN")
        return True


def _short(text: str) -> str:
    """エンジンの文（日本語）は Pyxel で描けないので、要点を英語に寄せる。"""
    for jp, en in (("ルーンが足りない", "not enough runes"), ("手番ではない", "not your turn"), ("解決待ち", "stack pending"),
                   ("候補がない", "no target"), ("雷撃ではない", "target is not BOLT"), ("山札がない", "deck empty")):
        if jp in text:
            return en
    return "not allowed"


def run():
    import pyxel

    W, H = 256, 192
    CW, CH = 36, 48
    t = Table()

    def hand_rects():
        cards = state["t"].hand()
        step = min(CW + 4, (W - 16 - CW) // max(1, len(cards) - 1))  # 多いときは重ねて並べる
        return [(8 + i * step, H - CH - 8, c) for i, c in enumerate(cards)]

    buttons = {"PASS": (W - 92, 108, 40, 14), "END": (W - 48, 108, 40, 14), "NEW": (W - 48, 4, 40, 12)}

    def inside(x, y, r):
        return r[0] <= x < r[0] + r[2] and r[1] <= y < r[1] + r[3]

    state = {"t": t, "tick": 0}

    def update():
        t = state["t"]
        state["tick"] += 1
        if pyxel.btnp(pyxel.MOUSE_BUTTON_LEFT):
            x, y = pyxel.mouse_x, pyxel.mouse_y
            if inside(x, y, buttons["NEW"]):
                state["t"] = Table(seed=state["tick"])
                return
            if t.winner():
                return
            hit = [c for rx, ry, c in hand_rects() if inside(x, y, (rx, ry, CW, CH))]
            if hit:  # 重なっているときは上（右）のカード
                t.cast(hit[-1])
            if inside(x, y, buttons["PASS"]):
                t.pass_()
            if inside(x, y, buttons["END"]):
                if t.end_turn():
                    t.say("BOT TURN")
        if state["tick"] % 20 == 0:  # ボットはゆっくり 1 つずつ
            t.bot_step()

    def card(x, y, k, hidden=False, cost=None):
        pyxel.rectb(x, y, CW, CH, 7)
        if hidden:
            pyxel.rect(x + 2, y + 2, CW - 4, CH - 4, 5)
            return
        col = {"bolt": 8, "ward": 12, "dispel": 13, "mend": 11}[k]
        pyxel.rect(x + 1, y + 1, CW - 2, 10, col)
        pyxel.text(x + 3, y + 3, LABEL[k], 0)
        pyxel.text(x + 3, y + 16, f"cost {cost}", 7)

    def draw():
        t = state["t"]
        pyxel.cls(1)
        st = t.st()
        # 相手（ボット）
        pyxel.text(8, 6, f"BOT  wounds {t.count('life-P2', 'wound')}/10  runes {t.count('pool-P2', 'rune')}", 7)
        for i in range(min(12, len(st["places"]["hand-P2"]))):  # 相手の手札は裏だけ（枚数）
            card(8 + i * 14, 16, None, hidden=True)
        # スタック（上が先に解決）
        pyxel.text(8, 70, "STACK (top resolves first)", 10)
        for i, e in enumerate(list(reversed(st.get("stack", [])))[:4]):
            k = e["action"].replace("cast-", "")
            pyxel.text(12, 79 + i * 8, f"#{e['n']} {e['by']} {LABEL.get(k, k)}", 9 if i == 0 else 6)
        if st.get("stack", []):
            pyxel.text(8, 112, "waiting: " + (",".join(t.waiting()) or "-"), 10)
        # 自分
        pyxel.text(8, 128, f"YOU  wounds {t.count('life-P1', 'wound')}/10  runes {t.count('pool-P1', 'rune')}"
                   f"   turn: {t.active()}", 7)
        for rx, ry, c in hand_rects():
            card(rx, ry, t.kind(c), cost=t.s.defn.parts[c]["attributes"]["cost"])
        for name, (bx, by, bw, bh) in buttons.items():
            pyxel.rect(bx, by, bw, bh, 3 if name != "NEW" else 2)
            pyxel.text(bx + 6, by + 4, name, 7)
        for i, m in enumerate(t.msg):  # 右の列に最近の出来事
            pyxel.text(124, 70 + i * 8, m[:32], 15)
        win = t.winner()
        if win:
            pyxel.rect(60, 60, 136, 30, 0)
            pyxel.text(72, 72, "YOU WIN!" if win == ME else ("DRAW" if win == "DRAW" else "BOT WINS"), 10)
        pyxel.circb(pyxel.mouse_x, pyxel.mouse_y, 2, 7)

    pyxel.init(W, H, title="Rune Clash (bg-skills)")
    pyxel.mouse(True)
    pyxel.run(update, draw)


if __name__ == "__main__":
    run()
