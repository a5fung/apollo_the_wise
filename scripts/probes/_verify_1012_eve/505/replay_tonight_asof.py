# READ-ONLY offline replay of tonight's (2026-10-12) parent-pass pick against the exported 17:10 ET board.
# Inputs are SELECT exports (themes_1012.tsv, eco.tsv, cooldowns.tsv [pre-pass], industries.tsv, sectors.tsv).
import sys, os, json
sys.path.insert(0, "/Users/alvinfung/apollo_the_wise")
from agents.market_intelligence.theme_engine import propose_parent_candidates
from agents.market_intelligence.theme_merge_arm import propose_merge_pairs, pair_key

def rows(f): return [l.rstrip("\n").split("\t") for l in open(f, encoding="utf-8") if l.strip()]
themes = []
for r in rows("themes_1012.tsv"):
    name, stage, source, parent, tk, desc = (r + [""] * 6)[:6]
    themes.append({"name": name, "stage": stage, "source": source, "parent_theme": parent or None,
                   "tickers": [t for t in tk.split(",") if t], "description": desc})
eco = {r[0]: r[1] for r in rows("eco_t.tsv") if r[2] < "2026-10-12 21:10:48"}  # only the mappings that EXISTED when the pass ran (UTC)
cool = {pair_key(r[0], r[1]) for r in rows("cooldowns.tsv")}
ind = {r[0]: r[1] for r in rows("industries.tsv") if len(r) > 1}
sec = {r[0]: r[1] for r in rows("sectors.tsv") if len(r) > 1}
live = [t for t in themes if t["stage"] != "Retired" and t["tickers"]]
print("board rows", len(themes), "| live non-Retired with members", len(live),
      "| non-Retired non-Fading", sum(1 for t in live if t["stage"] != "Fading"))
armb = {pair_key(a["name"], o["name"]) for a, o in propose_merge_pairs(live, cooldown_pairs=cool, sectors_by_ticker=sec, max_pairs=None)}
print("cooldown pairs (pre-pass)", len(cool), "| arm_b pairs (approx, override-table sectors)", len(armb))

def show(tag, c):
    print(f"\n== {tag}: {len(c)} ask(s)")
    for i, x in enumerate(c, 1):
        print(f" {i}. [{x['child_source']}] '{x['child']}' ({x['child_members']}) -> '{x['parent']}' ({x['parent_members']}) {x['e_code']} "
              f"sh_tk={x['shared_tickers']} ind={x.get('industry_overlap')} wsim={x.get('word_similarity')}")

new_capped = propose_parent_candidates(themes, eco, cooldown_pairs=cool, arm_b_pairs=armb, cap=6, industry_by_ticker=ind)
show("NEW closeness pick, cap 6 (compare with the 6 actual asks)", new_capped)
new_all = propose_parent_candidates(themes, eco, cooldown_pairs=cool, arm_b_pairs=armb, cap=None, industry_by_ticker=ind)
print(f"\nNEW pick whole queue (uncapped): {len(new_all)} childless themes with an eligible parent tonight; by child source:",
      {s: sum(1 for x in new_all if x['child_source'] == s) for s in sorted({x['child_source'] for x in new_all})})
print("   ask-able overlap/shared distribution: shared>=1:", sum(1 for x in new_all if x['shared_tickers'] >= 1),
      "| overlap>=0.5 and no shared:", sum(1 for x in new_all if x['shared_tickers'] == 0 and (x['industry_overlap'] or 0) >= 0.5),
      "| BELOW minimum (must be 0):", sum(1 for x in new_all if x['shared_tickers'] == 0 and (x['industry_overlap'] or 0) < 0.5))
print("   asks by ecosystem:", {e: sum(1 for x in new_all if x['e_code'] == e) for e in sorted({x['e_code'] for x in new_all})})
old_capped = propose_parent_candidates(themes, eco, cooldown_pairs=cool, arm_b_pairs=armb, cap=6, industry_by_ticker=None)
show("OLD size-ordered pick (pre-10-09 behaviour), cap 6", old_capped)
old_all = propose_parent_candidates(themes, eco, cooldown_pairs=cool, arm_b_pairs=armb, cap=None, industry_by_ticker=None)
print(f"\nOLD pick whole queue: {len(old_all)}; asks that would sit under the minimum (no shared stock, overlap<0.5):")
from agents.market_intelligence.theme_engine import parent_industry_overlap
by = {t['name']: t for t in themes}
under = [x for x in old_all if x['shared_tickers'] == 0 and parent_industry_overlap(by[x['child']], by[x['parent']], ind) < 0.5]
print("   ", len(under), "of", len(old_all))
# first-ask difference: how many children get a DIFFERENT first parent under the new pick vs the old
oldmap = {x['child']: x['parent'] for x in old_all}; newmap = {x['child']: x['parent'] for x in new_all}
both = set(oldmap) & set(newmap)
print("children asked under both:", len(both), "| different first parent:", sum(1 for c in both if oldmap[c] != newmap[c]),
      "| children only the old pick would ask (new pick: under the minimum / none):", len(set(oldmap) - set(newmap)))
# tonight's 6 children: what would the old pick have asked instead?
actual = ["Vertical Commerce & Tax/Payments Software-Fintech Platforms", "Cloud Data Storage & Analytics Infrastructure",
          "Cloud Supply Chain & Warehouse Management Software", "Cloud Financial Automation & Insurance Core Platform Software",
          "AI Server Power & Signal-Integrity Analog ICs", "Exchange, Options Trading & Alternative Consumer Credit Financials"]
print("\ntonight's 6 children - old pick vs new pick:")
for c in actual:
    print(f" - {c[:60]!r}: old -> {oldmap.get(c)!r} | new -> {newmap.get(c)!r}")

print("\nOLD pick's own top 6 - industry overlap of each (minimum is 0.50 unless a stock is shared):")
for x in old_capped:
    ov = parent_industry_overlap(by[x['child']], by[x['parent']], ind)
    print(f"   overlap {ov:.2f} shared {x['shared_tickers']} | {x['child'][:55]!r} -> {x['parent'][:45]!r}", "  <-- BELOW MINIMUM" if (x['shared_tickers']==0 and ov<0.5) else "")
