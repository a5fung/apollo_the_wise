"""#700 - the Sunday weekly review: cut the noise, keep what informs.

Operator 2026-10-11 (after a 12,257-character fold with nothing actionable in it): *"is there room to
improve it and reduce noise?"*, then his rule: *"even if something doesnt need me, if it's informative
it can still include so don't need to remove everthing but remove noise as much as possible."*

Design + decision table: docs/design/weekly_review_noise_700.md. Every rule here is a PRESENTATION
rule - no metric, threshold, grade, size or safeguard moved, and `metrics` is stored exactly as before
(the full, uncompacted text is stored beside it as `report.full_md`).

The fixture (`tests/fixtures/weekly_review_1011.json`) is the REAL stored 2026-10-11 row and the
2026-10-04 row that is its `prior` on the first run, rendered through the real `_assemble_report` by
`scripts/probes/_700_review_noise/harness_1011.py`. Every test here failed on origin/main before the renderer was changed (25 of the first 26; the
26th pins the new preview probe's read-only guard, which origin/main does not have). On top of that,
`scripts/probes/_700_review_noise/mutation_sweep.py` applies 15 one-line mutations to `system_review.py`
one at a time and every one is killed by at least one test in this file or the layout file; a test that
names a MUTATION below names one of those (`M<n>`) or says RED on origin/main.
"""
from __future__ import annotations

import asyncio
import copy
import json
from datetime import date, timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest

import agents.market_intelligence.db as dbmod
import agents.market_intelligence.system_review as sr
from scripts.probes._700_review_noise import harness_1011 as h
from tests.conftest import make_mock_pool
from tests.test_weekly_review_report_layout import _assemble

TODAY, WS = h.TODAY, h.WINDOW_START
FX = h.load_fixture()
SUMMARY = FX["review"]["summary"]
BULLETS = FX["review"]["suggestions"]                    # the three stored 10-11 anomaly bullets
BAND_SNAP = {"band": "HOLD", "override_active": False, "at_floor": True}


def _metrics() -> dict:
    return h.restore_dates(FX["review"]["metrics"])


def _prior(snapshot: dict | None = None, **metric_updates) -> dict:
    """The 10-04 row as `get_latest_system_review` returns it, optionally with a `report.snapshot`."""
    p = copy.deepcopy(FX["prior"])
    p["metrics"].update(metric_updates)
    if snapshot is not None:
        p["metrics"]["report"] = {"snapshot": snapshot}
    return p


def _render(prior=h.FIXTURE_PRIOR, **kw):
    return h.render_1011(prior, **kw)


def _lines(text: str) -> list[str]:
    return text.splitlines()


# -- 1-2. which review is "last week", and what the prompt carries ------------------------------

def test_prior_review_is_the_row_at_or_before_window_start():
    """The on-demand `weekly review` (agent.py) upserts a row dated THAT day, so "the latest row" on a
    Sunday after a Wednesday run is Wednesday's - a prior that hides the week. The comparison row is the
    newest one dated at or before `window_start`. MUTATION: the kwarg / `review_date <= $2` removed -
    this reddened (no such parameter); `run_weekly_review` no longer passing it reddened the last
    assertion."""
    pool, conn = make_mock_pool()
    conn.fetchrow = AsyncMock(return_value=None)
    with patch.object(dbmod, "get_pool", new=AsyncMock(return_value=pool)):
        asyncio.run(dbmod.get_latest_system_review(7, on_or_before=WS))
        sql = " ".join(conn.fetchrow.await_args.args[0].split())
        assert "review_date <= $2" in sql and "ORDER BY review_date DESC" in sql
        assert conn.fetchrow.await_args.args[1:] == (7, WS)
        asyncio.run(dbmod.get_latest_system_review(7))                 # the default call: the same statement,
        assert "$2::date IS NULL OR review_date <=" in " ".join(conn.fetchrow.await_args.args[0].split())
        assert conn.fetchrow.await_args.args[1:] == (7, None)          # ...with NULL bound = no upper bound
    # and the weekly run asks for exactly that row
    got = {}

    async def fake_latest(window_days=7, on_or_before=None):
        got.update(window_days=window_days, on_or_before=on_or_before)

    from contextlib import ExitStack
    with ExitStack() as stack:
        h.patch_render_inputs(stack, FX["render_inputs"])
        stack.enter_context(patch.object(sr, "_gather_and_aggregate", AsyncMock(return_value=_metrics())))
        stack.enter_context(patch.object(sr, "get_latest_system_review", fake_latest))
        stack.enter_context(patch.object(sr, "_synthesize", AsyncMock(return_value=SUMMARY)))
        stack.enter_context(patch.object(sr, "insert_system_review", AsyncMock()))
        stack.enter_context(patch.object(sr, "send_telegram_message", AsyncMock(return_value=True)))
        asyncio.run(sr.run_weekly_review(7))
    assert got == {"window_days": 7, "on_or_before": WS}


def test_synthesize_prompt_strips_last_weeks_rendered_text():
    """`report.full_md` / `fold_md` ride inside the stored metrics (~15 KB of last week's rendered text);
    handing them to the narrator would bloat a prompt that has truncated three times. MUTATION: the
    `if k != "report"` filter removed from `_synthesize`'s prior block - the 5,000 X's reached the
    prompt. RED, restored."""
    prior = {"review_date": "2026-10-04", "window_days": 7, "suggestions": ["old bullet"],
             "metrics": {"crypto": {"verdict": "KEPT-VERDICT"},
                         "report": {"full_md": "X" * 5000, "fold_md": "Y" * 100}}}
    seen = {}

    async def create(**kwargs):
        seen.update(kwargs)
        return SimpleNamespace(content=[SimpleNamespace(text="ok")], stop_reason="end_turn")

    fake = SimpleNamespace(messages=SimpleNamespace(create=create))
    metrics = {"window": {"days": 7, "start": "2026-10-04", "end": "2026-10-11"}}
    with patch.object(sr, "make_async_anthropic", lambda **kw: fake), \
            patch("agents.market_intelligence.spend_tracker.log_anthropic_call_safe", new=AsyncMock()):
        asyncio.run(sr._synthesize(metrics, prior))
    prompt = seen["messages"][0]["content"]
    assert "X" * 5000 not in prompt and "Y" * 100 not in prompt
    assert "KEPT-VERDICT" in prompt and "old bullet" in prompt          # the rest of last week still rides


# -- 3. repeated error rows -----------------------------------------------------------------------

def test_repeated_error_rows_collapse_to_one_line_per_type():
    """The 10-11 message printed 38 near-identical "quiet: it has not recurred" fragments. Now: one
    line per type and disposition, with the span, "none since", and the common cause. NOTHING is dropped
    from the data - the dispositioned list, the suppressed record and the full text keep every row.
    RED on origin/main: the fold carried the 38 fragments."""
    head, fold, meta = _render()
    line = [l for l in _lines(fold) if "ep_candidate_parse_error ×38" in l and "07:00–09:55" in l]
    assert len(line) == 1 and "none since" in line[0] and "quiet" in line[0]
    assert fold.count("has not recurred") == 0                          # no per-row fragment survives
    assert "⚪ *Errors logged (7d)* — 40 rows, 0 open" in fold
    assert "stop_coverage_repair_failed ×1" in fold and "judge_divergence_check_failed ×1" in fold
    # the data is untouched
    assert len(FX["review"]["metrics"]["audit_errors"]["dispositioned"]) == 40
    assert sum(1 for s in meta["suppressed"] if s["what"].startswith("ep_candidate_parse_error at")) == 38
    assert meta["full_md"].count("has not recurred") >= 38              # the stored full text keeps all rows


def test_collapse_error_rows_names_each_disposition_once_and_every_live_row():
    """Direct unit: a quiet group is one span line; a recovered group is one line carrying its `why`;
    every LIVE row keeps its own line (live rows are the ones the head escalates). MUTATION M10: the live
    rows cut to the first - the second live row vanished."""
    def row(disp, when, why, summary="x"):
        return {"disposition": disp, "when": when, "why": why, "summary": summary, "at": None}
    entry = {"event_type": "foo_failed", "count": 6, "days_ago": 3, "last_seen": "2026-10-08", "rows": [
        row("quiet", "Mon 10-05 07:00 ET", "it has not recurred in 6d (Mon 10-05 07:00 ET)", "5 of 100 rows failed"),
        row("quiet", "Mon 10-05 07:05 ET", "it has not recurred in 6d (Mon 10-05 07:05 ET)", "9 of 100 rows failed"),
        row("recovered", "Tue 10-06 09:00 ET", "foo_job ran clean Tue 10-06 10:00 ET"),
        row("live", "Thu 10-08 09:00 ET", "foo_failed — Boom: a (Thu 10-08 09:00 ET)"),
        row("live", "Thu 10-08 09:30 ET", "foo_failed — Boom: b (Thu 10-08 09:30 ET)"),
    ]}
    lines = sr.collapse_error_rows(entry)
    quiet = [l for l in lines if "quiet" in l]
    assert len(quiet) == 1 and "×2" in quiet[0] and "all Mon 10-05 07:00–07:05 ET" in quiet[0]
    assert "5–9 of 100 rows failed" in quiet[0]                         # digit runs that differ become a range
    recovered = [l for l in lines if "recovered" in l]
    assert len(recovered) == 1 and "foo_job ran clean Tue 10-06 10:00 ET" in recovered[0]
    assert len([l for l in lines if "live" in l]) == 2
    assert sr.collapse_error_rows({"event_type": "bar_error", "count": 2, "days_ago": 5,
                                   "last_seen": "2026-10-06"})[0].endswith("disposition unknown")


# -- 4-5. unchanged blocks leave the fold ---------------------------------------------------------

def test_unchanged_band_and_winner_capture_leave_the_fold_and_join_the_checked_line():
    """Bands HOLD and the 19% winner capture were identical to last week's: they now ride the head's
    checked line under "unchanged since last week", and the blocks go to the stored full text only.
    With no earlier review both print, and the decision log says why. MUTATION M2 / M14: `_changed`
    always printing, the winner-capture test forced True - the blocks stayed in the fold."""
    prior = _prior(snapshot={"band": BAND_SNAP})
    head, fold, meta = _render(prior)
    assert "Kill/scale band" not in fold and "MFE capture" not in fold
    assert _lines(head)[-1].endswith("unchanged since last week: bands HOLD · winner capture 19%._")
    shown = {c["section"]: c for c in meta["changes"]}
    assert shown["bands"]["shown"] is False and shown["mfe_capture"]["shown"] is False
    assert "Kill/scale band" in meta["full_md"] and "MFE capture" in meta["full_md"]
    head, fold, meta = _render(h.NO_PRIOR)
    assert "Kill/scale band" in fold and "MFE capture" in fold and "bands: HOLD" in head
    shown = {c["section"]: c for c in meta["changes"]}
    assert shown["bands"] == {"section": "bands", "shown": True, "why": "no prior"}
    assert shown["mfe_capture"]["shown"] is True and shown["mfe_capture"]["why"] == "no prior"
    # a band that moved prints again, with the move named in the log
    head, fold, meta = _render(_prior(snapshot={"band": {**BAND_SNAP, "band": "REDUCE"}}))
    assert "Kill/scale band" in fold
    assert next(c for c in meta["changes"] if c["section"] == "bands")["shown"] is True


def test_a_band_other_than_hold_is_an_action_and_prints_even_when_it_is_unchanged(monkeypatch):
    """Only an unchanged HOLD may leave the message. REDUCE / KILL / SCALE stay in the head's Needs-you
    list AND in the fold every week they stand, whatever last week said. MUTATION M15: the `band != "HOLD"`
    branch removed from the change test - an unchanged REDUCE vanished into the 'unchanged' phrase."""
    snap = {"band": "REDUCE", "override_active": False, "at_floor": True}
    block = "*🎚️ Kill/scale bands* (live-money, #268b):\n🟠 *Kill/scale band: REDUCE* — Halve risk/trade"
    monkeypatch.setattr(sr, "_band_section", AsyncMock(return_value=(block, "REDUCE", "Halve risk/trade", snap)))
    head, fold, meta = _assemble(monkeypatch, prior=_prior(snapshot={"band": snap}))
    assert "Kill/scale band: REDUCE" in fold
    assert "• kill/scale band is REDUCE — Halve risk/trade" in head and "bands: REDUCE" in head
    assert "unchanged since last week" not in head
    assert next(c for c in meta["changes"] if c["section"] == "bands") == {
        "section": "bands", "shown": True, "why": "band REDUCE is an action"}


def test_a_changed_crypto_verdict_prints_with_last_weeks_reading():
    """Crypto flipped from "1 crypto_ingest_error" (10-04) to "gates clean" (10-11): that is informative
    and prints with last week's reading beside it. Equal verdicts leave only a phrase on the checked
    line. MUTATION M2: `_changed` always printing - the equal-verdict case printed the block."""
    prior = _prior(crypto={**FX["prior"]["metrics"]["crypto"],
                           "verdict": "⚠️ not ready: 1 crypto_ingest_error events in last 7d"})
    head, fold, meta = _render(prior)
    crypto = [l for l in _lines(fold) if "Crypto RS" in l]
    assert len(crypto) == 1 and "last week: 1 crypto_ingest_error" in crypto[0] and "gates clean" in crypto[0]
    assert "7/7 ingests, 0 errors" in crypto[0] and "27 watchlist" in crypto[0]
    assert "crypto: live, gates clean" in head                          # printed week keeps its normal phrase
    same = _prior(crypto={**FX["prior"]["metrics"]["crypto"], "verdict": "✅ live; gates clean"})
    head, fold, meta = _render(same)
    assert "Crypto RS" not in fold
    assert "unchanged since last week:" in head and "crypto live, gates clean" in head.splitlines()[-1]
    assert next(c for c in meta["changes"] if c["section"] == "crypto")["shown"] is False


# -- 6. promotions: new or changed rows only ------------------------------------------------------

def test_promotion_rows_print_only_when_new_or_changed():
    """10-11 vs 10-04: only magna53_smallcap is new on the ladder. shadow_orb_5m's reason moved from
    median R -0.07 to -0.06 and 43 to 45 closed - digits only, the same blocker - so it stays out of the
    message and in the full text. MUTATION: the digit-stripping `re.sub(r"\\d+", "", reason)` removed
    from the comparison - shadow_orb_5m, parabolic_short and magna53_lowcap all printed. RED, restored."""
    sp = FX["review"]["metrics"]["strategy_promotions"]
    text, why, shown = sr._promotion_message(sp, FX["prior"]["metrics"]["strategy_promotions"]["checks"])
    assert shown is True                                               # the decision log reads this flag, not the text
    rows = [l for l in _lines(text) if l.startswith("•")]
    assert len(rows) == 1 and rows[0].startswith("• magna53_smallcap") and "new on the ladder" in rows[0]
    assert "(paper → live)" in rows[0] and "need 30 closed (have 0)" in rows[0]
    assert _lines(text)[0] == "📈 *Strategy promotion* — none ready · changed since last week:"
    assert "shadow_orb_5m" not in text
    head, fold, meta = _render()
    assert "shadow_orb_5m" not in fold and "shadow_orb_5m" in meta["full_md"]
    assert sum(1 for l in _lines(fold) if l.startswith("• magna53_smallcap")) == 1
    # nothing changed -> the header alone; no prior -> every ladder row prints, no "changed" claim
    same_text, _, same_shown = sr._promotion_message(sp, sp["checks"])
    assert _lines(same_text) == ["📈 *Strategy promotion* — none ready"] and same_shown is False
    first_text, first_why, first_shown = sr._promotion_message(sp, None)
    assert first_why == "no prior" and first_shown is True and "changed since last week" not in first_text
    assert len([l for l in _lines(first_text) if l.startswith("•")]) == 5


# -- 7-8. the narrative's "anomalies to verify" ---------------------------------------------------

# The 10-11 bullet 1 with its L2 citation (`l2_anomalies` = 1 (`cooldowns_per_day`)) dropped: what is left
# speaks only for the audit-error ledger and the one L1 invariant that ledger can speak to.
CLEAN_BULLET = (
    "`audit_errors.total` = 40, of which 38 are `ep_candidate_parse_error`. Those ran every 5 min on 10-07 "
    "from 07:00 to 09:55 ET, each with about 139-150 of ~13.2k snapshot rows dropped (`prev_close` 0/missing), "
    "and none have recurred. `l1_invariants` = 1 (`silent_audit_error_window`). They may be already-resolved "
    "or designed, so check them against audit ground truth.")


def test_narrative_anomalies_settled_by_the_record_become_a_count_and_say_why():
    """The three stored 10-11 bullets. #1 names ep_candidate_parse_error (38 rows, all quiet, no live row)
    but ALSO cites the L2 anomaly `cooldowns_per_day` - which the audit-error ledger cannot speak to - so it
    stays MINE: 3 observations, 0 settled (the review's finding: a settled bullet must never carry an L1/L2
    anomaly off the page). #2 names no audit type -> mine. #3 names stop_coverage_repair_failed but also CEG
    (a traded name) and a `stop_order_id` nothing in the record holds -> mine. The positive control is the
    same bullet 1 with the L2 citation dropped: it settles and the head says so. MUTATION M1: `settled`
    forced True in `verify_narrative_anomalies` - #2 and #3 vanished into the settled count."""
    head, fold, meta = _render()
    me = [l for l in meta["needs_me_lines"] if "observation" in l]
    assert len(me) == 1 and me[0].startswith("3 observations from this week's narrative for me to check Monday")
    assert "already settled" not in me[0]
    assert meta["needs_me"] == 2                                        # the ripe review + this one line
    # #700 follow-up (his rule, 10-11): unverified observations are mine — only the count reaches him
    assert "⚠️ *To verify (mine" not in fold
    assert not any(b[:60] in fold for b in BULLETS)
    assert "kept in the stored full text" in me[0]
    assert "settled by the record" not in fold
    assert "Anomalies to verify" not in fold and "UNVERIFIED" not in fold   # no unverified claim as a finding
    assert sr._extract_anomalies(SUMMARY) == BULLETS                    # next week's 🔁 check is unchanged
    assert not any(s["what"].startswith("narrative anomaly:") for s in meta["suppressed"])
    # positive control: the settle path still works on a bullet the ledger CAN speak for
    head, fold, meta = _render(summary=SUMMARY.replace(BULLETS[0], CLEAN_BULLET))
    me = [l for l in meta["needs_me_lines"] if "observation" in l]
    assert len(me) == 1 and me[0].startswith("2 observations from this week's narrative for me to check Monday")
    assert "1 more already settled by the record" in me[0]
    assert BULLETS[1][:60] not in fold and BULLETS[2][:60] not in fold
    assert CLEAN_BULLET[:40] not in fold                                # the settled bullet is not re-printed
    assert any(s["what"].startswith("narrative anomaly:") and "settled by the record" in s["rule"]
               for s in meta["suppressed"])


def test_a_bullet_naming_a_live_error_or_a_traded_ticker_is_never_settled():
    """The direction guard - the test that stops "settled" from drifting into "always". Green on today's
    code by vacuity (nothing settles anything); RED against `settled = True`. Keep it beside the test
    above, which is the positive control."""
    metrics = _metrics()
    verdicts = sr.verify_narrative_anomalies(BULLETS, metrics)
    assert [v["settled"] for v in verdicts] == [False, False, False]
    assert "`l2_anomalies`" in verdicts[0]["why"] and "anomaly" in verdicts[0]["why"]   # the L2 citation keeps #1 mine
    clean = sr.verify_narrative_anomalies([CLEAN_BULLET], metrics)[0]
    assert clean["settled"] and clean["why"].startswith("ep_candidate_parse_error ×38")
    live = {"audit_errors": {"top_types": [
        {"event_type": "foo_failed", "count": 2, "disposition": "live", "rows": [
            {"disposition": "quiet", "when": "Mon 10-05 07:00 ET", "why": "it has not recurred in 6d", "summary": "s"},
            {"disposition": "live", "when": "Thu 10-08 09:00 ET", "why": "foo_failed - Boom", "summary": "s"}]}]},
        "anomalies": {}}
    assert not sr.verify_narrative_anomalies(["`foo_failed` 2 events, check them."], live)[0]["settled"]
    absent = sr.verify_narrative_anomalies(["`never_seen_failed` appeared 3 times."], live)
    assert not absent[0]["settled"]                                     # a type the record does not hold
    traded = sr.verify_narrative_anomalies(["`ep_candidate_parse_error` hit CEG's scan."], metrics)
    assert not traded[0]["settled"]                                     # a ticker from the week's metrics
    zone = sr.verify_narrative_anomalies(
        ["Ran 07:00 to 09:55 ET (`ep_candidate_parse_error`), none since."], metrics)
    assert zone[0]["settled"]                                           # "ET" after a time is a zone, not a ticker
    # position, not just the fixed set: a token that follows a clock time is a zone even when it is ALSO a
    # ticker in this week's metrics; the same token with no time before it is a ticker and blocks settling
    with_cdt = copy.deepcopy(metrics)
    with_cdt["loser_breakdown"]["losers"].append({"ticker": "CDT", "total_pnl": -1.0})
    after_time = sr.verify_narrative_anomalies(
        ["Ran 07:00 to 09:55 CDT (`ep_candidate_parse_error`), none since."], with_cdt)
    assert after_time[0]["settled"]
    no_time = sr.verify_narrative_anomalies(["`ep_candidate_parse_error` also hit CDT."], with_cdt)
    assert not no_time[0]["settled"]
    assert not sr.verify_narrative_anomalies(["not a list"], None)[0]["settled"]    # any parse doubt: mine


def test_an_l1_or_l2_anomaly_in_a_bullet_keeps_it_mine_next_to_a_quiet_error_type():
    """The review's BLOCKING finding: the narrator is told to cite the week's L1/L2 footprint, and a bullet
    that cites a live-money breach beside a quiet audit type used to settle - the breach left the message
    and the Needs-me count. Only `silent_audit_error_window` (an invariant whose source is the audit-error
    window itself) may settle; any other L1/L2 key with count > 0 - named, or hidden behind a bare
    section count - keeps the bullet mine. MUTATION M16: `_settleable_anomaly_names` admitting every
    section (`if True:`) - the first three cases settled."""
    quiet = "`stop_coverage_repair_failed` count 1, quiet since 10-06"

    def verdict(text, anomalies):
        m = _metrics()
        m["anomalies"] = anomalies
        return sr.verify_narrative_anomalies([text], m)[0]

    breach = {"l1_invariants": {"count": 2, "by_key": [{"key": "open_position_without_stop", "count": 2}]}}
    v = verdict(f"Footprint: `l1_invariants` = 2 (`open_position_without_stop`), and {quiet}.", breach)
    assert not v["settled"] and "`l1_invariants`" in v["why"] and "anomaly" in v["why"]
    # the breach hidden behind a bare section count (the key itself never named) is still not settled
    assert not verdict(f"Footprint: `l1_invariants` = 2, and {quiet}.", breach)["settled"]
    # the section count with no keys listed at all: unknown, so mine
    assert not verdict(f"Footprint: `l1_invariants` = 2, and {quiet}.",
                       {"l1_invariants": {"count": 2, "by_key": []}})["settled"]
    # an L2 anomaly is not an audit-error claim either
    l2 = {"l2_anomalies": {"count": 1, "by_key": [{"key": "cooldowns_per_day", "count": 1}]}}
    assert not verdict(f"`l2_anomalies` = 1 (`cooldowns_per_day`); {quiet}.", l2)["settled"]
    # an L3 drift metric is a different claim from "the error type stopped"
    l3 = {"l3_drifts": {"count": 1, "transitions": [{"key": "theme_count_active", "p50": 1, "current": 2}]}}
    assert not verdict(f"`theme_count_active` moved band; {quiet}.", l3)["settled"]
    # ... and the allowlisted invariant, alone or beside a count-0 breach key, still settles
    ok = {"l1_invariants": {"count": 1, "by_key": [{"key": "silent_audit_error_window", "count": 1},
                                                   {"key": "open_position_without_stop", "count": 0}]}}
    assert verdict(f"`l1_invariants` = 1 (`silent_audit_error_window`); {quiet}.", ok)["settled"]
    # ... but the same allowlisted key beside a FIRING breach: the section count is no longer the audit
    # window's alone, so citing the bare section is mine; citing only the allowlisted key stays settled
    both = {"l1_invariants": {"count": 3, "by_key": [{"key": "silent_audit_error_window", "count": 1},
                                                     {"key": "open_position_without_stop", "count": 2}]}}
    assert not verdict(f"`l1_invariants` = 3; {quiet}.", both)["settled"]
    assert verdict(f"`silent_audit_error_window` fired once; {quiet}.", both)["settled"]
    # What "settled" does NOT cover: an impact claim written in prose names no identifier the lookup can
    # test. It is documented (design doc section 4), not detected.
    prose = verdict(f"{quiet}; the EP scan may have missed real candidates that morning.", {})
    assert prose["settled"]


def test_an_all_settled_narrative_block_prints_nothing_but_keeps_its_record():
    """When every ⚠️ bullet settles, nothing reaches the message (no count, no block) — the settle is
    recorded in `suppressed` with its reason, so the full text still shows what was dropped and why."""
    only = "\n".join(["⚠️ *Anomalies to verify* — UNVERIFIED; do NOT act before checking ground truth",
                      "• " + CLEAN_BULLET])
    block, me_line, sup = sr._anomaly_block(only, _metrics())
    assert block == ""
    assert me_line is None and len(sup) == 1
    assert "settled by the record" in sup[0]["rule"]


# -- 9. drift and docs drift re-rendered from metrics ---------------------------------------------

def test_drift_and_docs_drift_are_rerendered_in_plain_words_from_metrics():
    """The LLM's own Drift/Docs-drift wording ("1→2 (20.0 vs p50 5.0)") is cut; the fold re-renders from
    `anomalies.l3_drifts` / `drift_check` - one line per metric with what moved, today's number, the
    typical number and how many moves. MUTATION M12: the LLM's 📉 block passed
    through - its own wording came back and the plain lines did not."""
    head, fold, meta = _render()
    drift = [l for l in _lines(fold) if l.startswith(("• cooldowns per day", "• active theme count"))]
    assert len(drift) == 2
    assert any("band 1→2 — 20 a day vs a typical 5 (3 moves this week)" in l for l in drift)
    assert any("band 2→1 — 123 vs a typical 118 (3 moves this week)" in l for l in drift)
    assert "📉 *Drift — band moves this week*" in fold
    assert "20.0 vs p50" not in fold and "Docs drift (unverified)" not in fold
    assert ("📄 Docs: 1 dated claim nothing can verify — docs/setups/magna53_ep.md:675 (mine to re-check)"
            in fold)
    assert sr._render_drift({"l3_drifts": {"count": 0, "transitions": []}}) == ""
    assert sr._render_docs_drift({"unverified_n": 0}) == ""
    many = sr._render_docs_drift({"unverified_n": 5, "unverified_claims": [{"where": f"d.md:{i}"} for i in range(5)]})
    assert "5 dated claims" in many and "d.md:0, d.md:1, d.md:2" in many and "+2 more" in many
    hinted = sr._render_drift({"l3_drifts": {"count": 1, "transitions": [
        {"key": "theme_count_active", "from_band": 1, "to_band": 2, "current": 130.0, "p50": 118.0,
         "recent_change_hint": "#655 re-granularization"}]}})
    assert "may be intentional (#655 re-granularization)" in hinted


def test_an_unrecognised_narrative_block_is_kept_verbatim(monkeypatch):
    """Fail-open: a header the splitter does not know (the prompt can still ask for a "📐 Shadow ORB"
    line, and a model can invent one) lands in the fold untouched - and does NOT get
    swallowed by the block before it. Green today by construction (the whole summary folds); RED
    against a splitter that drops `other`. Keep it."""
    summary = ("✅ *Working*\n• a\n\n📄 *Docs drift (unverified):*\n• `d.md:1`: x\n\n"
               "🧿 *New thing*\n• the unknown block's bullet\n\n📐 *Shadow ORB:* 12 5m entries")
    head, fold, meta = _assemble(monkeypatch, summary=summary,
                                 drift_check={"unverified_n": 1, "unverified_claims": [{"where": "d.md:1"}]})
    assert "🧿 *New thing*\n• the unknown block's bullet" in fold
    assert "📐 *Shadow ORB:* 12 5m entries" in fold
    assert "📄 Docs: 1 dated claim nothing can verify — d.md:1" in fold   # the known block next to it was re-rendered
    kinds = [k for k, _ in sr.split_narrative_blocks(summary)]
    assert kinds == ["working", "docs_drift", "other", "other"]
    assert sr.split_narrative_blocks("preamble line\n✅ *Working*\n• a")[0][0] == "other"
    assert sr.split_narrative_blocks("") == []


# -- 11. boilerplate ------------------------------------------------------------------------------

def test_boilerplate_leaves_the_message_but_stays_in_the_full_text():
    """Legends, era keys, caveats, explainers, the calibration card and the cost-envelope block leave
    the message; every one is still in the stored full text. MUTATION M7: `_replay_message_lines`
    returning the lines unfiltered - the calibration card and caveat stayed in the fold."""
    head, fold, meta = _render()
    for gone in ("Legend:", "era key —", "ⓘ", "Per-delta review", "Cost envelope (MTD)", "Telemetry only",
                 "_Runs win or lose", "not enough to ask", "calibration (", "Engine-improvement queue"):
        assert gone not in fold, gone
        assert gone in meta["full_md"], gone
    assert "Cost envelope" not in head                                   # the head's "spend: $X of $150" carries it


# -- 12. the early-window drift line defers to the bands ------------------------------------------

def test_early_window_drift_is_silent_once_the_band_floor_is_reached():
    """Its own docstring: it exists for the weeks BEFORE the bands have 20 trades. At n=34 the band
    section owns the number. Below the floor it prints as today. MUTATION M11: the floor test deleted - the
    n=34 line printed."""
    head, fold, meta = _render(n_live=34)
    assert "Early-window drift" not in fold and "Early-window drift" in meta["full_md"]
    entry = next(c for c in meta["changes"] if c["section"] == "early_window_drift")
    assert entry["shown"] is False and "at floor: bands own it" in entry["why"]
    head, fold, meta = _render(n_live=6)
    assert "Early-window drift" in fold
    assert next(c for c in meta["changes"] if c["section"] == "early_window_drift")["shown"] is True


# -- 13. gaps -------------------------------------------------------------------------------------

def test_gaps_print_new_rows_only_and_count_the_carried():
    """10-11 vs 10-04: EROC and VST are new, six names carried. The table holds the new rows only and
    the header counts the rest. MUTATION M5: `new = cur - prior` changed to
    `cur` - all eight rows printed."""
    m = _metrics()["missed_opportunities"]
    prior_keys = {f"{g['ticker']}|{g['alert_date']}" for g in FX["prior"]["metrics"]["missed_opportunities"]["gaps"]}
    text, why, rows_shown, caps_shown = sr._gaps_message(m["gaps"], m["source_gap_summary"], prior_keys, None)
    assert rows_shown is True and caps_shown is True                   # the flags the decision log reads
    assert "2 new this week, 6 carried from last week" in _lines(text)[0]
    table = [l for l in _lines(text) if l[:5].strip() in {"EROC", "VST"}]
    assert len(table) == 2 and not any(t in text for t in ("CIFR", "VICR", "TWST", "RPD", "ARM", "TEM"))
    assert "Verify before acting" not in text and "ranked by peak missed upside" not in text   # explainer is gone
    all_old = {f"{g['ticker']}|{g['alert_date']}" for g in m["gaps"]}
    nothing, _, nothing_rows, nothing_caps = sr._gaps_message(m["gaps"], m["source_gap_summary"], all_old,
                                                              m["source_gap_summary"])
    assert nothing_rows is False and nothing_caps is False
    assert "0 new this week, 8 carried from last week" in nothing and "tckr" not in nothing
    assert "Strong-catalyst MODERATE caps" not in nothing               # unchanged caps line: full text only
    first, why, first_rows, first_caps = sr._gaps_message(m["gaps"], m["source_gap_summary"], None, None)
    assert why == "no prior" and "tckr" in first and "CIFR" in first    # nothing to compare against: print it all
    assert first_rows is True and first_caps is True
    assert sr._gaps_message([], m["source_gap_summary"], None, None) == ("", "no gaps", False, False)
    head, fold, meta = _render()
    assert "2 new this week, 6 carried from last week" in fold and "CIFR" not in fold
    assert "CIFR" in meta["full_md"]
    # caps line: prior (denom 18, unsourced 3) differs from now (14, 2) -> the line prints
    assert "Strong-catalyst MODERATE caps (60d, n=14)" in fold


# -- 14. setup review and replay-regression are event-keyed ----------------------------------------

def _change(meta: dict, section: str) -> dict:
    return next(c for c in meta["changes"] if c["section"] == section)


def test_replay_and_setup_rows_print_only_when_a_trade_closed_this_week():
    """Both are 90-day / all-time views over the closed-trade cohort: they only change when a trade
    closes. The key is NOT just "an alerted-this-week trade lost / has a post-mortem" - those lists are
    keyed on the ALERT date and miss a trade alerted earlier and held across the boundary that closes now
    (the 10-11 open book is KOD 11d and PENG 2d). So a close is any of: a loser or post-mortem in the
    window, a partial-taken winner closed in the window, or the live closed-trade count (all-time, stored
    in last week's snapshot) having moved. Nothing to compare against -> PRINT, never hide.
    MUTATION M3 / M7: the alert-window key forced True - both printed on the quiet week; M17: the count
    comparison dropped - the held-trade case stayed silent."""
    quiet = {"loser_breakdown": {}, "postmortem_best": None, "postmortem_worst": None}
    same = {"band": BAND_SNAP, "theme_queue_keys": [], "live_closed_n": 34}
    head, fold, meta = _render(_prior(snapshot=same), metrics_update=quiet)     # 34 last week, 34 now
    assert "Setup review" not in fold and "Replay-regression" not in fold
    assert "Setup review" in meta["full_md"] and "Replay-regression" in meta["full_md"]
    c = _change(meta, "closed_this_week")
    assert c["shown"] is False and "no close: 34 live closed trades" in c["why"]
    head, fold, meta = _render()                                         # CEG closed this week
    assert "🧪 *Setup review — entry/stop geometry (90d)* — a trade closed this week" in fold
    assert "Replay-regression" in fold and "live (n=34)" in fold and "rule eras:" in fold
    assert "calibration (" not in fold and "ⓘ" not in fold
    assert "eras: era_" not in fold and "eras: era_" in meta["full_md"]   # bare era letters need the legend; full text keeps them
    assert sr._replay_message_lines(["", "*🔁 Replay-regression* (live R-dist vs c)", "  live (n=5): x",
                                     "  rule eras: y", "  calibration (c): z", "  ⓘ caveat"]) \
        == ["", "*🔁 Replay-regression* (live R-dist vs c)", "  live (n=5): x", "  rule eras: y"]
    # the audit snapshot the replay writes is not a rendering choice: it still runs on the quiet week
    mocks: dict = {}
    _render(_prior(snapshot=same), metrics_update=quiet, mocks=mocks)
    assert mocks["audit"].await_count == 1
    assert mocks["audit"].await_args.args[0] == "replay_regression_snapshot"
    # THE review's case: a trade alerted before the window and held across it closes now - no loser, no
    # post-mortem, no partial-taken winner, but the live closed-trade count moved 33 -> 34
    held = {"band": BAND_SNAP, "theme_queue_keys": [], "live_closed_n": 33}
    head, fold, meta = _render(_prior(snapshot=held), metrics_update=quiet)
    assert "🧪 *Setup review — entry/stop geometry (90d)* — a trade closed this week" in fold
    assert "Replay-regression" in fold and "live (n=34)" in fold
    c = _change(meta, "closed_this_week")
    assert c["shown"] is True and "moved 33 -> 34" in c["why"]
    assert meta["full_md"].count("live (n=34)") == 1                     # printed once, not twice
    # a partial-taken winner that closed in the window is a close too
    mfe = copy.deepcopy(_metrics()["mfe_capture"])
    mfe["window_closes"] = [{"ticker": "KOD", "account_mode": "live", "capture_pct": 40, "kept": 20, "mfe": 50}]
    head, fold, meta = _render(_prior(snapshot=same), metrics_update={**quiet, "mfe_capture": mfe})
    assert "Setup review" in fold and "Replay-regression" in fold
    # nothing stored from last week (the first run after this ships) -> print, but claim no close
    head, fold, meta = _render(metrics_update=quiet)
    assert "Setup review" in fold and "Replay-regression" in fold
    assert "a trade closed this week" not in fold
    c = _change(meta, "closed_this_week")
    assert c["shown"] is True and "no stored closed-trade count" in c["why"]
    # the count unreadable (the replay run failed) -> print, and the failure line stays visible
    from contextlib import ExitStack
    with ExitStack() as stack:
        stack.enter_context(patch("agents.market_intelligence.replay_regression.run_replay_regression",
                                  AsyncMock(return_value={"lines": ["", "_replay-regression unavailable: x_"],
                                                          "error": "x"})))
        head, fold, meta = _render(_prior(snapshot=same), metrics_update=quiet)
    assert "replay-regression unavailable: x" in fold and "Setup review" in fold
    c = _change(meta, "closed_this_week")
    assert c["shown"] is True and "unavailable" in c["why"]
    assert "live_closed_n" not in meta["snapshot"]                       # no number to store, none invented


# -- 15. judge roll-up and the losers' flags ------------------------------------------------------

def test_judge_rollup_is_one_line_and_losers_flags_are_words():
    """The judge block (a code fence + a pointer) is one line. The loser's emoji flags become words a
    reader does not need a legend for. RED on origin/main: the judge block was a code fence plus a
    pointer, and the loser's flags were emoji and a legend."""
    head, fold, meta = _render()
    assert ("⚖️ *Holistic judge:* graded 10 of 10 alerts — 0 up, 4 down, 6 held · 0 fell back to our score"
            " · fire axes seen on 7, none on 3") in fold
    loser = [l for l in _lines(fold) if l.startswith("• `CEG`")]
    assert len(loser) == 1 and "the 5-min ORB would have blocked it (range 5.7% > 1.5x ATR)" in loser[0]
    assert "⛔" not in fold and "Legend" not in fold and "5m refs the" not in fold
    assert "n_losers" not in fold and "5m-blocked" not in fold          # the aggregate line needs >= 5 losers
    L = {"ticker": "ABC", "alert_date": "2026-10-06", "total_pnl": -40.0, "prose_mismatch": True,
         "orb5_verdict": "wider_stop", "orb5_low": 12.34, "time_to_stop_min": 3.2, "is_compound_loss": True,
         "entry_attempt": 2, "gap_through_dollars": 0.31, "earnings_boost_fired": True}
    words = sr._loser_flag_words(L)
    assert words == ["catalyst grade vs prose mismatch", "5-min ORB stop would sit at $12.34",
                     "stopped in 3.2m", "second attempt, compound loss", "filled $0.31 past the stop",
                     "earnings backstop fired"]
    assert sr._loser_flag_words({"ticker": "Z", "total_pnl": -1.0}) == []


# -- 16. #486 and #313 stay, compacted ------------------------------------------------------------

def test_theme_and_spend_sections_are_compact():
    """#486: one line per window, the queue lists only names NEW to the list (with a prior snapshot),
    the footer is a one-line pointer. #313: four lines, the top three callers inline, no footer.
    MUTATION M13: the queue listing every judge-only name instead of the new ones; RED on origin/main
    for the rest (the 2-line cells, the definitions footer, the 6-caller list)."""
    head, fold, meta = _render(h.NO_PRIOR)
    block = fold[fold.index("🧩 *Theme read, engine vs judge (#486)*"):].split("\n\n")[0]
    bl = _lines(block)
    assert len(bl) <= 7 + 2
    assert bl[1].startswith("This week (n=6): engine and judge agree on 4 of 6 (67%) — both saw a theme 2")
    assert "judge only 1 · engine only 1 · neither 2" in bl[1]
    assert bl[2].startswith("Last 30 days to Oct 11 (n=14): engine and judge agree on 11 of 14 (79%)")
    # no earlier review to compare: every name lists and NO novelty is claimed (AKAM 09-25 also sat in last
    # week's 30-day window, so "new to this list" would have been unfounded)
    assert "Judge saw a theme the engine did not — 2 in the last 30 days (no earlier review to compare):" in block
    assert "new to this list" not in block
    assert "• AKAM 09-25 — no theme row at all" in block and "• AAOI 10-09 — theme known, excluded (stage Nascent)" in block
    assert bl[-1] == ("_Counts 14 of 22 judge-graded alerts; definitions and the 8 left out: full text._")
    # a snapshot that holds an EMPTY queue is something to compare against: both are genuinely new
    head, fold, meta = _render(_prior(snapshot={"band": BAND_SNAP, "theme_queue_keys": []}))
    assert "2 in the last 30 days, both new to this list:" in fold
    # with last week's queue known, only the NEW name lists and the carried one is counted
    snap = {"band": BAND_SNAP, "theme_queue_keys": ["AAOI|2026-10-09"]}
    head, fold, meta = _render(_prior(snapshot=snap))
    assert "• AKAM 09-25" in fold and "• AAOI 10-09" not in fold
    assert "2 in the last 30 days, 1 new to this list:" in fold
    assert next(c for c in meta["changes"] if c["section"] == "theme_queue")["shown"] is True
    # #313
    spend = fold[fold.index("💸 *LLM spend vs realised P&L (#313)"):].split("\n\n")[0]
    sl = _lines(spend)
    assert len(sl) == 4, sl
    assert sl[1] == ("LLM spend $45.33 across 5,623 calls · top: eval_519_option_a $9.22 · "
                     "perplexity_news_search $8.09 · theme_assignment $7.21")
    assert sl[2].startswith("Judge-named callers $2.59 (6% of spend): judge_robustness_eval $0.90")
    assert sl[3] == "Live book (real money): $+17 over 6 closed trades (3 winners)"
    assert "Telemetry only" not in spend and "other callers" not in spend


# -- 17. what is stored ---------------------------------------------------------------------------

def test_report_meta_persists_snapshot_full_and_sent_text():
    """Nothing is deleted from the data: the stored row carries the snapshot the NEXT run compares
    against, the full uncompacted text, the head and fold exactly as sent, and the decision log.
    RED on origin/main: the stored report had no snapshot, full text or decision log."""
    from contextlib import ExitStack
    inserted, sent = [], []
    prior = copy.deepcopy(FX["prior"])
    with ExitStack() as stack:
        h.patch_render_inputs(stack, FX["render_inputs"])
        stack.enter_context(patch.object(sr, "_gather_and_aggregate", AsyncMock(return_value=_metrics())))
        stack.enter_context(patch.object(sr, "get_latest_system_review", AsyncMock(return_value=prior)))
        stack.enter_context(patch.object(sr, "_synthesize", AsyncMock(return_value=SUMMARY)))
        stack.enter_context(patch.object(sr, "insert_system_review",
                                         AsyncMock(side_effect=lambda r: inserted.append(r))))
        stack.enter_context(patch.object(sr, "send_telegram_message",
                                         AsyncMock(side_effect=lambda t, **kw: sent.append((t, kw)) or True)))
        review = asyncio.run(sr.run_weekly_review(7))
    assert len(sent) == 1 and sent[0][1] == {"parse_mode": "HTML"}      # ONE send, as before
    report = inserted[0]["metrics"]["report"]
    assert report["snapshot"]["band"] == BAND_SNAP
    assert sorted(report["snapshot"]["theme_queue_keys"]) == ["AAOI|2026-10-09", "AKAM|2026-09-25"]
    assert set(report["snapshot"]) == {"band", "theme_queue_keys", "live_closed_n"}
    assert report["snapshot"]["live_closed_n"] == 34                    # the all-time live closed-trade count
    assert report["full_md"].count("has not recurred") >= 38 and "ep_candidate_parse_error ×38" in report["head_md"] + report["fold_md"]
    assert len(report["full_md"]) > len(report["fold_md"]) > 0 and report["head_md"].startswith("🧠 *Weekly review")
    assert report["fold_chars"] == len(report["fold_md"])
    assert {c["section"] for c in report["changes"]} >= {"bands", "mfe_capture", "crypto", "promotions", "gaps",
                                                         "closed_this_week", "early_window_drift", "theme_queue"}
    assert all(set(c) == {"section", "shown", "why"} for c in report["changes"])
    assert len(report["suppressed"]) >= 41                              # the 40 dispositioned rows + the settled bullet
    assert inserted[0]["metrics"]["audit_errors"]["dispositioned"] == FX["review"]["metrics"]["audit_errors"]["dispositioned"]
    assert review["suggestions"] == BULLETS                             # shape unchanged: ALL bullets
    json.dumps(inserted[0]["metrics"]["report"])                        # JSON-safe: string keys, ISO dates


# -- 18. the budget -------------------------------------------------------------------------------

def test_the_1011_fixture_renders_under_the_budget():
    """The real 10-11 content through the real assembly. Baseline (pre-#700, measured from this same
    harness): the fold was ~12.4k characters. With the prior row (first run: band block and theme
    queue print once) it must fit 6,500; with no prior at all (everything prints as new) 7,500. The head
    stays at most 6 lines and still names every surface the old checked line named. RED on origin/main (12,446 characters); the cuts
    that carry it are the ones M2, M3, M5, M7, M11, M12 and M13 revert."""
    before = FX["before"]
    head, fold, meta = _render()
    assert len(fold) <= 6500, len(fold)
    assert len(fold) < before["fold_chars"] * 0.55
    assert meta["head_lines"] <= 6 and meta["fold_chars"] == len(fold)
    assert meta["needs_me"] == 2 and meta["needs_you"] == 0
    checked = head.splitlines()[-1]
    for phrase in before["checked_phrases"]:
        key = phrase.replace(": ", " ", 1) if phrase.startswith(("bands", "crypto")) else phrase
        assert phrase in checked or key in checked, phrase
    head2, fold2, meta2 = _render(h.NO_PRIOR)
    assert len(fold2) <= 7500, len(fold2)
    assert meta2["head_lines"] <= 6
    assert len(fold2) >= len(fold)                                       # no prior can only print MORE


# -- fail-open and the plumbing around the cuts -----------------------------------------------------

def test_a_prior_fetch_that_raises_prints_every_change_only_section_and_the_review_still_goes():
    """"Missing -> PRINT, never hide": if the comparison row cannot be read, the review does not die and
    does not guess - every change-only section prints and says why. RED on origin/main: the exception escaped `run_weekly_review` and nothing was
    sent."""
    from contextlib import ExitStack
    inserted, sent = [], []
    with ExitStack() as stack:
        h.patch_render_inputs(stack, FX["render_inputs"])
        stack.enter_context(patch.object(sr, "_gather_and_aggregate", AsyncMock(return_value=_metrics())))
        stack.enter_context(patch.object(sr, "get_latest_system_review",
                                         AsyncMock(side_effect=RuntimeError("pool closed"))))
        stack.enter_context(patch.object(sr, "_synthesize", AsyncMock(return_value=SUMMARY)))
        stack.enter_context(patch.object(sr, "insert_system_review",
                                         AsyncMock(side_effect=lambda r: inserted.append(r))))
        stack.enter_context(patch.object(sr, "send_telegram_message",
                                         AsyncMock(side_effect=lambda t, **kw: sent.append(t) or True)))
        asyncio.run(sr.run_weekly_review(7))
    assert len(sent) == 1 and len(inserted) == 1
    changes = {c["section"]: c for c in inserted[0]["metrics"]["report"]["changes"]}
    for section in ("bands", "mfe_capture", "crypto", "promotions", "gaps"):
        assert changes[section]["shown"] is True and changes[section]["why"] == "no prior", section


def test_a_compaction_that_raises_falls_back_to_the_full_text_never_to_silence(monkeypatch):
    """A bug in a message renderer costs that section its compaction, not its content: the fold carries
    the section's FULL text and the rest of the review is untouched. MUTATION M8: `compact()` stopped
    catching - the section's own except swallowed the error and the block vanished from the message."""
    def boom(*_a, **_k):
        raise ValueError("renderer bug")
    monkeypatch.setattr(sr, "_promotion_message", boom)
    monkeypatch.setattr(sr, "_silent_failures_message", boom)
    monkeypatch.setattr(sr, "_loser_message", boom)
    head, fold, meta = _render()
    assert "shadow_orb_5m" in fold and "magna53_lowcap" in fold          # the full ladder, not nothing
    assert fold.count("has not recurred") >= 38                           # the full error rows
    assert "5m refs the" in fold and "Legend:" in fold                    # the full losers section
    assert "bands" in head and "Crypto RS" in fold                        # the rest of the review still ran


def test_prior_metrics_that_came_back_as_a_json_string_still_compare():
    """`metrics` is a jsonb column; an older double-encoded row reads back as a STRING. The comparison
    decodes it (and a string that will not decode is 'not found' - the section prints). RED on origin/main (no such helper);
    MUTATION M2 also reddens the `_changed` half."""
    prior = {"metrics": json.dumps({"crypto": {"verdict": "V"}})}
    assert sr._prior_value(prior, "metrics", "crypto", "verdict") == (True, "V")
    assert sr._prior_value({"metrics": "{not json"}, "metrics", "crypto") == (False, None)
    assert sr._prior_value(None, "metrics") == (False, None)
    assert sr._prior_value({"metrics": {"a": None}}, "metrics", "a") == (True, None)    # present-but-null is found
    assert sr._changed(False, 1, 1) == (True, "no prior")
    assert sr._changed(True, 1, 1) == (False, "unchanged")
    assert sr._changed(True, 1, 2)[0] is True and "changed:" in sr._changed(True, 1, 2)[1]


def test_compose_report_names_the_unchanged_sections_on_the_checked_line():
    """The unchanged group is the last clause of the one checked line; with nothing else checked it is
    still printed. RED on origin/main: `compose_report` had no `unchanged` parameter."""
    head, fold, meta = sr.compose_report("H", [], [], ["errors: none"], ["x"], [],
                                         unchanged=["bands HOLD", "winner capture 19%"],
                                         full_sections=["x", "y"],
                                         changes=[{"section": "s", "shown": False, "why": "w"}])
    assert head.splitlines()[-1] == ("_Also checked — errors: none · unchanged since last week: "
                                     "bands HOLD · winner capture 19%._")
    assert meta["full_md"] == "x\n\ny" and meta["fold_md"] == "x" and meta["changes"][0]["why"] == "w"
    alone, _f, _m = sr.compose_report("H", [], [], [], [], [], unchanged=["bands HOLD"])
    assert alone.splitlines()[-1] == "_Also checked — unchanged since last week: bands HOLD._"


def test_the_new_message_renders_to_balanced_chunked_html():
    """The send path is unchanged: head through md_to_html, fold inside ONE expandable quote, chunked
    for Telegram's size limit with the quote closed and reopened per chunk."""
    from shared.telegram_format import chunk_html
    head, fold, meta = _render()
    html = sr.render_review_html(head, fold)
    assert html.count("<blockquote expandable>") == 1 and html.endswith("</blockquote>")
    chunks = chunk_html(html)
    assert 1 <= len(chunks) <= 3
    for c in chunks:
        assert c.count("<blockquote expandable>") == c.count("</blockquote>")
        assert c.count("<b>") == c.count("</b>")
    assert "<pre>" not in html and "`" not in html.split("<blockquote expandable>", 1)[1]


# -- the preview probe -----------------------------------------------------------------------------

def test_the_preview_probe_cannot_send_or_write(tmp_path):
    """The probe drives the REAL `run_weekly_review`. Every real sender and every real `mi_system_reviews`
    writer is replaced by a tripwire BEFORE the probe installs its captures: if the probe forgot to swap
    one, the tripwire fires and this reddens. What the review tried to do is counted, not performed.
    RED on origin/main (no probe). Dropping the `insert_system_review` capture from `run_preview` makes
    the row tripwire fire."""
    import agents.market_intelligence.briefing as briefing
    from scripts.probes._700_review_noise import preview as pv
    wire = AsyncMock(side_effect=AssertionError("a REAL Telegram send was attempted"))
    row = AsyncMock(side_effect=AssertionError("a REAL mi_system_reviews write was attempted"))
    capture = h.ROOT / "scripts/probes/_700_review_noise/q1_reviews.out"
    with patch.object(sr, "send_telegram_message", wire), patch.object(briefing, "send_telegram_message", wire), \
            patch.object(sr, "insert_system_review", row), patch.object(dbmod, "insert_system_review", row):
        stats = pv.main(["--offline", str(capture), "--date", "2026-10-11", "--out", str(tmp_path / "out")])
        assert wire.await_count == 0 and row.await_count == 0
        with pytest.raises(AssertionError, match="--strict"):
            pv.main(["--offline", str(capture), "--date", "2026-10-11", "--out", str(tmp_path / "o2"),
                     "--strict"])
    assert stats["mode"] == "offline" and stats["sent"] == 1 and stats["inserts_captured"] == 1
    assert stats["sends_refused"] == 0                  # nothing reached the wire, so the muzzle had nothing to refuse
    assert stats["needs_me"] == 2 and stats["head_lines"] <= 6 and stats["fold_chars"] > 0
    out = tmp_path / "out"
    assert {p.name for p in out.iterdir()} == {"head.md", "fold.md", "full.md", "message.html", "stats.json"}
    assert "unavailable" in (out / "fold.md").read_text(encoding="utf-8")      # offline: render-time sections fail open
    assert len((out / "full.md").read_text(encoding="utf-8")) > len((out / "fold.md").read_text(encoding="utf-8"))
    assert json.loads((out / "stats.json").read_text(encoding="utf-8"))["sent"] == 1


def test_the_preview_probes_read_only_pool_refuses_anything_but_a_read():
    """DB mode wraps the pool: a plain SELECT/WITH passes, every write (and a WITH ... INSERT) raises.
    A `WITH ... INSERT` passes a bare startswith("WITH") check, which is why the keyword scan exists."""
    from scripts.probes._700_review_noise import preview as pv
    for ok in ("SELECT 1", "  select * from t where updated_at > $1", "WITH x AS (SELECT 1) SELECT * FROM x"):
        pv._guard(ok)
    for bad in ("INSERT INTO t VALUES (1)", "UPDATE t SET a = 1", "DELETE FROM t", "ALTER TABLE t ADD c int",
                "WITH x AS (INSERT INTO t VALUES (1) RETURNING 1) SELECT * FROM x", "TRUNCATE t"):
        with pytest.raises(pv.ReadOnlyViolation):
            pv._guard(bad)

    class Conn:
        def __init__(self):
            self.ran = []

        async def fetchrow(self, sql, *a):
            self.ran.append(sql)
            return {"ok": 1}

    async def go():
        conn = Conn()
        ro = pv._ReadOnlyConn(conn)
        assert await ro.fetchrow("SELECT 1") == {"ok": 1}
        with pytest.raises(pv.ReadOnlyViolation):
            await ro.fetchrow("DELETE FROM t RETURNING 1")
        return conn.ran
    assert asyncio.run(go()) == ["SELECT 1"]


def test_the_preview_probes_pool_guard_reaches_modules_that_bound_get_pool_by_name():
    """`cost_board` and `missed_outcomes` do `from ...db import get_pool` at import, so patching `db.get_pool`
    alone left them on the real, unguarded pool. The guard now patches every loaded module whose `get_pool`
    IS the original (derived from `sys.modules`) and restores them when the stack closes. MUTATION M19:
    `_patch_name_bound_pools` made a no-op - the two modules kept the real function."""
    from contextlib import ExitStack
    import agents.market_intelligence.cost_board as cost_board
    import agents.market_intelligence.missed_outcomes as missed_outcomes
    from scripts.probes._700_review_noise import preview as pv

    original = dbmod.get_pool
    assert cost_board.get_pool is original and missed_outcomes.get_pool is original   # the premise
    sentinel = object()
    with ExitStack() as stack:
        patched = pv._patch_name_bound_pools(stack, original, sentinel)
        assert cost_board.get_pool is sentinel and missed_outcomes.get_pool is sentinel
        assert "agents.market_intelligence.cost_board" in patched
        assert "agents.market_intelligence.missed_outcomes" in patched
    assert cost_board.get_pool is original and missed_outcomes.get_pool is original    # and put back


def test_spend_near_the_ceiling_is_flagged_on_the_checked_line():
    """Cutting the cost-envelope block from the message also cut its 🟠 flag at 80% of the budget, so spend
    nearing the ceiling read like spend far below it. The checked phrase now carries the percentage and the
    words once it is at 80% or more; an over-budget month is the head's Needs-you line instead.
    MUTATION M21: `near` forced False - the 80% case lost its flag."""
    from contextlib import ExitStack

    def run(cost, budget, over):
        with ExitStack() as stack:
            h.patch_render_inputs(stack, FX["render_inputs"])
            stack.enter_context(patch.object(sr, "_spend_envelope",
                                             AsyncMock(return_value=("t", cost, budget, over))))
            return asyncio.run(sr._assemble_report(_metrics(), SUMMARY, WS, TODAY,
                                                   prior=copy.deepcopy(FX["prior"])))

    head, _fold, _meta = run(120.0, 150.0, False)
    assert "spend: $120.00 of $150 (80%, near the ceiling)" in head
    head, _fold, _meta = run(119.0, 150.0, False)
    assert "spend: $119.00 of $150 ·" in head and "near the ceiling" not in head
    head, _fold, meta = run(160.0, 150.0, True)                          # over: the head's action line owns it
    assert "near the ceiling" not in head and "LLM spend $160.00 is OVER the $150 monthly budget" in head
    head, _fold, _meta = run(10.0, 0.0, False)
    assert "spend: $10.00 (no budget set)" in head
