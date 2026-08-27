"""Kill/scale quarterly review — capture part 2 (open book + 2R era). READ-ONLY, 2026-08-26."""
import asyncio


async def main():
    from agents.market_intelligence.db import get_pool, OPEN_POSITION_STATUSES
    pool = await get_pool()
    async with pool.acquire() as c:
        print("=== Q9 OPEN BOOK (live) ===")
        for r in await c.fetch(
                """SELECT id, ticker, alert_date, status, regime, entry_price, entry_shares,
                          hard_stop, stop_price, remaining_shares, total_pnl, partial_taken,
                          breakeven_active, COALESCE(hold_days,0) AS hold_days,
                          risk_dollars, risk_dollars_actual, highest_price_seen, exits
                   FROM mi_live_trades WHERE status = ANY($1) AND account_mode='live'
                   ORDER BY alert_date""", list(OPEN_POSITION_STATUSES)):
            print("   ", dict(r))
        print("OPEN_POSITION_STATUSES =", list(OPEN_POSITION_STATUSES))

        print("\n=== Q10 2R ERA (hard_stop vs ORB geometry), every filled live trade ===")
        print("hdr: id|ticker|filled_d|status|orb_high|orb_low|hard_stop|orblow_stop_dist|"
              "2R_stop|is_2R|entry_shares|total_pnl")
        for r in await c.fetch(
                """SELECT id, ticker, status, orb_high, orb_low, hard_stop, entry_price,
                          entry_shares, total_pnl,
                          to_char(filled_at AT TIME ZONE 'America/New_York','YYYY-MM-DD') AS filled_d
                   FROM mi_live_trades WHERE account_mode='live' AND filled_at IS NOT NULL
                   ORDER BY filled_at"""):
            d = dict(r)
            try:
                oh, ol, hs = float(d["orb_high"]), float(d["orb_low"]), float(d["hard_stop"])
                two_r = 2 * ol - oh
                print(f"row: {d['id']}|{d['ticker']}|{d['filled_d']}|{d['status']}|{oh}|{ol}|"
                      f"{hs}|{round(oh-ol,4)}|{round(two_r,4)}|"
                      f"{abs(hs-two_r) < max(0.02, 0.005*oh)}|{d['entry_shares']}|{d['total_pnl']}")
            except Exception as e:
                print(f"row: {d['id']}|{d['ticker']}|{d['filled_d']}|{d['status']}|ERR {e}|"
                      f"orb_high={d['orb_high']} orb_low={d['orb_low']} hard_stop={d['hard_stop']}")

        print("\n=== Q11 EXIT LEGS on closed live cohort ===")
        for r in await c.fetch(
                """SELECT id, ticker, partial_taken, breakeven_active, hold_days, exits
                   FROM mi_live_trades WHERE status='closed' AND account_mode='live'
                   ORDER BY alert_date, id"""):
            print("   ", dict(r))
    print("\n=== DONE2 ===")


asyncio.run(main())
