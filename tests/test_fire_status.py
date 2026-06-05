"""Unit tests for the fire panel status helper (#201).

`_compute_fire_status` is the SSoT for "did we SEE a fire?" — it gates nothing
(advisory) but drives the weekly fire-discovery guardrail, so it must be locked.
Key invariants:
  - a REAL fire (Pradeep #1–4 named types + the 'other' catch-all) at material
    grade = fire_seen — we must NEVER demote a real earnings/deal EP;
  - a material grade with a NON-confirmed fire type (unknown /
    pre_catalyst_anticipation / NULL) is NOT fire_seen → it populates the
    discovery guardrail (real_unknown vs no_fire_confirmed by had-inputs);
  - theme/narrative axes light fire_seen independent of catalyst;
  - the first pass (no catalyst_type arg) falls back to magnitude (fail-open).
"""
from agents.market_intelligence.ep_detector import _compute_fire_status


def _st(**kw):
    return _compute_fire_status(**kw)[0]


def test_real_fire_named_type_stays_fire_seen():
    # TTAN/AGX shape: real earnings beat graded strong, sales_acceleration.
    assert _st(in_theme=False, in_narrative=False, catalyst_quality="strong",
               catalyst_text="Q1 beat, revenue +40%, guidance raised",
               catalyst_type="sales_acceleration") == "fire_seen"
    assert _st(in_theme=False, in_narrative=False, catalyst_quality="game_changer",
               catalyst_text="federal policy mandate drives demand",
               catalyst_type="policy") == "fire_seen"
    # 'other' = a catalyst exists but uncategorized — still a fire (conservative).
    assert _st(in_theme=False, in_narrative=False, catalyst_quality="strong",
               catalyst_text="real but odd corporate event not in taxonomy",
               catalyst_type="other") == "fire_seen"


def test_unconfirmed_fire_types_flip_to_guardrail():
    # pre_catalyst_anticipation = anticipated, not realized → not a seen fire.
    assert _st(in_theme=False, in_narrative=False, catalyst_quality="strong",
               catalyst_text="running ahead of an expected FDA decision",
               catalyst_type="pre_catalyst_anticipation") == "no_fire_confirmed"
    # unknown = couldn't identify (graded big, no nameable fire).
    assert _st(in_theme=False, in_narrative=False, catalyst_quality="strong",
               catalyst_text="heavy volume, sector momentum, no clear driver",
               catalyst_type="unknown") == "no_fire_confirmed"
    # NULL = classifier failed → not a seen fire.
    assert _st(in_theme=False, in_narrative=False, catalyst_quality="game_changer",
               catalyst_text="some reasonably long catalyst text here ok",
               catalyst_type=None) == "no_fire_confirmed"


def test_theme_and_narrative_axes_light_independently():
    assert _st(in_theme=True, in_narrative=False, catalyst_quality="routine",
               catalyst_text="", catalyst_type="unknown") == "fire_seen"
    assert _st(in_theme=False, in_narrative=True, catalyst_quality="routine",
               catalyst_text="", catalyst_type="unknown") == "fire_seen"


def test_unknown_split_discovery_gap_vs_true_negative():
    # No fire, thin/empty inputs → real_unknown (discovery gap).
    assert _st(in_theme=False, in_narrative=False, catalyst_quality="routine",
               catalyst_text="", catalyst_type="unknown") == "real_unknown"
    # No fire, had real inputs but nothing material → no_fire_confirmed.
    assert _st(in_theme=False, in_narrative=False, catalyst_quality="routine",
               catalyst_text="A reasonably long real news blurb with details",
               catalyst_type="unknown") == "no_fire_confirmed"


def test_first_pass_falls_back_to_magnitude():
    # No catalyst_type arg (in-loop first pass) → magnitude-only fire_seen.
    assert _st(in_theme=False, in_narrative=False, catalyst_quality="strong",
               catalyst_text="x") == "fire_seen"
    assert _st(in_theme=False, in_narrative=False, catalyst_quality="routine",
               catalyst_text="") == "real_unknown"
