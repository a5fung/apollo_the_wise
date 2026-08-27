"""EP alert: the catalyst grade and the alert tier are TWO axes, and the alert must say which
one acted (OKTA 2026-08-27 operator triage).

The defect: one live alert stated three mutually inconsistent things — header "Judge: HIGH
(hold)", judge prose "Demoted from gamechanger…", footer "Floor: game changer … Judge: HIGH
hold ← authoritative". Underneath, `mi_audit_log` recorded `dir=demote` on `floor=HIGH
judge=HIGH`.

The two values that were being read as one:
  • `dir` in ep_grade_decision  = the judge's SELF-REPORTED `direction_vs_floor`. Raw model
    output; `_normalize_verdict` checks enum membership only, never agreement with
    tier-vs-floor_tier. The model answered it on the CATALYST-GRADE axis.
  • `(hold)` in the header      = DERIVED from TIER_RANK (score_tier vs baseline_floor_tier).
    Factual. HIGH vs HIGH → held. The header was never the bug.

`game_changer` is a CATALYST grade; `HIGH` is the top of the ALERT TIER scale. "Demoted from
gamechanger to HIGH" is a category error, so no formatter may put them on one ladder.

2026-08-27 second pass — THE WORD ITSELF. The first pass left "Claude floor" and "the floor's
HIGH" in the wording, so one word still did both jobs:
  • `baseline_floor_tier` = the ALERT TIER our score produced before the judge reviewed it,
  • "Floor: game changer (Claude)" = the CATALYST GRADE from the Claude grader.
He read them as one ladder, which is our naming defect and not his misreading. "floor" is now
BANNED from every operator-facing string (the identifiers and the DB column keep it). The
pre-judge tier is "our score"; the grade's owner is "the Claude grader". Both ratings appear
on every alert, each with its own name and its own setter, and an arrow never joins one of
each. Swept mechanically by test_no_operator_facing_string_says_floor below.
"""
import io
import re

from agents.market_intelligence.briefing import (
    format_grade_outcome_lines, format_grade_provenance, format_tier_verdict,
    resolve_headline_grade, resolve_why_attribution,
)

_RATIONALE = ("Demoted from gamechanger because a ~1-2% revenue beat and modest guide raise on "
              "a $23B mega-cap SaaS name is material but not transformative — this is a "
              "high-quality beat-and-raise, not a structural re-rating event.")

# The real 2026-08-27 alert. Judge leans demote on the CATALYST axis; the tier it set held at
# HIGH; the floor grade stayed game_changer because the earnings carve-out overruled the
# floor's own revenue safety net 7 seconds before the judge ever ran.
OKTA = {
    "ticker": "OKTA", "catalyst_quality": "game_changer", "gemini_validation": "strong",
    "score_tier": "HIGH", "baseline_floor_tier": "HIGH", "grade_engine_authority": "judge",
    "ep_score": 90, "judge_direction": "demote", "judge_grade": "strong",
    "judge_rationale": _RATIONALE,
    "floor_grade_kept": {
        "gate": "revenue safety net (no prior-year comparable extracted)",
        "effect": "would have cut the catalyst grade to routine",
        "by": "the earnings carve-out",
        "why": "beat estimate by 1.2%, guidance raised, high confidence",
        "grade": "game_changer",
    },
}

# A judge demote that ACTUALLY CARRIES: the judge cut the tier HIGH → MODERATE. Its own
# direction agrees with the tier move, and no keep-event ran.
CARRIED = {
    "ticker": "XYZ", "catalyst_quality": "strong", "gemini_validation": "strong",
    "score_tier": "MODERATE", "baseline_floor_tier": "HIGH", "grade_engine_authority": "judge",
    "judge_direction": "demote", "judge_grade": "strong",
    "judge_rationale": "Demoted: a $270M contract is a rounding error for a $600B mega-cap.",
    "floor_grade_kept": None,
}


def _render(ep):
    """The alert fragment the operator reads, in the order send_ep_alert emits it."""
    return "\n".join(
        [f"*{ep['ticker']}* {resolve_headline_grade(ep)[1]}"]
        + format_grade_outcome_lines(ep)
        + [f"_{resolve_why_attribution(ep)}{ep.get('judge_rationale', '')}_",
           format_grade_provenance(ep)]
    )


# ── the OKTA case: nothing the judge argued actually moved ───────────────────────────────
def test_okta_header_reports_the_tier_that_acted():
    assert resolve_headline_grade(OKTA)[1] == "Judge: alert tier HIGH (held)"


def test_okta_states_what_acted_before_any_model_prose():
    out = _render(OKTA)
    acted = out.index("⚖️ Acted:")
    assert acted < out.index(_RATIONALE), "the derived outcome must precede the judge's prose"
    line = out.splitlines()[1]
    assert "alert tier *HIGH* (our score said HIGH; the judge held it)" in line
    assert "catalyst grade *game-changing* (set by the Claude grader)" in line


def test_okta_names_the_carveout_and_its_reason_as_what_overruled_the_floor():
    out = _render(OKTA)
    assert "↩️ Recorded, did NOT act:" in out
    assert "the earnings carve-out left the catalyst grade unchanged" in out
    assert "beat estimate by 1.2%, guidance raised, high confidence" in out
    # …and it is attributed to the GRADER's OWN safety net, which is what the carve-out
    # actually overrode. It ran inside the catalyst grader, BEFORE the judge — it never
    # overrode the judge, and the alert must not claim it did.
    assert "the catalyst grader's revenue safety net" in out
    assert "carve-out" not in out.split("↩️")[0], "no carve-out claim on the ACTED line"


def test_keep_event_counterfactual_comes_from_the_event_not_the_formatter():
    # The extraction-failure fail-open never reached a verdict — the renderer must not
    # assert "would have cut it to routine" for it the way it does for the carve-out.
    ext = dict(OKTA, floor_grade_kept={
        "gate": "revenue safety net", "effect": "could not run",
        "by": "the extraction-failure fail-open",
        "why": "the revenue metrics extraction failed", "grade": "game_changer"})
    out = _render(ext)
    assert "the catalyst grader's revenue safety net could not run" in out
    assert "would have cut" not in out
    assert "the extraction-failure fail-open left the catalyst grade unchanged" in out


def test_keep_event_never_credited_with_a_grade_it_did_not_set():
    # The unconditional #533 final resolve runs AFTER every keep-event, so the alert's
    # catalyst_quality can differ from what the keep-event preserved. Attributing the final
    # value to the keep-event would repeat the very time-skew this fix is about.
    moved = dict(OKTA, catalyst_quality="strong", judge_grade="routine")
    out = _render(moved)
    assert ("the earnings carve-out left the catalyst grade at *game-changing*, which the "
            "catalyst-tier corrective then re-resolved to *strong*") in out
    # …and the ACTED line still reports the grade that is actually acting.
    assert "catalyst grade *strong* (set by the Claude grader)" in out


def test_okta_labels_the_judges_demote_as_the_view_that_did_not_carry():
    out = _render(OKTA)
    assert "the judge's note argues a *demote* — but the tier it set held at HIGH" in out
    assert "the judge read the catalyst as *strong* against the grader's *game-changing*" in out
    assert "the judge sets the alert tier, never the catalyst grade" in out


def test_okta_prose_is_attributed_as_reasoning_not_outcome():
    # We cannot control model wording — it will keep saying "demoted". The label plus the
    # ⚖️ Acted line above it are what keep the outcome unambiguous anyway.
    assert resolve_why_attribution(OKTA) == "Judge's reasoning: "
    assert _render(OKTA).count("Judge's reasoning: ") == 1


# ── a demote that CARRIES must read differently from one that is overruled ───────────────
def test_carried_demote_renders_the_real_tier_transition():
    assert resolve_headline_grade(CARRIED)[1] == "Judge: alert tier HIGH→MODERATE (demoted)"
    assert "alert tier *MODERATE* (our score said HIGH; the judge demoted it)" in _render(CARRIED)


def test_carried_demote_has_no_did_not_move_claim():
    out = _render(CARRIED)
    assert "the tier it set held at" not in out
    assert "did not move that way" not in out


def test_carried_and_overruled_demotes_are_distinguishable():
    # Same judge_direction='demote', same "Demoted…" prose opener — the rendering must differ.
    assert OKTA["judge_direction"] == CARRIED["judge_direction"] == "demote"
    assert _render(OKTA) != _render(CARRIED)
    assert "(held)" in _render(OKTA) and "(demoted)" in _render(CARRIED)


# ── the two scales may never be printed as one ladder ────────────────────────────────────
_GRADES = ("game_changer", "game changer", "game-changing", "strong", "routine", "mna",
           "merger/acquisition")
_TIERS = ("HIGH", "MODERATE", "none")


def test_no_transition_arrow_ever_mixes_a_grade_with_a_tier():
    for ep in (OKTA, CARRIED,
               dict(OKTA, score_tier="HIGH", baseline_floor_tier="MODERATE"),
               dict(OKTA, grade_engine_authority="floor"),
               dict(OKTA, judge_direction="promote", judge_grade="game_changer")):
        for arrow in re.findall(r"([^\s·*]+)\s*→\s*([^\s·*]+)", _render(ep)):
            assert all(side in _TIERS for side in arrow), f"mixed-axis transition {arrow}"
            assert not any(side in _GRADES for side in arrow), f"grade in a transition {arrow}"


def test_tier_verdict_only_ever_speaks_tiers():
    assert format_tier_verdict({"score_tier": "HIGH", "baseline_floor_tier": "HIGH"}) == "HIGH (held)"
    assert format_tier_verdict(
        {"score_tier": "HIGH", "baseline_floor_tier": "MODERATE"}) == "MODERATE→HIGH (promoted)"
    assert format_tier_verdict(
        {"score_tier": "MODERATE", "baseline_floor_tier": "HIGH"}) == "HIGH→MODERATE (demoted)"
    # Unknown floor → no arrow invented.
    assert format_tier_verdict({"score_tier": "HIGH"}) == "HIGH"


def test_every_axis_is_named_wherever_a_value_is_shown():
    out = _render(OKTA)
    assert "alert tier" in out and "catalyst grade" in out
    # The judge leg of the footer states the limit of its authority.
    assert "sets the tier, not the catalyst grade" in format_grade_provenance(OKTA)


# ── markdown safety: underscored grades must never reach Telegram raw ────────────────────
def test_no_raw_underscored_grade_reaches_the_message():
    # 'game_changer' unescaped breaks Markdown italics → Telegram 400 (briefing.py comment
    # at the EP-line formatter). Every grade rendered here is space-substituted or escaped.
    for ep in (OKTA, CARRIED, dict(OKTA, grade_engine_authority="floor")):
        body = "\n".join([resolve_headline_grade(ep)[1]]
                         + format_grade_outcome_lines(ep)
                         + [format_grade_provenance(ep)])
        assert "game_changer" not in body
        assert body.count("*") % 2 == 0, "unbalanced bold markers"


# ── nothing to report → no empty "did NOT act" block ─────────────────────────────────────
def test_clean_alert_has_no_did_not_act_block():
    clean = {"ticker": "AAA", "catalyst_quality": "strong", "score_tier": "HIGH",
             "baseline_floor_tier": "MODERATE", "grade_engine_authority": "judge",
             "judge_direction": "promote", "judge_grade": "strong", "floor_grade_kept": None}
    lines = format_grade_outcome_lines(clean)
    assert len(lines) == 1 and lines[0].startswith("⚖️ Acted:")


def test_score_authority_alert_still_states_what_acted():
    # grade_engine_authority is STORED as 'floor' — the enum is untouched. Only the words change.
    scored = {"ticker": "BBB", "catalyst_quality": "strong", "score_tier": "HIGH",
              "baseline_floor_tier": "HIGH", "grade_engine_authority": "floor"}
    assert format_grade_outcome_lines(scored)[0] == (
        "⚖️ Acted: alert tier *HIGH* (our score — the judge did not review it) · "
        "catalyst grade *strong* (set by the Claude grader)")


def test_fallback_authority_names_the_judge_failure():
    fb = dict(OKTA, grade_engine_authority="fallback", floor_grade_kept=None)
    assert "(our score — the judge returned no verdict)" in format_grade_outcome_lines(fb)[0]


# ── the labels are DERIVED, not hardcoded (source-level pins) ─────────────────────────────
_EP_SRC = io.open("agents/market_intelligence/ep_detector.py", encoding="utf-8").read()
_BRIEF_SRC = io.open("agents/market_intelligence/briefing.py", encoding="utf-8").read()


def test_keep_label_is_set_from_the_decision_branch_not_the_deduped_audit_emit():
    # The carve-out DECISION (_downgrade_reason = None) re-runs every 5-min scan tick; its
    # audit emit is deduped per-ticker-per-day. Sourcing the label from the emit would blank
    # it on every tick after the first, silently changing the alert mid-morning.
    for stanza in re.findall(r"_floor_grade_kept = \{.*?\n\s*\}", _EP_SRC, re.S):
        head = _EP_SRC[:_EP_SRC.index(stanza)]
        assert "_should_log_catalyst_earnings_event_today" not in head.rsplit("\n\n", 1)[-1]
    # All three keep-events that can preserve the floor grade set the label, each naming
    # itself — a mechanism that did not fire can never be reported as the one that did.
    assert _EP_SRC.count("_floor_grade_kept = {") == 3
    for by in ("the earnings carve-out", "the live prior-year revenue lookup",
               "the extraction-failure fail-open"):
        assert f'"by": "{by}"' in _EP_SRC
    # Each record carries its OWN counterfactual + the grade as preserved, so neither is
    # inferred by the formatter (the extraction-failure branch has no counterfactual to give).
    assert _EP_SRC.count('"effect": "would have cut the catalyst grade to routine",') == 2
    assert _EP_SRC.count('"effect": "could not run",') == 1
    assert _EP_SRC.count('"grade": catalyst_quality,') == 3


def test_an_applied_downgrade_clears_the_keep_label():
    assert re.search(r'if _downgrade_reason:\n(\s*#.*\n)*\s*_floor_grade_kept = None', _EP_SRC)


def test_alert_dict_carries_the_display_fields():
    assert '"floor_grade_kept": _floor_grade_kept,' in _EP_SRC
    assert 'r["judge_direction"] = v.get("direction_vs_floor")' in _EP_SRC
    assert 'r["judge_grade"] = v.get("grade")' in _EP_SRC


def test_outcome_block_is_emitted_above_the_italic_rationale():
    body = _BRIEF_SRC[_BRIEF_SRC.index("async def send_ep_alert"):]
    assert body.index("_outcome_block") < body.index("_why_label}{_why_text}")


# ── THE WORD: "floor" is banned from everything he reads ──────────────────────────────────
#
# Operator, verbatim: "why is it called floor, what floor? Then it says 'floor: game changer'
# yet you say it rates it high, moderate, or nothing, then how is there gamechanger?" — one
# word was naming the pre-judge ALERT TIER and the CATALYST GRADE's owner. Identifiers and the
# `baseline_floor_tier` column keep the name; nothing rendered may.
_JUDGE_ROW = {"ticker": "OKTA", "judge_direction": "demote", "baseline_floor_tier": "HIGH",
              "judge_tier": "HIGH", "judge_materiality_tier": "material", "gap_pct": 12.0,
              "judge_rationale": "Demoted from gamechanger; material but not transformative."}


def _every_rendered_surface() -> dict:
    """Every operator-facing string this defect touches, keyed by the surface he sees it on."""
    from agents.market_intelligence.briefing import (
        _build_judge_delta_message, format_alert_tier_clause, format_catalyst_grade,
    )
    from agents.market_intelligence.ep_grade_judge import format_tier_transition
    from agents.market_intelligence.judge_review import aggregate_judge_review, format_judge_review

    review_rows = [dict(_JUDGE_ROW, alert_date="2026-08-27", score_tier="HIGH",
                        fwd_5d_pct=9.0, grounded_text="", realized_pnl=None, traded=None)]
    out = {
        "ep alert (OKTA)": _render(OKTA),
        "ep alert (carried demote)": _render(CARRIED),
        "ep alert (our score kept authority)": _render(dict(OKTA, grade_engine_authority="floor")),
        "ep alert (judge returned nothing)": _render(dict(OKTA, grade_engine_authority="fallback")),
        "judge delta digest (shadow)": _build_judge_delta_message(
            [_JUDGE_ROW], authority_on=False, date_str="Aug 27"),
        "judge delta digest (load-bearing)": _build_judge_delta_message(
            [dict(_JUDGE_ROW, judge_tier="MODERATE")], authority_on=True, date_str="Aug 27"),
        "monthly judge review": format_judge_review(aggregate_judge_review(review_rows), 30),
        "tier transition (moved)": format_tier_transition("MODERATE", "HIGH"),
        "tier transition (held)": format_tier_transition("HIGH", "HIGH"),
        "catalyst grade words": " ".join(
            format_catalyst_grade(g) for g in ("game_changer", "strong", "routine", "mna")),
    }
    # /why and /setup print the SAME clause (they call this one renderer — pinned below).
    for auth in ("judge", "floor", "fallback"):
        out[f"/why + /setup tier clause ({auth})"] = format_alert_tier_clause(
            {"score_tier": "HIGH", "baseline_floor_tier": "MODERATE",
             "grade_engine_authority": auth}, bold=False)
    return out


def test_no_operator_facing_string_says_floor():
    for surface, text in _every_rendered_surface().items():
        assert "floor" not in text.lower(), f"the banned word survives on: {surface}\n{text}"


def test_no_raw_enum_reaches_any_operator_facing_string():
    # The same rule that keeps 'game_changer' out also keeps 'grade_engine_authority' values
    # ('floor'/'fallback') and the underscored grade out of every surface.
    for surface, text in _every_rendered_surface().items():
        assert "game_changer" not in text, surface
        assert "grade_engine_authority" not in text, surface


# ── BOTH ratings, each with its own name and its own setter ───────────────────────────────
def test_both_ratings_appear_with_their_own_name_and_setter():
    for ep in (OKTA, CARRIED, dict(OKTA, grade_engine_authority="floor"),
               dict(OKTA, grade_engine_authority="fallback")):
        acted = format_grade_outcome_lines(ep)[0]
        # the TIER: named, and the thing that set it is named
        assert "alert tier" in acted
        assert ("the judge" in acted or "our score" in acted)
        # the GRADE: named, and its setter is named — and it is NEVER the judge
        assert "catalyst grade" in acted and "set by the Claude grader" in acted


def test_the_judge_is_never_shown_as_setting_the_catalyst_grade():
    out = _render(OKTA)
    assert "the judge sets the alert tier, never the catalyst grade" in out
    assert "sets the tier, not the catalyst grade" in format_grade_provenance(OKTA)


def test_perplexity_is_labelled_as_setting_nothing():
    assert "second opinion, sets nothing" in format_grade_provenance(OKTA)


def test_the_tier_clause_names_who_set_the_tier_in_all_three_authorities():
    from agents.market_intelligence.briefing import format_alert_tier_clause
    base = {"score_tier": "HIGH", "baseline_floor_tier": "MODERATE"}
    assert format_alert_tier_clause(dict(base, grade_engine_authority="judge"), bold=False) == (
        "alert tier HIGH (our score said MODERATE; the judge promoted it)")
    assert format_alert_tier_clause(dict(base, grade_engine_authority="floor"), bold=False) == (
        "alert tier HIGH (our score — the judge did not review it)")
    assert format_alert_tier_clause(dict(base, grade_engine_authority="fallback"), bold=False) == (
        "alert tier HIGH (our score — the judge returned no verdict)")


# ── plain words: a label he cannot act on is noise ────────────────────────────────────────
def test_catalyst_grade_renders_in_plain_words_everywhere():
    from agents.market_intelligence.briefing import format_catalyst_grade
    assert format_catalyst_grade("game_changer") == "game-changing"
    assert format_catalyst_grade("strong") == "strong"
    assert format_catalyst_grade("routine") == "routine"
    # NOT "M&A": llm_health sends parse_mode="HTML", where a bare & is invalid markup.
    assert format_catalyst_grade("mna") == "merger/acquisition"
    assert format_catalyst_grade(None, default="?") == "?"
    # An unknown value still never leaks an underscore.
    assert "_" not in format_catalyst_grade("some_new_grade")


def test_headline_catalyst_branch_uses_the_plain_words():
    hg = resolve_headline_grade({"catalyst_quality": "game_changer",
                                 "grade_engine_authority": "floor"})[1]
    assert hg == "Game-changing catalyst"


# ── the two scales may never be printed as one ladder — now across EVERY surface ──────────
def test_no_transition_arrow_anywhere_mixes_a_grade_with_a_tier():
    for surface, text in _every_rendered_surface().items():
        for arrow in re.findall(r"([^\s·*]+)\s*→\s*([^\s·*]+)", text):
            assert all(side in _TIERS for side in arrow), f"mixed-axis transition {arrow} on {surface}"
            assert not any(side in _GRADES for side in arrow), f"grade in a transition on {surface}"


def test_judge_delta_digest_draws_its_arrow_from_the_tiers_not_the_judges_word():
    from agents.market_intelligence.briefing import _build_judge_delta_message
    # The OKTA row: the judge's own word says demote, the tier it set held at HIGH.
    held = _build_judge_delta_message([_JUDGE_ROW], authority_on=False, date_str="Aug 27")
    assert "= `OKTA` HIGH (alert tier held)" in held
    assert "▼ `OKTA`" not in held, "the judge's word must not be drawn as a tier move"
    assert "judge's note: demote" in held, "…but it must still be reported, labelled"
    # A demote that really carried keeps its ▼ and states the transition tier→tier.
    moved = _build_judge_delta_message([dict(_JUDGE_ROW, judge_tier="MODERATE")],
                                       authority_on=False, date_str="Aug 27")
    assert "▼ `OKTA` HIGH→MODERATE" in moved
    assert "judge's note" not in moved, "no note when the word and the tier agree"


def test_judge_delta_digest_names_its_axis():
    from agents.market_intelligence.briefing import _build_judge_delta_message
    msg = _build_judge_delta_message([_JUDGE_ROW], authority_on=False, date_str="Aug 27")
    assert "ALERT TIER only — the judge does not set the catalyst grade" in msg


# ── /why and /setup must go through the ONE renderer, not re-derive it ────────────────────
_AGENT_SRC = io.open("agents/market_intelligence/agent.py", encoding="utf-8").read()


def test_why_and_setup_call_the_shared_tier_renderer():
    # Both surfaces built their own transition string, which is how the banned word survived
    # in three places after the first pass. One renderer or the drift comes back.
    assert _AGENT_SRC.count("format_alert_tier_clause({") == 2   # the /why + /setup call sites
    for dead in ("alert tier: floor", "held at floor", "from floor "):
        assert dead not in _AGENT_SRC


def test_why_and_setup_show_the_catalyst_grade_with_its_own_setter():
    assert "set by the Claude grader" in _AGENT_SRC
    assert "the judge does not set it" in _AGENT_SRC
