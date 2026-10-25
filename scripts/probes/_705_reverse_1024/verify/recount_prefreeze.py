#!/usr/bin/env python3
"""Independent pre-freeze recount of docs/analysis/cb_reverse_engineer_his_rules_prereg_2026-10-24.md (REGISTERED, NOT FROZEN, NOT RUN).

Reads ONLY: the holdings timeline's three TSVs (entries / exits / snapshots), the session calendar the holdings module pins
(`positions_pct_calendar.pkl.gz` cal list, cut at 2024-12-31 at read; sessions_A as the prefix check), the event-date files the holdings
module pins (candidates A / B: ticker, D, E, K, split only; EP events A / B: ticker, E, primary only), the minute trees' fetch logs
(`_done.psv`) and DIRECTORY LISTINGS (coverage only - no bar file is opened), and the captions folder (`subs/*.vtt`) with `video_status.tsv`
and `stream_moments.tsv` (ticker / t columns). No price, no minute bar, nothing in 2025-26. Not a re-run of any module; the registration is
NOT edited. It also writes the minute-fetch list (NOT fetched here) to /Users/alvinfung/apollo_data/cb702/minutes_rev_1024/fetch_list.psv.

Output: one line per claim `[line] label | doc | mine | OK / MISMATCH / NOTE`; the MISMATCH lines are listed again at the end.
"""
import bisect
import collections
import datetime
import glob
import gzip
import hashlib
import os
import pickle
import re
import statistics
import sys

import numpy as np
import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.abspath(os.path.join(HERE, "..", "..", "..", ".."))
DATA = "/Users/alvinfung/apollo_data"
H = f"{DATA}/cb702/qm_streams/holdings_1024/"
QS = f"{DATA}/cb702/qm_streams/"
VIS = QS + "vision/"
CUT = "2024-12-31"
A_LAST = "2022-03-31"
B_FIRST = "2022-04-01"
DENSE = ("2020-01-27", "2022-06-14")
Y20 = ("2020-01-27", "2020-12-31")
Y2122 = ("2021-01-04", "2022-06-14")
OUT_TXT = os.path.join(HERE, "recount_prefreeze.txt")
FETCH_DIR = f"{DATA}/cb702/minutes_rev_1024"
FETCH_LIST = f"{FETCH_DIR}/fetch_list.psv"
TREES = {"A": f"{DATA}/cb702_pre_v2/minutes", "B": f"{DATA}/cb702/minutes",
         "EP": f"{DATA}/cb702/minutes_ep_1023", "EP2": f"{DATA}/cb702/minutes_ep_1024"}
OTHER_TREES = {"com_delta_1018": f"{DATA}/cb702/minutes_com_delta_1018", "pre_com_1018": f"{DATA}/cb702/minutes_pre_com_1018",
               "delta_out": f"{DATA}/cb702/cb702_minutes_delta_out"}
QMLIB_DIR = os.path.join(REPO, "scripts", "probes", "_qm_streams")

LINES = []
CLAIMS = []


def say(msg=""):
    print(msg, flush=True)
    LINES.append(msg)


def fmt(x):
    if isinstance(x, (list, tuple, dict)):
        return str(x)
    if isinstance(x, (float, np.floating)):
        return f"{x:.4g}"
    return str(x)


def claim(line, label, doc, mine, note="", kind=None):
    """doc / mine compared as printed text. kind: None -> OK if equal else MISMATCH; 'NOTE' -> informational."""
    if kind is None:
        status = "OK" if fmt(doc) == fmt(mine) else "MISMATCH"
    else:
        status = kind
    CLAIMS.append((line, label, doc, mine, status, note))
    say(f"[L{line}] {label} | doc {fmt(doc)} | mine {fmt(mine)} | {status}" + (f" | {note}" if note else ""))
    return status


def sha(path):
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for ch in iter(lambda: fh.read(1 << 20), b""):
            h.update(ch)
    return h.hexdigest()


# ============================================================================================================== inputs
say("# #705 REVERSE-ENGINEER registration: independent pre-freeze recount (OUTCOME-FREE: timeline TSVs, event dates, fetch logs, captions)")
say("# registration: docs/analysis/cb_reverse_engineer_his_rules_prereg_2026-10-24.md (not edited)")
say("")
T = pd.read_csv(H + "entries.tsv", sep="\t", dtype=str, keep_default_na=False)
X = pd.read_csv(H + "exits.tsv", sep="\t", dtype=str, keep_default_na=False)
SN = pd.read_csv(H + "snapshots.tsv", sep="\t", dtype=str, keep_default_na=False)
SNI = SN.set_index("frame_id")
assert SNI.index.is_unique

with gzip.open(VIS + "positions_pct_calendar.pkl.gz", "rb") as fh:
    _cal_all, _sig = pickle.load(fh)
del _sig
CAL = [d for d in _cal_all if d <= CUT]          # dates only; anything after the cut is dropped at read
del _cal_all
SESS_A = [ln.strip() for ln in open(f"{DATA}/cb702_pre_v2/sessions.txt") if ln.strip()]
assert CAL[:len(SESS_A)] == SESS_A, "calendar cache does not start with sessions_A"
assert all(a < b for a, b in zip(CAL, CAL[1:]))
CI = {d: i for i, d in enumerate(CAL)}
say(f"- inputs: entries {len(T):,} rows, exits {len(X):,}, snapshots {len(SN):,}; calendar {CAL[0]}..{CAL[-1]} = {len(CAL):,} sessions "
    f"(era A sessions.txt {len(SESS_A):,}, last {SESS_A[-1]}); nothing after {CUT} kept")

ni = T[T.initial == "False"].copy()
ni["wl"] = pd.to_numeric(ni.window_len)
ni["flick"] = ni.flicker == "True"
ni["dec"] = ni.decides == "True"
ni["Eb"] = np.where(ni.setup == "undated", ni.lo, ni.E)            # buy day: the event day if dated, else the window start (holdings load_events)
for c in ("lo", "hi", "exit_lo", "exit_hi", "Eb"):
    ni[c + "_i"] = ni[c].map(lambda d: CI[d] if d in CI else -1)
ni["has_exit"] = ni.exit_hi_i >= 0
ni["undated"] = ni.setup == "undated"
ni["noev"] = ni.undated & (ni.undated_reason == "no_event_in_window")
assert (ni.lo_i >= 0).all() and (ni.hi_i >= 0).all() and (ni.Eb_i >= 0).all()
assert ((ni.hi_i - ni.lo_i + 1) == ni.wl).all(), "window_len != sessions in [lo, hi]"
m_ = ni.merge(X[["eid", "exit_lo", "exit_hi"]], on="eid", suffixes=("", "_x"))
assert ((m_.exit_lo == m_.exit_lo_x) & (m_.exit_hi == m_.exit_hi_x)).sum() == ni.has_exit.sum(), "exits.tsv disagrees with entries.tsv"


def inwin(df, win):
    return df[(df.Eb >= win[0]) & (df.Eb <= win[1])]


# ============================================================================================================== clocks (panel_clocks logic, re-derived)
def mins(c):
    if not c:
        return None
    h, m = c.split(":")
    return int(h) * 60 + int(m)


def _clock_cols(r):
    fc = flc = ""
    pctx = fctx = ""
    f = SNI.loc[r.first_frame] if r.first_frame in SNI.index else None
    p = SNI.loc[r.prev_full_frame] if (r.prev_full_frame and r.prev_full_frame in SNI.index) else None
    if f is not None:
        fctx = f.ctx
        if f.date == r.Eb and f.ctx != "pre":
            fc = f.clock
    if p is not None:
        pctx = p.ctx
        if p.date == r.Eb and p.ctx != "closed":
            flc = p.clock
    return pd.Series({"fc": fc, "flc": flc, "p_ctx": pctx, "f_ctx": fctx})


ni = pd.concat([ni, ni.apply(_clock_cols, axis=1)], axis=1)
dated = ni[~ni.undated]
assert (dated.fc == dated.first_clock_on_E).all() and (dated.flc == dated.flat_clock_on_E).all(), "re-derived clocks disagree with entries.tsv"

dec = ni[ni.dec]
noev = ni[ni.noev]
c633 = noev[(noev.wl <= 10) & (~noev.flick)]
ex_nf = noev[(noev.wl == 1) & (~noev.flick)]
ex_all = noev[noev.wl == 1]
multi_nf = noev[(noev.wl >= 2) & (noev.wl <= 10) & (~noev.flick)]

# ============================================================================================================== 0. headline
say("\n## 0. Headline counts and pins")
claim(26, "snapshots", 2907, len(SN))
claim(26, "buys (non-initial entries)", 1861, len(ni))
claim(26, "sells (non-initial entries with an exit window)", 1848, int(ni.has_exit.sum()))
claim(69, "entries / initial / non-initial", "1874 / 13 / 1861", f"{len(T)} / {int((T.initial == 'True').sum())} / {len(ni)}")
claim(69, "streams (distinct vid after duplicate-upload merge)", 517, SN.vid.nunique())
claim(69, "buy-window span (earliest window start .. latest first sighting, non-initial)", "2017-01 .. 2023-12", f"{ni.lo.min()[:7]} .. {ni.first_date.max()[:7]}")
g17 = sorted({d for d in SN.date if d.startswith("2017")})
claim(74, "2017 largest gap between stream dates (days)", 164, max((datetime.date.fromisoformat(b) - datetime.date.fromisoformat(a)).days for a, b in zip(g17, g17[1:])))
sha_doc = {"entries": "6a0dda2d", "exits": "1ed76a28", "snapshots": "a8987fce"}
for k, pfx in sha_doc.items():
    claim(383, f"holdings pin {k}.tsv sha prefix", pfx, sha(H + f"{k}.tsv")[:8])
claim(391, "holdings module (02_replay.py) sha prefix", "4275d72f",
      sha(os.path.join(REPO, "scripts/probes/_705_holdings_1024/02_replay.py"))[:8])
claim(359, "era A sessions (export 2016-01-04..2022-06-30)", 1634, len(SESS_A), "docs/methodology/backtest_data_standard.md l.31 also says 1,635")
claim(359, "era B first session / sessions kept to the cut", "2021-09-27 onward", f"{[d for d in CAL if d >= '2021-09-27'][0]}; {len([d for d in CAL if d >= '2021-09-27'])} sessions", kind="NOTE")

# ============================================================================================================== 1. population table
say("\n## 1. Population (L71-79)")
dated_all = ni[~ni.undated]
wide = dated_all[~dated_all.dec]
claim(73, "dated deciding n", 294, len(dec))
claim(73, "dated deciding names (distinct panel symbol)", 153, dec.sym.nunique())
claim(73, "dated deciding in dense window", 264, len(inwin(dec, DENSE)))
claim(73, "  2020 (01-27..12-31)", 149, len(inwin(dec, Y20)))
claim(73, "  2021-01-04..2022-06-14", 115, len(inwin(dec, Y2122)))
claim(73, "dated deciding with exit known", 290, int(dec.has_exit.sum()))
claim(74, "dated, window > 10 n", 50, len(wide))
claim(74, "dated, window > 10 names (distinct panel symbol)", 48, wide.sym.nunique(),
      f"distinct sym_a {wide.sym_a.nunique()}; sym UNION sym_a {len(set(wide.sym) | set(wide.sym_a))} (the doc's 48 only arises if a renamed symbol is counted twice)")
w_ex = wide[wide.has_exit]
claim(74, "dated wide: held-to-exit median (sessions, E .. exit window's last session, inclusive)", 116,
      float(np.median(w_ex.exit_hi_i - w_ex.Eb_i + 1)), f"{len(w_ex)} of {len(wide)} have an exit window")
claim(74, "dated wide: of the 50, buy event in 2017-18", 21, int(wide.E.str[:4].isin(["2017", "2018"]).sum()), "by event year; by window-start year it is 27")
claim(75, "no event, non-flicker, window <= 10 n", 633, len(c633))
claim(75, "  names", 274, c633.sym.nunique())
claim(75, "  window 1 (exact day)", 427, int((c633.wl == 1).sum()))
claim(75, "  window 2", 103, int((c633.wl == 2).sum()))
claim(75, "  window 3-5", 66, int(((c633.wl >= 3) & (c633.wl <= 5)).sum()))
claim(75, "  window 6-10", 37, int(((c633.wl >= 6) & (c633.wl <= 10)).sum()))
claim(54, "multi-session (2-10) no-event non-flicker windows", 206, int((c633.wl >= 2).sum()))
c349 = noev[(noev.wl <= 10) & noev.flick]
claim(76, "no event, flicker, window <= 10 n", 349, len(c349))
claim(76, "  names", 196, c349.sym.nunique())
claim(76, "  exact-day flickers", 273, int((c349.wl == 1).sum()))
claim(77, "no event, window > 10 n", 58, int((noev.wl > 10).sum()))
nc = ni[ni.undated_reason == "never_candidate"]
claim(78, "never a candidate n", 360, len(nc))
claim(78, "  names", 147, nc.sym.nunique())
vc = nc.sym.value_counts()
claim(78, "  TQQQ 26, SOXL 21, TNA 16, GBTC 15, ETHE 14, SPXL 14", "26/21/16/15/14/14", "/".join(str(int(vc.get(s, 0))) for s in ("TQQQ", "SOXL", "TNA", "GBTC", "ETHE", "SPXL")))
nb = ni[ni.undated_reason == "no_bars"]
claim(79, "no bars n", 117, len(nb))
claim(79, "  names", 81, nb.sym.nunique())
claim(79, "  NO, SBE, TVIX, ICP, CCIV all in the no-bars list", "all five", "all five" if all(s in set(nb.sym) for s in ("NO", "SBE", "TVIX", "ICP", "CCIV")) else "NOT all")
claim(71, "the seven groups sum to the non-initial entries", 1861, len(dec) + len(wide) + len(c633) + len(c349) + int((noev.wl > 10).sum()) + len(nc) + len(nb))

# ============================================================================================================== 2. events just outside the window
say("\n## 2. The 633 against our events just outside their window (L81-86)")
cols = ["ticker", "D", "E", "K", "split"]
ca = pd.read_csv(f"{DATA}/cb702_pre_v2/out/candidates_tl_com.tsv", sep="\t", dtype=str, keep_default_na=False, usecols=cols)
cb = pd.read_csv(f"{DATA}/cb702/out/candidates.tsv", sep="\t", dtype=str, keep_default_na=False, usecols=cols)
ca = ca[ca.E <= A_LAST]
cb = cb[(cb.E <= CUT) & (cb.D <= CUT) & (cb.E >= B_FIRST) & (cb.split == "discovery")]      # the timeline's rule: era B discovery only, cut at read
EV = {k: collections.defaultdict(set) for k in ("tl", "other", "ep")}
for era, df in (("A", ca), ("B", cb)):
    for r in df.itertuples():
        EV["tl" if r.K == "tl" else "other"][(era, r.ticker)].add(r.E)
for era, p, lo_, hi_ in (("A", f"{QS}ep_join_1023/ep_events_A.tsv.gz", "0000-00-00", A_LAST), ("B", f"{QS}ep_join_1023/ep_events_B.tsv.gz", B_FIRST, CUT)):
    e = pd.read_csv(p, sep="\t", dtype=str, keep_default_na=False, usecols=["ticker", "E", "primary"])
    e = e[(e.primary == "True") & (e.E >= lo_) & (e.E <= hi_)]
    for r in e.itertuples():
        EV["ep"][(era, r.ticker)].add(r.E)
say(f"- event files read (ticker/D/E/K/split, ticker/E/primary only): tl A {sum(len(v) for k, v in EV['tl'].items() if k[0] == 'A'):,} (name,E) pairs, "
    f"tl B {sum(len(v) for k, v in EV['tl'].items() if k[0] == 'B'):,}; other levels (com / k5 / k10 / full) "
    f"{sum(len(v) for v in EV['other'].values()):,}; EP primary {sum(len(v) for v in EV['ep'].values()):,}")


def evs(kind, r):
    return EV[kind].get(("A", r.sym_a), set()) | EV[kind].get(("B", r.sym), set())


rows = []
for r in c633.itertuples():
    base = evs("tl", r) | evs("ep", r)
    oth = evs("other", r)
    assert not any(r.lo <= e <= r.hi for e in base), "a no-event entry has a tl / EP event inside its window"
    ti = [CI[e] for e in base if e in CI]
    before = [r.lo_i - x for x in ti if x < r.lo_i]
    after = [x - r.hi_i for x in ti if x > r.hi_i]
    rows.append(dict(eid=r.eid, oth=any(r.lo <= e <= r.hi for e in oth), b15=any(1 <= x <= 5 for x in before), b620=any(6 <= x <= 20 for x in before),
                     a15=any(1 <= x <= 5 for x in after)))
R = pd.DataFrame(rows)
cls = np.where(R.oth, "other_level", np.where(R.b15, "before_1_5", np.where(R.a15, "after_1_5", np.where(R.b620, "before_6_20", "none"))))
cc = collections.Counter(cls)
say("- priority used (a partition; stated nowhere in the doc): other-level fired inside the window first, then 1-5 sessions before, then 1-5 after, then 6-20 before")
claim(82, "none of our events within 20 sessions before or 5 after", 343, cc["none"])
claim(82, "one 6-20 sessions before", 97, cc["before_6_20"])
claim(83, "one 1-5 sessions before", 69, cc["before_1_5"])
claim(83, "one 1-5 sessions AFTER the window", 77, cc["after_1_5"], f"{int(R.a15.sum())} of the 633 have an event 1-5 sessions after at all; {int((R.a15 & R.b15).sum())} of them also have one 1-5 before (counted under 'before')")
claim(85, "one of our OTHER level definitions fired inside the window", 47, cc["other_level"])
claim(81, "the five classes sum to", 633, sum(cc.values()))
byyr = c633.hi.str[:4].value_counts().sort_index().to_dict()
byyr_lo = c633.lo.str[:4].value_counts().sort_index().to_dict()
claim(85, "by 'buy year' (as printed: 2017/2019/2020/2021/2022/2023)", "6/67/301/198/45/16", "/".join(str(byyr.get(y, 0)) for y in ("2017", "2019", "2020", "2021", "2022", "2023")),
      "matches the WINDOW-END (stream) year only", kind="OK" if all(byyr.get(y, 0) == v for y, v in zip(("2017", "2019", "2020", "2021", "2022", "2023"), (6, 67, 301, 198, 45, 16))) else "MISMATCH")
claim(85, "by buy year under the holdings module's own E (= window start for undated)", "6/67/301/198/45/16", "/".join(str(byyr_lo.get(y, 0)) for y in ("2017", "2019", "2020", "2021", "2022", "2023")),
      "the module's `load_events` sets E = lo for undated buys and takes the year from E")
era_lo = c633.lo.map(lambda d: "A" if d <= A_LAST else "B").value_counts().to_dict()
era_hi = c633.hi.map(lambda d: "A" if d <= A_LAST else "B").value_counts().to_dict()
claim(86, "era-A / era-B windows (era by window start, the R10 buy-day rule with E = lo)", "596 / 37", f"{era_lo.get('A', 0)} / {era_lo.get('B', 0)}", f"by window end it is {era_hi.get('A', 0)} / {era_hi.get('B', 0)}")
claim(86, "touch the Q1-2022 hole", 24, int((c633.q1_2022_hole == "True").sum()))

# ============================================================================================================== 3. exact-day table
say("\n## 3. Exact-day sets (L88-94)")


def tdays(df, to="exit_hi_i"):
    d = df[df[to] >= 0]
    return int((d[to] - d.Eb_i + 1).sum())


def med_held(df):
    d = df[df.exit_hi_i >= 0]
    return float(np.median(d.exit_hi_i - d.Eb_i + 1))


claim(92, "exact non-flicker: all years", 427, len(ex_nf))
claim(92, "  exits known", 427, int(ex_nf.has_exit.sum()))
claim(92, "  dense window", 374, len(inwin(ex_nf, DENSE)))
claim(92, "  2020", 197, len(inwin(ex_nf, Y20)))
claim(92, "  2021-22", 177, len(inwin(ex_nf, Y2122)))
claim(92, "  trade-days all years (E .. exit window's last session, inclusive)", 4436, tdays(ex_nf))
claim(92, "  trade-days to the window's FIRST session", 3203, tdays(ex_nf, "exit_lo_i"))
claim(92, "  held to the window's last session, median", 6, med_held(ex_nf))
claim(93, "exact incl flickers: all years", 700, len(ex_all))
claim(93, "  flickers", 273, int(ex_all.flick.sum()))
claim(93, "  left by the buy day's close (exit window ends on E)", 161, int((ex_all.exit_hi_i == ex_all.Eb_i).sum()))
claim(93, "  dense window", 615, len(inwin(ex_all, DENSE)))
claim(93, "  2020", 335, len(inwin(ex_all, Y20)))
claim(93, "  2021-22", 280, len(inwin(ex_all, Y2122)))
claim(93, "  trade-days in the dense window", 3438, tdays(inwin(ex_all, DENSE)))
claim(93, "  held to the window's last session, median", 3, med_held(ex_all))
claim(94, "dated deciding: n", 294, len(dec))
claim(94, "  exits known", 290, int(dec.has_exit.sum()))
claim(94, "  same-day exits (exit window ends on E): all 294", 42, int((dec.exit_hi_i == dec.Eb_i).sum()), f"of the 264 in the window: {int((inwin(dec, DENSE).exit_hi_i == inwin(dec, DENSE).Eb_i).sum())}")
claim(94, "  flickers", 91, int(dec.flick.sum()))
claim(94, "  dense / 2020 / 2021-22", "264 / 149 / 115", f"{len(inwin(dec, DENSE))} / {len(inwin(dec, Y20))} / {len(inwin(dec, Y2122))}")
claim(94, "  trade-days all years", 3351, tdays(dec))
claim(94, "  trade-days to the window's first session", 2260, tdays(dec, "exit_lo_i"))
claim(94, "  held to the window's last session, median", 5, med_held(dec))
claim(47, "of the 264 dated in the dense window, left the panel by the buy day's close", 42, int((inwin(dec, DENSE).exit_hi_i == inwin(dec, DENSE).Eb_i).sum()))
claim(264, "exit window one session wide: dated in window", 183, int(((inwin(dec, DENSE).exit_hi_i == inwin(dec, DENSE).exit_lo_i) & inwin(dec, DENSE).has_exit).sum()))
claim(264, "exit window one session wide: overall of the exits", "1120 of 1848", f"{int(((ni.exit_hi_i == ni.exit_lo_i) & ni.has_exit).sum())} of {int(ni.has_exit.sum())}")
claim(166, "SELECT fit 2020 / flickers beside / check 2021-22 / flickers beside", "197 / +138 / 177 / +103",
      f"{len(inwin(ex_nf, Y20))} / +{len(inwin(ex_all, Y20)) - len(inwin(ex_nf, Y20))} / {len(inwin(ex_nf, Y2122))} / +{len(inwin(ex_all, Y2122)) - len(inwin(ex_nf, Y2122))}")
by_year_ex = ex_nf.Eb.str[:4].value_counts().to_dict()
claim(167, "beside: 2017 / 2019 / 2023 exact-day non-flicker buys", "1 / 35 / 7", f"{by_year_ex.get('2017', 0)} / {by_year_ex.get('2019', 0)} / {by_year_ex.get('2023', 0)}")
claim(288, "EXIT fit: undated 2020 exact-day, flickers included: n / trade-days", "335 / 1900", f"{len(inwin(ex_all, Y20))} / {tdays(inwin(ex_all, Y20))}")
claim(289, "EXIT check: undated 2021-22 exact-day, flickers included: n / trade-days", "280 / 1538", f"{len(inwin(ex_all, Y2122))} / {tdays(inwin(ex_all, Y2122))}")
claim(244, "STOP fit: dated 2020 (117 filled + 32 proxies = 149) and undated 2020 flickers included", "149 / 335", f"{len(inwin(dec, Y20))} / {len(inwin(ex_all, Y20))}", "the 117 / 32 split is a replay outcome: not recountable from the allowed inputs")

# the flicker asymmetry sentence (L299)
fit_exit = pd.concat([dec[dec.has_exit], inwin(ex_all, Y20)])
chk_exit = inwin(ex_all, Y2122)
claim(299, "EXIT check set share of flickers (%)", 37, round(100 * chk_exit.flick.mean()))
claim(299, "EXIT fit set share of flickers (%) (fit = 290 dated with exits + 335 undated 2020, L287)", 31, round(100 * fit_exit.flick.mean()),
      f"31% is the dated part alone ({round(100 * dec[dec.has_exit].flick.mean())}%); the undated 2020 part is {round(100 * inwin(ex_all, Y20).flick.mean())}%; combined {100 * fit_exit.flick.mean():.1f}% vs check {100 * chk_exit.flick.mean():.1f}%")

# same-day re-buys (the holdings module's F4 rule, re-derived from the entries)
nb_ = ni[ni.has_bars == "True"].copy()
nb_["era2"] = np.where(nb_.undated, np.where(nb_.Eb <= A_LAST, "A", "B"), nb_.era)
nb_["tk"] = np.where(nb_.era2 == "A", nb_.sym_a, nb_.sym)
seen, rebuy = {}, set()
for r in nb_.assign(en=nb_.eid.astype(int)).sort_values("en").itertuples():
    k = (r.era2, r.tk, r.Eb, r.undated)
    if k not in seen:
        seen[k] = r.eid
    else:
        rebuy.add(r.eid)
dwin = inwin(dec, DENSE)
claim(212, "262 dated buys in the window = 264 less same-day re-buys", 262, len(dwin) - int(dwin.eid.isin(rebuy).sum()))
claim(246, "dated 2021-22: 115 deciding, walked after the two same-day re-buys", 113, len(inwin(dec, Y2122)) - int(inwin(dec, Y2122).eid.isin(rebuy).sum()))
claim("--", "same-day re-buys INSIDE the registration's undated sets (doc is silent)", "not stated",
      f"427-set {int(ex_nf.eid.isin(rebuy).sum())}; 197 fit {int(inwin(ex_nf, Y20).eid.isin(rebuy).sum())}; 700-set {int(ex_all.eid.isin(rebuy).sum())}; 335 fit {int(inwin(ex_all, Y20).eid.isin(rebuy).sum())}; 280 check {int(inwin(ex_all, Y2122).eid.isin(rebuy).sum())}",
      "the holdings module walks none of them; a second entry of a name on its day repeats the same bar state", kind="NOTE")
claim("--", "inverted windows INSIDE the exact-day sets (window forced to 1 by lo := hi; doc calls all of them EXACT)", "not stated",
      f"{int((ex_nf.inverted == 'True').sum())} of 427; {int((ex_all.inverted == 'True').sum())} of 700", kind="NOTE")

# ============================================================================================================== 4. clocks
say("\n## 4. The clock on the buy day (L96-101, L201-208)")
fcn = dwin[dwin.fc != ""]
fl = dwin[dwin.flc != ""]
br_any = dwin[(dwin.fc != "") & (dwin.flc != "")]
br_in = dwin[(dwin.fc != "") & (dwin.p_ctx == "in") & (dwin.flc != "")]
w_any = (br_any.fc.map(mins) - br_any.flc.map(mins)).to_numpy()
claim(97, "dated in window: first seen in session on the buy day", 172, len(fcn))
claim(97, "dated: flat at a full IN-SESSION snapshot on the buy day (L98 wording; L96-97 define flat_clock as 'that session')", 185, int((fl.p_ctx == "in").sum()),
      f"185 counts every full frame without the name on E, incl. {int((fl.p_ctx == 'pre').sum())} taken PRE-MARKET (before the open)")
claim(98, "dated: both (a bracket) = first seen in session AND an IN-SESSION flat frame on E (the rule the undated 108 uses)", 135, len(br_in),
      f"135 reproduces only if a pre-market flat frame counts ({len(br_any)}); {len(br_any) - len(br_in)} of the 135 are pre-market-flat")
claim(98, "  2020 / 2021-22 (in-session flat rule)", "73 / 62", f"{int((br_in.Eb <= '2020-12-31').sum())} / {int((br_in.Eb > '2020-12-31').sum())}",
      f"the any-context rule gives {int((br_any.Eb <= '2020-12-31').sum())} / {int((br_any.Eb > '2020-12-31').sum())}")
w_in = (br_in.fc.map(mins) - br_in.flc.map(mins)).to_numpy()
claim(98, "dated bracket width median (minutes; in-session rule)", 36, float(np.median(w_in)), f"any-context rule: {float(np.median(w_any)):.0f}")
claim(98, "dated bracket width quartiles (in-session rule)", "21-59", f"{np.percentile(w_in, 25):.0f}-{np.percentile(w_in, 75):.0f}", f"any-context rule: {np.percentile(w_any, 25):.0f}-{np.percentile(w_any, 75):.0f}")
claim(98, "dated bracket: <= 30 minutes (in-session rule)", 57, int((w_in <= 30).sum()), f"any-context rule: {int((w_any <= 30).sum())}")
inf = dwin[dwin.orh5_infeasible == "True"]
claim(99, "dated in window held before 09:35", 9, len(inf))
claim(99, "  the nine (ticker date)", "TSLA 2020-04-14, UAL 2020-05-27, DXCM 2020-07-29, PINS 2020-07-31, SHOP 2020-08-26, TTD 2020-08-26, KOLD 2022-04-19, LAC 2022-04-21, TSLA 2022-04-21",
      ", ".join(f"{r.sym} {r.E}" for r in inf.sort_values("E").itertuples()))
for nm, df, nfc_doc, br_doc, med_doc, y_doc, h935 in (("exact non-flicker", ex_nf, 237, 108, 34, "60 / 48", 1), ("exact incl flickers", ex_all, None, 175, None, "103 / 72", None)):
    dn = inwin(df, DENSE)
    f1 = dn[dn.fc != ""]
    b_in = dn[(dn.fc != "") & (dn.p_ctx == "in") & (dn.flc != "")]
    b_any = dn[(dn.fc != "") & (dn.flc != "")]
    wi = (b_in.fc.map(mins) - b_in.flc.map(mins))
    if nfc_doc is not None:
        claim(100, f"{nm}: first seen in session (2020 / 2021-22 = 122 / 115)", nfc_doc, len(f1), f"{int((f1.Eb <= '2020-12-31').sum())} / {int((f1.Eb > '2020-12-31').sum())}")
    claim(101, f"{nm}: bracketed (flat frame IN-SESSION context)", br_doc, len(b_in), f"2020 / 2021-22 = {int((b_in.Eb <= '2020-12-31').sum())} / {int((b_in.Eb > '2020-12-31').sum())} (doc {y_doc})")
    claim(101, f"{nm}: bracketed under the ANY-context rule the dated 135 uses", "(not stated)", len(b_any), kind="NOTE")
    claim(101, f"{nm}: in-session bracket width median", med_doc if med_doc else "(not stated)", float(wi.median()),
          "the doc's 34 is the with-flickers median" if nm == "exact non-flicker" else "", kind=None if med_doc else "NOTE")
    if h935 is not None:
        claim(101, f"{nm}: held before 09:35", h935, int(dn.fc.map(lambda x: x != "" and x < "09:35").sum()))
claim(201, "unbracketed in-session sightings: dated (no flat frame at all that day)", 37, int(((dwin.fc != "") & (dwin.flc == "")).sum()),
      f"counting a pre-market-only flat frame as 'no in-session flat' (the undated 129 is counted that way) it is {len(fcn) - len(br_in)}")
dn = inwin(ex_nf, DENSE)
claim(201, "unbracketed in-session sightings: undated 'no flat frame that day'", 129, int(((dn.fc != "") & (dn.p_ctx != "in")).sum()),
      f"all {int(((dn.fc != '') & (dn.p_ctx != 'in') & (dn.flc != '')).sum())} of them DO have a pre-market flat frame on E - the dated rule counts that as a bracket")
claim(202, "pre-market first sightings, dated in window", 80, int((dwin.f_ctx == "pre").sum()))
d20 = inwin(dec, Y20)
b20 = d20[(d20.fc != "") & (d20.flc != "")]
d21 = inwin(dec, Y2122)
b21 = d21[(d21.fc != "") & (d21.flc != "")]
b20i = d20[(d20.fc != "") & (d20.p_ctx == "in") & (d20.flc != "")]
b21i = d21[(d21.fc != "") & (d21.p_ctx == "in") & (d21.flc != "")]
u20 = len(inwin(ex_nf, Y20)[(inwin(ex_nf, Y20).fc != '') & (inwin(ex_nf, Y20).p_ctx == 'in')])
u20f = len(inwin(ex_all, Y20)[(inwin(ex_all, Y20).fc != '') & (inwin(ex_all, Y20).p_ctx == 'in')])
claim(205, "ENTER fit 2020: bracketed dated + bracketed exact-day undated (flickers in brackets), one rule for both (in-session flat)", "73 + 60 (103)",
      f"{len(b20i)} + {u20} ({u20f})", f"73 is the any-context dated count ({len(b20)}); the doc's two sets use different rules")
u21 = len(inwin(ex_nf, Y2122)[(inwin(ex_nf, Y2122).fc != '') & (inwin(ex_nf, Y2122).p_ctx == 'in')])
u21f = len(inwin(ex_all, Y2122)[(inwin(ex_all, Y2122).fc != '') & (inwin(ex_all, Y2122).p_ctx == 'in')])
claim(205, "ENTER check 2021-22: bracketed dated + bracketed exact-day undated (flickers in brackets), one rule for both (in-session flat)", "62 + 48 (72)",
      f"{len(b21i)} + {u21} ({u21f})", f"62 is the any-context dated count ({len(b21)})")
claim(211, "held before 09:35: dated in window + exact-day undated non-flicker in window", "9 + 1", f"{len(inf)} + {int(inwin(ex_nf, DENSE).fc.map(lambda x: x != '' and x < '09:35').sum())}")
claim(208, "binomial half-width of a 50% share on 48 trades (points)", 14, round(196 * (0.25 / 48) ** 0.5, 0))

# ============================================================================================================== 5. re-buys
say("\n## 5. Re-buys (L103-104)")
allx = T.copy()
allx["n"] = allx.eid.astype(int)
cnt = allx.groupby("sym").size()
claim(103, "panel names (distinct symbol over all entries)", 684, len(cnt))
claim(103, "names with more than one entry", 280, int((cnt > 1).sum()))
cn = allx[allx.initial == "False"].groupby("sym").size()
claim(103, "entries of those names (non-initial)", 1467, int(cn[cn > 1].sum()), f"all {int(cnt[cnt > 1].sum())} incl. initial holdings")
exit_by_eid = allx.set_index("eid")
reb = []
for sym, g in allx.sort_values("n").groupby("sym"):
    prev = None
    for r in g.itertuples():
        if prev is not None and prev.initial == "False" and r.initial == "False" and prev.exit_hi:
            gap = (datetime.date.fromisoformat(r.lo) - datetime.date.fromisoformat(prev.exit_hi)).days
            if 0 <= gap <= 14:
                reb.append(dict(eid=r.eid, year=r.lo[:4], dec=r.decides == "True", undated=r.setup == "undated"))
        prev = r
RB = pd.DataFrame(reb)
claim(104, "entries opening 0..14 calendar days after the same name's previous (non-initial) entry's exit window's last session", 564, len(RB),
      "reading found by search (window start vs previous exit_hi, previous entry not an initial holding); 559-567 under neighbouring readings")
yy = RB.year.value_counts().to_dict()
claim(104, "  by year 2020 / 2021 / 2019 / 2022", "282 / 184 / 60 / 28", f"{yy.get('2020', 0)} / {yy.get('2021', 0)} / {yy.get('2019', 0)} / {yy.get('2022', 0)}")
claim(104, "  deciding / undated", "75 / 486", f"{int(RB.dec.sum())} / {int(RB.undated.sum())}")

# ============================================================================================================== 6. captions
say("\n## 6. Captions (L106-111, L129, L324)")
sys.path.insert(0, QMLIB_DIR)
import qmlib  # the project's caption parser for this exact folder (rolling-repeat de-duplication)

VS = pd.read_csv(QS + "video_status.tsv", sep="\t", dtype=str, keep_default_na=False).set_index("id")
paths = sorted(glob.glob(QS + "subs/*.vtt"))
claim(106, "videos with a caption track (vtt files)", 495, len(paths))
claim(106, "video_status: status ok / track en-orig", "495 / 495", f"{int((VS.status == 'ok').sum())} / {int((VS.track == 'en-orig').sum())}")
yr_tot = VS[VS.upload_date != ""].groupby(VS.upload_date.str[:4]).size()
yr_nocaps = VS[VS.status == "nocaps"].groupby(VS.upload_date.str[:4]).size()
claim(324, "2021 streams without a caption track", "44 of 189", f"{int(yr_nocaps.get('2021', 0))} of {int(yr_tot.get('2021', 0))}")
claim(324, "2022 streams without a caption track", "35 of 64", f"{int(yr_nocaps.get('2022', 0))} of {int(yr_tot.get('2022', 0))}")
WORDS = {os.path.basename(p).split(".")[0]: qmlib.parse_vtt(p) for p in paths}
TXT, OFF, TIM = {}, {}, {}
for v, ws in WORDS.items():
    toks = [w.lower() for _, w in ws]
    offs, pos = [], 0
    for w in toks:
        offs.append(pos)
        pos += len(w) + 1
    TXT[v], OFF[v], TIM[v] = " ".join(toks), offs, [t for t, _ in ws]
say(f"- {len(WORDS)} videos parsed, {sum(len(x) for x in WORDS.values()):,} words (qmlib.parse_vtt, lowercased, joined by spaces)")

FORMS = {"i sold": r"\bi sold\b", "stopped out": r"\bstopped out\b", "i got stopped": r"\bi got stopped\b", "stopped me out": r"\bstopped me out\b",
         "sold some": r"\bsold some\b", "sold a third": r"\bsold a third\b", "sold half": r"\bsold half\b", "sold everything": r"\bsold everything\b",
         "took partials": r"\btook partials?\b", "took profits": r"\btook profits?\b", "trimmed": r"\btrimmed\b", "i closed it": r"\bi closed it\b"}
form_n = {}
for k, rx in FORMS.items():
    r_ = re.compile(rx)
    form_n[k] = sum(len(r_.findall(t)) for t in TXT.values())
claim(108, "'i sold' occurrences", 1221, form_n["i sold"])
claim(108, "'stopped out' occurrences (doc: 'the two forms i sold and stopped out each 1,221')", 1221, form_n["stopped out"],
      f"{sum(len(re.findall(r'(?<!i got )stopped out', t)) for t in TXT.values())} when not part of 'i got stopped out'; no reading gives 1,221")
claim(108, "'i got stopped' occurrences", 883, form_n["i got stopped"])
claim(109, "'stopped me out' occurrences", 321, form_n["stopped me out"])


def phrase_hits(rxs):
    rx = re.compile("|".join(rxs))
    out = []
    for v, txt in TXT.items():
        for m in rx.finditer(txt):
            i = bisect.bisect_right(OFF[v], m.start()) - 1
            out.append((v, TIM[v][i], m.group(0)))
    return out


LISTED = list(FORMS.values())                                                       # the L106-108 list
CLASSES = [r"\bstopped out\b", r"\bgot stopped\b", r"\bstopped me out\b", r"\bi sold\b", r"\bsold it\b", r"\bsold all\b", r"\bsold everything\b",
           r"\bsold out\b", r"\bsold a third\b", r"\bsold half\b", r"\bsold some\b", r"\btook partials?\b", r"\btook profits?\b", r"\btrimmed\b",
           r"\bi closed it\b"]                                                     # the L316-319 classes + 'i closed it'

MOM = pd.read_csv(QS + "stream_moments.tsv", sep="\t", dtype=str, keep_default_na=False, usecols=["video", "t", "ticker"])
MOM["tf"] = MOM.t.astype(float)
MG = {v: g.sort_values("tf") for v, g in MOM.groupby("video")}
byname = collections.defaultdict(list)
for r in ni[ni.has_exit].itertuples():
    byname[r.sym].append(r)
    if r.sym_a != r.sym:
        byname[r.sym_a].append(r)
deciding_eids = set(dec.eid)


def census(label, rxs):
    hits = phrase_hits(rxs)
    yrs = collections.Counter()
    vids = set()
    near, qual, amb, trades = 0, 0, 0, set()
    q_yrs = collections.Counter()
    for v, t, ph in hits:
        up = VS.loc[v].upload_date
        yrs[up[:4]] += 1
        vids.add(v)
        g = MG.get(v)
        if g is None:
            continue
        ts = g.tf.to_numpy()
        lo_, hi_ = bisect.bisect_left(ts, t - 30), bisect.bisect_right(ts, t + 30)
        if hi_ <= lo_:
            continue
        near += 1
        s0 = bisect.bisect_right(CAL, f"{up[:4]}-{up[4:6]}-{up[6:]}") - 1
        quals = {r.eid for tk in set(g.ticker.iloc[lo_:hi_]) for r in byname.get(tk, ()) if r.exit_lo_i - 1 <= s0 <= r.exit_hi_i + 2}
        if quals:
            qual += 1
            q_yrs[up[:4]] += 1
            amb += int(len(quals) > 1)
            trades |= quals
    res = dict(hits=len(hits), videos=len(vids), yrs=dict(sorted(yrs.items())), near=near, qual=qual, amb=amb, trades=len(trades),
               deciding=len(trades & deciding_eids), q2020=q_yrs.get("2020", 0), q2021=q_yrs.get("2021", 0))
    say(f"- phrase set '{label}': {res}")
    return res


R_LIST = census("listed forms (L106-108)", LISTED)
R_CLS = census("section-9 classes + i closed it", CLASSES)
for key, doc, ln in (("hits", 4055, 107), ("videos", 478, 107), ("near", 2281, 109), ("qual", 795, 110), ("trades", 381, 110), ("deciding", 89, 110), ("amb", 153, 110),
                     ("q2020", 504, 110), ("q2021", 212, 110)):
    ok = (R_LIST[key] == doc) or (R_CLS[key] == doc)
    claim(ln, f"caption census '{key}'", doc, f"listed {R_LIST[key]} | classes {R_CLS[key]}", kind="OK" if ok else "MISMATCH")
doc_yrs = {"2020": 2244, "2021": 895, "2017": 436, "2019": 338, "2022": 89, "2023": 40, "2018": 13}
claim(108, "hits by upload year (2020/2021/2017/2019/2022/2023/2018)", "2244/895/436/338/89/40/13",
      "listed " + "/".join(str(R_LIST["yrs"].get(y, 0)) for y in doc_yrs) + " | classes " + "/".join(str(R_CLS["yrs"].get(y, 0)) for y in doc_yrs),
      kind="OK" if (R_LIST["yrs"] == doc_yrs or R_CLS["yrs"] == doc_yrs) else "MISMATCH")
claim(324, "795 joins reach 381 of 1,848 exits (%)", 21, round(100 * 381 / 1848))

# ============================================================================================================== 7. minute coverage + the fetch list
say("\n## 7. Minute coverage (fetch logs and directory listings only) and the fetch list (L365-368, L425)")


def load_done(tree, cut=None):
    out = {}
    with open(tree + "/_done.psv") as fh:
        for ln in fh:
            f = ln.rstrip("\n").split("|")
            if len(f) < 4 or (cut and f[0] > cut):
                continue
            out[(f[0], f[1])] = f[3]
    return out


def date_files(tree):
    return {fn[:-7] for fn in os.listdir(tree) if fn.endswith(".psv.gz")}


DONE = {k: load_done(v, CUT) for k, v in TREES.items()}
DFILES = {k: date_files(v) for k, v in TREES.items()}
ODONE = {k: load_done(v, CUT) for k, v in OTHER_TREES.items()}
OFILES = {k: date_files(v) for k, v in OTHER_TREES.items()}
say("- fetch-log pairs read: " + ", ".join(f"{k} {len(v):,}" for k, v in DONE.items()) + " | other local trees: " + ", ".join(f"{k} {len(v):,}" for k, v in ODONE.items()))


def bar_sym(date, sym_a, sym):
    """era A dates keyed by today's symbol (sym_a), era B dates point-in-time (sym): the doc's rule, L371."""
    return sym_a if date <= A_LAST else sym


def covered_pinned(date, sym_a, sym, trees=("A", "B", "EP", "EP2")):
    tk = bar_sym(date, sym_a, sym)
    for tr in trees:
        if DONE[tr].get((date, tk)) == "ok" and date in DFILES[tr]:
            return tr
    return None


def covered_other(date, sym_a, sym):
    tk = bar_sym(date, sym_a, sym)
    return any(ODONE[k].get((date, tk)) == "ok" and date in OFILES[k] for k in ODONE)


cov = ex_nf.apply(lambda r: covered_pinned(r.Eb, r.sym_a, r.sym), axis=1)
miss = ex_nf[cov.isna()]
claim(365, "exact-day no-event buys with minute bars on the buy day in the four trees", 32, int(cov.notna().sum()), f"trees: {cov.value_counts().to_dict()}")
claim(365, "  missing", 395, len(miss))
my_ = miss.Eb.str[:4].value_counts().to_dict()
claim(366, "  missing by year 2020 / 2021 / 2019 / 2022 / 2023 / 2017", "188 / 141 / 35 / 25 / 5 / 1", " / ".join(str(my_.get(y, 0)) for y in ("2020", "2021", "2019", "2022", "2023", "2017")))
claim(366, "  of the missing, covered only by the three other local trees", 0, int(miss.apply(lambda r: covered_other(r.Eb, r.sym_a, r.sym), axis=1).sum()), kind=None)
sess_rows = []
for r in multi_nf.itertuples():
    for i in range(r.lo_i, r.hi_i + 1):
        sess_rows.append((r.eid, CAL[i], r.sym_a, r.sym))
SR = pd.DataFrame(sess_rows, columns=["eid", "date", "sym_a", "sym"])
SR["cov"] = SR.apply(lambda r: covered_pinned(r.date, r.sym_a, r.sym), axis=1)
claim(367, "multi-session windows: sessions", 717, len(SR))
claim(367, "  covered", 22, int(SR["cov"].notna().sum()))
claim(367, "  windows", 206, SR.eid.nunique())
cov_dec = dec.apply(lambda r: next((tr for tr in (("EP", "EP2", "A", "B") if r.setup == "EP" else ("A", "B", "EP", "EP2"))
                                   if DONE[tr].get((r.E, r.sym_a if r.era == "A" else r.sym)) == "ok" and r.E in DFILES[tr]), None), axis=1)
claim(365, "deciding entries with minute bars on E", "290 of 294", f"{int(cov_dec.notna().sum())} of {len(dec)}",
      "uncovered: " + ", ".join(f"{r.sym} {r.E}" for r in dec[cov_dec.isna()].itertuples()) + " (no fetch-log row in any tree)")
fl_ex = ex_all[ex_all.flick]
cov_fl = fl_ex.apply(lambda r: covered_pinned(r.Eb, r.sym_a, r.sym), axis=1)
say(f"- exact-day flickers (included per L368): {len(fl_ex)}, covered {int(cov_fl.notna().sum())}, missing {int(cov_fl.isna().sum())}")

# the fetch list: exact-day (incl. flickers) + every window session of the 206 multi-session windows, minus what any local tree holds
PRIO = {"exact_nf": 0, "exact_flicker": 1, "window_session": 2}
need = {}                                                  # (bar symbol, date) -> (kind, panel symbol)


def add_need(tk, d, kind, sym):
    if (tk, d) not in need or PRIO[kind] < PRIO[need[(tk, d)][0]]:
        need[(tk, d)] = (kind, sym)


for r in ex_all.itertuples():
    add_need(bar_sym(r.Eb, r.sym_a, r.sym), r.Eb, "exact_flicker" if r.flick else "exact_nf", r.sym)
for r in SR.itertuples():
    add_need(bar_sym(r.date, r.sym_a, r.sym), r.date, "window_session", r.sym)
need_n = len(need)
fetch, hit_other = [], 0
for (tk, d), (kind, psym) in sorted(need.items(), key=lambda kv: (kv[0][1], kv[0][0])):
    if d > CUT:
        continue
    in_pinned = any(DONE[tr].get((d, tk)) == "ok" and d in DFILES[tr] for tr in DONE)
    in_other = any(ODONE[k].get((d, tk)) == "ok" and d in OFILES[k] for k in ODONE)
    hit_other += int((not in_pinned) and in_other)
    if not in_pinned and not in_other:
        fetch.append((tk, d, kind, psym))
by_kind = collections.Counter(k for _, _, k, _ in fetch)
by_year = collections.Counter(d[:4] for _, d, _, _ in fetch)
os.makedirs(FETCH_DIR, exist_ok=True)
with open(FETCH_LIST + ".partial", "w") as fh:
    for tk, d, _k, _p in fetch:
        fh.write(f"{tk}|{d}\n")
os.replace(FETCH_LIST + ".partial", FETCH_LIST)
say(f"- sessions the registration needs minute bars for: {need_n:,} distinct (ticker, date) pairs "
    f"(exact-day incl. flickers {sum(1 for v in need.values() if v[0] != 'window_session'):,} + window sessions only {sum(1 for v in need.values() if v[0] == 'window_session'):,}, deduplicated)")
say(f"- already held by a pinned tree or another local tree: {need_n - len(fetch):,} (of which only in an unpinned tree: {hit_other})")
say(f"- FETCH LIST: {len(fetch):,} pairs -> {FETCH_LIST} (format ticker|date, no header, sorted by date; NOT fetched here)")
say("  by kind: " + ", ".join(f"{k} {v}" for k, v in sorted(by_kind.items())))
say("  by year: " + ", ".join(f"{y} {n}" for y, n in sorted(by_year.items())) + f" | total {sum(by_year.values())} | latest date {max(d for _, d, _, _ in fetch)}")
assert max(d for _, d, _, _ in fetch) <= CUT
claim(425, "exact-day non-flicker pairs to fetch (doc: ~395 entries; distinct (ticker, date) pairs here)", "~395", by_kind.get("exact_nf", 0),
      "395 entries share 394 distinct pairs (one same-day re-buy)", kind="NOTE")
claim(425, "window sessions missing before dedupe (doc: ~695 = 717 - 22)", 695, int(SR["cov"].isna().sum()))
claim(368, "exact-day FLICKER pairs to fetch (L368 'included'; the doc's ~395 + ~695 leaves them out)", "not stated", int(cov_fl.isna().sum()), kind="NOTE")
claim(425, "total fetch size vs the doc's ~395 + ~695", "~1090", len(fetch), "the doc total omits the exact-day flickers", kind="MISMATCH" if abs(len(fetch) - 1090) > 20 else "OK")
alias_diff = [(tk, d, ps) for (tk, d, _k, ps) in fetch if ps != tk]
say(f"- fetch pairs whose bar symbol (today's name on era A dates) differs from the panel symbol: {len(alias_diff)}"
    + ("; e.g. " + ", ".join(f"{ps}->{tk} {d}" for tk, d, ps in alias_diff[:6]) if alias_diff else ""))
si = [(ps, d) for (tk, d, _k, ps) in fetch if d > A_LAST and ps != tk]
say(f"- era B dates use the panel's own symbol (point in time, L371), not sym_a: pairs where it matters {len(si)}" + (": " + ", ".join(f"{ps} {d}" for ps, d in si) if si else ""))
si2 = [(r.sym, r.sym_a, d) for (r, d) in [(r, r.Eb) for r in ex_all.itertuples()] if d > A_LAST and r.sym != r.sym_a]
say(f"- (sym_a would differ from sym on era-B dates for: {', '.join(f'{a}->{b} {c}' for a, b, c in si2) if si2 else 'none'}; the task wording says sym_a, the doc says point in time)")

# ============================================================================================================== not recountable
say("\n## Not recountable from the allowed inputs (outcome or price material; left unverified, not assumed)")
for ln, txt in ((16, "57 strict pairs with the talk before our event (the census)"),
                (119, "pool median ~2,460 names a day; planted-wrong-ticker rate 19% (needs the exports' prices)"),
                (212, "47 fills contradict the clock (needs the replay's fill minutes)"),
                (244, "117 filled + 32 close-fill proxies of the 149 (a replay outcome)"),
                (246, "S1 / our_status counts from the exits study: 20 of 24 early exits, 11 on day 0; 43 of 205 filled, 25 on day 0"),
                (306, "02_replay.txt l.174: final 20.53 (a replay equity)"),
                (49, "OCR symbol accuracy ~98%")):
    say(f"- [L{ln}] {txt}")

# ============================================================================================================== verdict
bad = [c for c in CLAIMS if c[4] == "MISMATCH"]
say(f"\n## RESULT: {len(CLAIMS)} lines, {sum(1 for c in CLAIMS if c[4] == 'OK')} OK, {len(bad)} MISMATCH, {sum(1 for c in CLAIMS if c[4] == 'NOTE')} NOTE")
for ln, label, doc, mine, status, note in bad:
    say(f"  MISMATCH [L{ln}] {label}: doc {fmt(doc)} vs mine {fmt(mine)}" + (f" ({note})" if note else ""))
with open(OUT_TXT, "w") as fh:
    fh.write("\n".join(LINES) + "\n")
