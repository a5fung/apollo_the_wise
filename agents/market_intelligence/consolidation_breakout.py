"""#702 Consolidation Breakout — Qullamaggie's breakout as a SETUP in the consolidation family.

PURE core shared by the offline backtest (`scripts/probes/_cb_backtest/`, P2) and the nightly shadow
job (P6): no DB, no network, no file I/O, no logging, no clock. Everything here is a function of
the arrays it is handed, so the two callers cannot drift apart.

SETUP, not Confirm (CLAUDE.md "SETUP vs FAMILY"): it buys the opening-range high on the breakout
day and stops at the low of that day, capped at one ADR. Confirm buys the close above the base
high and stops at the base low. Never pooled.

Source of the rules: `docs/methodology/operator_shared_notes.md`, section "2026-10-17 —
Qullamaggie's BREAKOUT setup". Plan: `/Users/alvinfung/.claude/plans/soft-singing-hamster.md`.
MRNA (`tests/fixtures/htf_labelled_bars.psv`) is the canary.

Provenance of every constant (ADR 0013 / Gate 5, `scripts/gate_provenance_registry.py`). NOTHING
here is in the registry yet — that is P6, with the backtest-chosen values citing the P4
registration doc. The scan is registry-enumerated, so this module is not scanned until then.
  S = sourced verbatim in operator_shared_notes.md      R = REUSES an existing cited constant
  B = chosen by the backtest, NO source yet — an explicit argument or a named constant here,
      never presented as sourced
  P = fixed by the approved plan's Definitions table, not by the article

The TRENDLINE breakout level `tl` (#702 P1c): the operator's note of 2026-10-17 (`operator_shared_notes.md`,
"2026-10-17 — his note on the breakout ENTRY") says he often draws the flag with *"a down sloping trend line and
a breakout of that trend line"*, which *"may dictate a lower entry than what we call a breakout"*. The line is
S-class (his words, "down sloping trend line"); how it is anchored and drawn (through the pole top, the line that
keeps every later high on or under it, projected one session ahead) is the #702 P1c spec's reading of that sentence,
not his words, and the line is tested BESIDE the horizontal pivots, never instead of them. `TL_TOUCH_TOL` (0.5%) is B and TELEMETRY
ONLY: it feeds `tl_interior_touches`, which never gates.

Reused (never re-implemented): `anticipation._MA_NEAR_PCT` (R), `anticipation.atr14_pct`,
`anticipation.COIL_HOLD_LIMIT` (R: the signed Family A hold rule, 0.50), `broker.exit_logic.adr20_pct_from_bars`
(imported under the sanctioned `# exec-boundary-ok:` marker - exit_logic is PURE exit-ladder math, no Alpaca client,
no trade-state I/O, the same reuse `pivot_analysis` / `giveback_shadow` make),
`flag_detector._DEAL_PIN_RANGE_THRESHOLD` (R), `flag_detector._RANGE_CONTRACTION_MAX` (R),
`flag_detector._POLE_ARTIFACT_JUMP` / `_POLE_ARTIFACT_VOL_MULT` (R: the pole data-artifact guard's two literals,
named there so this module imports them),
`flag_detector._evaluate_fresh_pin` + `_PIN_HISTORY_DAYS` (R: the #502 fresh deal-pin layer, called
as shipped on the same 40 rows prod feeds it), `constants.ENTRY_SLIPPAGE_PCT` (R).
MIRRORED, not imported, because `rs_engine` drags asyncpg + httpx into a pure module (the test
asserts equality against the real thing): `_percentile_ranks`, `MIN_PRICE`, `MIN_DOLLAR_VOL`.
MIRRORED because the real thing wants DB-shaped dict rows (per-call cost x ~2M watch nights; the
test asserts equality against it): `flag_detector._flag_resolved_by` -> `_base_resolved`. The pole
data-artifact guard (`flag_detector.compute_flag_metrics`) is mirrored in `_pole_data_artifact` (a
numpy form of the same rule) over the imported constants.

SHARED PLUMBING (end of file, section 7): the small pure helpers the offline runner and the nightly
shadow both need (test symbols, the contiguity test, the breakout test, the forward-window cut, the
cross-section, the one-trade-per-base stamping, the maturity label, `walk_arms`) live here ONCE and are
imported by both, so a forward row and a backtest row for the same night cannot drift apart.

Index convention: `i` is the session index of the WATCH NIGHT D inside a `DailyBars`. Every
feature about D uses bars <= i only. The breakout day is E = D + 1 (a later session).
Units: ADR20 and ATR14 are FRACTIONS of the close (0.05 = 5%) everywhere in this module.
"""
from __future__ import annotations

import re
from collections import defaultdict
from dataclasses import dataclass
from datetime import date
from typing import Optional, Sequence

import numpy as np

from agents.market_intelligence.anticipation import (
    COIL_HOLD_LIMIT,
    _MA_NEAR_PCT,
    atr14_pct as _anticipation_atr14_pct,
)
from agents.market_intelligence.broker.exit_logic import adr20_pct_from_bars  # exec-boundary-ok: exit_logic is PURE exit-ladder math (no Alpaca client, no trade-state I/O) — reusing its tested adr20_pct_from_bars() instead of a mirror copy (F11 discipline), same pattern as pivot_analysis/flag_detector/giveback_shadow
from agents.market_intelligence.constants import ENTRY_SLIPPAGE_PCT
from agents.market_intelligence.flag_detector import (
    _DEAL_PIN_RANGE_THRESHOLD,
    _PIN_HISTORY_DAYS,
    _POLE_ARTIFACT_JUMP as POLE_ARTIFACT_JUMP,
    _POLE_ARTIFACT_VOL_MULT as POLE_ARTIFACT_VOL_MULT,
    _RANGE_CONTRACTION_MAX,
    _evaluate_fresh_pin,
    _BASE_AGE_MIN_WATCH,
    _RUNUP_MIN_RATIO,
    _FLAG_DEPTH_MIN,
)


# ── Structure constants ─────────────────────────────────────────────────────────────────────────
MIN_HISTORY = 130                # P: >= 130 sessions ending D (the 126-session RS return needs 127)
PRIOR_MOVE_MIN = 0.30            # S: "anywhere from 30-100%+"
BASE_MIN_SESSIONS = 10           # S: consolidation "usually 2 weeks to 2 months" (10..45 sessions)
BASE_MAX_SESSIONS = 45
POLE_LOOKBACK = 40               # P: pole_low = min low over [P-40, P]. The article says only
                                 #    "sometime in the past 1-3 months" — no verbatim source for 40.
SMA_SHORT, SMA_MID, SMA_LONG = 10, 20, 50
SMA50_SLOPE_SESSIONS = 10        # P: SMA50(i) > SMA50(i-10) is "rising"
RECENT_WINDOW = 5                # B: the 5-session windows (higher lows, tightening, deal-pin) —
                                 #    NO source yet; the plan marks the 5-session window as B
RS_HORIZONS = (21, 63, 126)      # S: "1-month, 3-month, 6-month" in sessions
ADR_WINDOW = 20                  # R: exit_logic.adr20_pct_from_bars takes the last 20 bars
ATR_WINDOW = 14                  # R: anticipation.atr14_pct
# R: the pole data-artifact guard in flag_detector.compute_flag_metrics (htf.md "Flagpole
#    data-artifact", Gemini 6/27): a one-session close jump > 1.50x on < 2.0x the window's mean volume
#    is a split / bad tick, not a pole. `POLE_ARTIFACT_JUMP` / `POLE_ARTIFACT_VOL_MULT` are IMPORTED
#    above from the detector's named constants (the one place the literals live).
# The C0 structural gates, in evaluation order — the names `explain_watch` reports. `close_nonpositive`
# is bad data (a zero close); it is listed so the vocabulary is closed.
WATCH_GATES = ("history", "prior_move", "close_above_pole_high", "close_nonpositive", "sma50",
               "deal_pin_median", "fresh_pin", "pole_artifact", "adr_unusable")

# ── Universe (MIRRORS of rs_engine; equality asserted in the tests) ─────────────────────────────
MIN_PRICE = 5.0                  # R: rs_engine.MIN_PRICE (RAW close, not the adjusted one)
MIN_DOLLAR_VOL = 10_000_000.0    # R: rs_engine.MIN_DOLLAR_VOL (operator-signed 2026-06-15, #286)
UNIVERSE_TICKER_RE = re.compile(r"[A-Z]{1,5}")
UNIVERSE_SECURITY_TYPES = frozenset({"CS", "ADRC"})
DOLLAR_VOL_WINDOW = 20

# ── Group RS / phase / cells (P = plan Definitions; B = backtest-chosen, no source yet) ─────────
GROUP_MIN_MEMBERS = 10           # P: "groups with < 10 members -> NULL"
PHASE_SLOPE_PRIMARY = 1          # B: slope S grid {1, 5}, primary 1 — chosen before the freeze
RS_BEST_PRIMARY = 98.0           # S: "the 1 or 2% of stocks that are up the most" -> >= 98th pct
RS_BEST_STRICT = 99.0            # B: C2
RS_BEST_LOOSE = 95.0             # B: C5
GROUP_PCT_MIN = 80.0             # B: C2 / C6
PRIOR_MOVE_STRICT = 0.50         # B: C2 (grid 0.30 / 0.50 / 1.00)
PIVOT_KEYS = ("k5", "k10", "full", "tl")   # B: which pivot the cells and the breakout use — NO default,
                                          #    the primary is picked in the discovery read (P4). k5/k10/full are
                                          #    HORIZONTAL levels; "tl" is the down-sloping trendline (S: his
                                          #    2026-10-17 note), projected one session ahead — see `_down_trendline`
TL_TOUCH_TOL = 0.005             # B, TELEMETRY ONLY: a base high within 0.5% under the line is an interior touch
CELLS = ("C0", "C1", "C2", "C3", "C4", "C5", "C6", "C7")      # the 8 DECIDING cells
REPORT_CELLS = ("C1_no_retrace", "C1_no_tightening", "HTF")     # reported beside C1, never deciding
KS = PIVOT_KEYS                                                # the runner's and the shadow's name for the four levels
CELL_NAMES = CELLS + REPORT_CELLS                              # the 8 deciding + 2 reported-only cells

# ── Entries / exits ─────────────────────────────────────────────────────────────────────────────
OPENING_RANGE_MINUTES = {"orh1": 1, "orh5": 5, "orh60": 60}   # S: "first 1-minute ... 5-minute ... 60-minute"
ENTRY_VARIANTS = ("orh1", "orh5", "orh60", "pivot")
MINUTE_DAILY_MISMATCH_MAX = 0.01     # P: minute-day vs daily high/low differing by > 1% abstains
EXIT_HORIZON = 120                   # P: 120 sessions, then marked at the close and called censored
FIXED_TARGET_R = 3.0                 # P: the HTF-shadow-comparable control, +3R / -1R over 12 sessions
FIXED_SESSIONS = 12
PRIMARY_ARM = "p33_s3_t10"


# ═══════════════════════════════════════════════════════════════════════════════════════════════
# Data shapes
# ═══════════════════════════════════════════════════════════════════════════════════════════════
@dataclass(frozen=True, eq=False)
class DailyBars:
    """Ascending daily bars. `eq=False`: numpy fields make a generated __eq__ ambiguous."""
    dates: list            # list[datetime.date], strictly ascending
    o: np.ndarray
    h: np.ndarray
    l: np.ndarray
    c: np.ndarray
    v: np.ndarray

    def __len__(self) -> int:
        return len(self.c)

    def slice(self, lo: int, hi: int) -> "DailyBars":
        """Sessions [lo, hi) — e.g. `bars.slice(E + 1, E + 2 + horizon)` is the forward walk input:
        horizon + 1 sessions, the extra one being the next open a trail signal on the horizon
        session fills at (see `walk_exit`'s CALLER CONTRACT)."""
        return DailyBars(self.dates[lo:hi], self.o[lo:hi], self.h[lo:hi], self.l[lo:hi],
                         self.c[lo:hi], self.v[lo:hi])


def daily_bars_from_arrays(dates, o, h, l, c, v) -> DailyBars:
    """Validate and freeze. Raises ValueError on a length mismatch, non-ascending dates or a
    non-finite value — a silent NaN would make every comparison False and read as a pass."""
    dates = list(dates)
    arrs = [np.asarray(x, dtype=float) for x in (o, h, l, c, v)]
    n = len(dates)
    if any(a.shape != (n,) for a in arrs):
        raise ValueError("daily bars: dates/o/h/l/c/v lengths differ")
    if any(dates[k] >= dates[k + 1] for k in range(n - 1)):
        raise ValueError("daily bars: dates must be strictly ascending")
    if not all(np.isfinite(a).all() for a in arrs):
        raise ValueError("daily bars: non-finite value")
    return DailyBars(dates, *arrs)


def daily_bars_from_rows(rows: Sequence[dict]) -> DailyBars:
    """From the list-of-dicts `anticipation.db_rows_to_bars` returns ({date,o,h,l,c,v,...}; `date`
    is an ISO string there)."""
    dates = [d if isinstance(d, date) else date.fromisoformat(str(d))
             for d in (r["date"] for r in rows)]
    return daily_bars_from_arrays(
        dates,
        [r["o"] for r in rows], [r["h"] for r in rows], [r["l"] for r in rows],
        [r["c"] for r in rows], [r["v"] for r in rows])


@dataclass(frozen=True, eq=False)
class MinuteBars:
    """Regular-hours minute bars of ONE session. `minute` = minutes since 09:30 ET (0..389),
    strictly ascending; gaps are allowed (a thin minute has no bar)."""
    minute: np.ndarray
    o: np.ndarray
    h: np.ndarray
    l: np.ndarray
    c: np.ndarray
    v: np.ndarray

    def __len__(self) -> int:
        return len(self.minute)


def minute_bars_from_lists(minute, o, h, l, c, v) -> MinuteBars:
    m = np.asarray(minute, dtype=np.int64)
    arrs = [np.asarray(x, dtype=float) for x in (o, h, l, c, v)]
    n = len(m)
    if any(a.shape != (n,) for a in arrs):
        raise ValueError("minute bars: lengths differ")
    if n and (m[0] < 0 or m[-1] > 389 or (np.diff(m) <= 0).any()):
        raise ValueError("minute bars: minute must be strictly ascending within 0..389")
    if not all(np.isfinite(a).all() for a in arrs):
        raise ValueError("minute bars: non-finite value")
    return MinuteBars(m, *arrs)


# ═══════════════════════════════════════════════════════════════════════════════════════════════
# 1. Per-ticker structure at watch night D
# ═══════════════════════════════════════════════════════════════════════════════════════════════
def _argmax_last(a: np.ndarray) -> int:
    """Index of the maximum; ties resolve to the LATEST index (np.argmax returns the first)."""
    return len(a) - 1 - int(np.argmax(a[::-1]))


def _argmin_last(a: np.ndarray) -> int:
    return len(a) - 1 - int(np.argmin(a[::-1]))


def _bar_dicts(bars: DailyBars, lo: int, hi: int) -> list:
    """{h,l,c} dicts for sessions [lo, hi] inclusive — the shape the reused helpers read."""
    return [{"h": float(bars.h[j]), "l": float(bars.l[j]), "c": float(bars.c[j])}
            for j in range(lo, hi + 1)]


def _dollar_vol_median(bars: DailyBars, i: int) -> float:
    """Median of close x volume over the DOLLAR_VOL_WINDOW sessions ending at `i` (split-invariant)."""
    a = i - DOLLAR_VOL_WINDOW + 1
    return float(np.median(bars.c[a:i + 1] * bars.v[a:i + 1]))


def _pole_top(h: np.ndarray, c: np.ndarray, lo: int, hi: int) -> int:
    """The pole top P in [lo, hi], stateless mirror of `flag_detector._find_pivot_high`'s #592
    rule: walking forward, a higher (or equal — ties go to the latest) high only becomes the top
    when the pole is still extending (fewer than `_BASE_AGE_MIN_WATCH` bars since the current
    top) or some CLOSE since the current top went above it (`_flag_resolved_by`). A wick over an
    unresolved top never becomes the top, however old it gets (the reviewer's #592 point: with a
    plain argmax, a wick 10+ sessions old became P and moved the base start into the base)."""
    T = lo
    for t in range(lo + 1, hi + 1):
        if h[t] >= h[T] and (t - T - 1 < _BASE_AGE_MIN_WATCH or bool((c[T + 1:t + 1] > h[T]).any())):
            T = t
    return T


def _down_trendline(bars: DailyBars, P: int, i: int) -> dict:
    """The down-sloping TRENDLINE breakout level (#702 P1c; his note 2026-10-17 in `operator_shared_notes.md`:
    *"a flag with a down sloping trend line and a breakout of that trend line"* — "a lower entry than what we
    call a breakout"). Bars <= i only; P is the module's pole top.

    The line passes through the ANCHOR A = the base's highest high over [P, i] (ties -> the earliest; this is the
    pole top P unless a later wick topped it — a wick does not end the base) with slope
        m = max over j in (A, i] of (high[j] - high[A]) / (j - A)        (units: price per session, <= 0)
    — the flattest line from the anchor that keeps every later high on or under it. The touch j* is the argmax
    (ties -> the LATEST bar, `_argmax_last`). Fewer than `_BASE_AGE_MIN_WATCH` (3) sessions after the anchor
    -> no line yet (`pivot_tl` None). m == 0 (a flat top) is a valid line.

    `pivot_tl` is the line's value on the NEXT session, high[P] + m x (i + 1 - P): the level a breakout on
    E = i + 1 must clear. The horizontal pivots are FIXED levels read off bars <= i; this one is PROJECTED one
    session ahead, which is why it sits `|m|` under the line's own value at i. A projected value that is not
    > 0 is no level either (None: the line has fallen through zero; not expected on a night that passes the C0
    gates — close >= SMA50 — and kept so a caller never sees a non-positive "pivot").

    Returns every `tl` key on every call (the runner derives its watch-table columns from the first row's keys):
      pivot_tl, pivot_tl_idx, pivot_tl_date   the level, and the touch it is drawn through (idx/date are
                                              aliases of tl_touch_*, here so `pivot_<k>_date` reads uniformly)
      tl_slope_pct        m / high[A], per session (<= 0)
      tl_anchor_idx / tl_anchor_date   the anchor A (given on every call)
      tl_touch_idx / tl_touch_date / tl_touch_is_today (j* == i)
      tl_interior_touches the number of base highs in (P, i) — neither the pole top nor the watch night — within
                          `TL_TOUCH_TOL` (0.5%) UNDER the line at their own session (j* itself counts when it is
                          interior)
    TELEMETRY (none of it gates). Every field but the anchor is None when there is no line."""
    h = bars.h
    # The line is drawn from the base's HIGHEST high (ties -> the earliest), which is the pole top unless a later
    # WICK topped it (a wick does not end the base, `_base_resolved`). Anchoring at P alone left ~31% of watch
    # nights with no line (a base high above high[P] makes the slope positive) - the 10-17 review finding.
    A = P + int(np.argmax(h[P:i + 1]))                                 # ties -> the EARLIEST: a flat top stays a flat line
    out = {"pivot_tl": None, "pivot_tl_idx": None, "pivot_tl_date": None, "tl_slope_pct": None,
           "tl_anchor_idx": int(A), "tl_anchor_date": bars.dates[A].isoformat(), "tl_touch_idx": None,
           "tl_touch_date": None, "tl_touch_is_today": None, "tl_interior_touches": None}
    if i - A < _BASE_AGE_MIN_WATCH:                                   # the highest high is (nearly) tonight: no line to draw yet
        return out
    hp = float(h[A])
    seg = h[A + 1:i + 1]
    slopes = (seg - hp) / np.arange(1, i - A + 1, dtype=float)       # (high[j] - high[A]) / (j - A), j = A+1 .. i
    k = _argmax_last(slopes)
    m = float(slopes[k])                                              # <= 0 by construction (A is the highest high)
    out["tl_slope_pct"] = (m / hp) if hp > 0.0 else None
    if not m <= 0.0:                                                  # NaN guard only
        return out
    pivot = hp + m * (i + 1 - A)
    if not pivot > 0.0:
        return out
    j_star = A + 1 + k
    line = hp + m * np.arange(1, i - A, dtype=float)                  # the line at the interior sessions A+1 .. i-1
    touches = int((np.abs(line - h[A + 1:i]) <= TL_TOUCH_TOL * np.abs(line)).sum())
    touch_date = bars.dates[j_star].isoformat()
    out.update(pivot_tl=float(pivot), pivot_tl_idx=int(j_star), pivot_tl_date=touch_date,
               tl_touch_idx=int(j_star), tl_touch_date=touch_date,
               tl_touch_is_today=bool(j_star == i), tl_interior_touches=touches)
    return out


def _base_resolved(c: np.ndarray, P: int, i: int, pole_high: float) -> bool:
    """Has any CLOSE in (P, i] gone ABOVE high[P]? Mirrors `flag_detector._flag_resolved_by`
    (the #592 fix): STRICT `>` on the close, a wick over the top does not count. The real
    function also returns True for fewer than `_BASE_AGE_MIN_WATCH` (3) bars since the pivot —
    a pole still extending; that branch can never fire here (base_len >= 10 by construction).
    The test asserts equality against the real function."""
    return bool((c[P + 1:i + 1] > pole_high).any())


def _fresh_pin_rows(bars: DailyBars, i: int) -> list:
    """The last `_PIN_HISTORY_DAYS` (40) sessions ending at `i`, NEWEST FIRST, in the keys
    `flag_detector._evaluate_fresh_pin` reads — exactly what `_check_deal_pin_signatures_batch`
    feeds it in prod (the sticky carry re-runs the evaluator on `rows[k:]`, so the row count is
    part of the verdict)."""
    lo = max(0, i - _PIN_HISTORY_DAYS + 1)
    return [{"high_price": float(bars.h[j]), "low_price": float(bars.l[j]),
             "close": float(bars.c[j]), "volume": float(bars.v[j])}
            for j in range(i, lo - 1, -1)]


def _pole_data_artifact(bars: DailyBars, P: int) -> bool:
    """True when a single session inside the pole window [P-40, P] closed > 1.50x the previous
    close on < 2.0x the window's mean volume (a split / bad tick, not a pole). Mirrors the guard in
    `flag_detector.compute_flag_metrics` (htf.md "Flagpole data-artifact", Gemini 6/27): strict `>`
    on the ratio, strict `<` on the volume, mean over the window INCLUDING the spike day, and no
    verdict when the mean volume is not positive. The detector's window is 40 bars
    [P-39, P]; this module's pole window is 41 [P-40, P] (the same one `pole_low` is read from) —
    a deliberate one-session difference, stated rather than hidden."""
    a = P - POLE_LOOKBACK
    avg = float(bars.v[a:P + 1].mean())
    if not avg > 0.0:
        return False
    prev, cur = bars.c[a:P], bars.c[a + 1:P + 1]
    safe = np.where(prev > 0.0, prev, 1.0)
    jump = (prev > 0.0) & (cur / safe > POLE_ARTIFACT_JUMP)
    return bool((jump & (bars.v[a + 1:P + 1] < POLE_ARTIFACT_VOL_MULT * avg)).any())


def explain_watch(bars: DailyBars, i: int) -> tuple:
    """`(features, failing_gate)` at session `i`: `(dict, None)` when every C0 STRUCTURAL gate
    passes, else `(None, <name of the FIRST gate that failed>)`. Gates, in evaluation order
    (`WATCH_GATES`):
      history              >= 130 sessions ending D
      prior_move           P = highest high in [i-45, i-10] (ties -> the latest); pole_low = lowest
                           low in [P-40, P]; high(P) / pole_low - 1 >= 0.30
      close_above_pole_high  NO CLOSE above high(P) in (P, i] — a wick over the top does not end
                           the base (mirrors the shipped HTF `_flag_resolved_by`, strict `>`)
      sma50                close >= SMA50
      deal_pin_median      median daily range of the last 5 sessions >=
                           `flag_detector._DEAL_PIN_RANGE_THRESHOLD` — the MEDIAN arm only, not its
                           `is_pin`, which also needs 5 sessions under it
      fresh_pin            `flag_detector._evaluate_fresh_pin` (the #502 layer: a welded 5-session
                           band AND an announcement-sized volume event — a days-old cash deal that the
                           median arm cannot see yet) is NOT firing on the 40 rows ending at i
      pole_artifact        no > 50% one-session close jump on < 2x volume inside the pole window
      adr_unusable         ADR20 over the last 20 bars is positive
    (Bad data: a non-positive pole low reports `prior_move`; a non-positive close reports
    `close_nonpositive` — never a real name.) Raw price and liquidity are NOT checked here
    (`universe_ok`).

    Returns plain floats/ints/bools/ISO-date strings (json.dumps-safe). Key families:
      watch_date, i, close, pole_idx/pole_date/pole_high, pole_low/pole_low_idx/pole_low_date,
      prior_move, pole_sessions, base_len, base_low, base_depth, retrace, retrace_ok,
      pivot_k5 / pivot_k10 / pivot_full  (+ _date, + _idx),
      pivot_tl (+ _date, + _idx = the touch; None when no down-sloping line exists — see `_down_trendline`),
      sma10/sma20/sma50, sma20_ok, sma50_rising, higher_lows,
      range_recent5, range_early5, tightening_ratio, tightening_ok, median_range5,
      adr20, atr14 (fractions), trigger_bar_range_adr, inside_day,
      fresh_pin (always False on a passing row) + fresh_pin_band_pct / fresh_pin_spike_x (the
      evaluator's own numbers — how close the name was to the gate),
    and TELEMETRY (none of it gates): tl_slope_pct / tl_touch_idx / tl_touch_date / tl_touch_is_today /
      tl_interior_touches (the trendline's slope, touch and interior touches), median_dollar_vol20, pole_max_gain_day / pole_max_gain,
      pole_day_vol_ratio, pole_max_gap, atr14_slope (= ATR14% at i / ATR14% at P+1, both as a
      fraction of that day's close — the unit of `atr14`)."""
    n = len(bars)
    if not (0 <= i < n):
        raise IndexError(f"evaluate_watch: i={i} outside 0..{n - 1}")
    if i < MIN_HISTORY - 1:
        return None, "history"
    h, l, c = bars.h, bars.l, bars.c

    # prior move: P = the pole top in the window that leaves a 10..45 session base (#592 walk, `_pole_top`)
    lo, hi = i - BASE_MAX_SESSIONS, i - BASE_MIN_SESSIONS
    P = _pole_top(h, c, lo, hi)
    pole_high = float(h[P])
    base_len = i - P
    assert BASE_MIN_SESSIONS <= base_len <= BASE_MAX_SESSIONS, base_len   # true by construction
    pole_seg = l[P - POLE_LOOKBACK:P + 1]
    pole_low = float(pole_seg.min())
    if not pole_low > 0.0:
        return None, "prior_move"
    prior_move = pole_high / pole_low - 1.0
    if prior_move < PRIOR_MOVE_MIN:
        return None, "prior_move"

    if _base_resolved(c, P, i, pole_high):               # price left the base through the top
        return None, "close_above_pole_high"

    close_i = float(c[i])
    if not close_i > 0.0:
        return None, "close_nonpositive"
    sma50 = float(c[i - SMA_LONG + 1:i + 1].mean())
    if close_i < sma50:
        return None, "sma50"

    w = RECENT_WINDOW
    rng = (h[i - w + 1:i + 1] - l[i - w + 1:i + 1]) / c[i - w + 1:i + 1]
    median_range5 = float(np.sort(rng)[len(rng) // 2])   # same median as flag_detector._evaluate_deal_pin
    if median_range5 < _DEAL_PIN_RANGE_THRESHOLD:
        return None, "deal_pin_median"

    fresh = _evaluate_fresh_pin(_fresh_pin_rows(bars, i))
    if fresh is not None and fresh["is_fresh_pin"]:
        return None, "fresh_pin"

    if _pole_data_artifact(bars, P):
        return None, "pole_artifact"

    bar20 = _bar_dicts(bars, i - ADR_WINDOW + 1, i)
    adr20 = adr20_pct_from_bars(bar20)
    if adr20 is None or not adr20 > 0.0:
        return None, "adr_unusable"                       # unusable bars in the window — abstain

    # ── passed C0: compute every feature ───────────────────────────────────────────────────────
    pole_low_idx = (P - POLE_LOOKBACK) + _argmin_last(pole_seg)
    base_low = float(l[P + 1:i + 1].min())
    retrace = (pole_high - base_low) / (pole_high - pole_low)    # share of the pole's range given back

    def _pivot(window: int) -> tuple:
        a = i - window + 1
        j = a + _argmax_last(h[a:i + 1])
        return float(h[j]), j

    p5, p5_idx = _pivot(5)
    p10, p10_idx = _pivot(10)
    pf_idx = (P + 1) + _argmax_last(h[P + 1:i + 1])
    pf = float(h[pf_idx])
    tl = _down_trendline(bars, P, i)          # the 4th breakout level: a down-sloping line, projected to D+1

    sma10 = float(c[i - SMA_SHORT + 1:i + 1].mean())
    sma20 = float(c[i - SMA_MID + 1:i + 1].mean())
    sma50_prev = float(c[i - SMA50_SLOPE_SESSIONS - SMA_LONG + 1:i - SMA50_SLOPE_SESSIONS + 1].mean())

    early = h[P + 1:P + 1 + w] - l[P + 1:P + 1 + w]
    early_mean = float((early / c[P + 1:P + 1 + w]).mean())
    recent_mean = float(rng.mean())
    ratio = (recent_mean / early_mean) if early_mean > 0 else None

    atr_pct = _anticipation_atr14_pct(_bar_dicts(bars, i - ATR_WINDOW, i), ATR_WINDOW)
    atr_at_base = _anticipation_atr14_pct(_bar_dicts(bars, P + 1 - ATR_WINDOW, P + 1), ATR_WINDOW)
    bar_range = (float(h[i]) - float(l[i])) / close_i

    # telemetry about the pole (none of it gates): the biggest single-session close gain inside
    # (pole_low_idx, P] — ties -> the earliest — its volume against the 20 sessions that ended the day
    # before the pole began, and the biggest overnight gap. Empty when the low sits on P itself.
    gain_day = gain = vol_ratio = max_gap = None
    if pole_low_idx < P:
        prev, cur = c[pole_low_idx:P], c[pole_low_idx + 1:P + 1]
        okp = prev > 0.0
        g = np.where(okp, cur / np.where(okp, prev, 1.0) - 1.0, -np.inf)
        k = int(np.argmax(g))
        if np.isfinite(g[k]):
            gain, gain_day = float(g[k]), bars.dates[pole_low_idx + 1 + k].isoformat()
            a0 = pole_low_idx - 20
            if a0 >= 0:
                base_vol = float(bars.v[a0:pole_low_idx].mean())
                vol_ratio = (float(bars.v[pole_low_idx + 1 + k]) / base_vol) if base_vol > 0 else None
            gaps = np.where(okp, bars.o[pole_low_idx + 1:P + 1] / np.where(okp, prev, 1.0) - 1.0, -np.inf)
            max_gap = float(gaps.max())

    return {
        "watch_date": bars.dates[i].isoformat(), "i": int(i), "close": close_i,
        "pole_idx": int(P), "pole_date": bars.dates[P].isoformat(), "pole_high": pole_high,
        "pole_low": pole_low, "pole_low_idx": int(pole_low_idx),
        "pole_low_date": bars.dates[pole_low_idx].isoformat(),
        "prior_move": prior_move, "pole_sessions": int(P - pole_low_idx),
        "base_len": int(base_len), "base_low": base_low, "base_depth": 1.0 - base_low / pole_high,
        "retrace": float(retrace), "retrace_ok": bool(retrace <= COIL_HOLD_LIMIT),
        "pivot_k5": p5, "pivot_k5_idx": int(p5_idx), "pivot_k5_date": bars.dates[p5_idx].isoformat(),
        "pivot_k10": p10, "pivot_k10_idx": int(p10_idx), "pivot_k10_date": bars.dates[p10_idx].isoformat(),
        "pivot_full": pf, "pivot_full_idx": int(pf_idx), "pivot_full_date": bars.dates[pf_idx].isoformat(),
        **tl,
        "sma10": sma10, "sma20": sma20, "sma50": sma50,
        "sma20_ok": bool(close_i >= (1.0 - _MA_NEAR_PCT / 100.0) * sma20),
        "sma50_rising": bool(sma50 > sma50_prev),
        "higher_lows": bool(float(l[i - w + 1:i + 1].min()) > base_low),
        "range_recent5": recent_mean, "range_early5": early_mean,
        "tightening_ratio": ratio,
        "tightening_ok": bool(ratio is not None and ratio <= _RANGE_CONTRACTION_MAX),
        "median_range5": median_range5,
        "adr20": float(adr20),
        "atr14": (float(atr_pct) / 100.0) if atr_pct is not None else None,   # atr14_pct is PERCENT
        "trigger_bar_range_adr": bar_range / float(adr20),
        "inside_day": bool(h[i] <= h[i - 1] and l[i] >= l[i - 1]),
        "fresh_pin": False,
        "fresh_pin_band_pct": float(fresh["band_pct"]) if fresh is not None else None,
        "fresh_pin_spike_x": float(fresh["vol_spike_x"]) if fresh is not None else None,
        # ── telemetry, never a gate ──
        "median_dollar_vol20": _dollar_vol_median(bars, i),
        "pole_max_gain_day": gain_day, "pole_max_gain": gain, "pole_day_vol_ratio": vol_ratio,
        "pole_max_gap": max_gap,
        "atr14_slope": (float(atr_pct) / float(atr_at_base)
                        if atr_pct is not None and atr_at_base is not None and atr_at_base > 0 else None),
    }, None


def evaluate_watch(bars: DailyBars, i: int) -> Optional[dict]:
    """Watch-night structure at session `i`: the features, or None unless every C0 STRUCTURAL gate
    passes. A thin wrapper over `explain_watch`, which also names the gate that failed."""
    return explain_watch(bars, i)[0]


# ═══════════════════════════════════════════════════════════════════════════════════════════════
# 2. Cross-sectional features (the caller computes these once per date and passes them in)
# ═══════════════════════════════════════════════════════════════════════════════════════════════
def rs_returns(bars: DailyBars, i: int) -> tuple:
    """(r21, r63, r126) = close[i] / close[i-h] - 1; None where i-h < 0 or the base close is 0."""
    out = []
    for hz in RS_HORIZONS:
        j = i - hz
        out.append(float(bars.c[i] / bars.c[j] - 1.0) if j >= 0 and bars.c[j] > 0 else None)
    return tuple(out)


def percentile_ranks(values: list) -> list:
    """0-100, None stays None. EXACT mirror of `rs_engine._percentile_ranks` (pos / (n-1) * 100,
    rounded to 1 dp, ties ranked in input order); the test asserts equality against it."""
    valid = [(k, v) for k, v in enumerate(values) if v is not None]
    if not valid:
        return values[:]
    sorted_vals = sorted(valid, key=lambda x: x[1])
    n = len(sorted_vals)
    rank_map = {k: round(pos / max(n - 1, 1) * 100.0, 1) for pos, (k, _) in enumerate(sorted_vals)}
    return [rank_map.get(k) for k in range(len(values))]


def sic2(sic_code) -> Optional[str]:
    """First two digits of a SIC code as a string; None if missing/unparseable. An int loses
    its leading zero (SIC 0100 -> 100), so ints are zero-padded to 4 digits first."""
    if sic_code is None:
        return None
    if isinstance(sic_code, float):
        if sic_code != sic_code or not sic_code.is_integer():     # NaN or fractional
            return None
        sic_code = int(sic_code)
    if isinstance(sic_code, bool):
        return None
    s = f"{sic_code:04d}" if isinstance(sic_code, int) else str(sic_code).strip()
    if len(s) < 2 or not s.isdigit():
        return None
    return s[:2]


def group_returns(member_r63: dict, min_members: int = GROUP_MIN_MEMBERS) -> dict:
    """{group: median 63-session return}; groups with fewer than `min_members` usable members are
    absent (NULL downstream -> the group cells read False)."""
    out = {}
    for g, vals in member_r63.items():
        usable = sorted(v for v in vals if v is not None)
        if len(usable) < min_members:
            continue
        m = len(usable)
        out[g] = usable[m // 2] if m % 2 else (usable[m // 2 - 1] + usable[m // 2]) / 2.0
    return out


def _sma_at(bars: DailyBars, j: int, n: int) -> Optional[float]:
    """Mean of the n closes ending at session j. None when fewer than n sessions of history exist
    (j - n + 1 < 0). A `j` past the last bar is a CALLER bug (a numpy slice would silently average
    a truncated window), so it raises IndexError — the same convention as `evaluate_watch`."""
    if j >= len(bars):
        raise IndexError(f"_sma_at: j={j} outside 0..{len(bars) - 1}")
    return float(bars.c[j - n + 1:j + 1].mean()) if j - n + 1 >= 0 else None


def phase_qqq_10_20(qqq: DailyBars, j: int, slope: int = PHASE_SLOPE_PRIMARY) -> bool:
    """SMA10(j) > SMA20(j) and both rose over `slope` sessions. `j` is the WATCH NIGHT (known
    before the breakout day's open). False when the history is too short to say; IndexError when
    `j` is past the last bar. The caller joins QQQ/SPY to the watch night by DATE (never by
    position) and owns that join. NOT in the article — an attributed addition
    (operator_shared_notes.md 2026-10-17); S is B-class."""
    if slope < 1:
        raise ValueError("phase slope must be >= 1")
    a10, a20 = _sma_at(qqq, j, SMA_SHORT), _sma_at(qqq, j, SMA_MID)
    b10, b20 = _sma_at(qqq, j - slope, SMA_SHORT), _sma_at(qqq, j - slope, SMA_MID)
    if None in (a10, a20, b10, b20):
        return False
    return bool(a10 > a20 and a10 > b10 and a20 > b20)


def phase_spy_qqq_50(spy: DailyBars, qqq: DailyBars, j_spy: int, j_qqq: int) -> bool:
    """The alternative phase rule (cell C7): SPY and QQQ both close above their own SMA50."""
    s, q = _sma_at(spy, j_spy, SMA_LONG), _sma_at(qqq, j_qqq, SMA_LONG)
    if s is None or q is None:
        return False
    return bool(spy.c[j_spy] > s and qqq.c[j_qqq] > q)


# ═══════════════════════════════════════════════════════════════════════════════════════════════
# 3. Universe
# ═══════════════════════════════════════════════════════════════════════════════════════════════
def raw_factor_for(on: date, splits: Sequence[tuple]) -> float:
    """adjusted close x factor = RAW close on `on`. `splits` = [(execution_date, split_to /
    split_from), ...]; the factor is the product of the ratios of splits executing AFTER `on`
    (a 10:1 forward split -> 10, a 1:10 reverse -> 0.1). On the execution date itself the
    price is already post-split, so that split is excluded."""
    f = 1.0
    for exec_date, ratio in splits:
        if not ratio > 0:
            raise ValueError(f"split ratio must be > 0, got {ratio!r}")
        if exec_date > on:
            f *= float(ratio)
    return f


def universe_ok(bars: DailyBars, i: int, *, raw_factor: float, ticker: str,
                security_type: Optional[str]) -> bool:
    """Common stock / ADR (unknown type admitted, as prod does); ticker ^[A-Z]{1,5}$; RAW close
    >= $5; 20-session median dollar volume >= $10M (split-invariant); >= 130 sessions."""
    if not (0 <= i < len(bars)) or i < MIN_HISTORY - 1:
        return False
    if not (isinstance(ticker, str) and UNIVERSE_TICKER_RE.fullmatch(ticker)):
        return False
    if security_type and security_type not in UNIVERSE_SECURITY_TYPES:
        return False
    if not float(bars.c[i]) * raw_factor >= MIN_PRICE:
        return False
    return bool(_dollar_vol_median(bars, i) >= MIN_DOLLAR_VOL)


# ═══════════════════════════════════════════════════════════════════════════════════════════════
# 4. Cells
# ═══════════════════════════════════════════════════════════════════════════════════════════════
def _ge(x, thr) -> bool:
    return x is not None and x >= thr


def cell_flags(features: Optional[dict], ctx: dict, *, k: str) -> dict:
    """C0..C7 (`CELLS`, the 8 DECIDING cells) plus the three REPORTED-only cells (`REPORT_CELLS`:
    `C1_no_retrace`, `C1_no_tightening` — C1 with that one structure term dropped — and `HTF`, the
    high-tight-flag subset of C0; shown beside C1 and never deciding) as post-hoc flags on one watch row. `k` ("k5" | "k10" | "full" | "tl") selects the
    pivot the cell and the breakout use — NO default; the primary is chosen in the discovery read
    (P4). It enters C0 as the plan's "pivot" clause: the chosen pivot must exist (for "tl": there must be
    a down-sloping line that night, `pivot_tl` not None). It no longer has
    to sit at or under high(P): a wick over the pole top is a real resistance level, and the base
    survives a wick (only a CLOSE above the top ends it, see `explain_watch`).

    C1 = C0 + SMA20 tolerance + rising SMA50 + higher lows + tightening + RETRACE <= 50% (Family A's
    signed hold rule) + RS best >= 98 + the QQQ 10/20 phase. C2..C7 inherit every term of it.

    ctx keys: rs_best (max of the three percentiles), rs_all (min of them — carried for the
    caller's "all three >= 98" variant, not read by C0..C7), grp_pct (None -> group cells False),
    phase_qqq_10_20, phase_spy_qqq_50. A missing/None RS reads False for every RS cell."""
    if k not in PIVOT_KEYS:
        raise ValueError(f"cell_flags: k must be one of {PIVOT_KEYS}, got {k!r}")
    if features is None:
        return {name: False for name in CELLS + REPORT_CELLS}
    pivot = features.get(f"pivot_{k}")
    c0 = bool(pivot is not None and pivot > 0.0)
    rs_best, grp = ctx.get("rs_best"), ctx.get("grp_pct")
    phase_a = bool(ctx.get("phase_qqq_10_20"))
    phase_b = bool(ctx.get("phase_spy_qqq_50"))
    core = bool(c0 and features["sma20_ok"] and features["sma50_rising"] and features["higher_lows"])
    base = bool(core and features["tightening_ok"] and features["retrace_ok"])
    c1 = bool(base and _ge(rs_best, RS_BEST_PRIMARY) and phase_a)
    c6 = bool(c1 and _ge(grp, GROUP_PCT_MIN))
    return {
        "C0": c0,
        "C1": c1,
        "C2": bool(c1 and features["prior_move"] >= PRIOR_MOVE_STRICT
                   and _ge(rs_best, RS_BEST_STRICT) and _ge(grp, GROUP_PCT_MIN)),
        "C3": bool(base and _ge(rs_best, RS_BEST_PRIMARY)),                    # C1 without phase
        "C4": bool(base and phase_a),                                           # C1 without RS
        "C5": bool(base and _ge(rs_best, RS_BEST_LOOSE) and phase_a),           # RS >= 95
        "C6": c6,
        "C7": bool(base and _ge(rs_best, RS_BEST_PRIMARY) and phase_b),         # SPY+QQQ > SMA50
        # reported beside C1, never deciding
        "C1_no_retrace": bool(core and features["tightening_ok"]
                              and _ge(rs_best, RS_BEST_PRIMARY) and phase_a),
        "C1_no_tightening": bool(core and features["retrace_ok"]
                                 and _ge(rs_best, RS_BEST_PRIMARY) and phase_a),
        # the HIGH-TIGHT-FLAG subset of C0, on flag_detector's own signed geometry (a >= 90% pole in its 40-session
        # window, a flag holding >= 75% of the pole top): reported so HTF bases get #702's entry x exit grid
        # (his 10-17 ruling lifted the EP-first hold; the HTF paper read re-opens on such a grid, #397)
        "HTF": bool(c0 and features["pole_high"] / features["pole_low"] >= _RUNUP_MIN_RATIO
                    and features["base_low"] >= _FLAG_DEPTH_MIN * features["pole_high"]),
    }


def breakout_key(ticker: str, features: dict, k: str) -> tuple:
    """One trade per (ticker, pivot date for k). For "tl" the pivot date is the line's TOUCH date."""
    if k not in PIVOT_KEYS:
        raise ValueError(f"breakout_key: k must be one of {PIVOT_KEYS}, got {k!r}")
    pivot_date = features[f"pivot_{k}_date"]
    if pivot_date is None:                       # only "tl" can: no down-sloping line that night, so no base to key
        raise ValueError(f"breakout_key: no {k} pivot on this row")
    return (ticker, pivot_date)


# ═══════════════════════════════════════════════════════════════════════════════════════════════
# 5. Entries
# ═══════════════════════════════════════════════════════════════════════════════════════════════
_NO_DAY0 = {"stopped": False, "exit_price": None, "exit_minute": None}


def _entry_row(status: str, reason: Optional[str], *, fill=None, stop=None, fill_minute=None,
               width_pct=None, level=None, day0=None) -> dict:
    return {"status": status, "reason": reason, "fill": fill, "stop": stop,
            "fill_minute": fill_minute, "width_pct": width_pct, "level": level,
            "day0": dict(day0 if day0 is not None else _NO_DAY0)}


def _check_adr(adr20) -> float:
    if adr20 is None or not adr20 > 0:
        raise ValueError(f"adr20 must be a positive fraction, got {adr20!r}")
    return float(adr20)


def day0_walk(minutes: MinuteBars, *, fill_minute: int, stop: float) -> dict:
    """Walk the rest of the breakout day (minutes AFTER the fill minute) against the stop.
    A minute that OPENS below the stop exits at that open (worse than -1R); else a minute whose
    low touches the stop exits at the stop. The first hit ends the trade."""
    after = minutes.minute > fill_minute
    hit = np.flatnonzero(after & ((minutes.l <= stop) | (minutes.o < stop)))
    if len(hit) == 0:
        return dict(_NO_DAY0)
    j = int(hit[0])
    op = float(minutes.o[j])
    return {"stopped": True, "exit_price": op if op < stop else float(stop),
            "exit_minute": int(minutes.minute[j])}


def _finish_entry(fill: float, stop: float, fill_minute: Optional[int], level: float,
                  adr20: float) -> Optional[dict]:
    """The two post-fill abstains, in spec order. None = clean."""
    if stop >= fill:
        return _entry_row("abstain", "stop_at_or_above_fill", fill=fill, stop=stop,
                          fill_minute=fill_minute, level=level)
    width = (fill - stop) / fill
    if width > adr20:
        return _entry_row("abstain", "too_wide", fill=fill, stop=stop, fill_minute=fill_minute,
                          width_pct=width, level=level)
    return None


def _entry_one(minutes: MinuteBars, name: str, pivot: float, adr20: float, slippage: float) -> dict:
    if name == "pivot":
        level, first_min = float(pivot), 0
    else:
        k = OPENING_RANGE_MINUTES[name]
        in_range = minutes.minute < k
        if not in_range.any():
            return _entry_row("abstain", "no_opening_range_minutes")
        level = max(float(minutes.h[in_range].max()), float(pivot))
        first_min = k
    hits = np.flatnonzero((minutes.minute >= first_min) & (minutes.h > level))
    if len(hits) == 0:
        return _entry_row("no_trigger", "no_minute_above_level", level=level)
    m = int(hits[0])
    op = float(minutes.o[m])
    fill = (level if op <= level else op) * (1.0 + slippage)
    stop = float(minutes.l[:m + 1].min())            # low of the day AT the fill; not the full day
    fill_minute = int(minutes.minute[m])
    bad = _finish_entry(fill, stop, fill_minute, level, adr20)
    if bad is not None:
        return bad
    return _entry_row("filled", None, fill=fill, stop=stop, fill_minute=fill_minute,
                      width_pct=(fill - stop) / fill, level=level,
                      day0=day0_walk(minutes, fill_minute=fill_minute, stop=stop))


def entry_variants(minutes: Optional[MinuteBars], *, pivot: float, adr20: float, day_high: float,
                   day_low: float, slippage: float = ENTRY_SLIPPAGE_PCT) -> dict:
    """{"orh1","orh5","orh60","pivot"} -> {status, reason, fill, stop, fill_minute, width_pct,
    level, day0}. status "filled" | "no_trigger" | "abstain". `day0` is meaningful only when
    filled; a too_wide abstain still carries fill/stop/width so the caller can run the
    cap-not-skip sensitivity (re-walk with `day0_walk` on a capped stop).

    Abstains, in order: no_minutes; minute_daily_mismatch (minute-day high/low off the daily's by
    > 1%); minute_high_below_pivot; [per variant] stop_at_or_above_fill; too_wide
    (width > adr20). Additive to the spec: no_opening_range_minutes (no bar inside the first k
    minutes, so ORH_k is undefined)."""
    adr20 = _check_adr(adr20)
    pre = None
    if minutes is None or len(minutes) == 0:
        pre = "no_minutes"
    elif (not day_high > 0 or not day_low > 0
          or abs(float(minutes.h.max()) - day_high) / day_high > MINUTE_DAILY_MISMATCH_MAX
          or abs(float(minutes.l.min()) - day_low) / day_low > MINUTE_DAILY_MISMATCH_MAX):
        pre = "minute_daily_mismatch"
    elif float(minutes.h.max()) <= pivot:
        pre = "minute_high_below_pivot"
    if pre is not None:
        return {name: _entry_row("abstain", pre) for name in ENTRY_VARIANTS}
    return {name: _entry_one(minutes, name, pivot, adr20, slippage) for name in ENTRY_VARIANTS}


def close_entry(daily_close: float, daily_low: float, pivot: float, adr20: float, *,
                slippage: float = ENTRY_SLIPPAGE_PCT) -> dict:
    """The daily CLOSE variant: fill = close x (1 + slip) when the close is above the pivot,
    stop = that day's low, the same width rule. No day-0 walk — the entry IS the close."""
    adr20 = _check_adr(adr20)
    if not daily_close > pivot:
        return _entry_row("no_trigger", "close_not_above_pivot", level=float(pivot))
    fill = float(daily_close) * (1.0 + slippage)
    stop = float(daily_low)
    bad = _finish_entry(fill, stop, None, float(pivot), adr20)
    if bad is not None:
        return bad
    return _entry_row("filled", None, fill=fill, stop=stop, width_pct=(fill - stop) / fill,
                      level=float(pivot))


# ═══════════════════════════════════════════════════════════════════════════════════════════════
# 6. Exits
# ═══════════════════════════════════════════════════════════════════════════════════════════════
TRAIL_FILLS = ("next_open", "close")


@dataclass(frozen=True)
class Arm:
    """One exit arm. kind "qm": optional partial then trail; kind "fixed": +target_r / stop over
    max_sessions. partial_frac 0 / partial_session None = no partial (and so no breakeven move).

    trail_fill: where a trail signal (a close under the SMA) is filled. "next_open" = the remainder
    sells at the OPEN of the next session (his 09-29 execution ruling: decide on the true close,
    sell in the next morning's opening auction — docs/setups/exit_discipline.md, #687); "close" =
    at the signal close (sensitivity only — it cannot be executed). Partials always fill at the
    session close. breakeven: move the stop to the fill after the partial (False = the
    tail-killer control, exit_discipline.md / 545). partial_if_profit: take the partial (and the
    breakeven) only when the partial session's close is above the fill; either way the trail arms
    from the NEXT session on."""
    name: str
    kind: str                                  # "qm" | "fixed"
    partial_frac: float = 0.0
    partial_session: Optional[int] = None
    trail_sma: Optional[int] = None
    target_r: Optional[float] = None           # fixed only
    max_sessions: Optional[int] = None         # fixed only
    trail_before_partial: bool = False         # False = the article: "sell 1/3 to 1/2 ... after
                                               # 3-5 days ... The rest trailed" - the trail arms only
                                               # once the partial is taken. True = sensitivity.
    trail_fill: str = "next_open"
    breakeven: bool = True
    partial_if_profit: bool = False

    def __post_init__(self):
        if self.trail_fill not in TRAIL_FILLS:
            raise ValueError(f"Arm {self.name!r}: trail_fill must be one of {TRAIL_FILLS}, got {self.trail_fill!r}")
        if self.partial_if_profit and (self.partial_session is None or not self.partial_frac > 0):
            raise ValueError(f"Arm {self.name!r}: partial_if_profit needs a partial")


def _build_arms() -> dict:
    arms = {}
    for frac in (1 / 3, 1 / 2):
        for sess in (3, 5):
            for trail in (10, 20):
                nm = f"p{int(round(frac * 100))}_s{sess}_t{trail}"
                arms[nm] = Arm(nm, "qm", frac, sess, trail)
    # sensitivity: the primary with the trail live from session 1 (before the partial)
    arms["p33_s3_t10_early"] = Arm("p33_s3_t10_early", "qm", 1 / 3, 3, 10, trail_before_partial=True)
    # sensitivity: the primary with the trail filled at the signal close instead of the next open
    arms["p33_s3_t10_close"] = Arm("p33_s3_t10_close", "qm", 1 / 3, 3, 10, trail_fill="close")
    # control: the primary without the breakeven move after the partial (545: breakeven = the tail-killer)
    arms["p33_s3_t10_nobe"] = Arm("p33_s3_t10_nobe", "qm", 1 / 3, 3, 10, breakeven=False)
    # sensitivity: partial (and breakeven) only if the session-3 close is above the fill; trail from session 4
    arms["p33_s3_t10_ifprofit"] = Arm("p33_s3_t10_ifprofit", "qm", 1 / 3, 3, 10, partial_if_profit=True)
    arms["trail10_only"] = Arm("trail10_only", "qm", 0.0, None, 10)
    # control: the entry stop held to the horizon, then marked — no partial, no trail
    arms["stop_only"] = Arm("stop_only", "qm")
    arms["fixed_3r_12"] = Arm("fixed_3r_12", "fixed", target_r=FIXED_TARGET_R,
                              max_sessions=FIXED_SESSIONS)
    return arms


ARMS = _build_arms()


def _outcome(status: str, pnl: float, risk: float, fill: float, adr20: float, held: int,
             events: list) -> dict:
    return {"status": status, "realized_r": pnl / risk, "pnl_adr": pnl / (fill * adr20),
            "sessions_held": int(held), "events": events}


def walk_exit(*, fill: float, stop: float, closes_before, fwd: DailyBars, arm: Arm, adr20: float,
              horizon: int = EXIT_HORIZON) -> dict:
    """Daily walk from E+1 (`fwd[0]`; session j = 1). E is session 0.

    `closes_before` = the stock's closes UP TO AND INCLUDING E, so SMA10/20 exist from E+1 — the
    #548 defect (`flag_detector._htf_management_replay` omits them) is not copied. R is measured
    against the ENTRY stop even after the stop moves to breakeven.

    "qm", per session j = 1..horizon, in order: (1) stop — open <= stop exits ALL remaining at
    the open (a gap is worse than -1R), else low <= stop exits at the stop; (2) the partial at
    `partial_session`'s close, after which stop <- max(stop, fill) rests from the NEXT session
    (not with `breakeven=False`; `partial_if_profit` takes the partial only on a close above the
    fill); (3) trail — close < SMA(trail_sma) over closes_before + fwd through j is a SIGNAL on
    the close of j. `trail_fill="next_open"` (the default, every grid arm): the remainder exits at
    the OPEN of session j+1 (event `(j+1, "trail", open, remaining)`, sessions_held j+1) — booked
    straight away, so the stop check of j+1 can never book it a second time; if fwd ends at j the
    signal cannot fill and the remainder is marked at the close of j ("degraded"); if j is the
    horizon the status is "censored", filled at the next open when fwd has it, else marked at the
    close of j. `trail_fill="close"`: exits the remainder at the close of j, status "trailed";
    (4) j == horizon marks the remainder at the close ("censored"); if fwd runs out first it marks
    at the last close ("degraded"). When the breakeven stop lands ABOVE the partial session's
    close (the partial sold below the fill) an event `(j, "be_above_close", close, 0.0)` follows
    the partial: the next session's open will take it out — a hidden one-day time stop the runner
    counts.
    "fixed": target = fill + target_r x risk, pessimistic (a bar touching both -> the stop),
    max_sessions, then marked at the close ("time_exit"; "degraded" if fwd is shorter). A bar that
    gaps over the target fills AT the target, not the better open.

    Returns {status, realized_r, pnl_adr, sessions_held, events: [(j, kind, price, frac)]}.

    CALLER CONTRACT (P2 owns both):
      * `closes_before[-1]` MUST be E's own close. The module cannot check this; a series that
        stops at E-1 shifts every SMA a day (the #548 trap, at the call site). The runner asserts
        `closes_before[-1] == bars.c[E]` before calling.
      * `fwd` = horizon + 1 sessions: `bars.slice(E + 1, E + 2 + horizon)`. The extra session is the
        next open a trail signal on the horizon session fills at (status "censored"); with exactly
        `horizon` rows that branch is unreachable and the signal falls through to the mark at the
        horizon close. The walk itself never reads past session `horizon` except for that open.
      * status "degraded" = fwd ran out before the horizon — an UNSETTLED mark, not an outcome.
        The runner excludes every "degraded" row from the decisive numbers (or counts it open).
        With no forward bars at all the remainder is marked at E's close (`closes_before[-1]`,
        sessions_held 0); with no closes at all it books nothing (realized_r 0.0, no events).

    TRAIL TIMING (ruled 2026-10-17 by the orchestrator, from the article's own sequence): on a
    partial arm the trail (step 3) arms only AFTER the partial - before it, only the entry stop
    (the low of the day at the fill) protects the trade. `trail_before_partial=True` (arm
    "p33_s3_t10_early") keeps the trail live from session 1 as a sensitivity. Arms without a
    partial ("trail10_only") trail from session 1."""
    adr20 = _check_adr(adr20)
    risk = float(fill) - float(stop)
    if not risk > 0:
        raise ValueError(f"walk_exit: stop {stop} must be below fill {fill}")
    fill, stop0 = float(fill), float(stop)
    o, h, l, c = fwd.o, fwd.h, fwd.l, fwd.c
    n = len(c)
    events: list = []
    pnl = 0.0                                   # sum of (exit - fill) * fraction
    last_before = float(np.asarray(closes_before, dtype=float)[-1]) if len(closes_before) else None

    if arm.kind == "fixed":
        target = fill + float(arm.target_r) * risk
        for j in range(1, min(int(arm.max_sessions), n) + 1):
            oj, hj, lj, cj = float(o[j - 1]), float(h[j - 1]), float(l[j - 1]), float(c[j - 1])
            if oj <= stop0 or lj <= stop0:      # pessimistic: touching both -> the stop
                px = oj if oj <= stop0 else stop0
                events.append((j, "stop_gap" if oj < stop0 else "stop", px, 1.0))
                return _outcome("stopped", (px - fill), risk, fill, adr20, j, events)
            if hj >= target:
                events.append((j, "target", target, 1.0))
                return _outcome("target", (target - fill), risk, fill, adr20, j, events)
            if j == int(arm.max_sessions):
                events.append((j, "mark", cj, 1.0))
                return _outcome("time_exit", (cj - fill), risk, fill, adr20, j, events)
        return _degraded(c, n, 1.0, 0.0, fill, risk, adr20, events, last_before)

    # ── "qm" ───────────────────────────────────────────────────────────────────────────────────
    trail_n = arm.trail_sma
    cs = None
    n_before = 0
    if trail_n:
        tail = np.asarray(closes_before, dtype=float)[-trail_n:]
        n_before = len(tail)
        cs = np.concatenate(([0.0], np.cumsum(np.concatenate((tail, c)))))
    remaining = 1.0
    stop_now = stop0
    partial_done = False
    next_open = arm.trail_fill == "next_open"
    for j in range(1, min(int(horizon), n) + 1):
        oj, lj, cj = float(o[j - 1]), float(l[j - 1]), float(c[j - 1])
        # 1. the stop
        if oj <= stop_now or lj <= stop_now:
            px = oj if oj <= stop_now else stop_now
            events.append((j, "stop_gap" if oj < stop_now else "stop", px, remaining))
            pnl += (px - fill) * remaining
            return _outcome("stopped", pnl, risk, fill, adr20, j, events)
        # 2. the partial, at the close; the breakeven stop rests from the NEXT session
        if (not partial_done and arm.partial_session == j and arm.partial_frac > 0
                and not (arm.partial_if_profit and not cj > fill)):
            events.append((j, "partial", cj, arm.partial_frac))
            pnl += (cj - fill) * arm.partial_frac
            remaining -= arm.partial_frac
            partial_done = True
            if arm.breakeven:
                stop_now = max(stop_now, fill)
                if stop_now > cj:               # partial sold under the fill: tomorrow's open takes it
                    events.append((j, "be_above_close", cj, 0.0))
        # 3. the trail: first CLOSE below the SMA (today's close included)
        if arm.partial_if_profit:               # trail arms from the session AFTER the partial session
            trail_live = j > arm.partial_session
        else:
            trail_live = partial_done or arm.partial_session is None or arm.trail_before_partial
        if trail_n and trail_live:
            pos = n_before + j                  # 1-based position of session j inside cs
            if pos - trail_n >= 0:
                sma = (cs[pos] - cs[pos - trail_n]) / trail_n
                if cj < sma:
                    if not next_open:
                        events.append((j, "trail", cj, remaining))
                        pnl += (cj - fill) * remaining
                        return _outcome("trailed", pnl, risk, fill, adr20, j, events)
                    if j < n:                   # session j+1 exists: sell the remainder at its open
                        opx = float(o[j])
                        events.append((j + 1, "trail", opx, remaining))
                        pnl += (opx - fill) * remaining
                        return _outcome("censored" if j == int(horizon) else "trailed", pnl, risk,
                                        fill, adr20, j + 1, events)
                    # no next open: fall through — the horizon mark below, or "degraded" after the loop
        # 4. the horizon
        if j == int(horizon):
            events.append((j, "mark", cj, remaining))
            pnl += (cj - fill) * remaining
            return _outcome("censored", pnl, risk, fill, adr20, j, events)
    return _degraded(c, n, remaining, pnl, fill, risk, adr20, events, last_before)


def _degraded(c: np.ndarray, n: int, remaining: float, pnl: float, fill: float, risk: float,
              adr20: float, events: list, last_before: Optional[float]) -> dict:
    """fwd ran out before the horizon: mark what is left at the last close we have — the last
    forward close, or with no forward bars at all E's own close (`last_before`). Only when there
    is no close anywhere is nothing booked (realized so far, 0). Either way the status stays
    "degraded": a mark, not a settled outcome."""
    if n > 0:
        last = float(c[n - 1])
        events.append((n, "mark", last, remaining))
        pnl += (last - fill) * remaining
    elif last_before is not None:
        events.append((0, "mark", last_before, remaining))
        pnl += (last_before - fill) * remaining
    return _outcome("degraded", pnl, risk, fill, adr20, n, events)


def day0_result_to_outcome(entry: dict, adr20: float) -> dict:
    """A trade the day-0 walk stopped, in the same shape `walk_exit` returns (status
    "stopped_day0"): -1R at the stop, worse on a gap. The caller books it; it never reaches the
    daily walk."""
    adr20 = _check_adr(adr20)
    d0 = entry.get("day0") or {}
    if entry.get("status") != "filled" or not d0.get("stopped"):
        raise ValueError("day0_result_to_outcome: entry is not a day-0 stop-out")
    fill, stop, px = float(entry["fill"]), float(entry["stop"]), float(d0["exit_price"])
    kind = "day0_gap" if px < stop else "day0_stop"
    return _outcome("stopped_day0", px - fill, fill - stop, fill, adr20, 0, [(0, kind, px, 1.0)])


# ═══════════════════════════════════════════════════════════════════════════════════════════════
# 7. Shared plumbing - ONE definition for the offline runner (`scripts/probes/_cb_backtest/runner.py`) and the
#    nightly shadow (`consolidation_breakout_shadow.py`). Pure, no I/O. Both import these; neither keeps a copy.
# ═══════════════════════════════════════════════════════════════════════════════════════════════
POLE_DRIFT_MAX = 3                        # B: poles <= this many sessions apart are ONE base (chain key); the
#                                           module's own pole-top rule lets the top walk forward while "still extending"
POLE_BAD_HIGH_X = 1.25                    # data flag, NEVER a gate: pole-bar high above this x max(open, close) is a suspect print

# Exchange test symbols (Nasdaq/NYSE/Arca/Cboe/IEX test securities). `universe_ok` admits an unknown-type ticker by
# design ("as prod does"), so the callers drop these before it. Fixed list + the Z?ZZ[TC] test family; every one of
# these is in the export with a fake price and ~no real volume.
TEST_SYMBOLS = frozenset({"ATEST", "CTEST", "MTEST", "NTEST", "PTEST", "ZTEST",
                          "ZBZX", "ZEXIT", "ZIEXT", "ZXIET"})
_TEST_FAMILY = re.compile(r"Z[A-Z]ZZ[TC]")

# A walk's terminal exits; anything else is an OPEN MARK until `is_mature` says otherwise.
TERMINAL_STATUSES = frozenset({"stopped", "stopped_day0", "trailed", "target", "time_exit"})


def resolve_sectype(ticker: str, mi_types: dict, sic_types: dict) -> str:
    """`mi_security_types` value, else the SIC pull's point-in-time `type`, else "" (unknown, admitted)."""
    return mi_types.get(ticker) or sic_types.get(ticker) or ""


def is_test_symbol(ticker: str) -> bool:
    """An exchange test security (ZVZZT, NTEST, ...): never a universe member, never in the RS denominator."""
    return ticker in TEST_SYMBOLS or bool(_TEST_FAMILY.fullmatch(ticker))


def contiguous_window_mask(cidx: np.ndarray, window: int) -> np.ndarray:
    """True at bar i when the `window` bars ending at i are CONSECUTIVE SPY sessions, i.e.
    cidx[i] - cidx[i-window+1] == window-1 (cidx is strictly ascending, so equality means no session is
    missing). Everything the module reads at a watch night - the 130-bar history, RS 21/63/126, SMA50, the
    pole window, ADR20 - sits inside the 130 bars ending at i, so one test here covers all of it. A hole
    inside the span means a halt, a data gap or a REUSED TICKER (two companies glued into one series)."""
    n = len(cidx)
    out = np.zeros(n, dtype=bool)
    span = window - 1
    if n > span:
        c = np.asarray(cidx, dtype=np.int64)
        out[span:] = (c[span:] - c[:n - span]) == span
    return out


def contiguous_tail(cidx, window: int) -> bool:
    """`contiguous_window_mask` at its LAST index: do the `window` bars ending at the last one form consecutive
    SPY sessions? (The nightly shadow tests tonight only.)"""
    return len(cidx) >= window and bool(contiguous_window_mask(cidx, window)[-1])


def fwd_end(cidx: np.ndarray, e: int, hi: int) -> tuple:
    """(end, cut): exclusive end index of the forward walk that starts after breakout bar `e` and would run to
    `hi` (exclusive). The walk stops BEFORE the first bar that follows a missing session, so it never reads
    across a hole (a delisted-and-reused ticker would otherwise be booked on another company's prices); the
    shortened window makes `walk_exit` end 'degraded' - an unsettled mark that the decisive numbers exclude."""
    end = min(hi, len(cidx))
    if end - e >= 2:
        brk = np.flatnonzero(np.diff(np.asarray(cidx[e:end], dtype=np.int64)) != 1)
        if len(brk):
            return e + 1 + int(brk[0]), True
    return end, False


def forward_window(bars: "DailyBars", cidx, e: int, horizon: int) -> tuple:
    """(fwd, cut): the forward walk input for breakout bar `e` = sessions E+1 .. E+1+horizon (horizon + 1 bars, the
    module's slice contract), cut before the first missing session. `cidx` None = no hole information (the
    window is only bounded by the bars)."""
    end, cut = fwd_end(cidx, e, e + 2 + horizon) if cidx is not None else (min(e + 2 + horizon, len(bars)), False)
    return bars.slice(e + 1, end), cut


def gap_fields(open_e: float, pivot: float, adr20: float) -> tuple:
    """(gap_open_pct, gap_over_1adr): open(E)/pivot - 1, and open(E) > pivot x (1 + adr20)."""
    return open_e / pivot - 1.0, bool(open_e > pivot * (1.0 + adr20))


def breaks_out(high_e: float, pivot) -> bool:
    """high(E) > pivot_K(D). A K with no level that night (`pivot` None: "tl" on a night with no down-sloping line)
    never breaks out - comparing against None would raise, and a missing level must not read as a break."""
    return pivot is not None and high_e > pivot


def is_mature(status: str, n_fwd: int, horizon: int = EXIT_HORIZON) -> bool:
    """Harvest row 6, per walk. MATURE = the walk reached a terminal exit before the data ended (stopped,
    stopped_day0, trailed, target, time_exit), or it reached the horizon with >= horizon + 1 forward sessions (the
    extra session is the next open a trail signal on the horizon session fills at). Anything else - 'degraded'
    (forward bars ran out), or a 'censored' mark with fewer than horizon + 1 sessions behind it - is an OPEN MARK:
    recorded, never in a decisive number."""
    if status in TERMINAL_STATUSES:
        return True
    return status == "censored" and n_fwd >= horizon + 1


def cross_section_one_date(r21: list, r63: list, r126: list, groups: list) -> tuple:
    """Cross-section for ONE date over the universe members (parallel lists; None allowed).
    rs_best = max of the three percentiles, rs_all = min (None if any is None); the group return is
    `group_returns` over members' r63 (groups < 10 members drop out), grp_pct = `percentile_ranks`
    of the group medians; a member without a (surviving) group reads None."""
    p = [percentile_ranks(list(r)) for r in (r21, r63, r126)]
    rs_best, rs_all = [], []
    for a, b, c in zip(*p):
        vals = [x for x in (a, b, c) if x is not None]
        rs_best.append(max(vals) if vals else None)
        rs_all.append(min(vals) if len(vals) == 3 else None)
    member_r63 = defaultdict(list)
    for g, r in zip(groups, r63):
        if g is not None:
            member_r63[g].append(r)
    gr = group_returns(member_r63)
    gp = dict(zip(gr.keys(), percentile_ranks(list(gr.values())))) if gr else {}
    grp = [gp.get(g) if g is not None else None for g in groups]
    return rs_best, rs_all, grp, len(gr)


def stamp_retrigger(cands: list, *, key=None, retrig: str = "retrigger", first: str = "first_") -> None:
    """ONE TRADE PER BASE (harvest row 1): per (ticker, pole_date, K) the first breakout (by E) is the
    trade (retrigger=0); later ones retrigger=1. Also `first_<cell>`: within the same base+K, the first
    breakout where THAT cell held on the watch night - a cell whose flag was off on the base's first
    break would otherwise lose its valid later entry to the base-level rule (reported beside, not the spec).
    `key`/`retrig`/`first` let the same stamping run under another base key (see `stamp_base_chain`)."""
    key = key or (lambda c: (c["ticker"], c["pole_date"], c["K"]))
    groups = defaultdict(list)
    for c in cands:
        groups[key(c)].append(c)
    for g in groups.values():
        g.sort(key=lambda c: c["E"])
        seen = set()
        for k, c in enumerate(g):
            c[retrig] = 0 if k == 0 else 1
            for cell in CELL_NAMES:
                if c[cell] and cell not in seen:
                    seen.add(cell)
                    c[first + cell] = 1
                else:
                    c[first + cell] = 0


def chain_bases(poles) -> dict:
    """{(ticker, pole_ci): base_id} from `poles` = iterable of (ticker, pole_ci, pole_date) over EVERY watch row.
    A ticker's distinct poles, sorted by calendar index, are cut into runs wherever two neighbours are more
    than POLE_DRIFT_MAX sessions apart; each run is ONE base, id = ticker|pole_date of its earliest pole.
    Why components over poles, not a walk over breakouts: the module's pole top can drift 1-3 sessions inside
    ONE consolidation, and (in real data) alternate between two poles from night to night, so a chain that
    follows breakouts in E order misses the revisit; a component is E-order independent and is a COARSENING of
    the spec key by construction (same pole_date -> same pole_ci -> same base)."""
    by_tk = defaultdict(dict)
    for ticker, pci, pdate in poles:
        by_tk[ticker][int(pci)] = pdate
    out = {}
    for ticker, pm in by_tk.items():
        base, prev = None, None
        for pci in sorted(pm):
            if prev is None or pci - prev > POLE_DRIFT_MAX:
                base = f"{ticker}|{pm[pci]}"
            out[(ticker, pci)] = base
            prev = pci
    return out


def stamp_base_chain(cands: list, base_of: dict) -> None:
    """Stamp the drift-robust key BESIDE the spec key: `base_id` (from `chain_bases`), `retrigger_chain`,
    `first_chain_<cell>` - the same one-trade-per-base stamping, keyed (base_id, K). Which key is the
    decisive population is a P4 ruling, made before the 30-trade go/no-go is read. Raises KeyError if a
    candidate's pole was not in the watch rows it came from (cannot happen by construction)."""
    for c in cands:
        c["base_id"] = base_of[(c["ticker"], int(c["pole_ci"]))]
    stamp_retrigger(cands, key=lambda c: (c["base_id"], c["K"]), retrig="retrigger_chain", first="first_chain_")


def walk_arms(entry: dict, *, closes_before, fwd: DailyBars, adr20: float, horizon: int = EXIT_HORIZON,
              arms: Optional[dict] = None) -> dict:
    """{arm name: `walk_exit`-shaped result} for ONE filled entry over `arms` (default: every arm in `ARMS`; the
    shadow passes only the arms not yet final). A day-0 stop-out is booked ONCE by `day0_result_to_outcome` and is the
    outcome of EVERY arm (it never reaches the daily walk); otherwise `walk_exit` runs per arm with
    `closes_before` = the closes through E (the caller guarantees its last is E's own close, `walk_exit`'s CALLER
    CONTRACT) and `fwd` the forward window. Raw results - each caller formats its own rows."""
    arms = ARMS if arms is None else arms
    if entry["day0"]["stopped"]:
        one = day0_result_to_outcome(entry, adr20)
        return {name: dict(one) for name in arms}
    return {name: walk_exit(fill=entry["fill"], stop=entry["stop"], closes_before=closes_before, fwd=fwd, arm=arm,
                            adr20=adr20, horizon=horizon)
            for name, arm in arms.items()}
