"""User-curated 27-coin watchlist seeded on first migration.

Each entry uses a `coin_id_hint` (best-guess CoinGecko ID) rather than hard-coded
contract addresses to avoid impostor-token bugs from wrong addresses. On first
ingest, the resolver hits CoinGecko `/coins/{id}` once per coin to:
- Validate the CG id resolves
- Fetch chain + contract_address from the API's `platforms` map
- Persist the verified pair into crypto_token_address

Coins where the CG id is uncertain (e.g., DEX-only Ethereum tokens like KnoxNet)
are flagged with coin_id_hint=None — the resolver falls back to DexScreener
search by symbol within trusted chains.
"""

from typing import Optional


class WatchlistEntry:
    __slots__ = ("symbol", "coin_id_hint", "notes")

    def __init__(self, symbol: str, coin_id_hint: Optional[str], notes: str = ""):
        self.symbol = symbol
        self.coin_id_hint = coin_id_hint
        self.notes = notes


WATCHLIST_SEED: list[WatchlistEntry] = [
    # Mega / Large
    WatchlistEntry("BNB", "binancecoin"),
    WatchlistEntry("SOL", "solana"),
    WatchlistEntry("ADA", "cardano"),
    WatchlistEntry("DOT", "polkadot"),
    WatchlistEntry("LINK", "chainlink"),
    WatchlistEntry("HYPE", "hyperliquid"),
    # Mid
    WatchlistEntry("ATOM", "cosmos"),
    WatchlistEntry("SUI", "sui"),
    WatchlistEntry("TAO", "bittensor"),
    WatchlistEntry("RENDER", "render-token"),
    WatchlistEntry("FET", "artificial-superintelligence-alliance",
                   "Formerly Fetch.ai; merged with AGIX + OCEAN"),
    WatchlistEntry("ENA", "ethena"),
    WatchlistEntry("AERO", "aerodrome-finance"),
    WatchlistEntry("VIRTUAL", "virtual-protocol", "AI agent infra (Base L2)"),
    WatchlistEntry("PEPE", "pepe"),
    WatchlistEntry("BONK", "bonk"),
    WatchlistEntry("AKT", "akash-network"),
    WatchlistEntry("ASTER", None,
                   "Spot ASTER (user's source showed perp .P); "
                   "resolve via CoinGecko search on first ingest"),
    # Micro
    WatchlistEntry("SYRUP", "maple", "Maple Finance"),
    WatchlistEntry("CAKE", "pancakeswap-token"),
    WatchlistEntry("PUMP", "pump-fun", "Solana memecoin launchpad"),
    WatchlistEntry("MOG", "mog-coin"),
    WatchlistEntry("FARTCOIN", "fartcoin"),
    # Below floor — watchlist override
    WatchlistEntry("VVV", "venice-token"),
    WatchlistEntry("KTA", "keeta", "New L1; CG resolution may fail on first run"),
    WatchlistEntry("COPPERINU", None,
                   "Likely DEX-only meme; DexScreener fallback required"),
    WatchlistEntry("KNX", None,
                   "KnoxNet WETH pair on Ethereum Uniswap; "
                   "DexScreener-only — no CoinGecko listing expected"),
]
