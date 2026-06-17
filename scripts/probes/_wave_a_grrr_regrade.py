"""#210 Wave A acceptance test — does wiring Benzinga into the grounded corpus
flip the GRRR 2026-06-02 grade from suppressed -> a real catalyst?

READ-ONLY: news fetch + LLM grade + one SELECT. No trade state touched.

Method (advisor-specified isolation):
  1. Fetch every source ONCE for the as-of date.
  2. Build TWO grounded_text strings via the SHIPPING helper
     (ep_detector.build_grounded_text) that differ ONLY by the Benzinga block.
  3. Grade both with the SHIPPING grader (_classify_catalyst_claude on Sonnet).
  4. Anchor the factual "before" on the actual stored mi_ep_alerts verdict.
  5. Report the 6-K filed timestamp vs the Benzinga item time (timing thread).

ACCEPTANCE (hold literally): the WITH-Benzinga grade lands on strong/game_changer.
A flip to `mna` is NOT a pass — it means the grade's rule-3 is over-broad on
partnership/supply deals (a real finding, surfaced not papered over).

Usage (on the server, in the market-agent container env):
    python scripts/_wave_a_grrr_regrade.py            # GRRR 2026-06-02
    python scripts/_wave_a_grrr_regrade.py PGY 2026-06-03
"""
import asyncio
import sys
from datetime import date

from agents.market_intelligence.collector import (
    get_alpaca_news,
    get_fmp_profile,
    get_sec_recent_filings,
    is_primary_subject_news,
    search_news_perplexity,
)
from agents.market_intelligence.ep_detector import (
    build_grounded_text,
    _classify_catalyst_claude,
)


def _parse_args():
    ticker = sys.argv[1].upper() if len(sys.argv) > 1 else "GRRR"
    if len(sys.argv) > 2:
        y, m, d = (int(x) for x in sys.argv[2].split("-"))
        as_of = date(y, m, d)
    else:
        as_of = date(2026, 6, 2)
    return ticker, as_of


async def _stored_verdict(ticker: str, as_of: date):
    """Best-effort read of the as-of stored EP verdict (None if unavailable)."""
    try:
        from agents.market_intelligence.db import get_pool
        pool = await get_pool()
        async with pool.acquire() as con:
            return await con.fetchrow(
                """
                SELECT ticker, alert_date, ep_score, score_tier, catalyst_quality, catalyst
                FROM mi_ep_alerts
                WHERE ticker = $1 AND alert_date = $2
                ORDER BY created_at DESC LIMIT 1
                """,
                ticker, as_of,
            )
    except Exception as e:  # read-only convenience; never block the grade test
        print(f"  (stored-verdict lookup unavailable: {e})")
        return None


async def main():
    ticker, as_of = _parse_args()
    print(f"=== #210 Wave A re-grade: {ticker} as-of {as_of} ===\n")

    # 1. Fetch every source ONCE (lookback spans the gap day).
    # NOTE: get_sec_recent_filings is anchored on "now", not as_of — widen the
    # lookback to reach back to as_of. It's identical in both grade arms, so it
    # never confounds the Benzinga isolation; it only feeds the 6-K timing note.
    from_date = date.fromordinal(as_of.toordinal() - 3)
    sec_lookback = max(4, (date.today().toordinal() - as_of.toordinal()) + 5)
    profile, sec_filings, alpaca_news, perplexity_answer = await asyncio.gather(
        get_fmp_profile(ticker),
        get_sec_recent_filings(ticker, forms=("8-K", "6-K"), lookback_days=sec_lookback),
        get_alpaca_news(ticker, from_date=from_date, to_date=as_of),
        search_news_perplexity(
            f"What caused {ticker} stock to gap up around {as_of}? Latest catalyst and news.",
            recency="month",
        ),
    )
    company = profile.get("companyName", "") if profile else ""
    sec_filing = next((f for f in (sec_filings or []) if f.get("text")), None)

    # AS-OF reconstruction: a filing dated AFTER as_of did not exist on the gap
    # day — including it would let the control arm "cheat" with hindsight (the
    # GRRR 6-K filed 6/5 vs the 6/2 gap). Drop it from BOTH arms so the only
    # same-day primary source for the deal is the Benzinga wire.
    if sec_filing and str(sec_filing.get("filed", "")) > as_of.isoformat():
        print(f"-- AS-OF: dropping SEC {sec_filing['form']} filed {sec_filing['filed']} "
              f"(post-dates {as_of}; did not exist on the gap day)\n")
        sec_filing = None

    # 2. Primary-subject-filter the Benzinga items (the shipping filter).
    benzinga_items = [
        n for n in (alpaca_news or [])
        if is_primary_subject_news(n, ticker, company)
    ][:3]

    print(f"-- raw Alpaca/Benzinga items: {len(alpaca_news or [])}, "
          f"primary-subject kept: {len(benzinga_items)}")
    for n in (alpaca_news or []):
        kept = is_primary_subject_news(n, ticker, company)
        print(f"   [{'KEEP' if kept else 'drop'}] {n.get('created_at','')[:16]} "
              f"sym={n.get('symbols')} :: {(n.get('title') or '')[:90]}")
    print()

    # 5. 6-K timing thread.
    if sec_filing:
        print(f"-- SEC: {sec_filing['form']} filed {sec_filing['filed']} "
              f"items={sec_filing.get('items')}")
    else:
        print("-- SEC: no filing with body text returned for the window "
              "(6-K likely lagged the same-day PR — the press-wire timing argument)")
    bz_times = [n.get("created_at", "") for n in benzinga_items]
    if bz_times:
        print(f"-- Benzinga earliest kept item: {min(bz_times)}")
    print()

    # 3. Build two grounded strings differing ONLY by the Benzinga block.
    grounded_without = build_grounded_text(sec_filing, [], perplexity_answer)
    grounded_with = build_grounded_text(sec_filing, benzinga_items, perplexity_answer)

    q_without, a_without = await _classify_catalyst_claude(
        ticker, [], profile or {}, grounded_text=grounded_without)
    q_with, a_with = await _classify_catalyst_claude(
        ticker, [], profile or {}, grounded_text=grounded_with)

    # 4. Stored verdict anchor.
    stored = await _stored_verdict(ticker, as_of)

    print("=== RESULT ===")
    if stored:
        print(f"  stored 6/2 verdict : score={stored['ep_score']} "
              f"tier={stored['score_tier']} quality={stored['catalyst_quality']}")
        print(f"  stored catalyst    : {(stored['catalyst'] or '')[:300]}")
    print(f"  grade WITHOUT bz   : {q_without}")
    print(f"     -> {a_without[:200]}")
    print(f"  grade WITH bz      : {q_with}")
    print(f"     -> {a_with[:200]}")
    print()

    _TIER = {"routine": 0, "mna": 0, "strong": 1, "game_changer": 2}
    upgraded = _TIER.get(q_with, 0) > _TIER.get(q_without, 0)
    if upgraded:
        print(f"  ✅ ISOLATED UPGRADE — Benzinga lifts {ticker}: {q_without} -> {q_with} "
              f"(only the Benzinga block differs between arms).")
        print(f"     NOTE: the WITHOUT-bz arm is hindsight-contaminated (Perplexity-now has "
              f"indexed the deal), so this is a LOWER BOUND on Benzinga's same-day live value.")
    elif q_with == "mna":
        print(f"  ❌ NOT A PASS — flips to 'mna' (suppressed). Grade rule-3 over-broad on "
              f"partnership/supply-deal language. Real finding — do not paper over.")
    elif q_with == q_without:
        print(f"  ⚠️  NO CHANGE — both '{q_with}'. Either Benzinga added nothing the grade "
              f"weighted, or the no-bz arm already carried the catalyst (Perplexity re-run "
              f"may now be indexed). Inspect the two grounded strings.")
    else:
        print(f"  ⚠️  CHANGED but not to strong/gc: {q_without} -> {q_with}. Inspect.")


if __name__ == "__main__":
    asyncio.run(main())
