#!/usr/bin/env python3
"""EP backtest run 1 — Stage 3 replay + scoring. Drives scripts/probes/_bt_replay.py
UNCHANGED (the verified harness). Caller-side ORB-window guard: a fill must occur in
09:31-09:59 (live 10:00 unfilled-cancel); the guard pre-checks the 09:31-09:59 subset
with the harness's own _fill_entry, then hands the full day-0 stream to replay_trade
(same fill bar by construction — _fill_entry scans in order and the subset is a prefix)."""
import bisect, json, statistics, sys
from collections import defaultdict
from datetime import date, timedelta

sys.path.insert(0, "/Users/alvinfung/apollo_the_wise")
from scripts.probes._bt_replay import replay_trade, _fill_entry

TMP = "/Users/alvinfung/.claude/jobs/6b173ac9/tmp"
def pd(s): return date.fromisoformat(s)

adm = json.load(open(f"{TMP}/bt_admission_result.json"))

# minute bars
mbars = defaultdict(list)   # (date,ticker) -> [(hhmm, o,h,l,c)]
for line in open(f"{TMP}/bt_out_bars.psv"):
    f = line.rstrip("\n").split("|")
    if len(f) != 7: continue
    mbars[(pd(f[1]), f[0])].append((f[2], float(f[3]), float(f[4]), float(f[5]), float(f[6])))

# daily closes (for exit walk + coverage calendar)
daily = defaultdict(list)
for line in open(f"{TMP}/bt_out_daily.psv"):
    f = line.rstrip("\n").split("|")
    if len(f) != 7: continue
    h = float(f[3]) if f[3] else None; l = float(f[4]) if f[4] else None
    daily[f[0]].append((pd(f[1]), h, l, float(f[5])))
for t in daily: daily[t].sort()
all_dates = sorted({r[0] for rows in daily.values() for r in rows})
LAST_DATE = all_dates[-1]
HORIZON = 40

def daily_bars_after(t, d):
    """(bars, coverage_ok). Expected calendar: global sessions in (d, d+40] capped at LAST_DATE.
    Missing session or NULL H/L inside the expected window -> coverage_ok=False."""
    gi = bisect.bisect_right(all_dates, d)
    expected = all_dates[gi:gi + HORIZON]
    rows = {r[0]: r for r in daily.get(t, [])}
    bars, ok = [], True
    for ed in expected:
        r = rows.get(ed)
        if r is None or r[1] is None or r[2] is None:
            ok = False
            break
        bars.append({"high": r[1], "low": r[2], "close": r[3]})
    return bars, ok

def replay_one(d, t):
    bars = mbars.get((d, t), [])
    orb = next(({"high": b[2], "low": b[3]} for b in bars if b[0] == "09:30"), None)
    entry_all = [{"open": b[1], "high": b[2], "low": b[3], "close": b[4]}
                 for b in bars if b[0] > "09:30"]
    entry_win = [{"open": b[1], "high": b[2], "low": b[3], "close": b[4]}
                 for b in bars if "09:30" < b[0] <= "09:59"]
    dbars, cov_ok = daily_bars_after(t, d)
    if orb is None:
        return replay_trade(t, d, None, entry_all, dbars, coverage_ok=cov_ok)
    fill_idx, _ = _fill_entry(orb["high"], entry_win)
    if fill_idx is None:   # no fill by 09:59 -> live cancels at 10:00
        return replay_trade(t, d, orb, entry_win, [], coverage_ok=True)
    return replay_trade(t, d, orb, entry_all, dbars, coverage_ok=cov_ok)

def stats(rs):
    scored = [r for r in rs if r.r_multiple is not None]
    xs = [r.r_multiple for r in scored]
    reasons = defaultdict(int)
    for r in rs: reasons[r.reason] += 1
    out = dict(n_replayed=len(rs), n_scored=len(scored), reasons=dict(reasons))
    if xs:
        out.update(mean=round(statistics.mean(xs), 3), median=round(statistics.median(xs), 3),
                   total=round(sum(xs), 2), win=round(sum(1 for x in xs if x > 0) / len(xs), 3),
                   best=round(max(xs), 2), worst=round(min(xs), 2))
    return out

results = {}
for run in ("L", "U"):
    rows = adm[run]["replayable"]
    rs = []
    for a in rows:
        r = replay_one(pd(a["d"]), a["t"])
        rs.append(r)
        a["reason"], a["r"] = r.reason, r.r_multiple
    results[run] = dict(stats=stats(rs))
    print(f"\n== RUN {run} ==")
    print(json.dumps(results[run]["stats"], indent=1))
    scored = [(a["r"], a["t"], a["d"]) for a in rows if a.get("r") is not None]
    scored.sort()
    print("worst 3:", [(t, d, round(r, 2)) for r, t, d in scored[:3]])
    print("best 3:", [(t, d, round(r, 2)) for r, t, d in scored[-3:]])
    # single-big-mover check
    xs = sorted(a["r"] for a in rows if a.get("r") is not None)
    if len(xs) > 2:
        trimmed = xs[1:-1]
        print(f"ex best+worst: mean {statistics.mean(trimmed):.3f} median {statistics.median(trimmed):.3f} n={len(trimmed)}")
    # splits by month and gap band (U only meaningful)
    bymonth, byband = defaultdict(list), defaultdict(list)
    for a in rows:
        if a.get("r") is None: continue
        bymonth[a["d"][:7]].append(a["r"])
        g = a["eff_gap"]
        band = "9-10" if g < 10 else "10-15" if g < 15 else "15-20" if g < 20 else "20+"
        byband[band].append(a["r"])
    for k in sorted(bymonth):
        v = bymonth[k]
        print(f"  {k}: n={len(v)} mean={statistics.mean(v):.2f} med={statistics.median(v):.2f}")
    for k in ["9-10", "10-15", "15-20", "20+"]:
        v = byband.get(k, [])
        if v: print(f"  gap {k}: n={len(v)} mean={statistics.mean(v):.2f} med={statistics.median(v):.2f}")

json.dump({run: results[run]["stats"] for run in results}, open(f"{TMP}/bt_replay_stats.json", "w"), indent=1)
json.dump(adm, open(f"{TMP}/bt_admission_result.json", "w"), default=str)
print("\nwrote bt_replay_stats.json; annotated bt_admission_result.json")
