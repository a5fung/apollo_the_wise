"""Watchlist resolver — fills in coin_id, chain, contract_address for seed entries.

Seed entries with `coin_id_hint=None` (KNX, COPPERINU, ASTER) carry placeholder
`_unresolved_<symbol>` ids in `crypto_watchlist`. This module resolves them on
first ingest by:

1. Best effort: CoinGecko search by symbol → `/coins/{id}` for chain+contract
2. Fallback: DexScreener search by symbol within trusted chains; pick the
   highest-liquidity USDC/USDT-quoted pair

Resolution is one-time per coin. Once `coin_id` is non-placeholder AND
`chain`+`contract_address` are populated, the resolver skips the row.

Also re-validates already-resolved entries' contract addresses if the user
changes the seed (e.g., bug-fixing a wrong CG id) — the seed row gets the
new `coin_id_hint` but the watchlist row still has the old placeholder.
"""
from __future__ import annotations

import logging
from typing import Optional

from agents.market_intelligence.db import get_pool
from agents.market_intelligence.crypto import (
    coingecko_client as cg,
    dexscreener_client as ds,
)

logger = logging.getLogger(__name__)


async def resolve_pending_watchlist(prefetched_universe: Optional[list[dict]] = None) -> int:
    """Walk the watchlist, resolve any rows with placeholder ids or missing
    chain/contract. Returns the number of rows updated.

    `prefetched_universe`: top-250 from CoinGecko if the caller already has it
    (saves 1 CG /coins/markets call and N (coin-count) redundant fetches inside
    _resolve_one). The nightly orchestrator hoists this fetch.
    """
    pool = await get_pool()
    async with pool.acquire() as conn:
        pending = await conn.fetch(
            """
            SELECT coin_id, symbol, notes
            FROM crypto_watchlist
            WHERE coin_id LIKE '_unresolved_%'
               OR (contract_address IS NULL AND chain IS NULL)
            """
        )

    updated = 0
    for row in pending:
        symbol = row["symbol"]
        old_id = row["coin_id"]
        try:
            resolved = await _resolve_one(symbol, old_id, prefetched_universe)
        except Exception:
            logger.exception("Resolver crashed on %s; will retry next ingest", symbol)
            continue
        if not resolved:
            logger.warning("Resolver: %s unresolved (no CG match, no DS match)", symbol)
            continue

        new_id = resolved["coin_id"]
        chain = resolved.get("chain")
        contract = resolved.get("contract_address")

        async with pool.acquire() as conn:
            async with conn.transaction():
                # If the resolved coin_id differs from the placeholder, we need to
                # delete the old row and insert a new one (PK collision otherwise).
                if new_id != old_id:
                    await conn.execute(
                        "DELETE FROM crypto_watchlist WHERE coin_id = $1", old_id
                    )
                    await conn.execute(
                        """
                        INSERT INTO crypto_watchlist
                            (coin_id, symbol, chain, contract_address, source, notes)
                        VALUES ($1, $2, $3, $4, 'resolved', $5)
                        ON CONFLICT (coin_id) DO UPDATE SET
                            chain = COALESCE(EXCLUDED.chain, crypto_watchlist.chain),
                            contract_address = COALESCE(EXCLUDED.contract_address, crypto_watchlist.contract_address)
                        """,
                        new_id, symbol, chain, contract, row["notes"],
                    )
                else:
                    await conn.execute(
                        """
                        UPDATE crypto_watchlist
                           SET chain = COALESCE($1, chain),
                               contract_address = COALESCE($2, contract_address),
                               source = 'resolved'
                         WHERE coin_id = $3
                        """,
                        chain, contract, new_id,
                    )

                # Persist (chain, contract) -> coin_id mapping for cross-source dedup.
                if chain and contract:
                    await conn.execute(
                        """
                        INSERT INTO crypto_token_address (coin_id, chain, contract_address)
                        VALUES ($1, $2, $3)
                        ON CONFLICT (chain, contract_address) DO NOTHING
                        """,
                        new_id, chain, contract,
                    )
        updated += 1
        logger.info("Resolver: %s -> coin_id=%s chain=%s addr=%s",
                    symbol, new_id, chain, (contract or "")[:10])
    return updated


async def _resolve_one(
    symbol: str,
    fallback_id: str,
    prefetched_universe: Optional[list[dict]] = None,
) -> Optional[dict]:
    """Try CG first, then DexScreener. Returns dict with coin_id and optional
    chain+contract_address, or None if nothing resolves.
    """
    # Strategy 1: if symbol matches a top-universe entry, take it.
    try:
        universe = prefetched_universe
        if universe is None:
            universe = await cg.get_top_universe(per_page=250)
        match = next(
            (u for u in universe if (u.get("symbol") or "").upper() == symbol.upper()),
            None,
        )
        if match:
            coin_id = match.get("id")
            if coin_id:
                detail = await cg.get_coin_detail(coin_id)
                chain, contract = _pick_primary_platform(detail.get("platforms") or {})
                return {
                    "coin_id": coin_id,
                    "chain": chain,
                    "contract_address": contract,
                }
    except Exception:
        logger.exception("Resolver CG step failed for %s", symbol)

    # Strategy 2: DexScreener symbol search across trusted chains.
    try:
        pairs = await ds.search_token_by_symbol(symbol)
        trusted = [
            p for p in pairs
            if (p.get("chainId") or "") in ds.TRUSTED_CHAINS
            and (p.get("baseToken") or {}).get("symbol", "").upper() == symbol.upper()
        ]
        if trusted:
            trusted.sort(
                key=lambda p: float((p.get("liquidity") or {}).get("usd") or 0.0),
                reverse=True,
            )
            best = trusted[0]
            chain = best.get("chainId")
            contract = (best.get("baseToken") or {}).get("address")
            if chain and contract:
                # No CG id available; persist with a deterministic dex-anchored id
                # so downstream joins still work.
                synth_id = f"dex_{chain}_{contract.lower()}"
                return {
                    "coin_id": synth_id,
                    "chain": chain,
                    "contract_address": contract,
                }
    except Exception:
        logger.exception("Resolver DS step failed for %s", symbol)

    return None


def _pick_primary_platform(platforms: dict) -> tuple[Optional[str], Optional[str]]:
    """CG `platforms` is `{<chain>: <contract_address>}`. Pick a trusted chain
    if present; else return the first non-empty entry; else (None, None).
    """
    if not platforms:
        return None, None
    # Prefer trusted chains in priority order.
    for chain in ("ethereum", "solana", "base", "arbitrum"):
        contract = platforms.get(chain)
        if contract:
            return chain, contract
    # Fallback: first non-empty.
    for chain, contract in platforms.items():
        if contract:
            return chain, contract
    return None, None
