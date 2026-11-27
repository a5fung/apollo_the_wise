#!/usr/bin/env python3
"""Stage 4 review - (a) what the keep walk would hold had the 20 era-A 'file start' rows NOT been dropped (hash coins only; outcome-free);
(b) every data path named in the stage scripts, against the prereg 1.3 closed list + the A1 pull file. Output -> r4_counterfactual_paths.txt"""
import hashlib, re
from pathlib import Path
import pandas as pd
HERE = Path(__file__).resolve().parent; ST = HERE.parent; DATA = Path("/Users/alvinfung/apollo_data")
L = []
def P(s=""):
    print(s); L.append(str(s))
EV = pd.read_parquet(DATA / "cb702/bws1124_events_postdrop.parquet", columns=["era", "ticker", "D", "E", "key", "hstr", "uci", "kept", "kept2411"])
ucal = (ST / "stage1de/calendars_union.txt").read_text().split("\n"); uidx = {d: i for i, d in enumerate(ucal)}
extra = {}
for ln in (HERE / "r2_file_start.txt").read_text().splitlines():
    m = re.match(r"^\s+([A-Z]+) (\d{4}-\d\d-\d\d) 0 ", ln)
    if m: extra.setdefault(m.group(1), []).append(m.group(2))
assert sum(len(v) for v in extra.values()) == 20
def coin(seed, hs, d): return int.from_bytes(hashlib.sha256(f"{seed}|{hs}|{d}".encode()).digest()[:8], "big") / 2 ** 64
P("== (a) the 20 mis-dropped rows put back: keep walk per identity, both seeds ==")
for t, ds in extra.items():
    g = EV[(EV.ticker == t) & (EV.era == "A")]
    if len(g):
        key, hs = g.key.iloc[0], g.hstr.iloc[0]; full = EV[EV.key == key]
    else:
        key, hs = None, t; full = EV.iloc[0:0]
    P(f"{t}: identity string {hs!r}; surviving break rows of the identity {len(full)} (eras {sorted(set(full.era))}); rows put back {len(ds)} ({ds[0]} .. {ds[-1]})")
    for seed, col in ((1124, "kept"), (2411, "kept2411")):
        seq = sorted([(uidx[d], d, True) for d in ds] + [(u, d, False) for u, d in zip(full.uci, full.D)])
        last = None; newkept = []
        for u, d, isnew in seq:
            if (last is None or u - last > 60) and coin(seed, hs, d) < 0.2:
                last = u; newkept.append(d)
        old = sorted(full.D[full[col]])
        add = [d for d in newkept if d not in old]; lost = [d for d in old if d not in newkept]
        P(f"   seed {seed}: kept as run {old} -> with the rows back {newkept}; ADDED {add} LOST {lost}")
P("\n== (b) data paths named in the stage scripts ==")
closed = ["features_eraB", "holdout", "big_winners", "trades", "walk_stdout", "report.txt", "list_eraB.tsv", "cb702_pre_v2/out", "raw_close_bwin_1124", "fire_paths90"]
for stage in ("stage1ab", "stage1c", "stage1de", "stage1f", "stage2", "stage3"):
    for py in sorted((ST / stage).glob("*.py")):
        txt = py.read_text()
        hits = sorted({c for c in closed if c in txt})
        opens = sorted(set(re.findall(r'["\']([A-Za-z0-9_./-]+\.(?:csv\.gz|tsv\.gz|parquet|tsv|psv|npz|json|txt))["\']', txt)))
        P(f"{stage}/{py.name}: closed-list words present {hits or 'none'}")
        if hits:
            for i, ln in enumerate(txt.splitlines(), 1):
                if any(c in ln for c in hits): P(f"      L{i}: {ln.strip()[:170]}")
(HERE / "r4_counterfactual_paths.txt").write_text("\n".join(L) + "\n")
