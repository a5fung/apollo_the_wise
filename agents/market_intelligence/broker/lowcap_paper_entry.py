"""#624 SMALL-CAP PAPER LANE — the PAPER-ONLY order step (2026-10-10, operator "Ok to recs").

WHAT IT DOES. Reads today's HIGH rows from the lane's OWN table (mi_lowcap_paper_lane_alerts —
never mi_ep_alerts, which the live order step `live_tracker.process_new_alerts_live` reads) and
sends each through the single entry funnel `entry_pipeline.submit_trade_entry` with MAGNA53's
order: the same ORB stop-buy at the opening-range high, the same entry − 2R stop
(`order_manager.prepare_orb_order`), the same 09:31–09:45 window and the 10:00 ET cancel of an
unfilled order (`cancel_unfilled_entries` covers every account mode), the same submission-time gap
re-check at MAGNA53's own floor, the same ADV$ / ATR re-check at order time. The ONE difference
is the market-cap read: the lane exists for names under the floor, so the order-time re-check
runs `check_filters(..., skip_mcap=True)`.

WHY IT CANNOT REACH REAL MONEY — four independent walls, each test-pinned
(tests/test_624_paper_lane.py):
  1. It reads ONLY the lane table. A lane HIGH is never in mi_ep_alerts, so the live order step
     can never see it, and this step can never see a live alert.
  2. Before anything else it requires the lane's strategy row to be phase 'paper' AND to resolve
     (`resolve_account_mode_for_strategy`) to 'paper'; any other answer refuses the whole run and
     pages. `live_real_enabled` is never consulted.
  3. It calls `submit_trade_entry(require_account_mode='paper')` — the funnel itself refuses a
     strategy that resolves anywhere else, before any row or order (defense in depth for a phase
     change between 2 and 3).
  4. Every order the funnel places for it carries `make_client_order_id('paper',
     'magna53_smallcap', ticker)` (order_manager.submit_entry builds it from the row's
     account_mode + signal_type), so a fill event can only ever match the paper book
     (trade_stream._verify_event_account_mode rejects a cross-account event before any write).

PRE-FLIGHT. Before the FIRST lane order of an ET day, the paper account must answer
(`alpaca_client.get_account('paper')`, not trading- or account-blocked). A failure is logged,
audited and PAGED (paper-prefixed), and nothing is submitted; the next call retries (the paper
book had no trades for 60 days before this lane — review correction 9).

TELEGRAM POLICY (decided for the lane, paper only): an alert / a placed order / a skip sends NO
Telegram — audit rows only ("an alert that says no action is noise"). A FAILURE pages,
paper-prefixed: the pre-flight, a refused phase, a crashed per-name task, an order the funnel
could not place (the funnel's own infra:* skip and auto-enter-failed pages, which already carry
the 📄 PAPER prefix). The live #197 CAP+1 page is switched off for this caller.

STOP SWITCH. The runtime toggle `lowcap_paper_lane` (mi_safeguard_state, account_mode='global';
default ON — PENDING HIS CONFIRMATION) and `mi_strategies.enabled` both stop it; `/pause` and
LIVE_TRADING_ENABLED (the live kill switches) stop it too because they stop every order path.
"""
from __future__ import annotations

import asyncio
import logging
from datetime import date, datetime

from agents.market_intelligence.broker import alpaca_client as alpaca
from agents.market_intelligence.broker.entry_pipeline import (
    ACTION_AUTO_ENTER_FAILED,
    ACTION_AUTO_ENTERED,
    ACTION_BLOCKED,
    submit_trade_entry,
)
from agents.market_intelligence.broker.skip_reasons import WINDOW_DUPLICATE, WINDOW_OUT_OF_ORB
from agents.market_intelligence.backtester.filters import check_filters, compute_atr_14
from shared.dates import _ET, et_today
from agents.market_intelligence.constants import (
    LIVE_TRADING_ENABLED,
    mode_prefix,
    resolve_account_mode_for_strategy,
)
from agents.market_intelligence.db import (
    LOWCAP_PAPER_LANE_STRATEGY_ID,
    get_lowcap_paper_lane_highs,
    get_pool,
    get_runtime_toggle,
    log_audit_event,
)
# MAGNA53's OWN gap criterion — the same submission-time re-check the live step opts into.
from agents.market_intelligence.ep_detector import MIN_GAP_PCT as _MAGNA53_MIN_GAP_PCT

logger = logging.getLogger(__name__)

LANE_ACCOUNT_MODE = "paper"   # mode-ok: the lane's ONE permitted account — compared, never used to filter
STRATEGY_ID = LOWCAP_PAPER_LANE_STRATEGY_ID
TOGGLE = "lowcap_paper_lane"
TOGGLE_ENV = "LOWCAP_PAPER_LANE_ENABLED"
STRATEGY_LABEL = "ORB small-cap lane (paper)"

# The ET day the paper account last answered the pre-flight (None = not yet today).
_preflight_ok_date: date | None = None


def in_orb_window(now_et: datetime) -> bool:
    """MAGNA53's ORB submission window, the scheduler's own test (09:31 ≤ t < 09:45 ET)."""
    return now_et.hour == 9 and 31 <= now_et.minute < 45


async def _page(text: str) -> None:
    """A FAILURE page, paper-prefixed. Never raises."""
    try:
        from agents.market_intelligence.briefing import send_telegram_message
        await send_telegram_message(f"{mode_prefix(LANE_ACCOUNT_MODE)}{text}")
    except Exception as e:  # loud-ok: the audit row written by the caller is the durable record
        logger.error(f"#624 paper lane page failed: {e}")


async def paper_account_preflight(today: date) -> bool:
    """True when the paper account answered today (cached per ET day after the first success).
    On failure: log + audit + page, return False — the caller submits nothing."""
    global _preflight_ok_date
    if _preflight_ok_date == today:
        return True
    try:
        acct = await alpaca.get_account(account_mode=LANE_ACCOUNT_MODE)
        if acct.get("trading_blocked") or acct.get("account_blocked"):
            raise RuntimeError(f"paper account blocked (trading_blocked={acct.get('trading_blocked')}, "
                               f"account_blocked={acct.get('account_blocked')})")
        if not acct.get("equity"):
            raise RuntimeError(f"paper account returned no equity ({acct.get('equity')!r})")
    except Exception as e:  # loud-ok: logged + audited + paged below; the run submits nothing
        logger.error(f"#624 paper lane pre-flight FAILED — no lane orders: {e}")
        await log_audit_event("lowcap_paper_lane_preflight_failed",
                              f"{today.isoformat()}: {type(e).__name__}: {str(e)[:300]}")
        await _page(f"🚨 Small-cap paper lane: the PAPER account did not answer the pre-flight "
                    f"check — no lane orders placed ({type(e).__name__}: {str(e)[:160]})")
        return False
    _preflight_ok_date = today
    await log_audit_event("lowcap_paper_lane_preflight_ok",
                          f"{today.isoformat()}: paper account answered (equity ${acct['equity']:,.0f})")
    return True


async def _strategy_paper_or_refuse(today: date):
    """The lane's strategy row, ONLY when it is enabled, phase 'paper' and resolves to 'paper'.
    Disabled / missing → None quietly (the switch is off). Any other phase → None + audit + page:
    a lane that would route anywhere but paper is refused outright."""
    from agents.market_intelligence.strategies.registry import get_strategy
    strategy = await get_strategy(STRATEGY_ID)
    if strategy is None or not strategy.enabled:
        return None
    try:
        mode = resolve_account_mode_for_strategy(strategy) if strategy.phase == "paper" else None  # mode-ok: the lane's own phase guard — refuses anything but paper
    except Exception:  # loud-ok: an unresolvable phase is refused below
        mode = None
    if mode != LANE_ACCOUNT_MODE:
        msg = (f"{STRATEGY_ID} phase={strategy.phase!r} resolves to {mode!r} — the small-cap "
               f"lane orders on PAPER only; refused")
        await log_audit_event("lowcap_paper_lane_refused", f"{today.isoformat()}: {msg}")
        await _page(f"🚨 Small-cap paper lane refused to order: {msg}")
        return None
    return strategy


async def process_lowcap_paper_alerts(today: date | None = None,
                                      trigger: str = "lane_tick") -> list[dict]:
    """Submit today's lane HIGHs on the PAPER account. Called through the execution facade
    (`execution_client.trigger_lowcap_paper_entry`) by the lane task after the lane has graded a
    tick. Idempotent — a name with a trade row already is a silent WINDOW_DUPLICATE in the funnel."""
    today = today or et_today()
    if not LIVE_TRADING_ENABLED:
        return []
    if not await get_runtime_toggle(TOGGLE, TOGGLE_ENV, default=True):
        return []
    strategy = await _strategy_paper_or_refuse(today)
    if strategy is None:
        return []
    alerts = await get_lowcap_paper_lane_highs(today)
    if not alerts:
        return []

    now_et = datetime.now(_ET)
    if not in_orb_window(now_et):
        # A lane HIGH that first surfaced after 09:45 (or a call before 09:31): no order is
        # possible against the 09:30 bar. One durable skip row per name (the funnel's own
        # writer, paper book), audit only — the same terminal state live gives an out-of-window HIGH.
        if now_et.hour > 9 or (now_et.hour == 9 and now_et.minute >= 45):
            from agents.market_intelligence.broker.live_tracker import _insert_skipped_trade
            pool = await get_pool()
            out = []
            for a in alerts:
                async with pool.acquire() as conn:
                    has_row = await conn.fetchval(
                        "SELECT EXISTS(SELECT 1 FROM mi_live_trades WHERE ticker = $1 "
                        "AND alert_date = $2 AND account_mode = $3)",
                        a["ticker"], today, LANE_ACCOUNT_MODE)
                if has_row:
                    continue
                reason = f"{WINDOW_OUT_OF_ORB}: lane HIGH, order step ran {now_et.strftime('%H:%M')} ET"  # recovery-clock-ok: wall-clock label of when this step actually ran
                await _insert_skipped_trade(a["ticker"], today, a, None, reason,
                                            signal_type=STRATEGY_ID, account_mode=LANE_ACCOUNT_MODE)
                await log_audit_event("lowcap_paper_lane_out_of_window", f"{a['ticker']} — {reason}")
                out.append({"ticker": a["ticker"], "action": "skipped", "reason": reason})
            return out
        return []

    if not await paper_account_preflight(today):
        return []

    pool = await get_pool()
    async with pool.acquire() as conn:
        regime_record = await conn.fetchrow(
            "SELECT * FROM mi_market_regime WHERE regime_date <= $1 ORDER BY regime_date DESC LIMIT 1",
            today,
        )
    regime_record = dict(regime_record) if regime_record else None
    sem = asyncio.Semaphore(5)

    async def _one(alert: dict) -> dict:
        ticker = alert["ticker"]
        async with sem:
            # Order-time quality re-check, as live does — ADV$ / ATR only: the cap is the one
            # filter this lane inverts (a cap read here could only re-ask the question the lane
            # was built to answer).
            passed, skip_reason = await check_filters(ticker, today, skip_mcap=True)
            if not passed:
                from agents.market_intelligence.broker.live_tracker import _insert_skipped_trade
                await _insert_skipped_trade(ticker, today, alert, regime_record, skip_reason,
                                            signal_type=STRATEGY_ID, account_mode=LANE_ACCOUNT_MODE)
                await log_audit_event("lowcap_paper_lane_filtered", f"{ticker} — {skip_reason}")
                return {"ticker": ticker, "action": "filtered", "reason": skip_reason}
            atr_14, _ = await compute_atr_14(ticker, today)

            async def _spec(alert_ctx, orb_bar, regime, account_mode, _atr=atr_14, _today=today):
                from agents.market_intelligence.broker.order_manager import prepare_orb_order
                return await prepare_orb_order(alert_ctx, orb_bar, _atr or 0, regime,
                                               account_mode=account_mode, today=_today)

            return await submit_trade_entry(
                alert_context=alert,
                spec_builder=_spec,
                regime_record=regime_record,
                strategy_label=STRATEGY_LABEL,
                signal_type=STRATEGY_ID,
                today=today,
                atr_14=atr_14,
                success_title="Lane paper order placed",
                fade_midpoint_ratio=None,                 # MAGNA53's own setting
                rt_gap_floor_pct=_MAGNA53_MIN_GAP_PCT,    # MAGNA53's own submission-time gap floor
                aggregate_skips=True,                     # skips are audit rows; infra:* still pages
                require_account_mode=LANE_ACCOUNT_MODE,   # wall 3: the funnel refuses any other book
                page_cap_plus_one=False,                  # the live CAP+1 manual-trade prompt is off
            )

    raw = await asyncio.gather(*(_one(a) for a in alerts), return_exceptions=True)
    results: list[dict] = []
    for alert, r in zip(alerts, raw):
        tkr = alert["ticker"]
        if isinstance(r, BaseException):
            await log_audit_event("lowcap_paper_lane_crash", f"{tkr} [{trigger}] — {type(r).__name__}: {r}")
            await _page(f"🚨 *{tkr}* small-cap lane paper order crashed — {type(r).__name__}: {str(r)[:160]}")
            results.append({"ticker": tkr, "action": "crashed", "reason": str(r)})
            continue
        if r.get("action") == ACTION_BLOCKED and str(r.get("reason", "")).startswith("block:account_mode_mismatch"):
            await _page(f"🚨 *{tkr}* small-cap lane order REFUSED by the entry funnel — {r.get('reason')}")
        if r.get("reason") != WINDOW_DUPLICATE:
            await log_audit_event(
                "lowcap_paper_lane_order",
                f"{tkr} [{trigger}] → {r.get('action')}"
                + (f" ({r.get('reason')})" if r.get("reason") else "")
                + (f" trade_id={r.get('trade_id')}" if r.get("trade_id") else ""))
        results.append(r)
    entered = sum(1 for r in results if r.get("action") == ACTION_AUTO_ENTERED)
    failed = sum(1 for r in results if r.get("action") in (ACTION_AUTO_ENTER_FAILED, "crashed"))
    logger.info(f"#624 paper lane [{trigger}]: {entered} paper order(s) placed, {failed} failed, "
                f"{len(results)} lane HIGH(s)")
    return results
