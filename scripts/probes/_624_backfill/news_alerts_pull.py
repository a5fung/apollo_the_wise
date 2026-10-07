"""#624 news step 1 — recent live EP alerts and the corpus the live grader saw. READ-ONLY (SELECT only), one capture.
Output: /tmp/_624bf/news_alerts.jsonl (one row per alert since 2026-08-01) — ticker, alert_date, detected_at, gap, quality,
catalyst, catalyst_type, source classes from the ep_catalyst_provenance audit row, grounded_text (first 1500 chars) + length."""
import asyncio, json, re
from datetime import date
from agents.market_intelligence.db import get_pool


def j(v):
    return v if isinstance(v, (int, float, bool, str, type(None), list, dict)) else str(v)


async def main():
    pool = await get_pool()
    async with pool.acquire() as c:
        rows = await c.fetch("""select id, ticker, alert_date, gap_pct, ep_score, score_tier, catalyst, catalyst_quality, catalyst_type,
                                   claude_analysis, judge_tier, judge_grade, created_at, detected_at, source, grounded_text
                                from mi_ep_alerts where alert_date >= $1 order by alert_date, created_at""", date(2026, 8, 1))
        prov = await c.fetch("""select created_at, summary, detail from mi_audit_log where event_type='ep_catalyst_provenance'
                                and created_at >= '2026-07-30'""")
        pmap = {}
        for p in prov:
            try:
                d = json.loads(p["detail"])
                pmap.setdefault((d.get("ticker"), d.get("alert_date")), []).append(d.get("sources"))
            except Exception:
                pass
        out = []
        for r in rows:
            d = {k: j(v) for k, v in dict(r).items() if k not in ("grounded_text", "claude_analysis", "created_at", "detected_at")}
            d["created_at"] = str(r["created_at"]); d["detected_at"] = str(r["detected_at"])
            gt = r["grounded_text"] or ""
            d["grounded_len"] = len(gt); d["grounded_head"] = gt[:600]
            d["benzinga"] = [{"date": m.group(1), "title": m.group(2).strip()} for m in
                             re.finditer(r"\[Benzinga (\d{4}-\d{2}-\d{2})\] (.+?)\.(?:\s|$)", gt)]
            d["sec_head"] = (re.match(r"\[SEC [^\]]*\]", gt).group(0) if gt.startswith("[SEC") else None)
            d["has_web"] = "[Web summary]" in gt
            d["claude_analysis_head"] = (r["claude_analysis"] or "")[:500]
            d["prov_sources"] = pmap.get((r["ticker"], str(r["alert_date"])))
            out.append(d)
        with open("/tmp/_624bf/news_alerts.jsonl", "w") as f:
            for d in out:
                f.write(json.dumps(d, default=str) + "\n")
        print("alerts", len(out), "with grounded_text", sum(1 for d in out if d["grounded_len"]),
              "dates", out[0]["alert_date"] if out else None, out[-1]["alert_date"] if out else None)
asyncio.run(main())
