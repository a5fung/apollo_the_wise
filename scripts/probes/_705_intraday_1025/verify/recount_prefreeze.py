#!/usr/bin/env python3
"""Independent pre-freeze recount of docs/analysis/cb_intraday_layer_prereg_2026-10-25.md (REGISTERED, NOT FROZEN, NOT RUN).

Written WITHOUT importing 01_rev.py or 00_pop_fetch.py (neither is executed here; the registration and 00_pop_fetch.py are NOT edited).
Reads ONLY:
  - the holdings timeline's TSVs (entries / exits / snapshots) and the predecessor's dryrun_clocks.tsv (type_ok was the one column that
    could not be taken from the timeline - it is re-derived here from the two type tables and then compared; every other column of the
    dry-run table that can be re-derived is re-derived and compared, so the borrowed input is itself checked);
  - the session calendars (the pickle's date list cut at 2024-12-31 at read; sessions.txt of era A as the prefix check);
  - the minute trees' fetch logs (_done.psv) and DIRECTORY LISTINGS (coverage only - NO bar file of any tree is opened);
  - the two type tables (small_pulls.psv, cb702_sic.psv) to re-derive the type gate;
  - event DATES (candidates / EP events: ticker, D, E, K, split, primary only) for the one forward-event count;
  - the caption folder (subs/*.vtt) for the section-8 counts;
  - the predecessor's printouts (01_rev_check.txt, fit printouts, recount_check.txt, the SELECT chosen json) and the REV / delta_out trees'
    fetch.log, for the transcription checks of quoted numbers; operator_shared_notes.md for the quoted words and their line numbers.
No price, no minute bar, nothing dated after 2024-12-31 (asserted on every date list read), nothing of 2025-26. replay/ and his_exits/ are
never opened. The fetch lists on disk are only READ; this script's regenerated copies go to the scratchpad.

Output: one line per claim `[Ldoc] label | doc | mine | OK / MISMATCH / NOTE`; the MISMATCH lines are listed again at the end.
"""
import collections
import csv
import datetime
import glob
import gzip
import hashlib
import json
import math
import os
import pickle
import re
import sys

import numpy as np
import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.abspath(os.path.join(HERE, "..", "..", "..", ".."))
DATA = "/Users/alvinfung/apollo_data"
H = f"{DATA}/cb702/qm_streams/holdings_1024/"
QS = f"{DATA}/cb702/qm_streams/"
VIS = QS + "vision/"
SCRATCH = "/private/tmp/claude-501/-Users-alvinfung-apollo-the-wise/d30e3944-e07e-4b44-97de-010acba78d0b/scratchpad"
OUT_TXT = os.path.join(HERE, "recount_prefreeze.txt")
DOC = os.path.join(REPO, "docs", "analysis", "cb_intraday_layer_prereg_2026-10-25.md")
PREV_DIR = os.path.join(REPO, "scripts", "probes", "_705_reverse_1024")
INTRA_MIN = f"{DATA}/cb702/minutes_intra_1025"
LIST_FULL = f"{INTRA_MIN}/fetch_list_intra_1025.psv"
LIST_HOLD = f"{INTRA_MIN}/fetch_list_hold_only_intra_1025.psv"

CUT = "2024-12-31"
A_LAST = "2022-03-31"           # era by buy day: <= this A, else B
FIT = ("2020-01-27", "2020-12-31")
CHK = ("2021-01-04", "2022-06-14")
DENSE = ("2020-01-27", "2022-06-14")
WARM, TAIL, NOEXIT = 10, 20, 20
TREES = {"A": f"{DATA}/cb702_pre_v2/minutes", "B": f"{DATA}/cb702/minutes", "EP": f"{DATA}/cb702/minutes_ep_1023",
         "EP2": f"{DATA}/cb702/minutes_ep_1024", "REV": f"{DATA}/cb702/minutes_rev_1024"}
TREE_ORDER = ("A", "B", "EP", "EP2", "REV")
OTHER_TREES = {"com_delta_1018": f"{DATA}/cb702/minutes_com_delta_1018", "pre_com_1018": f"{DATA}/cb702/minutes_pre_com_1018",
               "delta_out": f"{DATA}/cb702/cb702_minutes_delta_out"}

LINES, CLAIMS = [], []
DL = open(DOC).read().splitlines()
UNRESOLVED = []


def LN(anchor):
    for i, ln in enumerate(DL, 1):
        if anchor in ln:
            return i
    UNRESOLVED.append(anchor)
    return "?"


def say(msg=""):
    print(msg, flush=True)
    LINES.append(msg)


def fmt(x):
    if isinstance(x, (list, tuple, dict, set)):
        return str(x)
    if isinstance(x, (float, np.floating)):
        return f"{x:.4g}"
    return str(x)


def claim(line, label, doc, mine, note="", kind=None):
    """doc / mine compared as printed text. kind: None -> OK if equal else MISMATCH; 'OK'/'MISMATCH' forced; 'NOTE' informational; 'NR' not recountable.
    `line` is a doc line number, '--' (not a doc claim) or '@anchor' (the first doc line containing the anchor text)."""
    if isinstance(line, str) and line.startswith("@"):
        line = LN(line[1:])
    status = ("OK" if fmt(doc) == fmt(mine) else "MISMATCH") if kind is None else kind
    CLAIMS.append((line, label, doc, mine, status, note))
    say(f"[L{line}] {label} | doc {fmt(doc)} | mine {fmt(mine)} | {status}" + (f" | {note}" if note else ""))
    return status


def sha(path):
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for ch in iter(lambda: fh.read(1 << 20), b""):
            h.update(ch)
    return h.hexdigest()


def hm(c):
    """'HH:MM' -> minutes since 09:30 (negative before the open); None for ''."""
    if not c:
        return None
    h, m = c.split(":")
    return int(h) * 60 + int(m) - 570


def assert_le_cut(dates, what):
    bad = [d for d in dates if d > CUT]
    assert not bad, f"{what}: dates after the 2024-12-31 cut were read: {bad[:3]}"


# ================================================================================================================ inputs
say("# #705 INTRADAY-LAYER registration: independent pre-freeze recount (OUTCOME-FREE: timeline TSVs, dry-run clocks, fetch logs, calendars)")
say("# registration: docs/analysis/cb_intraday_layer_prereg_2026-10-25.md (not edited); 00_pop_fetch.py not edited and not imported")
say("")
T = pd.read_csv(H + "entries.tsv", sep="\t", dtype=str, keep_default_na=False)
X = pd.read_csv(H + "exits.tsv", sep="\t", dtype=str, keep_default_na=False)
SN = pd.read_csv(H + "snapshots.tsv", sep="\t", dtype=str, keep_default_na=False)
DRY = pd.read_csv(H + "reverse/dryrun_clocks.tsv", sep="\t", dtype=str, keep_default_na=False)
SNI = SN.set_index("frame_id")
assert SNI.index.is_unique
assert DRY.eid.is_unique and len(DRY) == 1861

with gzip.open(VIS + "positions_pct_calendar.pkl.gz", "rb") as fh:
    _cal_all, _sig = pickle.load(fh)
del _sig
CAL = [d for d in _cal_all if d <= CUT]
del _cal_all
SESS_A = [ln.strip() for ln in open(f"{DATA}/cb702_pre_v2/sessions.txt") if ln.strip()]
assert CAL[:len(SESS_A)] == SESS_A, "calendar cache does not start with era A's sessions.txt"
assert all(a < b for a, b in zip(CAL, CAL[1:]))
CI = {d: i for i, d in enumerate(CAL)}
CALSET = set(CAL)
say(f"- inputs: entries {len(T):,} rows, exits {len(X):,}, snapshots {len(SN):,}, dryrun_clocks {len(DRY):,}; calendar {CAL[0]}..{CAL[-1]} = {len(CAL):,} sessions "
    f"(era A sessions.txt {len(SESS_A):,}, last {SESS_A[-1]}); nothing after {CUT} kept")

# ---- the type tables (re-derive the type gate; the registration says it read them) -------------------------------------------------
SMALL, SIC = {}, {}
for ln in open(f"{DATA}/cb702/small_pulls.psv").read().splitlines():
    f = ln.split("|")
    if f[0] == "sectype" and len(f) >= 3:
        SMALL[f[1]] = f[2]
for ln in open(f"{DATA}/cb702/cb702_sic.psv").read().splitlines():
    f = ln.split("|")
    if len(f) >= 6:
        SIC[f[0]] = f[5]


def type_of(t):
    if t == "LAZR":
        return "CS"                              # the registration's one override (Luminar: a stock in 2020-22, typed ETF today)
    if SMALL.get(t, ""):
        return SMALL[t]
    if SIC.get(t, ""):
        return SIC[t]
    return ""


# ================================================================================================================ per-entry fields
ni = T[T.initial == "False"].copy()
ni["eidn"] = ni.eid.astype(int)
ni["wl"] = pd.to_numeric(ni.window_len)
ni["flick"] = ni.flicker == "True"
ni["dated"] = ni.setup.isin(["breakout", "EP", "both"])
ni["undated"] = ni.setup == "undated"
ni["Eb"] = np.where(ni.dated, ni.E, ni.lo)                              # the buy day: the event day if dated, the window start if undated
ni["yr"] = ni.Eb.str[:4].astype(int)
ni["key_era"] = np.where(ni.dated, ni.era, np.where(ni.Eb <= A_LAST, "A", "B"))      # the holdings re-buy key's era
ni["eraB"] = ni.Eb > A_LAST                                                          # the registration's era rule (by buy day)
ni["inv"] = ni.inverted == "True"
ni["dec"] = ni.decides == "True"
ni["noev"] = ni.undated & (ni.undated_reason == "no_event_in_window")
for c in ("lo", "hi", "exit_lo", "exit_hi", "Eb"):
    ni[c + "_i"] = ni[c].map(lambda d: CI.get(d, -1) if d else -1)
ni["has_exit"] = ni.exit_hi_i >= 0
assert (ni.lo_i >= 0).all() and (ni.hi_i >= 0).all() and (ni.Eb_i >= 0).all(), "a buy day / window end is missing from the calendar"
assert ((ni.hi_i - ni.lo_i + 1) == ni.wl).all()
m_ = ni.merge(X[["eid", "exit_lo", "exit_hi"]], on="eid", suffixes=("", "_x"))
assert ((m_.exit_lo == m_.exit_lo_x) & (m_.exit_hi == m_.exit_hi_x)).all(), "exits.tsv disagrees with entries.tsv"
assert ((ni.exit_hi != "") == ni.has_exit).all(), "an exit window date is missing from the calendar"
assert_le_cut(list(ni.Eb) + list(ni.exit_hi[ni.exit_hi != ""]), "entries")

# ---- the type gate (own) -------------------------------------------------------------------------------------------------------------
ni["tkey"] = np.where(ni.Eb <= A_LAST, ni.sym_a, ni.sym)
ni["sec_type"] = ni.tkey.map(type_of)
ni["type_ok"] = ni.sec_type.isin(["CS", "ADRC", ""])

# ---- same-day re-buys (own; the holdings key (era, bar symbol, E, undated-flag) in eid order; rows without bars are never walked) -------
sdr = set()
seen = {}
for r in ni[ni.has_bars == "True"].sort_values("eidn").itertuples():
    tk = r.sym_a if r.key_era == "A" else r.sym
    k = (r.key_era, tk, r.Eb, r.undated)
    if k not in seen:
        seen[k] = r.eid
    else:
        sdr.add(r.eid)
ni["sdr"] = ni.eid.isin(sdr)
ni["gate"] = ni.type_ok & ~ni.inv & ~ni.sdr


# ---- the panel clocks on the buy day (own) -----------------------------------------------------------------------------------------------
def clock_cols(r):
    fc = flc = fctx = pctx = ""
    if r.first_frame in SNI.index:
        f = SNI.loc[r.first_frame]
        fctx = f.ctx
        if f.date == r.Eb and f.ctx != "pre":
            fc = f.clock
    if r.prev_full_frame and r.prev_full_frame in SNI.index:
        p = SNI.loc[r.prev_full_frame]
        pctx = p.ctx
        if p.date == r.Eb and p.ctx != "closed":
            flc = p.clock
    return pd.Series({"fc": fc, "flc": flc, "f_ctx": fctx, "p_ctx": pctx})


ni = pd.concat([ni, ni.apply(clock_cols, axis=1)], axis=1)
ni["inb"] = (ni.fc != "") & (ni.flc != "") & (ni.p_ctx == "in")                  # first seen in session AND an in-session flat frame
ni["prefl"] = (ni.fc != "") & (ni.flc != "") & (ni.p_ctx == "pre")              # first seen in session, flat frame pre-market
ni["hb0935"] = (ni.fc != "") & (ni.fc < "09:35")

# ---- guard (8): misread clocks per video (own) ---------------------------------------------------------------------------------------------
MIS = {}
for vid, g in SN.groupby("vid"):
    reads = []
    for r in g.itertuples():
        et = r.et_time
        if et and len(et) >= 16:
            try:
                s = int(et[11:13]) * 3600 + int(et[14:16]) * 60
            except ValueError:
                continue
            reads.append((r.frame_id, r.date, s, int(float(r.stream_ts))))
    if not reads:
        continue
    off = float(np.median([s - st for _f, _d, s, st in reads]))
    for fid, d, s, st in reads:
        if abs(s - st - off) > 120:
            MIS[fid] = d


def sane(r):
    """§2c in the registration's order: (i) flat clock >= 09:30 (the frame is already in-session by label), (ii) positive width,
    (iii) neither frame a misread clock."""
    fl, fm = hm(r.flc), hm(r.fc)
    if fl is None or fm is None or fl < 0:
        return "flat_before_open"
    if fm - fl <= 0:
        return "zero_width"
    if r.first_frame in MIS or r.prev_full_frame in MIS:
        return "clock_misread"
    return "ok"


ni["san"] = [sane(r) if r.inb else "" for r in ni.itertuples()]


def inwin(df, w):
    return df[(df.Eb >= w[0]) & (df.Eb <= w[1])]


def G(df):
    return df[df.gate]


dec = ni[ni.dec]
dec_used = dec[dec.gate]
ex_all = ni[ni.noev & (ni.wl == 1)]
ex_nf = ex_all[~ex_all.flick]

# ================================================================================================================ the borrowed table, checked
say("\n## 0. The borrowed table (dryrun_clocks.tsv) checked against my own derivation, row by row")
D = DRY.set_index("eid")
nd = ni.set_index("eid")
for dc, mc in (("first_clock_on_E", "fc"), ("flat_clock_on_E", "flc"), ("flat_ctx", "p_ctx"), ("first_ctx", "f_ctx")):
    claim("--", f"dryrun_clocks.{dc} vs my {mc} (rows that differ, of {len(nd)} non-initial)", 0, int((D.loc[nd.index, dc].values != nd[mc].values).sum()))
for dc, mc in (("in_session_bracket", "inb"), ("pre_market_flat_bracket", "prefl"), ("held_before_0935", "hb0935"),
               ("inverted", "inv"), ("same_day_rebuy", "sdr"), ("type_ok", "type_ok")):
    claim("--", f"dryrun_clocks.{dc} vs my {mc} (rows that differ)", 0, int(((D.loc[nd.index, dc] == "True").values != nd[mc].values).sum()))
claim("--", "dryrun_clocks.sec_type vs my type resolution (rows that differ)", 0, int((D.loc[nd.index, "sec_type"].values != nd.sec_type.values).sum()))
dd = ni[ni.dated]
claim("--", "entries.tsv stored first/flat clock of dated rows vs mine (rows that differ)", 0, int(((dd.first_clock_on_E != dd.fc) | (dd.flat_clock_on_E != dd.flc)).sum()))
claim("--", "dated rows whose stored era differs from the buy-day era rule (A <= 2022-03-31)", 0, int((dd.era != np.where(dd.Eb <= A_LAST, "A", "B")).sum()))
# frame-level sanity of the timeline's own frames (taken as is by the registration): the first frame shows the name, the flat frame is a FULL frame
# that does not, and in the same video the flat frame comes first
def frame_viol(df):
    v1 = v2 = v3 = v4 = 0
    for r in df.itertuples():
        f = SNI.loc[r.first_frame] if r.first_frame in SNI.index else None
        p_ = SNI.loc[r.prev_full_frame] if (r.prev_full_frame and r.prev_full_frame in SNI.index) else None
        if f is not None and r.sym not in (set(f.symbols.split(",")) | set(f.blip_filled.split(","))) and r.sym_a not in (set(f.symbols.split(",")) | set(f.blip_filled.split(","))):
            v1 += 1
        if p_ is not None:
            ps = set(p_.symbols.split(",")) | set(p_.blip_filled.split(","))
            v2 += int(r.sym in ps or r.sym_a in ps)
            v3 += int(p_.full != "True")
            if f is not None and p_.vid == f.vid:
                v4 += int(float(p_.stream_ts) >= float(f.stream_ts))
    return v1, v2, v3, v4


# (the scorable virgin windows are defined further below; this first pass covers every non-initial row)
claim("--", "frames: rows whose FIRST frame lacks the name (symbols + blip_filled) / whose flat frame shows it / whose flat frame is not full / flat frame not earlier in the same video",
      "0 / 0 / 0 / 0", " / ".join(str(x) for x in frame_viol(ni)), "all 1,861 non-initial rows")
SETS_DRY = {k: set() for k in ("dec_used", "und_fit", "und_chk", "stop_fit_dated", "stop_chk_dated", "sel_fit", "sel_chk", "ex_all", "ex_nf",
                               "ent_fit_dated", "ent_chk_dated", "ent_fit_und", "ent_chk_und", "ent_fit_und_fl", "ent_chk_und_fl", "c633", "c349")}
for r in DRY.itertuples():
    for s in r.sets.split(";"):
        if s in SETS_DRY:
            SETS_DRY[s].add(int(r.eid))
fd, cd_ = inwin(dec_used, FIT), inwin(dec_used, CHK)
sf, sc = G(inwin(ex_nf, FIT)), G(inwin(ex_nf, CHK))
uf, uc = G(inwin(ex_all, FIT)), G(inwin(ex_all, CHK))
mine_sets = {
    "dec_used": dec_used, "und_fit": uf, "und_chk": uc, "stop_fit_dated": fd, "stop_chk_dated": cd_, "sel_fit": sf, "sel_chk": sc,
    "ex_all": ex_all, "ex_nf": ex_nf, "ent_fit_dated": fd[fd.inb], "ent_chk_dated": cd_[cd_.inb], "ent_fit_und": sf[sf.inb], "ent_chk_und": sc[sc.inb],
    "ent_fit_und_fl": uf[uf.inb], "ent_chk_und_fl": uc[uc.inb],
    "c633": ni[ni.noev & (ni.wl <= 10) & ~ni.flick], "c349": ni[ni.noev & (ni.wl <= 10) & ni.flick],
}
for k, df in mine_sets.items():
    claim("--", f"my set {k} vs the predecessor's membership (eids in one but not the other)", 0, len(set(df.eidn) ^ SETS_DRY[k]), f"mine {len(df)}, dry run {len(SETS_DRY[k])}")

# ================================================================================================================ header counts
say("\n## 1. Headline counts and streams")
claim("@1,874 entries, 13 initial", "entries / initial / non-initial", "1874 / 13 / 1861", f"{len(T)} / {int((T.initial == 'True').sum())} / {len(ni)}")
claim("@1,874 entries, 13 initial", "snapshots", 2907, len(SN))
claim("@1,874 entries, 13 initial", "streams (distinct vid)", 517, SN.vid.nunique())
yrs = SN.date.str[:4]
mine_streams = "; ".join(f"{y}: {SN.loc[yrs == y, 'vid'].nunique()} / {SN.loc[yrs == y, 'date'].nunique()}" for y in sorted(yrs.unique()))
claim("@2a. Streams per year", "videos / session dates per year (2017-2023)",
      "2017: 11 / 11; 2018: 1 / 1; 2019: 39 / 39; 2020: 218 / 216; 2021: 177 / 177; 2022: 59 / 59; 2023: 12 / 12", mine_streams)
claim("@2019 has 39 stream days", "2019 stream days / 2020 stream days", "39 / 216", f"{SN.loc[yrs == '2019', 'date'].nunique()} / {SN.loc[yrs == '2020', 'date'].nunique()}")
claim("@only 21 misread clocks", "misread-clock frames (guard 8): total / in 2019", "21 / 21", f"{len(MIS)} / {sum(1 for d in MIS.values() if d.startswith('2019'))}")

# ================================================================================================================ the §2 table, cell by cell
say("\n## 2. The population table, cell by cell: trades / non-flicker / in-session windows (non-flicker) / exits known / era B")


def cells(df):
    return dict(n=len(df), nf=int((~df.flick).sum()), inb=int(df.inb.sum()), inb_nf=int((df.inb & ~df.flick).sum()),
                ex=int(df.has_exit.sum()), eb=int(df.eraB.sum()))


sets = {}
sets["fit_dated"], sets["fit_und"] = fd, uf
sets["y2122_dated"], sets["y2122_und"] = cd_, uc
sets["v2019_dated"] = dec_used[dec_used.yr == 2019]
sets["v2019_und"] = G(ex_all[ex_all.yr == 2019])
sets["v2023_dated"] = dec_used[dec_used.yr == 2023]
sets["v2023_und"] = G(ex_all[ex_all.yr == 2023])
sets["v2022h2_dated"] = dec_used[(dec_used.yr == 2022) & (dec_used.Eb > CHK[1])]
sets["v2022h2_und"] = G(ex_all[(ex_all.yr == 2022) & (ex_all.Eb > CHK[1])])
sets["v2020pre_dated"] = dec_used[(dec_used.Eb >= "2020-01-01") & (dec_used.Eb < FIT[0])]
sets["v2020pre_und"] = G(ex_all[(ex_all.Eb >= "2020-01-01") & (ex_all.Eb < FIT[0])])
sets["l1718_dated"] = dec_used[dec_used.yr <= 2018]
sets["l1718_und"] = G(ex_all[ex_all.yr <= 2018])
virgin = pd.concat([sets[k] for k in ("v2019_dated", "v2019_und", "v2023_dated", "v2023_und", "v2022h2_dated", "v2022h2_und", "v2020pre_dated", "v2020pre_und")])
l1718 = pd.concat([sets["l1718_dated"], sets["l1718_und"]])
allgated = pd.concat([dec_used, G(ex_all)])
blocks_all = pd.concat([fd, uf, cd_, uc, virgin, l1718])
claim("--", "partition: gated dated + gated exact-day trades / union of the blocks / duplicated rows in the union", f"{len(allgated)} / {len(allgated)} / 0",
      f"{len(allgated)} / {len(blocks_all)} / {int(blocks_all.eid.duplicated().sum())}")
claim("--", "partition: trades in the gated pool but in no block", 0, len(set(allgated.eid) - set(blocks_all.eid)))

cc = {k: cells(v) for k, v in sets.items()}
cc["virgin"], cc["l1718"] = cells(virgin), cells(l1718)
cc["v2022h2"] = cells(pd.concat([sets["v2022h2_dated"], sets["v2022h2_und"]]))
cc["v2020pre"] = cells(pd.concat([sets["v2020pre_dated"], sets["v2020pre_und"]]))
tbl = [
    ("@fit, dated 2020", "fit dated 2020", "fit_dated", dict(n=149, nf=104, inb=32, inb_nf=24, ex=149, eb=0)),
    ("@fit, undated exact-day 2020", "fit undated exact-day 2020 (flickers in)", "fit_und", dict(n=304, nf=188, inb=94, inb_nf=59, ex=304, eb=0)),
    ("@2021-22 dated** (2021-01-04", "2021-22 dated", "y2122_dated", dict(n=111, nf=68, inb=20, inb_nf=13, ex=111, eb=7)),
    ("@2021-22 undated exact-day**", "2021-22 undated exact-day", "y2122_und", dict(n=226, nf=145, inb=63, inb_nf=44, ex=226, eb=8)),
    ("@untouched: 2019 dated", "2019 dated", "v2019_dated", dict(n=16, nf=15, inb=1, inb_nf=1, ex=16, eb=0)),
    ("@untouched: 2019 undated exact-day", "2019 undated exact-day", "v2019_und", dict(n=44, nf=26, inb=18, inb_nf=10, ex=44, eb=0)),
    ("@untouched: 2023 dated", "2023 dated", "v2023_dated", dict(n=7, nf=5, inb=0, inb_nf=0, ex=3, eb=7)),
    ("@untouched: 2023 undated exact-day", "2023 undated exact-day", "v2023_und", dict(n=8, nf=5, inb=3, inb_nf=2, ex=8, eb=8)),
    ("@untouched: 2022 after 06-14", "2022 after 06-14 (dated + undated)", "v2022h2", dict(n=3, nf=3, inb=0, inb_nf=0, ex=3, eb=3)),
    ("@untouched: 2020 before 01-27", "2020 before 01-27 (dated + undated)", "v2020pre", dict(n=11, nf=11, inb=7, inb_nf=7, ex=11, eb=0)),
    ("@the virgin block, all", "the virgin block, all", "virgin", dict(n=89, nf=65, inb=29, inb_nf=20, ex=85, eb=18)),
    ("@listed, never walked: 2017-18", "listed, never walked 2017-18", "l1718", dict(n=4, nf=4, inb=0, inb_nf=0, ex=4, eb=0)),
]
for anc, label, key, doc in tbl:
    for f, nm in (("n", "trades"), ("nf", "non-flicker"), ("inb", "in-session windows"), ("inb_nf", "in-session non-flicker"), ("ex", "exits known"), ("eb", "era B")):
        claim(anc, f"{label}: {nm}", doc[f], cc[key][f])
claim("@untouched: 2022 after 06-14", "2022 after 06-14: dated + undated", "2 + 1", f"{len(sets['v2022h2_dated'])} + {len(sets['v2022h2_und'])}")
claim("@untouched: 2020 before 01-27", "2020 before 01-27: dated + undated", "2 + 9", f"{len(sets['v2020pre_dated'])} + {len(sets['v2020pre_und'])}")
claim("@4 still held at the last stream", "2023 dated: still held at the last stream (no exit window)", 4, int((~sets["v2023_dated"].has_exit).sum()))
claim("@89 of his trades", "virgin block: held past one stream (= non-flicker)", 65, int((~virgin.flick).sum()))
claim("@89 of his trades", "virgin block: dated by our events", 27, int(virgin.dated.sum()))
claim("@Eighteen of the 89 untouched trades", "era B in the virgin block", 18, int(virgin.eraB.sum()))
claim("@7 of the 2021-22 dated, 8 of the undated", "buys on or after 2022-04-01 in 2021-22: dated / undated", "7 / 8", f"{int(cd_.eraB.sum())} / {int(uc.eraB.sum())}")
claim("@all of 2023", "every 2023 trade is era B (buy day >= 2022-04-01)", "all", "all" if bool(virgin[virgin.yr == 2023].eraB.all()) else "not all")
med1718 = float(np.median(l1718[l1718.has_exit].exit_hi_i - l1718[l1718.has_exit].Eb_i + 1))
claim("@listed, never walked: 2017-18", "2017-18 trades: held to the sell window's last session, median sessions (doc '~250')", "~250", med1718, kind="OK" if 240 <= med1718 <= 260 else "MISMATCH")
claim("@the last two", "Q3: 2022-after-06-14 + January 2020 add this many trades to the virgin block", 14, cc["v2022h2"]["n"] + cc["v2020pre"]["n"])

# ================================================================================================================ §2b - clocks
say("\n## 3. The brackets' clocks: when a level exists at the first sighting")


def ge(df, col, m):
    return int((df[col].map(hm) >= m).sum())


def lt(df, col, m):
    return int((df[col].map(hm) < m).sum())


groups = {
    "fit dated 2020": fd[fd.inb], "fit undated nf 2020": sf[sf.inb], "fit undated flickers 2020": uf[uf.inb & uf.flick],
    "2021-22 dated": cd_[cd_.inb], "2021-22 undated nf": sc[sc.inb], "2021-22 undated flickers": uc[uc.inb & uc.flick],
}
for k, g in groups.items():
    say(f"  {k}: n {len(g)} | first >= 10:00 {ge(g, 'fc', 30)} | flat >= 10:00 {ge(g, 'flc', 30)} | first >= 10:30 {ge(g, 'fc', 60)} | first < 10:00 {lt(g, 'fc', 30)}")
g = groups["2021-22 undated nf"]
claim("@43 of the 44 undated", "2021-22 undated nf in-session windows closing at/after 10:00", "43 of 44", f"{ge(g, 'fc', 30)} of {len(g)}")
claim("@14 of the 44 open", "2021-22 undated nf in-session windows opening at/after 10:00 (flat frame)", "14 of 44", f"{ge(g, 'flc', 30)} of {len(g)}")
g = groups["2021-22 dated"]
claim("@43 of the 44 undated", "2021-22 dated in-session windows closing at/after 10:00", "17 of 20", f"{ge(g, 'fc', 30)} of {len(g)}")
g = groups["fit undated nf 2020"]
claim("@48 of 59 undated", "fit undated nf in-session windows closing at/after 10:00", "48 of 59", f"{ge(g, 'fc', 30)} of {len(g)}")
g = groups["fit dated 2020"]
claim("@19 of 32 dated", "fit dated in-session windows closing at/after 10:00", "19 of 32", f"{ge(g, 'fc', 30)} of {len(g)}")
hb = pd.concat([inwin(dec_used, DENSE), G(inwin(ex_nf, DENSE))])
hb = hb[hb.hb0935].sort_values(["Eb", "sym"])
claim("@Nine trades were held before 09:35", "held before 09:35 (gated dated + exact-day non-flicker, 2020-01-27..2022-06-14)", 9, len(hb))
claim("@seven first seen at 09:31-09:34", "  first seen 09:31-09:34 (7: TSLA 2020-04-14, UAL 05-27, DXCM 07-29, PINS 07-31, SHOP and TTD 08-26, ROKU 09-15)",
      "TSLA 2020-04-14, UAL 2020-05-27, DXCM 2020-07-29, PINS 2020-07-31, SHOP 2020-08-26, TTD 2020-08-26, ROKU 2020-09-15",
      ", ".join(f"{r.sym} {r.Eb}" for r in hb[hb.fc >= '09:31'].itertuples()))
claim("@not for LAC and TSLA", "  first seen 09:30 (no 1-minute high yet)", "LAC 2022-04-21, TSLA 2022-04-21", ", ".join(f"{r.sym} {r.Eb}" for r in hb[hb.fc < '09:31'].itertuples()))

# ---- §2c ---------------------------------------------------------------------------------------------------------------------------------
say("\n## 4. Clock sanity (§2c)")
vb = virgin[virgin.inb]
ok_v = vb[vb.san == "ok"]
claim("@17 scorable (9 non-flicker", "virgin block in-session windows -> scorable after §2c", "29 -> 17", f"{len(vb)} -> {len(ok_v)}")
claim("@17 scorable (9 non-flicker", "  scorable non-flicker / flickers", "9 / 8", f"{int((~ok_v.flick).sum())} / {int(ok_v.flick.sum())}")
doc_nf9 = ["ASPS 2019-10-03", "JCP 2019-10-07", "RLGY 2019-10-10", "CCS 2019-10-17", "BABA 2019-11-01", "LX 2019-11-15", "APT 2020-01-23", "CVNA 2023-05-18", "AI 2023-05-19"]
claim("@17 scorable (9 non-flicker", "  the nine scorable non-flicker windows (named)", sorted(doc_nf9), sorted(f"{r.sym} {r.Eb}" for r in ok_v[~ok_v.flick].itertuples()))
say("  dropped by name (virgin): " + ", ".join(sorted(f"{r.sym} {r.Eb} {r.san}" for r in vb[vb.san != "ok"].itertuples())))
claim("@17 scorable (9 non-flicker", "  windows dropped by (i) flat_before_open / (ii) zero_width / (iii) clock_misread", "12 dropped in all (29 - 17)",
      f"{int((vb.san == 'flat_before_open').sum())} / {int((vb.san == 'zero_width').sum())} / {int((vb.san == 'clock_misread').sum())} = {int((vb.san != 'ok').sum())}", kind="NOTE")
f20 = fd[fd.inb]
fu = uf[uf.inb]
claim("@31 + 59 (+34 flickers)", "fit: scorable dated / undated non-flicker / undated flickers", "31 / 59 / 34",
      f"{int((f20.san == 'ok').sum())} / {int(((fu.san == 'ok') & ~fu.flick).sum())} / {int(((fu.san == 'ok') & fu.flick).sum())}")
claim("@31 + 59 (+34 flickers)", "fit: windows out (one dated and one flicker, both zero width)", "dated {'zero_width': 1}; undated {'zero_width': 1}",
      f"dated {dict(collections.Counter(x for x in f20.san if x != 'ok'))}; undated {dict(collections.Counter(x for x in fu.san if x != 'ok'))}")
y2 = cd_[cd_.inb]
yu = uc[uc.inb]
claim("@one undated window out", "2021-22: scorable dated / undated non-flicker / undated flickers", "20 / 43 / 19",
      f"{int((y2.san == 'ok').sum())} / {int(((yu.san == 'ok') & ~yu.flick).sum())} / {int(((yu.san == 'ok') & yu.flick).sum())}")
claim("@one undated window out", "2021-22: the one undated window out", "{'flat_before_open': 1}", dict(collections.Counter(x for x in yu.san if x != "ok")))


def find(sym, d):
    r = ni[(ni.sym == sym) & (ni.Eb == d)]
    assert len(r) == 1, (sym, d, len(r))
    return r.iloc[0]


for sym in ("ARWR", "AVLR", "ITCI", "FCEL", "LX", "NTCT"):
    r = find(sym, "2020-01-02")
    claim("@ARWR / AVLR / ITCI", f"{sym} 2020-01-02: flat frame clock / label", "09:08 / in", f"{r.flc} / {r.p_ctx}")
claim("@FBR and JCP 2019-10-23 read", "FBR 2019-10-23 / JCP 2019-10-23 flat clock", "09:24 / 09:25", f"{find('FBR', '2019-10-23').flc} / {find('JCP', '2019-10-23').flc}")
a = find("APPS", "2019-10-01")
claim("@(APPS 2019-10-01 10:48", "APPS 2019-10-01: flat clock -> first clock", "10:48 -> 08:58", f"{a.flc} -> {a.fc}")
claim("@(APPS 2019-10-01 10:48", "ASPS 2019-10-17 width (minutes)", 0, hm(find("ASPS", "2019-10-17").fc) - hm(find("ASPS", "2019-10-17").flc))
claim("@(APPS 2019-10-01 10:48", "JCP 2019-10-23 width (minutes) - but it is already out under (i)", 0, hm(find("JCP", "2019-10-23").fc) - hm(find("JCP", "2019-10-23").flc))
claim("@(APPS 2019-10-01 10:48", "JCP 2019-10-23 is dropped under which rule, applied in the doc's order (i), (ii), (iii)", "flat_before_open", find("JCP", "2019-10-23").san,
      "the doc names JCP under both (i) (09:25) and (ii) (zero width); in order it is counted once, under (i) - harmless")
claim("@21 frames, all 2019", "(iii) APPS 2019-10-01 has a misread frame on one end ('APPS 2019-10-01 is one')", True, bool(a.first_frame in MIS or a.prev_full_frame in MIS),
      f"first_frame misread: {a.first_frame in MIS}; prev_full_frame misread: {a.prev_full_frame in MIS}")
allin = ni[ni.inb]
nmis_any = int(sum(1 for r in allin.itertuples() if r.first_frame in MIS or r.prev_full_frame in MIS))
claim("@21 frames, all 2019", "(iii) in-session windows (any block, any year) with a misread frame on either end, whatever the rule order", "(only APPS 2019-10-01 is named)", nmis_any,
      "; ".join(f"{r.sym} {r.Eb} -> {r.san}" for r in allin.itertuples() if r.first_frame in MIS or r.prev_full_frame in MIS), kind="NOTE")
claim("@21 frames, all 2019", "(iii) windows dropped BY (iii) after (i) and (ii) (anywhere)", 0, int((allin.san == "clock_misread").sum()))
claim("@21 frames, all 2019", "scorable virgin windows that carry a misread frame", 0, len(vb[(vb.san == "ok") & (vb.first_frame.isin(MIS) | vb.prev_full_frame.isin(MIS))]))
nf19 = ni[(ni.Eb.str[:4] == "2019") & ni.noev & (ni.wl == 1) & ~ni.flick & ni.inb & ni.gate]
w19 = nf19.apply(lambda r: hm(r.fc) - hm(r.flc), axis=1)
nf1923 = ni[ni.yr.isin([2019, 2023]) & ni.noev & (ni.wl == 1) & ~ni.flick & ni.inb & ni.gate]
w1923 = nf1923.apply(lambda r: hm(r.fc) - hm(r.flc), axis=1)
claim("@3 of its 12 non-flicker", "2019's non-flicker in-session buy windows with a flat frame after the first frame or zero width ('3 of its 12')", "3 of 12",
      f"{int((w19 <= 0).sum())} of {len(nf19)} (2019 undated alone); {int((w1923 <= 0).sum())} of {len(nf1923)} (2019 + 2023 undated)",
      "12 is the 2019 + 2023 undated count; 2019 alone has 10 (11 with the dated MIK 2019-10-10)")
claim("@17 scorable (9 non-flicker", "frames of the 17 scorable virgin windows: first frame lacks the name / flat frame shows it / flat frame not full / not earlier", "0 / 0 / 0 / 0",
      " / ".join(str(x) for x in frame_viol(ok_v)))
jan = pd.concat([sets["v2020pre_dated"], sets["v2020pre_und"]])
jan = jan[jan.inb]
claim("@January 2020's six", "January 2020 (before the 27th): in-session windows carrying a 09:08 flat frame / all in-session windows", "6 (all at 09:08) / 7 (table row)",
      f"{int((jan.flc == '09:08').sum())} (on {sorted(set(jan[jan.flc == '09:08'].Eb))}) / {len(jan)} (the seventh: {', '.join(f'{r.sym} {r.Eb} flat {r.flc}' for r in jan[jan.flc != '09:08'].itertuples())})",
      "the sentence says 'January 2020's six in-session windows all carry a flat frame at 09:08'; the six are those of 2020-01-02, the block has seven in-session windows", kind="NOTE")

# ================================================================================================================ §2a/§2d
say("\n## 5. Hold lengths and exit windows")


def med_held(df):
    d = df[df.has_exit]
    return float(np.median(d.exit_hi_i - d.Eb_i + 1))


claim("@a median 13 sessions", "2019 undated (non-flicker, gated): held to the sell window's last session, median sessions", 13, med_held(G(ex_nf[ex_nf.yr == 2019])))
claim("@a median 13 sessions", "2020 undated (non-flicker, gated): median sessions", 5, med_held(G(ex_nf[ex_nf.yr == 2020])))
dated21 = dec_used[dec_used.Eb.str[:4] == "2021"]
claim("@sell window one session wide on 80 of the 101", "dated 2021: sell window one session wide", "80 of 101", f"{int(((dated21.exit_hi_i == dated21.exit_lo_i) & dated21.has_exit).sum())} of {len(dated21)}")
claim("@sell window one session wide on 80 of the 101", "dated 2021-22: with exits", 111, int(cd_.has_exit.sum()))
wl19 = sorted(r.exit_hi_i - r.exit_lo_i + 1 for r in sets["v2019_dated"].itertuples() if r.has_exit)
claim("@2019's", "virgin dated 2019: sell windows span (sessions)", "1-14", f"{wl19[0]}-{wl19[-1]}")
wl23 = {r.sym: r.exit_hi_i - r.exit_lo_i + 1 for r in sets["v2023_dated"].itertuples() if r.has_exit}
claim("@GSIT and GTLB 2023 span 121", "2023 dated windows of 121 sessions", "GSIT 121, GTLB 121", ", ".join(f"{k} {v}" for k, v in sorted(wl23.items()) if v >= 100))
vd = pd.concat([sets["v2019_dated"], sets["v2023_dated"], sets["v2022h2_dated"], sets["v2020pre_dated"]])
claim("@23 dated trades", "virgin dated trades with exits", 23, int(vd.has_exit.sum()))
claim("@block (23 dated: 2019's 16", "  = 2019's 16 + 2023's 3 with exits + 2022-H2's 2 + January 2020's 2", "16 + 3 + 2 + 2",
      f"{int(sets['v2019_dated'].has_exit.sum())} + {int(sets['v2023_dated'].has_exit.sum())} + {int(sets['v2022h2_dated'].has_exit.sum())} + {int(sets['v2020pre_dated'].has_exit.sum())}")
claim("@23 dated trades", "virgin dated windows of 121 sessions", 2, int(sum(1 for v in wl23.values() if v == 121)))
vw = [r.exit_hi_i - r.exit_lo_i + 1 for r in vd[vd.has_exit].itertuples()]
claim("@hit rate on ~19", "EXIT virgin: dated trades with a sell window <= 20 sessions (the hit-rate base; doc '~19')", "~19", sum(1 for x in vw if x <= 20),
      f"windows > 20 sessions: {sorted(x for x in vw if x > 20)}", kind="OK" if abs(sum(1 for x in vw if x <= 20) - 19) <= 1 else "MISMATCH")
dn = dec[(dec.Eb >= DENSE[0]) & (dec.Eb <= DENSE[1])]
claim("@262 dated", "dated deciding buys in the dense window less same-day re-buys ('all 262 dated')", 262, int((~dn.sdr).sum()), f"{len(dn)} dated deciding in the window")
claim("@63 windows", "ENTER 2021-22 beside: 20 dated + 43 undated non-flicker = 63 windows (Q1)", 63, int((y2.san == "ok").sum()) + int(((yu.san == "ok") & ~yu.flick).sum()))
claim("@(43 vs 62)", "Q8: 2021-22 undated scorable windows: non-flicker vs with flickers", "43 vs 62", f"{int(((yu.san == 'ok') & ~yu.flick).sum())} vs {int((yu.san == 'ok').sum())}")
claim("@(9 vs 17)", "Q8: virgin scorable windows: non-flicker vs with flickers", "9 vs 17", f"{int((~ok_v.flick).sum())} vs {len(ok_v)}")

# ================================================================================================================ pre-market-flat
say("\n## 6. Pre-market-flat windows beside, and the expected scorable n")
pf = lambda df: int(df.prefl.sum())
und_chk_nf, und_fit_nf = uc[~uc.flick], uf[~uf.flick]
claim("@pre-market-flat windows (41 dated", "pre-market-flat windows, dated: 2021-22 / 2020", "41 / 41", f"{pf(cd_)} / {pf(fd)}")
chk_txt = open(os.path.join(PREV_DIR, "01_rev_check.txt")).read()
fit_enter = open(os.path.join(PREV_DIR, "01_rev_enter_fit.txt")).read()
m52 = re.search(r"pre-market-flat brackets undated \((\d+)\)", chk_txt)
m57 = re.search(r"pre-market-flat brackets, undated 2020 \((\d+)\)", fit_enter)
claim("@pre-market-flat windows (41 dated", "pre-market-flat windows, undated non-flicker (gated): 2021-22 / 2020 (population counts)", "52 / 57", f"{pf(und_chk_nf)} / {pf(und_fit_nf)}",
      f"the doc's 52 / 57 are the predecessor printouts' SCORED counts ({m52.group(1) if m52 else '?'} / {m57.group(1) if m57 else '?'}), not the populations; "
      f"with flickers: {pf(uc)} / {pf(uf)}")
claim("@Expected scorable n per level", "2021-22 scorable windows (dated + undated non-flicker) = L7's n", 63, int((y2.san == "ok").sum()) + int(((yu.san == "ok") & ~yu.flick).sum()))
y_all = pd.concat([y2[y2.san == "ok"], yu[(yu.san == "ok") & ~yu.flick]])
claim("@the 3 dated + 1 undated", "  windows closing before 10:00 (no_level_yet for L8 / L9)", "3 dated + 1 undated", f"{lt(y_all[y_all.dated], 'fc', 30)} dated + {lt(y_all[~y_all.dated], 'fc', 30)} undated")
claim("@the 3 dated + 1 undated", "  L8 / L9 scorable = 63 minus the 4 windows closing before 10:00 (doc '59-60')", "59-60", 63 - lt(y_all, "fc", 30),
      "59 before the record floor; 60 only if the one window the clock-sanity rule drops (64 - 1) is counted; the floor (3 of 64 last time) would take it to ~56", kind="NOTE")
mfl = re.search(r"records (\d+) \(dropped \{'bars_before_E_lt_20': (\d+)\}", chk_txt)
claim("@the 3 dated + 1 undated", "  the record floor of 20 bars took 3 of 64 last time (predecessor printout: records / dropped)", "61 / 3 (of 64)", f"{mfl.group(1)} / {mfl.group(2)} (of {len(y2) + int((~yu.flick).sum())})" if mfl else "not found",
      "transcription of 01_rev_check.txt; 64 = 20 dated + 44 undated in-session windows before the clock-sanity rule")

# ================================================================================================================ forward events
say("\n## 7. Forward events after the window")
cols = ["ticker", "D", "E", "K", "split"]
ca = pd.read_csv(f"{DATA}/cb702_pre_v2/out/candidates_tl_com.tsv", sep="\t", dtype=str, keep_default_na=False, usecols=cols)
cb = pd.read_csv(f"{DATA}/cb702/out/candidates.tsv", sep="\t", dtype=str, keep_default_na=False, usecols=cols)
ca = ca[ca.E <= A_LAST]
cb = cb[(cb.E <= CUT) & (cb.D <= CUT) & (cb.E >= "2022-04-01") & (cb.split == "discovery")]
EVB = collections.defaultdict(set)
for era, df in (("A", ca), ("B", cb)):
    for r in df[df.K == "tl"].itertuples():
        EVB[(era, r.ticker)].add(r.E)
for era, p, lo_, hi_ in (("A", f"{QS}ep_join_1023/ep_events_A.tsv.gz", "0000-00-00", A_LAST), ("B", f"{QS}ep_join_1023/ep_events_B.tsv.gz", "2022-04-01", CUT)):
    e = pd.read_csv(p, sep="\t", dtype=str, keep_default_na=False, usecols=["ticker", "E", "primary"])
    e = e[(e.primary == "True") & (e.E >= lo_) & (e.E <= hi_)]
    for r in e.itertuples():
        EVB[(era, r.ticker)].add(r.E)
c633 = mine_sets["c633"]
a15 = []
for r in c633.itertuples():
    ev = EVB.get(("A", r.sym_a), set()) | EVB.get(("B", r.sym), set())
    a15.append(any(1 <= CI[e] - r.hi_i <= 5 for e in ev if e in CI))
c633 = c633.assign(a15=a15)
claim("@126 of the 633", "no-event non-flicker buys (window <= 10 sessions) with an event 1-5 sessions after the window", 126, int(c633.a15.sum()))
claim("@126 of the 633", "  of them in 2021-22 (window start in 2021-01-04..2022-06-14)", 48, int((c633.a15 & (c633.lo >= CHK[0]) & (c633.lo <= CHK[1])).sum()),
      f"other readings: window END in the check window {int((c633.a15 & (c633.hi >= CHK[0]) & (c633.hi <= CHK[1])).sum())}; "
      f"gated and start in the window {int((c633.a15 & c633.gate & (c633.lo >= CHK[0]) & (c633.lo <= CHK[1])).sum())}; calendar years 2021-2022 {int((c633.a15 & c633.lo.str[:4].isin(['2021', '2022'])).sum())}")

# ================================================================================================================ minutes: coverage + the fetch list
say("\n## 8. Minute coverage and the fetch list")


def load_done(tree, cut=CUT):
    out, dropped = {}, 0
    with open(tree + "/_done.psv") as fh:
        for ln in fh:
            f = ln.rstrip("\n").split("|")
            if len(f) < 4:
                continue
            if f[0] > cut:
                dropped += 1
                continue
            out[(f[0], f[1])] = f[3]
    return out, dropped


def date_files(tree):
    return {fn[:-len(".psv.gz")] for fn in os.listdir(tree) if fn.endswith(".psv.gz")}


DONE, DFILES, drops = {}, {}, {}
for k in TREE_ORDER:
    DONE[k], drops[k] = load_done(TREES[k])
    DFILES[k] = date_files(TREES[k])
    assert_le_cut([d for d, _ in DONE[k]], f"done log {k}")
ODONE, OFILES = {}, {}
for k, p in OTHER_TREES.items():
    ODONE[k], _ = load_done(p)
    OFILES[k] = date_files(p)
say("- fetch-log pairs read: " + ", ".join(f"{k} {len(v):,}" for k, v in DONE.items()) + " | rows dropped after the cut at read: " + str(drops))
say("- date files per tree: " + ", ".join(f"{k} {len(v):,}" for k, v in DFILES.items()))
say(f"- status vocabulary over the five trees: {dict(collections.Counter(s for k in TREE_ORDER for s in DONE[k].values()))}")


def state(d, tk):
    for k in TREE_ORDER:
        if DONE[k].get((d, tk)) == "ok" and d in DFILES[k]:
            return "ok"
    for k in TREE_ORDER:
        if DONE[k].get((d, tk)) == "empty":
            return "empty"
    return "missing"


def hold_pairs(df, block, need, warm, tail, noexit, stats):
    for r in df.itertuples():
        if r.Eb_i < 0:
            stats["no_index"] += 1
            continue
        i0 = max(0, r.Eb_i - warm)
        j1 = min(r.exit_hi_i + tail, len(CAL) - 1) if r.has_exit else min(r.Eb_i + noexit, len(CAL) - 1)
        for i in range(i0, j1 + 1):
            d = CAL[i]
            tk = r.sym_a if d <= A_LAST else r.sym              # the bar symbol follows the SESSION's date
            st = state(d, tk)
            stats[st] += 1
            if st == "missing":
                need[(tk, d)].add(block)


fit_tr = pd.concat([fd, uf])
virg_tr = virgin
y2122_tr = pd.concat([cd_, uc])
BLK = (("fit2020", fit_tr), ("virgin", virg_tr), ("y2122", y2122_tr))
claim("--", "walked trades: fit / virgin / 2021-22 (the printout's 453 / 89 / 337)", "453 / 89 / 337", f"{len(fit_tr)} / {len(virg_tr)} / {len(y2122_tr)}", kind="NOTE")


def build(warm, tail, noexit, blocks=BLK):
    need = collections.defaultdict(set)
    stats = collections.Counter()
    for blk, df in blocks:
        hold_pairs(df, blk, need, warm, tail, noexit, stats)
    rows = sorted(need.items(), key=lambda kv: (kv[0][1], kv[0][0]))
    return rows, [f"{tk}|{d}|{'+'.join(sorted(b))}" for (tk, d), b in rows], stats


rowsB, linesB, statsB = build(WARM, TAIL, NOEXIT)
rowsA, linesA, statsA = build(WARM, 0, NOEXIT)
textB = ("\n".join(linesB) + "\n").encode()
textA = ("\n".join(linesA) + "\n").encode()
os.makedirs(SCRATCH, exist_ok=True)
open(os.path.join(SCRATCH, "recount_fetch_list_intra_1025.psv"), "wb").write(textB)
open(os.path.join(SCRATCH, "recount_fetch_list_hold_only_intra_1025.psv"), "wb").write(textA)
assert_le_cut([d for (_t, d), _b in rowsB], "my fetch list")
file_full = open(LIST_FULL).read().splitlines()
file_hold = open(LIST_HOLD).read().splitlines()
assert_le_cut([ln.split("|")[1] for ln in file_full], "fetch list on disk")
A_PAIRS = "@19,470 pairs"
claim(A_PAIRS, "fetch list: pairs / distinct dates", "19470 / 1005", f"{len(linesB)} / {len({d for (_t, d), _b in rowsB})}")
claim(A_PAIRS, "fetch list file rows vs my derivation (rows in one not the other, both ways / same order)", "0 / 0 / identical",
      f"{len(set(file_full) - set(linesB))} / {len(set(linesB) - set(file_full))} / {'identical' if file_full == linesB else 'order or content differs'}")
claim("@sha256 `e66f33d6", "fetch list file sha256", "e66f33d690f7d0d2ac9c797bedc16ff5bc79b9fffda268859016ed0d1d3f6254", sha(LIST_FULL))
claim("@sha256 `e66f33d6", "sha256 of the bytes of MY regenerated list", "e66f33d690f7d0d2ac9c797bedc16ff5bc79b9fffda268859016ed0d1d3f6254", hashlib.sha256(textB).hexdigest())
claim("@sha256 `e66f33d6", "three columns, no header; no third field all digits (so the fetcher's parse_list keeps every row)", "every row kept",
      "every row kept" if all(len(ln.split("|")) == 3 and not ln.split("|")[2].strip().lstrip("-").isdigit() for ln in file_full) else "a row would be read as a tier")
byb = collections.Counter("+".join(sorted(b)) for _k, b in rowsB)
claim("@fit 2020 8,795 pairs", "by block: fit 2020 only / virgin only / 2021-22 only", "8795 / 3179 / 7309", f"{byb.get('fit2020', 0)} / {byb.get('virgin', 0)} / {byb.get('y2122', 0)}")
claim("@fit 2020 8,795 pairs", "shared: fit+virgin / fit+2021-22", "52 / 135", f"{byb.get('fit2020+virgin', 0)} / {byb.get('fit2020+y2122', 0)}")
claim("@fit 2020 8,795 pairs", "shared pairs together ('187' in the headline) and no other block combination", "187 / 0",
      f"{byb.get('fit2020+virgin', 0) + byb.get('fit2020+y2122', 0)} / {sum(v for k, v in byb.items() if k not in ('fit2020', 'virgin', 'y2122', 'fit2020+virgin', 'fit2020+y2122'))}")
byy = collections.Counter(d[:4] for (_t, d), _b in rowsB)
claim("@by year 2019: 1,405", "by year 2019 / 2020 / 2021 / 2022 / 2023 / 2024", "1405 / 9367 / 6304 / 1454 / 924 / 16", " / ".join(str(byy.get(y, 0)) for y in ("2019", "2020", "2021", "2022", "2023", "2024")))
claim("@by year 2019: 1,405", "pairs in any other year (2017-18, 2025-26)", 0, sum(v for k, v in byy.items() if k not in ("2019", "2020", "2021", "2022", "2023", "2024")))
claim("@The fit + virgin blocks alone", "fit + virgin blocks alone (pairs not needed by 2021-22)", 12026, sum(1 for _k, b in rowsB if "y2122" not in b))
p24 = [(tk, d) for (tk, d), _b in rowsB if d.startswith("2024")]
held4 = ni[(~ni.has_exit) & ni.gate & ni.dec]
claim("@the four 2023-12 still-held", "the 2024 pairs: count / symbols = the still-held deciding trades (PATH, GME, GTLB, VKTX)", "16 / ['GME', 'GTLB', 'PATH', 'VKTX']",
      f"{len(p24)} / {sorted({tk for tk, _d in p24})}", kind="OK" if (len(p24) == 16 and sorted({tk for tk, _d in p24}) == sorted(held4.sym) == ['GME', 'GTLB', 'PATH', 'VKTX']) else "MISMATCH")
claim("@The hold-only list", "hold-only list: pairs / dates", "10503 / 966", f"{len(linesA)} / {len({d for (_t, d), _b in rowsA})}")
claim("@The hold-only list", "hold-only file rows vs my derivation (rows in one not the other, both ways / same order)", "0 / 0 / identical",
      f"{len(set(file_hold) - set(linesA))} / {len(set(linesA) - set(file_hold))} / {'identical' if file_hold == linesA else 'order or content differs'}")
claim("@The hold-only list", "hold-only file sha256", "28624df669d9a7e1edeba35da2d6f5d3b0d91b6347648b345a3f41cbd2d0c525", sha(LIST_HOLD))
claim("@The hold-only list", "hold-only pairs are a subset of the with-tail pairs (pairs not in the full list)", 0,
      len({(tk, d) for (tk, d), _b in rowsA} - {(tk, d) for (tk, d), _b in rowsB}))
claim("@The hold-only list", "the tail = the difference (pairs)", 8967, len(rowsB) - len(rowsA))
r_pure = build(0, 0, 0)
claim("@The hold-only list", "'hold-only' read literally (no warm-up, no tail, still-held: buy day only) - pairs / dates", "(not the list on disk)",
      f"{len(r_pure[0])} / {len({d for (_t, d), _b in r_pure[0]})}",
      "the file named hold-only still carries the 10-session warm-up and +20 sessions for the 4 still-held trades; the doc's text does say 'plus ten sessions before each buy'", kind="NOTE")
claim("--", "walked ticker-days (with tail): listed (missing) / already covered / logged empty at the source", "(see variant B in 00_pop_fetch.txt)",
      f"{statsB['missing']:,} (distinct pairs {len(rowsB):,}) / {statsB['ok']:,} / {statsB['empty']:,}", kind="NOTE")
claim("--", "walked trades without a calendar index (skipped)", 0, statsB["no_index"])
per_date = collections.Counter(d for (_t, d), _b in rowsB)
req = sum(math.ceil(n / 50) for n in per_date.values())
claim("@19 symbols per date on average", "symbols per date: average (rounded) / maximum", "19 / 69", f"{round(len(rowsB) / len(per_date))} / {max(per_date.values())}", f"average {len(rowsB) / len(per_date):.2f}")
claim("@19 symbols per date on average", "dates needing two requests (more than 50 symbols)", "(at most 69 -> two requests)", f"{sum(1 for n in per_date.values() if n > 50)}; max symbols {max(per_date.values())}", kind="NOTE")
claim("@19 symbols per date on average", "requests = sum of ceil(symbols / 50) ('about 1,100')", "about 1,100", req, f"{(req - 1100) / 1100:+.1%} against 1,100", kind="OK" if abs(req - 1100) / 1100 <= 0.10 else "MISMATCH")


fm_src = open(os.path.join(REPO, "scripts/probes/_cb_backtest/fetch_minutes.py")).read()
m_pr = re.search(r'"--per-request"[^\n]*?default=(\d+)', fm_src)
m_sl = re.search(r'"--sleep"[^\n]*?default=([0-9.]+)', fm_src)
claim("@50 symbols per request", "the fetcher's defaults: symbols per request / pause between requests (seconds)", "50 / 0.25", f"{m_pr.group(1) if m_pr else 'not found'} / {m_sl.group(1) if m_sl else 'not found'}")
intra_files = sorted(os.listdir(INTRA_MIN))
claim("@is written, not", "the intra folder holds the three files the derivation wrote (00_pop_fetch.txt + the two lists)", "all three present",
      "all three present" if all(f_ in intra_files for f_ in ("00_pop_fetch.txt", "fetch_list_hold_only_intra_1025.psv", "fetch_list_intra_1025.psv")) else "missing",
      "the doc says 'written, not fetched' - true when registered; a fetch has since run into this folder (section 15)")


def log_span(path):
    ln = open(path).read().splitlines()
    t0 = datetime.datetime.strptime(ln[0][:19], "%Y-%m-%d %H:%M:%S")
    t1 = datetime.datetime.strptime([x for x in ln if " done:" in x][-1][:19], "%Y-%m-%d %H:%M:%S")
    return (t1 - t0).total_seconds()


s_rev = log_span(TREES["REV"] + "/fetch.log")
claim("@508 dates in 2 min 34 s", "10-24 fetch: seconds from first line to 'done' (2 min 34 s = 154)", 154, s_rev)
claim("@508 dates in 2 min 34 s", "REV tree: ok pairs / empty pairs / dates", "1302 / 20 / 508",
      f"{sum(1 for v in DONE['REV'].values() if v == 'ok')} / {sum(1 for v in DONE['REV'].values() if v == 'empty')} / {len({d for d, _ in DONE['REV']})}")
s_do = log_span(OTHER_TREES["delta_out"] + "/fetch.log")
claim("@8-12 minutes", "pace: the nearest earlier run of the same shape (delta_out: 22,989 pairs, 1,137 dates, ~20 symbols a date) took (minutes)", "8-12 (this fetch)", f"{s_do / 60:.1f}",
      "the 10-24 run's pace (0.30 s/request) alone would give ~5 minutes for these requests; the delta_out run bears out 8-12 minutes",
      kind="OK" if 8 <= s_do / 60 <= 12 else "MISMATCH")
ses1718 = 0
for r in l1718.itertuples():
    i0 = max(0, r.Eb_i - WARM)
    j1 = min(r.exit_hi_i, len(CAL) - 1) if r.has_exit else min(r.Eb_i + NOEXIT, len(CAL) - 1)
    ses1718 += j1 - i0 + 1
claim("@2017-18 (4 trades", "2017-18: ticker-days for warm-up + hold of the 4 trades ('~800 pairs')", "~800", ses1718, kind="OK" if abs(ses1718 - 800) <= 40 else "MISMATCH")
inother = [(tk, d) for (tk, d), _b in rowsB if any(ODONE[k].get((d, tk)) == "ok" and d in OFILES[k] for k in ODONE)]
claim("@in NO local tree", "listed pairs an UNPINNED local tree (com_delta_1018, pre_com_1018, delta_out) already holds", 0, len(inother),
      "the derivation reads five trees; these three are not consulted ('NO local tree' in the doc)")
def buyday_state(df):
    return collections.Counter(state(r.Eb, r.sym_a if r.Eb <= A_LAST else r.sym) for r in df.itertuples())


scor = {"fit dated": f20[f20.san == "ok"], "fit undated nf": fu[(fu.san == "ok") & ~fu.flick], "fit flickers": fu[(fu.san == "ok") & fu.flick],
        "2021-22 dated": y2[y2.san == "ok"], "2021-22 undated nf": yu[(yu.san == "ok") & ~yu.flick], "2021-22 flickers": yu[(yu.san == "ok") & yu.flick],
        "virgin nf": ok_v[~ok_v.flick], "virgin flickers": ok_v[ok_v.flick]}
for k_, df_ in scor.items():
    st_ = buyday_state(df_)
    say(f"  scorable windows, buy-day minute state ({k_}): {dict(st_)}" + ("  empty: " + ", ".join(f"{r.sym} {r.Eb}" for r in df_.itertuples() if state(r.Eb, r.sym_a if r.Eb <= A_LAST else r.sym) == "empty") if st_.get("empty") else ""))
n_emp = sum(buyday_state(df_).get("empty", 0) for df_ in scor.values())
n_mis = sum(buyday_state(df_).get("missing", 0) for df_ in scor.values())
claim("@Thin minutes", "scorable ENTER windows whose BUY DAY has no minute bars at the source (read no_minutes) / not yet in any tree", "(counted, not stated)", f"{n_emp} / {n_mis}",
      "listed per block in the lines above; the scorable counts 31 / 59 / 34 / 17 / 9 / 20 / 43 are before this", kind="NOTE")
conf = 0
for k in TREE_ORDER:
    seen_ = {}
    for ln in open(TREES[k] + "/_done.psv"):
        f = ln.rstrip("\n").split("|")
        if len(f) >= 4 and f[0] <= CUT:
            kk = (f[0], f[1])
            if kk in seen_ and seen_[kk] != f[3]:
                conf += 1
            seen_[kk] = f[3]
claim("--", "pairs logged twice with different statuses inside one tree (the loaders keep the last row)", 0, conf)
m60 = re.search(r"exit-window first sessions with minute bars in a tree: (\d+) of (\d+)", chk_txt)
claim("@60 of 230 trades", "'the exit windows' first sessions on 60 of 230 trades' vs the predecessor's check printout", "60 of 230", f"{m60.group(1)} of {m60.group(2)}" if m60 else "not found",
      "transcription of 01_rev_check.txt (its G8 block); a count over the check set's trades, from minute-tree coverage, not bars")
claim("@60 of 230 trades", "1,302 of the 1,322 pairs of the 10-24 list have minute bars", "1302 of 1322", f"{sum(1 for v in DONE['REV'].values() if v == 'ok')} of {len(DONE['REV'])}")
rev_list = [ln for ln in open(TREES["REV"] + "/fetch_list.psv").read().splitlines() if ln]
claim("@60 of 230 trades", "the 10-24 fetch list file rows", 1322, len(rev_list))
axn = ni[ni.sym == "AXNX"]
axd = sorted(d for (d, t), v in DONE['REV'].items() if v == 'empty' and t == 'AXNX')
claim("@seven are AXNX", "REV empties: total / AXNX / all AXNX days in January 2020", "20 / 7 / True",
      f"{sum(1 for v in DONE['REV'].values() if v == 'empty')} / {len(axd)} / {all(d.startswith('2020-01') for d in axd)}", f"{axd[0]}..{axd[-1]}")
claim("@seven are AXNX", "AXNX in the virgin block's TRADE list ('now in the untouched block')", "in the untouched block",
      f"AXNX is a {int(axn.wl.iloc[0])}-session window ({axn.lo.iloc[0]}..{axn.hi.iloc[0]}), not an exact-day trade: in the virgin block's 89 trades: {bool(set(axn.eid) & set(virgin.eid))}",
      "the seven days fall inside the untouched DATE range (before 2020-01-27) but the AXNX buy is not one of the 89 trades; only a pair in the walked sessions would matter",
      kind="NOTE")

# ================================================================================================================ the 60-minute bars and early closes
say("\n## 9. The 60-minute bars and early closes")
rt = open(os.path.join(REPO, "scripts/probes/_cb_backtest/runner.py")).read()
mm = re.search(r"H60_EARLY_CLOSE = frozenset\(\{(.*?)\}\)", rt, re.S)
early = re.findall(r"\d{4}-\d{2}-\d{2}", mm.group(1))
e_in = [d for d in early if d <= CUT]
claim("@20 early-close days", "the runner's early-close list: dates", 20, len(early))
claim("@20 early-close days", "  of them inside this read's 2024-12-31 cut / all in the session calendar / 2025 dates", "(20 named; 2025 is sealed)", f"{len(e_in)} / {all(d in CALSET for d in e_in)} / {len(early) - len(e_in)}", kind="NOTE")
ends = [29] + list(range(29 + 60, 389 + 1, 60))
starts = [0] + [e + 1 for e in ends[:-1]]
claim("@[0,29], [30,89]", "60-minute windows of a full session", "[0,29] [30,89] [90,149] [150,209] [210,269] [270,329] [330,389] (7)", f"{' '.join(f'[{a_},{b_}]' for a_, b_ in zip(starts, ends))} ({len(ends)})")
ends_e = [e for e in ends if e <= 209]
claim("@[0,29], [30,89]", "windows on an early-close day", "4, last [150,209]", f"{len(ends_e)}, last [{starts[len(ends_e) - 1]},{ends_e[-1]}]")
claim("@70 bars", "EMA seed weight left after the 50 bars beyond the 20-bar seed: (19/21)^50 ('under 1%')", "< 1%", f"{(19 / 21) ** 50:.2%}", kind="OK" if (19 / 21) ** 50 < 0.01 else "MISMATCH")
claim("@a share read on 9 trades", "binomial 95% half-width of a 50% share on 9 trades (points) - doc 'carries +-30 points'", "+-30", f"+-{196 * math.sqrt(0.25 / 9):.0f}",
      "the doc rounds down; the half-width is about 33", kind="NOTE")
claim("@within ±15 points", "binomial 95% half-width on 35 trades (STOP: 'within +-15 points')", "+-15", f"+-{196 * math.sqrt(0.25 / 35):.0f}", kind="NOTE")

# ================================================================================================================ era-B offsets
say("\n## 10. Era-B offsets")
eb = uc[uc.eraB].sort_values("eidn")
offs = [f"{r.exit_lo_i - r.Eb_i}-{r.exit_hi_i - r.Eb_i}" for r in eb.itertuples()]
doc_offs = ["0-1", "4-4", "5-6", "5-6", "0-7", "2-6", "0-4", "0-4"]
claim("@0-1, 4-4, 5-6", "the 8 undated 2021-22 era-B trades: sell-window offsets from the buy day (as a set)", sorted(doc_offs), sorted(offs))
claim("@0-1, 4-4, 5-6", "  in eid order (the doc gives no order)", doc_offs, offs, kind="OK" if offs == doc_offs else "NOTE")
say(f"  in buy-day order: {[f'{r.exit_lo_i - r.Eb_i}-{r.exit_hi_i - r.Eb_i}' for r in eb.sort_values(['Eb', 'eidn']).itertuples()]}")
claim("@about 1,440 sessions late", "unified-calendar index of 2021-09-27 (era B's first session: the offset error, 'about 1,440' / '~1,445')", "~1,440 / ~1,445", CI.get("2021-09-27"),
      kind="OK" if abs(CI.get("2021-09-27") - 1445) <= 10 else "MISMATCH")
claim("@about 1,440 sessions late", "check trades affected by the era-B defect", 8, int(uc.eraB.sum()))
walked = pd.concat([fit_tr, virg_tr, y2122_tr])
hold = (walked.exit_hi_i - walked.Eb_i)[walked.has_exit]
claim("@refuses", "walked trades with a negative hold or a hold beyond the calendar: min / max sessions (largest = a stream gap)", "(none)", f"{int(hold.min())} / {int(hold.max())}", kind="NOTE")

# ================================================================================================================ captions
say("\n## 11. Captions (section 8): 495 files")
sys.path.insert(0, os.path.join(REPO, "scripts", "probes", "_qm_streams"))
import qmlib  # the project's caption parser (rolling-repeat de-duplication)

paths = sorted(glob.glob(QS + "subs/*.vtt"))
claim("@495 caption files", "caption files", 495, len(paths))
RAW = {os.path.basename(p).split(".")[0]: open(p, errors="replace").read().lower() for p in paths}
PAR = {os.path.basename(p).split(".")[0]: " ".join(w.lower() for _, w in qmlib.parse_vtt(p)) for p in paths}
P_A = re.compile(r"60[ -]?min|hourly|hour chart")
P_B = re.compile(r"60[ -]?min|hourly|hour chart|one hour|1 hour")
P_60 = re.compile(r"60[ -]?min")
P_EMA = re.compile(r"(20|twenty)[ -]?ema")
P_S8 = re.compile(r"(60[ -]?min(ute)?|hourly).{0,80}(20|twenty)[ -]?(ema|day)|(20|twenty)[ -]?ema.{0,80}(60[ -]?min(ute)?|hourly)")


def nfiles(rx, D_):
    return sum(1 for t in D_.values() if rx.search(t))


claim("@334 of 495", "'334 of 495 caption files mention the 60-minute chart' (the previous registration): 60[ -]?min", 334, f"raw vtt {nfiles(P_60, RAW)} | parsed words {nfiles(P_60, PAR)}",
      "reproduces only on the raw vtt text (inline timing tags in), not on the parsed words the section-8 join rule reads", kind="OK" if nfiles(P_60, RAW) == 334 else "MISMATCH")
claim("@344 files", "files matching the printed pattern 60[ -]?min|hourly|hour chart", 344,
      f"raw vtt {nfiles(P_A, RAW)} | parsed words {nfiles(P_A, PAR)}; raw with 'one hour|1 hour' added {nfiles(P_B, RAW)}",
      "344 appears only if 'one hour|1 hour' is added to the pattern, on raw text", kind="MISMATCH")
claim("@344 files", "files mentioning the 20 EMA ((20|twenty)[ -]?ema)", 103, f"raw vtt {nfiles(P_EMA, RAW)} | parsed words {nfiles(P_EMA, PAR)}", "reproduces only on raw text",
      kind="OK" if nfiles(P_EMA, RAW) == 103 else "MISMATCH")
claim("@344 files", "files carrying both within 80 characters (the section-8 pattern)", 169,
      f"parsed words {nfiles(P_S8, PAR)} | raw vtt {nfiles(P_S8, RAW)} | raw, dot spanning lines {sum(1 for t in RAW.values() if re.search(P_S8.pattern, t, re.S))}",
      f"no reading of 'within 80 characters' reaches 169; files with both patterns ANYWHERE: raw {sum(1 for t in RAW.values() if P_B.search(t) and P_EMA.search(t))}, "
      f"parsed {sum(1 for t in PAR.values() if P_B.search(t) and P_EMA.search(t))}", kind="MISMATCH")
fsly = [v for v, t in PAR.items() if re.search(r"fastly.{0,120}sold half of it 2 days ago when it broke below the 20.{0,60}60[ -]?minute chart.{0,200}previous day's lows", t)]
claim("@FSLY 2020-07-14: half sold", "FSLY 2020-07-14 words (half on the 20 EMA on the 60-minute chart, the rest on the previous day's low) in a caption", "present", f"present in {len(fsly)} file(s): {fsly}" if fsly else "absent",
      kind="OK" if fsly else "MISMATCH")

# ================================================================================================================ transcription checks
say("\n## 12. Transcription checks: the numbers the doc quotes from the predecessor, against its own printouts")
rc = open(os.path.join(PREV_DIR, "verify", "recount", "recount_check.txt")).read()
for anc, label, doc, pattern, text in (
    ("@36.6%, first-hour 22.0% feasible", "5-minute opening-range high feasible on 2021-22 undated (L1)", "36.6%", r"L1: feasible 15/41 = (36\.6%)", rc),
    ("@36.6%, first-hour 22.0% feasible", "first-hour high feasible (L6)", "22.0%", r"L6: feasible 9/41 = (22\.0%)", rc),
    ("@undated windows it read 31.7%", "random-price control feasible on 2021-22 undated", "31.7%", r"over all 61\): feasible (31\.7%)", rc),
    ("@85.9%", "random-price control hit-or-ballpark", "85.9%", r"feasible 31\.7%, hit-or-ballpark (85\.9%)", rc),
    ("@39.2%", "S1-T on 2021-22 undated, era-B fixed", "39.2%", r"S1-T +\|[^|]*\|[^|]*\|[^|]*\| (39\.2%)", rc),
    ("@39.2%", "S1-C", "41.5%", r"S1-C +\|[^|]*\|[^|]*\|[^|]*\| (41\.5%)", rc),
    ("@39.2%", "S3-T", "68.0%", r"S3-T +\|[^|]*\|[^|]*\|[^|]*\| (68\.0%)", rc),
    ("@39.2%", "S3-C", "57.8%", r"S3-C +\|[^|]*\|[^|]*\|[^|]*\| (57\.8%)", rc),
    ("@1.87", "dated 2021-22 his / ours", "1.87", r"his / ours (1\.87)", chk_txt),
    ("@1.87", "dated 2021-22 ours", "1.398", r"ours (1\.398)", chk_txt),
    ("@1.87", "dated 2021-22 his", "2.620", r"his (2\.620)", chk_txt),
    ("@0.027", "daily list recovery on dated 2021-22", "-0.027", r"recovery (-0\.027)", chk_txt),
    ("@37.7%", "daily list hit rate on undated 2021-22 (era-B fixed)", "37.7%", r"hit rates \(era-B offsets fixed[^)]*\): chosen list (37\.7%)", rc),
    ("@his ÷ ours 1.15", "undated 2021-22 his / ours", "1.15", r"his / ours (1\.15)", chk_txt),
    ("@L1 36.0% feasible on 89", "L1 feasible on the 2020 fit records", "36.0%", r"L1: feasible 32 = (36\.0%)", fit_enter),
    ("@kept 89 of 91", "the previous fit kept 89 records", "89", r"records: (89) \(dropped", fit_enter),
    ("@kept 212 of 226", "the STOP / EXIT check kept 212 records of 226", "212", r"STOP / EXIT records (212) of 226", rc),
    ("@98 of 212", "low of the day (S1-T) traded through on 98 of 212", "98", r"S1-T +\| 43\.9% \((98) /", rc),
    ("@65% of his unseen buys", "SELECT recall on the check (doc '65%')", "64.8%", r"recall (64\.8%)", chk_txt),
    ("@65% of his unseen buys", "SELECT pool rate on the check (doc 'one stock in five')", "18.6%", r"pool rate (18\.6%)", chk_txt),
):
    mt = re.search(pattern, text)
    claim(anc, label, doc, mt.group(1) if mt else "not found", "transcription of the predecessor's printout")
claim("@98 of 212", "98 / 212 and 97 / 212 (era-B fixed) against the doc's 'about 45%'", "about 45%", f"{98 / 212:.1%} / {97 / 212:.1%}", "46.2% as printed, 45.8% after the era-B fix", kind="NOTE")
# the predecessor's STOP range 'every level held through on 39-80%'
fixed_col = {}
for ln in rc.splitlines():
    mt = re.match(r"\s+(S\d|SMA50)-([TC])\s+\|(.*)", ln)
    if mt:
        cols_ = [c_.strip() for c_ in mt.group(3).split("|")]
        mv = re.match(r"(\d+\.\d)%", cols_[3])           # column 5: 'recount, era-B offsets fixed'
        mm0 = re.match(r"(\d+\.\d)%", cols_[2])          # column 4: the module's offsets
        fixed_col[f"{mt.group(1)}-{mt.group(2)}"] = (float(mv.group(1)) if mv else None, float(mm0.group(1)) if mm0 else None)
choos = [k for k in fixed_col if k.startswith(("S1-", "S2-", "S3-", "S4-", "S5-", "S6-", "S7-"))]
fx = [fixed_col[k][0] for k in choos]
md = [fixed_col[k][1] for k in choos]
s14 = [fixed_col[k][0] for k in fixed_col if k.startswith(("S1-", "S2-", "S3-", "S4-"))]
claim("@39-80%", "STOP INCONCLUSIVE: 'every level held through on 39-80% of the trades where price crossed it' (the predecessor's RESULT row, restated here): H_cond over S1-S7", "39-80%",
      f"era-B fixed {min(fx):.1f}-{max(fx):.1f}% ({max(choos, key=lambda k: fixed_col[k][0])} is the top); as printed (module offsets) {min(md):.1f}-{max(md):.1f}%; S1-S4 only, fixed {min(s14):.1f}-{max(s14):.1f}%",
      "the 39 is the era-B-fixed S1-T, the 80 the unfixed S4-C (66.7% after the fix); S5-T, S6-T, S7-T sit at 99 / 85 / 85%", kind="MISMATCH")
m26 = re.search(r"RECOUNT COMPLETE in \d+s: (\d+) MATCH, (\d+) MISMATCH", rc)
claim("@the recount's one MISMATCH", "the previous recount's one MISMATCH (era-B calendar index)", "1", m26.group(2) if m26 else "not found", f"recount_check.txt: {m26.group(0) if m26 else ''}")
claim("@the recount's one MISMATCH", "  and its era-B pickle indices of the exit window (the 'about 1,440 sessions late')", "1443-1450", (re.search(r"\| (1443-1450) \(check_exit_trades", rc) or [None, "not found"])[1])
md_dry = open(os.path.join(PREV_DIR, "01_rev_dryrun.txt")).read()
m63 = re.search(r"## RESULT: (\d+) claims, (\d+) OK, (\d+) MISMATCH", md_dry)
claim("@previous dry run's 63 counts", "the previous dry run's counts (claims / OK / MISMATCH)", "63", f"{m63.group(1)} / {m63.group(2)} / {m63.group(3)}" if m63 else "not found", kind="OK" if m63 and m63.group(1) == "63" else "MISMATCH")
kold = ni[(ni.sym == "KOLD") & (ni.Eb == "2022-04-19")]
claim("@KOLD out", "KOLD 2022-04-19 leaves the held-before-09:35 list by the type gate (type not CS / ADRC / untyped)", "out by the type gate", f"type {kold.sec_type.iloc[0]!r}, type_ok {bool(kold.type_ok.iloc[0])}",
      kind="OK" if not bool(kold.type_ok.iloc[0]) else "MISMATCH")
mdate = re.search(r"beside, L1 on the dated 2021-22 brackets \(a re-read; 20\): feasible (\d+\.\d)%", chk_txt)
claim("@dated 60% vs undated 37%", "2021-22 L1 feasible: dated (a re-read) / undated", "60% / 37%", f"{round(float(mdate.group(1)))}% / {round(36.6)}%" if mdate else "not found", "transcription of 01_rev_check.txt / recount_check.txt")
try:
    sj = json.load(open(H + "reverse/select_fit_chosen.json"))["text"]
except Exception as ex_:                              # noqa: BLE001
    sj = f"unreadable: {ex_}"
claim("@ADR20 ≥ 4.26%", "SELECT's passed condition set (the chosen json)", "F3<=233 & F9>=-0.05785 & F10>=0.04256 -> 233 sessions / 5.8% / 4.26%", sj,
      "the doc rounds 0.05785 to 5.8% and 0.04256 to 4.26%; F3 / F9 / F10 meanings are the predecessor's feature list", kind="OK" if sj == "F3<=233 & F9>=-0.05785 & F10>=0.04256" else "MISMATCH")

# ---- his words and their line numbers ----------------------------------------------------------------------------------------------------
notes = open(os.path.join(REPO, "docs", "methodology", "operator_shared_notes.md")).read().splitlines()


def nline(s):
    return [i for i, ln in enumerate(notes, 1) if s in ln]


say("- his words in operator_shared_notes.md:")
def in_range(lines_, lo_, hi_):
    return bool(lines_) and all(lo_ <= x <= hi_ for x in lines_)


_e, _st, _h60 = nline("Enter on the opening range highs"), nline("Stop is always lows of the day"), nline("on the 60-minute timeframe the first candle")
claim("@l.1941-1942, l.1944, l.2090-2091", "'Enter on the opening range highs...' starts at (doc: l.1941-1942)", "within 1941-1942", _e, kind="OK" if in_range(_e, 1941, 1942) else "MISMATCH")
claim("@l.1941-1942, l.1944, l.2090-2091", "'Stop is always lows of the day...' sits at (doc: l.1944)", "1944", _st,
      "l.1944 is the next bullet ('Size'); the Stop quote is one line earlier. The doc also lists the refs in a different order from its quotes (entry, 60-minute candle, stop)")
claim("@l.1941-1942, l.1944, l.2090-2091", "'(on the 60-minute timeframe the first candle is always only 30 minutes...' starts at (doc: l.2090-2091)", "within 2090-2091", _h60,
      kind="OK" if in_range(_h60, 2090, 2091) else "MISMATCH")
claim("@let's continue", "the ruling 'let's continue with option 1 tmr' sits in the last section", "last section", nline("let's continue with option 1 tmr"), kind="NOTE")

# ---- the pins named in the registration -----------------------------------------------------------------------------------------------
say("\n## 13. Pins named in the registration")
pf_py = os.path.join(REPO, "scripts/probes/_705_intraday_1025/00_pop_fetch.py")
pf_tx = os.path.join(REPO, "scripts/probes/_705_intraday_1025/00_pop_fetch.txt")
claim("@(sha256 `b7b75d56", "00_pop_fetch.py sha256 prefix", "b7b75d56", sha(pf_py)[:8])
claim("@(sha256 `b7b75d56", "00_pop_fetch.txt sha256 prefix", "d6bd0f67", sha(pf_tx)[:8])
claim("@(sha256 `b7b75d56", "the copy beside the fetch lists equals the repo printout", "identical", "identical" if sha(INTRA_MIN + "/00_pop_fetch.txt") == sha(pf_tx) else "differs")
pt = open(pf_tx).read()
src = open(pf_py).read()
rev_src = open(os.path.join(PREV_DIR, "01_rev.py")).read()
core = rev_src[rev_src.index("def load_core"):rev_src.index("def load_markets")]
forb = ("read_minutes", "read_minute_file", "bars_of", "load_markets", "load_daily_subset", "load_raw_flat", "load_raw_close", "MinuteBars", "day0_walk", "simulate", "trade_impact", "minute_bars_from_rows")
claim("@No price bar", "00_pop_fetch.py and the loader it calls (load_core) contain no price / minute-bar reader (static scan of the source)", "none",
      sorted({f_ for f_ in forb if f_ in src or f_ in core}) or "none", "names scanned: " + ", ".join(forb))
claim("@No price bar", "00_pop_fetch.py reads nothing dated after the cut itself (it passes the 2024-12-31 cut to the done-log loader and cuts the calendar)", "cut applied",
      "cut applied" if ("CUT_B" in rev_src and "cal = [d for d in cal_all if d <= CUT_B]" in core) else "not found")
claim("@19,470 pairs", "00_pop_fetch.txt reports the same two list shas as the files on disk", "both",
      "both" if ("sha256 " + sha(LIST_FULL) in pt and "sha256 " + sha(LIST_HOLD) in pt) else "not both")

# ================================================================================================================ after the registration: the fetch
say("\n## 15. After the registration (not doc claims): the minute fetch has since run into the intra folder - fetch log and _done.psv only, no bar file opened")
fl_txt = open(INTRA_MIN + "/fetch.log").read().splitlines() if os.path.exists(INTRA_MIN + "/fetch.log") else []
fl_first = next((x for x in fl_txt if " list:" in x), "")
fl_done = next((x for x in fl_txt if " done:" in x), "")
say(f"- fetch.log: {fl_first[20:] if fl_first else 'absent'} | {fl_done[20:] if fl_done else 'not finished'}")
if fl_done:
    sp_ = log_span(INTRA_MIN + "/fetch.log")
    claim("@8-12 minutes", "the fetch has since run: wall time (minutes) against the doc's '8-12 minutes' / its '~1,032 requests' against the doc's 'about 1,100'", "8-12 / about 1,100",
          f"{sp_ / 60:.1f} / {re.search(r'~([0-9,]+) requests', fl_first).group(1) if re.search(r'~([0-9,]+) requests', fl_first) else '?'}", kind="NOTE")
if os.path.exists(INTRA_MIN + "/_done.psv"):
    IDONE, idrop = load_done(INTRA_MIN)
    listed = {(tk, d) for (tk, d), _b in rowsB}
    in_done = {(tk, d) for (d, tk) in IDONE}
    claim("--", "fetch log vs the list: rows in the log, listed pairs not in the log, logged pairs not listed", "19470 / 0 / 0", f"{len(IDONE)} / {len(listed - in_done)} / {len(in_done - listed)}", "the fetch ran exactly the list")
    stc = collections.Counter(IDONE.values())
    claim("--", "fetch outcome (statuses)", "(not in the doc)", dict(stc), f"rows after the cut dropped at read: {idrop}", kind="NOTE")
    empt = {(tk, d) for (d, tk), v in IDONE.items() if v == "empty"}
    blk_e = collections.Counter("+".join(sorted(b)) for (tk, d), b in rowsB if (tk, d) in empt)
    say(f"  empty pairs by block: {dict(blk_e)}; by year: {dict(sorted(collections.Counter(d[:4] for _t, d in empt).items()))}")

    def state2(d, tk):
        st = state(d, tk)
        if st == "missing":
            v = IDONE.get((d, tk))
            return "ok2" if v == "ok" else ("empty" if v == "empty" else "missing")
        return st

    def trade_gaps(df):
        hold_gap = warm_gap = tail_gap = 0
        for r in df.itertuples():
            j1 = r.exit_hi_i if r.has_exit else min(r.Eb_i + NOEXIT, len(CAL) - 1)
            jt = min(r.exit_hi_i + TAIL, len(CAL) - 1) if r.has_exit else j1
            def anyemp(a_, b_):
                return any(state2(CAL[i], r.sym_a if CAL[i] <= A_LAST else r.sym) in ("empty", "missing") for i in range(a_, b_ + 1))
            hold_gap += int(anyemp(r.Eb_i, j1))
            warm_gap += int(anyemp(max(0, r.Eb_i - WARM), r.Eb_i - 1))
            tail_gap += int(r.has_exit and anyemp(r.exit_hi_i + 1, jt))
        return hold_gap, warm_gap, tail_gap
    for nm_, df_ in (("fit 2020", fit_tr), ("virgin block", virg_tr), ("2021-22", y2122_tr)):
        hg, wg, tg = trade_gaps(df_)
        say(f"  trades with at least one session with no minute bars at the source or still missing: hold {hg}, warm-up {wg}, tail {tg} (of {len(df_)} trades) - {nm_}")
    still_missing = sum(1 for (tk, d) in listed if state2(d, tk) == "missing")
    claim("--", "listed pairs still missing after the fetch (neither ok nor empty in any tree)", 0, still_missing, kind="NOTE")
else:
    say("- no _done.psv in the intra folder yet")

# ================================================================================================================ not recountable
say("\n## 14. Not recountable from the allowed inputs (price or outcome material; left unverified, not assumed)")
for anc, txt in (("@about 80 records", "STOP: 'about 80 records', '30-40 traded through' on the tight levels (needs the 50-bar floor and daily bars)"),
                 ("@a record needs 20 bars", "the 20-bar record floor on the new fit (needs bars before the buy day)"),
                 ("@Hit-or-ballpark above 85%", "section 10's expectations (guesses to be scored later)")):
    claim(anc, txt, "-", "-", kind="NR")

bad = [c_ for c_ in CLAIMS if c_[4] == "MISMATCH"]
say(f"\n## RESULT: {len(CLAIMS)} lines, {sum(1 for c_ in CLAIMS if c_[4] == 'OK')} OK, {len(bad)} MISMATCH, {sum(1 for c_ in CLAIMS if c_[4] == 'NOTE')} NOTE, {sum(1 for c_ in CLAIMS if c_[4] == 'NR')} not recountable")
if UNRESOLVED:
    say("  (anchors not found in the doc, line shown as '?'): " + "; ".join(sorted(set(UNRESOLVED))))
for ln, label, doc, mine, status, note in bad:
    say(f"  MISMATCH [L{ln}] {label}: doc {fmt(doc)} vs mine {fmt(mine)}" + (f" (note: {note})" if note else ""))
with open(OUT_TXT, "w") as fh:
    fh.write("\n".join(LINES) + "\n")
