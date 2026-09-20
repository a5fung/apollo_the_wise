"""⛔ WRITTEN, THEN DELIBERATELY NOT RUN — the answer was that neither job should be re-run.

Kept because the runtime measurement and the bound are right, and because the REASON not to run
it is the useful part. The operator asked "are these jobs critical to rerun?" and the honest
answer, checked rather than assumed, was no:
  * `minute_volume_curves_refresh` writes `mi_minute_volume_curves`, keyed `(ticker, anchor,
    et_clock_minute)` with a `refreshed_at` and NO date column. It is a rolling BASELINE
    refreshed in place, so "re-running it for Friday" is not a thing — the next scheduled run
    overwrites it either way. Its only consumer is the judge's `tape` block, which the code says
    "the scan does NOT pass yet — gated on the eval + sign-off".
  * `analyst_estimates_snapshot` stamps `as_of_date`, documented `-- when this value was READ`.
    Re-running it on Sunday stamps Sunday's vendor values as Friday's reading. That is worse
    than the gap: readers query `as_of_date >= $N` WINDOWS, so a one-day hole costs nothing,
    while a fabricated stamp is undetectable in a join. Friday's grading ran at 18:12 Friday and
    nothing written now can reach it.

The 78 + 31 rows an earlier pass DID write this way were exported and deleted; see
`_678_find_backdated_writes.sql` for the query that found them and the rule for judging them.

The original point still stands and is why the file survives: the 600 s bound in `_677` was
mine, not theirs. Measured over 30 days, `analyst_estimates_snapshot` averages 1094 s and has
reached 2412 s; `minute_volume_curves_refresh` averages 933 s. Both are NORMALLY slower than the
bound I gave them, so "TIMEOUT" said nothing about the jobs.

ORIGINAL HEADER FOLLOWS.

The two jobs #677 CUT OFF — re-run with a bound matched to their measured runtime.

They did not fail on 2026-09-18 and they did not fail on re-run: I gave them 600 s, inherited from
the Friday runner where every job was a quick shadow. Measured over 30 days of `mi_job_runs`:
`analyst_estimates_snapshot` averages 1094 s and has reached 2412 s; `minute_volume_curves_refresh`
averages 933 s with a max of 1152 s. Both are NORMALLY slower than the bound I set, so the timeout
was mine, not theirs. `analyst_estimates_snapshot` had already written 78 + 31 rows when it was cut,
so its Friday data is PARTIAL rather than absent — which is worse, because a partial table looks
populated.

Bound here is 3600 s: above the observed max (2412 s) with room, and still bounded, because an
unbounded re-run is how the incident being recovered from started.

Sends go through `scripts/probes/_muzzle.py` — the httpx chokepoint — NOT a list of sender names.
The name list is what put Friday's watchlist on his phone twice this morning.
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
    ("analyst_estimates_snapshot",   "_analyst_estimates_snapshot_job"),
    ("minute_volume_curves_refresh", "_minute_volume_curves_refresh_job"),
]

from scripts.probes._muzzle import muzzle_telegram
CAPTURED = []


def muzzle() -> int:
    muzzle_telegram(CAPTURED)
    return 1

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
    m = muzzle()
    print(f"clock pinned to {TARGET} across {n} binding(s); last_trading_day()={_SD.last_trading_day()}")
    print(f"outbound messages MUZZLED across {m} binding(s) — nothing will be sent")
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
            r = await asyncio.wait_for(f(), timeout=3600)
            results.append((jid, f"ok ({r})")); print(f"  {jid:30s} ok -> {r}")
        except asyncio.TimeoutError:
            results.append((jid, "TIMEOUT 3600s")); print(f"  {jid:30s} TIMEOUT at 3600s")
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

    print(f"\n=== MESSAGES CAPTURED (NOT SENT): {len(CAPTURED)} ===")
    for who, text in CAPTURED:
        flat = " ".join(text.split())
        print(f"  [{who}] {flat[:160]}")
    fw = [t for w, t in CAPTURED if "watchlist" in t.lower() or "Watchlist" in t]
    if fw:
        print("\n=== friday_watchlist BODY IN FULL (its Telegram IS its product) ===")
        print(fw[0][:3000])

    print("\n=== PER-JOB ===")
    for j, r in results:
        print(f"  {j:30s} {r}")


if __name__ == "__main__":
    asyncio.run(main())
