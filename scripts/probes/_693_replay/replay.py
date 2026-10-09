"""#693 replay — STEP 3, THE ONE PAID RUN. Read-only: calls the model and parses; never calls the
code that applies removals, never writes a production table (no spend-log row, no audit row, no
llm_samples capture).

For each of the 151 rebuilt 10-05 validator requests, two arms in the same run, interleaved:
  * "on"  — thinking ON: no `thinking` field (adaptive on claude-sonnet-5-5), max_tokens =
            thinking_headroom(1000) = 2024, exactly what the validator ran with 09-29..10-02;
  * "cut" — thinking cut: thinking={"type": "between_tools"}, max_tokens 1000, exactly what the
            live 10-05 run sent. A control on the SAME rebuilt inputs, so a difference vs "on"
            is not rebuild drift.
Through the production client factory (shared.llm_client.make_async_anthropic). Every raw response
+ parsed verdict is written to /tmp/693_replay.jsonl as it arrives.
"""
import asyncio, json, os, time, random

import anthropic
from shared.llm_client import make_async_anthropic, thinking_headroom
from shared.llm_samples import capture_disabled
from shared.llm_response import content_block_types, first_text
from shared.llm_models import pricing_for
from agents.market_intelligence.theme_engine import _extract_json_object, _is_mass_eviction, PRUNE_MIN_TICKERS

MODEL = "claude-sonnet-5-5"
SYSTEM = "You are a JSON API. Respond with valid JSON only. No prose, no markdown, no explanation."
OUT = "/tmp/693_replay.jsonl"
SPACING_S = 2.5          # ~24 requests/minute, well under the org limit, leaves room for live jobs
ARMS = {
    "on": dict(max_tokens=thinking_headroom(1000)),
    "cut": dict(max_tokens=1000, thinking={"type": "between_tools"}),
}


def parse(resp):
    raw = (first_text(resp) or "").strip()
    if not raw:
        return None, raw, f"no text (stop={resp.stop_reason}, blocks={content_block_types(resp)})"
    t = raw
    if t.startswith("```"):
        parts = t.split("\n", 1)
        t = parts[1].rstrip("` \n").strip() if len(parts) > 1 else t.strip("` ")
    try:
        result = json.loads(_extract_json_object(t))
        return sorted({x.upper() for x in (result.get("remove") or []) if isinstance(x, str)}), raw, None
    except Exception as e:
        return None, raw, f"{type(e).__name__}: {e}"


def applied(call, flagged):
    """What the validator would have REMOVED from this verdict (the guards after the model call;
    no operator-protection rows fired on 10-05). Rescore passes mass_flag_out and the Arm-A
    dissolve flag (both live that night); merge passes dissolve_flagged_pair=True."""
    tks = call["tickers"]
    fl = [x for x in flagged if x in tks]
    if not fl:
        return [], "none flagged"
    if call["arm"] == "rescore" and _is_mass_eviction(len(fl), len(tks)):
        return [], "mass-eviction signature: removals skipped, theme renamed"
    survivors = [x for x in tks if x not in fl]
    dissolve = call["arm"] in ("rescore", "merge")
    if len(survivors) < PRUNE_MIN_TICKERS and not (dissolve and len(tks) == 2):
        return [], "min-survivor guard: removals skipped"
    return fl, "applied"


async def main():
    rec = json.load(open("/tmp/693_recon.json"))
    calls = rec["calls"]
    price = pricing_for(MODEL)
    client = make_async_anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])
    jobs = [(i, arm) for i in range(len(calls)) for arm in ("on", "cut")]
    random.Random(693).shuffle(jobs)          # interleave arms over the run's wall-clock
    sem = asyncio.Semaphore(3)
    fh = open(OUT, "w")
    totals = {a: {"in": 0, "out": 0, "usd": 0.0, "n": 0, "errors": 0} for a in ARMS}

    async def one(k, i, arm):
        await asyncio.sleep(k * SPACING_S)
        call = calls[i]
        kw = dict(model=MODEL, system=SYSTEM, messages=[{"role": "user", "content": call["prompt"]}], **ARMS[arm])
        row = {"idx": i, "arm": arm, "call_arm": call["arm"], "theme": call["theme"], "tickers": call["tickers"],
               "live_removed": call["live_removed"], "request_max_tokens": kw["max_tokens"],
               "request_thinking": kw.get("thinking")}
        async with sem:
            for attempt in range(4):
                try:
                    t0 = time.time()
                    resp = await client.messages.create(**kw)
                    row["latency_s"] = round(time.time() - t0, 2)
                    break
                except anthropic.RateLimitError as e:
                    row.setdefault("rate_limited", 0); row["rate_limited"] += 1
                    await asyncio.sleep(30 + 15 * attempt)
                except Exception as e:
                    row["error"] = f"{type(e).__name__}: {str(e)[:300]}"
                    resp = None
                    break
            else:
                resp = None
                row["error"] = row.get("error") or "rate-limited 4x"
        if resp is not None:
            u = resp.usage
            row["usage"] = {"input": u.input_tokens, "output": u.output_tokens}
            row["usd"] = u.input_tokens * price["input"] / 1e6 + u.output_tokens * price["output"] / 1e6
            row["stop_reason"] = resp.stop_reason
            row["blocks"] = content_block_types(resp)
            row["raw_content"] = [b.model_dump() if hasattr(b, "model_dump") else str(b) for b in resp.content]
            flagged, raw, err = parse(resp)
            row["raw_text"] = raw
            row["flagged"] = flagged
            row["parse_error"] = err
            if flagged is not None:
                row["would_remove"], row["guard"] = applied(call, flagged)
            t = totals[arm]
            t["in"] += u.input_tokens; t["out"] += u.output_tokens; t["usd"] += row["usd"]; t["n"] += 1
        else:
            totals[arm]["errors"] += 1
        fh.write(json.dumps(row, default=str) + "\n"); fh.flush()

    with capture_disabled():
        await asyncio.gather(*[one(k, i, arm) for k, (i, arm) in enumerate(jobs)])
    fh.close()
    json.dump({"totals": totals, "price_per_mtok": price, "model": MODEL, "arms": {a: {k: v for k, v in d.items()} for a, d in ARMS.items()},
               "n_calls": len(calls), "finished": time.strftime("%Y-%m-%d %H:%M:%S %Z")},
              open("/tmp/693_replay_totals.json", "w"), indent=1)
    print(json.dumps(totals, indent=1))

asyncio.run(main())
