"""Nightly crypto RS ingest orchestrator.

One entry point: `run_nightly()` — invoked by scheduler at 18:00 ET (after
the equity post-nightly audit at 17:30). Idempotent and self-contained.

Pipeline:
1. Resolve any pending watchlist entries (one-time per coin)
2. Refresh universe from CoinGecko (top 250 by mcap) ∪ watchlist
3. Pull/refresh daily history for each coin via data_router
4. Compute crypto_rs_scores for today
5. Pull macro indicators (BTC.D, TOTAL3, stablecoin supply)
6. Evaluate the three-signal alt-season trigger
7. Audit log; Telegram surface only if CRYPTO_RS_ENABLED=true

Wash-trade gate (vol/mcap ratio + 90d age + 7d median vol) applied at the
universe-membership level — watchlist coins exempt regardless of liquidity.
"""
from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timedelta
from typing import Optional
from zoneinfo import ZoneInfo

from agents.market_intelligence.constants import CRYPTO_RS_ENABLED
from agents.market_intelligence.db import get_pool, log_audit_event
from agents.market_intelligence.crypto import (
    coingecko_client as cg,
    data_router,
    resolver,
    rs_engine,
    triggers,
)
from agents.market_intelligence.crypto.categories import (
    refresh_category_membership,
    compute_category_strength,
)
from agents.market_intelligence.crypto.db import (
    get_watchlist,
    upsert_daily_close,
)

logger = logging.getLogger(__name__)
_ET = ZoneInfo("America/New_York")

# Wash-trade gate (universe coins; watchlist exempt)
MIN_FLOOR_MCAP = 15_000_000  # universe floor; below = watchlist-only
MAX_VOL_MCAP_RATIO = 5.0      # > 5x = wash trade (volume can't sustainably exceed mcap)
MIN_VOL_MCAP_RATIO = 0.01    # < 1% = effectively dead


async def run_nightly() -> dict:
    """Main entry point. Returns a stats dict for the scheduler / audit log."""
    today = datetime.now(_ET).date()
    stats = {
        "date": today.isoformat(),
        "started_at": datetime.now(_ET).isoformat(),
        "shadow_mode": not CRYPTO_RS_ENABLED,
    }

    # Pull universe ONCE; reuse for both resolver and universe refresh.
    try:
        universe_rows = await cg.get_top_universe(per_page=250)
    except Exception:
        logger.exception("Universe fetch failed")
        stats["universe_size"] = 0
        await log_audit_event("crypto_ingest_error", "universe fetch failed", "")
        return stats

    try:
        resolved = await resolver.resolve_pending_watchlist(prefetched_universe=universe_rows)
        stats["watchlist_resolved"] = resolved
    except Exception:
        logger.exception("Resolver step failed (non-fatal)")
        stats["watchlist_resolved"] = -1

    try:
        universe_size = await _persist_universe(universe_rows)
        stats["universe_size"] = universe_size
    except Exception:
        logger.exception("Universe persist failed")
        stats["universe_size"] = 0
        await log_audit_event("crypto_ingest_error", "universe persist failed", "")
        return stats

    try:
        n_coins, n_bars = await _pull_daily_bars(today)
        stats["coins_with_bars"] = n_coins
        stats["bars_upserted"] = n_bars
    except Exception:
        logger.exception("Daily bar pull failed")
        stats["bars_upserted"] = 0

    try:
        n_scored = await _compute_and_store_rs(today)
        stats["coins_scored"] = n_scored
    except Exception:
        logger.exception("RS computation failed")
        stats["coins_scored"] = 0

    try:
        n_cats = await compute_category_strength(today)
        stats["categories_scored"] = n_cats
    except Exception:
        logger.exception("Category strength failed (non-fatal)")
        stats["categories_scored"] = 0

    try:
        macro = await _persist_macro(today)
        stats["macro_sources_ok"] = macro.get("sources_ok") or []
    except Exception:
        logger.exception("Macro persist failed")
        stats["macro_sources_ok"] = []

    try:
        trigger_result = await _evaluate_and_record_trigger(today)
        stats["trigger"] = {
            "fired": trigger_result.get("fired"),
            "reason": trigger_result.get("reason"),
        }
    except Exception:
        logger.exception("Trigger evaluation failed")
        stats["trigger"] = {"fired": False, "reason": "evaluation_error"}

    stats["finished_at"] = datetime.now(_ET).isoformat()
    await log_audit_event(
        "crypto_ingest_completed",
        f"date={today} universe={stats.get('universe_size')} scored={stats.get('coins_scored')} "
        f"trigger={stats['trigger'].get('fired')} shadow={stats['shadow_mode']}",
        str(stats)[:8000],
    )
    return stats


async def _persist_universe(universe: list[dict]) -> int:
    """Persist top-250 universe + watchlist union to crypto_universe.

    Wash-trade gate applies to top-250 rows; watchlist coins exempt.
    Single transaction with executemany — no per-row round-trip.
    """
    pool = await get_pool()
    today = datetime.now(_ET).date()

    # Filter top-250 through wash-trade gate.
    keep_rows: list[tuple] = []
    for row in universe:
        mcap = row.get("market_cap") or 0.0
        volume = row.get("total_volume") or 0.0
        if mcap < MIN_FLOOR_MCAP:
            continue
        ratio = (volume / mcap) if mcap > 0 else 0.0
        if not (MIN_VOL_MCAP_RATIO <= ratio <= MAX_VOL_MCAP_RATIO):
            continue
        keep_rows.append((
            row.get("id"),
            (row.get("symbol") or "").upper(),
            row.get("name"),
            row.get("market_cap_rank"),
            mcap,
            today,
        ))

    async with pool.acquire() as conn:
        async with conn.transaction():
            await conn.executemany(
                """
                INSERT INTO crypto_universe (coin_id, symbol, name, mcap_rank, mcap_usd, last_seen)
                VALUES ($1, $2, $3, $4, $5, $6)
                ON CONFLICT (coin_id) DO UPDATE SET
                    symbol = EXCLUDED.symbol,
                    name = EXCLUDED.name,
                    mcap_rank = EXCLUDED.mcap_rank,
                    mcap_usd = EXCLUDED.mcap_usd,
                    last_seen = EXCLUDED.last_seen
                """,
                keep_rows,
            )
            # Union watchlist (exempt from wash-trade gate).
            wl_rows = await conn.fetch(
                "SELECT coin_id, symbol FROM crypto_watchlist "
                "WHERE coin_id NOT LIKE '_unresolved_%'"
            )
            wl_inserts = [
                (w["coin_id"], w["symbol"], today) for w in wl_rows
            ]
            if wl_inserts:
                await conn.executemany(
                    """
                    INSERT INTO crypto_universe (coin_id, symbol, last_seen)
                    VALUES ($1, $2, $3)
                    ON CONFLICT DO NOTHING
                    """,
                    wl_inserts,
                )
    return len(keep_rows) + len(wl_rows)


async def _pull_daily_bars(today) -> tuple[int, int]:
    """For each universe coin, pull historical bars (Kraken-first, CG fallback).

    Per-coin: one HTTP fetch + one batched executemany for the whole bar window.
    Replaces the prior 50k-statement N+1 (one upsert per bar).
    """
    pool = await get_pool()
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            "SELECT coin_id, symbol FROM crypto_universe ORDER BY mcap_rank NULLS LAST"
        )

    n_coins = 0
    n_bars = 0
    sem = asyncio.Semaphore(3)  # bound concurrent HTTP fanout

    async def _fetch_one(coin_id: str, symbol: str) -> tuple[int, int]:
        async with sem:
            try:
                bars = await data_router.fetch_daily_history(coin_id, symbol, days=200)
            except Exception:
                logger.exception("history fetch failed for %s", symbol)
                return 0, 0
            if not bars:
                return 0, 0
            # Single connection acquire + executemany — pool isn't held while awaiting HTTP.
            tuples = [
                (
                    coin_id,
                    b["date"],
                    b.get("close_usd"),
                    None,  # close_btc filled later in _compute_and_store_rs
                    b.get("volume_usd"),
                    b.get("mcap_usd"),
                    b.get("source", "unknown"),
                )
                for b in bars
            ]
            async with pool.acquire() as conn2:
                await conn2.executemany(
                    """
                    INSERT INTO crypto_daily_closes
                        (coin_id, date, close_usd, close_btc, volume_usd, mcap_usd, source)
                    VALUES ($1, $2, $3, $4, $5, $6, $7)
                    ON CONFLICT (coin_id, date) DO UPDATE SET
                        close_usd = COALESCE(EXCLUDED.close_usd, crypto_daily_closes.close_usd),
                        close_btc = COALESCE(EXCLUDED.close_btc, crypto_daily_closes.close_btc),
                        volume_usd = COALESCE(EXCLUDED.volume_usd, crypto_daily_closes.volume_usd),
                        mcap_usd = COALESCE(EXCLUDED.mcap_usd, crypto_daily_closes.mcap_usd),
                        source = EXCLUDED.source
                    """,
                    tuples,
                )
            return 1, len(bars)

    results = await asyncio.gather(*[
        _fetch_one(r["coin_id"], r["symbol"]) for r in rows
    ])
    for c, b in results:
        n_coins += c
        n_bars += b
    return n_coins, n_bars


async def _compute_and_store_rs(today) -> int:
    """Compute RS for every coin with sufficient history; persist to crypto_rs_scores.

    Bulk-load history via single SELECT WHERE coin_id = ANY($1) (replaces N+1).
    Bulk close_btc backfill via UPDATE FROM (VALUES ...) join.
    """
    pool = await get_pool()
    history_window_start = today - timedelta(days=200)

    async with pool.acquire() as conn:
        coins = await conn.fetch(
            "SELECT coin_id, symbol, mcap_usd FROM crypto_universe"
        )
        coin_ids = [c["coin_id"] for c in coins]

        # Bulk-load all history in one shot — was 250 separate fetches.
        all_history = await conn.fetch(
            """
            SELECT coin_id, date, close_usd FROM crypto_daily_closes
            WHERE coin_id = ANY($1) AND date >= $2
            ORDER BY coin_id, date ASC
            """,
            coin_ids, history_window_start,
        )

    # Group history by coin in Python (cheap; no DB round-trip).
    history_by_coin: dict[str, list[dict]] = {}
    for r in all_history:
        history_by_coin.setdefault(r["coin_id"], []).append({
            "date": r["date"],
            "close_usd": float(r["close_usd"]) if r["close_usd"] else None,
        })

    btc_history = history_by_coin.get("bitcoin", [])
    btc_closes = {row["date"]: row["close_usd"] for row in btc_history if row.get("close_usd")}
    if not btc_closes:
        logger.warning("RS: no BTC history yet; skipping scoring this run")
        return 0

    coins_data = [
        {
            "coin_id": c["coin_id"],
            "symbol": c["symbol"],
            "mcap_usd": float(c["mcap_usd"]) if c["mcap_usd"] else None,
            "daily_closes": history_by_coin.get(c["coin_id"], []),
        }
        for c in coins
    ]

    scores = rs_engine.compute_rs_scores(coins_data, btc_closes, today)

    # Build close_btc backfill tuples in Python.
    backfill_tuples: list[tuple] = []
    for c in coins_data:
        for row in c["daily_closes"]:
            btc_close = btc_closes.get(row["date"])
            if btc_close and row.get("close_usd"):
                backfill_tuples.append((
                    float(row["close_usd"]) / btc_close,
                    c["coin_id"],
                    row["date"],
                ))

    score_tuples = [
        (
            s["coin_id"], s["score_date"], s["rs_1m"], s["rs_3m"], s["rs_6m"],
            s["rs_composite"], s["mcap_bucket"], s["rs_in_bucket"], s["rs_overall"],
        )
        for s in scores
    ]

    async with pool.acquire() as conn:
        async with conn.transaction():
            await conn.executemany(
                """
                INSERT INTO crypto_rs_scores
                    (coin_id, score_date, rs_1m, rs_3m, rs_6m, rs_composite,
                     mcap_bucket, rs_in_bucket, rs_overall)
                VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9)
                ON CONFLICT (coin_id, score_date) DO UPDATE SET
                    rs_1m = EXCLUDED.rs_1m,
                    rs_3m = EXCLUDED.rs_3m,
                    rs_6m = EXCLUDED.rs_6m,
                    rs_composite = EXCLUDED.rs_composite,
                    mcap_bucket = EXCLUDED.mcap_bucket,
                    rs_in_bucket = EXCLUDED.rs_in_bucket,
                    rs_overall = EXCLUDED.rs_overall
                """,
                score_tuples,
            )
            if backfill_tuples:
                await conn.executemany(
                    """
                    UPDATE crypto_daily_closes
                       SET close_btc = $1
                     WHERE coin_id = $2 AND date = $3
                    """,
                    backfill_tuples,
                )

    return len(scores)


async def _persist_macro(today) -> dict:
    """Pull BTC.D + TOTAL3 + stablecoin supply, persist daily snapshot."""
    pool = await get_pool()
    macro = await data_router.fetch_macro_indicators()

    async with pool.acquire() as conn:
        if "coingecko" in (macro.get("sources_ok") or []):
            await conn.execute(
                """
                INSERT INTO crypto_btc_dominance (date, dominance_pct, total_mcap_usd)
                VALUES ($1, $2, $3)
                ON CONFLICT (date) DO UPDATE SET
                    dominance_pct = EXCLUDED.dominance_pct,
                    total_mcap_usd = EXCLUDED.total_mcap_usd
                """,
                today, macro.get("btc_dominance_pct"), macro.get("total_market_cap_usd"),
            )
            await conn.execute(
                """
                INSERT INTO crypto_total3 (date, total3_mcap_usd)
                VALUES ($1, $2)
                ON CONFLICT (date) DO UPDATE SET
                    total3_mcap_usd = EXCLUDED.total3_mcap_usd
                """,
                today, macro.get("total3_mcap_usd"),
            )
        if "defillama" in (macro.get("sources_ok") or []):
            await conn.execute(
                """
                INSERT INTO crypto_stablecoin_flows
                    (date, total_stable_mcap, usdt_mcap, usdc_mcap)
                VALUES ($1, $2, $3, $4)
                ON CONFLICT (date) DO UPDATE SET
                    total_stable_mcap = EXCLUDED.total_stable_mcap,
                    usdt_mcap = EXCLUDED.usdt_mcap,
                    usdc_mcap = EXCLUDED.usdc_mcap
                """,
                today, macro.get("major_stables_mcap"),
                macro.get("usdt_mcap"), macro.get("usdc_mcap"),
            )
    return macro


async def _evaluate_and_record_trigger(today) -> dict:
    """Pull 90d of macro history, evaluate alt-season trigger, log + alert."""
    pool = await get_pool()

    async with pool.acquire() as conn:
        btc_rows = await conn.fetch(
            "SELECT date, dominance_pct FROM crypto_btc_dominance "
            "WHERE date >= $1 ORDER BY date ASC",
            today - timedelta(days=120),
        )
        total3_rows = await conn.fetch(
            "SELECT date, total3_mcap_usd FROM crypto_total3 "
            "WHERE date >= $1 ORDER BY date ASC",
            today - timedelta(days=120),
        )
        stable_rows = await conn.fetch(
            "SELECT date, total_stable_mcap FROM crypto_stablecoin_flows "
            "WHERE date >= $1 ORDER BY date ASC",
            today - timedelta(days=120),
        )
        last_alert_row = await conn.fetchrow(
            "SELECT triggered_at FROM crypto_dominance_alerts "
            "ORDER BY triggered_at DESC LIMIT 1"
        )

    # asyncpg returns TIMESTAMPTZ as timezone-aware UTC datetime; convert to ET
    # before .date() so cooldown dates match the rest of the codebase.
    last_alert_at = (
        last_alert_row["triggered_at"].astimezone(_ET).date()
        if last_alert_row else None
    )
    btc_hist = [(r["date"], float(r["dominance_pct"])) for r in btc_rows if r["dominance_pct"]]
    total3_hist = [(r["date"], float(r["total3_mcap_usd"])) for r in total3_rows if r["total3_mcap_usd"]]
    stable_hist = [(r["date"], float(r["total_stable_mcap"])) for r in stable_rows if r["total_stable_mcap"]]

    result = triggers.evaluate_alt_season(
        btc_dominance_history=btc_hist,
        total3_history=total3_hist,
        stablecoin_history=stable_hist,
        last_alert_at=last_alert_at,
        today=today,
    )

    if result["fired"]:
        async with pool.acquire() as conn:
            await conn.execute(
                """
                INSERT INTO crypto_dominance_alerts
                    (btc_d_pct, total3_breakout, stable_slope_30d, alert_type, cooldown_until)
                VALUES ($1, true, $2, 'three_signal_fired', $3)
                """,
                result["signals"]["btc_dominance_breakdown"]["current_pct"],
                result["signals"]["stable_slope_positive"]["slope"],
                datetime.now(_ET) + timedelta(days=triggers.COOLDOWN_DAYS),
            )
        await log_audit_event(
            "crypto_trigger_fired",
            f"alt-season three-signal trigger fired (shadow={not CRYPTO_RS_ENABLED})",
            str(result)[:8000],
        )
        if CRYPTO_RS_ENABLED:
            from agents.market_intelligence.crypto.briefing import send_alt_season_alert
            await send_alt_season_alert(result, today)
    elif result.get("pre_arm"):
        await log_audit_event(
            "crypto_trigger_pre_arm",
            "stables flowing in but alts not rotating yet",
            str(result["signals"])[:4000],
        )

    return result
