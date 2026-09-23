"""Reconciliation script for the 3-bug batch fixed 2026-05-14.

Idempotent — safe to re-run. Performs:

  1. BW #119: revert pre-fill state (partial_taken=FALSE, total_pnl=0,
     exits=[]) since the actual partial fill hasn't happened yet.
     remaining_shares is already correct at 1163 (sync_positions did it).
     The pending Alpaca orders (#75 partial sell, #76 new stop) will
     fire tomorrow's open and finalize_partial_exit will repopulate.

  2. SNDK: remove from "Semiconductor Front-End Interconnect & Wafer
     Processing Equipment" (misclassification — SanDisk = memory),
     add to "AI Memory & Storage" (correct theme).

  3. Phantom-flagged splits: reset adjustment_applied=FALSE on the 10
     wrongly-skipped split rows so the fixed _apply_one can re-process
     them. Tickers: AIXI ASBP DKI KALA SMX (5/11), BNZI CVNA OLOX (5/08),
     MHVIY (5/13), SLMT (5/14).

  4. Then call _apply_one on each reset row to actually apply the
     adjustment with the corrected phantom check.
"""
import asyncio
import json

from agents.market_intelligence.db import (
    get_pool, assign_ticker_to_theme, log_audit_event,
)
from agents.market_intelligence.splits_ingest import _apply_one


PHANTOM_AFFECTED = [
    # (ticker, execution_date)
    ("AIXI",  "2026-05-11"),
    ("ASBP",  "2026-05-11"),
    ("DKI",   "2026-05-11"),
    ("KALA",  "2026-05-11"),
    ("SMX",   "2026-05-11"),
    ("BNZI",  "2026-05-08"),
    ("CVNA",  "2026-05-08"),
    ("OLOX",  "2026-05-08"),
    ("MHVIY", "2026-05-13"),
    ("SLMT",  "2026-05-14"),
]


async def reconcile_bw() -> None:
    print("=== 1. BW #119 reconciliation ===")
    pool = await get_pool()
    async with pool.acquire() as conn:
        before = await conn.fetchrow(
            "SELECT id, partial_taken, total_pnl, jsonb_typeof(exits) AS exits_type, remaining_shares "
            "FROM mi_live_trades WHERE id=119"
        )
        print(f"Before: {dict(before)}")
        await conn.execute(
            """
            UPDATE mi_live_trades SET
                partial_taken = FALSE,
                total_pnl = 0,
                exits = '[]'::jsonb,
                breakeven_active = FALSE
            WHERE id = 119
              AND (partial_taken = TRUE OR total_pnl != 0)
            """
        )
        after = await conn.fetchrow(
            "SELECT id, partial_taken, total_pnl, exits::text AS exits, remaining_shares "
            "FROM mi_live_trades WHERE id=119"
        )
        print(f"After: {dict(after)}")
        await log_audit_event(
            "manual_reconcile_bw_pre_fill",
            "BW #119: reverted pre-fill state (partial_taken, total_pnl, exits) "
            "since actual partial fill hasn't occurred yet. finalize_partial_exit "
            "will repopulate on tomorrow's WS fill.",
        )


async def reconcile_sndk() -> None:
    print("=== 2. SNDK theme reassignment ===")
    pool = await get_pool()
    async with pool.acquire() as conn:
        before_wrong = await conn.fetchrow(
            "SELECT tickers FROM mi_themes WHERE theme_date=CURRENT_DATE "
            "AND name='Semiconductor Front-End Interconnect & Wafer Processing Equipment'"
        )
        before_right = await conn.fetchrow(
            "SELECT tickers FROM mi_themes WHERE theme_date=CURRENT_DATE "
            "AND name='AI Memory & Storage'"
        )
        print(f"Wrong theme members before: {before_wrong['tickers'] if before_wrong else None}")
        print(f"Right theme members before: {before_right['tickers'] if before_right else None}")

        if before_wrong and 'SNDK' in (before_wrong['tickers'] or []):
            await conn.execute(
                "UPDATE mi_themes SET tickers = array_remove(tickers, 'SNDK') "
                "WHERE theme_date=CURRENT_DATE "
                "AND name='Semiconductor Front-End Interconnect & Wafer Processing Equipment'"
            )
            print("Removed SNDK from wrong theme.")
        else:
            print("SNDK already absent from wrong theme.")

    # Now add to correct theme via the existing helper
    result = await assign_ticker_to_theme("SNDK", "AI Memory & Storage")
    print(f"Assign result: matched={result['matched']}, "
          f"before={result['before']}, after={result['after']}")
    await log_audit_event(
        "manual_reconcile_sndk_theme",
        "SNDK moved from 'Semiconductor Front-End Interconnect & Wafer Processing Equipment' "
        "(misclassification — SanDisk = memory) to 'AI Memory & Storage'.",
    )


async def reconcile_phantom_splits() -> None:
    print(f"=== 3. Phantom-flagged splits ({len(PHANTOM_AFFECTED)} tickers) ===")
    pool = await get_pool()
    from datetime import date as _date
    for ticker, exec_date_str in PHANTOM_AFFECTED:
        exec_date = _date.fromisoformat(exec_date_str)
        async with pool.acquire() as conn:
            row = await conn.fetchrow(
                "SELECT ticker, execution_date, split_from, split_to, adjustment_applied "
                "FROM mi_splits WHERE ticker=$1 AND execution_date=$2",
                ticker, exec_date,
            )
            if not row:
                print(f"  {ticker} {exec_date_str}: no split row, skipping")
                continue
            # Reset
            await conn.execute(
                "UPDATE mi_splits SET adjustment_applied=FALSE, applied_at=NULL "
                "WHERE ticker=$1 AND execution_date=$2",
                ticker, exec_date,
            )
        # Re-apply with the fixed phantom check
        result = await _apply_one(dict(row))
        print(f"  {ticker} {exec_date_str}: re-applied → {result[0]} success={result[1]} bars={result[2]}")

    await log_audit_event(
        "manual_reconcile_phantom_splits",
        f"Reset adjustment_applied=FALSE and re-applied {len(PHANTOM_AFFECTED)} split rows "
        f"wrongly flagged as phantom by the broken pre-fix check. Tickers: "
        f"{', '.join(t for t, _ in PHANTOM_AFFECTED)}.",
    )


async def verify() -> None:
    print("=== 4. Verification ===")
    pool = await get_pool()
    async with pool.acquire() as conn:
        # BW
        bw = await conn.fetchrow(
            "SELECT id, partial_taken, total_pnl, remaining_shares, exits::text "
            "FROM mi_live_trades WHERE id=119"
        )
        print(f"  BW: {dict(bw)}")

        # SNDK
        sndk_themes = await conn.fetch(
            "SELECT name FROM mi_themes WHERE theme_date=CURRENT_DATE "
            "AND 'SNDK'=ANY(tickers) ORDER BY name"
        )
        print(f"  SNDK in themes today: {[r['name'] for r in sndk_themes]}")

        # AIXI close history
        aixi = await conn.fetch(
            "SELECT trade_date, close FROM mi_daily_closes "
            "WHERE ticker='AIXI' AND trade_date BETWEEN '2026-05-06' AND '2026-05-14' "
            "ORDER BY trade_date"
        )
        print("  AIXI daily closes 5/06-5/14:")
        for r in aixi:
            print(f"    {r['trade_date']}: ${float(r['close']):.4f}")


async def main() -> None:
    await reconcile_bw()
    print()
    await reconcile_sndk()
    print()
    await reconcile_phantom_splits()
    print()
    await verify()


if __name__ == "__main__":
    asyncio.run(main())
