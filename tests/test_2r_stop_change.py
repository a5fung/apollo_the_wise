"""2026-08-16 — OPERATOR-SIGNED stop change (THE LINE): MAGNA53's protective stop
moves from the ORB low to entry − 2R, where R = entry − ORB low (so
new_stop = 2·orb_low − orb_high). Size halves BY the sizing formula itself
(shares = risk_dollars / stop_distance), so dollar risk per trade is unchanged.

🔴 The single most dangerous part of the change: the +2R profit target must NOT
move. One third still comes off at the ORIGINAL entry + 2·(entry − orb_low)
price. If the target were framed off the placed stop it would silently drift to
+4R — never tested, never approved.

Every test here asserts BEHAVIOUR (returned spec values / actual call args on a
reached code path), never comments or source text. Mutation results are recorded
in each docstring's `MUTATION:` line — each mutation was applied to the code and
the named test confirmed red, then reverted.

Evidence for the change (cited, not re-derived): matched 43 reconstructed HIGH
trades at equal dollar risk — live ORB-low stop SUM −6.0R median −1.00 vs 2R
stop at half size SUM +11.4R median +0.33 (docs/roadmap/
ep_profitability_program.md §0c-pre). SSoT: docs/setups/magna53_ep.md +
docs/setups/exit_discipline.md change logs 2026-08-16.
"""
from datetime import date, datetime, timezone
from unittest.mock import AsyncMock, patch

import pytest

import agents.market_intelligence.broker.order_manager as om
from agents.market_intelligence.broker.order_manager import (
    profit_target_r_per_share,
    stop_limit_buy_price,
)


# ── prepare_orb_order fixtures ────────────────────────────────────────────────
# ORB: H=20, L=19 → R=1.00, 2R stop=18.00, stop distance=2.00.
# equity 10_000 × risk 1% = $100 budget → 50 shares (old rule: 100).

_ALERT = {"ticker": "TSTX", "ep_score": 80, "catalyst_quality": "strong", "gap_pct": 12}
_ORB = {"high": 20.0, "low": 19.0}
_REGIME = {"regime": "Bull"}


async def _build_spec(orb=_ORB, atr=5.0, equity=10_000.0, risk_pct=0.01,
                      validate=(True, None)):
    """Run the REAL prepare_orb_order. `validate_orb_entry` must be patched
    because tests/conftest.py stubs the whole backtester.filters module (heavy
    import chain) — its default here mirrors the real function's pass result;
    the admission test injects the real rejection tuple instead."""
    with patch.object(om, "_resolve_regime_risk_pct", AsyncMock(return_value=risk_pct)), \
         patch.object(om, "validate_orb_entry", return_value=validate), \
         patch.object(om.alpaca, "get_account",
                      AsyncMock(return_value={"equity": equity})) as fake_account:
        spec, reason = await om.prepare_orb_order(
            _ALERT, orb, atr_14=atr, regime_record=_REGIME,
            account_mode="paper", today=date(2026, 8, 17),
        )
    return spec, reason, fake_account


@pytest.mark.asyncio
async def test_stop_is_2r_below_entry_not_the_orb_low():
    """The placed protective stop is entry − 2R = 2·orb_low − orb_high. The ORB
    low still DEFINES R; it is no longer the exit.
    MUTATION: `stop_loss_price = orb_low` (revert to the old rule) → this test
    fails (18.0 expected, 19.0 returned)."""
    spec, reason, _ = await _build_spec()
    assert reason is None
    assert spec["stop_loss_price"] == pytest.approx(18.0)
    assert spec["stop_loss_price"] != spec["orb_low"]
    # The ORB geometry itself is recorded unchanged — R stays reconstructable.
    assert spec["orb_low"] == 19.0 and spec["orb_high"] == 20.0


@pytest.mark.asyncio
async def test_size_halves_via_the_formula_no_second_halving():
    """$100 budget / $2.00 stop distance = 50 shares — exactly HALF the old
    rule's 100, produced by the sizing formula alone. An explicit halving on top
    would quarter the position (25) — the trap the signed change names.
    MUTATION 1: `shares = math.floor(...) // 2` (double halving) → fails (25).
    MUTATION 2: `risk_per_share = orb_high - orb_low` with the 2R stop kept
    (incoherent bookkeeping, shares NOT halved) → fails (100)."""
    spec, reason, _ = await _build_spec()
    assert reason is None
    assert spec["shares"] == 50
    assert spec["risk_per_share"] == pytest.approx(2.0)


@pytest.mark.asyncio
async def test_dollar_risk_at_the_stop_is_unchanged_by_the_change():
    """risk_dollars still means "dollar loss if the stop fills": shares × stop
    distance ≤ budget < (shares+1) × distance, with the budget itself untouched
    (equity × risk_pct — the same $100 the old rule risked).
    MUTATION: covered by the two above — any stop/size incoherence breaks the
    shares↔risk_per_share product asserted here."""
    spec, reason, _ = await _build_spec()
    assert reason is None
    assert spec["risk_dollars"] == pytest.approx(100.0)
    dist = spec["entry_price"] - spec["stop_loss_price"]
    assert spec["shares"] * dist <= spec["risk_dollars"] + 1e-9
    assert (spec["shares"] + 1) * dist > spec["risk_dollars"]


@pytest.mark.asyncio
async def test_entry_trigger_and_limit_formula_untouched():
    """Entry stays a stop-limit BUY at the ORB high with the existing limit
    formula — the change touches the EXIT side only."""
    spec, reason, _ = await _build_spec()
    assert reason is None
    assert spec["entry_price"] == 20.0
    assert spec["limit_price"] == stop_limit_buy_price(20.0)


@pytest.mark.asyncio
async def test_stop_too_wide_admission_gate_unchanged():
    """A stop_too_wide validation verdict still rejects BEFORE any sizing or
    account fetch, with the same reason class — admission logic is untouched by
    the stop change (validate_orb_entry judges ORB geometry vs ATR, and the ORB
    geometry did not move; the function itself is not in this change's diff)."""
    spec, reason, fake_account = await _build_spec(
        orb={"high": 20.0, "low": 15.0}, atr=2.0,
        validate=(False, "setup:stop_too_wide: 5.00 > 1.5x ATR 2.00"),
    )
    assert spec is None
    assert reason is not None and "stop_too_wide" in reason
    fake_account.assert_not_awaited()  # rejected before sizing, exactly as before


@pytest.mark.asyncio
async def test_nonpositive_2r_stop_is_rejected_not_submitted():
    """Defensive: ORB range ≥ orb_low makes 2·orb_low − orb_high ≤ 0 — a stop
    that cannot exist at the broker. Must reject loudly, never emit a spec.
    MUTATION: remove the `stop_loss_price <= 0` guard → fails (a spec with a
    negative stop is returned)."""
    # H=9, L=4 → range 5, ATR 10 passes validation; 2R stop = −1.
    spec, reason, _ = await _build_spec(orb={"high": 9.0, "low": 4.0}, atr=10.0)
    assert spec is None
    assert reason is not None and "2R stop" in reason
    # boundary: exactly $0 is also unplaceable
    spec0, reason0, _ = await _build_spec(orb={"high": 10.0, "low": 5.0}, atr=10.0)
    assert spec0 is None and reason0 is not None


# ── profit_target_r_per_share (the frame the +2R target is priced in) ─────────


def test_r_frame_magna53_is_orb_based_not_stop_based():
    """entry 100, orb_low 95, placed stop 90 (the new 2R stop): R must be 5
    (ORB), not 10 (stop distance).
    MUTATION: return `entry - stop` for magna53 → fails (10 ≠ 5)."""
    assert profit_target_r_per_share("magna53", 100.0, 90.0, 95.0) == pytest.approx(5.0)


def test_r_frame_magna53_legacy_row_identical():
    """A pre-change open trade has stop == orb_low: both frames agree, so
    in-flight trades see a byte-identical target at flip time."""
    assert profit_target_r_per_share("magna53", 100.0, 95.0, 95.0) == pytest.approx(5.0)


def test_r_frame_other_strategies_keep_stop_distance():
    """9M Day 2's stop (prior day low) IS its R — the ORB frame must not leak
    into other strategies (the #490 latent-defect class).
    MUTATION: add '9m_day2' to _ORB_R_FRAME_SIGNAL_TYPES → fails (5 ≠ 3)."""
    assert profit_target_r_per_share("9m_day2", 100.0, 97.0, 95.0) == pytest.approx(3.0)


def test_r_frame_returns_none_when_unframeable_never_guesses():
    """MUTATION: drop the orb_low >= entry guard → the third case fails."""
    assert profit_target_r_per_share("magna53", 100.0, 90.0, None) is None
    assert profit_target_r_per_share("magna53", None, 90.0, 95.0) is None
    assert profit_target_r_per_share("magna53", 100.0, 90.0, 101.0) is None
    assert profit_target_r_per_share("9m_day2", 100.0, None, None) is None
    assert profit_target_r_per_share("9m_day2", 100.0, 101.0, None) is None


# ── scan_profit_triggers, end to end: the target must NOT drift to +4R ───────


class _FakeConn:
    def __init__(self, rows, hi):
        self._rows, self._hi = rows, hi

    async def fetch(self, sql, *a):
        return self._rows

    async def fetchval(self, sql, *a):
        return self._hi


class _FakePool:
    def __init__(self, rows, hi):
        self._conn = _FakeConn(rows, hi)

    def acquire(self):
        conn = self._conn

        class _Ctx:
            async def __aenter__(self):
                return conn

            async def __aexit__(self, *a):
                return False

        return _Ctx()


class _NoonET(datetime):
    """datetime.now(_ET) → a fixed 12:00 ET trading-day time, so the scan's
    after-open gate passes deterministically regardless of when tests run."""

    @classmethod
    def now(cls, tz=None):
        return datetime(2026, 8, 17, 12, 0, tzinfo=tz)


def _trade_row(**over):
    row = {
        "id": 7, "ticker": "TSTX", "entry_price": 100.0,
        "hard_stop": 90.0,          # the NEW 2R stop
        "stop_price": 90.0,
        "orb_low": 95.0,            # R = 5 → target 110, drifted target 120
        "signal_type": "magna53",
        "remaining_shares": 30.0, "partial_taken": False,
        "filled_at": datetime(2026, 8, 17, 13, 31, tzinfo=timezone.utc),
        "account_mode": "live",
    }
    row.update(over)
    return row


async def _run_scan(monkeypatch, rows, hi):
    """Drive the REAL scan_profit_triggers over a fake pool; return the
    execute_partial_exit mock (call args = the behaviour under test)."""
    import agents.market_intelligence.constants as constants
    monkeypatch.setattr(constants, "PROFIT_TRIGGER_R", 2.0)
    fake_exec = AsyncMock(return_value=True)
    with patch.object(om, "get_pool", AsyncMock(return_value=_FakePool(rows, hi))), \
         patch.object(om, "datetime", _NoonET), \
         patch.object(om, "execute_partial_exit", fake_exec), \
         patch.object(om, "_profit_take_resting_limit_enabled", AsyncMock(return_value=True)), \
         patch.object(om, "_profit_trigger_already_announced", AsyncMock(return_value=True)), \
         patch.object(om, "send_telegram_message", AsyncMock(return_value=True)), \
         patch.object(om, "log_audit_event", AsyncMock()):
        results = await om.scan_profit_triggers()
    return fake_exec, results


@pytest.mark.asyncio
async def test_target_fires_at_the_ORIGINAL_2r_price_not_4r(monkeypatch):
    """🔴 THE primary correctness risk of the signed change. entry 100, ORB R=5,
    placed stop 90. The target is the ORIGINAL 110 = entry + 2·(entry−orb_low).
    A high of 110 must fire the partial WITH limit_price=110. Framed off the new
    stop the target would be 120 and this high would not fire at all — so the
    positive call assertion proves both the level and that the path was reached.
    MUTATION: `target = entry + PROFIT_TRIGGER_R * (entry - stop)` (the drift)
    → fails (execute_partial_exit never awaited)."""
    fake_exec, results = await _run_scan(monkeypatch, [_trade_row()], hi=110.0)
    fake_exec.assert_awaited_once_with(7, 10, limit_price=110.0)
    assert results == [{"ticker": "TSTX", "action": "partial_submitted", "shares": 10}]


@pytest.mark.asyncio
async def test_target_does_not_fire_below_the_orb_2r_level(monkeypatch):
    """Negative control at 109.99 < 110: proves the fire above is the target
    level acting, not the scan firing on anything ≥ entry."""
    fake_exec, results = await _run_scan(monkeypatch, [_trade_row()], hi=109.99)
    fake_exec.assert_not_awaited()
    assert results == []


@pytest.mark.asyncio
async def test_non_magna53_target_still_frames_off_its_own_stop(monkeypatch):
    """A 9m_day2 row (stop 97 = prior-day low, R=3): target 106, exactly as
    before this change — the ORB frame must not rewrite another strategy's
    target. MUTATION: adding 9m_day2 to _ORB_R_FRAME_SIGNAL_TYPES moves its
    target to 110 → this fails (not awaited at hi=106)."""
    row = _trade_row(id=8, ticker="NINE", signal_type="9m_day2",
                     hard_stop=97.0, stop_price=97.0)
    fake_exec, _ = await _run_scan(monkeypatch, [row], hi=106.0)
    fake_exec.assert_awaited_once_with(8, 10, limit_price=106.0)


@pytest.mark.asyncio
async def test_magna53_without_orb_low_skips_loudly_never_drifts(monkeypatch):
    """A magna53 row with no usable orb_low has NO ORB frame. Even at a high of
    150 (≥ the drifted +4R level 120) nothing may fire — a wrong-priced partial
    is worse than a skipped one (ADR 0014: never fabricate an R frame).
    MUTATION: falling back to entry − stop when orb_low is missing → fails
    (execute_partial_exit awaited)."""
    row = _trade_row(orb_low=None)
    fake_exec, results = await _run_scan(monkeypatch, [row], hi=150.0)
    fake_exec.assert_not_awaited()
    assert results == []
