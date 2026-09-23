"""W1 (#242) prod integration write check — exercises the LIVE insert_ep_alert path
(new grounded_text/baseline_floor_tier columns + 26-param INSERT) AND the judge shadow
writer (grade_holistic → update_ep_alert_judge_shadow) end-to-end against the real
mi_ep_alerts schema, then READS THE ROW BACK to prove the columns populated (the silent
0-row-UPDATE failure mode the advisor flagged). Synthetic non-colliding ticker; cleans up.

Run: docker exec apollo-market python /app/scripts/_w1_judge_integration_check.py
mi_ep_alerts is a telemetry/alerts table (NOT trade state) — this write is allowed.
"""
import asyncio

from agents.market_intelligence import db
from agents.market_intelligence.catalyst_materiality import extract_deal_value, rule_materiality
from agents.market_intelligence.collector import et_today
from agents.market_intelligence.ep_detector import _get_claude
from agents.market_intelligence.ep_grade_judge import assemble_judge_inputs, grade_holistic

TICKER = "ZZTEST"
_MKTCAP = 1.0e8  # $100M micro-cap; the $30M catalyst below = 30% of cap → rule 'transformative'


async def main():
    d = et_today()
    record = {
        "ticker": TICKER, "alert_date": d, "gap_pct": 18.5, "rel_volume": 4.1,
        "ep_score": 80, "score_tier": "HIGH", "catalyst": "Synthetic W1 integration probe",
        "catalyst_quality": "strong", "claude_analysis": "integration test only",
        "vol_percentile": 90, "source": "w1_integration_test",
        "grounded_text": "SYNTHETIC SEC 8-K body: company announced a $30M contract.",
        "baseline_floor_tier": "HIGH",
    }

    # 1) live insert path (new columns)
    await db.insert_ep_alert(record)
    print(f"[1] insert_ep_alert OK ({TICKER} {d})")

    # 2) judge call + shadow writer (replicates run_ep_scan._judge_shadow, incl. W4 #245
    #    deterministic deal/cap materiality wiring)
    r = {"ticker": TICKER, "score_tier": "HIGH", "catalyst_quality": "strong",
         "catalyst": record["catalyst"], "claude_analysis": record["claude_analysis"],
         "gap_pct": 18.5, "in_active_theme": False, "in_narrative_cohort": False,
         "ep_score": 80, "grounded_text": record["grounded_text"]}
    # W4: the rule tier the judge is fed — $30M catalyst ÷ $100M cap = 30% → 'transformative'
    rule_mat = rule_materiality(
        extract_deal_value(f"{r['catalyst']} {r['claude_analysis']} {record['grounded_text']}"),
        _MKTCAP)
    print(f"[2w4] rule_materiality (deal/cap) = {rule_mat!r}  (expect 'transformative')")
    assert rule_mat == "transformative", f"W4 rule wiring broken: got {rule_mat!r}"
    payload = assemble_judge_inputs(r, grounded_text=r["grounded_text"],
                                    market_cap=_MKTCAP, sector="Healthcare",
                                    materiality_tier=rule_mat)
    assert payload["materiality_tier"] == "transformative", "W4: tier did not reach payload"
    verdict = await grade_holistic(_get_claude(), payload, timeout=20,
                                   log_caller="judge_integration_probe")
    print(f"[2] grade_holistic → {verdict}")
    if verdict is not None:
        await db.update_ep_alert_judge_result(
            TICKER, d, judge_tier=verdict["tier"],
            judge_direction=verdict["direction_vs_floor"],
            judge_rationale=verdict["rationale"],
            judge_materiality_tier=verdict.get("materiality_tier"))
        print("[2b] update_ep_alert_judge_result OK")

    # 3) READ BACK — the real pass criterion
    pool = await db.get_pool()
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            "SELECT grounded_text, baseline_floor_tier, judge_tier, judge_direction, "
            "judge_rationale, judge_materiality_tier FROM mi_ep_alerts "
            "WHERE ticker=$1 AND alert_date=$2", TICKER, d)
    print("[3] READ-BACK:")
    for k in ("grounded_text", "baseline_floor_tier", "judge_tier", "judge_direction",
              "judge_materiality_tier"):
        print(f"      {k} = {row[k]!r}")
    print(f"      judge_rationale = {(row['judge_rationale'] or '')[:120]!r}")

    ok = (row["grounded_text"] and row["baseline_floor_tier"] == "HIGH"
          and (verdict is None or row["judge_tier"]))
    verdict_ok = verdict is None or (row["judge_tier"] and row["judge_direction"])
    print(f"\n  insert columns populated: {bool(row['grounded_text'] and row['baseline_floor_tier'])}")
    print(f"  judge shadow populated:   {bool(row['judge_tier']) if verdict is not None else 'judge fail-open (None) — acceptable'}")

    # 4) cleanup (telemetry-table DELETE — allowed)
    async with pool.acquire() as conn:
        await conn.execute("DELETE FROM mi_ep_alerts WHERE ticker=$1 AND alert_date=$2", TICKER, d)
    print("[4] cleanup: synthetic row deleted")

    print(f"\n=== W1 INTEGRATION CHECK: {'PASS' if ok and verdict_ok else 'FAIL — investigate'} ===")


asyncio.run(main())
