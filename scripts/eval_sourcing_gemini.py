#!/usr/bin/env python3
"""#186/#188 Gemini-as-SOURCING-channel eval (READ-ONLY; NO DB writes, NO trade state).

Reframed thesis (6/5): the #188 sourcing eval proved RUM was a SOURCING miss, and
graders converge on grounded input — so Gemini's value (if any) is NOT as a 3rd
grade-validator but as an INDEPENDENT sourcing channel with native Google-Search
grounding, to surface the non-8-K catalysts EDGAR can't see. This probes exactly that.

Smoke (6/5): gemini-2.5-flash grounded found RUM's real "$270 million multi-year cloud
services agreement with a third-party cloud provider" in one call — where prod sonar-pro
MISSED and sonar/reasoning-pro CONFABULATED ("Together AI"). Promising but N=1 — this
harness runs the full cohort + measures confabulation, per the RUM keyword-trap lesson.

DISCIPLINE (carried from eval_sourcing_perplexity.py):
  - ALWAYS adjudicate a "FOUND" lead vs the actual filing (collector.get_sec_recent_filings)
    — a keyword match is NOT a find (RUM: cheap tiers keyword-confabulated).
  - The pipeline's documented risk is confident CONFABULATION (perplexity_hallucination_
    keyword_leak, 11 M&A FPs). A channel that always emits a confident specific is MORE
    dangerous, not better — so CONTROL cases (no real catalyst) measure the real cost.
  - Quality-PRIMARY (feedback_model_selection_quality_over_cost): test the STRONGEST
    candidate (gemini-2.5-pro) head-to-head, not just the cheap one.

CAVEAT vs Perplexity: Gemini's Google-Search grounding has NO hard date-window filter
(Perplexity has search_after/before_date_filter). We scope temporally by putting the
event date in the query — a softer control. Flag any answer that clearly pulled
later-than-event info.

DECISION (locked): a channel that FINDS the real catalyst on the hard cases (RUM + the
unknown cohort) AND does NOT confabulate on controls → candidate to add as a parallel
sourcing vote (CHANGE_PROCESS). Else → EDGAR (#187) + sonar-pro stay; Gemini parked.

Run (server, read-only): docker exec apollo-market python scripts/eval_sourcing_gemini.py
Optional: --json /tmp/unknown_cohort.json  (also probe the unknown/coverage-gap cohort)
"""
import argparse
import json
import os
import time

from google import genai
from google.genai import types

# Production sourcing system prompt (collector._PERPLEXITY_SYSTEM_DEFAULT), for parity.
SYSTEM = (
    "You are a financial market analyst. Give direct, specific answers about current "
    "market catalysts. State the SPECIFIC catalyst (named counterparty, dollar value, "
    "date) when one exists. If there is NO clear company-specific catalyst, say so "
    "plainly — do not invent one. Plain text only."
)

# Quality-primary: strongest candidate (pro) head-to-head with the cheap one (flash).
MODELS = ["gemini-2.5-flash", "gemini-2.5-pro"]

# Same cohort as eval_sourcing_perplexity.py (parity for cross-channel comparison).
# (ticker, event_date 'YYYY-MM-DD', kind, must_find_keywords, note)
CASES = [
    ("RUM", "June 4 2026", "REAL",
     ["270", "third-party", "third party", "cloud", "nvidia", "blackwell"],
     "GOLD PROBE: real 8-K = $270M multi-year deal, UNNAMED third-party buys GPU cloud FROM Rumble."),
    ("TTAN", "June 5 2026", "REAL",
     ["earnings", "guidance", "revenue", "servicetitan"],
     "ServiceTitan Q earnings beat + upbeat guidance (8-K)."),
    ("AGX", "June 5 2026", "REAL",
     ["earnings", "argan", "backlog", "revenue", "eps"],
     "Argan strong earnings print (8-K)."),
    ("MRLN", "June 5 2026", "REAL",
     ["design review", "autonomous", "merlin", "c-130"],
     "Weak catalyst: completed a design review. Honest-find = surfaces it w/o inflating."),
    ("PGY", "June 4 2026", "CONTROL",
     ["short squeeze", "short-squeeze", "technical", "no clear", "no specific", "securitization"],
     "No clean EP catalyst (short-squeeze/technical; a routine $600M ABS existed). CONFAB = asserts earnings/M&A/FDA."),
]

DISCLAIMERS = ("no clear", "no specific", "not clearly identified", "no fresh",
               "could not", "cannot", "no single", "no company-specific")


def query_for(ticker, date_str):
    return (f"What caused {ticker} stock to gap up around {date_str}? "
            f"Identify the latest specific company catalyst and its source.")


def call(client, model, ticker, date_str):
    tool = types.Tool(google_search=types.GoogleSearch())
    cfg = types.GenerateContentConfig(
        tools=[tool], system_instruction=SYSTEM, temperature=0.0,
    )
    t0 = time.time()
    r = client.models.generate_content(
        model=model, contents=query_for(ticker, date_str), config=cfg)
    dt = time.time() - t0
    text = (r.text or "").strip()
    # grounding sources (the cited URLs — lets us adjudicate provenance)
    srcs = []
    try:
        gm = r.candidates[0].grounding_metadata
        for ch in (gm.grounding_chunks or []):
            if ch.web and ch.web.uri:
                srcs.append(ch.web.title or ch.web.uri)
    except Exception:
        pass
    um = getattr(r, "usage_metadata", None)
    tok = (getattr(um, "prompt_token_count", "?"), getattr(um, "candidates_token_count", "?"))
    return text, dt, srcs, tok


def score(text, case):
    low = text.lower()
    found = any(k in low for k in case[3])
    disc = any(m in low[:400] for m in DISCLAIMERS)
    if case[2] == "CONTROL":
        confab = any(w in low for w in ("acquisition", "merger", "fda approval",
                                        "definitive agreement to acquire", "earnings beat",
                                        "guidance raise", "buyout"))
        return "CONFAB" if confab else ("vague-ok" if (found or disc) else "vague?")
    return "FOUND" if found else ("MISS(disclaimer)" if disc else "MISS")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--json", default="", help="also probe an unknown_cohort.json feed (ticker/date)")
    args = ap.parse_args()
    client = genai.Client(api_key=os.environ["GEMINI_API_KEY"])

    print("=" * 92)
    print("#186 Gemini grounded-SOURCING eval — does Google-Search grounding FIND the catalyst?")
    print("Quality-primary: gemini-2.5-flash vs gemini-2.5-pro. Read-only. Adjudicate FOUND vs filing.")
    print("=" * 92)
    cost = {"gemini-2.5-flash": "$0.30/$2.50 +search", "gemini-2.5-pro": "$1.25/$10 +search"}
    summary = {m: {"FOUND": 0, "MISS": 0, "CONFAB": 0} for m in MODELS}

    for tk, d, kind, kws, note in CASES:
        print(f"\n{'─'*92}\n{tk}  {d}  [{kind}] — {note}")
        for model in MODELS:
            try:
                text, dt, srcs, tok = call(client, model, tk, d)
                v = score(text, (tk, d, kind, kws, note))
                if v == "FOUND": summary[model]["FOUND"] += 1
                elif v == "CONFAB": summary[model]["CONFAB"] += 1
                elif v.startswith("MISS"): summary[model]["MISS"] += 1
                print(f"  {model:18} {v:16} {dt:5.1f}s  in={tok[0]} out={tok[1]}")
                print(f"      « {text[:300].replace(chr(10),' ')} »")
                if srcs:
                    print(f"      src: {', '.join(srcs[:3])[:160]}")
            except Exception as e:
                print(f"  {model:18} ERROR  {type(e).__name__}: {str(e)[:90]}")

    # optional unknown-cohort probe (flash only — volume)
    if args.json:
        try:
            feed = json.load(open(args.json))
        except Exception as e:
            feed = []
            print(f"\n(could not load {args.json}: {e})")
        if feed:
            print(f"\n{'='*92}\n=== UNKNOWN/coverage-gap cohort probe (gemini-2.5-flash) — N={len(feed)} ===")
            print("Each needs filing-adjudication: did Gemini surface a REAL catalyst the prod pipeline missed?")
            for row in feed[:15]:
                tk, d = row["ticker"], row["date"]
                try:
                    text, dt, srcs, tok = call(client, "gemini-2.5-flash", tk, d)
                    print(f"\n  {tk} {d} (prod: {row.get('catalyst_quality')}/{row.get('catalyst_type')}): "
                          f"{dt:.1f}s")
                    print(f"      « {text[:260].replace(chr(10),' ')} »")
                except Exception as e:
                    print(f"  {tk} {d} ERROR {type(e).__name__}: {str(e)[:70]}")

    print(f"\n{'='*92}\n=== TIER SUMMARY (REAL: FOUND/MISS · CONTROL: CONFAB) ===")
    print(f"{'model':18} {'FOUND':>6} {'MISS':>6} {'CONFAB':>7}   cost $/1M in/out")
    for m in MODELS:
        s = summary[m]
        print(f"{m:18} {s['FOUND']:>6} {s['MISS']:>6} {s['CONFAB']:>7}   {cost[m]}")
    print("\nFOUND = keyword aid; ALWAYS verify the lead vs the actual 8-K (the RUM trap).")
    print("Compare against eval_sourcing_perplexity.py: sonar-pro MISSED RUM; sonar/reasoning-pro CONFABULATED.")


if __name__ == "__main__":
    main()
