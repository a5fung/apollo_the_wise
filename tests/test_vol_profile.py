"""Volume-profile alert context — Slice 1 (docs/analysis/volume_profile_alert_context_2026-07-27.md).

Pins, in order:
  • the measured metric definitions (V1 r5_50, V2 LAB50) against hand-computed known values —
    the math is a faithful port of the design session's cohort probe (vp_measure.py), so a
    drifted definition fails loudly here;
  • the doc's QBTS render (`5d avg 0.46× of 50d · last ≥avg vol day 22 sess ago (1.3×)`), the
    LAB50 ≥3 render threshold, and the none-found honest render;
  • depth honesty: <50 live bars renders `unseasoned` (never a superlative), "1y" only at
    ≥252 pre-alert sessions, else "#1 vol day in Xmo" — and NO rendered variant ever implies
    all-time ("ever"/"HVE" are Slice 2's Polygon-verified claims);
  • the FIXED 0→2× sparkline scale: a ~2× day and a ~0.5× day render differently, and the
    same ratio pattern renders IDENTICALLY across stocks with different absolute volume
    (cross-stock comparability — the whole point vs the min-max NTR spark), rows column-align
    with the NTR spark under dead bars, no lookahead;
  • THE LINE (telemetry-only): the two pinned UPDATE SQLs touch ONLY vol_* columns; the
    annotator is DB-first; per-ticker failures are isolated (never suppress the batch OR the
    tape sibling) and audited; static blast-radius pin incl. "never references
    tape_quality._WIN" (the shared-constant ban);
  • the alert surface (labeled NTR/VOL rows) and the EOD landmark pass (V4 — recap, not
    alert; doc §4: 128/196 alerts fire pre-9:45 where "on pace" is premarket noise).
"""
from __future__ import annotations

import asyncio
import re
from datetime import date, timedelta
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from tests.conftest import make_mock_pool

import agents.market_intelligence.tape_quality as tq
import agents.market_intelligence.vol_profile as vpm
from agents.market_intelligence.vol_profile import (
    _FULL_YEAR_BARS,
    _LAB50_MIN_RENDER,
    _MIN_BASE_BARS,
    _VOL_SPARK_WIN,
    annotate_one_vol_profile,
    eod_vol_landmark_pass,
    format_vol_landmark_line,
    format_vol_line,
    vol_landmark,
    vol_profile,
    vol_sparkline,
)


def _run(coro):
    return asyncio.run(coro)


# ─── Bar fixture builders ─────────────────────────────────────────────────────────────────

_D0 = date(2025, 6, 2)
_ALERT = _D0 + timedelta(days=400)   # far past every fixture bar


def _d(i: int) -> date:
    return _D0 + timedelta(days=i)


def _vbar(i: int, vol: float, close: float = 100.0) -> dict:
    return {"trade_date": _d(i), "open_price": close, "high_price": close * 1.04,
            "low_price": close * 0.96, "close": close, "volume": vol}


def _vols_bars(vols: list[float]) -> list[dict]:
    return [_vbar(i, v) for i, v in enumerate(vols)]


def _flat_bars(n: int = 60, vol: float = 1_000_000) -> list[dict]:
    return _vols_bars([vol] * n)


# ─── V1/V2 — metric definitions against hand-computed values ─────────────────────────────

def test_flat_volume_baseline():
    vp = vol_profile(_flat_bars(60), _ALERT)
    assert vp["hist_n"] == 60
    assert vp["r5_50"] == pytest.approx(1.0)
    assert vp["lab50"] == 0                       # the last pre-alert session itself was ≥avg
    assert vp["lab50_ratio"] == pytest.approx(1.0)


def test_dry_tail_known_values():
    """60×1M with the last 5 sessions at 500K. sma50 = (45·1M + 5·0.5M)/50 = 950K →
    r5_50 = 0.5M/950K; the last ≥avg day is index 54 (its own inclusive 50-SMA is exactly
    1M) → lab50 = 5, ratio 1.0."""
    vols = [1_000_000.0] * 55 + [500_000.0] * 5
    vp = vol_profile(_vols_bars(vols), _ALERT)
    assert vp["r5_50"] == pytest.approx(500_000 / 950_000)
    assert vp["lab50"] == 5
    assert vp["lab50_ratio"] == pytest.approx(1.0)


def test_lab50_ratio_uses_that_days_inclusive_sma():
    """Spike 2M at index 54, then 5 dry 500K sessions: the ≥avg day's ratio divides by ITS
    OWN as-of-day inclusive SMA ((49·1M + 2M)/50 = 1.02M) — the chart-overlay convention."""
    vols = [1_000_000.0] * 54 + [2_000_000.0] + [500_000.0] * 5
    vp = vol_profile(_vols_bars(vols), _ALERT)
    assert vp["lab50"] == 5
    assert vp["lab50_ratio"] == pytest.approx(2_000_000 / 1_020_000)
    assert vp["r5_50"] == pytest.approx(500_000 / 970_000)


def test_lab50_none_found_on_steady_decline():
    """Strictly declining volume: every checkable day sits below its own trailing mean →
    lab50 None with hist_n ≥ 50 — a REAL extreme, distinct from 'not computed'."""
    vols = [1_000_000.0 - 1_000 * i for i in range(60)]
    vp = vol_profile(_vols_bars(vols), _ALERT)
    assert vp["hist_n"] == 60
    assert vp["lab50"] is None and vp["lab50_ratio"] is None
    assert vp["r5_50"] < 1.0


def test_under_50_live_bars_is_unseasoned():
    vp = vol_profile(_flat_bars(49), _ALERT)
    assert vp == {"hist_n": 49}                   # no metrics — never a silent junk value
    vp50 = vol_profile(_flat_bars(50), _ALERT)
    assert vp50["r5_50"] == pytest.approx(1.0)    # exactly 50 → computable


def test_dead_bars_do_not_count_as_live():
    bars = _flat_bars(60)
    for i in range(11):
        bars[i]["volume"] = 0
    assert vol_profile(bars, _ALERT) == {"hist_n": 49}


def test_no_lookahead_alert_day_and_after_invisible():
    base = _flat_bars(60)
    with_future = base + [_vbar(400, 50_000_000.0), _vbar(401, 60_000_000.0)]
    assert with_future[-2]["trade_date"] == _ALERT     # ON the alert day — must be invisible
    assert vol_profile(with_future, _ALERT) == vol_profile(base, _ALERT)


# ─── format_vol_line ──────────────────────────────────────────────────────────────────────

def test_format_line_reproduces_the_doc_qbts_render():
    line = format_vol_line(
        {"hist_n": 273, "r5_50": 0.462, "lab50": 22, "lab50_ratio": 1.28})
    assert line == "VOL: 5d avg 0.46× of 50d · last ≥avg vol day 22 sess ago (1.3×)"


def test_format_line_lab50_render_threshold():
    base = {"hist_n": 100, "r5_50": 1.05, "lab50_ratio": 1.5}
    hidden = format_vol_line({**base, "lab50": _LAB50_MIN_RENDER - 1})
    shown = format_vol_line({**base, "lab50": _LAB50_MIN_RENDER})
    assert hidden == "VOL: 5d avg 1.05× of 50d"        # ≤2 sess = noise, segment hidden
    assert f"last ≥avg vol day {_LAB50_MIN_RENDER} sess ago (1.5×)" in shown


def test_format_line_none_found_states_honest_depth():
    line = format_vol_line({"hist_n": 100, "r5_50": 0.9, "lab50": None, "lab50_ratio": None})
    assert "no ≥avg vol day in last 51 sess" in line   # min(100−49, 260) checkable sessions


def test_format_line_unseasoned_and_empty():
    line = format_vol_line({"hist_n": 49})
    assert line == f"VOL: *unseasoned* (49 sessions < {_MIN_BASE_BARS} — no 50d base)"
    assert format_vol_line(None) == ""
    assert format_vol_line({}) == ""


# ─── V3 — the FIXED-scale sparkline ───────────────────────────────────────────────────────

def test_spark_fixed_scale_midline_and_extremes():
    """Flat volume = every ratio exactly 1.0× → the midline glyph, everywhere. A ~2.4× day
    renders █ and a ~0.5× day renders ▃ — different glyphs for different ratios on an
    ABSOLUTE scale (min-max normalisation would render a lone deviation identically)."""
    assert vol_sparkline(_flat_bars(60), _ALERT) == "▅" * _VOL_SPARK_WIN

    hot = _flat_bars(60)
    hot[59]["volume"] = 2_500_000            # ratio 2.5M/1.03M ≈ 2.43 → clamps to █ (≥2×)
    assert vol_sparkline(hot, _ALERT) == "▅" * 19 + "█"

    dry = _flat_bars(60)
    dry[59]["volume"] = 500_000              # ratio 0.5M/0.99M ≈ 0.51 → ▃
    assert vol_sparkline(dry, _ALERT) == "▅" * 19 + "▃"


def test_spark_identical_across_stocks_with_different_absolute_volume():
    """THE cross-stock property: the same ratio pattern renders the same glyphs whether the
    stock trades 1M or 80M shares."""
    pattern = [800_000.0, 1_300_000.0] * 30
    pattern[50] = 2_500_000.0
    small = _vols_bars(pattern)
    big = _vols_bars([v * 80 for v in pattern])
    s_small, s_big = vol_sparkline(small, _ALERT), vol_sparkline(big, _ALERT)
    assert s_small == s_big
    assert len(s_small) == _VOL_SPARK_WIN


def test_spark_column_aligns_with_ntr_spark_under_dead_bars():
    """Both sparks select the SAME window (last 20 pre-alert slots, tape-_live filter) —
    dead bars drop from both identically, so the labeled rows stay per-session aligned."""
    bars = _flat_bars(60)
    bars[45]["volume"] = 0
    bars[50]["volume"] = 0
    v, n = vol_sparkline(bars, _ALERT), tq.tape_sparkline(bars, _ALERT)
    assert len(v) == len(n) == 18


def test_spark_excludes_alert_day_and_handles_empty():
    base = _flat_bars(60)
    with_alert_day = base + [_vbar(400, 99_000_000.0)]
    assert vol_sparkline(with_alert_day, _ALERT) == vol_sparkline(base, _ALERT)
    assert vol_sparkline([], _ALERT) == ""


# ─── V4 — landmark + depth-honest labelling ───────────────────────────────────────────────

def test_landmark_depth_honest_at_100_bars():
    vols = [1_000_000.0] * 100
    vols[50] = 5_000_000.0
    lm = vol_landmark(_vols_bars(vols), _ALERT, 6_000_000.0)
    assert lm["vs_max"] == pytest.approx(1.2)
    assert lm["depth"] == 100
    line = format_vol_landmark_line("LMRK", lm)
    assert line == "`LMRK` vol 6.0M — #1 vol day in 4mo (1.2× prior max, 5.6× 50d avg)"
    assert "1y" not in line and "ever" not in line.lower()


def test_landmark_one_year_label_requires_252_sessions():
    lm_252 = vol_landmark(_flat_bars(260), _ALERT, 2_000_000.0)
    assert lm_252["depth"] == _FULL_YEAR_BARS
    assert "#1 vol day in 1y" in format_vol_landmark_line("YRLY", lm_252)

    lm_251 = vol_landmark(_flat_bars(251), _ALERT, 2_000_000.0)
    assert "#1 vol day in 11mo" in format_vol_landmark_line("ALMO", lm_251)
    assert "1y" not in format_vol_landmark_line("ALMO", lm_251)


def test_landmark_under_50_bars_renders_unseasoned_never_a_superlative():
    lm = vol_landmark(_flat_bars(49), _ALERT, 2_000_000.0)
    line = format_vol_landmark_line("BABY", lm)
    assert "*unseasoned*" in line and "49 sessions" in line
    assert "#1" not in line and "mo" not in line.split("—")[1].replace("landmark", "")


def test_landmark_never_implies_all_time():
    """No rendered variant may claim HVE/all-time — that is Slice 2's Polygon-verified label."""
    for n in (49, 100, 251, 260):
        lm = vol_landmark(_flat_bars(n), _ALERT, 9_000_000.0)
        line = format_vol_landmark_line("T", lm).lower()
        assert "ever" not in line and "hve" not in line and "all-time" not in line


def test_landmark_does_not_fire_below_prior_max():
    lm = vol_landmark(_flat_bars(100), _ALERT, 900_000.0)   # 0.9× of the 1M max
    assert lm["vs_max"] == pytest.approx(0.9)
    assert format_vol_landmark_line("QUIET", lm) == ""       # telemetry only, no line
    assert vol_landmark(_flat_bars(100), _ALERT, None) is None
    assert vol_landmark(_flat_bars(100), _ALERT, 0) is None
    assert vol_landmark([], _ALERT, 1_000_000.0) is None


# ─── THE LINE — telemetry-only, mechanically pinned ───────────────────────────────────────

def _assert_vol_only_sql(sql: str, expected_assigns: int):
    set_clause = sql.split("SET", 1)[1].split("WHERE", 1)[0]
    assigns = [a.strip() for a in set_clause.split(",") if a.strip()]
    assert len(assigns) == expected_assigns
    for a in assigns:
        col = a.split("=", 1)[0].strip()
        assert col.startswith("vol_"), f"non-vol column in the vol-profile update: {col}"
    for forbidden in ("score_tier", "ep_score", "judge_tier", "grade_engine_authority",
                      "confidence_multiplier", "setup_class", "fire_", "tape_"):
        assert forbidden not in sql


def test_vol_update_sqls_touch_only_vol_columns():
    from agents.market_intelligence.db import (
        EP_ALERT_VOL_LANDMARK_UPDATE_SQL, EP_ALERT_VOL_UPDATE_SQL,
    )
    _assert_vol_only_sql(EP_ALERT_VOL_UPDATE_SQL, 4)
    _assert_vol_only_sql(EP_ALERT_VOL_LANDMARK_UPDATE_SQL, 1)
    assert "vol_alert_vs_max" in EP_ALERT_VOL_LANDMARK_UPDATE_SQL


def test_vol_profile_module_never_touches_decision_paths_or_the_tape_window():
    """Static blast-radius pin (mirrors test_tape_quality's): no grade/judge/entry internals,
    no graded-field assignment — and NEVER a reference to tape_quality's shared `_WIN`
    constant (the sparkline width is a SEPARATE display constant by design; the tape
    thresholds were validated at _WIN=20 and this module must not be able to move them)."""
    src = open(vpm.__file__).read()
    forbidden = (
        "submit_trade_entry", "entry_pipeline", "grade_holistic", "assemble_judge_inputs",
        "resolve_composite_tier", "update_ep_alert_judge_result", "ep_threshold",
        'r["score_tier"] =', "r['score_tier'] =", 'r["ep_score"] =', "r['ep_score'] =",
        "import ep_detector", "from agents.market_intelligence.ep_detector",
        "update_ep_alert_tape_quality",
    )
    for token in forbidden:
        assert token not in src, f"vol_profile.py must never reference {token!r}"
    assert re.search(r"(?<![A-Za-z0-9_])_WIN\b", src) is None, \
        "vol_profile.py must not reference tape_quality._WIN (use _VOL_SPARK_WIN)"
    # The alignment invariant the decoupling protects: both windows are 20 today.
    assert _VOL_SPARK_WIN == tq._WIN == 20


# ─── Annotator behavior (driven from the tape-quality loop, same bars) ───────────────────

def _patch_tape_annotator(monkeypatch, bars_by):
    pool, conn = make_mock_pool()
    conn.execute = AsyncMock()

    async def _fake_pool():
        return pool

    async def _fake_bars(_conn, ticker, _alert_date, days=380):
        return bars_by[ticker]

    monkeypatch.setattr(tq, "get_pool", _fake_pool)
    monkeypatch.setattr(tq, "get_tape_bars_asof", _fake_bars)
    return conn


def _mk_results():
    return [
        {"ticker": "AAA", "alert_date": _ALERT, "ep_score": 74.0, "score_tier": "HIGH"},
        {"ticker": "BBB", "alert_date": _ALERT, "ep_score": 55.0, "score_tier": "MODERATE"},
    ]


def test_vol_failure_isolated_per_ticker_and_never_touches_the_tape_sibling(monkeypatch):
    """One ticker's vol write failing suppresses NEITHER its own tape annotation NOR the
    sibling candidate's vol annotation — and it is counted via vol_profile_shadow_failed."""
    _patch_tape_annotator(monkeypatch, {"AAA": _flat_bars(60), "BBB": _flat_bars(60)})
    audit = AsyncMock()
    monkeypatch.setattr(vpm, "log_audit_event", audit)
    real_update = vpm.update_ep_alert_vol_profile

    async def _boom_aaa(conn_, ticker, alert_date, vp):
        if ticker == "AAA":
            raise RuntimeError("vol write failed")
        await real_update(conn_, ticker, alert_date, vp)

    monkeypatch.setattr(vpm, "update_ep_alert_vol_profile", _boom_aaa)

    results = _mk_results()
    _run(tq.annotate_ep_alerts_tape_quality(results))   # must not raise

    assert results[0]["tape_quality"]["tier"] == "tape_clean"   # tape unaffected
    assert "vol_profile" not in results[0]                      # DB-first: no line w/o row
    assert results[1]["vol_profile"]["r5_50"] == pytest.approx(1.0)
    assert audit.await_count == 1
    assert audit.await_args.args[0] == "vol_profile_shadow_failed"


def test_annotator_attaches_display_key_after_db_write(monkeypatch):
    conn = _patch_tape_annotator(monkeypatch, {"AAA": _flat_bars(60), "BBB": _flat_bars(60)})
    from agents.market_intelligence.db import EP_ALERT_VOL_UPDATE_SQL
    results = _mk_results()
    _run(tq.annotate_ep_alerts_tape_quality(results))

    vol_calls = [c for c in conn.execute.await_args_list
                 if c.args[0] == EP_ALERT_VOL_UPDATE_SQL]
    assert len(vol_calls) == 2
    args = vol_calls[0].args
    assert args[1] == "AAA" and args[2] == _ALERT
    assert args[3] == 60                                  # vol_hist_n
    assert args[4] == pytest.approx(1.0)                  # vol_r5_50
    assert args[5] == 0                                   # vol_lab50
    assert args[6] == pytest.approx(1.0)                  # vol_lab50_ratio
    assert results[0]["vol_profile"]["sparkline"] == "▅" * _VOL_SPARK_WIN


def test_annotate_one_never_raises_on_garbage_bars(monkeypatch):
    audit = AsyncMock()
    monkeypatch.setattr(vpm, "log_audit_event", audit)
    r = {"ticker": "BAD", "alert_date": _ALERT}
    _run(annotate_one_vol_profile(MagicMock(), r, [{"trade_date": _d(0)}]))  # no volume key
    assert "vol_profile" not in r
    assert audit.await_count == 1
    assert audit.await_args.args[0] == "vol_profile_shadow_failed"


# ─── Alert surface — VOL line + labeled column-aligned rows ──────────────────────────────

def _send_alert_capture(ep):
    from agents.market_intelligence import briefing
    captured = {}

    async def _cap(text, *a, **k):
        captured["text"] = text
        return True

    with patch.object(briefing, "send_telegram_message", new=AsyncMock(side_effect=_cap)):
        asyncio.run(briefing.send_ep_alert(ep))
    return captured["text"]


def _annotated_ep(bars):
    tqs = tq.tape_quality(bars, _ALERT)
    tqs["sparkline"] = tq.tape_sparkline(bars, _ALERT)
    vp = vol_profile(bars, _ALERT)
    vp["sparkline"] = vol_sparkline(bars, _ALERT)
    return {"ticker": "VOLT", "score_tier": "HIGH", "gap_pct": 11.0, "ep_score": 78,
            "catalyst_quality": "strong", "rel_volume": 3.0,
            "tape_quality": tqs, "vol_profile": vp}


def test_ep_alert_renders_vol_line_and_aligned_labeled_sparks():
    text = _send_alert_capture(_annotated_ep(_flat_bars(60)))
    assert "VOL: 5d avg 1.00× of 50d" in text
    rows = text.split("\n")
    ntr_rows = [l for l in rows if l.startswith("`NTR ")]
    vol_rows = [l for l in rows if l.startswith("`VOL ")]
    assert len(ntr_rows) == 1 and len(vol_rows) == 1
    assert len(ntr_rows[0]) == len(vol_rows[0])       # 4-char labels + equal windows align
    assert vol_rows[0] == "`VOL " + "▅" * _VOL_SPARK_WIN + "`"


def test_ep_alert_with_only_vol_annotation_renders_labeled_vol_row():
    ep = _annotated_ep(_flat_bars(60))
    del ep["tape_quality"]
    text = _send_alert_capture(ep)
    assert "TAPE:" not in text and "`NTR " not in text
    assert "VOL: 5d avg 1.00× of 50d" in text
    assert "`VOL " + "▅" * _VOL_SPARK_WIN + "`" in text


# ─── EOD landmark pass (V4 — recap surface) ──────────────────────────────────────────────

def _patch_eod(monkeypatch, alerts, snapshot, bars):
    pool, conn = make_mock_pool()
    conn.fetch = AsyncMock(return_value=alerts)

    async def _fake_pool():
        return pool

    monkeypatch.setattr(vpm, "get_pool", _fake_pool)
    import agents.market_intelligence.collector as collector
    snap_mock = AsyncMock(return_value=snapshot)
    monkeypatch.setattr(collector, "get_snapshot_all", snap_mock)
    monkeypatch.setattr(vpm, "get_tape_bars_asof", AsyncMock(return_value=bars))
    writer = AsyncMock()
    monkeypatch.setattr(vpm, "update_ep_alert_vol_landmark", writer)
    audit = AsyncMock()
    monkeypatch.setattr(vpm, "log_audit_event", audit)
    return conn, snap_mock, writer, audit


def _absi_bars():
    vols = [5_000_000.0] * 260
    vols[100] = 23_800_000.0                      # the pre-alert max
    return _vols_bars(vols)


def test_eod_pass_renders_depth_honest_line_and_writes_telemetry(monkeypatch):
    conn, _snap, writer, _audit = _patch_eod(
        monkeypatch, [{"ticker": "ABSI"}],
        {"ABSI": {"day": {"v": 38_100_000}}}, _absi_bars())

    lines = _run(eod_vol_landmark_pass(_ALERT))

    assert lines == ["`ABSI` vol 38.1M — #1 vol day in 1y (1.6× prior max, 7.6× 50d avg)"]
    writer.assert_awaited_once()
    w_args = writer.await_args.args
    assert w_args[1] == "ABSI" and w_args[2] == _ALERT
    assert w_args[3] == pytest.approx(38_100_000 / 23_800_000)


def test_eod_pass_writes_telemetry_even_when_no_landmark_fires(monkeypatch):
    """The accrual IS the point (doc §6): sub-1.0× ratios persist, nothing renders."""
    _conn, _snap, writer, _audit = _patch_eod(
        monkeypatch, [{"ticker": "ABSI"}],
        {"ABSI": {"day": {"v": 10_000_000}}}, _absi_bars())

    lines = _run(eod_vol_landmark_pass(_ALERT))

    assert lines == []
    assert writer.await_args.args[3] == pytest.approx(10_000_000 / 23_800_000)


def test_eod_pass_snapshot_gaps_and_outage(monkeypatch):
    # Ticker missing from the snapshot → skipped honestly (no write, no line).
    _conn, _snap, writer, audit = _patch_eod(
        monkeypatch, [{"ticker": "GONE"}], {"OTHER": {"day": {"v": 1}}}, _absi_bars())
    assert _run(eod_vol_landmark_pass(_ALERT)) == []
    writer.assert_not_awaited()

    # Empty snapshot (an OUTAGE) → audited, never a silent "no landmarks today".
    _conn, _snap, writer, audit = _patch_eod(
        monkeypatch, [{"ticker": "ABSI"}], {}, _absi_bars())
    assert _run(eod_vol_landmark_pass(_ALERT)) == []
    assert audit.await_count == 1
    assert audit.await_args.args[0] == "vol_landmark_eod_failed"


def test_eod_pass_no_alerts_never_fetches_the_snapshot(monkeypatch):
    _conn, snap_mock, _writer, _audit = _patch_eod(monkeypatch, [], {}, [])
    assert _run(eod_vol_landmark_pass(_ALERT)) == []
    snap_mock.assert_not_awaited()
