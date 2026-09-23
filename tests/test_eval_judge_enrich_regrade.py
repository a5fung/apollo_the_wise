"""Regression pin for the M1-b --regrade cohort query (scripts/eval_judge_enrich.py).

The 2026-07-13 M1-b run crashed `KeyError: 'catalyst'` because `run_regrade` reused
`_SIZE_SQL`, whose projection omits the columns `build_judge_payload()` subscripts — the
--regrade path had always been deferred/batched, so the gap never surfaced until the run.

These pins are pure STATIC checks (read source text; no DB, no module import, no Opus spend):
  1. `_REGRADE_SQL`'s SELECT ⊇ every `row["…"]` column `build_judge_payload` reads, so the
     projection can never silently drift below its consumer again.
  2. `run_regrade` fetches `_REGRADE_SQL` (not `_SIZE_SQL`) — the exact caller bug.
"""
import re
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
ENRICH = (REPO / "scripts" / "eval_judge_enrich.py").read_text()
COMMON = (REPO / "agents" / "market_intelligence" / "judge_replay_common.py").read_text()


def _regrade_select() -> str:
    m = re.search(r'_REGRADE_SQL = """(.*?)"""', ENRICH, re.S)
    assert m, "_REGRADE_SQL constant not found in eval_judge_enrich.py"
    return m.group(1)


def _build_payload_row_reads() -> set[str]:
    """Every column build_judge_payload() subscripts off its `row` argument."""
    body = re.search(
        r'def build_judge_payload\(.*?(?=\nasync def |\ndef )', COMMON, re.S)
    assert body, "build_judge_payload not found in judge_replay_common.py"
    return set(re.findall(r'row\[["\'](\w+)["\']\]', body.group(0)))


def test_regrade_projection_covers_build_payload_reads():
    """The exact 2026-07-13 bug: a column build_judge_payload reads but the query omits."""
    select = _regrade_select()
    reads = _build_payload_row_reads()
    assert reads, "expected build_judge_payload to read >=1 row column"
    missing = [c for c in sorted(reads) if not re.search(rf'\b{c}\b', select)]
    assert not missing, (
        f"_REGRADE_SQL is missing columns build_judge_payload reads: {missing}. "
        f"Add them to the SELECT or the --regrade run will KeyError on the first row."
    )


def test_run_regrade_uses_regrade_sql_not_size_sql():
    """run_regrade must fetch the payload-complete projection, not the sizing one."""
    m = re.search(r'async def run_regrade\(.*?(?=\nasync def |\ndef )', ENRICH, re.S)
    assert m, "run_regrade not found"
    body = m.group(0)
    assert "conn.fetch(_REGRADE_SQL" in body, "run_regrade should fetch _REGRADE_SQL"
    assert "conn.fetch(_SIZE_SQL" not in body, (
        "run_regrade must NOT fetch _SIZE_SQL (the 2026-07-13 KeyError:'catalyst' crash)")
