#!/usr/bin/env python3
"""Independent recount of the #705 round-3 run (03_round3) from the TABLES IT WROTE only
(qm_round3_1024/trades.tsv.gz, account_his.tsv, account_band.tsv; the era-A export / sessions for the calendar, opens, closes).
No import of 01/02/03; the account simulation is recount_exec.py's (own sim of the first read's `simulate`), plus the two switches
the registration names: a per-trade risk (W3: 1% when QQQ at D is up, else 0.5%) and a gross cap (W4m: room = cash + 1 x the previous close's equity).

  (1) account curve B0 W1 W2 W2b W3 COMBINED W4m_B0 (and W1b W2_t20 W3b W4m_C beside, if asked: only the 7 requested are asserted)
      per row: yearly, final, max dd, offered, entered, 1%/0.5% split, skipped, trimmed, cap bound, max open, max gross, deepest cash
      daily curve vs the stored account_his.tsv, day by day, for the 7
  (2) the 200 same-day draws (seed 702 + registered key) re-derived; p5/p50/p95 + share vs the printed CONTROL BAND, the 7 variants
  (3) the fork: COMBINED 2020 / 2021 / band share, and the margin of the band share (draws near his final)
  (4) W3: his calls by QQQ state at D under B0 (count, mean R), and where B0's / W3's equity came from by state
"""
import collections, gzip, math, os, sys, zlib
import numpy as np, pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
OUT3 = "/Users/alvinfung/apollo_data/cb702/qm_streams/qm_round3_1024/"
OUT1 = "/Users/alvinfung/apollo_data/cb702/qm_streams/qm_replay_1023/"
EXPORT_A = "/Users/alvinfung/apollo_data/cb702_pre_v2/daily_closes_all.csv.gz"
SESS = "/Users/alvinfung/apollo_data/cb702_pre_v2/sessions.txt"
PRINTOUT = os.path.join(HERE, "..", "..", "03_round3.txt")
SEED, DRAWS = 702, 200
BAND_KEY = "qm_replay|band|A|same-day (registered)"
ROWS = []
def rec(claim, printed, mine, ok):
    ROWS.append((claim, printed, mine, "OK" if ok else "MISMATCH"))

# ------------------------------------------------------------------ load the trade table
t = pd.read_csv(OUT3 + "trades.tsv.gz", sep="\t", dtype=str, keep_default_na=False)
t = t[t.era == "A"].copy()
for c in ("realized_r", "fill", "stop", "fill_minute", "sessions_held", "width_pct", "adr20"):
    t[c] = pd.to_numeric(t[c].replace("", np.nan))
assert not t.duplicated(["ticker", "E", "stop_set", "arm"]).any()
F = t[t.entry_status == "filled"]
TB = {k: {(r.ticker, r.E): r for r in g.itertuples()} for k, g in F.groupby(["stop_set", "arm"])}
EV = t.drop_duplicates(["ticker", "E"])
QQQ = {(a, b): q for a, b, q in zip(EV.ticker, EV.E, EV.qqq_at_D)}
assert len(EV) == 23484 and (EV.is_his == "1").sum() == 236 and (EV.is_ctl == "1").sum() == 23188
print("filled rows per (stop, arm):", {k: len(v) for k, v in TB.items()})

# ------------------------------------------------------------------ the printout (parsed, not typed)
txt = open(PRINTOUT).read().split("\n")
def cells(l): return [c.strip() for c in l.split("|")]
def block(start_pat, end_pat):
    i = next(k for k, l in enumerate(txt) if l.startswith(start_pat))
    j = next(k for k in range(i + 1, len(txt)) if txt[k].startswith(end_pat))
    return txt[i:j]
ACC = {}
for l in block("## ACCOUNT CURVE", "### beside")[1:]:
    c = cells(l)
    if len(c) > 20 and not l.strip().startswith("-") and c[0] != "variant" and not c[0].startswith("-"):
        ACC[c[0].replace(" (beside)", "")] = c
BAND = {}
for l in block("## CONTROL BAND", "## THE FORK")[1:]:
    c = cells(l)
    if len(c) == 7 and c[0] not in ("variant",) and not c[0].startswith("-"):
        BAND[(c[0], c[1])] = c
FORK = [l for l in txt if l.startswith("- yearly return >= +50% in BOTH") or l.startswith("- the same-day band at or above his final")]

# ------------------------------------------------------------------ calendar / bars
cal = [l.strip() for l in open(SESS) if l.strip()]
ci = {d: i for i, d in enumerate(cal)}; NC = len(cal)
ex = pd.read_csv(EXPORT_A, header=None, names=["ticker", "d", "o", "h", "l", "c", "v"], dtype={"ticker": str, "d": str})
ex = ex[ex.ticker.isin(set(t.ticker))]; ex = ex[ex.d.isin(ci)]; ex["i"] = ex.d.map(ci)
OPEN, CLOSE = {}, {}
for tk, g in ex.groupby("ticker"):
    o = np.full(NC, np.nan); c = np.full(NC, np.nan)
    o[g.i.to_numpy()] = g.o.to_numpy(); c[g.i.to_numpy()] = g.c.to_numpy()
    OPEN[tk] = o; CLOSE[tk] = c
del ex

# ------------------------------------------------------------------ trade -> sim record (recount_exec.py's ordering of same-day legs)
_cache = {}
def sim_trade(r):
    k = (r.stop_set, r.arm, r.ticker, r.E)
    if k in _cache: return _cache[k]
    e = ci[r.E]; legs = []
    for lg in r.legs.split(";"):
        j, kind, frac, px = lg.split(":"); j = int(j); frac = float(frac); px = float(px)
        if kind == "mark": order = 3
        elif j == 0: order = 2
        elif kind in ("trail", "stop_gap"): order = 0
        elif kind == "partial": order = 3
        else:
            o = OPEN[r.ticker][e + j]
            order = 0 if abs(px - o) < 5e-7 else 2
        legs.append((e + j, order, frac, px))
    d = dict(tk=r.ticker, E=r.E, e=e, fill=r.fill, stop=r.stop, fm=int(r.fill_minute), legs=legs, r=r.realized_r,
             q=QQQ[(r.ticker, r.E)])
    _cache[k] = d
    return d

def simulate(trs, risk=0.01, cap=0.30, lim=0.30, risk_of=None, gross=1.0, track=False):
    byE = collections.defaultdict(list)
    for x in trs: byE[x["e"]].append(x)
    start = min(byE); last = max(l[0] for x in trs for l in x["legs"])
    sched = collections.defaultdict(lambda: ([], [], [], []))
    cash, eq_prev = 1.0, 1.0
    pos = []; cnt = collections.Counter(); ye = {}; curve = {}
    peak, dd = 1.0, 0.0
    max_open, max_gross, min_cash = 0, 0.0, 1.0
    ent = []
    for i in range(start, last + 1):
        def run(order):
            nonlocal cash
            S = sched.get(i)
            if S is None: return
            for p, frac, px in S[order]:
                cash += p["sh"] * frac * px; p["rem"] -= frac
        run(0)
        held = collections.defaultdict(float)
        for p in pos: held[p["tk"]] += p["sh"] * p["rem"] * p["fill"]
        for x in sorted(byE.get(i, []), key=lambda z: (z["fm"], z["tk"])):
            rr = risk if risk_of is None else risk_of(x)
            width = (x["fill"] - x["stop"]) / x["fill"]
            val = eq_prev * min(rr / width, cap)
            room_stock = lim * eq_prev - held[x["tk"]]
            if room_stock <= 1e-12:
                cnt["skipped_stock_limit"] += 1; continue
            trimmed = False
            if val > room_stock:
                val = room_stock; trimmed = True
            if val > cash + (gross - 1.0) * eq_prev + 1e-12:
                cnt["skipped_no_room"] += 1; continue
            if trimmed: cnt["trimmed_stock_limit"] += 1
            if min(rr / width, cap) == cap: cnt["cap_bound"] += 1
            cnt[f"risk_{rr:g}"] += 1
            cash -= val
            p = dict(tk=x["tk"], sh=val / x["fill"], fill=x["fill"], rem=1.0, lastc=x["fill"])
            held[x["tk"]] += val; pos.append(p)
            for (li, order, frac, px) in x["legs"]: sched[li][order].append((p, frac, px))
            cnt["entered"] += 1
            max_open = max(max_open, sum(1 for q in pos if q["rem"] > 1e-9)); min_cash = min(min_cash, cash)
            if track:
                ret = sum(f * px for (_l, _o, f, px) in x["legs"]) / x["fill"] - 1.0
                ent.append(dict(tk=x["tk"], E=x["E"], q=x["q"], val=val, pnl=val * ret, r=x["r"], rr=rr, yr=cal[i][:4]))
        run(2); run(3)
        pos = [p for p in pos if p["rem"] > 1e-9]
        mtm = cash; pv = 0.0
        for p in pos:
            c = CLOSE[p["tk"]][i]
            if not math.isnan(c): p["lastc"] = c
            pv += p["sh"] * p["rem"] * p["lastc"]
        mtm += pv
        if mtm > 0: max_gross = max(max_gross, pv / mtm)
        eq_prev = mtm; ye[cal[i][:4]] = mtm; curve[cal[i]] = mtm
        peak = max(peak, mtm); dd = max(dd, 1 - mtm / peak)
        sched.pop(i, None)
    prev, yr = 1.0, {}
    for y in sorted(ye): yr[y] = ye[y] / prev - 1; prev = ye[y]
    return dict(yearly=yr, final=eq_prev, dd=dd, cnt=cnt, open_left=len(pos), max_open=max_open, max_gross=max_gross,
                min_cash=min_cash, curve=curve, ent=ent)

QQ = lambda x: 0.01 if x["q"] == "up" else 0.005
VARS = {  # name: (stop_set, arm, risk_of, gross)
    "B0": ("lod", "p33_s3_t10", None, 1.0), "W1": ("base_low", "p33_s3_t10", None, 1.0),
    "W2": ("lod", "d3_p33_tspd", None, 1.0), "W2b": ("lod", "trail10_only", None, 1.0),
    "W3": ("lod", "p33_s3_t10", QQ, 1.0), "COMBINED": ("base_low", "d3_p33_tspd", QQ, 1.0),
    "W4m_B0": ("lod", "p33_s3_t10", None, 2.0)}
HIS = {}
def his_trades(v):
    s, a, _, _ = VARS[v]
    return [sim_trade(r) for r in TB[(s, a)].values() if r.is_his == "1"]

# ------------------------------------------------------------------ (1) account curve
pc = lambda x: f"{x*100:.1f}%"
print("\n(1) ACCOUNT CURVE (his calls, 30% cap, 30% per stock)")
ah = pd.read_csv(OUT3 + "account_his.tsv", sep="\t")
for v, (s, a, rof, g) in VARS.items():
    tr = his_trades(v)
    S = simulate(tr, risk_of=rof, gross=g, track=True); HIS[v] = S
    c = S["cnt"]; y = S["yearly"]
    p = ACC[v]
    mine_cols = [pc(y.get(str(yy), float("nan"))) if str(yy) in y else "-" for yy in (2017, 2018, 2019, 2020, 2021, 2022)]
    mine = (f"2020 {mine_cols[3]} 2021 {mine_cols[4]} final {S['final']:.3f} dd {pc(S['dd'])} entered {c['entered']} "
            f"skip_room {c['skipped_no_room']} skip_stock {c['skipped_stock_limit']}")
    pr = (f"2020 {p[8]} 2021 {p[9]} final {p[11]} dd {p[12]} entered {p[16]} skip_room {p[18]} skip_stock {p[19]}")
    ok = (mine_cols[3] == p[8] and mine_cols[4] == p[9] and f"{S['final']:.3f}" == p[11] and pc(S["dd"]) == p[12]
          and str(c["entered"]) == p[16] and str(c["skipped_no_room"]) == p[18] and str(c["skipped_stock_limit"]) == p[19]
          and S["open_left"] == 0)
    rec(f"account {v} (2020 / 2021 / final / dd / entered / skipped)", pr, mine, ok)
    print(" ", v, "|", pr, "|", mine, "|", "OK" if ok else "MISMATCH")
    # the rest of the printed row
    rest_m = (f"2017 {mine_cols[0]} 2018 {mine_cols[1]} 2019 {mine_cols[2]} 2022 {mine_cols[5]} offered {len(tr)} "
              f"1%/0.5% {c['risk_0.01']} / {c['risk_0.005']} trimmed {c['trimmed_stock_limit']} capbound {c['cap_bound']} "
              f"maxopen {S['max_open']} maxgross {pc(S['max_gross'])} mincash {S['min_cash']:+.3f}")
    rest_p = (f"2017 {p[5]} 2018 {p[6]} 2019 {p[7]} 2022 {p[10]} offered {p[13]} 1%/0.5% {p[17]} trimmed {p[20]} capbound {p[21]} "
              f"maxopen {p[22]} maxgross {p[23]} mincash {p[24]}")
    ok2 = (mine_cols == [p[5], p[6], p[7], p[8], p[9], p[10]] and str(len(tr)) == p[13] and
           f"{c['risk_0.01']} / {c['risk_0.005']}" == p[17] and str(c["trimmed_stock_limit"]) == p[20] and str(c["cap_bound"]) == p[21]
           and str(S["max_open"]) == p[22] and pc(S["max_gross"]) == p[23] and f"{S['min_cash']:+.3f}" == p[24])
    rec(f"account {v} (other printed columns)", rest_p, rest_m, ok2)
    print("     rest |", rest_p, "|", rest_m, "|", "OK" if ok2 else "MISMATCH")
    a_ = ah[ah.variant == v]
    stored = dict(zip(a_.date, a_.equity))
    common = [d for d in stored if d in S["curve"]]
    mx = max(abs(stored[d] - S["curve"][d]) for d in common)
    okc = len(common) == len(stored) and mx < 2e-6   # stored legs are printed to 6 decimals: ~1e-7 noise (recount_exec used 1e-6)
    rec(f"{v} daily curve vs stored account_his.tsv ({len(stored)} days)", f"{len(stored)} days, last {a_.equity.iloc[-1]:.6f}",
        f"{len(common)} days matched, max |diff| {mx:.1e}, last {S['final']:.6f}", okc)
    print(f"     daily curve: {len(common)}/{len(stored)} days, max |diff| {mx:.1e}")

# ------------------------------------------------------------------ (2) band
ctl = EV[EV.is_ctl == "1"]; hisE = EV[EV.is_his == "1"]
his_by_date = collections.Counter(hisE.E)
ctl_by_date = collections.defaultdict(list)
for tk, E in sorted(zip(ctl.ticker, ctl.E)): ctl_by_date[E].append((tk, E))
assert sum(len(v) for v in ctl_by_date.values()) == 23188
rng = np.random.default_rng([SEED, zlib.crc32(BAND_KEY.encode())])
draws = []
for _ in range(DRAWS):
    out = []
    for d in sorted(his_by_date):
        k = his_by_date[d]; pool = ctl_by_date.get(d, [])
        if len(pool) <= k: out.extend(pool); continue
        pick = rng.choice(len(pool), size=k, replace=False)
        out.extend(pool[j] for j in sorted(pick.tolist()))
    draws.append(out)
# first read's stored band parity for B0 (cap_30 row of the first read's file is "primary"? check 'b0' via round 3's own stored band)
b3 = pd.read_csv(OUT3 + "account_band.tsv", sep="\t")
print("\n(2) BAND (200 re-derived draws)")
BANDS = {}
for v, (s, a, rof, g) in VARS.items():
    sims = []
    for ids in draws:
        trs = [sim_trade(TB[(s, a)][k]) for k in ids if k in TB[(s, a)]]
        sims.append(simulate(trs, risk_of=rof, gross=g))
    BANDS[v] = sims
    for meas, key in (("2020", "2020 return"), ("2021", "2021 return"), ("final", "final equity"), ("dd", "max drawdown (higher = WORSE)")):
        vals = np.array([(s_["yearly"].get(meas) if meas in ("2020", "2021") else s_[meas]) for s_ in sims], dtype=float)
        hv = HIS[v]["yearly"][meas] if meas in ("2020", "2021") else HIS[v][meas]
        share = float((vals >= hv).mean())
        pcts = [float(np.percentile(vals, q)) for q in (5, 50, 95)]
        p = BAND[(v, key)]
        pr = f"p5 {p[3]} p50 {p[4]} p95 {p[5]} share {p[6]}"
        mine = f"p5 {pcts[0]:+.3f} p50 {pcts[1]:+.3f} p95 {pcts[2]:+.3f} share {share*100:.1f}%"
        ok = (f"{pcts[0]:+.3f}" == p[3] and f"{pcts[1]:+.3f}" == p[4] and f"{pcts[2]:+.3f}" == p[5] and f"{share*100:.1f}%" == p[6]
              and f"{hv:+.3f}" == p[2])
        # parity against the stored band file (5 percentiles, his, share), full precision
        r1 = b3[(b3.variant == v) & (b3.measure == {"2020": "2020", "2021": "2021", "final": "final", "dd": "max_dd"}[meas])]
        ok1 = False
        if len(r1) == 1:
            r1 = r1.iloc[0]
            diffs = [abs(float(r1[c]) - float(np.percentile(vals, q))) for c, q in (("p5", 5), ("p25", 25), ("p50", 50), ("p75", 75), ("p95", 95))]
            ok1 = max(diffs) < 1e-6 and abs(float(r1.share_ge_his) - share) < 1e-12 and abs(float(r1["his"]) - hv) < 1e-6
        rec(f"band {v} {key} (his / p5 / p50 / p95 / share; + stored account_band.tsv to 1e-6)", f"his {p[2]} " + pr, f"his {hv:+.3f} " + mine + f" [stored file match {ok1}]", ok and ok1)
        print(" ", v, key, "|", pr, "|", mine, "|", "OK" if (ok and ok1) else "MISMATCH")

# ------------------------------------------------------------------ (3) fork
S = HIS["COMBINED"]; y20, y21 = S["yearly"]["2020"], S["yearly"]["2021"]
fv = np.array([s_["final"] for s_ in BANDS["COMBINED"]]); cshare = float((fv >= S["final"]).mean())
rec("FORK COMBINED 2020 / 2021 / band share", "2020 16.6%, 2021 7.9%, band share 5.0%",
    f"2020 {pc(y20)}, 2021 {pc(y21)}, band share {pc(cshare)} ({int(round(cshare*DRAWS))} of {DRAWS})",
    pc(y20) == "16.6%" and pc(y21) == "7.9%" and pc(cshare) == "5.0%")
met_years = y20 >= .5 and y21 >= .5; met_band = cshare <= .05
rec("FORK verdict", "years not met; band MET (5.0% <= 5%) -> NEXT GAPS", f"years>=50% both: {met_years}; band<=5%: {met_band} -> " + ("EXPLAINED" if met_years and met_band else "NEXT GAPS"),
    (not met_years) and met_band)
srt = np.sort(fv)[::-1]
near = [(round(float(x), 6)) for x in srt[:14]]
print("\n(3) FORK: his COMBINED final", repr(S["final"]), "| top-14 band finals:", near)
print("   draws >= his:", int((fv >= S["final"]).sum()), "| the next draw below his:", float(srt[int((fv >= S['final']).sum())]),
      "| draws within 1e-3 of his:", [round(float(x), 5) for x in fv if abs(x - S["final"]) < 1e-3])

# ------------------------------------------------------------------ (4) W3 explanation
print("\n(4) W3: his calls by QQQ state at D")
b0t = [r for r in TB[("lod", "p33_s3_t10")].values() if r.is_his == "1"]
allhis = hisE.qqq_at_D.value_counts().to_dict()
print("   all 236 calls by state:", allhis)
W = {}
for st in ("up", "mixed", "down"):
    rs = [r.realized_r for r in b0t if QQQ[(r.ticker, r.E)] == st and r.mature == "1"]
    n_f = sum(1 for r in b0t if QQQ[(r.ticker, r.E)] == st)
    W[st] = (allhis.get(st, 0), n_f, len(rs), float(np.mean(rs)), float(np.sum(rs)), 100 * float(np.mean(np.array(rs) > 0)))
    print(f"   {st:6s} calls {allhis.get(st,0):3d} | filled {n_f:3d} (mature {len(rs)}) | mean R under B0 {np.mean(rs):+.3f} | sum R {np.sum(rs):+.1f} | win {W[st][5]:.0f}%")
mx_ = sorted([(r.realized_r, r.ticker, r.E) for r in b0t if QQQ[(r.ticker, r.E)] == "mixed" and r.mature == "1"], reverse=True)
print("   mixed: top 3 trades", [(a, b, c) for a, b, c in mx_[:3]], "| mean R without the top 1:", round(float(np.mean([x[0] for x in mx_[1:]])), 3), "| without top 3:", round(float(np.mean([x[0] for x in mx_[3:]])), 3), "| winners:", sum(1 for x in mx_ if x[0] > 0), "of", len(mx_))
nonup = [r.realized_r for r in b0t if QQQ[(r.ticker, r.E)] != "up" and r.mature == "1"]
print(f"   not-up (mixed+down): filled mature {len(nonup)} mean R {np.mean(nonup):+.3f} sum R {np.sum(nonup):+.1f}")
for st in ("up", "mixed", "down"):
    pass
for v in ("B0", "W3"):
    e = pd.DataFrame(HIS[v]["ent"])
    print(f"   {v}: entered {len(e)}; equity-fraction gained by state (sum of val*return, not compounded):")
    g = e.groupby("q").agg(n=("pnl", "size"), val=("val", "mean"), pnl=("pnl", "sum"), meanR=("r", "mean"))
    print("     " + g.round(3).to_string().replace("\n", "\n     "))
    print("     by year x state pnl:", e.assign(nonup=e.q != "up").groupby(["yr", "nonup"]).pnl.sum().round(3).to_dict())
# the 2020 / 2021 split of not-up calls
nu = [r for r in b0t if QQQ[(r.ticker, r.E)] != "up"]
print("   not-up filled by year:", collections.Counter(r.E[:4] for r in nu), " up by year:", collections.Counter(r.E[:4] for r in b0t if QQQ[(r.ticker, r.E)] == "up"))
ye = {y: (np.mean([r.realized_r for r in b0t if r.E[:4] == y and QQQ[(r.ticker, r.E)] != 'up' and r.mature == '1']),
          np.mean([r.realized_r for r in b0t if r.E[:4] == y and QQQ[(r.ticker, r.E)] == 'up' and r.mature == '1'])) for y in ("2020", "2021")}
print("   mean R (not-up, up) by year:", {k: (round(a, 3), round(b, 3)) for k, (a, b) in ye.items()})
# top 10 B0 trades: state
top = sorted(b0t, key=lambda r: -r.realized_r)[:10]
print("   B0's 10 biggest winners by state:", collections.Counter(QQQ[(r.ticker, r.E)] for r in top), [(r.ticker, r.E, round(r.realized_r, 1), QQQ[(r.ticker, r.E)]) for r in top])
PRS = {}
for l in txt:
    c = cells(l)
    if len(c) > 12 and c[0] == "B0" and c[1] in ("his QQQ up at D", "his QQQ mixed at D", "his QQQ down at D"):
        PRS[c[1].split()[2]] = c
for st in ("up", "mixed", "down"):
    p_ = PRS[st]; w = W[st]
    pr = f"calls {p_[2]}, filled {p_[3]}, mature {p_[4]}, win {p_[10]}, mean R {p_[11]}"
    mine = f"calls {w[0]}, filled {w[1]}, mature {w[2]}, win {w[5]:.1f}%, mean R {w[3]:+.3f}"
    rec(f"W3: his calls with QQQ {st} at D, under B0", pr, mine,
        (str(w[0]), str(w[1]), str(w[2]), f"{w[5]:.1f}%", f"{w[3]:+.3f}") == (p_[2], p_[3], p_[4], p_[10], p_[11]))

# ------------------------------------------------------------------ table out
print("\n\nclaim | printout | yours | match")
for r in ROWS: print(" | ".join(r))
print("\nMISMATCHES:", sum(1 for r in ROWS if r[3] != "OK"), "of", len(ROWS))
