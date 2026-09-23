"""Triage today's 3 EP alerts (QURE, JBL, LZB) against the 5 operator-reported issues (6/17).
Read-only. For each name dumps: the mi_ep_alerts row (judge/theme/catalyst/confidence fields),
the cached-metrics→rubric render, the structural theme-membership lookup, and the full audit
timeline (alert→grade-decision→any downgrade msg, with timestamps → the 20-min gap on LZB)."""
import asyncio
from agents.market_intelligence.db import get_pool
from agents.market_intelligence.collector import et_today

NAMES = ["QURE", "JBL", "LZB"]
FIELDS = ["ticker", "alert_date", "created_at", "score_tier", "ep_score", "gap_pct",
          "catalyst_quality", "confidence_multiplier", "gemini_validation", "catalyst_type",
          "fire_axes", "in_active_theme", "in_narrative_cohort", "materiality_tier",
          "grade_engine_authority", "judge_grade", "judge_tier", "judge_direction",
          "has_direct_source", "catalyst", "claude_analysis"]


async def main():
    today = et_today()
    pool = await get_pool()
    async with pool.acquire() as c:
        cols = {r["column_name"] for r in await c.fetch(
            "SELECT column_name FROM information_schema.columns WHERE table_name='mi_ep_alerts'")}
        pick = [f for f in FIELDS if f in cols]
        print(f"=== mi_ep_alerts (today={today}) — picked {len(pick)}/{len(FIELDS)} fields ===")
        for tk in NAMES:
            rows = await c.fetch(
                f"SELECT {', '.join(pick)} FROM mi_ep_alerts WHERE ticker=$1 "
                "ORDER BY created_at DESC LIMIT 1", tk)
            print(f"\n----- {tk} -----")
            if not rows:
                print("  (no mi_ep_alerts row)"); continue
            for k in pick:
                v = rows[0][k]
                if isinstance(v, str) and len(v) > 400:
                    v = v[:400] + " …[%d chars]" % len(rows[0][k])
                print(f"  {k:24}: {v}")

        # rubric (issue 2) + structural theme (issue 1) via the SAME code the alert uses
        print("\n=== RUBRIC + THEME (the exact alert-time lookups) ===")
        from agents.market_intelligence.catalyst_metrics_extractor import lookup_cached_metrics
        from agents.market_intelligence.catalyst_rubric_runtime import (
            score_ep_with_rubric, format_rubric_for_telegram, get_theme_membership,
            format_theme_for_telegram)
        for tk in NAMES:
            print(f"\n----- {tk} -----")
            try:
                ext = await lookup_cached_metrics(tk, today)
                print(f"  cached_metrics: {'PRESENT' if ext else 'NONE (→ no rubric block)'}")
                if ext:
                    rt = format_rubric_for_telegram(tk, ext, today)
                    print(f"  rubric_render: {rt[:300] if rt else 'score_ep_with_rubric → None'}")
            except Exception as e:
                print(f"  cached_metrics ERROR: {type(e).__name__}: {e}")
            try:
                th = await get_theme_membership(tk)
                print(f"  theme_membership(mi_themes): {th}")
                print(f"  theme_render: {format_theme_for_telegram(th)}")
            except Exception as e:
                print(f"  theme ERROR: {type(e).__name__}: {e}")

        # audit timeline (issue 3 — the alert→downgrade 20-min gap, which job sent it)
        print("\n=== AUDIT TIMELINE (today, ET) — alert / grade-decision / downgrade events ===")
        for tk in NAMES:
            print(f"\n----- {tk} -----")
            rows = await c.fetch("""
                SELECT (created_at AT TIME ZONE 'America/New_York') AS et, event_type,
                       left(coalesce(summary,''), 160) AS s
                FROM mi_audit_log
                WHERE (created_at AT TIME ZONE 'America/New_York')::date = $1
                  AND (summary ILIKE '%'||$2||'%' OR detail ILIKE '%'||$2||'%')
                ORDER BY created_at""", today, tk)
            if not rows:
                print("  (no audit rows mentioning the ticker today)")
            for r in rows:
                print(f"  {r['et']:%H:%M:%S}  {r['event_type']:42} {r['s']}")


if __name__ == "__main__":
    asyncio.run(main())
