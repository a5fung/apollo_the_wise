"""Verify the live_cutover_decision deferral is correctly handled.

Expected behavior:
- The entry is status=deferred with deferred_until/earliest_review_date 2026-06-22
- Parser treats deferred as eligible for re-eval (per #64 parser change)
- Today (2026-05-22), date < earliest_review_date 2026-06-22 → blocked by date
- Should appear in `pending` list (blocked by date), NOT in `ready` list

Run: docker exec apollo-market python -m scripts._verify_cutover_deferral
"""
import asyncio
from datetime import date


async def main():
    from agents.market_intelligence.data_gated_reviews import check_pending_reviews

    today = date(2026, 5, 22)
    r = await check_pending_reviews(today)
    print(f"Today: {today}")
    print(f"Ready: {len(r['ready'])}")
    print(f"Pending count: {r['pending_count']}")
    print()

    # Find the cutover entry across both buckets
    all_entries = r["ready"] + r["pending_summary"]
    cutover = next(
        (e for e in all_entries if e["review_id"] == "live_cutover_decision"),
        None,
    )
    if cutover:
        print(f"live_cutover_decision: {cutover}")
    else:
        print("live_cutover_decision: NOT in ready or first 5 pending (may be in tail)")
        # Try to load the YAML directly to confirm status
        from agents.market_intelligence.data_gated_reviews import _load_registry
        entries = _load_registry()
        match = next((e for e in entries if e.get("review_id") == "live_cutover_decision"), None)
        if match:
            print(f"  status={match.get('status')}")
            print(f"  earliest_review_date={match.get('earliest_review_date')}")
            print(f"  deferred_until={match.get('deferred_until')}")


if __name__ == "__main__":
    asyncio.run(main())
