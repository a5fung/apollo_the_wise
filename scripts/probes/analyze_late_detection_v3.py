"""Late-detection analysis on trustworthy timestamps only.

Filters dead_zone_v2.csv to alert_date >= 2026-03-20 (post-migration window).
Pre-2026-03-20 rows have created_at = 2026-03-28 13:26 (migration artifact).

Output: ORB window extension impact based on real EP scanner timestamps.
"""
from __future__ import annotations

import csv
from collections import defaultdict
from datetime import date

CUTOFF_DATE = date(2026, 3, 20)


def bucket(et_min: int) -> str:
    if et_min < 7 * 60:
        return "pre-7am (suspect)"
    if et_min < 9 * 60 + 30:
        return "7:00-9:29 (pre-open)"
    if et_min < 9 * 60 + 45:
        return "9:30-9:44 (in-window)"
    if et_min < 10 * 60:
        return "9:45-9:59"
    if et_min < 10 * 60 + 30:
        return "10:00-10:29"
    if et_min < 11 * 60:
        return "10:30-10:59"
    if et_min < 12 * 60:
        return "11:00-11:59"
    return "12:00+"


def main() -> None:
    with open("/tmp/dead_zone_v2.csv") as f:
        rows = list(csv.DictReader(f))

    rows = [r for r in rows if date.fromisoformat(r["alert_date"]) >= CUTOFF_DATE]
    print(f"Rows after 2026-03-20 cutoff: {len(rows)}")

    # Dedup HIGH_missed by (ticker, date), keep MIN et_min
    keyed: dict[tuple, dict] = {}
    mechs: dict[tuple, set] = defaultdict(set)
    for r in rows:
        if r["cohort"] != "HIGH_missed" or not r["et_alert_minute"]:
            continue
        key = (r["ticker"], r["alert_date"])
        em = int(r["et_alert_minute"])
        mechs[key].add(r["mechanism"])
        prev = keyed.get(key)
        if prev is None or em < int(prev["et_alert_minute"]):
            keyed[key] = r

    print(f"\nUnique HIGH_missed (ticker, date): {len(keyed)}")

    # Mechanism breakdown
    by_mech: dict[str, list[dict]] = defaultdict(list)
    for key, r in keyed.items():
        m = r["mechanism"]
        for special in mechs[key]:
            if special.startswith("skip:no ORB bar"):
                m = "bar_fetch_fail"
                break
        by_mech[m].append(r)

    print("\n=== Mechanism breakdown (unique, post-2026-03-20) ===")
    print(f"{'mechanism':<50} {'n':>4} {'pos':>4} {'pos%':>6}")
    for m in sorted(by_mech.keys()):
        sub = by_mech[m]
        pos = sum(1 for r in sub if r["label"] == "positive")
        print(f"{m[:50]:<50} {len(sub):>4} {pos:>4} {(pos/len(sub)*100):>5.1f}%")

    # late_detection earliest-minute distribution
    late = [r for r in keyed.values() if r["mechanism"] == "late_detection"]
    print(f"\n=== late_detection by EARLIEST minute (n={len(late)}) ===")
    by_bucket: dict[str, list[dict]] = defaultdict(list)
    for r in late:
        by_bucket[bucket(int(r["et_alert_minute"]))].append(r)

    bucket_order = [
        "9:30-9:44 (in-window)", "9:45-9:59", "10:00-10:29", "10:30-10:59",
        "11:00-11:59", "12:00+", "7:00-9:29 (pre-open)", "pre-7am (suspect)",
    ]
    print(f"{'bucket':<25} {'n':>4} {'pos':>4} {'pos%':>6} {'med_fwd':>8}")
    for b in bucket_order:
        sub = by_bucket.get(b, [])
        if not sub:
            continue
        pos = [r for r in sub if r["label"] == "positive"]
        fwds = sorted(float(r["fwd_5d_pct"]) for r in pos) if pos else []
        med_fwd = f"{fwds[len(fwds)//2]:.1f}%" if fwds else "-"
        print(f"{b:<25} {len(sub):>4} {len(pos):>4} {(len(pos)/len(sub)*100):>5.1f}% {med_fwd:>8}")

    # ORB extension sweep
    print("\n=== ORB window extension (UNIQUE, post-cutoff) ===")
    total_pos_late = sum(1 for r in late if r["label"] == "positive")
    print(f"  Total late_detection: {len(late)}, positives: {total_pos_late}")
    for cutoff_min, label in [(9*60+50, "9:50"), (9*60+55, "9:55"), (10*60, "10:00"), (10*60+30, "10:30"), (11*60, "11:00")]:
        captured = [r for r in late if 9*60+45 <= int(r["et_alert_minute"]) < cutoff_min]
        cap_pos = [r for r in captured if r["label"] == "positive"]
        prec = (len(cap_pos)/len(captured)*100) if captured else 0
        rec = (len(cap_pos)/total_pos_late*100) if total_pos_late else 0
        print(f"  Extend to {label}: captures {len(captured):>3} tuples, "
              f"{len(cap_pos):>2}/{total_pos_late} positives  prec={prec:>4.1f}%  recall={rec:>4.1f}%")

    # All unique missed positives in trustworthy window
    pos_unique = [r for r in keyed.values() if r["label"] == "positive"]
    pos_unique.sort(key=lambda r: -float(r["fwd_5d_pct"]))
    print(f"\n=== ALL UNIQUE missed positives post-2026-03-20 ===")
    print(f"Total: {len(pos_unique)}")
    print(f"{'mechanism':<25} {'ticker':<6} {'date':<12} {'et_min':>6} {'time':<6} {'fwd':>7} {'gap':>6}")
    for r in pos_unique:
        m = r["mechanism"]
        for special in mechs[(r["ticker"], r["alert_date"])]:
            if special.startswith("skip:no ORB bar"):
                m = "bar_fetch_fail"
                break
        em = int(r["et_alert_minute"])
        time_str = f"{em//60:02d}:{em%60:02d}"
        print(f"{m[:25]:<25} {r['ticker']:<6} {r['alert_date']} {em:>6} {time_str:<6} "
              f"{float(r['fwd_5d_pct']):>5.1f}% {float(r['gap_pct']):>5.1f}%")

    # Sanity: HIGH_entered (control) with successful trade
    entered = [r for r in rows if r["cohort"] == "HIGH_entered"]
    print(f"\n=== HIGH_entered (control, post-cutoff) ===")
    print(f"Total entered: {len(entered)}")
    for r in entered:
        em = int(r["et_alert_minute"]) if r["et_alert_minute"] else 0
        time_str = f"{em//60:02d}:{em%60:02d}"
        print(f"  {r['ticker']:<6} {r['alert_date']} {time_str} fwd={r['fwd_5d_pct']}% label={r['label']}")


if __name__ == "__main__":
    main()
