"""#622 redo — variant scoring pass (V1-V7 from _622sweep_variants_PREREGISTERED.md).
Runs locally, reads _622sweep_master.jsonl (written by _622sweep_join.py),
imports the REAL _score_ep + SCORE_WEIGHTS unmodified -- only builds
ALTERNATE weight dicts (dict-spread pattern, same style ep_rubric.py itself
uses for SCORE_WEIGHTS_LEGACY) and feeds them through the same pure function.
Nothing live touched; this is pure measurement.
"""
import copy
import json
import sys

sys.path.insert(0, "/Users/alvinfung/apollo_the_wise")

from agents.market_intelligence.ep_detector import _score_ep  # noqa: E402
from agents.market_intelligence.ep_rubric import SCORE_WEIGHTS, SEPARATION_BAR  # noqa: E402

PROBES = "/Users/alvinfung/apollo_the_wise/scripts/probes"

master = [json.loads(l) for l in open(f"{PROBES}/_622sweep_master.jsonl")]
settled = [r for r in master if r["status"] == "settled" and not r["is_degenerate"]]
settled_sorted = sorted(settled, key=lambda r: (r["scan_date"], r["ticker"]))
half = len(settled_sorted) // 2
first_half, second_half = settled_sorted[:half], settled_sorted[half:]
chpt = next(r for r in master if r["ticker"] == "CHPT")


def score_rows(rows, weights):
    out = []
    for r in rows:
        s, bd = _score_ep(weights=weights, **r["common_kwargs"])
        out.append((r, s, bd))
    return out


def group_stats(scored_rows, bar=SEPARATION_BAR):
    admitted = [(r, s) for r, s, bd in scored_rows if s >= bar]
    n = len(admitted)
    if n == 0:
        return {"n_admitted": 0, "sum_r": 0.0, "mean_r": None, "win_rate": None, "tickers": []}
    rs = [r["realized_r_0931"] for r, s in admitted]
    return {
        "n_admitted": n,
        "sum_r": round(sum(rs), 3),
        "mean_r": round(sum(rs) / n, 4),
        "win_rate": round(sum(1 for x in rs if x > 0) / n, 3),
        "tickers": sorted(f"{r['ticker']} {r['scan_date']} ({s}, R={r['realized_r_0931']:+.2f})"
                           for r, s in admitted),
    }


def evaluate_variant(name, weights, note=""):
    full = score_rows(settled, weights)
    fh = score_rows(first_half, weights)
    sh = score_rows(second_half, weights)
    chpt_s, chpt_bd = _score_ep(weights=weights, **chpt["common_kwargs"])
    return {
        "name": name, "note": note,
        "chpt_score": chpt_s, "chpt_admitted": chpt_s >= SEPARATION_BAR, "chpt_breakdown": chpt_bd,
        "full": group_stats(full),
        "first_half": group_stats(fh),
        "second_half": group_stats(sh),
        "baseline_full_mean_r": round(sum(r["realized_r_0931"] for r in settled) / len(settled), 4),
    }


results = {}

# V0 baselines (already computed in join, recompute here for a uniform report shape)
results["V0_HONEST_CURRENT"] = evaluate_variant(
    "V0_HONEST_CURRENT", SCORE_WEIGHTS, "current live rubric, all inputs honestly reconstructed")

from agents.market_intelligence.ep_rubric import SCORE_WEIGHTS_LEGACY  # noqa: E402
results["V0L_HONEST_LEGACY"] = evaluate_variant(
    "V0L_HONEST_LEGACY", SCORE_WEIGHTS_LEGACY, "pre-#533 rubric, all inputs honestly reconstructed")

# V1: legacy gap ladder only, current floor/liquidity/etc otherwise
v1_weights = {**SCORE_WEIGHTS, "gap": SCORE_WEIGHTS_LEGACY["gap"]}
results["V1_GAP_LEGACY_LADDER"] = evaluate_variant(
    "V1_GAP_LEGACY_LADDER", v1_weights,
    "current rubric, gap component swapped for the pre-#533 25/20/15/10 ladder")

# V2: gap reversed -- same cutpoints, inverted points
v2_gap = {
    "tiers": [(20, 10), (15, 15), (10, 20), (8, 25)],
    "default": 0,
    "source": "#622 redo V2 -- reversed ladder, smaller qualifying gap scores MORE",
}
v2_weights = {**SCORE_WEIGHTS, "gap": v2_gap}
results["V2_GAP_REVERSED"] = evaluate_variant(
    "V2_GAP_REVERSED", v2_weights,
    "current rubric, gap ladder inverted (8-9.9%->25 ... >=20%->10)")

# V3: vol_conviction grid
v3_grid = {}
for cut in (50, 60, 70, 80, 90, 95):
    for w in (5, 10, 15):
        vc = {"tiers": [(cut, w)], "default": 0, "source": f"#622 redo V3 grid cell cut={cut} w={w}"}
        weights = {**SCORE_WEIGHTS, "vol_conviction": vc}
        key = f"V3_VOLCONV_cut{cut}_w{w}"
        v3_grid[key] = evaluate_variant(key, weights, f"vol_conviction single tier: >={cut} -> {w} pts")
results["V3_VOLCONV_GRID"] = v3_grid

# V4: liquidity rescaled to this cohort's actual ADV$ range
v4_liq = {
    "adv_tiers": [(20_000_000, 15), (10_000_000, 12), (5_000_000, 10), (2_000_000, 7)],
    "adv_default": 0,
    "fallback_tiers": SCORE_WEIGHTS["liquidity"]["fallback_tiers"],
    "fallback_default": 0,
    "source": "#622 redo V4 -- liquidity tiers rescaled to this cohort's observed ADV$ range",
}
v4_weights = {**SCORE_WEIGHTS, "liquidity": v4_liq}
results["V4_LIQUIDITY_RESCALED"] = evaluate_variant(
    "V4_LIQUIDITY_RESCALED", v4_weights, "liquidity tiers at $2M/$5M/$10M/$20M instead of $50M-$500M")

with open(f"{PROBES}/_622sweep_variant_results.json", "w") as f:
    json.dump(results, f, indent=1, default=str)

# ─── console summary ───
print(f"baseline (unconditional) mean R on {len(settled)} settled: "
      f"{sum(r['realized_r_0931'] for r in settled)/len(settled):.4f}")
print(f"CHPT bar to clear: {SEPARATION_BAR}\n")

for key in ("V0_HONEST_CURRENT", "V0L_HONEST_LEGACY", "V1_GAP_LEGACY_LADDER", "V2_GAP_REVERSED",
            "V4_LIQUIDITY_RESCALED"):
    v = results[key]
    print(f"{key}: CHPT={v['chpt_score']} admitted={v['chpt_admitted']} | "
          f"full: n={v['full']['n_admitted']} sumR={v['full']['sum_r']} meanR={v['full']['mean_r']} "
          f"winrate={v['full']['win_rate']}")
    print(f"    first_half: n={v['first_half']['n_admitted']} meanR={v['first_half']['mean_r']} | "
          f"second_half: n={v['second_half']['n_admitted']} meanR={v['second_half']['mean_r']}")

print("\nV3 grid (only cells that admit CHPT):")
for key, v in results["V3_VOLCONV_GRID"].items():
    if v["chpt_admitted"]:
        print(f"  {key}: CHPT={v['chpt_score']} | full n={v['full']['n_admitted']} "
              f"sumR={v['full']['sum_r']} meanR={v['full']['mean_r']} | "
              f"fh n={v['first_half']['n_admitted']} meanR={v['first_half']['mean_r']} | "
              f"sh n={v['second_half']['n_admitted']} meanR={v['second_half']['mean_r']}")
