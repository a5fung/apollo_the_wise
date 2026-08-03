"""The chart-vision shadow drip is PAUSED; the capability is KEPT (operator 2026-08-02).

*"i want chart reading to play a role but maybe not just the current way where it's not bringing
value; however, i still want to leverage all the data/trades we're collecting to eval and test chart
reading separately, once we can refine it properly to be valuable, we can introduce back into
trading process."*

Measured before pausing: 56 rows over 24 days (~2.3/day against a cap of 8), 336 judge calls,
roughly $11/month — about 85% of ALL ep_grade_judge spend — producing 5 verdict changes, 1 clean
delta, and zero influence on any trade. #343 was signed "hold, no promotion" on 8/01, so it was
collecting for a decision already made and nagging weekly to label it.

**Nothing is lost by stopping**: charts render point-in-time from stored daily OHLCV, so any
historical alert can be re-graded on demand, and the offline corpus is already 4x larger.

⚠ **These assert the PARK, parsed — not a comment that says "paused".** An earlier draft matched
`next_run_time=None` as a substring near the job id, which would pass on a commented-out line or on
a neighbouring job's kwarg. Twice in two days this codebase shipped something whose source read
correct and whose live surface did not behave (`/audit`, `/crypto` both answered "Unknown command"
with working handlers), so the parse is on the real `add_job` keyword, and the second invocation
path is frozen too — parking a cron changes nothing if something else calls the job body.
"""
import ast
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
_SCHED_PATH = _ROOT / "agents/market_intelligence/scheduler.py"
_SCHED = _SCHED_PATH.read_text()
_TREE = ast.parse(_SCHED)

_JOB_IDS = ("chart_axis_shadow", "chart_axis_shadow_weekly_digest")


def _add_job_call(job_id: str) -> ast.Call:
    """The real `add_job(...)` node registering `job_id` — AST, not text proximity."""
    for node in ast.walk(_TREE):
        if not (isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)):
            continue
        if node.func.attr != "add_job":
            continue
        for kw in node.keywords:
            if kw.arg == "id" and isinstance(kw.value, ast.Constant) and kw.value.value == job_id:
                return node
    raise AssertionError(f"no add_job registration found for id={job_id!r}")


def _kwarg(call: ast.Call, name: str):
    for kw in call.keywords:
        if kw.arg == name:
            return kw.value
    return None


# ── the park itself ──────────────────────────────────────────────────────────────────────────

def test_the_daily_drip_does_not_auto_fire():
    val = _kwarg(_add_job_call("chart_axis_shadow"), "next_run_time")
    assert isinstance(val, ast.Constant) and val.value is None, \
        "the 17:50 ET daily drip must be registered with next_run_time=None"


def test_the_weekly_labeling_nag_does_not_auto_fire():
    """It asked the operator to label deltas for a decision signed 8/01 — and said so itself:
    'decision by 2026-07-31 (-2d)'."""
    val = _kwarg(_add_job_call("chart_axis_shadow_weekly_digest"), "next_run_time")
    assert isinstance(val, ast.Constant) and val.value is None


def test_the_park_survives_a_restart():
    """`next_run_time=None` re-applies at every boot only because the scheduler keeps its jobs in
    memory. A PERSISTENT jobstore would restore the stored trigger and quietly un-pause both jobs on
    the next restart — the pause would then hold until the first redeploy and no test would notice.
    If a jobstore is ever added, this fails and the pause needs a different mechanism."""
    ctor = next(
        (n for n in ast.walk(_TREE)
         if isinstance(n, ast.Call) and isinstance(n.func, ast.Name)
         and n.func.id == "AsyncIOScheduler"),
        None,
    )
    assert ctor is not None, "scheduler construction not found"
    assert _kwarg(ctor, "jobstores") is None, \
        "a persistent jobstore would override next_run_time=None on restart"


def test_no_OTHER_code_path_runs_the_shadow():
    """Parking the cron is only a pause if the cron is the ONLY caller. A job body invoked inline
    from another job, a digest, or a review would keep spending regardless of its trigger."""
    targets = {"_run_chart_axis_shadow", "_chart_axis_shadow_job",
               "_chart_axis_shadow_weekly_digest_job"}
    # AST, not grep: `chart_axis.py`'s module docstring NAMES `scheduler._chart_axis_shadow_job` to
    # say where the constants are imported from. A prose mention is not a call, and a text search
    # cannot tell the difference — which is the same class of false signal this file exists to avoid.
    # The definitions + their registration live in scheduler.py; the operator-driven one-shot is a
    # manual tool, not an automatic path. Both are named here rather than silently skipped.
    allowed = {"agents/market_intelligence/scheduler.py", "scripts/_verify_chart_axis_shadow.py"}
    callers: set[str] = set()
    for d in ("agents", "core", "channels", "shared", "scripts"):
        for path in (_ROOT / d).rglob("*.py"):
            rel = path.relative_to(_ROOT).as_posix()
            if rel in allowed:
                continue
            try:
                tree = ast.parse(path.read_text())
            except SyntaxError:
                continue
            for node in ast.walk(tree):
                name = (node.id if isinstance(node, ast.Name)
                        else node.attr if isinstance(node, ast.Attribute) else None)
                if name in targets:
                    callers.add(rel)
    assert not callers, f"unexpected caller(s) of the paused shadow: {sorted(callers)}"


# ── the capability is kept ───────────────────────────────────────────────────────────────────

def test_both_jobs_are_STILL_REGISTERED():
    """Unregistering would trip the scheduler's role-partition completeness guard at boot, and
    would also discard the ability to resume. Paused is not deleted."""
    for jid in _JOB_IDS:
        _add_job_call(jid)          # raises if the registration is gone
        assert jid in _SCHED


def test_the_CAPABILITY_is_kept_not_deleted():
    """The whole point of the middle ground: keep chart reading testable offline."""
    assert (_ROOT / "agents/market_intelligence/chart_axis.py").exists()
    assert (_ROOT / "scripts/eval_chart_judge.py").exists()


def test_charts_are_re_renderable_so_pausing_loses_no_data():
    """render_prior_day_chart builds from stored daily OHLCV — historical alerts stay gradeable."""
    src = (_ROOT / "agents/market_intelligence/chart_axis.py").read_text()
    assert "async def render_prior_day_chart" in src
    assert "get_prior_daily_ohlcv" in src


def test_the_pause_rationale_names_the_deliberate_tool():
    """A future reader must find the replacement, not just the removal."""
    i = _SCHED.index('id="chart_axis_shadow"')
    assert "eval_chart_judge.py" in _SCHED[max(0, i - 2000):i]
