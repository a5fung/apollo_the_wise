#!/usr/bin/env python3
"""#482 BLIND RECOUNT — written from PREREG.md's pre-registration section ONLY (above '## RESULT').

No code shared with read_482.py. Reads the read-only prod captures in ../data/*.csv (taken 2026-11-06;
never re-captured). R_cap is the prereg's own definition, book_geometry_arms.capped_dollar_r(row):
re-implemented here AND asserted equal to the prod import on every scored row.

Where the prereg's words admit more than one reading, every admissible reading is computed side by
side (the READINGS block), so a mismatch with read_482.out can be traced to a reading, not a bug.

Run: python3 scripts/probes/_482_read_1106/verify/recount.py > scripts/probes/_482_read_1106/verify/recount.out
"""
from __future__ import annotations

import csv
import math
import statistics
import sys
from datetime import date, datetime
from pathlib import Path
from zoneinfo import ZoneInfo

HERE = Path(__file__).resolve().parent
DATA = HERE.parent / "data"
REPO = HERE.parents[3]
sys.path.insert(0, str(REPO))
from agents.market_intelligence.book_geometry_arms import capped_dollar_r as prod_capped_dollar_r  # noqa: E402

_ET = ZoneInfo("America/New_York")
ERAS = ("C", "D", "E")
CONTROLS = ("live_actual", "live_replay")
STOP_ARMS = ("stop_orb_low", "stop_adr_050", "stop_adr_075", "stop_orb_3r", "stop_low_of_day")
ENTRY_BOOK_ARMS = ("entry_first_hour_bar", "book_first_hour_low_of_day")
HARVEST_ARMS = ("harvest_no_breakeven", "harvest_trail_only", "harvest_t3", "harvest_legacy_2r")
TRAIL_ARMS = ("trail_pivot_swing", "trail_character_ma")
LABELLED_ARMS = STOP_ARMS + ENTRY_BOOK_ARMS + HARVEST_ARMS + TRAIL_ARMS
# follows-live arms (lfc.ARMS follows_live_rule True + book_geometry_arms.BOOK_ARMS)
FOLLOWS_LIVE = {"live_actual", "live_replay", "stop_orb_low", "stop_adr_050", "stop_adr_075", "stop_orb_3r",
                "trail_pivot_swing", "trail_character_ma", "entry_first_hour_bar", "stop_low_of_day",
                "book_first_hour_low_of_day"}
TIE = 0.05
FIDELITY = 0.25


def f(x):
    if x is None or x == "":
        return None
    try:
        v = float(x)
    except ValueError:
        return None
    return None if math.isnan(v) else v


def read(name):
    with open(DATA / name, newline="") as fh:
        return list(csv.DictReader(fh))


# ── independent R_cap (the prereg's capped_dollar_r, from its docstring + formula) ──
REGIME_MULT = {"Bull": 1.00, "Choppy": 0.75, "Correcting": 0.50, "Crisis": 0.25}


def frac_capped(row):
    fill, stop, trig = f(row["entry_price"]), f(row["stop_price"]), f(row["orb_high"])
    fd = date.fromisoformat(row["fill_day"][:10])
    rp = 0.02 if fd >= date(2026, 10, 3) else 0.01
    mult = REGIME_MULT.get(row["regime"] or None, 0.25)
    if fill is None or stop is None or trig is None or trig <= 0:
        return None
    if fill - stop <= 0 or trig - stop <= 0:
        return None
    return min(mult * (fill - stop) / (trig - stop), 0.20 * (fill - stop) / (trig * rp))


def r_cap(row, r):
    fr = frac_capped(row)
    return None if (fr is None or r is None) else r * fr


# ── load ──
live = [r for r in read("live_all.csv")]
arms = read("lfc_arms.csv")
by_fill = {}
for a in arms:
    by_fill.setdefault(int(a["trade_id"]), {})[a["arm"]] = a

out = []
P = out.append


def hdr(t):
    P("")
    P("=" * 100)
    P(t)
    P("=" * 100)


# ── POPULATION ──
hdr("POPULATION (prereg §Population)")
cohort = [r for r in live if r["status"] == "closed" and r["account_mode"] == "live"
          and r["signal_type"] == "magna53" and r["fill_day_et"] >= "2026-08-16"]
P(f"captured live MAGNA53 rows filled >= 2026-08-16 ET: {len(live)}; status closed: {len(cohort)} (expected 20)")
nonclosed = [r for r in live if r["status"] != "closed"]
P(f"not closed (excluded from cohort): {[(r['id'], r['ticker'], r['status']) for r in nonclosed]}")


def own_era(r):
    if (r["exit_rule"] or "") == "depth":
        return "E"
    if r["alert_date"] >= "2026-09-06":
        return "D"
    return "C"


era_of = {}
stop = False
for r in cohort:
    tid = int(r["id"])
    e = own_era(r)
    era_of[tid] = e
    rec = {a["exit_era"] for a in by_fill.get(tid, {}).values()}
    if rec != {f"era_{e.lower()}"}:
        P(f"  ERA MISMATCH trade {tid} {r['ticker']}: own={e} recorder={rec}  -> READ STOPS")
        stop = True
P(f"own-row era == recorder exit_era on every trade: {not stop}")
attr = [(r["id"], r["ticker"], r["pnl_attribution"]) for r in cohort if (r["pnl_attribution"] or "").strip()]
P(f"excluded, non-NULL pnl_attribution: {attr or 'none'}")
att2 = [(r["id"], r["ticker"]) for r in cohort if r["entry_attempt"] == "2"]
P(f"kept + flagged, entry_attempt=2: {att2 or 'none'}")
no_rows = [int(r["id"]) for r in cohort if int(r["id"]) not in by_fill]
P(f"cohort fills with no recorder rows at all: {no_rows or 'none'}")
for e in ERAS:
    ids = [r for r in cohort if era_of[int(r["id"])] == e]
    P(f"era {e}: {len(ids)} fills  " + ", ".join(f"{r['ticker']}({r['id']})" for r in ids))
    mix = {}
    for r in ids:
        ae = by_fill[int(r["id"])]["live_actual"]["admission_era"]
        mix[ae] = mix.get(ae, 0) + 1
    for k, v in mix.items():
        P(f"     admission_era {k}: {v}")

# live_actual stop sanity
bad = [(t, d["live_actual"]["ticker"]) for t, d in by_fill.items()
       if f(d["live_actual"]["stop_price"]) != f(d["live_actual"]["live_stop"])]
P(f"sanity: live_actual stop_price == live_stop on every fill: {not bad} {bad or ''}")

# ── R_cap parity vs prod ──
hdr("R_cap PARITY: independent re-implementation vs prod book_geometry_arms.capped_dollar_r")
nchk, worst = 0, 0.0
for t, d in by_fill.items():
    for a in d.values():
        if a["outcome"] != "settled":
            continue
        mine = r_cap(a, f(a["realized_r"]))
        prod = prod_capped_dollar_r(dict(a))
        if mine is None or prod is None:
            assert mine is None and prod is None, (t, a["arm"], mine, prod)
            continue
        nchk += 1
        worst = max(worst, abs(mine - prod))
        stored = f(a["realized_r_capped"])
        if stored is not None and abs(stored - prod) > 1e-9:
            P(f"  stored realized_r_capped differs from capped_dollar_r: {t} {a['arm']} {stored} vs {prod}")
assert worst < 1e-9, worst
P(f"settled rows checked: {nchk}; max |mine - prod| = {worst:.2e}  -> identical")

# ── FIDELITY (R_own primary; R_cap shown for the reading check) ──
hdr("FIDELITY (both controls settled AND |live_replay R - live_actual R| <= 0.25R)")
P(f"{'trade':>6} {'tkr':6} {'era':3} {'act_R':>8} {'rep_R':>8} {'|dR|':>7} {'pass':5} {'act_Rcap':>9} {'rep_Rcap':>9} {'|dRcap|':>8} {'pass_cap':8}")
fid = {}
fid_cap = {}
for r in cohort:
    t = int(r["id"])
    d = by_fill[t]
    la, lr = d.get("live_actual"), d.get("live_replay")
    ok = la is not None and lr is not None and la["outcome"] == "settled" and lr["outcome"] == "settled"
    ra, rr = f(la["realized_r"]), f(lr["realized_r"])
    ca, cr = r_cap(la, ra), r_cap(lr, rr)
    fid[t] = ok and abs(rr - ra) <= FIDELITY
    fid_cap[t] = ok and abs(cr - ca) <= FIDELITY
    P(f"{t:>6} {r['ticker']:6} {era_of[t]:3} {ra:8.3f} {rr:8.3f} {abs(rr - ra):7.3f} {str(fid[t]):5} {ca:9.3f} {cr:9.3f} {abs(cr - ca):8.3f} {str(fid_cap[t]):8}")
for e in ERAS:
    fails = [(t, by_fill[t]["live_actual"]["ticker"]) for t in era_of if era_of[t] == e and not fid[t]]
    fails_c = [(t, by_fill[t]["live_actual"]["ticker"]) for t in era_of if era_of[t] == e and not fid_cap[t]]
    P(f"era {e}: fidelity FAILS (R_own reading) {fails}  | (R_cap reading) {fails_c}")


# ── per-arm per-era scoring ──
def classify(arm_row, reading_noentry, marks):
    """-> (kind, R_own, R_cap, pct, adr). kind in settled/no_entry/horizon/excluded:<why>"""
    if arm_row is None:
        return "excluded:missing", None, None, None, None
    o = arm_row["outcome"]
    fr = arm_row["final_reason"] or ""
    if o == "settled":
        r = f(arm_row["realized_r"])
        return "settled", r, r_cap(arm_row, r), f(arm_row["realized_pct"]), f(arm_row["pnl_adr"])
    if o == "horizon":
        if not marks:
            return "excluded:horizon", None, None, None, None
        m = f(arm_row["mark_r"])
        return "horizon", m, r_cap(arm_row, m), None, None
    if o == "unscoreable" and fr.startswith("no_entry:"):
        is_book = (arm_row["arm"] in ENTRY_BOOK_ARMS) if reading_noentry == "both_hour_arms" else (arm_row["arm_kind"] == "book")
        if is_book:
            return "no_entry", None, 0.0, 0.0, None
        return "excluded:unscoreable", None, None, None, None
    if o == "abstain":
        return "excluded:abstain", None, None, None, None
    return f"excluded:{o}", None, None, None, None


def med(xs):
    return statistics.median(xs) if xs else None


def bwt(ds):
    return (sum(1 for x in ds if x > TIE), sum(1 for x in ds if x < -TIE), sum(1 for x in ds if abs(x) <= TIE))


def sgn(x):
    return 0 if x is None or x == 0 else (1 if x > 0 else -1)


def score(arm, era, rd):
    """rd = reading dict: noentry, nbasis ('cap'|'own'), engine ('paired'|'all_settled'), fid ('own'|'cap'), marks."""
    fidmap = fid if rd["fid"] == "own" else fid_cap
    ex = {}
    rows = []  # paired fills (R_cap basis)
    eng = []
    for t in sorted(t for t in era_of if era_of[t] == era):
        d = by_fill[t]
        la, lr, ar = d["live_actual"], d["live_replay"], d.get(arm)
        kind, ro, rc, pc, ad = classify(ar, rd["noentry"], rd["marks"])
        lk, lro, lrc, lpc, lad = classify(la, rd["noentry"], rd["marks"])
        rk, rro, rrc, _, _ = classify(lr, rd["noentry"], rd["marks"])
        # engine check: arm and live_replay both settled
        if kind == "settled" and rc is None:  # invalid sizing frame (trigger at/below the arm's stop)
            ex["rcap_undefined_invalid_frame"] = ex.get("rcap_undefined_invalid_frame", 0) + 1
            if rd["badframe"] == "zero":
                rc = 0.0
            elif rd["badframe"] == "drop_fill":
                kind = "excluded:rcap_undefined"
        both_settled = ar is not None and ar["outcome"] == "settled" and lr["outcome"] == "settled"
        if both_settled and rc is not None and (rd["engine"] == "all_settled" or (fidmap[t] and la["outcome"] == "settled")):
            eng.append(rc - rrc)
        if la["outcome"] != "settled":
            ex["live_not_settled"] = ex.get("live_not_settled", 0) + 1
            continue
        if not fidmap[t]:
            ex["fidelity_fail"] = ex.get("fidelity_fail", 0) + 1
            continue
        if kind.startswith("excluded"):
            ex[kind] = ex.get(kind, 0) + 1
            continue
        if kind == "no_entry":
            ex["no_entry_scored_0"] = ex.get("no_entry_scored_0", 0) + 1
        rows.append(dict(t=t, tkr=la["ticker"], kind=kind, ro=ro, rc=rc, pc=pc, ad=ad, lro=lro, lrc=lrc, lpc=lpc, lad=lad))
    own = [x for x in rows if x["ro"] is not None]
    capr = [x for x in rows if x["rc"] is not None]
    n_cap, n_own = len(capr), len(own)
    dcap = [x["rc"] - x["lrc"] for x in capr]
    down = [x["ro"] - x["lro"] for x in own]
    dpct = [x["pc"] - x["lpc"] for x in rows if x["pc"] is not None and x["lpc"] is not None]
    dadr = [x["ad"] - x["lad"] for x in own if x["ad"] is not None and x["lad"] is not None]
    res = dict(
        n_cap=n_cap, n_own=n_own, ex=ex,
        a2=sum(1 for x in own if x["ro"] >= 2), a4=sum(1 for x in own if x["ro"] >= 4),
        l2=sum(1 for x in own if x["lro"] >= 2), l4=sum(1 for x in own if x["lro"] >= 4),
        amax=max((x["ro"] for x in own), default=None), lmax=max((x["lro"] for x in own), default=None),
        a15=sum(1 for x in own if x["ro"] <= -1.5), l15=sum(1 for x in own if x["lro"] <= -1.5),
        cap_sum=sum(dcap), cap_med=med(dcap), cap_bwt=bwt(dcap),
        cap_db=(sum(dcap) - max(dcap)) if dcap else None,
        own_sum=sum(down), own_med=med(down), own_bwt=bwt(down),
        own_db=(sum(down) - max(down)) if down else None,
        tailclip=sum(1 for x in capr if x["lro"] >= 2 and x["rc"] < x["lrc"] - 0.5),
        tailclip_base=sum(1 for x in capr if x["lro"] >= 2),
        rescue=sum(1 for x in own if x["lro"] <= -0.9 and x["ro"] > 0),
        rescue_base=sum(1 for x in own if x["lro"] <= -0.9),
        eng_sum=sum(eng) if eng else None, eng_n=len(eng),
        pct_sum=sum(dpct) if dpct else None, pct_med=med(dpct),
        adr_sum=sum(dadr) if dadr else None, adr_med=med(dadr),
        rows=rows,
    )
    res["eng_agree"] = res["eng_sum"] is not None and sgn(res["eng_sum"]) == sgn(res["cap_sum"])
    n_read = n_cap if rd["nbasis"] == "cap" else n_own
    res["readable"] = n_read >= 3
    res["won"] = (n_cap > 0 and res["cap_sum"] > 0 and n_own > 0 and res["own_sum"] > 0
                  and res["cap_db"] is not None and res["cap_db"] > 0 and res["eng_agree"]
                  and res["tailclip"] == 0 and res["a4"] >= res["l4"])
    res["won_why"] = [k for k, ok in (("Rcap>0", n_cap > 0 and res["cap_sum"] > 0),
                                      ("Rown>0", n_own > 0 and res["own_sum"] > 0),
                                      ("dropbest>0", res["cap_db"] is not None and res["cap_db"] > 0),
                                      ("engine_sign", res["eng_agree"]),
                                      ("tailclip=0", res["tailclip"] == 0),
                                      ("4R>=live", res["a4"] >= res["l4"])) if not ok]
    return res


def label(per_era, precedence="unreadable_first"):
    readable = [e for e in ERAS if per_era[e]["readable"]]
    not_won = [e for e in readable if not per_era[e]["won"]]
    if precedence == "unreadable_first":
        if len(readable) < 2:
            return "UNREADABLE"
        if not_won:
            return "NOT A CANDIDATE"
    else:
        if not_won:
            return "NOT A CANDIDATE"
        if len(readable) < 2:
            return "UNREADABLE"
    if "E" not in readable:
        return "WATCH-LIST, pending era E"
    return "WATCH-LIST"


PRIMARY = dict(noentry="both_hour_arms", nbasis="cap", engine="paired", fid="own", marks=False, badframe="skip_cap")
READINGS = {
    "PRIMARY": PRIMARY,
    "a:noentry=arm_kind_book_only": {**PRIMARY, "noentry": "arm_kind_book"},
    "b:readable_n=R_own_n": {**PRIMARY, "nbasis": "own"},
    "c:engine=all_era_both_settled": {**PRIMARY, "engine": "all_settled"},
    "f:fidelity_in_R_cap": {**PRIMARY, "fid": "cap"},
    "h:marks_counted": {**PRIMARY, "marks": True},
    "i:invalid_frame_Rcap=0": {**PRIMARY, "badframe": "zero"},
    "j:invalid_frame_drop_fill": {**PRIMARY, "badframe": "drop_fill"},
}

n_horizon = sum(1 for a in arms if a["outcome"] == "horizon")
hdr("HORIZON")
P(f"rows with outcome 'horizon' in the capture: {n_horizon}. The two label passes (marks excluded / marks at mark_r)"
  " are identical by construction; UNRESOLVED (horizon) cannot occur in this read." if n_horizon == 0 else
  f"horizon rows: {n_horizon}")

hdr("TIER 1 — PRIMARY READING, per arm per era (paired = live_actual settled + fidelity pass + arm scoreable)")
P("PRIMARY reading: no_entry -> 0 on BOTH hour arms (BOOK_ARMS vocabulary); readable n on R_cap-paired fills;")
P("engine over paired fills where arm+live_replay settled; fidelity in R_own; marks excluded (none exist);")
P("a settled arm row whose sizing frame is invalid (capped_dollar_r None: trigger at/below the arm stop) is left out")
P("of the R_cap sums only (n_cap < n_own) and kept in R_own.")
P("Tails in R_own on the arm's R_own-paired fills, live counted on the same fills. dropbest = sum - max(delta).")
P("")
results = {}
for rname, rd in READINGS.items():
    results[rname] = {arm: {e: score(arm, e, rd) for e in ERAS} for arm in LABELLED_ARMS + ("live_replay",)}

prim = results["PRIMARY"]
for arm in LABELLED_ARMS + ("live_replay",):
    P(f"--- {arm}")
    for e in ERAS:
        r = prim[arm][e]
        ex = ", ".join(f"{k}={v}" for k, v in sorted(r["ex"].items())) or "-"
        P(f"  era {e}: n_cap={r['n_cap']} n_own={r['n_own']}  excluded/flagged: {ex}")
        if r["n_cap"] == 0:
            continue
        fm = lambda x: "  n/a" if x is None else f"{x:+.3f}"
        P(f"     tail R_own  arm >=2R {r['a2']} >=4R {r['a4']} max {fm(r['amax'])} <=-1.5R {r['a15']}"
          f" | live >=2R {r['l2']} >=4R {r['l4']} max {fm(r['lmax'])} <=-1.5R {r['l15']}")
        P(f"     dR_cap  sum {fm(r['cap_sum'])} med {fm(r['cap_med'])} b/w/t {r['cap_bwt']} dropbest {fm(r['cap_db'])}")
        P(f"     dR_own  sum {fm(r['own_sum'])} med {fm(r['own_med'])} b/w/t {r['own_bwt']} dropbest {fm(r['own_db'])}")
        P(f"     tailclip {r['tailclip']}/{r['tailclip_base']}  rescues {r['rescue']}/{r['rescue_base']}"
          f"  engine sum(arm-replay) R_cap {fm(r['eng_sum'])} on n={r['eng_n']} sign_agrees={r['eng_agree']}")
        P(f"     pct dsum {fm(r['pct_sum'])} med {fm(r['pct_med'])} | adr dsum {fm(r['adr_sum'])} med {fm(r['adr_med'])}")
        P(f"     readable={r['readable']} WON={r['won']}" + ("" if r["won"] else f"  fails: {r['won_why']}"))
    P(f"  LABEL: {label(prim[arm])}")

# fills detail compact (separate loop so the line above stays readable)
hdr("TIER 1 — paired-fill detail (PRIMARY): arm R_own / R_cap vs live_actual R_own / R_cap")
for arm in LABELLED_ARMS:
    for e in ERAS:
        r = prim[arm][e]
        if not r["rows"]:
            continue
        P(f"{arm:28} {e}: " + "; ".join(
            f"{x['tkr']} {'NE' if x['kind'] == 'no_entry' else format(x['ro'], '+.2f')}/{'undef' if x['rc'] is None else format(x['rc'], '+.2f')}"
            f" v {x['lro']:+.2f}/{x['lrc']:+.2f}" for x in r["rows"]))

hdr("LABELS ACROSS READINGS (a label that changes across admissible readings is flagged FLIP)")
names = list(READINGS) + ["g:precedence=not_won_first"]
P(f"{'arm':28} " + " | ".join(f"{n[:22]:22}" for n in names))
flips = []
for arm in LABELLED_ARMS:
    labs = [label(results[n][arm]) for n in READINGS] + [label(prim[arm], "not_won_first")]
    flag = "" if len(set(labs)) == 1 else "  FLIP"
    if flag:
        flips.append((arm, dict(zip(names, labs))))
    P(f"{arm:28} " + " | ".join(f"{x[:22]:22}" for x in labs) + flag)
P("")
P("per-era WON / readable under each reading (R=readable, W=won):")
for arm in LABELLED_ARMS:
    cells = []
    for n in READINGS:
        cells.append(n.split(":")[0] + "[" + " ".join(
            f"{e}:{'R' if results[n][arm][e]['readable'] else '-'}{'W' if results[n][arm][e]['won'] else '-'}"
            f"{results[n][arm][e]['n_cap'] if READINGS[n]['nbasis'] == 'cap' else results[n][arm][e]['n_own']}"
            for e in ERAS) + "]")
    P(f"  {arm:28} " + "  ".join(cells))

hdr("DISAPPOINTS per era (live_actual R_cap sum < 0 AND no fill >= +4R)")
for e in ERAS:
    for basis in ("all era fills", "fidelity-passing fills"):
        ts = [t for t in era_of if era_of[t] == e and (basis == "all era fills" or fid[t])]
        la = [by_fill[t]["live_actual"] for t in ts]
        rc = sum(r_cap(a, f(a["realized_r"])) for a in la)
        n4 = sum(1 for a in la if f(a["realized_r"]) >= 4)
        P(f"era {e} [{basis:22}] n={len(ts)} live R_cap sum {rc:+.3f}  fills >=+4R {n4}  -> DISAPPOINTS={rc < 0 and n4 == 0}")

hdr("RECORDER CHECKS (reported; do not stop the read)")
dis = []
for t, d in sorted(by_fill.items()):
    e = era_of[t]
    want = (2.0, None) if e == "C" else (8.0, 3.0)
    for a in d.values():
        if a["arm"] not in FOLLOWS_LIVE:
            continue
        got = (f(a["target_r"]), f(a["breakeven_arm_r"]))
        if got != want:
            dis.append((t, a["ticker"], e, a["arm"], got, fid[t]))
grp = {}
for t, tk, e, arm, got, fp in dis:
    grp.setdefault((t, tk, e, got, fp), []).append(arm)
P(f"follows-live target_r/breakeven_arm_r disagreements (want C 2/NULL, D/E 8/3): {len(dis)} rows")
for (t, tk, e, got, fp), al in grp.items():
    P(f"  {tk}({t}) era {e} got {got} on {len(al)} arms; fidelity pass={fp} -> {'stays' if fp else 'already out on fidelity'}")
eq = []
for t in era_of:
    if era_of[t] != "C":
        continue
    a, b = by_fill[t]["harvest_legacy_2r"], by_fill[t]["live_replay"]
    eq.append((by_fill[t]["live_actual"]["ticker"], f(a["realized_r"]), f(b["realized_r"]),
               abs(f(a["realized_r"]) - f(b["realized_r"])) < 1e-9))
P(f"era C harvest_legacy_2r == live_replay: {sum(x[3] for x in eq)}/{len(eq)}  "
  + "; ".join(f"{x[0]} {x[1]:+.3f} v {x[2]:+.3f}" for x in eq if not x[3]))
tot = same = 0
for r in cohort:
    t = int(r["id"])
    m = datetime.fromisoformat(r["filled_at"].replace("+00", "+00:00")).astimezone(_ET)
    if (m.hour, m.minute) != (9, 31):
        continue
    a, b = by_fill[t]["stop_low_of_day"], by_fill[t]["stop_orb_low"]
    tot += 1
    if a["outcome"] == b["outcome"] and f(a["stop_price"]) == f(b["stop_price"]) and f(a["realized_r"]) == f(b["realized_r"]):
        same += 1
P(f"stop_low_of_day identical to stop_orb_low on 09:31 ET fills: {same}/{tot}")
allsame = sum(1 for t in by_fill if f(by_fill[t]["stop_low_of_day"]["realized_r"]) == f(by_fill[t]["stop_orb_low"]["realized_r"]))
P(f"  (all fills, identical realized_r: {allsame}/{len(by_fill)})")
P("hour-bar arms (entry_first_hour_bar, book_first_hour_low_of_day) only see fills where the 1-minute ORB high filled (selection effect).")

hdr("FILL FACTS (descriptive, from fill_facts rows)")
for e in ERAS:
    ff = [by_fill[t]["fill_facts"] for t in era_of if era_of[t] == e]
    fv = [f(a["fill_vs_trigger_pct"]) for a in ff if f(a["fill_vs_trigger_pct"]) is not None]
    rr = [f(a["real_risk_vs_trigger_risk"]) for a in ff if f(a["real_risk_vs_trigger_risk"]) is not None]
    P(f"era {e}: fill_vs_trigger_pct median {med(fv):+.3f} max {max(fv):+.3f} count>+1% {sum(1 for x in fv if x > 1)}"
      f" | real_risk_vs_trigger_risk median {med(rr):.3f} max {max(rr):.3f}  (n={len(fv)})")

hdr("SUMMARY TABLE (PRIMARY): arm | era | n_cap n_own | arm>=2 >=4 <=-1.5 | live>=2 >=4 <=-1.5 | dRown sum | dRcap sum | WON")
for arm in LABELLED_ARMS + ("live_replay",):
    for e in ERAS:
        r = prim[arm][e]
        if r["n_cap"] == 0:
            P(f"{arm:28} {e} | 0 0 | - | - | - | - | -")
            continue
        P(f"{arm:28} {e} | {r['n_cap']:2} {r['n_own']:2} | {r['a2']} {r['a4']} {r['a15']} | {r['l2']} {r['l4']} {r['l15']}"
          f" | {r['own_sum']:+8.3f} | {r['cap_sum']:+8.3f} | {'W' if r['won'] else '-'}{'R' if r['readable'] else 'u'}")
    P(f"{'':28}   LABEL {label(prim[arm])}" if arm != "live_replay" else "")

hdr("FLIPS")
P(f"{len(flips)} arm(s) whose label changes across admissible readings:")
for arm, d in flips:
    P(f"  {arm}: " + "; ".join(f"{k}={v}" for k, v in d.items()))

print("\n".join(out))

# machine-readable copy for the comparison step (written AFTER recount.out's numbers were fixed)
import json  # noqa: E402
_dump = {rn: {arm: {e: {k: v for k, v in r.items() if k != "rows"} for e, r in per.items()}
              for arm, per in res.items()} for rn, res in results.items()}
_dump["_labels"] = {rn: {arm: label(results[rn][arm]) for arm in LABELLED_ARMS} for rn in READINGS}
_dump["_labels"]["g:precedence=not_won_first"] = {arm: label(prim[arm], "not_won_first") for arm in LABELLED_ARMS}
(HERE / "recount.json").write_text(json.dumps(_dump, indent=1, default=list))
