"""An attribution swing is only a source problem if the source stopped delivering.

2026-08-20: Benzinga attribution read 87% -> 44% and fired a Telegram alert while
the feed was healthy (4.6 articles per extraction vs a 4.5 baseline). Off earnings
season there is no press release carrying a revenue figure, so the extractor cites
FMP/Perplexity instead — attribution is confounded by the week's cohort. Delivery
is not, so it is the gate.
"""
import pytest

from agents.market_intelligence import news_source_quality as nsq


def _stats(cov, attr, dens, n):
    return {"coverage_pct": cov, "attribution_pct": attr,
            "density_median": dens, "n_extractions": n,
            "coverage_count": 0, "attribution_count": 0}


async def _drift(cur, base, monkeypatch):
    """detect_drift() calls collect_source_stats twice: current window first,
    then the trailing baseline. Return them in that order."""
    calls = []

    async def fake_collect(start, end):
        calls.append((start, end))
        return cur if len(calls) == 1 else base

    monkeypatch.setattr(nsq, "collect_source_stats", fake_collect)
    out = await nsq.detect_drift()
    assert len(calls) == 2, "expected a current-window and a baseline-window call"
    return out


@pytest.mark.asyncio
async def test_FAILS_WITHOUT_FIX_the_2026_08_20_benzinga_alert_is_suppressed(monkeypatch):
    cur = {"Alpaca/Benzinga": _stats(78, 44, 4.6, 18)}
    base = {"Alpaca/Benzinga": _stats(98, 87, 4.5, 176)}
    out = await _drift(cur, base, monkeypatch)
    assert out["drift_events"] == [], "delivery was intact — this must not Telegram"
    assert len(out["suppressed_events"]) == 1
    ev = out["suppressed_events"][0]
    assert ev["suppressed_reason"] == "delivery_intact"
    assert ev["metric"] == "attribution_pct"


@pytest.mark.asyncio
async def test_a_real_outage_still_alerts(monkeypatch):
    """Coverage collapses with attribution — the source genuinely stopped."""
    cur = {"Alpaca/Benzinga": _stats(20, 15, 1.0, 40)}
    base = {"Alpaca/Benzinga": _stats(98, 87, 4.5, 176)}
    out = await _drift(cur, base, monkeypatch)
    metrics = {e["metric"] for e in out["drift_events"]}
    assert "attribution_pct" in metrics, "an outage must still fire"
    assert "coverage_pct" in metrics


@pytest.mark.asyncio
async def test_thin_articles_still_alert_even_when_coverage_holds(monkeypatch):
    """Coverage looks fine but density collapsed — degraded content, still real."""
    cur = {"Alpaca/Benzinga": _stats(95, 40, 1.0, 40)}
    base = {"Alpaca/Benzinga": _stats(98, 87, 4.5, 176)}
    out = await _drift(cur, base, monkeypatch)
    assert any(e["metric"] == "attribution_pct" for e in out["drift_events"])


@pytest.mark.asyncio
async def test_a_coverage_drift_is_never_suppressed_by_this_gate(monkeypatch):
    """The gate only ever applies to attribution — coverage IS delivery."""
    cur = {"Alpaca/Benzinga": _stats(50, 85, 4.5, 40)}
    base = {"Alpaca/Benzinga": _stats(98, 87, 4.5, 176)}
    out = await _drift(cur, base, monkeypatch)
    assert [e["metric"] for e in out["drift_events"]] == ["coverage_pct"]


@pytest.mark.asyncio
async def test_low_n_still_wins_over_the_delivery_gate(monkeypatch):
    cur = {"Alpaca/Benzinga": _stats(78, 44, 4.6, 5)}
    base = {"Alpaca/Benzinga": _stats(98, 87, 4.5, 176)}
    out = await _drift(cur, base, monkeypatch)
    assert out["drift_events"] == []
    assert out["low_n_events"][0]["suppressed_reason"] == "low_n"
