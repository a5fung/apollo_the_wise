import asyncio, copy, re
from collections import Counter
from unittest.mock import AsyncMock
from agents.market_intelligence import db as _db, briefing as _brief, theme_engine as te
_db.log_audit_event = AsyncMock(); _brief.send_telegram_message = AsyncMock()
from shared.llm_client import make_async_anthropic
from shared.dates import et_today
class Stop(BaseException): pass
cap = {}
class Cap:
    messages = None
    def __init__(self): self.messages = self
    async def create(self, **kw): cap["d"] = copy.deepcopy(kw); raise Stop()

def strip_pad_tool(t):
    t = copy.deepcopy(t); p = t["input_schema"]["properties"]
    if "analysis_scratchpad" in p:
        p.pop("analysis_scratchpad"); t["input_schema"]["required"] = [r for r in t["input_schema"]["required"] if r != "analysis_scratchpad"]
    return t

async def main():
    themes = await _db.get_active_themes()
    leaders = await _db.get_rs_leaders(et_today().strftime("%Y-%m-%d"), limit=40)
    by_t = {s["ticker"]: s for s in leaders}
    unc = [s for s in leaders if not any(s["ticker"] in (t.get("tickers") or []) for t in themes)][:12]
    body = te._assignment_body(unc).split("OUTPUT FORMAT", 1)[0] + (
        "OUTPUT FORMAT — IMPORTANT:\nDo NOT write any free text outside the tool call. "
        "The `assignments` array contains only the actual fits.")
    tool = strip_pad_tool(te._THEME_ASSIGNMENT_TOOL)
    reqs = {"assignment_NO_PAD": (5, dict(max_tokens=4000, tools=[tool], tool_choice={"type": "tool", "name": tool["name"]},
            messages=te._assignment_messages(te.assignment_shared_prefix(themes), body)))}
    te._get_anthropic_client = lambda: Cap()
    try: await te._discover_new_themes_single(unc, themes, by_t)
    except Stop: pass
    d = cap["d"]; d.pop("model", None)
    d["tools"] = [strip_pad_tool(t) for t in d["tools"]]
    def fix(text):
        text = re.sub(r"OUTPUT FORMAT — IMPORTANT:\n.*?\n\n", "OUTPUT FORMAT — IMPORTANT:\nDo NOT write any free text outside the tool call.\n\n", text, flags=re.S)
        return text.replace(", with your terse reasoning in `analysis_scratchpad`.", ".")
    for m in d["messages"]:
        if isinstance(m["content"], str): m["content"] = fix(m["content"])
        else:
            for blk in m["content"]:
                if blk.get("type") == "text": blk["text"] = fix(blk["text"])
    left = sum(str(m).count("analysis_scratchpad") for m in d["messages"])
    print("discovery prompt mentions of analysis_scratchpad after strip:", left, "| tool_choice:", d.get("tool_choice"))
    reqs["discovery_NO_PAD"] = (4, d)
    client = make_async_anthropic()
    for label, (n, kw) in reqs.items():
        res = Counter()
        async def one():
            try:
                r = await client.messages.create(model="claude-sonnet-5-5", **kw)
                tu = [bl for bl in r.content if getattr(bl, "type", "") == "tool_use"]
                res["answered:" + ",".join(sorted({bl.name for bl in tu})) if tu else f"no-tool:{r.stop_reason}"] += 1
            except Exception as e:
                res["REFUSED" if "refus" in str(e) or "no text block" in str(e) else type(e).__name__] += 1
        await asyncio.gather(*[one() for _ in range(n)])
        print(f"{label:24s} {dict(res)}")
asyncio.run(main())
