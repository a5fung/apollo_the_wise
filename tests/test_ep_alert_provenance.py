"""EP alert grade-coherence (6/17 operator triage). Since the judge is load-bearing (#249), the
alert must resolve to the JUDGE verdict and show HOW each rating was reached (where Perplexity
fits) — not headline a contradicted catalyst grade (LZB: grade 'routine' under a judge-promoted
HIGH) nor print a stale 'Claude + Perplexity agree' line after a post-agreement downgrade.

2026-08-27: the word "floor" is gone from every rendered string (it named BOTH the pre-judge
alert tier and the catalyst grade's owner). The pre-judge tier is "our score"; the grade is set
by "the Claude grader". The `baseline_floor_tier` fixtures keep the COLUMN name.

Pins the pure formatters: _judge_direction, resolve_headline_grade, format_grade_provenance.
"""
from agents.market_intelligence.briefing import (
    _judge_direction, resolve_headline_grade, format_grade_provenance,
    resolve_why_text, format_judge_trace_suffix,
)

# The three real 6/17 alerts (in-memory dict shape send_ep_alert receives).
QURE = {"ticker": "QURE", "catalyst_quality": "game_changer", "gemini_validation": "routine",
        "score_tier": "HIGH", "baseline_floor_tier": "HIGH", "grade_engine_authority": "judge"}
JBL = {"ticker": "JBL", "catalyst_quality": "game_changer", "gemini_validation": "strong",
       "score_tier": "HIGH", "baseline_floor_tier": "HIGH", "grade_engine_authority": "judge"}
LZB = {"ticker": "LZB", "catalyst_quality": "routine", "gemini_validation": "strong",
       "score_tier": "HIGH", "baseline_floor_tier": "MODERATE", "grade_engine_authority": "judge"}


# ── _judge_direction ─────────────────────────────────────────────────────────
def test_direction_promote_hold_demote():
    assert _judge_direction("HIGH", "MODERATE") == "promote"
    assert _judge_direction("HIGH", "HIGH") == "hold"
    assert _judge_direction("MODERATE", "HIGH") == "demote"
    assert _judge_direction("none", "MODERATE") == "demote"


def test_direction_none_on_unknown_tier():
    assert _judge_direction("HIGH", None) is None
    assert _judge_direction("WAT", "HIGH") is None


# ── resolve_headline_grade — resolves to the judge when load-bearing ──────────
def test_headline_leads_with_judge_when_load_bearing():
    # LZB: catalyst grade 'routine' but judge promoted the tier to HIGH → headline must be the
    # judge's tier verdict,
    # NEVER 'Routine' (the contradiction the operator flagged).
    # 2026-08-27: the label now NAMES its axis and draws the arrow tier→tier, so a catalyst
    # grade can never be read as one end of the transition (the OKTA category error).
    _, label = resolve_headline_grade(LZB)
    assert label == "Judge: alert tier MODERATE→HIGH (promoted)"
    assert "routine" not in label.lower() and "Routine" not in label


def test_headline_hold_when_judge_agrees_with_our_score():
    # No arrow when nothing moved — "held", past tense, on the named axis.
    assert resolve_headline_grade(QURE)[1] == "Judge: alert tier HIGH (held)"
    assert resolve_headline_grade(JBL)[1] == "Judge: alert tier HIGH (held)"
    assert "→" not in resolve_headline_grade(QURE)[1]


def test_headline_falls_back_to_the_catalyst_grade_when_not_judge():
    # The our-score branch names its axis too — the slot used to hold a bare tier on one alert
    # and a bare catalyst grade on the next, which is what let the two scales blur.
    # (grade_engine_authority is STORED as 'floor'; the enum is untouched, only the words changed.)
    scored = {"catalyst_quality": "strong", "grade_engine_authority": "floor"}
    assert resolve_headline_grade(scored)[1] == "Strong catalyst"


# ── format_grade_provenance — the Perplexity cross-check ONLY, no stale 'agree' ───
# 2026-08-27: the catalyst-grade and judge legs moved OUT of this line. Both ratings and their
# setters are stated once by format_grade_outcome_lines directly above it; the duplicate legs
# were the bulk the operator objected to, and two independently-worded copies of "who sets
# what" is how the retracted "advisory" claim survived in three places.
def test_provenance_carries_only_the_perplexity_cross_check():
    p = format_grade_provenance(LZB)
    assert p == "🔎 Perplexity: *strong* — differs, no score boost"
    assert "Claude grader" not in p and "Judge" not in p


def test_provenance_no_false_agree_on_lzb_stale_case():
    # The exact bug: LZB printed 'Claude + Perplexity agree' after strong→routine downgrade left
    # the multiplier stale. The provenance line compares FINAL grades → must say differs.
    assert "agrees" not in format_grade_provenance(LZB)
    assert "differs, no score boost" in format_grade_provenance(LZB)


def test_provenance_states_what_the_agreement_actually_did():
    """2026-08-27: "second opinion, sets nothing" was wrong. Agreement sets
    confidence_multiplier=1.2, which multiplies into the EP score — 61 of 147 alerts carried it
    in the 60 days to 2026-08-27. The line must state the effect, not deny it."""
    agree = {"catalyst_quality": "strong", "gemini_validation": "strong",
             "confidence_multiplier": 1.2, "score_tier": "HIGH",
             "baseline_floor_tier": "HIGH", "grade_engine_authority": "judge"}
    assert format_grade_provenance(agree) == "🔎 Perplexity: *strong* — agrees, score ×*1.2*"
    # …and when the hedge-downgrade cancelled the boost, say THAT rather than claiming 1.2x.
    cancelled = dict(agree, confidence_multiplier=1.0)
    assert "agrees, but boost cancelled" in format_grade_provenance(cancelled)


def test_provenance_never_claims_perplexity_sets_nothing():
    """The retracted claim. Perplexity's grade multiplies the score on agreement and its hedge
    text cuts the catalyst grade a notch — both live."""
    for ep in ({"catalyst_quality": "strong", "gemini_validation": "strong",
                "confidence_multiplier": 1.2},
               {"catalyst_quality": "routine", "gemini_validation": "strong"}):
        assert "sets nothing" not in format_grade_provenance(ep)


def test_provenance_is_empty_when_there_is_no_second_opinion():
    # Nothing unique left to say → emit nothing rather than a line restating the ⚖️ block.
    assert format_grade_provenance(
        {"catalyst_quality": "routine", "grade_engine_authority": "floor"}) == ""


# ── #329-trace: resolve_why_text — lead the italic with the JUDGE rationale ───
def test_why_leads_with_judge_rationale_when_authoritative():
    ep = dict(LZB, judge_rationale="Transformative deal vs a $120M micro-cap; theme hot.",
              claude_analysis="the grader's weaker take")
    assert resolve_why_text(ep) == "Transformative deal vs a $120M micro-cap; theme hot."


def test_why_falls_back_to_the_grader_analysis_when_not_judge():
    ep = {"grade_engine_authority": "floor", "claude_analysis": "grader analysis",
          "judge_rationale": "should be ignored"}
    assert resolve_why_text(ep) == "grader analysis"


def test_why_falls_back_when_judge_has_no_rationale():
    # Authoritative judge but empty rationale → don't blank the alert; show the grader's analysis.
    ep = dict(LZB, judge_rationale="  ", claude_analysis="grader analysis")
    assert resolve_why_text(ep) == "grader analysis"
    assert resolve_why_text({"grade_engine_authority": "judge"}) == ""  # nothing at all → empty


# ── #329-trace: format_judge_trace_suffix — divergence cues on the fire line ──
def test_trace_suffix_includes_materiality_and_source():
    s = format_judge_trace_suffix({"judge_materiality_tier": "transformative", "has_direct_source": True})
    assert s == " · materiality transformative · direct-source present"


def test_trace_suffix_partial_and_empty():
    assert format_judge_trace_suffix({"judge_materiality_tier": "minor"}) == " · materiality minor"
    assert format_judge_trace_suffix({"has_direct_source": True}) == " · direct-source present"
    assert format_judge_trace_suffix({}) == ""               # byte-identical fire line when absent
    assert format_judge_trace_suffix({"has_direct_source": False}) == ""
