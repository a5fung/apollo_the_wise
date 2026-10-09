"""#693 replay — STEP 4 ($0): compare per member: live (thinking cut, 10-05) vs replay thinking ON,
with the replay thinking-CUT control arm on the same rebuilt inputs. Reads the captured files only."""
import json, collections
rec = json.load(open("693_recon.json"))
rows = [json.loads(l) for l in open("693_replay.jsonl")]
by = {(r["idx"], r["arm"]): r for r in rows}
calls = rec["calls"]
out = {"per_member": [], "summary": {}}
pairs = collections.Counter()      # (live, on) on would_remove
pairs_flag = collections.Counter() # (live, on) on flagged
ctrl = collections.Counter()       # (live, cut)
oncut = collections.Counter()      # (on, cut)
members = 0
think_blocks = collections.Counter()
outtok = {"on": [], "cut": []}
for i, c in enumerate(calls):
    on, cut = by[(i, "on")], by[(i, "cut")]
    for a, r in (("on", on), ("cut", cut)):
        outtok[a].append(r["usage"]["output"])
        think_blocks[(a, "thinking" in (r.get("blocks") or []))] += 1
    live = set(c["live_removed"])
    for tk in c["tickers"]:
        members += 1
        L = tk in live
        O = tk in set(on.get("would_remove") or [])
        Of = tk in set(on.get("flagged") or [])
        C = tk in set(cut.get("would_remove") or [])
        pairs[(L, O)] += 1; pairs_flag[(L, Of)] += 1; ctrl[(L, C)] += 1; oncut[(O, C)] += 1
        if L or O or C or Of:
            out["per_member"].append({"call": i, "arm": c["arm"], "theme": c["theme"], "ticker": tk,
                "live": L, "on_removed": O, "on_flagged": Of, "on_guard": on.get("guard"),
                "cut_control_removed": C, "desc_changed_since_1005": tk in c["desc_changed_since"],
                "on_raw": on.get("raw_text"), "cut_raw": cut.get("raw_text")})
def tab(cn):
    return {"both": cn[(True, True)], "only_first": cn[(True, False)], "only_second": cn[(False, True)], "neither": cn[(False, False)]}
out["summary"] = {
    "calls": len(calls), "members_judged": members,
    "live_vs_on_removed": tab(pairs), "live_vs_on_flagged": tab(pairs_flag),
    "live_vs_cut_control": tab(ctrl), "on_vs_cut_control": tab(oncut),
    "removed_totals": {"live": sum(len(c["live_removed"]) for c in calls),
                       "on": sum(len(by[(i,'on')].get("would_remove") or []) for i in range(len(calls))),
                       "on_flagged": sum(len(by[(i,'on')].get("flagged") or []) for i in range(len(calls))),
                       "cut_control": sum(len(by[(i,'cut')].get("would_remove") or []) for i in range(len(calls)))},
    "thinking_block_present": {f"{a}:{t}": n for (a, t), n in think_blocks.items()},
    "output_tokens": {a: {"sum": sum(v), "avg": round(sum(v)/len(v), 1), "max": max(v),
                          "calls_over_50": sum(1 for x in v if x > 50)} for a, v in outtok.items()},
    "errors": [r for r in rows if r.get("error") or r.get("parse_error")],
    "stop_reasons": collections.Counter(f'{r["arm"]}:{r.get("stop_reason")}' for r in rows),
    "guards_hit": [(r["arm"], r["theme"], r.get("flagged"), r.get("guard")) for r in rows if r.get("guard") not in (None, "applied", "none flagged")],
}
json.dump(out, open("compare_out.json", "w"), indent=1, default=str)
print(json.dumps(out["summary"], indent=1, default=str))
print()
for m in out["per_member"]:
    tag = ("LIVE " if m["live"] else "     ") + ("ON " if m["on_removed"] else ("on-flag " if m["on_flagged"] else "   ")) + ("CUT" if m["cut_control_removed"] else "   ")
    print(f'{tag:16} {m["arm"]:15} {m["ticker"]:6} {m["theme"][:70]}  {"(desc changed)" if m["desc_changed_since_1005"] else ""} {m["on_guard"] if m["on_flagged"] and not m["on_removed"] else ""}')
