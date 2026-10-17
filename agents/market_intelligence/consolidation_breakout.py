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

Reused (never re-implemented): `anticipation._MA_NEAR_PCT` (R), `anticipation.atr14_pct`,
`broker.exit_logic.adr20_pct_from_bars`, `flag_detector._DEAL_PIN_RANGE_THRESHOLD` (R),
`flag_detector._RANGE_CONTRACTION_MAX` (R), `constants.ENTRY_SLIPPAGE_PCT` (R).
MIRRORED, not imported, because `rs_engine` drags asyncpg + httpx into a pure module (the test
asserts equality against the real thing): `_percentile_ranks`, `MIN_PRICE`, `MIN_DOLLAR_VOL`.

Index convention: `i` is the session index of the WATCH NIGHT D inside a `DailyBars`. Every
feature about D uses bars <= i only. The breakout day is E = D + 1 (a later session).
Units: ADR20 and ATR14 are FRACTIONS of the close (0.05 = 5%) everywhere in this module.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date
from typing import Optional, Sequence

import numpy as np

from agents.market_intelligence.anticipation import (
    _MA_NEAR_PCT,
    atr14_pct as _anticipation_atr14_pct,
)
from agents.market_intelligence.broker.exit_logic import adr20_pct_from_bars
from agents.market_intelligence.constants import ENTRY_SLIPPAGE_PCT
from agents.market_intelligence.flag_detector import (
    _DEAL_PIN_RANGE_THRESHOLD,
    _RANGE_CONTRACTION_MAX,
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
PIVOT_KEYS = ("k5", "k10", "full")   # B: which pivot the cells and the breakout use — NO default,
                                     #    the primary is picked in the discovery read (P4)
CELLS = ("C0", "C1", "C2", "C3", "C4", "C5", "C6", "C7")

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
        """Sessions [lo, hi) — e.g. `bars.slice(E + 1, E + 1 + horizon)` is the forward walk input."""
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


def evaluate_watch(bars: DailyBars, i: int) -> Optional[dict]:
    """Watch-night structure at session `i`. None unless every C0 STRUCTURAL gate passes.

    Gates: >= 130 sessions of history; a prior move (P = highest high in [i-45, i-10], ties ->
    the latest; pole_low = lowest low in [P-40, P]; high(P)/pole_low - 1 >= 0.30); no new high
    since P; close >= SMA50; the deal-pin guard (median daily range of the last 5 sessions
    >= `flag_detector._DEAL_PIN_RANGE_THRESHOLD` — the MEDIAN arm only, not its `is_pin`, which also
    needs all 5 days under it). Raw price and liquidity are NOT checked here (`universe_ok`).

    Returns plain floats/ints/bools/ISO-date strings (json.dumps-safe). Key families:
      watch_date, i, close, pole_idx/pole_date/pole_high, pole_low/pole_low_idx/pole_low_date,
      prior_move, pole_sessions, base_len, base_low, base_depth,
      pivot_k5 / pivot_k10 / pivot_full  (+ _date, + _idx),
      sma10/sma20/sma50, sma20_ok, sma50_rising, higher_lows,
      range_recent5, range_early5, tightening_ratio, tightening_ok, median_range5,
      adr20, atr14 (fractions), trigger_bar_range_adr, inside_day.
    """
    n = len(bars)
    if not (0 <= i < n):
        raise IndexError(f"evaluate_watch: i={i} outside 0..{n - 1}")
    if i < MIN_HISTORY - 1:
        return None
    h, l, c = bars.h, bars.l, bars.c

    # prior move: P = the (latest) highest high in the window that leaves a 10..45 session base
    lo, hi = i - BASE_MAX_SESSIONS, i - BASE_MIN_SESSIONS
    P = lo + _argmax_last(h[lo:hi + 1])
    pole_high = float(h[P])
    if float(h[P + 1:i + 1].max()) > pole_high:          # a new high since P — not a base under P
        return None
    base_len = i - P
    assert BASE_MIN_SESSIONS <= base_len <= BASE_MAX_SESSIONS, base_len   # true by construction

    pole_seg = l[P - POLE_LOOKBACK:P + 1]
    pole_low = float(pole_seg.min())
    if not pole_low > 0.0:
        return None
    prior_move = pole_high / pole_low - 1.0
    if prior_move < PRIOR_MOVE_MIN:
        return None

    close_i = float(c[i])
    if not close_i > 0.0:
        return None
    sma50 = float(c[i - SMA_LONG + 1:i + 1].mean())
    if close_i < sma50:
        return None

    w = RECENT_WINDOW
    rng = (h[i - w + 1:i + 1] - l[i - w + 1:i + 1]) / c[i - w + 1:i + 1]
    median_range5 = float(np.sort(rng)[len(rng) // 2])   # same median as flag_detector._evaluate_deal_pin
    if median_range5 < _DEAL_PIN_RANGE_THRESHOLD:
        return None

    # ── passed C0: compute every feature ───────────────────────────────────────────────────────
    pole_low_idx = (P - POLE_LOOKBACK) + _argmin_last(pole_seg)
    base_low = float(l[P + 1:i + 1].min())

    def _pivot(window: int) -> tuple:
        a = i - window + 1
        j = a + _argmax_last(h[a:i + 1])
        return float(h[j]), j

    p5, p5_idx = _pivot(5)
    p10, p10_idx = _pivot(10)
    pf_idx = (P + 1) + _argmax_last(h[P + 1:i + 1])
    pf = float(h[pf_idx])

    sma10 = float(c[i - SMA_SHORT + 1:i + 1].mean())
    sma20 = float(c[i - SMA_MID + 1:i + 1].mean())
    sma50_prev = float(c[i - SMA50_SLOPE_SESSIONS - SMA_LONG + 1:i - SMA50_SLOPE_SESSIONS + 1].mean())

    early = h[P + 1:P + 1 + w] - l[P + 1:P + 1 + w]
    early_mean = float((early / c[P + 1:P + 1 + w]).mean())
    recent_mean = float(rng.mean())
    ratio = (recent_mean / early_mean) if early_mean > 0 else None

    bar20 = _bar_dicts(bars, i - ADR_WINDOW + 1, i)
    adr20 = adr20_pct_from_bars(bar20)
    atr_pct = _anticipation_atr14_pct(_bar_dicts(bars, i - ATR_WINDOW, i), ATR_WINDOW)
    if adr20 is None or not adr20 > 0.0:
        return None                                   # unusable bars in the window — abstain
    bar_range = (float(h[i]) - float(l[i])) / close_i

    return {
        "watch_date": bars.dates[i].isoformat(), "i": int(i), "close": close_i,
        "pole_idx": int(P), "pole_date": bars.dates[P].isoformat(), "pole_high": pole_high,
        "pole_low": pole_low, "pole_low_idx": int(pole_low_idx),
        "pole_low_date": bars.dates[pole_low_idx].isoformat(),
        "prior_move": prior_move, "pole_sessions": int(P - pole_low_idx),
        "base_len": int(base_len), "base_low": base_low, "base_depth": 1.0 - base_low / pole_high,
        "pivot_k5": p5, "pivot_k5_idx": int(p5_idx), "pivot_k5_date": bars.dates[p5_idx].isoformat(),
        "pivot_k10": p10, "pivot_k10_idx": int(p10_idx), "pivot_k10_date": bars.dates[p10_idx].isoformat(),
        "pivot_full": pf, "pivot_full_idx": int(pf_idx), "pivot_full_date": bars.dates[pf_idx].isoformat(),
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
    }


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
    a = i - DOLLAR_VOL_WINDOW + 1
    return bool(float(np.median(bars.c[a:i + 1] * bars.v[a:i + 1])) >= MIN_DOLLAR_VOL)


# ═══════════════════════════════════════════════════════════════════════════════════════════════
# 4. Cells
# ═══════════════════════════════════════════════════════════════════════════════════════════════
def _ge(x, thr) -> bool:
    return x is not None and x >= thr


def cell_flags(features: Optional[dict], ctx: dict, *, k: str) -> dict:
    """C0..C7 as post-hoc flags on one watch row (the plan's cell table). `k` ("k5" | "k10" |
    "full") selects the pivot the cell and the breakout use — NO default; the primary is chosen
    in the discovery read (P4). It enters C0 as the plan's "pivot" clause: the chosen pivot must
    exist and sit at or under high(P).

    ctx keys: rs_best (max of the three percentiles), rs_all (min of them — carried for the
    caller's "all three >= 98" variant, not read by C0..C7), grp_pct (None -> group cells False),
    phase_qqq_10_20, phase_spy_qqq_50. A missing/None RS reads False for every RS cell."""
    if k not in PIVOT_KEYS:
        raise ValueError(f"cell_flags: k must be one of {PIVOT_KEYS}, got {k!r}")
    if features is None:
        return {name: False for name in CELLS}
    pivot = features.get(f"pivot_{k}")
    c0 = bool(pivot is not None and 0.0 < pivot <= features["pole_high"])
    rs_best, grp = ctx.get("rs_best"), ctx.get("grp_pct")
    phase_a = bool(ctx.get("phase_qqq_10_20"))
    phase_b = bool(ctx.get("phase_spy_qqq_50"))
    base = (c0 and features["sma20_ok"] and features["sma50_rising"]
            and features["higher_lows"] and features["tightening_ok"])
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
    }


def breakout_key(ticker: str, features: dict, k: str) -> tuple:
    """One trade per (ticker, pivot date for k)."""
    if k not in PIVOT_KEYS:
        raise ValueError(f"breakout_key: k must be one of {PIVOT_KEYS}, got {k!r}")
    return (ticker, features[f"pivot_{k}_date"])


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
@dataclass(frozen=True)
class Arm:
    """One exit arm. kind "qm": optional partial then trail; kind "fixed": +target_r / stop over
    max_sessions. partial_frac 0 / partial_session None = no partial (and so no breakeven move)."""
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


def _build_arms() -> dict:
    arms = {}
    for frac in (1 / 3, 1 / 2):
        for sess in (3, 5):
            for trail in (10, 20):
                nm = f"p{int(round(frac * 100))}_s{sess}_t{trail}"
                arms[nm] = Arm(nm, "qm", frac, sess, trail)
    # sensitivity: the primary with the trail live from session 1 (before the partial)
    arms["p33_s3_t10_early"] = Arm("p33_s3_t10_early", "qm", 1 / 3, 3, 10, trail_before_partial=True)
    arms["trail10_only"] = Arm("trail10_only", "qm", 0.0, None, 10)
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
    `partial_session`'s close, after which stop <- max(stop, fill) rests from the NEXT session;
    (3) trail — close < SMA(trail_sma) over closes_before + fwd through j exits the remainder at
    the close; (4) j == horizon marks the remainder at the close ("censored"); if fwd runs out
    first it marks at the last close ("degraded").
    "fixed": target = fill + target_r x risk, pessimistic (a bar touching both -> the stop),
    max_sessions, then marked at the close ("time_exit"; "degraded" if fwd is shorter). A bar that
    gaps over the target fills AT the target, not the better open.

    Returns {status, realized_r, pnl_adr, sessions_held, events: [(j, kind, price, frac)]}.

    CALLER CONTRACT (P2 owns both):
      * `closes_before[-1]` MUST be E's own close. The module cannot check this; a series that
        stops at E-1 shifts every SMA a day (the #548 trap, at the call site). The runner asserts
        `closes_before[-1] == bars.c[E]` before calling.
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
    for j in range(1, min(int(horizon), n) + 1):
        oj, lj, cj = float(o[j - 1]), float(l[j - 1]), float(c[j - 1])
        # 1. the stop
        if oj <= stop_now or lj <= stop_now:
            px = oj if oj <= stop_now else stop_now
            events.append((j, "stop_gap" if oj < stop_now else "stop", px, remaining))
            pnl += (px - fill) * remaining
            return _outcome("stopped", pnl, risk, fill, adr20, j, events)
        # 2. the partial, at the close; the breakeven stop rests from the NEXT session
        if (not partial_done and arm.partial_session == j and arm.partial_frac > 0):
            events.append((j, "partial", cj, arm.partial_frac))
            pnl += (cj - fill) * arm.partial_frac
            remaining -= arm.partial_frac
            partial_done = True
            stop_now = max(stop_now, fill)
        # 3. the trail: first CLOSE below the SMA (today's close included)
        if trail_n and (partial_done or arm.partial_session is None or arm.trail_before_partial):
            pos = n_before + j                  # 1-based position of session j inside cs
            if pos - trail_n >= 0:
                sma = (cs[pos] - cs[pos - trail_n]) / trail_n
                if cj < sma:
                    events.append((j, "trail", cj, remaining))
                    pnl += (cj - fill) * remaining
                    return _outcome("trailed", pnl, risk, fill, adr20, j, events)
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
