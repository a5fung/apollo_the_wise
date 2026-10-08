"""#655 rule A hold-out — step 2: ONE read-only prod pull (writes NOTHING to the database).

Captures, in one run, everything the hold-out needs whichever verdict source survives:
  * every `theme_correctness_check` audit row (summary + full stored detail + its length) — the live
    per-night G3 verdicts, if the 8,000-char detail budget kept them;
  * mi_themes rows since 2026-08-01 (board emulation per night, and the forward check on the
    discovery window's retired themes);
  * the name order `get_active_themes` returns (DISTINCT ON (name) ... ORDER BY name, DB collation);
  * the rebuild inputs, in case the detail was truncated: mi_stock_scores 09-24..10-07 and closes
    2026-05-15..10-07 for every scored / board ticker + SPY.

Run inside apollo-market:  python /tmp/x.py   -> /tmp/655_holdout_pull.pkl
"""
import asyncio
import pickle
from datetime import date

from agents.market_intelligence import ep_theme_belonging as etb
from agents.market_intelligence import market_adjusted_correlation as mac
from agents.market_intelligence.db import get_pool


def _f(x):
    return None if x is None else float(x)


async def main():
    pool = await get_pool()
    async with pool.acquire() as c:
        audit = await c.fetch(
            "SELECT id, created_at, summary, length(detail) AS dlen, detail FROM mi_audit_log "
            "WHERE event_type = 'theme_correctness_check' ORDER BY created_at")
        hist = await c.fetch(
            "SELECT id, theme_date, name, stage, tickers, rs_avg, score, source, days_active "
            "FROM mi_themes WHERE theme_date >= $1 ORDER BY theme_date, id", date(2026, 8, 1))
        order = await c.fetch(
            "SELECT name FROM (SELECT DISTINCT name FROM mi_themes WHERE theme_date >= $1) x ORDER BY name",
            date(2026, 8, 1))
        srows = await c.fetch(
            "SELECT score_date, ticker, rs_composite, sector FROM mi_stock_scores "
            "WHERE score_date >= $1 AND score_date <= $2", date(2026, 9, 24), date(2026, 10, 7))
    scores = {}
    for r in srows:
        scores.setdefault(r["score_date"], {})[r["ticker"]] = {"rs": _f(r["rs_composite"]), "sector": r["sector"]}
    tick = {r["ticker"] for r in srows} | {t for r in hist if r["theme_date"] >= date(2026, 9, 20)
                                             for t in (r["tickers"] or [])} | {mac.MARKET_TICKER}
    closes, n = await etb.fetch_closes(tick, date(2026, 5, 15), date(2026, 10, 8))
    blob = {
        "audit": [dict(created_at=r["created_at"], summary=r["summary"], dlen=r["dlen"], detail=r["detail"])
                  for r in audit],
        "hist": [dict(id=r["id"], theme_date=r["theme_date"], name=r["name"], stage=r["stage"],
                      tickers=list(r["tickers"] or []), rs_avg=_f(r["rs_avg"]), score=_f(r["score"]),
                      source=r["source"], days_active=r["days_active"]) for r in hist],
        "name_order": [r["name"] for r in order],
        "scores": scores,
        "closes": closes,
    }
    with open("/tmp/655_holdout_pull.pkl", "wb") as f:
        pickle.dump(blob, f)
    print(f"audit rows {len(audit)} (detail lengths {[r['dlen'] for r in audit]}) | mi_themes rows {len(hist)} | "
          f"names {len(order)} | score dates {sorted(scores)} | close rows {n} tickers {len(closes)}")
    for r in audit:
        print(r["created_at"], r["summary"][:200])


asyncio.run(main())
