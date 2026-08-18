"""Broker-order INGEST — the mutation half of ADR 0008 increment 2(b) (#184b).

Coverage-drift DETECTION (2a) is live: it finds broker orders/positions the DB mirror doesn't
track. This is the REPAIR half — reconstruct/repair the mirror so an a41e7c6a-class gap (broker is
covered, DB thinks NAKED → false-naked alarms + false remediation) can't persist. It MUTATES
mi_live_trades / mi_live_orders, so it ships DARK behind a FAIL-CLOSED 3-state toggle, phased on
per case class, each live-enable operator-signed after reviewing dry-run proposals (THE LINE).

Spec: docs/analysis/184b_broker_order_ingest_spec_2026-07-06.md. Case classes:
  R1  stop-pointer repair — DB open row, stop_order_id NULL/dead, broker HAS the apollo stop → repoint
  R2  untracked entry     — broker apollo BUY unfilled, no DB row → reconstruct status='order_placed'
  R3i untracked position  — broker position, no DB row → reconstruct status='filled'
  (foreign/manual COID    — NEVER ingest; the operator's manual trades are not ours to mirror)

Runs in the execution role (holds the live creds), inside coverage_drift's reconcile cycle but
AFTER detection completes and in its OWN guard — a broken ingest can NEVER abort FL-4 detection.

Today's authority (7/11): R1 is live-capable (behind live_r1); R2/R3i propose in dry-run only
(reconstruction is spec'd but the live write waits for observations + operator sign-off). Every
live enable = operator flips the mi_safeguard_state toggle after reviewing ≥3 clean dry-run
proposals (CHANGE_PROCESS). `/pause` does NOT gate this — it's mirror-repair, not entries.
"""
from __future__ import annotations

import json
import logging
from datetime import datetime
from zoneinfo import ZoneInfo

from agents.market_intelligence.briefing import send_telegram_message
from agents.market_intelligence.constants import mode_prefix
from agents.market_intelligence.db import get_pool, get_safeguard_state, log_audit_event, _jsonb_param

logger = logging.getLogger(__name__)
_ET = ZoneInfo("America/New_York")

INGEST_TOGGLE = "broker_order_ingest"
_INGEST_ENV = "BROKER_ORDER_INGEST_MODE"
INGEST_MODES = ("off", "dry_run", "live_r1", "live_r2", "live_r3")
PER_CYCLE_CAP = 2  # a mass-gap event should page via D1/D2 alerts, not bulk-mutate

# audit event types
INGEST_PROPOSED = "ingest_proposed"          # dry-run (or a live class that isn't enabled yet)
INGEST_RECONSTRUCTED = "ingest_reconstructed"  # a live mutation actually happened
INGEST_REJECTED = "ingest_rejected"          # a COID that failed validation (itself a finding)
INGEST_ERROR = "ingest_error"                # a throw inside ingest (loud; never re-raised)


# ─────────────────────────────── toggle (fail CLOSED) ────────────────────────────────
async def get_ingest_mode() -> str:
    """The 3-state ingest toggle. FAIL-CLOSED — UNLIKE get_runtime_toggle (which fails to the env
    value because it governs grade-quality); this governs trade-state MUTATION, so ANY uncertainty
    — DB error, or an unrecognized state string — resolves to 'off' (no write). Precedence:
    mi_safeguard_state.state (validated) → env → 'off'.
    #449: the raw SQL now goes through db.get_safeguard_state (shared read, same idiom as
    get_manual_halt_state / get_runtime_toggle); fail-direction UNCHANGED — still applied HERE,
    not inside the shared helper (a missing row falls to the env value, NOT to 'off' — that
    asymmetry vs an unrecognized-state/DB-error is why validate/coerce stays local, per-caller)."""
    import os
    env_raw = os.environ.get(_INGEST_ENV, "off").lower()
    env_mode = env_raw if env_raw in INGEST_MODES else "off"
    try:
        row = await get_safeguard_state(INGEST_TOGGLE, "global")
        state = row["state"] if row else env_mode
        return state if state in INGEST_MODES else "off"  # unrecognized → off (fail closed)
    except Exception as e:  # loud-ok: fail CLOSED (no mutation) on any read error — THE LINE
        logger.warning(f"ingest toggle read failed → 'off' (fail-closed): {e}")
        return "off"


_LIVE_TIER = {"live_r1": 1, "live_r2": 2, "live_r3": 3}  # off/dry_run absent → tier 0 (never mutate)


def _class_enabled(mode: str, drift_class: str) -> bool:
    """Is `drift_class` (r1/r2/r3) enabled to MUTATE at the current toggle mode? 'off'/'dry_run'
    never mutate; live_rN enables r1..rN cumulatively (live_r2 ⇒ r1+r2)."""
    return _LIVE_TIER.get(mode, 0) >= _LIVE_TIER["live_" + drift_class]


# ─────────────────────────────── COID parse + validate ───────────────────────────────
def parse_coid(coid: str) -> dict | None:
    """apollo_{mode}_{strategy}_{ticker}_{ms} → {mode,strategy,ticker,ms,alert_date}. None on a
    wrong shape. `strategy` may contain underscores; `ms` is the trailing all-digit field, and its
    epoch → the ET alert_date (never naive — the recurring tz-bug class)."""
    if not coid or not coid.startswith("apollo_"):
        return None
    parts = coid.split("_")            # ["apollo", mode, strategy…, ticker, ms] — ≥5 parts
    if len(parts) < 5:
        return None
    mode, ms, ticker = parts[1], parts[-1], parts[-2]
    strategy = "_".join(parts[2:-2])
    if mode not in ("live", "paper") or not ms.isdigit() or not ticker or not strategy:
        return None
    alert_date = datetime.fromtimestamp(int(ms) / 1000, _ET).date()
    return {"mode": mode, "strategy": strategy, "ticker": ticker, "ms": int(ms), "alert_date": alert_date}


async def validate_coid(parsed: dict, *, account_mode: str, symbol: str) -> tuple[bool, str]:
    """A mismatched COID is itself a finding (§2) — REJECT, never coerce. Checks: mode == the
    cycle's account_mode, ticker == the order/position symbol, strategy exists in the registry."""
    if parsed["mode"] != account_mode:
        return False, f"mode_mismatch coid={parsed['mode']} cycle={account_mode}"
    if parsed["ticker"] != symbol:
        return False, f"ticker_mismatch coid={parsed['ticker']} symbol={symbol}"
    pool = await get_pool()
    async with pool.acquire() as conn:
        exists = await conn.fetchval(
            "SELECT EXISTS (SELECT 1 FROM mi_strategies WHERE strategy_id = $1)", parsed["strategy"])
    return (True, "ok") if exists else (False, f"unknown_strategy {parsed['strategy']}")


# ─────────────────────────────── dedup + proposal emit ───────────────────────────────
def _signature(account_mode: str, drift_class: str, ticker: str, order_id: str | None) -> str:
    return f"ingest|{account_mode}|{drift_class}|{ticker}|{order_id or ''}"


async def _already_seen(conn, signature: str) -> bool:
    """Dedup — one emit per signature per 24h (mirrors coverage_drift._already_alerted so we don't
    Telegram-spam the same gap every 15-min cycle). Includes REJECTED: a persistently-invalid COID
    sits in the broker book indefinitely, so without it a reject re-Telegrams ~96×/day."""
    return bool(await conn.fetchval(
        """SELECT 1 FROM mi_audit_log
           WHERE event_type IN ($1, $2, $3) AND summary = $4 AND created_at > NOW() - INTERVAL '24 hours'
           LIMIT 1""", INGEST_PROPOSED, INGEST_RECONSTRUCTED, INGEST_REJECTED, signature))


async def _emit(event_type: str, signature: str, detail: dict, telegram: str | None) -> None:
    await log_audit_event(event_type, signature, json.dumps(detail, default=str))
    if telegram:
        await send_telegram_message(telegram)


# ───────────────────────────────────── R1 repair ─────────────────────────────────────
async def _handle_r1(conn, account_mode: str, mode: str, db_rows: list, open_orders: list) -> int:
    """R1 — repoint a NULL/dead stop_order_id to the broker's live apollo SELL stop for that ticker
    (the a41e7c6a false-naked incident). No-overwrite: the UPDATE re-asserts the prior pointer value
    in its WHERE so a concurrent write can't be clobbered. Returns the count acted (proposed or done)."""
    # index the broker's live apollo SELL stops by ticker
    live_order_ids = {o["id"] for o in open_orders}
    stops_by_ticker: dict[str, dict] = {}
    for o in open_orders:
        coid = o.get("client_order_id") or ""
        side = (o.get("side") or "").lower()
        otype = (o.get("type") or "").lower()
        if coid.startswith(f"apollo_{account_mode}_") and side == "sell" and "stop" in otype:
            stops_by_ticker.setdefault(o["symbol"], o)  # first live apollo sell-stop wins

    acted = 0
    for r in db_rows:
        ticker = r["ticker"]
        cur = r["stop_order_id"]
        # candidate only when the DB pointer is NULL, or points at an order that is NOT in the live
        # book (broker-confirmed absent — the pointer is stale). Never touch a still-live pointer.
        if cur is not None and cur in live_order_ids:
            continue
        broker_stop = stops_by_ticker.get(ticker)
        if not broker_stop:
            continue
        parsed = parse_coid(broker_stop.get("client_order_id") or "")
        if not parsed:
            continue
        ok, reason = await validate_coid(parsed, account_mode=account_mode, symbol=ticker)
        sig = _signature(account_mode, "r1", ticker, broker_stop["id"])
        if not ok:
            if not await _already_seen(conn, sig):
                await _emit(INGEST_REJECTED, sig,
                            {"class": "r1", "ticker": ticker, "reason": reason,
                             "client_order_id": broker_stop.get("client_order_id")},
                            f"{mode_prefix(account_mode)}⚠️ *Ingest R1 rejected* — {ticker}: {reason}")
            continue
        if await _already_seen(conn, sig):
            continue

        detail = {"class": "r1", "ticker": ticker, "trade_id": r["id"], "prior_stop_order_id": cur,
                  "broker_stop_order_id": broker_stop["id"], "stop_price": broker_stop.get("stop_price")}
        if _class_enabled(mode, "r1"):
            # LIVE repair — route the write through the authorized T1.5a owner (order_manager owns
            # ALL solo stop_order_id mutations) with a no-overwrite guard (expected_prior=cur) so a
            # concurrently-moved pointer is never clobbered.
            from agents.market_intelligence.broker import order_manager
            applied = await order_manager.set_stop_order_id(
                r["id"], broker_stop["id"], reason="ingest_r1_repair",
                account_mode=account_mode, expected_prior=cur)
            if not applied:
                continue  # a concurrent write moved the pointer — abort, don't clobber
            await _upsert_stop_order(conn, r["id"], broker_stop)
            await _emit(INGEST_RECONSTRUCTED, sig, {**detail, "action": "stop_pointer_repaired"},
                        f"{mode_prefix(account_mode)}🔧 *Ingest R1 — stop repaired* — {ticker}\n"
                        f"Repointed stop_order_id → `{broker_stop['id'][:8]}` "
                        f"(was `{(cur or 'NULL')[:8] if cur else 'NULL'}`); the broker's stop is now mirrored.")
        else:
            await _emit(INGEST_PROPOSED, sig, {**detail, "action": "propose_stop_pointer_repair"},
                        f"{mode_prefix(account_mode)}📋 *Ingest R1 proposal (dry-run)* — {ticker}\n"
                        f"DB stop_order_id is `{cur or 'NULL'}` but the broker holds apollo stop "
                        f"`{broker_stop['id'][:8]}`. Would repoint. Review to enable live_r1.")
        acted += 1
        if acted >= PER_CYCLE_CAP:
            break
    return acted


async def _upsert_stop_order(conn, trade_id: int, order: dict) -> None:
    """Mirror the broker's stop order into mi_live_orders (keyed on alpaca_order_id UNIQUE)."""
    await conn.execute(
        """INSERT INTO mi_live_orders (trade_id, alpaca_order_id, ticker, side, order_type, qty,
                                       stop_price, status, raw_response)
           VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9)
           ON CONFLICT (alpaca_order_id) DO UPDATE SET trade_id = EXCLUDED.trade_id,
                                                       status = EXCLUDED.status""",
        trade_id, order["id"], order["symbol"], (order.get("side") or "sell"),
        (order.get("type") or "stop"), float(order.get("qty") or 0),
        (float(order["stop_price"]) if order.get("stop_price") else None),
        # $9 has no explicit ::jsonb cast, but resolves to the column's jsonb type from
        # the INSERT target list, so the codec still applies — #216: codec single-encodes;
        # do NOT pre-dumps.
        (order.get("status") or "new"),
        _jsonb_param(order))


# ─────────────────────────── R2 / R3i — dry-run proposals only ────────────────────────
_RECENT_CLOSE_CLAIM_MINUTES = 30  # ≥2 reconcile cycles — a genuine gap persists and re-proposes


async def _fetch_claimed_order_ids(conn, account_mode: str) -> set[str]:
    """Every broker order id the DB mirror references ANYWHERE — R2's "is this order actually
    untracked?" set. Matching OPEN rows only is the CLSK 2026-07-14 false positive: the 10:00 ET
    ORB-window cleanup (and the 4:05 PM EOD cleanup, /pause, and every other DB-side status
    transition) flips a row out of the open set while the broker order sits in its cancel window,
    and the reconcile cycle — cron-collided at the same second — reads "broker has it, DB doesn't"
    for a row that had existed since 9:31 under the same order id. Two sources, both ANY-status:

      - mi_live_trades entry/stop pointers, any status — reuses coverage_drift's
        _fetch_all_known_order_ids, the operator-signed D2 fix for the SAME race (0c4e358; D2 and
        R2 false-fired together on CLSK, only D2 got fixed). Shared helper on purpose: detection's
        and ingest's tracking sets can never drift apart again.
      - mi_live_orders.alpaca_order_id — covers the one path that NULLs a trades pointer: the
        cleanup's prior-fills branch (order_manager.cancel_unfilled_entries, Day-1 re-entry
        pattern) sets entry_order_id=NULL, but the mi_live_orders row written at submission
        survives and still claims the id. Mode-unfiltered on purpose (ids are unique broker UUIDs;
        an id we recorded in ANY mode is not "untracked" in the reconstruction sense).

    A genuinely untracked order (referenced NOWHERE — the a41e7c6a submit-crash class writes
    neither table) is unaffected and still proposes. Cheap: two-column reads off a personal trade
    log, once per 15-min cycle."""
    from agents.market_intelligence.broker.coverage_drift import _fetch_all_known_order_ids
    claimed = await _fetch_all_known_order_ids(conn, account_mode)
    rows = await conn.fetch(
        "SELECT alpaca_order_id FROM mi_live_orders WHERE alpaca_order_id IS NOT NULL")
    claimed.update(r["alpaca_order_id"] for r in rows)
    return claimed


async def _fetch_recently_closed_tickers(conn, account_mode: str) -> set[str]:
    """R3i's guard for the same race class. Positions carry NO broker order id, so R2's
    exact-identity match is unavailable; the nearest identity is "a row for this (ticker, mode)
    just left the open set". Any close transition (stop-fill finalize, full exit, sync_positions)
    can race the scan exactly like the 10:00 cleanup raced CLSK: broker position snapshot taken
    before the row flipped 'closed' → the open-rows check reads a tracked position as untracked.
    A row whose closed_at is inside the claim window claims its ticker; the claim EXPIRES after
    _RECENT_CLOSE_CLAIM_MINUTES, so a position that genuinely persists (mirror truly wrong) is
    proposed 1-2 cycles later — DELAYED, never blinded — and D1 detection (unchanged, keyed on
    open rows) already pages it in real time regardless.

    On 'cancelled' rows: MOSTLY they set no closed_at (measured 2026-07-26: 41 of 45 NULL), which
    is the sensible shape — a cancelled unfilled entry holds no position, so it should not claim
    one. The 4 exceptions do claim their ticker for the window. That is deliberate-safe rather
    than a bug: an extra claim only DELAYS a dry-run proposal by a cycle, whereas a missing claim
    is the false positive this guard exists to stop. Do not "fix" it by filtering status without
    re-checking that direction.

    NOW() and closed_at both come from the DB clock — no client tz involved (the recurring
    tz-bug class)."""
    rows = await conn.fetch(
        """SELECT DISTINCT ticker FROM mi_live_trades
           WHERE account_mode = $1 AND closed_at > NOW() - make_interval(mins => $2)""",
        account_mode, _RECENT_CLOSE_CLAIM_MINUTES)
    return {r["ticker"] for r in rows}


async def _handle_r2_r3i(conn, account_mode: str, mode: str, open_orders: list, positions: list,
                         db_rows: list) -> int:
    """R2 (untracked apollo BUY entry) + R3i (untracked position) — reconstruction. Today these are
    PROPOSAL-ONLY (dry-run): the reconstruction contract (§3) is emitted for operator review; the
    live write waits for real observations + sign-off (spec: don't build authority for a
    zero-observation case). Returns the count proposed.

    Race-safety (the CLSK 2026-07-14 false R2): "untracked" is decided against the tickers of OPEN
    rows AND the order ids of ANY-status rows (_fetch_claimed_order_ids) — a row mid-transition
    (10:00/EOD cleanup, /pause, stop-fill finalize) still claims its order id, so a DB-side status
    flip racing the scan can never be read as a mirror gap. R3i, which has no order id to match,
    uses the recently-closed-ticker claim (_fetch_recently_closed_tickers) instead. The in-flight
    submission window is already safe: submit_entry mutates an EXISTING row whose pre-submission
    status ('confirmed') is in OPEN_POSITION_STATUSES, so tracked_tickers covers it."""
    tracked_tickers = {r["ticker"] for r in db_rows}
    claimed_order_ids = await _fetch_claimed_order_ids(conn, account_mode)
    recently_closed = await _fetch_recently_closed_tickers(conn, account_mode)
    acted = 0

    # R2 — broker apollo BUY orders (unfilled) with no open DB row for the ticker
    for o in open_orders:
        if acted >= PER_CYCLE_CAP:
            return acted
        coid = o.get("client_order_id") or ""
        side = (o.get("side") or "").lower()
        if not coid.startswith(f"apollo_{account_mode}_") or side != "buy":
            continue
        ticker = o["symbol"]
        if ticker in tracked_tickers:
            continue
        if o["id"] in claimed_order_ids:
            # The mirror references this exact order id somewhere (any status) — a row
            # mid-cleanup/mid-close, NOT an untracked order (CLSK 2026-07-14). Not a finding;
            # no audit row (same silence as the tracked_tickers skip above).
            continue
        parsed = parse_coid(coid)
        if not parsed:
            continue
        ok, reason = await validate_coid(parsed, account_mode=account_mode, symbol=ticker)
        sig = _signature(account_mode, "r2", ticker, o["id"])
        if await _already_seen(conn, sig):
            continue
        if not ok:
            await _emit(INGEST_REJECTED, sig, {"class": "r2", "ticker": ticker, "reason": reason},
                        f"{mode_prefix(account_mode)}⚠️ *Ingest R2 rejected* — {ticker}: {reason}")
            continue
        recon = {"ticker": ticker, "alert_date": parsed["alert_date"], "signal_type": parsed["strategy"],
                 "account_mode": account_mode, "entry_order_id": o["id"], "status": "order_placed",
                 "entry_price": o.get("stop_price") or o.get("limit_price"), "entry_shares": o.get("qty")}
        await _emit(INGEST_PROPOSED, sig, {"class": "r2", "action": "propose_entry_reconstruction",
                                           "reconstruction": recon},
                    f"{mode_prefix(account_mode)}📋 *Ingest R2 proposal (dry-run)* — {ticker}\n"
                    f"Untracked apollo BUY order `{o['id'][:8]}`, no DB row. Would reconstruct "
                    f"status='order_placed'. Review — R2 live is not enabled.")
        acted += 1

    # R3i — broker positions with no open DB row for the ticker
    for p in positions:
        if acted >= PER_CYCLE_CAP:
            return acted
        ticker = p.get("symbol")
        if not ticker or ticker in tracked_tickers:
            continue
        if ticker in recently_closed:
            # A row for this ticker closed inside the claim window — a close transition racing
            # the scan (the CLSK race class), not an untracked position. The claim expires in
            # _RECENT_CLOSE_CLAIM_MINUTES; a position that genuinely persists proposes then.
            continue
        sig = _signature(account_mode, "r3", ticker, None)
        if await _already_seen(conn, sig):
            continue
        recon = {"ticker": ticker, "account_mode": account_mode, "status": "filled",
                 "entry_price": p.get("avg_entry_price"), "entry_shares": p.get("qty"),
                 "remaining_shares": p.get("qty")}
        await _emit(INGEST_PROPOSED, sig, {"class": "r3i", "action": "propose_position_reconstruction",
                                           "reconstruction": recon,
                                           "note": "R3i has never been observed; dry-run only per spec"},
                    f"{mode_prefix(account_mode)}📋 *Ingest R3i proposal (dry-run)* — {ticker}\n"
                    f"Untracked broker position ({p.get('qty')} sh), no DB row. Would reconstruct "
                    f"status='filled'. Review — R3i live is NOT built (zero-observation case).")
        acted += 1
    return acted


# ───────────────────────────────────── entry point ───────────────────────────────────
async def run_ingest(account_mode: str, positions: list, open_orders: list, db_rows: list,
                     *, mode: str | None = None) -> int:
    """Reconcile the broker→DB mirror direction. Called by detect_coverage_drift AFTER detection
    completes, in its OWN guard (a throw here must never abort detection). Reuses the cycle's
    already-fetched broker/DB reads. Returns the total count acted (proposed or mutated); 0 when
    the toggle is 'off'. LIVE mutations are R1-only today and capped at PER_CYCLE_CAP; R2/R3i add
    dry-run PROPOSALS only, each capped independently (so the dry-run total can reach ~1.5× the cap —
    cosmetic while R2/R3 have no live write; thread a shared budget here when they gain one)."""
    if mode is None:
        mode = await get_ingest_mode()
    if mode == "off":
        return 0
    pool = await get_pool()
    total = 0
    async with pool.acquire() as conn:
        total += await _handle_r1(conn, account_mode, mode, db_rows, open_orders)
        if total < PER_CYCLE_CAP:
            # NB (when R2/R3 go live): pass budget=PER_CYCLE_CAP-total so the cross-class TOTAL is
            # capped. Safe to leave today — R2/R3i only propose, live mutation stays R1-only ≤ cap.
            total += await _handle_r2_r3i(conn, account_mode, mode, open_orders, positions, db_rows)
    if total:
        logger.info(f"order_ingest[{account_mode}] mode={mode}: acted on {total} mirror gap(s)")
    return total
