"""`/ideas` — the unified trade-ideas front door.

"Stocks in Play" = GRADUATED entries ONLY (promoted past shadow to ≥ paper phase) — the
genuinely tradeable list. An entry must be COMPLETED + GRADUATED before its names belong
here. Today the only graduated entry is **MAGNA53 EP**.

NOT in play (operator 2026-06-16, corrected repeatedly):
  • Shadow / in-development entries — **tight coil / flag, anticipation, wick,
    parabolic** — are being COMPLETED (the priority work, esp. anticipation #270). They are
    surfaced as "in development" drill-down buttons, never the in-play list.
  • **9M is the stock FILTER** (the universe that identifies candidates which feed the real
    entries) — NOT an entry. So 9M Day-2 is not in play; raw 9M + the sugar-baby cohort are
    universe, behind /9m and /sugarbabies.

The board is small / sometimes empty BY DESIGN — that's the honest state while entries are
still being completed. Do NOT pad it. As each entry graduates shadow→paper, its names earn
a place here. Kept light (no heavy imports at module top) so render_ideas_summary is
unit-testable without a DB.
"""
from __future__ import annotations

_SEP = "━━━━━━━━━━━━━━━━━━━━━"


def _reason_tag(r) -> str:
    return (r.get("reason") or "setup").split("—")[0].strip().replace("_", " ")


def render_ideas_summary(*, today, magna53, sip_rows) -> str:
    """Pure /ideas summary. GRADUATED entries only. All list args may be None."""
    lines = [f"💡 *Apollo Ideas* — {today.strftime('%a %b %d')}", _SEP]

    # GRADUATED entries (≥paper): MAGNA53 EP HIGH + any apollo_eligible substrate row.
    # 9M (raw + Day-2) is the stock FILTER, not an entry → deliberately excluded.
    inplay, seen = [], set()
    for a in (magna53 or []):
        t = a.get("ticker")
        if a.get("score_tier") == "HIGH" and t and t not in seen:
            seen.add(t)
            inplay.append((t, "MAGNA53 EP HIGH"))
    for r in (sip_rows or []):
        t = r.get("ticker")
        if r.get("automation_class") == "apollo_eligible" and t and t not in seen:
            seen.add(t)
            inplay.append((t, _reason_tag(r)))

    lines.append(f"🎯 *Stocks in Play* — graduated · tradeable now ({len(inplay)})")
    if inplay:
        for t, tag in inplay:
            lines.append(f"  🚨 `{t}` {tag}")
    else:
        lines.append("  _no graduated entry firing right now_")
    lines.append(_SEP)
    lines.append("🔬 *In development* (not yet in play — completing):")
    lines.append("  ⏱️ anticipation · 🚩 flag/coil")
    lines.append(_SEP)
    lines.append("_Tap a button to observe · 9M = stock filter → /9m · watchlist → /sugarbabies_")
    return "\n".join(lines)


async def build_ideas_text() -> str:
    """Fetch fail-open and render. Only graduated entries feed the in-play list (MAGNA53 EP +
    any apollo_eligible substrate row); shadow entries + the 9M universe are NOT fetched here —
    they're observed via the drill-down buttons / /9m / /sugarbabies."""
    import asyncio as _aio
    from agents.market_intelligence.collector import et_today, last_trading_day
    from agents.market_intelligence.db import get_stocks_in_play, get_today_ep_alerts

    today = et_today()
    query_str = last_trading_day(today).isoformat()

    sip, magna53 = await _aio.gather(
        get_stocks_in_play(active_only=True),
        get_today_ep_alerts(query_str),
        return_exceptions=True,
    )

    def _ok(x):
        return x if isinstance(x, list) else None

    return render_ideas_summary(today=today, magna53=_ok(magna53), sip_rows=_ok(sip))
