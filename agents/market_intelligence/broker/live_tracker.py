"""
Live trade tracker — the real-time analog of backtester/tracker.py.

Reuses the same trading logic (ORB entry, SMA trail, partials) but executes
via Alpaca broker instead of simulating retroactively.

Schedule:
- 9:32 AM ET: process_new_alerts_live() — ORB monitor, send proposals
- 4:45 PM ET: update_open_positions_live() — SMA trail, partials, stop updates
- 9:35 AM ET: morning_stop_refresh() — refresh stops for Day 2+ positions

#533 (2026-08-30, operator-signed): process_new_alerts_live orders the day's HIGH
board by prior-day RS composite (ep_score tiebreak) instead of the accidental
alphabetical order — flag `ep_slot_rank_rs`, default ON. Revert SQL + evidence +
the watch record live on ep_slot_rank_shadow.py's docstring:
    INSERT INTO mi_safeguard_state (safeguard, account_mode, state, last_transition_at, updated_at)
    VALUES ('ep_slot_rank_rs', 'global', 'off', NOW(), NOW())
    ON CONFLICT (safeguard, account_mode) DO UPDATE SET state = EXCLUDED.state, updated_at = NOW();
"""
from __future__ import annotations

import asyncio
import json
import logging
from datetime import date, datetime, time, timedelta, timezone
from zoneinfo import ZoneInfo

from agents.market_intelligence.broker import alpaca_client as alpaca
# #490: MAGNA53's OWN gap criterion, imported here so the opt-in at the call site names the
# strategy whose rule it is. Deliberately NOT imported inside entry_pipeline — that file is the
# SHARED funnel for MAGNA53 and 9M Day 2, and baking one strategy's constant into it is exactly
# how the 10%-floor-applied-to-a-3%-strategy defect happened.
from agents.market_intelligence.ep_detector import MIN_GAP_PCT as _MAGNA53_MIN_GAP_PCT
from agents.market_intelligence.broker.entry_pipeline import (
    ACTION_AUTO_ENTERED,
    ACTION_AUTO_ENTER_FAILED,
    ACTION_BLOCKED,
    ACTION_PROPOSAL_SEND_FAILED,
    ACTION_PROPOSED,
    ACTION_SKIPPED,
    submit_trade_entry,
)
from agents.market_intelligence.broker.exit_logic import (
    adr20_pct_from_bars,
    apply_daily_exit_step,
    depth_stop_price,
)
from agents.market_intelligence.broker import breakout_pp_exit as _bpp
from agents.market_intelligence.broker import breakout_pp_rules as _bpp_rules
from agents.market_intelligence.broker.order_manager import (
    BREAKOUT_PP_EXIT_RULE,
    BREAKOUT_V1_SIGNAL_TYPE as _BREAKOUT_V1_SIGNAL_TYPE,
    DEPTH_EXIT_RULE,
    depth_sale_words,
    profit_take_shares,
    prepare_orb_order,
    execute_partial_exit,
    execute_full_exit,
    finalize_stop_fill,
    update_stop,
)
from agents.market_intelligence.broker.skip_reasons import (
    BLOCK_CIRCUIT_BREAKER,
    BLOCK_DAILY_LOSS,
    BLOCK_MAX_POSITIONS,
    BLOCK_TRADING_PAUSED,
    cap_block_reason,
    strategy_cap_block_reason,
    INFRA_HALT_STATE_UNREADABLE,
    SETUP_ACCOUNT_FETCH_FAILED,
    WINDOW_DUPLICATE,
    humanize,
)
from agents.market_intelligence.backtester.filters import check_filters, compute_atr_14
from agents.market_intelligence.collector import et_today, get_index_history
from agents.market_intelligence.briefing import send_telegram_message
from agents.market_intelligence.db import (
    get_pool, get_manual_halt_state, _coerce_date, OPEN_POSITION_STATUSES,
    log_audit_event, get_runtime_toggle, latest_complete_score_date,
    get_same_day_excluded_stop_candidates,
)
# #533 (2026-08-30, operator-signed): the acting within-day slot-ranking key + the
# five-ranking watch recorder live in ONE module so what acts and what is recorded
# as acting cannot drift (the ep_detector/ep_shortlist_shadow precedent).
from agents.market_intelligence.ep_slot_rank_shadow import (
    rank_board_by_rs, snapshot_slot_rank_board,
)
from agents.market_intelligence.constants import (
    LIVE_TRADING_ENABLED,
    MAX_CONCURRENT_LIVE_POSITIONS,
    DAILY_LOSS_LIMIT_PCT,
    CIRCUIT_BREAKER_CONSEC_LOSSES,
    CIRCUIT_BREAKER_COOLDOWN_DAYS,
    current_account_mode,
    mode_prefix,
    resolve_strategy_mode_nonfatal,
    strategy_mode_prefix,
)

logger = logging.getLogger(__name__)


# ── Safeguards ───────────────────────────────────────────────────────────────


async def count_open_positions(
    conn, account_mode: str, signal_type: str | None = None,
) -> int:
    """Open-position count for the cap gates — the single SQL source of truth.

    Shared by `_check_safeguards` (the STEP-2 cheap early gate) AND
    `entry_pipeline.submit_trade_entry` STEP 6 (the authoritative insert-time
    recount under the per-mode advisory cap lock, #461) so the two reads can
    never drift. Counting vocabulary = `db.OPEN_POSITION_STATUSES` (inert
    `pending_confirmation` proposals excluded, #436 fork B). Per-mode isolated
    (#66); pass `signal_type` for the per-strategy (#65) variant.
    """
    if signal_type is None:
        return await conn.fetchval("""
            SELECT COUNT(*) FROM mi_live_trades
            WHERE status = ANY($2) AND account_mode = $1
        """, account_mode, list(OPEN_POSITION_STATUSES))
    return await conn.fetchval("""
        SELECT COUNT(*) FROM mi_live_trades
        WHERE status = ANY($3) AND account_mode = $1 AND signal_type = $2
    """, account_mode, signal_type, list(OPEN_POSITION_STATUSES))


_ET_ZONE = ZoneInfo("America/New_York")


def _exit_leg_et_date(raw_time) -> "date | None":
    """The ET calendar date of one `exits[]` leg's `time`. Aware stamps (every current broker-fill
    writer: `datetime.now(timezone.utc).isoformat()`) convert to ET. A NAIVE stamp keeps the date
    as written: older rows stored naive UTC (e.g. "2026-05-15T13:33:38") and `exit_logic` writes
    naive ET 16:00 — every fill lands in market hours, when both name the same ET date. None when
    unreadable."""
    try:
        ts = datetime.fromisoformat(str(raw_time))
    except (TypeError, ValueError):
        return None
    if ts.tzinfo is None:
        return ts.date()
    return ts.astimezone(_ET_ZONE).date()


def _losing_exit_legs(exits):
    """(pnl, ET date) of every LOSING leg of one trade's `exits` (a JSONB list, or its JSON text
    when no codec decoded it). Legs without both `pnl` and `time` are skipped (the circuit
    breaker's partial arm reads the same two keys); the date is None when unreadable. PURE."""
    if isinstance(exits, str):
        try:
            exits = json.loads(exits)
        except ValueError:
            return
    for leg in exits or []:
        if not isinstance(leg, dict) or leg.get("pnl") is None or not leg.get("time"):
            continue
        try:
            pnl = float(leg["pnl"])
        except (TypeError, ValueError):
            continue
        if pnl < 0:
            yield pnl, _exit_leg_et_date(leg["time"])


def _partial_losses_realized_on(exit_rows, today: date) -> float:
    """⚖ #687 ruling (1), operator 2026-10-01: the realized LOSSES of partial sales on trades
    still OPEN, dated `today` (ET). Returns a sum <= 0. PURE.

    `exit_rows` are `mi_live_trades` rows carrying `exits` (a JSONB list, or its JSON text
    when no codec decoded it). Each LEG counts on its own: a leg whose `pnl` is below zero
    and whose `time` falls on `today` (ET). Profit legs never offset a loss leg here — the
    ruling is that a loss on a partial sale counts at once. Legs without both `pnl` and
    `time` are skipped (the circuit breaker's partial arm reads the same two keys)."""
    total = 0.0
    for row in exit_rows or []:
        exits = row["exits"] if not isinstance(row, (list, tuple)) else row
        for pnl, leg_day in _losing_exit_legs(exits):
            if leg_day == today:
                total += pnl
    return total


def _closed_losses_realized_on(closed_rows, today: date) -> float:
    """⚖ #687 ruling (iv), operator 2026-10-02: the realized loss of trades CLOSED `today` (ET),
    each dollar counted ONCE, on the day it was realized. Returns a sum <= 0. PURE.

    `closed_rows` carry `total_pnl` and `exits` (the trade's legs; `total_pnl = sum(exits[].pnl)`,
    the invariant every closer writes — order_manager "Invariant: total_pnl = sum(exits[].pnl)").
    Per trade, `total_pnl` minus every LOSING leg dated an EARLIER ET day than `today`: ruling (1)
    already counted each of those on its own day, on the trade while it was still open (exactly
    the legs `_partial_losses_realized_on` reads: `pnl < 0` with a readable `time`). The trade
    counts when that remainder is a loss.
    - A losing leg dated TODAY stays inside `total_pnl` and counts once, here (the open-trade arm
      no longer sees a closed trade).
    - A leg with no readable `time` is never netted — the open-trade arm never counted it either.
    - PROFIT legs are never netted, whatever their day (unchanged from ruling (1)'s design: a
      profit leg is never counted on its own day, so it stays inside `total_pnl` and still
      offsets the trade's loss on the close day, as the closed arm always did)."""
    total = 0.0
    for row in closed_rows or []:
        try:
            pnl = float(row["total_pnl"] or 0)
        except (TypeError, ValueError):
            continue
        counted_earlier = sum(
            leg_pnl for leg_pnl, leg_day in _losing_exit_legs(row["exits"])
            if leg_day is not None and leg_day < today)
        remainder = pnl - counted_earlier
        if remainder < 0:
            total += remainder
    return total


async def _check_safeguards(
    account_mode: str | None = None,
    signal_type: str | None = None,
) -> tuple[bool, str | None, float]:
    """
    Check all safety gates before proposing a new trade.
    Returns (ok, reason, sizing_multiplier).
      - ok=True, reason=None, multiplier in [0.0, 1.0]: allow with possibly-reduced sizing
      - ok=False, reason=<block:*>, multiplier=0.0: blocked

    Dual-account aware (#66, 2026-05-10): when account_mode is passed,
    all mi_live_trades queries filter by AND account_mode = $1, and
    alpaca.get_account routes to the per-mode TradingClient. Per-mode
    isolated safeguards: paper at-cap doesn't constrain live and vice
    versa. None falls back to current_account_mode() for legacy callers.

    Per-strategy cap (#65): when signal_type is passed AND the strategy
    row has max_concurrent_positions set, enforces a per-strategy slot
    budget within the per-mode global envelope. NULL on the strategy row
    means "share the global cap" — no per-strategy gate.

    Tiered drawdown breaker (2026-05-18): active phase returns the tier's
    sizing multiplier (1.0 for OK/WATCH, 0.5 for REDUCE, 0.0 for BLOCK).
    Shadow phase always returns 1.0. Composes with mi_strategies
    .position_size_multiplier in entry_pipeline.
    """
    if not LIVE_TRADING_ENABLED:
        logger.debug("Safeguard: live trading disabled")
        return False, "live_trading_disabled", 0.0

    if account_mode is None:
        account_mode = current_account_mode()

    # Manual real-money halt (#345) — the operator's one-command `/pause` kill switch.
    # Highest-priority gate: a manual halt overrides every other safeguard. LIVE path
    # only (paper/shadow telemetry keeps running). DB-backed (mi_safeguard_state), read
    # per-entry so `/pause` takes effect on the NEXT entry with no redeploy. Fail-SAFE:
    # an unreadable halt state blocks the live path (capital protection) under a DISTINCT
    # reason so the operator is never told "you paused" when a DB error caused it.
    if account_mode == "live":
        halt = await get_manual_halt_state()
        if halt == "on":
            logger.info(f"Safeguard [{account_mode}] blocked: manual trading halt (/pause)")
            return False, BLOCK_TRADING_PAUSED, 0.0
        if halt == "unreadable":
            logger.error(
                f"Safeguard [{account_mode}] blocked: halt-state unreadable → failing safe"
            )
            return False, INFRA_HALT_STATE_UNREADABLE, 0.0

    pool = await get_pool()
    async with pool.acquire() as conn:
        # Max concurrent positions — per mode (paper noise doesn't
        # constrain live; live noise doesn't constrain paper). This read is
        # the CHEAP EARLY gate; the authoritative recount happens at insert
        # time inside entry_pipeline's per-mode-locked transaction (#461),
        # via the SAME count_open_positions helper.
        open_count = await count_open_positions(conn, account_mode)
        if open_count >= MAX_CONCURRENT_LIVE_POSITIONS:
            logger.info(
                f"Safeguard [{account_mode}] blocked: max positions "
                f"({open_count}/{MAX_CONCURRENT_LIVE_POSITIONS})"
            )
            # #484: built by the SHARED helper — this string is string-MATCHED by
            # the #197 CAP+1 alert, and it used to be hand-copied into
            # entry_pipeline's STEP-6 recount too.
            return False, cap_block_reason(
                open_count, MAX_CONCURRENT_LIVE_POSITIONS, account_mode,
            ), 0.0

        # Per-strategy concurrent-position cap (#65). Enforced WITHIN the
        # per-mode global envelope above. NULL on mi_strategies = share
        # global cap, no per-strategy gate.
        if signal_type:
            strat_cap = await conn.fetchval(
                "SELECT max_concurrent_positions FROM mi_strategies WHERE strategy_id = $1",
                signal_type,
            )
            if strat_cap is not None:
                strat_open = await count_open_positions(
                    conn, account_mode, signal_type,
                )
                if strat_open >= int(strat_cap):
                    logger.info(
                        f"Safeguard [{account_mode}/{signal_type}] blocked: "
                        f"per-strategy cap ({strat_open}/{strat_cap})"
                    )
                    return False, strategy_cap_block_reason(
                        signal_type, strat_open, strat_cap, account_mode,
                    ), 0.0

        # Daily loss limit (per-mode)
        try:
            account = await alpaca.get_account(account_mode=account_mode)
            equity = account["equity"]
        except Exception as e:
            logger.error(f"Safeguard [{account_mode}]: cannot get account equity: {e}")
            return False, f"{SETUP_ACCOUNT_FETCH_FAILED}: {e}", 0.0

        # PDT guard RETIRED 2026-06-04 (#181). FINRA Rule 4210 + Alpaca's new
        # intraday-margin framework eliminated the PDT designation and the $25K
        # floor (4x intraday BP now from $2K). Alpaca returns pattern_day_trader=
        # false / daytrade_count=0 (fields removed by 2026-07-06) and enforces
        # intraday-margin pre-trade checks broker-side (orders into a margin
        # deficit are rejected). No Apollo-side day-trade-count gate is needed.
        # See docs/setups/safeguards.md change log 2026-06-04.

        today = et_today()
        # FL-2 daily-loss COVERAGE fix (operator-signed 2026-07-24, CHANGE_PROCESS in
        # safeguards.md): attribute each realized loss to its CLOSE day (ET), NOT alert_date.
        # A multi-day position (Day 2-5: SMA trail / partials / time-stop) that stops out
        # today was INVISIBLE to this backstop under `alert_date = today` — its loss got
        # mis-attributed to the (prior) alert day. Each realized loss now counts ONCE, on the
        # day it is realized: this CLOSES the multi-day under-count hole (the safety win) AND
        # removes the old alert-day OVER-attribution — net MORE-CORRECT, not uniformly tighter
        # (some days it counts less: old 5/21 -$1505 -> new -$643, the position wasn't lost yet
        # on its alert day). Cannot false-trip (every trip still maps to real realized losses
        # >= 2%). Backtest: old vs new disagreed on 12/28 loss-days ($0-under-old days had real
        # losses: 6/24 -$1483, 5/26 -$862). closed_at 100% populated on closed trades (0/40
        # NULL); ET conversion per the TIMESTAMPTZ->ET-date rule (CLAUDE.md time-handling).
        # ⚖ #687 RULING (iv), operator 2026-10-02: count each realized dollar ONCE, on the day it
        # was realized. Ruling (1) (below) counts a losing partial leg on its own day while the
        # trade is open; on the day the trade later CLOSES, that leg is netted out of its
        # total_pnl here (`_closed_losses_realized_on`), so only what was realized TODAY counts.
        # Same rows as before (the WHERE is unchanged); the sum is taken per trade in Python.
        closed_today = await conn.fetch("""
            SELECT total_pnl, exits
            FROM mi_live_trades
            WHERE (closed_at AT TIME ZONE 'America/New_York')::date = $1
              AND status = 'closed' AND total_pnl < 0
              AND account_mode = $2
        """, today, account_mode)
        today_losses = _closed_losses_realized_on(closed_today, today)
        # ⚖ #687 RULING (1), operator 2026-10-01 ("Yes"): a loss on a PARTIAL sale counts toward
        # this limit AT ONCE — not only when the trade later closes. The query above sees CLOSED
        # trades only, so a sale that sells part of a position at a loss and leaves the rest open
        # (the close-below sale beside a resting +8R profit-take third; a stop that partly filled)
        # was invisible here until the remainder exited, possibly days later. Each such losing
        # leg dated today (ET) on a still-OPEN trade is added; on its close day it is netted out
        # of the closed arm above (ruling (iv)). SSoT: docs/setups/safeguards.md item 5 + change
        # log 2026-10-02.
        open_trade_exits = await conn.fetch("""
            SELECT exits FROM mi_live_trades
            WHERE status <> 'closed' AND account_mode = $1
              AND exits IS NOT NULL
        """, account_mode)
        today_losses += _partial_losses_realized_on(open_trade_exits, today)
        daily_limit = equity * DAILY_LOSS_LIMIT_PCT
        if abs(today_losses) >= daily_limit:
            logger.info(
                f"Safeguard [{account_mode}] blocked: daily loss limit "
                f"(${today_losses:+,.0f} >= ${daily_limit:.0f})"
            )
            return False, (
                f"{BLOCK_DAILY_LOSS}: ${today_losses:+,.0f} >= ${daily_limit:.0f} "
                f"(mode={account_mode})"
            ), 0.0

        # Circuit breaker: N consecutive losses, per mode (so a paper losing
        # streak doesn't gate live entries). Time-based escape valve mirrors
        # backtester semantics — without it, once N losses close, no new
        # entries can ever fire (the trailing-N window is permanently
        # all-losses until a winner ages into it).
        # ⚖ REALIZED PARTIAL PROFITS COUNT AS OUTCOMES (operator-signed 2026-08-05).
        # The streak read CLOSED trades only, and that is structurally biased against this
        # methodology: losers close fast (all 14 live losses closed within ~a day) while
        # winners are HELD by design. So the one event that could break the streak — a
        # winner closing — is the very thing the strategy delays, and a held winner
        # contributed nothing however well it did. Operator: *"winners tend to be held
        # longer... this circuit breaker will remain basically for a long time"* and *"what
        # we need to prevent is perpetual blockers otherwise we'll never trade."*
        #
        # A realized partial is BANKED money and enters the outcome sequence at its own exit
        # time, exactly like a close. It is not a special-case reset: the rule is still "are
        # the last N outcomes ALL losses", and a win anywhere in that window answers no.
        # Nothing is erased — if the trade later closes red, that close enters as its own
        # loss, so the record stays honest in both directions.
        #
        # ⚠ REJECTED, with evidence: expiring old losses by age. The replay
        # (`docs/analysis/535_circuit_breaker_partials_2026-08-05.md`) showed EVERY window
        # that would have unblocked 2026-08-05 also makes the breaker unable to fire on the
        # real 14-loss streak it exists for — at 14 days its peak count is 8, below the
        # threshold of 10, because those losses arrived ~1 per 2 days and expire faster than
        # they accumulate. That is disarming the safeguard, not modernising it.
        #
        # UNREALIZED gains are deliberately NOT counted: 5 of 12 live trades reached +1R or
        # better and ALL FIVE finished losers (#503), so "currently up" has been close to
        # uninformative here — and counting it would disarm the breaker precisely during the
        # round-tripping it should catch.
        recent_closed = await conn.fetch("""
            SELECT total_pnl, closed_at FROM mi_live_trades
            WHERE status = 'closed' AND total_pnl IS NOT NULL
              AND account_mode = $2
            UNION ALL
            -- Realized partial exits on STILL-OPEN trades. `exits` is the same array
            -- `total_pnl` is summed from on close, so this reads banked cash, never
            -- mark-to-market (verified on PLTR 307: total_pnl 33.27 = the single 2-share
            -- exit, while the position's unrealized was ~89).
            SELECT (e->>'pnl')::double precision AS total_pnl,
                   (e->>'time')::timestamptz     AS closed_at
              FROM mi_live_trades t
              CROSS JOIN LATERAL jsonb_array_elements(t.exits::jsonb) AS e
             WHERE t.status <> 'closed' AND t.account_mode = $2
               AND t.exits IS NOT NULL
               AND e ? 'pnl' AND e ? 'time'
            ORDER BY closed_at DESC LIMIT $1
        """, CIRCUIT_BREAKER_CONSEC_LOSSES, account_mode)

        if len(recent_closed) >= CIRCUIT_BREAKER_CONSEC_LOSSES:
            all_losses = all(r["total_pnl"] <= 0 for r in recent_closed)
            if all_losses:
                latest_loss_at = recent_closed[0]["closed_at"]
                cooldown_until = latest_loss_at + timedelta(days=CIRCUIT_BREAKER_COOLDOWN_DAYS)
                now = datetime.now(timezone.utc)
                if now < cooldown_until:
                    logger.info(
                        f"Safeguard blocked: circuit breaker "
                        f"({CIRCUIT_BREAKER_CONSEC_LOSSES} consecutive losses, "
                        f"cooldown until {cooldown_until.isoformat()})"
                    )
                    return False, (
                        f"{BLOCK_CIRCUIT_BREAKER}: cooldown until "
                        f"{cooldown_until.isoformat()}"
                    ), 0.0

    # Drawdown breaker — active phase only (env DRAWDOWN_BREAKER_PHASE='active').
    # Tiered (2026-05-18): BLOCK state hard-blocks new entries; REDUCE state
    # returns ok=True with 0.5× multiplier (entry_pipeline halves shares);
    # WATCH/OK return 1.0×. Shadow phase always returns 1.0× (informational
    # only). SSoT: docs/setups/safeguards.md.
    drawdown_multiplier = 1.0
    from agents.market_intelligence.constants import DRAWDOWN_BREAKER_PHASE
    if DRAWDOWN_BREAKER_PHASE == "active":
        from agents.market_intelligence.broker.drawdown_breaker import (
            read_breaker_state, get_tier_multiplier,
        )
        from agents.market_intelligence.broker.skip_reasons import BLOCK_DRAWDOWN_BREAKER
        dd_state = await read_breaker_state(account_mode)
        drawdown_multiplier = get_tier_multiplier(dd_state)
        if drawdown_multiplier == 0.0:
            # BLOCK tier — hard block
            logger.info(f"Safeguard [{account_mode}] blocked: drawdown {dd_state}")
            return False, (
                f"{BLOCK_DRAWDOWN_BREAKER}: {dd_state} (mode={account_mode}, "
                f"see mi_safeguard_state)"
            ), 0.0
        if drawdown_multiplier < 1.0:
            logger.info(
                f"Safeguard [{account_mode}]: drawdown {dd_state} → "
                f"sizing multiplier {drawdown_multiplier}×"
            )

    return True, None, drawdown_multiplier


# ── New Alerts (Day 1) ───────────────────────────────────────────────────────


def _is_window_duplicate_reason(reason) -> bool:
    """True when a skip reason is the WINDOW_DUPLICATE constant (bare, or with
    the vocabulary's optional ':detail' suffix). Matches on the constant from
    skip_reasons.py, never on the humanized display string (#475)."""
    if not isinstance(reason, str):
        return False
    return reason == WINDOW_DUPLICATE or reason.startswith(WINDOW_DUPLICATE + ":")


# ── #706: send each skip LINE once per ET day ────────────────────────────────
# `process_new_alerts_live` evaluates EVERY HIGH alert on every call, and it is called from the
# bar stream (once per first-bar arrival — i.e. once per subscribed ticker) AND the 09:31 cron
# fallback. Two evaluations that OVERLAP (both pass the per-ticker "already has a row today"
# check below before either has written its skip row) both run the pipeline and each sent its
# own grouped digest (2026-10-21: SPCX twice, 10 s apart). Message-only: the evaluation, the
# skip row and the result list are untouched; only the digest LINE for a (ticker, reason class)
# already announced today is held back.
#
#   key   = (ET day, ticker, reason CLASS) where the class is the vocabulary's aggregation key
#           `category:code` (skip_reasons.py) — the free-form detail after it ("$1.24 vs $0.83")
#           is dropped, so a number that moved does not resend, while a CHANGED reason
#           ("filter:atr_too_high" -> "block:max_positions") is a new key and does.
#   reset = the ET day: the day is part of the key, and keys of earlier days are dropped on
#           each call (a day 2 evaluation starts empty). Both entry paths run in the one
#           execution process and one event loop (the bar stream is a task on it; the cron
#           arrives as an HTTP call into it), so one in-memory set covers both.
#   lock  = `claim + send` is ONE critical section. An overlapping evaluation that reaches the
#           digest while the first is still sending WAITS for its result, then re-checks: sent ->
#           it adds nothing; failed -> it claims and sends the line itself. Without the lock the
#           second one would pass over the first's claim, the first's send could then fail and
#           release it, and NOBODY would send the line.
#   send failure = the claim is released, so an evaluation WAITING on the lock retries the line.
#           ⚠ That is the only retry there is: a LATER, non-overlapping call never reaches the
#           digest for a ticker that already has today's skip row (the per-ticker existence
#           check returns None for any status), so a send that failed with no overlapping
#           evaluation is not retried — exactly as before #706.
#   restart = the set is process memory: a restart empties it. A repeat after a restart needs a
#           skip path that wrote no row (the existence check stops every other re-evaluation);
#           that repeat is the accepted failure direction — a swallowed first line never is.
_skip_digest_sent: set[tuple[date, str, str]] = set()
_skip_digest_lock = asyncio.Lock()


def _skip_reason_class(reason) -> str:
    """`category:code` of a stored skip reason ('setup:stop_too_wide: ORB $1.24 …' ->
    'setup:stop_too_wide'). A free-form / legacy reason with no ':' is its whole stripped text."""
    if not isinstance(reason, str) or not reason.strip():
        return "no_reason"
    return ":".join(p.strip() for p in reason.split(":", 2)[:2])


def _claim_unsent_skips(digest_results: list[dict], today: date):
    """(fresh results to send, claimed keys). Pure bookkeeping on `_skip_digest_sent`; callers
    hold `_skip_digest_lock` across this AND the send so the claim cannot be passed over."""
    for k in [k for k in _skip_digest_sent if k[0] < today]:
        _skip_digest_sent.discard(k)
    fresh: list[dict] = []
    claimed: list[tuple[date, str, str]] = []
    for r in digest_results:
        key = (today, str(r.get("ticker")), _skip_reason_class(r.get("reason")))
        if key in _skip_digest_sent:
            continue
        _skip_digest_sent.add(key)
        claimed.append(key)
        fresh.append(r)
    return fresh, claimed


async def _send_skip_digest(digest_results: list[dict], today: date, mode_prefix: str) -> None:
    """Send the grouped skip digest for the lines not yet announced today (see the block above).
    A failed send releases its claim; the lock makes that release reach a waiting evaluation."""
    if not digest_results:
        return
    async with _skip_digest_lock:
        fresh, claimed = _claim_unsent_skips(digest_results, today)
        if not fresh:
            return
        bullets = "\n".join(
            f"• `{r['ticker']}` — {humanize(r.get('reason'))}"
            for r in fresh
        )
        sent_ok = False
        try:
            sent_ok = bool(await send_telegram_message(
                f"{mode_prefix}⏭️ *ORB skips ({today}, {len(fresh)})*\n{bullets}"
            ))
        except Exception as e:
            logger.error(f"ORB grouped-skip Telegram failed — {e}")
        if not sent_ok:
            _skip_digest_sent.difference_update(claimed)


def _reset_skip_digest_dedupe() -> None:
    """Forget every sent skip line and start a fresh lock (tests; never called in production)."""
    global _skip_digest_lock
    _skip_digest_sent.clear()
    _skip_digest_lock = asyncio.Lock()


# The day's HIGH-alert board — ⚠ BYTE-IDENTICAL to the pre-#533 inline query and it
# must stay that way (pinned by tests/test_533_slot_ranking.py): with the
# `ep_slot_rank_rs` toggle OFF this query's own row order IS the acting order, so
# any edit here silently moves the revert target. `DISTINCT ON (ticker)` +
# `ORDER BY ticker, ep_score DESC` does the per-ticker dedup (max ep_score row
# survives); the ACROSS-ticker order it leaves behind is ALPHABETICAL — the #533
# defect — which is why the deliberate ordering below is applied in Python
# afterwards instead of restructuring this SQL.
_HIGH_ALERT_SELECT_SQL = """
            SELECT DISTINCT ON (ticker)
                   ticker, alert_date, gap_pct, rel_volume, ep_score,
                   score_tier, catalyst, catalyst_quality, vol_percentile
            FROM mi_ep_alerts
            WHERE alert_date = $1 AND score_tier = 'HIGH'
            ORDER BY ticker, ep_score DESC
        """

# Prior-day RS for the #533 slot ranking — $2 is the board's tickers, $1 the
# resolved COMPLETE score date (db.latest_complete_score_date, the #554 guard: a
# stray one-row Saturday run can never rank the board). adv_20 + close ride along
# as raw inputs for the watch record (ADV$ = adv_20 x close, the pre-gap-price
# convention of ep_detector's large-cap floor).
_SLOT_RANK_RS_SQL = """
    SELECT ticker, rs_composite, rs_rank, adv_20, close
    FROM mi_stock_scores
    WHERE score_date = $1 AND ticker = ANY($2)
"""


async def process_new_alerts_live(today: date | None = None, trigger: str = "cron") -> list[dict]:
    """
    For each HIGH EP alert today, run the unified entry pipeline.

    Pre-pipeline work (MAGNA53-specific): check_filters (ADV/ATR%) and
    compute ATR14. Pipeline then handles: duplicate check, safeguards,
    bar fetch with retry, fade guard, spec build, DB insert, Alpaca submit
    (paper auto-confirm or live proposal), and terminal-state Telegram on
    every failure branch.

    trigger: "bar_stream" | "cron_9_31" | "cron_fallback" | "cron"
    """
    if today is None:
        today = et_today()

    if not LIVE_TRADING_ENABLED:
        logger.info("Live trading disabled, skipping")
        return []

    from agents.market_intelligence.db import log_audit_event

    pool = await get_pool()
    async with pool.acquire() as conn:
        alerts = await conn.fetch(_HIGH_ALERT_SELECT_SQL, today)
    alerts = [dict(a) for a in alerts]

    if not alerts:
        logger.info("No HIGH EP alerts today for live trading")
        return []

    # ── #533 WITHIN-DAY SLOT RANKING (2026-08-30, OPERATOR-SIGNED) ────────────
    # "switch to RS rank, but observe going forward if it deteriorates or other
    # ranking starts to do better." The list order below is the board's slot
    # PRIORITY: tasks are created in list order and the 5-way semaphore admits
    # the head of the list first, so under cap contention the top-ranked names
    # reach the insert-time recount (#461) first. Pre-#533 that priority was
    # ALPHABETICAL (the DISTINCT ON accident above). Acting order: prior-day
    # rs_composite DESC, ep_score DESC tiebreak, ticker ASC (slot_rank_key in
    # ep_slot_rank_shadow.py — evidence, revert SQL and the missing-RS-row
    # policy live on that module's docstring; SSoT docs/setups/magna53_ep.md).
    # ONE revert flag — `ep_slot_rank_rs` / EP_SLOT_RANK_RS_ENABLED, default ON;
    # OFF → the legacy query's own order acts, byte-identical, no redeploy.
    # Fail direction on ANY error here: the legacy order acts, loudly
    # (logger.exception + slot_rank_fallback audit row) — never a dead selection.
    # Note: concurrency means priority, not a strict serial guarantee — a
    # top-ranked name stalled on its bar fetch does not block lower picks
    # (deliberate; serializing would let one stall eat the 09:45 window).
    _slot_rank_live = True
    try:
        _slot_rank_live = await get_runtime_toggle(
            "ep_slot_rank_rs", "EP_SLOT_RANK_RS_ENABLED", default=True)
    except Exception as _ste:  # loud-ok: get_runtime_toggle fails open internally; belt+braces
        logger.warning(f"ep_slot_rank_rs toggle read failed — RS slot ranking stays ON: {_ste}")
    _rs_by_ticker: dict[str, dict] = {}
    _rs_score_date: "date | None" = None
    _slot_rank_acting = False
    try:
        async with pool.acquire() as conn:
            # #554 guard: latest COMPLETE run strictly before today — a stray
            # one-row Saturday write can never rank the board, and "prior-day"
            # stays prior-day even after tonight's run lands.
            _rs_score_date = await latest_complete_score_date(
                conn, on_or_before=today - timedelta(days=1))
            if _rs_score_date is not None:
                _rs_by_ticker = {
                    r["ticker"]: dict(r) for r in await conn.fetch(
                        _SLOT_RANK_RS_SQL, _rs_score_date,
                        [a["ticker"] for a in alerts])
                }
        _rank_by_rs = rank_board_by_rs(alerts, _rs_by_ticker)
        # Sorted COPY first, assign second — an exception lands BEFORE the list
        # mutates, so the fail direction (legacy order) is airtight.
        _rs_order = sorted(alerts, key=lambda a: _rank_by_rs[a["ticker"]])
        if _slot_rank_live and _rs_score_date is not None:
            _no_rs = [
                a["ticker"] for a in alerts
                if (_rs_by_ticker.get(a["ticker"]) or {}).get("rs_composite") is None
            ]
            if _no_rs:
                # Deliberate placement, mirrored from slot_rank_key: no RS row =
                # universe drift — ranked AFTER every RS-scored name (no evidence
                # of strength buys no priority), NEVER dropped from the board.
                logger.warning(
                    f"slot-rank [{trigger}]: no prior-day RS row for {_no_rs} "
                    f"(universe drift) — ranked after all RS-scored names, never dropped"
                )
            alerts = _rs_order
            _slot_rank_acting = True
        elif _slot_rank_live:
            logger.warning(
                f"slot-rank [{trigger}]: no complete RS score date before {today} "
                f"— legacy (alphabetical) order acts"
            )
    except Exception as _sre:  # loud-ok: fail direction = legacy order ACTS; durable audit row below
        logger.exception(f"slot-rank [{trigger}]: ranking failed — legacy (alphabetical) order acts: {_sre}")
        try:
            await log_audit_event(
                "slot_rank_fallback",
                f"[{trigger}] {type(_sre).__name__}: {str(_sre)[:200]}",
            )
        except Exception:  # loud-ok: log_audit_event never raises; belt+braces
            pass

    # The watch (the other half of the ruling) — one row per (invocation, ticker)
    # into mi_ep_slot_rank_shadow recording what EACH candidate ranking would have
    # picked. Runs on BOTH toggle sides (a revert must not kill the watch — the
    # watch is the revert's evidence). Fire-and-forget: never raises, SILENT.
    try:
        await snapshot_slot_rank_board(
            pool, alerts, _rs_by_ticker, _rs_score_date,
            acting_key=("rs" if _slot_rank_acting else "legacy_alpha"),
            trigger=trigger, alert_date=today,
        )
    except Exception as _sse:  # loud-ok: telemetry only — never blocks entries
        logger.warning(f"slot-rank shadow snapshot failed — {_sse}")

    # #444: this whole function is MAGNA53-only (signal_type="magna53" below) —
    # every alert in this batch shares ONE account_mode, so resolve it once for
    # the two digest surfaces (crash + skip-digest) instead of falling back to
    # the legacy global per message. Fail-open, never raises (mirrors the
    # ep_detector downgrade-ping precedent) — a resolve miss degrades to the
    # "mode unknown" label (strategy_mode_prefix(None) - main chat, #699; it used to be the
    # legacy-global PAPER guess, which now would also pick the paper chat), never blocks entry.
    _magna53_mode = await resolve_strategy_mode_nonfatal("magna53")

    logger.info(f"ORB monitor [{trigger}]: {len(alerts)} HIGH EP alerts: {[a['ticker'] for a in alerts]}")
    try:
        await log_audit_event("orb_triggered", f"[{trigger}] {len(alerts)} alerts: {[a['ticker'] for a in alerts]}")
    except Exception:  # loud-ok: log_audit_event() never raises — self-catches + logs internally (db.py); logger.info already fired immediately above
        pass

    async with pool.acquire() as conn:
        regime_record = await conn.fetchrow(
            "SELECT * FROM mi_market_regime WHERE regime_date <= $1 ORDER BY regime_date DESC LIMIT 1",
            today,
        )
    regime_record = dict(regime_record) if regime_record else None

    # Per-alert concurrency. Bar-fetch retry can block up to ~1 min on a
    # single ticker (entry_pipeline BAR_RETRY_MAX x BAR_RETRY_DELAY_SEC); serial
    # would stack past the 5-min cron interval on
    # any morning where multiple alerts miss the first bar. Semaphore
    # caps Alpaca-bound work to keep us under per-account rate limits.
    sem = asyncio.Semaphore(5)

    async def _process_alert(alert: dict) -> dict | None:
        ticker = alert["ticker"]
        async with sem:
            async with pool.acquire() as conn:
                # #624 (operator-approved 2026-10-10, review correction 3): "already traded
                # today" is asked of MAGNA53's OWN account only (dual-account invariant 3) — a
                # small-cap PAPER-lane trade on the same ticker/day must never make live MAGNA53
                # skip it. Fail direction: when the mode resolve above failed (None), today's
                # UNFILTERED check runs — never `account_mode = NULL`, which matches nothing and
                # would let a name live already holds be processed again.
                if _magna53_mode is not None:
                    exists = await conn.fetchval(
                        "SELECT EXISTS(SELECT 1 FROM mi_live_trades WHERE ticker = $1 "
                        "AND alert_date = $2 AND account_mode = $3)",
                        ticker, today, _magna53_mode,
                    )
                else:
                    exists = await conn.fetchval(
                        "SELECT EXISTS(SELECT 1 FROM mi_live_trades WHERE ticker = $1 AND alert_date = $2)",
                        ticker, today,
                    )
            if exists:
                logger.debug(f"Live trade already exists for {ticker} on {today}")
                return None

            passed, skip_reason = await check_filters(ticker, today)
            if not passed:
                # Attribute the filtered trade to the OWNING strategy's account
                # (operator 7/8, same fix as the scheduler out-of-orb path + the
                # entry_pipeline._skip path — this third writer was missed). Without
                # it the insert falls back to current_account_mode(), which reads
                # the legacy ALPACA_PAPER env (= 'paper' on prod), so a live-MAGNA53
                # filter:* skip would land in the dormant PAPER book, invisible to
                # every account_mode='live' operator surface (#447). Latent, never
                # fired (zero filter:* rows in prod history as of 2026-08-11) —
                # found by the account-mode literal sweep. _magna53_mode is the
                # #444 fail-open resolve above; None degrades to today's behavior.
                await _insert_skipped_trade(
                    ticker, today, alert, regime_record, skip_reason,
                    signal_type="magna53", account_mode=_magna53_mode,
                )
                logger.info(f"ORB filter [{trigger}]: {ticker} skipped — {skip_reason}")
                try:
                    await log_audit_event("orb_filtered", f"{ticker} [{trigger}] — {skip_reason}")
                except Exception:  # loud-ok: log_audit_event() never raises — self-catches + logs internally (db.py); logger.info already fired above, and the skip itself is already durable via _insert_skipped_trade() (uncaught) a few lines earlier
                    pass
                # Per-ticker Telegram suppressed — grouped digest fires post-gather.
                return {"ticker": ticker, "action": "filtered", "reason": skip_reason}

            atr_14, _atr_pct = await compute_atr_14(ticker, today)

            async def _magna_spec_builder(
                alert_ctx: dict,
                orb_bar: dict,
                regime: dict | None,
                account_mode: str,
                _atr=atr_14,
                _today=today,
            ) -> tuple[dict | None, str | None]:
                # #456: thread the SAME `today` this function already resolved
                # (used above for the regime fetch + alerts query + the
                # submit_trade_entry(today=...) call below) into the regime-
                # sizing staleness gate — not a second, independent et_today()
                # clock read inside order_manager.py.
                return await prepare_orb_order(
                    alert_ctx, orb_bar, _atr or 0, regime,
                    account_mode=account_mode, today=_today,
                )

            return await submit_trade_entry(
                alert_context=alert,
                spec_builder=_magna_spec_builder,
                regime_record=regime_record,
                strategy_label="ORB",
                signal_type="magna53",
                today=today,
                atr_14=atr_14,
                success_title="EP order placed",
                # MAGNA53 HIGH: Sonnet+Perplexity validation + ATR stop
                # width + 10:00 ET cleanup already cover dead-cat fills.
                # Midpoint check was over-strict; drop it.
                fade_midpoint_ratio=None,
                # #490: MAGNA53 opts IN to the submission-time gap re-check at its OWN 10% floor.
                # 9M Day 2 (line ~1248) deliberately does NOT — its bar is 3%, not 10%.
                rt_gap_floor_pct=_MAGNA53_MIN_GAP_PCT,
                aggregate_skips=True,
            )

    raw = await asyncio.gather(
        *(_process_alert(a) for a in alerts), return_exceptions=True,
    )
    results: list[dict] = []
    for alert, r in zip(alerts, raw):
        if r is None:
            continue
        if isinstance(r, BaseException):
            tkr = alert["ticker"]
            logger.exception(
                f"ORB monitor [{trigger}] {tkr}: per-alert task raised — {r}"
            )
            # Always write the crash to the audit log first — this is the
            # durable record. If Telegram is also down we'd otherwise lose all
            # trace of the failure.
            try:
                await log_audit_event(
                    "orb_pipeline_crash",
                    f"{tkr} [{trigger}] — {type(r).__name__}: {r}",
                )
            except Exception:
                logger.exception(f"ORB crash audit_log write also failed for {tkr}")
            try:
                await send_telegram_message(
                    f"{strategy_mode_prefix(_magna53_mode)}🚨 *{tkr}* ORB pipeline crashed — {type(r).__name__}: {r}"
                )
            except Exception:
                logger.exception(
                    f"ORB crash Telegram alert ALSO failed for {tkr} — "
                    f"check audit log event 'orb_pipeline_crash'"
                )
            results.append({"ticker": tkr, "action": "crashed", "reason": str(r)})
            continue
        results.append(r)

    entered = sum(1 for r in results if r.get("action") in (ACTION_AUTO_ENTERED, ACTION_PROPOSED))
    skipped_results = [r for r in results if r.get("action") in ("filtered", ACTION_SKIPPED, ACTION_BLOCKED)]
    logger.info(f"ORB monitor: {entered} entered, {len(skipped_results)} skipped out of {len(alerts)} alerts")

    # Grouped skip digest — one Telegram per cron-run instead of per-ticker.
    # #475 (2026-07-15): WINDOW_DUPLICATE skips are excluded from the digest —
    # they are dedup noise from the dual bar_stream/cron ORB trigger (the same
    # alert legitimately arrives twice; one path wins, the other reports
    # "duplicate"). All GENUINE skips (filter:/setup:/block:/infra:/other
    # window:) still surface; if only duplicates remain, no Telegram is sent.
    # Duplicates stay observable: results list, log line above, orb_duplicate audit.
    digest_results = [
        r for r in skipped_results
        if not _is_window_duplicate_reason(r.get("reason"))
    ]
    # #706: a (ticker, reason class) already announced today is not announced again. The digest is
    # message-only and runs AFTER every order was submitted, so nothing in it may stop `results`
    # reaching the caller.
    try:
        await _send_skip_digest(digest_results, today, strategy_mode_prefix(_magna53_mode))
    except Exception as e:
        logger.error(f"ORB skip digest failed (the orders above are unaffected) — {e}", exc_info=True)

    return results


# ── Day 2+ Position Management ──────────────────────────────────────────────


async def _load_exit_state(
    trade: dict, today: date,
) -> tuple[dict | None, list | None, str | None]:
    """Shared per-trade state-load preamble for `run_partial_exits` (3:45 PM)
    and `update_open_positions_live` (4:45 PM) — #363.

    Before this extraction the two jobs carried a BYTE-FOR-BYTE identical
    state-load preamble: the running_closes/exits JSON coerce, the
    `hard_stop = trade.get('hard_stop') or stop_price` fallback, the
    `remaining_shares<=0 or today<=alert_date` skip guard, the
    `get_index_history` daily-bar fetch + no-data branch, and the 8-key
    `state` dict fed into `apply_daily_exit_step`. RISK this closes: editing
    the preamble in one job and not the other silently drifts them — one
    feeds the PARTIAL, the other the TRAIL (both money-adjacent).

    Deliberately does NOT call `apply_daily_exit_step` — the decision call
    (+ each job's own `skip_*` kwargs) stays PER-JOB, untouched by this
    extraction. Also deliberately does NOT log or touch a `results` list —
    each caller keeps its own log wording (`"No daily bar..."` vs
    `"run_partial_exits: no daily bar..."`) and its own `results.append`
    shape, so those stay caller-owned.

    Returns `(state, daily_bars, skip_reason)`:
      - success: `(state, daily_bars, None)`.
      - `skip_reason="silent"`: the pre-existing `remaining_shares<=0 or
        today<=alert_date` guard fired — caller does a bare `continue`
        (nothing appended to `results`), exactly as before extraction.
      - `skip_reason="no_data"`: no daily bar yet for `today` — caller logs
        (its own wording) and appends `{"ticker": ..., "action": "no_data"}`
        to `results`, exactly as before extraction.
    """
    alert_date = trade["alert_date"]
    running_closes_in = trade.get("running_closes", [])
    if isinstance(running_closes_in, str):
        running_closes_in = json.loads(running_closes_in or "[]")
    exits_in = trade["exits"] if isinstance(trade["exits"], list) else json.loads(trade["exits"] or "[]")
    hard_stop = trade.get("hard_stop") or trade["stop_price"]

    if trade["remaining_shares"] <= 0 or today <= alert_date:
        return None, None, "silent"

    today_str = today.strftime("%Y-%m-%d")
    daily_bars = await get_index_history(trade["ticker"], today_str, today_str)
    if not daily_bars:
        return None, None, "no_data"

    # THE STOCK'S OWN CLOSES BEFORE ENTRY (#548, 2026-08-08 — operator: *"10d MA exists
    # regardless of how long we traded it"*). The trail is the STOCK's 10/20-day moving
    # average (EP_TRADING_RULES §B4); without this it averaged only the closes observed
    # while we held, so it could not exist until ~10 trading days in and was structurally
    # dead on a book whose longest hold is 2 days.
    #
    # 40 calendar days back covers the 20 trading closes SMA20 needs with room for holidays.
    # prior_closes = the closes BEFORE alert_date (the line and ADR20 read only these; the line has
    # never included the entry day's own close — a separate change, his call). The entry-day bar
    # is fetched in the same window but split off as `entry_day_close`, read only by the trail
    # ARMING (2026-10-28, CLS).
    #
    # FAIL-SOFT ON PURPOSE: any failure leaves prior_closes empty, which is byte-identical
    # to the pre-#548 behavior. A history hiccup must never abort a position-management
    # pass — that pass also carries the hard stop.
    prior_closes: list[float] = []
    prior_bars: list[dict] = []
    entry_day_close: float | None = None
    try:
        _hist = await get_index_history(
            trade["ticker"],
            (alert_date - timedelta(days=40)).strftime("%Y-%m-%d"),
            alert_date.strftime("%Y-%m-%d"),
        )
        for b in _hist or []:
            ts = b.get("t")
            if ts is not None and datetime.fromtimestamp(ts / 1000, tz=_ET_ZONE).date() >= alert_date:
                if b.get("c") is not None:
                    entry_day_close = float(b["c"])
            else:
                prior_bars.append(b)
        prior_closes = [float(b["c"]) for b in prior_bars if b.get("c") is not None]
    except Exception as e:  # loud-ok: display/indicator input, never the stop itself
        logger.warning(
            f"{trade['ticker']}: prior-close fetch for the MA trail failed ({e}) — trail "
            "falls back to held-period closes only (pre-#548 behavior)")

    state = {
        "alert_date": alert_date,
        "remaining_shares": trade["remaining_shares"],
        "entry_price": trade["entry_price"],
        "hard_stop": hard_stop,
        "partial_taken": trade.get("partial_taken", False),
        "breakeven_active": trade.get("breakeven_active", False),
        "exits": exits_in,
        "running_closes": running_closes_in,
        # Not part of the persisted trade state — recomputed each pass from price history,
        # so there is nothing to migrate and nothing to go stale.
        "prior_closes": prior_closes,
        "entry_day_close": entry_day_close,     # arming input only; never part of the line
        # #687 B: the depth rule's ADR20 (the 20 sessions BEFORE entry, from the SAME bars as
        # prior_closes). None below 10 usable sessions — including when the fetch failed this
        # pass — and the depth stop then rests at the hard/breakeven floor, as the analysis
        # walker rests a trade it cannot host. Read by the depth branch only.
        "adr20_pct": adr20_pct_from_bars(prior_bars),
    }
    return state, daily_bars, None


async def update_open_positions_live(today: date | None = None) -> list[dict]:
    """
    Update open live positions: SMA10/20 trail + stop updates (EOD, on the close).
    Same logic as backtester/tracker.py update_open_positions(), but executes
    real orders via Alpaca.

    #361 (2026-06-23): the Day 3-5 PARTIAL-PROFIT decision has been SPLIT OUT
    of this EOD (4:45 PM) job into `run_partial_exits()`, which runs DURING
    market hours (3:45 PM). Root cause: this job fires after the 16:00 ET close,
    so a partial's stop-replace parks in `pending_replace` until the next
    session open — both old+new orders reserve the shares, qty_available=0, and
    the partial aborts. Running the partial mid-session (stop-replaces settle in
    ~0.2s, the sell fills) fixes it. This job therefore passes
    `skip_partial_decision=True` to `apply_daily_exit_step` so the partial branch
    is bypassed here — the partial fires EXACTLY ONCE, at 3:45, NOT also at 4:45.
    The SMA-trail / stop-update / running_closes advance / daily summary stay
    here at 4:45 (EOD, on the settled close). When a 3:45 partial has already
    filled, `finalize_partial_exit` has persisted partial_taken / breakeven_active /
    reduced remaining_shares to the DB, so this job (which reads fresh from
    mi_live_trades) computes the effective stop floored at entry correctly.
    """
    if today is None:
        today = et_today()

    pool = await get_pool()
    async with pool.acquire() as conn:
        open_trades = await conn.fetch("""
            SELECT * FROM mi_live_trades
            WHERE status = 'filled' AND remaining_shares > 0
            ORDER BY alert_date ASC
        """)

    if not open_trades:
        logger.info("No open live positions to update")
        return []

    logger.info(f"Updating {len(open_trades)} open live positions: {[dict(t)['ticker'] for t in open_trades]}")
    results = []

    for trade in open_trades:
        trade = dict(trade)
        ticker = trade["ticker"]
        # Breakout v1 PAPER (2026-10-30): a row stamped 'breakout_pp' runs ITS exit (the `pp` arm,
        # broker/breakout_pp_rules.py) — paper only, and its breakout-day facts are captured here on
        # the breakout day itself (before the guard below, which skips the entry day), or on the first
        # later run that finds them missing. Every other row: nothing here runs.
        is_breakout_pp = trade.get("exit_rule") == BREAKOUT_PP_EXIT_RULE
        if is_breakout_pp:
            if not await _bpp.paper_wall(trade, "16:45"):
                results.append({"ticker": ticker, "action": "breakout_pp_refused"})
                continue
            # Advisor item 3 (pre-merge 2026-10-31): a fill the minute job could not check (a 15:55 fill has no
            # tick after it) gets his stop-at-the-fill check HERE, the next pass that runs — BEFORE the day-0 facts,
            # which read `hard_stop` (a lowered stop changes the +2R target they model). A row already checked is
            # one marker read; a sale (too wide) ends this row's pass; a lowered stop re-reads the row.
            if trade.get("signal_type") == _BREAKOUT_V1_SIGNAL_TYPE:
                from agents.market_intelligence.broker.breakout_v1_entry import check_stop_at_fill_after_close
                _chk = await check_stop_at_fill_after_close(
                    trade, now_et=datetime.combine(today, time(16, 45), tzinfo=_ET_ZONE))
                if _chk == "fill_sold_too_wide":
                    results.append({"ticker": ticker, "action": "breakout_v1_fill_stop_sold"})
                    continue
                if _chk == "fill_stop_lowered":
                    async with pool.acquire() as conn:
                        _fresh = await conn.fetchrow(
                            "SELECT stop_price, hard_stop, stop_order_id, remaining_shares, status, "
                            "risk_dollars_actual FROM mi_live_trades WHERE id = $1", trade["id"])
                    if _fresh:
                        trade.update(dict(_fresh))
            if _bpp.coerce_facts(trade.get("breakout_day0_pp")) is None and today >= trade["alert_date"]:
                _facts = await _bpp.ensure_day0_facts(trade)
                if _facts is not None:
                    trade["breakout_day0_pp"] = _facts
            # the backstop for "after a third SOLD the stop rests at the fill" on the breakout day itself (the
            # guard below skips that day; later days run it in the branch further down). The move itself is
            # `finalize_partial_exit`'s at the fill; this lifts a stop it could not (raise-only).
            if (today == trade["alert_date"] and trade.get("partial_taken")
                    and float(trade.get("remaining_shares") or 0) > 0 and trade.get("entry_price")
                    and float(trade.get("stop_price") or 0) < round(float(trade["entry_price"]), 2) - 0.005):
                await update_stop(trade["id"], round(float(trade["entry_price"]), 2), stop_source="breakeven")
        state, daily_bars, skip = await _load_exit_state(trade, today)
        if skip == "silent":
            continue
        if skip == "no_data":
            logger.debug(f"No daily bar for {ticker} on {today}")
            results.append({"ticker": ticker, "action": "no_data"})
            continue

        # #361: partials moved to run_partial_exits() (3:45 PM, market-hours).
        # This 4:45 EOD job bypasses the partial branch so it never double-fires
        # the partial — it owns ONLY the SMA-trail + stop-update + summary here.
        step = apply_daily_exit_step(state, daily_bars[0], today,
                                          # #548: the trail is the STOCK's MA, not our hold-period mean
                                          prior_closes=state.get("prior_closes"),
                                          trail_arm_on_close_above=True,
                                          entry_day_close=state.get("entry_day_close"),
                                     integer_partial_shares=True,
                                     skip_partial_decision=True)

        logger.info(
            f"Processing {ticker}: day={step.hold_days} close=${step.bar_close:.2f} "
            f"low=${step.bar_low:.2f} stop=${state['hard_stop']:.2f} "
            f"shares={trade['remaining_shares']:.0f} partial={state['partial_taken']}"
        )

        # 1. Hard-stop verification: re-call without hard_stop if Alpaca says
        # position is still open (stop didn't actually trigger yet).
        #
        # ⚠ account_mode is LOAD-BEARING (#444, fixed 2026-07-27) — same defect
        # class as morning_stop_refresh's get_order, but with a worse failure
        # mode. Without it this read defaults to current_account_mode() =
        # "paper" inside apollo-execution, so a LIVE position is looked up in the
        # PAPER book and comes back None → `not pos` → the branch below feeds
        # finalize_stop_fill a SYNTHETIC close, marking a still-open real
        # position as closed and dropping it out of stop management entirely.
        # That is state corruption, not just churn. It had not fired yet (no
        # `inferred_close` rows exist in prod) because the SMA-trail stopped_out
        # branch had not been reached for a live position — loaded, not
        # triggered. Fixed before it could.
        if step.action == "stopped_out":
            pos = await alpaca.get_position(
                ticker, account_mode=trade["account_mode"],
            )
            if not pos or pos["qty"] <= 0:
                # T1.3 refactor 2026-05-18: delegate close commit to
                # finalize_stop_fill (the canonical authorized writer for
                # close-path columns: exits, status, remaining_shares,
                # total_pnl, closed_at, stop_order_id). This path is the
                # FALLBACK when WS missed the stop fill — synthetic
                # deterministic order_id prevents collision with real
                # Alpaca IDs + makes the idempotent check work if
                # update_open_positions_live runs twice.
                #
                # Per docs/architecture/trade-state-ownership.md:
                # live_tracker is no longer a writer to those columns;
                # hold_days + running_closes are live_tracker-domain
                # (state machine outputs) and get their own UPDATE.
                synthetic_order_id = f"inferred_close_{trade['id']}_{today.isoformat()}"
                await finalize_stop_fill(
                    trade_id=trade["id"],
                    filled_qty=int(trade["remaining_shares"]),
                    filled_price=float(step.close_price),
                    order_id=synthetic_order_id,
                )
                # Live_tracker-domain follow-up: hold_days + running_closes
                async with pool.acquire() as conn:
                    await conn.execute("""
                        UPDATE mi_live_trades SET
                            hold_days = $2,
                            running_closes = $3::jsonb
                        WHERE id = $1
                    """, trade["id"], step.hold_days,
                        step.new_running_closes)
                # finalize_stop_fill already sends the close Telegram +
                # logs stop_exit_committed audit event. No duplicate ping.
                results.append({"ticker": ticker, "action": "stopped_out", "pnl": step.new_total_pnl})
                continue
            # Alpaca still holds — re-run skipping the close branch.
            # hard_stop stays in state so effective_stop still floors at it.
            # #361: partial branch is owned by run_partial_exits (3:45) — keep
            # skip_partial_decision=True here so this EOD job never partials.
            step = apply_daily_exit_step(state, daily_bars[0], today,
                                              # #548: the trail is the STOCK's MA, not our hold-period mean
                                              prior_closes=state.get("prior_closes"),
                                              trail_arm_on_close_above=True,
                                              entry_day_close=state.get("entry_day_close"),
                                         integer_partial_shares=True,
                                         skip_hard_stop_close=True,
                                         skip_partial_decision=True)

        # Breakout v1 PAPER (2026-10-30): the `pp` arm's evening — ITS OWN trail and stop, never the
        # ladder below. The stop-hit reconcile above is shared (it only books a stop the broker
        # already filled). Here: the close test against the stock's 20-day simple average (live from
        # session 3, or from a +2R third that FILLED) -> MARK the trade (`depth_sell_pending_on`, the same mark the
        # depth rule uses) and the 19:02 ET job sends the PAPER DAY market sale that fills at the next
        # open (#687 option (c)'s vehicle); NO trail stop is ever rested (the walk's stop is the day's
        # low at the fill, then the fill after a third) — the backstop below only lifts a stop still
        # under the fill once a third has sold. Decisions: broker/breakout_pp_rules.trail_decision.
        if is_breakout_pp:
            _sessions = await _bpp.load_sessions(trade, today, daily_bars[0])
            _entry = float(trade["entry_price"])
            if _sessions is not None:
                _cb, _fwd = _sessions
                # "a third sold" = the row's partial_taken (what actually FILLED — his ruling 2026-10-29),
                # never a high at +2R: a touch whose resting limit did not fill starts no trail
                _td = _bpp_rules.trail_decision(
                    closes_before=_cb, fwd=_fwd, partial_taken=bool(trade.get("partial_taken")))
            else:
                _td = {"j": None, "trail_live": False, "sma20": None, "close": step.bar_close, "sell": False}
            if _td["sell"]:
                async with pool.acquire() as conn:
                    await conn.execute("""
                        UPDATE mi_live_trades SET
                            hold_days = $2, running_closes = $3::jsonb,
                            depth_sell_pending_on = $4
                        WHERE id = $1
                    """, trade["id"], step.hold_days,
                        step.new_running_closes, today)
                await log_audit_event(
                    "breakout_pp_close_below_sma20",
                    f"{ticker}: session {_td['j']} closed ${_td['close']:.2f} under the 20-day "
                    f"${_td['sma20']:.2f} — selling the rest at the next open (paper day market order)",
                    json.dumps({"trade_id": trade["id"], "ticker": ticker,
                                "account_mode": trade.get("account_mode"), "session": _td["j"],
                                "close": _td["close"], "sma20": _td["sma20"],
                                "decided_on": today.isoformat()}),
                )
                results.append({"ticker": ticker, "action": "breakout_pp_sell_pending",
                                "session": _td["j"]})
                continue
            # after any third SOLD the stop rests at the fill (cost) — finalize_partial_exit moves it when
            # the third fills; this lifts one still under the fill (raise-only: update_stop refuses lower)
            current_stop = float(trade["stop_price"] or 0)
            if (trade.get("partial_taken") and step.new_remaining > 0
                    and _bpp_rules.stop_after_third(current_stop, _entry) > current_stop + 0.01):
                await update_stop(trade["id"], round(_entry, 2), stop_source="breakeven")
            async with pool.acquire() as conn:
                await conn.execute("""
                    UPDATE mi_live_trades SET
                        hold_days = $2,
                        breakeven_active = (breakeven_active OR $3),
                        running_closes = $4::jsonb
                    WHERE id = $1
                """, trade["id"], step.hold_days,
                    step.new_breakeven_active,
                    step.new_running_closes)
            results.append({"ticker": ticker, "action": "breakout_pp_held", "session": _td["j"],
                            "trail_live": _td["trail_live"], "sma20": _td["sma20"]})
            continue

        # 2. Partial profit branch — MOVED to run_partial_exits() (3:45 PM ET,
        # #361). With skip_partial_decision=True above, step.partial_fired is
        # always False here, so this job runs ONLY the SMA-trail + stop ladder.

        # #687 B: the rule this trade was ENTERED under, stamped on its row at entry and kept
        # for life. NULL = today's rule. The toggle is never read here — flipping it cannot
        # change an open trade's rule.
        is_depth = trade.get("exit_rule") == DEPTH_EXIT_RULE

        # 3. SMA trail close
        if step.action == "sma_stopped" and is_depth:
            # The depth rule decides on this TRUE close exactly as today's rule does, but sells
            # in the NEXT MORNING'S OPENING AUCTION (ruled 2026-09-29): mark it, leave the depth
            # stop on, and let the 19:01 ET job send the market-on-open order (Alpaca rejects
            # OPG orders before 19:00). Nothing is cancelled or sold here.
            # #687 (c): the sale's VEHICLE differs by book (live: opening auction; paper: a DAY
            # market order that fills at the open) — the words must say which.
            _words = depth_sale_words(trade.get("account_mode"))
            async with pool.acquire() as conn:
                await conn.execute("""
                    UPDATE mi_live_trades SET
                        hold_days = $2, running_closes = $3::jsonb,
                        depth_sell_pending_on = $4
                    WHERE id = $1
                """, trade["id"], step.hold_days,
                    step.new_running_closes, today)
            await log_audit_event(
                "depth_close_below_line",
                f"{ticker}: closed ${step.bar_close:.2f} below the trailing line "
                f"${step.effective_stop:.2f} — {_words['selling']}",
                json.dumps({"trade_id": trade["id"], "ticker": ticker,
                            "account_mode": trade.get("account_mode"),
                            "close": step.bar_close, "line": step.effective_stop,
                            "resting_stop": trade.get("stop_price"),
                            "decided_on": today.isoformat()}),
            )
            await send_telegram_message(
                f"{mode_prefix(trade.get('account_mode'))}📉 *{ticker} closed below "
                f"its trailing line* (${step.bar_close:.2f} < ${step.effective_stop:.2f}).\n"
                f"Selling at the next open: {_words['order_goes_in']}. "
                f"The stop stays on until then."
            )
            results.append({"ticker": ticker, "action": "depth_sell_pending",
                            "hold_days": step.hold_days})
            continue

        if step.action == "sma_stopped":
            await execute_full_exit(trade["id"], "sma_trail_stop")
            async with pool.acquire() as conn:
                await conn.execute("""
                    UPDATE mi_live_trades SET
                        hold_days = $2, running_closes = $3::jsonb
                    WHERE id = $1
                """, trade["id"], step.hold_days,
                    step.new_running_closes)
            results.append({"ticker": ticker, "action": "sma_stopped", "hold_days": step.hold_days})
            continue

        # 4. Still open — update Alpaca stop if effective_stop rose
        current_stop = trade["stop_price"] or 0
        if is_depth:
            # #687 B: the depth rule's RESTING stop — one ADR20 under today's line
            # (`step.effective_stop` = max(hard, SMA10/20 incl. today's close, entry once
            # breakeven is armed), the line today's rule rests ON). Same raise-only path:
            # `update_stop` refuses anything not above the live broker stop, which is the
            # ratchet the replay applies. No ADR20 → the hard/breakeven floor (never a move).
            depth_stop = depth_stop_price(
                line=step.effective_stop,
                hard_stop=float(state["hard_stop"]),
                entry_price=trade.get("entry_price"),
                breakeven_active=bool(step.new_breakeven_active),
                adr20_pct=state.get("adr20_pct"),
            )
            if depth_stop > current_stop + 0.01 and step.new_remaining > 0:
                await update_stop(trade["id"], depth_stop, stop_source="depth_trail")
        elif step.effective_stop > current_stop + 0.01 and step.new_remaining > 0:
            # #560: tell update_stop WHICH ladder input raised the stop (trail /
            # breakeven / hard_stop / giveback_floor) so the operator-facing
            # "Stop confirmed" Telegram (retry-recovered path) can say why —
            # presentation only, does not touch the price being set.
            await update_stop(trade["id"], round(step.effective_stop, 2),
                               stop_source=step.stop_source)

        # #361 (2026-06-23): the partial branch moved to run_partial_exits()
        # (3:45 PM), and this job now passes skip_partial_decision=True, so
        # step.partial_fired is always False here — the former `if
        # step.partial_fired` UPDATE (which deliberately omitted
        # breakeven_active to avoid the BW 5/14 optimistic-write incident) is
        # dead code and has been removed. This job persists ONLY the
        # state-machine / live_tracker-domain columns below.
        #
        # T1.4 refactor 2026-05-17: dropped stop_price + total_pnl +
        # partial_taken + remaining_shares from this UPDATE.
        #
        # - stop_price: update_stop() above owns trail writes. Writing here is
        #   redundant when update_stop succeeded and FALSELY OPTIMISTIC when it
        #   failed (KLAR-class bug).
        # - total_pnl / partial_taken / remaining_shares: step.new_X == state[X]
        #   (no change, partial decision skipped). The "no-op idempotent write"
        #   is actually a LOST UPDATE hazard if a WS fill arrived concurrently
        #   between state-load and this UPDATE — the stale read would clobber the
        #   WS write. Authorized writers: finalize_partial_exit,
        #   finalize_full_exit, finalize_stop_fill, _sync_positions_for_mode.
        #
        # Keeps: hold_days, breakeven_active (monotonic — see below),
        # running_closes (live_tracker domain; appended exactly once here).
        #
        # F22 (7/2 review — #361 regression): breakeven_active is written as
        # `old OR step`, MONOTONIC, never TRUE→FALSE. step.new_breakeven_active
        # is a passthrough of this job's OPENING read (partial branch skipped),
        # and the read→UPDATE window spans the whole job (network calls per
        # ticker). If finalize_partial_exit (the only TRUE-writer, on the WS
        # fill) lands inside that window — a delayed 3:45-partial fill, or an
        # operator /partialnow — a plain `= $3` clobbers TRUE back to FALSE
        # with NO self-heal (partial_taken stays TRUE so the partial never
        # re-fires; the stop then floors below entry for the trade's life).
        # OR-ing preserves it; safe because no writer legitimately resets the
        # flag on an open row (order_manager:1858 is TRUE-only).
        async with pool.acquire() as conn:
            await conn.execute("""
                UPDATE mi_live_trades SET
                    hold_days = $2,
                    breakeven_active = (breakeven_active OR $3),
                    running_closes = $4::jsonb
                WHERE id = $1
            """, trade["id"], step.hold_days,
                step.new_breakeven_active,
                step.new_running_closes)

        logger.info(
            f"{ticker}: effective_stop=${step.effective_stop:.2f} "
            f"(hard=${state['hard_stop'] or 0:.2f} sma={step.active_sma or 0:.2f} "
            f"be={'yes' if step.new_breakeven_active else 'no'})"
        )

        results.append({
            "ticker": ticker, "action": "updated",
            "effective_stop": step.effective_stop, "hold_days": step.hold_days,
        })

    return results


async def _breakout_pp_session3(trade: dict, today: date, state: dict, today_bar: dict) -> dict:
    """Breakout v1 PAPER (2026-10-30) — the `pp` arm's 15:45 ET step for ONE 'breakout_pp' row (see the
    branch in `run_partial_exits`). Acts on session 3 (reads the forming bar as the session's close) and,
    from session 4 on, RETRIES a session-3 third that was decided but never sold (`_breakout_pp_third_retry`,
    his ruling 2026-10-31). Paper only (`breakout_pp_exit.paper_wall`). Sells through the shared exits: the
    stall cut with `execute_full_exit(.., 'breakout_stall_cut')`, the session-3 third with
    `execute_partial_exit` (a third of the shares held, rounded down — `profit_take_shares`; for a breakout
    row that call never moves the stop — the stop moves to the fill when the third FILLS,
    `order_manager.finalize_partial_exit`). With the close above the fill and the +2R third still RESTING
    unfilled, the limit is cancelled first (`breakout_pp_exit.cancel_resting_third`, the cancel confirmed) and
    the third — the cancelled limit's own size — sold at the close; a fill in the race IS the third and
    nothing more is sold (his ruling 2026-10-29 late, "option a"). The DECISION to sell is recorded before
    anything is cancelled or sold (`breakout_pp_exit.SESSION_THIRD_DUE`), so a sale that does not happen is
    retried at the next close. A day-0 record that cannot be read leaves the cut UNAPPLIED (audited + paged
    in `ensure_day0_facts`) — the third is still decided."""
    ticker = trade["ticker"]
    if not await _bpp.paper_wall(trade, "15:45"):
        return {"ticker": ticker, "action": "breakout_pp_refused"}
    sessions = await _bpp.load_sessions(trade, today, today_bar)
    if sessions is None:
        return {"ticker": ticker, "action": "breakout_pp_no_history"}
    _closes_before, fwd = sessions
    if len(fwd) > _bpp_rules.LEG_SESSION:
        return await _breakout_pp_third_retry(trade, fwd, state)
    if len(fwd) != _bpp_rules.LEG_SESSION:
        return {"ticker": ticker, "action": "breakout_pp_not_session3", "session": len(fwd)}
    fill, stop0 = float(trade["entry_price"]), float(state["hard_stop"])
    facts = await _bpp.ensure_day0_facts(trade)
    # "a third sold" = what actually FILLED (his ruling 2026-10-29): the row's partial_taken; a +2R third still
    # RESTING at the broker is cancelled before the session-3 third is sold — never one beside it.
    # ... and the WIDER truth beside the flag (the advisor's final-review finding 2026-10-31): the third's OCO stop
    # leg filling is the third sold at its stop, booked by the stop-fill finalizer WITHOUT `partial_taken` — read
    # from the row's booked exits and the order book (`shares_already_sold`), never sold beside.
    partial_taken = bool(trade.get("partial_taken"))
    sold, sold_why = await _bpp.shares_already_sold(trade)
    third_done = partial_taken or sold
    resting, resting_oid = (False, None) if third_done else await _bpp.resting_third(trade["id"])
    if sold and not partial_taken:
        await log_audit_event(
            "breakout_pp_third_already_sold",
            f"{ticker} #{trade['id']}: session 3 — shares already left the position ({sold_why}); no session-3 "
            f"third and nothing retried (one third ever)",
            json.dumps({"trade_id": trade["id"], "ticker": ticker, "why": sold_why,
                        "remaining_shares": float(trade.get("remaining_shares") or 0)}),
        )
    if facts is None:
        decision = None
        if not third_done and float(fwd[-1]["c"]) > fill:
            decision = _bpp_rules.CANCEL_RESTING_THIRD if resting else "session_third"
        await log_audit_event(
            "breakout_pp_cut_not_applied",
            f"{ticker} #{trade['id']}: session 3 — no breakout-day record, the stall cut was NOT applied",
            json.dumps({"trade_id": trade["id"], "ticker": ticker, "decision": decision}),
        )
    else:
        decision = _bpp_rules.session3_decision(fill=fill, stop=stop0, day0=facts, fwd=fwd,
                                                partial_taken=partial_taken, third_resting=resting,
                                                shares_sold=sold)
    last = float(fwd[-1]["c"])
    if decision == "cut":
        r_now = (last - fill) / (fill - stop0) if fill > stop0 else None
        _r = f" · {r_now:+.2f}R" if r_now is not None else ""
        await log_audit_event(
            "breakout_pp_stall_cut",
            f"{ticker}: session 3, no high at +1R (${_bpp_rules.cut_level(fill, stop0):.2f}) — selling everything",
            json.dumps({"trade_id": trade["id"], "ticker": ticker, "last": last, "fill": fill, "stop": stop0,
                        "cut_level": _bpp_rules.cut_level(fill, stop0)}),
        )
        try:
            await send_telegram_message(
                f"{mode_prefix(trade.get('account_mode'))}✂️ *Stall cut: {ticker}*\n"
                f"day 3 · ${last:.2f}{_r} — never reached +1R. Selling all "
                f"{int(float(trade['remaining_shares']))} sh.")
        except Exception:  # loud-ok: the sale below must run regardless
            logger.warning(f"breakout pp stall-cut notify failed for {ticker}", exc_info=True)
        ok = await execute_full_exit(trade["id"], "breakout_stall_cut")
        return {"ticker": ticker, "action": "breakout_pp_cut_submitted" if ok else "breakout_pp_cut_failed"}
    if decision in (_bpp_rules.CANCEL_RESTING_THIRD, "session_third"):
        # HIS RULING 2026-10-31 ("Retry the sale at the next day's close"): the DECISION is recorded BEFORE any
        # cancel or sale, so a sale that does not happen today (an unconfirmed cancel, a failed or refused sale,
        # a limit left resting past the close) is retried by this step at the next close — from the DB, never
        # from memory (`_breakout_pp_third_retry`). A trade that reaches this line is the only kind ever retried.
        await log_audit_event(
            _bpp.SESSION_THIRD_DUE,
            f"{ticker} #{trade['id']}: session 3 at ${last:.2f}, above the fill ${fill:.2f} — a third is due at the "
            f"close ({decision}); a sale that does not happen today is retried at the next close",
            json.dumps({"trade_id": trade["id"], "ticker": ticker, "last": last, "fill": fill, "decision": decision,
                        "resting_order_id": resting_oid, "account_mode": trade.get("account_mode")}),
        )
        return await _breakout_pp_sell_third(trade, last=last, fill=fill, stop0=stop0,
                                             resting=(decision == _bpp_rules.CANCEL_RESTING_THIRD),
                                             resting_oid=resting_oid, session=_bpp_rules.LEG_SESSION, retry=False)
    return {"ticker": ticker, "action": "no_partial", "session": 3}


async def _breakout_pp_sell_third(trade: dict, *, last: float, fill: float, stop0: float, resting: bool,
                                  resting_oid: str | None, session: int, retry: bool,
                                  after_refusal: bool = False) -> dict:
    """The close sale of the third — ONE path for session 3 and for the retry sessions (his rulings 2026-10-29 late
    and 2026-10-31). A partial-exit order still resting (the +2R limit; on a retry, possibly a sale that never
    settled) is cancelled first — `breakout_pp_exit.cancel_resting_third`, confirm-or-replace — then exactly one
    of: a fill in the race IS the third (nothing more sold); a stop-leg fill is the third sold at its stop; dead ->
    the cancelled order's OWN size sold at market; unconfirmed, or a dead row that will not close -> nothing sold,
    cover converged from broker truth, paged. With nothing resting, a third of the shares held is sold at market.
    A plain sale the shared partial-exit REFUSED is re-read once (the 15:45 collision: the +2R poll placed its
    limit between this step's resting read and the sale's lock, so the pending-exit dedup refused the sale and the
    limit would have rested past the close): a partial-exit order now resting is cancelled and the third sold, this
    session; otherwise the sale is audited as not sold and paged — the next close retries it (the due record is
    already written). -> the step's result dict: `action` 'partial_submitted' | 'partial_failed' |
    'breakout_pp_third_filled_in_race' | 'breakout_pp_third_stopped_in_race' | 'breakout_pp_third_cancel_unconfirmed'
    | 'too_small_to_split'."""
    ticker = trade["ticker"]
    r_now = (last - fill) / (fill - stop0) if fill > stop0 else None
    _r = f" · {r_now:+.2f}R" if r_now is not None else ""
    day = f"day {session}" + (" (retry)" if retry else "")
    tag = {"trade_id": trade["id"], "ticker": ticker, "session": session, "retry": retry}
    third_from_cancel = False
    cx = None
    if resting:
        cx = await _bpp.cancel_resting_third(trade, resting_oid)
        _cx_detail = {**tag, "last": last, "fill": fill, "resting_order_id": resting_oid,
                      **{k: cx.get(k) for k in ("state", "qty", "filled_qty", "leg_id", "cancel_sent",
                                                "cancel_accepted", "marker_withdrawn", "row_update_error")}}
        if cx["state"] == "filled":
            # the +2R limit filled before the cancel took: THAT fill is the third (the stream books it) — no second
            await log_audit_event(
                "breakout_pp_third_filled_in_race",
                f"{ticker}: {day} — the resting partial-exit order filled while being cancelled "
                f"({cx.get('filled_qty') or 0:g} sh) — that fill is the third; nothing more sold",
                json.dumps(_cx_detail),
            )
            return {"ticker": ticker, "action": "breakout_pp_third_filled_in_race", "session": session}
        if cx["state"] == "stop_filled":
            # finding 2 (pre-merge 2026-10-31): the OCO's sibling STOP leg filled in the race — the third sold at its
            # stop; the parent reads cancelled with nothing filled. Nothing more is sold (the leg's fill is booked by
            # the stream's stop-fill handler through its own 'stop_loss' order row).
            await log_audit_event(
                "breakout_pp_third_stopped_in_race",
                f"{ticker}: {day} — the resting +2R third's own stop leg {str(cx.get('leg_id') or '?')[:8]} "
                f"filled while the limit was being cancelled — the third sold at its stop; nothing more sold",
                json.dumps(_cx_detail),
            )
            return {"ticker": ticker, "action": "breakout_pp_third_stopped_in_race", "session": session}
        if cx["state"] != "dead" or cx.get("row_update_error"):
            # findings 1 + 2 (pre-merge 2026-10-31): the step is NOT selling the third it marked for — never leave it
            # to the 5-minute coverage repair. The marker is withdrawn inside cancel_resting_third (a LATE settle is
            # then the stream's ordinary OCO-parent re-protect) and the cover is converged from broker truth NOW:
            # a no-op while the limit really rests (its open order row nets the third; nothing is placed on top of
            # its live stop leg — that would be two sells for one third), the cover when the cancel already settled
            # and the stream was told to leave it. A dead limit whose row could not be closed is closed again here
            # first, so the repair stops counting it as cover. His ruling 2026-10-31: the sale is retried at the
            # next close (the due record stands; the +2R limit is still never re-placed).
            cov = None
            if cx.get("cancel_sent"):
                cov = await _bpp.reprotect_after_unsold_third(
                    trade, dead_order_id=(resting_oid if cx.get("row_update_error") else None))
            _cx_detail["coverage"] = str(cov)[:300] if cov else None
            why = cx.get("row_update_error") or cx["state"]
            await log_audit_event(
                "breakout_pp_third_cancel_unconfirmed",
                f"{ticker}: {day} at ${last:.2f} — the resting partial-exit order "
                f"{str(resting_oid or '?')[:8]} could NOT be confirmed cancelled and closed ({why}) — no third sold; "
                f"cover converged from broker truth ({cov or 'already met / limit still resting'}); the sale is "
                f"retried at the next close",
                json.dumps(_cx_detail),
            )
            try:
                await send_telegram_message(
                    f"{mode_prefix(trade.get('account_mode'))}⚠️ *Breakout third: {ticker}*\n"
                    f"{day} · ${last:.2f}{_r} — the resting +2R limit could not be confirmed cancelled ({why}). "
                    f"No third was sold today; the sale is retried at the next close, and the +2R limit will not "
                    f"be re-placed. "
                    f"{cov or 'The shares are covered (the limit still rests, or its stop was put back).'} "
                    f"Check the order on Alpaca.")
            except Exception:  # loud-ok: audited above
                logger.warning(f"breakout pp cancel-unconfirmed notify failed for {ticker}", exc_info=True)
            return {"ticker": ticker, "action": "breakout_pp_third_cancel_unconfirmed", "session": session}
        await log_audit_event(
            "breakout_pp_third_cancelled_for_session_third",
            f"{ticker}: {day} at ${last:.2f} (fill ${fill:.2f}) — the unfilled partial-exit order "
            f"{str(resting_oid)[:8]} cancelled (confirmed); selling the third at the close",
            json.dumps(_cx_detail),
        )
        third_from_cancel = True
    # after a cancel: exactly the cancelled order's own size (one third ever); else a third of what is held
    shares = (int(float(cx["qty"])) if third_from_cancel
              else profit_take_shares(trade["remaining_shares"], trade.get("signal_type")))
    if shares < 1:
        if third_from_cancel:      # never leave the cancelled third's shares without a stop
            await _bpp.reprotect_after_unsold_third(trade)
        await log_audit_event(
            "breakout_pp_third_too_small",
            f"{ticker}: {day} third — {int(float(trade['remaining_shares']))} sh held, a third rounds to 0",
            json.dumps(tag),
        )
        return {"ticker": ticker, "action": "too_small_to_split"}
    await log_audit_event(
        _bpp.SESSION_THIRD_EVENT,
        f"{ticker}: {day} at ${last:.2f} (fill ${fill:.2f}) — selling {shares} sh",
        json.dumps({**tag, "last": last, "fill": fill, "shares": int(shares)}),
    )
    try:
        await send_telegram_message(
            f"{mode_prefix(trade.get('account_mode'))}💰 *Profit-take firing: {ticker}*\n"
            f"{day} · ${last:.2f}{_r}{', above the fill' if last > fill else ''}\n"
            + ("The day-3 sale did not happen — retrying at today's close. " if retry else "")
            + ("The resting +2R limit is cancelled. " if third_from_cancel else "")
            + f"Selling {shares} of {int(float(trade['remaining_shares']))} sh, "
            f"the stop moves to the fill (${fill:.2f}) once it sells.")
    except Exception:  # loud-ok: the partial below must run regardless
        logger.warning(f"breakout pp third notify failed for {ticker}", exc_info=True)
    sale_error = None
    try:
        ok = await execute_partial_exit(trade["id"], int(shares))
    except Exception as e:
        if not third_from_cancel:
            raise              # no cancel happened: the third's stop is intact; the caller audits it
        # the +2R limit is already cancelled (its OCO stop with it): a RAISE leaves the third as bare as a False
        logger.error(f"breakout pp: the {day} third sale raised for {ticker} #{trade['id']}: {e}", exc_info=True)
        ok, sale_error = False, f"{type(e).__name__}: {e}"[:300]
    if not ok and third_from_cancel:
        # the cancelled OCO took the third's own stop with it and the marker kept the stream from re-protecting:
        # cover the third's shares from broker truth now (idempotent; a no-op when already covered)
        cov = await _bpp.reprotect_after_unsold_third(trade)
        await log_audit_event(
            "breakout_pp_session_third_unsold_reprotected",
            f"{ticker}: {day} — the third after the cancel did not sell — re-protected from broker truth ({cov}); "
            f"the sale is retried at the next close",
            json.dumps({**tag, "shares": int(shares), "coverage": str(cov)[:300] if cov else None,
                        "sale_error": sale_error}),
        )
        try:
            await send_telegram_message(
                f"{mode_prefix(trade.get('account_mode'))}⚠️ *Breakout third NOT sold: {ticker}*\n"
                f"The resting order was cancelled but the {day} sale of {shares} sh failed. No third was sold "
                f"today; the sale is retried at the next close. {cov or 'Stop cover already met.'} "
                f"The +2R limit will not be re-placed.")
        except Exception:  # loud-ok: audited above
            logger.warning(f"breakout pp unsold-third notify failed for {ticker}", exc_info=True)
    elif not ok and not after_refusal:
        # Review low (pre-merge 2026-10-31, the 15:45 collision's REVERSE order): the +2R poll runs at 15:45:00 too.
        # When it placed its +2R OCO between this step's resting read (nothing resting) and the sale's lock, the
        # shared pending-exit dedup refused the sale — and the limit would rest past session 3 with no marker. The
        # refusal is not distinguishable by return value, so the book is RE-READ once: an order now resting is
        # cancelled (the marker, confirm-or-replace) and the third sold, this session. Nothing resting = the sale
        # failed for another reason: audited as not sold, paged; the next close retries it (the due record stands).
        resting2, oid2 = await _bpp.resting_third(trade["id"])
        if resting2:
            await log_audit_event(
                "breakout_pp_session_third_refused_limit_resting",
                f"{ticker}: {day} — the close sale was refused and a partial-exit order {str(oid2 or '?')[:8]} now "
                f"rests (the +2R poll placed its limit between this step's read and the sale) — cancelling it and "
                f"selling the third",
                json.dumps({**tag, "resting_order_id": oid2, "shares": int(shares)}),
            )
            return await _breakout_pp_sell_third(trade, last=last, fill=fill, stop0=stop0, resting=True,
                                                 resting_oid=oid2, session=session, retry=retry, after_refusal=True)
        await log_audit_event(
            "breakout_pp_session_third_unsold",
            f"{ticker}: {day} — the close sale of {shares} sh was refused or failed and nothing rests at the broker "
            f"— no third sold; the stop is unchanged; the sale is retried at the next close",
            json.dumps({**tag, "shares": int(shares)}),
        )
        try:
            await send_telegram_message(
                f"{mode_prefix(trade.get('account_mode'))}⚠️ *Breakout third NOT sold: {ticker}*\n"
                f"The {day} sale of {shares} sh was refused or failed (nothing resting at the broker). No third was "
                f"sold today; the stop is unchanged and the sale is retried at the next close. "
                f"The +2R limit will not be re-placed.")
        except Exception:  # loud-ok: audited above
            logger.warning(f"breakout pp unsold-third notify failed for {ticker}", exc_info=True)
    return {"ticker": ticker, "action": "partial_submitted" if ok else "partial_failed", "shares": int(shares)}


_RETRY_OUTCOME = {"partial_submitted": "breakout_pp_third_retry_sold",
                  "breakout_pp_third_filled_in_race": "breakout_pp_third_retry_third_filled",
                  "breakout_pp_third_stopped_in_race": "breakout_pp_third_retry_third_stopped"}


async def _breakout_pp_third_retry(trade: dict, fwd: list, state: dict) -> dict:
    """HIS RULING 2026-10-31 ("Go with rec": "Retry the sale at the next day's close") — sessions 4, 5, ...: a trade
    whose session-3 step DECIDED to sell the third (`breakout_pp_exit.session_third_due`, the record written before
    any cancel or sale) and still has no third sold (`partial_taken` FALSE — a +2R limit that filled first IS the
    third, and the retry stops) sells a third at THIS session's close through `_breakout_pp_sell_third`: any
    partial-exit order still resting (the +2R limit left past session 3, or a sale that never settled) is cancelled
    first, confirm-or-replace, never a second stop on a live leg and never two sells for one third. One third per
    trade, ever — `execute_partial_exit` re-checks `partial_taken` under the lock, so a fill that lands between this
    read and the sale refuses it. State from the DB and the broker only (restart-safe; nothing in memory). Every
    retry is audited (`breakout_pp_third_retry`, then `_sold` / `_third_filled` / `_third_stopped` / `_failed`);
    the sale and a failure page inside the sell path. The retry re-executes the session-3 DECISION — his rec carried
    no price condition, so none is applied here — and a trade whose session 3 decided nothing is never retried."""
    ticker, session = trade["ticker"], len(fwd)
    partial_taken = bool(trade.get("partial_taken"))
    # the flag AND the wider truth (a stop-leg fill of the third never sets the flag): nothing is retried once any
    # share has left the position — the third left under its OCO, if any, closes when its own leg fills
    sold, _sold_why = await _bpp.shares_already_sold(trade)
    due = False if sold else await _bpp.session_third_due(trade["id"])
    if _bpp_rules.retry_decision(fwd=fwd, partial_taken=partial_taken, session_third_due=due,
                                 shares_sold=sold) != _bpp_rules.RETRY_THIRD:
        return {"ticker": ticker, "action": "breakout_pp_not_session3", "session": session}
    fill, stop0 = float(trade["entry_price"]), float(state["hard_stop"])
    last = float(fwd[-1]["c"])
    resting, resting_oid = await _bpp.resting_third(trade["id"])
    await log_audit_event(
        "breakout_pp_third_retry",
        f"{ticker} #{trade['id']}: session {session} at ${last:.2f} — the session-3 third was never sold; retrying "
        f"the sale at the close"
        + (f" (a partial-exit order {str(resting_oid or '?')[:8]} still rests — the +2R limit, or a sale that never "
           f"settled — it is cancelled first)" if resting else ""),
        json.dumps({"trade_id": trade["id"], "ticker": ticker, "session": session, "last": last, "fill": fill,
                    "resting": resting, "resting_order_id": resting_oid, "account_mode": trade.get("account_mode")}),
    )
    try:
        res = await _breakout_pp_sell_third(trade, last=last, fill=fill, stop0=stop0, resting=resting,
                                            resting_oid=resting_oid, session=session, retry=True)
    except Exception as e:
        # a plain sale that RAISES (no cancel happened — the stop is intact) is still a retry that did not sell:
        # audited as the retry's failure and paged here, so the terminal row and the page exist on every path
        err = f"{type(e).__name__}: {e}"
        logger.error(f"breakout pp: the session-{session} retry raised for {ticker} #{trade['id']}: {err}",
                     exc_info=True)
        await log_audit_event(
            "breakout_pp_third_retry_failed",
            f"{ticker} #{trade['id']}: session {session} retry — the sale raised ({err[:200]}); no third sold; "
            f"the sale is retried at the next close",
            json.dumps({"trade_id": trade["id"], "ticker": ticker, "session": session, "result": "raised",
                        "error": err[:300]}),
        )
        try:
            await send_telegram_message(
                f"{mode_prefix(trade.get('account_mode'))}⚠️ *Breakout third NOT sold: {ticker}*\n"
                f"The day {session} retry of the third raised ({err[:120]}). No third was sold today; the stop is "
                f"unchanged and the sale is retried at the next close.")
        except Exception:  # loud-ok: audited above
            logger.warning(f"breakout pp retry-raised notify failed for {ticker}", exc_info=True)
        return {"ticker": ticker, "action": "breakout_pp_error", "retry": True, "session": session}
    outcome = _RETRY_OUTCOME.get(res["action"], "breakout_pp_third_retry_failed")
    await log_audit_event(
        outcome,
        f"{ticker} #{trade['id']}: session {session} retry — {res['action']}"
        + (f", {res['shares']} sh" if res.get("shares") else ""),
        json.dumps({"trade_id": trade["id"], "ticker": ticker, "session": session, "result": res["action"],
                    "shares": res.get("shares")}),
    )
    return dict(res, retry=True, session=session)


async def _breakout_pp_session3_guarded(trade: dict, today: date, state: dict, today_bar: dict) -> dict:
    """`_breakout_pp_session3`, with a raise audited for THAT row so it never skips every later trade in the
    15:45 pass (breakout rows only; the third-after-cancel re-protect happens inside before any raise escapes)."""
    try:
        return await _breakout_pp_session3(trade, today, state, today_bar)
    except Exception as e:
        ticker, err = trade["ticker"], f"{type(e).__name__}: {e}"
        logger.error(f"run_partial_exits: breakout pp session 3 raised for {ticker} #{trade['id']}: {err}",
                     exc_info=True)
        await log_audit_event(
            "breakout_pp_session3_raised",
            f"{ticker} #{trade['id']}: the session-3 breakout step raised — {err}"[:500],
            json.dumps({"trade_id": trade["id"], "ticker": ticker, "error": err[:300]}),
        )
        return {"ticker": ticker, "action": "breakout_pp_error"}


async def run_partial_exits(today: date | None = None) -> list[dict]:
    """Run the Day 3-5 partial-profit decision DURING market hours (3:45 PM ET).

    #361 (2026-06-23): SPLIT OUT of the 4:45 PM `update_open_positions_live`
    EOD job. The partial-profit decision LOGIC is UNCHANGED — it is still the
    single source of truth in `apply_daily_exit_step` (we reuse it; we do not
    duplicate the decision). Only WHEN it fires moved: from after the close
    (4:45) to mid-session (3:45).

    WHY 3:45 / market-hours: when the partial fired at 4:45 (after the 16:00 ET
    close), its stop-replace parked in `pending_replace` until the next session
    open. Both the old and the new stop reserved the shares → qty_available=0 →
    the partial sell aborted. Mid-session, the stop-replace settles in ~0.2s and
    the sell fills cleanly.

    Acts ONLY on the partial branch (`step.partial_fired`) → `execute_partial_exit`.
    Persists NOTHING here:
      - The reduced remaining / partial_taken / breakeven_active / exits are
        committed by `finalize_partial_exit` on the actual WS fill (the only
        authorized writer — BW 5/14 optimistic-write protocol).
      - running_closes / hold_days / SMA-trail stop stay OWNED by the 4:45 job.
        Writing running_closes here would DOUBLE-APPEND today's close (the
        append at exit_logic.py line ~98 runs every call), corrupting the SMA
        basis — so this function deliberately discards the rest of `step`.

    No double-fire: the 4:45 job passes `skip_partial_decision=True`, so the
    partial can fire only here, exactly once per day.

    Note: at 3:45 `get_index_history` returns today's FORMING daily bar (live
    Polygon aggregate), so `bar_close` is the intraday last trade, not the
    settled close. For the Day 3-4 branch (`bar_close > entry_price`) this is an
    intraday evaluation — implicit in the operator's choice of a market-hours
    trigger. Day 5+ is unconditional and unaffected.
    """
    if today is None:
        today = et_today()

    pool = await get_pool()
    async with pool.acquire() as conn:
        open_trades = await conn.fetch("""
            SELECT * FROM mi_live_trades
            WHERE status = 'filled' AND remaining_shares > 0
            ORDER BY alert_date ASC
        """)

    if not open_trades:
        logger.info("run_partial_exits: no open live positions")
        return []

    logger.info(
        f"run_partial_exits: scanning {len(open_trades)} open positions for "
        f"Day 3-5 partials: {[dict(t)['ticker'] for t in open_trades]}"
    )
    results: list[dict] = []

    for trade in open_trades:
        trade = dict(trade)
        ticker = trade["ticker"]
        state, daily_bars, skip = await _load_exit_state(trade, today)
        if skip == "silent":
            continue
        if skip == "no_data":
            logger.debug(f"run_partial_exits: no daily bar for {ticker} on {today}")
            results.append({"ticker": ticker, "action": "no_data"})
            continue

        # Breakout v1 PAPER (2026-10-30): a 'breakout_pp' row never takes the day-3/5 ladder below.
        # On SESSION 3 (today's forming bar is session 3) its `pp` arm decides here, before the
        # close, in the walk's order: the stall cut (no high at fill + 1R by now -> everything sold)
        # else the session-3 third (no third yet and the price is above the fill -> a resting +2R
        # limit cancelled first, then a third sold; the stop to the fill when it fills). Decisions:
        # breakout_pp_rules.session3_decision. From SESSION 4 on, a session-3 third that was decided
        # but never sold is RETRIED at this session's close (his ruling 2026-10-31;
        # breakout_pp_rules.retry_decision).
        if trade.get("exit_rule") == BREAKOUT_PP_EXIT_RULE:
            results.append(await _breakout_pp_session3_guarded(trade, today, state, daily_bars[0]))
            continue

        # Single-source-of-truth partial decision. We discard everything in
        # `step` EXCEPT partial_fired / partial_shares — the SMA-trail, stop,
        # and running_closes advance are the 4:45 job's domain (see docstring).
        #
        # skip_hard_stop_close=True is REQUIRED here (matches the 4:45 job's
        # post-verify re-run): at 3:45 the forming bar's `bar_low` is the
        # intraday low, so a position that WICKED to/through its hard_stop
        # intraday but recovered (still open, still green) would short-circuit
        # `apply_daily_exit_step` at its step-1 hard-stop close — returning
        # partial_fired=False BEFORE the partial branch — and we'd silently DROP
        # that day's partial. The real Alpaca resting stop is the actual stop
        # mechanism (the backtest-pure bar_low<=hard_stop close is a no-op once
        # the position is confirmed held); these positions ARE held (the query
        # filters status='filled' AND remaining_shares>0). Skipping the close
        # branch keeps the partial decision alive — faithful to the validated
        # live behavior. We still act ONLY on partial_fired; the close path is
        # never executed from this partial-only job.
        # #508 — when the intraday profit trigger is ON it OWNS the partial, so the
        # 3:45 time-gate must stand down or both could act on the same position.
        # Done at the CALLER, not by editing exit_logic: that module is pure decision
        # logic with no config dependency, and it already exposes exactly this seam
        # (`update_open_positions_live` at 4:45 has passed skip_partial_decision=True
        # since #361 for the same reason — one owner per decision).
        # PROFIT_TRIGGER_R = None restores the day-3/day-5 rule with no code change.
        from agents.market_intelligence.constants import PROFIT_TRIGGER_R
        step = apply_daily_exit_step(state, daily_bars[0], today,
                                          # #548: the trail is the STOCK's MA, not our hold-period mean
                                          prior_closes=state.get("prior_closes"),
                                          trail_arm_on_close_above=True,
                                          entry_day_close=state.get("entry_day_close"),
                                     integer_partial_shares=True,
                                     skip_hard_stop_close=True,
                                     skip_partial_decision=bool(PROFIT_TRIGGER_R))

        if not step.partial_fired:
            results.append({"ticker": ticker, "action": "no_partial"})
            continue

        logger.info(
            f"run_partial_exits: {ticker} day={step.hold_days} "
            f"close=${step.bar_close:.2f} partial_shares={step.partial_shares:.0f}"
        )

        # ── Announce the DECISION, not just the downstream fill (operator 2026-08-01:
        # "is telegram hooked up to notify me of profit takes"). It was not: this job
        # had ZERO Telegram calls, so a partial the system CHOSE to take reached him
        # only as a broker fill event with no statement of why or at what level. On a
        # rule whose whole purpose is "take profit at X", the reasoning is the message.
        # Self-catching: a notification failure must never abort a money action that
        # is about to run on the next line.
        try:
            _entry = trade.get("entry_price")
            _risk = (_entry - state["hard_stop"]) if (_entry and state["hard_stop"]) else None
            _rem = trade.get("remaining_shares")
            r_now = ((step.bar_close - _entry) / _risk) if (_risk and _entry) else None
            await send_telegram_message(
                f"{mode_prefix(trade.get('account_mode'))}💰 *Profit-take firing: {ticker}*\n"
                f"day {step.hold_days} · close ${step.bar_close:.2f}"
                + (f" · {r_now:+.2f}R" if r_now is not None else "")
                + f"\nSelling {int(step.partial_shares)} of {int(_rem)} sh, "
                f"stop moves to breakeven (${_entry:.2f})."
            )
        except Exception:  # loud-ok: send_telegram_message self-catches and returns False; this guards the f-string/format path only. The partial below MUST run regardless.
            logger.warning(f"partial-decision notify failed for {ticker}", exc_info=True)

        partial_ok = await execute_partial_exit(trade["id"], int(step.partial_shares))
        # finalize_partial_exit commits the DB state on the actual WS fill; if
        # the helper aborts/fails it has already audit-logged + (where relevant)
        # re-protected the stop. Nothing to persist here either way — the 4:45
        # job and the WS fill own all state writes.
        results.append({
            "ticker": ticker,
            "action": "partial_submitted" if partial_ok else "partial_failed",
            "shares": int(step.partial_shares),
        })

    return results


# ── Morning Stop Refresh ─────────────────────────────────────────────────────


async def post_close_stop_refresh() -> int:
    """16:20 ET — put a live GTC stop on every open position BEFORE the next open.

    ⚖ **THE GOAL, operator 2026-08-04, verbatim: *"do we have a stop always during
    market hours"*.** Until this job, the answer was NO for five minutes a day.

    THE HOLE IT CLOSES. An entry bracket is submitted `TimeInForce.DAY`, so its stop
    LEG dies at the 16:00 close. `morning_stop_refresh` re-places it as a standalone
    GTC — but at **09:35**, five minutes after the open. Verified on PLTR 307
    (2026-08-04): leg expired 16:00, and the live account then showed zero open
    orders with all 6 shares free. Verified the other way on QBTS (2026-07-28):
    refreshed 09:35, stopped out 09:36:24. So every Day-2+ position traded the first
    five minutes of its session — the most volatile five minutes, the ones an
    overnight gap resolves into — with no resting stop.

    WHY AFTER THE CLOSE IS THE SAFE PLACE, and 09:35 same-day was not. The ADR-0029
    exclusion below exists because at 09:35 a same-morning fill's OTO child is LIVE
    and holding the shares, so re-placing raced it (the WULF `insufficient qty
    available` self-conflict). At 16:20 that child has ALREADY EXPIRED — there is
    nothing to race. That is the whole reason this job can cover same-day fills when
    the morning one must not, and it is why `include_same_day` is True here.

    Idempotent by construction: the still-active check below skips any position whose
    stop is already resting, so a position that somehow kept its stop is left alone.
    `morning_stop_refresh` stays exactly as it is — belt and braces, not replaced.
    """
    return await _stop_refresh(include_same_day=True, label="post-close")


async def morning_stop_refresh() -> int:
    """
    At 9:35 AM, ensure stop orders are active for all Day 2+ positions.
    Alpaca DAY stops expire overnight — re-place them as GTC.
    Returns count of stops refreshed.

    ⚠ As of 2026-08-04 this is the BACKSTOP, not the primary: `post_close_stop_refresh`
    (16:20 ET) now places the GTC stop the evening before, so a position normally
    arrives at the open already protected and every trade here hits the
    "still active → skip" branch. Kept because a stop that dies overnight (broker-side
    cancel, a fill that did not settle) must still be caught before the day trades.

    SAME-DAY EXCLUSION (ADR 0029 D1, signed 2026-07-12, shipped 2026-07-26). The
    docstring above always said "Day 2+", but the query did not enforce it — it
    selected every filled position including ones that filled THIS MORNING, whose
    stop is an OTO child placed atomically with the entry. Refreshing those raced
    the broker's own child order and produced the WULF `insufficient qty
    available` self-conflict. Entry day = the OTO child owns the stop BY
    CONSTRUCTION; the refresh exists solely to replace overnight-expired DAY
    stops, which by definition cannot apply to a same-morning fill. Excluding
    them removes the 9:35 collision at the root — the #433 retry machinery stays
    as belt-and-suspenders and is expected to go quiet.

    Day-1 RE-ENTRY is covered by the same exclusion and deliberately so (advisor
    carve-in, ADR 0029): `attempt_day1_reentry` places a FRESH OTO bracket on the
    same alert_date after a stop-out, so its protection is likewise its own
    atomically-placed child.

    This job NEVER discovers stops — a NULL/stale `stop_order_id` is a MIRROR
    defect, healed by the remediation stack (3-source capture at fill,
    `sync_positions` Path-C naked remediation, #184b R1 ingest repointing), never
    by this refresh. So a genuinely-naked same-day trade is still caught; it is
    not silently skipped forever. Risk framing: this NARROWS a live job — it does
    strictly less, on a cohort whose protection already exists.
    """
    return await _stop_refresh(include_same_day=False, label="Morning")


async def _stop_refresh(*, include_same_day: bool, label: str) -> int:
    """Shared body for both stop-refresh passes. The ONLY difference between them is
    whether same-day fills are in scope — see each caller's docstring for why.

    #527 Part 1 (2026-08-07): emits ONE `stop_refresh_ran` audit row per run,
    UNCONDITIONALLY — including the all-quiet case where nothing needs doing.
    Before this, the function only ever logged via `logger.info`/`logger.error`
    and stayed completely silent when every position was already covered, so
    "ran and found everything fine" was indistinguishable from "never ran at
    all". Measured in prod: `post_close_stop_refresh` produced ZERO
    `mi_audit_log` rows in the three days since it shipped (PLAN.md #527) —
    not proof it was broken, just proof we had no way to tell either way.
    Telemetry only: no placement/threshold/ordering decision below changed.

    #414 HEARTBEAT (2026-09-08): the morning pass's `alert_date <> $1` guard
    (ADR 0029 D1) EXCLUDES same-day fills in the SQL itself, so an excluded row
    never reaches `examined` and the summary said nothing about what the
    exclusion removed. Measured on the live book: 15 of the last 17 fills
    landed before 09:35, so the exclusion has fired plenty — we simply never
    counted it, which is why #414's verify sat stuck since August ("cannot be
    manufactured"). This counts + names the same-day rows the morning pass is
    ABOUT to skip, purely for the audit row below — it changes nothing about
    which rows get refreshed. Read-only and failure-isolated: a failure here
    degrades to "unavailable" (`None`) rather than blocking the real refresh
    that follows. The post-close pass has nothing to exclude by construction
    (`include_same_day=True`), so it never touches this — no misleading zero.
    """
    from agents.market_intelligence.broker import order_manager as _om
    today = et_today()
    pool = await get_pool()
    same_day_excluded: list[str] | None = None
    async with pool.acquire() as conn:
        if include_same_day:
            trades = await conn.fetch("""
                SELECT id, ticker, remaining_shares, stop_price, stop_order_id,
                       account_mode
                FROM mi_live_trades
                WHERE status = 'filled' AND remaining_shares > 0
            """)
        else:
            try:
                same_day_excluded = await get_same_day_excluded_stop_candidates(conn, today)
            except Exception as e:  # loud-ok: telemetry-only read; the real refresh below must run regardless
                logger.warning(f"{label}: same-day-excluded read failed (non-fatal): {e}")
                same_day_excluded = None
            trades = await conn.fetch("""
                SELECT id, ticker, remaining_shares, stop_price, stop_order_id,
                       account_mode
                FROM mi_live_trades
                WHERE status = 'filled' AND remaining_shares > 0
                  AND alert_date <> $1
            """, today)

    examined = len(trades)
    refreshed = 0
    refreshed_tickers: list[str] = []
    unprotected: list[str] = []
    already_covered: list[str] = []
    covered_by_resting_exit: list[str] = []  # #687 ruling (2): no new stop, broker-covered
    sold_at_market: list[str] = []  # #687 ruling (iii): price through the stop → sold, paged
    skipped: list[dict] = []  # [{"ticker": ..., "reason": "no_stop_price" | "no_remaining_shares"}]
    for trade in trades:
        ticker = trade["ticker"]
        stop_price = trade["stop_price"]

        if not stop_price or not trade["remaining_shares"]:
            skipped.append({
                "ticker": ticker,
                "reason": "no_stop_price" if not stop_price else "no_remaining_shares",
            })
            continue

        # Check if existing stop order is still active.
        #
        # ⚠ account_mode is LOAD-BEARING here (#444, fixed 2026-07-27). Without
        # it this read defaulted to current_account_mode(), which resolves to
        # "paper" inside apollo-execution — so a LIVE stop_order_id was looked up
        # in the PAPER book, always returned None, and this "still active → skip"
        # branch was unreachable dead code. The job then cancelled and re-placed
        # every live Day-2+ stop EVERY morning at an identical price, each cycle
        # leaving a window with no resting stop on a real position. Confirmed in
        # prod on SMCI: 9:35 ET replacements on 07-22, 07-23 and 07-24, all
        # $28.5 → $28.50, one of which raised an APIError and needed the #433
        # retry. Passing the trade's OWN mode makes the skip branch reachable, so
        # an already-active stop is left alone.
        if trade["stop_order_id"]:
            order = await alpaca.get_order(
                trade["stop_order_id"], account_mode=trade["account_mode"],
            )
            if order and str(order.get("status", "")).split(".")[-1].lower() in ("new", "accepted", "held"):
                logger.debug(f"Stop still active for {ticker}")
                already_covered.append(ticker)
                continue

        # Re-place stop
        success = await update_stop(trade["id"], stop_price)
        if success is _om.STOP_SOLD_AT_MARKET:
            # #687 ruling (iii): price through the stop → `update_stop` sold at market and paged
            # it. Not a "No stop on X" gap: the sale fills in milliseconds, so the broker re-check
            # below would find neither a stop nor a covering order.
            sold_at_market.append(ticker)
        elif success:
            refreshed += 1
            refreshed_tickers.append(ticker)
            logger.info(f"{label} stop refreshed: {ticker} @${stop_price:.2f}")
        elif await _om._resting_exits_cover_position(
                trade["id"], ticker, float(trade["remaining_shares"]), trade["account_mode"]):
            # ⚖ #687 ruling (2), operator 2026-10-01: no new stop was placed, but the BROKER
            # shows the shares covered — a resting +8R profit-take OCO third (its own stop
            # leg), or our own queued closing order. Not a gap: recorded, not paged.
            covered_by_resting_exit.append(ticker)
        else:
            # A position we could not re-protect must never be a log line only —
            # that is the exact shape of the gap this job exists to close.
            unprotected.append(ticker)

    if refreshed:
        # #475 (2026-07-15): routine housekeeping — expected every morning for
        # every Day 2+ position (DAY stops expire overnight). Log only; failures
        # in update_stop() keep their own loud paths.
        logger.info(
            f"{label}: refreshed {refreshed} stop order(s) — {', '.join(refreshed_tickers)}"
        )
    if unprotected:
        logger.error(f"{label}: FAILED to place a stop for {', '.join(unprotected)}")
        await log_audit_event(
            "stop_refresh_failed",
            f"{label}: could not place a stop for {', '.join(unprotected)}",
            json.dumps({"pass": label, "tickers": unprotected}),
        )
        await send_telegram_message(
            f"🚨 *No stop on {', '.join(unprotected)}* — the {label} stop refresh "
            f"could not place one. The position is unprotected for the next session."
        )

    # #527 Part 1 — proof-of-run, UNCONDITIONAL (fires even when nothing needed doing;
    # that all-quiet case is exactly what was previously unprovable). Per-ticker
    # breakdown goes in `detail` (JSON), not the summary — the summary stays a fixed
    # 4-number shape so it reads the same whether 1 position or 40 were examined.
    reason_counts: dict[str, int] = {}
    for s in skipped:
        reason_counts[s["reason"]] = reason_counts.get(s["reason"], 0) + 1
    skip_summary = ", ".join(f"{k}={v}" for k, v in sorted(reason_counts.items())) or "none"
    summary = (
        f"{label}: examined {examined}, placed {refreshed}, "
        f"already-covered {len(already_covered)}, skipped {len(skipped)} ({skip_summary})"
    )
    detail = {
        "pass": label,
        "examined": examined,
        "placed": refreshed,
        "placed_tickers": refreshed_tickers,
        "already_covered": already_covered,
        "skipped": skipped,
        "unprotected": unprotected,
    }
    if covered_by_resting_exit:
        detail["covered_by_resting_exit"] = covered_by_resting_exit
    if sold_at_market:
        detail["sold_at_market"] = sold_at_market
    # #414 — only the morning pass excludes anything, and only when the read above
    # succeeded. `same_day_excluded is None` covers BOTH the post-close pass
    # (nothing to exclude by construction) and a failed read on the morning pass
    # (unknown, not zero) — either way, stay silent rather than write a number
    # that isn't true. An empty list IS a real, reportable zero.
    if same_day_excluded is not None:
        detail["same_day_excluded"] = len(same_day_excluded)
        detail["same_day_excluded_tickers"] = same_day_excluded
        summary += (
            f", same-day excluded {len(same_day_excluded)} "
            f"({', '.join(same_day_excluded) if same_day_excluded else 'none'})"
        )
    await log_audit_event("stop_refresh_ran", summary, json.dumps(detail))
    return refreshed


# ── Daily Summary ────────────────────────────────────────────────────────────


async def _gather_mode_summary(conn, mode: str, today) -> dict:
    """Per-account-mode slice of the daily book. Every query is filtered by
    account_mode so paper and live never bleed together (the pre-dual-account
    version queried the whole table and mislabeled everything paper — operator 7/8)."""
    stats = await conn.fetchrow("""
        SELECT
            COUNT(*) FILTER (WHERE status NOT IN ('skipped','cancelled','order_failed')) as total,
            COUNT(*) FILTER (WHERE status = 'closed' AND total_pnl > 0) as winners,
            COUNT(*) FILTER (WHERE status = 'closed' AND total_pnl <= 0) as losers,
            COALESCE(SUM(total_pnl) FILTER (WHERE status = 'closed'), 0) as realized_pnl
        FROM mi_live_trades WHERE account_mode = $1
    """, mode)
    open_trades = await conn.fetch("""
        SELECT ticker, entry_price, remaining_shares, stop_price, hold_days,
               partial_taken, total_pnl
        FROM mi_live_trades
        WHERE status = 'filled' AND remaining_shares > 0 AND account_mode = $1
        ORDER BY alert_date ASC
    """, mode)
    todays_closes = await conn.fetch("""
        SELECT ticker, total_pnl, hold_days FROM mi_live_trades
        WHERE status = 'closed' AND account_mode = $2
          AND (closed_at AT TIME ZONE 'America/New_York')::date = $1
    """, today, mode)
    todays_entries = await conn.fetch("""
        SELECT ticker, entry_price, entry_shares FROM mi_live_trades
        WHERE alert_date = $1 AND account_mode = $2 AND status IN ('filled', 'order_placed')
    """, today, mode)
    todays_skipped = await conn.fetch("""
        SELECT ticker, skip_reason FROM mi_live_trades
        WHERE alert_date = $1 AND account_mode = $2
          AND status IN ('skipped', 'cancelled', 'order_failed')
    """, today, mode)
    return {"stats": stats, "open": open_trades, "closes": todays_closes,
            "entries": todays_entries, "skipped": todays_skipped}


def _mode_has_activity(d: dict) -> bool:
    return bool(d["entries"] or d["closes"] or d["skipped"] or d["open"]
                or (d["stats"]["total"] and d["stats"]["total"] > 0))


async def send_live_trade_summary() -> None:
    """Daily summary of trading activity, PER ACCOUNT (dual-account #66).
    #479: routed into the 16:55 Market Close Digest (BOOK section) instead of
    a standalone Telegram — render text unchanged.

    Live-money account is the PRIMARY block (full detail); paper is FOLDED into a
    compact secondary line (operator 7/8: only the paper book was reported, so the
    real-money EOD state was invisible). Paper-only deployments (ENABLE_LIVE_MODE
    off) render exactly as before. Called after the position update."""
    from agents.market_intelligence.constants import active_account_modes
    pool = await get_pool()
    today = et_today()
    modes = active_account_modes()
    async with pool.acquire() as conn:
        data = {m: await _gather_mode_summary(conn, m, today) for m in modes}

    primary = "live" if "live" in modes else "paper"
    prim = data[primary]
    prim_label = "Live" if primary == "live" else "Paper"
    lines = [f"{mode_prefix(primary)}📊 *Live Trade Update (Alpaca — {prim_label})*\n"]

    # ── PRIMARY block (full detail) ──
    if prim["entries"]:
        lines.append("*Entered today:*")
        for t in prim["entries"]:
            lines.append(f"  ▶ {t['ticker']} @${t['entry_price']:.2f} × {t['entry_shares']:.0f}")
        lines.append("")
    if prim["skipped"]:
        lines.append("*Filtered today:*")
        for t in prim["skipped"]:
            lines.append(f"  ⊘ {t['ticker']}: {humanize(t['skip_reason'])}")
        lines.append("")
    if prim["closes"]:
        lines.append("*Closed today:*")
        for t in prim["closes"]:
            emoji = "✅" if t["total_pnl"] > 0 else "❌"
            lines.append(f"  {emoji} {t['ticker']} ${t['total_pnl']:+,.2f} ({t['hold_days']}d)")
        lines.append("")
    if prim["open"]:
        lines.append(f"*Open positions ({len(prim['open'])}):*")
        for t in prim["open"]:
            ticker = t["ticker"]
            try:
                pos = await alpaca.get_position(ticker, primary)
                current = pos["current_price"] if pos else None
                unrealized = pos["unrealized_pl"] if pos else 0
            except Exception as e:
                logger.warning(f"Could not get position for {ticker} ({primary}) in summary: {e}")
                current = None
                unrealized = 0
            entry_str = f"${t['entry_price']:.2f}" if t["entry_price"] else "?"
            current_str = f"${current:.2f}" if current else "?"
            pnl_emoji = "🟢" if unrealized > 0 else "🔴" if unrealized < 0 else "⚪"
            partial = " ½" if t["partial_taken"] else ""
            lines.append(
                f"  {pnl_emoji} {ticker} {entry_str}→{current_str} "
                f"${unrealized:+,.0f} · {t['hold_days']}d{partial}"
            )
        lines.append("")

    ps = prim["stats"]
    prim_closed = (ps["winners"] or 0) + (ps["losers"] or 0)
    try:
        account = await alpaca.get_account(primary)
        lines.append(f"*Account:* ${account['equity']:,.0f}")
    except Exception as e:
        logger.warning(f"Could not get {primary} account equity for summary: {e}")
    if prim_closed > 0:
        wr = ps["winners"] / prim_closed * 100
        lines.append(f"*Record:* {ps['winners']}W/{ps['losers']}L ({wr:.0f}%) · "
                     f"${float(ps['realized_pnl']):+,.2f}")
    elif ps["total"]:
        lines.append(f"*Trades:* {ps['total']} (no closes yet)")

    # ── FOLDED paper block (compact secondary) ──
    # Only when paper is ACTIVELY trading that day (today-activity or open positions) —
    # NOT for the dormant historical cumulative. Nothing is phase='paper' today, so this
    # stays silent until a setup is promoted to paper (operator 7/8); it then auto-reappears.
    pap = data.get("paper")
    _paper_active = pap and (pap["entries"] or pap["closes"] or pap["skipped"] or pap["open"])
    if primary == "live" and _paper_active:
        pst = pap["stats"]
        pap_closed = (pst["winners"] or 0) + (pst["losers"] or 0)
        seg = []
        try:
            pa = await alpaca.get_account("paper")
            seg.append(f"${pa['equity']:,.0f}")
        except Exception as e:
            logger.warning(f"Could not get paper account equity for summary: {e}")
        if pap_closed > 0:
            wr = pst["winners"] / pap_closed * 100
            seg.append(f"{pst['winners']}W/{pst['losers']}L ({wr:.0f}%) · "
                       f"${float(pst['realized_pnl']):+,.2f}")
        act = []
        if pap["entries"]:
            act.append(f"{len(pap['entries'])} entered")
        if pap["skipped"]:
            act.append(f"{len(pap['skipped'])} filtered")
        if pap["closes"]:
            act.append(f"{len(pap['closes'])} closed")
        if pap["open"]:
            act.append(f"{len(pap['open'])} open")
        lines.append("\n— 📄 *Paper (shadow book):* " + (" · ".join(seg) or "—")
                     + (f"  ·  today: {', '.join(act)}" if act else ""))

    # Surface if any account had activity today or holds open positions.
    # #479: the routine daily summary no longer Telegrams directly — the same
    # render text goes to close_digest.contribute("BOOK", ...) and lands in
    # the 16:55 Market Close Digest (this function is job-exclusive to the
    # 16:45 live_position_update job).
    if any(_mode_has_activity(data[m]) for m in modes):
        from agents.market_intelligence.close_digest import contribute
        contribute("BOOK", "\n".join(lines))


# ── Helpers ──────────────────────────────────────────────────────────────────


async def _insert_skipped_trade(
    ticker: str,
    today: date,
    alert: dict | None,
    regime_record: dict | None,
    skip_reason: str,
    signal_type: str | None = None,
    account_mode: str | None = None,
) -> None:
    """Insert a skipped live trade record.

    alert / regime_record may be None — the bar-stream timeout path cannot
    hydrate them without a DB join during a stuck lock. The invariant is that
    (ticker, alert_date, status='skipped', skip_reason) lands in mi_live_trades;
    score/catalyst/gap/regime can be LEFT-JOINed from mi_ep_alerts by /why.

    account_mode: the Alpaca account the skipped signal belongs to. Pass it for
    strategy-bound skips (a live-strategy signal → 'live') so the EOD summary
    attributes the filtered trade to the right account. Defaults to
    current_account_mode() for legacy callers (pre-dual-account behavior).
    """
    pool = await get_pool()
    # `today` (the alert_date) arrives as an ISO STRING when this is dispatched
    # over the intelligence→execution HTTP wire (_wire_default serializes dates);
    # coerce back so asyncpg's date_encode doesn't raise. This is the DB-write
    # boundary — routed through the shared db._coerce_date helper (LZB
    # 2026-06-13: this site missed the coercion → a HIGH alert sat with no terminal row).
    today = _coerce_date(today)
    ep_score = alert.get("ep_score") if alert else None
    catalyst_quality = alert.get("catalyst_quality") if alert else None
    gap_pct = alert.get("gap_pct") if alert else None
    regime = regime_record.get("regime") if regime_record else None
    from agents.market_intelligence.constants import current_account_mode
    account_mode = account_mode or current_account_mode()
    async with pool.acquire() as conn:
        await conn.execute("""
            INSERT INTO mi_live_trades
                (ticker, alert_date, ep_score, catalyst_quality, gap_pct,
                 regime, status, skip_reason, signal_type, account_mode)
            VALUES ($1, $2, $3, $4, $5, $6, 'skipped', $7, $8, $9)
            -- MUST match the LIVE constraint. #465 (commit 5de10cb, 2026-08-01 16:45 ET) dropped
            -- mi_live_trades_ticker_alert_date_key and replaced it with the 3-column
            -- mi_live_trades_ticker_alert_date_mode_key, but this clause kept naming the 2-column
            -- target -- so from the next boot EVERY skip-row insert raised
            -- "no unique or exclusion constraint matching the ON CONFLICT specification",
            -- was swallowed into a logged ERROR, and no HIGH EP got a durable terminal row.
            -- Surfaced 2026-08-03 as a DOUBLE Telegram: the row is also the duplicate-suppression
            -- anchor (step 1 of submit_trade_entry), so with it missing the bar_stream and cron_9_31
            -- monitors both ran FTK to completion and both messaged the operator.
            -- tests/test_live_trades_conflict_target.py pins this against the declared schema.
            ON CONFLICT (ticker, alert_date, account_mode) DO NOTHING
        """,
            ticker, today, ep_score, catalyst_quality, gap_pct, regime,
            skip_reason, signal_type, account_mode,
        )


# ── 9M EP Day 2 ORB ──────────────────────────────────────────────────────────


# submit_9m_day2_trade REMOVED 2026-08-02 (#515). The Day-2 ENTRY strategy is retired; the 9M
# CHARACTER detection and the prior-day-low ORB GEOMETRY (renamed
# prepare_prior_day_low_orb_order, still used by the #482 shadow lane) both stay.
