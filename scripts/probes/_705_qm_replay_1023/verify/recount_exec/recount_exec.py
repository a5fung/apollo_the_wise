#!/usr/bin/env python3
"""Independent recount of the #705 execution-variants run (02_execution_variants) from the TABLES IT WROTE only
(qm_exec_1023/trades.tsv.gz, chains.tsv, plus the first read's account_band.tsv for a band-parity check and the era-A export /
candidate stream for the calendar, opens, closes, base rows). No import of 01_replay.py / 02_execution_variants.py, no walk.

  (1) per-trade headline V0 / V1 / V3 / COMBINED, his calls and control
  (2) account curve V0 / V1 / V3 / V4 / COMBINED (recount.py's chronological simulation, 'mark' legs added)
  (3) the fork + the same-day band (200 draws re-derived from seed 702 + the registered key; V0's band is checked against the
      FIRST read's stored account_band.tsv before COMBINED's is trusted)
  (4) V1 control extremes: 5 largest / 5 smallest, stop width, minute-0, own-low check against the stored minute file
  (5) chain reconstruction (his chains independent; control chains structural + pass-count totals)
"""
import collections, gzip, math, os, re, sys, zlib
import numpy as np, pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
OUT2 = "/Users/alvinfung/apollo_data/cb702/qm_streams/qm_exec_1023/"
OUT1 = "/Users/alvinfung/apollo_data/cb702/qm_streams/qm_replay_1023/"
EXPORT_A = "/Users/alvinfung/apollo_data/cb702_pre_v2/daily_closes_all.csv.gz"
CAND_A = "/Users/alvinfung/apollo_data/cb702_pre_v2/out/candidates_tl_com.tsv"
SESS = "/Users/alvinfung/apollo_data/cb702_pre_v2/sessions.txt"
MINUTES = "/Users/alvinfung/apollo_data/cb702_pre_v2/minutes/"
PRINTOUT = os.path.join(HERE, "..", "..", "02_execution_variants.txt")
SEED, DRAWS = 702, 200
BAND_KEY = "qm_replay|band|A|same-day (registered)"

ROWS = []   # (claim, printout, yours, match)
def rec(claim, printed, mine, ok):
    ROWS.append((claim, printed, mine, "OK" if ok else "MISMATCH"))

# ------------------------------------------------------------------ load
t = pd.read_csv(OUT2 + "trades.tsv.gz", sep="\t", dtype=str, keep_default_na=False)
t = t[t.era == "A"].copy()
for c in ("realized_r", "fill", "stop", "fill_minute", "sessions_held", "width_pct", "adr20"):
    t[c] = pd.to_numeric(t[c].replace("", np.nan))
assert not t.duplicated(["ticker", "E", "entry_set"]).any()
F = t[t.entry_status == "filled"]
TB = {s: {(r.ticker, r.E): r for r in g.itertuples()} for s, g in F.groupby("entry_set")}
print("filled rows per entry set:", {s: len(v) for s, v in TB.items()})

ch = pd.read_csv(OUT2 + "chains.tsv", sep="\t", dtype=str, keep_default_na=False)
ch = ch[ch.era == "A"]
CH = {}   # (variant, group) -> {(tk, E): [E_i...]}
for (v, g), d in ch.groupby(["variant", "group"]):
    CH[(v, g)] = {(a, b): es.split(",") for a, b, es in zip(d.origin_ticker, d.origin_E, d.trade_Es)}
CH_SET = {"V3": "orh5", "COMBINED": "level_tc"}

# ---------------------------------------------------------------- the printout (parsed, not typed)
txt = open(PRINTOUT).read().split("\n")
def block(start_pat, end_pat):
    i = next(k for k, l in enumerate(txt) if l.startswith(start_pat))
    j = next(k for k in range(i + 1, len(txt)) if txt[k].startswith(end_pat))
    return txt[i:j]
def cells(l):
    return [c.strip() for c in l.split("|")]
HEAD = {}
for l in block("## HEADLINE", "### beside")[1:]:
    c = cells(l)
    if len(c) > 10 and c[0] in ("V0", "V1", "V3", "COMBINED") and c[1] in ("his calls", "control (same day)"):
        HEAD[(c[0], "his" if c[1] == "his calls" else "ctl")] = c
ACC = {}
for l in block("## ACCOUNT CURVE", "- beside")[1:]:
    c = cells(l)
    if len(c) > 12 and c[0] in ("V0", "V1", "V3", "V4", "COMBINED"):
        ACC[c[0]] = c
BAND = {}
for l in block("## CONTROL BAND", "- beside")[1:]:
    c = cells(l)
    if len(c) == 7 and c[0] in ("V0", "V1", "V3", "V4", "COMBINED"):
        BAND[(c[0], c[1])] = c

# ------------------------------------------------------------------ (1) headline
def tail(r):
    r = np.asarray(r, dtype=float)
    return dict(n=len(r), ge10=100 * float((r >= 10).mean()), mx=float(r.max()), win=100 * float((r > 0).mean()), mean=float(r.mean()))

def trades_of(variant, group):
    """rows (itertuples) of the trades behind a headline cell."""
    if variant in ("V0", "V1"):
        s = {"V0": "orh5", "V1": "level"}[variant]
        flag = "is_his" if group == "his" else "is_ctl"
        return [r for r in TB[s].values() if getattr(r, flag) == "1"]
    s = CH_SET[variant]
    seen, out = set(), []
    for (tk, E0), es in CH[(variant, group)].items():
        for E in es:
            if (tk, E) not in seen:
                seen.add((tk, E)); out.append(TB[s][(tk, E)])
    return out

def num(s):
    return float(s.replace("+", "").replace("%", ""))

print("\n(1) HEADLINE")
for v in ("V0", "V1", "V3", "COMBINED"):
    for g in ("his", "ctl"):
        rows = trades_of(v, g)
        mat = [r for r in rows if r.mature == "1"]
        st = tail([r.realized_r for r in mat])
        p = HEAD[(v, g)]
        lab = f"{v} {'his calls' if g == 'his' else 'control'}"
        # printed: trades n = c[3], mature n = c[4], >=10R = c[6], max = c[8], win = c[10], mean = c[11]
        mine = f"n={len(rows)} mean={st['mean']:+.3f} >=10R/100={st['ge10']:+.1f} max={st['mx']:+.2f} win={st['win']:.1f}%"
        pr = f"n={p[3]} mean={p[11]} >=10R/100={p[6]} max={p[8]} win={p[10]}"
        ok = (len(rows) == int(p[3]) and len(mat) == int(p[4]) and f"{st['mean']:+.3f}" == p[11] and f"{st['ge10']:+.1f}" == p[6]
              and f"{st['mx']:+.2f}" == p[8] and f"{st['win']:.1f}%" == p[10])
        rec(f"headline {lab}", pr, mine, ok)
        print(" ", lab, "|", pr, "|", mine, "|", "OK" if ok else "MISMATCH")

# ------------------------------------------------------------------ calendar / bars
sess = [l.strip() for l in open(SESS) if l.strip()]
cal = sess
ci = {d: i for i, d in enumerate(cal)}
NC = len(cal)
need_tk = set(t.ticker)
ex = pd.read_csv(EXPORT_A, header=None, names=["ticker", "d", "o", "h", "l", "c", "v"], dtype={"ticker": str, "d": str})
ex = ex[ex.ticker.isin(need_tk)]
ex = ex[ex.d.isin(ci)]
ex["i"] = ex.d.map(ci)
OPEN, CLOSE = {}, {}
for tk, g in ex.groupby("ticker"):
    o = np.full(NC, np.nan); c = np.full(NC, np.nan)
    o[g.i.to_numpy()] = g.o.to_numpy(); c[g.i.to_numpy()] = g.c.to_numpy()
    OPEN[tk] = o; CLOSE[tk] = c
del ex
print("\nbars loaded for", len(OPEN), "tickers; calendar", NC)

# ------------------------------------------------------------------ trade -> sim record
_cache = {}
def sim_trade(r):
    k = (r.entry_set, r.ticker, r.E)
    if k in _cache:
        return _cache[k]
    e = ci[r.E]
    legs = []
    for lg in r.legs.split(";"):
        j, kind, frac, px = lg.split(":"); j = int(j); frac = float(frac); px = float(px)
        if kind == "mark":
            order = 3
        elif j == 0:
            order = 2                       # day0_stop / day0_gap: after the fill, inside the day
        elif kind == "trail" or kind == "stop_gap":
            order = 0
        elif kind == "partial":
            order = 3
        else:                               # stop
            o = OPEN[r.ticker][e + j]
            order = 0 if abs(px - o) < 5e-7 else 2
        legs.append((e + j, order, frac, px))
    d = dict(tk=r.ticker, E=r.E, e=e, fill=r.fill, stop=r.stop, fm=int(r.fill_minute), legs=legs, r=r.realized_r)
    _cache[k] = d
    return d

def simulate(trs, risk=0.01, cap=0.20, lim=0.30):
    byE = collections.defaultdict(list)
    for x in trs:
        byE[x["e"]].append(x)
    if not byE:
        return None
    start = min(byE); last = max(l[0] for x in trs for l in x["legs"])
    sched = collections.defaultdict(lambda: ([], [], [], []))
    cash, eq_prev = 1.0, 1.0
    pos = []
    cnt = collections.Counter()
    ye = {}
    peak, dd = 1.0, 0.0        # the start equity 1.0 counts as a peak (as in the first read's drawdown)
    for i in range(start, last + 1):
        def run(order):
            nonlocal cash
            S = sched.get(i)
            if S is None:
                return
            for p, frac, px in S[order]:
                cash += p["sh"] * frac * px
                p["rem"] -= frac
        run(0)
        held = collections.defaultdict(float)
        for p in pos:
            held[p["tk"]] += p["sh"] * p["rem"] * p["fill"]
        for x in sorted(byE.get(i, []), key=lambda z: (z["fm"], z["tk"])):
            width = (x["fill"] - x["stop"]) / x["fill"]
            val = eq_prev * min(risk / width, cap)
            room = lim * eq_prev - held[x["tk"]]
            if room <= 1e-12:
                cnt["skipped_stock_limit"] += 1; continue
            if val > room:
                val = room; cnt["trimmed_stock_limit"] += 1
            if val > cash + 1e-12:
                cnt["skipped_no_room"] += 1; continue
            cash -= val
            p = dict(tk=x["tk"], sh=val / x["fill"], fill=x["fill"], rem=1.0, lastc=x["fill"])
            held[x["tk"]] += val
            pos.append(p)
            for (li, order, frac, px) in x["legs"]:
                sc = sched[li]
                sc[order].append((p, frac, px))
            cnt["entered"] += 1
        run(2); run(3)
        pos = [p for p in pos if p["rem"] > 1e-9]
        mtm = cash
        for p in pos:
            c = CLOSE[p["tk"]][i]
            if not math.isnan(c):
                p["lastc"] = c
            mtm += p["sh"] * p["rem"] * p["lastc"]
        eq_prev = mtm
        ye[cal[i][:4]] = mtm
        peak = max(peak, mtm); dd = max(dd, 1 - mtm / peak)
        sched.pop(i, None)
    prev, yr = 1.0, {}
    for y in sorted(ye):
        yr[y] = ye[y] / prev - 1; prev = ye[y]
    return dict(yearly=yr, final=eq_prev, dd=dd, cnt=cnt, open_left=len(pos))

VAR_ACC = {"V0": ("V0", 0.20), "V1": ("V1", 0.20), "V3": ("V3", 0.20), "V4": ("V0", 0.30), "COMBINED": ("COMBINED", 0.30)}
def his_trades(src):
    if src in ("V0", "V1"):
        return [sim_trade(r) for r in trades_of(src, "his")]
    return [sim_trade(r) for r in trades_of(src, "his")]

print("\n(2) ACCOUNT CURVE (his calls)")
HIS_SIM = {}
for v, (src, cap) in VAR_ACC.items():
    s = simulate(his_trades(src), cap=cap)
    HIS_SIM[v] = s
    p = ACC[v]
    # printed columns: variant,risk,cap,2017,2018,2019,2020,2021,2022,final,maxdd,offered,reentries,entered,skip_room,skip_stock,trim,capbound,maxopen,maxgross
    y20, y21 = s["yearly"]["2020"], s["yearly"]["2021"]
    mine = (f"2020 {y20*100:.1f}% 2021 {y21*100:.1f}% final {s['final']:.3f} dd {s['dd']*100:.1f}% entered {s['cnt']['entered']} "
            f"skip_room {s['cnt']['skipped_no_room']} skip_stock {s['cnt']['skipped_stock_limit']}")
    pr = f"2020 {p[6]} 2021 {p[7]} final {p[9]} dd {p[10]} entered {p[13]} skip_room {p[14]} skip_stock {p[15]}"
    ok = (f"{y20*100:.1f}%" == p[6] and f"{y21*100:.1f}%" == p[7] and f"{s['final']:.3f}" == p[9] and f"{s['dd']*100:.1f}%" == p[10]
          and str(s['cnt']['entered']) == p[13] and str(s['cnt']['skipped_no_room']) == p[14] and str(s['cnt']['skipped_stock_limit']) == p[15]
          and s["open_left"] == 0)
    rec(f"account {v}", pr, mine, ok)
    print(" ", v, "|", pr, "|", mine, "|", "OK" if ok else "MISMATCH")
    # also compare against the daily curve file? (only the year-ends here; the stored curve is read below)

# stored daily curve vs mine (year-end equity)
ah = pd.read_csv(OUT2 + "account_his.tsv", sep="\t")
for v in VAR_ACC:
    a = ah[ah.variant == v]
    ok = abs(a.equity.iloc[-1] - HIS_SIM[v]["final"]) < 1e-6
    rec(f"stored daily curve account_his.tsv last value vs my final, {v}", f"{a.equity.iloc[-1]:.6f}", f"{HIS_SIM[v]['final']:.6f}", ok)
    print("  stored curve last value", v, round(a.equity.iloc[-1], 6), "mine", round(HIS_SIM[v]["final"], 6))

# ------------------------------------------------------------------ (3) band: re-derived draws
ev0 = t[t.entry_set == "orh5"]
his_by_date = collections.Counter(ev0[ev0.is_his == "1"].E)
assert sum(his_by_date.values()) == 236
ctl_ev = ev0[ev0.is_ctl == "1"]
ctl_by_date = collections.defaultdict(list)
for tk, E in zip(ctl_ev.ticker, ctl_ev.E):          # file order = (ticker, E) sorted, as in the first read's event list
    ctl_by_date[E].append((tk, E))
assert sum(len(v) for v in ctl_by_date.values()) == 23188
rng = np.random.default_rng([SEED, zlib.crc32(BAND_KEY.encode())])
draws = []
for _ in range(DRAWS):
    out = []
    for d in sorted(his_by_date):
        k = his_by_date[d]; pool = ctl_by_date.get(d, [])
        if len(pool) <= k:
            out.extend(pool); continue
        pick = rng.choice(len(pool), size=k, replace=False)
        out.extend(pool[j] for j in sorted(pick.tolist()))
    draws.append(out)

def draw_trades(src, ids):
    if src in ("V0", "V1"):
        s = {"V0": "orh5", "V1": "level"}[src]
        return [sim_trade(TB[s][k]) for k in ids if k in TB[s]]
    s = CH_SET[src]; seen, out = set(), []
    for k in ids:
        for E in CH[(src, "ctl")].get(k, []):
            if (k[0], E) not in seen:
                seen.add((k[0], E)); out.append(sim_trade(TB[s][(k[0], E)]))
    return out

# first read's stored band (V0 parity)
b1 = pd.read_csv(OUT1 + "account_band.tsv", sep="\t", dtype=str, keep_default_na=False)
b1 = b1[(b1.band == "same-day (registered)")]
BANDS = {}
print("\n(3) BAND (200 re-derived draws)")
for v, (src, cap) in VAR_ACC.items():
    sims = [simulate(draw_trades(src, ids), cap=cap) for ids in draws]
    BANDS[v] = sims
    for meas in ("2020", "2021", "final", "dd"):
        vals = np.array([(s["yearly"].get(meas) if meas in ("2020", "2021") else s[meas]) for s in sims], dtype=float)
        hv = HIS_SIM[v]["yearly"][meas] if meas in ("2020", "2021") else HIS_SIM[v][meas]
        share = float((vals >= hv).mean())
        pcts = [float(np.percentile(vals, q)) for q in (5, 50, 95)]
        key = {"2020": "2020 return", "2021": "2021 return", "final": "final equity", "dd": "max drawdown (higher = WORSE)"}[meas]
        p = BAND[(v, key)]
        pr = f"p5 {p[3]} p50 {p[4]} p95 {p[5]} share {p[6]}"
        mine = f"p5 {pcts[0]:+.3f} p50 {pcts[1]:+.3f} p95 {pcts[2]:+.3f} share {share*100:.1f}%"
        ok = (f"{pcts[0]:+.3f}" == p[3] and f"{pcts[1]:+.3f}" == p[4] and f"{pcts[2]:+.3f}" == p[5] and f"{share*100:.1f}%" == p[6])
        rec(f"band {v} {key}", pr, mine, ok)
        print(" ", v, key, "|", pr, "|", mine, "|", "OK" if ok else "MISMATCH")
        if v == "V0":
            m1 = {"2020": "2020", "2021": "2021", "final": "final", "dd": "max_dd"}[meas]
            r1 = b1[(b1.config == "primary") & (b1.measure == m1)]
            if len(r1) == 1:
                r1 = r1.iloc[0]
                diffs = [abs(float(r1[c]) - float(np.percentile(vals, q))) for c, q in (("p5", 5), ("p25", 25), ("p50", 50), ("p75", 75), ("p95", 95))]
                dshare = abs(float(r1.share_ge_his) - share)
                dhis = abs(float(r1["his"]) - hv)
                ok1 = max(diffs) < 1e-6 and dshare < 1e-12 and dhis < 1e-6   # stored legs are printed to 6 decimals: ~1e-7 float noise
                rec(f"band parity vs FIRST read's STORED V0 band (5 pctiles + his + share), {key}",
                    f"stored his {float(r1['his']):.6f} p5 {float(r1.p5):+.4f} share {r1.share_ge_his}",
                    f"his {hv:.6f} p5 {np.percentile(vals,5):+.4f} share {share}  (max pctile diff {max(diffs):.1e}, his diff {dhis:.1e})", ok1)
                if meas == "dd":
                    near = sorted(vals)[:0]
                    close = [(float(x), float(x) - hv) for x in vals if abs(x - hv) < 1e-4]
                    print("   dd draws within 1e-4 of his:", close, "his", repr(hv), "stored his", r1["his"])

# the fork
y20, y21 = HIS_SIM["COMBINED"]["yearly"]["2020"], HIS_SIM["COMBINED"]["yearly"]["2021"]
cvals = np.array([s["final"] for s in BANDS["COMBINED"]]); cshare = float((cvals >= HIS_SIM["COMBINED"]["final"]).mean())
fork_lines = [l for l in txt if l.startswith("- yearly return >= +50% in BOTH") or l.startswith("- the same-day band at or above his final")]
pr = "2020 38.5%, 2021 13.7%, band share 10.0%"
mine = f"2020 {y20*100:.1f}%, 2021 {y21*100:.1f}%, band share {cshare*100:.1f}% ({int(round(cshare*DRAWS))} of {DRAWS})"
rec("FORK COMBINED 2020 / 2021 / band share (user-stated)", pr, mine,
    f"{y20*100:.1f}" == "38.5" and f"{y21*100:.1f}" == "13.7" and f"{cshare*100:.1f}" == "10.0")
rec("FORK verdict (printout: both-years arm not met, band arm not met -> NEXT GAPS)", "; ".join(l[:60] for l in fork_lines) + " -> NEXT GAPS", f"years>=50% in both: {y20 >= .5 and y21 >= .5}; share<=5%: {cshare <= .05} -> NEXT GAPS",
    not (y20 >= .5 and y21 >= .5 and cshare <= .05))


# ------------------------------------------------------------------ trade-table internal consistency (legs -> R), every filled row
bad_r = bad_f = bad_w = 0
for r in F.itertuples():
    fr = pr_ = 0.0
    for lg in r.legs.split(";"):
        j, kind, frac, px = lg.split(":"); fr += float(frac); pr_ += float(frac) * (float(px) - r.fill)
    bad_f += abs(fr - 1) > 1e-5
    bad_r += abs(pr_ / (r.fill - r.stop) - r.realized_r) > 2e-3 * max(1, abs(r.realized_r)) * 0.01 + 1e-4 * max(1.0, abs(r.realized_r))
    bad_w += abs((r.fill - r.stop) / r.fill - r.width_pct) > 1e-9
rec("trade table: legs sum to 1, R recomputed from legs, width = (fill-stop)/fill, every filled row (all 5 entry sets)",
    "(asserted in the run)", f"{len(F)} rows; legs!=1: {bad_f}; R off (rel 1e-4): {bad_r}; width off: {bad_w}", bad_f == 0 and bad_r == 0 and bad_w == 0)
print("legs->R consistency:", len(F), bad_f, bad_r, bad_w)

# ------------------------------------------------------------------ (5) chain reconstruction
print("\n(5) CHAIN RECONSTRUCTION")
cand = pd.read_csv(CAND_A, sep="\t", dtype=str, keep_default_na=False, usecols=["K", "ticker", "E", "base_id"])
cand = cand[cand.K == "tl"]
later = collections.defaultdict(list)
for tk, b, E in zip(cand.ticker, cand.base_id, cand.E):
    later[(tk, b)].append(E)
for k in later:
    later[k].sort()

def chain_rec(tk, E0, setname, refuse_none=True):
    """-> (chain E list, passes Counter) under the rule: stop-out earns a retry; next filled row with exit_day < E2 <= cal[e0+20]; <= 2."""
    T = TB[setname]
    o = T.get((tk, E0))
    if o is None:
        return [], collections.Counter()
    e0 = ci[E0]
    lim = cal[min(NC - 1, e0 + 20)]
    chain, cur, n_re, passes = [E0], o, 0, collections.Counter()
    while n_re < 2 and cur.status in ("stopped", "stopped_day0"):
        exit_d = cal[ci[cur.E] + int(cur.sessions_held)]
        nxt = None
        for E2 in later[(tk, o.base_id)]:
            if not (exit_d < E2 <= lim):
                continue
            if (tk, E2) not in T:
                passes["not_filled"] += 1; continue
            nxt = E2; break
        if nxt is None:
            break
        chain.append(nxt); cur = T[(tk, nxt)]; n_re += 1
    return chain, passes

def check_chains(v, g):
    setname = CH_SET[v]
    stored = CH[(v, g)]
    diff, tot = 0, collections.Counter()
    for (tk, E0), es in stored.items():
        mine, ps = chain_rec(tk, E0, setname)
        if mine != es:
            diff += 1
    return stored, diff

for v in ("V3", "COMBINED"):
    setname = CH_SET[v]
    stored = CH[(v, "his")]
    # all his events with a filled origin
    his_orig = [r for r in TB[setname].values() if r.is_his == "1"]
    assert len(his_orig) == len(stored), (len(his_orig), len(stored))
    d = 0; passes = collections.Counter()
    for r in his_orig:
        mine, ps = chain_rec(r.ticker, r.E, setname)
        passes.update(ps)
        d += mine != stored[(r.ticker, r.E)]
    pr = {"V3": "his: re-entry trades 114, passed_not_filled 28, reentry_1 86, reentry_2 42",
          "COMBINED": "his: re-entry trades 202, passed_not_filled 12, reentry_1 135, reentry_2 90"}[v]
    n1 = sum(1 for e in stored.values() if len(e) >= 2); n2 = sum(1 for e in stored.values() if len(e) == 3)
    re_keys = {(k[0], E) for k, es in stored.items() for E in es[1:]}
    his_keys = {(r.ticker, r.E) for r in his_orig}
    mine_s = (f"chains differing from chains.tsv: {d}; distinct re-entry trades {len(re_keys)} (already a his call: {len(re_keys & his_keys)}), "
              f"passed_not_filled {passes['not_filled']}, reentry_1 {n1}, reentry_2 {n2}")
    exp = {"V3": (114, 16, 28, 86, 42), "COMBINED": (202, 22, 12, 135, 90)}[v]
    ok = d == 0 and (len(re_keys), len(re_keys & his_keys), passes["not_filled"], n1, n2) == exp
    rec(f"{v} his chains rebuilt independently (stop-out -> next filled break, exit day < E2 <= E+20, max 2)", pr, mine_s, ok)
    print(" ", v, "his:", mine_s, "|", pr, "|", "OK" if ok else "MISMATCH")
    # control: structural validity + pass totals; unfilled rows are not_filled passes, filled-but-skipped are control-rule passes
    stored_c = CH[(v, "ctl")]
    bad = 0; p_nf = p_cr = 0
    for (tk, E0), es in stored_c.items():
        T = TB[setname]
        if es[0] != E0 or any((tk, E) not in T for E in es) or len(es) > 3:
            bad += 1; continue
        e0 = ci[E0]; lim = cal[min(NC - 1, e0 + 20)]
        cur = T[(tk, E0)]; n_re = 0; idx = 0
        while n_re < 2 and cur.status in ("stopped", "stopped_day0"):
            exit_d = cal[ci[cur.E] + int(cur.sessions_held)]
            want = es[idx + 1] if idx + 1 < len(es) else None
            hit = None
            for E2 in later[(tk, T[(tk, E0)].base_id)]:
                if not (exit_d < E2 <= lim):
                    continue
                if want is not None and E2 == want:
                    hit = E2; break
                if (tk, E2) not in T:
                    p_nf += 1
                else:
                    p_cr += 1     # filled but skipped -> must be a control-rule refusal (not independently checkable)
            if want is None:
                break
            if hit is None:
                bad += 1; break
            cur = T[(tk, want)]; n_re += 1; idx += 1
        else:
            if idx + 1 != len(es):
                bad += 1
    pcr, pnf = {"V3": (254, 3939), "COMBINED": (290, 1587)}[v]
    pr = f"ctl: passed_control_rule {pcr}, passed_not_filled {pnf} (sum {pcr + pnf})"
    mine_s = f"invalid chains {bad}; skipped-filled rows {p_cr}, unfilled rows passed {p_nf} (sum {p_cr + p_nf})"
    # the run checks the control rule BEFORE 'filled', so its control-rule count also holds refused rows that never filled: mine <= theirs, sums equal
    ok = bad == 0 and p_cr <= pcr and p_cr + p_nf == pcr + pnf
    rec(f"{v} control chains: structure valid + total rows passed", pr, mine_s, ok)
    print(" ", v, "ctl:", mine_s, "|", pr, "|", "OK" if ok else "MISMATCH")

# ------------------------------------------------------------------ (4) V1 control extremes
print("\n(4) V1 CONTROL EXTREMES")
v1 = pd.DataFrame([r._asdict() for r in TB["level"].values() if r.is_ctl == "1" and r.mature == "1"])
print("  V1 ctl mature trades:", len(v1), "max", v1.realized_r.max(), "min", v1.realized_r.min())
v1["w"] = v1.width_pct * 100
def firstbar(tk, E, fm):
    """own-low check from the stored minute file: (first bar's minute index, fill minute's low, day's min low before it)"""
    rows = []
    with gzip.open(MINUTES + f"{E}.psv.gz", "rt") as fh:
        for l in fh:
            p = l.split("|")
            if p[0] == tk:
                rows.append((int(p[1]), float(p[2]), float(p[3]), float(p[4]), float(p[5])))
    rows.sort()
    m = [i for i, x in enumerate(rows) if x[0] == fm][0]
    prior_low = min([x[3] for x in rows[:m]], default=float("inf"))
    return rows[0][0], rows[m][3], prior_low
def show(df, title):
    print(" ", title)
    print("   ticker   E           R       fill      stop      width%   fill_min first_bar stop==fill-min-low  own_low  status        exit legs")
    for r in df.itertuples():
        fb, lo, pl = firstbar(r.ticker, r.E, int(r.fill_minute))
        own = lo < pl
        print(f"   {r.ticker:<8} {r.E}  {r.realized_r:+9.2f}  {r.fill:9.3f} {r.stop:9.3f} {r.w:7.3f}  {int(r.fill_minute):>7}  {fb:>8}  {str(abs(lo - r.stop) < 1e-9):<18} {str(own):<8} {r.status:<13} {r.legs[:70]}")
    return df
top = show(v1.sort_values("realized_r", ascending=False).head(5), "5 LARGEST")
bot = show(v1.sort_values("realized_r").head(5), "5 SMALLEST")
ext = pd.concat([top, bot])
print("  all 10: fill_minute==0:", int((ext.fill_minute == 0).sum()), "| width% max:", round(ext.w.max(), 3), "| width% median of V1 ctl:", round(v1.w.median(), 3))
rec("V1 control max R / worst R", "+589.98 / -93.79", f"{v1.realized_r.max():+.2f} / {v1.realized_r.min():+.2f}",
    f"{v1.realized_r.max():+.2f}" == "+589.98" and f"{v1.realized_r.min():+.2f}" == "-93.79")
# concentration: how much of the extreme tail sits on narrow stops / minute-0
for thr in (0.2, 0.5):
    narrow = v1[v1.w < thr]
    print(f"  stop width < {thr}% of fill: {len(narrow)} trades ({len(narrow)/len(v1)*100:.1f}%), |R|>20: {int((narrow.realized_r.abs()>20).sum())} of {int((v1.realized_r.abs()>20).sum())} such trades overall; R>=10: {int((narrow.realized_r>=10).sum())} of {int((v1.realized_r>=10).sum())}")
m0 = v1[v1.fill_minute == 0]
print(f"  fill in minute 0: {len(m0)} of {len(v1)}; |R|>20 in minute 0: {int((m0.realized_r.abs()>20).sum())} of {int((v1.realized_r.abs()>20).sum())}; R>=10 in minute 0: {int((m0.realized_r>=10).sum())} of {int((v1.realized_r>=10).sum())}")
print("  sum of R: all", round(v1.realized_r.sum(), 1), "| minute 0:", round(m0.realized_r.sum(), 1), "| other:", round(v1.realized_r.sum() - m0.realized_r.sum(), 1))
print("  mean R: all", round(v1.realized_r.mean(), 3), "| minute 0:", round(m0.realized_r.mean(), 3), "| not minute 0:", round(v1[v1.fill_minute != 0].realized_r.mean(), 3))

# ------------------------------------------------------------------ table
print("\n\nclaim | printout | yours | match")
for c, p, m, ok in ROWS:
    print(f"{c} | {p} | {m} | {ok}")
print("\nMISMATCHES:", sum(1 for r in ROWS if r[3] != "OK"), "of", len(ROWS))
