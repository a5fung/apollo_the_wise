"""A column declared and never once written was invisible to every check we had (#543).

Operator found `crypto_btc_dominance.slope_30d`: 97 rows since 2026-04-27, every one NULL,
three months unnoticed. Then: *"we need better dq checks for our tables and data, null checks at
the very least, anomaly detection, row counts, etc."*

**Most of that already existed** — `run_null_rate_sweep` (a populated column going null),
`run_job_liveness_sweep` (a job producing no rows), the #340 row-count drift sweep, and the
L1/L2/L3 anomaly system. `slope_30d` went through two specific holes:

1. `_evaluate_column` SKIPS always-null columns **by design** — its own docstring says
   *"always-null → None (never met the populated bar)"*. Correct for its job (catching a column
   that BROKE), and exactly why it cannot see one that was never wired.
2. `_NULL_SWEEP_TABLES` covers five tables. `crypto_btc_dominance` is not one of them.

So this sweep is the COMPLEMENT, not a replacement. A numeric column 100% NULL across its whole
history on a table with real rows is dead or unwired — **binary, not a rate**, which is what makes
it near-impossible to false-positive on.

First live run: **6 dead columns across 65 tables**, including `mi_stock_scores.market_cap` on
**455,506 rows**.
"""
import pathlib
import re

SRC = pathlib.Path("agents/market_intelligence/health_checks.py").read_text(encoding="utf-8")
SCHED = pathlib.Path("agents/market_intelligence/scheduler.py").read_text(encoding="utf-8")


def _fn() -> str:
    i = SRC.find("async def run_dead_column_sweep")
    assert i > 0, "the dead-column sweep is gone"
    return SRC[i:]


def test_it_detects_NEVER_populated_not_merely_sparse():
    """`count(col)` counts NON-NULL rows. Zero across the whole table is the definition of
    never-written — and it is a different question from the null-RATE sweep's."""
    body = _fn()
    assert re.search(r'count\("\{col\}"\)|count\(\\"', body) or 'count("{col}")' in body, (
        "the sweep no longer counts non-null values per column")


def test_it_announces_each_column_ONCE_EVER():
    """A build defect, not a daily condition. A column unwired today is unwired tomorrow, and
    re-announcing it nightly is exactly how a guard becomes noise and gets muted — the failure
    mode this repo threw away three checks for last week."""
    body = _fn()
    assert "dead_column_detected" in body
    assert "already" in body and "not in already" in body, (
        "the once-ever dedupe is gone — this will now nag every night")


def test_the_audit_log_IS_the_dedupe_state():
    """No new table, and the state survives a restart. Same pattern as `cost_new_lane`."""
    body = _fn()
    assert "FROM mi_audit_log WHERE event_type = 'dead_column_detected'" in body


def test_a_young_table_is_not_judged():
    """A table with a handful of rows has not had a chance to populate anything yet — flagging
    it would be a false positive on day one of any new feature."""
    assert "_DEAD_COL_MIN_ROWS" in SRC
    body = _fn()
    assert "< _DEAD_COL_MIN_ROWS" in body


def test_one_bad_table_cannot_kill_the_sweep():
    """A health guard that dies on the first permission error is a health guard that is off."""
    body = _fn()
    assert "except Exception" in body and 'out["errors"].append' in body


def test_it_actually_runs_nightly():
    """An inert detector is worse than none — this repo has shipped one before."""
    assert "run_dead_column_sweep" in SCHED, "the sweep is not wired into any job"
    seg = SCHED.split("run_dead_column_sweep")[-1][:500]
    assert "except Exception" in seg, (
        "the sweep is not isolated — a failure in it would take down the audit chain it shares "
        "a job with")


def test_the_alert_tells_you_what_to_DO():
    """'Dead column' with no instruction is a puzzle, not an alert."""
    body = _fn()
    assert "wire the writer or drop the column" in body


def test_it_does_not_duplicate_the_null_RATE_sweep():
    """The two answer different questions and both must survive: this one finds NEVER-written,
    the other finds WAS-written-and-broke. Collapsing either into the other reopens a hole."""
    assert "def _evaluate_column" in SRC, "the null-rate evaluator was removed"
    assert "always-null" in SRC, (
        "the null-rate sweep no longer documents that it skips always-null columns — that "
        "comment is the reason this second sweep exists")
