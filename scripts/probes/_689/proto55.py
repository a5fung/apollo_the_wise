import asyncio, copy, json, re
from collections import Counter
from unittest.mock import AsyncMock
from agents.market_intelligence import db as _db, briefing as _brief, theme_engine as te
_db.log_audit_event = AsyncMock(); _brief.send_telegram_message = AsyncMock()
for n in ("persist_narrative_theme_candidates", "insert_theme_candidates_shadow", "persist_synthesis_theme_candidates"):
    if hasattr(_db, n): setattr(_db, n, AsyncMock())
from shared.llm_client import make_async_anthropic
from shared.dates import et_today
from agents.market_intelligence.universe import TICKER_DESC

ITEM = te._THEME_ASSIGNMENT_TOOL["input_schema"]["properties"]["assignments"]
NEW_ASSIGN = {"name": "assign_stocks_to_themes", "description": te._THEME_ASSIGNMENT_TOOL["description"],
  "input_schema": {"type": "object", "properties": {
    "assignments": ITEM,
    "no_fit": {"type": "array", "description": "Every uncovered stock NOT assigned, each with a short reason.",
               "items": {"type": "object", "properties": {"ticker": {"type": "string"},
                         "reason": {"type": "string", "description": "<=8 words: why no listed theme fits"}},
                         "required": ["ticker", "reason"]}}},
  "required": ["assignments", "no_fit"]}}
NEW_FMT = ("OUTPUT FORMAT — IMPORTANT:\nDo NOT write any free text outside the tool call. "
           "`assignments` holds only the actual fits, each with a one-sentence rationale. "
           "`no_fit` lists every other stock with a short reason (<=8 words).")
def new_body(stocks): return te._assignment_body(stocks).split("OUTPUT FORMAT", 1)[0] + NEW_FMT

DECLINED = {"type": "array", "description": "Candidate groups you did NOT report as themes, each with a short reason.",
            "items": {"type": "object", "properties": {"tickers": {"type": "array", "items": {"type": "string"}},
                      "reason": {"type": "string", "description": "<=10 words"}}, "required": ["tickers", "reason"]}}
def new_discovery_tool(t):
    t = copy.deepcopy(t); s = t["input_schema"]; s["properties"].pop("analysis_scratchpad", None)
    s["properties"]["declined"] = DECLINED
    s["required"] = [r for r in s["required"] if r != "analysis_scratchpad"] + ["declined"]
    return t
def fix_text(kw, fn):
    for m in kw["messages"]:
        if isinstance(m["content"], str): m["content"] = fn(m["content"])
        else:
            for b in m["content"]:
                if b.get("type") == "text": b["text"] = fn(b["text"])
    if isinstance(kw.get("system"), str): kw["system"] = fn(kw["system"])

class Stop(BaseException): pass
cap = {}
class Cap:
    def __init__(self, label): self.label = label; self.messages = self
    async def create(self, **kw): cap[self.label] = copy.deepcopy(kw); raise Stop()
async def capture(label, fn):
    te._get_anthropic_client = lambda: Cap(label)
    try: await fn()
    except Stop: pass
    except Exception as e: print(f"CAPTURE {label} raised {type(e).__name__}: {str(e)[:120]}")
    return cap.get(label)

async def main():
    themes = await _db.get_active_themes()
    leaders = await _db.get_rs_leaders(et_today().strftime("%Y-%m-%d"), limit=200)
    by_t = {s["ticker"]: s for s in leaders}
    covered = {tk for t in themes for tk in (t.get("tickers") or [])}
    unc = [s for s in leaders if s["ticker"] not in covered]
    print("population: themes", len(themes), "| leaders", len(leaders), "| uncovered", len(unc))
    batches = [unc[i:i + 12] for i in (0, 12, 24)]
    reqs = []
    for i, b in enumerate(batches):
        if b: reqs.append((f"assign batch{i+1} ({len(b)} stocks)", 5, "claude-sonnet-5-5", dict(max_tokens=8000, tools=[NEW_ASSIGN],
            tool_choice={"type": "tool", "name": "assign_stocks_to_themes"},
            messages=te._assignment_messages(te.assignment_shared_prefix(themes), new_body(b)))))
    reqs.append(("assign batch1 on SONNET 5, thinking on", 2, "claude-sonnet-5", dict(reqs[0][3])))
    # EP fit shape: real shadow rows, shortlist themes rebuilt from mi_themes as of scan_date
    pool = await _db.get_pool()
    async with pool.acquire() as c:
        rows = await c.fetch("SELECT DISTINCT ON (ticker) ticker, scan_date, shortlist FROM mi_ep_theme_belonging_shadow "
                             "WHERE fit_status IN ('rejected','confirmed') AND shortlist IS NOT NULL ORDER BY ticker, scan_date DESC LIMIT 3")
        for r in rows:
            names = [x["theme"] for x in json.loads(r["shortlist"])]
            th = [dict(x) for x in await c.fetch("SELECT DISTINCT ON (name) name, tickers, description, stage FROM mi_themes "
                  "WHERE name = ANY($1) AND theme_date <= $2 ORDER BY name, theme_date DESC", names, r["scan_date"])]
            stock = {"ticker": r["ticker"], "sector": (by_t.get(r["ticker"]) or {}).get("sector", "Unknown"),
                     "description": TICKER_DESC.get(r["ticker"], "")}
            reqs.append((f"EP fit {r['ticker']} ({len(th)} themes)", 5, "claude-sonnet-5-5", dict(max_tokens=2000, tools=[NEW_ASSIGN],
                tool_choice={"type": "tool", "name": "assign_stocks_to_themes"},
                messages=te._assignment_messages(te.assignment_shared_prefix(th), new_body([stock])))))
    # discovery with `declined` on two batches
    for i, b in enumerate(batches[:2]):
        kw = await capture(f"disc{i}", lambda b=b: te._discover_new_themes_single(b, themes, by_t))
        if not kw: continue
        kw = copy.deepcopy(kw); kw.pop("model", None)
        kw["tools"] = [new_discovery_tool(t) if t["name"] == "report_themes" else t for t in kw["tools"]]
        fix_text(kw, lambda s: s.replace(", with your terse reasoning in `analysis_scratchpad`.", ".") and re.sub(
            r"OUTPUT FORMAT — IMPORTANT:\n.*?\n\n", "OUTPUT FORMAT — IMPORTANT:\nDo NOT write any free text outside the tool call. "
            "Report each theme in `themes`; list each candidate group you did not report in `declined` with a short reason "
            "(<=10 words).\n\n", s.replace(", with your terse reasoning in `analysis_scratchpad`.", "."), flags=re.S))
        left = sum(json.dumps(m).count("analysis_scratchpad") for m in kw["messages"])
        reqs.append((f"discovery batch{i+1} (pad refs left {left})", 4, "claude-sonnet-5-5", kw))
    big = sorted(themes, key=lambda t: -len(t.get("tickers") or []))[:2]
    for j, bt in enumerate(big):
        kw = await capture(f"split{j}", lambda bt=bt: te._split_fat_theme(bt, by_t, 0))
        if not kw: continue
        kw = copy.deepcopy(kw); kw.pop("model", None); kw.pop("thinking", None)
        for t in kw["tools"]:
            if t["name"] == "propose_split":
                s = t["input_schema"]; s["properties"].pop("analysis_scratchpad", None)
                s["properties"]["reason"] = {"type": "string", "description": "One line (<=15 words): why this carve, or why none."}
                s["required"] = [r for r in s["required"] if r != "analysis_scratchpad"] + ["reason"]
        fix_text(kw, lambda s: re.sub(r"OUTPUT FORMAT — IMPORTANT:\n.*\Z", "OUTPUT FORMAT — IMPORTANT:\nDo NOT write any free text "
            "outside the tool call. Put the carve (or null) in `split` and a one-line reason in `reason`.", s, flags=re.S))
        reqs.append((f"split {bt['name'][:28]}", 3, "claude-sonnet-5-5", kw))
    kw = await capture("rename", lambda: te._rename_theme_to_fit_cluster(big[0]["name"], list(big[0].get("tickers") or [])[:10],
                                                                    big[0].get("description"), list(big[0].get("tickers") or [])[:2]))
    if kw:
        kw = copy.deepcopy(kw); kw.pop("model", None); kw.pop("thinking", None)
        kw["tools"] = [new_discovery_tool(t) if t["name"] == "report_themes" else t for t in kw["tools"]]
        fix_text(kw, lambda s: s.replace("Do NOT write any free text before the tool call — all reasoning goes in\n`analysis_scratchpad`, kept to one terse line.",
                                         "Do NOT write any free text outside the tool call."))
        reqs.append(("rename", 3, "claude-sonnet-5-5", kw))
    kw = await capture("validation", lambda: te._validate_theme_membership(big[0]["name"], list(big[0].get("tickers") or []), [], thesis=big[0].get("description")))
    if kw: kw = copy.deepcopy(kw); kw.pop("model", None); reqs.append(("validation (unchanged)", 3, "claude-sonnet-5-5", kw))
    kw = await capture("lane2", lambda: te.discover_narrative_themes(persist=False))
    if kw: kw = copy.deepcopy(kw); kw.pop("model", None); reqs.append(("lane2 narrative (unchanged)", 3, "claude-sonnet-5-5", kw))

    client = make_async_anthropic()
    for label, n, model, kw in reqs:
        res = Counter(); outs = []; extra = []
        async def one():
            try:
                r = await client.messages.create(model=model, **kw)
                tu = [b for b in r.content if getattr(b, "type", "") == "tool_use"]
                if tu:
                    res["answered"] += 1; inp = tu[0].input or {}
                    if "no_fit" in inp: extra.append(f"fit{len(inp.get('assignments') or [])}/nofit{len(inp.get('no_fit') or [])}")
                    if "declined" in inp: extra.append(f"th{len(inp.get('themes') or [])}/dec{len(inp.get('declined') or [])}")
                elif r.stop_reason == "end_turn" and getattr(r.content[-1], "type", "") == "text":
                    res["answered-text"] += 1
                else: res[f"no-tool:{r.stop_reason}"] += 1
                outs.append(r.usage.output_tokens)
            except Exception as e:
                res["REFUSED" if "refus" in str(e) or "no text block" in str(e) else type(e).__name__] += 1
        await asyncio.gather(*[one() for _ in range(n)])
        print(f"{label:44s} {model:18s} {dict(res)} out~{sum(outs)//max(len(outs),1)} {' '.join(extra[:5])}")
asyncio.run(main())
