"""#461 — position-cap check→insert TOCTOU race (design doc
`docs/decisions/461_toctou_cap_design_2026-07-18.md`, operator-approved).

`submit_trade_entry` reads the open-position count at STEP 2 (`_check_safeguards`)
and inserts the trade row at STEP 6 — with up to ~30 s of awaits between them
(bar-fetch retry, fade guard, spec build). Concurrent candidates (the ORB
monitor's `Semaphore(5)` + `gather`) could ALL pass STEP 2 on the same stale
count and ALL insert → cap overshoot (worst case cap+4). The fix: an
authoritative recount + INSERT (+ auto-enter confirm flip) in ONE transaction
under a per-`account_mode` `pg_advisory_xact_lock` at STEP 6.

RACE-REPRODUCTION PROOF (design test-plan item 1 — run pre-fix first):
against the PRE-fix pipeline (commit 0bbdd42) the main race test FAILED with
    assert len(db.countable("live")) == 5  →  7 == 5 is False   (cap+2 overshoot)
and the per-strategy variant FAILED with 3 == 1. Both PASS post-fix. That
fail-pre-fix run is what proves these tests actually detect the overshoot.

The FakeDB models exactly what the fix relies on: pg_advisory_xact_lock
blocking semantics (per (namespace, key) asyncio.Lock), xact scope (lock
released at transaction exit — commit OR error), row visibility after the
holder's txn ends, and ON CONFLICT DO NOTHING. Real-Postgres semantics
(cross-connection blocking, hashtext keying, commit-before-release ordering)
are proven separately in `tests/test_461_cap_lock_real_pg.py` (DSN-gated,
sibling of the #151 real-PG gate).

BYTE-PRESERVED behavior pinned here (THE LINE — no cap change):
cap VALUE (5, `MAX_CONCURRENT_LIVE_POSITIONS`), counting vocabulary
(`db.OPEN_POSITION_STATUSES`, #436 pending_confirmation exclusion), skip-reason
formats (`block:max_positions: N/5 (mode=x)` → ledger `cap_blocked` + #197
CAP+1 alert), per-account-mode isolation (paper never serializes against live).
"""
from __future__ import annotations

import asyncio
from datetime import date
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from agents.market_intelligence.db import OPEN_POSITION_STATUSES
from agents.market_intelligence.broker import entry_pipeline as ep
from agents.market_intelligence.broker import live_tracker as lt
from agents.market_intelligence.broker.skip_reasons import (
    BLOCK_MAX_POSITIONS,
    BLOCK_STRATEGY_POSITION_CAP,
    WINDOW_DUPLICATE,
)

_TODAY = date(2026, 7, 17)


# ─── Fake asyncpg pool: shared table state + real advisory-lock semantics ────


class FakeDB:
    """Shared mi_live_trades + mi_strategies state across all connections."""

    def __init__(self):
        self.rows: list[dict] = []
        self.next_id = 1
        self.locks: dict[tuple, asyncio.Lock] = {}
        self.strat_caps: dict[str, int | None] = {}  # strategy_id -> cap (missing/None = NULL)

    def countable(self, mode: str) -> list[dict]:
        return [
            r for r in self.rows
            if r["account_mode"] == mode and r["status"] in OPEN_POSITION_STATUSES
        ]

    def seed(self, n: int, mode: str = "live", status: str = "filled",
             signal_type: str = "magna53") -> None:
        for _ in range(n):
            self.rows.append({
                "id": self.next_id, "ticker": f"SEED{self.next_id}",
                "alert_date": date(2026, 7, 1), "status": status,
                "account_mode": mode, "signal_type": signal_type,
            })
            self.next_id += 1


class _FakeTxn:
    def __init__(self, conn):
        self.conn = conn

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        # xact scope: advisory locks release at transaction end — commit,
        # rollback, or error — exactly like pg_advisory_xact_lock.
        for lock in self.conn._xact_locks:
            lock.release()
        self.conn._xact_locks.clear()
        return False


class FakeConn:
    def __init__(self, db: FakeDB):
        self.db = db
        self._xact_locks: list[asyncio.Lock] = []

    def transaction(self):
        return _FakeTxn(self)

    async def fetchval(self, sql, *args):
        s = " ".join(sql.split())
        if "pg_advisory_xact_lock" in s:
            # args = (namespace, account_mode) — the SQL applies hashtext()
            # server-side, so the fake keys on the raw mode string.
            key = (args[0], args[1])
            lock = self.db.locks.setdefault(key, asyncio.Lock())
            await lock.acquire()
            self._xact_locks.append(lock)
            return None
        if "SELECT EXISTS(SELECT 1 FROM mi_live_trades" in s:
            return any(
                r["ticker"] == args[0] and r["alert_date"] == args[1]
                for r in self.db.rows
            )
        if "SELECT alert_date FROM mi_live_trades" in s:
            return None  # step-1b multi-day open-position guard: nothing held
        if "COALESCE(SUM(total_pnl)" in s:
            return 0  # daily-loss query
        if "SELECT COUNT(*) FROM mi_live_trades" in s:
            if "signal_type = $2" in s:
                mode, sig, statuses = args
                return sum(
                    1 for r in self.db.rows
                    if r["account_mode"] == mode and r["signal_type"] == sig
                    and r["status"] in statuses
                )
            mode, statuses = args
            return sum(
                1 for r in self.db.rows
                if r["account_mode"] == mode and r["status"] in statuses
            )
        if "SELECT max_concurrent_positions FROM mi_strategies" in s:
            return self.db.strat_caps.get(args[0])
        if "INSERT INTO mi_live_trades" in s:
            ticker, alert_date = args[0], args[1]
            if any(r["ticker"] == ticker and r["alert_date"] == alert_date
                   for r in self.db.rows):
                return None  # ON CONFLICT (ticker, alert_date) DO NOTHING
            row = {
                "id": self.db.next_id, "ticker": ticker, "alert_date": alert_date,
                "status": "pending_confirmation",
                "signal_type": args[14], "account_mode": args[15],
            }
            self.db.next_id += 1
            self.db.rows.append(row)
            return row["id"]
        raise AssertionError(f"FakeConn.fetchval: unhandled SQL: {s[:140]}")

    async def fetch(self, sql, *args):
        s = " ".join(sql.split())
        if "SELECT total_pnl, closed_at" in s:
            return []  # circuit-breaker window: no closed trades
        raise AssertionError(f"FakeConn.fetch: unhandled SQL: {s[:140]}")

    async def execute(self, sql, *args):
        s = " ".join(sql.split())
        if "SET status='confirmed'" in s:
            for r in self.db.rows:
                if r["id"] == args[0]:
                    r["status"] = "confirmed"
            return "UPDATE 1"
        raise AssertionError(f"FakeConn.execute: unhandled SQL: {s[:140]}")


class FakePool:
    """Every acquire() hands out a FRESH connection over the shared FakeDB —
    modelling each concurrent task holding its own pooled connection."""

    def __init__(self, db: FakeDB):
        self.db = db

    def acquire(self):
        conn = FakeConn(self.db)

        class _CM:
            async def __aenter__(_self):
                return conn

            async def __aexit__(_self, *exc):
                return False

        return _CM()


# ─── Harness: real submit_trade_entry + real _check_safeguards over FakeDB ───


def _wire(monkeypatch, db: FakeDB, *, phase: str = "live",
          live_real_enabled: bool = True, n_racers: int = 1):
    """Patch the pipeline's I/O edges (Alpaca, Telegram, audit, registry) but
    keep the REAL submit_trade_entry + REAL _check_safeguards running against
    the shared FakeDB. Returns (sent_telegrams, audit_mock).

    The bar fetch is a rendezvous barrier: every racer must clear STEP 2 (the
    stale early count) before ANY racer reaches STEP 6 — the exact interleaving
    that produces the overshoot pre-fix."""
    pool = FakePool(db)
    audit = AsyncMock()
    sent: list[str] = []

    async def _capture(msg, *a, **k):
        sent.append(msg)
        return True

    monkeypatch.setattr(ep, "get_pool", AsyncMock(return_value=pool))
    monkeypatch.setattr(ep, "log_audit_event", audit)
    monkeypatch.setattr(ep, "send_telegram_message", _capture)
    monkeypatch.setattr(ep, "current_account_mode", lambda: "paper")

    monkeypatch.setattr(lt, "get_pool", AsyncMock(return_value=pool))
    monkeypatch.setattr(lt, "LIVE_TRADING_ENABLED", True)
    monkeypatch.setattr(lt, "get_manual_halt_state", AsyncMock(return_value="off"))
    monkeypatch.setattr(lt.alpaca, "get_account",
                        AsyncMock(return_value={"equity": 100_000.0}))
    monkeypatch.setattr(lt, "_insert_skipped_trade", AsyncMock())

    import agents.market_intelligence.constants as consts
    monkeypatch.setattr(consts, "DRAWDOWN_BREAKER_PHASE", "shadow")

    import agents.market_intelligence.strategies.registry as registry
    strategy = SimpleNamespace(
        enabled=True, phase=phase, live_real_enabled=live_real_enabled,
        position_size_multiplier=1.0, strategy_id="magna53",
    )
    monkeypatch.setattr(registry, "get_strategy", AsyncMock(return_value=strategy))

    import agents.market_intelligence.exposure_family as exposure_family
    monkeypatch.setattr(exposure_family, "shadow_check_and_emit", AsyncMock())

    import agents.market_intelligence.broker.order_manager as om
    monkeypatch.setattr(om, "submit_entry",
                        AsyncMock(return_value=SimpleNamespace(id="ord-1")))

    barrier = {"arrived": 0}
    release = asyncio.Event()

    async def _gated_bar(ticker, today, strategy_label):
        barrier["arrived"] += 1
        if barrier["arrived"] >= n_racers:
            release.set()
        await release.wait()
        return {"open": 10.0, "high": 10.5, "low": 9.8}

    monkeypatch.setattr(ep, "fetch_orb_bar_with_retry", _gated_bar)
    return sent, audit


async def _spec_builder(alert_ctx, orb_bar, regime, account_mode):
    return ({
        "orb_high": 10.5, "orb_low": 9.8, "entry_price": 10.55,
        "stop_loss_price": 9.75, "shares": 10, "position_size": 105.5,
        "risk_dollars": 8.0, "risk_per_share": 0.8,
    }, None)


async def _submit(ticker: str, catalyst_quality: str = "strong") -> dict:
    return await ep.submit_trade_entry(
        alert_context={"ticker": ticker, "ep_score": 71,
                       "catalyst_quality": catalyst_quality, "gap_pct": 10.0},
        spec_builder=_spec_builder,
        regime_record=None,
        strategy_label="ORB",
        signal_type="magna53",
        today=_TODAY,
        atr_14=1.0,
        fade_midpoint_ratio=None,
    )


# ─── 1. The race reproduction (design test-plan item 1) ──────────────────────


@pytest.mark.asyncio
async def test_race_concurrent_entries_cannot_exceed_cap(monkeypatch):
    """4 countable live rows + 3 racers all past STEP 2 on the stale count.
    PRE-FIX this failed with 7 countable rows (cap+2 — the overshoot).
    POST-FIX: exactly ONE racer is admitted; the cap holds at 5."""
    db = FakeDB()
    db.seed(4, mode="live")
    sent, audit = _wire(monkeypatch, db, n_racers=3)

    results = await asyncio.wait_for(
        asyncio.gather(_submit("AAA"), _submit("BBB"), _submit("CCC")),
        timeout=10,
    )

    # THE invariant: never more countable rows than the cap.
    assert len(db.countable("live")) == 5, (
        f"cap overshoot: {len(db.countable('live'))} countable rows "
        f"(cap=5) — the STEP-6 recheck failed to serialize"
    )
    entered = [r for r in results if r["action"] == ep.ACTION_AUTO_ENTERED]
    blocked = [r for r in results if r["action"] == ep.ACTION_BLOCKED]
    assert len(entered) == 1, f"exactly one racer admitted at cap-1; got {results}"
    assert len(blocked) == 2
    # Skip-reason format byte-identical to the STEP-2 gate (ledger 'cap_blocked'
    # mapping + #197 CAP+1 alert both match on this exact shape).
    for r in blocked:
        assert r["reason"] == f"{BLOCK_MAX_POSITIONS}: 5/5 (mode=live)"
    # Observe-only race telemetry — the #461 verify-live signal.
    recheck_events = [
        c for c in audit.await_args_list if c.args[0] == "cap_recheck_blocked"
    ]
    assert len(recheck_events) == 2


@pytest.mark.asyncio
async def test_race_per_strategy_cap_covered_by_same_lock(monkeypatch):
    """#65 per-strategy recheck rides the same per-mode lock (design test-plan
    item 3). strat cap=1, 3 racers → 1 admitted, 2 blocked. PRE-FIX: all 3
    inserted (3 countable, strat-cap 1 → failed with 3 == 1)."""
    db = FakeDB()
    db.strat_caps["magna53"] = 1
    sent, audit = _wire(monkeypatch, db, n_racers=3)

    results = await asyncio.wait_for(
        asyncio.gather(_submit("AAA"), _submit("BBB"), _submit("CCC")),
        timeout=10,
    )

    assert len(db.countable("live")) == 1, (
        f"per-strategy cap overshoot: {len(db.countable('live'))} countable rows (cap=1)"
    )
    entered = [r for r in results if r["action"] == ep.ACTION_AUTO_ENTERED]
    blocked = [r for r in results if r["action"] == ep.ACTION_BLOCKED]
    assert len(entered) == 1
    assert len(blocked) == 2
    for r in blocked:
        assert r["reason"] == f"{BLOCK_STRATEGY_POSITION_CAP}: magna53 1/1 (mode=live)"


# ─── 2. Duplicate-conflict path inside the transaction (test-plan item 5) ────


@pytest.mark.asyncio
async def test_same_ticker_conflict_still_window_duplicate_no_lock_leak(monkeypatch):
    """Two same-ticker racers: ON CONFLICT DO NOTHING inside the txn still
    yields the silent WINDOW_DUPLICATE return, and the xact lock is released
    (no leak) — the loser's empty transaction commits cleanly."""
    db = FakeDB()
    sent, audit = _wire(monkeypatch, db, n_racers=2)

    results = await asyncio.wait_for(
        asyncio.gather(_submit("SAME"), _submit("SAME")), timeout=10,
    )

    actions = sorted(r["action"] for r in results)
    assert actions == sorted([ep.ACTION_AUTO_ENTERED, ep.ACTION_SKIPPED])
    dup = next(r for r in results if r["action"] == ep.ACTION_SKIPPED)
    assert dup["reason"] == WINDOW_DUPLICATE
    assert len(db.countable("live")) == 1
    lock = db.locks.get((ep._CAP_LOCK_NAMESPACE, "live"))
    assert lock is not None and not lock.locked(), "xact lock leaked past txn end"


# ─── 3. Per-account-mode isolation (#66 — paper never waits on live) ─────────


@pytest.mark.asyncio
async def test_paper_entry_never_serializes_against_live_lock(monkeypatch):
    """While the LIVE cap key is held, a paper entry must proceed immediately —
    the lock key derives from account_mode (hashtext('paper') != hashtext('live'))
    and the recounts are mode-filtered. #66 isolation preserved."""
    db = FakeDB()
    sent, audit = _wire(monkeypatch, db, phase="paper", n_racers=1)

    live_lock = db.locks.setdefault((ep._CAP_LOCK_NAMESPACE, "live"), asyncio.Lock())
    await live_lock.acquire()  # a live-mode holder mid-transaction
    try:
        result = await asyncio.wait_for(_submit("PPR"), timeout=5)
    finally:
        live_lock.release()

    assert result["action"] == ep.ACTION_AUTO_ENTERED
    assert len(db.countable("paper")) == 1
    assert len(db.countable("live")) == 0, "paper row must never count toward live"


# ─── 4. #197 CAP+1 alert parity through the recheck-blocked path ─────────────


@pytest.mark.asyncio
async def test_cap_plus_one_alert_fires_when_recheck_blocks_game_changer(monkeypatch):
    """A game_changer blocked by the STEP-6 recheck takes the SAME _skip path
    as a STEP-2 block → the #197 CAP+1 CANDIDATE Telegram still fires
    (startswith(BLOCK_MAX_POSITIONS) on the byte-identical reason)."""
    db = FakeDB()
    db.seed(4, mode="live")
    sent, audit = _wire(monkeypatch, db, n_racers=2)

    await asyncio.wait_for(
        asyncio.gather(_submit("GC1", "game_changer"), _submit("GC2", "game_changer")),
        timeout=10,
    )

    assert len(db.countable("live")) == 5
    cap_plus_one = [m for m in sent if "CAP+1 CANDIDATE" in m]
    assert len(cap_plus_one) == 1, (
        f"exactly one blocked game_changer → one CAP+1 alert; sent={sent}"
    )


# ─── 5. Vocabulary pins ──────────────────────────────────────────────────────


def test_cap_lock_namespace_is_distinct_and_int4():
    """The cap lock must never collide with the #151 per-trade exit lock, and
    must fit pg_advisory_xact_lock's int4 classid."""
    from agents.market_intelligence.broker.order_manager import _TRADE_LOCK_NAMESPACE
    assert ep._CAP_LOCK_NAMESPACE != _TRADE_LOCK_NAMESPACE
    assert 0 < ep._CAP_LOCK_NAMESPACE < 2**31


@pytest.mark.asyncio
async def test_recheck_counts_use_the_shared_open_statuses(monkeypatch):
    """#436 preserved at the recheck: 4 inert pending_confirmation proposals
    must NOT block an entry (they are not positions — OPEN_POSITION_STATUSES
    is the single counting vocabulary for BOTH the STEP-2 gate and the
    STEP-6 recheck via the shared count_open_positions helper)."""
    db = FakeDB()
    db.seed(4, mode="live", status="pending_confirmation")
    sent, audit = _wire(monkeypatch, db, n_racers=1)

    result = await asyncio.wait_for(_submit("OKAY"), timeout=5)

    assert result["action"] == ep.ACTION_AUTO_ENTERED
    assert len(db.countable("live")) == 1  # only the new confirmed row counts
