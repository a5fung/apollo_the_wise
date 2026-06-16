"""#270 delayed-EP re-entry — SHADOW lifecycle composition (Step 3).

Ports the gate-free replay/coil logic (validated in `scripts/_270_*.py`) into the
production package so the readiness job (`scheduler._delayed_ep_readiness_job`) and
the `/sip` board can compose the lifecycle — EP gap → gap-low UNDERCUT → RECLAIM →
COIL → entry → harvest — from daily bars (the MNTS template). The offline scripts
stay the frozen analysis artifacts; `tests/test_delayed_ep_golden.py` pins this port
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
from typing import Optional

from agents.market_intelligence.flag_detector import _compute_rmv

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


# ─────────────────────────────────────────────────────────────────────────────
# Ported lifecycle (byte-identical to scripts/_270_delayed_ep_replay.py::replay —
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


def lifecycle(bars):
    """First cycle that reaches ARMED → structured context (gap_day_low + indices).
    None if the name never undercut. Reuses replay() so the funnel stays single-sourced."""
    idx_of = {b["date"]: i for i, b in enumerate(bars)}
    watched = armed = trig = None
    for date, state, _ in replay(bars):
        if state == "WATCHED" and armed is None:
            watched = date
        elif state == "ARMED" and armed is None and watched is not None:
            armed = date
        elif state == "TRIGGERED" and armed is not None and trig is None:
            trig = date
            break
    if armed is None or watched is None:
        return None
    return {"gap_day": watched, "gap_day_low": bars[idx_of[watched]]["l"],
            "armed_idx": idx_of[armed], "armed_date": armed,
            "trig_idx": idx_of[trig] if trig else None, "trig_date": trig}


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
# silently corrupts the calibration dataset. `tests/test_delayed_ep_golden.py`
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
                lookback: int = 5, current_window: int = 2) -> Optional[float]:
    """RMV (0-100 contraction index) on replay-shaped bars via the canonical
    flag_detector._compute_rmv — recorded telemetry on the lifecycle row, NOT a gate."""
    return _compute_rmv(bars_to_rmv_rows(bars), today_idx,
                        lookback=lookback, current_window=current_window)
