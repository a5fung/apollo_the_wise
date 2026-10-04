"""#394 C1 — the coil-finder tune probe (scripts/probes/_394_coil_tune.py) is itself tested.

The probe runs ONCE against prod (piped into the market container) and its verdict lines feed the
operator's sign-off on the hold cap / board ordering / orderliness demotion (methodology
docs/analysis/394_coil_tuning_methodology_2026-07-11.md §3). So the pure parts are pinned here — the
3a sweep rule, the 3b Spearman-gap rule, the 3c orderliness metric and quartile rule — and a fake
READ ONLY DB drives `main()` end to end on a hand-built cohort. No DB, no network, no model calls.
"""
from __future__ import annotations

import importlib.util
from datetime import date, timedelta
from pathlib import Path
from unittest.mock import AsyncMock

import pytest

from agents.market_intelligence.anticipation import COIL_HOLD_LIMIT, find_coil_setup

_PATH = Path(__file__).resolve().parent.parent / "scripts" / "probes" / "_394_coil_tune.py"
_spec = importlib.util.spec_from_file_location("coil_tune_394", _PATH)
cp = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(cp)


def _bars(closes, *, opens=None, hl=0.01):
    d0 = date(2026, 1, 1)
    out = []
    for k, c in enumerate(closes):
        out.append({"date": (d0 + timedelta(days=k)).isoformat(), "o": c if opens is None else opens[k],
                    "h": c * (1 + hl), "l": c * (1 - hl), "c": c, "v": 1e6, "o_missing": False})
    return out


_RUNUP = [100.0] * 30 + [100.0 + 3.0 * (k + 1) for k in range(10)]     # 100 -> 130, peak idx 39


# ─── live-code fidelity ───────────────────────────────────────────────────────────────────────────

def test_selftest_passes():
    assert cp.selftest() == 0


def test_probe_imports_the_live_coil_finder_not_a_copy():
    """The hold sweep must measure exactly what COIL_HOLD_LIMIT gates: the probe imports the live
    function object, so a change to find_coil_setup changes the probe with it."""
    assert cp.find_coil_setup is find_coil_setup
    assert cp.INCUMBENT_CAP == COIL_HOLD_LIMIT


def test_probe_uses_the_live_orderliness_score_so_the_stored_score_and_the_tables_are_one_definition():
    """#394 C2: the orderliness score the board stores IS the one the signed 2026-10-03 quartile
    tables were computed with — the probe imports the live functions (same objects, not copies), so
    the two cannot drift. (A probe that re-defined any of these after importing would not be `is`.)"""
    import agents.market_intelligence.anticipation as ant
    assert cp.orderliness_score is ant.orderliness_score
    assert cp.percentile is ant.percentile
    assert cp.rows_to_bars is ant.db_rows_to_bars        # the live loader flags a NULL open itself


@pytest.mark.parametrize("coil", [125.0, 118.0, 112.0])
def test_hold_retrace_equals_live_retrace_and_is_point_in_time(coil):
    bars = _bars(_RUNUP + [coil] * 15 + [140.0] * 5)          # a later breakout must not leak backwards
    i = 54
    t, peak = cp.hold_retrace(bars, i)
    live = find_coil_setup(bars[:i + 1], i)
    assert t == live["retrace"] and peak == live["peak_date"] == bars[39]["date"]
    assert abs(t - (130.0 - coil * 0.99) / 30.0) < 1e-9


def test_today_pct_mirrors_the_live_board_field():
    from agents.market_intelligence.anticipation import evaluate_coil_consolidation
    bars = _bars(_RUNUP + [125.0] * 14 + [125.5])
    row, _ = evaluate_coil_consolidation(bars)
    assert row is not None and cp.today_pct(bars, len(bars) - 1) == row["today_pct"]


# ─── 3c orderliness metric ────────────────────────────────────────────────────────────────────────

def test_orderliness_is_p95_overnight_gap_over_atr14_pct():
    closes = [100.0] * 30
    opens = list(closes)
    opens[21:26] = [100.0, 100.0, 101.0, 100.0, 103.0]          # gaps 0,0,1,0,3 %
    bars = _bars(closes, opens=opens)
    score, n, dropped = cp.orderliness_score(bars, 20, 25)
    assert n == 5 and dropped == 0
    assert score == pytest.approx(2.6 / 2.0)                      # P95 = 2.6 %, ATR14% = 2.0 %


def test_orderliness_window_is_strictly_after_the_anchor_and_ignores_later_bars():
    closes = [100.0] * 30
    opens = list(closes)
    opens[20] = 110.0                                             # the anchor day's own gap: excluded
    opens[27] = 120.0                                             # after the window: excluded
    bars = _bars(closes, opens=opens)
    score, n, _ = cp.orderliness_score(bars, 20, 25)
    assert n == 5 and score == pytest.approx(0.0)


def test_null_open_days_are_dropped_not_read_as_close_to_close_moves():
    closes = [100.0] * 24 + [104.0] + [104.0] * 5
    bars = _bars(closes)                                           # opens == closes (the live NULL fallback)
    bars[24]["o_missing"] = True                                   # day 24: close jumped 4 %, open unknown
    score, n, dropped = cp.orderliness_score(bars, 20, 26)
    assert dropped == 1 and n == 5 and score == pytest.approx(0.0)


def test_rows_to_bars_flags_a_null_open():
    raw = [{"trade_date": date(2026, 7, 1), "open_price": None, "high_price": 11, "low_price": 9,
            "close": 10, "volume": 5},
           {"trade_date": date(2026, 7, 2), "open_price": 10.5, "high_price": 11, "low_price": 9,
            "close": 10, "volume": 5}]
    b = cp.rows_to_bars(raw)
    assert b[0]["o_missing"] and b[0]["o"] == 10.0 and not b[1]["o_missing"]


# ─── 3a sweep rule ────────────────────────────────────────────────────────────────────────────────

def _spread(n, lo, hi):
    return [lo + (hi - lo) * k / (n - 1) for k in range(n)]


def test_3a_moves_to_the_tighter_cap_when_it_wins_inside_the_recall_guard():
    items = [(0.2, r) for r in _spread(40, -1.0, 2.0)] + [(0.45, -2.0)] * 12
    code, text = cp.hold_cap_verdict(cp.hold_cap_cells(items), items)
    assert code == "MOVE 40%" and "-> 40%" in text


def test_3a_recall_guard_blocks_a_cap_that_cuts_more_than_30_percent():
    items = [(0.2, 2.0)] * 10 + [(0.45, 0.2)] * 30
    assert cp.hold_cap_verdict(cp.hold_cap_cells(items), items)[0] == "KEEP"


def test_3a_recall_guard_boundary_is_inclusive_at_exactly_30_percent():
    items = [(0.2, r) for r in _spread(35, 0.0, 2.0)] + [(0.45, -3.0)] * 15   # 35/50 = 70 % kept
    assert cp.hold_cap_verdict(cp.hold_cap_cells(items), items)[0] == "MOVE 40%"


def test_3a_knife_edge_is_no_change():
    items = [(0.2, 0.5)] * 30 + [(0.45, -1.0)] * 40
    assert cp.hold_cap_verdict(cp.hold_cap_cells(items), items)[0] == "KNIFE-EDGE"


def test_3a_decisive_n_is_the_marginal_band_not_the_cell():
    items = [(0.2, r) for r in _spread(60, -1.0, 2.0)] + [(0.45, -2.0)] * 6
    code, text = cp.hold_cap_verdict(cp.hold_cap_cells(items), items)
    assert code == "INSUFFICIENT" and "6 rows" in text


def test_3a_widen_cell_equals_the_incumbent_when_nothing_above_the_cap_fired():
    items = [(0.3, r) for r in _spread(30, -1.0, 2.0)]
    cells = cp.hold_cap_cells(items)
    assert cells[1]["n"] == cells[2]["n"] and cells[1]["median_r"] == cells[2]["median_r"]
    assert cp.hold_cap_verdict(cells, items)[0] == "KEEP"


def test_3a_small_incumbent_cell_is_insufficient():
    items = [(0.3, 1.0)] * 9
    assert cp.hold_cap_verdict(cp.hold_cap_cells(items), items)[0] == "INSUFFICIENT"


# ─── 3b Spearman-gap rule ─────────────────────────────────────────────────────────────────────────

def test_spearman_matches_a_hand_computed_value_with_ties():
    assert cp.spearman([1, 1, 2, 3], [1, 2, 3, 4]) == pytest.approx(4.5 / (4.5 * 5.0) ** 0.5)


def test_3b_adopts_only_on_a_gap_of_at_least_015():
    assert cp.ordering_verdict({"(i) incumbent": 0.05, "(ii) rmv-led": 0.20}, 40)[0] == "ADOPT (ii)"
    assert cp.ordering_verdict({"(i) incumbent": 0.05, "(ii) rmv-led": 0.19}, 40)[0] == "KEEP"
    assert cp.ordering_verdict({"(i) incumbent": -0.30, "(iv) orderliness-demoted": -0.10}, 40)[0] == "ADOPT (iv)"
    # the best challenger is the one compared, not the first past the bar
    assert cp.ordering_verdict({"(i) incumbent": 0.0, "(ii) rmv-led": 0.2, "(iii) streak-led": 0.3},
                               40)[0] == "ADOPT (iii)"


def test_3b_needs_n20_and_a_defined_incumbent():
    assert cp.ordering_verdict({"(i) incumbent": 0.0, "(ii) rmv-led": 0.9}, 19)[0] == "INSUFFICIENT"
    assert cp.ordering_verdict({"(i) incumbent": None, "(ii) rmv-led": 0.9}, 40)[0] == "INSUFFICIENT"


def test_incumbent_ordering_is_the_live_board_order():
    """Live: ORDER BY tight_close_streak DESC NULLS LAST, today_pct ASC NULLS LAST."""
    rows = [{"streak": 3, "today_pct": 0.002}, {"streak": 3, "today_pct": 0.001},
            {"streak": None, "today_pct": 0.0}, {"streak": 5, "today_pct": 0.009}]
    keys = [cp.ordering_keys(r, False)["(i) incumbent"] for r in rows]
    assert sorted(range(4), key=lambda k: keys[k]) == [3, 1, 0, 2]


def test_ordering_iv_demotes_the_gappy_quartile_beneath_everything():
    a = cp.ordering_keys({"streak": 9, "today_pct": 0.0}, True)["(iv) orderliness-demoted"]
    b = cp.ordering_keys({"streak": 0, "today_pct": 0.05}, False)["(iv) orderliness-demoted"]
    assert b < a


# ─── 3c quartile rule ─────────────────────────────────────────────────────────────────────────────

def test_quartile_table_and_demotion_rule():
    scores = list(range(40))
    rs = [0.0] * 30 + [-1.0] * 10                                   # the 10 gappiest lose
    table, qi = cp.quartile_table(scores, rs)
    assert [t["n"] for t in table] == [10, 10, 10, 10] and table[3]["lo"] == 30
    top = [r for r, q in zip(rs, qi) if q == 3]
    rest = [r for r, q in zip(rs, qi) if q < 3]
    assert cp.demotion_verdict(top, rest)[0] == "DEMOTE"
    assert cp.demotion_verdict([-0.49] * 10, [0.0] * 30)[0] == "NO-DEMOTE"
    assert cp.demotion_verdict([-5.0] * 9, [0.0] * 30)[0] == "INSUFFICIENT"


def test_combine_verdicts_compares_actions_and_insufficient_does_not_vote():
    code, text = cp.combine_verdicts({"a": ("KEEP", ""), "b": ("INSUFFICIENT", "")})
    assert code == "NO CHANGE" and "not voting" in text and "b" in text
    code, text = cp.combine_verdicts({"a": ("KEEP", ""), "b": ("KNIFE-EDGE", "")})
    assert code == "NO CHANGE" and "knife-edge in b -> re-arm" in text
    assert cp.combine_verdicts({"a": ("KEEP", ""), "b": ("MOVE 40%", "")})[0] == "SPLIT"
    assert cp.combine_verdicts({"a": ("MOVE 40%", ""), "b": ("MOVE 40%", "")})[0] == "MOVE 40%"
    assert cp.combine_verdicts({"a": ("INSUFFICIENT", "")})[0] == "UNCHANGED"
    assert cp.action_of("INSUFFICIENT") == "UNCHANGED" and cp.action_of("NO-DEMOTE") == "NO CHANGE"


# ─── end to end on a fake READ ONLY DB ────────────────────────────────────────────────────────────

class _Tx:
    async def __aenter__(self):
        return self

    async def __aexit__(self, *a):
        return False


class _FakeConn:
    def __init__(self, data):
        self.data, self.sql = data, []

    def transaction(self, readonly=False):
        assert readonly, "the probe must read inside a READ ONLY transaction"
        return _Tx()

    async def fetch(self, sql, *args):
        self.sql.append(sql)
        for key, rows in self.data.items():
            if key in sql:
                return rows
        raise AssertionError(f"unexpected query: {sql[:80]}")


class _Acquire:
    def __init__(self, conn):
        self.conn = conn

    async def __aenter__(self):
        return self.conn

    async def __aexit__(self, *a):
        return False


class _Pool:
    def __init__(self, conn):
        self.conn = conn

    def acquire(self):
        return _Acquire(self.conn)


_D0 = date(2026, 5, 15)                 # bar 50 (the entry bar) = 2026-07-04, after the corrected-base cut


def _ticker_bars(tk, level, k):
    """runup 100 -> 130 (peak bar 39), a coil at `level` whose tail (k % 6 + 3 days) is flat so the
    tight-close streak varies, a Confirm breakout at bar 50, then a little drift. Coil opens gap by
    a ticker-specific amount so orderliness varies."""
    closes = list(_RUNUP)
    flat_from = 50 - (k % 6 + 3)
    for m in range(40, 50):
        closes.append(level if m >= flat_from or m % 2 == 0 else level * 1.01)
    closes.append(level * 1.03)                                      # bar 50: breakout, below the 130 peak
    closes += [level * 1.03] * 9
    out = []
    for i, c in enumerate(closes):
        o = c
        if 40 < i < 50 and i % 3 == 0:
            o = closes[i - 1] * (1 + 0.002 * (k % 7))
        out.append({"ticker": tk, "trade_date": _D0 + timedelta(days=i), "open_price": o,
                    "high_price": c * 1.01, "low_price": c * 0.99, "close": c, "volume": 1e6})
    return out


def _shadow(i, tk, *, mode, stop, r, origin="family_a", entry=None, anchor=None, outcome="stop"):
    return {"id": i, "ticker": tk, "anchor_date": anchor or _D0 + timedelta(days=39),
            "entry_date": entry or _D0 + timedelta(days=50), "entry_price": 100.0, "stop_price": 95.0,
            "stop_kind": stop, "entry_mode": mode, "origin": origin, "outcome": outcome,
            "realized_r": r if outcome else None, "realized_r_h12": None, "fwd_mfe_r": None,
            "rmv_5d": None, "rmv_15d": None, "range_pct": None, "vol_ratio": None,
            "vol_dryup_ratio": None, "regime_at_entry": "Neutral", "would_pass_quality": True}


@pytest.mark.asyncio
async def test_main_end_to_end_on_a_fake_db(monkeypatch, capsys):
    levels = [125.0, 123.0, 121.0, 119.0, 118.0, 117.0]             # retrace 0.21 .. 0.47
    bars, shadow, board = [], [], []
    i = 0
    for k in range(36):
        tk = f"C{k:02d}"
        bars += _ticker_bars(tk, levels[k % 6], k)
        mode, stop = (("confirm", "base_low") if k < 24 else ("anticipate", "coiled_low"))
        shadow.append(_shadow(i, tk, mode=mode, stop=stop, r=(k % 5) - 1.5))
        i += 1
    for k, tk in enumerate(("S0", "S1", "S2")):                     # too few to vote
        bars += _ticker_bars(tk, 120.0, k)
        shadow.append(_shadow(i, tk, mode="anticipate", stop="structural_low", r=1.0)); i += 1
    bars += _ticker_bars("NINE", 120.0, 1)
    shadow.append(_shadow(i, "NINE", mode="confirm", stop="base_low", r=9.0, origin="9m")); i += 1
    shadow.append(_shadow(i, "C00", mode="confirm", stop="base_low", r=4.0,
                          entry=date(2026, 6, 20))); i += 1           # pre-coil-finder era: excluded
    shadow.append(_shadow(i, "C01", mode="confirm", stop="base_low", r=None, outcome=None)); i += 1
    shadow.append(_shadow(i, "C02", mode="confirm", stop="base_low", r=0.5,
                          anchor=_D0 + timedelta(days=30))); i += 1   # wrong stored anchor -> fidelity alarm
    # the skip paths — each must be counted, none may abort the only prod capture:
    shadow.append(_shadow(i, "NOBARS", mode="confirm", stop="base_low", r=0.1)); i += 1  # no bars at all
    bad = _ticker_bars("BADBAR", 120.0, 2)
    bad[10]["high_price"] = None                                      # one unreadable row drops the ticker
    bars += bad
    shadow.append(_shadow(i, "BADBAR", mode="confirm", stop="base_low", r=0.2)); i += 1
    bars += [{"ticker": "FLAT", "trade_date": _D0 + timedelta(days=d), "open_price": 50.0,
              "high_price": 50.5, "low_price": 49.5, "close": 50.0, "volume": 1e6} for d in range(60)]
    shadow.append(_shadow(i, "FLAT", mode="confirm", stop="base_low", r=0.3)); i += 1    # no coil on recompute
    zero = _ticker_bars("ZERO", 120.0, 3)
    zero[45].update(open_price=0.0, high_price=0.0, low_price=0.0, close=0.0)          # degenerate bar
    bars += zero
    shadow.append(_shadow(i, "ZERO", mode="confirm", stop="base_low", r=0.4)); i += 1
    for k, tk in enumerate(("B0", "B1", "B2", "C01")):
        board.append({"ticker": tk, "anchor_date": _D0 + timedelta(days=39), "state": "coiled",
                      "tight_close_streak": 3 - k, "today_pct": 0.001 * k, "rmv_15d": 10.0 * k,
                      "last_eval": _D0 + timedelta(days=49)})
        if tk != "C01":
            bars += _ticker_bars(tk, 121.0, k)
    board.append({"ticker": "P0", "anchor_date": _D0 + timedelta(days=39), "state": "post_runup",
                  "tight_close_streak": 9, "today_pct": 0.0, "rmv_15d": 0.0,
                  "last_eval": _D0 + timedelta(days=49)})

    conn = _FakeConn({"FROM mi_consolidation_entry_shadow": shadow,
                      "FROM mi_anticipation_consolidation": board,
                      "FROM mi_daily_closes": bars})
    from agents.market_intelligence import db as dbmod
    monkeypatch.setattr(dbmod, "get_pool", AsyncMock(return_value=_Pool(conn)))

    assert await cp.main() == 0
    out = capsys.readouterr().out

    assert all(s.lstrip().upper().startswith("SELECT") for s in conn.sql), "read-only probe"
    assert out.index("MODULE IDENTITY") < out.index("POPULATION COMPOSITION") < out.index("VERDICT 3a")
    for label in ("confirm/base_low", "anticipate/coiled_low", "anticipate/structural_low", cp.POOLED):
        for knob in ("3a", "3b", "3c"):
            assert f"VERDICT {knob} [{label}]:" in out, (knob, label)
    assert "VERDICT 3a [anticipate/structural_low]: INSUFFICIENT" in out
    assert "TUNE COHORT: 44 settled family_a rows" in out             # 36 + 3 + wrong anchor + 4 skip paths
    fid = next(ln for ln in out.splitlines() if ln.startswith("  fidelity [confirm/base_low]"))
    assert "29 rows" in fid and "anchor mismatch 1 (4%)" in fid and "no coil on recompute 1" in fid
    assert "'no bars for ticker': 2" in fid and "'error:ZeroDivisionError': 1" in fid
    assert "ALARM: 1 tickers have unreadable bars and are skipped: BADBAR (TypeError)" in out
    assert "fidelity [anticipate/coiled_low]: 12 rows" in out and "anchor mismatch 0 (0%)" in out
    for knob in ("3a HOLD CAP", "3b RANK ORDERING", "3c ORDERLINESS demotion"):
        assert f"KNOB {knob}:" in out
    assert out.count("POOLING CHANGES VERDICT:") == 3
    board_out = out[out.index("TOP-5 BOARD"):out.index("KNOB VERDICTS")]
    assert "(i) incumbent              B0 B1 B2" in board_out           # C01 has an open shadow: graduated
    assert "C01" not in board_out and "P0" not in board_out
