"""Backward check: decliner-into-catalyst bounce signal.

Trigger: 2026-05-22 #77 Pradeep rally-bands review surfaced an
unexpected finding — the `pre_20d < -5%` (declining) band has
materially higher 5d forward returns than ANY other rally-state band
in our HIGH-tier MAGNA53 cohort. 2026-05-23 first deep-dive (N=14
settled): +9.06% avg, 64% WR, median +15.9%, broadly distributed
across cases (not outlier-driven).

Claim being tested: HIGH-tier catalyst on a declining stock indicates
a truly game-changing catalyst (strong enough news to overcome the
adverse trend = high-conviction reversal signal). The catalyst-quality
filter is already doing the rally-state work implicitly; adding a
rally-state filter on top would be over-fitting / lose signal.

This is the OPPOSITE of Pradeep's "sideways-into-catalyst best" framing
for general momentum trading. For OUR cohort (HIGH-tier filtered), the
ordering is: declining > strong-rally > rallying > sideways/modest.

Method:
  1. Pull HIGH alerts last 60d (deduped, CS/ADRC-only per #59 hygiene)
  2. For each, compute pre_20d return + 5d forward return
  3. Slice the decliner band into sub-bands (-5 to -10, -10 to -20, <-20)
     to see if signal scales with depth of decline
  4. Catalyst-quality breakdown within decliner band (does game_changer
     dominate vs strong vs routine?)
  5. Decision matrix per `feedback_sample_size_discipline`:
     - N≥30 settled AND WR ≥55% AND avg ≥+5%: investigate ship of a
       "catalyst-driven bounce" telemetry tag
     - N≥30 settled AND WR drops <50%: signal was noise, close
     - N<30: continue accumulating

Run: docker exec apollo-market python -m scripts._b78_decliner_band_bounce_signal
"""
import asyncio
from collections import defaultdict


SUB_BANDS = [
    (-10, "  -5 to -10%   (shallow decline)"),
    (-20, "  -10 to -20%  (moderate decline)"),
    (1e9, "  -20%+        (deep decline)"),  # sentinel — anything less than -20 (more negative)
]


def sub_band_for(pct: float | None) -> str | None:
    if pct is None or pct >= -5:
        return None
    # pct is < -5
    if pct >= -10:
        return SUB_BANDS[0][1]
    if pct >= -20:
        return SUB_BANDS[1][1]
    return SUB_BANDS[2][1]


async def main():
    from agents.market_intelligence.db import get_pool
    from scripts._backward_check_utils import band_stats, format_band_row, format_header
    pool = await get_pool()

    async with pool.acquire() as conn:
        rows = await conn.fetch("""
            WITH alerts AS (
                SELECT DISTINCT ON (a.ticker, a.alert_date)
                       a.ticker, a.alert_date, a.ep_score, a.catalyst_quality,
                       a.gap_pct
                FROM mi_ep_alerts a
                LEFT JOIN mi_security_types st ON st.ticker = a.ticker
                WHERE a.alert_date >= CURRENT_DATE - INTERVAL '60 days'
                  AND a.score_tier = 'HIGH'
                  AND (st.security_type IS NULL
                       OR st.security_type IN ('CS', 'ADRC'))
                ORDER BY a.ticker, a.alert_date, a.ep_score DESC NULLS LAST
            )
            SELECT a.ticker, a.alert_date, a.ep_score, a.catalyst_quality, a.gap_pct,
                   CASE WHEN d_pre21.close > 0 AND d_pre1.close IS NOT NULL
                        THEN (d_pre1.close / d_pre21.close - 1) * 100
                        ELSE NULL END          AS pre20d_pct,
                   CASE WHEN d0.open_price > 0 AND d5.close IS NOT NULL
                        THEN (d5.close / d0.open_price - 1) * 100
                        ELSE NULL END          AS ret_5d
            FROM alerts a
            LEFT JOIN LATERAL (
                SELECT close FROM mi_daily_closes
                WHERE ticker = a.ticker AND trade_date < a.alert_date
                ORDER BY trade_date DESC LIMIT 1
            ) d_pre1 ON TRUE
            LEFT JOIN LATERAL (
                SELECT close FROM mi_daily_closes
                WHERE ticker = a.ticker AND trade_date < a.alert_date
                ORDER BY trade_date DESC OFFSET 20 LIMIT 1
            ) d_pre21 ON TRUE
            LEFT JOIN mi_daily_closes d0
                ON d0.ticker = a.ticker AND d0.trade_date = a.alert_date
            LEFT JOIN LATERAL (
                SELECT close FROM mi_daily_closes
                WHERE ticker = a.ticker AND trade_date > a.alert_date
                ORDER BY trade_date ASC OFFSET 4 LIMIT 1
            ) d5 ON TRUE
        """)

    # Filter to decliner band only
    decliners = [r for r in rows if r["pre20d_pct"] is not None and r["pre20d_pct"] < -5]
    n_total = len(rows)
    n_decliners = len(decliners)
    print(f"Cohort: {n_total} HIGH alerts in 60d. Decliner band (pre_20d <-5%): {n_decliners}")
    print()

    # Sub-band breakdown
    print("=" * 130)
    print("DECLINER SUB-BAND BREAKDOWN — does signal scale with depth of decline?")
    print("=" * 130)
    print(format_header(label_width=40))
    print("-" * 130)
    by_sub_band: dict[str, list] = defaultdict(list)
    for r in decliners:
        sb = sub_band_for(r["pre20d_pct"])
        if sb:
            by_sub_band[sb].append(r["ret_5d"])
    for upper, label in SUB_BANDS:
        items = by_sub_band.get(label, [])
        n = len(items)
        if n == 0:
            continue
        stats = band_stats(items)
        print(format_band_row(label, n, n_decliners, stats, label_width=40))
    print()

    # Catalyst-quality breakdown within decliner band
    print("=" * 130)
    print("DECLINER BAND × CATALYST QUALITY — which catalyst class drives the signal?")
    print("=" * 130)
    by_cq: dict[str, list] = defaultdict(list)
    for r in decliners:
        cq = r.get("catalyst_quality") or "unknown"
        by_cq[cq].append(r["ret_5d"])
    print(f"{'CATALYST':<20} {'N':>5}  {'avg_5d':>10}  {'median':>10}  {'winners ≥+5%':>14}")
    print("-" * 65)
    for cq in sorted(by_cq.keys()):
        items = by_cq[cq]
        n = len(items)
        settled = [v for v in items if v is not None]
        n_settled = len(settled)
        if n_settled == 0:
            print(f"{cq:<20} {n:>5}  {'—':>10}  {'—':>10}  {'—':>14}")
            continue
        avg = sum(settled) / n_settled
        sorted_vals = sorted(settled)
        median = sorted_vals[n_settled // 2]
        winners = sum(1 for v in settled if v >= 5)
        print(f"{cq:<20} {n:>5}  {avg:>+9.1f}%  {median:>+9.1f}%  {winners}/{n_settled} ({100*winners//n_settled}%)".replace(' ',' '))
    print()

    # Decision gate
    print("=" * 130)
    print("DECISION GATE — sample_size_discipline + validate_metric_before_decision")
    print("=" * 130)
    settled = [r for r in decliners if r["ret_5d"] is not None]
    n_settled = len(settled)
    if n_settled == 0:
        print("No settled outcomes yet.")
        return
    avg = sum(r["ret_5d"] for r in settled) / n_settled
    winners = sum(1 for r in settled if r["ret_5d"] >= 5)
    wr = winners / n_settled * 100
    print(f"Decliner band N_settled={n_settled} avg={avg:+.2f}% WR(≥+5%)={wr:.1f}%")
    print()
    if n_settled < 30:
        print(f"→ N<30: KEEP OBSERVING. Need {30 - n_settled} more settled cases before ship decision.")
        print("   Re-run on monthly cadence via agents/market_intelligence/quarterly_review.py.")
    elif wr >= 55 and avg >= 5:
        print("→ N≥30 + WR ≥55% + avg ≥+5%: PROMOTE to methodology review.")
        print("   File followup to design a 'catalyst-driven bounce' tag in evening briefing,")
        print("   shadow telemetry for 30d, then operator-only watchlist surface if real.")
        print("   DO NOT auto-include this band — that's apollo_eligible class (per ADR 0004)")
        print("   and requires N≥10 settled positive after a shadow-phase tag period.")
    elif wr < 50:
        print("→ N≥30 + WR <50%: signal was small-N noise. CLOSE the investigation.")
    else:
        print(f"→ N≥30 + WR ∈ [50, 55): MARGINAL. Continue observing; review at N≥50.")
    print()
    print("Caveat: this is forward-return drift, not entry-aware P&L. Per")
    print("feedback_validate_metric_before_decision.md, any methodology ship MUST")
    print("compare ORB-entry simulation outcomes against open-to-close drift, not")
    print("just close-to-close forward returns. The cohort is HIGH-tier filtered;")
    print("baseline comparison is the WR of other bands in the same cohort.")


if __name__ == "__main__":
    asyncio.run(main())
