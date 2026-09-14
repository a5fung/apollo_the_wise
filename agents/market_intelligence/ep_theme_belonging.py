"""EP theme BELONGING — the +10 theme bonus keys on whether the alerting stock BELONGS to a
live theme, decided AT ALERT TIME from the tape, not on whether last night's assignment pass
happened to file it in a theme's ticker list.

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

BELONGING, as decided here (NO LOOKAHEAD — every input predates the alert date):
  1. LISTED — the ticker is in the ticker list of a theme staged in THEME_BONUS_STAGES (today's
     rule, kept as one way to belong: if it is already listed, it belongs).
  2. CO-MOVES — the ticker's market-adjusted daily returns (log return minus SPY's log return)
     over the BELONGING_LOOKBACK_SESSIONS sessions ending STRICTLY BEFORE the scan date
     correlate at >= BELONGING_CORR_BAR with the equal-weight basket of a THEME_BONUS_STAGES
     theme's members (leave-one-out if the ticker is itself a member). Bar 0.35 is the
     operator-signed bar for the assignment gate's sector-test replacement (2026-09-13 —
     reference scale: real theme members sit 0.5-0.8, a random board stock ~0.05;
     docs/analysis/cross_industry_themes_2026-09-13.md). Whether 0.35 TRANSFERS to this use (a
     max over ~20 baskets, not one nominated pair) is what the backtest's null-control curve
     answers — docs/analysis/ep_theme_belonging_backtest_2026-09-13.md.
  Insufficient history / no baskets / any error -> "cannot judge" -> list membership decides
  (today's behaviour), never a dead scan and never a manufactured belonging.

STAGE SET: `THEME_BONUS_STAGES` is the ONE named constant both the list read and the co-movement
read use. Today = Accelerating + Mainstream, byte-identical to the pre-fix stage filter. Whether
Nascent should also pay is a SEPARATE operator decision (measured separately, +32 alerts on the
list read alone) — deliberately NOT bundled here; the shadow row records the incl-Nascent read
so that decision has live evidence.

THE TOGGLE (reversion only — operator 2026-09-13: the fix ships ON): `ep_theme_belonging`
(`mi_safeguard_state`, account_mode 'global') / env `EP_THEME_BELONGING_ENABLED`, DEFAULT ON
via db.get_runtime_toggle. OFF restores the pre-fix behaviour byte-for-byte (list membership
alone decides the +10). Revert with NO redeploy (~60s cache lag):
    INSERT INTO mi_safeguard_state (safeguard, account_mode, state, last_transition_at, updated_at)
    VALUES ('ep_theme_belonging', 'global', 'off', NOW(), NOW())
    ON CONFLICT (safeguard, account_mode) DO UPDATE SET state = EXCLUDED.state, updated_at = NOW();
Nothing in this module writes to mi_safeguard_state.

COST: one mi_daily_closes query for the board's members + SPY (~700 tickers x ~65 sessions)
PER DAY — the basket context is cached on (scan date, board signature) because neither the
board nor prior closes move intraday — plus one small query for the <=SHORTLIST_SIZE graded
names per tick. Both are logged in ms on the "EP scan:" summary line so the real cost is
readable in prod.

SHADOW RECORD (`mi_ep_theme_belonging_shadow`, one row per scored candidate per day, first/last
idiom): what list membership alone and what belonging would each have scored, which one ACTED,
the co-movement read behind it (best theme, correlation, overlap), the incl-Nascent read, and
the bar/lookback/stage set stamped on the row (the #606 acting-value convention). Read by NO
grading / entry / sizing / safeguard path — evidence only. Writer registered in
scripts/preflight_db_updates.SHADOW_WRITER_STATEMENTS (#629: a silent recorder is where a type
bug hides longest).

SSoT: docs/setups/magna53_ep.md (change log 2026-09-13).
"""
from __future__ import annotations

import logging
import math
import time
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from typing import Any, Iterable

import numpy as np

logger = logging.getLogger(__name__)

# Module-level for test patchability (the ep_score_shadow / catalyst_tier_shadow convention —
# tests patch `etb.get_pool` / `etb.get_runtime_toggle` directly).
from agents.market_intelligence.db import get_pool, get_runtime_toggle  # noqa: E402

# ── THE CONSTANTS ───────────────────────────────────────────────────────────────────────────
# The ONE stage set the theme bonus pays on (list read AND co-movement read). Pre-fix literal
# was `("Accelerating", "Mainstream")` inline at ep_detector.py:3186 — same values, one name,
# so a future ruling (Nascent?) is a one-line change he can make, never two drifting copies.
THEME_BONUS_STAGES: tuple[str, ...] = ("Accelerating", "Mainstream")
# The stages the SHADOW read also scores (never acting) — the incl-Nascent evidence lane.
BELONGING_SHADOW_STAGES: tuple[str, ...] = THEME_BONUS_STAGES + ("Nascent",)
# Co-movement bar — operator-signed 2026-09-13 for the sector-test replacement (see module
# docstring); registered in scripts/gate_provenance_registry.py (plain assignment on purpose —
# the provenance checker parses `NAME = <literal>`, not an annotated assignment).
BELONGING_CORR_BAR = 0.35
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


# ── Data shapes ─────────────────────────────────────────────────────────────────────────────
@dataclass(frozen=True)
class BelongingRead:
    """One candidate's belonging verdict at one scan date. `belongs_paying` is what ACTS when the
    toggle is on (listed OR co-moves with a THEME_BONUS_STAGES basket); everything else is the
    evidence behind it and the incl-Nascent shadow read."""
    ticker: str
    listed: bool
    best_theme: str | None
    best_stage: str | None
    best_corr: float | None
    n_sessions: int
    basket_n: int
    belongs_paying: bool
    belongs_incl_nascent: bool
    best_nascent_theme: str | None
    best_nascent_corr: float | None
    reason: str  # listed | comoves | below_bar | no_history | no_baskets


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
    prep_ms: float
    n_closes_rows: int
    cached: bool = False

    @property
    def sessions(self) -> list[date]:
        """The N RETURN sessions."""
        return self.close_sessions[1:]


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
                    listed_paying: set[str], *, bar: float = BELONGING_CORR_BAR,
                    paying_stages: tuple[str, ...] = THEME_BONUS_STAGES) -> BelongingRead:
    """The belonging verdict for ONE candidate against every basket. `belongs_paying` is
    listed OR (best correlation among `paying_stages` baskets >= bar). The Nascent read is
    carried separately and never acts."""
    t = (ticker or "").upper()
    listed = t in listed_paying
    best: tuple[float, ThemeBasket, int, int] | None = None
    best_nas: tuple[float, ThemeBasket] | None = None
    n_seen = 0
    if candidate is not None and baskets:
        for bk in baskets:
            corr, n, used = correlate(candidate, bk, exclude=t)
            if corr is None:
                continue
            n_seen += 1
            if bk.stage in paying_stages:
                if best is None or corr > best[0]:
                    best = (corr, bk, n, used)
            elif bk.stage == "Nascent":
                if best_nas is None or corr > best_nas[0]:
                    best_nas = (corr, bk)
    comoves = best is not None and best[0] >= bar
    nas_comoves = best_nas is not None and best_nas[0] >= bar
    if listed:
        reason = "listed"
    elif comoves:
        reason = "comoves"
    elif not baskets:
        # THE BOARD is the reason, and it outranks the ticker's own history: with no basket to
        # compare against, belonging is unjudgeable no matter how much price data this ticker
        # has. Ordering this after the `candidate is None` check reported `no_history` on an
        # empty board — blaming missing price data for what is actually an empty theme board,
        # which would send anyone reading the shadow rows to the wrong place.
        reason = "no_baskets"
    elif candidate is None or n_seen == 0:
        reason = "no_history"
    else:
        reason = "below_bar"
    return BelongingRead(
        ticker=t, listed=listed,
        best_theme=best[1].name if best else None,
        best_stage=best[1].stage if best else None,
        best_corr=round(best[0], 4) if best else None,
        n_sessions=best[2] if best else 0,
        basket_n=best[3] if best else 0,
        belongs_paying=bool(listed or comoves),
        belongs_incl_nascent=bool(listed or comoves or nas_comoves),
        best_nascent_theme=best_nas[1].name if best_nas else None,
        best_nascent_corr=round(best_nas[0], 4) if best_nas else None,
        reason=reason,
    )


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


def _reset_cache() -> None:
    _ctx_cache["key"] = None
    _ctx_cache["ctx"] = None


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
    for th in themes:
        if (th.get("stage") or "").strip() in BELONGING_SHADOW_STAGES:
            members.update((t or "").upper() for t in (th.get("tickers") or []) if t)
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
        excess=excess, baskets=baskets, listed_paying=listed,
        prep_ms=(time.monotonic() - t0) * 1000.0, n_closes_rows=n_rows, cached=False,
    )
    _ctx_cache["key"], _ctx_cache["ctx"] = key, ctx
    return ctx


async def score_candidates(ctx: BasketContext, tickers: Iterable[str]) -> dict[str, BelongingRead]:
    """Per tick: the belonging verdict for each graded candidate. Fetches closes only for
    names the basket context does not already hold (members already have vectors), over the
    context's OWN close sessions (all strictly before the scan date). Raises on I/O failure —
    the caller degrades to list membership."""
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


async def read_belonging_toggle() -> bool:
    """The reversion toggle (default ON). DB row > env > default; any DB error -> env/default
    (fail-open to the fix — the row is the operator's revert lever, not a liveness check)."""
    return bool(await get_runtime_toggle(*BELONGING_TOGGLE, default=BELONGING_DEFAULT_ON))


# ── The shadow record ───────────────────────────────────────────────────────────────────────
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
        "belongs_paying": bool(r.belongs_paying) if r else bool(listed),
        "belongs_incl_nascent": bool(r.belongs_incl_nascent) if r else bool(listed),
        "best_nascent_theme": r.best_nascent_theme if r else None,
        "best_nascent_corr": r.best_nascent_corr if r else None,
        "reason": r.reason if r else "no_read",
        "acting_in_theme": bool(acting_in_theme),
        "ep_score_acting": float(ep_score_acting),
        "ep_score_listed_only": float(ep_score_listed_only),
        "ep_score_with_belonging": float(ep_score_with_belonging),
        "ep_bar": float(ep_bar),
        "crossed_bar": bool((ep_score_listed_only >= ep_bar) != (ep_score_with_belonging >= ep_bar)),
        "toggle_on": bool(toggle_on),
        "corr_bar": float(BELONGING_CORR_BAR),
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
        belongs_paying, belongs_incl_nascent, best_nascent_theme, best_nascent_corr, reason,
        acting_in_theme,
        ep_score_acting_first, ep_score_acting_last,
        ep_score_listed_only_first, ep_score_listed_only_last,
        ep_score_with_belonging_first, ep_score_with_belonging_last,
        ep_bar, crossed_bar, toggle_on, corr_bar, lookback_sessions, stage_set
    ) VALUES (
        $1::date, $2::text, $3::timestamptz, $3::timestamptz,
        $4::boolean, $5::text, $6::text, $7::double precision, $8::int, $9::int,
        $10::boolean, $11::boolean, $12::text, $13::double precision, $14::text,
        $15::boolean,
        $16::double precision, $16::double precision,
        $17::double precision, $17::double precision,
        $18::double precision, $18::double precision,
        $19::double precision, $20::boolean, $21::boolean, $22::double precision, $23::int, $24::text
    )
    ON CONFLICT (scan_date, ticker) DO UPDATE SET
        last_seen_et                  = EXCLUDED.last_seen_et,
        listed                        = EXCLUDED.listed,
        best_theme                    = EXCLUDED.best_theme,
        best_stage                    = EXCLUDED.best_stage,
        best_corr                     = EXCLUDED.best_corr,
        n_sessions                    = EXCLUDED.n_sessions,
        basket_n                      = EXCLUDED.basket_n,
        belongs_paying                = EXCLUDED.belongs_paying,
        belongs_incl_nascent          = EXCLUDED.belongs_incl_nascent,
        best_nascent_theme            = EXCLUDED.best_nascent_theme,
        best_nascent_corr             = EXCLUDED.best_nascent_corr,
        reason                        = EXCLUDED.reason,
        acting_in_theme               = EXCLUDED.acting_in_theme,
        ep_score_acting_last          = EXCLUDED.ep_score_acting_last,
        ep_score_listed_only_last     = EXCLUDED.ep_score_listed_only_last,
        ep_score_with_belonging_last  = EXCLUDED.ep_score_with_belonging_last,
        ep_bar                        = EXCLUDED.ep_bar,
        crossed_bar                   = EXCLUDED.crossed_bar,
        toggle_on                     = EXCLUDED.toggle_on,
        corr_bar                      = EXCLUDED.corr_bar,
        lookback_sessions             = EXCLUDED.lookback_sessions,
        stage_set                     = EXCLUDED.stage_set
"""

# The positional contract between build_belonging_shadow_row and the SQL above — ONE place.
SHADOW_ROW_PARAM_KEYS: tuple[str, ...] = (
    "listed", "best_theme", "best_stage", "best_corr", "n_sessions", "basket_n",
    "belongs_paying", "belongs_incl_nascent", "best_nascent_theme", "best_nascent_corr", "reason",
    "acting_in_theme", "ep_score_acting", "ep_score_listed_only", "ep_score_with_belonging",
    "ep_bar", "crossed_bar", "toggle_on", "corr_bar", "lookback_sessions", "stage_set",
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
