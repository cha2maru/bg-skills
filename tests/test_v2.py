"""第二版（RUL-028）の受入基準：作業場・案の重ね方・比べる・試行の記録・設計の状態・手引き・スキル（SPC-071〜077）。"""
import json
import shutil
import subprocess
from pathlib import Path

import pytest
import yaml

from bgskills.cli import main
from bgskills.definition import load
from bgskills.design import compare, experiments, init, record, rulebook, status
from bgskills.session import Session
from bgskills.tools import check_refs, selfplay

ROOT = Path(__file__).parent.parent


@pytest.fixture
def ws(tmp_path):
    init(tmp_path / "g", "試作", "2-4")
    return tmp_path / "g"


def test_AC_071_1_init_creates_runnable_workspace(ws):
    for rel in ("game.yaml", "variants/hand-5.yaml", "experiments.jsonl", "journal.md", ".gitignore"):
        assert (ws / rel).exists(), rel
    assert "sessions/" in (ws / ".gitignore").read_text(encoding="utf-8")
    assert check_refs(load(ws / "game.yaml")) == []
    r = selfplay(ws / "game.yaml", 2, games=4)
    assert r["outcomes"] and "打ち切り" not in r["outcomes"] and set(r["win_rate"]) == {"P1", "P2"}


def test_AC_071_2_init_refuses_non_empty(tmp_path):
    (tmp_path / "g").mkdir()
    (tmp_path / "g" / "mine.txt").write_text("x", encoding="utf-8")
    with pytest.raises(ValueError):
        init(tmp_path / "g")
    assert sorted(p.name for p in (tmp_path / "g").iterdir()) == ["mine.txt"]


def test_AC_072_1_variant_overlays_session_and_is_copied(ws, tmp_path):
    s = Session.create(tmp_path / "s", ws / "game.yaml", 2, {}, 1, variants=[ws / "variants/hand-5.yaml"])
    s.act("setup", "keeper")
    assert len(s.state()["places"]["hand-P1"]) == 5
    meta = yaml.safe_load((s.dir / "session.yaml").read_text(encoding="utf-8"))
    assert meta["variants"] == [{"name": "hand-5", "file": "variant-1.yaml"}] and (s.dir / "variant-1.yaml").exists()


def test_AC_072_2_replace_add_remove_by_id(ws, tmp_path):
    v = tmp_path / "v.yaml"
    v.write_text(yaml.safe_dump({"rules": [{"id": "R2", "type": "turn", "text": "替えた文"}, {"id": "R9", "type": "always", "text": "足した"}],
                                 "remove": ["draw"]}, allow_unicode=True), encoding="utf-8")
    d = load(ws / "game.yaml", 2, None, [v])
    assert d.rules["R2"]["text"] == "替えた文" and "R9" in d.rules and d.rules["R1"]["text"].startswith("20 枚")
    assert "draw" not in {a["id"] for a in d.data["actions"]} and "play" in {a["id"] for a in d.data["actions"]}


def test_AC_072_3_session_keeps_its_copy(ws, tmp_path):
    v = tmp_path / "hand.yaml"
    shutil.copy(ws / "variants/hand-5.yaml", v)
    s = Session.create(tmp_path / "s", ws / "game.yaml", 2, {}, 1, variants=[v])
    s.act("setup", "keeper")
    v.write_text(v.read_text(encoding="utf-8").replace("times: 5", "times: 2"), encoding="utf-8")
    assert len(Session(s.dir).state()["places"]["hand-P1"]) == 5


def test_AC_073_1_compare_base_and_variant(ws):
    r = compare(ws / "game.yaml", {"hand-5": ws / "variants/hand-5.yaml"}, 2, games=4)
    assert set(r["rows"]) == {"base", "hand-5"}
    for row in r["rows"].values():
        assert {"outcomes", "avg_turns", "undecided_rate", "outcome_rates", "win_rate"} <= set(row)
    assert r["rows"]["hand-5"]["avg_turns"] < r["rows"]["base"]["avg_turns"]  # 手札が多いと山札が早く尽きる


def test_AC_074_1_record_selfplay_and_compare(ws, capsys):
    log = ws / "experiments.jsonl"
    main(["selfplay", str(ws / "game.yaml"), "--players", "2", "--games", "3", "--record", str(log)])
    main(["compare", str(ws / "game.yaml"), "--variant", f"hand-5={ws / 'variants/hand-5.yaml'}", "--players", "2", "--games", "3",
          "--record", str(log), "--note", "手札"])
    rows = [json.loads(x) for x in log.read_text(encoding="utf-8").splitlines()]
    assert [r["tool"] for r in rows] == ["selfplay", "compare", "compare"] and rows[2]["variants"] == ["hand-5"]
    assert rows[1]["def_hash"] == rows[0]["def_hash"] != rows[2]["def_hash"] and rows[2]["note"] == "手札"
    assert {"time", "game", "version", "players", "games", "seed", "max_turns", "result"} <= set(rows[0])


def test_AC_074_2_experiments_newest_first(ws):
    log = ws / "experiments.jsonl"
    for n in ("一", "二", "三"):
        record(log, ws / "game.yaml", [], "selfplay", 2, 1, 0, 60, {"outcomes": {}, "avg_turns": 1}, n)
    assert [r["note"] for r in experiments(log, 2)] == ["三", "二"]


def test_AC_075_1_status(ws):
    log = ws / "experiments.jsonl"
    record(log, ws / "game.yaml", [], "selfplay", 2, 1, 0, 60, {"outcomes": {}, "avg_turns": 1})
    st = status(load(ws / "game.yaml"), log)
    assert st["version"] == 1 and st["check_errors"] == 0
    assert st["undecided"]["open_rulings"] == [{"id": "J1", "question": "合計が同じときはどうするか"}]
    assert st["undecided"]["open_questions"] and st["undecided"]["rules_text_only"] == [] and len(st["recent_experiments"]) == 1


def test_AC_076_1_rulebook_hides_detail_and_open(tmp_path):
    d = yaml.safe_load((ROOT / "examples/rune-clash.yaml").read_text(encoding="utf-8"))
    d["rules"].append({"id": "CR1", "type": "always", "detail": True, "text": "審判用の細かい文"})
    p = tmp_path / "r.yaml"
    p.write_text(yaml.safe_dump(d, allow_unicode=True), encoding="utf-8")
    md = rulebook(load(p, 2))
    assert md.startswith("# ルーン決闘") and all(h in md for h in ("## 部品", "## ルール", "## よくある質問"))
    assert "審判用の細かい文" not in md
    opens = [r["question"] for r in d.get("rulings") or [] if r.get("status") == "open"]
    assert opens and all(q not in md for q in opens)


def test_AC_077_1_skills_for_start_and_iterate():
    for name in ("bg-start", "bg-iterate"):
        text = (ROOT / "skills" / name / "SKILL.md").read_text(encoding="utf-8")
        assert text.startswith("---\nname: " + name) and "description:" in text
    if shutil.which("claude"):
        out = subprocess.run(["claude", "plugin", "validate", str(ROOT)], capture_output=True, text=True, timeout=120).stdout
        assert "bg-skills:bg-start" in out and "bg-skills:bg-iterate" in out
