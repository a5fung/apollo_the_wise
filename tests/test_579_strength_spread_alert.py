"""#579 — ad-hoc alert on the strength-map direction spreads.

The strength map already computes "are the miners outrunning the metal?" — it only ever
surfaced inside the WEEKLY briefing, so the operator found a 15.3pt precious-metals lead on
Twitter before Apollo told him. This surface fires DAILY on a genuine crossing of each pair's
own self-calibrating 75th-percentile bar (measured in
docs/analysis/579_spread_firing_distribution_2026-09-11.md — that measurement is not re-derived
or re-argued here, only built), never on a schedule and never on every day the reading stays
elevated.

Tests exercise the PURE core (`evaluate_spread_crossing`, `_classify_spread_state`,
`_is_new_crossing`, `format_spread_crossing_alert`) with hand-built spread histories, plus one
DB-mocked wiring test for the audit/Telegram/state-persistence plumbing. THE LINE: nothing here
touches strategy, entry, exit, sizing, safeguard, grade or admission — this is a notification.
"""
from __future__ import annotations

from datetime import date, timedelta
from unittest.mock import AsyncMock

import pytest

from tests.conftest import make_mock_pool

from agents.market_intelligence import strength_map as sm

# Comfortably above `_SPREAD_ALERT_MIN_JUDGED` (240) once the 30-session lag is paid, so every
# `evaluate_spread_crossing` call below actually measures a band instead of skipping.
_N_FLAT = 300


def _jittery_history(n, base=5.0, amp=0.2, period=7):
    """n nearly-flat (date, spread) points with small deterministic jitter. A realistic
    'typical move is small but not exactly zero' population — a perfectly flat series would
    give the degenerate band=0 (every reading, even a truly flat one, would then read as a
    crossing), which no real market spread behaves like."""
    d0 = date(2020, 1, 1)
    return [(d0 + timedelta(days=i), base + (i % period) * amp) for i in range(n)]


def _step_after(hist, level, hold):
    """Appends `hold` more points held FLAT at `level` right after `hist` — models a genuine
    regime shift (a step), not a one-day blip."""
    d0 = hist[-1][0]
    return hist + [(d0 + timedelta(days=i + 1), level) for i in range(hold)]


# ── DoD 6: only the complexes that actually have a spread ──────────────────────────────────

def test_only_precious_metals_and_energy_qualify():
    """Uranium/Agriculture/Macro backdrop have no anchor+expression pair and must be ABSENT
    from the alert entirely — never silently counted as quiet."""
    assert sm._SPREAD_ALERT_COMPLEXES == ("Precious metals", "Energy")
    names = {c["name"] for c in sm.COMPLEXES}
    for absent in ("Uranium", "Agriculture", "Macro backdrop"):
        assert absent in names            # sanity: the complex exists in strength_map...
        assert absent not in sm._SPREAD_ALERT_COMPLEXES   # ...but never in this alert


def test_short_history_is_skipped_not_guessed():
    """Below `_SPREAD_ALERT_MIN_JUDGED` the alert must say so and evaluate nothing — never
    invent a default bar the way `_dominance_band` does for a DIFFERENT purpose (a classifier
    that must always show something). This alert only ever fires or stays silent; a guessed bar
    could fire wrongly."""
    ev = sm.evaluate_spread_crossing(_jittery_history(50), old_state="quiet")
    assert ev["measured"] is False


# ── DoD 2: fire on the crossing, not on every day above the bar ────────────────────────────

def test_a_crossing_fires_once_and_not_again_while_it_stays_above():
    """The move goes from below the bar to at/above it -> fires. The NEXT day, still elevated
    in the SAME direction, with that state now persisted -> must NOT re-fire. Median run above
    the bar is 2-3 days; firing daily through that run is the exact failure mode named in the
    task."""
    base = _jittery_history(_N_FLAT)
    hist = _step_after(base, level=base[-1][1] + 10.0, hold=2)
    first_jump_idx = _N_FLAT   # 0-based index of the first post-jump point

    ev_first = sm.evaluate_spread_crossing(hist[:first_jump_idx + 1], old_state="quiet")
    assert ev_first["measured"] is True
    assert ev_first["new_state"] == "pulling_ahead"
    assert ev_first["crossed"] is True, ev_first

    ev_next = sm.evaluate_spread_crossing(hist[:first_jump_idx + 2],
                                           old_state=ev_first["new_state"])
    assert ev_next["new_state"] == "pulling_ahead"
    assert ev_next["crossed"] is False, ev_next


# ── DoD 3: dedupe on (complex, DIRECTION) ───────────────────────────────────────────────────

def test_dropping_below_and_re_crossing_fires_again():
    """A re-fire in the SAME direction requires the move to drop back below the bar first."""
    base = _jittery_history(_N_FLAT)
    hold_long = sm._SPREAD_ALERT_MOVE_SESSIONS + 3   # far enough past the jump the move reverts
    hist_late = _step_after(base, level=base[-1][1] + 10.0, hold=hold_long)

    ev_late = sm.evaluate_spread_crossing(hist_late, old_state="pulling_ahead")
    assert ev_late["new_state"] == "quiet"
    assert ev_late["crossed"] is False   # dropping to quiet is never itself a fired event

    # a SECOND jump, now that the dedupe has cleared, must fire again in the SAME direction.
    hist_recross = _step_after(hist_late, level=hist_late[-1][1] + 10.0, hold=1)
    ev_recross = sm.evaluate_spread_crossing(hist_recross, old_state=ev_late["new_state"])
    assert ev_recross["new_state"] == "pulling_ahead"
    assert ev_recross["crossed"] is True, ev_recross


def test_the_opposite_direction_fires_separately():
    """A swing from +10 through zero to -10 is two different trades, not one continuing
    event — a direct flip to the opposite direction always fires, even without an intervening
    'quiet' reading."""
    base = _jittery_history(_N_FLAT)
    hist_down = _step_after(base, level=base[-1][1] - 10.0, hold=1)   # a FALL, not a rise
    ev = sm.evaluate_spread_crossing(hist_down, old_state="pulling_ahead")
    assert ev["new_state"] == "falling_behind"
    assert ev["crossed"] is True, ev


def test_the_move_is_symmetric_a_fall_counts_like_a_rise():
    """Operator's own question, answered: 'what about the reverse — what if it drops ten
    points?' The magnitude gate must be exactly as sensitive to a fall as to a rise; only the
    reported DIRECTION differs."""
    base = _jittery_history(_N_FLAT)
    hist_up = _step_after(base, level=base[-1][1] + 10.0, hold=1)
    hist_down = _step_after(base, level=base[-1][1] - 10.0, hold=1)
    ev_up = sm.evaluate_spread_crossing(hist_up, old_state="quiet")
    ev_down = sm.evaluate_spread_crossing(hist_down, old_state="quiet")
    assert ev_up["crossed"] and ev_down["crossed"]
    assert ev_up["new_state"] == "pulling_ahead"
    assert ev_down["new_state"] == "falling_behind"
    assert abs(ev_up["move"]) == pytest.approx(abs(ev_down["move"]), abs=0.5)


# ── DoD 4 + 5: plain-word direction and a stated silence rate ──────────────────────────────

def test_message_names_the_direction_in_plain_words():
    """An absolute-value trigger would render opposite trades identically — the message must
    say WHICH direction happened, in the operator's own words, and state its own silence rate
    so a quiet month reads as expected rather than as a broken job. No pipe tables (CLAUDE.md)."""
    up = dict(measured=True, judged=300, date=date(2026, 9, 11), band=10.3, move=14.9,
              spread_now=18.4, old_state="quiet", new_state="pulling_ahead",
              crossed=True, crossings_per_month=1.2)
    down = dict(up, new_state="falling_behind", move=-14.9)

    msg_up = sm.format_spread_crossing_alert("Precious metals", up)
    msg_down = sm.format_spread_crossing_alert("Precious metals", down)

    assert "Gold miners pulling ahead of gold" in msg_up
    assert "Gold miners falling behind gold" in msg_down
    assert msg_up != msg_down
    assert "1.2x a month" in msg_up
    assert "|" not in msg_up          # never a pipe table
    assert "```" in msg_up            # monospace block for the numbers

    energy = dict(up, crossings_per_month=0.9)
    msg_energy = sm.format_spread_crossing_alert("Energy", energy)
    assert "Energy stocks pulling ahead of oil & gas" in msg_energy


# ── wiring: DB state + audit + Telegram, and per-complex isolation ─────────────────────────

@pytest.mark.asyncio
async def test_wiring_audits_always_telegrams_only_on_crossing_and_persists_state(monkeypatch):
    """End-to-end through `run_spread_crossing_alert`: an audit row every run (even the quiet
    complex), Telegram ONLY for the complex that actually crossed, state persisted for both —
    and ONLY the two qualifying complexes are ever touched (DoD 6, exercised live)."""
    pool, conn = make_mock_pool()
    conn.fetch = AsyncMock(return_value=[])   # _direction_spread_series is patched below
    monkeypatch.setattr(sm, "get_pool", AsyncMock(return_value=pool))

    base = _jittery_history(_N_FLAT)
    crossing_hist = _step_after(base, level=base[-1][1] + 10.0, hold=1)
    quiet_hist = _jittery_history(_N_FLAT + 5)

    def _fake_spread_series(series, complex_def, bars):
        return crossing_hist if complex_def["name"] == "Precious metals" else quiet_hist
    monkeypatch.setattr(sm, "_direction_spread_series", _fake_spread_series)

    state_reads = []
    state_writes = []

    async def _fake_get_state(conn_, name):
        state_reads.append(name)
        return "quiet"

    async def _fake_set_state(conn_, name, state, move, band):
        state_writes.append((name, state))

    monkeypatch.setattr(sm, "_get_alert_state", _fake_get_state)
    monkeypatch.setattr(sm, "_set_alert_state", _fake_set_state)

    audit = AsyncMock()
    monkeypatch.setattr(sm, "log_audit_event", audit)
    from agents.market_intelligence import briefing as _brief
    tg = AsyncMock()
    monkeypatch.setattr(_brief, "send_telegram_message", tg)

    res = await sm.run_spread_crossing_alert(date(2026, 9, 12))

    assert set(state_reads) == {"Precious metals", "Energy"}   # only the 2 qualifying complexes
    assert audit.await_count == 2                              # audited every run, quiet included
    tg.assert_awaited_once()                                   # Telegram ONLY on the crossing
    assert "Gold miners pulling ahead of gold" in tg.await_args.args[0]
    assert res["fired"] == ["Precious metals"]
    assert set(state_writes) == {("Precious metals", "pulling_ahead"), ("Energy", "quiet")}


@pytest.mark.asyncio
async def test_a_failed_telegram_send_does_not_advance_state(monkeypatch):
    """`send_telegram_message` returns False (does not raise) on a missing token/chat-id or an
    HTTP failure. If the state write happened anyway, a delivery failure would silently EAT the
    crossing — tomorrow's comparison would see the old, unfired state and never notice it
    already changed. The fix: skip the state write on a failed send so the next run retries."""
    pool, conn = make_mock_pool()
    conn.fetch = AsyncMock(return_value=[])
    monkeypatch.setattr(sm, "get_pool", AsyncMock(return_value=pool))

    base = _jittery_history(_N_FLAT)
    crossing_hist = _step_after(base, level=base[-1][1] + 10.0, hold=1)
    monkeypatch.setattr(sm, "_direction_spread_series",
                        lambda series, complex_def, bars: crossing_hist)
    monkeypatch.setattr(sm, "_get_alert_state", AsyncMock(return_value="quiet"))
    set_calls = AsyncMock()
    monkeypatch.setattr(sm, "_set_alert_state", set_calls)
    monkeypatch.setattr(sm, "log_audit_event", AsyncMock())
    from agents.market_intelligence import briefing as _brief
    monkeypatch.setattr(_brief, "send_telegram_message", AsyncMock(return_value=False))

    res = await sm.run_spread_crossing_alert(date(2026, 9, 12))

    assert res["fired"] == []                                    # a failed send never "fires"
    assert set(res["errors"]) == {"Precious metals", "Energy"}    # both crossed, both failed to send
    set_calls.assert_not_awaited()        # state must NOT advance on a failed send, for either


@pytest.mark.asyncio
async def test_one_complex_failure_does_not_silence_the_other(monkeypatch):
    """Failures must never break the host job or block a sibling complex (CLAUDE.md style:
    per-complex try/except + logger.warning + `# loud-ok:`)."""
    pool, conn = make_mock_pool()
    conn.fetch = AsyncMock(return_value=[])
    monkeypatch.setattr(sm, "get_pool", AsyncMock(return_value=pool))

    quiet_hist = _jittery_history(_N_FLAT + 5)

    def _fake_spread_series(series, complex_def, bars):
        if complex_def["name"] == "Precious metals":
            raise RuntimeError("boom — simulated data problem")
        return quiet_hist
    monkeypatch.setattr(sm, "_direction_spread_series", _fake_spread_series)
    set_calls = AsyncMock()
    monkeypatch.setattr(sm, "_get_alert_state", AsyncMock(return_value="quiet"))
    monkeypatch.setattr(sm, "_set_alert_state", set_calls)
    audit = AsyncMock()
    monkeypatch.setattr(sm, "log_audit_event", audit)
    from agents.market_intelligence import briefing as _brief
    monkeypatch.setattr(_brief, "send_telegram_message", AsyncMock())

    res = await sm.run_spread_crossing_alert(date(2026, 9, 12))

    assert res["errors"] == ["Precious metals"]   # the broken complex is counted as failed...
    assert res["fired"] == []                     # ...never fires (nothing to send for it)
    assert res["skipped"] == []                   # Energy's quiet history WAS measurable (not "too little history")
    # ...and Energy still ran to completion despite Precious metals blowing up beside it.
    audit.assert_awaited_once()
    set_calls.assert_awaited_once()
    assert set_calls.await_args.args[1] == "Energy"   # args[0] is `conn`
