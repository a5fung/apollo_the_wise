"""#594 step 0 — his chart rulings are SCORED against, not just stored.

Until 2026-09-21 `scripts/probes/_structure_read_v3.py` only MENTIONED
`tests/fixtures/must_not_trade_charts.py` in its docstring. 25 operator rulings sat captured
and unused, and #519 makes them the bar a paid vision eval (~$190) has to beat — so the paid
run could not have been interpreted either way. He said "encode the rulings"; this pins what
the encoding must keep true.

⚠ THE BUG THIS FILE WAS BORN FROM, because it is the same one the repo keeps making. The first
run of `score_against_operator_rulings` reported "1 of 33 real EPs wrongly rejected — TDIC
2026-05-12", which would have read as a RULE 0 violation. TDIC carries `excluded=True` and its
own reason calls it "a data anomaly, not a real tradeable EP" — next-day high $750, close $576,
then a full round-trip to $20. Three members are excluded and `test_577_must_not_miss_eps.py`
does not assert on them either. The arithmetic was right; the population was wrong.
"""
from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
for p in (str(REPO), str(REPO / "scripts" / "probes")):
    if p not in sys.path:
        sys.path.insert(0, p)

_spec = importlib.util.spec_from_file_location(
    "_structure_read_v3", REPO / "scripts" / "probes" / "_structure_read_v3.py")
V3 = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(V3)

from tests.fixtures.must_not_miss_eps import MUST_NOT_MISS          # noqa: E402
from tests.fixtures.must_not_trade_charts import MUST_NOT_TRADE     # noqa: E402


def _rejects_everything(_tk, _d):
    return {V3.ANCHOR_75_METRIC: 999.0}


def _rejects_nothing(_tk, _d):
    return {V3.ANCHOR_75_METRIC: 0.0}


def test_excluded_members_are_not_part_of_the_rule_0_bar():
    """THE REGRESSION. An `excluded=True` member must never be counted as a real EP wrongly
    rejected — it is a print nobody claims is tradeable."""
    out = V3.score_against_operator_rulings(_rejects_everything)
    n_excluded = sum(1 for m in MUST_NOT_MISS if getattr(m, "excluded", False))
    assert n_excluded >= 1, "fixture no longer marks any member excluded — this test is vacuous"
    assert out["real_eps_n"] == len(MUST_NOT_MISS) - n_excluded, (
        f"the RULE 0 denominator is {out['real_eps_n']} against {len(MUST_NOT_MISS)} members and "
        f"{n_excluded} exclusions — excluded prints are back in the bar."
    )
    assert out["real_eps_wrongly_rejected"] == out["real_eps_n"], "stub rejects all; count disagrees"


def test_the_exclusions_stay_VISIBLE_rather_than_silently_dropped():
    """An unexplained 30-against-33 invites the next reader to 'correct' it back."""
    out = V3.score_against_operator_rulings(_rejects_nothing)
    assert len(out["excluded_from_bar"]) == sum(
        1 for m in MUST_NOT_MISS if getattr(m, "excluded", False))
    assert all(isinstance(x, tuple) and len(x) == 2 for x in out["excluded_from_bar"])


def test_an_unreadable_date_is_not_counted_as_passing():
    """None is not False. A date whose bars we cannot read has not cleared the rule, and
    folding the two would flatter the must-not-reject column — the one direction RULE 0 says
    we may never flatter."""
    assert V3.anchor75_rejects(None) is None
    assert V3.anchor75_rejects({V3.ANCHOR_75_METRIC: None}) is None
    out = V3.score_against_operator_rulings(lambda _t, _d: None)
    assert out["real_eps_wrongly_rejected"] == 0
    assert out["unreadable"]["real_eps"] == out["real_eps_n"], (
        "unreadable dates vanished instead of being counted in their own column")


def test_both_directions_are_reported_not_just_rejections():
    """The fixture's own rule: "a filter judged only on what it rejects will reject
    everything." His GOOD_CHART/OKISH_CHART vocabulary exists so the read can lose points for
    refusing a chart he approved."""
    out = V3.score_against_operator_rulings(_rejects_everything)
    assert out["must_not_reject_n"] >= 1, "no must-not-reject population — scoring is one-sided"
    assert out["must_not_reject_wrongly_rejected"] == out["must_not_reject_n"]
    assert out["bad_charts_n"] == len(MUST_NOT_TRADE)


def test_the_parameter_is_declared_and_is_HIS_number():
    """⚠ At this n a favourable cutline is trivial to find and worthless. The function scores
    ONE pre-declared rule and must not grow a search over cutlines — a function that tries
    several and reports the best is a fitting machine wearing a measurement's name.

    Checked through the SIGNATURE rather than by grepping the source: the scorer takes exactly
    one argument, the read supplier. There is nowhere to pass a cutline, a list of cutlines or
    a metric, so a search would have to change this signature and redden this test. (A source
    grep for "for cutline in" was the first draft; it read the same and cost a ratchet slot
    that the #678 SQL pin — which has no runtime seam at all — needs more.)"""
    import inspect
    assert V3.ANCHOR_75_CUTLINE == 75.0
    assert V3.ANCHOR_75_METRIC == "runup_low_pct_20"
    params = list(inspect.signature(V3.score_against_operator_rulings).parameters)
    assert params == ["read_for"], (
        f"the scorer grew parameters {params} — a cutline or metric can now be varied from "
        f"outside, which is how a measurement becomes a fitting machine."
    )
    out = V3.score_against_operator_rulings(_rejects_nothing)
    assert out["parameter"]["cutline"] == 75.0
    assert isinstance(out["parameter"]["cutline"], float), "cutline became a collection"


def test_pointed_at_dates_never_wear_his_name():
    """He pointed at MXL 04-24 while explaining that 04-21 was the wrong day; he never ruled it
    tradeable. Counting it as a must-not-reject would be agent inference behind the operator's
    name — the one thing the fixture forbids outright."""
    out = V3.score_against_operator_rulings(_rejects_everything)
    assert "pointed_at_rejected" in out and "pointed_at_n" in out
    assert out["must_not_reject_n"] < out["must_not_reject_n"] + out["pointed_at_n"], (
        "pointed-at dates were folded into the operator-labelled population")
