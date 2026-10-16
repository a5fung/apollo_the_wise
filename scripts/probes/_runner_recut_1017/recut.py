#!/usr/bin/env python3
"""Runner-rule re-cut against the live depth exit (pre-registration 2026-10-16, §8 build spec).

  --selftest   synthetic bars only; prints no outcome total
  --gate       the gates on the real population (G0, G2, G2b, G3, G-ext); prints NO outcome total
  --run        THE run (re-runs every gate first and refuses to print a total if one is red)
  --trace      the two pre-registered hand-traces, from the raw bars

The control is the LIVE walker (`live_fill_counterfactuals.walk_arm`, §2 kwargs verbatim). Candidates
and the reference rows run through `walker_cand.walk_cand`, a generated frozen copy of that walker with
one hook set (make_walker.py; the full difference is walker_diff.out). Money-R = pnl / (entry - placed
stop); 1 money-R = 2 ORB-R. Read-only; no DB; no prod. The extension pull was REFUSED by the permission
system, so the read of record is the capture alone (pre-registration §1 Fallback).
"""
import argparse
import bisect
import gzip
import hashlib
import importlib.util
import json
import math
import random
import statistics
import sys
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from datetime import date, timedelta
from typing import Optional

REPO = "/Users/alvinfung/apollo_the_wise"
P = f"{REPO}/scripts/probes/_runner_recut_1017"
CAP = f"{P}/captures"
OUTDIR = P   # where --run writes run_rows.tsv / run_results.json (the dry-run on synthetic rows overrides it)
sys.path.insert(0, REPO)

from agents.market_intelligence.broker.exit_logic import adr20_pct_from_bars  # noqa: E402
from agents.market_intelligence.live_fill_counterfactuals import (  # noqa: E402
    HORIZON_SESSIONS, walk_arm as LIVE_WALK)
from scripts.probes._bt_replay import _fill_entry  # noqa: E402

_spec = importlib.util.spec_from_file_location("walker_cand", f"{P}/walker_cand.py")
walker_cand = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(walker_cand)
walk_cand = walker_cand.walk_cand

DATA_END = date(2026, 8, 28)
H1_END = date(2026, 6, 30)
TAIL_R = 4.0
BE_R = 1.5
RULES = ["t3_be", "t5_be", "t10_be", "t20_be", "close_only", "sma10_depth", "sma20_depth",
         "atr1_be", "atr2_be", "gb25_be", "gb50_be"]
FRAMES = ["A", "B"]
PRIMARY = ("A", "t20_be")
REFS = ["t20_entry_ref", "era_d", "control_at_close"]
SEED = 1017
PERM_DRAWS = 5000
BOOT_DRAWS = 10000

# the pinned input hashes (pre-registration §1; the full values are in input_hashes.sha256)
PINNED = {"bt_admission_result.json": "60febea3b5e3c87a", "bt_out_bars.psv": "7711e94e742ba235",
          "bt_out_daily.psv": "af539500c7ef13c9", "bt_out_cov.psv": "b351b1bfdae078bc",
          "runner_sweep_results.json": "5d1c5666", "runner_sweep_rows.tsv": "cb2936d6",
          "runner_sweep_stdout.txt": "16663c02"}

CONTROL_KW = dict(harvest="live_ladder", trail_mode="sma", breakeven_at_r=3.0, breakeven_at_partial=True,
                  trail_prior_closes=True, ladder_partial=False, horizon=40, depth_exit=True)


def pd(s):
    return date.fromisoformat(s)


# ═══════════════════════════ loaders (copied from _runner_sweep.py, blob 57e4e246) ═══════════════════════════
@dataclass
class Inputs:
    rows_u: list
    mbars: dict
    daily: dict
    all_dates: list
    hashes: dict


def load_inputs() -> Inputs:
    hashes = {}
    for f in PINNED:
        h = hashlib.sha256(gzip.open(f"{CAP}/{f}.gz", "rb").read()).hexdigest()
        hashes[f] = h
    adm = json.load(gzip.open(f"{CAP}/bt_admission_result.json.gz", "rt"))
    rows_u = adm["U"]["replayable"]
    mbars = defaultdict(list)
    for line in gzip.open(f"{CAP}/bt_out_bars.psv.gz", "rt"):
        f = line.rstrip("\n").split("|")
        if len(f) != 7:
            continue
        mbars[(pd(f[1]), f[0])].append((f[2], float(f[3]), float(f[4]), float(f[5]), float(f[6])))
    for k, v in mbars.items():
        assert all(v[i][0] < v[i + 1][0] for i in range(len(v) - 1)), f"minute bars not ascending for {k}"
    daily = defaultdict(list)
    for line in gzip.open(f"{CAP}/bt_out_daily.psv.gz", "rt"):
        f = line.rstrip("\n").split("|")
        if len(f) != 7:
            continue
        o = float(f[2]) if f[2] else None
        h = float(f[3]) if f[3] else None
        l = float(f[4]) if f[4] else None
        daily[f[0]].append((pd(f[1]), o, h, l, float(f[5])))
    for t in daily:
        daily[t].sort()
    all_dates = sorted({r[0] for rows in daily.values() for r in rows})
    return Inputs(rows_u, mbars, daily, all_dates, hashes)


def atr14_abs(inp: Inputs, t, d):
    """Absolute ATR14 through d-1 (copied from _runner_sweep.py)."""
    rows = inp.daily.get(t, [])
    dates = [r[0] for r in rows]
    hi = bisect.bisect_left(dates, d)
    rows = [r for r in rows[max(0, hi - 35):hi] if r[2] is not None and r[3] is not None]
    if len(rows) < 10:
        return None
    trs = []
    for i in range(1, len(rows)):
        h, l, pc = rows[i][2], rows[i][3], rows[i - 1][4]
        trs.append(max(h - l, abs(h - pc), abs(l - pc)))
    if not trs:
        return None
    w = trs[-14:]
    return sum(w) / len(w)


@dataclass
class Trade:
    t: str
    d: date
    entry: float
    orb_low: float
    orb_high: float
    r_orb: float
    stop: float
    day0: list
    fill_idx: int
    sessions: list
    prior: list
    adr20: Optional[float]
    atr14: Optional[float]
    day0_close: float
    pre_rows: list = field(default_factory=list)

    @property
    def key(self):
        return (self.t, self.d.isoformat())

    @property
    def risk(self):
        return self.entry - self.stop

    @property
    def target(self):
        return self.entry + 8.0 * self.r_orb

    @property
    def week(self):
        return self.d.isocalendar()[:2]


def build_trades(inp: Inputs):
    trades, acct = [], Counter()
    for a in inp.rows_u:
        t, d = a["t"], pd(a["d"])
        bars = inp.mbars.get((d, t), [])
        orb = next(({"high": b[2], "low": b[3]} for b in bars if b[0] == "09:30"), None)
        if orb is None:
            acct["no_bars:no_orb_bar"] += 1
            continue
        entry_all = [{"m": b[0], "o": b[1], "h": b[2], "l": b[3], "c": b[4]} for b in bars if b[0] > "09:30"]
        if not entry_all:
            acct["no_bars:no_bars_after_orb"] += 1
            continue
        if orb["high"] <= orb["low"]:
            acct["no_bars:degenerate_orb"] += 1
            continue
        entry_win = [{"open": b["o"], "high": b["h"], "low": b["l"], "close": b["c"]}
                     for b in entry_all if b["m"] <= "09:59"]
        fill_idx, _ = _fill_entry(orb["high"], entry_win)
        if fill_idx is None:
            acct["never_triggered"] += 1
            continue
        entry = orb["high"]
        r_orb = entry - orb["low"]
        rows = inp.daily.get(t, [])
        dates = [r[0] for r in rows]
        hi = bisect.bisect_left(dates, d)
        pre = [r for r in rows[max(0, hi - 20):hi] if r[0] >= d - timedelta(days=60)]
        adr20 = adr20_pct_from_bars([{"h": r[2], "l": r[3], "c": r[4]} for r in pre])
        prior = [r[4] for r in rows if d - timedelta(days=40) <= r[0] < d]
        gi = bisect.bisect_right(inp.all_dates, d)
        expected = inp.all_dates[gi:gi + HORIZON_SESSIONS]
        rowmap = {r[0]: r for r in rows}
        sess = []
        for ed in expected:
            r = rowmap.get(ed)
            if r is None or r[2] is None or r[3] is None:
                sess.append((ed, None))
            else:
                sess.append((ed, {"o": r[1], "h": r[2], "l": r[3], "c": r[4]}))
        d0 = next((r[4] for r in rows if r[0] == d), None)
        if d0 is None:
            d0 = entry_all[-1]["c"]
        trades.append(Trade(t, d, entry, orb["low"], orb["high"], r_orb, 2 * orb["low"] - orb["high"],
                            entry_all, fill_idx, sess, prior, adr20, atr14_abs(inp, t, d), d0, pre))
    trades.sort(key=lambda x: (x.d, x.t))
    acct["filled"] = len(trades)
    return trades, acct


# ═══════════════════════════ walking ═══════════════════════════
def walk_kwargs(tr: Trade, **over):
    kw = dict(entry=tr.entry, stop=tr.stop, target=tr.target, day0_bars=tr.day0, fill_idx=tr.fill_idx,
              sessions=tr.sessions, prior_closes=tr.prior, fill_day=tr.d, r_frame_ps=tr.r_orb,
              depth_adr20_pct=tr.adr20, **CONTROL_KW)
    kw.update(over)
    return kw


def live_control(tr):
    return LIVE_WALK(**walk_kwargs(tr))


def live_era_d(tr):
    return LIVE_WALK(**walk_kwargs(tr, depth_exit=False, depth_adr20_pct=None))


def cand_walk(tr, rule=None, frame=None, ref=None, trace=None, mutate_early=False):
    hook = dict(rule=rule, frame=frame, ref=ref, atr14=tr.atr14, day0_close=tr.day0_close, trace=trace,
                mutate_early=mutate_early)
    return walk_cand(**walk_kwargs(tr), hook=hook)


@dataclass
class Arm:
    R: Optional[float]
    status: str          # settled | horizon | data_end | gap | abstain | other
    out: dict
    exit_session: Optional[int]
    final_reason: Optional[str]
    partial: bool


def last_close_of(tr: Trade, out: dict) -> float:
    """The last stored close the walk reached: the session close it got to, else the day-0 close.
    (Derived from the LIVE walker's own sessions_walked, so the control needs no hook; the frozen copy
    also reports `last_close` and G2 checks the two agree.)"""
    sw = out["sessions_walked"]
    return tr.sessions[sw - 1][1]["c"] if sw >= 1 else tr.day0[-1]["c"]


def score(tr: Trade, out: dict) -> Arm:
    risk = tr.risk
    st = out["status"]
    if st == "settled":
        return Arm(out["pnl_per_share"] / risk, "settled", out, out.get("exit_session"),
                   out.get("final_reason"), out["partial_fired"])
    if st == "horizon":
        return Arm(out["mark_pnl_per_share"] / risk, "horizon", out, None, "horizon", out["partial_fired"])
    if st == "pending":
        reason = out["reason"] or ""
        if reason.startswith("missing_session"):
            return Arm(None, "gap", out, None, reason, out["partial_fired"])
        if reason in ("open_walk_not_definitive", "depth_next_open_not_yet_settled"):
            booked = sum(e["pnl"] for e in out["exits"])
            mark = booked + (last_close_of(tr, out) - tr.entry) * out["remaining"]
            return Arm(mark / risk, "data_end", out, None, reason, out["partial_fired"])
        return Arm(None, "other", out, None, reason, out["partial_fired"])
    if st == "abstain":
        return Arm(None, "abstain", out, None, out["reason"], out["partial_fired"])
    return Arm(None, "other", out, None, out.get("reason"), out["partial_fired"])


# ═══════════════════════════ comparisons ═══════════════════════════
def _feq(a, b, tol=1e-9):
    if a is None or b is None:
        return a is None and b is None
    if isinstance(a, float) or isinstance(b, float):
        return abs(a - b) <= tol
    return a == b


def legs_equal(la, lb, tol=1e-9):
    if len(la) != len(lb):
        return False
    for x, y in zip(la, lb):
        if set(x) != set(y):
            return False
        for k in x:
            if isinstance(x[k], (int, float)) and isinstance(y[k], (int, float)) and not isinstance(x[k], bool):
                if abs(x[k] - y[k]) > tol:
                    return False
            elif x[k] != y[k]:
                return False
    return True


COMPARE_KEYS = ("status", "reason", "pending_at", "final_reason", "partial_fired", "gap_through",
                "exit_session", "sessions_walked", "pnl_per_share", "mark_pnl_per_share", "remaining")


def outs_equal(a, b):
    for k in COMPARE_KEYS:
        if not _feq(a.get(k), b.get(k)):
            return False, k
    if not legs_equal(a["exits"], b["exits"]):
        return False, "exits"
    return True, None


def is_day0_leg(leg):
    return len(str(leg["time"])) == 5


def legs_before(out, trig_idx, sessions):
    """Legs booked strictly BEFORE the trigger session (day-0 legs always count when the trigger is a
    later session; a day-0 trigger compares day-0 legs only up to the trigger minute -> all day-0 legs
    are control-identical by construction)."""
    if trig_idx == 0:
        return [l for l in out["exits"] if is_day0_leg(l)]
    tdate = sessions[trig_idx - 1][0].isoformat()
    return [l for l in out["exits"] if is_day0_leg(l) or str(l["time"])[:10] < tdate]


def g3_compare(ctrl_copy, cand, frame, sessions, ctrl_trace=None, cand_trace=None):
    """Returns (ok, why). ctrl_copy = hookless copy's out (records both triggers); cand = candidate's out."""
    rec_c = ctrl_copy["trig"].get(frame)
    rec_k = cand["trig"].get(frame)
    if rec_c is None:
        ok, k = outs_equal(ctrl_copy, cand)
        return (ok, None if ok else f"no-trigger trade differs on {k}")
    if rec_k is None or rec_k["idx"] != rec_c["idx"] or abs(rec_k["F"] - rec_c["F"]) > 1e-9:
        return False, f"trigger differs control={rec_c} cand={rec_k}"
    if not legs_equal(legs_before(ctrl_copy, rec_c["idx"], sessions), legs_before(cand, rec_c["idx"], sessions)):
        return False, "legs before the trigger differ"
    if ctrl_trace is not None and cand_trace is not None:
        pre_c = [s for s in ctrl_trace.get("sessions", []) if s["idx"] < rec_c["idx"]]
        pre_k = [s for s in cand_trace.get("sessions", []) if s["idx"] < rec_c["idx"]]
        if pre_c != pre_k:
            return False, "pre-trigger session lines differ"
    return True, None


# ═══════════════════════════ statistics (stdlib only) ═══════════════════════════
def pctile(xs, q):
    s = sorted(xs)
    n = len(s)
    if n == 0:
        return None
    pos = (n - 1) * q
    lo = int(math.floor(pos))
    hi = min(lo + 1, n - 1)
    return s[lo] + (s[hi] - s[lo]) * (pos - lo)


def signflip_p(block_sums, draws=PERM_DRAWS, seed=SEED):
    rng = random.Random(seed)
    sums = list(block_sums)
    obs = sum(sums)
    hits = 0
    for _ in range(draws):
        perm = sum(s if rng.random() < 0.5 else -s for s in sums)
        if abs(perm) >= abs(obs) - 1e-12:
            hits += 1
    return (hits + 1) / (draws + 1)


def boot_ci(blocks, draws=BOOT_DRAWS, seed=SEED):
    """blocks: list of (sum_of_deltas, n). Week-clustered bootstrap of the mean paired difference."""
    rng = random.Random(seed)
    nb = len(blocks)
    if nb == 0:
        return None, None
    vals = []
    for _ in range(draws):
        s = n = 0
        for _ in range(nb):
            bs, bn = blocks[rng.randrange(nb)]
            s += bs
            n += bn
        vals.append(s / n if n else 0.0)
    vals.sort()
    return vals[int(0.025 * draws)], vals[int(math.ceil(0.975 * draws)) - 1]


def mfe_r(tr: Trade, arm: Arm):
    """Best intraday high reached while the arm held the position, in money-R."""
    hi = max(b["h"] for b in tr.day0[tr.fill_idx:])
    n = arm.exit_session if arm.exit_session is not None else len(tr.sessions)
    for idx, (_, b) in enumerate(tr.sessions, start=1):
        if idx > n:
            break
        if b is not None:
            hi = max(hi, b["h"])
    return (hi - tr.entry) / tr.risk


def best_close_r(tr: Trade, arm: Arm):
    cl = [tr.day0_close]
    n = arm.exit_session if arm.exit_session is not None else len(tr.sessions)
    for idx, (_, b) in enumerate(tr.sessions, start=1):
        if idx > n:
            break
        if b is not None:
            cl.append(b["c"])
    return (max(cl) - tr.entry) / tr.risk


# ═══════════════════════════ the population run ═══════════════════════════
@dataclass
class Row:
    tr: Trade
    ctrl: Arm
    copy0: dict
    copy0_trace: dict
    arms: dict = field(default_factory=dict)       # (frame, rule) -> Arm
    cand_outs: dict = field(default_factory=dict)  # (frame, rule) -> (out, trace)
    refs: dict = field(default_factory=dict)
    ref_outs: dict = field(default_factory=dict)   # ref name -> (out, trace)


def run_population(trades, with_arms=True):
    rows = []
    for tr in trades:
        tr0 = {}
        copy0 = cand_walk(tr, trace=tr0)
        r = Row(tr, score(tr, live_control(tr)), copy0, tr0)
        if with_arms:
            for fr in FRAMES:
                for rule in RULES:
                    trc = {}
                    o = cand_walk(tr, rule=rule, frame=fr, trace=trc)
                    r.arms[(fr, rule)] = score(tr, o)
                    r.cand_outs[(fr, rule)] = (o, trc)
            trc = {}
            o = cand_walk(tr, rule="t20_be", frame="A", ref="t20_entry_ref", trace=trc)
            r.refs["t20_entry_ref"] = score(tr, o)
            r.ref_outs["t20_entry_ref"] = (o, trc)
            r.refs["era_d"] = score(tr, live_era_d(tr))
            trc = {}
            o = cand_walk(tr, ref="control_at_close", trace=trc)
            r.refs["control_at_close"] = score(tr, o)
            r.ref_outs["control_at_close"] = (o, trc)
        rows.append(r)
    return rows


# ═══════════════════════════ gates (no outcome totals) ═══════════════════════════
def run_gates(inp, trades, rows, out=print, include_ext=True):
    ok_all = True

    def line(name, ok, msg):
        nonlocal ok_all
        ok_all &= bool(ok)
        out(f"{name:<8} {'PASS' if ok else 'FAIL'}  {msg}")

    # G0: inputs are the pinned bytes
    bad = [f for f, pin in PINNED.items() if not inp.hashes[f].startswith(pin)]
    line("G0", not bad, f"decompressed capture hashes match the pinned prefixes ({len(PINNED)} files)"
         if not bad else f"HASH MISMATCH {bad}")

    # G2: the hookless copy == the live walker on every row
    bad2 = []
    for r in rows:
        okk, k = outs_equal(live_control(r.tr), r.copy0)
        if not okk:
            bad2.append((r.tr.key, k))
        elif r.copy0.get("last_close") is not None and abs(r.copy0["last_close"] - last_close_of(r.tr, r.copy0)) > 1e-9:
            bad2.append((r.tr.key, "last_close derivation"))
    line("G2", not bad2, f"frozen copy with no rule == live walk_arm on all {len(rows)} filled rows "
         f"(status, reason, pending_at, every exit leg to 1e-9)" if not bad2 else f"{len(bad2)} differ, e.g. {bad2[:3]}")

    # G2b: positive evidence that the depth stop ENGAGED (this is the depth_engaged_proof)
    adr_none = [r.tr.key for r in rows if r.tr.adr20 is None]
    ev_bind, ev_nopen = [], []
    stop_above_entry = 0
    for r in rows:
        for e in r.copy0_trace.get("depth", []):
            if e["binding"] and e["raised"]:
                ev_bind.append((r.tr.key, e))
        ex = r.copy0["exits"]
        if r.copy0["final_reason"] == "sma_trail_stop" and ex and ex[-1].get("fill") == "next_open":
            sidx = r.copy0["exit_session"]            # the sale session; the deciding session is one earlier
            dec = r.tr.sessions[sidx - 2][1]["c"]
            if abs(ex[-1]["price"] - dec) > 1e-9:
                ev_nopen.append((r.tr.key, sidx, dec, ex[-1]["price"]))
        if r.copy0["final_reason"] == "stop_hit" and ex and ex[-1]["price"] > r.tr.entry + 1e-9:
            stop_above_entry += 1
    n_next_open = sum(1 for r in rows if r.copy0["final_reason"] == "sma_trail_stop")
    g2b_ok = bool(ev_bind) and bool(ev_nopen)
    line("G2b", g2b_ok,
         f"ADR20 None on {len(adr_none)} of {len(rows)} rows {adr_none[:6]} | sessions where the resting stop = line x (1-ADR20) "
         f"AND raised the stop: {len(ev_bind)} | close-below sales: {n_next_open}, of which priced at a next open that differs "
         f"from the deciding close: {len(ev_nopen)} | stop-hit sales above entry (depth-bound stop): {stop_above_entry}")
    if ev_bind:
        k, e = ev_bind[0]
        out(f"           example stop: {k[0]} {k[1]} session {e['idx']} ({e['d']}) line {e['line']:.4f} ADR20 {e['adr20']:.4f} "
            f"floor {e['floor']:.2f} -> depth stop {e['depth_stop']:.2f} (was {e['resting_before']:.2f})")
    if ev_nopen:
        k, sidx, dec, px = ev_nopen[0]
        out(f"           example sale:  {k[0]} {k[1]} sold session {sidx}: deciding close {dec:.4f}, next open {px:.4f}")

    # G3: every candidate equals the control up to its trigger
    g3_bad = []
    n_cmp = 0
    n_fired = Counter()
    for r in rows:
        for fr in FRAMES:
            if fr in r.copy0["trig"]:
                n_fired[fr] += 1
        for (fr, rule), (o, trc) in r.cand_outs.items():
            n_cmp += 1
            okk, why = g3_compare(r.copy0, o, fr, r.tr.sessions, r.copy0_trace, trc)
            if not okk:
                g3_bad.append((r.tr.key, fr, rule, why))
        o, trc = r.ref_outs["t20_entry_ref"]
        okk, why = g3_compare(r.copy0, o, "A", r.tr.sessions, r.copy0_trace, trc)
        n_cmp += 1
        if not okk:
            g3_bad.append((r.tr.key, "A", "t20_entry_ref", why))
        o, trc = r.ref_outs["control_at_close"]
        n_cmp += 1
        if r.copy0["final_reason"] != "sma_trail_stop":
            okk, k = outs_equal(r.copy0, o)       # no close-below sale on this path -> identical to the control
            if not okk:
                g3_bad.append((r.tr.key, "-", "control_at_close", f"differs on {k} with no close-below sale"))
    line("G3", not g3_bad, f"{n_cmp} candidate/reference x trade walks equal the control on every trade whose trigger never fired, and "
         f"match it up to the trigger bar where it did (Frame A fired on {n_fired['A']} trades, Frame B on {n_fired['B']})"
         if not g3_bad else f"{len(g3_bad)} differ, e.g. {g3_bad[:3]}")

    # G-ext: cannot run
    if include_ext:
        out("G-ext    NOT RUN  the optional prod pull (pre-registration step 3) was REFUSED by the permission system; "
            "no extension attached, the capture alone is the read of record (pull_daily_ext.REFUSED.txt). Positions still "
            "open at 2026-08-28 are marked at their last stored close and counted per arm.")
    return ok_all


# ═══════════════════════════ synthetic self-tests ═══════════════════════════
ENTRY, ORB_LOW, ORB_HIGH = 100.0, 96.0, 100.0
STOP = 2 * ORB_LOW - ORB_HIGH   # 92
R_ORB = ENTRY - ORB_LOW         # 4
RISK = ENTRY - STOP             # 8


def syn_day0(extra=None):
    bars = [dict(m="09:31", o=99.5, h=100.2, l=99.0, c=100.0)]
    for i in range(1, 6):
        bars.append(dict(m=f"09:{31 + i}", o=100.0, h=101.0, l=99.8, c=100.5))
    if extra:
        bars += extra
    bars.append(dict(m="15:59", o=100.5, h=101.0, l=100.5, c=101.0))
    return bars


def syn_trade(sess, prior=None, day0=None, adr=0.05, atr=2.0, ticker="SYN", d0=date(2026, 5, 4)):
    prior = prior if prior is not None else [95.0] * 20
    sessions = [(d0 + timedelta(days=i + 1), b) for i, b in enumerate(sess)]
    tr = Trade(ticker, d0, ENTRY, ORB_LOW, ORB_HIGH, R_ORB, STOP, day0 or syn_day0(), 0, sessions, prior,
               adr, atr, 101.0)
    return tr


def B(o, h, l, c):
    return dict(o=o, h=h, l=l, c=c)


def s_run(n=30):
    s = [B(101, 115, 100.5, 114), B(116, 135, 115, 130)]
    for k in range(3, n + 1):
        c = 130 + (k - 2)
        s.append(B(c - 1, c + 1, c - 2, c))
    return s


def s_roll():
    s = [B(101, 115, 100.5, 114), B(116, 135, 115, 130)]
    s += [B(130, 131, 129, 130)] * 6                      # s3..s8
    s += [B(127, 128, 107, 108), B(106, 110, 105, 109)]   # s9 closes below the line, s10 opens 106
    s += [B(109, 110, 108, 109)] * 20
    return s


def s_atr():
    s = [B(101, 115, 100.5, 114), B(116, 135, 115, 130), B(131, 141, 130, 135), B(134, 134.5, 131, 133)]
    s += [B(133, 134, 132, 133)] * 26
    return s


def s_gb():
    s = [B(101, 115, 100.5, 114), B(116, 135, 115, 130), B(131, 141, 130, 140), B(139, 139.5, 122, 124),
         B(123, 124, 117, 118), B(117, 118, 115, 116)]
    s += [B(116, 117, 115, 116)] * 24
    return s


def s_gap():
    s = [B(101, 115, 100.5, 114), B(116, 135, 115, 130), B(95, 96, 94, 95)]
    s += [B(95, 96, 94, 95)] * 27
    return s


def s_flat():
    return [B(101, 104, 99, 102)] * 30


def s_pre():
    # control closes below its line BEFORE any +8R: BE touch s1, close 106 < line 110 on s2, sale at s3 open 107
    return [B(113, 115, 112.5, 114), B(113, 114, 105, 106), B(107, 108, 106, 107)] + [B(109, 110, 108, 109)] * 27


PRIOR_PRE = [110.0] * 20


def selftest(out=print):
    fails = []

    def check(name, got, want, tol=1e-6):
        okk = (abs(got - want) <= tol) if isinstance(want, float) else (got == want)
        out(f"  {'ok  ' if okk else 'FAIL'} {name}: got {got!r}" + ("" if okk else f"  want {want!r}"))
        if not okk:
            fails.append(name)

    def run(tr, rule=None, frame=None, ref=None, **kw):
        o = cand_walk(tr, rule=rule, frame=frame, ref=ref, **kw)
        return o, score(tr, o)

    out("synthetic battery (entry 100, stop 92, 1 money-R = 8; +8R partial at 132, +3R arm at 112)")
    tr_run = syn_trade(s_run())
    tr_roll = syn_trade(s_roll())
    tr_atr = syn_trade(s_atr())
    tr_gb = syn_trade(s_gb())
    tr_gap = syn_trade(s_gap())
    tr_flat = syn_trade(s_flat())
    tr_pre = syn_trade(s_pre(), prior=PRIOR_PRE)

    # (0) identity of the hookless copy to the live walker on every scenario
    for nm, tr in [("run", tr_run), ("roll", tr_roll), ("atr", tr_atr), ("gb", tr_gb), ("gap", tr_gap),
                   ("flat", tr_flat), ("pre", tr_pre)]:
        okk, k = outs_equal(live_control(tr), cand_walk(tr))
        check(f"G2 identity copy==live [{nm}]", okk, True)

    # (1) hold-N rules, Frame A: partial at s2 -> sold at the close of session 2+N = 130+N
    for N in (3, 5, 10, 20):
        o, a = run(tr_run, f"t{N}_be", "A")
        want = ((132 - 100) / 3 + (130 + N - 100) * 2 / 3) / 8
        check(f"t{N}_be A exits at the close of session {2 + N}", a.R, want)
        check(f"t{N}_be A reason", o["final_reason"], "time_close")
    # Frame B: BE touch s1, partial still books at s2, hold 3 sessions from s1 -> close of s4 = 132
    o, a = run(tr_run, "t3_be", "B")
    check("t3_be B exits at the close of session 4", a.R, ((132 - 100) / 3 + 32 * 2 / 3) / 8)
    # horizon: the control on the rising series never closes and is marked at the 40th... (30 sessions here)
    c = score(tr_run, live_control(tr_run))
    check("control on a rising series is marked at the last stored close (data end), not sold", c.status, "data_end")

    # (2) chandelier: peak close s3 = 135; atr1 level 133 (touch s4 low 131 -> exit AT the level), atr2 level 131
    o, a = run(tr_atr, "atr1_be", "A")
    check("atr1_be A exits at the level 133", a.R, ((132 - 100) / 3 + 33 * 2 / 3) / 8)
    o, a = run(tr_atr, "atr2_be", "A")
    check("atr2_be A exits at the level 131", a.R, ((132 - 100) / 3 + 31 * 2 / 3) / 8)

    # (3) give-back: peak 140; gb25 floor 130 -> close 124 decides at s4, sold at s5 OPEN 123; gb50 floor 120 -> s5 close 118 decides, s6 open 117
    o, a = run(tr_gb, "gb25_be", "A")
    check("gb25_be A sells at the NEXT open (123), not the deciding close (124)", a.R, ((132 - 100) / 3 + 23 * 2 / 3) / 8)
    o, a = run(tr_gb, "gb50_be", "A")
    check("gb50_be A sells at the NEXT open (117)", a.R, ((132 - 100) / 3 + 17 * 2 / 3) / 8)

    # (4) line rules after the partial: close_only rests F=100 only and sells at the next open 106 (not the close 108);
    #     sma10_depth is stopped by its depth stop; sma20_depth (lower line) is not, and sells at the next open
    o, a = run(tr_roll, "close_only", "A")
    check("close_only A: close below the line -> NEXT open 106", a.R, ((132 - 100) / 3 + 6 * 2 / 3) / 8)
    check("close_only A: priced at a next open != the deciding close", o["exits"][-1]["price"] != 108.0, True)
    sma10_s8 = (2 * 95 + 114 + 130 * 7) / 10
    rest10 = round(sma10_s8 - 1.0 * 0.05 * sma10_s8, 2)
    o, a = run(tr_roll, "sma10_depth", "A")
    check(f"sma10_depth A: stopped at its depth stop {rest10}", a.R, ((132 - 100) / 3 + (rest10 - 100) * 2 / 3) / 8)
    o, a = run(tr_roll, "sma20_depth", "A")
    check("sma20_depth A: single lower line -> not stopped, sells at the next open 106", a.R, ((132 - 100) / 3 + 6 * 2 / 3) / 8)
    c = score(tr_roll, live_control(tr_roll))
    check("control (max of both lines) on the same bars is stopped at the SMA10 depth stop", c.R, ((132 - 100) / 3 + (rest10 - 100) * 2 / 3) / 8)

    # (5) gap through the resting stop: fills at the open 95, not at F=100
    o, a = run(tr_gap, "t3_be", "A")
    check("gap through F: fills at the open 95", a.R, ((132 - 100) / 3 + (95 - 100) * 2 / 3) / 8)
    check("gap_through flag set", o["gap_through"], True)

    # (6) no trigger -> every candidate IS the control
    c0 = cand_walk(tr_flat)
    allsame = all(outs_equal(c0, cand_walk(tr_flat, rule=r, frame=f))[0] for f in FRAMES for r in RULES)
    check("no-trigger identity: all 22 arms equal the control on a flat path", allsame, True)
    check("flat path never fires either trigger", len(c0["trig"]), 0)

    # (7) day-0 breakeven touch hands over at session 1 (Frame B)
    day0 = syn_day0(extra=[dict(m="10:00", o=101.0, h=113.0, l=100.8, c=112.0)])
    tr_d0 = syn_trade([B(112, 113, 111, 112)] * 30, day0=day0)
    c0 = cand_walk(tr_d0)
    check("Frame B trigger on day 0 recorded at index 0", c0["trig"].get("B", {}).get("idx"), 0)
    o, a = run(tr_d0, "t3_be", "B")
    check("Frame B day-0 trigger: t3 sells at the close of session 3 (112)", a.R, (112 - 100) / 8)

    # (8) F above entry at the trigger: the orderable form rests at F, #687's reference resets to entry
    prior_hi = [105.0] * 20
    s = [B(101, 115, 100.5, 114), B(116, 135, 115, 130), B(129, 131, 100.3, 130)] + [B(130, 131, 129, 130)] * 27
    tr_f = syn_trade(s, prior=prior_hi)
    c0 = cand_walk(tr_f)
    Fa = c0["trig"]["A"]["F"]
    check("F at the Frame-A trigger sits ABOVE entry (depth stop had ratcheted)", Fa > 100.0, True)
    o, a = run(tr_f, "t20_be", "A")
    check("orderable t20_be: low 100.3 <= F -> stopped at F", o["final_reason"], "stop_hit")
    o2, a2 = run(tr_f, "t20_be", "A", ref="t20_entry_ref")
    check("t20_entry_ref: stop reset to entry 100 -> low 100.3 does NOT stop it", o2["final_reason"] != "stop_hit", True)

    # (9) control_at_close prices the close-below sale at the deciding close
    o, a = run(tr_roll, None, None, ref="control_at_close")
    c = score(tr_roll, live_control(tr_roll))
    check("control_at_close differs from the control only where a close-below sale occurs (this path is a stop-hit: equal)", abs(a.R - c.R) < 1e-9, True)
    # a path with a real close-below sale: shrink the depth stop out of reach (no ADR20 -> floor only)
    tr_roll_noadr = syn_trade(s_roll(), adr=None)
    c = score(tr_roll_noadr, live_control(tr_roll_noadr))
    o, a = run(tr_roll_noadr, None, None, ref="control_at_close")
    check("no-ADR path: control sells at next open 106", c.R, ((132 - 100) / 3 + 6 * 2 / 3) / 8)
    check("control_at_close sells at the deciding close 108", a.R, ((132 - 100) / 3 + 8 * 2 / 3) / 8)

    # (10) the mutation: apply the candidate BEFORE the trigger -> G3 must go RED
    ctrl_copy = cand_walk(tr_pre)
    cs = score(tr_pre, live_control(tr_pre))
    check("pre scenario: control sells on a close-below at s2 (next open 107) before any +8R", cs.final_reason, "sma_trail_stop")
    good = cand_walk(tr_pre, rule="t20_be", frame="A")
    okg, _ = g3_compare(ctrl_copy, good, "A", tr_pre.sessions)
    check("G3 stays GREEN for the honest candidate (trigger never fires -> identical)", okg, True)
    bad = cand_walk(tr_pre, rule="t20_be", frame="A", mutate_early=True)
    okb, why = g3_compare(ctrl_copy, bad, "A", tr_pre.sessions)
    check("MUTATION (candidate applied before the trigger) turns G3 RED", okb, False)
    # Frame B: honest candidate on the same bars (B trigger = s1) is identical up to s1 and then OWNS the walk
    ctrl_trc, hon_trc = {}, {}
    cc = cand_walk(tr_pre, trace=ctrl_trc)
    hon = cand_walk(tr_pre, rule="t20_be", frame="B", trace=hon_trc)
    okh, why = g3_compare(cc, hon, "B", tr_pre.sessions, ctrl_trc, hon_trc)
    check("Frame B honest candidate: G3 GREEN (identical up to the trigger bar)", okh, True)
    check("Frame B honest candidate DIFFERS from the control after the trigger (it holds; the control sold)",
          score(tr_pre, hon).R != score(tr_pre, live_control(tr_pre)).R, True)
    # Frame B mutation on bars where the control closes below its line BEFORE the +3R arm ever trades
    tr_pre2 = syn_trade([B(108, 109, 105, 106), B(105, 106, 104, 105)] + [B(105, 106, 104, 105)] * 28, prior=PRIOR_PRE)
    ctrl_trc, bad_trc = {}, {}
    cc = cand_walk(tr_pre2, trace=ctrl_trc)
    check("pre2 scenario: control sells on a close-below at s1 (next open 105), B trigger never fires",
          (score(tr_pre2, live_control(tr_pre2)).final_reason, len(cc["trig"])), ("sma_trail_stop", 0))
    bb = cand_walk(tr_pre2, rule="t20_be", frame="B", mutate_early=True, trace=bad_trc)
    okb2, why2 = g3_compare(cc, bb, "B", tr_pre2.sessions, ctrl_trc, bad_trc)
    check("MUTATION in Frame B turns G3 RED too", okb2, False)

    # (11) orderability: the resting stop never steps down in the orderable arms (F >= entry, ratchet only)
    for nm, tr in [("run", tr_run), ("roll", tr_roll), ("f", tr_f)]:
        for fr in FRAMES:
            for rule in RULES:
                trc = {}
                cand_walk(tr, rule=rule, frame=fr, trace=trc)
                ses = [s_ for s_ in trc.get("sessions", []) if s_["owned"]]
                dec = any(ses[i + 1]["resting_in"] < ses[i]["resting_in"] - 1e-9 for i in range(len(ses) - 1))
                if dec:
                    fails.append(f"resting decreased {nm} {fr} {rule}")
    check("no orderable arm ever steps its resting stop DOWN after the trigger", not any("resting decreased" in f for f in fails), True)

    # (12) the statistics, on constructed data with known answers
    rng_ok = signflip_p([1.0] * 10)
    check("sign-flip p on ten equal +1 weeks is tiny (true p = 2/1024)", 0.0003 < rng_ok < 0.006, True)
    check("sign-flip p on a zero difference is 1", signflip_p([0.0] * 8), 1.0)
    check("sign-flip p on offsetting weeks (+1,-1,+1,-1) is large", signflip_p([1.0, -1.0, 1.0, -1.0]) > 0.3, True)
    lo, hi = boot_ci([(2.0, 2)] * 12)
    check("bootstrap CI of a constant mean-1.0 difference collapses to 1.0", (round(lo, 9), round(hi, 9)), (1.0, 1.0))
    check("percentile (linear): p90 of 0..10 is 9.0", pctile(list(range(11)), 0.9), 9.0)

    # (13) the reporting path end to end on a SYNTHETIC population (no real number is touched)
    global OUTDIR
    import tempfile
    old_out = OUTDIR
    OUTDIR = tempfile.mkdtemp(prefix="recut_dry_")
    try:
        scen = [(s_run(), None), (s_roll(), None), (s_atr(), None), (s_gb(), None), (s_gap(), None), (s_flat(), None)]
        syn_rows_trades = []
        for i in range(24):
            sess, _ = scen[i % len(scen)]
            syn_rows_trades.append(syn_trade(sess, ticker=f"S{i:02d}", d0=date(2026, 4, 13) + timedelta(days=7 * (i // 2) + i % 2)))
        rows = run_population(syn_rows_trades)
        stub = Inputs([{"t": tr.t, "d": tr.d.isoformat()} for tr in syn_rows_trades], {}, {}, [], {})
        lines = []
        res = do_run(stub, syn_rows_trades, Counter(filled=len(syn_rows_trades)), rows, out=lines.append)
        check("dry-run of do_run completes and returns a verdict word", res["verdict"]["word"] in ("PROPOSAL", "STANDS", "TOO FEW"), True)
        check("dry-run wrote its rows file", len(open(f"{OUTDIR}/run_rows.tsv").read().splitlines()), len(rows) + 1)
        gl = []
        gate_ok = run_gates(Inputs(stub.rows_u, {}, {}, [], {f: PINNED[f] + "0" * 10 for f in PINNED}), syn_rows_trades, rows, out=gl.append)
        check("gates run on the synthetic population (G0 consumes stub hashes; G2/G3 must be green)",
              all(("PASS" in l) for l in gl if l.startswith(("G0", "G2 ", "G3"))), True)
        # a hand check: the 4 copies of s_run (24/6) under Frame A t20_be all read 5.5R; control marked at data end
        tt = [r for r in rows if r.tr.t in ("S00", "S06", "S12", "S18")]
        check("synthetic s_run copies: primary arm R = 5.5 on all four", [round(r.arms[PRIMARY].R, 6) for r in tt], [5.5] * 4)
    finally:
        OUTDIR = old_out

    out(f"selftest: {'ALL PASS' if not fails else 'FAILURES: ' + str(fails)}")
    return not fails


# ═══════════════════════════ measures ═══════════════════════════
def measure(name, rows, getarm, frame=None):
    """Paired against the control on the trades both settle or mark."""
    pairs = []
    for r in rows:
        a = getarm(r)
        if a.R is not None and r.ctrl.R is not None:
            pairs.append((r, a))
    n = len(pairs)
    d = {"name": name, "frame": frame, "paired_n": n}
    if n == 0:
        return d
    R = [a.R for _, a in pairs]
    C = [r.ctrl.R for r, _ in pairs]
    delta = [x - y for x, y in zip(R, C)]
    keys = [r.tr.key for r, _ in pairs]
    engaged = [i for i, (r, _) in enumerate(pairs) if frame and frame in r.copy0["trig"]]
    differ = [i for i in range(n) if abs(delta[i]) > 0.005]
    d.update(engaged_n=len(engaged) if frame else None, differ_n=len(differ))
    d["differ_weeks"] = len({pairs[i][0].tr.week for i in differ})
    d["n_tail"] = sum(1 for x in R if x >= TAIL_R - 1e-9)
    d["n_tail_ctrl"] = sum(1 for x in C if x >= TAIL_R - 1e-9)
    d["n_be"] = sum(1 for x in R if x >= BE_R - 1e-9)
    d["n_be_ctrl"] = sum(1 for x in C if x >= BE_R - 1e-9)
    d["p90"] = pctile(R, 0.9)
    best = max(range(n), key=lambda i: R[i])
    d["best"] = (keys[best], R[best])
    d["tail_lost"] = [keys[i] for i in range(n) if C[i] >= TAIL_R - 1e-9 and R[i] < TAIL_R - 1e-9]
    d["tail_gained"] = [keys[i] for i in range(n) if C[i] < TAIL_R - 1e-9 and R[i] >= TAIL_R - 1e-9]
    d["total"] = sum(R)
    d["mean"] = sum(R) / n
    d["median"] = statistics.median(R)
    d["win"] = sum(1 for x in R if x > 0) / n
    d["ctrl_total"] = sum(C)
    d["delta_total"] = sum(delta)
    d["delta_mean"] = sum(delta) / n
    srt = sorted(R, reverse=True)
    d["drop_best2"] = sum(R) - sum(srt[:2])
    pos = sorted(((x, i) for i, x in enumerate(delta) if x > 1e-12), reverse=True)
    top2 = pos[:2]
    d["top2_contrib"] = [(keys[i], x) for x, i in top2]
    d["delta_ex_top2"] = sum(delta) - sum(x for x, _ in top2)
    top5 = pos[:5]
    d["top5"] = [(keys[i], x) for x, i in top5]
    d["top5_share"] = (sum(x for x, _ in top5) / sum(delta)) if sum(delta) > 1e-12 else None
    # time
    mo = defaultdict(lambda: [0.0, 0])
    for (r, _), x in zip(pairs, delta):
        k = r.tr.d.strftime("%Y-%m")
        mo[k][0] += x
        mo[k][1] += 1
    d["by_month"] = {k: (round(v[0], 3), v[1]) for k, v in sorted(mo.items())}
    h1 = [x for (r, _), x in zip(pairs, delta) if r.tr.d <= H1_END]
    h2 = [x for (r, _), x in zip(pairs, delta) if r.tr.d > H1_END]
    d["h1"], d["h1_n"], d["h2"], d["h2_n"] = sum(h1), len(h1), sum(h2), len(h2)
    # separation
    blocks = defaultdict(lambda: [0.0, 0])
    for (r, _), x in zip(pairs, delta):
        blocks[r.tr.week][0] += x
        blocks[r.tr.week][1] += 1
    d["n_blocks"] = len(blocks)
    d["p_weekblock"] = signflip_p([v[0] for v in blocks.values()])
    d["boot_lo"], d["boot_hi"] = boot_ci([(v[0], v[1]) for v in blocks.values()])
    # capture on engaged trades (ratio of sums: arm R / best close reached, in R)
    eng = [(pairs[i][0], pairs[i][1]) for i in engaged]
    bc = [(a.R, best_close_r(r.tr, a)) for r, a in eng if best_close_r(r.tr, a) > 0]
    d["capture"] = (sum(x for x, _ in bc) / sum(y for _, y in bc)) if bc else None
    d["capture_n"] = len(bc)
    # costs
    d["worst"] = (keys[min(range(n), key=lambda i: R[i])], min(R))
    d["loss_beyond_1p5"] = sum(1 for x in R if x < -1.5 - 1e-9)
    d["giveback"] = sum(1 for (r, a), x in zip(pairs, R) if mfe_r(r.tr, a) >= BE_R and x <= 1e-9)
    d["open_horizon"] = sum(1 for _, a in pairs if a.status == "horizon")
    d["open_data_end"] = sum(1 for _, a in pairs if a.status == "data_end")
    # engaged / orderability extras
    if frame:
        Fs = [(r.copy0["trig"][frame]["F"] - r.tr.entry) / r.tr.risk for r, _ in eng]
        d["F_above_entry"] = sum(1 for x in Fs if x > 1e-9)
        d["F_median_R"] = statistics.median(Fs) if Fs else None
        d["F_min_R"] = min(Fs) if Fs else None
    return d


def fmt_row(d):
    if d.get("paired_n", 0) == 0:
        return f"{d['name']:<22} no paired trades"
    return (f"{(d['frame'] or '-'):<2} {d['name']:<17} n={d['paired_n']:<4} eng={d.get('engaged_n') if d.get('engaged_n') is not None else '-':<4} "
            f"diff={d['differ_n']:<4} 4R={d['n_tail']}({100 * d['n_tail'] / d['paired_n']:.1f}%) 1.5R={d['n_be']} p90={d['p90']:+.2f} "
            f"tot={d['total']:+.2f} mean={d['mean']:+.4f} dTot={d['delta_total']:+.2f} dEx2={d['delta_ex_top2']:+.2f} "
            f"drop2={d['drop_best2']:+.2f} H1/H2={d['h1']:+.2f}/{d['h2']:+.2f} p={d['p_weekblock']:.4f} med={d['median']:+.3f} "
            f"win={100 * d['win']:.1f}% open(h/e)={d['open_horizon']}/{d['open_data_end']}")


def verdict(m, orderable_ok):
    P1 = m["differ_n"] >= 10 and m["differ_weeks"] >= 6
    P2 = m["delta_total"] > 0 and m["p_weekblock"] < 0.05
    P3 = m["delta_ex_top2"] > 0
    P4 = m["h1"] > 0 and m["h2"] > 0
    P5 = m["n_tail"] >= m["n_tail_ctrl"]
    P6 = orderable_ok
    if not P1:
        word = "TOO FEW"
    elif P2 and P3 and P4 and P5 and P6:
        word = "PROPOSAL"
    else:
        word = "STANDS"
    return dict(P1=P1, P2=P2, P3=P3, P4=P4, P5=P5, P6=P6, word=word)


# ═══════════════════════════ the run ═══════════════════════════
def do_run(inp, trades, acct, rows, out=print):
    out("=" * 100)
    out("RUNNER RE-CUT - THE RUN (read of record = the capture alone; extension pull REFUSED)")
    out("=" * 100)
    out(f"population: {len(inp.rows_u)} Run-U replayable rows on {len({a['t'] for a in inp.rows_u})} tickers; "
        f"{dict(acct)}")
    cst = Counter(r.ctrl.status for r in rows)
    out(f"control walk status over {len(rows)} filled trades: {dict(cst)}   (settled = sold; horizon = marked at the 40th "
        f"close; data_end = still open at 2026-08-28, marked at the last stored close; gap = a session missing INSIDE the "
        f"capture, unscoreable; abstain = same-bar order unknowable)")
    scored = [r for r in rows if r.ctrl.R is not None]
    out(f"control scored n={len(scored)}; Frame A trigger (the +8 ORB-R partial) fired on "
        f"{sum(1 for r in scored if 'A' in r.copy0['trig'])}; Frame B trigger (the +3 ORB-R arm) fired on "
        f"{sum(1 for r in scored if 'B' in r.copy0['trig'])}; control R>=+4.0 on {sum(1 for r in scored if r.ctrl.R >= 4 - 1e-9)}; "
        f"R>=+1.5 on {sum(1 for r in scored if r.ctrl.R >= 1.5 - 1e-9)}")
    out("")

    # control row (vs itself)
    cR = [r.ctrl.R for r in scored]
    srt = sorted(cR, reverse=True)
    cm = dict(name="control (depth)", n=len(cR), n_tail=sum(1 for x in cR if x >= 4 - 1e-9),
              n_be=sum(1 for x in cR if x >= 1.5 - 1e-9), p90=pctile(cR, 0.9), total=sum(cR), mean=sum(cR) / len(cR),
              drop_best2=sum(cR) - sum(srt[:2]), median=statistics.median(cR), win=sum(1 for x in cR if x > 0) / len(cR),
              open_h=sum(1 for r in scored if r.ctrl.status == "horizon"),
              open_e=sum(1 for r in scored if r.ctrl.status == "data_end"))
    best = max(scored, key=lambda r: r.ctrl.R)
    cm["best"] = (best.tr.key, best.ctrl.R)
    cm["worst"] = min(((r.ctrl.R, r.tr.key) for r in scored))
    cm["loss_beyond_1p5"] = sum(1 for x in cR if x < -1.5 - 1e-9)
    cm["giveback"] = sum(1 for r in scored if mfe_r(r.tr, r.ctrl) >= 1.5 and r.ctrl.R <= 1e-9)
    cm["4r_names"] = sorted(r.tr.key for r in scored if r.ctrl.R >= 4 - 1e-9)
    out(f"CONTROL  n={cm['n']} +4R={cm['n_tail']} ({100 * cm['n_tail'] / cm['n']:.1f}%) +1.5R={cm['n_be']} p90={cm['p90']:+.3f} "
        f"total={cm['total']:+.2f} mean={cm['mean']:+.4f} drop-best-2={cm['drop_best2']:+.2f} median={cm['median']:+.3f} "
        f"win={100 * cm['win']:.1f}% best={cm['best'][0]} {cm['best'][1]:+.2f}R worst={cm['worst'][1]} {cm['worst'][0]:+.2f}R "
        f"losses<-1.5R={cm['loss_beyond_1p5']} give-backs={cm['giveback']} open(h/e)={cm['open_h']}/{cm['open_e']}")
    out(f"  control +4R names: {cm['4r_names']}")
    out("")

    results = {"control": cm, "arms": {}, "refs": {}}
    out("--- PRIMARY ---")
    prim = measure("t20_be (PRIMARY)", rows, lambda r: r.arms[PRIMARY], "A")
    results["arms"]["A|t20_be"] = prim
    out(fmt_row(prim))
    out("")
    out("--- the other 21 arms (EXPLORATORY: cannot produce a proposal) ---")
    for fr in FRAMES:
        for rule in RULES:
            if (fr, rule) == PRIMARY:
                continue
            m = measure(rule, rows, lambda r, k=(fr, rule): r.arms[k], fr)
            results["arms"][f"{fr}|{rule}"] = m
            out(fmt_row(m))
    out("")
    out("--- reference rows (never candidates) ---")
    for nm in REFS:
        m = measure(nm, rows, lambda r, k=nm: r.refs[k], "A" if nm == "t20_entry_ref" else None)
        results["refs"][nm] = m
        out(fmt_row(m))
    out("")

    # the primary in full
    out("--- PRIMARY IN FULL (Frame A t20_be) ---")
    for k in ("paired_n", "engaged_n", "differ_n", "differ_weeks", "n_blocks", "n_tail", "n_tail_ctrl", "n_be", "n_be_ctrl", "p90",
              "total", "ctrl_total", "mean", "median", "win", "delta_total", "delta_mean", "delta_ex_top2", "drop_best2",
              "h1", "h1_n", "h2", "h2_n", "p_weekblock", "boot_lo", "boot_hi", "top5_share", "capture", "capture_n",
              "loss_beyond_1p5", "giveback", "open_horizon", "open_data_end", "F_above_entry", "F_median_R", "F_min_R"):
        out(f"  {k:<16} {prim.get(k)}")
    for k in ("best", "worst", "tail_lost", "tail_gained", "top2_contrib", "top5", "by_month"):
        out(f"  {k:<16} {prim.get(k)}")
    out("")

    # P1-P6 mechanically
    orderable = all(
        all((r.copy0['trig'][fr]['F'] >= r.tr.entry - 1e-9) for r in rows if fr in r.copy0['trig']) for fr in FRAMES)
    dec_any = 0
    for r in rows:
        for k, (o, trc) in r.cand_outs.items():
            ses = [s for s in trc.get("sessions", []) if s["owned"]]
            if any(ses[i + 1]["resting_in"] < ses[i]["resting_in"] - 1e-9 for i in range(len(ses) - 1)):
                dec_any += 1
    orderable = orderable and dec_any == 0
    v = verdict(prim, orderable)
    out("--- THE PRE-REGISTERED BAR, APPLIED MECHANICALLY TO THE PRIMARY ---")
    out(f"  P1 >=10 trades differ AND >=6 distinct entry weeks : {v['P1']}  (differ n={prim['differ_n']}, weeks={prim['differ_weeks']})")
    out(f"  P2 paired total > 0 AND week-block p < 0.05        : {v['P2']}  (delta total={prim['delta_total']:+.3f}, p={prim['p_weekblock']:.4f})")
    out(f"  P3 ahead without its two largest contributors      : {v['P3']}  (delta ex top 2={prim['delta_ex_top2']:+.3f})")
    out(f"  P4 ahead in BOTH halves                            : {v['P4']}  (H1={prim['h1']:+.3f} n={prim['h1_n']}, H2={prim['h2']:+.3f} n={prim['h2_n']})")
    out(f"  P5 +4R count no lower than the control's           : {v['P5']}  (arm {prim['n_tail']} vs control {prim['n_tail_ctrl']})")
    out(f"  P6 orderable live (F>=entry at every trigger; resting stop never stepped down in {len(rows) * len(FRAMES) * len(RULES)} walks): {v['P6']}")
    out(f"  RESULT WORD: {v['word']}")
    results["verdict"] = v
    out("")

    # exploratory registration: largest paired total among arms meeting P1,P3,P4,P5 with unadjusted p<0.05
    cands = []
    for k, m in results["arms"].items():
        if k == "A|t20_be" or m.get("paired_n", 0) == 0:
            continue
        vv = verdict(m, True)
        if vv["P1"] and vv["P3"] and vv["P4"] and vv["P5"] and m["p_weekblock"] < 0.05 and m["delta_total"] > 0:
            cands.append((m["delta_total"], k))
    cands.sort(reverse=True)
    out(f"--- EXPLORATORY: arms meeting P1,P3,P4,P5 with unadjusted p<0.05 and a positive total: {cands if cands else 'NONE'}")
    results["next_primary"] = cands[0][1] if cands else None
    out(f"    registered as the next primary: {results['next_primary'] or 'none'}")
    # frame B expectation check
    wrong = [(k, round(m['delta_mean'], 3), m['p_weekblock'], round(m['h1'], 2), round(m['h2'], 2)) for k, m in results["arms"].items()
             if k.startswith("B|") and m.get("paired_n", 0) and m["delta_mean"] > 0.2 and m["p_weekblock"] < 0.01
             and m["h1"] > 0 and m["h2"] > 0]
    out(f"--- FRAME B EXPECTATION (wrong if any Frame B rule gains > +0.2R a trade with p<0.01 and ahead in both halves): "
        f"{'WRONG: ' + str(wrong) if wrong else 'holds (none does)'}")
    results["frame_b_expectation_wrong"] = wrong

    # marks per arm (the stated limit of the refused pull)
    out("")
    out("--- MARKS PER ARM (positions still open: horizon = marked at the 40th close; data_end = open at 2026-08-28, marked at the last stored close) ---")
    out(f"  control: horizon {cm['open_h']}, data_end {cm['open_e']}, of {cm['n']} scored")
    for k in ["A|t20_be"] + [f"{fr}|{ru}" for fr in FRAMES for ru in RULES if (fr, ru) != PRIMARY]:
        m = results["arms"][k]
        out(f"  {k:<18} horizon {m['open_horizon']}, data_end {m['open_data_end']}, of {m['paired_n']} paired")
    for nm, m in results["refs"].items():
        out(f"  {nm:<18} horizon {m['open_horizon']}, data_end {m['open_data_end']}, of {m['paired_n']} paired")
    # unscored accounting per arm
    out("")
    out("--- UNSCORED PER ARM (abstain / gap) ---")
    unsc = {"control": Counter(r.ctrl.status for r in rows if r.ctrl.R is None)}
    out(f"  control: {dict(unsc['control'])}")
    for k in [(f, ru) for f in FRAMES for ru in RULES]:
        c = Counter(r.arms[k].status for r in rows if r.arms[k].R is None)
        if c:
            out(f"  {k[0]}|{k[1]:<12} {dict(c)}")
    for nm in REFS:
        c = Counter(r.refs[nm].status for r in rows if r.refs[nm].R is None)
        if c:
            out(f"  {nm:<14} {dict(c)}")

    # dumps
    with open(f"{OUTDIR}/run_rows.tsv", "w") as fh:
        cols = ["control"] + [f"{fr}|{ru}" for fr in FRAMES for ru in RULES] + REFS
        fh.write("ticker\tdate\tweek\tstatus_ctrl\ttrigA_idx\ttrigB_idx\t" + "\t".join(cols) + "\n")
        for r in rows:
            vals = [r.ctrl.R] + [r.arms[(fr, ru)].R for fr in FRAMES for ru in RULES] + [r.refs[n].R for n in REFS]
            ta = r.copy0["trig"].get("A", {}).get("idx", "")
            tb = r.copy0["trig"].get("B", {}).get("idx", "")
            fh.write(f"{r.tr.t}\t{r.tr.d}\t{r.tr.week[0]}-W{r.tr.week[1]:02d}\t{r.ctrl.status}\t{ta}\t{tb}\t" +
                     "\t".join("" if v is None else f"{v:.4f}" for v in vals) + "\n")
    json.dump(results, open(f"{OUTDIR}/run_results.json", "w"), indent=1, default=str)
    out(f"\nwrote {OUTDIR}/run_rows.tsv and {OUTDIR}/run_results.json")
    return results


# ═══════════════════════════ hand-traces ═══════════════════════════
def sma(xs, w):
    return sum(xs[-w:]) / w if len(xs) >= w else None


def do_trace(inp, trades, rows, out=print):
    out("HAND-TRACES: the FIRST trade in entry order that shows each event; every number below is recomputed from the raw bars")
    out("with independent arithmetic (no library calls), then compared with the walker's own answer.\n")
    ev1 = next((r for r in rows if r.ctrl.status == "settled" and r.ctrl.final_reason == "sma_trail_stop"
                and r.ctrl.out["exits"][-1].get("fill") == "next_open"), None)
    ev2 = next((r for r in rows if r.arms[PRIMARY].partial and r.arms[PRIMARY].status == "settled"
                and r.arms[PRIMARY].final_reason == "time_close"), None)
    for title, r, which in (("EVENT 1: the control's first depth next-open sale", ev1, "control"),
                            ("EVENT 2: the primary's first +8R partial followed by a t20 time exit", ev2, "primary")):
        out("=" * 100)
        out(title)
        if r is None:
            out("  NO TRADE in the population shows this event (reported, not substituted).")
            if which == "primary":
                alt = next((r for r in rows if r.arms[PRIMARY].partial and r.arms[PRIMARY].R is not None), None)
                out(f"  for the record, the first trade with a +8R partial under the primary: "
                    f"{alt.tr.key if alt else 'none'} (exit {alt.arms[PRIMARY].final_reason if alt else '-'})")
            continue
        tr = r.tr
        out(f"  {tr.t} entry date {tr.d}: ORB high {tr.orb_high} low {tr.orb_low}; entry {tr.entry}; ORB-R {tr.r_orb:.4f}; "
            f"placed stop 2*low-high = {2 * tr.orb_low - tr.orb_high:.4f}; money-R unit {tr.risk:.4f}")
        out(f"  +3 ORB-R arm {tr.entry + 3 * tr.r_orb:.4f}; +8 ORB-R partial {tr.entry + 8 * tr.r_orb:.4f}")
        pre = [x for x in inp.daily[tr.t] if x[0] < tr.d][-20:]
        pre = [x for x in pre if x[0] >= tr.d - timedelta(days=60)]
        adr = sum((x[2] - x[3]) / x[4] for x in pre) / len(pre) if len(pre) >= 10 else None
        out(f"  ADR20 = mean (high-low)/close over the {len(pre)} sessions before entry = {adr}   (walker input {tr.adr20})")
        closes = list(tr.prior)
        out(f"  prior closes in [entry-40d, entry-1]: {len(closes)} values, last 3 {closes[-3:]}")
        arm = r.ctrl if which == "control" else r.arms[PRIMARY]
        trc = {}
        o = cand_walk(tr, trace=trc) if which == "control" else cand_walk(tr, rule="t20_be", frame="A", trace=trc)
        out(f"  triggers recorded: {o['trig']}")
        resting = None
        out(f"  {'idx':>3} {'date':<10} {'open':>8} {'high':>8} {'low':>8} {'close':>8} {'SMA10':>8} {'SMA20':>8} "
            f"{'resting in':>10} {'decision':<28}")
        run_closes = []
        for s in trc["sessions"]:
            run_closes.append(s["c"])
            tc = closes + run_closes
            s10, s20 = sma(tc, 10), sma(tc, 20)
            line = max(x for x in (s10, s20) if x is not None) if (s10 or s20) else None
            dec = "owned by candidate" if s["owned"] else "control"
            if s["closed"]:
                dec += f" -> {s['reason']}"
            out(f"  {s['idx']:>3} {s['d']:<10} {s['o']!s:>8} {s['h']:>8.2f} {s['l']:>8.2f} {s['c']:>8.2f} "
                f"{(s10 or 0):>8.3f} {(s20 or 0):>8.3f} {s['resting_in']:>10.2f} {dec:<28}")
        for e in trc.get("depth", []):
            if e["binding"]:
                line_r = round(e["line"], 2)
                indep = max(round(e["floor"], 2), round(line_r - 1.0 * adr * line_r, 2)) if adr else None
                out(f"    depth stop on session {e['idx']}: line {e['line']:.4f} -> independent {indep} vs walker {e['depth_stop']:.2f}")
                break
        last = o["exits"][-1]
        out(f"  legs: {[(l['reason'], round(l['price'], 4), round(l['shares'], 4)) for l in o['exits']]}")
        out(f"  walker answer: final_reason={o['final_reason']} exit_session={o['exit_session']} R={arm.R:+.4f}")
        # independent R
        pnl = sum((l['price'] - tr.entry) * l['shares'] for l in o["exits"])
        out(f"  independent R = sum((price-entry)*shares)/money-R = {pnl / tr.risk:+.4f}")
        if which == "control":
            idx = o["exit_session"]
            dec_close = tr.sessions[idx - 2][1]["c"]
            nxt_open = tr.sessions[idx - 1][1]["o"]
            out(f"  the decision: session {idx - 1} closed {dec_close} below its line; the sale is session {idx}'s OPEN {nxt_open} "
                f"(walker price {last['price']}): {'MATCH' if abs(nxt_open - last['price']) < 1e-9 else 'MISMATCH'}; "
                f"differs from the deciding close: {abs(nxt_open - dec_close) > 1e-9}")
        else:
            trigA = o["trig"]["A"]
            exit_i = trigA["idx"] + 20
            c20 = tr.sessions[exit_i - 1][1]["c"]
            out(f"  trigger session {trigA['idx']} (session 0 of the hold), F = {trigA['F']:.4f}; the 20th session after it is "
                f"{exit_i}, close {c20}; walker exit price {last['price']}: {'MATCH' if abs(c20 - last['price']) < 1e-9 else 'MISMATCH'}")
        out("")


# ═══════════════════════════ main ═══════════════════════════
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--selftest", action="store_true")
    ap.add_argument("--gate", action="store_true")
    ap.add_argument("--run", action="store_true")
    ap.add_argument("--trace", action="store_true")
    ap.add_argument("--ext", action="store_true", help="attach the daily-bar extension (NOT AVAILABLE: the pull was refused)")
    a = ap.parse_args()
    if a.ext:
        print("--ext requested but the optional prod pull was REFUSED; there is no extension file. Run without --ext.")
        sys.exit(3)
    if a.selftest:
        sys.exit(0 if selftest() else 1)
    inp = load_inputs()
    trades, acct = build_trades(inp)
    if a.gate or a.run or a.trace:
        rows = run_population(trades)
    if a.gate:
        print(f"population: {len(inp.rows_u)} rows -> {len(trades)} filled trades {dict(acct)}")
        sys.exit(0 if run_gates(inp, trades, rows) else 1)
    if a.run:
        buf = []
        okg = run_gates(inp, trades, rows, out=buf.append)
        if not okg:
            print("\n".join(buf))
            print("A GATE IS RED - no totals printed.")
            sys.exit(1)
        print("gates (re-run immediately before the run):")
        print("\n".join(buf))
        print()
        do_run(inp, trades, acct, rows)
    if a.trace:
        do_trace(inp, trades, rows)


if __name__ == "__main__":
    main()
