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

2026-08-27 third pass — WHAT THE JUDGE'S CATALYST READ DOES. The second pass printed that
read under "Recorded, did NOT act" as "advisory only; the judge sets the alert tier, never
the catalyst grade". That was WRONG and this file pinned it. The judge weighs the catalyst to
reach the tier it sets, so its read ACTS — through the tier. OMER 2026-08-13 is the proof:
stored label `routine`, our score MODERATE, judge read the catalyst as better and set HIGH.
The only thing the judge never does is relabel `catalyst_quality`. The alert now says exactly
that on the CATALYST line, and the duplicate "who set what" legs were removed from the
provenance footer (operator: "crystal clear on all this without adding overall bulk").
Account: docs/analysis/judge_authority_2026-08-27.md.
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
    assert out.index("📊 Grader:") < out.index(_RATIONALE), \
        "the derived outcome must precede the judge's prose"
    # ONE VOICE PER LINE (operator 2026-08-27: "clarity, clear separation and not confusion").
    # Each party that read the catalyst says what IT said; the decision takes the last line.
    assert out.splitlines()[1:5] == [
        "📊 Grader: *game-changing*",
        "🔎 Perplexity: *strong* — differs, no score boost",
        "⚖️ Judge: *strong* (disagrees with the grader)",
        "✅ Decision: alert tier *HIGH* (our score said HIGH; the judge held it)",
    ]


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
    # …and the CATALYST line still reports the grade that is actually acting.
    assert "📊 Grader: *strong*" in out


def test_the_judges_catalyst_read_is_shown_as_acting_never_as_advisory():
    """The 2026-08-27 correction. The judge's read of the catalyst is the input to the tier it
    sets, so it may never be rendered as inert. `advisory` and `never the catalyst grade` are
    the two phrasings that were wrong; both are banned from the block."""
    out = _render(OKTA)
    assert "⚖️ Judge: *strong* (disagrees with the grader)" in out
    # The read must NOT sit in the did-not-act block.
    assert "⚖️ Judge:" not in out.split("↩️")[-1] or "↩️" not in out
    for banned in ("advisory", "never the catalyst grade", "sets nothing",
                   "the judge's note argues a *demote*"):
        assert banned not in out, f"retracted claim still rendered: {banned}"


def test_a_self_contradicting_direction_is_named_only_when_nothing_else_explains_it():
    """`direction_vs_floor` is specified TIER vs TIER, so `demote` under a held tier is the
    model contradicting itself. When the judge's catalyst read differs it already explains the
    wording — printing a second note about it is the bulk the operator objected to."""
    # OKTA: judge read (strong) differs from the label → explained, no extra note.
    assert "own direction field says" not in _render(OKTA)
    # Same row with the judge agreeing on the grade → nothing explains `demote`, so say it.
    unexplained = dict(OKTA, judge_grade="game_changer", floor_grade_kept=None)
    out = _render(unexplained)
    assert "the judge's own direction field says *demote* while the tier it set held at HIGH" in out
    assert "that field compares tiers" in out


def test_okta_prose_is_attributed_as_reasoning_not_outcome():
    # We cannot control model wording — it will keep saying "demoted". The label plus the
    # ⚖️ Acted line above it are what keep the outcome unambiguous anyway.
    assert resolve_why_attribution(OKTA) == "Judge's reasoning: "
    assert _render(OKTA).count("Judge's reasoning: ") == 1


# ── a demote that CARRIES must read differently from one that is overruled ───────────────
def test_carried_demote_renders_the_real_tier_transition():
    assert resolve_headline_grade(CARRIED)[1] == "Judge: alert tier HIGH→MODERATE (demoted)"
    assert ("✅ Decision: alert tier *MODERATE* (our score said HIGH; the judge demoted it)"
            in _render(CARRIED))


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


def test_every_line_names_exactly_one_voice():
    """The separation contract. A line may carry the Grader OR Perplexity OR the Judge OR the
    Decision — never two. Packing grader + judge + limit-of-authority into one sentence is
    what read as confusion (operator 2026-08-27)."""
    _VOICES = ("📊 Grader:", "🔎 Perplexity:", "⚖️ Judge:", "✅ Decision:")
    for ep in (OKTA, CARRIED, dict(OKTA, grade_engine_authority="floor")):
        for line in format_grade_outcome_lines(ep):
            if line.startswith("↩️") or line.startswith("   •"):
                continue
            hits = [v for v in _VOICES if line.startswith(v)]
            assert len(hits) == 1, f"line owns no single voice: {line}"
            for other in _VOICES:
                if other != hits[0]:
                    assert other not in line, f"two voices on one line: {line}"


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
    assert [l.split(":")[0] for l in lines] == ["📊 Grader", "⚖️ Judge", "✅ Decision"]
    assert "↩️" not in "".join(lines)   # no Perplexity read on this fixture → no line for it


def test_score_authority_alert_still_states_what_acted():
    # grade_engine_authority is STORED as 'floor' — the enum is untouched. Only the words change.
    scored = {"ticker": "BBB", "catalyst_quality": "strong", "score_tier": "HIGH",
              "baseline_floor_tier": "HIGH", "grade_engine_authority": "floor"}
    assert format_grade_outcome_lines(scored) == [
        "📊 Grader: *strong*",
        "✅ Decision: alert tier *HIGH* (our score — the judge did not review it)"]


def test_fallback_authority_names_the_judge_failure():
    fb = dict(OKTA, grade_engine_authority="fallback", floor_grade_kept=None)
    assert "(our score — the judge returned no verdict)" in "\n".join(
        format_grade_outcome_lines(fb))


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
        block = "\n".join(format_grade_outcome_lines(ep))
        # the TIER: named on the Decision line, and the thing that set it is named
        assert "✅ Decision: alert tier" in block
        assert ("the judge" in block or "our score" in block)
        # the GRADE: on its own line, owned by the grader
        assert "📊 Grader: *" in block


def test_the_judge_is_never_shown_as_relabelling_the_catalyst_grade():
    """The narrow, TRUE limit on the judge — it cannot rewrite `catalyst_quality`. The old
    version asserted the broader claim ("never the catalyst grade"), which read as "its
    catalyst view does not matter" and was wrong: that view sets the tier. With one voice per
    line the limit is shown structurally — the Grader line keeps its own value whatever the
    judge read."""
    out = _render(OKTA)
    assert "📊 Grader: *game-changing*" in out      # unchanged by the judge's *strong* read
    assert "⚖️ Judge: *strong*" in out


def test_perplexity_line_states_its_real_effect_not_that_it_sets_nothing():
    """2026-08-27: "second opinion, sets nothing" was wrong in the same way the judge's
    "advisory only" was. Agreement sets confidence_multiplier=1.2, which multiplies into the
    EP score — 61 of 147 alerts carried it in the 60d to 2026-08-27; and Perplexity's hedge
    text cuts the catalyst grade a notch (10 times since 2026-05-05)."""
    # OKTA: Perplexity read `strong` against the label `game_changer` → no boost earned.
    assert "🔎 Perplexity: *strong* — differs, no score boost" in _render(OKTA)
    assert "sets nothing" not in _render(OKTA)
    boosted = dict(OKTA, gemini_validation="game_changer", confidence_multiplier=1.2)
    assert "🔎 Perplexity: *game-changing* — agrees, score ×*1.2*" in _render(boosted)


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


# ── the judge's catalyst read must SURVIVE the alert (2026-08-27) ─────────────────────────
_DB_SRC = io.open("agents/market_intelligence/db.py", encoding="utf-8").read()


def test_the_judges_catalyst_read_is_persisted_not_just_held_in_memory():
    """Until 2026-08-27 `judge_grade` existed only on the in-memory alert dict, so the alert
    could show the judge's catalyst read and `/why` — reading the row back — could not. The
    read is what the corrected catalyst line is built from; if it is not stored, the
    correction is true for one render and gone afterwards."""
    assert "judge_grade = COALESCE(" in _DB_SRC, "the judge result UPDATE must write it"
    assert '"judge_grade TEXT"' in _DB_SRC, "_ensure_ep_alert_columns must add it"
    assert re.search(r'judge_grade=v\.get\("grade"\)', _EP_SRC), \
        "the detector must pass the judge's own grade to the writer"
    # …and the row read that feeds the operator surfaces must select it.
    assert re.search(r"judge_grade, judge_grade_reason, judge_tier_reason, catalyst_quality",
                     _DB_SRC)


def test_no_surface_calls_the_judges_catalyst_read_advisory():
    """The retracted claim, swept at source. `update_ep_alert_judge_result` not writing
    `catalyst_quality` was read as "the judge's catalyst view does not matter" — it sets the
    tier. Any surface reintroducing the word about the judge's grade read fails here."""
    for src, name in ((_BRIEF_SRC, "briefing.py"), (_EP_SRC, "ep_detector.py")):
        for line in src.splitlines():
            low = line.lower()
            if "advisory" in low and "judge" in low and "grade" in low:
                assert "2026-08-27" in line or "retracted" in low, \
                    f"{name}: judge grade read called advisory again — {line.strip()[:90]}"


def test_the_judges_read_comes_before_its_decision():
    """Operator 2026-08-27: "the judge needs to share its own judgement… then it needs to share
    its final judgement." The read always precedes the decision, whether it agrees or not."""
    for ep in (OKTA, dict(OKTA, judge_grade="game_changer", floor_grade_kept=None)):
        lines = format_grade_outcome_lines(ep)
        judge_at = next(i for i, l in enumerate(lines) if l.startswith("⚖️ Judge:"))
        decide_at = next(i for i, l in enumerate(lines) if l.startswith("✅ Decision:"))
        assert judge_at < decide_at
    # …and the judge's line says which way it went against the grader.
    assert "disagrees with the grader" in "\n".join(format_grade_outcome_lines(OKTA))
    assert "agrees with the grader" in "\n".join(format_grade_outcome_lines(
        dict(OKTA, judge_grade="game_changer")))


# ── #602: the judge's one-line WHY on each of its two calls ──────────────────────────────
_WHY = {"judge_grade_reason": "a 1.4% revenue beat on a $23B company is material but not "
                              "transformative",
        "judge_tier_reason": "a fresh, primary-sourced beat-and-raise clears HIGH"}


def test_each_judge_call_carries_its_own_one_line_why():
    """Operator 2026-08-27, signed: the judge states its read AND why it disagrees, then its
    final call AND why. Both whys come from the judge (`grade_reason` / `tier_reason`) — the
    renderer never composes one."""
    lines = format_grade_outcome_lines(dict(OKTA, **_WHY))
    judge = next(l for l in lines if l.startswith("⚖️ Judge:"))
    decide = next(l for l in lines if l.startswith("✅ Decision:"))
    assert judge.endswith("material but not transformative")
    assert decide.endswith("beat-and-raise clears HIGH")


def test_a_missing_why_drops_the_clause_and_never_invents_one():
    """Pre-#602 rows and fail-open verdicts have no reason stored. The line must render
    exactly as before rather than the renderer supplying a plausible sentence."""
    lines = format_grade_outcome_lines(OKTA)   # no *_reason keys
    assert "⚖️ Judge: *strong* (disagrees with the grader)" in lines
    assert not any(" — a " in l for l in lines if l.startswith(("⚖️ Judge:", "✅ Decision:")))


def test_the_why_is_escaped_and_clipped_before_telegram():
    """Model text on a Markdown surface: an unescaped underscore breaks italics -> 400."""
    nasty = dict(OKTA, judge_grade_reason="beat was game_changer *huge* " + "x" * 400)
    line = next(l for l in format_grade_outcome_lines(nasty) if l.startswith("⚖️ Judge:"))
    assert "game_changer" not in line
    assert line.count("*") % 2 == 0
    assert len(line) < 260


def test_the_rubric_states_each_output_fields_axis():
    """The root cause: rule 2 taught PROMOTES/DEMOTES as GRADE verbs while
    `direction_vs_floor` is a TIER field, so the model answered it on the grade axis (OKTA
    wrote `demote` while holding HIGH). v4 says raises/lowers the GRADE and spells out the
    tier field literally."""
    from agents.market_intelligence.ep_grade_judge import _RUBRIC, RUBRIC_VERSION
    assert RUBRIC_VERSION.startswith("v4-")
    assert "PROMOTES the grade" not in _RUBRIC and "DEMOTES it" not in _RUBRIC
    assert "RAISES the GRADE" in _RUBRIC and "LOWERS the GRADE" in _RUBRIC
    assert "describes the TIER AND NOTHING ELSE" in _RUBRIC
    assert "If you lowered the GRADE but kept the TIER, that is \"hold\"" in _RUBRIC


def test_a_missing_reason_never_kills_an_otherwise_valid_verdict():
    """`grade_reason`/`tier_reason` are schema-REQUIRED so the model fills them, but a model
    omission must not fail-open a real EP over a display field."""
    from agents.market_intelligence.ep_grade_judge import _normalize_verdict
    v = _normalize_verdict({"grade": "strong", "tier": "HIGH", "direction_vs_floor": "hold",
                            "fire_axes": ["catalyst"], "rationale": "r"})
    assert v is not None and v["grade_reason"] is None and v["tier_reason"] is None
