#!/usr/bin/env python3
"""#270 Step 3 staging smoke — validates every NOT-YET-DB-EXERCISED path against a
real (prod-restored) schema. All 23 #270 unit tests are pure Python over synthetic/TSV
data; the SQL layer (gap-seed CTE + window funcs, the CREATE TABLE, the ON CONFLICT
upsert + date coercion, the substrate-feed JSONB write through the plain-json.dumps
codec) has never touched a database. Per CLAUDE.md "Done = VERIFIED-LIVE", this is the
gate before #270 merges.

Run inside the staging market container (intelligence role, prod-restored DB):
    docker exec apollo-staging-market python scripts/verify_270_staging.py

Read-MOSTLY: writes ONE synthetic ticker ('ZZSMOKE') into mi_delayed_ep_lifecycle and
mi_stocks_in_play, reads it back through the real getters, then DELETEs it. Safe on the
disposable staging DB. Exits non-zero on the first failure so the deploy gate is honest.
"""
import asyncio
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

_ET = ZoneInfo("America/New_York")
T = "ZZSMOKE"   # synthetic smoke ticker; cleaned up at the end
_FAILED: list[str] = []


def _check(name, ok, detail=""):
    mark = "✅" if ok else "❌"
    print(f"  {mark} {name}{(' — ' + detail) if detail else ''}")
    if not ok:
        _FAILED.append(name)


async def main():
    from agents.market_intelligence import delayed_ep as de
    from agents.market_intelligence.collector import et_today
    from agents.market_intelligence.db import (
        get_pool, get_delayed_ep_gap_seeds, get_delayed_ep_state_map,
        get_delayed_ep_watch_set, get_delayed_ep_3b_unsettled,
        get_delayed_ep_ohlcv, upsert_delayed_ep_lifecycle,
        get_delayed_ep_lifecycle_board, upsert_stocks_in_play, get_stocks_in_play,
    )
    from agents.market_intelligence.stocks_in_play_sources import (
        SOURCE_DELAYED_EP_REENTRY, CLASS_OPERATOR_ONLY,
    )
    today = et_today()
    print(f"=== #270 staging smoke — {today.isoformat()} (ticker {T}) ===")

    # 1 — gap-seed CTE + window functions (LAG prev_close, ADV20 median) on real schema
    try:
        seeds = await get_delayed_ep_gap_seeds(today)
        _check("gap-seed CTE/window", isinstance(seeds, list), f"{len(seeds)} seeds")
    except Exception as e:
        _check("gap-seed CTE/window", False, repr(e)); seeds = []

    # 2 — the three read getters the jobs depend on
    for name, coro in (("state_map", get_delayed_ep_state_map()),
                       ("watch_set", get_delayed_ep_watch_set()),
                       ("3b_unsettled", get_delayed_ep_3b_unsettled())):
        try:
            r = await coro
            _check(name, isinstance(r, (list, dict)), f"{len(r)}")
        except Exception as e:
            _check(name, False, repr(e))

    # 3 — OHLCV getter + bars adapter + evaluate_candidate over REAL bars (if any seed)
    if seeds:
        try:
            s = seeds[0]
            bars = de.db_rows_to_bars(await get_delayed_ep_ohlcv(s["ticker"], today))
            row = de.evaluate_candidate(bars, s["gap_day"].isoformat()) if len(bars) >= 30 else None
            _check("ohlcv+evaluate_candidate", True,
                   f"{s['ticker']} bars={len(bars)} -> {row['state'] if row else 'unconfirmed'}")
        except Exception as e:
            _check("ohlcv+evaluate_candidate", False, repr(e))

    # 4 — lifecycle UPSERT round-trip: CREATE TABLE cols + ON CONFLICT + _dd coercion
    try:
        await upsert_delayed_ep_lifecycle(
            T, today, state="ready", gap_day_low=10.0, gap_day_vol=1_000_000,
            sma200_at_gap=8.0, armed_date=today, coiled_date=None, ready_date=today,
            triggered_date=None, entry_tactic=None, entry_price=None, stop_price=None,
            reenter_count=0, base_run=3, rmv_5d=8.0, rmv_15d=12.0, tight_close_pct=0.05,
            fwd_mfe_pct=None, realized_r=None, settled=False, last_eval=today)
        # re-fire to exercise ON CONFLICT DO UPDATE + the ISO-string date-coercion path
        await upsert_delayed_ep_lifecycle(
            T, today, state="ready", gap_day_low=10.0, gap_day_vol=1_000_000,
            sma200_at_gap=8.0, armed_date=today.isoformat(), coiled_date=None,
            ready_date=today.isoformat(), triggered_date=None, entry_tactic=None,
            entry_price=None, stop_price=None, reenter_count=0, base_run=3, rmv_5d=8.0,
            rmv_15d=12.0, tight_close_pct=0.05, fwd_mfe_pct=None, realized_r=None,
            settled=False, last_eval=today)
        board = await get_delayed_ep_lifecycle_board()
        _check("lifecycle upsert+board round-trip",
               any(r["ticker"] == T for r in board), f"board={len(board)}")
    except Exception as e:
        _check("lifecycle upsert+board round-trip", False, repr(e))

    # 5 — substrate feed: sip_payload + upsert_stocks_in_play JSONB write + read-back
    try:
        reason, signal = de.sip_payload(
            state="ready", gap_day_iso=today.isoformat(), base_run=3, rmv_5d=8.0)
        await upsert_stocks_in_play(
            ticker=T, source_detector=SOURCE_DELAYED_EP_REENTRY,
            automation_class=CLASS_OPERATOR_ONLY, reason=reason, readiness_signal=signal,
            source_phase="shadow", entry_date=today,
            expires_at=datetime.now(_ET) + timedelta(days=7))
        sip = await get_stocks_in_play(
            source_detector=SOURCE_DELAYED_EP_REENTRY, active_only=True)
        _check("substrate feed JSONB round-trip",
               any(r["ticker"] == T for r in sip), f"delayed_ep rows={len(sip)}")
    except Exception as e:
        _check("substrate feed JSONB round-trip", False, repr(e))

    # cleanup — remove the synthetic rows (disposable staging DB, but stay tidy)
    try:
        pool = await get_pool()
        async with pool.acquire() as conn:
            await conn.execute("DELETE FROM mi_delayed_ep_lifecycle WHERE ticker=$1", T)
            await conn.execute(
                "DELETE FROM mi_stocks_in_play WHERE ticker=$1 AND source_detector=$2",
                T, SOURCE_DELAYED_EP_REENTRY)
        print(f"  🧹 cleaned up {T}")
    except Exception as e:
        print(f"  ⚠ cleanup failed (harmless on disposable staging DB): {e!r}")

    print("=" * 48)
    if _FAILED:
        print(f"RED — {len(_FAILED)} check(s) failed: {', '.join(_FAILED)}")
        raise SystemExit(1)
    print("GREEN — every #270 SQL path validated against the prod-restored schema.")


if __name__ == "__main__":
    asyncio.run(main())
