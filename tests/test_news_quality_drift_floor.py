"""#264 — drift checker min-N floor: a thin current window must not Telegram.

The 6/9 false alarm: 'Benzinga attribution 68%→20%' on n=10 current vs n=50
earnings-season baseline — cohort composition, not source degradation. Below
_MIN_CURRENT_N the drift-shaped event is audit-only (low_n_events).
"""
import asyncio

from agents.market_intelligence import news_source_quality as nsq


def _stats(n: int, attr: float) -> dict:
    return {"Alpaca/Benzinga": {
        "coverage_pct": 50.0, "density_median": 3,
        "attribution_pct": attr, "n_extractions": n,
    }}


def _run_detect(monkeypatch, current_n: int):
    calls = iter([_stats(current_n, 20.0), _stats(50, 68.0)])  # current, baseline

    async def fake_collect(start, end):
        return next(calls)

    monkeypatch.setattr(nsq, "collect_source_stats", fake_collect)
    return asyncio.run(nsq.detect_drift())


def test_thin_window_drift_is_audit_only(monkeypatch):
    rep = _run_detect(monkeypatch, current_n=10)
    assert rep["drift_events"] == []
    assert len(rep["low_n_events"]) == 1
    assert rep["low_n_events"][0]["current_n"] == 10
    # No drift_events → format returns None → no Telegram path.
    assert nsq.format_drift_alert(rep) is None


def test_full_window_drift_fires_with_n_context(monkeypatch):
    rep = _run_detect(monkeypatch, current_n=nsq._MIN_CURRENT_N)
    assert len(rep["drift_events"]) == 1 and rep["low_n_events"] == []
    alert = nsq.format_drift_alert(rep)
    # (2) of #264: the operator can eyeball significance from the message.
    assert f"n={nsq._MIN_CURRENT_N}" in alert and "baseline n=50" in alert
