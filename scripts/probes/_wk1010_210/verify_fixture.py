"""Check fixture_cases.json's `expected` bucket counts against its own timestamps (spec Part 1).

Buckets are over SAME-DAY items only (tv_news_shadow.is_same_day_item: ET date == alert_date, or
the prior trading day at/after 16:00 ET): before_grade = published <= our_captured_at ·
repoll_window = captured_at < published <= 10:00:00 ET on alert_date · after_cutoff = later.
reaches_grade_time = oldest item of the WHOLE window <= captured_at (that is what
tv_oldest_item_published is), so an out-of-window filler still counts toward reach.
No holidays fall in the fixture dates, so the prior trading day is the previous weekday.
"""
import json
from datetime import datetime, time, timedelta
from zoneinfo import ZoneInfo

ET = ZoneInfo("America/New_York")


def prior_weekday(d):
    p = d - timedelta(days=1)
    while p.weekday() >= 5:
        p -= timedelta(days=1)
    return p


def same_day(t, alert_date):
    d = t.date()
    if d == alert_date:
        return True
    return d == prior_weekday(alert_date) and t.time() >= time(16, 0)


d = json.load(open("fixture_cases.json", encoding="utf-8"))
ok = True
for k, c in d["cases"].items():
    cap = datetime.fromisoformat(c["our_captured_at"])
    ad = datetime.fromisoformat(c["alert_date"]).date()
    cutoff = datetime.combine(ad, time(10, 0), tzinfo=ET)
    ts_all = [datetime.fromtimestamp(it["published"], tz=ET) for it in c["tv_items"]]
    ts = [t for t in ts_all if same_day(t, ad)]
    got = {
        "tv_items_before_grade": sum(t <= cap for t in ts),
        "tv_items_in_repoll_window": sum(cap < t <= cutoff for t in ts),
        "tv_items_after_cutoff": sum(t > cutoff for t in ts),
        "tv_coverage_reaches_grade_time": min(ts_all) <= cap,
    }
    exp = {kk: d["expected"][k][kk] for kk in got}
    same = got == exp
    ok &= same
    print(k, f"same_day={len(ts)}/{len(ts_all)}", got, "MATCH" if same else f"MISMATCH expected {exp}")
print("fixture expected counts consistent:", ok)
raise SystemExit(0 if ok else 1)
