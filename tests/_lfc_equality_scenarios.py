"""Shared fixture scenarios for the #482 book-arms OLD-vs-NEW equality proof (2026-10-26).

The golden file `tests/fixtures/lfc_pre_book_arms_golden.json` was produced by running
`live_fill_counterfactuals.run_live_fill_counterfactuals` over THESE scenarios on the code as it
stood BEFORE the book-geometry arms were added (git HEAD 9a61d43d with agents/ unmodified). The equality test re-runs
the same scenarios on the changed tree and asserts every pre-existing column of every pre-existing
arm row is byte-equal and every new column is NULL on those rows. Imports nothing from the new
module, so the generator could run on the old tree.

Regenerate ONLY by checking out the pre-change tree: `python tests/_lfc_equality_scenarios.py > golden`
on any other tree defeats the proof."""
from __future__ import annotations

import json
import sys
from datetime import date, datetime, timedelta
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from tests import test_live_fill_counterfactuals as base  # noqa: E402

_ET = base._ET
NOW = base._NOW
TODAY = base._TODAY


def _shift_day0(day0, d):
    return [dict(b, m=b["m"].replace(year=d.year, month=d.month, day=d.day)) for b in day0]


def _pre_for(d, n_days=40):
    pre = [{"trade_date": x, "open_price": 9.0, "high_price": 9.18, "low_price": 8.82, "close": 9.0}
           for x in [d - timedelta(days=k) for k in range(1, n_days)] if x.weekday() < 5]
    return sorted(pre, key=lambda r: r["trade_date"])


def scenarios() -> dict[str, dict]:
    """name -> kwargs for base._wire plus the trade row; each is one recorder run."""
    out: dict[str, dict] = {}
    out["default"] = {"trade": base._trade_row()}
    out["override_8r_3r"] = {
        "trade": base._trade_row(
            entry_shares=30.0, total_pnl=40.0,
            exits=[{"reason": "partial_profit", "price": 14.0, "shares": 10, "pnl": 40.0},
                   {"reason": "stop_hit", "price": 10.0, "shares": 20, "pnl": 0.0}],
            closed_at=datetime(2026, 8, 25, 16, 0, tzinfo=_ET)),
        "minutes": [base.DAY0_A[0], base.DAY0_A[1], base._m(9, 32, 10.02, 11.6, 10.1, 11.5), base.DAY0_A[4]],
        "sessions": [(base.SESSIONS[0], base._bar(12.0, 14.5, 12.0, 14.2)),
                     (base.SESSIONS[1], base._bar(10.0, 10.1, 9.8, 9.85))],
        "overrides": [{"signal_type": "magna53", "profit_trigger_r": 8.0, "breakeven_arm_r": 3.0}],
    }
    d = date(2026, 10, 14)       # a depth-stamped fill (era E): the row's exit_rule decides the era
    out["depth_row"] = {
        "trade": base._trade_row(
            id=77, alert_date=d, exit_rule="depth",
            filled_at=datetime(2026, 10, 14, 9, 31, 7, tzinfo=_ET),
            closed_at=datetime(2026, 10, 16, 10, 0, tzinfo=_ET)),
        "minutes": _shift_day0(base.DAY0_A, d),
        "sessions": [(date(2026, 10, 15), base._bar(10.6, 10.8, 9.9, 10.4)),
                     (date(2026, 10, 16), base._bar(10.5, 11.5, 10.3, 11.4)),
                     (date(2026, 10, 19), base._bar(11.5, 12.2, 11.2, 12.0)),
                     (date(2026, 10, 20), base._bar(8.5, 8.7, 8.4, 8.6)),
                     (date(2026, 10, 21), base._bar(8.6, 8.8, 8.5, 8.7)),
                     (date(2026, 10, 22), base._bar(8.6, 8.8, 8.5, 8.7))],
        "now": datetime(2026, 10, 22, 18, 4, tzinfo=_ET),
        "pre": _pre_for(d),
        "overrides": [{"signal_type": "magna53", "profit_trigger_r": 8.0, "breakeven_arm_r": 3.0}],
    }
    out["missing_orb_low"] = {"trade": base._trade_row(id=43, orb_low=None)}
    out["open_trade"] = {"trade": base._trade_row(id=44, status="open", total_pnl=None, closed_at=None,
                                                  exits=[], partial_taken=False)}
    return out


def build_wire_kwargs(sc: dict) -> dict:
    """The kwargs for base._wire from one scenario (daily rows assembled the way the tests do)."""
    trade = sc["trade"]
    sessions = sc.get("sessions", base.SESS_A)
    pre = sc.get("pre", base._pre_rows())
    daily = pre + [{"trade_date": s, "open_price": b["o"], "high_price": b["h"], "low_price": b["l"],
                    "close": b["c"]} for s, b in sessions]
    kw = {"trade": trade, "daily": daily, "minutes": sc.get("minutes", base.DAY0_A)}
    if "overrides" in sc:
        kw["overrides"] = sc["overrides"]
    return kw


async def run_old_recorder(name: str, sc: dict) -> dict:
    """Run the EXISTING recorder over one scenario and return {out, rows} (rows = every INSERT)."""
    from agents.market_intelligence import live_fill_counterfactuals as lfc
    mp = pytest.MonkeyPatch()
    try:
        _, inserts, _, _ = base._wire(mp, **build_wire_kwargs(sc))
        now = sc.get("now", NOW)
        out = await lfc.run_live_fill_counterfactuals(now.date(), now_et=now)
    finally:
        mp.undo()
    return {"out": out, "rows": [dict(r) for r in inserts]}


def to_jsonable(v):
    if isinstance(v, (datetime, date)):
        return v.isoformat()
    if isinstance(v, dict):
        return {k: to_jsonable(x) for k, x in v.items()}
    if isinstance(v, (list, tuple)):
        return [to_jsonable(x) for x in v]
    return v


async def _main() -> None:
    result = {}
    for name, sc in scenarios().items():
        r = await run_old_recorder(name, sc)
        result[name] = {"out": r["out"], "rows": to_jsonable(r["rows"])}
    print(json.dumps(result, indent=1, sort_keys=True))


if __name__ == "__main__":
    import asyncio
    asyncio.run(_main())
