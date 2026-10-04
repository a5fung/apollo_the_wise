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

Part C — #394 (operator 2026-10-03, "Add it now"): the M&A screen on the COIL BOARD. A stock
pinned by a buyout reads as a perfect coil but cannot break out; the scan runs the SAME decision
the flag scan uses (the REAL ma_filter.is_likely_ma with the day window — only its I/O edges are
faked here) and a screened name's board rows are taken off; a name whose price moves stays on;
an unreadable own-day bar keeps it on and records it.

Everything here is SHADOW/telemetry — the pins assert recording, never any submit path.
"""
import asyncio
import json
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
                        rs=72.0, non_stock=None, mna_result=(False, None), real_mna=False,
                        keys=None):
    """Patch every collaborator _consolidation_readiness_scan touches; returns the capture dict.
    `real_mna=True` leaves ma_filter.is_likely_ma REAL (only its I/O edges are faked by the
    caller) — the #394 tests run the live decision, not a stand-in. `keys` overrides the
    evaluated (ticker, anchor) keys."""
    import agents.market_intelligence.db as db
    import agents.market_intelligence.ma_filter as ma_filter

    bars = bars or _mk_bars()
    cons = _cons_for(bars)
    cap = {"audits": [], "inserts": [], "upserts": 0, "mna_calls": 0, "upsert_tickers": [],
           "marks": [], "audit_details": []}

    async def fake_audit(event_type, summary, detail=None):
        cap["audits"].append((event_type, summary))
        cap["audit_details"].append((event_type, detail))

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
        cap["upsert_tickers"].append(a[0] if a else kw.get("ticker"))

    async def fake_insert(ticker, anchor_date, **kw):
        cap["inserts"].append((ticker, anchor_date, kw))
        return True

    async def fake_mna(ticker, **kw):
        cap["mna_calls"] += 1
        return mna_result

    async def fake_mark(ticker, scan_date):
        cap["marks"].append((ticker, scan_date))
        return 2                          # e.g. NUVL: two board rows taken off

    async def fake_first_log(ticker, detector_tag):
        return True

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
    monkeypatch.setattr(db, "mark_consolidation_mna_screened", fake_mark)
    monkeypatch.setattr(ma_filter, "should_log_mna_filter_fired", fake_first_log)
    if not real_mna:
        monkeypatch.setattr(ma_filter, "is_likely_ma", fake_mna)
    monkeypatch.setattr(ant, "db_rows_to_bars", lambda rows: rows)
    monkeypatch.setattr(ant, "select_consolidation_keys", lambda u, e: list(keys) if keys else [
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
    assert cap["marks"] == [("TST", _TODAY)]              # #394: and its board rows taken off


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


# ══ Part C — #394: the M&A screen on the coil board (operator 2026-10-03, "Add it now") ═══════
# Today's board top 5 was mostly stocks pinned by buyouts (CRNX, NUVL, DV, FBRX, MKTX). The scan
# runs the REAL ma_filter.is_likely_ma here — the headline answer and the DB edges are the only
# fakes — so these pin the live decision (the news nominates, the own-day range decides), not a
# stand-in.
_CRNX_HIT = {"source": "polygon_headline_model", "match_path": "title",
             "matched_keyword": "definitive agreement",
             "title": "Crinetics to be acquired for $XX per share in cash",
             "published_utc": "2026-07-07T12:00:00Z", "publisher": "wire",
             "role": "target", "status": "signed", "consideration": "cash",
             "counterparty": "Acquirer"}


def _bars_with_own_day(range_pct, *, own_day=True):
    """The harness bars with the LAST bar re-dated to the scan date (own_day=True) — or to the day
    before (own_day=False: the scan date's own bar is missing) — and an own-day range of
    `range_pct` % of the close."""
    bars = _mk_bars()
    c = 100.0
    half = c * range_pct / 200.0
    day = _TODAY if own_day else _TODAY - timedelta(days=1)
    bars[-1] = {**bars[-1], "date": day.isoformat(), "o": c, "h": c + half, "l": c - half, "c": c}
    return bars


def _real_mna_edges(monkeypatch, hit):
    """Fake ONLY is_likely_ma's I/O: the Polygon headline answer and the DB dedup / audit writes.
    Returns (filter_rows, headline_calls)."""
    import agents.market_intelligence.db as db
    import agents.market_intelligence.ma_filter as mf

    filter_rows, headline_calls = [], []

    async def fake_scan(ticker, **kw):
        headline_calls.append(ticker)
        return mf.HeadlineScan(dict(hit, ticker=ticker) if hit else None, [], [], 1 if hit else 0)

    async def fake_first_today(event_type, summary_like):
        return True

    async def fake_db_audit(event_type, summary, detail=None):
        filter_rows.append((event_type, summary, detail))

    monkeypatch.setattr(mf, "headline_deal_scan", fake_scan)
    monkeypatch.setattr(mf, "_first_today", fake_first_today)
    monkeypatch.setattr(db, "log_audit_event", fake_db_audit)
    return filter_rows, headline_calls


def _key(ticker, anchor=date(2026, 5, 26)):
    return {"ticker": ticker, "anchor_date": anchor, "dvol_med": 5e7}


async def _scan():
    stats, transitions, entries = {"universe": 0, "written": 0}, [], []
    await sched._consolidation_readiness_scan(_TODAY, stats, transitions, entries)
    return stats, entries


def _rows(cap, event_type):
    return [(s, d) for (e, s), (_e, d) in zip(cap["audits"], cap["audit_details"]) if e == event_type]


@pytest.mark.asyncio
async def test_394_pinned_buyout_is_kept_off_the_coil_board(monkeypatch):
    """CRNX-shaped: the target of a signed all-cash deal, own-day range 0.3% → pinned. Not
    written, no entry fires from it, EVERY board row of the ticker taken off, one fired row in
    #692's convention naming the deal answer and the price reading."""
    from agents.market_intelligence.audit_events import MNA_FILTER_FIRED
    bars = _bars_with_own_day(0.3)
    cap, _ = _patch_scan_harness(monkeypatch, bars=bars, csig=_csig(bars), real_mna=True,
                                 keys=[_key("CRNX")])
    _real_mna_edges(monkeypatch, _CRNX_HIT)

    stats, entries = await _scan()

    assert cap["upserts"] == 0 and stats["written"] == 0       # not written to the board
    assert cap["inserts"] == [] and entries == []               # no entry signal fires from it
    assert cap["marks"] == [("CRNX", _TODAY)]                   # its board rows taken off
    fired = _rows(cap, MNA_FILTER_FIRED)
    assert len(fired) == 1
    summary, detail = fired[0]
    assert summary.startswith("CRNX via polygon_headline_model (anticipation)")
    assert "target/signed/cash" in summary and "day range 0.3% <= 2.0% pinned" in summary
    d = json.loads(detail)
    assert (d["role"], d["status"], d["consideration"]) == ("target", "signed", "cash")
    assert d["why"] == "pinned" and d["detector"] == "anticipation"
    assert d["pin"]["window"] == "day" and d["pin"]["range_pct"] == pytest.approx(0.3)
    assert d["off_board_rows"] == 2


@pytest.mark.asyncio
async def test_394_news_nominated_name_whose_price_moves_stays_on(monkeypatch):
    """The same deal answer, but the stock ranged 3.0% today (> the 2.0% ceiling) → the price
    releases it: written to the board, its entry fires, nothing taken off, and is_likely_ma's
    own `mna_filter_released` row names the free reading."""
    from agents.market_intelligence.audit_events import MNA_FILTER_FIRED
    bars = _bars_with_own_day(3.0)
    cap, _ = _patch_scan_harness(monkeypatch, bars=bars, csig=_csig(bars), real_mna=True,
                                 keys=[_key("DEALX")])
    filter_rows, _calls = _real_mna_edges(monkeypatch, _CRNX_HIT)

    stats, entries = await _scan()

    assert cap["upsert_tickers"] == ["DEALX"] and stats["written"] == 1
    assert [t for t, _o, _m, _s in entries] == ["DEALX"]
    assert cap["marks"] == [] and _rows(cap, MNA_FILTER_FIRED) == []
    released = [s for e, s, _d in filter_rows if e == "mna_filter_released"]
    assert len(released) == 1 and "price is FREE" in released[0] and "day range 3.0%" in released[0]


@pytest.mark.asyncio
async def test_394_non_deal_coil_is_untouched(monkeypatch):
    """No deal in the news → exactly today's path: written, entry fires, no screen rows at all."""
    from agents.market_intelligence.audit_events import (
        ANTICIPATION_MNA_PRICE_UNREAD, MNA_FILTER_FIRED)
    bars = _bars_with_own_day(0.3)            # tight, but no deal: tightness alone never screens
    cap, _ = _patch_scan_harness(monkeypatch, bars=bars, csig=_csig(bars), real_mna=True,
                                 keys=[_key("COIL")])
    filter_rows, calls = _real_mna_edges(monkeypatch, None)

    stats, entries = await _scan()

    assert calls == ["COIL"]                                    # it WAS screened
    assert cap["upsert_tickers"] == ["COIL"] and len(cap["inserts"]) == 1
    assert cap["marks"] == []
    assert _rows(cap, MNA_FILTER_FIRED) == [] and _rows(cap, ANTICIPATION_MNA_PRICE_UNREAD) == []
    assert filter_rows == []


@pytest.mark.asyncio
async def test_394_unreadable_own_day_bar_keeps_it_on_and_records_it(monkeypatch):
    """A nominated name whose scan-date bar is missing: is_likely_ma blocks on the news alone
    (`news_blocked_price_unread`); the coil-board spec keeps it ON the board and records it."""
    from agents.market_intelligence.audit_events import (
        ANTICIPATION_MNA_PRICE_UNREAD, MNA_FILTER_FIRED)
    bars = _bars_with_own_day(0.3, own_day=False)
    cap, _ = _patch_scan_harness(monkeypatch, bars=bars, real_mna=True, keys=[_key("CRNX")])
    _real_mna_edges(monkeypatch, _CRNX_HIT)

    stats, _entries = await _scan()

    assert cap["upsert_tickers"] == ["CRNX"] and stats["written"] == 1   # on the board
    assert cap["marks"] == [] and _rows(cap, MNA_FILTER_FIRED) == []
    unread = _rows(cap, ANTICIPATION_MNA_PRICE_UNREAD)
    assert len(unread) == 1
    assert "no_own_day_bar" in unread[0][0] and "kept ON the coil board" in unread[0][0]
    d = json.loads(unread[0][1])
    assert d["why"] == "news_blocked_price_unread" and d["role"] == "target"


@pytest.mark.asyncio
async def test_394_screen_is_the_live_is_likely_ma_with_the_day_window(monkeypatch):
    """The screen REUSES ma_filter.is_likely_ma — the scan resolves the module's own function
    object at call time (a spy installed there is what runs) — with the flag scan's options and
    a reader that returns the DAY window at DAY_WINDOW_PIN_MAX_PCT."""
    import agents.market_intelligence.ma_filter as mf
    real = mf.is_likely_ma
    assert real.__module__ == "agents.market_intelligence.ma_filter"
    bars = _bars_with_own_day(0.3)
    cap, _ = _patch_scan_harness(monkeypatch, bars=bars, real_mna=True, keys=[_key("CRNX")])
    _real_mna_edges(monkeypatch, _CRNX_HIT)
    seen = []

    async def spy(ticker, **kw):
        seen.append((ticker, kw, await kw["pin_reader"]()))
        return await real(ticker, **kw)

    monkeypatch.setattr(mf, "is_likely_ma", spy)
    await _scan()

    assert len(seen) == 1
    ticker, kw, reading = seen[0]
    assert ticker == "CRNX"
    assert kw["check_polygon"] is True and kw["on_or_before"] == _TODAY
    assert kw["polygon_lookback_days"] == 21
    assert reading.window == "day" and reading.threshold_pct == mf.DAY_WINDOW_PIN_MAX_PCT
    assert reading.readable and reading.pinned
    assert cap["marks"] == [("CRNX", _TODAY)]          # and the real verdict drove the board


@pytest.mark.asyncio
async def test_394_one_check_per_ticker_across_its_board_rows(monkeypatch):
    """NUVL sat on the board twice (two anchors). One screen, one off-board mark, one fired row
    — and neither anchor is written."""
    from agents.market_intelligence.audit_events import MNA_FILTER_FIRED
    bars = _bars_with_own_day(0.3)
    cap, _ = _patch_scan_harness(monkeypatch, bars=bars, real_mna=True,
                                 keys=[_key("NUVL"), _key("NUVL", date(2026, 4, 20))])
    _f, calls = _real_mna_edges(monkeypatch, _CRNX_HIT)

    await _scan()

    assert calls == ["NUVL"]
    assert cap["marks"] == [("NUVL", _TODAY)] and cap["upserts"] == 0
    assert len(_rows(cap, MNA_FILTER_FIRED)) == 1


@pytest.mark.asyncio
async def test_394_the_capped_screen_walks_the_board_top_first(monkeypatch):
    """The check cap tripped on every run in the 07-14..08-24 capture, and the keys come in DB
    order. With one check left, the screen must spend it on the name the board shows FIRST (the
    tightest coil), not on whichever key came first — and the unchecked rest still writes."""
    import agents.market_intelligence.ma_filter as mf
    from agents.market_intelligence.audit_events import ANTICIPATION_MNA_CHECK_CAPPED
    bars = _mk_bars()
    cap, _ = _patch_scan_harness(monkeypatch, bars=bars, keys=[
        _key("LOOSE"), _key("MIDDLE"), _key("TOPCOIL"), _key("AGED")])
    monkeypatch.setattr(sched, "_CONS_MNA_CHECKS_CAP", 1)
    shape = {"LOOSE": ("post_runup", 1, 0.010), "MIDDLE": ("coiled", 2, 0.004),
             "TOPCOIL": ("coiled", 6, 0.002), "AGED": ("aged", 9, 0.001)}

    async def tagged_ohlcv(ticker, today):
        return [dict(b, tk=ticker) for b in bars]

    def per_ticker_cons(b, **kw):
        state, streak, pct = shape[b[0]["tk"]]
        return {**_cons_for(b), "state": state, "tight_close_streak": streak, "today_pct": pct}, None

    screened = []

    async def recorder(ticker, **kw):
        screened.append(ticker)
        return False, None

    import agents.market_intelligence.db as db
    monkeypatch.setattr(db, "get_anticipation_ohlcv", tagged_ohlcv)
    monkeypatch.setattr(ant, "evaluate_coil_consolidation", per_ticker_cons)
    monkeypatch.setattr(mf, "is_likely_ma", recorder)

    stats, _entries = await _scan()

    assert screened == ["TOPCOIL"]                         # the board's first row got the check
    assert cap["upsert_tickers"] == ["TOPCOIL", "MIDDLE", "LOOSE", "AGED"]   # board order
    assert stats["written"] == 4                           # fail-open: the cap drops nothing
    assert len(_rows(cap, ANTICIPATION_MNA_CHECK_CAPPED)) == 1


# ══ #394 the board's DB edge, on REAL SQL ═════════════════════════════════════════════════════
# The production db.py functions run unchanged against an in-memory SQLite table with the same
# columns ($N → ?N; NOW() registered), so these pin what the board actually SHOWS — not the text
# of a query. Columns mirror db.py's CREATE TABLE mi_anticipation_consolidation.
import re as _re
import sqlite3 as _sqlite3

import agents.market_intelligence.db as _db

_REAL_DB = {n: getattr(_db, n) for n in (
    "get_consolidation_board", "get_consolidation_state_map", "upsert_consolidation",
    "mark_consolidation_mna_screened", "clear_consolidation_mna_screened")}
_DATE_COLS = {"anchor_date", "last_eval", "mna_screened_on"}
_DDL = """CREATE TABLE mi_anticipation_consolidation (
    ticker TEXT NOT NULL, anchor_date TEXT NOT NULL, state TEXT NOT NULL, runup_ratio REAL,
    runup_high REAL, coil_days INT, last_close REAL, today_pct REAL, rmv_5d REAL, rmv_15d REAL,
    pullback_shape TEXT, pullback_shapes TEXT, fresh_tightening INT, fresh_2bar_tr_pct REAL,
    atr14_pct REAL, tight_close_streak INT, dvol_med REAL, last_eval TEXT, mna_screened_on TEXT,
    orderliness REAL,
    created_at TEXT DEFAULT CURRENT_TIMESTAMP, updated_at TEXT DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (ticker, anchor_date),
    CHECK (state IN ('coiled','post_runup','aged')))"""


class _SqliteConn:
    def __init__(self, cx):
        self.cx = cx

    @staticmethod
    def _q(sql, args):
        return (_re.sub(r"\$(\d+)", r"?\1", sql),
                [a.isoformat() if isinstance(a, date) else a for a in args])

    async def execute(self, sql, *args):
        cur = self.cx.execute(*self._q(sql, args))
        return f"UPDATE {cur.rowcount}"

    async def fetch(self, sql, *args):
        cur = self.cx.execute(*self._q(sql, args))
        cols = [c[0] for c in cur.description]
        return [{c: (date.fromisoformat(v) if c in _DATE_COLS and v else v)
                 for c, v in zip(cols, row)} for row in cur.fetchall()]


class _SqlitePool:
    def __init__(self):
        self.cx = _sqlite3.connect(":memory:")
        self.cx.create_function("NOW", 0, lambda: "2026-07-14T21:35:00")
        self.cx.execute(_DDL)
        self.conn = _SqliteConn(self.cx)

    def acquire(self):
        pool = self

        class _CM:
            async def __aenter__(self):
                return pool.conn

            async def __aexit__(self, *a):
                return False
        return _CM()

    def seed(self, ticker, anchor, *, last_eval, state="coiled", streak=3, today_pct=0.004,
             screened_on=None, orderliness=None):
        self.cx.execute(
            "INSERT INTO mi_anticipation_consolidation (ticker, anchor_date, state, runup_ratio, "
            "runup_high, coil_days, tight_close_streak, today_pct, dvol_med, last_eval, "
            "mna_screened_on, orderliness) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
            (ticker, str(anchor), state, 1.3, 100.0, 6, streak, today_pct, 5e7, str(last_eval),
             str(screened_on) if screened_on else None, orderliness))

    def row(self, ticker, anchor):
        r = self.cx.execute("SELECT last_eval, mna_screened_on FROM mi_anticipation_consolidation "
                            "WHERE ticker=? AND anchor_date=?", (ticker, str(anchor))).fetchone()
        return r


def _real_board_db(monkeypatch):
    """The real board functions over an in-memory SQLite table (restores any harness fakes)."""
    from unittest.mock import AsyncMock
    pool = _SqlitePool()
    monkeypatch.setattr(_db, "get_pool", AsyncMock(return_value=pool))
    for name, fn in _REAL_DB.items():
        monkeypatch.setattr(_db, name, fn)
    return pool


async def _board_tickers():
    return [r["ticker"] for r in await _db.get_consolidation_board()]


@pytest.mark.asyncio
async def test_394_board_shows_only_coils_the_latest_scan_rewrote(monkeypatch):
    """Today's five buyout-pinned names sat at the top on summer rows the scan stopped rewriting
    (tight-day streaks frozen at 8-12). The board shows only rows the LATEST scan rewrote; the
    old rows stay in the table as history."""
    pool = _real_board_db(monkeypatch)
    latest = date(2026, 10, 2)
    for tk, anchor, last_eval, streak in (
            ("NUVL", date(2026, 6, 9), date(2026, 6, 26), 12),
            ("NUVL", date(2026, 6, 20), date(2026, 6, 30), 10),
            ("CRNX", date(2026, 7, 7), date(2026, 7, 20), 11),
            ("FBRX", date(2026, 7, 27), date(2026, 8, 10), 9),
            ("DV", date(2026, 8, 7), date(2026, 8, 25), 9),
            ("MKTX", date(2026, 9, 1), date(2026, 9, 15), 8)):
        pool.seed(tk, anchor, last_eval=last_eval, streak=streak)
    pool.seed("REAL", date(2026, 9, 22), last_eval=latest, streak=3)
    pool.seed("RUNUP", date(2026, 9, 25), last_eval=latest, state="post_runup", streak=0)
    pool.seed("OLD", date(2026, 7, 1), last_eval=latest, state="aged", streak=7)
    pool.seed("SCRND", date(2026, 9, 20), last_eval=latest, streak=6, screened_on=latest)

    assert await _board_tickers() == ["REAL", "RUNUP"]
    n_rows = pool.cx.execute("SELECT count(*) FROM mi_anticipation_consolidation").fetchone()[0]
    assert n_rows == 10                                          # history kept

    # a row the latest scan REWRITES is shown again (CRNX re-evaluated as a coil on 10-02)
    await _db.upsert_consolidation(
        "CRNX", date(2026, 7, 7), state="coiled", runup_ratio=1.3, runup_high=10.0, coil_days=5,
        last_close=10.0, today_pct=0.003, rmv_5d=20.0, rmv_15d=25.0, pullback_shape=None,
        pullback_shapes=None, fresh_tightening=True, fresh_2bar_tr_pct=1.0, atr14_pct=3.0,
        tight_close_streak=4, dvol_med=5e7, last_eval=latest)
    assert await _board_tickers() == ["CRNX", "REAL", "RUNUP"]


@pytest.mark.asyncio
async def test_394_mark_takes_every_row_off_and_the_price_release_clear_brings_it_back(monkeypatch):
    pool = _real_board_db(monkeypatch)
    today = date(2026, 10, 2)
    pool.seed("NUVL", date(2026, 9, 10), last_eval=today, streak=5)
    pool.seed("NUVL", date(2026, 9, 1), last_eval=today, streak=4)
    pool.seed("NUVL", date(2026, 6, 9), last_eval=today, state="aged")
    assert await _board_tickers() == ["NUVL", "NUVL"]

    assert await _db.mark_consolidation_mna_screened("NUVL", today) == 2   # aged row untouched
    assert await _board_tickers() == []
    # a second screen keeps the FIRST screen date (the day the hold began)
    await _db.mark_consolidation_mna_screened("NUVL", today + timedelta(days=3))
    assert pool.row("NUVL", date(2026, 9, 10))[1] == today.isoformat()
    state = await _db.get_consolidation_state_map()
    assert state[("NUVL", date(2026, 9, 10))]["mna_screened_on"] == today

    # a normal write never clears the mark (only the price release does)
    await _db.upsert_consolidation(
        "NUVL", date(2026, 9, 10), state="coiled", runup_ratio=1.3, runup_high=10.0, coil_days=5,
        last_close=10.0, today_pct=0.003, rmv_5d=20.0, rmv_15d=25.0, pullback_shape=None,
        pullback_shapes=None, fresh_tightening=True, fresh_2bar_tr_pct=1.0, atr14_pct=3.0,
        tight_close_streak=5, dvol_med=5e7, last_eval=today)
    assert await _board_tickers() == []

    assert await _db.clear_consolidation_mna_screened("NUVL") == 2
    assert await _board_tickers() == ["NUVL", "NUVL"]


# ── #394 fix 2: THE PRICE HOLDS A SCREENED NAME past the 21-day news lookback ────────────────
_HELD_ANCHOR = date(2026, 5, 26)          # == the harness coil's anchor (bars[55])


def _seed_held(pool):
    """HELD: screened off 25 days before the scan (its deal headline is past the 21-day news
    lookback, so the news no longer nominates it); two rows, both marked. FREE: an unscreened
    coil carried from yesterday."""
    yday = _TODAY - timedelta(days=1)
    screened = _TODAY - timedelta(days=25)
    pool.seed("HELD", _HELD_ANCHOR, last_eval=yday, streak=9, screened_on=screened)
    pool.seed("HELD", date(2026, 5, 1), last_eval=yday, streak=7, screened_on=screened)
    pool.seed("FREE", _HELD_ANCHOR, last_eval=yday, streak=3)
    return screened


async def _scan_held(monkeypatch, range_pct, *, own_day=True):
    bars = _bars_with_own_day(range_pct, own_day=own_day)
    cap, _ = _patch_scan_harness(monkeypatch, bars=bars, csig=_csig(bars), real_mna=True,
                                 keys=[_key("HELD"), _key("HELD", date(2026, 5, 1)), _key("FREE")])
    pool = _real_board_db(monkeypatch)
    screened = _seed_held(pool)
    _f, calls = _real_mna_edges(monkeypatch, None)       # the news no longer nominates HELD
    stats, entries = await _scan()
    return cap, pool, screened, calls, entries


@pytest.mark.asyncio
async def test_394_screened_name_stays_off_at_day_25_while_its_price_is_pinned(monkeypatch):
    from agents.market_intelligence.audit_events import ANTICIPATION_MNA_PIN_HELD
    cap, pool, screened, calls, entries = await _scan_held(monkeypatch, 0.3)

    assert "HELD" in calls                                # the news was asked — and passed it
    assert pool.row("HELD", _HELD_ANCHOR) == ((_TODAY - timedelta(days=1)).isoformat(),
                                               screened.isoformat())   # not written, still marked
    assert [t for t, *_ in entries] == ["FREE"]           # no entry fires from HELD
    assert await _board_tickers() == ["FREE"]             # FREE untouched, HELD off
    held = _rows(cap, ANTICIPATION_MNA_PIN_HELD)
    assert len(held) == 1                                 # one row for its two board rows
    assert "day range 0.3% <= 2.0%" in held[0][0] and screened.isoformat() in held[0][0]


@pytest.mark.asyncio
async def test_394_screened_name_returns_when_its_price_moves(monkeypatch):
    from agents.market_intelligence.audit_events import (
        ANTICIPATION_MNA_PIN_HELD, ANTICIPATION_MNA_PIN_RELEASED)
    cap, pool, _screened, _calls, entries = await _scan_held(monkeypatch, 3.0)

    assert pool.row("HELD", _HELD_ANCHOR) == (_TODAY.isoformat(), None)   # written, unmarked
    assert pool.row("HELD", date(2026, 5, 1))[1] is None   # the old anchor's mark cleared too
    # (HELD's two keys fire twice through the harness's fake insert; the real open-dedup index
    # keeps one row)
    assert {t for t, *_ in entries} == {"FREE", "HELD"}
    assert sorted(await _board_tickers()) == ["FREE", "HELD"]
    released = _rows(cap, ANTICIPATION_MNA_PIN_RELEASED)
    assert len(released) == 1 and "day range 3.0% > 2.0%" in released[0][0]
    assert _rows(cap, ANTICIPATION_MNA_PIN_HELD) == []


@pytest.mark.asyncio
async def test_394_unreadable_price_does_not_release_a_held_name(monkeypatch):
    """A holiday run (no own-day bar) must not release every held buyout: unreadable changes
    nothing — HELD stays off, the unscreened FREE is written as always."""
    from agents.market_intelligence.audit_events import ANTICIPATION_MNA_PIN_HELD
    cap, pool, screened, _calls, _entries = await _scan_held(monkeypatch, 0.3, own_day=False)

    assert pool.row("HELD", _HELD_ANCHOR)[1] == screened.isoformat()
    assert await _board_tickers() == ["FREE"]
    held = _rows(cap, ANTICIPATION_MNA_PIN_HELD)
    assert len(held) == 1 and "unreadable (no_own_day_bar)" in held[0][0]


# ══ Part D — #394 C2 Phase 1: the ORDERLINESS score rides the scan onto the board, DISPLAY ONLY ═
# Operator ruling 2026-10-03 on the C1 tables: "Sign" — keep the 50% cap, keep the board order, no
# orderliness demotion. So the score is written on every coil row and shown on the /anticipation
# line, and these tests pin that it can change NOTHING else: not which rows show, not their order,
# not what the scan admits, writes or fires. The pure definition / admission tests are in
# tests/test_anticipation_coil_finder.py (the #394 C2 section) and the probe-identity pin in
# tests/test_394_coil_tune_probe.py; this half runs the real scan, the real upsert + board SQL
# (in-memory SQLite) and the real /anticipation handler.
_REAL_ANT = {n: getattr(ant, n) for n in ("db_rows_to_bars", "evaluate_coil_consolidation")}


def _raw_coil_rows(*, gappy_days=(), null_open_dip=False, dip_open_as_close=False):
    """60 raw mi_daily_closes rows: 35 flat bars at 100, a +30% leg (103..130, peak idx 44), then 15
    flat coil bars at 125. Every open = the prior close except `gappy_days` (open +1.0% over the flat
    125). `null_open_dip` puts a -5% close dip on idx 50 with a NULL open (the live loader's close
    substitute would read it as a 5% overnight gap); `dip_open_as_close` gives that day a real open
    equal to the dipped close instead (a genuine 5% gap — the contrast case)."""
    closes = [100.0] * 35 + [100.0 + 3.0 * (k + 1) for k in range(10)] + [125.0] * 15
    if null_open_dip or dip_open_as_close:
        closes[50] = 118.75
    opens = [closes[0]] + closes[:-1]
    for d in gappy_days:
        opens[d] = 125.0 * 1.01
    if dip_open_as_close:
        opens[50] = closes[50]
    d0 = date(2026, 4, 1)
    rows = [{"trade_date": d0 + timedelta(days=i), "open_price": opens[i], "high_price": c * 1.01,
             "low_price": c * 0.99, "close": c, "volume": 1_000_000}
            for i, c in enumerate(closes)]
    if null_open_dip:
        rows[50]["open_price"] = None
    return rows


async def _scan_real_coil(monkeypatch, raw, ticker="COIL"):
    """The REAL scan: real evaluate_coil_consolidation + real db_rows_to_bars over raw rows, real
    upsert + board over SQLite (only the I/O edges the harness always fakes stay faked)."""
    import agents.market_intelligence.db as db
    cap, _ = _patch_scan_harness(monkeypatch, keys=[_key(ticker)])
    monkeypatch.setattr(ant, "db_rows_to_bars", _REAL_ANT["db_rows_to_bars"])
    monkeypatch.setattr(ant, "evaluate_coil_consolidation", _REAL_ANT["evaluate_coil_consolidation"])

    async def raw_ohlcv(tk, today):
        return raw

    monkeypatch.setattr(db, "get_anticipation_ohlcv", raw_ohlcv)
    pool = _real_board_db(monkeypatch)
    stats, entries = await _scan()
    return cap, pool, stats, entries


@pytest.mark.asyncio
async def test_394_the_scan_stores_the_score_and_the_board_line_shows_it_in_plain_words(monkeypatch):
    """Raw rows -> real coil-finder -> real upsert -> real board SELECT -> real /anticipation
    handler. Three of the 15 coil days open +1.0% over a flat 125 close; ATR14% is 2.0%, so the
    P95 overnight gap (1.0%) is half a normal day's range: 0.5."""
    from agents.market_intelligence.agent import MarketIntelligenceAgent
    from shared.models import AgentRequest
    import agents.market_intelligence.db as db

    raw = _raw_coil_rows(gappy_days=(50, 55, 58))
    cap, pool, stats, _entries = await _scan_real_coil(monkeypatch, raw)

    assert stats["written"] == 1
    stored = pool.cx.execute("SELECT orderliness FROM mi_anticipation_consolidation "
                             "WHERE ticker='COIL'").fetchone()[0]
    assert stored == pytest.approx(0.5)
    board = await _db.get_consolidation_board()
    assert [r["ticker"] for r in board] == ["COIL"] and board[0]["orderliness"] == pytest.approx(0.5)

    # the operator surface: the real handler over that board
    async def no_rows(*a, **kw):
        return []

    async def no_summary():
        return {"settled_n": 0, "open_n": 0}

    async def no_open():
        return set()

    monkeypatch.setattr(db, "get_consolidation_entry_shadows", no_rows)
    monkeypatch.setattr(db, "get_consolidation_entry_shadow_summary", no_summary)
    monkeypatch.setattr(db, "get_open_shadow_tickers", no_open)
    res = await MarketIntelligenceAgent()._handle_anticipation_query(
        AgentRequest(task="/anticipation", user_id=1, conversation_id="t"))
    body = res.result if hasattr(res, "result") else res["result"]
    line = next(ln for ln in body.splitlines() if "`COIL " in ln)
    assert line.startswith("  `COIL ` +30% · coiling 15d")
    assert line.endswith("overnight gaps 0.5× daily range")


@pytest.mark.asyncio
async def test_394_a_null_open_day_is_dropped_by_the_live_scan_not_read_as_a_gap(monkeypatch):
    """The live loader substitutes the close for a NULL open; unflagged, a -5% close dip would read
    as a 5% overnight gap. Same dip, NULL open -> dropped -> a calm coil (0.0); same dip with a REAL
    open at the dipped close -> a genuine 5% gap, scored."""
    _cap, pool_a, _s, _e = await _scan_real_coil(monkeypatch, _raw_coil_rows(null_open_dip=True))
    nulled = pool_a.cx.execute("SELECT orderliness FROM mi_anticipation_consolidation").fetchone()[0]
    assert nulled == pytest.approx(0.0)

    _cap, pool_b, _s, _e = await _scan_real_coil(monkeypatch, _raw_coil_rows(dip_open_as_close=True))
    real_gap = pool_b.cx.execute("SELECT orderliness FROM mi_anticipation_consolidation").fetchone()[0]
    assert real_gap is not None and real_gap > 0.1


# ranking / admission: the score is wildly ANTI-correlated with the board here (the tightest coil is
# the gappiest) — if anything ever sorted or gated on it, the board below would change.
_D_SHAPES = {"LOOSE": ("post_runup", 1, 0.010), "MIDDLE": ("coiled", 2, 0.004),
             "TIE": ("coiled", 2, 0.005), "TOPCOIL": ("coiled", 6, 0.002),
             "AGED": ("aged", 9, 0.001)}
_D_SCORES = {"TOPCOIL": 2.4, "MIDDLE": 1.1, "TIE": 0.05, "LOOSE": 0.7, "AGED": 0.0}


async def _scan_shapes(monkeypatch, *, with_score):
    import agents.market_intelligence.db as db
    bars = _mk_bars()
    cap, _ = _patch_scan_harness(monkeypatch, bars=bars, csig=_csig(bars), keys=[
        _key(t) for t in ("LOOSE", "MIDDLE", "TIE", "TOPCOIL", "AGED")])

    async def tagged_ohlcv(ticker, today):
        return [dict(b, tk=ticker) for b in bars]

    def per_ticker_cons(b, **kw):
        tk = b[0]["tk"]
        state, streak, pct = _D_SHAPES[tk]
        cons = {**_cons_for(b), "state": state, "tight_close_streak": streak, "today_pct": pct}
        if with_score:
            cons["orderliness"] = _D_SCORES[tk]
        return cons, None

    monkeypatch.setattr(db, "get_anticipation_ohlcv", tagged_ohlcv)
    monkeypatch.setattr(ant, "evaluate_coil_consolidation", per_ticker_cons)
    pool = _real_board_db(monkeypatch)
    stats, entries = await _scan()
    written = [r[0] for r in pool.cx.execute("SELECT ticker FROM mi_anticipation_consolidation "
                                             "ORDER BY rowid")]
    scores = dict(pool.cx.execute("SELECT ticker, orderliness FROM mi_anticipation_consolidation"))
    return {"stats": stats, "entries": [(t, o, m) for t, o, m, _s in entries], "written": written,
            "board": await _board_tickers(), "scores": scores, "mna_calls": cap["mna_calls"],
            "inserts": [(t, kw["entry_mode"]) for t, _a, kw in cap["inserts"]]}


@pytest.mark.asyncio
async def test_394_the_score_changes_no_ranking_admission_or_entry(monkeypatch):
    with_score = await _scan_shapes(monkeypatch, with_score=True)
    without = await _scan_shapes(monkeypatch, with_score=False)

    # identical in every way the operator can see or the money path can feel ...
    for key in ("stats", "entries", "written", "board", "mna_calls", "inserts"):
        assert with_score[key] == without[key], key
    assert with_score["written"] == ["TOPCOIL", "MIDDLE", "TIE", "LOOSE", "AGED"]   # scan = board order
    assert with_score["board"] == ["TOPCOIL", "MIDDLE", "TIE", "LOOSE"]              # streak desc, today_pct asc; aged hidden
    assert with_score["stats"]["written"] == 5                                      # every candidate admitted
    assert with_score["inserts"], "the harness's Confirm fires must have run on both sides"
    # ... except the stored column itself
    assert with_score["scores"] == _D_SCORES
    assert set(without["scores"].values()) == {None}


@pytest.mark.asyncio
async def test_394_board_read_order_and_set_are_identical_with_and_without_scores(monkeypatch):
    """The board SELECT alone, on seeded rows: the same rows with wildly different scores (and with
    none) come back in the same order — the score is selected, never ordered or filtered on."""
    latest = date(2026, 10, 2)
    rows = [("A", 6, 0.002, "coiled", 0.1), ("B", 6, 0.004, "coiled", 2.3), ("C", 3, 0.001, "coiled", 0.9),
            ("D", 3, 0.009, "post_runup", 5.0), ("E", 0, 0.003, "post_runup", None),
            ("F", 9, 0.001, "aged", 0.0)]
    boards = {}
    for label, use_scores in (("with", True), ("rev", True), ("none", False)):
        pool = _real_board_db(monkeypatch)
        for i, (tk, streak, pct, state, score) in enumerate(rows):
            if label == "rev":
                score = None if score is None else 10.0 - score          # the opposite ranking
            pool.seed(tk, date(2026, 9, 1) + timedelta(days=i), last_eval=latest, state=state,
                      streak=streak, today_pct=pct, orderliness=score if use_scores else None)
        boards[label] = await _db.get_consolidation_board()
    order = {k: [r["ticker"] for r in v] for k, v in boards.items()}
    assert order["with"] == order["rev"] == order["none"] == ["A", "B", "C", "D", "E"]
    assert [r["orderliness"] for r in boards["with"]] == [0.1, 2.3, 0.9, 5.0, None]   # carried, NULL kept
    assert all(r["orderliness"] is None for r in boards["none"])


@pytest.mark.asyncio
async def test_394_a_first_seen_pinned_coil_gets_a_marked_row_so_the_price_hold_keeps_it_off(
        monkeypatch):
    """2026-10-03 review: a pinned buyout screened the FIRST time it appears had no row for the
    mark to sit on (the mark is an UPDATE), so once its headline aged out of the 21-day news
    lookback it came back with its full streak. Night 1 now writes the row and marks it (hidden
    from the board); a later night with no news is decided by the own-day price — still pinned,
    still off."""
    bars = _bars_with_own_day(0.3)
    _patch_scan_harness(monkeypatch, bars=bars, csig=_csig(bars), real_mna=True,
                        keys=[_key("NUVL")])
    pool = _real_board_db(monkeypatch)
    _real_mna_edges(monkeypatch, _CRNX_HIT)

    await _scan()                                          # night 1: the news nominates NUVL
    assert pool.row("NUVL", _HELD_ANCHOR) == (_TODAY.isoformat(), _TODAY.isoformat())
    assert await _board_tickers() == []

    _real_mna_edges(monkeypatch, None)                     # the headline has aged out
    _, entries = await _scan()
    assert await _board_tickers() == [] and entries == []  # held off by its pinned price
    assert pool.row("NUVL", _HELD_ANCHOR)[1] == _TODAY.isoformat()
