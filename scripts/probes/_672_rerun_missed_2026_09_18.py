"""#672 — re-run Friday 2026-09-18's missed nightly jobs, with et_today PINNED to that date.

WHY THE PIN: 17 of the 21 missed job functions take no date parameter and read `et_today()`.
Run bare on a Saturday they record 2026-09-19, not Friday — a naive re-run is WORSE than the
gap it is meant to close.

SAFETY, all of it: snapshots row counts for every mi_* table before and after, fingerprints
mi_live_trades (THE LINE — this must not move), bounds every job at 600s so this script cannot
reproduce the very hang it exists to recover from, and reports per-job outcome.

DELIBERATELY EXCLUDED and why:
  evening_briefing / spend_alarm / strength_spread_alert — they Telegram the operator, and the
      content would be Friday's arriving on Saturday. His call, not mine.
  theme_synthesis — weekend-guarded, would no-op.
  crypto_nightly_ingest — scheduled mon-sun, tonight's own run covers it.
  model_resolution_refresh / judge_eval_divergence_check — daily and self-correcting.

Run: docker cp this into apollo-market, then `docker exec apollo-market python <path>`.
"""
import asyncio, datetime as _dt

TARGET = _dt.date(2026, 9, 18)
import agents.market_intelligence.collector as c
c.et_today = lambda: TARGET
from agents.market_intelligence import scheduler as sch
from agents.market_intelligence.db import get_pool

JOBS = [
    ("flag_continuation_scan",      "_flag_scan_job"),
    ("parabolic_scan",              "_parabolic_scan_job"),
    ("sugar_babies_cohort_refresh", "_sugar_babies_cohort_refresh_job"),
    ("consolidation_readiness",     "_consolidation_readiness_job"),
    ("alert_rank_shadow",           "_alert_rank_shadow_job"),
    ("exit_path_shadow",            "_exit_path_shadow_job"),
    ("sell_discipline_recorder",    "_sell_discipline_recorder_job"),
    ("delayed_entry_shadow",        "_delayed_entry_shadow_job"),
    ("live_fill_counterfactuals",   "_live_fill_counterfactuals_job"),
    ("wick_forward_returns",        "_wick_forward_returns_job"),
    ("theme_axis_co_move_refresh",  "_theme_axis_co_move_refresh_job"),
    ("theme_axis_eod_unscored",     "_theme_axis_eod_unscored_job"),
    ("coverage_probe",              "_coverage_probe_job"),
    ("post_nightly_audit",          "_post_nightly_audit_job"),
]


async def snapshot(conn):
    tabs = [r["table_name"] for r in await conn.fetch(
        "SELECT table_name FROM information_schema.tables "
        "WHERE table_schema='public' AND table_name LIKE 'mi\\_%' ORDER BY 1")]
    out = {}
    for t in tabs:
        try:
            out[t] = await conn.fetchval(f'SELECT count(*) FROM "{t}"')
        except Exception:
            out[t] = None
    return out


async def trade_fingerprint(conn):
    return await conn.fetchval(
        "SELECT md5(string_agg(id::text||coalesce(status,'')||coalesce(stop_order_id,''), '|' "
        "ORDER BY id)) FROM mi_live_trades")


async def main():
    pool = await get_pool()
    async with pool.acquire() as conn:
        before, fp_before = await snapshot(conn), await trade_fingerprint(conn)
    print(f"snapshot: {len(before)} mi_* tables; live-trade fingerprint {fp_before}")

    results = []
    for jid, fn in JOBS:
        f = getattr(sch, fn, None)
        if f is None:
            results.append((jid, "NO SUCH FN")); print(f"  {jid:30s} NO SUCH FN"); continue
        try:
            r = await asyncio.wait_for(f(), timeout=600)
            results.append((jid, f"ok ({r})")); print(f"  {jid:30s} ok -> {r}")
        except asyncio.TimeoutError:
            results.append((jid, "TIMEOUT 600s")); print(f"  {jid:30s} TIMEOUT at 600s")
        except Exception as e:
            results.append((jid, f"ERR {type(e).__name__}: {e}"))
            print(f"  {jid:30s} ERROR {type(e).__name__}: {str(e)[:120]}")

    async with pool.acquire() as conn:
        after, fp_after = await snapshot(conn), await trade_fingerprint(conn)

    print("\n=== ROW-COUNT DELTAS ===")
    seen = False
    for t in sorted(after):
        b, a = before.get(t), after.get(t)
        if b is not None and a is not None and a != b:
            seen = True; print(f"  {t:44s} {b:>7} -> {a:>7}  ({a - b:+d})")
    if not seen:
        print("  (no row-count change in any mi_* table)")

    print("\n=== LIVE TRADE STATE ===")
    print("  UNCHANGED" if fp_before == fp_after else f"  CHANGED {fp_before} -> {fp_after}")

    print("\n=== PER-JOB ===")
    for j, r in results:
        print(f"  {j:30s} {r}")


if __name__ == "__main__":
    asyncio.run(main())
