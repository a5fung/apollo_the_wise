"""#240 cross-ticker synthesis — mechanical-grounding contract.

validate_cohorts is the load-bearing anti-confab layer (proto-#212 lesson:
mechanical grounding > LLM-on-LLM skepticism): LLM proposals only survive if
their members come from the real RS candidate list, are cohort-sized, and are
not a restatement of an existing live theme.
"""
from agents.market_intelligence.theme_synthesis import validate_cohorts

_CANDS = {"RCAT", "AVAV", "KTOS", "RDW", "ASPI", "OKTA", "CRWD", "DDOG", "TWLO"}


def _cohort(name="Drone Defense Spending", tickers=("RCAT", "AVAV", "KTOS"),
            thesis="Govt drone funding lifts the group", confidence="medium"):
    return {"name": name, "tickers": list(tickers), "thesis": thesis,
            "confidence": confidence}


def test_valid_cohort_passes():
    kept, dropped = validate_cohorts([_cohort()], _CANDS, {})
    assert len(kept) == 1 and not dropped
    assert kept[0]["tickers"] == ["RCAT", "AVAV", "KTOS"]


def test_hallucinated_member_drops_cohort():
    # The RUM-class failure: a name the LLM invented that is NOT in the RS data.
    kept, dropped = validate_cohorts(
        [_cohort(tickers=("RCAT", "AVAV", "ZZFAKE"))], _CANDS, {})
    assert kept == [] and "ZZFAKE" in dropped[0]


def test_too_small_cohort_drops():
    kept, dropped = validate_cohorts([_cohort(tickers=("RCAT", "AVAV"))], _CANDS, {})
    assert kept == [] and "2 members" in dropped[0]


def test_live_theme_restatement_drops():
    live = {"Defense Drones": {"RCAT", "AVAV", "KTOS", "RDW"}}
    kept, dropped = validate_cohorts([_cohort()], _CANDS, live)
    assert kept == [] and "restates live theme" in dropped[0]


def test_partial_live_overlap_below_threshold_passes():
    # 1/3 members in a live theme (< 60%) — still an emerging story.
    live = {"Defense Drones": {"RCAT"}}
    kept, _ = validate_cohorts([_cohort()], _CANDS, live)
    assert len(kept) == 1


def test_caps_at_three_cohorts_and_dedupes_members():
    cohorts = [
        _cohort(name=f"Cohort {i}", tickers=("OKTA", "CRWD", "DDOG", "OKTA"))
        for i in range(5)
    ]
    kept, _ = validate_cohorts(cohorts, _CANDS, {})
    assert len(kept) == 3
    assert kept[0]["tickers"] == ["OKTA", "CRWD", "DDOG"]  # deduped, order kept
