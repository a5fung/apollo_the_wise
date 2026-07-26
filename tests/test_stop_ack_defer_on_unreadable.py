"""#456 — the stop-ack watchdog must DEFER on an unreadable broker, not act blind.

Operator ruling 2026-07-26. Before this, a failed `get_open_orders` fell through
with `existing = []` and the watchdog placed a fallback stop BLIND — which defeats
the check it sits inside. That broker query exists precisely because a REDUNDANT
stop is rejected by Alpaca with "insufficient qty available", i.e. the BW #119
false CRITICAL of 2026-05-27 (#128). Acting on an unreadable broker re-creates
that bug; deferring costs at most one 30s cycle.

WHAT THESE TESTS CHECK, HONESTLY: this is a control-flow policy inside a long
DB-driven loop, and the sibling test file (test_stop_ack_broker_covered.py)
deliberately excerpts the classifier rather than importing the scheduler. Rather
than fake-exercise a copy of the branch — which would pass no matter what the
real code does — these assert against the SOURCE of the real function. That is
narrow but it is not vacuous: each assertion pins a specific way the ruling has
been silently reverted before, and they fail loudly if someone rewrites the
branch to act instead of defer.
"""
import re
from pathlib import Path

_SRC = (Path(__file__).resolve().parents[1]
        / "agents" / "market_intelligence" / "scheduler.py").read_text()


def _watchdog_source() -> str:
    """The body of _stop_ack_timeout_watchdog_job, up to the next top-level def."""
    start = _SRC.index("async def _stop_ack_timeout_watchdog_job")
    nxt = re.search(r"\n(?:async def |def )", _SRC[start + 10:])
    return _SRC[start: start + 10 + nxt.start()] if nxt else _SRC[start:]


def _unreadable_branch() -> str:
    """The `except` block guarding the broker read."""
    body = _watchdog_source()
    start = body.index("except Exception as get_err:")
    # Ends at the next line indented at the same depth as `sell_orders = [`.
    end = body.index("sell_orders = [", start)
    return body[start:end]


def test_defers_instead_of_acting_blind():
    """The branch must `continue`, not fall through to remediation."""
    branch = _unreadable_branch()
    assert "continue" in branch, (
        "the unreadable-broker branch no longer defers — it falls through to "
        "remediation, which places a stop blind and re-creates the BW #119 "
        "false CRITICAL (#128). Operator ruled DEFER on 2026-07-26."
    )


def test_does_not_resurrect_the_empty_list_fallthrough():
    """`existing = []` here is the exact pre-ruling fail-open."""
    branch = _unreadable_branch()
    assert not re.search(r"^\s*existing\s*=\s*\[\]", branch, re.M), (
        "`existing = []` is back in the unreadable-broker branch — that is the "
        "fail-open the 2026-07-26 ruling removed: it makes an unreadable broker "
        "indistinguishable from a genuinely uncovered position."
    )


def test_deferral_does_not_burn_the_daily_remediation_attempt():
    """The subtle one.

    The watchdog dedups one remediation attempt per (trade_id, day) by matching
    three event types. If the deferral's own audit event were ever added to that
    set, a single transient broker blip would suppress the retry for a full day —
    turning a 30-second deferral into a 24-hour blind spot. That would be a silent
    regression, so pin it.
    """
    body = _watchdog_source()
    dedup_sql = body[body.index("SELECT 1 FROM mi_audit_log"):]
    dedup_sql = dedup_sql[:dedup_sql.index("INTERVAL '1 day'")]
    assert "stop_ack_broker_unreadable" not in dedup_sql, (
        "the deferral's audit event is now matched by the once-per-day dedup — a "
        "transient broker read failure would suppress the retry for 24h instead "
        "of 30s."
    )
    # And the three real remediation events must still be the dedup's basis.
    for ev in ("stop_ack_timeout_remediated",
               "stop_ack_remediation_failed",
               "stop_ack_broker_covered"):
        assert ev in dedup_sql, f"dedup no longer covers {ev}"


def test_sustained_outage_does_not_flood_the_audit_log():
    """The job runs every 30s in market hours; an unguarded audit write would be
    2 rows/minute/trade for the length of an outage."""
    branch = _unreadable_branch()
    assert "INTERVAL '1 hour'" in branch, (
        "the deferral's audit write lost its own dedup window — a sustained "
        "broker outage will flood mi_audit_log at 2 rows/minute per trade."
    )
