"""#672 — re-run Friday 2026-09-18's missed nightly jobs, with et_today PINNED to that date.

WHY THE PIN: 17 of the 21 missed job functions take no date parameter and read `et_today()`.
Run bare on a Saturday they record 2026-09-19, not Friday — a naive re-run is WORSE than the
gap it is meant to close. VERIFIED in the running container: every one of the 14 jobs below
routes its date through `et_today()`; none computes one with `datetime.now(_ET)` or
`date.today()`, so the pin reaches all of them.

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
import asyncio, datetime as _dt, sys

TARGET = _dt.date(2026, 9, 18)

# ── THE DATE PIN, and why it is a sys.modules walk and not one assignment ──────────────
# `et_today()` is defined in shared/dates.py and RE-EXPORTED widely. MEASURED in the running
# container on 2026-09-19: **10 modules hold their own `et_today` binding** — shared.dates,
# collector, rs_engine, regime, theme_engine, ep_detector, outcome_tracker, state_alerts and
# two more. A module that did `from ... import et_today` at import time keeps its OWN
# reference, so patching `collector.et_today` alone reaches ONE of the ten and the other nine
# still return Saturday. The first draft of this script did exactly that and would have
# recorded 09-19 while reporting success.
#
# So: import everything the jobs touch FIRST, then rebind every binding that exists, then
# ASSERT none is left. The assert is the point — a pin that silently half-applies is worse
# than no pin, because the rows look right until someone checks their date.
import agents.market_intelligence.scheduler          # noqa: F401  (pulls the graph in)
import agents.market_intelligence.db                 # noqa: F401
import agents.market_intelligence.theme_engine       # noqa: F401
import agents.market_intelligence.briefing           # noqa: F401
import shared.dates as _SD


def _pinned_today():
    return TARGET


def pin_the_clock() -> int:
    """Rebind et_today everywhere it is held. Returns how many bindings were pinned."""
    _SD.et_today = _pinned_today          # the source, so any LATER `from ... import` is pinned too
    n = 0
    for mod in list(sys.modules.values()):
        if mod is not None and callable(getattr(mod, "et_today", None)):
            setattr(mod, "et_today", _pinned_today)
            n += 1
    return n


def assert_pinned() -> None:
    bad = {}
    for name, mod in list(sys.modules.items()):
        f = getattr(mod, "et_today", None) if mod is not None else None
        if callable(f):
            try:
                v = f()
            except Exception as e:                      # pragma: no cover
                v = f"ERR {e}"
            if v != TARGET:
                bad[name] = v
    if bad:
        raise SystemExit(f"REFUSING TO RUN — {len(bad)} et_today binding(s) still not {TARGET}: {bad}")
    if _SD.last_trading_day() != TARGET:
        raise SystemExit(f"REFUSING TO RUN — last_trading_day() is {_SD.last_trading_day()}, not {TARGET}")
    # operator_today() is deliberately NOT pinned: it is the OPERATOR's clock, not market logic.


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
    n = pin_the_clock()
    assert_pinned()
    print(f"clock pinned to {TARGET} across {n} binding(s); last_trading_day()={_SD.last_trading_day()}")
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
