"""2026-10-05 first-live-day check (read-only): today's M&A filter rows (#692/#692b + 10-03 review
fixes), EP alerts and live entries with their risk dollars vs equity × RISK_PCT (#688), and the
regime multiplier in force. Writes nothing.  Run inside apollo-market."""
import asyncio
import json

from agents.market_intelligence import constants
from agents.market_intelligence.db import get_pool

EVENTS = ("mna_filter_fired", "mna_filter_released", "mna_pin_confirmed", "mna_pin_unreadable",
          "mna_release_merit_grade", "mna_release_without_merit_grade", "open_window_price_pin",
          "mna_grade_without_pin", "mna_deal_answers_conflict")


async def main():
    pool = await get_pool()
    async with pool.acquire() as c:
        rows = await c.fetch(
            "SELECT created_at AT TIME ZONE 'America/New_York' AS t, event_type, left(summary, 220) AS s "
            "FROM mi_audit_log WHERE event_type = ANY($1) AND created_at >= "
            "(date_trunc('day', NOW() AT TIME ZONE 'America/New_York') AT TIME ZONE 'America/New_York') "
            "ORDER BY created_at", list(EVENTS))
        alerts = await c.fetch(
            "SELECT ticker, score_tier, ep_score, created_at AT TIME ZONE 'America/New_York' AS t "
            "FROM mi_ep_alerts WHERE alert_date = (NOW() AT TIME ZONE 'America/New_York')::date "
            "ORDER BY created_at")
        cols = {r["column_name"] for r in await c.fetch(
            "SELECT column_name FROM information_schema.columns WHERE table_name = 'mi_live_trades'")}
        want = [x for x in ("id", "ticker", "status", "account_mode", "entry_shares", "orb_high",
                            "orb_low", "risk_dollars", "risk_pct", "skip_reason", "created_at")
                if x in cols]
        trades = await c.fetch(
            f"SELECT {', '.join(want)} FROM mi_live_trades WHERE created_at >= "
            "(date_trunc('day', NOW() AT TIME ZONE 'America/New_York') AT TIME ZONE 'America/New_York') "
            "ORDER BY created_at")
    print(f"RISK_PCT = {constants.RISK_PCT}")
    print(f"== M&A filter rows today ({len(rows)})")
    for r in rows:
        print(f"  {r['t']:%H:%M:%S} {r['event_type']:<34} {r['s']}")
    print(f"== EP alerts today ({len(alerts)})")
    for a in alerts:
        print(f"  {a['t']:%H:%M:%S} {a['ticker']:<6} {a['score_tier']} {a['ep_score']}")
    print(f"== live trades rows today ({len(trades)})  columns: {want}")
    for t in trades:
        print("  ", json.dumps({k: (str(v) if v is not None else None) for k, v in dict(t).items()}))


asyncio.run(main())
