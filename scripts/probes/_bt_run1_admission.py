#!/usr/bin/env python3
"""EP backtest run 1 — admission stack under TODAY's rules (2026-08-29), $0 path.

Population: /Users/alvinfung/.claude/jobs/6b173ac9/tmp/_bt_population_capture.psv
(effective_gap = max(gap_pct_open, scanlog_max_gap) >= 9.0 -> 4,453 ticker-days).

Every constant read from code 2026-08-29 (see doc's manifest):
  ep_detector.py: MIN_PREV_CLOSE=5.0 MIN_PREV_DAY_VOLUME=50_000 MAX_TICKER_LEN=5
                  MAX_EXTENSION_PCT=50.0 (line 213, reverted today) EP_COOLDOWN_DAYS=60
                  ADV_BACKFILL_LIMIT=50 regime_multiplier=1.2 if Bull
  ep_rubric.py:   SCORE_WEIGHTS (flat gap 10 @ >=8; adv tiers 500/250/100/50M -> 15/12/10/7;
                  catalyst gc=25 strong=15; float +5; vol_conviction (90,5)(70,3);
                  theme +10; floor branch4 gap>=10+gc -> 60; output 1.25x+15; bar 65)
                  SHORTLIST_WEIGHTS liq(15,3) gap(10,1) theme(10,1); SHORTLIST_SIZE=20
  backtester/filters.py: MIN_ADV_DOLLAR_VOLUME=1M (median close*vol, 30d window, >=10 rows,
                  no-data -> SKIP); MAX_ATR_PCT=15 (Wilder 14, <10 rows -> pass);
                  MIN_MARKET_CAP=500M (missing -> pass)
  constants.py:   SKIP_TICKERS

Run L: catalyst=0, no floor. Run U: catalyst=15 all; 25 + floor where stored v3-era
(>=2026-06-12) grade says game_changer; stored 'mna' any era -> post-grade kill.
Judge OFF. Not simulated (stated in doc): sustain rule, pm/session RVOL, pm-shares floor,
float/vol_conviction points, per-tick shortlist churn, portfolio-level safeguards.
"""
import bisect, json, statistics, sys
from collections import defaultdict
from datetime import date, timedelta

TMP = "/Users/alvinfung/.claude/jobs/6b173ac9/tmp"

# mi_security_types (pulled 2026-08-29, TODAY's table — as-of drift stated in doc):
# live gate = skip security_type NOT IN ('CS','ADRC'); skip unclassified (P2.0b fail-safe).
SEC_TYPE = {}
_sec = None
for _line in open(f"{TMP}/bt_out_sec.psv"):
    _line = _line.rstrip("\n")
    if _line.startswith("=== "): _sec = _line[4:]; continue
    if _sec == "SECTYPES" and _line:
        _t, _st = _line.split("|"); SEC_TYPE[_t] = _st

SKIP_TICKERS = {
    "TQQQ","SQQQ","SPXL","SPXS","UPRO","SDS","SSO","QLD","QID","UDOW","SDOW","LABU","LABD",
    "SOXL","SOXS","TNA","TZA","FNGU","FNGD","TECL","TECS","FAS","FAZ","NUGT","DUST","JNUG",
    "JDST","GDXD","ERX","ERY","GUSH","DRIP","UVXY","SVXY","VXX","UVIX","SVIX","BOIL","KOLD",
    "UCO","SCO","AGQ","ZSL","GLL","DULL","UGL","YANG","YINN","CWEB","BRZU","BZQ","EDC","EDZ",
    "DRN","DRV","RETL","BNKU","MSTZ","MSTU","CONL","TSLL","NVDL","NVDS","MUU","MULL","SNXX",
    "QBTZ","WDCX","SPY","QQQ","IWM","DIA","VOO","VTI","IVV","RSP","XLK","XLE","XLF","XLV",
    "XLI","XLB","XLP","XLU","XLY","XLRE","XLC","SMH","IBB","XBI","GDX","GDXJ","KRE","USO",
    "BNO","DBO","UNG","GLD","SLV","IAU","PPLT","PALL","WEAT","CORN","SOYB","CPER","DBA","DBC",
    "GSG","PDBC","NRGU","NRGD","CRCA","OKLS",
}
ADV_TIERS = [(500e6,15),(250e6,12),(100e6,10),(50e6,7)]
SHORTLIST_SIZE, ADV_BACKFILL_LIMIT = 20, 50
MAX_EXTENSION_PCT, EP_COOLDOWN_DAYS = 50.0, 60
MIN_ADV_DOLLAR, MAX_ATR_PCT, MIN_MCAP = 1_000_000, 15.0, 500_000_000
RAW_GAP_PTS, THEME_PTS, CAT_STRONG, CAT_GC, FLOOR_GC = 10, 10, 15, 25, 60
BAR_PRESENTED = 65.0  # = (raw*mult)*1.25+15 >= 65  <=>  raw*mult >= 40

def tier_points(v, tiers, default=0):
    for cut, pts in tiers:
        if v >= cut: return pts
    return default

def pd(s): return date.fromisoformat(s)

# ── load population ──────────────────────────────────────────────────────────
pop = []
for line in open(f"{TMP}/_bt_population_capture.psv"):
    f = line.rstrip("\n").split("|")
    g = float(f[5]) if f[5] else -999.0
    s = float(f[6]) if f[6] else -999.0
    eff = max(g, s)
    if eff < 9.0: continue
    pop.append(dict(d=pd(f[0]), t=f[1], open=float(f[2]), prev_close=float(f[3]),
                    prev_volume=float(f[4]), gap_open=g, gap_scan=s, eff_gap=eff))
print(f"population ticker-days: {len(pop)}")

# ── load daily closes ────────────────────────────────────────────────────────
daily = defaultdict(list)          # ticker -> [(date, o,h,l,c,v)] sorted
for line in open(f"{TMP}/bt_out_daily.psv"):
    f = line.rstrip("\n").split("|")
    if len(f) != 7: continue
    o = float(f[2]) if f[2] else None; h = float(f[3]) if f[3] else None
    l = float(f[4]) if f[4] else None
    daily[f[0]].append((pd(f[1]), o, h, l, float(f[5]), float(f[6])))
for t in daily: daily[t].sort()
d_dates = {t: [r[0] for r in rows] for t, rows in daily.items()}
all_dates = sorted({r[0] for rows in daily.values() for r in rows})  # global calendar

# ── load small capture sections ──────────────────────────────────────────────
sec = None
regime_rows, themes, mcap, adv_map, scan_grades, alerts = [], [], {}, {}, defaultdict(set), []
for line in open(f"{TMP}/bt_out_small.psv"):
    line = line.rstrip("\n")
    if line.startswith("=== "): sec = line[4:]; continue
    if not line: continue
    f = line.split("|")
    if sec == "REGIME": regime_rows.append((pd(f[0]), f[1]))
    elif sec == "THEMES": themes.append((pd(f[0]), f[1], f[2], set(f[3].split(",")) if f[3] else set()))
    elif sec == "MCAPS": mcap[f[0]] = float(f[1])
    elif sec == "STOCK_SCORES_ADV":
        if f[2]: adv_map[(pd(f[0]), f[1])] = float(f[2])
    elif sec == "SCANLOG_GRADES": scan_grades[(pd(f[0]), f[1])].add(f[2])
    elif sec == "ALERTS":
        alerts.append(dict(d=pd(f[0]), t=f[1], cq=f[2], tier=f[3], src=f[5]))
        if f[2]: scan_grades[(pd(f[0]), f[1])].add(f[2])
regime_rows.sort(); regime_dates = [r[0] for r in regime_rows]
score_dates = sorted({k[0] for k in adv_map})

# first qualifying scanlog tick (UTC) per ticker-day
first_tick = {}
sec = None
for line in open(f"{TMP}/bt_out_cov.psv"):
    line = line.rstrip("\n")
    if line.startswith("=== "): sec = line[4:]; continue
    if not line: continue
    f = line.split("|")
    if sec == "SCANLOG_FIRST_QUALIFYING_TICK" and len(f) == 3:
        first_tick[(pd(f[0]), f[1])] = f[2]  # e.g. '2026-05-01 13:50:00.033586+00'

# ORB bar coverage (re-derived from DB — population file's has_orb_bar is STALE)
cov = {}
sec = None
for line in open(f"{TMP}/bt_out_cov.psv"):
    line = line.rstrip("\n")
    if line.startswith("=== "): sec = line[4:]; continue
    if not line or sec != "ORB_COVERAGE": continue
    f = line.split("|")
    if len(f) == 5: cov[(pd(f[1]), f[0])] = (int(f[2]), int(f[3]), int(f[4]))

# ── as-of helpers ────────────────────────────────────────────────────────────
def regime_asof(d):        # latest regime_date < d (EOD job; D's row absent at 9:30)
    i = bisect.bisect_left(regime_dates, d)
    return regime_rows[i-1][1] if i > 0 else "Unknown"

_theme_cache = {}
def theme_set_asof(d):     # latest snapshot per name, theme_date in [d-7, d-1]; drop Retired
    if d in _theme_cache: return _theme_cache[d]
    latest = {}
    for td, name, stage, tks in themes:
        if d - timedelta(days=7) <= td < d:
            if name not in latest or td > latest[name][0]: latest[name] = (td, stage, tks)
    out = set()
    for td, stage, tks in latest.values():
        if stage in ("Accelerating", "Mainstream"): out |= tks
    _theme_cache[d] = out
    return out

def stored_adv_asof(t, d): # get_adv_map(prev trading day): latest score_date < d (<=5d back)
    i = bisect.bisect_left(score_dates, d)
    if i == 0: return None
    sd = score_dates[i-1]
    if (d - sd).days > 5: return None
    return adv_map.get((sd, t))

def rows_before(t, d, cal_days):
    rows = daily.get(t, [])
    dates = d_dates.get(t, [])
    lo = bisect.bisect_left(dates, d - timedelta(days=cal_days))
    hi = bisect.bisect_left(dates, d)
    return rows[lo:hi]

def adv_filter_median(t, d):   # median close*volume, [d-30, d-1], >=10 rows else None
    rows = rows_before(t, d, 30)
    if len(rows) < 10: return None
    return statistics.median(r[4] * r[5] for r in rows)

def adv20_backfill(t, d):      # mean volume last 20 trading days strictly before d
    rows = rows_before(t, d, 45)[-20:]
    if len(rows) < 10: return None
    return sum(r[5] for r in rows) / len(rows)

def atr14_pct(t, d):           # Wilder on rows through d-1 (live at 9:31 lacks day-d row)
    rows = rows_before(t, d, 35)
    rows = [r for r in rows if r[2] is not None and r[3] is not None]
    if len(rows) < 10: return None
    trs = []
    for i in range(1, len(rows)):
        h, l, pc = rows[i][2], rows[i][3], rows[i-1][4]
        trs.append(max(h - l, abs(h - pc), abs(l - pc)))
    if not trs: return None
    w = trs[-14:]
    atr = sum(w) / len(w)
    lc = rows[-1][4]
    return atr / lc * 100 if lc > 0 else None

def min_close_ext(t, d):       # MIN(close), trade_date in [d-10, d)
    rows = rows_before(t, d, 10)
    return min((r[4] for r in rows), default=None)

def in_orb_window(c):
    if c["gap_open"] >= 9.0: return True
    ft = first_tick.get((c["d"], c["t"]))
    if ft is None: return True    # unknown tick time -> assume in-window (over-admit, counted)
    hhmm = ft[11:16]              # UTC; 09:44 ET == 13:44 UTC (EDT window Apr-Aug)
    return hhmm <= "13:44"

def grade_of(c, run):
    g = scan_grades.get((c["d"], c["t"]), set())
    if run == "L": return None
    if "mna" in g: return "mna"
    if "game_changer" in g and c["d"] >= date(2026, 6, 12): return "game_changer"
    return "strong"

# ── the funnel ───────────────────────────────────────────────────────────────
def run_funnel(run):
    kills = defaultdict(int)
    admitted, replayable = [], []
    alert_hist = defaultdict(list)   # ticker -> [alert dates], self-consistent per run
    days = sorted({c["d"] for c in pop})
    floor_pass = []
    for c in pop:
        if len(c["t"]) > 5 or c["t"] in SKIP_TICKERS: kills["1_universe_floor"] += 1
        elif SEC_TYPE.get(c["t"]) not in ("CS", "ADRC"):
            kills["1b_sectype_" + ("nonstock" if c["t"] in SEC_TYPE else "unclassified")] += 1
        elif c["prev_close"] < 5.0: kills["1_universe_floor"] += 1
        elif c["prev_volume"] < 50_000: kills["1_universe_floor"] += 1
        else: floor_pass.append(c)
    by_day = defaultdict(list)
    for c in floor_pass: by_day[c["d"]].append(c)

    n_cooldown_gap15 = 0
    for d in days:
        cands = by_day.get(d, [])
        theme_set = theme_set_asof(d)
        regime = regime_asof(d)
        mult = 1.2 if regime == "Bull" else 1.0
        # prescore (stored-ADV only, mirrors sort-time adv_source check)
        entries = []
        for c in cands:
            adv_sh = stored_adv_asof(c["t"], d)
            advd = adv_sh * c["prev_close"] if adv_sh else None
            in_theme = c["t"] in theme_set
            liq = tier_points(advd, ADV_TIERS) if advd else None
            raw = {"liquidity": liq, "gap": 10, "theme_bonus": 10 if in_theme else 0}
            avail = [k for k in raw if raw[k] is not None]
            wts = {"liquidity": (15, 3), "gap": (10, 1), "theme_bonus": (10, 1)}
            weighted = sum(raw[k] * wts[k][1] for k in avail)
            max_av = sum(wts[k][0] * wts[k][1] for k in avail)
            comp = round(weighted * 65 / max(1, max_av), 2)
            entries.append((c, comp, advd, in_theme))
        entries.sort(key=lambda e: (-e[1], -(e[2] or 0.0), e[0]["t"]))
        for c, *_ in entries[SHORTLIST_SIZE:]: kills["2_shortlist_cap"] += 1
        rank = 0
        for c, comp, advd_stored, in_theme in entries[:SHORTLIST_SIZE]:
            rank += 1
            t = c["t"]
            # cooldown (self-consistent; no earnings bypass — counted)
            hist = alert_hist[t]
            if any(0 < (d - ad).days <= EP_COOLDOWN_DAYS for ad in hist):
                kills["3_cooldown"] += 1
                if c["eff_gap"] >= 15: n_cooldown_gap15 += 1
                continue
            # extension
            low5 = min_close_ext(t, d)
            if low5 and low5 > 0 and c["prev_close"]:
                if (c["prev_close"] - low5) / low5 * 100 >= MAX_EXTENSION_PCT:
                    kills["4_extension"] += 1; continue
            # quality filters (code order: ADV -> ATR -> mcap)
            advmed = adv_filter_median(t, d)
            if advmed is None: kills["5_adv_no_data"] += 1; continue
            if advmed < MIN_ADV_DOLLAR: kills["5_adv_too_low"] += 1; continue
            ap = atr14_pct(t, d)
            if ap is not None and ap > MAX_ATR_PCT: kills["6_atr"] += 1; continue
            mc = mcap.get(t)
            if mc is not None and mc < MIN_MCAP: kills["7_mcap"] += 1; continue
            # score
            adv_sh = stored_adv_asof(t, d) or adv20_backfill(t, d)   # backfill: rank<=50 always true here
            advd = adv_sh * c["prev_close"] if adv_sh else None
            liq_pts = tier_points(advd, ADV_TIERS) if advd else 0
            g = grade_of(c, run)
            if g == "mna": kills["9_postgrade_mna"] += 1; continue
            cat_pts = 0 if run == "L" else (CAT_GC if g == "game_changer" else CAT_STRONG)
            raw = RAW_GAP_PTS + liq_pts + cat_pts + (THEME_PTS if in_theme else 0)
            if run == "U" and g == "game_changer" and c["eff_gap"] >= 10:
                raw = max(raw, FLOOR_GC)
            presented = raw * mult * 1.25 + 15
            if presented < BAR_PRESENTED: kills["8_score_bar"] += 1; continue
            # HIGH alert — enters cooldown history regardless of ORB window
            alert_hist[t].append(d)
            admitted.append(dict(c, run=run, raw=raw, presented=round(presented, 1),
                                 liq_pts=liq_pts, cat=g or "none", theme=in_theme,
                                 regime=regime))
            if not in_orb_window(c): kills["10_orb_window"] += 1; continue
            replayable.append(admitted[-1])
    return dict(kills=kills, admitted=admitted, replayable=replayable,
                floor_pass=len(floor_pass), cooldown_gap15=n_cooldown_gap15)

res = {}
for run in ("L", "U"):
    r = run_funnel(run)
    res[run] = r
    print(f"\n== RUN {run} ==  floors passed: {r['floor_pass']}")
    for k in sorted(r["kills"]): print(f"  {k}: {r['kills'][k]}")
    print(f"  ADMITTED (HIGH): {len(r['admitted'])}  replayable (in ORB window): {len(r['replayable'])}")
    print(f"  cooldown kills w/ gap>=15 (bypass upper bound): {r['cooldown_gap15']}")

# sanity: L subset of U (per ticker-day)
setL = {(a["d"], a["t"]) for a in res["L"]["admitted"]}
setU = {(a["d"], a["t"]) for a in res["U"]["admitted"]}
print(f"\nL admitted not in U (cooldown-shadow artifacts): {len(setL - setU)}")

# survivors needing minute bars (union), with re-derived coverage
union = {(a["d"], a["t"]) for a in res["L"]["replayable"]} | {(a["d"], a["t"]) for a in res["U"]["replayable"]}
have, missing = [], []
for d, t in sorted(union):
    c = cov.get((d, t))
    if c and c[0] == 1 and c[1] > 0: have.append((d, t))
    else: missing.append((d, t))
print(f"replay union: {len(union)}  with ORB+entry bars: {len(have)}  missing bars: {len(missing)}")
with open(f"{TMP}/bt_survivors.psv", "w") as fh:
    for d, t in sorted(union):
        fh.write(f"{d}|{t}\n")
with open(f"{TMP}/bt_admission_result.json", "w") as fh:
    json.dump({run: {"kills": dict(r["kills"]), "floor_pass": r["floor_pass"],
                     "cooldown_gap15": r["cooldown_gap15"],
                     "admitted": [{**a, "d": a["d"].isoformat()} for a in r["admitted"]],
                     "replayable": [{**a, "d": a["d"].isoformat()} for a in r["replayable"]]}
               for run, r in res.items()}, fh, default=str)
print("wrote bt_survivors.psv + bt_admission_result.json")
