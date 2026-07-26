"""#456 DoD(a) — regime-keyed risk multiplier (operator-ruled 2026-07-26).

Covers:
  - constants.regime_risk_multiplier: pure lookup, all 4 labels + None +
    unrecognized-label floor.
  - order_manager._resolve_regime_risk_pct (the ONE resolver both real-money
    sizing sites call):
      flag OFF -> byte-identical to the pre-#456 VIX-scaled + qqq_ema_bullish
                  binary-halve formula (numeric pin against the operator's own
                  worked example: VIX 18.58 + bearish EMA -> 0.4105x).
      flag ON  -> fresh Bull/Choppy/Correcting/Crisis size correctly and do
                  NOT alert; missing / stale / unrecognized-label floors to
                  0.25x AND fires the fail-loud Telegram+audit alert, deduped
                  once per ET day per account_mode.
  - prepare_orb_order (MAGNA53) and prepare_9m_day2_orb_order (9M Day2) both
    route through the shared resolver (pinned so they can't drift apart).
  - flag_detector.prepare_htf_breakout_order (HTF shadow, site #3): flag OFF
    byte-identical; flag ON folds via the pure lookup only (no alerting — the
    function is deliberately pure/sync, no execution-boundary import).
  - briefing._format_regime_section's "size ≈X×" display line stays in sync
    with the flag (not a sizing site, but a correctness-relevant display).

Run: pytest tests/test_regime_sizing.py -v
"""
from __future__ import annotations

from datetime import date
from unittest.mock import AsyncMock, patch

import pytest

from agents.market_intelligence import constants
from agents.market_intelligence.audit_events import SIZING_REGIME_FALLBACK
from agents.market_intelligence.broker import order_manager as om
from tests.conftest import make_mock_pool

# Tuesday / Monday / Friday fixture dates used throughout (2026-07-28 is a
# real Tuesday; 07-27 Monday; 07-24 Friday — see date-arithmetic pin below).
_TUE = date(2026, 7, 28)
_MON = date(2026, 7, 27)
_FRI = date(2026, 7, 24)


def test_fixture_weekdays_are_what_they_claim():
    assert _TUE.weekday() == 1 and _MON.weekday() == 0 and _FRI.weekday() == 4


# ── constants.regime_risk_multiplier — pure lookup ──────────────────────────


def test_regime_risk_multiplier_all_four_labels():
    assert constants.regime_risk_multiplier("Bull") == 1.00
    assert constants.regime_risk_multiplier("Choppy") == 0.75
    assert constants.regime_risk_multiplier("Correcting") == 0.50
    assert constants.regime_risk_multiplier("Crisis") == 0.25


def test_regime_risk_multiplier_none_and_unrecognized_floor():
    assert constants.regime_risk_multiplier(None) == 0.25
    assert constants.regime_risk_multiplier("") == 0.25
    assert constants.regime_risk_multiplier("Bullish-ish") == 0.25  # renamed/typo'd label


# ── Harness: audit-log-as-state dedup (mirrors test_intraday_drawdown.py) ───


class _Harness:
    """Fake audit log + telegram around _resolve_regime_risk_pct. The audit
    store backs BOTH log_audit_event (writes) and the dedup query's
    conn.fetch (reads) — exercises the real dedup logic instead of mocking
    it away, same idiom as test_intraday_drawdown.py's _Harness."""

    def __init__(self):
        self.audit_rows: list[dict] = []
        self.sent: list[str] = []
        self._current_today: date | None = None  # set per resolve() call

    async def fake_audit(self, event_type, summary, detail=""):
        # Real log_audit_event() takes no date param — created_at is
        # DB-server NOW(). Stash the ET day this call happened on (known from
        # the enclosing resolve() call) so the fake dedup query below can
        # filter by day, same as the real `(created_at AT TIME ZONE ...)::date
        # = $2` predicate.
        self.audit_rows.append(
            {"event_type": event_type, "summary": summary, "today": self._current_today})

    async def fake_send(self, msg, **kwargs):
        self.sent.append(msg)
        return True

    def fallback_rows(self):
        return [r for r in self.audit_rows if r["event_type"] == SIZING_REGIME_FALLBACK]

    async def resolve(self, regime_record, today, account_mode, base_pct=0.01):
        self._current_today = today
        pool, conn = make_mock_pool()

        async def fake_fetch(query, event_type, today_param):
            return [{"summary": r["summary"]} for r in self.audit_rows
                    if r["event_type"] == event_type and r["today"] == today_param]

        conn.fetch = AsyncMock(side_effect=fake_fetch)
        # order_manager.py imports send_telegram_message at MODULE level
        # (`from agents.market_intelligence.briefing import send_telegram_message`),
        # so the name is bound into om's own namespace at import time —
        # patch it there, not on the briefing module (patching the source
        # module wouldn't reach om's already-bound reference).
        with patch.object(om, "log_audit_event", self.fake_audit), \
             patch.object(om, "get_pool", AsyncMock(return_value=pool)), \
             patch.object(om, "send_telegram_message", self.fake_send):
            return await om._resolve_regime_risk_pct(
                regime_record, today, account_mode, base_pct=base_pct,
            )


# ── Flag OFF: byte-identical to pre-#456 behavior ───────────────────────────


@pytest.mark.asyncio
async def test_flag_off_reproduces_vix_scaled_plus_ema_halve_numerically(monkeypatch):
    monkeypatch.setattr(constants, "REGIME_SIZING_ENABLED", False)
    h = _Harness()
    regime_record = {
        "regime": "Correcting", "vix": 18.58, "qqq_ema_bullish": False,
        "regime_date": _MON,
    }
    risk_pct = await h.resolve(regime_record, _TUE, "live", base_pct=0.01)
    # VIX 18.58 -> scaled max(0.25, 1-(18.58-15)/20)=0.821 -> EMA halve *0.5
    # = 0.4105x. Matches the operator-shown worked example: $4,835 * 0.004105
    # == $19.85 (today's actual risk/trade in the live Correcting stretch).
    assert risk_pct == pytest.approx(0.004105, abs=1e-6)
    assert 4835.0 * risk_pct == pytest.approx(19.85, abs=0.01)
    assert h.sent == [] and h.audit_rows == []  # flag OFF never alerts


@pytest.mark.asyncio
async def test_flag_off_missing_regime_is_full_base_fail_open_unchanged(monkeypatch):
    monkeypatch.setattr(constants, "REGIME_SIZING_ENABLED", False)
    h = _Harness()
    risk_pct = await h.resolve(None, _TUE, "paper", base_pct=0.01)
    assert risk_pct == 0.01  # today's fail-open, byte-identical — no floor, no alert
    assert h.sent == [] and h.audit_rows == []


@pytest.mark.asyncio
async def test_flag_off_bullish_ema_no_halve(monkeypatch):
    monkeypatch.setattr(constants, "REGIME_SIZING_ENABLED", False)
    h = _Harness()
    regime_record = {"regime": "Bull", "vix": 14.0, "qqq_ema_bullish": True}
    risk_pct = await h.resolve(regime_record, _TUE, "live", base_pct=0.01)
    assert risk_pct == pytest.approx(0.01)  # VIX <= 15 -> full base, EMA bullish -> no halve


# ── Flag ON: fresh regime rows, each label, no alert ────────────────────────


@pytest.mark.asyncio
async def test_flag_on_fresh_each_label_sizes_correctly_and_never_alerts(monkeypatch):
    monkeypatch.setattr(constants, "REGIME_SIZING_ENABLED", True)
    h = _Harness()
    expected = {"Bull": 0.01, "Choppy": 0.0075, "Correcting": 0.005, "Crisis": 0.0025}
    for label, exp in expected.items():
        risk_pct = await h.resolve(
            {"regime": label, "regime_date": _MON}, _TUE, "paper", base_pct=0.01,
        )
        assert risk_pct == pytest.approx(exp), label
    assert h.sent == [] and h.audit_rows == []


@pytest.mark.asyncio
async def test_flag_on_fresh_correcting_beats_todays_accidental_ema_halve(monkeypatch):
    # The proposal's headline number: Correcting fresh -> 0.50x vs today's
    # effective 0.41-0.48x (VIX-scaled + EMA halve) — a real exposure increase,
    # already accepted by the operator; pinned here so a regression can't
    # silently drift the level.
    monkeypatch.setattr(constants, "REGIME_SIZING_ENABLED", True)
    h = _Harness()
    risk_pct = await h.resolve(
        {"regime": "Correcting", "regime_date": _MON}, _TUE, "live", base_pct=0.01,
    )
    assert risk_pct == pytest.approx(0.005)
    assert 4835.0 * risk_pct == pytest.approx(24.175, abs=0.01)
    assert h.sent == []  # a legitimate fresh Correcting reading is NOT a fallback


# ── Flag ON: missing / stale / unrecognized -> floor + fail-loud ───────────


@pytest.mark.asyncio
async def test_flag_on_missing_regime_floors_and_alerts(monkeypatch):
    monkeypatch.setattr(constants, "REGIME_SIZING_ENABLED", True)
    h = _Harness()
    risk_pct = await h.resolve(None, _TUE, "live", base_pct=0.01)
    assert risk_pct == pytest.approx(0.0025)
    assert len(h.sent) == 1 and "FALLBACK" in h.sent[0]
    assert len(h.fallback_rows()) == 1
    assert "account_mode=live" in h.fallback_rows()[0]["summary"]
    assert "missing_or_stale" in h.fallback_rows()[0]["summary"]


@pytest.mark.asyncio
async def test_flag_on_stale_regime_date_floors_and_alerts(monkeypatch):
    # Tuesday reading Friday's row (nightly didn't run Monday) — genuinely
    # stale, per the advisor-caught predicate: threshold for Tuesday is
    # Monday, and Friday < Monday.
    monkeypatch.setattr(constants, "REGIME_SIZING_ENABLED", True)
    h = _Harness()
    stale_record = {"regime": "Bull", "regime_date": _FRI}
    risk_pct = await h.resolve(stale_record, _TUE, "paper", base_pct=0.01)
    assert risk_pct == pytest.approx(0.0025)
    assert len(h.sent) == 1
    assert len(h.fallback_rows()) == 1


@pytest.mark.asyncio
async def test_flag_on_monday_reading_fridays_row_is_NOT_stale(monkeypatch):
    # The exact case the proposal's own staleness test names: "Monday
    # correctly accepts Friday's row." Also the case the naive predicate
    # (regime_date < last_trading_day(today)) gets WRONG in the other
    # direction on a plain Tuesday -- pinned here for the weekend edge too.
    monkeypatch.setattr(constants, "REGIME_SIZING_ENABLED", True)
    h = _Harness()
    fresh_over_weekend = {"regime": "Choppy", "regime_date": _FRI}
    risk_pct = await h.resolve(fresh_over_weekend, _MON, "live", base_pct=0.01)
    assert risk_pct == pytest.approx(0.0075)
    assert h.sent == []  # must NOT be treated as stale


@pytest.mark.asyncio
async def test_flag_on_ordinary_trading_day_yesterdays_row_is_fresh(monkeypatch):
    # The advisor-caught bug this test guards against: a naive
    # `regime_date < last_trading_day(today)` is TRUE every single ordinary
    # morning (last_trading_day(today) == today on any trading day), which
    # would floor + fail-loud-alert every day. Tuesday reading Monday's row
    # (the normal 9:31 ET case — today's nightly hasn't run yet) must be FRESH.
    monkeypatch.setattr(constants, "REGIME_SIZING_ENABLED", True)
    h = _Harness()
    normal_case = {"regime": "Bull", "regime_date": _MON}
    risk_pct = await h.resolve(normal_case, _TUE, "live", base_pct=0.01)
    assert risk_pct == pytest.approx(0.01)
    assert h.sent == []


@pytest.mark.asyncio
async def test_flag_on_unrecognized_label_floors_and_alerts(monkeypatch):
    monkeypatch.setattr(constants, "REGIME_SIZING_ENABLED", True)
    h = _Harness()
    weird = {"regime": "Melting-Up", "regime_date": _MON}  # fresh date, bad label
    risk_pct = await h.resolve(weird, _TUE, "live", base_pct=0.01)
    assert risk_pct == pytest.approx(0.0025)
    assert len(h.sent) == 1
    assert "unrecognized_label" in h.fallback_rows()[0]["summary"]


# ── Dedup: once per ET day per account_mode ─────────────────────────────────


@pytest.mark.asyncio
async def test_dedup_second_call_same_day_same_mode_is_silent(monkeypatch):
    monkeypatch.setattr(constants, "REGIME_SIZING_ENABLED", True)
    h = _Harness()
    await h.resolve(None, _TUE, "live", base_pct=0.01)
    assert len(h.sent) == 1
    risk_pct = await h.resolve(None, _TUE, "live", base_pct=0.01)
    assert risk_pct == pytest.approx(0.0025)  # floor still applied correctly
    assert len(h.sent) == 1                   # but no re-alert
    assert len(h.fallback_rows()) == 1         # and no duplicate audit row


@pytest.mark.asyncio
async def test_dedup_is_scoped_per_account_mode(monkeypatch):
    monkeypatch.setattr(constants, "REGIME_SIZING_ENABLED", True)
    h = _Harness()
    await h.resolve(None, _TUE, "live", base_pct=0.01)
    await h.resolve(None, _TUE, "paper", base_pct=0.01)
    assert len(h.sent) == 2  # independent per account_mode
    assert len(h.fallback_rows()) == 2


@pytest.mark.asyncio
async def test_dedup_resets_the_next_day(monkeypatch):
    monkeypatch.setattr(constants, "REGIME_SIZING_ENABLED", True)
    h = _Harness()
    await h.resolve(None, _MON, "live", base_pct=0.01)
    await h.resolve(None, _TUE, "live", base_pct=0.01)
    assert len(h.sent) == 2  # different ET day -> independent


# ── Both real sizing sites route through the ONE shared resolver ───────────


@pytest.mark.asyncio
async def test_prepare_orb_order_routes_through_shared_resolver():
    fake_resolver = AsyncMock(return_value=0.005)
    with patch.object(om, "_resolve_regime_risk_pct", fake_resolver), \
         patch.object(om, "validate_orb_entry", return_value=(True, None)), \
         patch.object(om.alpaca, "get_account", AsyncMock(return_value={"equity": 4835.0})):
        alert = {"ticker": "TEST", "ep_score": 80, "catalyst_quality": "x", "gap_pct": 5}
        orb_bar = {"high": 20.0, "low": 19.0}
        regime_record = {"regime": "Correcting"}
        spec, reason = await om.prepare_orb_order(
            alert, orb_bar, atr_14=0.5, regime_record=regime_record, account_mode="live",
        )
    assert reason is None
    fake_resolver.assert_awaited_once()
    call_args = fake_resolver.await_args.args
    assert call_args[0] is regime_record
    assert call_args[2] == "live"
    assert spec["risk_dollars"] == pytest.approx(4835.0 * 0.005, abs=0.01)


@pytest.mark.asyncio
async def test_prepare_orb_order_threads_caller_supplied_today_not_a_fresh_clock_read():
    # Advisor-caught gap: a caller-supplied `today` (the SAME value already
    # used for the regime fetch / alerts query / submit_trade_entry) must
    # reach the resolver verbatim -- NOT get silently replaced by a second,
    # independent et_today() call inside order_manager.py (a real risk under
    # EXECUTION_MODE=http, where the two containers' clocks are a second,
    # unpinned time source in the money path).
    fake_resolver = AsyncMock(return_value=0.01)
    caller_today = date(2026, 6, 15)  # deliberately NOT "today" by wall clock
    with patch.object(om, "_resolve_regime_risk_pct", fake_resolver), \
         patch.object(om, "validate_orb_entry", return_value=(True, None)), \
         patch.object(om.alpaca, "get_account", AsyncMock(return_value={"equity": 4835.0})):
        alert = {"ticker": "TEST", "ep_score": 80, "catalyst_quality": "x", "gap_pct": 5}
        orb_bar = {"high": 20.0, "low": 19.0}
        await om.prepare_orb_order(
            alert, orb_bar, atr_14=0.5, regime_record={"regime": "Bull"},
            account_mode="live", today=caller_today,
        )
    assert fake_resolver.await_args.args[1] == caller_today


@pytest.mark.asyncio
async def test_prepare_9m_day2_orb_order_routes_through_shared_resolver():
    fake_resolver = AsyncMock(return_value=0.0075)
    with patch.object(om, "_resolve_regime_risk_pct", fake_resolver), \
         patch.object(om.alpaca, "get_account", AsyncMock(return_value={"equity": 4835.0})):
        sugar_baby = {"ticker": "TEST", "low_price": 19.0, "alert_date": _MON}
        orb_bar = {"high": 20.0, "low": 19.0}
        regime_record = {"regime": "Choppy"}
        spec, reason = await om.prepare_9m_day2_orb_order(
            sugar_baby, orb_bar, regime_record=regime_record, account_mode="paper",
        )
    assert reason is None
    fake_resolver.assert_awaited_once()
    call_args = fake_resolver.await_args.args
    assert call_args[0] is regime_record
    assert call_args[2] == "paper"
    # risk_dollars in the spec is shares(floored) * risk_per_share, not the
    # raw equity*risk_pct target — shares = floor(4835*0.0075 / 1.0) = 36.
    assert spec["shares"] == 36
    assert spec["risk_dollars"] == pytest.approx(36.0)


@pytest.mark.asyncio
async def test_prepare_9m_day2_orb_order_threads_caller_supplied_today():
    fake_resolver = AsyncMock(return_value=0.01)
    caller_today = date(2026, 6, 15)
    with patch.object(om, "_resolve_regime_risk_pct", fake_resolver), \
         patch.object(om.alpaca, "get_account", AsyncMock(return_value={"equity": 4835.0})):
        sugar_baby = {"ticker": "TEST", "low_price": 19.0, "alert_date": _MON}
        orb_bar = {"high": 20.0, "low": 19.0}
        await om.prepare_9m_day2_orb_order(
            sugar_baby, orb_bar, regime_record={"regime": "Bull"},
            account_mode="paper", today=caller_today,
        )
    assert fake_resolver.await_args.args[1] == caller_today


# ── Site #3: flag_detector HTF breakout shadow (pure, never submitted) ─────


def test_htf_shadow_flag_off_byte_identical(monkeypatch):
    monkeypatch.setattr(constants, "REGIME_SIZING_ENABLED", False)
    from agents.market_intelligence import flag_detector as fd
    spec, reject = fd.prepare_htf_breakout_order(
        base_high=100.0, base_low=90.0, regime_record=None,
    )
    # VIX None -> fail-open full base; regime_record None -> no EMA halve.
    assert spec["risk_dollars"] == pytest.approx(1000.0)


def test_htf_shadow_flag_on_none_regime_pins_to_floor(monkeypatch):
    # Documented behavior change (not a bug): the caller always hardcodes
    # regime_record=None today, so under the flag this permanently floors
    # the shadow's fixed-notional multiplier at 0.25x. Uniform scale on a
    # fixed notional; doesn't corrupt the #356 edge dataset. See safeguards.md.
    monkeypatch.setattr(constants, "REGIME_SIZING_ENABLED", True)
    from agents.market_intelligence import flag_detector as fd
    spec, reject = fd.prepare_htf_breakout_order(
        base_high=100.0, base_low=90.0, regime_record=None,
    )
    assert spec["risk_dollars"] == pytest.approx(250.0)


def test_htf_shadow_flag_on_uses_regime_label_when_provided(monkeypatch):
    monkeypatch.setattr(constants, "REGIME_SIZING_ENABLED", True)
    from agents.market_intelligence import flag_detector as fd
    spec, reject = fd.prepare_htf_breakout_order(
        base_high=100.0, base_low=90.0, regime_record={"regime": "Bull"},
    )
    assert spec["risk_dollars"] == pytest.approx(1000.0)


# ── Operator-facing display line (briefing.py) stays in sync with the flag ─


def test_briefing_size_line_flag_off_unchanged(monkeypatch):
    monkeypatch.setattr(constants, "REGIME_SIZING_ENABLED", False)
    from agents.market_intelligence.briefing import _format_regime_section
    regime = {"regime": "Correcting", "vix": 18.58, "qqq_ema_bullish": False,
              "ep_threshold": 75, "description": "x\nNet score -2"}
    out = _format_regime_section(regime)
    assert "size ≈0.41×" in out


def test_briefing_size_line_flag_on_shows_regime_multiplier_even_without_vix(monkeypatch):
    monkeypatch.setattr(constants, "REGIME_SIZING_ENABLED", True)
    from agents.market_intelligence.briefing import _format_regime_section
    regime = {"regime": "Correcting", "vix": None, "ep_threshold": 75,
              "description": "x\nNet score -2"}
    out = _format_regime_section(regime)
    # Under the flag the multiplier no longer depends on VIX -- must show
    # even on a VIX-null day (pre-#456 this line was hidden entirely).
    assert "size ≈0.50×" in out
