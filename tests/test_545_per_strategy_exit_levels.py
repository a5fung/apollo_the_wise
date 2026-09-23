"""#545 (2026-09-06) — per-strategy exit LEVELS, shipped DARK.

Two mechanisms, both defaulted to exactly today's behaviour:

  1. The intraday partial's MULTIPLE is per-strategy (`mi_strategies.profit_trigger_r`,
     NULL = the global `constants.PROFIT_TRIGGER_R`). The SWITCH stays global — `None`
     still means "no intraday partial anywhere, day-3/5 ladder back" (test_profit_trigger_508
     pins that half). The defect this fixes: scan_profit_triggers had NO signal_type
     predicate, so raising the constant for MAGNA53 (the only strategy the #545 evidence
     covers) would have moved every other strategy's partial too.

  2. A PRICE-ARMED breakeven (`mi_strategies.breakeven_arm_r`, NULL = OFF): the protective
     stop moves to entry when the position trades at entry + N x R, whether or not a partial
     has fired. It targets the FULL-position OTO stop leg via an atomic price-only replace.

Every test here drives the REAL scan functions over a query-routing fake pool. Each carries a
MUTATION TARGET naming the defect it kills; the byte-identity guards were proven red by
deleting the mechanism (see the commit).
"""
from __future__ import annotations

import ast
import inspect
import json
import pathlib
from contextlib import ExitStack
from datetime import datetime, timezone
from unittest.mock import AsyncMock, patch

import pytest

from agents.market_intelligence.broker import order_manager as om

SRC = pathlib.Path("agents/market_intelligence/broker/order_manager.py").read_text()

ENTRY = 100.0
ORB_LOW = 95.0            # R = 5 (the ORB frame) -> +2R = 110, +3R = 115, +8R = 140
PLACED_STOP = 90.0        # the era-C 2R stop
OTO_LEG_ID = "oto_leg_full_position"
NEW_STOP_ID = "successor_stop_at_entry"


# ─────────────────────────── query-routing fake pool ───────────────────────────

class _Conn:
    def __init__(self, harness):
        self.h = harness

    async def fetch(self, sql, *a, **k):
        self.h.fetches.append(sql)
        if "FROM mi_strategies" in sql:
            return self.h.override_rows
        if "FROM mi_live_trades" in sql:
            return self.h.trade_rows
        return []

    async def fetchval(self, sql, *a, **k):
        if "MAX(high)" in sql:
            return self.h.hi
        if "pg_try_advisory_lock" in sql:
            return self.h.lock_acquired
        return True

    async def fetchrow(self, sql, *a, **k):
        return None

    async def execute(self, sql, *a, **k):
        self.h.executes.append((sql, a))


class _Acquire:
    """pool.acquire() is used BOTH as `async with pool.acquire() as conn` and as
    `conn = await pool.acquire(timeout=...)` (the advisory try-lock) — support both."""

    def __init__(self, conn):
        self._conn = conn

    def __await__(self):
        async def _c():
            return self._conn
        return _c().__await__()

    async def __aenter__(self):
        return self._conn

    async def __aexit__(self, *exc):
        return False


class _Pool:
    def __init__(self, harness):
        self._conn = _Conn(harness)

    def acquire(self, *a, **k):
        return _Acquire(self._conn)

    async def release(self, conn):
        return None


class _NoonET(datetime):
    @classmethod
    def now(cls, tz=None):
        return datetime(2026, 9, 8, 12, 0, tzinfo=tz)


class Harness:
    def __init__(self, *, trade_rows, override_rows, hi, lock_acquired=True):
        self.trade_rows = trade_rows
        self.override_rows = override_rows
        self.hi = hi
        self.lock_acquired = lock_acquired
        self.fetches: list[str] = []
        self.executes: list[tuple] = []
        self.audits: list[tuple] = []
        self.sent: list[str] = []

    async def audit(self, evt, summary="", detail=""):
        self.audits.append((evt, summary, detail))

    async def send(self, msg, *a, **k):
        self.sent.append(msg)
        return True

    def trade_updates(self):
        return [(sql, args) for sql, args in self.executes if "UPDATE mi_live_trades" in sql]


def _trade(**over):
    row = {
        "id": 41, "ticker": "TSTX", "entry_price": ENTRY,
        "hard_stop": PLACED_STOP, "stop_price": PLACED_STOP,
        "stop_order_id": OTO_LEG_ID, "orb_low": ORB_LOW,
        "signal_type": "magna53", "remaining_shares": 30.0,
        "partial_taken": False, "breakeven_active": False,
        "filled_at": datetime(2026, 9, 8, 13, 31, tzinfo=timezone.utc),
        "account_mode": "live",
    }
    row.update(over)
    return row


def _override(signal_type="magna53", profit_trigger_r=None, breakeven_arm_r=None):
    return {"signal_type": signal_type, "profit_trigger_r": profit_trigger_r,
            "breakeven_arm_r": breakeven_arm_r}


def _order(status="new", stop_price=PLACED_STOP, oid=OTO_LEG_ID, order_class="oto"):
    return {"id": oid, "status": status, "stop_price": stop_price, "order_class": order_class,
            "qty": 30.0, "filled_qty": 0}


# ═══════════════════════════════ 1. the resolvers ═══════════════════════════════

def test_no_override_returns_the_global_multiple_exactly():
    """THE byte-identity guard for the partial. MUTATION TARGET: a resolver that returns a
    hard-coded level, ignores `global_r`, or treats {} as anything but "use the global"."""
    assert om.resolve_profit_trigger_r("magna53", {}, 2.0) == 2.0
    assert om.resolve_profit_trigger_r("9m_day2", {}, 2.0) == 2.0
    assert om.resolve_profit_trigger_r("magna53", None, 2.0) == 2.0
    assert om.resolve_profit_trigger_r("magna53", {}, None) is None
    # An override row that carries only the OTHER column is still "no override".
    ov = {"magna53": {"profit_trigger_r": None, "breakeven_arm_r": 3.0}}
    assert om.resolve_profit_trigger_r("magna53", ov, 2.0) == 2.0


def test_override_changes_only_that_strategy():
    """MUTATION TARGET: a resolver keyed on anything but signal_type, or one that applies the
    first override it finds to every strategy (the very defect this build removes)."""
    ov = {"magna53": {"profit_trigger_r": 8.0, "breakeven_arm_r": None}}
    assert om.resolve_profit_trigger_r("magna53", ov, 2.0) == 8.0
    assert om.resolve_profit_trigger_r("9m_day2", ov, 2.0) == 2.0
    assert om.resolve_profit_trigger_r(None, ov, 2.0) == 2.0


def test_non_positive_or_garbage_override_falls_back_to_the_global():
    """0 x R would fire at entry — a typo must never read as "at once". The DB CHECK rejects
    it; this is the code-side belt. MUTATION TARGET: dropping the `> 0` guard."""
    for bad in (0, 0.0, -1, "nope"):
        ov = {"magna53": {"profit_trigger_r": bad}}
        assert om.resolve_profit_trigger_r("magna53", ov, 2.0) == 2.0


def test_breakeven_arm_is_off_unless_a_strategy_sets_it():
    """There is NO global default for the arm — {} means OFF for everyone (the dark claim).
    MUTATION TARGET: a default level, or a non-positive value treated as armed."""
    assert om.resolve_breakeven_arm_r("magna53", {}) is None
    assert om.resolve_breakeven_arm_r("magna53", None) is None
    ov = {"magna53": {"profit_trigger_r": None, "breakeven_arm_r": 3.0}}
    assert om.resolve_breakeven_arm_r("magna53", ov) == 3.0
    assert om.resolve_breakeven_arm_r("9m_day2", ov) is None
    for bad in (0, -2, "x"):
        assert om.resolve_breakeven_arm_r("magna53", {"magna53": {"breakeven_arm_r": bad}}) is None


@pytest.mark.asyncio
async def test_db_reader_keys_by_signal_type_and_skips_foreign_rows():
    """`db.get_strategy_exit_overrides` — the one SQL site. Rows lacking the columns (a test
    double feeding trade rows back through the same conn) are skipped, never raised on.
    MUTATION TARGET: keying by strategy_id (trades carry signal_type), or raising on a
    foreign row (which would take the whole scan down on the fake pools other tests use)."""
    from agents.market_intelligence import db

    class _C:
        async def fetch(self, sql):
            assert "FROM mi_strategies" in sql and "signal_type" in sql
            return [_override("magna53", 8.0, None), _override("wick_fill", None, 3.0),
                    _trade()]  # <- a trade row: no override columns → skipped
    out = await db.get_strategy_exit_overrides(conn=_C())
    assert out == {
        "magna53": {"profit_trigger_r": 8.0, "breakeven_arm_r": None},
        "wick_fill": {"profit_trigger_r": None, "breakeven_arm_r": 3.0},
    }


def test_schema_adds_exactly_the_columns_the_reader_selects():
    """The ALTERs and the SELECT must name the same columns, and each column is CHECKed
    positive at the DB. MUTATION TARGET: renaming one side, or dropping a CHECK."""
    dbsrc = pathlib.Path("agents/market_intelligence/db.py").read_text()
    for col in ("profit_trigger_r", "breakeven_arm_r"):
        assert f"ADD COLUMN IF NOT EXISTS {col} NUMERIC" in dbsrc, col
        assert f"CHECK ({col} IS NULL OR {col} > 0)" in dbsrc, col
    sel = inspect.getsource(__import__("agents.market_intelligence.db", fromlist=["x"])
                            .get_strategy_exit_overrides)
    assert "SELECT signal_type, profit_trigger_r, breakeven_arm_r FROM mi_strategies" in sel


# ═════════════════ 2. scan_profit_triggers — the multiple is per-strategy ═════════════════

async def _run_partial_scan(h: Harness, *, global_r=2.0, overrides_raise=False,
                            announced=True):
    fake_exec = AsyncMock(return_value=True)
    with ExitStack() as st:
        st.enter_context(patch("agents.market_intelligence.constants.PROFIT_TRIGGER_R", global_r))
        st.enter_context(patch.object(om, "get_pool", AsyncMock(return_value=_Pool(h))))
        st.enter_context(patch.object(om, "datetime", _NoonET))
        st.enter_context(patch.object(om, "execute_partial_exit", fake_exec))
        st.enter_context(patch.object(om, "_profit_take_resting_limit_enabled",
                                      AsyncMock(return_value=True)))
        st.enter_context(patch.object(om, "_profit_trigger_already_announced",
                                      AsyncMock(return_value=announced)))
        st.enter_context(patch.object(om, "send_telegram_message", h.send))
        st.enter_context(patch.object(om, "log_audit_event", h.audit))
        if overrides_raise:
            st.enter_context(patch("agents.market_intelligence.db.get_strategy_exit_overrides",
                                   AsyncMock(side_effect=RuntimeError("db down"))))
        results = await om.scan_profit_triggers()
    return fake_exec, results


@pytest.mark.asyncio
async def test_partial_with_no_override_fires_at_the_global_2r_target():
    """Byte identity, end to end: no override row → the target is entry + 2.0 x R = 110,
    exactly as before this build. MUTATION TARGET: any change to the resolved level when
    mi_strategies carries nothing (e.g. reading the wrong column, a default of 8)."""
    h = Harness(trade_rows=[_trade()], override_rows=[], hi=110.0)
    fake_exec, results = await _run_partial_scan(h)
    fake_exec.assert_awaited_once_with(41, 10, limit_price=110.0, trigger=None)
    assert results == [{"ticker": "TSTX", "action": "partial_submitted", "shares": 10}]


@pytest.mark.asyncio
async def test_partial_override_moves_magna53_to_8r_and_nothing_else():
    """MUTATION TARGET: `target = entry + PROFIT_TRIGGER_R * r` (the global creeping back),
    or an override applied without the signal_type key."""
    ov = [_override("magna53", profit_trigger_r=8.0)]
    # 110 (the old 2R) must NOT fire for magna53 any more...
    h = Harness(trade_rows=[_trade()], override_rows=ov, hi=110.0)
    fake_exec, results = await _run_partial_scan(h)
    fake_exec.assert_not_awaited()
    assert results == []
    # ...140 (= entry + 8 x 5) does, at the 8R price.
    h = Harness(trade_rows=[_trade()], override_rows=ov, hi=140.0)
    fake_exec, _ = await _run_partial_scan(h)
    fake_exec.assert_awaited_once_with(41, 10, limit_price=140.0, trigger=None)
    # A 9m_day2 row (stop 97 = its own R frame, R=3) is untouched by the magna53 row:
    # fires at its 2R = 106 exactly as today.
    nine = _trade(id=42, ticker="NINE", signal_type="9m_day2", hard_stop=97.0, stop_price=97.0)
    h = Harness(trade_rows=[nine], override_rows=ov, hi=106.0)
    fake_exec, _ = await _run_partial_scan(h)
    fake_exec.assert_awaited_once_with(42, 10, limit_price=106.0, trigger=None)


@pytest.mark.asyncio
async def test_partial_announces_and_audits_the_resolved_multiple_not_the_global():
    """The operator reads "8R above" — not "2R above" — when the override is 8. The
    execute_partial_exit mock never flips `delivered`, so the scan's own fallback Telegram
    goes out and its text is asserted. MUTATION TARGET: leaving `PROFIT_TRIGGER_R` in the
    Telegram text, the trigger context, or the audit summary/detail."""
    ov = [_override("magna53", profit_trigger_r=8.0)]
    h = Harness(trade_rows=[_trade()], override_rows=ov, hi=140.0)
    await _run_partial_scan(h, announced=False)
    assert len(h.sent) == 1 and "8R above $100.00" in h.sent[0], h.sent
    assert "2R above" not in h.sent[0]
    fired = [a for a in h.audits if a[0] == "profit_trigger_fired"]
    assert fired and "8R target" in fired[0][1]
    assert json.loads(fired[0][2])["r_multiple"] == 8.0


@pytest.mark.asyncio
async def test_partial_runs_on_the_global_when_the_override_read_fails():
    """A DB hiccup must never move a live partial's level — fail to TODAY.
    MUTATION TARGET: letting the read raise out of the scan, or defaulting to OFF."""
    h = Harness(trade_rows=[_trade()], override_rows=[], hi=110.0)
    fake_exec, _ = await _run_partial_scan(h, overrides_raise=True)
    fake_exec.assert_awaited_once_with(41, 10, limit_price=110.0, trigger=None)


@pytest.mark.asyncio
async def test_global_off_switch_still_wins_over_a_per_strategy_override():
    """`PROFIT_TRIGGER_R = None` = no intraday partial ANYWHERE — an override cannot switch
    it on for one strategy (the 3:45 ladder is then the owner, and it stands down on the
    same global read). MUTATION TARGET: gating the early return on the overrides."""
    ov = [_override("magna53", profit_trigger_r=8.0)]
    h = Harness(trade_rows=[_trade()], override_rows=ov, hi=200.0)
    fake_exec, results = await _run_partial_scan(h, global_r=None)
    fake_exec.assert_not_awaited()
    assert results == [] and h.fetches == [], "OFF must short-circuit before any DB read"


def test_the_stand_down_in_live_tracker_stays_a_global_read():
    """The switch is global, so the 3:45 ladder's stand-down must keep reading the global —
    a per-strategy read there would let both partial paths act on the same position.
    (Also pinned by test_profit_trigger_508; restated here because THIS build is the one
    that made the multiple per-strategy and deliberately did not touch the switch.)"""
    src = pathlib.Path("agents/market_intelligence/broker/live_tracker.py").read_text()
    assert "skip_partial_decision=bool(PROFIT_TRIGGER_R)" in src


# ═════════════════════ 3. scan_breakeven_arms — the price-armed breakeven ═════════════════════

async def _run_arm_scan(h: Harness, *, get_order, replace_order=None, alerted=False,
                        polls=2):
    replace = replace_order or AsyncMock(return_value=_order(oid=NEW_STOP_ID, stop_price=ENTRY))
    set_ptr = AsyncMock(return_value=True)
    coverage = AsyncMock(return_value="🛡 re-placed")
    with ExitStack() as st:
        st.enter_context(patch.object(om, "get_pool", AsyncMock(return_value=_Pool(h))))
        st.enter_context(patch.object(om, "datetime", _NoonET))
        st.enter_context(patch.object(om.alpaca, "get_order", get_order))
        st.enter_context(patch.object(om.alpaca, "replace_order", replace))
        st.enter_context(patch.object(om.alpaca, "make_client_order_id",
                                      lambda *a, **k: "live-magna53-TSTX-coid"))
        st.enter_context(patch.object(om.alpaca, "get_position",
                                      AsyncMock(return_value={"qty": 30.0})))
        st.enter_context(patch.object(om, "set_stop_order_id", set_ptr))
        st.enter_context(patch.object(om, "_ensure_stop_coverage", coverage))
        st.enter_context(patch.object(om, "_breakeven_arm_already_alerted",
                                      AsyncMock(return_value=alerted)))
        st.enter_context(patch.object(om, "send_telegram_message", h.send))
        st.enter_context(patch.object(om, "log_audit_event", h.audit))
        st.enter_context(patch.object(om, "_BREAKEVEN_ARM_VERIFY_POLLS", polls))
        st.enter_context(patch.object(om, "_BREAKEVEN_ARM_VERIFY_INTERVAL_S", 0))
        results = await om.scan_breakeven_arms()
    return {"results": results, "replace": replace, "set_ptr": set_ptr, "coverage": coverage}


def _live_leg(stop_price=PLACED_STOP):
    """get_order fake: the OTO leg is live at `stop_price`; the successor is live at entry."""
    async def _go(order_id, account_mode=None, **k):
        if order_id == OTO_LEG_ID:
            return _order(stop_price=stop_price)
        if order_id == NEW_STOP_ID:
            return _order(oid=NEW_STOP_ID, stop_price=ENTRY)
        return None
    return AsyncMock(side_effect=_go)


ARMED = [_override("magna53", breakeven_arm_r=3.0)]


@pytest.mark.asyncio
async def test_dark_with_no_override_reads_no_positions_and_calls_no_broker():
    """THE dark claim for the arm: every `breakeven_arm_r` NULL → [] before the position
    query, before any broker call. MUTATION TARGET: a default arm level; querying
    positions before checking for an armed strategy."""
    get_order = _live_leg()
    h = Harness(trade_rows=[_trade()], override_rows=[], hi=999.0)
    out = await _run_arm_scan(h, get_order=get_order)
    assert out["results"] == []
    assert not any("FROM mi_live_trades" in q for q in h.fetches), "positions were read"
    get_order.assert_not_awaited()
    out["replace"].assert_not_awaited()
    assert h.executes == [] and h.sent == []
    # A row whose ONLY override is the partial multiple must not arm anything either.
    h = Harness(trade_rows=[_trade()], override_rows=[_override("magna53", 8.0, None)], hi=999.0)
    out = await _run_arm_scan(h, get_order=get_order)
    assert out["results"] == [] and not any("FROM mi_live_trades" in q for q in h.fetches)


@pytest.mark.asyncio
async def test_arms_with_no_partial_taken_the_previously_impossible_case():
    """entry 100, ORB R 5, arm at +3R = 115: a high of 115.5 with NO partial taken moves
    the stop to entry — the case that did not exist while breakeven lived inside
    execute_partial_exit. MUTATION TARGET: gating on partial_taken; framing R off the
    placed 2R stop (level 130 → no arm at 115.5); a level below +3R (the 114.99 test)."""
    h = Harness(trade_rows=[_trade(partial_taken=False)], override_rows=ARMED, hi=115.5)
    out = await _run_arm_scan(h, get_order=_live_leg())
    assert out["results"] == [{"ticker": "TSTX", "action": "armed", "new_stop_id": NEW_STOP_ID}]
    out["replace"].assert_awaited_once()
    args, kwargs = out["replace"].await_args
    assert args == (OTO_LEG_ID,)
    assert kwargs["stop_price"] == ENTRY and kwargs["account_mode"] == "live"
    assert kwargs["client_order_id"] == "live-magna53-TSTX-coid", "mode-bound COID at the submission site"
    # pointer + price + flag written atomically, ONCE, after the successor read back live
    ups = h.trade_updates()
    assert len(ups) == 1
    sql, args = ups[0]
    assert "stop_order_id = $2" in sql and "stop_price = $3" in sql and "breakeven_active = TRUE" in sql
    assert args == (41, NEW_STOP_ID, ENTRY)
    assert [a[0] for a in h.audits if a[0].startswith("breakeven_arm")] == ["breakeven_armed"]
    assert len(h.sent) == 1 and "Breakeven armed" in h.sent[0] and "3R above" in h.sent[0]


@pytest.mark.asyncio
async def test_does_not_arm_below_the_level():
    """Negative control one cent under +3R: no broker read, no replace, no write.
    MUTATION TARGET: `<=` vs `<` drift, or a level computed off entry alone."""
    get_order = _live_leg()
    h = Harness(trade_rows=[_trade()], override_rows=ARMED, hi=114.99)
    out = await _run_arm_scan(h, get_order=get_order)
    assert out["results"] == []
    get_order.assert_not_awaited()
    out["replace"].assert_not_awaited()
    assert h.executes == [] and h.sent == []


@pytest.mark.asyncio
async def test_raise_only_never_lowers_a_stop_already_above_entry():
    """A trailed position whose BROKER stop sits at 101.50 (> entry): no replace — the arm
    can only ever raise. The flag is still set so the daily pass composes via max() and
    this scan stops re-reading the trade. Decided against the BROKER stop, not the DB
    (the DB says 90). MUTATION TARGET: comparing against `stop_price` from the row;
    replacing unconditionally; `min()`."""
    h = Harness(trade_rows=[_trade(stop_price=PLACED_STOP)], override_rows=ARMED, hi=120.0)
    out = await _run_arm_scan(h, get_order=_live_leg(stop_price=101.50))
    assert out["results"] == [{"ticker": "TSTX", "action": "already_at_breakeven"}]
    out["replace"].assert_not_awaited()
    ups = h.trade_updates()
    assert len(ups) == 1 and ups[0][0].strip() == \
        "UPDATE mi_live_trades SET breakeven_active = TRUE WHERE id = $1"
    assert ups[0][1] == (41,)
    assert "stop_price" not in ups[0][0], "a flag-only write must not touch the price"
    assert h.sent == [], "nothing moved — nothing to announce"


@pytest.mark.asyncio
async def test_idempotent_no_second_broker_replace():
    """Two layers. (1) The SQL never re-selects an armed trade. (2) Even with the flag lost,
    a broker stop already AT entry takes the flag-only path — never a second replace.
    MUTATION TARGET: dropping the `breakeven_active` predicate; `>` instead of `>=`
    at the already-at-entry check."""
    src = ast.get_source_segment(SRC, next(
        n for n in ast.walk(ast.parse(SRC))
        if isinstance(n, ast.AsyncFunctionDef) and n.name == "scan_breakeven_arms"))
    assert "COALESCE(breakeven_active, FALSE) = FALSE" in src
    h = Harness(trade_rows=[_trade(breakeven_active=False)], override_rows=ARMED, hi=120.0)
    out = await _run_arm_scan(h, get_order=_live_leg(stop_price=ENTRY))
    out["replace"].assert_not_awaited()
    assert out["results"] == [{"ticker": "TSTX", "action": "already_at_breakeven"}]


@pytest.mark.asyncio
async def test_targets_the_full_position_stop_leg_price_only():
    """It arms BEFORE any partial, so the replace targets `mi_live_trades.stop_order_id` —
    the full-position OTO leg — with a PRICE-ONLY replace (no qty kwarg: quantity never
    changes, so it cannot race the share reservation, and a rejection is a no-op). It must
    not route through execute_partial_exit's reduced-stop path, nor cancel-then-new.
    MUTATION TARGET: passing qty; calling update_stop / _reduce_stop_via_cancel_new /
    execute_partial_exit / place_stop_order from the arm."""
    h = Harness(trade_rows=[_trade(remaining_shares=30.0)], override_rows=ARMED, hi=120.0)
    out = await _run_arm_scan(h, get_order=_live_leg())
    args, kwargs = out["replace"].await_args
    assert args[0] == OTO_LEG_ID
    assert "qty" not in kwargs, "price-only: a qty replace on an OTO leg is rejected (42210000)"
    # the mi_live_orders record carries the FULL remaining quantity
    orders = [(s, a) for s, a in h.executes if "INSERT INTO mi_live_orders" in s]
    assert len(orders) == 1 and orders[0][1][3] == 30.0 and orders[0][1][4] == ENTRY
    tree = ast.parse(SRC)
    for fn in ("scan_breakeven_arms", "_arm_breakeven_on_full_stop"):
        body = ast.get_source_segment(SRC, next(
            n for n in ast.walk(tree) if isinstance(n, ast.AsyncFunctionDef) and n.name == fn))
        for banned in ("execute_partial_exit(", "_reduce_stop_via_cancel_new(",
                       "_replace_stop_leg_via_cancel_new(", "update_stop(", "place_stop_order(",
                       "cancel_order("):
            assert banned not in body, f"{fn} must not call {banned}"
        assert "replace_order(" in body or fn == "scan_breakeven_arms"


@pytest.mark.asyncio
async def test_rejected_replace_leaves_the_db_untouched_and_alerts_once():
    """A rejected price-only replace is atomic — the old stop stays live. Nothing is written,
    the audit row lands, the operator hears ONCE (not every 5 minutes), and the next poll
    retries. MUTATION TARGET: writing the flag on rejection (which would silently END the
    retries with the stop still at 90); Telegramming on every cycle."""
    replace = AsyncMock(side_effect=RuntimeError("42210000 stop above market"))
    h = Harness(trade_rows=[_trade()], override_rows=ARMED, hi=120.0)
    out = await _run_arm_scan(h, get_order=_live_leg(), replace_order=replace)
    assert out["results"] == [{"ticker": "TSTX", "action": "arm_rejected"}]
    assert h.trade_updates() == [], "a rejected replace must write NOTHING"
    out["set_ptr"].assert_not_awaited()
    assert [a[0] for a in h.audits if a[0].startswith("breakeven_arm")] == ["breakeven_arm_rejected"]
    assert len(h.sent) == 1 and "rejected" in h.sent[0] and "still protected" in h.sent[0]
    # already announced today → audit again, no second Telegram
    h2 = Harness(trade_rows=[_trade()], override_rows=ARMED, hi=120.0)
    await _run_arm_scan(h2, get_order=_live_leg(), replace_order=replace, alerted=True)
    assert h2.sent == [] and [a[0] for a in h2.audits] == ["breakeven_arm_rejected"]


@pytest.mark.asyncio
async def test_dead_successor_nulls_the_pointer_and_reprotects_loudly():
    """The replace consumed the old leg and the successor read back DEAD → the position is
    naked: pointer nulled (broker-confirmed terminal read), re-protect to broker truth
    post-lock, 🚨 Telegram. Never the flag write. MUTATION TARGET: treating "dead" as
    "unknown" (pointer persisted to a dead order); skipping the re-protect."""
    async def _go(order_id, account_mode=None, **k):
        if order_id == OTO_LEG_ID:
            return _order()
        return _order(oid=NEW_STOP_ID, status="rejected", stop_price=ENTRY)
    h = Harness(trade_rows=[_trade()], override_rows=ARMED, hi=120.0)
    out = await _run_arm_scan(h, get_order=AsyncMock(side_effect=_go))
    assert out["results"] == [{"ticker": "TSTX", "action": "arm_failed_successor_dead"}]
    out["set_ptr"].assert_awaited_once_with(41, None, reason="breakeven_arm_failed",
                                            account_mode="live")
    out["coverage"].assert_awaited_once()
    assert h.trade_updates() == []
    assert any("🚨" in m and "FAILED" in m for m in h.sent)


@pytest.mark.asyncio
async def test_unverified_successor_persists_the_pointer_but_withholds_price_and_flag():
    """Still pending after the verify budget: the successor LIKELY lives, so the pointer is
    persisted (best broker truth), but stop_price and the flag are WITHHELD — the DB
    understating protection is the safe direction (#548 idiom). The next poll's broker
    read then converges via the flag-only path. MUTATION TARGET: writing the 3-column
    UPDATE on an unconfirmed successor."""
    async def _go(order_id, account_mode=None, **k):
        if order_id == OTO_LEG_ID:
            return _order()
        return _order(oid=NEW_STOP_ID, status="pending_replace", stop_price=ENTRY)
    h = Harness(trade_rows=[_trade()], override_rows=ARMED, hi=120.0)
    out = await _run_arm_scan(h, get_order=AsyncMock(side_effect=_go))
    assert out["results"] == [{"ticker": "TSTX", "action": "arm_unverified",
                               "new_stop_id": NEW_STOP_ID}]
    out["set_ptr"].assert_awaited_once_with(41, NEW_STOP_ID, reason="breakeven_arm_unverified",
                                            account_mode="live")
    assert h.trade_updates() == []
    assert len(h.sent) == 1 and "not confirmed live" in h.sent[0]


@pytest.mark.asyncio
async def test_partial_in_flight_or_unreadable_stop_touches_nothing():
    """A partial holding the trade lock, or a stop the broker cannot confirm live, defers —
    no replace, no write, audit only (transient → mi_audit_log, not Telegram).
    MUTATION TARGET: proceeding without the lock; treating an unreadable stop as 90."""
    h = Harness(trade_rows=[_trade()], override_rows=ARMED, hi=120.0, lock_acquired=False)
    out = await _run_arm_scan(h, get_order=_live_leg())
    assert out["results"] == [{"ticker": "TSTX", "action": "skipped_partial_in_flight"}]
    out["replace"].assert_not_awaited()
    assert h.trade_updates() == [] and h.sent == []
    h = Harness(trade_rows=[_trade()], override_rows=ARMED, hi=120.0)
    out = await _run_arm_scan(h, get_order=AsyncMock(return_value=None))
    assert out["results"] == [{"ticker": "TSTX", "action": "skipped_stop_unreadable"}]
    out["replace"].assert_not_awaited()
    assert h.trade_updates() == [] and h.sent == []
    assert [a[0] for a in h.audits] == ["breakeven_arm_skipped"]


@pytest.mark.asyncio
async def test_a_strategy_without_an_arm_level_is_skipped_even_when_another_is_armed():
    """magna53 armed at 3R must not arm a 9m_day2 position. MUTATION TARGET: applying the
    first armed level to every row."""
    nine = _trade(id=42, ticker="NINE", signal_type="9m_day2", hard_stop=97.0, stop_price=97.0)
    h = Harness(trade_rows=[nine], override_rows=ARMED, hi=500.0)
    get_order = _live_leg()
    out = await _run_arm_scan(h, get_order=get_order)
    assert out["results"] == []
    get_order.assert_not_awaited()


# ═══════════════════════════════ 4. wiring + registries ═══════════════════════════════

def test_scheduler_runs_the_arm_after_the_partial_in_its_own_try():
    """The arm runs in `_track_open_position_extremes_job` AFTER scan_profit_triggers and
    inside a try block that does NOT contain the partial — an exception out of the new
    path can never starve today's live partial. MUTATION TARGET: removing the call
    (the mechanism is dead), moving it before the partial, or sharing the try."""
    src = pathlib.Path("agents/market_intelligence/scheduler.py").read_text()
    tree = ast.parse(src)
    job = next(n for n in ast.walk(tree)
               if isinstance(n, ast.AsyncFunctionDef) and n.name == "_track_open_position_extremes_job")
    body = ast.get_source_segment(src, job)
    assert "await scan_breakeven_arms()" in body, "the arm is not scheduled"
    assert body.index("await scan_profit_triggers()") < body.index("await scan_breakeven_arms()")
    tries = [n for n in ast.walk(job) if isinstance(n, ast.Try)]
    owning = [t for t in tries if "scan_breakeven_arms()" in ast.get_source_segment(src, t)]
    assert owning, "the arm must sit inside a try/except"
    inner = min(owning, key=lambda t: len(ast.get_source_segment(src, t)))
    assert "scan_profit_triggers" not in ast.get_source_segment(src, inner)


def test_the_arm_writer_is_registered_in_both_trade_state_gates():
    """Gate 5 G (column-write authority) + the boot-time prepare gate both know the new
    writer, and the SQL registered for prepare is the SQL the function runs."""
    from scripts.audit_column_writes import ALLOWED_WRITERS
    from scripts.preflight_db_updates import TRADE_LIFECYCLE_UPDATES
    for col in ("stop_order_id", "stop_price", "breakeven_active"):
        assert "order_manager._mark_breakeven_armed" in ALLOWED_WRITERS[col], col
    registered = {lbl: sql for lbl, sql in TRADE_LIFECYCLE_UPDATES if "_mark_breakeven_armed" in lbl}
    assert len(registered) == 2
    fn_src = inspect.getsource(om._mark_breakeven_armed)
    for sql in registered.values():
        assert " ".join(sql.split()) in " ".join(fn_src.split())


def test_the_arm_never_lives_inside_the_recorder():
    """Same rule as the partial (#500 class): track_open_position_extremes is name-registered
    as a pure recorder; a stop replace inside it would trip Gate 5 G."""
    rec = ast.get_source_segment(SRC, next(
        n for n in ast.walk(ast.parse(SRC))
        if isinstance(n, ast.AsyncFunctionDef) and n.name == "track_open_position_extremes"))
    assert "replace_order" not in rec and "scan_breakeven_arms" not in rec
