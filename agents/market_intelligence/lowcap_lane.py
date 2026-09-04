"""#624 (2026-09-04) — MAGNA53 LOW-CAP LANE, SHADOW ONLY: the scan-tick recorder.

THE RULE (P15 — the sentence in docs/setups/magna53_ep.md "Low-cap lane", verbatim):
    A $5+ stock under $500M market cap that gaps 15% or more and whose volume by the 09:31
    tick already ranks in the top 10% of its own trailing history is a lane candidate; every
    other MAGNA53 gate it failed is stamped on its row.

WHY A LANE AND WHY SHADOW (operator rulings 2026-09-04, all four fixed): CHPT 2026-09-03 — a
$134M name that gapped 33%, ran 46% and closed on the highest volume in its history — was
dropped by the $500M market-cap floor before it was ever scored. The candidate rule cell on
the #622/#623 evidence (n=46, +0.527R) is TWO trades (WETO +12.08R, FBRX +10.71R = 94% of the
sum; ex-both n=44 +0.03R), and BOTH thresholds sit just under those two trades' own
coordinates. That is the shape of a tail strategy, not of no edge — but n=46 cannot pin the
tail rate to better than a factor of five, and resolving it is this shadow's ONLY job. It is a
LANE of MAGNA53, not a setup: buy point, stop, target and harvest are MAGNA53's, unchanged;
only the universe differs. Sizing 1.0, its own slot allocation, exit work in parallel (#545).

WHAT THIS MODULE DOES, AND WHERE IT SITS. `run_ep_scan` grades only the top SHORTLIST_SIZE
candidates per tick, and the liquidity-led pre-score sorts small caps LAST — so the lane's
real population has never been seen by any study (every one of the 46 evidence rows reached
the top-20; the full-list population is wider). The hook therefore runs over the FULL
candidate list BEFORE the shortlist cut:
  1. `screen_board` — PURE, no I/O, no mutation: the two free terms (gap >= 15%, volume
     percentile >= 90 against the mi_daily_closes rolling-20-day-mean history the scan already
     fetched for every candidate) plus the $5 universe floor, on every candidate. Evaluated
     only at POST-OPEN ticks ("by the 09:31 tick" is a session reading); the FIRST qualifying
     tick is the record (db: ON CONFLICT DO NOTHING), and its wall-clock is what the walker
     submits from — never a fixed 09:31 (#622: the sign flips at 09:36).
  2. `enrich_and_record` — the survivors only (measured ~0.7 signals/session, max 2/day on the
     evidence; bounded here by MAX_ENRICH_PER_TICK and a per-(ticker, day) dedupe): the cap
     read (yfinance profile — NOT FMP; `collector.get_fmp_profile` is yfinance under the
     name), ADV$/ATR via `check_filters(skip_mcap=True)`, the extension / cooldown /
     shortlist-cap facts off the scan's own maps, one batched Alpaca minute-bar read for the
     real-time volume, one batched Alpaca NBBO read for quoted spread + bid/ask SIZE (the
     operator's fillability requirement — the one thing four studies never measured), and
     `ma_filter.is_likely_ma` (keyword + Polygon headlines, no LLM) as the score-free lane's
     only catalyst check. Then ONE batched insert into mi_lowcap_lane_signals.

⚠ THE ACTING VOLUME READING IS THE DELAYED SNAPSHOT (`acting_volume_source='delayed'`): it is
what nearly all 46 evidence rows used, `mi_ep_scan_log.today_volume` is populated on only 24
of 417 rows, and #490's real-time refresh covers only the scored top-20. The real-time read
is stored ALONGSIDE for comparison; switching which one acts is a later, separate fork.

⚠ THE `_mcap_cache` HAZARD — why the cap is read here and not through `check_filters`.
`backtester.filters._check_market_cap` pins `_mcap_cache[ticker] = None` on ANY yfinance
exception and returns None = PASS. A lane read for a name outside the top-20 that hit a
transient error would leave that name clearing the $500M gate WITHOUT A RETRY if it later
entered the top-20 on another tick — an admission change from a shadow. So the lane calls
`check_filters(..., skip_mcap=True)` (ADV$ + ATR are pure DB reads, no cache) and reads the
cap via `get_fmp_profile` behind a LANE-LOCAL per-day cache. The acting cache is never
written by this module (source-pinned by tests/test_624_lowcap_lane.py).

THE LINE — read this before touching anything here:
  - The hook is SYNCHRONOUS in `run_ep_scan` only long enough to SNAPSHOT the fields it needs
    and detach a task (strong ref in the scan's `_WATCHDOG_BG_TASKS`). The ORB-window tick
    never awaits the lane; the acting candidate dicts are never shared with it (copied).
  - It NEVER mutates `candidates` or any scan map, never sets a key on a candidate, never
    calls `_log_filtered`, never adds a `continue` (test_605 counts both), never feeds
    `_score_ep` / tier / alerts / `insert_ep_alert` / `enqueue_pending_allocation`.
  - ONE write target: mi_lowcap_lane_signals (plus mi_audit_log via `log_audit_event`).
  - Fail-open at BOTH layers: the sync dispatch is wrapped in `run_ep_scan`; the task body
    catches everything, counts it, audits it. A broken lane is a logged warning, never a dead
    scan. `should_run('magna53_lowcap')` (mi_strategies.enabled) is the operator's real switch.
  - SILENT. No Telegram while evidence accrues (the #482/#593/#617 posture).
  - Byte-identity of the acting path with the hook on / off / raising is proven by a real
    `run_ep_scan` run in tests/test_624_lowcap_lane.py — the first test in the repo that
    executes the scan end to end.
"""
from __future__ import annotations

import asyncio
import json
import logging
from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Any, Optional

from agents.market_intelligence import rule_eras
from agents.market_intelligence.backtester.filters import (
    MAX_ATR_PCT,
    MIN_ADV_DOLLAR_VOLUME,
    MIN_MARKET_CAP,
    check_filters,
)
from agents.market_intelligence.broker.skip_reasons import (
    FILTER_ADV_NO_DATA,
    FILTER_ADV_TOO_LOW,
    FILTER_ATR_TOO_HIGH,
)
from agents.market_intelligence.collector import (
    get_alpaca_latest_quotes,
    get_alpaca_minute_cum_volumes,
    get_fmp_profile,
)
from agents.market_intelligence.db import (
    get_lowcap_lane_prior_signal_dates,
    get_lowcap_lane_signal_tickers,
    insert_lowcap_lane_signals,
    log_audit_event,
)
# The live floors, imported never restated (the #595 / gap_near_miss_replay precedent): the
# lane is "the names under the cap floor that clear the two free terms", so its cap ceiling
# IS the live floor, and the $5 universe floor is the scan's own. A second literal would drift
# the moment the operator moves one. `_volume_percentile` is the scan's own ranking primitive.
from agents.market_intelligence.ep_detector import (
    EP_COOLDOWN_DAYS,
    MAX_EXTENSION_PCT,
    MIN_PREMARKET_SHARES,
    MIN_PREV_CLOSE,
    _volume_percentile,
)
from agents.market_intelligence.ep_rubric import SHORTLIST_SIZE
from agents.market_intelligence.ma_filter import is_likely_ma
from agents.market_intelligence.strategies.registry import should_run

logger = logging.getLogger(__name__)

STRATEGY_ID = "magna53_lowcap"
LANE_RULE_VERSION = "lane_v1"
LANE_MIN_GAP_PCT = 15.0             # the evidence cell's gap term (>=15: n=46 +0.53 / ex-top-2 +0.03)
LANE_MIN_VOL_PERCENTILE = 90.0      # "top 10% of its own trailing history" — the >=90 cell
LANE_MAX_MARKET_CAP = MIN_MARKET_CAP  # < the live floor: exactly the names the floor turns away
LANE_MIN_PREV_CLOSE = MIN_PREV_CLOSE  # the $5 universe floor — a candidate already cleared it
MAX_ENRICH_PER_TICK = 6             # bounds the yfinance / Polygon / Alpaca fan-out on a flood tick;
                                    # names beyond it are re-screened next tick (not marked evaluated)
MAX_CAP_RETRIES_PER_DAY = 3         # an unreadable cap is retried on later ticks, then given up for the
                                    # day (a name yfinance simply has no cap for must not cost 36 reads)

# Per-day dedupe of the EXPENSIVE half: a name is enriched once per (ticker, ET day) whether it
# was admitted (row written) or rejected on the cap. Restart-safe via get_lowcap_lane_signal_tickers.
_evaluated_date: Optional[date] = None
_evaluated: set[str] = set()
# Lane-local cap cache (per day) — NEVER backtester.filters._mcap_cache (module docstring).
_cap_cache_date: Optional[date] = None
_cap_cache: dict[str, Optional[float]] = {}
_cap_failures: dict[str, int] = {}     # per-day, per-ticker unreadable-cap count


# ── Pure compute (fixture-testable, no IO) ─────────────────────────────────────────────


@dataclass(frozen=True)
class LaneVerdict:
    ticker: str
    meets_free_terms: bool
    gap_pct: Optional[float]
    prev_close: Optional[float]
    vol_percentile: Optional[float]
    vol_history_n: int
    fail_reasons: tuple[str, ...] = field(default_factory=tuple)


def free_terms(candidate: dict, vol_history: list[float]) -> LaneVerdict:
    """The two free terms + the universe floor for ONE candidate. Pure. `vol_history` is the
    rolling-20-day-mean series the scan already fetched (mi_daily_closes-sourced); an EMPTY
    history ranks nothing — `_volume_percentile` returns its neutral 50, which cannot clear 90,
    and `vol_history_n=0` says why (P1: a data gap is recorded, never guessed around)."""
    ticker = candidate.get("ticker")
    gap = candidate.get("gap_pct")
    prev_close = candidate.get("prev_close")
    today_volume = candidate.get("today_volume") or 0
    hist = list(vol_history or [])
    pct = _volume_percentile(today_volume, hist) if hist else None
    fails: list[str] = []
    if prev_close is None or prev_close < LANE_MIN_PREV_CLOSE:
        fails.append("prev_close_below_floor")
    if gap is None or gap < LANE_MIN_GAP_PCT:
        fails.append("gap_below_lane_floor")
    if not hist:
        fails.append("no_volume_history")
    elif pct is None or pct < LANE_MIN_VOL_PERCENTILE:
        fails.append("vol_percentile_below_lane_floor")
    return LaneVerdict(
        ticker=ticker, meets_free_terms=not fails, gap_pct=gap, prev_close=prev_close,
        vol_percentile=pct, vol_history_n=len(hist), fail_reasons=tuple(fails),
    )


_SNAPSHOT_KEYS = (
    "ticker", "gap_pct", "gap_pct_rt", "gap_pct_delayed", "price_source", "prev_close",
    "current_price", "today_volume", "adv", "adv_source",
)


def snapshot_board(candidates: list[dict]) -> list[dict]:
    """COPY the fields the lane reads off every candidate — the acting loop mutates these
    dicts after the hook point (quality metrics, rt volume, grades), and the lane's task runs
    concurrently with it. Shallow per-field copies of scalars; the acting dicts are never
    referenced again. Pure."""
    return [{k: c.get(k) for k in _SNAPSHOT_KEYS} for c in candidates]


def screen_board(snapshots: list[dict], vol_history_daily_map: dict[str, list[float]],
                 minutes_since_open: Optional[int]) -> list[LaneVerdict]:
    """The free terms over the whole board. Pure. Pre-market (minutes_since_open None) ->
    nothing evaluates: the rule is a session reading ("by the 09:31 tick")."""
    if minutes_since_open is None:
        return []
    return [free_terms(s, vol_history_daily_map.get(s.get("ticker"), []))
            for s in snapshots if s.get("ticker")]


def quoted_spread_bps(bid: Optional[float], ask: Optional[float]) -> Optional[float]:
    """(ask - bid) / mid x 10,000. None unless both sides are real prices."""
    if not bid or not ask or bid <= 0 or ask <= 0 or ask < bid:
        return None
    mid = (ask + bid) / 2.0
    return round((ask - bid) / mid * 10_000.0, 2)


def blocking_filters_for(*, extension_pct: Optional[float], on_cooldown: bool,
                         days_since_prior_alert: Optional[int], quality_reason: Optional[str],
                         quality_adv_dollar: Optional[float], atr_pct: Optional[float],
                         acting_rank: Optional[int], ma_flag: Optional[bool],
                         today_volume: float) -> list[dict]:
    """Every OTHER MAGNA53 gate the name failed at the tick, each with its compared value and
    threshold (the cap floor is implied by lane membership and carried by `market_cap`).
    Stage-honest: a gate whose input was never computed is simply absent, never guessed.
    The RVOL@T gate and the score bar need the graded path and are NOT reconstructible here —
    stated in the SSoT section rather than approximated. Pure."""
    out: list[dict] = []
    if extension_pct is not None and extension_pct >= MAX_EXTENSION_PCT:
        out.append({"gate": "extended", "value": round(extension_pct, 2),
                    "threshold": MAX_EXTENSION_PCT})
    if on_cooldown:
        out.append({"gate": "cooldown", "value": days_since_prior_alert,
                    "threshold": EP_COOLDOWN_DAYS})
    if quality_reason:
        if quality_reason.startswith(FILTER_ADV_NO_DATA):
            out.append({"gate": "adv_no_data", "value": None, "threshold": MIN_ADV_DOLLAR_VOLUME})
        elif quality_reason.startswith(FILTER_ADV_TOO_LOW):
            out.append({"gate": "adv_too_low", "value": quality_adv_dollar,
                        "threshold": MIN_ADV_DOLLAR_VOLUME})
        elif quality_reason.startswith(FILTER_ATR_TOO_HIGH):
            out.append({"gate": "atr_too_high", "value": atr_pct, "threshold": MAX_ATR_PCT})
        else:
            out.append({"gate": "quality_filter", "value": None, "threshold": None,
                        "reason": quality_reason})
    if acting_rank is not None and acting_rank > SHORTLIST_SIZE:
        out.append({"gate": "shortlist_cap", "value": acting_rank, "threshold": SHORTLIST_SIZE})
    if ma_flag:
        out.append({"gate": "mna", "value": True, "threshold": None})
    if today_volume < MIN_PREMARKET_SHARES:
        # raw floor only — the R6 carve-outs (5x pm RVOL / strong+ grade) need the graded path
        out.append({"gate": "pm_shares_floor", "value": today_volume,
                    "threshold": MIN_PREMARKET_SHARES, "reason": "raw floor; carve-outs need a grade"})
    return out


# ── Orchestration (DB reads + the one write; all off the ORB critical path) ─────────────


def _reset_day_state(today: date) -> None:
    global _evaluated_date, _evaluated, _cap_cache_date, _cap_cache, _cap_failures
    if _evaluated_date != today:
        _evaluated_date, _evaluated = today, set()
    if _cap_cache_date != today:
        _cap_cache_date, _cap_cache, _cap_failures = today, {}, {}


async def _market_cap(ticker: str) -> tuple[Optional[float], Optional[str]]:
    """The cap via the LANE'S OWN cache. (None, 'unavailable') on any failure — the lane
    never treats unknown as under-the-floor, and never touches the acting cache."""
    if _cap_cache.get(ticker) is not None:
        return _cap_cache[ticker], "yfinance_profile"
    try:
        profile = await get_fmp_profile(ticker)
        cap = profile.get("marketCap") if profile else None
        cap = float(cap) if cap is not None else None
    except Exception as e:  # loud-ok: counted + audited by the caller's tally; the name is retried next tick
        logger.warning(f"#624 lane cap read failed for {ticker}: {e}")
        cap = None
    _cap_cache[ticker] = cap
    return cap, ("yfinance_profile" if cap is not None else "unavailable")


async def enrich_and_record(survivors: list[LaneVerdict], snapshots_by_ticker: dict[str, dict], *,
                            today: date, now_et: datetime, minutes_since_open: Optional[int],
                            extension_map: dict[str, float], cooldown_tickers: set[str],
                            cooldown_last_alert: dict[str, date],
                            rank_by_prescore: dict[str, int], rank_by_gap: dict[str, int],
                            acting_rank: dict[str, int], regime_label: Optional[str]) -> dict[str, int]:
    """The expensive half, for the free-term survivors only. Returns counters."""
    out = {"survivors": len(survivors), "enriched": 0, "admitted": 0, "rejected_cap": 0,
           "cap_unavailable": 0, "deduped": 0, "tick_capped": 0, "written": 0, "errors": 0}
    _reset_day_state(today)
    try:
        already = await get_lowcap_lane_signal_tickers(today)
    except Exception as e:  # loud-ok: the in-process set still dedupes; a restart may re-enrich once (DB conflict absorbs it)
        logger.warning(f"#624 lane: today's signal tickers read failed — {e}")
        already = set()
    todo = [v for v in sorted(survivors, key=lambda v: -(v.gap_pct or 0.0))
            if v.ticker not in _evaluated and v.ticker not in already]
    out["deduped"] = len(survivors) - len(todo)
    if len(todo) > MAX_ENRICH_PER_TICK:
        out["tick_capped"] = len(todo) - MAX_ENRICH_PER_TICK
        await log_audit_event(
            "lowcap_lane_tick_cap",
            f"{out['tick_capped']} free-term survivor(s) deferred to the next tick "
            f"(cap {MAX_ENRICH_PER_TICK}): {', '.join(v.ticker for v in todo[MAX_ENRICH_PER_TICK:])}")
        todo = todo[:MAX_ENRICH_PER_TICK]
    if not todo:
        return out

    admitted: list[tuple[LaneVerdict, float, str]] = []
    for v in todo:
        cap, cap_source = await _market_cap(v.ticker)
        out["enriched"] += 1
        if cap is None:
            out["cap_unavailable"] += 1
            _cap_failures[v.ticker] = _cap_failures.get(v.ticker, 0) + 1
            gave_up = _cap_failures[v.ticker] >= MAX_CAP_RETRIES_PER_DAY
            if gave_up:
                _evaluated.add(v.ticker)   # bounded: no more reads for this name today
            await log_audit_event(
                "lowcap_lane_cap_unavailable",
                f"{v.ticker}: gap {v.gap_pct:.1f}% vol pct {v.vol_percentile:.0f} — cap unreadable "
                f"({_cap_failures[v.ticker]}/{MAX_CAP_RETRIES_PER_DAY}), not recorded"
                + (" — giving up for today" if gave_up else " (retried next tick)"))
            continue                       # NOT marked evaluated until the retry budget is spent
        _evaluated.add(v.ticker)
        if cap >= LANE_MAX_MARKET_CAP:
            out["rejected_cap"] += 1       # above the floor: the acting path's own universe
            continue
        admitted.append((v, cap, cap_source))
    if not admitted:
        return out
    out["admitted"] = len(admitted)

    tickers = [v.ticker for v, _, _ in admitted]
    rt_vols: dict = {}
    quotes: dict = {}
    prior_lane: dict = {}
    try:
        rt_vols = await get_alpaca_minute_cum_volumes(tickers, now_et)
    except Exception as e:  # loud-ok: the rt read is the STORED companion, never acting; NULL is honest
        logger.warning(f"#624 lane rt volume read failed: {e}")
    try:
        quotes = await get_alpaca_latest_quotes(tickers)
    except Exception as e:  # loud-ok: fillability columns NULL for this tick, recorded as such
        logger.warning(f"#624 lane quote read failed: {e}")
    try:
        prior_lane = await get_lowcap_lane_prior_signal_dates(tickers, today)
    except Exception as e:  # loud-ok: days_since_prior_lane_signal NULL; nothing acting reads it
        logger.warning(f"#624 lane prior-signal read failed: {e}")

    admission_era = rule_eras.admission_era_as_of(today)
    rows: list[dict] = []
    for v, cap, cap_source in admitted:
        try:
            snap = snapshots_by_ticker.get(v.ticker, {})
            metrics: dict = {}
            # ⚠ skip_mcap=True ALWAYS — see the module docstring (_mcap_cache hazard).
            passed, quality_reason = await check_filters(v.ticker, today, skip_mcap=True, metrics=metrics)
            try:
                ma_flag, ma_tel = await is_likely_ma(v.ticker, check_polygon=True)
            except Exception as e:  # loud-ok: catalyst flag NULL for this row, recorded as such
                logger.warning(f"#624 lane M&A check failed for {v.ticker}: {e}")
                ma_flag, ma_tel = None, None
            lc5 = extension_map.get(v.ticker)
            pc = v.prev_close
            ext = (round((pc - lc5) / lc5 * 100.0, 2) if lc5 and lc5 > 0 and pc else None)
            last_alert = cooldown_last_alert.get(v.ticker)
            dsa = (today - last_alert).days if last_alert else None
            rank_act = acting_rank.get(v.ticker)
            rt = rt_vols.get(v.ticker) or {}
            rt_measured = (rt.get("pm_bars", 0) or 0) + (rt.get("session_bars", 0) or 0) > 0
            q = quotes.get(v.ticker) or {}
            prior = prior_lane.get(v.ticker)
            today_volume = float(snap.get("today_volume") or 0)
            rows.append({
                "ticker": v.ticker, "scan_date": today, "tick_wallclock_et": now_et,
                "minutes_since_open": minutes_since_open,
                "gap_pct": v.gap_pct, "gap_pct_rt": snap.get("gap_pct_rt"),
                "gap_pct_delayed": snap.get("gap_pct_delayed"), "price_source": snap.get("price_source"),
                "prev_close": pc, "current_price": snap.get("current_price"),
                "market_cap": cap, "market_cap_source": cap_source,
                "today_volume_delayed": today_volume,
                "today_volume_rt": (float(rt.get("pm_vol", 0) + rt.get("session_vol", 0))
                                    if rt_measured else None),
                "rt_pm_bars": rt.get("pm_bars"), "rt_session_bars": rt.get("session_bars"),
                "acting_volume_source": "delayed",
                "vol_percentile": v.vol_percentile, "vol_history_n": v.vol_history_n,
                "extension_pct": ext,
                "quality_adv_dollar": metrics.get("quality_adv_dollar"),
                "atr_pct": metrics.get("atr_pct"),
                "blocking_filters": blocking_filters_for(
                    extension_pct=ext, on_cooldown=v.ticker in cooldown_tickers,
                    days_since_prior_alert=dsa, quality_reason=None if passed else quality_reason,
                    quality_adv_dollar=metrics.get("quality_adv_dollar"), atr_pct=metrics.get("atr_pct"),
                    acting_rank=rank_act, ma_flag=ma_flag, today_volume=today_volume),
                "rank_by_prescore": rank_by_prescore.get(v.ticker),
                "rank_by_gap": rank_by_gap.get(v.ticker),
                "in_shortlist": (rank_act is not None and rank_act <= SHORTLIST_SIZE),
                "days_since_prior_alert": dsa,
                "days_since_prior_lane_signal": (today - prior).days if prior else None,
                "bid_px": q.get("bid"), "ask_px": q.get("ask"),
                "bid_size": q.get("bid_size"), "ask_size": q.get("ask_size"),
                "quoted_spread_bps": quoted_spread_bps(q.get("bid"), q.get("ask")),
                "quote_ts": q.get("ts"),
                "ma_flag": ma_flag, "ma_source": (ma_tel or {}).get("source") if ma_tel else None,
                "admission_era": admission_era, "regime": regime_label,
                "lane_gap_floor_pct": LANE_MIN_GAP_PCT,
                "lane_vol_percentile_floor": LANE_MIN_VOL_PERCENTILE,
                "lane_max_market_cap": float(LANE_MAX_MARKET_CAP),
                "lane_rule_version": LANE_RULE_VERSION,
            })
        except Exception as e:  # loud-ok: one name's enrichment failure is counted + audited; the others proceed
            out["errors"] += 1
            await log_audit_event("lowcap_lane_error", f"{v.ticker} {today.isoformat()}: {type(e).__name__}: {e}")
    if rows:
        out["written"] = await insert_lowcap_lane_signals(rows)
        for r in rows:
            await log_audit_event(
                "lowcap_lane_signal_recorded",
                f"{r['ticker']} gap {r['gap_pct']:.1f}% vol pct {r['vol_percentile']:.0f} "
                f"cap ${(r['market_cap'] or 0) / 1e6:.0f}M at {now_et.strftime('%H:%M')} ET — "
                f"{len(r['blocking_filters'])} other gate(s) failed (SHADOW, record only)",
                json.dumps({k: r.get(k) for k in (
                    "ticker", "gap_pct", "vol_percentile", "market_cap", "blocking_filters",
                    "quoted_spread_bps", "bid_size", "ask_size", "ma_flag", "in_shortlist")},
                    default=str),
            )
    return out


async def run_lowcap_lane_tick(snapshots: list[dict], *, today: date, now_et: datetime,
                               minutes_since_open: Optional[int],
                               vol_history_daily_map: dict[str, list[float]],
                               extension_map: dict[str, float], cooldown_tickers: set[str],
                               cooldown_last_alert: dict[str, date],
                               rank_by_prescore: dict[str, int], rank_by_gap: dict[str, int],
                               acting_rank: dict[str, int],
                               regime_label: Optional[str]) -> dict[str, Any]:
    """The detached task body. NEVER raises."""
    out: dict[str, Any] = {"board": len(snapshots), "survivors": 0, "written": 0, "errors": 0}
    try:
        if not await should_run(STRATEGY_ID):
            out["skipped"] = "disabled"
            return out
        verdicts = screen_board(snapshots, vol_history_daily_map, minutes_since_open)
        survivors = [v for v in verdicts if v.meets_free_terms]
        out["survivors"] = len(survivors)
        if not survivors:
            return out
        by_ticker = {s["ticker"]: s for s in snapshots if s.get("ticker")}
        out.update(await enrich_and_record(
            survivors, by_ticker, today=today, now_et=now_et,
            minutes_since_open=minutes_since_open, extension_map=extension_map,
            cooldown_tickers=cooldown_tickers, cooldown_last_alert=cooldown_last_alert,
            rank_by_prescore=rank_by_prescore, rank_by_gap=rank_by_gap,
            acting_rank=acting_rank, regime_label=regime_label))
    except Exception as e:  # loud-ok: shadow-only — counted, audited, never reaches the scan
        out["errors"] += 1
        logger.warning(f"#624 low-cap lane tick failed (shadow-only): {e}")
        try:
            await log_audit_event("lowcap_lane_error", f"tick {now_et.isoformat()}: {type(e).__name__}: {e}")
        except Exception:  # loud-ok: the audit sink itself failed; the warning above already spoke
            pass
    return out


def schedule_lowcap_lane_tick(candidates: list[dict], *, today: date, now_et: datetime,
                              minutes_since_open: Optional[int],
                              vol_history_daily_map: dict[str, list[float]],
                              extension_map: dict[str, float], cooldown_tickers: set[str],
                              cooldown_last_alert: dict[str, date],
                              rank_by_prescore: dict[str, int], rank_by_gap: dict[str, int],
                              acting_rank: dict[str, int], regime_label: Optional[str],
                              bg_tasks: set) -> Optional["asyncio.Task"]:
    """The SYNCHRONOUS entry `run_ep_scan` calls before the shortlist cut: snapshot the board,
    copy the maps, detach the task. Returns the task (None pre-market or on an empty board)
    so a test can drain it. Nothing here awaits; nothing here mutates a scan object."""
    if minutes_since_open is None or not candidates:
        return None
    task = asyncio.create_task(run_lowcap_lane_tick(
        snapshot_board(candidates), today=today, now_et=now_et,
        minutes_since_open=minutes_since_open,
        vol_history_daily_map={k: list(v) for k, v in (vol_history_daily_map or {}).items()},
        extension_map=dict(extension_map or {}), cooldown_tickers=set(cooldown_tickers or ()),
        cooldown_last_alert=dict(cooldown_last_alert or {}),
        rank_by_prescore=dict(rank_by_prescore or {}), rank_by_gap=dict(rank_by_gap or {}),
        acting_rank=dict(acting_rank or {}), regime_label=regime_label))
    bg_tasks.add(task)
    task.add_done_callback(bg_tasks.discard)
    return task
