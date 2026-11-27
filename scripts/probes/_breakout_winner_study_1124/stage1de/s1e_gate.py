"""1e GATE, written independently of the walk code in s1e_events.py: session positions from the two era calendar FILES by bisect (not the walk's index),
walk re-implemented per identity from the post-drop event table; checks (1) the re-run keep set equals the written one, (2) no identity kept twice within 60
sessions across eras, (3) no (identity, D) in both eras. Prints the smallest cross-era gap among identities kept in both eras."""
import bisect, hashlib, json
import pandas as pd
from pathlib import Path
DATA = Path("/Users/alvinfung/apollo_data/cb702"); HERE = Path(__file__).resolve().parent
dates = sorted(set(open(DATA / "bws1124_eraA_list_ctx.cal.txt").read().split()) | set(open(DATA / "bws1124_eraB_list_ctx.cal.txt").read().split()))
pos = lambda d: bisect.bisect_left(dates, d)
assert all(dates[pos(d)] == d for d in dates[::50])
ev = pd.read_parquet(DATA / "bws1124_events_postdrop.parquet")
q = json.load(open(HERE / "1e_result.json"))["q"]
res = {}
for seed, col in ((1124, "kept"), (2411, "kept2411")):
    keep = set(); cross = []
    for key, g in ev.groupby("key"):
        rows = sorted(zip(g.D, g.era, g.hstr), key=lambda r: r[0]); last = None; lk = []
        for d, e, h in rows:
            p = pos(d)
            if last is not None and p - last <= 60: continue
            u = int.from_bytes(hashlib.sha256(f"{seed}|{h}|{d}".encode()).digest()[:8], "big") / 2 ** 64
            if u < q: keep.add((key, d)); last = p; lk.append((p, e))
        for (p1, e1), (p2, e2) in zip(lk, lk[1:]):
            assert p2 - p1 > 60
            if e1 != e2: cross.append(p2 - p1)
    written = set(zip(ev.key[ev[col]], ev.D[ev[col]]))
    res[seed] = (len(keep), keep == written, min(cross) if cross else None, len(cross))
    print(f"seed {seed}: independent walk keeps {len(keep):,}; equals the written set: {keep == written}; identities-pairs kept across eras: {len(cross)}, smallest cross-era gap {min(cross) if cross else None} sessions (must be > 60)")
dup = ev.groupby(["key", "D"]).era.nunique().max()
print(f"max eras per (identity, D): {dup} (must be 1)")
ok = all(r[1] for r in res.values()) and dup == 1 and all(r[2] is None or r[2] > 60 for r in res.values())
print("1e GATE:", "PASS" if ok else "FAIL")
(HERE / "1e_gate.txt").write_text(f"1e gate {'PASS' if ok else 'FAIL'}; {res}\n")
