#!/usr/bin/env python3
"""Independent recount of the ONE check of docs/analysis/cb_intraday_layer_prereg_2026-10-25.md (#705 intraday layer).

LOCAL, READ-ONLY. Writes only recount_check.txt beside this file. Does NOT run 01_intra.py's --check / --*-fit / --why-rates / --reset-fits;
never opens a minute or daily date after 2024-12-31 (asserted on every read); nothing of 2025-26.

WHAT IS IMPORTED (frozen copy 01_intra_frozen_ac598fc58aae.py, sha-checked against the freeze pin) AND WHAT IT IS USED FOR
  loaders only : load_core (buys / clocks / sets), load_for_stage (daily exports), MinuteStore (raw minute files), recs_for (record = daily bars
                 + minutes + ADR20), bar_sym, bars_of, EARLY_CLOSE;
  frozen account code (NOT recounted here; named in the table): rp.simulate, rev.speed_trail_trade (`ours`), rev.panel_trade (`his`),
                 rev.recovery, the Trade plumbing `make_legs_trade` fed with MY legs.
NOT USED anywhere: enter_score_trade, enter_summary, held_through_intra, stop_table_intra, exit_walk_intra, accounts_intra, hit_rates_for,
  exit_prepare, apply_chain, any check_stages code. Every level, crossing, verdict, control draw, held-through cell, EMA, trigger and leg
  below is recomputed here from the raw minute files / daily export / frames, then compared (a) row by row with the side-output TSVs and
  (b) after re-aggregation with the printout 01_intra_check.txt.

Two layers per claim: L1 = the printout's number re-aggregated from the side-output TSV (catches arithmetic / labelling);
                       L2 = the TSV rows re-derived from raw bars (catches the computation).
"""
import bisect
import gzip
import hashlib
import importlib.util
import json
import math
import os
import re
import sys
import zlib
from collections import Counter, defaultdict
from datetime import date

import numpy as np
import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
INTRA_DIR = os.path.abspath(os.path.join(HERE, "..", ".."))
REPO = os.path.abspath(os.path.join(INTRA_DIR, "..", "..", ".."))
DATA = "/Users/alvinfung/apollo_data"
OUTD = f"{DATA}/cb702/qm_streams/holdings_1024/intraday"
FROZEN = os.path.join(INTRA_DIR, "01_intra_frozen_ac598fc58aae.py")
PRINTOUT = os.path.join(INTRA_DIR, "01_intra_check.txt")
DOC = os.path.join(REPO, "docs", "analysis", "cb_intraday_layer_prereg_2026-10-25.md")
OUT_TXT = os.path.join(HERE, "recount_check.txt")
CUT = "2024-12-31"
SEED = 702

LOG = []
CLAIMS = []          # (stage, claim, printout, mine, status, note)


def say(msg=""):
    print(msg, flush=True)
    LOG.append(msg)


def fnum(x):
    a = np.asarray(x, dtype=float)
    return float(a.reshape(-1)[0]) if a.size == 1 else float("nan")


def num_eq(a, b, tol):
    if a is None or b is None:
        return a is None and b is None
    try:
        if isinstance(a, float) and isinstance(b, float) and math.isnan(a) and math.isnan(b):
            return True
        return abs(float(a) - float(b)) <= tol
    except (TypeError, ValueError):
        return a == b


def claim(stage, name, printed, mine, tol=0.0, note="", ok=None, info=False):
    """Record one claim. ok=None -> decided by equality (numbers within tol, strings by ==)."""
    if ok is None:
        if isinstance(printed, (int, float, np.floating, np.integer)) and isinstance(mine, (int, float, np.floating, np.integer)):
            ok = num_eq(float(printed), float(mine), tol)
        else:
            ok = (str(printed) == str(mine))
    CLAIMS.append((stage, name, printed, mine, ("NOTE" if info else "MATCH") if ok else "MISMATCH", note))
    if not ok:
        say(f"  !! MISMATCH [{stage}] {name}: printout {printed} | mine {mine} | {note}")
    return ok


def fmt(x):
    if isinstance(x, (float, np.floating)):
        return f"{x:.4f}".rstrip("0").rstrip(".") if not math.isnan(x) else "nan"
    return str(x)


def hm(s):
    """'HH:MM' ET -> minutes since 09:30 (negative before the open); None for empty."""
    if s is None or (isinstance(s, float) and math.isnan(s)) or s == "":
        return None
    h, m = str(s).split(":")
    return int(h) * 60 + int(m) - 570


def isnull(x):
    return x is None or (isinstance(x, float) and math.isnan(x)) or x == ""


def rng_for(key, seed=SEED):
    return np.random.default_rng([seed, zlib.crc32(key.encode()) & 0xFFFFFFFF])


def sha(path):
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for ch in iter(lambda: fh.read(1 << 20), b""):
            h.update(ch)
    return h.hexdigest()


# ───────────────────────────── load the frozen module (loaders only) ─────────────────────────────
PIN = None
for ln in open(os.path.join(INTRA_DIR, "01_intra_pins.txt")):
    if ln.startswith("- intra_module:"):
        PIN = ln.split(":", 1)[1].strip()
assert sha(FROZEN) == PIN, "frozen module is not the pinned module"
assert sha(os.path.join(INTRA_DIR, "01_intra.py")) == PIN, "live 01_intra.py differs from the pinned module"
_spec = importlib.util.spec_from_file_location("intra_frozen_recount", FROZEN)
I = importlib.util.module_from_spec(_spec)
sys.modules["intra_frozen_recount"] = I
_spec.loader.exec_module(I)
rev, rp, cb, H, R = I.rev, I.rp, I.cb, I.H, I.R

PR = open(PRINTOUT, encoding="utf-8").read().splitlines()


def printed_block(header_start):
    """The printout lines after the '- header_start...' line up to the next '- ' / '## ' line."""
    for i, ln in enumerate(PR):
        if ln.startswith(header_start):
            out = [ln]
            for x in PR[i + 1:]:
                if x.startswith("- ") or x.startswith("## ") or x.startswith("CHECK COMPLETE"):
                    break
                out.append(x)
            return out
    raise KeyError(header_start)


LVL_RX = re.compile(r"^\s+(L\d)[^:]*: feasible (\d+) = ([\d.]+)% \+-\d+; hit-or-ballpark (\d+) = ([\d.]+)% \+-\d+; shifted-window control feasible ([\d.]+)% hit ([\d.]+)%")


def parse_enter_block(header_start):
    blk = printed_block(header_start)
    out = dict(levels={}, n=None)
    m = re.search(r": (\d+) scorable windows", blk[0])
    out["n"] = int(m.group(1)) if m else None
    for ln in blk[1:]:
        m = LVL_RX.match(ln)
        if m:
            out["levels"][m.group(1)] = dict(f=int(m.group(2)), fp=float(m.group(3)), h=int(m.group(4)), hp=float(m.group(5)), sf=float(m.group(6)), sh=float(m.group(7)))
        m = re.match(r"^\s+random-price control: feasible ([\d.]+)%, hit-or-ballpark ([\d.]+)%", ln)
        if m:
            out["control"] = (float(m.group(1)), float(m.group(2)))
        m = re.match(r"^\s+'any opening range'.*?: feasible ([\d.]+)%, hit ([\d.]+)%.*its shifted-window control ([\d.]+)%", ln)
        if m:
            out["union"] = (float(m.group(1)), float(m.group(2)), float(m.group(3)))
    return out


def r1(x):
    """Round a share to one decimal in percent the way the printout does (pct)."""
    return float(f"{100.0 * x:.1f}")


# ───────────────────────────── load core + markets (loaders) ─────────────────────────────
say("# RECOUNT of the #705 intraday-layer CHECK (one run) — independent re-derivation from raw minute files / daily export / frames")
say(f"- module under recount: sha {PIN[:12]} (frozen copy == live 01_intra.py == the freeze pin); printout {os.path.basename(PRINTOUT)} {sha(PRINTOUT)[:12]}; registration {sha(DOC)[:12]}")
C = I.load_core(lambda m: None)
S, IS, E, mis, cal, CI = C["S"], C["I"], C["E"], C["mis"], C["cal"], C["CI"]
buys_by_eid = {b.eid: b for b in C["buys"]}
fit_tsv = {s: pd.read_csv(f"{OUTD}/{s}_fit_trades.tsv", sep="\t") for s in ("enter", "stop", "exit")}
FIT_EIDS = {s: set(df.eid) for s, df in fit_tsv.items()}
FIT_KEYS = {s: set(zip(df.sym, df.E)) for s, df in fit_tsv.items()}

enter_df = pd.read_csv(f"{OUTD}/check_enter_trades.tsv", sep="\t", keep_default_na=False, na_values=[""], dtype={"beside": str})
stop_df = pd.read_csv(f"{OUTD}/check_stop_trades.tsv", sep="\t")
exit_df = pd.read_csv(f"{OUTD}/check_exit_trades.tsv", sep="\t")
bars_df = pd.read_csv(f"{OUTD}/check_exit_bars.tsv.gz", sep="\t")
enter_df["beside"] = enter_df["beside"].fillna("")

all_check_buys = IS["chk22_dated"] + IS["chk22_und"] + IS["virgin_all"] + E["pre_dated_chk"] + E["pre_und_chk"] + E["prefirst_chk"] + E["held_0935"]
_fit_buys_pre = [buys_by_eid[int(e)] for e in fit_tsv["stop"].eid]          # the STOP fit's 415 records are re-derived too (section C2)
names_a, names_b = I.names_of(all_check_buys + _fit_buys_pre)
M = I.load_for_stage(lambda m: None, C, names_a, names_b)
store, sight = M["store"], M["sight"]
store.forbid = frozenset()
guard0 = I.BarGuard(None)

# ───────────────────────────── helpers on raw bars ─────────────────────────────
EARLY_MINE = {"2019-07-03", "2019-11-29", "2019-12-24", "2020-11-27", "2020-12-24", "2021-11-26", "2022-11-25", "2023-07-03", "2023-11-24",
              "2024-07-03", "2024-11-29", "2024-12-24"}
EARLY_MOD = {d for d in I.EARLY_CLOSE if "2019-01-01" <= d <= CUT}
WIN_FULL = [(0, 29), (30, 89), (90, 149), (150, 209), (210, 269), (270, 329), (330, 389)]
WIN_EARLY = [(0, 29), (30, 89), (90, 149), (150, 209)]
EXIST = {"L7": 1, "L8": 30, "L9": 30, "L1": 5, "L6": 60}


def is_early(d):
    return d in EARLY_MINE or (d in I.EARLY_CLOSE and d < "2019-01-01")


def trim(mb, d):
    """The session's minute arrays (minute,o,h,l,c) with minutes >= 210 dropped on an early-close day."""
    mn, o, h, l, c = (np.asarray(x) for x in (mb.minute, mb.o, mb.h, mb.l, mb.c))
    if is_early(d):
        s = mn < 210
        return mn[s], o[s], h[s], l[s], c[s]
    return mn, o, h, l, c


def h60_mine(mb, d):
    """Clock-anchored 60-minute bars of one session: list over windows of None | dict(k, lo, hi, o, h, l, c, first, close_m, n)."""
    mn, o, h, l, c = trim(mb, d)
    out = []
    for k, (lo, hi) in enumerate(WIN_EARLY if is_early(d) else WIN_FULL):
        s = (mn >= lo) & (mn <= hi)
        if not s.any():
            out.append(None)
            continue
        ix = np.flatnonzero(s)
        out.append(dict(k=k, lo=lo, hi=hi, o=float(o[ix[0]]), h=float(h[s].max()), l=float(l[s].min()), c=float(c[ix[-1]]), first=int(mn[ix[0]]),
                        close_m=int(mn[ix[-1]]), n=int(len(ix))))
    return out


def first_cross_from(mb, level, m_from):
    if mb is None or level is None or not np.isfinite(level):
        return None
    hit = np.flatnonzero((np.asarray(mb.minute) >= m_from) & (np.asarray(mb.h) > level))
    return int(mb.minute[hit[0]]) if len(hit) else None


def window_range_verdict(mb, price, flat_m, first_m, adr20):
    mn = np.asarray(mb.minute)
    s = (mn > flat_m) & (mn <= first_m)
    if not s.any():
        return "no_bracket_minutes"
    lo, hi = float(np.asarray(mb.l)[s].min()), float(np.asarray(mb.h)[s].max())
    if lo <= price <= hi:
        return "HIT"
    if min(abs(price - lo), abs(price - hi)) <= 0.25 * adr20 * price:
        return "BALLPARK"
    return "MISS"


def sess_close(d):
    return 210 if is_early(d) else 390


def get_mb(b, d=None):
    d = d or b.E
    return store.get(d, I.bar_sym(d, b.sym_a, b.sym), b)


def must_not_exceed(d):
    assert d <= CUT, f"date {d} beyond {CUT}"


# ═════════════════════════════════════════════════════════════════════════════════════════════
# A. POPULATIONS (registration §2 / §5d / §6b / §7d) and disjointness from the fit sets
# ═════════════════════════════════════════════════════════════════════════════════════════════
say("\n## A. POPULATIONS")
claim("A", "early-close days 2019-2024 (mine, from the exchange calendar) == the module's list on those dates", len(EARLY_MOD), len(EARLY_MINE),
      note="12 half-days 2019-2024", ok=(EARLY_MOD == EARLY_MINE))


def my_clock_sane(b):
    fl, fm = hm(b.flat_clock), hm(b.first_clock)
    if fl is None or fm is None or fl < 0:
        return "flat_before_open"
    if fm - fl <= 0:
        return "zero_width"
    if b.first_frame in mis or b.prev_full_frame in mis:
        return "clock_misread"
    return "ok"


def my_windows(bs, flicker=None):
    return [b for b in bs if b.in_bracket and my_clock_sane(b) == "ok" and (flicker is None or b.flicker == flicker)]


# set sizes against the registration's §2 table
reg_sizes = {"chk22_dated": 111, "chk22_und": 226, "virgin_und": 62, "virgin_dated": 27, "virgin_all": 89, "fit_dated": 149, "fit_und": 304}
for k, n in reg_sizes.items():
    claim("A", f"set size {k} (registration §2)", n, len(IS[k]))
# independent membership of the ENTER windows (own §2c): deciding 43, dated 20, flickers 19, virgin 17 (9 nf)
mine_dec = my_windows(IS["chk22_und"], flicker=False)
claim("A", "ENTER deciding windows after §2c (2021-22 undated non-flicker in-session) = 43", 43, len(mine_dec))
claim("A", "  ... same eids as the loader's E['chk22_und']", True, {b.eid for b in mine_dec} == {b.eid for b in E["chk22_und"]})
claim("A", "2021-22 dated in-session windows after §2c = 20", 20, len(my_windows(IS["chk22_dated"])))
claim("A", "2021-22 undated flicker windows = 19", 19, len(my_windows(IS["chk22_und"], flicker=True)))
mine_v = my_windows(IS["virgin_all"])
claim("A", "virgin in-session windows scorable after §2c = 17 (9 non-flicker)", "17 (9)", f"{len(mine_v)} ({sum(1 for b in mine_v if not b.flicker)})")
v9 = sorted(f"{b.sym} {b.E}" for b in mine_v if not b.flicker)
claim("A", "the 9 virgin non-flicker windows by name (registration §2c)", ", ".join(sorted(["ASPS 2019-10-03", "JCP 2019-10-07", "RLGY 2019-10-10", "CCS 2019-10-17", "BABA 2019-11-01", "LX 2019-11-15", "APT 2020-01-23", "CVNA 2023-05-18", "AI 2023-05-19"])), ", ".join(v9))
dropped22 = [f"{b.sym} {b.E} {my_clock_sane(b)}" for b in IS["chk22_und"] if b.in_bracket and not b.flicker and my_clock_sane(b) != "ok"]
claim("A", "2021-22 undated non-flicker in-session window dropped by §2c", "DWAC 2022-01-31 flat_before_open", "; ".join(dropped22))

# the check-side TSV rows vs the registration's check sets and the fit sets
chk_windows = enter_df[enter_df.beside == ""]
claim("A", "ENTER check TSV: first 61 rows = the draw population's records (64 windows less 3 under the 20-bar floor)", 61, len(chk_windows))
dec_rows = enter_df[(enter_df.beside == "") & (~enter_df.dated.astype(bool)) & (enter_df.scorable.astype(bool)) & (enter_df.sane == "ok") & (~enter_df.flicker.astype(bool))]
claim("A", "ENTER DECIDING set = beside empty, undated, scorable, sane ok, non-flicker (TSV) = 40 records", 40, len(dec_rows))
claim("A", "  ... deciding eids are a subset of the 43 windows; the 3 absent ones are exactly the 20-bar-floor drops", True,
      set(dec_rows.eid) <= {b.eid for b in mine_dec})
missing3 = [b for b in mine_dec if b.eid not in set(dec_rows.eid)]


def my_bars_before_E(b):
    era = I.era_of(b.E)
    D = M["Ds"][era]
    tk = b.sym_a if era == "A" else b.sym
    bars, cidx = I.bars_of(D, tk)
    e_ci = bisect.bisect_left(D.cal, date.fromisoformat(b.E))
    return int(np.searchsorted(cidx, e_ci))


claim("A", "  ... the 3 missing windows each have < 20 daily bars before the buy day (own count from the export)", "3 dropped {'bars_before_E_lt_20': 3}",
      f"{sum(1 for b in missing3 if my_bars_before_E(b) < 20)} of {len(missing3)} have <20 ({', '.join(f'{b.sym} {b.E} e={my_bars_before_E(b)}' for b in missing3)})",
      ok=(len(missing3) == 3 and all(my_bars_before_E(b) < 20 for b in missing3)))
claim("A", "  ... every window of the deciding set has >= 20 daily bars before the buy day", True, all(my_bars_before_E(buys_by_eid[e]) >= 20 for e in dec_rows.eid))
prev41 = {b.eid for b in S["ent_chk_und"]}
gate7_rows = chk_windows[(chk_windows.eid.isin(prev41)) & (chk_windows.scorable.astype(bool))]
claim("A", "gate (vii) population: the previous read's 41 undated records (44 windows, DWAC in) scorable here", 41, len(gate7_rows))
virgin_rows = enter_df[enter_df.beside == "virgin"]
claim("A", "ENTER virgin TSV rows: 17 windows' records with minutes (9 nf + 8 flicker, one flicker without minutes -> 16 rows?)", "9 nf / 7 fl scorable",
      f"{int((~virgin_rows.flicker.astype(bool)).sum())} nf / {int(virgin_rows.flicker.astype(bool).sum())} fl rows", ok=((~virgin_rows.flicker.astype(bool)).sum() == 9 and virgin_rows.flicker.astype(bool).sum() == 7))

# disjointness from the fit sets: eid, (sym, E) and by date window
fit_win = ("2020-01-27", "2020-12-31")
check_sets = {
    "ENTER check rows": [(int(r.eid), r.sym, r.E) for r in enter_df.itertuples()],
    "STOP check rows": [(int(r.eid), r.sym, r.E) for r in stop_df.itertuples()],
    "EXIT check rows": [(int(r.eid), r.sym, r.E) for r in exit_df.itertuples()],
}
for nm, rows in check_sets.items():
    in_fit_win = [r for r in rows if fit_win[0] <= r[2] <= fit_win[1]]
    ov_eid = [r for r in rows if any(r[0] in FIT_EIDS[s] for s in FIT_EIDS)]
    ov_key = [r for r in rows if any((r[1], r[2]) in FIT_KEYS[s] for s in FIT_KEYS)]
    claim("A", f"disjointness: {nm} ({len(rows)}) vs the three fit TSVs by eid / (sym,E) / fit date window 2020-01-27..12-31", "0 / 0 / 0",
          f"{len(ov_eid)} / {len(ov_key)} / {len(in_fit_win)}", ok=(not ov_eid and not ov_key and not in_fit_win))
fit_eids_loader = {b.eid for b in IS["fit_dated"] + IS["fit_und"]}
claim("A", "disjointness: the loader's fit sets (fit_dated 149 + fit_und 304) share no eid with any DECIDING/beside-scored check population (chk22 dated+und, virgin, pre-flat, pre-first)", 0,
      len(fit_eids_loader & {b.eid for b in IS["chk22_dated"] + IS["chk22_und"] + IS["virgin_all"] + E["pre_dated_chk"] + E["pre_und_chk"] + E["prefirst_chk"]}))
held_ov = sorted(f"{b.sym} {b.E}" for b in E["held_0935"] if b.eid in fit_eids_loader)
claim("A", "NOTE: the 'held before 09:35' beside list (9 trades, L7 only, deciding nothing) reuses fit-window trades by design (§2b names TSLA/UAL/DXCM/PINS/SHOP/TTD/ROKU 2020)",
      "beside only", f"{len(held_ov)} of {len(E['held_0935'])} are fit-set trades ({', '.join(held_ov)})", ok=True, info=True,
      note="not a check population; no decision reads it")

# STOP populations
vu_df = stop_df[stop_df.eid.isin({b.eid for b in IS["virgin_und"]})]
claim("A", "STOP deciding records = the virgin undated trades after the 50-bar floor (62 -> 58)", "58 of 62 (no_bar_on_E 4)", f"{len(vu_df)} of {len(IS['virgin_und'])}",
      ok=(len(vu_df) == 58))


def virgin_by_date(row_E, dated):
    y = int(row_E[:4])
    return (y in (2019, 2023)) or (row_E[:4] == "2022" and row_E > "2022-06-14") or ("2020-01-01" <= row_E <= "2020-01-26")


stop_rows_E = {int(r.eid): (r.E, bool(r.dated)) for r in stop_df.itertuples()}
mine_vu = {e for e, (Ed, d) in stop_rows_E.items() if virgin_by_date(Ed, d) and not d}
claim("A", "STOP deciding = rows undated AND dated in 2019 / 2023 / 2022 after 06-14 / 2020 before 01-27 (own date test) == loader virgin_und rows", True,
      mine_vu == set(vu_df.eid))
no_bar = [b for b in IS["virgin_und"] if b.eid not in set(stop_df.eid)]
claim("A", "  ... the 4 virgin undated trades with no record: no daily bar on the buy day (own test)", "4",
      f"{len(no_bar)} (" + ", ".join(f"{b.sym} {b.E}" for b in no_bar) + ")", ok=(len(no_bar) == 4))
vd_df = stop_df[stop_df.eid.isin({b.eid for b in IS["virgin_dated"]})]
claim("A", "STOP beside: virgin dated 27 -> records", "26 (bars_before_E_lt_50 1)", len(vd_df), ok=(len(vd_df) == 26))
claim("A", "STOP beside: 2021-22 undated 226 -> 212, dated 111 -> 110", "212 / 110",
      f"{int(stop_df.eid.isin({b.eid for b in IS['chk22_und']}).sum())} / {int(stop_df.eid.isin({b.eid for b in IS['chk22_dated']}).sum())}",
      ok=(stop_df.eid.isin({b.eid for b in IS['chk22_und']}).sum() == 212 and stop_df.eid.isin({b.eid for b in IS['chk22_dated']}).sum() == 110))
claim("A", "EXIT deciding rows = 2021-22 dated with an exit, after the 50-bar floor", "110 rows, 107 armed", f"{len(exit_df)} rows, {int((exit_df.abstain.isna() | (exit_df.abstain == '')).sum())} armed",
      ok=(len(exit_df) == 110 and int(exit_df.abstain.isna().sum()) == 107))
claim("A", "EXIT eids == the loader's 2021-22 dated set minus one under the floor", True, set(exit_df.eid) <= {b.eid for b in IS["chk22_dated"]} and len(IS["chk22_dated"]) - len(exit_df) == 1)


# ═════════════════════════════════════════════════════════════════════════════════════════════
# B. ENTER (§5): levels, crossings, verdicts, the random-price control replay, the shifted-window control, the union, the veto
# ═════════════════════════════════════════════════════════════════════════════════════════════
say("\n## B. ENTER")
ALL = ("L7", "L8", "L9", "L1", "L2", "L3", "L4", "L5", "L6")
I.preload_buy_days(store, all_check_buys)


def recs_of(bs):
    r, drop = I.recs_for(bs, M, store, guard0, min_bars=20)
    return r, drop


def l9_in_force(L9, d, m):
    for k, (lo, hi) in enumerate(WIN_EARLY if is_early(d) else WIN_FULL):
        if lo <= m <= hi:
            return L9[k] if k >= 1 else None
    return None


def my_levels(rec):
    b, mb = rec.b, rec.mb
    mn, hh = np.asarray(mb.minute), np.asarray(mb.h)
    floor = float(b.pivot) if (b.dated and b.setup in ("breakout", "both") and b.pivot is not None) else None
    fl = (lambda x: None if x is None else (max(x, floor) if floor is not None else x))
    L7raw = float(hh[mn == 0].max()) if (mn == 0).any() else None
    L8raw = float(hh[mn <= 29].max()) if (mn <= 29).any() else None
    o5 = float(hh[mn < 5].max()) if (mn < 5).any() else None
    o60 = float(hh[mn < 60].max()) if (mn < 60).any() else None
    bars = h60_mine(mb, b.E)
    sched = [None] + [(bars[k - 1]["h"] if bars[k - 1] is not None else None) for k in range(1, len(bars))]
    p, e = rec.p, rec.e
    L = dict(L7=fl(L7raw), L8=fl(L8raw), L9=[fl(x) for x in sched],
             L1=(max(o5, float(b.pivot)) if (b.dated and b.pivot is not None) else o5) if o5 is not None else None,
             L2=float(rec.bars.h[p]),
             L3=float(b.pivot) if (b.setup in ("breakout", "both") and b.pivot is not None) else float(np.max(rec.bars.h[max(p - 19, 0):p + 1])),
             L4=float(rec.bars.o[e]), L5=float(rec.bars.c[p]), L6=o60)
    return L, dict(L7_raw=L7raw, L8_raw=L8raw, L1_raw=o5, L6_raw=o60, H60_0_high=(bars[0]["h"] if bars[0] else None))


def my_l9_cross(mb, L9, d):
    mn, hh = np.asarray(mb.minute), np.asarray(mb.h)
    for i in np.flatnonzero(mn >= 30):
        lvl = l9_in_force(L9, d, int(mn[i]))
        if lvl is not None and float(hh[i]) > lvl:
            return int(mn[i])
    return None


def my_score_level(rec, lv, L, flat, first):
    """-> dict(price, cross, feasible, verdict)"""
    mb, b = rec.mb, rec.b
    if first < EXIST.get(lv, 0):
        # the TSV keeps an OLD level's raw price on a not-yet-existing window (rec.levels) and no price for a NEW level
        return dict(price=(L[lv] if lv in ("L1", "L2", "L3", "L4", "L5", "L6") else None), cross=None, feasible=False, verdict="no_level_yet")
    if lv == "L9":
        cross = my_l9_cross(mb, L["L9"], b.E)
        price = l9_in_force(L["L9"], b.E, first)
        feas = cross is not None and flat < cross <= first
        if price is None:
            return dict(price=None, cross=cross, feasible=feas, verdict="no_bar")
        return dict(price=price, cross=cross, feasible=feas, verdict=window_range_verdict(mb, price, flat, first, rec.adr20))
    price = L[lv]
    if lv == "L7" and price is None:
        return dict(price=None, cross=None, feasible=False, verdict="no_bar_0930")
    if price is None or not np.isfinite(price):
        return dict(price=price, cross=None, feasible=False, verdict="no_level")
    cross = first_cross_from(mb, price, EXIST.get(lv, 0) if lv in ("L7", "L8") else 0)
    feas = cross is not None and flat < cross <= first
    return dict(price=price, cross=cross, feasible=feas, verdict=window_range_verdict(mb, price, flat, first, rec.adr20))


def my_shift(rec, lv, L, cross, flat, first, n=200):
    b, mb = rec.b, rec.mb
    w = first - flat
    exist = EXIST.get(lv, 0)
    close = sess_close(b.E)
    room = close - w - exist
    feas, hit = np.zeros(n, dtype=bool), np.zeros(n, dtype=bool)
    if room < 0 or w <= 0:
        return dict(no_room=True, feas=feas, hit=hit, fs=float("nan"), hs=float("nan"))
    for d in range(n):
        s = exist + int(rng_for(f"intra|bracket|{b.eid}|{lv}|{d}").integers(0, room + 1))
        feas[d] = cross is not None and s < cross <= s + w
        price = l9_in_force(L["L9"], b.E, s + w) if lv == "L9" else L[lv]
        if price is None or not np.isfinite(price):
            continue
        v = window_range_verdict(mb, float(price), s, s + w, rec.adr20)
        hit[d] = v in ("HIT", "BALLPARK")
    return dict(no_room=False, feas=feas, hit=hit, fs=float(feas.mean()), hs=float(hit.mean()))


def my_random_control(mb, flat, first, adr20, rng):
    """200 closes of uniformly random minutes (09:30-16:00; a minute with no bar takes the nearest PRIOR bar's close, before the first bar the first open),
    each scored as a level with the first crossing searched from minute 0 over the whole session."""
    u = rng.integers(0, 390, size=200)
    mn, cc, oo = np.asarray(mb.minute), np.asarray(mb.c), np.asarray(mb.o)
    idx = np.searchsorted(mn, u, side="right") - 1
    px = np.where(idx >= 0, cc[np.maximum(idx, 0)], oo[0])
    f, hh_ = np.zeros(200, dtype=bool), np.zeros(200, dtype=bool)
    for i, p in enumerate(px):
        cr = first_cross_from(mb, float(p), 0)
        f[i] = cr is not None and flat < cr <= first
        hh_[i] = window_range_verdict(mb, float(p), flat, first, adr20) in ("HIT", "BALLPARK")
    return float(f.mean()), float(hh_.mean())


def my_score_window(rec, ctl_rng):
    b, mb = rec.b, rec.mb
    flat, first = hm(b.flat_clock), hm(b.first_clock)
    L, raw = my_levels(rec)
    res = {lv: my_score_level(rec, lv, L, flat, first) for lv in ALL}
    cf, ch = my_random_control(mb, flat, first, rec.adr20, ctl_rng)
    res["control"] = (cf, ch)
    res["shift"] = {}
    for lv in ALL:
        if lv == "L9":
            cross = my_l9_cross(mb, L["L9"], b.E)
        elif lv in ("L7", "L8"):
            cross = first_cross_from(mb, L[lv], EXIST[lv]) if L[lv] is not None else None
        else:
            cross = first_cross_from(mb, L[lv], 0) if L[lv] is not None else None
        res["shift"][lv] = my_shift(rec, lv, L, cross, flat, first)
    res["union"] = dict(feasible=any(res[lv]["feasible"] for lv in ("L7", "L1", "L8")), hit=any(res[lv]["verdict"] in ("HIT", "BALLPARK") for lv in ("L7", "L1", "L8")))
    uf = np.zeros(200, dtype=bool)
    for lv in ("L7", "L1", "L8"):
        uf |= res["shift"][lv]["feas"]
    res["union"]["shift_f"] = float(uf.mean())
    res["raw"] = raw
    res["levels"] = L
    return res


# ---- replay in the exact order the registration fixes (§3 / C6): draw population (E, eid) -> 2021-22 flickers -> virgin (flicker, E, eid) -> pre-flat dated -> pre-flat undated
draw_pop = sorted(S["ent_chk_dated"] + S["ent_chk_und"], key=lambda b: (b.E, b.eid))
claim("B", "random-price control draw population (the previous read's windows)", 64, len(draw_pop))
recs_draw, drop_draw = recs_of(draw_pop)
claim("B", "  ... records after the 20-bar floor / with minutes", "61 (dropped 3)", f"{len(recs_draw)} (dropped {sum(drop_draw.values())})", ok=(len(recs_draw) == 61))
ctl_rng = rng_for("rev|minute")           # the frozen draw: one generator, replayed in order
SC = {}                                   # eid -> my result (first scoring wins; a window appears in one set only except 'draw' + deciding)
ordered = []
for r in sorted(recs_draw, key=lambda x: (x.b.E, x.b.eid)):
    if r.mb is None:
        continue
    SC[r.b.eid] = my_score_window(r, ctl_rng)
    ordered.append(r.b.eid)
rr_fl, _ = recs_of(E["chk22_fl"])
fl_ids = []
for r in sorted(rr_fl, key=lambda x: (x.b.E, x.b.eid)):
    if r.mb is None:
        continue
    SC[r.b.eid] = my_score_window(r, ctl_rng)
    fl_ids.append(r.b.eid)
rr_v, _ = recs_of(E["virgin"])
v_ids = []
for r in sorted(rr_v, key=lambda x: (x.b.flicker, x.b.E, x.b.eid)):
    if r.mb is None:
        continue
    SC[r.b.eid] = my_score_window(r, ctl_rng)
    v_ids.append(r.b.eid)
pre_ids = {}
for lab, bs in (("pre_d", E["pre_dated_chk"]), ("pre_u", E["pre_und_chk"])):
    rr, _ = recs_of(bs)
    ids = []
    for r in sorted(rr, key=lambda x: (x.b.E, x.b.eid)):
        if r.mb is None or hm(r.b.first_clock) is None or hm(r.b.flat_clock) is None:
            continue
        SC[r.b.eid] = my_score_window(r, ctl_rng)
        ids.append(r.b.eid)
    pre_ids[lab] = ids
say(f"- scored (mine): draw population {len(ordered)}, 2021-22 flickers {len(fl_ids)}, virgin {len(v_ids)}, pre-flat dated {len(pre_ids['pre_d'])}, undated {len(pre_ids['pre_u'])}")

# ---- (B1) L2 row-by-row against the TSV
def tsv_rows_for(df):
    return {int(r["eid"]): r for r in df.to_dict("records")}


tsv_all = tsv_rows_for(enter_df)
n_cmp, bad_rows = 0, []
for eid, res in SC.items():
    if eid not in tsv_all:
        continue
    t = tsv_all[eid]
    n_cmp += 1
    probs = []
    for lv in ALL:
        s = res[lv]
        tp = t[f"{lv}_price"]
        if not ((isnull(tp) and s["price"] is None) or (not isnull(tp) and s["price"] is not None and abs(float(tp) - float(s["price"])) <= 1e-9 * max(1.0, abs(float(tp))))):
            probs.append(f"{lv}_price {tp} vs {s['price']}")
        tc = t[f"{lv}_cross"]
        if not ((isnull(tc) and s["cross"] is None) or (not isnull(tc) and s["cross"] is not None and int(float(tc)) == s["cross"])):
            probs.append(f"{lv}_cross {tc} vs {s['cross']}")
        if bool(t[f"{lv}_feasible"]) != bool(s["feasible"]):
            probs.append(f"{lv}_feasible")
        if str(t[f"{lv}_verdict"]) != s["verdict"]:
            probs.append(f"{lv}_verdict {t[f'{lv}_verdict']} vs {s['verdict']}")
        sh = res["shift"][lv]
        if not sh["no_room"]:
            if abs(float(t[f"{lv}_shift_feasible"]) - sh["fs"]) > 1e-12 or abs(float(t[f"{lv}_shift_hit"]) - sh["hs"]) > 1e-12:
                probs.append(f"{lv}_shift {t[f'{lv}_shift_feasible']}/{t[f'{lv}_shift_hit']} vs {sh['fs']}/{sh['hs']}")
        if bool(t[f"{lv}_shift_no_room"]) != bool(sh["no_room"]):
            probs.append(f"{lv}_no_room")
    if abs(float(t["control_feasible"]) - res["control"][0]) > 1e-12 or abs(float(t["control_hit"]) - res["control"][1]) > 1e-12:
        probs.append(f"control {t['control_feasible']}/{t['control_hit']} vs {res['control']}")
    if bool(t["union_feasible"]) != res["union"]["feasible"] or bool(t["union_hit"]) != res["union"]["hit"]:
        probs.append("union")
    if abs(float(t["union_shift_feasible"]) - res["union"]["shift_f"]) > 1e-12:
        probs.append(f"union_shift {t['union_shift_feasible']} vs {res['union']['shift_f']}")
    for k_t, k_m in (("L1_raw", "L1_raw"), ("L6_raw", "L6_raw"), ("L7_raw", "L7_raw"), ("L8_raw", "L8_raw"), ("H60_0_high", "H60_0_high")):
        tv, mv = t[k_t], res["raw"][k_m]
        if not ((isnull(tv) and mv is None) or (not isnull(tv) and mv is not None and abs(float(tv) - mv) < 1e-9)):
            probs.append(f"{k_t} {tv} vs {mv}")
    if abs(float(t["adr20"]) - rec_adr) > 1e-12 if False else False:
        pass
    if probs:
        bad_rows.append((eid, t["sym"], t["E"], probs[:4]))
claim("B", f"L2 per-row: {n_cmp} TSV rows x 9 levels x (price, crossing minute, feasible, verdict, shifted-control feasible+hit) + control + union + raw levels re-derived from raw minute bars",
      f"{n_cmp} rows", f"{n_cmp - len(bad_rows)} rows identical, {len(bad_rows)} differ", ok=(len(bad_rows) == 0 and n_cmp == len(tsv_all)),
      note=("; ".join(f"{e} {s} {d}: {p}" for e, s, d, p in bad_rows[:5])))
claim("B", "  ... TSV rows scored == rows I scored (no row only on one side)", len(tsv_all), len({e for e in SC if e in tsv_all}))

# ---- (B2) L1: printed blocks re-aggregated from MY rows
def agg(ids):
    rows = [SC[e] for e in ids]
    n = len(rows)
    out = dict(n=n, levels={}, control=(float(np.mean([r["control"][0] for r in rows])) if n else float("nan"), float(np.mean([r["control"][1] for r in rows])) if n else float("nan")))
    for lv in ALL:
        f = sum(r[lv]["feasible"] for r in rows)
        h = sum(r[lv]["verdict"] in ("HIT", "BALLPARK") for r in rows)
        room = [r["shift"][lv] for r in rows if not r["shift"][lv]["no_room"]]
        out["levels"][lv] = dict(f=int(f), h=int(h), sf=float(np.mean([s["fs"] for s in room])) if room else float("nan"),
                                 sh=float(np.mean([s["hs"] for s in room])) if room else float("nan"), verdicts=Counter(r[lv]["verdict"] for r in rows))
    uf = sum(r["union"]["feasible"] for r in rows)
    uh = sum(r["union"]["hit"] for r in rows)
    out["union"] = (uf / n if n else float("nan"), uh / n if n else float("nan"), float(np.mean([r["union"]["shift_f"] for r in rows])) if n else float("nan"))
    out["uf"], out["uh"] = uf, uh
    return out


dec_ids = [e for e in ordered if e in {b.eid for b in E["chk22_und"]}]
dated_ids = [e for e in ordered if e in {b.eid for b in E["chk22_dated"]}]
vnf_ids = [e for e in v_ids if not buys_by_eid[e].flicker]
vfl_ids = [e for e in v_ids if buys_by_eid[e].flicker]
claim("B", "DECIDING records (mine, scored from raw minutes)", 40, len(dec_ids))
claim("B", "  ... == TSV deciding eids", True, set(dec_ids) == set(dec_rows.eid))
SETS = [("DECIDING:", dec_ids, "deciding 2021-22 undated nf"), ("- beside: the 20 dated", dated_ids, "dated 2021-22 (beside)"), ("- beside: 2021-22 flickers", fl_ids, "2021-22 flickers (beside)"),
        ("- the untouched years, non-flicker", vnf_ids, "untouched nf (veto set)"), ("- beside: the untouched years, flickers", vfl_ids, "untouched flickers (beside)"),
        ("- beside: pre-market-flat windows, dated", pre_ids["pre_d"], "pre-market-flat dated (beside)"), ("- beside: pre-market-flat windows, undated", pre_ids["pre_u"], "pre-market-flat undated (beside)")]
AG = {}
for hdr, ids, lab in SETS:
    pb = parse_enter_block("- " + hdr if not hdr.startswith("-") else hdr)
    mine = agg(ids)
    AG[lab] = mine
    claim("B", f"[{lab}] scorable windows", pb["n"], mine["n"])
    for lv in ALL:
        pl, ml = pb["levels"][lv], mine["levels"][lv]
        claim("B", f"[{lab}] {lv}: feasible n", pl["f"], ml["f"])
        claim("B", f"[{lab}] {lv}: feasible share", pl["fp"], r1(ml["f"] / mine["n"]), tol=0.05)
        claim("B", f"[{lab}] {lv}: hit-or-ballpark n", pl["h"], ml["h"])
        claim("B", f"[{lab}] {lv}: shifted-window control feasible / hit (%)", f"{pl['sf']} / {pl['sh']}", f"{r1(ml['sf'])} / {r1(ml['sh'])}")
    claim("B", f"[{lab}] random-price control feasible / hit-or-ballpark (%)", f"{pb['control'][0]} / {pb['control'][1]}", f"{r1(mine['control'][0])} / {r1(mine['control'][1])}")
    claim("B", f"[{lab}] 'any opening range' union feasible / hit / shifted control (%)", f"{pb['union'][0]} / {pb['union'][1]} / {pb['union'][2]}",
          f"{r1(mine['union'][0])} / {r1(mine['union'][1])} / {r1(mine['union'][2])}")

# ---- (B3) the named headline claims
D = AG["deciding 2021-22 undated nf"]
claim("B", "HEADLINE L8 (chosen) feasible on the 40 = 18 = 45.0% and hit-or-ballpark 35 = 87.5%", "18 = 45.0% / 35 = 87.5%", f"{D['levels']['L8']['f']} = {r1(D['levels']['L8']['f']/40)}% / {D['levels']['L8']['h']} = {r1(D['levels']['L8']['h']/40)}%")
claim("B", "HEADLINE union 'any opening range' (L7/L1/L8) feasible 62.5% vs the random-price control 30.0% (beside)", "62.5% vs 30.0%",
      f"{r1(D['union'][0])}% (n={D['uf']}) vs {r1(D['control'][0])}% (exact {D['control'][0]:.4f})", ok=(r1(D['union'][0]) == 62.5 and r1(D['control'][0]) == 30.0))
# gate (vii): the previous 41 undated records
g7 = [e for e in ordered if e in prev41]
g7f = float(np.mean([SC[e]["control"][0] for e in g7]))
g7h = float(np.mean([SC[e]["control"][1] for e in g7]))
claim("B", "gate (vii): random-price control on the previous 41 undated windows reproduces 31.7% / 85.9% (replayed draws, mine)", "31.7% / 85.9% on 41", f"{r1(g7f)}% / {r1(g7h)}% on {len(g7)}",
      ok=(len(g7) == 41 and r1(g7f) == 31.7 and r1(g7h) == 85.9))
# margin at equality: 45.0 vs 30.0 + 15
fs = D["levels"]["L8"]["f"] / 40
cf = D["control"][0]
claim("B", "control margin: L8 feasible 0.4500 vs random-price control + 0.15 (exact)", "printout lists only 'feasible 45.0% < 50.0%'; margin not listed", f"0.4500 vs {cf:.4f}+0.15 = {cf + 0.15:.4f}",
      ok=True, info=True, note=("the margin test is " + ("PASSED" if fs >= cf + 0.15 else "FAILED") + " on exact numbers; it sits at equality, so the printout's reason list silently passes it; the verdict is FAIL on the 50% bar alone"))
# verdict logic: chosen L8, deciding
reasons = []
if len(dec_ids) < 40:
    reasons.append("size")
if fs < 0.50:
    reasons.append(f"feasible {r1(fs)}% < 50.0%")
sf_ = D["levels"]["L8"]["sf"]
if not fs >= cf + 0.15:
    reasons.append("random control margin")
if not fs >= sf_ + 0.15:
    reasons.append("shifted control margin")
if D["levels"]["L8"]["h"] / 40 < 0.70:
    reasons.append("hit floor")
falsifier = all(D["levels"][lv]["f"] / 40 < 0.5 for lv in ("L7", "L8", "L9"))
verdict_enter = "FAIL" if reasons else "PASS"
claim("B", "ENTER verdict on the deciding set (mine: size>=40, feasible>=50%, controls+15, hit floor 70%)", "FAIL (feasible 45.0% < 50.0%; falsifier: no new level >= 50%)",
      f"{verdict_enter} ({'; '.join(reasons)}; falsifier no new level>=50%: {falsifier})", ok=(verdict_enter == "FAIL" and reasons == ["feasible 45.0% < 50.0%"] and falsifier))
claim("B", "n = 40 sits exactly on the size floor (<=39 -> INCONCLUSIVE-by-size)", "40 (floor 40)", f"{len(dec_ids)}", ok=(len(dec_ids) == 40), info=True, note="one fewer record would have flipped the stage to INCONCLUSIVE-by-size; the verdict is FAIL either way")
# sign veto on the 9
V = AG["untouched nf (veto set)"]
vf = V["levels"]["L8"]["f"] / V["n"]
vctrl = max(V["control"][0], V["levels"]["L8"]["sf"])
veto = vf < vctrl
claim("B", "sign veto: L8 feasible on the 9 untouched nf windows (3/9 = 33.3%) vs the larger control (random 3.3%, shifted 0.9%) -> no veto", "33.3% vs 3.3% -> no veto",
      f"{r1(vf)}% vs {r1(vctrl)}% -> {'VETO' if veto else 'no veto'}", ok=(V["n"] == 9 and r1(vf) == 33.3 and r1(vctrl) == 3.3 and not veto))


# ═════════════════════════════════════════════════════════════════════════════════════════════
# C. STOP (§6): the held-through table on the 62 undated untouched trades (58 records)
# ═════════════════════════════════════════════════════════════════════════════════════════════
say("\n## C. STOP")
FR = defaultdict(list)
for row in C["sn"].itertuples():
    names = set(x for x in str(row.symbols if isinstance(row.symbols, str) else "").split(",") if x) | set(x for x in str(row.blip_filled if isinstance(row.blip_filled, str) else "").split(",") if x)
    for s_ in names:
        FR[(row.date, s_)].append((int(row.idx), row.ctx, row.clock if isinstance(row.clock, str) else ""))


def my_last_in_session_clock(d, sym):
    fr = [x for x in FR.get((d, sym), ()) if x[1] == "in" and x[2]]
    return (max(fr)[2], max(fr, key=lambda x: hm(x[2]))[2]) if fr else (None, None)


def my_after_close_frame(d, sym):
    return any(x[1] == "closed" for x in FR.get((d, sym), ()))


recs_vu, d_vu = I.recs_for(IS["virgin_und"], M, store, guard0)
recs_vd, d_vd = I.recs_for(IS["virgin_dated"], M, store, guard0)
claim("C", "STOP records (mine, loader record builder): virgin undated 58 / virgin dated 26", "58 / 26", f"{len(recs_vu)} / {len(recs_vd)}", ok=(len(recs_vu) == 58 and len(recs_vd) == 26))
stop_t = {int(r["eid"]): r for r in stop_df.to_dict("records")}


def sma_trailing(c, n):
    c = np.asarray(c, dtype=float)
    out = np.full(len(c), np.nan)
    if len(c) >= n:
        cs = np.cumsum(np.insert(c, 0, 0.0))
        out[n - 1:] = (cs[n:] - cs[:-n]) / n
    return out


def own_off(rec, d):
    """Session offset of date d from the buy day on the record's OWN calendar (a bisect); asserts d is a session of it."""
    must_not_exceed(d)
    dd = date.fromisoformat(d)
    ci = bisect.bisect_left(rec.cal, dd)
    assert ci < len(rec.cal), f"{d} beyond the record's calendar"
    return (ci - rec.e_ci), rec.cal[ci] == dd


def sess_date(rec, j):
    k = rec.e_ci + j
    return rec.cal[k].isoformat() if 0 <= k < len(rec.cal) else None


def mb_of(rec, j):
    d = sess_date(rec, j)
    if d is None:
        return None
    must_not_exceed(d)
    return store.get(d, I.bar_sym(d, rec.b.sym_a, rec.b.sym), rec.b)


def preload_range(recs, j_from, j_to_fn):
    pairs = []
    for r in recs:
        jt = j_to_fn(r)
        if jt is None:
            continue
        for j in range(j_from, jt + 1):
            d = sess_date(r, j)
            if d is not None:
                must_not_exceed(d)
                pairs.append((d, I.bar_sym(d, r.b.sym_a, r.b.sym), r.b))
    return store.preload(pairs)


def first_touch(mb, L, after=-1):
    if mb is None:
        return None
    mn, ll, oo = np.asarray(mb.minute), np.asarray(mb.l), np.asarray(mb.o)
    ix = np.flatnonzero((mn > after) & ((ll <= L) | (oo < L)))
    return int(mn[ix[0]]) if len(ix) else None


def recs_info(rec):
    """my own offsets, fill checks, flags for one record"""
    b = rec.b
    lo_j, lo_ok = own_off(rec, b.exit_lo) if b.exit_lo else (None, True)
    hi_j, hi_ok = own_off(rec, b.exit_hi) if b.exit_hi else (None, True)
    return lo_j, hi_j, lo_ok and hi_ok


offs_bad, snapped = [], 0
for r in recs_vu:
    lo_j, hi_j, ok_ = recs_info(r)
    t = stop_t[r.b.eid]
    snapped += (not ok_)
    if lo_j != int(t["exit_lo_j"]) or hi_j != int(t["exit_hi_j"]):
        offs_bad.append((r.b.sym, r.b.E, lo_j, hi_j, t["exit_lo_j"], t["exit_hi_j"]))
claim("C", "L2 sell-window offsets (bisect on each record's OWN calendar) == TSV exit_lo_j/exit_hi_j on the 58; every exit date is a session", "58 rows", f"{58 - len(offs_bad)} equal, {snapped} snapped", ok=(not offs_bad and snapped == 0))
era_b = [r for r in recs_vu if r.era == "B"]
diff_cal, diff_names = 0, []
for r in [x for x in recs_vu + recs_vd if x.b.exit_hi]:
    lo_j, hi_j, _ = recs_info(r)
    ci0 = bisect.bisect_left(cal, r.b.E)
    ci1 = bisect.bisect_left(cal, r.b.exit_hi)
    if (ci1 - ci0) != hi_j:
        diff_cal += 1
        diff_names.append(f"{r.b.sym} {r.b.E} era {r.era} (own {hi_j} vs unified {ci1 - ci0})")
claim("C", "era-B offset defect: exit_hi offset on the record's own calendar vs the unified main calendar (virgin undated + dated records, 18 era-B among 89)", "own calendar used (defect fixed)",
      f"{len(era_b)} era-B undated records; {diff_cal} of {sum(1 for x in recs_vu + recs_vd if x.b.exit_hi)} offsets (records with an exit) differ own-vs-unified: " + "; ".join(diff_names), ok=True, info=True,
      note="informational: 0 differences = the own calendar and the unified calendar agree on the virgin block, so the old 1,445-1,569 session offset defect does not recur there")

# S-level inputs and fills
preload_range(recs_vu, 0, lambda r: own_off(r, r.b.exit_hi)[0])
fill_bad, lvl_bad, flag_bad = [], [], []
slip = []
STOPS = {}
for r in recs_vu:
    b, t = r.b, stop_t[r.b.eid]
    assert t["fill_src"] == "open" and int(t["fill_minute"]) == 0 and not b.dated
    slip.append(float(t["fill"]) / float(r.bars.o[r.e]) - 1.0)
    fill = float(t["fill"])
    mb = r.mb
    rm = hm(b.first_clock) if (b.first_clock and b.f_ctx == "in" and hm(b.first_clock) is not None and hm(b.first_clock) >= 0) else 0
    S1 = float(r.bars.l[r.e])
    S3 = float(r.bars.l[r.p])
    S9, S9s1 = S1, True
    S10, S10s1 = S1, True
    if mb is not None and rm >= 30:
        mn_, ll_ = np.asarray(mb.minute), np.asarray(mb.l)
        if (mn_ <= 29).any():
            S9, S9s1 = float(ll_[mn_ <= 29].min()), False
        done = [x for x in h60_mine(mb, b.E) if x is not None and x["hi"] < rm]
        if done:
            S10, S10s1 = done[-1]["l"], False
    S8 = fill * (1.0 - 2.0 * float(t["adr20"]))
    sma50 = sma_trailing(r.bars.c, 50)
    STOPS[b.eid] = dict(S1=S1, S3=S3, S9=S9, S10=S10, S8=S8, SMA50=sma50, S9s1=S9s1, S10s1=S10s1, rm=rm, fill=fill)
    if abs(float(r.adr20) - float(t["adr20"])) > 1e-12:
        fill_bad.append((b.sym, b.E, "adr20"))
    if int(float(t["read_minute"])) != rm:
        flag_bad.append((b.sym, b.E, "read_minute", t["read_minute"], rm))
    if bool(t["S9_is_S1"]) != S9s1 or bool(t["S10_is_S1"]) != S10s1 or not bool(t["S1_is_S2"]):
        flag_bad.append((b.sym, b.E, "flags", t["S9_is_S1"], S9s1, t["S10_is_S1"], S10s1))
    for nm_, v_ in (("S1", S1), ("S3", S3), ("S9", S9), ("S10", S10), ("S8", S8)):
        tv = t[f"{nm_}_level0"]
        if abs(float(tv) - v_) > 1e-9 * max(1, abs(v_)):
            lvl_bad.append((b.sym, b.E, nm_, tv, v_))
    tv = t["SMA50_level0"]
    if not ((np.isnan(float(tv)) and np.isnan(sma50[r.e])) or abs(float(tv) - sma50[r.e]) < 1e-9 * max(1, abs(sma50[r.e]))):
        lvl_bad.append((b.sym, b.E, "SMA50", tv, sma50[r.e]))
claim("C", "L2 fill = daily open x (1 + slippage) on every undated record (constant ratio), fill_minute 0, fill_src 'open', S1_is_S2", "58 open fills",
      f"slippage min {min(slip):.6f} max {max(slip):.6f}", ok=(max(slip) - min(slip) < 1e-9), note="the 0.1% slippage constant is the frozen H.undated_entry's")
claim("C", "L2 ADR20 on the 58 (loader) == TSV adr20", 0, len(fill_bad))
claim("C", "L2 read minute / S9_is_S1 / S10_is_S1 flags re-derived from first_clock+f_ctx and the buy-day minutes == TSV", "0 differ", f"{len(flag_bad)} differ", ok=(not flag_bad), note=str(flag_bad[:3]))
claim("C", "L2 level-0 prices S1,S3,S9,S10,S8,SMA50 re-derived (daily export lows / minute lows / h60 bars / fill) == TSV", "0 differ", f"{len(lvl_bad)} differ", ok=(not lvl_bad), note=str(lvl_bad[:3]))
claim("C", "'differ from S1' counts (S9, S10) = records with S9/S10 != S1", "22 / 22",
      f"{sum(1 for e in STOPS if not STOPS[e]['S9s1'])} / {sum(1 for e in STOPS if not STOPS[e]['S10s1'])}",
      ok=(sum(1 for e in STOPS if not STOPS[e]["S9s1"]) == 22 and sum(1 for e in STOPS if not STOPS[e]["S10s1"]) == 22))


def my_held(rec, name, V):
    """The doc's §6a held-through, rewritten from the registration text: -> dict(any, certain, unres, first_j, event_m, no_bar)."""
    b, t = rec.b, stop_t[rec.b.eid]
    st = STOPS[b.eid]
    day_low = (name == "S1") or (name in ("S9", "S10") and st[name + "s1"] if name in ("S9", "S10") else False) or name == "S1"
    if name in ("S9", "S10"):
        day_low = st["S9s1"] if name == "S9" else st["S10s1"]
    j0 = 1 if (V == "T" and day_low) else 0
    lo_j, hi_j = int(t["exit_lo_j"]), int(t["exit_hi_j"])
    J = hi_j
    out = dict(any=False, certain=False, unres=False, first_j=None, event_m=None, no_bar=0)
    first_m = hm(b.first_clock) if (b.first_clock and b.f_ctx == "in") else None
    if first_m is not None and first_m < 0:
        first_m = None
    flat_m = hm(b.flat_clock) if b.flat_clock else None
    if flat_m is not None and flat_m < 0:
        flat_m = None
    fill_min = 0
    for j in range(j0, J + 1):
        k = rec.e + j
        if not (k < len(rec.cidx) and int(rec.cidx[k]) == rec.e_ci + j):
            break
        if name == "SMA50":
            L = st["SMA50"][k]
        elif name == "S8":
            L = st["S8"]
        else:
            L = st[name]
        if not np.isfinite(L):
            continue
        through, m = False, None
        if V == "C":
            through = float(rec.bars.c[k]) < L
        elif V == "T":
            if j == 0:
                mb0 = rec.mb
                if mb0 is not None:
                    lower = max(fill_min, flat_m if flat_m is not None else -1)
                    m = first_touch(mb0, L, lower)
                    through = m is not None
                else:
                    through = float(rec.bars.l[k]) <= L
            else:
                through = float(rec.bars.l[k]) <= L
                if through and j == lo_j:
                    m = first_touch(mb_of(rec, j), L)
        else:
            mbj = rec.mb if j == 0 else mb_of(rec, j)
            bars_j = h60_mine(mbj, sess_date(rec, j)) if mbj is not None else None
            if bars_j is None:
                out["no_bar"] += 1
                continue
            if j == 0:
                lower = max(fill_min, flat_m if flat_m is not None else -1)
                cands = [x for x in bars_j if x is not None and x["close_m"] > lower]
            else:
                cands = [x for x in bars_j if x is not None]
            for x in cands:
                if x["c"] < L:
                    through, m = True, x["close_m"]
                    break
        if not through:
            continue
        out["any"] = True
        if out["first_j"] is None:
            out["first_j"] = j
        out["event_m"] = m
        if j == 0 and V != "C":
            if first_m is None or m is None:
                out["unres"] = True
            elif m >= first_m:
                if j == lo_j:
                    cl, _ = my_last_in_session_clock(b.exit_lo, b.sym)
                    out["certain"] = cl is not None and m < hm(cl)
                else:
                    out["certain"] = True
            else:
                out["unres"] = True
            break
        if j < lo_j:
            out["certain"] = True
            break
        if j == lo_j:
            if V == "C":
                out["certain"] = bool(my_after_close_frame(b.exit_lo, b.sym))
            else:
                cl, _ = my_last_in_session_clock(b.exit_lo, b.sym)
                if cl is None or m is None:
                    out["unres"] = True
                elif m < hm(cl):
                    out["certain"] = True
            break
        break
    return out


CELLS = [(n_, v_) for n_ in ("S1", "S3", "S9", "S10", "S8", "SMA50") for v_ in ("T", "C", "H")]
HELD = {}
bad_cells = []
for r in recs_vu:
    t = stop_t[r.b.eid]
    for (n_, v_) in CELLS:
        h = my_held(r, n_, v_)
        HELD[(r.b.eid, n_, v_)] = h
        pre = f"{n_}_{v_}"
        tv = (bool(t[f"{pre}_any"]), bool(t[f"{pre}_certain"]), bool(t[f"{pre}_unresolved"]))
        mv = (h["any"], h["certain"], h["unres"])
        fj = t[f"{pre}_first_j"]
        em = t[f"{pre}_event_m"]
        fj_ok = (isnull(fj) and h["first_j"] is None) or (not isnull(fj) and h["first_j"] == int(float(fj)))
        em_ok = (isnull(em) and h["event_m"] is None) or (not isnull(em) and h["event_m"] is not None and int(float(em)) == h["event_m"])
        if tv != mv or not fj_ok or not em_ok:
            bad_cells.append((r.b.sym, r.b.E, pre, tv, mv, fj, h["first_j"], em, h["event_m"]))
claim("C", f"L2 per record x 18 cells (S1,S3,S9,S10,S8,SMA50 x T,C,H): traded-through / certain / unresolved / first session / event minute re-derived from raw bars+frames == TSV",
      f"{58 * 18} cells", f"{58 * 18 - len(bad_cells)} equal, {len(bad_cells)} differ", ok=(not bad_cells), note="; ".join(str(x) for x in bad_cells[:4]))
# the alternative reading of 'the last in-session frame' (max clock instead of max idx) — does it ever bite on the exit_lo days used?
alt_diff = 0
for r in recs_vu:
    a_, b_ = my_last_in_session_clock(r.b.exit_lo, r.b.sym)
    alt_diff += int(a_ != b_)
claim("C", "last in-session frame on the exit_lo day: frame with the highest idx vs the highest clock (the code takes max idx) — differ on", "n/a", f"{alt_diff} of 58 records", ok=True, info=True,
      note="informational: if > 0 the certainty of a T/H touch on the sell day could depend on the choice")

# L1: re-aggregate the deciding column and compare with the printed table
tab_lines = [ln for ln in PR if re.match(r"^\s{2}(S\d+|SMA50)-[TCH]\s+\|", ln)]
claim("C", "printed deciding table rows", 18, len(tab_lines))
printed_tab = {}
for ln in tab_lines:
    cols = [x.strip() for x in ln.split("|")]
    printed_tab[cols[0]] = cols
dec_stop_ids = [r.b.eid for r in recs_vu]
tab_mine = {}
for (n_, v_) in CELLS:
    anyn = sum(HELD[(e, n_, v_)]["any"] for e in dec_stop_ids)
    cert = sum(HELD[(e, n_, v_)]["certain"] for e in dec_stop_ids)
    unr = sum(HELD[(e, n_, v_)]["unres"] for e in dec_stop_ids)
    widths = []
    for r in recs_vu:
        st = STOPS[r.b.eid]
        L0 = st["SMA50"][r.e] if n_ == "SMA50" else st[n_]
        if np.isfinite(L0):
            widths.append((st["fill"] - L0) / st["fill"])
    differ = sum(1 for e in dec_stop_ids if (not STOPS[e][n_ + "s1"])) if n_ in ("S9", "S10") else len(dec_stop_ids)
    nobar = sum(HELD[(e, n_, v_)]["no_bar"] > 0 for e in dec_stop_ids)
    tab_mine[(n_, v_)] = dict(any=anyn, cert=cert, unr=unr, hcond=(cert / anyn if anyn else float("nan")), hall=cert / len(dec_stop_ids), tight=float(np.median(widths)), elig=anyn >= 20,
                              differ=differ, nobar=nobar)
for (n_, v_), mv in tab_mine.items():
    cols = printed_tab[f"{n_}-{v_}"]
    pf = lambda s: float(s.rstrip("%"))
    claim("C", f"[{n_}-{v_}] tightness / traded through / certain / unresolved", f"{cols[1]} / {cols[2]} / {cols[3]} / {cols[4]}", f"{r1(mv['tight']).__format__('.1f')}% / {mv['any']} / {mv['cert']} / {mv['unr']}")
    claim("C", f"[{n_}-{v_}] H_cond / H_all / eligible / differ", f"{cols[5]} / {cols[6]} / {cols[7]} / {cols[8]}", f"{r1(mv['hcond']):.1f}% / {r1(mv['hall']):.1f}% / {mv['elig']} / {mv['differ'] if n_ in ('S9','S10') else '-'}"
          if not (n_ in ("S9", "S10")) else f"{r1(mv['hcond']):.1f}% / {r1(mv['hall']):.1f}% / {mv['elig']} / {mv['differ']}")
    # differ from S1 is '-' in the printout for S1/S3/S8/SMA50 cells and the count for S9/S10; the line above handles both
    if n_ in ("S1", "S3", "S8", "SMA50"):
        pass

# ---- beside columns re-aggregated from the TSV (L1) and the fit column (JSON + fit TSV)
hdr_cols = None
for ln in PR:
    if ln.strip().startswith("level-variant"):
        hdr_cols = [x.strip() for x in ln.split("|")]
sets_beside = {
    "virgin dated 27": {b.eid for b in IS["virgin_dated"]},
    "2021-22 undated 226": {b.eid for b in IS["chk22_und"]},
    "nf": {b.eid for b in IS["chk22_und"] if not b.flicker},
    "untouched-by-path": {b.eid for b in IS["chk22_und"] if not b.in_dated_path},
    "2021-22 dated 111": {b.eid for b in IS["chk22_dated"]},
}
col_of = {nm: hdr_cols.index(nm) for nm in list(sets_beside) + ["fit H_cond"]}
n_bad = 0
for nm, ids in sets_beside.items():
    sub = stop_df[stop_df.eid.isin(ids)]
    for (n_, v_) in CELLS:
        pre = f"{n_}_{v_}"
        a_ = int(sub[f"{pre}_any"].astype(bool).sum())
        c_ = int(sub[f"{pre}_certain"].astype(bool).sum())
        mine_h = (c_ / a_) if a_ else float("nan")
        pv = printed_tab[f"{n_}-{v_}"][col_of[nm]]
        mv = f"{r1(mine_h):.1f}%" if a_ else "-"
        if pv != mv:
            n_bad += 1
            say(f"  !! beside [{nm}] {n_}-{v_}: printed {pv} mine {mv}")
claim("C", "L1 beside columns (virgin dated 27, 2021-22 undated 226, nf, untouched-by-path, 2021-22 dated 111) H_cond re-aggregated from the TSV x 18 cells", f"{5 * 18} numbers", f"{5 * 18 - n_bad} equal", ok=(n_bad == 0))
_sz = (len(stop_df[stop_df.eid.isin(sets_beside['2021-22 undated 226'])]), len(stop_df[stop_df.eid.isin(sets_beside['2021-22 dated 111'])]), len(stop_df[stop_df.eid.isin(sets_beside['virgin dated 27'])]))
claim("C", "beside set sizes in the TSV (records): 2021-22 undated / dated / virgin dated", "212 / 110 / 26", " / ".join(map(str, _sz)), ok=(_sz == (212, 110, 26)))
fit_json = json.load(open(f"{OUTD}/stop_fit_chosen.json"))["object"]
fit_tab = fit_json["fit_table"]
fit_df = pd.read_csv(f"{OUTD}/stop_fit_trades.tsv", sep="\t")
n_bad = 0
for (n_, v_) in CELLS:
    pre = f"{n_}_{v_}"
    a_ = int(fit_df[f"{pre}_any"].astype(bool).sum())
    c_ = int(fit_df[f"{pre}_certain"].astype(bool).sum())
    jh = fit_tab[f"{n_}-{v_}"]
    pv = printed_tab[f"{n_}-{v_}"][col_of["fit H_cond"]]
    if not (jh["any"] == a_ and jh["certain"] == c_ and pv == f"{r1(jh['H_cond']):.1f}%" and abs(jh["H_cond"] - c_ / a_) < 1e-12):
        n_bad += 1
        say(f"  !! fit [{n_}-{v_}] json any/cert {jh['any']}/{jh['certain']} tsv {a_}/{c_} printed {pv}")
claim("C", "L1 fit column: stop_fit_chosen.json fit_table == re-aggregation of stop_fit_trades.tsv == the printed 'fit H_cond' x 18 cells", "18 cells", f"{18 - n_bad} equal", ok=(n_bad == 0))
claim("C", "fit TSV population (records)", fit_tab["S1-T"]["n"], len(fit_df))
# the choose rule: tightest (level, variant) with positive width, >=20 traded through, H_cond <= 10% on the fit (S8 / SMA50 never)
cands = [(f"{l_}-{v_}", fit_tab[f"{l_}-{v_}"]["H_cond"], fit_tab[f"{l_}-{v_}"]["any"]) for l_ in ("S1", "S3", "S9", "S10") for v_ in ("T", "C", "H")
         if fit_tab[f"{l_}-{v_}"]["eligible"] and fit_tab[f"{l_}-{v_}"]["H_cond"] <= 0.10 and fit_tab[f"{l_}-{v_}"]["tight"] > 0]
best = min((fit_tab[f"{l_}-{v_}"]["H_cond"], f"{l_}-{v_}") for l_ in ("S1", "S3", "S9", "S10") for v_ in ("T", "C", "H"))
claim("C", "STOP chosen cell on the fit = none (no S1/S3/S9/S10 cell with >=20 traded through, positive width and H_cond <= 10%)", "none -> INCONCLUSIVE",
      f"{'none' if not cands else cands} (lowest fit H_cond among the 12 cells {r1(best[0]):.1f}% at {best[1]})", ok=(not cands))
claim("C", "STOP verdict (chosen None) = INCONCLUSIVE; the check table alone cannot produce it", "INCONCLUSIVE", "INCONCLUSIVE" if not cands else "PASS/FAIL possible", ok=(not cands))
# the verdict would NOT have changed on the deciding column even if a cell had been chosen: the lowest check H_cond among cells with >= 20 traded through
elig_chk = [(tab_mine[(l_, v_)]["hcond"], f"{l_}-{v_}") for l_ in ("S1", "S3", "S9", "S10") for v_ in ("T", "C", "H") if tab_mine[(l_, v_)]["elig"]]
claim("C", "informational: lowest H_cond on the 58 among eligible 12 cells", "20.0% (S1-C) / 21.7% (S1-H)", f"{r1(min(elig_chk)[0]):.1f}% ({min(elig_chk)[1]})", ok=(r1(min(elig_chk)[0]) == 20.0),
      note="no cell is near the 15% pass bar on the deciding set either")
# Spearman beside: 6 cells (S9/S10 equal S1 on > half their records are left out)
used = [(l_, v_) for l_ in ("S1", "S3") for v_ in ("T", "C", "H")]
fx = pd.Series([fit_tab[f"{l_}-{v_}"]["H_cond"] for l_, v_ in used]).rank(method="average")
cx = pd.Series([tab_mine[(l_, v_)]["hcond"] for l_, v_ in used]).rank(method="average")
rho = float(np.corrcoef(fx, cx)[0, 1])
claim("C", "beside: Spearman of the cells' H_cond order, fit vs deciding (S9/S10 left out: S1 on > half their records)", "-0.75 on 6 cells", f"{rho:.2f} on {len(used)} cells", ok=(round(rho, 2) == -0.75 and len(used) == 6))
# re-buys apart
rb = [r for r in recs_vu if stop_t[r.b.eid]["rebuy"] in (True, "True")]
line = [ln for ln in PR if ln.startswith("- re-buys among the deciding")][0]
nrb = int(re.search(r"deciding \((\d+)\)", line).group(1))
claim("C", "re-buys among the deciding: count", nrb, len(rb))
bad_rb = []
for m_ in re.finditer(r"(S\d+-[TCH]) H_cond ([\d.]+)%", line):
    cell = m_.group(1)
    n_, v_ = cell.split("-")
    a_ = sum(HELD[(r.b.eid, n_, v_)]["any"] for r in rb)
    c_ = sum(HELD[(r.b.eid, n_, v_)]["certain"] for r in rb)
    if f"{r1(c_ / a_):.1f}" != m_.group(2):
        bad_rb.append((cell, m_.group(2), c_, a_))
claim("C", "re-buys apart: 12 cells' H_cond re-derived from my held-through", "12 cells", f"{12 - len(bad_rb)} equal", ok=(not bad_rb), note=str(bad_rb))


# ---- C2. the FIT column re-derived from bars (the verdict INCONCLUSIVE hangs on it): 415 fit records x 18 cells, general fill (undated open / ORH5 / close proxy / level:L8)
say("\n## C2. STOP fit column re-derived from raw bars")
fit_buys = [buys_by_eid[int(e)] for e in fit_df.eid]
recs_fit, d_fit = I.recs_for(fit_buys, M, store, guard0)
claim("C", "fit records (loader record builder) == fit TSV rows == JSON fit_table n", f"{len(fit_df)} / {fit_tab['S1-T']['n']}", f"{len(recs_fit)}", ok=(len(recs_fit) == len(fit_df) == fit_tab["S1-T"]["n"]))
fit_t = {int(r["eid"]): r for r in fit_df.to_dict("records")}
preload_range(recs_fit, 0, lambda r: own_off(r, r.b.exit_hi)[0])


def ctx_for(rec, fill, fm, fsrc, adr20):
    b, mb = rec.b, rec.mb
    s1m = fm if (fsrc.startswith(("level", "orh5")) and fm is not None) else None
    if mb is not None and s1m is not None:
        sel = np.asarray(mb.minute) <= s1m
        S1 = float(np.asarray(mb.l)[sel].min()) if sel.any() else float(rec.bars.l[rec.e])
        s1s2 = not sel.any()
    else:
        S1, s1s2 = float(rec.bars.l[rec.e]), True
    rm = hm(b.first_clock) if (b.first_clock and b.f_ctx == "in" and hm(b.first_clock) is not None and hm(b.first_clock) >= 0) else fm
    S9, S9s1, S10, S10s1 = S1, True, S1, True
    if mb is not None and rm is not None and rm >= 30:
        mn_, ll_ = np.asarray(mb.minute), np.asarray(mb.l)
        if (mn_ <= 29).any():
            S9, S9s1 = float(ll_[mn_ <= 29].min()), False
        done = [x for x in h60_mine(mb, b.E) if x is not None and x["hi"] < rm]
        if done:
            S10, S10s1 = done[-1]["l"], False
    return dict(fill=fill, fm=fm, S1=S1, S1_is_S2=s1s2, S3=float(rec.bars.l[rec.p]), S9=S9, S10=S10, S9s1=S9s1, S10s1=S10s1, S8=fill * (1.0 - 2.0 * adr20),
                SMA50=sma_trailing(rec.bars.c, 50), rm=rm)


def held_g(rec, name, V, cx, lo_j, hi_j):
    b = rec.b
    if name == "S1":
        day_low = cx["S1_is_S2"]
    elif name in ("S9", "S10"):
        day_low = cx["S1_is_S2"] and cx[name + "s1"]
    else:
        day_low = False
    j0 = 1 if (V == "T" and day_low) else 0
    out = dict(any=False, certain=False, unres=False, first_j=None, event_m=None, no_bar=0)
    first_m = hm(b.first_clock) if (b.first_clock and b.f_ctx == "in") else None
    if first_m is not None and first_m < 0:
        first_m = None
    flat_m = hm(b.flat_clock) if b.flat_clock else None
    if flat_m is not None and flat_m < 0:
        flat_m = None
    fm = cx["fm"]
    for j in range(j0, hi_j + 1):
        k = rec.e + j
        if not (k < len(rec.cidx) and int(rec.cidx[k]) == rec.e_ci + j):
            break
        L = cx["SMA50"][k] if name == "SMA50" else cx[name]
        if not np.isfinite(L):
            continue
        through, m = False, None
        if V == "C":
            through = float(rec.bars.c[k]) < L
        elif V == "T":
            if j == 0:
                if rec.mb is not None and fm is not None:
                    m = first_touch(rec.mb, L, max(fm, flat_m if flat_m is not None else -1))
                    through = m is not None
                elif fm == 0:
                    through = float(rec.bars.l[k]) <= L
                else:
                    if float(rec.bars.l[k]) <= L:
                        out["unres"] = True
                    continue
            else:
                through = float(rec.bars.l[k]) <= L
                if through and j == lo_j:
                    m = first_touch(mb_of(rec, j), L)
        else:
            mbj = rec.mb if j == 0 else mb_of(rec, j)
            bars_j = h60_mine(mbj, sess_date(rec, j)) if mbj is not None else None
            if bars_j is None:
                out["no_bar"] += 1
                continue
            if j == 0:
                if fm is None:
                    continue
                lower = max(fm, flat_m if flat_m is not None else -1)
                cands = [x for x in bars_j if x is not None and x["close_m"] > lower]
            else:
                cands = [x for x in bars_j if x is not None]
            for x in cands:
                if x["c"] < L:
                    through, m = True, x["close_m"]
                    break
        if not through:
            continue
        out["any"] = True
        if out["first_j"] is None:
            out["first_j"] = j
        out["event_m"] = m
        if j == 0 and V != "C":
            if first_m is None or m is None:
                out["unres"] = True
            elif m >= first_m:
                if j == lo_j:
                    cl, _ = my_last_in_session_clock(b.exit_lo, b.sym)
                    out["certain"] = cl is not None and m < hm(cl)
                else:
                    out["certain"] = True
            else:
                out["unres"] = True
            break
        if j < lo_j:
            out["certain"] = True
            break
        if j == lo_j:
            if V == "C":
                out["certain"] = bool(my_after_close_frame(b.exit_lo, b.sym))
            else:
                cl, _ = my_last_in_session_clock(b.exit_lo, b.sym)
                if cl is None or m is None:
                    out["unres"] = True
                elif m < hm(cl):
                    out["certain"] = True
            break
        break
    return out


# the generalisation must reproduce the 58-record result exactly before it is trusted on the fit
gen_bad = 0
for r in recs_vu:
    t = stop_t[r.b.eid]
    cx = ctx_for(r, float(t["fill"]), 0, "open", float(t["adr20"]))
    lo_j, hi_j = own_off(r, r.b.exit_lo)[0], own_off(r, r.b.exit_hi)[0]
    for (n_, v_) in CELLS:
        g_ = held_g(r, n_, v_, cx, lo_j, hi_j)
        h_ = HELD[(r.b.eid, n_, v_)]
        gen_bad += int((g_["any"], g_["certain"], g_["unres"]) != (h_["any"], h_["certain"], h_["unres"]))
claim("C", "C2 cross-check: the generalised held-through (any fill type) reproduces the 58-record cells exactly", "0 differ", f"{gen_bad} differ of {58 * 18}", ok=(gen_bad == 0))
FIT_HELD, fit_bad, fit_lvl_bad, fit_flag_bad, fit_off_bad = {}, [], [], [], []
fit_ctx = {}
for r in recs_fit:
    t = fit_t[r.b.eid]
    fm = None if isnull(t["fill_minute"]) else int(float(t["fill_minute"]))
    cx = ctx_for(r, float(t["fill"]), fm, t["fill_src"], float(t["adr20"]))
    fit_ctx[r.b.eid] = cx
    lo_j, hi_j = own_off(r, r.b.exit_lo)[0], own_off(r, r.b.exit_hi)[0]
    if lo_j != int(t["exit_lo_j"]) or hi_j != int(t["exit_hi_j"]):
        fit_off_bad.append(r.b.eid)
    if bool(t["S1_is_S2"]) != cx["S1_is_S2"] or bool(t["S9_is_S1"]) != cx["S9s1"] or bool(t["S10_is_S1"]) != cx["S10s1"] or (isnull(t["read_minute"]) != (cx["rm"] is None)) \
            or (cx["rm"] is not None and int(float(t["read_minute"])) != cx["rm"]):
        fit_flag_bad.append((r.b.eid, r.b.sym, r.b.E))
    for nm_ in ("S1", "S3", "S9", "S10", "S8"):
        if abs(float(t[f"{nm_}_level0"]) - cx[nm_]) > 1e-9 * max(1, abs(cx[nm_])):
            fit_lvl_bad.append((r.b.eid, nm_))
    for (n_, v_) in CELLS:
        h = held_g(r, n_, v_, cx, lo_j, hi_j)
        FIT_HELD[(r.b.eid, n_, v_)] = h
        pre = f"{n_}_{v_}"
        tv = (bool(t[f"{pre}_any"]), bool(t[f"{pre}_certain"]), bool(t[f"{pre}_unresolved"]))
        fj, em = t[f"{pre}_first_j"], t[f"{pre}_event_m"]
        fj_ok = (isnull(fj) and h["first_j"] is None) or (not isnull(fj) and h["first_j"] == int(float(fj)))
        em_ok = (isnull(em) and h["event_m"] is None) or (not isnull(em) and h["event_m"] is not None and int(float(em)) == h["event_m"])
        if tv != (h["any"], h["certain"], h["unres"]) or not fj_ok or not em_ok:
            fit_bad.append((r.b.sym, r.b.E, pre, tv, (h["any"], h["certain"], h["unres"]), fj, h["first_j"], em, h["event_m"]))
claim("C", "C2 fit sell-window offsets (own calendar) == fit TSV", "0 differ", f"{len(fit_off_bad)} differ", ok=(not fit_off_bad))
claim("C", "C2 fit S1/S3/S9/S10/S8 level-0 prices and the S1_is_S2 / S9_is_S1 / S10_is_S1 / read-minute flags re-derived == fit TSV (fill, fill minute, source taken from the fit TSV as inputs: the chain's L8 / ORH5 / open fill is ENTER's output, not recounted here)",
      "0 differ", f"{len(fit_lvl_bad)} levels, {len(fit_flag_bad)} flags differ", ok=(not fit_lvl_bad and not fit_flag_bad), note=str((fit_lvl_bad + fit_flag_bad)[:3]))
claim("C", f"C2 fit L2: {len(recs_fit)} records x 18 cells (traded through / certain / unresolved / first session / event minute) re-derived from bars+frames == fit TSV", f"{len(recs_fit) * 18} cells",
      f"{len(recs_fit) * 18 - len(fit_bad)} equal, {len(fit_bad)} differ", ok=(not fit_bad), note="; ".join(str(x) for x in fit_bad[:3]))
fit_mine = {}
n_bad = 0
for (n_, v_) in CELLS:
    a_ = sum(FIT_HELD[(e, n_, v_)]["any"] for e in fit_ctx)
    c_ = sum(FIT_HELD[(e, n_, v_)]["certain"] for e in fit_ctx)
    u_ = sum(FIT_HELD[(e, n_, v_)]["unres"] for e in fit_ctx)
    widths = []
    for r in recs_fit:
        cx = fit_ctx[r.b.eid]
        L0 = cx["SMA50"][r.e] if n_ == "SMA50" else cx[n_]
        if np.isfinite(L0):
            widths.append((cx["fill"] - L0) / cx["fill"])
    tight = float(np.median(widths))
    jh = fit_tab[f"{n_}-{v_}"]
    differ = sum(1 for e in fit_ctx if not fit_ctx[e][n_ + "s1"]) if n_ in ("S9", "S10") else len(fit_ctx)
    ok_ = (jh["any"] == a_ and jh["certain"] == c_ and jh["unresolved"] == u_ and abs(jh["tight"] - tight) < 1e-12 and jh["eligible"] == (a_ >= 20)
           and abs(jh["H_cond"] - c_ / a_) < 1e-12 and jh["differ"] == differ)
    fit_mine[(n_, v_)] = (a_, c_, c_ / a_, tight)
    if not ok_:
        n_bad += 1
        say(f"  !! fit json [{n_}-{v_}] {jh} mine any {a_} cert {c_} unres {u_} tight {tight} differ {differ}")
claim("C", "C2 fit table (18 cells: n, traded through, certain, unresolved, H_cond, median width, eligible, differ) from MY cells == stop_fit_chosen.json", "18 cells", f"{18 - n_bad} equal", ok=(n_bad == 0))
cands2 = [(f"{l_}-{v_}", fit_mine[(l_, v_)][2]) for l_ in ("S1", "S3", "S9", "S10") for v_ in ("T", "C", "H") if fit_mine[(l_, v_)][0] >= 20 and fit_mine[(l_, v_)][2] <= 0.10 and fit_mine[(l_, v_)][3] > 0]
low2 = min((fit_mine[(l_, v_)][2], f"{l_}-{v_}") for l_ in ("S1", "S3", "S9", "S10") for v_ in ("T", "C", "H"))
claim("C", "C2 STOP chosen cell on the fit from MY recomputed fit table = none (lowest fit H_cond among the 12 cells)", "none -> INCONCLUSIVE", f"{'none' if not cands2 else cands2} (lowest {r1(low2[0]):.1f}% at {low2[1]})", ok=(not cands2))


# ═════════════════════════════════════════════════════════════════════════════════════════════
# D. EXIT (§7): the 60-minute 20-EMA rule E1 on the dated 2021-22 trades; accounts; recovery; hit rate; vetoes; bootstrap
# ═════════════════════════════════════════════════════════════════════════════════════════════
say("\n## D. EXIT")
SLIP, MAXMIS = 0.001, 0.01
recs_22d_all, d22 = I.recs_for(IS["chk22_dated"], M, store, guard0)
dec_recs = [r for r in recs_22d_all if r.b.exit_hi]
claim("D", "EXIT deciding records (2021-22 dated with an exit, after the 50-bar floor)", 110, len(dec_recs))
CAL_DATES = [date.fromisoformat(d) for d in cal]
CAP30 = I.CAP30
guards_of = lambda era: M["guards"].get(era, {}) if isinstance(M.get("guards"), dict) else {}


def my_registered(rec):
    """The registered fill and stop (chain with neither ENTER nor STOP passed), re-derived from raw minute bars + the daily export."""
    b, bars, e, mb = rec.b, rec.bars, rec.e, rec.mb
    fill = fm = src = None
    if b.dated:
        if mb is not None and len(mb) > 0 and b.pivot is not None:
            mn, hh, ll, oo = (np.asarray(x) for x in (mb.minute, mb.h, mb.l, mb.o))
            dh, dl = float(bars.h[e]), float(bars.l[e])
            pivot = float(b.pivot)
            pre = None
            if not dh > 0 or not dl > 0 or abs(hh.max() - dh) / dh > MAXMIS or abs(ll.min() - dl) / dl > MAXMIS:
                pre = "minute_daily_mismatch"
            elif hh.max() <= pivot:
                pre = "minute_high_below_pivot"
            if pre is None:
                inr = mn < 5
                if inr.any():
                    level = max(float(hh[inr].max()), pivot)
                    hits = np.flatnonzero((mn >= 5) & (hh > level))
                    if len(hits):
                        m = int(hits[0])
                        op = float(oo[m])
                        f_ = (level if op <= level else op) * (1.0 + SLIP)
                        s_ = float(ll[:m + 1].min())
                        if s_ < f_:
                            width = (f_ - s_) / f_
                            fill, fm = f_, int(mn[m])
                            src = "orh5_too_wide" if width > rec.adr20 else "orh5"
        if fill is None:
            fill, fm, src = float(bars.c[e]) * (1.0 + SLIP), None, "close_proxy"
    else:
        fill, fm, src = float(bars.o[e]) * (1.0 + SLIP), 0, "open"
    # the registered stop
    s1 = float(bars.l[e])
    if src.startswith("orh5") and mb is not None:
        sel = np.asarray(mb.minute) <= fm
        if sel.any():
            s1 = float(np.asarray(mb.l)[sel].min())
    if b.dated:
        stop, ssrc = s1, "S1-T"
    else:
        stop, ssrc = fill * (1.0 - rec.adr20), "ADR20-T"
    if not (np.isfinite(stop) and stop < fill):
        stop, ssrc = fill * (1.0 - rec.adr20), ssrc + "->ADR20"
    # day-0 stop after the fill (T): a minute after the fill minute opening under the stop (exit at that open) or with a low at it (exit at the stop)
    d0 = dict(cb._NO_DAY0)
    if fm is not None:
        if mb is not None:
            mn, ll, oo = np.asarray(mb.minute), np.asarray(mb.l), np.asarray(mb.o)
            hit = np.flatnonzero((mn > fm) & ((ll <= stop) | (oo < stop)))
            if len(hit):
                i = int(hit[0])
                d0 = {"stopped": True, "exit_price": float(oo[i]) if oo[i] < stop else float(stop), "exit_minute": int(mn[i])}
        elif fm == 0:
            if float(bars.l[e]) <= stop:
                d0 = {"stopped": True, "exit_price": float(stop), "exit_minute": None}
    return dict(fill=fill, fill_minute=fm, fill_src=src, stop=stop, stop_src=ssrc, day0=d0)


def build_items(rec, J_tail):
    items, missing = [], 0
    for j in range(-10, J_tail + 1):
        d = sess_date(rec, j)
        if d is None:
            break
        mbj = rec.mb if j == 0 else mb_of(rec, j)
        bars = h60_mine(mbj, d) if mbj is not None else None
        if bars is None:
            missing += 1
            continue
        for x in bars:
            if x is not None:
                items.append((j, x))
    return items, missing


def my_ema(closes, n=20, alpha=2.0 / 21.0):
    c = np.asarray(closes, dtype=float)
    out = np.full(len(c), np.nan)
    if len(c) >= n:
        out[n - 1] = c[:n].mean()
        for i in range(n, len(c)):
            out[i] = alpha * c[i] + (1 - alpha) * out[i - 1]
    return out


def my_exit_prep(rec):
    b = rec.b
    lo_j, _ = own_off(rec, b.exit_lo)
    hi_j, _ = own_off(rec, b.exit_hi)
    guards = guards_of(rec.era)
    bh, why = rev.break_horizon(rec, guards)         # frozen: the forward window cut at the first missing session / identity break
    J_tail = min(hi_j + 20, bh)
    return dict(lo_j=lo_j, hi_j=hi_j, bh=bh, why=why, J_tail=J_tail, guards=guards)


def my_e1_walk(rec, reg, prep, items, ema, armed):
    """E1 under the registered stop: per session the stop first (day-0 stop / gap open / low at the level), then the first armed 60-minute close
    under the EMA -> the NEXT present minute's open (the day's last bar -> the next session's open, booked j+1)."""
    legs = []
    out = dict(legs=legs, last_j=None, stop_preempt=False, cut="")
    stop = reg["stop"]
    armed_j = items[armed][0]
    for j in range(0, prep["J_tail"] + 1):
        k = rec.e + j
        if not (k < len(rec.cidx) and int(rec.cidx[k]) == rec.e_ci + j):
            kk = rec.e + j - 1
            legs.append(I.Leg(j - 1, None, float(rec.bars.c[kk]), "mark_hole", 1.0, I.ORDER_CLOSE))
            out["cut"] = "hole"
            break
        if j == 0:
            d0 = reg["day0"]
            if d0["stopped"]:
                px = float(d0["exit_price"])
                legs.append(I.Leg(0, d0["exit_minute"], px, "day0_gap" if px < stop else "day0_stop", 1.0, I.ORDER_INTRADAY))
                out["stop_preempt"] = True
                break
        else:
            if float(rec.bars.o[k]) < stop:
                legs.append(I.Leg(j, 0, float(rec.bars.o[k]), "stop_gap", 1.0, I.ORDER_OPEN))
                out["stop_preempt"] = True
                break
            if float(rec.bars.l[k]) <= stop:
                m = first_touch(mb_of(rec, j), stop)
                legs.append(I.Leg(j, m, stop, "stop", 1.0, I.ORDER_INTRADAY))
                out["stop_preempt"] = True
                break
        for i, (jj, x) in enumerate(items):
            if jj != j or i < armed:
                continue
            if np.isfinite(ema[i]) and x["c"] < ema[i]:
                mbj = rec.mb if j == 0 else mb_of(rec, j)
                d = sess_date(rec, j)
                mn, oo = trim(mbj, d)[0], trim(mbj, d)[1]
                nxt = np.flatnonzero(mn > x["close_m"])
                if len(nxt):
                    legs.append(I.Leg(j, x["close_m"], float(oo[nxt[0]]), "e1", 1.0, I.ORDER_INTRADAY))
                else:
                    kn = k + 1
                    if kn < len(rec.cidx) and int(rec.cidx[kn]) == rec.e_ci + j + 1:
                        legs.append(I.Leg(j + 1, None, float(rec.bars.o[kn]), "e1", 1.0, I.ORDER_OPEN))
                    else:
                        legs.append(I.Leg(j, None, float(rec.bars.c[k]), "e1", 1.0, I.ORDER_CLOSE))
                break
        if legs:
            break
    if not legs:
        kJ = rec.e + prep["J_tail"]
        legs.append(I.Leg(prep["J_tail"], None, float(rec.bars.c[kJ]), "cut_at_tail", 1.0, I.ORDER_CLOSE))
        out["cut"] = out["cut"] or "tail"
    out["last_j"] = max(lg.j for lg in legs)
    return out


def exit_pipeline(recs, label, tsv=None, w0=None, boot=False):
    """-> dict(finals, recovery, hit rate, counts ...) with every per-trade quantity re-derived here."""
    prows = []
    cnt = Counter()
    ours, chosen, his = [], [], []
    hits = scor = 0
    row_bad = []
    for r in recs:
        b = r.b
        reg = my_registered(r)
        prep = my_exit_prep(r)
        r.fill, r.fill_minute, r.stop, r.day0 = reg["fill"], reg["fill_minute"], reg["stop"], reg["day0"]
        r.fill_src, r.stop_src = reg["fill_src"], reg["stop_src"]
        r.exit_lo_j, r.exit_hi_j = prep["lo_j"], prep["hi_j"]
        items, missing = build_items(r, prep["J_tail"])
        closes = np.array([x["c"] for _, x in items])
        ema = my_ema(closes)
        armed = None
        for i, (jj, x) in enumerate(items):
            if jj < 0:
                continue
            if jj == 0:
                if r.fill_minute is not None and x["hi"] > r.fill_minute:
                    armed = i
                    break
                continue
            armed = i
            break
        thin = armed is None or armed < 20 + 45
        info = dict(eid=b.eid, items=items, ema=ema, armed=armed, thin=thin, missing=missing, prep=prep, reg=reg)
        prows.append(info)
        if armed is None:
            cnt["no_armed_bar"] += 1
            continue
        if thin:
            cnt["ema_thin"] += 1
            continue
        w = my_e1_walk(r, reg, prep, items, ema, armed)
        info["walk"] = w
        width = (r.fill - r.stop) / r.fill
        if not width > 0:
            cnt["stop_at_or_above_fill"] += 1
            continue
        tail_kind = "cut_at_tail" if prep["J_tail"] == prep["hi_j"] + 20 else ("mark_break" if prep["why"] == "break" else "mark_hole" if prep["why"] == "hole" else "cut_at_horizon")
        t_c = I.make_legs_trade(r, w["legs"], width, M["map_b"], len(cal))
        t_o = rev.speed_trail_trade(r, M, prep["guards"])
        t_h = rev.panel_trade(r, M["map_b"], len(cal), max_j=prep["bh"], cut_kind=tail_kind if tail_kind != "cut_at_tail" else "mark_hole")
        if t_o is None or t_c is None or t_h is None:
            cnt["unbuildable"] += 1
            continue
        cnt["trades"] += 1
        cnt["stop_preempt"] += int(w["stop_preempt"])
        cnt["cut_at_tail"] += int(any(lg.kind == "cut_at_tail" for lg in w["legs"]))
        cnt["cut_other"] += int(any(lg.kind in ("mark_hole", "mark_break", "cut_at_horizon", "cut_at_data_end") for lg in w["legs"]))
        ours.append(t_o); chosen.append(t_c); his.append(t_h)
        # hit rate: the LAST leg's booked session inside [exit_lo_j, exit_hi_j] on windows <= 20 sessions whose walk was not cut before the window
        wl = prep["hi_j"] - prep["lo_j"] + 1
        if wl <= 20 and w["last_j"] is not None and prep["J_tail"] >= prep["hi_j"] and not (w["cut"] == "hole" and w["last_j"] < prep["lo_j"]):
            scor += 1
            hit = prep["lo_j"] <= w["last_j"] <= prep["hi_j"]
            hits += int(hit)
            info["hit"] = hit
            info["scorable"] = True
        else:
            info["scorable"] = False
    if w0 is None:
        w0 = CI[min(r.b.E for r in recs)]
    sims = {k: rp.simulate(v, CAP30, CAL_DATES, w0) for k, v in (("ours", ours), ("chosen", chosen), ("his", his))}
    rec_, void = rev.recovery(sims["ours"]["final"], sims["chosen"]["final"], sims["his"]["final"])
    out = dict(rows=prows, cnt=cnt, sims=sims, recovery=rec_, void=void, hits=hits, scor=scor, lists=(ours, chosen, his), w0=w0)
    if boot and len(ours) >= 2:
        rng = rng_for("intra|boot")
        n = len(ours)
        vals = []
        for _ in range(1000):
            idx = rng.integers(0, n, size=n)
            s = {k: rp.simulate([v[i] for i in idx], CAP30, CAL_DATES, w0) for k, v in (("ours", ours), ("chosen", chosen), ("his", his))}
            r_, v_ = rev.recovery(s["ours"]["final"], s["chosen"]["final"], s["his"]["final"])
            if np.isfinite(r_):
                vals.append(r_)
        out["boot"] = (float(np.percentile(vals, 5)), float(np.percentile(vals, 95)), len(vals))
    return out


preload_range(dec_recs, -10, lambda r: own_off(r, r.b.exit_hi)[0] + 20)
EX = exit_pipeline(dec_recs, "dated 2021-22", w0=CI["2021-01-04"], boot=True)

# ---- L2 per-trade: fills / stops / bars / EMA / armed / E1 legs vs the side outputs
ex_t = {int(r["eid"]): r for r in exit_df.to_dict("records")}
bars_g = {e: g for e, g in bars_df.groupby("eid")}
bad = defaultdict(list)
for info in EX["rows"]:
    eid = info["eid"]
    t = ex_t[eid]
    reg, prep = info["reg"], info["prep"]
    # fill / stop
    if abs(reg["fill"] - float(t["fill"])) > 1e-9 * reg["fill"] or reg["fill_src"] != t["fill_src"] or (reg["fill_minute"] is None) != isnull(t["fill_minute"]) \
            or (reg["fill_minute"] is not None and int(float(t["fill_minute"])) != reg["fill_minute"]):
        bad["fill"].append((eid, reg["fill"], reg["fill_src"], reg["fill_minute"], t["fill"], t["fill_src"], t["fill_minute"]))
    if abs(reg["stop"] - float(t["stop"])) > 1e-9 * reg["stop"] or reg["stop_src"] != t["stop_src"]:
        bad["stop"].append((eid, reg["stop"], reg["stop_src"], t["stop"], t["stop_src"]))
    if prep["lo_j"] != int(t["exit_lo_j"]) or prep["hi_j"] != int(t["exit_hi_j"]) or prep["hi_j"] - prep["lo_j"] + 1 != int(t["window_len"]) or prep["J_tail"] != int(t["J_tail"]) \
            or not isnull(t["cut_why"]):
        bad["offsets/J_tail"].append((eid, prep["lo_j"], prep["hi_j"], prep["J_tail"], t["exit_lo_j"], t["exit_hi_j"], t["J_tail"]))
    # bars
    g = bars_g[eid].sort_values(["j", "k"]).reset_index(drop=True)
    items = info["items"]
    if len(g) != len(items):
        bad["bars_n"].append((eid, len(g), len(items)))
    else:
        for i, (jj, x) in enumerate(items):
            rw = g.iloc[i]
            if int(rw.j) != jj or int(rw.k) != x["k"] or int(rw.close_minute) != x["close_m"] or any(abs(float(rw[c_]) - x[c2]) > 1e-9 for c_, c2 in (("o", "o"), ("h", "h"), ("l", "l"), ("c", "c"))):
                bad["bars"].append((eid, i, jj, x["k"]))
                break
        em = info["ema"]
        fe = g["ema"].to_numpy(dtype=float)
        if not np.allclose(np.nan_to_num(em, nan=-1), np.nan_to_num(fe, nan=-1), rtol=0, atol=1e-9):
            bad["ema"].append(eid)
        sm = np.full(len(items), np.nan)
        cl = np.array([x["c"] for _, x in items])
        for i in range(19, len(cl)):
            sm[i] = cl[i - 19:i + 1].mean()
        if not np.allclose(np.nan_to_num(sm, nan=-1), np.nan_to_num(g["sma"].to_numpy(dtype=float), nan=-1), rtol=0, atol=1e-9):
            bad["sma"].append(eid)
        if info["armed"] is not None:
            fl_ = (np.arange(len(items)) >= info["armed"]).astype(int)
            if not np.array_equal(fl_, g["armed"].to_numpy()):
                bad["armed_flag"].append(eid)
    # armed / thin / seed residual / warm-up
    if info["armed"] is None or int(t["bars_before_armed"]) != info["armed"]:
        bad["bars_before_armed"].append((eid, info["armed"], t["bars_before_armed"]))
    else:
        resid = (1 - 2 / 21) ** max(0, info["armed"] - 20)
        if abs(resid - float(t["seed_residual"])) > 1e-12:
            bad["seed_residual"].append(eid)
    if (info["thin"] and t["abstain"] != "ema_thin") or (not info["thin"] and not isnull(t["abstain"])):
        bad["abstain"].append((eid, info["thin"], t["abstain"]))
    if sum(1 for jj, _ in info["items"] if jj < 0) != int(t["warmup_bars"]) or info["missing"] != int(t["missing_sessions"]):
        bad["warmup/missing"].append((eid, t["warmup_bars"], t["missing_sessions"]))
    # E1
    if not info["thin"]:
        w = info["walk"]
        if int(t["E1_last_j"]) != w["last_j"] or bool(t["E1_stop_preempt"]) != w["stop_preempt"]:
            bad["E1_last_j/preempt"].append((eid, t["E1_last_j"], w["last_j"], t["E1_stop_preempt"], w["stop_preempt"]))
        legs = ";".join(f"{lg.kind}@{lg.j}" for lg in w["legs"])
        if legs != t["E1_legs"]:
            bad["E1_legs"].append((eid, t["E1_legs"], legs))
        if bool(t["E1_scorable"]) != info["scorable"] or (info["scorable"] and bool(t["E1_hit"]) != info["hit"]):
            bad["E1_hit"].append((eid, t["E1_scorable"], info["scorable"], t["E1_hit"], info.get("hit")))
for key, label in (("fill", "registered fill (ORH5 / too_wide / close proxy), fill minute and source"), ("stop", "registered stop (day low at the fill minute; S1-T), source"),
                   ("offsets/J_tail", "sell-window offsets, window width and J_tail = exit_hi + 20 (no cut)"), ("bars_n", "60-minute bar count per trade"), ("bars", "60-minute bars o/h/l/c/close-minute rebuilt from raw minutes (28,219 rows)"),
                   ("ema", "20-EMA series (seed = mean of first 20 bars, alpha 2/21)"), ("sma", "20-bar plain average series"), ("armed_flag", "armed flag per bar"),
                   ("bars_before_armed", "bars before the armed bar"), ("seed_residual", "seed residual (19/21)^(n-20)"), ("abstain", "ema_thin abstention (< 65 bars before armed)"),
                   ("warmup/missing", "warm-up bars and missing sessions"), ("E1_last_j/preempt", "E1 last-leg session and stop pre-emption flag"), ("E1_legs", "E1 leg kind@session string"),
                   ("E1_hit", "E1 scorable / hit flags")):
    claim("D", f"L2 per trade ({len(EX['rows'])} rows): {label}", "0 differ", f"{len(bad[key])} differ", ok=(len(bad[key]) == 0), note=str(bad[key][:3]))
claim("D", "L2 bars file rows == rows rebuilt", len(bars_df), sum(len(i["items"]) for i in EX["rows"]))

# ---- era-B dated 2021-22 trades: the printed own-calendar offsets (gate v) and own-vs-unified on all 110 deciding records
eb_lines = [ln.strip() for ln in PR if ln.strip().startswith("era B ") and "own-calendar offsets" in ln]
eb_printed = sorted(re.findall(r"era B (\S+) (\d{4}-\d\d-\d\d): own-calendar offsets exit_lo (\d+) exit_hi (\d+)", "\n".join(eb_lines)))
eb_mine = sorted((r.b.sym, r.b.E, str(own_off(r, r.b.exit_lo)[0]), str(own_off(r, r.b.exit_hi)[0])) for r in dec_recs if r.era == "B")
claim("D", "era-B dated 2021-22 trades: own-calendar exit_lo / exit_hi offsets (7 trades)", "; ".join(f"{a} {b_} {c_}-{d_}" for a, b_, c_, d_ in eb_printed), "; ".join(f"{a} {b_} {c_}-{d_}" for a, b_, c_, d_ in eb_mine),
      ok=(eb_printed == eb_mine and len(eb_mine) == 7))
n_diff_dec = sum(1 for r in dec_recs if (bisect.bisect_left(cal, r.b.exit_hi) - bisect.bisect_left(cal, r.b.E)) != own_off(r, r.b.exit_hi)[0])
claim("D", "own-calendar vs unified-calendar exit_hi offset on the 110 deciding records", "n/a (offsets fixed to the record's own calendar)", f"{n_diff_dec} of 110 differ", ok=True, info=True,
      note="0 = the two calendars agree on this block; the old 1,445-1,569 session defect does not recur")


# ---- accounts, recovery, hit rate, abstentions vs the printed lines
ln_chain = [ln for ln in PR if ln.startswith("- dated 2021-22, chain fill and stop, E1")][0]
ln_reg = [ln for ln in PR if ln.startswith("- dated 2021-22, registered fill and stop, E1")][0]
m_ = re.search(r"stop_preempt (\d+), trades (\d+)\): ours ([\d.]+) \| chosen ([\d.]+) \| his ([\d.]+) \| his / ours ([\d.]+) \| recovery ([+-][\d.]+)", ln_chain)
p_pre, p_n, p_o, p_c, p_h, p_ratio, p_rec = int(m_.group(1)), int(m_.group(2)), float(m_.group(3)), float(m_.group(4)), float(m_.group(5)), float(m_.group(6)), float(m_.group(7))
S_ = EX["sims"]
claim("D", "trades in the account / stop pre-emptions", f"{p_n} / {p_pre}", f"{EX['cnt']['trades']} / {EX['cnt']['stop_preempt']}")
claim("D", "ours (speed trail, frozen code; my fill & stop) final equity multiple", p_o, round(S_["ours"]["final"], 3), tol=0.0005)
claim("D", "chosen (E1; MY legs through the frozen account simulator) final equity multiple", p_c, round(S_["chosen"]["final"], 3), tol=0.0005)
claim("D", "his (panel exit at the close of exit_hi, frozen code) final equity multiple", p_h, round(S_["his"]["final"], 3), tol=0.0005)
claim("D", "his / ours", p_ratio, round(S_["his"]["final"] / S_["ours"]["final"], 2), tol=0.005)
claim("D", "recovery = (ln chosen - ln ours) / (ln his - ln ours)", p_rec, round(EX["recovery"], 3), tol=0.0005, note=f"exact {EX['recovery']:.5f}; VOID reason '{EX['void']}'")
claim("D", "recovery vs the bar: 0.25 -> FAIL", "FAIL (-0.027 < 0.25)", f"{'FAIL' if EX['recovery'] < 0.25 else 'PASS'} ({EX['recovery']:+.3f})", ok=(EX["recovery"] < 0.25 and not EX["void"]))
for k_, lab in (("ours", "ours"), ("chosen", "chosen"), ("his", "his")):
    s_ = S_[k_]
    pl = [ln for ln in PR if ln.startswith(f"    {lab}: by year")]
    # the first three such lines after the chain line
    idx_chain = PR.index(ln_chain)
    blk = [x for x in PR[idx_chain + 1:idx_chain + 5] if x.startswith(f"    {lab}: by year")][0]
    mine_blk = f"    {lab}: by year " + ", ".join(f"{y} {rp.pct(x)}" for y, x in sorted(s_["yearly"].items())) + f" | max DD {rp.pct(s_['max_dd'])} | entered {s_['counts']['entered']}, skipped no room {s_['counts']['skipped_no_room']}"
    claim("D", f"{lab}: by-year returns | max drawdown | entered | skipped (no room)", blk.strip(), mine_blk.strip())
ab = EX["cnt"]["ema_thin"] + EX["cnt"]["no_armed_bar"] + EX["cnt"]["cut_at_tail"] + EX["cnt"]["cut_other"]
den = EX["cnt"]["trades"] + EX["cnt"]["ema_thin"] + EX["cnt"]["no_armed_bar"]
claim("D", "abstentions (cut_at_tail + horizon + data_end + guard + hole + break + ema_thin + no-bar) / share of trades", "3 = 2.7%", f"{ab} = {rp.pct(ab / den)}", ok=(ab == 3 and rp.pct(ab / den) == "2.7%"))
claim("D", "ema_thin abstentions", 3, EX["cnt"]["ema_thin"])
hit_line = [ln for ln in PR if ln.startswith("- dated 2021-22, EMA(20) on the 60-minute bars")][0]
p_hit = float(re.search(r"E1 \(CHOSEN\) last-leg hit ([\d.]+)%", hit_line).group(1))
claim("D", "E1 last-leg hit rate on the 107 (the sell day seen)", f"{p_hit}% on 107", f"{rp.pct(EX['hits'] / EX['scor'])} ({EX['hits']}/{EX['scor']})", ok=(EX["scor"] == 107 and float(rp.pct(EX["hits"] / EX["scor"]).rstrip('%')) == p_hit))
claim("D", "E1 half-leg hit rate 0.0% (E1 has no half leg)", "0.0%", "0.0% (no half leg by construction)", ok=True, info=True)
bp = re.search(r"interval of the recovery.*?\[([+-][\d.]+), ([+-][\d.]+)\]", PR[PR.index(ln_chain) + 4])
claim("D", "bootstrap 90% interval of the recovery (1000 draws, seed 702, key intra|boot, trade resampling)", f"[{bp.group(1)}, {bp.group(2)}]", f"[{EX['boot'][0]:+.3f}, {EX['boot'][1]:+.3f}] ({EX['boot'][2]} finite draws)",
      ok=(f"{EX['boot'][0]:+.3f}" == bp.group(1) and f"{EX['boot'][1]:+.3f}" == bp.group(2)))
# chain == registered blocks, fill_fallback 0
chain_tail = ln_chain.split("): ", 1)[1]
reg_tail = ln_reg.split("): ", 1)[1]
claim("D", "the chain line and the registered line are identical (neither ENTER nor STOP passed)", "identical", "identical" if chain_tail == reg_tail else "DIFFER", ok=(chain_tail == reg_tail))
claim("D", "fill_fallback 0 (no ENTER-level fill used)", "fill_fallback 0", "fill_fallback 0 (the chain carries the registered fill: ENTER FAIL, STOP INCONCLUSIVE)", ok=("fill_fallback 0" in " ".join(PR)))
src_ct = Counter(i["reg"]["fill_src"] for i in EX["rows"])
claim("D", "registered fill sources on the 110 dated trades", "orh5 90 / orh5_too_wide 12 / close_proxy 8", " / ".join(f"{k} {v}" for k, v in sorted(src_ct.items(), key=lambda kv: -kv[1])), ok=(src_ct == Counter({"orh5": 90, "orh5_too_wide": 12, "close_proxy": 8})))


# ---- the untouched dated trades (the sign veto) and the undated 2021-22 (beside): same pipeline, printed aggregates only (no per-trade TSV exists for them)
recs_vd_ex = [r for r in recs_vd if r.b.exit_hi]
claim("D", "untouched dated trades with an exit: records (23 with exits - DDOG 2019-11-13 under the 50-bar floor = 22)", "22", len(recs_vd_ex), ok=(len(recs_vd_ex) == 22),
      note=f"virgin dated with exits in the loader set: {sum(1 for b in IS['virgin_dated'] if b.exit_hi)}")
recs_22u_all, d22u = I.recs_for(IS["chk22_und"], M, store, guard0)
recs_22u_ex = [r for r in recs_22u_all if r.b.exit_hi]
preload_range(recs_vd_ex + recs_22u_ex, -10, lambda r: own_off(r, r.b.exit_hi)[0] + 20)
EXV = exit_pipeline(recs_vd_ex, "untouched dated", w0=CI[min(r.b.E for r in recs_vd_ex)])
ln_v = [ln for ln in PR if ln.startswith("- the untouched dated trades (the sign veto), E1")][0]
mv = re.search(r"stop_preempt (\d+), trades (\d+)\): ours ([\d.]+) \| chosen ([\d.]+) \| his ([\d.]+) \| his / ours ([\d.]+) \| recovery (\S+) \| VOID \(his / ours = ([\d.]+) < 1.25\)", ln_v)
SV = EXV["sims"]
claim("D", "untouched dated (veto set): trades / stop pre-emptions", f"{mv.group(2)} / {mv.group(1)}", f"{EXV['cnt']['trades']} / {EXV['cnt']['stop_preempt']}")
claim("D", "untouched dated: ours / chosen / his final equity", f"{mv.group(3)} / {mv.group(4)} / {mv.group(5)}", f"{SV['ours']['final']:.3f} / {SV['chosen']['final']:.3f} / {SV['his']['final']:.3f}")
claim("D", "untouched dated: his / ours (VOID, < 1.25) and recovery nan", f"{mv.group(6)} (VOID {mv.group(8)}) / {mv.group(7)}", f"{SV['his']['final'] / SV['ours']['final']:.2f} (VOID {SV['his']['final'] / SV['ours']['final']:.3f}) / {EXV['recovery']}",
      ok=(f"{SV['his']['final'] / SV['ours']['final']:.2f}" == mv.group(6) and f"{SV['his']['final'] / SV['ours']['final']:.3f}" == mv.group(8) and bool(EXV["void"])))
idx_v = PR.index(ln_v)
for lab in ("ours", "chosen", "his"):
    blk = [x for x in PR[idx_v + 1:idx_v + 5] if x.startswith(f"    {lab}: by year")][0]
    s_ = SV[lab]
    mine_blk = f"    {lab}: by year " + ", ".join(f"{y} {rp.pct(x)}" for y, x in sorted(s_["yearly"].items())) + f" | max DD {rp.pct(s_['max_dd'])} | entered {s_['counts']['entered']}, skipped no room {s_['counts']['skipped_no_room']}"
    claim("D", f"untouched dated {lab}: by year | max DD | entered | skipped", blk.strip(), mine_blk.strip())
v_hit = float(re.search(r"the untouched dated trades \(windows <= 20 sessions\): E1 last-leg hit ([\d.]+)% / half-leg hit [\d.]+% on (\d+)", " ".join(PR)).group(1))
v_n = int(re.search(r"the untouched dated trades \(windows <= 20 sessions\): E1 last-leg hit ([\d.]+)% / half-leg hit [\d.]+% on (\d+)", " ".join(PR)).group(2))
claim("D", "untouched dated hit rate E1 (windows <= 20 sessions)", f"{v_hit}% on {v_n}", f"{rp.pct(EXV['hits'] / EXV['scor'])} ({EXV['hits']}/{EXV['scor']})", ok=(EXV["scor"] == v_n and float(rp.pct(EXV["hits"] / EXV["scor"]).rstrip('%')) == v_hit))
lo_ = math.log(SV["his"]["final"] / SV["ours"]["final"])
claim("D", "untouched-dated sign veto: fires only if ln(his/ours) > 0 AND ln(chosen/ours) < 0", "abstains (his 0.991 <= ours 1.015)", f"ln(his/ours) = {lo_:+.4f} -> {'abstains' if lo_ <= 0 else 'could fire'}", ok=(lo_ <= 0))
claim("D", "the sign veto abstains, so the verdict stays FAIL (and the VOID of the veto set is not applied to the deciding set)", "EXIT FAIL", f"EXIT {'FAIL' if (EX['recovery'] < 0.25 and not EX['void'] and lo_ <= 0) else 'other'}", ok=(EX["recovery"] < 0.25 and lo_ <= 0))
# beside: undated 2021-22
EXU = exit_pipeline(recs_22u_ex, "undated 2021-22", w0=CI["2021-01-04"])
ln_u = [ln for ln in PR if ln.startswith("- beside: undated 2021-22, chain fill and stop, E1")][0]
mu = re.search(r"ema_thin (\d+), stop_preempt (\d+), trades (\d+)\): ours ([\d.]+) \| chosen ([\d.]+) \| his ([\d.]+) \| his / ours ([\d.]+) \| recovery (\S+) \| VOID \(his / ours = ([\d.]+) < 1.25\)", ln_u)
SU = EXU["sims"]
claim("D", "beside undated 2021-22: ema_thin / stop pre-emptions / trades", f"{mu.group(1)} / {mu.group(2)} / {mu.group(3)}", f"{EXU['cnt']['ema_thin']} / {EXU['cnt']['stop_preempt']} / {EXU['cnt']['trades']}")
claim("D", "beside undated 2021-22: ours / chosen / his (VOID 1.09)", f"{mu.group(4)} / {mu.group(5)} / {mu.group(6)} (ratio {mu.group(7)})", f"{SU['ours']['final']:.3f} / {SU['chosen']['final']:.3f} / {SU['his']['final']:.3f} (ratio {SU['his']['final'] / SU['ours']['final']:.2f})")
u_hit = re.search(r"beside: undated 2021-22: E1 last-leg hit ([\d.]+)% / half-leg hit [\d.]+% on (\d+)", " ".join(PR))
claim("D", "beside undated 2021-22 hit rate E1", f"{u_hit.group(1)}% on {u_hit.group(2)}", f"{rp.pct(EXU['hits'] / EXU['scor'])} ({EXU['hits']}/{EXU['scor']})", ok=(EXU["scor"] == int(u_hit.group(2)) and float(rp.pct(EXU["hits"] / EXU["scor"]).rstrip('%')) == float(u_hit.group(1))))

# ---- sensitivities (do not change any printed number): what a literal reading of the registration would add
# (1) STOP: a buy-day unresolved event ends the scan in the code; the doc's H_cond counts "a session he CERTAINLY held" -> scan on to later sessions
def my_held_cont(rec, name, V):
    b, t = rec.b, stop_t[rec.b.eid]
    base = HELD[(b.eid, name, V)]
    if not (base["unres"] and base["first_j"] == 0 and not base["certain"]):
        return base
    # re-scan from session 1 on with the same rules
    st = STOPS[b.eid]
    lo_j, hi_j = int(t["exit_lo_j"]), int(t["exit_hi_j"])
    for j in range(1, hi_j + 1):
        k = rec.e + j
        if not (k < len(rec.cidx) and int(rec.cidx[k]) == rec.e_ci + j):
            break
        L = st["SMA50"][k] if name == "SMA50" else st[name]
        if not np.isfinite(L):
            continue
        if V == "T":
            through = float(rec.bars.l[k]) <= L
            m = first_touch(mb_of(rec, j), L) if (through and j == lo_j) else None
        elif V == "C":
            through, m = float(rec.bars.c[k]) < L, None
        else:
            mbj = mb_of(rec, j)
            bj = h60_mine(mbj, sess_date(rec, j)) if mbj is not None else None
            through, m = False, None
            for x in (bj or []):
                if x is not None and x["c"] < L:
                    through, m = True, x["close_m"]
                    break
        if not through:
            continue
        if j < lo_j:
            return dict(base, certain=True)
        if j == lo_j:
            if V == "C":
                return dict(base, certain=bool(my_after_close_frame(b.exit_lo, b.sym)))
            cl, _ = my_last_in_session_clock(b.exit_lo, b.sym)
            return dict(base, certain=(cl is not None and m is not None and m < hm(cl)))
        return base
    return base


sens = {}
for (n_, v_) in (("S1", "T"), ("S1", "C"), ("S1", "H"), ("S3", "T"), ("S3", "H"), ("S9", "T"), ("S9", "H"), ("S10", "T"), ("S10", "H")):
    anyn = sum(HELD[(r.b.eid, n_, v_)]["any"] for r in recs_vu)
    cert = sum(my_held_cont(r, n_, v_)["certain"] for r in recs_vu)
    sens[(n_, v_)] = (cert, anyn, cert / anyn if anyn else float("nan"), tab_mine[(n_, v_)]["hcond"])
changed = {k: v for k, v in sens.items() if v[0] != round(v[3] * v[1])}
claim("C", "SENSITIVITY: scanning on after an unresolved buy-day event (literal reading of 'a session he CERTAINLY held') changes H_cond in", "n/a (not in the printout)",
      f"{len(changed)} of {len(sens)} cells tested" + (": " + "; ".join(f"{k[0]}-{k[1]} {r1(v[3]):.1f}% -> {r1(v[2]):.1f}%" for k, v in changed.items()) if changed else ""),
      ok=True, info=True, note="can only RAISE H_cond; the INCONCLUSIVE verdict rests on the fit table having no cell <= 10%, which a raise cannot repair")

# (2) EXIT: the stop pre-empts any leg inside a session. How often does E1's trigger bar close BEFORE the stop would have been touched in the same session?
inv = []
for info, r in zip(EX["rows"], dec_recs):
    if info.get("walk") is None or not info["walk"]["stop_preempt"]:
        continue
    w = info["walk"]
    leg = w["legs"][-1]
    j = leg.j
    if leg.minute in (None, 0) and leg.kind == "stop_gap":
        continue
    for i, (jj, x) in enumerate(info["items"]):
        if jj == j and i >= info["armed"] and np.isfinite(info["ema"][i]) and x["c"] < info["ema"][i]:
            if leg.minute is not None and x["close_m"] < leg.minute:
                inv.append((r.b.sym, r.b.E, j, x["close_m"], leg.minute, leg.kind))
            break
claim("D", "SENSITIVITY: stop pre-emptions where E1's bar had already closed under the EMA earlier in that session (the 'stop first' reading sells at the stop instead of the E1 open)", "n/a (registered reading, listed)",
      f"{len(inv)} of {EX['cnt']['stop_preempt']}" + (": " + ", ".join(f"{a} {b_} +{c_}" for a, b_, c_, _, _, _ in inv[:8]) if inv else ""), ok=True, info=True,
      note="informational; a registered reading of the doc ('the chain's stop pre-empts any leg inside a session')")


# ═════════════════════════════════════════════════════════════════════════════════════════════
# the table
# ═════════════════════════════════════════════════════════════════════════════════════════════
def write_table():
    n_ok = sum(1 for c_ in CLAIMS if c_[4] == "MATCH")
    n_note = sum(1 for c_ in CLAIMS if c_[4] == "NOTE")
    n_bad = len(CLAIMS) - n_ok - n_note
    say(f"\n## CLAIM TABLE ({len(CLAIMS)} claims: {n_ok} MATCH, {n_note} NOTE, {n_bad} MISMATCH)")
    say("stage | claim | printout | yours | status (note)")
    for st_, nm_, pr_, mi_, stt, note in CLAIMS:
        say(f"{st_} | {nm_} | {fmt(pr_)} | {fmt(mi_)} | {stt}" + (f" ({note})" if note and (stt == 'MISMATCH' or len(note) < 300) else ""))
    with open(OUT_TXT, "w", encoding="utf-8") as fh:
        fh.write("\n".join(LOG) + "\n")
    return n_ok, n_bad


say("\n## WHAT RESTS ON FROZEN IMPORTS vs WHAT IS MINE")
say("- mine (recomputed from raw minute files / daily export / frames): every level (L1-L9), first crossing, feasible, HIT/BALLPARK/MISS, the random-price control replay, the shifted-window control (200 draws x 9 levels per window), the union,")
say("  the virgin veto; the S1/S3/S9/S10/S8/SMA50 levels, the 18 held-through cells (traded through / certain / unresolved / first session / event minute), the fit-table choose rule, Spearman, re-buys;")
say("  the 60-minute bars (28,219 rows), the EMA, the armed bar, ema_thin, the registered ORH5 / open fill, the S1-T / ADR20 stop, the day-0 stop, E1's legs, the hit rate, the abstention share, the bootstrap.")
say("- frozen / loader code NOT recounted: the buys / clock / set loaders (load_core), the daily-export and minute-file readers, the 'ours' speed trail (rev.speed_trail_trade -> cb.walk_arms), 'his' (rev.panel_trade), the account simulator rp.simulate at cap_30,")
say("  rev.recovery, Trade plumbing make_legs_trade (fed with MY legs), rev.break_horizon, the snapshot frames as loaded. 'ours' and 'his' therefore agree with the printout by construction of the SAME simulator on MY fill/stop inputs; only their inputs are independent.")
say("- STOP fit column: the 415 fit records' 18 cells are re-derived from bars (C2), but the fit's fills (open / ORH5 / close proxy / level:L8) and fill minutes are taken from stop_fit_trades.tsv as INPUTS (they are ENTER's and the registered fill's outputs on 2020); ENTER's L8 fit and the 2020 EXIT/ENTER fit tables are not recounted.")
say("- shared-reading risk: where the registration is silent I mirrored the code's rule (strict '>' crossing; a touch = low <= level OR open < level; day-0 events only after max(fill minute, flat clock); the stop is tested before E1 inside a session). The two sensitivities above test the two that could move a number.")
say(f"- bootstrap: {EX['boot'][2]} of 1000 resamples had a finite recovery (the rest were VOID, his/ours < 1.25, and are dropped); the printout says '1000 draws' and prints the interval of the finite ones. Information only.")
say("- n = 40 on the ENTER deciding set sits exactly on the registered floor; L8's random-control margin passes by 0.0004 on exact numbers (0.4500 vs 0.2996 + 0.15). Neither changes FAIL (45.0% < the 50% bar).")
say("- on the 58 deciding records S9 and S10 are numerically identical in all three variants (the last completed 60-minute bar before a read minute in 30..89 IS the 30-minute bar), so the 12 STOP cells carry 9 distinct readings there.")
say("- exact recovery -0.02708 equals the daily list's in-sample -0.027 named in registration §7d to three decimals; the finals differ (daily list on the old offsets: ours 1.398, his 2.620), so this is a coincidence, not a copy.")

if os.environ.get("RECOUNT_SELFTEST"):
    claim("SELFTEST", "deliberate wrong number must print MISMATCH", 0.451, 0.45, tol=0.0005 / 10)
n_ok, n_bad = write_table() if "RECOUNT_NOFINAL" not in os.environ else (0, 0)
