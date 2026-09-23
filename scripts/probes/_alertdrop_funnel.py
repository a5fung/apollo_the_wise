"""Alert-volume collapse (2026-08-24) — FURTHEST-STAGE funnel per (day, ticker).
Reads the two read-only prod captures. $0, no network."""
import sys, os, collections
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))
from agents.market_intelligence.missed_outcomes import _categorize_skip_reason

SEP = "|~|"
HERE = os.path.dirname(os.path.abspath(__file__))

def load(path):
    raw = open(path).read().splitlines()
    sec, body = None, collections.defaultdict(list)
    for ln in raw:
        if ln.startswith("===") and ln.endswith("==="):
            sec = ln.strip("="); continue
        if sec is None: continue
        if ln.startswith("(") and ln.endswith("rows)"): continue
        body[sec].append(ln)
    out = {}
    for k, v in body.items():
        if not v: out[k] = []; continue
        hdr = v[0].split(SEP)
        out[k] = [dict(zip(hdr, ln.split(SEP))) for ln in v[1:] if len(ln.split(SEP)) == len(hdr)]
    return out

cap1 = load(os.path.join(HERE, "_alertdrop_capture_out.psv"))
cap2 = load(os.path.join(HERE, "_alertdrop_capture2_out.psv"))
ticks = cap2["R1_SCANLOG_TICKS"]
tape = {r["trade_date"]: r for r in cap1["Q5_TAPE_BREADTH"]}
regime = {r["regime_date"]: r for r in cap1["Q4_REGIME"]}

alert_tier = collections.defaultdict(collections.Counter)
for r in cap1["Q10_ALERT_DAILY_TIER"]:
    if r["src"] == "live":
        alert_tier[r["alert_date"]][r["score_tier"]] += int(r["n"])
alerted_names = collections.defaultdict(dict)
for r in cap1["Q3_ALERTS"]:
    if r["src"] == "live":
        alerted_names[r["alert_date"]][r["ticker"]] = r["score_tier"]

# funnel position of each canonical category (higher = further down the funnel)
POS = {
    "d1_universe_floor": 10,
    "adv_low": 20, "mcap_low": 20, "atr_high": 20, "extension_gate": 20,
    "pm_rvol_low": 20, "session_rvol_low": 20, "cooldown": 20, "ma_filter": 20,
    "filter_other": 20, "infra_skip": 20, "setup_other": 20, "block_other": 20,
    "outside_top20": 30,
    "catalyst_downgrade": 80,
    "score_below_50": 90,
    "ALERTED": 100,
    "duplicate_scan": 0,       # post-decision artifact — never a terminal stage
}
GATE_NAMES = {
    "d1_universe_floor": "D-1 universe floor (prior close < $5 / prior volume < 50k)",
    "adv_low": "average dollar volume too thin",
    "mcap_low": "market cap under $500M",
    "atr_high": "daily swings too wild (ATR cap)",
    "extension_gate": "already ran too far before the gap",
    "pm_rvol_low": "pre-market volume below its usual pace",
    "session_rvol_low": "session volume below its usual pace",
    "cooldown": "alerted within the last 60 days",
    "ma_filter": "merger / buyout, not a momentum gap",
    "filter_other": "other filter",
    "outside_top20": "outside the top-20 grading shortlist",
    "catalyst_downgrade": "catalyst graded routine — not scoreable",
    "score_below_50": "scored, under the alert bar",
    "ALERTED_HIGH": "HIGH alert",
    "ALERTED_MODERATE": "MODERATE alert",
}

per = collections.defaultdict(lambda: {"pos": -1, "cat": None, "graded": False,
                                       "scored": False, "ticks": 0, "gap": None})
for r in ticks:
    d, t = r["scan_date"], r["ticker"]
    k = (d, t)
    st = per[k]
    st["ticks"] += 1
    if r["catalyst_quality"]:
        st["graded"] = True
    if r["ep_score"]:
        st["scored"] = True
    if st["gap"] is None and r["gap_pct"]:
        try: st["gap"] = float(r["gap_pct"])
        except ValueError: pass
    fr = r["filter_reason"]
    if fr == "<none>":
        cat = "ALERTED"
    else:
        cat = _categorize_skip_reason("scan_filter", fr)
    p = POS.get(cat, 20)
    if p > st["pos"]:
        st["pos"], st["cat"] = p, cat

days = sorted({d for d, _ in per})
day_bucket = collections.defaultdict(collections.Counter)
day_arrived, day_graded, day_scored = collections.Counter(), collections.Counter(), collections.Counter()
for (d, t), st in per.items():
    day_arrived[d] += 1
    if st["graded"]: day_graded[d] += 1
    if st["scored"]: day_scored[d] += 1
    tier = alerted_names.get(d, {}).get(t)
    if tier:
        cat = "ALERTED_" + tier
    elif st["cat"] == "ALERTED":
        cat = "reached_scan_end_no_alert_row"
    else:
        cat = st["cat"] or "unknown"
    day_bucket[d][cat] += 1

cats = ["d1_universe_floor", "mcap_low", "adv_low", "atr_high", "extension_gate",
        "pm_rvol_low", "session_rvol_low", "cooldown", "ma_filter", "filter_other",
        "outside_top20", "catalyst_downgrade", "score_below_50",
        "reached_scan_end_no_alert_row", "ALERTED_MODERATE", "ALERTED_HIGH"]
extra = sorted({c for d in day_bucket for c in day_bucket[d]} - set(cats))
cats += extra

print("### DAILY FUNNEL — every (day, ticker) assigned to the FURTHEST stage it reached")
print(SEP.join(["date", "regime", "bar", "tape_gap10", "arrived", "graded", "scored"] + cats))
for d in days:
    reg = regime.get(d, {}); tp = tape.get(d, {})
    row = [d, (reg.get("regime") or "-")[:10], reg.get("ep_threshold", "-"),
           tp.get("gap10", "-"), str(day_arrived[d]), str(day_graded[d]), str(day_scored[d])]
    row += [str(day_bucket[d].get(c, 0)) for c in cats]
    print(SEP.join(row))

PERIODS = [
    ("A  07-27..08-07", "2026-07-27", "2026-08-07"),
    ("B  08-10..08-14", "2026-08-10", "2026-08-14"),
    ("C  08-17..08-21", "2026-08-17", "2026-08-21"),
]
print()
print("### PER-TRADING-DAY MEANS BY PERIOD")
print(SEP.join(["period", "days", "tape_gap10", "tape_gap9L", "arrived", "graded", "scored"] + cats))
agg = {}
for name, lo, hi in PERIODS:
    ds = [d for d in days if lo <= d <= hi]
    n = len(ds)
    v = {
        "tape_gap10": sum(int(tape[d]["gap10"]) for d in ds) / n,
        "tape_gap9L": sum(int(tape[d]["gap9_liquid"]) for d in ds) / n,
        "arrived": sum(day_arrived[d] for d in ds) / n,
        "graded": sum(day_graded[d] for d in ds) / n,
        "scored": sum(day_scored[d] for d in ds) / n,
    }
    for c in cats:
        v[c] = sum(day_bucket[d].get(c, 0) for d in ds) / n
    agg[name] = v
    print(SEP.join([name, str(n)] + [f"{v[k]:.2f}" for k in
                   ["tape_gap10", "tape_gap9L", "arrived", "graded", "scored"] + cats]))

print()
print("### STAGE-BY-STAGE CHANGE (per trading day, and as a share of what ARRIVED)")
A, B, C = agg["A  07-27..08-07"], agg["B  08-10..08-14"], agg["C  08-17..08-21"]
print(f"{'stage':44s}{'A/day':>8s}{'B/day':>8s}{'C/day':>8s}   {'A%arr':>7s}{'B%arr':>7s}{'C%arr':>7s}")
def line(label, key):
    a, b, c = A[key], B[key], C[key]
    print(f"{label:44s}{a:8.1f}{b:8.1f}{c:8.1f}   "
          f"{a/A['arrived']*100:6.1f}%{b/B['arrived']*100:6.1f}%{c/C['arrived']*100:6.1f}%")
line("tape: names gapping >=10% that day", "tape_gap10")
line("ARRIVED in the scan", "arrived")
for c in cats:
    if A[c] + B[c] + C[c] > 0:
        line("  killed/ended: " + GATE_NAMES.get(c, c), c)
line("REACHED GRADING", "graded")
line("REACHED SCORING", "scored")

print()
print("### PASS RATES (survivorship)")
for name in agg:
    v = agg[name]
    arr, gr, sc = v["arrived"], v["graded"], v["scored"]
    hi = v["ALERTED_HIGH"]
    print(f"\n{name}")
    print(f"   arrived / tape gap>=10%        {arr/v['tape_gap10']*100:6.1f}%   ({arr:.1f} of {v['tape_gap10']:.1f})")
    print(f"   graded  / arrived              {gr/arr*100:6.1f}%   ({gr:.1f} of {arr:.1f})")
    print(f"   scored  / graded               {sc/gr*100:6.1f}%   ({sc:.1f} of {gr:.1f})")
    print(f"   HIGH    / scored               {hi/sc*100:6.1f}%   ({hi:.1f} of {sc:.1f})")
    print(f"   HIGH    / arrived              {hi/arr*100:6.1f}%")
