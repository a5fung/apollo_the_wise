"""Trial merge of the survivorship refetch into the 2017-21 export (2026-10-23), for the STEP 0 gate — not yet the rebuild.
Trial 1 (a plain append) showed Alpaca serves a renamed company's whole history under BOTH its old and its new symbol, so the refetch
re-added ~400 companies the export already carries under today's name (strict twins: same bars; scaled twins: the same bars at a
later reverse-split scale). Rules, in order:
  1. a refetched symbol already in the export is dropped (the export wins);
  2. every CONFIRMED strict pair and every scaled twin from trial 1's duplicate lens with exactly one refetched member: the refetched
     member is dropped (the export's series under today's symbol carries the company);
     both members refetched: the one with fewer bars is dropped (tie: alphabetical second);
  0. only (ticker, date) keys present in BOTH the split-adjusted and the raw fetch are kept (the PIT lenses need a raw close per row);
  3. each kept refetched symbol gets its Polygon type (records.tsv, as of its listing) as a `sectype|SYM|TYPE|` row in small_pulls.psv,
     the same row shape the export's own type pulls use.
Pairs with no refetched member (the export's own 71) are left for the rebuild's FIGI / CIK dedupe and still refuse G3.
usage: 06_merge_trial.py <survivorship dir> <trial-1 audit dir> <out dir>"""
import os, sys, gzip, pandas as pd
D, A1, O = sys.argv[1:4]
PRE = os.path.dirname(D.rstrip("/"))
os.makedirs(O, exist_ok=True)
pre_syms = set(pd.read_csv(f"{PRE}/daily_closes_all.csv.gz", names=["t"], usecols=[0], dtype=str).t)
rf = pd.read_csv(f"{D}/refetch_combined_1023.csv.gz", names=list("tdohlcv"), dtype={"t": str, "d": str})
raw = pd.read_csv(f"{D}/refetch_combined_raw_1023.csv.gz", names=list("tdohlcv"), dtype={"t": str, "d": str})
both = rf[["t", "d"]].merge(raw[["t", "d"]], on=["t", "d"])          # Alpaca's split and raw feeds differ on ~130 rows (SPAC symbols):
n0 = len(rf); rf = rf.merge(both, on=["t", "d"]); raw = raw.merge(both, on=["t", "d"])   # keep only the keys both carry
print(f"rows without a raw twin dropped: {n0 - len(rf)} adjusted")
ref = set(rf.t); nbars = rf.t.value_counts()
drop = {s: "already_in_export" for s in ref & pre_syms}
pairs = pd.read_csv(f"{A1}/dup/A_trial_pairs.tsv", sep="\t", dtype=str)
pairs = pairs[pairs.confirmed == "True"][["sym_a", "sym_b"]].assign(kind="strict")
tw = pd.read_csv(f"{A1}/dup/A_trial_scaled_twins.tsv", sep="\t", dtype=str)[["sym_a", "sym_b"]].assign(kind="scaled")
for r in pd.concat([pairs, tw]).itertuples():
    a, b = r.sym_a, r.sym_b
    ina, inb = a in ref and a not in pre_syms, b in ref and b not in pre_syms
    if ina and not inb: drop.setdefault(a, f"{r.kind}_twin_of_{b}")
    elif inb and not ina: drop.setdefault(b, f"{r.kind}_twin_of_{a}")
    elif ina and inb:
        lose = sorted([a, b], key=lambda s: (-nbars.get(s, 0), s))[1]
        drop.setdefault(lose, f"{r.kind}_twin_of_{a if lose == b else b}(both_refetched)")
keep = ref - set(drop)
pd.Series(drop, name="reason").rename_axis("symbol").reset_index().to_csv(f"{O}/refetch_dropped.tsv", sep="\t", index=False)
print(f"refetched symbols {len(ref):,}; dropped {len(drop):,} " + str(pd.Series(drop).str.replace(r"_of_.*", "", regex=True).value_counts().to_dict()) + f"; kept {len(keep):,}")
with gzip.open(f"{O}/daily_closes_all.csv.gz", "wt") as fh:
    with gzip.open(f"{PRE}/daily_closes_all.csv.gz", "rt") as src:
        for ln in src: fh.write(ln)
    rf[rf.t.isin(keep)].to_csv(fh, header=False, index=False)
with gzip.open(f"{O}/daily_raw_close.csv.gz", "wt") as fh:
    with gzip.open(f"{PRE}/daily_raw_close.csv.gz", "rt") as src:
        for ln in src: fh.write(ln)
    raw[raw.t.isin(keep)][["t", "d", "c"]].to_csv(fh, header=False, index=False)
rec = pd.read_csv(f"{D}/refetch_combined_records_1023.tsv", sep="\t", dtype=str).fillna("")
rec = rec.sort_values("delisted").drop_duplicates("ticker", keep="last").set_index("ticker")
with open(f"{O}/small_pulls.psv", "w") as fh:
    fh.write(open(f"{PRE}/small_pulls.psv").read().rstrip("\n") + "\n")
    for s in sorted(keep):
        t = rec.type.get(s, "")
        if t: fh.write(f"sectype|{s}|{t}|\n")
print(f"typed {sum(1 for s in keep if rec.type.get(s, ''))} of {len(keep)} kept; bars kept {int(rf.t.isin(keep).sum()):,}")
for f in ("symbol_guard.tsv", "cb702_sic.psv", "sessions.txt"):
    if not os.path.exists(f"{O}/{f}"): os.symlink(f"{PRE}/{f}", f"{O}/{f}")
