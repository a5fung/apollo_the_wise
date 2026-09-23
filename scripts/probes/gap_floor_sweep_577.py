#!/usr/bin/env python3
"""#577 MIN_GAP_PCT floor sweep — the operator asked "loosen to what though?" Price the options.

READ-ONLY, $0. Consumes the already-captured _552_cohort.psv (tier-A real-stock gap-day cohort,
2026-03-01..07-15, gap>=8%, close>=$10, $vol>=$50M — capture-once-read-many) plus
_577gap_prod_capture.txt (one-shot prod reads, 2026-08-19: scan-log band volumes in the 8.0-floor
era 04-13..05-15, tick detail for the 3 log-era excluded winners, minute-bar coverage check).

Measures, per candidate floor {10.0 (today), 9.5, 9.0, 8.5, 8.0}:
  - winners admitted that 10.0 excludes: >=8xADR tail winners AND separately the evidence >=10R set
    (winner_r_available_2026-08-16.txt GEOMETRY 1, TDIC excluded as the source's own flagged artifact)
  - losers (non-winners) admitted
  - winner density of the resulting admitted pool (P4/P5) — both >=8xADR-level and >=10R-level
  - extra candidates/day: cohort tier-A basis (band rows / 92 sessions) and the LIVE scanner's own
    8.0-era count of names that NEVER crossed 10 intraday (Q9 in the capture — truly new names,
    since today's per-tick floor already admits any name whose delayed reading reaches 10%)
  - sum of geometry-1 R-available carried by the recovered >=10R names (P3: the tail SUM)
Plus the BAND+TRIGGER shape (8-10 at open -> WATCH -> tradeable on a 10% cross): the any-time-of-day
cross (day high >= 1.10 x prior close) is computable from daily bars; the 09:30-09:44-only variant is
NOT computable for 12 of the 15 (zero minute bars persisted — never alerted), stated, not estimated.

Basis caveat (P8, stated everywhere): cohort gap = SESSION OPEN vs prior close. The live scanner's
admission is per-tick on the ~15-min-delayed snapshot — a name under 10% at the open that crosses
10% intraday is ALREADY admitted today at the cross tick (SNOW 05-07 read 10.28 at 09:40 in-window;
UMC 05-06 read 10.64 at 09:30; QCOM 04-24 read 10.27). The floor binds hardest on names that NEVER
print 10%: at 8.0 four of the fifteen >=10R winners are in that class (NBIS ASX IREN SMTC).

THE LINE: measurement only. Nothing proposed, no code path touched, no toggle.
Usage: python3 scripts/probes/gap_floor_sweep_577.py
"""
from pathlib import Path

HERE = Path(__file__).resolve().parent
PSV = HERE / "_552_cohort.psv"

# GEOMETRY-1 >=10R set from docs/analysis/winner_r_available_2026-08-16.txt (26 names; TDIC is the
# source-flagged artifact and excluded from the "real" count, matching tests/fixtures/must_not_miss_eps.py).
R10 = {  # (ticker, date): R geometry-1
    ("MU", "2026-04-08"): 49.0, ("UMC", "2026-04-17"): 38.4, ("STRL", "2026-04-08"): 37.5,
    ("MRVL", "2026-03-31"): 35.4, ("ASX", "2026-04-08"): 31.6, ("SNDK", "2026-04-08"): 31.1,
    ("SNOW", "2026-05-07"): 24.5, ("ALGM", "2026-04-08"): 22.9, ("NBIS", "2026-04-08"): 20.5,
    ("AMKR", "2026-04-08"): 20.0, ("AEHR", "2026-03-31"): 19.7, ("TDIC", "2026-05-12"): 18.6,
    ("UMC", "2026-05-06"): 18.0, ("FLY", "2026-03-12"): 16.4, ("BE", "2026-04-08"): 15.9,
    ("USAR", "2026-04-08"): 15.5, ("QCOM", "2026-04-24"): 13.6, ("QBTS", "2026-04-08"): 13.0,
    ("AMD", "2026-04-24"): 12.6, ("HUT", "2026-04-08"): 11.5, ("QURE", "2026-05-29"): 11.1,
    ("ARM", "2026-05-06"): 11.0, ("SMTC", "2026-03-30"): 10.6, ("IREN", "2026-04-08"): 10.5,
    ("APLD", "2026-04-08"): 10.5, ("INTC", "2026-04-24"): 10.2,
}
ARTIFACT = {("TDIC", "2026-05-12")}

# Live-scanner extra-candidates/day, 8.0-floor era 04-13..05-15 (24 sessions), NEVER-crossed-10
# basis (max intraday reading < 10) — Q9 in _577gap_prod_capture.txt. avg / median per day.
LIVE_EXTRA = {8.0: (22.8, 18.5), 8.5: (14.0, 12.0), 9.0: (7.7, 6.0), 9.5: (3.3, 2.5)}
LIVE_POOL10 = (30.1, 26.0)  # today's >=10 pool, same era, avg/median per day

SESSIONS = 92  # distinct sessions with >=1 tier-A 8%+ gap day in the cohort window


def load():
    rows = []
    for ln in PSV.read_text().splitlines():
        p = ln.split("|")
        if len(p) < 11:
            continue
        t, dt = p[0], p[1]
        gap, o, hi, pc = float(p[2]), float(p[3]), float(p[4]), float(p[5])
        winner = p[10] == "1"
        rows.append(dict(t=t, dt=dt, gap=gap, hi=hi, pc=pc, winner=winner,
                         r10=(t, dt) in R10 and (t, dt) not in ARTIFACT,
                         r1=R10.get((t, dt), 0.0) if (t, dt) not in ARTIFACT else 0.0,
                         crossed=hi >= 1.10 * pc))
    return rows


def main():
    rows = load()
    assert len(rows) == 749, len(rows)
    assert sum(r["winner"] for r in rows) == 78
    band = [r for r in rows if 8.0 <= r["gap"] < 10.0]
    assert len(band) == 252 and sum(r["winner"] for r in band) == 25

    pool10 = [r for r in rows if r["gap"] >= 10.0]
    base_w = sum(r["winner"] for r in pool10)
    base_r10 = sum(r["r10"] for r in pool10)
    base_rsum = sum(r["r1"] for r in pool10)

    print("=" * 100)
    print("FLOOR SWEEP — tier-A cohort 2026-03-01..07-15 (749 gap days / 92 sessions), gap basis = session open")
    print("=" * 100)
    hdr = (f"{'floor':>6} {'pool':>5} {'8xADR-w':>8} {'dens':>6} {'>=10R':>6} {'r10dens':>8} "
           f"{'+w':>4} {'+10R':>5} {'+lose':>6} {'+cand/d(cohort)':>16} {'+cand/d(live avg/med)':>22} {'R-sum10R':>9}")
    print(hdr)
    for f in (10.0, 9.5, 9.0, 8.5, 8.0):
        pool = [r for r in rows if r["gap"] >= f]
        add = [r for r in rows if f <= r["gap"] < 10.0]
        w = sum(r["winner"] for r in pool)
        r10n = sum(r["r10"] for r in pool)
        rsum = sum(r["r1"] for r in pool)
        aw = sum(r["winner"] for r in add)
        ar10 = sum(r["r10"] for r in add)
        alose = len(add) - aw
        live = LIVE_EXTRA.get(f)
        livestr = f"+{live[0]:.1f} / +{live[1]:.1f}" if live else "—"
        print(f"{f:>6.1f} {len(pool):>5} {w:>8} {w/len(pool)*100:>5.1f}% {r10n:>6} {r10n/len(pool)*100:>7.1f}% "
              f"{aw:>4} {ar10:>5} {alose:>6} {'+%.1f' % (len(add)/SESSIONS):>16} {livestr:>22} {rsum:>9.1f}")
    print(f"\n  today's live pool >=10 for scale: {LIVE_POOL10[0]:.1f} avg / {LIVE_POOL10[1]:.0f} median names/day (8.0-era scanner)")

    # marginal-band densities (does the ADDED slice enrich or dilute the slot pool? P4/P5)
    print("\nMARGINAL BAND ONLY (the slice each floor ADDS vs 10.0):")
    print(f"{'band':>10} {'rows':>5} {'8xADR-w':>8} {'dens':>6} {'>=10R':>6} {'r10dens':>8} {'R-sum':>7}")
    for lo in (9.5, 9.0, 8.5, 8.0):
        add = [r for r in rows if lo <= r["gap"] < 10.0]
        aw = sum(r["winner"] for r in add)
        ar10 = sum(r["r10"] for r in add)
        print(f"{('%.1f-10' % lo):>10} {len(add):>5} {aw:>8} {aw/len(add)*100:>5.1f}% {ar10:>6} "
              f"{ar10/len(add)*100:>7.1f}% {sum(r['r1'] for r in add):>7.1f}")
    print(f"{'>=10 pool':>10} {len(pool10):>5} {base_w:>8} {base_w/len(pool10)*100:>5.1f}% {base_r10:>6} "
          f"{base_r10/len(pool10)*100:>7.1f}% {base_rsum:>7.1f}")

    # ex-04-08 robustness (13 of the 26 >=10R live on one macro session)
    print("\nEX-2026-04-08 ROBUSTNESS (the macro-bounce session carries 10 of the 15 band >=10R):")
    rx = [r for r in rows if r["dt"] != "2026-04-08"]
    for lo, hi in ((10.0, 999.0), (8.0, 10.0)):
        seg = [r for r in rx if lo <= r["gap"] < hi]
        w = sum(r["winner"] for r in seg)
        r10n = sum(r["r10"] for r in seg)
        lbl = ">=10 pool" if hi > 100 else "8-10 band"
        print(f"  {lbl}: {len(seg)} rows | 8xADR winners {w} ({w/len(seg)*100:.1f}%) | >=10R {r10n} ({r10n/len(seg)*100:.1f}%)")

    # BAND+TRIGGER (8-10 at open -> WATCH -> trade on 10% cross), any-time-of-day upper bound
    print("\n" + "=" * 100)
    print("BAND+TRIGGER SHAPE — 8-10 at open admitted to WATCH, tradeable only on a 10% cross")
    print("=" * 100)
    crossers = [r for r in band if r["crossed"]]
    cw = sum(r["winner"] for r in crossers)
    cr10 = sum(r["r10"] for r in crossers)
    never = [r for r in band if not r["crossed"]]
    nw10 = [(r["t"], r["dt"], r["gap"]) for r in never if r["r10"]]
    print(f"  any-time-of-day cross (day high >= 1.10 x prior close — the only daily-bar-computable trigger):")
    print(f"    admitted: {len(crossers)} of {len(band)} band days | winners {cw}/25 | non-winners {len(crossers)-cw}/227")
    print(f"    >=10R recovered: {cr10} of 15 | crosser pool density: 8xADR {cw/len(crossers)*100:.1f}%, "
          f">=10R {cr10/len(crossers)*100:.1f}% | +{len(crossers)/SESSIONS:.1f} cand/day")
    print(f"    NEVER crossed 10 all day — unrecoverable by ANY 10%-trigger shape: "
          f"{', '.join('%s %s (%.1f%%)' % x for x in sorted(nw10, key=lambda x: x[2]))}")
    print(f"    R-sum of those four: {sum(r['r1'] for r in never if r['r10']):.1f}R of the band's "
          f"{sum(r['r1'] for r in band if r['r10']):.1f}R")
    print("""
  09:30-09:44-ONLY trigger (the ORB-window variant): NOT measurable for 12 of the 15 —
  zero minute bars persisted for any of them (mi_intraday_bars: 0 rows; never alerted -> never
  captured; Q1 in _577gap_prod_capture.txt). The 3 log-era names ARE verifiable from scan ticks:
  SNOW 05-07 read 10.28 at 09:40 (in-window cross), UMC 05-06 read 10.64 at 09:30, QCOM 04-24
  read 10.27 (tick untimestamped). All 3 were then dropped by top-20 cap (x2) / score<50 (x1) —
  the floor was 8.0 at the time and was NOT the binding gate for any of them.""")


if __name__ == "__main__":
    main()
