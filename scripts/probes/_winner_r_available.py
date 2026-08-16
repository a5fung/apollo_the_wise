#!/usr/bin/env python3
"""R-available-from-a-tradeable-entry over the 78 real-stock tail winners.

Sizes the INTC-shaped subset of the 78 tail winners (ep_profitability_program.md
2026-08-16 "HOW MANY IS ENOUGH"): of the names the 8x-ADR-from-close scan calls
winners, how many offered a large R from OUR entry/stop geometry?

Inputs (cached, read-only):
  scripts/probes/_552_cohort.psv      -- the 749 tier-A gap days incl. the 78 winners
  scripts/probes/_winner_r_bars.tsv   -- daily bars for the 68 winner tickers (pulled 2026-08-16)

Definitions (stated simplifications):
  entry  = EP-day HIGH (daily-resolution analogue of the ORB-high stop-buy; the
           real ORB high is <= the day high, so this is the WORST tradeable fill
           of the day -- R here is conservative vs the true ORB entry)
  stop1  = EP-day LOW            (risk1 = high - low = the day's range)
  stop2  = entry - 0.5*ADR*entry (risk2 = 0.5 * adr_frac * entry; guards against
           a freak-tight EP-day range inflating R arithmetically)
  R_avail = (max high over the NEXT 60 sessions - entry) / risk

Output: docs/analysis/winner_r_available_2026-08-16.txt  (capture once, read many)
"""
import csv, math, statistics as st
from collections import defaultdict

REPO = "/Users/alvinfung/apollo_the_wise"
COHORT = f"{REPO}/scripts/probes/_552_cohort.psv"
BARS = f"{REPO}/scripts/probes/_winner_r_bars.tsv"
OUT = f"{REPO}/docs/analysis/winner_r_available_2026-08-16.txt"
HORIZON = 60

# ---- load bars ----
bars = defaultdict(list)  # ticker -> [(date, o,h,l,c,v)]
with open(BARS) as f:
    for row in csv.reader(f, delimiter="|"):
        if len(row) < 7:
            continue
        t, d = row[0], row[1]
        o, h, l, c, v = (float(x) for x in row[2:7])
        bars[t].append((d, o, h, l, c, v))
for t in bars:
    bars[t].sort()

# ---- load cohort winners ----
winners = []
with open(COHORT) as f:
    for row in csv.reader(f, delimiter="|"):
        if len(row) < 12 or row[10] != "1":
            continue
        winners.append(dict(
            ticker=row[0], date=row[1], gap_pct=float(row[2]), o=float(row[3]),
            hi=float(row[4]), pc=float(row[5]), c=float(row[6]),
            adr_pct=float(row[7]), dvol_m=float(row[8]), tailx=float(row[9]),
            alert_n=int(row[11]),
        ))
assert len(winners) == 78, f"expected 78 winners, got {len(winners)}"

rows = []
for w in winners:
    seq = bars[w["ticker"]]
    idx = next((i for i, b in enumerate(seq) if b[0] == w["date"]), None)
    if idx is None:
        rows.append({**w, "err": "EP-day bar missing"})
        continue
    d, o, h, l, c, v = seq[idx]
    fwd = seq[idx + 1: idx + 1 + HORIZON]
    n_fwd = len(fwd)
    adr_frac = w["adr_pct"] / 100.0
    risk1 = h - l
    risk2 = 0.5 * adr_frac * h
    if n_fwd == 0:
        rows.append({**w, "err": "no forward sessions"})
        continue
    peak = max(b[2] for b in fwd)
    peak_i = max(range(n_fwd), key=lambda i: fwd[i][2])  # first occurrence of max? use argmax then min index
    # first session achieving the peak
    peak_i = next(i for i in range(n_fwd) if fwd[i][2] == peak)
    r1 = (peak - h) / risk1 if risk1 > 0 else float("nan")
    r2 = (peak - h) / risk2 if risk2 > 0 else float("nan")
    # matched-horizon R (20 sessions, same window as the tailx screen)
    fwd20 = fwd[:20]
    peak20 = max(b[2] for b in fwd20) if fwd20 else float("nan")
    r1_20 = (peak20 - h) / risk1 if risk1 > 0 else float("nan")
    # stop-1 breach before the peak session (daily resolution; same-day = ambiguous, counted)
    stop_first = any(fwd[i][3] < l for i in range(peak_i + 1))
    # close position within EP-day range
    cir = (c - l) / (h - l) if h > l else float("nan")
    rows.append({**w, "err": "", "entry": h, "stop1": l, "risk1": risk1,
                 "risk1_pct": risk1 / h * 100, "risk2": risk2,
                 "risk2_pct": risk2 / h * 100, "peak": peak, "n_fwd": n_fwd,
                 "days_to_peak": peak_i + 1, "r1": r1, "r2": r2, "r1_20": r1_20,
                 "stop1_breached_before_peak": stop_first, "close_in_range": cir})

ok = [r for r in rows if not r["err"]]
bad = [r for r in rows if r["err"]]

def bucket(r):
    if r <= 0:
        return "never exceeded entry"
    if r < 2:
        return "<2R"
    if r < 5:
        return "2-5R"
    if r < 10:
        return "5-10R"
    if r < 20:
        return "10-20R"
    return ">=20R"

ORDER = [">=20R", "10-20R", "5-10R", "2-5R", "<2R", "never exceeded entry"]

def dist(key):
    d = defaultdict(list)
    for r in ok:
        d[bucket(r[key])].append(r)
    return d

def spearman(xs, ys):
    def rank(v):
        s = sorted(range(len(v)), key=lambda i: v[i])
        rk = [0.0] * len(v)
        i = 0
        while i < len(s):
            j = i
            while j + 1 < len(s) and v[s[j + 1]] == v[s[i]]:
                j += 1
            avg = (i + j) / 2 + 1
            for k in range(i, j + 1):
                rk[s[k]] = avg
            i = j + 1
        return rk
    rx, ry = rank(xs), rank(ys)
    mx, my = st.mean(rx), st.mean(ry)
    num = sum((a - mx) * (b - my) for a, b in zip(rx, ry))
    den = math.sqrt(sum((a - mx) ** 2 for a in rx) * sum((b - my) ** 2 for b in ry))
    return num / den if den else float("nan")

def med(vals):
    return st.median(vals) if vals else float("nan")

L = []
P = L.append
P("WINNER R-AVAILABLE FROM A TRADEABLE ENTRY -- 2026-08-16")
P("=" * 78)
P("Cohort: the 78 real-stock tier-A tail winners (>=8xADR from close, 20d fwd),")
P("2026-03-01..07-15, from scripts/probes/_552_cohort.psv (ETF-clean rebuild).")
P("Bars: scripts/probes/_winner_r_bars.tsv (mi_daily_closes, pulled 2026-08-16,")
P("read-only). Entry = EP-day HIGH (daily ORB-high analogue -- worst tradeable")
P("fill of the day, conservative vs a real 09:31-09:45 ORB high). Stop1 = EP-day")
P("LOW. Stop2 = 0.5xADR below entry. R = (max high next 60 sessions - entry)/risk.")
P(f"N = {len(ok)} measured; {len(bad)} unmeasurable: " +
  ("; ".join(f"{r['ticker']} {r['date']} ({r['err']})" for r in bad) if bad else "none"))
P("")

for key, label in (("r1", "GEOMETRY 1: stop = EP-day low (risk = the day's range)"),
                   ("r2", "GEOMETRY 2: stop = 0.5xADR below entry")):
    d = dist(key)
    P(label)
    P("-" * len(label))
    for b in ORDER:
        rs = d.get(b, [])
        names = ", ".join(f"{r['ticker']} {r['date'][5:]}" for r in
                          sorted(rs, key=lambda r: -r[key]))
        P(f"  {b:<22} n={len(rs):>2}  {names}")
    ge10 = [r for r in ok if r[key] >= 10]
    ge5 = [r for r in ok if r[key] >= 5]
    P(f"  >=10R: {len(ge10)} of {len(ok)}  |  >=5R: {len(ge5)} of {len(ok)}"
      f"  |  median R: {med([r[key] for r in ok]):.2f}")
    P("")

# truncation + inflation flags
trunc = [r for r in ok if r["n_fwd"] < HORIZON]
P("INTEGRITY FLAGS")
P("---------------")
P(f"  Truncated forward windows (<{HORIZON} sessions available; late-cohort names):"
  f" n={len(trunc)}")
for r in sorted(trunc, key=lambda r: r["n_fwd"]):
    P(f"    {r['ticker']} {r['date']}: {r['n_fwd']} sessions (r1={r['r1']:.1f})")
tight = [r for r in ok if r["risk1_pct"] < 2.0]
P(f"  Tight-range inflation risk (EP-day range <2% of entry -> geometry-1 R"
  f" arithmetically inflated): n={len(tight)}")
for r in sorted(tight, key=lambda r: r["risk1_pct"]):
    P(f"    {r['ticker']} {r['date']}: range {r['risk1_pct']:.2f}% of entry,"
      f" r1={r['r1']:.1f} vs r2={r['r2']:.1f}")
sf = [r for r in ok if r["stop1_breached_before_peak"] and r["r1"] > 0]
sf10 = [r for r in sf if r["r1"] >= 10]
P(f"  Stop-1 (EP-day low) breached at daily resolution BEFORE the peak session:"
  f" n={len(sf)} of the {sum(1 for r in ok if r['r1']>0)} that exceeded entry;"
  f" {len(sf10)} of the >=10R names: "
  + ", ".join(f"{r['ticker']} {r['date'][5:]}" for r in sf10))
P("  (R-available deliberately ignores the breach -- it prices the move, not a")
P("   hold rule -- but a breached name needs the no-intraday-stop / re-entry fork")
P("   to be captured. Same caveat as INTC in the roadmap doc.)")
P("")

P("  Named data anomaly: TDIC 2026-05-12 -- next-day high $750 (close $576) then a")
P("  full round-trip to $20 the following session. A halt-prone squeeze where the")
P("  peak print was almost certainly not capturable; its 18.6R (geo-1) should be")
P("  read as an artifact of the definition, not a tradeable opportunity.")
P("")

# concentration + alert overlap for the >=10R subset
ge10_1 = [r for r in ok if r["r1"] >= 10]
sess = defaultdict(int)
for r in ge10_1:
    sess[r["date"]] += 1
P("CONCENTRATION AND ALERT OVERLAP OF THE >=10R (GEOMETRY-1) SUBSET")
P("----------------------------------------------------------------")
P(f"  n={len(ge10_1)} across {len(sess)} distinct sessions; largest single session: "
  + max(sess.items(), key=lambda kv: kv[1])[0] + f" carries {max(sess.values())}")
for dte, n in sorted(sess.items(), key=lambda kv: -kv[1])[:5]:
    P(f"    {dte}: {n}")
al = [r for r in ge10_1 if r["alert_n"] > 0]
P(f"  Live-alerted among the >=10R subset: {len(al)}"
  + (" -- " + ", ".join(f"{r['ticker']} {r['date'][5:]}" for r in al) if al else ""))
P(f"  Live-alerted among all 78: {sum(1 for r in ok if r['alert_n'] > 0)}"
  " (cohort psv counts live mi_ep_alerts rows only; the purge-era caveat from")
P("   missed_winners_why applies -- INTC/SMCI alert rows were purged, so 0 here)")
tr_lo = [r for r in ok if r["r1"] < 5 and r["n_fwd"] < HORIZON]
P(f"  Truncation bias in the <5R group: {len(tr_lo)} of {sum(1 for r in ok if r['r1'] < 5)}"
  f" have <{HORIZON} forward sessions -- their R can still grow; the SMCI-shaped"
  " count is partly an upper bound.")
P("")

# correlation
xs = [r["tailx"] for r in ok]
P("DOES THE 8xADR-FROM-CLOSE SCREEN TRACK R-FROM-ENTRY?")
P("----------------------------------------------------")
P(f"  Spearman(tailx, R geometry-1, 60d): {spearman(xs, [r['r1'] for r in ok]):+.3f}   (n={len(ok)})")
P(f"  Spearman(tailx, R geometry-2, 60d): {spearman(xs, [r['r2'] for r in ok]):+.3f}")
P(f"  Spearman(tailx, R geometry-1, matched 20d window): {spearman(xs, [r['r1_20'] for r in ok]):+.3f}")
P("")

# INTC-shaped vs SMCI-shaped
hi_grp = [r for r in ok if r["r1"] >= 10]
lo_grp = [r for r in ok if r["r1"] < 5]
mid_grp = [r for r in ok if 5 <= r["r1"] < 10]
P("INTC-SHAPED (>=10R geo-1) vs SMCI-SHAPED (<5R geo-1) AT EP-DAY TIME")
P("-------------------------------------------------------------------")
feats = [("gap_pct", "gap %"), ("adr_pct", "ADR %"), ("close_in_range", "close position in day range (1=at high)"),
         ("dvol_m", "dollar volume $M"), ("c", "close $"), ("risk1_pct", "EP-day range % of entry"),
         ("tailx", "tailx (screen score)"), ("days_to_peak", "sessions to fwd peak")]
P(f"  {'feature':<42}{'>=10R (n=' + str(len(hi_grp)) + ')':>16}{'5-10R (n=' + str(len(mid_grp)) + ')':>16}{'<5R (n=' + str(len(lo_grp)) + ')':>14}")
for k, lab in feats:
    P(f"  {lab:<42}{med([r[k] for r in hi_grp]):>16.2f}{med([r[k] for r in mid_grp]):>16.2f}{med([r[k] for r in lo_grp]):>14.2f}")
P("  Mechanics check (the gap/range separation is PARTLY the geo-1 denominator --")
P("  a wide day-1 range mechanically deflates R1). With the range removed from the")
P("  denominator it survives, weakened:")
P(f"    Spearman(gap %,   R geo-2 60d)  = {spearman([r['gap_pct'] for r in ok], [r['r2'] for r in ok]):+.3f}")
P(f"    Spearman(range %, R geo-2 60d)  = {spearman([r['risk1_pct'] for r in ok], [r['r2'] for r in ok]):+.3f}")
P(f"    Spearman(gap %,   days-to-peak) = {spearman([r['gap_pct'] for r in ok], [r['days_to_peak'] for r in ok]):+.3f}")
P("  So: bigger day-1 gaps yield somewhat less R even at a fixed ADR stop, and")
P("  they peak much sooner -- the INTC-shaped winner is a modest gap that grinds")
P("  for weeks; the SMCI-shaped one spends its move on day 1.")
P("")

# top 10
P("TOP 10 BY R AVAILABLE (geometry 1)")
P("----------------------------------")
P(f"  {'ticker':<7}{'EP day':<12}{'entry':>8}{'stop':>8}{'risk%':>7}{'peak':>9}{'d2pk':>6}"
  f"{'R geo1':>8}{'R geo2':>8}{'gap%':>7}{'alerted':>9}")
for r in sorted(ok, key=lambda r: -r["r1"])[:10]:
    P(f"  {r['ticker']:<7}{r['date']:<12}{r['entry']:>8.2f}{r['stop1']:>8.2f}"
      f"{r['risk1_pct']:>6.1f}%{r['peak']:>9.2f}{r['days_to_peak']:>6}"
      f"{r['r1']:>8.1f}{r['r2']:>8.1f}{r['gap_pct']:>7.1f}{('yes' if r['alert_n'] else 'no'):>9}")
P("")

# full per-name table
P("FULL PER-NAME TABLE (sorted by R geometry-1 desc)")
P("-------------------------------------------------")
P(f"  {'ticker':<7}{'EP day':<12}{'entry':>8}{'stop1':>8}{'risk1%':>8}{'peak':>9}"
  f"{'nfwd':>6}{'d2pk':>6}{'Rg1':>8}{'Rg2':>8}{'R20g1':>8}{'gap%':>7}{'ADR%':>6}"
  f"{'clsRng':>7}{'$volM':>8}{'tailx':>7}{'stop1st':>8}{'alert':>6}")
for r in sorted(ok, key=lambda r: -r["r1"]):
    P(f"  {r['ticker']:<7}{r['date']:<12}{r['entry']:>8.2f}{r['stop1']:>8.2f}"
      f"{r['risk1_pct']:>7.1f}%{r['peak']:>9.2f}{r['n_fwd']:>6}{r['days_to_peak']:>6}"
      f"{r['r1']:>8.1f}{r['r2']:>8.1f}{r['r1_20']:>8.1f}{r['gap_pct']:>7.1f}"
      f"{r['adr_pct']:>6.1f}{r['close_in_range']:>7.2f}{r['dvol_m']:>8.0f}"
      f"{r['tailx']:>7.1f}{('y' if r['stop1_breached_before_peak'] else 'n'):>8}"
      f"{('y' if r['alert_n'] else 'n'):>6}")
P("")
P("Simplifications, restated: entry is the DAY high, not the 09:31-09:45 ORB high")
P("(true ORB entry is lower -> more R than shown on names that ran all day; less")
P("on names that faded after the open -- direction of bias is name-dependent).")
P("Daily bars cannot order same-day high vs low; the stop-first flag is daily-")
P("resolution. 60-session horizon truncated for late-cohort names as flagged.")
P("Read-only; nothing proposed (THE LINE).")

with open(OUT, "w") as f:
    f.write("\n".join(L) + "\n")
print("\n".join(L[:120]))
print(f"\n[full capture -> {OUT}]")
