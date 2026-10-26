#!/usr/bin/env python3
"""Independent pre-freeze recount of docs/analysis/cb_rule_mix_prereg_2026-10-25.md (REGISTERED, NOT FROZEN, NOT RUN).

The registration is NOT edited. Neither predecessor recount is imported (both execute everything at import and one writes its own record);
their loader logic is re-typed here. Nothing from the frozen modules is imported or executed - the frozen intraday module is read as TEXT
(constants, function names) and by sha256 only.

OUTCOME-FREE. Reads ONLY:
  - the holdings timeline's TSVs (entries / exits / snapshots) and the reverse stage's dryrun_clocks.tsv (borrowed set membership, itself
    checked row by row against a derivation from the timeline);
  - the session calendars (pickle cut at 2024-12-31 at read), the two type tables, the minute trees' fetch logs (_done.psv) and DIRECTORY
    listings (NO bar file of any tree is opened), the fetch lists;
  - the intraday / reverse printouts (transcription of the numbers the doc copies, at the lines the doc cites);
  - the intraday side outputs' per-trade TSVs, tallying ONLY columns the frozen stage already wrote and printed (row counts per block,
    `*_feasible` flags, `E*_hit` / `E1_stop_preempt` flags) - no rule is fired, no held-through or exit is computed, no price is read;
  - the exits study and operator_shared_notes.md (quotes + line cites), two caption files (cue times), the frozen module as TEXT.
Nothing dated after 2024-12-31 (asserted on every date list); replay/ and his_exits/ are never opened.

Output: one line per claim `[Ldoc] label | doc | mine | OK / MISMATCH / NOTE`; the MISMATCH lines are listed again at the end.
"""
import collections
import datetime
import glob
import gzip
import hashlib
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
INTRA = H + "intraday/"
REVO = H + "reverse/"
OUT_TXT = os.path.join(HERE, "recount_prefreeze.txt")
DOC = os.path.join(REPO, "docs", "analysis", "cb_rule_mix_prereg_2026-10-25.md")
P_INT = os.path.join(REPO, "scripts", "probes", "_705_intraday_1025")
P_REV = os.path.join(REPO, "scripts", "probes", "_705_reverse_1024")
F_ENT = os.path.join(P_INT, "01_intra_enter_fit.txt")
F_STP = os.path.join(P_INT, "01_intra_stop_fit.txt")
F_EXT = os.path.join(P_INT, "01_intra_exit_fit.txt")
F_CHK = os.path.join(P_INT, "01_intra_check.txt")
F_RENT = os.path.join(P_REV, "01_rev_enter_fit.txt")
F_STUDY = os.path.join(REPO, "docs", "analysis", "cb_his_exits_study_2026-10-24.md")
F_NOTES = os.path.join(REPO, "docs", "methodology", "operator_shared_notes.md")
F_MOD = os.path.join(P_INT, "01_intra_frozen_ac598fc58aae.py")
F_INTRA_DOC = os.path.join(REPO, "docs", "analysis", "cb_intraday_layer_prereg_2026-10-25.md")
INTRA_MIN = f"{DATA}/cb702/minutes_intra_1025"
LIST_FULL = f"{INTRA_MIN}/fetch_list_intra_1025.psv"

CUT = "2024-12-31"
A_LAST = "2022-03-31"
FIT = ("2020-01-27", "2020-12-31")
CHK = ("2021-01-04", "2022-06-14")
DENSE = ("2020-01-27", "2022-06-14")
WARM, TAIL, NOEXIT = 10, 20, 20
TREES = {"A": f"{DATA}/cb702_pre_v2/minutes", "B": f"{DATA}/cb702/minutes", "EP": f"{DATA}/cb702/minutes_ep_1023",
         "EP2": f"{DATA}/cb702/minutes_ep_1024", "REV": f"{DATA}/cb702/minutes_rev_1024"}
TREE_ORDER = ("A", "B", "EP", "EP2", "REV")

LINES, CLAIMS = [], []
DOC_TOKEN_WARN = []
DL = open(DOC, encoding="utf8").read().splitlines()
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


def numeq(doc, mine):
    """doc and mine are texts with numbers; equal count, and each mine rounded to the DOC token's decimals equals the doc token."""
    dt = re.findall(r"-?\d+(?:\.\d+)?", str(doc).replace(",", ""))
    mt = re.findall(r"-?\d+(?:\.\d+)?", str(mine).replace(",", ""))
    if len(dt) != len(mt) or not dt:
        return False
    for d, m in zip(dt, mt):
        dec = len(d.split(".")[1]) if "." in d else 0
        if round(float(m), dec) != float(d):
            return False
    return True


def claim(line, label, doc, mine, note="", kind=None, tol=False):
    """doc / mine compared as printed text. kind None -> OK if equal else MISMATCH; 'OK'/'MISMATCH' forced; 'NOTE' informational.
    `line` = a doc line number, '--' (not a doc claim) or '@anchor' (the first doc line containing the anchor text)."""
    if isinstance(line, str) and line.startswith("@"):
        line = LN(line[1:])
    if kind is None and tol:
        kind = "OK" if numeq(doc, mine) else "MISMATCH"
    status = ("OK" if fmt(doc) == fmt(mine) else "MISMATCH") if kind is None else kind
    if isinstance(line, int) and kind != "NOTE":
        win = " ".join(DL[max(0, line - 3):line + 1]).replace(",", "")
        toks = re.findall(r"\d+(?:\.\d+)?", str(doc).replace(",", ""))
        lost = [t for t in toks if t not in win]
        if lost:
            DOC_TOKEN_WARN.append((line, label, str(doc), lost))
    CLAIMS.append((line, label, doc, mine, status, note))
    say(f"[L{line}] {label} | doc {fmt(doc)} | mine {fmt(mine)} | {status}" + (f" | {note}" if note else ""))
    return status


_TXT = {}


def lines_of(path):
    if path not in _TXT:
        _TXT[path] = open(path, encoding="utf8").read().split("\n")
    return _TXT[path]


def L(path, n):
    return lines_of(path)[n - 1]


def grab(path, n, pat):
    """regex groups of line n of a file, or None."""
    m = re.search(pat, L(path, n))
    return m.groups() if m else None


def tr(anchor, label, doc, path, n, pat, note="", sep=" / ", tol=False):
    """transcription claim: the number(s) the doc copies vs the cited line of the printout."""
    g = grab(path, n, pat)
    mine = sep.join(g) if g else f"NO MATCH at {os.path.basename(path)} l.{n}: {L(path, n)[:120]!r}"
    return claim(anchor, f"{label} [{os.path.basename(path)} l.{n}]", doc, mine, note, tol=tol)


def pct(a, b, nd=1):
    return f"{100.0 * a / b:.{nd}f}%"


def sha(path):
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for ch in iter(lambda: fh.read(1 << 20), b""):
            h.update(ch)
    return h.hexdigest()


def hm(c):
    if not c:
        return None
    h, m = c.split(":")
    return int(h) * 60 + int(m) - 570


def assert_le_cut(dates, what):
    bad = [d for d in dates if d > CUT]
    assert not bad, f"{what}: dates after the 2024-12-31 cut were read: {bad[:3]}"


say("# #705 RULE-MIX registration: independent pre-freeze recount (OUTCOME-FREE: timeline TSVs, clocks, calendars, fetch logs, printout lines)")
say("# registration: docs/analysis/cb_rule_mix_prereg_2026-10-25.md (not edited); no predecessor recount imported; the frozen module read as text + sha only")
say("")

# =============================================================================================================== inputs (re-typed loaders)
T = pd.read_csv(H + "entries.tsv", sep="\t", dtype=str, keep_default_na=False)
X = pd.read_csv(H + "exits.tsv", sep="\t", dtype=str, keep_default_na=False)
SN = pd.read_csv(H + "snapshots.tsv", sep="\t", dtype=str, keep_default_na=False)
DRY = pd.read_csv(REVO + "dryrun_clocks.tsv", sep="\t", dtype=str, keep_default_na=False)
SNI = SN.set_index("frame_id")
assert SNI.index.is_unique and DRY.eid.is_unique and len(DRY) == 1861
with gzip.open(QS + "vision/positions_pct_calendar.pkl.gz", "rb") as fh:
    _cal_all, _sig = pickle.load(fh)
del _sig
CAL = [d for d in _cal_all if d <= CUT]
del _cal_all
SESS_A = [ln.strip() for ln in open(f"{DATA}/cb702_pre_v2/sessions.txt") if ln.strip()]
assert CAL[:len(SESS_A)] == SESS_A and all(a < b for a, b in zip(CAL, CAL[1:]))
CI = {d: i for i, d in enumerate(CAL)}
say(f"- inputs: entries {len(T):,} rows, exits {len(X):,}, snapshots {len(SN):,}, dryrun_clocks {len(DRY):,}; calendar {CAL[0]}..{CAL[-1]} = {len(CAL):,} sessions "
    f"(era A sessions.txt {len(SESS_A):,}, last {SESS_A[-1]}); nothing after {CUT} kept")

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
        return "CS"
    return SMALL.get(t, "") or SIC.get(t, "") or ""


ni = T[T.initial == "False"].copy()
ni["eidn"] = ni.eid.astype(int)
ni["wl"] = pd.to_numeric(ni.window_len)
ni["flick"] = ni.flicker == "True"
ni["dated"] = ni.setup.isin(["breakout", "EP", "both"])
ni["undated"] = ni.setup == "undated"
ni["Eb"] = np.where(ni.dated, ni.E, ni.lo)
ni["yr"] = ni.Eb.str[:4].astype(int)
ni["key_era"] = np.where(ni.dated, ni.era, np.where(ni.Eb <= A_LAST, "A", "B"))
ni["eraB"] = ni.Eb > A_LAST
ni["inv"] = ni.inverted == "True"
ni["dec"] = ni.decides == "True"
ni["noev"] = ni.undated & (ni.undated_reason == "no_event_in_window")
for c in ("lo", "hi", "exit_lo", "exit_hi", "Eb"):
    ni[c + "_i"] = ni[c].map(lambda d: CI.get(d, -1) if d else -1)
ni["has_exit"] = ni.exit_hi_i >= 0
assert (ni.lo_i >= 0).all() and (ni.hi_i >= 0).all() and (ni.Eb_i >= 0).all()
assert ((ni.hi_i - ni.lo_i + 1) == ni.wl).all()
assert_le_cut(list(ni.Eb) + list(ni.exit_hi[ni.exit_hi != ""]), "entries")
ni["tkey"] = np.where(ni.Eb <= A_LAST, ni.sym_a, ni.sym)
ni["sec_type"] = ni.tkey.map(type_of)
ni["type_ok"] = ni.sec_type.isin(["CS", "ADRC", ""])
sdr, seen = set(), {}
for r in ni[ni.has_bars == "True"].sort_values("eidn").itertuples():
    tk = r.sym_a if r.key_era == "A" else r.sym
    k = (r.key_era, tk, r.Eb, r.undated)
    if k not in seen:
        seen[k] = r.eid
    else:
        sdr.add(r.eid)
ni["sdr"] = ni.eid.isin(sdr)
ni["gate"] = ni.type_ok & ~ni.inv & ~ni.sdr


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
ni["inb"] = (ni.fc != "") & (ni.flc != "") & (ni.p_ctx == "in")
ni["prefl"] = (ni.fc != "") & (ni.flc != "") & (ni.p_ctx == "pre")
ni["hb0935"] = (ni.fc != "") & (ni.fc < "09:35")

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
fd, cd_ = inwin(dec_used, FIT), inwin(dec_used, CHK)
uf, uc = G(inwin(ex_all, FIT)), G(inwin(ex_all, CHK))
sf, sc = uf[~uf.flick], uc[~uc.flick]

# ---- the borrowed table (dryrun_clocks / set membership) checked against this derivation -------------------------------------------------
say("\n## 0. The borrowed set membership (dryrun_clocks.tsv) checked against my own derivation from the timeline")
D = DRY.set_index("eid")
nd = ni.set_index("eid")
for dc, mc in (("first_clock_on_E", "fc"), ("flat_clock_on_E", "flc"), ("flat_ctx", "p_ctx"), ("first_ctx", "f_ctx")):
    claim("--", f"dryrun_clocks.{dc} vs my {mc} (rows that differ, of {len(nd)})", 0, int((D.loc[nd.index, dc].values != nd[mc].values).sum()))
for dc, mc in (("in_session_bracket", "inb"), ("pre_market_flat_bracket", "prefl"), ("inverted", "inv"), ("same_day_rebuy", "sdr"), ("type_ok", "type_ok")):
    claim("--", f"dryrun_clocks.{dc} vs my {mc} (rows that differ)", 0, int(((D.loc[nd.index, dc] == "True").values != nd[mc].values).sum()))
SETS_DRY = collections.defaultdict(set)
for r in DRY.itertuples():
    for s in r.sets.split(";"):
        SETS_DRY[s].add(int(r.eid))
mine_sets = {"und_fit": uf, "und_chk": uc, "stop_fit_dated": fd, "stop_chk_dated": cd_, "dec_used": dec_used,
             "ent_fit_dated": fd[fd.inb], "ent_chk_dated": cd_[cd_.inb], "ent_fit_und": sf[sf.inb], "ent_chk_und": sc[sc.inb],
             "ent_fit_und_fl": uf[uf.inb], "ent_chk_und_fl": uc[uc.inb]}
for k, df in mine_sets.items():
    claim("--", f"my set {k} vs the reverse dry run's membership (eids in one but not the other)", 0, len(set(df.eidn) ^ SETS_DRY[k]), f"mine {len(df)}")

# =============================================================================================================== header / sec 0
say("\n## 1. Header and §0 (In plain words): the numbers copied from printouts")
tr("@best entry level was first crossed inside his", "§0: the best entry level's feasible share on the unseen windows / the bar (doc rounds to whole percents)",
   "45% / 50%", F_CHK, 80, r"feasible ([\d.]+%) < ([\d.]+%)", tol=True)
# stop ranges: library cells only vs all cells, on the deciding 62 (check l.135-152) and the 2020 fit (stop fit l.40-57)
def htable(path, first, last):
    out = {}
    for n in range(first, last + 1):
        m = re.match(r"\s+(\S+-[TCH])\s+\|\s+([\d.]+)%\s+\|\s+(\d+)\s+\|\s+(\d+)\s+\|\s+(\d+)\s+\|\s+([\d.]+)%", L(path, n))
        assert m, (path, n, L(path, n)[:100])
        out[m.group(1)] = float(m.group(6))
    return out


H62 = htable(F_CHK, 135, 152)
H20 = htable(F_STP, 40, 57)
lib = lambda d: {k: v for k, v in d.items() if k.split("-")[0] in ("S1", "S3", "S9", "S10")}
claim("@held through on 16-33%", "§0: H_cond range, the 12 LIBRARY cells (S1/S3/S9/S10 x T/C/H), the deciding 62 untouched (check l.135-146)",
      "16-33%", f"{min(lib(H62).values()):.0f}-{max(lib(H62).values()):.0f}%",
      f"the 16.1% is SMA50-T (l.150), a control the doc itself says is not in the library; all 18 printed cells: {min(H62.values()):.0f}-{max(H62.values()):.0f}% "
      f"(S8-C 12.5% is the floor); library-only floor is {min(lib(H62).items(), key=lambda kv: kv[1])}")
claim("@(25-61% on the 2020 fit)", "§0: H_cond range, the 12 library cells, the 2020 fit (stop fit l.40-51)", "25-61%",
      f"{min(lib(H20).values()):.0f}-{max(lib(H20).values()):.0f}%", f"all 18 printed cells: {min(H20.values()):.0f}-{max(H20.values()):.0f}% (SMA50-T 18.9%)")
rec_ = float(grab(F_CHK, 185, r"recovery ([+-][\d.]+)")[0])
claim("@recovered none of the gap", "§0: 'the 60-minute exit recovered none of the gap' - recovery on dated 2021-22 (check l.185), bar 0.25", "none (<= 0)", f"{rec_:+.3f}",
      kind="OK" if rec_ <= 0 else "MISMATCH")
tr("@explains 55% of his 2020", "§0: 'any opening range' 2020 feasible / random-price control (doc: 55% against 21%)", "55% / 21%",
   F_ENT, 34, r"feasible ([\d.]+%).*?\(([\d.]+%): a price", tol=True)
tr("@explains 55% of his 2020", "§0: 'any opening range' 2021-22 feasible / random-price control (doc: 62.5% against 30%)", "62.5% / 30%",
   F_CHK, 30, r"feasible ([\d.]+%).*?\(([\d.]+%): a price", tol=True)
u20 = grab(F_ENT, 34, r"feasible ([\d.]+%).*?\(([\d.]+%): a price")
u21 = grab(F_CHK, 30, r"feasible ([\d.]+%).*?\(([\d.]+%): a price")
claim("@the union of L7 / L1 / L8 is 55.2%", "§7: union 2020 / 2021-22, then random-price controls 2020 / 2021-22 (printed l.34 / l.30)", "55.2% / 62.5% / 21.0% / 30.0%",
      f"{u20[0]} / {u21[0]} / {u20[1]} / {u21[1]}")
# =============================================================================================================== §2 populations
say("\n## 2. The §2 table: populations recounted from the timeline; printed scorable counts transcribed")
claim("@The timeline is taken as is", "entries (1,874)", 1874, len(T))
sets = {}
virg_all = pd.concat([dec_used[dec_used.yr == 2019], G(ex_all[ex_all.yr == 2019]), dec_used[dec_used.yr == 2023], G(ex_all[ex_all.yr == 2023]),
                      dec_used[(dec_used.yr == 2022) & (dec_used.Eb > CHK[1])], G(ex_all[(ex_all.yr == 2022) & (ex_all.Eb > CHK[1])]),
                      dec_used[(dec_used.Eb >= "2020-01-01") & (dec_used.Eb < FIT[0])], G(ex_all[(ex_all.Eb >= "2020-01-01") & (ex_all.Eb < FIT[0])])])
v_dated, v_und = virg_all[virg_all.dated], virg_all[~virg_all.dated]
claim("@dated 149 + undated 304", "STOP 2020: dated / undated (flickers in)", "149 / 304", f"{len(fd)} / {len(uf)}")
claim("@dated 111 (110 records)", "STOP 2021-22: dated / undated", "111 / 226", f"{len(cd_)} / {len(uc)}")
claim("@62 undated (58 records)", "STOP untouched: undated / dated", "62 / 27", f"{len(v_und)} / {len(v_dated)}")
claim("--", "the untouched block total (89 = 62 + 27) and no overlap with the fit / 2021-22 sets (my own partition check)", "89 / 0",
      f"{len(virg_all)} / {len(set(virg_all.eid) & (set(fd.eid) | set(uf.eid) | set(cd_.eid) | set(uc.eid)))}")
tr("@62 undated (58 records)", "STOP check records: virgin undated / virgin dated / 2021-22 undated / 2021-22 dated (printed)", "58 / 26 / 212 / 110",
   F_CHK, 110, r"virgin undated (\d+) of 62.*?virgin dated (\d+) \(.*?2021-22 undated (\d+) \(.*?2021-22 dated (\d+) \(")
tr("@dated 149 + undated 304", "STOP 2020 fit set (printed)", "149 / 304", F_STP, 7, r"dated 2020 (\d+) \+ exact-day undated 2020 (\d+)")
# ENTER windows after 2c
f20, fu = fd[fd.inb], uf[uf.inb]
y2, yu = cd_[cd_.inb], uc[uc.inb]
ok = lambda df: df[df.san == "ok"]
claim("@in-session windows after §2c: 31 dated", "ENTER 2020 windows after §2c: dated / undated non-flicker / undated flickers", "31 / 59 / 34",
      f"{len(ok(f20))} / {int((ok(fu).flick == False).sum())} / {int(ok(fu).flick.sum())}")
tr("@in-session windows after §2c: 31 dated", "ENTER 2020 printed: fit-set windows decided / flickers beside", "31 / 59 / 34",
   F_ENT, 7, r"fit set: (\d+) dated \+ (\d+) undated non-flicker.*?; (\d+) flickers beside")
claim("@20 dated (7 flickers)", "ENTER 2021-22 windows after §2c: dated / of which flickers / undated non-flicker / undated flickers", "20 / 7 / 43 / 19",
      f"{len(ok(y2))} / {int(ok(y2).flick.sum())} / {int((ok(yu).flick == False).sum())} / {int(ok(yu).flick.sum())}")
vb = virg_all[virg_all.inb]
okv = vb[vb.san == "ok"]
claim("@9 non-flicker + 8 flickers", "ENTER untouched windows after §2c: non-flicker / flickers", "9 / 8", f"{int((~okv.flick).sum())} / {int(okv.flick.sum())}")
nf9 = sorted(f"{r.sym} {r.Eb}" for r in okv[~okv.flick].itertuples())
claim("@9 non-flicker + 8 flickers", "the nine non-flicker windows: 2019 count / APT 2020-01-23 / 2023 names", "6 / APT 2020-01-23 / AI, CVNA",
      f"{sum(1 for x in nf9 if x.split()[1].startswith('2019'))} / {[x for x in nf9 if x.startswith('APT')][0]} / "
      f"{', '.join(sorted(x.split()[0] for x in nf9 if x.split()[1].startswith('2023')))}")
claim("@pre-market-flat windows: 2020 41 dated", "pre-market-flat windows, dated: 2020 / 2021-22 (population = printed)", "41 / 41", f"{int(fd.prefl.sum())} / {int(cd_.prefl.sum())}")
claim("@pre-market-flat windows: 2020 41 dated", "pre-market-flat windows, undated non-flicker: POPULATION 2020 / 2021-22 (the printed SCORED counts are 56 / 52)", "56 / 52 (scored)",
      f"{int(sf.prefl.sum())} / {int(sc.prefl.sum())} (population)",
      "the doc's 56 / 52 are the printouts' scored counts, which is what the cell says ('as the printouts'); the populations are larger", kind="NOTE")
tr("@pre-market-flat windows: 2020 41 dated", "printed pre-market-flat 2020 dated", "41", F_ENT, 73, r"dated 2020: (\d+) scorable")
tr("@pre-market-flat windows: 2020 41 dated", "printed pre-market-flat 2020 undated", "56", F_ENT, 85, r"undated 2020: (\d+) scorable")
tr("@pre-market-flat windows: 2020 41 dated", "printed pre-market-flat 2021-22 dated", "41", F_CHK, 81, r"dated 2021-22: (\d+) scorable")
tr("@pre-market-flat windows: 2020 41 dated", "printed pre-market-flat 2021-22 undated", "52", F_CHK, 93, r"undated 2021-22: (\d+) scorable")
tr("@87 scorable deciding (30 + 57", "ENTER 2020 deciding dated scorable (printed)", "30", F_ENT, 35, r"dated: (\d+) scorable")
claim("@87 scorable deciding (30 + 57", "ENTER 2020 deciding total (L23 of the printout: 87)", "87", int(grab(F_ENT, 23, r"(\d+) scorable windows")[0]))
tr("@87 scorable deciding (30 + 57", "ENTER 2020 undated non-flicker scorable (printed)", "57", F_ENT, 47, r"undated non-flicker: (\d+) scorable")
tr("@87 scorable deciding (30 + 57", "ENTER 2020 flickers scorable (printed)", "28", F_ENT, 61, r"flickers 2020.*?: (\d+) scorable")
tr("@40 undated non-flicker + 20 dated scorable", "ENTER 2021-22: DECIDING undated (printed l.18/19)", "40", F_CHK, 19, r"(\d+) scorable windows")
tr("@40 undated non-flicker + 20 dated scorable", "ENTER 2021-22: dated scorable (printed)", "20", F_CHK, 31, r"(\d+) scorable windows")
tr("@40 undated non-flicker + 20 dated scorable", "ENTER 2021-22: flickers scorable (printed)", "19", F_CHK, 43, r"(\d+) scorable windows")
tr("@20 dated (7 flickers)", "ENTER 2021-22: dated windows / of which flickers (printed draw population)", "20 / 7", F_CHK, 18,
   r"population: (\d+) dated incl\. (\d+) flickers")
tr("@9 + 7 scorable (l.55, l.67)", "ENTER untouched non-flicker scorable (printed)", "9", F_CHK, 55, r"(\d+) scorable windows")
tr("@9 + 7 scorable (l.55, l.67)", "ENTER untouched flickers scorable (printed)", "7", F_CHK, 67, r"(\d+) scorable windows")
# EXIT populations
tr("@139 scorable for the hit rate", "EXIT 2020 scorable (printed, hit rate base)", "139", F_EXT, 37, r"E1 \(CHOSEN\) last-leg hit [\d.]+% / half-leg hit [\d.]+% on (\d+)")
claim("@139 scorable for the hit rate", "EXIT 2020 dated population / minus guard (5) exclusions = 139", "149 / 10 / 139",
      f"{len(fd)} / {int(grab(F_EXT, 11, r'(\d+) of 149 trades excluded')[0])} / {int(grab(F_EXT, 12, r'records: (\d+)')[0])}")
tr("@107 armed / 199 scorable", "EXIT 2021-22 dated armed (printed)", "107", F_CHK, 182, r"armed (\d+),")
tr("@107 armed / 199 scorable", "EXIT 2021-22 undated scorable (printed)", "199", F_CHK, 203, r"E1 last-leg hit [\d.]+% / half-leg hit [\d.]+% on (\d+);")
tr("@23 with exits; 18 windows", "EXIT untouched dated: chain trades (printed l.196; timeline 23 minus the one record the floor dropped)", "22", F_CHK, 196, r"trades (\d+)\)")
tr("@23 with exits; 18 windows", "EXIT untouched dated windows <= 20 sessions (printed)", "18", F_CHK, 200, r"on (\d+); E2")
vd_ex = v_dated[v_dated.has_exit]
vw = [r.exit_hi_i - r.exit_lo_i + 1 for r in vd_ex.itertuples()]
claim("@23 with exits; 18 windows", "EXIT untouched dated: with exits / windows <= 20 sessions, FROM THE TIMELINE", "23 / 18",
      f"{len(vd_ex)} / {sum(1 for x in vw if x <= 20)}",
      f"mixed bases in the doc cell: 23 = timeline, pre record-floor; 18 = the printed hit-rate base AFTER the floor dropped one record (dry run l.112: 23 -> 22); "
      f"the timeline's own count of windows <= 20 is {sum(1 for x in vw if x <= 20)} (windows > 20: {sorted(x for x in vw if x > 20)})", kind="NOTE")
d21 = dec_used[dec_used.Eb.str[:4] == "2021"]
claim("@one session wide on 80 of 101", "§2a: 2021 dated with a one-session sell window", "80 of 101", f"{int(((d21.exit_hi_i == d21.exit_lo_i) & d21.has_exit).sum())} of {len(d21)}")
claim("@dated 111; undated 226", "EXIT 2021-22: dated / undated populations", "111 / 226", f"{len(cd_)} / {len(uc)}")
claim("@dated 149", "EXIT 2020: dated / undated populations", "149 / 304", f"{len(fd)} / {len(uf)}")
claim("@27 dated (23 with exits", "EXIT untouched: 27 dated / 62 undated populations", "27 / 62", f"{len(v_dated)} / {len(v_und)}")
tr("@67 of 139 walks stopped first", "§2b: stop pre-empted the 60-minute walk, 2020 dated (printed)", "67 of 139", F_EXT, 43, r"stop_preempt (\d+), trades (\d+)", sep=" of ")
tr("@56 of 107", "§2b: stop pre-empted, 2021-22 dated (printed l.185)", "56 of 107", F_CHK, 185, r"stop_preempt (\d+), trades (\d+)\)", sep=" of ")
tr("@44 of 200 on 2021-22 undated", "§2b: stop pre-empted, 2021-22 undated (printed l.205)", "44 of 200", F_CHK, 205, r"stop_preempt (\d+), trades (\d+)\)", sep=" of ")

# =============================================================================================================== side outputs (tallies of printed columns)
say("\n## 3. Side outputs: per-trade TSVs tallied (columns the frozen stage already wrote and printed)")
ef = pd.read_csv(INTRA + "enter_fit_trades.tsv", sep="\t", dtype=str, keep_default_na=False)
ce = pd.read_csv(INTRA + "check_enter_trades.tsv", sep="\t", dtype=str, keep_default_na=False)
sfit = pd.read_csv(INTRA + "stop_fit_trades.tsv", sep="\t", dtype=str, keep_default_na=False)
sch = pd.read_csv(INTRA + "check_stop_trades.tsv", sep="\t", dtype=str, keep_default_na=False)
xfit = pd.read_csv(INTRA + "exit_fit_trades.tsv", sep="\t", dtype=str, keep_default_na=False)
xchk = pd.read_csv(INTRA + "check_exit_trades.tsv", sep="\t", dtype=str, keep_default_na=False)
for nm, d_ in (("enter_fit", ef), ("check_enter", ce), ("stop_fit", sfit), ("check_stop", sch), ("exit_fit", xfit), ("check_exit", xchk)):
    assert_le_cut([e for e in d_.E if e], nm)
edec = ef[ef.beside == ""]
claim("@(2020: L7 16.1 / L8 34.5", "ENTER 2020 TSV: deciding rows (the doc's n 87)", 87, len(edec))
shares = {k: pct(int((edec[f"{k}_feasible"] == "True").sum()), len(edec)) for k in ("L7", "L8", "L9", "L1", "L2", "L3", "L4", "L5", "L6")}
claim("@(2020: L7 16.1 / L8 34.5", "§9 gate (viii) 2020 ENTER standalone shares re-read from the TSV: L7 / L8 / L9", "16.1% / 34.5% / 34.5%",
      f"{shares['L7']} / {shares['L8']} / {shares['L9']}")
claim("@(2020: L7 16.1 / L8 34.5", "2020 deciding, other levels re-read (info: L1 36.8% on 87 vs the rev fit's 36.0% on 89; L2 18.4; L3 13.8; L4 1.1; L5 1.1; L6 16.1)",
      "-", f"L1 {shares['L1']}; L2 {shares['L2']}; L3 {shares['L3']}; L4 {shares['L4']}; L5 {shares['L5']}; L6 {shares['L6']}", kind="NOTE")
claim("@the union of L7 / L1 / L8 is 55.2%", "'any opening range' union (L7|L1|L8) feasible on the 87, from the union flag", "55.2%",
      pct(int((edec.union_feasible == "True").sum()), len(edec)))
claim("@flickers 28", "ENTER 2020 TSV: flickers rows", 28, int(ef.beside.str.startswith("flickers").sum()))
claim("@pre-market-flat windows: 2020 41 dated", "ENTER 2020 TSV: pre-market-flat dated / undated rows", "41 / 56",
      f"{int((ef.beside == 'pre-market-flat windows, dated 2020').sum())} / {int((ef.beside == 'pre-market-flat windows, undated 2020').sum())}")
cdec = ce[(ce.beside == "") & (ce.dated == "False") & (ce.flicker == "False") & (ce.sane == "ok")]
claim("@2021-22: L7 27.5 / L8 45.0 / L9 45.0 / L1 35.0 on 40", "ENTER 2021-22 TSV: deciding rows (undated non-flicker, sane == ok)", 40, len(cdec))
cs = {k: pct(int((cdec[f"{k}_feasible"] == "True").sum()), len(cdec)) for k in ("L7", "L8", "L9", "L1")}
claim("@2021-22: L7 27.5 / L8 45.0 / L9 45.0 / L1 35.0 on 40", "§9 gate (viii) 2021-22 ENTER standalone shares re-read from the TSV: L7 / L8 / L9 / L1", "27.5% / 45.0% / 45.0% / 35.0%",
      f"{cs['L7']} / {cs['L8']} / {cs['L9']} / {cs['L1']}")
claim("@the union of L7 / L1 / L8 is 55.2%", "2021-22 union (L7|L1|L8) on the 40, from the union flag", "62.5%", pct(int((cdec.union_feasible == "True").sum()), len(cdec)))
cdat = ce[(ce.beside == "") & (ce.dated == "True") & (ce.sane == "ok")]
claim("@20 dated (7 flickers)", "ENTER 2021-22 TSV: dated rows / of which flickers", "20 / 7", f"{len(cdat)} / {int((cdat.flicker == 'True').sum())}")
claim("@20 dated (7 flickers)", "ENTER 2021-22 TSV: undated flicker rows", 19, int((ce.beside == "flickers").sum()))
claim("@9 + 7 scorable", "ENTER untouched TSV: non-flicker / flicker rows", "9 / 7", f"{int(((ce.beside == 'virgin') & (ce.flicker == 'False')).sum())} / {int(((ce.beside == 'virgin') & (ce.flicker == 'True')).sum())}")
# STOP block counts by timeline date window
def blk(df):
    inb = (df.E >= CHK[0]) & (df.E <= CHK[1])
    return collections.Counter(zip(np.where(inb, "2021-22", "untouched"), np.where(df.dated == "True", "dated", "undated")))
bc = blk(sch)
claim("@62 undated (58 records)", "STOP check TSV rows: untouched undated / untouched dated / 2021-22 undated / 2021-22 dated", "58 / 26 / 212 / 110",
      f"{bc[('untouched', 'undated')]} / {bc[('untouched', 'dated')]} / {bc[('2021-22', 'undated')]} / {bc[('2021-22', 'dated')]}")
claim("--", "STOP fit TSV rows (415 records of the 453-trade fit set; printed stop fit l.12)", 415, len(sfit), kind=None)
# EXIT hit rates and stop pre-empt flags
hit = lambda d, k: int((d[f"{k}_hit"] == "True").sum())
claim("@(2020: 40.3 / 40.3 / 39.6 / 39.6 on 139", "EXIT 2020 TSV: E1 / E2 / E3 / E4 last-leg hit on the 139 rows", "40.3% / 40.3% / 39.6% / 39.6% on 139",
      " / ".join(pct(hit(xfit, k), len(xfit)) for k in ("E1", "E2", "E3", "E4")) + f" on {len(xfit)}")
xa = xchk[xchk.abstain == ""]
claim("@(2020: 40.3 / 40.3 / 39.6 / 39.6 on 139", "EXIT 2021-22 dated TSV: E1 / E2 / E3 / E4 last-leg hit on the 107 armed rows", "38.3% / 36.4% / 35.5% / 35.5% on 107",
      " / ".join(pct(hit(xa, k), len(xa)) for k in ("E1", "E2", "E3", "E4")) + f" on {len(xa)}")
claim("@67 of 139 walks stopped first", "EXIT TSV: E1_stop_preempt True, 2020 (139 rows)", "67 of 139", f"{int((xfit.E1_stop_preempt == 'True').sum())} of {len(xfit)}")
claim("@(56 of 107)", "EXIT TSV: E1_stop_preempt True, 2021-22 dated (107 armed)", "56 of 107", f"{int((xa.E1_stop_preempt == 'True').sum())} of {len(xa)}")
claim("@printed 40.3 / 39.6 / 40.3 (2020)", "§7 mapping M-1 / M-2 / M-7 = E1 / E4 / E2: 2020 printed hits", "40.3 / 39.6 / 40.3",
      f"{pct(hit(xfit, 'E1'), len(xfit))[:-1]} / {pct(hit(xfit, 'E4'), len(xfit))[:-1]} / {pct(hit(xfit, 'E2'), len(xfit))[:-1]}")
claim("@printed 40.3 / 39.6 / 40.3 (2020)", "§7 mapping M-1 / M-2 / M-7 = E1 / E4 / E2: 2021-22 printed hits", "38.3 / 35.5 / 36.4",
      f"{pct(hit(xa, 'E1'), len(xa))[:-1]} / {pct(hit(xa, 'E4'), len(xa))[:-1]} / {pct(hit(xa, 'E2'), len(xa))[:-1]}")
tr("@(2020: 40.3 / 40.3 / 39.6 / 39.6 on 139", "§9 (viii-a) printed 2020 E1 / E2 / E3 / E4", "40.3 / 40.3 / 39.6 / 39.6", F_EXT, 37,
   r"E1 \(CHOSEN\) last-leg hit ([\d.]+)%.*?E2 last-leg hit ([\d.]+)%.*?E3 last-leg hit ([\d.]+)%.*?E4 last-leg hit ([\d.]+)%")
tr("@(2020: 40.3 / 40.3 / 39.6 / 39.6 on 139", "§9 (viii-a) printed 2021-22 E1 / E2 / E3 / E4", "38.3 / 36.4 / 35.5 / 35.5", F_CHK, 183,
   r"E1 \(CHOSEN\) last-leg hit ([\d.]+)%.*?E2 last-leg hit ([\d.]+)%.*?E3 last-leg hit ([\d.]+)%.*?E4 last-leg hit ([\d.]+)%")
tr("@(2020: 40.3 / 40.3 / 39.6 / 39.6 on 139", "§9 (viii-a) printed 2021-22 base", "107", F_CHK, 183, r"E1 \(CHOSEN\).*? on (\d+); E2")

# L4 evidence behind "never feasible ... by construction" (E-7 / §7)
l4 = edec[edec.L4_feasible == "True"]
l4c = ce[(ce.L4_feasible == "True") & (ce.beside != "")]
claim("@never feasible on an in-session window by construction", "E-7 L4 'never feasible on an in-session window by construction': in-session windows where L4 IS feasible (2020 deciding 87)",
      "none", f"{len(l4)} ({'; '.join(f'{r.sym} {r.E} flat {r.flat_clock} first {r.first_clock} cross at minute {r.L4_cross}' for r in l4.itertuples())})",
      "the same row cites '1.1% (rev l.15)' = 1 feasible window; the cell's 'never' contradicts its own citation")
claim("@never feasible on an in-session window by construction", "L4 feasible in the 2021-22 / untouched in-session windows (flickers beside)", "none",
      "; ".join(f"{r.sym} {r.E} ({r.beside or 'deciding'}) flat {r.flat_clock} first {r.first_clock} cross at minute {r.L4_cross}" for r in l4c.itertuples()) or "none",
      "printout: 2021-22 flickers L4 feasible 1 = 5.3% (check l.50); further evidence for the row above", kind="NOTE")
tr("@never feasible on an in-session window by construction", "E-7 L4 2020 number cited (rev l.15)", "1.1%", F_RENT, 15, r"L4: feasible \d+ = ([\d.]+%)")


rf = pd.read_csv(REVO + "enter_fit_trades.tsv", sep="\t", dtype=str, keep_default_na=False)
assert_le_cut([e for e in rf.E if e], "reverse enter_fit_trades")
rsh = {k: pct(int((rf[f"{k}_feasible"] == "True").sum()), len(rf)) for k in ("L1", "L2", "L3", "L4")}
for anc_, lv_, dv_ in (("@| E-1 |", "L1", "36.0%"), ("@| E-3 |", "L2", "18.0%"), ("@| E-5 |", "L3", "13.5%"), ("@| E-7 |", "L4", "1.1%")):
    claim(anc_, f"reverse ENTER fit TSV ({len(rf)} rows): {lv_} feasible share", dv_, rsh[lv_], f"{int((rf[f'{lv_}_feasible'] == 'True').sum())} of {len(rf)}")
r4 = rf[rf.L4_feasible == "True"]
claim("@never feasible on an in-session window by construction", "reverse ENTER fit TSV: the one L4-feasible window (same trade as the intraday fit's?)", "none",
      "; ".join(f"{r.sym} {r.E} flat {r.flat_clock} first {r.first_clock} cross minute {r.L4_cross}" for r in r4.itertuples()),
      "same trade as the intraday fit's L4-feasible window" if set(r4.eid) == set(l4.eid) else "different trade", kind="NOTE")
claim("@(the registered 'his' account's booking point, R8)", "§11 item 5 cites R8 for 'the registered his account's booking point' (close of exit_hi, no stop): R8's text in the reverse registration",
      "booking point stated", "R8 says only 'his under no stop, the registered ones beside'; the close-of-exit_hi booking point is stated at the reverse registration's §8c (l.405) and F10 (l.662)",
      "a cite pointing at the neighbouring rule, content correct", kind="NOTE")
claim("@three closes that day", "gate (ix): 'its first 60-minute close below is 2020-07-10' - what the cited printout line establishes", "first close below since the fill = 07-10",
      "the line gives 3 closes ON 07-10 (first at 13:59) and the touch on 07-13; it does not say no earlier close existed since the 06-29 fill",
      "the pinned bucket (M-1 MISS-EARLY) holds either way: any earlier first firing is also before exit_lo on a certainly-held session", kind="NOTE")


# ---- arithmetic the template/table states ------------------------------------------------------------------------------------------------
pm_d, pm_u = int(grab(F_ENT, 73, r"dated 2020: (\d+) scorable")[0]), int(grab(F_ENT, 85, r"undated 2020: (\d+) scorable")[0])
claim("@composition: in-session 87", "§9 template header: 'pre-market-flat 97 (beside)' = printed 41 dated + 56 undated (enter fit l.73 + l.85)", "97", f"{pm_d + pm_u}")
claim("@composition: in-session 87", "§9 template header: 'in-session 87' = printed deciding windows (enter fit l.23)", "87", grab(F_ENT, 23, r"(\d+) scorable windows")[0])
claim("@±33 points on 9", "§2 '±33 points on 9': the 95% half-width of a share on n = 9 at its widest (p = 0.5), points", "33", f"{196 * (0.25 / 9) ** 0.5:.0f}",
      "the printed untouched intervals run +-21 to +-37 (check l.55-66); 33 is the p = 0.5 worst case")
ms = {k: re.search(rf"{k} ([\d.]+) ADR20", L(F_STUDY, 97) + " " + L(F_STUDY, 98)) for k in ("extension", "big up day")}
claim("@**M-10's thresholds (extension 2.0 ADR20", "§11 item 9 / §3c M-10 thresholds vs the exits study's fixed markers (study l.97): extension / big up day, in ADR20", "2.0 / 1.5",
      f"{ms['extension'].group(1) if ms['extension'] else '?'} / {ms['big up day'].group(1) if ms['big up day'] else '?'}")

# =============================================================================================================== §3 library numbers
say("\n## 4. §3 libraries: the 2020 ordering numbers against the cited printout lines, and the order rule against those numbers")
ordE = []
for anc, lab, doc, path, n, pat in (
        ("@| E-1 |", "E-1 L1", "36.0% on 89", F_RENT, 12, r"L1: feasible \d+ = ([\d.]+%)"),
        ("@| E-2 |", "E-2 L8", "34.5% on 87", F_ENT, 25, r"L8 \(CHOSEN\): feasible \d+ = ([\d.]+%)"),
        ("@| E-3 |", "E-3 L2", "18.0%", F_RENT, 13, r"L2: feasible \d+ = ([\d.]+%)"),
        ("@| E-4 |", "E-4 L7", "16.1%", F_ENT, 24, r"L7 \(new\): feasible \d+ = ([\d.]+%)"),
        ("@| E-5 |", "E-5 L3", "13.5%", F_RENT, 14, r"L3: feasible \d+ = ([\d.]+%)"),
        ("@| E-6 |", "E-6 L9", "34.5%", F_ENT, 26, r"L9 \(new\): feasible \d+ = ([\d.]+%)"),
        ("@| E-7 |", "E-7 L4", "1.1%", F_RENT, 15, r"L4: feasible \d+ = ([\d.]+%)")):
    tr(anc, lab, doc.split(" ")[0], path, n, pat)
    ordE.append(float(grab(path, n, pat)[0][:-1]))
tr("@| E-1 |", "E-1 L1 n (rev fit scored)", "89", F_RENT, 11, r"(\d+) scorable trades")
tr("@| E-2 |", "E-2 L8 n (intra fit scored)", "87", F_ENT, 23, r"(\d+) scorable windows")
claim("@L5 the prior close (an EP gap level", "L5 'an EP gap level, 1.1% / 5.0%': 2020 / 2021-22 deciding", "1.1% / 5.0%",
      f"{grab(F_ENT, 31, r'L5 .*?feasible \d+ = ([\d.]+%)')[0]} / {grab(F_CHK, 27, r'L5 .*?feasible \d+ = ([\d.]+%)')[0]}")
t1, t2 = ordE[:5], [ordE[5], ordE[6]]
claim("@**The order rule, stated once:**", "ENTER order: tier-1 rows E-1..E-5 non-increasing in the printed 2020 number; tier-2 E-6, E-7 non-increasing", "monotone",
      "monotone" if (t1 == sorted(t1, reverse=True) and t2 == sorted(t2, reverse=True)) else f"NOT monotone: {ordE}", f"numbers {ordE}")
wid = {}
for k, n in (("S1", 40), ("S3", 43), ("S9", 46), ("S10", 49)):
    wid[k] = float(grab(F_STP, n, r"\|\s+([\d.]+)%\s+\|")[0])
tr("@| S-2 |", "S-2 S10 median width (cited l.49)", "2.8%", F_STP, 49, r"\|\s+([\d.]+%)\s+\|")
tr("@| S-5 |", "S-5 S9 median width (cited l.46)", "2.9%", F_STP, 46, r"\|\s+([\d.]+%)\s+\|")
tr("@| S-8 |", "S-8 S1-H median width: doc cites l.40", "3.2%", F_STP, 40, r"\|\s+([\d.]+%)\s+\|")
s1h = grab(F_STP, 42, r"^\s+(S1-H)\s+\|\s+([\d.]+%)\s+\|")
claim("@| S-8 |", "S-8 is the S1-H cell but l.40 is the S1-T row; the S1-H row is l.42 (same width)", "l.40", f"l.42 ({s1h[0]}, {s1h[1]})",
      "number holds (all three S1 variants share the width); the line cite names the S1-T row", kind="NOTE")
tr("@| S-10 |", "S-10 S3 median width (cited l.43)", "5.6%", F_STP, 43, r"\|\s+([\d.]+%)\s+\|")
claim("@Order within tier 2 = tightest median width first", "STOP tier-2 order S10, S9, S1, S3 ascending by printed width", "ascending",
      "ascending" if (wid["S10"] <= wid["S9"] <= wid["S1"] <= wid["S3"]) else f"NOT ascending {wid}", f"widths {wid}")
claim("@one full ADR20 against medians under 6%", "S-13 'last by definition ... medians under 6%': the largest library median width (S3)", "< 6%", f"{max(wid.values())}%",
      kind="OK" if max(wid.values()) < 6 else "MISMATCH")
claim("@S1 was held through on 44%", "§7 'S1 was held through on 44% of the fit trades where price crossed it' (S1-T H_cond, stop fit l.40)", "44%", f"{H20['S1-T']:.0f}%")
# EXIT numbers
tr("@| M-1 |", "M-1 E1 last-leg hit on 139 (l.37)", "40.3%", F_EXT, 37, r"E1 \(CHOSEN\) last-leg hit ([\d.]+%)")
tr("@| M-2 |", "M-2 E4 last-leg hit (l.37; E3 collapses onto it: 39.6% both)", "39.6%", F_EXT, 37, r"E4 last-leg hit ([\d.]+%)")
tr("@| M-2 |", "M-2: E3 = E4 on the 2020 panel (E3)", "39.6%", F_EXT, 37, r"E3 last-leg hit ([\d.]+%)")
m2_ = grab(F_CHK, 183, r"E3 last-leg hit ([\d.]+%).*?E4 last-leg hit ([\d.]+%)")
claim("@| M-2 |", "M-2: E3 = E4 also on the 2021-22 panel (my extra check; the cell states 39.6% both for 2020)", "equal", "equal" if m2_[0] == m2_[1] else f"differ {m2_}", f"{m2_}", kind="NOTE")
tr("@| M-7 |", "M-7 E2 last-leg hit (l.37)", "40.3%", F_EXT, 37, r"E2 last-leg hit ([\d.]+%)")
tr("@| M-8 |", "M-8 first red close on 139 (l.40)", "31.7%", F_EXT, 40, r"first red close ([\d.]+%)")
tr("@| M-9 |", "M-9 close of session 3 on 139 (l.40)", "20.1%", F_EXT, 40, r"close of session 3 ([\d.]+%)")
m8_21 = grab(F_CHK, 184, r"first red close ([\d.]+%)")[0]
m9_21 = grab(F_CHK, 184, r"close of session 3 ([\d.]+%)")[0]
claim("@M-8 (the first red close 31.7%", "§7 2021-22 dated M-8 first red close / M-9 close of session 3 (check l.184)", "25.2% / 14.0%", f"{m8_21} / {m9_21}")
claim("@M-8 (the first red close 31.7%", "§7 2020 dated M-8 / M-9 (exit fit l.40)", "31.7% / 20.1%",
      f"{grab(F_EXT, 40, r'first red close ([\d.]+%)')[0]} / {grab(F_EXT, 40, r'close of session 3 ([\d.]+%)')[0]}")
tr("@a known 50.5% there", "the previous 3-rule daily list on dated 2021-22 (check l.184)", "50.5%", F_CHK, 184, r"daily list \(IN-SAMPLE there\) ([\d.]+%)")
wu_ = grab(F_EXT, 33, r"under (\d+) \+ (\d+) = (\d+) bars")
claim("@the 65-bar warm-up floor", "M-1 warm-up floor in bars (exit fit l.33: 20 seed + 45 post-seed)", "65", f"{wu_[2]}", f"{wu_[0]} + {wu_[1]}", kind=None if int(wu_[0]) + int(wu_[1]) == int(wu_[2]) else "MISMATCH")

say("\n## 5. §3c / §7: the exits-study counts, transcribed from §3 and checked by arithmetic")
ES = {}
ES["l60"] = grab(F_STUDY, 60, r"\*\*(\d+) of (\d+) exits at or below .*?and (\d+) in")
ES["l62"] = grab(F_STUDY, 62, r"before\*\* the first close below the 10-day in (\d+) of (\d+), within it (\d+), after (\d+)")
ES["l63"] = grab(F_STUDY, 63, r"before (\d+), within (\d+), after (\d+)")
ES["l64"] = grab(F_STUDY, 64, r"on (\d+) of 117 \(before (\d+)\)")
ES["l65"] = grab(F_STUDY, 65, r"before his window on (\d+), within (\d+), after (\d+), never (\d+)")
ES["l68"] = grab(F_STUDY, 68, r"on (\d+) / (\d+) of 117")
ES["l69"] = grab(F_STUDY, 69, r"\*\*(\d+) of the 21 left|(\d+) of 117 stalled")
ES["l69b"] = grab(F_STUDY, 69, r"(\d+) of 117 stalled; \*\*(\d+) of the 21")
assert all(v is not None for v in ES.values()), ES
n117 = int(ES["l60"][1])
claim("@the exits study's 2020 description", "exits study §3 (l.54): 117 filled dated exits", "117", grab(F_STUDY, 54, r"\((\d+) filled")[0])
claim("@the exits study's 2020 description", "STOP 2020 row: filled exits below the fill at exit_hi = 29 + 20 (l.60)", "49 of 117 (29 + 20)",
      f"{int(ES['l60'][0]) + int(ES['l60'][2])} of {n117} ({ES['l60'][0]} + {ES['l60'][2]})")
b28 = grab(F_STUDY, 247, r"; (\d+) of 88 exits at")[0]
b24 = grab(F_STUDY, 248, r"(\d+) in \(.1, 0\)")[0]
claim("@exits study 2021-22: 52 of 88", "STOP 2021-22 row: filled dated below the fill at exit_hi = 28 + 24 of 88 (study l.247-248)", "52 of 88 (28 + 24)",
      f"{int(b28) + int(b24)} of 88 ({b28} + {b24})")
claim("@| M-3 |", "M-3 within his window = 39 of 117 = 33.3%", "39 of 117 = 33.3%", f"{ES['l62'][2]} of {ES['l62'][1]} = {pct(int(ES['l62'][2]), int(ES['l62'][1]))}")
claim("@| M-4 |", "M-4 within his window = 28 of 117 = 23.9%", "28 of 117 = 23.9%", f"{ES['l63'][1]} of {n117} = {pct(int(ES['l63'][1]), n117)}")
claim("@| M-5 |", "M-5 16 of 21 stallers left by session 3 -> <= 13.7% (of 117)", "16 of 21 -> 13.7%", f"{ES['l69b'][1]} of {ES['l69b'][0]} -> {pct(int(ES['l69b'][1]), n117)}")
claim("@| M-6 |", "M-6 +2R within his window = 12 of 117 = 10.3%", "12 of 117 = 10.3%", f"{ES['l65'][1]} of {n117} = {pct(int(ES['l65'][1]), n117)}")
claim("@| M-10 |", "M-10 extension 13 / big up 6 of 117 -> ordered on 11.1%", "13 / 6 of 117 -> 11.1%",
      f"{ES['l68'][1]} / {ES['l68'][0]} of {n117} -> {pct(int(ES['l68'][1]), n117)}", "the study's row is 'a big up day / an extension ... 6 / 13', so extension = 13, big up = 6")
tier1 = [40.3, 39.6, 33.3, 23.9, 13.7, 10.3]
tier2 = [40.3, 31.7, 20.1, 11.1]
claim("@**The order rule, stated once:**", "EXIT order: tier-1 M-1..M-6 non-increasing in the printed number; tier-2 M-7..M-10 non-increasing", "monotone",
      "monotone" if (tier1 == sorted(tier1, reverse=True) and tier2 == sorted(tier2, reverse=True)) else "NOT monotone", f"tier1 {tier1}; tier2 {tier2}")
ib = lambda w, b: (int(w), int(b))
w3, a3 = int(ES["l62"][2]), int(ES["l62"][3])
w4, a4 = int(ES["l63"][1]), int(ES["l63"][2])
red_tot, red_before = int(ES["l64"][0]), int(ES["l64"][1])
b2, w2 = int(ES["l65"][0]), int(ES["l65"][1])
red_within = red_tot - red_before
prec = (100 * w3 / (w3 + a3), 100 * w4 / (w4 + a4), 100 * red_within / red_tot, 100 * w2 / (w2 + b2))
claim("@Precision (floors): M-3", "§7 precision floors: M-3 (39 within vs 21 fired-while-held) / M-4 / M-8 / M-6", "~65% / ~74% / ~40% / ~17%",
      f"{prec[0]:.1f}% ({w3}/({w3}+{a3})) / {prec[1]:.1f}% ({w4}/({w4}+{a4})) / {prec[2]:.1f}% ({red_within}/{red_tot}) / {prec[3]:.1f}% ({w2}/({w2}+{b2}))",
      "the doc's 40% for M-8 is 41.5% (within 2 points of a tilde figure)",
      kind="OK" if (abs(prec[0] - 65) < 1 and abs(prec[1] - 74) < 1 and abs(prec[2] - 40) < 2 and abs(prec[3] - 17) < 1) else "MISMATCH")
claim("@Precision (floors): M-3", "§7: '39 within vs 21 fired-while-held' - the study's counts for the 10-day (l.62)", "39 / 21", f"{w3} / {a3}")
# losers share vs the §7 guess
claim("@losers are 40-55% of exits per block", "§7 guess 'losers are 40-55% of exits per block' vs the doc's own §2 figures (49 of 117 / 52 of 88)", "40-55%",
      f"{pct(49, 117)} (2020) / {pct(52, 88)} (2021-22)",
      "the 59% is the exits study's FILLED dated subset (88); the guess is per block (111 dated + 226 undated, whose loss share §2 says is read at the run) - a guess about a larger "
      "population is not contradicted by a number on a subset; NOTE, not a mismatch", kind="NOTE")

say("\n## 6. §5 / §7 / §9: controls, constants, gate numbers")
tr("@21.0% on", "§5: random-price control standalone floor 2020 (enter fit l.33)", "21.0%", F_ENT, 33, r"feasible ([\d.]+%)")
tr("@21.0% on", "§5: random-price control standalone floor 2021-22 (check l.29)", "30.0%", F_CHK, 29, r"feasible ([\d.]+%)")
tr("@31.7% / 85.9% on", "§5/§9 gate (vii): the control re-read on the previous 41 undated records (check l.17)", "31.7% / 85.9% / 41", F_CHK, 17, r"feasible ([\d.]+%), hit-or-ballpark ([\d.]+%) \(known .*? on (\d+)\)", sep=" / ")
l8_ = grab(F_CHK, 21, r"L8 \(CHOSEN\): feasible \d+ = ([\d.]+%).*?shifted-window control feasible ([\d.]+%)")
claim("@read FAILED at +15 over 31.7%", "§6: the level the intraday read FAILED = L8 on the 40 (check l.21): feasible / shifted control", "(not stated in the doc)", " / ".join(l8_), kind="NOTE")
claim("@read FAILED at +15 over 31.7%", "§6 'the level the intraday read FAILED at +15 over 31.7%': the margin over each control the check actually printed",
      "+15 over 31.7%", f"+{45.0 - 30.0:.1f} over 30.0% (the check's own control on the 40, l.29); +{45.0 - 31.7:.1f} over 31.7% (the gate-vii known answer on the previous 41, l.17)",
      "45.0 - 31.7 = 13.3, not 15; the +15 margin is met only against 30.0% (by 0.0004 per the intraday RESULT) - the read FAILED on the absolute >= 50% bar",
      kind="MISMATCH")
txt_mod = open(F_MOD, encoding="utf8").read()
rev_txt = open(os.path.join(P_REV, "01_rev_frozen_e908253f7405.py"), encoding="utf8").read()
txt_mod = open(F_MOD, encoding="utf8").read()
c_seed = re.search(r"^SEED = (\d+)", txt_mod, re.M).group(1)
c_rl = re.search(r"^RANDOM_LEVELS = (\d+)", rev_txt, re.M).group(1)
c_sd = re.search(r"^SHIFT_DRAWS = (\d+)", txt_mod, re.M).group(1)
c_sk = re.search(r'^SHIFT_KEY = "([^"]+)"', txt_mod, re.M).group(1)
c_rk = re.search(r'^RANDOM_KEY = "([^"]+)"', rev_txt, re.M).group(1)
claim("@seed 702", "constants in the frozen modules: SEED / RANDOM_LEVELS (rev) / SHIFT_DRAWS / SHIFT_KEY / RANDOM_KEY", "702 / 200 / 200 / intra|bracket|{eid}|{level}|{draw} / rev|minute",
      f"{c_seed} / {c_rl} / {c_sd} / {c_sk} / {c_rk}")
claim("@STOP_VARIANT_TIE", "frozen module STOP_VARIANT_TIE order (the doc: T, C, H)", "T, C, H",
      ", ".join(k for k, _v in sorted(eval(re.search(r"^STOP_VARIANT_TIE = (\{[^}]*\})", txt_mod, re.M).group(1)).items(), key=lambda kv: kv[1])))
claim("@the 60-minute 20-EMA close", "frozen module EMA_N (the 20-EMA)", 20, int(re.search(r"^EMA_N, EMA_ALPHA = (\d+),", txt_mod, re.M).group(1)))
names = ["load_core", "intra_sets", "enter_sets", "windows_of", "clock_sane", "recs_for", "make_irec", "IRec", "MinuteStore", "BarGuard", "h60_bars", "bar_sequence",
         "ema_series", "armed_index", "ema_is_thin", "intraday_levels", "enter_score_trade", "shifted_control", "stop_levels_intra", "held_through_intra", "prior_low",
         "smas_for", "fnum", "IdCache", "exit_walk_intra", "score_new_fixed", "score_l9"]
miss = [n for n in names if not re.search(rf"^(def|class) {n}\b", txt_mod, re.M)]
claim("@Reused as they are", "§9 'reused as they are' names present as def/class in the frozen intraday module (27 names)", "none missing", f"{len(miss)} missing: {miss}" if miss else "none missing")
miss_rev = [n for n in ("score_level", "random_levels", "level_at") if not re.search(rf"^def {n}\b", rev_txt, re.M)]
claim("@Reused as they are", "§9 rev.random_levels / rev.level_at / score_level present in the frozen reverse module", "none missing", f"missing: {miss_rev}" if miss_rev else "none missing")
claim("@sha256 `ac598fc58aae", "§9: frozen intraday module sha256 prefix", "ac598fc58aae", sha(F_MOD)[:12])
fz = "<!-- FREEZE -->"
claim("@doc_body` (`6c3741e48788", "§9: the intraday registration's doc_body (sha256 of the bytes above the freeze marker) prefix", "6c3741e48788",
      hashlib.sha256(open(F_INTRA_DOC, encoding="utf8").read().split(fz, 1)[0].encode("utf-8")).hexdigest()[:12])
this = open(DOC, encoding="utf8").read()
claim("@the literal appears once", "this doc: the freeze marker appears as an exact line once (and in prose as a quoted literal count)", "1 / 1",
      f"{sum(1 for ln in DL if ln.strip() == fz)} / {this.count(fz)}", "exact-marker lines / occurrences of the literal anywhere in the file")

say("\n## 7. FSLY 693 (gate ix): timeline, calendar, printout")
r693 = ni[ni.eid == "693"].iloc[0]
claim("@FSLY eid 693", "eid 693: symbol / setup / buy day / exit window", "FSLY / undated / 2020-06-29 / 07-13..07-14", f"{r693.sym} / {r693.setup} / {r693.Eb} / {r693.exit_lo[5:]}..{r693.exit_hi[5:]}")
sess = [d for d in CAL if "2020-06-29" <= d <= "2020-07-14"]
claim("@a 10-session hold", "sessions from the buy day 06-29 to exit_lo 07-13 inclusive (the doc: a 10-session hold)", 10, CI["2020-07-13"] - CI["2020-06-29"] + 1, f"calendar: {sess}")
wd = lambda d: datetime.date.fromisoformat(d).strftime("%a")
claim("@07-11 and 07-12 are a weekend", "07-10 / 07-11 / 07-12 / 07-13 weekdays", "Fri / Sat / Sun / Mon", " / ".join(wd(f"2020-07-{x}") for x in ("10", "11", "12", "13")))
claim("@one session before exit_lo 07-13", "07-10 is one session before 07-13 and two before 07-14 on the calendar (§1 e: 'one to two sessions')", "1 / 2",
      f"{CI['2020-07-13'] - CI['2020-07-10']} / {CI['2020-07-14'] - CI['2020-07-10']}")
claim("--", "07-03 is not a session (the independence-day observance), so the hold counts 9 sessions to 07-10", "absent", "absent" if "2020-07-03" not in CI else "present")
tr("@three closes that day", "FSLY gate (vi): 60-minute closes below the 20-EMA on 07-10 / first at / touch of the prior low on 07-13", "3 / 13:59 / True", F_STP, 35,
   r"2020-07-10: (\d+) \(first at (\d+:\d+)\); a touch of the prior day's low on 2020-07-13: (\w+)")
vs = pd.read_csv(QS + "video_status.tsv", sep="\t", dtype=str, keep_default_na=False).set_index("id")
claim("@`cMkRsqvlVHM` 2020-07-14", "caption videos' upload dates: cMkRsqvlVHM / YwMoUTd4naQ", "2020-07-14 / 2020-07-13",
      f"{vs.loc['cMkRsqvlVHM', 'upload_date'][:4]}-{vs.loc['cMkRsqvlVHM', 'upload_date'][4:6]}-{vs.loc['cMkRsqvlVHM', 'upload_date'][6:]} / "
      f"{vs.loc['YwMoUTd4naQ', 'upload_date'][:4]}-{vs.loc['YwMoUTd4naQ', 'upload_date'][4:6]}-{vs.loc['YwMoUTd4naQ', 'upload_date'][6:]}")


def cues(fn):
    out = []
    for blk_ in open(fn, encoding="utf8").read().split("\n\n"):
        ls = blk_.strip().split("\n")
        for i, l_ in enumerate(ls):
            m = re.match(r"(\d\d:\d\d:\d\d)\.\d+ --> ", l_)
            if m:
                out.append((m.group(1), " ".join(re.sub(r"<[^>]+>", "", x) for x in ls[i + 1:])))
    return out


cm = cues(QS + "subs/cMkRsqvlVHM.en-orig.vtt")
yw = cues(QS + "subs/YwMoUTd4naQ.en-orig.vtt")
t_a = [t for t, b in cm if "I sold half of it 2 days ago when it broke below the 20" in b]
t_b = [t for t, b in cm if "took out the previous day's lows" in b]
t_c = [t for t, b in yw if "did sell half on friday when it took out" in b]
claim("@~00:52:28", "caption cMkRsqvlVHM: 'sold half ... broke below the 20' cue / 'took out the previous day's lows' cue", "00:52:28", t_a[0] if t_a else "NOT FOUND", f"the 'previous day's lows' half-sentence is the cue at {t_b[0] if t_b else 'NOT FOUND'} (14 s later; the doc's '~' covers the pair)")
claim("@~00:04:44", "caption YwMoUTd4naQ: 'did sell half on friday when it took out' cue", "00:04:44", t_c[0] if t_c else "NOT FOUND")
tn = open(QS + "subs/tnHw5CKxcH4.en-orig.vtt", encoding="utf8").read()
claim("@`tnHw5CKxcH4`", "caption tnHw5CKxcH4 names a '60-minute range' for an add (E-6)", "present", "present" if re.search(r"takes out the 60-minute\s+.*?range that's my ad", re.sub(r"<[^>]+>", "", tn).replace("\n", " ")) or "60-minute range that's my ad" in re.sub(r"<[^>]+>", "", tn).replace("\n", " ") else "NOT FOUND")

say("\n## 8. His words: quotes and line cites in operator_shared_notes.md")
NT = lines_of(F_NOTES)


def span(a, b):
    return re.sub(r"\s+", " ", " ".join(NT[a - 1:b]).replace("*", "").replace(">", "")).replace("“", '"').replace("”", '"')


def inq(label, a, b, text, anchor=None):
    s = span(a, b)
    found = text in s
    where = ""
    if not found:
        for aa, bb in ((a, b + 1), (a, b + 2), (a - 1, b), (a - 2, b)):
            if text in span(aa, bb):
                where = f" (found in l.{aa}-{bb})"
                break
    claim(anchor or "--", f"quote at notes l.{a}-{b}: {label}", "inside the cited lines", "inside the cited lines" if found else f"NOT inside{where}")


inq("entry", 1941, 1942, "Enter on the opening range highs. The opening range highs can be the highs of the first 1-minute candle, the 5-minute candle or the 60-minute candle.", "@Enter on the opening range highs.")
inq("'buy as the daily chart starts to break out'", 1942, 1942, "simply buy as the daily chart starts to break out", "@Or *\"simply buy as the daily chart")
claim("@Or *\"simply buy as the daily chart", "notes l.1942: is 'simply buy as the daily chart starts to break out' a quoted/italic phrase in the notes?", "quoted (as the doc renders it)",
      "unquoted plain text in the notes (the italic quote ends at 'candle.\"'; the sentence after it is the notes' own paraphrase)" if '*"Enter on' in NT[1940] and 'Or simply buy' in NT[1941] and '*' not in NT[1941].split('Or simply')[1] else "quoted",
      "the doc says 'the article's words via the notes' - it presents a paraphrase line in quote marks", kind="NOTE")
inq("60-minute first candle / whatever timeframe / don't even have to use any intraday chart", 2090, 2091,
    "(on the 60-minute timeframe the first candle is always only 30 minutes, 9.30-10 AM). You can use whatever timeframe or a combination of them. You don't even have to use any intraday chart, just look at the daily chart and enter when the stock is starting to break out.",
    "@l.2090-2091:")
inq("anticipating the breakout", 2093, 2094, "I don't find it as effective", "@anticipating the breakout")
inq("stop", 1943, 1943, "Stop is always lows of the day and stop should not be wider than the ATR or ADR of the stock.", "@Stop is always lows of the day")
inq("exit part 1", 1946, 1946, "sell 1/3 to 1/2 of the position after 3-5 days, and then move the stop to break even", "@sell 1/3 to 1/2 of the position")
inq("exit part 2", 1946, 1947, "trailed with the 10- or the 20-day moving average", "@sell 1/3 to 1/2 of the position")
inq("exit part 3", 1947, 1947, "You wait for the first CLOSE below the 10-day", "@sell 1/3 to 1/2 of the position")
inq("2R", 2046, 2047, "sell 1/3 at 2R then move to break even stop then trail rest at break of 10 or 20d", "@sell 1/3 at 2R then move")
inq("10d/20d", 2046, 2047, "10d for faster stocks and 20d for slower stocks, also depend how far the are from 10/20", "@sell 1/3 at 2R then move")
inq("combo", 2060, 2060, "The day thing is also correct, it may be a combo and depends", "@The day thing is also correct")
inq("stallers 1", 2066, 2067, "if breakouts have no follow through in next few days then it may be better to get out", "@l.2066-2071")
inq("stallers 2", 2070, 2070, "Cut stallers is important", "@l.2066-2071")
inq("his yes", 2078, 2079, "his \"yes\"", "@(l.2078-2079)")
inq("his 10-25 note", 2596, 2596, "What seems to be the case is there's no 100% had rule, there's rules and discretion, so best to to categorize them e.g. 20% rule X, 34% rule Y, etc. To see if we get the right coverage when summed together.", "@l.2596")
inq("method line", 2598, 2598, "list the candidate rules from his words", "@(l.2598)")
inq("method line", 2598, 2598, "tag each trade with the rule that explains it, report each rule's share, and judge the set by its combined coverage", "@(l.2598)")


say("\n## 6b. Further transcription: the other beside lines the §7 'known already' bullet quotes, cites that bound a block, gate bars, record floors")
tr("@on the 20 dated 2021-22 windows", "§7: 20 dated 2021-22 windows: union / random-price / shifted (check l.42)", "65.0% / 32.7% / 15.2%", F_CHK, 42,
   r"feasible ([\d.]+%).*?\(([\d.]+%): a price.*?shifted-window control ([\d.]+%)")
tr("@untouched 9, 33.3% vs 3.3%", "§7: untouched 9: union / random-price / shifted (check l.66)", "33.3% / 3.3% / 4.0%", F_CHK, 66,
   r"feasible ([\d.]+%).*?\(([\d.]+%): a price.*?shifted-window control ([\d.]+%)")
tr("@flickers 2021-22 52.6%", "§7: 2021-22 flickers: union / random-price (check l.54)", "52.6% / 22.5%", F_CHK, 54, r"feasible ([\d.]+%).*?\(([\d.]+%): a price")
claim("@the shifted-window union 6.5% / 6.7%", "§7: shifted-window union 2020 / 2021-22 (the two 'any opening range' lines)", "6.5% / 6.7%",
      f"{grab(F_ENT, 34, r'shifted-window control ([\d.]+%)')[0]} / {grab(F_CHK, 30, r'shifted-window control ([\d.]+%)')[0]}")
sh = []
for path, rng in ((F_ENT, range(24, 30)), (F_CHK, range(20, 25))):
    for n in rng:
        m_ = re.search(r"shifted-window control feasible ([\d.]+)%", L(path, n))
        sh.append(float(m_.group(1)))
claim("@against the 1-7% shifted shares", "§6: shifted-window feasible shares of the library's tagged levels (L7, L8, L9, L1, L2, L3), 2020 and 2021-22: range", "1-7%",
      f"{min(sh):.1f}-{max(sh):.1f}%", "rounds to 1-7%", kind="OK" if (round(min(sh)) == 1 and round(max(sh)) == 7) else "MISMATCH")
claim("@(`01_intra_enter_fit.txt` l.73-96", "cite range enter fit l.73-96 bounds the pre-market-flat blocks (starts at the dated header, ends on the undated block's last line, l.97 is the next item)", "bounded",
      "bounded" if (L(F_ENT, 73).startswith("- pre-market-flat windows, dated 2020") and "'any opening range'" in L(F_ENT, 96) and L(F_ENT, 97).startswith("- held before")) else "NOT bounded")
claim("@(`01_intra_enter_fit.txt` l.73-96", "cite range check l.81-104 bounds the pre-market-flat blocks", "bounded",
      "bounded" if (L(F_CHK, 81).startswith("- beside: pre-market-flat windows, dated 2021-22") and "'any opening range'" in L(F_CHK, 104) and L(F_CHK, 105).startswith("- held before")) else "NOT bounded")
tr("@Record floors as before", "ENTER record floor (20 bars before the buy day) [enter fit l.13]", "20", F_ENT, 13, r"record floor = (\d+) bars")
tr("@Record floors as before", "STOP record floor (50 bars) [stop fit l.12]", "50", F_STP, 12, r"record floor = (\d+) bars")
tr("@Record floors as before", "EXIT record floor (50 bars) [exit fit l.12]", "50", F_EXT, 12, r"record floor = (\d+) bars")
tr("@(i)** minute-built session bars", "gate (i) bars: high/low within 0.5% on >= 98%; open/close within 0.5% on >= 90% [check l.11]", "98% / 90%", F_CHK, 11,
   r"\(bar ([\d.]+%);.*?\(bar ([\d.]+%);", tol=True)
tr("@a daily close below a level beyond the auction band", "gate (iii) bar: the last 60-minute bar closes below on >= 98% of such days [check l.131]", "98%", F_CHK, 131, r"\(bar ([\d.]+%)\)", tol=True)
claim("@raw L7 ≤ L1 ≤ L8 ≤ L6", "gate (ii) wording (raw L7 <= L1 <= L8 <= L6; the builder's first bar = L8_raw) is the printout's", "present",
      "present" if ("raw L7 <= L1 <= L8 <= L6" in L(F_ENT, 19) and "first bar equals L8_raw" in L(F_ENT, 19)) else "NOT present")
need = {"enter": [f"L{k}_{c}" for k in range(1, 10) for c in ("cross", "feasible", "verdict")],
        "stop": [f"S{lv}_{v}_{c}" for lv in (1, 3, 9, 10) for v in "TCH" for c in ("any", "certain", "unresolved", "first_j")],
        "exit": [f"E{k}_{c}" for k in (1, 2, 4) for c in ("last_j", "stop_preempt")]}
cols_by = {"enter": set(ef.columns) & set(ce.columns), "stop": set(sfit.columns) & set(sch.columns), "exit": set(xfit.columns) & set(xchk.columns)}
miss_c = {k: [c for c in v if c not in cols_by[k]] for k, v in need.items()}
claim("@(viii) NEW", "gate (viii): the TSV columns it names exist in both the fit and the check files (enter L1-L9 cross/feasible/verdict; stop _any/_certain/_unresolved/_first_j; exit E1/E2/E4 _last_j/_stop_preempt)",
      "none missing", "none missing" if not any(miss_c.values()) else f"missing {miss_c}")


l1_ = grab(F_ENT, 27, r"L1 \(re-read\): feasible \d+ = ([\d.]+%)")[0]
claim("@L1    | his words", "§9 template row shows L1 standalone 36.0% (the rev-fit number on 89, E-1); the intra fit's re-read of L1 on the same 87 windows is higher (enter fit l.27; TSV tally above)",
      "36.0%", f"{l1_} on 87", "gate (viii) re-reads one decimal: the printed run will show 36.8 beside a template that says 36.0", kind="NOTE")

# =============================================================================================================== fetch coverage
say("\n## 9. §8: the minute fetch (fetch logs and fetch lists only; NO bar file opened)")


def load_done(tree):
    out = {}
    with open(tree + "/_done.psv") as fh:
        for ln in fh:
            f = ln.rstrip("\n").split("|")
            if len(f) < 4 or f[0] > CUT:
                continue
            out[(f[0], f[1])] = f[3]
    return out


def date_files(tree):
    return {fn[:-len(".psv.gz")] for fn in os.listdir(tree) if fn.endswith(".psv.gz")}


DONE = {k: load_done(TREES[k]) for k in TREE_ORDER}
DFILES = {k: date_files(TREES[k]) for k in TREE_ORDER}
INT_DONE = load_done(INTRA_MIN)
lst = [ln.split("|") for ln in open(LIST_FULL).read().splitlines()]
assert_le_cut([r[1] for r in lst], "fetch list")
claim("@19,470 pairs", "fetch list: pairs", 19470, len(lst))
cnt = collections.Counter(INT_DONE.values())
claim("@19,184 ok, 286 empty", "fetch log (_done.psv of the intra tree): ok / empty / other, over the listed pairs", "19184 / 286 / 0",
      f"{cnt['ok']} / {cnt['empty']} / {sum(v for k, v in cnt.items() if k not in ('ok', 'empty'))}")
listed = {(r[1], r[0]) for r in lst}
claim("@pending.psv", "listed pairs with no fetch-log row (pending.psv expected empty)", 0, len(listed - set(INT_DONE)), "")
claim("@19,184 ok, 286 empty", "fetch-log rows not on the list", 0, len(set(INT_DONE) - listed))
claim("@tail ends ≤ 2024-01", "latest listed session (the doc: the tail ends <= 2024-01)", "<= 2024-01", max(r[1] for r in lst)[:7], kind="OK" if max(r[1] for r in lst) <= "2024-01-31" else "MISMATCH")


def state(d, tk):
    for k in TREE_ORDER:
        if DONE[k].get((d, tk)) == "ok" and d in DFILES[k]:
            return "ok"
    for k in TREE_ORDER:
        if DONE[k].get((d, tk)) == "empty":
            return "empty"
    return "missing"


def walked(df):
    out = set()
    for r in df.itertuples():
        i0 = max(0, r.Eb_i - WARM)
        j1 = min(r.exit_hi_i + TAIL, len(CAL) - 1) if r.has_exit else min(r.Eb_i + NOEXIT, len(CAL) - 1)
        for i in range(i0, j1 + 1):
            d = CAL[i]
            out.add((d, r.sym_a if d <= A_LAST else r.sym))
    return out


allpop = pd.concat([fd, uf, cd_, uc, virg_all])
wk = walked(allpop)
miss_pairs = {p for p in wk if state(*p) == "missing" and p not in INT_DONE}
claim("@covers every session this read", "walked ticker-days of every STOP/EXIT/ENTER population (10 warm-up + hold + 20 tail; still-held 20): neither in the five existing trees nor in the fetch log", 0,
      len(miss_pairs), f"walked pairs {len(wk):,}; sessions of the listed pairs are the missing ones of the five trees ({len([p for p in wk if state(*p) == 'missing']):,})")
claim("@covers every session this read", "walked pairs by state: ok in a tree / empty at source in a tree / missing from the trees, covered by the fetch", "info",
      f"{sum(1 for p in wk if state(*p) == 'ok'):,} / {sum(1 for p in wk if state(*p) == 'empty'):,} / {sum(1 for p in wk if state(*p) == 'missing'):,}", kind="NOTE")
claim("@covers every session this read", "walked pairs not on the list and not already in a tree = the fetch list is exactly the walked-missing set", "identical",
      "identical" if {p for p in wk if state(*p) == "missing"} == listed else f"differ: {len({p for p in wk if state(*p) == 'missing'} ^ listed)} pairs", kind=None)
claim("@(the tail ends ≤ 2024-01", "latest walked session of the still-held 2023 trades, FROM THE CALENDAR (buy day + 20 sessions)",
      "<= 2024-01", max(d for d, _ in wk)[:7], kind="OK" if max(d for d, _ in wk) <= "2024-01-31" else "MISMATCH")

# =============================================================================================================== summary
say("\n## Summary")
bad = [c for c in CLAIMS if c[4] == "MISMATCH"]
notes = [c for c in CLAIMS if c[4] == "NOTE"]
say(f"- claims: {len(CLAIMS)}; OK {sum(1 for c in CLAIMS if c[4] == 'OK')}; MISMATCH {len(bad)}; NOTE {len(notes)}; unresolved doc anchors {len(UNRESOLVED)}")
if UNRESOLVED:
    say("- UNRESOLVED anchors (doc line shown as '?'): " + "; ".join(UNRESOLVED))
say("\n## DOC-TOKEN CHECK (every number in the 'doc' column must occur within 3 lines of its anchor in the registration; a failure here is MY transcription, not a doc finding)")
for ln_, lab_, d_, lost_ in DOC_TOKEN_WARN:
    say(f"[L{ln_}] {lab_} | doc column {d_} | tokens not found near the anchor: {lost_}")
if not DOC_TOKEN_WARN:
    say("(none)")
say("\n## MISMATCH lines")
for c in bad:
    say(f"[L{c[0]}] {c[1]} | doc {fmt(c[2])} | mine {fmt(c[3])}" + (f" | {c[5]}" if c[5] else ""))
if not bad:
    say("(none)")
say("\n## NOTE lines")
for c in notes:
    say(f"[L{c[0]}] {c[1]} | doc {fmt(c[2])} | mine {fmt(c[3])}" + (f" | {c[5]}" if c[5] else ""))
with open(OUT_TXT, "w", encoding="utf8") as fh:
    fh.write("\n".join(LINES) + "\n")
sys.exit(0)
