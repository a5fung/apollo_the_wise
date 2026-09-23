"""Slice HIGH_missed::late_detection by et_alert_minute bucket.

Question: are missed-HIGH alerts mostly clustered at 9:45-9:59 (ORB window
extension would capture them) or scattered into mid-day (different problem)?
"""
from __future__ import annotations

import csv
from collections import defaultdict


def bucket(et_min: int) -> str:
    if et_min < 9 * 60 + 30:
        return "pre-open"
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
    if et_min < 13 * 60:
        return "12:00-12:59"
    if et_min < 14 * 60:
        return "13:00-13:59"
    if et_min < 15 * 60:
        return "14:00-14:59"
    return "15:00+"


def main() -> None:
    with open("/tmp/dead_zone_v2.csv") as f:
        rows = list(csv.DictReader(f))

    late = [r for r in rows if r["mechanism"] == "late_detection" and r["et_alert_minute"]]
    print(f"late_detection rows with et_alert_minute: {len(late)}")

    by_bucket: dict[str, list[dict]] = defaultdict(list)
    for r in late:
        by_bucket[bucket(int(r["et_alert_minute"]))].append(r)

    bucket_order = [
        "9:30-9:44 (in-window)", "9:45-9:59", "10:00-10:29", "10:30-10:59",
        "11:00-11:59", "12:00-12:59", "13:00-13:59", "14:00-14:59", "15:00+", "pre-open",
    ]

    print(f"\n{'bucket':<25} {'n':>4} {'pos':>4} {'pos%':>6} {'med_fwd':>8} {'med_rvol14':>10}")
    cum_n = 0
    cum_pos = 0
    for b in bucket_order:
        sub = by_bucket.get(b, [])
        if not sub:
            continue
        pos = [r for r in sub if r["label"] == "positive"]
        cum_n += len(sub)
        cum_pos += len(pos)
        fwds = sorted(float(r["fwd_5d_pct"]) for r in pos) if pos else []
        med_fwd = f"{fwds[len(fwds)//2]:.1f}%" if fwds else "-"
        rvols = sorted(float(r["rvol_at_14"]) for r in sub if r["rvol_at_14"])
        med_rv = f"{rvols[len(rvols)//2]:.2f}" if rvols else "-"
        print(f"{b:<25} {len(sub):>4} {len(pos):>4} {(len(pos)/len(sub)*100):>5.1f}% {med_fwd:>8} {med_rv:>10}")

    print(f"\nCumulative: {cum_n} rows, {cum_pos} positives")

    # ORB window extension impact
    print("\n=== If we extend ORB window 9:45 → 9:55 ===")
    captured = [r for r in late if 9*60+45 <= int(r["et_alert_minute"]) < 9*60+55]
    cap_pos = [r for r in captured if r["label"] == "positive"]
    print(f"  Rows captured: {len(captured)} ({len(captured)/len(late)*100:.1f}% of late)")
    print(f"  Positives captured: {len(cap_pos)} ({len(cap_pos)/29*100:.1f}% of 29 missed winners)")

    print("\n=== If we extend ORB window 9:45 → 10:00 ===")
    captured = [r for r in late if 9*60+45 <= int(r["et_alert_minute"]) < 10*60]
    cap_pos = [r for r in captured if r["label"] == "positive"]
    print(f"  Rows captured: {len(captured)} ({len(captured)/len(late)*100:.1f}% of late)")
    print(f"  Positives captured: {len(cap_pos)} ({len(cap_pos)/29*100:.1f}% of 29 missed winners)")

    # Show all 9:45-9:59 misses
    print("\n=== All 9:45-9:59 misses ===")
    win = sorted(by_bucket.get("9:45-9:59", []), key=lambda r: -float(r["fwd_5d_pct"]))
    print(f"{'ticker':<6} {'date':<12} {'et_min':>6} {'fwd':>7} {'rvol14':>8} {'gap':>6} {'label':<10}")
    for r in win:
        rv = f"{float(r['rvol_at_14']):.2f}" if r["rvol_at_14"] else "-"
        print(f"{r['ticker']:<6} {r['alert_date']} {r['et_alert_minute']:>6} "
              f"{float(r['fwd_5d_pct']):>5.1f}% {rv:>8} {float(r['gap_pct']):>5.1f}% {r['label']:<10}")

    # Bar-fetch bug spotlight
    print("\n=== Bar-fetch failure cohort (13 rows, all winners) ===")
    bf = [r for r in rows if r["mechanism"].startswith("skip:no ORB bar")]
    print(f"{'ticker':<6} {'date':<12} {'et_min':>6} {'fwd':>7} {'gap':>6}")
    for r in sorted(bf, key=lambda r: -float(r["fwd_5d_pct"])):
        print(f"{r['ticker']:<6} {r['alert_date']} {r['et_alert_minute']:>6} "
              f"{float(r['fwd_5d_pct']):>5.1f}% {float(r['gap_pct']):>5.1f}%")


if __name__ == "__main__":
    main()
