"""
Unified trade-entry pipeline.

Single code path for every ORB bracket entry (MAGNA53 EP and 9M Day 2).
Strategy differences (stop source, position sizing) are injected via the
`spec_builder` callback; everything else — duplicate check, safeguards,
bar-fetch-with-retry, fade guard, DB insert, Alpaca submit, audit log,
Telegram — lives here exactly once.

Contract: every terminal failure state sends a Telegram message. No
silent skips. If a monitored candidate fails to enter, the user finds
out in real time.
"""
from __future__ import annotations

import asyncio
import logging
from datetime import date
from typing import Any, Awaitable, Callable

from agents.market_intelligence.broker import alpaca_client as alpaca
from agents.market_intelligence.broker.skip_reasons import (
    BLOCK_PAPER_STRATEGY_ON_LIVE,
    BLOCK_STRATEGY_DISABLED,
    BLOCK_STRATEGY_IN_SHADOW,
    INFRA_NO_BAR,
    INFRA_ORDER_SUBMIT_FAILED,
    SETUP_FADED_FROM_ORB,
    WINDOW_DUPLICATE,
    BLOCK_TICKER_OPEN_POSITION,
    humanize,
)
from agents.market_intelligence.briefing import send_telegram_message
from agents.market_intelligence.constants import current_account_mode, mode_prefix
from agents.market_intelligence.db import get_pool, log_audit_event

logger = logging.getLogger(__name__)

BAR_RETRY_MAX = 3
BAR_RETRY_DELAY_SEC = 10
FADE_MIDPOINT_RATIO = 0.5

# Bounded action vocabulary for `submit_trade_entry` return dicts.
# Callers pattern-match on these (see live_tracker.process_new_alerts_live
# success/skip counters and submit_9m_day2_trade sugar-baby status mapping).
ACTION_AUTO_ENTERED = "auto_entered"
ACTION_PROPOSED = "proposed"
ACTION_AUTO_ENTER_FAILED = "auto_enter_failed"
ACTION_PROPOSAL_SEND_FAILED = "proposal_send_failed"
ACTION_SKIPPED = "skipped"
ACTION_BLOCKED = "blocked"


# ── Bar fetch ────────────────────────────────────────────────────────────────

async def fetch_orb_bar_with_retry(
    ticker: str,
    today: date,
    strategy_label: str,
) -> dict | None:
    """Fetch first 1-min bar, retrying every BAR_RETRY_DELAY_SEC up to
    BAR_RETRY_MAX attempts. The REST endpoint can take a few seconds after
    bar close (9:31:00) to return the settled bar; single-attempt callers
    miss any candidate that hits the gap.
    """
    bar: dict | None = None
    for attempt in range(1, BAR_RETRY_MAX + 1):
        bar = await alpaca.get_first_bar(ticker, today)
        if bar:
            return bar
        if attempt < BAR_RETRY_MAX:
            logger.info(
                f"{strategy_label} {ticker}: no bar attempt {attempt}/{BAR_RETRY_MAX}, "
                f"retry in {BAR_RETRY_DELAY_SEC}s"
            )
            try:
                await log_audit_event(
                    "orb_bar_miss",
                    f"{strategy_label} {ticker} attempt {attempt}/{BAR_RETRY_MAX} — "
                    f"bar not available, retry {BAR_RETRY_DELAY_SEC}s",
                )
            except Exception:
                pass
            await asyncio.sleep(BAR_RETRY_DELAY_SEC)
    return None


# ── Fade guard ───────────────────────────────────────────────────────────────

async def check_fade_guard(
    ticker: str, orb_bar: dict, ratio: float | None = FADE_MIDPOINT_RATIO,
) -> tuple[bool, str | None]:
    """Return (ok, skip_reason). If the latest trade is below
    `orb_low + (orb_high - orb_low) * ratio`, the gap-and-go has lost
    momentum. Silent-on-data-failure: if `get_latest_trade` returns None,
    we let the bracket through — don't block on feed flakiness.

    `ratio=None` skips the check entirely. MAGNA53 EP HIGH passes None
    because Sonnet+Perplexity validation + ATR stop width + 10:00 ET
    cleanup already cover the dead-cat-fill case. 9M Day 2 (no LLM) passes
    a smaller ratio (e.g. 0.25) to keep some fade protection.
    """
    if ratio is None:
        return True, None

    orb_high = orb_bar["high"]
    orb_low = orb_bar["low"]
    orb_midpoint = orb_low + (orb_high - orb_low) * ratio

    latest = await alpaca.get_latest_trade(ticker)
    if not latest or not latest.get("price"):
        return True, None

    last_price = float(latest["price"])
    if last_price >= orb_midpoint:
        return True, None

    fade_pct = (orb_high - last_price) / orb_high * 100 if orb_high > 0 else 0
    reason = (
        f"{SETUP_FADED_FROM_ORB}: last ${last_price:.2f} < threshold "
        f"${orb_midpoint:.2f} (ratio={ratio:.2f}, ORB H=${orb_high:.2f} "
        f"L=${orb_low:.2f}, faded {fade_pct:.1f}%)"
    )
    return False, reason


# ── Main pipeline ────────────────────────────────────────────────────────────

SpecBuilder = Callable[
    [dict, dict, dict | None], Awaitable[tuple[dict | None, str | None]]
]
SkipHook = Callable[[str], Awaitable[None]]


async def submit_trade_entry(
    *,
    alert_context: dict,
    spec_builder: SpecBuilder,
    regime_record: dict | None,
    strategy_label: str,
    signal_type: str,
    today: date,
    atr_14: float | None = None,
    success_icon: str = "📊",
    success_title: str = "Order placed",
    stop_label: str = "Stop",
    on_skip: SkipHook | None = None,
    fade_midpoint_ratio: float | None = FADE_MIDPOINT_RATIO,
    aggregate_skips: bool = False,
) -> dict:
    """Single entry-submission pipeline.

    Required `alert_context` keys: ticker, ep_score, catalyst_quality, gap_pct.

    `spec_builder(alert_context, orb_bar, regime_record)` returns
    `(order_spec, skip_reason)`. The spec dict must contain orb_high, orb_low,
    entry_price, stop_loss_price, shares, position_size, risk_dollars.

    Every terminal skip/block/failure state calls `send_telegram_message`.
    No silent drops.
    """
    from agents.market_intelligence.broker.live_tracker import (
        _check_safeguards,
        _insert_skipped_trade,
    )
    from agents.market_intelligence.broker.order_manager import submit_entry
    from agents.market_intelligence.broker.telegram_confirm import send_trade_proposal

    ticker = alert_context["ticker"]
    pool = await get_pool()

    async def _skip(
        reason: str,
        icon: str = "⏭️",
        audit_event: str = "orb_skipped",
        action: str = ACTION_SKIPPED,
    ) -> dict:
        if on_skip:
            try:
                await on_skip(reason)
            except Exception as e:
                logger.warning(f"{strategy_label} {ticker}: on_skip hook raised — {e}")
        try:
            await _insert_skipped_trade(
                ticker, today, alert_context, regime_record, reason,
                signal_type=signal_type,
            )
        except Exception as e:
            logger.error(f"{strategy_label} {ticker}: _insert_skipped_trade raised — {e}")
        try:
            await log_audit_event(audit_event, f"{strategy_label} {ticker} — {reason}")
        except Exception:
            pass
        # aggregate_skips=True: caller emits one grouped digest after gather().
        # infra:* always pings immediately (no-silent-failures rule); filter /
        # setup / block reasons stay aggregated.
        is_infra = isinstance(reason, str) and reason.startswith("infra:")
        if not aggregate_skips or is_infra:
            try:
                await send_telegram_message(
                    f"{mode_prefix()}{icon} *{ticker}* {strategy_label} skipped — {humanize(reason)}"
                )
            except Exception as e:
                logger.error(f"{strategy_label} {ticker}: telegram skip alert failed — {e}")
        return {"ticker": ticker, "action": action, "reason": reason}

    # 1. Duplicate check — trade row already exists for this ticker+date.
    async with pool.acquire() as conn:
        exists = await conn.fetchval(
            "SELECT EXISTS(SELECT 1 FROM mi_live_trades WHERE ticker=$1 AND alert_date=$2)",
            ticker, today,
        )
    if exists:
        logger.debug(f"{strategy_label} {ticker}: trade row already exists")
        try:
            await log_audit_event(
                "orb_duplicate", f"{strategy_label} {ticker} — {WINDOW_DUPLICATE}"
            )
        except Exception:
            pass
        # Not a failure — silent is correct here. It's already been handled once.
        return {"ticker": ticker, "action": ACTION_SKIPPED, "reason": WINDOW_DUPLICATE}

    # 1b. Open-position guard — block if we already hold this ticker from any
    # prior alert_date. Prevents cross-strategy / cross-day double exposure
    # (e.g. TEAM 5/04: 9M Day 2 placed bracket while MAGNA53 5/01 fill still
    # open). Same-day dedup above handles the within-day case; this catches
    # multi-day. `status='filled' AND remaining_shares > 0` is the canonical
    # "we own shares" signal (matches update_open_positions_live).
    async with pool.acquire() as conn:
        already_open = await conn.fetchval(
            """
            SELECT alert_date FROM mi_live_trades
            WHERE ticker = $1
              AND status = 'filled'
              AND remaining_shares > 0
              AND alert_date != $2
            ORDER BY alert_date DESC
            LIMIT 1
            """,
            ticker, today,
        )
    if already_open is not None:
        reason = f"{BLOCK_TICKER_OPEN_POSITION}: open since {already_open.isoformat()}"
        return await _skip(
            reason, icon="🚫",
            audit_event="orb_blocked", action=ACTION_BLOCKED,
        )

    # 1a. Strategy phase gate. Fail-open if the strategy isn't in the registry
    # (legacy code path / pre-deploy state). Once seeded, the gate is the
    # single per-strategy enable/disable surface.
    from agents.market_intelligence.strategies.registry import get_strategy
    strategy = await get_strategy(signal_type)
    if strategy is not None:
        if not strategy.enabled:
            return await _skip(
                BLOCK_STRATEGY_DISABLED, icon="🚫",
                audit_event="orb_blocked", action=ACTION_BLOCKED,
            )
        if strategy.phase == "shadow":
            return await _skip(
                BLOCK_STRATEGY_IN_SHADOW, icon="🚫",
                audit_event="orb_blocked", action=ACTION_BLOCKED,
            )
        if strategy.phase == "paper" and current_account_mode() == "live":
            return await _skip(
                BLOCK_PAPER_STRATEGY_ON_LIVE, icon="🚫",
                audit_event="orb_blocked", action=ACTION_BLOCKED,
            )

    # 2. Safeguards — position cap / daily loss / circuit breaker.
    ok, sg_reason = await _check_safeguards()
    if not ok:
        return await _skip(sg_reason, icon="🚫", audit_event="orb_blocked", action=ACTION_BLOCKED)

    # 3. Bar fetch with retry.
    orb_bar = await fetch_orb_bar_with_retry(ticker, today, strategy_label)
    if not orb_bar:
        return await _skip(
            f"{INFRA_NO_BAR}: {BAR_RETRY_MAX} retries exhausted",
            icon="⚠️",
        )
    try:
        await log_audit_event(
            "orb_bar_fetched",
            f"{strategy_label} {ticker} O={orb_bar['open']:.2f} "
            f"H={orb_bar['high']:.2f} L={orb_bar['low']:.2f} "
            f"range={orb_bar['high']-orb_bar['low']:.2f}",
        )
    except Exception:
        pass

    # 4. Fade guard.
    fade_ok, fade_reason = await check_fade_guard(ticker, orb_bar, fade_midpoint_ratio)
    if not fade_ok:
        return await _skip(fade_reason, audit_event="orb_faded")

    # 5. Strategy-specific spec build.
    order_spec, spec_reason = await spec_builder(alert_context, orb_bar, regime_record)
    if not order_spec:
        msg = spec_reason or "order spec failed"
        return await _skip(msg, audit_event="orb_skipped")

    # 6. Insert trade row.
    account_mode = current_account_mode()
    async with pool.acquire() as conn:
        trade_id = await conn.fetchval(
            """
            INSERT INTO mi_live_trades
                (ticker, alert_date, ep_score, catalyst_quality, gap_pct, regime,
                 status, orb_high, orb_low, atr_14,
                 entry_price, entry_shares, stop_price, hard_stop,
                 position_size, risk_dollars, signal_type, account_mode, proposed_at)
            VALUES ($1,$2,$3,$4,$5,$6,'pending_confirmation',$7,$8,$9,
                    $10,$11,$12,$12,$13,$14,$15,$16,NOW())
            ON CONFLICT (ticker, alert_date) DO NOTHING
            RETURNING id
            """,
            ticker, today,
            alert_context.get("ep_score", 0),
            alert_context.get("catalyst_quality"),
            alert_context.get("gap_pct"),
            regime_record.get("regime") if regime_record else None,
            order_spec["orb_high"], order_spec["orb_low"], atr_14,
            order_spec["entry_price"], float(order_spec["shares"]),
            order_spec["stop_loss_price"],
            order_spec["position_size"], order_spec["risk_dollars"],
            signal_type, account_mode,
        )
    if not trade_id:
        logger.debug(f"{strategy_label} {ticker}: trade row insert hit unique conflict")
        return {"ticker": ticker, "action": ACTION_SKIPPED, "reason": WINDOW_DUPLICATE}

    # 7. Submit bracket.
    is_paper = account_mode == "paper"

    if is_paper:
        logger.info(f"{strategy_label} paper auto-confirm: {ticker} (trade_id={trade_id})")
        async with pool.acquire() as conn:
            await conn.execute(
                "UPDATE mi_live_trades SET status='confirmed', confirmed_at=NOW() WHERE id=$1",
                trade_id,
            )
        order = await submit_entry(trade_id)
        if not order:
            logger.error(
                f"{strategy_label} {ticker}: submit_entry returned None "
                f"(trade_id={trade_id}) — check mi_live_trades.skip_reason"
            )
            try:
                await log_audit_event(
                    "orb_order_failed",
                    f"{strategy_label} {ticker} — submit_entry returned None "
                    f"(trade_id={trade_id})",
                )
            except Exception:
                pass
            await send_telegram_message(
                f"{mode_prefix()}⚠️ *{ticker}* {strategy_label} auto-enter failed — "
                f"check logs (trade_id={trade_id})"
            )
            return {"ticker": ticker, "action": ACTION_AUTO_ENTER_FAILED}

        try:
            await log_audit_event(
                "orb_order_placed",
                f"{strategy_label} {ticker} entry=${order_spec['entry_price']:.2f} "
                f"stop=${order_spec['stop_loss_price']:.2f} "
                f"shares={order_spec['shares']} "
                f"risk=${order_spec['risk_dollars']:.0f} trade_id={trade_id}",
            )
        except Exception:
            pass
        await send_telegram_message(
            f"{mode_prefix()}{success_icon} *{success_title}:* {ticker}\n"
            f"Stop-limit BUY @ ${order_spec['entry_price']:.2f} (pending trigger) | "
            f"{stop_label}: ${order_spec['stop_loss_price']:.2f}\n"
            f"Shares: {order_spec['shares']} | "
            f"Risk: ${order_spec['risk_dollars']:.0f}\n"
            f"_Fills if price ≥ ${order_spec['entry_price']:.2f}; cancels 10:00 ET if unfilled._"
        )
        return {"ticker": ticker, "action": ACTION_AUTO_ENTERED, "trade_id": trade_id}

    # Live (non-paper) — send Telegram proposal for manual confirmation.
    live_real_enabled = bool(strategy.live_real_enabled) if strategy else False
    sent = await send_trade_proposal(
        alert_context, order_spec, trade_id,
        live_real_enabled=live_real_enabled,
    )
    if sent:
        logger.info(f"{strategy_label} trade proposal sent: {ticker} (id={trade_id})")
        return {"ticker": ticker, "action": ACTION_PROPOSED, "trade_id": trade_id}
    await send_telegram_message(
        f"{mode_prefix()}⚠️ *{ticker}* {strategy_label} proposal send failed — "
        f"check logs (trade_id={trade_id})"
    )
    return {"ticker": ticker, "action": ACTION_PROPOSAL_SEND_FAILED}
