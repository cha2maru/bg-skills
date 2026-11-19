"""裁定（RUL-017）：ルールの穴を埋める定義の rulings（sangeki の裁定の書き方を参考）。決まった裁定・未決（分かっている穴）・
一般の原則。対局中の裁定（SPC-019）を、定義へ持ち帰る候補として出す（SPC-020）。"""
from pathlib import Path

import pytest
import yaml

from bgskills.cli import main
from bgskills.definition import load
from bgskills.session import Session
from bgskills.tools import check_refs, complexity, rulings_report
from bgskills.view import view

EX = Path(__file__).parent.parent / "examples"


def test_rulings_in_definition_and_view(tmp_path):
    d = load(EX / "rune-clash.yaml", 2)
    assert check_refs(d) == []
    r = rulings_report(d)
    assert r["decided"] == ["J2"] and r["open"][0]["id"] == "J3" and r["principles"][0]["id"] == "J1"
    c = complexity(d)
    assert c["rulings"] == {"count": 3, "open": 1, "principles": 1} and "ruling J3（未決）" in c["machine_layer"]["R5"]
    s = Session.create(tmp_path / "s", EX / "rune-clash.yaml", 2, {}, 1)
    s.act("setup", "keeper")
    card = next(c for c in s.state()["places"]["hand-P1"] if s.defn.parts[c]["kind"] == "dispel") \
        if any(s.defn.parts[c]["kind"] == "dispel" for c in s.state()["places"]["hand-P1"]) else None
    if card:  # 部品の意味に、関わる裁定（解呪は J2）が添えられる
        it = next(x for x in view(s.defn, s.state(), "P1", meaning=True)["areas"]["hand-P1"]["shown"] if x.get("id") == card)
        assert any(j["id"] == "J2" for j in it["rulings"])


def test_ruling_shape_is_checked(tmp_path):
    src = (EX / "rune-clash.yaml").read_text(encoding="utf-8")
    bad = src.replace("    status: open  # 未決：分かっている穴。今のエンジンは「引けないだけ」\n", "").replace(
        "    rules: [R4]\n    refs: [dispel]", "    rules: [R9]\n    refs: [dispel]")
    (tmp_path / "d.yaml").write_text(bad, encoding="utf-8")
    refs = [x["ref"] for x in check_refs(load(tmp_path / "d.yaml", 2))]
    assert any("decision（裁定）がない" in x for x in refs) and "R9" in refs


def test_session_rulings_to_bring_back(tmp_path, capsys):
    s = Session.create(tmp_path / "s", EX / "werewolf.yaml", 5, {}, 1, strict=False)
    s.apply({"op": "ruling", "question": "投票しない（棄権する）ことはできるか", "decision": "できる。その票は数えない",
             "by": "keeper", "rules": ["R7"]})
    s.apply({"op": "ruling", "question": "夜に話した村人はどうなるか", "decision": "警告だけ（罰はない）", "by": "keeper"})
    capsys.readouterr()
    main(["rulings", str(s.dir)])
    back = yaml.safe_load(capsys.readouterr().out)["to_bring_back"]
    # 定義で未決（J3）の問いを対局で裁いたら、J3 を決まった裁定に書き換える候補になる
    assert [b["id"] for b in back] == ["J3", "J-s-2"] and back[0]["decision"].startswith("できる")
    assert all(b["authority"] == "keeper" and b["status"] == "decided" and b["found_in"] == "s" for b in back)
