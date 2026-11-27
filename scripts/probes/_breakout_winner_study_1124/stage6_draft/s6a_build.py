"""Stage 6 DRAFT step a: the read's components for every kept event (seed 1124 U seed 2411). OUTCOME-FREE: opens no outcome file; every
series is cut at D before the feature function sees it (asserted inside). Writes gr1_components.tsv.gz (a draft table, not hashed as a freeze)."""
import hashlib, sys, time
from pathlib import Path
HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "stage1f")); sys.path.insert(0, str(HERE))
from lib1f import *          # noqa  (asserts prereg + A1 + pins; setup_store; EraCtx; load_dates; bv, cb)
HERE = Path(__file__).resolve().parent   # lib1f's star-import rebinds HERE to stage1de: bind it back (the first run wrote its table there; moved here by hand, same bytes)
import gr1
SH = {"docs/analysis/breakout_winner_study_prereg_DRAFT_2026-11-24.md": "3eb2b9b0247bc0ba7bf0d8e6f1efd67da1078fc090373c83c1bc14599339042a",
      "docs/analysis/breakout_winner_study_prereg_amendment_A1_2026-11-26.md": "4a7beda14378ed2dea42308d92364dd92de4907aa3c7da4aaaffdffe75d17b10",
      "docs/analysis/breakout_winner_study_prereg_amendment_A2_2026-11-26.md": "0a6cc4174ef27d187e49100e966023340f7eb0e31cc2d552f4c5ea594f622f6b",
      "docs/analysis/breakout_winner_study_prereg_amendment_A3_2026-11-26.md": "a0c11a3685bc83369a9fba29766368e82734432ea9a3a464fd363787e6d34268"}
for p, h in SH.items():
    assert hashlib.sha256((REPO / p).read_bytes()).hexdigest() == h, f"{p} sha differs - STOP"
assert_docs()
t0 = time.time()
TBLP = HERE.parent / "stage1f/feature_table.tsv.gz"
assert hashlib.sha256(TBLP.read_bytes()).hexdigest() == "d629ef0af85f0ed3404d0e9cffcc6545627fa3dec6230eb4da94cb3ed95bf53c"
T = pd.read_csv(TBLP, sep="\t", low_memory=False, keep_default_na=False, na_values=[""], dtype={"ticker": str})
T = T[(T.kept == True) | (T.kept2411 == True)].reset_index(drop=True)
assert int(T.kept.sum()) == 11596 and int(T.kept2411.sum()) == 11607
assert T.E.max() <= "2024-12-31"
gB, fA, fB = load_dates()
recs = []
for era in ("A", "B"):
    S = setup_store(era)
    cal = [d.isoformat() for d in S.D.cal]
    assert cal[-1] <= "2024-12-31"
    guard = {t: sorted(date.fromordinal(int(o)).isoformat() for o in v) for t, v in S.breaks.items()} if era == "A" else gB
    ctx = EraCtx(era, S, cal, guard, fA if era == "A" else fB)
    for r in T[T.era == era].itertuples(index=False):
        k, a, d, ci, o, h, l, c, v = ctx.series(r.ticker)
        Di = int(np.searchsorted(ci, int(r.ci))); assert int(ci[Di]) == int(r.ci) and cal[int(r.ci)] == r.D
        raw_close = float(S.raw_factor[a + Di]) * float(S.D.c[a + Di])
        cut = gr1.cut_at_D((d, ci, o, h, l, c, v), Di)
        assert int(cut[1][-1]) == int(r.ci) and str(cut[0][-1])[:10] == r.D          # nothing after D is handed on
        vals, nul = gr1.v_parts(bv=bv, cb=cb, cal=cal, cut=cut, ciD=int(r.ci), rs_best=r.rs_best, raw_close=raw_close,
                                flag_dates=ctx.flags.get(r.ticker, []), guard_dates=ctx.guard.get(r.ticker, []))
        rec = dict(era=era, ci=int(r.ci), D=r.D, E=r.E, ticker=r.ticker, kept=bool(r.kept), kept2411=bool(r.kept2411), set=r.set, Ey=r.Ey, month=r.month,
                   gr1_null=nul or "")
        rec.update(vals)
        recs.append(rec)
    G.clear()
F = pd.DataFrame(recs).sort_values(["era", "ci", "ticker"]).reset_index(drop=True)
F.to_csv(HERE / "gr1_components.tsv.gz", sep="\t", index=False, float_format="%.10g", compression={"method": "gzip", "mtime": 0})
print(f"rows {len(F)}; NULL {dict(F.gr1_null.value_counts())}; {time.time()-t0:.0f}s; outcome files opened: 0")
