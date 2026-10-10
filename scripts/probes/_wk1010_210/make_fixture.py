"""#210 2026-10-10 — turn the captured prod pulls into ONE fixture file for the build card.

Reads q1_read.out (ACN 10-01, PENG 10-07: our stored corpus + TradingView's same-day items)
and q2_anchor.out (BFLY 06-18: our stored corpus) and writes fixture_cases.json. The build
spec in docs/analysis/210_tv_miss_read_2026-10-10.md tells the card to copy this file to
tests/fixtures/ unchanged. Nothing here touches prod; every title and timestamp is real
except the two BFLY TradingView items, whose `published` is SYNTHETIC and labelled so —
TradingView's rolling window rolled past June months ago, so those times cannot be
observed; the titles are the documented ones (docs/methodology/ep_reference_bfly_2026-06-18.md).
"""
from __future__ import annotations

import json
import sys
from datetime import datetime
from zoneinfo import ZoneInfo

ET = ZoneInfo("America/New_York")


def section(text: str, start: str, end: str) -> list[str]:
    lines = text.splitlines()
    i = next(k for k, l in enumerate(lines) if l.startswith(start))
    j = next(k for k, l in enumerate(lines) if l.startswith(end) and k > i)
    return lines[i + 1:j]


def rows(lines: list[str], ncols: int) -> list[list[str]]:
    out = []
    for l in lines:
        if not l or l.startswith("(") or l.startswith("###"):
            continue
        cells = l.split("\t")
        if len(cells) == ncols:
            out.append(cells)
    return out[1:]  # drop header


def corpus_from(cells: list[str], idx_polygon: int, idx_alpaca: int, idx_fmp: int) -> dict:
    def load(s):
        return json.loads(s) if s and s != "null" else []
    return {
        "polygon": [{"title": i.get("title"), "published": i.get("published_utc")}
                    for i in load(cells[idx_polygon])],
        "alpaca": [{"title": i.get("title"), "published": i.get("created_at")}
                   for i in load(cells[idx_alpaca])],
        "fmp": [{"title": i.get("title"), "published": None}  # yfinance items carry no date
                for i in load(cells[idx_fmp])],
    }


def et_iso(local: str) -> str:
    return datetime.fromisoformat(local).replace(tzinfo=ET).isoformat()


q1 = open("q1_read.out", encoding="utf-8").read()
q2 = open("q2_anchor.out", encoding="utf-8").read()

cases: dict = {}

# Q3: ticker, alert_date, extracted_et, extraction_quality, polygon, alpaca, fmp, pplx
for c in rows(section(q1, "### Q3", "### Q4"), 8):
    cases[c[0]] = {
        "ticker": c[0], "alert_date": c[1],
        "our_captured_at": et_iso(c[2]),
        "our_corpus": corpus_from(c, 4, 5, 6),
        "our_perplexity_present": bool(c[7].strip()),
    }
# Q4: ticker, alert_date, missed(json)
for c in rows(section(q1, "### Q4", "### Q5"), 3):
    cases[c[0]]["tv_items"] = json.loads(c[2])
    cases[c[0]]["tv_items_note"] = (
        "the 25 same-day items the LIVE shadow recorded as tv_items_we_missed (real titles, "
        "providers and unix `published`); tv_item_count was 25 so this is the whole window")

# BFLY 06-18 corpus (q2 A2; its pplx column spans lines, so split on the first 7 tabs)
a2 = section(q2, "### A2", "### A3")
bfly_line = next(l for l in a2 if l.startswith("BFLY\t"))
c = bfly_line.split("\t", 6)
cases["BFLY"] = {
    "ticker": "BFLY", "alert_date": c[1],
    "our_captured_at": et_iso(c[2]),
    "our_corpus": corpus_from(c, 3, 4, 5),
    "our_perplexity_present": True,
    "tv_items": [
        # Filler so the synthetic window "reaches" our 07:01 capture the way a real 25-item
        # window would: a REAL title we also held (Polygon, publisher Benzinga, 06-16 13:11 UTC)
        # — it must match as title/story and must not appear in the missed list.
        {"title": "16 Million People, One Underserved Disease: The AI Imaging Push to Close the "
                  "Congenital Heart Gap",
         "provider": "benzinga",
         "published": int(datetime(2026, 6, 16, 9, 11, tzinfo=ET).timestamp()),
         "published_is_synthetic": True,
         "published_note": "placed window filler; the real Polygon published_utc is 2026-06-16T13:11Z"},
        {"title": "Butterfly Network Provides Commentary on Midjourney Medical's Full Body "
                  "Ultrasound Scanner Announcement",
         "provider": "business_wire",
         "published": int(datetime(2026, 6, 18, 8, 5, tzinfo=ET).timestamp()),
         "published_is_synthetic": True},
        {"title": "BFLY Stock Hits Four-Year High — What Is Butterfly Network's Connection "
                  "With AI Startup Midjourney?",
         "provider": "stocktwits",
         "published": int(datetime(2026, 6, 18, 11, 56, tzinfo=ET).timestamp()),
         "published_is_synthetic": False,
         "published_note": "11:56 ET is the documented Stocktwits timestamp (08:56 PDT)"},
    ],
    "tv_items_note": ("NOT a live capture — the window rolled past June. Titles are the two "
                      "documented TradingView-carried pieces; the Business Wire time is a "
                      "placed assumption (premarket), the Stocktwits time is documented."),
}

# Buckets (spec Part 1): before_grade = published <= our_captured_at · repoll_window =
# captured_at < published <= 10:00:00 ET on alert_date (the last tick the scan could still act;
# the #344 BFLY class) · after_cutoff = later. tv_items_we_missed is NULL unless the oldest
# TradingView item is <= our_captured_at (the window reaches our grade time); otherwise it is the
# unmatched items of the first two buckets, each labelled with its bucket and class.
expected = {
    "ACN": {"tv_items_before_grade": 0, "tv_items_in_repoll_window": 1, "tv_items_after_cutoff": 24,
            "tv_coverage_reaches_grade_time": False, "tv_items_we_missed": None,
            "why": "every TV item is after our 07:10 ET capture; oldest window item 09:31 ET, so "
                   "the window cannot speak to grade time -> NULL, never a list"},
    "PENG": {"tv_items_before_grade": 17, "tv_items_in_repoll_window": 1, "tv_items_after_cutoff": 7,
             "tv_coverage_reaches_grade_time": True, "tv_items_we_missed": [],
             "must_match_as_story": [
                 ["Penguin Solutions names Stephen Cumming as CFO",
                  "Penguin Solutions Appoints Stephen Cumming As CFO, Effective Immediately"],
                 ["Needham maintains Buy rating on Penguin Solutions, $85 price target",
                  "Needham Maintains Buy on Penguin Solutions, Raises Price Target to $85"],
                 ["Penguin Solutions Price Target Raised to $85.00/Share From $75.00 by Stifel",
                  "Stifel Maintains Buy on Penguin Solutions, Raises Price Target to $85"],
                 ["Penguin Solutions Q4 Earnings Call Highlights",
                  "Penguin Solutions Reports Q4 2026 Results: Full Earnings Call Transcript"],
             ],
             "must_match_as_class_not_story": [
                 ["Rosenblatt maintains Buy rating on Penguin Solutions, $100 price target",
                  "Stifel Maintains Buy on Penguin Solutions, Raises Price Target to $85"],
             ],
             "why": "17 items before our 09:35 ET capture: 11 retitles + 6 commentary on "
                    "stories we held (hand-read); the one re-poll-window item (Stifel via "
                    "TradingView's analyst feed, 09:43) is a retitle of our 09:25 Stifel item; "
                    "0 stories we lacked"},
    "BFLY": {"tv_items_before_grade": 0, "tv_items_in_repoll_window": 1, "tv_items_after_cutoff": 1,
             "tv_coverage_reaches_grade_time": True,
             "filler_note": "the 06-16 filler is OUTSIDE the same-day window (06-18, or 06-17 >= "
                            "16:00 ET) so it falls in no bucket; it exists only so the oldest item "
                            "of the window is <= our capture, as a real 25-item window would be",
             "tv_items_we_missed_titles": [
                 "Butterfly Network Provides Commentary on Midjourney Medical's Full Body "
                 "Ultrasound Scanner Announcement"],
             "tv_items_we_missed_bucket": "repoll_window",
             "why": "a true miss must survive: the release arrived after our 07:01 grade but inside "
                    "the actionable window (the #344 re-poll class); our 7 items hold no "
                    "catalyst-class story, so neither class nor move absorbs it. The Stocktwits "
                    "piece (11:56) is after the cutoff -> counted, not missed. The filler item is "
                    "one we held -> matched as title."},
}

json.dump({"generated": "2026-10-10", "source": "scripts/probes/_wk1010_210/{q1_read,q2_anchor}.out",
           "cases": cases, "expected": expected},
          open("fixture_cases.json", "w", encoding="utf-8"), indent=1, ensure_ascii=False)
for k, v in cases.items():
    n_ours = sum(len(v["our_corpus"][s]) for s in ("polygon", "alpaca", "fmp"))
    print(f"{k} {v['alert_date']} captured {v['our_captured_at']} ours={n_ours} tv={len(v['tv_items'])}")
