"""Market-adjusted co-movement — the ONE definition of "this stock moves with that basket".

SPY-SUBTRACTION, NOT A BETA RESIDUAL. Each ticker's daily log return minus SPY's, over the last
BELONGING_LOOKBACK_SESSIONS sessions STRICTLY BEFORE a date, Pearson-correlated with the
equal-weight mean of a basket's members (leave-one-out when the candidate is itself a member).
`correlation_engine.py` adjusts by a fitted beta and is a DIFFERENT statistic on a separately
calibrated bar; the 0.35 bars both callers use were measured on the subtraction. Do not merge the
two — that is a detection change (THE LINE), not a refactor.

WHO IMPORTS IT (as a peer — neither caller reaches into the other for this maths):
  - `ep_theme_belonging.py` — the EP scan's theme-belonging SHORTLIST (stage 1 of the +10 bonus).
  - `theme_engine.py` — the nightly assignment gate's membership test (`_load_comove_context`,
    `_comove_verdict`, ASSIGN_COMOVE_BAR).
Born inside `ep_theme_belonging.py` with the 2026-09-13 bug fix and moved here 2026-09-18 (#660)
as a PURE MOVE — bodies verbatim, verdicts byte-identical on replay. The `BELONGING_*` constant
names are the EP module's historical names, kept on purpose so every existing reader (ep_detector,
the probes, the shadow-row stamps) binds the SAME object rather than a renamed copy.

The two bars that decide anything live with their callers, not here: `BELONGING_SHORTLIST_CORR_BAR`
/ `BELONGING_CORR_BAR` in `ep_theme_belonging.py`, `ASSIGN_COMOVE_BAR` in `theme_engine.py`. The
closes READ (`fetch_closes`, mi_daily_closes) stays in `ep_theme_belonging.py` too — I/O, not maths.

SSoT: docs/architecture/theme_engine.md (membership test) · docs/setups/magna53_ep.md (belonging).
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import date
from typing import Iterable

import numpy as np

# Window: the 60-session market-adjusted window the 2026-09-13 cross-industry analysis measured
# every reference correlation on (members 0.5-0.8, random ~0.05) — same scale, same window.
BELONGING_LOOKBACK_SESSIONS: int = 60
# Below this many overlapping sessions a correlation is not a reading — "cannot judge".
BELONGING_MIN_OVERLAP_SESSIONS: int = 30
# A basket of 1-2 names is a single stock, not a group; correlation to it is noise.
BELONGING_MIN_BASKET_MEMBERS: int = 3
MARKET_TICKER = "SPY"
# 60 sessions ~ 87 calendar days; margin for holidays and a thin first week. Public (was
# `_CALENDAR_DAYS_FOR_LOOKBACK`): both callers size their closes read with it.
CALENDAR_DAYS_FOR_LOOKBACK: int = 100


@dataclass
class ThemeBasket:
    name: str
    stage: str
    members: tuple[str, ...]      # members WITH usable price history, in matrix row order
    matrix: np.ndarray            # (n_members, n_sessions) excess log returns, NaN where missing
    mean_all: np.ndarray          # the ALL-MEMBERS equal-weight mean, computed once at build
    # `mean_all` exists because the basket mean depends on the BASKET, not on the candidate being
    # scored — and stage 1 runs on every graded candidate on every tick, INSIDE the ORB window
    # (unlike the stage-2 fit call, which is premarket-gated). Recomputing it per candidate was
    # ~20x the necessary work. Only a candidate that is ITSELF a member needs the leave-one-out
    # recompute; everyone else reads this.


# ── Pure math ───────────────────────────────────────────────────────────────────────────────
def session_index(market_closes: dict[date, float], before_date: date,
                  lookback_sessions: int = BELONGING_LOOKBACK_SESSIONS) -> list[date]:
    """The CLOSE sessions the window is built on: the market's own trade dates STRICTLY before
    `before_date`, the last `lookback_sessions + 1` of them (N+1 closes -> N returns). The
    `< before_date` filter is applied HERE too, never trusted to the fetch — the no-lookahead
    guarantee must not depend on a query's WHERE clause alone."""
    dates = sorted(d for d, c in market_closes.items()
                   if d < before_date and c is not None and c > 0)
    return dates[-(lookback_sessions + 1):] if lookback_sessions > 0 else dates


def log_returns(closes: dict[date, float], close_sessions: list[date]) -> np.ndarray:
    """Log returns aligned to close_sessions[1:]; NaN wherever either close is missing/<=0."""
    n = len(close_sessions)
    out = np.full(max(n - 1, 0), np.nan)
    for i in range(1, n):
        c0 = closes.get(close_sessions[i - 1])
        c1 = closes.get(close_sessions[i])
        if c0 and c1 and c0 > 0 and c1 > 0:
            out[i - 1] = math.log(c1 / c0)
    return out


def excess_returns(closes_by_ticker: dict[str, dict[date, float]], close_sessions: list[date],
                   market_returns: np.ndarray) -> dict[str, np.ndarray]:
    """Market-adjusted (SPY-subtracted) log returns per ticker. Subtraction, not a beta
    residual, on purpose: it is the adjustment the 2026-09-13 analysis measured 0.35 on."""
    out: dict[str, np.ndarray] = {}
    for t, closes in closes_by_ticker.items():
        if t == MARKET_TICKER:
            continue
        r = log_returns(closes, close_sessions)
        if r.shape != market_returns.shape:
            continue
        out[t] = r - market_returns
    return out


def usable(vec: np.ndarray, min_overlap: int) -> bool:
    """At least `min_overlap` finite sessions — below that a vector is not a reading. Public
    (was `_usable`): `build_baskets` here and `score_candidates` in the EP module share it."""
    return int(np.isfinite(vec).sum()) >= min_overlap


def _basket_mean(sub: np.ndarray, min_members: int) -> np.ndarray:
    """Equal-weight mean excess return across `sub`'s rows, NaN on any session where fewer than
    `min_members` rows are finite. ONE definition, called from build_baskets (all members) and
    from correlate (leave-one-out) so the cached vector and the recomputed one cannot drift."""
    finite = np.isfinite(sub)
    counts = finite.sum(axis=0)
    with np.errstate(invalid="ignore"):
        return np.where(counts >= min_members,
                        np.nansum(np.where(finite, sub, 0.0), axis=0) / np.maximum(counts, 1),
                        np.nan)


def build_baskets(themes: Iterable[dict], excess: dict[str, np.ndarray],
                  stages: tuple[str, ...],
                  min_members: int = BELONGING_MIN_BASKET_MEMBERS,
                  min_overlap: int = BELONGING_MIN_OVERLAP_SESSIONS) -> list[ThemeBasket]:
    """One basket per theme in `stages` with >= min_members members that have usable history.
    Retired themes never reach here (get_active_themes drops them); a stage outside `stages`
    is skipped, so the acting read and the shadow read share one construction. `stages` has no
    default here — which stages pay is the CALLER's rule (the EP module's wrapper supplies
    BELONGING_SHADOW_STAGES; the nightly engine passes a one-theme sentinel)."""
    baskets: list[ThemeBasket] = []
    for th in themes:
        stage = (th.get("stage") or "").strip()
        if stage not in stages:
            continue
        members = tuple(sorted({(t or "").upper() for t in (th.get("tickers") or []) if t}))
        rows = [t for t in members if t in excess and usable(excess[t], min_overlap)]
        if len(rows) < min_members:
            continue
        matrix = np.vstack([excess[t] for t in rows])
        baskets.append(ThemeBasket(
            name=th.get("name") or "", stage=stage, members=tuple(rows),
            matrix=matrix, mean_all=_basket_mean(matrix, min_members),
        ))
    return baskets


def correlate(candidate: np.ndarray, basket: ThemeBasket, exclude: str | None = None,
              min_members: int = BELONGING_MIN_BASKET_MEMBERS,
              min_overlap: int = BELONGING_MIN_OVERLAP_SESSIONS) -> tuple[float | None, int, int]:
    """Pearson correlation of the candidate's excess returns with the basket's equal-weight
    mean excess return (leave-one-out when `exclude` is a member). A session counts only where
    the candidate is finite AND at least `min_members` members are finite. Returns
    (corr | None, overlap sessions, basket members used)."""
    keep = [i for i, m in enumerate(basket.members) if m != (exclude or "").upper()]
    if len(keep) < min_members:
        return None, 0, len(keep)
    if len(keep) == len(basket.members) and basket.mean_all is not None:
        basket_mean = basket.mean_all          # nothing excluded -> the mean built with the basket
    else:
        basket_mean = _basket_mean(basket.matrix[keep], min_members)
    mask = np.isfinite(candidate) & np.isfinite(basket_mean)
    n = int(mask.sum())
    if n < min_overlap:
        return None, n, len(keep)
    a, b = candidate[mask], basket_mean[mask]
    if a.std() < 1e-12 or b.std() < 1e-12:
        return None, n, len(keep)
    corr = float(np.corrcoef(a, b)[0, 1])
    if not math.isfinite(corr):
        return None, n, len(keep)
    return corr, n, len(keep)
