async def main():
    themes = await _db.get_active_themes()
    leaders = await _db.get_rs_leaders(et_today().strftime("%Y-%m-%d"), limit=200)
    by_t = {s["ticker"]: s for s in leaders}
    big = sorted(themes, key=lambda t: -len(t.get("tickers") or []))[:2]
    reqs = []
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
    kw = await capture("validation", lambda: te._validate_theme_membership(big[0]["name"], list(big[0].get("tickers") or []), [], thesis=big[0].get("description")))
    if kw: kw = copy.deepcopy(kw); kw.pop("model", None); reqs.append(("validation (unchanged)", 3, "claude-sonnet-5-5", kw))
    from datetime import date as _d
    for d in ("2026-09-25", "2026-09-24", "2026-09-23"):
        kw = await capture("lane2" + d, lambda d=d: te.discover_narrative_themes(scan_date=_d.fromisoformat(d), persist=False))
        if kw:
            kw = copy.deepcopy(kw); kw.pop("model", None); reqs.append((f"lane2 narrative {d} (unchanged)", 3, "claude-sonnet-5-5", kw)); break
    client = make_async_anthropic()
    for label, n, model, kw in reqs:
        res = Counter(); extra = []
        async def one():
            try:
                r = await client.messages.create(model=model, **kw)
                tu = [b for b in r.content if getattr(b, "type", "") == "tool_use"]
                txt = r.content[-1].text if r.content and getattr(r.content[-1], "type", "") == "text" else ""
                if tu:
                    res["answered"] += 1; extra.append(str({k: v for k, v in (tu[0].input or {}).items() if k != "reason"})[:60])
                elif txt: res["answered-text"] += 1; extra.append(txt[:60].replace(chr(10), " "))
                else: res[f"no-answer:{r.stop_reason}"] += 1
            except Exception as e:
                res["REFUSED" if "refus" in str(e) or "no text block" in str(e) else type(e).__name__] += 1; extra.append(str(e)[:100])
        await asyncio.gather(*[one() for _ in range(n)])
        print(f"{label:40s} {dict(res)} | {extra[0] if extra else ''}")
asyncio.run(main())
