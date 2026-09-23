"""#622 redo — advisor-directed rechecks before finalizing the report:
1. Gap Spearman + V1/V2 admitted stats restricted to fresh ticks (dist<=300s).
2. Per-half BASELINE-RELATIVE lift for every variant (not vs zero).
3. Exact mi_stock_scores coverage count (n_adv20_rows==0) across the 154 pop.
4. Precise V0 admitted-set mechanism (which names, which floor branch).
"""
import json
import math
import sys

sys.path.insert(0, "/Users/alvinfung/apollo_the_wise")
from agents.market_intelligence.ep_detector import _score_ep  # noqa: E402
from agents.market_intelligence.ep_rubric import SCORE_WEIGHTS, SCORE_WEIGHTS_LEGACY, SEPARATION_BAR  # noqa: E402

PROBES = "/Users/alvinfung/apollo_the_wise/scripts/probes"
master = [json.loads(l) for l in open(f"{PROBES}/_622sweep_master.jsonl")]
settled = [r for r in master if r["status"] == "settled" and not r["is_degenerate"]]
settled_sorted = sorted(settled, key=lambda r: (r["scan_date"], r["ticker"]))
half = len(settled_sorted) // 2
first_half, second_half = settled_sorted[:half], settled_sorted[half:]


def spearman(xs, ys):
    pairs = [(x, y) for x, y in zip(xs, ys) if x is not None and y is not None]
    n = len(pairs)
    if n < 3:
        return None, n
    xv, yv = [p[0] for p in pairs], [p[1] for p in pairs]

    def rank(vals):
        order = sorted(range(len(vals)), key=lambda i: vals[i])
        ranks = [0.0] * len(vals)
        i = 0
        while i < len(order):
            j = i
            while j + 1 < len(order) and vals[order[j + 1]] == vals[order[i]]:
                j += 1
            avg_rank = (i + j) / 2.0 + 1
            for k in range(i, j + 1):
                ranks[order[k]] = avg_rank
            i = j + 1
        return ranks
    rx, ry = rank(xv), rank(yv)
    mx, my = sum(rx) / n, sum(ry) / n
    cov = sum((a - mx) * (b - my) for a, b in zip(rx, ry))
    sx = math.sqrt(sum((a - mx) ** 2 for a in rx))
    sy = math.sqrt(sum((b - my) ** 2 for b in ry))
    if sx == 0 or sy == 0:
        return None, n
    return cov / (sx * sy), n


print("=== 1. Gap Spearman restricted to fresh ticks (dist<=300s) ===")
fresh = [r for r in settled if (r.get("tick_dist_from_0931_sec") or 1e9) <= 300]
stale = [r for r in settled if (r.get("tick_dist_from_0931_sec") or 1e9) > 300]
print(f"fresh n={len(fresh)}  stale n={len(stale)}")
xs = [r["gap_pct"] for r in fresh]
ys = [r["realized_r_0931"] for r in fresh]
rho, n = spearman(xs, ys)
print(f"gap_pct vs realized_r, FRESH ONLY: rho={rho:.3f} n={n}" if rho is not None else "n/a")
xs = [r["gap_pct"] for r in stale]
ys = [r["realized_r_0931"] for r in stale]
rho2, n2 = spearman(xs, ys)
print(f"gap_pct vs realized_r, STALE ONLY: rho={rho2:.3f} n={n2}" if rho2 is not None else "n/a")

print()
print("=== V1/V2 admitted stats, fresh-tick-only subsample ===")
v1_weights = {**SCORE_WEIGHTS, "gap": SCORE_WEIGHTS_LEGACY["gap"]}
v2_gap = {"tiers": [(20, 10), (15, 15), (10, 20), (8, 25)], "default": 0, "source": "V2"}
v2_weights = {**SCORE_WEIGHTS, "gap": v2_gap}
for name, weights in [("V1_GAP_LEGACY_LADDER", v1_weights), ("V2_GAP_REVERSED", v2_weights)]:
    admitted = []
    for r in fresh:
        s, bd = _score_ep(weights=weights, **r["common_kwargs"])
        if s >= SEPARATION_BAR:
            admitted.append((r, s))
    rs = [r["realized_r_0931"] for r, s in admitted]
    if rs:
        print(f"{name} (fresh-only, n={len(fresh)} eligible): admitted={len(rs)} "
              f"sumR={sum(rs):.2f} meanR={sum(rs)/len(rs):.3f}")
    else:
        print(f"{name} (fresh-only): 0 admitted")

print()
print("=== 2. Per-half BASELINE-RELATIVE lift for each variant ===")
baseline_fh = sum(r["realized_r_0931"] for r in first_half) / len(first_half)
baseline_sh = sum(r["realized_r_0931"] for r in second_half) / len(second_half)
baseline_full = sum(r["realized_r_0931"] for r in settled) / len(settled)
print(f"baseline: full={baseline_full:.4f}  first_half={baseline_fh:.4f} (n={len(first_half)})  "
      f"second_half={baseline_sh:.4f} (n={len(second_half)})")

variant_defs = {
    "V0_HONEST_CURRENT": SCORE_WEIGHTS,
    "V0L_HONEST_LEGACY": SCORE_WEIGHTS_LEGACY,
    "V1_GAP_LEGACY_LADDER": v1_weights,
    "V2_GAP_REVERSED": v2_weights,
    "V4_LIQUIDITY_RESCALED": {**SCORE_WEIGHTS, "liquidity": {
        "adv_tiers": [(20_000_000, 15), (10_000_000, 12), (5_000_000, 10), (2_000_000, 7)],
        "adv_default": 0, "fallback_tiers": SCORE_WEIGHTS["liquidity"]["fallback_tiers"],
        "fallback_default": 0, "source": "V4"}},
    "V3_VOLCONV_w10": {**SCORE_WEIGHTS, "vol_conviction": {"tiers": [(70, 10)], "default": 0, "source": "V3"}},
}


def admitted_stats(rows, weights):
    out = []
    for r in rows:
        s, bd = _score_ep(weights=weights, **r["common_kwargs"])
        if s >= SEPARATION_BAR:
            out.append((r["ticker"], r["scan_date"], s, r["realized_r_0931"]))
    return out


for name, weights in variant_defs.items():
    fh_adm = admitted_stats(first_half, weights)
    sh_adm = admitted_stats(second_half, weights)
    fh_r = [x[3] for x in fh_adm]
    sh_r = [x[3] for x in sh_adm]
    fh_mean = sum(fh_r) / len(fh_r) if fh_r else None
    sh_mean = sum(sh_r) / len(sh_r) if sh_r else None
    print(f"\n{name}:")
    if fh_mean is not None:
        lift_fh = fh_mean - baseline_fh
        print(f"  H1: n={len(fh_r)} meanR={fh_mean:.3f} vs H1 baseline {baseline_fh:.3f} -> lift {lift_fh:+.3f}")
        print(f"      names: {[f'{t} {d} R={r:+.2f}' for t,d,s,r in fh_adm]}")
    else:
        print("  H1: 0 admitted")
    if sh_mean is not None:
        lift_sh = sh_mean - baseline_sh
        print(f"  H2: n={len(sh_r)} meanR={sh_mean:.3f} vs H2 baseline {baseline_sh:.3f} -> lift {lift_sh:+.3f}")
        print(f"      names: {[f'{t} {d} R={r:+.2f}' for t,d,s,r in sh_adm]}")
    else:
        print("  H2: 0 admitted")

print()
print("=== 3. mi_stock_scores coverage across the 154 population ===")
feats = [json.loads(l) for l in open(f"{PROBES}/_622sweep_features_out.jsonl")]
zero_cov = sum(1 for r in feats if r.get("n_adv20_rows_mi_stock_scores") == 0)
print(f"n_adv20_rows_mi_stock_scores == 0: {zero_cov} / {len(feats)}")
nonzero = [r["n_adv20_rows_mi_stock_scores"] for r in feats if r.get("n_adv20_rows_mi_stock_scores")]
print(f"nonzero coverage rows: {len(nonzero)}, range {min(nonzero) if nonzero else None}-{max(nonzero) if nonzero else None}")

print()
print("=== 4. V0 admitted-set mechanism detail ===")
for r in settled:
    s, bd = _score_ep(weights=SCORE_WEIGHTS, **r["common_kwargs"])
    if s >= SEPARATION_BAR:
        print(f"  {r['ticker']} {r['scan_date']}: score={s} catalyst={r['catalyst_quality']} "
              f"regime={r['regime_label']} mult={r['regime_multiplier']} bd={bd} R={r['realized_r_0931']:+.2f}")

print()
print("=== V3 cut=50 contamination check (zero-volume rows clearing the 50 cut) ===")
zero_vol_rows = [r for r in settled if r.get("vol_pct_daily_bars") == 50.0 and
                 (r.get("adv_dollar") is None or True)]
# actual zero-volume-at-tick rows are the ones where features had vol_pct_daily_bars None -> filled 50
n_defaulted_50 = sum(1 for r in settled if r.get("vol_pct_daily_bars") == 50.0)
print(f"rows with vol_pct_daily_bars exactly 50.0 (includes function's own neutral default): {n_defaulted_50}")
