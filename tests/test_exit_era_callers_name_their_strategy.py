"""Every caller of the exit-rule lookup names the strategy it is pricing (2026-09-22).

Since the 2026-09-06 per-strategy flip (#545) a date alone no longer names an exit bracket:
`exit_rules_as_of(d)` / `exit_era_label(d)` without a `signal_type` return the GLOBAL stack, which
MAGNA53 left that day. Two shadow lanes that exist to price declined MAGNA53 candidates under
"the CURRENT-era MAGNA53 bracket" (their own words) kept calling without one and walked 95
rows (85 settled; 37 sustain-reject, 58 gap-near-miss) under the retired +2R-partial stack for two
weeks — nothing failed, the rows were
simply priced under a rule nobody trades.

The population is DERIVED (an AST walk over every production package), never hand-listed, so a
new caller is covered the day it is written.
"""
from __future__ import annotations

import ast
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
PACKAGES = ("agents", "shared", "broker", "channels", "core", "scripts")
LOOKUPS = {"exit_rules_as_of", "exit_era_label"}


def _lookup_calls() -> list[tuple[str, int, ast.Call]]:
    found = []
    for pkg in PACKAGES:
        root = REPO / pkg
        if not root.is_dir():
            continue
        for path in sorted(root.rglob("*.py")):
            tree = ast.parse(path.read_text(), filename=str(path))
            for node in ast.walk(tree):
                if not isinstance(node, ast.Call):
                    continue
                fn = node.func
                name = fn.attr if isinstance(fn, ast.Attribute) else getattr(fn, "id", None)
                if name in LOOKUPS:
                    found.append((str(path.relative_to(REPO)), node.lineno, node))
    return found


def _names_strategy(call: ast.Call) -> bool:
    return len(call.args) >= 2 or any(k.arg == "signal_type" for k in call.keywords)


def test_the_population_is_real():
    """Name the members rather than floor the count — a floor cannot catch a walk that goes
    blind to a package (the 09-20 lesson)."""
    files = {f for f, _, _ in _lookup_calls()}
    for must in ("agents/market_intelligence/gap_near_miss_replay.py",
                 "agents/market_intelligence/sustain_reject_replay.py",
                 "agents/market_intelligence/lowcap_lane_replay.py",
                 "agents/market_intelligence/system_review.py"):
        assert must in files, f"the AST walk no longer sees {must}"


def test_every_exit_rule_lookup_names_its_strategy():
    bare = [f"{f}:{ln}" for f, ln, call in _lookup_calls() if not _names_strategy(call)]
    assert not bare, (
        "exit-rule lookup without a signal_type — since 2026-09-06 that silently returns the "
        "GLOBAL stack, not the bracket the strategy trades:\n  " + "\n  ".join(bare))


def test_the_magna53_lanes_price_under_magna53s_current_bracket():
    """Behavioural half: a post-flip walk in all three MAGNA53 lanes is stamped era_d with the
    +8R partial. The low-cap lane included — operator 2026-09-22: it is a lane of MAGNA53, so it
    prices under MAGNA53's bracket, not its own registry row's (which the 09-06 flip left alone)."""
    from datetime import date
    from agents.market_intelligence import rule_eras
    d = date(2026, 9, 22)
    assert rule_eras.exit_era_label(d, "magna53") == "era_d"
    assert rule_eras.exit_rules_as_of(d, "magna53")["intraday_partial_r"] == 8.0
    lanes = {"agents/market_intelligence/gap_near_miss_replay.py",
             "agents/market_intelligence/sustain_reject_replay.py",
             "agents/market_intelligence/lowcap_lane_replay.py"}
    seen = {}
    for f, ln, call in _lookup_calls():
        if f in lanes:
            arg = call.args[1] if len(call.args) >= 2 else None
            seen.setdefault(f, []).append(getattr(arg, "value", None))
    assert set(seen) == lanes
    assert all(v == ["magna53", "magna53"] for v in seen.values()), seen


def _walk_arm_calls() -> list[tuple[str, int, ast.Call]]:
    found = []
    for pkg in PACKAGES:
        root = REPO / pkg
        if not root.is_dir():
            continue
        for path in sorted(root.rglob("*.py")):
            for node in ast.walk(ast.parse(path.read_text(), filename=str(path))):
                if isinstance(node, ast.Call) and getattr(node.func, "id", getattr(node.func, "attr", None)) == "walk_arm":
                    found.append((str(path.relative_to(REPO)), node.lineno, node))
    return found


def test_every_walk_passes_the_stamped_rules_breakeven_arm():
    """A stamp is only true if the walk reads the same stack. Until 2026-09-22 the three lanes
    stamped their rows from `exit_rules_as_of` but never passed its `breakeven_at_r` to the
    walker (and pinned the partial at a +2R constant), so an era D stamp would have sat on an
    era C walk. Derived over every production `walk_arm` call, named below so the walk cannot
    silently go blind."""
    calls = _walk_arm_calls()
    files = {f for f, _, _ in calls}
    assert {"agents/market_intelligence/live_fill_counterfactuals.py",
            "agents/market_intelligence/gap_near_miss_replay.py",
            "agents/market_intelligence/sustain_reject_replay.py",
            "agents/market_intelligence/lowcap_lane_replay.py"} <= files
    missing = [f"{f}:{ln}" for f, ln, c in calls
               if not any(k.arg == "breakeven_at_r" for k in c.keywords)]
    assert not missing, "walk_arm without breakeven_at_r:\n  " + "\n  ".join(missing)
    # ...and the partial level comes from the stack too: no lane reads a +2R constant any more,
    # and every lane's pinned_target call takes the stack's partial_r.
    for f in ("gap_near_miss_replay.py", "sustain_reject_replay.py", "lowcap_lane_replay.py"):
        tree = ast.parse((REPO / "agents/market_intelligence" / f).read_text())
        names = {n.id for n in ast.walk(tree) if isinstance(n, ast.Name)}
        assert "TARGET_R" not in names, f
        pins = [n for n in ast.walk(tree) if isinstance(n, ast.Call)
                and getattr(n.func, "id", None) == "pinned_target"]
        assert pins and all(getattr(n.args[2], "id", None) == "partial_r" for n in pins), f
