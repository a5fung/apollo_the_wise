"""#264 — drift checker min-N floor: a thin current window must not Telegram.

The 6/9 false alarm: 'Benzinga attribution 68%→20%' on n=10 current vs n=50
earnings-season baseline — cohort composition, not source degradation. Below
_MIN_CURRENT_N the drift-shaped event is audit-only (low_n_events).
"""
import asyncio

from agents.market_intelligence import news_source_quality as nsq


def _stats(n: int, attr: float, cov: float = 50.0, dens: int = 3) -> dict:
    return {"Alpaca/Benzinga": {
        "coverage_pct": cov, "density_median": dens,
        "attribution_pct": attr, "n_extractions": n,
    }}


def _run_detect(monkeypatch, current_n: int, cov: float = 50.0, dens: int = 3):
    # current, baseline. Delivery (coverage/density) is flat by default, which
    # is the cohort-composition shape; pass cov/dens to model a real outage.
    calls = iter([_stats(current_n, 20.0, cov, dens), _stats(50, 68.0)])

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
    # Delivery must ALSO have degraded, else the 2026-08-20 gate correctly reads
    # the attribution swing as cohort composition (see the next test).
    rep = _run_detect(monkeypatch, current_n=nsq._MIN_CURRENT_N, cov=5.0, dens=1)
    attr = [e for e in rep["drift_events"] if e["metric"] == "attribution_pct"]
    assert len(attr) == 1 and rep["low_n_events"] == []
    alert = nsq.format_drift_alert(rep)
    # (2) of #264: the operator can eyeball significance from the message.
    assert f"n={nsq._MIN_CURRENT_N}" in alert and "baseline n=50" in alert


def test_full_window_attribution_swing_is_audit_only_when_delivery_HOLDS(monkeypatch):
    """2026-08-20: the n floor alone let Benzinga 87%->44% through at n=18. If
    the source is still delivering, an attribution swing is cohort composition."""
    rep = _run_detect(monkeypatch, current_n=nsq._MIN_CURRENT_N)  # delivery flat
    assert rep["drift_events"] == []
    assert len(rep["suppressed_events"]) == 1
    assert rep["suppressed_events"][0]["suppressed_reason"] == "delivery_intact"
    assert nsq.format_drift_alert(rep) is None
