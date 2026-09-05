"""#321 write-back + in-window recovery (2026-09-04) — the "fix YoY once and for all" card.

Three failure modes were found behind the 19 missing-YoY cases of the 30d review
(data_gated_reviews.yaml::yoy_missing_data_quality_investigation). This file locks the two
that ship here:

  (a) NSSC 8/24 — a correct answer computed at 07:25 was re-derived "missing" at 09:30:07 and
      DOWNGRADED, because the recovery was never written anywhere a later tick could see.
      Now: persist_yoy_recovery -> mi_ep_catalyst_metrics.yoy_recovered_json, read back by
      lookup_cached_metrics under `_yoy_recovered`, honoured FIRST in the #321 block (a dict
      read, so the 9:30-9:45 latency guard for the FETCH does not apply).
  (b) BE 8/12 — first seen inside the ORB window, where the fetch is off by design. Now: a
      DETACHED background fetch behind `live_yoy_recovery_inwindow` (default OFF — the
      operator's flip), whose write-back the next tick reads through (a).

Plus the DG date-sanity guard in compute_yoy_from_prior_year (fiscal-label convention mismatch
-> a row TWO years back; fail-closed to None, never a wrong number).

The third mode — the beat+guidance carve-out pre-empting the recovery for 12/19 — is a
scoring-ORDER change awaiting the operator's sign-off; nothing here touches that order.
"""
import asyncio
import json
import re
from datetime import date
from pathlib import Path

import pytest

_EP_SRC = (Path(__file__).resolve().parent.parent
           / "agents" / "market_intelligence" / "ep_detector.py").read_text()
_BLOCK = _EP_SRC[_EP_SRC.find("# #321 LIVE rescue"):]
_BLOCK = _BLOCK[:_BLOCK.find("# Extraction died and we deliberately kept the grade")]


def _run(coro):
    return asyncio.run(coro)


# ── (a) source pins on the #321 block ─────────────────────────────────────────────────────

def test_persisted_answer_is_read_before_any_fetch():
    """The write-back must be consulted BEFORE compute_yoy_from_prior_year — that is the whole
    NSSC fix: an answer already in hand is never re-derived."""
    read = _BLOCK.find("_persisted_yoy_recovery(_extracted)")
    fetch = _BLOCK.find("compute_yoy_from_prior_year(")
    assert read != -1 and fetch != -1
    assert read < fetch, "the persisted read must precede the fetch in the #321 block"


def test_persisted_read_is_not_gated_by_the_orb_window():
    """The top-level condition of the block carries the toggle only; `_in_orb_cutoff` gates the
    FETCH branch (latency), never the dict read. Pre-fix the window sat in the top-level `if`
    and that is what threw NSSC's answer away."""
    cond = re.search(
        r'if \(_downgrade_reason == "q_rev_yoy_missing_no_prior_year_comparable"\s*'
        r'and await get_runtime_toggle\("live_yoy_recovery", "LIVE_YOY_RECOVERY"\)\):',
        _BLOCK)
    assert cond, "the #321 top-level condition changed shape (window guard crept back in?)"
    fetch_guard = _BLOCK.find("if _rec is None and not _in_orb_cutoff:")
    assert fetch_guard != -1 and fetch_guard > cond.end()


def test_writeback_happens_before_the_floor_decision():
    """A real BELOW-floor number must survive too — else the next tick re-derives 'missing' and
    the `_recovered` reason (the real number) is lost. So the persist sits before the compare."""
    persist = _BLOCK.find("await persist_yoy_recovery(ticker, today, _rec)")
    floor = _BLOCK.find("_ryoy >= EARNINGS_REVENUE_GATE_MIN_YOY")
    assert persist != -1 and floor != -1
    assert persist < floor


def test_fetch_passes_alert_date_for_the_dg_guard():
    assert "alert_date=today" in _BLOCK


def test_apply_logic_unchanged_same_audit_same_floor():
    """Behaviour identical except that the number survives: same audit event, same floor, same
    `_recovered` reason label."""
    assert 'catalyst_yoy_recovered_live' in _BLOCK
    assert 'pct_recovered"' in _BLOCK
    assert "timeout=4" in _BLOCK, "the out-of-window fetch keeps its 4s cap"


# ── (b) in-window background fetch: toggle-gated, default OFF, never awaited ───────────────

def test_inwindow_background_is_operator_toggle_default_off():
    assert ('get_runtime_toggle(\n                        "live_yoy_recovery_inwindow", '
            '"LIVE_YOY_RECOVERY_INWINDOW", default=False)') in _BLOCK


def test_inwindow_fetch_is_never_awaited_on_the_scan_path():
    """The 6/28 latency guard's guarantee: nothing in the window waits on yfinance."""
    spawn = _BLOCK.find("_spawn_yoy_recovery_background(")
    assert spawn != -1
    before = _BLOCK[max(0, spawn - 40):spawn]
    assert "await" not in before, "the background spawn must not be awaited"
    # and the spawn sits inside the in-window branch, i.e. after the out-of-window fetch branch
    assert spawn > _BLOCK.find("if _rec is None and not _in_orb_cutoff:")


def test_background_spawn_dedups_per_ticker_per_day_and_needs_inputs(monkeypatch):
    from agents.market_intelligence import ep_detector as ep

    monkeypatch.setattr(ep, "_yoy_bg_started", set())
    monkeypatch.setattr(ep, "_yoy_bg_started_date", None)
    monkeypatch.setattr(ep, "_yoy_bg_tasks", set())
    started = []

    async def _fake_compute(ticker, fp, val, alert_date=None):
        started.append((ticker, alert_date))
        return None

    async def _drive():
        from agents.market_intelligence import fundamentals as fm
        monkeypatch.setattr(fm, "compute_yoy_from_prior_year", _fake_compute)
        d = date(2026, 8, 12)
        assert ep._spawn_yoy_recovery_background("BE", d, None, 1.0) is False      # no period
        assert ep._spawn_yoy_recovery_background("BE", d, "Q2 2026", None) is False  # no value
        assert ep._spawn_yoy_recovery_background("BE", d, "Q2 2026", 1.07e9) is True
        assert ep._spawn_yoy_recovery_background("BE", d, "Q2 2026", 1.07e9) is False  # same day: dedup
        assert ep._spawn_yoy_recovery_background("BE", date(2026, 8, 13), "Q2 2026", 1.07e9) is True  # new day
        await asyncio.gather(*list(ep._yoy_bg_tasks))

    _run(_drive())
    assert started == [("BE", date(2026, 8, 12)), ("BE", date(2026, 8, 13))]
    assert not ep._yoy_bg_tasks, "done-callback must drop the strong ref"


def test_background_task_writes_back_on_a_result(monkeypatch):
    from agents.market_intelligence import ep_detector as ep
    from agents.market_intelligence import fundamentals as fm
    from agents.market_intelligence import catalyst_metrics_extractor as cme

    monkeypatch.setattr(ep, "_yoy_bg_started", set())
    monkeypatch.setattr(ep, "_yoy_bg_started_date", None)
    monkeypatch.setattr(ep, "_yoy_bg_tasks", set())
    writes = []

    async def _fake_compute(ticker, fp, val, alert_date=None):
        return {"yoy_pct": 166.7, "prior_period": "Q2'25", "prior_revenue_m": 401.0,
                "source": "yfinance_prior_year"}

    async def _fake_persist(ticker, alert_date, rec):
        writes.append((ticker, alert_date, rec["yoy_pct"]))
        return True

    async def _drive():
        monkeypatch.setattr(fm, "compute_yoy_from_prior_year", _fake_compute)
        monkeypatch.setattr(cme, "persist_yoy_recovery", _fake_persist)
        assert ep._spawn_yoy_recovery_background("BE", date(2026, 8, 12), "Q2 2026", 1.07e9)
        await asyncio.gather(*list(ep._yoy_bg_tasks))

    _run(_drive())
    assert writes == [("BE", date(2026, 8, 12), 166.7)]


# ── the persisted-read helper ─────────────────────────────────────────────────────────────

def test_persisted_yoy_recovery_shape_checked():
    from agents.market_intelligence.ep_detector import _persisted_yoy_recovery
    good = {"yoy_pct": 10.1, "prior_period": "Q4'25"}
    assert _persisted_yoy_recovery({"_yoy_recovered": good}) == good
    assert _persisted_yoy_recovery({}) is None
    assert _persisted_yoy_recovery(None) is None
    assert _persisted_yoy_recovery({"_yoy_recovered": {"prior_period": "Q4'25"}}) is None
    assert _persisted_yoy_recovery({"_yoy_recovered": "10.1"}) is None


# ── lookup_cached_metrics carries the write-back; persist_yoy_recovery is narrow + loud ────

class _FakeConn:
    def __init__(self, row, executed):
        self._row = row
        self._executed = executed
        self.status = "UPDATE 1"

    async def fetchrow(self, *a, **k):
        return self._row

    async def execute(self, sql, *params):
        self._executed.append((sql, params))
        return self.status


class _FakeAcquire:
    def __init__(self, conn):
        self._conn = conn

    async def __aenter__(self):
        return self._conn

    async def __aexit__(self, *a):
        return False


class _FakePool:
    def __init__(self, row, executed, status="UPDATE 1"):
        self._conn = _FakeConn(row, executed)
        self._conn.status = status

    def acquire(self):
        return _FakeAcquire(self._conn)


def _wire(monkeypatch, row, status="UPDATE 1"):
    from agents.market_intelligence import catalyst_metrics_extractor as cme
    executed = []

    async def _pool():
        return _FakePool(row, executed, status)

    monkeypatch.setattr(cme, "get_pool", _pool)
    return cme, executed


def test_lookup_merges_the_writeback_under_the_annotation_key(monkeypatch):
    raw = {"extraction_quality": "medium", "fiscal_period": "Q4 FY2026",
           "q_revenue_usd": {"value": 55_809_000, "yoy_pct": None}}
    rec = {"yoy_pct": 10.1, "prior_period": "Q4'25", "prior_revenue_m": 50.7,
           "source": "yfinance_prior_year"}
    cme, _ = _wire(monkeypatch, {"q_revenue_yoy_pct": None, "extraction_quality": "medium",
                                 "raw_json": dict(raw), "yoy_recovered_json": rec})
    out = _run(cme.lookup_cached_metrics("NSSC", date(2026, 8, 24)))
    assert out["_yoy_recovered"] == rec
    # the extraction itself is untouched — the rubric's input stays exactly what the LLM said
    assert out["q_revenue_usd"]["yoy_pct"] is None
    assert cme.get_q_revenue_yoy_pct(out) is None


def test_lookup_accepts_a_string_encoded_writeback(monkeypatch):
    rec = {"yoy_pct": 24.7, "prior_period": "Q2'25"}
    cme, _ = _wire(monkeypatch, {"q_revenue_yoy_pct": None, "extraction_quality": "medium",
                                 "raw_json": {"extraction_quality": "medium"},
                                 "yoy_recovered_json": json.dumps(rec)})
    out = _run(cme.lookup_cached_metrics("GPRK", date(2026, 8, 31)))
    assert out["_yoy_recovered"] == rec


def test_lookup_without_a_writeback_has_no_annotation(monkeypatch):
    cme, _ = _wire(monkeypatch, {"q_revenue_yoy_pct": None, "extraction_quality": "medium",
                                 "raw_json": {"extraction_quality": "medium"},
                                 "yoy_recovered_json": None})
    out = _run(cme.lookup_cached_metrics("X", date(2026, 8, 24)))
    assert "_yoy_recovered" not in out


def test_lookup_still_refuses_a_failure_row_even_with_a_writeback(monkeypatch):
    """#543 DoD stays ahead of the merge: a transport-failure row is never served as cache."""
    cme, _ = _wire(monkeypatch, {"q_revenue_yoy_pct": None, "extraction_quality": "low",
                                 "raw_json": {"extraction_quality": "low",
                                              "extraction_error": "extraction_call_failed"},
                                 "yoy_recovered_json": {"yoy_pct": 5.0}})
    assert _run(cme.lookup_cached_metrics("X", date(2026, 8, 24))) is None


def test_persist_writes_the_registered_statement_with_a_jsonb_param(monkeypatch):
    cme, executed = _wire(monkeypatch, None)
    rec = {"yoy_pct": 10.1, "prior_period": "Q4'25"}
    assert _run(cme.persist_yoy_recovery("NSSC", date(2026, 8, 24), rec)) is True
    assert len(executed) == 1
    sql, params = executed[0]
    assert sql is cme.YOY_RECOVERY_WRITEBACK_SQL
    assert params[0] == "NSSC" and params[1] == date(2026, 8, 24)
    # the DICT goes to the pool's JSONB codec — a pre-dumped string would double-encode
    assert params[2] == rec and isinstance(params[2], dict)


def test_persist_is_loud_and_false_when_no_row_matched(monkeypatch):
    cme, _ = _wire(monkeypatch, None, status="UPDATE 0")
    assert _run(cme.persist_yoy_recovery("X", date(2026, 8, 24), {"yoy_pct": 1.0})) is False


def test_persist_never_raises(monkeypatch):
    from agents.market_intelligence import catalyst_metrics_extractor as cme

    async def _boom():
        raise RuntimeError("db down")

    monkeypatch.setattr(cme, "get_pool", _boom)
    assert _run(cme.persist_yoy_recovery("X", date(2026, 8, 24), {"yoy_pct": 1.0})) is False


def test_writeback_statement_is_registered_in_the_deploy_gate():
    """The gate's own rule: register a writer when you add one — prepared from the REAL constant."""
    from scripts.preflight_db_updates import SHADOW_WRITER_STATEMENTS
    from agents.market_intelligence.catalyst_metrics_extractor import YOY_RECOVERY_WRITEBACK_SQL
    assert any(sql is YOY_RECOVERY_WRITEBACK_SQL for _, sql in SHADOW_WRITER_STATEMENTS)


def test_schema_adds_the_column_at_boot():
    src = (Path(__file__).resolve().parent.parent
           / "agents" / "market_intelligence" / "db.py").read_text()
    assert re.search(r"ALTER TABLE mi_ep_catalyst_metrics\s+ADD COLUMN IF NOT EXISTS yoy_recovered_json JSONB", src)


# ── the DG date-sanity guard ──────────────────────────────────────────────────────────────

def _fake_gf(rows, ends):
    async def _gf(ticker):
        return {"quarterly_revenue": rows, "quarterly_period_ends": ends}
    return _gf


@pytest.mark.asyncio
async def test_dg_shape_start_year_fiscal_naming_is_rejected_not_fabricated(monkeypatch):
    """DG names its fiscal year by its STARTING calendar year: 'Q2 FY2026' = the quarter ending
    Jul-2026. yfinance's end-year labels call that quarter Q2'27, so prior_key (2, 2025) lands on
    the row ending Jul-2024 — TWO years back. With 8 quarters of history the old code returned
    a confidently-wrong YoY; the guard turns it into None."""
    from agents.market_intelligence import fundamentals
    rows = [{"period": "Q2'25", "revenue_m": 10_200.0},   # ends 2024-07-31 (wrong year)
            {"period": "Q3'25", "revenue_m": 10_180.0},
            {"period": "Q4'25", "revenue_m": 10_300.0},
            {"period": "Q1'26", "revenue_m": 10_436.0},
            {"period": "Q2'26", "revenue_m": 10_727.7},   # ends 2025-07-31 (the real prior year)
            {"period": "Q3'26", "revenue_m": 10_649.5},
            {"period": "Q4'26", "revenue_m": 10_911.2},
            {"period": "Q1'27", "revenue_m": 10_787.0}]
    ends = {"Q2'25": "2024-07-31", "Q3'25": "2024-10-31", "Q4'25": "2025-01-31",
            "Q1'26": "2025-04-30", "Q2'26": "2025-07-31", "Q3'26": "2025-10-31",
            "Q4'26": "2026-01-31", "Q1'27": "2026-04-30"}
    monkeypatch.setattr(fundamentals, "get_fundamentals", _fake_gf(rows, ends))
    # without the alert date the label match still fires (the pre-guard behaviour) — wrong year
    ungated = await fundamentals.compute_yoy_from_prior_year("DG", "Q2 FY2026", 11_290_000_000)
    assert ungated is not None and ungated["prior_period"] == "Q2'25"
    # with it, the two-years-back row is rejected — None, never a fabricated number
    assert await fundamentals.compute_yoy_from_prior_year(
        "DG", "Q2 FY2026", 11_290_000_000, alert_date=date(2026, 8, 27)) is None


@pytest.mark.asyncio
async def test_guard_passes_the_real_cohort_shapes(monkeypatch):
    """Replayed 2026-09-04 against all 102 prior-year matches in the 35-day cohort: the band
    changes none of them. Three representative shapes: a normal 37-day lag (INSM), a June-FYE
    Q4 (HRB, 43 days), and the stalest fill seen (BRUN, ~134 days — kept: freshness is rubric
    semantics, not this guard's)."""
    from agents.market_intelligence import fundamentals
    cases = [
        ("INSM", "Q2 2026", 425_486_000, date(2026, 8, 6), "Q2'25", "2025-06-30", 107.0),
        ("HRB", "Q4 FY2026", 1_145_000_000, date(2026, 8, 12), "Q4'25", "2025-06-30", 1111.0),
        ("BRUN", "Q1 2026", 10_960_000, date(2026, 8, 12), "Q1'25", "2025-03-31", 4.1),
    ]
    for t, fp, val, ad, prior, end, prior_m in cases:
        monkeypatch.setattr(fundamentals, "get_fundamentals",
                            _fake_gf([{"period": prior, "revenue_m": prior_m}], {prior: end}))
        rec = await fundamentals.compute_yoy_from_prior_year(t, fp, val, alert_date=ad)
        assert rec is not None and rec["prior_period"] == prior, t


def test_guard_cannot_judge_means_pass_through():
    from agents.market_intelligence.fundamentals import _prior_year_end_plausible
    d = date(2026, 8, 27)
    assert _prior_year_end_plausible(None, d) is True          # no end date recorded
    assert _prior_year_end_plausible("2025-07-31", None) is True  # no alert date (other callers)
    assert _prior_year_end_plausible("garbage", d) is True     # unparseable
    assert _prior_year_end_plausible("2025-07-31", d) is True  # the real prior year (27-day lag)
    assert _prior_year_end_plausible("2024-07-31", d) is False  # two years back — the DG shape
    assert _prior_year_end_plausible("2026-07-31", d) is False  # the CURRENT quarter, not a prior year


def test_get_fundamentals_records_period_ends_as_a_separate_map():
    """Period ends ride a top-level map, not a key on each row — the row lists' consumers and
    their exact-shape fixtures are untouched."""
    src = (Path(__file__).resolve().parent.parent
           / "agents" / "market_intelligence" / "fundamentals.py").read_text()
    assert 'quarterly_period_ends[label] = str(col)[:10]' in src
    assert 'result["quarterly_period_ends"] = quarterly_period_ends' in src
