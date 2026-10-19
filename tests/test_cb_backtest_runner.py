"""#702 P2a — tests for scripts/probes/_cb_backtest/runner.py (daily stage) and fetch_minutes.py.

The runner only SCHEDULES calls into the frozen module (`consolidation_breakout`); what is tested here is
the logic the runner adds around it: the numpy pre-screen (proved lossless against the real gate), the
RAW-price factor segmentation, the E-is-the-next-session join, one-trade-per-base, the discovery-only
rule, the cross-section, and the minute fetcher's pure helpers. Synthetic data, plus the repo's real
labelled bars (tests/fixtures/htf_labelled_bars.psv) where a real-data check is the point.
"""
from __future__ import annotations

import datetime as dt
import gzip
import re
from pathlib import Path

import numpy as np
import pytest

from agents.market_intelligence import consolidation_breakout as cb
from scripts.probes._cb_backtest import fetch_minutes as fm
from scripts.probes._cb_backtest import runner as rn

FIXTURE = Path(__file__).resolve().parent / "fixtures" / "htf_labelled_bars.psv"


def _weekdays(n, start=dt.date(2025, 1, 6)):
    out, d = [], start
    while len(out) < n:
        if d.weekday() < 5:
            out.append(d)
        d += dt.timedelta(days=1)
    return out


def _fixture_bars():
    """{ticker: DailyBars} from the labelled fixture (real bars, ~280 sessions each)."""
    rows = {}
    for ln in FIXTURE.read_text().splitlines():
        f = ln.split("|")
        rows.setdefault(f[0], []).append(f)
    out = {}
    for t, rs in rows.items():
        cols = [[float(r[k]) for r in rs] for k in (2, 3, 4, 5, 6)]
        out[t] = cb.daily_bars_from_arrays([dt.date.fromisoformat(r[1]) for r in rs], *cols)
    return out


def _walk(n, seed, jump_at=(), jump=0.0):
    """A bounded random walk with optional single-session jumps (so some nights pass the pole gate)."""
    rng = np.random.default_rng(seed)
    c = 20.0 * np.exp(np.cumsum(rng.normal(0, 0.02, n)))
    for j in jump_at:
        c[j:] *= 1.0 + jump
    h = c * (1 + rng.uniform(0.002, 0.03, n))
    l = c * (1 - rng.uniform(0.002, 0.03, n))
    return cb.daily_bars_from_arrays(_weekdays(n), c, h, l, c, np.full(n, 2e6))


# ═══ pre-screen ═══════════════════════════════════════════════════════════════════════════════
class TestPrescreen:
    def test_mask_equals_the_brute_force_definition(self):
        b = _walk(400, 1, jump_at=(150, 260), jump=0.5)
        skip = rn.prescreen_skip_mask(b.h, b.l)
        want = np.zeros(len(b), dtype=bool)
        for i in range(85, len(b)):
            H, L = b.h[i - 45:i - 9].max(), b.l[i - 85:i - 9].min()
            want[i] = L > 0 and H / L - 1.0 < 0.30
        assert (skip == want).all()
        assert skip.any() and (~skip[85:]).any()                  # non-vacuous both ways
        assert not skip[:85].any()                                # no full window -> never skipped

    def test_a_bad_low_is_never_skipped_and_short_series_is_all_false(self):
        b = _walk(200, 2)
        l = b.l.copy()
        l[100:110] = 0.0                                          # L <= 0 anywhere in the window: cannot prove
        assert not rn.prescreen_skip_mask(b.h, l)[110:150].any()
        assert not rn.prescreen_skip_mask(b.h[:60], b.l[:60]).any()

    def test_every_skip_fails_at_prior_move_on_synthetic_and_real_bars(self):
        series = {f"syn{k}": _walk(330, k, jump_at=(140 + 20 * k,), jump=0.45) for k in range(6)}
        series.update(_fixture_bars())
        checked = skipped = passed = 0
        for name, b in series.items():
            skip = rn.prescreen_skip_mask(b.h, b.l)
            for i in range(cb.MIN_HISTORY - 1, len(b)):
                feat, gate = cb.explain_watch(b, i)
                checked += 1
                passed += feat is not None
                if skip[i]:
                    skipped += 1
                    assert feat is None and gate == "prior_move", (name, i, gate)
        assert checked > 1000 and skipped > 100 and passed > 20   # the proof is not vacuous
        # real names are in the set: MRNA's canary night passes every gate and is NOT skipped
        mrna = series["MRNA"]
        i = mrna.dates.index(dt.date(2026, 9, 16))
        assert cb.explain_watch(mrna, i)[0] is not None and not rn.prescreen_skip_mask(mrna.h, mrna.l)[i]


# ═══ scan_ticker: the funnel is exhaustive and the pre-screen is lossless ═══════════════════════
class TestScanTicker:
    def test_mrna_funnel_and_prescreen_is_lossless(self):
        b = _fixture_bars()["MRNA"]
        cidx = np.arange(len(b))
        args = ("MRNA", b, cidx, [], "CS", 0)
        on, off = rn.scan_ticker(*args), rn.scan_ticker(*args, prescreen=False)
        n_nights = len(b)
        assert sum(on["counts"].values()) == sum(off["counts"].values()) == n_nights
        assert on["counts"][(2026, "prescreen_skip")] + sum(
            v for (y, g), v in on["counts"].items() if g == "prior_move") == sum(
            v for (y, g), v in off["counts"].items() if g == "prior_move")      # skips were prior_move fails
        assert [w["watch_date"] for w in on["watch"]] == [w["watch_date"] for w in off["watch"]]
        assert on["watch"] == off["watch"]
        w = next(w for w in on["watch"] if w["watch_date"] == "2026-09-16")
        assert w["pivot_k5"] == 149.7344 and w["pivot_k10"] == 156.4151 and w["ticker"] == "MRNA"
        assert len(on["uni_ci"]) == len(on["rs"]) and on["rs"].shape[1] == 3
        assert set(g for (_, g) in on["counts"]) <= {"universe_fail", "prescreen_skip", "pass", *cb.WATCH_GATES}

    def test_a_penny_stock_is_never_a_member(self):
        b = _walk(300, 5)
        b = cb.daily_bars_from_arrays(b.dates, b.o * 0.1, b.h * 0.1, b.l * 0.1, b.c * 0.1, b.v)   # ~$2
        r = rn.scan_ticker("PENNY", b, np.arange(300), [], "CS", 0)
        assert len(r["uni_ci"]) == 0 and not r["watch"]
        assert r["counts"][(2025, "universe_fail")] + r["counts"].get((2026, "universe_fail"), 0) == 300

    def test_a_reverse_split_makes_the_raw_price_the_gate(self):
        b = _walk(300, 6)                                         # ~$20 adjusted, so RAW = adjusted x factor
        sp = [(b.dates[250], 0.1)]                                # a 1:10 reverse split after bar 249: RAW = adj x 0.1 = ~$2
        r_split = rn.scan_ticker("RVRS", b, np.arange(300), sp, "CS", 0)
        r_plain = rn.scan_ticker("RVRS", b, np.arange(300), [], "CS", 0)
        assert 0 < len(r_split["uni_ci"]) < len(r_plain["uni_ci"])       # bars before the split fail the $5 floor


# ═══ factor / classification helpers ═══════════════════════════════════════════════════════════
def test_factor_by_bar_equals_raw_factor_for_on_every_bar():
    dates = _weekdays(120)
    splits = [(dates[40], 10.0), (dates[41], 0.5), (dates[90], 0.1), (dt.date(2030, 1, 1), 3.0)]
    got = rn.factor_by_bar(dates, splits)
    want = np.array([cb.raw_factor_for(d, splits) for d in dates])
    assert (got == want).all()
    assert got[39] != got[40] and got[40] != got[41]                 # the execution date itself is post-split
    assert (rn.factor_by_bar(dates, []) == 1.0).all()


def test_split_label_boundary_is_2024_12_31():
    assert rn.split_label(dt.date(2024, 12, 31)) == "discovery"
    assert rn.split_label(dt.date(2025, 1, 1)) == "holdout"
    assert rn.split_label(dt.date(2022, 3, 28)) == "discovery"


def test_sectype_fallback_order_mi_then_sic_then_unknown():
    assert rn.resolve_sectype("A", {"A": "CS"}, {"A": "ETF"}) == "CS"
    assert rn.resolve_sectype("A", {"A": ""}, {"A": "ADRC"}) == "ADRC"       # empty mi value falls through
    assert rn.resolve_sectype("A", {}, {"A": "ETF"}) == "ETF"
    assert rn.resolve_sectype("A", {}, {}) == ""                              # unknown is admitted by universe_ok


def test_next_bar_status_is_the_next_spy_session_or_a_named_gap():
    cidx = np.array([0, 1, 2, 4, 5, 6])               # the ticker has no bar on session 3
    assert rn.next_bar_status(cidx, 0, last_ci=9) == "ok"
    assert rn.next_bar_status(cidx, 2, last_ci=9) == "gap_in_bars"             # next bar is session 4, not 3
    assert rn.next_bar_status(cidx, 5, last_ci=9) == "no_next_bar"             # data ends before the calendar
    assert rn.next_bar_status(np.array([0, 1, 2]), 2, last_ci=2) == "pending"  # D is the last session


def test_gap_fields_are_strictly_over_one_adr():
    assert rn.gap_fields(11.0, 10.0, 0.10) == (pytest.approx(0.10), False)    # exactly 1 ADR above: not over
    assert rn.gap_fields(11.01, 10.0, 0.10)[1] is True
    assert rn.gap_fields(9.5, 10.0, 0.10) == (pytest.approx(-0.05), False)


def test_acct_pct_uses_min_of_20pct_position_and_1pct_risk():
    assert rn.acct_pct(2.0, 0.02) == pytest.approx(2.0 * 0.20 * 0.02)         # 20% cap binds: 0.4% per R
    assert rn.acct_pct(3.0, 0.10) == pytest.approx(3.0 * 0.01)                # 1% risk binds
    assert rn.acct_pct(-1.0, 0.10) == pytest.approx(-0.01)


# ═══ one trade per base ════════════════════════════════════════════════════════════════════════
def _cand(ticker="X", pole="2025-03-03", k="k5", e="2025-04-01", split="discovery", e_ci=0, pole_ci=0, **cells):
    c = {"ticker": ticker, "pole_date": pole, "K": k, "E": e, "D": e, "split": split, "E_ci": e_ci,
         "pole_ci": pole_ci}
    for name in rn.CELL_NAMES:
        c[name] = bool(cells.get(name, False))
    c["C0"] = True
    return c


def test_first_breakout_per_base_and_k_is_the_trade_the_rest_are_retriggers():
    cs = [_cand(e="2025-04-03"), _cand(e="2025-04-01"), _cand(e="2025-04-02"),
          _cand(k="k10", e="2025-04-02"),                          # another K of the same base: its own first
          _cand(pole="2025-03-10", e="2025-04-01"),                # another base
          _cand(ticker="Y", e="2025-04-01")]
    rn.stamp_retrigger(cs)
    by = {(c["ticker"], c["pole_date"], c["K"], c["E"]): c["retrigger"] for c in cs}
    assert by[("X", "2025-03-03", "k5", "2025-04-01")] == 0
    assert by[("X", "2025-03-03", "k5", "2025-04-02")] == 1 and by[("X", "2025-03-03", "k5", "2025-04-03")] == 1
    assert by[("X", "2025-03-03", "k10", "2025-04-02")] == 0
    assert by[("X", "2025-03-10", "k5", "2025-04-01")] == 0 and by[("Y", "2025-03-03", "k5", "2025-04-01")] == 0


def test_first_in_cell_keeps_a_cells_valid_entry_that_the_base_level_rule_drops():
    # night 1: C1 false, breaks out (base-level trade). night 2: C1 true, breaks out again (a "retrigger").
    cs = [_cand(e="2025-04-01"), _cand(e="2025-04-02", C1=True), _cand(e="2025-04-03", C1=True)]
    rn.stamp_retrigger(cs)
    assert [c["retrigger"] for c in cs] == [0, 1, 1]
    assert [c["first_C1"] for c in cs] == [0, 1, 0]
    assert [c["first_C0"] for c in cs] == [1, 0, 0]


def test_overlap_open_is_discovery_only_and_reads_the_previous_filled_trade():
    a = _cand(pole="p1", e="2025-01-02", e_ci=10)
    b = _cand(pole="p2", e="2025-01-09", e_ci=15)                    # 5 sessions later
    c = _cand(pole="p3", e="2025-02-20", e_ci=60)
    h = _cand(pole="p4", e="2025-06-02", e_ci=100, split="holdout")
    r = _cand(pole="p1", e="2025-01-03", e_ci=11)                    # same base as a: a retrigger
    for x in (a, b, c, h, r):
        x["retrigger"] = 0
    r["retrigger"] = 1
    for x, d in ((a, "d1"), (b, "d2"), (c, "d3"), (h, "d4"), (r, "d5")):
        x["D"] = d
    outcomes = {("X", "d1", "k5"): (True, 8, "trailed"),             # open until session 18
                ("X", "d2", "k5"): (True, 3, "stopped"),             # ends at 18
                ("X", "d3", "k5"): (False, 0, None)}                 # never filled: not a trade
    rn.stamp_overlap_open([a, b, c, h, r], outcomes)
    assert (a["overlap_open"], b["overlap_open"], c["overlap_open"]) == (0, 1, 0)   # b arrived at 15 <= 18
    assert h["overlap_open"] == "" and r["overlap_open"] == ""        # holdout / retrigger: not computed
    d = _cand(pole="p9", e="2025-03-03", e_ci=40)
    d["retrigger"], d["D"] = 0, "z"
    prev = _cand(pole="p8", e="2025-01-06", e_ci=5)
    prev["retrigger"], prev["D"] = 0, "w"
    rn.stamp_overlap_open([prev, d], {("X", "w", "k5"): (True, 3, "degraded")})
    assert d["overlap_open"] == 1                                     # an unsettled previous trade is still open


def test_only_discovery_candidates_are_ever_walked():
    cs = [_cand(split="discovery"), _cand(split="holdout"), _cand(split="discovery")]
    assert [c["split"] for c in rn.select_close_variant_candidates(cs)] == ["discovery", "discovery"]


def _stamp_both(cs, extra_watch_poles=()):
    """Spec stamps + chain stamps; the chain's poles come from the candidates' own watch rows (+ extras)."""
    poles = {(c["ticker"], c["pole_ci"], c["pole_date"]) for c in cs} | set(extra_watch_poles)
    rn.stamp_retrigger(cs)
    rn.stamp_base_chain(cs, rn.chain_bases(poles))


def test_chain_key_merges_poles_that_drift_up_to_3_sessions_but_not_4():
    # the module's pole top walks forward inside ONE consolidation, so the spec key (pole_date) re-keys the base
    cs = [_cand(pole="p0", pole_ci=100, e="2025-04-01"),                       # C1 off on the first break
          _cand(pole="p1", pole_ci=102, e="2025-04-08", C1=True),             # pole top drifted 2 sessions
          _cand(pole="p2", pole_ci=105, e="2025-04-10", C1=True),             # +3 again: chained transitively
          _cand(pole="p3", pole_ci=109, e="2025-05-20"),                      # +4 from the last pole: a NEW base
          _cand(k="k10", pole="p1", pole_ci=102, e="2025-04-08"),             # another K: same base id, its own trade
          _cand(ticker="Y", pole="p1", pole_ci=102, e="2025-04-08")]          # another ticker
    _stamp_both(cs)
    assert [c["retrigger"] for c in cs[:4]] == [0, 0, 0, 0]                    # spec key: four poles = four 'trades'
    assert [c["retrigger_chain"] for c in cs[:4]] == [0, 1, 1, 0]
    assert cs[0]["base_id"] == cs[1]["base_id"] == cs[2]["base_id"] == "X|p0" and cs[3]["base_id"] == "X|p3"
    assert [c["first_chain_C1"] for c in cs[:3]] == [0, 1, 0]                  # C1's valid entry is the chain's 2nd break
    assert [c["first_chain_C0"] for c in cs[:3]] == [1, 0, 0]
    assert cs[4]["base_id"] == "X|p0" and cs[4]["retrigger_chain"] == 0        # K is part of the stamping key, not the id
    assert cs[5]["retrigger_chain"] == 0 and cs[5]["base_id"] == "Y|p1"


def test_chain_key_is_a_coarsening_of_the_spec_key_even_when_the_pole_alternates():
    # real data alternates between two poles night to night (BYND: 303, 287, 303). A walk over breakouts in E
    # order treats the revisit as a new chain; components over poles cannot: same pole_date -> same base.
    cs = [_cand(pole="a", pole_ci=303, e="2025-01-10"), _cand(pole="b", pole_ci=287, e="2025-01-11"),
          _cand(pole="a", pole_ci=303, e="2025-01-27"), _cand(pole="a", pole_ci=303, e="2025-01-28")]
    _stamp_both(cs)
    assert [c["retrigger"] for c in cs] == [0, 0, 1, 1]
    assert [c["retrigger_chain"] for c in cs] == [0, 0, 1, 1]
    assert all(c["retrigger_chain"] >= c["retrigger"] for c in cs)
    # a revisit whose own chain starts on ANOTHER pole date (first-pole-date ids would split it)
    ds = [_cand(pole="a", pole_ci=100, e="2025-01-02"), _cand(pole="b", pole_ci=102, e="2025-01-03"),
          _cand(pole="z", pole_ci=200, e="2025-01-04"), _cand(pole="b", pole_ci=102, e="2025-01-06")]
    _stamp_both(ds)
    assert [c["retrigger"] for c in ds] == [0, 0, 0, 1] and [c["retrigger_chain"] for c in ds] == [0, 1, 0, 1]


def test_a_watch_only_pole_in_between_joins_two_breakout_poles_into_one_base():
    cs = [_cand(pole="a", pole_ci=100, e="2025-01-02"), _cand(pole="c", pole_ci=106, e="2025-01-09")]
    _stamp_both(cs)
    assert [c["retrigger_chain"] for c in cs] == [0, 0]                         # 6 apart, nothing between: two bases
    ds = [_cand(pole="a", pole_ci=100, e="2025-01-02"), _cand(pole="c", pole_ci=106, e="2025-01-09")]
    _stamp_both(ds, extra_watch_poles=[("X", 103, "b")])                        # the top really walked 100 -> 103 -> 106
    assert [c["retrigger_chain"] for c in ds] == [0, 1] and ds[0]["base_id"] == ds[1]["base_id"] == "X|a"


def test_overlap_open_remembers_the_longest_open_trade_not_the_latest():
    a = _cand(pole="p1", e="2025-01-02", e_ci=10)                    # open until session 40
    b = _cand(pole="p2", e="2025-01-09", e_ci=15)                    # opens inside a, is out by 17
    c = _cand(pole="p3", e="2025-02-03", e_ci=25)                    # b is long gone, a is still open
    d = _cand(pole="p4", e="2025-03-03", e_ci=45)                    # a ended at 40: free
    for x, dd in ((a, "d1"), (b, "d2"), (c, "d3"), (d, "d4")):
        x["retrigger"], x["D"] = 0, dd
    outcomes = {("X", "d1", "k5"): (True, 30, "trailed"), ("X", "d2", "k5"): (True, 2, "stopped"),
                ("X", "d3", "k5"): (True, 1, "stopped"), ("X", "d4", "k5"): (False, 0, None)}
    rn.stamp_overlap_open([a, b, c, d], outcomes)
    assert [x["overlap_open"] for x in (a, b, c, d)] == [0, 1, 1, 0]   # overwrite-with-latest read c as 0


def test_step0_prints_both_base_keys_and_the_go_no_go_under_each():
    cs = [_cand(pole="p0", pole_ci=100, e="2025-04-01", split="holdout"),
          _cand(pole="p1", pole_ci=102, e="2025-04-08", split="holdout", C1=True),     # drifted pole, same base
          _cand(ticker="Y", pole="q0", pole_ci=300, e="2025-05-01", split="holdout", C1=True)]
    _stamp_both(cs)
    for c in cs:
        c["gap_over_1adr"], c["pole_bad_high"] = False, 0
    cs[1]["pole_bad_high"] = 1
    txt = rn.step0_text(cs)
    assert "GO/NO-GO input, SPEC key (plan: C1 needs >= 30 holdout trades): k5: 2," in txt
    assert "GO/NO-GO input, CHAIN key (plan: C1 needs >= 30 holdout trades): k5: 1," in txt
    assert "-- SPEC key" in txt and "-- CHAIN key" in txt
    assert "non-retrigger C1 trades affected: holdout 1, discovery 0" in txt


# ═══ data integrity: holes, reused tickers, test symbols, future splits ═════════════════════════
def test_contiguous_window_mask_needs_130_consecutive_sessions():
    cidx = np.arange(300)
    cidx[150:] += 7                                                  # 7 sessions missing between bar 149 and 150
    m = rn.contiguous_window_mask(cidx, 130)
    assert not m[:129].any()                                         # no full window yet
    assert m[129:150].all() and not m[150:279].any() and m[279:].all()   # a window containing the hole fails
    assert rn.contiguous_window_mask(np.arange(200), 130)[129:].all()
    assert not rn.contiguous_window_mask(np.arange(100), 130).any()


def _reused_ticker_bars(n=330, jump_at=200, scale=8.0):
    """One series that is really TWO companies: $20-ish, then (after the missing sessions) 8x the price."""
    b = _walk(n, 11)
    f = np.ones(n)
    f[jump_at:] = scale
    return cb.daily_bars_from_arrays(b.dates, b.o * f, b.h * f, b.l * f, b.c * f, b.v)


def test_a_hole_in_the_130_bar_window_is_a_history_failure_and_rs_never_spans_it():
    b = _reused_ticker_bars()
    n = len(b)
    cidx = np.arange(n)
    cidx[200:] += 4                                                  # 4 sessions missing between bar 199 and 200
    r = rn.scan_ticker("HOLE", b, cidx, [], "CS", 0)
    ctl = rn.scan_ticker("HOLE", b, np.arange(n), [], "CS", 0)       # same bars, no hole
    hist = sum(v for (_y, g), v in r["counts"].items() if g == "history")
    assert sum(r["counts"].values()) == n == sum(ctl["counts"].values())     # every night still lands in ONE row
    assert hist > 0 and not any(g == "history" for (_y, g) in ctl["counts"])
    # members: windows wholly before the hole (bars 129..199) or wholly after it (bar >= 200 + 129)
    idx_of_ci = {int(c): k for k, c in enumerate(cidx)}
    members = [idx_of_ci[int(c)] for c in r["uni_ci"]]
    assert members and all(129 <= i <= 199 or i >= 329 for i in members)
    assert hist == len(ctl["uni_ci"]) - len(r["uni_ci"])             # the nights the hole removed are the 'history' row
    # the glued series reads r126 ~ +700% across the hole; no admitted night does
    assert np.nanmax(np.abs(ctl["rs"][:, 2])) > 5.0 and np.nanmax(np.abs(r["rs"][:, 2])) < 1.0
    assert all(w["ci"] in set(int(c) for c in r["uni_ci"]) for w in r["watch"])


def test_exchange_test_symbols_are_never_universe_members():
    for t in ("ZVZZT", "ZTEST", "NTEST", "PTEST", "ZBZX", "ZXZZT", "ZAZZT", "ZWZZT", "ZJZZT", "ZIEXT", "ZEXIT",
              "ZXIET", "ATEST", "CTEST", "MTEST", "ZVZZC"):
        assert rn.is_test_symbol(t), t
    for t in ("ZION", "ZIM", "ZBH", "ZETA", "ZZZ", "AAPL", "TEST", "ZVZZ", "ZVZZTX", "SZZL"):
        assert not rn.is_test_symbol(t), t
    b = _walk(300, 5)                                                 # liquid, ~$20, unknown type: universe_ok alone admits it
    real = rn.scan_ticker("ZION", b, np.arange(300), [], "", 0)
    test = rn.scan_ticker("ZVZZT", b, np.arange(300), [], "", 0)
    assert len(real["uni_ci"]) > 0
    assert len(test["uni_ci"]) == 0 and not test["watch"] and sum(test["counts"].values()) == 300
    assert test["counts"][(2025, "universe_fail")] + test["counts"].get((2026, "universe_fail"), 0) == 300


def test_a_split_executing_after_the_data_ends_is_not_in_the_adjusted_series(tmp_path):
    sp = tmp_path / "s.psv"
    sp.write_text("LU|2026-10-23|10|1\nAMTD|2026-10-19|1|60\nKEEP|2026-10-16|1|2\nOLD|2024-01-02|8|1\n")
    last = dt.date(2026, 10, 16)
    got = rn.load_splits(sp, through=last)
    assert "LU" not in got and "AMTD" not in got                      # execute after the last session
    assert got["KEEP"] == [(last, 2.0)] and got["OLD"] == [(dt.date(2024, 1, 2), 0.125)]   # ON the last session: kept
    assert set(rn.load_splits(sp)) == {"LU", "AMTD", "KEEP", "OLD"}   # no cutoff: everything
    dates = _weekdays(10, dt.date(2026, 10, 5))
    assert (rn.factor_by_bar(dates, got.get("LU", [])) == 1.0).all()  # raw = adjusted for LU on every bar
    assert (rn.factor_by_bar(dates, rn.load_splits(sp)["LU"]) == 0.1).all()   # the bug: raw price / 10 on every bar


def test_fwd_end_stops_before_the_first_bar_that_follows_a_missing_session():
    cidx = np.array([0, 1, 2, 3, 5, 6, 7, 8])                         # session 4 missing: bar 4 follows the hole
    assert rn.fwd_end(cidx, 1, 8) == (4, True)                        # bars 2, 3 kept
    assert rn.fwd_end(cidx, 5, 8) == (8, False)                       # no hole after e
    assert rn.fwd_end(cidx, 1, 3) == (3, False)                       # the hole is beyond the requested window
    assert rn.fwd_end(cidx, 7, 8) == (8, False)                       # nothing after e
    assert rn.fwd_end(cidx, 3, 8) == (4, True)                        # hole right after e: empty walk


def test_watch_rows_carry_the_pole_calendar_index_and_the_bad_high_ratio():
    b = _fixture_bars()["MRNA"]
    cidx = np.arange(len(b)) + 5
    r = rn.scan_ticker("MRNA", b, cidx, [], "CS", 5)
    w = next(w for w in r["watch"] if w["watch_date"] == "2026-09-16")
    P = w["pole_idx"]
    assert w["pole_ci"] == int(cidx[P])
    assert w["pole_hi_over_oc"] == pytest.approx(w["pole_high"] / max(b.o[P], b.c[P])) and w["pole_hi_over_oc"] >= 1.0
    h = b.h.copy()
    h[P] *= 1.5                                                       # a bad high print on the pole bar
    bad = cb.daily_bars_from_arrays(b.dates, b.o, h, b.l, b.c, b.v)
    w2 = next(w for w in rn.scan_ticker("MRNA", bad, cidx, [], "CS", 5)["watch"] if w["watch_date"] == "2026-09-16")
    assert w2["pole_idx"] == P and w2["pole_hi_over_oc"] > rn.POLE_BAD_HIGH_X


# ═══ the CLOSE variant wiring (E alignment, closes_before, fwd window) ══════════════════════════
def _close_bars():
    n = 220
    d = _weekdays(n)
    o = np.full(n, 10.0)
    h, l, c = o * 1.01, o * 0.99, o.copy()
    e = 150
    o[e], h[e], l[e], c[e] = 10.2, 10.9, 10.1, 10.8              # E: closes 10.8 above the 10.5 pivot, low 10.1
    # forward: flat at 10.8 for 5 sessions, then a gap below the stop (10.1) -> stop_only books the gap open
    for j in range(1, 6):
        o[e + j], h[e + j], l[e + j], c[e + j] = 10.8, 10.9, 10.7, 10.8
    o[e + 6], h[e + 6], l[e + 6], c[e + 6] = 9.5, 9.6, 9.4, 9.5
    return cb.daily_bars_from_arrays(d, o, h, l, c, np.full(n, 1e6)), e


def _close_cand(bars, e, **kw):
    c = {"E_i": e, "E": bars.dates[e].isoformat(), "D": bars.dates[e - 1].isoformat(), "pivot": 10.5,
         "adr20": 0.10, "K": "k5", "pole_date": "p", "retrigger": 0}
    for name in rn.CELL_NAMES:
        c[name], c["first_" + name] = False, 0
    c.update(kw)
    return c


def test_close_variant_rows_walk_the_next_session_onward_and_cover_every_arm():
    bars, e = _close_bars()
    (row,) = rn.close_variant_rows("T", bars, [_close_cand(bars, e)])
    assert row["close_status"] == "filled"
    assert row["close_fill"] == pytest.approx(10.8 * (1 + cb.ENTRY_SLIPPAGE_PCT))
    assert row["close_stop"] == pytest.approx(10.1)                        # E's own low
    risk = row["close_fill"] - row["close_stop"]
    assert row["st_stop_only"] == "stopped" and row["held_stop_only"] == 6
    assert row["r_stop_only"] == pytest.approx((9.5 - row["close_fill"]) / risk)       # the gap open, session E+6
    assert row["fwd_bars"] == len(bars) - e - 1                          # 69 left, fewer than horizon + 1
    for name in cb.ARMS:
        assert row[f"st_{name}"] and row[f"r_{name}"] is not None
    assert row["acct_stop_only"] == pytest.approx(rn.acct_pct(row["r_stop_only"], row["close_width_pct"]))


def test_close_variant_refuses_a_misaligned_breakout_day_and_records_non_triggers():
    bars, e = _close_bars()
    with pytest.raises(AssertionError):
        rn.close_variant_rows("T", bars, [_close_cand(bars, e, E=bars.dates[e + 1].isoformat())])
    (row,) = rn.close_variant_rows("T", bars, [_close_cand(bars, e, pivot=10.9)])      # close 10.8 <= 10.9
    assert row["close_status"] == "no_trigger" and "st_stop_only" not in row


def test_close_variant_walk_stops_at_a_hole_and_ends_degraded():
    bars, e = _close_bars()
    cand = _close_cand(bars, e)
    (plain,) = rn.close_variant_rows("T", bars, [cand])
    (same,) = rn.close_variant_rows("T", bars, [cand], np.arange(len(bars)))      # contiguous: identical to no cidx
    assert same == plain and same["fwd_hole"] == 0 and plain["st_stop_only"] == "stopped"
    cidx = np.arange(len(bars))
    cidx[e + 4:] += 3                                                 # three sessions missing after E+3
    (cut,) = rn.close_variant_rows("T", bars, [cand], cidx)
    assert cut["fwd_hole"] == 1 and cut["fwd_bars"] == 3 and cut["fwd_last_date"] == bars.dates[e + 3].isoformat()
    assert cut["close_status"] == "filled"
    for name in cb.ARMS:                                               # the stop-out after the hole is never booked
        assert cut[f"st_{name}"] == "degraded", name
    with pytest.raises(AssertionError):                                # D's 130-bar window must be consecutive
        bad = np.arange(len(bars))
        bad[e - 5:] += 2
        rn.close_variant_rows("T", bars, [cand], bad)


# ═══ cross-section ═════════════════════════════════════════════════════════════════════════════
def test_cross_section_ranks_groups_and_nulls_small_groups():
    n = 12
    r21 = [float(k) for k in range(n)]
    r63 = [float(k) for k in range(n)]
    r126 = [float(n - k) for k in range(n)]
    r126[3] = None
    groups = ["A"] * 10 + ["B"] * 2                                   # B has 2 members: dropped (min 10)
    best, allp, grp, n_groups = rn.cross_section_one_date(r21, r63, r126, groups)
    assert n_groups == 1 and grp[:10] == [0.0] * 10 and grp[10:] == [None, None]    # one group -> pos 0 of max(n-1,1)
    p21 = cb.percentile_ranks(r21)
    p126 = cb.percentile_ranks(r126)
    assert best[11] == max(p21[11], cb.percentile_ranks(r63)[11], p126[11])
    assert allp[3] is None                                             # a missing horizon -> no "all three" claim
    assert best[3] == max(p21[3], cb.percentile_ranks(r63)[3])         # but rs_best uses what exists
    best2, _, grp2, _ = rn.cross_section_one_date(r21[:2], r63[:2], r126[:2], [None, "A"])
    assert grp2 == [None, None] and len(best2) == 2


# ═══ file loaders ══════════════════════════════════════════════════════════════════════════════
def test_loaders_dedupe_splits_keep_leading_zero_sic_and_read_regimes(tmp_path):
    sp = tmp_path / "splits.psv"
    sp.write_text("AAA|2023-05-01|1|10\nAAA|2023-05-01|1|10\nBBB|2024-01-02|8|1\n")
    assert rn.load_splits(sp) == {"AAA": [(dt.date(2023, 5, 1), 10.0)], "BBB": [(dt.date(2024, 1, 2), 0.125)]}
    sic = tmp_path / "sic.psv"
    sic.write_text("AAA|2026-10-16|200|0100|AGRICULTURAL PRODUCTION|CS\nBBB|2026-10-16|200||x|ADRC\nCCC|2026-10-16|404|||\n")
    by, typ = rn.load_sic(sic)
    assert by == {"AAA": "01", "BBB": None, "CCC": None} and typ["BBB"] == "ADRC"
    sm = tmp_path / "small.psv"
    sm.write_text("sectype|AAA|CS|XNYS\nregime|2025-03-03|Correcting|\nregime|2025-03-04|Bull|1.2\n")
    types, reg = rn.load_small(sm)
    assert types == {"AAA": "CS"} and reg[dt.date(2025, 3, 4)] == "Bull"


# ═══ fetch_minutes helpers ═════════════════════════════════════════════════════════════════════
class TestFetchMinutes:
    ET = fm._ET

    def test_minute_offsets_cover_0930_to_1559_et_across_dst(self):
        for d in (dt.date(2025, 1, 15), dt.date(2025, 7, 15)):             # EST and EDT
            at = lambda h, m: dt.datetime(d.year, d.month, d.day, h, m, tzinfo=self.ET)
            assert fm.minute_since_open(at(9, 30)) == 0
            assert fm.minute_since_open(at(15, 59)) == 389
            assert fm.minute_since_open(at(16, 0)) is None and fm.minute_since_open(at(9, 29)) is None
            assert fm.minute_since_open(at(9, 31).astimezone(dt.timezone.utc)) == 1     # UTC in, ET out
        with pytest.raises(ValueError):
            fm.minute_since_open(dt.datetime(2025, 1, 15, 9, 30))

    def test_window_is_tz_aware_et_session(self):
        s, e = fm.window(dt.date(2025, 7, 15))
        assert s.tzinfo is not None and (s.hour, s.minute) == (9, 30) and (e.hour, e.minute) == (16, 0)
        assert s.utcoffset() == dt.timedelta(hours=-4)

    def test_parse_list_accepts_both_separators_header_and_tier(self, tmp_path):
        p = tmp_path / "l.tsv"
        p.write_text("ticker\tdate\ttier\nAAA\t2025-03-03\t1\nBBB\t2025-03-03\t0\nAAA|2025-03-04|0\nAAA\t2025-03-03\t1\n")
        assert fm.parse_list(p) == {dt.date(2025, 3, 3): ["AAA", "BBB"], dt.date(2025, 3, 4): ["AAA"]}
        assert fm.parse_list(p, min_tier=1) == {dt.date(2025, 3, 3): ["AAA"]}

    def test_resume_log_and_multi_member_gzip_round_trip(self, tmp_path):
        class Bar:
            def __init__(self, ts, px):
                self.timestamp, self.open, self.high, self.low, self.close, self.volume = ts, px, px + 1, px - 1, px, 100
        t0 = dt.datetime(2025, 3, 3, 14, 30, tzinfo=dt.timezone.utc)        # 09:30 ET
        rows = fm.format_rows("AAA", [Bar(t0, 10.0), Bar(t0 + dt.timedelta(minutes=1), 11.0),
                                      Bar(t0 - dt.timedelta(minutes=1), 9.0)])    # pre-open bar dropped
        assert rows == ["AAA|0|10.0|11.0|9.0|10.0|100", "AAA|1|11.0|12.0|10.0|11.0|100"]
        f = tmp_path / "2025-03-03.psv.gz"
        fm._append_gz(f, rows[:1])
        fm._append_gz(f, rows[1:])                                           # a second gzip member
        assert gzip.open(f, "rt").read().splitlines() == rows
        (tmp_path / fm.DONE_NAME).write_text("2025-03-03|AAA|2|ok\n2025-03-03|BBB|0|empty\nbad line\n")
        assert fm.load_done(tmp_path) == {(dt.date(2025, 3, 3), "AAA"), (dt.date(2025, 3, 3), "BBB")}
        assert list(fm.chunks(list("abcde"), 2)) == [["a", "b"], ["c", "d"], ["e"]]

    def test_repair_gz_keeps_complete_members_and_drops_a_truncated_tail(self, tmp_path):
        f = tmp_path / "2025-03-03.psv.gz"
        fm._append_gz(f, ["AAA|0|1|1|1|1|1"])
        fm._append_gz(f, ["BBB|0|2|2|2|2|2"])
        clean = f.read_bytes()
        assert fm.repair_gz(f) == 0 and f.read_bytes() == clean            # a clean file is left alone
        assert fm.repair_gz(tmp_path / "missing.psv.gz") == 0
        third = gzip.compress(b"CCC|0|3|3|3|3|3\n", mtime=0)
        f.write_bytes(clean + third[:len(third) // 2])                      # killed halfway through the third member
        with pytest.raises(EOFError):                                       # the reader dies at the tail, losing later data too
            gzip.open(f, "rt").read()
        assert fm.repair_gz(f) == len(third) // 2
        assert gzip.open(f, "rt").read().splitlines() == ["AAA|0|1|1|1|1|1", "BBB|0|2|2|2|2|2"]
        fm._append_gz(f, ["CCC|0|3|3|3|3|3"])                               # the re-fetch appends cleanly now
        assert gzip.open(f, "rt").read().splitlines() == ["AAA|0|1|1|1|1|1", "BBB|0|2|2|2|2|2", "CCC|0|3|3|3|3|3"]
        f.write_bytes(clean + b"\x1f\x8bjunk-not-a-gzip-member")           # garbage after the last good member
        assert fm.repair_gz(f) > 0 and f.read_bytes() == clean
        f.write_bytes(third[:7])                                            # nothing complete at all
        assert fm.repair_gz(f) == 7 and f.read_bytes() == b""

    def test_fetch_date_repairs_a_truncated_date_file_before_appending(self, tmp_path, monkeypatch):
        class Bar:
            def __init__(self, ts, px):
                self.timestamp, self.open, self.high, self.low, self.close, self.volume = ts, px, px + 1, px - 1, px, 100

        class Resp:
            data = {"BBB": [Bar(dt.datetime(2025, 3, 3, 14, 30, tzinfo=dt.timezone.utc), 5.0)]}   # 09:30 ET

        class Client:
            def get_stock_bars(self, _req):
                return Resp()

        monkeypatch.setattr(fm, "_request", lambda syms, d: None)           # no alpaca-py request object needed
        d = dt.date(2025, 3, 3)
        f = tmp_path / "2025-03-03.psv.gz"
        fm._append_gz(f, ["AAA|0|1.0|2.0|0.0|1.0|100"])
        third = gzip.compress(b"CCC|0|3|3|3|3|3\n", mtime=0)
        f.write_bytes(f.read_bytes() + third[:10])                          # a previous run died mid-append
        logs = []
        assert fm.fetch_date(Client(), d, ["BBB"], tmp_path, 50, 0.0, logs.append) == (1, 0, 0)
        assert gzip.open(f, "rt").read().splitlines() == ["AAA|0|1.0|2.0|0.0|1.0|100", "BBB|0|5.0|6.0|4.0|5.0|100"]
        assert any("truncated" in m for m in logs) and (d, "BBB") in fm.load_done(tmp_path)

    def test_dry_run_needs_no_credentials_and_skips_done_pairs(self, tmp_path, monkeypatch, capsys):
        for k in ("ALPACA_API_KEY", "ALPACA_SECRET_KEY", "ALPACA_PAPER_API_KEY", "ALPACA_PAPER_SECRET_KEY"):
            monkeypatch.delenv(k, raising=False)
        lst = tmp_path / "l.psv"
        lst.write_text("AAA|2025-03-03\nBBB|2025-03-03\nAAA|2025-03-04\n")
        out = tmp_path / "out"
        out.mkdir()
        (out / fm.DONE_NAME).write_text("2025-03-03|AAA|390|ok\n")
        fm.main(["--list", str(lst), "--out", str(out), "--dry-run"])
        assert "to fetch 2 pairs over 2 dates" in capsys.readouterr().err


# ═══════════════════════════════════════════════════════════════════════════════════════════════
# P2b - the MINUTE STAGE (entries, exits, controls, sensitivities, holdout firewall, report)
# ═══════════════════════════════════════════════════════════════════════════════════════════════
import inspect  # noqa: E402
from collections import Counter  # noqa: E402

from agents.market_intelligence import anticipation as ant  # noqa: E402


def _e_day_minutes():
    """One breakout session, minute by minute (390 rows). pivot 10.25: orh1/pivot fill at minute 1, orh5 at minute 7
    (level ORH5 = 10.30), orh60 never triggers (ORH60 = 10.60 is the session high). Session high 10.60, low 10.15."""
    rows = []
    for m in range(390):
        if m == 0:
            rows.append((m, 10.20, 10.25, 10.15, 10.22))
        elif 1 <= m <= 4:
            rows.append((m, 10.25, 10.30 if m == 3 else 10.28, 10.20, 10.25))
        elif m in (5, 6):
            rows.append((m, 10.28, 10.29, 10.25, 10.28))
        elif m == 7:
            rows.append((m, 10.29, 10.35, 10.28, 10.34))
        elif m < 20:
            rows.append((m, 10.34, 10.40, 10.30, 10.38))
        elif m == 20:
            rows.append((m, 10.40, 10.60, 10.38, 10.58))
        else:
            rows.append((m, 10.55, 10.58, 10.50, 10.55))
    return rows


def _minute_lines(ticker, rows=None):
    return [f"{ticker}|{m}|{o}|{h}|{l}|{c}|1000" for m, o, h, l, c in (rows or _e_day_minutes())]


def _mb(rows=None):
    rows = rows or _e_day_minutes()
    return cb.minute_bars_from_lists([r[0] for r in rows], [r[1] for r in rows], [r[2] for r in rows],
                                     [r[3] for r in rows], [r[4] for r in rows], [1000.0] * len(rows))


DISCOVERY_START = dt.date(2023, 1, 2)       # a discovery candidate's D must be <= 2024-12-31 (read_candidates checks it)


def _e_bars(n=220, e=150, tail=None, start=None):
    """Flat $10 history, then E (high 10.60 / low 10.15, close 10.55), then forward days: d1 runs to 10.85; d2 dips to
    10.25 (inside the fill, above the entry stop 10.15); d3 gaps down to 9.50; flat 9.50 after. Starts 2025-01-06
    (holdout-era dates) unless `start` says otherwise."""
    d = _weekdays(n) if start is None else _weekdays(n, start)
    o = np.full(n, 10.0)
    h, l, c = o * 1.01, o * 0.99, o.copy()
    o[e], h[e], l[e], c[e] = 10.20, 10.60, 10.15, 10.55
    fwd = tail or [(10.60, 10.85, 10.50, 10.80), (10.70, 10.75, 10.25, 10.70), (9.50, 9.60, 9.40, 9.50)]
    for j in range(1, n - e):
        oo, hh, ll, cc = fwd[j - 1] if j <= len(fwd) else (9.50, 9.60, 9.40, 9.50)
        o[e + j], h[e + j], l[e + j], c[e + j] = oo, hh, ll, cc
    return cb.daily_bars_from_arrays(d, o, h, l, c, np.full(n, 1e6)), e


def _m_cand(bars, e, **kw):
    c = {"ticker": "X", "D": bars.dates[e - 1].isoformat(), "E": bars.dates[e].isoformat(), "K": "k5", "split": "discovery",
         "pole_date": "p", "base_id": "X|p", "apollo_regime": "", "pivot": 10.25, "adr20": 0.10, "high_E": 10.60,
         "low_E": 10.15, "open_E": 10.20, "close_E": 10.55, "atr14": 0.05, "median_dollar_vol20": 5e7,
         "retrigger": 0, "retrigger_chain": 0, "pole_bad_high": 0, "gap_over_1adr": False, "phase_qqq_10_20": True,
         "phase_qqq_10_20_s5": True, "phase_spy_qqq_50": False, "inside_day": False}
    for name in rn.CELL_COLS:
        c[name] = name in ("C0", "C1")
    for name in rn.CELL_NAMES:
        c["first_" + name], c["first_chain_" + name] = 1, 1
    c.update(kw)
    return c


def _eval(bars=None, e=None, minutes=None, **kw):
    if bars is None:
        bars, e = _e_bars()
    cidx = np.arange(len(bars))
    c = _m_cand(bars, e, **kw)
    res = rn.evaluate_candidate(c, bars, cidx, e, minutes if minutes is not None else _mb(), list(bars.dates), len(bars) - 1)
    return c, bars, e, {r["variant"]: r for r in res}


# ═══ the minute reader ═══════════════════════════════════════════════════════════════════════════
class TestMinuteReader:
    def test_the_last_block_per_date_and_ticker_wins_across_gzip_members(self, tmp_path):
        f = tmp_path / "2025-03-03.psv.gz"
        fm._append_gz(f, ["AAA|0|1|1|1|1|1", "AAA|1|1|1|1|1|1", "BBB|0|2|2|2|2|2"])
        fm._append_gz(f, ["CCC|0|3|3|3|3|3"])
        fm._append_gz(f, ["AAA|0|9|9|9|9|9", "AAA|1|9|9|9|9|9", "AAA|2|9|9|9|9|9"])      # a resumed fetch re-did AAA
        blocks, info = rn.read_minute_file(f)
        assert [r[2] for r in blocks["AAA"]] == ["9", "9", "9"]                          # the LAST block, not the first
        assert [r[2] for r in blocks["BBB"]] == ["2"] and [r[2] for r in blocks["CCC"]] == ["3"]
        assert info["refetched"] == 1 and not info["truncated"]
        only, _ = rn.read_minute_file(f, {"BBB"})
        assert set(only) == {"BBB"}                                                      # the want-filter skips the rest

    def test_a_ticker_in_two_consecutive_members_is_a_refetch_the_second_replaces_and_bad_lines_are_counted(self, tmp_path):
        f = tmp_path / "d.psv.gz"
        fm._append_gz(f, ["AAA|0|1|1|1|1|1", "AAA|1|1|1|1|1|1"])
        fm._append_gz(f, ["AAA|2|1|1|1|1|1", "not a row"])
        blocks, info = rn.read_minute_file(f)
        # the fetcher writes ONE member per symbol per fetch, so the second member is a re-fetch: it REPLACES, never extends
        assert [r[1] for r in blocks["AAA"]] == ["2"] and info["bad_lines"] == 1 and info["refetched"] == 1

    def test_a_crash_resume_refetch_right_after_the_tickers_own_member_is_one_390_row_block_and_usable(self, tmp_path):
        """The reviewer's repro: SSS's member was written, the crash lost its done-line, and the resume re-fetches SSS FIRST,
        so the new member directly follows the old one. Merged, the 780 rows fail validation (duplicate minutes) and a
        fetched pair becomes an `invalid` -> no_minutes data abstain; replaced, it is the new 390-row block."""
        f = tmp_path / "2023-01-12.psv.gz"
        fm._append_gz(f, [f"AAA|{m}|1|1|1|1|1" for m in range(390)])           # done-line written
        fm._append_gz(f, [f"SSS|{m}|5|5|5|5|5" for m in range(390)])           # member written, crash before its done-line
        fm._append_gz(f, [f"SSS|{m}|6|6|6|6|6" for m in range(390)])           # resume: SSS is the first not-done ticker
        (tmp_path / "_done.psv").write_text("2023-01-12|AAA|390|ok\n2023-01-12|SSS|390|ok\n")
        blocks, info = rn.read_minute_file(f)
        assert len(blocks["SSS"]) == 390 and {r[2] for r in blocks["SSS"]} == {"6"}        # the LAST fetch, once
        assert len(blocks["AAA"]) == 390 and info["refetched"] == 1
        mb, state = rn.minutes_for(blocks, rn.load_done_pairs(tmp_path), "2023-01-12", "SSS")
        assert state == "ok" and mb is not None
        only, _ = rn.read_minute_file(f, {"SSS"})                                           # the want-filter path agrees
        assert len(only["SSS"]) == 390 and set(only) == {"SSS"}
        # a multi-ticker member is still read by runs inside the member, and a re-fetch of one of its tickers wins
        g = tmp_path / "2023-01-13.psv.gz"
        fm._append_gz(g, ["AAA|0|1|1|1|1|1", "AAA|1|1|1|1|1|1", "BBB|0|2|2|2|2|2"])
        fm._append_gz(g, ["BBB|0|7|7|7|7|7", "BBB|1|7|7|7|7|7"])
        gb, _ = rn.read_minute_file(g)
        assert len(gb["AAA"]) == 2 and [r[2] for r in gb["BBB"]] == ["7", "7"]

    def test_a_truncated_tail_member_is_dropped_and_every_complete_member_before_it_is_kept(self, tmp_path):
        f = tmp_path / "d.psv.gz"
        fm._append_gz(f, ["AAA|0|1|1|1|1|1"])
        third = gzip.compress(("BBB|0|2|2|2|2|2\n" * 400).encode(), mtime=0)
        f.write_bytes(f.read_bytes() + third[:len(third) // 2])
        blocks, info = rn.read_minute_file(f)
        assert info["truncated"] is True and "AAA" in blocks and "BBB" not in blocks
        f.write_bytes(f.read_bytes()[:len(f.read_bytes()) - len(third) // 2] + b"\x1f\x8bjunk")           # garbage after the good member
        assert rn.read_minute_file(f)[1]["truncated"] and "AAA" in rn.read_minute_file(f)[0]

    def test_minutes_for_distinguishes_pending_from_an_abstain(self):
        blocks = {"AAA": [list(map(str, ("AAA", 0, 1, 1, 1, 1, 1))), list(map(str, ("AAA", 1, 1, 1, 1, 1, 1)))],
                  "BAD": [list(map(str, ("BAD", 5, 1, 1, 1, 1, 1))), list(map(str, ("BAD", 5, 1, 1, 1, 1, 1)))]}
        done = {("2025-03-03", "AAA"): "ok", ("2025-03-03", "BAD"): "ok", ("2025-03-03", "EMPTY"): "empty"}
        assert rn.minutes_for(blocks, done, "2025-03-03", "AAA")[1] == "ok"
        assert rn.minutes_for(blocks, done, "2025-03-03", "BAD") == (None, "invalid")       # duplicate minutes
        assert rn.minutes_for(blocks, done, "2025-03-03", "EMPTY") == (None, "no_rows")     # fetched, nothing came back
        assert rn.minutes_for(blocks, done, "2025-03-03", "NEVER") == (None, "pending")     # not fetched yet: skipped
        assert rn.minutes_for(blocks, None, "2025-03-03", "NEVER") == (None, "pending")     # no _done.psv: absent = pending
        assert rn.minutes_for(blocks, None, "2025-03-03", "AAA")[1] == "ok"


# ═══ maturity / account % / bootstrap ════════════════════════════════════════════════════════════
class TestMaturity:
    def test_terminal_and_horizon_statuses(self):
        H = cb.EXIT_HORIZON
        for st in ("stopped", "stopped_day0", "trailed", "target", "time_exit"):
            assert rn.is_mature(st, 3, H)                                    # a terminal exit before the data end
        assert not rn.is_mature("degraded", H + 1, H)                        # forward bars ran out: an open mark
        assert rn.is_mature("censored", H + 1, H)                            # horizon reached with the next open behind it
        assert not rn.is_mature("censored", H, H)                            # marked at the horizon close, no next open: open mark
        assert not rn.is_mature("censored", 60, H)

    def test_a_walk_cut_at_a_hole_is_an_open_mark_and_a_stop_before_it_is_mature(self):
        c, bars, e, vr = _eval()
        cidx = np.arange(len(bars))
        cidx[e + 6:] += 3                                                   # three sessions missing after E+5: the stop at E+3 is first
        cut = rn.evaluate_candidate(c, bars, cidx, e, _mb(), list(bars.dates) + [bars.dates[-1]] * 4, len(bars) + 2)
        arms = {r["variant"]: r for r in cut}["orh5"]["arms"]
        assert arms[cb.PRIMARY_ARM]["mature"] is True and arms[cb.PRIMARY_ARM]["status"] == "stopped"
        d, e2 = _e_bars(tail=[(10.75 + 0.01 * j, 10.90 + 0.01 * j, 10.70 + 0.01 * j, 10.80 + 0.01 * j) for j in range(9)])   # never stopped or trailed: the walk reaches the cut
        cidx2 = np.arange(len(d))
        cidx2[e2 + 4:] += 3                                                 # hole after E+3: the walk ends degraded
        cut2 = rn.evaluate_candidate(_m_cand(d, e2), d, cidx2, e2, _mb(), list(d.dates) + [d.dates[-1]] * 4, len(d) + 2)
        a = {r["variant"]: r for r in cut2}["orh5"]["arms"][cb.PRIMARY_ARM]
        assert a["status"] == "degraded" and a["mature"] is False and a["open_mark"] is True

    def test_arm_result_carries_the_labels(self):
        res = {"status": "stopped", "realized_r": -1.0, "pnl_adr": -0.2, "sessions_held": 2, "events": [(1, "partial", 1, .3), (2, "be_above_close", 1, 0.0)]}
        a = rn.arm_result(res, width=0.05, n_fwd=10)
        assert a["mature"] is True and a["open_mark"] is False and a["beabove"] == 1
        assert a["acct_pct"] == pytest.approx(rn.acct_pct(-1.0, 0.05))


class TestBootstrap:
    def test_deterministic_per_key_and_independent_of_call_order(self):
        rng = np.random.default_rng(3)
        v = rng.normal(0.3, 2.0, 120)
        months = np.array([f"2023-{1 + k % 12:02d}" for k in range(120)])
        a1 = rn.block_bootstrap_ci(v, months, key="g1")
        b1 = rn.block_bootstrap_ci(v, months, key="g2")
        a2 = rn.block_bootstrap_ci(v, months, key="g1")
        assert a1 == a2 and a1 != b1                                        # same key -> same stream; another key -> its own
        assert a1[0] < v.mean() < a1[1]

    def test_it_resamples_whole_months_not_trades(self):
        v = np.array([1.0, 1.0, 1.0, 5.0])
        months = np.array(["a", "a", "a", "b"])
        lo, hi = rn.block_bootstrap_ci(v, months, key="x", draws=4000)
        assert lo == pytest.approx(1.0) and hi == pytest.approx(5.0)         # only {all a, all b, mixed} means are reachable
        one = rn.block_bootstrap_ci(np.array([2.0, 4.0]), np.array(["m", "m"]), key="y")
        assert one == (3.0, 3.0)                                            # one block: every resample is the sample
        assert all(x != x for x in rn.block_bootstrap_ci([], [], key="z"))

    def test_terciles_and_stats(self):
        cuts = rn.tercile_cuts(np.arange(1.0, 10.0))
        assert list(rn.tercile_of([1.0, 4.0, 9.0, float("nan")], cuts)) == [1, 2, 3, 0]
        s = rn.rstats([10.0, 5.0, 3.0, 1.0, 0.5, -1.0, -1.0], [1, 1, 1, 1, 1, 1, 1], [0.1] * 7)
        assert s["n"] == 7 and s["share_ge3"] == pytest.approx(3 / 7) and s["share_ge5"] == pytest.approx(2 / 7)
        assert s["share_ge10"] == pytest.approx(1 / 7) and s["mean_ex_top5"] == pytest.approx(-1.0)   # the two smallest remain
        assert rn.rstats([1.0, 2.0])["mean_ex_top5"] is None and rn.rstats([])["n"] == 0


# ═══ the candidate engine: entries, day-0, controls, sensitivities ═══════════════════════════════
class TestEngine:
    def test_variants_arms_and_row_alignment(self):
        c, bars, e, vr = _eval()
        assert {k: v["entry"]["status"] for k, v in vr.items()} == {"orh1": "filled", "orh5": "filled", "orh60": "no_trigger", "pivot": "filled"}
        assert vr["orh5"]["entry"]["fill_minute"] == 7 and vr["orh1"]["entry"]["fill_minute"] == 1
        assert vr["orh5"]["entry"]["stop"] == pytest.approx(10.15)
        assert set(vr["orh5"]["arms"]) == set(rn.ALL_ARMS) and len(rn.ALL_ARMS) == len(cb.ARMS) + 2
        assert vr["orh60"]["arms"] == {}
        prefix = rn.cand_values(c)
        rows = [r for v in vr.values() for r in rn.trade_rows_for(c, v, prefix)]
        assert all(len(r) == len(rn.TRADE_COLS) for r in rows)
        assert sum(1 for r in rows if r[len(rn.TRADE_CAND_COLS)] == "orh5") == len(rn.ALL_ARMS)
        nt = [r for r in rows if r[len(rn.TRADE_CAND_COLS)] == "orh60"]
        assert len(nt) == 1 and nt[0][len(rn.TRADE_CAND_COLS) + len(rn.TRADE_VAR_COLS)] == ""        # one row, no arm
        assert len(rn.entry_row_for(c, vr["orh5"], "ok")) == len(rn.ENTRY_COLS)
        cb_arm = vr["orh5"]["arms"][cb.PRIMARY_ARM]
        assert cb_arm["status"] == "stopped" and cb_arm["mature"] and cb_arm["sessions_held"] == 3
        fill, stop = vr["orh5"]["entry"]["fill"], vr["orh5"]["entry"]["stop"]
        assert cb_arm["realized_r"] == pytest.approx((9.50 - fill) / (fill - stop))               # the d3 gap open, booked at the open

    def test_a_day0_stop_out_is_booked_once_for_every_arm_but_the_controls_walk_day0_themselves(self):
        rows = _e_day_minutes()
        rows = [r if r[0] != 12 else (12, 10.34, 10.40, 10.10, 10.30) for r in rows]      # minute 12 trades through the 10.15 stop
        bars, e = _e_bars()
        h = bars.h.copy(); l = bars.l.copy()
        l[e] = 10.10                                                                       # the daily low agrees with the minutes
        bars = cb.daily_bars_from_arrays(bars.dates, bars.o, h, l, bars.c, bars.v)
        c, bars, e, vr = _eval(bars, e, _mb(rows), low_E=10.10)
        ent = vr["orh5"]["entry"]
        assert ent["day0"]["stopped"] and ent["day0"]["exit_minute"] == 12
        want = cb.day0_result_to_outcome(ent, c["adr20"])
        for name in cb.ARMS:
            a = vr["orh5"]["arms"][name]
            assert a["status"] == "stopped_day0" and a["mature"] and a["realized_r"] == pytest.approx(want["realized_r"])
            assert a["sessions_held"] == 0
        fa = vr["orh5"]["arms"][rn.FAMILY_A_ARM]
        assert fa["status"] == "settled" and fa["realized_r"] < 0                           # stopped out in the minutes, by simulate's own walk

    def test_too_wide_abstain_gets_the_cap_not_skip_rerun(self):
        c, bars, e, vr = _eval(adr20=0.01)                                                  # a 1.5% stop is wider than a 1% ADR
        ent = vr["orh5"]["entry"]
        assert ent["status"] == "abstain" and ent["reason"] == "too_wide" and vr["orh5"]["arms"] == {}
        cap = vr["orh5"]["sens"]["cap"]
        assert cap["stop"] == pytest.approx(ent["fill"] * 0.99)
        assert cap["status"] == "stopped" and cap["mature"]                                  # d3 gap through the capped stop too
        want = (9.50 - ent["fill"]) / (ent["fill"] - cap["stop"])
        assert cap["realized_r"] == pytest.approx(want)
        rows = rn.trade_rows_for(c, vr["orh5"], rn.cand_values(c))
        assert len(rows) == 1                                                               # one row, no arm, carrying the cap columns
        row = dict(zip(rn.TRADE_COLS, rows[0]))
        assert row["arm"] == "" and row["status"] == "abstain" and row["abstain_reason"] == "too_wide"
        assert row["cap_acct_pct"] == pytest.approx(cap["acct_pct"]) and row["cap_realized_r"] == pytest.approx(cap["realized_r"])
        assert row["cap_stop"] == pytest.approx(cap["stop"]) and row["cap_mature"] == 1

    def test_horizon_60_atr14_floors_and_account_pct_are_recorded_per_row(self):
        c, bars, e, vr = _eval()
        prim = vr["orh5"]["arms"][cb.PRIMARY_ARM]
        h60 = vr["orh5"]["sens"]["h60"]
        assert h60["status"] == prim["status"] == "stopped" and h60["realized_r"] == pytest.approx(prim["realized_r"])
        width = vr["orh5"]["entry"]["width_pct"]
        assert rn.atr_wide_flag(width, 0.05) == 0 and rn.atr_wide_flag(width, 0.01) == 1 and rn.atr_wide_flag(None, 0.05) == ""
        assert rn.floor_flags(width, 0.10) == [0, 1, 1, 1, 1]                               # width 1.55%: under .25 x 10% = 2.5% and every wider floor
        assert rn.floor_flags(0.03, 0.10) == [0, 0, 1, 1, 1]                                # 3%: clears the .25 floor only
        assert rn.floor_flags(None, 0.10) == [""] * 5
        assert prim["acct_pct"] == pytest.approx(rn.acct_pct(prim["realized_r"], width))
        grind = [(10.75 + 0.01 * j, 10.90 + 0.01 * j, 10.70 + 0.01 * j, 10.80 + 0.01 * j) for j in range(70)]   # a slow climb: never stopped, never trailed
        d, e2 = _e_bars(tail=grind)                                                         # 120 > the 69 bars on disk, 60 < them
        c2, _b, _e, v2 = _eval(d, e2)
        assert v2["orh5"]["arms"][cb.PRIMARY_ARM]["mature"] is False                         # 120-session walk: forward bars ran out
        assert v2["orh5"]["sens"]["h60"]["mature"] is True and v2["orh5"]["sens"]["h60"]["status"] == "censored"


# ═══ the two controls on a hand-worked example ═══════════════════════════════════════════════════
class TestControls:
    def test_family_a_hand_worked(self):
        # fill = 10.30 x 1.001, stop 10.15: +1R = 10.4706 is touched at minute 20 (half out, +0.5R); +3R = 10.7912 on d1 (h 10.85)
        # takes the other half at +3R: 0.5 x 1 + 0.5 x 3 = 2.0R, out on forward day 1
        c, bars, e, vr = _eval()
        fa = vr["orh5"]["arms"][rn.FAMILY_A_ARM]
        assert fa["realized_r"] == pytest.approx(2.0) and fa["sessions_held"] == 1 and fa["mature"] and fa["status"] == "settled"
        ent = vr["orh5"]["entry"]
        assert fa["pnl_adr"] == pytest.approx(2.0 * (ent["fill"] - ent["stop"]) / (ent["fill"] * c["adr20"]))
        # the same call made by hand through the two shipped functions
        mb = _mb()
        md = rn.minute_dicts(mb)
        daily = [{"o": float(bars.o[e + j]), "h": float(bars.h[e + j]), "l": float(bars.l[e + j]), "c": float(bars.c[e + j])} for j in range(1, 6)]
        path = ant.build_mixed_path(md, rn.fill_position(mb, 7), daily)
        assert ant.simulate(ent["fill"], ent["stop"], path, ant.SETTLE_RULE, "pess")[0] == pytest.approx(fa["realized_r"])
        assert all(b["kind"] == "min" for b in path[:-5]) and path[0]["day_idx"] == 0 and path[-5]["kind"] == "day"

    def test_family_a_with_two_forward_bars_is_an_open_mark_unless_it_exited_earlier(self):
        c, bars, e, vr = _eval()
        ent = vr["orh5"]["entry"]
        mb = _mb()
        md, fp = rn.minute_dicts(mb), rn.fill_position(mb, 7)
        quiet = cb.daily_bars_from_arrays(bars.dates[:2], [10.6] * 2, [10.7] * 2, [10.5] * 2, [10.6] * 2, [1e6] * 2)
        a = rn.family_a_control(mdicts=md, fill_pos=fp, fwd=quiet, fill=ent["fill"], stop=ent["stop"], adr20=0.10)
        assert a["mature"] is False and a["status"] == "open_mark"                          # marked at the last close, not exited
        run = cb.daily_bars_from_arrays(bars.dates[:2], [10.6, 10.7], [10.85, 10.9], [10.5, 10.6], [10.8, 10.8], [1e6] * 2)
        b = rn.family_a_control(mdicts=md, fill_pos=fp, fwd=run, fill=ent["fill"], stop=ent["stop"], adr20=0.10)
        assert b["mature"] is True and b["realized_r"] == pytest.approx(2.0)                # out at day 1 < the 2 available days

    def test_apollo_walk_inputs_are_the_live_ladder_anchored_on_the_placed_risk(self):
        fill, stop = 10.3103, 10.15
        target, kw = rn.apollo_walk_inputs(fill, stop, 0.04)
        risk = fill - stop
        assert target == pytest.approx(fill + 4 * risk)                       # +8 ORB-R with 1 placed-risk R = 2 ORB-R
        assert kw["r_frame_ps"] == pytest.approx(risk / 2) and fill - 2 * kw["r_frame_ps"] == pytest.approx(stop)
        # recut.py CONTROL_KW (the precedent), minus the three keys walk_arm is given explicitly here
        assert kw["breakeven_at_r"] == 3.0 and kw["breakeven_at_partial"] is True and kw["trail_prior_closes"] is True
        assert kw["ladder_partial"] is False and kw["depth_exit"] is True and kw["depth_adr20_pct"] == 0.04
        rules = rn.apollo_rules()
        assert rules["intraday_partial_r"] == 8.0 and rules["exit_rule"] == "depth" and rules["close_below_sale"] == "next_open"

    def test_apollo_hand_worked_breakeven_scratch(self):
        # day 0: minute 20's high 10.60 >= fill + 1.5 x risk (10.5507) arms the breakeven at the fill. Day 1 runs
        # (10.50 .. 10.85, short of +4 R = 10.9515); day 2 trades down to 10.25 - inside the fill, above the CB stop 10.15 -
        # so the live ladder is stopped at breakeven (R = 0.0) while the CB stop-only arm is still in the trade.
        c, bars, e, vr = _eval()
        ent = vr["orh5"]["entry"]
        ap = vr["orh5"]["arms"][rn.APOLLO_ARM]
        assert ap["status"] == "settled" and ap["mature"] and ap["note"] == "stop_hit"
        assert ap["realized_r"] == pytest.approx(0.0, abs=1e-9) and ap["sessions_held"] == 2
        assert vr["orh5"]["arms"]["stop_only"]["status"] == "stopped" and vr["orh5"]["arms"]["stop_only"]["sessions_held"] == 3

    def test_a_breakout_bar_that_is_also_the_low_of_the_day_does_not_abstain_the_apollo_walk(self):
        # fill minute 0 trades 10.20-10.35 and IS the low of the day, so the CB stop (low of the day at the fill) is 10.20
        # = the fill bar's own low. walk_arm's fill-bar test (low <= stop) would abstain 'straddles the stop'; the CB trade
        # never walks the fill bar (day0_walk starts after it), so the adapter neutralises the bar's LOW (its high and
        # close post-date a buy that triggered inside it, and stay live).
        c, bars, e, vr = _eval()
        rows = [(0, 10.30, 10.35, 10.20, 10.34)] + [(m, 10.34, 10.40, 10.31, 10.38) for m in range(1, 390)]
        md = rn.minute_dicts(_mb(rows))
        fill, stop = 10.30 * 1.001, 10.20
        sessions = rn.apollo_sessions(bars, np.arange(len(bars)), list(bars.dates), e, len(bars) - 1, 120)
        a = rn.apollo_control(mdicts=md, fill_pos=0, sessions=sessions, prior_closes=[10.0] * 10, e_date=bars.dates[e],
                              fill=fill, stop=stop, adr20=0.10)
        assert a["status"] == "settled" and a["mature"] and a["realized_r"] is not None
        from agents.market_intelligence import live_fill_counterfactuals as lfc
        target, kw = rn.apollo_walk_inputs(fill, stop, 0.10)
        raw = lfc.walk_arm(entry=fill, stop=stop, target=target, day0_bars=md, fill_idx=0, sessions=sessions,
                           prior_closes=[10.0] * 10, harvest="live_ladder", fill_day=bars.dates[e], horizon=120, **kw)
        assert raw["status"] == "abstain" and raw["reason"] == "day0_fill_bar_straddles_stop"      # the raw walker WOULD have

    def test_the_fill_bars_high_still_arms_the_breakeven_on_day_zero(self):
        # fill bar: 10.20 .. 10.60 (stop 10.20 = its low). Its high 10.60 >= fill + 1.5 x risk (10.4758) arms the breakeven
        # at the fill; minute 1 then trades down to 10.30 - below the fill, above the original stop - so the live ladder is
        # stopped at breakeven ON DAY 0 (R = 0), where a fully inert fill bar would have left the trade open.
        c, bars, e, vr = _eval()
        rows = ([(0, 10.30, 10.60, 10.20, 10.40), (1, 10.40, 10.45, 10.30, 10.42)]
                + [(m, 10.42, 10.50, 10.35, 10.45) for m in range(2, 390)])
        md = rn.minute_dicts(_mb(rows))
        fill, stop = 10.30 * 1.001, 10.20
        sessions = rn.apollo_sessions(bars, np.arange(len(bars)), list(bars.dates), e, len(bars) - 1, 120)
        a = rn.apollo_control(mdicts=md, fill_pos=0, sessions=sessions, prior_closes=[10.0] * 10, e_date=bars.dates[e],
                              fill=fill, stop=stop, adr20=0.10)
        assert a["status"] == "settled" and a["sessions_held"] == 0 and a["note"] == "stop_hit"
        assert a["realized_r"] == pytest.approx(0.0, abs=1e-9)

    def test_apollo_open_walks_are_marks_with_no_r_and_a_hole_blocks(self):
        c, bars, e, vr = _eval()
        ent = vr["orh5"]["entry"]
        mb = _mb()
        md, fp = rn.minute_dicts(mb), rn.fill_position(mb, 7)
        one_day = rn.apollo_sessions(bars, np.arange(len(bars)), list(bars.dates), e, e + 1, 120)
        a = rn.apollo_control(mdicts=md, fill_pos=fp, sessions=one_day, prior_closes=[10.0] * 10, e_date=bars.dates[e],
                              fill=ent["fill"], stop=ent["stop"], adr20=0.10)
        assert a["status"] == "pending" and a["mature"] is False and a["realized_r"] is None and a["note"]
        cidx = np.arange(len(bars))
        cidx[e + 2:] += 1                                                    # E+2 is missing from the ticker's bars
        sess = rn.apollo_sessions(bars, cidx, list(bars.dates) + [bars.dates[-1]], e, len(bars), 120)
        assert sess[0][1] is not None and sess[1][1] is None                 # a hole is a None bar, not a skipped day
        b = rn.apollo_control(mdicts=md, fill_pos=fp, sessions=sess, prior_closes=[10.0] * 10, e_date=bars.dates[e],
                              fill=ent["fill"], stop=ent["stop"], adr20=0.10)
        assert b["status"] == "pending" and "missing_session" in b["note"] and not b["mature"]


# ═══ the forward window is the daily stage's, byte for byte ═══════════════════════════════════════
def test_forward_window_is_what_close_variant_rows_walks():
    bars, e = _close_bars()
    cidx = np.arange(len(bars))
    cidx[e + 4:] += 3
    fwd, cut = rn.forward_window(bars, cidx, e, cb.EXIT_HORIZON)
    (row,) = rn.close_variant_rows("T", bars, [_close_cand(bars, e)], cidx)
    assert len(fwd) == row["fwd_bars"] == 3 and cut is True and row["fwd_hole"] == 1
    assert fwd.dates[-1].isoformat() == row["fwd_last_date"]
    f2, c2 = rn.forward_window(bars, None, e, cb.EXIT_HORIZON)
    assert len(f2) == len(bars) - e - 1 and c2 is False


# ═══ the STEP 0 firewall ═════════════════════════════════════════════════════════════════════════
def _write_cands(path, cands):
    cols = (["ticker", "D", "E", "K", "split", "pole_date", "base_id", "apollo_regime", "pivot", "adr20", "high_E", "low_E",
             "open_E", "close_E", "atr14", "median_dollar_vol20", "retrigger", "retrigger_chain", "pole_bad_high"]
            + list(rn.FLAG_FIELDS) + list(rn.CELL_COLS) + ["first_" + x for x in rn.CELL_NAMES]
            + ["first_chain_" + x for x in rn.CELL_NAMES])
    rn.write_tsv(path, cands, cols)


def _syn_dir(tmp_path, *, split="discovery", n_cands=1, with_done=True):
    """DATA dir: a SPY+X daily export, candidates.tsv, a minute dir with ONE session (X's E day), _done.psv. The bars sit
    in the split's own period (a discovery candidate's D is <= 2024-12-31, a holdout one's is later)."""
    bars, e = _e_bars(start=DISCOVERY_START if split == "discovery" else None)
    data = tmp_path / "data"
    (data / "out").mkdir(parents=True)
    with gzip.open(data / "daily_closes_all.csv.gz", "wt") as fh:
        for t in ("SPY", "X"):
            for k in range(len(bars)):
                fh.write(f"{t},{bars.dates[k].isoformat()},{bars.o[k]},{bars.h[k]},{bars.l[k]},{bars.c[k]},{bars.v[k]}\n")
    cands = [_m_cand(bars, e, split=split, K=k) for k in ("k5", "k10", "full", "tl")[:n_cands]]
    for c in cands:
        c["pole_date"] = "p"
    _write_cands(data / "out" / "candidates.tsv", cands)
    md = data / "minutes"
    md.mkdir()
    fm._append_gz(md / f"{bars.dates[e].isoformat()}.psv.gz", _minute_lines("X"))
    if with_done:
        (md / "_done.psv").write_text(f"{bars.dates[e].isoformat()}|X|390|ok\n")
    return data, bars, e, cands


class TestStep0Firewall:
    FORBIDDEN_COLS = ("day0", "exit", "realized", "held", "pnl", "mature", "arm")

    def test_step0_never_reaches_a_walker_and_writes_no_outcome_column(self, tmp_path, monkeypatch, capsys):
        data, bars, e, cands = _syn_dir(tmp_path, split="holdout", n_cands=3)

        def boom(*a, **k):
            raise AssertionError("STEP 0 reached an outcome walker")
        from agents.market_intelligence import live_fill_counterfactuals as lfc
        for owner, name in ((cb, "walk_exit"), (cb, "day0_result_to_outcome"), (ant, "simulate"), (lfc, "walk_arm"),
                            (rn, "walk_arms"), (rn, "family_a_control"), (rn, "apollo_control"), (rn, "cap_sensitivity"),
                            (rn, "evaluate_candidate"), (rn, "load_daily"), (rn, "close_variant_rows")):
            monkeypatch.setattr(owner, name, boom)
        rn.main(["step0-entries", "--data", str(data), "--workers", "1", "--small-out", str(tmp_path / "small")])
        txt = capsys.readouterr().out
        comp = (data / "out" / "entries_holdout_composition.tsv").read_text().splitlines()
        header = comp[0].split("\t")
        assert header == rn.COMPOSITION_COLS
        assert not [h for h in header if any(f in h for f in self.FORBIDDEN_COLS)]
        assert not {"fill", "stop", "level"} & set(header)                           # not even the fill price or the stop
        assert len(comp) == 1 + 3 * len(rn.MINUTE_VARIANTS)                          # 3 candidates x 4 variants, entry-time facts
        rows = [dict(zip(header, r.split("\t"))) for r in comp[1:]]
        by = {(r["K"], r["variant"]): r for r in rows}
        assert by[("k5", "orh5")]["status"] == "filled" and by[("k5", "orh5")]["fill_minute"] == "7"
        assert by[("k5", "orh60")]["status"] == "no_trigger"
        assert "GO/NO-GO input, SPEC key" in txt and "GO/NO-GO input, CHAIN key" in txt
        assert "C1" in txt and "orh5: k5=1" in txt                                    # C1 holdout, spec key: one k5 filled

    def test_entry_facts_carry_entry_time_columns_only(self):
        # behaviour, not source text: the walker-never-reached guarantee is the monkeypatch test above
        facts = rn.entry_facts(_mb(), _m_cand(*_e_bars()))
        assert set(facts["orh5"]) == {"status", "reason", "width_pct", "fill_minute"}      # nothing else leaves the function

    def test_a_pending_pair_is_not_an_abstain_and_an_empty_one_is(self, tmp_path):
        data, bars, e, cands = _syn_dir(tmp_path, split="holdout", n_cands=1, with_done=False)
        rn.main(["step0-entries", "--data", str(data), "--workers", "1", "--small-out", str(tmp_path / "small")])
        assert len((data / "out" / "entries_holdout_composition.tsv").read_text().splitlines()) == 1 + 4
        (data / "minutes" / "_done.psv").write_text(f"{bars.dates[e].isoformat()}|X|0|empty\n")
        (data / "minutes" / f"{bars.dates[e].isoformat()}.psv.gz").write_bytes(gzip.compress(b"", mtime=0))
        rn.main(["step0-entries", "--data", str(data), "--workers", "1", "--small-out", str(tmp_path / "small")])
        rows = [r.split("\t") for r in (data / "out" / "entries_holdout_composition.tsv").read_text().splitlines()[1:]]
        assert len(rows) == 4 and all(r[6] == "abstain" and r[7] == "no_minutes" and r[8] == "no_rows" for r in rows)


# ═══ the holdout guard ═══════════════════════════════════════════════════════════════════════════
class TestHoldoutGuard:
    def _tree(self, tmp_path, monkeypatch):
        data = tmp_path / "data"
        (data / "out").mkdir(parents=True)
        (data / "minutes").mkdir()
        small = tmp_path / "small"
        small.mkdir()
        monkeypatch.setattr(rn, "HERE", tmp_path / "hereroot")
        (rn.HERE / "out").mkdir(parents=True)
        repo = tmp_path / "repo"
        (repo / "agents" / "market_intelligence").mkdir(parents=True)
        (repo / "docs" / "analysis").mkdir(parents=True)
        (repo / "agents" / "market_intelligence" / "consolidation_breakout.py").write_text("# module\n")
        for rel in rn.FROZEN_CODE.values():                                   # the code the controls and the fills compute with
            (repo / rel).parent.mkdir(parents=True, exist_ok=True)
            (repo / rel).write_text(f"# {rel}\n")
        (data / "daily_closes_all.csv.gz").write_bytes(b"export")
        (data / "cb702_sic.psv").write_text("sic\n")
        for name in ("watch.tsv.gz", "candidates.tsv", "minute_fetch_list.tsv", "gap_in_bars.tsv", "close_variant_discovery.tsv.gz",
                     "trades_discovery.tsv.gz", "entries_discovery.tsv.gz", "entries_holdout_composition.tsv",
                     "discovery_report.tsv"):
            (data / "out" / name).write_text(name)
        (rn.HERE / "out" / "discovery_report.txt").write_text("report")
        (data / "minutes" / "2025-03-03.psv.gz").write_bytes(b"m1")
        return data, repo

    def _doc(self, repo, data, body="Method / population. What this does not answer. n=1.\n"):
        doc = repo / "docs" / "analysis" / "cb_preregistration_2026-10-20.md"
        doc.write_text(body + rn.FREEZE_MARK + "\n## Freeze record\n")
        pins = rn.pin_lines(data, repo) + [f"- doc body sha256: `{rn.doc_body_sha(doc.read_text())}`"]
        doc.write_text(doc.read_text() + "\n".join(pins) + "\n")
        return doc

    def test_a_matching_footer_accepts_and_every_edit_refuses(self, tmp_path, monkeypatch):
        data, repo = self._tree(tmp_path, monkeypatch)
        doc = self._doc(repo, data)
        assert rn.freeze_check(data=data, repo=repo) == []
        (data / "out" / "trades_discovery.tsv.gz").write_text("one byte changed")
        assert any("trades_discovery.tsv.gz sha256 mismatch" in p for p in rn.freeze_check(data=data, repo=repo))
        (data / "out" / "trades_discovery.tsv.gz").write_text("trades_discovery.tsv.gz")      # restored
        assert rn.freeze_check(data=data, repo=repo) == []
        (data / "minutes" / "fetch.log").write_text("a log line")                              # logs and OS litter are not data
        (data / ".DS_Store").write_bytes(b"x")
        assert rn.freeze_check(data=data, repo=repo) == []
        (data / "minutes" / "2025-03-04.psv.gz").write_bytes(b"a new minute file")           # the tree pin sees a new file
        assert any(p.startswith("minutes (tree) sha256 mismatch") for p in rn.freeze_check(data=data, repo=repo))
        (data / "minutes" / "2025-03-04.psv.gz").unlink()
        (data / "cb702_sic.psv").write_text("edited")                                         # a data file
        assert any(p.startswith("data/cb702_sic.psv sha256 mismatch") for p in rn.freeze_check(data=data, repo=repo))
        (data / "cb702_sic.psv").write_text("sic\n")
        doc.write_text(doc.read_text().replace("n=1", "n=2"))                                 # the doc body
        assert any(p.startswith("doc body sha256 mismatch") for p in rn.freeze_check(data=data, repo=repo))

    def test_missing_doc_marker_pin_or_file_refuse(self, tmp_path, monkeypatch):
        data, repo = self._tree(tmp_path, monkeypatch)
        assert "registration doc missing" in rn.freeze_check(data=data, repo=repo)[0]
        doc = repo / "docs" / "analysis" / "cb_preregistration_2026-10-20.md"
        doc.write_text("no marker here\n")
        assert "no <!-- FREEZE --> marker" in rn.freeze_check(data=data, repo=repo)[0]
        doc.unlink()
        doc = self._doc(repo, data)
        (data / "out" / "watch.tsv.gz").unlink()                                              # a pinned file gone
        assert "cell table: file missing" in rn.freeze_check(data=data, repo=repo)
        (data / "out" / "watch.tsv.gz").write_text("watch.tsv.gz")
        lines = [ln for ln in doc.read_text().splitlines() if not ln.startswith("- runner sha256")]
        doc.write_text("\n".join(lines) + "\n")
        assert "footer carries no runner sha256" in rn.freeze_check(data=data, repo=repo)
        (repo / "docs" / "analysis" / "cb_preregistration_2026-10-21.md").write_text("another")
        assert "2 registration docs" in rn.freeze_check(data=data, repo=repo)[0]

    def test_cli_refuses_with_exit_2_before_opening_anything(self, tmp_path, monkeypatch, capsys):
        data, repo = self._tree(tmp_path, monkeypatch)
        monkeypatch.setattr(rn, "REPO", repo)

        def boom(*a, **k):
            raise AssertionError("the holdout was opened")
        for name in ("read_candidates", "load_daily", "run_minute_stage", "_setup_minute_inputs"):
            monkeypatch.setattr(rn, name, boom)
        with pytest.raises(SystemExit) as ex:                                                  # no registration doc at all
            rn.main(["holdout", "--data", str(data)])
        assert ex.value.code == 2 and "REFUSED" in capsys.readouterr().err
        with pytest.raises(SystemExit) as ex:                                                  # the skip flag needs --dry-run
            rn.main(["holdout", "--data", str(data), "--no-freeze-check"])
        assert ex.value.code == 2 and "--dry-run" in capsys.readouterr().err
        self._doc(repo, data)
        (data / "daily_closes_all.csv.gz").write_bytes(b"edited export")
        with pytest.raises(SystemExit) as ex:                                                  # a mismatch refuses
            rn.main(["holdout", "--data", str(data)])
        assert ex.value.code == 2 and "daily_closes_all.csv.gz sha256 mismatch" in capsys.readouterr().err

    def test_dry_run_and_print_pins_and_a_second_run_is_refused(self, tmp_path, monkeypatch, capsys):
        data, repo = self._tree(tmp_path, monkeypatch)
        monkeypatch.setattr(rn, "REPO", repo)
        monkeypatch.setattr(rn, "read_candidates", lambda *a, **k: [])
        monkeypatch.setattr(rn, "_setup_minute_inputs", lambda *a, **k: {"cands": [], "files": {}, "by_date": {}, "minutes_dir": data / "minutes"})
        assert rn.run_holdout(argparse_ns(data, dry_run=True, no_freeze_check=True)) == 0
        assert "DRY RUN (freeze check SKIPPED)" in capsys.readouterr().out
        assert rn.run_holdout(argparse_ns(data, print_pins=True)) == 0
        pins = capsys.readouterr().out
        assert "- module sha256: `" in pins and "- minutes (tree) sha256: `" in pins and "- cell table sha256: `" in pins
        self._doc(repo, data)
        assert rn.run_holdout(argparse_ns(data, dry_run=True)) == 0                            # the check passed, then it only describes
        assert "DRY RUN (freeze check passed)" in capsys.readouterr().out
        (data / "out" / "trades_holdout.tsv.gz").write_bytes(b"")
        assert rn.run_holdout(argparse_ns(data)) == 2 and "joined ONCE" in capsys.readouterr().err


    def test_an_edit_to_the_code_the_numbers_are_computed_with_refuses(self, tmp_path, monkeypatch):
        """Finding: the freeze pinned the module file but not constants.py (ENTRY_SLIPPAGE_PCT sets every fill), nor the
        Family A / Apollo control code. A production edit after the freeze must now refuse the run."""
        data, repo = self._tree(tmp_path, monkeypatch)
        self._doc(repo, data)
        assert rn.freeze_check(data=data, repo=repo) == []
        assert set(rn.FROZEN_CODE) == {"code/constants.py", "code/anticipation.py", "code/live_fill_counterfactuals.py",
                                       "code/rule_eras.py", "code/exit_logic.py"}
        for label, rel in rn.FROZEN_CODE.items():
            f = repo / rel
            before = f.read_text()
            f.write_text(before + "ENTRY_SLIPPAGE_PCT = 0.9  # an edit after the freeze\n")
            assert any(p.startswith(f"{label} sha256 mismatch") for p in rn.freeze_check(data=data, repo=repo)), label
            f.unlink()
            assert f"{label}: file missing" in rn.freeze_check(data=data, repo=repo), label
            f.write_text(before)
            assert rn.freeze_check(data=data, repo=repo) == [], label                  # restored: accepted again
        assert all(f"- {k} sha256: `" in "\n".join(rn.pin_lines(data, repo)) for k in rn.FROZEN_CODE)   # --print-pins carries them

    def test_every_repo_file_the_outcome_path_computes_with_is_pinned(self):
        """The pin list is DERIVED, not hand-listed: walk the static call graph from the runner's two worker entry points
        (`_minute_job`, `_step0_job`) into each repo module they call, and into the repo modules THOSE call, following
        function-level imports too. Every module reached must be pinned (FROZEN_CODE / the module pin) or exempt with a
        reason. The members are NAMED, so a new import into the outcome path fails here instead of slipping past a count."""
        import ast
        repo = Path(rn.__file__).resolve().parents[3]

        def parse(mod):
            path = repo.joinpath(*mod.split(".")).with_suffix(".py")
            tree = ast.parse(path.read_text())
            defs = {n.name: n for n in tree.body if isinstance(n, ast.FunctionDef)}
            assigns = {t.id: n for n in tree.body if isinstance(n, ast.Assign) for t in n.targets if isinstance(t, ast.Name)}
            return tree, defs, assigns

        def local_imports(node):                                                       # {bound name: module}
            out = {}
            for n in ast.walk(node):
                if isinstance(n, ast.ImportFrom) and n.level == 0 and (n.module or "").split(".")[0] in ("agents", "shared", "core"):
                    for a in n.names:
                        out[a.asname or a.name] = n.module
            return out

        def used_imports(mod, entries):
            """{(module, name)} the entries of `mod` reach through its own functions."""
            tree, defs, assigns = parse(mod)
            top = local_imports(ast.Module(body=[n for n in tree.body if isinstance(n, (ast.Import, ast.ImportFrom))],
                                           type_ignores=[]))                           # module-level imports only
            seen, todo, hit = set(), list(entries), set()
            while todo:
                f = todo.pop()
                if f in seen:
                    continue
                seen.add(f)
                node = defs.get(f) or assigns.get(f)
                if node is None:
                    continue
                lazy = local_imports(node) if f in defs else {}
                for m in ast.walk(node):
                    if isinstance(m, ast.Name):
                        if m.id in lazy:
                            hit.add((lazy[m.id], m.id))
                        elif m.id in top:
                            hit.add((top[m.id], m.id))
                        if m.id in defs or m.id in assigns:
                            todo.append(m.id)
            return hit

        # runner -> the repo-module names its outcome path touches (cb.X, ant.X, lfc.X, rule_eras.X)
        rtree = ast.parse(Path(rn.__file__).read_text())
        rdefs = {n.name: n for n in rtree.body if isinstance(n, ast.FunctionDef)}
        seen, todo, attrs = set(), ["_minute_job", "_step0_job"], {}
        alias = {"cb": "agents.market_intelligence.consolidation_breakout", "ant": "agents.market_intelligence.anticipation",
                 "lfc": "agents.market_intelligence.live_fill_counterfactuals", "rule_eras": "agents.market_intelligence.rule_eras"}
        while todo:
            f = todo.pop()
            if f in seen or f not in rdefs:
                continue
            seen.add(f)
            for n in ast.walk(rdefs[f]):
                if isinstance(n, ast.Name) and n.id in rdefs:
                    todo.append(n.id)
                if isinstance(n, ast.Attribute) and isinstance(n.value, ast.Name) and n.value.id in alias:
                    attrs.setdefault(alias[n.value.id], set()).add(n.attr)
        assert set(attrs) == set(alias.values()), set(attrs)                           # all four are on the outcome path
        reached, work = set(attrs), [(m, set(a)) for m, a in attrs.items()]
        visited = set()
        while work:
            mod, names = work.pop()
            for (m2, nm) in used_imports(mod, sorted(names)):
                if (m2, nm) in visited:
                    continue
                visited.add((m2, nm))
                reached.add(m2)
                work.append((m2, {nm}))
        pinned = {"agents.market_intelligence.consolidation_breakout"} | {
            rel[:-3].replace("/", ".") for rel in rn.FROZEN_CODE.values()}
        assert reached == {"agents.market_intelligence.consolidation_breakout", "agents.market_intelligence.constants",
                           "agents.market_intelligence.anticipation", "agents.market_intelligence.live_fill_counterfactuals",
                           "agents.market_intelligence.rule_eras", "agents.market_intelligence.broker.exit_logic",
                           "agents.market_intelligence.db"}, sorted(reached)
        assert reached - pinned == set(rn.FROZEN_CODE_EXEMPT), sorted(reached - pinned)       # nothing is silently unpinned
        assert all(len(why) > 20 for why in rn.FROZEN_CODE_EXEMPT.values())
        assert {n for m, n in visited if m == "agents.market_intelligence.db"} == {"_f"}      # only the float helper

    def test_the_holdout_runs_only_in_its_registered_form(self, tmp_path, monkeypatch, capsys):
        """Finding: `holdout --out <dir>` passed the freeze check against the untouched DATA/out, then read an UNPINNED
        candidates.tsv from <dir> and looked for 'already joined' there - so the once-only run could be repeated at will.
        --limit-dates / --no-close / --no-apollo ran a partial or altered holdout whose output then blocked the real one."""
        data, repo = self._tree(tmp_path, monkeypatch)
        monkeypatch.setattr(rn, "REPO", repo)
        self._doc(repo, data)
        other = tmp_path / "elsewhere"
        other.mkdir()

        def boom(*a, **k):
            raise AssertionError("the holdout was opened")
        for name in ("read_candidates", "load_daily", "run_minute_stage", "_setup_minute_inputs"):
            monkeypatch.setattr(rn, name, boom)
        for extra, needle in ((["--out", str(other)], "--out"), (["--small-out", str(other)], "--small-out"),
                              (["--limit-dates", "3"], "--limit-dates"), (["--no-close"], "--no-close"),
                              (["--no-apollo"], "--no-apollo")):
            for tail in ([], ["--dry-run"], ["--dry-run", "--no-freeze-check"]):           # the dry run reads the file too
                with pytest.raises(SystemExit) as ex:
                    rn.main(["holdout", "--data", str(data)] + extra + tail)
                err = capsys.readouterr().err
                assert ex.value.code == 2 and "REFUSED" in err and needle in err, (extra, tail, err)
        # the registered form is still accepted: DATA/out spelled out is the same place
        monkeypatch.setattr(rn, "_setup_minute_inputs", lambda *a, **k: {"cands": [], "files": {}, "by_date": {}, "minutes_dir": data / "minutes"})
        assert rn.run_holdout(argparse_ns(data, out=str(data / "out"), dry_run=True)) == 0
        assert "DRY RUN (freeze check passed)" in capsys.readouterr().out
        # --print-pins is a read-only helper and stays available
        assert rn.run_holdout(argparse_ns(data, out=str(other), print_pins=True)) == 0

    def test_a_crashed_runs_partial_files_refuse_a_rerun_and_are_named(self, tmp_path, monkeypatch, capsys):
        data, repo = self._tree(tmp_path, monkeypatch)
        monkeypatch.setattr(rn, "REPO", repo)
        self._doc(repo, data)
        ran = []
        monkeypatch.setattr(rn, "run_minute_stage", lambda *a, **k: ran.append(1))
        assert rn.run_holdout(argparse_ns(data)) == 0 and ran == [1]                     # nothing on disk: it runs
        part = data / "out" / "trades_holdout.tsv.gz.partial"
        part.write_bytes(b"half a run")
        assert rn.holdout_existing_outputs(data / "out") == [part]
        assert rn.run_holdout(argparse_ns(data)) == 2 and ran == [1]
        err = capsys.readouterr().err
        assert "CRASHED holdout run" in err and str(part) in err and "removes it by hand" in err
        part.unlink()
        (data / "out" / "entries_holdout.tsv.gz.partial").write_bytes(b"x")              # either table's partial counts
        assert rn.run_holdout(argparse_ns(data)) == 2 and ran == [1]


def argparse_ns(data, **kw):
    import argparse
    ns = dict(data=str(data), out=None, small_out=None, workers=1, minutes=None, limit_dates=0, no_close=False, dry_run=False,
              no_freeze_check=False, print_pins=False, prereg=None, trades=None, no_apollo=False)
    ns.update(kw)
    return argparse.Namespace(**ns)


# ═══ #702 P4b: K = "com", the center-of-mass level - runner-only, suffixed outputs, the pinned names untouched ═════════
class TestCenterOfMassK:
    def test_keys_parse_and_the_default_keeps_every_pinned_name(self):
        assert rn.EXTRA_KS == cb.EXTRA_PIVOT_KEYS == ("com", "comb") and not set(rn.EXTRA_KS) & set(rn.KS)
        assert rn.parse_keys(None) == rn.parse_keys("") == rn.KS and rn.out_suffix(rn.KS) == ""
        assert rn.parse_keys("com") == ("com",) and rn.out_suffix(("com",)) == "_com"
        assert rn.parse_keys("k5, com") == ("k5", "com") and rn.out_suffix(("k5", "com")) == "_k5_com"
        for bad in ("k7", "com,com", ",", "tl,"):
            if bad == "tl,":
                assert rn.parse_keys(bad) == ("tl",) and rn.out_suffix(("tl",)) == "_tl"      # a subset of KS is NOT the default name
                continue
            with pytest.raises(ValueError):
                rn.parse_keys(bad)
        assert rn.run_keys(argparse_ns("x")) == (rn.KS, "")                              # a namespace without `keys` = the default

    def test_scan_ticker_adds_the_com_level_only_when_asked(self):
        b = _fixture_bars()["MRNA"]
        cidx = np.arange(len(b))
        plain = rn.scan_ticker("MRNA", b, cidx, [], "CS", 0)
        com = rn.scan_ticker("MRNA", b, cidx, [], "CS", 0, extra_keys=("com",))
        assert plain["counts"] == com["counts"] and len(plain["watch"]) == len(com["watch"]) == 60
        assert not any(k.startswith(("pivot_com", "com_")) for w in plain["watch"] for k in w)
        for w0, w1 in zip(plain["watch"], com["watch"]):
            assert {k: v for k, v in w1.items() if not k.startswith(("pivot_com", "com_"))} == w0     # the existing row is identical
            P, i = w1["pole_idx"], w1["i"]
            assert w1["pivot_com"] == pytest.approx(float(np.median(b.h[P + 1:i + 1])))                  # the median base high
            assert w1["com_variant"] == "quantile"

    def test_daily_with_keys_com_writes_suffixed_files_no_outcome_and_the_pinned_names_do_not_appear(self, tmp_path, capsys):
        data = TestTrendlineK()._daily_dir(tmp_path, with_done=True)
        small = tmp_path / "small"
        rn.main(["daily", "--data", str(data), "--workers", "1", "--small-out", str(small), "--keys", "com", "--no-close-variant"])
        txt = capsys.readouterr().out
        out = data / "out"
        assert {p.name for p in out.iterdir()} == {"watch_com.tsv.gz", "candidates_com.tsv", "gap_in_bars_com.tsv",
                                                   "minute_fetch_list_com.tsv", "minute_fetch_list_delta_com.tsv"}
        assert {p.name for p in small.iterdir()} == {"universe_by_date_com.tsv", "gate_counts_com.tsv", "run_summary_com.txt"}
        rd = TestTrendlineK()._read
        watch = rd(out / "watch_com.tsv.gz", gz=True)
        cols = set(watch[0])
        assert {"pivot_com", "pivot_com_date", "com_variant", "com_ignored_bars", "C0_com", "C1_com", "C1_s5_com"} <= cols
        assert not any(c.endswith(("_k5", "_k10", "_full", "_tl")) for c in cols if c.startswith(("C0", "C1", "C2")))   # cells for com only
        mrna = next(r for r in watch if r["ticker"] == "MRNA" and r["watch_date"] == "2026-09-16")
        b = _fixture_bars()["MRNA"]
        P, i = int(mrna["pole_idx"]), int(mrna["i"])
        assert float(mrna["pivot_com"]) == pytest.approx(float(np.median(b.h[P + 1:i + 1]))) and mrna["com_variant"] == "quantile"
        cands = rd(out / "candidates_com.tsv")
        assert cands and {c["K"] for c in cands} == {"com"} and all(c["overlap_open"] == "" for c in cands)   # no outcome anywhere
        assert all(float(c["pivot"]) > 0 for c in cands)
        full = rd(out / "minute_fetch_list_com.tsv")
        delta = rd(out / "minute_fetch_list_delta_com.tsv")
        assert list(full[0]) == ["ticker", "date", "tier"] and {(r["ticker"], r["date"]) for r in full} == {(c["ticker"], c["E"]) for c in cands}
        assert ("MRNA", "2026-09-17") not in {(r["ticker"], r["date"]) for r in delta}       # the fetched pair is not asked again
        assert {(r["ticker"], r["date"]) for r in delta} == {(r["ticker"], r["date"]) for r in full} - {("MRNA", "2026-09-17")}
        assert "CLOSE VARIANT: SKIPPED" in txt and "COM LEVEL vs the breakout day" in txt and "per era:" in txt
        # the composition text for the com run, and the stages that read its candidates by the suffixed name
        rn.main(["daily", "--data", str(data), "--workers", "1", "--small-out", str(small), "--keys", "com", "--step0"])
        assert (small / "step0_com.txt").exists() and "com:trades" in (small / "step0_com.txt").read_text()
        rn.main(["step0-entries", "--data", str(data), "--workers", "1", "--small-out", str(small), "--keys", "com"])
        assert "nothing to do" in capsys.readouterr().out                                    # no minute file on disk
        with pytest.raises(SystemExit):
            rn.main(["report", "--data", str(data), "--small-out", str(small), "--keys", "com"])
        assert "trades_discovery_com.tsv.gz not found" in capsys.readouterr().err

    def test_the_holdout_refuses_keys(self, tmp_path):
        data = tmp_path / "data"
        (data / "out").mkdir(parents=True)
        bad = rn.holdout_option_problems(argparse_ns(data, keys="com"), data)
        assert len(bad) == 1 and "--keys com" in bad[0] and "registered levels only" in bad[0]
        assert rn.holdout_option_problems(argparse_ns(data), data) == []


# ═══ #702 P4b step 6b: K = "comb" (com, closed at or below the line the night before) + the per-regime table ═════════
class TestCombK:
    def _run(self, data, tmp_path, keys, name):
        out, small = tmp_path / f"out_{name}", tmp_path / f"small_{name}"
        rn.main(["daily", "--data", str(data), "--out", str(out), "--small-out", str(small), "--workers", "1", "--keys", keys,
                 "--no-close-variant"])
        return out, small

    def test_keys_parse_and_the_suffix_follows_the_existing_convention(self):
        assert rn.parse_keys("com,comb") == ("com", "comb") and rn.out_suffix(("com", "comb")) == "_com_comb"
        assert rn.parse_keys("comb") == ("comb",) and rn.out_suffix(("comb",)) == "_comb"
        assert rn.run_keys(argparse_ns("x", keys="com, comb")) == (("com", "comb"), "_com_comb")
        with pytest.raises(ValueError):
            rn.parse_keys("comb,comb")

    def test_scan_ticker_adds_the_comb_fields_only_when_comb_is_asked(self):
        b = _fixture_bars()["MRNA"]
        cidx = np.arange(len(b))
        com = rn.scan_ticker("MRNA", b, cidx, [], "CS", 0, extra_keys=("com",))
        comb = rn.scan_ticker("MRNA", b, cidx, [], "CS", 0, extra_keys=("comb",))
        both = rn.scan_ticker("MRNA", b, cidx, [], "CS", 0, extra_keys=("com", "comb"))
        assert not any(k.startswith("pivot_comb") for w in com["watch"] for k in w)          # a com-only run has no comb column
        for wc, wb, w2 in zip(com["watch"], comb["watch"], both["watch"]):
            assert wb["pivot_comb"] == wb["pivot_com"] and wb["pivot_comb_idx"] == wb["pivot_com_idx"]
            assert wb["pivot_comb_date"] == wb["pivot_com_date"] and w2 == wb               # comb alone == com + comb
            assert {k: v for k, v in wb.items() if not k.startswith("pivot_comb")} == wc    # the com fields are com's own

    def test_comb_fetch_check_passes_a_subset_and_raises_on_a_pair_com_does_not_have(self):
        com = {("A", "2025-01-02"), ("B", "2025-01-03"), ("C", "2025-01-06")}
        msg = rn.comb_fetch_check({("A", "2025-01-02")}, com, com)
        assert "1 comb" in msg and "ALL among com's 3" in msg and "2 com pairs" in msg and "no minute fetch beyond com's" in msg
        assert "0 comb" in rn.comb_fetch_check(set(), com)
        with pytest.raises(AssertionError, match="outside com's: 1"):
            rn.comb_fetch_check({("A", "2025-01-02"), ("Z", "2025-01-02")}, com)
        with pytest.raises(AssertionError, match="differ from the com level's breaks"):
            rn.comb_fetch_check({("A", "2025-01-02")}, com, {("A", "2025-01-02")})

    def test_daily_com_comb_one_pass_comb_is_the_closed_at_or_below_subset_of_com(self, tmp_path, capsys):
        data = TestTrendlineK()._daily_dir(tmp_path, with_done=True)
        rd = TestTrendlineK()._read
        out_cc, small_cc = self._run(data, tmp_path, "com,comb", "cc")
        out_c, _ = self._run(data, tmp_path, "com", "c")
        out_b, _ = self._run(data, tmp_path, "comb", "b")
        txt = capsys.readouterr().out
        # the suffix convention: ONE set of files, the K column carries both levels
        assert {p.name for p in out_cc.iterdir()} == {"watch_com_comb.tsv.gz", "candidates_com_comb.tsv", "gap_in_bars_com_comb.tsv",
                                                      "minute_fetch_list_com_comb.tsv", "minute_fetch_list_delta_com_comb.tsv"}
        assert {p.name for p in small_cc.iterdir()} == {"universe_by_date_com_comb.tsv", "gate_counts_com_comb.tsv",
                                                        "run_summary_com_comb.txt"}
        assert "COMB FETCH CHECK" in txt and "ALL among com's" in (small_cc / "run_summary_com_comb.txt").read_text()
        watch = rd(out_cc / "watch_com_comb.tsv.gz", gz=True)
        assert {"pivot_com", "pivot_comb", "pivot_comb_date", "C0_com", "C0_comb", "C1_comb", "C1_s5_comb"} <= set(watch[0])
        # C0_comb is exactly `close(D) <= the com level`; C0_com holds wherever the level exists
        for r in watch:
            assert (r["C0_comb"] == "1") is (float(r["close"]) <= float(r["pivot_com"])) and r["C0_com"] == "1"
        by_night = {(r["ticker"], r["watch_date"]): r for r in watch}
        cands = rd(out_cc / "candidates_com_comb.tsv")
        com, comb = [c for c in cands if c["K"] == "com"], [c for c in cands if c["K"] == "comb"]
        assert com and comb and {c["K"] for c in cands} == {"com", "comb"}
        pairs = lambda rows: {(c["ticker"], c["E"]) for c in rows}
        assert pairs(comb) < pairs(com)                                                    # a STRICT subset: some nights closed above the line
        com_by = {(c["ticker"], c["E"]): c for c in com}
        for c in comb:
            w = by_night[(c["ticker"], c["D"])]
            assert w["C0_comb"] == "1" and c["C0"] == "1" and float(w["close"]) <= float(c["pivot"])    # only nights at or under the line
            assert c["pivot"] == com_by[(c["ticker"], c["E"])]["pivot"] and c["pivot_date"] == com_by[(c["ticker"], c["E"])]["pivot_date"]
        dropped = [c for c in com if (c["ticker"], c["E"]) not in pairs(comb)]
        assert dropped and all(float(by_night[(c["ticker"], c["D"])]["close"]) > float(c["pivot"]) for c in dropped)
        # the `com` rows are the com-only run's rows, byte for byte; the fetch list is com's (no new fetch)
        only = rd(out_c / "candidates_com.tsv")
        assert [dict(c) for c in com] == [dict(c) for c in only]
        assert (out_cc / "minute_fetch_list_com_comb.tsv").read_bytes() == (out_c / "minute_fetch_list_com.tsv").read_bytes()
        assert (out_cc / "minute_fetch_list_delta_com_comb.tsv").read_bytes() == (out_c / "minute_fetch_list_delta_com.tsv").read_bytes()
        # a comb-only run is the comb rows of the two-key run, and its fetch list is the comb pairs
        b_only = rd(out_b / "candidates_comb.tsv")
        assert [dict(c) for c in b_only] == [dict(c) for c in comb]
        assert {(r["ticker"], r["date"]) for r in rd(out_b / "minute_fetch_list_comb.tsv")} == pairs(comb) <= pairs(com)

    def test_a_first_break_from_above_does_not_use_up_the_base_for_the_later_break_from_below(self):
        """The unstated piece: a comb candidate exists only on a night that closed at or below the line, so one-trade-per-base
        counts the first break FROM BELOW (a from-above row would be retrigger=0 and push the real one to retrigger=1)."""
        mk = lambda ticker, E, K="comb": {"ticker": ticker, "pole_date": "p", "K": K, "E": E, **{c: True for c in cb.CELL_NAMES}}
        cands = [mk("A", "2025-02-05"), mk("A", "2025-02-12")]            # only the from-below nights are comb candidates
        cb.stamp_retrigger(cands)
        assert [c["retrigger"] for c in cands] == [0, 1]                 # the first from-below break is the trade


def _regime_frame():
    """A synthetic report frame: 12 filled headline walks of one (K, cell) set, regimes Bull x5 / Choppy x3 / Correcting x1 /
    missing x2 (+ Crisis x1), two of them still open; C1 holds on 8 of the 12."""
    import pandas as pd
    regs = ["Bull"] * 5 + ["Choppy"] * 3 + ["Correcting"] + ["Crisis"] + ["missing"] * 2
    r = [6.0, -1.0, 0.5, 2.0, -1.0, 5.0, -1.0, 0.3, -1.0, 12.0, -1.0, 0.0]
    mature = [1, 1, 1, 1, 1, 1, 1, 1, 0, 1, 1, 0]
    n = len(regs)
    df = pd.DataFrame({"K": ["k5"] * n, "variant": ["orh5"] * n, "arm": [cb.PRIMARY_ARM] * n, "retrigger": [0] * n,
                       "retrigger_chain": [0] * n, "mature": mature, "realized_r": r, "pnl_adr": [x / 3 for x in r],
                       "acct_pct": [x / 100 for x in r], "regime": regs})
    for c in cb.CELL_NAMES:
        df[c] = 0
    df["C0"] = 1
    df.loc[:7, "C1"] = 1
    return df


class TestRegimeTable:
    def test_the_rows_per_regime_add_up_to_the_cell_n_and_use_the_reports_own_statistics(self):
        df = _regime_frame()
        rows = rn.regime_report_rows(df)
        assert all(r["slice"] == "regime" and r["variant"] == "orh5" and r["arm"] == cb.PRIMARY_ARM for r in rows)
        for key in ("spec", "chain"):
            for cell, want in (("C0", 12), ("C1", 8)):
                grp = [r for r in rows if r["key"] == key and r["cell"] == cell and r["K"] == "k5"]
                allr = next(r for r in grp if r["value"] == "ALL")
                regs = [r for r in grp if r["value"] != "ALL"]
                assert [r["value"] for r in regs] == ["Bull", "Choppy", "Correcting", "Crisis", "missing"]
                assert allr["n_filled"] == want == sum(r["n_filled"] for r in regs)
                assert allr["n"] == sum(r["n"] for r in regs) and allr["n_open"] == sum(r["n_open"] for r in regs)
                assert allr["n"] + allr["n_open"] == allr["n_filled"]
                assert allr["sum_r"] == pytest.approx(sum(r.get("sum_r", 0.0) for r in regs))     # an empty regime carries n=0 only
        c0 = {r["value"]: r for r in rows if r["key"] == "spec" and r["cell"] == "C0"}
        assert (c0["Bull"]["n"], c0["Bull"]["mean_r"], c0["Bull"]["share_ge5"]) == (5, pytest.approx(1.3), pytest.approx(0.2))
        assert (c0["Choppy"]["n"], c0["Choppy"]["n_open"], c0["Choppy"]["share_ge5"]) == (3, 0, pytest.approx(1 / 3))
        assert (c0["Correcting"]["n"], c0["Correcting"]["n_open"], c0["Correcting"].get("mean_r")) == (0, 1, None)   # its one walk is open
        assert (c0["Crisis"]["n"], c0["Crisis"]["share_ge5"]) == (1, 1.0)
        assert (c0["missing"]["n"], c0["missing"]["n_open"], c0["missing"]["share_ge5"]) == (1, 1, 0.0)
        assert c0["ALL"]["n"] == 10 and c0["ALL"]["n_open"] == 2 and c0["ALL"]["share_ge5"] == pytest.approx(0.3)
        c1 = {r["value"]: r for r in rows if r["key"] == "spec" and r["cell"] == "C1"}
        assert c1["Bull"]["n"] == 5 and c1["Choppy"]["n"] == 3 and c1["Correcting"]["n"] == 0 and c1["Crisis"]["n"] == 0

    def test_an_unknown_label_gets_its_own_row_and_an_empty_frame_has_no_rows(self):
        df = _regime_frame()
        df.loc[0, "regime"] = "Euphoria"
        vals = [r["value"] for r in rn.regime_report_rows(df) if r["key"] == "spec" and r["cell"] == "C0"]
        assert vals == ["ALL", "Bull", "Choppy", "Correcting", "Crisis", "missing", "Euphoria"]
        assert rn.regime_report_rows(df.iloc[0:0]) == []

    def test_labels_and_the_date_map(self, tmp_path):
        assert [rn.regime_label(x) for x in ("Bull", " Choppy ", "", None, float("nan"))] == ["Bull", "Choppy", "missing", "missing", "missing"]
        _write_cands(tmp_path / "c.tsv", [_m_cand(_e_bars()[0], _e_bars()[1], apollo_regime="Bull"),
                                          _m_cand(_e_bars()[0], _e_bars()[1], D="2023-01-03", apollo_regime="")])
        got = rn.regime_by_date(tmp_path / "c.tsv")
        assert got["2023-01-03"] == "missing" and list(got.values()).count("Bull") == 1
        assert rn.regime_by_date(tmp_path / "nope.tsv") == {}

    def test_report_writes_regime_report_beside_the_pinned_files_and_changes_none_of_them(self, tmp_path, capsys):
        data, bars, e, cands = _syn_dir(tmp_path, n_cands=3)
        _close_file(data, bars, e, cands)
        _write_cands(data / "out" / "candidates.tsv", [dict(c, apollo_regime="Choppy") for c in cands])
        small = tmp_path / "small"
        rn.main(["minute", "--data", str(data), "--workers", "1", "--small-out", str(small)])
        rn.main(["report", "--data", str(data), "--small-out", str(small)])
        txt = capsys.readouterr().out
        assert "by regime" in txt
        out = data / "out"
        assert (out / "regime_report.tsv").exists() and (small / "regime_report.txt").exists()
        assert not (out / "regime_report_holdout.tsv").exists()
        reg = pd_read(out / "regime_report.tsv")
        assert list(reg.columns) == rn.REGIME_COLS
        rep = pd_read(out / "discovery_report.tsv")                                      # the full table (the small copy is rounded)
        head_sel = lambda f: (f.key == "spec") & (f.cell == "C1") & (f.K == "k5") & (f.variant == "orh5") & (f.arm == cb.PRIMARY_ARM)
        head = rep[head_sel(rep) & (rep.slice == "all")].iloc[0]                         # the report's own headline row
        mine = reg[head_sel(reg)].set_index("value")
        assert (mine.loc["ALL", "n"], mine.loc["ALL", "mean_r"], mine.loc["ALL", "n_open"]) == (head.n, head.mean_r, head.n_open)
        assert head.n == 1 and head.n_open == 0
        assert mine.loc["Choppy", "n"] == 1 and mine.loc["Bull", "n"] == 0 and mine.loc["missing", "n"] == 0   # the label travelled candidates -> trades table
        # the run printed the per-regime text and did not touch the report text (a two-run byte-equality is in test_minute_then_report)
        assert "-- SPEC key" in (small / "regime_report.txt").read_text()

    def test_an_unlabelled_date_reads_missing_and_a_missing_candidates_file_is_said_aloud(self, tmp_path, capsys):
        data, bars, e, cands = _syn_dir(tmp_path, n_cands=1)
        _close_file(data, bars, e, cands)
        small = tmp_path / "small"
        rn.main(["minute", "--data", str(data), "--workers", "1", "--small-out", str(small)])
        rn.main(["report", "--data", str(data), "--small-out", str(small)])
        reg = pd_read(data / "out" / "regime_report.tsv")
        c1 = reg[(reg.key == "spec") & (reg.cell == "C1") & (reg.K == "k5")].set_index("value")
        assert c1.loc["missing", "n"] == 1 and c1.loc["Bull", "n"] == 0                 # _m_cand carries apollo_regime=""
        trades = data / "out" / "trades_discovery.tsv.gz"
        (data / "out" / "candidates.tsv").rename(data / "out" / "candidates_gone.tsv")
        capsys.readouterr()
        rn.main(["report", "--data", str(data), "--small-out", str(small), "--trades", str(trades)])
        assert "not found or empty" in capsys.readouterr().out

    def test_the_holdout_run_writes_its_own_regime_table_once(self, tmp_path, capsys):
        data, bars, e, cands = _syn_dir(tmp_path, split="holdout", n_cands=1)
        _write_cands(data / "out" / "candidates.tsv", [dict(c, apollo_regime="Bull") for c in cands])
        small = tmp_path / "small"
        rn.run_minute_stage(argparse_ns(data, small_out=str(small)), "holdout")
        out = data / "out"
        assert (out / "regime_report_holdout.tsv").exists() and (small / "regime_report_holdout.txt").exists()
        assert not (out / "regime_report.tsv").exists()
        reg = pd_read(out / "regime_report_holdout.tsv")
        c1 = reg[(reg.key == "spec") & (reg.cell == "C1") & (reg.K == "k5")].set_index("value")
        assert c1.loc["ALL", "n"] == 1 and c1.loc["Bull", "n"] == 1 and c1.loc["Choppy", "n"] == 0
        assert sorted(p.name for p in out.glob("*.tsv*")) == ["candidates.tsv", "entries_holdout.tsv.gz", "regime_report_holdout.tsv",
                                                              "trades_holdout.tsv.gz"]
        assert "HOLDOUT by regime" in capsys.readouterr().out

    def test_minute_and_report_on_com_comb_write_the_suffixed_files_and_the_regime_table_per_k(self, tmp_path, capsys):
        """The discovery re-read the main loop will run is `minute --keys com,comb` then `report --keys com,comb`: both stages
        read `candidates_com_comb.tsv`, write `*_com_comb`, and the regime table carries both K and the suffix."""
        data, bars, e, cands = _syn_dir(tmp_path, n_cands=1)
        cs = [dict(_m_cand(bars, e, K=k), pole_date="p", apollo_regime="Choppy") for k in ("com", "comb")]
        _write_cands(data / "out" / "candidates_com_comb.tsv", cs)
        small = tmp_path / "small"
        rn.main(["minute", "--data", str(data), "--workers", "1", "--small-out", str(small), "--keys", "com,comb", "--no-close"])
        rn.main(["report", "--data", str(data), "--small-out", str(small), "--keys", "com,comb"])
        capsys.readouterr()
        out = data / "out"
        assert {"trades_discovery_com_comb.tsv.gz", "entries_discovery_com_comb.tsv.gz", "discovery_report_com_comb.tsv",
                "regime_report_com_comb.tsv"} <= {p.name for p in out.iterdir()}
        assert not (out / "trades_discovery.tsv.gz").exists() and not (out / "regime_report.tsv").exists()   # the pinned names are not written
        assert (small / "regime_report_com_comb.txt").exists() and (small / "discovery_report_com_comb.txt").exists()
        assert set(pd_read(out / "trades_discovery_com_comb.tsv.gz").K) == {"com", "comb"}
        reg = pd_read(out / "regime_report_com_comb.tsv")
        for k in ("com", "comb"):
            c1 = reg[(reg.key == "spec") & (reg.cell == "C1") & (reg.K == k)].set_index("value")
            assert c1.loc["ALL", "n"] == 1 and c1.loc["Choppy", "n"] == 1 and c1.loc["Bull", "n"] == 0

    def test_the_discovery_minute_stage_writes_no_regime_table(self, tmp_path):
        data, bars, e, cands = _syn_dir(tmp_path, n_cands=1)
        _close_file(data, bars, e, cands)
        rn.main(["minute", "--data", str(data), "--workers", "1", "--small-out", str(tmp_path / "small")])
        assert not list((data / "out").glob("regime_report*")) and not list((tmp_path / "small").glob("regime_report*"))


# ═══ end to end: minute -> report, and the holdout engine ═════════════════════════════════════════
def _close_file(data, bars, e, cands):
    rows = []
    for c in cands:
        rows += rn.close_variant_rows("X", bars, [dict(c, E_i=e)], np.arange(len(bars)))
    cols = list(rows[0].keys())
    rn.write_tsv(data / "out" / "close_variant_discovery.tsv.gz", rows, cols, gz=True)


class TestMinuteEndToEnd:
    def test_minute_then_report(self, tmp_path, capsys):
        data, bars, e, cands = _syn_dir(tmp_path, n_cands=3)
        _close_file(data, bars, e, cands)
        small = tmp_path / "small"
        args = ["minute", "--data", str(data), "--workers", "1", "--small-out", str(small)]
        rn.main(args)
        out = capsys.readouterr().out
        assert "DISCOVERY MINUTE STAGE" in out and "DATA GATE" in out and "PENDING fetch" in out
        trades = pd_read(data / "out" / "trades_discovery.tsv.gz")
        entries = pd_read(data / "out" / "entries_discovery.tsv.gz")
        assert list(trades.columns) == rn.TRADE_COLS and list(entries.columns) == rn.ENTRY_COLS
        o5 = trades[(trades.variant == "orh5") & (trades.K == "k5")]
        assert sorted(o5.arm.dropna()) == sorted(rn.ALL_ARMS) and o5.mature.eq(1).all()
        cl = trades[(trades.variant == "close") & (trades.K == "k5")]
        assert sorted(cl.arm.dropna()) == sorted(cb.ARMS) and len(entries[entries.variant == "close"]) == 3     # reused, joined
        assert (trades[trades.variant == "orh60"].arm.isna()).all() and (trades[trades.variant == "orh60"].status == "no_trigger").all()
        assert set(entries[entries.variant == "orh5"].minutes_state) == {"ok"}
        # the report reads exactly that file; two runs are byte-identical (fixed seed)
        assert rn.main(["report", "--data", str(data), "--small-out", str(small)]) is None
        txt1 = (small / "discovery_report.txt").read_text()
        rn.main(["report", "--data", str(data), "--small-out", str(small)])
        assert (small / "discovery_report.txt").read_text() == txt1
        assert "HEADLINE - entry orh5, arm p33_s3_t10" in txt1 and "C1_no_tightening" in txt1 and "SENSITIVITIES" in txt1
        assert (data / "out" / "discovery_report.tsv").exists() and (small / "discovery_report.tsv").exists()
        import pandas as pd
        rep = pd.read_csv(small / "discovery_report.tsv", sep="\t", keep_default_na=False, na_values=[""])
        r = rep[(rep.key == "spec") & (rep.cell == "C1") & (rep.K == "k5") & (rep.variant == "orh5") & (rep.arm == cb.PRIMARY_ARM)].iloc[0]
        assert r.n == 1 and r.n_open == 0                                                    # ONE trade per (K, variant, arm), mature

    def test_the_holdout_engine_walks_the_close_variant_itself_and_the_discovery_run_ignores_the_holdout(self, tmp_path, capsys):
        data, bars, e, cands = _syn_dir(tmp_path, split="holdout", n_cands=1)
        small = tmp_path / "small"
        rn.main(["minute", "--data", str(data), "--workers", "1", "--small-out", str(small)])      # nothing in the discovery split
        assert "nothing to do" in capsys.readouterr().out and not (data / "out" / "trades_discovery.tsv.gz").exists()
        ns = argparse_ns(data, small_out=str(small))
        rn.run_minute_stage(ns, "holdout")                                                         # the engine only; the CLI guard is tested above
        t = pd_read(data / "out" / "trades_holdout.tsv.gz")
        assert set(t.split) == {"holdout"} and "close" in set(t.variant) and len(t[(t.variant == "close")]) == len(cb.ARMS)

    def test_a_crash_mid_run_leaves_no_final_table_only_a_partial_and_a_clean_run_leaves_no_partial(self, tmp_path, monkeypatch, capsys):
        data, bars, e, cands = _syn_dir(tmp_path, split="holdout", n_cands=1)
        ns = argparse_ns(data, small_out=str(tmp_path / "small"))
        real = rn._minute_job

        def crash(date_iso):
            raise RuntimeError("worker died")
        monkeypatch.setattr(rn, "_minute_job", crash)
        with pytest.raises(RuntimeError):
            rn.run_minute_stage(ns, "holdout")
        out = data / "out"
        assert not (out / "trades_holdout.tsv.gz").exists() and not (out / "entries_holdout.tsv.gz").exists()
        assert (out / "trades_holdout.tsv.gz.partial").exists() and (out / "entries_holdout.tsv.gz.partial").exists()
        assert [q.name for q in rn.holdout_existing_outputs(out)] == ["trades_holdout.tsv.gz.partial", "entries_holdout.tsv.gz.partial"]
        monkeypatch.setattr(rn, "_minute_job", real)                                   # the operator clears the partial and re-runs
        for q in rn.holdout_existing_outputs(out):
            q.unlink()
        rn.run_minute_stage(ns, "holdout")
        assert (out / "trades_holdout.tsv.gz").exists() and (out / "entries_holdout.tsv.gz").exists()
        assert not list(out.glob("*.partial"))                                           # a finished run leaves no partial
        assert [q.name for q in rn.holdout_existing_outputs(out)] == ["trades_holdout.tsv.gz", "entries_holdout.tsv.gz"]

    def test_the_data_gate_blocks_above_five_percent(self):
        tally = Counter({("data_abstain", "none"): 90, ("data_abstain", "no_minutes"): 4, ("data_abstain", "minute_daily_mismatch"): 3,
                         ("data_abstain", "minute_high_below_pivot"): 3})
        share, txt = rn.minute_data_gate(tally)
        assert share == pytest.approx(0.10) and "BLOCKS THE READ" in txt and "match rate 97.00%" in txt
        assert "ok" in rn.minute_data_gate(Counter({("data_abstain", "none"): 99, ("data_abstain", "no_minutes"): 1}))[1]


def pd_read(path):
    import pandas as pd
    return pd.read_csv(path, sep="\t", keep_default_na=False, na_values=[""], low_memory=False)


def test_read_candidates_types_and_group_by_date(tmp_path):
    bars, e = _e_bars(start=DISCOVERY_START)
    hbars, he = _e_bars()
    cs = [_m_cand(hbars, he, split="holdout"), _m_cand(bars, e, K="k10"), _m_cand(bars, e, E="2030-01-01")]
    _write_cands(tmp_path / "c.tsv", cs)
    only = rn.read_candidates(tmp_path / "c.tsv", "discovery")
    assert len(only) == 2 and only[0]["pivot"] == 10.25 and only[0]["C1"] is True and only[0]["C2"] is False
    assert only[0]["retrigger"] == 0 and isinstance(only[0]["first_C0"], int) and only[0]["atr14"] == 0.05
    by = rn.group_by_date(only, {bars.dates[e].isoformat()})
    assert list(by) == [bars.dates[e].isoformat()] and [c["K"] for c in by[bars.dates[e].isoformat()]] == ["k10"]


def test_read_candidates_refuses_a_row_whose_split_label_disagrees_with_its_D(tmp_path):
    """Finding: `minute` trusted the file's split column, so `minute --out X` on a relabelled file computed HOLDOUT outcomes
    (and relabelling the other way hid holdout rows from `holdout`). The label is re-derived from D (split_label)."""
    dbars, de = _e_bars(start=DISCOVERY_START)
    hbars, he = _e_bars()
    ok = [_m_cand(dbars, de), _m_cand(hbars, he, split="holdout")]
    _write_cands(tmp_path / "ok.tsv", ok)
    assert len(rn.read_candidates(tmp_path / "ok.tsv")) == 2 and len(rn.read_candidates(tmp_path / "ok.tsv", "holdout")) == 1
    holdout_as_discovery = [_m_cand(hbars, he, split="discovery")]                       # a 2025 D wearing the discovery label
    _write_cands(tmp_path / "a.tsv", holdout_as_discovery)
    with pytest.raises(ValueError, match="labelled split='discovery' but D falls in the 'holdout' period"):
        rn.read_candidates(tmp_path / "a.tsv", "discovery")
    discovery_as_holdout = [_m_cand(dbars, de, split="holdout")]                         # and the other way round
    _write_cands(tmp_path / "b.tsv", discovery_as_holdout)
    with pytest.raises(ValueError, match="labelled split='holdout' but D falls in the 'discovery' period"):
        rn.read_candidates(tmp_path / "b.tsv", "holdout")
    with pytest.raises(ValueError):                                                      # checked even for the side not asked for
        rn.read_candidates(tmp_path / "a.tsv", "holdout")
    edge = [_m_cand(dbars, de, D="2024-12-31"), _m_cand(hbars, he, D="2025-01-02", split="holdout")]   # the boundary is exact
    _write_cands(tmp_path / "e.tsv", edge)
    assert len(rn.read_candidates(tmp_path / "e.tsv")) == 2


def test_minute_on_a_relabelled_candidates_file_computes_nothing(tmp_path):
    """The end-to-end form of the hole: a holdout candidate (D in 2025) relabelled discovery in an `--out` directory."""
    data, bars, e, cands = _syn_dir(tmp_path, split="holdout", n_cands=1)
    other = tmp_path / "elsewhere"
    other.mkdir()
    relabelled = [dict(c, split="discovery") for c in cands]
    _write_cands(other / "candidates.tsv", relabelled)
    with pytest.raises(ValueError, match="relabelled or is stale"):
        rn.main(["minute", "--data", str(data), "--out", str(other), "--workers", "1", "--small-out", str(tmp_path / "small")])
    assert not list(other.glob("trades_*")) and not list(other.glob("entries_*"))


# ═══ #702 P1c: K = "tl", the down-sloping trendline level ═════════════════════════════════════════
class TestTrendlineK:
    def test_ks_is_the_modules_four_levels_and_the_new_one_is_the_fetch_delta_k(self):
        assert rn.KS == cb.PIVOT_KEYS == ("k5", "k10", "full", "tl") and rn.NEW_FETCH_KS == ("tl",)

    def test_breaks_out_is_strictly_above_and_a_missing_level_never_breaks(self):
        assert rn.breaks_out(10.01, 10.0) is True
        assert rn.breaks_out(10.0, 10.0) is False and rn.breaks_out(9.99, 10.0) is False
        assert rn.breaks_out(1e9, None) is False             # a night with no down-sloping line has no tl level: no TypeError, no break

    def test_minute_fetch_delta_is_the_new_ks_pairs_not_already_in_done(self):
        full = [{"ticker": t, "date": d, "tier": tier} for t, d, tier in
                [("AAA", "2025-03-03", 0), ("BBB", "2025-03-03", 1), ("AAA", "2025-03-04", 0), ("CCC", "2025-03-05", 1)]]
        cands = [{"ticker": "AAA", "E": "2025-03-03", "K": "k5"}, {"ticker": "AAA", "E": "2025-03-03", "K": "tl"},   # shared pair
                 {"ticker": "BBB", "E": "2025-03-03", "K": "k5"},                                                    # k5 only: not new
                 {"ticker": "AAA", "E": "2025-03-04", "K": "tl"}, {"ticker": "CCC", "E": "2025-03-05", "K": "tl"}]
        done = {("2025-03-03", "AAA"): "ok", ("2025-03-05", "CCC"): "empty"}            # 'empty' counts as fetched too
        got = rn.minute_fetch_delta(full, cands, done)
        assert got == [{"ticker": "AAA", "date": "2025-03-04", "tier": 0}]              # the list's own order and tier
        assert rn.minute_fetch_delta(full, cands, {}) == [r for r in full if (r["ticker"], r["date"]) != ("BBB", "2025-03-03")]
        assert rn.minute_fetch_delta(full, cands, None) == rn.minute_fetch_delta(full, cands, {})    # no _done.psv: nothing fetched
        assert rn.minute_fetch_delta(full, [c for c in cands if c["K"] != "tl"], {}) == []

    def _daily_dir(self, tmp_path, *, with_done):
        """DATA dir for the real daily stage: SPY + QQQ (flat), MRNA (the fixture's real bars) and WICK = MRNA with one
        base high on 09-09 lifted over the pole high (a wick: the base stands, but no down-sloping line exists)."""
        mrna = _fixture_bars()["MRNA"]
        wick_h = mrna.h.copy()
        k = mrna.dates.index(dt.date(2026, 9, 9))
        wick_h[k] = 180.0                                            # pole high is 176.66; 09-09 is outside the pole window
        wick = cb.daily_bars_from_arrays(mrna.dates, mrna.o, wick_h, mrna.l, mrna.c, mrna.v)
        data = tmp_path / "data"
        (data / "out").mkdir(parents=True)
        n = len(mrna)
        with gzip.open(data / "daily_closes_all.csv.gz", "wt") as fh:
            for t, b in (("MRNA", mrna), ("WICK", wick)):
                for j in range(n):
                    fh.write(f"{t},{b.dates[j].isoformat()},{b.o[j]},{b.h[j]},{b.l[j]},{b.c[j]},{b.v[j]}\n")
            for t in ("SPY", "QQQ"):
                for j in range(n):
                    px = 100.0 + 0.01 * j
                    fh.write(f"{t},{mrna.dates[j].isoformat()},{px},{px * 1.001},{px * 0.999},{px},1000000000\n")
        for name in ("small_pulls.psv", "cb702_splits.psv", "cb702_sic.psv"):
            (data / name).write_text("")
        if with_done:                                               # the first pull: MRNA's 09-17 session was fetched
            (data / "minutes").mkdir()
            (data / "minutes" / "_done.psv").write_text("2026-09-17|MRNA|390|ok\n")
        return data

    def _read(self, path, gz=False):
        import csv
        opener = gzip.open if gz else open
        with opener(path, "rt", newline="") as fh:
            return list(csv.DictReader(fh, delimiter="\t"))

    def test_daily_stage_end_to_end_tl_candidates_and_the_fetch_delta(self, tmp_path, capsys):
        data = self._daily_dir(tmp_path, with_done=False)
        small = tmp_path / "small"
        rn.main(["daily", "--data", str(data), "--workers", "1", "--small-out", str(small)])
        txt = capsys.readouterr().out
        out = data / "out"
        watch = self._read(out / "watch.tsv.gz", gz=True)
        cands = self._read(out / "candidates.tsv")
        # the watch table carries the new level, its telemetry and a cell block per K
        cols = set(watch[0])
        assert {"pivot_tl", "pivot_tl_date", "tl_slope_pct", "tl_interior_touches", "C0_tl", "C1_tl", "C1_s5_tl"} <= cols
        mrna = next(r for r in watch if r["ticker"] == "MRNA" and r["watch_date"] == "2026-09-16")
        m = (148.93 - 176.66) / 19
        assert float(mrna["pivot_tl"]) == pytest.approx(176.66 + 20 * m) and mrna["pivot_tl_date"] == "2026-09-16"
        wick = next(r for r in watch if r["ticker"] == "WICK" and r["watch_date"] == "2026-09-16")
        # WICK's base high (the 180 wick) tops the pole high, so its line is anchored on the wick, not the pole top
        assert wick["pivot_tl"] != "" and wick["C0_tl"] == "1" and wick["C0_k5"] == "1" and float(wick["tl_slope_pct"]) <= 0
        assert wick["tl_anchor_idx"] != wick["pole_idx"]
        # candidates: MRNA breaks out of all four levels on 09-17; WICK only of k5 (its k10/full are the 180 wick)
        on = {(c["ticker"], c["K"]): c for c in cands if c["D"] == "2026-09-16"}
        assert {k for (t, k) in on if t == "MRNA"} == {"k5", "k10", "full", "tl"}
        wick_e = next(r for r in cands if r["ticker"] == "WICK" and r["D"] == "2026-09-16")["high_E"]
        assert {k for (t, k) in on if t == "WICK"} == {"k5"} | ({"tl"} if float(wick_e) > float(wick["pivot_tl"]) else set())
        tl = on[("MRNA", "tl")]
        assert float(tl["pivot"]) == pytest.approx(176.66 + 20 * m) and tl["pivot_date"] == "2026-09-16" and tl["E"] == "2026-09-17"
        assert tl["pole_date"] == on[("MRNA", "k5")]["pole_date"] == "2026-08-19"          # the spec key is (ticker, pole_date, K)
        # one trade per base: the base's FIRST tl break (by E) is the trade, every later one is a retrigger. By hand, the first
        # is D = 09-03 -> E = 09-04: the touch is 09-02 (156.4151, 10 sessions after the pole), m = (156.4151 - 176.66) / 10,
        # and E is the 12th session after the pole, so the level is 176.66 + 12 m = 152.3661; E's high 154.69 clears it
        base = sorted((c for c in cands if c["ticker"] == "MRNA" and c["K"] == "tl" and c["pole_date"] == "2026-08-19"),
                      key=lambda c: c["E"])
        assert [c["retrigger"] for c in base] == ["0"] + ["1"] * (len(base) - 1) and tl is base[-1]
        first = base[0]
        assert (first["D"], first["E"], first["pivot_date"]) == ("2026-09-03", "2026-09-04", "2026-09-02")
        assert float(first["pivot"]) == pytest.approx(176.66 + 12 * (156.4151 - 176.66) / 10) == pytest.approx(152.3661, abs=5e-5)
        assert float(first["high_E"]) == 154.69 > float(first["pivot"])
        # invariants over EVERY tl row: a level existed that night and E's high cleared it; no candidate on a no-line night
        no_line = {(r["ticker"], r["watch_date"]) for r in watch if r["pivot_tl"] == ""}
        for c in cands:
            if c["K"] == "tl":
                assert (c["ticker"], c["D"]) not in no_line and float(c["high_E"]) > float(c["pivot"])
        # the delta: nothing was fetched yet, so every tl pair is in it; full list = the union incl. tl pairs
        delta = self._read(out / "minute_fetch_list_delta.tsv")
        tl_pairs = {(c["ticker"], c["E"]) for c in cands if c["K"] == "tl"}
        assert {(r["ticker"], r["date"]) for r in delta} == tl_pairs and ("MRNA", "2026-09-17") in tl_pairs
        full = {(r["ticker"], r["date"]) for r in self._read(out / "minute_fetch_list.tsv")}
        assert tl_pairs <= full
        assert list(delta[0]) == ["ticker", "date", "tier"]
        assert f"MINUTE FETCH DELTA" in txt and f"{len(delta):,} pairs" in txt
        assert "no _done.psv" in txt
        # the daily-stage STEP 0 carries tl: a column group in the composition tables and a count in the go/no-go line
        # (a hardcoded K tuple in step0_text / _step0_block would drop these)
        assert "tl:trades" in txt and "tl:first" in txt and "tl:gap>1adr" in txt
        assert re.search(r"k5: \d+, k10: \d+, full: \d+, tl: \d+", txt.split("GO/NO-GO input, SPEC key", 1)[1].splitlines()[0])
        # the tl-vs-horizontal population table: the no-line night count per split, read off the watch table
        # (the WICK nights are anchored on the wick that topped the pole high)
        assert "tl: no line" in txt and "tl anchored on a later wick" in txt
        # the fixture's 2026 nights all fall in the HOLDOUT split (D > 2024-12-31); the discovery row exists and is empty
        rows = {ln.split()[0]: [int(x.replace(",", "")) for x in ln.split()[1:]]
                for ln in txt.splitlines() if ln.split()[:1] in (["discovery"], ["holdout"]) and len(ln.split()) == 6}
        assert rows["discovery"] == [0, 0, 0, 0, 0]
        h = [w for w in watch if w["split"] == "holdout"]
        assert rows["holdout"] == [
            len(h), sum(w["C0_k5"] == "1" for w in h), sum(w["C0_tl"] == "1" for w in h),
            sum(w["pivot_tl"] == "" for w in h),
            sum(w["tl_anchor_idx"] != "" and w["tl_anchor_idx"] != w["pole_idx"] for w in h)]
        n, c0_k5, c0_tl, no_line, wick_anchored = rows["holdout"]
        # no-line nights = the highest high under 3 sessions old; the WICK nights are anchored on the wick, not lost
        assert no_line > 0 and wick_anchored > 0 and c0_tl < c0_k5 and c0_k5 - c0_tl == no_line

    def test_the_fetch_delta_leaves_out_what_the_first_pull_already_fetched(self, tmp_path, capsys):
        data = self._daily_dir(tmp_path, with_done=True)
        rn.main(["daily", "--data", str(data), "--workers", "1", "--small-out", str(tmp_path / "small")])
        txt = capsys.readouterr().out
        out = data / "out"
        cands = self._read(out / "candidates.tsv")
        delta = {(r["ticker"], r["date"]) for r in self._read(out / "minute_fetch_list_delta.tsv")}
        tl_pairs = {(c["ticker"], c["E"]) for c in cands if c["K"] == "tl"}
        assert ("MRNA", "2026-09-17") in tl_pairs and ("MRNA", "2026-09-17") not in delta        # in _done.psv
        assert delta == tl_pairs - {("MRNA", "2026-09-17")}
        assert "1 pairs in _done.psv" in txt

    def test_the_minute_stage_the_step0_and_the_report_all_carry_tl(self, tmp_path, capsys):
        data, bars, e, cands = _syn_dir(tmp_path, n_cands=4)
        assert [c["K"] for c in cands] == ["k5", "k10", "full", "tl"]
        _close_file(data, bars, e, cands)
        small = tmp_path / "small"
        rn.main(["minute", "--data", str(data), "--workers", "1", "--small-out", str(small)])
        capsys.readouterr()
        trades = pd_read(data / "out" / "trades_discovery.tsv.gz")
        entries = pd_read(data / "out" / "entries_discovery.tsv.gz")
        assert set(trades.K) == {"k5", "k10", "full", "tl"} and set(entries.K) == {"k5", "k10", "full", "tl"}
        tl5 = trades[(trades.K == "tl") & (trades.variant == "orh5")]
        assert sorted(tl5.arm.dropna()) == sorted(rn.ALL_ARMS) and tl5.mature.eq(1).all()
        rn.main(["report", "--data", str(data), "--small-out", str(small)])
        import pandas as pd
        rep = pd.read_csv(small / "discovery_report.tsv", sep="\t", keep_default_na=False, na_values=[""])
        r = rep[(rep.key == "spec") & (rep.cell == "C1") & (rep.K == "tl") & (rep.variant == "orh5") & (rep.arm == cb.PRIMARY_ARM)]
        assert len(r) == 1 and r.iloc[0].n == 1
        txt = (small / "discovery_report.txt").read_text()
        assert "tl" in txt.split("HEADLINE", 1)[1]
        # STEP 0 on the holdout: the K appears in the composition and in the go/no-go line
        hdata, _hb, _he, hcands = _syn_dir(tmp_path / "h", split="holdout", n_cands=4)
        rn.main(["step0-entries", "--data", str(hdata), "--workers", "1", "--small-out", str(tmp_path / "hsmall")])
        step0 = capsys.readouterr().out
        assert "orh5: k5=1, k10=1, full=1, tl=1" in step0 and "tl     orh5" in step0
        comp = self._read(hdata / "out" / "entries_holdout_composition.tsv")
        assert {r["K"] for r in comp} == {"k5", "k10", "full", "tl"} and len(comp) == 4 * len(rn.MINUTE_VARIANTS)
