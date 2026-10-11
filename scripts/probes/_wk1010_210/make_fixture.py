"""#210 2026-10-10 — turn the captured prod pulls into ONE fixture file for the build card.

Reads q1_read.out (ACN 10-01, PENG 10-07: our stored corpus + TradingView's same-day items)
and q2_anchor.out (BFLY 06-18: our stored corpus) and writes fixture_cases.json. The build
spec in docs/analysis/210_tv_miss_read_2026-10-10.md tells the card to copy this file to
tests/fixtures/ unchanged. Nothing here touches prod; every title and timestamp is real
except (a) the two BFLY TradingView items, whose `published` is SYNTHETIC and labelled so —
TradingView's rolling window rolled past June months ago, so those times cannot be
observed; the titles are the documented ones (docs/methodology/ep_reference_bfly_2026-06-18.md)
— and (b) the ACN_PREVIEW case (review correction 6, 2026-10-10), a CONSTRUCTED variant of
the real ACN row whose one re-dated item is labelled `published_is_synthetic` too.
Expectations are PROVEN by run_fixture_proof.py (its table is pasted into the doc).
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

# ACN_PREVIEW (correction 6) — CONSTRUCTED from ACN's real corpus: the three 06:39-06:45 ET
# Benzinga results wires are REMOVED and the Zacks preview ("ACN Set to Report Q4 Earnings",
# really published 09-29 13:17 UTC) is RE-DATED into the same-day window (10-01 05:00 ET,
# synthetic, labelled). It models "our only same-day earnings item is a preview": the Reuters
# results summary at 09:31 must then read `class` (same class, no proof of the same story),
# NOT `event`. The real ACN case is the CONTROL — the same Reuters item against the real corpus
# (results wires present) must read `event`. Without the control the test would not discriminate.
_RESULTS_WIRE_PREFIXES = ("Accenture Q4 EPS", "Accenture Sees Q1", "Accenture Sees FY2027")
_acn = cases["ACN"]
_preview_title = "ACN Set to Report Q4 Earnings: Here's What Investors Should Know"
cases["ACN_PREVIEW"] = {
    "ticker": "ACN", "alert_date": _acn["alert_date"],
    "our_captured_at": _acn["our_captured_at"],
    "our_corpus": {
        "polygon": [
            ({"title": i["title"], "published": "2026-10-01T09:00:00Z",
              "published_is_synthetic": True,
              "published_note": "re-dated into the same-day window; the real Polygon "
                                "published_utc is 2026-09-29T13:17:00Z"}
             if i["title"] == _preview_title else i)
            for i in _acn["our_corpus"]["polygon"]],
        "alpaca": [i for i in _acn["our_corpus"]["alpaca"]
                   if not i["title"].startswith(_RESULTS_WIRE_PREFIXES)],
        "fmp": [],
    },
    "our_perplexity_present": True,
    "tv_items": _acn["tv_items"],
    "tv_items_note": ("CONSTRUCTED, not a live row: ACN 10-01's real TradingView window and real "
                      "corpus with the three results wires removed and the Zacks preview re-dated "
                      "into the same-day window (synthetic, labelled on the item). Exists to pin "
                      "correction 6: a preview on our side must not absorb the actual results."),
}

# FRAME (spec Part 1, corrected 2026-10-10 review): buckets are over SAME-DAY items only —
# before_grade = published <= our_captured_at · repoll_window = captured_at < published <=
# 10:00:00 ET on alert_date (the scan's last tick / the 10:00 ET unfilled-cancel; the #344 BFLY
# class) · after_cutoff = later. REACH is `oldest item of the WHOLE window <= 16:00 ET on the prior
# TRADING day` (the start of the same-day period) — NOT `<= our_captured_at`, which leaves the
# stretch between 16:00 and the oldest item unseen (correction 2). tv_unseen_minutes_at_period_start
# = ceil(minutes from period start to the oldest item), 0 when the window reaches.
# tv_items_unmatched_seen = the none/class items of the first two buckets, always when a diff is
# possible; tv_items_we_missed (the DoD column) = that list when the window reaches, else NULL.
# must_match_as_held: the TV title must come back `title`, `story`, `event` or `move` — any verdict
# meaning "a story we held" (the hand table's retitle/commentary kinds).
_PENG_PAIRS = [
    ["Penguin Solutions names Stephen Cumming as CFO",
     "Penguin Solutions Appoints Stephen Cumming As CFO, Effective Immediately"],
    ["Needham maintains Buy rating on Penguin Solutions, $85 price target",
     "Needham Maintains Buy on Penguin Solutions, Raises Price Target to $85"],
    ["Penguin Solutions Price Target Raised to $85.00/Share From $75.00 by Stifel",
     "Stifel Maintains Buy on Penguin Solutions, Raises Price Target to $85"],
    ["Penguin Solutions Q4 Earnings Call Highlights",
     "Penguin Solutions Reports Q4 2026 Results: Full Earnings Call Transcript"],
]
expected = {
    "ACN": {"tv_items_before_grade": 0, "tv_items_in_repoll_window": 1, "tv_items_after_cutoff": 24,
            "tv_coverage_reaches_period_start": False, "tv_unseen_minutes_at_period_start": 1052,
            "tv_items_we_missed": None, "tv_items_unmatched_seen": [],
            "seen_verdicts_all_held": True,
            "control_must_match_as_event": [
                "Accenture PLC reports results for the quarter ended August 31 - Earnings Summary",
                "Accenture Q4 EPS $3.29 Beats $3.18 Estimate, Sales $18.700B Beat $18.030B Estimate"],
            "why": "every TV item is after our 07:10 ET capture; oldest window item 09:31:47 ET vs "
                   "period start 09-30 16:00 ET = 1052 unseen minutes -> the DoD column is NULL, "
                   "never a list. The one re-poll item (Reuters results summary, 09:31) is the "
                   "results event we held -> `event`; unmatched_seen is empty."},
    "ACN_PREVIEW": {"tv_items_before_grade": 0, "tv_items_in_repoll_window": 1,
                    "tv_items_after_cutoff": 24,
                    "tv_coverage_reaches_period_start": False,
                    "tv_unseen_minutes_at_period_start": 1052,
                    "tv_items_we_missed": None,
                    "tv_items_unmatched_seen_titles": [
                        "Accenture PLC reports results for the quarter ended August 31 - Earnings Summary"],
                    "tv_items_unmatched_seen_match": "class",
                    "must_match_as_class_not_event": [
                        "Accenture PLC reports results for the quarter ended August 31 - Earnings Summary",
                        _preview_title],
                    "why": "our only same-day earnings item is a PREVIEW, so the actual results on "
                           "TradingView's side are NOT the event we held -> `class`, visible in "
                           "unmatched_seen (loose readout), never absorbed as `event`."},
    "PENG": {"tv_items_before_grade": 17, "tv_items_in_repoll_window": 1, "tv_items_after_cutoff": 7,
             "tv_coverage_reaches_period_start": False, "tv_unseen_minutes_at_period_start": 7,
             "tv_items_we_missed": None, "tv_items_unmatched_seen": [],
             "seen_verdicts_all_held": True,
             "must_match_as_held": _PENG_PAIRS,
             "must_match_as_class_not_story": [
                 ["Rosenblatt maintains Buy rating on Penguin Solutions, $100 price target",
                  "Stifel Maintains Buy on Penguin Solutions, Raises Price Target to $85"],
             ],
             "why": "17 items before our 09:35 ET capture (11 retitles + 6 commentary on stories we "
                    "held, hand-read) and 1 re-poll-window item (Stifel via TradingView's analyst "
                    "feed, 09:43, a retitle of our 09:25 Stifel item): all 18 seen items read as "
                    "held, unmatched_seen is empty. The window's oldest item is 16:07 ET vs period "
                    "start 16:00 -> 7 unseen minutes -> the DoD column is NULL (a LOWER BOUND by "
                    "hand, not a zero the instrument may claim)."},
    "BFLY": {"tv_items_before_grade": 0, "tv_items_in_repoll_window": 1, "tv_items_after_cutoff": 1,
             "tv_coverage_reaches_period_start": True, "tv_unseen_minutes_at_period_start": 0,
             "filler_note": "the 06-16 filler is OUTSIDE the same-day window (06-18, or 06-17 >= "
                            "16:00 ET) so it falls in no bucket; it exists only so the oldest item "
                            "of the window is <= the period start, as a real 25-item window would be",
             "tv_items_we_missed_titles": [
                 "Butterfly Network Provides Commentary on Midjourney Medical's Full Body "
                 "Ultrasound Scanner Announcement"],
             "tv_items_we_missed_bucket": "repoll_window",
             "tv_items_we_missed_match": "none",
             "why": "an unmatched item must survive: the release arrived after our 07:01 grade but "
                    "inside the actionable window (the #344 re-poll class; per "
                    "docs/analysis/missed_ep_bfly_2026-06-18.md our own Alpaca/Benzinga feed carried "
                    "it at 08:12 ET, so this is a re-poll-window item, NOT proof TradingView had a "
                    "story our feeds never carried); our 7 items hold no catalyst-class story, so "
                    "neither class nor move absorbs it. The Stocktwits piece (11:56) is after the "
                    "cutoff -> counted, not missed. The filler item is one we held -> `title`."},
}

json.dump({"generated": "2026-10-10", "source": "scripts/probes/_wk1010_210/{q1_read,q2_anchor}.out",
           "cases": cases, "expected": expected},
          open("fixture_cases.json", "w", encoding="utf-8"), indent=1, ensure_ascii=False)
for k, v in cases.items():
    n_ours = sum(len(v["our_corpus"][s]) for s in ("polygon", "alpaca", "fmp"))
    print(f"{k} {v['alert_date']} captured {v['our_captured_at']} ours={n_ours} tv={len(v['tv_items'])}")
