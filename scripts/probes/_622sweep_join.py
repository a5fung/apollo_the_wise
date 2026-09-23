"""#622 redo — Part 2 join + sweep. Runs LOCALLY (no docker/DB needed): imports
the REAL `ep_detector._score_ep` / `ep_rubric` tables directly (verified
byte-identical to the server run via a fidelity check reproducing CHPT's
prior buggy-input score 52.5/80.0 exactly before this script was written —
see chat record; not re-asserted here to keep this file focused on the sweep
itself).

Reads (all already captured, nothing paid runs here):
  _622sweep_features_out.jsonl   -- 154 point-in-time feature rows
  _622score_raw.jsonl            -- 48 catalyst grades (prior study)
  _622score_chpt_out.json        -- CHPT's catalyst grade (prior study)
  _622sweep_catalyst_raw.jsonl   -- 60 new catalyst grades (this session)
  _622_replay_out.tsv            -- realized_r_0931 / mark_r_0931 / status_0931

Variants are EXACTLY those pre-registered in
_622sweep_variants_PREREGISTERED.md, written and committed to disk before
this script was run.

Writes: _622sweep_master.jsonl (the joined per-row dataset) and
_622sweep_results.json (every stat this script produces, read by the human
summary written separately).
"""
import csv
import json
import math
import sys
from datetime import date

sys.path.insert(0, "/Users/alvinfung/apollo_the_wise")

from agents.market_intelligence.ep_detector import _score_ep  # noqa: E402
from agents.market_intelligence.ep_rubric import (  # noqa: E402
    SCORE_WEIGHTS, SCORE_WEIGHTS_LEGACY, SEPARATION_BAR, tier_points,
)

PROBES = "/Users/alvinfung/apollo_the_wise/scripts/probes"
DEGENERATE = {("RELL", "2026-06-08"), ("AVBC", "2026-07-24")}

# ─────────────────────────── load everything ───────────────────────────

features = {}
with open(f"{PROBES}/_622sweep_features_out.jsonl") as f:
    for line in f:
        r = json.loads(line)
        features[(r["ticker"], r["scan_date"])] = r

catalyst = {}
with open(f"{PROBES}/_622score_raw.jsonl") as f:
    for line in f:
        r = json.loads(line)
        catalyst[(r["ticker"], r["scan_date"])] = {**r, "grade_source": "prior_48sample"}
chpt_raw_grade = {
    "ticker": "CHPT", "scan_date": "2026-09-03", "catalyst_quality": "strong",
    "grade_source": "prior_chpt_case_study",
}
catalyst[("CHPT", "2026-09-03")] = chpt_raw_grade
with open(f"{PROBES}/_622sweep_catalyst_raw.jsonl") as f:
    for line in f:
        r = json.loads(line)
        catalyst[(r["ticker"], r["scan_date"])] = {**r, "grade_source": "this_session_new"}

replay = {}
with open(f"{PROBES}/_622_replay_out.tsv") as f:
    for row in csv.DictReader(f, delimiter="\t"):
        if row["cohort"] != "excluded":
            continue
        replay[(row["ticker"], row["scan_date"])] = row


def _rf(v):
    try:
        return float(v) if v not in (None, "") else None
    except (TypeError, ValueError):
        return None


# ─────────────────────────── build master rows ───────────────────────────

master = []
for key, feat in features.items():
    ticker, scan_date = key
    rrow = replay.get(key)
    if rrow is None:
        continue
    status = rrow["status_0931"]
    if status not in ("settled", "open_at_horizon"):
        continue
    is_degenerate = key in DEGENERATE
    realized_r = _rf(rrow["realized_r_0931"])
    mark_r = _rf(rrow["mark_r_0931"])
    cat = catalyst.get(key)
    if cat is None:
        # no_entry/no_trade/abstain rows never graded -- but settled/open_at_horizon
        # should ALL have a grade; flag loudly if not (data integrity check).
        print(f"WARNING: no catalyst grade for {key} (status={status})", file=sys.stderr)
        continue

    gap = feat.get("gap_pct_0931")
    vol_pct = feat.get("vol_pct_daily_bars")
    if vol_pct is None:
        # _volume_percentile's OWN "unknown/zero volume -- neutral" branch
        # (today_volume<=0 at the chosen tick, or empty adv_history) -- not a
        # default WE impose, the function's documented behavior.
        vol_pct = 50.0
    adv_dollar = feat.get("adv_dollar_0931")
    mcap = feat.get("market_cap_0931")
    float_shares = feat.get("float_shares_fmp_now")
    prior_3m = feat.get("prior_3m_change_0931")
    proj_vol = feat.get("projected_vol_multiple_0931")
    rel_vol = feat.get("rel_volume_0931")
    regime_mult = feat.get("regime_multiplier", 1.0)
    in_theme = bool(feat.get("in_active_theme"))
    quality = cat.get("catalyst_quality") or "routine"

    profile = {"floatShares": float_shares}
    common_kwargs = dict(
        gap_pct=gap, rel_volume=rel_vol, catalyst_quality=quality, profile=profile,
        regime_multiplier=regime_mult, vol_percentile=vol_pct, prior_3m_change=prior_3m,
        projected_vol_multiple=proj_vol, in_active_theme=in_theme, adv_dollar=adv_dollar,
    )
    s0, bd0 = _score_ep(weights=SCORE_WEIGHTS, **common_kwargs)
    s0l, bd0l = _score_ep(weights=SCORE_WEIGHTS_LEGACY, **common_kwargs)

    master.append({
        "ticker": ticker, "scan_date": scan_date, "status": status,
        "is_degenerate": is_degenerate, "realized_r_0931": realized_r, "mark_r_0931": mark_r,
        "gap_pct": gap, "vol_pct_daily_bars": vol_pct,
        "vol_pct_live_mechanism": feat.get("vol_pct_live_mechanism"),
        "adv_dollar": adv_dollar, "market_cap": mcap, "float_shares": float_shares,
        "prior_3m_change": prior_3m, "in_active_theme": in_theme,
        "regime_label": feat.get("regime_label"), "regime_multiplier": regime_mult,
        "catalyst_quality": quality, "grade_source": cat.get("grade_source"),
        "tick_dist_from_0931_sec": feat.get("tick_dist_from_0931_sec"),
        "today_volume_source": feat.get("today_volume_source"),
        "market_cap_source": feat.get("market_cap_source"),
        "v0_current": s0, "v0_current_bd": bd0,
        "v0_legacy": s0l, "v0_legacy_bd": bd0l,
        "common_kwargs": common_kwargs,
    })

with open(f"{PROBES}/_622sweep_master.jsonl", "w") as f:
    for r in master:
        f.write(json.dumps(r, default=str) + "\n")

print(f"master rows: {len(master)}")
n_settled_clean = sum(1 for r in master if r["status"] == "settled" and not r["is_degenerate"])
n_open = sum(1 for r in master if r["status"] == "open_at_horizon")
n_degenerate_settled = sum(1 for r in master if r["status"] == "settled" and r["is_degenerate"])
print(f"settled (clean): {n_settled_clean}  open_at_horizon: {n_open}  "
      f"degenerate settled (excluded from stats): {n_degenerate_settled}")

# ─────────────────────────── stats helpers ───────────────────────────

def spearman(xs, ys):
    """Spearman rank correlation, no scipy. Pairs with either value None dropped.
    Average ranks for ties. Returns (rho, n) or (None, n) if n<3."""
    pairs = [(x, y) for x, y in zip(xs, ys) if x is not None and y is not None
             and not (isinstance(x, float) and math.isnan(x))]
    n = len(pairs)
    if n < 3:
        return None, n
    xv = [p[0] for p in pairs]
    yv = [p[1] for p in pairs]

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


def clean_settled(rows):
    return [r for r in rows if r["status"] == "settled" and not r["is_degenerate"]]


def summarize_group(rows):
    rs = [r["realized_r_0931"] for r in rows]
    n = len(rs)
    if n == 0:
        return {"n": 0}
    return {
        "n": n, "sum_r": round(sum(rs), 3), "mean_r": round(sum(rs) / n, 4),
        "median_r": round(sorted(rs)[n // 2] if n % 2 else (sorted(rs)[n // 2 - 1] + sorted(rs)[n // 2]) / 2, 4),
        "win_rate": round(sum(1 for x in rs if x > 0) / n, 3),
    }


settled = clean_settled(master)
settled_sorted = sorted(settled, key=lambda r: (r["scan_date"], r["ticker"]))
half = len(settled_sorted) // 2
first_half = settled_sorted[:half]
second_half = settled_sorted[half:]

results = {"n_settled_clean": len(settled), "n_open_at_horizon": n_open,
           "baseline_full": summarize_group(settled),
           "baseline_first_half": summarize_group(first_half),
           "baseline_second_half": summarize_group(second_half),
           "date_split_boundary": second_half[0]["scan_date"] if second_half else None}

chpt = next((r for r in master if r["ticker"] == "CHPT"), None)
results["chpt"] = {
    "realized_r_0931": chpt["realized_r_0931"], "gap_pct": chpt["gap_pct"],
    "vol_pct_daily_bars": chpt["vol_pct_daily_bars"],
    "vol_pct_live_mechanism": chpt["vol_pct_live_mechanism"],
    "adv_dollar": chpt["adv_dollar"], "market_cap": chpt["market_cap"],
    "catalyst_quality": chpt["catalyst_quality"],
    "v0_current": chpt["v0_current"], "v0_current_bd": chpt["v0_current_bd"],
    "v0_legacy": chpt["v0_legacy"], "v0_legacy_bd": chpt["v0_legacy_bd"],
    "bar": SEPARATION_BAR,
} if chpt else None

# ─────────────────────────── univariate pass ───────────────────────────

def uni(rows, field, transform=None):
    xs = [transform(r[field]) if transform and r[field] is not None else r[field] for r in rows]
    ys = [r["realized_r_0931"] for r in rows]
    return spearman(xs, ys)

univariate_fields = [
    ("gap_pct", None), ("vol_pct_daily_bars", None), ("adv_dollar", None),
    ("adv_dollar_log10", lambda r: math.log10(r["adv_dollar"]) if r.get("adv_dollar") and r["adv_dollar"] > 0 else None),
    ("market_cap", None), ("float_shares", None), ("prior_3m_change", None),
]
uni_results = {}
for name, _ in univariate_fields:
    if name == "adv_dollar_log10":
        xs = [math.log10(r["adv_dollar"]) if r.get("adv_dollar") and r["adv_dollar"] > 0 else None for r in settled]
        ys = [r["realized_r_0931"] for r in settled]
        rho, n = spearman(xs, ys)
        xs1 = [math.log10(r["adv_dollar"]) if r.get("adv_dollar") and r["adv_dollar"] > 0 else None for r in first_half]
        ys1 = [r["realized_r_0931"] for r in first_half]
        rho1, n1 = spearman(xs1, ys1)
        xs2 = [math.log10(r["adv_dollar"]) if r.get("adv_dollar") and r["adv_dollar"] > 0 else None for r in second_half]
        ys2 = [r["realized_r_0931"] for r in second_half]
        rho2, n2 = spearman(xs2, ys2)
    else:
        rho, n = uni(settled, name)
        rho1, n1 = uni(first_half, name)
        rho2, n2 = uni(second_half, name)
    uni_results[name] = {
        "full": {"rho": round(rho, 3) if rho is not None else None, "n": n},
        "first_half": {"rho": round(rho1, 3) if rho1 is not None else None, "n": n1},
        "second_half": {"rho": round(rho2, 3) if rho2 is not None else None, "n": n2},
        "sign_agrees": (rho1 is not None and rho2 is not None and
                        ((rho1 > 0) == (rho2 > 0))) if rho1 is not None and rho2 is not None else None,
    }

# catalyst_quality (ordinal) and in_active_theme (binary), regime
qmap = {"routine": 0, "strong": 1, "game_changer": 2}
xs = [qmap.get(r["catalyst_quality"], 0) for r in settled]
ys = [r["realized_r_0931"] for r in settled]
rho, n = spearman(xs, ys)
uni_results["catalyst_quality_ordinal"] = {"full": {"rho": round(rho, 3) if rho else None, "n": n}}

xs = [1 if r["in_active_theme"] else 0 for r in settled]
rho, n = spearman(xs, ys)
uni_results["in_active_theme"] = {"full": {"rho": round(rho, 3) if rho else None, "n": n}}

xs = [1 if r["regime_label"] == "Bull" else 0 for r in settled]
rho, n = spearman(xs, ys)
uni_results["regime_bull"] = {"full": {"rho": round(rho, 3) if rho else None, "n": n}}

# catalyst quality group means (categorical, correlation isn't quite right for this)
by_quality = {}
for q in ("routine", "strong", "game_changer"):
    rows_q = [r for r in settled if r["catalyst_quality"] == q]
    by_quality[q] = summarize_group(rows_q)
uni_results["catalyst_quality_group_means"] = by_quality

results["univariate"] = uni_results

with open(f"{PROBES}/_622sweep_results.json", "w") as f:
    json.dump(results, f, indent=1, default=str)

print("Wrote _622sweep_master.jsonl and _622sweep_results.json (part 1: univariate pass)")
print(json.dumps({"chpt": results["chpt"], "baseline_full": results["baseline_full"]}, indent=1))
