"""EP theme BELONGING — the +10 theme bonus keys on whether the alerting stock BELONGS to a
live theme, decided AT ALERT TIME, not on whether last night's assignment pass happened to
file it in a theme's ticker list.

THE DEFECT THIS FIXES (operator, 2026-09-13, a BUG ruling — not a criteria change):
    "building a theme is to discover strength in a group, if a stock (EP) gets recognized to
    be in the theme, it should get the boost. Otherwise it's kinda backwards, EP will likely
    move the stock into a theme but the EP already happened so there's nothing to boost."
    "this is a bug, this is wrong, we need to fix it, EP gets boost if it belongs to a theme,
    regardless if it's already in a theme or not at the time of EP alert."

Measured over 120 days (n=346 EP alerts, docs/analysis/theme_boost_arrives_late_2026-09-13.md):
only 22 (6%) were on a paying theme's list on the alert day, while 54 joined a paying theme
AFTERWARDS, median 4 days later. The ticker arrays are the record of what the engine filed LAST
NIGHT, so the boost systematically arrived after the event it exists to inform.

BELONGING IS A TWO-STAGE RULE (2026-09-14 — the first cut was correlation alone and it was
WRONG; see "why two stages" below). NO LOOKAHEAD — every input predates the alert date.
  1. LISTED — the ticker is in the ticker list of a theme staged in THEME_BONUS_STAGES (today's
     rule, kept as one way to belong: if it is already listed, it belongs).
  2. SHORTLIST (cheap, $0) — the ticker's market-adjusted daily returns (log return minus
     SPY's) over the BELONGING_LOOKBACK_SESSIONS sessions ending STRICTLY BEFORE the scan date
     correlate at >= BELONGING_SHORTLIST_CORR_BAR with the equal-weight basket of a
     THEME_BONUS_STAGES theme's members (leave-one-out if the ticker is itself a member). The
     top BELONGING_SHORTLIST_THEMES such themes are the SHORTLIST. A shortlist is NOT belonging.
  3. FIT (one bounded Sonnet call) — `theme_engine.judge_theme_fit` asks, of the shortlist
     only, the SAME question the nightly assignment pass asks of the whole board: does this
     stock's business CLEARLY fit one of these themes? Same prompt, same tool, same rules —
     ONE definition of "fits a theme" in the codebase, not a second one that drifts. The
     stock BELONGS iff it is listed OR the fit is CONFIRMED against a paying-stage theme.

WHY TWO STAGES (the 2026-09-13 replay, n=346 alerts): correlation alone against every live
basket admitted 197 of 346 (57%) at 0.35, and the admissions were visibly wrong — D (a
utility) matched *Hydraulic Fracturing & Well Completion Services* at 0.45, BKKT (crypto)
and QBTS (quantum) matched *Satellite Imagery & Geospatial Intelligence*, CMPS (biotech)
matched *Custom AI Silicon*. Operator: *"That is clearly wrong themes for those stocks."*
The 0.35 bar was derived for ONE stock against ONE nominated theme; the BEST of ~20-120
baskets clears 0.35 by coincidence, and raising the bar drops IREN (a case he wants to work)
before it drops BKKT. So correlation became the FILTER and the fit judgement the DECIDER.

FAIL DIRECTION — always list membership (today's behaviour), loudly: thin history / no
baskets / no description / the fit call errors, times out, or the per-tick / per-day budget
is spent -> "cannot judge" -> listed decides. Never a dead scan, never a manufactured bonus.
A scoring path that can hang is worse than one that under-pays: every fit call sits under
BELONGING_FIT_TIMEOUT_S, at most BELONGING_FIT_CALLS_PER_TICK per tick inside a
BELONGING_FIT_TICK_BUDGET_S wall budget, at most BELONGING_FIT_CALLS_PER_DAY per day, and
NO call is made at or after 9:30 ET (the ORB entry window — the #344 posture): post-open
ticks use the day's cached verdicts only. Verdicts are cached per (scan date, ticker,
shortlist) so a name is judged ONCE a day, not once a tick.

STAGE SET: `THEME_BONUS_STAGES` is the ONE named constant the list read and the shortlist
read use. Today = Accelerating + Mainstream, byte-identical to the pre-fix stage filter.
Whether Nascent should also pay is a SEPARATE operator decision — deliberately NOT bundled.
The shadow row carries the Nascent SHORTLIST (correlation only, UNJUDGED — no live call is
spent on an evidence lane); the backtest judges it with real fit calls and reports it as its
own number (docs/analysis/ep_theme_belonging_backtest_2026-09-13.md).

THE TOGGLE (reversion only — operator 2026-09-13: the fix ships ON): `ep_theme_belonging`
(`mi_safeguard_state`, account_mode 'global') / env `EP_THEME_BELONGING_ENABLED`, DEFAULT ON
via db.get_runtime_toggle. OFF restores the pre-fix behaviour byte-for-byte (list membership
alone decides the +10) and spends NO fit calls. Revert with NO redeploy (~60s cache lag):
    INSERT INTO mi_safeguard_state (safeguard, account_mode, state, last_transition_at, updated_at)
    VALUES ('ep_theme_belonging', 'global', 'off', NOW(), NOW())
    ON CONFLICT (safeguard, account_mode) DO UPDATE SET state = EXCLUDED.state, updated_at = NOW();
Nothing in this module writes to mi_safeguard_state.

COST: one mi_daily_closes query for the board's members + SPY (~700 tickers x ~65 sessions)
PER DAY (the basket context is cached on (scan date, board signature)), one small closes query
for the <=SHORTLIST_SIZE graded names per tick, numpy correlations, and ~US$0.007 per fit
call (Sonnet, ~1.2k input + ~250 output tokens) for each unlisted shortlisted name, once per
day. Both DB legs are logged in ms on the "EP scan complete" line; the fit calls and their ms
are logged there too.

SHADOW RECORD (`mi_ep_theme_belonging_shadow`, one row per scored candidate per day, first/last
idiom): what list membership alone and what belonging would each have scored, which one ACTED,
the shortlist (theme / stage / correlation) and the fit verdict behind it (status, theme,
rationale), the unjudged Nascent shortlist, and the bar / lookback / stage set stamped on the
row (the #606 acting-value convention) — so the backtest can be re-read without re-running a
single LLM call. Read by NO grading / entry / sizing / safeguard path — evidence only. Writer
registered in scripts/preflight_db_updates.SHADOW_WRITER_STATEMENTS (#629).

SSoT: docs/setups/magna53_ep.md (change log 2026-09-13 + 2026-09-14).
"""
from __future__ import annotations

import asyncio
import json
import logging
import math
import time
from dataclasses import dataclass, replace
from datetime import date, datetime, timedelta
from typing import Any, Iterable

import numpy as np

logger = logging.getLogger(__name__)

# Module-level for test patchability (the ep_score_shadow / catalyst_tier_shadow convention —
# tests patch `etb.get_pool` / `etb.get_runtime_toggle` / `etb.judge_theme_fit` directly).
from agents.market_intelligence.db import get_pool, get_runtime_toggle  # noqa: E402


async def judge_theme_fit(ticker: str, **kw) -> tuple[str, str | None, str]:
    """THE fit judgement — `theme_engine.judge_theme_fit`, the nightly assignment pass's own
    question asked of a shortlist. Bound here (lazily: theme_engine is heavy and imports back
    into this package) so the scan path has ONE seam to patch and ONE definition to call."""
    from agents.market_intelligence.theme_engine import judge_theme_fit as _judge
    return await _judge(ticker, **kw)


# ── THE CONSTANTS ───────────────────────────────────────────────────────────────────────────
# The ONE stage set the theme bonus pays on (list read AND shortlist read). Pre-fix literal
# was `("Accelerating", "Mainstream")` inline at ep_detector.py:3186 — same values, one name,
# so a future ruling (Nascent?) is a one-line change he can make, never two drifting copies.
THEME_BONUS_STAGES: tuple[str, ...] = ("Accelerating", "Mainstream")
# The stages the SHADOW shortlist also covers (never acting) — the Nascent evidence lane.
BELONGING_SHADOW_STAGES: tuple[str, ...] = THEME_BONUS_STAGES + ("Nascent",)
# The operator-signed co-movement bar (2026-09-13) for the ASSIGNMENT GATE's sector-test
# replacement (PLAN #655: "swap the assignment gate's sector-identity test for a
# market-adjusted co-movement test at bar 0.35"). Derived for ONE stock against ONE nominated
# theme (members 0.5-0.8, a random board stock ~0.05 — docs/analysis/cross_industry_themes_
# 2026-09-13.md). It is kept here as that signed reference; the EP path does NOT read it as a
# belonging verdict (see BELONGING_SHORTLIST_CORR_BAR). Registered in
# scripts/gate_provenance_registry.py (plain assignment on purpose — the provenance checker
# parses `NAME = <literal>`, not an annotated assignment).
BELONGING_CORR_BAR = 0.35
# ⚠ A FILTER, NOT A VERDICT. The shortlist bar: a theme whose basket correlates at or above
# this with the candidate is OFFERED to the fit judgement; nothing is decided here. It is its
# own constant, separate from BELONGING_CORR_BAR, because the two mean different things and
# must be free to move separately: 0.35 was derived for a single nominated pair, and the
# BEST correlation across the whole live board (best-of-~20 paying baskets, up to ~120 over
# a 120-day window) clears 0.35 by coincidence — 57% of alerts did, including a utility in a
# fracking theme. Raising it does not help (IREN drops before BKKT); judging the shortlist
# does. Same value as the signed bar so the shortlist is at least as permissive as anything
# he signed — a real member is never filtered out before the judgement sees it.
BELONGING_SHORTLIST_CORR_BAR = 0.35
# How many themes the shortlist offers the judgement, best correlation first. The prompt's
# own rule ("pick the most specific theme if multiple could fit") does the choosing.
BELONGING_SHORTLIST_THEMES: int = 3
# Window: the 60-session market-adjusted window the 2026-09-13 cross-industry analysis measured
# every reference correlation on (members 0.5-0.8, random ~0.05) — same scale, same window.
BELONGING_LOOKBACK_SESSIONS: int = 60
# Below this many overlapping sessions a correlation is not a reading — "cannot judge".
BELONGING_MIN_OVERLAP_SESSIONS: int = 30
# A basket of 1-2 names is a single stock, not a group; correlation to it is noise.
BELONGING_MIN_BASKET_MEMBERS: int = 3
MARKET_TICKER = "SPY"
BELONGING_TOGGLE: tuple[str, str] = ("ep_theme_belonging", "EP_THEME_BELONGING_ENABLED")
BELONGING_DEFAULT_ON: bool = True
# 60 sessions ~ 87 calendar days; margin for holidays and a thin first week.
_CALENDAR_DAYS_FOR_LOOKBACK: int = 100
# ── The fit call's bounds (all named — a scoring path that can hang is worse than one that
# under-pays). Sized from the replay: ~1-2 unlisted shortlisted ALERTS per scan day, but the
# graded shortlist (<=SHORTLIST_SIZE names, most sub-bar) can carry more; at ~US$0.007 a call
# the day cap is ~US$0.30 worst case.
BELONGING_FIT_CALLS_PER_TICK: int = 3
BELONGING_FIT_CALLS_PER_DAY: int = 40
BELONGING_FIT_TIMEOUT_S: float = 15.0
BELONGING_FIT_TICK_BUDGET_S: float = 30.0
# The FMP profile description is a PR paragraph; the nightly's one-liner is preferred and this
# cap (the catalyst classifier's own) bounds the fallback.
_PROFILE_DESCRIPTION_CHARS: int = 300

# fit_status vocabulary (stamped on the shadow row; `fit` / `fit_unjudged` in `reason`):
FIT_LISTED = "listed"              # no judgement needed — already on a paying list
FIT_NOT_SHORTLISTED = "not_shortlisted"   # no paying basket cleared the shortlist bar
FIT_PENDING = "pending"            # shortlisted, judgement not yet asked (stage 1 output)
FIT_CONFIRMED = "confirmed"        # the judgement named a shortlisted theme -> BELONGS
FIT_REJECTED = "rejected"          # the judgement found no fit -> does not belong
FIT_FAILED = "failed"              # the call returned no verdict (truncated / silent stop)
FIT_TIMEOUT = "timeout"
FIT_ERROR = "error"
FIT_BUDGET = "budget"              # per-tick / per-day cap or wall budget spent
FIT_OFF = "off"                    # toggle reverted — no call spent
FIT_WINDOW = "window"              # at/after 9:30 ET with no cached verdict — no call spent
FIT_NO_DESCRIPTION = "no_description"
_UNJUDGED = frozenset({FIT_PENDING, FIT_FAILED, FIT_TIMEOUT, FIT_ERROR, FIT_BUDGET, FIT_OFF,
                       FIT_WINDOW, FIT_NO_DESCRIPTION})


# ── Data shapes ─────────────────────────────────────────────────────────────────────────────
@dataclass(frozen=True)
class BelongingRead:
    """One candidate's belonging verdict at one scan date. `belongs_paying` is what ACTS when the
    toggle is on (listed OR fit CONFIRMED against a THEME_BONUS_STAGES theme); everything else
    is the evidence behind it. `shortlist` / `nascent_shortlist` are (theme, stage, corr)
    tuples, best correlation first; the Nascent one is never judged live."""
    ticker: str
    listed: bool
    best_theme: str | None
    best_stage: str | None
    best_corr: float | None
    n_sessions: int
    basket_n: int
    shortlist: tuple[tuple[str, str, float], ...]
    nascent_shortlist: tuple[tuple[str, str, float], ...]
    fit_status: str
    fit_theme: str | None
    fit_stage: str | None
    fit_rationale: str | None
    belongs_paying: bool
    reason: str  # listed | fit | shortlisted_rejected | fit_unjudged | below_bar | no_history | no_baskets

    @property
    def shortlisted(self) -> bool:
        return bool(self.shortlist)


@dataclass
class ThemeBasket:
    name: str
    stage: str
    members: tuple[str, ...]      # members WITH usable price history, in matrix row order
    matrix: np.ndarray            # (n_members, n_sessions) excess log returns, NaN where missing


@dataclass
class BasketContext:
    before_date: date
    close_sessions: list[date]    # ascending, ALL strictly < before_date; N+1 closes -> N returns
    market_returns: np.ndarray    # SPY log returns, aligned to close_sessions[1:]
    excess: dict[str, np.ndarray]  # per ticker, aligned to close_sessions[1:]
    baskets: list[ThemeBasket]
    listed_paying: set[str]
    themes_by_name: dict[str, dict]   # the BELONGING_SHADOW_STAGES themes, for the fit prompt
    prep_ms: float
    n_closes_rows: int
    cached: bool = False

    @property
    def sessions(self) -> list[date]:
        """The N RETURN sessions."""
        return self.close_sessions[1:]


class FitBudget:
    """One scan tick's fit-call ledger: calls made, wall-clock spent, and the shared per-day
    counter. `allow()` is the single gate every call goes through."""
    def __init__(self, *, per_tick: int = BELONGING_FIT_CALLS_PER_TICK,
                 per_day: int = BELONGING_FIT_CALLS_PER_DAY,
                 tick_budget_s: float = BELONGING_FIT_TICK_BUDGET_S) -> None:
        self.per_tick, self.per_day, self.tick_budget_s = per_tick, per_day, tick_budget_s
        self.calls = 0
        self.seconds = 0.0
        self.confirmed = 0
        self.rejected = 0
        self.unjudged = 0

    def allow(self, scan_date: date) -> bool:
        return (self.calls < self.per_tick and self.seconds < self.tick_budget_s
                and _day_calls(scan_date) < self.per_day)

    def charge(self, seconds: float, scan_date: date) -> None:
        self.calls += 1
        self.seconds += seconds
        _fit_day["calls"] = _day_calls(scan_date) + 1


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


def _usable(vec: np.ndarray, min_overlap: int) -> bool:
    return int(np.isfinite(vec).sum()) >= min_overlap


def build_baskets(themes: Iterable[dict], excess: dict[str, np.ndarray],
                  stages: tuple[str, ...] = BELONGING_SHADOW_STAGES,
                  min_members: int = BELONGING_MIN_BASKET_MEMBERS,
                  min_overlap: int = BELONGING_MIN_OVERLAP_SESSIONS) -> list[ThemeBasket]:
    """One basket per theme in `stages` with >= min_members members that have usable history.
    Retired themes never reach here (get_active_themes drops them); a stage outside `stages`
    is skipped, so the acting read and the shadow read share one construction."""
    baskets: list[ThemeBasket] = []
    for th in themes:
        stage = (th.get("stage") or "").strip()
        if stage not in stages:
            continue
        members = tuple(sorted({(t or "").upper() for t in (th.get("tickers") or []) if t}))
        rows = [t for t in members if t in excess and _usable(excess[t], min_overlap)]
        if len(rows) < min_members:
            continue
        baskets.append(ThemeBasket(
            name=th.get("name") or "", stage=stage, members=tuple(rows),
            matrix=np.vstack([excess[t] for t in rows]),
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
    sub = basket.matrix[keep]
    finite = np.isfinite(sub)
    counts = finite.sum(axis=0)
    with np.errstate(invalid="ignore"):
        basket_mean = np.where(counts >= min_members,
                               np.nansum(np.where(finite, sub, 0.0), axis=0) / np.maximum(counts, 1),
                               np.nan)
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


def score_belonging(ticker: str, candidate: np.ndarray | None, baskets: list[ThemeBasket],
                    listed_paying: set[str], *, bar: float = BELONGING_SHORTLIST_CORR_BAR,
                    paying_stages: tuple[str, ...] = THEME_BONUS_STAGES,
                    top_k: int = BELONGING_SHORTLIST_THEMES) -> BelongingRead:
    """STAGE 1 — the belonging read for ONE candidate against every basket: listed, or a
    SHORTLIST of the top-k paying-stage baskets correlating at >= `bar` (plus the Nascent
    shortlist, evidence only). A shortlisted, unlisted name comes back `fit_status=pending`
    and `belongs_paying=False` — nothing belongs on correlation alone; `resolve_fit` decides."""
    t = (ticker or "").upper()
    listed = t in listed_paying
    paying: list[tuple[float, ThemeBasket, int, int]] = []
    nascent: list[tuple[float, ThemeBasket]] = []
    n_seen = 0
    if candidate is not None and baskets:
        for bk in baskets:
            corr, n, used = correlate(candidate, bk, exclude=t)
            if corr is None:
                continue
            n_seen += 1
            if bk.stage in paying_stages:
                paying.append((corr, bk, n, used))
            elif bk.stage == "Nascent":
                nascent.append((corr, bk))
    paying.sort(key=lambda x: -x[0])
    nascent.sort(key=lambda x: -x[0])
    best = paying[0] if paying else None
    shortlist = tuple((bk.name, bk.stage, round(c, 4)) for c, bk, _, _ in paying[:top_k] if c >= bar)
    nas_shortlist = tuple((bk.name, bk.stage, round(c, 4)) for c, bk in nascent[:top_k] if c >= bar)
    if listed:
        fit_status, reason = FIT_LISTED, "listed"
    elif shortlist:
        fit_status, reason = FIT_PENDING, "fit_unjudged"
    elif not baskets:
        # THE BOARD is the reason, and it outranks the ticker's own history: with no basket to
        # compare against, belonging is unjudgeable no matter how much price data this ticker
        # has. Ordering this after the `candidate is None` check reported `no_history` on an
        # empty board — blaming missing price data for what is actually an empty theme board,
        # which would send anyone reading the shadow rows to the wrong place.
        fit_status, reason = FIT_NOT_SHORTLISTED, "no_baskets"
    elif candidate is None or n_seen == 0:
        fit_status, reason = FIT_NOT_SHORTLISTED, "no_history"
    else:
        fit_status, reason = FIT_NOT_SHORTLISTED, "below_bar"
    return BelongingRead(
        ticker=t, listed=listed,
        best_theme=best[1].name if best else None,
        best_stage=best[1].stage if best else None,
        best_corr=round(best[0], 4) if best else None,
        n_sessions=best[2] if best else 0,
        basket_n=best[3] if best else 0,
        shortlist=shortlist, nascent_shortlist=nas_shortlist,
        fit_status=fit_status, fit_theme=None, fit_stage=None, fit_rationale=None,
        belongs_paying=bool(listed),
        reason=reason,
    )


def with_fit(read: BelongingRead, status: str, theme: str | None = None,
             stage: str | None = None, rationale: str | None = None) -> BelongingRead:
    """STAGE 2's result applied to a stage-1 read: the ONE place `belongs_paying` and `reason`
    are derived from a fit status. Confirmed -> belongs (`fit`); rejected -> not
    (`shortlisted_rejected`); anything unjudged -> listed decides (`fit_unjudged`)."""
    if read.listed:
        return read
    if status == FIT_CONFIRMED:
        return replace(read, fit_status=status, fit_theme=theme, fit_stage=stage,
                       fit_rationale=rationale, belongs_paying=True, reason="fit")
    if status == FIT_REJECTED:
        return replace(read, fit_status=status, fit_theme=None, fit_stage=None,
                       fit_rationale=rationale, belongs_paying=False, reason="shortlisted_rejected")
    if status not in _UNJUDGED:
        raise ValueError(f"unknown fit status {status!r}")
    return replace(read, fit_status=status, fit_theme=None, fit_stage=None,
                   fit_rationale=rationale, belongs_paying=False, reason="fit_unjudged")


def resolve_theme_bonus_input(listed: bool, read: BelongingRead | None, live: bool) -> bool:
    """THE seam `_score_ep`'s `in_active_theme` argument goes through. Toggle OFF -> list
    membership, byte-identical to the pre-fix behaviour. Toggle ON -> the belonging verdict
    when one exists for this ticker; a missing read (no history, setup failure) falls back to
    list membership — a fix that cannot judge changes nothing."""
    if live and read is not None:
        # UNION, never replacement. Being on the list IS one way to belong, and the operator's
        # instruction was to ADD a second way — *"EP gets boost if it belongs to a theme,
        # regardless if it's already in a theme or not at the time of EP alert"* (2026-09-13).
        # Returning the correlation verdict alone would STRIP the bonus from a listed stock whose
        # 60-session correlation happens to sit under the bar — a live-money REGRESSION dressed as
        # a fix, and the opposite of what was asked for. Caught by this module's own test
        # (`...off_is_list_membership_on_is_the_verdict`, "listed is listed") before deploy.
        return bool(listed) or bool(read.belongs_paying)
    return bool(listed)


def listed_paying_set(themes: Iterable[dict],
                      stages: tuple[str, ...] = THEME_BONUS_STAGES) -> set[str]:
    """The pre-fix rule, as a function: the union of ticker lists of themes in `stages`."""
    out: set[str] = set()
    for th in themes:
        if (th.get("stage") or "").strip() in stages:
            out.update((t or "").upper() for t in (th.get("tickers") or []) if t)
    return out


def _board_signature(themes: Iterable[dict], stages: tuple[str, ...]) -> tuple:
    return tuple(sorted(
        ((th.get("name") or ""), (th.get("stage") or "").strip(),
         tuple(sorted((t or "").upper() for t in (th.get("tickers") or []) if t)))
        for th in themes if (th.get("stage") or "").strip() in stages))


def candidate_description(ticker: str, profile: dict | None) -> tuple[str, str | None]:
    """(description, sector) for the fit prompt — the nightly's own one-liner (universe
    TICKER_DESC, DB overrides applied at boot) first, the FMP profile's paragraph (capped)
    when the universe has none; sector from the profile. Empty description -> the judgement
    refuses (the nightly refuses to cluster blind too)."""
    from agents.market_intelligence.universe import TICKER_DESC
    t = (ticker or "").upper()
    p = profile or {}
    desc = (TICKER_DESC.get(t) or "").strip()
    if not desc:
        desc = str(p.get("description") or "").strip()[:_PROFILE_DESCRIPTION_CHARS]
    sector = (p.get("sector") or None)
    return desc, sector


# ── I/O ─────────────────────────────────────────────────────────────────────────────────────
_CLOSES_SQL = """
    SELECT ticker, trade_date, close FROM mi_daily_closes
    WHERE ticker = ANY($1::text[]) AND trade_date >= $2::date AND trade_date < $3::date
      AND close IS NOT NULL AND close > 0
"""


async def fetch_closes(tickers: Iterable[str], start_date: date,
                       end_exclusive: date) -> tuple[dict[str, dict[date, float]], int]:
    """ONE query: closes for `tickers` on [start_date, end_exclusive). `end_exclusive` is the
    scan date — the window ends STRICTLY before it (no lookahead). Returns ({ticker: {date:
    close}}, rows)."""
    syms = sorted({(t or "").upper() for t in tickers if t})
    if not syms:
        return {}, 0
    pool = await get_pool()
    async with pool.acquire() as conn:
        rows = await conn.fetch(_CLOSES_SQL, syms, start_date, end_exclusive)
    out: dict[str, dict[date, float]] = {}
    for r in rows:
        out.setdefault(r["ticker"], {})[r["trade_date"]] = float(r["close"])
    return out, len(rows)


_ctx_cache: dict[str, Any] = {"key": None, "ctx": None}
# Fit verdicts for the day: (scan_date, ticker, shortlist names) -> (status, theme, stage,
# rationale). Only CONFIRMED / REJECTED are cached — a failure is retried next tick within
# the budget, never remembered as a verdict.
_fit_cache: dict[tuple, tuple[str, str | None, str | None, str | None]] = {}
_fit_day: dict[str, Any] = {"date": None, "calls": 0}


def _day_calls(scan_date: date) -> int:
    if _fit_day.get("date") != scan_date:
        _fit_day["date"], _fit_day["calls"] = scan_date, 0
        _fit_cache.clear()
    return int(_fit_day["calls"])


def _reset_cache() -> None:
    _ctx_cache["key"] = None
    _ctx_cache["ctx"] = None
    _fit_cache.clear()
    _fit_day["date"], _fit_day["calls"] = None, 0


async def prepare_basket_context(themes: list[dict], before_date: date,
                                 lookback_sessions: int = BELONGING_LOOKBACK_SESSIONS) -> BasketContext:
    """Once per scan DAY (cached on the board signature): fetch the members' + SPY's closes
    strictly before `before_date`, build the market-adjusted return matrix and one basket per
    BELONGING_SHADOW_STAGES theme. Raises on I/O failure — the caller degrades to list
    membership, loudly."""
    key = (before_date, _board_signature(themes, BELONGING_SHADOW_STAGES))
    cached = _ctx_cache.get("ctx")
    if cached is not None and _ctx_cache.get("key") == key:
        cached.cached = True
        return cached
    t0 = time.monotonic()
    members: set[str] = set()
    themes_by_name: dict[str, dict] = {}
    for th in themes:
        if (th.get("stage") or "").strip() in BELONGING_SHADOW_STAGES:
            members.update((t or "").upper() for t in (th.get("tickers") or []) if t)
            themes_by_name[th.get("name") or ""] = th
    listed = listed_paying_set(themes)
    closes: dict[str, dict[date, float]] = {}
    n_rows = 0
    if members:
        closes, n_rows = await fetch_closes(
            members | {MARKET_TICKER},
            before_date - timedelta(days=_CALENDAR_DAYS_FOR_LOOKBACK), before_date)
    close_sessions = session_index(closes.get(MARKET_TICKER, {}), before_date, lookback_sessions)
    market = log_returns(closes.get(MARKET_TICKER, {}), close_sessions)
    excess = excess_returns(closes, close_sessions, market) if len(close_sessions) > 1 else {}
    baskets = build_baskets(themes, excess)
    ctx = BasketContext(
        before_date=before_date, close_sessions=close_sessions, market_returns=market,
        excess=excess, baskets=baskets, listed_paying=listed, themes_by_name=themes_by_name,
        prep_ms=(time.monotonic() - t0) * 1000.0, n_closes_rows=n_rows, cached=False,
    )
    _ctx_cache["key"], _ctx_cache["ctx"] = key, ctx
    return ctx


async def score_candidates(ctx: BasketContext, tickers: Iterable[str]) -> dict[str, BelongingRead]:
    """Per tick, STAGE 1: the belonging read for each graded candidate. Fetches closes only
    for names the basket context does not already hold (members already have vectors), over
    the context's OWN close sessions (all strictly before the scan date). Raises on I/O
    failure — the caller degrades to list membership."""
    syms = sorted({(t or "").upper() for t in tickers if t})
    if not syms:
        return {}
    excess = dict(ctx.excess)
    missing = [t for t in syms if t not in excess]
    if missing and len(ctx.close_sessions) > 1:
        closes, _ = await fetch_closes(missing, ctx.close_sessions[0], ctx.before_date)
        for t, cl in closes.items():
            r = log_returns(cl, ctx.close_sessions)
            if r.shape == ctx.market_returns.shape:
                excess[t] = r - ctx.market_returns
    out: dict[str, BelongingRead] = {}
    for t in syms:
        vec = excess.get(t)
        if vec is not None and not _usable(vec, BELONGING_MIN_OVERLAP_SESSIONS):
            vec = None
        out[t] = score_belonging(t, vec, ctx.baskets, ctx.listed_paying)
    return out


async def resolve_fit(read: BelongingRead, *, ctx: BasketContext, profile: dict | None,
                      budget: FitBudget, live: bool, in_window: bool, scan_date: date,
                      timeout_s: float = BELONGING_FIT_TIMEOUT_S) -> BelongingRead:
    """STAGE 2 for one shortlisted candidate: the day's cached verdict if there is one, else
    ONE bounded fit call — only while the toggle is ON, only before 9:30 ET, only inside the
    budget. Never raises; every failure comes back as an unjudged read (listed decides)."""
    if read.fit_status != FIT_PENDING:
        return read
    key = (scan_date, read.ticker, tuple(n for n, _, _ in read.shortlist))
    _day_calls(scan_date)                      # rolls the day (and the cache) over if needed
    hit = _fit_cache.get(key)
    if hit is not None:
        return with_fit(read, *hit)
    if not live:
        return with_fit(read, FIT_OFF)
    if not in_window:
        budget.unjudged += 1
        return with_fit(read, FIT_WINDOW, rationale="post-open tick, no cached verdict")
    if not budget.allow(scan_date):
        budget.unjudged += 1
        logger.warning(f"EP scan: theme fit budget spent — {read.ticker} unjudged, list membership decides")
        return with_fit(read, FIT_BUDGET)
    description, sector = candidate_description(read.ticker, profile)
    if not description:
        budget.unjudged += 1
        return with_fit(read, FIT_NO_DESCRIPTION)
    themes = [ctx.themes_by_name[n] for n, _, _ in read.shortlist if n in ctx.themes_by_name]
    if not themes:
        budget.unjudged += 1
        return with_fit(read, FIT_ERROR, rationale="shortlisted themes not in context")
    t0 = time.monotonic()
    try:
        status, theme, rationale = await asyncio.wait_for(
            judge_theme_fit(read.ticker, description=description, sector=sector, themes=themes),
            timeout=timeout_s)
    except asyncio.TimeoutError:
        budget.charge(time.monotonic() - t0, scan_date)
        budget.unjudged += 1
        logger.warning(f"EP scan: theme fit for {read.ticker} timed out after {timeout_s:.0f}s — list membership decides")
        return with_fit(read, FIT_TIMEOUT)
    except Exception as e:  # loud-ok: the fit degrades to the pre-fix read, never a dead scan
        budget.charge(time.monotonic() - t0, scan_date)
        budget.unjudged += 1
        logger.warning(f"EP scan: theme fit for {read.ticker} failed ({e}) — list membership decides")
        return with_fit(read, FIT_ERROR, rationale=str(e)[:200])
    budget.charge(time.monotonic() - t0, scan_date)
    if status == FIT_CONFIRMED and theme:
        stage = next((s for n, s, _ in read.shortlist if n == theme), None)
        _fit_cache[key] = (FIT_CONFIRMED, theme, stage, rationale)
        budget.confirmed += 1
        logger.info(f"EP scan: theme fit CONFIRMED {read.ticker} → '{theme}' ({stage}): {rationale}")
        return with_fit(read, FIT_CONFIRMED, theme, stage, rationale)
    if status == FIT_REJECTED:
        _fit_cache[key] = (FIT_REJECTED, None, None, rationale)
        budget.rejected += 1
        logger.info(f"EP scan: theme fit rejected {read.ticker} (shortlist "
                    f"{[n for n, _, _ in read.shortlist]}): {rationale}")
        return with_fit(read, FIT_REJECTED, rationale=rationale)
    budget.unjudged += 1
    logger.warning(f"EP scan: theme fit for {read.ticker} returned no verdict ({rationale}) — list membership decides")
    return with_fit(read, FIT_FAILED, rationale=rationale)


async def read_belonging_toggle() -> bool:
    """The reversion toggle (default ON). DB row > env > default; any DB error -> env/default
    (fail-open to the fix — the row is the operator's revert lever, not a liveness check)."""
    return bool(await get_runtime_toggle(*BELONGING_TOGGLE, default=BELONGING_DEFAULT_ON))


# ── The shadow record ───────────────────────────────────────────────────────────────────────
def _shortlist_json(items: tuple[tuple[str, str, float], ...]) -> str | None:
    return json.dumps([{"theme": n, "stage": s, "corr": c} for n, s, c in items]) if items else None


def build_belonging_shadow_row(read: BelongingRead | None, *, ticker: str, listed: bool,
                               acting_in_theme: bool, ep_score_acting: float,
                               ep_score_listed_only: float, ep_score_with_belonging: float,
                               ep_bar: float, toggle_on: bool) -> dict[str, Any]:
    """The recorder's input, built from the REAL BelongingRead the scan resolved (never a
    hand-written dict — the #649 lesson: the producer's shape is the contract). `crossed_bar`
    = the two scores land on different sides of the acting bar, i.e. the fix would move the
    HIGH decision for this name today."""
    r = read
    return {
        "ticker": (ticker or "").upper(),
        "listed": bool(listed if r is None else r.listed),
        "best_theme": r.best_theme if r else None,
        "best_stage": r.best_stage if r else None,
        "best_corr": r.best_corr if r else None,
        "n_sessions": int(r.n_sessions) if r else 0,
        "basket_n": int(r.basket_n) if r else 0,
        "shortlist": _shortlist_json(r.shortlist) if r else None,
        "nascent_shortlist": _shortlist_json(r.nascent_shortlist) if r else None,
        "fit_status": r.fit_status if r else "no_read",
        "fit_theme": r.fit_theme if r else None,
        "fit_stage": r.fit_stage if r else None,
        "fit_rationale": (r.fit_rationale or None) if r else None,
        "belongs_paying": bool(r.belongs_paying) if r else bool(listed),
        "reason": r.reason if r else "no_read",
        "acting_in_theme": bool(acting_in_theme),
        "ep_score_acting": float(ep_score_acting),
        "ep_score_listed_only": float(ep_score_listed_only),
        "ep_score_with_belonging": float(ep_score_with_belonging),
        "ep_bar": float(ep_bar),
        "crossed_bar": bool((ep_score_listed_only >= ep_bar) != (ep_score_with_belonging >= ep_bar)),
        "toggle_on": bool(toggle_on),
        "shortlist_bar": float(BELONGING_SHORTLIST_CORR_BAR),
        "lookback_sessions": int(BELONGING_LOOKBACK_SESSIONS),
        "stage_set": "+".join(THEME_BONUS_STAGES),
    }


# Explicit casts on every parameter that is re-used or nullable — the #606 type-deduction
# class (a bare $n in two typed contexts) is exactly what SHADOW_WRITER_STATEMENTS exists to
# catch at deploy, and casts keep the prepare unambiguous.
EP_THEME_BELONGING_SHADOW_UPSERT_SQL = """
    INSERT INTO mi_ep_theme_belonging_shadow (
        scan_date, ticker, first_seen_et, last_seen_et,
        listed, best_theme, best_stage, best_corr, n_sessions, basket_n,
        shortlist, nascent_shortlist, fit_status, fit_theme, fit_stage, fit_rationale,
        belongs_paying, reason, acting_in_theme,
        ep_score_acting_first, ep_score_acting_last,
        ep_score_listed_only_first, ep_score_listed_only_last,
        ep_score_with_belonging_first, ep_score_with_belonging_last,
        ep_bar, crossed_bar, toggle_on, shortlist_bar, lookback_sessions, stage_set
    ) VALUES (
        $1::date, $2::text, $3::timestamptz, $3::timestamptz,
        $4::boolean, $5::text, $6::text, $7::double precision, $8::int, $9::int,
        $10::text, $11::text, $12::text, $13::text, $14::text, $15::text,
        $16::boolean, $17::text, $18::boolean,
        $19::double precision, $19::double precision,
        $20::double precision, $20::double precision,
        $21::double precision, $21::double precision,
        $22::double precision, $23::boolean, $24::boolean, $25::double precision, $26::int, $27::text
    )
    ON CONFLICT (scan_date, ticker) DO UPDATE SET
        last_seen_et                  = EXCLUDED.last_seen_et,
        listed                        = EXCLUDED.listed,
        best_theme                    = EXCLUDED.best_theme,
        best_stage                    = EXCLUDED.best_stage,
        best_corr                     = EXCLUDED.best_corr,
        n_sessions                    = EXCLUDED.n_sessions,
        basket_n                      = EXCLUDED.basket_n,
        shortlist                     = EXCLUDED.shortlist,
        nascent_shortlist             = EXCLUDED.nascent_shortlist,
        fit_status                    = EXCLUDED.fit_status,
        fit_theme                     = EXCLUDED.fit_theme,
        fit_stage                     = EXCLUDED.fit_stage,
        fit_rationale                 = EXCLUDED.fit_rationale,
        belongs_paying                = EXCLUDED.belongs_paying,
        reason                        = EXCLUDED.reason,
        acting_in_theme               = EXCLUDED.acting_in_theme,
        ep_score_acting_last          = EXCLUDED.ep_score_acting_last,
        ep_score_listed_only_last     = EXCLUDED.ep_score_listed_only_last,
        ep_score_with_belonging_last  = EXCLUDED.ep_score_with_belonging_last,
        ep_bar                        = EXCLUDED.ep_bar,
        crossed_bar                   = EXCLUDED.crossed_bar,
        toggle_on                     = EXCLUDED.toggle_on,
        shortlist_bar                 = EXCLUDED.shortlist_bar,
        lookback_sessions             = EXCLUDED.lookback_sessions,
        stage_set                     = EXCLUDED.stage_set
"""

# The positional contract between build_belonging_shadow_row and the SQL above — ONE place.
SHADOW_ROW_PARAM_KEYS: tuple[str, ...] = (
    "listed", "best_theme", "best_stage", "best_corr", "n_sessions", "basket_n",
    "shortlist", "nascent_shortlist", "fit_status", "fit_theme", "fit_stage", "fit_rationale",
    "belongs_paying", "reason", "acting_in_theme",
    "ep_score_acting", "ep_score_listed_only", "ep_score_with_belonging",
    "ep_bar", "crossed_bar", "toggle_on", "shortlist_bar", "lookback_sessions", "stage_set",
)


def shadow_row_params(row: dict[str, Any], scan_date: date, now_et: datetime) -> tuple:
    """The exact positional tuple the upsert binds — $1 scan_date, $2 ticker, $3 tick time,
    then SHADOW_ROW_PARAM_KEYS in order."""
    return (scan_date, row["ticker"], now_et, *(row.get(k) for k in SHADOW_ROW_PARAM_KEYS))


async def record_ep_theme_belonging_shadow(rows: list[dict[str, Any]], scan_date: date,
                                           now_et: datetime) -> int:
    """Batch writer — fire-and-forget after the scan loop (the ep_score_shadow contract: never
    raises, never blocks the scan). Returns rows written (0 on any failure)."""
    if not rows:
        return 0
    try:
        pool = await get_pool()
        written = 0
        async with pool.acquire() as conn:
            for row in rows:
                try:
                    await conn.execute(EP_THEME_BELONGING_SHADOW_UPSERT_SQL,
                                       *shadow_row_params(row, scan_date, now_et))
                    written += 1
                except Exception as e:  # loud-ok: one bad row must not drop the batch
                    logger.warning(f"theme belonging shadow: row failed for {row.get('ticker')}: {e}")
        return written
    except Exception as e:  # loud-ok: telemetry never jeopardizes the scan
        logger.warning(f"theme belonging shadow: batch write failed — {e}")
        return 0
