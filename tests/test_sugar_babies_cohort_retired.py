"""Sugar Babies cohort retired 2026-11-09 (operator): no scheduler job, no /sugarbabies handler."""
from agents.market_intelligence import agent as agent_mod
from agents.market_intelligence import db, scheduler


def test_scheduler_no_longer_registers_the_cohort_refresh():
    assert not hasattr(scheduler, "_sugar_babies_cohort_refresh_job")
    assert not hasattr(scheduler, "JOB_SUGAR_BABIES_COHORT_REFRESH")


def test_the_sugarbabies_handler_and_cohort_list_query_are_gone():
    cls = agent_mod.MarketIntelligenceAgent
    assert not hasattr(cls, "_handle_sugar_babies_query")
    assert not hasattr(db, "get_sugar_babies_cohort_latest")
