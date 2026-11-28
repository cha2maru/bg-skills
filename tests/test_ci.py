"""勝ちの割合の 95% の幅（SPC-083）：selfplay・compare の席ごとの win_rate の横に win_ci（Wilson）。"""
import json
from pathlib import Path

from bgskills.design import compare, experiments
from bgskills.sim import selfplay, wilson

EX = Path(__file__).parent.parent / "examples"


def _ci_holds(r):
    assert set(r["win_ci"]) == set(r["win_rate"]) and r["win_ci"]
    for p, (lo, hi) in r["win_ci"].items():
        assert 0 <= lo <= r["win_rate"][p] <= hi <= 1


def test_AC_083_1_selfplay_and_compare_have_win_ci(tmp_path):
    _ci_holds(selfplay(EX / "harvest-road.yaml", 2, games=10))
    _ci_holds(compare(EX / "harvest-road.yaml", {}, 2, games=5)["rows"]["base"])
    log = tmp_path / "experiments.jsonl"  # 幅の無い古い記録も読める
    log.write_text(json.dumps({"time": "t", "result": {"win_rate": {"P1": 0.5}}}) + "\n", encoding="utf-8")
    assert "win_ci" not in experiments(log)[0]


def test_AC_083_1_wilson_edges():
    assert wilson(0, 0) == [0.0, 1.0]
    lo, hi = wilson(10, 10)
    assert hi == 1.0 and 0.6 < lo < 0.75
    lo, hi = wilson(0, 10)
    assert lo == 0.0 and 0.25 < hi < 0.4
