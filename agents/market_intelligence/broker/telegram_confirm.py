"""
Staged-trade FYI proposals via Telegram.

#364 (operator-decided 2026-07-03): the [Confirm]/[Skip] inline buttons and their
callback machinery are REMOVED — review finding F17 proved the flow structurally
broken under the HTTP split (the button press executed on a creds-less container
and flipped status→'confirmed' BEFORE submit → permanent wedge; it never worked
in prod). The proposal message stays as a pure FYI for the live+live_real_enabled=False
phase; the row stays 'pending_confirmation' (inert — nothing can auto-submit it).
If a staged/manual-confirm phase is ever wanted again, it needs a real routing
design first (the W2-step-5 deferral) AND submit-before-flip ordering.

Uses Telegram Bot API directly via httpx (same pattern as send_telegram_message).
"""
from __future__ import annotations

import logging
import os

import httpx

logger = logging.getLogger(__name__)


async def send_trade_proposal(
    alert: dict,
    order_spec: dict,
    trade_id: int,
    *,
    live_real_enabled: bool = False,
) -> bool:
    """
    Send a staged-trade FYI proposal to Telegram (no buttons — #364).
    Returns True if message was sent successfully.

    When account_mode='live' AND live_real_enabled=False, the header shows the
    STAGED-PAPER banner: the strategy hasn't been promoted to real-$, nothing
    auto-submits, and there is NO in-chat confirm — arming real money is the
    operator's SQL flip per the runbook (live_real_enabled=TRUE + restart).
    """
    ticker = order_spec["ticker"]
    entry = order_spec["entry_price"]
    stop = order_spec["stop_loss_price"]
    risk = order_spec["risk_dollars"]
    shares = order_spec["shares"]
    score = order_spec.get("ep_score", 0)
    # Sanitize the rubric grade: "game_changer" etc. carry "_" which Markdown reads as italic →
    # an unclosed entity → Telegram 400 (the parse-fragility class; SNX 6/25 trade #234).
    catalyst = (alert.get("catalyst_quality") or "N/A").replace("_", " ")
    gap = alert.get("gap_pct", 0)
    regime = order_spec.get("regime", "Unknown")
    # Show risk as % only — don't leak account equity
    equity = order_spec.get("equity", 0)
    risk_pct = (risk / equity * 100) if equity else 0

    from agents.market_intelligence.constants import current_account_mode, mode_prefix
    if current_account_mode() == "live" and not live_real_enabled:
        header = f"🟡 *STAGED-PAPER (not armed — no auto-submit):* {ticker}"
    else:
        header = f"{mode_prefix()}📊 *TRADE PROPOSAL (FYI): {ticker}*"
    # Theme membership (C8, 2026-05-19) — surface on the proposal FYI.
    # Pradeep #1 catalyst type; decision-support for the operator's read.
    theme_line = ""
    try:
        from agents.market_intelligence.catalyst_rubric_runtime import (
            get_theme_membership, format_theme_for_telegram,
        )
        _theme = await get_theme_membership(ticker)
        theme_line = "\n" + format_theme_for_telegram(_theme)
    except Exception as _te:
        logger.debug(f"trade proposal theme lookup failed for {ticker}: {_te}")

    text = (
        f"{header}\n"
        f"Entry: ${entry:.2f} (ORB high)\n"
        f"Stop: ${stop:.2f} (ORB low)\n"
        f"Risk: ${risk:.0f} ({risk_pct:.1f}% of account)\n"
        f"Shares: {shares}\n"
        f"Score: {score:.0f} | Catalyst: {catalyst}\n"
        f"Gap: {gap:.1f}% | Regime: {regime}"
        f"{theme_line}"
    )

    bot_token = os.environ.get("TELEGRAM_BOT_TOKEN")
    allowed = os.environ.get("TELEGRAM_ALLOWED_USER_IDS", "")
    chat_id = int(allowed.split(",")[0].strip())

    async def _post(parse_mode: "str | None") -> None:
        payload = {
            "chat_id": chat_id,
            "text": text,
            "disable_web_page_preview": True,
        }
        if parse_mode:
            payload["parse_mode"] = parse_mode
        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.post(
                f"https://api.telegram.org/bot{bot_token}/sendMessage", json=payload
            )
            resp.raise_for_status()

    try:
        await _post("Markdown")
        logger.info(f"Trade proposal sent: {ticker} (trade_id={trade_id})")
        return True
    except Exception as e:
        # Markdown can 400 on an unescaped char in a dynamic field (SNX 6/25 trade #234 —
        # "game_changer" underscore → "can't find end of entity"). A live-trade proposal MUST
        # reach the operator, so retry PLAIN TEXT before giving up.
        logger.warning(f"Trade proposal Markdown send failed for {ticker} ({e}) — retrying plain text")
        try:
            await _post(None)
            logger.info(f"Trade proposal sent (plain-text fallback): {ticker} (trade_id={trade_id})")
            return True
        except Exception as e2:
            logger.error(f"Failed to send trade proposal for {ticker} (markdown + plain): {e2}")
            return False
