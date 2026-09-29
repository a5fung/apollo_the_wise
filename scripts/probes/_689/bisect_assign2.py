import asyncio, copy, anthropic
from agents.market_intelligence import db as _db, theme_engine as te
from shared.llm_client import make_async_anthropic
from shared.dates import et_today

async def main():
    themes = (await _db.get_active_themes())[:10]
    leaders = await _db.get_rs_leaders(et_today().strftime("%Y-%m-%d"), limit=40)
    unc = [s for s in leaders if not any(s["ticker"] in (t.get("tickers") or []) for t in themes)][:3]
    tool = copy.deepcopy(te._THEME_ASSIGNMENT_TOOL)
    tool["input_schema"]["properties"].pop("analysis_scratchpad"); tool["input_schema"]["required"] = ["assignments"]
    prefix = te.assignment_shared_prefix(themes); body = te._assignment_body(unc)
    stock_part, rest = body.split("Rules:", 1)
    rules, fmt = rest.split("OUTPUT FORMAT", 1)
    print("STOCK PART:", stock_part.replace("\n", " | ")[:600])
    client = make_async_anthropic(); raw = anthropic.AsyncAnthropic()
    async def run(label, text, use_tool=True, blocks=False):
        content = [{"type": "text", "text": text}] if blocks else text
        kw = dict(model="claude-sonnet-5-5", max_tokens=3000, messages=[{"role": "user", "content": content}])
        try:
            if use_tool:
                r = await client.messages.create(tools=[tool], tool_choice={"type": "tool", "name": tool["name"]}, **kw)
            else:
                r = await raw.messages.create(**kw)
            print(f"{label:52s} stop={r.stop_reason} out={r.usage.output_tokens}")
        except Exception as e:
            print(f"{label:52s} FAILED {str(e)[:80]}")
    await run("I prefix + stocks + rules (no OUTPUT FORMAT)", prefix + stock_part + "Rules:" + rules)
    await run("J prefix + stocks only", prefix + stock_part)
    await run("K stocks only + 'assign if it fits'", stock_part + "\nAssign each stock to one of: " + ", ".join(t["name"] for t in themes))
    await run("L prefix only + 'no stocks'", prefix + "\nUNCOVERED STOCKS: none")
    await run("M full H text, plain, NO tool", prefix + body, use_tool=False)
    await run("N stocks only, plain, NO tool", stock_part + "\nWhich theme fits each stock?", use_tool=False)
    for s in unc:
        await run(f"O one stock line only, plain: {s['ticker']}", te._assignment_stock_line(s) + "\nWhat does this company do?", use_tool=False)
asyncio.run(main())
