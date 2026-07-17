"""#454 R3 part (1) — the weekly-review early-window drift appendix.

The load-bearing properties: (1) the line EXISTS from closed-trade 5 onward — the window
where the SIGNED #268b bands are silent (below the 20-trade sample floor) — and carries the
n<20 caveat IN the line; (2) it is informational only — it never emits a band/action word;
(3) it compares against the two trailing-20 reference points that ARE programmatically
stored in `CALIBRATION_ENVELOPE` (no full percentile curve exists anywhere).
"""
from unittest.mock import AsyncMock

import pytest

import agents.market_intelligence.kill_scale_bands as ksb
from agents.market_intelligence import system_review as sr


def _wire(monkeypatch, rs):
    """Drive the section via the band cohort edge (the SAME source the bands read)."""
    monkeypatch.setattr(ksb, "assemble_band_inputs", AsyncMock(return_value={
        "realized_rs": rs, "drawdown_tier": "OK",
        "equity_above_start": False, "account_mode": "live",
    }))


@pytest.mark.asyncio
async def test_below_5_trades_omitted_entirely(monkeypatch):
    # n<5: too thin to show anything — no misleading near-empty line (appendix convention).
    _wire(monkeypatch, [-1.0] * 4)
    assert await sr._early_window_drift_section() == ""


@pytest.mark.asyncio
async def test_pre_floor_prints_caveat_in_the_line(monkeypatch):
    # 5 ≤ n < 20 — THE window the section exists for: bands silent, caveat printed inline.
    _wire(monkeypatch, [-1.0, -1.0, 3.0, -1.0, -1.0])          # mean −0.20R, n=5
    out = await sr._early_window_drift_section()
    assert "Early-window drift" in out
    assert "-0.20R" in out and "5 closed trades" in out
    assert "n=5 < 20 sample floor" in out
    assert "SILENT" in out and "informational only" in out
    # −0.20R sits above p5 (−0.63R) → healthy-range phrasing, no scare framing.
    assert "within calibration's healthy trailing-20 range" in out


@pytest.mark.asyncio
async def test_pre_floor_flags_below_p5(monkeypatch):
    # Mean −0.70R ≤ envelope trailing-20 p5 (−0.63R) but above the min (−1.03R).
    _wire(monkeypatch, [-1.0] * 9 + [2.0])                     # mean −0.70R, n=10
    out = await sr._early_window_drift_section()
    assert "below calibration's trailing-20 p5 (-0.63R)" in out
    assert "n=10 < 20 sample floor" in out


@pytest.mark.asyncio
async def test_pre_floor_flags_at_or_below_calibration_min(monkeypatch):
    # Mean −1.10R ≤ the worst healthy trailing-20 window (−1.03R) — the loudest phrasing.
    _wire(monkeypatch, [-1.1] * 8)                             # mean −1.10R, n=8
    out = await sr._early_window_drift_section()
    assert "at/below calibration's worst trailing-20 window (-1.03R)" in out


@pytest.mark.asyncio
async def test_at_floor_defers_to_the_band_section(monkeypatch):
    # n ≥ 20: the bands now bind — the line still renders but points at the band verdict.
    _wire(monkeypatch, [0.5] * 20)
    out = await sr._early_window_drift_section()
    assert "+0.50R" in out and "20 closed trades" in out
    assert "n=20" in out and "kill/scale band section above" in out
    assert "SILENT" not in out


@pytest.mark.asyncio
async def test_informational_only_no_band_action_words(monkeypatch):
    # Even on an ugly cohort the line must never verdict (#268b bands own that).
    _wire(monkeypatch, [-1.2] * 12)
    out = await sr._early_window_drift_section()
    for banned in ("KILL", "REDUCE", "SCALE"):
        assert banned not in out
