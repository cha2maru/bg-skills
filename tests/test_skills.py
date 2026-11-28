"""スキルと利用者向けの手引きの中の `bg <サブコマンド> …` の例が、今の bg の引数に合うか（SPC-082）。"""
import argparse
import re
from pathlib import Path

from bgskills import cli

ROOT = Path(__file__).parent.parent
DOCS = sorted(ROOT.glob("skills/*/SKILL.md")) + [ROOT / "docs" / "commands.md"]


def _parsers():
    """main() の中で作る argparse を取り出す（parse_args の手前で止める）。"""
    got = {}
    orig = argparse.ArgumentParser.parse_args

    def stop(self, *a, **k):
        got["p"] = self
        raise SystemExit(0)
    argparse.ArgumentParser.parse_args = stop
    try:
        try:
            cli.main([])
        except SystemExit:
            pass
    finally:
        argparse.ArgumentParser.parse_args = orig
    sub = next(a for a in got["p"]._actions if isinstance(a, argparse._SubParsersAction))
    return {name: {o for act in sp._actions for o in act.option_strings} for name, sp in sub.choices.items()}


def problems(text: str, subs: dict) -> list[str]:
    out = []
    for m in re.finditer(r"(?<![\w-])bg ([a-z][a-z-]+)((?:[^`\n|]*))", text):
        name, rest = m.group(1), m.group(2)
        if name in ("skills",):  # 「bg-skills」などの語は対象外
            continue
        if name not in subs:
            out.append(f"bg {name}：サブコマンドが無い")
            continue
        for flag in re.findall(r"(?<![\w-])(--[a-z][a-z-]*)", rest):
            if flag not in subs[name]:
                out.append(f"bg {name} {flag}：引数が無い")
    return out


def test_AC_082_1_examples_match_cli():
    subs = _parsers()
    bad = {str(p.relative_to(ROOT)): problems(p.read_text(encoding="utf-8"), subs) for p in DOCS if p.exists()}
    bad = {k: v for k, v in bad.items() if v}
    assert not bad, bad


def test_AC_082_2_unknown_flag_is_reported():
    subs = _parsers()
    assert problems("`bg league x.yaml --nosuch 1`", subs) == ["bg league --nosuch：引数が無い"]
    assert problems("`bg compare a.yaml --record e.jsonl`", subs) == []
