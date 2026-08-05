"""#534 D3(b) ECOSYSTEM REACTIVATION detector (2026-08-05) — deterministic, $0, no-LLM.

WHY THIS EXISTS. Operator, 2026-08-04, on the duplicate defense themes: "multiple defense stocks
moving and having EP around the same time, this might be indicator that this group is coming back
alive after a dormant period." On that exact day the signal existed in prod only as five duplicate
births nobody aggregated. This detector is the aggregation: a DORMANT ecosystem (no live theme /
all-Fading at the alert window's start) collecting >= 3 distinct HIGH EP tickers in 5 sessions
against a quiet 15-session trailing baseline.

Thresholds were DERIVED from a 66-session prod replay (2026-05-06..2026-08-05, 324 HIGH ticker-day
alerts) before anything shipped — the distributions, the hand-checked incidents each rejected
setting would have admitted, and the both-ways proof (fires on the defense fixture, silent on the
late-July semis earnings night) live in `agents/market_intelligence/health_checks.py`'s #534
section header. Every fixture below is a REAL measured shape from that replay, not an invention.

Mirrors test_theme_quality_check.py: PURE decisions tested first with zero mocking, then the
orchestrator driven end-to-end with the db.py layer monkeypatched (its SQL was exercised for real
by the replay's capture against prod, not re-proven here).

⚠ THE SAFETY WALL — the one non-negotiable in the #534 brief: the detector NEVER births a theme.
Its seed source 'ecosystem_reactivation' must stay OUT of AUTO_PROMOTE_THEME_SOURCES (the #469
allowlist) and OUT of the judge's active_narratives feed — the birth gate + operator own whether
anything becomes a theme. Pinned below.
"""
from __future__ import annotations

from datetime import date

import pytest

from agents.market_intelligence import health_checks
from agents.market_intelligence.health_checks import (
    _evaluate_ecosystem_reactivation,
    _is_missing_db_object,
    REACT_WINDOW_SESSIONS,
    REACT_BASELINE_SESSIONS,
    REACT_MIN_CLUSTER,
    REACT_MAX_BASELINE,
    _REACT_BOARD_LOOKBACK_DAYS,
    run_ecosystem_reactivation_check,
)


# ── Derived-threshold pins: the values ARE the measurement (see the #534 header) ─────────────────


def test_the_derived_thresholds_are_pinned():
    # Moving any of these re-opens the derivation: K=3 is the measured elbow (pairs are ~10x
    # triples and are Lane-2 / birth-gate territory); Q=1 and B=15 are exactly what separated
    # the defense wake-up (baseline 0) from the ARM+LRCX+SIMO earnings night (baseline 2).
    assert REACT_WINDOW_SESSIONS == 5
    assert REACT_BASELINE_SESSIONS == 15
    assert REACT_MIN_CLUSTER == 3
    assert REACT_MAX_BASELINE == 1


def test_board_lookback_mirrors_the_engines_own_liveness_horizon():
    # Dormancy uses get_active_themes' stale_after_days=7 — the engine's own definition of
    # "still the same lifecycle". If the engine's default ever moves without this mirror
    # following, the detector silently drifts out of sync with what it's judging.
    import inspect
    from agents.market_intelligence.db import get_active_themes
    default = inspect.signature(get_active_themes).parameters["stale_after_days"].default
    assert _REACT_BOARD_LOOKBACK_DAYS == default


# ── Pure decision: _evaluate_ecosystem_reactivation (zero mocking, real replay shapes) ───────────


def test_fires_on_the_defense_fixture_shape():
    # THE acceptance case (2026-08-04/05): PLTR TSAT VOYG AMRC alert 08-04 (KTOS follows 08-05),
    # E-DEF's board at window-start 07-29 was two Fading themes, baseline 0 in the prior 15
    # sessions. Exact values from the replay: 4 mapped tickers, dormant, quiet -> MUST fire.
    flags = _evaluate_ecosystem_reactivation(
        window_by_eco={"E-DEF": {"AMRC", "PLTR", "TSAT", "VOYG"}},
        baseline_by_eco={},
        live_stages_by_eco={"E-DEF": {
            "Defense Prime Contractors & Aerospace Systems": "Fading",
            "Defense Precision Components & Mission-Critical Subsystems": "Fading",
        }},
        window_dates_by_eco={"E-DEF": {date(2026, 8, 4)}},
    )
    assert len(flags) == 1, "a dormant ecosystem with a 4-ticker cluster and quiet baseline MUST fire"
    f = flags[0]
    assert f["e_code"] == "E-DEF"
    assert f["tickers"] == ["AMRC", "PLTR", "TSAT", "VOYG"]
    assert f["n_baseline"] == 0
    assert f["fading_themes"]  # dormant-via-all-Fading, not via empty board


def test_silent_on_the_semis_earnings_night_shape():
    # THE confounder (§5's "an earnings surge is not a theme"): ARM+LRCX+SIMO all reported
    # earnings the same night (07-30) into an all-Fading E-AISEMI — cluster 3, dormant, BUT the
    # trailing baseline held AEHR+TSEM (2 > Q=1). The quiet precondition is what separates a
    # wake-up from a broad earnings week — this exact prod shape must stay silent.
    flags = _evaluate_ecosystem_reactivation(
        window_by_eco={"E-AISEMI": {"ARM", "LRCX", "SIMO"}},
        baseline_by_eco={"E-AISEMI": {"AEHR", "TSEM"}},
        live_stages_by_eco={"E-AISEMI": {"Semiconductor Test & Measurement": "Fading"}},
    )
    assert flags == [], "a noisy trailing baseline means momentum, not a wake-up — no fire"


def test_silent_on_a_pair():
    # K=2 would have admitted QBTS+RGTI (05-21), DDOG+FTNT (05-07), HUT+IREN (07-20) — pairs
    # are Lane-2's 2-member same-day anchor / the birth gate's two-sighting arm territory,
    # ~10x more common than triples in the measured distribution. A pair must not fire here.
    flags = _evaluate_ecosystem_reactivation(
        window_by_eco={"E-QUANTUM": {"QBTS", "RGTI"}},
        baseline_by_eco={"E-QUANTUM": {"QUBT"}},
        live_stages_by_eco={},
    )
    assert flags == []


def test_silent_when_a_live_non_fading_theme_exists_at_window_start():
    # The late-July "Technology cluster of 14" names that DID map, mapped into LIVE ecosystems
    # (E-AIINFRA/E-SAAS with Nascent/Accelerating themes) — an awake ecosystem collecting
    # alerts is normal life, not a reactivation.
    flags = _evaluate_ecosystem_reactivation(
        window_by_eco={"E-AIINFRA": {"SMCI", "CORZ", "MPWR"}},
        baseline_by_eco={},
        live_stages_by_eco={"E-AIINFRA": {
            "AI Data Center Power Infrastructure": "Accelerating",
            "GPU Cloud Compute": "Fading",
        }},
    )
    assert flags == []


def test_fires_when_the_ecosystem_has_no_live_theme_at_all():
    # Dormancy's other branch: an EMPTY board (every lineage theme Retired / aged out) — the
    # "no live theme" wording of the operator line.
    flags = _evaluate_ecosystem_reactivation(
        window_by_eco={"E-CRYPTO": {"HUT", "IREN", "CLSK"}},
        baseline_by_eco={"E-CRYPTO": {"WULF"}},  # exactly Q=1 — quiet, inclusive bound
        live_stages_by_eco={},
    )
    assert len(flags) == 1
    assert flags[0]["fading_themes"] == []  # renders as "no live theme"


def test_deterministic_order_across_multiple_firings():
    flags = _evaluate_ecosystem_reactivation(
        window_by_eco={"E-DEF": {"A", "B", "C"}, "E-CRYPTO": {"X", "Y", "Z"}},
        baseline_by_eco={},
        live_stages_by_eco={},
    )
    assert [f["e_code"] for f in flags] == ["E-CRYPTO", "E-DEF"]


# ── _is_missing_db_object: skip-not-flag discrimination ─────────────────────────────────────────


def test_missing_relation_is_recognized_by_name_and_message():
    class UndefinedTableError(Exception):
        pass

    assert _is_missing_db_object(UndefinedTableError("boom"))
    assert _is_missing_db_object(RuntimeError('relation "mi_theme_ecosystems" does not exist'))
    assert not _is_missing_db_object(RuntimeError("connection reset"))


# ── Orchestrator end-to-end (db.py layer monkeypatched) ─────────────────────────────────────────

TODAY = date(2026, 8, 4)
# 20 real sessions ending 08-04 (the replay's spine: score_dates ∪ HIGH alert dates).
SESSIONS = [
    date(2026, 7, 7), date(2026, 7, 8), date(2026, 7, 9), date(2026, 7, 10),
    date(2026, 7, 13), date(2026, 7, 14), date(2026, 7, 15), date(2026, 7, 16),
    date(2026, 7, 17), date(2026, 7, 20), date(2026, 7, 21), date(2026, 7, 22),
    date(2026, 7, 23), date(2026, 7, 24), date(2026, 7, 27), date(2026, 7, 28),
    date(2026, 7, 29), date(2026, 7, 30), date(2026, 7, 31), date(2026, 8, 3),
    date(2026, 8, 4),
][1:]  # exactly 20


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


@pytest.fixture
def _captured_seeds(monkeypatch):
    seeds: list[tuple] = []

    async def _seed(run_date, e_code, tickers, thesis):
        seeds.append((run_date, e_code, tickers, thesis))

    monkeypatch.setattr(health_checks, "persist_reactivation_seed", _seed)
    return seeds


def _wire_defense_fixture(monkeypatch, alerted=frozenset()):
    """The real 08-04 prod shape end-to-end: 4 defense alerts on 08-04, one WULF
    baseline alert mapped to E-CRYPTO only, all-Fading E-DEF board at window-start."""
    async def _sessions(conn, asof, n):
        return SESSIONS

    async def _alerts(conn, start, end):
        return ([{"alert_date": date(2026, 8, 4), "ticker": tk}
                 for tk in ["PLTR", "TSAT", "VOYG", "AMRC"]]
                + [{"alert_date": date(2026, 7, 6), "ticker": "WULF"}])

    async def _membership(conn, tickers, asof):
        # The engine's same-night births are the mapping path (measured: strictly-prior
        # membership maps NONE of these — the dead defense themes never held them).
        return {"PLTR": ["E-DEF"], "TSAT": ["E-DEF"], "VOYG": ["E-DEF"],
                "AMRC": ["E-DEF", "E-SAAS"], "WULF": ["E-CRYPTO"]}

    async def _board(conn, cutoff, lookback_days=7):
        assert cutoff == date(2026, 7, 29), "dormancy must be judged at WINDOW START, not today"
        return [
            {"e_code": "E-DEF", "name": "Defense Prime Contractors & Aerospace Systems",
             "stage": "Fading"},
            {"e_code": "E-DEF", "name": "Defense Precision Components & Mission-Critical Subsystems",
             "stage": "Fading"},
            {"e_code": "E-SAAS", "name": "Cloud Data Storage & Analytics Infrastructure",
             "stage": "Accelerating"},
        ]

    async def _alerted(conn, days=10):
        return set(alerted)

    monkeypatch.setattr(health_checks, "get_reactivation_sessions", _sessions)
    monkeypatch.setattr(health_checks, "get_high_ep_ticker_days", _alerts)
    monkeypatch.setattr(health_checks, "get_ticker_ecosystem_membership", _membership)
    monkeypatch.setattr(health_checks, "get_mapped_theme_stages_before", _board)
    monkeypatch.setattr(health_checks, "get_reactivation_alerted_ecosystems", _alerted)
    monkeypatch.setattr(health_checks, "et_today", lambda: TODAY)


@pytest.mark.asyncio
async def test_defense_fixture_fires_telegram_audit_and_seed(
        _captured_telegram, _captured_audit, _captured_seeds, monkeypatch):
    _wire_defense_fixture(monkeypatch)

    summary = await run_ecosystem_reactivation_check(conn=object())

    assert len(summary["flags"]) == 1
    f = summary["flags"][0]
    assert f["e_code"] == "E-DEF"
    assert f["tickers"] == ["AMRC", "PLTR", "TSAT", "VOYG"]
    # AMRC's second home (E-SAAS, Accelerating board) must NOT fire — awake ecosystem.
    assert all(fl["e_code"] != "E-SAAS" for fl in summary["flags"])

    assert len(_captured_telegram) == 1
    assert "ECOSYSTEM REACTIVATION" in _captured_telegram[0]
    assert "E-DEF" in _captured_telegram[0]
    assert "EPs/1d" in _captured_telegram[0]  # the design's operator-line shape "N EPs/Kd"

    assert any(e[0] == "ecosystem_reactivation" and e[1].startswith("E-DEF:")
               for e in _captured_audit)

    assert len(_captured_seeds) == 1
    run_date, e_code, tickers, thesis = _captured_seeds[0]
    assert e_code == "E-DEF"
    assert tickers == ["AMRC", "PLTR", "TSAT", "VOYG"]
    assert "dormant lineage" in thesis  # historical members ride in the thesis


@pytest.mark.asyncio
async def test_clean_run_is_audit_only_no_telegram_no_seed(
        _captured_telegram, _captured_audit, _captured_seeds, monkeypatch):
    _wire_defense_fixture(monkeypatch)

    async def _no_alerts(conn, start, end):
        return []

    monkeypatch.setattr(health_checks, "get_high_ep_ticker_days", _no_alerts)

    summary = await run_ecosystem_reactivation_check(conn=object())

    assert summary["flags"] == []
    assert _captured_telegram == []
    assert _captured_seeds == []
    assert any(e[0] == "ecosystem_reactivation_clean" for e in _captured_audit)


@pytest.mark.asyncio
async def test_dedupe_suppresses_a_recently_announced_incident(
        _captured_telegram, _captured_audit, _captured_seeds, monkeypatch):
    # One incident sustains ~4 fire-days (measured) — night two must not re-announce.
    _wire_defense_fixture(monkeypatch, alerted={"E-DEF"})

    summary = await run_ecosystem_reactivation_check(conn=object())

    assert summary["flags"] == []
    assert _captured_telegram == []
    assert _captured_seeds == []
    assert any(e[0] == "ecosystem_reactivation_clean" for e in _captured_audit)


@pytest.mark.asyncio
async def test_dedupe_read_failure_fails_open_and_re_announces(
        _captured_telegram, _captured_audit, _captured_seeds, monkeypatch, caplog):
    _wire_defense_fixture(monkeypatch)

    async def _broken(conn, days=10):
        raise RuntimeError("connection reset")

    monkeypatch.setattr(health_checks, "get_reactivation_alerted_ecosystems", _broken)

    with caplog.at_level("WARNING"):
        summary = await run_ecosystem_reactivation_check(conn=object())

    assert len(summary["flags"]) == 1  # re-announced, not dropped
    assert len(_captured_telegram) == 1
    assert "will re-announce" in caplog.text


@pytest.mark.asyncio
async def test_seed_write_failure_does_not_cost_the_alert(
        _captured_telegram, _captured_audit, monkeypatch, caplog):
    # The seed is the SECONDARY output; the operator line is the primary one. A broken
    # shadow-table write must be recorded as an error, never swallow the Telegram.
    _wire_defense_fixture(monkeypatch)

    async def _broken_seed(run_date, e_code, tickers, thesis):
        raise RuntimeError("shadow table locked")

    monkeypatch.setattr(health_checks, "persist_reactivation_seed", _broken_seed)

    with caplog.at_level("WARNING"):
        summary = await run_ecosystem_reactivation_check(conn=object())

    assert len(_captured_telegram) == 1
    assert any(e.get("stage") == "seed" for e in summary["errors"])


@pytest.mark.asyncio
async def test_too_few_sessions_is_skipped_not_flagged(
        _captured_telegram, _captured_audit, _captured_seeds, monkeypatch):
    # A thin table must be SKIPPED with a distinct reason, never reported as a finding.
    _wire_defense_fixture(monkeypatch)

    async def _thin(conn, asof, n):
        return SESSIONS[:8]

    monkeypatch.setattr(health_checks, "get_reactivation_sessions", _thin)

    summary = await run_ecosystem_reactivation_check(conn=object())

    assert summary["flags"] == []
    assert any("sessions in the data" in s for s in summary["skipped"])
    assert _captured_telegram == []


@pytest.mark.asyncio
async def test_missing_table_is_skipped_with_a_distinct_reason(
        _captured_telegram, _captured_audit, _captured_seeds, monkeypatch):
    _wire_defense_fixture(monkeypatch)

    class UndefinedTableError(Exception):
        pass

    async def _missing(conn, tickers, asof):
        raise UndefinedTableError('relation "mi_theme_ecosystems" does not exist')

    monkeypatch.setattr(health_checks, "get_ticker_ecosystem_membership", _missing)

    summary = await run_ecosystem_reactivation_check(conn=object())

    assert summary["flags"] == []
    assert any("missing table/column" in s for s in summary["skipped"])
    assert summary["errors"] == []  # a skip is not an error
    assert _captured_telegram == []


@pytest.mark.asyncio
async def test_taxonomy_load_failure_degrades_to_membership_only(
        _captured_telegram, _captured_audit, _captured_seeds, monkeypatch):
    # The exemplar fallback rides on theme_ecosystems.yaml; a broken loader must degrade the
    # MAPPING, never kill the check (the membership path alone reproduces the fixture).
    _wire_defense_fixture(monkeypatch)

    def _broken_taxonomy():
        raise RuntimeError("yaml exploded")

    import agents.market_intelligence.theme_ecosystems as te
    monkeypatch.setattr(te, "get_ecosystems", _broken_taxonomy)

    summary = await run_ecosystem_reactivation_check(conn=object())

    assert len(summary["flags"]) == 1
    assert summary["flags"][0]["e_code"] == "E-DEF"


# ── THE SAFETY WALL — never an auto-promote (the whole safety story, pinned) ────────────────────


def test_reactivation_source_is_excluded_from_the_auto_promote_allowlist():
    # #469: AUTO_PROMOTE_THEME_SOURCES is an ALLOWLIST — a source not named there can NEVER
    # graduate into live mi_themes via promote_shadow_themes. The reactivation seed must stay
    # out: the birth gate + operator own whether a reactivation cohort becomes a theme.
    from agents.market_intelligence.db import AUTO_PROMOTE_THEME_SOURCES
    assert "ecosystem_reactivation" not in AUTO_PROMOTE_THEME_SOURCES


def test_reactivation_source_never_feeds_the_judges_narrative_context():
    # get_narrative_theme_candidates feeds the judge's own active_narratives input — its
    # source IN-list is the anti-circularity wall. The reactivation seed must not be there.
    import inspect
    from agents.market_intelligence import db as dbmod
    src = inspect.getsource(dbmod.get_narrative_theme_candidates)
    assert "ecosystem_reactivation" not in src


def test_seed_writer_uses_the_source_guarded_upsert_and_never_touches_mi_themes():
    import inspect
    from agents.market_intelligence import db as dbmod
    src = inspect.getsource(dbmod.persist_reactivation_seed)
    assert "_upsert_theme_candidate_shadow" in src  # the sibling lanes' guarded conflict path
    assert "ecosystem_reactivation" in src
    for verb in ("INSERT INTO mi_themes", "UPDATE mi_themes", "DELETE FROM mi_themes"):
        assert verb not in src


def test_detector_module_never_writes_mi_themes():
    # The whole detector is a read-model + one shadow-lane seed: nothing in the new #534
    # section may INSERT/UPDATE/DELETE mi_themes rows.
    hcsrc = open("agents/market_intelligence/health_checks.py").read()
    section = hcsrc[hcsrc.index("#534 D3(b)"):]
    for verb in ("INSERT INTO mi_themes", "UPDATE mi_themes", "DELETE FROM mi_themes"):
        assert verb not in section


# ── Wiring ──────────────────────────────────────────────────────────────────────────────────────


def test_it_is_wired_into_the_nightly_audit_and_alerts():
    sched = open("agents/market_intelligence/scheduler.py").read()
    assert "run_ecosystem_reactivation_check" in sched
    i = sched.index("run_ecosystem_reactivation_check")
    block = sched[i:i + 1500]
    assert "notify_job_failure" in block, "a health guard that dies silently is the failure it exists to prevent"


def test_dedupe_lives_in_db_py_recency_bounded_with_the_established_idiom():
    dbsrc = open("agents/market_intelligence/db.py").read()
    assert "get_reactivation_alerted_ecosystems" in dbsrc
    i = dbsrc.index("async def get_reactivation_alerted_ecosystems")
    block = dbsrc[i:i + 900]
    assert "SELECT DISTINCT" in block and "split_part" in block
    # RECENCY-bounded (unlike theme-quality's forever-set): an ecosystem can wake again
    # months later; TIMESTAMPTZ interval arithmetic, never a bare ::date cast.
    assert "NOW() -" in block
    assert "::date cast" in block or "created_at >=" in block

    hcsrc = open("agents/market_intelligence/health_checks.py").read()
    assert "will re-announce" in hcsrc
