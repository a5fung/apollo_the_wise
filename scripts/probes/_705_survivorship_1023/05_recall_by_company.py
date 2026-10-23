"""Recall per company (2026-10-23), from 04's classification. A missed symbol is:
  not_stock       its 2022 type is not CS / ADRC (preferred, ETF, ETN, fund, warrant, unit) -> correctly not fetched;
  new_name_ok     an active record shares its FIGI / CIK and that CURRENT ticker is in the 2017-21 export with Jan-Jun 2022 bars;
  new_name_GAP    a current ticker exists but is NOT in the 2017-21 export (a live company the file lacks);
  gone_GAP        no active successor: a gone company the refetch did not bring back;
  no_record       Polygon has no record for the symbol.
Recall = 1 - (new_name_GAP + gone_GAP + no_record) / (stock companies in the population). Printed for A and B separately.
usage: 05_recall_by_company.py <classified.tsv> <recall_check.txt> <cb702_pre export>"""
import sys, re, pandas as pd
cl = pd.read_csv(sys.argv[1], sep="\t", dtype=str).fillna("")
txt = open(sys.argv[2]).read()
pops = {"A": int(re.search(r"A\. .*?: (\d+); refetched (\d+)", txt).group(1)), "B": int(re.search(r"B\. .*?: (\d+); refetched (\d+)", txt).group(1))}
hits = {"A": int(re.search(r"A\. .*?: \d+; refetched (\d+)", txt).group(1)), "B": int(re.search(r"B\. .*?: \d+; refetched (\d+)", txt).group(1))}
miss = {k: set(m.split()) for k, m in zip("AB", re.findall(r"misses: (.*)", txt))}
pre = pd.read_csv(sys.argv[3], names=["t", "d"], usecols=[0, 1], dtype=str)
h1 = set(pre.t[(pre.d >= "2022-01-03") & (pre.d <= "2022-06-30")]); del pre
def kind(r):
    if not r.type_2022 and not r.name_2022: return "no_record"
    if r.type_2022 not in ("CS", "ADRC"): return "not_stock"
    cur = r.current_by_figi or r.current_by_cik
    if cur and cur != r.symbol: return "new_name_ok" if cur in h1 else "new_name_GAP"
    if cur == r.symbol: return "new_name_GAP"          # trades today under the same symbol but the file lacks it
    return "gone_GAP"
cl["kind"] = cl.apply(kind, axis=1)
cl["current"] = cl.current_by_figi.where(cl.current_by_figi != "", cl.current_by_cik)
for k in "AB":
    c = cl[cl.symbol.isin(miss[k])]
    vc = c.kind.value_counts().to_dict()
    stock = pops[k] - vc.get("not_stock", 0)
    gaps = vc.get("new_name_GAP", 0) + vc.get("gone_GAP", 0) + vc.get("no_record", 0)
    print(f"{k}: population {pops[k]}, refetched {hits[k]}, misses {len(c)} -> {vc}")
    print(f"   stock companies {stock}; covered (refetched or under the new name) {stock - gaps} = {100 * (stock - gaps) / stock:.1f}%")
    for kk in ("new_name_GAP", "gone_GAP", "no_record"):
        x = c[c.kind == kk]
        if len(x): print(f"   {kk}: " + ", ".join(f"{r.symbol}{'->' + r.current if r.current else ''} ({r.name_2022[:28]}; {r.delisted or '-'})" for r in x.itertuples()))
cl.to_csv(sys.argv[1].replace(".tsv", "_kind.tsv"), sep="\t", index=False)
