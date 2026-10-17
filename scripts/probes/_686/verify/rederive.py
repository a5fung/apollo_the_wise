#!/usr/bin/env python3
"""#686 independent verifier — re-derive the frozen read's numbers from the REGISTRATION TEXT
(docs/analysis/686_preregistration_2026-10-04.md) and the pulled data in ../data/, WITHOUT importing
preregistered_read.py or any #684 module. Read-only on everything outside verify/.

Definitions used (registration section in brackets; production code read only where the
registration cites it as the definition):
  population  [§2]  pop.tsv rows, one per (ticker, scan_date), block 2026-09-04..09-25
  ADR$        [§3]  mean((h-l)/c) over the 20 sessions strictly before the gap day x gap-day close
                    (delayed_entry_shadow.compute_ep_adr_dollar)
  frame A     [§3]  (max HIGH over sessions +1..+15 - gap-day CLOSE) / ADR$; sessions = XNYS
                    calendar (SPY dates in daily.tsv.gz cross-checked against exchange_calendars)
  runner      [§4]  >= 5 ADR (also >= 8)
  frame B     [§3]  HIGH alert row -> first HIGH alert < 09:45 -> submit = max(first HIGH, 09:31)
                    -> rt gap: open of submit-minute bar vs prior daily close < 9% (missing bar passes)
                    -> ORB = 09:30 bar; range<=0 or > 1.5 x ATR14-prior (simple mean of last 14 TRs,
                       prior bars within 40 calendar days, >=10 rows else skipped:
                       alert_rank_shadow.compute_atr14_prior; filters.validate_orb_entry)
                    -> stop = 2L-H; price P = open of first bar at/after submit
                    -> P > H: limit = round(P*1.002,2); limit-stop > 1.5*(H-stop) -> chase skip,
                       else fill at P
                    -> else stop-limit at H, limit = round(max(H*1.005, H+0.02),2), walk to 09:59
  permutation [§6]  runner labels shuffled within ISO week; p(declared)=share diff>=obs,
                    p(reverse)=share diff<=obs. OWN generator (numpy default_rng, seed 686) — the
                    registration fixes the seed but not the RNG library / shuffle call / consumption
                    order, so the read's exact draws cannot be reproduced from the text. Also an
                    EXACT p by enumerating the within-week permutation distribution.
"""
import collections
import csv
import gzip
import itertools
import math
import os
import sys
from datetime import date, timedelta

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.join(HERE, "..", "data")
OUT = os.path.join(HERE, "..", "out")
RS_SHADOW = os.path.join(HERE, "..", "..", "_rank_shadow", "verify_rank_shadow_2026-10-16.out")

BLOCK_LO, BLOCK_HI = date(2026, 9, 4), date(2026, 9, 25)
D = lambda s: date.fromisoformat(s)


def read_psv(name):
    rows = []
    with open(os.path.join(DATA, name)) as f:
        hdr = f.readline().rstrip("\n").split("|")
        for line in f:
            line = line.rstrip("\n")
            if not line or (line.startswith("(") and line.endswith("rows)")) or line.endswith("row)"):
                continue
            rows.append(dict(zip(hdr, line.split("|"))))
    return rows


def fnum(x):
    try:
        return float(x)
    except (TypeError, ValueError):
        return None


lines = []
def P(*a):
    s = " ".join(str(x) for x in a)
    print(s)
    lines.append(s)


# ---------------------------------------------------------------- load
pop = read_psv("pop.tsv")
trades = read_psv("trades.tsv")
daily = collections.defaultdict(list)
with gzip.open(os.path.join(DATA, "daily.tsv.gz"), "rt") as f:
    hdr = f.readline().rstrip("\n").split("|")
    for line in f:
        line = line.rstrip("\n")
        if not line or line.startswith("("):
            continue
        r = dict(zip(hdr, line.split("|")))
        daily[r["ticker"]].append((D(r["trade_date"]), float(r["open_price"]), float(r["high_price"]),
                                   float(r["low_price"]), float(r["close"]), float(r["volume"] or 0)))
for t in daily:
    daily[t].sort()
bars = collections.defaultdict(list)  # (ticker, scan_date) -> [(hhmm, o, h, l)]
with open(os.path.join(DATA, "live_entry_bars.tsv")) as f:
    hdr = f.readline().rstrip("\n").split("|")
    for line in f:
        line = line.rstrip("\n")
        if not line or line.startswith("("):
            continue
        r = dict(zip(hdr, line.split("|")))
        bars[(r["ticker"], r["scan_date"])].append((r["hhmm"], float(r["open"]), float(r["high"]), float(r["low"])))
for k in bars:
    bars[k].sort()

read_out = {}
with open(os.path.join(OUT, "686_outcomes.tsv")) as f:
    for r in csv.DictReader(f, delimiter="\t"):
        read_out[(r["ticker"], r["scan_date"])] = r
feat = {}
with open(os.path.join(DATA, "features.tsv")) as f:
    for r in csv.DictReader(f, delimiter="\t"):
        feat[(r["ticker"], r["scan_date"])] = r

# ---------------------------------------------------------------- (1) population
P("=" * 100)
P("(1) POPULATION")
keys = [(r["ticker"], r["scan_date"]) for r in pop]
P(f"  rows {len(pop)}; unique (ticker, scan_date) {len(set(keys))}")
dates = collections.Counter(r["scan_date"] for r in pop)
P(f"  scan dates {len(dates)}: {dict(sorted(dates.items()))}")
out_of_block = [k for k in keys if not (BLOCK_LO <= D(k[1]) <= BLOCK_HI)]
P(f"  rows outside 09-04..09-25: {out_of_block}")
null_score = [k for r, k in zip(pop, keys) if r["ep_score"] == ""]
P(f"  rows with NULL ep_score: {null_score}")
spy_dates = [d for d, *_ in daily["SPY"]]
cal_block = [d for d in spy_dates if BLOCK_LO <= d <= BLOCK_HI]
try:
    import exchange_calendars as xc
    xnys = xc.get_calendar("XNYS")
    xs = [s.date() for s in xnys.sessions_in_range("2026-09-04", "2026-10-16")]
    P(f"  XNYS sessions 09-04..10-16: {len(xs)}; SPY daily dates same span: "
      f"{len([d for d in spy_dates if BLOCK_LO <= d <= date(2026,10,16)])}; identical: "
      f"{xs == [d for d in spy_dates if BLOCK_LO <= d <= date(2026,10,16)]}")
except Exception as e:  # pragma: no cover
    P(f"  exchange_calendars unavailable ({e}); SPY dates used as the calendar")
missing_sessions = [d.isoformat() for d in cal_block if d.isoformat() not in dates]
P(f"  block sessions (SPY calendar) {len(cal_block)}; sessions with ZERO population rows: {missing_sessions}")
set_keys = set(keys)
# in-block prior scored dates must themselves be population rows
prior = {(r["ticker"], r["scan_date"]): r for r in read_psv("prior.tsv")}
inblock_prev = [(t, s, prior[(t, s)]["prev_scored_date"]) for (t, s) in keys
                if prior[(t, s)]["prev_scored_date"] and BLOCK_LO <= D(prior[(t, s)]["prev_scored_date"])]
P(f"  in-block prev_scored_date references: {inblock_prev}; all present in pop: "
  f"{all((t, p) in set_keys for t, s, p in inblock_prev)}; any pointing at 09-10: "
  f"{any(p == '2026-09-10' for _, _, p in inblock_prev)}")
# independent alert list: mi_alert_rank_shadow capture (one row per live alert) from _rank_shadow
rs_alerts = []
if os.path.exists(RS_SHADOW):
    with open(RS_SHADOW) as f:
        hdr = f.readline().rstrip("\n").split("|")
        for line in f:
            p = line.rstrip("\n").split("|")
            if len(p) >= 5 and p[1][:4] == "2026" and BLOCK_LO <= D(p[1]) <= BLOCK_HI:
                rs_alerts.append((p[0], p[1], p[4], p[3]))
P(f"  independent alert list (_rank_shadow/verify_rank_shadow_2026-10-16.out, block dates): {len(rs_alerts)} alerts; "
  f"missing from pop: {[a for a in rs_alerts if (a[0], a[1]) not in set_keys]}")
P(f"    alerts there: {[a[0]+' '+a[1][5:]+' '+a[2] for a in rs_alerts]}")
alerted_pop = sorted(k for r, k in zip(pop, keys) if r["any_pass_tick"] == "t")
P(f"  pop rows with a scan PASS (alerted): {len(alerted_pop)}; same set as the alert list: "
  f"{set(alerted_pop) == set((a[0], a[1]) for a in rs_alerts)}")
P(f"  trades.tsv records {len(trades)}; all in pop: {all((t['ticker'], t['alert_date']) in set_keys for t in trades)}; "
  f"rank-shadow trade_filled=True: {[a[0] for a in rs_alerts if a[3] == 'True']}")
blockish = [(t["ticker"], t["alert_date"], t["status"], t["skip_reason"]) for t in trades if "block:" in t["skip_reason"]]
P(f"  records carrying a block:* reason: {blockish}")

# ---------------------------------------------------------------- per-row bar context
rows = []
problems = collections.defaultdict(list)
for r in pop:
    t, s = r["ticker"], r["scan_date"]
    sd = D(s)
    db = daily[t]
    pre = [b for b in db if b[0] < sd]
    g = [b for b in db if b[0] == sd]
    if not g:
        problems["no_gap_day_bar"].append((t, s))
        continue
    g = g[0]
    cal_fwd = [d for d in spy_dates if d > sd][:15]
    tick_dates = {b[0]: b for b in db}
    fwd = [tick_dates[d] for d in cal_fwd if d in tick_dates]
    if len(cal_fwd) < 15:
        problems["calendar_short"].append((t, s))
    if len(fwd) < 15:
        problems["censored_missing_calendar_sessions"].append((t, s, [d.isoformat() for d in cal_fwd if d not in tick_dates]))
    own_next15 = [b for b in db if b[0] > sd][:15]
    if [b[0] for b in own_next15] != cal_fwd:
        problems["own_next15_differs_from_calendar"].append((t, s))
    if len(pre) < 20:
        problems["lt20_prior"].append((t, s))
    w = pre[-20:]
    adr_frac = sum((h - l) / c for _, _, h, l, c, _ in w if c > 0) / len([1 for b in w if b[4] > 0])
    close0 = g[4]
    adr_d = adr_frac * close0
    mx = max(b[2] for b in fwd)
    run_a = (mx - close0) / adr_d
    prev_close_daily = pre[-1][4]
    rows.append(dict(t=t, s=s, sd=sd, r=r, pre=pre, g=g, fwd=fwd, adr_frac=adr_frac, adr_d=adr_d,
                     close0=close0, run_a=run_a, runner5=int(run_a >= 5), runner8=int(run_a >= 8),
                     prev_close_daily=prev_close_daily,
                     week="%d-W%02d" % sd.isocalendar()[:2]))

P("  bar-context problems: " + (str(dict(problems)) if problems else "none"))
P(f"  rows with 15 calendar forward sessions present: {sum(len(x['fwd']) == 15 for x in rows)} of {len(rows)}")

# split / adjustment consistency (frame B mixes intraday fills with daily forward highs)
P("  split/adjustment checks:")
bad = []
for x in rows:
    b = bars.get((x["t"], x["s"]))
    o930 = b[0][1] if b and b[0][0] == "09:30" else None
    rd = o930 / x["g"][1] if o930 else None
    pc = fnum(x["r"]["prev_close"])
    rp = pc / x["prev_close_daily"] if pc else None
    if (rd is not None and abs(rd - 1) > 0.03) or (rp is not None and abs(rp - 1) > 0.01):
        bad.append((x["t"], x["s"], round(rd, 4) if rd else None, round(rp, 4) if rp else None))
    # forward split: any adjacent forward daily close ratio wildly off
P(f"    rows with 09:30 intraday open vs daily open off >3% or scan prev_close vs daily prior close off >1%: {bad}")
day_hi_vs_intraday = []
for x in rows:
    b = bars.get((x["t"], x["s"]))
    if b:
        ih = max(h for _, _, h, _ in b)
        r_ = ih / x["g"][2]
        if abs(r_ - 1) > 0.02:
            day_hi_vs_intraday.append((x["t"], x["s"], round(r_, 4)))
P(f"    rows whose intraday day-high vs daily high differs >2%: {day_hi_vs_intraday}")

# ---------------------------------------------------------------- (2) frame A
P("=" * 100)
P("(2) FRAME A")
n5 = sum(x["runner5"] for x in rows); n8 = sum(x["runner8"] for x in rows)
al = [x for x in rows if x["r"]["any_pass_tick"] == "t"]
P(f"  n {len(rows)}; runners >=5 ADR {n5}; >=8 ADR {n8}; alerted n {len(al)} runners {sum(x['runner5'] for x in al)}; "
  f"not-alerted n {len(rows)-len(al)} runners {n5 - sum(x['runner5'] for x in al)}")
P(f"  runners: {[(x['t'], x['s'][5:], round(x['run_a'], 3)) for x in rows if x['runner5']]}")
maxdiff = 0; disagree = []
for x in rows:
    ro = read_out[(x["t"], x["s"])]
    d_ = abs(float(ro["run_xadr"]) - x["run_a"])
    maxdiff = max(maxdiff, d_)
    if int(ro["runner5"]) != x["runner5"]:
        disagree.append((x["t"], x["s"], ro["run_xadr"], x["run_a"]))
P(f"  vs read's 686_outcomes.tsv: max |run_xadr diff| {maxdiff:.4f} (read rounds to 3 dp); runner5 disagreements {disagree}")
near = [(x["t"], x["s"][5:], round(x["run_a"], 3)) for x in rows if 4.5 <= x["run_a"] < 5.5]
P(f"  rows within 0.5 ADR of the 5-ADR bar (fragility): {near}")
adr_cmp = max(abs(float(feat[(x['t'], x['s'])]['adr_dollar_ep']) - x['adr_d']) / x['adr_d'] for x in rows)
P(f"  ADR$ vs features.tsv adr_dollar_ep: max relative diff {adr_cmp:.2e}")

# ---------------------------------------------------------------- (3) frame B
P("=" * 100)
P("(3) FRAME B (today's order path, modelled from the registration §3 table)")


def hm(s):
    h, m = s.split(":")
    return int(h) * 60 + int(m)


def atr14_prior(x):
    lo = x["sd"] - timedelta(days=40)
    hlc = [(h, l, c) for d, o, h, l, c, v in x["pre"] if d >= lo]
    if len(hlc) < 10:
        return None
    trs = [max(hlc[i][0] - hlc[i][1], abs(hlc[i][0] - hlc[i - 1][2]), abs(hlc[i][1] - hlc[i - 1][2]))
           for i in range(1, len(hlc))]
    w = trs[-14:]
    return sum(w) / len(w)


def frame_b(x):
    r = x["r"]
    info = {}
    if r["any_high_alert"] != "t":
        return "not_high_never_ordered", info
    fh = r["first_high_alert_et"]
    info["first_high"] = fh
    if hm(fh) >= hm("09:45"):
        return "window_out_of_orb", info
    submit = max(hm(fh), hm("09:31"))
    b = bars.get((x["t"], x["s"]), [])
    bm = {hm(h): (o, hi, lo) for h, o, hi, lo in b}
    if hm("09:30") not in bm:
        return "unreadable_no_0930", info
    _, H, L = bm[hm("09:30")]
    info.update(H=H, L=L, submit="%02d:%02d" % divmod(submit, 60))
    # rt gap recheck: open of the submit-minute bar vs prior close; missing -> pass
    if submit in bm:
        g = (bm[submit][0] - x["prev_close_daily"]) / x["prev_close_daily"] * 100
        info["rt_gap"] = round(g, 2)
        if g < 9.0:
            return "gap_below_floor", info
    else:
        info["rt_gap"] = "missing->pass"
    atr = atr14_prior(x)
    info["atr14"] = round(atr, 4) if atr else None
    rng = H - L
    if rng <= 0:
        return "orb_invalid:zero_range", info
    if atr and atr > 0 and rng > 1.5 * atr:
        return "orb_invalid:stop_too_wide", info
    stop = 2 * L - H
    after = [m for m in sorted(bm) if m >= submit]
    if not after:
        return "unreadable_no_bar_after_submit", info
    Pz = bm[after[0]][0]
    info["P"] = Pz
    if Pz > H:
        lim = round(Pz * 1.002, 2)
        if lim - stop > 1.5 * (H - stop):
            info["chase_ratio"] = round((lim - stop) / (H - stop), 3)
            return "chase_cap_skip", info
        info.update(fill_min=after[0], fill_px=Pz, kind="market_or_skip_limit")
        return "filled", info
    lim = round(max(H * 1.005, H + 0.02), 2)
    info["limit"] = lim
    armed = False
    prev_m = None
    gaps = []
    for m in after:
        if m >= hm("10:00"):
            break
        if prev_m is not None and m - prev_m > 1:
            gaps.append(("%02d:%02d" % divmod(prev_m, 60), "%02d:%02d" % divmod(m, 60)))
        o, hi, lo = bm[m]
        if armed:
            if lo <= lim:
                info.update(fill_min=m, fill_px=lim, kind="stop_limit_pullback_to_limit", gaps=gaps)
                return "filled", info
        elif H <= o <= lim:
            info.update(fill_min=m, fill_px=o, kind="stop_limit_bracket_open", gaps=gaps)
            return "filled", info
        elif o < H and hi >= H:
            info.update(fill_min=m, fill_px=H, kind="stop_limit_bracket_at_H", gaps=gaps)
            return "filled", info
        elif o > lim:
            armed = True
        prev_m = m
    info["gaps"] = gaps
    return "no_entry", info


for x in rows:
    st, info = frame_b(x)
    x["b_status"], x["b_info"] = st, info
    x["orderable"] = int(st in ("filled", "no_entry", "chase_cap_skip"))
    x["runB"] = None; x["runnerB"] = 0
    if st == "filled":
        b = bars[(x["t"], x["s"])]
        day_hi = max(hi for h, o, hi, lo in b if hm(h) >= info["fill_min"])
        fwd_hi = max(bb[2] for bb in x["fwd"])
        x["runB"] = (max(day_hi, fwd_hi) - info["fill_px"]) / x["adr_d"]
        x["runnerB"] = int(x["runB"] >= 5)

c = collections.Counter(x["b_status"].split(":")[0] for x in rows)
P(f"  admission/status counts: {dict(c)}")
orderable = [x for x in rows if x["orderable"]]
P(f"  orderable {len(orderable)}: {[x['t']+' '+x['s'][5:] for x in orderable]}")
fills = [x for x in rows if x["b_status"] == "filled"]
P(f"  filled {len(fills)}; runners_B {sum(x['runnerB'] for x in rows)}")
for x in rows:
    if x["r"]["any_high_alert"] == "t":
        i = x["b_info"]
        P(f"    {x['t']:5} {x['s'][5:]} {x['b_status']:24} first_high {i.get('first_high')} submit {i.get('submit')} "
          f"H {i.get('H')} L {i.get('L')} rt_gap {i.get('rt_gap')} atr14 {i.get('atr14')} P {i.get('P')} "
          f"lim {i.get('limit')} chase {i.get('chase_ratio')} fill {i.get('fill_px')}@{('%02d:%02d' % divmod(i['fill_min'],60)) if 'fill_min' in i else ''} "
          f"{i.get('kind','')} runB {round(x['runB'],3) if x['runB'] is not None else ''} gaps {i.get('gaps','')}")
# compare to the read
mism_b = []
for x in rows:
    ro = read_out[(x["t"], x["s"])]
    rs = ro["orb_status"].split(":")[0]
    mine = x["b_status"].split(":")[0]
    if rs != mine or int(ro["filled"]) != int(x["b_status"] == "filled") or int(ro["runnerB5"]) != x["runnerB"]:
        mism_b.append((x["t"], x["s"], ro["orb_status"], x["b_status"]))
    if x["b_status"] == "filled":
        if abs(float(ro["entry_px"]) - x["b_info"]["fill_px"]) > 1e-6 or abs(float(ro["run_xadr_B"]) - x["runB"]) > 6e-4:
            mism_b.append((x["t"], x["s"], "fill/runB", ro["entry_px"], x["b_info"]["fill_px"], ro["run_xadr_B"], round(x["runB"], 4)))
P(f"  vs read's 686_outcomes.tsv: frame-B mismatches {mism_b}")
trec = {(t["ticker"], t["alert_date"]): t for t in trades}
P("  orderable x order record:")
for x in orderable:
    t = trec.get((x["t"], x["s"]))
    P(f"    {x['t']:5} {x['s'][5:]} model {x['b_status']:15} record {t['status'] if t else 'NONE':9} {t['skip_reason'] if t else ''}")
nonord_rec = [(k, v["status"], v["skip_reason"][:60]) for k, v in trec.items()
              if k not in {(x['t'], x['s']) for x in orderable}]
P(f"  records on rows the model does NOT find orderable: {nonord_rec}")

# ---------------------------------------------------------------- (4) never-bought split
P("=" * 100)
P("(4) FRAME-A RUNNERS TODAY'S PATH NEVER BUYS")
nb = [x for x in rows if x["runner5"] and x["b_status"] != "filled"]
P(f"  {len(nb)} of {n5}: {dict(collections.Counter(x['b_status'].split(':')[0] for x in nb))}")
P(f"  bought: {[x['t']+' '+x['s'][5:] for x in rows if x['runner5'] and x['b_status']=='filled']}")
P(f"  never bought: {[(x['t'], x['s'][5:], x['b_status'].split(':')[0], x['r']['any_pass_tick']) for x in nb]}")

# ---------------------------------------------------------------- features I recompute myself
CUTS = {
    "PRE_repeat_scored_90d": ("bool0", None, None),
    "PRE_prev_close": ("LOWER", 18.06, 66.6),
    "PRE_adr20_pct": ("HIGHER", 4.4901, 6.4167),
    "PRE_dollar_vol_20d": ("LOWER", 3.2458e7, 1.6391e8),
}
for x in rows:
    pr = prior[(x["t"], x["s"])]["prev_scored_date"]
    x["PRE_repeat_scored_90d"] = int(bool(pr) and (x["sd"] - D(pr)).days <= 90)
    x["PRE_prev_close"] = fnum(x["r"]["prev_close"])
    x["PRE_adr20_pct"] = x["adr_frac"] * 100
    w = x["pre"][-20:]
    x["PRE_dollar_vol_20d"] = sum(c * v for d, o, h, l, c, v in w) / len(w)
    # base range 20: (max close - min close over the 20 prior sessions) / prev close
    cl = [b[4] for b in x["pre"][-20:]]
    x["PRE_base_range20_pct"] = (max(cl) - min(cl)) / cl[-1] * 100
    x["CLOSE_range_xadr"] = (x["g"][2] - x["g"][3]) / (x["adr_frac"] * x["prev_close_daily"])  # features.tsv normalises by ADR x PREV close (adr_dollar_prev)
    x["CLOSE_range_xadr_epclose"] = (x["g"][2] - x["g"][3]) / x["adr_d"]
P("=" * 100)
P("FEATURE CROSS-CHECK vs the read's data/features.tsv (my values from raw bars):")
for col in ["PRE_repeat_scored_90d", "PRE_prev_close", "PRE_adr20_pct", "PRE_dollar_vol_20d",
            "PRE_base_range20_pct", "CLOSE_range_xadr"]:
    diffs = []
    for x in rows:
        fv = fnum(feat[(x["t"], x["s"])][col])
        if fv is None:
            diffs.append((x["t"], x["s"], "read NaN", x[col]))
        elif abs(fv - x[col]) > 1e-5 * max(1e-9, abs(fv)) + 1e-9:   # features.tsv is written at 6 significant digits
            diffs.append((x["t"], x["s"], fv, x[col]))
    P(f"  {col}: {'identical on all 75' if not diffs else diffs[:8]}")

# ---------------------------------------------------------------- permutation machinery
weeks = sorted(set(x["week"] for x in rows))


def diff_of(fav, lab):
    a = lab[fav]; b = lab[~fav]
    return a.mean() - b.mean()


def perm_p(fav, lab, wk, n_draws, rng):
    obs = diff_of(fav, lab)
    idx_by_w = [np.where(wk == w)[0] for w in np.unique(wk)]
    ge = le = 0
    for _ in range(n_draws):
        L = lab.copy()
        for ix in idx_by_w:
            L[ix] = lab[ix][rng.permutation(len(ix))]
        d = diff_of(fav, L)
        ge += d >= obs - 1e-12
        le += d <= obs + 1e-12
    return obs, ge / n_draws, le / n_draws


def exact_p(fav, lab, wk):
    """Exact within-week permutation distribution of (#runners in fav). The difference is monotone in
    that count (group sizes fixed), so p = P[count >= obs] / P[count <= obs]. Per week the count of
    runners landing in fav is hypergeometric; convolve across weeks."""
    nf = fav.sum(); nr = (~fav).sum(); R = lab.sum()
    dist = {0: 1.0}
    for w in np.unique(wk):
        ix = wk == w
        n = int(ix.sum()); k = int(lab[ix].sum()); f = int(fav[ix].sum())
        hd = {j: math.comb(k, j) * math.comb(n - k, f - j) / math.comb(n, f)
              for j in range(max(0, f - (n - k)), min(k, f) + 1)}
        nd = collections.defaultdict(float)
        for a, pa in dist.items():
            for j, pj in hd.items():
                nd[a + j] += pa * pj
        dist = nd
    obs = int(lab[fav].sum())
    return sum(p for c, p in dist.items() if c >= obs), sum(p for c, p in dist.items() if c <= obs)


def split(col, kind, lo, hi, label="runner5", subset=None):
    xs = [x for x in (rows if subset is None else subset) if x[col] is not None]
    v = np.array([x[col] for x in xs], dtype=float)
    if kind == "bool0":
        fav = v == 0
    elif kind == "bool1":
        fav = v == 1
    elif kind == "LOWER":
        fav = v <= lo
    elif kind == "HIGHER":
        fav = v >= hi
    lab = np.array([x[label] for x in xs], dtype=float)
    wk = np.array([x["week"] for x in xs])
    return fav, lab, wk


# ---------------------------------------------------------------- (5) HOLDS / AGAINST splits (+ the two PASS-eligible)
P("=" * 100)
P("(5) SPLITS + week-block permutation p (own generator numpy default_rng(686); 2,000 draws as registered, "
  "200,000 draws for precision, and EXACT)")
read_lines = open(os.path.join(OUT, "686_results_out.txt")).read().splitlines()
for col, (kind, lo, hi) in CUTS.items():
    fav, lab, wk = split(col, kind, lo, hi)
    obs, pd2k, pr2k = perm_p(fav, lab, wk, 2000, np.random.default_rng(686))
    _, pd200k, pr200k = perm_p(fav, lab, wk, 200000, np.random.default_rng(686))
    ped, per = exact_p(fav, lab, wk)
    rl = [l for l in read_lines if l.startswith(col + " |")]
    rl = rl[0].split(" | ")[6:9] if rl else "?"
    P(f"  {col:22} fav {int(fav.sum())}/{lab[fav].mean()*100:.1f}% ({int(lab[fav].sum())} runners) vs rest "
      f"{int((~fav).sum())}/{lab[~fav].mean()*100:.1f}% ({int(lab[~fav].sum())}) diff {obs*100:+.1f}pp | "
      f"p(dec) 2k {pd2k:.3f} 200k {pd200k:.4f} exact {ped:.4f} | p(rev) 2k {pr2k:.3f} 200k {pr200k:.4f} exact {per:.4f}"
      f"  || read: {rl}")
    if col == "PRE_adr20_pct":
        P(f"     thin-rule inputs: runners among rows carrying the feature {int(lab.sum())} (>=3), fav {int(fav.sum())} (>=8), "
          f"rest {int((~fav).sum())} (>=8) -> not thin; sign {'+' if obs > 0 else '-'} -> "
          f"{'sign against' if obs <= 0 else 'sign ok'}")
    if col == "PRE_dollar_vol_20d":
        P(f"     thin-rule inputs: runners among rows carrying the feature {int(lab.sum())}, fav {int(fav.sum())}, rest {int((~fav).sum())}; "
          f"sign {'+' if obs > 0 else '-'}")

# ---------------------------------------------------------------- (6) leads
P("=" * 100)
P("(6) REVERSED LEADS on the block (declared: that third runs LESS)")
ADR_LO, ADR_HI = 4.4901, 6.4167
for x in rows:
    a = x["PRE_adr20_pct"]
    x["adr_stratum"] = 0 if a <= ADR_LO else (2 if a >= ADR_HI else 1)


def controlled(third, lab, strat):
    tot = 0; acc = 0.0
    for s_ in np.unique(strat):
        ix = strat == s_
        t_ = third & ix; r_ = (~third) & ix
        if t_.sum() == 0 or r_.sum() == 0:
            continue
        n = ix.sum()
        acc += n * (lab[t_].mean() - lab[r_].mean()); tot += n
    return acc / tot if tot else float("nan")


for name, col, rule in [("L1 quietest third", "PRE_base_range20_pct", lambda v: v <= 16.3469),
                        ("L2 widest gap-day-range third", "CLOSE_range_xadr", lambda v: v >= 2.9858)]:
    v = np.array([x[col] for x in rows]); third = rule(v)
    lab = np.array([x["runner5"] for x in rows], dtype=float)
    wk = np.array([x["week"] for x in rows]); strat = np.array([x["adr_stratum"] for x in rows])
    obs_raw = lab[third].mean() - lab[~third].mean()
    # raw p(less): shuffle within week
    _, _, pl_raw = perm_p(third, lab, wk, 200000, np.random.default_rng(687))
    pe_more, pe_less = exact_p(third, lab, wk)
    obs_c = controlled(third, lab, strat)
    rng = np.random.default_rng(687)
    cells = [np.where((wk == w) & (strat == s_))[0] for w in np.unique(wk) for s_ in np.unique(strat)]
    cells = [c_ for c_ in cells if len(c_)]
    le = 0; ge = 0; N = 50000
    for _ in range(N):
        L = lab.copy()
        for ix in cells:
            L[ix] = lab[ix][rng.permutation(len(ix))]
        d = controlled(third, L, strat)
        le += d <= obs_c + 1e-12; ge += d >= obs_c - 1e-12
    P(f"  {name:30} third {int(third.sum())}/{lab[third].mean()*100:.1f}% ({int(lab[third].sum())}) vs rest "
      f"{int((~third).sum())}/{lab[~third].mean()*100:.1f}% ({int(lab[~third].sum())}) raw {obs_raw*100:+.1f}pp "
      f"p(less) 200k {pl_raw:.3f} exact {pe_less:.3f} | controlled {obs_c*100:+.1f}pp p(less) {le/N:.3f} p(more) {ge/N:.3f} (50k draws)")
    P(f"     strata sizes (ADR% <=4.49 / mid / >=6.42): {[int((strat==s_).sum()) for s_ in range(3)]}; third per stratum "
      f"{[int((third & (strat==s_)).sum()) for s_ in range(3)]}; runners per stratum {[int(lab[strat==s_].sum()) for s_ in range(3)]}")

# ---------------------------------------------------------------- sensitivity: GRAL 09-21 calendar-censored
P("=" * 100)
P("SENSITIVITY — drop GRAL 09-21 (its daily file has no 09-23 bar, so its +1..+15 calendar window is incomplete)")
sub = [x for x in rows if not (x["t"] == "GRAL" and x["s"] == "2026-09-21")]
P(f"  frame A: n {len(sub)} runners {sum(x['runner5'] for x in sub)}")
for col, (kind, lo, hi) in CUTS.items():
    fav, lab, wk = split(col, kind, lo, hi, subset=sub)
    ped, per = exact_p(fav, lab, wk)
    obs = lab[fav].mean() - lab[~fav].mean()
    P(f"  {col:22} fav {int(fav.sum())}/{lab[fav].mean()*100:.1f}% vs rest {int((~fav).sum())}/{lab[~fav].mean()*100:.1f}% "
      f"diff {obs*100:+.1f}pp exact p(dec) {ped:.4f} p(rev) {per:.4f}")

with open(os.path.join(HERE, "rederive_out.txt"), "w") as f:
    f.write("\n".join(lines) + "\n")
