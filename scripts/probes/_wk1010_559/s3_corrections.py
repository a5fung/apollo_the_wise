"""#559 era-D re-cut — step 3: the lookups behind the 2026-10-10 verifier corrections that are NOT
replay outputs. $0, no network, no DB: reads c1_scope.out + c2_bars.out only.
Run: python3 scripts/probes/_wk1010_559/s3_corrections.py > scripts/probes/_wk1010_559/s3_corrections_out.txt
"""
from __future__ import annotations

import os
import sys
from collections import Counter, defaultdict
from datetime import date

P = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, P)
from readcap import read_sections, f  # noqa: E402

S1 = read_sections("c1_scope.out")
S2 = read_sections("c2_bars.out")
CLS = ["ep_rt_universe_catch", "ep_rt_floor_flip_up", "ep_rt_admit", "ep_rt_live_miss"]
sl = defaultdict(list)
for r in S1["SCANLOG"]:
    sl[(r["scan_date"], r["ticker"])].append(r)
alerts = {(r["alert_date"], r["ticker"]): r for r in S1["ALERTS"]}
ev = defaultdict(list)
for r in S1["EVENTS"]:
    ev[(r["d"], r["ticker"])].append(r)


def graded_rows(k):
    return [r for r in sl.get(k, []) if r["reject_stage"] != "gap_floor"]


def show_scan(k, all_rows=False):
    rows = sl.get(k, []) if all_rows else graded_rows(k)
    print(f"  {k[0]} {k[1]}: {len(sl.get(k, []))} scan rows, {len(graded_rows(k))} past the gap floor")
    for r in rows:
        print(f"     {r['scan_et']} stage={r['reject_stage'] or '(passed)':17s} score={r['ep_score'] or '-':>5s} "
              f"tier={r['score_tier'] or '-':9s} cat={r['catalyst_quality'] or '-':8s} | {r['filter_reason'][:78]}")


print("=" * 100)
print("1. THE 'GRADE KEEPS THEM OUT' CLAIM — names behind the tail, by recorded stage")
print("=" * 100)
for k in (("2026-09-17", "NUAI"), ("2026-10-01", "TDAY"), ("2026-09-09", "FTK"), ("2026-09-18", "FWDI"),
          ("2026-09-08", "RGTI"), ("2026-09-17", "ATTO")):
    show_scan(k)
bgsi = [k for k in sl if k[1] == "BGSI"]
print("  BGSI (the one in-window name that never held the floor at a scan tick):")
for k in sorted(bgsi):
    stages = Counter(r["reject_stage"] for r in sl[k])
    print(f"     {k}: stages {dict(stages)}; first event "
          f"{[(r['event_type'][6:], r['tick_et'], r['rt_gap']) for r in ev.get(k, []) if r['event_type'] in CLS][:2]}")
# FTK's opening bar
ftk = [r for r in S2["MIN"] if r["ticker"] == "FTK" and r["et_min"].startswith("2026-09-09 09:3")]
print("  FTK 2026-09-09 first minute bars (et_min open high low close volume):")
for r in ftk[:4]:
    print(f"     {r['et_min']} {r['open']} {r['high']} {r['low']} {r['close']} vol {r['volume']}")

print()
print("=" * 100)
print("2. TRADES THE SWITCHES ADDED — CEG 10-06 and PENG 10-07: real-time vs delayed feed through the morning")
print("=" * 100)
for k in (("2026-10-06", "CEG"), ("2026-10-07", "PENG")):
    print(f"  {k[0]} {k[1]} alert: " + str({a: alerts[k][a] for a in ('detected_et', 'gap_pct', 'ep_score', 'score_tier')}))
    for r in ev[k]:
        if r["event_type"] in CLS + ["ep_rt_floor_flip_down"]:
            print(f"     event {r['tick_et']} {r['event_type'][6:]:16s} rt {r['rt_gap']}% delayed {r['delayed_gap']}%  "
                  f"{r['summary'][:90]}")
    rows = sorted(sl[k], key=lambda r: r["scan_et"])
    dl_first = [(r["scan_et"], r["gap_pct_rt"], r["gap_pct_delayed"]) for r in rows
                if r["gap_pct_delayed"] and float(r["gap_pct_delayed"]) >= 9.0]
    print(f"     scan ticks where the DELAYED feed read >= 9% (scan_et, rt, delayed): {dl_first[:6]}")
    print(f"     scan ticks <= 09:44 where rt >= 9%: "
          f"{[(r['scan_et'], r['gap_pct_rt']) for r in rows if r['gap_pct_rt'] and float(r['gap_pct_rt']) >= 9.0 and r['scan_et'] <= '09:44:59'][:4]}")
print("  in-window HIGH alerts (09:31-09:44) and what the live book did with each:")
trades = {(t["alert_date"], t["ticker"]): t for t in S1["TRADES"]}
for a in sorted(S1["ALERTS"], key=lambda x: (x["alert_date"], x["ticker"])):
    if a["score_tier"] == "HIGH" and "09:31:00" <= a["detected_et"] <= "09:44:59":
        t = trades.get((a["alert_date"], a["ticker"]))
        print(f"     {a['alert_date']} {a['ticker']:5s} det {a['detected_et']} live={t['status'] if t else 'no row'} "
              f"{(t['skip_reason'] or '')[:50] if t else ''}")

print()
print("=" * 100)
print("3. THE FIVE HIGH ALERTS LOST TO THE 09:45 WINDOW — admission or feed timing?")
print("=" * 100)
for tk, d in (("ONON", "2026-09-22"), ("ACN", "2026-10-01"), ("SNPS", "2026-10-01"), ("TLN", "2026-10-06"), ("VST", "2026-10-06")):
    k = (d, tk)
    a = alerts[k]
    first = min((r for r in ev[k] if r["event_type"] in CLS), key=lambda r: r["tick_et"])
    t = trades[k]
    print(f"  {d} {tk:5s} alert det {a['detected_et']} score {a['ep_score']} {a['score_tier']} | first real-time read "
          f"{first['tick_et']} ({first['event_type'][6:]}, rt {first['rt_gap']}% / delayed {first['delayed_gap']}%) | "
          f"live={t['status']} {t['skip_reason'][:30]}")
    sc = [(r["scan_et"], r["ep_score"], r["score_tier"], r["reject_stage"]) for r in sorted(sl[k], key=lambda r: r["scan_et"])
          if r["ep_score"] or r["reject_stage"] in ("score_bar", "post_grade_filter", "duplicate", "")]
    print(f"        graded scan rows (scan_et, score, tier, stage): {sc[:9]}")

print("  scan-tick vs one-minute view of the three that first read >= 9% at/after 09:45 (SNPS, TLN, VST):")
mins = defaultdict(list)
for r in S2["MIN"]:
    mins[r["ticker"]].append(r)
for tk, d in (("SNPS", "2026-10-01"), ("TLN", "2026-10-06"), ("VST", "2026-10-06")):
    pc = float(sorted({r["prev_close"] for r in sl[(d, tk)] if r["prev_close"]})[0])
    floor_px = pc * 1.09
    bars = [r for r in mins[tk] if r["et_min"].startswith(d) and "09:31" <= r["et_min"][11:] <= "09:59"]
    touch = [r["et_min"][11:] for r in bars if f(r["high"]) >= floor_px and r["et_min"][11:] <= "09:44"]
    ticks = [(r["scan_et"][:5], r["gap_pct_rt"]) for r in sorted(sl[(d, tk)], key=lambda r: r["scan_et"]) if "09:30" <= r["scan_et"] <= "09:59"]
    print(f"     {tk} {d}: prev close {pc}, 9% floor price {floor_px:.2f}; scan ticks 09:30-09:59 (time, rt gap%): {ticks}")
    print(f"        one-minute bars 09:31-09:44 whose HIGH was >= the floor price: {touch}")

print()
print("=" * 100)
print("4. RAW REAL-TIME EVENT RATE — 08-10 baseline window vs this window (the four admit classes)")
print("=" * 100)


def trading_days(a: date, b: date):
    out, d = [], a
    from datetime import timedelta
    while d <= b:
        if d.weekday() < 5:
            out.append(d)
        d += timedelta(days=1)
    return out


base = {r["event_type"]: int(r["n"]) for r in S1["BASELINE_EVCOUNT"]}
base_days = trading_days(date(2026, 7, 21), date(2026, 8, 10))
win_counts = Counter()
per_day_admit = Counter()
days_with = set()
for r in S1["EVCOUNT"]:
    if r["event_type"] in CLS:
        win_counts[r["event_type"]] += int(r["n"])
        days_with.add(r["d"])
        if r["event_type"] == "ep_rt_admit":
            per_day_admit[r["d"]] += int(r["n"])
win_days = trading_days(date(2026, 9, 8), date(2026, 10, 9))
print(f"  baseline 2026-07-21..2026-08-10: weekdays {len(base_days)} (no market holiday in range); counts {base}; "
      f"total {sum(base.values())} -> {sum(base.values()) / len(base_days):.1f}/day")
print(f"  this window 2026-09-08..2026-10-09: weekdays {len(win_days)} (Columbus Day 10-12 is outside); "
      f"counts {dict(win_counts)}; total {sum(win_counts.values())} -> {sum(win_counts.values()) / len(win_days):.1f}/day")
print(f"  ratio of raw events/day: {(sum(base.values()) / len(base_days)) / (sum(win_counts.values()) / len(win_days)):.2f}x")
print(f"  ep_rt_admit per day in this window: min {min(per_day_admit.values())}, max {max(per_day_admit.values())}, "
      f"days with any {len(per_day_admit)}; baseline ep_rt_admit {base.get('ep_rt_admit')} over {len(base_days)} days "
      f"= {base.get('ep_rt_admit', 0) / len(base_days):.1f}/day")
print(f"  ep_rt_admit per day sorted: {sorted(per_day_admit.values())}")
