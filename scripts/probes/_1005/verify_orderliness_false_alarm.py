"""2026-10-05 read-only adversarial re-check of the 'orderliness dead column = false alarm' verdict:
(1) is the column populated now and does the BOARD the operator reads show it; (2) when did the
column reach the server; (3) for every past dead-column alarm, would a 'quiet first night, alert if
rows written after the sighting are still empty' rule have stayed quiet or alerted."""
import asyncio
from datetime import datetime, timedelta, time as dtime
from zoneinfo import ZoneInfo
from agents.market_intelligence.db import get_pool, get_consolidation_board

ET = ZoneInfo("America/New_York")
T = "AT TIME ZONE 'America/New_York'"


def next_sweep(t):
    d = t.date() + timedelta(days=1)
    while d.weekday() >= 5:
        d += timedelta(days=1)
    return datetime.combine(d, dtime(17, 30), tzinfo=ET)


async def main():
    pool = await get_pool()
    async with pool.acquire() as c:
        print("now ET:", await c.fetchval(f"SELECT (now() {T})::text"))
        r = await c.fetchrow(f"""SELECT count(*) n, count(orderliness) n_ord,
                 (SELECT max(last_eval) FROM mi_anticipation_consolidation) max_eval,
                 count(*) FILTER (WHERE last_eval=(SELECT max(last_eval) FROM mi_anticipation_consolidation)) n_latest,
                 count(orderliness) FILTER (WHERE last_eval=(SELECT max(last_eval) FROM mi_anticipation_consolidation)) n_latest_ord,
                 count(*) FILTER (WHERE orderliness='NaN'::float) n_nan
                 FROM mi_anticipation_consolidation""")
        print("== table:", dict(r))
        print("== distinct orderliness values tonight:",
              await c.fetchval("""SELECT count(DISTINCT round(orderliness::numeric,4)) FROM mi_anticipation_consolidation
                                  WHERE orderliness IS NOT NULL"""))
        board = await get_consolidation_board()
        print(f"== board rows (what /anticipation reads): {len(board)}, unscored: "
              f"{sum(1 for b in board if b.get('orderliness') is None)}")
        for b in board[:5]:
            print("   ", b["ticker"], b["state"], b.get("orderliness"))
        print("== boot/deploy audit rows since Sat 10-03 18:00 ET")
        for x in await c.fetch(f"""SELECT (created_at {T})::text t, event_type, LEFT(summary,140) s FROM mi_audit_log
                 WHERE created_at > '2026-10-03 22:00+00' AND (event_type ILIKE '%boot%' OR event_type ILIKE '%deploy%'
                 OR event_type ILIKE '%startup%' OR event_type ILIKE '%preflight%') ORDER BY created_at LIMIT 30"""):
            print("   ", x["t"], x["event_type"], "|", x["s"])
        print("== was there a consolidation_readiness run between Sat 10-03 and tonight?")
        for x in await c.fetch(f"""SELECT job_id, status, (started_at {T})::text s FROM mi_job_runs
                 WHERE job_id='consolidation_readiness' AND started_at > '2026-10-02 12:00+00' ORDER BY started_at"""):
            print("   ", dict(x))

        print("== replay: would 'quiet first night, alert night 2 if rows written after the sighting are all empty' fire?")
        rows = await c.fetch("""SELECT created_at, summary FROM mi_audit_log
                                WHERE event_type='dead_column_detected' ORDER BY created_at""")
        for a in rows:
            tbl, col = a["summary"].split(".", 1)
            flag_t = a["created_at"].astimezone(ET)
            nxt = next_sweep(flag_t)
            try:
                tcols = {x["column_name"] for x in await c.fetch(
                    "SELECT column_name FROM information_schema.columns WHERE table_schema='public' AND table_name=$1", tbl)}
                ts = next((x for x in ("updated_at", "created_at", "computed_at", "recorded_at", "logged_at") if x in tcols), None)
                if ts is None:
                    print(f"  {flag_t:%m-%d %H:%M} {a['summary']:55s} no ts col -> night-2 fallback alert"); continue
                first = await c.fetchval(f'SELECT min("{ts}") FROM "{tbl}" WHERE "{col}" IS NOT NULL')
                if first is not None and first <= nxt:
                    verdict = f"QUIET (filled {first.astimezone(ET):%m-%d %H:%M} before night-2 sweep)"
                else:
                    n_between = await c.fetchval(
                        f'SELECT count(*) FROM "{tbl}" WHERE "{ts}" > $1 AND "{ts}" <= $2', flag_t, nxt)
                    verdict = (f"ALERT night 2 ({n_between} rows written in between, col empty)" if n_between
                               else "QUIET (no new rows by night 2)")
                    fs = f"{first.astimezone(ET):%m-%d %H:%M}" if first else "never"
                    verdict += f"; first filled {fs}"
                print(f"  {flag_t:%m-%d %H:%M} {a['summary']:55s} [{ts}] {verdict}")
            except Exception as e:
                print(f"  {a['summary']} ERR {type(e).__name__}: {str(e)[:100]}")


asyncio.run(main())
