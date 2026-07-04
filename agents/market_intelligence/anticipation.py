"""#270 anticipation re-entry — SHADOW lifecycle composition (Step 3).

Ports the gate-free replay/coil logic (validated in `scripts/_270_*.py`) into the
production package so the readiness job (`scheduler._anticipation_readiness_job`) and
the `/sip` board can compose the lifecycle — EP gap → gap-low UNDERCUT → RECLAIM →
COIL → entry → harvest — from daily bars (the MNTS template). The offline scripts
stay the frozen analysis artifacts; `tests/test_anticipation_golden.py` pins this port
byte-identical to their funnel (cohort 62→30→16 + MNTS dates) so the two can't
silently diverge — the same golden-test discipline as the `_270_harvest` extraction.

LABEL → STATE (load-bearing — see the table header in db.py): `replay()` emits the
script's terminal label **TRIGGERED** = the daily volume-RECLAIM. The JOB layer maps
that to lifecycle state **`ready`** (a SET-UP); it writes lifecycle state `triggered`
ONLY when an ENTRY fires (anticipation coil-close or the 3b first5/gdl break). Keep
that mapping OUT of `replay()` so the golden test pins the funnel, not the renaming.

PURE + import-safe: no I/O, no submit, no module-level side effects. RMV is REUSED
from `flag_detector._compute_rmv` (telemetry only — #54 verdict + STEP 0: NOT a gate;
the COILED gate stays range + base_run). Reuse, not a 4th copy (search-before-build).
"""
from datetime import datetime, timedelta, timezone
from typing import Optional

from agents.market_intelligence.flag_detector import (
    _compute_rmv, _compute_fresh_tightening, _evaluate_deal_pin,
)

# ── lifecycle thresholds — template-grounded (NOT self-certified). Calibration knobs
#    #1 (EXPANSION floor) / #2 (trigger-volume floor) are probed (N=17 illustrative) and
#    pending operator sign-off; shadow defaults = the probe recommendation. ──────────────
GAP = 0.40            # gap-day close ≥ +40% vs prior close
VOLX = 3.0            # gap-day volume ≥ 3× ADV20 (mirrors the 9M 3×-ADV gate)
ARM_WINDOW = 15       # undercut must land within 15 trading days of the gap
EXPANSION = 1.5       # trigger volume > 1.5× the pullback's average volume

# coil / anticipation (step 2c)
TIGHT_RANGE = 0.07    # daily (high-low)/close ≤ 7% = a contraction bar
VOL_CONTRACT = 1.0    # vol ≤ 1.0× ADV20 = the quiet "rest" before expansion
BASE_RANGE = 0.12     # contained base day = range ≤ 12% AND close > gap_day_low
MATURE_DAYS = 3       # require a ≥3-day developed base before a coiled entry qualifies
FWD_N = 10            # forward endpoint = trigger day + 10 trading days

# ── Generalized TIGHTENING recorder (operator 2026-06-16): the core signal is a
#    constructive tightening PULLBACK, of which the gap-low undercut is ONE shape, not a
#    requirement. We RECORD the tightening telemetry + the pullback SHAPE broadly (every
#    post-thrust name in the arm window) — that recorded set is the calibration dataset; the
#    ARMED *alert* stays narrow (gap-low undercut) until evidence + sign-off broaden the gate
#    (advisor 6/16: don't swap one un-calibrated hard gate for another). Thresholds below
#    mirror flag_detector's shape constants (search-before-build — its annotator is
#    snapshot/flag-candidate-bound, so this is the daily-bar EOD analog), NOT new gates. ──
_MA_NEAR_PCT = 2.0            # close within 2% of a moving average = "pulled into the MA" (flag_detector._MA_PULLBACK_NEAR_PCT)
_FRESH_TIGHT_BASE_AGE_MIN = 4  # _compute_fresh_tightening's own floor (mirror; <4 returns no-fire)
# Pradeep's qualifying tightness (tweet 2026-06-15, docs/methodology/operator_shared_notes.md):
# "price percent change today between -.4 and .4" = |close % change| ≤ 0.4%, then "a series of
# tight days in the previous two bars". TIGHT_CLOSE_PCT is the per-bar gate; the STREAK is the
# series. 0.4% is Pradeep-canonical; tiny-caps calibrate ~1.4% (#270 STEP 0) — telemetry, recal-able.
TIGHT_CLOSE_PCT = 0.004


# ─────────────────────────────────────────────────────────────────────────────
# Ported lifecycle (byte-identical to scripts/_270_anticipation_replay.py::replay —
# the golden test pins this). Bars are ascending dicts {date,o,h,l,c,v}.
# ─────────────────────────────────────────────────────────────────────────────
def _sma(vals, i, n):
    if i + 1 < n:
        return None
    return sum(vals[i - n + 1:i + 1]) / n


def _ema_series(vals, n):
    k = 2 / (n + 1)
    out = [None] * len(vals)
    if len(vals) < n:
        return out
    seed = sum(vals[:n]) / n
    out[n - 1] = seed
    for i in range(n, len(vals)):
        out[i] = vals[i] * k + out[i - 1] * (1 - k)
    return out


def replay(bars):
    """WATCHED → ARMED → TRIGGERED lifecycle from daily OHLCV. Returns a list of
    (date, state, detail). The terminal TRIGGERED label = the daily volume-RECLAIM
    (the JOB layer maps it to lifecycle state 'ready' — NOT 'triggered'/entry)."""
    closes = [b["c"] for b in bars]
    vols = [b["v"] for b in bars]
    ema21 = _ema_series(closes, 21)
    events = []
    state = "NONE"
    g = {}          # active WATCHED context
    pull_vols = []  # volumes observed during the pullback (expansion baseline)

    for i, b in enumerate(bars):
        sma200 = _sma(closes, i, 200)
        sma20 = _sma(closes, i, 20)
        adv20 = _sma(vols, i, 20)
        prev_c = closes[i - 1] if i > 0 else None

        if state in ("NONE", "TRIGGERED"):
            if prev_c and adv20 and sma200:
                gap = b["c"] / prev_c - 1
                if gap >= GAP and b["c"] > sma200 and b["v"] >= VOLX * adv20:
                    state = "WATCHED"
                    g = {"date": b["date"], "low": b["l"], "vol": b["v"],
                         "gap": gap, "i": i}
                    pull_vols = []
                    events.append((b["date"], "WATCHED",
                                   f"gap +{gap*100:.0f}% close {b['c']:.2f} > SMA200 "
                                   f"{sma200:.2f}; vol {b['v']/1e6:.1f}M = {b['v']/adv20:.1f}x ADV20; "
                                   f"gap_day_low={b['l']:.2f}"))
            continue

        # in WATCHED or ARMED: accumulate pullback volume (days after the gap)
        if i > g["i"]:
            pull_vols.append(b["v"])

        if state == "WATCHED":
            if i - g["i"] > ARM_WINDOW:
                events.append((b["date"], "EXPIRED",
                               f"no undercut within {ARM_WINDOW}d of gap"))
                state, g = "NONE", {}
                continue
            if b["l"] < g["low"] and b["v"] < g["vol"]:
                state = "ARMED"
                events.append((b["date"], "ARMED",
                               f"UNDERCUT gap_day_low {g['low']:.2f}: low {b['l']:.2f}; "
                               f"vol {b['v']/1e6:.1f}M < burst {g['vol']/1e6:.0f}M (contraction)"))
            continue

        if state == "ARMED":
            base = sum(pull_vols[:-1]) / max(len(pull_vols) - 1, 1) if len(pull_vols) > 1 else g["vol"]
            reclaim = b["c"] > g["low"] and (sma20 is None or b["c"] > sma20)
            expand = b["v"] > EXPANSION * base
            ema_ok = ema21[i] is None or b["c"] > ema21[i]
            if reclaim and expand:
                events.append((b["date"], "TRIGGERED",
                               f"RECLAIM close {b['c']:.2f} > gap_day_low {g['low']:.2f}"
                               f"{' & > SMA20 '+format(sma20,'.2f') if sma20 else ''}"
                               f"{' & > EMA21' if ema_ok else ' (BELOW EMA21!)'}; "
                               f"vol {b['v']/1e6:.1f}M = {b['v']/base:.1f}x pullback-avg (expansion)"))
                state = "TRIGGERED"
            continue
    return events


# ─────────────────────────────────────────────────────────────────────────────
# Coil / anticipation (ported from scripts/_270_anticipation_replay.py). `ctx` is
# the structured lifecycle context that the readiness job carries per (ticker,gap_day).
# ─────────────────────────────────────────────────────────────────────────────
def _adv(vols, i, n=20):
    return sum(vols[max(0, i - n + 1):i + 1]) / min(i + 1, n)


def _sma20(closes, i):
    return sum(closes[i - 19:i + 1]) / 20 if i >= 19 else None


def base_run(bars, ctx, i):
    """Consecutive 'base days' ending at i: close > gap_day_low AND range ≤ BASE_RANGE.
    The developed-contraction maturity proxy (the cheap pre-filter for the chart-read)."""
    n, j = 0, i
    while j > ctx["armed_idx"]:
        b = bars[j]
        rng = (b["h"] - b["l"]) / b["c"] if b["c"] else 1
        if b["c"] > ctx["gap_day_low"] and rng <= BASE_RANGE:
            n, j = n + 1, j - 1
        else:
            break
    return n


def find_coiled_days(bars, ctx, min_base=1):
    """Forward-computable COILED days in the armed window: reclaimed pivot (close >
    gap_day_low AND > SMA20) + tight range + quiet volume, no expansion yet. min_base>1
    adds the MATURITY gate. [] if a fast undercut→trigger left no qualifying coiled day."""
    a0 = ctx["armed_idx"] + 1
    a1 = ctx["trig_idx"] if ctx["trig_idx"] is not None else min(ctx["armed_idx"] + ARM_WINDOW, len(bars))
    vols = [b["v"] for b in bars]
    closes = [b["c"] for b in bars]
    out = []
    for i in range(a0, a1):
        b = bars[i]
        s20 = _sma20(closes, i)
        rng = (b["h"] - b["l"]) / b["c"] if b["c"] else 1
        reclaimed = b["c"] > ctx["gap_day_low"] and (s20 is None or b["c"] > s20)
        if reclaimed and rng <= TIGHT_RANGE and b["v"] <= VOL_CONTRACT * _adv(vols, i):
            if base_run(bars, ctx, i) >= min_base:
                out.append(i)
    return out


# ─────────────────────────────────────────────────────────────────────────────
# Key-adapters — kept SEPARATE and explicit. RMV is non-gating telemetry, so a
# mis-mapped key (high/low swap, wrong close) yields garbage RMV with NO error and
# silently corrupts the calibration dataset. `tests/test_anticipation_golden.py`
# asserts `compute_rmv` == flag_detector._compute_rmv on the same series (the
# uncovered silent-corruption surface the golden funnel test does NOT cover).
# ─────────────────────────────────────────────────────────────────────────────
def db_rows_to_bars(rows: list[dict]) -> list[dict]:
    """mi_daily_closes rows → the replay/coil bar shape {date,o,h,l,c,v}. Accepts the
    DB column names (trade_date, open_price, high_price, low_price, close, volume)."""
    out = []
    for r in rows:
        out.append({
            "date": str(r["trade_date"]),
            "o": float(r["open_price"]) if r.get("open_price") is not None else float(r["close"]),
            "h": float(r["high_price"]),
            "l": float(r["low_price"]),
            "c": float(r["close"]),
            "v": float(r["volume"]) if r.get("volume") is not None else 0.0,
        })
    return out


def bars_to_rmv_rows(bars: list[dict]) -> list[dict]:
    """Replay-shaped bars {h,l,c} → the rows `_compute_rmv`/`_wilder_tr` read
    (high_price, low_price, close). The ONLY mapping point — keep it 1:1 and tested."""
    return [{"high_price": b["h"], "low_price": b["l"], "close": b["c"]} for b in bars]


def compute_rmv(bars: list[dict], today_idx: int,
                lookback: int = 15, current_window: int = 3) -> Optional[float]:
    """RMV (0-100 contraction index) on replay-shaped bars via the canonical
    flag_detector._compute_rmv — recorded telemetry on the lifecycle row, NOT a gate."""
    return _compute_rmv(bars_to_rmv_rows(bars), today_idx,
                        lookback=lookback, current_window=current_window)


def bars_to_ft_rows(bars: list[dict]) -> list[dict]:
    """Replay bars → the rows `_compute_fresh_tightening` reads — a SUPERSET of bars_to_rmv_rows
    (adds `volume`). The ONLY mapping point for the tightening primitive; equality-tested against
    flag_detector in tests/test_anticipation_tightening.py (same silent-corruption guard as RMV)."""
    return [{"high_price": b["h"], "low_price": b["l"], "close": b["c"], "volume": b["v"]}
            for b in bars]


def compute_fresh_tightening(bars: list[dict], idx: int, base_age: int,
                             recent_avg_vol: Optional[float] = None):
    """(fires, fresh_2bar_tr_pct, atr14_pct) at `idx` via the canonical
    flag_detector._compute_fresh_tightening — the 2-bar range/vol contraction primitive (reused,
    not reinvented). RECORDED telemetry on the lifecycle row, NOT a gate (advisor 6/16)."""
    return _compute_fresh_tightening(bars_to_ft_rows(bars), idx, base_age,
                                     recent_avg_vol=recent_avg_vol)


# Pullback SHAPE priority — gap-low undercut is ONE shape, not THE requirement (operator 6/16).
# More-specific structural pivots first; low_vol_rest (no pivot, pure contraction) last.
_SHAPE_PRIORITY = ("gap_low_undercut", "ma10_pullback", "ma20_pullback", "low_vol_rest")


def detect_pullback_shape(bars: list[dict], gap_idx: int, i: int):
    """Which constructive-tightening SHAPE bar `i` exhibits — the pivot price has pulled into.
    Daily-bar EOD analog of flag_detector.compute_entry_technique_annotations (that one is
    snapshot + flag-candidate bound, so NOT reusable here — verified 6/16). Returns
    (primary_shape | None, [all_shapes]). Recorded telemetry: the broad set is the calibration
    dataset for a future generalized ARMED gate; today only gap_low_undercut arms (the alert).
    Thresholds reuse the coil/flag constants — no new gate numbers invented."""
    b = bars[i]
    closes = [x["c"] for x in bars]
    vols = [x["v"] for x in bars]
    shapes = []

    if b["l"] < bars[gap_idx]["l"]:                       # 1. gap-low undercut (U&R / MNTS shape)
        shapes.append("gap_low_undercut")

    for lbl, n in (("ma10", 10), ("ma20", 20)):           # 2. MA pullback (close pulled into an MA)
        ma = _sma(closes, i, n)
        if ma and abs(b["c"] - ma) / b["c"] * 100.0 <= _MA_NEAR_PCT:
            shapes.append(f"{lbl}_pullback")

    rng = (b["h"] - b["l"]) / b["c"] if b["c"] else 1.0   # 3. low-vol rest (tight + quiet, no pivot)
    adv = _adv(vols, i)
    if rng <= TIGHT_RANGE and adv and b["v"] <= VOL_CONTRACT * adv:
        shapes.append("low_vol_rest")

    primary = next((s for s in _SHAPE_PRIORITY if s in shapes), None)
    return primary, shapes


def tight_close_streak(bars: list[dict], i: int, thresh: float = TIGHT_CLOSE_PCT) -> int:
    """Consecutive bars ending at `i` with |close % change| ≤ thresh — Pradeep's "a series of tight
    days" (tweet 6/15, docs/methodology/operator_shared_notes.md). The per-bar gate is his
    "price percent change today between -.4 and .4" (= 0.4% close-to-close, NOT the intrabar range —
    the reply clarified this). Recorded telemetry, not a gate."""
    n, j = 0, i
    while j > 0:
        prev = bars[j - 1]["c"]
        if prev and abs(bars[j]["c"] / prev - 1) <= thresh:
            n, j = n + 1, j - 1
        else:
            break
    return n


def tightening_telemetry(bars: list[dict], i: int, gap_idx: int, armed_idx: Optional[int] = None):
    """The generalized tightening RECORD at bar `i` (recorded broadly, gates nothing yet).
    base_age = bars since the pullback began (armed bar if armed, else the gap) so the
    fresh-tightening primitive has a base to measure against. Returns a flat dict of telemetry
    columns. ALL values JSON/SQL-native (float/bool/str/None)."""
    base_anchor = armed_idx if armed_idx is not None else gap_idx
    base_age = max(i - base_anchor, 0)
    recent = [b["v"] for b in bars[max(base_anchor, i - 5):i]] if i > base_anchor else []
    recent_avg_vol = (sum(recent) / len(recent)) if recent else None
    fires, fresh_tr_pct, atr14_pct = compute_fresh_tightening(
        bars, i, base_age, recent_avg_vol=recent_avg_vol)
    primary, shapes = detect_pullback_shape(bars, gap_idx, i)
    return {
        "pullback_shape": primary,
        "pullback_shapes": ",".join(shapes) if shapes else None,
        "fresh_tightening": bool(fires),
        "fresh_2bar_tr_pct": round(fresh_tr_pct, 3) if fresh_tr_pct is not None else None,
        "atr14_pct": round(atr14_pct, 3) if atr14_pct is not None else None,
        "tight_close_streak": tight_close_streak(bars, i),   # Pradeep's "series of tight days"
    }


# ─────────────────────────────────────────────────────────────────────────────
# Harvest evaluator (ported from scripts/_270_harvest.py — the realized-exit simulator
# behind realized_r). tests/test_anticipation_settlement.py pins this port equal to the
# script on a known path, same anti-drift discipline as the funnel golden test.
# A `path` bar = {o,h,l,c, kind:'min'|'day', prior_low, day_idx}; caller owns construction.
# ─────────────────────────────────────────────────────────────────────────────
def simulate(entry, init_stop, path, rule, bound):
    """Realized R under one intrabar `bound` ('opt' target-first / 'pess' stop-first).
    Returns (realized_R, captured_pct_of_mfe, fills) or None if risk <= 0."""
    risk = entry - init_stop
    if risk <= 0:
        return None
    if rule.get("perfect_mfe"):
        mfe_px = max(b["h"] for b in path)
        return (mfe_px - entry) / risk, 1.0, []

    partials = list(rule.get("partials", []))
    stop = init_stop
    pos = 1.0
    realized = 0.0
    day_count = 0
    mfe_px = entry
    fills = []

    for b in path:
        mfe_px = max(mfe_px, b["h"])
        gb = rule.get("day0_giveback")
        if (gb is not None and b["kind"] == "min" and b["day_idx"] == 0
                and (mfe_px - entry) >= risk):
            stop = max(stop, mfe_px - gb * (mfe_px - entry))
        if b["kind"] == "day":
            day_count += 1
            if rule.get("trail_prior_low") and b["prior_low"] is not None:
                stop = max(stop, b["prior_low"])
        tgt_px = entry + partials[0][0] * risk if partials else None
        hit_tgt = tgt_px is not None and b["h"] >= tgt_px
        hit_stop = b["l"] <= stop

        def take_partial():
            nonlocal pos, realized, partials, stop
            r_mult, frac = partials.pop(0)
            f = min(frac, pos)
            realized += f * r_mult
            pos -= f
            fills.append((b["day_idx"], f))
            if rule.get("breakeven_after_first"):
                stop = max(stop, entry)

        def take_stop():
            nonlocal pos, realized
            fill = min(stop, b["o"])
            realized += pos * (fill - entry) / risk
            fills.append((b["day_idx"], pos))
            pos = 0.0

        if hit_tgt and hit_stop:
            if bound == "opt":
                take_partial()
                if pos > 0 and b["l"] <= stop:
                    take_stop()
            else:
                take_stop()
        elif hit_tgt:
            take_partial()
        elif hit_stop:
            take_stop()

        if pos <= 0:
            break
        if rule.get("time_stop_days") and b["kind"] == "day" and day_count >= rule["time_stop_days"]:
            realized += pos * (b["c"] - entry) / risk
            fills.append((b["day_idx"], pos))
            pos = 0.0
            break

    if pos > 0:
        realized += pos * (path[-1]["c"] - entry) / risk
        fills.append((path[-1]["day_idx"], pos))
    captured = realized / ((mfe_px - entry) / risk) if mfe_px > entry else float("nan")
    return realized, captured, fills


def daily_path(bars, entry_idx, end_idx):
    """Daily-only `path` over (entry_idx, end_idx] for a close-entry harvest. `prior_low`
    seeds from the entry day's low and trails the previous completed daily bar; day_idx ≥ 1."""
    path, prior_low = [], bars[entry_idx]["l"]
    for di, b in enumerate(bars[entry_idx + 1: end_idx + 1], start=1):
        path.append({"o": b["o"], "h": b["h"], "l": b["l"], "c": b["c"],
                     "kind": "day", "prior_low": prior_low, "day_idx": di})
        prior_low = b["l"]
    return path


# ─────────────────────────────────────────────────────────────────────────────
# Settlement (Phase 3) — realized_r for a 'triggered' lifecycle row, or ABSTAIN.
#
# triggered is NOT terminal: the readiness job keeps triggered+settled=FALSE rows in the
# re-eval set until their forward window completes (count TRADING bars, not calendar days),
# then settles realized_r + fwd_mfe_pct and flips settled=TRUE. realized_r is TAGGED by
# entry_tactic upstream (the row's column) so the N≥5 graduation peek never blends
# anticipation (≈0R realized) with FIRST5 (+1–2R).
# ─────────────────────────────────────────────────────────────────────────────
# W3 PRIMARY shadow exit: +1R/+3R ½/½ scale-out with a day-5 time-stop on the unbanked
# remainder (Phase 7 records the full ladder spectrum for comparison).
SETTLE_RULE = dict(partials=[(1.0, 0.5), (3.0, 0.5)], time_stop_days=5)
SETTLE_FORWARD_BARS = 5      # forward TRADING bars needed before an anticipation row settles
SETTLE_DEGRADE_DAYS = 21     # calendar days w/o enough bars (halt/delist) → settle DEGRADED on what's there


def realized_r_from_fills(entry, stop, fills) -> Optional[float]:
    """FIRST5/gdl realized R from the execution-persisted day-0 MINUTE fills. Each fill =
    {'price','fraction',...}; fractions sum to ~1.0 (whole position exits). This is the ONLY
    faithful FIRST5 realized_r — the day-0 minute scale-out (banks ~93% on day 0) cannot be
    reconstructed from daily bars, so we NEVER approximate it from them (advisor 6/16)."""
    risk = entry - stop
    if not fills or risk <= 0:
        return None
    return sum(f["fraction"] * (f["price"] - entry) / risk for f in fills)


def settle_row(*, entry_tactic, entry_price, stop_price, bars, entry_idx,
               day0_fills=None, rule=None, min_forward_bars=SETTLE_FORWARD_BARS,
               days_since_trigger=None) -> Optional[dict]:
    """Settle one 'triggered' row, or return None to ABSTAIN (leave it for a later run).

    `bars` = the ascending daily series; `entry_idx` = the index of the ENTRY day in it
    (the coiled day for anticipation; the reclaim/3b day for first5/gdl). Returns
    {realized_r, fwd_mfe_pct, settled, degraded} on settlement.

    STRUCTURAL ABSTAIN (advisor 6/16): a minute-scale tactic (first5_break / gdl_reclaim)
    with NO persisted day-0 fills ABSTAINS — it never falls back to a daily-bar approximation
    (that fallback is exactly what would re-inject the MFE-shaped error into the deployable
    for the +1–2R tactic the edge lives in). Anticipation settles on the daily path faithfully
    (it's a close entry — no day-0 minute geometry to miss)."""
    risk = (entry_price - stop_price) if (entry_price and stop_price) else None
    if not risk or risk <= 0:
        return None

    n_forward = len(bars) - 1 - entry_idx
    if entry_tactic in ("first5_break", "gdl_reclaim"):
        if not day0_fills:
            return None  # ── STRUCTURAL ABSTAIN — wait for execution to persist the fills ──
        rr = realized_r_from_fills(entry_price, stop_price, day0_fills)
        end = min(entry_idx + min_forward_bars, len(bars) - 1)
        mfe = ((max(b["h"] for b in bars[entry_idx + 1:end + 1]) - entry_price) / risk
               if end > entry_idx else 0.0)
        return {"realized_r": rr, "fwd_mfe_pct": mfe, "settled": rr is not None, "degraded": False}

    if entry_tactic != "anticipation":
        return None  # unknown tactic → abstain rather than guess

    degraded = False
    if n_forward < min_forward_bars:
        # terminal fallback: a tiny-cap that stops printing (halt/delist) would leave realized_r
        # NULL forever → after a bounded window settle DEGRADED on the bars we have; else abstain.
        if days_since_trigger is not None and days_since_trigger >= SETTLE_DEGRADE_DAYS and n_forward >= 1:
            degraded = True
        else:
            return None
    end = min(entry_idx + min_forward_bars, len(bars) - 1)
    out = simulate(entry_price, stop_price, daily_path(bars, entry_idx, end),
                   rule or SETTLE_RULE, "pess")
    if out is None:
        return None
    realized_r, _captured, _fills = out
    mfe = (max(b["h"] for b in bars[entry_idx + 1:end + 1]) - entry_price) / risk
    return {"realized_r": realized_r, "fwd_mfe_pct": mfe, "settled": True, "degraded": degraded}


# ─────────────────────────────────────────────────────────────────────────────
# Lifecycle-from-bars evaluation (Phase 4a) — derive the CURRENT lifecycle row for one
# (ticker, gap_day) from its daily bars. PURE: the readiness job (scheduler) supplies the
# ticker + bars and owns persistence. The replay-label → lifecycle-state mapping is applied
# HERE (the JOB layer), never inside replay() — so the golden test still pins the funnel.
# ─────────────────────────────────────────────────────────────────────────────
def cycle_for_gap(bars, gap_day):
    """The lifecycle cycle SEEDED at `gap_day` (a date str). Parses replay()'s event stream
    for the WATCHED at gap_day and this cycle's events up to the next WATCHED. Returns the
    cycle's dates/indices, or None if gap_day isn't a WATCHED seed in these bars."""
    idx_of = {b["date"]: i for i, b in enumerate(bars)}
    if gap_day not in idx_of:
        return None
    events = replay(bars)
    seq = next((k for k, (d, s, _) in enumerate(events) if s == "WATCHED" and d == gap_day), None)
    if seq is None:
        return None
    armed_date = ready_date = None
    expired = False
    for d, s, _ in events[seq + 1:]:
        if s == "WATCHED":
            break                               # next cycle started
        if s == "ARMED" and armed_date is None:
            armed_date = d
        elif s == "TRIGGERED" and ready_date is None:
            ready_date = d                       # replay TRIGGERED = the daily RECLAIM = 'ready'
            break
        elif s == "EXPIRED":
            expired = True
            break
    gi = idx_of[gap_day]
    return {"gap_day": gap_day, "gap_idx": gi,
            "gap_day_low": bars[gi]["l"], "gap_day_vol": bars[gi]["v"],
            "armed_date": armed_date, "armed_idx": idx_of.get(armed_date) if armed_date else None,
            "ready_date": ready_date, "ready_idx": idx_of.get(ready_date) if ready_date else None,
            "expired": expired}


def evaluate_candidate(bars, gap_day, min_base=MATURE_DAYS):
    """Derive the current lifecycle row dict for (gap_day) from its daily bars, or None if
    gap_day isn't a valid WATCHED seed. State precedence (the JOB-layer label→state mapping):
      triggered  a MATURE coil fired the (shadow) anticipation entry — the only state here
                 carrying entry_price/stop_price (+ `_entry_idx` for settlement)
      ready      the daily RECLAIM happened (replay TRIGGERED) — a SET-UP awaiting the 3b
                 confirmation entry (first5/gdl, Phase 6); NOT itself an entry
      coiled     reclaimed pivot + tight + quiet (immature coil — no mature base yet)
      armed      undercut of gap_day_low, no qualifying coil yet
      watched    gap seeded, no undercut yet
      expired    no undercut within the arm window
    rmv_5d/15d + tight_close_pct are recorded TELEMETRY (not gates)."""
    cyc = cycle_for_gap(bars, gap_day)
    if cyc is None:
        return None
    last_idx = len(bars) - 1
    last = bars[last_idx]
    prev = bars[last_idx - 1] if last_idx > 0 else None
    row = {
        "gap_day": gap_day, "gap_day_low": cyc["gap_day_low"], "gap_day_vol": cyc["gap_day_vol"],
        "sma200_at_gap": _sma([b["c"] for b in bars], cyc["gap_idx"], 200),
        "armed_date": cyc["armed_date"], "ready_date": cyc["ready_date"],
        "coiled_date": None, "triggered_date": None, "entry_tactic": None,
        "entry_price": None, "stop_price": None, "base_run": None, "reenter_count": 0,
        "rmv_5d": compute_rmv(bars, last_idx, lookback=5),
        "rmv_15d": compute_rmv(bars, last_idx, lookback=15),
        "tight_close_pct": (abs(last["c"] / prev["c"] - 1) if prev and prev["c"] else None),
        # generalized tightening RECORD at the current bar — broad telemetry (operator 6/16):
        # captures tightening-into-a-pivot on every name (incl. pre-arm watched names that pull
        # into an MA/rest WITHOUT undercutting the gap-low) → the calibration set for a future
        # generalized ARMED gate. Gates nothing today.
        **tightening_telemetry(bars, last_idx, cyc["gap_idx"], armed_idx=cyc["armed_idx"]),
        "armed_shape": None,
        "_entry_idx": None,
    }

    if cyc["armed_idx"] is None:
        row["state"] = "expired" if (cyc["expired"] or last_idx - cyc["gap_idx"] > ARM_WINDOW) else "watched"
        return row

    # the pullback shape that armed it (today always includes gap_low_undercut — the narrow gate;
    # co-present MA/low-vol shapes recorded too, so the broadening evidence accrues per-row)
    row["armed_shape"] = detect_pullback_shape(bars, cyc["gap_idx"], cyc["armed_idx"])[0]

    ctx = {"gap_day_low": cyc["gap_day_low"], "armed_idx": cyc["armed_idx"],
           "trig_idx": cyc["ready_idx"]}
    coiled = find_coiled_days(bars, ctx, min_base=1)
    mature = [i for i in coiled if base_run(bars, ctx, i) >= min_base]

    if mature:                                   # mature coil → (shadow) anticipation entry
        ci = mature[0]
        row.update(state="triggered", entry_tactic="anticipation",
                   coiled_date=bars[ci]["date"], triggered_date=bars[ci]["date"],
                   entry_price=bars[ci]["c"], stop_price=bars[ci]["l"],
                   base_run=base_run(bars, ctx, ci), _entry_idx=ci)
        return row

    if coiled:
        row["coiled_date"] = bars[coiled[0]]["date"]
        row["base_run"] = base_run(bars, ctx, coiled[-1])

    if cyc["ready_idx"] is not None:
        row["state"] = "ready"                   # reclaim set-up, awaiting the 3b entry
    elif coiled:
        row["state"] = "coiled"
    else:
        row["state"] = "armed"
    return row


# ═════════════════════════════════════════════════════════════════════════════
# FAMILY A — "consolidation plays post a runup" (ADR 0013, operator-signed §2). A SEPARATE
# lifecycle from the gap-anchored machine above (`replay`/`evaluate_candidate` = FAMILY B, the
# delayed-EP/fishhook rework, #297): runup → coil (constructive tightening; undercut ALLOWED) →
# [3 entry modes DEFERRED]. This Phase-1 build is the SHADOW RECORDER only — it confirms the
# runup canary + records the coil/tightness telemetry per (ticker, anchor_date). The signed
# deliverable is the SHORTLIST for operator judgment; tightness is ORDERING-ONLY (an open
# question — the 6/16 probe did NOT show it isolating the picks). Entry modes (Anticipate /
# Confirm-flag / U&R) + realized-R settlement + the flag-detector WATCH_UR change are later,
# separately-gated phases.
#
# ANCHOR-STABILITY INVARIANT (the production trap the advisor flagged 6/17): the lifecycle key
# is the ABSOLUTE runup-peak-close date, NOT a scan-relative "last N bars from today" index. A
# scan-relative key drifts as the window slides → the nightly re-scan writes a DUPLICATE row for
# the same setup → transition-dedup silently breaks (this project's recurring failure class).
# The peak-close date for an active consolidation does not move day-to-day, so the same setup
# re-keys identically. Verified empirically (6/16-vs-6/17) before the job is un-paused.
#
# Reuses the tightening PRIMITIVES (`compute_fresh_tightening`, `compute_rmv`, `tight_close_streak`,
# `_sma`, `_adv`) — but NOT `detect_pullback_shape`, whose `gap_low_undercut` is gap-anchored
# (FAMILY B). Family-A coil shapes are the constructive pivots (MA-pullback / low-vol rest); the
# base-low undercut → U&R is an ENTRY MODE, deferred with the rest.
# ═════════════════════════════════════════════════════════════════════════════
RUNUP_MIN = 1.15        # §2 SIGNED: MAX(close)/MIN(close) ≥ 1.15 = a "runup" (a ≥15% leg)
RUNUP_WINDOW = 10       # §2 SIGNED: over a rolling 10-session window
CONSOL_AGE_OUT = 20     # sessions past the peak before the setup ages out (board hygiene, NOT a gate)
TIGHT_SERIES_MIN = 2    # Pradeep "a series of tight days in the previous two bars" → ≥2 (ranking, not a gate)


def consolidation_shapes(bars, i):
    """The constructive-coil SHAPE(s) bar `i` exhibits — the Family-A analog of
    `detect_pullback_shape` WITHOUT the gap-anchored `gap_low_undercut` (that's FAMILY B / the
    deferred U&R entry mode). Reuses the same MA-near + low-vol-rest constants — no new gate
    numbers. Returns (primary | None, [all_shapes])."""
    b = bars[i]
    closes = [x["c"] for x in bars]
    vols = [x["v"] for x in bars]
    shapes = []
    for lbl, n in (("ma10", 10), ("ma20", 20)):          # close pulled into a moving average
        ma = _sma(closes, i, n)
        if ma and abs(b["c"] - ma) / b["c"] * 100.0 <= _MA_NEAR_PCT:
            shapes.append(f"{lbl}_pullback")
    rng = (b["h"] - b["l"]) / b["c"] if b["c"] else 1.0  # tight + quiet, no pivot
    adv = _adv(vols, i)
    if rng <= TIGHT_RANGE and adv and b["v"] <= VOL_CONTRACT * adv:
        shapes.append("low_vol_rest")
    primary = next((s for s in ("ma10_pullback", "ma20_pullback", "low_vol_rest") if s in shapes), None)
    return primary, shapes


def consolidation_telemetry(bars, i, anchor_idx):
    """The Family-A coil RECORD at bar `i` (records, gates nothing). base_age = bars since the
    runup peak so the fresh-tightening primitive has a base to measure against. Reuses the shared
    tightness atoms; returns a flat JSON/SQL-native dict."""
    base_age = max(i - anchor_idx, 0)
    recent = [b["v"] for b in bars[max(anchor_idx, i - 5):i]] if i > anchor_idx else []
    recent_avg_vol = (sum(recent) / len(recent)) if recent else None
    fires, fresh_tr_pct, atr14_pct = compute_fresh_tightening(
        bars, i, base_age, recent_avg_vol=recent_avg_vol)
    primary, shapes = consolidation_shapes(bars, i)
    return {
        "pullback_shape": primary,
        "pullback_shapes": ",".join(shapes) if shapes else None,
        "fresh_tightening": bool(fires),
        "fresh_2bar_tr_pct": round(fresh_tr_pct, 3) if fresh_tr_pct is not None else None,
        "atr14_pct": round(atr14_pct, 3) if atr14_pct is not None else None,
        "tight_close_streak": tight_close_streak(bars, i),   # Pradeep's "series of tight days"
    }


# ═════════════════════════════════════════════════════════════════════════════
# #391 COIL-FINDER — operator-locked anticipation model (2026-06-27), SHADOW telemetry.
# Anatomy: RUNUP (≥15% leg) → HOLD (consolidation low above ~50% retrace of the runup leg —
# give back more than half and the runup is negated, regardless of tightness) → TIGHT flat
# coil. Unlike evaluate_consolidation (peak-anchored base = peak..now, which swallows a
# pullback and inflated CRWD to a 24% "base"), this measures the runup LEG, the give-back, and
# the RECENT coil tightness SEPARATELY. Validated against the operator cohort in
# docs/analysis/anticipation_coil_finder_validation_2026-06-27.md (finds all 5 operator coils
# incl HNGE's May base; rejects GPGI's 199% retrace). The HOLD gate is applied by the CALLER
# (evaluate_coil_consolidation), NOT here — `retrace` is returned so the cap lives in ONE place
# (COIL_HOLD_LIMIT), tuned there.
# Pure; no I/O. Operates on db_rows_to_bars shape {date,o,h,l,c,v}.
COIL_RUNUP_LB = 45        # window (bars) to locate the runup peak
COIL_RUNUP_MIN = 1.15     # the leg must be ≥15% (peak / prior swing low)
COIL_PRE_LB = 30          # look back this far before the peak for the runup-leg base (swing low)
COIL_MIN_CONS = 4         # min consolidation bars after the peak
COIL_WINDOW = 12          # tightness (band / slope / adr) measured over the recent N bars
COIL_HOLD_LIMIT = 0.50    # SOFT, operator-tunable cap on the retrace of the runup leg the
                          # consolidation may give back — evaluate_coil_consolidation gates on it
                          # ("shallower the better, 50% is the rough limit" — operator 6/27, to be tested).


def find_coil_setup(bars, i):
    """The #391 coil at bar `i`, or None. RUNUP leg → consolidation give-back (retrace) →
    recent-coil tightness, all measured separately. Returns a flat dict (peak_date, runup,
    cons_days, retrace, coil_days, base_len, band, slope, adr) or None if there is no qualifying
    runup→consolidation. Does NOT apply the HOLD gate — returns `retrace` so the caller filters
    on COIL_HOLD_LIMIT (keeps the ~50% cap tunable). Pure python, no numpy."""
    closes = [b["c"] for b in bars]
    if i < COIL_RUNUP_LB + 5:
        return None
    pk = max(range(i - COIL_RUNUP_LB, i + 1), key=lambda k: closes[k])   # runup peak
    cons_days = i - pk
    if cons_days < COIL_MIN_CONS:                                        # need a consolidation after it
        return None
    peak = closes[pk]
    pre = min(range(max(0, pk - COIL_PRE_LB), pk + 1), key=lambda k: closes[k])
    prelow = closes[pre]
    leg = peak - prelow
    if leg <= 0 or peak / prelow < COIL_RUNUP_MIN:
        return None
    cons = bars[pk + 1:i + 1]
    retrace = (peak - min(b["l"] for b in cons)) / leg                   # fraction of the leg given back
    win = cons[-min(len(cons), COIL_WINDOW):]                            # the recent coil
    hi = max(b["h"] for b in win)
    lo = min(b["l"] for b in win)
    mc = sum(b["c"] for b in win) / len(win)
    band = (hi - lo) / mc
    ys = [b["c"] for b in win]
    nx = len(ys)
    xs = list(range(nx))
    mxx = sum(xs) / nx
    myy = sum(ys) / nx
    den = sum((x - mxx) ** 2 for x in xs)
    slope = (sum((x - mxx) * (y - myy) for x, y in zip(xs, ys)) / den / mc) if den else 0.0
    # DURATION: how far back the close stays inside the coil [lo, hi] = the FULL base, not just the
    # recent window (a months-long base is "too long to wait" — Pradeep 3-20d). A ranking signal.
    base_len = 0
    for k in range(i, -1, -1):
        if lo <= bars[k]["c"] <= hi:
            base_len += 1
        else:
            break
    # ORDERLINESS: mean daily range % over the coil (gappy / drunken-man-walk = high; tight orderly = low).
    adr = sum((b["h"] - b["l"]) / b["c"] for b in win) / len(win) * 100
    return {
        "peak_date": bars[pk]["date"],
        "peak_idx": pk,                      # the runup-peak index — lets the caller skip a re-scan
        "peak_price": peak,
        "runup": peak / prelow,
        "cons_days": cons_days,
        "retrace": retrace,
        "coil_days": len(win),
        "base_len": base_len,
        "band": band,
        "slope": slope,
        "adr": adr,
    }


# ── Buyout / deal-PIN shape guard (#410, operator-filed 2026-06-30 post-NUVL FP) ──────────
# NUVL 6/30: gapped ~37% to the acquisition price and flatlined — the "tight days at the apex"
# the coil-finder read were the post-deal PIN, not an organic coil (buy 123.50 / stop 123.43 =
# 0.06% stop distance was the giveaway). Independent of news (#387, ma_filter.is_likely_ma,
# applied by the caller/job) — this is a pure price-SHAPE guard so an unannounced or
# coverage-gap deal-pin still gets caught. REUSES flag_detector's proven deal-pin primitive
# (`_evaluate_deal_pin`, the KALV 2026-05-11 catch — median (H-L)/close < 0.5% across >= 5 of
# the sampled sessions) over the coil's own recent-tightness window rather than a parallel
# formula (search-before-build).
COIL_PIN_GAP_LEG_MIN = 0.60   # a single bar supplying >= this much of the WHOLE runup leg (60%+
                               # of the peak/prelow move landing in ONE day) = a gap-driven leg,
                               # not an organic multi-day climb — paired with the deal-pin
                               # flatness test for the full gap-to-flat signature (NUVL: the
                               # entire +37% leg was one bar -> ratio 1.0).


def coil_pin_reject_reason(bars: list[dict], coil: dict) -> Optional[str]:
    """Buyout/deal-PIN shape check on a `find_coil_setup` result. Returns a distinct reject
    reason ('stop_floor' | 'gap_to_flat'), or None when the coil reads organic. Does NOT gate
    inside find_coil_setup itself — mirrors the HOLD-gate split (retrace exposed, gated by
    evaluate_coil_consolidation) so the raw coil dict stays inspectable/testable in isolation.
    Pure; no I/O; the caller (evaluate_coil_consolidation) applies the reject, and the job layer
    (scheduler._consolidation_readiness_job) re-derives + audits the distinct reason on a reject
    so it is NOT silently dropped.

      stop_floor  — the coil's own recent window fails the deal-pin flatness test: a real coil's
                    tightest days still show SOME range; a pinned deal price does not (this is
                    the "stop distance below a floor" guard — a would-be entry/stop off this
                    window implies a sub-half-percent stop, which no genuine coil produces).
      gap_to_flat — ADDITIONALLY, a single bar supplied >= COIL_PIN_GAP_LEG_MIN of the whole
                    runup leg (a gap INTO the price, not a multi-day climb) — the classic
                    gap-then-flatline deal-pin signature (NUVL).
    """
    pk, cons_days = coil["peak_idx"], coil["cons_days"]
    i = pk + cons_days                      # == the bar index find_coil_setup(bars, i) was called with
    cons = bars[pk + 1:i + 1]
    win = cons[-min(len(cons), COIL_WINDOW):]
    pin_sig = _evaluate_deal_pin(bars_to_rmv_rows(win))
    if pin_sig is None or not pin_sig["is_pin"]:
        return None                          # not enough window data, or a real (non-flat) coil
    if pk > 0 and coil.get("runup"):
        prior_close = bars[pk - 1]["c"]
        peak_price = coil["peak_price"]
        leg = peak_price - (peak_price / coil["runup"])      # == peak - prelow
        bar_gap = peak_price - prior_close                    # the peak day's own single-bar move
        if leg > 0 and prior_close and (bar_gap / leg) >= COIL_PIN_GAP_LEG_MIN:
            return "gap_to_flat"
    return "stop_floor"


def evaluate_coil_consolidation(bars, *, hold_limit=COIL_HOLD_LIMIT):
    """#327 LIVE Family-A base detection (operator-integrated 2026-06-27) — REPLACES the
    peak-anchored evaluate_consolidation, which anchored at the runup peak and called peak..now the
    "base", swallowing the post-runup PULLBACK (CRWD read a 24% band because a −21% pullback sat
    inside it). find_coil_setup locates the TRUE coil (runup LEG → give-back, measured separately)
    and applies the HOLD gate (retrace ≤ hold_limit of the runup leg — give back more than half and
    the runup is negated, NOT basing, regardless of tightness). The SAME tightness telemetry +
    lifecycle state (coiled/post_runup/aged) are then recorded against the CORRECTED anchor (the
    coil's runup peak), so upsert_consolidation + the board + the entry signals are unchanged.

    Returns (result, reject_reason) (simplify GROUP 2, 2026-07-03 — was bare None on any reject,
    which forced the caller, scheduler._consolidation_readiness_job, to re-run find_coil_setup +
    the hold check + coil_pin_reject_reason itself just to audit WHY). `result` is the
    evaluate_consolidation-shaped dict (anchor_date = the coil peak), or None on any reject.
    `reject_reason` is None for a plain miss (no runup→coil, or gave back > hold_limit) and
    'stop_floor' / 'gap_to_flat' specifically for the #410 buyout/deal-pin guard — the only case
    the caller needs to distinguish (audit-worthy) from a normal non-candidate (silent skip).
    SHADOW recorder: NO entry/stop/settlement here."""
    coil = find_coil_setup(bars, len(bars) - 1)
    if coil is None or coil["retrace"] > hold_limit:
        return None, None                            # no runup→coil, or gave back > ~50% (negated)
    pin_reason = coil_pin_reject_reason(bars, coil)
    if pin_reason:
        return None, pin_reason                       # #410 buyout/deal-pin shape (NUVL-class FP)
    anchor_date = coil["peak_date"]
    anchor_idx = coil["peak_idx"]            # from find_coil_setup — provably in-bars, no re-scan
    last_idx = len(bars) - 1
    last = bars[last_idx]
    prev = bars[last_idx - 1] if last_idx > 0 else None
    coil_days = last_idx - anchor_idx                 # bars since the peak (board semantics, unchanged)
    tel = consolidation_telemetry(bars, last_idx, anchor_idx)
    if coil_days > CONSOL_AGE_OUT:
        state = "aged"
    elif tel["fresh_tightening"] or tel["tight_close_streak"] >= TIGHT_SERIES_MIN:
        state = "coiled"
    else:
        state = "post_runup"
    return {
        "anchor_date": anchor_date,
        "state": state,
        "runup_ratio": round(coil["runup"], 4),
        "runup_high": round(coil["peak_price"], 4),
        "coil_days": coil_days,
        "last_close": round(last["c"], 4),
        "today_pct": (round(abs(last["c"] / prev["c"] - 1), 5) if prev and prev["c"] else None),
        "rmv_5d": compute_rmv(bars, last_idx, lookback=5),
        "rmv_15d": compute_rmv(bars, last_idx, lookback=15),
        "hold_retrace": round(coil["retrace"], 4),    # NEW: give-back of the runup leg (the hold gate)
        **tel,
    }, None


# ═════════════════════════════════════════════════════════════════════════════
# #327 ENTRY SIGNAL — the validated coil-apex timing gate (SHADOW, SINGLE-SOURCE).
# Validated 2026-06-18 (docs/analysis/ninem_consolidation_vs_day2_replay_327_2026-06-18.md):
# across the 9M coil cohort, PERSISTENCE — N consecutive tight days — NOT rmv DEPTH — times the
# entry. N=3 lifts capture 32%→44% and median uncapped MFE +0.8R→+2.1R, STOP-MATCHED, and the
# lift survives turning each knob (Δ +9–12pp) in a robust REGION: daily range ≤5–7%, vol ≤1.0×ADV,
# rmv_5d ≤30–40, N=2–3. It VANISHES under over-tight level gates (range≤4% → Δ0; vol≤0.7 noisy) →
# the gate sits at the inclusive edge. This is THE single source for the signal: the offline sweep
# (scripts/_327_entry_signal.py) AND the live entry-watch (scheduler._consolidation_readiness_job)
# both call is_entry_tight — tests/test_consolidation_entry_signal.py pins it so the forward shadow
# measures the validated signal, not a re-implementation that drifted. SHADOW: records the would-be
# entry; ZERO execution authority.
# ─────────────────────────────────────────────────────────────────────────────
ENTRY_RMV_MAX = 30.0     # rmv_15d ≤ this = contracted. PROVISIONAL — creator's "<30 = getting tight"
                         # on the ratio-to-baseline RMV (creator-confirmed 2026-06-27); the operator's
                         # labeling pass calibrates the final value (the N≥10 evidence). Gate moved
                         # rmv_5d→rmv_15d: the new ratio form only reads "contracted" against the long
                         # baseline — the 5-bar window overlaps the recent run (~50 for a real coil).
                         # #327 is SHADOW (not traded). See ADR 0013 change-log.
ENTRY_RANGE_MAX = 0.07   # daily (H−L)/C ≤ this (== TIGHT_RANGE; robust 5–7%)
ENTRY_VOL_MAX = 1.0      # vol ≤ this × ADV20 (== VOL_CONTRACT, the quiet "rest")
ENTRY_TIGHT_N = 3        # consecutive tight days before the fire (the validated count; 2–3 region)
ENTRY_TARGET_R = 3.0     # "capture" = forward MFE reaches +TARGET_R × risk before the stop (settle def)


# ── #385 volume dry-up TELEMETRY (Gemini review 6/27) — a SECOND, independent contraction axis
#    alongside rmv_5d/rmv_15d. RMV (_compute_rmv) reads gap-aware TRUE RANGE only — it has no
#    visibility into volume, so a range-tight bar on ELEVATED volume (a drift, not a rest) reads
#    identically to a genuine low-volume coil. Recording the volume axis SEPARATELY lets the
#    graduation eval test whether dry-up (reduced-but-active volume) predicts coil outcomes better
#    than range contraction alone — "the two together separate a coil from a drift" (PLAN #385).
#    Mirrors compute_rmv's OWN window shape (current_window=3 over lookback=15) so the two axes are
#    directly comparable — same naming convention (_3/_15), never overloads rmv_*. TELEMETRY ONLY —
#    not a gate; #327's is_entry_tight is unchanged (rmv_15d + range + vol-vs-ADV only). ──────────
def volume_dryup(bars: list[dict], idx: int, *, current_window: int = 3, lookback: int = 15):
    """(vol_sma_3, vol_sma_15, vol_dryup_ratio) at bar `idx` — plain volume SMAs over the trailing
    `current_window` / `lookback` bars (mean(volume), NOT ADV-normalized) + their ratio (lower =
    more dried up vs the recent baseline). Backward-looking only (reads bars[:idx+1]) — point-in-time
    safe, same discipline as is_entry_tight's own gate reads. Returns (None, None, None) when fewer
    than `lookback` bars are available ending at `idx` (mirrors _compute_rmv's own insufficient-
    history floor) or the baseline mean is 0 (dead/void feed — no denominator to ratio against)."""
    if idx < lookback - 1:
        return None, None, None
    vols = [b["v"] for b in bars]
    vol_sma_3 = sum(vols[idx - current_window + 1: idx + 1]) / current_window
    vol_sma_15 = sum(vols[idx - lookback + 1: idx + 1]) / lookback
    ratio = round(vol_sma_3 / vol_sma_15, 4) if vol_sma_15 else None
    return round(vol_sma_3, 1), round(vol_sma_15, 1), ratio


def is_entry_tight(bars, rmv_rows, vols, i, *, rmv_max=ENTRY_RMV_MAX,
                   range_max=ENTRY_RANGE_MAX, vol_max=ENTRY_VOL_MAX) -> bool:
    """One bar's #327 tightness gate — contracted rmv_15d + tight daily range + quiet volume.
    Backward-looking only (reads bars/rmv_rows/vols up to `i`). The SINGLE per-bar feature the
    offline sweep and the live entry-watch share (pinned by the golden test). `rmv_rows`/`vols` are
    passed in (not rederived per-bar) so a run-scan over many bars stays cheap. Gates on rmv_15d (the
    ratio-RMV's canonical baseline) — rmv_5d's 5-bar window overlaps the recent run, reading ~50 for a
    real coil (creator-confirmed 2026-06-27)."""
    rmv = _compute_rmv(rmv_rows, i, lookback=15)
    if rmv is None or rmv > rmv_max:
        return False
    c = bars[i]["c"]
    if not c or (bars[i]["h"] - bars[i]["l"]) / c > range_max:
        return False
    if not bars[i]["v"]:
        return False  # volume-dead bar (halt / void) — a real VCP rest still trades shares (Gemini 2026-06-27)
    adv = _adv(vols, i)
    return bool(adv) and bars[i]["v"] <= vol_max * adv


def entry_signal_at(bars, idx, anchor_idx, *, n=ENTRY_TIGHT_N, rmv_max=ENTRY_RMV_MAX,
                    range_max=ENTRY_RANGE_MAX, vol_max=ENTRY_VOL_MAX):
    """Point-in-time #327 entry signal AS OF bar `idx` (reads only bars[:idx+1]): do the trailing
    N bars — all strictly AFTER the runup peak `anchor_idx` — each pass is_entry_tight? Returns the
    fire record (the would-be anticipate entry + both measured stops + the gate readings) on a fire,
    else None. The coil-apex bet: capture the imminent expansion, or take a quick tight-stop loss.
    SHADOW only — the live job RECORDS the row, never submits."""
    run_lo = idx - n + 1
    if run_lo < 0 or run_lo <= anchor_idx or idx >= len(bars):
        return None                                  # the coil run must form AFTER the runup peak
    rr = bars_to_rmv_rows(bars)
    vols = [b["v"] for b in bars]
    if not all(is_entry_tight(bars, rr, vols, j, rmv_max=rmv_max, range_max=range_max,
                              vol_max=vol_max) for j in range(run_lo, idx + 1)):
        return None
    entry = bars[idx]["c"]
    adv = _adv(vols, idx)
    vol_sma_3, vol_sma_15, vol_dryup_ratio = volume_dryup(bars, idx)   # #385 — 2nd contraction axis
    return {
        "entry_date": bars[idx]["date"],
        "entry_price": round(entry, 4),
        "signal_n": n,
        "rmv_5d": _compute_rmv(rr, idx, lookback=5),       # 2nd telemetry (NOT the gate now)
        "rmv_15d": _compute_rmv(rr, idx, lookback=15),     # the gate reading (#327 gates on this)
        "range_pct": round((bars[idx]["h"] - bars[idx]["l"]) / entry, 5) if entry else None,
        "vol_ratio": round(bars[idx]["v"] / adv, 3) if adv else None,
        "vol_sma_3": vol_sma_3,             # #385 volume dry-up telemetry — TELEMETRY ONLY, not a gate
        "vol_sma_15": vol_sma_15,
        "vol_dryup_ratio": vol_dryup_ratio,
        "stop_kind": "coiled_low",                   # the validated default stop (robustness baseline)
        "stop_price": round(bars[idx]["l"], 4),      # coiled_low = the entry bar's low
        "structural_low": round(min(bars[j]["l"] for j in range(run_lo, idx + 1)), 4),  # alt stop, recorded
        "target_r": ENTRY_TARGET_R,
    }


# ── CONFIRM entry mode (ADR 0013 §1 — flag→consolidation merge, 2026-06-22) ──────
# The second Family-A entry mode: enter on the CONFIRMED breakout of the consolidation base, stop at
# the base low. ADR §1 "Confirm = on the CONFIRMED breakout (base_high + volume)". Detected on the
# SAME §2 consolidation universe via the daily bars — deliberately NOT by reusing the live #94
# intraday flag-break job / mi_flag_breaks (which lives on the flag detector's separate 50%/60d
# universe): gating Confirm by flag-cohort membership would silently under-detect on exactly the §2
# names we are told to measure (the #270 phantom failure-mode in miniature) AND touch the load-bearing
# live path. A NEW pure detector mirroring entry_signal_at keeps Confirm on the signed universe +
# isolated. Returns the would-be entry; ZERO execution authority (the live job RECORDS, never submits).
ENTRY_CONFIRM_VOL_MIN = 1.5   # breakout volume ≥ this × ADV20 (flag_detector's confirmed-break vol gate)


def confirm_signal_at(bars, idx, anchor_idx, *, vol_min=ENTRY_CONFIRM_VOL_MIN):
    """Point-in-time CONFIRM entry AS OF bar `idx` (reads only bars[:idx+1]): the consolidation base
    BREAKS OUT — today's close exceeds the highest base close (post-runup-peak, pre-break) AND volume
    confirms (≥ vol_min × ADV20). Entry = the break-day close; stop = the base low (ADR §1 "base /
    breakout low"). Returns the fire record on a fire, else None. SHADOW only."""
    if idx < anchor_idx + 2 or idx >= len(bars):
        return None                                  # need a base between the runup peak and the break
    base_high = max(bars[j]["c"] for j in range(anchor_idx + 1, idx))   # consolidation high (post-peak, pre-break)
    close = bars[idx]["c"]
    if not close or close <= base_high:
        return None                                  # today does not close above the base
    vols = [b["v"] for b in bars]
    adv = _adv(vols, idx)
    if not adv or bars[idx]["v"] < vol_min * adv:
        return None                                  # the break must come on confirming volume
    rr = bars_to_rmv_rows(bars)
    base_low = round(min(bars[j]["l"] for j in range(anchor_idx + 1, idx + 1)), 4)  # the stop = base low
    vol_sma_3, vol_sma_15, vol_dryup_ratio = volume_dryup(bars, idx)   # #385 — parity with anticipate
    return {
        "entry_date": bars[idx]["date"],
        "entry_price": round(close, 4),
        "signal_n": 0,                               # n/a for confirm (not a tight-day-count signal) — sentinel
        "rmv_5d": _compute_rmv(rr, idx, lookback=5),
        "rmv_15d": _compute_rmv(rr, idx, lookback=15),   # parity with anticipate (telemetry; confirm gates on the breakout)
        "range_pct": round((bars[idx]["h"] - bars[idx]["l"]) / close, 5) if close else None,
        "vol_ratio": round(bars[idx]["v"] / adv, 3) if adv else None,
        "vol_sma_3": vol_sma_3,             # #385 volume dry-up telemetry — TELEMETRY ONLY, not a gate
        "vol_sma_15": vol_sma_15,
        "vol_dryup_ratio": vol_dryup_ratio,
        "stop_kind": "base_low",                     # Confirm stop = the base low
        "stop_price": base_low,
        "structural_low": base_low,
        "target_r": ENTRY_TARGET_R,
    }


# ── #327 forward-shadow SETTLEMENT (operator "build the machinery now", 6/18) ──
# The validation's PRIMARY metric was the asymmetric bet (capture% + UNCAPPED MFE/risk under a
# FIXED stop) — the clean entry-quality signal (the harvest buries good entries, #270-Step-0). The
# secondary, decision-relevant column is the BANKABLE realized R under the +1R/+3R day-5 ladder
# (SETTLE_RULE) — faithful to the offline #327 replay. We record BOTH; they intentionally use
# DIFFERENT horizons (the 12-bar OBSERVATION window for the bet vs the rule's own day-5 time-stop).
ENTRY_SETTLE_WINDOW = 12   # forward trading bars to observe the asymmetric bet (the validation horizon)


def entry_bet_outcome(bars, entry_idx, stop, *, target_r=ENTRY_TARGET_R, window=ENTRY_SETTLE_WINDOW,
                      entry_price=None, include_entry_bar=False):
    """The validated asymmetric bet from a close-of-coil entry under a FIXED `stop`, over `window`
    forward bars: returns (outcome, fwd_mfe_r) where outcome ∈ capture (MFE hits +target_r×risk
    first) / stop (stop hit first) / open (neither by window end); fwd_mfe_r = UNCAPPED favorable
    excursion / risk (the entry-quality measure). None if risk ≤ 0. The SINGLE source — the offline
    sweep (scripts/_327_entry_signal.bet_outcome) delegates here, pinned by the settle test. A
    same-bar target is credited capture (the rare h≥tgt & l≤stop tie is second-order for this read).

    `entry_price` / `include_entry_bar` (F11, #356 dedup — flag_detector._htf_settle_from_bars'
    two named deltas) generalize the close-of-coil default to an intraday-fill entry: `entry_price`
    overrides the default fill (bars[entry_idx]['c']) — for an entry that fills at a different price
    than the bar's close (e.g. a stop-limit-buy fill at base_high); `include_entry_bar` starts the
    forward scan AT entry_idx instead of entry_idx+1 — for a fill that happens intraday, where the
    entry bar's own remaining range is still live (vs. the default close-of-bar entry, where the
    entry bar is already fully priced in and the scan starts the NEXT bar). Both default to the
    ORIGINAL close-entry / next-bar-only semantics — EXACT prior behavior when omitted."""
    entry = float(entry_price) if entry_price is not None else bars[entry_idx]["c"]
    if stop is None or stop >= entry:
        return None
    risk = entry - stop
    tgt = entry + target_r * risk
    mfe, out = entry, "open"
    start = entry_idx if include_entry_bar else entry_idx + 1
    for i in range(start, min(entry_idx + 1 + window, len(bars))):
        b = bars[i]
        mfe = max(mfe, b["h"])
        if b["h"] >= tgt:
            out = "capture"
            break
        if b["l"] <= stop:
            out = "stop"
            break
    return out, (mfe - entry) / risk


def settle_entry_shadow(bars, entry_idx, stop_price, *, target_r=ENTRY_TARGET_R,
                        window=ENTRY_SETTLE_WINDOW, rule=None):
    """Settle one #327 entry-shadow row from its daily bars, or None to ABSTAIN (still provisional).
    Returns {outcome, fwd_mfe_r, realized_r}:
      outcome / fwd_mfe_r ← entry_bet_outcome (the validated bet under coiled_low, the 12-bar horizon)
      realized_r          ← settle_row's anticipation harvest under SETTLE_RULE (the bankable R; a
                            close entry → settled faithfully on the daily path). REUSES the tested
                            settlement core, not a 2nd copy.

    Settles as soon as the outcome is DEFINITIVE — a capture or stop is FINAL regardless of the
    remaining window; only 'open' stays provisional until the full `window` elapses. This rescues a
    name that stops/captures then HALTS/gets acquired (the bare 12-bar gate would orphan it →
    outcome NULL forever → a survivorship hole in capture%; the residual halt-while-GENUINELY-open
    is surfaced via the readout's open_overdue count, never silently dropped — advisor 6/18).
    realized_r ABSTAINS (None) when the harvest's own min bars aren't present yet (a halt within <5
    bars); the outcome still settles — closing the survivorship hole is what matters."""
    bet = entry_bet_outcome(bars, entry_idx, stop_price, target_r=target_r, window=window)
    if bet is None:
        return None
    outcome, fwd_mfe_r = bet
    if outcome == "open" and (len(bars) - 1 - entry_idx) < window:
        return None   # neither target nor stop yet + window incomplete → provisional, abstain
    st = settle_row(entry_tactic="anticipation", entry_price=bars[entry_idx]["c"],
                    stop_price=stop_price, bars=bars, entry_idx=entry_idx, rule=rule or SETTLE_RULE)
    realized_r = st["realized_r"] if st else None
    return {"outcome": outcome, "fwd_mfe_r": round(fwd_mfe_r, 4),
            "realized_r": round(realized_r, 4) if realized_r is not None else None}


# ── Plain-words Family-A row formatters (operator 6/18 — glanceable, no acronym soup). The SINGLE
#    shared formats for /anticipation (agent.py) AND the daily Family-A digest (scheduler.py) so the
#    two can't drift (feedback_single_source_of_truth). None-safe; ordering is the caller's job. ──
def _num(v):
    try:
        return float(v) if v is not None else None
    except (TypeError, ValueError):
        return None


def _tightness_word(rmv):
    """RMV (0-100 contraction index, lower = tighter) → a plain-words tightness label, or None."""
    if rmv is None:
        return None
    if rmv <= 15:
        return "very tight"
    if rmv <= 40:
        return "tight"
    return "loose"


def format_consolidation_row(ticker, runup_ratio, coil_days, rmv_5d=None,
                             fresh_tightening=False, coiled=True) -> str:
    """A Family-A candidate row.  coiled=True (the tight shortlist):
        `LUNL ` +70% · coiling 14d · very tight · tightening↓
    coiled=False (post-runup, NOT coiled yet — the tightness word would read as a contradiction in
    that section, so omit it; show only runup + age):
        `FUTU ` +17% · 15d since peak"""
    ru, rmv = _num(runup_ratio), _num(rmv_5d)
    ru_s = f"+{(ru - 1) * 100:.0f}%" if ru is not None else "?%"
    if not coiled:
        return f"  `{ticker:<5}` {ru_s} · {coil_days or 0}d since peak"
    parts = [ru_s, f"coiling {coil_days or 0}d"]
    word = _tightness_word(rmv)
    if word:
        parts.append(word)
    if fresh_tightening:
        parts.append("tightening↓")
    return f"  `{ticker:<5}` " + " · ".join(parts)


def format_entry_fired_row(ticker, entry_price, stop_price, origin=None) -> str:
    """A #327 entry-shadow that fired — the would-be anticipate entry.
        `PRIM ` buy 101.30 · stop 100.09 (−1.2%) · 9M"""
    e, s = _num(entry_price), _num(stop_price)
    stop_pct = f" ({(s / e - 1) * 100:+.1f}%)" if (e and s) else ""
    tag = " · 9M" if origin == "9m" else ""
    e_s = f"buy {e:.2f}" if e is not None else "buy ?"
    s_s = f"stop {s:.2f}" if s is not None else "stop ?"
    return f"  `{ticker:<5}` {e_s} · {s_s}{stop_pct}{tag}"


def format_entry_settled_row(ticker, outcome, realized_r) -> str:
    """A settled #327 entry-shadow.  `PRIM ` ✓ captured +3.0R · ✗ stopped −1.0R · ○ timed out +0.4R"""
    r = _num(realized_r)
    icon, word = {"capture": ("✓", "captured"), "stop": ("✗", "stopped"),
                  "open": ("○", "timed out")}.get(outcome, ("·", outcome or "?"))
    r_s = f" {r:+.1f}R" if r is not None else ""
    return f"  `{ticker:<5}` {icon} {word}{r_s}"


def select_consolidation_keys(universe, existing):
    """Decide which (ticker, anchor_date) the readiness job evaluates — the CARRY-FORWARD that keeps
    the lifecycle key STABLE when the rolling-window anchor drifts. The §2 universe re-derives the
    anchor each scan; a base whose runup peak ages out of the 15-session window would otherwise
    re-key to a lesser peak → a DUPLICATE row for the SAME leg (the 6/17 probe: 7/71 names drifted in
    one day, all off the aging-out 2026-05-26 peak). Mirrors Family-B's seed∪live key union, plus the
    'same leg or new leg?' branch a rolling anchor needs (Family-B's gap_day is event-fixed, so its
    union is trivially stable).

    universe: [{'ticker','anchor_date','runup_high','dvol_med'}] — the fresh §2 proposer.
    existing: {ticker: [{'anchor_date','runup_high','dvol_med'}]} — the non-aged rows already recorded.
    Returns [{'ticker','anchor_date','dvol_med'}] to evaluate:
      • every existing non-aged row, with ITS stored anchor (carry-forward — the stable key);
      • a universe candidate ONLY when it is a genuinely NEW setup: the ticker has no existing
        non-aged row, OR today's runup_high exceeds EVERY existing anchor's high (a new higher-high
        leg). A universe re-anchor to a LESSER peak (the old peak aged out) is IGNORED — the carried
        row already covers that leg.
    Changes WHICH keys are evaluated, NOT §2 membership (the gate is unchanged — job-layer concern)."""
    out, seen = [], set()
    for tk, rows in existing.items():
        for r in rows:
            key = (tk, r["anchor_date"])
            if key not in seen:
                out.append({"ticker": tk, "anchor_date": r["anchor_date"],
                            "dvol_med": r.get("dvol_med")})
                seen.add(key)
    for u in universe:
        key = (u["ticker"], u["anchor_date"])
        if key in seen:
            continue
        ex = existing.get(u["ticker"])
        if not ex or (u.get("runup_high") or 0) > max((r.get("runup_high") or 0) for r in ex):
            out.append({"ticker": u["ticker"], "anchor_date": u["anchor_date"],
                        "dvol_med": u.get("dvol_med")})
            seen.add(key)
        # else: a re-anchor to a LESSER peak (old peak aged out) → the carried row covers it; skip.
    return out


# ─────────────────────────────────────────────────────────────────────────────
# 3b intraday FIRST5 / GDL confirmation entry (Phase 6, ported from
# scripts/_270_entry_replay.py). PURE: the EXECUTION-role EOD job supplies minute bars +
# persists. Detection is lookahead-SAFE (entry = the fixed first-5-min-OR high, known by
# 9:35; the forward MFE/harvest legitimately uses later bars). realized_r harvests over a
# FAITHFUL mixed minute+daily path — NEVER a daily approximation of the day-0 scale-out
# (the error this whole arc closed; the advisor's 6/16 settlement guard).
# ─────────────────────────────────────────────────────────────────────────────
_RTH_OPEN, _RTH_CLOSE = 9 * 60 + 30, 16 * 60     # ET minutes


def polygon_to_rth_minutes(raw: list[dict], et_date_iso: str) -> list[dict]:
    """Polygon 1-min aggs ({t:epoch_ms, o,h,l,c,v}) → ascending RTH bars {m,o,h,l,c} for the
    ET date. t is UTC ms; ET = UTC−4 (EDT) — matches the analysis script's convention."""
    out = []
    for b in raw:
        et = datetime.fromtimestamp(int(b["t"]) / 1000, timezone.utc) - timedelta(hours=4)
        if et.date().isoformat() != et_date_iso:
            continue
        m = et.hour * 60 + et.minute
        if not (_RTH_OPEN <= m < _RTH_CLOSE):
            continue
        out.append({"m": m, "o": float(b["o"]), "h": float(b["h"]),
                    "l": float(b["l"]), "c": float(b["c"])})
    out.sort(key=lambda x: x["m"])
    return out


def detect_first5_break(minute_bars: list[dict], gdl: float):
    """Break above the first-5-min-OR high; stop = first-5-min-OR low. Returns
    (entry, stop, break_idx) or None. Ported from _270_entry_replay.entry_first5."""
    or5 = [b for b in minute_bars if _RTH_OPEN <= b["m"] < _RTH_OPEN + 5]
    if not or5:
        return None
    hi, lo = max(b["h"] for b in or5), min(b["l"] for b in or5)
    for i, b in enumerate(minute_bars):
        if b["m"] < _RTH_OPEN + 5:
            continue
        if b["h"] > hi:                          # the break
            if hi <= lo or hi <= gdl * 0.98:     # must be a real reclaim
                return None
            return hi, lo, i
    return None


def detect_gdl_reclaim(minute_bars: list[dict], gdl: float):
    """First intraday reclaim of the gap-day-low; stop = gap-day-low. Returns
    (entry, stop, break_idx) or None. Ported from _270_entry_replay.entry_gdl."""
    for i, b in enumerate(minute_bars):
        if b["c"] > gdl:
            if b["c"] <= gdl:
                return None
            return b["c"], gdl, i
    return None


def build_mixed_path(minute_bars: list[dict], break_idx: int, daily_forward: list[dict]) -> list[dict]:
    """Day-0 MINUTE bars after the break (kind='min', day_idx=0) + the subsequent DAILY bars
    day1..N (kind='day', day_idx≥1, prior_low trailing). The faithful FIRST5 harvest geometry:
    the day-0 minute scale-out banks the bulk, the runner rides the daily trail to the day-5
    time stop. daily_forward = ascending {o,h,l,c} AFTER the trigger day."""
    path = [{"o": b["o"], "h": b["h"], "l": b["l"], "c": b["c"],
             "kind": "min", "prior_low": None, "day_idx": 0}
            for b in minute_bars[break_idx + 1:]]
    prior_low = min((b["l"] for b in minute_bars), default=None)   # day-0 low seeds the trail
    for di, b in enumerate(daily_forward, start=1):
        path.append({"o": b["o"], "h": b["h"], "l": b["l"], "c": b["c"],
                     "kind": "day", "prior_low": prior_low, "day_idx": di})
        prior_low = b["l"]
    return path


def simulate_first5(entry, stop, minute_bars, break_idx, daily_forward, rule=None) -> Optional[dict]:
    """Realized R + the scale-out fill record for a FIRST5/gdl entry, harvested over the
    FAITHFUL mixed minute+daily path. Returns {realized_r, fwd_mfe_pct, fills} or None. `fills`
    = [{day_idx, fraction}] (persisted as day0_fills for audit); realized_r is the simulate
    output over the real geometry — execution owns this because intelligence has daily bars only."""
    risk = entry - stop
    if risk <= 0:
        return None
    path = build_mixed_path(minute_bars, break_idx, daily_forward)
    if not path:
        return None
    out = simulate(entry, stop, path, rule or SETTLE_RULE, "pess")
    if out is None:
        return None
    realized_r, _captured, fills = out
    mfe = (max(b["h"] for b in path) - entry) / risk
    return {"realized_r": realized_r, "fwd_mfe_pct": mfe,
            "fills": [{"day_idx": d, "fraction": f} for d, f in fills]}


# ── ADR 0004 Stocks-in-Play feed (pure payload builder) ───────────────────
# A anticipation row that reaches ready/triggered ALSO surfaces in the unified
# /watch board (one row per detector, ADR 0004) — /sip stays the drill-down.
# This builds the (reason, readiness_signal) pair; the async DB write + TTL
# live in scheduler._feed_anticipation_sip. Kept pure so the JSON-safety of the
# readiness_signal (no raw dates/Decimals — the jsonb codec is plain json.dumps)
# is unit-testable without a DB.
_SIP_TACTIC_SHORT = {"anticipation": "anticip", "first5_break": "first5",
                     "gdl_reclaim": "gdl"}


def sip_payload(*, state, gap_day_iso, entry_tactic=None, entry_price=None,
                stop_price=None, base_run=None, rmv_5d=None):
    """Return (reason, readiness_signal) for a anticipation mi_stocks_in_play row.

    Every value in readiness_signal is JSON-native (Decimals → float, dates
    pre-stringified by the caller) so the plain-json.dumps jsonb codec can't
    choke (the date/Decimal hazard the sugar-baby site dodges by str()-ing)."""
    tac = _SIP_TACTIC_SHORT.get(entry_tactic, entry_tactic or "")
    if state == "ready":
        reason = "anticipation reclaim ready — awaiting entry"
    elif entry_price is not None:
        reason = f"anticipation {tac} entry @ {float(entry_price):.2f}"
    else:
        reason = f"anticipation {tac or 'entry'} triggered"
    signal = {
        "state": state,
        "gap_day": gap_day_iso,
        "entry_tactic": entry_tactic,
        "base_run": int(base_run) if base_run is not None else None,
        "rmv_5d": float(rmv_5d) if rmv_5d is not None else None,
        "entry_price": float(entry_price) if entry_price is not None else None,
        "stop_price": float(stop_price) if stop_price is not None else None,
    }
    return reason, signal
