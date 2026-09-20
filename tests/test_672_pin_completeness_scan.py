"""#672 — no daily intelligence job may derive its DATA date from the wall clock; the pin must reach it.

The recovery sweep re-runs a missed job with `et_today()` pinned to the day it was due. A job that
computes `datetime.now(_ET).date()` itself is NOT reached — re-run on Saturday for Friday it records
Saturday (or, for a weekend guard, no-ops and records a success that did nothing). The 09-19 probe
hand-checked 14 jobs for this; the sweep's population is derived and 60+, so the check is derived too:
`scripts/check_job_date_sources.py` walks each eligible job's transitive call graph by AST.

First run over the real tree flagged EIGHT real sites (theme_synthesis, intraday_signals_eod_digest,
position_mgmt_judge, delayed_residual, crypto ingest ×2 + data_router, minute_volume, close_digest),
all routed through `et_today()` in the same commit — same live behaviour, now pinnable. Two remaining
wall-clock reads are about NOW (an alert dedup key, alert wording) and carry `# recovery-clock-ok:`.

The detector is proven on SYNTHETIC source first (so the real tree being clean is not the only
evidence it works), then gated on the real tree.
"""
from __future__ import annotations

import ast
import textwrap
from pathlib import Path

from scripts import check_job_date_sources as scan


def _mod(body: str, name: str = "agents.market_intelligence.synthetic") -> scan.Module:
    m = scan.Module.__new__(scan.Module)
    m.path = Path("/synthetic.py")
    m.name = name
    m.src = textwrap.dedent(body).lstrip("\n")
    m.tree = ast.parse(m.src)
    m.lines = m.src.splitlines()
    m.funcs = {n.name: n for n in m.tree.body if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))}
    m.imports = {}
    scan.Module._collect_imports(m.tree, m.imports)
    m.sends_directly = scan.TELEGRAM_HOST in m.src
    return m


def test_detector_flags_the_three_shapes_that_mislabel_a_rerun():
    """The exact shapes found on the real tree on 2026-09-20.
    MUTATION: emptying `DATE_DERIVATIONS` reddens this (zero hits). Verified RED."""
    m = _mod('''
        from datetime import datetime
        async def job_a():
            now_et = datetime.now(_ET)
            if not get_market_status(now_et.date()).is_trading_day:   # theme_synthesis shape
                return 0
        async def job_b():
            run_date = datetime.now(_ET).strftime("%Y-%m-%d")          # delayed_residual shape
        async def job_c():
            today = datetime.now(_ET).date().isoformat()                # close_digest shape
        async def clean():
            stamp = datetime.now(_ET)                                    # a timestamp — NOT a date
            d = et_today()
    ''')
    hits = {f: scan.date_from_clock(m, f) for f in ("job_a", "job_b", "job_c", "clean")}
    assert hits["job_a"] and hits["job_b"] and hits["job_c"], hits
    assert hits["clean"] == [], f"a bare timestamp was flagged: {hits['clean']}"
    assert all(not h["escaped"] for f in ("job_a", "job_b", "job_c") for h in hits[f])


def test_detector_honours_the_reviewed_escape_and_follows_calls_transitively():
    """MUTATION: dropping the `closure` walk (returning only the start function) loses the hit in
    `helper`, reddening the second assert. Verified RED."""
    m = _mod('''
        from datetime import datetime
        def helper():
            key = datetime.now(_ET).date().isoformat()  # recovery-clock-ok: a once-per-day dedup key about now
            other = datetime.now(_ET).date()
        async def job():
            helper()
    ''')
    chain = scan.closure({m.name: m}, (m, "job"))
    assert [f for _, f in chain] == ["job", "helper"]
    hits = [h for _, f in chain for h in scan.date_from_clock(m, f)]
    assert len(hits) == 2 and sum(h["escaped"] for h in hits) == 1
    assert next(h for h in hits if h["escaped"])["reason"].startswith("a once-per-day")


def test_sender_detection_sees_a_direct_bot_api_poster_and_the_shared_wrappers():
    m = _mod('''
        import httpx
        async def _send_with_keyboard(t):
            async with httpx.AsyncClient() as c:
                await c.post("https://api.telegram.org/botX/sendMessage", json={"text": t})
        async def job():
            await _send_with_keyboard("hi")
        async def silent():
            return 1
    ''')
    chain = scan.closure({m.name: m}, (m, "job"))
    assert any(scan.sends(m, f) or (m.sends_directly and f in scan.SENDER_NAMES) for _, f in chain)
    assert not scan.sends(m, "silent")


def test_the_real_tree_has_no_unescaped_wall_clock_date_in_any_recoverable_job():
    """THE GATE. Every daily, non-execution, non-paused, non-in-session job in scheduler.py, with its
    whole call graph, derives its data date only through `et_today()` / `last_trading_day()`.

    # source-pin-ok: the property is a relation across the CALL GRAPH of 46 registered jobs
    # (which job reaches which wall-clock date derivation), not the behaviour of one function —
    # exercising it would mean running 46 production jobs under a pin against a database.
    # Same class as tests/test_no_nested_pool_acquire.py.

    MUTATION: reverting `_theme_synthesis_job` to `now_et.date()` reddens this — verified RED
    before the fix landed (that was the scan's first real-tree run)."""
    rep = scan.analyse()
    assert len(rep["jobs"]) >= 40, f"only {len(rep['jobs'])} jobs examined — the registration parser lost the population"
    flagged = [(j["job_id"], h["module"], h["line"], h["text"]) for j in rep["jobs"]
               for h in j.get("date_from_clock", []) if not h["escaped"]]
    assert not flagged, (
        "a recoverable job derives a calendar date from the wall clock — re-run on Saturday for Friday "
        "it records Saturday. Route it through et_today(), or mark it `# recovery-clock-ok: <why it is "
        f"about NOW>`:\n  " + "\n  ".join(f"{j}: {m}:{l}  {t}" for j, m, l, t in flagged))
    assert any(j["job_id"] == "theme_synthesis" for j in rep["jobs"]), "theme_synthesis dropped out of the population"
