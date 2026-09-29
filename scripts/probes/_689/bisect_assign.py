import asyncio, copy, json
from agents.market_intelligence import db as _db, theme_engine as te
from shared.llm_client import make_async_anthropic
from shared.dates import et_today

def proposed(tool, body):
    t = copy.deepcopy(tool)
    t["input_schema"]["properties"]["analysis_scratchpad"]["description"] = (
        "REQUIRED. Brief notes, one short line per uncovered stock: its core business, "
        "the candidate theme(s), whether it fits, and the decision. "
        "These notes are how you avoid hallucinated connections.")
    body = (body.replace("Do NOT write any free-text analysis before your tool call. All per-ticker reasoning belongs INSIDE",
                         "Do NOT write any free text outside the tool call. All per-ticker notes belong INSIDE")
                .replace("Free text before the tool call wastes", "Free text outside the tool call wastes")
                .replace("directly with your reasoning in `analysis_scratchpad`", "directly with your notes in `analysis_scratchpad`"))
    return t, body

async def main():
    themes = await _db.get_active_themes()
    leaders = await _db.get_rs_leaders(et_today().strftime("%Y-%m-%d"), limit=40)
    unc = [s for s in leaders if not any(s["ticker"] in (t.get("tickers") or []) for t in themes)][:12]
    client = make_async_anthropic()
    async def run(label, th, stocks, variant="proposed", drop_pad=False):
        tool = te._THEME_ASSIGNMENT_TOOL; body = te._assignment_body(stocks)
        if variant == "proposed": tool, body = proposed(tool, body)
        if drop_pad:
            tool = copy.deepcopy(tool); tool["input_schema"]["properties"].pop("analysis_scratchpad")
            tool["input_schema"]["required"] = ["assignments"]
        msgs = te._assignment_messages(te.assignment_shared_prefix(th), body)
        try:
            r = await client.messages.create(model="claude-sonnet-5-5", max_tokens=4000, tools=[tool],
                    tool_choice={"type": "tool", "name": tool["name"]}, messages=msgs)
            print(f"{label:48s} stop={r.stop_reason} out={r.usage.output_tokens}")
        except Exception as e:
            print(f"{label:48s} FAILED {str(e)[:90]}")
    n = len(themes)
    await run("A proposed, full board (control)", themes, unc)
    await run("B proposed, 10 themes", themes[:10], unc)
    await run("C proposed, full board, no scratchpad field", themes, unc, drop_pad=True)
    await run("D proposed, first half of themes", themes[: n // 2], unc)
    await run("E proposed, second half of themes", themes[n // 2:], unc)
    await run("F proposed, full board, 3 stocks", themes, unc[:3])
    await run("G ORIGINAL wording, 10 themes", themes[:10], unc, variant="original")
    await run("H proposed, 10 themes, 3 stocks", themes[:10], unc[:3])
    print("stocks:", [s["ticker"] for s in unc])
asyncio.run(main())
