"""#533 Change 6 — catalyst-tier SHADOW grader tests (2026-08-22).

Pure lattice + marker/sector functions, the DB write half (mocked pool — the #173
0-rows lesson), and THE LINE pins: the writer inserts ONLY into
mi_catalyst_tier_shadow, and `shadow_retier` takes no gap/price/score argument
(operator correction 2026-08-22 — surprise must never proxy the subject's own
price reaction). Every assertion checks a computed VALUE.
"""
import asyncio
import inspect
import sys
from datetime import date, datetime
from pathlib import Path
from unittest.mock import AsyncMock

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from agents.market_intelligence import catalyst_tier_shadow as cts


# ── shadow_retier: the lattice ────────────────────────────────────────────────────────


def _retier(q, sched="unknown", combined="unclassified", beat=False,
            demo=False, concrete=False, sconf=False):
    return cts.shadow_retier(q, sched, combined, beat, demo, concrete, sconf)


def test_mna_passes_through_untouched():
    assert _retier("mna") == ("mna", "mna_passthrough")


def test_scheduled_gc_without_content_delta_demotes_one_step():
    """The FP mechanism under repair: a scheduled earnings recap graded game_changer on
    FORM (backward-looking, no beat-vs-consensus language) drops to strong."""
    tier, rule = _retier("game_changer", sched="scheduled", combined="backward", beat=False)
    assert tier == "strong" and rule == "gc_demoted_scheduled_no_content_delta"


def test_scheduled_gc_with_beat_and_forward_is_kept_peg_class():
    """Operator correction 1 (the PEG family): scheduled calendar + unexpected CONTENT
    (beat + forward guidance change) keeps the top tier — INTC 04-24 class."""
    tier, rule = _retier("game_changer", sched="scheduled", combined="forward", beat=True)
    assert tier == "game_changer" and rule == "gc_kept_scheduled_content_delta"


def test_scheduled_gc_with_forward_but_no_beat_demotes():
    """Content delta needs BOTH halves for a scheduled event — forward words alone
    (contract/partnership vocabulary fires on wires constantly) are not consensus delta."""
    assert _retier("game_changer", sched="scheduled", combined="forward", beat=False)[0] == "strong"


def test_unscheduled_gc_needs_forward_content():
    assert _retier("game_changer", sched="unscheduled", combined="forward")[0] == "game_changer"
    tier, rule = _retier("game_changer", sched="unscheduled", combined="unclassified")
    assert tier == "strong" and rule == "gc_demoted_unscheduled_no_forward"


def test_unknown_calendar_keeps_gc_fail_open():
    """No calendar lane at all -> no lane to judge in -> the tier is KEPT (fail-open on
    wholly-missing data; the demotions above require a KNOWN lane + absent evidence)."""
    tier, rule = _retier("game_changer", sched="unknown")
    assert tier == "game_changer" and rule == "gc_kept_unknown_failopen"


def test_strong_promotes_only_on_unscheduled_forward_with_group_repricing():
    """The MRNA 08-19 class: own unscheduled forward event AND the sector moved with it."""
    tier, rule = _retier("strong", sched="unscheduled", combined="forward", sconf=True)
    assert tier == "game_changer" and rule == "strong_promoted_group_repricing"
    # any leg missing -> stays strong
    assert _retier("strong", sched="unscheduled", combined="forward", sconf=False)[0] == "strong"
    assert _retier("strong", sched="scheduled", combined="forward", sconf=True)[0] == "strong"
    assert _retier("strong", sched="unscheduled", combined="backward", sconf=True)[0] == "strong"


def test_strong_is_never_demoted():
    for sched in ("scheduled", "unscheduled", "unknown"):
        assert _retier("strong", sched=sched, combined="backward")[0] == "strong"


def test_routine_corrective_needs_marker_and_concrete_event():
    """Rule-4 sector-demotion corrective: promoted ONE step (never straight to the top)."""
    tier, rule = _retier("routine", demo=True, concrete=True)
    assert tier == "strong" and rule == "routine_promoted_demotion_corrective"
    assert _retier("routine", demo=True, concrete=False)[0] == "routine"
    assert _retier("routine", demo=False, concrete=True)[0] == "routine"


def test_routine_never_reaches_game_changer_in_one_pass():
    """One-step moves only — pinned across the whole input product for routine."""
    for sched in ("scheduled", "unscheduled", "unknown"):
        for combined in ("forward", "backward", "unclassified"):
            for beat in (False, True):
                for sconf in (False, True):
                    tier, _ = cts.shadow_retier("routine", sched, combined, beat,
                                                True, True, sconf)
                    assert tier != "game_changer"


def test_shadow_retier_takes_no_price_input():
    """Operator correction 2 (2026-08-22): surprise must not collapse into a proxy for
    the subject's own gap/price reaction. Pinned structurally — the signature carries no
    gap/price/score/reaction parameter."""
    params = set(inspect.signature(cts.shadow_retier).parameters)
    forbidden = {"gap", "gap_pct", "price", "score", "ep_score", "reaction",
                 "gap_read", "pct_change", "rel_volume"}
    assert params & forbidden == set()


def test_unknown_live_grade_passes_through_visibly():
    tier, rule = _retier("weird_grade")
    assert tier == "weird_grade" and rule == "unknown_live_grade_passthrough"


# ── markers ───────────────────────────────────────────────────────────────────────────


def test_demotion_marker_matches_rule4_vocabulary():
    assert cts.detect_demotion_marker(
        "Gap appears driven by broad sector momentum with no company-specific catalyst.", None)
    assert cts.detect_demotion_marker("Stock is rising in sympathy with NVDA's report.", None)
    assert not cts.detect_demotion_marker(
        "Company reported record Q2 revenue and raised full-year guidance.", None)
    assert not cts.detect_demotion_marker(None, None)


def test_concrete_event_reads_sec_stamp_and_event_words():
    assert cts.detect_concrete_event(None, "[SEC 8-K filed 2026-08-19, items 8.01] body")
    assert cts.detect_concrete_event("Phase 3 trial met its primary endpoint.", None)
    assert not cts.detect_concrete_event("Momentum continuation, no news found.", None)
    assert not cts.detect_concrete_event(None, None)


# ── sector follow-through ─────────────────────────────────────────────────────────────


def test_sector_follow_through_counts_exclude_self_and_gate_on_share():
    board = {"MRNA": "Healthcare", "TWST": "Healthcare", "A1": "Healthcare",
             "A2": "Healthcare", "A3": "Healthcare", "T1": "Technology",
             "T2": "Technology", "T3": "Technology", "T4": "Technology",
             "E1": "Energy", "E2": None}
    r = cts.sector_follow_through(board, "MRNA")
    assert r["sector_n"] == 4                      # 4 OTHER healthcare names
    assert r["board_n"] == 11
    assert r["sector_share"] == pytest.approx(0.4)  # 4/10
    assert r["sector_confirm"] is True             # n>=4 and share>=0.30
    # 3 same-sector -> below the n floor even at high share
    r2 = cts.sector_follow_through({"X": "Energy", "Y": "Energy", "Z": "Energy",
                                    "W": "Energy"}, "X")
    assert r2["sector_n"] == 3 and r2["sector_confirm"] is False


def test_sector_follow_through_missing_sector_is_never_a_confirm():
    r = cts.sector_follow_through({"AAA": None, "BBB": "Tech"}, "AAA")
    assert r["sector"] is None and r["sector_confirm"] is False and r["sector_n"] is None


# ── compute_shadow_verdict — end-to-end pure path (real classifier, no DB/LLM) ────────


def test_mrna_case_end_to_end_promotes_to_game_changer():
    """The reference EP, replayed through the REAL classifier on its recorded corpus
    excerpt: unscheduled (no earnings keywords) + forward (phase-3/approval vocabulary)
    + sector confirm -> strong promotes to game_changer."""
    gtext = ("[Benzinga 2026-08-19] Merck And Moderna Announce Topline Results From The "
             "Phase 3 Interpath-001 Trial; intismeran in combination with KEYTRUDA "
             "demonstrated statistically significant improvements. "
             "[Web summary] The FDA's approval of Moderna's first mRNA flu vaccine gave "
             "the stock a fresh regulatory catalyst.")
    board = {"MRNA": "Healthcare", "TWST": "Healthcare", "B1": "Healthcare",
             "B2": "Healthcare", "B3": "Healthcare", "C1": "Technology",
             "C2": None, "C3": "Energy"}
    v = cts.compute_shadow_verdict(
        ticker="MRNA", live_quality="strong",
        claude_analysis="Positive Phase 3 readout for the personalized cancer vaccine.",
        grounded_text=gtext, news_summary="Phase 3 Interpath-001 topline results",
        sector_by_ticker=board)
    assert v["expct_sched"] == "unscheduled"
    assert v["expct_combined"] == "forward"
    assert v["sector_confirm"] is True
    assert v["shadow_tier"] == "game_changer"
    assert v["rule"] == "strong_promoted_group_repricing"


def test_scheduled_recap_gc_end_to_end_demotes():
    """An in-line earnings recap graded game_changer: scheduled + backward, no beat
    language -> shadow says strong."""
    gtext = ("[SEC 8-K filed 2026-06-02, items 2.02,9.01] The company reported third-quarter "
             "results. Revenue of $120 million was reported for the quarter.")
    v = cts.compute_shadow_verdict(
        ticker="AAAA", live_quality="game_changer",
        claude_analysis="Massive quarterly earnings report.",
        grounded_text=gtext, news_summary="reported earnings", sector_by_ticker={"AAAA": None})
    assert v["expct_sched"] == "scheduled"
    assert v["shadow_tier"] == "strong"


# ── the write half: mocked pool ───────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_record_writes_only_the_shadow_table(monkeypatch):
    """THE LINE pin: the only statement executed is the mi_catalyst_tier_shadow upsert;
    the batch returns the written count and swallows nothing silently on success."""
    from tests.conftest import make_mock_pool
    pool, conn = make_mock_pool()
    executed = []

    async def _execute(sql, *args):
        executed.append((sql, args))
        return "INSERT 0 1"
    conn.execute = _execute
    monkeypatch.setattr(cts, "get_pool", AsyncMock(return_value=pool))
    monkeypatch.setattr(cts, "get_sectors_batch",
                        AsyncMock(return_value={"MRNA": "Healthcare"}))
    n = await cts.record_catalyst_tier_shadow(
        [{"ticker": "MRNA", "live_quality": "strong", "claude_analysis": None,
          "grounded_text": None, "news_summary": None, "gap_pct": 10.0,
          "adv_dollar": 3e8, "rel_volume": 1.5, "projected_vol_multiple": None,
          "ep_score": 21.6, "live_tier": None}],
        ["MRNA", "TWST"], date(2026, 8, 19), datetime(2026, 8, 19, 7, 5))
    assert n == 1
    assert len(executed) == 1
    sql, args = executed[0]
    assert "INSERT INTO mi_catalyst_tier_shadow" in sql
    assert "mi_ep_alerts" not in sql and "mi_live_trades" not in sql
    assert "ON CONFLICT (scan_date, ticker)" in sql
    # regrade_count increments ONLY when the shadow tier changes
    assert "IS DISTINCT FROM EXCLUDED.shadow_tier_last" in sql


@pytest.mark.asyncio
async def test_record_is_fail_open_on_pool_failure(monkeypatch):
    monkeypatch.setattr(cts, "get_pool", AsyncMock(side_effect=RuntimeError("db down")))
    n = await cts.record_catalyst_tier_shadow(
        [{"ticker": "X", "live_quality": "routine"}], ["X"],
        date(2026, 8, 19), datetime(2026, 8, 19, 7, 5))
    assert n == 0  # swallowed, logged — never raises into the scan


@pytest.mark.asyncio
async def test_record_empty_inputs_is_a_noop():
    assert await cts.record_catalyst_tier_shadow(
        [], ["X"], date(2026, 8, 19), datetime(2026, 8, 19, 7, 5)) == 0


@pytest.mark.asyncio
async def test_sector_fetch_failure_degrades_to_no_confirm_not_a_crash(monkeypatch):
    from tests.conftest import make_mock_pool
    pool, conn = make_mock_pool()
    captured = []

    async def _execute(sql, *args):
        captured.append(args)
        return "INSERT 0 1"
    conn.execute = _execute
    monkeypatch.setattr(cts, "get_pool", AsyncMock(return_value=pool))
    monkeypatch.setattr(cts, "get_sectors_batch",
                        AsyncMock(side_effect=RuntimeError("cache down")))
    n = await cts.record_catalyst_tier_shadow(
        [{"ticker": "MRNA", "live_quality": "strong"}], ["MRNA", "TWST"],
        date(2026, 8, 19), datetime(2026, 8, 19, 7, 5))
    assert n == 1
    # sector_confirm arg (position 19 in the upsert params, index 18) is False
    assert captured[0][18] is False


# ── THE LINE: nothing live imports this module's verdicts ─────────────────────────────


def test_no_live_path_reads_the_shadow_table():
    """mi_catalyst_tier_shadow may be WRITTEN by catalyst_tier_shadow.py only. Since the
    2026-08-22 flip its ONE permitted reader is health_checks.py — the read-only flip
    monitor (run_catalyst_lattice_monitor), an alerting surface that feeds Telegram/audit
    rows and never a grading / entry / sizing / safeguard path. No other module may
    SELECT from it (grep the live packages; docs/tests excluded)."""
    import subprocess
    repo = Path(__file__).resolve().parent.parent
    out = subprocess.run(
        ["grep", "-rl", "--include=*.py", "mi_catalyst_tier_shadow",
         str(repo / "agents"), str(repo / "core"), str(repo / "channels"),
         str(repo / "shared"), str(repo / "broker")],
        capture_output=True, text=True).stdout.strip().splitlines()
    # ep_detector.py names the table in COMMENTS only (writer dispatch, never a read);
    # scheduler.py wires the monitor by function name, not the table.
    allowed = {str(repo / "agents/market_intelligence/catalyst_tier_shadow.py"),
               str(repo / "agents/market_intelligence/db.py"),
               str(repo / "agents/market_intelligence/ep_detector.py"),
               # the flip monitor (read-only SELECT) + _NOT_SWEEP_PARAMS reason strings
               str(repo / "agents/market_intelligence/health_checks.py")}
    assert set(out) <= allowed, f"unexpected readers of the shadow table: {set(out) - allowed}"
    # and the ONLY live SELECT against it is the flip monitor's, in health_checks.py
    sel = subprocess.run(
        ["grep", "-rln", "--include=*.py", "-i", r"select.*mi_catalyst_tier_shadow",
         str(repo / "agents"), str(repo / "core"), str(repo / "channels"),
         str(repo / "shared"), str(repo / "broker")],
        capture_output=True, text=True).stdout.strip().splitlines()
    assert set(sel) <= {str(repo / "agents/market_intelligence/health_checks.py")}, (
        f"live SELECT against the shadow table outside the flip monitor: {sel}")


# ── #533 Change 6 FLIP (2026-08-22, operator-signed): resolve_live_tier + live_side ───


def test_revert_flag_off_restores_the_raw_llm_grade_for_every_verdict():
    """THE REVERT PIN: with the `catalyst_tier_lattice` flag OFF, the acting grade is the
    raw LLM grade — byte-identical pre-flip behaviour — no matter what the lattice said."""
    for llm in ("game_changer", "strong", "routine", "mna"):
        for shadow in ("game_changer", "strong", "routine", "mna"):
            verdict = {"shadow_tier": shadow, "rule": "any"}
            assert cts.resolve_live_tier(llm, verdict, False) == (llm, "llm")


def test_flag_on_makes_the_lattice_verdict_the_acting_grade():
    verdict = {"shadow_tier": "game_changer", "rule": "strong_promoted_group_repricing"}
    assert cts.resolve_live_tier("strong", verdict, True) == ("game_changer", "lattice")


def test_lattice_failure_fails_open_to_the_raw_grade():
    """Fail direction: a missing/failed verdict degrades to the LLM grade (pre-flip
    behaviour), stamped 'llm' — a lattice failure delays the corrected tier, never
    darkens the scan or mislabels the acting side."""
    assert cts.resolve_live_tier("strong", None, True) == ("strong", "llm")
    assert cts.resolve_live_tier("strong", {}, True) == ("strong", "llm")
    assert cts.resolve_live_tier("strong", {"shadow_tier": None}, True) == ("strong", "llm")


@pytest.mark.asyncio
async def test_recorder_writes_the_precomputed_acting_verdict_and_live_side(monkeypatch):
    """Post-flip contract: an item carrying the verdict that ACTED is recorded VERBATIM
    (no recompute drift — get_sectors_batch must not even be called), and live_side lands
    as the LAST positional arg."""
    from tests.conftest import make_mock_pool
    pool, conn = make_mock_pool()
    captured = []

    async def _execute(sql, *args):
        captured.append((sql, args))
        return "INSERT 0 1"
    conn.execute = _execute
    monkeypatch.setattr(cts, "get_pool", AsyncMock(return_value=pool))
    sector_fetch = AsyncMock(return_value={"MRNA": "Healthcare"})
    monkeypatch.setattr(cts, "get_sectors_batch", sector_fetch)
    verdict = cts.compute_shadow_verdict(
        ticker="MRNA", live_quality="strong",
        claude_analysis="unscheduled label expansion", grounded_text="[SEC 8-K] guidance",
        news_summary="raises full-year guidance",
        sector_by_ticker={"MRNA": "Healthcare", "A": "Healthcare", "B": "Healthcare",
                          "C": "Healthcare", "D": "Healthcare", "E": "Tech"})
    n = await cts.record_catalyst_tier_shadow(
        [{"ticker": "MRNA", "live_quality": "strong", "verdict": verdict,
          "live_side": "lattice", "ep_score": 72.0, "live_tier": "HIGH"}],
        ["MRNA"], date(2026, 8, 19), datetime(2026, 8, 19, 7, 5))
    assert n == 1
    sql, args = captured[0]
    assert "live_side" in sql and "$27" in sql
    assert args[4] == verdict["shadow_tier"]   # $5 shadow_tier = the ACTING verdict, verbatim
    assert args[5] == verdict["rule"]          # $6 rule
    assert args[-1] == "lattice"               # $27 live_side
    sector_fetch.assert_not_called()           # verdict given -> no recompute, no refetch


@pytest.mark.asyncio
async def test_recorder_legacy_items_recompute_and_stamp_llm(monkeypatch):
    """Items WITHOUT a precomputed verdict (flag off / inline lattice failure) keep the
    original recompute path and default live_side='llm' — pre-flip rows stay honest."""
    from tests.conftest import make_mock_pool
    pool, conn = make_mock_pool()
    captured = []

    async def _execute(sql, *args):
        captured.append(args)
        return "INSERT 0 1"
    conn.execute = _execute
    monkeypatch.setattr(cts, "get_pool", AsyncMock(return_value=pool))
    monkeypatch.setattr(cts, "get_sectors_batch", AsyncMock(return_value={}))
    n = await cts.record_catalyst_tier_shadow(
        [{"ticker": "X", "live_quality": "routine"}], ["X"],
        date(2026, 8, 19), datetime(2026, 8, 19, 7, 5))
    assert n == 1
    assert captured[0][-1] == "llm"
