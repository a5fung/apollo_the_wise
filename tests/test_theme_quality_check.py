"""Nightly THEME QUALITY check (#531, 2026-08-04) — two regression guards for the two theme-
lifecycle bugs #368 fixed.

WHY THIS EXISTS. Operator, verbatim: "i'm really asking for quality checks regularly to make sure
our themes are solid without me needing to check it and review manually." He should learn a theme
defect from a Telegram, not from an investigation — which is exactly how #368 itself was found (5
of 9 theme-credit false positives traced to one mechanism nobody was watching for).

Two signatures were measured against 97 real trading days of prod `mi_themes` (2026-03-19..
2026-08-04) before either shipped; two more (fragmentation, churn) were measured and DROPPED as
too noisy to trust — see `agents/market_intelligence/health_checks.py`'s #531 section header for
the full counts and reasoning.

  A. "retired while healthy" — a theme silently vanished from mi_themes (no row at all, any stage)
     the night after its last-known row was Fading WITH rs_avg populated. Measured: 6 of 165
     distinct retirement incidents, every one hand-checked real. The #368/F2 regression guard.
  B. "member pruned while rising" — a ticker left a still-alive theme while its 6-session RS
     trajectory was rising and it was a genuine prune candidate (not a mass-eviction, not moved to
     another theme). Measured: 25 of 164 prune-shaped exits; 79% of the scored ones recovered to
     RS>=50 within 10 sessions vs 36% of the falling control — the #368/F3 regression guard.

Mirrors `test_health_checks_null_sweep.py`'s shape: PURE decisions tested first with zero mocking
(plain dicts/floats — the exact real-data shapes hand-verified during measurement), then the
orchestrator (`run_theme_quality_check`) driven end-to-end with the db.py layer monkeypatched
(its SQL is exercised for real by `docs/analysis/531_theme_quality_measurement_2026-08-04.md`'s
measurement run against prod, not re-proven here).
"""
from __future__ import annotations

from datetime import date

import pytest

from agents.market_intelligence import health_checks
from agents.market_intelligence.health_checks import (
    _evaluate_theme_retirement,
    _evaluate_pruned_while_rising,
    _is_mass_eviction,
    _rs_rising_mirror,
    _PRUNE_RS_HARD_MIRROR,
    _PRUNE_RS_SOFT_MIRROR,
    _PRUNE_HOLD_MIN_POINTS_MIRROR,
    _check_pruned_while_rising,
    run_theme_quality_check,
)


# ── Mirror-parity pin: this check's copy of the engine's thresholds/rising test ──────────────────
# If theme_engine.py's real values ever move without this file following, the check silently
# drifts out of sync with the mechanism it's guarding — exactly the failure class #531 exists to
# catch elsewhere. Pin it here too.


def test_mirrored_constants_match_the_real_engine():
    from agents.market_intelligence.theme_engine import (
        PRUNE_RS_HARD, PRUNE_RS_SOFT, PRUNE_HOLD_MIN_POINTS,
    )
    assert _PRUNE_RS_HARD_MIRROR == PRUNE_RS_HARD
    assert _PRUNE_RS_SOFT_MIRROR == PRUNE_RS_SOFT
    assert _PRUNE_HOLD_MIN_POINTS_MIRROR == PRUNE_HOLD_MIN_POINTS


def test_mirrored_rs_rising_matches_the_real_engine_across_samples():
    from agents.market_intelligence.theme_engine import _rs_rising as real_rs_rising
    samples = [
        [10.7, 7.4, 6.0, 1.5, 1.7, 2.4],   # IREN's real 7/22 shape — rising
        [25.4, 26.0, 23.9, 20.5, 19.2, 16.2],  # STE — rising (V-shape)
        [20.4, 25.8, 35.7, 42.3, 55.0, 45.7],  # GD — falling from a high point
        [5.0, 4.0, 3.0],                        # too few points — fails closed
        [],
        # 2026-08-26: BLDR's real 08-25 history — the collapse that the endpoint-only
        # test called "rising" (10.0 > 5.9) and this very check false-alarmed on. Both
        # sides must now agree it is NOT rising, or the check drifts from the engine.
        [10.0, 13.8, 25.7, 29.4, 29.2, 5.9],
        [12.2, 70.7, 71.6, 66.4, 36.6, 5.3],    # BRUN 08-20, same shape, prod-recorded
        [22.1, 23.9, 24.4, 11.9, 19.9, 15.9],   # SO — genuinely up over the window
    ]
    for hist in samples:
        assert _rs_rising_mirror(hist) == real_rs_rising(hist), hist


# ── Signature A: _evaluate_theme_retirement (pure, zero mocking) ─────────────────────────────────


def test_fires_on_the_verified_bitcoin_mining_shape():
    # Real prod case (2026-08-04): last row before vanishing was Fading, rs_avg=84.9 on 8/03;
    # no row at all for the theme on 8/04 (the silent-vanish shape). This is the DoD case.
    today = date(2026, 8, 4)
    history = [
        {"theme_date": date(2026, 8, 3), "stage": "Fading", "rs_avg": 84.9, "score": 72.5},
        {"theme_date": date(2026, 7, 31), "stage": "Fading", "rs_avg": None, "score": 25.2},
    ]
    verdict = _evaluate_theme_retirement(today, history)
    assert verdict is not None, "a healthy (rs_avg-bearing) Fading row that silently vanished MUST flag"
    assert verdict["prior_rs_avg"] == 84.9
    assert verdict["prior_date"] == date(2026, 8, 3)


def test_silent_on_the_correct_weak_retirement_shape():
    # 'Crypto Recovery'-style: last row was Fading with rs_avg=None (the weak branch — the
    # EXPECTED, correct retirement shape #368/F2 was never meant to touch).
    today = date(2026, 4, 1)
    history = [
        {"theme_date": date(2026, 3, 31), "stage": "Fading", "rs_avg": None, "score": 0.0},
        {"theme_date": date(2026, 3, 30), "stage": "Fading", "rs_avg": None, "score": 2.7},
    ]
    assert _evaluate_theme_retirement(today, history) is None


def test_silent_when_an_explicit_same_day_row_exists():
    # The Arm-A 2-member-dissolve false positive found and excluded during measurement: an
    # explicit stage='Retired' row IS written same-day (score=0, rs_avg=None, tickers={}) — a
    # DIFFERENT, legitimate mechanism (validation-flagged member dissolves a 2-member theme).
    # #368/F2 never touches this path; firing here would point at the wrong fix.
    today = date(2026, 7, 27)
    history = [
        {"theme_date": date(2026, 7, 27), "stage": "Retired", "rs_avg": None, "score": 0.0},
        {"theme_date": date(2026, 7, 24), "stage": "Nascent", "rs_avg": 93.8, "score": 76.9},
    ]
    assert _evaluate_theme_retirement(today, history) is None


def test_silent_when_no_prior_history_at_all():
    # A brand-new theme with no history to judge "healthy" against — can't confirm anything.
    assert _evaluate_theme_retirement(date(2026, 8, 4), []) is None


def test_silent_when_prior_row_is_outside_the_lookback_window():
    # A name can be REUSED after a long gap (measurement finding: 'Custom AI Silicon & Chip
    # Architecture Licensing' went dark 03-30..04-16, then came back — not the same lifecycle
    # as the original 03-20 birth). If a stale healthy row ever slipped past the caller's
    # [today-7, today] fetch bound, this pure function must not treat a 40-day-old Fading/
    # rs_avg row as "just retired while healthy" — without this the reused-name class becomes
    # a false-positive source once any caller ever widens the bound.
    today = date(2026, 8, 4)
    history = [
        {"theme_date": date(2026, 6, 25), "stage": "Fading", "rs_avg": 90.0, "score": 78.0},
    ]
    assert _evaluate_theme_retirement(today, history) is None


# ── Signature B: _is_mass_eviction + _evaluate_pruned_while_rising (pure, zero mocking) ──────────


def test_mass_eviction_excludes_a_validation_strip():
    # #214 signature: >=3 leavers AND >=50% of membership gone at once — a strip, not a prune.
    assert _is_mass_eviction(n_gone=3, prior_member_count=5) is True
    assert _is_mass_eviction(n_gone=4, prior_member_count=6) is True


def test_mass_eviction_does_not_exclude_an_ordinary_one_or_two_ticker_prune():
    assert _is_mass_eviction(n_gone=1, prior_member_count=6) is False
    assert _is_mass_eviction(n_gone=2, prior_member_count=6) is False


def test_mass_eviction_does_not_exclude_a_few_leavers_from_a_big_theme():
    # 3 leavers from an 18-member theme is <50% — an ordinary prune day, not a strip.
    assert _is_mass_eviction(n_gone=3, prior_member_count=18) is False


def test_fires_on_the_verified_iren_shape():
    # Real prod case (2026-07-22): IREN pruned from 'AI Compute & GPU Data Center Hosting
    # Operators' while igniting — RS 10.7, rising over the hold window. Exactly the #368 miner
    # cohort mechanism F3 now holds instead of prunes.
    hist6 = [10.7, 7.4, 6.0, 1.5, 1.7, 2.4]
    verdict = _evaluate_pruned_while_rising(rs_now=10.7, hist3=hist6[:3], hist6=hist6)
    assert verdict is not None, "a hard-floor prune candidate whose RS is rising MUST flag"
    assert verdict["rs_now"] == 10.7


def test_silent_on_a_falling_control():
    # The hold correctly still prunes falling exits — this check must stay silent on them too.
    # newest(2.8) < oldest(3.7) -> falling.
    hist6 = [2.8, 2.6, 2.5, 2.2, 3.7, 3.7]
    assert _evaluate_pruned_while_rising(rs_now=2.8, hist3=hist6[:3], hist6=hist6) is None


def test_silent_when_rs_now_is_at_or_above_the_soft_floor():
    # The engine's own gate: rs_now >= PRUNE_RS_SOFT(35) was NEVER a prune candidate at all — it
    # left the theme for some OTHER reason (validation, reassignment). Without this gate a rising
    # ticker that simply wasn't up for pruning would false-fire (the bug caught before shipping).
    hist6 = [40.0, 10.0, 10.0, 10.0, 10.0, 5.0]  # "rising" by the raw newest>oldest test, but rs_now=40
    assert _evaluate_pruned_while_rising(rs_now=40.0, hist3=hist6[:3], hist6=hist6) is None


def test_soft_band_requires_the_three_day_confirm():
    # rs_now in [HARD, SOFT) = [25, 35) is a candidate ONLY on the 3rd consecutive sub-floor day
    # (mirrors the engine's soft-prune gate exactly). Two of the last three days are >= SOFT here
    # -> never actually became a prune candidate -> must NOT fire even though it's "rising".
    hist6 = [30.0, 40.0, 40.0, 5.0, 4.0, 3.0]  # hist3 = [30, 40, 40] — not all < SOFT
    assert _evaluate_pruned_while_rising(rs_now=30.0, hist3=hist6[:3], hist6=hist6) is None


def test_soft_band_fires_once_three_day_confirm_and_rising_both_hold():
    hist6 = [30.0, 32.0, 33.0, 5.0, 4.0, 3.0]  # hist3 all < SOFT(35); newest(30) > oldest(3) -> rising
    verdict = _evaluate_pruned_while_rising(rs_now=30.0, hist3=hist6[:3], hist6=hist6)
    assert verdict is not None


def test_silent_when_rs_now_is_missing():
    assert _evaluate_pruned_while_rising(rs_now=None, hist3=[], hist6=[]) is None


# ── Signature B: _check_pruned_while_rising orchestration (the two bugs an advisor review
# caught before shipping — both worth their own regression test, not just a passing count) ──────


@pytest.mark.asyncio
async def test_mass_eviction_is_judged_on_all_leavers_not_the_moved_filtered_count(monkeypatch):
    # Real prod shape (2026-08-04 dry run, exact tickers): 'Gold & Precious Metals Miners
    # Rotation' (18 prior members) split into two child themes — 15 members MOVED there, 1
    # straggler (HYMC) did not. That is a structural split, not a daily prune, and must be
    # excluded WHOLESALE. A first-pass bug computed mass-eviction on the moved-filtered count
    # (1 of 18 — nowhere near the >=50% bar) instead of the true leaver count (16 of 18), which
    # would have let the straggler fire on its own. Verifies the fix: mass-eviction must be
    # judged BEFORE the moved-filter shrinks the population.
    today, prior = date(2026, 8, 4), date(2026, 8, 3)

    async def _departures(conn, t, p):
        rows = [
            {"name": "Gold & Precious Metals Miners Rotation", "ticker": tk,
             "prior_member_count": 18, "moved_today": True}
            for tk in ["SBSW", "KGC", "NEM", "GFI", "IAG", "AU", "PAAS", "HL", "EXK",
                       "FSM", "CDE", "AGI", "SSRM", "PPTA", "AG"]
        ]
        rows.append({"name": "Gold & Precious Metals Miners Rotation", "ticker": "HYMC",
                     "prior_member_count": 18, "moved_today": False})
        return rows

    async def _rs_on_date(conn, tickers, d):
        return {"HYMC": 10.0}  # sub-hard-floor, would otherwise be a prune candidate

    async def _rs_batch(tickers, asof, days=6):
        return {"HYMC": [10.0, 9.8, 3.0, 3.2, 4.7, 3.8]}  # rising — would fire if scored

    monkeypatch.setattr(health_checks, "get_theme_member_departures", _departures)
    monkeypatch.setattr(health_checks, "get_rs_on_date", _rs_on_date)
    monkeypatch.setattr(health_checks, "get_recent_rs_batch", _rs_batch)

    result = await _check_pruned_while_rising(conn=object(), today=today, prior_date=prior)

    assert result["flags"] == [], "a 17-of-18 structural split must exclude the straggler too"


@pytest.mark.asyncio
async def test_a_ticker_absent_from_todays_exact_rs_snapshot_is_skipped_not_scored(monkeypatch):
    # theme_engine.py's `missing_rs_tickers` branch (a ticker absent from today's RS universe)
    # prunes on plain 5-day history and NEVER consults `_rs_rising` — so a departed ticker with
    # no row for exactly today is a DIFFERENT engine code path, not this check's concern. A
    # first-pass bug read `get_recent_rs_batch`'s hist[0] as "today's RS", which silently falls
    # back to the nearest PRIOR date for a ticker missing today — misrepresenting a stale value
    # as current and scoring it as if the engine's rising-hold path had applied to it.
    today, prior = date(2026, 8, 4), date(2026, 8, 3)

    async def _departures(conn, t, p):
        return [{"name": "Some Theme", "ticker": "GHOST", "prior_member_count": 5,
                 "moved_today": False}]

    async def _rs_on_date(conn, tickers, d):
        return {}  # GHOST has NO row for exactly `today` — dropped out of the RS universe

    async def _rs_batch(tickers, asof, days=6):
        # get_recent_rs_batch would still return a (stale, 3-sessions-old) rising-looking
        # history — the exact trap the exact-date fix closes.
        return {"GHOST": [8.0, 2.0, 2.0, 2.0]}

    monkeypatch.setattr(health_checks, "get_theme_member_departures", _departures)
    monkeypatch.setattr(health_checks, "get_rs_on_date", _rs_on_date)
    monkeypatch.setattr(health_checks, "get_recent_rs_batch", _rs_batch)

    result = await _check_pruned_while_rising(conn=object(), today=today, prior_date=prior)

    assert result["flags"] == [], "a ticker missing today's RS snapshot is a different engine path"


# ── Integration: run_theme_quality_check end-to-end (db.py layer monkeypatched) ──────────────────


@pytest.fixture
def _captured_telegram(monkeypatch):
    sent: list[str] = []

    async def _send(text, *a, **k):
        sent.append(text)
        return True

    import agents.market_intelligence.briefing as briefing
    monkeypatch.setattr(briefing, "send_telegram_message", _send)
    return sent


@pytest.fixture
def _captured_audit(monkeypatch):
    events: list[tuple] = []

    async def _audit(event_type, summary, detail=""):
        events.append((event_type, summary, detail))

    monkeypatch.setattr(health_checks, "log_audit_event", _audit)
    return events


def _wire_signature_a(monkeypatch, names, history_by_name, alerted=frozenset()):
    async def _names(conn, start, end):
        return names

    async def _history(conn, names_, asof, lookback_days=7):
        return history_by_name

    async def _alerted(conn, event_type):
        return set(alerted)

    monkeypatch.setattr(health_checks, "get_theme_retired_candidate_names", _names)
    monkeypatch.setattr(health_checks, "get_theme_history_window", _history)
    monkeypatch.setattr(health_checks, "get_theme_quality_alerted_targets", _alerted)


def _wire_signature_b_empty(monkeypatch):
    async def _dates(conn=None):
        return None
    monkeypatch.setattr(health_checks, "get_latest_two_theme_dates", _dates)


def _wire_signature_a_empty(monkeypatch):
    async def _names(conn, start, end):
        return []
    monkeypatch.setattr(health_checks, "get_theme_retired_candidate_names", _names)


def _wire_rs(monkeypatch, hist_by_ticker: dict[str, list[float]]):
    """Wires both RS reads signature B needs: get_rs_on_date (exact-today value — the
    stale-value bug fix) and get_recent_rs_batch (the 6-session trajectory). Uses hist[0] as
    the exact-today value, matching the real relationship (get_recent_rs_batch's hist[0] IS
    today's exact row whenever one exists — the two must never disagree in a test double)."""
    async def _rs_on_date(conn, tickers, d):
        return {tk: h[0] for tk, h in hist_by_ticker.items() if tk in tickers and h}

    async def _rs_batch(tickers, asof, days=6):
        return {tk: h for tk, h in hist_by_ticker.items() if tk in tickers}

    monkeypatch.setattr(health_checks, "get_rs_on_date", _rs_on_date)
    monkeypatch.setattr(health_checks, "get_recent_rs_batch", _rs_batch)


@pytest.mark.asyncio
async def test_retirement_flag_fires_telegram_and_audit(_captured_telegram, _captured_audit, monkeypatch):
    today = date(2026, 8, 4)
    _wire_signature_a(
        monkeypatch,
        names=["Bitcoin Mining & Crypto Infrastructure Operators"],
        history_by_name={
            "Bitcoin Mining & Crypto Infrastructure Operators": [
                {"theme_date": date(2026, 8, 3), "stage": "Fading", "rs_avg": 84.9, "score": 72.5},
            ]
        },
    )
    _wire_signature_b_empty(monkeypatch)
    monkeypatch.setattr(health_checks, "et_today", lambda: today)

    summary = await run_theme_quality_check(conn=object())

    assert len(summary["retired_while_healthy"]) == 1
    assert summary["retired_while_healthy"][0]["name"] == "Bitcoin Mining & Crypto Infrastructure Operators"
    assert len(_captured_telegram) == 1
    assert "Bitcoin Mining" in _captured_telegram[0]
    assert "THEME QUALITY" in _captured_telegram[0]
    assert any(e[0] == "theme_retired_while_healthy" for e in _captured_audit)


@pytest.mark.asyncio
async def test_prune_flag_fires_telegram_and_audit(_captured_telegram, _captured_audit, monkeypatch):
    today = date(2026, 8, 4)
    prior = date(2026, 8, 3)
    _wire_signature_a_empty(monkeypatch)

    async def _dates(conn=None):
        return (today, prior)

    async def _departures(conn, t, p):
        return [
            {"name": "AI Compute & GPU Data Center Hosting Operators", "ticker": "IREN",
             "prior_member_count": 4, "moved_today": False},
        ]

    async def _alerted(conn, event_type):
        return set()

    monkeypatch.setattr(health_checks, "get_latest_two_theme_dates", _dates)
    monkeypatch.setattr(health_checks, "get_theme_member_departures", _departures)
    _wire_rs(monkeypatch, {"IREN": [10.7, 7.4, 6.0, 1.5, 1.7, 2.4]})
    monkeypatch.setattr(health_checks, "get_theme_quality_alerted_targets", _alerted)
    monkeypatch.setattr(health_checks, "et_today", lambda: today)

    summary = await run_theme_quality_check(conn=object())

    assert len(summary["pruned_while_rising"]) == 1
    assert summary["pruned_while_rising"][0]["ticker"] == "IREN"
    assert len(_captured_telegram) == 1
    assert "IREN" in _captured_telegram[0]
    assert any(e[0] == "theme_member_pruned_while_rising" for e in _captured_audit)


@pytest.mark.asyncio
async def test_clean_run_is_audit_only_no_telegram(_captured_telegram, _captured_audit, monkeypatch):
    _wire_signature_a_empty(monkeypatch)
    _wire_signature_b_empty(monkeypatch)
    monkeypatch.setattr(health_checks, "et_today", lambda: date(2026, 8, 4))

    summary = await run_theme_quality_check(conn=object())

    assert summary["retired_while_healthy"] == []
    assert summary["pruned_while_rising"] == []
    assert _captured_telegram == []  # Telegram reserved for real findings
    assert any(e[0] == "theme_quality_clean" for e in _captured_audit)


@pytest.mark.asyncio
async def test_dedupe_suppresses_an_already_announced_retirement(_captured_telegram, _captured_audit, monkeypatch):
    # The condition persists (the theme_retired audit event re-fires for days) but the finding
    # must not become nightly wallpaper — already-announced names are dropped before alerting.
    today = date(2026, 8, 4)
    _wire_signature_a(
        monkeypatch,
        names=["Bitcoin Mining & Crypto Infrastructure Operators"],
        history_by_name={
            "Bitcoin Mining & Crypto Infrastructure Operators": [
                {"theme_date": date(2026, 8, 3), "stage": "Fading", "rs_avg": 84.9, "score": 72.5},
            ]
        },
        alerted={"Bitcoin Mining & Crypto Infrastructure Operators"},
    )
    _wire_signature_b_empty(monkeypatch)
    monkeypatch.setattr(health_checks, "et_today", lambda: today)

    summary = await run_theme_quality_check(conn=object())

    assert summary["retired_while_healthy"] == []
    assert _captured_telegram == []
    assert not any(e[0] == "theme_retired_while_healthy" for e in _captured_audit)
    assert any(e[0] == "theme_quality_clean" for e in _captured_audit)


@pytest.mark.asyncio
async def test_dedupe_read_failure_fails_open_and_re_announces(_captured_telegram, _captured_audit, monkeypatch, caplog):
    # If the dedupe read itself breaks, the cost must be a duplicate alert — never a silently
    # missed one. Mirrors run_inert_sweep_check's fail-open discipline exactly.
    today = date(2026, 8, 4)
    _wire_signature_a(
        monkeypatch,
        names=["Bitcoin Mining & Crypto Infrastructure Operators"],
        history_by_name={
            "Bitcoin Mining & Crypto Infrastructure Operators": [
                {"theme_date": date(2026, 8, 3), "stage": "Fading", "rs_avg": 84.9, "score": 72.5},
            ]
        },
    )
    _wire_signature_b_empty(monkeypatch)
    monkeypatch.setattr(health_checks, "et_today", lambda: today)

    async def _broken_alerted(conn, event_type):
        raise RuntimeError("connection reset")

    monkeypatch.setattr(health_checks, "get_theme_quality_alerted_targets", _broken_alerted)

    with caplog.at_level("WARNING"):
        summary = await run_theme_quality_check(conn=object())

    assert len(summary["retired_while_healthy"]) == 1  # re-announced, not dropped
    assert len(_captured_telegram) == 1
    assert "will re-announce" in caplog.text


@pytest.mark.asyncio
async def test_one_signature_failing_does_not_blind_the_other(_captured_telegram, _captured_audit, monkeypatch):
    today = date(2026, 8, 4)

    async def _broken_names(conn, start, end):
        raise RuntimeError("boom")

    monkeypatch.setattr(health_checks, "get_theme_retired_candidate_names", _broken_names)

    prior = date(2026, 8, 3)

    async def _dates(conn=None):
        return (today, prior)

    async def _departures(conn, t, p):
        return [
            {"name": "AI Compute & GPU Data Center Hosting Operators", "ticker": "IREN",
             "prior_member_count": 4, "moved_today": False},
        ]

    async def _alerted(conn, event_type):
        return set()

    monkeypatch.setattr(health_checks, "get_latest_two_theme_dates", _dates)
    monkeypatch.setattr(health_checks, "get_theme_member_departures", _departures)
    _wire_rs(monkeypatch, {"IREN": [10.7, 7.4, 6.0, 1.5, 1.7, 2.4]})
    monkeypatch.setattr(health_checks, "get_theme_quality_alerted_targets", _alerted)
    monkeypatch.setattr(health_checks, "et_today", lambda: today)

    summary = await run_theme_quality_check(conn=object())

    # Signature A blew up — recorded as an error, no flags — but signature B still ran clean.
    assert summary["retired_while_healthy"] == []
    assert any(e.get("signature") == "retired_while_healthy" for e in summary["errors"])
    assert len(summary["pruned_while_rising"]) == 1


@pytest.mark.asyncio
async def test_fewer_than_two_theme_dates_is_skipped_not_flagged(monkeypatch, _captured_telegram, _captured_audit):
    # A missing/thin table must be SKIPPED with a distinct reason, never reported as a defect.
    _wire_signature_a_empty(monkeypatch)
    _wire_signature_b_empty(monkeypatch)  # returns None -> "fewer than 2 distinct ... skip"
    monkeypatch.setattr(health_checks, "et_today", lambda: date(2026, 8, 4))

    summary = await run_theme_quality_check(conn=object())

    assert summary["pruned_while_rising"] == []
    assert any("fewer than 2" in e.get("error", "") for e in summary["errors"])
    assert _captured_telegram == []  # a skip is not a defect — no alert


# ── Wiring ─────────────────────────────────────────────────────────────────────────────────────


def test_it_is_wired_into_the_nightly_audit_and_alerts():
    sched = open("agents/market_intelligence/scheduler.py").read()
    assert "run_theme_quality_check" in sched
    i = sched.index("run_theme_quality_check")
    block = sched[i:i + 1500]
    assert "notify_job_failure" in block, "a health guard that dies silently is the failure it exists to prevent"


def test_dedupe_lives_in_db_py_and_fails_open_with_the_established_idiom():
    dbsrc = open("agents/market_intelligence/db.py").read()
    assert "get_theme_quality_alerted_targets" in dbsrc
    i = dbsrc.index("async def get_theme_quality_alerted_targets")
    block = dbsrc[i:i + 700]
    assert "SELECT DISTINCT" in block and "split_part" in block

    hcsrc = open("agents/market_intelligence/health_checks.py").read()
    assert "will re-announce" in hcsrc


def test_findings_persist_forever_once_announced_no_resolve_path():
    # Each finding is a discrete past event (a specific retirement, a specific prune) — unlike
    # increment 2's null/job-liveness reconcile, there is deliberately no "resolved" status here.
    hcsrc = open("agents/market_intelligence/health_checks.py").read()
    i = hcsrc.index("async def run_theme_quality_check")
    block = hcsrc[i:i + 6000]
    assert "reconcile_health_flags" not in block
