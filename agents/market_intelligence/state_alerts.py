"""
State-change alerts — detect meaningful changes in RS, themes, and technicals.

Fires after the nightly data pull, separate from evening briefing.
Alerts arrive ~4:30-5:00 PM ET via Telegram.

Noise thresholds:
- RS deterioration: drop > 15 points in ~10 trading days
- Theme transitions: only genuine stage changes (ticker-overlap matching to handle renames)
- MA breaks: RS >= 60, volume >= 1.5x ADV, only 20MA and 50MA
- Theme composition: only RS 70+ stocks joining/leaving
"""
from __future__ import annotations

import logging
from datetime import date, timedelta

from agents.market_intelligence.collector import et_today
from agents.market_intelligence.db import get_pool

logger = logging.getLogger(__name__)

# Minimum ticker overlap to consider two themes "the same" despite name differences
_THEME_MATCH_OVERLAP = 0.5  # 50% of tickers in common


async def _fetch_theme_pair(today: date) -> tuple[list[dict], list[dict]]:
    """Fetch today's and prior day's themes once for reuse across checks."""
    pool = await get_pool()
    async with pool.acquire() as conn:
        prior_date_row = await conn.fetchrow("""
            SELECT DISTINCT theme_date FROM mi_themes
            WHERE theme_date < $1
            ORDER BY theme_date DESC LIMIT 1
        """, today)
        if not prior_date_row:
            return [], []
        prior_date = prior_date_row["theme_date"]

        today_rows = await conn.fetch(
            "SELECT name, stage, tickers FROM mi_themes WHERE theme_date = $1", today
        )
        prior_rows = await conn.fetch(
            "SELECT name, stage, tickers FROM mi_themes WHERE theme_date = $1", prior_date
        )
    return [dict(r) for r in today_rows], [dict(r) for r in prior_rows]


async def detect_state_changes(
    trade_date: date | None = None,
) -> tuple[list[dict], list[dict], list[dict]]:
    """Compare today's state to prior.

    Returns (alerts, today_themes, prior_themes) — themes are cached for
    reuse by send_state_alerts() to avoid redundant DB fetches.
    """
    today = trade_date or et_today()
    alerts: list[dict] = []

    # Fetch theme data once for all theme-related checks
    today_themes, prior_themes = await _fetch_theme_pair(today)

    try:
        alerts.extend(await _check_rs_deterioration(today))
    except Exception as e:
        logger.error(f"RS deterioration check failed: {e}")

    try:
        alerts.extend(_check_theme_transitions(today_themes, prior_themes))
    except Exception as e:
        logger.error(f"Theme transition check failed: {e}")

    try:
        alerts.extend(await _check_ma_breaks(today))
    except Exception as e:
        logger.error(f"MA break check failed: {e}")

    try:
        alerts.extend(await _check_theme_composition(today, today_themes, prior_themes))
    except Exception as e:
        logger.error(f"Theme composition check failed: {e}")

    return alerts, today_themes, prior_themes


async def _check_rs_deterioration(today: date) -> list[dict]:
    """
    For active tracked stocks: compare today's rs_composite to 10 trading days ago.
    Alert if drop > 15 points.
    """
    pool = await get_pool()
    alerts = []

    async with pool.acquire() as conn:
        prior_date_row = await conn.fetchrow("""
            SELECT DISTINCT score_date FROM mi_stock_scores
            WHERE score_date <= $1 - INTERVAL '12 days'
              AND score_date >= $1 - INTERVAL '18 days'
            ORDER BY score_date DESC LIMIT 1
        """, today)
        if not prior_date_row:
            return []
        prior_date = prior_date_row["score_date"]

        tracked = await conn.fetch(
            "SELECT ticker FROM mi_tracked_stocks WHERE active = TRUE AND (quote_type IS NULL OR quote_type = 'EQUITY')"
        )
        if not tracked:
            return []
        tickers = [r["ticker"] for r in tracked]

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


def _match_themes_by_tickers(
    today_themes: list[dict],
    prior_themes: list[dict],
) -> dict[str, str]:
    """
    Match today's themes to prior themes by ticker overlap, not name.
    Returns {today_name: prior_name} for matched themes.
    Handles the theme engine renaming themes via Claude each day.
    """
    matches: dict[str, str] = {}
    used_prior: set[str] = set()

    for t in today_themes:
        today_tickers = set(t.get("tickers") or [])
        if not today_tickers:
            continue

        best_match = None
        best_overlap = 0.0

        for p in prior_themes:
            p_name = p["name"]
            if p_name in used_prior:
                continue
            prior_tickers = set(p.get("tickers") or [])
            if not prior_tickers:
                continue

            intersection = len(today_tickers & prior_tickers)
            # Overlap = fraction of the smaller set that's shared
            overlap = intersection / min(len(today_tickers), len(prior_tickers))

            if overlap > best_overlap:
                best_overlap = overlap
                best_match = p_name

        if best_match and best_overlap >= _THEME_MATCH_OVERLAP:
            matches[t["name"]] = best_match
            used_prior.add(best_match)

    return matches


def _check_theme_transitions(
    today_themes: list[dict], prior_themes: list[dict],
) -> list[dict]:
    """
    Compare today's themes to yesterday's using ticker-overlap matching.
    Only alert on genuine stage changes, not theme renames.
    """
    if not today_themes or not prior_themes:
        return []

    name_map = _match_themes_by_tickers(today_themes, prior_themes)
    prior_stage_map = {t["name"]: t["stage"] for t in prior_themes}
    alerts = []

    for t in today_themes:
        today_name = t["name"]
        matched_prior = name_map.get(today_name)
        if not matched_prior:
            continue

        prior_stage = prior_stage_map.get(matched_prior)
        if prior_stage and prior_stage != t["stage"]:
            alerts.append({
                "type": "theme_transition",
                "theme": today_name,
                "from_stage": prior_stage,
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
        prior_date_row = await conn.fetchrow("""
            SELECT DISTINCT score_date FROM mi_stock_scores
            WHERE score_date < $1
            ORDER BY score_date DESC LIMIT 1
        """, today)
        if not prior_date_row:
            return []
        prior_date = prior_date_row["score_date"]

        tracked = await conn.fetch(
            "SELECT ticker FROM mi_tracked_stocks WHERE active = TRUE AND (quote_type IS NULL OR quote_type = 'EQUITY')"
        )
        if not tracked:
            return []
        tickers = [r["ticker"] for r in tracked]

        today_data = await conn.fetch("""
            SELECT ticker, rs_composite, close, sma_20, sma_50, adv_20
            FROM mi_stock_scores
            WHERE score_date = $1 AND ticker = ANY($2)
              AND rs_composite >= 60
              AND close IS NOT NULL
        """, today, tickers)

        prior_data = await conn.fetch("""
            SELECT ticker, close, sma_20, sma_50
            FROM mi_stock_scores
            WHERE score_date = $1 AND ticker = ANY($2) AND close IS NOT NULL
        """, prior_date, tickers)
        prior_map = {r["ticker"]: dict(r) for r in prior_data}

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

            if vol_ratio < 1.5:
                continue

            for ma_col, ma_label in [("sma_20", "20MA"), ("sma_50", "50MA")]:
                today_ma = row[ma_col]
                prior_ma = prior.get(ma_col)
                prior_close = prior.get("close")

                if not today_ma or not prior_ma or not prior_close:
                    continue

                if prior_close >= prior_ma and close < today_ma:
                    alerts.append({
                        "type": "ma_break",
                        "ticker": ticker,
                        "ma": ma_label,
                        "rs": int(row["rs_composite"]),
                        "vol_ratio": round(vol_ratio, 1),
                    })

    return alerts


async def _check_theme_composition(
    today: date, today_themes: list[dict], prior_themes: list[dict],
) -> list[dict]:
    """
    For each theme on both today and yesterday:
    - Match themes by ticker overlap (handles renames)
    - Compare tickers[] arrays
    - Alert for RS 70+ stocks joining/leaving
    """
    if not today_themes or not prior_themes:
        return []

    name_map = _match_themes_by_tickers(today_themes, prior_themes)
    prior_ticker_map = {t["name"]: set(t.get("tickers") or []) for t in prior_themes}

    # Get RS scores for filtering
    all_tickers = set()
    for t in today_themes:
        all_tickers.update(t.get("tickers") or [])
    for tks in prior_ticker_map.values():
        all_tickers.update(tks)

    if not all_tickers:
        return []

    pool = await get_pool()
    async with pool.acquire() as conn:
        rs_rows = await conn.fetch("""
            SELECT ticker, rs_composite FROM mi_stock_scores
            WHERE score_date = $1 AND ticker = ANY($2) AND rs_composite IS NOT NULL
        """, today, list(all_tickers))
    rs_map = {r["ticker"]: r["rs_composite"] for r in rs_rows}

    alerts = []
    for t in today_themes:
        today_name = t["name"]
        matched_prior = name_map.get(today_name)
        if not matched_prior:
            continue

        today_set = set(t.get("tickers") or [])
        prior_set = prior_ticker_map.get(matched_prior, set())

        added = today_set - prior_set
        removed = prior_set - today_set

        added_strong = [tk for tk in added if rs_map.get(tk, 0) >= 70]
        removed_strong = [tk for tk in removed if rs_map.get(tk, 0) >= 70]

        if added_strong or removed_strong:
            alerts.append({
                "type": "theme_composition",
                "theme": today_name,
                "added": sorted(added_strong),
                "removed": sorted(removed_strong),
            })

    return alerts


async def send_state_alerts(
    alerts: list[dict],
    theme_changelog: list[dict] | None = None,
    today_themes: list[dict] | None = None,
    prior_themes: list[dict] | None = None,
) -> None:
    """Format alerts + theme changelog into Telegram message.

    Filters changelog to suppress noise from theme renames:
    - Pruned/assigned only shown if the stock actually changed themes (not just a rename)
    - New/retired themes only shown if they have no high-overlap match with prior day
    """
    from agents.market_intelligence.briefing import send_telegram_message

    theme_changelog = theme_changelog or []

    if not alerts and not theme_changelog:
        return

    # Detect theme renames from cached data (or fetch if not provided)
    if today_themes is not None and prior_themes is not None:
        renamed_themes = _match_themes_by_tickers(today_themes, prior_themes)
    else:
        renamed_themes = await _get_renamed_themes()

    lines = ["*STATE CHANGES*"]

    # Group alerts by type
    rs_alerts = [a for a in alerts if a["type"] == "rs_deterioration"]
    theme_alerts = [a for a in alerts if a["type"] == "theme_transition"]
    ma_alerts = [a for a in alerts if a["type"] == "ma_break"]
    comp_alerts = [a for a in alerts if a["type"] == "theme_composition"]

    # Group changelog by type — filter out rename noise
    all_renamed_names = set(renamed_themes.keys()) | set(renamed_themes.values())

    pruned = [c for c in theme_changelog if c["type"] == "ticker_pruned"
              and c.get("theme") not in all_renamed_names]
    assigned = [c for c in theme_changelog if c["type"] == "ticker_assigned"
                and c.get("theme") not in all_renamed_names]
    new_themes = [c for c in theme_changelog if c["type"] == "theme_new"
                  and c.get("theme") not in renamed_themes]
    retired_themes = [c for c in theme_changelog if c["type"] == "theme_retired"
                      and c.get("theme") not in renamed_themes.values()]

    # Dedup: remove tickers from composition alerts already in changelog
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
        _stage_rank = {"Fading": 0, "Nascent": 1, "Mainstream": 2, "Accelerating": 3}
        positive = [a for a in theme_alerts if _stage_rank.get(a["to_stage"], 0) > _stage_rank.get(a["from_stage"], 0)]
        negative = [a for a in theme_alerts if _stage_rank.get(a["to_stage"], 0) < _stage_rank.get(a["from_stage"], 0)]

        lines.append("")
        lines.append("⚡ *Theme Transitions*")
        if positive:
            lines.append("_Improving_")
            for a in positive[:10]:
                lines.append(f"  {a['theme']}: {a['from_stage']} → {a['to_stage']}")
        if negative:
            if positive:
                lines.append("")
            lines.append("_Deteriorating_")
            for a in negative[:10]:
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

    # Only send if there's actual content beyond the header
    if len(lines) <= 1:
        logger.info("State changes: all filtered as rename noise, nothing to send")
        return

    text = "\n".join(lines)
    await send_telegram_message(text)
    logger.info(f"Sent {len(alerts) + len(theme_changelog)} state-change alerts")


async def _get_renamed_themes() -> dict[str, str]:
    """Get {today_name: prior_name} for themes that were just renamed (high ticker overlap).
    Used to suppress noise in changelog."""
    today = et_today()
    pool = await get_pool()
    async with pool.acquire() as conn:
        prior_date_row = await conn.fetchrow("""
            SELECT DISTINCT theme_date FROM mi_themes
            WHERE theme_date < $1
            ORDER BY theme_date DESC LIMIT 1
        """, today)
        if not prior_date_row:
            return {}
        prior_date = prior_date_row["theme_date"]

        today_themes = await conn.fetch(
            "SELECT name, tickers FROM mi_themes WHERE theme_date = $1", today
        )
        prior_themes = await conn.fetch(
            "SELECT name, tickers FROM mi_themes WHERE theme_date = $1", prior_date
        )

    return _match_themes_by_tickers(
        [dict(r) for r in today_themes],
        [dict(r) for r in prior_themes],
    )
