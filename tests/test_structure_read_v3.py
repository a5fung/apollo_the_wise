"""`scripts/probes/_structure_read_v3.py` + `tests/fixtures/must_not_trade_charts.py`.

WHY THESE TESTS EXIST. The v3 read is SHADOW and drives nothing — no rule, no gate, no
toggle, no trade state (THE LINE). What these tests protect is not behaviour, it is the
honesty of the two numbers in `docs/analysis/structure_read_v3_2026-08-25.md`:

  1. **The live extension rule must be REPLICATED, not approximated.** The whole "what does
     this add BEYOND the gate we already have" claim is unfalsifiable if
     `extension_live_pct` is a lookalike. `ep_detector.py` uses `MIN(close)` over
     `[alert_date - 10 CALENDAR days, alert_date)` — calendar, not sessions — and fails OPEN
     when the window is empty. All three properties are pinned below.
  2. **`is_clear_air` must read the NUMBERS, not v2's `label`.** IPCX 2026-07-29 carries
     `overhead_vol_frac = 0.9959` and is still labelled CLEAR_AIR by v2, because the label
     consults only the zone and vacuum fields. That artifact is pinned as a regression test
     so nobody later "fixes" the composition by reaching for the label.
  3. **No cutline may acquire a default.** `verdict()` takes the cutline as a required
     argument on purpose: a default would become a de-facto proposed threshold, and
     detection criteria are the operator's sole authority.
  4. **The operator's labels must not drift.** The fixture records his verbatim words and
     the numbers he was shown. `test_fixture_numbers_still_match_the_bars` re-derives every
     recorded `extension_live_pct` from `mi_daily_closes` bars and fails if the fixture ever
     drifts from its source — the same guard `must_not_miss_eps.py` uses against
     `_552_cohort.psv`.

🛑 WHAT THESE TESTS DELIBERATELY DO **NOT** ASSERT: that any of the eleven must stay
excluded, or that any measure must reject them. That would be a new admission constraint,
which is the operator's call and not a test's. The fixture records his judgement and the
live stack's past behaviour as DATA.

No DB, no network, no Alpaca, no LLM — arithmetic over literal bars, plus one optional
re-derivation from a capture file that skips when the capture is absent.
"""
from __future__ import annotations

import gzip
from collections import defaultdict
from datetime import date, timedelta
from pathlib import Path

import pytest

from scripts.probes import _structure_read_v3 as V3
from tests.fixtures import must_not_trade_charts as F

_CAPTURE = Path(__file__).resolve().parents[1] / "scripts" / "probes" / "_srbt_bars.psv.gz"


def _bars(rows, start=date(2026, 3, 2)):
    """rows = [(o, h, l, c, v), ...] on consecutive weekday-ish dates."""
    out = []
    d = start
    for o, h, l, c, v in rows:
        out.append({"trade_date": d, "open_price": float(o), "high_price": float(h),
                    "low_price": float(l), "close": float(c), "volume": float(v)})
        d += timedelta(days=1)
    return out


# ══ 1 — the live extension rule, replicated ═══════════════════════════════════════════
def test_extension_live_pct_reproduces_the_live_arithmetic():
    """(prev_close - MIN(close in window)) / MIN * 100, exactly as ep_detector.py."""
    bars = _bars([(10, 10, 10, 10, 1), (10, 10, 10, 8, 1), (10, 10, 10, 12, 1)],
                 start=date(2026, 3, 2))
    # window [03-05 - 10d, 03-05) = 02-23..03-04 -> all three bars; MIN close = 8; prev = 12
    got = V3.extension_live_pct(bars, date(2026, 3, 5))
    assert got == pytest.approx((12 - 8) / 8 * 100)          # 50.0%


def test_the_live_window_is_calendar_days_not_trading_sessions():
    """The gate's window is `today - timedelta(days=10)`. A bar 11 calendar days back is
    OUTSIDE it even though it is only a few sessions back — replicating that is the whole
    point of this function, and getting it wrong would silently change every count."""
    old = _bars([(10, 10, 10, 5, 1)], start=date(2026, 3, 1))     # 11 days before 03-12
    recent = _bars([(10, 10, 10, 9, 1), (10, 10, 10, 10, 1)], start=date(2026, 3, 9))
    bars = old + recent
    got = V3.extension_live_pct(bars, date(2026, 3, 12))
    # the 5.0 close is excluded; MIN over the window is 9.0
    assert got == pytest.approx((10 - 9) / 9 * 100)
    assert got != pytest.approx((10 - 5) / 5 * 100)


def test_the_gate_fails_open_when_the_window_is_empty():
    """`extension_map.get(ticker)` returns None live and the check is SKIPPED — the name
    passes. A new filter that fails CLOSED where the live one fails open would be a
    different rule wearing the same name."""
    stale = _bars([(10, 10, 10, 5, 1)], start=date(2026, 1, 5))
    assert V3.extension_live_pct(stale, date(2026, 3, 12)) is None
    assert V3.blocked_by_live_extension_rule(stale, date(2026, 3, 12)) is False


def test_blocked_uses_the_live_constant_and_is_inclusive_at_the_cap():
    """The live test is `>=`, and the cap is IMPORTED so an operator change carries over."""
    from agents.market_intelligence.ep_detector import MAX_EXTENSION_PCT
    assert V3.MAX_EXTENSION_PCT is MAX_EXTENSION_PCT
    lo = 100.0
    hi = lo * (1 + MAX_EXTENSION_PCT / 100.0)                 # exactly at the cap
    bars = _bars([(1, 1, 1, lo, 1), (1, 1, 1, hi, 1)], start=date(2026, 3, 10))
    assert V3.blocked_by_live_extension_rule(bars, date(2026, 3, 12)) is True
    just_under = _bars([(1, 1, 1, lo, 1), (1, 1, 1, hi * 0.999, 1)], start=date(2026, 3, 10))
    assert V3.blocked_by_live_extension_rule(just_under, date(2026, 3, 12)) is False


# ══ 2 — the run-up family ═════════════════════════════════════════════════════════════
def test_run_up_windows_measure_from_the_low_of_their_own_window():
    bars = _bars([(10, 10, 4, 5, 1)] + [(10, 10, 8, 9, 1)] * 4 + [(10, 10, 10, 12, 1)])
    # last 5 sessions exclude the 4.0 low; last 6 include it
    assert V3.runup_low_pct(bars, 5) == pytest.approx((12 - 8) / 8 * 100)
    assert V3.runup_low_pct(bars, 6) == pytest.approx((12 - 4) / 4 * 100)
    # ext_close_pct uses CLOSES, so it sees 9.0 not 8.0 over the same 5
    assert V3.ext_close_pct(bars, 5) == pytest.approx((12 - 9) / 9 * 100)


def test_runup_adr_divides_by_adr_in_price_units():
    """The ADR-normalised member exists so a run can be read in the name's own daily
    ranges. 20% ADR on a 12.00 close = 2.40 per unit."""
    bars = _bars([(10, 10, 8, 9, 1)] * 5 + [(10, 10, 10, 12, 1)])
    assert V3.runup_adr(bars, 5, 20.0) == pytest.approx((12 - 8) / (12 * 0.20))
    assert V3.runup_adr(bars, 5, None) is None
    assert V3.runup_adr(bars, 5, 0.0) is None


def test_pct_of_captured_range_is_zero_at_the_low_and_one_at_the_high():
    at_high = _bars([(1, 20, 5, 20, 1), (1, 20, 5, 20, 1)])
    at_low = _bars([(1, 20, 5, 20, 1), (1, 20, 5, 5, 1)])
    assert V3.pct_of_captured_range(at_high) == pytest.approx(1.0)
    assert V3.pct_of_captured_range(at_low) == pytest.approx(0.0)


# ══ 3 — the composition ═══════════════════════════════════════════════════════════════
def test_is_clear_air_reads_the_numbers_not_the_v2_label():
    """🔴 THE IPCX ARTIFACT, pinned. v2 labels a name CLEAR_AIR while 99.6% of its traded
    volume sits above the open, because the label consults only zones and vacuums. v3's
    composition inherits that, deliberately and explicitly, rather than silently."""
    ipcx_shaped = {"zones_remaining": 0, "inside_unfilled_gap": False,
                   "overhead_unfilled_gap_span_adr": 0.0,
                   "overhead_vol_frac": 0.9959, "label": "CLEAR_AIR"}
    assert V3.is_clear_air(ipcx_shaped) is True

    buried = dict(ipcx_shaped, zones_remaining=3)
    assert V3.is_clear_air(buried) is False
    assert V3.is_clear_air(dict(ipcx_shaped, inside_unfilled_gap=True)) is False
    assert V3.is_clear_air(dict(ipcx_shaped, overhead_unfilled_gap_span_adr=2.0)) is False


def test_verdict_requires_an_explicit_cutline():
    """No default cutline, ever. A default becomes a proposed threshold, and thresholds are
    the operator's sole authority (THE LINE)."""
    with pytest.raises(TypeError):
        V3.verdict({"zones_remaining": 0}, "ext_close_pct_5")      # type: ignore[call-arg]


def test_verdict_vocabulary():
    clear = {"zones_remaining": 0, "inside_unfilled_gap": False,
             "overhead_unfilled_gap_span_adr": 0.0, "ext_close_pct_5": 50.0}
    assert V3.verdict(clear, "ext_close_pct_5", 40.0) == "EXHAUSTED_BLUE_SKY"
    assert V3.verdict(clear, "ext_close_pct_5", 60.0) == "PASS"
    assert V3.verdict(dict(clear, zones_remaining=5), "ext_close_pct_5", 40.0) == "NOT_BLUE_SKY"
    # the control arm ignores the chart read entirely
    assert V3.verdict(dict(clear, zones_remaining=5), "ext_close_pct_5", 40.0,
                      require_clear_air=False) == "EXHAUSTED_BLUE_SKY"
    assert V3.verdict({}, "ext_close_pct_5", 40.0) == "UNREADABLE"


def test_the_read_still_refuses_lookahead():
    """Inherited from v2 and re-asserted: an alert-day bar reaching the read is a hard
    error, not a silently wrong number."""
    bars = _bars([(10, 11, 9, 10, 1000)] * 30, start=date(2026, 3, 2))
    with pytest.raises(AssertionError):
        V3.structure_read_v3(bars, bars[-1]["trade_date"], 11.0)


# ══ 4 — the fixture ═══════════════════════════════════════════════════════════════════
def test_every_ruling_is_operator_sourced_and_well_formed():
    assert F.CHART_RULINGS, "the fixture must not be empty"
    for r in F.CHART_RULINGS:
        assert r.label_source == "operator", f"{r.ticker} {r.alert_date} is not operator-sourced"
        assert r.verdict in F.VERDICTS, f"{r.ticker} {r.alert_date}: unknown verdict {r.verdict}"
        assert r.ruling_date == F.RULING_DATE
        date.fromisoformat(r.alert_date)
        if r.better_date:
            date.fromisoformat(r.better_date)
            assert r.better_date_note, f"{r.ticker}: better_date needs a note saying why"


def test_the_eleven_bad_charts_are_the_measured_population():
    """The two headline counts in the v3 doc are against exactly these eleven. If the list
    grows, the doc's numbers are stale and must be recomputed."""
    assert len(F.MUST_NOT_TRADE) == 11
    assert all(r.verdict == F.BAD_CHART for r in F.MUST_NOT_TRADE)


def test_rulings_are_keyed_on_ticker_AND_date_not_ticker_alone():
    """His judgement is about WHERE IN THE MOVE a name is. CAR carries three different
    verdicts on three dates, and AEHR is a real EP in one fixture and a bad chart in the
    other — so the key must be the pair, and duplicate pairs must not exist."""
    keys = [(r.ticker, r.alert_date) for r in F.CHART_RULINGS]
    assert len(keys) == len(set(keys)), "duplicate (ticker, date) ruling"
    assert len({r.verdict for r in F.CHART_RULINGS if r.ticker == "CAR"}) > 1

    from tests.fixtures.must_not_miss_eps import MUST_NOT_MISS
    good = {(m.ticker, m.alert_date) for m in MUST_NOT_MISS if not m.excluded}
    bad = {(r.ticker, r.alert_date) for r in F.MUST_NOT_TRADE}
    assert not (good & bad), "a (ticker, date) cannot be both a real EP and a bad chart"
    assert {m.ticker for m in MUST_NOT_MISS} & {r.ticker for r in F.MUST_NOT_TRADE}, (
        "AEHR should appear on both sides on DIFFERENT dates — that pair is the point")


def test_a_date_he_only_pointed_at_is_never_labelled_as_one_he_stated():
    """🔴 THE PROVENANCE RULE. He STATED that CAR on 04-01 was ok'ish. He only POINTED AT
    MXL 04-24 — "there's 3 tight days prior to the big gap on 4/24" — while explaining why
    04-21 was the wrong date; he never ruled 04-24 tradeable. Promoting that to an operator
    must-not-reject label would put an agent's inference behind his name, which is exactly
    what this fixture forbids elsewhere (see the VEEE note). The two lists stay disjoint."""
    stated = set(F.MUST_NOT_REJECT_DATES)
    pointed = set(F.POINTED_AT_DATES)
    assert ("CAR", "2026-04-01", F.OKISH_EARLIER) in stated
    assert ("MXL", "2026-04-24", F.WRONG_DAY) in pointed
    assert ("MXL", "2026-04-24", F.WRONG_DAY) not in stated
    assert not any(t == "VEEE" for t, _, _ in stated)
    assert not {(t, d) for t, d, _ in stated} & {(t, d) for t, d, _ in pointed}

    for r in F.CHART_RULINGS:
        if r.better_date:
            assert r.better_date_provenance in (F.STATED, F.POINTED_AT), (
                f"{r.ticker} {r.alert_date}: a better_date needs its provenance declared")


def test_the_measurement_defect_is_recorded_as_such():
    """VEEE 2026-07-08 is a data defect, not a chart opinion, and must stay labelled as one
    so nobody scores it as a bad chart."""
    veee = [r for r in F.CHART_RULINGS if r.ticker == "VEEE"]
    assert len(veee) == 1
    assert veee[0].verdict == F.NO_SETUP_ON_THIS_DATE
    assert veee[0].gap_open_pct is not None and veee[0].gap_open_pct < 9.0, (
        "the whole ruling is that this date gapped under our own floor")
    assert veee[0] not in F.MUST_NOT_TRADE


def test_the_verbatim_operator_words_are_preserved():
    assert F.OPERATOR_VERDICT_ON_THE_LIST == "these are horrendous charts"
    assert "CAR on 4/1" in F.OPERATOR_QUALIFICATION
    quoted = {r.operator_words for r in F.CHART_RULINGS if r.operator_words}
    assert any("bottoming base" in w for w in quoted)         # ARQQ
    assert any("3 tight days" in w for w in quoted)           # MXL
    assert any("don't see gap" in w for w in quoted)          # VEEE


@pytest.mark.skipif(not _CAPTURE.exists(), reason="bar capture not present in this clone")
def test_fixture_numbers_still_match_the_bars():
    """Re-derive every recorded `extension_live_pct` from the capture, the same guard
    `must_not_miss_eps.py` runs against `_552_cohort.psv`. A fixture number that drifts
    from its source is worse than no number — it gets cited."""
    want = {r.ticker for r in F.CHART_RULINGS}
    bars: dict[str, list[dict]] = defaultdict(list)
    with gzip.open(_CAPTURE, "rt") as fh:
        for ln in fh:
            p = ln.rstrip("\n").split("|")
            if len(p) < 7 or p[0] not in want or p[3] == "" or p[4] == "":
                continue
            bars[p[0]].append({"trade_date": date.fromisoformat(p[1]),
                               "open_price": float(p[2]), "high_price": float(p[3]),
                               "low_price": float(p[4]), "close": float(p[5]),
                               "volume": float(p[6] or 0)})
    for t in bars:
        bars[t].sort(key=lambda r: r["trade_date"])

    for r in F.CHART_RULINGS:
        if r.extension_live_pct is None:
            continue
        ad = date.fromisoformat(r.alert_date)
        prior = [b for b in bars.get(r.ticker, []) if b["trade_date"] < ad]
        assert prior, f"no bars for {r.ticker} before {r.alert_date}"
        got = V3.extension_live_pct(prior, ad)
        assert got == pytest.approx(r.extension_live_pct, abs=0.1), (
            f"{r.ticker} {r.alert_date}: fixture says {r.extension_live_pct}, "
            f"bars say {got:.1f} — the fixture has drifted from its source")
