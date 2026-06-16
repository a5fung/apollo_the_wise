"""`/ideas` — the unified trade-ideas front door.

"Stocks in Play" = ONE curated list of the **best actionable ideas right now**: the
matured/tradeable names across every detector, consolidated, deduped per ticker (combined
setup tags), and priority-ranked. The per-strategy drill-down buttons + the edit-in-place
← back nav live in channels/telegram.py (orchestrator); this module owns only the TEXT.

What "Stocks in Play" is NOT (operator 2026-06-16): the raw universe/watchlist. The
sugar-baby cohort is the Pradeep 9M *universe to watch* ("9M = universe, not entry"), so it
is NOT "in play" — it drops to a one-line `/sugarbabies` pointer, never the actionable list.

TRANSITIONAL: the actionable ideas are read-time-consolidated from the per-detector getters
here, until ADR-0004 #292 migrates each detector into mi_stocks_in_play with an
actionability class — then "Stocks in Play" ranks the substrate rows directly and the getter
calls drop out. Ranking is sort-by-tier only (no numeric score — sample-size discipline).

Kept light (no heavy imports at module top) so render_ideas_summary is unit-testable without
a DB. Only CAPS-safe tickers + fixed setup tags are emitted — never a raw source_detector
(underscores desync Telegram Markdown); reason-derived tags are underscore-stripped.
"""
from __future__ import annotations

_SEP = "━━━━━━━━━━━━━━━━━━━━━"


def render_ideas_summary(*, today, sip_rows, magna53, ninem_day2, flags, fishhook) -> str:
    """Pure /ideas summary. All list args may be None (a failed/again getter)."""
    lines = [f"💡 *Apollo Ideas* — {today.strftime('%a %b %d')}", _SEP]

    # ── consolidate the best ACTIONABLE ideas: ticker → [best_tier, [tags]] ──
    # tier 0 strongest. Dedup combines setup tags + keeps the strongest tier (a name that's
    # both a MAGNA53 HIGH and a 9M shows once, ranked by the HIGH).
    ideas: dict[str, list] = {}

    def _add(ticker, tier, tag):
        if not ticker:
            return
        cur = ideas.get(ticker)
        if cur is None:
            ideas[ticker] = [tier, [tag]]
        else:
            cur[0] = min(cur[0], tier)
            if tag not in cur[1]:
                cur[1].append(tag)

    # EP catalyst (MAGNA53) — HIGH is the strongest actionable signal
    for a in (magna53 or []):
        if a.get("score_tier") == "HIGH":
            _add(a.get("ticker"), 0, "MAGNA53 HIGH")
        elif a.get("score_tier") == "MODERATE":
            _add(a.get("ticker"), 4, "MAGNA53 mod")
    # 9M Day-2 = the CONFIRMED breakout ORB candidate — a real setup (small list). Raw 9M
    # intraday alerts are the UNIVERSE ("9M = universe, not entry"), ~50/day — they are NOT
    # actionable and live behind the 🏦 9M drill-down button, never this curated list.
    for a in (ninem_day2 or []):
        _add(a.get("ticker"), 1, "9M Day2")
    # Continuation flags — TRIGGERED/COILED are actionable; TIGHTENING/WATCH still forming
    for r in (flags or []):
        if r.get("stage") == "TRIGGERED":
            _add(r.get("ticker"), 1, "flag triggered")
        elif r.get("stage") == "COILED":
            _add(r.get("ticker"), 2, "flag coiled")
    # Fishhook — active open anchors
    for r in (fishhook or []):
        if r.get("state") in ("pending", "promoted", "reclaimed"):
            _add(r.get("ticker"), 3, "fishhook")
    # Substrate rows (anticipation etc.): actionable tiers only; informational = universe
    universe = set()
    for r in (sip_rows or []):
        cls = r.get("automation_class")
        if cls in ("apollo_eligible", "operator_only"):
            tag = (r.get("reason") or "setup").split("—")[0].strip().replace("_", " ")
            _add(r.get("ticker"), 0 if cls == "apollo_eligible" else 2, tag)
        elif r.get("ticker"):
            universe.add(r["ticker"])

    ranked = sorted(ideas.items(), key=lambda kv: (kv[1][0], kv[0]))
    lines.append(f"🎯 *Stocks in Play* — best actionable now ({len(ranked)})")
    if ranked:
        for ticker, (_tier, tags) in ranked[:12]:
            lines.append(f"  `{ticker}` {' · '.join(tags)}")
        if len(ranked) > 12:
            lines.append(f"  _…+{len(ranked) - 12} more_")
    else:
        lines.append("  _nothing actionable right now — check back as setups mature_")
    if universe:
        lines.append(f"  _universe: {len(universe)} on the watchlist → /sugarbabies_")
    lines.append(_SEP)
    lines.append("_Tap a strategy below for its full board · SHADOW where noted_")
    return "\n".join(lines)


async def build_ideas_text() -> str:
    """Fetch each surface fail-open (a single bad getter never blanks the board) and render
    the consolidated actionable list. Detector getters are read-time-consolidated until
    ADR-0004 #292 migrates them into the substrate."""
    import asyncio as _aio
    from agents.market_intelligence.collector import (
        et_today, prev_trading_days, last_trading_day,
    )
    from agents.market_intelligence.db import (
        get_stocks_in_play, get_today_ep_alerts,
        get_all_9m_sugar_babies, get_fishhook_outcomes_window,
    )
    from agents.market_intelligence.flag_detector import get_flag_watchlist

    today = et_today()
    query_str = last_trading_day(today).isoformat()
    yesterday = prev_trading_days(1, from_date=last_trading_day(today))[0]

    # NOTE: raw 9M intraday alerts are deliberately NOT fetched — they're the universe
    # (~50/day), surfaced via the /9m button, not the curated actionable list.
    sip, magna53, day2, flags, fishhook = await _aio.gather(
        get_stocks_in_play(active_only=True),
        get_today_ep_alerts(query_str),
        get_all_9m_sugar_babies(yesterday),
        get_flag_watchlist(),
        get_fishhook_outcomes_window(60),
        return_exceptions=True,
    )

    def _ok(x):
        return x if isinstance(x, list) else None

    return render_ideas_summary(
        today=today, sip_rows=_ok(sip), magna53=_ok(magna53),
        ninem_day2=_ok(day2), flags=_ok(flags), fishhook=_ok(fishhook))
