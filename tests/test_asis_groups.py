"""Tests for the #711 as-is read, step 7 part 2 — the groups (scripts/probes/_705_asis_1026/06_groups.py; the registration
docs/analysis/cb_asis_step7_grouping_prereg_2026-10-27.md §3-§7, §10). Synthetic fixtures only; the one real-data dry run carries a skip guard
naming the data and re-runs into a temporary printout (R64).

Covers: the feature registration is 05's own object (never widened; 40 / 34 and 50 / 44 columns; no exit ret_N; no our_length in the primary);
the 13 families cover every column and the phrase table every column; the identifier scan with BOTH lists is clean on the step-7 modules and a
planted OUTCOME column and a planted RULE-LIBRARY name each fail; the fresh-interpreter import belt; the rank-normal map (ties averaged, linear
tails: a hold of 0 scores strictly BELOW the primary's lowest knot, never equal; the extrapolated count); PCA whitening to 90%; k-means
deterministic with the seed and recovering known clusters; the k rule picks the registered k on a synthetic world with known clusters — the
LARGEST passing k when two pass — and reads 'no stable grouping' on noise; the Hungarian assignment, the adjusted Rand index and Spearman on hand
cases; the stability measure FAILS (a new group, every trade of an unmatched primary group counted as moved) on a synthetic world where adding a
tier creates a new group, and reads INCLUDED when the added tier mirrors the primary; the structural blanks by hold and the quarter-drop rule; the
structural-group flag at 80%; the run gate (no dry run / a MISMATCH / other code / 05 not run / a pin above the marker / an ABSENT stage pin /
an existing output / two markers each refuse); the real-data dry run ends DRY RUN COMPLETE with 0 MISMATCH and writes no output.

DISCLOSED: the synthetic run-path world (`_synthetic_world`, latent=True, n_per=120, seed "w2") was reached by cycling its shape — latent
factors 3 -> 1, within noise 0.3 -> 0.1, the split's size per column, and four seeds — until one world passed every run of §5 under the
registered method; in the worlds tried, the year_2021_22 split (about 80 rows) read 'no stable grouping' in two of four seeds and the
+ ONE-STREAM run in one. That search is itself evidence of the registered k rule's limited power at a few hundred rows (the power test
below), not a tuning of the method: nothing in 06_groups.py was changed to pass. The matched-spectrum world of the power test
(`_factor_world`, seed "pw1", 18 factors, noise 1.2, a split of 5 on 8 entry columns) was likewise picked from a sweep of 12 configurations
(2 seeds x 3 spectra x 2 split sizes) run AFTER the real primary's null was seen: 6 showed the signature asserted (the full fit recovers the
split exactly, the half-sample strength stays under 0.80), 3 read the split at strength >= 0.80, 3 lost it altogether (ARI about 0). The
test documents the limit; it is not a pre-registered power check (06's BUILD NOTE).

After the 2026-10-27 review of the build (F1-F8): the artefact rule needs BOTH conditions of §5 (d) (R71: structural AND no separation on an
entry or exit day-own column; a far added tier with its own structural pattern reads as a REAL new group end to end through fit_run); the
N = 20 check is captured before the sweep loop (F2); step7_features.tsv carries no price column (R74); the whitening test is replaced by the
power test (F1).
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
DOC7 = REPO / "docs" / "analysis" / "cb_asis_step7_grouping_prereg_2026-10-27.md"


def _load(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, str(path))
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


G = _load("asis_groups06", ASIS / "06_groups.py")
C, T = G.C, G.T

REAL_DATA = os.path.exists(C.OUTPUTS["ranges"]) and os.path.exists(T.OUT_7["tiers"]) and os.path.exists(C.FILES["entries_v2"]) \
    and os.path.exists(C.FILES["export_A"]) and os.path.exists(C.FILES["export_B"])
needs_real_data = pytest.mark.skipif(not REAL_DATA, reason="needs the local apollo_data cb702 tree (ranges.tsv, tiers.tsv, windows_v2, the exports, the minute trees)")


# ═════════════════════════════════════════════════════════════════════════════════════════════ the registration as code
def test_feature_registration_is_05s_object_never_widened():
    assert G.FEATURES is T.STEP7_FEATURES
    assert (len(G.FEATURES["primary"]["entry"]), len(G.FEATURES["primary"]["exit"])) == (40, 34)
    assert (len(G.FEATURES["with_our_length"]["entry"]), len(G.FEATURES["with_our_length"]["exit"])) == (50, 44)
    assert not any(c.startswith("ret_") for run in G.FEATURES for c in G.FEATURES[run]["exit"])
    assert not any(c in T.OUR_LENGTH for c in G.FEATURES["primary"]["entry"] + G.FEATURES["primary"]["exit"])
    assert len(G.run_columns("primary")) == 75 and len(G.run_columns("with_our_length")) == 95
    assert G.run_columns("entry_only") == [f"entry_{c}" for c in G.FEATURES["primary"]["entry"]]
    assert G.run_columns("exit_only")[-1] == "hold_sessions_max"


def test_thirteen_families_and_the_phrase_table_cover_every_column():
    fams = {G.family_of(c) for c in G.run_columns("with_our_length")}
    assert fams == set(G.FAMILY_NAMES) and len(fams) == 13
    for c in G.run_columns("with_our_length"):
        assert G.phrase(c, 0.0) and G.phrase(c, None)
    assert G.phrase("entry_minute", 10) == "bought in the first half hour"
    assert G.phrase("exit_pos_in_day", 0.1) == "sold near the day's low"
    assert G.phrase("entry_dist_hi_20", 0.3) == "bought at the one-month high"
    assert G.phrase("entry_vol_day_vs_5", 2.5) == "bought on twice the usual volume"
    assert G.phrase("entry_ret_10", 20) == "bought after a two-week run-up of over 15%"
    assert G.phrase("hold_sessions_max", 0) == "a same-day round trip"
    with pytest.raises(ValueError):
        G.family_of("entry_dist_round")


# ═════════════════════════════════════════════════════════════════════════════════════════════ guards
def test_identifier_scan_both_lists_clean_and_a_planted_outcome_column_or_rule_name_fails(tmp_path):
    forb = T.forbidden_all()
    assert {"result_pct", "dollar_result", "winner", "E", "level_at", "setup"} <= forb
    assert C.scan_identifiers([str(ASIS / n) for n in G.SCAN_FILES_G], forb) == []
    assert "06_groups.py" in G.SCAN_FILES_G and "forbidden_outcomes.txt" in G.MODULE_FILES_G
    outcome = tmp_path / "outcome.py"
    outcome.write_text("cols = ['pos_in_day', 'result_pct']\nregained = 1\n", encoding="utf-8")
    assert [t for _p, _l, t in C.scan_identifiers([str(outcome)], forb)] == ["'result_pct'"]
    rule = tmp_path / "rule.py"
    rule.write_text("def f(level_at):\n    return level_at\nsetup_paths = 2\n", encoding="utf-8")
    assert [t for _p, _l, t in C.scan_identifiers([str(rule)], forb)] == ["level_at", "level_at"]


def test_fresh_interpreter_import_holds_no_rule_module_and_no_network_client():
    code = ("import importlib.util, json, sys\n"
            f"spec = importlib.util.spec_from_file_location('g06', {str(ASIS / '06_groups.py')!r})\n"
            "m = importlib.util.module_from_spec(spec); sys.modules['g06'] = m; spec.loader.exec_module(m)\n"
            "mods = set(sys.modules)\n"
            "print(json.dumps({'rule': m.C.rule_modules_loaded(), 'net': sorted(mods & {'requests', 'urllib3', 'http.client', "
            "'anthropic', 'openai', 'psycopg2', 'sqlalchemy'})}))\n")
    r = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, timeout=180, cwd=str(REPO))
    assert r.returncode == 0, r.stderr[-2000:]
    out = json.loads(r.stdout.strip().splitlines()[-1])
    assert out["rule"] == [] and out["net"] == []


# ═════════════════════════════════════════════════════════════════════════════════════════════ the method (§4)
def test_rank_map_averages_ties_and_continues_the_slope_beyond_the_knots_never_clipping():
    m = G.RankMap([1, 2, 2, 3, 10])
    assert m.x.tolist() == [1.0, 2.0, 3.0, 10.0]
    assert m.y[1] == pytest.approx((m.y[0] + m.y[2]) / 2 * 0 + m.y[1])          # the tie's score is the mean of ranks 2 and 3
    sc, ex = m.apply(np.array([1.0, 0.0, 2.0, 20.0, np.nan]))
    assert sc[0] == pytest.approx(m.y[0]) and not ex[0]
    assert sc[1] < m.y[0] and ex[1]                                           # a hold of 0 scores strictly BELOW the lowest knot
    assert sc[3] > m.y[-1] and ex[3]
    assert np.isnan(sc[4]) and not ex[4]
    assert ex.sum() == 2
    m1 = G.RankMap([5.0, 5.0])
    sc, ex = m1.apply(np.array([5.0, 6.0]))
    assert sc.tolist() == [0.0, 0.0] and ex.tolist() == [False, True]


def test_standardize_zero_fills_blanks_and_counts_them():
    X = np.array([[1.0, np.nan], [2.0, 1.0], [3.0, 2.0]])
    maps = G.fit_maps(X, ["a", "b"])
    Z, extra, blanks = G.standardize(X, ["a", "b"], maps)
    assert Z[0, 1] == 0.0 and blanks == {"a": 0, "b": 1} and extra == {"a": 0, "b": 0}
    assert Z[:, 0].tolist() == pytest.approx(sorted(Z[:, 0].tolist()))


def test_pca_whitens_to_ninety_percent():
    rng = np.random.default_rng(1)
    base = rng.normal(size=(200, 2))
    X = np.column_stack([base[:, 0], base[:, 0] * 2 + rng.normal(scale=0.01, size=200), base[:, 1], rng.normal(scale=0.05, size=200)])
    pca = G.PCA(X)
    Zp = pca.transform(X)
    assert pca.m == 2 and pca.explained >= 0.9
    assert np.allclose(Zp.std(0, ddof=1), 1.0, atol=0.05)


def _three_clusters(n=60, sep=6.0, seed="clusters", sd=0.5):
    rng = C.rng_for(seed)
    return np.vstack([rng.normal((0, 0), sd, (n, 2)), rng.normal((sep, 0), sd, (n, 2)), rng.normal((0, sep), sd, (n, 2))])


def test_kmeans_is_deterministic_with_the_seed_and_recovers_known_clusters():
    Z = _three_clusters()
    a = G.kmeans(Z, 3, C.rng_for("step7_test_k3"))
    b = G.kmeans(Z, 3, C.rng_for("step7_test_k3"))
    assert np.array_equal(a["labels"], b["labels"]) and a["inertia"] == b["inertia"]
    truth = np.repeat([0, 1, 2], 60)
    assert G.adjusted_rand(a["labels"], truth) == pytest.approx(1.0)
    assert G.nearest(np.array([[0.1, 0.1], [5.9, 0.0]]), a["centroids"]).tolist() == [a["labels"][0], a["labels"][60]]


def test_k_rule_picks_the_registered_k_on_known_clusters_the_largest_passing_and_none_on_noise():
    ch = G.choose_k(_three_clusters(), "test3", halves=10)
    assert ch["k"] == 3 and ch["n_min"] == 30 and ch["sweep"][3]["strength"] >= 0.8
    assert all(not (ch["sweep"][k]["strength_ok"] and ch["sweep"][k]["size_ok"]) for k in (4, 5, 6, 7, 8))
    rng = C.rng_for("pairs")                                                           # two far-apart pairs of clusters: k = 2 AND k = 4 pass; the LARGEST is taken
    pairs = np.vstack([rng.normal(ctr, 0.5, (40, 2)) for ctr in ((0, 0), (6, 0), (40, 0), (46, 0))])
    ch4 = G.choose_k(pairs, "test4", halves=10)
    assert ch4["sweep"][2]["strength"] >= 0.8 and ch4["sweep"][2]["size_ok"] and ch4["sweep"][4]["strength"] >= 0.8 and ch4["sweep"][4]["size_ok"]
    assert ch4["k"] == 4
    noise = C.rng_for("noise").normal(size=(120, 4))
    chn = G.choose_k(noise, "testnoise", halves=6)
    assert chn["k"] is None
    assert G.min_group_size(677) == 34 and G.min_group_size(1187) == 60 and G.min_group_size(100) == 30


def test_hungarian_adjusted_rand_and_spearman_on_hand_cases():
    assert G.hungarian(np.array([[4.0, 1.0], [2.0, 3.0]])) == [(0, 1), (1, 0)]
    assert G.hungarian(np.array([[1.0, 5.0, 5.0], [5.0, 5.0, 1.0]])) == [(0, 0), (1, 2)]        # 2 primary groups, 3 other: one left unmatched
    assert G.hungarian(np.array([[1.0, 5.0], [5.0, 1.0], [5.0, 5.0]])) == [(0, 0), (1, 1)]      # 3 primary groups, 2 other: group 2 unmatched
    assert G.hungarian(np.array([[1.0, 5.0], [5.0, 1.0], [0.0, 0.0]])) == [(0, 0), (2, 1)]      # the cheaper row takes the column; group 1 unmatched
    assert G.hungarian(np.zeros((0, 3))) == []
    assert G.adjusted_rand(np.array([0, 0, 1, 1]), np.array([1, 1, 0, 0])) == pytest.approx(1.0)
    assert abs(G.adjusted_rand(np.array([0, 0, 1, 1]), np.array([0, 1, 0, 1]))) < 1e-9 or G.adjusted_rand(np.array([0, 0, 1, 1]), np.array([0, 1, 0, 1])) < 0
    assert G.spearman([1, 2, 3, 4], [10, 20, 30, 40]) == pytest.approx(1.0)
    assert G.spearman([1, 2, 3, 4], [4, 3, 2, 1]) == pytest.approx(-1.0)
    assert G.pair_share(np.array([0, 0, 0, 1, 1]), np.array([0, 0, 1, 1, 1])) == pytest.approx(1 / 3)


def _fake_run(Zp: np.ndarray, labels: np.ndarray, eids: list, cols: list, run="x", primary=None) -> dict:
    k = int(labels.max()) + 1
    cent = np.vstack([Zp[labels == g].mean(0) for g in range(k)])
    R = {"run": run, "cols": cols, "eids": list(eids), "Z": Zp, "Zp": Zp, "labels": labels, "centroids": cent, "k": k, "run_mean": Zp.mean(0),
         "mode_b": False, "own_space": False, "X": Zp, "patterns": ["1"] * len(eids), "struct": np.zeros((len(eids), len(cols)), dtype=bool), "dropped": []}
    R["profiles"] = {g: G.profile(Zp, labels, g, R["run_mean"]) for g in range(k)}
    if primary is not None:
        R["common_cols"] = cols
        R["profiles_common"] = {g: G.profile(Zp, labels, g, primary["run_mean"]) for g in range(k)}
    return R


def _cols(n):
    base = ["entry_pos_in_day", "entry_minute", "entry_gap_pct", "entry_range_pct", "entry_ret_10", "exit_pos_in_day", "exit_minute", "hold_sessions_max",
            "entry_dist_hi_10", "entry_vol_day_vs_10", "entry_dist_ma_5", "entry_sessions_since_hi_5", "entry_dist_lo_5"]
    return base[:n]


def test_stability_fails_when_an_added_tier_forms_a_new_group_and_passes_when_it_mirrors_the_primary():
    cols = _cols(2)
    Z = _three_clusters(n=50, sep=8.0, seed="stab")                      # the primary: 3 groups of 50
    labels = np.repeat([0, 1, 2], 50)
    eids = list(range(150))
    primary = _fake_run(Z, labels, eids, cols, "primary")
    tier = {e: "HIGH" for e in eids}
    # (a) the added tier lands far away: a 4th group, every added row from the tier; the primary's own rows keep their groups
    far = C.rng_for("far").normal((20, 20), 0.5, (40, 2))
    Z2 = np.vstack([Z, far])
    lab2 = np.concatenate([labels, np.full(40, 3)])
    eids2 = eids + list(range(1000, 1040))
    tier.update({e: "ONE-STREAM" for e in range(1000, 1040)})
    other = _fake_run(Z2, lab2, eids2, cols, "plus", primary)
    cmp = G.compare_mode_a(primary, other, set(eids), {"ONE-STREAM"}, tier)
    assert cmp["moved"] == 0 and len(cmp["pairs"]) == 3
    assert [g["group"] for g in cmp["new_groups"]] == [3] and cmp["new_groups"][0]["added_share"] == 1.0 and cmp["new_groups"][0]["unmatched"]
    cons = G.consequence(cmp, 0.02, set())
    assert "new group" in cons["reading"] and cons["new_real"] and "he decides" in cons["action"]
    cons_art = G.consequence(cmp, 0.02, {3})                              # the same new group read as an ARTEFACT (R71, both conditions): judged on the move alone
    assert cons_art["new_artefact"] and "INCLUDED" in cons_art["action"]
    # (b) the added tier merges two primary groups: one primary group unmatched -> every one of its trades moved -> FAILS
    lab3 = np.concatenate([np.where(labels == 2, 0, labels), np.full(40, 1)])
    other3 = _fake_run(Z2, lab3, eids2, cols, "merge", primary)
    cmp3 = G.compare_mode_a(primary, other3, set(eids), {"ONE-STREAM"}, tier)
    assert cmp3["unmatched_primary"] and cmp3["moved"] >= 50 and cmp3["moved_share"] >= 50 / 150
    assert G.consequence(cmp3, 0.02, set())["lost"]
    # (c) the added tier mirrors the primary: no move, no new group, every description survives -> INCLUDED
    mirror = Z + C.rng_for("mirror").normal(0, 0.05, Z.shape)
    Z4 = np.vstack([Z, mirror])
    lab4 = np.concatenate([labels, labels])
    eids4 = eids + list(range(2000, 2150))
    tier.update({e: "ONE-STREAM" for e in range(2000, 2150)})
    other4 = _fake_run(Z4, lab4, eids4, cols, "mirror", primary)
    cmp4 = G.compare_mode_a(primary, other4, set(eids), {"ONE-STREAM"}, tier)
    assert cmp4["moved"] == 0 and not cmp4["new_groups"] and all(s["verdict"] == "survives" for s in cmp4["survival"].values())
    cons4 = G.consequence(cmp4, 0.02, set())
    assert "INCLUDED" in cons4["action"] and cons4["excess"] < 0


def test_mode_b_contingency_and_survival_on_the_common_columns():
    cols = _cols(2)
    Z = _three_clusters(n=40, sep=8.0, seed="modeb")
    labels = np.repeat([0, 1, 2], 40)
    eids = list(range(120))
    primary = _fake_run(Z, labels, eids, cols, "primary")
    # the other partition relabels the groups and moves 4 trades
    lab2 = (labels + 1) % 3
    lab2[:4] = 0
    other = _fake_run(Z, lab2, eids, cols, "entry_only", primary)
    other["mode_b"] = True
    cmp = G.compare_mode_b(primary, other)
    assert cmp["pairs"] == [(0, 1), (1, 2), (2, 0)] and cmp["moved"] == 4 and cmp["moved_share"] == pytest.approx(4 / 120)
    assert 0.8 < cmp["ari"] < 1.0 and set(cmp["survival"]) == {0, 1, 2}


def test_survival_verdicts_by_families_and_spearman():
    cols = _cols(13)
    p = np.array([3.0, -2.0, 1.5, 0.1, 0.2, 0.2, 0.1, -1.2, 1.1, 0.2, 0.1, 0.05, 0.0])
    assert G.survival(p, p, cols)["verdict"] == "survives"
    swapped = p.copy()
    swapped[8], swapped[12] = 0.0, 1.1                                    # dist_hi_10 -> dist_lo_5: another family enters the top five
    v = G.survival(p, swapped, cols)
    assert v["verdict"] in ("partial", "lost") and not v["same_families"]
    assert G.survival(p, -p, cols)["verdict"] == "lost"
    fams = G.top_families(p, cols)
    assert fams[0] == ("position in day", 1) and fams[1] == ("minute", -1) and len(fams) == 5


# ═════════════════════════════════════════════════════════════════════════════════════════════ blanks (§3.3-3.4)
def test_structural_blanks_follow_the_hold_and_the_quarter_rule_drops_data_blank_rows():
    ex = {c: 1.0 for c in G.FEATURES["primary"]["exit"]}
    out, struct = G.apply_structural(ex, 1, 1)                            # one session: every look-back blank, the day-own columns kept
    assert all(out[c] == "" for c in struct) and all(out[c] == 1.0 for c in G.DAY_OWN if c in out)
    assert "dist_prev_close" in struct and "dist_hi_3" in struct and "pos_in_day" not in struct
    out0, struct0 = G.apply_structural(ex, 0, 0)                          # a same-session round trip: every look-back defined
    assert struct0 == set() and all(v == 1.0 for v in out0.values())
    out4, struct4 = G.apply_structural(ex, 4, 5)
    assert {"dist_prev_high", "dist_hi_3"} <= set(ex) - struct4 and "dist_hi_5" in struct4
    assert G.structural_pattern(4, 5) == "1,3" and G.structural_pattern(1, 1) == "(none)" and G.structural_pattern(0, 0).startswith("1,3,5")
    cols = ["entry_pos_in_day", "entry_minute", "entry_gap_pct", "entry_range_pct", "exit_dist_hi_3", "hold_sessions_max"]
    feats = {
        1: {"meta": {"hold_sessions_min": "1", "hold_sessions_max": "1"}, "middle": {"entry": {"pos_in_day": 0.5, "minute": 10, "gap_pct": 1, "range_pct": 2}, "exit": {"dist_hi_3": ""}, "struct": {"dist_hi_3"}, "trade": {"hold_sessions_max": "1"}}},
        2: {"meta": {"hold_sessions_min": "1", "hold_sessions_max": "1"}, "middle": {"entry": {"pos_in_day": "", "minute": "", "gap_pct": 1, "range_pct": 2}, "exit": {"dist_hi_3": ""}, "struct": {"dist_hi_3"}, "trade": {"hold_sessions_max": "1"}}},
        3: {"meta": {"hold_sessions_min": "1", "hold_sessions_max": "1"}, "middle": None},
    }
    A = G.assemble(feats, [1, 2, 3], cols)
    assert A["eids"] == [1] and [d[0] for d in A["dropped"]] == [2, 3]
    assert A["dropped"][0][1] == pytest.approx(2 / 5) and A["dropped"][1][1] == 1.0   # the structural blank never counts toward the quarter
    assert A["struct"][0].tolist() == [False, False, False, False, True, False] and A["patterns"] == ["(none)"]


def test_structural_group_flag_at_eighty_percent():
    R = {"labels": np.array([0, 0, 0, 0, 0, 1, 1, 1, 1, 1]), "k": 2, "patterns": ["(none)"] * 4 + ["1"] + ["1", "1", "1,3", "1,3", "1,3"]}
    st = G.structural_groups(R)
    assert st[0]["structural"] and st[0]["top_pattern"] == "(none)" and st[0]["top_share"] == 0.8
    assert not st[1]["structural"] and st[1]["top_share"] == 0.6


def test_artefact_rule_needs_both_conditions_of_section_5d():
    """R71 (review F3): structural AND no separation on an entry or exit day-own column. The hold and the exit look-backs are not consulted."""
    cols = ["entry_pos_in_day", "entry_minute", "exit_pos_in_day", "exit_dist_hi_3", "hold_sessions_max"]
    assert [cols[k] for k in G.pattern_free_columns(cols)] == ["entry_pos_in_day", "entry_minute", "exit_pos_in_day"]
    n = 40
    Z = np.zeros((2 * n, 5))
    labels = np.repeat([0, 1], n)
    # group 1 differs from group 0 on the exit look-back and the hold ONLY (the pattern's own columns): structural -> an artefact
    Z[n:, 3], Z[n:, 4] = 3.0, -2.0
    R = {"labels": labels, "k": 2, "cols": cols, "patterns": ["1"] * n + ["1,3,5,8,10,13,20,30,40,50,60"] * n}
    R["run_mean"] = Z.mean(0)
    R["profiles"] = {g: G.profile(Z, labels, g, R["run_mean"]) for g in range(2)}
    st = G.structural_groups(R)
    art = G.artefact_groups(R, st)
    assert st[1]["structural"] and not art[1]["separates"] and art[1]["artefact"] and art[1]["max_dev"] == 0.0
    assert art[0]["artefact"]                                               # the mirror group is structural too and separates nowhere pattern-free
    # the same group separating on ONE entry column by half a spread: a real group, not an artefact
    Z2 = Z.copy()
    Z2[n:, 1] = 1.0                                                          # entry_minute: deviation from the run's mean = +0.5 / -0.5
    R2 = dict(R, run_mean=Z2.mean(0))
    R2["profiles"] = {g: G.profile(Z2, labels, g, R2["run_mean"]) for g in range(2)}
    art2 = G.artefact_groups(R2, st)
    assert art2[1]["separates"] and not art2[1]["artefact"] and art2[1]["max_col"] == "entry_minute" and art2[1]["max_dev"] == pytest.approx(0.5)
    # just under the line stays an artefact; an exit DAY-OWN column counts like an entry column
    Z3 = Z.copy()
    Z3[n:, 2] = 0.98
    R3 = dict(R, run_mean=Z3.mean(0))
    R3["profiles"] = {g: G.profile(Z3, labels, g, R3["run_mean"]) for g in range(2)}
    assert G.artefact_groups(R3, st)[1]["artefact"] and G.artefact_groups(R3, st)[1]["max_col"] == "exit_pos_in_day"
    Z3[n:, 2] = 1.2
    R3["run_mean"] = Z3.mean(0)
    R3["profiles"] = {g: G.profile(Z3, labels, g, R3["run_mean"]) for g in range(2)}
    assert not G.artefact_groups(R3, st)[1]["artefact"]
    # a non-structural group is never an artefact, whatever it separates on
    R4 = dict(R, patterns=["1"] * n + ["1"] * 20 + ["1,3"] * 20)
    st4 = G.structural_groups(R4)
    assert not st4[1]["structural"] and not G.artefact_groups(R4, st4)[1]["artefact"]


# ═════════════════════════════════════════════════════════════════════════════════════════════ the run gate
def _gate_env(tmp_path, monkeypatch, complete=True, mismatch=0, modules_line=None, tiers_run=True, outcome="no style we could show we would see"):
    d = tmp_path / "w"
    d.mkdir(parents=True)
    paths = {"dry": str(d / "dry.txt"), "run": str(d / "run.txt"), "refused": str(d / "refused.txt"), "pins": str(d / "pins.txt"), "power": str(d / "06b_power.txt")}
    B = G.power_module()
    # 7b §11 (fix card, 06b R99): the --run waits for a POWER COMPLETE made by the modules on disk, pinned below the 7b doc's marker, with its step7b_power ledger row
    Path(paths["power"]).write_text(f"# power\n- modules: {B.module_shas_line()}\nPOWER COMPLETE: {outcome}\n", encoding="utf-8")
    doc7b = d / "doc7b.md"
    doc7b.write_text(f"# step 7b\n\nbody 7b\n\n<!-- FREEZE -->\n## Freeze record\n- power7b_printout: {C.sha(paths['power'])}\n", encoding="utf-8")
    monkeypatch.setattr(B, "DOC7B", str(doc7b))
    monkeypatch.setattr(B, "CACHE_DIR", str(d / "step7b_cache"))                     # 06b R83: no test writes the null cache into the data tree
    ml = G.module_shas_line() if modules_line is None else modules_line
    lines = ["# dry", f"- modules: {ml}", f"RESULT: 3 claims, {3 - mismatch} OK, {mismatch} MISMATCH"]
    if complete:
        lines.append("DRY RUN COMPLETE")
    Path(paths["dry"]).write_text("\n".join(lines) + "\n", encoding="utf-8")
    for key in ("ranges", "candidates", "coverage"):
        (d / f"{key}.tsv").write_text("eid\n", encoding="utf-8")
    (d / "check.tsv").write_text("stmt_id\n", encoding="utf-8")
    (d / "03.txt").write_text("run\n", encoding="utf-8")
    (d / "05dry.txt").write_text("dry\nRESULT: 1 claims, 1 OK, 0 MISMATCH\nDRY RUN COMPLETE\n", encoding="utf-8")
    (d / "05run.txt").write_text("run\n" + ("RUN COMPLETE\n" if tiers_run else ""), encoding="utf-8")
    (d / "tiers.tsv").write_text("eid\n", encoding="utf-8")
    monkeypatch.setattr(C, "OUTPUTS", {k: str(d / f"{k}.tsv") for k in ("candidates", "ranges", "coverage")})
    monkeypatch.setattr(T, "CHECK_R1_R5", str(d / "check.tsv"))
    monkeypatch.setattr(T, "P03_RUN", str(d / "03.txt"))
    monkeypatch.setattr(T, "OUT_7", {"tiers": str(d / "tiers.tsv")})
    monkeypatch.setattr(T, "P05", {"dry": str(d / "05dry.txt"), "run": str(d / "05run.txt"), "refused": str(d / "05ref.txt"), "pins": str(d / "05pins.txt")})
    monkeypatch.setattr(G, "OUT_G", {k: str(d / f"step7_{k}.tsv") for k in ("features", "groups", "descriptions", "stability")})
    (d / "ledger.tsv").write_text(f"stage\tpath\tsha256\ttime\nstep7b_power\t{d / 'step7b_power.tsv'}\tx\tnow\n", encoding="utf-8")     # 7b R99: the power run's ledger row
    monkeypatch.setattr(C, "LEDGER", str(d / "ledger.tsv"))
    monkeypatch.setattr(C, "ledger_verify", lambda: [])
    monkeypatch.setattr(C, "subs_list_sha", lambda paths=None: "subs")
    doc = d / "doc.md"
    doc.write_text("# step 7\n\nbody\n\n<!-- FREEZE -->\n## Freeze record\n", encoding="utf-8")
    pins = G.pins_g(str(doc), paths["dry"])
    doc.write_text(doc.read_text(encoding="utf-8") + "\n".join(f"- {k}: {v}" for k, v in pins.items()) + "\n", encoding="utf-8")
    return {"paths": paths, "doc": str(doc), "dir": d, "doc7b": str(doc7b)}


def test_run_gate_passes_in_a_complete_world_and_its_stage_pins_are_the_step7_ones(tmp_path, monkeypatch):
    w = _gate_env(tmp_path, monkeypatch)
    assert G.run_gate(w["doc"], w["paths"]) == []
    pins = G.pins_g(w["doc"], w["paths"]["dry"])
    keys = set(G.stage_pin_keys(pins, w["doc"]))
    assert {"tiers", "run7_tiers_printout", "06_groups.py", "dryrun7g_printout", "dryrun7_printout", "05_tiers.py", "doc_body_steps56", "ranges"} <= keys
    assert "doc_body" in pins and "doc_body" not in keys


def test_run_gate_refuses_without_a_dry_run_a_mismatch_other_code_or_05_not_run(tmp_path, monkeypatch):
    w = _gate_env(tmp_path, monkeypatch, complete=False)
    assert any("has not completed" in p for p in G.run_gate(w["doc"], w["paths"]))
    w = _gate_env(tmp_path / "b", monkeypatch, mismatch=1)
    assert any("1 MISMATCH" in p for p in G.run_gate(w["doc"], w["paths"]))
    w = _gate_env(tmp_path / "c", monkeypatch, modules_line="06_groups.py 0000000000000000")
    assert any("other code" in p for p in G.run_gate(w["doc"], w["paths"]))
    w = _gate_env(tmp_path / "d", monkeypatch, tiers_run=False)
    assert any("05_tiers.py --run has not completed" in p for p in G.run_gate(w["doc"], w["paths"]))


def test_run_gate_refuses_a_pin_above_the_marker_an_absent_stage_pin_an_existing_output_and_two_markers(tmp_path, monkeypatch):
    w = _gate_env(tmp_path, monkeypatch)
    doc = Path(w["doc"])
    text = doc.read_text(encoding="utf-8")
    pins = G.pins_g(w["doc"], w["paths"]["dry"])
    line = f"- dryrun7g_printout: {pins['dryrun7g_printout']}"
    doc.write_text(text.replace(line + "\n", "").replace("<!-- FREEZE -->", line + "\n<!-- FREEZE -->"), encoding="utf-8")
    assert any("dryrun7g_printout" in p and "freeze marker" in p for p in G.run_gate(w["doc"], w["paths"]))
    doc.write_text(text, encoding="utf-8")
    os.remove(T.OUT_7["tiers"])
    assert G.pins_g(w["doc"], w["paths"]["dry"])["tiers"] == "ABSENT"
    doc.write_text(text + "- tiers: ABSENT\n", encoding="utf-8")
    assert any("ABSENT" in p and "tiers" in p for p in G.run_gate(w["doc"], w["paths"]))
    Path(T.OUT_7["tiers"]).write_text("eid\n", encoding="utf-8")
    doc.write_text(text, encoding="utf-8")
    assert G.run_gate(w["doc"], w["paths"]) == []
    Path(G.OUT_G["groups"]).write_text("eid\n", encoding="utf-8")
    assert any("outputs exist" in p for p in G.run_gate(w["doc"], w["paths"]))
    os.remove(G.OUT_G["groups"])
    doc.write_text(text + "<!-- FREEZE -->\n", encoding="utf-8")
    assert any("freeze marker" in p for p in G.run_gate(w["doc"], w["paths"]))
    assert any("registration is missing" in p for p in G.run_gate(str(tmp_path / "none.md"), w["paths"]))


def test_the_real_registration_is_frozen_with_one_marker_and_06_is_not_yet_pinned_so_run_refuses():
    text = DOC7.read_text(encoding="utf-8")
    assert len(C.marker_spans(text.encode())) == 1
    assert "06_groups.py" in text and "STEP7_FEATURES" in text
    if REAL_DATA:
        problems = G.run_gate()
        assert problems == [] or any("freeze marker" in p or "has not completed" in p or "outputs exist" in p for p in problems)


# ═════════════════════════════════════════════════════════════════════════════════════════════ real data
@needs_real_data
def test_dry_run_on_real_data_ends_complete_with_zero_mismatch_and_writes_no_output(tmp_path, monkeypatch):
    paths = dict(G.P06)
    paths["dry"] = str(tmp_path / "dry.txt")                      # R64: never the pinned printout
    monkeypatch.setattr(G, "P06", paths)
    monkeypatch.setattr(C, "rule_modules_loaded", lambda: [])    # a shared pytest process may hold other tests' modules; the fresh-interpreter test covers the belt
    before = {k: os.path.exists(p) for k, p in G.OUT_G.items()}
    assert G.main(["--dry-run"]) == 0
    lines = [ln for ln in Path(paths["dry"]).read_text(encoding="utf-8").splitlines() if ln.strip()]
    assert lines[-1].startswith("DRY RUN COMPLETE") and C.printout_mismatches(paths["dry"]) == 0
    text = "\n".join(lines)
    assert "primary rows (HIGH + MEDIUM): expected 677, got 677" in text
    assert "k sweep — PRIMARY" in text and "k chosen by the rule" in text
    assert "max |score|" in text and "(R72" in text                 # review F4: the score sizes are printed beside the extrapolated counts
    assert "Entry and exit described on the same session (R73" in text    # review F5: the same-session readout
    assert "EXACTLY the 153 rangeless (no bars) + the 31 inverted" in text and "9 / 6 no_range" in text        # review F8
    assert "### primary — group" not in text                       # no group description in a dry run
    assert {k: os.path.exists(p) for k, p in G.OUT_G.items()} == before


# ═════════════════════════════════════════════════════════════════════════════════════════════ the run path on a synthetic world
def _synthetic_world(n_per=60, seed="world", latent=True):
    """feats / tiers / ranges shaped like the real inputs: two clear groups on the ENTRY side (early high-volume buys near the high after a
    run-up vs late buys near the low) shifting every entry column; HIGH + MEDIUM rows, a ONE-STREAM tier that mirrors them and a LOW tier.
    `latent=True`: beside the split, every column is driven by ONE latent factor per trade plus small noise (a low-rank world, which PCA to
    90% keeps in a few components — the only shape the registered whitened space reads reliably; with three factors or independent noise the
    same perfect split reads 'no stable grouping' in about half of the seeded worlds tried while building this test); False: independent
    column noise (see test_registered_whitening_cannot_read_a_split_carried_by_independent_columns)."""
    rng = C.rng_for(seed)
    cols_e, cols_x = G.FEATURES["with_our_length"]["entry"], G.FEATURES["with_our_length"]["exit"]
    loads = {c: rng.choice([-1.0, 1.0]) * rng.uniform(0.7, 1.5, size=1) for c in list(cols_e) + list(cols_x)}
    shifts = {c: float(rng.uniform(0.3, 1.0)) for c in cols_e}             # a PARTIAL split on the ordinary columns (its size differs per column, under the
    #                                                                         latent spread), so only the nine hand-planted columns carry a perfect split and
    #                                                                         the top-five families are not a tie
    feats, tiers, ranges = {}, [], {}
    eid = 0
    for tier, n in (("HIGH", n_per), ("MEDIUM", n_per), ("ONE-STREAM", n_per), ("LOW", 20)):
        for i in range(n):
            eid += 1
            grp = i % 2
            fac = rng.normal(size=1)

            def val(c, shift=0.0):
                return round(float(shift + (loads[c] @ fac + 0.1 * rng.normal() if latent else rng.normal())), 4)
            ent = {c: val(c, 0.5 * shifts[c] if grp == 0 else -0.5 * shifts[c]) for c in cols_e}
            ent["minute"] = int(rng.integers(0, 30)) if grp == 0 else int(rng.integers(300, 389))
            ent["pos_in_day"] = round(float(rng.uniform(0.8, 1.0)) if grp == 0 else float(rng.uniform(0.0, 0.2)), 4)
            ent["ret_10"] = round(float(rng.normal(25, 3)) if grp == 0 else float(rng.normal(-10, 3)), 4)
            ent["dist_hi_10"] = round(float(rng.normal(0, 0.5)) if grp == 0 else float(rng.normal(-20, 2)), 4)
            for c in cols_e:
                if c.startswith("vol_day_vs_"):
                    ent[c] = round(float(rng.normal(3, 0.3)) if grp == 0 else float(rng.normal(0.8, 0.1)), 4)
            exi = {c: val(c) for c in cols_x}
            exi["minute"] = int(rng.integers(0, 389))
            exi["pos_in_day"] = round(float(rng.uniform()), 4)
            hold = int(rng.integers(1, 6)) if tier != "LOW" else int(rng.integers(0, 6))      # LOW carries a few same-day holds (below the primary's lowest knot)
            exi, struct = G.apply_structural(exi, hold, hold)
            rec = {"entry": ent, "exit": exi, "struct": struct, "trade": {"hold_sessions_max": str(hold)},
                   "flags": {"entry": set(), "exit": set()}, "at": {"entry": ("2020-06-01", ent["minute"], 10.0), "exit": ("2020-06-03", exi["minute"], 11.0)}}
            tr = {"eid": str(eid), "sym": f"S{eid}", "year": "2020" if i % 3 else "2021", "tier": tier, "tier_reason": "x", "confirmed": "True" if i % 7 == 0 else "False",
                  "minute_coverage": "both", "hold_sessions_min": str(hold), "hold_sessions_max": str(hold), "buy_range_width_pct": "1.5", "sale_range_width_pct": "2.5"}
            feats[eid] = {"meta": tr, "middle": rec, "low": rec if tier in G.PRIMARY_TIERS else None, "high": rec if tier in G.PRIMARY_TIERS else None}
            if tier == "LOW" and i % 2:
                feats[eid]["middle"] = None
            tiers.append(tr)
            ranges[(str(eid), "buy")] = {"lo": "2020-06-01", "hi": "2020-06-01"}
            ranges[(str(eid), "sale")] = {"lo": "2020-06-03", "hi": "2020-06-03"}
    return feats, tiers, ranges


def test_run_path_on_a_synthetic_world_finds_the_planted_groups_and_every_comparison_runs():
    feats, tiers, ranges = _synthetic_world(n_per=120, seed="w2")
    say = G.Say()
    tiers_by_eid = {int(t["eid"]): t for t in tiers}
    tier_of_eid = {e: t["tier"] for e, t in tiers_by_eid.items()}
    primary = G.fit_run("primary", feats, tiers, None, say)
    assert len(primary["eids"]) == 240 and primary["k"] == 2 and primary["choice"]["n_min"] == 30
    assert primary["choice"]["sweep"][2]["strength"] >= 0.8
    st = G.structural_groups(primary)
    descs = [G.describe_group(primary, g, tiers_by_eid, ranges, st) for g in range(2)]
    G.print_descriptions(primary, descs, st, say)
    words = " | ".join(f["words"] for d in descs for f in d["features"])
    assert "bought" in words and all(len(d["examples"]) == 3 for d in descs) and all(d["band_width"]["buy"] == 1.5 for d in descs)
    assert all(d["n"] == 120 for d in descs)
    fams = {f["family"] for d in descs for f in d["features"]}
    assert fams & {"minute", "position in day", "run-up", "from recent highs", "volume"}
    ed = G.expectation_descriptions(descs)
    assert ed["early_buy_near_high_after_runup"]
    floor = G.noise_floor(primary["Zp"], primary)
    assert floor["floor"] < 0.05 and len(floor["seeded"]) == 5 and len(floor["bootstrap"]) == 5
    seen = {}
    for run in G.RUNS[1:]:
        R = G.fit_run(run, feats, tiers, primary, say)
        seen[run] = R
        if run == "confirmed":
            assert R["choice"] is None and R["k"] == 2 and len(R["eids"]) == sum(1 for t in tiers if t["confirmed"] == "True" and feats[int(t["eid"])]["middle"] is not None)
            continue
        if run == "exit_only":
            if R["k"] is None:                                          # the exit side carries no split: whatever the rule reads there, the run must complete
                continue
            st_r = G.structural_groups(R)
            cmp = G.compare_mode_b(primary, R)
            G.consequence(cmp, floor["floor"], {g for g, a in G.artefact_groups(R, st_r).items() if a["artefact"]})
            continue
        assert R["k"] == 2, (run, {k: v["strength"] for k, v in R["choice"]["sweep"].items()})
        st_r = G.structural_groups(R)
        ds = [G.describe_group(R, g, tiers_by_eid, ranges, st_r) for g in range(R["k"])]
        added = set(G.RUN_TIERS[run]) - set(G.PRIMARY_TIERS)
        cmp = G.compare_mode_b(primary, R) if R["mode_b"] else G.compare_mode_a(primary, R, set(primary["eids"]), added, tier_of_eid)
        cons = G.consequence(cmp, floor["floor"], {g for g, a in G.artefact_groups(R, st_r).items() if a["artefact"]})     # R71: both conditions
        G.print_descriptions(R, ds, st_r, say)
        G.print_comparison(run, cmp, cons, R, primary, say)
        assert cmp["moved_share"] < 0.05 and "INCLUDED" in cons["action"], (run, cmp["moved_share"], cons)
        assert all(s["verdict"] == "survives" for s in cmp["survival"].values()), (run, cmp["survival"])
    assert seen["plus_low"]["extra"]["hold_sessions_max"] > 0                                 # same-day holds extrapolate below the primary's lowest knot
    rows = G.feature_out_rows(feats, tiers)
    assert len(rows) == sum(1 for t in tiers for m in ("middle", "low", "high") if feats[int(t["eid"])].get(m) is not None)
    assert set(G.FEATURE_OUT_COLS) >= set(rows[0])
    assert not any("price" in c for c in G.FEATURE_OUT_COLS) and "entry_price" not in rows[0] and "exit_price" not in rows[0]     # R74 (review F6)
    assert any("stability —" in ln for ln in say.lines) and any("NEW group" in ln or "no new group" in ln for ln in say.lines)


def test_run_path_reads_a_far_added_tier_as_a_real_new_group_not_included():
    """Review F7, end to end through fit_run + choose_k: the ONE-STREAM tier of the w2 world is moved far away on every ordinary entry column
    and given the same-day structural pattern (hold 0, every exit look-back defined). + ONE-STREAM re-chooses k, the Hungarian matching leaves
    the far groups unmatched (new, every row from the added tier), they are STRUCTURAL but separate on the entry side, so R71 reads them as
    REAL new groups and the consequence is 'he decides' — never INCLUDED. The primary's own rows keep their groups."""
    feats, tiers, _r = _synthetic_world(n_per=120, seed="w2")
    cols_e = G.FEATURES["with_our_length"]["entry"]
    for t in tiers:
        if t["tier"] != "ONE-STREAM":
            continue
        rec = feats[int(t["eid"])]["middle"]
        for c in cols_e:
            if c not in ("minute", "pos_in_day"):
                rec["entry"][c] = round(float(rec["entry"][c]) + 6.0, 4)
        t["hold_sessions_min"] = t["hold_sessions_max"] = "0"
        rec["trade"]["hold_sessions_max"] = "0"
        full = {c: 0.1 for c in G.FEATURES["with_our_length"]["exit"]}
        full["minute"], full["pos_in_day"] = rec["exit"]["minute"], rec["exit"]["pos_in_day"]
        rec["exit"], rec["struct"] = G.apply_structural(full, 0, 0)
    say = G.Say()
    tier_of_eid = {int(t["eid"]): t["tier"] for t in tiers}
    primary = G.fit_run("primary", feats, tiers, None, say)
    assert primary["k"] == 2
    floor = G.noise_floor(primary["Zp"], primary)
    R = G.fit_run("plus_one_stream", feats, tiers, primary, say)
    assert R["k"] is not None and R["k"] > primary["k"]
    st = G.structural_groups(R)
    art = G.artefact_groups(R, st)
    cmp = G.compare_mode_a(primary, R, set(primary["eids"]), {"ONE-STREAM"}, tier_of_eid)
    new = cmp["new_groups"]
    assert new and all(g["unmatched"] and g["added_share"] == 1.0 and g["n"] >= 60 for g in new) and sum(g["n"] for g in new) == 120
    assert all(st[g["group"]]["structural"] and art[g["group"]]["separates"] and not art[g["group"]]["artefact"] for g in new)
    assert all(art[g["group"]]["max_col"].startswith("entry_") for g in new)
    assert cmp["moved_share"] < 0.05 and not cmp["unmatched_primary"]
    cons = G.consequence(cmp, floor["floor"], {g for g in art if art[g]["artefact"]})
    assert cons["new_real"] and not cons["new_artefact"] and "he decides" in cons["action"] and "INCLUDED" not in cons["action"]
    # the same world with the far groups read as artefacts (the first build's one-condition rule) would have INCLUDED the tier
    assert "INCLUDED" in G.consequence(cmp, floor["floor"], {g["group"] for g in new})["action"]


# ═════════════════════════════════════════════════════════════════════════════════════════════ 7b: main() under a carried method / column set
def _world_env(monkeypatch, n_per=120, seed="w2"):
    """main() on the synthetic world: the real-data loaders replaced (never the real matrix), the belt check stubbed (a shared pytest process)."""
    feats, tiers, ranges = _synthetic_world(n_per=n_per, seed=seed)
    monkeypatch.setattr(G, "load_inputs", lambda say: {"tiers": tiers, "ranges": ranges, "L": None})

    def _build(L, tiers_, ranges_, say, modes=("middle", "low", "high")):
        f = dict(feats)                                                            # main() pops `_checks`: a fresh dict per stage
        f["_checks"] = {"range_mismatch": 0, "sweep20_mismatch": 0, "lo_at_mismatch": 0, "hi_at_mismatch": 0}
        return f
    monkeypatch.setattr(G, "build_features", _build)
    monkeypatch.setattr(C, "rule_modules_loaded", lambda: [])
    return feats, tiers, ranges


@pytest.mark.parametrize("method", G.METHODS_7B[1:])
def test_main_under_each_carried_method_reaches_dry_run_complete_and_run_complete_on_the_synthetic_world(tmp_path, monkeypatch, method):
    """7b fix card (06b R96): under a carried method the primary carries no `choice`; the dry run's minimum-size claim and step 7 §7's first
    expectation read the method's own fit. Both stages of main() run end to end on the synthetic world, gated as the real run is (POWER
    COMPLETE naming the method, made by the modules on disk, pinned, ledgered; the method's own dry printout), and the §7 block is reached
    whenever the method reads groups — the reviewer's crash points sat AFTER the carried method's real reading had been printed."""
    w = _gate_env(tmp_path, monkeypatch, outcome=f"carried {method} on registered")
    B = G.power_module()
    monkeypatch.setattr(B, "M3_NULL", 100)                                        # the resolution of M3's null, never its construction
    monkeypatch.setattr(G, "P06", dict(G.P06, **w["paths"]))
    monkeypatch.setattr(G, "DOC7", w["doc"])
    _world_env(monkeypatch)
    assert G.main(["--dry-run", "--method", method]) == 0
    dry = Path(G.dry_path_for(method, "registered"))
    text = dry.read_text(encoding="utf-8")
    lines = [ln for ln in text.splitlines() if ln.strip()]
    assert lines[-1].startswith("DRY RUN COMPLETE") and f"### {method} — PRIMARY" in text and "- 7b gate: 06b_power.txt ends POWER COMPLETE naming" in text
    assert "[OK] minimum group size for the primary (5% of the registered 677, R70): expected 34, got 34" not in text        # the synthetic world's n differs
    assert "minimum group size for the primary (5% of the registered 677, R70): expected 34, got 30" in text               # 06b R96: min_group_size(240) = 30
    assert not os.path.exists(w["paths"]["dry"]) or "REFUSED" not in Path(w["paths"]["dry"]).read_text(encoding="utf-8")   # the pinned default printout untouched
    # the run: its gate reads the METHOD's dry printout; the synthetic world cannot meet the registration's counts, so a 0-MISMATCH printout
    # by the modules on disk stands in (as _gate_env's default one does) and is pinned below the step-7 doc's marker
    dry.write_text("\n".join(["# dry", f"- modules: {G.module_shas_line()}", "RESULT: 33 claims, 33 OK, 0 MISMATCH", "DRY RUN COMPLETE"]) + "\n", encoding="utf-8")
    Path(w["doc"]).write_text(Path(w["doc"]).read_text(encoding="utf-8") + f"- dryrun7g_printout: {C.sha(str(dry))}\n", encoding="utf-8")
    assert G.run_gate(w["doc"], dict(w["paths"], dry=str(dry)), method=method) == []
    assert G.main(["--run", "--method", method]) == 0, Path(w["paths"]["refused"]).read_text(encoding="utf-8") if os.path.exists(w["paths"]["refused"]) else ""
    run = Path(w["paths"]["run"]).read_text(encoding="utf-8")
    rlines = [ln for ln in run.splitlines() if ln.strip()]
    assert rlines[-1].startswith("RUN COMPLETE") and f"the carried method {method} on the registered columns" in run
    assert all(os.path.exists(p) for p in G.OUT_G.values())
    if "NO STABLE GROUPING on the primary" in run:                               # M1 and M3u read one group on this world: the one-population branch
        assert "## Expectations (§7)" not in run and "- the other runs are not compared" in run
    else:                                                                        # M2w, M2u, M3w, M4 read groups here: the whole §5 machinery and the §7 block
        assert "## Expectations (§7)" in run and "3-5 groups by its rule (" in run and "3-5 groups at strength >= 0.80" not in run   # 7b §2 item 3
        assert f"(the carried method {method} refitted)" in run and "## Run: plus_one_stream" in run and "## Run: exit_only" in run
        assert ("DISTINCT rows" in run) == (method in ("M3w", "M3u"))               # 06b R102: the split test's bootstrap arm on the resample's distinct rows
    assert G.ledger_stage_rows("step7_groups_dry_run") and str(dry) in Path(C.LEDGER).read_text(encoding="utf-8")                   # the ledger names the method's own dry run


def test_pattern_free_run_describes_the_hold_and_the_exit_lookbacks_per_group_while_grouping_on_56_columns():
    """7b §6 Fallback 1 (06b R97): under `--columns pattern_free` a run groups on its gap-free columns but DESCRIBES the hold and the exit
    look-backs per group — the group medians cover the run's registered columns (so R63's hold line can be scored), the printout carries a
    'described, never grouped on' line, and the five farthest features stay on the grouped columns."""
    feats, tiers, ranges = _synthetic_world(n_per=120, seed="w2")
    say = G.Say()
    tiers_by_eid = {int(t["eid"]): t for t in tiers}
    primary = G.fit_run("primary", feats, tiers, None, say, columns="pattern_free")
    assert primary["Z"].shape[1] == 56 and len(primary["cols"]) == 56 and primary["k"] == 2
    assert primary["desc"]["cols"] == G.run_columns("primary") and primary["desc"]["X"].shape == (len(primary["eids"]), 75)
    st = G.structural_groups(primary)
    descs = [G.describe_group(primary, g, tiers_by_eid, ranges, st) for g in range(primary["k"])]
    for d in descs:
        assert d["medians"]["hold_sessions_max"] is not None and set(d["medians"]) == set(G.run_columns("primary"))
        assert set(d["described_only"]) == set(G.run_columns("primary")) - set(primary["cols"]) and len(d["described_only"]) == 19
        assert "hold_sessions_max" in d["described_only"] and all(c.startswith("exit_") or c == "hold_sessions_max" for c in d["described_only"])
        assert all(f["column"] in primary["cols"] for f in d["features"])
    G.print_descriptions(primary, descs, st, say)
    assert any("described, never grouped on" in ln and "hold_sessions_max" in ln and "exit_dist_prev_close" in ln for ln in say.lines)
    assert "sale_within_two_sessions_near_low" in G.expectation_descriptions(descs)                       # R63 reads the hold from the medians
    # the registered column set carries no description matrix and its medians are the grouped columns' (the default path, unchanged)
    reg = G.fit_run("primary", feats, tiers, None, say)
    assert reg["desc"] is None
    dreg = G.describe_group(reg, 0, tiers_by_eid, ranges, G.structural_groups(reg))
    assert dreg["described_only"] == {} and set(dreg["medians"]) == set(reg["cols"])
    # every other run under pattern_free: its own fitted rows, its registered columns described (exit-only: the 16 grouped, 35 described)
    for run, n_desc in (("plus_one_stream", 75), ("exit_only", 35), ("with_our_length", 95), ("year_2020", 75)):
        R = G.fit_run(run, feats, tiers, primary, say, columns="pattern_free")
        assert R["desc"]["cols"] == G.run_columns(run) and R["desc"]["X"].shape == (len(R["eids"]), n_desc), run
        assert len(R["cols"]) == len(G.run_columns(run, "pattern_free"))
    assert G.assemble(feats, [1, 2, 3], G.run_columns("primary"), drop=False)["eids"] == [1, 2, 3]


def _factor_world(seed="pw1", n=658, nf=18, noise=1.2, shift=5.0, n_split=8):
    """A matrix shaped like the real primary (n = 658, the 75 primary columns, a factor spectrum needing about 18 whitened components at 90%)
    with a two-way split of +-shift planted on the first `n_split` entry columns. -> (X, truth)."""
    cols = G.run_columns("primary")
    rng = C.rng_for(seed)
    W = rng.normal(size=(nf, len(cols))) * rng.uniform(0.5, 1.5, size=(nf, 1))
    X = rng.normal(size=(n, nf)) @ W + noise * rng.normal(size=(n, len(cols)))
    truth = np.arange(n) % 2
    ent = [k for k, c in enumerate(cols) if c.startswith("entry_")]
    X[:, ent[:n_split]] += np.where(truth[:, None] == 0, shift, -shift)
    return X, truth


def test_the_k_rule_reads_no_grouping_on_a_planted_split_at_the_real_shape_a_power_limit_not_whitening():
    """Documents the registered k rule's reach (§4.4: prediction strength on random HALVES, >= 0.80), at the real primary's shape — about 18
    whitened components, 658 rows — after the real primary read no stable grouping (06's BUILD NOTE; the review's F1). (a) On a factor world
    with a split planted on 8 of the 40 entry columns, the FULL-data k = 2 fit recovers the split exactly, yet the half-sample strength reads
    well under 0.80, so the rule reads 'no stable grouping' with the split there: the null cannot tell low power at this size from an absence
    of groups. (b) The first build's independent-noise world (`_synthetic_world(latent=False)`) also reads none, but it is a special case:
    its split is perfect on 8 of the 40 entry columns, not 'every' column, and it needs about 38 components. No remedy is asserted: the
    unwhitened components the first build offered read ARI about 0 on the factor world. Reported, not changed: the method is frozen."""
    cols = G.run_columns("primary")
    X, truth = _factor_world()
    maps = G.fit_maps(X, cols)
    Z, _e, _b = G.standardize(X, cols, maps)
    pca = G.PCA(Z)
    Zp = pca.transform(Z)
    assert 14 <= pca.m <= 22                                               # the real primary: 18 components at 90.7%
    fit = G.kmeans(Zp, 2, C.rng_for("step7_power_k2"))
    assert G.adjusted_rand(fit["labels"], truth) == pytest.approx(1.0)    # the split IS there and the full fit finds it
    ps = G.prediction_strength(Zp, 2, C.rng_for("step7_ps_power_k2"), halves=10)
    assert ps < 0.8                                                         # ... and the registered half-sample rule still reads none
    unwhitened = (Z - pca.mean) @ pca.vec
    assert abs(G.adjusted_rand(G.kmeans(unwhitened, 2, C.rng_for("power_unwhitened"))["labels"], truth)) < 0.2     # not a remedy
    feats, tiers, _r = _synthetic_world(latent=False)
    primary = G.fit_run("primary", feats, tiers, None, G.Say())
    assert primary["pca"].m > 30                                            # the special case: independent noise, tens of components
    assert primary["k"] is None and max(v["strength"] for v in primary["choice"]["sweep"].values()) < 0.8
    truth2 = np.array([int(e) % 2 for e in primary["eids"]])
    perfect = 0
    for k, c in enumerate(primary["cols"]):
        if not c.startswith("entry_"):
            continue
        v = primary["X"][:, k]
        a, b = v[truth2 == 0], v[truth2 == 1]
        if a.min() > b.max() or b.min() > a.max():
            perfect += 1
    assert perfect == 8                                                     # 8 of 40, not 'every entry column'
