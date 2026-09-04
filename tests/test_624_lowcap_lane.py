"""#624 (2026-09-04) — the MAGNA53 low-cap lane, SHADOW ONLY: tick recorder + nightly walker.

THE LINE — the properties this file proves at the code layer:
  1. BYTE-IDENTITY OF THE ACTING PATH: `run_ep_scan` is RUN end to end (the first test in the
     repo to do so) three times on the same fixture board — lane ON, lane OFF
     (`should_run` False), lane RAISING — and the returned results, every captured
     mi_ep_scan_log row, and every insert_ep_alert call are identical across the three.
     The fixture board dies at the RVOL@T gate (the earliest kill in the graded loop), so
     the grading / judge path is NOT exercised here — stated, not hidden; the structural pins
     in part 4 cover placement + non-mutation for everything downstream.
  2. NON-MUTATION: the hook snapshots the board; no candidate dict changes; no scan map changes.
  3. THE `_mcap_cache` HAZARD: the lane never calls check_filters without skip_mcap=True and
     never names the acting cache; a failed cap read records nothing and retries.
  4. FAIL-OPEN: a raising lane is a counted, audited warning — the scan returns the same result.
  5. SURVIVORSHIP + TICK-TIME: the walker submits from the row's OWN tick, marks >=09:45 ticks
     out-of-window without simulating, writes open walks with a mark, records the overnight
     tail and the offering flag.
  6. REGISTRATIONS: job, liveness, deploy-gate SQL, DDL columns, exec list, importer boundaries,
     the registry seed (median gate nulled), the adapter, the YAML gate's #545 binding, the
     SSoT sentence, and NO ADMISSION_SWITCHES row at shadow.
"""
from __future__ import annotations

import asyncio
import copy
import inspect
import json
import re
import sys
from datetime import date, datetime, time, timedelta
from pathlib import Path
from unittest.mock import AsyncMock, patch
from zoneinfo import ZoneInfo

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from agents.market_intelligence import db
from agents.market_intelligence import ep_detector
from agents.market_intelligence import lowcap_lane as lane
from agents.market_intelligence import lowcap_lane_replay as lcl
from agents.market_intelligence import rule_eras

_ET = ZoneInfo("America/New_York")
_REPO = Path(__file__).resolve().parent.parent
_LANE = _REPO / "agents" / "market_intelligence" / "lowcap_lane.py"
_WALKER = _REPO / "agents" / "market_intelligence" / "lowcap_lane_replay.py"

SESSION_DATE = date(2026, 9, 3)     # Thursday, era C, a real NYSE trading day (CHPT's day)
TODAY = date(2026, 9, 4)
TICK = datetime(2026, 9, 3, 9, 31, 12, tzinfo=_ET)


@pytest.fixture(autouse=True)
def _real_filter_constants(monkeypatch):
    """tests/conftest.py stubs agents.market_intelligence.backtester.filters; since #624 the
    stub carries the REAL threshold constants (read off filters.py's source), and this fixture
    patches a faithful validate_orb_entry for the walker — the `_real_orb_validation` pattern
    of the sibling test files — plus fresh per-day lane state."""
    assert lane.LANE_MAX_MARKET_CAP == 500_000_000      # conftest reads the REAL floor off filters.py
    assert lane.MIN_ADV_DOLLAR_VOLUME == 1_000_000 and lane.MAX_ATR_PCT == 15.0

    def _validate(orb_high, orb_low, atr_14):
        orb_range = orb_high - orb_low
        if orb_range <= 0:
            return False, "setup:zero_range"
        if atr_14 and atr_14 > 0 and orb_range > 1.5 * atr_14:
            return False, f"setup:stop_too_wide: {orb_range:.2f} > 1.5x ATR {atr_14:.2f}"
        return True, None
    monkeypatch.setattr(lcl, "validate_orb_entry", _validate)
    # fresh per-day lane state per test
    monkeypatch.setattr(lane, "_evaluated_date", None)
    monkeypatch.setattr(lane, "_evaluated", set())
    monkeypatch.setattr(lane, "_cap_cache_date", None)
    monkeypatch.setattr(lane, "_cap_cache", {})
    monkeypatch.setattr(lane, "_cap_failures", {})


def _cand(ticker, gap=20.0, prev_close=6.0, today_volume=2_000_000, adv=None, adv_source="pending"):
    return {"ticker": ticker, "gap_pct": gap, "gap_pct_rt": None, "gap_pct_delayed": gap,
            "price_source": "polygon_delayed", "prev_close": prev_close,
            "current_price": round(prev_close * (1 + gap / 100), 2),
            "today_volume": today_volume, "adv": adv, "adv_source": adv_source,
            "prev_day_volume": 500_000, "rel_volume": None, "projected_vol_multiple": None}


HIST_90 = [1_000_000.0] * 9 + [3_000_000.0]      # 2,000,000 today -> 90.0th percentile exactly
HIST_LOW = [3_000_000.0] * 10                     # 2,000,000 today -> 0th percentile


# ── Part 1: the pure rule ─────────────────────────────────────────────────────────────


def test_rule_thresholds_are_the_evidence_cell():
    assert lane.LANE_MIN_GAP_PCT == 15.0
    assert lane.LANE_MIN_VOL_PERCENTILE == 90.0
    assert lane.LANE_MIN_PREV_CLOSE == ep_detector.MIN_PREV_CLOSE == 5.0


def test_free_terms_admit_exactly_at_the_boundaries():
    v = lane.free_terms(_cand("AAAA", gap=15.0), HIST_90)
    assert v.meets_free_terms and v.vol_percentile == 90.0 and v.vol_history_n == 10
    assert not lane.free_terms(_cand("AAAA", gap=14.99), HIST_90).meets_free_terms
    hist_89 = [1_000_000.0] * 8 + [3_000_000.0] * 2          # 80th percentile
    v = lane.free_terms(_cand("AAAA", gap=20.0), hist_89)
    assert not v.meets_free_terms and "vol_percentile_below_lane_floor" in v.fail_reasons
    v = lane.free_terms(_cand("AAAA", gap=20.0, prev_close=4.99), HIST_90)
    assert not v.meets_free_terms and "prev_close_below_floor" in v.fail_reasons


def test_no_volume_history_never_reads_as_conviction():
    """`_volume_percentile` returns a neutral 50 on an empty history — which cannot clear 90;
    the verdict says WHY (vol_history_n=0) rather than guessing."""
    v = lane.free_terms(_cand("AAAA", gap=30.0), [])
    assert not v.meets_free_terms and v.vol_percentile is None and v.vol_history_n == 0
    assert "no_volume_history" in v.fail_reasons


def test_screen_board_is_a_session_reading_only():
    board = lane.snapshot_board([_cand("AAAA")])
    assert lane.screen_board(board, {"AAAA": HIST_90}, None) == []           # pre-market: nothing
    out = lane.screen_board(board, {"AAAA": HIST_90}, 1)
    assert [v.ticker for v in out if v.meets_free_terms] == ["AAAA"]


def test_snapshot_board_copies_never_aliases_the_acting_dicts():
    c = _cand("AAAA")
    before = copy.deepcopy(c)
    snap = lane.snapshot_board([c])[0]
    snap["gap_pct"] = 999.0
    snap["extra"] = "x"
    assert c == before


def test_quoted_spread_bps_needs_both_sides():
    assert lane.quoted_spread_bps(9.95, 10.05) == pytest.approx(100.0, abs=0.01)
    assert lane.quoted_spread_bps(0, 10.05) is None
    assert lane.quoted_spread_bps(10.10, 10.05) is None       # crossed book is no information


def test_blocking_filters_carry_value_and_threshold_and_omit_uncomputed_gates():
    bf = lane.blocking_filters_for(
        extension_pct=61.0, on_cooldown=True, days_since_prior_alert=12,
        quality_reason="filter:adv_too_low: $400,000", quality_adv_dollar=400_000.0,
        atr_pct=None, acting_rank=57, ma_flag=True, today_volume=10_000)
    gates = {b["gate"]: b for b in bf}
    assert gates["extended"]["value"] == 61.0 and gates["extended"]["threshold"] == ep_detector.MAX_EXTENSION_PCT
    assert gates["cooldown"]["value"] == 12 and gates["cooldown"]["threshold"] == ep_detector.EP_COOLDOWN_DAYS
    assert gates["adv_too_low"]["value"] == 400_000.0 and gates["adv_too_low"]["threshold"] == 1_000_000
    assert gates["shortlist_cap"]["value"] == 57 and gates["shortlist_cap"]["threshold"] == 20
    assert "mna" in gates and gates["pm_shares_floor"]["value"] == 10_000
    assert "atr_too_high" not in gates                       # never computed past the ADV kill
    clean = lane.blocking_filters_for(
        extension_pct=5.0, on_cooldown=False, days_since_prior_alert=None, quality_reason=None,
        quality_adv_dollar=5e6, atr_pct=8.0, acting_rank=3, ma_flag=False, today_volume=2e6)
    assert clean == []


# ── Part 2: enrichment — the cap hazard, dedupe, the tick cap, the row ────────────────


def _ctx(**over):
    base = dict(today=SESSION_DATE, now_et=TICK, minutes_since_open=1, extension_map={},
                cooldown_tickers=set(), cooldown_last_alert={}, rank_by_prescore={},
                rank_by_gap={}, acting_rank={}, regime_label="Bull")
    base.update(over)
    return base


def _wire_enrich(monkeypatch, *, caps: dict, quality=(True, None), metrics=None,
                 ma=(False, None), rt=None, quotes=None, prior=None, existing=()):
    written, audits = [], []

    async def _cap(ticker):
        v = caps.get(ticker, "raise")
        if v == "raise":
            raise RuntimeError("yfinance down")
        return {"marketCap": v}

    async def _cf(ticker, d, skip_mcap=False, metrics=None):
        assert skip_mcap is True, "the lane must NEVER let check_filters touch the acting cap cache"
        if metrics is not None:
            metrics.update(metrics_ or {})
        return quality

    metrics_ = metrics
    monkeypatch.setattr(lane, "get_fmp_profile", _cap)
    monkeypatch.setattr(lane, "check_filters", _cf)
    monkeypatch.setattr(lane, "is_likely_ma", AsyncMock(return_value=ma))
    monkeypatch.setattr(lane, "get_alpaca_minute_cum_volumes", AsyncMock(return_value=rt or {}))
    monkeypatch.setattr(lane, "get_alpaca_latest_quotes", AsyncMock(return_value=quotes or {}))
    monkeypatch.setattr(lane, "get_lowcap_lane_prior_signal_dates", AsyncMock(return_value=prior or {}))
    monkeypatch.setattr(lane, "get_lowcap_lane_signal_tickers", AsyncMock(return_value=set(existing)))

    async def _ins(rows):
        written.extend(rows)
        return len(rows)

    async def _audit(ev, summary, detail=""):
        audits.append((ev, summary, detail))
    monkeypatch.setattr(lane, "insert_lowcap_lane_signals", _ins)
    monkeypatch.setattr(lane, "log_audit_event", _audit)
    return written, audits


@pytest.mark.asyncio
async def test_admitted_name_writes_one_row_with_the_full_record(monkeypatch):
    written, audits = _wire_enrich(
        monkeypatch, caps={"CHPT": 134_000_000},
        quality=(False, "filter:atr_too_high: 22.1% > 15.0%"),
        metrics={"quality_adv_dollar": 8_500_000.0, "atr_pct": 22.1},
        ma=(False, None),
        rt={"CHPT": {"pm_vol": 400_000, "session_vol": 569_501, "pm_bars": 90, "session_bars": 1}},
        quotes={"CHPT": {"bid": 6.90, "ask": 6.95, "bid_size": 300.0, "ask_size": 1200.0,
                         "ts": TICK}},
        prior={"CHPT": SESSION_DATE - timedelta(days=45)})
    hist_chpt = [400_000.0] * 9 + [1_500_000.0]        # 969,501 today -> 90.0th percentile exactly
    v = lane.free_terms(_cand("CHPT", gap=32.95, prev_close=5.19, today_volume=969_501), hist_chpt)
    assert v.meets_free_terms
    out = await lane.enrich_and_record(
        [v], {"CHPT": lane.snapshot_board([_cand("CHPT", gap=32.95, prev_close=5.19, today_volume=969_501)])[0]},
        **_ctx(extension_map={"CHPT": 4.0}, cooldown_last_alert={},
               rank_by_prescore={"CHPT": 41}, rank_by_gap={"CHPT": 1}, acting_rank={"CHPT": 41}))
    assert out["admitted"] == 1 and out["written"] == 1 and out["errors"] == 0
    r = written[0]
    assert r["ticker"] == "CHPT" and r["scan_date"] == SESSION_DATE and r["tick_wallclock_et"] == TICK
    assert r["market_cap"] == 134_000_000 and r["market_cap_source"] == "yfinance_profile"
    assert r["acting_volume_source"] == "delayed" and r["today_volume_delayed"] == 969_501
    assert r["today_volume_rt"] == 969_501.0 and r["rt_session_bars"] == 1
    assert r["vol_percentile"] == 90.0 and r["vol_history_n"] == 10
    assert r["extension_pct"] == pytest.approx((5.19 - 4.0) / 4.0 * 100, abs=0.01)
    assert r["atr_pct"] == 22.1 and r["quality_adv_dollar"] == 8_500_000.0
    gates = {b["gate"] for b in r["blocking_filters"]}
    assert gates == {"atr_too_high", "shortlist_cap"}
    assert r["in_shortlist"] is False and r["rank_by_prescore"] == 41 and r["rank_by_gap"] == 1
    assert r["quoted_spread_bps"] == pytest.approx((6.95 - 6.90) / 6.925 * 1e4, abs=0.01)
    assert r["bid_size"] == 300.0 and r["ask_size"] == 1200.0
    assert r["days_since_prior_lane_signal"] == 45 and r["days_since_prior_alert"] is None
    assert r["ma_flag"] is False
    assert r["admission_era"] == rule_eras.admission_era_as_of(SESSION_DATE)
    assert r["lane_gap_floor_pct"] == 15.0 and r["lane_vol_percentile_floor"] == 90.0
    assert r["lane_max_market_cap"] == 500_000_000.0 and r["lane_rule_version"] == "lane_v1"
    assert any(ev == "lowcap_lane_signal_recorded" for ev, *_ in audits)


@pytest.mark.asyncio
async def test_cap_at_or_above_the_floor_is_not_the_lane(monkeypatch):
    written, _ = _wire_enrich(monkeypatch, caps={"BIGX": 500_000_000})
    v = lane.free_terms(_cand("BIGX"), HIST_90)
    out = await lane.enrich_and_record([v], {"BIGX": lane.snapshot_board([_cand("BIGX")])[0]}, **_ctx())
    assert out["rejected_cap"] == 1 and written == []
    assert "BIGX" in lane._evaluated                 # decided for the day — not re-read every tick


@pytest.mark.asyncio
async def test_unreadable_cap_records_nothing_and_is_retried_next_tick(monkeypatch):
    """The _mcap_cache hazard, inverted: a failed read is NEVER 'under the floor' and NEVER
    'evaluated' — it is audited and retried."""
    written, audits = _wire_enrich(monkeypatch, caps={})       # every read raises
    v = lane.free_terms(_cand("FAIL"), HIST_90)
    out = await lane.enrich_and_record([v], {"FAIL": lane.snapshot_board([_cand("FAIL")])[0]}, **_ctx())
    assert out["cap_unavailable"] == 1 and written == []
    assert "FAIL" not in lane._evaluated
    assert any(ev == "lowcap_lane_cap_unavailable" for ev, *_ in audits)
    # ...bounded: after MAX_CAP_RETRIES_PER_DAY unreadable ticks the name is given up for the day
    for _ in range(lane.MAX_CAP_RETRIES_PER_DAY - 1):
        await lane.enrich_and_record([v], {"FAIL": lane.snapshot_board([_cand("FAIL")])[0]}, **_ctx())
    assert "FAIL" in lane._evaluated and written == []
    assert sum(1 for ev, *_ in audits if ev == "lowcap_lane_cap_unavailable") == lane.MAX_CAP_RETRIES_PER_DAY
    assert "giving up" in audits[-1][1]


@pytest.mark.asyncio
async def test_per_day_dedupe_reads_the_table_and_the_process_set(monkeypatch):
    written, _ = _wire_enrich(monkeypatch, caps={"AAAA": 1e8, "BBBB": 1e8}, existing={"AAAA"})
    lane._evaluated_date, lane._evaluated = SESSION_DATE, {"BBBB"}
    vs = [lane.free_terms(_cand(t), HIST_90) for t in ("AAAA", "BBBB")]
    out = await lane.enrich_and_record(vs, {t: lane.snapshot_board([_cand(t)])[0] for t in ("AAAA", "BBBB")}, **_ctx())
    assert out["deduped"] == 2 and out["enriched"] == 0 and written == []


@pytest.mark.asyncio
async def test_tick_cap_bounds_the_fanout_and_defers_the_rest(monkeypatch):
    tickers = [f"T{i:02d}" for i in range(lane.MAX_ENRICH_PER_TICK + 3)]
    written, audits = _wire_enrich(monkeypatch, caps={t: 1e8 for t in tickers})
    vs = [lane.free_terms(_cand(t, gap=15.0 + i), HIST_90) for i, t in enumerate(tickers)]
    out = await lane.enrich_and_record(vs, {t: lane.snapshot_board([_cand(t)])[0] for t in tickers}, **_ctx())
    assert out["tick_capped"] == 3 and out["enriched"] == lane.MAX_ENRICH_PER_TICK
    assert len(written) == lane.MAX_ENRICH_PER_TICK
    assert any(ev == "lowcap_lane_tick_cap" for ev, *_ in audits)
    # the biggest gaps went first; the three smallest are the deferred ones (not evaluated)
    deferred = {t for t in tickers if t not in lane._evaluated}
    assert deferred == set(tickers[:3])


@pytest.mark.asyncio
async def test_disabled_strategy_does_no_io(monkeypatch):
    monkeypatch.setattr(lane, "should_run", AsyncMock(return_value=False))
    reads = AsyncMock(side_effect=AssertionError("must not read when disabled"))
    monkeypatch.setattr(lane, "get_lowcap_lane_signal_tickers", reads)
    out = await lane.run_lowcap_lane_tick(
        lane.snapshot_board([_cand("AAAA")]), vol_history_daily_map={"AAAA": HIST_90}, **_ctx())
    assert out["skipped"] == "disabled" and out["written"] == 0


@pytest.mark.asyncio
async def test_a_raising_lane_is_counted_and_never_raises(monkeypatch):
    monkeypatch.setattr(lane, "should_run", AsyncMock(return_value=True))
    monkeypatch.setattr(lane, "enrich_and_record", AsyncMock(side_effect=RuntimeError("boom")))
    audits = []

    async def _audit(ev, summary, detail=""):
        audits.append(ev)
    monkeypatch.setattr(lane, "log_audit_event", _audit)
    out = await lane.run_lowcap_lane_tick(
        lane.snapshot_board([_cand("AAAA")]), vol_history_daily_map={"AAAA": HIST_90}, **_ctx())
    assert out["errors"] == 1 and "lowcap_lane_error" in audits


@pytest.mark.asyncio
async def test_schedule_detaches_a_task_and_never_touches_the_board(monkeypatch):
    monkeypatch.setattr(lane, "should_run", AsyncMock(return_value=False))
    board = [_cand("AAAA"), _cand("BBBB", gap=9.5)]
    frozen = json.dumps(board, sort_keys=True, default=str)
    maps = dict(vol_history_daily_map={"AAAA": HIST_90}, extension_map={"AAAA": 4.0},
                cooldown_tickers={"BBBB"}, cooldown_last_alert={"BBBB": SESSION_DATE - timedelta(days=3)},
                rank_by_prescore={"AAAA": 2, "BBBB": 1}, rank_by_gap={"AAAA": 1, "BBBB": 2},
                acting_rank={"AAAA": 2, "BBBB": 1})
    frozen_maps = json.dumps(maps, sort_keys=True, default=str)
    bg: set = set()
    assert lane.schedule_lowcap_lane_tick(board, today=SESSION_DATE, now_et=TICK, minutes_since_open=None,
                                          regime_label="Bull", bg_tasks=bg, **maps) is None   # pre-market
    task = lane.schedule_lowcap_lane_tick(board, today=SESSION_DATE, now_et=TICK, minutes_since_open=1,
                                          regime_label="Bull", bg_tasks=bg, **maps)
    assert task in bg
    await task
    assert json.dumps(board, sort_keys=True, default=str) == frozen
    assert json.dumps(maps, sort_keys=True, default=str) == frozen_maps
    assert task not in bg                                       # done-callback discards the strong ref


# ── Part 3: the byte-identity run — run_ep_scan end to end, lane ON / OFF / RAISING ────


def _snap(prev_close, price, today_vol, prev_vol=500_000):
    return {"prevDay": {"c": prev_close, "v": prev_vol},
            "min": {"c": price, "av": today_vol},
            "day": {"o": price, "v": today_vol},
            "lastTrade": {"p": price}}


class _FrozenDatetime(datetime):
    @classmethod
    def now(cls, tz=None):
        return TICK.astimezone(tz) if tz else TICK.replace(tzinfo=None)


async def _run_scan_once(monkeypatch, *, lane_mode: str):
    """One full run_ep_scan on a fixture board. 20 big-ADV fillers (top-20 by pre-score),
    all killed at the RVOL@T gate; 3 sub-shortlist names, two of which meet the lane rule.
    Returns (results, scan_log_rows, alert_inserts, lane_rows)."""
    from agents.market_intelligence import minute_volume as mv
    fillers = {f"BIG{i:02d}": _snap(50.0, 60.0, 5_000_000) for i in range(20)}
    smalls = {"CHPT": _snap(5.19, 6.90, 969_501), "WETO": _snap(6.00, 7.20, 2_000_000),
              "ZQRT": _snap(8.00, 9.60, 100_000)}
    snapshots = {**fillers, **smalls}
    adv_map = {t: 10_000_000.0 for t in fillers}          # $500M+ ADV$ -> composite 55, above the cut
    vol_hist = {"CHPT": [400_000.0] * 9 + [1_500_000.0], "WETO": [500_000.0] * 10,
                "ZQRT": [500_000.0] * 10}
    scan_log, alerts, audits = [], [], []

    async def _log_scan(rows):
        scan_log.extend(copy.deepcopy(rows))

    async def _insert_alert(record):
        alerts.append(copy.deepcopy(record))

    async def _toggle(name, env, default=True, **kw):
        return default

    async def _rvol(ticker, now_et, today_premkt_vol, today_session_vol):
        return {"anchor": "session", "rvol_at_time": 0.0, "baseline_n": mv.MIN_BASELINE_N_FOR_GATE,
                "today_cum_vol": int(today_session_vol), "baseline_mean": 1.0}

    async def _audit(ev, summary, detail=""):
        audits.append(ev)

    async def _noop(*a, **k):
        return None

    from tests.conftest import make_mock_pool
    pool, conn = make_mock_pool()
    conn.fetch = AsyncMock(return_value=[])
    conn.fetchval = AsyncMock(return_value=None)
    conn.fetchrow = AsyncMock(return_value=None)
    conn.execute = AsyncMock(return_value="INSERT 0 1")

    monkeypatch.setattr(ep_detector, "get_snapshot_all", AsyncMock(return_value=snapshots))
    monkeypatch.setattr(ep_detector, "get_latest_regime", AsyncMock(return_value={"regime": "Bull", "ep_threshold": 70}))
    monkeypatch.setattr(ep_detector, "get_adv_map", AsyncMock(return_value=adv_map))
    monkeypatch.setattr(ep_detector, "get_volume_history", AsyncMock(return_value={}))
    monkeypatch.setattr(ep_detector, "get_volume_history_daily_closes", AsyncMock(return_value=vol_hist))
    monkeypatch.setattr(ep_detector, "get_pool", AsyncMock(return_value=pool))
    monkeypatch.setattr(ep_detector, "get_runtime_toggle", _toggle)
    monkeypatch.setattr(ep_detector, "log_ep_scan_candidates", _log_scan)
    monkeypatch.setattr(ep_detector, "insert_ep_alert", _insert_alert)
    monkeypatch.setattr(ep_detector, "log_audit_event", _audit)
    monkeypatch.setattr(ep_detector, "compute_rvol_at_time", _rvol)
    monkeypatch.setattr(ep_detector, "_compute_adv_from_polygon", AsyncMock(return_value=None))
    monkeypatch.setattr(ep_detector, "_rt_miss_watchdog", _noop)
    monkeypatch.setattr(ep_detector, "et_today", lambda: SESSION_DATE)
    monkeypatch.setattr(ep_detector, "datetime", _FrozenDatetime)
    monkeypatch.setattr(db, "get_pool", AsyncMock(return_value=pool))
    monkeypatch.setattr(db, "get_active_themes", AsyncMock(return_value=[]))
    monkeypatch.setattr(db, "get_narrative_theme_candidates", AsyncMock(return_value=[]))
    monkeypatch.setattr(db, "get_holistic_judge_enabled", AsyncMock(return_value=False))
    monkeypatch.setattr(db, "get_composite_authority_enabled", AsyncMock(return_value=False))
    from agents.market_intelligence import universe_floor_shadow, ep_shortlist_shadow, catalyst_tier_shadow
    monkeypatch.setattr(universe_floor_shadow, "record_universe_floor_shadow", AsyncMock(return_value=0))
    monkeypatch.setattr(ep_shortlist_shadow, "record_ep_shortlist_shadow", AsyncMock(return_value=0))
    monkeypatch.setattr(catalyst_tier_shadow, "fetch_board_sectors", AsyncMock(return_value={}))

    # the lane side
    lane_rows = []
    lane._evaluated_date, lane._evaluated = None, set()
    lane._cap_cache_date, lane._cap_cache, lane._cap_failures = None, {}, {}
    if lane_mode == "raising":
        monkeypatch.setattr(lane, "schedule_lowcap_lane_tick",
                            lambda *a, **k: (_ for _ in ()).throw(RuntimeError("lane exploded")))
    else:
        monkeypatch.setattr(lane, "should_run", AsyncMock(return_value=(lane_mode == "on")))
        monkeypatch.setattr(lane, "get_lowcap_lane_signal_tickers", AsyncMock(return_value=set()))
        monkeypatch.setattr(lane, "get_fmp_profile",
                            AsyncMock(side_effect=lambda t: {"marketCap": {"CHPT": 134e6, "WETO": 12e6}.get(t, 2e9)}))
        monkeypatch.setattr(lane, "check_filters", AsyncMock(return_value=(True, None)))
        monkeypatch.setattr(lane, "is_likely_ma", AsyncMock(return_value=(False, None)))
        monkeypatch.setattr(lane, "get_alpaca_minute_cum_volumes", AsyncMock(return_value={}))
        monkeypatch.setattr(lane, "get_alpaca_latest_quotes", AsyncMock(return_value={}))
        monkeypatch.setattr(lane, "get_lowcap_lane_prior_signal_dates", AsyncMock(return_value={}))
        monkeypatch.setattr(lane, "log_audit_event", _audit)

        async def _ins(rows):
            lane_rows.extend(rows)
            return len(rows)
        monkeypatch.setattr(lane, "insert_lowcap_lane_signals", _ins)

    results = await ep_detector.run_ep_scan(SESSION_DATE.isoformat())
    # drain every fire-and-forget task the scan spawned (scan_log batch write, the lane task)
    for _ in range(5):
        pending = [t for t in asyncio.all_tasks() if t is not asyncio.current_task() and not t.done()]
        if not pending:
            break
        await asyncio.gather(*pending, return_exceptions=True)
    return results, scan_log, alerts, lane_rows


fillers_and_smalls = [f"BIG{i:02d}" for i in range(20)] + ["CHPT", "WETO", "ZQRT"]


def _canon(obj):
    return json.dumps(obj, sort_keys=True, default=str)


@pytest.mark.asyncio
async def test_run_ep_scan_is_byte_identical_with_the_lane_on_off_and_raising(monkeypatch):
    """THE test that matters: the hook sits on the live scan path inside the ORB window."""
    on = await _run_scan_once(monkeypatch, lane_mode="on")
    off = await _run_scan_once(monkeypatch, lane_mode="off")
    raising = await _run_scan_once(monkeypatch, lane_mode="raising")

    for a, b, what in ((on, off, "on vs off"), (on, raising, "on vs raising")):
        assert _canon(a[0]) == _canon(b[0]), f"results differ: {what}"
        assert _canon(a[1]) == _canon(b[1]), f"scan_log rows differ: {what}"
        assert _canon(a[2]) == _canon(b[2]), f"alert inserts differ: {what}"

    results, scan_log, alerts, lane_rows = on
    # the fixture's acting path: 20 fillers killed at the RVOL gate, 3 names beyond the cut,
    # zero alerts — the same on every side
    assert results == [] and alerts == []
    by_ticker = {r["ticker"]: r for r in scan_log}
    assert set(by_ticker) == set(fillers_and_smalls), sorted(set(fillers_and_smalls) ^ set(by_ticker))
    assert all(by_ticker[f"BIG{i:02d}"]["reject_stage"] == "rvol_gate" for i in range(20))
    assert {by_ticker[t]["reject_stage"] for t in ("CHPT", "WETO", "ZQRT")} == {"shortlist_cap"}
    assert all(r["score_tier"] is None and r["ep_score"] is None for r in scan_log)
    # and the lane, ON, recorded exactly the two names that meet the rule — from the full list
    assert sorted(r["ticker"] for r in lane_rows) == ["CHPT", "WETO"]
    chpt = next(r for r in lane_rows if r["ticker"] == "CHPT")
    assert chpt["in_shortlist"] is False and chpt["market_cap"] == 134e6
    assert {b["gate"] for b in chpt["blocking_filters"]} == {"shortlist_cap"}
    assert off[3] == [] and raising[3] == []


# ── Part 4: structural pins on the hook ───────────────────────────────────────────────


def _scan_src():
    return inspect.getsource(ep_detector.run_ep_scan)


def test_hook_sits_before_the_shortlist_cut_wrapped_and_lazily_imported():
    src = _scan_src()
    hook = src.index("schedule_lowcap_lane_tick(")
    cut = src.index("for c in candidates[SHORTLIST_SIZE:]:")
    graded = src.index("for c in candidates[:SHORTLIST_SIZE]:")
    assert hook < cut < graded, "the lane must see the FULL list before the shortlist cut"
    # lazy import inside the function, wrapped, never awaited, never assigned
    block = src[src.rindex("try:", 0, hook):src.index("except", hook)]
    assert "from agents.market_intelligence.lowcap_lane import schedule_lowcap_lane_tick" in block
    assert "await" not in block and "=" not in block.split("schedule_lowcap_lane_tick(")[0].split("import")[-1]
    head = (_REPO / "agents" / "market_intelligence" / "ep_detector.py").read_text().split("async def run_ep_scan")[0]
    assert "lowcap_lane" not in head, "ep_detector is on exec_loaded_modules.txt — the lane must not be a top-level import"
    assert "candidates, today=today" in block


def _code_only(src: str) -> str:
    """Source with comment lines and docstrings removed — pins on CODE, never on prose."""
    src = re.sub(r'"""(.*?)"""', "", src, flags=re.S)
    return "\n".join(l for l in src.splitlines() if not l.strip().startswith("#"))


def test_hook_adds_no_continue_and_no_log_filtered_site():
    """test_605 counts both; this pins the intent locally so a future edit cannot slip a gate in."""
    src = _scan_src()
    hook = src.index("#624 LOW-CAP LANE")
    end = src.index("for c in candidates[SHORTLIST_SIZE:]:")
    block = _code_only(src[hook:end])
    assert "continue" not in block and "_log_filtered(" not in block and "_scan_row(" not in block
    assert "schedule_lowcap_lane_tick(" in block


def test_lane_never_writes_the_acting_cap_cache():
    code = _code_only(_LANE.read_text())
    assert not re.search(r"_mcap_cache\s*[\[=]", code), "the lane must never write the acting cap cache"
    assert not re.search(r"import[^\n]*_mcap_cache", code)
    src = _LANE.read_text()
    calls = re.findall(r"check_filters\((.*?)\)", src, re.S)
    real = [c for c in calls if "v.ticker" in c]
    assert real and all("skip_mcap=True" in c for c in real)


def test_lane_module_never_touches_the_acting_path():
    src = _LANE.read_text()
    import_lines = [l for l in src.splitlines() if re.match(r"\s*(from|import)\s", l)]
    for banned in ("order_manager", "live_tracker", "entry_pipeline", "execution_client",
                   "alpaca_client", "telegram", "briefing", "_score_ep", "insert_ep_alert",
                   "enqueue_pending_allocation"):
        assert not any(banned in l for l in import_lines), banned
    code = _code_only(src)
    assert "insert_ep_alert" not in code and "enqueue_pending_allocation" not in code
    assert not re.search(r"\b(UPDATE|DELETE FROM|INSERT INTO)\b", code), "inline SQL in the recorder"
    writers = {n.strip() for n in re.search(r"from agents\.market_intelligence\.db import \((.*?)\)", src, re.S).group(1).split(",") if n.strip()}
    assert {w for w in writers if w.startswith(("insert_", "update_", "upsert_", "record_", "settle_", "delete_"))} == {"insert_lowcap_lane_signals"}


def test_nothing_imports_the_lane_modules_except_their_one_seam_each():
    lane_importers, walker_importers = [], []
    for py in sorted((_REPO / "agents").rglob("*.py")):
        text = py.read_text()
        if py != _LANE and re.search(r"^\s*(from|import)\s+[\w.]*lowcap_lane\b", text, re.M):
            lane_importers.append(str(py.relative_to(_REPO)))
        if py != _WALKER and re.search(r"^\s*(from|import)\s+[\w.]*lowcap_lane_replay\b", text, re.M):
            walker_importers.append(str(py.relative_to(_REPO)))
    assert lane_importers == ["agents/market_intelligence/ep_detector.py"], lane_importers
    assert walker_importers == ["agents/market_intelligence/scheduler.py"], walker_importers
    allowed = {"db.py", "health_checks.py", "lowcap_lane.py", "lowcap_lane_replay.py", "adapters.py"}
    for py in (_REPO / "agents" / "market_intelligence").rglob("*.py"):
        if py.name in allowed:
            continue
        code = _code_only(py.read_text())
        assert "mi_lowcap_lane_signals" not in code and "mi_lowcap_lane_replays" not in code, py.relative_to(_REPO)


# ── Part 5: the walker ────────────────────────────────────────────────────────────────


def _m(hh, mm, o, h, l, c, d=SESSION_DATE):
    return {"m": datetime(d.year, d.month, d.day, hh, mm, tzinfo=_ET), "o": o, "h": h, "l": l, "c": c}


def _daily_row(d, o, h, l, c, v):
    return {"trade_date": d, "open_price": o, "high_price": h, "low_price": l, "close": c, "volume": v}


PRIOR_ROWS = [_daily_row(SESSION_DATE - timedelta(days=i), 10.0, 10.6, 9.4, 10.0, 1_000_000)
              for i in range(15, 0, -1)]
D0_ROW = _daily_row(SESSION_DATE, 10.0, 12.0, 9.4, 11.5, 9_000_000)


def _sig(ticker="CHPT", tick=TICK):
    return {"signal_id": 7, "ticker": ticker, "scan_date": SESSION_DATE, "tick_wallclock_et": tick,
            "prev_close": 10.0, "market_cap": 134e6, "gap_pct": 20.0, "vol_percentile": 95.0}


def _out():
    return {"settled": 0, "no_trade": 0, "unscoreable": 0, "open": 0, "horizon": 0,
            "pending": 0, "errors": 0, "candidates": 0, "written": 0}


def test_walker_pure_helpers():
    assert lcl.stop_pct_of_entry(10.5, 8.5) == pytest.approx(19.0476, abs=1e-3)
    assert lcl.stop_pct_of_entry(0, 8.5) is None and lcl.stop_pct_of_entry(10.5, None) is None
    sessions = [(SESSION_DATE + timedelta(days=1), {"o": 4.0, "h": 5.0, "l": 3.9, "c": 4.5})]
    assert lcl.next_open_gap_pct(7.70, sessions) == pytest.approx((4.0 - 7.70) / 7.70 * 100, abs=1e-3)
    assert lcl.next_open_gap_pct(7.70, []) is None and lcl.next_open_gap_pct(None, sessions) is None
    filings = [{"form": "8-K", "filed": "2026-09-04", "items": "3.02,9.01", "url": "u1"},
               {"form": "8-K", "filed": "2026-09-04", "items": "2.02", "url": "u2"},
               {"form": "424B5", "filed": "2026-09-02", "items": "", "url": "u3"},   # before the hold
               {"form": "424B4", "filed": "2026-09-05", "items": "", "url": "u4"}]
    flag, matched = lcl.offering_from_filings(filings, SESSION_DATE, date(2026, 9, 5))
    assert flag is True and [m["url"] for m in matched] == ["u1", "u4"]
    assert lcl.offering_from_filings([], SESSION_DATE, date(2026, 9, 5)) == (False, [])


def test_walker_reuses_the_siblings_primitives_never_a_sixth_walker():
    import agents.market_intelligence.sustain_reject_replay as srr
    import agents.market_intelligence.live_fill_counterfactuals as lfc
    assert lcl.srr.entry_walk is srr.entry_walk and lcl.srr.submit_time_and_window is srr.submit_time_and_window
    assert lcl.srr.current_era_stop is srr.current_era_stop and lcl.srr.mark_pnl_per_share is srr.mark_pnl_per_share
    assert lcl.walk_arm is lfc.walk_arm and lcl.pinned_target is lfc.pinned_target


def _wire_walker(monkeypatch, *, day0, sessions, stored=True, fetched=None, filings=None):
    written, persisted = [], []

    async def _upsert(fields):
        written.append(dict(fields))
        return True

    async def _bars(conn, ticker, start, end):
        return day0 if stored else []

    async def _fetch(ticker, start, end):
        return fetched or []

    async def _persist(ticker, bars):
        persisted.append((ticker, len(bars)))

    monkeypatch.setattr(lcl, "get_daily_ohlc_range", AsyncMock(return_value=PRIOR_ROWS + [D0_ROW]))
    monkeypatch.setattr(lcl, "get_intraday_bars_window", _bars)
    monkeypatch.setattr(lcl.lfc, "_assemble_sessions", AsyncMock(return_value=sessions))
    monkeypatch.setattr(lcl, "upsert_lowcap_lane_replay", _upsert)
    monkeypatch.setattr(lcl, "get_minute_bars_range", _fetch)
    monkeypatch.setattr(lcl, "persist_intraday_bars", _persist)
    monkeypatch.setattr(lcl, "get_sec_recent_filings", AsyncMock(return_value=filings or []))
    monkeypatch.setattr(lcl, "log_audit_event", AsyncMock())
    return written, persisted


@pytest.mark.asyncio
async def test_settled_winner_walks_from_its_own_tick_and_records_the_overnight_tail(monkeypatch):
    """Tick 09:33 -> submit 09:33 (never 09:31). Fill at orb_high 10.5 on the 09:34 bar,
    stop 8.5, target 10.5+2x(10.5-9.5)=12.5 hit on day 1 (partial), stop-to-breakeven,
    then the day-2 open collapses (the UNCY class) and stops the runner at the open."""
    day0 = [_m(9, 30, 10.0, 10.5, 9.5, 10.3), _m(9, 31, 10.3, 10.4, 10.2, 10.35),
            _m(9, 32, 10.3, 10.4, 10.2, 10.35), _m(9, 33, 10.3, 10.45, 10.2, 10.4),
            _m(9, 34, 10.4, 10.6, 10.3, 10.55)] + \
           [_m(9, 35 + i, 10.55, 10.7, 10.5, 10.6) for i in range(25)]
    d1, d2 = SESSION_DATE + timedelta(days=1), SESSION_DATE + timedelta(days=5)   # Fri, Tue
    sessions = [(d1, {"o": 11.0, "h": 13.0, "l": 10.8, "c": 12.8}),
                (d2, {"o": 7.0, "h": 7.5, "l": 6.5, "c": 6.8})]
    filings = [{"form": "8-K", "filed": d2.isoformat(), "items": "3.02", "url": "u"}]
    written, _ = _wire_walker(monkeypatch, day0=day0, sessions=sessions, filings=filings)
    out = _out()
    tick = datetime(2026, 9, 3, 9, 33, 40, tzinfo=_ET)
    await lcl._record_one_signal(conn=object(), sig=_sig(tick=tick), last_session=date(2026, 9, 9),
                                 run_date=date(2026, 9, 10), out=out)
    assert out["errors"] == 0 and len(written) == 1
    f = written[0]
    assert f["submit_time_et"] == time(9, 33) and f["window_out_of_orb"] is False
    assert f["entry_status"] == "filled" and f["entry_minute"] == day0[4]["m"]
    assert f["entry_price"] == pytest.approx(10.5) and f["stop_price"] == pytest.approx(8.5)
    assert f["stop_pct_of_entry"] == pytest.approx((10.5 - 8.5) / 10.5 * 100, abs=1e-3)
    assert f["target_price"] == pytest.approx(12.5) and f["partial_fired"] is True
    assert f["outcome"] == "settled" and f["day0_bars_source"] == "stored"
    assert f["day0_close"] == pytest.approx(11.5)          # the daily row's close, not the last stored minute
    assert f["next_open_gap_pct"] == pytest.approx((11.0 - 11.5) / 11.5 * 100, abs=1e-3)
    assert f["offering_flag"] is True and f["offering_forms"][0]["items"] == "3.02"
    assert f["offering_checked_through"] == d2
    # the UNCY shape: 1/3 off at +2R (12.5), stop to breakeven, the runner gaps THROUGH the
    # resting stop and fills at the 7.0 open -> (2.0/3 + (7.0-10.5)*2/3) / 2.0 = -0.8333R
    assert f["gap_through"] is True and f["exit_session"] == 2
    assert f["realized_r"] == pytest.approx((2.0 / 3 + (7.0 - 10.5) * 2 / 3) / 2.0, abs=1e-3)
    assert f["meets_positive"] is False and f["meets_3r"] is False
    assert f["admission_era"] == rule_eras.admission_era_as_of(SESSION_DATE)
    assert f["replay_exit_era"] == rule_eras.exit_era_label(date(2026, 9, 10))
    assert f["signal_id"] == 7 and f["tick_wallclock_et"] == tick


@pytest.mark.asyncio
async def test_tick_at_or_after_0945_is_out_of_window_never_simulated(monkeypatch):
    written, _ = _wire_walker(monkeypatch, day0=[], sessions=[])
    out = _out()
    tick = datetime(2026, 9, 3, 9, 45, 3, tzinfo=_ET)
    await lcl._record_one_signal(conn=object(), sig=_sig(tick=tick), last_session=TODAY, run_date=TODAY, out=out)
    f = written[0]
    assert f["window_out_of_orb"] is True and f["submit_time_et"] is None
    assert f["entry_status"] == "window_out_of_orb" and f["outcome"] == "no_trade"
    assert out["no_trade"] == 1


@pytest.mark.asyncio
async def test_never_alerted_name_fetches_and_persists_its_day0_bars(monkeypatch):
    day0 = [_m(9, 30, 10.0, 10.5, 9.5, 10.3), _m(9, 31, 10.4, 10.6, 10.3, 10.55),
            _m(9, 32, 10.5, 10.55, 8.0, 8.2)]
    fetched = [{"t_et": b["m"], "open": b["o"], "high": b["h"], "low": b["l"], "close": b["c"], "volume": 1000, "vwap": None}
               for b in day0]
    written, persisted = _wire_walker(monkeypatch, day0=day0, sessions=[], stored=False, fetched=fetched)
    out = _out()
    await lcl._record_one_signal(conn=object(), sig=_sig(), last_session=TODAY, run_date=TODAY, out=out)
    assert persisted == [("CHPT", 3)]
    f = written[0]
    assert f["day0_bars_source"] == "fetched_alpaca" and f["outcome"] == "settled"
    assert f["realized_r"] == pytest.approx(-1.0) and f["meets_3r"] is False
    assert f["next_open_gap_pct"] is None and f["offering_flag"] is None   # stopped on day 0: no overnight


@pytest.mark.asyncio
async def test_no_bars_anywhere_is_pending_then_unscoreable_never_dropped(monkeypatch):
    written, _ = _wire_walker(monkeypatch, day0=[], sessions=[], stored=False, fetched=[])
    out = _out()
    await lcl._record_one_signal(conn=object(), sig=_sig(), last_session=TODAY, run_date=TODAY, out=out)
    assert written == [] and out["pending"] == 1
    stale = date(2026, 9, 14)                      # 7 sessions past the signal day
    await lcl._record_one_signal(conn=object(), sig=_sig(), last_session=stale, run_date=stale, out=out)
    assert written[0]["outcome"] == "unscoreable" and written[0]["entry_status"] == "no_day0_minute_bars"


@pytest.mark.asyncio
async def test_still_open_walk_is_written_with_a_mark_and_refreshed(monkeypatch):
    day0 = [_m(9, 30, 10.0, 10.5, 9.5, 10.3), _m(9, 31, 10.4, 10.6, 10.3, 10.55),
            _m(9, 32, 10.55, 10.6, 10.5, 10.58)]
    sessions = [(SESSION_DATE + timedelta(days=1), {"o": 10.6, "h": 10.7, "l": 10.55, "c": 10.65})]
    written, _ = _wire_walker(monkeypatch, day0=day0, sessions=sessions)
    out = _out()
    await lcl._record_one_signal(conn=object(), sig=_sig(), last_session=TODAY, run_date=TODAY, out=out)
    f = written[0]
    assert f["outcome"] == "open" and f["mark_r"] == pytest.approx((10.65 - 10.5) / 2.0)
    assert f["mark_meets_positive"] is True and f["mark_meets_3r"] is False
    assert f["next_open_gap_pct"] == pytest.approx((10.6 - 11.5) / 11.5 * 100, abs=1e-3)
    assert f["offering_checked_through"] == TODAY and out["open"] == 1


@pytest.mark.asyncio
async def test_run_skips_terminal_rows_revisits_open_ones_and_isolates_failures(monkeypatch):
    pop = [_sig("AAAA"), _sig("BBBB"), _sig("CCCC")]
    existing = {("AAAA", SESSION_DATE): "settled", ("BBBB", SESSION_DATE): "open"}
    seen = []

    async def _rec(conn, sig, last_session, run_date, out):
        seen.append(sig["ticker"])
        if sig["ticker"] == "CCCC":
            raise RuntimeError("boom")
    from tests.conftest import make_mock_pool
    pool, _ = make_mock_pool()
    audits = []

    async def _audit(ev, summary, detail=""):
        audits.append(ev)
    monkeypatch.setattr(lcl, "get_lowcap_lane_population", AsyncMock(return_value=pop))
    monkeypatch.setattr(lcl, "get_lowcap_lane_replay_existing", AsyncMock(return_value=existing))
    monkeypatch.setattr(lcl, "get_pool", AsyncMock(return_value=pool))
    monkeypatch.setattr(lcl, "_record_one_signal", _rec)
    monkeypatch.setattr(lcl, "log_audit_event", _audit)
    out = await lcl.run_lowcap_lane_replay(TODAY, now_et=datetime(2026, 9, 4, 18, 15, tzinfo=_ET))
    assert seen == ["BBBB", "CCCC"] and out["errors"] == 1 and out["population"] == 3
    assert "lowcap_lane_replay_error" in audits and "lowcap_lane_replay_recorded" in audits


@pytest.mark.asyncio
async def test_a_broken_population_query_never_raises(monkeypatch):
    monkeypatch.setattr(lcl, "get_lowcap_lane_population", AsyncMock(side_effect=RuntimeError("db")))
    monkeypatch.setattr(lcl, "log_audit_event", AsyncMock())
    out = await lcl.run_lowcap_lane_replay(TODAY, now_et=datetime(2026, 9, 4, 18, 15, tzinfo=_ET))
    assert out["errors"] == 1 and out["written"] == 0


def test_walker_boundary_only_the_two_market_data_wrappers_from_broker():
    src = _WALKER.read_text()
    import_lines = [l for l in src.splitlines() if re.match(r"\s*(from|import)\s", l)]
    broker = [l for l in import_lines if "agents.market_intelligence.broker" in l]
    assert len(broker) == 2 and all("# exec-boundary-ok:" in l for l in broker)
    assert any("get_minute_bars_range" in l for l in broker) and any("persist_intraday_bars" in l for l in broker)
    for banned in ("order_manager", "live_tracker", "entry_pipeline", "execution_client",
                   "telegram", "briefing", "gap_near_miss_replay", "lowcap_lane import"):
        assert not any(banned in l for l in import_lines), banned
    assert not re.search(r"\b(UPDATE|DELETE FROM|INSERT INTO)\b", src), "inline SQL in the walker"
    writers = {n.strip() for n in re.search(r"from agents\.market_intelligence\.db import \((.*?)\)", src, re.S).group(1).split(",") if n.strip()}
    assert {w for w in writers if w.startswith(("insert_", "update_", "upsert_", "record_", "settle_", "delete_"))} == {"upsert_lowcap_lane_replay"}


# ── Part 6: registrations, schema, seed, adapter, gate, SSoT ─────────────────────────


def test_registrations_job_liveness_preflight_schema_exec_list():
    from agents.market_intelligence import scheduler as sched, health_checks as hc
    import scripts.preflight_db_updates as pf
    assert "lowcap_lane_replay" in sched.INTELLIGENCE_OWNED_JOB_IDS
    assert "lowcap_lane_replay" not in sched.EXECUTION_OWNED_JOB_IDS
    assert any(t[0] == "mi_lowcap_lane_signals" and t[2] == "scan_date" for t in hc._DETECTOR_LIVENESS_TABLES)
    assert any(t[0] == "mi_lowcap_lane_replays" and t[2] == "settled_session" for t in hc._DETECTOR_LIVENESS_TABLES)
    assert any(sql is db.LOWCAP_LANE_SIGNAL_INSERT_SQL for _, sql in pf.SHADOW_WRITER_STATEMENTS)
    assert any(sql is db.LOWCAP_LANE_REPLAY_UPSERT_SQL for _, sql in pf.SHADOW_WRITER_STATEMENTS)
    src = (_REPO / "agents" / "market_intelligence" / "db.py").read_text()
    for table, cols in (("mi_lowcap_lane_signals", db.LOWCAP_LANE_SIGNAL_COLS),
                        ("mi_lowcap_lane_replays", db.LOWCAP_LANE_REPLAY_COLS)):
        block = re.search(rf"CREATE TABLE IF NOT EXISTS {table} \((.*?)\n\s*\);", src, re.S).group(1)
        key = "UNIQUE (ticker, scan_date)" if table.endswith("signals") else "UNIQUE (ticker, session_date)"
        assert key in block
        for col in cols:
            assert re.search(rf"^\s*{col}\s+", block, re.M), f"{table}: column {col} missing from CREATE"
    exec_list = (_REPO / "scripts" / "exec_loaded_modules.txt").read_text()
    assert "lowcap_lane" not in exec_list
    sched_src = (_REPO / "agents" / "market_intelligence" / "scheduler.py").read_text()
    assert 'id="lowcap_lane_replay"' in sched_src and "CronTrigger(hour=18, minute=15" in sched_src.split('id="lowcap_lane_replay"')[0][-400:]


def test_upsert_sql_guards_terminal_rows_and_insert_binds_its_jsonb():
    sql = db.LOWCAP_LANE_REPLAY_UPSERT_SQL
    assert "ON CONFLICT (ticker, session_date) DO UPDATE SET" in sql
    assert "WHERE mi_lowcap_lane_replays.outcome = 'open'" in sql
    assert sql.count("::jsonb") == 3                 # exits, offering_forms, replay_exit_rules
    ins = db.LOWCAP_LANE_SIGNAL_INSERT_SQL
    assert ins.startswith("INSERT INTO mi_lowcap_lane_signals (")
    assert ins.endswith("ON CONFLICT (ticker, scan_date) DO NOTHING")
    assert ins.count("::jsonb") == 1                 # blocking_filters


@pytest.mark.asyncio
async def test_signal_writer_is_fail_open_and_binds_every_column(monkeypatch):
    from tests.conftest import make_mock_pool
    pool, conn = make_mock_pool()
    sent = []

    async def _em(sql, argrows):
        sent.append((sql, argrows))
    conn.executemany = _em
    monkeypatch.setattr(db, "get_pool", AsyncMock(return_value=pool))
    row = {c: None for c in db.LOWCAP_LANE_SIGNAL_COLS}
    row.update(ticker="CHPT", scan_date="2026-09-03", blocking_filters=[{"gate": "x"}])
    assert await db.insert_lowcap_lane_signals([row]) == 1
    sql, argrows = sent[0]
    assert sql is db.LOWCAP_LANE_SIGNAL_INSERT_SQL and len(argrows[0]) == len(db.LOWCAP_LANE_SIGNAL_COLS)
    assert argrows[0][1] == date(2026, 9, 3)          # ISO string coerced to a date at the writer
    monkeypatch.setattr(db, "get_pool", AsyncMock(side_effect=RuntimeError("db down")))
    assert await db.insert_lowcap_lane_signals([row]) == 0


@pytest.mark.asyncio
async def test_purge_old_data_never_deletes_the_lane_tables():
    from unittest.mock import MagicMock
    executed = []

    async def fake_execute(sql, *a):
        executed.append(sql)
        return "DELETE 0"
    conn = MagicMock()
    conn.execute = fake_execute
    pool = MagicMock()
    pool.acquire = MagicMock()
    pool.acquire.return_value.__aenter__ = AsyncMock(return_value=conn)
    pool.acquire.return_value.__aexit__ = AsyncMock(return_value=False)
    with patch.object(db, "get_pool", AsyncMock(return_value=pool)):
        await db.purge_old_data()
    assert executed and not any("mi_lowcap_lane" in s for s in executed)


@pytest.mark.asyncio
async def test_seed_row_is_shadow_with_the_median_gate_nulled_on_both_rungs():
    from unittest.mock import MagicMock
    conn = MagicMock()
    batches = []

    async def _em(sql, rows):
        batches.append(rows)
    conn.executemany = _em
    conn.execute = AsyncMock()
    await db._seed_strategies_registry(conn)
    seeds = {r[0]: r for r in batches[0]}
    s = seeds["magna53_lowcap"]
    assert s[2] == "orb_long" and s[3] == "shadow" and s[4] == "magna53_lowcap"
    assert s[5] == "mi_lowcap_lane_replays" and s[6] == "unpaired_r"
    thr = s[7]
    assert thr["shadow_to_paper"]["min_median_r"] is None and thr["paper_to_live"]["min_median_r"] is None
    assert thr["shadow_to_paper"]["min_closed"] == 30 and thr["paper_to_live"]["min_closed"] == 30
    assert "max_drawdown_pct" not in thr["shadow_to_paper"]
    from agents.market_intelligence.strategies.promotion import _eval_unpaired_r
    from agents.market_intelligence.strategies.adapters import OutcomeRow
    # 37% at +0.33, 35% at -1.00, the rest small: median +0.33 — a 0.0 bar would PASS this
    rows = [OutcomeRow("magna53_lowcap", f"T{i}", SESSION_DATE, "closed", r, None, 1, None)
            for i, r in enumerate([0.33] * 17 + [-1.0] * 16 + [0.1] * 8 + [4.0] * 5)]
    _, blocking = _eval_unpaired_r(rows, thr["shadow_to_paper"])
    assert blocking == []                              # the registry cannot see the tail question


@pytest.mark.asyncio
async def test_adapter_maps_outcomes_and_drops_unscoreable(monkeypatch):
    from agents.market_intelligence.strategies import adapters
    from tests.conftest import make_mock_pool
    pool, conn = make_mock_pool()

    def _r(**k):
        base = dict(ticker="T", session_date=SESSION_DATE, outcome="settled", realized_r=2.5, mark_r=None,
                    sessions_walked=3, exit_session=3, meets_3r=False, meets_4r=False,
                    stop_pct_of_entry=19.0, next_open_gap_pct=-1.2, offering_flag=False,
                    admission_era="adm_x", replay_exit_era="era_c")
        base.update(k)
        return base
    conn.fetch = AsyncMock(return_value=[
        _r(ticker="A"), _r(ticker="B", outcome="open", realized_r=None, mark_r=1.1),
        _r(ticker="C", outcome="horizon", realized_r=None, mark_r=0.4),
        _r(ticker="D", outcome="no_trade", realized_r=None)])
    monkeypatch.setattr(adapters, "get_pool", AsyncMock(return_value=pool))
    assert "magna53_lowcap" in adapters._ADAPTERS
    rows = await adapters.get_outcomes("magna53_lowcap", 90)
    by = {r.ticker: r for r in rows}
    assert by["A"].status == "closed" and by["A"].r_multiple == 2.5 and by["A"].hold_days == 3
    assert by["B"].status == "open" and by["B"].r_multiple is None and by["B"].extras["mark_r"] == 1.1
    assert by["C"].status == "open" and by["D"].status == "no_entry"
    sql = conn.fetch.call_args.args[0]
    assert "mi_lowcap_lane_replays" in sql and "outcome <> 'unscoreable'" in sql


def test_no_admission_switch_row_at_shadow_and_the_note_says_why():
    """A row would relabel every MAGNA53 fill's admission_era with an identical filter set."""
    assert not any("lowcap" in name for _, name, *_ in rule_eras.ADMISSION_SWITCHES)
    assert rule_eras.admission_era_as_of(date(2026, 9, 8)) == "adm_2026-08-31_extension_cap_50_slot_rank_rs"
    src = (_REPO / "agents" / "market_intelligence" / "rule_eras.py").read_text()
    assert "#624" in src and "NO row" in src and "PAPER FLIP" in src


def test_gated_review_binds_to_545_by_its_real_name_and_gates_on_sample_only():
    import yaml
    reg = yaml.safe_load((_REPO / "data_gated_reviews.yaml").read_text())
    entries = reg["reviews"] if isinstance(reg, dict) else reg
    e = next(x for x in entries if x.get("review_id") == "lowcap_lane_graduation_624")
    assert e["kind"] == "accrual" and e["status"] == "pending" and e["threshold"] == 1
    assert e["added_on"] == date(2026, 9, 4) and isinstance(e["earliest_review_date"], date)
    assert "to_regclass('mi_lowcap_lane_replays')" in e["predicate_sql"]
    flat = " ".join(e["predicate_sql"].split())
    assert "COUNT(*) FILTER (WHERE outcome = 'settled') >= 30" in flat
    assert "COUNT(DISTINCT ticker) FILTER (WHERE outcome = 'settled') >= 20" in flat
    assert "realized_r" not in flat, "no R bar in the predicate — the gate counts samples, the read counts tails"
    action = e["action_when_ready"]
    assert "#545" in action and "ENTRY/EXIT TACTICS PROGRAM" in action
    assert "limit-exit reversion" not in action.lower().replace("not \"limit-exit reversion\"", "")
    assert ">=4 settled walks >=3R" in action and "top-2" in action
    assert "extension guard" in action and "DO NOT propose it" in action
    assert set(e["discriminates_on"]) == {"mi_lowcap_lane_replays.admission_era",
                                          "mi_lowcap_lane_replays.replay_exit_era"}
    assert "task #545" in e["cross_refs"] and "task #624" in e["cross_refs"]


def test_ssot_carries_the_rule_sentence_verbatim_and_a_dated_entry():
    ssot = (_REPO / "docs" / "setups" / "magna53_ep.md").read_text()
    sentence = ("A $5+ stock under $500M market cap that gaps 15% or more and whose volume by the "
                "09:31 tick already ranks in the top 10% of its own trailing history is a lane "
                "candidate; every other MAGNA53 gate it failed is stamped on its row.")
    assert " ".join(sentence.split()) in " ".join(ssot.split())
    assert re.search(r"^### 2026-09-04 — #624", ssot, re.M)
    assert "## Low-cap lane" in ssot
    assert not (_REPO / "docs" / "setups" / "lowcap_lane.md").exists()     # a LANE, not a setup
    router = (_REPO / "docs" / "SSoT.md").read_text()
    assert "lowcap" not in router.lower()
