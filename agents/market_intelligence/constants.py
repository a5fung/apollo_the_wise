"""Shared constants and helpers for the Market Intelligence agent."""

# ── Position sizing ──────────────────────────────────────────────────────────
ACCOUNT_SIZE = 100_000       # Total account value ($)
RISK_PCT = 0.01              # 1% account risk per trade
MAX_POSITION_PCT = 0.20      # Max 20% of account in one trade
ENTRY_SLIPPAGE_PCT = 0.001   # 0.1% slippage on breakout entries

# ── Live trading ─────────────────────────────────────────────────────────────
import os
LIVE_TRADING_ENABLED = os.environ.get("LIVE_TRADING_ENABLED", "false").lower() == "true"


def current_account_mode() -> str:
    """Return "paper" or "live" based on ALPACA_PAPER env, read per-call.

    Per-call (not module-level cache) so a future hot env-flip flips the label
    immediately. Used for `mi_live_trades.account_mode`, the `account_mode_active`
    boot audit event, the `/status` and `/config` mode lines, and (via the
    `mode_prefix` helper) every Telegram surface.
    """
    return "paper" if os.environ.get("ALPACA_PAPER", "true").lower() == "true" else "live"


def mode_prefix() -> str:
    """Account-mode prefix for Telegram message headers (trailing space)."""
    return "💰 LIVE-$ " if current_account_mode() == "live" else "📄 PAPER "

# ── Crypto RS shadow flag ────────────────────────────────────────────────────
# false (default): nightly ingest runs, RS computed, audit-only on trigger fire,
#   /crypto + /altseason commands return shadow-mode message.
# true: full alt-season Telegram alerts + briefing surfaces enabled.
CRYPTO_RS_ENABLED = os.environ.get("CRYPTO_RS_ENABLED", "false").lower() == "true"
MAX_CONCURRENT_LIVE_POSITIONS = 5
CONFIRMATION_TIMEOUT_SEC = 300       # 5 min for user to tap Confirm/Skip
DAILY_LOSS_LIMIT_PCT = 0.02          # 2% daily loss limit
CIRCUIT_BREAKER_CONSEC_LOSSES = 5    # Pause after N consecutive losses (EP win rate ~20s% → P(5 consec) ≈ 33%)
CIRCUIT_BREAKER_COOLDOWN_DAYS = 1    # Block resumes after this window past last loss

REGIME_EMOJI = {
    "Bull": "🟢",
    "Choppy": "🟡",
    "Correcting": "🔴",
    "Crisis": "🚨",
    "Unknown": "⚫",
}

# Sectors excluded from RS leaders unless stock price >= SECTOR_FILTER_MIN_PRICE.
# Small-cap biotech/pharma spike on drug trials — noise, not institutional accumulation.
SECTOR_FILTER_SECTORS = frozenset({
    "Healthcare",           # FMP top-level sector for biotech + pharma
})
# Stocks in filtered sectors with price >= this are kept (large-cap pharma/biotech)
SECTOR_FILTER_MIN_PRICE = 50.0


def is_sector_filtered(sector: str | None, price: float | None) -> bool:
    """Return True if this stock should be excluded (small-cap Healthcare/Biotech)."""
    return (sector or "") in SECTOR_FILTER_SECTORS and (price or 0) < SECTOR_FILTER_MIN_PRICE


def trimmed_mean(values: list[float]) -> float:
    """
    Trimmed mean — drop the bottom 20% of values, then average the rest.
    Resists 1-2 outliers dragging down a strong theme while still reflecting
    broad weakness if many stocks are fading.

    ≤5 stocks: drop lowest 1. 6-10: drop lowest 2. 11+: drop bottom 20%.
    Minimum 3 values required for trimming; below that, plain mean.
    """
    if not values:
        return 0.0
    if len(values) < 3:
        return sum(values) / len(values)

    sorted_vals = sorted(values)
    n = len(sorted_vals)
    if n <= 5:
        drop = 1
    elif n <= 10:
        drop = 2
    else:
        drop = max(1, int(n * 0.2))

    trimmed = sorted_vals[drop:]
    return sum(trimmed) / len(trimmed)

# Leveraged/inverse ETFs, broad index ETFs, sector ETFs — excluded from RS leaders and EP scans
SKIP_TICKERS = frozenset({
    # Leveraged / inverse
    "TQQQ", "SQQQ", "SPXL", "SPXS", "UPRO", "SDS", "SSO", "QLD", "QID",
    "UDOW", "SDOW", "LABU", "LABD", "SOXL", "SOXS", "TNA", "TZA",
    "FNGU", "FNGD", "TECL", "TECS", "FAS", "FAZ", "NUGT", "DUST",
    "JNUG", "JDST", "GDXD", "ERX", "ERY", "GUSH", "DRIP", "UVXY",
    "SVXY", "VXX", "UVIX", "SVIX", "BOIL", "KOLD", "UCO", "SCO",
    "AGQ", "ZSL", "GLL", "DULL", "UGL", "YANG", "YINN", "CWEB",
    "BRZU", "BZQ", "EDC", "EDZ", "DRN", "DRV", "RETL", "BNKU",
    "MSTZ", "MSTU", "CONL", "TSLL", "NVDL", "NVDS",  # Single-stock leveraged
    "MUU", "MULL", "SNXX", "QBTZ", "WDCX",  # MicroSectors / leveraged ETNs
    # Broad index ETFs
    "SPY", "QQQ", "IWM", "DIA", "VOO", "VTI", "IVV", "RSP",
    # Sector ETFs (not individual stock EPs)
    "XLK", "XLE", "XLF", "XLV", "XLI", "XLB", "XLP", "XLU", "XLY",
    "XLRE", "XLC", "SMH", "IBB", "XBI", "GDX", "GDXJ", "KRE",
    # Commodity ETFs — track commodities, not stocks
    "USO", "BNO", "DBO", "UNG", "GLD", "SLV", "IAU", "PPLT", "PALL",
    "WEAT", "CORN", "SOYB", "CPER", "DBA", "DBC", "GSG", "PDBC",
    "NRGU", "NRGD",  # Leveraged energy ETNs
    # 2x leveraged thematic ETFs
    "CRCA",  # Direxion 2x daily
    "OKLS",  # 2x leveraged
})
# Pre-computed list for PostgreSQL ANY/ALL queries (avoids frozenset→list on every call)
SKIP_TICKERS_LIST = list(SKIP_TICKERS)
