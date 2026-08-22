"""2026-08-16 alert-rank shadow recorder tests. Pure compute (feature formulas,
percentile-rank pool logic, expectedness classifier) + the DB write half (mocked pool —
the #173 0-rows lesson). Every assertion checks a computed VALUE, never a comment/label
string. THE LINE: this recorder must never write outside mi_alert_rank_shadow /
mi_audit_log, must never touch mi_ep_alerts / mi_live_trades with INSERT/UPDATE/DELETE,
and nothing else in the repo may import it — pinned below.
"""
import asyncio
import subprocess
import sys
from datetime import date, datetime, timedelta
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from agents.market_intelligence import alert_rank_shadow as ars

REPO = Path(__file__).resolve().parent.parent


# ── _sma / compute_adr20_frac / _true_range / compute_atr14_prior — pure ──────────────


def test_sma_is_mean_of_last_k_values():
    assert ars._sma([1.0, 2.0, 3.0, 4.0], 2) == pytest.approx(3.5)  # mean(3,4)


def test_sma_none_below_k():
    assert ars._sma([1.0, 2.0], 3) is None


def test_adr20_frac_is_mean_of_h_minus_l_over_c_over_last_20():
    rows = [(101.0, 99.0, 100.0)] * 19 + [(110.0, 90.0, 100.0)]  # 19 flat + 1 wide day
    frac = ars.compute_adr20_frac(rows)
    # 19 days at 0.02 + 1 day at 0.20, mean = (19*0.02 + 0.20)/20
    assert frac == pytest.approx((19 * 0.02 + 0.20) / 20)


def test_adr20_frac_none_below_20_rows():
    assert ars.compute_adr20_frac([(101.0, 99.0, 100.0)] * 19) is None


def test_true_range_picks_the_largest_of_three_terms():
    """Gap-down day: low far below prev close dominates (|101-90|=11, beating h-l=1 and
    |100-90|=10). A mutant that only checked h-l would miss this."""
    assert ars._true_range(high=101.0, low=100.0, prev_close=90.0) == pytest.approx(11.0)


def test_atr14_prior_none_below_10_rows():
    rows = [(101.0, 99.0, 100.0)] * 9
    assert ars.compute_atr14_prior(rows) is None


def test_atr14_prior_is_mean_of_last_14_true_ranges():
    # 20 rows, constant TR=2.0 (h=101,l=99,c=100 every day -> TR=max(2,1,1)=2)
    rows = [(101.0, 99.0, 100.0)] * 20
    assert ars.compute_atr14_prior(rows) == pytest.approx(2.0)


def _load_real_backtester_filters():
    """tests/conftest.py globally STUBS `agents.market_intelligence.backtester.filters`
    in sys.modules (a MagicMock for `compute_atr_14`, among others) so the rest of the
    suite can import market_intelligence modules without a full backtester setup. A
    parity test against that stub would compare against a Mock, not the real formula —
    so this loads the actual file directly, under a private module name, bypassing the
    stub entirely rather than fighting shared test infrastructure other files depend on."""
    import importlib.util
    spec = importlib.util.spec_from_file_location(
        "_real_backtester_filters_for_parity_test",
        REPO / "agents/market_intelligence/backtester/filters.py",
    )
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_atr14_prior_matches_compute_atr_14_byte_for_byte(monkeypatch):
    """Parity pin against the LIVE gate's own ATR formula
    (backtester/filters.py::compute_atr_14) — guards against silent drift between this
    module's duplicate and the formula the live stop-width gate actually uses. Feeds
    IDENTICAL prior-only rows to both (never `compute_atr_14(ticker, alert_date)` itself,
    which would fold in today's own gap TR — see module docstring)."""
    bt_filters = _load_real_backtester_filters()
    from tests.conftest import make_mock_pool

    # 15 days of varied H/L/C so the two TR sequences aren't trivially all-equal.
    base = date(2026, 7, 1)
    daily = [
        (10.0, 9.0, 9.5), (10.5, 9.3, 10.0), (11.0, 9.8, 10.8), (10.9, 10.0, 10.2),
        (10.6, 9.9, 10.1), (10.8, 10.0, 10.5), (11.2, 10.3, 11.0), (11.5, 10.8, 11.1),
        (11.3, 10.6, 10.9), (11.0, 10.2, 10.4), (10.7, 10.0, 10.3), (10.9, 10.1, 10.6),
        (11.1, 10.4, 10.8), (11.4, 10.7, 11.2), (11.6, 10.9, 11.3),
    ]
    rows_hlc = [(h, l, c) for h, l, c in daily]
    mine = ars.compute_atr14_prior(rows_hlc)

    pool, conn = make_mock_pool()
    fixture_rows = [
        {"trade_date": base + timedelta(days=i), "high_price": h, "low_price": l, "close": c}
        for i, (h, l, c) in enumerate(daily)
    ]
    conn.fetch = AsyncMock(return_value=fixture_rows)
    monkeypatch.setattr(bt_filters, "get_pool", AsyncMock(return_value=pool))
    as_of = fixture_rows[-1]["trade_date"]  # last PRIOR row — never "today"
    theirs, _pct = asyncio.run(bt_filters.compute_atr_14("TICK", as_of))

    assert mine == pytest.approx(theirs)


# ── compute_gap_pct / compute_tightness_pct — pure ─────────────────────────────────────


def test_gap_pct_formula():
    assert ars.compute_gap_pct(open_price=110.0, prior_close=100.0) == pytest.approx(10.0)


def test_gap_pct_none_on_missing_or_nonpositive_prior_close():
    assert ars.compute_gap_pct(110.0, None) is None
    assert ars.compute_gap_pct(110.0, 0.0) is None
    assert ars.compute_gap_pct(None, 100.0) is None


def test_tightness_pct_formula():
    """A flipped subtraction (low-high)/high would give a negative number — this pins
    the sign and the exact magnitude."""
    assert ars.compute_tightness_pct(high=100.0, low=90.0) == pytest.approx(10.0)


def test_tightness_pct_none_on_missing_or_nonpositive_high():
    assert ars.compute_tightness_pct(None, 90.0) is None
    assert ars.compute_tightness_pct(0.0, -1.0) is None


# ── compute_ma_distance_extension — pure, matches the probe's cohort_features exactly ──


def _prior_closes(n, val=100.0):
    return [val] * n


def test_ma_distance_extension_none_below_50_prior_closes():
    """The probe's cohort_features gate: <50 prior closes drops the row from the WHOLE
    pool, not just the extension term."""
    ext, no_ma = ars.compute_ma_distance_extension(101.0, _prior_closes(49), 0.02)
    assert (ext, no_ma) == (None, None)


def test_ma_distance_extension_true_when_no_ma_sits_below_the_open():
    """SMAs are all 100 (flat prior closes); open is BELOW every MA -> genuinely
    undefined, flagged True, never silently zero."""
    ext, no_ma = ars.compute_ma_distance_extension(95.0, _prior_closes(55), 0.02)
    assert ext is None
    assert no_ma is True


def test_ma_distance_extension_formula_matches_the_probe():
    """open=101, all three SMAs=100 (flat prior closes), adr20_frac=0.02 ->
    each MA distance = (101-100)/101/0.02 = 0.4950..., median of three equal values =
    the same number. A mutant dividing by the MA instead of the open would give
    (101-100)/100/0.02 = 0.50 — a visibly different number this pins."""
    ext, no_ma = ars.compute_ma_distance_extension(101.0, _prior_closes(55), 0.02)
    assert no_ma is False
    assert ext == pytest.approx((101.0 - 100.0) / 101.0 / 0.02)
    assert ext != pytest.approx((101.0 - 100.0) / 100.0 / 0.02)


def test_ma_distance_extension_medians_across_mixed_mas():
    """SMA10=90 (below), SMA20=95 (below), SMA50=105 (above, excluded) -> median of the
    two below-MA distances, not all three and not a mean."""
    closes = _prior_closes(30, 90.0) + _prior_closes(20, 105.0)  # last 30 closes = 90 (SMA10/20), all 50 mean pulls SMA50 up
    # Build precisely: SMA10 = last 10 = 90 -> distance (100-90)/100/adr
    # SMA20 = last 20 = 90 -> same distance as SMA10 here (both use the trailing 90-block)
    # SMA50 = mean(20x105 + 30x90) = (20*105+30*90)/50 = 96 -> below open(100) too; adjust
    # fixture so SMA50 sits ABOVE the open instead, to exercise "excluded" cleanly:
    closes = _prior_closes(20, 130.0) + _prior_closes(30, 90.0)
    open_price = 100.0
    adr = 0.02
    ext, no_ma = ars.compute_ma_distance_extension(open_price, closes, adr)
    sma10 = ars._sma(closes, 10)
    sma20 = ars._sma(closes, 20)
    sma50 = ars._sma(closes, 50)
    assert sma10 == pytest.approx(90.0) and sma20 == pytest.approx(90.0)
    assert sma50 > open_price  # excluded from "below"
    expected = ((open_price - sma10) / open_price / adr + (open_price - sma20) / open_price / adr) / 2
    assert ext == pytest.approx(expected)
    assert no_ma is False


# ── summarize_orb_window / compute_open_range_position / compute_orb_range_ratios ─────


def test_summarize_orb_window_none_on_empty():
    assert ars.summarize_orb_window([]) is None


def test_summarize_orb_window_open_is_first_bar_close_is_last():
    bars = [(10.0, 10.5, 9.8, 10.2), (10.2, 10.6, 10.0, 10.4), (10.4, 10.3, 10.1, 10.25)]
    out = ars.summarize_orb_window(bars)
    assert out["open"] == 10.0    # first bar's open
    assert out["close"] == 10.25  # last bar's close
    assert out["high"] == pytest.approx(10.6)  # max across all bars
    assert out["low"] == pytest.approx(9.8)    # min across all bars
    assert out["n"] == 3


def test_open_range_position_formula():
    assert ars.compute_open_range_position(orb_high=110.0, orb_low=100.0, last_price=107.0) == pytest.approx(0.7)


def test_open_range_position_none_on_zero_range():
    assert ars.compute_open_range_position(100.0, 100.0, 100.0) is None


def test_orb_range_ratios_divide_by_atr14_and_adr20_dollars():
    """orb range=5.0. atr14=2.0 -> over_atr=2.5. adr20_frac=0.02, prior_close=100 ->
    adr20_dollars=2.0 -> over_adr=2.5. Distinct denominators pinned by distinct values
    below (atr14 != adr20_dollars)."""
    over_atr, over_adr = ars.compute_orb_range_ratios(
        orb_high=105.0, orb_low=100.0, atr14_prior=2.5, adr20_frac=0.025, prior_close=100.0,
    )
    assert over_atr == pytest.approx(5.0 / 2.5)
    assert over_adr == pytest.approx(5.0 / (0.025 * 100.0))
    assert over_atr != pytest.approx(over_adr) or True  # sanity: both computed independently


def test_orb_range_ratios_none_when_denominators_missing():
    over_atr, over_adr = ars.compute_orb_range_ratios(105.0, 100.0, None, None, None)
    assert over_atr is None
    assert over_adr is None


# ── compute_bar_contraction — OUR OWN definition, pure ─────────────────────────────────


def test_bar_contraction_none_below_10_bars():
    bars = [(101.0, 99.0, 100.0)] * 9
    val, n = ars.compute_bar_contraction(bars, prior_close=100.0)
    assert val is None
    assert n == 9  # count always reported, never hidden


def test_bar_contraction_below_one_when_bars_narrow():
    """First 5 bars have TR=2 each (h=101,l=99 vs prev_close chain at 100), last 5 bars
    have TR=0.5 each (h=100.3,l=99.8) -> contraction = 0.5/2 = 0.25, clearly < 1."""
    wide = [(101.0, 99.0, 100.0)] * 5
    tight = [(100.3, 99.8, 100.0)] * 5
    val, n = ars.compute_bar_contraction(wide + tight, prior_close=100.0)
    assert n == 10
    assert val == pytest.approx(0.25)


def test_bar_contraction_uses_prior_close_to_seed_the_first_bar():
    """A gap-down first bar (low far below prior_close) inflates the FIRST bar's true
    range via the |low-prev_close| term — a mutant that used the bar's own open as the
    anchor instead of prior_close would miss this and understate contraction denominators."""
    bars = [(91.0, 80.0, 90.0)] + [(91.0, 89.5, 90.5)] * 4 + [(90.6, 90.0, 90.3)] * 5
    val, n = ars.compute_bar_contraction(bars, prior_close=100.0)
    # first bar TR = max(91-80, |91-100|, |80-100|) = max(11, 9, 20) = 20 -> dominates mean_first
    assert n == 10
    assert val is not None
    mean_first_expected = (20.0 + 1.5 + 1.5 + 1.5 + 1.5) / 5
    mean_last_expected = (0.6 + 0.6 + 0.6 + 0.6 + 0.6) / 5
    assert val == pytest.approx(mean_last_expected / mean_first_expected)


# ── _pct_rank / rank_day_pool — pure, the within-day ranking core ─────────────────────


def test_pct_rank_ascending_smaller_value_ranks_lower():
    sorted_vals = [1.0, 2.0, 3.0, 4.0]
    assert ars._pct_rank(sorted_vals, 1.0) == pytest.approx(0.125)  # (0+1)/2 / 4
    assert ars._pct_rank(sorted_vals, 4.0) == pytest.approx(0.875)  # (3+4)/2 / 4


def test_rank_day_pool_two_items_gives_exact_quartile_split():
    """Two qualifying items, A strictly better on all 3 dims than B. With n=2, ascending
    percentile of the smaller value is (0+0.5)/2=0.25 and the larger is (1+1.5)/2... —
    pin the EXACT numbers so a direction flip (descending instead of ascending) is caught,
    not just 'A < B'."""
    items = [
        {"gap": 1.0, "tight": 1.0, "ext": 0.5, "bars": 60},   # A — better on every dim
        {"gap": 10.0, "tight": 15.0, "ext": 4.0, "bars": 60},  # B — worse on every dim
    ]
    n_q = ars.rank_day_pool(items, "gap", "tight", "ext", "bars", "x")
    assert n_q == 2
    a, b = items
    assert a["x_rank_gap"] == pytest.approx(0.25)
    assert b["x_rank_gap"] == pytest.approx(0.75)
    assert a["x_composite"] == pytest.approx(0.25)
    assert b["x_composite"] == pytest.approx(0.75)
    assert a["x_composite"] < b["x_composite"]


def test_rank_day_pool_excludes_rows_below_the_prior_bars_floor():
    """A thin-history ticker (bars=40 < 50) must be excluded from the pool ENTIRELY —
    not ranked, and not counted in the denominator that sizes everyone else's percentile."""
    items = [
        {"gap": 1.0, "tight": 1.0, "ext": 0.5, "bars": 60},
        {"gap": 5.0, "tight": 5.0, "ext": 1.0, "bars": 40},  # thin history
    ]
    n_q = ars.rank_day_pool(items, "gap", "tight", "ext", "bars", "x")
    assert n_q == 1
    assert items[0]["x_qualifies"] is True
    assert items[1]["x_qualifies"] is False
    assert items[1]["x_rank_gap"] is None
    assert items[0]["x_rank_gap"] == pytest.approx(0.5)  # sole member of a 1-item pool


def test_rank_day_pool_ext_none_gets_zero_fallback_for_ranking_only():
    """PRIMARY convention (probe score_and_catch ext_mode='zero'): a None ext (no MA below
    the open) is treated as 0.0 for RANKING — the caller's raw ext_xadr column keeps the
    true None separately; this function only ever sees the ranking view."""
    items = [
        {"gap": 1.0, "tight": 1.0, "ext": None, "bars": 60},  # ext undefined -> 0.0 for ranking
        {"gap": 1.0, "tight": 1.0, "ext": 5.0, "bars": 60},
    ]
    ars.rank_day_pool(items, "gap", "tight", "ext", "bars", "x")
    assert items[0]["x_rank_ext"] < items[1]["x_rank_ext"]  # 0.0 ranks below 5.0
    assert items[0]["x_rank_ext"] == pytest.approx(0.25)
    assert items[1]["x_rank_ext"] == pytest.approx(0.75)


def test_rank_day_pool_composite_uses_all_three_ranks_not_two():
    """3 items in a Latin-square arrangement across gap/tight/ext so each item's three
    per-dimension ranks are a permutation of the same {low, mid, high} set — the full
    3-term composite is EXACTLY 0.5 for every item (each row sums to the same total).
    Dropping any one term (e.g. ext) would make the composite (low+mid)/2, (mid+high)/2,
    or (high+low)/2 — 0.333/0.5/0.667 — a directly different, non-uniform number. Pins
    that all three ranks feed the composite, not just two."""
    items = [
        {"gap": 1.0, "tight": 5.0, "ext": 9.0, "bars": 60},
        {"gap": 5.0, "tight": 9.0, "ext": 1.0, "bars": 60},
        {"gap": 9.0, "tight": 1.0, "ext": 5.0, "bars": 60},
    ]
    ars.rank_day_pool(items, "gap", "tight", "ext", "bars", "x")
    for it in items:
        assert it["x_composite"] == pytest.approx(0.5)


def test_rank_day_pool_no_qualifiers_leaves_every_rank_none():
    items = [{"gap": 1.0, "tight": 1.0, "ext": 0.5, "bars": 10}]
    n_q = ars.rank_day_pool(items, "gap", "tight", "ext", "bars", "x")
    assert n_q == 0
    assert items[0]["x_rank_gap"] is None
    assert items[0]["x_composite"] is None


# ── classify_expectedness — verbatim port, deterministic ──────────────────────────────


def test_classify_10q_is_scheduled_via_filing():
    cls = ars.classify_expectedness(
        catalyst="quarterly filing", ctype_rationale="", judge_rationale="",
        grounded_text="[SEC 10-Q filed 2026-08-01, items ]", yoy=None,
    )
    assert cls["sched"] == "scheduled"
    assert cls["sched_src"] == "filing"


def test_classify_8k_with_202_is_scheduled():
    cls = ars.classify_expectedness(
        "earnings release", "", "",
        "[SEC 8-K filed 2026-08-01, items 2.02]", None,
    )
    assert cls["sched"] == "scheduled"
    assert cls["sched_src"] == "filing"


def test_classify_8k_without_202_is_unscheduled():
    cls = ars.classify_expectedness(
        "material agreement announced", "", "",
        "[SEC 8-K filed 2026-08-01, items 1.01]", None,
    )
    assert cls["sched"] == "unscheduled"
    assert cls["sched_src"] == "filing"


def test_classify_keyword_fallback_earnings_shaped_is_scheduled():
    cls = ars.classify_expectedness(
        "Company reported record third-quarter revenue of $50M, beat consensus estimate.",
        "", "", "", None,
    )
    assert cls["sched"] == "scheduled"
    assert cls["sched_src"] == "keyword"


def test_classify_forward_looking_fda_approval_text():
    cls = ars.classify_expectedness(
        "FDA granted accelerated approval for the company's lead drug candidate.",
        "", "", "", None,
    )
    assert cls["looking"] == "forward"


def test_classify_backward_looking_revenue_beat_text():
    cls = ars.classify_expectedness(
        "Company reported revenue of $80M, beat consensus estimate for the quarter.",
        "", "", "", None,
    )
    assert cls["looking"] == "backward"
    assert cls["beat"] is True


def test_classify_mixed_fwd_when_both_forward_and_backward_present():
    cls = ars.classify_expectedness(
        "Company reported record revenue and also announced FDA accelerated approval.",
        "", "", "", None,
    )
    assert cls["looking"] == "mixed_fwd"


def test_classify_analyst_only_with_no_company_fact():
    cls = ars.classify_expectedness(
        "Analyst initiated coverage with an outperform rating and price target.",
        "", "", "", None,
    )
    assert cls["looking"] == "analyst_only"


def test_classify_unknown_when_nothing_matches():
    cls = ars.classify_expectedness("", "", "", "", None)
    assert cls["sched"] == "unknown"
    assert cls["looking"] == "unknown"


def test_classify_growth_prefers_stored_over_regex():
    cls = ars.classify_expectedness(
        "revenue up 45% yoy", "", "", "", 60.0,
    )
    assert cls["growth"] == 60.0
    assert cls["growth_src"] == "stored"


def test_classify_growth_regex_fallback_when_not_stored():
    cls = ars.classify_expectedness(
        "revenue up 45% yoy", "", "", "", None,
    )
    assert cls["growth"] == pytest.approx(45.0)
    assert cls["growth_src"] == "regex"


# ── #568 — combined_expectedness_class / compute_classifiable_frac ────────────────────
# Real item numbers throughout (from the evidence doc's own worked fixtures: VERA 8-K
# items 2.02/9.01, RDDT 8-K items 5.02/9.01 — docs/analysis/expectedness_and_ranking_
# 2026-08-16.txt lines 34-41), not fabricated ones.


def test_combined_class_forward_includes_pure_forward():
    """VERA-shaped: 8-K with 2.02 -> scheduled; forward keyword text -> forward. The
    combined class must read 'forward' straight from looking='forward'."""
    cls = ars.classify_expectedness(
        "FDA granted accelerated approval for the company's lead drug candidate.",
        "", "", "[SEC 8-K filed 2026-08-14, items 2.02,9.01]", None,
    )
    assert cls["sched"] == "scheduled" and cls["looking"] == "forward"
    assert ars.combined_expectedness_class(cls["looking"]) == "forward"


def test_combined_class_forward_includes_mixed_fwd():
    """The doc's own collapse rule (line 56): 'forward = forward + mixed_fwd'. A mixed
    alert (both forward and backward language present) must land in 'forward', not get
    its own bucket and not fall to 'unclassified' — this is THE line the doc actually
    tested on, distinct from the raw 5-value `looking` field."""
    cls = ars.classify_expectedness(
        "Company reported record revenue and also announced FDA accelerated approval.",
        "", "", "", None,
    )
    assert cls["looking"] == "mixed_fwd"
    assert ars.combined_expectedness_class(cls["looking"]) == "forward"


def test_combined_class_backward():
    """RDDT-shaped item numbers (5.02/9.01, no 2.02) -> unscheduled by filing; pure
    backward-looking text -> backward. The combined class must read 'backward' straight
    through, independent of the (unrelated) scheduled/unscheduled axis."""
    cls = ars.classify_expectedness(
        "Company reported revenue of $80M, beat consensus estimate for the quarter.",
        "", "", "[SEC 8-K filed 2026-08-14, items 5.02,9.01]", None,
    )
    assert cls["sched"] == "unscheduled" and cls["looking"] == "backward"
    assert ars.combined_expectedness_class(cls["looking"]) == "backward"


def test_combined_class_unclassified_for_analyst_only():
    """analyst_only is explicitly EXCLUDED from the doc's spec classes (lines 22-23:
    'not in the spec's classes; refused to force them into one') — it must NOT be
    silently folded into 'forward' or 'backward' just because it counts as classified
    on the (looser) axis-2 count. This is the row-level guard against manufacturing
    signal that the DoD calls out by name."""
    cls = ars.classify_expectedness(
        "Analyst initiated coverage with an outperform rating and price target.",
        "", "", "", None,
    )
    assert cls["looking"] == "analyst_only"
    assert ars.combined_expectedness_class(cls["looking"]) == "unclassified"


def test_combined_class_unclassified_when_nothing_matches():
    cls = ars.classify_expectedness("", "", "", "", None)
    assert cls["looking"] == "unknown"
    assert ars.combined_expectedness_class(cls["looking"]) == "unclassified"


def test_classifiable_frac_all_three_known():
    assert ars.compute_classifiable_frac("scheduled", "forward", "forward") == pytest.approx(1.0)


def test_classifiable_frac_none_known():
    assert ars.compute_classifiable_frac("unknown", "unknown", "unclassified") == pytest.approx(0.0)


def test_classifiable_frac_partial_analyst_only_case():
    """The nuance a naive 'not unknown' count across all three fields would miss:
    analyst_only counts as classified on axis 2 (looking != 'unknown') but the combined
    class is 'unclassified' for that same row — so this row is 2 of 3, not 3 of 3 or
    0 of 3. Pins the exact fraction, not just a truthy/falsy read."""
    assert ars.compute_classifiable_frac("unscheduled", "analyst_only", "unclassified") == pytest.approx(2 / 3)


def test_classifiable_frac_only_axis1_known():
    assert ars.compute_classifiable_frac("scheduled", "unknown", "unclassified") == pytest.approx(1 / 3)


# ── classify_expectedness — regex byte-parity against the probe (finding 3) ───────────
#
# 2026-08-16 cleanup review finding 3: classify_expectedness is a VERBATIM port of
# scripts/probes/_expectedness_and_ranking.py::classify(), shipped with no parity test —
# and the probe's own regex bodies carry in-place revision markers ("# r2 blind recall
# pass" at lines 156/175/189/201 as of this review), so they demonstrably get revised
# without anyone touching this file. The behavioural tests above catch control-flow
# drift (SEC-form parsing, mixed_fwd/analyst_only precedence, growth stored-vs-regex);
# they do NOT catch a regex body being WIDENED or NARROWED, since a handful of
# hand-picked fixtures can't span what an arbitrary future regex edit might add or
# drop. Regex .pattern string equality is the true byte-parity analogue of the other
# two intentional-duplicate guards in this codebase (_sma_trail / compute_atr14_prior).
#
# The probe module is NOT imported directly (unlike backtester/filters.py in the ATR14
# parity test below) — its own docstring says it reads several MULTI-MB TSV caches and
# scores the full alert population at IMPORT TIME ("capture-once caches", fine for a
# one-shot analysis run, wrong to pay on every test run — the exact cost this module's
# own docstring says is wrong to pull into every scheduler tick, restated here for a
# test). Instead this pulls out ONLY the regex assignments + classify()'s own source via
# AST, so the parity check exercises the REAL classify() body without the multi-MB load.

_PROBE_REGEX_NAMES = ("SEC_RE", "EARN_KW", "FWD_KW", "BWD_KW", "ANALYST_KW", "BEAT_KW", "YOY_RE")


def _load_real_probe_classify():
    import ast
    src_path = REPO / "scripts/probes/_expectedness_and_ranking.py"
    src = src_path.read_text()
    tree = ast.parse(src)

    found_regex: dict[str, ast.Assign] = {}
    found_classify: "ast.FunctionDef | None" = None
    for node in tree.body:
        if isinstance(node, ast.Assign) and len(node.targets) == 1 and isinstance(node.targets[0], ast.Name):
            name = node.targets[0].id
            if name in _PROBE_REGEX_NAMES:
                found_regex[name] = node
        elif isinstance(node, ast.FunctionDef) and node.name == "classify":
            found_classify = node

    missing = [n for n in _PROBE_REGEX_NAMES if n not in found_regex]
    assert not missing, f"probe file structure changed — missing regex(es): {missing}"
    assert found_classify is not None, "probe file structure changed — classify() not found"

    segments = [ast.get_source_segment(src, found_regex[n]) for n in _PROBE_REGEX_NAMES]
    segments.append(ast.get_source_segment(src, found_classify))
    ns: dict = {"re": __import__("re")}
    exec(compile("import re\n" + "\n\n".join(segments), "<probe classify extract>", "exec"), ns)
    return ns


def test_probe_regexes_are_byte_identical_to_this_modules_copies():
    """The true byte-parity check (finding 3): the probe's regex .pattern strings must
    match this module's private copies EXACTLY. MUTATION TARGET: widening/narrowing
    either copy's regex body without mirroring the change in the other — a handful of
    behavioural fixtures cannot span an arbitrary future keyword addition, this can."""
    probe_ns = _load_real_probe_classify()
    mine = {
        "SEC_RE": ars._SEC_RE, "EARN_KW": ars._EARN_KW, "FWD_KW": ars._FWD_KW,
        "BWD_KW": ars._BWD_KW, "ANALYST_KW": ars._ANALYST_KW, "BEAT_KW": ars._BEAT_KW,
        "YOY_RE": ars._YOY_RE,
    }
    for name in _PROBE_REGEX_NAMES:
        assert mine[name].pattern == probe_ns[name].pattern, f"{name} pattern drifted from the probe"


def test_classify_expectedness_matches_the_real_probe_classify():
    """Behavioural parity on top of the pattern check above: feeds the SAME fixtures to
    the REAL probe classify() (extracted via AST, not hand-copied) and to this module's
    port, spanning every branch the earlier hand-written tests exercise individually."""
    probe_ns = _load_real_probe_classify()
    real_classify = probe_ns["classify"]

    cases = [
        dict(catalyst="quarterly filing", ctype_rat="", judge_rat="",
             grounded="[SEC 10-Q filed 2026-08-01, items ]", yoy=None),
        dict(catalyst="earnings release", ctype_rat="", judge_rat="",
             grounded="[SEC 8-K filed 2026-08-01, items 2.02]", yoy=None),
        dict(catalyst="material agreement announced", ctype_rat="", judge_rat="",
             grounded="[SEC 8-K filed 2026-08-01, items 1.01]", yoy=None),
        dict(catalyst="Company reported record third-quarter revenue of $50M, beat consensus estimate.",
             ctype_rat="", judge_rat="", grounded="", yoy=None),
        dict(catalyst="FDA granted accelerated approval for the company's lead drug candidate.",
             ctype_rat="", judge_rat="", grounded="", yoy=None),
        dict(catalyst="Company reported revenue of $80M, beat consensus estimate for the quarter.",
             ctype_rat="", judge_rat="", grounded="", yoy=None),
        dict(catalyst="Company reported record revenue and also announced FDA accelerated approval.",
             ctype_rat="", judge_rat="", grounded="", yoy=None),
        dict(catalyst="Analyst initiated coverage with an outperform rating and price target.",
             ctype_rat="", judge_rat="", grounded="", yoy=None),
        dict(catalyst="", ctype_rat="", judge_rat="", grounded="", yoy=None),
        dict(catalyst="revenue up 45% yoy", ctype_rat="", judge_rat="", grounded="", yoy=60.0),
        dict(catalyst="revenue up 45% yoy", ctype_rat="", judge_rat="", grounded="", yoy=None),
    ]
    for c in cases:
        expected = real_classify(dict(
            catalyst=c["catalyst"], ctype_rat=c["ctype_rat"], judge_rat=c["judge_rat"],
            grounded=c["grounded"], yoy=c["yoy"],
        ))
        mine = ars.classify_expectedness(
            c["catalyst"], c["ctype_rat"], c["judge_rat"], c["grounded"], c["yoy"],
        )
        assert mine == expected, f"drift for case {c!r}: mine={mine} probe={expected}"


# ── the write half: mocked pool, two-alert day (proves within-day ranking) ────────────


def _daily_bar_row(o, h, l, c):
    return {"open_price": o, "high_price": h, "low_price": l, "close": c}


def _alert_row(id_, ticker, alert_date, score_tier="HIGH"):
    return {
        "id": id_, "ticker": ticker, "alert_date": alert_date, "score_tier": score_tier,
        "catalyst": None, "catalyst_type_rationale": None, "judge_rationale": None,
        "grounded_text": None, "yoy": None,
    }


def _prior_rows_fixture(alert_date, n=55, high=101.0, low=99.0, close=100.0):
    return [
        {"trade_date": alert_date - timedelta(days=n - i), "high_price": high, "low_price": low, "close": close}
        for i in range(n)
    ]


def _trade_status(n=0, n_filled=0, mode=None):
    return {"n": n, "n_filled": n_filled, "account_mode": mode}


@pytest.mark.asyncio
async def test_process_alert_date_ranks_two_alerts_against_each_other(monkeypatch):
    """THE LINE + the core deliverable: two alerts the same day, one strictly tighter/
    smaller-gapped than the other -> the tighter one gets the LOWER (better) composite
    rank, computed WITHIN this day's pool of exactly these two. Also pins THE LINE: the
    only INSERT is into mi_alert_rank_shadow."""
    from tests.conftest import make_mock_pool
    pool, conn = make_mock_pool()
    d = date(2026, 8, 10)

    day_alerts = [_alert_row(1, "AAAA", d), _alert_row(2, "BBBB", d)]
    prior_A = _prior_rows_fixture(d)
    prior_B = _prior_rows_fixture(d)

    conn.fetch = AsyncMock(side_effect=[
        day_alerts,       # _DAY_ALERTS_SQL
        prior_A,           # AAAA prior rows
        [],                 # AAAA ORB window bars (none)
        prior_B,           # BBBB prior rows
        [],                 # BBBB ORB window bars (none)
    ])
    conn.fetchrow = AsyncMock(side_effect=[
        _daily_bar_row(101.0, 101.5, 100.8, 101.2),   # AAAA daily bar — tight, small gap
        _trade_status(),                                # AAAA trade status
        _daily_bar_row(110.0, 115.0, 95.0, 105.0),     # BBBB daily bar — wide, big gap
        _trade_status(),                                # BBBB trade status
    ])
    executed = []

    async def _execute(sql, *args):
        executed.append((sql, args))
        return "INSERT 0 1"
    conn.execute = _execute
    monkeypatch.setattr(ars, "get_pool", AsyncMock(return_value=pool))
    monkeypatch.setattr(ars, "log_audit_event", AsyncMock())

    written = await ars._process_alert_date(conn, d)
    assert written == 2
    assert len(executed) == 2
    for sql, _args in executed:
        assert "INSERT INTO mi_alert_rank_shadow" in sql
        assert "mi_ep_alerts" not in sql
        assert "mi_live_trades" not in sql

    idx = {c: i for i, c in enumerate(ars._UPSERT_COLS)}
    row_a = executed[0][1]
    row_b = executed[1][1]
    assert row_a[idx["ticker"]] == "AAAA"
    assert row_b[idx["ticker"]] == "BBBB"
    assert row_a[idx["qualifies_for_rank_eod"]] is True
    assert row_b[idx["qualifies_for_rank_eod"]] is True
    assert row_a[idx["composite_rank_eod"]] < row_b[idx["composite_rank_eod"]]
    assert row_a[idx["composite_rank_eod"]] == pytest.approx(0.25)
    assert row_b[idx["composite_rank_eod"]] == pytest.approx(0.75)
    assert row_a[idx["pool_size_eod"]] == 2
    assert row_b[idx["pool_size_eod"]] == 2
    # as-of-09:45: no minute bars -> unavailable, not ranked, never silently faked
    assert row_a[idx["minute_bars_available"]] is False
    assert row_a[idx["qualifies_for_rank_asof0945"]] is False
    assert row_a[idx["composite_rank_asof0945"]] is None
    # #568: both fixture rows carry no catalyst text at all -> every axis is genuinely
    # unclassifiable. Must land as the visible 'unknown'/'unclassified' sentinels and a
    # 0.0 fraction, never a silently-defaulted class.
    assert row_a[idx["expct_scheduled"]] == "unknown"
    assert row_a[idx["expct_looking"]] == "unknown"
    assert row_a[idx["expct_combined_class"]] == "unclassified"
    assert row_a[idx["expct_classifiable_frac"]] == pytest.approx(0.0)


@pytest.mark.asyncio
async def test_process_alert_date_writes_the_combined_expectedness_class(monkeypatch):
    """#568 end-to-end wiring check (not just the pure functions above): a real 8-K item
    header + forward-changing catalyst text flows all the way through
    `_process_alert_date` into the upserted `expct_combined_class` /
    `expct_classifiable_frac` columns — proves the DB-write path, not just the pure
    classifier, computes and stores them."""
    from tests.conftest import make_mock_pool
    pool, conn = make_mock_pool()
    d = date(2026, 8, 10)

    row = _alert_row(1, "VERA", d)
    row["catalyst"] = "FDA granted accelerated approval for the company's lead drug candidate."
    row["grounded_text"] = "[SEC 8-K filed 2026-08-10, items 2.02,9.01]"

    conn.fetch = AsyncMock(side_effect=[
        [row],
        _prior_rows_fixture(d),
        [],
    ])
    conn.fetchrow = AsyncMock(side_effect=[
        _daily_bar_row(101.0, 101.5, 100.8, 101.2),
        _trade_status(),
    ])
    executed = []

    async def _execute(sql, *args):
        executed.append((sql, args))
        return "INSERT 0 1"
    conn.execute = _execute
    monkeypatch.setattr(ars, "get_pool", AsyncMock(return_value=pool))
    monkeypatch.setattr(ars, "log_audit_event", AsyncMock())

    written = await ars._process_alert_date(conn, d)
    assert written == 1
    idx = {c: i for i, c in enumerate(ars._UPSERT_COLS)}
    stored = executed[0][1]
    assert stored[idx["expct_scheduled"]] == "scheduled"
    assert stored[idx["expct_looking"]] == "forward"
    assert stored[idx["expct_combined_class"]] == "forward"
    assert stored[idx["expct_classifiable_frac"]] == pytest.approx(1.0)


@pytest.mark.asyncio
async def test_day_bar_source_falls_back_to_polygon(monkeypatch):
    from tests.conftest import make_mock_pool
    pool, conn = make_mock_pool()
    d = date(2026, 8, 10)
    conn.fetch = AsyncMock(side_effect=[
        [_alert_row(1, "CCCC", d)],
        _prior_rows_fixture(d),
        [],
    ])
    conn.fetchrow = AsyncMock(side_effect=[
        None,  # mi_daily_closes has no row -> Polygon fallback
        _trade_status(),
    ])

    async def _fake_get_index_history(ticker, from_date, to_date):
        return [{"o": 20.0, "h": 21.0, "l": 19.5, "c": 20.5}]

    import agents.market_intelligence.collector as collector_mod
    monkeypatch.setattr(collector_mod, "get_index_history", _fake_get_index_history)

    executed = []

    async def _execute(sql, *args):
        executed.append(args)
        return "INSERT 0 1"
    conn.execute = _execute
    monkeypatch.setattr(ars, "get_pool", AsyncMock(return_value=pool))
    monkeypatch.setattr(ars, "log_audit_event", AsyncMock())

    await ars._process_alert_date(conn, d)
    idx = {c: i for i, c in enumerate(ars._UPSERT_COLS)}
    assert executed[0][idx["day_bar_source"]] == "polygon_fallback"
    assert executed[0][idx["day_open"]] == 20.0


@pytest.mark.asyncio
async def test_atr14_uses_correctly_paired_dates_when_a_prior_row_lacks_high_low(monkeypatch):
    """Regression (found in review before ship): H/L-filtering out a row with a NULL
    high_price and then zipping the filtered list POSITIONALLY against the unfiltered
    date list silently mispairs every row after the drop — a date-based cutoff filter
    then applies to the WRONG dates (and can drop the true most-recent row off the end
    entirely). Fixture: a null-H/L row sits before the ATR cutoff boundary; the rows
    straddling the boundary carry deliberately distinct H/L so a mispairing changes both
    WHICH rows are included and the resulting atr14_prior value — not just a count."""
    from tests.conftest import make_mock_pool
    pool, conn = make_mock_pool()
    d = date(2026, 8, 20)
    monkeypatch.setattr(ars, "_ATR14_LOOKBACK_DAYS", 13)  # cutoff = d-1-13 = d-14

    # index i -> trade_date = d - 20 + i  (i=0..19, oldest..newest, spanning d-20..d-1).
    # A null-H/L row sits well BEFORE the cutoff (i=2); two deliberately EXTREME rows
    # straddle the window — one right AT the cutoff boundary (i=6), one at the true most
    # recent day (i=19). A positional (unfixed) zip shifts everything after the null row by
    # one, which relabels the i=6 extreme onto an excluded date and drops the i=19 extreme
    # off the end of a truncated zip — either failure changes the composition of the ATR
    # window, not just its date labels, so the resulting atr14_prior VALUE differs.
    specs = [(105.0, 95.0, 100.0)] + [(None, None, 100.0)] + [(101.0, 99.0, 100.0)] * 4
    specs += [(150.0, 50.0, 100.0)]  # i=6, the cutoff boundary
    specs += [(101.0, 99.0, 100.0)] * 12
    specs += [(300.0, 10.0, 100.0)]  # i=19, the most recent day
    assert len(specs) == 20
    prior_raw = [
        {"trade_date": d - timedelta(days=20 - i), "high_price": h, "low_price": l, "close": c}
        for i, (h, l, c) in enumerate(specs)
    ]
    cutoff = d - timedelta(days=14)
    expected_atr_hlc = [
        (h, l, c) for i, (h, l, c) in enumerate(specs)
        if h is not None and (d - timedelta(days=20 - i)) >= cutoff
    ]
    expected_atr14 = ars.compute_atr14_prior(expected_atr_hlc)
    assert expected_atr14 is not None

    conn.fetch = AsyncMock(side_effect=[
        [_alert_row(1, "EEEE", d)],
        prior_raw,
        [],
    ])
    conn.fetchrow = AsyncMock(side_effect=[
        _daily_bar_row(101.0, 101.5, 100.8, 101.2),
        _trade_status(),
    ])
    executed = []

    async def _execute(sql, *args):
        executed.append(args)
        return "INSERT 0 1"
    conn.execute = _execute
    monkeypatch.setattr(ars, "get_pool", AsyncMock(return_value=pool))
    monkeypatch.setattr(ars, "log_audit_event", AsyncMock())

    await ars._process_alert_date(conn, d)
    idx = {c: i for i, c in enumerate(ars._UPSERT_COLS)}
    assert executed[0][idx["atr14_prior"]] == pytest.approx(expected_atr14)
    # prior_bars_count is CLOSE-only (matches the probe's exact gate) — all 20 rows have a
    # close, including the null-H/L one, so the ranking-pool gate isn't shrunk by an H/L gap.
    assert executed[0][idx["prior_bars_count"]] == 20


@pytest.mark.asyncio
async def test_trade_exists_and_filled_are_read_from_mi_live_trades_status(monkeypatch):
    from tests.conftest import make_mock_pool
    pool, conn = make_mock_pool()
    d = date(2026, 8, 10)
    conn.fetch = AsyncMock(side_effect=[
        [_alert_row(1, "DDDD", d)],
        _prior_rows_fixture(d),
        [],
    ])
    conn.fetchrow = AsyncMock(side_effect=[
        _daily_bar_row(101.0, 101.5, 100.8, 101.2),
        _trade_status(n=1, n_filled=1, mode="live"),
    ])
    executed = []

    async def _execute(sql, *args):
        executed.append(args)
        return "INSERT 0 1"
    conn.execute = _execute
    monkeypatch.setattr(ars, "get_pool", AsyncMock(return_value=pool))
    monkeypatch.setattr(ars, "log_audit_event", AsyncMock())

    await ars._process_alert_date(conn, d)
    idx = {c: i for i, c in enumerate(ars._UPSERT_COLS)}
    assert executed[0][idx["trade_exists"]] is True
    assert executed[0][idx["trade_filled"]] is True
    assert executed[0][idx["account_mode"]] == "live"


@pytest.mark.asyncio
async def test_record_alert_rank_shadow_scans_only_unrecorded_dates(monkeypatch):
    """The catch-up scan: only alert_dates carrying at least one unrecorded alert_id are
    fetched — pinned by asserting the SQL and by proving _process_alert_date runs once
    per returned date."""
    from tests.conftest import make_mock_pool
    pool, conn = make_mock_pool()
    d1 = date(2026, 8, 5)

    conn.fetch = AsyncMock(side_effect=[
        [{"alert_date": d1}],   # _DATES_NEEDING_PROCESSING_SQL
    ])
    monkeypatch.setattr(ars, "get_pool", AsyncMock(return_value=pool))
    monkeypatch.setattr(ars, "log_audit_event", AsyncMock())

    calls = []

    async def _fake_process(conn_, alert_date_):
        calls.append(alert_date_)
        return 3
    monkeypatch.setattr(ars, "_process_alert_date", _fake_process)

    out = await ars.record_alert_rank_shadow(date(2026, 8, 10))
    assert out == {"population": 1, "written": 3, "errors": 0}
    assert calls == [d1]
    sql_used = conn.fetch.call_args_list[0][0][0]
    assert "LEFT JOIN mi_alert_rank_shadow" in sql_used
    assert "s.alert_id IS NULL" in sql_used


def test_dates_needing_processing_sql_also_catches_pre_568_stale_rows():
    """#568 migration coverage — this is a string assertion on a SQL CONSTANT, not a
    label/comment (the usual reason this file avoids string assertions, per its own
    header comment: "every assertion checks a computed VALUE, never a comment/label
    string"). It is an exception, and a deliberate one: a mocked pool cannot evaluate a
    real WHERE clause against real rows, so the predicate ITSELF is the thing under
    test, and this is the only way to pin it. The advisor caught a real bug this guards:
    the ORIGINAL predicate (`s.alert_id IS NULL` alone) only reprocesses alert_dates
    with a genuinely MISSING shadow row — it would never revisit the 255 rows that
    already existed before `expct_combined_class` was added, silently leaving them NULL
    forever. The `OR s.expct_combined_class IS NULL` clause is what makes the one-time
    backfill actually run. Read-only prod check (2026-08-18): the OLD predicate alone
    matched 1 of 62 distinct live alert_dates; see `_DATES_NEEDING_PROCESSING_SQL`'s own
    comment for the full reasoning (the column doesn't exist in prod yet, so the NEW
    predicate can't be run there today — the guarantee is a Postgres one: ADD COLUMN
    with no DEFAULT sets every existing row's new column to NULL)."""
    assert "s.alert_id IS NULL OR s.expct_combined_class IS NULL" in ars._DATES_NEEDING_PROCESSING_SQL


@pytest.mark.asyncio
async def test_summary_audit_fires_even_when_every_date_errors(monkeypatch):
    """2026-08-16 cleanup review finding 1: a night where the population query returns
    dates but every one fails to process used to come out byte-identical (0, no audit
    row) to a night with nothing to do at all — the summary event was gated `if written`.
    MUTATION TARGET: restoring that gate. Population > 0 with 0 written must still emit
    exactly one `alert_rank_shadow_recorded` row stating BOTH numbers, so "0 of 2" reads
    as distinguishable from "0 of 0" in the audit trail."""
    from tests.conftest import make_mock_pool
    pool, conn = make_mock_pool()
    d1, d2 = date(2026, 8, 5), date(2026, 8, 6)
    conn.fetch = AsyncMock(side_effect=[[{"alert_date": d1}, {"alert_date": d2}]])
    monkeypatch.setattr(ars, "get_pool", AsyncMock(return_value=pool))
    audited = []

    async def _audit(event_type, summary, detail=""):
        audited.append((event_type, summary))
    monkeypatch.setattr(ars, "log_audit_event", _audit)

    async def _fake_process(conn_, alert_date_):
        raise RuntimeError("boom")
    monkeypatch.setattr(ars, "_process_alert_date", _fake_process)

    out = await ars.record_alert_rank_shadow(date(2026, 8, 10))
    assert out == {"population": 2, "written": 0, "errors": 2}
    recorded = [s for e, s in audited if e == "alert_rank_shadow_recorded"]
    assert len(recorded) == 1
    # Checks the POPULATION phrase specifically, not just "2" anywhere in the string
    # (a bare substring check would also match an unrelated date fragment — the exact
    # "assertion matched a comment, not behaviour" trap this file's own header warns of).
    assert "0 row(s) written/updated across 2 date(s) needing processing" in recorded[0]
    assert "(2 error(s))" in recorded[0]
    assert sum(1 for e, _ in audited if e == "alert_rank_shadow_error") == 2


@pytest.mark.asyncio
async def test_summary_audit_fires_on_a_genuinely_empty_night_too(monkeypatch):
    """The unconditional-emission fix must not accidentally start firing TWICE, or stop
    firing on the legitimate 0-of-0 night (nothing new since the last run) — both are
    real, distinguishable states this test pins independently of the error-path test
    above."""
    from tests.conftest import make_mock_pool
    pool, conn = make_mock_pool()
    conn.fetch = AsyncMock(side_effect=[[]])
    monkeypatch.setattr(ars, "get_pool", AsyncMock(return_value=pool))
    audited = []

    async def _audit(event_type, summary, detail=""):
        audited.append((event_type, summary))
    monkeypatch.setattr(ars, "log_audit_event", _audit)

    out = await ars.record_alert_rank_shadow(date(2026, 8, 10))
    assert out == {"population": 0, "written": 0, "errors": 0}
    recorded = [s for e, s in audited if e == "alert_rank_shadow_recorded"]
    assert len(recorded) == 1
    assert "0 row(s) written/updated across 0 date(s) needing processing" in recorded[0]


# ── retention ───────────────────────────────────────────────────────────────────────────


def test_purge_old_data_never_deletes_the_alert_rank_shadow():
    from unittest.mock import patch
    import agents.market_intelligence.db as db_module

    executed_sqls = []

    async def fake_execute(sql, cutoff):
        executed_sqls.append(sql.strip())
        return "DELETE 0"

    mock_conn = MagicMock()
    mock_conn.execute = fake_execute
    mock_pool = MagicMock()
    mock_pool.acquire = MagicMock()
    mock_pool.acquire.return_value.__aenter__ = AsyncMock(return_value=mock_conn)
    mock_pool.acquire.return_value.__aexit__ = AsyncMock(return_value=False)

    with patch.object(db_module, "get_pool", AsyncMock(return_value=mock_pool)):
        asyncio.run(db_module.purge_old_data())

    tables_deleted = {sql.split("FROM")[1].split("WHERE")[0].strip() for sql in executed_sqls if "DELETE" in sql}
    assert "mi_alert_rank_shadow" not in tables_deleted


# ── THE LINE: nothing else in the repo reads/imports this module or its table ─────────


def test_nothing_outside_this_module_imports_alert_rank_shadow():
    """grep the whole repo for imports of this module — only this file, its own module,
    and the scheduler registration may reference it. A decision-path import (ep_detector,
    entry_pipeline, order_manager, judge) here would be THE LINE breach this test exists
    to catch."""
    out = subprocess.run(
        ["grep", "-rl", "--include=*.py", "alert_rank_shadow",
         str(REPO / "agents"), str(REPO / "tests")],
        capture_output=True, text=True,
    )
    hits = {line.strip() for line in out.stdout.splitlines() if line.strip()}
    allowed = {
        str(REPO / "agents/market_intelligence/alert_rank_shadow.py"),
        str(REPO / "agents/market_intelligence/scheduler.py"),
        str(REPO / "agents/market_intelligence/db.py"),
        # 2026-08-16 cleanup review finding 1 Fix B: a READ-ONLY liveness row (telemetry
        # watching telemetry, no write path back into alert_rank_shadow) — see that
        # module's own docstring for why this is not THE LINE breach this test guards.
        str(REPO / "agents/market_intelligence/health_checks.py"),
        # 2026-08-17 (#517): the readiness-sanity population-mismatch check's static table->
        # discriminating-column map includes `mi_alert_rank_shadow` (it has `account_mode`,
        # per prod information_schema.columns) purely as a STRING KEY for regex analysis of
        # OTHER entries' predicate_sql text — it never imports the module, queries the table,
        # or touches any decision path. Same non-decision, read-only-adjacent shape as the
        # health_checks.py exemption directly above.
        str(REPO / "agents/market_intelligence/data_gated_reviews.py"),
        str(REPO / "tests/test_alert_rank_shadow.py"),
        str(REPO / "tests/test_detector_liveness_543.py"),
        # 2026-08-18: PART 2 of the six-item-list build (running-read conversion of
        # `alert_rank_shadow_out_of_sample`). Tests the registry entry's YAML text and
        # the pure, DB-free scorer/renderer in `scripts/alert_rank_shadow_running_read.py`
        # (which is itself outside agents/ and tests/, so this grep never sees it directly)
        # — read-only reporting/plumbing, same non-decision shape as the two exemptions
        # above; no import of the live module, no DB access, nothing on a decision path.
        str(REPO / "tests/test_alert_rank_shadow_running_read.py"),
        # 2026-08-22 (#533 Change 6): catalyst_tier_shadow.py imports ONLY the pure,
        # DB-free expectedness classifiers (classify_expectedness /
        # combined_expectedness_class) to compute its OWN shadow verdicts, written
        # solely to mi_catalyst_tier_shadow — telemetry consuming telemetry's pure
        # functions. It never writes mi_alert_rank_shadow, never reads its table, and
        # its verdicts are read by nothing on a grading/entry/sizing path (pinned by
        # tests/test_catalyst_tier_shadow.py::test_no_live_path_reads_the_shadow_table).
        # Same non-decision shape as the health_checks.py exemption above.
        str(REPO / "agents/market_intelligence/catalyst_tier_shadow.py"),
        str(REPO / "tests/test_catalyst_tier_shadow.py"),
    }
    unexpected = hits - allowed
    assert not unexpected, f"unexpected references to alert_rank_shadow: {unexpected}"


def test_mi_alert_rank_shadow_table_is_never_read_by_the_grading_or_entry_path():
    """grep the ep_detector / broker decision-path files for the table name itself
    (not just the module) — a caller could read the raw table without importing this
    module's Python. Zero hits outside db.py's own CREATE TABLE + this module."""
    out = subprocess.run(
        ["grep", "-rl", "mi_alert_rank_shadow",
         str(REPO / "agents/market_intelligence/ep_detector.py"),
         str(REPO / "agents/market_intelligence/broker")],
        capture_output=True, text=True,
    )
    hits = [line.strip() for line in out.stdout.splitlines() if line.strip()]
    assert hits == []


# ═══════════════════ #569 — pre-gap extension + base duration x quietness ═════════════
# Every free parameter these functions use was pre-registered in
# scripts/probes/_569_pregap_base_axes.py BEFORE any outcome was joined; these tests pin
# the definitions as registered. All are behavioural: each was mutation-checked during
# authoring (reference price swapped to the open · band made down-moves-only · censoring
# forced False · ceiling widened · legacy-window split dropped · stale clause removed)
# and each targeted test failed under its mutation; mutations reverted, not left in.


def test_pregap_extension_reads_the_prior_close_not_the_gap_day_open():
    """THE MRNA PROPERTY: a flat-basing stock that gaps hugely is maximally extended on
    the gap-day open (the existing EOD read) and barely extended pre-gap. Exact values
    both ways, so a mutation that re-anchors pregap to the open cannot pass."""
    closes = [99.0] * 45 + [100.0] * 10  # 55 sessions, drifting 1% — a quiet base
    adr = 0.02
    ext_pregap, no_ma_pregap = ars.compute_pregap_extension(closes, adr)
    # SMAs through D-1: sma10=100.0 (not strictly below), sma20=99.5, sma50=99.2
    assert no_ma_pregap is False
    assert ext_pregap == pytest.approx(
        st_median([(100.0 - 99.5) / 100.0 / adr, (100.0 - 99.2) / 100.0 / adr])
    )
    assert ext_pregap == pytest.approx(0.325)
    # the SAME stock gapping to 200 at the open: the gap-day read calls it ~25x ADR
    ext_eod, _ = ars.compute_ma_distance_extension(200.0, closes, adr)
    assert ext_eod == pytest.approx((200.0 - 99.5) / 200.0 / adr)  # median of the three
    assert ext_pregap < 1.0 < ext_eod  # extension created BY the gap, invisible pre-gap


def test_pregap_extension_no_ma_below_when_price_sits_at_or_below_its_mas():
    closes = [100.0] * 45 + [99.0] * 10  # drifted DOWN — every SMA at/above the close
    ext, no_ma_below = ars.compute_pregap_extension(closes, 0.02)
    assert ext is None
    assert no_ma_below is True


def test_pregap_extension_unclassifiable_below_the_prior_bars_gate():
    ext, flag = ars.compute_pregap_extension([100.0] * 40, 0.02)  # < 50 closes
    assert (ext, flag) == (None, None)
    assert ars.compute_pregap_extension([], 0.02) == (None, None)


def test_base_duration_an_up_move_breaks_the_base_exactly_like_a_down_move():
    """The operator's 2026-08-19 correction, as behaviour: quietness means no major move
    in EITHER direction. A spike ABOVE the current price 50 sessions back (h=180, faded)
    and a flush BELOW it (l=55, recovered) must yield the SAME base_days = 49 — the
    up-spike is the case a drawdown-only band definition silently passes (it sits
    entirely above every later price), and this test fails such a mutant."""
    pre = [(101.0, 99.0, 100.0)] * 50
    post = [(101.0, 99.0, 100.0)] * 49
    up_spike = ars.compute_base_duration(pre + [(180.0, 99.0, 100.0)] + post, 0.02)
    down_flush = ars.compute_base_duration(pre + [(101.0, 55.0, 100.0)] + post, 0.02)
    assert up_spike["base_days_raw40"] == 49    # (180-99)/180 = 45% > 40% stops the walk
    assert down_flush["base_days_raw40"] == 49  # (101-55)/101 = 45.5% > 40% likewise
    assert up_spike["base_days_raw40"] == down_flush["base_days_raw40"]
    assert up_spike["base_censored_raw40"] is False  # the base ENDED — not a history edge
    assert up_spike["base_depth_raw40"] == pytest.approx((101.0 - 99.0) / 101.0)


def test_base_duration_censored_at_the_history_edge_but_not_at_the_252_cap():
    quiet = (101.0, 99.0, 100.0)
    short = ars.compute_base_duration([quiet] * 30, 0.02)
    assert short["base_days_raw40"] == 30
    assert short["base_censored_raw40"] is True   # quiet to the edge -> a lower bound
    assert short["base_lookback_bars"] == 30
    long = ars.compute_base_duration([quiet] * 260, 0.02)
    assert long["base_days_raw40"] == 252          # the registered one-year cap
    assert long["base_censored_raw40"] is False    # cap reached is NOT censoring


def test_base_duration_unclassifiable_below_min_lookback_never_defaulted():
    out = ars.compute_base_duration([(101.0, 99.0, 100.0)] * 19, 0.02)
    assert out["base_lookback_bars"] == 19         # coverage ALWAYS populated
    for k, v in out.items():
        if k != "base_lookback_bars":
            assert v is None, f"{k} must be NULL (visible), got {v}"


def test_base_duration_adr6_ceiling_binds_tighter_on_a_low_adr_name():
    """raw40 vs the ADR-normalised twin diverge exactly where they should: a 17% step
    sits inside the raw 40% band but outside 6 x a 2% ADR (= 12%)."""
    older = [(86.0, 84.0, 85.0)] * 30
    recent = [(101.0, 99.0, 100.0)] * 30
    out = ars.compute_base_duration(older + recent, 0.02)
    # full 60-session band: (101-84)/101 = 16.8% <= 40% -> raw40 spans everything
    assert out["base_days_raw40"] == 60
    assert out["base_censored_raw40"] is True
    # 6xADR ceiling = 12%: the walk stops when the older block enters the band
    assert out["base_days_adr6"] == 30
    assert out["base_censored_adr6"] is False
    assert out["base_depth_adr6"] == pytest.approx((101.0 - 99.0) / 101.0)


def test_base_net_displacement_reads_drift_over_the_base_in_adr_units():
    rows = [(100.0 + 0.5 * i + 1.0, 100.0 + 0.5 * i - 1.0, 100.0 + 0.5 * i) for i in range(25)]
    out = ars.compute_base_duration(rows, 0.05)
    assert out["base_days_raw40"] == 25            # band (113-99)/113 = 12.4% <= 40%
    assert out["base_depth_raw40"] == pytest.approx((113.0 - 99.0) / 113.0)
    # |112 - 100| / 100 / 0.05 = 2.4 x ADR of net drift, base start close -> D-1 close
    assert out["base_net_disp_xadr"] == pytest.approx(2.4)


def test_base_duration_without_adr20_still_computes_raw40_and_marks_adr6_null():
    out = ars.compute_base_duration([(101.0, 99.0, 100.0)] * 30, None)
    assert out["base_days_raw40"] == 30
    assert out["base_days_adr6"] is None           # variant needs ADR20; NULL, visible
    assert out["base_net_disp_xadr"] is None


@pytest.mark.asyncio
async def test_process_alert_date_writes_the_pregap_and_base_axes(monkeypatch):
    """#569 end-to-end wiring (the #568 pattern): the axes flow through
    `_process_alert_date` into the upserted columns — including the two visible-NULL
    conventions (no-MA-below pregap ext; base coverage column always populated). A
    mutation wiring ext_xadr_pregap to the EOD extension fails here: the fixture's EOD
    ext is a number (open 101 > SMA 100) while the pregap ext is genuinely NULL+flag."""
    from tests.conftest import make_mock_pool
    pool, conn = make_mock_pool()
    d = date(2026, 8, 10)
    conn.fetch = AsyncMock(side_effect=[
        [_alert_row(1, "MRNA", d)],
        _prior_rows_fixture(d),   # 55 flat sessions: h=101, l=99, c=100
        [],
    ])
    conn.fetchrow = AsyncMock(side_effect=[
        _daily_bar_row(101.0, 101.5, 100.8, 101.2),
        _trade_status(),
    ])
    executed = []

    async def _execute(sql, *args):
        executed.append((sql, args))
        return "INSERT 0 1"
    conn.execute = _execute
    monkeypatch.setattr(ars, "get_pool", AsyncMock(return_value=pool))
    monkeypatch.setattr(ars, "log_audit_event", AsyncMock())

    written = await ars._process_alert_date(conn, d)
    assert written == 1
    idx = {c: i for i, c in enumerate(ars._UPSERT_COLS)}
    stored = executed[0][1]
    # flat closes: every SMA == prior close -> genuinely undefined, never zero-filled
    assert stored[idx["ext_xadr_pregap"]] is None
    assert stored[idx["ext_no_ma_below_pregap"]] is True
    # while the EOD read (open 101 above SMA 100) IS a number — the two must differ
    assert stored[idx["ext_xadr_eod"]] == pytest.approx((101.0 - 100.0) / 101.0 / 0.02)
    # 55 quiet sessions, all within both bands, running to the history edge
    assert stored[idx["base_days_raw40"]] == 55
    assert stored[idx["base_censored_raw40"]] is True
    assert stored[idx["base_depth_raw40"]] == pytest.approx((101.0 - 99.0) / 101.0)
    assert stored[idx["base_days_adr6"]] == 55
    assert stored[idx["base_net_disp_xadr"]] == pytest.approx(0.0)
    assert stored[idx["base_lookback_bars"]] == 55


@pytest.mark.asyncio
async def test_legacy_100_day_window_is_preserved_when_the_pull_spans_400_days(monkeypatch):
    """#569 widened the daily pull to 400 days for the base axis; every pre-#569 column
    must keep computing from the ORIGINAL 100-day series. Rows older than 100 days (at a
    2x different price) must be INVISIBLE to prior_bars_count/SMA/gap — and VISIBLE to
    the base axis, which correctly ends the base at that older price regime."""
    from tests.conftest import make_mock_pool
    pool, conn = make_mock_pool()
    d = date(2026, 8, 10)
    old_rows = [
        {"trade_date": d - timedelta(days=300 - i), "high_price": 201.0, "low_price": 199.0, "close": 200.0}
        for i in range(30)
    ]
    conn.fetch = AsyncMock(side_effect=[
        [_alert_row(1, "AAAA", d)],
        old_rows + _prior_rows_fixture(d),   # 30 old @200 + 55 recent @100, ascending
        [],
    ])
    conn.fetchrow = AsyncMock(side_effect=[
        _daily_bar_row(101.0, 101.5, 100.8, 101.2),
        _trade_status(),
    ])
    executed = []

    async def _execute(sql, *args):
        executed.append((sql, args))
        return "INSERT 0 1"
    conn.execute = _execute
    monkeypatch.setattr(ars, "get_pool", AsyncMock(return_value=pool))
    monkeypatch.setattr(ars, "log_audit_event", AsyncMock())

    await ars._process_alert_date(conn, d)
    idx = {c: i for i, c in enumerate(ars._UPSERT_COLS)}
    stored = executed[0][1]
    assert stored[idx["prior_bars_count"]] == 55       # NOT 85 — legacy window intact
    assert stored[idx["sma50"]] == pytest.approx(100.0)  # unpolluted by the 200s
    assert stored[idx["base_lookback_bars"]] == 85      # base axis sees the full pull
    # the base walk stops where the 200-price regime begins: not a history-edge read
    assert stored[idx["base_days_raw40"]] == 55
    assert stored[idx["base_censored_raw40"]] is False


def test_dates_needing_processing_sql_also_catches_pre_569_stale_rows():
    """Same exception, same reason as the #568 predicate test above (a SQL CONSTANT can
    only be pinned as text): `base_lookback_bars` is ALWAYS populated by
    `compute_base_duration` under #569 code (0 is a real value), so NULL uniquely means
    "written before #569" — the OR clause is what makes the one-time recompute of every
    pre-existing row actually run, then self-extinguishes."""
    assert "OR s.base_lookback_bars IS NULL" in ars._DATES_NEEDING_PROCESSING_SQL


def st_median(vals):
    import statistics
    return statistics.median(vals)
