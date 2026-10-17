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
