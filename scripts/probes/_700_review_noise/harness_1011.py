"""#700 — render the stored 2026-10-11 review through the REAL `_assemble_report`, offline.

Shared by `tests/test_weekly_review_noise_700.py` (the length budget, the change-detection cases) and
`preview.py --fixture` (a laptop render of the 10-11 message under the current code). Everything the
sections read at render time is patched from `tests/fixtures/weekly_review_1011.json`'s
`render_inputs` (rebuilt from the one-time q3 capture by `build_fixture_1011.py`); nothing touches a
database, Telegram, or the clock. The stored 10-11 `summary` stands in for the LLM (it is not re-run).

    render_1011(prior=...)  ->  (head_md, fold_md, meta)
"""
from __future__ import annotations

import asyncio
import copy
import inspect
import json
from contextlib import ExitStack
from datetime import date, timedelta
from pathlib import Path
from unittest.mock import AsyncMock, patch

ROOT = Path(__file__).resolve().parents[3]
FIXTURE = ROOT / "tests" / "fixtures" / "weekly_review_1011.json"
TODAY = date(2026, 10, 11)
WINDOW_START = TODAY - timedelta(days=7)
NO_PRIOR = None
FIXTURE_PRIOR = "fixture"          # the 10-04 row as it stood on the 10-18 first run: raw metrics, no snapshot


def load_fixture() -> dict:
    return json.loads(FIXTURE.read_text(encoding="utf-8"))


def restore_dates(metrics: dict) -> dict:
    """The aggregators hand the renderers `date` objects; the stored JSON has ISO strings."""
    m = copy.deepcopy(metrics)
    mo = m.get("missed_opportunities") or {}
    for key in ("gaps", "top_winners"):
        for r in mo.get(key) or []:
            if isinstance(r.get("alert_date"), str):
                r["alert_date"] = date.fromisoformat(r["alert_date"])
    return m


def _theme_reads(ri: dict) -> tuple[list[dict], list[dict]]:
    th = ri["theme"]
    rows = [{**r, "alert_date": date.fromisoformat(r["alert_date"])} for r in th["clean"]]
    graded = [{"ticker": r["ticker"], "alert_date": r["alert_date"], "judge_theme": r["judge_theme"]}
              for r in rows]
    for i in range(th["left_out"]):          # judge-graded alerts the clean-read filter left out
        graded.append({"ticker": f"LO{i}", "alert_date": date(2026, 9, 20),
                       "judge_theme": i < th["left_out_judge_themed"]})
    return rows, graded


def _live_inputs(ri: dict, n_live: int | None):
    import agents.market_intelligence.kill_scale_bands as ksb
    closed = ri["live_closed"] if n_live is None else ri["live_closed"][:n_live]
    rs = [c["r"] for c in closed]
    meta = [{"alert_date": date.fromisoformat(c["alert_date"]), "signal_type": c["signal_type"]}
            for c in closed]
    inputs = {"realized_rs": rs, "realized_r_meta": meta, "drawdown_tier": "OK",
              "equity_above_start": False, "account_mode": "live", "open_positions": ri["open_live"]}
    verdict = ksb.evaluate_kill_scale_bands(rs, equity_above_start=False, drawdown_tier="OK")
    return inputs, verdict


def patch_render_inputs(stack: ExitStack, ri: dict, n_live: int | None = None) -> dict:
    """Install every render-time input the 10-11 run read live (bands, the early-window cohort, replay,
    the setup row, the theme reads, spend and P&L, the 2nd-opinion line) as patches on `stack`.
    Returns the mocks by short name (`audit` = the replay snapshot writer) so a test can assert on them."""
    import agents.market_intelligence.cost_board as cost_board
    import agents.market_intelligence.db as dbmod
    import agents.market_intelligence.kill_scale_bands as ksb
    import agents.market_intelligence.system_review as sr

    inputs, verdict = _live_inputs(ri, n_live)
    era_trades = [{"signal_type": c["signal_type"], "account_mode": "live",
                   "alert_date": date.fromisoformat(c["alert_date"]), "exit_reason": c["exit_reason"],
                   "peak_r": None, "realized_r": None, "stop_per_adr": None}
                  for c in ri["live_closed"] if date.fromisoformat(c["alert_date"]) >= TODAY - timedelta(days=90)]
    rows, graded = _theme_reads(ri)
    sp = ri["spend_envelope"]
    audit = AsyncMock(return_value=None)
    for target, name, new in (
        (ksb, "assess_bands", AsyncMock(return_value=(inputs, verdict, None))),
        (ksb, "assemble_band_inputs", AsyncMock(return_value=inputs)),
        (dbmod, "log_audit_event", audit),                              # the replay snapshot write
        (sr, "get_setup_performance_review", AsyncMock(return_value=[ri["setup_row"]])),
        (sr, "get_setup_era_trades", AsyncMock(return_value=era_trades)),
        (sr, "get_engine_vs_judge_theme_rows", AsyncMock(return_value=rows)),
        (sr, "get_judge_graded_alert_flags", AsyncMock(return_value=graded)),
        (sr, "get_closed_pnl_by_account_mode", AsyncMock(return_value=[ri["live_book"]])),
        (sr, "_spend_envelope", AsyncMock(return_value=(sp["text"], sp["cost"], sp["budget"], False))),
        (sr, "_judge_divergence_section", AsyncMock(return_value=ri["second_opinion"])),
        (cost_board, "compute_caller_spend_window", AsyncMock(return_value=ri["spend_callers"])),
    ):
        stack.enter_context(patch.object(target, name, new))
    stack.enter_context(patch("agents.market_intelligence.collector.et_today", lambda: TODAY))
    return {"audit": audit}


def render_1011(prior=FIXTURE_PRIOR, *, n_live: int | None = None, summary: str | None = None,
                metrics_update: dict | None = None, mocks: dict | None = None):
    """(head_md, fold_md, meta) for the 10-11 review. `prior`: FIXTURE_PRIOR (the 10-04 row), None (no
    earlier review), or a dict shaped like `get_latest_system_review`'s return. Under the pre-#700
    renderer (no `prior` parameter) the argument is ignored — that is how `before` was captured."""
    import agents.market_intelligence.system_review as sr
    fx = load_fixture()
    metrics = restore_dates(fx["review"]["metrics"])
    metrics.update(metrics_update or {})
    if prior == FIXTURE_PRIOR:
        prior = copy.deepcopy(fx["prior"])
    kwargs = {}
    if "prior" in inspect.signature(sr._assemble_report).parameters:
        kwargs["prior"] = prior
    with ExitStack() as stack:
        got = patch_render_inputs(stack, fx["render_inputs"], n_live)
        if mocks is not None:
            mocks.update(got)
        return asyncio.run(sr._assemble_report(
            metrics, summary if summary is not None else fx["review"]["summary"],
            WINDOW_START, TODAY, **kwargs))
