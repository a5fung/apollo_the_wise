"""#571 (2026-08-23) — make the 20%-of-equity notional cap's truncation VISIBLE.

`prepare_orb_order`'s `max_position = equity * MAX_POSITION_PCT` step silently shrinks
`shares` when a tight stop prices out a share count worth more than 20% of equity — the
trade still fires, just smaller, and nothing recorded it except the shares==0 reject a few
lines below. Measured over the 22 closed live trades
(docs/analysis/position_sizing_571_2026-08-23.md): bound 11 of 22, cutting intended risk
from ~$48 to as little as $15.

🛑 THE LINE — this card is TELEMETRY ONLY. Nothing here changes the cap value (20%), the
risk_pct formula, the floor()/rounding, or the zero-share reject. Every test below either
pins a NEW observable (the audit event, the new `risk_dollars_actual` field) or proves an
OLD observable (shares, risk_dollars, position_size) is byte-identical to what the
hardcoded-0.20 formula already produced — the actual no-op proof for the P15-class constant
fork (`order_manager.py` pointing at `constants.MAX_POSITION_PCT` instead of a second
hardcoded `0.20` literal).
"""
import math
from datetime import date
from unittest.mock import AsyncMock, patch

import pytest

import agents.market_intelligence.broker.order_manager as om
from agents.market_intelligence import constants
from agents.market_intelligence.audit_events import SIZING_NOTIONAL_CAP_TRUNCATED

_TODAY = date(2026, 8, 23)


def test_max_position_pct_constant_is_020():
    """Pins the value BEFORE it's read through the new indirection — a future edit to
    constants.py can't silently move live sizing without this test failing first."""
    assert constants.MAX_POSITION_PCT == 0.20


# ── prepare_orb_order (the LIVE MAGNA53 sizing path) ────────────────────────────────────


async def _build_spec(orb, equity=10_000.0, risk_pct=0.01, emit_cap_telemetry=True,
                      account_mode="live"):
    alert = {"ticker": "TSTX", "ep_score": 80, "catalyst_quality": "strong", "gap_pct": 12}
    fake_audit = AsyncMock()
    with patch.object(om, "_resolve_regime_risk_pct", AsyncMock(return_value=risk_pct)), \
         patch.object(om, "validate_orb_entry", return_value=(True, None)), \
         patch.object(om, "log_audit_event", fake_audit), \
         patch.object(om.alpaca, "get_account", AsyncMock(return_value={"equity": equity})):
        spec, reason = await om.prepare_orb_order(
            alert, orb, atr_14=5.0, regime_record={"regime": "Bull"},
            account_mode=account_mode, today=_TODAY,
            emit_cap_telemetry=emit_cap_telemetry,
        )
    return spec, reason, fake_audit


# ORB high=20, low=19.9 -> 2R stop = 2*19.9-20 = 19.8 -> risk_per_share ~= 0.2 (float
# arithmetic lands a hair over 0.2, e.g. 0.20000000000000284).
# equity 10,000 x 1% = $100 budget / ~$0.20 = 499 shares BEFORE the cap (floor of
# 499.9999999999929, not the idealized 500 — real float imprecision, not a test artifact);
# 499 x $20 = $9,980 notional, far past max_position = 10,000 x 0.20 = $2,000 -> capped to
# floor(2000/20) = 100.
_TIGHT_ORB = {"high": 20.0, "low": 19.9}

# ORB high=20, low=19 -> 2R stop=18 -> risk_per_share=2.0. $100 budget / $2 = 50 shares;
# 50 x $20 = $1,000 notional, UNDER max_position=$2,000 -> the cap never binds.
_WIDE_ORB = {"high": 20.0, "low": 19.0}


@pytest.mark.asyncio
async def test_cap_binding_emits_the_audit_row():
    spec, reason, fake_audit = await _build_spec(_TIGHT_ORB)
    assert reason is None
    assert spec["shares"] == 100  # capped, byte-identical to the old 0.20-literal formula
    fake_audit.assert_awaited_once()
    event_type, summary = fake_audit.await_args.args[0], fake_audit.await_args.args[1]
    assert event_type == SIZING_NOTIONAL_CAP_TRUNCATED
    assert "TSTX" in summary and "2026-08-23" in summary
    assert "499->100" in summary
    assert "$100.00 intended" in summary
    assert "$20.00 actual" in summary
    assert "20%" in summary  # the fraction that matters: actual / intended


@pytest.mark.asyncio
async def test_cap_not_binding_emits_nothing():
    spec, reason, fake_audit = await _build_spec(_WIDE_ORB)
    assert reason is None
    assert spec["shares"] == 50  # uncapped — matches test_2r_stop_change.py's pin
    fake_audit.assert_not_awaited()


@pytest.mark.asyncio
async def test_shares_and_dollars_unchanged_by_the_instrumentation():
    """The load-bearing no-op proof: hand-compute what the OLD `equity * 0.20` literal
    formula produces and assert the new code (constant + telemetry added) matches exactly,
    for both the capped and uncapped case. Any drift here means the constant swap or the
    telemetry call mutated sizing — a THE LINE violation."""
    equity = 10_000.0

    # Capped case
    spec, _, _ = await _build_spec(_TIGHT_ORB, equity=equity)
    stop = 2 * 19.9 - 20.0
    risk_per_share = 20.0 - stop
    risk_dollars = equity * 0.01
    shares_before_cap = math.floor(risk_dollars / risk_per_share)
    max_position = equity * 0.20
    expected_shares = math.floor(max_position / 20.0)
    assert shares_before_cap == 499 and expected_shares == 100  # sanity on the hand math
    assert spec["shares"] == expected_shares
    assert spec["risk_dollars"] == pytest.approx(risk_dollars)  # pre-cap budget, unchanged
    assert spec["position_size"] == pytest.approx(expected_shares * 20.0)

    # Uncapped case
    spec2, _, _ = await _build_spec(_WIDE_ORB, equity=equity)
    risk_per_share2 = 20.0 - 18.0
    expected_shares2 = int((equity * 0.01) // risk_per_share2)
    assert spec2["shares"] == expected_shares2 == 50
    assert spec2["position_size"] == pytest.approx(50 * 20.0)


@pytest.mark.asyncio
async def test_risk_dollars_actual_is_final_shares_times_risk_per_share():
    """The new queryable field — must reflect the FINAL (post-cap) shares, not the pre-cap
    budget that `risk_dollars` already carries."""
    spec, _, _ = await _build_spec(_TIGHT_ORB)
    assert spec["risk_dollars_actual"] == pytest.approx(100 * 0.2, abs=1e-6)
    assert spec["risk_dollars_actual"] < spec["risk_dollars"]  # the whole point: it's smaller

    spec2, _, _ = await _build_spec(_WIDE_ORB)
    # Uncapped: actual == shares * risk_per_share, which can be a hair under the budget
    # only via floor() — never larger, never equal to a DIFFERENT quantity.
    assert spec2["risk_dollars_actual"] == pytest.approx(50 * 2.0, abs=1e-6)
    assert spec2["risk_dollars_actual"] <= spec2["risk_dollars"] + 1e-9


@pytest.mark.asyncio
async def test_persisted_risk_dollars_actual_matches_audit_message_hoisted_value():
    """Regression pin for the hoist that made `risk_dollars_actual` computed ONCE in
    `prepare_orb_order` and passed into `_log_notional_cap_truncation`, instead of being
    computed independently at both call sites 17 lines apart. Byte-identical to the
    pre-hoist values (hand-verified: capped case = floor(2000/20)=100 shares *
    risk_per_share ~=0.2 -> $20.00; uncapped case = 50 shares * $2.00 -> $100.00) — a
    hoist bug (e.g. passing the wrong shares/risk_per_share) would desync the persisted
    `mi_live_trades.risk_dollars_actual` field from the audit-log summary, or silently
    change the value itself. Exact equality, not approx: the persisted number must be
    byte-identical to what it was before the hoist."""
    spec, _, fake_audit = await _build_spec(_TIGHT_ORB)
    assert spec["risk_dollars_actual"] == 20.0
    summary = fake_audit.await_args.args[1]
    assert f"${spec['risk_dollars_actual']:.2f} actual" in summary

    spec2, _, fake_audit2 = await _build_spec(_WIDE_ORB)
    assert spec2["risk_dollars_actual"] == 100.0
    fake_audit2.assert_not_awaited()  # uncapped -> no truncation message to cross-check


@pytest.mark.asyncio
async def test_shadow_lane_call_suppresses_the_audit_event():
    """shadow_orb_tracker.py calls prepare_orb_order with emit_cap_telemetry=False (and
    account_mode=None) — no Alpaca submit happens there, so a truncation must not pollute
    the #571 signal, which is meant to measure only real, real-money truncated trades."""
    spec, reason, fake_audit = await _build_spec(
        _TIGHT_ORB, emit_cap_telemetry=False, account_mode=None,
    )
    assert reason is None
    assert spec["shares"] == 100  # cap still applies — only the TELEMETRY is suppressed
    fake_audit.assert_not_awaited()


# ── prepare_prior_day_low_orb_order (#482 shadow-only path — constant swap only) ────────


@pytest.mark.asyncio
async def test_prior_day_low_path_constant_swap_is_also_a_no_op():
    """This function's live caller (`submit_9m_day2_trade`) was removed in #515 — it now
    serves ONLY the #482 shadow lane, so it gets the constant fix (was a second hardcoded
    0.20 literal) but no #571 telemetry. Proves that swap is numerically identical too."""
    sugar_baby = {"ticker": "TSTX", "low_price": 19.9, "alert_date": _TODAY}
    orb_bar = {"high": 20.0, "low": 19.9}
    equity = 10_000.0
    with patch.object(om, "_resolve_regime_risk_pct", AsyncMock(return_value=0.01)), \
         patch.object(om.alpaca, "get_account", AsyncMock(return_value={"equity": equity})):
        spec, reason = await om.prepare_prior_day_low_orb_order(
            sugar_baby, orb_bar, regime_record={"regime": "Bull"}, account_mode="paper",
        )
    assert reason is None
    # risk_per_share floored to the 2% minimum (20*0.02=0.4, since 20-19.9=0.1 < 0.4);
    # $100 budget / $0.4 = 250 shares before the cap; capped to floor(2000/20)=100.
    max_position = equity * 0.20
    expected_shares = int(max_position // 20.0)
    assert expected_shares == 100
    assert spec["shares"] == expected_shares
