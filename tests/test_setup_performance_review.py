"""STANDING per-setup entry/stop geometry review (operator 2026-08-02).

*"every setup, entry/stop, win/losses, etc will need periodic review regardless if we're winning or
losing. We're not trying to overfit, but we need to regularly monitor, ask questions, test
assumptions, finetune where appropriate, so this becomes a standing process."*

Built after doing this cut BY HAND found what no existing weekly section did: all 12 closed live
trades exited stop_hit with ZERO by any other route, half died inside 25 minutes, the stop sat at
0.46x the instrument's own ADR, and four trades reached >=+2R before closing at a full loss.

**Two invariants these tests hold:**
1. It SURFACES and asks; it never prescribes a stop, size or entry (THE LINE + CHANGE_PROCESS r3).
2. **The anti-overfit guard is the N-GATE, not the cadence.** Running weekly is fine; asking a
   question every week on n=3 is how you tune on noise.
"""
import asyncio
from unittest.mock import AsyncMock

import agents.market_intelligence.system_review as sr


def _run(c):
    return asyncio.get_event_loop().run_until_complete(c) if False else asyncio.run(c)


def _row(**kw):
    base = dict(signal_type="magna53", account_mode="live", n=12, wins=0, total_pnl=-224.01,
                top_exit="stop_hit", n_stop_hit=12, med_peak_r=0.56, med_realized_r=-1.00,
                ran_then_lost=4, med_stop_per_adr=0.46, blind_peaks=5, phase="live")
    base.update(kw)
    return base


def _section(monkeypatch, rows):
    monkeypatch.setattr(sr, "get_setup_performance_review", AsyncMock(return_value=rows))
    return _run(sr._setup_performance_section())


# ── it catches what the hand-cut caught ──────────────────────────────────────────────────────

def test_flags_that_every_exit_was_the_stop(monkeypatch):
    """The tell no win-rate number shows: nothing ever reached a profit-take."""
    out = _section(monkeypatch, [_row()])
    assert "every one of 12 exits was the stop" in out


def test_flags_winners_converting_to_losers(monkeypatch):
    out = _section(monkeypatch, [_row()])
    assert "4 trades reached ≥+2R and still closed red" in out


def test_flags_a_stop_inside_the_instruments_own_range(monkeypatch):
    out = _section(monkeypatch, [_row()])
    assert "0.46× the instrument" in out


def test_surfaces_the_unreadable_peaks_rather_than_hiding_them(monkeypatch):
    """5 of the 12 peaks were unreadable (fast exit, recorder blind <10m). A review that quoted
    peak stats without that caveat would overstate its own certainty."""
    out = _section(monkeypatch, [_row()])
    assert "unreadable" in out and "blind" in out


# ── the anti-overfit guard ───────────────────────────────────────────────────────────────────

def test_thin_samples_are_reported_but_asked_NOTHING(monkeypatch):
    """THE guard. n=3 still gets its numbers shown — monitoring is the point — but must generate
    no question, or the standing review becomes a weekly invitation to tune on noise."""
    out = _section(monkeypatch, [_row(n=3, n_stop_hit=3, ran_then_lost=2, wins=0)])
    assert "monitoring only" in out
    assert "Questions for you" not in out
    assert "every one of" not in out


def test_a_healthy_setup_asks_nothing(monkeypatch):
    """It runs win OR lose — but a setup with a mixed exit profile and a sane stop should produce
    no questions, so the section stays signal rather than noise."""
    out = _section(monkeypatch, [_row(n=20, wins=8, n_stop_hit=9, ran_then_lost=0,
                                      med_stop_per_adr=1.10, blind_peaks=0, top_exit="stop_hit")])
    assert "Questions for you" not in out


# ── it never prescribes ──────────────────────────────────────────────────────────────────────

def test_it_never_tells_the_operator_what_to_set(monkeypatch):
    out = _section(monkeypatch, [_row()]).lower()
    for verb in ("should set", "recommend", "widen the stop", "use a stop of", "increase size"):
        assert verb not in out, f"section must SURFACE, not prescribe (found: {verb})"


def test_renders_nothing_when_there_is_no_data(monkeypatch):
    assert _section(monkeypatch, []) == ""


def test_a_query_failure_degrades_to_silence_not_a_broken_review(monkeypatch):
    monkeypatch.setattr(sr, "get_setup_performance_review", AsyncMock(side_effect=RuntimeError("db")))
    assert _run(sr._setup_performance_section()) == ""


# ── retired strategies must be MARKED, never read as running ─────────────────────────────────
# The operator saw 9m_day2 in this section hours after we deleted the strategy and reasonably
# asked "why is it back?". The rows were old paper trades (newest 2026-06-10) — the section was
# simply not saying so. Unlabelled history beside live cohorts is how confusion gets built in.

def test_a_retired_strategy_is_labelled_as_history(monkeypatch):
    out = _section(monkeypatch, [_row(signal_type="9m_day2", account_mode="paper",
                                      n=7, wins=3, phase="deprecated")])
    assert "RETIRED" in out and "history only" in out


def test_a_retired_strategy_never_generates_a_question(monkeypatch):
    """Even with every trigger tripped — there is nothing left to tune on a deleted strategy."""
    out = _section(monkeypatch, [_row(signal_type="9m_day2", n=30, n_stop_hit=30,
                                      ran_then_lost=5, med_stop_per_adr=0.2,
                                      phase="deprecated")])
    assert "Questions for you" not in out
    assert "retired strategy" in out


def test_a_live_strategy_is_not_labelled_retired(monkeypatch):
    out = _section(monkeypatch, [_row(phase="live")])
    assert "RETIRED" not in out
    assert "Questions for you" in out
