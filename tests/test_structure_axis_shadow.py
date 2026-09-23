"""#330 structure-axis SHADOW build (ADR 0016). Focused tests for the meta-rubric structure
axis — the #329 sibling of the #328 theme axis:

  • compute_structure_features() — AS-OF (no-lookahead) Stage-2 / RMV-tightness / extension
    reads from an ascending OHLCV bar list, reusing flag_detector._compute_rmv and
    parabolic_detector._sma directly (not reimplemented);
  • structure_axis_credit() — the pure, boost-only stage2 x tightness -> credit decision, one
    test per ADR 0016 v1-mapping bucket + a boost-only sweep pinning no negative path exists;
  • log_structure_axis_shadow() — the SHADOW writer: fires exactly one upsert, is idempotent
    on (ticker, alert_date), NEVER raises, and NEVER mutates the `r` dict it's handed (THE
    LINE — the live grade path must be untouched).

SHADOW ONLY — none of this touches the live grade / judge output / trade state. See
docs/decisions/0016-structure-axis-meta-rubric.md for the full design.
"""
from __future__ import annotations

import asyncio
import copy
from datetime import date, timedelta
from unittest.mock import AsyncMock

from tests.conftest import make_mock_pool

from agents.market_intelligence.structure_axis_shadow import (
    _RMV_LOOKBACK,
    _SMA200_WINDOW,
    _TIGHT_RMV_MAX,
    compute_structure_features,
    log_structure_axis_shadow,
    structure_axis_credit,
)


def _run(coro):
    return asyncio.run(coro)


# ─── Bar fixture builders ──────────────────────────────────────────────────────────────────

def _bar(trade_date, close, high, low, volume=100_000.0):
    return {
        "trade_date": trade_date, "open_price": close, "high_price": high,
        "low_price": low, "close": close, "volume": volume,
    }


def _make_uptrend_bars(n=220, tail_tight: "bool | None" = None):
    """Monotonically rising closes (a clean Stage-2 candidate: prior_close ends near the ATH
    and comfortably above a rising SMA-200). `tail_tight`: True -> last 3 bars' daily range is
    tight (~0.2%) vs a ~2% baseline (a real RMV coil); False -> last 3 bars match the ~2%
    baseline (no contraction); None -> uniform ~2% range throughout (no tail distinction,
    used for the insufficient-history variants)."""
    start = date(2025, 1, 1)
    bars = []
    for i in range(n):
        c = 50.0 + i * 0.3
        if tail_tight is True and i >= n - 3:
            spread = 0.002
        elif tail_tight is False and i >= n - 3:
            spread = 0.02
        else:
            spread = 0.02
        bars.append(_bar(start + timedelta(days=i), c, c * (1 + spread / 2), c * (1 - spread / 2)))
    return bars


def _make_crash_bars(n=220):
    """Rises to a peak then crashes over the final 30 bars to ~20% of the peak — a dead-cat
    bounce shape (the #356 NCI lesson): short MAs alone wouldn't catch this, but prior_close
    ends well below a 200d SMA computed over the mixed rise+crash window."""
    start = date(2025, 1, 1)
    peak_idx = n - 30
    peak = 50.0 + peak_idx * 0.5
    closes = []
    for i in range(n):
        if i <= peak_idx:
            closes.append(50.0 + i * 0.5)
        else:
            frac = (i - peak_idx) / (n - 1 - peak_idx)
            closes.append(peak * (1 - 0.8 * frac))
    return [
        _bar(start + timedelta(days=i), c, c * 1.02, c * 0.98)
        for i, c in enumerate(closes)
    ]


# ─── compute_structure_features (pure logic) ──────────────────────────────────────────────

def test_insufficient_history_everything_none():
    """Empty bar list -> every field None, never a guessed value."""
    feats = compute_structure_features([], date(2026, 6, 20))
    assert feats == {
        "prior_close": None, "stage2": None, "sma_200": None, "trailing_high": None,
        "rmv_15": None, "rmv_tight": None, "extension_ratio": None, "sma_10": None,
    }


def test_short_history_stage2_and_rmv_uncomputable_but_extension_is():
    """Fewer than 200 bars -> sma_200/stage2 stay None (real absence, not a guess), and fewer
    than 16 bars -> rmv_15 stays None too, but extension (needs only 10 bars) IS computable —
    each component degrades independently on its own data floor."""
    bars = _make_uptrend_bars(n=12)
    feats = compute_structure_features(bars, date(2026, 6, 20))
    assert feats["stage2"] is None
    assert feats["sma_200"] is None
    assert feats["rmv_15"] is None
    assert feats["extension_ratio"] is not None  # 12 >= _SMA10_WINDOW(10)


def test_stage2_true_and_tight_base():
    """Clean Stage-2 uptrend + a genuinely tight recent 3-bar window vs the 15-bar baseline
    -> stage2 True, rmv_tight True (RMV-15 <= the reused ENTRY_RMV_MAX cutline)."""
    bars = _make_uptrend_bars(n=_SMA200_WINDOW + 20, tail_tight=True)
    feats = compute_structure_features(bars, date(2026, 6, 20))
    assert feats["stage2"] is True
    assert feats["rmv_15"] is not None
    assert feats["rmv_tight"] is True
    assert feats["rmv_15"] <= _TIGHT_RMV_MAX
    assert feats["extension_ratio"] is not None


def test_stage2_true_but_base_not_tight():
    """Same Stage-2 uptrend, but the recent 3-bar window matches the (not contracted) 15-bar
    baseline -> stage2 True, rmv_tight False."""
    bars = _make_uptrend_bars(n=_SMA200_WINDOW + 20, tail_tight=False)
    feats = compute_structure_features(bars, date(2026, 6, 20))
    assert feats["stage2"] is True
    assert feats["rmv_15"] is not None
    assert feats["rmv_tight"] is False
    assert feats["rmv_15"] > _TIGHT_RMV_MAX


def test_stage2_false_on_dead_cat_crash():
    """The #356 NCI lesson fixture: prior_close ends well below a 200d SMA computed over a
    rise-then-crash window -> stage2 False (never a penalty on its own — that's
    structure_axis_credit's job, this just reports the read)."""
    bars = _make_crash_bars(n=_SMA200_WINDOW + 20)
    feats = compute_structure_features(bars, date(2026, 6, 20))
    assert feats["stage2"] is False
    assert feats["sma_200"] is not None


def test_rmv_lookback_boundary_uses_the_prior_idx_window():
    """RMV needs `idx >= _RMV_LOOKBACK` (today_idx counts as one of the lookback bars) —
    pin the exact boundary against flag_detector._compute_rmv's own `today_idx < lookback`
    guard so this module's floor can't silently drift from the SSoT primitive's."""
    just_short = _make_uptrend_bars(n=_RMV_LOOKBACK)  # idx = n-1 = lookback-1 < lookback
    feats_short = compute_structure_features(just_short, date(2026, 6, 20))
    assert feats_short["rmv_15"] is None

    just_enough = _make_uptrend_bars(n=_RMV_LOOKBACK + 1)  # idx = lookback -> computable
    feats_enough = compute_structure_features(just_enough, date(2026, 6, 20))
    assert feats_enough["rmv_15"] is not None


# ─── structure_axis_credit (pure, boost-only) ──────────────────────────────────────────────

def test_credit_stage2_unknown_zero_credit():
    credit = structure_axis_credit({"stage2": None, "rmv_tight": None})
    assert credit == {
        "credit_steps": 0, "marker": "unknown",
        "reason": credit["reason"],  # message content asserted loosely below
    }
    assert "not computable" in credit["reason"]


def test_credit_stage2_tight_full_boost():
    credit = structure_axis_credit({"stage2": True, "rmv_tight": True})
    assert credit["credit_steps"] == 1
    assert credit["marker"] == "stage2_tight"


def test_credit_stage2_only_near_miss_no_credit():
    credit = structure_axis_credit({"stage2": True, "rmv_tight": False})
    assert credit["credit_steps"] == 0
    assert credit["marker"] == "stage2_only_near_miss"


def test_credit_stage2_only_rmv_unknown_treated_as_near_miss():
    """Stage-2 True but RMV itself uncomputable -> still the near-miss band (not the full
    boost) — an unknown tightness read must never be treated as tight."""
    credit = structure_axis_credit({"stage2": True, "rmv_tight": None})
    assert credit["credit_steps"] == 0
    assert credit["marker"] == "stage2_only_near_miss"


def test_credit_no_stage2_zero_credit():
    credit = structure_axis_credit({"stage2": False, "rmv_tight": True})
    assert credit["credit_steps"] == 0
    assert credit["marker"] == "no_stage2"


def test_credit_never_negative_sweep():
    """Boost-only hard guardrail: no combination of inputs ever yields credit_steps < 0."""
    for stage2 in (None, True, False):
        for rmv_tight in (None, True, False):
            credit = structure_axis_credit({"stage2": stage2, "rmv_tight": rmv_tight})
            assert credit["credit_steps"] >= 0
            assert credit["marker"] in (
                "unknown", "stage2_tight", "stage2_only_near_miss", "no_stage2",
            )


# ─── log_structure_axis_shadow (writer; mocked pool/accessor) ─────────────────────────────

def _patch_bars(monkeypatch, bars):
    async def _fake_bars(_conn, _ticker, _alert_date, days=380):
        return bars
    monkeypatch.setattr(
        "agents.market_intelligence.structure_axis_shadow.get_daily_bars_asof", _fake_bars)


def test_logger_fires_and_writes_row(monkeypatch):
    pool, conn = make_mock_pool()
    conn.execute = AsyncMock()
    bars = _make_uptrend_bars(n=_SMA200_WINDOW + 20, tail_tight=True)
    _patch_bars(monkeypatch, bars)

    r = {"ticker": "TICK", "alert_date": date(2026, 6, 20), "score_tier": "HIGH"}
    _run(log_structure_axis_shadow(conn, r))

    assert conn.execute.await_count == 1
    args = conn.execute.await_args.args
    # positional: sql, ticker, alert_date, grade, prior_close, stage2, sma_200,
    #             trailing_high, rmv_15, rmv_tight, extension_ratio, sma_10,
    #             credit_steps, marker, reason
    assert args[1] == "TICK"
    assert args[2] == date(2026, 6, 20)
    assert args[3] == "HIGH"
    assert args[5] is True                # stage2
    assert args[9] is True                # rmv_tight
    assert args[12] == 1                  # credit_steps
    assert args[13] == "stage2_tight"      # marker
    assert "ON CONFLICT (ticker, alert_date) DO UPDATE" in args[0]


def test_missing_ticker_or_alert_date_is_a_noop(monkeypatch):
    pool, conn = make_mock_pool()
    conn.execute = AsyncMock()
    _patch_bars(monkeypatch, [])

    _run(log_structure_axis_shadow(conn, {"ticker": None, "alert_date": date(2026, 6, 20)}))
    _run(log_structure_axis_shadow(conn, {"ticker": "X", "alert_date": None}))
    assert conn.execute.await_count == 0


def test_upsert_is_idempotent_on_ticker_date(monkeypatch):
    """The EP scan re-runs every 5 min -> the writer must upsert (latest-scan-wins); the real
    table's UNIQUE (ticker, alert_date) collapses repeated calls to one row."""
    pool, conn = make_mock_pool()
    conn.execute = AsyncMock()
    bars = _make_uptrend_bars(n=_SMA200_WINDOW + 20, tail_tight=True)
    _patch_bars(monkeypatch, bars)

    r = {"ticker": "RPT", "alert_date": date(2026, 6, 20), "score_tier": "HIGH"}
    _run(log_structure_axis_shadow(conn, r))
    _run(log_structure_axis_shadow(conn, r))  # second 5-min cycle

    assert conn.execute.await_count == 2
    sql = conn.execute.await_args.args[0]
    assert "ON CONFLICT (ticker, alert_date) DO UPDATE" in sql


def test_writer_never_raises_on_db_error(monkeypatch):
    """SHADOW contract: a telemetry failure must NOT propagate into the grade path."""
    pool, conn = make_mock_pool()
    conn.execute = AsyncMock(side_effect=RuntimeError("db down"))
    _patch_bars(monkeypatch, _make_uptrend_bars(n=_SMA200_WINDOW + 20, tail_tight=True))
    monkeypatch.setattr(
        "agents.market_intelligence.structure_axis_shadow.log_audit_event", AsyncMock())

    r = {"ticker": "ERR", "alert_date": date(2026, 6, 20), "score_tier": "HIGH"}
    _run(log_structure_axis_shadow(conn, r))  # must not raise


def test_writer_never_raises_when_bars_accessor_fails(monkeypatch):
    """A read-side failure (e.g. DB hiccup fetching history) must also fail closed to
    telemetry, not propagate into the judge-shadow caller."""
    pool, conn = make_mock_pool()
    conn.execute = AsyncMock()

    async def _boom(_conn, _ticker, _alert_date, days=380):
        raise RuntimeError("history fetch failed")
    monkeypatch.setattr(
        "agents.market_intelligence.structure_axis_shadow.get_daily_bars_asof", _boom)
    monkeypatch.setattr(
        "agents.market_intelligence.structure_axis_shadow.log_audit_event", AsyncMock())

    r = {"ticker": "ERR2", "alert_date": date(2026, 6, 20), "score_tier": "MODERATE"}
    _run(log_structure_axis_shadow(conn, r))
    assert conn.execute.await_count == 0


# ─── THE LINE — zero-live-mutation pin ─────────────────────────────────────────────────────

def test_shadow_never_mutates_r(monkeypatch):
    """THE LINE pin: the shadow computation must leave the caller's `r` dict byte-identical —
    the live grade the judge/floor/every downstream consumer sees is untouched, regardless of
    what structure credit fires."""
    pool, conn = make_mock_pool()
    conn.execute = AsyncMock()
    _patch_bars(monkeypatch, _make_uptrend_bars(n=_SMA200_WINDOW + 20, tail_tight=True))

    r = {
        "ticker": "PIN", "alert_date": date(2026, 6, 20), "score_tier": "HIGH",
        "fire_axes": ["catalyst"], "judge_rationale": "strong 8-K",
    }
    r_before = copy.deepcopy(r)
    _run(log_structure_axis_shadow(conn, r))
    assert r == r_before


def test_module_never_touches_live_judge_internals():
    """Static pin: the shadow module must not import or reference any live judge/grade-
    building internals — a textual grep, cheap and durable against refactors that would
    otherwise silently widen this module's blast radius onto the 9:45 live grade path."""
    import agents.market_intelligence.structure_axis_shadow as mod
    src = open(mod.__file__).read()
    forbidden = (
        "_build_judge_prompt", "assemble_judge_inputs", "grade_holistic",
        'r["score_tier"] =', "r['score_tier'] =",
    )
    for token in forbidden:
        assert token not in src, f"structure_axis_shadow.py must never reference {token!r}"
