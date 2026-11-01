"""OLD-vs-NEW proof harness for the #482 recorder (follow-up 1, the trail-arming era switch).

Runs, on whatever tree it is pointed at (REPO env var):
  (a) the five `_lfc_equality_scenarios` recorder runs (every INSERT the recorder makes);
  (b) `walk_arm` over the unit fixtures of tests/test_live_fill_counterfactuals.py, every harvest x
      every stop arm, plus the price-armed breakeven variant;
  (c) the same walks SHIFTED to 2017 session dates (the frozen #705 v2 read walks 2016-2022).
Prints one JSON document. Run once on the base tree and once on the changed tree; diff.
"""
from __future__ import annotations

import asyncio
import json
import os
import sys
from datetime import date, timedelta

REPO = os.environ["REPO"]
sys.path.insert(0, REPO)
os.chdir(REPO)

from tests import test_live_fill_counterfactuals as base  # noqa: E402
from tests._lfc_equality_scenarios import run_old_recorder, scenarios, to_jsonable  # noqa: E402
from agents.market_intelligence import live_fill_counterfactuals as lfc  # noqa: E402


def _shift_sessions(sessions, first: date):
    out, d = [], first
    for _, bar in sessions:
        while d.weekday() >= 5:
            d += timedelta(days=1)
        out.append((d, bar))
        d += timedelta(days=1)
    return out


def _walks(day0, fill_day, sessions, tag):
    res = {}
    stops = {"live": base.LIVE_STOP, "orb_low": base.ORB_LOW, "adr_050": 9.8, "adr_075": 9.7, "orb_3r": 8.5}
    for harvest in lfc.HARVEST_RULES:
        for sname, stop in stops.items():
            r = lfc.walk_arm(entry=base.ENTRY, stop=stop, target=base.TARGET, day0_bars=day0,
                             fill_idx=base.FILL_IDX_A, sessions=sessions, prior_closes=base.PRIOR_CLOSES,
                             harvest=harvest, fill_day=fill_day, breakeven_at_r=None)   # the pre-#545 global stack, stated
            res[f"{tag}:{harvest}:{sname}"] = to_jsonable(r)
    r = lfc.walk_arm(entry=base.ENTRY, stop=base.LIVE_STOP, target=base.TARGET_8R, day0_bars=day0,
                     fill_idx=base.FILL_IDX_A, sessions=sessions, prior_closes=base.PRIOR_CLOSES,
                     harvest="live_ladder", fill_day=fill_day, breakeven_at_r=3.0, r_frame_ps=base.R_PS)
    res[f"{tag}:live_ladder:8r_3r"] = to_jsonable(r)
    # a trade bought BELOW its line (the CLS shape): prior closes far above the entry
    r = lfc.walk_arm(entry=base.ENTRY, stop=base.LIVE_STOP, target=None, day0_bars=day0,
                     fill_idx=base.FILL_IDX_A, sessions=sessions, prior_closes=[30.0] * 20,
                     harvest="live_ladder", fill_day=fill_day, breakeven_at_r=None)
    res[f"{tag}:live_ladder:below_line"] = to_jsonable(r)
    return res


async def main():
    out = {"recorder": {}, "walks": {}}
    for name, sc in scenarios().items():
        r = await run_old_recorder(name, sc)
        out["recorder"][name] = {"out": r["out"], "rows": to_jsonable(r["rows"])}
    out["walks"].update(_walks(base.DAY0_A, base.FILL_DAY, base.SESS_A, "2026"))
    d2017 = date(2017, 3, 2)
    day0_2017 = [dict(b, m=b["m"].replace(year=2017, month=3, day=2)) for b in base.DAY0_A]
    out["walks"].update(_walks(day0_2017, d2017, _shift_sessions(base.SESS_A, date(2017, 3, 3)), "2017"))
    print(json.dumps(out, indent=1, sort_keys=True, default=str))


asyncio.run(main())
