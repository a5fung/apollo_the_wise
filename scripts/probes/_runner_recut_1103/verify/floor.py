#!/usr/bin/env python3
"""BLIND verifier: the #718 open-floor cut, computed straight from the 10-16 captures (stdlib only).

Rule under test: a Run-U row is dropped when its 09:30 OPEN < round(prev_close x 1.09, 6).
Open = the 09:30 minute bar's open in bt_out_bars (field 3); prev_close = the admission row's.
Cross-checks: the admission row's own 'open'; the daily capture's last close before the entry date.
"""
import gzip
import json
from collections import Counter, defaultdict

CAP = "/Users/alvinfung/apollo_the_wise/scripts/probes/_runner_recut_1017/captures"


def load():
    adm = json.load(gzip.open(f"{CAP}/bt_admission_result.json.gz", "rt"))
    rows = adm["U"]["replayable"]
    o930 = {}
    for line in gzip.open(f"{CAP}/bt_out_bars.psv.gz", "rt"):
        f = line.rstrip("\n").split("|")
        if len(f) != 7 or f[2] != "09:30":
            continue
        k = (f[0], f[1])
        assert k not in o930, f"duplicate 09:30 bar {k}"
        o930[k] = float(f[3])
    daily = defaultdict(list)
    for line in gzip.open(f"{CAP}/bt_out_daily.psv.gz", "rt"):
        f = line.rstrip("\n").split("|")
        if len(f) != 7:
            continue
        daily[f[0]].append((f[1], float(f[5])))
    for t in daily:
        daily[t].sort()
    return rows, o930, daily


def classify():
    rows, o930, daily = load()
    out = []
    for r in rows:
        t, d, pc = r["t"], r["d"], r["prev_close"]
        floor_px = round(pc * 1.09, 6)
        bar_open = o930.get((t, d))
        src = "bar" if bar_open is not None else "admission_row"
        op = bar_open if bar_open is not None else r["open"]
        prior = [c for (dd, c) in daily.get(t, []) if dd < d]
        out.append(dict(t=t, d=d, prev_close=pc, floor=floor_px, open=op, open_src=src, adm_open=r["open"],
                        dropped=op < floor_px, adm_dropped=r["open"] < floor_px,
                        daily_prev=prior[-1] if prior else None,
                        gap_open=r["gap_open"], gap_scan=r["gap_scan"], eff_gap=r["eff_gap"],
                        pct_vs_floor=(op / floor_px - 1) * 100))
    return out


def dropped_keys():
    return {(x["t"], x["d"]) for x in classify() if x["dropped"]}


if __name__ == "__main__":
    c = classify()
    n = len(c)
    drop = [x for x in c if x["dropped"]]
    print(f"rows {n}; dropped {len(drop)}; kept {n - len(drop)}")
    print(f"open source: {Counter(x['open_src'] for x in c)}")
    print(f"admission-row open on the same side of the floor: {sum(x['dropped'] == x['adm_dropped'] for x in c)} of {n}; "
          f"value differs (>1e-9) on {sum(abs(x['open'] - x['adm_open']) > 1e-9 for x in c)}")
    print(f"prev_close == daily capture's prior close (1e-9): {sum(x['daily_prev'] is not None and abs(x['daily_prev'] - x['prev_close']) < 1e-9 for x in c)} of {n}")
    ties = [x for x in c if x["open"] == x["floor"]]
    print(f"exact ties open == floor: {[(x['t'], x['d']) for x in ties]}")
    print(f"seed arms (gap_open>=9, gap_scan>=9): all {Counter((x['gap_open'] >= 9, x['gap_scan'] >= 9) for x in c)}; "
          f"dropped {Counter((x['gap_open'] >= 9, x['gap_scan'] >= 9) for x in drop)}; "
          f"kept {Counter((x['gap_open'] >= 9, x['gap_scan'] >= 9) for x in c if not x['dropped'])}")
    print(f"gap_open of kept rows min {min(x['gap_open'] for x in c if not x['dropped'])}; "
          f"of dropped max {max(x['gap_open'] for x in drop)}")
    # gap_open recomputed from the bar open, to see whether gap_open uses the bar or the admission open
    print(f"bar-open gap >= 9.0 exactly matches 'not dropped' on {sum(((x['open']/x['prev_close']-1)*100 >= 9.0) == (not x['dropped']) for x in c)} of {n}")
    near = sorted([x for x in drop if x["pct_vs_floor"] > -0.10], key=lambda x: -x["pct_vs_floor"])
    print("dropped within 0.10% under the floor (open/floor - 1):",
          [(x["t"], x["d"], round(x["pct_vs_floor"], 3), round((x['open']/x['prev_close']-1)*100 - 9, 3)) for x in near])
    near_above = sorted([x for x in c if not x["dropped"] and x["pct_vs_floor"] < 0.10], key=lambda x: x["pct_vs_floor"])
    print("kept within 0.10% above the floor:", [(x["t"], x["d"], round(x["pct_vs_floor"], 3)) for x in near_above])
    print("dropped list:", ", ".join(f"{x['t']} {x['d'][5:]}" for x in sorted(drop, key=lambda x: (x['d'], x['t']))))
    json.dump(c, open("/Users/alvinfung/apollo_the_wise/scripts/probes/_runner_recut_1103/verify/floor_rows.json", "w"), indent=0)
