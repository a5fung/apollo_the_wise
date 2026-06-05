#!/usr/bin/env python3
"""#188 model-eval, SOURCING slice (READ-ONLY; NO DB writes, NO trade state).

Question: which Perplexity tier best FINDS the real catalyst? The grade-task and
materiality slices both converged -> default Sonnet; the remaining lever is the
INPUT (sourcing). Production uses `sonar-pro` for the catalyst summary
(collector.search_news_perplexity) + base `sonar` for the one-word cross-validation
(ep_detector:429). #187 EDGAR ingestion is the ROBUST fix for 8-K catalysts; this
tests whether a stronger Perplexity tier helps for the NON-8-K / general case.

GROUND-TRUTH PROBE (the gold case): RUM 6/4 — the stored PRODUCTION sonar-pro text
literally says "catalyst is not clearly identified" — it MISSED the real $270M
Rumble/NVIDIA Blackwell GPU-cloud deal (8-K). So we have a known sonar-pro FAILURE.
Do sonar-pro(high) / sonar-reasoning-pro / sonar-deep-research find it?

TIME-CONFOUND CONTROL (advisor 2026-06-05): Perplexity searches LIVE, so a re-run
today isn't the same as the event-day run. We pin each query with
search_after/before_date_filter to the event window [date-2, date+1], so every tier
searches the SAME window regardless of when this is run. (Not perfect — the live
index still changes — but removes the gross recency-window confound.)

SCORING: auto-flag FOUND if any ground-truth keyword appears (case-insensitive);
CONFABULATED on the control if it asserts a specific deal/earnings that didn't happen.
Raw lead (first ~320 chars) printed for human verification — the keyword flag is an
aid, not the verdict.

⚠️ KEYWORD-FOUND IS A TRAP — THE RUM LESSON (2026-06-05, advisor-caught). On the gold
probe, `sonar` and `sonar-reasoning-pro` scored FOUND on nvidia/blackwell/gpu — but
read the leads: they asserted an agreement "with Together AI ... compute as a service"
with NO $270M. The real 8-K (verified via collector.get_sec_recent_filings) is a
multi-year $270M agreement with an UNNAMED third-party customer who buys GPU cloud
capacity FROM Rumble. Wrong counterparty, wrong structure = CONFABULATION that happens
to contain the keywords. Only `sonar-deep-research` surfaced the real "$270 million".
`sonar-pro` (production) honestly MISSED (flagged the negative Pomerantz item) rather
than fabricate — the SAFER failure mode for a pipeline whose documented risk is
`perplexity_hallucination_keyword_leak` (11 M&A FPs from confident confabulation).
=> ALWAYS adjudicate "FOUND" leads against the actual 8-K before ranking tiers.
=> VERDICT (this cohort): do NOT swap sonar-pro; the eval confirms #187 EDGAR is the
   load-bearing sourcing fix. Tier choice is undecidable here (N=1 hard case; needs
   clean no-catalyst controls to measure confabulation rate, which is the real cost).

DECISION RULE (locked):
  - A higher tier reliably FINDS the real catalyst where sonar-pro MISSES (esp. RUM)
    AND doesn't confabulate on the control -> quality edge -> recommend upgrade for
    sourcing (weigh latency/cost; deep-research is minutes + $$).
  - All tiers behave alike (all find / all miss) -> no upgrade; EDGAR (#187) stays the
    8-K fix, sonar-pro stays for the general case.

Run (server, read-only): docker exec apollo-market python scripts/eval_sourcing_perplexity.py
"""
import os
import time

import httpx

# Production system prompt (collector._PERPLEXITY_SYSTEM_DEFAULT), verbatim.
SYSTEM = (
    "You are a financial market analyst. Give direct, specific answers "
    "about current market catalysts. "
    "Never include citation numbers like [1] or [2]. "
    "Never say 'search results show' or 'I cannot find'. "
    "Plain text only — no markdown, no bullets."
)

# Production EP sourcing query (ep_detector.py:1248), verbatim template.
def query_for(ticker: str) -> str:
    return f"What caused {ticker} stock to gap up? Latest catalyst and news."

TIERS = ["sonar", "sonar-pro", "sonar-reasoning-pro", "sonar-deep-research"]

# Disclaimer markers (collector._PERPLEXITY_DISCLAIMER_MARKERS) — a "miss" signal.
DISCLAIMERS = (
    "no recent catalysts found", "no direct catalyst", "no specific news",
    "no direct information", "nearest match", "closest match",
    "i don't have information", "no information about", "not clearly identified",
)

# (ticker, alert_date 'YYYY-MM-DD', kind, must_find_keywords, note)
# kind: REAL = should surface the specific catalyst; CONTROL = no real catalyst,
# should stay vague (confabulation = naming a specific deal/earnings).
CASES = [
    ("RUM", "2026-06-04", "REAL",
     ["nvidia", "blackwell", "gpu", "270", "cloud capacity"],
     "GOLD PROBE: $270M Rumble/NVIDIA Blackwell GPU-cloud deal (8-K). Prod sonar-pro MISSED it."),
    ("TTAN", "2026-06-05", "REAL",
     ["earnings", "guidance", "revenue", "servicetitan"],
     "ServiceTitan Q earnings beat + upbeat guidance (8-K)."),
    ("AGX", "2026-06-05", "REAL",
     ["earnings", "argan", "backlog", "revenue", "power"],
     "Argan strong earnings print (8-K)."),
    ("MRLN", "2026-06-05", "REAL",
     ["design review", "autonomous", "plane", "merlin"],
     "Weak catalyst: completed a design review. Honest-find = surfaces it w/o inflating."),
    ("PGY", "2026-06-04", "CONTROL",
     ["short squeeze", "short-squeeze", "technical"],
     "No clear catalyst (short-squeeze/technical). CONFAB = asserts a specific deal/earnings."),
]


def _date_window(d: str) -> tuple[str, str]:
    """Perplexity wants M/D/YYYY. Window = [date-2, date+1] around the event."""
    from datetime import date, timedelta
    y, m, dd = map(int, d.split("-"))
    ev = date(y, m, dd)
    after = ev - timedelta(days=2)
    before = ev + timedelta(days=1)
    f = lambda x: f"{x.month}/{x.day}/{x.year}"
    return f(after), f(before)


def call(api_key, model, ticker, date_str):
    after, before = _date_window(date_str)
    body = {
        "model": model,
        "messages": [
            {"role": "system", "content": SYSTEM},
            {"role": "user", "content": query_for(ticker)},
        ],
        "search_after_date_filter": after,
        "search_before_date_filter": before,
        "web_search_options": {"search_context_size": "high"},
        "return_citations": False,
    }
    t0 = time.time()
    # deep-research can take minutes
    timeout = 240 if "deep-research" in model else 60
    with httpx.Client(timeout=timeout) as c:
        r = c.post("https://api.perplexity.ai/chat/completions",
                   headers={"Authorization": f"Bearer {api_key}"}, json=body)
        r.raise_for_status()
        j = r.json()
    dt = time.time() - t0
    text = j["choices"][0]["message"]["content"].strip()
    usage = j.get("usage", {})
    return text, dt, usage


def score(text, case):
    low = text.lower()
    found = any(k in low for k in case[3])
    disc = any(m in low[:320] for m in DISCLAIMERS)
    if case[2] == "CONTROL":
        # confab if it asserts a specific REAL-sounding catalyst keyword set
        confab = any(w in low for w in ("acquisition", "merger", "fda approval",
                                        "definitive agreement", "earnings beat", "guidance raise"))
        return "CONFAB" if confab else ("vague-ok" if (found or disc) else "vague?")
    # REAL case
    if found:
        return "FOUND"
    return "MISS(disclaimer)" if disc else "MISS"


def main():
    api_key = os.environ["PERPLEXITY_API_KEY"]
    print("=" * 92)
    print("#188 SOURCING eval — Perplexity tiers: does it FIND the real catalyst?")
    print("Date-pinned to each event window [date-2, date+1]; search_context=high. Read-only.")
    print("=" * 92)
    cost_note = {"sonar": "$1/$1", "sonar-pro": "$3/$15", "sonar-reasoning-pro": "$2/$8",
                 "sonar-deep-research": "$2/$8 +search/reason fees (minutes)"}
    summary = {t: {"FOUND": 0, "MISS": 0, "CONFAB": 0} for t in TIERS}
    for tk, d, kind, kws, note in CASES:
        print(f"\n{'─'*92}\n{tk}  {d}  [{kind}]  — {note}")
        for model in TIERS:
            try:
                text, dt, usage = call(api_key, model, tk, d)
                verdict = score(text, (tk, d, kind, kws, note))
                if verdict == "FOUND":
                    summary[model]["FOUND"] += 1
                elif verdict == "CONFAB":
                    summary[model]["CONFAB"] += 1
                elif verdict.startswith("MISS"):
                    summary[model]["MISS"] += 1
                tok = f"in={usage.get('prompt_tokens','?')} out={usage.get('completion_tokens','?')}"
                print(f"  {model:22} {verdict:16} {dt:5.1f}s  {tok}")
                print(f"      « {text[:320].replace(chr(10),' ')} »")
            except Exception as e:
                print(f"  {model:22} ERROR  {type(e).__name__}: {str(e)[:80]}")

    print(f"\n{'='*92}\n=== TIER SUMMARY (REAL cases: FOUND/MISS; CONTROL: CONFAB count) ===")
    print(f"{'tier':22} {'FOUND':>6} {'MISS':>6} {'CONFAB':>7}   cost $/1M in/out")
    for t in TIERS:
        s = summary[t]
        print(f"{t:22} {s['FOUND']:>6} {s['MISS']:>6} {s['CONFAB']:>7}   {cost_note[t]}")
    print("\nFOUND = surfaced the specific real catalyst (keyword aid; verify lead text).")
    print("RUM is the gold probe — prod sonar-pro MISSED its $270M NVIDIA deal.")


if __name__ == "__main__":
    main()
