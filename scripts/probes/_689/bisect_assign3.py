import asyncio, copy
from agents.market_intelligence import db as _db, theme_engine as te
from shared.llm_client import make_async_anthropic
from shared.dates import et_today

async def main():
    themes = (await _db.get_active_themes())[:10]
    leaders = await _db.get_rs_leaders(et_today().strftime("%Y-%m-%d"), limit=40)
    unc = [s for s in leaders if not any(s["ticker"] in (t.get("tickers") or []) for t in themes)][:3]
    tool = copy.deepcopy(te._THEME_ASSIGNMENT_TOOL)
    tool["input_schema"]["properties"]["analysis_scratchpad"]["description"] = (
        "REQUIRED. Brief notes, one short line per uncovered stock: its core business, "
        "the candidate theme(s), whether it fits, and the decision. "
        "These notes are how you avoid hallucinated connections.")
    prefix = te.assignment_shared_prefix(themes); body = te._assignment_body(unc)
    base = body.split("OUTPUT FORMAT", 1)[0]
    S = ["Do NOT write any free text outside the tool call.",
         " All per-ticker notes belong INSIDE the `assign_stocks_to_themes` tool's `analysis_scratchpad` field.",
         " Free text outside the tool call wastes the output budget and can cause the response to truncate before the tool is invoked.",
         "\n\nCall `assign_stocks_to_themes` directly with your notes in `analysis_scratchpad` (one short line per ticker: business + decision + theme name or \"no fit\").",
         " The `assignments` array contains only the actual fits."]
    client = make_async_anthropic()
    async def run(label, fmt):
        text = prefix + base + fmt
        try:
            r = await client.messages.create(model="claude-sonnet-5-5", max_tokens=3000, tools=[tool],
                    tool_choice={"type": "tool", "name": tool["name"]}, messages=[{"role": "user", "content": text}])
            print(f"{label:60s} stop={r.stop_reason} out={r.usage.output_tokens}")
        except Exception as e:
            print(f"{label:60s} FAILED {str(e)[:70]}")
    await run("P1 no OUTPUT FORMAT (reworded field)", "")
    acc = "OUTPUT FORMAT — IMPORTANT:\n"
    for i, s in enumerate(S, 2):
        acc += s
        await run(f"P{i} + sentence {i-1}: {s.strip()[:40]}", acc)
    for i, s in enumerate(S, 1):
        await run(f"Q{i} ONLY sentence {i}: {s.strip()[:40]}", "OUTPUT FORMAT — IMPORTANT:\n" + s.strip())
    await run("R new: 'Use analysis_scratchpad for one short line per ticker'",
              "OUTPUT FORMAT:\nUse `analysis_scratchpad` for one short line per ticker (business, decision, theme name or \"no fit\"). "
              "The `assignments` array contains only the actual fits.")
asyncio.run(main())
