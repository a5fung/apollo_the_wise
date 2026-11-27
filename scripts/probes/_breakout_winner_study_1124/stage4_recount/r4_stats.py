"""R4 stage 3b recount (blind): the discovery statistic from the prereg text (5.1/5.2) + the EP text it cites (5.1: thirds, ties, MH, permutation layout).
Discovery events only (era A, E <= 2020-12-31). Writes per-feature raw statistics; the floors (condition 3, B4 tag) are applied in r4_decide.py AFTER stage-2 outputs
may be opened. Permutation: u = default_rng(1124).random((10000, n)) over events in the fixed order (era, E, ticker); within each (era, month) stratum the labels of the
events scored on the feature are re-dealt among those events in key order."""
import json, sys, time
from collections import OrderedDict
import numpy as np, pandas as pd
import r4_common as C

NPERM, NBOOT = 10000, 2000
GROUPS = OrderedDict([("volatility", ["f1"]), ("size", ["f2", "f3"]), ("strength", ["f4", "f5", "f6"]), ("run-up", ["f7", "f8", "f9"]),
                      ("highs", ["f10", "f11"]), ("base", ["f12", "f13", "f14"]), ("tightness", ["f15", "f16"]), ("volume", ["f17", "f18"]),
                      ("averages", ["f19", "f20"]), ("trend", ["f21", "f22"]), ("stage", ["f23"]), ("open", ["f24a", "f24b"])])
TWO_GROUP = {"f11", "f14", "f23"}


def thirds_assign(vals, strata_codes, min_n=6):
    """vals (float array, NaN = unscored), strata_codes int array -> assign array (-1 unscored/ineligible, 0 bottom, 1 mid, 2 top)."""
    assign = np.full(len(vals), -1, np.int8)
    for s in np.unique(strata_codes):
        idx = np.flatnonzero((strata_codes == s) & np.isfinite(vals))
        m = len(idx)
        if m < min_n:
            continue
        v = vals[idx]
        order = np.argsort(v, kind="stable")
        sv = v[order]
        sizes = [m // 3 + (1 if i < m % 3 else 0) for i in range(3)]
        bounds = np.cumsum([0] + sizes)
        third_of_pos = np.repeat(np.arange(3), sizes)
        i = 0
        while i < m:
            j = i
            while j + 1 < m and sv[j + 1] == sv[i]:
                j += 1
            mid = (i + j) // 2          # lower middle of the block's positions
            t = third_of_pos[mid]
            assign[idx[order[i:j + 1]]] = t
            i = j + 1
    return assign


def twogroup_assign(vals, strata_codes, yes_mask):
    """MH eligibility: months with >= 2 of each group among scored events. returns (assign (1 yes / 0 no / -1), eligible)"""
    assign = np.full(len(vals), -1, np.int8)
    for s in np.unique(strata_codes):
        idx = np.flatnonzero((strata_codes == s) & np.isfinite(vals))
        if len(idx) == 0:
            continue
        y = yes_mask[idx]
        if y.sum() >= 2 and (~y).sum() >= 2:
            assign[idx] = np.where(y, 1, 0)
    return assign


class Perm:
    def __init__(self, U, strata_codes, y):
        self.U, self.sc, self.y = U, strata_codes, y.astype(np.float64)
        self.cache = {}

    def perm_for(self, idx, key):
        ck = (key, idx[0], len(idx))
        if ck not in self.cache:
            if len(self.cache) > 80:
                self.cache.clear()
            self.cache[ck] = np.argsort(self.U[:, idx], axis=1).astype(np.int16)
        return self.cache[ck]

    def logratios(self, assign, kind, mask_key=None):
        """permuted log ratios (NPERM,) for the assignment (thirds: 2 vs 0; two-group: MH yes vs no)."""
        S = self.U.shape[0]
        mask_key = hash((assign >= 0).tobytes())
        if kind == "thirds":
            wt, wb = np.zeros(S), np.zeros(S); nt = nb = 0
            for s in np.unique(self.sc[assign >= 0]):
                idx = np.flatnonzero((self.sc == s) & (assign >= 0))
                perm = self.perm_for(idx, (mask_key, s))
                L = self.y[idx]; a = assign[idx]
                top, bot = (a == 2), (a == 0)
                wt += (top[perm] * L[None, :]).sum(1); wb += (bot[perm] * L[None, :]).sum(1)
                nt += int(top.sum()); nb += int(bot.sum())
            sm = (wt == 0) | (wb == 0)
            rt = np.where(sm, (wt + .5) / (nt + 1), wt / nt); rb = np.where(sm, (wb + .5) / (nb + 1), wb / nb)
            return np.log(rt / rb)
        num, den = np.zeros(S), np.zeros(S)
        for s in np.unique(self.sc[assign >= 0]):
            idx = np.flatnonzero((self.sc == s) & (assign >= 0))
            perm = self.perm_for(idx, (mask_key, s))
            L = self.y[idx]; a = assign[idx]
            g1 = (a == 1)
            n1, n0 = int(g1.sum()), int((~g1).sum()); N = n1 + n0
            A = (g1[perm] * L[None, :]).sum(1); Bw = L.sum() - A
            num += A * n0 / N; den += Bw * n1 / N
        sm = (num == 0) | (den == 0)
        return np.log(np.where(sm, (num + .5) / (den + .5), num / np.where(den == 0, 1, den)))


def observed(assign, kind, y, sc):
    """pooled stats from an assignment: dict(rate_top, rate_mid, rate_bot, ratio, logr, n_top, n_bot, w_top, w_bot, blocks=[(per-stratum counts)])"""
    blocks = []
    for s in np.unique(sc[assign >= 0]):
        idx = np.flatnonzero((sc == s) & (assign >= 0)); a = assign[idx]; L = y[idx]
        if kind == "thirds":
            blocks.append((s, int((a == 2).sum()), float(L[a == 2].sum()), int((a == 0).sum()), float(L[a == 0].sum()), int((a == 1).sum()), float(L[a == 1].sum())))
        else:
            blocks.append((s, int((a == 1).sum()), float(L[a == 1].sum()), int((a == 0).sum()), float(L[a == 0].sum()), 0, 0.0))
    return blocks


def ratio_from_blocks(blocks, kind, sel=None):
    B = blocks if sel is None else [blocks[i] for i in sel]
    if kind == "thirds":
        nt = sum(b[1] for b in B); wt = sum(b[2] for b in B); nb = sum(b[3] for b in B); wb = sum(b[4] for b in B)
        if nt == 0 or nb == 0:
            return np.nan, (nt, wt, nb, wb)
        sm = wt == 0 or wb == 0
        rt = (wt + .5) / (nt + 1) if sm else wt / nt; rb = (wb + .5) / (nb + 1) if sm else wb / nb
        return rt / rb, (nt, wt, nb, wb)
    num = den = 0.0
    for (_, n1, a, n0, b, _, _) in B:
        N = n1 + n0
        num += a * n0 / N; den += b * n1 / N
    nt = sum(b[1] for b in B); wt = sum(b[2] for b in B); nb = sum(b[3] for b in B); wb = sum(b[4] for b in B)
    if num == 0 or den == 0:
        return (num + .5) / (den + .5), (nt, wt, nb, wb)
    return num / den, (nt, wt, nb, wb)


def main():
    C.assert_pins()
    FT = pd.read_parquet(C.BIG / f"r4_feature_table{C.SUF}.parquet")
    O = pd.read_parquet(C.BIG / f"r4_outcomes_disc{C.SUF}.parquet")
    D = FT[FT.set == "DISC"].merge(O[["era", "ticker", "D", "win", "monster", "clean", "adr_tail", "fail", "win_untrunc", "win_hiE", "win_E1", "full_window", "proxy"]],
                                   on=["era", "ticker", "D"])
    D = D.sort_values(["era", "E", "ticker"]).reset_index(drop=True)
    n = len(D)
    log = open(C.OUTD / f"stage3b_stats{C.SUF}.log", "w")

    def P(*a):
        s = " ".join(str(x) for x in a); print(s, flush=True); log.write(s + "\n"); log.flush()
    assert (D.era == "A").all() and D.E.max() <= "2020-12-31"
    y = D.win.to_numpy().astype(np.float64)
    sc = pd.factorize(D.era + "|" + D.month)[0]
    yr = np.array([int(x[:4]) for x in D.E])
    P(f"discovery events {n}; winners {int(y.sum())} ({y.mean():.4%}); 2017-19 rate {y[yr <= 2019].mean():.4%} (n={int((yr <= 2019).sum())})")
    t0 = time.time()
    U = np.random.default_rng(1124).random((NPERM, n))
    pr = Perm(U, sc, y)
    feats = {}
    # f24a / f24b populations
    f24 = D.f24.to_numpy()
    above = D.f24_above.to_numpy() == 1
    cols = {f: D[f].to_numpy() for f in [f"f{i}" for i in range(1, 24) if i != 24] + ["B1", "B2", "B3", "B4"]}
    cols["f24a"] = np.where(above, f24, np.nan); cols["f24b"] = np.where(~above, f24, np.nan)
    names = [f"f{i}" for i in range(1, 24)] + ["f24a", "f24b"]
    # decide kind per feature (tie-heavy fallback, size rules) -- outcome-free
    spec = {}
    for f in names + ["B1", "B2", "B3", "B4"]:
        v = cols[f]; sco = np.isfinite(v)
        if f in TWO_GROUP:
            yes = v == 1.0
            spec[f] = dict(kind="two", yes=yes, note="two-group")
            continue
        a = thirds_assign(v, sc)
        nsc = int(sco.sum())
        top, bot = int((a == 2).sum()), int((a == 0).sum())
        if (top < 0.20 * nsc or bot < 0.20 * nsc) and f not in ("B1", "B2", "B3", "B4"):
            vals, cnt = np.unique(v[sco], return_counts=True)
            mc = vals[np.argmax(cnt)]
            spec[f] = dict(kind="two", yes=(v == mc), note=f"tie-heavy fallback (top {top / nsc:.1%} bottom {bot / nsc:.1%} of scored): most common value {mc} vs rest")
        else:
            spec[f] = dict(kind="thirds", note="thirds")
    rows = []
    desc_only = {}
    for f in names + ["B1", "B2", "B3", "B4"]:
        v = cols[f]; sp = spec[f]; sco = np.isfinite(v); nsc = int(sco.sum())
        t1 = time.time()
        if sp["kind"] == "thirds":
            a = thirds_assign(v, sc)
        else:
            a = twogroup_assign(v, sc, sp["yes"])
            # size rule: smaller group among scored discovery events under 100 or under 15%
            ny = int((sp["yes"] & sco).sum()); nn = nsc - ny
            small = min(ny, nn)
            if f in names and (small < 100 or small < 0.15 * nsc):
                desc_only[f] = f"smaller group {small} of {nsc} (<100 or <15%)"
        if f in ("f24a", "f24b") and nsc < 300:
            desc_only[f] = f"only {nsc} scored (<300)"
        kind = "thirds" if sp["kind"] == "thirds" else "two"
        blocks = observed(a, kind, y, sc)
        ratio, (nt, wt, nb, wb) = ratio_from_blocks(blocks, kind)
        lr = np.log(ratio)
        pl = pr.logratios(a, kind)
        p2 = (1 + int((np.abs(pl) >= abs(lr) - 1e-12).sum())) / (NPERM + 1)
        sd = float(pl.std(ddof=1))
        # ex-2020: strata of years <= 2019
        yrs_blocks = [int(yr[np.flatnonzero(sc == b[0])[0]]) for b in blocks]
        sel = [i for i, yb in enumerate(yrs_blocks) if yb <= 2019]
        r19, c19 = ratio_from_blocks(blocks, kind, sel)
        # bootstrap over blocks
        rngb = np.random.default_rng(1124)
        nbk = len(blocks); bs = []
        for _ in range(NBOOT):
            pick = rngb.integers(0, nbk, nbk)
            r_, _ = ratio_from_blocks(blocks, kind, pick.tolist())
            bs.append(r_)
        lo, hi = np.nanpercentile(bs, [5, 95])
        mid_rate = (sum(b[6] for b in blocks) / max(1, sum(b[5] for b in blocks))) if kind == "thirds" else np.nan
        rows.append(dict(feature=f, kind=sp["kind"], note=sp["note"], n_scored=nsc, n_strata=len(blocks), n_top=nt, w_top=wt, n_bot=nb, w_bot=wb,
                         rate_top=wt / nt if nt else np.nan, rate_bot=wb / nb if nb else np.nan, rate_mid=mid_rate, ratio=ratio, p2=p2, sd_perm=sd,
                         z_own=abs(lr) / sd, ratio_ex2020=r19, ci_lo=lo, ci_hi=hi, desc_only=desc_only.get(f, "")))
        P(f"{f:5s} {sp['kind']:6s} n={nsc:5d} top {wt:.0f}/{nt} bot {wb:.0f}/{nb} ratio {ratio:.3f} p2 {p2:.4f} ex2020 {r19:.3f} CI [{lo:.2f},{hi:.2f}] z {abs(lr) / sd:.2f} "
          f"{'DESC-ONLY ' + desc_only.get(f, '') if f in desc_only else ''} [{sp['note'][:60]}] ({time.time() - t1:.0f}s)")
    R_ = pd.DataFrame(rows)
    R_.to_csv(C.OUTD / f"r4_stats_own{C.SUF}.tsv", sep="\t", index=False)
    json.dump({"desc_only": desc_only}, open(C.OUTD / f"r4_desc_only{C.SUF}.json", "w"))
    # ---------------- common sets and z (EP 5.2 cond 6) -------------------------------------------------
    cand = [f for f in names if f not in desc_only]
    P("candidates (not description-only):", cand)
    common_all = np.ones(n, bool)
    for f in cand:
        if f in ("f24a", "f24b"):
            continue
        common_all &= np.isfinite(cols[f])
    P(f"common set (all candidates except 24a/24b): {int(common_all.sum())} of {n} discovery events")
    zrows = []

    def z_on(f, mask, tag):
        v = np.where(mask, cols[f], np.nan)
        sp = spec[f]
        if sp["kind"] == "thirds":
            a = thirds_assign(v, sc); kind = "thirds"
        else:
            a = twogroup_assign(v, sc, sp["yes"] & mask); kind = "two"
        blocks = observed(a, kind, y, sc)
        if not blocks:
            return np.nan, np.nan, int((a >= 0).sum())
        ratio, _ = ratio_from_blocks(blocks, kind)
        pl = pr.logratios(a, kind)
        return abs(np.log(ratio)) / float(pl.std(ddof=1)), ratio, int((a >= 0).sum())
    for gname, members in GROUPS.items():
        mem = [f for f in members if f in cand]
        if not mem:
            continue
        gm = np.ones(n, bool)
        for f in mem:
            if f not in ("f24a", "f24b"):
                gm &= np.isfinite(cols[f])
        for f in mem:
            zg, rg, ng = z_on(f, gm & (common_all if f in ("f24a", "f24b") else True), "grp")
            za, ra, na = z_on(f, common_all, "all")
            zrows.append(dict(feature=f, group=gname, grp_common_n=int(gm.sum()), z_grp=zg, ratio_grp=rg, n_grp=ng, z_all=za, ratio_all=ra, n_all=na))
            P(f"  z {f:5s} group {gname:10s} z_grp {zg:.2f} (ratio {rg:.3f}, set {int(gm.sum())}) z_all {za:.2f} (ratio {ra:.3f}, set {int(common_all.sum())})")
    pd.DataFrame(zrows).to_csv(C.OUTD / f"r4_stats_z{C.SUF}.tsv", sep="\t", index=False)
    D.to_parquet(C.OUTD / f"r4_disc_frame{C.SUF}.parquet", index=False)
    P(f"done {time.time() - t0:.0f}s")


if __name__ == "__main__":
    main()
