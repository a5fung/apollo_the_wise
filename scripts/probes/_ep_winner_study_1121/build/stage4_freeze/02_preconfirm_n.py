#!/usr/bin/env python3
"""STAGE 4 / step 7 — PRE-CONFIRM PRINTS (prereg §6 step 7, §3, §11). OUTCOME-FREE: reads ONLY the stage-1 feature table (built from
bars < E + open(E)), stage4_freeze/h_reads.tsv.gz (same rule) and the VERDICT / cap lines of stage3/discovery.txt (the carried list and
directions only). No bar file, no outcome table and no label is opened here.
Confirm n per carried feature, the combination and H1-H4, per era, with the layout the confirm test will use:
  thirds within (era, month) with >= 6 scored events, mid-rank ties (§5.1); two-group = months with >= 6 scored and >= 2 of each (A1).
Run: python3 02_preconfirm_n.py > 02_preconfirm_n.txt"""
import hashlib
import sys
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent
STAGE1 = HERE.parent / "stage1"
sys.path.insert(0, str(STAGE1))
import common as C      # noqa: E402
import stats as S       # noqa: E402

FT_SHA = "ade1d7802eaf70aa60a9b5514d79b72084876d9601b0999328c9b1aad0cf0de7"
HR_SHA = "0b995389a41fc462e5ca81b3d7ce38247cd42f36dd754e1edd7c44d3110d79f7"
PRE_S11_BYTES, PRE_S11_SHA = 49932, "4f2dbe7fa6f58171180689cc9b374ba4fd88f2f8ef68c9bfbeb723e32bf9bdfc"
CARRIED = {"f02": -1, "f03": +1, "f09": +1, "f18": -1}       # stage3/discovery.txt "CARRIED LIST (direction frozen)"
NAMES = {"f02": "gap size in daily ranges", "f03": "short run-up (20)", "f09": "base depth (40)", "f18": "price (raw)",
         "combo": "combination f02+f03+f09+f18", "H1": "below the 200-day at the open", "H2": "in a downtrend",
         "H3": "above all moving averages at open", "H4": "ADR20 (= B2)"}
DIRN = {"f02": "LOW third wins", "f03": "HIGH third wins", "f09": "HIGH third wins", "f18": "LOW third wins", "combo": "HIGH third wins",
        "H1": "NO wins", "H2": "NO wins", "H3": "YES wins", "H4": "HIGH third wins"}
TWO = {"H1", "H2", "H3"}

print("# STAGE 4 / 02 — PRE-CONFIRM PRINTS (outcome-free): confirm n per carried feature, combination and H1-H4, per era")
doc = open(C.PREREG, "rb").read()
assert hashlib.sha256(doc[:PRE_S11_BYTES]).hexdigest() == PRE_S11_SHA, "the pre-§11 text of the prereg changed"
assert b"\n## 11. HIS GALLERY READS FROZEN" in doc[PRE_S11_BYTES:]
print(f"prereg: first {PRE_S11_BYTES} bytes sha256 {PRE_S11_SHA[:8]}… = the document before §11 (ASSERT OK: §11 is append-only)")
assert C.sha(STAGE1 / "feature_table.tsv.gz") == FT_SHA and C.sha(HERE / "h_reads.tsv.gz") == HR_SHA
print(f"inputs: feature_table.tsv.gz {FT_SHA[:8]}… · h_reads.tsv.gz {HR_SHA[:8]}… (ASSERT OK)")
d3 = (HERE.parent / "stage3" / "discovery.txt").read_text()
for f, s in CARRIED.items():
    assert f"VERDICT: {f} " in d3 and f"CARRIED to confirm, direction frozen: {'HIGH' if s > 0 else 'LOW'} third wins" in d3.split(f"VERDICT: {f} ")[1].split("\n")[0], f
assert "-> the four: ['f09', 'f02', 'f18', 'f03']" in d3
print("carried list + directions equal stage3/discovery.txt (ASSERT OK; only its VERDICT lines are parsed)")

T = pd.read_csv(STAGE1 / "feature_table.tsv.gz", sep="\t", keep_default_na=False, na_values=[""], dtype={"ticker": str, "E": str, "year": str})
Hh = pd.read_csv(HERE / "h_reads.tsv.gz", sep="\t", keep_default_na=False, na_values=[""], dtype={"ticker": str, "E": str, "year": str})
assert (T.ticker.to_numpy() == Hh.ticker.to_numpy()).all() and (T.E.to_numpy() == Hh.E.to_numpy()).all() and (T.era.to_numpy() == Hh.era.to_numpy()).all()
for h in ("H1", "H2", "H3", "H4"):
    T[h] = Hh[h].to_numpy()
assert np.allclose(T.H4.dropna(), T.B2.dropna()) and (T.H4.notna() == T.B2.notna()).all()
Cf = T[T.set == "CONF"].reset_index(drop=True)
assert len(Cf) == 2251 and Cf.E.min() >= "2021-01-01" and (Cf.era == "A").sum() == 867 and (Cf.era == "B").sum() == 1384
N = len(Cf)

# §5.6 combination on confirm — the discovery definition applied to confirm events (ranks within (era, month) over events scored on all four)
mask = np.ones(N, bool)
for f in CARRIED:
    mask &= Cf[f].notna().to_numpy()
acc = np.zeros(N)
for f, s in CARRIED.items():
    pr = S.pct_rank_within(Cf, f, ["era", "month"], mask)
    acc += pr if s > 0 else (1.0 - pr)
Cf["combo"] = np.where(mask, acc / len(CARRIED), np.nan)

ROWS = list(CARRIED) + ["combo", "H1", "H2", "H3", "H4"]
print(f"\nconfirm set: {N} events (era A {int((Cf.era == 'A').sum())}, E 2021-01-04..2022-04-04 · era B {int((Cf.era == 'B').sum())}, E 2022-04-05..2024-09-30)")
print("Holm family (prereg §11.2) = 9: " + " · ".join(f"{r} [{DIRN[r]}]" for r in ROWS))
print("\n## CONFIRM n — scored = non-NULL; in test = in an (era, month) group that qualifies; low / high = bottom / top third, or yes / no for H1-H3")
hdr = f"   {'':6}{'name':36} {'era':>6} {'events':>7} {'scored':>7} {'months':>7} {'in test':>8} {'bottom|yes':>11} {'middle':>7} {'top|no':>7}"
print(hdr)
out = []
for r in ROWS:
    if r in TWO:
        g = np.where(Cf[r].isna(), -1, Cf[r].fillna(0)).astype(int)
        t = S.assign_two(Cf, g, ["era", "month"], min_n=S.MIN_MONTH)
        lo, hi, mid = (t == 2), (t == 0), np.zeros(N, bool)          # yes | no
    else:
        t = S.assign_thirds(Cf, r, ["era", "month"], S.MIN_MONTH, True)
        lo, hi, mid = (t == 0), (t == 2), (t == 1)
    for era in ("A", "B", "A+B"):
        m = np.ones(N, bool) if era == "A+B" else (Cf.era == era).to_numpy()
        sc = int((m & Cf[r].notna().to_numpy()).sum())
        it = m & (t >= 0)
        nm = len(set(zip(Cf.era[it], Cf.month[it])))
        print(f"   {r:6}{NAMES[r]:36} {era:>6} {int(m.sum()):7d} {sc:7d} {nm:7d} {int(it.sum()):8d} {int((m & lo).sum()):11d} {('-' if r in TWO else str(int((m & mid).sum()))):>7} {int((m & hi).sum()):7d}")
        out.append((r, era, int(m.sum()), sc, nm, int(it.sum()), int((m & lo).sum()), int((m & mid).sum()), int((m & hi).sum())))
    if r in TWO:
        sm_ = min(int(lo.sum()), int(hi.sum())); tot = int((t >= 0).sum())
        print(f"   {'':6}{'':36} smaller group in test {sm_} = {sm_ / tot:.1%} of {tot}")
pd.DataFrame(out, columns=["row", "era", "events", "scored", "months", "in_test", "bottom_or_yes", "middle", "top_or_no"]).to_csv(HERE / "confirm_n.tsv", sep="\t", index=False)

print("\n## CONFIRM n per year (scored / events)")
print("   " + f"{'era year':10}{'events':>7}" + "".join(f"{r:>7}" for r in ROWS))
for (era, y), g in Cf.groupby(["era", "year"]):
    print("   " + f"{era + ' ' + y:10}{len(g):7d}" + "".join(f"{int(g[r].notna().sum()):7d}" for r in ROWS))
print("\n## NOTES (outcome-free)")
print("   * H1 / H3 need 200 sessions, H2 220: era-B events before 2022-07-18 (H1/H3) / 2022-08-11 (H2) are NULL — the era-B file starts 2021-09-27.")
print("   * H4's thirds are the same thirds stage 3 used for B2 (mid-rank ties, within (era, month)).")
print("   * No outcome, forward bar or label was opened by this script; the confirm run (step 8) has NOT been run.")
print(f"\nPREREG sha256 NOW (with §11) = {C.sha(C.PREREG)}")
print(f"stage4_freeze sha256: hreads.py {C.sha(HERE / 'hreads.py')} | 01_freeze_reads.py {C.sha(HERE / '01_freeze_reads.py')} | 01_freeze_reads.txt {C.sha(HERE / '01_freeze_reads.txt')} | h_reads.tsv.gz {C.sha(HERE / 'h_reads.tsv.gz')} | this script {C.sha(__file__)}")
