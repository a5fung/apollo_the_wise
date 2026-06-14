#!/usr/bin/env python3
"""#271 CLASS B (gate-free) — analyze the daily +/-20%/5d breadth series: universe stability
(the count-vs-% calibration decision), the distribution (extreme threshold), and the late-May
2026 window (Pradeep's 5/24 SPY exhaustion anchor). Read-only; mirrors t2108_color rigor (a
display annotation, NOT a trade gate — no forward-return backtest, per advisor 6/14)."""
from pathlib import Path

HERE = Path(__file__).resolve().parent
rows = []
for line in (HERE / "_271_breadth_series.tsv").read_text().splitlines():
    p = line.strip().split("|")
    if len(p) != 6:
        continue
    d, uni, up, dn, up5, dn5 = p
    rows.append({"d": d, "uni": int(uni), "up": int(up), "dn": int(dn),
                 "up5": int(up5), "dn5": int(dn5)})

# drop warmup (no 5d return yet) — keep days with a real universe
rows = [r for r in rows if r["uni"] > 1000]


def pct(xs, q):
    s = sorted(xs)
    return s[min(len(s) - 1, int(q / 100 * len(s)))]


unis = [r["uni"] for r in rows]
print(f"#271 CLASS B series: {len(rows)} trading days, {rows[0]['d']}..{rows[-1]['d']}\n")
print(f"UNIVERSE (count-vs-% check): min {min(unis)}  median {pct(unis,50)}  max {max(unis)}  "
      f"spread {max(unis)-min(unis)} ({(max(unis)-min(unis))/pct(unis,50)*100:.0f}% of median)")
print("  -> if spread is small, a raw COUNT threshold is stable (matches Pradeep); else normalize to %.\n")

for name, key in (("UP20 (up>=20%/5d = exhaustion side)", "up"),
                  ("DOWN20 (down>=20%/5d = washout side)", "dn"),
                  ("UP20 price>=$5", "up5"), ("DOWN20 price>=$5", "dn5")):
    xs = [r[key] for r in rows]
    pcts = [r[key] / r["uni"] * 100 for r in rows]
    print(f"{name}:")
    print(f"  count   p50 {pct(xs,50):4d}  p75 {pct(xs,75):4d}  p90 {pct(xs,90):4d}  "
          f"p95 {pct(xs,95):4d}  p99 {pct(xs,99):4d}  max {max(xs)}")
    print(f"  %univ   p50 {pct(pcts,50):.1f}%  p90 {pct(pcts,90):.1f}%  p95 {pct(pcts,95):.1f}%  "
          f"p99 {pct(pcts,99):.1f}%  max {max(pcts):.1f}%")

# proposed CONVENTION thresholds (p90 of the $5-floor %univ series — display annotation, tunable)
up5_pcts = sorted(r["up5"] / r["uni"] * 100 for r in rows)
dn5_pcts = sorted(r["dn5"] / r["uni"] * 100 for r in rows)
AMBER = up5_pcts[int(0.90 * len(up5_pcts))]    # exhaustion: up>=20%/5d ($5) >= p90
GREEN = dn5_pcts[int(0.90 * len(dn5_pcts))]    # washout:   down>=20%/5d ($5) >= p90
print(f"\nPROPOSED CONVENTION thresholds ($5-floor, %univ, p90 — tunable like T2108's 20/85):")
print(f"  AMBER (exhaustion) up20_$5 >= {AMBER:.1f}% of universe;  GREEN (washout) down20_$5 >= {GREEN:.1f}%")

# extreme days each side ($5-floor = the proposed metric)
print("\nTOP-8 UP20_$5 days (exhaustion candidates):")
for r in sorted(rows, key=lambda r: -r["up5"])[:8]:
    print(f"  {r['d']}  up20_$5={r['up5']:4d} ({r['up5']/r['uni']*100:.1f}%)  down20_$5={r['dn5']:4d}  uni={r['uni']}")
print("\nTOP-8 DOWN20_$5 days (washout candidates):")
for r in sorted(rows, key=lambda r: -r["dn5"])[:8]:
    print(f"  {r['d']}  down20_$5={r['dn5']:4d} ({r['dn5']/r['uni']*100:.1f}%)  up20_$5={r['up5']:4d}  uni={r['uni']}")

# Pradeep anchor window: late May 2026 ($5-floor + does it light AMBER?)
print(f"\nPRADEEP 5/24 ANCHOR window (2026-05-18..05-29) — A=amber if up20_$5 >= {AMBER:.1f}%:")
for r in rows:
    if "2026-05-18" <= r["d"] <= "2026-05-29":
        up5p = r["up5"] / r["uni"] * 100
        lit = " <- AMBER" if up5p >= AMBER else ""
        print(f"  {r['d']}  up20_$5={r['up5']:4d} ({up5p:.1f}%)  "
              f"down20_$5={r['dn5']:4d} ({r['dn5']/r['uni']*100:.1f}%)  uni={r['uni']}{lit}")
