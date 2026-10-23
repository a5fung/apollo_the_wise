"""Candidate rebuild of the 2017-21 export (2026-10-23): cb702_pre + the survivorship refetch, de-duplicated and typed, written to a NEW
era dir (cb702_pre stays untouched: its files are hash-pinned by the A+ freeze and the held RS-alone freeze). Same row shapes and the
same identity-guard derivation as `_cb_backtest/selection_pre.export` (ext_bars.guard over the combined arrays, then the SPY calendar).
Steps:
  1. the original arrays (ext_2016_2022/alp_flat.npz) + the refetched symbols 06 kept (adjusted and raw, both keys present), with the
     same row rules as ext_bars.build: finite positive OHLC, volume > 0 (Alpaca forward-fills a dormant symbol with zero-volume rows);
  2. de-duplication from the trial-2 duplicate lens (dedupe map): a strict pair drops `drop_hint`'s rows on the matched span
     [first, last]; a scaled twin drops the member NOT active in Alpaca's asset list (both or neither: fewer bars, then alphabetical)
     on [first_scaled, last_scaled] — raw closes inside a scaled pair were checked equal (only the later-split scale differs);
     every drop is written to dedupe_applied.tsv with the kept symbol (the alias map for label joins);
  3. identity guard re-derived over the combined arrays; for an original symbol untouched by step 2 it must equal cb702_pre's
     guard (asserted — the parity check that the build path is the same);
  4. types: small_pulls.psv = cb702_pre's + `sectype|SYM|TYPE|` for kept refetched symbols (Polygon records) and for the export's own
     untyped admitted tickers (07, point in time);
  5. daily_closes_all.csv.gz, daily_raw_close.csv.gz, sessions.txt, symbol_guard.tsv, cb702_sic.psv, export_stats.tsv.
usage: 08_build_v2.py <survivorship dir> <out era dir>"""
import os, sys, csv, shutil, datetime as dt, numpy as np, pandas as pd
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "_qm_streams"))
import ext_bars
D, OUT = sys.argv[1:3]
PRE = os.path.dirname(D.rstrip("/")); EXT = "/Users/alvinfung/apollo_data/cb702/qm_streams/ext_2016_2022"
T2 = f"{D}/merged_trial2"; os.makedirs(OUT, exist_ok=True); stats = {}
a = ext_bars.load(EXT)
n_rows = a["stop"] - a["start"]
orig = pd.DataFrame({"t": np.repeat(a["tickers"], n_rows), "o_d": a["d"], **{k: a[k] for k in ("o", "h", "l", "c", "v", "c_raw")}})
stats["orig_rows"], stats["orig_symbols"] = len(orig), int(orig.t.nunique())
dropped = pd.read_csv(f"{T2}/refetch_dropped.tsv", sep="\t", dtype=str)
rf = pd.read_csv(f"{D}/refetch_combined_1023.csv.gz", names=["t", "d", "o", "h", "l", "c", "v"], dtype={"t": str, "d": str})
rw = pd.read_csv(f"{D}/refetch_combined_raw_1023.csv.gz", names=["t", "d", "o", "h", "l", "c", "v"], usecols=[0, 1, 5], dtype={"t": str, "d": str})
rf = rf[~rf.t.isin(set(dropped.symbol)) & ~rf.t.isin(set(orig.t))]
rf = rf.merge(rw.rename(columns={"c": "c_raw"}), on=["t", "d"])
ok = np.isfinite(rf[["o", "h", "l", "c", "v", "c_raw"]]).all(axis=1) & (rf[["o", "h", "l", "c", "c_raw"]] > 0).all(axis=1) & (rf.v > 0)
stats["refetch_rows_in"], stats["refetch_rows_bad_or_zero_volume_dropped"] = len(rf), int((~ok).sum())
rf = rf[ok]; rf["o_d"] = pd.to_datetime(rf.d).map(dt.date.toordinal).astype(np.int32)
rf = rf.drop(columns="d"); stats["refetch_symbols_added"] = int(rf.t.nunique())
m = pd.concat([orig, rf[orig.columns]], ignore_index=True)
# 2. de-duplication
dm = pd.read_csv(f"{T2}/audit/dup/A_trial2_dedupe_map.tsv", sep="\t", dtype=str)
tw = pd.read_csv(f"{T2}/audit/dup/A_trial2_scaled_twins.tsv", sep="\t", dtype=str)
ast = pd.read_csv("/Users/alvinfung/apollo_data/cb702/qm_streams/alpaca_all_2016_2022/assets.tsv", sep="\t", dtype=str)
active = set(ast.symbol[ast.status == "active"]); nb = m.t.value_counts()
todo = []
for r in dm[~dm.kind.str.startswith("scaled")].itertuples():
    keep = r.sym_b if r.drop_hint == r.sym_a else r.sym_a
    todo.append((r.drop_hint, keep, r.first, r.last, r.kind))
for r in tw.itertuples():
    a_, b_ = r.sym_a, r.sym_b
    score = lambda s: (s in active, nb.get(s, 0), [-ord(ch) for ch in s])
    lose, keep = (b_, a_) if score(a_) > score(b_) else (a_, b_)
    todo.append((lose, keep, r.first_scaled, r.last_scaled, r.kind))
dates = pd.Series(m.o_d.map(dt.date.fromordinal).astype(str).values, index=m.index)
kill = pd.Series(False, index=m.index); log = []
for lose, keep, f, l, kind in todo:
    sel = (m.t == lose) & (dates >= f) & (dates <= l)
    log.append(dict(dropped_symbol=lose, kept_symbol=keep, first=f, last=l, kind=kind, rows=int(sel.sum()))); kill |= sel
m = m[~kill].sort_values(["t", "o_d"], kind="stable").reset_index(drop=True)
pd.DataFrame(log).to_csv(f"{OUT}/dedupe_applied.tsv", sep="\t", index=False)
stats["dedupe_pairs_applied"], stats["dedupe_rows_dropped"] = len(log), int(kill.sum())
# 3. guard over the combined arrays
codes, uniques = pd.factorize(m["t"], sort=True)
bounds = np.concatenate(([0], np.flatnonzero(np.diff(codes)) + 1, [len(codes)]))
arr = dict(tickers=np.array([str(u) for u in uniques]), start=bounds[:-1].astype(np.int64), stop=bounds[1:].astype(np.int64),
           d=m.o_d.to_numpy(np.int32), **{k: m[k].to_numpy(float) for k in ("o", "h", "l", "c", "v", "c_raw")})
rows, _ = ext_bars.guard(arr, {})
ext_bars.write_guard(rows, OUT)
old = {r["symbol"]: r["breaks"] for r in csv.DictReader(open(f"{PRE}/symbol_guard.tsv"), delimiter="\t")}
touched = {x["dropped_symbol"] for x in log}
bad = [s for s in old if s not in touched and s in rows and rows[s]["breaks"] != old[s]]
stats["guard_parity_untouched_original_symbols_differing"] = len(bad)
assert not bad, f"guard differs from cb702_pre for untouched symbols: {bad[:5]}"
stats["symbols_with_a_break"] = sum(1 for r in rows.values() if r["breaks"])
# 5. calendar + files (same shapes as selection_pre.export)
cal = ext_bars._calendar(arr); ci = np.searchsorted(cal, arr["d"])
on = (ci < len(cal)) & (cal[np.minimum(ci, len(cal) - 1)] == arr["d"])
stats["off_calendar_bars_dropped"] = int((~on).sum())
tick = np.repeat(arr["tickers"], arr["stop"] - arr["start"])[on]; days = (arr["d"][on] - 719163).astype("datetime64[D]").astype(str)
for sym in ("SPY", "QQQ"):
    assert np.array_equal(arr["d"][on][tick == sym], cal), f"{sym} does not carry every SPY session"
gz = {"method": "gzip", "compresslevel": 3}
pd.DataFrame({"ticker": tick, "d": days, **{k: arr[k][on] for k in ("o", "h", "l", "c", "v")}}).to_csv(f"{OUT}/daily_closes_all.csv.gz", header=False, index=False, compression=gz)
pd.DataFrame({"ticker": tick, "d": days, "c_raw": arr["c_raw"][on]}).to_csv(f"{OUT}/daily_raw_close.csv.gz", header=False, index=False, compression=gz)
open(f"{OUT}/sessions.txt", "w").write("\n".join(dt.date.fromordinal(int(x)).isoformat() for x in cal) + "\n")
stats["rows_written"], stats["symbols_written"] = int(on.sum()), int(len(np.unique(tick)))
# 4. types
rec = pd.read_csv(f"{D}/refetch_combined_records_1023.tsv", sep="\t", dtype=str).fillna("").sort_values("delisted").drop_duplicates("ticker", keep="last").set_index("ticker")
ty = pd.read_csv(f"{D}/untyped_types_1023.tsv", sep="\t", dtype=str).fillna("")
added = set(rf.t); n_rt = n_ut = 0
with open(f"{OUT}/small_pulls.psv", "w") as fh:
    fh.write(open(f"{PRE}/small_pulls.psv").read().rstrip("\n") + "\n")
    for s in sorted(added):
        if rec.type.get(s, ""): fh.write(f"sectype|{s}|{rec.type[s]}|\n"); n_rt += 1
    for r in ty.itertuples():
        if r.type: fh.write(f"sectype|{r.ticker}|{r.type}|\n"); n_ut += 1
stats["types_added_refetched"], stats["types_added_untyped_existing"], stats["untyped_existing_still_unknown"] = n_rt, n_ut, int((ty.type == "").sum())
shutil.copyfile(f"{PRE}/cb702_sic.psv", f"{OUT}/cb702_sic.psv")
with open(f"{OUT}/export_stats.tsv", "w") as f:
    for k, v in stats.items(): f.write(f"{k}\t{v}\n")
print("\n".join(f"{k}\t{v}" for k, v in stats.items()))
