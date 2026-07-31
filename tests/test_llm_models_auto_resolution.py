"""#509 model auto-resolution — shared/llm_models.py's opt-in runtime layer.

Pins the design fork this card resolved: `scripts/preflight_judge_eval_gate.py`
runs on the HOST at deploy time and re-parses this file's SOURCE with `ast` — a
value computed by calling code is invisible to it. So:

  1. OPUS/SONNET/HAIKU and every role binding derived from them (JUDGE_MODEL
     included) MUST stay plain literals — never reassigned via the resolver.
     (tests/test_preflight_judge_eval_gate.py::test_extract_live_keys_matches_
     the_real_module_hash is the AST-level pin for this; these tests pin the
     runtime-value side.)
  2. Auto-resolution lives ENTIRELY behind `effective_model`/`role_resolution`,
     driven by the opt-in `RESOLVED_ROLES` map — untouched roles are
     byte-identical to their plain constant, always.
  3. `tier_of` recognises any concrete id in a tracked family (parser-based),
     not just the three pinned literals.
  4. `pricing_for` falls back to a resolved id's TIER rate (not the flat
     DEFAULT) when the exact id isn't in PRICING_PER_MTOK yet.
"""
from shared import llm_models
from shared.model_resolver import TierResolution


# ─── The gate constraint: constants stay plain literals ─────────────────────

def test_tier_constants_are_plain_literal_pins():
    assert llm_models.OPUS == llm_models.OPUS_PIN == "claude-opus-4-8"
    assert llm_models.SONNET == llm_models.SONNET_PIN == "claude-sonnet-4-6"
    assert llm_models.HAIKU == llm_models.HAIKU_PIN == "claude-haiku-4-5-20251001"


def test_judge_model_is_the_plain_pin_alias():
    # This is the exact value the AST-based deploy gate reads — it must be a
    # source-level literal-or-alias chain, never a call result.
    assert llm_models.JUDGE_MODEL == llm_models.OPUS_PIN


# ─── RESOLVED_ROLES scope ────────────────────────────────────────────────────

def test_the_divergence_model_is_NOT_auto_resolved():
    """THE scope pin, and the one that matters (operator opted all roles in
    2026-07-31).

    JUDGE_DIVERGENCE_MODEL is the #301 independent second read on the judge's
    verdict, and its whole value is being a DIFFERENT model/tier — "not just a
    cheaper rerun of the same model", per its own registry comment. If it
    tracked the resolver alongside JUDGE_MODEL, both would drift toward the same
    family generation and the independence that IS the check would quietly
    erode.

    This fails loud if someone "completes the set" later. That is the intended
    failure — the exclusion is deliberate, not an oversight.
    """
    assert "JUDGE_DIVERGENCE_MODEL" not in llm_models.RESOLVED_ROLES
    assert llm_models.effective_model("JUDGE_DIVERGENCE_MODEL") == \
        llm_models.JUDGE_DIVERGENCE_MODEL
    assert llm_models.role_resolution("JUDGE_DIVERGENCE_MODEL") is None


def test_every_other_role_binding_IS_tracked():
    """The operator's "opt all in" — a role added to the registry later that
    nobody opts in is exactly the staleness this replaced (theme advisor
    stranded on opus-4-6; METRICS_EXTRACTION_MODEL still on a 2026-06-09 pin).
    """
    for role in ("JUDGE_MODEL", "THEME_MODEL", "THEME_ADVISOR_MODEL",
                 "SYNTHESIS_MODEL", "COMPRESSION_MODEL",
                 "METRICS_EXTRACTION_MODEL", "GROUNDED_GRADE_MODEL",
                 "MATERIALITY_MODEL", "CATALYST_TYPE_MODEL"):
        assert role in llm_models.RESOLVED_ROLES, f"{role} left behind"


def test_unknown_role_name_effective_model_is_empty_not_a_crash():
    assert llm_models.effective_model("NOT_A_REAL_ROLE") == ""
    assert llm_models.role_resolution("NOT_A_REAL_ROLE") is None


# ─── effective_model / role_resolution for a RESOLVED_ROLES role ────────────
# _ROLE_RESOLUTIONS is computed once at import; these tests inject a fake
# TierResolution directly rather than re-exercising resolve_tier's own
# precedence chain (already covered by tests/test_model_resolver.py) —
# they pin that the ACCESSOR reads it correctly.

def test_effective_model_reads_role_resolutions(monkeypatch):
    fake = TierResolution("opus", "claude-opus-5", "cache",
                          "2026-07-30T00:00:00+00:00", "cache newer than pin")
    monkeypatch.setitem(llm_models._ROLE_RESOLUTIONS, "JUDGE_MODEL", fake)
    assert llm_models.effective_model("JUDGE_MODEL") == "claude-opus-5"
    assert llm_models.role_resolution("JUDGE_MODEL") is fake


def test_effective_model_falls_back_when_resolution_is_pin(monkeypatch):
    fake = TierResolution("opus", llm_models.OPUS_PIN, "pin", None, "no resolution cache")
    monkeypatch.setitem(llm_models._ROLE_RESOLUTIONS, "JUDGE_MODEL", fake)
    assert llm_models.effective_model("JUDGE_MODEL") == llm_models.OPUS_PIN


def test_ep_grade_judge_binds_to_effective_model_at_import():
    # The one real call site #509 actually drives — pin that it used the
    # accessor, not the raw constant, at its own import time.
    from agents.market_intelligence import ep_grade_judge
    assert ep_grade_judge.MODEL == llm_models.effective_model("JUDGE_MODEL")


# ─── tier_of: parser-based, recognises any family member ────────────────────

def test_tier_of_recognises_pinned_and_legacy_ids():
    assert llm_models.tier_of(llm_models.OPUS) == "opus"
    assert llm_models.tier_of(llm_models.SONNET) == "sonnet"
    assert llm_models.tier_of(llm_models.HAIKU) == "haiku"
    # legacy pins parse fine too — they're just not RESOLVED_ROLES-tracked
    assert llm_models.tier_of(llm_models.OPUS_4_7) == "opus"
    assert llm_models.tier_of(llm_models.SONNET_4_5) == "sonnet"


def test_tier_of_recognises_a_genuinely_newer_unpinned_release():
    # The exact scenario the old exact-3-value map got wrong (advisor catch):
    # a release NEWER than anything pinned must still be attributed correctly.
    assert llm_models.tier_of("claude-opus-5") == "opus"


def test_tier_of_none_for_unparseable():
    assert llm_models.tier_of("claude-fable-5") is None
    assert llm_models.tier_of("gpt-4") is None
    assert llm_models.tier_of("") is None


# ─── pricing_for ─────────────────────────────────────────────────────────────

def test_pricing_for_exact_match():
    assert llm_models.pricing_for(llm_models.OPUS) == {"input": 5.00, "output": 25.00}
    assert llm_models.pricing_for(llm_models.SONNET) == {"input": 3.00, "output": 15.00}
    assert llm_models.pricing_for("sonar-pro") == {"input": 3.00, "output": 15.00}


def test_pricing_for_unpinned_release_falls_back_to_tier_rate():
    # claude-opus-5 is not a key in PRICING_PER_MTOK — must price at opus's
    # rate, NOT silently fall to DEFAULT_PRICING_PER_MTOK ($3/$15, the Sonnet
    # rate) which would understate a real Opus call's cost.
    price = llm_models.pricing_for("claude-opus-5")
    assert price == llm_models.PRICING_PER_MTOK[llm_models.OPUS_PIN]
    assert price != llm_models.DEFAULT_PRICING_PER_MTOK


def test_pricing_for_totally_unknown_id_falls_back_to_default():
    assert llm_models.pricing_for("gpt-4-turbo") == llm_models.DEFAULT_PRICING_PER_MTOK
    assert llm_models.pricing_for("claude-fable-5") == llm_models.DEFAULT_PRICING_PER_MTOK
