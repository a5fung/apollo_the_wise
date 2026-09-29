"""#687 INDEPENDENT CHECK (1)+(2) — population re-derived from check_pull_out.txt (own SQL, raw floors in SQL) and
survivorship. Reads only captured files. Writes check_population.txt."""
from __future__ import annotations
import collections, csv, json, sys
from datetime import date, timedelta
from pathlib import Path
HERE = Path(__file__).resolve().parent
REPO = HERE.parents[2]
sys.path.insert(0, str(REPO))
from agents.market_intelligence.constants import SKIP_TICKERS  # the live list (a definition, not a result)

OUT = open(HERE / "check_population.txt", "w")
def P(*a):
    s = " ".join(str(x) for x in a); print(s); OUT.write(s + "\n")

def section(name):
    rows, hdr, on = [], None, False
    for l in open(HERE / "check_pull_out.txt"):
        l = l.rstrip("\n")
        if l.startswith("=== "):
            on = (l == f"=== {name} ==="); hdr = None; continue
        if not on or l in ("BEGIN", "ROLLBACK"):
            continue
        if hdr is None:
            hdr = l.split("|"); continue
        p = l.split("|")
        if len(p) == len(hdr):
            rows.append(dict(zip(hdr, p)))
    return rows

def f(x):
    try: return float(x)
    except (TypeError, ValueError): return None

# ── trading sessions (market-wide dates with a full grouped-daily file) ──
dates = sorted(date.fromisoformat(r["trade_date"]) for r in section("DATES") if int(r["n"]) > 3000)
prev_session = {d: dates[i - 1] for i, d in enumerate(dates) if i > 0}

# ── security types: the SAME captured sources the study used (no new lookups) ──
st = {}
for l in open(HERE / "pull_sectypes_out.txt"):
    p = l.rstrip("\n").split("|")
    if len(p) == 4 and p[0] != "ticker":
        st[p[0]] = p[1]
poly = json.load(open(HERE / "types_unclassified.json"))
def typ(t):
    if t in st: return st[t]
    return (poly.get(t) or {}).get("type") or "UNKNOWN"

rows = section("POP")
P(f"# #687 CHECK (1) POPULATION — own SQL (raw floors applied in SQL from splits executed <= 2026-09-29), n candidate rows {len(rows)}")
excl = collections.Counter(); kept = []; unk_pass = []
for r in rows:
    t = r["ticker"]; d = date.fromisoformat(r["trade_date"])
    o, pc, v, avgv20 = f(r["o"]), f(r["pc"]), f(r["v"]), f(r["avgv20"])
    fac = f(r["fac"]); low = f(r["low_close"]); adv = f(r["adv_dollar"]); nadv = int(r["nadv"] or 0)
    atr, lc, atr_n = f(r["atr14"]), f(r["atr_lastc"]), int(r["atr_n"] or 0)
    rec = {"t": t, "d": d, "o": o, "pc": pc, "fac": fac, "gap": (o - pc) / pc * 100, "pdate": date.fromisoformat(r["pdate"]),
           "vm": (v / avgv20) if avgv20 else None, "n20": int(r["n20"] or 0)}
    ty = typ(t)
    # other rules first so an UNKNOWN-typed row can be scored on everything else
    fails = []
    if low is None or (pc - low) / low * 100 >= 50: fails.append("ext")
    if nadv < 10 or adv is None or adv < 1_000_000: fails.append("adv")
    atr_pct = (atr / lc * 100) if (atr is not None and lc and atr_n >= 10) else None
    if atr_pct is not None and atr_pct > 15: fails.append("atr")
    if rec["vm"] is None or rec["vm"] < 3: fails.append("vol3x")
    if t in SKIP_TICKERS: excl["skip_list"] += 1; continue
    if ty not in ("CS", "ADRC"):
        excl[f"type:{ty}"] += 1
        if ty == "UNKNOWN" and not fails: unk_pass.append(rec)
        continue
    if fails:
        excl["fail:" + fails[0]] += 1; continue
    kept.append(rec)
kept.sort(key=lambda r: (r["d"], r["t"]))
last = {}; mine = []
for r in kept:
    if r["t"] in last and (r["d"] - last[r["t"]]).days < 60:
        excl["cooldown60"] += 1; continue
    last[r["t"]] = r["d"]; mine.append(r)
P("   exclusions:", dict(sorted(excl.items())))
theirs = {}
with open(HERE / "population.tsv") as fh:
    for r in csv.DictReader(fh, delimiter="|"):
        theirs[(r["ticker"], date.fromisoformat(r["trade_date"]))] = r
mk = {(r["t"], r["d"]): r for r in mine}
P(f"   MINE {len(mk)} gap-days on {len({k[0] for k in mk})} tickers | THEIRS {len(theirs)} on {len({k[0] for k in theirs})} | common {len(set(mk) & set(theirs))}")
for lab, S in (("mine", mk), ("theirs", theirs)):
    P(f"   by year {lab}:", dict(sorted(collections.Counter(k[1].year for k in S).items())))
only_m = sorted(set(mk) - set(theirs), key=lambda k: (k[1], k[0])); only_t = sorted(set(theirs) - set(mk), key=lambda k: (k[1], k[0]))
P(f"   ONLY MINE {len(only_m)}:", [(k[0], str(k[1]), round(mk[k]['fac'], 4), round(mk[k]['pc'] * mk[k]['fac'], 2)) for k in only_m][:40])
P(f"   ONLY THEIRS {len(only_t)}:", [(k[0], str(k[1]), theirs[k]['split_factor']) for k in only_t][:40])

# ── the adjusted-floor leak in pull_pop.sql: rows admitted only on RAW values that the adjusted SQL floor never saw ──
leak = [k for k in only_m if (mk[k]["pc"] < 5)]
leak_v = [k for k in only_m if k not in leak]
P(f"   of ONLY MINE: adjusted prior close < $5 but raw >= $5 (a later FORWARD split; pull_pop.sql's adjusted floor dropped it) {len(leak)}; "
  f"other (adjusted prior-day volume < 50k, raw >= 50k: a later REVERSE split) {len(leak_v)}")

# ── future-dated splits: population.py multiplied by every split in splits.json after d, incl. ones executing AFTER the pull ──
spl = collections.defaultdict(list)
for s in json.load(open(HERE / "splits.json")):
    spl[s["ticker"]].append(s)
fut = [(k, s["execution_date"], s["split_from"], s["split_to"]) for k in theirs for s in spl.get(k[0], [])
       if s["execution_date"] > "2026-09-29" and date.fromisoformat(s["execution_date"]) > k[1]]
P(f"   population rows whose raw-floor factor included a split executing AFTER the 2026-09-29 pull (not yet in any adjusted series): {len(fut)} {fut[:10]}")

# ── split-adjustment integrity: does mi_daily_closes carry each split (no jump across the ex-date)? ──
sc = section("SPLITCHECK"); cls = collections.Counter(); bad_sc = []
pop_t = {k[0] for k in theirs}
for r in sc:
    pcl, xo = f(r["pclose"]), f(r["xopen"])
    if not pcl or not xo:
        cls["no_bars"] += 1; continue
    ratio = xo / pcl; fac = float(r["sto"]) / float(r["sfrom"])
    if abs(fac - 1) < 0.2:
        cls["tiny_ratio_split"] += 1; continue
    # adjusted series: ratio ~ 1; unadjusted: ratio ~ 1/fac
    import math
    lr, lf = math.log(ratio), math.log(1 / fac)
    c_ = "adjusted" if abs(lr) < abs(lr - lf) else "UNADJUSTED"
    cls[c_] += 1
    if c_ == "UNADJUSTED":
        bad_sc.append((r["ticker"], r["xd"], r["sfrom"], r["sto"], round(ratio, 3), r["ticker"] in pop_t))
P(f"   SPLIT INTEGRITY (splits executed <= 2026-09-29, prior close vs ex-date open in mi_daily_closes): {dict(cls)}; "
  f"unadjusted splits on population tickers {sum(1 for x in bad_sc if x[5])}: {[x for x in bad_sc if x[5]][:15]}")

# ── prior ROW vs prior SESSION ──
stale = [k for k in theirs if k in mk and mk[k]["pdate"] != prev_session.get(k[1])]
P(f"   population rows whose prior close is NOT from the previous market session (lag(close) is the prior ROW): {len(stale)} "
  f"{[(k[0], str(k[1]), str(mk[k]['pdate']), str(prev_session.get(k[1]))) for k in sorted(stale, key=lambda k: k[1])[:25]]}")
gapdays = collections.Counter(min((k[1] - mk[k]["pdate"]).days, 99) for k in stale)
P(f"   calendar-day spread of those stale prior rows: {dict(sorted(gapdays.items()))}")

# ── look-ahead audit ──
P("   LOOK-AHEAD: admission reads the gap day's OPEN (09:30-knowable) and the gap day's FULL-DAY VOLUME (vol >= 3x; stated look-ahead);"
  " never its high/low/close (population.py reads o via gap_pct and v via vol_mult only). The 60-day cooldown is keyed on rows that PASSED the"
  " full-day volume rule, so it inherits the look-ahead: a day that failed on full-day volume never starts a cooldown.")
# how much the cooldown inherits: rows that pass everything EXCEPT vol3x and would, if they had started a cooldown, have blocked a kept row
pre_vol = sorted([r for r in rows if True], key=lambda r: (r["trade_date"], r["ticker"]))

# ── (2) SURVIVORSHIP ──
P("")
P("# #687 CHECK (2) SURVIVORSHIP")
sl = section("SURV_LAST")
yr = collections.Counter()
for r in sl:
    m = r["m"][:7]
    if m < "2026-09": yr[m[:4]] += int(r["tickers"])
P(f"   mi_daily_closes tickers whose LAST row falls in each year (a survivor-only table would show ~0 before the build date): {dict(sorted(yr.items()))}; "
  f"monthly 2024: {[int(r['tickers']) for r in sl if r['m'].startswith('2024')]}")

# vol_mult rounding: pull_pop.sql rounds vol_mult to 2 dp before the >= 3.0 test
rnd = [k for k in theirs if k not in mk and abs(float(theirs[k]["vol_mult"]) - 3.0) < 1e-9]
P(f"   rows admitted only because pull_pop.sql ROUNDS vol_mult to 2 dp (true v/avgv20 in [2.995, 3.0)): {len(rnd)} "
  f"{[(k[0], str(k[1])) for k in rnd]}; the rest of the set difference is the adjusted-floor leak (WIT fwd split; CDLX, MTEN reverse splits) "
  f"and two 60-day cooldown cascades (CDLX 03-15, BOOM 02-25)")

# UNKNOWN-typed rows (absent from mi_security_types AND from the 225-name Polygon lookup) that pass every other rule
ukt = collections.Counter(r["t"] for r in unk_pass)
P(f"   UNKNOWN-type rows that pass every OTHER rule (dropped as 'non_stock:UNKNOWN', not looked up): {len(unk_pass)} rows on {len(ukt)} tickers: "
  f"{sorted(ukt.items())}")
span = {r["ticker"]: (r["firstd"], r["lastd"]) for r in section("UNK_SPAN")}
real = {t for t in ukt if not (t.endswith("W") or t in ("ZVZZT", "ZJZZT") or t.endswith("Y") or t in ("FNGA", "FNGB", "CETH", "PXIU"))}
P(f"   of those, plausibly common stock (not a test ticker, warrant 'W', OTC ADR 'Y' or ETN/ETF by name): {len(real)} tickers, "
  f"{sum(ukt[t] for t in real)} rows: {[(t, ukt[t], span.get(t)) for t in sorted(real)]}")

# ── (2) in-population delisted / stopped-reporting names and what they contribute ──
lastbar = {}
for line in open(HERE / "pull_daily_out.txt"):
    p = line.rstrip("\n").split("|")
    if len(p) == 7 and p[0] != "ticker" and not p[0].startswith("==="):
        try: d = date.fromisoformat(p[1])
        except ValueError: continue
        if p[0] not in lastbar or d > lastbar[p[0]]: lastbar[p[0]] = d
HZ = date(2026, 8, 31)
dead = {t for t, d in lastbar.items() if d < HZ - timedelta(days=14)}
popdead = [k for k in theirs if k[0] in dead]
P(f"   population gap-days in names whose daily bars STOP before 2026-08-17 (delisted / acquired / stopped reporting): {len(popdead)} of {len(theirs)} "
  f"on {len({k[0] for k in popdead})} tickers; by entry year {dict(sorted(collections.Counter(k[1].year for k in popdead).items()))}")
apt = {}
with open(HERE / "arms_per_trade.tsv") as fh:
    for r in csv.DictReader(fh, delimiter="|"):
        apt[(r["ticker"], date.fromisoformat(r["entry_day"]))] = r
def R(r, a):
    return float(r[f"{a}_R"]) if r[f"{a}_status"] == "settled" and r[f"{a}_R"] else None
arms = ("A0", "A1", "D10", "T20_hs", "T20_be")
paired = [k for k, r in apt.items() if all(R(r, a) is not None for a in ("A0", "A1", "D10", "T20_hs", "S20_hs", "T20_be", "S20_be"))]
for lab, S in (("delisted-later", [k for k in paired if k[0] in dead]), ("still trading", [k for k in paired if k[0] not in dead])):
    n = len(S)
    tot = {a: sum(R(apt[k], a) for k in S) for a in arms}
    P(f"   {lab:15s} paired n={n:4d}: A0 total {tot['A0']:+8.2f} mean {tot['A0'] / max(n, 1):+.3f} | A1-A0 {tot['A1'] - tot['A0']:+7.2f} "
      f"D10-A0 {tot['D10'] - tot['A0']:+7.2f} T20_be-A0 {tot['T20_be'] - tot['A0']:+7.2f} T20_hs-A0 {tot['T20_hs'] - tot['A0']:+7.2f}")
fc = [(k, [apt[k][f"{a}_final"] for a in ("A0", "A1", "D10")]) for k in paired if any(apt[k][f"{a}_final"] == "delisted_forced_close" for a in ("A0", "A1", "D10"))]
P(f"   force-closed at the last close (main arms): {len(fc)} trades; per-arm final reasons {[(k[0], str(k[1]), v) for k, v in fc]}")
fcr = [(k, [apt[k][f"{a}_final"] for a in ("T20_hs", "S20_hs", "T20_be", "S20_be")]) for k in paired if any(apt[k][f"{a}_final"] == "delisted_forced_close" for a in ("T20_hs", "S20_hs", "T20_be", "S20_be"))]
P(f"   force-closed (runner arms): {[(k[0], str(k[1]), v) for k, v in fcr]}")
OUT.close()

# ── (2b) do the entry-day abstains (no 09:30 bar / minute gaps) fall on later-delisted names more often? ──
import gzip
have930 = set(); nbars = collections.Counter()
for n in ("minutes_entry.tsv.gz", "minutes_entry2.tsv.gz"):
    with gzip.open(HERE / n, "rt") as fh:
        for line in fh:
            p = line.split("|", 2)
            k = (p[0], p[1][:10])
            nbars[k] += 1
            if p[1][11:16] == "09:30":
                have930.add(k)
O2 = open(HERE / "check_population.txt", "a")
for lab, S in (("delisted-later", [k for k in theirs if k[0] in dead]), ("still trading", [k for k in theirs if k[0] not in dead])):
    no930 = sum(1 for k in S if (k[0], str(k[1])) not in have930)
    msg = f"   entry-day minute coverage, {lab}: {len(S)} gap-days, no 09:30 bar {no930} ({no930 / len(S) * 100:.1f}%)"
    print(msg); O2.write(msg + "\n")
O2.close()
