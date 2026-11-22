#!/usr/bin/env python3
"""STAGE 1 / step 1b — cross-era identity map (prereg §1 "Cross-era identity"). OUTCOME-FREE: closes of the shared overlap
2021-09-27..2022-06-30 only, ALL tickers of both daily files; no row after 2022-06-30 is kept (asserted).

Rule (frozen): era-A ticker a and era-B ticker b are the SAME identity when they share >= 40 sessions and their close-to-close
returns agree within 0.002 on >= 90% of the shared consecutive-session pairs. Candidates: the first 10 shared returns, rounded
to 4 decimals, are equal (the frozen text finds them by hashing; here the same equality is applied pair by pair to EVERY
(a, b), which is that rule with no hash collisions and no missed bucket). BESIDE (description): pairs passing the full test
without the first-10 candidate filter.
Run: python3 02_identity.py > 02_identity.txt"""
import numpy as np
import pandas as pd
import common as C

LO, HI = "2021-09-27", "2022-06-30"
MIN_SHARED, TOL, MIN_AGREE, NFIRST = 40, 0.002, 0.90, 10
cal = C.calendars()
sA = cal["A"][cal["A"] >= LO]
sB = cal["B"][cal["B"] <= HI]
assert len(sA) == len(sB) and (sA == sB).all(), "overlap calendars differ"
S = len(sA)
print(f"# STAGE 1 / 02 identity map. Overlap {LO}..{HI}: {S} sessions (the two era calendars agree on every one).")


def read(era):
    parts = []
    for ch in pd.read_csv(C.DAILY[era], header=None, names=["t", "d", "o", "h", "l", "c", "v"], usecols=["t", "d", "c"],
                          dtype={"t": str, "d": str, "c": "float64"}, keep_default_na=False, chunksize=2_000_000):
        ch = ch[(ch.d >= LO) & (ch.d <= HI)]
        parts.append(ch)
    df = pd.concat(parts, ignore_index=True)
    assert df.d.max() <= HI and df.d.min() >= LO
    si = np.searchsorted(sA, df.d.to_numpy(dtype="U10"))
    on = (si < S) & (sA[np.minimum(si, S - 1)] == df.d.to_numpy(dtype="U10"))
    df = df[on].copy(); df["si"] = si[on]
    assert not df.duplicated(["t", "si"]).any()
    tk = np.array(sorted(df.t.unique()))
    ti = np.searchsorted(tk, df.t.to_numpy())
    M = np.full((len(tk), S), np.nan)
    M[ti, df.si.to_numpy()] = np.where(df.c.to_numpy() > 0, df.c.to_numpy(), np.nan)
    return tk, M


tkA, MA = read("A")
tkB, MB = read("B")
print(f"tickers with a bar in the overlap: era A {len(tkA)}, era B {len(tkB)}")
keepA = np.isfinite(MA).sum(1) >= MIN_SHARED
keepB = np.isfinite(MB).sum(1) >= MIN_SHARED
tkA, MA, tkB, MB = tkA[keepA], MA[keepA], tkB[keepB], MB[keepB]
print(f"with >= {MIN_SHARED} overlap sessions (the only ones that can pass): era A {len(tkA)}, era B {len(tkB)}")
PA, PB = np.isfinite(MA), np.isfinite(MB)
with np.errstate(invalid="ignore", divide="ignore"):
    RA = MA[:, 1:] / MA[:, :-1] - 1.0
    RB = MB[:, 1:] / MB[:, :-1] - 1.0
VA, VB = np.isfinite(RA), np.isfinite(RB)
RA0, RB0 = np.nan_to_num(RA).astype(np.float64), np.nan_to_num(RB).astype(np.float64)
QA, QB = np.round(RA0, 4), np.round(RB0, 4)
PBf = PB.astype(np.float32)
rows = []
CH = 40
for a0 in range(0, len(tkA), CH):
    sl = slice(a0, a0 + CH)
    shared = PA[sl].astype(np.float32) @ PBf.T                                   # (ch, nB) shared sessions
    mask = VA[sl][:, None, :] & VB[None, :, :]                                   # (ch, nB, S-1) shared consecutive pairs
    npair = mask.sum(2)
    agree = (np.abs(RA0[sl][:, None, :] - RB0[None, :, :]) <= TOL) & mask
    nag = agree.sum(2)
    full = (shared >= MIN_SHARED) & (npair > 0) & (nag >= MIN_AGREE * npair - 1e-12)
    ia, ib = np.nonzero(full)
    for i, j in zip(ia, ib):
        m = mask[i, j]
        first = np.flatnonzero(m)[:NFIRST]
        cand = bool((QA[a0 + i, first] == QB[j, first]).all()) and len(first) == NFIRST
        rows.append((tkA[a0 + i], tkB[j], int(shared[i, j]), int(npair[i, j]), int(nag[i, j]), nag[i, j] / npair[i, j], cand))
P = pd.DataFrame(rows, columns=["a", "b", "shared_sessions", "pairs", "agree", "agree_share", "first10_equal"])
P.to_csv(C.HERE / "identity_pairs_all.tsv", sep="\t", index=False, float_format="%.4f")
OFF = P[P.first10_equal].copy()
print(f"\npairs passing the full test (>= {MIN_SHARED} shared sessions, >= {MIN_AGREE:.0%} of shared return pairs within {TOL}): {len(P)}")
print(f"  of them, passing the frozen candidate rule (first {NFIRST} shared returns equal at 4 decimals) = THE MAP: {len(OFF)}"
      f" | failing it (beside, NOT in the map): {len(P) - len(OFF)}")
same = OFF[OFF.a == OFF.b]
ren = OFF[OFF.a != OFF.b]
print(f"  THE MAP: same-symbol pairs {len(same)} | renames (a != b) {len(ren)}")
# multi-matches
ca, cb_ = OFF.groupby("a").size(), OFF.groupby("b").size()
multi_a, multi_b = ca[ca > 1], cb_[cb_ > 1]
print(f"  tickers matching more than one counterpart: era-A side {len(multi_a)}, era-B side {len(multi_b)}")
ev = C.build_population(verbose=lambda *_: None)
evA, evB = set(ev.loc[ev.era == "A", "ticker"]), set(ev.loc[ev.era == "B", "ticker"])
print("\n## every rename in THE MAP (era-B symbol -> era-A symbol; * = an event ticker on that side)")
for r in ren.sort_values(["b", "a"]).itertuples(index=False):
    print(f"  {r.b}{'*' if r.b in evB else ''} -> {r.a}{'*' if r.a in evA else ''}  shared {r.shared_sessions}, agree {r.agree}/{r.pairs} = {r.agree_share:.3f}")
print("\n## tickers matching more than one counterpart (THE MAP)")
for a in multi_a.index:
    g = OFF[OFF.a == a]
    print(f"  era-A {a}{'*' if a in evA else ''} <- era-B {', '.join(f'{b}({s:.3f})' for b, s in zip(g.b, g.agree_share))}")
for b in multi_b.index:
    g = OFF[OFF.b == b]
    print(f"  era-B {b}{'*' if b in evB else ''} -> era-A {', '.join(f'{a}({s:.3f})' for a, s in zip(g.a, g.agree_share))}")
# same-symbol pairs that fail (symbol reuse = two identities)
setA, setB = set(tkA), set(tkB)
both = sorted(setA & setB)
okk = set(zip(OFF.a, OFF.b))
allk = {(a, b): c for a, b, c in zip(P.a, P.b, P.first10_equal)}
ixA = {t: i for i, t in enumerate(tkA)}; ixB = {t: i for i, t in enumerate(tkB)}
fails = []
for t in both:
    if (t, t) in okk:
        continue
    i, j = ixA[t], ixB[t]
    sh = int((PA[i] & PB[j]).sum()); m = VA[i] & VB[j]; n = int(m.sum())
    ag = int(((np.abs(RA0[i] - RB0[j]) <= TOL) & m).sum())
    fails.append((t, sh, n, ag, ag / n if n else float("nan"), "full test passed, first-10 rule failed" if (t, t) in allk else
                  ("under 40 shared sessions" if sh < MIN_SHARED else "returns disagree")))
print(f"\n## same-symbol pairs present in both overlaps (>= {MIN_SHARED} sessions each): {len(both)}; in THE MAP {len(both) - len(fails)}; NOT in the map {len(fails)}"
      f" (two identities under the frozen rule)")
from collections import Counter
print(f"  reasons: {dict(Counter(f[5] for f in fails))}")
for t, sh, n, ag, s, why in fails:
    tag = ("*A" if t in evA else "") + ("*B" if t in evB else "")
    print(f"  {t}{tag}: shared {sh}, agree {ag}/{n} = {s:.3f} — {why}")
print("\n## beside: renames (a != b) passing the full test but NOT the first-10 rule (not in the map)")
x = P[(~P.first10_equal) & (P.a != P.b)]
print(f"  {len(x)} pairs; involving an event ticker on either side: {int(sum((a in evA) or (b in evB) for a, b in zip(x.a, x.b)))}")
for r in x.sort_values("b").itertuples(index=False):
    if (r.a in evA) or (r.b in evB):
        print(f"  {r.b}{'*' if r.b in evB else ''} ~ {r.a}{'*' if r.a in evA else ''}  shared {r.shared_sessions}, agree {r.agree}/{r.pairs} = {r.agree_share:.3f}")
print("\n## the three suspected mapping errors the critique named (era-B -> era-A), full-test numbers whatever the verdict")
for b, a in (("LC", "HAPN"), ("PSTG", "P"), ("OSTK", "NXH")):
    for bb, aa in ((b, a), (a, b)):
        if aa in ixA and bb in ixB:
            i, j = ixA[aa], ixB[bb]
            sh = int((PA[i] & PB[j]).sum()); m = VA[i] & VB[j]; n = int(m.sum())
            ag = int(((np.abs(RA0[i] - RB0[j]) <= TOL) & m).sum())
            print(f"  era-B {bb} vs era-A {aa}: shared {sh}, agree {ag}/{n} = {ag / n if n else float('nan'):.3f} | in THE MAP: {(aa, bb) in okk}")
        else:
            print(f"  era-B {bb} vs era-A {aa}: not testable (era-A {aa} present {aa in ixA}, era-B {bb} present {bb in ixB}; >= {MIN_SHARED} overlap sessions needed)")
for b, a in (("DWAC", "DJT"), ("PTRA", "PTRAQ"), ("GPS", "GAP")):
    assert (a, b) in okk, f"frozen assert failed: {b}->{a} not found"
print("\nASSERT OK: DWAC->DJT, PTRA->PTRAQ and GPS->GAP are in the map.")
# identity per event ticker  (REWRITTEN after run 1 — run 1 keyed an unmapped era-B ticker by its bare symbol, which silently
# merged it BY NAME with the era-A ticker of the same symbol; the frozen text says a same-symbol pair that fails is TWO identities.
# The pair test above is unchanged and its counts are identical between the two runs.)
mapB = {}
amb = []
for b, g in OFF.groupby("b"):
    if len(g) == 1:
        mapB[b] = g.a.iloc[0]
    else:
        amb.append(b)
allA_syms = set(pd.read_csv(C.HERE / "population.tsv", sep="\t", dtype=str, keep_default_na=False).query("era == 'A'").ticker)
fullpass_same = set(P[(P.a == P.b)].a)
out = []
for b in sorted(evB):
    if b in mapB:
        st, idl, ida = ("mapped_same_symbol" if mapB[b] == b else "mapped_rename"), mapB[b], mapB[b]
    elif b in amb:
        st, idl, ida = "AMBIGUOUS_multi_counterpart", b + "#B", b + "#B"
    elif b in setA and b in setB and b in fullpass_same:
        st, idl, ida = "same_symbol_full_test_PASS_first10_FAIL", b + "#B", b            # literal: two identities; alt: one
    elif b in setA and b in setB:
        st, idl, ida = "same_symbol_returns_disagree(symbol reuse)", b + "#B", b + "#B"
    elif b in allA_syms:
        st, idl, ida = "untestable_symbol_also_has_era_A_events", b, b                    # literal: own symbol -> merges by name
    else:
        st, idl, ida = "unmapped_no_counterpart", b, b
    out.append(("B", b, idl, ida, st))
for a in sorted(evA):
    out.append(("A", a, a, a, "era_A_own_symbol"))
I = pd.DataFrame(out, columns=["era", "ticker", "identity_frozen", "identity_alt", "status"])
I.to_csv(C.HERE / "identity_map_event_tickers.tsv", sep="\t", index=False)
print(f"\n## identity for event tickers (era-A events keep their own symbol; era-B event tickers: {len(evB)})")
print("   identity_frozen = the frozen rule taken literally (map = first-10 candidate rule AND full test; a same-symbol pair not in the map = two identities, keyed SYM#B)")
print("   identity_alt    = the same, except a same-symbol pair that PASSES the full 40-session / 90% test but fails the first-10 rounding rule is ONE identity")
for k, n in sorted(Counter(I[I.era == 'B'].status).items()):
    tk = sorted(I[(I.era == 'B') & (I.status == k)].ticker)
    print(f"   {k}: {n}" + (f": {tk}" if n <= 60 and not k.startswith("mapped_same") and k != "unmapped_no_counterpart" else ""))
ambA = [a for a in evA if a in multi_a.index]
print(f"   era-A event tickers claimed by more than one era-B ticker (both map to the one era-A identity; no conflict): {len(ambA)}: {sorted(ambA)}")
ev2 = ev.merge(I, on=["era", "ticker"], how="left")
assert ev2.identity_frozen.notna().all()
for col in ("identity_frozen", "identity_alt"):
    both_eras = ev2.groupby(col).era.nunique(); both_sets = ev2.groupby(col).set.nunique()
    print(f"   [{col}] identities in the population: {ev2[col].nunique()} (raw symbols {ev.ticker.nunique()}, (era, symbol) {len(ev.groupby(['era', 'ticker']))});"
          f" with events in BOTH eras {int((both_eras > 1).sum())}; in BOTH discovery and confirm {int((both_sets > 1).sum())};"
          f" with >= 3 confirm events {int((ev2[ev2.set == 'CONF'].groupby(col).size() >= 3).sum())}")
x2 = P[(~P.first10_equal) & (P.a != P.b)]
x2 = x2[[(b in evB) for b in x2.b]]
print(f"   (beside) era-B EVENT tickers with a different-symbol era-A counterpart that passes the full test but not the first-10 rule: {x2.b.nunique()} tickers, {len(x2)} pairs"
      f" (flat-price instruments match each other under the 0.002 test; none is added to either identity column)")
print(f"identity_pairs_all.tsv sha256 {C.sha(C.HERE / 'identity_pairs_all.tsv')}")
print(f"identity_map_event_tickers.tsv sha256 {C.sha(C.HERE / 'identity_map_event_tickers.tsv')}")
