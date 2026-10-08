"""#655 rule A hold-out — step 4: robustness of the hold-out G3-after-rule numbers ($0, local, read-only).

The drift-free figure (survivors keep tonight's verdicts) is the pre-stated measure. Because the hold-out
margins over the 90% bar are 1-2 themes, this re-runs the REAL `compute_g3` on each hold-out night's
board with the retired themes removed (what the nightly check would actually print — the RNG stream
shifts, so survivors can flip). First proves the rebuild reproduces the live row (headline + every
per-theme verdict) from the pulled inputs; only then trusts the after-rule recompute.
"""
import collections
import pickle
import sys
from datetime import timedelta

sys.path.insert(0, "/Users/alvinfung/apollo_the_wise")
from agents.market_intelligence import market_adjusted_correlation as mac
from agents.market_intelligence import theme_correctness as tc

import json

S = "/private/tmp/claude-501/-Users-alvinfung-apollo-the-wise/d30e3944-e07e-4b44-97de-010acba78d0b/scratchpad/"
HERE = "/Users/alvinfung/apollo_the_wise/scripts/probes/_655/rule_a_holdout/"
pull = pickle.load(open(S + "655_holdout_pull.pkl", "rb"))
anc = pickle.load(open(HERE + "a_discovery_anchor.pkl", "rb"))
ho = pickle.load(open(HERE + "c_holdout.pkl", "rb"))
lines = []


def P(*a):
    s = " ".join(str(x) for x in a)
    print(s)
    lines.append(s)


hist_by = collections.defaultdict(dict)
for r in pull["hist"]:
    hist_by[r["name"]][r["theme_date"]] = r
closes = pull["closes"]
live = {}
for a in pull["audit"]:
    if a["created_at"].hour < 12:
        continue
    live[a["created_at"].date()] = json.loads(a["detail"])["g3"]
HO = sorted(d for d in live if d.isoformat() >= "2026-10-05")


def inputs(D, score_lag):
    sds = sorted(d for d in pull["scores"] if d <= D)
    sd = sds[-1 - score_lag]
    scores = pull["scores"][sd]
    sector = {t: v["sector"] for t, v in scores.items() if v["sector"]}
    sessions = mac.session_index(closes.get(mac.MARKET_TICKER, {}), D, mac.BELONGING_LOOKBACK_SESSIONS)
    market = mac.log_returns(closes.get(mac.MARKET_TICKER, {}), sessions)
    excess = mac.excess_returns(closes, sessions, market)
    return scores, sector, excess, sd


def board(D):
    out = []
    for r in live[D]["themes"]:
        n = r["name"]
        ds = [d for d in hist_by[n] if D - timedelta(days=7) <= d <= D]
        t = list(hist_by[n][max(ds)]["tickers"]) if ds else []
        out.append({"name": n, "stage": r["stage"], "tickers": t})
    return out


ok_lag = {}
for D in HO:
    b = board(D)
    size_ok = sum(1 for t, r in zip(b, live[D]["themes"]) if len(t["tickers"]) == r["size"])
    for lag in (0, 1):
        scores, sector, excess, sd = inputs(D, lag)
        g = tc.compute_g3(b, excess, tc.usable_set(excess), scores, sector)
        lv = {r["name"]: r["pass_g3"] for r in live[D]["themes"]}
        same = sum(1 for r in g["themes"] if r["pass_g3"] == lv[r["name"]])
        P(f"{D} rebuild (scores {sd}): sizes match {size_ok}/{len(b)} | G3 {g['pass']}/{g['n_judgeable']} vs live "
          f"{live[D]['pass']}/{live[D]['n_judgeable']} | per-theme verdicts identical {same}/{len(b)}")
        if same == len(b) and D not in ok_lag:
            ok_lag[D] = lag

P("")
for key in ("A3a", "A3b", "A5a", "A5b"):
    K, framing = int(key[1]), key[2]
    retired = dict(ho[key]["new"])
    if framing == "b":
        retired.update(anc["res"][K]["retired"])
    cells = []
    for (D, r_df, p_df, n_df) in ho[key]["per"]:
        if D not in ok_lag:
            cells.append(f"{D.isoformat()[5:]} drift-free {r_df:.1f}% | recompute n/a (rebuild not exact)")
            continue
        gone = {n for n, d in retired.items() if d <= D}
        b = [t for t in board(D) if t["name"] not in gone]
        scores, sector, excess, _ = inputs(D, ok_lag[D])
        g = tc.compute_g3(b, excess, tc.usable_set(excess), scores, sector)
        cells.append(f"{D.isoformat()[5:]} drift-free {r_df:.1f}% | recompute {g['rate_pct']}% ({g['pass']}/{g['n_judgeable']}) "
                     f"{'PASS' if g['pass_bar'] else 'FAIL'}")
    P(f"{key}: " + "  ||  ".join(cells))

open(HERE + "d_recompute_check.out", "w").write("\n".join(lines) + "\n")
