"""F22 (7/2 review — #361 regression): the 4:45 EOD job's breakeven_active write
must be MONOTONIC (`breakeven_active OR $3`), never a plain `= $3` passthrough.

Why a source pin: the hazard is a refactor quietly reverting the SQL form — the
lost-update itself needs a mid-job finalize_partial_exit interleave that unit
mocks can't honestly reproduce (it's a cross-process race). The OR form makes
the race harmless BY CONSTRUCTION (Postgres evaluates old-value OR param), so
pinning the form IS pinning the fix. Natural exercise: every 4:45 run on any
open (incl. paper) position executes this UPDATE.
"""
import inspect

from agents.market_intelligence.broker import live_tracker


def test_eod_breakeven_write_is_monotonic_or():
    src = inspect.getsource(live_tracker.update_open_positions_live)
    assert "breakeven_active = (breakeven_active OR $3)" in src, (
        "F22 regression: the EOD UPDATE must OR the old flag — a plain "
        "`breakeven_active = $3` re-opens the finalize_partial_exit lost-update "
        "(TRUE clobbered to FALSE, no self-heal, stop floors below entry)."
    )


def test_partial_job_persists_nothing():
    # The 3:45 partial job must stay write-free (finalize_partial_exit owns the
    # partial fields on the WS fill; the 4:45 job owns the rest) — F22's sibling
    # invariant: no UPDATE statement in run_partial_exits at all.
    src = inspect.getsource(live_tracker.run_partial_exits)
    assert "UPDATE mi_live_trades" not in src, (
        "run_partial_exits must persist NOTHING (BW 5/14 optimistic-write protocol)"
    )
