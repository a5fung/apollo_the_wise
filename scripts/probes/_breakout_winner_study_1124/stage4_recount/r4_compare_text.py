import re, pandas as pd, numpy as np
import r4_common as C
own = pd.read_csv(C.OUTD / f"r4_stats_own{C.SUF}.tsv", sep="\t").set_index("feature")
txt = open("/Users/alvinfung/apollo_the_wise/scripts/probes/_breakout_winner_study_1124/stage3/3_discovery.txt").read()
blocks = re.split(r"\n(?=f\d\d[ab]? - |B\d - )", txt)
rows = []
for b in blocks:
    m = re.match(r"(f\d\d[ab]?|B\d) - ", b)
    if not m: continue
    k = m.group(1)
    f = ("f" + str(int(k[1:3])) + (k[3:] if len(k) > 3 else "")) if k.startswith("f") else k
    big = re.search(r"bottom (\d+)/(\d+) = [\d.]+% \| middle (\d+)/(\d+) = [\d.]+% \| top (\d+)/(\d+)", b)
    ci = re.search(r"90% interval ([\d.]+)-([\d.]+)", b)
    pm = re.search(r"permutation p \(two-sided, 10,000\) ([\d.]+)", b)
    if f in own.index:
        o = own.loc[f]
        rows.append(dict(f=f, t_bot=big and f"{big.group(1)}/{big.group(2)}", m_bot=f"{o.w_bot:.0f}/{o.n_bot}", t_top=big and f"{big.group(5)}/{big.group(6)}", m_top=f"{o.w_top:.0f}/{o.n_top}",
                         t_lo=float(ci.group(1)) if ci else np.nan, m_lo=o.ci_lo, t_hi=float(ci.group(2)) if ci else np.nan, m_hi=o.ci_hi))
D = pd.DataFrame(rows)
D["counts_equal"] = (D.t_bot == D.m_bot) & (D.t_top == D.m_top)
D["d_ci"] = np.fmax((D.t_lo - D.m_lo).abs(), (D.t_hi - D.m_hi).abs())
print(D.round(3).to_string()); print("counts all equal:", bool(D[D.t_bot.notna()].counts_equal.all()), "| max CI endpoint diff", D.d_ci.max())
D.to_csv(C.OUTD / f"r4_vs_stage3_text{C.SUF}.tsv", sep="\t", index=False)
