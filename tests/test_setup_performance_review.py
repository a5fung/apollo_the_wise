"""STANDING per-setup entry/stop geometry review (operator 2026-08-02).

*"every setup, entry/stop, win/losses, etc will need periodic review regardless if we're winning or
losing. We're not trying to overfit, but we need to regularly monitor, ask questions, test
assumptions, finetune where appropriate, so this becomes a standing process."*

**Three invariants these tests hold:**
1. It SURFACES and asks; it never prescribes a stop, size or entry (THE LINE + CHANGE_PROCESS r3).
2. **The anti-overfit guard is the N-GATE, not the cadence.** Running weekly is fine; asking a
   question every week on n=3 is how you tune on noise.
3. **Every ASK is era-scoped (#585, 2026-08-23).** A cohort statistic spanning a rule-change date
   (PROFIT_TRIGGER_R live 2026-08-01, the entry-2R stop live 2026-08-16) answers a question the
   rule already closed. The 2026-08-23 weekly review said "5 trades reached +2R and closed red"
   as a live question when 4 of the 5 predated the mechanism that answers it — the operator
   caught it, not the system. Every ask below must be re-checked against only the trades entered
   under the CURRENT rule, and must say so (not go silent) when that sample is too thin to ask.
"""
import asyncio
from datetime import date
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


def _trade(alert_date, peak_r=0.5, realized_r=-0.3, exit_reason="stop_hit", stop_per_adr=0.46,
           signal_type="magna53", account_mode="live"):
    return dict(signal_type=signal_type, account_mode=account_mode, alert_date=alert_date,
                exit_reason=exit_reason, peak_r=peak_r, realized_r=realized_r,
                stop_per_adr=stop_per_adr)


# Default era-trade fixture: 12 trades dated AFTER both rule boundaries (2026-08-01 and
# 2026-08-16), reproducing the default `_row()`'s blended numbers exactly under EITHER era
# boundary — 4 reached >=+2R and closed red, all 12 exited stop_hit, median stop/ADR 0.46. Tests
# that only care about formatting (not era-scoping itself) use this so their old assertions'
# INTENT is preserved even though the exact wording changed to name the current-rules cohort.
_DEFAULT_ERA_TRADES = (
    [_trade(date(2026, 8, 20), peak_r=2.5, realized_r=-1.0) for _ in range(4)]
    + [_trade(date(2026, 8, 20), peak_r=0.4, realized_r=-0.2) for _ in range(8)]
)


def _section(monkeypatch, rows, era_trades=_DEFAULT_ERA_TRADES):
    monkeypatch.setattr(sr, "get_setup_performance_review", AsyncMock(return_value=rows))
    if isinstance(era_trades, Exception):
        monkeypatch.setattr(sr, "get_setup_era_trades", AsyncMock(side_effect=era_trades))
    else:
        monkeypatch.setattr(sr, "get_setup_era_trades", AsyncMock(return_value=era_trades))
    return _run(sr._setup_performance_section())


# ── it catches what the hand-cut caught (now against the CURRENT-rules cohort) ──────────────

def test_flags_that_every_exit_was_the_stop(monkeypatch):
    """The tell no win-rate number shows: nothing ever reached a profit-take."""
    out = _section(monkeypatch, [_row()])
    assert "every one of 12 exits under the current rules" in out
    assert "was the stop" in out


def test_flags_winners_converting_to_losers(monkeypatch):
    out = _section(monkeypatch, [_row()])
    assert "4 of 4 trades that reached ≥+2R under the current stop rules" in out
    assert "still closed red" in out


def test_flags_a_stop_inside_the_instruments_own_range(monkeypatch):
    out = _section(monkeypatch, [_row()])
    assert "0.46× the instrument" in out
    assert "under the current rules" in out


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


# ── era-scoping (#585, 2026-08-23) ───────────────────────────────────────────────────────────

def test_era_fetch_failure_suppresses_asks_rather_than_falling_back_to_blended(monkeypatch):
    """FAILS CLOSED. If the era-scoped fetch breaks, the section must not fall back to asking
    the unscoped (potentially rule-mixing) question — that fallback IS the bug being fixed."""
    out = _section(monkeypatch, [_row()], era_trades=RuntimeError("db unavailable"))
    assert "Questions for you" not in out
    assert "every one of 12 exits was the stop" not in out


def test_a_thin_current_era_says_not_enough_instead_of_asking(monkeypatch):
    """Requirement: '1 trade under the current rules — not enough to ask' is the correct,
    honest output when the blended condition would have asked but the current-rules sample
    can't carry it."""
    era_trades = [_trade(date(2026, 8, 20), peak_r=2.5, realized_r=-1.0)]  # only 1, all else old
    out = _section(monkeypatch, [_row()], era_trades=era_trades)
    assert "not enough to ask" in out
    assert "2026-08-16" in out
    # the misleading blended-only claim must never stand alone as a question
    assert "4 trades reached ≥+2R and still closed red — winners converting to losers." not in out


def test_the_exit_concentration_predate_count_is_read_from_era_trades_not_subtracted(monkeypatch):
    """predate = trades in era_trades dated before the boundary, computed directly — NOT
    (blended n) - (era n). The blended n comes from a different query (joined to
    mi_strategies); subtracting across two queries would misreport if that join ever fans out."""
    era_trades = (
        [_trade(date(2026, 7, 1))] * 3          # predates 2026-08-01, excluded
        + [_trade(date(2026, 8, 15))] * 9        # current era, n=9 >= floor
    )
    out = _section(monkeypatch, [_row(n=12, n_stop_hit=12, ran_then_lost=0, med_stop_per_adr=1.0)],
                    era_trades=era_trades)
    assert "every one of 9 exits under the current rules" in out
    assert "(3 predate the 2026-08-01 profit-trigger rule, excluded)" in out


# The real 2026-08-23 shape: MANE/PLTR/QBTS/SMCI/FIGS/ETON/NVCR. 7 trades reached >=+2R; 5 of
# them (MANE, QBTS, SMCI, FIGS, NVCR) closed red. The weekly review handed that "5 closed red"
# back as a live question. Ground truth (verified against prod, read-only, 2026-08-23): NONE of
# the 7 were entered on/after the 2026-08-16 stop-geometry change — the era the "+2R" unit itself
# is measured under. A correct review reports the split, not the blended 5.
_STRADDLE_TRADES = [
    _trade(date(2026, 7, 15), peak_r=7.92, realized_r=-0.23, stop_per_adr=0.30),   # MANE
    _trade(date(2026, 8, 4), peak_r=5.39, realized_r=3.42, exit_reason="trail_stop",
           stop_per_adr=0.40),                                                      # PLTR (win)
    _trade(date(2026, 7, 27), peak_r=3.74, realized_r=-1.00, stop_per_adr=0.35),    # QBTS
    _trade(date(2026, 7, 22), peak_r=3.21, realized_r=-0.70, stop_per_adr=0.32),    # SMCI
    _trade(date(2026, 8, 7), peak_r=2.90, realized_r=-0.37, stop_per_adr=0.38),     # FIGS
    _trade(date(2026, 8, 10), peak_r=2.09, realized_r=0.52, exit_reason="partial_exit",
           stop_per_adr=0.41),                                                      # ETON (win)
    _trade(date(2026, 7, 23), peak_r=2.00, realized_r=-1.00, stop_per_adr=0.29),    # NVCR
]


def test_a_straddling_cohort_is_reported_split_not_blended(monkeypatch):
    row = _row(n=22, wins=2, ran_then_lost=5, n_stop_hit=15, med_stop_per_adr=0.46)
    out = _section(monkeypatch, [row], era_trades=_STRADDLE_TRADES)
    # the literal bug from the 2026-08-23 review must not reappear as a standalone question
    assert "5 trades reached ≥+2R and still closed red — winners converting to losers." not in out
    # it must say so, not go silent
    assert "not enough to ask" in out
    assert "2026-08-16" in out


def test_a_straddling_cohort_still_asks_when_the_current_era_genuinely_supports_it(monkeypatch):
    """Sanity check on the other side: once ENOUGH of the reached-+2R trades sit inside the
    current stop era, the ask must fire again — this is scoping, not permanent silencing."""
    era_trades = _STRADDLE_TRADES + [
        _trade(date(2026, 8, 18), peak_r=2.2, realized_r=-0.5, stop_per_adr=0.9),
        _trade(date(2026, 8, 19), peak_r=2.4, realized_r=-0.6, stop_per_adr=0.9),
    ]
    row = _row(n=24, wins=2, ran_then_lost=5, n_stop_hit=15, med_stop_per_adr=0.46)
    out = _section(monkeypatch, [row], era_trades=era_trades)
    assert "2 of 2 trades that reached ≥+2R under the current stop rules" in out
    assert "Questions for you" in out
