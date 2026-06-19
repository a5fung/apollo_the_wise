"""Late-detection analysis dedup'd by (ticker, alert_date).

v1 anomaly (2026-04-30): 168 rows in 13:00-13:59 ET bucket. Caused by EP
scanner re-firing every 5 min on the same setup. Each scan creates a new
mi_ep_alerts row. Need unique (ticker, date) to count real misses.

Also computes MIN(et_alert_minute) per (ticker, date) — earliest time the
EP first appeared. That's the time the ORB window decision should use.
"""
from __future__ import annotations

import csv
from collections import defaultdict


def bucket(et_min: int) -> str:
    if et_min < 9 * 60 + 30:
        return "pre-open"
    if et_min < 9 * 60 + 45:
        return "9:30-9:44"
    if et_min < 10 * 60:
        return "9:45-9:59"
    if et_min < 10 * 60 + 30:
        return "10:00-10:29"
    if et_min < 11 * 60:
        return "10:30-10:59"
    if et_min < 12 * 60:
        return "11:00-11:59"
    if et_min < 13 * 60:
        return "12:00-12:59"
    return "13:00+"


def main() -> None:
    with open("/tmp/dead_zone_v2.csv") as f:
        rows = list(csv.DictReader(f))

    # Group by (ticker, date) — keep MIN et_min, and union mechanisms across cycles
    keyed: dict[tuple, dict] = {}
    mechs: dict[tuple, set] = defaultdict(set)
    for r in rows:
        if r["cohort"] != "HIGH_missed":
            continue
        if not r["et_alert_minute"]:
            continue
        key = (r["ticker"], r["alert_date"])
        em = int(r["et_alert_minute"])
        mechs[key].add(r["mechanism"])
        prev = keyed.get(key)
        if prev is None or em < int(prev["et_alert_minute"]):
            keyed[key] = r

    print(f"HIGH_missed unique (ticker, date) tuples: {len(keyed)}")

    # Mechanism breakdown after dedup (using MIN-time row's mechanism)
    by_mech_unique: dict[str, list[dict]] = defaultdict(list)
    for key, r in keyed.items():
        # Prefer non-late_detection mechanism if any cycle had one (e.g. bar_fetch fail)
        ms = mechs[key]
        m = r["mechanism"]
        for special in ms:
            if special.startswith("skip:no ORB bar"):
                m = special
                break
        by_mech_unique[m].append(r)

    print("\n=== UNIQUE (ticker, date) HIGH_missed by mechanism ===")
    print(f"{'mechanism':<50} {'n':>4} {'pos':>4} {'pos%':>6}")
    for m in sorted(by_mech_unique.keys()):
        sub = by_mech_unique[m]
        pos = sum(1 for r in sub if r["label"] == "positive")
        print(f"{m[:50]:<50} {len(sub):>4} {pos:>4} {(pos/len(sub)*100):>5.1f}%")

    # Late detection — bucket by EARLIEST et_alert_minute per (ticker, date)
    late_unique = [r for r in keyed.values() if r["mechanism"] == "late_detection"]
    print(f"\n=== UNIQUE late_detection by EARLIEST et_alert_minute ===")
    print(f"  Total unique: {len(late_unique)}")

    by_bucket: dict[str, list[dict]] = defaultdict(list)
    for r in late_unique:
        by_bucket[bucket(int(r["et_alert_minute"]))].append(r)

    bucket_order = [
        "9:30-9:44", "9:45-9:59", "10:00-10:29", "10:30-10:59",
        "11:00-11:59", "12:00-12:59", "13:00+", "pre-open",
    ]
    print(f"\n{'bucket':<14} {'n':>4} {'pos':>4} {'pos%':>6} {'med_fwd':>8}")
    for b in bucket_order:
        sub = by_bucket.get(b, [])
        if not sub:
            continue
        pos = [r for r in sub if r["label"] == "positive"]
        fwds = sorted(float(r["fwd_5d_pct"]) for r in pos) if pos else []
        med_fwd = f"{fwds[len(fwds)//2]:.1f}%" if fwds else "-"
        print(f"{b:<14} {len(sub):>4} {len(pos):>4} {(len(pos)/len(sub)*100):>5.1f}% {med_fwd:>8}")

    print("\n=== ORB window extension impact (UNIQUE) ===")
    for cutoff_min, label in [(9*60+55, "9:55"), (10*60, "10:00"), (10*60+30, "10:30")]:
        captured = [r for r in late_unique if 9*60+45 <= int(r["et_alert_minute"]) < cutoff_min]
        cap_pos = [r for r in captured if r["label"] == "positive"]
        total_pos_late = sum(1 for r in late_unique if r["label"] == "positive")
        print(f"  Extend to {label}: captures {len(captured)}/{len(late_unique)} late tuples, "
              f"{len(cap_pos)}/{total_pos_late} positives "
              f"(prec {(len(cap_pos)/len(captured)*100) if captured else 0:.1f}%)")

    # All unique missed positives — full list with earliest minute
    print("\n=== ALL UNIQUE missed positives (any mechanism) ===")
    pos_unique = [r for r in keyed.values() if r["label"] == "positive"]
    pos_unique.sort(key=lambda r: -float(r["fwd_5d_pct"]))
    print(f"Total: {len(pos_unique)}")
    print(f"{'mechanism':<25} {'ticker':<6} {'date':<12} {'et_min':>6} {'fwd':>7} {'gap':>6}")
    for r in pos_unique[:30]:
        m = r["mechanism"]
        for special in mechs[(r["ticker"], r["alert_date"])]:
            if special.startswith("skip:no ORB bar"):
                m = "bar_fetch_fail"
                break
        print(f"{m[:25]:<25} {r['ticker']:<6} {r['alert_date']} {r['et_alert_minute']:>6} "
              f"{float(r['fwd_5d_pct']):>5.1f}% {float(r['gap_pct']):>5.1f}%")


if __name__ == "__main__":
    main()
