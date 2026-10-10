"""#692 phrases — the ONE paid check (2026-10-10). Runs INSIDE apollo-market (holds the model key).

    docker cp paid_check.py apollo-market:/tmp/paid_check.py
    docker cp paid_check_set.json apollo-market:/tmp/paid_check_set.json
    docker exec -w /app apollo-market python /tmp/paid_check.py --price     # prints the price, no model call
    docker exec -w /app apollo-market python /tmp/paid_check.py /tmp/paid_check_set.json /tmp/paid_check_out.jsonl
    docker cp apollo-market:/tmp/paid_check_out.jsonl .

The SAME function production runs (`ma_filter.ask_deal_question`: same prompt, tool, model,
company-name lookup) on each unique (ticker, headline). Reads and model calls ONLY:
  * the spend-log write inside ask_deal_question is replaced by a no-op (no table is written);
  * the process-level memo/budget are in-memory only.
Every raw tool answer is captured to the output file. ABORTS before the first call above the price ceiling.
"""
import asyncio
import json
import sys
from datetime import datetime
from zoneinfo import ZoneInfo

from agents.market_intelligence import ma_filter as mf
from shared.llm_models import GROUNDED_GRADE_MODEL, pricing_for

CEILING_USD = 2.00
_ET = ZoneInfo("America/New_York")


def estimate(items):
    tool = len(json.dumps(mf._HEADLINE_TOOL))
    inp = sum(len(mf.build_headline_prompt(i["ticker"], "Some Company Inc", i, None)) / 3.5
              + tool / 3.5 + 350 for i in items)
    out = len(items) * 130
    p = pricing_for(GROUNDED_GRADE_MODEL)
    return inp, out, (inp * p["input"] + out * p["output"]) / 1e6, p


async def _noop_spend(**kw):
    return None


class _Recorder:
    """Wraps the production client; keeps every response's usage + raw tool input."""
    def __init__(self, inner):
        self.inner = inner
        self.last = None
        self.messages = self
        self.in_tok = 0
        self.out_tok = 0

    async def create(self, **kw):
        r = await self.inner.messages.create(**kw)
        u = getattr(r, "usage", None)
        self.in_tok += getattr(u, "input_tokens", 0) or 0
        self.out_tok += getattr(u, "output_tokens", 0) or 0
        blk = next((b for b in (r.content or []) if getattr(b, "type", None) == "tool_use"), None)
        self.last = {"raw_tool_input": getattr(blk, "input", None), "stop_reason": getattr(r, "stop_reason", None),
                     "usage": {"in": getattr(u, "input_tokens", None), "out": getattr(u, "output_tokens", None)}}
        return r


async def main():
    args = sys.argv[1:]
    price_only = "--price" in args
    args = [a for a in args if a != "--price"]
    src = args[0] if args else "/tmp/paid_check_set.json"
    dst = args[1] if len(args) > 1 else "/tmp/paid_check_out.jsonl"
    items = json.load(open(src))
    inp, out, est, p = estimate(items)
    print(f"model={GROUNDED_GRADE_MODEL} pricing={p} headlines={len(items)} est_in={inp:.0f} est_out={out:.0f} est_usd={est:.3f}")
    if price_only:
        return
    if est > CEILING_USD:
        print(f"ABORT: estimate ${est:.2f} above ceiling ${CEILING_USD:.2f}")
        return
    import agents.market_intelligence.spend_tracker as st
    st.log_anthropic_call_safe = _noop_spend          # no table write
    rec = _Recorder(mf._get_headline_client())
    mf._headline_client = rec
    now = datetime.now(_ET)
    spent_in = spent_out = 0
    with open(dst, "w") as f:
        for it in items:
            t = it["ticker"]
            co = await mf._company_name(t)
            item = {"title": it["title"], "description": it["description"],
                    "published_utc": it["published_utc"], "publisher": it.get("publisher") or "",
                    "tickers": it.get("tickers") or [], "news_source": "alpaca"}
            rec.last = None
            ans, how = await mf.ask_deal_question(t, item, company_name=co, now_et=now, budget_pool="shared")
            row = {"ticker": t, "days": it["days"], "title": it["title"], "published_utc": it["published_utc"],
                   "match_path": it["match_path"], "kw": it["kw"], "company_name": co, "how": how,
                   "answer": (None if ans is None else {"role": ans.role, "status": ans.status,
                                                        "consideration": ans.consideration,
                                                        "counterparty": ans.counterparty,
                                                        "note": ans.source_text}),
                   "acts": (None if ans is None else bool(mf._headline_acts(ans))),
                   "nominates": (None if ans is None else bool(mf.deal_nominates(ans))),
                   "raw": rec.last}
            f.write(json.dumps(row, default=str) + "\n")
            f.flush()
    actual = (rec.in_tok * p["input"] + rec.out_tok * p["output"]) / 1e6
    print(f"DONE rows={len(items)} in_tok={rec.in_tok} out_tok={rec.out_tok} actual_usd={actual:.4f} -> {dst}")


asyncio.run(main())
