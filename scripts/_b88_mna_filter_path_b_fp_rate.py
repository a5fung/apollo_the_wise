"""Backward check: M&A filter Path A + Path B fix (#88) — TP/FP drift detection.

Trigger: 2026-05-23 #88 shipped a two-path discriminator on
ma_filter.polygon_news_has_mna_headline (Path A = title keyword match,
Path B = description match + ticker in insights + insight reasoning
contains M&A kw). Pre-ship backward-replay against 13 historical cases
showed 2/2 TPs kept, 8/10 FPs blocked.

This monthly re-evaluation script re-classifies the 30d of post-#88
mna_filter_fired audit events to detect:
  1. TP regression — a filter shape that was supposed to keep TPs has
     started dropping them (e.g., Polygon API changes to insights
     structure)
  2. New FP patterns — articles that pass our discriminator but are
     still semantically wrong (acquirer direction-blind leaks via
     description matches, sympathy-merger reasoning bleed, etc.)
  3. polygon_news_insights_missing audit count — if Polygon stops
     populating insights on certain article classes, Path B starts
     skipping articles entirely (false-negative risk)

Per `feedback_methodology_insights_need_periodic_revalidation.md`:
this script is the auto-refresh for #88's Path A + Path B design.

Run: docker exec apollo-market python -m scripts._b88_mna_filter_path_b_fp_rate
"""
import asyncio
import json
from collections import Counter, defaultdict


async def main():
    from agents.market_intelligence.db import get_pool
    pool = await get_pool()

    async with pool.acquire() as conn:
        # Pull post-#88 mna_filter_fired events. The #88 ship was
        # 2026-05-23; only events on/after that date are evaluated
        # under the new logic. Earlier events used the old code.
        rows = await conn.fetch("""
            SELECT split_part(summary, ' ', 1) AS ticker,
                   created_at::date AS audit_date,
                   detail
            FROM mi_audit_log
            WHERE event_type = 'mna_filter_fired'
              AND created_at >= '2026-05-23'::date
              AND created_at > NOW() - INTERVAL '30 days'
        """)
        n_total = len(rows)

        # polygon_news_insights_missing — Path B skip count
        insights_missing = await conn.fetchval("""
            SELECT COUNT(*) FROM mi_audit_log
            WHERE event_type = 'polygon_news_insights_missing'
              AND created_at > NOW() - INTERVAL '30 days'
        """)

    print(f"#88 M&A filter Path B re-evaluation — last 30d (post-2026-05-23 ship)")
    print(f"  Total mna_filter_fired events: {n_total}")
    print(f"  polygon_news_insights_missing skips: {insights_missing}")
    print()

    if n_total == 0:
        print("→ No post-#88 mna_filter_fired events yet. Check again next month.")
        return

    # Slice by match path (title vs description+insights)
    path_counts = Counter()
    by_ticker: dict[str, list] = defaultdict(list)
    by_path_titles: dict[str, set] = defaultdict(set)

    for r in rows:
        ticker = r["ticker"]
        d = r["detail"] or ""
        # Try JSON parse first; fall back to substring match
        match_path = "unknown"
        title_preview = "—"
        try:
            obj = json.loads(d)
            match_path = obj.get("match_path", "unknown")
            title_preview = (obj.get("title") or "")[:80]
        except (json.JSONDecodeError, ValueError):
            if '"match_path": "title"' in d or 'match_path=title' in d:
                match_path = "title"
            elif "description+insights" in d:
                match_path = "description+insights"
            elif "claude_classifier" in d:
                match_path = "claude_classifier"  # EP path, not polygon_news
        path_counts[match_path] += 1
        by_ticker[ticker].append((r["audit_date"], match_path))
        if title_preview != "—":
            by_path_titles[match_path].add(title_preview)

    print("=" * 100)
    print("MATCH PATH DISTRIBUTION (last 30d)")
    print("=" * 100)
    for path, count in path_counts.most_common():
        print(f"  {path:<30} {count:>4}  ({100*count//n_total}%)")
    print()

    print("=" * 100)
    print("TOP TICKERS BY FIRE COUNT (post-#89 dedup should keep this small)")
    print("=" * 100)
    print(f"{'TICKER':<8} {'fires':>6}  paths")
    print("-" * 50)
    for ticker, events in sorted(by_ticker.items(), key=lambda x: -len(x[1]))[:15]:
        paths = Counter(p for _, p in events)
        path_summary = ", ".join(f"{p}:{n}" for p, n in paths.most_common())
        print(f"{ticker:<8} {len(events):>6}  {path_summary}")
    print()

    print("=" * 100)
    print("SAMPLE TITLES BY PATH (manual TP/FP classification needed)")
    print("=" * 100)
    for path in ["title", "description+insights"]:
        titles = by_path_titles.get(path, set())
        if not titles:
            continue
        print(f"\n>>> {path} matches (showing up to 10 unique titles):")
        for t in list(titles)[:10]:
            print(f"  • {t}")
    print()

    # Decision gate
    print("=" * 100)
    print("DECISION GATE — methodology drift detection")
    print("=" * 100)
    title_count = path_counts.get("title", 0)
    desc_insights_count = path_counts.get("description+insights", 0)
    claude_count = path_counts.get("claude_classifier", 0)
    total_polygon = title_count + desc_insights_count

    if total_polygon == 0 and claude_count > 0:
        print(f"→ All {claude_count} fires were claude_classifier path (EP detector).")
        print("  No polygon_news layer activity to evaluate. Check again next month.")
    elif total_polygon < 5:
        print(f"→ Only {total_polygon} polygon_news fires in 30d (title={title_count},")
        print(f"  description+insights={desc_insights_count}). N too small for drift")
        print(f"  detection. Continue accumulating; review at N>=20.")
    else:
        title_pct = 100 * title_count // total_polygon if total_polygon else 0
        desc_pct = 100 * desc_insights_count // total_polygon if total_polygon else 0
        print(f"→ Polygon-news fires: {total_polygon} (title={title_count}/{title_pct}%, ")
        print(f"  description+insights={desc_insights_count}/{desc_pct}%)")
        print()
        print("OPERATOR ACTION REQUIRED — manual TP/FP classification of the sample")
        print("titles above. Score each fire:")
        print("  - TP: article is genuinely about this ticker's M&A activity (target side)")
        print("  - FP: article isn't about this ticker's M&A (multi-tag bleed, sympathy")
        print("    move, name collision, acquirer direction-blindness, etc.)")
        print()
        print("Compare TP rate to #88 ship baseline (2 TPs / 13 cases = 15% TP rate):")
        print("  - If TP rate ≥30% AND insights_missing is low: filter is working well")
        print("  - If TP rate <15%: FP rate has DRIFTED HIGHER — investigate which path")
        print("    is leaking (likely Path B description+insights direction-blindness)")
        print("  - If insights_missing > 20% of total: Path B is skipping too many ")
        print("    articles (false-negative risk); investigate Polygon insights coverage")
    print()
    print("Cross-references:")
    print("  - #88: Path A + Path B fix ship (2026-05-23)")
    print("  - #90: residual direction-blindness via descriptions (filed 2026-05-23)")
    print("  - feedback_methodology_insights_need_periodic_revalidation.md")


if __name__ == "__main__":
    asyncio.run(main())
