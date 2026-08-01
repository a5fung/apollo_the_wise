"""Shared constants and helpers for the Market Intelligence agent."""

import os

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
    or fetch failed). **This is a FAIL-OPEN, not "conservative"** — it sizes
    at FULL base risk on unknown volatility (the comment here mislabeled the
    direction for over a year; corrected #456 2026-07-26, no functional
    change — every pre-2026-03 day and any future VIX-ingest regression rode
    this at full risk). Superseded by `regime_risk_multiplier()` below when
    `REGIME_SIZING_ENABLED=true`; kept byte-identical here so the flag-OFF
    path reproduces today's exact behavior.

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


# ── Regime-keyed risk multiplier (#456, operator-ruled 2026-07-26) ───────────
# Replaces vix_scaled_risk_pct() + the separate qqq_ema_bullish binary halve as
# the SINGLE sizing axis for real-money entries. Operator: "vix shouldn't be
# the thing that controls sizing, we have a full regime" — VIX still affects
# sizing, but only once, as one input INTO the regime classifier (regime.py),
# not as a second independent scale. Full analysis + evidence:
# docs/analysis/456_regime_sizing_proposal_2026-07-26.md. SSoT change-log +
# sizing-composition doc: docs/setups/safeguards.md.
#
# FEATURE-FLAGGED. Default OFF reproduces today's exact behavior byte-for-byte
# (vix_scaled_risk_pct + the qqq_ema_bullish halve, both left in place above/
# at each call site). Flip to on via env var (no code change) once the
# operator signs off on the live flip — see safeguards.md "Flip steps".
REGIME_SIZING_ENABLED = os.environ.get("REGIME_SIZING_ENABLED", "false").lower() == "true"

# Bull/Choppy/Correcting evidenced directionally (N≥10 for Bull=29, pooled
# non-Bull=14); Correcting (n=5) and Crisis (n=0) are STRUCTURAL PRIORS, not
# measurements — flagged as such in the safeguards.md change-log (CHANGE_PROCESS
# rule 2). Quarterly review 2026-08-01 re-evaluates as the live cohort accrues.
REGIME_RISK_MULTIPLIER: dict[str, float] = {
    "Bull": 1.00,
    "Choppy": 0.75,
    "Correcting": 0.50,
    "Crisis": 0.25,
}
# Unknown / stale / missing / unrecognized-label floor (operator ruling 5:
# "it should fail loud so we can fix" — the floor pairs with a Telegram+audit
# fail-loud alert at the call site, NOT inside this pure lookup; see
# broker/order_manager.py's resolver).
REGIME_SIZING_FALLBACK_MULTIPLIER = 0.25


def regime_risk_multiplier(regime_label: str | None) -> float:
    """PURE lookup: regime label -> risk multiplier (#456). No I/O, no async —
    deliberately importable from execution-boundary-pure shadow code
    (flag_detector.py's HTF breakout shadow) as well as the real broker sizing
    sites. An unrecognized label (including None) falls back to the maximal-
    caution floor — future-proof against label renames; unknown vocabulary
    must never silently full-size.

    Callers that need the FAIL-LOUD side effect (staleness detection, Telegram
    + audit dedup) do NOT call this directly — see
    broker.order_manager._resolve_regime_risk_pct, the single async resolver
    both real sizing sites (MAGNA53 ORB + 9M Day2) call so the fold can never
    drift between them.
    """
    if regime_label is None:
        return REGIME_SIZING_FALLBACK_MULTIPLIER
    return REGIME_RISK_MULTIPLIER.get(regime_label, REGIME_SIZING_FALLBACK_MULTIPLIER)

# ── Live trading ─────────────────────────────────────────────────────────────
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


def active_account_modes() -> list[str]:
    """The account modes this deployment actually operates — the SSoT for
    every "for mode in ..." iteration (sync, reconcile, equity snapshot,
    coverage drift, stream lifecycle). Was 6 hand-copied literals that
    drifted within a single file before this helper (2026-07-05 /simplify)."""
    return ["paper", "live"] if ENABLE_LIVE_MODE else ["paper"]


# ── Strategy phase vocabulary (SSoT — 2026-07-06 /simplify altitude) ──────────
# The #424 'deprecated' rollout hardcoded these literals in 5+ places (entry
# gate, preflight, promotion, the DB CHECK twice, telegram display) and MISSED
# two — the CHECK constraint (boot-crash) and the preflight (deploy-gate crash).
# One source of truth so a new phase is a single edit, not a grep-every-`==`-site:
#   VALID_STRATEGY_PHASES — the full allowed set (the DB CHECK derives from this).
#   NO_SUBMIT_PHASES      — phases that NEVER fire a real order (gate + preflight
#                           consult this; a strategy in one of these never submits).
VALID_STRATEGY_PHASES = frozenset({"shadow", "paper", "live", "deprecated"})
NO_SUBMIT_PHASES = frozenset({"shadow", "deprecated"})

# ── Grade tier lattice (SSoT — ADR 0024 §3) ──────────────────────────────────
# The ordinal EP/judge tier ladder: none < MODERATE < HIGH. Credits move a base
# tier along it (meta_rubric_compose.compose_final_tier); briefing reuses the rank.
TIER_LATTICE = ("none", "MODERATE", "HIGH")
TIER_RANK = {t: i for i, t in enumerate(TIER_LATTICE)}

# ── Service-split roles (#256 W2, 2026-06-13) ────────────────────────────────
# Apollo is splitting into apollo-execution (broker / streams / safeguards /
# Alpaca creds) and apollo-intelligence (detection / themes / judge / briefings)
# so an intelligence deploy can never restart trade execution. Until the cutover,
# the single process runs SERVICE_ROLE="combined" — both job sets + both stream
# consumers — BYTE-IDENTICAL to pre-split behavior.
#   combined     — one process owns everything (DEFAULT; pre-split behavior)
#   execution    — broker, streams, safeguards, execution scheduler jobs only
#   intelligence — detection / themes / judge / briefings; NO streams, NO broker
#                  jobs; reaches execution via the execution_client HTTP transport
SERVICE_ROLE = os.environ.get("SERVICE_ROLE", "combined").lower()
_VALID_SERVICE_ROLES = {"combined", "execution", "intelligence"}

# EXECUTION_MODE selects how execution_client reaches the broker:
#   inprocess — direct in-process broker calls (DEFAULT; pre-split behavior)
#   http      — POST to the apollo-execution service (X-Apollo-Secret), the
#               same auth pattern as orchestrator→market
EXECUTION_MODE = os.environ.get("EXECUTION_MODE", "inprocess").lower()
_VALID_EXECUTION_MODES = {"inprocess", "http"}

# Base URL of the apollo-execution service, used by execution_client's HTTP
# transport when EXECUTION_MODE=http (e.g. "http://apollo-execution:8007").
# Empty in combined/inprocess (the transport is never taken). Required at boot
# when EXECUTION_MODE=http — see assert_service_role_coherent().
EXECUTION_SERVICE_URL = os.environ.get("EXECUTION_SERVICE_URL", "").rstrip("/")


def runs_execution_jobs() -> bool:
    """True when THIS process owns broker / streams / execution scheduler jobs."""
    return SERVICE_ROLE in ("combined", "execution")


def runs_intelligence_jobs() -> bool:
    """True when THIS process owns detection / theme / judge / briefing jobs."""
    return SERVICE_ROLE in ("combined", "intelligence")


def assert_service_role_coherent() -> None:
    """Fail LOUD at boot on an incoherent role/mode combo (#256 W2, advisor 6/13).

    A container that misreads SERVICE_ROLE must NEVER silently fall back to
    'combined' — that would run BOTH job sets AND both trade-stream consumers =
    double order execution / double fill processing (the #1 cutover hazard).
    Invalid values, and the http-without-split combo, raise RuntimeError and
    block the container start (surfaces in docker logs immediately).
    """
    if SERVICE_ROLE not in _VALID_SERVICE_ROLES:
        raise RuntimeError(
            f"SERVICE_ROLE={SERVICE_ROLE!r} invalid — must be one of "
            f"{sorted(_VALID_SERVICE_ROLES)}. Refusing to boot (a misread role "
            f"must never default to 'combined' = double execution)."
        )
    if EXECUTION_MODE not in _VALID_EXECUTION_MODES:
        raise RuntimeError(
            f"EXECUTION_MODE={EXECUTION_MODE!r} invalid — must be one of "
            f"{sorted(_VALID_EXECUTION_MODES)}. Refusing to boot."
        )
    # http transport only makes sense once the process is SPLIT: the
    # intelligence side speaks http to a SEPARATE execution service. A
    # 'combined' process with EXECUTION_MODE=http would HTTP-call itself.
    if EXECUTION_MODE == "http" and SERVICE_ROLE == "combined":
        raise RuntimeError(
            "EXECUTION_MODE=http requires SERVICE_ROLE in {execution, "
            "intelligence} (the split topology); got SERVICE_ROLE='combined' "
            "(a single process would HTTP-call itself). Refusing to boot."
        )
    # http transport with no target URL = every cross-boundary call fails at
    # first use (mid-trading), not at boot. Catch it at boot instead (advisor
    # 6/13, #256 commit 5a). The execution role serves routes locally and never
    # dials out, so the URL is only required for the intelligence client.
    if (EXECUTION_MODE == "http" and SERVICE_ROLE == "intelligence"
            and not EXECUTION_SERVICE_URL):
        raise RuntimeError(
            "EXECUTION_MODE=http + SERVICE_ROLE=intelligence requires "
            "EXECUTION_SERVICE_URL (the apollo-execution base URL). It is unset "
            "— every cross-boundary call would fail at first use. Refusing to boot."
        )


def resolve_account_mode_for_strategy(strategy) -> str:
    """Resolve the Alpaca account mode for a given strategy row.

    Single source of truth for routing strategy submissions to paper vs live
    Alpaca clients. Reads `strategy.phase` (and indirectly `live_real_enabled`
    via the caller's gating).

    Mapping:
      phase='shadow'                          → no submit (caller short-circuits)
      phase='deprecated'                      → no submit (caller short-circuits,
                                                 same as shadow — #424, terminal)
      phase='paper'                           → 'paper' (Alpaca paper account)
      phase='live' + live_real_enabled=True   → 'live'  (Alpaca live account)
      phase='live' + live_real_enabled=False  → 'live'  (staged-paper Telegram only)

    Note: 'live' return covers both real-$ submit AND staged-paper Telegram
    proposals — the live_real_enabled gate happens downstream of mode resolution.
    Raises for 'shadow'/'deprecated'/anything else — callers MUST short-circuit
    on the phase gate (see broker/entry_pipeline.py::_phase_gate_skip_reason)
    before reaching this resolver. Fail-closed by design: an unhandled phase
    should crash loudly here, never silently default to a submit-capable mode.
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


def get_strategy_account_mode(strategy) -> str:
    """Resolve a strategy's Alpaca account_mode for a SIGNAL-bound surface (alert/skip label).

    Phase-guarded so it never raises: a paper/live strategy resolves via
    `resolve_account_mode_for_strategy`; anything else (None, shadow, deprecated) falls back
    to the global `current_account_mode()` for a sensible display label. Single source of truth
    for the "attribute this signal to its owning account" pattern threaded through the EP-scan
    skip + entry-pipeline skip (7/8); the broader #444 mode-label sweep reuses this."""
    if strategy and getattr(strategy, "phase", None) in ("paper", "live"):
        return resolve_account_mode_for_strategy(strategy)
    return current_account_mode()


async def resolve_strategy_mode_nonfatal(strategy_id: str) -> "str | None":
    """Fail-open label-mode resolve for alert surfaces (#444; deduped from two
    hand-rolled copies, review 7/17). NEVER raises — a registry hiccup is a
    label miss, not a reason to abort a live path (the ORB-subscribe contract).
    LOUD without aborting: failure emits `strategy_mode_resolve_error` (the
    `_error` suffix lands it in the morning-brief error banner), replacing the
    silent container-log-only downgrade the review flagged — a live-money alert
    mislabeled as paper should not fail invisibly. Callers memoize per tick."""
    import logging
    try:
        from agents.market_intelligence.strategies.registry import get_strategy
        strategy = await get_strategy(strategy_id)
        return get_strategy_account_mode(strategy)
    except Exception as e:
        logging.getLogger(__name__).warning(
            f"{strategy_id}: label-mode resolve failed (fail-open to legacy prefix): {e}")
        try:
            from agents.market_intelligence.db import log_audit_event
            await log_audit_event(
                "strategy_mode_resolve_error",
                summary=(f"{strategy_id}: account-mode label resolve failed — "
                         f"alerts fall back to the legacy global prefix"),
                detail=str(e)[:400],
            )
        except Exception:  # loud-ok: the audit write itself must not break the alert path
            pass
        return None


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
DAILY_LOSS_LIMIT_PCT = 0.02          # 2% daily loss limit
# ── Intraday profit trigger (#508, operator-signed 2026-08-01) ───────────────
# Take a partial when the position first trades at entry + N x risk_per_share,
# then move the stop to breakeven. REPLACES the day-3/day-5 time gate, which fired
# once in 12 live trades because live holds average 1.50 days (docs/setups/
# exit_discipline.md).
#
# None/0 = OFF, and OFF is the shipped default until the operator flips it: the
# reversion path for this change is this constant, not a code revert.
# Evidence: docs/analysis/508_change_proposal_profit_trigger_2026-08-01.md
# (+0.43R/trade vs actual on the live cohort under the REAL 5-min-poll fill model).
PROFIT_TRIGGER_R: float | None = 2.0   # LIVE 2026-08-01 (operator-signed). Set to None to revert.

CIRCUIT_BREAKER_CONSEC_LOSSES = 10   # Pause after N consecutive losses (EP win rate ~25% → P(10 consec) ≈ 5.6%, vs P(5) = 24%).
                                     # Bumped 5→10 on 2026-05-08: at 5 the breaker tripped on 6-loss streak (BSX 4/23 → AMD 5/07)
                                     # — a normal occurrence in a fast-stop strategy. Two known structural issues remain:
                                     # (1) self-perpetuating — each new loss closing during cooldown advances latest_loss_at + 24h;
                                     # (2) methodology-blind — closed-trade streak over-weights losers because Pradeep methodology
                                     # holds winners until trailing stop catches them. Both resolved by drawdown-based replacement
                                     # (task #39). This threshold-bump is the interim stand-in.
CIRCUIT_BREAKER_COOLDOWN_DAYS = 1    # Block resumes after this window past last loss

# ── Drawdown-based circuit breaker (#39, tiered 2026-05-18) ──────────────────
# Replaces count-based breaker on flip day. Methodology-aware: trips on equity
# drawdown from recent peak (Alpaca account.equity includes unrealized — open
# winners' MTM lifts equity, prevents false trips). State-machine evaluated
# once daily at 16:10 ET, persisted in mi_safeguard_state. _check_safeguards()
# reads cached state via cheap PK lookup. SSoT: docs/setups/safeguards.md.
#
# TIERED REDESIGN 2026-05-18: 25% WR strategy sees P(7 losses) = 13.3% — a
# -7% drawdown is statistically NORMAL variance, not strategy failure. Hard
# block during normal variance prevents finding the winners that pay for the
# losses. Methodology-correct: ADJUST SIZING with drawdown, don't stop.
#
# Tier transitions (asymmetric hysteresis at each boundary):
#   OK → WATCH at -4%; WATCH → OK at -2.5%      (informational only)
#   WATCH → REDUCE at -7%; REDUCE → WATCH at -4% (half-sized entries)
#   REDUCE → BLOCK at -12%; BLOCK → REDUCE at -7% (catastrophic; block entries)
# Trip-side: jump to deepest applicable tier in one snapshot.
# Release-side: step up at most one tier per evaluation.
DRAWDOWN_PEAK_WINDOW_DAYS = 30

# Tier trip thresholds (drawdown_pct must be ≤ to trip into deeper tier)
DRAWDOWN_WATCH_TRIP_PCT    = -0.04
DRAWDOWN_REDUCE_TRIP_PCT   = -0.07
DRAWDOWN_BLOCK_TRIP_PCT    = -0.12

# Tier release thresholds (drawdown_pct must be ≥ to step up to lighter tier)
DRAWDOWN_WATCH_RELEASE_PCT  = -0.025  # WATCH → OK
DRAWDOWN_REDUCE_RELEASE_PCT = -0.04   # REDUCE → WATCH
DRAWDOWN_BLOCK_RELEASE_PCT  = -0.07   # BLOCK → REDUCE

# Sizing multiplier per state — applied to entry_shares + risk_dollars in
# entry_pipeline AFTER spec_builder. Composes multiplicatively with the
# per-strategy `mi_strategies.position_size_multiplier` (#65) — e.g. 9M Day 2
# at 0.5× × REDUCE 0.5× = 0.25× during bleed weeks. Conservative-by-design.
DRAWDOWN_TIER_MULTIPLIER = {
    "OK":     1.0,
    "WATCH":  1.0,   # informational only — no sizing change
    "REDUCE": 0.5,   # halve new entries
    "BLOCK":  0.0,   # no entries (hard block via skip_reason)
}

MIN_SNAPSHOT_HISTORY_DAYS  = 7       # Active-phase fail-safe; don't trip on sparse history.
                                     # Shadow always evaluates and emits regardless (calibration).
DRAWDOWN_BREAKER_PHASE = os.environ.get("DRAWDOWN_BREAKER_PHASE", "shadow").lower()
                                     # 'shadow' | 'active' — env-driven flip.
                                     # Shadow: daily cron emits transition events; _check_safeguards no-op.
                                     # Active: _check_safeguards reads state, gates entries per tier.

# DEPRECATED — legacy binary thresholds (pre-2026-05-18). Kept for one cycle
# in case any imports remain. Will remove after tiered design ships clean.
DRAWDOWN_TRIP_PCT          = DRAWDOWN_WATCH_TRIP_PCT     # legacy alias
DRAWDOWN_RELEASE_PCT       = DRAWDOWN_WATCH_RELEASE_PCT  # legacy alias

# ── Earnings revenue-growth gate (2026-05-19, AGYS hotfix) ────────────────────
# LLM catalyst classifier returns 'strong' on narrative ("24% beat, record Q4")
# without decomposing into revenue substance. Pradeep + Phase 5 rubric: revenue
# growth IS the substance of earnings catalysts. AGYS 2026-05-19 fired HIGH
# on ~1% revenue growth → exactly the non-EP-in-EP-clothing class. Gate
# downgrades earnings 'strong'/'game_changer' to 'routine' when
# sales_yoy_latest < threshold (fail-closed if missing). Score-50 floor
# filters naturally post-downgrade. 5% threshold is conservative
# ("company actually growing"); refine via Phase 5 calibration.
EARNINGS_REVENUE_GATE_ENABLED = os.environ.get(
    "EARNINGS_REVENUE_GATE_ENABLED", "true"
).lower() == "true"
EARNINGS_REVENUE_GATE_MIN_YOY = float(os.environ.get(
    "EARNINGS_REVENUE_GATE_MIN_YOY", "5.0"
))  # PERCENT (matches mi_fundamental_flags.sales_yoy_latest storage convention,
    # e.g. 15.6 = 15.6%, NOT 0.156). Default 5.0 = 5% YoY revenue growth.

# ── 6-axis catalyst rubric runtime gate (2026-05-19, Phase 5 ship) ────────────
# When earnings-day catalyst extracted to mi_ep_catalyst_metrics, the rubric
# runs on the fresh structured data and produces composite_scaled (0-39).
# composite < CATALYST_RUBRIC_MIN_COMPOSITE → downgrade to routine.
# Falls through to the Q-rev threshold safety net if rubric can't score
# (no q_revenue_yoy_pct extracted).
#
# Label bands (from catalyst_rubric.LABEL_BANDS):
#   30+: game_changer
#   22-29: strong            <-- default threshold 22 = strong-or-better
#   14-21: routine
#   0-13: weak
CATALYST_RUBRIC_GATE_ENABLED = os.environ.get(
    "CATALYST_RUBRIC_GATE_ENABLED", "true"
).lower() == "true"
CATALYST_RUBRIC_MIN_COMPOSITE = float(os.environ.get(
    "CATALYST_RUBRIC_MIN_COMPOSITE", "22"
))  # Default 22 = strong floor. Below 22 (routine/weak) → downgrade.

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
