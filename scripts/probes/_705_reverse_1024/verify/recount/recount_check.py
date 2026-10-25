#!/usr/bin/env python3
"""#705 reverse 01 — INDEPENDENT RECOUNT of the one `--check` run (01_rev_check.txt).

Read-only. Recomputes the check's populations and numbers from the raw inputs (entries.tsv, snapshots.tsv, the calendar pickle, the
daily exports, the raw closes, the minute trees, the type tables) and from the check's side outputs (check_*.tsv), with its OWN code.

What is imported, and why (everything else is this file's own code):
  - 01_rev_frozen_e908253f7405.py, as a module, for PATHS and DATA LOADERS ONLY: FILES / MINUTES / CUT_B, `load_done_all`,
    `read_minutes` (the minute trees). No stage function of it (no load_buys / build_sets / pick_features / pool_rows_for_days /
    enter_* / stop_* / held_through / exit_* / accounts_for) is called.
  - through it, the frozen holdings replay's loaders: `rp.load_daily_subset`, `R.load_raw_close`, `R.load_breaks`, `H.unify_calendars`,
    `SEC.resolve_type` / `load_small` / `load_sic`; and, for the EXIT accounts only, the FROZEN account machinery `rp.Trade`,
    `rp.simulate` (cap_30), `H.to_unified`, and for the `ours` account the frozen speed trail `cb.walk_arms` + `rp.make_trade` +
    `cb.forward_window` + `rp.cut_at_break`. Every account number is labelled REUSED-SIM in the table: the trade LISTS for `chosen` and
    `his` are built here; the simulator and the speed-trail walk are the pinned code.
Nothing is written outside verify/recount/ (the printout and a cache of the rebuilt SELECT pool).
"""
from __future__ import annotations

import bisect
import gzip
import importlib.util
import math
import os
import pickle
import sys
import time
import zlib
from collections import Counter, defaultdict
from datetime import date
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pandas as pd
from numpy.lib.stride_tricks import sliding_window_view as swv

HERE = os.path.dirname(os.path.abspath(__file__))
RD = os.path.abspath(os.path.join(HERE, "..", ".."))                       # scripts/probes/_705_reverse_1024
REPO = os.path.abspath(os.path.join(RD, "..", "..", ".."))
FROZEN = os.path.join(RD, "01_rev_frozen_e908253f7405.py")
CACHE = os.path.join(HERE, "cache")
OUT_TXT = os.path.join(HERE, "recount_check.txt")
CHECK_TXT = os.path.join(RD, "01_rev_check.txt")

spec = importlib.util.spec_from_file_location("_rev_frozen_loaders", FROZEN)
REV = importlib.util.module_from_spec(spec)
sys.modules["_rev_frozen_loaders"] = REV
spec.loader.exec_module(REV)
H, rp, R, cb, SEC = REV.H, REV.rp, REV.R, REV.cb, REV.SEC
FILES, CUT_B = REV.FILES, REV.CUT_B
OUT_DIR = REV.OUT_DIR

# ---- the registration's constants, re-typed here from the doc (not read from the module) -----------------------------------------------
FIT_WIN = ("2020-01-27", "2020-12-31")
CHECK_WIN = ("2021-01-04", "2022-06-14")
A_LAST = "2022-03-31"            # ENTER / STOP / EXIT era by buy day
A_EXPORT_LAST = "2022-06-30"     # SELECT era A through its export end
SETUPS = ("breakout", "EP", "both")
ADMIT = {"CS", "ADRC", ""}
OVERRIDE = {"LAZR": "CS"}
HORIZON = 120
SLIP_IN = 0.001
CHOSEN_SEL = [[("F3", "<=", 233.0), ("F9", ">=", -0.05785387226911948), ("F10", ">=", 0.0425632647101688)]]
CHOSEN_EXIT = [[("X7", "<=", 0.0)], [("X1", "<=", -0.5), ("X4", "==", 1)], [("X2", "<=", 0.0), ("X5", ">=", 3)]]

LINES = []


def say(s=""):
    print(s, flush=True)
    LINES.append(s)


def pct(x, nd=1):
    return "-" if x is None or not np.isfinite(x) else f"{100 * x:.{nd}f}%"


def hhmm(c):
    if not c:
        return None
    h_, m_ = c.split(":")
    return int(h_) * 60 + int(m_) - 570


# =====================================================================================================================================
# 0. inputs and populations (own derivation from entries.tsv / snapshots.tsv)
# =====================================================================================================================================
T0 = time.time()
say("# #705 REVERSE 01 — INDEPENDENT RECOUNT of the one check run (01_rev_check.txt)")
say(f"# module for paths / loaders only: {os.path.basename(FROZEN)}; nothing of 2025-26 opened; local only")
ent = pd.read_csv(FILES["entries"], sep="\t", dtype=str, keep_default_na=False)
sn = pd.read_csv(FILES["snapshots"], sep="\t", dtype=str, keep_default_na=False)
with gzip.open(FILES["calendar_cache"], "rb") as fh:
    cal_all, _sig = pickle.load(fh)
CAL = [d for d in cal_all if d <= CUT_B]
CI = {d: i for i, d in enumerate(CAL)}
small, sic = SEC.load_small(Path(FILES["small_pulls"])), SEC.load_sic(Path(FILES["sic"]))
say(f"- entries {len(ent):,}, snapshots {len(sn):,}, calendar {CAL[0]}..{CAL[-1]} ({len(CAL):,} sessions)")

snf = sn.set_index("frame_id")
B = []
for r in ent.to_dict("records"):
    initial = r["initial"] == "True"
    dated = r["setup"] in SETUPS
    E = r["E"] if dated else r["lo"]
    b = SimpleNamespace(eid=int(r["eid"]), sym=r["sym"], sym_a=r["sym_a"], setup=r["setup"], dated=dated, E=E, lo=r["lo"], hi=r["hi"],
                        wl=int(r["window_len"] or 0), inverted=r["inverted"] == "True", flicker=r["flicker"] == "True", initial=initial,
                        ur=r["undated_reason"], has_bars=r["has_bars"] == "True", decides=r["decides"] == "True",
                        exit_lo=r["exit_lo"], exit_hi=r["exit_hi"], tl_era=r["era"],
                        pivot=(float(r["pivot"]) if (r["setup"] in ("breakout", "both") and r["pivot"]) else
                               float(r["ep_prev_close"]) if (r["setup"] == "EP" and r["ep_prev_close"]) else None),
                        adr_stored=float(r["adr20"]) if (r["setup"] in ("breakout", "both") and r["adr20"]) else None,
                        first_frame=r["first_frame"], prev_full_frame=r["prev_full_frame"])
    b.noev = b.setup == "undated" and b.ur == "no_event_in_window"
    b.nc = b.ur == "never_candidate"
    key = b.sym_a if (E and E <= A_LAST) else b.sym
    t_ = OVERRIDE.get(key) or SEC.resolve_type(key, small, sic)[0]
    b.sec_type, b.type_ok = t_, t_ in ADMIT
    # the panel clock on E (first sighting frame on E not pre-market; last full frame without the name on E not after the close)
    b.first_clock = b.flat_clock = ""
    b.p_ctx = b.f_ctx = ""
    if not initial and E:
        if b.first_frame in snf.index:
            f = snf.loc[b.first_frame]
            b.f_ctx = f["ctx"]
            if f["date"] == E and f["ctx"] != "pre":
                b.first_clock = f["clock"]
        if b.prev_full_frame and b.prev_full_frame in snf.index:
            p_ = snf.loc[b.prev_full_frame]
            b.p_ctx = p_["ctx"]
            if p_["date"] == E and p_["ctx"] != "closed":
                b.flat_clock = p_["clock"]
    b.in_bracket = bool(b.first_clock) and bool(b.flat_clock) and b.p_ctx == "in"
    b.Ei = CI.get(E, -1)
    b.exit_lo_i, b.exit_hi_i = CI.get(b.exit_lo, -1), CI.get(b.exit_hi, -1)
    B.append(b)

# same-day re-buy (the holdings F4 rule, re-implemented): a later entry (eid order) of the same bar-file name, same buy day, same kind
first_key = {}
for b in sorted(B, key=lambda x: x.eid):
    b.sdr = False
    if b.initial or not b.has_bars:
        continue
    era = b.tl_era if (b.dated and b.tl_era) else ("A" if b.E <= A_LAST else "B")
    k = (era, b.sym_a if era == "A" else b.sym, b.E, b.setup == "undated")
    if k in first_key:
        b.sdr = True
    else:
        first_key[k] = b.eid
NI = [b for b in B if not b.initial]
inw = lambda bs, w: [b for b in bs if w[0] <= b.E <= w[1]]                       # noqa: E731
gate = lambda bs: [b for b in bs if b.type_ok and not b.inverted and not b.sdr]   # noqa: E731
ex_nf = [b for b in NI if b.noev and b.wl == 1 and not b.flicker]
ex_all = [b for b in NI if b.noev and b.wl == 1]
nc_ex = [b for b in NI if b.nc and b.wl == 1 and not b.flicker and b.type_ok and not b.inverted and not b.sdr]
P = {}
P["sel_chk"] = gate(inw(ex_nf, CHECK_WIN))
P["sel_chk_nc"] = inw(nc_ex, CHECK_WIN)
P["sel_fit"] = gate(inw(ex_nf, FIT_WIN))
P["sel_fit_nc"] = inw(nc_ex, FIT_WIN)
P["und_chk"] = gate(inw(ex_all, CHECK_WIN))
P["und_fit"] = gate(inw(ex_all, FIT_WIN))
dec_used = gate([b for b in NI if b.decides])
P["dated_chk"] = inw(dec_used, CHECK_WIN)
P["ent_chk_dated"] = [b for b in P["dated_chk"] if b.in_bracket]
P["ent_chk_und"] = [b for b in P["sel_chk"] if b.in_bracket]
P["sel_chk_flick"] = gate([b for b in inw(ex_all, CHECK_WIN) if b.flicker])
# §10: buy day inside a dated trade's 121-session path on the same panel name
paths = defaultdict(list)
for d in NI:
    if d.dated and d.Ei >= 0:
        paths[d.sym].append((d.Ei, d.Ei + HORIZON, d.eid))
for b in NI:
    b.in_dated_path = any(lo <= b.Ei <= hi and eid != b.eid for lo, hi, eid in paths.get(b.sym, ()))
BYEID = {b.eid: b for b in B}

say("\n## 0. POPULATIONS (own derivation) vs the registration (§2b / §6 / §7 / §8)")
REG = {"sel_chk": 145, "sel_chk_nc": 15, "sel_fit": 188, "und_chk": 226, "und_fit": 304, "dated_chk": 111, "ent_chk_dated": 20, "ent_chk_und": 44}
POPROWS = []
for k, v in REG.items():
    n = len(P[k])
    POPROWS.append((k, v, n))
    say(f"- {k}: registration {v} | recount {n} -> {'MATCH' if n == v else 'MISMATCH'}")
say(f"- und_chk non-flicker {sum(1 for b in P['und_chk'] if not b.flicker)} (registration 145); untouched by a dated path {sum(1 for b in P['und_chk'] if not b.in_dated_path)} (registration 161)")
chk_all_eids = {b.eid for k in ("sel_chk", "sel_chk_nc", "und_chk", "dated_chk") for b in P[k]}
assert all(CHECK_WIN[0] <= BYEID[e].E <= CHECK_WIN[1] for e in chk_all_eids)

# side outputs: eid sets
SO = {f: pd.read_csv(f"{OUT_DIR}/{f}.tsv", sep="\t", dtype=str, keep_default_na=False) for f in
      ("check_select_buys", "check_select_flickers", "check_select_other_level", "check_stop_trades", "check_exit_trades")}
FIT = {f: pd.read_csv(f"{OUT_DIR}/{f}.tsv", sep="\t", dtype=str, keep_default_na=False, usecols=["eid"]) for f in
       ("select_fit_buys", "enter_fit_trades", "stop_fit_trades", "exit_fit_trades")}
so_sel = set(SO["check_select_buys"]["eid"].astype(int))
so_stop = SO["check_stop_trades"]
so_stop_u = set(so_stop[so_stop["dated"] == "False"]["eid"].astype(int))
so_stop_d = set(so_stop[so_stop["dated"] == "True"]["eid"].astype(int))
so_exit = set(SO["check_exit_trades"]["eid"].astype(int))
my_sel = {b.eid for b in P["sel_chk"] + P["sel_chk_nc"]}
my_und = {b.eid for b in P["und_chk"]}
my_dat = {b.eid for b in P["dated_chk"]}
fit_eids = {f: set(d["eid"].astype(int)) for f, d in FIT.items()}
all_fit = set().union(*fit_eids.values())
und_2122_in_fit = {e for e in all_fit if not BYEID[e].dated and CHECK_WIN[0] <= BYEID[e].E <= CHECK_WIN[1]}
say(f"- check_select_buys eids {len(so_sel)} ⊆ recount SELECT check set {len(my_sel)}: {so_sel <= my_sel}")
say(f"- check_stop_trades undated eids {len(so_stop_u)} ⊆ recount undated check set {len(my_und)}: {so_stop_u <= my_und}; dated {len(so_stop_d)} ⊆ {len(my_dat)}: {so_stop_d <= my_dat}")
say(f"- check_exit_trades eids {len(so_exit)} == stop undated eids: {so_exit == so_stop_u}")
say(f"- fit-set trades inside the check side outputs: SELECT {len(so_sel & fit_eids['select_fit_buys'])}, STOP/EXIT undated "
    f"{len(so_stop_u & all_fit)}; any undated 2021-22 eid in ANY fit file: {len(und_2122_in_fit)}; check buys with E outside the check window: 0")
say(f"- the dated 2021-22 eids found in exit_fit_trades.tsv: {len(my_dat & fit_eids['exit_fit_trades'])} of {len(my_dat)} (registered in-sample, §10 — expected, beside only)")
POP_OK = (so_sel <= my_sel and so_stop_u <= my_und and so_stop_d <= my_dat and so_exit == so_stop_u and not und_2122_in_fit
          and not (so_sel & all_fit) and not (so_stop_u & all_fit) and all(n == v for _k, v, n in POPROWS))

# =====================================================================================================================================
# bars
# =====================================================================================================================================
t0 = time.time()
DA, infoA = rp.load_daily_subset(FILES["export_A"], keep=None)
keepB = {b.sym for b in NI if b.E and b.E > A_LAST and b.E <= CHECK_WIN[1]} | {"QQQ", "SPY"}
DB, infoB = rp.load_daily_subset(FILES["export_B"], keep=keepB, cut=CUT_B)
raw_flat = R.load_raw_close(Path(FILES["raw_close_A"]), DA)
say(f"\n- exports: era A {infoA['rows_kept']:,} rows ({len(DA.tickers):,} tickers), era B {infoB['rows_kept']:,} rows kept ({len(DB.tickers)} tickers, cut {CUT_B}); raw closes aligned {len(raw_flat):,} ({time.time() - t0:.0f}s)")
A_CI = {d.isoformat(): i for i, d in enumerate(DA.cal)}
B_CI = {d.isoformat(): i for i, d in enumerate(DB.cal)}
assert [d.isoformat() for d in DA.cal] == CAL[:len(DA.cal)], "era A export calendar is not the pickle calendar's prefix"
cal_u, map_b = H.unify_calendars(DA.cal, DB.cal)
assert [d.isoformat() for d in cal_u] == CAL
GUARDS = {"A": R.load_breaks(FILES["guard_A"]), "B": R.load_breaks(FILES["guard_B"])}


def arrays(D, tk):
    tid = D.tid.get(tk)
    if tid is None:
        return None
    a, z = int(D.start[tid]), int(D.stop[tid])
    return dict(o=np.asarray(D.o[a:z], float), h=np.asarray(D.h[a:z], float), l=np.asarray(D.l[a:z], float), c=np.asarray(D.c[a:z], float),
                v=np.asarray(D.v[a:z], float), ci=np.asarray(D.ci[a:z], np.int64), a=a, z=z, tid=tid)


def qqq_state_map(D):
    q = arrays(D, "QQQ")
    out = {}
    for k in range(len(q["c"])):
        if k < 19:
            out[int(q["ci"][k])] = ""
            continue
        c = q["c"][k]
        s10, s20 = q["c"][k - 9:k + 1].mean(), q["c"][k - 19:k + 1].mean()
        out[int(q["ci"][k])] = "up" if (c > s10 and c > s20) else "down" if (c < s10 and c < s20) else "mixed"
    return out, q


QST_A, QQQ_A = qqq_state_map(DA)


def win_reduce(x, P_, end_off, w, fn):
    """fn over x[p-end_off-w+1 .. p-end_off] for each p in P_ (NaN where the window starts before 0)."""
    out = np.full(len(P_), np.nan)
    q = P_ - end_off
    ok = (q - w + 1 >= 0) & (q < len(x))
    if ok.any() and len(x) >= w:
        W = swv(x, w)
        out[ok] = fn(W[q[ok] - w + 1], axis=1)
    return out


def shift_ratio(c, P_, k):
    out = np.full(len(P_), np.nan)
    ok = P_ - k >= 0
    out[ok] = c[P_[ok]] / c[P_[ok] - k] - 1.0
    return out


def sel_feats(A, P_, raw, qst):
    """F1..F14, ret63 / ret21, F17 and the floor quantities at prior-session bar indices P_ (own implementation of §5b)."""
    o, h, l, c, v, ci = A["o"], A["h"], A["l"], A["c"], A["v"], A["ci"]
    P_ = np.asarray(P_, np.int64)
    rr = (h - l) / c
    adr = win_reduce(rr, P_, 0, 20, np.mean)
    cp = c[P_]
    px = cp * adr
    F = {}
    F["F1"] = (cp - win_reduce(h, P_, 1, 20, np.max)) / px
    F["F2"] = (cp - win_reduce(h, P_, 1, 50, np.max)) / px
    f3 = np.empty(len(P_))
    for i, p in enumerate(P_):
        s = max(0, p - 251)
        f3[i] = p - (s + int(np.argmax(h[s:p + 1])))
    F["F3"] = f3
    F["F4"] = (win_reduce(h, P_, 0, 10, np.max) - win_reduce(l, P_, 0, 10, np.min)) / px
    for n_, nm in ((10, "F5"), (20, "F6"), (50, "F7")):
        F[nm] = (cp - win_reduce(c, P_, 0, n_, np.mean)) / px
    F["F8"] = shift_ratio(c, P_, 20)
    F["F9"] = shift_ratio(c, P_, 60)
    F["F10"] = adr
    F["F11"] = v[P_] / win_reduce(v, P_, 1, 20, np.mean)
    F["F12"] = (h[P_] - l[P_]) / px
    hl = h[P_] - l[P_]
    F["F13"] = np.where(hl > 0, (cp - l[P_]) / np.where(hl > 0, hl, 1.0), 0.5)
    nxt = np.where(P_ + 1 < len(o), P_ + 1, P_)
    F["F14"] = np.where(P_ + 1 < len(o), (o[nxt] - cp) / px, np.nan)
    F["ret63"] = shift_ratio(c, P_, 63)
    F["ret21"] = shift_ratio(c, P_, 21)
    F["F17"] = np.array([qst.get(int(x), "") for x in ci[P_]], dtype=object)
    F["raw"] = raw[P_] if raw is not None else cp
    F["dvmed"] = win_reduce(c * v, P_, 0, 20, np.median)
    F["contig130"] = np.array([p >= 129 and int(ci[p]) - int(ci[p - 129]) == 129 for p in P_])
    F["next_is_bar"] = np.array([p + 1 < len(ci) and int(ci[p + 1]) - int(ci[p]) == 1 for p in P_])
    return F


def cond_eval(df, conj):
    m = np.ones(len(df), bool)
    for f, op, thr in conj:
        x = df[f].to_numpy()
        if op == "==":
            m &= (x == thr)
        else:
            x = np.asarray(x, float)
            m &= (x <= thr) if op == "<=" else (x >= thr)
    return m


def set_meets(df, conjs):
    out = np.zeros(len(df), bool)
    for cj in conjs:
        out |= cond_eval(df, cj)
    return out


def binom95(k, n):
    p = k / n
    return 1.96 * math.sqrt(p * (1 - p) / n) if n else float("nan")


RESULTS = []   # (claim, printout, recount, status, note)


def claim(name, printed, mine, ok, note=""):
    RESULTS.append((name, printed, mine, "MATCH" if ok else "MISMATCH", note))


# =====================================================================================================================================
# 1. SELECT
# =====================================================================================================================================
say("\n## 1. SELECT recount: the check buys, the pick floor, the pool on the check buys' days, recall / pool rate / lift, the §5d rank")
chk_buys = P["sel_chk"] + P["sel_chk_nc"]
chk_days = sorted({CI[b.E] for b in chk_buys})
pick_rows, drop = [], Counter()
for b in chk_buys:
    A = arrays(DA, b.sym_a)
    if A is None:
        drop["ticker_not_in_export"] += 1
        continue
    e = int(np.searchsorted(A["ci"], A_CI[b.E]))
    if not (e < len(A["ci"]) and int(A["ci"][e]) == A_CI[b.E]):
        drop["no_bar_on_E"] += 1
        continue
    if e < 50:
        drop["bars_before_E_lt_50"] += 1
        continue
    p = e - 1
    F = sel_feats(A, [p], raw_flat[A["a"]:A["z"]], QST_A)
    row = {k: (v[0] if hasattr(v, "__len__") else v) for k, v in F.items()}
    reason = ("no_bar_on_prior_session" if not row["next_is_bar"] else "history_lt_130" if not row["contig130"] else
              "raw_close_lt_5" if not row["raw"] >= 5.0 else "dollar_vol_lt_10M" if not row["dvmed"] >= 10e6 else "")
    row.update(eid=b.eid, ticker=b.sym_a, day=b.E, day_ci=CI[b.E], nc=b.nc, sec_type=b.sec_type, floor_reason=reason, floor_ok=reason == "")
    pick_rows.append(row)
picks_all = pd.DataFrame(pick_rows)
say(f"- SELECT check buys rebuilt {len(chk_buys)} (no-event {len(P['sel_chk'])} + never-a-candidate {len(P['sel_chk_nc'])}); records {len(picks_all)} (dropped {dict(drop)}); "
    f"pool floor failed {int((~picks_all['floor_ok']).sum())} ({dict(Counter(picks_all.loc[~picks_all['floor_ok'], 'floor_reason']))}); pass {int(picks_all['floor_ok'].sum())}")
picks = picks_all[picks_all["floor_ok"]].reset_index(drop=True)

# held by day (own: every non-initial entry with a window start, lo .. exit_hi or the last session, keyed by sym_a)
held = defaultdict(set)
for b in NI:
    if not b.lo:
        continue
    hi_ = b.exit_hi if b.exit_hi else CAL[-1]
    for d in CAL[bisect.bisect_left(CAL, b.lo):bisect.bisect_right(CAL, hi_)]:
        held[d].add(b.sym_a)

pool_cache = os.path.join(CACHE, "pool_check_days.pkl.gz")
if os.path.exists(pool_cache):
    with gzip.open(pool_cache, "rb") as fh:
        pool = pickle.load(fh)
    say(f"- pool read back from the recount's own cache ({len(pool):,} rows)")
else:
    t0 = time.time()
    want = np.asarray(chk_days, np.int64)
    parts = []
    for n_t, tk in enumerate(DA.tickers):
        t_ = OVERRIDE.get(tk) or SEC.resolve_type(tk, small, sic)[0]
        if t_ not in ADMIT:
            continue
        tid = DA.tid[tk]
        a, z = int(DA.start[tid]), int(DA.stop[tid])
        ci = np.asarray(DA.ci[a:z], np.int64)
        if len(ci) < 131:
            continue
        pos = np.searchsorted(ci, want - 1)
        pc = np.minimum(pos, len(ci) - 1)
        pn = np.minimum(pos + 1, len(ci) - 1)
        okp = (pos < len(ci) - 1) & (ci[pc] == want - 1) & (ci[pn] == want)
        if not okp.any():
            continue
        A = arrays(DA, tk)
        Pp, Dd = pos[okp], want[okp]
        F = sel_feats(A, Pp, raw_flat[a:z], QST_A)
        keep = F["contig130"] & (F["raw"] >= 5.0) & (F["dvmed"] >= 10e6) & np.isfinite(F["F10"]) & (F["F10"] > 0)
        if not keep.any():
            continue
        df = pd.DataFrame({k: F[k][keep] for k in [f"F{i}" for i in range(1, 15)] + ["ret63", "ret21", "F17"]})
        df["ticker"] = tk
        df["day_ci"] = Dd[keep]
        parts.append(df)
        if (n_t + 1) % 3000 == 0:
            say(f"  pool scan {n_t + 1:,} / {len(DA.tickers):,} ({time.time() - t0:.0f}s)")
    pool = pd.concat(parts, ignore_index=True)
    pool["day"] = [CAL[int(x)] for x in pool["day_ci"]]
    pool["held"] = [tk in held.get(d, set()) for tk, d in zip(pool["ticker"], pool["day"])]
    os.makedirs(CACHE, exist_ok=True)
    with gzip.open(pool_cache, "wb") as fh:
        pickle.dump(pool, fh)
    say(f"- pool rebuilt in {time.time() - t0:.0f}s: {len(pool):,} admitted rows on {pool['day_ci'].nunique()} days")


def share_below_half_ties(vals, x):
    v = vals[np.isfinite(vals)]
    return float((np.sum(v < x) + 0.5 * np.sum(v == x)) / len(v)) if len(v) else float("nan")


# pool F15 / F16: the registered formula (share below + half the ties, itself included) within the day's whole pool
for src, dst in (("ret63", "F15"), ("ret21", "F16")):
    out = np.full(len(pool), np.nan)
    for d, idx in pool.groupby("day_ci").indices.items():
        x = pool[src].to_numpy(float)[idx]
        fin = np.isfinite(x)
        xs = np.sort(x[fin])
        lo_ = np.searchsorted(xs, x[fin], "left")
        hi_ = np.searchsorted(xs, x[fin], "right")
        out[idx[fin]] = (lo_ + 0.5 * (hi_ - lo_)) / len(xs)
    pool[dst] = out
pool_free = pool[~pool["held"]].reset_index(drop=True)
# pick F15 / F16 against the day's NOT-HELD pool plus the pick
byday = {d: g for d, g in pool_free.groupby("day_ci")}
for src, dst in (("ret63", "F15"), ("ret21", "F16")):
    vals = []
    for _i, r in picks.iterrows():
        g = byday.get(r["day_ci"])
        x = float(r[src])
        if g is None or not np.isfinite(x):
            vals.append(np.nan)
            continue
        vals.append(share_below_half_ties(np.concatenate((g[src].to_numpy(float), [x])), x))
    picks[dst] = vals
m_pick = set_meets(picks, CHOSEN_SEL)
m_pool = set_meets(pool_free, CHOSEN_SEL)
rec_, rate_ = m_pick.mean(), m_pool.mean()
lift_ = rec_ / rate_
vsel = "PASS" if (rec_ >= 0.50 and rate_ <= 0.20) else "FAIL" if lift_ < 2.0 else "INCONCLUSIVE"
say(f"- pool rows (not held) on {len(chk_days)} days: {len(pool_free):,} (all admitted incl. his held names {len(pool):,})")
say(f"- CHOSEN set (full-precision thresholds): recall {int(m_pick.sum())} / {len(picks)} = {pct(rec_)} (+-{100 * binom95(int(m_pick.sum()), len(picks)):.0f}), "
    f"pool rate {int(m_pool.sum()):,} / {len(pool_free):,} = {pct(rate_)}, lift {lift_:.2f} -> {vsel}")
typed = picks["sec_type"] != ""
say(f"- without the no-type-row buys: recall {pct(m_pick[typed.to_numpy()].mean())}; no-event only {pct(m_pick[~picks['nc'].to_numpy(bool)].mean())}; "
    f"never-a-candidate {pct(m_pick[picks['nc'].to_numpy(bool)].mean()) if picks['nc'].any() else '-'}")
# compare per-pick against the side output
so = SO["check_select_buys"].copy()
so["eid"] = so["eid"].astype(int)
mm = picks.merge(so, on="eid", suffixes=("", "_so"))
diffs = {}
for k in [f"F{i}" for i in range(1, 17)]:
    a_ = mm[k].to_numpy(float)
    b_ = pd.to_numeric(mm[k + "_so"], errors="coerce").to_numpy(float)
    both = np.isfinite(a_) & np.isfinite(b_)
    diffs[k] = (float(np.max(np.abs(a_[both] - b_[both]) / np.maximum(1e-12, np.abs(b_[both])))) if both.any() else 0.0,
                int((np.isfinite(a_) != np.isfinite(b_)).sum()))
f17_diff = int((mm["F17"].astype(str) != mm["F17_so"].astype(str)).sum())
meets_so = mm["meets"].map({"True": True, "False": False}).to_numpy(bool)
meets_me = set_meets(mm, CHOSEN_SEL)
say(f"- per-pick vs check_select_buys.tsv ({len(mm)} joined): max relative diff per feature " +
    ", ".join(f"{k} {d[0]:.1e}" + (f" (nan-mismatch {d[1]})" if d[1] else "") for k, d in diffs.items()) + f"; F17 differs on {f17_diff}; "
    f"'meets' differs on {int((meets_so != meets_me).sum())}; TSV recall {meets_so.mean():.4f}")
claim("SELECT check buys (records)", "144", str(len(picks_all)), len(picks_all) == 144)
claim("SELECT failing the pool floor", "22", str(int((~picks_all['floor_ok']).sum())), int((~picks_all['floor_ok']).sum()) == 22)
claim("SELECT pool rows (not held), 99 days", "215,938 on 99", f"{len(pool_free):,} on {len(chk_days)}", len(pool_free) == 215938 and len(chk_days) == 99)
claim("SELECT recall", "64.8%", pct(rec_), pct(rec_) == "64.8%")
claim("SELECT pool rate", "18.6%", pct(rate_), pct(rate_) == "18.6%")
claim("SELECT lift", "3.48", f"{lift_:.2f}", f"{lift_:.2f}" == "3.48")
claim("SELECT verdict", "PASS", vsel, vsel == "PASS")

# §5d rank (the fit's frozen rank model applied by own code)
import json
selj = json.load(open(f"{OUT_DIR}/select_fit_chosen.json"))["object"]
rm = selj["rank_model"]
w, b0, mu, sd = np.asarray(rm["w"]), float(rm["b"]), np.asarray(rm["mu"]), np.asarray(rm["sd"])


def design(df):
    X = np.column_stack([df[f"F{i}"].to_numpy(float) for i in range(1, 17)] + [(df["F17"].to_numpy() == c).astype(float) for c in ("up", "mixed", "down")])
    return np.nan_to_num(X, nan=0.0, posinf=0.0, neginf=0.0)


qp = pool_free[m_pool]
sc_q = ((design(qp) - mu) / sd) @ w + b0
qday = qp["day_ci"].to_numpy()
sc_p = ((design(picks) - mu) / sd) @ w + b0
pcts = []
for i in np.flatnonzero(m_pick):
    s_ = sc_q[qday == picks.loc[i, "day_ci"]]
    allv = np.concatenate((s_, [sc_p[i]]))
    pcts.append(float((np.sum(allv > sc_p[i]) + 0.5 * (np.sum(allv == sc_p[i]) - 1)) / len(allv)))
med = float(np.median(pcts))
rv = "PASS" if med <= 0.25 else "FAIL" if med >= 0.40 else "INCONCLUSIVE"
say(f"- §5d rank: median percentile from the top {med:.4f} over {len(pcts)} qualifying picks -> {rv}")
claim("SELECT §5d rank median percentile", "0.29 (79 picks), INCONCLUSIVE", f"{med:.2f} ({len(pcts)}), {rv}", f"{med:.2f}" == "0.29" and len(pcts) == 79)

# =====================================================================================================================================
# 2. ENTER
# =====================================================================================================================================
say("\n## 2. ENTER recount: L1 (and L2-L6) on the 2021-22 in-session brackets; the deciding undated set; the random-level control (seed replayed)")
DONE, MFILES = REV.load_done_all()
mcache = {}


def bars_for_buy(b, min_bars, era=None):
    era = era or ("A" if b.E <= A_LAST else "B")
    D, CIx = (DA, A_CI) if era == "A" else (DB, B_CI)
    tk = b.sym_a if era == "A" else b.sym
    A = arrays(D, tk)
    if A is None:
        return None, "ticker_not_in_export"
    if b.E not in CIx:
        return None, "no_bar_on_E"
    e = int(np.searchsorted(A["ci"], CIx[b.E]))
    if not (e < len(A["ci"]) and int(A["ci"][e]) == CIx[b.E]):
        return None, "no_bar_on_E"
    if e < min_bars:
        return None, f"bars_before_E_lt_{min_bars}"
    A.update(e=e, p=e - 1, era=era, tk=tk, D=D, CIx=CIx)
    A["adr"] = float(b.adr_stored) if b.adr_stored else float(np.mean((A["h"][e - 20:e] - A["l"][e - 20:e]) / A["c"][e - 20:e]))
    return A, None


def minutes_on(d, tk, trees):
    mb = REV.read_minutes(d, tk, DONE, MFILES, tuple(t for t in trees if t in DONE), mcache)
    return mb if (mb is not None and len(mb)) else None


def first_cross(mb, L):
    k = np.flatnonzero(mb.h > L)
    return int(mb.minute[k[0]]) if len(k) else None


def score(mb, L, fm, lm, adr, tol=0.25):
    if L is None or not np.isfinite(L):
        return False, "no_level"
    m = first_cross(mb, L)
    feas = m is not None and fm < m <= lm
    sel = (mb.minute > fm) & (mb.minute <= lm)
    if not sel.any():
        return feas, "no_bracket_minutes"
    lo, hi = float(mb.l[sel].min()), float(mb.h[sel].max())
    if lo <= L <= hi:
        return feas, "HIT"
    if min(abs(L - lo), abs(L - hi)) <= tol * adr * L:
        return feas, "BALLPARK"
    return feas, "MISS"


ent_set = P["ent_chk_dated"] + P["ent_chk_und"]
erecs, edrop = [], Counter()
for b in ent_set:
    A, why = bars_for_buy(b, 20)
    if A is None:
        edrop[why] += 1
        continue
    trees = ("EP", "EP2", "A", "B", "REV") if b.setup == "EP" else ("A", "B", "EP", "EP2", "REV")
    A["mb"] = minutes_on(b.E, A["tk"], trees)
    erecs.append((b, A))
rng = np.random.default_rng([702, zlib.crc32("rev|minute".encode()) & 0xFFFFFFFF])
scored = {}
for b, A in sorted(erecs, key=lambda x: (x[0].E, x[0].eid)):
    mb = A["mb"]
    if mb is None:
        continue
    e, p, h, l, c, o = A["e"], A["p"], A["h"], A["l"], A["c"], A["o"]
    fm, lm = hhmm(b.flat_clock), hhmm(b.first_clock)
    o5 = float(mb.h[mb.minute < 5].max()) if (mb.minute < 5).any() else None
    lv = {"L1": (max(o5, b.pivot) if (b.dated and b.pivot is not None) else o5) if o5 is not None else None,
          "L2": float(h[p]), "L3": float(b.pivot) if (b.setup in ("breakout", "both") and b.pivot is not None) else float(np.max(h[max(p - 19, 0):p + 1])),
          "L4": float(o[e]), "L5": float(c[p]), "L6": float(mb.h[mb.minute < 60].max()) if (mb.minute < 60).any() else None}
    res = {}
    for L, x in lv.items():
        if lm < {"L1": 5, "L6": 60}.get(L, 0):
            res[L] = (False, "no_level_yet")
        else:
            res[L] = score(mb, x, fm, lm, A["adr"])
    u = rng.integers(0, 390, size=200)
    idx = np.searchsorted(mb.minute, u, side="right") - 1
    ctl = np.where(idx >= 0, mb.c[np.maximum(idx, 0)], mb.o[0])
    cf = ch = 0
    for x in ctl:
        f_, v_ = score(mb, float(x), fm, lm, A["adr"])
        cf += int(f_)
        ch += int(v_ in ("HIT", "BALLPARK"))
    res["control"] = (cf / 200, ch / 200)
    scored[b.eid] = (b, res)
deciding = {k: v for k, v in scored.items() if not v[0].dated}
dated_s = {k: v for k, v in scored.items() if v[0].dated}
n_d = len(deciding)
say(f"- ENTER records {len(erecs)} of {len(ent_set)} (dropped {dict(edrop)}); scorable {len(scored)} (no minutes {sum(1 for _b, A in erecs if A['mb'] is None)}); deciding (undated) {n_d}; dated beside {len(dated_s)}")
summ = {}
for L in ("L1", "L2", "L3", "L4", "L5", "L6"):
    f_ = sum(1 for _b, r in deciding.values() if r[L][0])
    h_ = sum(1 for _b, r in deciding.values() if r[L][1] in ("HIT", "BALLPARK"))
    vc = Counter(r[L][1] for _b, r in deciding.values())
    summ[L] = (f_ / n_d, h_ / n_d)
    say(f"- {L}: feasible {f_}/{n_d} = {pct(f_ / n_d)} (+-{100 * binom95(f_, n_d):.0f}); hit-or-ballpark {h_}/{n_d} = {pct(h_ / n_d)} ({', '.join(f'{k} {v}' for k, v in sorted(vc.items()))})")
cf_m = float(np.mean([r["control"][0] for _b, r in deciding.values()]))
ch_m = float(np.mean([r["control"][1] for _b, r in deciding.values()]))
say(f"- control (seeded stream replayed, one 200-draw per scorable record in (E, eid) order over all {len(scored)}): feasible {pct(cf_m)}, hit-or-ballpark {pct(ch_m)}")
f1d = sum(1 for _b, r in dated_s.values() if r["L1"][0]) / max(1, len(dated_s))
h1d = sum(1 for _b, r in dated_s.values() if r["L1"][1] in ("HIT", "BALLPARK")) / max(1, len(dated_s))
say(f"- beside, L1 on the dated 2021-22 brackets ({len(dated_s)}): feasible {pct(f1d)}, hit-or-ballpark {pct(h1d)}")
fs, hs = summ["L1"]
reasons = [r_ for r_, bad in (("feasible < 50%", fs < 0.5), ("feasible < control + 15", fs < cf_m + 0.15), ("hit < 70%", hs < 0.7), ("hit < control + 15", hs < ch_m + 0.15)) if bad]
vent = "INCONCLUSIVE" if n_d < 40 else "PASS" if not reasons else "FAIL" if all(summ[L][0] < 0.5 for L in summ) else "INCONCLUSIVE"
say(f"- ENTER verdict (own rule from §6): {vent} ({'; '.join(reasons)})")
claim("ENTER deciding set", "41 undated (61 records, 3 dropped <20 bars)", f"{n_d} undated ({len(erecs)} records, dropped {dict(edrop)})", n_d == 41 and len(erecs) == 61)
claim("ENTER L1 feasible (41)", "36.6%", pct(fs), pct(fs) == "36.6%")
claim("ENTER L1 hit-or-ballpark (41)", "87.8%", pct(hs), pct(hs) == "87.8%")
claim("ENTER control feasible", "31.7%", pct(cf_m), pct(cf_m) == "31.7%", "seeded draw replayed")
claim("ENTER control hit-or-ballpark", "85.9%", pct(ch_m), pct(ch_m) == "85.9%", "seeded draw replayed")
claim("ENTER beside: L1 dated 20", "60.0% / 90.0%", f"{pct(f1d)} / {pct(h1d)}", pct(f1d) == "60.0%" and pct(h1d) == "90.0%")
claim("ENTER verdict", "FAIL", vent, vent == "FAIL")

# =====================================================================================================================================
# 3. STOP
# =====================================================================================================================================
say("\n## 3. STOP recount on the undated 2021-22 check buys: held-through per level and variant, own walk; then the side output aggregated")
sight = defaultdict(list)
for r in sn.to_dict("records"):
    names = {x for x in (r.get("symbols") or "").split(",") if x} | {x for x in (r.get("blip_filled") or "").split(",") if x}
    for s_ in names:
        sight[(r["date"], s_)].append((int(r["idx"]), r["ctx"], r["clock"]))


def last_in_clock(d, s_):
    fr = [x for x in sight.get((d, s_), ()) if x[1] == "in" and x[2]]
    return max(fr)[2] if fr else None


def after_close(d, s_):
    return any(x[1] == "closed" for x in sight.get((d, s_), ()))


def frame_after(d, s_, m):
    return any(x[1] == "in" and x[2] and hhmm(x[2]) is not None and hhmm(x[2]) > m for x in sight.get((d, s_), ()))


def sma_at(c, k, n):
    return float(np.mean(c[k - n + 1:k + 1])) if k >= n - 1 else float("nan")


srecs, sdrop = [], Counter()
for b in P["und_chk"]:
    A, why = bars_for_buy(b, 50)
    if A is None:
        sdrop[why] += 1
        continue
    e, p = A["e"], A["p"]
    A["mb"] = minutes_on(b.E, A["tk"], ("A", "B", "EP", "EP2", "REV"))
    A["fill"] = float(A["o"][e]) * (1 + SLIP_IN)
    adr = A["adr"]
    A["lv"] = {"S1": float(A["l"][e]), "S2": float(A["l"][e]), "S3": float(A["l"][p]), "S4": A["fill"] * (1 - adr),
               "S5": float(np.max(A["h"][max(p - 19, 0):p + 1])), "S6": float(np.min(A["l"][max(p - 19, 0):p + 1])), "S7": ("sma", 10),
               "S8": A["fill"] * (1 - 2 * adr), "SMA50": ("sma", 50)}
    # exit offsets: MODULE = the pickle-calendar index minus the bar's own-export calendar index (as the check computed it);
    #               FIXED  = both on the trade's own export calendar (differs only for era-B buys)
    e_ci = int(A["ci"][e])
    A["off_mod"] = (max(0, b.exit_lo_i - e_ci), max(0, b.exit_hi_i - e_ci)) if b.exit_hi_i >= 0 else None
    A["off_fix"] = ((max(0, A["CIx"][b.exit_lo] - e_ci), max(0, A["CIx"][b.exit_hi] - e_ci))
                    if (b.exit_hi_i >= 0 and b.exit_lo in A["CIx"] and b.exit_hi in A["CIx"]) else A["off_mod"])
    if b.exit_lo and b.exit_lo != b.E:
        tk_x = b.sym_a if b.exit_lo <= A_LAST else b.sym
        A["xmb"] = minutes_on(b.exit_lo, tk_x, ("A", "B", "EP", "EP2", "REV"))
    else:
        A["xmb"] = None
    srecs.append((b, A))
say(f"- STOP / EXIT records {len(srecs)} of {len(P['und_chk'])} (dropped {dict(sdrop)}); era B buys among them {sum(1 for _b, A in srecs if A['era'] == 'B')}")


def bar_at(A, j):
    k = A["e"] + j
    if k >= len(A["ci"]) or int(A["ci"][k]) != int(A["ci"][A["e"]]) + j:
        return None
    return k


def lvl_at(A, lvl, j):
    if isinstance(lvl, tuple):
        k = bar_at(A, j)
        return sma_at(A["c"], k, lvl[1]) if k is not None else float("nan")
    return float(lvl)


def held_thru(b, A, name, V, mode):
    lvl = A["lv"][name]
    j0 = 1 if (V == "T" and name in ("S1", "S2")) else 0          # S1 is the day's low on every undated (open) fill
    off = A["off_mod"] if mode == "mod" else A["off_fix"]
    if off is None:
        return False, False
    lo_j, J = off
    mb, xmb = A["mb"], A["xmb"]
    for j in range(j0, J + 1):
        k = bar_at(A, j)
        if k is None:
            break
        L = lvl_at(A, lvl, j)
        if not np.isfinite(L):
            continue
        touch_m = None
        if V == "C":
            thr = A["c"][k] < L
        elif j == 0:
            if mb is not None:
                hit = np.flatnonzero((mb.minute > 0) & ((mb.l <= L) | (mb.o < L)))
                thr = len(hit) > 0
                touch_m = int(mb.minute[hit[0]]) if thr else None
            else:
                thr = A["l"][k] <= L                          # an open fill (minute 0) without minutes: the day's low
        else:
            thr = A["l"][k] <= L
        if not thr:
            continue
        if j < lo_j:
            return True, True
        if j == lo_j:
            if V == "C":
                return True, after_close(b.exit_lo, b.sym)
            c_last = last_in_clock(b.exit_lo, b.sym)
            if j == 0 and touch_m is not None:
                return True, frame_after(b.E, b.sym, touch_m)
            if c_last is not None and xmb is not None:
                hit = np.flatnonzero((xmb.l <= L) | (xmb.o < L))
                return True, bool(len(hit) and int(xmb.minute[hit[0]]) < hhmm(c_last))
            return True, False
        return True, False
    return False, False


LEVELS = ("S1", "S2", "S3", "S4", "S5", "S6", "S7", "S8", "SMA50")
tabs = {}
for mode in ("mod", "fix"):
    for sub_name, pred in (("all", lambda b: True), ("nf", lambda b: not b.flicker), ("untouched", lambda b: not b.in_dated_path)):
        for L in LEVELS:
            for V in ("T", "C"):
                a_ = c_ = 0
                for b, A in srecs:
                    if not pred(b):
                        continue
                    an, ce = held_thru(b, A, L, V, mode)
                    a_ += an
                    c_ += ce
                tabs[(mode, sub_name, L, V)] = (a_, c_)
# the side output aggregated (certain / any on the undated rows)
st = SO["check_stop_trades"]
stu = st[st["dated"] == "False"]
PRINTED_STOP = {"S1-T": ("43.9%", 98, 43), "S1-C": ("50.0%", 66, 33), "S2-T": ("43.9%", 98, 43), "S2-C": ("50.0%", 66, 33), "S3-T": ("72.7%", 99, 72),
                "S3-C": ("64.6%", 65, 42), "S4-T": ("65.7%", 70, 46), "S4-C": ("80.0%", 40, 32), "S5-T": ("99.0%", 208, 206), "S5-C": ("69.2%", 195, 135),
                "S6-T": ("91.3%", 23, 21), "S6-C": ("88.2%", 17, 15), "S7-T": ("86.7%", 165, 143), "S7-C": ("53.8%", 132, 71), "S8-T": ("77.4%", 31, 24),
                "S8-C": ("86.4%", 22, 19), "SMA50-T": ("87.4%", 95, 83), "SMA50-C": ("58.2%", 79, 46)}
PRINTED_NF = {"S1-T": "56.3%", "S1-C": "58.8%", "S3-T": "80.0%", "S4-C": "87.9%"}
PRINTED_UN = {"S1-T": "42.6%", "S1-C": "48.0%", "S3-T": "68.7%", "S4-C": "80.0%"}
say("  level-variant | printout (any / certain) | side-output aggregate | recount, module offsets | recount, era-B offsets fixed | nf 145 (mod) | untouched 161 (mod)")
for L in LEVELS:
    for V in ("T", "C"):
        lv = f"{L}-{V}"
        pr = PRINTED_STOP[lv]
        so_a = int((stu[f"{L}_{V}_any"] == "True").sum())
        so_c = int((stu[f"{L}_{V}_certain"] == "True").sum())
        a_m, c_m = tabs[("mod", "all", L, V)]
        a_f, c_f = tabs[("fix", "all", L, V)]
        a_n, c_n = tabs[("mod", "nf", L, V)]
        a_u, c_u = tabs[("mod", "untouched", L, V)]
        say(f"  {lv:<13} | {pr[0]} ({pr[1]} / {pr[2]}) | {pct(so_c / so_a)} ({so_a} / {so_c}) | {pct(c_m / a_m)} ({a_m} / {c_m}) | {pct(c_f / a_f)} ({a_f} / {c_f}) | "
            f"{pct(c_n / a_n)} | {pct(c_u / a_u)}")
        ok = (so_a, so_c) == (pr[1], pr[2]) and (a_m, c_m) == (pr[1], pr[2])
        if lv in ("S1-T", "S1-C", "S3-T", "S4-C"):
            ok_nf = pct(c_n / a_n) == PRINTED_NF[lv] and pct(c_u / a_u) == PRINTED_UN[lv]
            claim(f"STOP {lv} H_cond (undated; nf / untouched)", f"{pr[0]} ({pr[1]}/{pr[2]}); {PRINTED_NF[lv]} / {PRINTED_UN[lv]}",
                  f"{pct(c_m / a_m)} ({a_m}/{c_m}); {pct(c_n / a_n)} / {pct(c_u / a_u)}; era-B fixed {pct(c_f / a_f)} ({a_f}/{c_f})", ok and ok_nf,
                  "side-output aggregate " + ("equal" if (so_a, so_c) == (pr[1], pr[2]) else f"{so_a}/{so_c}"))
        elif not ok:
            say(f"    ^ {lv}: recount differs from the printout")
# verdict: no level met H_cond <= 10% on the FIT (stop_fit_chosen.json) -> INCONCLUSIVE by §7's rule; and every check level > 10%
stpj = json.load(open(f"{OUT_DIR}/stop_fit_chosen.json"))["object"]
fit_min = min(v["H_cond"] for k, v in stpj["fit_table"].items() if k.split("-")[0] in ("S1", "S2", "S3", "S4", "S5", "S6", "S7") and v["eligible"])
chk_all_gt30 = all(tabs[("mod", "all", L, V)][1] / tabs[("mod", "all", L, V)][0] > 0.30 for L in LEVELS[:8] for V in ("T", "C"))
vstop = "INCONCLUSIVE" if stpj["level"] is None else "?"
say(f"- STOP verdict: the fit chose no level (lowest eligible S1-S7 H_cond on the fit {pct(fit_min)} > 10%) -> {vstop}; every check level > 30% "
    f"(falsifier reading, not reached because no level was chosen): {chk_all_gt30}")
claim("STOP verdict", "INCONCLUSIVE", vstop, vstop == "INCONCLUSIVE")
claim("STOP / EXIT base (header says 226)", "226 set; trades 212", f"226 set; {len(srecs)} records ({dict(sdrop)})", len(srecs) == 212,
      "label only: the 14 fall under the registered 50-bar record floor; every number is on the 212")
eraB = [(b, A) for b, A in srecs if A["era"] == "B"]
claim("exit_lo_j / exit_hi_j on the era-B undated check trades", "1443-1450 (check_exit_trades.tsv; check_g8_B.tsv: 15 rows incl. 7 dated)",
      f"{len(eraB)} trades, own-calendar offsets " + ", ".join(f"{A['off_fix'][0]}-{A['off_fix'][1]}" for _b, A in eraB), False,
      "pickle-calendar exit index minus the era-B export's bar index; inflates STOP 'certain' on those trades (e.g. S4-C 80.0% -> 66.7%), "
      "holds 'his' to the 120-session horizon (non-flicker his 1.341 -> 1.533), and makes the 8 non-scorable in the hit rate "
      "(the check's 'held_to_hole_before_window 8'); NO verdict flips; the EXIT fit's era-B dated 2022 trades carry the same offset (not re-run here)")

# =====================================================================================================================================
# 4. EXIT
# =====================================================================================================================================
say("\n## 4. EXIT recount: hit rates (own feature rows and own decision-list walk) and the three accounts (own trade lists; frozen simulate)")
QQQ_B = arrays(DB, "QQQ")


def qqq_close(A, k):
    D = A["D"]
    Q = QQQ_A if A["era"] == "A" else QQQ_B
    ci = int(A["ci"][k])
    j = int(np.searchsorted(Q["ci"], ci))
    return float(Q["c"][j]) if (j < len(Q["ci"]) and int(Q["ci"][j]) == ci) else float("nan")


def xrows(A, J, fill, stop):
    """[J+1, 10] exit features on consecutive bars 0..J, or None when a hole / the data's end comes first."""
    c, o, h, l = A["c"], A["o"], A["h"], A["l"]
    adr, risk = A["adr"], fill - stop
    rows, maxr = [], -np.inf
    for j in range(J + 1):
        k = bar_at(A, j)
        if k is None:
            return None
        px = c[k] * adr
        maxr = max(maxr, (h[k] - fill) / risk)
        rj = (c[k] - fill) / risk
        s10, s20 = sma_at(c, k, 10), sma_at(c, k, 20)
        q, qp_ = qqq_close(A, k), qqq_close(A, k - 1)
        rows.append([(c[k] - s10) / px if np.isfinite(s10) else 0.0, (c[k] - s20) / px if np.isfinite(s20) else 0.0, float(c[k] < c[k - 1]),
                     float(c[k] < l[k - 1]), float(j), (o[k] - c[k - 1]) / (c[k - 1] * adr), rj, maxr - rj,
                     float(q < qp_) if (np.isfinite(q) and np.isfinite(qp_)) else 0.0, (h[k] - l[k]) / px])
    return np.asarray(rows, float)


XI = {f"X{i}": i - 1 for i in range(1, 11)}


def list_day(X):
    best = 10 ** 6
    for rule in CHOSEN_EXIT:
        m = np.ones(len(X), bool)
        for f, op, thr in rule:
            x = X[:, XI[f]]
            m &= (x <= thr) if op == "<=" else (x >= thr) if op == ">=" else (x == thr)
        hh = np.flatnonzero(m)
        if len(hh):
            best = min(best, int(hh[0]))
    return best


def red_day(X):
    red = np.flatnonzero(X[1:, 2] > 0) + 1
    return int(red[0]) if len(red) else 10 ** 6


def consec_until(A, cap):
    j = 0
    while j < cap and bar_at(A, j + 1) is not None:
        j += 1
    return j


for b, A in srecs:
    A["stop"] = A["fill"] * (1 - A["adr"])
hits = {}
so_x = SO["check_exit_trades"].copy()
so_x["eid"] = so_x["eid"].astype(int)
so_day = dict(zip(so_x["eid"], so_x["chosen (list)"].astype(int)))
for mode in ("mod", "fix"):
    sd, lo_, hi_, sc_, notes, same = [], [], [], [], Counter(), 0
    rd, s3 = [], []
    for b, A in srecs:
        off = A["off_mod"] if mode == "mod" else A["off_fix"]
        if off is None:
            continue
        J = off[1]
        X = xrows(A, J, A["fill"], A["stop"])
        trunc = False
        if X is None:
            J2 = consec_until(A, J)
            X = xrows(A, J2, A["fill"], A["stop"])
            trunc = True
        d_ = list_day(X)
        if mode == "mod" and so_day.get(b.eid) == d_:
            same += 1
        sd.append(d_)
        rd.append(red_day(X))
        s3.append(2)
        if off[0] <= len(X) - 1:
            lo_.append(off[0])
            hi_.append(min(off[1], len(X) - 1))
            sc_.append((b.exit_hi_i - b.exit_lo_i + 1) <= 20 and not trunc)
        else:
            notes["held_to_hole_before_window"] += 1
            lo_.append(0)
            hi_.append(-1)
            sc_.append(False)
    sd, lo_, hi_, sc_ = map(np.asarray, (sd, lo_, hi_, sc_))
    m = sc_ & (hi_ >= 0)
    hr = lambda days: float(((np.asarray(days)[m] >= lo_[m]) & (np.asarray(days)[m] <= hi_[m])).mean())   # noqa: E731
    hits[mode] = dict(list=hr(sd), s3=hr(s3), red=hr(rd), n=int(m.sum()), notes=dict(notes), same=same, total=len(sd))
    say(f"- hit rates ({'module offsets' if mode == 'mod' else 'era-B offsets fixed'}; scorable {int(m.sum())} of {len(sd)}; {dict(notes)}): "
        f"chosen list {pct(hits[mode]['list'])}, close of session 3 {pct(hits[mode]['s3'])}, first red close {pct(hits[mode]['red'])}"
        + (f"; own list sell day equals the TSV's on {same} of {len(sd)}" if mode == "mod" else ""))
# the TSV alone (no bars): sell day in [lo, hi] on windows <= 20 sessions; the 8 era-B rows are 'held to a hole' (lo > path) as the check read them
tsv_lo, tsv_hi = so_x["exit_lo_j"].astype(int).to_numpy(), so_x["exit_hi_j"].astype(int).to_numpy()
wl20 = np.array([(BYEID[e].exit_hi_i - BYEID[e].exit_lo_i + 1) <= 20 for e in so_x["eid"]])
eraA = np.array([BYEID[e].E <= A_LAST for e in so_x["eid"]])
mt = wl20 & eraA
tsv_hit = float(((so_x["chosen (list)"].astype(int).to_numpy()[mt] >= tsv_lo[mt]) & (so_x["chosen (list)"].astype(int).to_numpy()[mt] <= tsv_hi[mt])).mean())
say(f"- hit rate from check_exit_trades.tsv alone (era-A rows, window <= 20 sessions: {int(mt.sum())}): {pct(tsv_hit)} (the bar-based recount above also drops a window cut by a hole)")
claim("EXIT chosen list hit rate", "37.3%", f"{pct(hits['mod']['list'])} (TSV-only {pct(tsv_hit)}; era-B fixed {pct(hits['fix']['list'])})", pct(hits["mod"]["list"]) == "37.3%")

# ---- the three accounts
CAP30 = H.CAP30
cal_dates = list(cal_u)
w0 = CI[CHECK_WIN[0]]
ORDER_OPEN, ORDER_CLOSE, ORDER_INTRADAY = rp.ORDER_OPEN, rp.ORDER_CLOSE, rp.ORDER_INTRADAY
ARMS = {H.SPEED_ARM: H.ARMS[H.SPEED_ARM]}


def bars_obj(A):
    tid = A["tid"]
    return R.bars_for(A["D"], tid)


def simple_trade(b, A, j, px, kind, width):
    if not (np.isfinite(px) and width > 0):
        return None
    ci = int(A["ci"][A["e"]]) + j
    order = ORDER_OPEN if kind in ("stop_gap", "stop_close") else ORDER_CLOSE if kind in ("mark", "mark_hole", "mark_break", "sell_close") else ORDER_INTRADAY
    fill = float(A["fill"])
    stop = fill * (1 - width)
    legs = [(ci, order, 1.0, float(px), kind, j)]
    rs = tuple(sum(f * (pp * (1 - s_) - fill) for _c, _o, f, pp, _k, _j in legs) / (fill - stop) for s_ in rp.EXIT_SLIPS)
    era = A["era"]
    tk = A["tk"]
    t = rp.Trade(key=(era, tk, b.E), ticker=tk, era=era, e_ci=int(A["ci"][A["e"]]), fill_minute=0, fill=fill, stop=stop, width=width, status=kind,
                 mature=True, realized_r=rs[0], r_slip=rs, sessions_held=j, legs=legs, path_c=np.asarray(A["c"][A["e"]:A["e"] + j + 1], float),
                 retrigger=0, year=int(b.E[:4]), month=b.E[:7])
    return H.to_unified(t, map_b)


def day0_stop(A, stop):
    mb = A["mb"]
    if mb is not None:
        hh = np.flatnonzero((mb.minute > 0) & ((mb.l <= stop) | (mb.o < stop)))
        if len(hh):
            op = float(mb.o[hh[0]])
            return True, (op if op < stop else stop)
        return False, None
    return (True, stop) if A["l"][A["e"]] <= stop else (False, None)


def fwd_len(A, b):
    """The speed trail's forward window length: consecutive bars after E (<= 121), cut at the first identity break after E."""
    n = consec_until(A, HORIZON + 1)
    cut_hole = n < HORIZON + 1 and A["e"] + n + 1 < len(A["ci"])
    brk = GUARDS[A["era"]].get(A["tk"])
    nb = n
    if brk is not None and len(brk):
        eo = date.fromisoformat(b.E).toordinal()
        jj = int(np.searchsorted(brk, eo, side="right"))
        if jj < len(brk):
            dates = A["D"].cal
            for i in range(1, n + 1):
                if dates[int(A["ci"][A["e"] + i])].toordinal() >= int(brk[jj]):
                    nb = i - 1
                    break
    why = "break" if nb < n else ("hole" if cut_hole else "")
    return nb, why


def ours_trade(b, A):
    bars, cidx = bars_obj(A)
    e = A["e"]
    width = (A["fill"] - A["stop"]) / A["fill"]
    st_, px = day0_stop(A, A["stop"])
    d0 = {"stopped": bool(st_), "exit_price": px, "exit_minute": None}
    en = {"status": "filled", "reason": None, "fill": float(A["fill"]), "stop": float(A["stop"]), "fill_minute": 0, "width_pct": width,
          "level": float(A["fill"]), "day0": d0}
    fwd, _cut = cb.forward_window(bars, cidx, e, HORIZON)
    fwd, _brk = rp.cut_at_break(fwd, bars.dates[e], GUARDS[A["era"]].get(A["tk"]))
    raw = cb.walk_arms(en, closes_before=bars.c[:e + 1], fwd=fwd, adr20=A["adr"], horizon=HORIZON, arms=ARMS)[H.SPEED_ARM]
    ev = SimpleNamespace(era=A["era"], ticker=A["tk"], E=b.E, retrigger=0, year=int(b.E[:4]), month=b.E[:7])
    return H.to_unified(rp.make_trade(ev, en, raw, bars, cidx, e, len(fwd)), map_b)


def chosen_trade(b, A, bh, why):
    stop = A["stop"]
    width = (A["fill"] - stop) / A["fill"]
    st_, px = day0_stop(A, stop)
    if st_:
        return simple_trade(b, A, 0, px, "day0_gap" if px < stop else "day0_stop", width)
    hz = min(HORIZON, bh)
    Jm = consec_until(A, hz)
    X = xrows(A, Jm, A["fill"], stop)
    sj = list_day(X)
    for j in range(0, Jm + 1):
        k = bar_at(A, j)
        if j >= 1:
            if A["o"][k] < stop:
                return simple_trade(b, A, j, float(A["o"][k]), "stop_gap", width)
            if A["l"][k] <= stop:
                return simple_trade(b, A, j, stop, "stop", width)
        if j == sj:
            return simple_trade(b, A, j, float(A["c"][k]), "sell_close", width)
    kind = "mark" if Jm >= hz else "mark_hole"
    if kind == "mark" and why and Jm == bh and bh < HORIZON:
        kind = "mark_break" if why == "break" else "mark_hole"
    return simple_trade(b, A, Jm, float(A["c"][bar_at(A, Jm)]), kind, width)


def his_trade(b, A, bh, why, mode):
    off = A["off_mod"] if mode == "mod" else A["off_fix"]
    width = (A["fill"] - A["stop"]) / A["fill"]
    J = off[1]
    j = consec_until(A, min(J, bh))
    return simple_trade(b, A, j, float(A["c"][bar_at(A, j)]), "mark" if j == J else ("mark_break" if why == "break" else "mark_hole"), width)


ACC = {}
for mode in ("mod", "fix"):
    for sub_name, pred in (("all", lambda b: True), ("nf", lambda b: not b.flicker), ("untouched", lambda b: not b.in_dated_path)):
        lists = {"ours": [], "chosen": [], "his": []}
        cnt = Counter()
        for b, A in srecs:
            if not pred(b) or A["off_mod"] is None:
                continue
            bh, why = fwd_len(A, b)
            cnt[f"cut_at_{why}"] += int(bool(why) and A[("off_mod" if mode == "mod" else "off_fix")][1] > bh)
            to, tc, th = ours_trade(b, A), chosen_trade(b, A, bh, why), his_trade(b, A, bh, why, mode)
            if to is None or tc is None or th is None:
                cnt["unbuildable"] += 1
                continue
            lists["ours"].append(to)
            lists["chosen"].append(tc)
            lists["his"].append(th)
            cnt["trades"] += 1
        sims = {k: rp.simulate(v, CAP30, cal_dates, w0) for k, v in lists.items()}
        ACC[(mode, sub_name)] = (sims, cnt)
        fo, fc, fh = sims["ours"]["final"], sims["chosen"]["final"], sims["his"]["final"]
        ratio = fh / fo
        void = ratio <= 1.0 or ratio < 1.25
        recv = float("nan") if void else (math.log(fc) - math.log(fo)) / (math.log(fh) - math.log(fo))
        say(f"- [{'module offsets' if mode == 'mod' else 'era-B offsets FIXED'}] {sub_name} ({dict(cnt)}): ours {fo:.3f} | chosen {fc:.3f} | his {fh:.3f} | his / ours {ratio:.3f} "
            f"-> {'VOID (no bar)' if void else f'recovery {recv:+.3f} -> ' + ('PASS' if recv >= 0.25 else 'FAIL')}")
        for k_, s_ in sims.items():
            say(f"    {k_}: by year " + ", ".join(f"{y} {pct(x)}" for y, x in sorted(s_["yearly"].items())) + f" | max DD {pct(s_['max_dd'])} | entered {s_['counts']['entered']}, skipped no room {s_['counts']['skipped_no_room']}")
s_all, c_all = ACC[("mod", "all")]
s_nf, c_nf = ACC[("mod", "nf")]
s_fx, _ = ACC[("fix", "all")]
s_fxn, _ = ACC[("fix", "nf")]
fm3 = lambda s: f"{s['ours']['final']:.3f} / {s['chosen']['final']:.3f} / {s['his']['final']:.3f}"   # noqa: E731
claim("EXIT all: ours / chosen / his (REUSED-SIM)", "1.503 / 1.646 / 1.727 (212 trades)", f"{fm3(s_all)} ({c_all['trades']}); era-B fixed {fm3(s_fx)}",
      fm3(s_all) == "1.503 / 1.646 / 1.727" and c_all["trades"] == 212, "ours = frozen speed trail; chosen / his trade lists own")
r_all = s_all["his"]["final"] / s_all["ours"]["final"]
r_fx = s_fx["his"]["final"] / s_fx["ours"]["final"]
claim("EXIT his / ours -> verdict", "1.15 -> VOID (no bar)", f"{r_all:.2f} -> {'VOID' if r_all < 1.25 else 'not VOID'}; era-B fixed {r_fx:.2f} -> {'VOID' if r_fx < 1.25 else 'not VOID'}",
      f"{r_all:.2f}" == "1.15" and r_all < 1.25)
claim("EXIT non-flicker: ours / chosen / his (REUSED-SIM)", "1.883 / 1.772 / 1.341 (134 trades)", f"{fm3(s_nf)} ({c_nf['trades']}); era-B fixed {fm3(s_fxn)}",
      fm3(s_nf) == "1.883 / 1.772 / 1.341" and c_nf["trades"] == 134)

# =====================================================================================================================================
# the table
# =====================================================================================================================================
claim("Populations = the registration's check sets; no fit trade inside", "§2b counts 145/15/188/226/304/111/20/44, nf 145, untouched 161",
      f"sets {', '.join(f'{k} {n}' for k, _v, n in POPROWS)}; undated 2021-22 eids in any fit file {len(und_2122_in_fit)}", POP_OK)
say("\n## RECOUNT TABLE: claim | printout | recount | status")
for nm, pr, mi, stt, note in RESULTS:
    say(f"- {nm} | {pr} | {mi} | {stt}" + (f" ({note})" if note else ""))
n_mis = sum(1 for r in RESULTS if r[3] == "MISMATCH")
say(f"\nRECOUNT COMPLETE in {time.time() - T0:.0f}s: {len(RESULTS) - n_mis} MATCH, {n_mis} MISMATCH")
with open(OUT_TXT, "w") as fh:
    fh.write("\n".join(LINES) + "\n")
