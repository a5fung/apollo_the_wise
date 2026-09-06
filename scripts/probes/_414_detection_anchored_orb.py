"""#414 — re-run the out-of-window cohort with the opening range anchored to DETECTION.

WHY THIS EXISTS (operator, 2026-09-06): "we widen window to catch them because it gaps
later but when we check it already through our limit, what doesn't add up". He was right.
`ep_replay.walk_campaign` takes the ORB from the 09:30 bar unless one is supplied, so a
09:50 detection was being priced off a twenty-minute-old level — every later bar opens above
both trigger and limit, and the row books `triggered_above_limit_never_filled`. That test
could only ever fail on the names that moved, i.e. the tail.

This supplies a DETECTION-ANCHORED range instead: the first minute bar at or after the
detection minute becomes the opening range, exactly as the #624 low-cap lane walks "from the
row's OWN tick wall-clock, never a fixed 09:31".

READ-ONLY. Writes nothing, changes no rule-set, touches no live path.
"""
from __future__ import annotations

import sys
from datetime import date, datetime, time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from scripts.ep_replay import (  # noqa: E402
    RULESETS, load_daily, load_minutes, walk_campaign,
)

# (ticker, alert_date, detected ET) — the 29 window:out_of_orb skips over 90 days.
COHORT = [
    ("IDCC", "2026-06-11", "09:51"), ("AKTS", "2026-06-12", "09:55"),
    ("PENG", "2026-07-08", "09:55"), ("IREN", "2026-07-20", "09:51"),
    ("HAS",  "2026-07-21", "09:50"), ("NNE",  "2026-07-27", "09:56"),
    ("TEVA", "2026-07-29", "09:51"), ("LRCX", "2026-07-30", "09:51"),
    ("BLZE", "2026-07-31", "09:56"), ("AMRC", "2026-08-04", "09:45"),
    ("TSAT", "2026-08-04", "09:56"), ("HGTY", "2026-08-05", "09:55"),
    ("ECG",  "2026-08-05", "09:51"), ("CAI",  "2026-08-06", "09:53"),
    ("DCTH", "2026-08-06", "09:56"), ("ONTO", "2026-08-07", "09:52"),
    ("MTW",  "2026-08-07", "09:52"), ("ACHR", "2026-08-10", "09:45"),
    ("NESR", "2026-08-10", "09:45"), ("MRX",  "2026-08-12", "09:55"),
    ("BE",   "2026-08-12", "09:50"), ("CRWV", "2026-08-12", "09:50"),
    ("OMER", "2026-08-13", "09:45"), ("KURA", "2026-08-13", "09:51"),
    ("NMAX", "2026-08-14", "09:50"), ("TWST", "2026-08-19", "09:55"),
    ("UUUU", "2026-08-21", "09:55"), ("VEEV", "2026-08-27", "09:50"),
    ("CHRN", "2026-08-27", "09:50"),
]


def main() -> None:
    minutes, daily = load_minutes(), load_daily()
    rs = RULESETS["era_c_late_window"]
    rows = []
    for tkr, d_s, det_s in COHORT:
        ad = date.fromisoformat(d_s)
        det = time(*map(int, det_s.split(":")))
        bars = minutes.get((tkr, ad), [])
        anchor = next((b for b in bars if b["m"].time() >= det), None)
        if anchor is None:
            rows.append((tkr, d_s, None, "no bar at/after detection", None))
            continue
        # The detection minute IS the opening range — same shape as a 09:30 ORB, one bar.
        res = walk_campaign(ticker=tkr, alert_date=ad, rs=rs, minutes=minutes, daily=daily,
                            submit=anchor["m"].time(),
                            orb_high=anchor["h"], orb_low=anchor["l"])
        rows.append((tkr, d_s, res.get("entered"), res.get("final_reason") or res.get("reason"),
                     res.get("realized_r")))

    print(f"{'ticker':7}{'date':12}{'entered':9}{'R':>9}  outcome")
    got = []
    for tkr, d_s, ent, why, R in rows:
        rr = f"{R:+.2f}R" if isinstance(R, (int, float)) else "—"
        if isinstance(R, (int, float)) and ent:
            got.append(R)
        print(f"{tkr:7}{d_s:12}{str(ent):9}{rr:>9}  {str(why)[:44]}")
    if got:
        import statistics as st
        print(f"\nENTERED + SETTLED  n={len(got)}  sum {sum(got):+.2f}R  "
              f"mean {st.mean(got):+.2f}R  median {st.median(got):+.2f}R")
        print(f"  >=3R {sum(1 for r in got if r >= 3)}   >=5R {sum(1 for r in got if r >= 5)}"
              f"   winners {sum(1 for r in got if r > 0)}/{len(got)}")
    else:
        print("\nno settled entries")


if __name__ == "__main__":
    main()
