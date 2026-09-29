import asyncio, base64, json, sys, time, types, copy
from collections import Counter
from unittest.mock import AsyncMock
PAYLOAD = json.loads(base64.b64decode(PAYLOAD_B64))
from agents.market_intelligence import db as _db, briefing as _brief, spend_tracker as _st
_db.log_audit_event = AsyncMock(); _brief.send_telegram_message = AsyncMock(); _st.log_anthropic_call_safe = AsyncMock()
from agents.market_intelligence import theme_engine as te_old
te_old.log_audit_event = AsyncMock()
def load(name, path, alias=None):
    mod = types.ModuleType(alias or name); mod.__file__ = path; mod.__package__ = name.rsplit(".", 1)[0]
    sys.modules[alias or name] = mod
    exec(compile(base64.b64decode(PAYLOAD[name]).decode(), path, "exec"), mod.__dict__)
    return mod
lc = load("shared.llm_client", "/app/shared/llm_client.py")
load("shared.output_ceilings", "/app/shared/output_ceilings.py")
load("shared.llm_thinking", "/app/shared/llm_thinking.py")
te_new = load("agents.market_intelligence.theme_engine", "/app/agents/market_intelligence/theme_engine.py", alias="te_new_mod")
te_new.log_audit_event = AsyncMock()
te_old.THEME_MODEL = "claude-sonnet-5"; te_new.THEME_MODEL = "claude-sonnet-5-5"
from shared.dates import et_today
SEM = asyncio.Semaphore(6)
client = lc.make_async_anthropic()

async def fit(te, row, themes, stock):
    async with SEM:
        t0 = time.monotonic()
        try:
            st, th, why = await te.judge_theme_fit(row["ticker"], description=stock["description"], sector=stock["sector"],
                                                   themes=themes, client=client)
        except Exception as e:
            st, th, why = "ERROR", None, f"{type(e).__name__}: {str(e)[:80]}"
        return {"status": st, "theme": th, "why": (why or "")[:160], "secs": round(time.monotonic() - t0, 1)}

async def main():
    pool = await _db.get_pool()
    async with pool.acquire() as c:
        rows = [dict(r) for r in await c.fetch(
            "SELECT DISTINCT ON (ticker, scan_date) ticker, scan_date, shortlist, fit_status, fit_theme FROM mi_ep_theme_belonging_shadow "
            "WHERE shortlist IS NOT NULL AND shortlist <> '[]' AND fit_status IN ('rejected','confirmed','window') "
            "ORDER BY ticker, scan_date DESC")]
        descs = await _db.get_descriptions_batch(list({r["ticker"] for r in rows}))
        sect = {}
        if hasattr(_db, "get_sectors_batch"):
            try: sect = await _db.get_sectors_batch(list({r["ticker"] for r in rows}))
            except Exception: sect = {}
        cases = []
        for r in rows:
            names = [x["theme"] for x in json.loads(r["shortlist"])]
            th = [dict(x) for x in await c.fetch("SELECT DISTINCT ON (name) name, tickers, description, stage FROM mi_themes "
                  "WHERE name = ANY($1) AND theme_date <= $2 ORDER BY name, theme_date DESC", names, r["scan_date"])]
            if not th: continue
            cases.append((r, th, {"ticker": r["ticker"], "sector": sect.get(r["ticker"]) or "Unknown",
                                  "description": (descs.get(r["ticker"]) or "")[:300]}))
    print(f"POPULATION ep-fit cases {len(cases)} (stored: {dict(Counter(r['fit_status'] for r, _, _ in cases))}), "
          f"dates {min(r['scan_date'] for r,_,_ in cases)}..{max(r['scan_date'] for r,_,_ in cases)}, "
          f"no description {sum(1 for _,_,s in cases if not s['description'])}")
    jobs = []
    for r, th, s in cases:
        jobs += [fit(te_old, r, th, s), fit(te_old, r, th, s), fit(te_new, r, th, s), fit(te_new, r, th, s)]
    res = await asyncio.gather(*jobs)
    out = []
    for i, (r, th, s) in enumerate(cases):
        o1, o2, n1, n2 = res[4 * i: 4 * i + 4]
        out.append({"ticker": r["ticker"], "date": str(r["scan_date"]), "stored": r["fit_status"], "stored_theme": r["fit_theme"],
                    "offered": [t["name"] for t in th], "old1": o1, "old2": o2, "new1": n1, "new2": n2})
    v = lambda x: (x["status"], x["theme"])
    agree = lambda a, b: sum(1 for x in out if v(x[a]) == v(x[b]))
    n = len(out)
    print(f"EP FIT AGREEMENT (n={n}): old-vs-old {agree('old1','old2')}/{n} | new-vs-new {agree('new1','new2')}/{n} | "
          f"old1-vs-new1 {agree('old1','new1')}/{n} | old2-vs-new2 {agree('old2','new2')}/{n}")
    for k in ("old1", "old2", "new1", "new2"):
        c = Counter(x[k]["status"] for x in out); secs = sorted(x[k]["secs"] for x in out)
        print(f"  {k}: {dict(c)} | seconds p50 {secs[len(secs)//2]} max {secs[-1]}")
    stored_judged = [x for x in out if x["stored"] in ("rejected", "confirmed")]
    print(f"  vs STORED verdict (n={len(stored_judged)} judged): old1 {sum(1 for x in stored_judged if x['old1']['status']==x['stored'])} | "
          f"new1 {sum(1 for x in stored_judged if x['new1']['status']==x['stored'])}")
    for x in out:
        if len({v(x[k]) for k in ("old1", "old2", "new1", "new2")}) > 1:
            print(f"  DIFF {x['ticker']} {x['date']} stored={x['stored']} | old1={v(x['old1'])} old2={v(x['old2'])} new1={v(x['new1'])} new2={v(x['new2'])}")
            print(f"       old why: {x['old1']['why'][:120]} | new why: {x['new1']['why'][:120]}")
    json.dump(out, open("/tmp/compare_epfit.json", "w"), default=str)

    # nightly assignment: 3 real batches, today's board
    themes = await _db.get_active_themes()
    leaders = await _db.get_rs_leaders(et_today().strftime("%Y-%m-%d"), limit=200)
    covered = {tk for t in themes for tk in (t.get("tickers") or [])}
    unc = [s for s in leaders if s["ticker"] not in covered]
    batches = [unc[i:i + 12] for i in (0, 12, 24)]
    async def batch(te, b, k):
        async with SEM:
            try:
                props = await te._propose_assignment_batch(client, b, shared_prefix=te.assignment_shared_prefix(themes),
                        cooldown_note="", advisor_state={"calls": 0}, batch_no=k, n_batches=3, pool_size=len(unc))
                return sorted((p.get("ticker"), te._strip_stage_label(p.get("theme") or "")) for p in (props or []))
            except Exception as e:
                return [("ERROR", f"{type(e).__name__}: {str(e)[:60]}")]
    jobs = []
    for k, b in enumerate(batches, 1):
        jobs += [batch(te_old, b, k), batch(te_old, b, k), batch(te_new, b, k), batch(te_new, b, k)]
    res = await asyncio.gather(*jobs)
    for k in range(3):
        o1, o2, n1, n2 = res[4 * k: 4 * k + 4]
        print(f"ASSIGN batch{k+1} ({len(batches[k])} stocks): old1 {o1} | old2 {o2} | new1 {n1} | new2 {n2}")
    # discovery: 2 batches, themes found
    by_t = {s["ticker"]: s for s in leaders}
    async def disc(te, b):
        async with SEM:
            try:
                th = await te._discover_new_themes_single(b, themes, by_t)
                return [(t.get("name"), sorted(t.get("tickers") or [])) for t in (th or [])]
            except Exception as e:
                return [("ERROR", str(e)[:60])]
    res = await asyncio.gather(*[disc(te_old, batches[0]), disc(te_new, batches[0]), disc(te_old, batches[1]), disc(te_new, batches[1])])
    print(f"DISCOVERY batch1: old {res[0]} | new {res[1]}")
    print(f"DISCOVERY batch2: old {res[2]} | new {res[3]}")
asyncio.run(main())
