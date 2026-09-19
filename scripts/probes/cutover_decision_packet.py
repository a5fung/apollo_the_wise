"""6/22 live-cutover decision packet — auto-assembles the GO/NO-GO evidence so the call is
data-ready, and so we SEE NOW which gates are short and can attack them this week.

Read-only. Each gate is error-wrapped → reports what it finds or flags 'manual/doc check'.
Run: docker exec apollo-market python scripts/cutover_decision_packet.py
"""
import asyncio

from agents.market_intelligence import db


async def _q(conn, sql, *args):
    try:
        return await conn.fetch(sql, *args)
    except Exception as e:
        return [{"_err": str(e)[:120]}]


async def main():
    pool = await db.get_pool()
    async with pool.acquire() as c:
        print("══ LIVE-CUTOVER DECISION PACKET (target 6/22) ══")
        print("   READ-ONLY · verdicts are the operator's.\n")

        # ── Gate 1: drawdown breaker (armed via #174) ──────────────────────
        print("─ Gate 1 — drawdown breaker (mi_safeguard_state) ─")
        rows = await _q(c, "SELECT safeguard, account_mode, state, last_transition_at "
                           "FROM mi_safeguard_state ORDER BY safeguard, account_mode")
        for r in rows:
            if r.get("_err"):
                print(f"   ⚠ {r['_err']}")
            else:
                print(f"   {r['safeguard']:<26} {r['account_mode']:<6} state={r['state']:<10} "
                      f"since={r['last_transition_at']}")

        # ── Gate 3: paper R-expectancy (closed methodology cohort) ─────────
        print("\n─ Gate 3 — paper R-expectancy N≥10 (mi_live_trades closed) ─")
        rows = await _q(c, """
            SELECT account_mode,
                   COUNT(*) FILTER (WHERE status='closed') AS closed,
                   COUNT(*) FILTER (WHERE status='closed' AND total_pnl>0) AS wins,
                   ROUND(SUM(total_pnl) FILTER (WHERE status='closed')::numeric,0) AS net_pnl
            FROM mi_live_trades
            WHERE created_at >= NOW() - INTERVAL '45 days'
            GROUP BY account_mode ORDER BY account_mode
        """)
        for r in rows:
            if r.get("_err"):
                print(f"   ⚠ {r['_err']}")
            else:
                n = r["closed"] or 0
                wr = f"{(r['wins'] or 0)/n*100:.0f}%" if n else "n/a"
                gate = "✅ N≥10" if n >= 10 else f"🔴 need {10-n} more"
                print(f"   {r['account_mode']:<6} closed={n:<3} win={wr:<5} net=${r['net_pnl']}  {gate}")

        # ── Partial-exit hardening: clean cycles (N=7 needed) ──────────────
        print("\n─ Partial-exit hardening — N=7 clean unattended cycles ─")
        rows = await _q(c, """
            SELECT event_type, COUNT(*) n, MAX(created_at) last
            FROM mi_audit_log
            WHERE created_at >= NOW() - INTERVAL '30 days'
              AND event_type ILIKE '%partial%'
            GROUP BY event_type ORDER BY n DESC
        """)
        if rows and not rows[0].get("_err"):
            for r in rows:
                print(f"   {r['event_type']:<40} n={r['n']:<4} last={r['last']}")
        else:
            print(f"   ⚠ {rows[0].get('_err') if rows else 'no partial events 30d'}")
        print("   → clean-cycle count is a MANUAL read of these (success vs failure events).")

        # ── #142 RDW pending_new watchdog (stuck-order class) ──────────────
        print("\n─ #142 — stuck pending_new / order-reconcile (last 30d) ─")
        rows = await _q(c, """
            SELECT event_type, COUNT(*) n, MAX(created_at) last
            FROM mi_audit_log
            WHERE created_at >= NOW() - INTERVAL '30 days'
              AND (event_type ILIKE '%pending_new%' OR event_type ILIKE '%order_status_reconcil%'
                   OR event_type ILIKE '%stuck%')
            GROUP BY event_type ORDER BY n DESC
        """)
        if rows and not rows[0].get("_err"):
            for r in rows:
                print(f"   {r['event_type']:<40} n={r['n']:<4} last={r['last']}")
            if all(not x.get("_err") for x in rows) and not rows:
                print("   (no stuck-order events — clean)")
        else:
            print(f"   ⚠ {rows[0].get('_err') if rows else 'none'}")

        # ── Doc / ops gates (not queryable — flag for manual) ──────────────
        print("\n─ Manual / doc gates (operator) ─")
        print("   • Gate 5 F — CRMD post-mortem sign-off → docs/incidents/2026-05-14-crmd-naked-position.md §8")
        print("   • Gate 4b — dual-mode env on Hetzner (ALPACA_LIVE_*, ENABLE_LIVE_MODE=true)")
        print("   • Gate-3 SIP cohort verdict — docs/analysis/sip_replay_gate3_2026-06-06.md (+2.27R, GO-supportive)")

        print("\n══ Run weekly; the 🔴 lines are what to attack before 6/22. ══")


asyncio.run(main())
