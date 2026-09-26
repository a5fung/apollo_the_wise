"""Block 5 / P5 — the one line item P3 left for the write-up: which way does the day-0 abstain
select?

P3 scores the incumbent-stop cells on ~1,320 of the 3,398 fires with >=10 sessions elapsed;
2,042 abstain because they are minute-grade fires whose day low reached the (tight) incumbent
stop and no $0 minute source exists to order day 0. Production DID settle those rows (it fetched
minutes live at settle time), so the recorded columns on trigger.csv are the ground truth the
grid could not reach. This reads them: for the incumbent stop with no target (the lane's own
M-none arm) and the incumbent trail arm (M-trail), compare the recorded outcome / realized_r /
tail on the ABSTAINED rows against the SCORED rows, per pattern.

Population = the grid's own: sessions elapsed >= 10 by 2026-09-25 via the real `_trading_days`
(never settlement status). SCORED = the ids P3 wrote to p3_events.csv for
(recorded, incumbent, none) with elapsed >= 10 (the event log carries only walked rows).
KILLED = stop at/above entry. ABSTAINED = population − scored − killed.

$0, read-only, local files only. Output: p5_summary.json (small, committed).
"""
import csv
import json
import sys
from collections import defaultdict
from datetime import date, timedelta
from pathlib import Path

HERE = Path(__file__).parent
REPO_ROOT = HERE.resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))
from agents.market_intelligence.delayed_entry_shadow import _trading_days  # real code

LAST_SESSION = date(2026, 9, 25)
WINDOW, PRIMARY_K = 20, 10


def _f(s):
    try:
        return float(s) if s not in (None, "") else None
    except ValueError:
        return None


def main():
    # 1. the scored ids at s10 for (recorded, incumbent, none) from P3's event log
    scored_ids = set()
    with open(HERE / "p3_events.csv", newline="") as fh:
        for r in csv.DictReader(fh):
            if r["convention"] != "recorded" or r["stop"] != "incumbent" or r["target"] != "none":
                continue
            if int(r["elapsed"]) >= PRIMARY_K:
                scored_ids.add(int(r["id"]))

    # 2. the s10 population from the trigger extract, elapsed via the real trading-day calendar
    trig, td_cache = {}, {}
    with open(HERE / "trigger.csv", newline="") as fh:
        for r in csv.DictReader(fh):
            trig[int(r["id"])] = r
    status = {}
    for rid, r in trig.items():
        fd = date.fromisoformat(r["fire_date"])
        if fd not in td_cache:
            td_cache[fd] = len(_trading_days(fd + timedelta(days=1), LAST_SESSION)[:WINDOW])
        if td_cache[fd] < PRIMARY_K:
            continue
        ep, sp = _f(r["entry_price"]), _f(r["stop_price"])
        if rid in scored_ids:
            status[rid] = "scored"
        elif ep is None or sp is None or sp >= ep:
            status[rid] = "killed"
        else:
            status[rid] = "abstain"

    def summarise(ids, floor=None):
        if floor is not None:
            ids = [i for i in ids if (_f(trig[i]["stop_width_pct"]) or 0.0) >= floor]
        n = len(ids)
        settled = [trig[i] for i in ids if trig[i]["outcome"] not in ("", None)]
        out = {"n": n, "n_settled": len(settled)}
        if not settled:
            return out
        oc = defaultdict(int)
        for r in settled:
            oc[r["outcome"]] += 1
        rr = [_f(r["realized_r"]) for r in settled]
        rr = [x for x in rr if x is not None]
        rt = [_f(r["realized_r_trail"]) for r in settled]
        rt = [x for x in rt if x is not None]
        mfe = [_f(r["mfe_r"]) for r in settled]
        mfe = [x for x in mfe if x is not None]
        r10 = [_f(r["r_none_s10"]) for r in settled]
        r10 = [x for x in r10 if x is not None]
        rt_sorted = sorted(rt)
        out.update({
            "m_trail_median_r": round(rt_sorted[len(rt_sorted) // 2], 4) if rt else None,
            "m_trail_max_r": round(max(rt), 2) if rt else None,
            "recorded_outcome_counts": dict(oc),
            "pct_outcome_stop": round(100.0 * oc.get("stop", 0) / len(settled), 2),
            "m_none_mean_r": round(sum(rr) / len(rr), 4) if rr else None,
            "m_none_pct_positive": round(100.0 * sum(1 for x in rr if x > 0) / len(rr), 2) if rr else None,
            "m_trail_mean_r": round(sum(rt) / len(rt), 4) if rt else None,
            "m_trail_pct_positive": round(100.0 * sum(1 for x in rt if x > 0) / len(rt), 2) if rt else None,
            "m_trail_ge_3r_pct": round(100.0 * sum(1 for x in rt if x >= 3) / len(rt), 2) if rt else None,
            "mfe_ge_3r_pct": round(100.0 * sum(1 for x in mfe if x >= 3) / len(mfe), 2) if mfe else None,
            "r_none_s10_mean": round(sum(r10) / len(r10), 4) if r10 else None,
            "r_none_s10_pct_positive": round(100.0 * sum(1 for x in r10 if x > 0) / len(r10), 2) if r10 else None,
        })
        return out

    groups = defaultdict(list)
    for rid, st in status.items():
        rung = trig[rid]["rung"]
        groups[(st, "ALL")].append(rid)
        groups[(st, rung)].append(rid)

    summary = {"population": "recorded convention, incumbent stop, no target, s10 population (>=10 sessions elapsed)",
               "counts": {st: sum(1 for s in status.values() if s == st) for st in ("scored", "abstain", "killed")},
               "by_status": {}, "by_status_floored_0p5pct": {}}
    for st in ("scored", "abstain"):
        summary["by_status"][st] = {}
        summary["by_status_floored_0p5pct"][st] = {}
        for rung in ("ALL", "ep_low_reclaim", "ep_close_reclaim", "ep_high_break", "ep_close_620_prox"):
            summary["by_status"][st][rung] = summarise(groups.get((st, rung), []))
            summary["by_status_floored_0p5pct"][st][rung] = summarise(groups.get((st, rung), []), floor=0.5)

    # 3. the direction, in one number per arm: recorded M-none / M-trail mean on abstained vs scored
    a, s = summary["by_status_floored_0p5pct"]["abstain"]["ALL"], summary["by_status_floored_0p5pct"]["scored"]["ALL"]
    summary["direction"] = {
        "note": "floored population (stop_width_pct >= 0.5, the grid's own floor); the unfloored M-trail mean is carried by near-zero-stop rows (max R listed) and is not read",
        "m_none_mean_r_abstain_minus_scored": (round(a["m_none_mean_r"] - s["m_none_mean_r"], 4)
                                               if a.get("m_none_mean_r") is not None and s.get("m_none_mean_r") is not None else None),
        "m_trail_mean_r_abstain_minus_scored": (round(a["m_trail_mean_r"] - s["m_trail_mean_r"], 4)
                                                if a.get("m_trail_mean_r") is not None and s.get("m_trail_mean_r") is not None else None),
        "m_trail_ge_3r_pct_abstain_minus_scored": (round(a["m_trail_ge_3r_pct"] - s["m_trail_ge_3r_pct"], 2)
                                                   if a.get("m_trail_ge_3r_pct") is not None and s.get("m_trail_ge_3r_pct") is not None else None),
    }
    with open(HERE / "p5_summary.json", "w") as fh:
        json.dump(summary, fh, indent=1)
    print(json.dumps(summary, indent=1))


if __name__ == "__main__":
    main()
