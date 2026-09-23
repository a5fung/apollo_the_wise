"""#327 blocker fix + shadow-fix pack wiring (operator-signed 2026-07-14).

Part A — the readiness SCAN is time-budgeted and the settlement ALWAYS runs. On 7/13 the Monday
scan HUNG >2h (unbounded cumulative M&A-guard Polygon time) and was watchdog-killed, so the
INLINE settlement never ran — 170 rows stuck past-ripe. Pins:
  • scan times out → consolidation_readiness_scan_timeout audit event + settlement still runs +
    the job completes cleanly (success, not aborted);
  • no-timeout path emits no timeout audit (guards inverted logic);
  • the #387 M&A guard is CAPPED per run (fail-open past _CONS_MNA_CHECKS_CAP + one audit row).

Part B wiring — the scan records the shadow-fix pack on every fire (§1 quality flag RECORDED
never gated · §2 structural_low headline stop + coiled_low continuity + sub-1% flag · §3 the
re-wired Confirm control arm, tagged entry_mode='confirm' · §4 regime_at_entry), and the
settlement step threads §5's bound_conflict + realized_r_h12 into the write-back.

Everything here is SHADOW/telemetry — the pins assert recording, never any submit path.
"""
import asyncio
from datetime import date, timedelta

import pytest

import agents.market_intelligence.anticipation as ant
import agents.market_intelligence.scheduler as sched
from agents.market_intelligence.audit_events import (
    ANTICIPATION_MNA_CHECK_CAPPED, CONSOLIDATION_READINESS_SCAN_TIMEOUT,
)

_TODAY = date(2026, 7, 14)


def _patch_job_shell(monkeypatch, *, settled=None):
    """Patch the JOB's non-scan collaborators; returns (audits, telegrams, settle_calls)."""
    import agents.market_intelligence.briefing as briefing
    import agents.market_intelligence.collector as collector
    import agents.market_intelligence.db as db

    audits, telegrams, settle_calls = [], [], []

    async def fake_audit(event_type, summary, detail=None):
        audits.append((event_type, summary))

    async def fake_settle(today):
        settle_calls.append(today)
        return settled or []

    async def fake_htf(today):
        return []

    async def fake_send(msg):
        telegrams.append(msg)
        return True

    async def fake_open_tickers():
        return set()

    monkeypatch.setattr(sched, "log_audit_event", fake_audit)
    monkeypatch.setattr(sched, "_run_entry_shadow_settlement", fake_settle)
    monkeypatch.setattr(sched, "_htf_breakout_settle_job", fake_htf)
    monkeypatch.setattr(collector, "et_today", lambda: _TODAY)
    monkeypatch.setattr(briefing, "send_telegram_message", fake_send)
    monkeypatch.setattr(db, "get_open_shadow_tickers", fake_open_tickers)
    return audits, telegrams, settle_calls


# ── Part A(1): scan times out → audit + settlement STILL runs + clean return ──────────────────
@pytest.mark.asyncio
async def test_scan_timeout_settlement_still_runs(monkeypatch):
    audits, telegrams, settle_calls = _patch_job_shell(monkeypatch)
    monkeypatch.setattr(sched, "_CONS_SCAN_BUDGET_S", 0.05)

    async def hanging_scan(today, stats, transitions, entries_fired):
        stats["written"] = 3          # partial progress BEFORE the hang — must survive the cancel
        await asyncio.sleep(60)       # the 7/13 failure mode: the scan never returns

    monkeypatch.setattr(sched, "_consolidation_readiness_scan", hanging_scan)

    await sched._consolidation_readiness_job()   # must NOT raise — the job completes (success)

    # settlement ran despite the hung scan (the 170-row-backlog fix):
    assert settle_calls == [_TODAY]
    # the timeout was audited, loudly:
    timeout_audits = [a for a in audits if a[0] == CONSOLIDATION_READINESS_SCAN_TIMEOUT]
    assert len(timeout_audits) == 1
    assert "settlement still ran" in timeout_audits[0][1]
    # the operator digest carries the partial-scan banner (with the pre-cancel partial count):
    assert len(telegrams) == 1
    assert "budget" in telegrams[0] and "settlement ran in full" in telegrams[0]
    assert "3 evaluated" in telegrams[0]


# ── Part A(2): the happy path emits NO timeout artifacts (inverted-logic guard) ───────────────
@pytest.mark.asyncio
async def test_scan_success_no_timeout_audit(monkeypatch):
    audits, telegrams, settle_calls = _patch_job_shell(
        monkeypatch, settled=[("TST", {"outcome": "stop", "realized_r": -1.0})])

    async def quick_scan(today, stats, transitions, entries_fired):
        stats["universe"], stats["written"] = 5, 5

    monkeypatch.setattr(sched, "_consolidation_readiness_scan", quick_scan)

    await sched._consolidation_readiness_job()

    assert settle_calls == [_TODAY]                       # settlement runs on this path too
    assert not [a for a in audits if a[0] == CONSOLIDATION_READINESS_SCAN_TIMEOUT]
    assert len(telegrams) == 1 and "budget" not in telegrams[0]
    assert "Settled today" in telegrams[0]


# ── the scan harness (Part A(3) + Part B wiring) ───────────────────────────────────────────────
def _mk_bars(n=60, v=200_000.0):
    """Rising daily bars with REAL ISO dates (the scan parses anchor_date via fromisoformat)."""
    d0 = date(2026, 4, 1)
    bars = []
    for i in range(n):
        c = 50.0 + 0.5 * i
        bars.append({"date": (d0 + timedelta(days=i)).isoformat(),
                     "o": c, "h": c + 0.2, "l": c - 0.2, "c": c, "v": v})
    return bars


def _cons_for(bars, anchor_idx=55):
    return {
        "anchor_date": bars[anchor_idx]["date"], "state": "coiled", "runup_ratio": 1.25,
        "runup_high": bars[anchor_idx]["c"], "coil_days": 4, "last_close": bars[-1]["c"],
        "today_pct": 0.002, "rmv_5d": 20.0, "rmv_15d": 25.0, "pullback_shape": None,
        "pullback_shapes": None, "fresh_tightening": True, "fresh_2bar_tr_pct": 1.5,
        "atr14_pct": 3.0, "tight_close_streak": 3,
    }


def _patch_scan_harness(monkeypatch, *, n_keys=1, bars=None, sig=None, csig=None,
                        rs=72.0, non_stock=None, mna_result=(False, None)):
    """Patch every collaborator _consolidation_readiness_scan touches; returns the capture dict."""
    import agents.market_intelligence.db as db
    import agents.market_intelligence.ma_filter as ma_filter

    bars = bars or _mk_bars()
    cons = _cons_for(bars)
    cap = {"audits": [], "inserts": [], "upserts": 0, "mna_calls": 0}

    async def fake_audit(event_type, summary, detail=None):
        cap["audits"].append((event_type, summary))

    async def fake_universe(today):
        return []

    async def fake_state_map():
        return {}

    async def fake_9m(since):
        return set()

    async def fake_regime():
        return {"regime": "Bull", "regime_date": _TODAY}

    async def fake_non_stock():
        return non_stock or set()

    async def fake_ohlcv(ticker, today):
        return bars                       # db_rows_to_bars is patched to identity below

    async def fake_rs(d, tickers):
        return {t: {"rs_composite": rs} for t in tickers} if rs is not None else {}

    async def fake_upsert(*a, **kw):
        cap["upserts"] += 1

    async def fake_insert(ticker, anchor_date, **kw):
        cap["inserts"].append((ticker, anchor_date, kw))
        return True

    async def fake_mna(ticker, **kw):
        cap["mna_calls"] += 1
        return mna_result

    monkeypatch.setattr(sched, "log_audit_event", fake_audit)
    monkeypatch.setattr(db, "get_anticipation_universe", fake_universe)
    monkeypatch.setattr(db, "get_consolidation_state_map", fake_state_map)
    monkeypatch.setattr(db, "get_recent_9m_tickers", fake_9m)
    monkeypatch.setattr(db, "get_latest_regime", fake_regime)
    monkeypatch.setattr(db, "get_non_common_stock_tickers", fake_non_stock)
    monkeypatch.setattr(db, "get_anticipation_ohlcv", fake_ohlcv)
    monkeypatch.setattr(db, "get_rs_for_tickers", fake_rs)
    monkeypatch.setattr(db, "upsert_consolidation", fake_upsert)
    monkeypatch.setattr(db, "insert_consolidation_entry_shadow", fake_insert)
    monkeypatch.setattr(ma_filter, "is_likely_ma", fake_mna)
    monkeypatch.setattr(ant, "db_rows_to_bars", lambda rows: rows)
    monkeypatch.setattr(ant, "select_consolidation_keys", lambda u, e: [
        {"ticker": f"TST{i}" if n_keys > 1 else "TST",
         "anchor_date": date(2026, 5, 26), "dvol_med": 5e7} for i in range(n_keys)])
    monkeypatch.setattr(ant, "evaluate_coil_consolidation", lambda b, **kw: (dict(cons), None))
    monkeypatch.setattr(ant, "entry_signal_at", lambda b, i, a: dict(sig) if sig else None)
    monkeypatch.setattr(ant, "confirm_signal_at", lambda b, i, a: dict(csig) if csig else None)
    return cap, bars


def _sig(bars):
    """A realistic anticipate fire record off the constructed bars (entry 79.5, coiled_low 79.2 =
    0.377% risk — sub-1%; structural_low 78.0 = 1.887% — the headline)."""
    return {"entry_date": bars[-1]["date"], "entry_price": 79.5, "signal_n": 3,
            "rmv_5d": 20.0, "rmv_15d": 25.0, "range_pct": 0.02, "vol_ratio": 0.8,
            "vol_sma_3": 180_000.0, "vol_sma_15": 220_000.0, "vol_dryup_ratio": 0.818,
            "stop_kind": "coiled_low", "stop_price": 79.2, "structural_low": 78.0,
            "target_r": 3.0}


def _csig(bars):
    """A confirm fire record (base_low stop 76.5 = 4.375% of the 80.0 break entry)."""
    return {"entry_date": bars[-1]["date"], "entry_price": 80.0, "signal_n": 0,
            "rmv_5d": 20.0, "rmv_15d": 25.0, "range_pct": 0.03, "vol_ratio": 2.1,
            "vol_sma_3": 300_000.0, "vol_sma_15": 220_000.0, "vol_dryup_ratio": 1.364,
            "stop_kind": "base_low", "stop_price": 76.5, "structural_low": 76.5,
            "target_r": 3.0}


# ── Part A(3): the #387 M&A guard is capped per run, fail-open + audited once ─────────────────
@pytest.mark.asyncio
async def test_mna_checks_capped_per_run(monkeypatch):
    cap, _ = _patch_scan_harness(monkeypatch, n_keys=10)
    monkeypatch.setattr(sched, "_CONS_MNA_CHECKS_CAP", 3)

    stats, transitions, entries = {"universe": 0, "written": 0}, [], []
    await sched._consolidation_readiness_scan(_TODAY, stats, transitions, entries)

    assert cap["mna_calls"] == 3                          # capped — not one per candidate
    capped = [a for a in cap["audits"] if a[0] == ANTICIPATION_MNA_CHECK_CAPPED]
    assert len(capped) == 1                               # audited ONCE per run
    assert stats["written"] == 10                         # fail-OPEN: nothing dropped by the cap


# ── Part B §1/§3/§4: Confirm fires; the pack fields are recorded (Anticipate PARKED 2026-08-09 —
#    operator: "stop the shadow ... don't kill the setup"; see scheduler.py's provenance comment
#    at the removed anticipate fire site) ───────────────────────────────────────────────────────
@pytest.mark.asyncio
async def test_scan_records_confirm_arm_only_anticipate_parked(monkeypatch):
    bars = _mk_bars()
    cap, _ = _patch_scan_harness(monkeypatch, bars=bars, sig=_sig(bars), csig=_csig(bars))

    stats, transitions, entries = {"universe": 0, "written": 0}, [], []
    await sched._consolidation_readiness_scan(_TODAY, stats, transitions, entries)

    # ANTICIPATE PARKED: only Confirm reaches the DB, even though a valid anticipate `sig` was
    # available from the harness — the WIRING was turned off, not the underlying signal.
    assert len(cap["inserts"]) == 1
    c = cap["inserts"][0][2]

    # §3 — the Confirm control arm records through the SAME insert, tagged:
    assert c["entry_mode"] == "confirm"
    assert c["stop_kind"] == "base_low" and c["stop_price"] == 76.5
    assert c["coiled_low"] is None                        # anticipate-only geometry
    assert c["sub1pct_reject"] is False                   # 4.375% base_low risk
    # §1/§4 — quality flag + regime pack fields still recorded on whichever arm is live:
    assert c["would_pass_quality"] is True
    assert c["regime_at_entry"] == "Bull"

    # only Confirm surfaces in the fired accumulator now:
    modes = {(t, m) for t, _o, m, _s in entries}
    assert modes == {("TST", "confirm")}


# ── the parked anticipate geometry is still LIVE CODE (un-wired, not deleted) — pin it directly
#    against the helper so a future re-wire has coverage without going through the scan's wiring ──
@pytest.mark.asyncio
async def test_entry_shadow_fire_kwargs_anticipate_geometry_still_correct(monkeypatch):
    import agents.market_intelligence.db as db

    bars = _mk_bars()

    async def fake_rs(d, tickers):
        return {t: {"rs_composite": 72.0} for t in tickers}

    monkeypatch.setattr(db, "get_rs_for_tickers", fake_rs)

    kw = await sched._entry_shadow_fire_kwargs(
        "TST", _sig(bars), bars, mode="anticipate", non_stock=set(),
        regime_label="Bull", today=_TODAY)

    assert kw["entry_mode"] == "anticipate"
    # §2 — structural_low is the HEADLINE stop; the fire-bar low keeps accruing in coiled_low:
    assert kw["stop_kind"] == "structural_low" and kw["stop_price"] == 78.0
    assert kw["coiled_low"] == 79.2
    assert kw["stop_pct"] == pytest.approx((79.5 - 78.0) / 79.5 * 100, rel=1e-4)
    assert kw["sub1pct_reject"] is True                    # coiled_low risk 0.377% < 1%
    # §1 — quality flag + raw components RECORDED (rising bars → above 50SMA; ADV ≈ $15M; RS 72):
    assert kw["would_pass_quality"] is True
    assert kw["is_common_stock"] is True and kw["above_50sma"] is True
    assert kw["rs_at_entry"] == 72.0 and kw["adv20_dollar"] > 5_000_000
    # §4 — regime stamped:
    assert kw["regime_at_entry"] == "Bull"


# ── Part B §1 A/B doctrine: a would-FAIL fire is still RECORDED (flag only, never a filter) ───
@pytest.mark.asyncio
async def test_quality_fail_still_records_the_fire(monkeypatch):
    # Anticipate is PARKED (2026-08-09) — this exercises the A/B doctrine via the live Confirm
    # arm now (csig, not sig); the doctrine itself (never filter the write) is mode-agnostic.
    bars = _mk_bars()
    cap, _ = _patch_scan_harness(monkeypatch, bars=bars, csig=_csig(bars), rs=40.0,
                                 non_stock={"TST"})     # ETF-classified AND RS below floor
    stats, transitions, entries = {"universe": 0, "written": 0}, [], []
    await sched._consolidation_readiness_scan(_TODAY, stats, transitions, entries)

    assert len(cap["inserts"]) == 1                       # the write happened anyway (A/B)
    kw = cap["inserts"][0][2]
    assert kw["would_pass_quality"] is False
    assert kw["is_common_stock"] is False and kw["rs_at_entry"] == 40.0


# ── Part B §3: an M&A-excluded candidate fires NEITHER arm (guard unchanged by the re-wire) ───
@pytest.mark.asyncio
async def test_mna_excluded_candidate_fires_neither_arm(monkeypatch):
    bars = _mk_bars()
    cap, _ = _patch_scan_harness(monkeypatch, bars=bars, sig=_sig(bars), csig=_csig(bars),
                                 mna_result=(True, {"source": "polygon_news"}))
    stats, transitions, entries = {"universe": 0, "written": 0}, [], []
    await sched._consolidation_readiness_scan(_TODAY, stats, transitions, entries)
    assert cap["inserts"] == [] and entries == []
    assert stats["written"] == 0                          # excluded before the upsert, as before


# ── Part B §5: the settlement step threads bound_conflict + realized_r_h12 through ────────────
@pytest.mark.asyncio
async def test_settlement_threads_new_fields_to_writeback(monkeypatch):
    import agents.market_intelligence.db as db

    d0 = date(2026, 6, 1)
    bars = [{"date": (d0 + timedelta(days=i)).isoformat(),
             "o": 100.0, "h": 100.0, "l": 100.0, "c": 100.0, "v": 1e6} for i in range(20)]
    entry_i = 19
    bars[entry_i]["date"] = "2026-06-20"
    # forward path: ONE bar spans target (115) AND stop (95) → pess outcome 'stop', legacy opt
    # said 'capture' → bound_conflict True; realized (harvest, gap-fill at min(stop, open)=95,
    # open=105) = −1.0 at both horizons.
    bars.append({"date": "2026-06-21", "o": 105.0, "h": 116.0, "l": 94.0, "c": 105.0, "v": 1e6})
    for i in range(12):
        bars.append({"date": (date(2026, 6, 22) + timedelta(days=i)).isoformat(),
                     "o": 100.0, "h": 100.0, "l": 99.0, "c": 100.0, "v": 1e6})

    writebacks = []

    async def fake_ripe(cutoff):
        return [{"id": 7, "ticker": "TST", "anchor_date": date(2026, 6, 1),
                 "entry_date": date(2026, 6, 20), "entry_price": 100.0,
                 "stop_price": 95.0, "target_r": 3.0}]

    async def fake_ohlcv(ticker, today):
        return bars

    async def fake_writeback(row_id, **kw):
        writebacks.append((row_id, kw))
        return True

    monkeypatch.setattr(db, "get_settleable_consolidation_entry_shadows", fake_ripe)
    monkeypatch.setattr(db, "get_anticipation_ohlcv", fake_ohlcv)
    monkeypatch.setattr(db, "settle_consolidation_entry_shadow", fake_writeback)
    monkeypatch.setattr(ant, "db_rows_to_bars", lambda rows: rows)

    settled = await sched._run_entry_shadow_settlement(_TODAY)

    assert len(writebacks) == 1
    row_id, kw = writebacks[0]
    assert row_id == 7
    assert kw["outcome"] == "stop"                        # §5: pess-aligned headline
    assert kw["bound_conflict"] is True                   # legacy opt bound disagreed
    assert kw["realized_r"] == pytest.approx(-1.0)
    assert kw["realized_r_h12"] == pytest.approx(-1.0)
    assert settled and settled[0][0] == "TST"
