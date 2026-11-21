"""画面（bg serve）の受入基準を、ヘッドレスのブラウザで確かめる。playwright は依存に入れていない。

実行：uv run --with playwright pytest tests/test_ui.py
ブラウザは playwright のキャッシュの chromium_headless_shell を使う（BG_CHROMIUM で上書きできる）。
"""
import glob
import json
import os
import threading
from http.server import ThreadingHTTPServer
from pathlib import Path

import pytest

pw = pytest.importorskip("playwright.sync_api")

from bgskills.server import make_handler  # noqa: E402
from bgskills.session import Session  # noqa: E402

EX = Path(__file__).parent.parent / "examples"
ALL_ON = """try { localStorage.setItem("bg-show", JSON.stringify(["ids","states","vis","orient","meta","hidden","help"])) } catch (e) {}"""


def _chromium():
    if os.environ.get("BG_CHROMIUM"):
        return os.environ["BG_CHROMIUM"]
    hits = sorted(glob.glob(os.path.expanduser("~/.cache/ms-playwright/chromium_headless_shell-*/*/chrome-headless-shell")))
    return hits[-1] if hits else None


@pytest.fixture(scope="module")
def browser():
    with pw.sync_playwright() as p:
        b = p.chromium.launch(executable_path=_chromium())
        yield b
        b.close()


def _serve(session_dir):
    httpd = ThreadingHTTPServer(("127.0.0.1", 0), make_handler(session_dir))
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    return httpd, f"http://127.0.0.1:{httpd.server_address[1]}/"


@pytest.fixture
def kag(tmp_path, browser):
    s = Session.create(tmp_path / "k", EX / "kagaribi.yaml", 2, {"P1": "agent:a", "P2": "human"}, 7)
    s.apply({"op": "shuffle", "area": "deck"})
    for p in ("P1", "P1", "P1", "P2", "P2", "P2"):
        s.apply({"op": "move", "obj": "top:deck", "to": f"hand-{p}", "by": p, "rule": "R1"})
    httpd, url = _serve(s.dir)
    page = browser.new_page(viewport={"width": 1400, "height": 950})
    errors = []
    page.on("pageerror", lambda e: errors.append(str(e)))
    page.add_init_script(ALL_ON)  # 既存の受入基準は詳しい表示を前提にする（SPC-049 の既定は名前だけ）
    page.goto(url)
    page.wait_for_selector(".tablegrid")
    yield s, page, errors
    assert errors == []
    page.close()
    httpd.shutdown()


def test_AC_027_1_seats_rotate_to_viewer(kag):
    s, page, _ = kag
    page.select_option("#as", "P2")
    page.wait_for_timeout(500)
    assert page.locator(".seat.bottom .label").inner_text().startswith("P2")
    assert page.locator(".seat.top .label").inner_text().startswith("P1")
    assert page.locator(".cell.center [data-area=deck]").count() == 1


def test_AC_027_2_nested_player_area(kag):
    _, page, _ = kag
    assert page.locator("[data-area=player-P1] [data-area=hand-P1]").count() == 1


def test_AC_028_1_drag_logs_actor_and_rule(kag):
    s, page, _ = kag
    page.select_option("#by", "P1")
    page.select_option("#rule", "R2")
    src = page.locator("[data-area=deck] .card").last
    dst = page.locator("[data-area=discard]")
    src.hover()
    page.mouse.down()
    page.mouse.move(400, 400, steps=4)
    dst.hover(position={"x": 120, "y": 30})
    page.mouse.up()
    page.wait_for_timeout(700)
    last = s.log()[-1]
    assert last["to"] == "discard" and last["by"] == "P1" and last["rule"] == "R2"


def test_AC_029_agent_op_redrawn(kag):
    s, page, _ = kag
    top = s.state()["places"]["deck"][-1]
    s.apply({"op": "move", "obj": top, "to": "discard", "by": "keeper"})  # エージェント側（bg op と同じ経路）
    page.wait_for_selector(f"[data-area=discard] [data-obj='{top}']", timeout=2000)


def test_AC_030_backs(kag):
    _, page, _ = kag
    page.select_option("#as", "P1")
    page.wait_for_timeout(500)
    assert page.locator("[data-area=hand-P2] .card.hidden").count() == 3
    assert "18 枚" in page.locator("[data-area=deck] .pile").inner_text()
    own = page.locator("[data-area=hand-P1] .card").first.inner_text()
    assert "持ち主（P1）" in own and "facing" not in own


def test_AC_031_and_038_4_tap_flip_orientation(kag):
    s, page, _ = kag
    s.apply({"op": "move", "obj": "top:hand-P1", "to": "fire-P1", "facing": "up"})
    obj = s.log()[-1]["obj"]
    page.wait_for_selector(f"[data-area=fire-P1] [data-obj='{obj}']")
    card = page.locator(f"[data-obj='{obj}']")
    card.click()
    page.wait_for_timeout(150)
    page.locator(f"[data-obj='{obj}']").click()  # ダブルクリック（自分で数える方式）
    page.wait_for_timeout(700)
    c = page.locator(f"[data-obj='{obj}']")
    box = c.bounding_box()
    assert s.state()["states"][obj]["turn"] == "sideways" and box["width"] > box["height"]  # 横長
    assert "→" in c.locator(".orient").inner_text()  # 上が右を向く（AC-038-4）
    c.click()
    page.keyboard.press("f")
    page.wait_for_timeout(700)
    assert s.state()["states"][obj]["facing"] == "down" and "down" in page.locator(f"[data-obj='{obj}']").get_attribute("class")


def test_AC_032_links(tmp_path, browser):
    d = {"game": {"id": "l", "version": 1, "players": {"min": 1, "max": 1}}, "players": [{"id": "A"}],
         "areas": [{"id": "board", "areas": [{"id": f"a{i}", "pos": [i % 2, i // 2]} for i in range(4)]}],
         "links": [{"between": [f"a{i}", f"a{j}"], "type": t} for i, j, t in
                   [(0, 1, "h"), (2, 3, "h"), (0, 2, "v"), (1, 3, "v"), (0, 3, "d"), (1, 2, "d")]],
         "objects": []}
    p = tmp_path / "l.yaml"
    p.write_text(json.dumps(d), encoding="utf-8")
    s = Session.create(tmp_path / "s", p, 1, {}, 1)
    httpd, url = _serve(s.dir)
    page = browser.new_page()
    page.goto(url)
    page.wait_for_selector("svg.links line", state="attached")
    assert page.locator("svg.links line").count() == 6 and page.locator("svg.links text").count() == 6
    page.close()
    httpd.shutdown()


def test_AC_036_hex_map(tmp_path, browser):
    s = Session.create(tmp_path / "h", EX / "hex-skirmish.yaml", 2, {}, 1)
    httpd, url = _serve(s.dir)
    page = browser.new_page(viewport={"width": 1400, "height": 1000})
    page.goto(url)
    page.wait_for_selector(".hexcell")
    assert page.locator(".hexcell").count() == 19
    xs = {round(page.locator(f"[data-area='h{q}_0']").bounding_box()["x"]) for q in (-1, 0, 1)}
    assert len(xs) == 3  # 横に並ぶ
    src = page.locator("[data-area=reserve-R] .card").last
    src.hover()
    page.mouse.down()
    page.mouse.move(500, 300, steps=4)
    page.locator("[data-area='h0_0']").hover()
    page.mouse.up()
    page.wait_for_timeout(700)
    assert s.log()[-1]["to"] == "h0_0"
    page.screenshot(path=str(tmp_path / "hex.png"))
    page.close()
    httpd.shutdown()


def test_AC_040_1_action_button(kag):
    s, page, _ = kag
    page.select_option("#by", "P1")
    n = len(s.state()["places"]["hand-P1"])
    page.locator("#actions button", has_text="山札から 1 枚引く").click()
    page.wait_for_timeout(700)
    assert len(s.state()["places"]["hand-P1"]) == n + 1 and s.log()[-1]["action"] == "draw"


def test_AC_040_2_and_041_1_bound_action_on_card(kag):
    s, page, _ = kag
    wood = next(o for o in s.state()["places"]["deck"] if o.startswith("W"))
    s.apply({"op": "move", "obj": wood, "to": "hand-P1"})
    page.select_option("#by", "P1")
    page.wait_for_selector(f"[data-area=hand-P1] [data-obj='{wood}']")
    page.locator(f"[data-obj='{wood}']").click()
    page.locator("#inspect button", has_text="薪を火に置く").click()
    page.wait_for_timeout(700)
    st = s.state()
    assert wood in st["places"]["fire-P1"] and st["states"][wood]["facing"] == "up" and s.log()[-1]["action"] == "stoke"


def test_AC_041_2_bound_action_on_area(kag):
    _, page, _ = kag
    page.select_option("#by", "P1")
    page.locator("[data-area=deck] > .head b").click()
    page.wait_for_timeout(300)
    assert page.locator("#inspect button", has_text="山札から 1 枚引く").count() == 1


def test_AC_042_fold(kag):
    s, page, _ = kag
    n = len(s.log())
    page.locator("[data-area=deck] > .head .fold").click()
    page.wait_for_timeout(300)
    assert "たたんでいる：18" in page.locator("[data-area=deck]").inner_text()
    assert page.locator("[data-area=deck] .card").count() == 0 and len(s.log()) == n
    page.locator("[data-area=deck] > .head .fold").click()  # 次のテストのためにひらいておく（localStorage）


def test_AC_048_2_reorder_in_ordered_hand(tmp_path, browser):
    d = {"game": {"id": "o", "version": 1, "players": {"min": 1, "max": 1}}, "players": [{"id": "A"}],
         "kinds": {"card": {"base": "object"}},
         "areas": [{"id": "hand", "owner": "A", "ordered": True}],
         "objects": [{"id": x, "kind": "card", "start": "hand"} for x in ("A1", "B1", "C1")]}
    p = tmp_path / "o.yaml"
    p.write_text(json.dumps(d), encoding="utf-8")
    s = Session.create(tmp_path / "s", p, 1, {}, 1)
    httpd, url = _serve(s.dir)
    page = browser.new_page()
    page.goto(url)
    page.wait_for_selector("[data-obj=C1]")
    page.locator("[data-obj=C1]").hover()
    page.mouse.down()
    page.mouse.move(10, 10, steps=3)
    page.locator("[data-obj=A1]").hover()
    page.mouse.up()
    page.wait_for_timeout(700)
    assert s.state()["places"]["hand"] == ["C1", "A1", "B1"]
    assert [e.get_attribute("data-obj") for e in page.locator("[data-area=hand] .card").all()] == ["C1", "A1", "B1"]
    page.close()
    httpd.shutdown()


def test_AC_049_display_options(tmp_path, browser):
    s = Session.create(tmp_path / "k", EX / "kagaribi.yaml", 2, {}, 7)
    s.apply({"op": "move", "obj": "top:deck", "to": "hand-P1", "by": "P1"})
    card = s.log()[-1]["obj"]
    httpd, url = _serve(s.dir)
    ctx = browser.new_context()
    page = ctx.new_page()
    page.goto(url)
    page.wait_for_selector(f"[data-obj='{card}']")
    text = page.locator(f"[data-obj='{card}']").inner_text()
    assert card not in text and "turn" not in text and "公開" not in text  # AC-049-1：名前だけ
    page.locator("#showmenu summary").click()
    page.locator("#show-states").check()
    assert "turn" in page.locator(f"[data-obj='{card}']").inner_text()
    page.reload()
    page.wait_for_selector(f"[data-obj='{card}']")
    assert "turn" in page.locator(f"[data-obj='{card}']").inner_text()  # AC-049-2：開き直しても残る
    page.locator("#showmenu summary").click()
    page.locator("#show-states").uncheck()
    page.locator(f"[data-obj='{card}']").click()
    page.wait_for_timeout(300)
    assert "turn" in page.locator(f"[data-obj='{card}']").inner_text()  # AC-049-3：選んだカードだけ状態
    ins = page.locator("#inspect").inner_text()
    assert card in ins and "公開" in ins
    ctx.close()
    httpd.shutdown()


def test_AC_050_metric_badges_on_seats(kag):
    s, page, _ = kag
    s.apply({"op": "move", "obj": "top:hand-P1", "to": "fire-P1", "facing": "up"})
    page.wait_for_timeout(2000)
    assert "火の合計" in page.locator(".seat.bottom .label").inner_text()
    page.locator("#t-metrics").click()
    assert "手札の枚数" in page.locator("#side").inner_text()


def test_AC_051_flow_bar(kag):
    s, page, _ = kag
    assert "本番" in page.locator("#actions .flowline").inner_text()
    assert page.locator("#actions .ph.now").inner_text() == "引く"
    page.locator("#actions button", has_text="次のフェーズへ").click()
    page.wait_for_timeout(700)
    assert s.state()["flow"]["phase"] == "act" and page.locator("#actions .ph.now").inner_text() == "行為"


def test_RUL009_talk_tab_and_whisper(tmp_path, browser):
    """発言の欄（RUL-009）：内緒話は、聞いていない人には話したことだけ。画面から話すと記録に残る。"""
    s = Session.create(tmp_path / "w", EX / "werewolf.yaml", 5, {}, 1, strict=False)
    s.apply({"op": "say", "by": "P1", "to": ["P2"], "text": "ひみつ"})
    httpd, url = _serve(s.dir)
    page = browser.new_page(viewport={"width": 1400, "height": 950})
    errors = []
    page.on("pageerror", lambda e: errors.append(str(e)))
    page.goto(url)
    page.wait_for_selector(".tablegrid")
    page.select_option("#as", "P3")
    page.wait_for_timeout(400)
    page.click("#t-talk")
    assert "（内緒話）" in page.locator("#talk").inner_text() and "ひみつ" not in page.locator("#talk").inner_text()
    page.select_option("#as", "P2")
    page.wait_for_timeout(400)
    page.click("#t-talk")
    assert "ひみつ" in page.locator("#talk").inner_text()
    page.select_option("#by", "P2")
    page.click("#t-talk")
    page.fill("#side input.small", "こんにちは")
    page.click("#side button[type=submit]")
    page.wait_for_timeout(500)
    assert {k: v for k, v in s.state()["talk"][-1].items() if k in ("by", "text")} == {"by": "P2", "text": "こんにちは"}
    assert errors == []
    page.close()
    httpd.shutdown()


def test_polygon_areas_hit_test(tmp_path, browser):
    """複雑なエリアの形（poly）：外接する四角が重なっても、点を含む多角形のエリアだけが受ける。"""
    import yaml
    d = {"format": "bg-def/0.1", "game": {"id": "poly", "name": "多角形", "version": 1, "players": {"min": 1, "max": 1}},
         "players": [{"id": "P1"}], "kinds": {"cell": {"base": "area"}, "pawn": {"base": "object", "shape": "round"}},
         "areas": [{"id": "board", "name": "盤", "aspect": "1 / 1", "areas": [
             {"id": "a", "name": "左下", "kind": "cell", "poly": [[0, 0], [1, 1], [0, 1]], "color": "#cde"},
             {"id": "b", "name": "右上", "kind": "cell", "poly": [[0, 0], [1, 0], [1, 1]], "color": "#edc"}]}],
         "objects": [{"id": "p", "kind": "pawn", "start": "a"}], "rules": [{"id": "R1", "text": "置く"}]}
    path = tmp_path / "poly.yaml"
    path.write_text(yaml.safe_dump(d, allow_unicode=True), encoding="utf-8")
    s = Session.create(tmp_path / "s", path, 1, {}, 1)
    httpd, url = _serve(s.dir)
    page = browser.new_page(viewport={"width": 1400, "height": 950})
    page.goto(url)
    page.wait_for_selector(".polycell")
    box = page.locator(".rectwrap").bounding_box()
    hit = lambda fx, fy: page.evaluate("([x, y]) => document.elementFromPoint(x, y).closest('[data-area]')?.dataset.area",
                                      [box["x"] + box["width"] * fx, box["y"] + box["height"] * fy])
    assert hit(0.15, 0.85) == "a" and hit(0.85, 0.15) == "b"  # 同じ外接四角の中でも、三角形で分かれる
    pawn = page.locator("[data-obj=p]").bounding_box()
    page.mouse.move(pawn["x"] + pawn["width"] / 2, pawn["y"] + pawn["height"] / 2)
    page.mouse.down()
    page.mouse.move(box["x"] + box["width"] * 0.8, box["y"] + box["height"] * 0.2, steps=8)
    page.mouse.up()
    page.wait_for_timeout(500)
    assert s.state()["places"]["b"] == ["p"]
    page.close()
    httpd.shutdown()


def test_many_seats_and_wide_table(tmp_path, browser):
    """8 人の卓（左・上・右の辺に席を並べる）と、横の欄をたたんで卓を広くする・拡大縮小する（表示だけ）。"""
    s = Session.create(tmp_path / "w", EX / "werewolf.yaml", 8, {}, 1)
    httpd, url = _serve(s.dir)
    page = browser.new_page(viewport={"width": 1400, "height": 950})
    errors = []
    page.on("pageerror", lambda e: errors.append(str(e)))
    page.goto(url)
    page.wait_for_selector(".tablegrid")
    counts = {k: page.locator(f".cell.{k} > .seat").count() for k in ("bottom", "left", "top", "right")}
    assert counts == {"bottom": 1, "left": 2, "top": 3, "right": 2}
    tops = page.locator(".cell.top > .seat").evaluate_all("els => els.map(e => e.getBoundingClientRect().top)")
    assert max(tops) - min(tops) < 5  # 上の辺の 3 席は横に並ぶ
    w0 = page.locator("#table").bounding_box()["width"]
    page.click("#tog-inspect")
    page.click("#tog-side")
    page.wait_for_timeout(300)
    assert not page.locator("#inspect").is_visible() and not page.locator("#sidepanel").is_visible()
    assert page.locator("#table").bounding_box()["width"] > w0 + 250  # 卓が広くなる（ルールの欄 300px のぶん。調べる欄は選んだときだけ重ねて出す）
    page.select_option("#zoom", "0.6")
    page.wait_for_timeout(300)
    assert page.evaluate("document.querySelector('#table').style.zoom") == "0.6"
    page.reload()
    page.wait_for_selector(".tablegrid")
    assert not page.locator("#inspect").is_visible()  # 見る人のブラウザに覚える
    page.evaluate("localStorage.removeItem('bg-ui')")
    assert errors == []
    page.close()
    httpd.shutdown()


def test_offer_accept_button(tmp_path, browser):
    """提案（守られる約束）：相手の画面に「受ける」が出て、押すと中身がまとめて動く。"""
    from test_social import TRADE
    (tmp_path / "trade.yaml").write_text(TRADE, encoding="utf-8")
    s = Session.create(tmp_path / "t", tmp_path / "trade.yaml", 3, {}, 1)
    s.apply({"op": "say", "by": "P1", "text": "木 2 と鉱石 1", "offer": [
        {"op": "move", "obj": "w1", "from": "hand-P1", "to": "hand-P2", "n": 2},
        {"op": "move", "obj": "o1", "from": "hand-P2", "to": "hand-P1"}]})
    httpd, url = _serve(s.dir)
    page = browser.new_page(viewport={"width": 1400, "height": 950})
    errors = []
    page.on("pageerror", lambda e: errors.append(str(e)))
    page.goto(url)
    page.wait_for_timeout(1500)
    assert errors == []
    page.select_option("#by", "P3")  # 相手（with）でない人にはボタンを出さない
    page.click("#t-talk")
    assert page.locator("#talk button:has-text('受ける')").count() == 0
    page.select_option("#by", "P2")
    page.click("#t-talk")
    assert "提案 #0（受付中）" in page.locator("#talk").inner_text()
    page.click("#talk button:has-text('受ける')")
    page.wait_for_timeout(600)
    st = s.state()
    assert st["talk"][0]["status"] == "accepted" and st["places"]["hand-P1"] == [{"w1": 1}, {"o1": 1}]
    assert "成立" in page.locator("#talk").inner_text()
    assert errors == []
    page.close()
    httpd.shutdown()


def test_offer_draft_by_drag(kag):
    """画面で提案を組み立てる：組み立て中は卓で動かしても動かず提案の中身に足され、「提案として話す」で出る。"""
    s, page, _ = kag
    page.select_option("#by", "P1")
    page.click("#t-talk")
    page.click("#draft-toggle")
    n = len(s.log())
    src = page.locator("[data-area=hand-P1] .card").first
    src.hover()
    page.mouse.down()
    page.mouse.move(400, 400, steps=4)
    page.locator("[data-area=hand-P2]").hover(position={"x": 60, "y": 30})
    page.mouse.up()
    page.wait_for_timeout(500)
    assert len(s.log()) == n and "組み立て中の提案（1 件）" in page.locator("#draft").inner_text()
    page.fill("#side input.small", "これをあげる")
    page.click("#side button[type=submit]")
    page.wait_for_timeout(600)
    assert s.state().get("talk"), page.locator("#toast").inner_text()
    t = s.state()["talk"][-1]
    assert t["status"] == "open" and t["with"] == "P2"  # 落とした先は P2 の手札（かその中のカード） and t["by"] == "P1"


def test_stack_bar_pass_button(tmp_path, browser):
    """スタック：解決待ちを上から並べ、見送るボタンで解決が進む。"""
    from test_stack import SPELLS
    (tmp_path / "d.yaml").write_text(SPELLS, encoding="utf-8")
    s = Session.create(tmp_path / "s", tmp_path / "d.yaml", 2, {}, 1)
    s.act("bolt", "P1", {"target": "P2"})
    httpd, url = _serve(s.dir)
    page = browser.new_page(viewport={"width": 1400, "height": 950})
    errors = []
    page.on("pageerror", lambda e: errors.append(str(e)))
    page.goto(url)
    page.wait_for_timeout(1500)
    page.select_option("#by", "P2")
    page.wait_for_timeout(300)
    assert "#1 雷" in page.locator("#stack").inner_text()
    page.click("#stack button:has-text('見送る')")
    page.wait_for_timeout(600)
    assert s.state()["stack"] == [] and errors == []
    page.close()
    httpd.shutdown()


def test_layout_defaults_fixed_cards_fit_and_overlay_inspect(tmp_path, browser):
    """見栄え（RUL-019）：カードは決まった大きさ、卓の大きさは「画面に合わせる」が既定、調べる欄は選んだときだけ重ねて出す、
    枚数の多い置き場は重ねて並べる、空のエリアは --compact に出る（別のテスト）。"""
    s = Session.create(tmp_path / "r", EX / "rune-clash.yaml", 2, {}, 3)
    s.act("setup", "keeper")
    httpd, url = _serve(s.dir)
    page = browser.new_page(viewport={"width": 1440, "height": 900})
    page.goto(url)
    page.wait_for_timeout(1500)
    assert page.locator("#zoom").input_value() == "fit"
    assert not page.locator("#inspect").is_visible()
    box = page.locator("[data-area=hand-P1] .card").first.bounding_box()
    z = float(page.evaluate("document.querySelector('#table').style.zoom") or 1)
    assert abs(box["width"] / z - 64) < 2 and abs(box["height"] / z - 90) < 2
    assert page.locator("[data-area=deck-P1] .items.fan").count() == 1  # 山札は重ねて並べる
    page.locator("[data-area=hand-P1] .card").first.click()
    page.wait_for_timeout(300)
    assert page.locator("#inspect").is_visible()
    page.keyboard.press("Escape")
    page.wait_for_timeout(300)
    assert not page.locator("#inspect").is_visible()
    page.close()
    httpd.shutdown()


def test_stacked_items_drawn_overlapped(tmp_path, browser):
    """重なりの表現（RUL-020）：精霊獣に付けたエネルギーは本体の下にずらして重ね、ダメージカウンター（数える部品）は右肩に載せる。
    「重なりを一覧で出す」に切り替えると、カードの中の一覧に戻る。重ねたカードも掴める。"""
    s = Session.create(tmp_path / "d", EX / "beast-duel.yaml", 2, {}, 3, strict=False)
    s.act("setup", "keeper")
    s.apply({"op": "move", "obj": "P1-hibana-1", "to": "active-P1", "by": "keeper"})
    for e in ("P1-fire-1", "P1-fire-2"):
        s.apply({"op": "move", "obj": e, "to": "P1-hibana-1", "by": "keeper"})
    s.apply({"op": "move", "obj": "counter-pool", "from": "supply", "to": "P1-hibana-1", "n": 3, "by": "keeper"})
    httpd, url = _serve(s.dir)
    page = browser.new_page(viewport={"width": 1440, "height": 900})
    page.goto(url)
    page.wait_for_timeout(1500)
    wrap = page.locator(".stackwrap").filter(has=page.locator("[data-obj=P1-hibana-1]"))
    assert wrap.locator(".under [data-obj]").count() == 2 and "×3" in wrap.locator(".tokens").inner_text()
    host, under = page.locator("[data-obj=P1-hibana-1]").bounding_box(), page.locator("[data-obj=P1-fire-2]").bounding_box()
    assert under["y"] > host["y"]  # 下へずらしてのぞく
    page.click("#showmenu summary")
    page.check("#show-stacklist")
    page.wait_for_timeout(300)
    assert page.locator(".stackwrap").count() == 0 and page.locator("[data-obj=P1-hibana-1] .stack").count() == 1
    page.close()
    httpd.shutdown()


def test_map_table_not_double_shrunk(tmp_path, browser):
    """地図のある卓（多角形の州）：「画面に合わせる」でも卓全体は縮めず（zoom 1）、地図だけを地図の上端から画面の下までに収める。
    以前は二重に縮めて州の名前と駒が読めなくなった。"""
    import yaml
    cells = [{"id": f"c{i}", "name": f"州{i}", "kind": "cell", "poly": [[i / 6, 0], [(i + 1) / 6, 0], [(i + 1) / 6, 1], [i / 6, 1]],
              "color": "#cde"} for i in range(6)]
    d = {"format": "bg-def/0.1", "game": {"id": "map", "name": "地図", "version": 1, "players": {"min": 1, "max": 1}},
         "players": [{"id": "P1"}], "kinds": {"cell": {"base": "area"}},
         "areas": [{"id": "board", "name": "地図", "aspect": "4 / 3", "areas": cells}] +
                  [{"id": f"r{i}", "name": f"置き場{i}"} for i in range(12)],
         "objects": [], "rules": [{"id": "R1", "text": "地図"}]}
    path = tmp_path / "map.yaml"
    path.write_text(yaml.safe_dump(d, allow_unicode=True), encoding="utf-8")
    s = Session.create(tmp_path / "s", path, 1, {}, 1)
    httpd, url = _serve(s.dir)
    page = browser.new_page(viewport={"width": 1440, "height": 900})
    page.goto(url)
    page.wait_for_timeout(1500)
    assert page.evaluate("document.querySelector('#table').style.zoom") in ("1", "")
    box = page.locator(".rectwrap").bounding_box()
    assert box["y"] + box["height"] <= 900 + 1
    page.close()
    httpd.shutdown()


def test_turn_seat_recent_move_and_card_face(tmp_path, browser):
    """見やすさ（RUL-022）：手番の人の席に「手番」、最後に動いた部品と置き場を強調、数の属性を大きく、
    子エリアだけを持つ入れ物には「空」を出さない。"""
    s = Session.create(tmp_path / "k", EX / "kagaribi.yaml", 2, {}, 1)
    s.act("setup", "keeper")
    card = s.state()["places"]["hand-P1"][0]
    s.apply({"op": "move", "obj": card, "to": "discard", "by": "P1"})
    httpd, url = _serve(s.dir)
    page = browser.new_page(viewport={"width": 1440, "height": 900})
    page.goto(url)
    page.wait_for_timeout(1500)
    assert page.locator(".seat.turn").count() == 1
    assert page.locator(f".card.recent[data-obj='{card}']").count() == 1
    assert page.locator("[data-area=discard].recent").count() == 1
    assert page.locator(".card .bignum").count() >= 1
    page.close()
    httpd.shutdown()


def test_cards_and_tokens_look_different(tmp_path, browser):
    """カードとトークン（RUL-023）：種類の shape（pawn など）を持つ部品は立体の駒、持ち主の色で塗る。数える部品には形の印。
    得点の道（マスの多い盤）は小さなマスで描く。"""
    s = Session.create(tmp_path / "h", EX / "harvest-road.yaml", 2, {}, 7)
    s.act("setup", "keeper")
    httpd, url = _serve(s.dir)
    page = browser.new_page(viewport={"width": 1440, "height": 900})
    page.goto(url)
    page.wait_for_timeout(1500)
    pawn = page.locator("[data-obj=marker-P1]")
    assert "shape-pawn" in pawn.get_attribute("class") and "token" in pawn.get_attribute("class")
    assert page.evaluate("getComputedStyle(document.querySelector('[data-obj=marker-P1]')).getPropertyValue('--kind').trim()") == "#d0453a"
    card = page.locator("[data-area=market] .card").first
    assert "token" not in card.get_attribute("class")
    assert page.locator(".kids.grid.dense").count() == 1
    page.close()
    httpd.shutdown()


def test_view_error_does_not_keep_previous_viewpoint(tmp_path, browser):
    """見え方を作れなかったら（定義の式の誤りなど）、画面は前の立場（キーパー）の局面を出し続けない（漏れ。RUL-024 の検証で見つかった）。
    詳細ルールは、ルール欄で手引きの後にたたんで出す。"""
    import yaml
    d = yaml.safe_load((EX / "kagaribi.yaml").read_text(encoding="utf-8"))
    d["actions"][1]["require"] = [{"expr": "no_such_function()", "text": "壊れた条件"}]
    d["rules"].append({"id": "CR1", "type": "always", "detail": True, "text": "詳細ルールの文"})
    p = tmp_path / "broken.yaml"
    p.write_text(yaml.safe_dump(d, allow_unicode=True), encoding="utf-8")
    s = Session.create(tmp_path / "b", p, 2, {}, 1)
    s.act("setup", "keeper")
    httpd, url = _serve(s.dir)
    page = browser.new_page(viewport={"width": 1440, "height": 900})
    page.goto(url)
    page.wait_for_timeout(1500)
    assert page.locator("[data-area=hand-P2] .card[data-obj]").count() == 3  # キーパーには見える
    assert page.locator("details.detailrules").count() == 1 and not page.locator("details.detailrules").evaluate("e => e.open")
    page.select_option("#as", "P1")
    page.wait_for_timeout(1500)
    assert page.locator("[data-area=hand-P2] .card[data-obj]").count() == 0
    assert "局面を出せない" in page.locator("#table").inner_text()
    page.close()
    httpd.shutdown()


SHAPES = """
format: bg-def/0.1
game: {id: shapes, name: 形の盤, version: 1, players: {min: 1, max: 1}}
players: [{id: P1}]
kinds: {stone: {base: object, shape: disc, distinct: false}}
areas:
  - id: board
    name: 盤
    viewbox: "0 0 200 100"
    color: "#ddd"
    areas:
      - {id: pond, name: 池, path: "M20 50 A30 30 0 1 0 80 50 A30 30 0 1 0 20 50 Z", color: "#9cf"}
      - {id: hill, name: 丘, path: "M120 90 Q150 0 180 90 Z", color: "#9c6", xy: [150, 70]}
  - {id: bag, name: 袋}
objects:
  - {id: stones, kind: stone, count: 5, start: bag}
rules: [{id: R1, type: action, text: 石を池か丘に置く。}]
"""


def test_shape_board_paths_and_drop(tmp_path, browser):
    """形の盤（RUL-025）：viewbox の中の path（円弧・曲線）をエリアとして描き、形に部品を落として動かせる。"""
    (tmp_path / "s.yaml").write_text(SHAPES, encoding="utf-8")
    s = Session.create(tmp_path / "s", tmp_path / "s.yaml", 1, {}, 1)
    httpd, url = _serve(s.dir)
    page = browser.new_page(viewport={"width": 1440, "height": 900})
    page.goto(url)
    page.wait_for_timeout(1500)
    assert page.locator("svg.vbsvg path[data-area=pond]").count() == 1 and page.locator(".vbbox[data-area=hill]").count() == 1
    chip = page.locator("[data-area=bag] .chip").first.bounding_box()
    pond = page.locator("svg.vbsvg path[data-area=pond]").bounding_box()
    page.mouse.move(chip["x"] + 5, chip["y"] + 5)
    page.mouse.down()
    page.mouse.move(pond["x"] + pond["width"] * 0.25, pond["y"] + pond["height"] * 0.5, steps=8)
    page.mouse.up()
    page.wait_for_timeout(800)
    assert s.state()["places"]["pond"] == [{"stones": 1}]
    page.close()
    httpd.shutdown()
