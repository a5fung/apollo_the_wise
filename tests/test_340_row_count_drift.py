"""#340 — row-count DRIFT sweep (`health_checks.run_row_count_drift_sweep`).

A hand-pinned `expected_min_rows` rots, and rots silently in the worst direction: when the real
distribution steps DOWN legitimately, the job sits `empty_result` forever and the red light stops
meaning anything. #286 is the incident this is calibrated against — a liquidity floor took nightly
rows from 3,888-4,008 to 2,467-2,530 and `nightly_data_pull` was red EVERY market day for 2+ weeks
with nobody reading it.

Two signals, and the tests exist to prove they catch OPPOSITE failures:
  A. DROP        — latest run far below the trailing median → the DATA broke.
  B. STALE FLOOR — repeated empty_result at a STABLE row count → the PIN is wrong, not the data.

The load-bearing case is that **A alone cannot catch #286**: after a step-down the new level
becomes the median and the drop check correctly goes quiet, while the frozen pin stays red
forever. `test_step_down_is_invisible_to_the_drop_check_but_caught_by_b` pins exactly that.
"""
import asyncio
from datetime import datetime, timedelta

import pytest

from agents.market_intelligence import health_checks as hc

_T0 = datetime(2026, 7, 31, 17, 0)


def _runs(job_id, counts, *, status="success", pin=2200):
    """Newest-first run rows, as the sweep's query returns them."""
    return [{"job_id": job_id, "started_at": _T0 - timedelta(days=i), "rows_written": c,
             "status": status if not isinstance(status, list) else status[i],
             "expected_min_rows": pin}
            for i, c in enumerate(counts)]


def _wire(monkeypatch, rows):
    class _Conn:
        async def fetch(self, *a, **k):
            return rows

    class _Acq:
        async def __aenter__(self): return _Conn()
        async def __aexit__(self, *a): return False

    class _Pool:
        def acquire(self): return _Acq()

    async def _pool():
        return _Pool()
    monkeypatch.setattr(hc, "get_pool", _pool)

    logged, sent = [], []

    async def _log(event_type, summary, detail=""):
        logged.append((event_type, summary, detail))
    monkeypatch.setattr(hc, "log_audit_event", _log)

    import agents.market_intelligence.briefing as briefing

    async def _send(msg, *a, **k):
        sent.append(msg)
        return True
    monkeypatch.setattr(briefing, "send_telegram_message", _send)
    return logged, sent


def _run():
    return asyncio.run(hc.run_row_count_drift_sweep())


# ── signal A: the data broke ─────────────────────────────────────────────────────────────────

def test_flags_a_real_collapse(monkeypatch):
    # steady ~2500, then today 400
    _wire(monkeypatch, _runs("nightly_data_pull", [400] + [2500, 2490, 2510, 2495, 2505, 2500]))
    out = _run()
    assert [d["job_id"] for d in out["drops"]] == ["nightly_data_pull"]
    assert out["drops"][0]["drop_pct"] > 25


def test_ordinary_wobble_does_not_flag(monkeypatch):
    """The post-#286 band was 2,467-2,530 — ~2.5% spread. A guard that fires on that gets muted,
    and a muted guard misses the real failure."""
    _wire(monkeypatch, _runs("nightly_data_pull", [2467, 2530, 2500, 2490, 2510, 2495, 2505]))
    assert _run()["drops"] == []


def test_thin_history_never_flags(monkeypatch):
    """Fewer than _ROWCOUNT_MIN_HISTORY priors → we cannot judge, so we must not guess."""
    _wire(monkeypatch, _runs("new_job", [10, 2500, 2500]))
    assert _run()["drops"] == []


# ── signal B: the PIN broke — the #286 class ─────────────────────────────────────────────────

def test_stale_pin_detected_when_counts_are_stable(monkeypatch):
    _wire(monkeypatch, _runs("nightly_data_pull", [2467, 2530, 2500, 2490, 2510, 2505],
                             status="empty_result", pin=3500))
    out = _run()
    assert len(out["stale_floors"]) == 1
    s = out["stale_floors"][0]
    assert s["expected_min_rows"] == 3500 and s["consecutive"] >= 3
    assert 2400 < s["stable_at"] < 2600


def test_step_down_is_invisible_to_the_drop_check_but_caught_by_b(monkeypatch):
    """THE load-bearing case, and the reason two signals exist.

    #286 exactly: a legitimate step-down settles into a stable new normal. Once it has, the
    trailing median IS the new level, so signal A is correctly silent — and the frozen pin stays
    red forever with nobody reading it. Only B turns that into an alert.
    """
    _wire(monkeypatch, _runs("nightly_data_pull", [2500, 2490, 2510, 2495, 2505, 2500],
                             status="empty_result", pin=3500))
    out = _run()
    assert out["drops"] == [], "drop check should be quiet — the new level IS the median"
    assert len(out["stale_floors"]) == 1, "stale-pin check must catch what the drop check cannot"


def test_unstable_counts_are_NOT_called_a_stale_pin(monkeypatch):
    """Wildly varying counts that trip the pin are a DATA problem, not a miscalibrated pin —
    calling them a pin issue would send the operator to recalibrate away a real failure."""
    _wire(monkeypatch, _runs("nightly_data_pull", [100, 2500, 40, 1800, 3, 2200],
                             status="empty_result", pin=3500))
    assert _run()["stale_floors"] == []


def test_a_single_empty_result_is_not_yet_a_pin_problem(monkeypatch):
    _wire(monkeypatch, _runs("j", [2500] * 6,
                             status=["empty_result"] + ["success"] * 5, pin=3500))
    assert _run()["stale_floors"] == []


# ── emission + robustness ────────────────────────────────────────────────────────────────────

def test_clean_sweep_writes_audit_but_sends_no_telegram(monkeypatch):
    """Telegram is reserved for real failures (CLAUDE.md) — a quiet night must stay quiet."""
    logged, sent = _wire(monkeypatch, _runs("j", [2500, 2490, 2510, 2495, 2505, 2500]))
    _run()
    assert any(e[0] == "row_count_drift_sweep" for e in logged)
    assert sent == []


def test_findings_send_exactly_one_grouped_telegram(monkeypatch):
    logged, sent = _wire(monkeypatch,
                         _runs("a", [400] + [2500] * 6) + _runs("b", [300] + [1000] * 6))
    _run()
    assert len(sent) == 1 and "DROP" in sent[0]
    assert "a" in sent[0] and "b" in sent[0]


def test_never_raises_when_the_db_is_down(monkeypatch):
    async def _boom():
        raise RuntimeError("db down")
    monkeypatch.setattr(hc, "get_pool", _boom)
    out = _run()                       # must not raise
    assert out["errors"] and out["drops"] == []


def test_one_bad_job_does_not_kill_the_sweep(monkeypatch):
    bad = _runs("bad", [None, None, None, None, None, None])   # rows_written None → int() blows
    _wire(monkeypatch, bad + _runs("good", [400] + [2500] * 6))
    out = _run()
    assert out["errors"], "the bad job should be recorded, not swallowed"
    assert [d["job_id"] for d in out["drops"]] == ["good"], "the good job must still be scanned"


@pytest.mark.parametrize("pct", [hc._ROWCOUNT_DROP_PCT])
def test_threshold_sits_between_the_noise_and_the_real_step(pct):
    """Calibration is an assertion, not a comment: #286's real step was -36.5%; in-band wobble is
    ~2.5%. The threshold must separate them, or the guard is either noisy or blind."""
    assert 0.025 < pct < 0.365
