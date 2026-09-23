"""#266 evidence run — does theme membership validation AT BIRTH add value over what already
exists (post-assignment validation + the 6 AM round-trip validator + Mon/Wed/Fri validation)?

Read-only. The decisive metric is STRIP LATENCY: for members of newly-born themes that later get
stripped by validation, how long AFTER the theme's birth was the strip? If strips cluster at ~0
(post-assignment validation already catches them at birth) → birth-validation is redundant. If
there's a meaningful tail of strips landing DAYS later (caught only on the next Mon/Wed/Fri cycle)
→ birth/identity-change validation would catch them earlier = the gap #266 fills.

Also quantifies the RESIDUAL the round-trip alarm misses (it only fires at ≥50% AND ≥2 stripped
within 3d) — themes with a smaller but real bad-birth fraction.
"""
import asyncio
from agents.market_intelligence.db import get_pool

WINDOW_DAYS = 60


async def main():
    pool = await get_pool()
    async with pool.acquire() as c:
        # Members of themes born in the window that were later stripped — with the strip latency
        # measured from the theme's birth (created_at).
        rows = [dict(r) for r in await c.fetch(f"""
            WITH born AS (
                SELECT name, created_at, tickers, array_length(tickers,1) AS n
                FROM mi_themes
                WHERE created_at >= NOW() - INTERVAL '{WINDOW_DAYS} days'
                  AND array_length(tickers,1) >= 2
            ),
            strip AS (
                SELECT b.name, b.created_at, b.n, s.ticker,
                       EXTRACT(EPOCH FROM (s.removed_at - b.created_at))/3600.0 AS lat_hours
                FROM born b
                JOIN mi_validation_cooldowns s
                  ON s.theme_name = b.name AND s.ticker = ANY(b.tickers)
                 AND s.removed_at >= b.created_at
                 AND s.removed_at <= b.created_at + INTERVAL '14 days'
            )
            SELECT name, created_at, n, ticker, lat_hours FROM strip
            ORDER BY created_at DESC, lat_hours
        """)]
        born_n = await c.fetchval(f"""
            SELECT count(*) FROM mi_themes
            WHERE created_at >= NOW() - INTERVAL '{WINDOW_DAYS} days' AND array_length(tickers,1) >= 2""")

    print(f"=== #266 birth-validation evidence (themes born last {WINDOW_DAYS}d, ≥2 members) ===")
    print(f"  themes born (≥2 members) ........ {born_n}")
    print(f"  member-strips within 14d of birth {len(rows)}")
    if not rows:
        print("  → no post-birth strips in window: birth-validation adds nothing measurable now.")
        return

    lats = sorted(r["lat_hours"] for r in rows)
    n = len(lats)

    def pct_le(h):
        return sum(1 for x in lats if x <= h) / n * 100

    med = lats[n // 2]
    print("\n  STRIP LATENCY from theme birth (the decisive metric):")
    print(f"    median ............ {med:7.1f}h ({med/24:.1f}d)")
    print(f"    ≤ 1h  (at-birth) .. {pct_le(1):5.0f}%   (post-assignment validation already catches)")
    print(f"    ≤ 24h ............. {pct_le(24):5.0f}%")
    print(f"    ≤ 72h (3d) ........ {pct_le(72):5.0f}%   (round-trip validator's window)")
    print(f"    > 72h (the GAP) ... {100 - pct_le(72):5.0f}%   (caught only on next Mon/Wed/Fri cycle)")

    # themes with ANY post-birth strip, and the residual below the round-trip alarm bar
    by_theme = {}
    for r in rows:
        by_theme.setdefault((r["name"], r["created_at"]), {"n": r["n"], "within3d": 0})
        if r["lat_hours"] <= 72:
            by_theme[(r["name"], r["created_at"])]["within3d"] += 1
    alarmed = sum(1 for v in by_theme.values() if v["within3d"] >= max(2, int(v["n"] * 0.5)))
    print(f"\n  themes with ≥1 post-birth strip .. {len(by_theme)}")
    print(f"    of which the round-trip ALARM fires (≥50% & ≥2 in 3d) .. {alarmed}")
    print(f"    RESIDUAL (real bad-birth, below the alarm bar) ......... {len(by_theme) - alarmed}")

    print("\n  Worst late strips (>72h — the birth-validation gap):")
    late = [r for r in rows if r["lat_hours"] > 72][:12]
    for r in late:
        print(f"    {r['ticker']:6} from '{r['name'][:40]}' — {r['lat_hours']/24:.1f}d after birth")


if __name__ == "__main__":
    asyncio.run(main())
