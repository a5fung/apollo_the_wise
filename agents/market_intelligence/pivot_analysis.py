"""ADR 0031 C1+C2 — per-stock character profile + confirmed-swing-pivot detection (PURE).

Requirements SSoT: docs/methodology/pivots-and-stock-character.md. v1 = the COMPUTABLE tier
only. Everything here is pure math over daily bars (dicts with high_price/low_price/close;
ascending) — no DB, no LLM, no broker. Consumers: pivot_stop_shadow (C3); later #267 prompts /
#255 memory (each behind its own gate — ADR 0031 §6.3).

All numeric parameters are v1 DEFAULTS (ADR 0031 F2, operator-signed 2026-07-12): tunable only
by shadow evidence, never re-litigated per name — the PROFILE varies per stock; the DETECTOR
stays fixed.
"""
from __future__ import annotations

import statistics

from agents.market_intelligence.broker.exit_logic import ema as _ema  # exec-boundary-ok: exit_logic is PURE exit-ladder math (no Alpaca client, no trade-state I/O) — reusing its tested ema() instead of a 4th copy (F11 discipline), same pattern as flag_detector/giveback_shadow

# ── v1 detector defaults (ADR 0031 §2) ──────────────────────────────────────
_MAS = (("sma10", "sma", 10), ("ema21", "ema", 21), ("sma20", "sma", 20), ("sma50", "sma", 50))
_TREND_WINDOW = 120          # trading bars (cap)
_REANCHOR_GAIN = 0.50        # close ≥ +50% over the prior 90d max close re-anchors (the MNTS rule)
_REANCHOR_LOOKBACK = 90
_ABOVE_RUN_MIN = 5           # closes above the MA before an episode can begin
_TOUCH_BAND = 1.02           # low ≤ MA×1.02 begins an episode
_BREAK_CONSEC = 3            # consecutive closes below the MA = BROKEN
_EPISODE_MAX_DAYS = 20       # stale → BROKEN
_PRE_HIGH_LOOKBACK = 20      # the swing high a RESPECTED episode must reclaim
_MIN_EPISODES = 3
_RESPECT_BAR = 2 / 3
_UNDERCUT_PCTL = 0.80


def _sma(vals, window):
    return sum(vals[-window:]) / window if len(vals) >= window else None


def _ma_series(closes, kind, window):
    out = []
    for i in range(len(closes)):
        seg = closes[: i + 1]
        out.append(_ema(seg, window) if kind == "ema" else _sma(seg, window))
    return out


def _trend_window_start(closes) -> int:
    """The MNTS re-anchor: the LAST index whose close ≥ (1+gain)× the prior 90d max close
    starts the character window (a re-rating resets the personality). Else the 120-bar cap."""
    start = max(0, len(closes) - _TREND_WINDOW)
    for i in range(len(closes) - 1, 0, -1):
        prior = closes[max(0, i - _REANCHOR_LOOKBACK):i]
        if prior and closes[i] >= (1.0 + _REANCHOR_GAIN) * max(prior):
            return max(start, i)
    return start


def character_profile(bars: list[dict]) -> dict | None:
    """The per-ticker character profile, or None = ABSTAIN (first-class: <3 episodes on
    every MA, or no MA clears 2/3 respect — the name stays on the global trail).

    Returns {home_ma, home_kind, home_window, undercut_p80, respect_rates,
             n_episodes, pullback_duration_med, window_anchor_idx}.
    """
    if len(bars) < 60:
        return None
    closes = [float(b["close"]) for b in bars]
    lows = [float(b["low_price"]) for b in bars]
    highs = [float(b["high_price"]) for b in bars]
    w0 = _trend_window_start(closes)

    respect_rates, episode_stats = {}, {}
    for name, kind, window in _MAS:
        ma = _ma_series(closes, kind, window)
        episodes = []      # (respected: bool, undercut: float, duration: int)
        i = w0
        above_run = 0
        while i < len(bars):
            m = ma[i]
            if m is None:
                i += 1
                continue
            if above_run >= _ABOVE_RUN_MIN and lows[i] <= m * _TOUCH_BAND:
                # episode begins at i
                pre_high = max(highs[max(0, i - _PRE_HIGH_LOOKBACK):i], default=closes[i])
                undercut, below_run, j = 0.0, 0, i
                respected = None
                while j < len(bars):
                    mj = ma[j]
                    if mj is not None and lows[j] < mj:
                        undercut = max(undercut, (mj - lows[j]) / mj)
                    if mj is not None and closes[j] < mj:
                        below_run += 1
                    else:
                        below_run = 0
                    if closes[j] >= pre_high:
                        respected = True
                        break
                    if below_run >= _BREAK_CONSEC or (j - i) >= _EPISODE_MAX_DAYS:
                        respected = False
                        break
                    j += 1
                if respected is None:      # ran off the end of history — indeterminate, drop
                    break
                episodes.append((respected, undercut, j - i + 1))
                above_run = 0
                i = j + 1
                continue
            above_run = above_run + 1 if closes[i] > m else 0
            i += 1
        if len(episodes) >= _MIN_EPISODES:
            rate = sum(1 for e in episodes if e[0]) / len(episodes)
            respect_rates[name] = round(rate, 3)
            episode_stats[name] = episodes

    if not respect_rates:
        return None
    for name, kind, window in _MAS:   # shortest-first order IS the preference order
        rate = respect_rates.get(name)
        if rate is not None and rate >= _RESPECT_BAR:
            eps = episode_stats[name]
            respected_undercuts = sorted(e[1] for e in eps if e[0])
            if not respected_undercuts:
                continue
            k = max(0, min(len(respected_undercuts) - 1,
                           int(round(_UNDERCUT_PCTL * (len(respected_undercuts) - 1)))))
            return {
                "home_ma": name, "home_kind": kind, "home_window": window,
                "undercut_p80": round(respected_undercuts[k], 4),
                "respect_rates": respect_rates,
                "n_episodes": len(eps),
                "pullback_duration_med": statistics.median(e[2] for e in eps),
                "window_anchor_idx": w0,
            }
    return None


def confirmed_swing_lows(bars: list[dict], k: int = 2) -> list[tuple[int, float]]:
    """Fractal pivot lows: low[i] < low[i±1..k]; CONFIRMED at index i+k (the stop may move
    only on the confirmation bar — no lookahead). Returns [(confirm_idx, pivot_low), …]."""
    lows = [float(b["low_price"]) for b in bars]
    out = []
    for i in range(k, len(lows) - k):
        if all(lows[i] < lows[i - d] and lows[i] < lows[i + d] for d in range(1, k + 1)):
            out.append((i + k, lows[i]))
    return out


def annotate_pivot_stops(bars: list[dict], k: int = 2) -> list[float | None]:
    """Per-day ratcheting P1 stop: the max of all swing lows CONFIRMED by that day.
    Ratchets up only (ADR 0031 §3 — never widens). None until the first confirmation."""
    pivots = confirmed_swing_lows(bars, k=k)
    out: list[float | None] = [None] * len(bars)
    stop = None
    pi = 0
    for day in range(len(bars)):
        while pi < len(pivots) and pivots[pi][0] <= day:
            stop = pivots[pi][1] if stop is None else max(stop, pivots[pi][1])
            pi += 1
        out[day] = stop
    return out
