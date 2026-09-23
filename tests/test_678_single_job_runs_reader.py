"""One reader for `mi_job_runs` ledger rows, and the ordering it now imposes is load-bearing.

FOUND 2026-09-20 by the simplify pass, and it is the one finding TWO of the four reviewers raised
independently: `job_recovery.fetch_ledger` and `db.get_job_runs_for` were added the SAME DAY, ran
near-identical SQL against the same table (same WHERE shape; `duration_s` vs `finished_at`; days vs
hours), and neither knew about the other. A column added to `mi_job_runs` had to be found twice.

⚠ THE PART THAT WAS NOT OBVIOUS. Folding them meant `fetch_ledger` inherited `ORDER BY started_at
ASC`, and `classify_slot` **returns on the first matching row**, so its verdict depends on row
order — while its old input had NO `ORDER BY` at all. The pre-existing behaviour was therefore
whatever the query plan happened to emit. Verified on the real prod ledger before the change
landed: 90,342 rows, old and new queries return **identical row sets**, and over **17,130
permutation probes zero verdicts changed** — 3,148 differed only in the HH:MM inside a `done`
detail string, which nothing branches on. Chronological is deterministic AND the order that branch
actually means.
"""
from __future__ import annotations

import ast
import random
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

from agents.market_intelligence import db, job_recovery
from agents.market_intelligence.job_recovery import classify_slot

_ET = ZoneInfo("America/New_York")
REPO = Path(__file__).resolve().parents[1]


def _reader_sql() -> str:
    """Every string literal inside `get_job_runs_for` EXCEPT its docstring — i.e. the SQL.

    ⚠ TWO drafts of this were worthless and both read GREEN under mutation, which is the only
    reason they were caught. (1) Asserting over `inspect.getsource(...)` whole: the docstring
    explains why `duration_s` and the `ORDER BY` matter, so it CONTAINS both strings and the test
    passed with the SQL deleted. (2) Subtracting `__doc__` from the source text: `__doc__ in
    source` is False, so the subtraction silently no-opped and draft 1 came straight back.
    The docstring is the function's first statement — let the AST say so, and never pattern-match
    a docstring out of source text again."""
    tree = ast.parse((REPO / "agents" / "market_intelligence" / "db.py").read_text(encoding="utf-8"))
    fn = next(n for n in ast.walk(tree)
              if isinstance(n, (ast.AsyncFunctionDef, ast.FunctionDef)) and n.name == "get_job_runs_for")
    body = fn.body[1:] if ast.get_docstring(fn) is not None else fn.body
    return "\n".join(n.value for b in body for n in ast.walk(b)
                      if isinstance(n, ast.Constant) and isinstance(n.value, str))


def test_the_one_reader_still_selects_what_the_recovery_sweep_needs():
    """`fetch_ledger` delegates, so `bound_for` silently loses its p95 input if `duration_s` is
    dropped from the shared query — and nothing else would fail.

    # source-pin-ok: the property is "which columns and ORDER BY this ONE SQL statement carries".
    # There is no runtime seam that exposes it without a live Postgres — exercising it would mean
    # standing up the ledger table. The behavioural half (that fetch_ledger delegates here at all,
    # and converts its window correctly) IS exercised, below.
    """
    sql = _reader_sql()
    assert "mi_job_runs" in sql, "the reader no longer queries the ledger at all"
    for col in ("duration_s", "scheduled_for", "status", "started_at"):
        assert col in sql, (
            f"the shared ledger reader stopped selecting {col!r}. `fetch_ledger` delegates to it, "
            f"so the recovery sweep loses that column silently — `bound_for` would fall back to "
            f"its 30-minute default timeout for every job and nothing would fail."
        )
    assert "ORDER BY started_at ASC" in sql, (
        "the ORDER BY is load-bearing: classify_slot returns on the first matching row, so "
        "dropping it makes the recovery sweep's verdicts depend on the query plan again."
    )


def _rows(n_slot_rows: int) -> tuple[list[dict], datetime]:
    base = datetime(2026, 9, 14, 17, 0, tzinfo=_ET)
    rows = [
        {"job_id": "j", "started_at": base + timedelta(minutes=3), "status": "success",
         "scheduled_for": None, "duration_s": 12.0, "error_message": None},
        {"job_id": "j", "started_at": base + timedelta(minutes=9), "status": "interrupted",
         "scheduled_for": None, "duration_s": None, "error_message": "cancelled"},
        {"job_id": "j", "started_at": base - timedelta(days=1), "status": "success",
         "scheduled_for": None, "duration_s": 30.0, "error_message": None},
    ][:n_slot_rows]
    return rows, base


def test_a_verdict_does_not_depend_on_the_order_rows_arrive_in():
    """The property the fold relies on, exercised rather than asserted from the prod run: whatever
    order the ledger arrives in, the DISPOSITION KIND is the same. Only a `done` detail's displayed
    timestamp may differ, and nothing branches on that."""
    rng = random.Random(0)
    now = datetime(2026, 9, 20, 12, 0, tzinfo=_ET)
    for n in (2, 3):
        rows, base = _rows(n)
        expected = classify_slot("j", base, 3600, rows, now).kind
        for _ in range(50):
            shuffled = rows[:]
            rng.shuffle(shuffled)
            got = classify_slot("j", base, 3600, shuffled, now)
            assert got.kind == expected, (
                f"reordering {n} ledger rows changed the verdict {expected!r} -> {got.kind!r}. "
                f"classify_slot returns on the first match, so the shared query's ORDER BY is the "
                f"only thing making this deterministic."
            )


def test_fetch_ledger_converts_its_day_window_to_the_shared_readers_hours():
    """A units slip here silently shrinks `bound_for`'s history 24x and shortens every re-run
    timeout. Exercised through the real function with the DB call stubbed."""
    seen = {}

    async def _fake(job_ids, since_hours=240):
        seen["hours"] = since_hours
        return [{"job_id": "a", "started_at": None, "status": "success", "scheduled_for": None,
                 "duration_s": 1.0, "error_message": None}]

    import asyncio
    orig = db.get_job_runs_for
    db.get_job_runs_for = _fake
    try:
        out = asyncio.run(job_recovery.fetch_ledger(["a"], days=60))
    finally:
        db.get_job_runs_for = orig
    assert "hours" in seen, (
        "fetch_ledger never called db.get_job_runs_for — it has grown its own SELECT against "
        "mi_job_runs again, which is the #678 duplication returning."
    )
    assert seen["hours"] == 60 * 24, f"60 days reached the reader as {seen['hours']} hours"
    assert list(out) == ["a"] and len(out["a"]) == 1, "rows are no longer grouped by job_id"
