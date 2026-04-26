"""Telegram surfaces for /crypto and /altseason — gated by CRYPTO_RS_ENABLED.

Shadow mode (default): all formatters return a "shadow mode" message.
Live mode (flag=true): full briefings with current RS rankings, BTC.D arrow,
trigger status.

All Telegram sends route through the existing send_telegram_message helper
so failure handling matches the equity-side conventions.
"""
from __future__ import annotations

import logging
from datetime import date, timedelta
from typing import Optional

from agents.market_intelligence.constants import CRYPTO_RS_ENABLED
from agents.market_intelligence.briefing import send_telegram_message
from agents.market_intelligence.db import get_pool, log_audit_event

logger = logging.getLogger(__name__)


SHADOW_MESSAGE = (
    "🔬 *Crypto RS — shadow mode*\n\n"
    "Data is being collected nightly but Telegram surfaces are disabled.\n"
    "Flip `CRYPTO_RS_ENABLED=true` in env + restart market agent to activate."
)


async def render_crypto_top(category: Optional[str] = None, limit: int = 10) -> str:
    """Top RS-vs-BTC list, optionally filtered by category."""
    if not CRYPTO_RS_ENABLED:
        return SHADOW_MESSAGE

    pool = await get_pool()
    async with pool.acquire() as conn:
        # Latest score date
        latest = await conn.fetchval("SELECT MAX(score_date) FROM crypto_rs_scores")
        if latest is None:
            return "_No crypto RS data yet — first ingest pending._"

        if category:
            rows = await conn.fetch(
                """
                SELECT u.symbol, s.rs_overall, s.rs_in_bucket, s.mcap_bucket
                FROM crypto_rs_scores s
                JOIN crypto_universe u ON u.coin_id = s.coin_id
                JOIN crypto_categories c ON c.coin_id = s.coin_id
                WHERE s.score_date = $1
                  AND c.category_slug = $2
                  AND s.rs_overall IS NOT NULL
                ORDER BY s.rs_overall DESC
                LIMIT $3
                """,
                latest, category.lower(), limit,
            )
        else:
            rows = await conn.fetch(
                """
                SELECT u.symbol, s.rs_overall, s.rs_in_bucket, s.mcap_bucket
                FROM crypto_rs_scores s
                JOIN crypto_universe u ON u.coin_id = s.coin_id
                WHERE s.score_date = $1 AND s.rs_overall IS NOT NULL
                ORDER BY s.rs_overall DESC
                LIMIT $2
                """,
                latest, limit,
            )
        btc_d_row = await conn.fetchrow(
            "SELECT dominance_pct FROM crypto_btc_dominance "
            "WHERE date = $1",
            latest,
        )

    if not rows:
        return f"_No coins matched (category={category})._"

    header = f"*Crypto RS · top {limit}{' · ' + category if category else ''}*"
    if btc_d_row and btc_d_row["dominance_pct"]:
        header += f"  ·  BTC.D *{float(btc_d_row['dominance_pct']):.1f}%*"

    body_lines = ["```"]
    body_lines.append(f"{'#':<3}{'SYM':<10}{'RS':>6} {'BUCKET':>10} {'BUCK_RS':>8}")
    for i, r in enumerate(rows, start=1):
        rs = float(r["rs_overall"]) if r["rs_overall"] is not None else 0.0
        bucket_rs = float(r["rs_in_bucket"]) if r["rs_in_bucket"] is not None else 0.0
        body_lines.append(
            f"{i:<3}{(r['symbol'] or '?'):<10}{rs:>6.1f} {r['mcap_bucket']:>10} {bucket_rs:>8.1f}"
        )
    body_lines.append("```")
    body_lines.append(f"_data: {latest}_")
    return f"{header}\n\n" + "\n".join(body_lines)


async def render_alt_season_status() -> str:
    """`/altseason` output — three-signal status + trigger state."""
    if not CRYPTO_RS_ENABLED:
        return SHADOW_MESSAGE

    pool = await get_pool()
    async with pool.acquire() as conn:
        btc = await conn.fetchrow(
            "SELECT date, dominance_pct FROM crypto_btc_dominance "
            "ORDER BY date DESC LIMIT 1"
        )
        total3 = await conn.fetchrow(
            "SELECT date, total3_mcap_usd FROM crypto_total3 "
            "ORDER BY date DESC LIMIT 1"
        )
        stable = await conn.fetchrow(
            "SELECT date, total_stable_mcap FROM crypto_stablecoin_flows "
            "ORDER BY date DESC LIMIT 1"
        )
        last_alert = await conn.fetchrow(
            "SELECT triggered_at, cooldown_until FROM crypto_dominance_alerts "
            "ORDER BY triggered_at DESC LIMIT 1"
        )

    parts = ["*Alt-season trigger status*\n"]
    parts.append("```")
    if btc:
        parts.append(f"BTC.D       : {float(btc['dominance_pct']):.2f}% (as of {btc['date']})")
    if total3:
        parts.append(f"TOTAL3      : ${float(total3['total3_mcap_usd']):,.0f} (as of {total3['date']})")
    if stable:
        parts.append(f"Stables tot : ${float(stable['total_stable_mcap']):,.0f} (as of {stable['date']})")
    parts.append("```")

    from datetime import datetime
    from zoneinfo import ZoneInfo
    et = ZoneInfo("America/New_York")
    if last_alert:
        triggered_et = last_alert["triggered_at"].astimezone(et).date()
        cu = last_alert["cooldown_until"]
        if cu and cu > datetime.now(et):
            parts.append(f"\n_Last alert: {triggered_et}; cooldown active until {cu.astimezone(et).date()}._")
        else:
            parts.append(f"\n_Last alert: {triggered_et}; cooldown expired — armed._")
    else:
        parts.append("\n_No alerts yet; trigger armed._")

    return "\n".join(parts)


async def send_alt_season_alert(trigger_result: dict, today: date) -> None:
    """Fire the alt-season Telegram alert. Called only when CRYPTO_RS_ENABLED=true
    AND all three signals fire AND cooldown clear."""
    s = trigger_result["signals"]
    msg_lines = [
        "🚨 *ALT-SEASON TRIGGER FIRED*",
        "",
        "All three signals confirm capital rotation into the long tail.",
        "",
        "```",
        f"Stable mcap slope (30d): {s['stable_slope_positive']['slope']:.2e}  ✅",
        f"BTC.D                  : {s['btc_dominance_breakdown']['current_pct']:.2f}% "
        f"(slope {s['btc_dominance_breakdown']['slope']:.4f}, "
        f"{s['btc_dominance_breakdown']['persistence_days']}d persistence)  ✅",
        f"TOTAL3                 : ${s['total3_breakout']['current']:,.0f} "
        f"vs SMA90 ${s['total3_breakout']['sma_90d']:,.0f}  ✅",
        "```",
        "",
        f"_date: {today}; cooldown 30d_",
    ]
    sent = await send_telegram_message("\n".join(msg_lines))
    if not sent:
        await log_audit_event(
            "crypto_alert_send_failed",
            "alt-season Telegram alert failed to send",
            "",
        )
        return

    # Attach top-10 RS list as follow-up message
    top = await render_crypto_top(limit=10)
    await send_telegram_message(top)
