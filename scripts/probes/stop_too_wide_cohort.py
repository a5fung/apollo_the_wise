#!/usr/bin/env python3
"""
Probe for the data-gated review `stop_too_wide_outcome_cohort` (data_gated_reviews.yaml
~line 2371). READ-ONLY, $0 — no LLM calls, no DB writes, no live/paper trade-state touched.

Question: does MAGNA53's `setup:stop_too_wide` filter (ORB range > 1.5x ATR_14 -> reject)
shed winners? Two seed cases (STRL 5/05, AIP 5/13) raised the worry at N=2.

This script:
  1. Loads the rejected cohort (MAGNA53 ATR-based stop_too_wide skips only -- the
     9M Day-2 "stop distance > 15%" skips share the same skip_reason PREFIX but are
     a DIFFERENT setup/filter and are explicitly excluded, see NOTE below).
  2. Loads the baseline: HIGH-tier MAGNA53 alerts that PASSED the stop_too_wide gate
     and were actually taken (orb_high/orb_low/atr_14 present on mi_live_trades).
  3. For every row, reconstructs ORB geometry (rejected rows only -- orb_high/orb_low
     are never persisted on a skipped row, so they're parsed algebraically out of the
     free-text skip_reason, which is exact to the printed rounding) and runs the SAME
     daily-exit ladder used in production (agents/market_intelligence/broker/exit_logic.py
     ::apply_daily_exit_step -- hard stop / SMA10-20 trail / Day3-5 partial / breakeven)
     re-implemented here as a faithful, read-only port (no import -- avoids pulling in
     the live asyncpg/Alpaca dependency graph; verified line-by-line against the source
     2026-08-17).
  4. Applies the CURRENT (2026-08-16, operator-signed) stop rule uniformly to BOTH
     cohorts: stop = 2*orb_low - orb_high (entry - 2R, R = orb_high - orb_low). This
     is "our own bracket" as it exists today. The ATR/ORB-range gate itself did not
     move in that change, so the same 9 rows would still be rejected today.
  5. Normalizes everything by ADR20 (house formula, from sell_discipline.py:
     AVG((high-low)/NULLIF(close,0)*100) over the 30 calendar days before alert_date,
     i.e. ~20 trading sessions) -- raw percent is rigged toward the rejected cohort by
     construction (the filter selects on volatility).

NOTE on the N=13 gate count: the review's predicate_sql counts
`skip_reason LIKE 'setup:stop_too_wide%'` without distinguishing setup. Two DIFFERENT
code paths write that prefix:
  - order_manager.py prepare_orb_order (MAGNA53): "ORB range $X (Y%) > 1.5x ATR $Z"
  - order_manager.py prepare_prior_day_low_orb_order (9M Day 2): "stop distance N% > 15%"
The 9M check anchors off the PRIOR DAY LOW (not ORB range vs ATR) and caps stop
distance at 15% of price -- a different setup, different anchor, different threshold.
Of the 17 total `stop_too_wide%` rows since 2026-05-05, only 9 are MAGNA53 (the
setup this review is about); the other 8 are 9M Day 2. The gate's "N=13 settled"
read is real but conflates the two -- the true MAGNA53-only cohort is N=9, of which
only 5 are past the 25-day settle lag as of today.
"""
from __future__ import annotations

import json
import re
import statistics
from datetime import date, timedelta

SCRATCH = "/private/tmp/claude-501/-Users-alvinfung-apollo-the-wise/6bd49b80-0683-4b68-be72-adb54075b1c4/scratchpad"
TODAY = date(2026, 8, 17)  # operator_now.py PT date at time of run; bars are ET/daily anyway

# ── 1. Rejected cohort (MAGNA53 ATR-based stop_too_wide only) ──────────────────────
REJECTED_RAW = [
    # ticker, alert_date, ep_score, gap_pct, skip_reason
    ("STRL", "2026-05-05", 96.0, 29.37, "setup:stop_too_wide: ORB range $35.02 (5.0%) > 1.5x ATR $20.33"),
    ("EVER", "2026-05-05", 100.0, 19.99, "setup:stop_too_wide: ORB range $1.00 (5.5%) > 1.5x ATR $0.70"),
    ("AIP", "2026-05-13", 115.2, 20.81, "setup:stop_too_wide: ORB range $3.18 (9.8%) > 1.5x ATR $3.02"),
    ("GO", "2026-05-14", 84.0, 17.38, "setup:stop_too_wide: ORB range $0.71 (8.1%) > 1.5x ATR $0.60"),
    ("PONY", "2026-05-26", 64.8, 12.66, "setup:stop_too_wide: ORB range $0.74 (7.6%) > 1.5x ATR $0.73"),
    ("CORT", "2026-07-30", 96.0, 24.21, "setup:stop_too_wide: ORB range $7.25 (6.9%) > 1.5x ATR $6.89"),
    ("AEVA", "2026-08-06", 96.0, 22.28, "setup:stop_too_wide: ORB range $3.08 (13.4%) > 1.5x ATR $2.33"),
    ("ATRO", "2026-08-12", 72.0, 11.29, "setup:stop_too_wide: ORB range $5.75 (7.2%) > 1.5x ATR $5.29"),
    ("HTFL", "2026-08-14", 96.0, 25.12, "setup:stop_too_wide: ORB range $2.55 (7.0%) > 1.5x ATR $2.19"),
]

_SKIP_RE = re.compile(
    r"ORB range \$(?P<range>[\d.]+) \((?P<pct>[\d.]+)%\) > 1\.5x ATR \$(?P<atr15>[\d.]+)"
)


def reconstruct_orb(skip_reason: str) -> tuple[float, float, float]:
    """Algebraically invert the printed skip_reason back to (orb_high, orb_low, atr_14).
    Exact given the code's own arithmetic (order_manager.py ~L388-393):
        orb_range = orb_high - orb_low
        orb_pct   = orb_range / orb_low * 100
        printed atr15 = 1.5 * atr_14
    Small rounding error only from the printed decimal precision (range: 2dp,
    pct: 1dp, atr15: 2dp) -- immaterial at these price levels.
    """
    m = _SKIP_RE.search(skip_reason)
    if not m:
        raise ValueError(f"could not parse: {skip_reason}")
    orb_range = float(m["range"])
    orb_pct = float(m["pct"])
    atr15 = float(m["atr15"])
    orb_low = orb_range / (orb_pct / 100.0)
    orb_high = orb_low + orb_range
    atr_14 = atr15 / 1.5
    return orb_high, orb_low, atr_14


# ── 2. Load baseline (passed-the-gate, actually-taken HIGH MAGNA53 alerts) ─────────
def load_baseline() -> list[dict]:
    rows = []
    seen = set()
    with open(f"{SCRATCH}/baseline_passed.psv") as f:
        for line in f:
            parts = line.rstrip("\n").split("|")
            if len(parts) != 7:
                continue
            ticker, alert_date_s, ep_score, orb_high, orb_low, atr_14, status = parts
            key = (ticker, alert_date_s)
            if key in seen:
                continue
            seen.add(key)
            rows.append({
                "ticker": ticker,
                "alert_date": date.fromisoformat(alert_date_s),
                "ep_score": float(ep_score) if ep_score else None,
                "orb_high": float(orb_high),
                "orb_low": float(orb_low),
                "atr_14": float(atr_14) if atr_14 else None,
                "status": status,
                "actually_filled": status in ("closed", "filled"),
                "cohort": "baseline_passed",
            })
    return rows


def load_rejected() -> list[dict]:
    rows = []
    for ticker, alert_date_s, ep_score, gap_pct, skip_reason in REJECTED_RAW:
        orb_high, orb_low, atr_14 = reconstruct_orb(skip_reason)
        rows.append({
            "ticker": ticker,
            "alert_date": date.fromisoformat(alert_date_s),
            "ep_score": ep_score,
            "orb_high": orb_high,
            "orb_low": orb_low,
            "atr_14": atr_14,
            "status": "rejected",
            "actually_filled": None,  # unknown/counterfactual -- see LIMITATION in doc
            "cohort": "rejected_stop_too_wide",
        })
    return rows


# ── 3. Daily bars ───────────────────────────────────────────────────────────────────
def load_bars() -> dict[str, list[tuple[date, dict]]]:
    bars: dict[str, list[tuple[date, dict]]] = {}
    with open(f"{SCRATCH}/daily_bars.psv") as f:
        for line in f:
            parts = line.rstrip("\n").split("|")
            if len(parts) != 6:
                continue
            ticker, d, o, h, l, c = parts
            try:
                bar = {"o": float(o), "h": float(h), "l": float(l), "c": float(c)}
            except ValueError:
                continue
            bars.setdefault(ticker, []).append((date.fromisoformat(d), bar))
    for t in bars:
        bars[t].sort(key=lambda x: x[0])
    return bars


# ── 4. ADR20 (house formula, sell_discipline.py _SCAN_SQL) ─────────────────────────
def adr20_pct(ticker_bars: list[tuple[date, dict]], alert_date: date) -> float | None:
    window = [
        (b["h"] - b["l"]) / b["c"] * 100.0
        for d, b in ticker_bars
        if alert_date - timedelta(days=30) <= d < alert_date and b["c"]
    ]
    if not window:
        return None
    return statistics.mean(window)


def prior_closes(ticker_bars: list[tuple[date, dict]], alert_date: date) -> list[float]:
    return [
        b["c"] for d, b in ticker_bars
        if alert_date - timedelta(days=40) <= d <= alert_date - timedelta(days=1)
    ]


def forward_bars(ticker_bars: list[tuple[date, dict]], alert_date: date, n_sessions: int):
    fwd = [(d, b) for d, b in ticker_bars if d > alert_date]
    return fwd[:n_sessions]


def day0_bar(ticker_bars: list[tuple[date, dict]], alert_date: date):
    for d, b in ticker_bars:
        if d == alert_date:
            return b
    return None


# ── 5. Faithful port of apply_daily_exit_step (read-only reference; see module
#      docstring). Hard stop -> SMA10/20 trail (max, seeded with prior_closes) ->
#      Day3-5 partial (1/3 shares) -> breakeven-after-partial -> close-below-
#      effective-stop trail exit. No giveback/EMA/handoff opt-ins (none are live
#      defaults for MAGNA53).
PROFIT_TRIGGER_R = 2.0  # order_manager.scan_profit_triggers / constants.PROFIT_TRIGGER_R, LIVE 2026-08-01


def simulate(entry: float, hard_stop: float, orb_low: float, alert_date: date,
             fwd: list[tuple[date, dict]], prior_close_list: list[float],
             day0: dict | None, *, check_day0_stop: bool = False,
             model_profit_trigger: bool = True) -> dict:
    """Ports TWO independent production mechanisms, not one:

    (A) `exit_logic.apply_daily_exit_step` -- hard stop / SMA10-20 trail / Day3-5
        hold-based partial. Skips `today <= alert_date` (day 0) entirely; day 0's
        real intraday stop risk is a live broker order this daily-bar probe can't
        see. check_day0_stop=True is a SENSITIVITY-ONLY variant (off by default)
        that tests day0's whole-session LOW against the stop -- a biased proxy
        that can trip on a pre-fill dip before the ORB-high buy ever triggered,
        so it over-counts and is kept OFF by default. NOTE: this was NOT the
        main driver of the wrong initial verdict below (turning it off alone did
        not move the baseline median off -1.00R) -- (B) was. Left in only as a
        documented, ruled-out alternative explanation.

    (B) `order_manager.scan_profit_triggers` (`constants.PROFIT_TRIGGER_R = 2.0`,
        LIVE since 2026-08-01) -- a SEPARATE, price-triggered 1/3 partial, live
        from the moment of fill (i.e. INCLUDING day 0), independent of the daily
        ladder above. Target = entry + PROFIT_TRIGGER_R * (entry - orb_low) --
        the OLD orb-defined R, held fixed by the operator-signed 2026-08-16
        design specifically so the target does NOT drift when the stop widens
        (order_manager.py ~L5852). Algebraically this equals entry + risk_per_share
        exactly (2*(entry-orb_low) == entry-stop_current under the current 2R
        stop) -- i.e. the target sits at exactly +1R in THIS probe's stop-distance
        R-unit, symmetric with the -1R stop. Modeled here from the daily bar's
        HIGH (a safe upper-bound proxy for "did any intraday minute cross the
        target that day" -- exact for day attribution, since a day's high IS the
        max of its own minute highs); fill assumed AT the target price, matching
        the resting-GTC-limit "final design" the source describes. Missing this
        mechanism entirely was the root cause of a wrong initial verdict here
        (median realized R came out matching the OLD, pre-2026-08-16 stop rule's
        documented behavior) -- caught by advisor review, see docs/analysis note.
        model_profit_trigger=False (OFF) is a sensitivity variant for comparison.

    Whichever mechanism fires first, on a given day, wins for THAT day; a hard
    stop is terminal (ends the trade) so it is checked before the target on the
    same day. The target check runs on day 0 (mechanism B is live from fill);
    the hard-stop/trail check does not (mechanism A skips day 0, matching
    production `apply_daily_exit_step`'s own semantics -- see (A) above).
    """
    remaining = 1.0
    partial_taken = False
    breakeven_active = False
    trigger_fired = False
    running_closes: list[float] = []
    exits: list[dict] = []
    hold_days = 0
    target = entry + PROFIT_TRIGGER_R * (entry - orb_low) if (model_profit_trigger and orb_low) else None

    if check_day0_stop and day0 is not None and day0["l"] <= hard_stop:
        pnl = (hard_stop - entry) * remaining
        exits.append({"day": alert_date, "price": hard_stop, "reason": "stop_hit_day0", "pnl": pnl})
        return {
            "closed": True, "close_reason": "stop_hit_day0", "hold_days": 0,
            "total_pnl": pnl, "peak_close": entry, "running_closes": [], "trigger_fired": False,
        }

    peak_close = entry

    # Day 0: mechanism (B) only -- the price-trigger partial is live from fill,
    # mechanism (A)'s daily ladder is not evaluated yet (day 0 is its skip day).
    if day0 is not None and target is not None and day0["h"] >= target:
        partial_shares = remaining / 3.0
        partial_pnl = (target - entry) * partial_shares
        remaining -= partial_shares
        exits.append({"day": alert_date, "price": target, "reason": "profit_trigger", "pnl": partial_pnl})
        partial_taken = True
        breakeven_active = True
        trigger_fired = True
        peak_close = max(peak_close, target)

    for d, bar in fwd:
        hold_days = (d - alert_date).days
        bar_low, bar_high, bar_close = bar["l"], bar["h"], bar["c"]
        running_closes.append(bar_close)
        peak_close = max(peak_close, bar_close)

        # 1. hard stop (terminal -- checked first)
        if hard_stop and bar_low <= hard_stop:
            pnl_this = (hard_stop - entry) * remaining
            total_pnl = sum(e["pnl"] for e in exits) + pnl_this
            exits.append({"day": d, "price": hard_stop, "reason": "stop_hit", "pnl": pnl_this})
            return {
                "closed": True, "close_reason": "stop_hit", "hold_days": hold_days,
                "total_pnl": total_pnl, "peak_close": peak_close, "running_closes": running_closes,
                "trigger_fired": trigger_fired,
            }

        # 1b. price-triggered +1R partial (mechanism B, live every day incl. this one)
        if not partial_taken and target is not None and bar_high >= target:
            partial_shares = remaining / 3.0
            partial_pnl = (target - entry) * partial_shares
            remaining -= partial_shares
            exits.append({"day": d, "price": target, "reason": "profit_trigger", "pnl": partial_pnl})
            partial_taken = True
            breakeven_active = True
            trigger_fired = True
            peak_close = max(peak_close, target)

        # 2. trail = max(SMA10, SMA20) over prior_closes + running_closes (#548 stock history)
        trail_closes = prior_close_list + running_closes
        sma10 = sum(trail_closes[-10:]) / 10 if len(trail_closes) >= 10 else None
        sma20 = sum(trail_closes[-20:]) / 20 if len(trail_closes) >= 20 else None
        active_sma = None
        if sma20 is not None:
            active_sma = sma10 if (sma10 is not None and sma10 > sma20) else sma20
        elif sma10 is not None:
            active_sma = sma10

        # 3. Day 3-5 HOLD-based partial (mechanism A) -- mutually exclusive with the
        # price trigger above via the shared `partial_taken` flag, exactly like
        # production (scan_profit_triggers and exit_logic both gate on the same
        # mi_live_trades.partial_taken column).
        if hold_days >= 3 and not partial_taken:
            take_partial = (hold_days <= 4 and bar_close > entry) or hold_days >= 5
            if take_partial:
                partial_shares = remaining / 3.0
                if partial_shares > 0:
                    partial_pnl = (bar_close - entry) * partial_shares
                    remaining -= partial_shares
                    exits.append({"day": d, "price": bar_close, "reason": "partial_profit", "pnl": partial_pnl})
                    partial_taken = True
                    breakeven_active = True

        # 4. effective stop
        effective_stop = hard_stop
        if active_sma and active_sma > effective_stop:
            effective_stop = active_sma
        if breakeven_active and entry > effective_stop:
            effective_stop = entry

        # 5. close-below-trail exit
        if bar_close < effective_stop and remaining > 0:
            pnl_this = (bar_close - entry) * remaining
            total_pnl = sum(e["pnl"] for e in exits) + pnl_this
            exits.append({"day": d, "price": bar_close, "reason": "sma_trail_stop", "pnl": pnl_this})
            return {
                "closed": True, "close_reason": "sma_trail_stop", "hold_days": hold_days,
                "total_pnl": total_pnl, "peak_close": peak_close, "running_closes": running_closes,
                "trigger_fired": trigger_fired,
            }

    # window exhausted, still open -- mark-to-last-close
    total_pnl = sum(e["pnl"] for e in exits)
    if remaining > 0 and fwd:
        last_close = fwd[-1][1]["c"]
        total_pnl += (last_close - entry) * remaining
    return {
        "closed": False, "close_reason": "window_end_open", "hold_days": hold_days,
        "total_pnl": total_pnl, "peak_close": peak_close, "running_closes": running_closes,
        "trigger_fired": trigger_fired,
    }


# ── 6. Per-row feature build ────────────────────────────────────────────────────────
def build_row(row: dict, bars_by_ticker: dict) -> dict | None:
    t = row["ticker"]
    ticker_bars = bars_by_ticker.get(t, [])
    if not ticker_bars:
        return None
    orb_high, orb_low = row["orb_high"], row["orb_low"]
    alert_date = row["alert_date"]
    adr = adr20_pct(ticker_bars, alert_date)
    prior = prior_closes(ticker_bars, alert_date)
    d0 = day0_bar(ticker_bars, alert_date)

    entry = orb_high
    orb_range = orb_high - orb_low
    stop_current = 2 * orb_low - orb_high  # current (2026-08-16) 2R rule
    risk_per_share = entry - stop_current  # = 2 * orb_range, always > 0 for orb_range>0
    if risk_per_share <= 0:
        return None
    risk_pct = risk_per_share / entry * 100.0
    orb_range_pct = orb_range / orb_low * 100.0 if orb_low else None

    # raw excursion (MFE) at 5d / 20d, from bar HIGHS (best price touched, not what
    # the bracket kept) -- separate from the bracket-realized R below.
    fwd20 = forward_bars(ticker_bars, alert_date, 20)
    fwd5 = fwd20[:5]
    all_highs_incl_d0 = ([d0["h"]] if d0 else []) + [b["h"] for _, b in fwd20]
    mfe20_pct = (max(all_highs_incl_d0) / entry - 1) * 100.0 if all_highs_incl_d0 else None
    highs5 = ([d0["h"]] if d0 else []) + [b["h"] for _, b in fwd5]
    mfe5_pct = (max(highs5) / entry - 1) * 100.0 if highs5 else None

    n_settled_5d = len(fwd5) >= 5 or (alert_date + timedelta(days=8)) <= TODAY
    n_settled_20d = len(fwd20) >= 20 or (alert_date + timedelta(days=29)) <= TODAY

    # Fill plausibility: orb_high is BY DEFINITION the max of the first 5 minutes,
    # so day_high >= orb_high always holds when the reconstruction is clean; a
    # reconstructed orb_high AT OR ABOVE the day's actual high means the ORB high
    # WAS (about) the session high -- i.e. price never came back up to retest it
    # after the opening 5 minutes, so a stop-limit buy queued at that level almost
    # certainly never filled in the live 9:31-9:44 ET window (a real "cancelled:
    # ORB window unfilled", $0, not a trade). Headroom in %, floored at 0.
    d0_high = d0["h"] if d0 else None
    fill_headroom_pct = ((d0_high - entry) / entry * 100.0) if d0_high else None
    likely_unfilled = fill_headroom_pct is not None and fill_headroom_pct <= 0.1

    sim = simulate(entry, stop_current, orb_low, alert_date, fwd20, prior, d0,
                    check_day0_stop=False, model_profit_trigger=True)
    sim_no_trigger = simulate(entry, stop_current, orb_low, alert_date, fwd20, prior, d0,
                               check_day0_stop=False, model_profit_trigger=False)
    sim_sens = simulate(entry, stop_current, orb_low, alert_date, fwd20, prior, d0,
                         check_day0_stop=True, model_profit_trigger=True)
    realized_r = sim["total_pnl"] / risk_per_share
    peak_r = (sim["peak_close"] - entry) / risk_per_share
    realized_r_no_trigger = sim_no_trigger["total_pnl"] / risk_per_share
    realized_r_sens = sim_sens["total_pnl"] / risk_per_share
    # ADR-normalized realized/peak RETURN (house convention, sell_discipline.py
    # realized_adr = realized_r * stop_pct / adr_pct == (realized_$/entry*100)/adr_pct).
    # Decouples "how much did the trade actually make" from "how wide is this
    # trade's own R unit" -- R-multiples are NOT comparable across cohorts whose
    # stop distance (in ADR terms) differs ~2x, which it does here (risk_adr
    # median 2.9 rejected vs 1.2 baseline) -- a wide-stop trade can print a
    # "less negative R" purely because its R unit is inflated, not because the
    # trade did better. This field is the apples-to-apples one.
    realized_pct = sim["total_pnl"] / entry * 100.0
    peak_pct = (sim["peak_close"] - entry) / entry * 100.0
    realized_adr_norm = (realized_pct / adr) if adr else None
    peak_adr_norm = (peak_pct / adr) if adr else None
    # How far (in the stock's own ADR20s) does price need to run for the
    # scan_profit_triggers partial to fire at all? target - entry = 2*orb_range.
    target_price = entry + PROFIT_TRIGGER_R * (entry - orb_low) if orb_low else None
    target_distance_adr = (((target_price - entry) / entry * 100.0) / adr) if (target_price and adr) else None

    return {
        "ticker": t, "alert_date": alert_date.isoformat(), "cohort": row["cohort"],
        "ep_score": row.get("ep_score"),
        "status": row.get("status"), "actually_filled": row.get("actually_filled"),
        "orb_range_pct": orb_range_pct, "adr20_pct": adr,
        "orb_range_adr": (orb_range_pct / adr) if (orb_range_pct and adr) else None,
        "risk_pct": risk_pct, "risk_adr": (risk_pct / adr) if adr else None,
        "mfe5_pct": mfe5_pct, "mfe5_adr": (mfe5_pct / adr) if (mfe5_pct is not None and adr) else None,
        "mfe20_pct": mfe20_pct, "mfe20_adr": (mfe20_pct / adr) if (mfe20_pct is not None and adr) else None,
        "realized_r": realized_r, "peak_r": peak_r,
        "realized_pct": realized_pct, "realized_adr_norm": realized_adr_norm,
        "peak_pct": peak_pct, "peak_adr_norm": peak_adr_norm,
        "close_reason": sim["close_reason"], "hold_days": sim["hold_days"],
        "n_fwd_bars": len(fwd20), "settled_5d": n_settled_5d, "settled_20d": n_settled_20d,
        "fill_headroom_pct": fill_headroom_pct, "likely_unfilled": likely_unfilled,
        "realized_r_sens_day0check": realized_r_sens,
        "close_reason_sens": sim_sens["close_reason"],
        "realized_r_no_profit_trigger": realized_r_no_trigger,
        "profit_trigger_fired": sim.get("trigger_fired", False),
        "target_distance_adr": target_distance_adr,
    }


def pctl(vals: list[float], p: float) -> float | None:
    if not vals:
        return None
    s = sorted(vals)
    k = (len(s) - 1) * p
    f, c = int(k), min(int(k) + 1, len(s) - 1)
    if f == c:
        return s[f]
    return s[f] + (s[c] - s[f]) * (k - f)


def summarize(rows: list[dict], label: str):
    print(f"\n=== {label} (N={len(rows)}) ===")
    for field, unit in [
        ("orb_range_adr", "ORB range, in ADR20s"),
        ("risk_adr", "stop distance (current 2R rule), in ADR20s"),
        ("mfe5_pct", "raw 5d MFE %"), ("mfe5_adr", "5d MFE, in ADR20s"),
        ("mfe20_pct", "raw 20d MFE %"), ("mfe20_adr", "20d MFE, in ADR20s"),
        ("realized_r", "realized R under current bracket"),
        ("peak_r", "peak R touched (close-based) under current bracket"),
        ("realized_adr_norm", "ADR-NORMALIZED realized return (apples-to-apples, R-unit-independent)"),
        ("peak_adr_norm", "ADR-NORMALIZED peak return touched (close-based)"),
    ]:
        vals = [r[field] for r in rows if r.get(field) is not None]
        if not vals:
            print(f"  {field:16s} ({unit}): no data")
            continue
        med = statistics.median(vals)
        p90 = pctl(vals, 0.90)
        mean = statistics.mean(vals)
        print(f"  {field:16s} ({unit}): n={len(vals):3d}  median={med:+.3f}  mean={mean:+.3f}  p90={p90:+.3f}")
    r_vals = [r["realized_r"] for r in rows if r.get("realized_r") is not None]
    if r_vals:
        for thr in (0, 1, 2, 5):
            share = sum(1 for v in r_vals if v >= thr) / len(r_vals) * 100
            print(f"    share reaching >= {thr:+d}R realized: {share:.0f}%")
    adr_vals = [r["realized_adr_norm"] for r in rows if r.get("realized_adr_norm") is not None]
    if adr_vals:
        for thr in (0, 1, 2, 5):
            share = sum(1 for v in adr_vals if v >= thr) / len(adr_vals) * 100
            print(f"    share reaching >= {thr:+d} ADR realized (normalized): {share:.0f}%")
    close_reasons = {}
    for r in rows:
        close_reasons[r["close_reason"]] = close_reasons.get(r["close_reason"], 0) + 1
    print(f"  close reasons: {close_reasons}")


def main():
    bars_by_ticker = load_bars()
    rejected = load_rejected()
    baseline = load_baseline()

    rejected_built = [b for r in rejected if (b := build_row(r, bars_by_ticker))]
    baseline_built = [b for r in baseline if (b := build_row(r, bars_by_ticker))]

    print(f"rejected: {len(rejected)} raw -> {len(rejected_built)} built")
    print(f"baseline: {len(baseline)} raw -> {len(baseline_built)} built")

    print("\n--- REJECTED COHORT (MAGNA53 stop_too_wide only) — per-row ---")
    for r in sorted(rejected_built, key=lambda x: x["alert_date"]):
        print(json.dumps(r, default=str))

    summarize(rejected_built, "REJECTED (MAGNA53 stop_too_wide) -- assumes fill at ORB high")
    summarize(baseline_built, "BASELINE, ALL gate-passers (incl. never-filled 'ORB window unfilled')")
    baseline_filled = [r for r in baseline_built if r["actually_filled"]]
    summarize(baseline_filled, "BASELINE, ACTUALLY-FILLED ONLY (ground truth from mi_live_trades.status)")

    # settled-only cuts
    rej_5d = [r for r in rejected_built if r["settled_5d"]]
    rej_20d = [r for r in rejected_built if r["settled_20d"]]
    summarize(rej_5d, "REJECTED, 5d-settled only")
    summarize(rej_20d, "REJECTED, 20d-settled only")
    base_20d = [r for r in baseline_filled if r["settled_20d"]]
    summarize(base_20d, "BASELINE, ACTUALLY-FILLED + 20d-settled only")

    rej_plausible = [r for r in rejected_built if not r["likely_unfilled"]]
    rej_plausible_5d = [r for r in rej_plausible if r["settled_5d"]]
    summarize(rej_plausible, "REJECTED, excluding likely-never-filled (GO/PONY headroom<=0.1%)")
    summarize(rej_plausible_5d, "REJECTED, excl. likely-unfilled + 5d-settled")
    print("\n--- fill headroom (day0 high vs entry), all 9 rejected ---")
    for r in sorted(rejected_built, key=lambda x: x["alert_date"]):
        print(f"  {r['ticker']:6s} headroom={r['fill_headroom_pct']:+.2f}%  likely_unfilled={r['likely_unfilled']}")

    # ── Advisor follow-up 1: does headroom actually predict non-fill? ──
    # Baseline has REAL status (37 cancelled / 40 filled) to validate the
    # heuristic used to exclude GO/PONY from the rejected cohort.
    print("\n--- headroom-vs-actually_filled validation (all 77 baseline gate-passers) ---")
    thresholds = [(-100, 0.1, "<=0.1% (near-zero/negative)"), (0.1, 2, "0.1-2%"),
                  (2, 5, "2-5%"), (5, 100, ">5%")]
    for lo, hi, label in thresholds:
        bucket = [r for r in baseline_built
                  if r["fill_headroom_pct"] is not None and lo < r["fill_headroom_pct"] <= hi]
        if not bucket:
            continue
        filled = sum(1 for r in bucket if r["actually_filled"])
        print(f"  headroom {label:28s}: n={len(bucket):3d}  actually filled={filled}/{len(bucket)} "
              f"({filled/len(bucket)*100:.0f}%)")

    # ── Advisor follow-up 2: target reachability (in ADR20s) by cohort ──
    print("\n--- profit-trigger target distance, in ADR20s (2x the ORB range, normalized) ---")
    for label, rows in [
        ("Rejected (all 9)", rejected_built),
        ("Baseline (filled)", baseline_filled),
    ]:
        vals = [r["target_distance_adr"] for r in rows if r.get("target_distance_adr") is not None]
        if vals:
            print(f"  {label:20s}: n={len(vals):3d}  median={statistics.median(vals):.2f} ADR  "
                  f"mean={statistics.mean(vals):.2f} ADR")
    print("  per-row (rejected): ticker, target_distance_adr, mfe20_adr, trigger_fired")
    for r in sorted(rejected_built, key=lambda x: x["alert_date"]):
        print(f"    {r['ticker']:6s} target={r['target_distance_adr']:.2f} ADR  "
              f"mfe20={r['mfe20_adr']:.2f} ADR  fired={r['profit_trigger_fired']}")

    with open(f"{SCRATCH}/stop_too_wide_results.json", "w") as f:
        json.dump({"rejected": rejected_built, "baseline": baseline_built}, f, indent=2, default=str)
    print(f"\nWrote {SCRATCH}/stop_too_wide_results.json")


if __name__ == "__main__":
    main()
