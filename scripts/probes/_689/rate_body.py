import asyncio, base64, json, sys, types, copy
from collections import Counter
from unittest.mock import AsyncMock
PAYLOAD = json.loads(base64.b64decode(PAYLOAD_B64))
def load(name, path):
    mod = types.ModuleType(name); mod.__file__ = path; mod.__package__ = name.rsplit(".", 1)[0]
    sys.modules[name] = mod
    exec(compile(base64.b64decode(PAYLOAD[name]).decode(), path, "exec"), mod.__dict__)
    pkg = sys.modules[mod.__package__]; setattr(pkg, name.rsplit(".", 1)[1], mod)
    return mod
import shared, agents.market_intelligence
lc = load("shared.llm_client", "/app/shared/llm_client.py")
from agents.market_intelligence import db as _db, briefing as _brief
_db.log_audit_event = AsyncMock(); _db.persist_synthesis_theme_candidates = AsyncMock(); _brief.send_telegram_message = AsyncMock()
M = "agents.market_intelligence."
tma = load(M+"theme_merge_arm", "/app/agents/market_intelligence/theme_merge_arm.py")
te = load(M+"theme_engine", "/app/agents/market_intelligence/theme_engine.py")
tecos = load(M+"theme_ecosystems", "/app/agents/market_intelligence/theme_ecosystems.py")
ts = load(M+"theme_synthesis", "/app/agents/market_intelligence/theme_synthesis.py")
ed = load(M+"ecosystem_discovery", "/app/agents/market_intelligence/ecosystem_discovery.py")
class Stop(BaseException): pass
captured = {}
class Cap:
    def __init__(self, label): self.label = label; self.messages = self
    async def create(self, **kw): captured[self.label] = copy.deepcopy(kw); raise Stop()
async def capture(label, fn):
    te._get_anthropic_client = lambda: Cap(label)
    try: await fn()
    except Stop: pass
    except Exception as e: print(f"CAPTURE {label} raised {type(e).__name__}: {str(e)[:120]}")

async def main():
    from shared.dates import et_today
    themes = await _db.get_active_themes()
    leaders = await _db.get_rs_leaders(et_today().strftime("%Y-%m-%d"), limit=40)
    by_t = {s["ticker"]: s for s in leaders}
    big = max(themes, key=lambda t: len(t.get("tickers") or []))
    pair = {t["name"]: t for t in themes}
    nm = ["Cloud Data Storage & Analytics Infrastructure", "Cloud Application Delivery & Observability Infrastructure"]
    a, b = (pair[nm[0]], pair[nm[1]]) if all(n in pair for n in nm) else (themes[0], themes[1])
    unc = [s for s in leaders if not any(s["ticker"] in (t.get("tickers") or []) for t in themes)][:12]
    reqs = {}
    reqs["containment"] = (5, dict(max_tokens=1000, thinking={"type": "disabled"}, tools=[tma.CONTAINMENT_ADJUDICATION_TOOL],
        tool_choice={"type": "tool", "name": tma.CONTAINMENT_ADJUDICATION_TOOL["name"]},
        messages=[{"role": "user", "content": tma.build_containment_prompt(a, b, {})}]))
    reqs["merge"] = (2, dict(max_tokens=1000, tools=[tma.MERGE_ADJUDICATION_TOOL],
        tool_choice={"type": "tool", "name": tma.MERGE_ADJUDICATION_TOOL["name"]},
        messages=[{"role": "user", "content": tma.build_adjudication_prompt(a, b, {})}]))
    tool = copy.deepcopy(te._THEME_ASSIGNMENT_TOOL)
    tool["input_schema"]["properties"]["analysis_scratchpad"]["description"] = (
        "REQUIRED. Brief notes, one short line per uncovered stock: its core business, "
        "the candidate theme(s), whether it fits, and the decision.")
    body = te._assignment_body(unc)
    body = body.split("OUTPUT FORMAT", 1)[0] + ("OUTPUT FORMAT — IMPORTANT:\nDo NOT write any free text outside the tool call. "
                                                "The `assignments` array contains only the actual fits.")
    reqs["assignment_NO_NOTES_INSTRUCTION"] = (5, dict(max_tokens=4000, tools=[tool],
        tool_choice={"type": "tool", "name": tool["name"]}, messages=te._assignment_messages(te.assignment_shared_prefix(themes), body)))
    from agents.market_intelligence.theme_ecosystems import get_ecosystems
    ecos = get_ecosystems()
    await capture("discovery", lambda: te._discover_new_themes_single(unc, themes, by_t))
    await capture("split", lambda: te._split_fat_theme(big, by_t, 0))
    await capture("rename", lambda: te._rename_theme_to_fit_cluster(big["name"], list(big.get("tickers") or [])[:10], big.get("description"), list(big.get("tickers") or [])[:2]))
    await capture("synthesis", lambda: ts.run_theme_synthesis())
    await capture("ecosystem_assign", lambda: tecos._assign_via_haiku(big, ecos, {}))
    await capture("ecosystem_propose", lambda: ed.propose_ecosystem_via_llm(themes[:4], ecos))
    reps = {"discovery": 3, "split": 3, "rename": 3, "synthesis": 5, "ecosystem_assign": 2, "ecosystem_propose": 5}
    for k, kw in captured.items():
        kw.pop("model", None); reqs[k] = (reps.get(k, 3), kw)
    client = lc.make_async_anthropic()
    for label, (n, kw) in reqs.items():
        res = Counter(); notes = []
        async def one():
            try:
                r = await client.messages.create(model="claude-sonnet-5-5", **kw)
                tu = [bl for bl in r.content if getattr(bl, "type", "") == "tool_use"]
                res["answered" if tu else f"no-tool:{r.stop_reason}"] += 1
            except Exception as e:
                m = str(e); key = "REFUSED" if "refus" in m or "no text block" in m else f"{type(e).__name__}"
                res[key] += 1; notes.append(m[:110])
        await asyncio.gather(*[one() for _ in range(n)])
        print(f"{label:34s} {dict(res)}" + (f"  e.g. {notes[0]}" if notes else ""))
asyncio.run(main())
