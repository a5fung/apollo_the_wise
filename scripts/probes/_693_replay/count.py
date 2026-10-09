"""#693 replay — STEP 2 ($0): token-count every rebuilt request (count_tokens is free) and compare
with the live 10-05 api_usage input_tokens. No generation, no DB writes."""
import asyncio, json, os
import anthropic
SYSTEM = "You are a JSON API. Respond with valid JSON only. No prose, no markdown, no explanation."
async def main():
    rec = json.load(open("/tmp/693_recon.json"))
    usage = json.load(open("/tmp/693_usage_1005.json"))
    cl = anthropic.AsyncAnthropic(api_key=os.environ["ANTHROPIC_API_KEY"])
    sem = asyncio.Semaphore(4)
    async def cnt(call):
        async with sem:
            for th in ({"type": "between_tools"}, None):
                try:
                    kw = dict(model="claude-sonnet-5-5", system=SYSTEM,
                              messages=[{"role": "user", "content": call["prompt"]}])
                    if th: kw["thinking"] = th
                    r = await cl.messages.count_tokens(**kw)
                    call["count_tokens"] = r.input_tokens
                    call["count_shape"] = "between_tools" if th else "no_thinking_field"
                    return
                except Exception as e:
                    call["count_err"] = f"{type(e).__name__}: {str(e)[:200]}"
    await asyncio.gather(*[cnt(c) for c in rec["calls"]])
    # live order: rows 0..132 rescore, then 2 rehome, 7 post, 1 join, 5 birth, 3 merge
    later = usage[133:]
    later_calls = [c for c in rec["calls"] if c["arm"] != "rescore"]
    for c, u in zip(later_calls, later):
        c["live_input_tokens"] = u["i"]; c["live_output_tokens"] = u["o"]; c["live_t"] = u["t"]
    rs_live = sorted(u["i"] for u in usage[:133])
    rs_rec = sorted(c.get("count_tokens", -1) for c in rec["calls"] if c["arm"] == "rescore")
    from collections import Counter
    lv, rc = Counter(rs_live), Counter(rs_rec)
    exact = sum((lv & rc).values())
    rec["fidelity"] = {"rescore_exact_multiset_matches": exact, "rescore_n": 133,
                       "rescore_live_sum": sum(rs_live), "rescore_rebuilt_sum": sum(rs_rec),
                       "later": [(c["arm"], c["theme"][:50], c.get("count_tokens"), c.get("live_input_tokens")) for c in later_calls],
                       "shape": Counter(c.get("count_shape") for c in rec["calls"]),
                       "errors": [c.get("count_err") for c in rec["calls"] if c.get("count_err")][:3]}
    json.dump(rec, open("/tmp/693_recon.json", "w"), indent=1, default=str)
    print(json.dumps(rec["fidelity"], indent=1, default=str))
    # list rescore rebuilt counts not found in live
    print("rescore unmatched rebuilt:", sorted((rc - lv).elements())[:40])
    print("rescore unmatched live:   ", sorted((lv - rc).elements())[:40])
asyncio.run(main())
