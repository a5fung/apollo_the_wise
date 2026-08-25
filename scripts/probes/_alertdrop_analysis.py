"""Alert-volume collapse (2026-08-24) — funnel reconstruction from the ONE prod capture.
Reads scripts/probes/_alertdrop_capture_out.psv. Read-only, no network, $0."""
import sys, os, csv, io
from collections import defaultdict, Counter
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))
from agents.market_intelligence.missed_outcomes import _categorize_skip_reason

SEP = "|~|"
PATH = os.path.join(os.path.dirname(__file__), "_alertdrop_capture_out.psv")
raw = open(PATH).read().splitlines()

sections, cur = {}, None
for ln in raw:
    if ln.startswith("===Q"):
        cur = ln.strip("=")
        sections[cur] = []
        continue
    if cur is None:
        continue
    if ln.startswith("(") and ln.endswith("rows)"):
        continue
    sections[cur].append(ln)

def rows(name):
    body = sections[name]
    if not body:
        return []
    hdr = body[0].split(SEP)
    out = []
    for ln in body[1:]:
        p = ln.split(SEP)
        if len(p) != len(hdr):
            continue
        out.append(dict(zip(hdr, p)))
    return out

scan = rows("Q1_SCANLOG_DEDUPED")
health = {r["scan_date"]: r for r in rows("Q2_SCAN_HEALTH")}
tape = {r["trade_date"]: r for r in rows("Q5_TAPE_BREADTH")}
regime = {r["regime_date"]: r for r in rows("Q4_REGIME")}
alert_tier = rows("Q10_ALERT_DAILY_TIER")

# alerts per day (live source only)
alerts = defaultdict(Counter)
for r in alert_tier:
    if r["src"] != "live":
        continue
    alerts[r["alert_date"]][r["score_tier"]] += int(r["n"])

days = sorted(health)

# ---- categorise every deduped (day,ticker) last state ----
by_day = defaultdict(list)
for r in scan:
    by_day[r["scan_date"]].append(r)

cat_of = {}
day_cat = defaultdict(Counter)
day_qual = defaultdict(Counter)
for d, rs in by_day.items():
    for r in rs:
        fr = r["filter_reason"]
        fr = None if fr in ("<none>", "") else fr
        if fr is None:
            c = "ALERTED_" + (r["score_tier"] or "NONE")
        else:
            c = _categorize_skip_reason("scan_filter", fr)
        cat_of[(d, r["ticker"])] = c
        day_cat[d][c] += 1
        if r["catalyst_quality"]:
            day_qual[d][r["catalyst_quality"]] += 1

allcats = sorted({c for d in day_cat for c in day_cat[d]})

print("=" * 120)
print("FUNNEL — deduped to LAST state per (day, ticker). 'arrived' = distinct tickers in mi_ep_scan_log.")
print("=" * 120)
hdr = ["date", "reg", "bar", "tape10", "tape9L", "arrived"] + allcats + ["HIGH"]
print(SEP.join(hdr))
for d in days:
    reg = regime.get(d, {})
    t = tape.get(d, {})
    line = [d, (reg.get("regime") or "")[:6], reg.get("ep_threshold", ""),
            t.get("gap10", ""), t.get("gap9_liquid", ""), str(len(by_day.get(d, [])))]
    line += [str(day_cat[d].get(c, 0)) for c in allcats]
    line += [str(alerts[d].get("HIGH", 0))]
    print(SEP.join(line))

print()
print("=" * 120)
print("CATALYST QUALITY of every GRADED name (deduped last state)")
print("=" * 120)
quals = ["game_changing", "strong", "moderate", "weak", "routine"]
print(SEP.join(["date", "graded_total"] + quals))
for d in days:
    tot = sum(day_qual[d].values())
    print(SEP.join([d, str(tot)] + [str(day_qual[d].get(q, 0)) for q in quals]))

# ---- period aggregation ----
PERIODS = [
    ("A pre  07-27..08-07", [d for d in days if "2026-07-27" <= d <= "2026-08-07"]),
    ("B mid  08-10..08-14", [d for d in days if "2026-08-10" <= d <= "2026-08-14"]),
    ("C late 08-17..08-21", [d for d in days if "2026-08-17" <= d <= "2026-08-21"]),
]
print()
print("=" * 120)
print("PERIOD MEANS PER TRADING DAY")
print("=" * 120)
keys = ["tape10", "tape9_liquid", "arrived", "graded", "HIGH"] + allcats
print(SEP.join(["period", "n_days"] + keys))
for name, ds in PERIODS:
    n = len(ds)
    vals = {
        "tape10": sum(int(tape[d]["gap10"]) for d in ds) / n,
        "tape9_liquid": sum(int(tape[d]["gap9_liquid"]) for d in ds) / n,
        "arrived": sum(len(by_day.get(d, [])) for d in ds) / n,
        "graded": sum(sum(day_qual[d].values()) for d in ds) / n,
        "HIGH": sum(alerts[d].get("HIGH", 0) for d in ds) / n,
    }
    for c in allcats:
        vals[c] = sum(day_cat[d].get(c, 0) for d in ds) / n
    print(SEP.join([name, str(n)] + [f"{vals[k]:.1f}" for k in keys]))

print()
print("=" * 120)
print("SURVIVORSHIP LADDER — absolute per-day means and PASS RATES")
print("=" * 120)
for name, ds in PERIODS:
    n = len(ds)
    arrived = sum(len(by_day.get(d, [])) for d in ds) / n
    tape10 = sum(int(tape[d]["gap10"]) for d in ds) / n
    top20 = sum(day_cat[d].get("outside_top20", 0) for d in ds) / n
    graded = sum(sum(day_qual[d].values()) for d in ds) / n
    prefilters = sum(
        day_cat[d].get(c, 0) for d in ds
        for c in ("adv_low", "mcap_low", "atr_high", "extension_gate", "pm_rvol_low",
                  "session_rvol_low", "cooldown", "ma_filter", "duplicate_scan",
                  "d1_universe_floor", "filter_other")
    ) / n
    below = sum(day_cat[d].get("score_below_50", 0) for d in ds) / n
    routine = sum(day_cat[d].get("catalyst_downgrade", 0) for d in ds) / n
    high = sum(alerts[d].get("HIGH", 0) for d in ds) / n
    print(f"\n{name}   ({n} trading days)")
    print(f"  tape: gap>=10% names on the day      {tape10:8.1f}")
    print(f"  arrived in the scan                  {arrived:8.1f}   ({arrived/tape10*100:5.1f}% of tape)")
    print(f"  killed by mechanical pre-filters     {prefilters:8.1f}   ({prefilters/arrived*100:5.1f}% of arrivals)")
    print(f"  killed by the top-20 shortlist cap   {top20:8.1f}   ({top20/arrived*100:5.1f}% of arrivals)")
    print(f"  reached grading (has a catalyst)     {graded:8.1f}   ({graded/arrived*100:5.1f}% of arrivals)")
    print(f"  graded routine -> not scoreable      {routine:8.1f}   ({routine/graded*100:5.1f}% of graded)")
    print(f"  scored but under the bar             {below:8.1f}   ({below/graded*100:5.1f}% of graded)")
    print(f"  HIGH alerts                          {high:8.1f}   ({high/graded*100:5.1f}% of graded, {high/arrived*100:4.1f}% of arrivals)")
