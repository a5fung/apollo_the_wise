"""Distributional analysis of 9M Day 2 stop-distance / ATR ratio (#54).

Cohort: 90d of 9M Day 2 candidates (entered + skipped + cancelled).
Outcome-based backward check isn't feasible yet — only N=4 entered,
N=3 closed (below sample-size threshold).

Instead, ask the distributional question:
  - What stop/ATR ratios were we ENTERING?
  - What ratios were we SKIPPING?
  - Would the proposed ATR-normalized cap (2.5× ATR) change behavior
    vs the current absolute cap (15% stop distance)?

For each candidate:
  - stop_distance_pct = (entry_price - stop_price) / entry_price
  - ATR-14% at entry_date (from mi_daily_closes pre-entry)
  - stop_atr_ratio = stop_distance_pct / atr14_pct

Then crosstab: absolute-gate-decision × ATR-gate-decision.
Identifies cases where the gates would DIFFER.

Run: docker exec apollo-market python -m scripts._b54_9m_day2_stop_atr_distribution
"""
import asyncio
from collections import defaultdict


async def main():
    from agents.market_intelligence.db import get_pool
    pool = await get_pool()

    async with pool.acquire() as conn:
        rows = await conn.fetch("""
            WITH trades AS (
                SELECT t.id, t.ticker, t.alert_date, t.status, t.signal_type,
                       t.entry_price, t.stop_price, t.skip_reason, t.total_pnl,
                       t.entry_shares, t.risk_dollars
                FROM mi_live_trades t
                LEFT JOIN mi_security_types st ON st.ticker = t.ticker
                WHERE t.alert_date >= CURRENT_DATE - INTERVAL '90 days'
                  AND t.signal_type = '9m_day2'
                  AND (st.security_type IS NULL
                       OR st.security_type IN ('CS', 'ADRC'))
            ),
            atr_bars AS (
                SELECT tr.id, d.trade_date, d.high_price, d.low_price, d.close,
                       LAG(d.close) OVER (PARTITION BY tr.id ORDER BY d.trade_date) AS prev_close
                FROM trades tr
                JOIN mi_daily_closes d ON d.ticker = tr.ticker
                WHERE d.trade_date < tr.alert_date
                  AND d.trade_date >= tr.alert_date - INTERVAL '30 days'
            ),
            atr_calc AS (
                SELECT id,
                       AVG(
                           GREATEST(
                               high_price - low_price,
                               ABS(high_price - prev_close),
                               ABS(low_price - prev_close)
                           ) / NULLIF(prev_close, 0) * 100
                       ) AS atr14_pct
                FROM (
                    SELECT *, ROW_NUMBER() OVER (PARTITION BY id ORDER BY trade_date DESC) AS rn
                    FROM atr_bars WHERE prev_close IS NOT NULL
                ) sub
                WHERE rn <= 14
                GROUP BY id
            )
            SELECT t.id, t.ticker, t.alert_date, t.status, t.skip_reason,
                   t.entry_price, t.stop_price, t.total_pnl, t.risk_dollars,
                   atr.atr14_pct,
                   CASE WHEN t.entry_price > 0 AND t.stop_price > 0
                        THEN (t.entry_price - t.stop_price) / t.entry_price * 100
                        ELSE NULL END AS stop_dist_pct
            FROM trades t
            LEFT JOIN atr_calc atr ON atr.id = t.id
            ORDER BY t.alert_date DESC, t.ticker
        """)

    # Categorize
    entered = []
    skipped_stop_too_wide = []
    skipped_other = []
    for r in rows:
        record = dict(r)
        sd = record.get("stop_dist_pct")
        atr = record.get("atr14_pct")
        record["stop_atr_ratio"] = (sd / atr) if (sd and atr and atr > 0) else None
        if record["status"] in ("filled", "closed"):
            entered.append(record)
        elif record["status"] == "skipped":
            reason = (record.get("skip_reason") or "").lower()
            if "stop_too_wide" in reason:
                skipped_stop_too_wide.append(record)
            else:
                skipped_other.append(record)

    print(f"9M Day 2 cohort (90d): {len(rows)} total candidates")
    print(f"  entered (filled/closed): {len(entered)}")
    print(f"  skipped (stop_too_wide):  {len(skipped_stop_too_wide)}")
    print(f"  skipped (other reasons):  {len(skipped_other)}")
    print()

    # ENTERED — show ratios
    print("=" * 100)
    print(f"ENTERED ({len(entered)}):")
    print(f"  {'ticker':<8} {'date':<12} {'stop_dist':<10} {'ATR':<7} {'ratio':<8} {'status':<8} {'pnl'}")
    for r in entered:
        sd = f"{r['stop_dist_pct']:.2f}%" if r['stop_dist_pct'] else "—"
        atr = f"{r['atr14_pct']:.2f}%" if r['atr14_pct'] else "—"
        ratio = f"{r['stop_atr_ratio']:.2f}x" if r['stop_atr_ratio'] else "—"
        pnl = f"${r['total_pnl']:.0f}" if r['total_pnl'] is not None else "open"
        print(f"  {r['ticker']:<8} {str(r['alert_date']):<12} {sd:<10} {atr:<7} {ratio:<8} {r['status']:<8} {pnl}")
    print()

    # SKIPPED by stop_too_wide — these are CURRENT gate firings
    print("=" * 100)
    print(f"SKIPPED via stop_too_wide gate ({len(skipped_stop_too_wide)}):")
    print(f"  {'ticker':<8} {'date':<12} {'stop_dist':<10} {'ATR':<7} {'ratio':<8} {'reason'}")
    for r in skipped_stop_too_wide[:20]:
        sd = f"{r['stop_dist_pct']:.2f}%" if r['stop_dist_pct'] else "—"
        atr = f"{r['atr14_pct']:.2f}%" if r['atr14_pct'] else "—"
        ratio = f"{r['stop_atr_ratio']:.2f}x" if r['stop_atr_ratio'] else "—"
        reason = (r['skip_reason'] or "")[:50]
        print(f"  {r['ticker']:<8} {str(r['alert_date']):<12} {sd:<10} {atr:<7} {ratio:<8} {reason}")
    print()

    # Hypothetical ATR-gate decisions
    # Current gate: stop_dist > 15% → REJECT
    # Proposed:     stop_dist / ATR > 2.5x → REJECT
    print("=" * 100)
    print("GATE COMPARISON: absolute 15% vs ATR-normalized 2.5x")
    print("=" * 100)

    candidates_for_gate = entered + skipped_stop_too_wide
    quad: dict[str, list] = defaultdict(list)
    for r in candidates_for_gate:
        sd = r['stop_dist_pct']
        ratio = r['stop_atr_ratio']
        if sd is None or ratio is None:
            continue
        abs_reject = sd > 15.0
        atr_reject = ratio > 2.5
        key = f"abs_{'REJECT' if abs_reject else 'PASS'}_atr_{'REJECT' if atr_reject else 'PASS'}"
        quad[key].append(r)

    for k in ("abs_PASS_atr_PASS", "abs_PASS_atr_REJECT",
              "abs_REJECT_atr_PASS", "abs_REJECT_atr_REJECT"):
        items = quad.get(k, [])
        print(f"\n{k} ({len(items)}):")
        for r in items[:10]:
            sd = f"{r['stop_dist_pct']:.2f}%"
            atr = f"{r['atr14_pct']:.2f}%"
            ratio = f"{r['stop_atr_ratio']:.2f}x"
            outcome = r['status']
            pnl = f"${r['total_pnl']:.0f}" if r['total_pnl'] is not None else ("open" if outcome != "skipped" else "—")
            print(f"  {r['ticker']:<8} {str(r['alert_date']):<12} stop={sd:<7} ATR={atr:<7} ratio={ratio:<7} {outcome} pnl={pnl}")
    print()

    # Key question: were any entries enabled by absolute-pass-but-ATR-reject?
    # These are the "PURR-class" trades that would be blocked by ATR gate.
    purr_class = quad.get("abs_PASS_atr_REJECT", [])
    print(f"PURR-class trades (absolute PASS but ATR-normalized REJECT): {len(purr_class)}")
    if purr_class:
        entered_purr = [r for r in purr_class if r['status'] in ('filled', 'closed')]
        skipped_purr = [r for r in purr_class if r['status'] == 'skipped']
        with_pnl = [r for r in entered_purr if r['total_pnl'] is not None]
        if with_pnl:
            avg_pnl = sum(r['total_pnl'] for r in with_pnl) / len(with_pnl)
            winners = sum(1 for r in with_pnl if r['total_pnl'] > 0)
            print(f"  Entered: {len(entered_purr)} ({winners}/{len(with_pnl)} winners, avg pnl ${avg_pnl:.0f})")
        else:
            print(f"  Entered: {len(entered_purr)} (no closed P&L yet)")
        print(f"  Skipped (other reason): {len(skipped_purr)}")


if __name__ == "__main__":
    asyncio.run(main())
