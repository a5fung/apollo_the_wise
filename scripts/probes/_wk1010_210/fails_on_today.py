"""#210 2026-10-10 (review fix) — shows, on TODAY's code (branch base a2e84b4a), the exact failure
each new test in the build card hits, so "tests that fail on today's code" is a captured fact
and not a promise. Run from the repo root: python3 scripts/probes/_wk1010_210/fails_on_today.py
> scripts/probes/_wk1010_210/fails_on_today.out. $0, no network, no DB.
"""
from __future__ import annotations

import os
import sys
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

sys.path.insert(0, os.getcwd())
ET = ZoneInfo("America/New_York")

import agents.market_intelligence.db as db  # noqa: E402
import agents.market_intelligence.tv_news_shadow as s  # noqa: E402
from shared.dates import last_trading_day  # noqa: E402

print("1) the story matcher is not importable:")
try:
    from agents.market_intelligence.tv_news_shadow import match_tv_item  # noqa: F401
    print("   importable (unexpected)")
except ImportError as e:
    print("   ImportError:", e)

print("2) the frame columns do not exist on build_shadow_row's row (ACN-shaped input):")
alert = {"ticker": "ACN", "alert_date": date(2026, 10, 1), "catalyst_quality": "routine",
         "has_direct_source": True, "source_class_count": 5}
corpus = {"raw_polygon_news_json": [],
          "raw_alpaca_news_json": [{"title": "Accenture Q4 EPS $3.29 Beats $3.18 Estimate"}],
          "raw_fmp_news_json": [], "raw_perplexity_text": "x"}
payload = {"items": [{"id": 1, "provider": "reuters",
                      "title": "Accenture PLC reports results for the quarter ended August 31 - Earnings Summary",
                      "published": int(datetime(2026, 10, 1, 9, 31, 47, tzinfo=ET).timestamp())}]}
row = s.build_shadow_row(alert, corpus, "XNYS", "NYSE:ACN", None, (payload, None))
for col in ("our_captured_at", "tv_coverage_reaches_period_start", "tv_unseen_minutes_at_period_start",
            "tv_items_before_grade", "tv_items_in_repoll_window", "tv_items_after_cutoff",
            "tv_match_summary", "tv_items_unmatched_seen"):
    try:
        row[col]
        print(f"   {col}: present (unexpected)")
    except KeyError:
        print(f"   KeyError: {col}")
print("   today's tv_coverage_reaches_alert_date =", row["tv_coverage_reaches_alert_date"],
      "<- a 09:31 oldest item on the alert DATE passes the date-granular guard")
print("   today's tv_items_we_missed =", [i["title"][:44] for i in row["tv_items_we_missed"]],
      "<- a list where the corrected rule says NULL (window oldest 09:31 > period start 16:00)")

print("3) the period start is not holiday-aware:")
print("   last_trading_day(2026-09-08 minus 1 day) =", last_trading_day(date(2026, 9, 8) - timedelta(days=1)),
      "<- Labor Day; the prior NYSE trading day is 2026-09-04")
try:
    from agents.market_intelligence.tv_news_shadow import prior_trading_day_holiday_aware  # noqa: F401
    print("   importable (unexpected)")
except ImportError as e:
    print("   ImportError:", e)

print("4) the population and corpus functions do not exist:")
for fn in ("get_tv_shadow_population", "get_grade_corpus", "write_grade_corpus"):
    print(f"   db.{fn}:", "present (unexpected)" if hasattr(db, fn) else "absent (AttributeError)")
print("   db.get_no_catalyst_alert_population (to be replaced):", hasattr(db, "get_no_catalyst_alert_population"))

print("5) the job slot is 20:45 ET:")
src = open("agents/market_intelligence/scheduler.py", encoding="utf-8").read()
i = src.index('id="tv_news_shadow"')
print("   ", src[src.rfind("CronTrigger(", 0, i):src.index(")", src.rfind("CronTrigger(", 0, i)) + 1])
