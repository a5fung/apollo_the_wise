"""
State-change alerts — detect meaningful changes in RS, themes, and technicals.

Fires after the nightly data pull, separate from evening briefing.
Alerts arrive ~4:30-5:00 PM ET via Telegram.

Noise thresholds:
- RS deterioration: drop > 15 points in ~10 trading days
- Theme transitions: all stage changes (limited count, not noisy)
- MA breaks: RS >= 60, volume >= 1.5x ADV, only 20MA and 50MA
- Theme composition: only RS 70+ stocks joining/leaving
"""
from __future__ import annotations

import logging
from datetime import date, timedelta

from agents.market_intelligence.db import get_pool

logger = logging.getLogger(__name__)


async def detect_state_changes(trade_date: date | None = None) -> list[dict]:
    """Compare today's state to prior. Returns alert dicts."""
    today = trade_date or date.today()
    alerts: list[dict] = []

    try:
        alerts.extend(await _check_rs_deterioration(today))
    except Exception as e:
        logger.error(f"RS deterioration check failed: {e}")

    try:
        alerts.extend(await _check_theme_transitions(today))
    except Exception as e:
        logger.error(f"Theme transition check failed: {e}")

    try:
        alerts.extend(await _check_ma_breaks(today))
    except Exception as e:
        logger.error(f"MA break check failed: {e}")

    try:
        alerts.extend(await _check_theme_composition(today))
    except Exception as e:
        logger.error(f"Theme composition check failed: {e}")

    return alerts


async def _check_rs_deterioration(today: date) -> list[dict]:
    """
    For active tracked stocks: compare today's rs_composite to 10 trading days ago.
    Alert if drop > 15 points.
    """
    pool = await get_pool()
    alerts = []

    async with pool.acquire() as conn:
        # Find score date ~10 trading days ago
        prior_date_row = await conn.fetchrow("""
            SELECT DISTINCT score_date FROM mi_stock_scores
            WHERE score_date <= $1 - INTERVAL '12 days'
              AND score_date >= $1 - INTERVAL '18 days'
            ORDER BY score_date DESC LIMIT 1
        """, today)
        if not prior_date_row:
            return []
        prior_date = prior_date_row["score_date"]

        # Get active tracked tickers
        tracked = await conn.fetch(
            "SELECT ticker FROM mi_tracked_stocks WHERE active = TRUE"
        )
        if not tracked:
            return []
        tickers = [r["ticker"] for r in tracked]

        # Get today's and prior RS for tracked stocks
        today_scores = await conn.fetch("""
            SELECT ticker, rs_composite FROM mi_stock_scores
            WHERE score_date = $1 AND ticker = ANY($2) AND rs_composite IS NOT NULL
        """, today, tickers)
        today_map = {r["ticker"]: r["rs_composite"] for r in today_scores}

        prior_scores = await conn.fetch("""
            SELECT ticker, rs_composite FROM mi_stock_scores
            WHERE score_date = $1 AND ticker = ANY($2) AND rs_composite IS NOT NULL
        """, prior_date, tickers)
        prior_map = {r["ticker"]: r["rs_composite"] for r in prior_scores}

        for ticker in tickers:
            if ticker in today_map and ticker in prior_map:
                drop = prior_map[ticker] - today_map[ticker]
                if drop > 15:
                    alerts.append({
                        "type": "rs_deterioration",
                        "ticker": ticker,
                        "rs_now": int(today_map[ticker]),
                        "rs_prior": int(prior_map[ticker]),
                        "drop": int(drop),
                    })

    return alerts


async def _check_theme_transitions(today: date) -> list[dict]:
    """
    Compare today's themes to yesterday's by name.
    Alert on any stage change.
    """
    pool = await get_pool()
    alerts = []

    async with pool.acquire() as conn:
        # Find yesterday's theme date
        prior_date_row = await conn.fetchrow("""
            SELECT DISTINCT theme_date FROM mi_themes
            WHERE theme_date < $1
            ORDER BY theme_date DESC LIMIT 1
        """, today)
        if not prior_date_row:
            return []
        prior_date = prior_date_row["theme_date"]

        today_themes = await conn.fetch(
            "SELECT name, stage FROM mi_themes WHERE theme_date = $1", today
        )
        prior_themes = await conn.fetch(
            "SELECT name, stage FROM mi_themes WHERE theme_date = $1", prior_date
        )

        prior_map = {r["name"]: r["stage"] for r in prior_themes}

        for t in today_themes:
            name = t["name"]
            if name in prior_map and prior_map[name] != t["stage"]:
                alerts.append({
                    "type": "theme_transition",
                    "theme": name,
                    "from_stage": prior_map[name],
                    "to_stage": t["stage"],
                })

    return alerts


async def _check_ma_breaks(today: date) -> list[dict]:
    """
    For active tracked stocks with RS >= 60:
    - Today: close < sma_20 (or sma_50)
    - Yesterday: close >= sma_20 (or sma_50) — broke TODAY
    - Volume today > 1.5x ADV-20
    """
    pool = await get_pool()
    alerts = []

    async with pool.acquire() as conn:
        # Find yesterday's score date
        prior_date_row = await conn.fetchrow("""
            SELECT DISTINCT score_date FROM mi_stock_scores
            WHERE score_date < $1
            ORDER BY score_date DESC LIMIT 1
        """, today)
        if not prior_date_row:
            return []
        prior_date = prior_date_row["score_date"]

        # Get active tracked tickers with RS >= 60
        tracked = await conn.fetch(
            "SELECT ticker FROM mi_tracked_stocks WHERE active = TRUE"
        )
        if not tracked:
            return []
        tickers = [r["ticker"] for r in tracked]

        # Today's data
        today_data = await conn.fetch("""
            SELECT ticker, rs_composite, close, sma_20, sma_50, adv_20
            FROM mi_stock_scores
            WHERE score_date = $1 AND ticker = ANY($2)
              AND rs_composite >= 60
              AND close IS NOT NULL
        """, today, tickers)

        # Yesterday's data
        prior_data = await conn.fetch("""
            SELECT ticker, close, sma_20, sma_50
            FROM mi_stock_scores
            WHERE score_date = $1 AND ticker = ANY($2) AND close IS NOT NULL
        """, prior_date, tickers)
        prior_map = {r["ticker"]: dict(r) for r in prior_data}

        # Today's volume from mi_daily_closes
        today_vol = await conn.fetch("""
            SELECT ticker, volume FROM mi_daily_closes
            WHERE trade_date = $1 AND ticker = ANY($2) AND volume > 0
        """, today, tickers)
        vol_map = {r["ticker"]: r["volume"] for r in today_vol}

        for row in today_data:
            ticker = row["ticker"]
            close = row["close"]
            prior = prior_map.get(ticker)
            if not prior:
                continue

            adv = row["adv_20"] or 0
            today_volume = vol_map.get(ticker, 0)
            vol_ratio = today_volume / adv if adv > 0 else 0

            # Only alert if volume is significant
            if vol_ratio < 1.5:
                continue

            for ma_col, ma_label in [("sma_20", "20MA"), ("sma_50", "50MA")]:
                today_ma = row[ma_col]
                prior_ma = prior.get(ma_col)
                prior_close = prior.get("close")

                if not today_ma or not prior_ma or not prior_close:
                    continue

                # Broke today: was above, now below
                if prior_close >= prior_ma and close < today_ma:
                    alerts.append({
                        "type": "ma_break",
                        "ticker": ticker,
                        "ma": ma_label,
                        "rs": int(row["rs_composite"]),
                        "vol_ratio": round(vol_ratio, 1),
                    })

    return alerts


async def _check_theme_composition(today: date) -> list[dict]:
    """
    For each theme on both today and yesterday:
    - Compare tickers[] arrays
    - Alert for RS 70+ stocks joining/leaving
    """
    pool = await get_pool()
    alerts = []

    async with pool.acquire() as conn:
        prior_date_row = await conn.fetchrow("""
            SELECT DISTINCT theme_date FROM mi_themes
            WHERE theme_date < $1
            ORDER BY theme_date DESC LIMIT 1
        """, today)
        if not prior_date_row:
            return []
        prior_date = prior_date_row["theme_date"]

        today_themes = await conn.fetch(
            "SELECT name, tickers FROM mi_themes WHERE theme_date = $1", today
        )
        prior_themes = await conn.fetch(
            "SELECT name, tickers FROM mi_themes WHERE theme_date = $1", prior_date
        )
        prior_map = {r["name"]: set(r["tickers"] or []) for r in prior_themes}

        # Get RS scores for filtering (only alert on RS 70+ stocks)
        all_tickers = set()
        for t in today_themes:
            all_tickers.update(t["tickers"] or [])
        for tks in prior_map.values():
            all_tickers.update(tks)

        if not all_tickers:
            return []

        rs_rows = await conn.fetch("""
            SELECT ticker, rs_composite FROM mi_stock_scores
            WHERE score_date = $1 AND ticker = ANY($2) AND rs_composite IS NOT NULL
        """, today, list(all_tickers))
        rs_map = {r["ticker"]: r["rs_composite"] for r in rs_rows}

        for t in today_themes:
            name = t["name"]
            if name not in prior_map:
                continue

            today_set = set(t["tickers"] or [])
            prior_set = prior_map[name]

            added = today_set - prior_set
            removed = prior_set - today_set

            # Filter to RS 70+ only
            added_strong = [tk for tk in added if rs_map.get(tk, 0) >= 70]
            removed_strong = [tk for tk in removed if rs_map.get(tk, 0) >= 70]

            if added_strong or removed_strong:
                alerts.append({
                    "type": "theme_composition",
                    "theme": name,
                    "added": sorted(added_strong),
                    "removed": sorted(removed_strong),
                })

    return alerts


async def send_state_alerts(
    alerts: list[dict],
    theme_changelog: list[dict] | None = None,
) -> None:
    """Format alerts + theme changelog into Telegram message."""
    from agents.market_intelligence.briefing import send_telegram_message

    theme_changelog = theme_changelog or []

    if not alerts and not theme_changelog:
        return

    lines = ["*STATE CHANGES*"]

    # Group alerts by type
    rs_alerts = [a for a in alerts if a["type"] == "rs_deterioration"]
    theme_alerts = [a for a in alerts if a["type"] == "theme_transition"]
    ma_alerts = [a for a in alerts if a["type"] == "ma_break"]
    comp_alerts = [a for a in alerts if a["type"] == "theme_composition"]

    # Group changelog by type
    pruned = [c for c in theme_changelog if c["type"] == "ticker_pruned"]
    assigned = [c for c in theme_changelog if c["type"] == "ticker_assigned"]
    new_themes = [c for c in theme_changelog if c["type"] == "theme_new"]
    retired_themes = [c for c in theme_changelog if c["type"] == "theme_retired"]

    # Dedup: remove tickers from composition alerts that are already in changelog
    changelog_tickers = set()
    for c in pruned:
        changelog_tickers.add((c["theme"], c["ticker"], "removed"))
    for c in assigned:
        changelog_tickers.add((c["theme"], c["ticker"], "added"))

    if comp_alerts:
        deduped_comp = []
        for a in comp_alerts:
            added = [tk for tk in a.get("added", [])
                     if (a["theme"], tk, "added") not in changelog_tickers]
            removed = [tk for tk in a.get("removed", [])
                       if (a["theme"], tk, "removed") not in changelog_tickers]
            if added or removed:
                deduped_comp.append({**a, "added": added, "removed": removed})
        comp_alerts = deduped_comp

    # --- Render sections ---

    if theme_alerts:
        lines.append("")
        lines.append("⚡ *Theme Transitions*")
        for a in theme_alerts[:10]:
            lines.append(f"  {a['theme']}: {a['from_stage']} → {a['to_stage']}")

    if assigned:
        lines.append("")
        lines.append("➕ *Stocks Added to Themes*")
        for a in assigned[:10]:
            lines.append(f"  {a['ticker']} → {a['theme']}")
            if a.get("rationale"):
                lines.append(f"    _{a['rationale']}_")

    if pruned:
        lines.append("")
        lines.append("✂️ *Stocks Pruned from Themes*")
        for a in pruned[:10]:
            lines.append(f"  {a['ticker']} from {a['theme']} (RS {a['rs']:.0f})")

    if new_themes:
        lines.append("")
        lines.append("🆕 *New Themes*")
        for a in new_themes[:10]:
            lines.append(f"  {a['theme']}: {', '.join(a.get('tickers', []))}")

    if retired_themes:
        lines.append("")
        lines.append("🪦 *Themes Retired*")
        for a in retired_themes[:10]:
            lines.append(f"  {a['theme']}")

    if rs_alerts:
        lines.append("")
        lines.append("📉 *RS Deterioration*")
        for a in rs_alerts[:10]:
            lines.append(
                f"  {a['ticker']}: RS {a['rs_prior']} → {a['rs_now']} (-{a['drop']} in 2wk)"
            )

    if ma_alerts:
        lines.append("")
        lines.append("🔻 *MA Breaks*")
        for a in ma_alerts[:10]:
            lines.append(
                f"  {a['ticker']}: broke {a['ma']} on {a['vol_ratio']}x vol (RS {a['rs']})"
            )

    if comp_alerts:
        lines.append("")
        lines.append("🔄 *Theme Composition*")
        for a in comp_alerts[:10]:
            parts = []
            if a["added"]:
                parts.append("+" + " +".join(a["added"]))
            if a["removed"]:
                parts.append("-" + " -".join(a["removed"]))
            lines.append(f"  {a['theme']}: {' '.join(parts)}")

    text = "\n".join(lines)
    await send_telegram_message(text)
    logger.info(f"Sent {len(alerts) + len(theme_changelog)} state-change alerts")
