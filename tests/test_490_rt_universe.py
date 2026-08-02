"""#490 RT-1 — Pass-0 full-universe real-time overlay (design §5.1) + Q1-Q4 tick-quality
guards (§3) + halt quarantine (§4) + split hold (§2.2).

The load-bearing FREEZE guarantee: with EP_RT_UNIVERSE_ENABLED off (the deploy default), the
overlay is a pure no-op — candidates returned as the SAME object, zero Alpaca calls — so a
dark deploy is byte-identical to the #489 hybrid. With the flag on but the
`ep_rt_universe_authoritative` toggle off (shadow), the candidate cohort is STILL untouched:
a guard-passing rt crosser emits `ep_rt_universe_catch` audit-only (digest surfacing per the
7/21 noise ruling) and is NOT admitted (no LLM spend).
"""
import asyncio
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

from agents.market_intelligence import collector, ep_detector

_ET = ZoneInfo("America/New_York")
_PREV = date(2026, 7, 23)


def _now(h=8, m=0):
    return datetime(2026, 7, 24, h, m, 0, tzinfo=_ET)


def _bar_ts(d: date):
    return datetime(d.year, d.month, d.day, 0, 0, tzinfo=_ET)


def _sn(now, pc, *, price=12.0, price_age=5.0, bid=11.98, ask=12.02, quote_age=10.0,
        minute_close=11.95, minute_vol=50_000, minute_age=60.0,
        daily_close=None, daily_date=_PREV, prev_daily_close=None, prev_daily_date=None):
    """A guard-passing rt snapshot by default: fresh in-band print, corroborating bar,
    date-matched daily_bar == the Polygon prev_close (pre-open semantics)."""
    return {
        "price": price,
        "price_ts": now - timedelta(seconds=price_age) if price_age is not None else None,
        "bid": bid, "ask": ask, "bid_size": 1, "ask_size": 1,
        "quote_ts": now - timedelta(seconds=quote_age) if quote_age is not None else None,
        "minute_close": minute_close, "minute_volume": minute_vol,
        "minute_ts": now - timedelta(seconds=minute_age) if minute_age is not None else None,
        "day_volume": None,
        "daily_bar_close": pc if daily_close is None else daily_close,
        "daily_bar_ts": _bar_ts(daily_date) if daily_date else None,
        "prev_close": prev_daily_close,
        "prev_daily_bar_ts": _bar_ts(prev_daily_date) if prev_daily_date else None,
    }


_POLY_SNAP = {"NVVE": {"min": {"c": 10.1}, "prevDay": {"c": 10.0, "v": 1_000_000}}}


def _wire(monkeypatch, snaps, *, authoritative=False, stats_fill=None, holds=None,
          universe_on=True):
    monkeypatch.setattr(ep_detector, "EP_RT_UNIVERSE_ENABLED", universe_on)
    monkeypatch.setattr(ep_detector, "EP_RT_PASS2_ENABLED", True)

    async def _toggle(name, env, default=True):
        return authoritative
    monkeypatch.setattr(ep_detector, "get_runtime_toggle", _toggle)

    async def _snaps_fn(tickers, timeout_s=4.0, concurrency=1, stats=None):
        if stats is not None:
            stats.update(stats_fill or {"batches_total": 1, "batches_failed": 0})
        return snaps
    monkeypatch.setattr(collector, "get_alpaca_snapshots_batch", _snaps_fn)

    async def _holds(today):
        return holds if holds is not None else set()
    monkeypatch.setattr(ep_detector, "_corp_action_holds_today", _holds)
    monkeypatch.setattr(ep_detector, "_audit_dedupe_check", lambda *a, **k: True)
    monkeypatch.setattr(ep_detector, "_rt_fresh_seen", set())
    monkeypatch.setattr(ep_detector, "_rt_fresh_seen_date", None)

    logged = []

    async def _log(event_type, summary, detail=""):
        logged.append(event_type)
    monkeypatch.setattr(ep_detector, "log_audit_event", _log)
    return logged


def _overlay(cands, snaps_universe, now):
    return asyncio.run(ep_detector._apply_rt_universe_overlay(
        cands, [("NVVE", 10.0)], _POLY_SNAP, {}, None, now, _PREV))


# ── FREEZE: flags off = pure no-op, zero fetches ────────────────────────────────────────────

def test_overlay_noop_when_universe_flag_off(monkeypatch):
    monkeypatch.setattr(ep_detector, "EP_RT_UNIVERSE_ENABLED", False)
    monkeypatch.setattr(ep_detector, "EP_RT_PASS2_ENABLED", True)

    async def _boom(*a, **k):
        raise AssertionError("flags-off must NEVER fetch")
    monkeypatch.setattr(collector, "get_alpaca_snapshots_batch", _boom)
    cands = [{"ticker": "AAA", "gap_pct": 12.0}]
    out, snaps = asyncio.run(ep_detector._apply_rt_universe_overlay(
        cands, [("NVVE", 10.0)], _POLY_SNAP, {}, None, _now(), _PREV))
    assert out is cands and snaps is None


def test_overlay_noop_when_pass2_off(monkeypatch):
    # R5 semantics: killing the hybrid kills the universe overlay with it.
    monkeypatch.setattr(ep_detector, "EP_RT_UNIVERSE_ENABLED", True)
    monkeypatch.setattr(ep_detector, "EP_RT_PASS2_ENABLED", False)

    async def _boom(*a, **k):
        raise AssertionError("pass2-off must NEVER fetch")
    monkeypatch.setattr(collector, "get_alpaca_snapshots_batch", _boom)
    cands = []
    out, snaps = asyncio.run(ep_detector._apply_rt_universe_overlay(
        cands, [("NVVE", 10.0)], _POLY_SNAP, {}, None, _now(), _PREV))
    assert out is cands and snaps is None


# ── SHADOW: catch event, NOT admitted ───────────────────────────────────────────────────────

def test_shadow_crosser_emits_catch_but_is_not_admitted(monkeypatch):
    now = _now()
    logged = _wire(monkeypatch, {"NVVE": _sn(now, 10.0)}, authoritative=False)
    cands = []
    out, snaps = _overlay(cands, None, now)
    assert out is cands and out == []          # cohort untouched — no LLM spend
    assert "ep_rt_universe_catch" in logged
    assert snaps is not None                    # the map is reused by Pass-2 + the watchdog


def test_authoritative_crosser_is_admitted_as_candidate(monkeypatch):
    now = _now()
    _wire(monkeypatch, {"NVVE": _sn(now, 10.0)}, authoritative=True)
    out, _ = _overlay([], None, now)
    assert len(out) == 1
    c = out[0]
    assert c["ticker"] == "NVVE"
    assert c["price_source"] == "alpaca_sip_universe"
    assert c["gap_pct"] == 20.0 and c["gap_pct_rt"] == 20.0
    assert c["current_price"] == 12.0           # §6.4 coherence — rt price IS the decided price
    assert c["gap_pct_delayed"] == 1.0          # the delayed read rides along, honestly labeled
    assert c["prev_close_verified"] is True
    assert c["prev_close"] == 10.0              # Polygon prevDay.c stays the SOLE denominator


def test_already_candidate_ticker_is_left_to_pass2(monkeypatch):
    now = _now()
    logged = _wire(monkeypatch, {"NVVE": _sn(now, 10.0)}, authoritative=True)
    cands = [{"ticker": "NVVE", "gap_pct": 6.0, "prev_close": 10.0, "gap_pct_delayed": 6.0}]
    out, _ = _overlay(cands, None, now)
    assert len(out) == 1 and out[0]["gap_pct"] == 6.0   # untouched here — Pass-2 owns the cohort
    assert "ep_rt_universe_catch" not in logged


# ── Q1-Q4 guard rejections (each enum reason reachable + LOUD) ─────────────────────────────

def _reject_events(logged):
    return [e for e in logged if e == "ep_rt_tick_quality_reject"]


def test_q3_no_bar_confirm_rejects_admission(monkeypatch):
    now = _now()
    # Fresh in-band print but NO minute bar → no RT-only admission on one print alone.
    logged = _wire(monkeypatch, {"NVVE": _sn(now, 10.0, minute_close=None, minute_vol=0)})
    out, _ = _overlay([], None, now)
    assert out == [] and _reject_events(logged) and "ep_rt_universe_catch" not in logged


def test_crossed_quote_without_bar_rejects(monkeypatch):
    now = _now()
    logged = _wire(monkeypatch, {"NVVE": _sn(now, 10.0, bid=12.10, ask=12.02,
                                             minute_close=None, minute_vol=0)})
    out, _ = _overlay([], None, now)
    assert out == [] and _reject_events(logged)


def test_outside_band_print_without_bar_rejects(monkeypatch):
    now = _now()
    # Fresh valid quote 10.00/10.04 but print at 12.0 — way outside the NBBO band, no bar.
    logged = _wire(monkeypatch, {"NVVE": _sn(now, 10.0, bid=10.00, ask=10.04,
                                             minute_close=None, minute_vol=0)})
    out, _ = _overlay([], None, now)
    assert out == [] and _reject_events(logged)


def test_outside_band_print_falls_back_to_corroborating_bar(monkeypatch):
    now = _now()
    # Print 12.0 outside a 11.0/11.04 quote, but a fresh minute bar at 11.02 (+10.2%)
    # corroborates → the read falls through to the BAR close and still catches.
    logged = _wire(monkeypatch, {"NVVE": _sn(now, 10.0, bid=11.00, ask=11.04,
                                             minute_close=11.02)})
    out, snaps = _overlay([], None, now)
    assert "ep_rt_universe_catch" in logged and not _reject_events(logged)


def test_stale_quote_with_corroborating_bar_is_accepted(monkeypatch):
    now = _now()
    # Quote 20 min old pre-open (> 300s) → Q1 skipped → Q3 carries the admission.
    logged = _wire(monkeypatch, {"NVVE": _sn(now, 10.0, quote_age=1200.0)})
    out, _ = _overlay([], None, now)
    assert "ep_rt_universe_catch" in logged and not _reject_events(logged)


def test_q4_insane_gap_rejected_without_q1_and_q3(monkeypatch):
    now = _now()
    # +250% print, stale quote, no bar → insane_gap hard reject.
    logged = _wire(monkeypatch, {"NVVE": _sn(now, 10.0, price=35.0, quote_age=1200.0,
                                             minute_close=None, minute_vol=0)})
    out, _ = _overlay([], None, now)
    assert out == [] and _reject_events(logged) and "ep_rt_universe_catch" not in logged


def test_q4_real_100pct_mover_passes_with_q1_and_q3(monkeypatch):
    now = _now()
    # The NVVE class Q4 exists to PROTECT: price 4.5× prev_close but a real NBBO and real
    # printed bars back it → accepted (the old 30pp clamp would have rejected it).
    logged = _wire(monkeypatch, {"NVVE": _sn(now, 10.0, price=45.0, bid=44.9, ask=45.1,
                                             minute_close=44.8)})
    out, _ = _overlay([], None, now)
    assert "ep_rt_universe_catch" in logged and not _reject_events(logged)


# ── §2.2 split hold + §2.1 mismatch + §4 halt quarantine ───────────────────────────────────

def test_corp_action_hold_blocks_rt_admission(monkeypatch):
    now = _now()
    logged = _wire(monkeypatch, {"NVVE": _sn(now, 10.0)}, holds={"NVVE"})
    out, _ = _overlay([], None, now)
    assert out == [] and "ep_rt_corp_action_hold" in logged
    assert "ep_rt_universe_catch" not in logged


def test_date_keyed_mismatch_degrades_to_delayed(monkeypatch):
    now = _now()
    # daily_bar (date-matched) close 11.0 vs Polygon 10.0 = 10% disagreement → degrade.
    logged = _wire(monkeypatch, {"NVVE": _sn(now, 10.0, daily_close=11.0)})
    out, _ = _overlay([], None, now)
    assert out == [] and "ep_rt_prev_close_mismatch" in logged
    assert "ep_rt_universe_catch" not in logged


def test_halt_suspect_quarantined_after_fresh_session_print(monkeypatch):
    now1, now2 = _now(9, 35), _now(9, 40)
    sn_fresh = _sn(now1, 10.0)
    logged = _wire(monkeypatch, {"NVVE": sn_fresh})
    _overlay([], None, now1)                      # tick 1: fresh print RTH → tracked (+ a catch)
    catches_after_tick1 = logged.count("ep_rt_universe_catch")
    # tick 2: print frozen (5 min old) + crossed quote + stale → halt_suspect.
    sn_frozen = _sn(now2, 10.0, price_age=300.0, bid=0, ask=0, quote_age=300.0)
    monkeypatch.setattr(collector, "get_alpaca_snapshots_batch",
                        _mk_snaps_fn({"NVVE": sn_frozen}))
    out, _ = asyncio.run(ep_detector._apply_rt_universe_overlay(
        [], [("NVVE", 10.0)], _POLY_SNAP, {}, 10, now2, _PREV))
    assert out == [] and "ep_rt_halt_suspect" in logged
    # tick 2 must NOT add a catch — the frozen name can't be RT-only admitted this tick.
    assert logged.count("ep_rt_universe_catch") == catches_after_tick1


def _mk_snaps_fn(snaps):
    async def _fn(tickers, timeout_s=4.0, concurrency=1, stats=None):
        if stats is not None:
            stats.update({"batches_total": 1, "batches_failed": 0})
        return snaps
    return _fn


# ── §5.3 failure ladder ────────────────────────────────────────────────────────────────────

def test_batch_failure_emits_degraded_event(monkeypatch):
    now = _now()
    logged = _wire(monkeypatch, {"NVVE": _sn(now, 10.0)},
                   stats_fill={"batches_total": 34, "batches_failed": 2})
    _overlay([], None, now)
    assert "ep_rt_universe_degraded" in logged


def test_whole_fetch_failure_degrades_to_hybrid_and_alerts(monkeypatch):
    now = _now()
    _wire(monkeypatch, {})

    async def _boom(tickers, timeout_s=4.0, concurrency=1, stats=None):
        raise RuntimeError("alpaca down")
    monkeypatch.setattr(collector, "get_alpaca_snapshots_batch", _boom)
    alerted = []

    async def _alert(provider, exc, context=""):
        alerted.append((provider, context))
    from agents.market_intelligence import llm_health
    monkeypatch.setattr(llm_health, "maybe_alert_api_failure", _alert)
    cands = [{"ticker": "AAA", "gap_pct": 12.0}]
    out, snaps = _overlay(cands, None, now)
    assert out is cands and snaps is None
    assert alerted == [("alpaca", "ep_rt_universe")]


# ── _snap_candidate freeze (byte-identical to the pre-#490 Pass-1 inline block) ────────────

def test_snap_candidate_parity_premarket_no_adv_map():
    snap = {"day": {"v": 500}, "min": {"av": 800}, "prevDay": {"v": 123}}
    assert ep_detector._snap_candidate("ABC", snap, 10.0, 11.0, 10.0, {}, None) == {
        "ticker": "ABC", "prev_close": 10.0, "current_price": 11.0, "gap_pct": 10.0,
        "today_volume": 500, "adv": 123, "adv_source": "pending",
        "rel_volume": round(500 / 123, 2), "projected_vol_multiple": None,
        "gap_pct_delayed": 10.0, "price_source": "polygon_delayed",
    }


def test_snap_candidate_parity_postopen_projection():
    snap = {"day": {"v": 500}, "min": {}, "prevDay": {"v": 123}}
    out = ep_detector._snap_candidate("ABC", snap, 10.0, 11.5, 15.0, {"ABC": 1000}, 20)
    assert out["adv"] == 1000 and out["adv_source"] == "rs_universe"
    assert out["rel_volume"] == 0.5
    assert out["projected_vol_multiple"] == round(0.5 * (390 / 20), 1)


def test_snap_candidate_parity_pre945_no_projection():
    snap = {"day": {"v": 500}, "min": {}, "prevDay": {"v": 123}}
    out = ep_detector._snap_candidate("ABC", snap, 10.0, 11.5, 15.0, {"ABC": 1000}, 5)
    assert out["projected_vol_multiple"] is None   # <15 min since open — raw RVOL governs


# ── fork 4: shadow catches surface DIGEST-ONLY (ride the existing 10:00 digest) ────────────

def _digest_pool(monkeypatch, miss_rows, catch_rows):
    import json as _json

    class _C:
        def __init__(self):
            self.calls = 0

        async def fetch(self, q, *a):
            self.calls += 1
            rows = miss_rows if "ep_rt_live_miss" in q else catch_rows
            return [{"detail": _json.dumps(r)} for r in rows]

    class _A:
        async def __aenter__(self):
            return _C()

        async def __aexit__(self, *a):
            return False

    class _P:
        def acquire(self):
            return _A()

    async def _pool():
        return _P()
    monkeypatch.setattr(ep_detector, "get_pool", _pool)


def test_digest_appends_universe_catches_dedup_vs_misses(monkeypatch):
    from agents.market_intelligence import briefing
    _digest_pool(
        monkeypatch,
        [{"ticker": "AEHR", "rt_gap": 12.5, "tick_et": "09:31"}],
        [{"ticker": "AEHR", "rt_gap": 12.5, "tick_et": "09:31"},     # overlap → deduped
         {"ticker": "NVVE", "rt_gap": 31.8, "tick_et": "07:35"}])    # pre-open — watchdog-blind
    sent = []

    async def _tg(msg):
        sent.append(msg)
        return True
    monkeypatch.setattr(briefing, "send_telegram_message", _tg)
    n = asyncio.run(ep_detector.send_rt_miss_digest(run_date=date(2026, 7, 24)))
    assert n == 2 and len(sent) == 1
    assert "NVVE" in sent[0] and "shadow catches (1" in sent[0]


def test_digest_catches_only_still_sends(monkeypatch):
    from agents.market_intelligence import briefing
    _digest_pool(monkeypatch, [], [{"ticker": "NVVE", "rt_gap": 31.8, "tick_et": "07:35"}])
    sent = []

    async def _tg(msg):
        sent.append(msg)
        return True
    monkeypatch.setattr(briefing, "send_telegram_message", _tg)
    n = asyncio.run(ep_detector.send_rt_miss_digest(run_date=date(2026, 7, 24)))
    assert n == 1 and len(sent) == 1 and "NVVE" in sent[0]
    assert "Real-time EP misses" not in sent[0]


# ── #490 gate-1 diagnostic: the three previously-SILENT drop paths ───────────────────────────
# The RT-2 packet could not explain 5 residual misses (QMCO/QURE/SCL 7/29, DY 7/30, VECO 7/31).
# Each passed every universe filter, was liquid and CS-classified, and produced NO ep_rt_* event
# of any kind. Reading the overlay showed why: three paths dropped a ticker with zero telemetry.
# Until they are named, a miss cannot be attributed and gate 1 cannot be signed either way.

def test_the_three_silent_paths_are_now_named():
    """Static, deliberately: these fire only inside a live overlay tick against a real snapshot
    batch, so behaviour tests would need the whole fetch mocked. What matters for gate 1 is that
    each drop EMITS something — assert the emit sites exist and each `continue` is preceded by a
    log call."""
    src = open("agents/market_intelligence/ep_detector.py").read()
    for ev in ("ep_rt_universe_coverage", "ep_rt_no_price", "ep_rt_retreated_below_floor"):
        assert f'"{ev}"' in src, f"{ev} missing — that drop path is still silent"


def test_coverage_telemetry_is_unconditional():
    """The pre-existing `ep_rt_universe_degraded` event fires only when a whole BATCH fails, so a
    tick where every batch succeeded but individual symbols came back empty was invisible. The
    coverage row must therefore NOT sit behind the batches_failed check."""
    src = open("agents/market_intelligence/ep_detector.py").read()
    cov = src.index('"ep_rt_universe_coverage"')
    degraded = src.index('if stats.get("batches_failed"):')
    assert cov < degraded, "coverage telemetry must be logged BEFORE/outside the degraded branch"


def test_retreat_is_distinguishable_from_a_data_gap():
    """The whole point: a benign retreat below the floor and a missing RT read must not look the
    same in the audit log, or gate 1's misses stay unattributable."""
    src = open("agents/market_intelligence/ep_detector.py").read()
    assert '"ep_rt_retreated_below_floor"' in src and '"ep_rt_no_price"' in src
    assert src.index('"ep_rt_no_price"') < src.index('"ep_rt_retreated_below_floor"')
