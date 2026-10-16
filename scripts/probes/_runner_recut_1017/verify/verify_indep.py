"""Independent verifier for the 2026-10-16 runner re-cut (read-only; $0; no prod).

Rebuilds the population from the gzipped captures with its OWN loader, walks the control with the
LIVE walk_arm (the pre-registered control), re-implements the control walk from scratch to recover
the resting stop at the +8 ORB-R partial, implements Frame A t20_be (orderable) and t20_entry_ref
itself, and recomputes every headline aggregate (exact sign-flip enumeration, own bootstrap).
Compares against run_rows.tsv / run_results.json. Imports from recut.py / walker_cand.py: NONE.
"""
import gzip
import itertools
import json
import statistics
import sys
from collections import Counter, defaultdict
from datetime import date, timedelta

import numpy as np

REPO = "/Users/alvinfung/apollo_the_wise"
sys.path.insert(0, REPO)
from agents.market_intelligence.live_fill_counterfactuals import walk_arm  # noqa: E402  (the control)
from agents.market_intelligence.broker.exit_logic import depth_stop_price  # noqa: E402  (live pure fn)

P = f"{REPO}/scripts/probes/_runner_recut_1017"
CAP = f"{P}/captures"
H = 40
H1_END = date(2026, 6, 30)


def D(s):
    return date.fromisoformat(s)


# ---------------- own loader ----------------
adm = json.load(gzip.open(f"{CAP}/bt_admission_result.json.gz", "rt"))
rows_u = adm["U"]["replayable"]
mb = defaultdict(list)
with gzip.open(f"{CAP}/bt_out_bars.psv.gz", "rt") as fh:
    for ln in fh:
        f = ln.rstrip("\n").split("|")
        if len(f) != 7:
            continue
        mb[(f[0], f[1])].append(dict(m=f[2], o=float(f[3]), h=float(f[4]), l=float(f[5]), c=float(f[6])))
for k in mb:
    mb[k].sort(key=lambda b: b["m"])
dly = defaultdict(dict)
with gzip.open(f"{CAP}/bt_out_daily.psv.gz", "rt") as fh:
    for ln in fh:
        f = ln.rstrip("\n").split("|")
        if len(f) != 7:
            continue
        dly[f[0]][D(f[1])] = dict(o=float(f[2]) if f[2] else None, h=float(f[3]) if f[3] else None,
                                  l=float(f[4]) if f[4] else None, c=float(f[5]))
cal = sorted({d for t in dly for d in dly[t]})

# ---------------- own trade build ----------------
acct = Counter()
trades = []
for a in rows_u:
    t, d = a["t"], D(a["d"])
    bars = mb.get((t, a["d"]), [])
    orb = [b for b in bars if b["m"] == "09:30"]
    post = [b for b in bars if b["m"] > "09:30"]
    if not orb:
        acct["no_orb"] += 1
        continue
    if not post:
        acct["no_bars_after_orb"] += 1
        continue
    oh, ol = orb[0]["h"], orb[0]["l"]
    if oh <= ol:
        acct["degenerate_orb"] += 1
        continue
    fi = None
    for i, b in enumerate(post):           # own fill rule: first 09:31-09:59 bar opening <= ORB high and reaching it
        if b["m"] > "09:59":
            break
        if b["o"] <= oh and b["h"] >= oh:
            fi = i
            break
    if fi is None:
        acct["never_triggered"] += 1
        continue
    entry, rorb = oh, oh - ol
    stop = 2 * ol - oh
    tk = dly[t]
    before = sorted(x for x in tk if x < d)
    pre20 = before[-20:]
    vals = [(tk[x]["h"] - tk[x]["l"]) / tk[x]["c"] for x in pre20 if tk[x]["h"] is not None and tk[x]["l"] is not None]
    adr = sum(vals) / len(vals) if len(vals) >= 10 else None
    prior = [tk[x]["c"] for x in before if x >= d - timedelta(days=40)]
    gi = next((i for i, x in enumerate(cal) if x > d), len(cal))
    sess = []
    for x in cal[gi:gi + H]:
        r = tk.get(x)
        sess.append((x, None if (r is None or r["h"] is None or r["l"] is None) else dict(r)))
    trades.append(dict(t=t, d=d, entry=entry, stop=stop, rorb=rorb, target=entry + 8 * rorb, be=entry + 3 * rorb,
                       day0=post, fi=fi, sess=sess, prior=prior, adr=adr, wk=d.isocalendar()[:2]))
trades.sort(key=lambda x: (x["d"], x["t"]))
acct["filled"] = len(trades)


# ---------------- control via the LIVE walk_arm ----------------
def live(tr, depth=True):
    o = walk_arm(entry=tr["entry"], stop=tr["stop"], target=tr["target"], day0_bars=tr["day0"], fill_idx=tr["fi"],
                 sessions=tr["sess"], prior_closes=tr["prior"], harvest="live_ladder", fill_day=tr["d"],
                 breakeven_at_partial=True, trail_prior_closes=True, ladder_partial=False, horizon=H,
                 breakeven_at_r=3.0, r_frame_ps=tr["rorb"], trail_mode="sma",
                 depth_exit=depth, depth_adr20_pct=tr["adr"] if depth else None)
    risk = tr["entry"] - tr["stop"]
    if o["status"] == "settled":
        return o["status"], o["pnl_per_share"] / risk
    if o["status"] == "horizon":
        return "horizon", o["mark_pnl_per_share"] / risk
    if o["status"] == "pending" and o["reason"] in ("open_walk_not_definitive", "depth_next_open_not_yet_settled"):
        sw = o["sessions_walked"]
        lc = tr["sess"][sw - 1][1]["c"] if sw >= 1 else tr["day0"][-1]["c"]
        return "data_end", (sum(e["pnl"] for e in o["exits"]) + (lc - tr["entry"]) * o["remaining"]) / risk
    return o["status"], None


# ---------------- own walker (control clone + t20 forms + control_at_close) ----------------
def my_walk(tr, mode="control"):
    """mode: control | t20_be | t20_ref | at_close. Returns dict(status, R, trigA, F, exit)."""
    E, S, T, BE, adr = tr["entry"], tr["stop"], tr["target"], tr["be"], tr["adr"]
    risk = E - S
    rem, pnl, partial, closed = 1.0, 0.0, False, False
    info = dict(trigA=None, F=None, exit=None)
    hold = None  # (F, sell_session) once a t20 form takes over

    def res(status, extra_close=None):
        p = pnl + ((extra_close - E) * rem if extra_close is not None else 0.0)
        return dict(status=status, R=p / risk if status not in ("abstain", "gap") else None, **info)

    cur = S
    day0 = tr["day0"]
    fb = day0[tr["fi"]]
    if fb["l"] <= S:
        if fb["h"] >= T:
            return res("abstain")
        if fb["c"] < S:
            pnl += (S - E) * rem; rem = 0; closed = True; info["exit"] = ("d0", "stop", S)
        else:
            return res("abstain")
    if not closed and fb["h"] >= T and fb["c"] >= S:
        q = rem / 3; pnl += (T - E) * q; rem -= q; partial = True; cur = max(cur, E); info["trigA"] = 0
    if not closed and fb["h"] >= BE:
        cur = max(cur, E)
    for b in day0[tr["fi"] + 1:]:
        if closed:
            break
        hs = b["l"] <= cur
        ht = (not partial) and b["h"] >= T
        if hs and ht:
            return res("abstain")
        if cur < E and b["h"] >= BE and b["l"] <= E:
            return res("abstain")
        if b["h"] >= BE:
            cur = max(cur, E)
        if hs:
            px = b["o"] if b["o"] < cur else cur
            pnl += (px - E) * rem; rem = 0; closed = True; info["exit"] = ("d0", "stop", px)
        elif ht:
            q = rem / 3; pnl += (T - E) * q; rem -= q; partial = True; cur = max(cur, E); info["trigA"] = 0
    if info["trigA"] == 0 and mode in ("t20_be", "t20_ref"):
        info["F"] = max(cur, E) if mode == "t20_be" else E   # day-0 trigger: the day-0 remainder already rests at entry
    if closed:
        return res("settled")
    if mode in ("t20_be", "t20_ref") and info["trigA"] == 0:
        info["F"] = cur if mode == "t20_be" else E
        hold = (info["F"], 20)
    resting, be_act = cur, partial
    held = []
    last_c = day0[-1]["c"]
    sw = 0
    sess = tr["sess"]
    for idx, (d, b) in enumerate(sess, start=1):
        if b is None:
            return res("gap")
        sw = idx; last_c = b["c"]
        if hold is not None:                      # ---- the t20 hold: stop F rests, no line
            F, sell = hold
            if b["l"] <= F:
                px = b["o"] if (b["o"] is not None and b["o"] < F) else F
                pnl += (px - E) * rem; rem = 0; info["exit"] = (idx, "stop_F", px); return res("settled")
            if idx == sell:
                pnl += (b["c"] - E) * rem; rem = 0; info["exit"] = (idx, "time_close", b["c"]); return res("settled")
            continue
        if resting < E and b["h"] >= BE and b["l"] <= E:
            return res("abstain")
        if b["h"] >= BE:
            resting = max(resting, E)
        ht = (not partial) and b["h"] >= T
        if ht and b["l"] <= resting:
            return res("abstain")
        if ht:
            q = rem / 3; pnl += (T - E) * q; rem -= q; partial = True; resting = max(resting, E); be_act = True
            info["trigA"] = idx
            if mode in ("t20_be", "t20_ref"):
                info["F"] = resting if mode == "t20_be" else E
                hold = (info["F"], idx + 20)
                assert b["l"] > info["F"] or mode == "t20_ref"
                if b["l"] <= info["F"]:
                    px = b["o"] if b["o"] < info["F"] else info["F"]
                    pnl += (px - E) * rem; rem = 0; info["exit"] = (idx, "stop_F", px); return res("settled")
                continue                           # the candidate's close decision replaces the control's
        held.append(b["c"])
        if b["l"] <= resting:
            px = b["o"] if (b["o"] is not None and b["o"] < resting) else resting
            pnl += (px - E) * rem; rem = 0; info["exit"] = (idx, "stop", px); return res("settled")
        tc = tr["prior"] + held
        s10 = sum(tc[-10:]) / 10 if len(tc) >= 10 else None
        s20 = sum(tc[-20:]) / 20 if len(tc) >= 20 else None
        line = (s10 if s10 > s20 else s20) if s20 is not None else s10
        eff = resting
        if line and line > eff:
            eff = line
        if be_act and E > eff:
            eff = E
        if b["c"] < eff:
            if mode == "at_close":
                pnl += (b["c"] - E) * rem; rem = 0; info["exit"] = (idx, "close_below@close", b["c"]); return res("settled")
            nxt = sess[idx] if idx < len(sess) else None
            if nxt is None and idx >= H:
                return res("horizon", b["c"])
            if nxt is None:
                return res("data_end", b["c"])
            if nxt[1] is None or nxt[1].get("o") is None:
                return res("gap")
            px = nxt[1]["o"]
            pnl += (px - E) * rem; rem = 0; info["exit"] = (idx + 1, "close_below@next_open", px, b["c"])
            return res("settled")
        resting = max(resting, depth_stop_price(line=eff, hard_stop=S, entry_price=E, breakeven_active=be_act,
                                                adr20_pct=adr))
    if sw >= H:
        return res("horizon", last_c)
    return res("data_end", last_c)


# ---------------- run ----------------
out = []
pr = out.append
pr(f"population (own loader): {len(rows_u)} rows on {len({r['t'] for r in rows_u})} tickers; {dict(acct)}")
pr(f"entry dates: {min(t['d'] for t in trades)} -> {max(t['d'] for t in trades)}; ADR20 None on "
   f"{sum(1 for t in trades if t['adr'] is None)} of {len(trades)}")

tsv = {}
with open(f"{P}/run_rows.tsv") as fh:
    hdr = fh.readline().rstrip("\n").split("\t")
    for ln in fh:
        f = ln.rstrip("\n").split("\t")
        tsv[(f[0], f[1])] = dict(zip(hdr, f))
pr(f"run_rows.tsv rows: {len(tsv)}; my filled set == tsv set: {set((t['t'], t['d'].isoformat()) for t in trades) == set(tsv)}")


def tv(k, col):
    v = tsv[k][col]
    return None if v in ("", "None", "nan") else float(v)


ctrl, mine_ctrl, t20, ref, atc, erad = {}, {}, {}, {}, {}, {}
mism = []
for tr in trades:
    k = (tr["t"], tr["d"].isoformat())
    ctrl[k] = live(tr)
    erad[k] = live(tr, depth=False)
    mine_ctrl[k] = my_walk(tr, "control")
    t20[k] = my_walk(tr, "t20_be")
    ref[k] = my_walk(tr, "t20_ref")
    atc[k] = my_walk(tr, "at_close")
    a, b = ctrl[k], mine_ctrl[k]
    if a[0] != b["status"] or (a[1] is None) != (b["R"] is None) or (a[1] is not None and abs(a[1] - b["R"]) > 1e-9):
        mism.append((k, a, b["status"], b["R"]))
pr(f"live walk_arm control statuses: {dict(Counter(v[0] for v in ctrl.values()))}")
pr(f"own control clone == live walk_arm (status + R to 1e-9) on {len(trades) - len(mism)} of {len(trades)}; mismatches {mism[:5]}")

# compare live control R to tsv
bad = [(k, ctrl[k][1], tv(k, "control")) for k in ctrl
       if (ctrl[k][1] is None) != (tv(k, "control") is None)
       or (ctrl[k][1] is not None and abs(ctrl[k][1] - tv(k, "control")) > 6e-5)]
pr(f"live control R vs run_rows.tsv control column (4dp): {len(ctrl) - len(bad)} of {len(ctrl)} agree; disagreements {bad[:5]}")


def cmp_col(mine, col, label):
    bad = [(k, (mine[k]["R"]), tv(k, col)) for k in mine
           if (mine[k]["R"] is None) != (tv(k, col) is None)
           or (mine[k]["R"] is not None and abs(mine[k]["R"] - tv(k, col)) > 6e-5)]
    pr(f"own {label} vs run_rows.tsv '{col}': {len(mine) - len(bad)} of {len(mine)} agree; disagreements {bad[:6]}")


cmp_col(t20, "A|t20_be", "t20_be (orderable, F = resting stop at the partial)")
cmp_col(ref, "t20_entry_ref", "t20_entry_ref (F reset to entry)")
cmp_col(atc, "control_at_close", "control_at_close")
bad = [(k, erad[k][1], tv(k, "era_d")) for k in erad if (erad[k][1] is None) != (tv(k, "era_d") is None)
       or (erad[k][1] is not None and abs(erad[k][1] - tv(k, "era_d")) > 6e-5)]
pr(f"live era_d (depth_exit=False) vs run_rows.tsv 'era_d': {len(erad) - len(bad)} of {len(erad)} agree; disagreements {bad[:5]}")

# engaged set + F
scored = [k for k in ctrl if ctrl[k][1] is not None]
eng = [k for k in scored if mine_ctrl[k]["trigA"] is not None]
risk = {(tr["t"], tr["d"].isoformat()): tr["entry"] - tr["stop"] for tr in trades}
ent = {(tr["t"], tr["d"].isoformat()): tr["entry"] for tr in trades}
Fs = {k: (t20[k]["F"] - ent[k]) / risk[k] for k in eng}
pr(f"scored n={len(scored)}; Frame A engaged (control reached +8 ORB-R partial) = {len(eng)}; "
   f"day-0 triggers {sum(1 for k in eng if mine_ctrl[k]['trigA'] == 0)}")
pr(f"F above entry on {sum(1 for v in Fs.values() if v > 1e-9)} of {len(Fs)}: "
   f"{[(k, round(v, 3)) for k, v in Fs.items() if v > 1e-9]}; median F {statistics.median(Fs.values()):.3f}R")
pr(f"tsv trigA_idx non-empty: {sum(1 for k in tsv if tsv[k]['trigA_idx'] not in ('', 'None'))}; "
   f"trigger index agreement: {sum(1 for k in eng if tsv[k]['trigA_idx'] not in ('', 'None') and int(tsv[k]['trigA_idx']) == mine_ctrl[k]['trigA'])} of {len(eng)}")


# ---------------- aggregates from my own vectors ----------------
def agg(arm, name):
    ks = [k for k in scored if arm[k] is not None]
    R = np.array([arm[k] for k in ks]); C = np.array([ctrl[k][1] for k in ks])
    dl = R - C
    differ = [ks[i] for i in range(len(ks)) if abs(dl[i]) > 0.005]
    wk = {k: D(k[1]).isocalendar()[:2] for k in ks}
    pos = sorted([(dl[i], ks[i]) for i in range(len(ks)) if dl[i] > 1e-12], reverse=True)
    h1 = sum(dl[i] for i in range(len(ks)) if D(ks[i][1]) <= H1_END)
    h2 = sum(dl[i] for i in range(len(ks)) if D(ks[i][1]) > H1_END)
    n1 = sum(1 for k in ks if D(k[1]) <= H1_END)
    blocks = defaultdict(lambda: [0.0, 0])
    for i, k in enumerate(ks):
        blocks[wk[k]][0] += dl[i]; blocks[wk[k]][1] += 1
    bs = np.array([v[0] for v in blocks.values()]); bn = np.array([v[1] for v in blocks.values()])
    nz = [x for x in bs if abs(x) > 1e-12]
    obs = abs(sum(bs))
    hits = sum(1 for sg in itertools.product((1, -1), repeat=len(nz)) if abs(sum(s * x for s, x in zip(sg, nz))) >= obs - 1e-12)
    p_exact = hits / 2 ** len(nz)
    rng = np.random.default_rng(20261016)
    idx = rng.integers(0, len(bs), size=(10000, len(bs)))
    boot = bs[idx].sum(1) / bn[idx].sum(1)
    tail = lambda v: v >= 4.0 - 1e-9  # noqa: E731
    lost = [k for i, k in enumerate(ks) if tail(C[i]) and not tail(R[i])]
    gained = [k for i, k in enumerate(ks) if tail(R[i]) and not tail(C[i])]
    srt = np.sort(R)[::-1]
    return dict(name=name, n=len(ks), differ=len(differ), differ_weeks=len({wk[k] for k in differ}), blocks=len(bs),
                nz_blocks=len(nz), total=R.sum(), ctrl_total=C.sum(), delta=dl.sum(), delta_ex_top2=dl.sum() - sum(x for x, _ in pos[:2]),
                top2=[(k, round(x, 2)) for x, k in pos[:2]], drop_best2=R.sum() - srt[:2].sum(), ctrl_drop_best2=C.sum() - np.sort(C)[::-1][:2].sum(),
                h1=h1, h2=h2, n1=n1, n2=len(ks) - n1, p_exact=p_exact, boot=(np.percentile(boot, 2.5), np.percentile(boot, 97.5)),
                n4=int(sum(tail(x) for x in R)), n4c=int(sum(tail(x) for x in C)), n15=int(sum(x >= 1.5 - 1e-9 for x in R)),
                n15c=int(sum(x >= 1.5 - 1e-9 for x in C)), lost=lost, gained=gained, median=float(np.median(R)),
                cmedian=float(np.median(C)), win=float(np.mean(R > 0)), p90=float(np.percentile(R, 90)),
                cp90=float(np.percentile(C, 90)), mean_delta=dl.mean(),
                ex_baba=dl.sum() - sum(dl[i] for i, k in enumerate(ks) if k == ("BABA", "2026-07-08")),
                open_end=None)


res_json = json.load(open(f"{P}/run_results.json"))
for name, arm in (("PRIMARY A t20_be", {k: t20[k]["R"] for k in scored}),
                  ("REF t20_entry_ref", {k: ref[k]["R"] for k in scored}),
                  ("REF control_at_close", {k: atc[k]["R"] for k in scored}),
                  ("REF era_d", {k: erad[k][1] for k in scored})):
    m = agg(arm, name)
    pr(f"\n== {name} (own aggregates) ==")
    for kk in ("n", "differ", "differ_weeks", "blocks", "nz_blocks", "total", "ctrl_total", "delta", "mean_delta", "delta_ex_top2",
               "top2", "ex_baba", "drop_best2", "ctrl_drop_best2", "h1", "n1", "h2", "n2", "p_exact", "boot", "n4", "n4c",
               "n15", "n15c", "lost", "gained", "median", "cmedian", "win", "p90", "cp90"):
        v = m[kk]
        pr(f"  {kk:<16} {round(v, 4) if isinstance(v, float) else v}")

# bar, applied to my own numbers
m = agg({k: t20[k]["R"] for k in scored}, "primary")
P1 = m["differ"] >= 10 and m["differ_weeks"] >= 6
P2 = m["delta"] > 0 and m["p_exact"] < 0.05
P3 = m["delta_ex_top2"] > 0
P4 = m["h1"] > 0 and m["h2"] > 0
P5 = m["n4"] >= m["n4c"]
word = "TOO FEW" if not P1 else ("PROPOSAL" if (P2 and P3 and P4 and P5) else "STANDS")
pr(f"\nBAR on own numbers: P1 {P1} P2 {P2} P3 {P3} P4 {P4} P5 {P5} -> {word}")

# open at data end counts
pr(f"open at data end: control {sum(1 for k in scored if ctrl[k][0] == 'data_end')}, "
   f"primary {sum(1 for k in scored if t20[k]['status'] == 'data_end')}; horizon control "
   f"{sum(1 for k in scored if ctrl[k][0] == 'horizon')}, primary {sum(1 for k in scored if t20[k]['status'] == 'horizon')}")
marks = [(k, round(ctrl[k][1], 2)) for k in scored if ctrl[k][0] == "data_end"]
pr(f"control data-end marks: {marks}; sum {sum(v for _, v in marks):+.2f}R")

# per-trade engaged table
pr("\nengaged 29 (own): key | trigA | F(R) | control R | t20_be R | t20 exit | delta")
for k in eng:
    pr(f"  {k[0]:<6} {k[1]} trig={mine_ctrl[k]['trigA']:<3} F={Fs[k]:+.3f} ctrl={ctrl[k][1]:+.4f} t20={t20[k]['R']:+.4f} "
       f"exit={t20[k]['exit']} ctrl_exit={mine_ctrl[k]['exit']} d={t20[k]['R'] - ctrl[k][1]:+.4f} st={ctrl[k][0]}/{t20[k]['status']}")

# BABA hand trace from raw bars
tr = next(x for x in trades if x["t"] == "BABA" and x["d"] == date(2026, 7, 8))
pr(f"\nBABA 2026-07-08 raw: entry {tr['entry']} ORB-R {tr['rorb']:.4f} stop {tr['stop']:.4f} target {tr['target']:.4f} "
   f"+3R {tr['be']:.4f} ADR20 {tr['adr']:.5f}")
for i, (d, b) in enumerate(tr["sess"], 1):
    if b is None:
        continue
    pr(f"  s{i:<2} {d} o {b['o']:.2f} h {b['h']:.2f} l {b['l']:.2f} c {b['c']:.2f}")
pr(f"  control: {mine_ctrl[('BABA', '2026-07-08')]}")
pr(f"  t20_be : {t20[('BABA', '2026-07-08')]}")
print("\n".join(out))
