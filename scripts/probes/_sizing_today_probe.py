"""Read-only: was today's entry half-size, and what drove the multiplier (strategy vs drawdown)?"""
import asyncio
from agents.market_intelligence.db import get_pool


async def main():
    pool = await get_pool()
    async with pool.acquire() as c:
        print("=== today's mi_live_trades entries ===")
        rows = await c.fetch("""
            SELECT ticker, signal_type, account_mode, status, entry_price, entry_shares,
                   position_size, risk_dollars, alert_date
            FROM mi_live_trades
            WHERE alert_date >= CURRENT_DATE - INTERVAL '1 day'
            ORDER BY alert_date DESC, ticker
        """)
        for r in rows:
            print(f"  {r['alert_date']} {r['ticker']:6} {r['signal_type']:9} {r['account_mode']:5} "
                  f"{r['status']:18} shares={r['entry_shares']} entry={r['entry_price']} "
                  f"size=${r['position_size']} risk=${r['risk_dollars']}")
        if not rows:
            print("  (no trade rows today)")

        print("\n=== per_strategy_sizing_applied audit (the multiplier breakdown) last 30h ===")
        rows = await c.fetch("""
            SELECT created_at, summary FROM mi_audit_log
            WHERE event_type = 'per_strategy_sizing_applied'
              AND created_at > NOW() - INTERVAL '30 hours' ORDER BY created_at DESC
        """)
        for r in rows:
            print(f"  {str(r['created_at'])[:19]}  {r['summary']}")
        if not rows:
            print("  (none — no sizing multiplier applied today; entries were full-size, multiplier=1.0)")

        print("\n=== drawdown-breaker tier state (per mode) — REDUCE = 0.5x sizing ===")
        rows = await c.fetch("""
            SELECT safeguard, account_mode, state, updated_at FROM mi_safeguard_state
            WHERE safeguard ILIKE '%drawdown%' ORDER BY account_mode
        """)
        for r in rows:
            print(f"  {r['safeguard']:24} {r['account_mode']:5} state={r['state']}  ({str(r['updated_at'])[:19]})")
        if not rows:
            print("  (no drawdown safeguard state rows = OK/no reduction)")

        print("\n=== latest market regime ===")
        r = await c.fetchrow("SELECT regime, regime_date FROM mi_regime ORDER BY regime_date DESC LIMIT 1")
        if r:
            print(f"  {r['regime']}  ({r['regime_date']})")


asyncio.run(main())
