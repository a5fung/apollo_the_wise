import asyncio, copy, json, anthropic
from agents.market_intelligence import theme_merge_arm as tma
from agents.market_intelligence.db import get_pool
from shared.llm_client import _apply_forced_tool_rewrite

def swap_words(s):
    return (s.replace("CANDIDATE CHILD", "CANDIDATE NARROWER").replace("CANDIDATE PARENT", "CANDIDATE BROADER")
             .replace("CHILD_OF", "NARROWER_OF").replace("child", "narrower").replace("parent", "broader"))

async def main():
    pool = await get_pool()
    names = ["Cloud Data Storage & Analytics Infrastructure", "Cloud Application Delivery & Observability Infrastructure"]
    async with pool.acquire() as c:
        rows = {r["name"]: dict(r) for r in await c.fetch(
            "SELECT DISTINCT ON (name) name, tickers, description, stage FROM mi_themes WHERE name = ANY($1) ORDER BY name, theme_date DESC", names)}
    prompt = tma.build_containment_prompt(rows[names[0]], rows[names[1]], {})
    tool = tma.CONTAINMENT_ADJUDICATION_TOOL
    rew, _ = _apply_forced_tool_rewrite(dict(model="claude-sonnet-5-5", max_tokens=1500,
        messages=[{"role": "user", "content": "x"}], tools=[tool], tool_choice={"type": "tool", "name": tool["name"]}))
    oc = rew["output_config"]

    no_pad = copy.deepcopy(oc); s = no_pad["format"]["schema"]
    s["properties"].pop("analysis_scratchpad"); s["required"].remove("analysis_scratchpad")
    neutral_desc = copy.deepcopy(oc); neutral_desc["format"]["schema"]["properties"]["analysis_scratchpad"]["description"] = "Brief notes."
    renamed = copy.deepcopy(oc); s3 = renamed["format"]["schema"]
    s3["properties"] = {"notes": s3["properties"].pop("analysis_scratchpad"), **s3["properties"]}
    s3["required"] = ["notes", "verdict", "reason"]
    swapped = json.loads(swap_words(json.dumps(oc)))

    cut = prompt.split("Adjudicate with the tool.")[0].rstrip()
    q = "Is 'Cloud Data Storage' a sub-theme of 'Cloud Infrastructure'? Answer in the schema."
    tests = [
        ("1 simple q + schema WITHOUT scratchpad", q, no_pad),
        ("2 simple q + schema, scratchpad kept, child/parent -> narrower/broader", swap_words(q), swapped),
        ("3 simple q + schema, scratchpad renamed 'notes' (same 'Reason FIRST' text)", q, renamed),
        ("4 simple q + schema, scratchpad name kept, description 'Brief notes.'", q, neutral_desc),
        ("5 simple q + ORIGINAL schema (control, refused before)", q, oc),
        ("6 prod prompt minus final 'Fill analysis_scratchpad FIRST' paragraph, plain", cut, None),
        ("7 prod prompt, child/parent swapped, final paragraph kept, plain", swap_words(prompt), None),
        ("8 ORIGINAL prod prompt, plain (control, refused before)", prompt, None),
    ]
    raw = anthropic.AsyncAnthropic()
    print("PROMPT final paragraph:", repr(prompt[len(cut):][:400]))
    print("SCRATCHPAD desc:", oc["format"]["schema"]["properties"]["analysis_scratchpad"]["description"])
    for label, text, cfg in tests:
        kw = dict(model="claude-sonnet-5-5", max_tokens=1500, messages=[{"role": "user", "content": text}])
        if cfg: kw["output_config"] = cfg
        try:
            r = await raw.messages.create(**kw)
            last = r.content[-1] if r.content else None
            print(f"{label} || stop={r.stop_reason} out={r.usage.output_tokens} || "
                  f"{(last.text[:160] if last is not None and last.type == 'text' else '').replace(chr(10), ' ')}")
        except Exception as e:
            print(f"{label} || ERROR {str(e)[:200]}")
asyncio.run(main())
