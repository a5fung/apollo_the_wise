#!/usr/bin/env python3
"""STRUCTURE READ v3 — the supply ladder PLUS where-in-the-move the name already is.
(READ-ONLY · SHADOW ONLY · $0 · MEASUREMENT ONLY. Wired into nothing. Changes no rule, no
threshold, no toggle, no trade state. Any promotion is the operator's fork — THE LINE.)

WHY THIS EXISTS
---------------
Operator, 2026-08-25, restating the objective after the v2 read measured a null as a winner
predictor: *"The first bar I want it to clear is to filter out the bad charts, like CAPR. I
want to make sure we don't trade these poor charts, that's the first objective."*

Shown eleven of the read's worst calls he said ***"these are horrendous charts"*** — every
one of which v2 scored CLEAR_AIR — and added the qualification that names the mechanism:
***"some of them are ok'ish if the EP alert day was earlier, e.g. CAR on 4/1."*** The same
ticker is a good chart early in its move and a horrendous one after it has run. The labels
are in `tests/fixtures/must_not_trade_charts.py`.

THE MECHANISM, FROM `docs/analysis/structure_read_backtest_2026-08-25.md` §6
---------------------------------------------------------------------------
Of six CLEAR_AIR names that then fell 24-98%, four had already run 77-242% in the prior five
sessions. **A stock that has just run 200% has nothing overhead because it already ate it
all.** "Nothing overhead" and "extended" are the same chart, and v2 scores that chart as
clean because it has no input for where in the move the name is. That input is what v3 adds.

WHAT IS REUSED, NOT RE-IMPLEMENTED (P15)
----------------------------------------
  * `_structure_read_v2.structure_read_v2` — the whole supply read, imported UNCHANGED. Not
    one v2 parameter is adjusted here; v3 only appends fields and composes a verdict.
  * The LIVE extension rule is replicated to the line, not approximated: `ep_detector.py`
    fetches `MIN(close)` over `[alert_date - 10 calendar days, alert_date)` and skips when
    `(prev_close - MIN) / MIN * 100 >= MAX_EXTENSION_PCT` (75.0 since 2026-08-22,
    operator-signed; 50.0 before). `extension_live_pct()` below computes exactly that, from
    the same bars, so "what does v3 add BEYOND the rule we already have" is answerable
    rather than rhetorical. `MAX_EXTENSION_PCT` is IMPORTED from the live module — if the
    operator moves it, this file moves with it.

NEW HERE — the run-up family. Four members, all pre-registered before any count was seen,
each a different reading of "where in the move":
  1. `ext_close_pct(n)`   — the live rule's own shape at other windows: prev close against
                            the MIN CLOSE of the last n sessions, in percent. n=5 is the
                            live window; 10/20/60 are the same question asked further back.
  2. `runup_low_pct(n)`   — prev close against the MIN LOW of the last n sessions. Uses the
                            true intraday low, so a name that wicked down and recovered is
                            measured from where it actually traded.
  3. `runup_adr(n)`       — the same run, divided by ADR20 in price units: "how many typical
                            daily ranges has this name already travelled?" Volatility- and
                            price-normalised, so a $2 microcap and a $300 large cap are on
                            one scale. This is the member with no absolute-percent basis.
  4. `pct_of_52w_range`   — where the prior close sits inside the whole captured high-low
                            range, 0.0 at the low, 1.0 at the high. The crudest possible
                            "where in the move" and included precisely as a floor to beat.

⚠ NO CUTLINE IS CHOSEN IN THIS FILE. `verdict()` takes the cutline as an argument and has no
default. Every number in `docs/analysis/structure_read_v3_2026-08-25.md` is reported as a
sweep across the whole range; the only distinguished value is the operator-signed 75.0
carried over unchanged, which was chosen by him and not by this study.

NO LOOKAHEAD — inherited from v2, which ASSERTS its bar list contains nothing dated on or
after the alert date, and re-asserted here. Every field below reads prior bars plus the
alert-day OPEN (known at 09:30, which is when admission decides). The alert-day
high/low/close/volume are never read.
"""
from __future__ import annotations

import sys
from datetime import date, timedelta
from pathlib import Path

HERE = Path(__file__).resolve().parent
_REPO = HERE.parents[1]
if str(_REPO) not in sys.path:
    sys.path.insert(0, str(_REPO))
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))

import _structure_read_v2 as V2  # noqa: E402  (the supply read, imported unchanged)

from agents.market_intelligence.ep_detector import MAX_EXTENSION_PCT  # noqa: E402

# The live gate's own window, in CALENDAR days — `ep_detector.py` uses
# `window_start = today - timedelta(days=10)`, commented "~5 trading days + buffer".
LIVE_EXT_WINDOW_DAYS = 10

# The run-up windows reported. 5 is the live rule's own reach; the rest ask the same
# question further back, which is what the CAR 04-01 / 04-21 / 04-22 case needs.
RUNUP_WINDOWS = (5, 10, 20, 60)


# ── the live extension rule, replicated to the line ───────────────────────────────────
def extension_live_pct(bars: list[dict], alert_date: date) -> float | None:
    """EXACTLY what `ep_detector.py` computes for its extension skip, from the same bars.

    `MIN(close)` over `[alert_date - 10 calendar days, alert_date)`, then
    `(prev_close - MIN) / MIN * 100`. Returns None when the window is empty or the prior
    close is missing — which is how the live gate behaves too (`extension_map.get(ticker)`
    returns None and the check is skipped, i.e. the name PASSES).
    """
    if not bars:
        return None
    start = alert_date - timedelta(days=LIVE_EXT_WINDOW_DAYS)
    win = [b for b in bars if start <= b["trade_date"] < alert_date]
    closes = [float(b["close"]) for b in win if b.get("close")]
    prev_close = float(bars[-1]["close"]) if bars[-1].get("close") else None
    if not closes or not prev_close:
        return None
    lo = min(closes)
    return None if lo <= 0 else (prev_close - lo) / lo * 100.0


def blocked_by_live_extension_rule(bars: list[dict], alert_date: date,
                                   cap: float = MAX_EXTENSION_PCT) -> bool:
    """Would the extension gate ALREADY have killed this name-day? Fail-open like the live
    gate: an uncomputable extension is not a block."""
    e = extension_live_pct(bars, alert_date)
    return e is not None and e >= cap


# ── the run-up family ─────────────────────────────────────────────────────────────────
def ext_close_pct(bars: list[dict], n: int) -> float | None:
    """Prior close against the MIN CLOSE of the last n sessions, in percent.
    The live rule's own shape, asked over an explicit number of TRADING sessions."""
    win = bars[-n:]
    closes = [float(b["close"]) for b in win if b.get("close")]
    if not closes or not bars[-1].get("close"):
        return None
    lo = min(closes)
    return None if lo <= 0 else (float(bars[-1]["close"]) - lo) / lo * 100.0


def runup_low_pct(bars: list[dict], n: int) -> float | None:
    """Prior close against the MIN LOW of the last n sessions, in percent."""
    win = bars[-n:]
    lows = [float(b["low_price"]) for b in win if b.get("low_price")]
    if not lows or not bars[-1].get("close"):
        return None
    lo = min(lows)
    return None if lo <= 0 else (float(bars[-1]["close"]) - lo) / lo * 100.0


def runup_adr(bars: list[dict], n: int, adr_pct: float | None) -> float | None:
    """The same run in ADR20 units — how many typical daily ranges already travelled.

    Price- and volatility-normalised, which is the point: the whole v2 finding was that an
    un-normalised chart quantity reads liquidity class. A run measured in the name's own
    daily ranges cannot be a size proxy in the same way.
    """
    if not adr_pct or adr_pct <= 0 or not bars or not bars[-1].get("close"):
        return None
    prev_close = float(bars[-1]["close"])
    win = bars[-n:]
    lows = [float(b["low_price"]) for b in win if b.get("low_price")]
    if not lows:
        return None
    unit = prev_close * adr_pct / 100.0
    return None if unit <= 0 else (prev_close - min(lows)) / unit


def pct_of_captured_range(bars: list[dict]) -> float | None:
    """Where the prior close sits inside the whole captured high-low range. 0 = at the low,
    1 = at the high. The crudest 'where in the move' reading, kept as a floor to beat."""
    highs = [float(b["high_price"]) for b in bars if b.get("high_price")]
    lows = [float(b["low_price"]) for b in bars if b.get("low_price")]
    if not highs or not lows or not bars[-1].get("close"):
        return None
    hi, lo = max(highs), min(lows)
    return None if hi <= lo else (float(bars[-1]["close"]) - lo) / (hi - lo)


# ── the composition ───────────────────────────────────────────────────────────────────
def is_clear_air(read: dict) -> bool:
    """The v2 'nothing overhead' condition, read off the NUMBERS not off the label.

    ⚠ v2's own `label` is not usable here: IPCX 2026-07-29 carries
    `overhead_vol_frac = 0.9959` — 99.6% of its traded volume sits above the open — and is
    still labelled CLEAR_AIR, because the label consults only the zone and gap-vacuum
    fields. This function uses the same three fields the label does, so the composition is
    explicit rather than inherited from a label whose name overstates it.
    """
    return (read.get("zones_remaining") == 0
            and not read.get("inside_unfilled_gap")
            and (read.get("overhead_unfilled_gap_span_adr") or 0.0) <= 0.0)


def verdict(read: dict, metric: str, cutline: float, require_clear_air: bool = True) -> str:
    """The v3 verdict. NO DEFAULT CUTLINE — the caller must supply one, and every cutline
    used in the study is reported as a sweep.

    `EXHAUSTED_BLUE_SKY` — nothing overhead AND already run past `cutline` on `metric`.
    That is the operator's chart: empty space above only because the name ate it all.
    `require_clear_air=False` gives the control arm — extension alone, no chart read — so
    the study can say what the supply read ADDS rather than assuming it adds anything.
    """
    v = read.get(metric)
    if v is None:
        return "UNREADABLE"
    if require_clear_air and not is_clear_air(read):
        return "NOT_BLUE_SKY"
    return "EXHAUSTED_BLUE_SKY" if v >= cutline else "PASS"


def structure_read_v3(bars: list[dict], alert_date: date, open_px: float) -> dict:
    """The v2 read plus the run-up family. Pure over prior bars + the alert-day open."""
    out = V2.structure_read_v2(bars, alert_date, open_px)
    out["clear_air"] = is_clear_air(out)
    out["extension_live_pct"] = extension_live_pct(bars, alert_date)
    out["blocked_by_live_extension_rule"] = blocked_by_live_extension_rule(bars, alert_date)
    if out.get("reason"):
        return out
    adr = out.get("adr20_pct")
    for n in RUNUP_WINDOWS:
        out[f"ext_close_pct_{n}"] = ext_close_pct(bars, n)
        out[f"runup_low_pct_{n}"] = runup_low_pct(bars, n)
        out[f"runup_adr_{n}"] = runup_adr(bars, n, adr)
    out["pct_of_captured_range"] = pct_of_captured_range(bars)
    return out


RUNUP_FIELDS = ([f"{k}_{n}" for n in RUNUP_WINDOWS
                 for k in ("ext_close_pct", "runup_low_pct", "runup_adr")]
                + ["pct_of_captured_range", "extension_live_pct",
                   "blocked_by_live_extension_rule", "clear_air"])
