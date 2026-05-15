"""Shared constants and helpers for the Market Intelligence agent."""

# ── Position sizing ──────────────────────────────────────────────────────────
ACCOUNT_SIZE = 100_000       # Total account value ($)
RISK_PCT = 0.01              # 1% account risk per trade
MAX_POSITION_PCT = 0.20      # Max 20% of account in one trade
ENTRY_SLIPPAGE_PCT = 0.001   # 0.1% slippage on breakout entries


def vix_scaled_risk_pct(vix_value: float | None, base_pct: float = RISK_PCT) -> float:
    """P19 — Continuous VIX-scaled risk sizing.

    Formula: risk = base × max(0.25, 1 - (VIX - 15) / 20).
      VIX ≤ 15  → 1.0× base (low-vol environment, full risk)
      VIX  20   → 0.75× base
      VIX  25   → 0.50× base
      VIX  30   → 0.25× base (vol floor — never go below 25% of base)
      VIX > 30  → still 0.25× base (clamp)

    Returns base_pct unchanged when vix_value is None (no VIX ingest yet,
    or fetch failed). This is the conservative fallback — equivalent to
    the existing binary RISK_PCT * 0.5 halving when regime is bearish.

    Use cases when VIX is wired up:
    - entry_pipeline._size_position can call this with the latest VIX
      reading instead of the binary halve-on-bearish-regime logic
    - alpha override: VIX > 25 dampens position size even within
      permissive regimes; VIX < 12 doesn't increase above base (no
      complacency reward)

    Per project_market_intelligence_backlog.md P19 "Binary captures ~80%
    of the benefit today; revisit after 3+ months live." This helper
    ships ready-to-use; integration deferred to live cutover.
    """
    if vix_value is None or vix_value <= 0:
        return base_pct
    scaled_multiplier = max(0.25, 1.0 - (vix_value - 15.0) / 20.0)
    scaled_multiplier = min(1.0, scaled_multiplier)
    return base_pct * scaled_multiplier

# ── Live trading ─────────────────────────────────────────────────────────────
import os
LIVE_TRADING_ENABLED = os.environ.get("LIVE_TRADING_ENABLED", "false").lower() == "true"

# ── Dual-account architecture (#66, 2026-05-10) ───────────────────────────────
# ENABLE_LIVE_MODE=true (production default): both ALPACA_PAPER_API_KEY/SECRET
# AND ALPACA_LIVE_API_KEY/SECRET required; per-mode TradingClient singletons.
# ENABLE_LIVE_MODE=false (dev/test): only ALPACA_PAPER_* required; strategies
# at phase='live' blocked at boot. Removes "two key pairs to clone and run"
# friction for new contributors. Boot fallback in agent.py maps the legacy
# ALPACA_API_KEY/ALPACA_SECRET_KEY to the paper account if ALPACA_PAPER_* not
# set — keeps git-revert rollback clean for ONE deploy cycle.
ENABLE_LIVE_MODE = os.environ.get("ENABLE_LIVE_MODE", "true").lower() == "true"


def resolve_account_mode_for_strategy(strategy) -> str:
    """Resolve the Alpaca account mode for a given strategy row.

    Single source of truth for routing strategy submissions to paper vs live
    Alpaca clients. Reads `strategy.phase` (and indirectly `live_real_enabled`
    via the caller's gating).

    Mapping:
      phase='shadow'                          → no submit (caller short-circuits)
      phase='paper'                           → 'paper' (Alpaca paper account)
      phase='live' + live_real_enabled=True   → 'live'  (Alpaca live account)
      phase='live' + live_real_enabled=False  → 'live'  (staged-paper Telegram only)

    Note: 'live' return covers both real-$ submit AND staged-paper Telegram
    proposals — the live_real_enabled gate happens downstream of mode resolution.
    """
    phase = getattr(strategy, "phase", None) or (strategy.get("phase") if isinstance(strategy, dict) else None)
    if phase == "paper":
        return "paper"
    if phase == "live":
        return "live"
    raise ValueError(f"Cannot resolve account_mode for strategy phase={phase!r}")


def current_account_mode() -> str:
    """LEGACY: return "paper" or "live" based on ALPACA_PAPER env, read per-call.

    Pre-dual-account global mode resolver. Still used for non-trade contexts
    (`/status` default view, `account_mode_active` boot audit event) where a
    single mode label is meaningful. For trade-bound calls, use
    `resolve_account_mode_for_strategy(strategy)` and propagate `account_mode`
    explicitly through alpaca client calls.
    """
    return "paper" if os.environ.get("ALPACA_PAPER", "true").lower() == "true" else "live"


def mode_prefix(account_mode: str | None = None) -> str:
    """Account-mode prefix for Telegram message headers (trailing space).

    Pass `account_mode` explicitly for trade-bound surfaces (so paper-tier
    and live-tier strategies render with the correct prefix in dual-mode).
    Defaults to current_account_mode() for backward compat with non-trade
    surfaces.
    """
    mode = account_mode or current_account_mode()
    return "💰 LIVE-$ " if mode == "live" else "📄 PAPER "

# ── Crypto RS shadow flag ────────────────────────────────────────────────────
# false (default): nightly ingest runs, RS computed, audit-only on trigger fire,
#   /crypto + /altseason commands return shadow-mode message.
# true: full alt-season Telegram alerts + briefing surfaces enabled.
CRYPTO_RS_ENABLED = os.environ.get("CRYPTO_RS_ENABLED", "false").lower() == "true"
MAX_CONCURRENT_LIVE_POSITIONS = 5
CONFIRMATION_TIMEOUT_SEC = 300       # 5 min for user to tap Confirm/Skip
DAILY_LOSS_LIMIT_PCT = 0.02          # 2% daily loss limit
CIRCUIT_BREAKER_CONSEC_LOSSES = 10   # Pause after N consecutive losses (EP win rate ~25% → P(10 consec) ≈ 5.6%, vs P(5) = 24%).
                                     # Bumped 5→10 on 2026-05-08: at 5 the breaker tripped on 6-loss streak (BSX 4/23 → AMD 5/07)
                                     # — a normal occurrence in a fast-stop strategy. Two known structural issues remain:
                                     # (1) self-perpetuating — each new loss closing during cooldown advances latest_loss_at + 24h;
                                     # (2) methodology-blind — closed-trade streak over-weights losers because Pradeep methodology
                                     # holds winners until trailing stop catches them. Both resolved by drawdown-based replacement
                                     # (task #39). This threshold-bump is the interim stand-in.
CIRCUIT_BREAKER_COOLDOWN_DAYS = 1    # Block resumes after this window past last loss

# ── Drawdown-based circuit breaker (#39) ──────────────────────────────────────
# Replaces count-based breaker on flip day. Methodology-aware: trips on equity
# drawdown from recent peak (Alpaca account.equity includes unrealized — open
# winners' MTM lifts equity, prevents false trips). State-machine evaluated
# once daily at 16:10 ET, persisted in mi_safeguard_state. _check_safeguards()
# reads cached state via cheap PK lookup. SSoT: docs/setups/safeguards.md.
DRAWDOWN_PEAK_WINDOW_DAYS  = 30      # Rolling N-day peak window
DRAWDOWN_TRIP_PCT          = -0.05   # Trip when drawdown ≤ -5% (from peak)
DRAWDOWN_RELEASE_PCT       = -0.025  # Release at ≥ -2.5% (asymmetric → no flap)
MIN_SNAPSHOT_HISTORY_DAYS  = 7       # Active-phase fail-safe; don't trip on sparse history.
                                     # Shadow always evaluates and emits regardless (calibration).
DRAWDOWN_BREAKER_PHASE = os.environ.get("DRAWDOWN_BREAKER_PHASE", "shadow").lower()
                                     # 'shadow' | 'active' — env-driven flip.
                                     # Shadow: daily cron emits transition events; _check_safeguards no-op.
                                     # Active: _check_safeguards reads state, blocks on TRIPPED.

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
