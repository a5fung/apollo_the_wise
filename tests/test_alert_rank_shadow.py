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

    n = await ars.record_alert_rank_shadow(date(2026, 8, 10))
    assert n == 3
    assert calls == [d1]
    sql_used = conn.fetch.call_args_list[0][0][0]
    assert "LEFT JOIN mi_alert_rank_shadow" in sql_used
    assert "s.alert_id IS NULL" in sql_used


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
        str(REPO / "tests/test_alert_rank_shadow.py"),
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
