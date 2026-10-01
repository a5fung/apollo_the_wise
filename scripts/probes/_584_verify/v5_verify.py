"""#584 independent verify — re-derives the analyst's numbers from raw captures.
Inputs (captured once): v2_rows_out.csv (shadow rows <= 09-30), v3_closes_out.csv (daily bars),
v4_splits_out.csv. Output: v5_out.txt. Does NOT reuse scripts/probes/_584/*."""
import csv, math, statistics as st, sys
from collections import defaultdict
from datetime import date, timedelta

D = "/Users/alvinfung/apollo_the_wise/scripts/probes/_584_verify/"
out = open(D + "v5_out.txt", "w")
def p(*a):
    print(*a, file=out)

def fnum(x):
    return None if x in ("", None) else float(x)

rows = []
with open(D + "v2_rows_out.csv") as f:
    for r in csv.DictReader(f):
        r["scan_date"] = date.fromisoformat(r["scan_date"])
        for k in list(r):
            if k.startswith(("gap_pct", "today_", "prev_")):
                r[k] = fnum(r[k])
            if k.startswith("minutes_since_open"):
                r[k] = None if r[k] == "" else int(r[k])
        r["fp"] = r["failed_price_floor"] == "t"
        r["fv"] = r["failed_volume_floor"] == "t"
        r["rej"] = r["fp"] or r["fv"]
        r["cls"] = "PV" if (r["fp"] and r["fv"]) else ("P" if r["fp"] else ("V" if r["fv"] else "ADM"))
        rows.append(r)

bars = defaultdict(dict)  # ticker -> date -> (o,h,l,c,v)
datecount = defaultdict(int)
with open(D + "v3_closes_out.csv") as f:
    for r in csv.DictReader(f):
        d = date.fromisoformat(r["trade_date"])
        bars[r["ticker"]][d] = tuple(fnum(r[k]) for k in ("open_price", "high_price", "low_price", "close", "volume"))
        datecount[d] += 1
cal = sorted(d for d, n in datecount.items() if n >= 300)
calidx = {d: i for i, d in enumerate(cal)}

splits = []
with open(D + "v4_splits_out.csv") as f:
    for r in csv.DictReader(f):
        splits.append((r["ticker"], date.fromisoformat(r["execution_date"]), r["adjustment_applied"]))

def wilson(k, n, z=1.96):
    if n == 0:
        return (float("nan"), float("nan"))
    ph = k / n
    den = 1 + z * z / n
    c = (ph + z * z / (2 * n)) / den
    h = z * math.sqrt(ph * (1 - ph) / n + z * z / (4 * n * n)) / den
    return (100 * (c - h), 100 * (c + h))

def pct(x):
    return f"{100*x:+.1f}%"

# ---------------- 1. POPULATION ----------------
p("=== 1. POPULATION ===")
p("calendar sessions in captured bars:", cal[0], "->", cal[-1], "n=", len(cal))
sd = sorted({r["scan_date"] for r in rows})
p("scan dates:", sd[0], "->", sd[-1], "n=", len(sd))
p("total rows:", len(rows))
rej = [r for r in rows if r["rej"]]
adm = [r for r in rows if not r["rej"]]
p("rejected rows/names:", len(rej), len({r["ticker"] for r in rej}))
for c in ("P", "PV", "V"):
    p("  class", c, "rows", sum(1 for r in rej if r["cls"] == c))
p("admitted rows/names:", len(adm), len({r["ticker"] for r in adm}))
p("min gap_pct_first all rows:", round(min(r["gap_pct_first"] for r in rows if r["gap_pct_first"] is not None), 3))
rej_ao = [r for r in rej if r["today_dollar_volume_at_open"] is not None]
p("rejected with today_dollar_volume_at_open:", len(rej_ao), "names", len({r["ticker"] for r in rej_ao}))
p("rejected without at_open:", len(rej) - len(rej_ao))
p("  of those, minutes_since_open_last NOT NULL:", sum(1 for r in rej if r["today_dollar_volume_at_open"] is None and r["minutes_since_open_last"] is not None))
p("  of those, minutes_since_open_at_open NOT NULL:", sum(1 for r in rej if r["today_dollar_volume_at_open"] is None and r["minutes_since_open_at_open"] is not None))
p("  fallback-eligible (no at_open, last<=15):", sum(1 for r in rej if r["today_dollar_volume_at_open"] is None and r["minutes_since_open_last"] is not None and r["minutes_since_open_last"] <= 15))
p("rejected at_open dollar volume == 0:", sum(1 for r in rej_ao if r["today_dollar_volume_at_open"] == 0))
mix = defaultdict(int)
for r in rej_ao:
    mix[r["minutes_since_open_at_open"]] += 1
p("rejected at_open minute mix:", dict(sorted(mix.items())))
inw = [r for r in rej_ao if r["minutes_since_open_at_open"] <= 15]
p("rejected in-window (at_open min <=15):", len(inw), "names", len({r["ticker"] for r in inw}))
p("rejected out-of-window (min 20/25):", sum(1 for r in rej_ao if r["minutes_since_open_at_open"] > 15))
# fraction rows whose at_open minute dv mismatch: check dv = vol*price
bad = sum(1 for r in rej_ao if r["today_volume_at_open"] is not None and r["today_price_at_open"] and abs(r["today_volume_at_open"] * r["today_price_at_open"] - r["today_dollar_volume_at_open"]) > 1)
p("rows where dv_at_open != vol*price (>$1):", bad)

# ---------------- outcome builder ----------------
def outcome(r, h):
    """D0 = scan_date. returns dict or reason string."""
    t, d0 = r["ticker"], r["scan_date"]
    b = bars.get(t, {})
    if d0 not in calidx:
        return "d0_not_session"
    i0 = calidx[d0]
    if i0 + h >= len(cal):
        return "unsettled"
    fwd = [cal[i0 + k] for k in range(h + 1)]
    if any(d not in b for d in fwd):
        return "missing_fwd_bar"
    prior = [d for d in sorted(b) if d < d0][-20:]
    if len(prior) < 20:
        return "adr_short"
    adr = sum((b[d][1] - b[d][2]) / b[d][3] for d in prior) / 20
    o = b[d0][0]
    if not o:
        return "no_open"
    exc = max(b[d][1] for d in fwd) / o - 1
    exc_x0 = max(b[d][1] for d in fwd[1:]) / o - 1
    settled = b[fwd[-1]][3] / o - 1
    # jump guard: close_t / close_{t-1} for t in D0+1..D0+h
    jumps_up = jumps_dn = False
    for k in range(1, h + 1):
        c1, c0 = b[fwd[k]][3], b[fwd[k - 1]][3]
        if c0 and c1 / c0 > 4:
            jumps_up = True
        if c0 and c1 / c0 < 0.25:
            jumps_dn = True
    prevd = prior[-1]
    bar_gap = b[d0][0] / b[prevd][3] - 1
    return dict(adr=adr, exc=exc, exc_x0=exc_x0, settled=settled, ju=jumps_up, jd=jumps_dn,
                bar_gap=bar_gap, o=o, d0c=b[d0][3], d0v=b[d0][4], prevc=b[prevd][3])

H = 5
for r in rows:
    r["oc"] = outcome(r, H)

def settled_clean(rs, guard="up"):
    out_, reasons = [], defaultdict(int)
    for r in rs:
        o = r["oc"]
        if isinstance(o, str):
            reasons[o] += 1
            continue
        if guard == "up" and o["ju"]:
            reasons["jump_up"] += 1
            continue
        if guard == "both" and (o["ju"] or o["jd"]):
            reasons["jump_any"] += 1
            continue
        out_.append(r)
    return out_, dict(reasons)

settle_dates = [d for d in sd if calidx.get(d, 10**9) + H < len(cal)]
p("\n5-session settleable D0 dates:", settle_dates[0], "->", settle_dates[-1], "n=", len(settle_dates))
inw_s = [r for r in inw if r["scan_date"] in settle_dates]
p("in-window rejected, D0 settleable:", len(inw_s), "names", len({r["ticker"] for r in inw_s}))
cl, why = settled_clean(inw_s, "up")
p("  clean (guard up only):", len(cl), "names", len({r["ticker"] for r in cl}), "dropped:", why)
cl2, why2 = settled_clean(inw_s, "both")
p("  clean (guard both dirs):", len(cl2), "names", len({r["ticker"] for r in cl2}), "dropped:", why2)

# ---------------- 20-session ----------------
p("\n=== 20-session settled ===")
r20 = [r for r in inw if not isinstance(outcome(r, 20), str)]
p("in-window rejected rows with a D0+20 close in captured bars:", len(r20))
# forward calendar: Oct 2026 weekdays (no NYSE holiday in Oct; Columbus Day open)
fcal = list(cal)
d = cal[-1]
while len(fcal) < len(cal) + 40:
    d += timedelta(days=1)
    if d.weekday() < 5 and d != date(2026, 11, 26):
        fcal.append(d)
fidx = {d: i for i, d in enumerate(fcal)}
def date15(rs):
    first = {}
    for r in rs:
        dd = fcal[fidx[r["scan_date"]] + 20]
        if r["ticker"] not in first or dd < first[r["ticker"]]:
            first[r["ticker"]] = dd
    ds = sorted(first.values())
    return (ds[14] if len(ds) >= 15 else None, len(ds))
p("D0=2026-09-02 -> D0+20 =", fcal[fidx[date(2026, 9, 2)] + 20])
BARS = [10e6, 25e6, 50e6, 100e6]
for bv in BARS:
    allg = [r for r in inw if r["today_dollar_volume_at_open"] >= bv]
    g10 = [r for r in allg if r["gap_pct_at_open"] >= 10]
    p(f"  >=${bv/1e6:.0f}M  15th distinct name settles(20s) all gaps: {date15(allg)}   gap>=10: {date15(g10)}")

# ---------------- per-bar table ----------------
def stats(rs):
    n = len(rs)
    if n == 0:
        return "n=0"
    k = sum(1 for r in rs if r["oc"]["exc"] >= 8 * r["oc"]["adr"])
    kx = sum(1 for r in rs if r["oc"]["exc_x0"] >= 8 * r["oc"]["adr"])
    up = sum(1 for r in rs if r["oc"]["settled"] >= 0.20)
    dn = sum(1 for r in rs if r["oc"]["settled"] <= -0.20)
    dn50 = sum(1 for r in rs if r["oc"]["settled"] <= -0.50)
    med = st.median(r["oc"]["settled"] for r in rs)
    ex = sorted(r["oc"]["exc"] for r in rs)
    p90 = ex[min(len(ex) - 1, int(math.ceil(0.9 * len(ex))) - 1)]
    lo, hi = wilson(k, n)
    dlo, dhi = wilson(dn, n)
    return (f"n={n} names={len({r['ticker'] for r in rs})} reach={k}/{n} {100*k/n:.1f}% [{lo:.1f}-{hi:.1f}] "
            f"reach_exD0={kx}/{n} {100*kx/n:.1f}% | settled>=+20%: {up} {100*up/n:.1f}% | <=-20%: {dn} {100*dn/n:.1f}% [{dlo:.1f}-{dhi:.1f}] "
            f"| <=-50%: {dn50} | med settled {pct(med)} | exc med {pct(st.median(ex))} P90(nearest-rank) {pct(p90)} "
            f"P90(interp) {pct(st.quantiles(ex, n=10)[-1]) if n>1 else 'na'}")

def per_day(rs, dates):
    by = defaultdict(set)
    for r in rs:
        by[r["scan_date"]].add(r["ticker"])
    return sum(len(by[d]) for d in dates) / len(dates)

p("\n=== 2. PER-BAR TABLE (rejected, in-window, gap_pct_at_open>=10, 5-session, guard=up) ===")
for bv in BARS:
    allw = [r for r in inw if r["today_dollar_volume_at_open"] >= bv and r["gap_pct_at_open"] >= 10]
    allw_any = [r for r in inw if r["today_dollar_volume_at_open"] >= bv]
    s = [r for r in cl if r["today_dollar_volume_at_open"] >= bv and r["gap_pct_at_open"] >= 10]
    p(f">=${bv/1e6:.0f}M names/day (gap>=10) all-20={per_day(allw, sd):.2f} settled-15={per_day(allw, settle_dates):.2f} | any-gap all-20={per_day(allw_any, sd):.2f}"
      f" | share gap>=10 among clearers={len(allw)/max(1,len(allw_any)):.2f}")
    p("   ", stats(s))
    # attrition at this bar
    a = [r for r in inw_s if r["today_dollar_volume_at_open"] >= bv and r["gap_pct_at_open"] >= 10]
    _, w = settled_clean(a, "up")
    p("    attrition:", w, " guard-both n=", len(settled_clean(a, "both")[0]))
    # per-day share of 09-17
    by = defaultdict(int)
    for r in allw:
        by[r["scan_date"]] += 1
    top = sorted(by.items(), key=lambda x: -x[1])[:3]
    p("    top days by clearers:", [(str(d), n) for d, n in top], "of", len(allw))

# derived winners/day
p("\n  winners/day check (names/day x settled proportion, DERIVED not counted):")
for bv in BARS:
    allw = [r for r in inw if r["today_dollar_volume_at_open"] >= bv and r["gap_pct_at_open"] >= 10]
    s = [r for r in cl if r["today_dollar_volume_at_open"] >= bv and r["gap_pct_at_open"] >= 10]
    n = len(s)
    k = sum(1 for r in s if r["oc"]["exc"] >= 8 * r["oc"]["adr"])
    up = sum(1 for r in s if r["oc"]["settled"] >= 0.20)
    dn = sum(1 for r in s if r["oc"]["settled"] <= -0.20)
    npd = per_day(allw, sd)
    # actual counted per settled day
    p(f"   >=${bv/1e6:.0f}M derived: reach {npd*k/n:.2f}/day settle+20 {npd*up/n:.2f}/day crash {npd*dn/n:.2f}/day"
      f" | COUNTED over 15 settled days: reach {k/15:.2f} settle+20 {up/15:.2f} crash {dn/15:.2f}")

# ---------------- admitted comparator ----------------
p("\n=== 3. ADMITTED COMPARATOR (in-window, 5-session, guard=up) ===")
adm_ao = [r for r in adm if r["today_dollar_volume_at_open"] is not None and r["minutes_since_open_at_open"] is not None and r["minutes_since_open_at_open"] <= 15]
p("admitted in-window rows/names:", len(adm_ao), len({r["ticker"] for r in adm_ao}))
adm_s = [r for r in adm_ao if r["scan_date"] in settle_dates]
acl, aw = settled_clean(adm_s, "up")
p("admitted settled clean:", len(acl), "names", len({r["ticker"] for r in acl}), "dropped:", aw)
p("ADMITTED all gaps:", stats(acl))
a10 = [r for r in acl if r["gap_pct_at_open"] >= 10]
p("ADMITTED gap_at_open>=10:", stats(a10))
a10b = [r for r in acl if r["oc"]["bar_gap"] >= 0.10]
p("ADMITTED daily-bar open gap>=10% (#570 def):", stats(a10b))
a9 = [r for r in acl if r["gap_pct_at_open"] >= 9]
p("ADMITTED gap_at_open>=9 (live MIN_GAP_PCT):", stats(a9))
all_adm_g10 = [r for r in adm_ao if r["gap_pct_at_open"] >= 10]
p("admitted gap>=10 names/day all-20:", f"{per_day(all_adm_g10, sd):.2f}", "settled-15:", f"{per_day(all_adm_g10, settle_dates):.2f}")
p("share of admitted settled-clean with gap_at_open<10:", f"{sum(1 for r in acl if r['gap_pct_at_open']<10)/len(acl):.2f}")
for bv in BARS:
    s = [r for r in a10 if r["today_dollar_volume_at_open"] >= bv]
    k = sum(1 for r in s if r["oc"]["exc"] >= 8 * r["oc"]["adr"])
    p(f"  ADMITTED gap>=10 & >=${bv/1e6:.0f}M: {k}/{len(s)}")

p("\n=== review-literal (rejected, all gaps) ===")
for bv in BARS:
    s = [r for r in cl if r["today_dollar_volume_at_open"] >= bv]
    p(f">=${bv/1e6:.0f}M", stats(s))
p("\n=== rejected gap filter via daily-bar open gap>=10% instead of shadow gap ===")
for bv in BARS:
    s = [r for r in cl if r["today_dollar_volume_at_open"] >= bv and r["oc"]["bar_gap"] >= 0.10]
    p(f">=${bv/1e6:.0f}M", stats(s))

# ---------------- composition ----------------
p("\n=== composition (rejected in-window) ===")
p("median gap_at_open all in-window:", round(st.median(r["gap_pct_at_open"] for r in inw), 2), "share>=10:", round(sum(1 for r in inw if r["gap_pct_at_open"] >= 10) / len(inw), 3))
for bv in BARS:
    s = [r for r in inw if r["today_dollar_volume_at_open"] >= bv]
    p(f">=${bv/1e6:.0f}M n={len(s)} share gap>=10 {sum(1 for r in s if r['gap_pct_at_open']>=10)/len(s):.2f} med gap {st.median(r['gap_pct_at_open'] for r in s):.1f} "
      f"med prev_close {st.median(r['prev_close'] for r in s):.2f} P-class share {sum(1 for r in s if r['cls'] in ('P',))/len(s):.2f} P|PV {sum(1 for r in s if r['fp'])/len(s):.2f}"
      f" minute1 share {sum(1 for r in s if r['minutes_since_open_at_open']==1)/len(s):.2f}")
p("reads at minute 5-15 clearing $10M:", sum(1 for r in inw if r["minutes_since_open_at_open"] >= 5 and r["today_dollar_volume_at_open"] >= 10e6), "of", sum(1 for r in inw if r["minutes_since_open_at_open"] >= 5))

# ---------------- splits + premarket share ----------------
p("\n=== caveats ===")
for t, ed, aa in splits:
    hits = [r for r in inw if r["ticker"] == t and r["scan_date"] <= ed and calidx.get(r["scan_date"], -1) >= 0 and calidx[r["scan_date"]] + H < len(cal) and cal[calidx[r["scan_date"]] + H] >= ed]
    if hits:
        p(f"split {t} {ed} applied={aa} hits in-window rows D0..D0+5: {[str(r['scan_date']) for r in hits]}")
ratios = [r["today_volume_first"] / r["today_volume_at_open"] for r in inw
          if r["minutes_since_open_first"] is None and r["minutes_since_open_at_open"] == 1 and r["today_volume_at_open"]]
p("premarket-first & minute-1 rows:", len(ratios), "median first/at_open volume:", round(st.median(ratios), 3), "P25:", round(st.quantiles(ratios, n=4)[0], 3))
r50 = [r for r in inw if r["today_dollar_volume_at_open"] >= 50e6 and r["minutes_since_open_first"] is None and r["minutes_since_open_at_open"] == 1 and r["today_volume_at_open"]]
if r50:
    p(" same for $50M clearers n=", len(r50), "median:", round(st.median(r["today_volume_first"] / r["today_volume_at_open"] for r in r50), 3))
# D0 daily volume vs at_open volume for $50M clearers
rr = [r["today_volume_at_open"] / r["oc"]["d0v"] for r in inw if r["today_dollar_volume_at_open"] >= 50e6 and not isinstance(r["oc"], str) and r["oc"]["d0v"]]
if rr:
    p(" $50M clearers: at_open volume / D0 full-day bar volume median:", round(st.median(rr), 3))
# price sanity: shadow prev_close vs bar prev close
pc = [r["prev_close"] / r["oc"]["prevc"] for r in inw if not isinstance(r["oc"], str) and r["oc"]["prevc"]]
p("shadow prev_close / bar D-1 close: median", round(st.median(pc), 4), "outside [0.98,1.02]:", sum(1 for x in pc if not 0.98 <= x <= 1.02), "of", len(pc))

# ---------------- spot rows ----------------
p("\n=== spot rows (units) ===")
def spot(r, tag):
    o = r["oc"]
    p(f"{tag}: {r['scan_date']} {r['ticker']} cls={r['cls']} min={r['minutes_since_open_at_open']} vol={r['today_volume_at_open']:.0f} px={r['today_price_at_open']} "
      f"dv=${r['today_dollar_volume_at_open']/1e6:.1f}M gap_at_open={r['gap_pct_at_open']:.2f} (pct units) prev_close={r['prev_close']} "
      f"bar_gap={pct(o['bar_gap'])} D0open={o['o']} ADR20={100*o['adr']:.2f}% 8xADR={800*o['adr']:.1f}% exc={pct(o['exc'])} settled={pct(o['settled'])} reach={o['exc']>=8*o['adr']}")
c50 = sorted([r for r in cl if r["today_dollar_volume_at_open"] >= 50e6 and r["gap_pct_at_open"] >= 10], key=lambda r: -r["today_dollar_volume_at_open"])
spot(c50[len(c50) // 2], "REJ $50M clearer (median dv)")
win = [r for r in c50 if r["oc"]["exc"] >= 8 * r["oc"]["adr"]]
spot(win[0], "REJ $50M reach winner")
spot(a10[len(a10) // 2], "ADMITTED gap>=10")
p("\nREJ $50M gap>=10 settled rows (ticker date dv exc settled reach):")
for r in sorted(c50, key=lambda r: r["scan_date"]):
    o = r["oc"]
    p(f"  {r['scan_date']} {r['ticker']:6s} dv=${r['today_dollar_volume_at_open']/1e6:6.1f}M min={r['minutes_since_open_at_open']} gap={r['gap_pct_at_open']:6.1f} ADR={100*o['adr']:5.1f}% exc={pct(o['exc']):>8s} exD0={pct(o['exc_x0']):>8s} settled={pct(o['settled']):>8s} reach={'Y' if o['exc']>=8*o['adr'] else '.'}")
out.close()
