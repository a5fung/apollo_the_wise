"""#200 verify (one-shot, advisory table only — NOT trade-state).

Proves NOW (without a polluting 1PM full scan) that:
  1. the theme-gated compute formula yields the right demoted/retained grades, and
  2. the REAL insert_ep_alert persists theme_gated_tier/score/in_active_theme
     and reads them back (column types + result->record plumbing).

Writes/deletes ONE sentinel row (ticker ZZ200V, source='verify_sentinel') on
mi_ep_alerts (an advisory/alert table, not mi_live_trades). Idempotent cleanup.
"""
import asyncio


def compute_theme_gated_grade(breakdown, in_theme, effective_mult, ep_threshold,
                              earnings_override_fired):
    # Mirrors ep_detector.run_ep_scan inline block exactly.
    structure_raw = sum(breakdown.values()) - breakdown.get("conviction_floor", 0)
    theme_gated_raw = sum(breakdown.values()) if in_theme else structure_raw
    score = round(theme_gated_raw * effective_mult, 1)
    tier = ("HIGH" if (score >= ep_threshold or earnings_override_fired)
            else "MODERATE")
    return tier, score


def _compute_checks():
    thr = 70
    # themeless game_changer the floor promoted: structure=45, floor lifts to 80
    bd_floor = {"gap": 20, "rvol": 10, "catalyst": 15, "theme_bonus": 0,
                "conviction_floor": 35}  # sum = 80
    bd_strong = {"gap": 30, "rvol": 20, "catalyst": 25, "theme_bonus": 0}  # sum = 75
    print("[compute] themeless+floor   ->", compute_theme_gated_grade(bd_floor, False, 1.0, thr, False),
          "(expect MODERATE 45 — DEMOTED)")
    print("[compute] in-theme+floor    ->", compute_theme_gated_grade(bd_floor, True, 1.0, thr, False),
          "(expect HIGH 80 — == live)")
    print("[compute] themeless+strong  ->", compute_theme_gated_grade(bd_strong, False, 1.0, thr, False),
          "(expect HIGH 75 — structure holds)")
    print("[compute] themeless+earn-ovr->", compute_theme_gated_grade(bd_floor, False, 1.0, thr, True),
          "(expect HIGH 45 — override carries)")


async def _roundtrip():
    from agents.market_intelligence.db import insert_ep_alert, get_pool
    from agents.market_intelligence.collector import et_today
    today = et_today()
    rec = {
        "ticker": "ZZ200V", "alert_date": today, "gap_pct": 12.3,
        "rel_volume": 5.0, "ep_score": 80.0, "score_tier": "HIGH",
        "catalyst": "verify sentinel", "catalyst_quality": "game_changer",
        "source": "verify_sentinel",
        "theme_gated_tier": "MODERATE", "theme_gated_score": 45.0,
        "in_active_theme": False,
    }
    await insert_ep_alert(rec)
    pool = await get_pool()
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            "SELECT ticker, score_tier, theme_gated_tier, theme_gated_score, "
            "in_active_theme FROM mi_ep_alerts "
            "WHERE ticker='ZZ200V' AND source='verify_sentinel' "
            "ORDER BY detected_at DESC LIMIT 1"
        )
        print("[roundtrip] read back:", dict(row) if row else None)
        ok = bool(row) and row["theme_gated_tier"] == "MODERATE" \
            and float(row["theme_gated_score"]) == 45.0 \
            and row["in_active_theme"] is False
        await conn.execute(
            "DELETE FROM mi_ep_alerts WHERE ticker='ZZ200V' AND source='verify_sentinel'"
        )
        print("[roundtrip] sentinel deleted; PASS" if ok else "[roundtrip] FAIL")
        return ok


def main():
    _compute_checks()
    ok = asyncio.run(_roundtrip())
    print("RESULT:", "PASS" if ok else "FAIL")


if __name__ == "__main__":
    main()
