"""Step 4 (local, $0): two free signals per gap event, since Alpaca's split-adjusted bars and its corporate-actions feed both miss the
known spin-offs (OPLN 2019 absent from the feed; OPLN and ZWS identical under 'all' adjustment).
  (a) DOWN gaps — a NEW listing: any export ticker whose first bar falls within gap_date-2 .. gap_date+1 (a spin-off lists on or
      around the distribution date); its name from assets.tsv and its first close, beside the parent's dollar drop.
  (b) UP gaps — a bad print: the gap reverts the next session (next close within 10% of the pre-gap close).
Positive controls: OPLN 2019-06-28 must show a new listing (IAA); ZWS 2021-10-05 must show one (RBC)."""
import pandas as pd
D = "/Users/alvinfung/apollo_the_wise/scripts/probes/_705_corp_actions_1023"
ev = pd.read_csv(f"{D}/01_events.tsv", sep="\t")
names = {}
for ln in open("/Users/alvinfung/apollo_data/cb702/qm_streams/alpaca_all_2016_2022/assets.tsv"):
    p = ln.rstrip("\n").split("\t")
    if len(p) > 1: names[p[0]] = p[1]
rows = []
for exf, lo, hi in (("/Users/alvinfung/apollo_data/cb702_pre/daily_closes_all.csv.gz", "2017", "2022-01-31"),
                    ("/Users/alvinfung/apollo_data/cb702/daily_closes_all.csv.gz", "2022-02", "2024-12-31")):
    ex = pd.read_csv(exf, header=None, names=["t", "d", "o", "h", "l", "c", "v"], usecols=[0, 1, 2, 5])
    ex = ex[ex.d <= "2024-12-31"]
    first = ex.groupby("t").d.min(); fc = ex.sort_values("d").groupby("t").c.first()
    sub = ev[(ev.gap_date >= lo) & (ev.gap_date <= hi)]
    ex = ex[ex.t.isin(set(sub.ticker))].sort_values(["t", "d"])
    for r in sub.itertuples():
        g = ex[ex.t == r.ticker].reset_index(drop=True)
        i = g.index[g.d == r.gap_date]
        if len(i) == 0 or i[0] == 0: continue
        i = i[0]; pc, o = g.c[i - 1], g.o[i]; nxt = g.c[i + 1] if i + 1 < len(g) else None
        gap = o / pc - 1
        d0 = pd.Timestamp(r.gap_date)
        newl = first[(pd.to_datetime(first) >= d0 - pd.Timedelta(days=2)) & (pd.to_datetime(first) <= d0 + pd.Timedelta(days=1))]
        cand = [f"{t}({names.get(t,'?')[:28]}, ${fc[t]:.2f})" for t in newl.index][:6] if gap < 0 else []
        rev = (nxt is not None and abs(nxt / pc - 1) < 0.10) if gap > 0 else None
        rows.append((r.ticker, r.gap_date, names.get(r.ticker, "?")[:30], round(gap, 3), round(pc, 2), round(pc - o, 2), len(newl) if gap < 0 else "", "|".join(cand), rev))
out = pd.DataFrame(rows, columns=["ticker", "gap_date", "name", "gap", "prev_close", "dollar_drop", "n_new_listings", "new_listings", "up_gap_reverted_next_day"])
out.to_csv(f"{D}/05_local_checks.tsv", sep="\t", index=False)
print(out[out.gap < 0].to_string(index=False, max_colwidth=120))
print("\nUP gaps:", int((out.gap > 0).sum()), "| reverted next day (bad-print suspects):", int((out.up_gap_reverted_next_day == True).sum()))
print(out[out.up_gap_reverted_next_day == True][["ticker", "gap_date", "name", "gap", "prev_close"]].to_string(index=False))
