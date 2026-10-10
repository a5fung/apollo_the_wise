"""#655 scope Q-A step 1: G3 fails by theme size over the last 10 nightly rows (stored verdicts). $0."""
from collections import Counter
from load import load
b = load()
rows = [r for r in b["correctness"] if r["et"][11:16] == "17:31"][-10:]
tot = Counter()
print("night | judged | pass | G3% | fails: size2 size3 size4+ | judged by size 2/3/4+ | pass-rate on 4+ only | G4 signed / settled")
for r in rows:
    th = [t for t in r["detail"]["g3"]["themes"] if t["cohesion"] is not None]
    f = [t for t in th if not t["pass_g3"]]
    c = Counter(min(t["size"], 4) for t in f)
    j = Counter(min(t["size"], 4) for t in th)
    big = [t for t in th if t["size"] >= 4]
    bigp = sum(t["pass_g3"] for t in big)
    g4 = r["detail"]["g4"]
    print(f"{r['et'][:10]} | {len(th)} | {len(th)-len(f)} | {100*(len(th)-len(f))/len(th):.1f} | "
          f"{c[2]} {c[3]} {c[4]} | {j[2]}/{j[3]}/{j[4]} | {bigp}/{len(big)} = {100*bigp/len(big):.1f}% | "
          f"{g4['small']}/{g4['n_board']} {g4['rate_pct']}% / " + (f"{g4['settled']['small']}/{g4['settled']['n_board']} {g4['settled']['rate_pct']}%" if 'settled' in g4 else '-'))
    for k in (2, 3, 4):
        tot[f"fail{k}"] += c[k]; tot[f"j{k}"] += j[k]
    tot["fails"] += len(f); tot["judged"] += len(th)
    small = [t for t in th if t["size"] <= 3]
    tot["smallpass"] += sum(t["pass_g3"] for t in small)
print(dict(tot))
print(f"fails that are 2-3-member: {tot['fail2']+tot['fail3']} of {tot['fails']}; 4+: {tot['fail4']}")
print(f"2-3-member theme-nights judged {tot['j2']+tot['j3']}, passing {tot['smallpass']}"
      f" ({100*tot['smallpass']/(tot['j2']+tot['j3']):.1f}%); size2 fail {tot['fail2']}/{tot['j2']}, size3 fail {tot['fail3']}/{tot['j3']}")
# unjudgeable themes on board
for r in rows:
    th = r["detail"]["g3"]["themes"]
    un = [t for t in th if t["cohesion"] is None]
    print(r["et"][:10], "unjudgeable", len(un), Counter(min(t['size'],4) for t in un))
