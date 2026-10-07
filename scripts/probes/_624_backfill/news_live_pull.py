"""#624 news step 1 — what the LIVE system saw on the 19 lane ticker-days. READ-ONLY prod reads (SELECT only), one capture.
Prints: mi_ep_alerts columns; every mi_ep_alerts row on a lane ticker-day; mi_ep_scan_log catalyst columns for those
ticker-days; mi_audit_log ep_catalyst_provenance / catalyst-related rows for those ticker-days."""
import asyncio, json
from datetime import date
from agents.market_intelligence.db import get_pool

PAIRS = [('BIAF', '2026-09-09'), ('COLA', '2026-09-11'), ('GRML', '2026-09-22'), ('GRML', '2026-09-23'), ('GRML', '2026-09-24'), ('JAGX', '2026-09-25'), ('MKDW', '2026-09-11'), ('MKDW', '2026-09-17'), ('NCT', '2026-09-22'), ('PCLA', '2026-09-10'), ('PCLA', '2026-09-11'), ('RLGT', '2026-09-15'), ('SDEV', '2026-10-05'), ('SRZN', '2026-09-24'), ('SVRN', '2026-09-21'), ('TNON', '2026-09-11'), ('VEEA', '2026-09-17'), ('VNCE', '2026-09-14'), ('XRPN', '2026-09-30')]
TICKS = sorted({t for t, _ in PAIRS})
DATES = sorted({d for _, d in PAIRS})


def j(v):
    return v if isinstance(v, (int, float, bool, str, type(None), list, dict)) else str(v)


async def main():
    pool = await get_pool()
    async with pool.acquire() as c:
        cols = await c.fetch("select column_name, data_type from information_schema.columns where table_name='mi_ep_alerts' order by ordinal_position")
        print("=== mi_ep_alerts cols:", [(r["column_name"]) for r in cols])
        dates = [date.fromisoformat(d) for d in DATES]
        rows = await c.fetch("select * from mi_ep_alerts where ticker = any($1) and (alert_date = any($2) or created_at::date = any($2)) order by ticker, created_at", TICKS, dates) \
            if any(r["column_name"] == "alert_date" for r in cols) else \
            await c.fetch("select * from mi_ep_alerts where ticker = any($1) and created_at::date = any($2) order by ticker, created_at", TICKS, dates)
        pairset = set(PAIRS)
        n = 0
        for r in rows:
            d = {k: j(v) for k, v in dict(r).items()}
            ad = str(d.get("alert_date") or str(d.get("created_at"))[:10])
            if (d["ticker"], ad) in pairset or (d["ticker"], str(d.get("created_at"))[:10]) in pairset:
                print("ALERT", json.dumps(d, default=str)[:3500]); n += 1
        print("=== alerts on lane ticker-days:", n)
        # scan log
        sl = await c.fetch("""select ticker, scan_date, min(scan_time_et) first_t, max(catalyst_quality) cq, max(llm_catalyst_quality) lcq, count(*) n,
                              max(ep_score) mx, max(score_tier) tier, min(filter_reason) fr, max(reject_stage) rs
                              from mi_ep_scan_log where ticker = any($1) and scan_date = any($2) group by ticker, scan_date order by scan_date, ticker""", TICKS, dates)
        for r in sl:
            if (r["ticker"], str(r["scan_date"])) in pairset:
                print("SCAN", json.dumps({k: j(v) for k, v in dict(r).items()}, default=str))
        # audit rows
        au = await c.fetch("""select created_at, event_type, summary, left(detail, 1500) detail from mi_audit_log
                              where (created_at at time zone 'America/New_York')::date = any($1)
                                and (event_type ilike '%catalyst%' or event_type ilike '%ep_%' or event_type ilike 'lowcap%' or event_type ilike '%mna%')
                              order by created_at""", dates)
        for r in au:
            s = (r["summary"] or "")
            hit = [t for t in TICKS if s.startswith(t) or (" " + t + " ") in (" " + s + " ") or ('"ticker": "%s"' % t) in (r["detail"] or "")]
            if hit:
                print("AUDIT", str(r["created_at"])[:19], r["event_type"], "|", s[:200], "|", (r["detail"] or "")[:600].replace("\n", " "))
asyncio.run(main())
