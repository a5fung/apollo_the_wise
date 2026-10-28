"""Tests for #711 step 7b — the power check (scripts/probes/_705_asis_1026/06b_power.py; the registration
docs/analysis/cb_asis_step7b_power_prereg_2026-10-27.md §4-§7, §11) and the `--method` / `--columns` switches of 06_groups.py. Synthetic
fixtures only (a SYNTHETIC shape built from a factor world with hold-driven blanks and tied columns — never the real shape file); the one
real-data test (the default 06_groups dry run reproducing the pinned blocks) carries a skip guard naming the data and re-runs into a
temporary printout (R64).

Covers (§11): the shape file holds only §4.1's contents and the thin-pair rule zeroes a pair under 30 shared rows; the gap coupling follows
the latent hold rank and survives a plant (C3's Spearman reads negative on a reversed rank); the tie step is monotone and reproduces a
run-size vector; the coherent plant moves the block columns by Delta_B and the oracle hits at the target; C2 catches a misaligned plant;
each method finds a strong two-way split on a toy world and reads one group on a single population run THROUGH the pipeline (two toy
worlds, by reduction — see WHITENED_TOY / UNWHITENED_TOY); M3w's and M3u's p-values are roughly uniform on single-population sets through
the pipeline; parallel analysis keeps planted components on a toy spectrum; the selection rule on hand-made score tables (a qualifier, the per-block line, the tie order, C1's outcome, Fallback 1,
Fallback 2, the size-line source); every gate refuses (no dry run, a MISMATCH, a pin above the marker, an existing output or ledger row,
--shape before the freeze, a non-default --method on --dry-run or --run without POWER COMPLETE, a default --run before POWER COMPLETE);
06_groups under the defaults reproduces the pinned k-sweep and Claims blocks; the identifier scan on 06b_power.py with both lists. Plus:
the vectorized k-means equals the registered one, the null cache equals regeneration, the real-data seal, the fresh-interpreter import belt,
and a CI-safe end-to-end 7b dry run on a synthetic shape file. Fix card (2026-10-27, two read-only reviews; 06b R95-R100): M3's null under a
REUSED space carries the tested rows' spectrum while the own-space path is unchanged; the null cache is trusted by key + code stamp only;
both 7b gates need the power printout made by the modules on disk, pinned and ledgered, with only the registered outcomes; --power refuses
on a shape n other than 658. Finish card (2026-10-28, 7b Re-registration 1; 06b R101-R104): the selection falls through to the gap-free arm
whenever no method qualifies on the 75 columns (item 4; R87 superseded); the M3 noise floor's bootstrap arm tests each resample's DISTINCT
rows and assigns every row (item 3); the sealed real-data loader set is derived, and the test enumerates it the same way and names the
members; the M3 calibration assertion runs on a gap-free, tie-free Gaussian shape at n = 658 (the gapped world a printed readout). The
run path under each carried method and the `pattern_free` descriptions are in tests/test_asis_groups.py (beside the synthetic world they
run on).

DISCLOSED — the toy worlds of the per-method split test were SEARCHED (2026-10-27, synthetic only, no real shape read): through the
rank-normal pipeline a planted group's separation in the WHITENED space is capped at sqrt(1 / (s (1 - s))) (2.0 for a 50 / 50 split)
whatever the plant, so the whitened methods (M0, M2w, M3w, M4) read a split only when the whitened space is tiny — the registration's §12
first finding, reproduced here: on the default factor shape (10 factors, noise 1, 12-18 whitened components) every whitened method read ONE
group on a 50 / 50 plant at Delta 4 while the unwhitened ones read it at adjusted Rand 0.96-1.00. Their toy (WHITENED_TOY) is therefore a
one-factor world with strong loadings on every column, the nine block columns independent of the factor, no hold-driven blanks and no
repeated values (3 whitened components: the factor, the plant, one noise axis). The unwhitened methods (M1, M2u, M3u) cannot use it —
unwhitened k-means splits the dominant factor axis (M1 and M2u read k = 2 / 4 on its null) — so their toy (UNWHITENED_TOY) is the default
shape at n = 400, where the coherent plant moves every factor-correlated column. Nothing in 06b_power.py was changed to pass; the worlds
show each method CAN see a strong split and reads one group on a null of the same world — power at the registered 30% target is what
--power measures, never a test.
"""
from __future__ import annotations

import importlib.util
import json
import os
import subprocess
import sys
from pathlib import Path

import numpy as np
import pytest

REPO = Path(__file__).resolve().parents[1]
ASIS = REPO / "scripts" / "probes" / "_705_asis_1026"
DOC7B = REPO / "docs" / "analysis" / "cb_asis_step7b_power_prereg_2026-10-27.md"


def _load(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, str(path))
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


B = _load("asis_power06b", ASIS / "06b_power.py")
G, C, T = B.G, B.C, B.T

REAL_DATA = os.path.exists(C.OUTPUTS["ranges"]) and os.path.exists(T.OUT_7["tiers"]) and os.path.exists(C.FILES["entries_v2"]) \
    and os.path.exists(C.FILES["export_A"]) and os.path.exists(C.FILES["export_B"])
needs_real_data = pytest.mark.skipif(not REAL_DATA, reason="needs the local apollo_data cb702 tree (ranges.tsv, tiers.tsv, windows_v2, the exports, the minute trees)")


# ═════════════════════════════════════════════════════════════════════════════════════════════ a synthetic shape (never the real one)
def synthetic_primary(n: int = 220, nf: int = 10, seed: str = "synth7b", noise: float = 1.0, independent_blocks: bool = False,
                      gaps: bool = True, ties: bool = True, min_load: float = 0.0, short: bool = True, continuous_hold: bool = False) -> tuple:
    """A primary-shaped raw matrix: the 75 primary columns, a factor structure, hold-driven structural blanks (the registered exit look-back
    rule), a few short-history data blanks, integer count columns and the minute with repeated values. -> (X with NaN, cols).
    `gaps=False`: every hold is 61+ (no exit look-back is structurally blank); `ties=False`: no rounded columns (the integer hold stays);
    `min_load > 0`: every column loads on every factor at least that strongly (signs at random) — the WHITENED_TOY knobs, whose worlds
    these three leave byte-identical. The M3 calibration world adds `short=False` (no short-history data blanks) and `continuous_hold=True`
    (a continuous hold, the one repeated-value column left under ties=False): with gaps=False, not one blank cell and not one repeated value."""
    cols = G.run_columns("primary")
    rng = C.rng_for(seed)
    W = rng.normal(size=(nf, len(cols))) * rng.uniform(0.4, 1.4, size=(nf, 1))
    if min_load > 0:
        W = rng.choice([-1.0, 1.0], size=(nf, len(cols))) * rng.uniform(min_load, 1.4, size=(nf, len(cols)))
    X = rng.normal(size=(n, nf)) @ W + noise * rng.normal(size=(n, len(cols)))
    if independent_blocks:                                                        # the nine block columns stand alone (R_BB = I: Delta_B = sep / sqrt 3)
        for b in B.BLOCK_NAMES:
            for c in B.BLOCKS[b]:
                X[:, cols.index(c)] = rng.normal(size=n)
    if gaps:
        hold = np.clip(np.round(np.exp(rng.normal(0.8, 0.9, n))), 1, 60).astype(int)
    else:
        hold = np.clip(np.round(np.exp(rng.normal(4.3, 0.3, n))), 61, 200).astype(int)
    if continuous_hold:                                                           # the same draw count; the values continuous (no repeated value)
        hold = (1.0 + 59.0 * rng.random(n)) if gaps else (61.0 + np.exp(rng.normal(3.0, 0.6, n)))
    X[:, cols.index("hold_sessions_max")] = hold
    for k, c in enumerate(cols):
        if not ties:
            break
        if c.endswith(("sessions_since_hi_5", "sessions_since_hi_60")):
            X[:, k] = np.clip(np.round(np.abs(X[:, k]) * 2), 0, 20)
        if c in ("exit_minute", "entry_minute"):
            X[:, k] = np.clip(np.round(X[:, k] * 60 + 180), 0, 389)
    for i in range(n):
        ok = set(T.exit_lookbacks_defined(hold[i], hold[i]))
        for k, c in enumerate(cols):
            if c.startswith("exit_"):
                base = c[5:]
                for N, names in T.LOOKBACKS.items():
                    if base in names and N not in ok:
                        X[i, k] = np.nan
    short_rows = rng.random(n) < (0.03 if short else 0.0)
    for k, c in enumerate(cols):
        if c.endswith("_60") and c.startswith("entry_"):
            X[short_rows, k] = np.nan
    return X, cols


_SHAPE = {}


def synthetic_shape(n: int = 220, nf: int = 10, noise: float = 1.0, independent_blocks: bool = False, gaps: bool = True, ties: bool = True,
                    min_load: float = 0.0, short: bool = True, continuous_hold: bool = False):
    """(npz contents, facts, ShapeContext, the raw matrix). The default is the factor world with gaps and ties (12-18 whitened components,
    7-8 by parallel analysis — shaped like his). WHITENED_TOY / UNWHITENED_TOY are the per-method split test's worlds (the module docstring
    says why there are two): whitening caps a planted group's separation at sqrt(1 / (s (1 - s))) along its discriminant whatever the
    plant, so with many unit-variance components k-means sits in noise optima (the registration's §8 expectation and §12's first finding);
    and a block collinear with the factors takes a tiny Delta_B at a fixed separation (the plant then lives in a near-degenerate direction
    the pipeline cannot see), which is why the whitened toy's block columns are independent of its factor."""
    key = (n, nf, noise, independent_blocks, gaps, ties, min_load, short, continuous_hold)
    if key not in _SHAPE:
        X, cols = synthetic_primary(n, nf, noise=noise, independent_blocks=independent_blocks, gaps=gaps, ties=ties, min_load=min_load, short=short,
                                    continuous_hold=continuous_hold)
        d = B.shape_from_matrix(X, cols, G.fit_maps(X, cols), C.rng_for("step7b_hold_ties"))
        facts = d.pop("_facts")
        _SHAPE[key] = (d, facts, B.ShapeContext(d), X)
    return _SHAPE[key]


WHITENED_TOY = dict(n=300, nf=1, noise=0.05, independent_blocks=True, gaps=False, ties=False, min_load=0.7)   # 3 whitened components
UNWHITENED_TOY = dict(n=400)                                                                                   # the default shape, more rows


@pytest.fixture(autouse=True)
def _cache_in_tmp(tmp_path, monkeypatch):
    """No test writes M3's null cache into the data tree (06b R83): every path that caches is redirected under tmp_path."""
    monkeypatch.setattr(B, "CACHE_DIR", str(tmp_path / "step7b_cache"))


SPEC_NULL = {"groups": [], "delta": None, "sep": None}


def spec_target(block="B1", delta=1.5, count=None, n=220):
    return {"groups": [(block, count or int(round(0.3 * n)))], "delta": delta, "sep": B.sep_of(delta), "share": "30%"}


# ═════════════════════════════════════════════════════════════════════════════════════════════ the shape (§4.1)
def test_shape_file_holds_only_the_four_summaries_and_the_thin_pair_rule_zeroes_a_pair_under_30_shared_rows(tmp_path):
    d, facts, ctx, X = synthetic_shape()
    assert sorted(d) == sorted(B.SHAPE_KEYS)
    path = str(tmp_path / "shape.npz")
    B.save_shape(d, path)
    back = B.load_shape(path)
    assert sorted(back) == sorted(B.SHAPE_KEYS) and back["n"] == 220 and back["cols"] == G.run_columns("primary")
    assert np.array_equal(back["masks"], d["masks"]) and np.allclose(back["R"], d["R"])
    np.savez(str(tmp_path / "extra.npz"), **{k: d[k] for k in B.SHAPE_KEYS}, rows=np.zeros(3))      # a file carrying anything else refuses
    with pytest.raises(C.GuardStop):
        B.load_shape(str(tmp_path / "extra.npz"))
    # the thin-pair rule: a column present on 20 rows only shares < 30 rows with every other -> 0 off the diagonal, 1 on it (R76)
    X2 = X.copy()
    cols = G.run_columns("primary")
    k = cols.index("exit_dist_hi_40")
    X2[:, k] = np.nan
    X2[:20, k] = np.linspace(-1, 1, 20)
    d2 = B.shape_from_matrix(X2, cols, G.fit_maps(X2, cols), C.rng_for("t"))
    assert d2["shared"][k, k] == 20 and d2["R_unclipped"][k, k] == 1.0
    assert np.all(d2["R_unclipped"][k, [j for j in range(len(cols)) if j != k]] == 0.0)
    assert d2["_facts"]["pairs_thin"] >= len(cols) - 1
    # R is a unit-diagonal positive-definite correlation; the clipping floor holds; the masks are the blanks; run sizes sum to the non-blank count
    assert np.allclose(np.diag(d["R"]), 1.0) and np.linalg.eigvalsh(d["R"]).min() > 0 and facts["eig_min_after"] >= B.EIG_FLOOR * 0.5
    assert np.array_equal(d["masks"], ~np.isfinite(X)) and set(d["hold_rank"].tolist()) == set(range(220))
    for j in range(len(cols)):
        assert ctx.runs[j].sum() == int(np.isfinite(X[:, j]).sum())
    # the hold rank orders the holds (ties broken by the seeded draw, R92)
    hold = X[:, cols.index("hold_sessions_max")]
    order = np.argsort(d["hold_rank"])
    assert np.all(np.diff(hold[order]) >= 0)


# ═════════════════════════════════════════════════════════════════════════════════════════════ the made-up set (§4.2)
def test_gap_coupling_follows_the_latent_hold_rank_and_survives_a_plant_and_reads_negative_on_a_reversed_rank():
    d, facts, ctx, X = synthetic_shape()
    st = B.make_set(ctx, "N1", "plain", 0, SPEC_NULL)
    c3 = B.check_c3(ctx, st)
    assert c3["blank_ok"] and c3["spearman_ok"] and abs(c3["spearman"] - ctx.hold_gap_spearman) < 1e-12
    assert ctx.hold_gap_spearman > 0.5                                        # a longer hold -> more exit look-backs defined
    # the masks are HIS masks as a set (a permutation of the rows), assigned by the latent hold rank
    assert sorted(map(tuple, st["masks"].astype(int).tolist())) == sorted(map(tuple, ctx.masks.astype(int).tolist()))
    rank = np.argsort(np.argsort(st["hold_latent"], kind="stable"), kind="stable")
    assert np.array_equal(st["masks"], ctx.mask_by_rank[rank])
    # a plant on B3 (exit-day columns) moves no mask: the same latent step-1 hold -> the same masks; C3 still holds
    sp = spec_target("B3")
    stp = B.make_set(ctx, "curve", "B3_d1.5", 0, sp)
    rank_p = np.argsort(np.argsort(stp["latent1"][:, ctx.j_hold], kind="stable"), kind="stable")
    assert np.array_equal(stp["masks"], ctx.mask_by_rank[rank_p]) and B.check_c3(ctx, stp)["spearman_ok"]
    assert stp["latent"][:, ctx.j_hold].tolist() == stp["latent1"][:, ctx.j_hold].tolist()      # the hold's delta is 0 (§4.4)
    # a REVERSED coupling reads a negative Spearman (far from the real value): C3 catches it
    masks_rev = ctx.mask_by_rank[::-1][rank]
    sp_rev = B.spearman(st["hold_latent"], (~masks_rev[:, ctx.lookback_idx]).sum(1))
    assert sp_rev < 0 and round(sp_rev, 3) != round(ctx.hold_gap_spearman, 3)
    # a SHUFFLED coupling reads near 0
    sh = ctx.mask_by_rank[C.rng_for("shuffle").permutation(ctx.n)]
    assert abs(B.spearman(st["hold_latent"], (~sh[:, ctx.lookback_idx]).sum(1))) < 0.3


def test_tie_step_is_monotone_and_reproduces_a_run_size_vector():
    rng = C.rng_for("ties")
    X = rng.normal(size=(40, 2))
    masks = np.zeros((40, 2), dtype=bool)
    masks[:5, 1] = True
    runs = [np.array([3, 1, 2, 10, 24]), np.array([35])]
    out = B.tie_step(X, masks, runs)
    assert np.isnan(out[:5, 1]).all() and np.isfinite(out[:, 0]).all()
    _u, counts = np.unique(out[:, 0], return_counts=True)
    assert counts.tolist() == [3, 1, 2, 10, 24]                                   # his run sizes, from the smallest value up
    order = np.argsort(X[:, 0], kind="stable")
    assert np.all(np.diff(out[order, 0]) >= 0)                                    # monotone in the latent value
    assert np.unique(out[5:, 1]).size == 1                                        # one run -> one shared value
    with pytest.raises(C.GuardStop):
        B.tie_step(X, masks, [np.array([40]), np.array([30])])                      # sizes not summing to the non-blank count
    assert B.run_sizes_of(np.array([2.0, 1.0, np.nan, 2.0, 3.0])).tolist() == [1, 2, 1]


def test_coherent_plant_moves_the_block_columns_by_delta_b_and_the_oracle_hits_at_the_target():
    d, facts, ctx, X = synthetic_shape()
    for b in B.BLOCK_NAMES:
        sep = B.sep_of(1.5)
        sh = ctx.shift(b, sep)
        delta_b = ctx.delta_b(b, sep)
        assert all(abs(sh[k] - delta_b) < 1e-9 for k in ctx.block_idx[b])          # the three block columns move by Delta_B each
        assert sh[ctx.j_hold] == 0.0
        full = delta_b * (ctx.R[:, ctx.block_idx[b]] @ np.linalg.inv(ctx.R[np.ix_(ctx.block_idx[b], ctx.block_idx[b])]) @ np.ones(3))
        assert abs(ctx.mahalanobis(full) - sep) < 1e-6                            # the separation is fixed at sep before the hold is zeroed
        assert abs(ctx.mahalanobis(ctx.shift(b, B.sep_of(3.0))) / ctx.mahalanobis(sh) - 2.0) < 1e-9
    sp = spec_target("B2")
    st = B.make_set(ctx, "curve", "B2_d1.5", 3, sp, through=3)
    assert (st["labels"] == 1).sum() == 66 and st["k_true"] == 2                    # an EXACT count
    assert np.allclose(st["latent"][st["labels"] == 1] - st["latent1"][st["labels"] == 1], ctx.shift("B2", sp["sep"]))
    hits = [B.oracle(ctx, B.make_set(ctx, "curve", "B2_d1.5", i, sp, through=3), sp)["hit"] for i in range(10)]
    assert sum(hits) >= 8
    assert B.oracle(ctx, st, SPEC_NULL) == {"hit": None, "ari": None}
    # the three-group world: two planted groups, three labels
    sp3 = {"groups": [("B1", 60), ("B3", 40)], "delta": 1.5, "sep": B.sep_of(1.5), "share": "x"}
    st3 = B.make_set(ctx, "three", "x", 0, sp3, through=3)
    assert np.bincount(st3["labels"]).tolist() == [120, 60, 40] and st3["k_true"] == 3


def test_c2_catches_a_misaligned_plant():
    d, facts, ctx, X = synthetic_shape()
    sp = spec_target("B1", delta=2.0)
    pooled = {}
    for i in range(8):                                                             # one set's AUC has sd ~0.03; C2 pools 50 sets (R78)
        c2i = B.check_c2(ctx, B.make_set(ctx, "curve", "B1_d2.0", i, sp), sp)
        assert c2i["monotone_ok"] == c2i["columns"]
        for key, (al, line, af) in c2i["auc"].items():
            pooled.setdefault(key, []).append((al, line, af))
    for (_g, col), vals in pooled.items():
        al, line, af = (float(np.mean([v[j] for v in vals])) for j in range(3))
        assert al >= line, (col, al, line)
        assert abs(line - (B.Phi(ctx.delta_b("B1", sp["sep"]) / np.sqrt(2)) - 0.02)) < 1e-12 and 0.4 < af < 1.0
    st = B.make_set(ctx, "curve", "B1_d2.0", 1, sp)
    c2 = B.check_c2(ctx, st, sp)
    bad = dict(st)
    bad["labels"] = st["labels"][C.rng_for("mis").permutation(ctx.n)]          # the plant on other rows than the labels say
    c2b = B.check_c2(ctx, bad, sp)
    assert all(abs(al - 0.5) < 0.1 and al < line for al, line, _af in c2b["auc"].values())
    lost = dict(st, latent=st["latent1"])                                        # a lost plant reads near 0.50 as well
    assert all(al < line for al, line, _af in B.check_c2(ctx, lost, sp)["auc"].values())
    broken = dict(st)
    Xh = st["X"].copy()
    k = ctx.block_idx["B1"][0]
    idx = np.flatnonzero(~st["masks"][:, k])
    Xh[idx[:2], k] = Xh[idx[:2], k][::-1] + np.array([5.0, -5.0])                  # a re-ordering breaks (b)
    broken["X"] = Xh
    assert B.check_c2(ctx, broken, sp)["monotone_ok"] < c2["columns"]


# ═════════════════════════════════════════════════════════════════════════════════════════════ the methods (§5)
def test_vectorized_kmeans_equals_the_registered_kmeans_and_the_rank_statistics_match():
    rng = np.random.default_rng(5)
    Z = rng.normal(size=(300, 9))
    Z[:120] += 2.5
    for k in (2, 3, 5):
        a = B.kmeans_v(Z, k, C.rng_for(f"twin{k}"), 20)
        b = G.kmeans(Z, k, C.rng_for(f"twin{k}"), 20)
        assert B.ari(a["labels"], b["labels"]) == pytest.approx(1.0) and a["inertia"] == pytest.approx(b["inertia"], rel=1e-10)
    ps_a = B.prediction_strength_v(Z, 2, C.rng_for("ps"), halves=5)
    ps_b = G.prediction_strength(Z, 2, C.rng_for("ps"), halves=5)
    assert ps_a == pytest.approx(ps_b, abs=1e-9)
    many = B.kmeans_many(np.stack([Z, Z[::-1]]), 2, C.rng_for("many"), 10)
    assert many["labels"].shape == (2, 300) and B.ari(many["labels"][0], many["labels"][1][::-1]) == pytest.approx(1.0)
    for _ in range(5):
        x, y = rng.integers(0, 4, 50), rng.integers(0, 3, 50)
        assert B.ari(x, y) == pytest.approx(G.adjusted_rand(x, y))
    assert B.ari(np.array([0, 0, 1, 1]), np.array([1, 1, 0, 0])) == pytest.approx(1.0)
    assert B.auc(np.array([2, 3, 4]), np.array([0, 1])) == 1.0 and B.auc(np.array([1, 1]), np.array([1, 1])) == 0.5
    assert B.spearman([1, 2, 3], [1, 2, 3]) == pytest.approx(1.0) and B.spearman([1, 2, 3], [3, 2, 1]) == pytest.approx(-1.0)
    assert B.rankdata(np.array([3.0, 1.0, 1.0, 2.0])).tolist() == [4.0, 1.5, 1.5, 3.0]
    lo, hi = B.wilson(240, 300)
    assert 0.75 < lo < 0.8 < hi < 0.85 and B.wilson(0, 10)[0] == 0.0 and B.wilson(10, 10)[1] == pytest.approx(1.0)
    assert B.spread_all_trades(1.5) == pytest.approx(1.236, abs=1e-3)              # the registration's "about 1.2"
    assert B.Phi(0) == 0.5 and B.sep_of(1.5) == pytest.approx(2.598, abs=1e-3)


def test_parallel_analysis_keeps_planted_components_on_a_toy_spectrum():
    rng = C.rng_for("pa")
    n, p = 400, 20
    F = rng.normal(size=(n, 3)) * np.array([4.0, 3.0, 2.0])
    L = rng.normal(size=(3, p))
    Z = F @ L + rng.normal(size=(n, p))
    pa = B.ParallelAnalysis(Z, C.rng_for("pa_perm"))
    assert pa.m == 3 and pa.kept_by_rule == 3 and pa.transform(Z).shape == (n, 3)
    assert np.allclose(pa.transform(Z).var(0, ddof=1), pa.lam, rtol=1e-6)         # unwhitened: the components keep their eigenvalues
    noise = rng.normal(size=(n, p))
    pn = B.ParallelAnalysis(noise, C.rng_for("pa_perm2"))
    assert pn.m == B.PA_MIN and pn.kept_by_rule <= 2                               # at least 2 kept, nothing above the noise line
    sp = B.Spaces(Z, "step7b_M1_toy_perm")
    assert sp.m("pa") == 3 and sp.m("whitened") >= 3 and sp.transform(Z, "whitened").shape[1] == sp.m("whitened")


def _toy_world(ctx):
    """A strong two-way split through the pipeline (a 50 / 50 B1 plant at Delta 4 on `ctx`) and a single population of the same world."""
    sp = spec_target("B1", delta=4.0, count=ctx.n // 2)
    sp["share"] = "50%"
    strong = B.make_set(ctx, "curve", "B1_d4.0", 0, sp)
    null = B.make_set(ctx, "N1", "plain", 1, SPEC_NULL)
    return sp, strong, null


@pytest.mark.parametrize("name", B.METHODS)
def test_each_method_finds_a_strong_two_way_split_on_a_toy_world_and_reads_one_group_on_a_single_population_through_the_pipeline(name):
    d, facts, ctx, X = synthetic_shape(**(WHITENED_TOY if B.SPACE_OF[name] == "whitened" else UNWHITENED_TOY))   # the module docstring says why two
    sp, strong, null = _toy_world(ctx)
    n_min = 30
    fit = B.run_method(name, B.Spaces(strong["Z"], "step7b_M1_toy_perm"), n_min, f"step7b_{name}_toy", cache=False)
    sc = B.score(fit, strong)
    assert fit["k"] == 2 and sc["hit"] and sc["ari"] >= 0.9, (name, fit["k"], sc, fit["detail"])
    assert fit["means"].shape == (2, fit["m"]) and fit["labels"].shape == (ctx.n,)
    assert np.array_equal(B.assign(fit, B.Spaces(strong["Z"], "step7b_M1_toy_perm").transform(strong["Z"], fit["space"])), fit["labels"]) or name in ("M3w", "M3u")
    fit0 = B.run_method(name, B.Spaces(null["Z"], "step7b_M1_toy0_perm"), n_min, f"step7b_{name}_toy0", cache=False)
    sc0 = B.score(fit0, null)
    assert fit0["k"] == 1 and sc0["false_alarm"] is False and fit0["labels"].max() == 0, (name, fit0["k"], fit0["detail"])


def _m3_top_p(ctx, n_sets: int, tag: str, cache: bool) -> dict:
    """The top-level p of M3w / M3u on `n_sets` single-population sets of `ctx` run THROUGH the pipeline (never raw draws)."""
    ps = {"w": [], "u": []}
    for i in range(n_sets):
        st = B.make_set(ctx, "N1", "plain", 100 + i, SPEC_NULL)
        for kind in ("w", "u"):
            fit = B.split_rule(st["Z"], 30, f"step7b_M3{kind}_{tag}_{i}", kind, cache=cache)
            ps[kind].append(fit["top_p"])
    return ps


def test_m3_p_values_are_roughly_uniform_on_single_population_sets_through_the_pipeline(monkeypatch, capsys):
    """The registered calibration check, on a world where uniformity is exact (review, low): one Gaussian population at n = 658 with NO
    blank cell and NO repeated value (gaps=False, ties=False, short=False, continuous_hold=True), so the data's and the null's left singular vectors share one
    distribution once the spectrum is matched. The gapped, tied world (the default synthetic shape at n = 658, ~9,800 blanks) is run beside
    as a PRINTED readout, never asserted: there M3w's p-values are pulled down by the zero-filled gaps — a property of the data the power
    run measures on the N1 cells, not of the implementation."""
    monkeypatch.setattr(B, "M3_NULL", 200)                                         # the resolution, not the construction (never raw draws)
    d, facts, ctx, X = synthetic_shape(658, gaps=False, ties=False, short=False, continuous_hold=True)
    assert ctx.n_blank == 0 and all(len(ctx.runs[k]) == 658 for k in range(ctx.p))   # not one blank cell, not one repeated value
    ps = _m3_top_p(ctx, 24, "unif", cache=True)                                   # the whitened null caches under tmp (the autouse fixture)
    for kind, vals in ps.items():
        v = np.sort(vals)
        emp = np.arange(1, len(v) + 1) / len(v)
        assert 0.3 < np.mean(v) < 0.7, (kind, vals)
        assert np.max(np.abs(emp - v)) < 0.35 and np.max(np.abs(emp - 1 / len(v) - v)) < 0.35, (kind, vals)
        assert sum(1 for x in vals if x < 0.01) == 0
    dg, fg, ctx_g, Xg = synthetic_shape(658)                                       # the gapped, tied world: a readout
    pg = _m3_top_p(ctx_g, 8, "gapped", cache=True)
    with capsys.disabled():
        print(f"\n[readout] M3 top-level p on the GAPPED synthetic world (n = 658, {ctx_g.n_blank} blanks), 8 sets: "
              f"M3w {[round(x, 3) for x in pg['w']]} ({sum(1 for x in pg['w'] if x < 0.01)} below 0.01); "
              f"M3u {[round(x, 3) for x in pg['u']]} ({sum(1 for x in pg['u'] if x < 0.01)} below 0.01) — not asserted")


def test_m3_null_under_a_reused_space_carries_the_tested_rows_spectrum_and_the_own_space_path_is_unchanged(monkeypatch):
    """06b R95 (fix card): a mode-A run tests OTHER rows in the primary's reused reduction, where their covariance is neither the identity
    nor diag(lam). One population (the synthetic primary world at n = 440, maps fitted on all rows so no extrapolated tail enters), the
    reduction fitted on its first 220 rows: the top-level p of M3w / M3u on the whole 440 (a superset, like + ONE-STREAM) and on a half of
    the 220 (like a year run) reads roughly uniform under the tested rows' own spectrum, while the unit null read the registered 'split'
    on every superset (the defect). On the rows the space was fitted on the null is the registered one, bit for bit."""
    monkeypatch.setattr(B, "M3_NULL", 200)                                         # the resolution, never the construction
    ps = {k: [] for k in ("w_sup", "u_sup", "w_half", "u_half", "w_sup_unit")}
    for i in range(8):
        X, cols = synthetic_primary(n=440, seed=f"reused{i}")
        maps = G.fit_maps(X, cols)
        Zp, _e, _b = G.standardize(X[:220], cols, maps)
        Zs, _e, _b = G.standardize(X, cols, maps)
        sp = B.Spaces(Zp, f"step7b_M1_reused_{i}_perm")
        half = np.sort(C.rng_for(f"half{i}").permutation(220)[:110])
        for kind in ("w", "u"):
            red = sp.red["whitened" if kind == "w" else "pa"]
            fs = B.split_rule(Zs, 30, f"step7b_M3{kind}_reused_s_{i}", kind, top_space=red)
            fh = B.split_rule(Zp[half], 30, f"step7b_M3{kind}_reused_h_{i}", kind, top_space=red)
            own = B.split_rule(Zp, 30, f"step7b_M3{kind}_reused_o_{i}", kind, top_space=red)
            assert fs["nodes"][0]["null"] == "rescaled" and fh["nodes"][0]["null"] == "rescaled" and own["nodes"][0]["null"] == "own"
            ps[f"{kind}_sup"].append(fs["top_p"])
            ps[f"{kind}_half"].append(fh["top_p"])
            if kind == "w":
                Zps = red.transform(Zs)
                idx, _f = B.two_means_index(Zps, C.rng_for(f"step7b_M3w_reused_s_{i}_starts"), B.M3_STARTS)
                null = B.null_indices_whitened(len(Zps), Zps.shape[1])
                ps["w_sup_unit"].append((1 + int((null <= idx).sum())) / (B.M3_NULL + 1.0))
    for k in ("w_sup", "u_sup", "w_half", "u_half"):
        v = np.array(ps[k])                                                            # seeded, so deterministic: a uniform-ish spread, none at the level
        assert 0.2 < v.mean() < 0.85 and int((v < 0.01).sum()) == 0, (k, v)
    assert int((np.array(ps["w_sup_unit"]) <= 0.02).sum()) >= 7, ps["w_sup_unit"]        # the unit null on a superset: a 'split' whatever the data
    # the own-space null is the registered one, bit for bit (every power-run set, every child, the floor's seeded refits)
    sp = B.Spaces(Zp, "step7b_M1_reused_x_perm")
    Zw, Zu = sp.transform(Zp, "whitened"), sp.transform(Zp, "pa")
    assert np.allclose(B.tested_spectrum(Zw), 1.0, atol=1e-9) and np.allclose(B.tested_spectrum(Zu), sp.red["pa"].lam, rtol=1e-9, atol=1e-9)
    nw, kw = B.null_for_node(Zw, sp.red["whitened"], "w", C.rng_for("x"), True)
    assert kw == "own" and np.array_equal(nw, B.null_indices_whitened(220, Zw.shape[1]))
    nu, ku = B.null_for_node(Zu, sp.red["pa"], "u", C.rng_for("y"), True)
    assert ku == "own" and np.array_equal(nu, B.null_indices_unwhitened(220, Zu.shape[1], sp.red["pa"].lam, C.rng_for("y")))
    nr, kr = B.null_for_node(Zw[half], sp.red["whitened"], "w", C.rng_for("z"), True)
    assert kr == "rescaled" and not np.array_equal(nr, nw)


def test_null_cache_equals_regeneration_and_is_keyed_by_the_registered_name(tmp_path, monkeypatch):
    monkeypatch.setattr(B, "M3_NULL", 50)
    monkeypatch.setattr(B, "CACHE_DIR", str(tmp_path / "cache"))
    a = B.null_indices_whitened(80, 4, cache=False)
    b = B.null_indices_whitened(80, 4, cache=True)
    c = B.null_indices_whitened(80, 4, cache=True)
    assert np.array_equal(a, b) and np.array_equal(b, c) and os.path.exists(B.null_cache_path(80, 4))
    with np.load(B.null_cache_path(80, 4)) as z:
        assert str(z["key"]) == "step7b_null_80_4" and int(z["draws"]) == 50 and str(z["stamp"]) == B.null_code_stamp()
    # R98: a foreign cache (the right counts, another key, no stamp) is ignored and replaced; a stale stamp regenerates; the stamp follows
    # the null path's code and the registered counts
    path = B.null_cache_path(80, 4)
    np.savez(path, idx=np.zeros(50), draws=50, starts=B.M3_STARTS, key="not_the_registered_key")
    assert not B.null_cache_valid(path, 80, 4)
    assert np.array_equal(B.null_indices_whitened(80, 4, cache=True), a) and B.null_cache_valid(path, 80, 4)
    np.savez(path, idx=np.zeros(50), draws=50, starts=B.M3_STARTS, key="step7b_null_80_4", stamp="other code")
    assert not B.null_cache_valid(path, 80, 4) and np.array_equal(B.null_indices_whitened(80, 4, cache=True), a)
    np.savez(path, idx=np.zeros(50), draws=50, starts=B.M3_STARTS, key="step7b_null_80_4", stamp=B.null_code_stamp())
    assert B.null_cache_valid(path, 80, 4) and np.array_equal(B.null_indices_whitened(80, 4, cache=True), np.zeros(50))     # trusted: key + counts + stamp
    stamp = B.null_code_stamp()
    monkeypatch.setattr(B, "M3_NULL", 51)
    assert B.null_code_stamp() != stamp and not B.null_cache_valid(path, 80, 4)
    monkeypatch.setattr(B, "M3_NULL", 50)
    assert B.null_code_stamp() == stamp and len(stamp) == 64
    W, _r = B.null_draws(80, 4, draws=50)
    assert W.shape == (50, 80, 4) and np.allclose(W.var(1, ddof=1), 1.0)           # re-whitened by its own PCA: unit variance, all m kept
    u1 = B.null_indices_unwhitened(80, 4, np.array([4.0, 2.0, 1.0, 0.5]), C.rng_for("nu"))
    u2 = B.null_indices_unwhitened(80, 4, np.array([4.0, 2.0, 1.0, 0.5]), C.rng_for("nu"))
    assert np.array_equal(u1, u2) and 0 < u1.mean() < 1


# ═════════════════════════════════════════════════════════════════════════════════════════════ scoring and the one rule that picks (§6)
def _tab(n1=5, n2=10, target=(85, 85, 85), small=(30, 30, 30), curve=None):
    t = {"N1": (n1, 300), "N2": (n2, 300)}
    for b, h in zip(B.BLOCK_NAMES, target):
        t[("curve", 1.5, b)] = (h, 100)
    for b, h in zip(B.BLOCK_NAMES, small):
        t[("small", b)] = (h, 40)
    for delta, hits in (curve or {1.0: (5, 5, 5), 2.0: (38, 38, 38), 3.0: (40, 40, 40)}).items():
        for b, h in zip(B.BLOCK_NAMES, hits):
            t[("curve", delta, b)] = (h, 40)
    t[("three",)] = (20, 40)
    return t


def test_selection_rule_on_hand_made_score_tables():
    base = {("registered", "M0"): _tab(target=(20, 25, 30)), ("pattern_free", "M0"): _tab(target=(20, 25, 30))}
    for nm in B.ELIGIBLE:
        base[("registered", nm)] = _tab(n1=40)                                     # everyone fails N1 unless overridden
        base[("pattern_free", nm)] = _tab(n1=40)
    # a qualifier
    tabs = dict(base)
    tabs[("registered", "M3u")] = _tab(n1=10, n2=20, target=(80, 80, 85))
    dec = B.decide(tabs)
    assert dec["c1_ok"] and dec["carried"] == "M3u" and dec["outcome"] == "carried M3u on registered" and not dec["fallback1"]
    q = dec["qual"]["registered"]["M3u"]
    assert q["qualifies"] and q["power"] == pytest.approx(245 / 3)
    # the per-block line: pooled 245 but one block at 69 -> not a qualifier
    tabs[("registered", "M3u")] = _tab(n1=10, n2=20, target=(69, 88, 88))
    assert not B.decide(tabs)["qual"]["registered"]["M3u"]["qualifies"]
    # the tie order: two qualifiers within 5 points -> the earlier of M1, M2w, M2u, M3w, M3u, M4; beyond 5 points -> the higher
    tabs[("registered", "M3u")] = _tab(n1=10, n2=20, target=(88, 88, 88))
    tabs[("registered", "M2w")] = _tab(n1=10, n2=20, target=(85, 85, 85))
    assert B.decide(tabs)["carried"] == "M2w"
    tabs[("registered", "M2w")] = _tab(n1=10, n2=20, target=(80, 80, 80))
    assert B.decide(tabs)["carried"] == "M3u"
    tabs[("registered", "M4")] = _tab(n1=10, n2=20, target=(99, 99, 99))
    assert B.decide(tabs)["carried"] == "M4"
    # C1's outcome: M0 at the target -> one style with power, whatever qualifies
    tabs[("registered", "M0")] = _tab(target=(80, 80, 80))
    dec = B.decide(tabs)
    assert not dec["c1_ok"] and dec["outcome"] == "one style with power (C1)" and dec["carried"] is None and dec["size_source"] == ("M0", "registered")
    # Fallback 1: no method qualifies on the 75 columns (here none even passes N1) -> the selection repeats on the gap-free arm
    tabs = dict(base)
    tabs[("pattern_free", "M1")] = _tab(n1=12, n2=25, target=(82, 82, 82))
    dec = B.decide(tabs)
    assert dec["fallback1"] and dec["carried"] == "M1" and dec["outcome"] == "carried M1 on pattern_free" and dec["columns"] == "pattern_free"
    # Fallback 2: no qualifier on either arm -> no style we could show we would see (Fallback 1 fired on the way: the 56-column arm was
    # searched too); the size-line source = the highest-power method passing both FA lines, the 75-column arm first (R103)
    tabs = dict(base)
    tabs[("registered", "M2u")] = _tab(n1=10, n2=20, target=(50, 50, 50))
    tabs[("registered", "M3w")] = _tab(n1=10, n2=20, target=(60, 60, 60))
    dec = B.decide(tabs)
    assert dec["outcome"] == "no style we could show we would see" and dec["carried"] is None and dec["fallback1"] and dec["columns"] == "registered"
    assert dec["size_source"] == ("M3w", "registered") and "75" not in dec["size_source_why"] and "registered columns" in dec["size_source_why"]
    # ... the 56-column arm's passing methods serve the size line only when none passes both lines on the 75 (R103: the 75 first)
    tabs56 = dict(tabs)
    tabs56[("pattern_free", "M4")] = _tab(n1=10, n2=20, target=(70, 70, 70))        # passes both lines on 56 with more power than M3w on 75
    assert B.decide(tabs56)["size_source"] == ("M3w", "registered")
    tabs56 = dict(base)
    tabs56[("pattern_free", "M4")] = _tab(n1=10, n2=20, target=(70, 70, 70))
    dec56 = B.decide(tabs56)
    assert dec56["outcome"] == "no style we could show we would see" and dec56["size_source"] == ("M4", "pattern_free") and dec56["columns"] == "registered"
    # ... and M0 when no method passes both false-alarm lines on either arm (its false-alarm rate printed beside)
    tabs = dict(base)
    for nm in B.ELIGIBLE:
        tabs[("registered", nm)] = _tab(n1=10, n2=40, target=(50, 50, 50))
    dec = B.decide(tabs)
    assert dec["outcome"] == "no style we could show we would see" and dec["size_source"] == ("M0", "registered")
    # Re-registration 1 item 4 (R103; R87 superseded): some method passes N1 on the 75 columns, none qualifies there, one qualifies on the
    # 56 -> Fallback 1 fires on "no qualifier on the 75", the selection repeats on the 56-column arm, and that qualifier is CARRIED on
    # pattern_free (under R87 this case read Fallback 2)
    tabs87 = dict(base)
    tabs87[("registered", "M2u")] = _tab(n1=10, n2=20, target=(50, 50, 50))        # passes N1 on the 75, does not qualify
    tabs87[("pattern_free", "M3u")] = _tab(n1=10, n2=20, target=(85, 85, 85))      # qualifies on the gap-free arm
    dec87 = B.decide(tabs87)
    assert dec87["fallback1"] and dec87["columns"] == "pattern_free" and dec87["carried"] == "M3u" and dec87["outcome"] == "carried M3u on pattern_free"
    assert dec87["size_source"] == ("M3u", "pattern_free") and B.size_line(tabs87, dec87["size_source"])["delta_star"] == 1.5     # the hand table carries the whole curve
    tabs87[("registered", "M1")] = _tab(n1=10, n2=20, target=(81, 81, 81))         # a 75-column qualifier is carried before any 56-column one
    assert B.decide(tabs87)["outcome"] == "carried M1 on registered" and not B.decide(tabs87)["fallback1"]
    sl = B.size_line(tabs, dec["size_source"])
    assert "M0's false-alarm rate" in sl["text"] and sl["delta_star"] == 2.0       # 114 of 120 at Delta 2.0 passes; the target (75 of 300) does not
    # the size line: Delta* = the smallest Delta with pooled power >= 80%
    t = _tab(target=(85, 85, 85), curve={1.0: (5, 5, 5), 2.0: (38, 38, 38), 3.0: (40, 40, 40)}, small=(20, 20, 20))
    sl = B.size_line({("registered", "M3u"): t}, ("M3u", "registered"))
    assert sl["delta_star"] == 1.5 and "1.5 within-group spreads" in sl["text"] and "about 1.2 of each measure" in sl["text"] and "a 15% group at Delta 2.0: 50 in 100" in sl["text"]
    t2 = _tab(target=(50, 50, 50), curve={1.0: (5, 5, 5), 2.0: (38, 38, 38), 3.0: (40, 40, 40)})
    assert B.size_line({("registered", "M1"): t2}, ("M1", "registered"))["delta_star"] == 2.0
    t3 = _tab(target=(50, 50, 50), curve={1.0: (5, 5, 5), 2.0: (20, 20, 20), 3.0: (30, 30, 30)})
    assert "more than 3.0" in B.size_line({("registered", "M1"): t3}, ("M1", "registered"))["text"]
    arm = {("pattern_free", "M1"): {"N1": (3, 300), "N2": (5, 300), ("curve", 1.5, "B1"): (60, 100), ("curve", 1.5, "B2"): (60, 100), ("curve", 1.5, "B3"): (60, 100)}}
    assert "not run on the 56 columns" in B.size_line(arm, ("M1", "pattern_free"))["text"]
    # tabulate / oracle_table on hand rows
    rows = [{"world": "N1", "cell": "plain", "i": 0, "fresh": False, "columns": "registered", "method": "M1", "false_alarm": True, "hit": None, "block": "", "delta": None, "oracle_hit": None, "oracle_ari": None},
            {"world": "curve", "cell": "B1_d1.5", "i": 0, "fresh": False, "columns": "registered", "method": "M1", "false_alarm": None, "hit": True, "block": "B1", "delta": 1.5, "oracle_hit": True, "oracle_ari": 0.7},
            {"world": "curve", "cell": "B1_d1.5", "i": 0, "fresh": False, "columns": "registered", "method": "M0", "false_alarm": None, "hit": False, "block": "B1", "delta": 1.5, "oracle_hit": True, "oracle_ari": 0.7},
            {"world": "curve", "cell": "B1_d1.5", "i": 9, "fresh": True, "columns": "registered", "method": "M1", "false_alarm": None, "hit": True, "block": "B1", "delta": 1.5, "oracle_hit": True, "oracle_ari": 0.7}]
    tabs = B.tabulate(rows)
    assert tabs[("registered", "M1")] == {"N1": (1, 1), ("curve", 1.5, "B1"): (1, 1)} and tabs[("registered", "M0")] == {("curve", 1.5, "B1"): (0, 1)}
    assert B.oracle_table(rows) == {("curve", 1.5, "B1"): (1, 1, 0.7)}
    assert sum(n for _w, _c, n, _s in B.cells()) == 1420 and len(B.target_cells()) == 3
    assert sum(n for w, _c, n, s in B.cells() if B.in_gap_free_arm(w, s)) == 900
    # R93: the registered exact counts at n = 658; the same shares at another n (the synthetic end-to-end shape)
    assert B.plant_counts(658) == {"curve": 197, "small": 99, "three": (329, 197, 132)} and B.plant_counts() == B.plant_counts(658)
    specs = {(w, c): s for w, c, _n, s in B.cells(658)}
    assert specs[("curve", "B1_d1.5")]["groups"] == [("B1", 197)] and specs[("small", "B3_d2.0")]["groups"] == [("B3", 99)]
    assert specs[("three", "B1B3_d1.5")]["groups"] == [("B1", 197), ("B3", 132)] and specs[("three", "B1B3_d1.5")]["share"] == "329/197/132"
    assert B.plant_counts(220) == {"curve": 66, "small": 33, "three": (110, 66, 44)}


def test_score_reads_false_alarms_and_hits():
    st = {"k_true": 1, "labels": np.zeros(10, int)}
    assert B.score({"k": 2, "labels": np.arange(10) % 2}, st) == {"false_alarm": True, "hit": None, "ari": None}
    assert B.score({"k": 1, "labels": np.zeros(10, int)}, st)["false_alarm"] is False
    truth = np.array([0] * 7 + [1] * 3)
    st2 = {"k_true": 2, "labels": truth}
    assert B.score({"k": 2, "labels": truth}, st2)["hit"] and B.score({"k": 3, "labels": truth}, st2)["hit"] is False
    assert B.score({"k": 2, "labels": np.arange(10) % 2}, st2)["hit"] is False


# ═════════════════════════════════════════════════════════════════════════════════════════════ the real-data seal, pins, gates (§11)
def _enumerate_loaders() -> list:
    """The sealed set, enumerated here the way 06b derives it (R104): load_* / read_* / preload_* callables of the four modules, MinuteStore,
    its alias on C.R, and G.build_features. -> [(holder name, attribute)]."""
    out = []
    for label, mod in (("C", C), ("P", P_()), ("T", T), ("G", G)):
        for nm in sorted(dir(mod)):
            if nm.startswith(("load_", "read_", "preload_")) and callable(getattr(mod, nm)):
                out.append((label, nm))
        if callable(getattr(mod, "MinuteStore", None)):
            out.append((label, "MinuteStore"))
    out.append(("C.R", "read_minute_file"))
    out.append(("G", "build_features"))
    return out


def test_seal_real_loaders_makes_every_real_data_loader_raise_and_unseal_restores():
    """R104: the sealed set is derived and the test enumerates it the same way, naming the members — the nine loaders the first build
    hand-listed must all be in it, plus every other load_* / read_* / preload_* callable the four modules hold."""
    holders = {"C": C, "P": P_(), "T": T, "G": G, "C.R": C.R}
    want = _enumerate_loaders()
    got = [(next(k for k, v in holders.items() if v is h), nm) for h, nm in B.sealed_loader_names()]
    assert got == want and len(want) >= 21
    names = {f"{h}.{nm}" for h, nm in want}
    assert {"G.load_inputs", "G.build_features", "T.load_inputs", "T.read_tsv", "P.load_all", "P.preload_minutes", "C.load_daily_subset",
            "C.load_done_all", "C.load_raw_close_subset"} <= names                                                 # the first build's hand list
    assert {"C.load_sessions", "C.load_lexicon", "C.load_alias", "C.read_minute_file", "C.load_done", "C.load_splits", "C.load_splits_sealed",
            "C.MinuteStore", "C.R.read_minute_file", "P.read_frames", "P.read_windows"} <= names                   # the review's unsealed ones
    orig = {(h, nm): getattr(holders[h], nm) for h, nm in want}
    B.seal_real_loaders()
    try:
        for h, nm in want:
            with pytest.raises(C.GuardStop):
                getattr(holders[h], nm)()
        B.seal_real_loaders()                                                        # idempotent: a second seal keeps the originals
        assert len(B._SEALED) == len(want)
    finally:
        B.unseal_real_loaders()
    assert all(getattr(holders[h], nm) is fn for (h, nm), fn in orig.items()) and B._SEALED == []
    assert G.load_inputs is orig[("G", "load_inputs")] and C.R.read_minute_file is C.read_minute_file


def P_():
    return B.P


def _gate_env(tmp_path, monkeypatch, dry_complete=True, mismatch=0, modules_line=None, groups_dry=True, freeze=True, shape=True):
    """A complete world under tmp_path: both registrations with the pins pasted below ONE marker, both dry runs complete, the shape file
    and its printout, an empty ledger; every path of 06b / 06 / 05 / asis_common monkeypatched."""
    d = tmp_path / "w"
    d.mkdir(parents=True, exist_ok=True)
    paths = {"shape": str(d / "06b_shape.txt"), "dry": str(d / "06b_dry.txt"), "run": str(d / "06b_power.txt"), "refused": str(d / "06b_refused.txt"), "pins": str(d / "06b_pins.txt")}
    monkeypatch.setattr(B, "P06B", paths)
    monkeypatch.setattr(B, "SHAPE_NPZ", str(d / "step7b_shape.npz"))
    monkeypatch.setattr(B, "POWER_TSV", str(d / "step7b_power.tsv"))
    monkeypatch.setattr(B, "CACHE_DIR", str(d / "cache"))
    gpaths = {"dry": str(d / "06_dry.txt"), "run": str(d / "06_run.txt"), "refused": str(d / "06_refused.txt"), "pins": str(d / "06_pins.txt"), "power": paths["run"]}
    monkeypatch.setattr(G, "P06", gpaths)
    monkeypatch.setattr(G, "OUT_G", {k: str(d / f"step7_{k}.tsv") for k in ("features", "groups", "descriptions", "stability")})
    for key in ("ranges", "candidates", "coverage"):
        (d / f"{key}.tsv").write_text("eid\n", encoding="utf-8")
    (d / "check.tsv").write_text("stmt_id\n", encoding="utf-8")
    (d / "03.txt").write_text("run\n", encoding="utf-8")
    (d / "05dry.txt").write_text("dry\nRESULT: 1 claims, 1 OK, 0 MISMATCH\nDRY RUN COMPLETE\n", encoding="utf-8")
    (d / "05run.txt").write_text("run\nRUN COMPLETE\n", encoding="utf-8")
    (d / "tiers.tsv").write_text("eid\n", encoding="utf-8")
    monkeypatch.setattr(C, "OUTPUTS", {k: str(d / f"{k}.tsv") for k in ("candidates", "ranges", "coverage")})
    monkeypatch.setattr(T, "CHECK_R1_R5", str(d / "check.tsv"))
    monkeypatch.setattr(T, "P03_RUN", str(d / "03.txt"))
    monkeypatch.setattr(T, "OUT_7", {"tiers": str(d / "tiers.tsv")})
    monkeypatch.setattr(T, "P05", {"dry": str(d / "05dry.txt"), "run": str(d / "05run.txt"), "refused": str(d / "05ref.txt"), "pins": str(d / "05pins.txt")})
    (d / "ledger.tsv").write_text("stage\tpath\tsha256\ttime\n", encoding="utf-8")
    monkeypatch.setattr(C, "LEDGER", str(d / "ledger.tsv"))
    monkeypatch.setattr(C, "ledger_verify", lambda: [])
    monkeypatch.setattr(C, "subs_list_sha", lambda paths=None: "subs")
    doc7 = d / "doc7.md"
    doc7.write_text("# step 7\n\nbody\n\n<!-- FREEZE -->\n## Freeze record\n", encoding="utf-8")
    monkeypatch.setattr(T, "DOC7", str(doc7))
    monkeypatch.setattr(G, "DOC7", str(doc7))
    doc7b = d / "doc7b.md"
    doc7b.write_text("# step 7b\n\nbody 7b\n\n<!-- FREEZE -->\n## Freeze record\n", encoding="utf-8")
    monkeypatch.setattr(B, "DOC7B", str(doc7b))
    if shape:
        dd, _f, _ctx, _X = synthetic_shape()
        B.save_shape(dd, B.SHAPE_NPZ)
        Path(paths["shape"]).write_text("shape\nSHAPE COMPLETE\n", encoding="utf-8")
    ml = B.module_shas_line() if modules_line is None else modules_line
    lines = ["# dry", f"- modules: {ml}", f"RESULT: 3 claims, {3 - mismatch} OK, {mismatch} MISMATCH"] + (["DRY RUN COMPLETE"] if dry_complete else [])
    Path(paths["dry"]).write_text("\n".join(lines) + "\n", encoding="utf-8")
    glines = ["# dry", f"- modules: {G.module_shas_line()}", "RESULT: 33 claims, 33 OK, 0 MISMATCH"] + (["DRY RUN COMPLETE"] if groups_dry else [])
    Path(gpaths["dry"]).write_text("\n".join(glines) + "\n", encoding="utf-8")
    pins = B.pins_b(str(doc7b), paths["dry"])
    if freeze:
        doc7b.write_text(doc7b.read_text(encoding="utf-8") + "\n".join(f"- {k}: {v}" for k, v in pins.items()) + "\n", encoding="utf-8")
    return {"paths": paths, "doc7b": str(doc7b), "doc7": str(doc7), "dir": d, "gpaths": gpaths}


def test_pins_carry_the_7b_keys_and_the_reference_pair():
    pins = B.pins_b(str(DOC7B), str(ASIS / "06b_power_dryrun.txt"), include_outputs=True)
    assert {"doc_body_7b", "doc_body", "doc_body_steps56", "reference_06_groups.py", "reference_06_groups_dryrun", "step7b_shape", "shape7b_printout",
            "06b_power.py", "dryrun7b_printout", "06_groups.py", "dryrun7g_printout", "05_tiers.py", "forbidden_outcomes.txt", "forbidden_identifiers.txt",
            "power7b_printout", "step7b_power"} <= set(pins)
    assert pins["reference_06_groups.py"] == B.REF_06_SHA and pins["reference_06_groups_dryrun"] == B.REF_DRY_SHA
    assert pins["doc_body_7b"] == C.doc_body_sha(str(DOC7B))
    assert "doc_body_7b" in B.stage_pin_keys_b(pins) and "entries" not in B.stage_pin_keys_b(pins)


def test_the_real_7b_registration_is_frozen_with_one_marker_and_its_body_pinned():
    text = DOC7B.read_text(encoding="utf-8")
    assert len(C.marker_spans(text.encode())) == 1
    assert "06b_power.py" in text and "POWER COMPLETE" in text and "--method" in text
    assert B.doc_frozen(str(DOC7B)) == []                                            # doc_body_7b sits below the marker
    assert C.doc_body_sha(str(DOC7B)) == "cf2ec533f2d34a2667c027865c50a692bbaa440ba6dc2727752957c00c5e2d4b"
    assert os.path.exists(B.REF_DRY) and C.sha(B.REF_DRY) == B.REF_DRY_SHA           # the reference copy is the pinned printout


def test_shape_gate_refuses_before_the_freeze_once_run_and_on_an_existing_output(tmp_path, monkeypatch):
    w = _gate_env(tmp_path, monkeypatch, shape=False, freeze=False)
    assert any("not pinned below" in p for p in B.shape_gate(w["doc7b"], w["paths"]))
    doc = Path(w["doc7b"])
    doc.write_text(doc.read_text(encoding="utf-8") + f"- doc_body_7b: {C.doc_body_sha(w['doc7b'])}\n", encoding="utf-8")
    assert B.shape_gate(w["doc7b"], w["paths"]) == []
    Path(w["paths"]["shape"]).write_text("x\n", encoding="utf-8")
    assert any("outputs exist" in p for p in B.shape_gate(w["doc7b"], w["paths"]))
    os.remove(w["paths"]["shape"])
    Path(C.LEDGER).write_text("stage\tpath\tsha256\ttime\nstep7b_shape\tx\ty\tz\n", encoding="utf-8")
    assert any("once means once" in p for p in B.shape_gate(w["doc7b"], w["paths"]))
    doc.write_text(doc.read_text(encoding="utf-8") + "<!-- FREEZE -->\n", encoding="utf-8")       # two markers: not frozen
    assert any("not pinned" in p for p in B.shape_gate(w["doc7b"], w["paths"]))
    assert any("missing" in p for p in B.shape_gate(str(tmp_path / "none.md"), w["paths"]))


def test_power_gate_passes_in_a_complete_world_and_refuses_each_broken_one(tmp_path, monkeypatch):
    w = _gate_env(tmp_path, monkeypatch)
    assert B.power_gate(w["doc7b"], w["paths"]) == []
    w = _gate_env(tmp_path / "a", monkeypatch, dry_complete=False)
    assert any("has not completed" in p for p in B.power_gate(w["doc7b"], w["paths"]))
    w = _gate_env(tmp_path / "b", monkeypatch, mismatch=1)
    assert any("1 MISMATCH" in p for p in B.power_gate(w["doc7b"], w["paths"]))
    w = _gate_env(tmp_path / "c", monkeypatch, modules_line="06b_power.py 0000000000000000")
    assert any("other code" in p for p in B.power_gate(w["doc7b"], w["paths"]))
    w = _gate_env(tmp_path / "d", monkeypatch, groups_dry=False)
    assert any("06_groups' default dry run has not completed" in p for p in B.power_gate(w["doc7b"], w["paths"]))
    w = _gate_env(tmp_path / "e", monkeypatch)
    doc = Path(w["doc7b"])
    text = doc.read_text(encoding="utf-8")
    line = f"- dryrun7b_printout: {B.pins_b(w['doc7b'], w['paths']['dry'])['dryrun7b_printout']}"
    doc.write_text(text.replace(line + "\n", "").replace("<!-- FREEZE -->", line + "\n<!-- FREEZE -->"), encoding="utf-8")    # the pin ABOVE the marker
    assert any("dryrun7b_printout" in p and "freeze marker" in p for p in B.power_gate(w["doc7b"], w["paths"]))
    doc.write_text(text, encoding="utf-8")
    Path(B.POWER_TSV).write_text("x\n", encoding="utf-8")
    assert any("outputs exist" in p for p in B.power_gate(w["doc7b"], w["paths"]))
    os.remove(B.POWER_TSV)
    Path(C.LEDGER).write_text("stage\tpath\tsha256\ttime\nstep7b_power\tx\ty\tz\n", encoding="utf-8")
    assert any("once means once" in p for p in B.power_gate(w["doc7b"], w["paths"]))
    Path(C.LEDGER).write_text("stage\tpath\tsha256\ttime\n", encoding="utf-8")
    os.remove(B.SHAPE_NPZ)
    doc.write_text(text + "- step7b_shape: ABSENT\n", encoding="utf-8")
    assert any("ABSENT" in p and "step7b_shape" in p for p in B.power_gate(w["doc7b"], w["paths"]))
    assert any("missing" in p for p in B.power_gate(str(tmp_path / "none.md"), w["paths"]))


def test_06_groups_refuses_a_non_default_method_on_every_real_data_stage_and_the_default_run_before_power_complete(tmp_path, monkeypatch):
    w = _gate_env(tmp_path, monkeypatch)
    calls = []
    monkeypatch.setattr(G, "load_inputs", lambda say: calls.append("loaded") or (_ for _ in ()).throw(AssertionError("the real matrix was opened")))
    monkeypatch.setattr(C, "rule_modules_loaded", lambda: [])
    for stage in ("--dry-run", "--run"):
        assert G.main([stage, "--method", "M3u"]) == 3                                   # no POWER COMPLETE at all
        assert G.main([stage, "--columns", "pattern_free"]) == 3
    assert calls == []
    refused = Path(G.dry_path_for("M3u", "registered")).read_text(encoding="utf-8")       # 06b R90: its own printout, never the pinned one
    assert "REFUSED" in refused and "POWER COMPLETE" in refused
    assert not os.path.exists(G.P06["dry"]) or "REFUSED" not in Path(G.P06["dry"]).read_text(encoding="utf-8")
    # the default --run before POWER COMPLETE
    probs = G.run_gate(w["doc7"], w["gpaths"])
    assert any("POWER COMPLETE" in p for p in probs)
    # R99: the power printout must be made by the modules on disk, pinned below the 7b marker and ledgered — for BOTH gates; each piece missing refuses
    def _power(outcome, modules=True, pin=True, ledger=True):
        Path(w["paths"]["run"]).write_text("# power\n" + (f"- modules: {B.module_shas_line()}\n" if modules else "") + f"POWER COMPLETE: {outcome}\n", encoding="utf-8")
        doc = Path(w["doc7b"])
        body = "\n".join(ln for ln in doc.read_text(encoding="utf-8").splitlines() if not ln.startswith("- power7b_printout:")) + "\n"
        doc.write_text(body + (f"- power7b_printout: {C.sha(w['paths']['run'])}\n" if pin else ""), encoding="utf-8")
        Path(C.LEDGER).write_text("stage\tpath\tsha256\ttime\n" + ("step7b_power\tx\ty\tz\n" if ledger else "step7b_power_printout\tx\ty\tz\n"), encoding="utf-8")
    _power("carried M1 on registered")
    assert B.named_by_power_complete("M1", "registered", w["doc7b"], w["paths"]["run"]) == []
    assert any("not 'carried M3u on registered'" in p for p in B.named_by_power_complete("M3u", "registered", w["doc7b"], w["paths"]["run"]))
    assert B.named_by_power_complete("M1", "pattern_free", w["doc7b"], w["paths"]["run"]) != []
    _power("carried M1 on registered", modules=False)
    assert any("other code" in p for p in B.named_by_power_complete("M1", "registered", w["doc7b"], w["paths"]["run"]))
    _power("carried M1 on registered", pin=False)
    assert any("not below" in p for p in B.named_by_power_complete("M1", "registered", w["doc7b"], w["paths"]["run"]))
    _power("carried M1 on registered", ledger=False)                                   # a step7b_power_printout row is not the step7b_power row
    assert any("no step7b_power ledger row" in p for p in B.named_by_power_complete("M1", "registered", w["doc7b"], w["paths"]["run"]))
    # the default --run is refused while POWER COMPLETE names a carried method (R90); only the two registered default outcomes unlock it (R99)
    _power("carried M1 on registered")
    assert any("not the registered run" in p for p in B.default_run_gate(w["paths"]["run"], w["doc7b"]))
    _power("one style with power (C1)")
    assert B.default_run_gate(w["paths"]["run"], w["doc7b"]) == []
    _power("no style we could show we would see")
    assert B.default_run_gate(w["paths"]["run"], w["doc7b"]) == [] and B.power_outcome(w["paths"]["run"]) == "no style we could show we would see"
    def _7b_problems():                                                                 # 06_groups' default --run gate carries the 7b problems (B.DOC7B is this world's)
        return [p for p in G.run_gate(w["doc7"], w["gpaths"]) if "06b_power" in p or "POWER COMPLETE" in p or "step7b_power" in p]
    assert _7b_problems() == []
    for miss in ("modules", "pin", "ledger"):
        _power("no style we could show we would see", **{miss: False})
        assert B.default_run_gate(w["paths"]["run"], w["doc7b"]) != [] and _7b_problems() != [], miss
    Path(w["paths"]["run"]).write_text(f"# power\n- modules: {B.module_shas_line()}\nPOWER COMPLETE\n", encoding="utf-8")           # a bare line: no outcome
    _power_sha = C.sha(w["paths"]["run"])
    Path(w["doc7b"]).write_text(Path(w["doc7b"]).read_text(encoding="utf-8") + f"- power7b_printout: {_power_sha}\n", encoding="utf-8")
    Path(C.LEDGER).write_text("stage\tpath\tsha256\ttime\nstep7b_power\tx\ty\tz\n", encoding="utf-8")
    assert B.power_outcome(w["paths"]["run"]) == "" and any("not one of the registered outcomes" in p for p in B.default_run_gate(w["paths"]["run"], w["doc7b"]))
    _power("something unregistered")
    assert any("not one of the registered outcomes" in p for p in B.default_run_gate(w["paths"]["run"], w["doc7b"]))
    assert B.DEFAULT_OUTCOMES == ("one style with power (C1)", "no style we could show we would see")
    Path(w["paths"]["run"]).write_text("# power\nREFUSED: x\n", encoding="utf-8")
    assert B.power_outcome(w["paths"]["run"]) is None and any("has not completed" in p for p in B.default_run_gate(w["paths"]["run"], w["doc7b"]))
    # a step7_groups ledger row refuses the --run whatever else holds
    Path(C.LEDGER).write_text("stage\tpath\tsha256\ttime\nstep7_groups_groups\tx\ty\tz\n", encoding="utf-8")
    assert any("step7_groups ledger row" in p for p in G.run_gate(w["doc7"], w["gpaths"]))
    assert G.ledger_stage_rows("step7_groups_") == ["step7_groups_groups"] and B.ledger_has_stage("step7b_") == []


def test_run_columns_under_pattern_free_follow_section_7_3():
    assert len(G.run_columns("primary", "pattern_free")) == 56 and len(G.run_columns("plus_low", "pattern_free")) == 56
    assert G.run_columns("entry_only", "pattern_free") == G.run_columns("entry_only")
    assert len(G.run_columns("exit_only", "pattern_free")) == 16 and "hold_sessions_max" not in G.run_columns("exit_only", "pattern_free")
    assert len(G.run_columns("with_our_length", "pattern_free")) == 69
    assert not any(c.startswith("exit_") and c[5:] not in G.DAY_OWN for c in G.run_columns("primary", "pattern_free"))
    assert [G.run_columns("primary")[k] for k in G.pattern_free_columns(G.run_columns("primary"))] == G.run_columns("primary", "pattern_free")
    with pytest.raises(ValueError):
        G.run_columns("primary", "other")
    assert "06b_power.py" in G.SCAN_FILES_G and "06b_power.py" in G.MODULE_FILES_G and G.METHODS_7B[0] == "registered" and G.COLUMNS_7B == ("registered", "pattern_free")


def test_identifier_scan_on_06b_with_both_lists_is_clean_and_a_planted_name_fails(tmp_path):
    forb = T.forbidden_all()
    assert C.scan_identifiers([str(ASIS / n) for n in B.SCAN_FILES_B], forb) == []
    assert "06b_power.py" in B.SCAN_FILES_B and "06_groups.py" in B.SCAN_FILES_B
    planted = tmp_path / "p.py"
    planted.write_text("x = 1\nwinner = x\ns = 'setup'\n", encoding="utf-8")
    assert sorted(t for _p, _l, t in C.scan_identifiers([str(planted)], forb)) == ["'setup'", "winner"]


def test_fresh_interpreter_import_of_06b_holds_no_rule_module_and_no_network_client():
    code = ("import importlib.util, json, sys\n"
            f"spec = importlib.util.spec_from_file_location('b06', {str(ASIS / '06b_power.py')!r})\n"
            "m = importlib.util.module_from_spec(spec); sys.modules['b06'] = m; spec.loader.exec_module(m)\n"
            "mods = set(sys.modules)\n"
            "print(json.dumps({'rule': m.C.rule_modules_loaded(), 'net': sorted(mods & {'requests', 'urllib3', 'http.client', "
            "'anthropic', 'openai', 'psycopg2', 'sqlalchemy'}), 'same': m.G is sys.modules['asis_groups06']}))\n")
    r = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, timeout=180, cwd=str(REPO))
    assert r.returncode == 0, r.stderr[-2000:]
    out = json.loads(r.stdout.strip().splitlines()[-1])
    assert out["rule"] == [] and out["net"] == [] and out["same"]


# ═════════════════════════════════════════════════════════════════════════════════════════════ end to end on a synthetic shape (CI-safe)
def test_7b_dry_run_runs_end_to_end_on_a_synthetic_shape_file(tmp_path, monkeypatch):
    w = _gate_env(tmp_path, monkeypatch)
    for name, val in (("DRY_C2_SETS", 3), ("DRY_C5_SETS", 3), ("DRY_C6_SETS", 6), ("DRY_PLUMB", 1), ("M3_NULL", 100)):
        monkeypatch.setattr(B, name, val)
    monkeypatch.setattr(C, "rule_modules_loaded", lambda: [])
    try:
        assert B.main(["--dry-run"]) == 0
    finally:
        B.unseal_real_loaders()
    text = Path(w["paths"]["dry"]).read_text(encoding="utf-8")
    lines = [ln for ln in text.splitlines() if ln.strip()]
    assert lines[-1].startswith("DRY RUN COMPLETE") and C.printout_mismatches(w["paths"]["dry"]) is not None
    for key in ("C6 —", "C2 —", "C5 —", "C7", "projected wall time", "Plumbing", "the whitened 2-means index", "[OK] C2 (b)", "[OK] C3 —", "the shape file holds exactly",
                "the pooled latent through the rank map", "AFTER the tie step", "before the tie step, Re-registration 1 item 1"):      # R101: the claim's arm and the readout
        assert key in text, key
    assert all(nm in text for nm in B.METHODS) and "real-data loaders sealed (R104, derived)" in text
    assert not os.path.exists(B.POWER_TSV) and not os.path.exists(w["paths"]["run"])
    # the shape stage refuses in this world (an output exists); --power refuses without the pins of the new dry run
    assert B.main(["--shape"]) == 3 and "REFUSED" in Path(w["paths"]["refused"]).read_text(encoding="utf-8")
    assert B.main(["--power"]) == 3


def test_power_stage_refuses_before_pass_1_when_the_shape_n_is_not_the_registered_658(tmp_path, monkeypatch):
    """06b R100: a claim that can be read before the run is read before it — the gate passes in this world (every pin below the marker, both
    dry runs complete by the modules on disk), the synthetic shape's n = 220 is not the registered 658, and the stage refuses with no
    POWER COMPLETE, no output and no ledger row (a MISMATCH of any claim but C1 is a refusal, never an outcome)."""
    w = _gate_env(tmp_path, monkeypatch)
    monkeypatch.setattr(C, "rule_modules_loaded", lambda: [])
    assert B.power_gate(w["doc7b"], w["paths"]) == []
    try:
        assert B.main(["--power"]) == 4
    finally:
        B.unseal_real_loaders()
    text = Path(w["paths"]["refused"]).read_text(encoding="utf-8")
    assert "REFUSED: the shape file's n is 220, not the registered 658" in text and "POWER COMPLETE" not in text
    assert not os.path.exists(B.POWER_TSV) and not os.path.exists(w["paths"]["run"]) and B.power_outcome(w["paths"]["run"]) is None
    assert B.ledger_has_stage("step7b_power") == []


def test_run_set_rows_carry_every_method_and_column_set_and_the_noise_floor_refits_the_carried_method():
    d, facts, ctx, X = synthetic_shape(**WHITENED_TOY)
    sp = spec_target("B1", delta=4.0, count=ctx.n // 2)
    res = B.run_set(ctx, "curve", "B1_d4.0", 0, sp, ("registered", "pattern_free"), ("M2w", "M4"), cache=False)
    assert len(res["rows"]) == 4 and {r["columns"] for r in res["rows"]} == {"registered", "pattern_free"} and all(r["hit"] for r in res["rows"])
    assert res["c3"]["spearman_ok"] and res["oracle"]["hit"] and set(res["rows"][0]) == set(B.TSV_COLS)
    # the §7.2 machinery on a toy primary: group means as centroids, the method's assignment, the floor (5 seeded + 5 bootstrap)
    strong = B.make_set(ctx, "curve", "B1_d4.0", 0, sp)
    spaces = B.Spaces(strong["Z"], "step7b_real_M1_primary_perm")
    for name in ("M2w", "M3w", "M4"):
        fit = B.run_method(name, spaces, 30, f"step7b_real_{name}_primary", cache=False)
        primary = {"fit7b": fit, "spaces7b": spaces, "Zp": spaces.transform(strong["Z"], fit["space"]), "Z": strong["Z"]}
        fl = B.noise_floor_7b(primary, 30, cache=False)
        assert len(fl["seeded"]) == 5 and len(fl["bootstrap"]) == 5 and fl["floor"] < 0.1, (name, fl)
        assert np.array_equal(B.assign(fit, primary["Zp"]), fit["labels"]) or name == "M3w"
        assert B.ari(B.assign(fit, primary["Zp"]), fit["labels"]) > 0.95
        assert (fl["boot_rows"] == []) == (name != "M3w")                            # R102: the distinct-row counts travel only under M3


def test_m3_noise_floor_bootstrap_arm_tests_the_resamples_distinct_rows_and_assigns_every_row(monkeypatch):
    """7b Re-registration 1 item 3 (06b R102): under a carried M3w / M3u the five bootstrap refits run the split procedure on each
    resample's DISTINCT rows (about 63% of n) — the resample drawn as registered from `..._floor_boot<i>_boot` — and every row is then
    assigned by nearest leaf mean; the seeded refits and the other methods' bootstrap refits still see n rows."""
    d, facts, ctx, X = synthetic_shape(**WHITENED_TOY)
    sp = spec_target("B1", delta=4.0, count=ctx.n // 2)
    strong = B.make_set(ctx, "curve", "B1_d4.0", 0, sp)
    spaces = B.Spaces(strong["Z"], "step7b_real_M1_primary_perm")
    n = ctx.n
    seen = []
    orig = B.refit_at_k

    def _record(fit, spaces_, Zp, Z, n_min, key, cache=True):
        seen.append((key, len(Zp), len(Z)))
        return orig(fit, spaces_, Zp, Z, n_min, key, cache)
    monkeypatch.setattr(B, "refit_at_k", _record)
    for name in ("M3w", "M2w"):
        seen.clear()
        fit = B.run_method(name, spaces, 30, f"step7b_real_{name}_primary", cache=False)
        primary = {"fit7b": fit, "spaces7b": spaces, "Zp": spaces.transform(strong["Z"], fit["space"]), "Z": strong["Z"]}
        fl = B.noise_floor_7b(primary, 30, cache=False)
        boots = [(k, a, b) for k, a, b in seen if "_floor_boot" in k]
        seeds = [(k, a, b) for k, a, b in seen if "_floor_seed" in k]
        assert len(boots) == 5 and len(seeds) == 5 and all(a == n and b == n for _k, a, b in seeds)
        for i, (key, a, b) in enumerate(boots, 1):
            idx = C.rng_for(f"step7b_real_{name}_floor_boot{i}_boot").integers(0, n, n)        # the registered resample
            distinct = len(np.unique(idx))
            if name == "M3w":
                assert a == b == distinct and 0.55 * n < distinct < 0.72 * n and fl["boot_rows"][i - 1] == distinct, (i, a, distinct)
            else:
                assert a == b == n and fl["boot_rows"] == []
        assert len(fl["bootstrap"]) == 5 and all(0.0 <= x <= 1.0 for x in fl["bootstrap"]) and fl["floor"] < 0.1, (name, fl)
    # the assignment of every row (nearest leaf mean in the top-level space) on a distinct-row refit, directly
    fit = B.run_method("M3w", spaces, 30, "step7b_real_M3w_primary", cache=False)
    Zw = spaces.transform(strong["Z"], "whitened")
    idx = np.unique(C.rng_for("step7b_real_M3w_floor_boot1_boot").integers(0, n, n))
    r = orig(fit, spaces, Zw[idx], strong["Z"][idx], 30, "step7b_real_M3w_floor_boot1", False)
    r["method"] = "M3w"
    lab = B.assign(r, Zw)
    assert lab.shape == (n,) and r["nodes"][0]["n"] == len(idx) and r["nodes"][0]["null"] == "rescaled" and B.ari(lab, fit["labels"]) > 0.9


# ═════════════════════════════════════════════════════════════════════════════════════════════ real data
@needs_real_data
def test_default_06_groups_dry_run_reproduces_the_pinned_k_sweep_and_claims_blocks(tmp_path, monkeypatch):
    paths = dict(G.P06)
    paths["dry"] = str(tmp_path / "dry.txt")                                           # R64: never the pinned printout
    monkeypatch.setattr(G, "P06", paths)
    monkeypatch.setattr(C, "rule_modules_loaded", lambda: [])
    assert G.main(["--dry-run"]) == 0
    lines = Path(paths["dry"]).read_text(encoding="utf-8").splitlines()
    ref = Path(B.REF_DRY).read_text(encoding="utf-8").splitlines()
    rs, rc = B.reference_blocks(ref)
    ns, nc = B.reference_blocks(lines)
    assert len(rs) > 5 and len(rc) == 32 and rs == ns and nc[:32] == rc and len(nc) == 33
    assert "[OK] the k-sweep block and the 32 claim lines above reproduce the reference dry run" in "\n".join(lines)
    assert C.printout_mismatches(paths["dry"]) == 0 and lines[-1].startswith("DRY RUN COMPLETE")
    assert B.reproduces_reference(lines) == (True, "")
    broken = [ln.replace("0.524", "0.525") if ln.startswith("  2  0.524") else ln for ln in lines]
    ok, why = B.reproduces_reference(broken)
    assert not ok and "k sweep differs" in why
