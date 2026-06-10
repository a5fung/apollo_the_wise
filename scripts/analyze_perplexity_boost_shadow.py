"""#233 (Wave C Part 1 analyzer) — Perplexity agreement-boost shadow read.

READ-ONLY. Walks the `perplexity_boost_shadow` audit rows (emitted since
2026-06-08 on every uncached grade tick where the 1.2x pplx-agreement boost
applied) and answers the Wave-C question: how many HIGHs are MANUFACTURED by
the boost (score_without_boost < threshold <= live_score), and how does that
split by has_direct_source?

  - manufactured + has_direct_source=False  → the confident-confabulation
    population the demotion flip targets (Perplexity alone pushed it to HIGH).
  - manufactured + has_direct_source=True   → agreement boost working as
    designed (direct source corroborates; boost is the tiebreaker).

⚠ LOWER BOUND, by design: this measures ONE mechanism (the multiplier). The
base grade can also be lifted by Perplexity-in-corpus (sole grounded text) —
unmeasured until the Part-2 bounded re-grade. Forward 5d peak is attached per
row (the #199 pattern) as directional context only.

The live demotion flip stays HARD-gated: CHANGE_PROCESS + N + operator
sign-off. This script is the evidence surface for that decision, never the
decision itself.

Run on prod:  docker exec apollo-market python /app/scripts/analyze_perplexity_boost_shadow.py [days]
"""
from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

if sys.stdout.encoding and sys.stdout.encoding.lower() not in ("utf-8", "utf8"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")


async def main(days: int = 90) -> None:
    from agents.market_intelligence.db import get_pool
    pool = await get_pool()
    async with pool.acquire() as conn:
        rows = await conn.fetch("""
            SELECT created_at, detail
            FROM mi_audit_log
            WHERE event_type = 'perplexity_boost_shadow'
              AND created_at > NOW() - ($1 || ' days')::interval
            ORDER BY created_at
        """, str(days))

        parsed = []
        for r in rows:
            try:
                d = json.loads(r["detail"])
            except (TypeError, ValueError):
                continue
            swb = d.get("score_without_boost")
            thr = d.get("ep_threshold")
            live = d.get("live_score")
            d["manufactured_high"] = (
                d.get("live_tier") == "HIGH"
                and not d.get("earnings_override_fired")
                and swb is not None and thr is not None and live is not None
                and swb < thr <= live
            )
            parsed.append(d)

        # Forward 5d peak per ticker/date (directional context only). Cached
        # per (ticker, alert_date) — boost rows are per grade TICK, so the same
        # alert recurs many times over a 90d window; one lookup each, not N.
        fwd_cache: dict[tuple, object] = {}
        for d in parsed:
            key = (d.get("ticker"), d.get("alert_date"))
            if key not in fwd_cache:
                try:
                    fwd_cache[key] = await conn.fetchrow("""
                        SELECT d0.open_price AS open_d0, h5.h AS max_high_5d
                        FROM (SELECT open_price FROM mi_daily_closes
                              WHERE ticker = $1 AND trade_date = $2::date) d0,
                             (SELECT MAX(high_price) AS h FROM (
                                  SELECT high_price FROM mi_daily_closes
                                  WHERE ticker = $1 AND trade_date >= $2::date
                                  ORDER BY trade_date ASC LIMIT 6) x) h5
                    """, key[0], key[1])
                except Exception:
                    fwd_cache[key] = None
            fwd = fwd_cache[key]
            if fwd and fwd["open_d0"] and fwd["max_high_5d"]:
                d["fwd_5d_peak_pct"] = round(
                    (fwd["max_high_5d"] - fwd["open_d0"]) / fwd["open_d0"] * 100, 1)

    n = len(parsed)
    man = [d for d in parsed if d["manufactured_high"]]
    man_nodirect = [d for d in man if not d.get("has_direct_source")]
    print(f"=== Perplexity boost shadow — last {days}d (#233 Wave C Part 1) ===")
    print("READ-ONLY · LOWER BOUND (multiplier mechanism only; corpus-lift unmeasured until Part 2)\n")
    print(f"boost-applied ticks: {n}")
    print(f"manufactured HIGHs (unboosted < threshold ≤ boosted): {len(man)}")
    print(f"  └ WITHOUT a direct source (the demotion-flip target): {len(man_nodirect)}")
    if parsed:
        print("\nrows:")
        for d in parsed:
            tag = ("🎯MANUFACTURED-NO-DIRECT" if d in man_nodirect
                   else "manufactured(direct-corroborated)" if d["manufactured_high"]
                   else "boost-inert")
            fwd = f"  fwd5d {d['fwd_5d_peak_pct']:+.1f}%" if "fwd_5d_peak_pct" in d else ""
            print(f"  {d.get('ticker'):<6} {d.get('alert_date')}  {d.get('live_tier'):<8} "
                  f"{d.get('score_without_boost')}→{d.get('live_score')} (thr {d.get('ep_threshold')}) "
                  f"direct={d.get('has_direct_source')}  {tag}{fwd}")
    verdict_n = len(man_nodirect)
    print(f"\nPart-2 trigger (task #233: 'once Part 1 shows magnitude'): "
          f"{'NOT MET' if verdict_n < 5 else 'review with operator'} "
          f"(manufactured-no-direct N={verdict_n}, want ≥5 before the bounded re-grade).")
    print("HARD gate unchanged: live demotion flip = CHANGE_PROCESS + operator sign-off.")


if __name__ == "__main__":
    asyncio.run(main(int(sys.argv[1]) if len(sys.argv) > 1 else 90))
