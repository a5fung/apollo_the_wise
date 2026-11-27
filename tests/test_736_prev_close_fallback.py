"""#736 (2026-11-27): the morning after Thanksgiving Polygon's snapshot carried prevDay.c = 0 on up
to 3,482 of 13,253 rows (ordinary names: TTC, BG, UFPI) and the EP candidate build dropped every one
of them. A row with NO Polygon prev close is now filled from the KNOWN previous trading date — the
date-keyed Alpaca bar first, else our stored `mi_daily_closes` row for that same date, else it is
dropped and counted exactly as before. Bug fix: no EP rule, threshold or score changes.

Pins (each fails on the pre-#736 code, where every such row was dropped):
  (a) prevDay 0 + an Alpaca bar dated the previous trading day -> candidate, source alpaca;
  (b) prevDay 0, no Alpaca match, stored close for that date -> candidate, source stored;
  (c) prevDay 0 and only an OLDER-date close available -> still dropped (and counted);
  (d) a row WITH a Polygon prev close -> byte-identical candidate dict;
  (e) the stored-close load raising -> today's drop behaviour, the scan does not raise.
  Plus: the incident date itself (11-27, no date argument) resolves to 11-25, not the 11-26
  holiday; a filled row is never 'verified' by the bar it came from.
"""
from __future__ import annotations

import asyncio
import copy
import logging
import sys
from datetime import date, datetime
from pathlib import Path
from unittest.mock import AsyncMock
from zoneinfo import ZoneInfo

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from agents.market_intelligence import collector
from agents.market_intelligence import db
from agents.market_intelligence import ep_detector

_ET = ZoneInfo("America/New_York")
SESSION_DATE = date(2026, 11, 27)     # Friday after Thanksgiving (the incident morning)
PREV_SESSION = date(2026, 11, 25)     # the real previous trading day (11-26 was the holiday)
OLDER_SESSION = date(2026, 11, 24)
PRE_OPEN = datetime(2026, 11, 27, 9, 25, 12, tzinfo=_ET)


def _bar_ts(d: date) -> datetime:
    return datetime(d.year, d.month, d.day, 0, 0, tzinfo=_ET)   # Alpaca daily bars: midnight ET


def _alpaca(close, d, vol=900_000):
    """Alpaca snapshot dict as collector.get_alpaca_snapshots_batch returns it, pre-open shape:
    daily_bar still holds the previous session, previous_daily_bar the one before."""
    return {"daily_bar_close": close, "daily_bar_ts": _bar_ts(d), "day_volume": vol,
            "prev_close": close * 0.98, "prev_daily_bar_ts": _bar_ts(OLDER_SESSION),
            "prev_daily_bar_volume": 700_000, "price": None}


def _snap(prev_close, price, prev_vol=500_000, today_vol=3_000_000):
    return {"prevDay": {"c": prev_close, "v": prev_vol},
            "min": {"c": price, "av": today_vol},
            "day": {"o": price, "v": today_vol},
            "lastTrade": {"p": price}}


@pytest.fixture(autouse=True)
def _fresh_fill_cache(monkeypatch):
    monkeypatch.setattr(ep_detector, "_prev_close_fill_key", None)
    monkeypatch.setattr(ep_detector, "_prev_close_fill_map", {})
    monkeypatch.setattr(ep_detector, "_prev_close_fill_done", set())
    monkeypatch.setattr(ep_detector, "_prev_close_fill_date_memo", None)
    monkeypatch.setattr(ep_detector, "_prev_close_fill_failed_ticks", 0)


# ── the fill date ─────────────────────────────────────────────────────────────────────

def test_incident_morning_fill_date_is_the_real_previous_session_not_the_holiday():
    # the scan's own _prev_trade_date (last_trading_day) names 11-26 here — the holiday
    assert ep_detector._prev_close_fill_date(SESSION_DATE, None) == PREV_SESSION
    assert ep_detector._prev_close_fill_date(SESSION_DATE, "2026-11-25") == PREV_SESSION
    assert ep_detector._prev_close_fill_date(date(2026, 11, 25), None) == date(2026, 11, 24)


# ── the fill helper ───────────────────────────────────────────────────────────────────

def _run(coro):
    return asyncio.new_event_loop().run_until_complete(coro)


def _patch_sources(monkeypatch, *, alpaca=None, stored=None, stored_exc=None):
    seen = {"alpaca": [], "stored": []}

    async def _batch(tickers, **kw):
        seen["alpaca"].append(list(tickers))
        return {t: v for t, v in (alpaca or {}).items() if t in tickers}

    async def _stored(d, tickers):
        seen["stored"].append((d, list(tickers)))
        if stored_exc:
            raise stored_exc
        rows = (stored or {}).get(d, {})
        return [{"ticker": t, "close": c, "volume": v} for t, (c, v) in rows.items() if t in tickers]

    monkeypatch.setattr(collector, "get_alpaca_snapshots_batch", _batch)
    monkeypatch.setattr(ep_detector, "_load_stored_daily_closes", _stored)
    return seen


def test_a_alpaca_bar_dated_the_previous_session_fills_close_and_volume(monkeypatch):
    _patch_sources(monkeypatch, alpaca={"TTC": _alpaca(80.0, PREV_SESSION, vol=1_234_000)})
    rows = {"TTC": _snap(0, 90.0, prev_vol=0)}
    patched, counts = _run(ep_detector._fill_missing_prev_closes(rows, SESSION_DATE, PREV_SESSION))
    assert counts == {"alpaca": 1, "stored": 0}
    p = patched["TTC"]
    assert p["prevDay"]["c"] == 80.0 and p["prevDay"]["v"] == 1_234_000
    assert p[ep_detector._PREV_CLOSE_FILL_MARK] == ep_detector.PREV_CLOSE_FILL_SRC_ALPACA
    assert rows["TTC"]["prevDay"]["c"] == 0, "the shared snapshot row is never mutated"


def test_b_no_alpaca_match_falls_to_the_stored_close_for_that_date(monkeypatch):
    seen = _patch_sources(monkeypatch, alpaca={"BG": _alpaca(70.0, OLDER_SESSION)},
                          stored={PREV_SESSION: {"BG": (71.5, 2_000_000)}})
    rows = {"BG": _snap(0, 80.0, prev_vol=0)}
    patched, counts = _run(ep_detector._fill_missing_prev_closes(rows, SESSION_DATE, PREV_SESSION))
    assert counts == {"alpaca": 0, "stored": 1}
    assert patched["BG"]["prevDay"] == {"c": 71.5, "v": 2_000_000}
    assert patched["BG"][ep_detector._PREV_CLOSE_FILL_MARK] == ep_detector.PREV_CLOSE_FILL_SRC_STORED
    assert seen["stored"] == [(PREV_SESSION, ["BG"])], "one batched read, exactly that date"


def test_c_only_an_older_date_close_available_stays_dropped(monkeypatch):
    _patch_sources(monkeypatch, alpaca={"UFPI": _alpaca(100.0, OLDER_SESSION)},
                   stored={OLDER_SESSION: {"UFPI": (100.0, 1_000_000)}})
    rows = {"UFPI": _snap(0, 115.0, prev_vol=0)}
    patched, counts = _run(ep_detector._fill_missing_prev_closes(rows, SESSION_DATE, PREV_SESSION))
    assert patched == {} and counts == {"alpaca": 0, "stored": 0}


def test_a_close_with_no_known_volume_is_not_filled(monkeypatch):
    # never a silent volume-floor reject: an unknown volume keeps the counted drop
    _patch_sources(monkeypatch, alpaca={"TTC": _alpaca(80.0, PREV_SESSION, vol=None)},
                   stored={PREV_SESSION: {"TTC": (80.0, None)}})
    patched, _ = _run(ep_detector._fill_missing_prev_closes(
        {"TTC": _snap(0, 90.0, prev_vol=0)}, SESSION_DATE, PREV_SESSION))
    assert patched == {}


def test_e_stored_load_raising_fails_open_and_retries_a_capped_number_of_ticks(monkeypatch, caplog):
    seen = _patch_sources(monkeypatch, stored_exc=RuntimeError("pool exploded"))
    rows = {"BG": _snap(0, 80.0, prev_vol=0)}
    patched, counts = _run(ep_detector._fill_missing_prev_closes(rows, SESSION_DATE, PREV_SESSION))
    assert patched == {} and counts == {"alpaca": 0, "stored": 0}
    assert "stored-close stage failed" in caplog.text
    for _ in range(5):
        _run(ep_detector._fill_missing_prev_closes(rows, SESSION_DATE, PREV_SESSION))
    # a failed stage is retried, but only EP_PREV_CLOSE_FILL_MAX_FAILED_TICKS times a morning —
    # an outage must not cost every ORB-window tick the stage timeout
    assert len(seen["stored"]) == ep_detector.EP_PREV_CLOSE_FILL_MAX_FAILED_TICKS == 2
    # a new morning starts fresh
    _run(ep_detector._fill_missing_prev_closes(rows, date(2026, 11, 30), SESSION_DATE))
    assert len(seen["stored"]) == 3


def test_a_clean_answer_is_cached_for_the_morning(monkeypatch):
    seen = _patch_sources(monkeypatch, alpaca={"TTC": _alpaca(80.0, PREV_SESSION)})
    rows = {"TTC": _snap(0, 90.0, prev_vol=0), "NOPE": _snap(0, 9.0, prev_vol=0)}
    for _ in range(3):
        patched, counts = _run(ep_detector._fill_missing_prev_closes(rows, SESSION_DATE, PREV_SESSION))
        assert set(patched) == {"TTC"} and counts == {"alpaca": 1, "stored": 0}
    assert len(seen["alpaca"]) == 1 and len(seen["stored"]) == 1, "one fetch per morning"


def test_targets_are_only_rows_without_a_polygon_prev_close():
    snaps = {"HAS": _snap(50.0, 60.0), "ZERO": _snap(0, 60.0), "NOKEY": {"min": {"c": 5}},
             "AB.C": _snap(0, 6.0), "TOOLONG": _snap(0, 6.0), "BADPD": {"prevDay": None}}
    assert set(ep_detector._prev_close_fill_targets(snaps, set(), set())) == {"ZERO", "NOKEY"}


# ── (d) byte-identity on a Polygon row ───────────────────────────────────────────────

def test_d_snap_candidate_on_a_polygon_row_is_byte_identical_to_the_pre_736_shape():
    snap = _snap(50.0, 60.0)
    got = ep_detector._snap_candidate("HAS", snap, 50.0, 60.0, 20.0, {"HAS": 1_000_000.0}, 30)
    want = {"ticker": "HAS", "prev_close": 50.0, "current_price": 60.0, "gap_pct": 20.0,
            "today_volume": got["today_volume"], "prev_day_volume": 500_000, "adv": 1_000_000.0,
            "adv_source": "rs_universe", "rel_volume": got["rel_volume"],
            "projected_vol_multiple": got["projected_vol_multiple"], "gap_pct_delayed": 20.0,
            "price_source": "polygon_delayed"}
    assert got == want and list(got) == list(want)
    assert "prev_close_source" not in got


# ── run_ep_scan end to end on the incident morning ───────────────────────────────────

async def _drive(monkeypatch, snaps, *, alpaca=None, stored=None, stored_exc=None, fill=True):
    """One run_ep_scan, no date argument (as prod calls it), on 2026-11-27 pre-open. Captures the
    scan-log rows (one per candidate that reaches the graded loop) and the parse-drop audit."""
    from agents.market_intelligence import minute_volume as mv
    from tests.conftest import make_mock_pool

    scan_log, audits = [], []

    async def _toggle(name, env, default=True, **kw):
        return default

    async def _rvol(ticker, now_et, today_premkt_vol, today_session_vol):
        return {"anchor": "session", "rvol_at_time": 0.0, "baseline_n": mv.MIN_BASELINE_N_FOR_GATE,
                "today_cum_vol": int(today_session_vol), "baseline_mean": 1.0}

    async def _log_scan(rows):
        scan_log.extend(rows)

    async def _audit(event, *a, **k):
        audits.append((event, a))

    async def _noop(*a, **k):
        return None

    class _FrozenDatetime(datetime):
        @classmethod
        def now(cls, tz=None):
            return PRE_OPEN.astimezone(tz) if tz else PRE_OPEN.replace(tzinfo=None)

    pool, conn = make_mock_pool()
    conn.fetch = AsyncMock(return_value=[])
    conn.fetchval = AsyncMock(return_value=None)
    conn.fetchrow = AsyncMock(return_value=None)
    conn.execute = AsyncMock(return_value="INSERT 0 1")

    _patch_sources(monkeypatch, alpaca=alpaca, stored=stored, stored_exc=stored_exc)
    if not fill:   # the pre-#736 path: nothing is ever filled
        monkeypatch.setattr(ep_detector, "_fill_missing_prev_closes",
                            AsyncMock(return_value=({}, {"alpaca": 0, "stored": 0})))
    monkeypatch.setattr(ep_detector, "get_snapshot_all", AsyncMock(return_value=snaps))
    monkeypatch.setattr(ep_detector, "get_latest_regime",
                        AsyncMock(return_value={"regime": "Bull", "ep_threshold": 70}))
    monkeypatch.setattr(ep_detector, "get_adv_map", AsyncMock(return_value={}))
    monkeypatch.setattr(ep_detector, "latest_complete_score_date", AsyncMock(return_value=None))
    monkeypatch.setattr(ep_detector, "get_volume_history", AsyncMock(return_value={}))
    monkeypatch.setattr(ep_detector, "get_volume_history_daily_closes", AsyncMock(return_value={}))
    monkeypatch.setattr(ep_detector, "get_pool", AsyncMock(return_value=pool))
    monkeypatch.setattr(ep_detector, "get_runtime_toggle", _toggle)
    monkeypatch.setattr(ep_detector, "log_ep_scan_candidates", _log_scan)
    monkeypatch.setattr(ep_detector, "insert_ep_alert", _noop)
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
    from agents.market_intelligence import universe_floor_shadow, catalyst_tier_shadow
    from agents.market_intelligence import ep_shortlist_shadow as esls
    monkeypatch.setattr(universe_floor_shadow, "record_universe_floor_shadow", AsyncMock(return_value=0))
    monkeypatch.setattr(esls, "record_ep_shortlist_shadow", AsyncMock(return_value=0))
    monkeypatch.setattr(catalyst_tier_shadow, "fetch_board_sectors", AsyncMock(return_value={}))
    from agents.market_intelligence import setup_class_classifier as _scc
    monkeypatch.setattr(_scc, "get_recent_upgrade_events", AsyncMock(return_value=[]))
    from agents.market_intelligence import lowcap_lane as lane
    monkeypatch.setattr(lane, "should_run", AsyncMock(return_value=False))

    ep_detector._catalyst_cache_date = None
    ep_detector._catalyst_cache = {}
    await ep_detector.run_ep_scan()
    for _ in range(5):
        pending = [t for t in asyncio.all_tasks() if t is not asyncio.current_task() and not t.done()]
        if not pending:
            break
        await asyncio.gather(*pending, return_exceptions=True)
    return {r["ticker"]: r for r in scan_log}, audits


def _incident_snaps():
    snaps = {"HAS": _snap(50.0, 60.0)}                       # an ordinary Polygon row
    snaps["TTC"] = _snap(0, 96.0, prev_vol=0)                # (a) Alpaca dated 11-25
    snaps["BG"] = _snap(0, 88.0, prev_vol=0)                 # (b) stored 11-25
    snaps["UFPI"] = _snap(0, 130.0, prev_vol=0)              # (c) only an 11-24 close exists
    return snaps


_INCIDENT_ALPACA = {"TTC": _alpaca(80.0, PREV_SESSION), "UFPI": _alpaca(100.0, OLDER_SESSION)}
_INCIDENT_STORED = {PREV_SESSION: {"BG": (73.0, 2_000_000)},
                    OLDER_SESSION: {"UFPI": (100.0, 1_000_000)}}


@pytest.mark.asyncio
async def test_run_ep_scan_on_the_incident_morning_builds_the_filled_candidates(monkeypatch, caplog):
    caplog.set_level(logging.INFO, logger=ep_detector.logger.name)
    rows, _ = await _drive(monkeypatch, _incident_snaps(),
                           alpaca=_INCIDENT_ALPACA, stored=_INCIDENT_STORED)
    assert rows["TTC"]["prev_close"] == 80.0          # (a)
    assert rows["BG"]["prev_close"] == 73.0           # (b)
    assert "UFPI" not in rows                         # (c) older-date close never used
    assert "HAS" in rows
    line = [r.getMessage() for r in caplog.records if "candidate build dropped" in r.getMessage()]
    assert line and "1 with prev_close 0/missing" in line[0]
    assert "prev_close filled 2 (1 alpaca, 1 stored, date 2026-11-25)" in line[0]


@pytest.mark.asyncio
async def test_d_the_polygon_row_is_byte_identical_with_and_without_the_fill(monkeypatch):
    with_fill, _ = await _drive(monkeypatch, _incident_snaps(),
                                alpaca=_INCIDENT_ALPACA, stored=_INCIDENT_STORED)
    with monkeypatch.context() as m:
        without, _ = await _drive(m, _incident_snaps(), alpaca=_INCIDENT_ALPACA,
                                  stored=_INCIDENT_STORED, fill=False)
    assert set(without) == {"HAS"}, "pre-#736: every prevDay-0 row dropped"

    def _strip(r):
        # wall-clock stamps, and the two COHORT ranks (they move only because the filled names
        # now share the cohort — the row's own values must not move at all)
        r = copy.deepcopy(r)
        for k in ("seen_at", "created_at", "scan_ts", "rank_by_prescore", "rank_by_gap"):
            r.pop(k, None)
        return r
    assert _strip(with_fill["HAS"]) == _strip(without["HAS"])


@pytest.mark.asyncio
async def test_e_stored_load_raising_in_the_scan_keeps_todays_drop(monkeypatch):
    rows, _ = await _drive(monkeypatch, _incident_snaps(), alpaca={},
                           stored_exc=RuntimeError("pool exploded"))
    assert set(rows) == {"HAS"}


# ── a filled denominator is never verified by its own bar ────────────────────────────

@pytest.mark.asyncio
async def test_pass2_never_verifies_an_alpaca_filled_prev_close(monkeypatch):
    monkeypatch.setattr(ep_detector, "EP_RT_PASS2_ENABLED", True)

    async def _toggle(name, env, default=True, **kw):
        return default
    monkeypatch.setattr(ep_detector, "get_runtime_toggle", _toggle)
    monkeypatch.setattr(ep_detector, "log_audit_event", AsyncMock(return_value=None))
    sn = {**_alpaca(80.0, PREV_SESSION), "price": 96.0, "price_ts": PRE_OPEN}
    filled = ep_detector._snap_candidate(
        "TTC", {**_snap(80.0, 96.0), ep_detector._PREV_CLOSE_FILL_MARK:
                ep_detector.PREV_CLOSE_FILL_SRC_ALPACA}, 80.0, 96.0, 20.0, {}, None)
    plain = ep_detector._snap_candidate("HAS", _snap(80.0, 96.0), 80.0, 96.0, 20.0, {}, None)
    out = await ep_detector._apply_realtime_pass2(
        [filled, plain], PRE_OPEN, prev_trade_date=PREV_SESSION,
        snaps={"TTC": sn, "HAS": dict(sn)})
    by_t = {c["ticker"]: c for c in out}
    assert by_t["TTC"]["prev_close_source"] == ep_detector.PREV_CLOSE_FILL_SRC_ALPACA
    assert by_t["TTC"]["prev_close_verified"] is False
    assert by_t["HAS"]["prev_close_verified"] is True    # unchanged for a Polygon row
