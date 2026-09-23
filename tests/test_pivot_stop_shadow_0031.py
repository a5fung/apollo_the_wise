"""ADR 0031 pins — character profiler (C1), pivot detectors (C2), trail modes, shadow (C3)."""
import math
from datetime import date, timedelta
from unittest.mock import AsyncMock, MagicMock

import pytest

from agents.market_intelligence.pivot_analysis import (
    annotate_pivot_stops, character_profile, confirmed_swing_lows,
)
from agents.market_intelligence.broker.exit_logic import (
    apply_daily_exit_step, seed_exit_state, iter_exit_ladder,
)


def _bar(d, h, l, c):
    return {"trade_date": d, "high_price": h, "low_price": l, "close": c}


def _synth(closes, dip_idx=(), dip_frac=0.0):
    """Bars from closes; low dips below the close by dip_frac at dip_idx."""
    out = []
    for i, c in enumerate(closes):
        low = c * (1 - dip_frac) if i in dip_idx else c * 0.995
        out.append(_bar(date(2026, 1, 1) + timedelta(days=i), c * 1.005, low, c))
    return out


# ── C1: the character profiler ──────────────────────────────────────────────
def _respecter_bars(n_episodes=6, window=10):
    """A name that rides above its 10SMA and RESPECTS every touch: 8 up days, then a
    single-day touch of the SMA (low dips to it), immediate reclaim to a new high."""
    closes, bars = [], []
    px = 100.0
    d = date(2026, 1, 1)
    for ep in range(n_episodes + 1):
        for _ in range(9):
            px *= 1.01
            closes.append(px)
            bars.append(_bar(d, px * 1.004, px * 0.997, px)); d += timedelta(days=1)
        # the touch day: low tags the sma (≈ mean of last 10) then closes strong;
        sma = sum(closes[-window:]) / min(window, len(closes))
        closes.append(px)  # close holds
        bars.append(_bar(d, px * 1.002, sma * 0.999, px)); d += timedelta(days=1)
        # reclaim day: new high above the pre-episode high
        px *= 1.03
        closes.append(px)
        bars.append(_bar(d, px * 1.005, px * 0.997, px)); d += timedelta(days=1)
    return bars


def test_profiler_respecter_gets_a_home_ma():
    prof = character_profile(_respecter_bars())
    assert prof is not None
    assert prof["home_ma"] in ("sma10", "ema21", "sma20")  # a short MA wins for a 10MA-rider
    assert prof["n_episodes"] >= 3
    assert 0.0 <= prof["undercut_p80"] < 0.10


def test_profiler_abstains_on_short_history():
    assert character_profile(_synth([100 + i for i in range(30)])) is None


def test_profiler_abstains_when_nothing_respects():
    # a steady downtrend: closes below every MA, no episodes can even begin
    closes = [100 * (0.99 ** i) for i in range(140)]
    assert character_profile(_synth(closes)) is None


def test_reanchor_on_rerating():
    # 100 flat bars, then a +60% day (re-rating), then 30 more: the window anchors at the jump
    closes = [100.0] * 100 + [160.0] + [160 + i * 0.1 for i in range(30)]
    prof = character_profile(_synth(closes))
    # profile likely abstains (few episodes post-anchor) — the PIN is the anchor index
    from agents.market_intelligence.pivot_analysis import _trend_window_start
    assert _trend_window_start(closes) == 100


# ── C2: confirmed swing lows + the ratchet ──────────────────────────────────
def test_swing_low_confirmation_timing_no_lookahead():
    lows = [10, 9.5, 9.0, 9.6, 10.2, 10.8, 10.1, 9.8, 10.4, 11.0]
    bars = [_bar(date(2026, 1, 1) + timedelta(days=i), l + 1, l, l + 0.5) for i, l in enumerate(lows)]
    piv = confirmed_swing_lows(bars, k=2)
    # low[2]=9.0 is a fractal low (< 10,9.5 and < 9.6,10.2) confirmed at idx 4
    assert (4, 9.0) in piv
    stops = annotate_pivot_stops(bars, k=2)
    assert stops[3] is None          # NOT yet confirmed at idx 3 — no lookahead
    assert stops[4] == 9.0           # moves ON the confirmation bar
    # low[7]=9.8 fractal (< 10.1,10.8 and < 10.4,11.0) confirmed idx 9 — RATCHETS UP
    assert stops[9] == 9.8
    assert all(a is None or b is None or b >= a for a, b in zip(stops, stops[1:]))  # never widens


# ── the two trail modes (behind the enum guard; defaults untouched) ─────────
def test_unknown_trail_mode_still_raises():
    with pytest.raises(ValueError):
        apply_daily_exit_step({"alert_date": date(2026, 1, 1), "remaining_shares": 10},
                              {"l": 1, "c": 1}, date(2026, 1, 2), trail_mode="bogus")


def test_pivot_swing_mode_exits_on_close_below_annotated_stop():
    st = seed_exit_state(alert_date=date(2026, 1, 1), entry_price=10.0, hard_stop=8.0,
                        remaining_shares=100, partial_taken=True, breakeven_active=False)
    bars = [
        (date(2026, 1, 2), {"l": 10.4, "c": 10.5, "pivot_stop": None}),
        (date(2026, 1, 3), {"l": 10.8, "c": 11.0, "pivot_stop": 10.6}),
        (date(2026, 1, 4), {"l": 10.4, "c": 10.5, "pivot_stop": 10.6}),  # close < pivot → exit
    ]
    steps = list(iter_exit_ladder(st, bars, trail_mode="pivot_swing", skip_partial_decision=True))
    assert steps[-1][2].closed
    assert steps[-1][2].close_reason == "sma_trail_stop"  # the ladder's uniform close-below branch


def test_character_ma_mode_uses_undercut_tolerance():
    # 20 flat closes at 10 → sma20 = 10. With 10% undercut tolerance the line is 9.0:
    # a close at 9.5 (below the MA but inside the name's habitual undercut) must NOT exit.
    st = seed_exit_state(alert_date=date(2026, 1, 1), entry_price=10.0, hard_stop=5.0,
                        remaining_shares=100, partial_taken=True)
    bars = [(date(2026, 1, 2) + timedelta(days=i), {"l": 9.9, "c": 10.0}) for i in range(20)]
    bars.append((date(2026, 2, 5), {"l": 9.4, "c": 9.5}))
    steps = list(iter_exit_ladder(st, bars, trail_mode="character_ma",
                                  character_ma_window=20, character_ma_kind="sma",
                                  character_undercut=0.10, skip_partial_decision=True))
    assert not steps[-1][2].closed   # 9.5 > 9.0 line → tolerated undercut, still holding
    # and WITHOUT the tolerance the same close exits:
    st2 = seed_exit_state(alert_date=date(2026, 1, 1), entry_price=10.0, hard_stop=5.0,
                         remaining_shares=100, partial_taken=True)
    steps2 = list(iter_exit_ladder(st2, list(bars), trail_mode="character_ma",
                                   character_ma_window=20, character_ma_kind="sma",
                                   character_undercut=0.0, skip_partial_decision=True))
    assert steps2[-1][2].closed


# ── C3: the shadow end-to-end (fake pool; no-mutation pin) ──────────────────
@pytest.mark.asyncio
async def test_shadow_logs_row_and_never_mutates_trades(monkeypatch):
    from agents.market_intelligence import pivot_stop_shadow as pss
    from tests.conftest import make_mock_pool
    pool, conn = make_mock_pool()

    closed_trade = {"id": 42, "ticker": "TSTX", "alert_date": date(2026, 6, 1),
                    "account_mode": "live", "entry_price": 10.0, "entry_shares": 100,
                    "hard_stop": 9.0}
    fwd_bars = [_bar(date(2026, 6, 2) + timedelta(days=i), 10.5 + i * 0.1, 10.0 + i * 0.1,
                     10.2 + i * 0.1) for i in range(12)]
    hist_bars = [_bar(date(2026, 1, 1) + timedelta(days=i), 10.1, 9.9, 10.0) for i in range(80)]

    conn.fetch = AsyncMock(side_effect=[[closed_trade], fwd_bars, hist_bars])
    conn.execute = AsyncMock(return_value="INSERT 0 1")
    monkeypatch.setattr(pss, "get_pool", AsyncMock(return_value=pool))
    monkeypatch.setattr(pss, "log_audit_event", AsyncMock())

    n = await pss.run_pivot_stop_shadow(date(2026, 6, 20))

    assert n == 1
    # exactly ONE write, and it's the shadow INSERT — never a mi_live_trades mutation
    writes = [c.args[0] for c in conn.execute.await_args_list]
    assert len(writes) == 1 and "INSERT INTO mi_pivot_stop_shadow" in writes[0]
    assert "mi_live_trades" not in writes[0]
    # the insert carries baseline + p1 numerics and the plain-dict/None profile (jsonb codec)
    args = conn.execute.await_args_list[0].args
    assert isinstance(args[5], float)  # baseline_exit_r


# ── #310: same-day round trips silently dropped forever (no fwd bars on their own close
# day + an exact `closed_at = today` match meant they were never revisited) ────────────
@pytest.mark.asyncio
async def test_insufficient_forward_bars_skipped_with_audit_no_insert(monkeypatch):
    """A same-day round trip has few/no forward bars yet — must be DEFERRED (no row), with
    a reasoned audit event, not silently dropped. FAILS pre-fix: `if not fwd: continue`
    only caught the EMPTY case, so these 2 non-empty-but-too-few bars sailed through and
    got INSERTed as a garbage 'held to end' row."""
    from agents.market_intelligence import pivot_stop_shadow as pss
    from tests.conftest import make_mock_pool
    pool, conn = make_mock_pool()

    closed_trade = {"id": 77, "ticker": "WULF", "alert_date": date(2026, 7, 6),
                    "account_mode": "live", "entry_price": 10.0, "entry_shares": 100,
                    "hard_stop": 9.0}
    fwd_bars = [_bar(date(2026, 7, 7) + timedelta(days=i), 10.5, 10.0, 10.2) for i in range(2)]

    conn.fetch = AsyncMock(side_effect=[[closed_trade], fwd_bars])
    conn.execute = AsyncMock(return_value="INSERT 0 1")
    audit = AsyncMock()
    monkeypatch.setattr(pss, "get_pool", AsyncMock(return_value=pool))
    monkeypatch.setattr(pss, "log_audit_event", audit)

    n = await pss.run_pivot_stop_shadow(date(2026, 7, 8))

    assert n == 0
    conn.execute.assert_not_awaited()  # no garbage row
    assert any(c.args and c.args[0] == "pivot_stop_shadow_skipped"
              for c in audit.await_args_list)
    assert any("insufficient_forward_bars" in c.kwargs.get("summary", "")
              for c in audit.await_args_list)


@pytest.mark.asyncio
async def test_bad_inputs_skipped_with_audit_no_insert(monkeypatch):
    """Non-positive entry/stop/shares must be DEFERRED with an audit event, not the old
    silent `continue` (no event was ever emitted for this branch pre-fix)."""
    from agents.market_intelligence import pivot_stop_shadow as pss
    from tests.conftest import make_mock_pool
    pool, conn = make_mock_pool()

    bad_trade = {"id": 5, "ticker": "ZZZZ", "alert_date": date(2026, 7, 1),
                "account_mode": "live", "entry_price": 0.0, "entry_shares": 100,
                "hard_stop": 9.0}
    conn.fetch = AsyncMock(side_effect=[[bad_trade]])
    conn.execute = AsyncMock(return_value="INSERT 0 1")
    audit = AsyncMock()
    monkeypatch.setattr(pss, "get_pool", AsyncMock(return_value=pool))
    monkeypatch.setattr(pss, "log_audit_event", audit)

    n = await pss.run_pivot_stop_shadow(date(2026, 7, 8))

    assert n == 0
    conn.execute.assert_not_awaited()
    assert any(c.args and c.args[0] == "pivot_stop_shadow_skipped"
              for c in audit.await_args_list)
    assert any("bad_inputs" in c.kwargs.get("summary", "") for c in audit.await_args_list)


@pytest.mark.asyncio
async def test_same_day_roundtrip_shadowed_once_min_bars_exist(monkeypatch):
    """#310's whole point: once _MIN_FWD_BARS forward bars have accumulated (over later
    catch-up runs), a same-day round trip DOES get shadowed."""
    from agents.market_intelligence import pivot_stop_shadow as pss
    from tests.conftest import make_mock_pool
    pool, conn = make_mock_pool()

    closed_trade = {"id": 88, "ticker": "CRCL", "alert_date": date(2026, 7, 6),
                    "account_mode": "live", "entry_price": 10.0, "entry_shares": 100,
                    "hard_stop": 9.0}
    fwd_bars = [_bar(date(2026, 7, 7) + timedelta(days=i), 10.5 + i * 0.1, 10.0 + i * 0.1,
                     10.2 + i * 0.1) for i in range(pss._MIN_FWD_BARS)]
    hist_bars = [_bar(date(2026, 1, 1) + timedelta(days=i), 10.1, 9.9, 10.0) for i in range(80)]

    conn.fetch = AsyncMock(side_effect=[[closed_trade], fwd_bars, hist_bars])
    conn.execute = AsyncMock(return_value="INSERT 0 1")
    monkeypatch.setattr(pss, "get_pool", AsyncMock(return_value=pool))
    monkeypatch.setattr(pss, "log_audit_event", AsyncMock())

    n = await pss.run_pivot_stop_shadow(date(2026, 7, 13))

    assert n == 1
    writes = [c.args[0] for c in conn.execute.await_args_list]
    assert len(writes) == 1 and "INSERT INTO mi_pivot_stop_shadow" in writes[0]


@pytest.mark.asyncio
async def test_catchup_query_uses_lookback_not_exact_day_match(monkeypatch):
    """Root cause pin: the old query matched `closed_at::date = today` EXACTLY, so a trade
    skipped once (0 forward bars on its own close day) was never looked at again. The new
    query must pass a lookback-days param (beyond signal_type/account_mode/today) so the
    SAME trade is re-considered on later runs, and must not do an exact-date match."""
    from agents.market_intelligence import pivot_stop_shadow as pss
    from tests.conftest import make_mock_pool
    pool, conn = make_mock_pool()
    conn.fetch = AsyncMock(side_effect=[[]])
    monkeypatch.setattr(pss, "get_pool", AsyncMock(return_value=pool))
    monkeypatch.setattr(pss, "log_audit_event", AsyncMock())

    n = await pss.run_pivot_stop_shadow(date(2026, 7, 20), signal_type="magna53",
                                        account_mode="live")

    assert n == 0
    query, *params = conn.fetch.await_args_list[0].args
    assert params == ["magna53", "live", date(2026, 7, 20), pss._CATCHUP_LOOKBACK_DAYS]
    assert "closed_at" in query
    assert "= $3" not in query  # no longer an exact-date match on closed_at


@pytest.mark.asyncio
async def test_rerun_does_not_duplicate_rows(monkeypatch):
    """Idempotency: once a trade is shadowed, the (unchanged) `NOT EXISTS` filter means it
    never reappears in a later run's row set — the second run logs 0 more, and only ONE
    INSERT happens across both runs. The insert itself keeps `ON CONFLICT (trade_id) DO
    NOTHING` as the natural-key backstop (trade_id is the table's PRIMARY KEY)."""
    from agents.market_intelligence import pivot_stop_shadow as pss
    from tests.conftest import make_mock_pool
    pool, conn = make_mock_pool()

    closed_trade = {"id": 99, "ticker": "HUT", "alert_date": date(2026, 7, 6),
                    "account_mode": "live", "entry_price": 10.0, "entry_shares": 100,
                    "hard_stop": 9.0}
    fwd_bars = [_bar(date(2026, 7, 7) + timedelta(days=i), 10.5 + i * 0.1, 10.0 + i * 0.1,
                     10.2 + i * 0.1) for i in range(6)]
    hist_bars = [_bar(date(2026, 1, 1) + timedelta(days=i), 10.1, 9.9, 10.0) for i in range(80)]

    # 1st run: trade is un-shadowed -> gets inserted. 2nd run: NOT EXISTS now excludes it
    # (already shadowed) -> empty row set, nothing to (re-)insert.
    conn.fetch = AsyncMock(side_effect=[[closed_trade], fwd_bars, hist_bars, []])
    conn.execute = AsyncMock(return_value="INSERT 0 1")
    monkeypatch.setattr(pss, "get_pool", AsyncMock(return_value=pool))
    monkeypatch.setattr(pss, "log_audit_event", AsyncMock())

    n1 = await pss.run_pivot_stop_shadow(date(2026, 7, 13))
    n2 = await pss.run_pivot_stop_shadow(date(2026, 7, 14))

    assert n1 == 1
    assert n2 == 0
    assert conn.execute.await_count == 1
    insert_sql = conn.execute.await_args_list[0].args[0]
    assert "ON CONFLICT (trade_id) DO NOTHING" in insert_sql
