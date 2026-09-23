"""A position must have a resting stop during EVERY minute of market hours (2026-08-04).

⚖ Operator, 2026-08-04, after being handed too many options and not enough answers:
*"do we have a stop always during market hours, do we sell partial at 2R, if not, then
it's all garbage."* This file pins the first half.

THE HOLE. An entry bracket is submitted `TimeInForce.DAY`, so its stop LEG expires at the
16:00 close. `morning_stop_refresh` re-placed it as a standalone GTC — but at 09:35, five
minutes AFTER the open. Measured both ways in prod:
  * PLTR 307, 2026-08-04 — leg expired 16:00; the live account then reported zero open
    orders with all 6 shares free.
  * QBTS,     2026-07-28 — refreshed 09:35, stopped out 09:36:24.
So every Day-2+ position traded the first five minutes of its session naked — the most
volatile five minutes there are, and the ones an overnight gap resolves into.

THE FIX. `post_close_stop_refresh` at 16:20 ET places the next session's GTC stop the
evening before. `morning_stop_refresh` stays as the backstop.

⚠ WHY 16:20 AND NOT 09:35-SAME-DAY. ADR 0029 D1 removed same-day fills from the morning
pass because their OTO child is LIVE at 09:35 and re-placing raced it (the WULF
`insufficient qty available` self-conflict). After the close that child has already
expired — nothing to race. That asymmetry IS the design, so it is pinned here: if someone
later "unifies" the two passes, this file fails.
"""
import ast
import inspect
import pathlib

SRC = pathlib.Path("agents/market_intelligence/broker/live_tracker.py").read_text()
SCHED = pathlib.Path("agents/market_intelligence/scheduler.py").read_text()
TREE = ast.parse(SRC)


def _fn(name):
    return next(n for n in ast.walk(TREE)
                if isinstance(n, (ast.AsyncFunctionDef, ast.FunctionDef)) and n.name == name)


def test_a_post_close_pass_exists_at_all():
    assert _fn("post_close_stop_refresh")


def test_the_post_close_pass_covers_SAME_DAY_fills():
    """The whole point. A trade that filled today is exactly the one whose bracket leg
    just died at the close; excluding it would leave the hole open."""
    src = ast.get_source_segment(SRC, _fn("post_close_stop_refresh"))
    assert "include_same_day=True" in src


def test_the_MORNING_pass_still_excludes_same_day_fills():
    """ADR 0029 D1 — un-excluding it here would reintroduce the WULF collision."""
    src = ast.get_source_segment(SRC, _fn("morning_stop_refresh"))
    assert "include_same_day=False" in src


def test_the_two_passes_share_one_body():
    """Two hand-maintained copies of a stop-placement loop is how they drift. The ONLY
    difference between the passes must be the same-day scope."""
    shared = _fn("_stop_refresh")
    src = ast.get_source_segment(SRC, shared)
    assert "update_stop(" in src, "the shared body owns the actual placement"
    for caller in ("post_close_stop_refresh", "morning_stop_refresh"):
        body = ast.get_source_segment(SRC, _fn(caller))
        assert "_stop_refresh(" in body
        assert "update_stop(" not in body, f"{caller} must delegate, not re-implement"


def test_the_same_day_scope_actually_changes_the_QUERY():
    """A flag that does not reach the SQL is the 91-day inert-sweep defect (#521)."""
    src = ast.get_source_segment(SRC, _fn("_stop_refresh"))
    assert "if include_same_day:" in src
    branch = src[src.index("if include_same_day:"):]
    excl = branch.index("alert_date <> $1")
    assert "else:" in branch[:excl], "the same-day EXCLUSION must sit in the else branch"


def test_an_unplaceable_stop_REACHES_THE_OPERATOR():
    """A position we could not protect is the exact failure this job exists to prevent.
    A log line would make it invisible — the shape of every silent-failure bug this week."""
    src = ast.get_source_segment(SRC, _fn("_stop_refresh"))
    assert "unprotected" in src
    assert "send_telegram_message" in src, "must alert, not just log"
    assert "stop_refresh_failed" in src, "must leave a durable audit row"


def test_an_already_resting_stop_is_LEFT_ALONE():
    """Idempotence. Re-placing a live stop opens a window with no resting stop — the #444
    defect that cancelled and re-placed SMCI's stop at an identical price three mornings
    running."""
    src = ast.get_source_segment(SRC, _fn("_stop_refresh"))
    i = src.index('trade["stop_order_id"]')
    assert "continue" in src[i:i + 700]
    assert 'account_mode=trade["account_mode"]' in src, (
        "#444: the status read must use the trade's OWN mode or the skip branch is dead code")


def test_it_runs_AFTER_the_close_and_BEFORE_the_next_open():
    i = SCHED.index('id="post_close_stop_refresh"')
    block = SCHED[i - 700:i]
    assert "hour=16, minute=20" in block, "16:20 ET — after eod_cleanup 16:05 and reconcile 16:15"
    assert 'timezone="America/New_York"' in block, "never UTC cron for a market-clock job"
    assert 'day_of_week="mon-fri"' in block


def test_it_is_routed_to_the_EXECUTION_role():
    """broker/ work runs on apollo-execution. An unclassified job fails the split-role
    boot; one classified to intelligence would never place a stop at all."""
    from agents.market_intelligence import scheduler as s
    assert "post_close_stop_refresh" in s.EXECUTION_OWNED_JOB_IDS
    assert "post_close_stop_refresh" not in s.INTELLIGENCE_OWNED_JOB_IDS


def test_the_morning_backstop_was_NOT_removed():
    """Belt and braces. A stop killed overnight by the broker still needs catching before
    the day trades."""
    assert 'id="morning_stop_refresh"' in SCHED
    assert "hour=9, minute=35" in SCHED


def test_it_stands_down_when_trading_is_disabled():
    from agents.market_intelligence import scheduler as s
    src = inspect.getsource(s._post_close_stop_refresh_job)
    assert "LIVE_TRADING_ENABLED" in src and "return" in src
