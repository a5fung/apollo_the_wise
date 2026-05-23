"""Replay #88 M&A filter fix against 13 historical polygon_news cases.

For each (ticker, expected_label) pair, fetch the matching article via
Polygon, apply new polygon_news_has_mna_headline logic, print decision +
expected vs actual.

Pre-ship gate per advisor 2026-05-23 + sample_size_discipline:
  - 2 of 2 TPs MUST be preserved (D, EL)
  - ≥5 of 7 verified FPs MUST be blocked
  - Any TP regression → DO NOT ship

Run: docker exec apollo-market python -m scripts._replay_88_mna_filter_fix
"""
import asyncio
from datetime import date


# Historical cases from 90d mi_audit_log polygon_news mna_filter_fired walk
# (2026-05-22 classification, verified 2026-05-23). Title hint matches the
# article that triggered the FP/TP.
CASES: list[dict] = [
    # TPs — must be preserved
    {"ticker": "D",    "label": "TP", "window_start": "2026-05-15", "window_end": "2026-05-17", "title_hint": "Dominion In Talks"},
    {"ticker": "EL",   "label": "TP", "window_start": "2026-04-01", "window_end": "2026-05-22", "title_hint": "Walks Away From Merger"},
    # FPs — should be blocked
    {"ticker": "QBTS", "label": "FP", "window_start": "2026-05-10", "window_end": "2026-05-12", "title_hint": "IonQ Rises"},
    {"ticker": "RGTI", "label": "FP", "window_start": "2026-05-10", "window_end": "2026-05-12", "title_hint": "IonQ Rises"},
    {"ticker": "MNST", "label": "FP", "window_start": "2026-04-01", "window_end": "2026-05-22", "title_hint": "Celsius"},
    {"ticker": "ONDS", "label": "FP", "window_start": "2026-04-01", "window_end": "2026-05-22", "title_hint": "Defense Play"},
    {"ticker": "INFQ", "label": "FP", "window_start": "2026-05-01", "window_end": "2026-05-22", "title_hint": "Infleqtion"},
    {"ticker": "NBIS", "label": "FP", "window_start": "2026-04-15", "window_end": "2026-05-22", "title_hint": "Nebius Breaks Out"},
    {"ticker": "NXT",  "label": "FP", "window_start": "2026-04-01", "window_end": "2026-05-22", "title_hint": "Nextpower"},
    # FPs — not classified earlier but appeared in audit log
    {"ticker": "IREN", "label": "FP", "window_start": "2026-04-01", "window_end": "2026-05-22", "title_hint": "Acquisition of Nostrum"},
    {"ticker": "FOUR", "label": "FP", "window_start": "2026-04-01", "window_end": "2026-05-22", "title_hint": "Explosive Growth"},
    {"ticker": "PINS", "label": "FP", "window_start": "2026-04-01", "window_end": "2026-05-22", "title_hint": "ODDITY"},
]


async def replay_case(case: dict) -> dict:
    """Fetch the matching article and apply the new logic. Returns
    {ticker, label, expected, actual, kept_or_blocked, ...} for reporting.
    """
    import os
    import httpx
    from agents.market_intelligence.ma_filter import matches_mna_keywords

    ticker = case["ticker"]
    title_hint = case["title_hint"]

    api_key = os.environ["POLYGON_API_KEY"]
    async with httpx.AsyncClient(timeout=15) as cl:
        r = await cl.get(
            "https://api.polygon.io/v2/reference/news",
            params={
                "ticker": ticker,
                "published_utc.gte": case["window_start"],
                "published_utc.lte": case["window_end"],
                "limit": 30,
                "apiKey": api_key,
            },
        )
    data = r.json()

    # Find the article matching title_hint
    target = None
    for art in data.get("results", []):
        if title_hint in (art.get("title") or ""):
            target = art
            break

    if target is None:
        return {
            "ticker": ticker,
            "label": case["label"],
            "actual": "ARTICLE_NOT_FOUND",
            "expected": "kept" if case["label"] == "TP" else "blocked",
            "match": False,
        }

    title = target.get("title", "")
    description = target.get("description") or ""

    # Path A: title match
    title_kw = matches_mna_keywords(title)
    if title_kw:
        return {
            "ticker": ticker,
            "label": case["label"],
            "actual": "kept (Path A: title)",
            "expected": "kept" if case["label"] == "TP" else "blocked",
            "match": case["label"] == "TP",
            "matched_keyword": title_kw,
            "title": title[:100],
        }

    desc_kw = matches_mna_keywords(description)
    if not desc_kw:
        return {
            "ticker": ticker,
            "label": case["label"],
            "actual": "blocked (no kw in title or description)",
            "expected": "kept" if case["label"] == "TP" else "blocked",
            "match": case["label"] == "FP",
            "title": title[:100],
        }

    insights = target.get("insights") or []
    if not insights:
        return {
            "ticker": ticker,
            "label": case["label"],
            "actual": "blocked (description kw but no insights field)",
            "expected": "kept" if case["label"] == "TP" else "blocked",
            "match": case["label"] == "FP",
            "title": title[:100],
        }

    ticker_insight = next((i for i in insights if i.get("ticker") == ticker), None)
    if ticker_insight is None:
        return {
            "ticker": ticker,
            "label": case["label"],
            "actual": "blocked (ticker not in insights — QBTS class)",
            "expected": "kept" if case["label"] == "TP" else "blocked",
            "match": case["label"] == "FP",
            "title": title[:100],
        }

    reasoning = ticker_insight.get("sentiment_reasoning") or ""
    reasoning_kw = matches_mna_keywords(reasoning)
    if not reasoning_kw:
        return {
            "ticker": ticker,
            "label": case["label"],
            "actual": "blocked (insighted but reasoning lacks M&A kw)",
            "expected": "kept" if case["label"] == "TP" else "blocked",
            "match": case["label"] == "FP",
            "title": title[:100],
            "reasoning": reasoning[:120],
        }

    return {
        "ticker": ticker,
        "label": case["label"],
        "actual": "kept (Path B: description+insights+reasoning kw)",
        "expected": "kept" if case["label"] == "TP" else "blocked",
        "match": case["label"] == "TP",
        "matched_keyword": desc_kw,
        "reasoning_kw": reasoning_kw,
        "title": title[:100],
        "reasoning": reasoning[:120],
    }


async def main():
    print("=" * 100)
    print("#88 M&A filter fix — replay against 13 historical cases")
    print("=" * 100)
    print()

    results = []
    for case in CASES:
        r = await replay_case(case)
        results.append(r)
        match_marker = "✓" if r["match"] else "✗"
        print(f"{match_marker} {r['ticker']:<6} [{r['label']}]  expected: {r['expected']:<8}  actual: {r['actual']}")
        if not r["match"]:
            print(f"      title: {r.get('title', '')}")
            if r.get("reasoning"):
                print(f"      reasoning: {r['reasoning']}")

    print()
    print("=" * 100)
    n_tp = sum(1 for r in results if r["label"] == "TP")
    n_fp = sum(1 for r in results if r["label"] == "FP")
    tp_kept = sum(1 for r in results if r["label"] == "TP" and "kept" in r["actual"])
    fp_blocked = sum(1 for r in results if r["label"] == "FP" and "blocked" in r["actual"])
    tp_lost = n_tp - tp_kept
    fp_still_through = n_fp - fp_blocked

    print(f"TPs kept:     {tp_kept}/{n_tp}")
    print(f"FPs blocked:  {fp_blocked}/{n_fp}")
    print(f"TPs LOST:     {tp_lost}     (must be 0 for ship)")
    print(f"FPs still through (acquirer direction-blind class, separate #90): {fp_still_through}")
    print()

    ship_ok = tp_lost == 0 and fp_blocked >= 5
    print(f"SHIP GATE: {'PASS' if ship_ok else 'FAIL'}")
    if not ship_ok:
        if tp_lost > 0:
            print("  → TP regression detected — DO NOT SHIP")
        if fp_blocked < 5:
            print("  → Fewer than 5 FPs blocked — FP-reduction value insufficient")


if __name__ == "__main__":
    asyncio.run(main())
