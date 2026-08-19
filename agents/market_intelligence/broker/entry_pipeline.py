"""
Unified trade-entry pipeline.

Single code path for every ORB bracket entry (MAGNA53 EP and 9M Day 2).
Strategy differences (stop source, position sizing) are injected via the
`spec_builder` callback; everything else — duplicate check, safeguards,
bar-fetch-with-retry, fade guard, DB insert, Alpaca submit, audit log,
Telegram — lives here exactly once.

Contract: every terminal failure state sends a Telegram message. No
silent skips. If a monitored candidate fails to enter, the user finds
out in real time.
"""
from __future__ import annotations

import asyncio
import logging
from datetime import date
from typing import Any, Awaitable, Callable

from agents.market_intelligence.broker import alpaca_client as alpaca
from agents.market_intelligence.broker.skip_reasons import (
    BLOCK_PAPER_STRATEGY_ON_LIVE,
    BLOCK_STRATEGY_DISABLED,
    BLOCK_STRATEGY_IN_SHADOW,
    BLOCK_STRATEGY_DEPRECATED,
    BLOCK_MAX_POSITIONS,
    BLOCK_STRATEGY_POSITION_CAP,
    cap_block_reason,
    strategy_cap_block_reason,
    INFRA_NO_BAR,
    INFRA_ORDER_SUBMIT_FAILED,
    SETUP_FADED_FROM_ORB,
    SETUP_GAP_BELOW_FLOOR,
    WINDOW_DUPLICATE,
    BLOCK_TICKER_OPEN_POSITION,
    humanize,
)
from agents.market_intelligence.briefing import send_telegram_message
from agents.market_intelligence.constants import (
    MAX_CONCURRENT_LIVE_POSITIONS,
    current_account_mode,
    get_strategy_account_mode,
    mode_prefix,
    resolve_account_mode_for_strategy,
)
from agents.market_intelligence.db import get_pool, log_audit_event
import math

logger = logging.getLogger(__name__)

BAR_RETRY_MAX = 3
BAR_RETRY_DELAY_SEC = 10
FADE_MIDPOINT_RATIO = 0.5

# ── #461 per-account_mode position-cap lock (advisory, xact-scoped, DB-global) ─
# Namespace for the STEP-6 atomic cap recheck (design:
# docs/decisions/461_toctou_cap_design_2026-07-18.md, operator-approved).
# DISTINCT from order_manager._TRADE_LOCK_NAMESPACE = 0x504152 ("PAR" —
# session-level, per-trade, guards the partial-vs-reconciler EXIT path); the
# two locks live in different namespaces and are never held together, so no
# collision and no deadlock ordering concern. Two-int form
# pg_advisory_xact_lock(classid, objid): classid = this constant, objid =
# hashtext(account_mode) → per-MODE serialization only — paper never
# serializes against live (#66 isolation). Xact-scoped: auto-releases at
# commit/rollback/error/connection-death — no unlock bookkeeping.
_CAP_LOCK_NAMESPACE = 0x434150  # "CAP" — fits int4; arbitrary fixed namespace

# Bounded action vocabulary for `submit_trade_entry` return dicts.
# Callers pattern-match on these (see live_tracker.process_new_alerts_live
# success/skip counters and submit_9m_day2_trade sugar-baby status mapping).
ACTION_AUTO_ENTERED = "auto_entered"
ACTION_PROPOSED = "proposed"
ACTION_AUTO_ENTER_FAILED = "auto_enter_failed"
ACTION_PROPOSAL_SEND_FAILED = "proposal_send_failed"
ACTION_SKIPPED = "skipped"
ACTION_BLOCKED = "blocked"


# ── Bar fetch ────────────────────────────────────────────────────────────────

async def fetch_orb_bar_with_retry(
    ticker: str,
    today: date,
    strategy_label: str,
) -> dict | None:
    """Fetch first 1-min bar, retrying every BAR_RETRY_DELAY_SEC up to
    BAR_RETRY_MAX attempts.

    PRIMARY source: the 09:30 bar the WebSocket stream already delivered
    (bar_stream.get_cached_first_bar). 2026-08-13: three HIGH alerts
    (HLIT/CRMD/CGEM) skipped infra:no_bar because this function re-fetched
    over REST a bar the stream had already pushed — REST minute aggregation
    can lag bar close by more than the whole retry budget. The cache is
    consulted on EVERY attempt (a stream bar can land during a retry sleep)
    and only ever holds the true 09:30 ET minute, so the ORB definition is
    unchanged.

    FALLBACK: REST get_first_bar, exactly today's behaviour — the REST
    endpoint can take a few seconds after bar close (9:31:00) to return the
    settled bar; single-attempt callers miss any candidate that hits the gap.
    """
    bar: dict | None = None
    for attempt in range(1, BAR_RETRY_MAX + 1):
        stream_bar = _stream_cached_bar(ticker, today)
        if stream_bar:
            logger.info(
                f"{strategy_label} {ticker}: ORB bar from stream cache "
                f"(attempt {attempt}) O={stream_bar['open']:.2f} "
                f"H={stream_bar['high']:.2f} L={stream_bar['low']:.2f}"
            )
            try:
                await log_audit_event(
                    "orb_bar_stream_used",
                    f"{strategy_label} {ticker} attempt {attempt} — "
                    f"O={stream_bar['open']:.2f} H={stream_bar['high']:.2f} "
                    f"L={stream_bar['low']:.2f}",
                )
            except Exception:  # loud-ok: log_audit_event() never raises — self-catches + logs internally (db.py); logger.info already fired immediately above
                pass
            return stream_bar
        bar = await alpaca.get_first_bar(ticker, today)
        if bar:
            return bar
        if attempt < BAR_RETRY_MAX:
            logger.info(
                f"{strategy_label} {ticker}: no bar attempt {attempt}/{BAR_RETRY_MAX}, "
                f"retry in {BAR_RETRY_DELAY_SEC}s"
            )
            try:
                await log_audit_event(
                    "orb_bar_miss",
                    f"{strategy_label} {ticker} attempt {attempt}/{BAR_RETRY_MAX} — "
                    f"bar not available, retry {BAR_RETRY_DELAY_SEC}s",
                )
            except Exception:  # loud-ok: log_audit_event() never raises — self-catches + logs internally (db.py); logger.info already fired immediately above
                pass
            await asyncio.sleep(BAR_RETRY_DELAY_SEC)
    return None


def _stream_cached_bar(ticker: str, today: date) -> dict | None:
    """Error-wrapped lookup of the stream-delivered 09:30 bar. ANY failure
    (import, lookup, bad state) returns None so the REST fallback runs —
    this path may narrow the bar sources to zero under no circumstances."""
    try:
        from agents.market_intelligence.broker import bar_stream
        return bar_stream.get_cached_first_bar(ticker, today)
    except Exception as e:  # loud-ok: fallback path — REST fetch proceeds identically; a cache failure must never block the entry
        logger.warning(f"stream bar-cache lookup failed for {ticker} (non-fatal): {e}")
        return None


# ── Fade guard ───────────────────────────────────────────────────────────────

async def check_fade_guard(
    ticker: str, orb_bar: dict, ratio: float | None = FADE_MIDPOINT_RATIO,
) -> tuple[bool, str | None]:
    """Return (ok, skip_reason). If the latest trade is below
    `orb_low + (orb_high - orb_low) * ratio`, the gap-and-go has lost
    momentum. Silent-on-data-failure: if `get_latest_trade` returns None,
    we let the bracket through — don't block on feed flakiness.

    `ratio=None` skips the check entirely. MAGNA53 EP HIGH passes None
    because Sonnet+Perplexity validation + ATR stop width + 10:00 ET
    cleanup already cover the dead-cat-fill case. 9M Day 2 (no LLM) passes
    a smaller ratio (e.g. 0.25) to keep some fade protection.
    """
    if ratio is None:
        return True, None

    orb_high = orb_bar["high"]
    orb_low = orb_bar["low"]
    orb_midpoint = orb_low + (orb_high - orb_low) * ratio

    latest = await alpaca.get_latest_trade(ticker)
    if not latest or not latest.get("price"):
        return True, None

    last_price = float(latest["price"])
    if last_price >= orb_midpoint:
        return True, None

    fade_pct = (orb_high - last_price) / orb_high * 100 if orb_high > 0 else 0
    reason = (
        f"{SETUP_FADED_FROM_ORB}: last ${last_price:.2f} < threshold "
        f"${orb_midpoint:.2f} (ratio={ratio:.2f}, ORB H=${orb_high:.2f} "
        f"L=${orb_low:.2f}, faded {fade_pct:.1f}%)"
    )
    return False, reason


async def check_rt_gap_floor(
    ticker: str, alert_context: dict, floor_pct: float | None = None,
) -> tuple[bool, str | None]:
    """#490 — re-check the gap against REAL-TIME price at submission. Return (ok, skip_reason).

    **This is a bug fix, not a new filter** (operator ruling 2026-08-01: *"the blocking live path is
    in fact correct given the price retreated from the 10% gap, so in a way the current path is a
    bug"*). `MIN_GAP_PCT = 10.0` is an existing, signed detection criterion. The alert row is written
    on whichever scan tick first scored it HIGH — often hours before the open — and
    `live_tracker.process_new_alerts_live` then selects that ROW at 09:31 without re-reading price.
    So a name that retreated below the floor in between was entered anyway, in violation of the
    system's own criterion. Measured: FTNT 2026-07-30 was logged at 7.77% at 09:30:05, one minute
    before entry, and entered; WKC, QBTS and FTNT all faded below the floor pre-entry and all lost.

    **FAIL OPEN — a bad tick must never kill a good entry.** Identical posture to
    `check_fade_guard`'s silent-on-data-failure rule. We block ONLY on a positive, trustworthy read
    that is below the floor. Every other path returns ok: toggle off, no `prev_close` on the alert,
    no/zero/negative latest trade, or any exception at all.

    Toggle-gated by `ep_rt_entry_gap_recheck` (default OFF) so it ships inert and reverts in ~60s
    with no deploy.
    """
    if floor_pct is None:
        return True, None      # strategy did not opt in — see rt_gap_floor_pct
    try:
        from agents.market_intelligence.db import get_prev_close, get_runtime_toggle
        if not await get_runtime_toggle(
            "ep_rt_entry_gap_recheck", "EP_RT_ENTRY_GAP_RECHECK", default=False):
            return True, None

        # `mi_ep_alerts` carries no prev_close column, so it is fetched from mi_daily_closes —
        # the SAME Polygon denominator the detector uses, so the scan and this guard cannot
        # disagree about one name on one day. (An earlier draft read `alert_context["prev_close"]`,
        # which does not exist: the guard would have silently failed open and done nothing.)
        alert_date = alert_context.get("alert_date")
        if alert_date is None:
            return True, None
        prev_close = await get_prev_close(ticker, alert_date)
        if not prev_close or prev_close <= 0:
            return True, None          # no denominator → cannot judge → let it through

        latest = await alpaca.get_latest_trade(ticker)
        if not latest or not latest.get("price"):
            return True, None          # feed flakiness → let it through (fade-guard rule)
        price = float(latest["price"])
        if price <= 0:
            return True, None

        rt_gap = (price - prev_close) / prev_close * 100
        if rt_gap >= floor_pct:
            return True, None

        alert_gap = alert_context.get("gap_pct")
        alert_txt = f"{float(alert_gap):.1f}%" if alert_gap is not None else "n/a"
        return False, (
            f"{SETUP_GAP_BELOW_FLOOR}: rt {rt_gap:.1f}% < {floor_pct:.0f}% floor "
            f"(alert said {alert_txt}, last ${price:.2f} vs prev close ${prev_close:.2f})"
        )
    except Exception as e:
        # loud-ok: this guard may only ever REMOVE entries. Any failure inside it must land on
        # today's behaviour, never on a block — an exception here must not become a silent halt.
        logger.warning(f"rt gap re-check failed for {ticker} (non-fatal, entry proceeds): {e}")
        return True, None


# ── Main pipeline ────────────────────────────────────────────────────────────

SpecBuilder = Callable[
    [dict, dict, dict | None, str], Awaitable[tuple[dict | None, str | None]]
]
# 4th positional arg is account_mode ('paper' | 'live'), threaded so the
# spec_builder can fetch equity from the correct Alpaca account when sizing.
# Added 2026-05-10 (#66 dual-account).
SkipHook = Callable[[str], Awaitable[None]]


def _should_auto_enter(account_mode: str, live_real_enabled: bool) -> bool:
    """Auto-submit the bracket immediately (True) vs. send a manual-confirm Telegram
    proposal (False).

    - paper                              -> True  (paper always auto-confirms)
    - live + live_real_enabled=True      -> True  (REAL-money auto-entry; operator-signed
                                                   2026-06-20, START-SMALL launch)
    - live + live_real_enabled=False     -> False (staged-paper ramp: proposal only)

    Live auto-entry has NO per-trade human gate, so it leans on the upstream
    `_check_safeguards` (LIVE_TRADING_ENABLED, /pause halt, max-positions, daily-loss,
    drawdown breaker) + `submit_entry`'s #345 /pause re-check + START-SMALL sizing
    (position_size_multiplier) + the position cap. live_real_enabled gates real money;
    safeguards.md HARD-gates it on /pause being verified-live.
    """
    return account_mode == "paper" or (account_mode == "live" and bool(live_real_enabled))


def _apply_composite_multiplier(baseline_shares: int, composite_multiplier: float) -> tuple[int, bool]:
    """Step-5b sizing arithmetic, pure → (shares, clamped).

    RED-3 safeguard clamp (operator-ruled 2026-07-12, rulings-pack R5): a multiplier sizes
    DOWN freely but may NEVER push size past the builder's baseline — the spec's shares are
    by construction cap-MAXIMAL under the 20%-capital + VIX-scaled-risk safeguards (both
    builders size AT risk_pct, clamped to 20% equity), so clamping to baseline re-imposes
    both caps with zero duplicated cap math. Raising the caps is a CHANGE_PROCESS on
    RISK_PCT / the 20% cap — never a multiplier backdoor. Pre-clamp, a >1.0 allocator step
    (ADR 0022) would have sized straight through the safeguards
    (composition_redteam_2026-07-12.md RED-3).
    """
    new_shares = math.floor(baseline_shares * composite_multiplier)
    if new_shares > baseline_shares:
        return baseline_shares, True
    return new_shares, False


def _phase_gate_skip_reason(strategy) -> str | None:
    """Field-only strategy-registry gate: disabled / shadow / deprecated.

    Returns the skip_reasons constant to block on, or None to proceed.
    Deliberately excludes the "paper phase on a live account" check (needs
    `current_account_mode()` at call time) so this stays a pure, easily
    testable predicate over the strategy row alone.

    'deprecated' (#424, ADR 0022 §1 — terminal, operator-signed 2026-07-05/06:
    9m_day2 retired as "9M is a condition not a setup"; flag_continuation
    retired as "replaced by HTF + Anticipation") is treated exactly like
    'shadow' here: no new paper/live entries, ever. Without this, a
    deprecated strategy would fall through to `resolve_account_mode_for_strategy`,
    which raises ValueError for any phase other than 'paper'/'live' — a crash
    instead of a clean skip.
    """
    from agents.market_intelligence.constants import NO_SUBMIT_PHASES
    if not strategy.enabled:
        return BLOCK_STRATEGY_DISABLED
    # NO_SUBMIT_PHASES (constants) is the SSoT for "never fires an order"; the
    # per-phase skip reason below is display only. A new no-submit phase added to
    # the set is blocked here automatically (2026-07-06 /simplify altitude).
    if strategy.phase in NO_SUBMIT_PHASES:
        return BLOCK_STRATEGY_DEPRECATED if strategy.phase == "deprecated" else BLOCK_STRATEGY_IN_SHADOW
    return None


async def submit_trade_entry(
    *,
    alert_context: dict,
    spec_builder: SpecBuilder,
    regime_record: dict | None,
    strategy_label: str,
    signal_type: str,
    today: date,
    atr_14: float | None = None,
    success_title: str = "Order placed",
    stop_label: str = "Stop",
    on_skip: SkipHook | None = None,
    fade_midpoint_ratio: float | None = FADE_MIDPOINT_RATIO,
    # #490 — the real-time gap floor to re-check at submission, per STRATEGY.
    # None = skip (the DEFAULT, deliberately): `submit_trade_entry` is the shared funnel for
    # MAGNA53 *and* 9M Day 2, and MIN_GAP_PCT is MAGNA53's 10% criterion. 9M Day 2's own bar is
    # 3% gap OR 4% intraday gain (`ninem_detector._MIN_GAP_PCT`), so enforcing 10% there would
    # silently rewrite ANOTHER strategy's entry discipline. Same idiom as fade_midpoint_ratio.
    rt_gap_floor_pct: float | None = None,
    aggregate_skips: bool = False,
) -> dict:
    """Single entry-submission pipeline.

    Required `alert_context` keys: ticker, ep_score, catalyst_quality, gap_pct.

    `spec_builder(alert_context, orb_bar, regime_record)` returns
    `(order_spec, skip_reason)`. The spec dict must contain orb_high, orb_low,
    entry_price, stop_loss_price, shares, position_size, risk_dollars.

    Every terminal skip/block/failure state calls `send_telegram_message`.
    No silent drops. The auto-enter SUCCESS path is log+audit only (#475,
    2026-07-15) — the WS FILLED alert is the single per-trade Telegram.
    """
    from agents.market_intelligence.broker.live_tracker import (
        _check_safeguards,
        _insert_skipped_trade,
        count_open_positions,
    )
    from agents.market_intelligence.broker.order_manager import submit_entry
    from agents.market_intelligence.broker.telegram_confirm import send_trade_proposal

    ticker = alert_context["ticker"]
    pool = await get_pool()

    async def _skip(
        reason: str,
        icon: str = "⏭️",
        audit_event: str = "orb_skipped",
        action: str = ACTION_SKIPPED,
    ) -> dict:
        if on_skip:
            try:
                await on_skip(reason)
            except Exception as e:
                logger.warning(f"{strategy_label} {ticker}: on_skip hook raised — {e}")
        # #444: bound BEFORE the try so a resolve failure (or `strategy` not yet
        # assigned in the enclosing scope — _skip can fire ahead of the phase-gate
        # line for the open-position guard) leaves this None rather than unbound.
        # mode_prefix(None) == mode_prefix() — the CAP+1 alert below degrades to
        # today's exact legacy-global behavior instead of silently vanishing into
        # the except below it (a NameError here would have been swallowed).
        _skip_mode = None
        try:
            # Attribute the filtered trade to the OWNING strategy's account so the EOD summary
            # shows a live-strategy skip under LIVE, not paper (operator 7/8). Resolved here
            # (skip path only) to avoid touching the main flow; the helper phase-guards + falls
            # back to the global mode, so no silent except.
            _skip_mode = get_strategy_account_mode(strategy)
            await _insert_skipped_trade(
                ticker, today, alert_context, regime_record, reason,
                signal_type=signal_type, account_mode=_skip_mode,
            )
        except Exception as e:
            # This swallow is WHY the #465 constraint drift ran unnoticed from 2026-08-01 to
            # 2026-08-03: the insert raised on every skip, the ERROR went to the container log,
            # and nothing operator-facing changed until the missing row let a duplicate Telegram
            # through. Keep failing OPEN (a recording failure must never alter entry behaviour)
            # but make it VISIBLE -- an *_error audit row is on the alerting path.
            logger.error(f"{strategy_label} {ticker}: _insert_skipped_trade raised — {e}")
            try:
                # REUSE the event the scheduler's out-of-ORB path already emits
                # (scheduler.py ~1005) rather than minting a second name for the same class --
                # two names for one failure make any aggregation over it quietly wrong.
                await log_audit_event(
                    "skip_row_write_error",
                    f"{ticker} {today} entry-pipeline skip row NOT persisted — "
                    f"{type(e).__name__}: {e}",
                )
            except Exception:  # loud-ok: log_audit_event self-catches; the logger.error above already fired
                pass
        try:
            await log_audit_event(audit_event, f"{strategy_label} {ticker} — {reason}")
        except Exception:  # loud-ok: log_audit_event() never raises — self-catches + logs internally (db.py); a Telegram skip/block alert always follows below (its own try/except is loud)
            pass
        # aggregate_skips=True: caller emits one grouped digest after gather().
        # infra:* always pings immediately (no-silent-failures rule); filter /
        # setup / block reasons stay aggregated.
        is_infra = isinstance(reason, str) and reason.startswith("infra:")
        if not aggregate_skips or is_infra:
            try:
                await send_telegram_message(
                    f"{mode_prefix()}{icon} *{ticker}* {strategy_label} skipped — {humanize(reason)}"  # mode_prefix() ok here — pre-account-routing skip
                )
            except Exception as e:
                logger.error(f"{strategy_label} {ticker}: telegram skip alert failed — {e}")
        # #197: a game_changer blocked by the FLAT global max-positions cap is a
        # CAP+1 CANDIDATE. Surface it IMMEDIATELY + actionably (independent of skip
        # aggregation) so the operator can take it manually — the cap+1 rule is
        # SHADOW-only, Apollo will NOT auto-enter it. Additive Telegram; no
        # decision/trade-state change. Scoped to BLOCK_MAX_POSITIONS only (not the
        # per-strategy slot cap) to stay consistent with the policy ("bend the flat
        # 5-slot cap to a 6th") AND with the durable ledger, whose skip_category
        # 'cap_blocked' maps from block:max_positions alone — alert ↔ ledger parity.
        try:
            _cq = (alert_context.get("catalyst_quality") or "")
            _is_cap = isinstance(reason, str) and reason.startswith(BLOCK_MAX_POSITIONS)
            if _is_cap and _cq == "game_changer":
                await send_telegram_message(
                    f"{mode_prefix(_skip_mode)}🌟🚫 *CAP+1 CANDIDATE — {ticker}*\n"
                    f"game\\_changer · score {alert_context.get('ep_score', '?')} · "
                    f"blocked by full position cap.\n"
                    f"_Would auto-enter under the cap+1 rule (SHADOW — not live). "
                    f"Apollo will NOT take it; consider acting manually._"
                )
        except Exception as e:
            logger.error(f"{strategy_label} {ticker}: cap+1 candidate alert failed — {e}")
        return {"ticker": ticker, "action": action, "reason": reason}

    # #465 (money-path audit R4): the two pre-checks below and the ON CONFLICT
    # target had NO account_mode filter, violating dual-account invariant 3
    # ("account_mode filter on every trade query"). A PAPER row therefore
    # suppressed a LIVE entry on the same ticker/day — fail-safe in direction
    # (skip, never double-order) but a REAL entry silently dropped and mislabeled
    # `window:duplicate`. Overlap is plausible, not theoretical: a 9M day is often
    # an EP day (9M-Day2 paper x magna53 live). Zero collisions in 258 rows so far;
    # fixed before it bites, not after.
    # The strategy row is not fetched until the phase gate (1a) below, so resolve
    # the mode here rather than REORDERING a money-path gate to suit a dedup filter.
    # Fail-safe: if the strategy is unknown (legacy path / pre-seed), fall back to
    # the process-wide mode — which reproduces exactly the pre-#465 behaviour for
    # that case rather than inventing a new one.
    # #444 pins that a resolver failure must NOT break the entry path — its test
    # ("resolver boom") caught this line unguarded, which would have turned a
    # registry hiccup into a dropped entry. Degrade to the process-wide mode, which
    # is exactly the pre-#465 behaviour, rather than propagating.
    try:
        from agents.market_intelligence.strategies.registry import get_strategy as _get_strategy
        _dedup_strategy = await _get_strategy(signal_type)
        _dedup_mode = (get_strategy_account_mode(_dedup_strategy)
                       if _dedup_strategy is not None else current_account_mode())
    except Exception as e:  # loud-ok: falls back to the pre-#465 behaviour; logged, never silent
        logger.warning(f"{strategy_label} {ticker}: dedup mode resolve failed ({e}) — "
                       f"falling back to process mode")
        _dedup_mode = current_account_mode()
    # 1. Duplicate check — trade row already exists for this ticker+date.
    async with pool.acquire() as conn:
        exists = await conn.fetchval(
            "SELECT EXISTS(SELECT 1 FROM mi_live_trades "
            "WHERE ticker=$1 AND alert_date=$2 AND account_mode=$3)",
            ticker, today, _dedup_mode,
        )
    if exists:
        logger.debug(f"{strategy_label} {ticker}: trade row already exists")
        try:
            await log_audit_event(
                "orb_duplicate", f"{strategy_label} {ticker} — {WINDOW_DUPLICATE}"
            )
        except Exception:  # loud-ok: log_audit_event() never raises — self-catches + logs internally (db.py); logger.debug already fired above, and the underlying trade row already exists from a prior telemetered pass
            pass
        # Not a failure — silent is correct here. It's already been handled once.
        return {"ticker": ticker, "action": ACTION_SKIPPED, "reason": WINDOW_DUPLICATE}

    # 1b. Open-position guard — block if we already hold this ticker from any
    # prior alert_date. Prevents cross-strategy / cross-day double exposure
    # (e.g. TEAM 5/04: 9M Day 2 placed bracket while MAGNA53 5/01 fill still
    # open). Same-day dedup above handles the within-day case; this catches
    # multi-day. `status='filled' AND remaining_shares > 0` is the canonical
    # "we own shares" signal (matches update_open_positions_live).
    async with pool.acquire() as conn:
        already_open = await conn.fetchval(
            """
            SELECT alert_date FROM mi_live_trades
            WHERE ticker = $1
              AND status = 'filled'
              AND remaining_shares > 0
              AND alert_date != $2
              AND account_mode = $3
            ORDER BY alert_date DESC
            LIMIT 1
            """,
            ticker, today, _dedup_mode,
        )
    if already_open is not None:
        reason = f"{BLOCK_TICKER_OPEN_POSITION}: open since {already_open.isoformat()}"
        return await _skip(
            reason, icon="🚫",
            audit_event="orb_blocked", action=ACTION_BLOCKED,
        )

    # 1a. Strategy phase gate. Fail-open if the strategy isn't in the registry
    # (legacy code path / pre-deploy state). Once seeded, the gate is the
    # single per-strategy enable/disable surface.
    from agents.market_intelligence.strategies.registry import get_strategy
    strategy = await get_strategy(signal_type)
    if strategy is not None:
        _phase_block = _phase_gate_skip_reason(strategy)
        if _phase_block is not None:
            return await _skip(
                _phase_block, icon="🚫",
                audit_event="orb_blocked", action=ACTION_BLOCKED,
            )
        if strategy.phase == "paper" and current_account_mode() == "live":
            return await _skip(
                BLOCK_PAPER_STRATEGY_ON_LIVE, icon="🚫",
                audit_event="orb_blocked", action=ACTION_BLOCKED,
            )

    # 2. Safeguards — position cap / daily loss / circuit breaker.
    # Resolve account_mode from strategy here (pre-spec-builder) so safeguards
    # filter by the correct mode AND so spec_builder can route alpaca calls
    # to the correct account for equity sizing.
    if strategy is not None:
        _safeguard_mode = resolve_account_mode_for_strategy(strategy)
    else:
        _safeguard_mode = current_account_mode()
    ok, sg_reason, drawdown_multiplier = await _check_safeguards(
        account_mode=_safeguard_mode, signal_type=signal_type,
    )
    if not ok:
        return await _skip(sg_reason, icon="🚫", audit_event="orb_blocked", action=ACTION_BLOCKED)

    # 2b. #452 exposure-family SHADOW (premortem R1, sitting-ruled 7/12 B3): observe-only —
    # emits audit + Telegram when this entry would lift same-family (active-theme) exposure
    # above the threshold. NEVER blocks; error-wrapped so it can never affect the entry
    # (the #94-hook pattern). Blocking = the operator fork after ~2 clean weeks
    # (exposure_family_cap_promotion review).
    try:
        from agents.market_intelligence.exposure_family import shadow_check_and_emit
        await shadow_check_and_emit(ticker, _safeguard_mode, strategy_label)
    except Exception as _fe:
        logger.warning(f"exposure_family shadow check failed for {ticker} (non-fatal): {_fe}")

    # 3. Bar fetch with retry.
    orb_bar = await fetch_orb_bar_with_retry(ticker, today, strategy_label)
    if not orb_bar:
        return await _skip(
            f"{INFRA_NO_BAR}: {BAR_RETRY_MAX} retries exhausted",
            icon="⚠️",
        )
    try:
        await log_audit_event(
            "orb_bar_fetched",
            f"{strategy_label} {ticker} O={orb_bar['open']:.2f} "
            f"H={orb_bar['high']:.2f} L={orb_bar['low']:.2f} "
            f"range={orb_bar['high']-orb_bar['low']:.2f}",
        )
    except Exception:  # loud-ok: log_audit_event() never raises — self-catches + logs internally (db.py); pipeline proceeds identically regardless (audit-only OHLC record for /why)
        pass

    # 4. Fade guard.
    fade_ok, fade_reason = await check_fade_guard(ticker, orb_bar, fade_midpoint_ratio)
    if not fade_ok:
        return await _skip(fade_reason, audit_event="orb_faded")

    # 4b. #490 real-time gap re-check — enforce MIN_GAP_PCT at SUBMISSION, not just at the scan
    # tick that wrote the alert row hours earlier. Placed here, beside the fade guard, because it
    # is the same class of gate (setup quality read off live price) and it must run BEFORE sizing
    # and submission. Fails open on every non-answer; see check_rt_gap_floor.
    gap_ok, gap_reason = await check_rt_gap_floor(ticker, alert_context, rt_gap_floor_pct)
    if not gap_ok:
        return await _skip(gap_reason, audit_event="orb_gap_below_floor")

    # 5. Strategy-specific spec build. Pass account_mode so the builder
    # fetches equity from the correct Alpaca account when sizing.
    order_spec, spec_reason = await spec_builder(
        alert_context, orb_bar, regime_record, _safeguard_mode,
    )
    if not order_spec:
        msg = spec_reason or "order spec failed"
        return await _skip(msg, audit_event="orb_skipped")

    # 5b. Composite sizing multiplier:
    #     final = per_strategy_multiplier (#65) × drawdown_tier_multiplier (2026-05-18)
    #
    # Per-strategy (#65): 9M Day 2 ramps at e.g. 0.5× without touching its
    # builder. Drawdown tier (2026-05-18): REDUCE = 0.5×, WATCH/OK = 1.0×.
    # Composition is methodology-correct — bleed weeks compound conservative
    # sizing across both axes (e.g. 9M Day 2 0.5× × REDUCE 0.5× = 0.25×).
    strategy_multiplier = 1.0
    if strategy is not None:
        strategy_multiplier = float(getattr(strategy, "position_size_multiplier", None) or 1.0)
    composite_multiplier = strategy_multiplier * drawdown_multiplier
    if composite_multiplier != 1.0 and order_spec.get("shares"):
        baseline_shares = int(order_spec["shares"])
        new_shares, clamped = _apply_composite_multiplier(baseline_shares, composite_multiplier)
        if clamped:
            try:
                await log_audit_event(
                    "sizing_multiplier_clamped",
                    f"{strategy_label} {ticker}: composite {composite_multiplier:.2f}x would size "
                    f"past builder baseline {baseline_shares} — clamped to baseline "
                    f"(20%/risk caps re-imposed)",
                )
            except Exception:  # loud-ok: log_audit_event() self-catches; the clamp already applied above
                pass
        if new_shares < 1:
            return await _skip(
                f"setup:size_too_small: post-multiplier ({composite_multiplier:.2f}x "
                f"= strategy {strategy_multiplier:.2f}x × drawdown {drawdown_multiplier:.2f}x) "
                f"shares < 1",
                audit_event="orb_skipped",
            )
        risk_per_share = float(order_spec.get("risk_per_share") or 0)
        entry_price = float(order_spec.get("entry_price") or 0)
        order_spec["shares"] = new_shares
        order_spec["position_size"] = round(new_shares * entry_price, 2)
        order_spec["risk_dollars"] = round(new_shares * risk_per_share, 2)
        try:
            await log_audit_event(
                "per_strategy_sizing_applied",
                f"{strategy_label} {ticker} composite={composite_multiplier:.2f}x "
                f"(strategy {strategy_multiplier:.2f}x × drawdown {drawdown_multiplier:.2f}x) → "
                f"shares={new_shares} risk=${order_spec['risk_dollars']:.0f}",
            )
        except Exception:  # loud-ok: log_audit_event() never raises — self-catches + logs internally (db.py); sizing math (order_spec) already mutated above this block, unaffected by the audit write
            pass

    # 6. Insert trade row — ATOMIC recount + insert (+ auto-enter confirm flip)
    # under the per-mode advisory cap lock (#461 TOCTOU fix, operator-approved
    # design docs/decisions/461_toctou_cap_design_2026-07-18.md).
    #
    # STEP 2's _check_safeguards is the cheap EARLY gate; between it and here
    # sit multiple awaits (exposure shadow, bar-fetch retry up to ~30s, fade
    # guard, spec build), so its count can be stale by insert time — concurrent
    # candidates (the ORB monitor's Semaphore(5)+gather) could all pass STEP 2
    # on the same count and overshoot the cap. This ONE transaction is the
    # AUTHORITATIVE check: pg_advisory_xact_lock serializes every entry funnel
    # in the same account_mode (coroutines, overlapping ORB triggers, AND
    # processes — EXECUTION_MODE=http; the lock lives in Postgres, the #151
    # lesson), the recount reads committed state via the SAME
    # count_open_positions SQL as STEP 2 (single SoT, zero drift), and the
    # insert + confirm flip commit BEFORE the lock releases — the next
    # waiter's recount necessarily sees this row. Paper never serializes
    # against live: hashtext('paper') != hashtext('live') (#66). No external
    # I/O inside the lock — the Alpaca submit stays post-commit (step 7); lock
    # hold time = recount + insert + update = single-digit ms. An error inside
    # the txn rolls back (lock auto-releases) and takes the existing
    # orb_pipeline_crash path. Cap VALUE, counting vocabulary (#436), and
    # skip-reason formats are UNCHANGED — only WHEN the count is read moved.
    account_mode = _safeguard_mode
    is_paper = account_mode == "paper"
    live_real_enabled = bool(strategy.live_real_enabled) if strategy else False
    # Auto-enter vs. staged-paper proposal (see _should_auto_enter): paper
    # auto-confirms; a phase=live strategy auto-enters REAL money only when
    # live_real_enabled=True (operator-signed 2026-06-20). Computable pre-txn —
    # both inputs already in scope.
    auto_enter = _should_auto_enter(account_mode, live_real_enabled)

    cap_reason: str | None = None
    trade_id = None
    async with pool.acquire() as conn:
        async with conn.transaction():
            await conn.fetchval(
                "SELECT pg_advisory_xact_lock($1, hashtext($2))",
                _CAP_LOCK_NAMESPACE, account_mode,
            )
            open_count = await count_open_positions(conn, account_mode)
            # #576 (2026-08-19, MRNA): a same-ticker/alert_date/account_mode
            # racer can commit its row in the gap between STEP 1's dedup
            # check (run OUTSIDE this lock — the exact TOCTOU window #461
            # fixed for the CAP count) and this recheck. When that racer is
            # THIS candidate's own sibling (the dual bar_stream/cron ORB
            # trigger, #475), the row that pushed open_count to/past the cap
            # can be this ticker's OWN just-filled entry — the operator then
            # reads "max positions reached" on a name already in the book,
            # which looks like a missed trade on a stock we hold. A same-
            # ticket race that lands BEFORE the cap is full already resolves
            # correctly via the INSERT's own `ON CONFLICT DO NOTHING` below
            # (silent WINDOW_DUPLICATE — proven by
            # test_same_ticker_conflict_still_window_duplicate_no_lock_leak);
            # the ONLY gap is when the cap check fires FIRST and never lets
            # that ON CONFLICT branch run. Checking for a same-key row before
            # the cap short-circuit closes that gap without loosening the cap
            # for anyone else's genuinely-new candidacy — a real cap block
            # for a DIFFERENT ticker is completely unaffected.
            _self_row_exists = await conn.fetchval(
                "SELECT EXISTS(SELECT 1 FROM mi_live_trades "
                "WHERE ticker=$1 AND alert_date=$2 AND account_mode=$3)",
                ticker, today, account_mode,
            )
            if _self_row_exists:
                pass  # let the INSERT below hit ON CONFLICT DO NOTHING -> WINDOW_DUPLICATE
            elif open_count >= MAX_CONCURRENT_LIVE_POSITIONS:
                # Byte-identical reason format to the STEP-2 gate — the
                # ledger's 'cap_blocked' mapping + the #197 CAP+1 alert both
                # match on it.
                cap_reason = cap_block_reason(
                    open_count, MAX_CONCURRENT_LIVE_POSITIONS, account_mode,
                )
            else:
                # Per-strategy cap (#65) — identical TOCTOU shape, covered by
                # the same per-mode lock. NULL = share global cap, no gate.
                strat_cap = await conn.fetchval(
                    "SELECT max_concurrent_positions FROM mi_strategies WHERE strategy_id = $1",
                    signal_type,
                )
                if strat_cap is not None:
                    strat_open = await count_open_positions(
                        conn, account_mode, signal_type,
                    )
                    if strat_open >= int(strat_cap):
                        cap_reason = strategy_cap_block_reason(
                            signal_type, strat_open, strat_cap, account_mode,
                        )
            if cap_reason is None:
                trade_id = await conn.fetchval(
                    """
                    INSERT INTO mi_live_trades
                        (ticker, alert_date, ep_score, catalyst_quality, gap_pct, regime,
                         status, orb_high, orb_low, atr_14,
                         entry_price, entry_shares, stop_price, hard_stop,
                         position_size, risk_dollars, signal_type, account_mode, proposed_at)
                    VALUES ($1,$2,$3,$4,$5,$6,'pending_confirmation',$7,$8,$9,
                            $10,$11,$12,$12,$13,$14,$15,$16,NOW())
                    ON CONFLICT (ticker, alert_date, account_mode) DO NOTHING
                    RETURNING id
                    """,
                    ticker, today,
                    alert_context.get("ep_score", 0),
                    alert_context.get("catalyst_quality"),
                    alert_context.get("gap_pct"),
                    regime_record.get("regime") if regime_record else None,
                    order_spec["orb_high"], order_spec["orb_low"], atr_14,
                    order_spec["entry_price"], float(order_spec["shares"]),
                    order_spec["stop_loss_price"],
                    order_spec["position_size"], order_spec["risk_dollars"],
                    signal_type, account_mode,
                )
                if trade_id and auto_enter:
                    # Auto-enter confirm flip INSIDE the same transaction: the
                    # row becomes countable (OPEN_POSITION_STATUSES includes
                    # 'confirmed', not 'pending_confirmation' — #436)
                    # atomically with the recount, closing the former sub-ms
                    # pending→confirmed gap as well.
                    await conn.execute(
                        "UPDATE mi_live_trades SET status='confirmed', confirmed_at=NOW() WHERE id=$1",
                        trade_id,
                    )
        # Transaction committed here → advisory xact lock released.

    if cap_reason is not None:
        # The race actually fired: STEP 2 passed on a then-current count that
        # went stale before insert. Observe-only telemetry — this event is the
        # #461 verify-live signal (a fired event in prod = the fix working).
        try:
            await log_audit_event(
                "cap_recheck_blocked",
                f"{strategy_label} {ticker} — insert-time cap recheck blocked: {cap_reason}",
            )
        except Exception:  # loud-ok: log_audit_event() never raises — self-catches + logs internally (db.py); the _skip below Telegrams + ledgers the block itself
            pass
        return await _skip(
            cap_reason, icon="🚫", audit_event="orb_blocked", action=ACTION_BLOCKED,
        )

    if not trade_id:
        logger.debug(f"{strategy_label} {ticker}: trade row insert hit unique conflict")
        return {"ticker": ticker, "action": ACTION_SKIPPED, "reason": WINDOW_DUPLICATE}

    # 7. Submit bracket. All _check_safeguards rules ran at STEP 2 + the cap
    # recheck above; submit_entry re-checks the /pause halt (defense in depth).
    if auto_enter:
        _mode_label = "paper" if is_paper else "LIVE real-$"
        logger.info(f"{strategy_label} {_mode_label} auto-enter: {ticker} (trade_id={trade_id})")
        order = await submit_entry(trade_id)
        if not order:
            logger.error(
                f"{strategy_label} {ticker}: submit_entry returned None "
                f"(trade_id={trade_id}) — check mi_live_trades.skip_reason"
            )
            try:
                await log_audit_event(
                    "orb_order_failed",
                    f"{strategy_label} {ticker} — submit_entry returned None "
                    f"(trade_id={trade_id})",
                )
            except Exception:  # loud-ok: log_audit_event() never raises — self-catches + logs internally (db.py); logger.error already fired above, and the failure Telegram below is unconditional (not gated on this try)
                pass
            await send_telegram_message(
                f"{mode_prefix(account_mode)}⚠️ *{ticker}* {strategy_label} auto-enter failed — "
                f"check logs (trade_id={trade_id})"
            )
            return {"ticker": ticker, "action": ACTION_AUTO_ENTER_FAILED}

        try:
            await log_audit_event(
                "orb_order_placed",
                f"{strategy_label} {ticker} entry=${order_spec['entry_price']:.2f} "
                f"stop=${order_spec['stop_loss_price']:.2f} "
                f"shares={order_spec['shares']} "
                f"risk=${order_spec['risk_dollars']:.0f} trade_id={trade_id}",
            )
        except Exception:  # loud-ok: log_audit_event() never raises — self-catches + logs internally (db.py); trade already durable in mi_live_trades + submitted to Alpaca before this line, and the success Telegram below is unconditional
            pass
        # #475 (2026-07-15, noise reduction): the "order placed (pending trigger)"
        # Telegram is DROPPED — a pending stop-limit is not yet a trade. The WS
        # FILLED alert (trade_stream._process_entry_fill: entry price, shares,
        # stop) is the sole per-trade Telegram. Placement stays observable via
        # this log line + the orb_order_placed audit row above. The former
        # theme-membership Telegram append (C8) went with the message; theme
        # context lives in the EP alert/briefing surfaces.
        logger.info(
            f"{strategy_label} {success_title} [{account_mode}]: {ticker} "
            f"stop-limit BUY @${order_spec['entry_price']:.2f} (pending trigger) | "
            f"{stop_label}: ${order_spec['stop_loss_price']:.2f} | "
            f"shares={order_spec['shares']} risk=${order_spec['risk_dollars']:.0f} | "
            f"cancels 10:00 ET if unfilled (trade_id={trade_id})"
        )
        return {"ticker": ticker, "action": ACTION_AUTO_ENTERED, "trade_id": trade_id}

    # Live + NOT live_real_enabled — staged-paper ramp: Telegram proposal, manual confirm.
    sent = await send_trade_proposal(
        alert_context, order_spec, trade_id,
        live_real_enabled=live_real_enabled,
        account_mode=account_mode,
    )
    if sent:
        logger.info(f"{strategy_label} trade proposal sent: {ticker} (id={trade_id})")
        return {"ticker": ticker, "action": ACTION_PROPOSED, "trade_id": trade_id}
    await send_telegram_message(
        f"{mode_prefix(account_mode)}⚠️ *{ticker}* {strategy_label} proposal send failed — "
        f"check logs (trade_id={trade_id})"
    )
    return {"ticker": ticker, "action": ACTION_PROPOSAL_SEND_FAILED}
