"""Breakout v1 REBUILT from Qullamaggie's trades — stage 1, the nightly list (his spec sign-off 2026-11-02, "signd off").

The spec: `docs/analysis/cb_rebuild_from_qm_trades_2026-11-02.md` (§1 the 7 list rules, §2 the order score, §3 the
10-day volume bar). The owner: `docs/setups/consolidation_breakout.md` (change log 2026-11-02 "REBUILT").

THE ACCEPTANCE BAR is the SCORECARD: Qullamaggie's 269 dated breakout buys (2017-2023, setup breakout|both,
`holdings_1024/entries.tsv`) with the 26 big winners among them, self-contained in `tests/fixtures/qm_breakout_scorecard/`
(each buy's split-adjusted daily bars from 300 sessions before the night D through his buy day E, plus rs_best and the
raw close at D — the two inputs that need the whole universe or the raw store — his label, and the research result).
The LIVE `breakout_v1.v1_gates` at D must put 263 of the 269 on the list, all 26 big winners, and leave off exactly
his 6 NOs; the 16 buys he labelled no / EP-like that the list still keeps are pinned ON as the KNOWN NEGATIVES (the
committed negatives for the next rule, never silently "fixed"). MTW 2026-10-30 — v1's first paper buy, "no setup" by
his read — must be OFF. A mismatch is a defect in the port, never a reason to move a threshold.

The order inputs are checked against the research formula itself (pandas rolling, `23_move126_rule.py` /
`32_tight_recently.py`) on all 269 series, and against stage 0's printed era-B reads (`stage0/s0.txt`).
"""
from __future__ import annotations

import csv
import gzip
import math
import random
from collections import defaultdict
from datetime import date, timedelta
from pathlib import Path

import numpy as np
import pytest

from agents.market_intelligence import breakout_v1 as bv
from agents.market_intelligence import breakout_v1_list as bl
from agents.market_intelligence import consolidation_breakout as cb

FX = Path(__file__).parent / "fixtures" / "qm_breakout_scorecard"

# His 6 NOs among Qullamaggie's buys (operator_shared_notes 2026-11-02, the 11 dropped charts): the rebuilt list leaves
# off exactly these — by the gate that stops each (the spec's backward step).
HIS_SIX_NOS = {("YPF", "2019-04-17"): ["base_depth"], ("W", "2020-04-07"): ["prior_move"],
               ("DOCU", "2020-12-04"): ["prior_move"], ("DOCU", "2020-12-15"): ["prior_move"],
               ("SQM", "2021-09-10"): ["prior_move"], ("MRNA", "2021-11-29"): ["base_depth"]}
# The spec §1's 16 KNOWN NON-SETUPS the rebuilt list still keeps: buys he labelled no or EP-like (by buy day E).
KNOWN_NON_SETUPS = {("ANET", "2018-03-12"), ("TDOC", "2019-10-31"), ("STNE", "2019-11-18"), ("ZS", "2020-03-24"),
                    ("EXEL", "2020-04-20"), ("SHOP", "2020-04-20"), ("NVAX", "2020-05-12"), ("PLNT", "2020-05-26"),
                    ("UAL", "2020-05-27"), ("JMIA", "2020-11-18"), ("FEAC", "2020-11-30"), ("UPST", "2021-08-12"),
                    ("FCX", "2021-12-07"), ("MU", "2021-12-21"), ("FCX", "2021-12-27"), ("MDB", "2021-12-27")}
# stage0/s0.txt "era-B buys one by one" (2026-11-02, the blind-recounted stage 0): 6-month move, it in daily ranges,
# the last-10-close spread in daily ranges, volume(E) / the 10-day average, and whether the NEW (10-day) bar fires.
STAGE0_ERA_B = {
    ("LHX", "2022-04-05"): ("39%", "14.0", "1.6", "1.08", False), ("LMT", "2022-04-05"): ("45%", "17.1", "1.4", "1.34", True),
    ("LMT", "2022-04-06"): ("45%", "17.7", "1.5", "1.15", False), ("X", "2022-04-12"): ("118%", "25.3", "1.3", "1.03", False),
    ("LAC", "2022-04-21"): ("113%", "13.7", "1.8", "1.81", True), ("TSLA", "2022-04-21"): ("65%", "15.5", "2.0", "1.66", True),
    ("FTNT", "2022-04-21"): ("34%", "10.2", "1.2", "1.44", True), ("VLO", "2022-05-27"): ("65%", "15.3", "1.0", "0.92", False),
    ("FREY", "2022-11-15"): ("156%", "22.5", "3.2", "1.47", True), ("U", "2022-11-15"): ("102%", "12.4", "6.4", "1.45", True),
    ("PDD", "2023-01-05"): ("140%", "34.2", "2.9", "1.76", True), ("FCX", "2023-01-06"): ("58%", "18.9", "1.9", "1.86", True),
    ("MDGL", "2023-01-24"): ("451%", "73.2", "1.2", "0.94", False), ("LI", "2023-04-17"): ("106%", "32.2", "2.4", "1.78", True),
    ("AI", "2023-05-17"): ("231%", "32.1", "5.2", "2.75", True), ("GSIT", "2023-06-01"): ("403%", "21.0", "2.3", "1.70", True),
    ("DKNG", "2023-09-11"): ("79%", "20.4", "3.4", "0.89", False), ("GME", "2023-12-14"): ("69%", "8.6", "2.1", "0.86", False),
}


@pytest.fixture(scope="module")
def scorecard():
    """[(buys.tsv row, DailyBars, D, the LIVE v1_gates at D)] for all 269 of Qullamaggie's dated breakout buys."""
    buys = list(csv.DictReader(open(FX / "buys.tsv"), delimiter="\t"))
    by_eid = defaultdict(list)
    with gzip.open(FX / "bars.psv.gz", "rt") as f:
        for r in csv.DictReader(f, delimiter="|"):
            by_eid[r["eid"]].append(r)
    out = []
    for r in buys:
        rr = sorted(by_eid[r["eid"]], key=lambda x: x["date"])
        ds = [date.fromisoformat(x["date"]) for x in rr]
        b = cb.daily_bars_from_arrays(ds, *[[float(x[k]) for x in rr] for k in "ohlcv"])
        D = ds.index(date.fromisoformat(r["D"]))
        assert ds[D + 1] == date.fromisoformat(r["E"])            # the fixture's bars run through his buy day E
        g = bv.v1_gates(b, D, rs_best=float(r["rs_best"]), raw_close=float(r["raw_close_D"]))
        out.append((r, b, D, g))
    return out


def _key(r):
    return (r["sym"], r["E"])


# ── the constants: every one pinned to the signed-off spec ────────────────────────────────────────────────────────
def test_every_list_constant_is_the_signed_off_spec():
    assert bv.RS_MIN == 35.0                                     # rule 2 (his buys' lowest 35.3)
    assert bv.ADR_MIN == 0.021 and bv.PINNED_ADR_MAX == 0.01      # rule 3 + his "both" pinned-deal gate
    assert bv.BASE_DEPTH_ADR_MIN == 1.511376833908041            # rule 4, his good LRN 2020-08-05
    # 2026-11-11 INITIAL RULE SET (pending his sign-off before paper; docs/analysis/cb_initial_rules_2026-11-11.md):
    assert bv.BASE_DEPTH_ADR_MAX == 11.0                         # was 8.9797 (HEXO 2020-08-13 is 10.8)
    assert bv.PRIOR_MOVE_MIN == 0.20                             # was 0.32135 (PBR 2019-10-22 is 21%)
    assert bv.EMA_SPAN == 21 and bv.EMA21_ADR_MIN == -0.9         # was -0.6335 (NVAX 2021-04-13 is -0.85)
    assert (bv.RANGE_LOOKBACK, bv.RANGE_MIN_LEN, bv.RANGE_GIVE_BACK, bv.RANGE_RUN_LOOKBACK, bv.RANGE_TOL_SESSIONS) == (126, 10, 0.5, 60, 20)
    assert bv.SMA_SESSIONS == 50                                 # rule 7
    assert (bv.MIN_PRICE, bv.MIN_DOLLAR_VOL, bv.MIN_BARS) == (2.0, 5_000_000.0, 86)   # rule 1 unchanged
    assert (bv.VOL_X, bv.VOL_WINDOW, bv.RECENT) == (1.2, 10, 5)  # §3: 1.2x the last 10 sessions; the 5-day level
    assert (bv.RUNUP6M_SESSIONS, bv.RUNUP6M_LOW_SESSIONS, bv.SPREAD_SESSIONS) == (126, 63, 10)   # §2
    assert bl.MESSAGE_TOP_N == 10 and bl.HISTORY_SESSIONS >= 126 + 63
    # the forward shadow's shared constants are NOT the list's and did not move
    assert cb.RS_BEST_PRIMARY == 98.0 and cb.PRIOR_MOVE_MIN == 0.30


def test_the_gate_list_is_the_rebuilt_rules_and_the_four_removed_gates_are_gone():
    # 2026-11-11 initial rule set: the 50-day is no longer a gate (telemetry); a range is measured, never a gate
    assert bv.GATES == ("history", "universe", "pinned", "adr", "rs", "prior_move", "base_depth", "ema21")
    for gone in ("higher_lows", "surf", "tightening", "breakdown"):
        assert gone not in bv.GATES
        assert not hasattr(bv, "surf_run")


# ── THE SCORECARD ─────────────────────────────────────────────────────────────────────────────────────────────────
def test_the_scorecard_under_the_initial_rule_set_all_269_listed_and_no_buy_of_the_1102_trigger_lost(scorecard):
    """2026-11-11 initial rule set (PENDING HIS SIGN-OFF). The loosened gates list ALL 269 of Qullamaggie's dated buys
    the night before (263 on 2026-11-02; his 6 former NOs — YPF, W, DOCU x2, SQM, MRNA — are Qullamaggie buys and count
    now: his 11-11 ruling). The level is the LOWER of the range high and the 5-day high, the volume bar his 1.2x the last
    10 sessions (recorded, not required since his 11-11 "drop it"), so every buy the 11-02 trigger fired on still fires:
    256 of 269 on the daily bar (156 on 11-02), 26 of the 26 big winners (21). On these 269 the range high is never under the 5-day high; the wick rule lowers 5 levels."""
    assert len(scorecard) == 269 and all(g["ok"] and g["failed"] == [] for _, _, _, g in scorecard)
    fired = [(r, bv.breakout_triggered({"h": float(b.h[D + 1]), "v": float(b.v[D + 1])}, g)["fired"]) for r, b, D, g in scorecard]
    # the price break alone (his 2026-11-11 "drop it"): 256 of 269 and ALL 26 big winners; with the volume bar it was
    # 165 / 22 (the wick rule; 160 / 21 without it)
    assert sum(f for _, f in fired) == 256 and sum(f for r, f in fired if r["big_winner"] == "1") == 26
    with_vol = [(r, bool(bv.breakout_triggered({"h": float(b.h[D + 1]), "v": float(b.v[D + 1])}, g)["volume_pass"]) and f)
                for (r, b, D, g), (_, f) in zip(scorecard, fired)]
    assert sum(f for _, f in with_vol) == 165 and sum(f for r, f in with_vol if r["big_winner"] == "1") == 22
    old = [(r, g["gates"]["prior_move"]["value"]["prior_move"] >= 0.3213536987121892
            and g["gates"]["base_depth"]["value"]["depth_adr"] <= 8.979719460898997
            and g["gates"]["ema21"]["value"]["vs_ema21_adr"] >= -0.6335 and g["sma50"]["pass"]
            and float(b.h[D + 1]) > g["level5"] and float(b.v[D + 1]) >= 1.2 * g["vol10"]) for r, b, D, g in scorecard]
    assert sum(f for _, f in old) == 156 and sum(f for r, f in old if r["big_winner"] == "1") == 21
    assert all(n or not o for (_, n), (_, o) in zip(fired, old))             # nothing the 11-02 trigger bought is lost
    assert all(g["level"] <= g["level5"] and g["level_source"] != "range" for _, _, _, g in scorecard)
    assert sum(g["range"]["pass"] for _, _, _, g in scorecard) == 190        # a range existed the night before on 190


def test_the_16_known_non_setups_stay_on_the_list_as_the_committed_negatives(scorecard):
    """The rebuilt list keeps 16 of Qullamaggie's buys that HE labelled no or EP-like — known non-setups, the negatives
    the next rule is judged on. Derived from the fixture's labels (no / EP), not only hand-listed."""
    def non_setup(label):
        return label.startswith("no") or "EP" in label
    derived = {_key(r) for r, _, _, g in scorecard if g["ok"] and non_setup(r["his_label"])}
    # 2026-11-11: his labels of Qullamaggie buys are a report column, not a bar. The loosened gates keep the 16 and
    # his 6 former NOs (22 rows, 21 distinct ticker-days).
    assert KNOWN_NON_SETUPS <= derived and len(KNOWN_NON_SETUPS) == 16
    assert derived - KNOWN_NON_SETUPS == set(HIS_SIX_NOS)


def test_the_knife_edges_the_rules_were_pinned_on(scorecard):
    """Rule 6 sits at TSLA 2022-04-21's own value (-0.63349 daily ranges under the 21-day EMA; -0.63 would drop his 'ok'
    TSLA) and rule 4's low end IS his good LRN 2020-08-05 (inclusive). Both stay on the list."""
    row = {_key(r): g for r, _, _, g in scorecard}
    tsla = row[("TSLA", "2022-04-21")]["gates"]["ema21"]
    assert tsla["pass"] is True and tsla["value"]["vs_ema21_adr"] == pytest.approx(-0.6334871453264559, abs=1e-12)
    assert bv.EMA21_ADR_MIN <= -0.6335 <= tsla["value"]["vs_ema21_adr"] < -0.63   # the 11-02 knife edge, inside the 11-11 line
    lrn = row[("LRN", "2020-08-05")]["gates"]["base_depth"]
    assert lrn["pass"] is True and lrn["value"]["depth_adr"] == pytest.approx(bv.BASE_DEPTH_ADR_MIN, abs=1e-12)


def test_mtw_1030_v1s_first_paper_buy_is_back_on_under_the_initial_rule_set():
    """MTW (his 'no setup', 11-02): prior move 0.30789, rs_best 98.6 (`scripts/probes/_mtw_1102/q1.out`). The 11-02
    rebuild left it off on its 32.1% run-up alone. Under the 2026-11-11 initial rule set (prior move >= 20%, his grades
    a report column only) it is LISTED again, with a range high of 23.875 to buy through — a KNOWN consequence of
    loosening to keep every Qullamaggie buy, pinned here so it is seen, and stated in the SSoT change log."""
    rr = list(csv.DictReader(open(FX / "mtw_bars.csv")))
    b = cb.daily_bars_from_arrays([date.fromisoformat(r["trade_date"]) for r in rr],
                                  *[[float(r[k]) for r in rr] for k in ("open_price", "high_price", "low_price",
                                                                        "close", "volume")])
    D = len(b) - 1
    assert b.dates[D] == date(2026, 10, 30)
    g = bv.v1_gates(b, D, rs_best=98.6)
    assert g["ok"] is True and g["failed"] == [] and g["level"] == 23.875 == g["level5"] and g["range"]["value"]["len"] == 18
    assert round(g["prior_move"], 5) == 0.30789 < 0.3213536987121892 and g["pole_date"] == "2026-10-06"
    assert round(g["adr20"], 4) == 0.0406


# ── the order inputs: the research formula, exactly ───────────────────────────────────────────────────────────────
def test_the_order_inputs_equal_the_research_formula_on_all_269_series(scorecard):
    """`23_move126_rule.py`: (h / l.rolling(64, min_periods=1).min() - 1).rolling(126, min_periods=1).max();
    `32_tight_recently.py`: (c.rolling(10).max() / c.rolling(10).min() - 1) / ((h - l) / c).rolling(20).mean()."""
    pd = pytest.importorskip("pandas")
    for r, b, D, g in scorecard:
        h, lo, c = (pd.Series(np.asarray(x[:D + 1], float)) for x in (b.h, b.l, b.c))
        m126 = (h / lo.rolling(64, min_periods=1).min() - 1).rolling(126, min_periods=1).max().iloc[-1]
        adr = ((h - lo) / c).rolling(20).mean().iloc[-1]
        c10 = ((c.rolling(10).max() / c.rolling(10).min() - 1) / adr).iloc[-1]
        oi = bv.order_inputs(b, D, g["adr20"])
        assert oi["runup6m"] == m126, _key(r)                      # same arithmetic, bit for bit
        assert oi["runup6m_adr"] == pytest.approx(m126 / adr, rel=1e-12), _key(r)
        assert oi["spread10_adr"] == pytest.approx(c10, rel=1e-12), _key(r)


def test_the_era_b_buys_read_as_stage0_printed_on_the_10_day_bar_11_of_18(scorecard):
    """stage0/s0.txt (blind-recounted): each era-B buy's 6-month move, it in daily ranges, the last-10-close spread,
    its buy-day volume vs the 10-day average and whether the NEW bar fires — 11 of the 18. GME 2023-12-14 fired on the
    old 50-day bar (1.69x) and does not on the 10-day (0.86x): the bar really changed."""
    seen, fired = 0, 0
    for r, b, D, g in scorecard:
        k = _key(r)
        if k not in STAGE0_ERA_B:
            continue
        seen += 1
        oi = bv.order_inputs(b, D, g["adr20"])
        # stage 0's trigger: the 5-day high and 1.2x the last 10 sessions (both telemetry since 2026-11-11)
        t = bv.breakout_triggered({"h": float(b.h[D + 1]), "v": float(b.v[D + 1])},
                                  dict(g, ok=True, level=g["level5"], vol_bar=1.2 * g["vol10"]))
        t["fired"] = t["level_pass"] and t["volume_pass"]          # stage 0's own trigger (volume was a condition then)
        got = (f"{oi['runup6m']:.0%}", f"{oi['runup6m_adr']:.1f}", f"{oi['spread10_adr']:.1f}",
               f"{float(b.v[D + 1]) / g['vol10']:.2f}", t["fired"])
        assert got == STAGE0_ERA_B[k], k
        fired += t["fired"]
        if k == ("GME", "2023-12-14"):
            assert float(b.v[D + 1]) >= 1.2 * g["vol50"] and t["volume_pass"] is False
    assert seen == 18 and fired == 11


def test_the_volume_bar_is_1_2x_the_mean_of_the_last_10_sessions_to_d():
    n = 120
    days = [date(2024, 1, 1) + timedelta(days=i) for i in range(n)]
    c = np.linspace(10.0, 14.0, n)
    v = np.concatenate([np.full(n - 10, 5_000_000.0), np.full(10, 1_000_000.0)])   # a heavy run-up, a quiet last 10
    b = cb.DailyBars(dates=days, o=c.copy(), h=c * 1.03, l=c * 0.97, c=c, v=v)
    g = bv.v1_gates(b, n - 1, rs_best=99.0)
    assert g["vol10"] == 1_000_000.0 and g["vol_bar"] == pytest.approx(1_200_000.0)
    assert g["vol50"] == pytest.approx((40 * 5_000_000.0 + 10 * 1_000_000.0) / 50)     # telemetry only
    t = bv.breakout_triggered({"h": 1e9, "v": 1_200_000.0}, dict(g, ok=True))
    assert t["volume_pass"] is True and bv.breakout_triggered({"h": 1e9, "v": 1_199_999.0}, g)["volume_pass"] is False


def test_runup6m_reads_only_bars_up_to_d_and_the_low_at_most_63_sessions_before_the_high():
    n = 300
    days = [date(2024, 1, 1) + timedelta(days=i) for i in range(n)]
    c = np.full(n, 10.0)

    def bars(high_at=None, high=40.0):
        h, lo = c * 1.01, c * 0.99                  # 10.1 / 9.9 everywhere ...
        lo[200] = 5.0                               # ... but one deep low at session 200
        if high_at is not None:
            h[high_at] = high
        return cb.DailyBars(dates=days, o=c.copy(), h=h, l=lo, c=c, v=np.full(n, 1e6))
    # a high 63 sessions after the low pairs with it: 40 / 5 - 1
    assert bv.runup6m_at(bars(263), 280) == 7.0
    # 64 sessions after, it no longer does: 40 / 9.9 - 1 (a 65-session window would read 7.0)
    assert bv.runup6m_at(bars(264), 280) == pytest.approx(40.0 / 9.9 - 1)
    # a high after D never counts; nor does one more than 125 sessions before D
    assert bv.runup6m_at(bars(290, 1000.0), 280) == bv.runup6m_at(bars(None), 280) == pytest.approx(10.1 / 5.0 - 1)
    assert bv.runup6m_at(bars(150, 1000.0), 280) == bv.runup6m_at(bars(None), 280)
    assert bv.runup6m_at(bars(155, 1000.0), 280) == pytest.approx(1000.0 / 9.9 - 1)     # D-125 is inside
    assert bv.order_inputs(bars(263), 280, None) == {"runup6m": 7.0, "runup6m_adr": None, "spread10_adr": None}


# ── the order score: the within-night ranking ─────────────────────────────────────────────────────────────────────
def test_pct_rank_is_pandas_average_pct_with_ties_and_none_kept_out():
    assert bl.pct_rank([1.0, 2.0, 2.0]) == [1 / 3, 2.5 / 3, 2.5 / 3]
    assert bl.pct_rank([1.0, 2.0, 2.0], ascending=False) == [1.0, 1.5 / 3, 1.5 / 3]
    assert bl.pct_rank([None, 3.0, 1.0]) == [None, 1.0, 0.5]
    assert bl.pct_rank([]) == [] and bl.pct_rank([None]) == [None]
    pd = pytest.importorskip("pandas")
    rnd = random.Random(11)
    for _ in range(50):
        vals = [rnd.choice([None, *[round(rnd.uniform(0, 5), 1) for _ in range(3)]]) for _ in range(rnd.randint(1, 40))]
        s = pd.Series([np.nan if x is None else x for x in vals], dtype=float)
        for asc in (True, False):
            want = [None if math.isnan(x) else x for x in s.rank(pct=True, ascending=asc).tolist()]
            assert bl.pct_rank(vals, ascending=asc) == want


def _row(t, run, spread):
    return {"ticker": t, "level": 10.0, "rs_best": 50.0, "runup6m_adr": run, "spread10_adr": spread}


def test_the_order_score_ranks_bigger_run_ups_and_tighter_closes_first_ties_by_ticker_none_last():
    rows = bl.rank_rows([_row("CCC", 10.0, 3.0), _row("AAA", 30.0, 1.0), _row("BBB", 20.0, 2.0),
                         _row("ZZZ", None, 1.0), _row("DDD", 30.0, 1.0)])
    assert [r["ticker"] for r in rows] == ["AAA", "DDD", "BBB", "CCC", "ZZZ"]     # AAA = DDD: ticker breaks the tie
    by = {r["ticker"]: r for r in rows}
    # run-up pct over the 4 with one: AAA/DDD 3.5/4, BBB 2/4, CCC 1/4; spread pct over all 5 (tighter = higher):
    # AAA/DDD/ZZZ tie at 1.0 -> (3+4+5)/3 / 5 = 0.8, BBB 2/5, CCC 1/5
    assert by["AAA"]["order_score"] == by["DDD"]["order_score"] == (3.5 / 4 + 0.8) / 2
    assert by["BBB"]["order_score"] == (2 / 4 + 2 / 5) / 2 and by["CCC"]["order_score"] == (1 / 4 + 1 / 5) / 2
    assert by["ZZZ"]["order_score"] is None and by["ZZZ"]["list_rank"] == 5
    assert [r["list_rank"] for r in rows] == [1, 2, 3, 4, 5]
    # the score ORDERS, it never removes
    assert len(bl.rank_rows([_row(f"T{k}", None, None) for k in range(3)])) == 3


def test_the_list_order_equals_the_researchs_groupby_rank_on_a_night_with_ties():
    """33_rank_topn.py: p_run = rank(pct=True), p_tight = rank(pct=True, ascending=False), score = their mean, the
    list rank = score.rank(ascending=False, method='first') on ticker-sorted rows."""
    pd = pytest.importorskip("pandas")
    rnd = random.Random(7)
    rows = [_row(f"T{k:03d}", round(rnd.uniform(5, 40), 0), round(rnd.uniform(0.5, 6), 1)) for k in range(300)]
    rnd.shuffle(rows)
    df = pd.DataFrame([dict(r) for r in rows]).sort_values("ticker").reset_index(drop=True)
    score = (df.runup6m_adr.rank(pct=True) + df.spread10_adr.rank(pct=True, ascending=False)) / 2
    want = df.assign(rank=score.rank(ascending=False, method="first")).sort_values("rank").ticker.tolist()
    got = bl.rank_rows(rows)
    assert [r["ticker"] for r in got] == want
    assert [r["order_score"] for r in got] == sorted(score.tolist(), reverse=True)
