"""#694 (2026-10-10, his option 2 on 2026-10-08): the shortlist RANKING reads LAST NIGHT'S
completed volume on every tick, and pre-market dollar volume orders the names with NO volume
record. GRADING is untouched (`adv_map` is not changed).

Why: `run_ep_scan()` is called with no date, so `prev_date` == today and `get_adv_map(prev_date)`
reads today's `mi_stock_scores` rows, which the RS run writes at ~17:00 -- the volume term of the
signed pre-score (45 of 65 points) was empty ALL DAY and every tie fell to ticker A->Z.

Pins here (each fails on the pre-#694 code):
  1. `shortlist_sort_key`: pm_dollar orders ONLY no-record names; known names ignore it.
  2. `compute_shortlist_ranking(last_night_adv=)`: the ENTRY carries `rs_prev_complete`; the
     candidate dict is not touched; a real own source wins; None / empty = old behaviour.
  3. Regression replays from scripts/probes/_694/dataset.csv: 10-05 and 07-30.
  4. `run_ep_scan` driven end to end on a PRE-OPEN and an AFTER-OPEN tick with today's scores
     absent and last night's complete: the shadow rows carry a real volume term; the no-record
     tie is decided by pre-market dollar volume, not A->Z; fail-open when no complete date.
"""
from __future__ import annotations

import asyncio
import csv
import logging
import sys
from datetime import date, datetime, timedelta
from pathlib import Path
from unittest.mock import AsyncMock
from zoneinfo import ZoneInfo

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from agents.market_intelligence import db
from agents.market_intelligence import ep_detector
from agents.market_intelligence import ep_shortlist_shadow as esls
from agents.market_intelligence.ep_rubric import SHORTLIST_SIZE, shortlist_sort_key
from agents.market_intelligence.ep_shortlist_shadow import (
    _REAL_ADV_SOURCES, compute_shortlist_ranking)

_ET = ZoneInfo("America/New_York")
_REPO = Path(__file__).resolve().parent.parent
_DATASET = _REPO / "scripts" / "probes" / "_694" / "dataset.csv"


# ── Part 1: the sort key ──────────────────────────────────────────────────────────────


def test_pm_dollar_orders_only_the_no_record_names():
    # two no-record names tied at the same composite: the bigger pre-market $ ranks first,
    # even though A->Z would put AAA first
    assert shortlist_sort_key("ZZZ", 32.5, None, 9_000_000) < \
           shortlist_sort_key("AAA", 32.5, None, 1_000_000)
    # no pre-market figure = 0, so it loses to any positive one and then falls to A->Z
    assert shortlist_sort_key("ZZZ", 32.5, None, 1.0) < shortlist_sort_key("AAA", 32.5, None, None)
    assert shortlist_sort_key("AAA", 32.5, None, None) < shortlist_sort_key("BBB", 32.5, None, None)


def test_names_with_a_record_ignore_pm_dollar_exactly_as_before():
    # equal composite + equal ADV$: pm_dollar must NOT reorder -> ticker asc, as before
    assert shortlist_sort_key("AAA", 46.0, 278e6, 1.0) < shortlist_sort_key("BBB", 46.0, 278e6, 9e12)
    # a bigger ADV$ still beats a bigger pm$
    assert shortlist_sort_key("BBB", 46.0, 300e6, 1.0) < shortlist_sort_key("AAA", 46.0, 278e6, 9e12)
    # the slot is exactly 0.0 for a name with a record
    assert shortlist_sort_key("AAA", 46.0, 278e6, 5e9)[2] == 0.0
    # omitting pm_dollar is the old signature's order
    assert shortlist_sort_key("AAA", 55.0, 1e9) == (-55.0, -1e9, 0.0, "AAA")


# ── Part 2: compute_shortlist_ranking(last_night_adv=) ────────────────────────────────


def _c(ticker, *, prev_close=50.0, gap=20.0, adv=None, src="pending",
       today_volume=None, price=None):
    return {"ticker": ticker, "prev_close": prev_close, "gap_pct": gap, "adv": adv,
            "adv_source": src, "today_volume": today_volume,
            "current_price": price if price is not None else prev_close * (1 + gap / 100)}


def test_the_entry_carries_last_nights_volume_and_the_candidate_is_untouched():
    cands = [_c("KNWN", adv=123.0, src="pending")]
    snapshot = dict(cands[0])
    entries, _ = compute_shortlist_ranking(cands, set(), last_night_adv={"KNWN": 10_000_000.0})
    e = entries[0]
    assert e["adv"] == 10_000_000.0 and e["adv_source"] == "rs_prev_complete"
    assert e["adv_dollar"] == 10_000_000.0 * 50.0 and e["composite"] == 55   # $500M tier
    assert cands[0] == snapshot, "the function stays pure: the candidate dict is not mutated"
    assert "rs_prev_complete" in _REAL_ADV_SOURCES


def test_a_real_own_source_wins_and_a_missing_map_is_todays_behaviour():
    own = _c("OWN", adv=2_000_000.0, src="rs_universe")
    entries, _ = compute_shortlist_ranking([own], set(), last_night_adv={"OWN": 99_999_999.0})
    assert entries[0]["adv"] == 2_000_000.0 and entries[0]["adv_source"] == "rs_universe"
    pend = _c("PEND", adv=5_555_555.0, src="pending")
    for ln in (None, {}, {"OTHER": 1.0}, {"PEND": 0}):
        entries, _ = compute_shortlist_ranking([pend], set(), last_night_adv=ln)
        assert entries[0]["adv_source"] == "pending" and entries[0]["adv_dollar"] is None
        assert entries[0]["composite"] == 32.5


def test_the_pm_dollar_sort_artifact_is_tv_times_price_and_is_not_a_persisted_field():
    cands = [_c("AAA", today_volume=100_000, price=10.0), _c("ZZZ", today_volume=900_000, price=10.0)]
    entries, ranks = compute_shortlist_ranking(cands, set())
    assert {e["ticker"]: e["pm_dollar"] for e in entries} == {"AAA": 1_000_000.0, "ZZZ": 9_000_000.0}
    assert ranks == {"ZZZ": 1, "AAA": 2}, "pre-market $ decides the no-record tie, not A->Z"
    rows = esls.build_shortlist_shadow_rows(entries, ranks, {"AAA": 1, "ZZZ": 2}, "prescore", 0)
    assert all("pm_dollar" not in r and "composite" not in r for r in rows)


# ── Part 3: regression replays from the 694 dataset ───────────────────────────────────


def _f(x):
    return float(x) if x not in ("", None) else None


def _replay(scan_date: str):
    """The last pre-open board of `scan_date` from the 694 dataset, run through the REAL
    compute_shortlist_ranking. Returns (kept, cut, ranks_old) where ranks_old = the same board
    ranked WITHOUT last night's volume (what the pre-#694 code did)."""
    rows = [r for r in csv.DictReader(open(_DATASET))
            if r["scan_date"] == scan_date and r["pool"] == "1"]
    cands, theme, last_night = [], set(), {}
    for r in rows:
        price = _f(r["tick_price"])
        pm = _f(r["k2_pm_dollar"])
        cands.append({
            "ticker": r["ticker"], "prev_close": _f(r["prev_close"]), "gap_pct": _f(r["gap_pct"]),
            "adv": None, "adv_source": "pending", "current_price": price,
            "today_volume": (pm / price) if pm and price else None,
        })
        if r["in_theme"] == "1":
            theme.add(r["ticker"])
        if _f(r["adv20_P"]):
            last_night[r["ticker"]] = _f(r["adv20_P"])
    _, ranks = compute_shortlist_ranking(cands, theme, last_night_adv=last_night)
    # the PRE-#694 ranking: no last-night volume, no pre-market figure -> composite, then A->Z
    _, ranks_old = compute_shortlist_ranking(
        [{**c, "today_volume": None} for c in cands], theme)
    # fix (b) alone (last night's volume, signed key as-is = option 1): no pre-market tie-break
    _, ranks_opt1 = compute_shortlist_ranking(
        [{**c, "today_volume": None} for c in cands], theme, last_night_adv=last_night)
    ordered = sorted(ranks, key=ranks.get)
    return ordered[:SHORTLIST_SIZE], ordered[SHORTLIST_SIZE:], ranks_old, ranks_opt1


def test_10_05_option_2_cuts_the_five_the_reviewer_replayed():
    kept, cut, *_ = _replay("2026-10-05")
    assert len(kept) + len(cut) == 25
    assert set(cut) == {"SBS", "PAGS", "INTR", "GRML", "VIV"}


def test_10_05_the_old_empty_volume_ranking_cut_the_names_that_were_lost():
    """What the live scan actually did (A->Z within a theme bucket; at the 09:25 board the
    alphabetical tail SBS, SDEV, STNE, TIMB, VIV -- at 09:20 SDEV, STNE, TIMB were cut for GRML,
    INTR, PAGS). Pins that the replay really measures a CHANGE."""
    _, _, ranks_old, _ = _replay("2026-10-05")
    old_cut = {t for t, r in ranks_old.items() if r > SHORTLIST_SIZE}
    assert {"SDEV", "STNE", "TIMB"} <= old_cut
    assert not old_cut & {"PBR", "XP"}           # the two in-theme names lead either way


def test_07_30_option_2_uses_the_premarket_tiebreak_among_no_record_names():
    kept, cut, _, ranks_opt1 = _replay("2026-07-30")
    assert len(kept) + len(cut) == 30
    assert {"STGW", "CMCO", "SMHI"} <= set(cut)
    assert {"PN", "SMTI", "BOOM"} <= set(kept)
    # option 1 (last night's volume, signed key as-is) cuts the alphabetically last of that
    # tied group instead -- the pre-market tie-break is what changes it
    opt1_cut = {t for t, r in ranks_opt1.items() if r > SHORTLIST_SIZE}
    assert {"SMHI", "SMTI", "STGW"} <= opt1_cut and "PN" not in opt1_cut


# ── Part 4: run_ep_scan end to end (the lookup is empty ALL DAY, so pre-open AND after-open) ──


SESSION_DATE = date(2026, 10, 7)          # a Wednesday
LAST_NIGHT = date(2026, 10, 6)
PRE_OPEN = datetime(2026, 10, 7, 9, 25, 12, tzinfo=_ET)
AFTER_OPEN = datetime(2026, 10, 7, 10, 31, 12, tzinfo=_ET)

KNOWN = [f"KN{i:02d}" for i in range(12)]            # last-night record, $500M+ -> composite 55
NO_REC = [f"NR{i:02d}" for i in range(10)]           # no record -> composite 32.5
# pre-market volume DEcreases with the ticker number, except the two A->Z-LAST names which are
# the busiest: A->Z would cut NR08/NR09 (alphabetically last); the pm$ tie-break cuts the two
# LOWEST-volume ones, NR06/NR07.
NR_VOL = {"NR00": 900_000, "NR01": 800_000, "NR02": 700_000, "NR03": 600_000, "NR04": 500_000,
          "NR05": 400_000, "NR06": 150_000, "NR07": 140_000, "NR08": 1_200_000, "NR09": 1_100_000}


def _snap(prev_close, price, today_vol, prev_vol=500_000):
    return {"prevDay": {"c": prev_close, "v": prev_vol},
            "min": {"c": price, "av": today_vol},
            "day": {"o": price, "v": today_vol},
            "lastTrade": {"p": price}}


async def _drive(monkeypatch, *, tick: datetime, complete_date, ln_raises=False):
    """One full run_ep_scan, called the way production calls it (NO date argument), with
    today's mi_stock_scores empty and last night's complete. Every candidate is killed at the
    RVOL@T gate (the earliest graded-loop kill) -- this drives the SHORTLIST, not the grading.
    Returns (shadow_rows, scan_log_rows, latest_complete_mock, get_adv_map_mock)."""
    from agents.market_intelligence import minute_volume as mv
    from tests.conftest import make_mock_pool

    snaps = {t: _snap(50.0, 60.0, 5_000_000) for t in KNOWN}
    snaps.update({t: _snap(50.0, 60.0, NR_VOL[t]) for t in NO_REC})
    last_night = {t: 10_000_000.0 for t in KNOWN}      # x $50 prev close = $500M ADV$
    scan_log, shadow = [], []

    async def _adv(d):
        # prod shape: today's rows are not written yet -> empty; last night's are complete
        return {} if str(d)[:10] == SESSION_DATE.isoformat() else dict(last_night)

    async def _toggle(name, env, default=True, **kw):
        return default

    async def _rvol(ticker, now_et, today_premkt_vol, today_session_vol):
        return {"anchor": "session", "rvol_at_time": 0.0, "baseline_n": mv.MIN_BASELINE_N_FOR_GATE,
                "today_cum_vol": int(today_session_vol), "baseline_mean": 1.0}

    async def _log_scan(rows):
        scan_log.extend(rows)

    async def _record(rows, scan_date, now_et):
        shadow.extend(rows)
        return len(rows)

    async def _noop(*a, **k):
        return None

    class _FrozenDatetime(datetime):
        @classmethod
        def now(cls, tz=None):
            return tick.astimezone(tz) if tz else tick.replace(tzinfo=None)

    pool, conn = make_mock_pool()
    conn.fetch = AsyncMock(return_value=[])
    conn.fetchval = AsyncMock(return_value=None)
    conn.fetchrow = AsyncMock(return_value=None)
    conn.execute = AsyncMock(return_value="INSERT 0 1")
    latest = (AsyncMock(side_effect=RuntimeError("pool exploded")) if ln_raises
              else AsyncMock(return_value=complete_date))
    adv_mock = AsyncMock(side_effect=_adv)

    monkeypatch.setattr(ep_detector, "get_snapshot_all", AsyncMock(return_value=snaps))
    monkeypatch.setattr(ep_detector, "get_latest_regime", AsyncMock(return_value={"regime": "Bull", "ep_threshold": 70}))
    monkeypatch.setattr(ep_detector, "get_adv_map", adv_mock)
    monkeypatch.setattr(ep_detector, "latest_complete_score_date", latest)
    monkeypatch.setattr(ep_detector, "get_volume_history", AsyncMock(return_value={}))
    monkeypatch.setattr(ep_detector, "get_volume_history_daily_closes", AsyncMock(return_value={}))
    monkeypatch.setattr(ep_detector, "get_pool", AsyncMock(return_value=pool))
    monkeypatch.setattr(ep_detector, "get_runtime_toggle", _toggle)
    monkeypatch.setattr(ep_detector, "log_ep_scan_candidates", _log_scan)
    monkeypatch.setattr(ep_detector, "insert_ep_alert", _noop)
    monkeypatch.setattr(ep_detector, "log_audit_event", _noop)
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
    monkeypatch.setattr(universe_floor_shadow, "record_universe_floor_shadow", AsyncMock(return_value=0))
    monkeypatch.setattr(esls, "record_ep_shortlist_shadow", _record)
    monkeypatch.setattr(catalyst_tier_shadow, "fetch_board_sectors", AsyncMock(return_value={}))
    from agents.market_intelligence import setup_class_classifier as _scc
    monkeypatch.setattr(_scc, "get_recent_upgrade_events", AsyncMock(return_value=[]))
    # the 624 harness's lane hook is scheduled on the same path; keep it inert
    from agents.market_intelligence import lowcap_lane as lane
    monkeypatch.setattr(lane, "should_run", AsyncMock(return_value=False))

    ep_detector._catalyst_cache_date = None
    ep_detector._catalyst_cache = {}
    await ep_detector.run_ep_scan()                       # NO date, exactly as prod calls it
    for _ in range(5):
        pending = [t for t in asyncio.all_tasks() if t is not asyncio.current_task() and not t.done()]
        if not pending:
            break
        await asyncio.gather(*pending, return_exceptions=True)
    return shadow, scan_log, latest, adv_mock


def _cut(scan_log):
    return {r["ticker"] for r in scan_log if r["reject_stage"] == "shortlist_cap"}


@pytest.mark.asyncio
@pytest.mark.parametrize("tick", [PRE_OPEN, AFTER_OPEN], ids=["pre_open", "after_open"])
async def test_run_ep_scan_ranks_on_last_nights_volume_with_todays_scores_absent(monkeypatch, tick):
    shadow, scan_log, latest, adv_mock = await _drive(monkeypatch, tick=tick, complete_date=LAST_NIGHT)

    # the lookup is bounded exactly as the card says, on an open connection
    assert latest.await_count == 1
    kw = latest.await_args.kwargs
    assert kw == {"on_or_before": SESSION_DATE - timedelta(days=1),
                  "on_or_after": SESSION_DATE - timedelta(days=7)}
    assert latest.await_args.args, "called with the open connection"

    # THE DoD: the volume term is populated -- the known names carry last night's volume
    by_t = {r["ticker"]: r for r in shadow}
    assert len(by_t) == 22
    for t in KNOWN:
        assert by_t[t]["adv_source"] == "rs_prev_complete" and by_t[t]["adv"] == 10_000_000.0
    # a no-record name stays a placeholder (liquidity axis missing -> composite rescales)
    assert all(by_t[t]["adv_source"] == "pending" for t in NO_REC)

    # the ranking: the 12 known names (composite 55) lead; the no-record tie is decided by
    # pre-market $ volume (NR08 > NR09 > NR00 ... > NR07), NOT A->Z
    ranks = {t: r["rank_by_prescore"] for t, r in by_t.items()}
    assert sorted(KNOWN, key=ranks.get) == sorted(KNOWN)           # equal everything -> ticker asc
    assert max(ranks[t] for t in KNOWN) == 12
    assert [t for t in sorted(NO_REC, key=ranks.get)] == sorted(NO_REC, key=lambda t: -NR_VOL[t])

    # and the graded cohort (acting key = prescore) cut the two LOWEST pre-market $ names
    assert all(r["acting_key"] == "prescore" for r in shadow)
    assert _cut(scan_log) == {"NR06", "NR07"}, "A->Z would have cut NR08/NR09"
    assert len(by_t) - len(_cut(scan_log)) == SHORTLIST_SIZE

    # GRADING IS UNTOUCHED: the main adv_map is still today's (empty) lookup; last night's map
    # was read as a SEPARATE call and only fed the ranking
    dates = [str(c.args[0])[:10] for c in adv_mock.await_args_list]
    assert dates.count(SESSION_DATE.isoformat()) == 1 and dates.count(LAST_NIGHT.isoformat()) == 1


@pytest.mark.asyncio
async def test_no_complete_prior_date_is_todays_behaviour_and_logs_one_line(monkeypatch, caplog):
    caplog.set_level(logging.INFO, logger=ep_detector.logger.name)
    shadow, scan_log, latest, _ = await _drive(monkeypatch, tick=PRE_OPEN, complete_date=None)
    assert latest.await_count == 1
    by_t = {r["ticker"]: r for r in shadow}
    assert len(by_t) == 22 and all(r["adv_source"] == "pending" for r in shadow)
    # today's behaviour: every composite ties -> pre-market $ still orders (fix applies to
    # all pending names), but NO last-night volume is invented
    assert all(r["adv"] != 10_000_000.0 for r in shadow)
    lines = [r.getMessage() for r in caplog.records if "ranking without last-night volume" in r.getMessage()]
    assert len(lines) == 1, lines


@pytest.mark.asyncio
async def test_a_lookup_error_fails_open_loudly_and_the_scan_still_ranks(monkeypatch, caplog):
    caplog.set_level(logging.WARNING, logger=ep_detector.logger.name)
    shadow, scan_log, _, _ = await _drive(monkeypatch, tick=PRE_OPEN, complete_date=None, ln_raises=True)
    assert len(shadow) == 22 and all(r["adv_source"] == "pending" for r in shadow)
    assert len(scan_log) == 22, "the scan completed"
    assert any("last-night volume lookup failed" in r.getMessage() for r in caplog.records)

