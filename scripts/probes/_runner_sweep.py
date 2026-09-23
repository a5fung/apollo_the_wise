#!/usr/bin/env python3
"""Runner-rule sweep — what happens to the 2/3 after the +2R partial (2026-08-29, $0).

Drives scripts/probes/_bt_replay.py (EXTENDED in place with runner_rule — the same file,
not a copy; its self-tests + both mutation tests + the runner-rule battery are green).
Cohort = run 1's Run U replayable rows, loaded from the SAME captures
(/Users/alvinfung/.claude/jobs/6b173ac9/tmp/bt_*). GATE: the control rule must reproduce
run 1's stored per-row outcomes on all 295 rows before any other rule is trusted.
Everything upstream of the partial is identical across rules by construction (the
pre-partial walk is shared code, not a convention).

Outputs: runner_sweep_results.json + runner_sweep_rows.tsv under the job tmp dir.
Read-only; no DB access at all (captures only).
"""
import bisect, json, statistics, sys
from collections import defaultdict
from datetime import date

sys.path.insert(0, "/Users/alvinfung/apollo_the_wise")
from scripts.probes._bt_replay import replay_trade, _fill_entry, PARTIAL_FRACTION

TMP = "/Users/alvinfung/.claude/jobs/6b173ac9/tmp"
THIRD = PARTIAL_FRACTION
TWO3 = 1 - PARTIAL_FRACTION


def pd(s):
    return date.fromisoformat(s)


adm = json.load(open(f"{TMP}/bt_admission_result.json"))
rows_u = adm["U"]["replayable"]

# minute bars (same loader as _bt_run1_replay.py)
mbars = defaultdict(list)
for line in open(f"{TMP}/bt_out_bars.psv"):
    f = line.rstrip("\n").split("|")
    if len(f) != 7:
        continue
    mbars[(pd(f[1]), f[0])].append((f[2], float(f[3]), float(f[4]), float(f[5]), float(f[6])))

# daily rows: ticker|date|open|high|low|close|volume — keep OPEN this time (gap pricing)
daily = defaultdict(list)
for line in open(f"{TMP}/bt_out_daily.psv"):
    f = line.rstrip("\n").split("|")
    if len(f) != 7:
        continue
    o = float(f[2]) if f[2] else None
    h = float(f[3]) if f[3] else None
    l = float(f[4]) if f[4] else None
    daily[f[0]].append((pd(f[1]), o, h, l, float(f[5])))
for t in daily:
    daily[t].sort()
all_dates = sorted({r[0] for rows in daily.values() for r in rows})
HORIZON = 40


def daily_bars_after(t, d):
    """(bars, coverage_ok) — identical calendar/NULL semantics to _bt_run1_replay.py,
    plus each bar carries 'open' (may be None) for the gap-fill sensitivity pricing."""
    gi = bisect.bisect_right(all_dates, d)
    expected = all_dates[gi:gi + HORIZON]
    rows = {r[0]: r for r in daily.get(t, [])}
    bars, ok = [], True
    for ed in expected:
        r = rows.get(ed)
        if r is None or r[2] is None or r[3] is None:
            ok = False
            break
        bars.append({"open": r[1], "high": r[2], "low": r[3], "close": r[4]})
    return bars, ok


def prior_closes(t, d, n=27):
    """The stock's closes strictly before d, oldest-first, last n (live: ~40 calendar
    days ending D-1, #548)."""
    rows = daily.get(t, [])
    dates = [r[0] for r in rows]
    hi = bisect.bisect_left(dates, d)
    return [r[4] for r in rows[max(0, hi - n):hi]]


def atr14_abs(t, d):
    """Absolute ATR14 through d-1 — the admission filter's own arithmetic
    (_bt_run1_admission.atr14_pct), un-normalized."""
    rows = daily.get(t, [])
    dates = [r[0] for r in rows]
    hi = bisect.bisect_left(dates, d)
    rows = [r for r in rows[max(0, hi - 35):hi] if r[2] is not None and r[3] is not None]
    if len(rows) < 10:
        return None
    trs = []
    for i in range(1, len(rows)):
        h, l, pc = rows[i][2], rows[i][3], rows[i - 1][4]
        trs.append(max(h - l, abs(h - pc), abs(l - pc)))
    if not trs:
        return None
    w = trs[-14:]
    return sum(w) / len(w)


def day0_close(t, d):
    rows = daily.get(t, [])
    for r in rows:
        if r[0] == d:
            return r[4]
    return None


def replay_one(d, t, rule, gap_fill=False):
    """Same ORB-window guard as _bt_run1_replay.replay_one, plus the runner rule."""
    bars = mbars.get((d, t), [])
    orb = next(({"high": b[2], "low": b[3]} for b in bars if b[0] == "09:30"), None)
    entry_all = [{"open": b[1], "high": b[2], "low": b[3], "close": b[4]}
                 for b in bars if b[0] > "09:30"]
    entry_win = [{"open": b[1], "high": b[2], "low": b[3], "close": b[4]}
                 for b in bars if "09:30" < b[0] <= "09:59"]
    dbars, cov_ok = daily_bars_after(t, d)
    ctx = {"prior_closes": prior_closes(t, d), "atr14": atr14_abs(t, d),
           "day0_close": day0_close(t, d)}
    if orb is None:
        return replay_trade(t, d, None, entry_all, dbars, coverage_ok=cov_ok,
                            runner_rule=rule, runner_ctx=ctx, gap_fill_at_open=gap_fill)
    fill_idx, _ = _fill_entry(orb["high"], entry_win)
    if fill_idx is None:
        return replay_trade(t, d, orb, entry_win, [], coverage_ok=True,
                            runner_rule=rule, runner_ctx=ctx, gap_fill_at_open=gap_fill)
    return replay_trade(t, d, orb, entry_all, dbars, coverage_ok=cov_ok,
                        runner_rule=rule, runner_ctx=ctx, gap_fill_at_open=gap_fill)


# ── GATE: control must reproduce run 1's stored outcomes row-for-row ──────────────────
mismatch = 0
for a in rows_u:
    r = replay_one(pd(a["d"]), a["t"], "breakeven")
    same_reason = (r.reason == a["reason"])
    stored = a.get("r")
    same_r = (r.r_multiple is None and stored is None) or \
             (r.r_multiple is not None and stored is not None and abs(r.r_multiple - stored) < 1e-9)
    if not (same_reason and same_r):
        mismatch += 1
        print(f"MISMATCH {a['t']} {a['d']}: stored {a['reason']}/{stored} vs {r.reason}/{r.r_multiple}")
assert mismatch == 0, f"{mismatch} rows diverge from run 1 — STOP, do not trust the sweep"
print(f"GATE PASS: control reproduces run 1 on all {len(rows_u)} Run-U rows")

RULES = ["breakeven", "hard", "live_trail_be", "sma10", "sma20", "atr1", "atr2",
         "gb25", "gb50", "t3", "t5", "t10", "t20"]
SENS = ["sma10_touch", "sma20_touch"]

# missing-input census (loud degradation counts)
no_atr = [a["t"] + " " + a["d"] for a in rows_u if atr14_abs(pd(a["d"]), a["t"]) is None]
no_atr = [f"{a['t']} {a['d']}" for a in rows_u if atr14_abs(a["t"], pd(a["d"])) is None]
short_prior = [f"{a['t']} {a['d']}" for a in rows_u if len(prior_closes(a["t"], pd(a["d"]))) < 20]
no_d0 = [f"{a['t']} {a['d']}" for a in rows_u if day0_close(a["t"], pd(a["d"])) is None]
print(f"inputs: no ATR14 {len(no_atr)} {no_atr[:5]} | <20 prior closes {len(short_prior)} "
      f"{short_prior[:8]} | no day0 close {len(no_d0)} {no_d0[:5]}")

results = {r: {} for r in RULES + SENS}
rowdump = []
for rule in RULES + SENS:
    per = {}
    for a in rows_u:
        res = replay_one(pd(a["d"]), a["t"], rule)
        per[(a["t"], a["d"])] = res
    results[rule]["per"] = per

# gap-fill sensitivity (touch rules only — close-priced rules are unaffected by definition)
gapsens = {}
for rule in ["breakeven", "hard", "atr1", "atr2", "t10", "t20"]:
    per = {}
    for a in rows_u:
        res = replay_one(pd(a["d"]), a["t"], rule, gap_fill=True)
        per[(a["t"], a["d"])] = res
    gapsens[rule] = per

# ── fixed cohort = control-scored rows (n=194) ────────────────────────────────────────
ctrl = results["breakeven"]["per"]
cohort = [k for k, v in ctrl.items() if v.r_multiple is not None]
assert len(cohort) == 194, f"cohort {len(cohort)} != 194"
TOP2 = {("AOSL", "2026-04-14"), ("BABA", "2026-07-08")}


def summarize(per, name):
    scored = {k: per[k] for k in cohort if per[k].r_multiple is not None}
    dropped = [k for k in cohort if per[k].r_multiple is None]
    xs = [v.r_multiple for v in scored.values()]
    tgt = {k: v for k, v in scored.items() if v.reason == "target"}
    runner = {k: (v.r_multiple - THIRD) / TWO3 for k, v in tgt.items()}
    ex2 = [v.r_multiple for k, v in scored.items() if k not in TOP2]
    deltas = {k: scored[k].r_multiple - ctrl[k].r_multiple for k in scored}
    worse = {k: d for k, d in deltas.items() if d < -1e-9}
    better = {k: d for k, d in deltas.items() if d > 1e-9}
    open_end = [k for k, v in tgt.items() if v.detail == "held_to_close_after_partial"]
    gap_exits = [k for k, v in tgt.items() if v.detail and "gap_open" in v.detail]
    s = {
        "rule": name, "n": len(xs),
        "unresolvable_vs_control": len(dropped), "dropped": [f"{t} {d}" for t, d in dropped],
        "mean": round(statistics.mean(xs), 4), "median": round(statistics.median(xs), 4),
        "total": round(sum(xs), 2), "win": round(sum(1 for x in xs if x > 0) / len(xs), 3),
        "mean_ex_top2": round(statistics.mean(ex2), 4),
        "median_ex_top2": round(statistics.median(ex2), 4),
        "n_target": len(tgt),
        "tgt_at_exact_third": sum(1 for k, v in tgt.items() if abs(v.r_multiple - THIRD) < 1e-9),
        "tgt_below_third": sum(1 for v in tgt.values() if v.r_multiple < THIRD - 1e-9),
        "tgt_above_third": sum(1 for v in tgt.values() if v.r_multiple > THIRD + 1e-9),
        "runner_mean": round(statistics.mean(runner.values()), 3) if runner else None,
        "runner_median": round(statistics.median(runner.values()), 3) if runner else None,
        "runner_max": round(max(runner.values()), 2) if runner else None,
        "n_worse_than_ctrl": len(worse), "R_given_up": round(sum(worse.values()), 2),
        "n_better_than_ctrl": len(better), "R_gained": round(sum(better.values()), 2),
        "still_open_at_data_end": len(open_end),
        "open_end_names": [f"{t} {d}" for t, d in sorted(open_end)][:40],
        "touch_exits_through_gap_open": len(gap_exits),
    }
    return s


table = []
for rule in RULES + SENS:
    s = summarize(results[rule]["per"], rule)
    table.append(s)
    print(f"{rule:>14}: n={s['n']} mean={s['mean']:+.3f} med={s['median']:+.3f} "
          f"tot={s['total']:+.1f} exact1/3={s['tgt_at_exact_third']} "
          f"below={s['tgt_below_third']} above={s['tgt_above_third']} "
          f"worse={s['n_worse_than_ctrl']}({s['R_given_up']}) "
          f"better={s['n_better_than_ctrl']}(+{s['R_gained']}) "
          f"ex2mean={s['mean_ex_top2']:+.3f} open@end={s['still_open_at_data_end']} "
          f"gapx={s['touch_exits_through_gap_open']} drop={s['unresolvable_vs_control']}")

# gap-fill sensitivity summary
gaptab = {}
for rule, per in gapsens.items():
    xs = [per[k].r_multiple for k in cohort if per[k].r_multiple is not None]
    base = [results[rule]["per"][k].r_multiple for k in cohort
            if results[rule]["per"][k].r_multiple is not None and per[k].r_multiple is not None]
    paired = [(per[k].r_multiple, results[rule]["per"][k].r_multiple) for k in cohort
              if per[k].r_multiple is not None and results[rule]["per"][k].r_multiple is not None]
    dmean = statistics.mean(g - b for g, b in paired)
    gaptab[rule] = {"n": len(paired), "mean_at_level": round(statistics.mean(b for _, b in paired), 4),
                    "mean_at_open": round(statistics.mean(g for g, _ in paired), 4),
                    "delta_mean": round(dmean, 4)}
    print(f"gap-fill {rule:>10}: mean {gaptab[rule]['mean_at_level']:+.3f} -> "
          f"{gaptab[rule]['mean_at_open']:+.3f} (delta {dmean:+.4f})")

# concentration: each rule's top-5 trades and their share of total R
conc = {}
for rule in RULES:
    per = results[rule]["per"]
    scored = sorted(((per[k].r_multiple, k) for k in cohort if per[k].r_multiple is not None),
                    reverse=True)
    tot = sum(x for x, _ in scored)
    top5 = scored[:5]
    conc[rule] = {"top5": [(f"{t} {d}", round(x, 2)) for x, (t, d) in top5],
                  "top5_share_of_total": round(sum(x for x, _ in top5) / tot, 2) if tot else None}

# per-row dump for the record
with open(f"{TMP}/runner_sweep_rows.tsv", "w") as fh:
    fh.write("ticker\tdate\t" + "\t".join(RULES + SENS) + "\tctrl_reason\n")
    for k in sorted(cohort, key=lambda k: (k[1], k[0])):
        vals = []
        for rule in RULES + SENS:
            v = results[rule]["per"][k].r_multiple
            vals.append("" if v is None else f"{v:.4f}")
        fh.write(f"{k[0]}\t{k[1]}\t" + "\t".join(vals) + f"\t{ctrl[k].reason}\n")

json.dump({"table": table, "gap_sensitivity": gaptab, "concentration": conc,
           "inputs": {"no_atr14": no_atr, "short_prior": short_prior, "no_day0": no_d0}},
          open(f"{TMP}/runner_sweep_results.json", "w"), indent=1)
print(f"\nwrote {TMP}/runner_sweep_results.json + runner_sweep_rows.tsv")
