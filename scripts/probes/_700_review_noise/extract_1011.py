"""#700 — read the one-time capture (q1_reviews.out) and print the 2026-10-11 review's stored
pieces beside the 2026-10-04 ones, so the design doc's hand render uses REAL content.
Read-only over a local file; no DB, no send."""
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
rows = [json.loads(l) for l in (HERE / "q1_reviews.out").read_text(encoding="utf-8").splitlines()
        if l.strip().startswith("{")]
by = {r["review_date"]: r for r in rows}
cur, prev = by["2026-10-11"], by["2026-10-04"]
m, p = cur["metrics"], prev["metrics"]
part = sys.argv[1] if len(sys.argv) > 1 else "a"


def j(x, n=1500):
    return json.dumps(x, ensure_ascii=False, default=str)[:n]


if part == "a":
    print("rows:", [(r["review_date"], r["window_days"]) for r in rows])
    print("metrics keys:", sorted(m.keys()))
    print("\n=== SUMMARY 10-11 ===\n" + cur["summary"])
    print("\n=== SUGGESTIONS 10-11 ===", json.dumps(cur["suggestions"], indent=1, ensure_ascii=False))
    print("\n=== REPORT META 10-11 ===", json.dumps({k: v for k, v in m["report"].items() if k != "suppressed"},
                                                   indent=1, ensure_ascii=False))
    print("suppressed n:", len(m["report"]["suppressed"]))
    for s in m["report"]["suppressed"][:4]:
        print("  ", s)
    ae = m["audit_errors"]
    print("\n=== AUDIT_ERRORS 10-11 === total", ae["total"], "open", ae["open_total"])
    for t in ae["top_types"]:
        print(" ", t["event_type"], "x", t["count"], "disp", t["disposition"], "last", t["last_seen"],
              "days_ago", t["days_ago"])
        for d in t["rows"][:3]:
            print("     row:", d["disposition"], "|", d["why"], "| job", d.get("job_id"), "| exc",
                  d.get("exception"), "| summary", (d.get("summary") or "")[:110])
        print("     ... rows:", len(t["rows"]))
    print("\n=== PENDING REVIEWS ===", j(m["pending_reviews"], 2500))
    print("\n=== PROMOTIONS ===", j(m["strategy_promotions"], 2500))
elif part == "b":
    for k in ["crypto", "mfe_capture", "judge_weekly", "drift_check", "cooldowns", "theme_churn", "anomalies",
              "regime", "ep_outcomes", "paper_trades", "shadow_orb", "wick", "clusters", "window"]:
        print(f"\n=== {k} 10-11 ===", j(m.get(k), 1200))
        print(f"--- {k} 10-04 ---", j(p.get(k), 600))
elif part == "c":
    mo = m["missed_opportunities"]
    print("=== MISSED 10-11 === keys", list(mo.keys()))
    print("gaps n", len(mo.get("gaps") or []), "top", len(mo.get("top_winners") or []),
          "cats", len(mo.get("by_category") or []))
    print(j(mo, 3500))
    print("\n=== LOSERS 10-11 ===", j(m["loser_breakdown"], 1500))
    print("\n=== POSTMORTEM best/worst ===", j({"best": m.get("postmortem_best"), "worst": m.get("postmortem_worst")}, 3000))
elif part == "d":
    print("=== 10-04 SUMMARY ===\n" + prev["summary"])
    print("\n=== 10-04 audit_errors ===", j({k: v for k, v in p["audit_errors"].items() if k != "dispositioned"}, 1500))
    print("\n=== 10-04 report meta ===", j({k: v for k, v in p["report"].items() if k != "suppressed"}, 1500))
    print("\n=== 10-04 pending ===", j(p["pending_reviews"], 1200))
    print("\n=== 10-04 promotions ===", j(p["strategy_promotions"], 1200))
    print("\n=== 10-04 missed ===", j(p["missed_opportunities"], 1200))
    print("\n=== news_source_quality 10-11 ===", j(m.get("news_source_quality"), 800))
