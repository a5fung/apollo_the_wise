"""#700 — run the §4 settle rule over the stored 10-11 and 10-04 bullets: first its FIRST condition (does
every audit event type a bullet names exist in that week's `audit_errors.top_types` with zero live rows?),
then the REAL `verify_narrative_anomalies` (all three conditions + the L1/L2 guard of the review-fix round)
with its verdict and reason. Also lists the promotion ladder ids both weeks (for the §8 'only
magna53_smallcap is new' line). Read-only over the local capture."""
import json
import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parents[2]))
from agents.market_intelligence.system_review import verify_narrative_anomalies  # noqa: E402

rows = [json.loads(l) for l in (HERE / "q1_reviews.out").read_text(encoding="utf-8").splitlines()
        if l.strip().startswith("{")]
by = {r["review_date"]: r for r in rows}
TYPE_RE = re.compile(r"\b[a-z0-9]+(?:_[a-z0-9]+)*_(?:error|failed)\b")
TICKER_RE = re.compile(r"\b[A-Z]{2,5}\b")
NOT_TICKERS = {"ET", "PT", "UTC", "AM", "PM"}

for d in ("2026-10-11", "2026-10-04"):
    m = by[d]["metrics"]
    types = {t["event_type"]: sum(1 for r in t.get("rows") or [] if r.get("disposition") == "live")
             for t in m["audit_errors"]["top_types"]}
    print(f"\n=== {d} top_types (live rows): {types}")
    tickers = set()

    def walk(o):
        if isinstance(o, dict):
            if isinstance(o.get("ticker"), str):
                tickers.add(o["ticker"])
            for v in o.values():
                walk(v)
        elif isinstance(o, list):
            for v in o:
                walk(v)
    walk(m)
    for i, b in enumerate(by[d]["suggestions"], 1):
        named = TYPE_RE.findall(b)
        ok = bool(named) and all(t in types and types[t] == 0 for t in named)
        tick = sorted(t for t in TICKER_RE.findall(b) if t in tickers and t not in NOT_TICKERS)
        print(f"  bullet {i}: names {named} -> cond1 {'PASS' if ok else 'FAIL'}; "
              f"tickers in week's set: {tick}; raw caps tokens: {sorted(set(TICKER_RE.findall(b)))}")
    for i, v in enumerate(verify_narrative_anomalies(by[d]["suggestions"], m), 1):
        print(f"  REAL rule, bullet {i}: {'SETTLED' if v['settled'] else 'mine'} - {v['why']}")
    print(f"  promotions ids: {[c['strategy_id'] for c in m['strategy_promotions']['checks']]}")
