#!/usr/bin/env python3
"""#594 re-score — VERIFIER-CORRECTION CHECKS (2026-10-10, branch wk1010/594-rescore-fix).

LOCAL · $0 · NO NETWORK. Reads `bars.tsv` + the two fixtures through the committed `run_score.py`
(imported unchanged); prints a text report. Re-runnable at will:

    python scripts/probes/_594_rescore/fix_checks.py > scripts/probes/_594_rescore/fix_checks_out.txt

MEASUREMENT ONLY. Nothing here changes a rule, threshold, filter or trade behaviour, and nothing
here is a proposal to — any change to admission is his (THE LINE). No cutline is searched: every
cap used below (50, 75) already existed before this study.

WHAT IT ANSWERS (one section each, matching the corrections to the 10-10 doc):
  1. WINDOW FORK  — what moves if ONLY the extension rule's lookback changes (5 -> 20 sessions),
                    at today's cap 50 and at the cap-75 value the 08-25 study used.
  2. DATA SEAMS   — bars that cross a ticker-reuse seam (another company's history under the same
                    symbol) or an unadjusted split; what the four affected series look like, and
                    what moves when the other company's bars are removed.
  3. ERA          — the live gate's formula changed in commit 38e86996 (2026-04-16); the dates
                    that predate it, and what the OLD formula would have said on them.
  4. OUTCOME ON SCREEN — his verdicts vs the 20-day result, split by session, and the standard
                    errors behind the 'which field leans' sentence.
"""
from __future__ import annotations

import sys
from collections import Counter, defaultdict
from datetime import date, timedelta
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import run_score as RS  # noqa: E402  (the committed driver, unchanged)

P = print
A_STATE = RS.load_alert_state()
POPS = {"real_eps(31)": RS.EPS, "approved(14)": RS.APPROVED, "bad(25)": RS.BAD,
        "other(6)": RS.OTHER, "pointed-at(4)": RS.POINTED}


def rej_by_field(rf, field: str, cap: float, pl):
    out = []
    for t, d, *_ in pl:
        v = (rf(t, d) or {}).get(field)
        if v is not None and v >= cap:
            out.append((t, d))
    return out


def names(lst):
    return ", ".join(f"{t} {d[5:]}" for t, d in lst) or "none"


# ───────────────────────────────────────────────────────────────────────────────────────
P("=" * 100)
P("1. WINDOW FORK — only the lookback moves; the basis is the live gate's own (lowest CLOSE)")
P("=" * 100)
P("   live gate as coded  = extension_live_pct (lowest close over the prior 10 CALENDAR days, ~5 sessions)")
P("   20-session version  = ext_close_pct_20  (lowest close over the prior 20 SESSIONS; same formula, longer reach)")
P("   (the low-based run-up used by the committed ANCHOR75 scorer is a DIFFERENT basis; shown last, for reference)")
P()
rows = [("live gate, cap 50 (today)", "extension_live_pct", 50.0),
        ("live gate, cap 75 (08-22..08-28 value)", "extension_live_pct", 75.0),
        ("20-session close version, cap 50", "ext_close_pct_20", 50.0),
        ("20-session close version, cap 75", "ext_close_pct_20", 75.0),
        ("20-session LOW-based run-up, cap 75 (=ANCHOR75)", "runup_low_pct_20", 75.0)]
RS_FORK = {}
for label, fld, cap in rows:
    P(f"[{label}]  field={fld} >= {cap:g}")
    cell = {}
    for pn, pl in POPS.items():
        rej = rej_by_field(RS.read_for, fld, cap, pl)
        cell[pn] = rej
        extra = ""
        if pn == "bad(25)":
            hi = [x for x in rej if A_STATE.get(x) == "HIGH"]
            extra = f"   | of the 10 alerted HIGH: {len(hi)} ({names(hi)})"
        P(f"   {pn:14s} rejected {len(rej):2d} of {len(pl):2d} -> {names(rej)}{extra}")
    RS_FORK[label] = cell
    P()
base = set(RS_FORK["live gate, cap 50 (today)"]["bad(25)"])
w50 = set(RS_FORK["20-session close version, cap 50"]["bad(25)"])
P(f"window-only change at cap 50: bad charts it adds beyond the live gate: {names(sorted(w50 - base))}"
  f" | live-gate catches it would drop: {names(sorted(base - w50))}")
P("   alert tier of each added bad chart: "
  + ", ".join(f"{t} {d[5:]} = {A_STATE.get((t, d), 'no alert row')}" for t, d in sorted(w50 - base)))
for pn in ("real_eps(31)", "approved(14)", "other(6)", "pointed-at(4)"):
    add = [x for x in RS_FORK["20-session close version, cap 50"][pn] if x not in RS_FORK["live gate, cap 50 (today)"][pn]]
    P(f"   {pn:14s} rejected ONLY by the 20-session version at cap 50 (not by the live gate): {names(add)}")
# who exactly: the approved dates and EPs that the window change rejects, with the values
P()
P("   values behind the window-only rejections at cap 50 (ext_close_pct_20 vs extension_live_pct):")
for pn in ("real_eps(31)", "approved(14)", "other(6)", "pointed-at(4)", "bad(25)"):
    for t, d in RS_FORK["20-session close version, cap 50"][pn]:
        r = RS.read_for(t, d)
        P(f"     {pn:14s} {t:5s} {d}  20-session {r['ext_close_pct_20']:.1f}%   live {r['extension_live_pct']:.1f}%")
P()
P("   at cap 75, the 20-session LOW-based run-up (ANCHOR75) vs the live gate at 50:")
P(f"     bad: {len(RS_FORK['20-session LOW-based run-up, cap 75 (=ANCHOR75)']['bad(25)'])} of 25  "
  f"real EPs lost {len(RS_FORK['20-session LOW-based run-up, cap 75 (=ANCHOR75)']['real_eps(31)'])} of 31  "
  f"approved lost {len(RS_FORK['20-session LOW-based run-up, cap 75 (=ANCHOR75)']['approved(14)'])} of 14")
P(f"   at cap 75, the 20-session CLOSE version: bad {len(RS_FORK['20-session close version, cap 75']['bad(25)'])} of 25  "
  f"real EPs lost {len(RS_FORK['20-session close version, cap 75']['real_eps(31)'])} of 31  "
  f"approved lost {len(RS_FORK['20-session close version, cap 75']['approved(14)'])} of 14  "
  f"(vs live gate at 75: bad {len(RS_FORK['live gate, cap 75 (08-22..08-28 value)']['bad(25)'])} of 25)")

# ───────────────────────────────────────────────────────────────────────────────────────
P()
P("=" * 100)
P("2. DATA SEAMS — a series that holds another company's bars, or an unadjusted split")
P("=" * 100)
P("   scan: every consecutive pair of stored bars per ticker where open/prev close is >2.5 or <0.4, or the calendar gap exceeds 10 days")
suspects = []
for t, rows_ in sorted(RS.BAR_DATA.items()):
    for a, b in zip(rows_, rows_[1:]):
        pc, o = a["close"], b["open_price"]
        gap = (b["trade_date"] - a["trade_date"]).days
        ratio = o / pc if pc > 0 else 0
        if ratio > 2.5 or ratio < 0.4 or gap > 10:
            suspects.append((t, a["trade_date"], b["trade_date"], pc, o, ratio, gap))
for t, d0, d1, pc, o, ratio, gap in suspects:
    P(f"   {t:5s} {d0} -> {d1}  prev close {pc:g}  next open {o:g}  ratio {ratio:.3f}  calendar gap {gap} days")
P("   (single-day ratios on ABVX, NVTS, OMER, QTTB, QURE, VEEE are one-day moves/gaps with a 1-3 day gap, not seams)")
P()
SEAMS = {"IBTA": date(2024, 4, 18), "MRLN": date(2026, 3, 17), "NIQ": date(2025, 7, 23), "QH": date(2026, 5, 29)}
for t, s in SEAMS.items():
    allb = RS.BAR_DATA[t]
    before = [b for b in allb if b["trade_date"] < s]
    after = [b for b in allb if b["trade_date"] >= s]
    P(f"   {t:5s} seam at {s}: {len(before)} bars before ({before[0]['trade_date']} -> {before[-1]['trade_date']}), "
      f"{len(after)} bars from the seam on ({after[0]['trade_date']} -> {after[-1]['trade_date']})")
P()
P("   ruled-date prior-bar counts for those four, as stored vs counting only bars from the seam on:")
for tk, d, v, rd in RS.ALL45:
    if tk in SEAMS:
        dd = date.fromisoformat(d)
        stored = len([b for b in RS.BAR_DATA[tk] if b["trade_date"] < dd])
        real = len([b for b in RS.BAR_DATA[tk] if SEAMS[tk] <= b["trade_date"] < dd])
        P(f"     {tk:5s} {d} ({v}): stored prior bars {stored}, from the seam on {real}")
P()
cnt = sorted(((RS.read_for(t, d) or {}).get("n_bars"), t, d) for t, d, *_ in RS.ALL45)
P(f"   the 'min 136 prior bars' date: {cnt[0]}   next lowest: {cnt[1]}, {cnt[2]}")
P()
# QH: the split artifact in the run-up
P("   QH 2026-06-18 — the stored series straddles an unadjusted split (0.094 -> 7.8 across a 57-day gap):")
r = RS.read_for("QH", "2026-06-18")
P(f"     as stored: runup_low_pct_20 = {r['runup_low_pct_20']:.1f}%   extension_live_pct = {r['extension_live_pct']:.1f}%   ext_close_pct_20 = {r['ext_close_pct_20']:.1f}%")
qh_post = [b for b in RS.BAR_DATA["QH"] if b["trade_date"] >= SEAMS["QH"] and b["trade_date"] < date(2026, 6, 18)]
lo = min(b["low_price"] for b in qh_post)
pc = qh_post[-1]["close"]
P(f"     post-split bars only ({len(qh_post)} bars, {qh_post[0]['trade_date']} -> {qh_post[-1]['trade_date']}): "
  f"lowest low {lo:g}, prior close {pc:g} -> run-up from lowest low = {(pc - lo) / lo * 100:.1f}%   (>= 75: {(pc - lo) / lo * 100 >= 75})")
P("     bars missing inside the gap (weekdays 2026-04-03 .. 2026-05-28 with no stored row): "
  f"{sum(1 for i in range((date(2026,5,29) - date(2026,4,3)).days) if (date(2026,4,3) + timedelta(days=i)).weekday() < 5)}")

# sensitivity: remove the other company's bars / the pre-split bars and re-score
P()
P("   SENSITIVITY — remove every bar before each seam, then re-score with the committed arms:")


def snapshot_verdicts(tag):
    RS._cache.clear()
    rf, rf13 = RS.make_read_for(), RS.make_read_for(RS.THIRTEEN_MONTH_FLOOR)
    out = {}
    for arm_name, arm in RS.ARMS.items():
        for pn, pl in (("real_eps", RS.EPS), ("approved", RS.APPROVED), ("bad", RS.BAD)):
            rej, _, un = RS.tally(pl, arm, rf=rf)
            out[(arm_name, pn)] = (len(rej), len(pl), len(un), [f"{t} {d[5:]}" for t, d, *_ in rej])
    for wname, f in (("full", rf), ("13m", rf13)):
        for pn, pl in (("real_eps", RS.EPS), ("approved", RS.APPROVED), ("bad", RS.BAD)):
            rej, _, un = RS.tally(pl, RS.arm_v3read, rf=f)
            out[("V3READ-" + wname, pn)] = (len(rej), len(pl), len(un), [f"{t} {d[5:]}" for t, d, *_ in rej])
    aucs = {}
    for fld in RS.AUC_FIELDS:
        bx = [(rf(t, d) or {}).get(fld) for t, d, *_ in RS.BAD]
        ax = [(rf(t, d) or {}).get(fld) for t, d, *_ in RS.APPROVED]
        A, se, n1, n2 = RS.auc(bx, ax)
        aucs[fld] = (A, se)
    labels = {f"{t} {d[5:]}": (rf(t, d) or {}).get("label") for t, d, *_ in RS.ALL45 + [(t, d, None, None) for t, d in RS.EPS]}
    xt: dict = defaultdict(Counter)
    for grp, pl in (("bad", RS.BAD), ("approved", RS.APPROVED), ("real_eps", RS.EPS)):
        for t, d, *_ in pl:
            xt[(rf(t, d) or {}).get("label", "UNREADABLE")][grp] += 1
    aucs["_xtab"] = {k: (v["bad"], v["approved"], v["real_eps"]) for k, v in sorted(xt.items())}
    per_date = {}
    for t, d, *_ in RS.ALL45 + [(t, d, None, None) for t, d in RS.EPS]:
        x = rf(t, d) or {}
        per_date[(t, d)] = (RS.arm_ext50(x), RS.arm_anchor75(x), RS.arm_v3read(x), x.get("label"),
                            None if x.get("overhead_vol_frac") is None else round(x["overhead_vol_frac"], 3),
                            x.get("zones_remaining"), x.get("n_bars"),
                            None if x.get("runup_low_pct_20") is None else round(x["runup_low_pct_20"], 1))
    return out, aucs, labels, per_date


orig = {t: list(v) for t, v in RS.BAR_DATA.items()}
base_out, base_auc, base_lab, base_pd = snapshot_verdicts("as stored")
for variant, seams in (("IBTA + MRLN + NIQ other-company bars removed", {k: SEAMS[k] for k in ("IBTA", "MRLN", "NIQ")}),
                       ("all four seams (QH pre-split bars removed too)", SEAMS)):
    for t, s in seams.items():
        RS.BAR_DATA[t] = [b for b in orig[t] if b["trade_date"] >= s]
    o2, a2, l2, pd2 = snapshot_verdicts(variant)
    P()
    P(f"   >>> variant: {variant}")
    P(f"   {'arm / population':22s} {'as stored':>12s} {'variant':>12s}")
    for key in base_out:
        b, v = base_out[key], o2[key]
        mark = "" if b[:3] == v[:3] and b[3] == v[3] else "   <-- differs"
        P(f"   {key[0] + ' ' + key[1]:22s} {b[0]:>4d} of {b[1]:<3d}  {v[0]:>4d} of {v[1]:<3d}  unread {b[2]}/{v[2]}{mark}"
          + (f"   stored: {', '.join(b[3])} | variant: {', '.join(v[3])}" if mark else ""))
    P("   supply label (bad, approved, real EPs) as stored : " + str(base_auc["_xtab"]))
    P("   supply label (bad, approved, real EPs) variant   : " + str(a2["_xtab"]))
    for fld in RS.AUC_FIELDS:
        P(f"   AUC {fld:20s} as stored {base_auc[fld][0]:.3f} (se {base_auc[fld][1]:.3f})   variant {a2[fld][0]:.3f} (se {a2[fld][1]:.3f})")
    moved = [(k, base_pd[k], pd2[k]) for k in base_pd if base_pd[k] != pd2[k]]
    P(f"   dates (45 rulings + 31 real EPs) where any verdict, label or supply field differs: {len(moved)}")
    for k, b, v in moved:
        P(f"     {k[0]:5s} {k[1]}  stored (EXT50,ANCHOR75,V3READ,label,ovh,zones,n_bars,run20)={b}  variant={v}")
    lab_changes = [(k, base_lab[k], l2[k]) for k in base_lab if base_lab[k] != l2[k]]
    P(f"   label changes: {lab_changes or 'none'}")
    for t in seams:
        RS.BAR_DATA[t] = list(orig[t])
RS.BAR_DATA.update({t: list(v) for t, v in orig.items()})
RS._cache.clear()

# ───────────────────────────────────────────────────────────────────────────────────────
P()
P("=" * 100)
P("3. ERA — the live extension gate's FORMULA (commit 38e86996, committed 2026-04-16 20:40 PT)")
P("=" * 100)
P("   OLD (before the commit): extension_map = the close of the LATEST stored bar with trade_date <= today-8 days (looking back 7 more days); ext = (prev close - that close) / that close")
P("   NEW (from the commit, and replayed everywhere in this study): lowest close over [today-10 days, today)")
cut = date(2026, 4, 16)
pre_rulings = [(t, d, v) for t, d, v, _ in RS.ALL45 if date.fromisoformat(d) <= cut]
pre_eps = [(t, d) for t, d in RS.EPS if date.fromisoformat(d) <= cut]
pre_excl = [(t, d) for t, d in RS.EPS_EXCL if date.fromisoformat(d) <= cut]
pre_pointed = [(t, d, v) for t, d, v in RS.POINTED if date.fromisoformat(d) <= cut]
P(f"   dated on or before 2026-04-16: rulings {len(pre_rulings)} {[(t, d[5:], v) for t, d, v in pre_rulings]}; "
  f"real EPs {len(pre_eps)} (earliest {min(d for _, d in pre_eps)}, latest {max(d for _, d in pre_eps)}); "
  f"excluded EPs {len(pre_excl)}; pointed-at {len(pre_pointed)}")
after = sorted((d, t) for t, d in RS.EPS if date.fromisoformat(d) > cut)
P(f"   first real EP dated after the commit: {after[0][1]} {after[0][0]}")
first_ruling_after = sorted((d, t) for t, d, *_ in RS.ALL45 if date.fromisoformat(d) > cut)[0]
P(f"   first ruling dated after the commit: {first_ruling_after[1]} {first_ruling_after[0]}")
P(f"   rulings before the earliest real EP / all dates: earliest ruled date {min(d for _, d, *_ in RS.ALL45)}; earliest real EP {min(d for _, d in RS.EPS)}")


def old_formula_ext(tk: str, iso: str):
    d = date.fromisoformat(iso)
    cand = [b for b in RS.BAR_DATA[tk] if d - timedelta(days=15) <= b["trade_date"] <= d - timedelta(days=8)]
    prior = [b for b in RS.BAR_DATA[tk] if b["trade_date"] < d]
    if not cand or not prior:
        return None
    ref = cand[-1]["close"]
    return None if ref <= 0 else (prior[-1]["close"] - ref) / ref * 100.0


P()
P("   OLD vs NEW formula on every date that predates the commit (cap 50 on both):")
moved_old = 0
for tk, d in [(t, d) for t, d, _ in pre_rulings] + pre_eps + pre_excl + [(t, d) for t, d, _ in pre_pointed]:
    o = old_formula_ext(tk, d)
    nw = (RS.read_for(tk, d) or {}).get("extension_live_pct")
    flag_o = None if o is None else o >= 50
    flag_n = None if nw is None else nw >= 50
    if flag_o != flag_n:
        moved_old += 1
    P(f"     {tk:5s} {d}  old formula {('n/a' if o is None else f'{o:6.1f}%')} -> {('n/a' if flag_o is None else 'REJ' if flag_o else 'keep')}"
      f"   new formula {('n/a' if nw is None else f'{nw:6.1f}%')} -> {('n/a' if flag_n is None else 'REJ' if flag_n else 'keep')}")
P(f"   dates where the old and new formula give a different cap-50 verdict: {moved_old}")

# ───────────────────────────────────────────────────────────────────────────────────────
P()
P("=" * 100)
P("4. OUTCOME ON SCREEN — his verdict vs the 20-session result, by session; and the lean of each field in standard errors")
P("=" * 100)
bysess = defaultdict(Counter)
mism = []
for grp, pl in (("bad", RS.BAD), ("approved", RS.APPROVED)):
    for t, d, v, rd in pl:
        fw = RS.fwd_ret_20(t, d)
        if fw is None:
            bysess[rd]["no 20-session result"] += 1
            continue
        match = (grp == "bad" and fw < 0) or (grp == "approved" and fw >= 0)
        bysess[rd]["match" if match else "against"] += 1
        if not match:
            mism.append((rd, t, d, v, f"{fw * 100:+.0f}%"))
tot = Counter()
for rd in sorted(bysess):
    c = bysess[rd]
    P(f"   session {rd}: verdict agrees with the later move on {c['match']}, goes against it on {c['against']}"
      + (f", no 20-session result on {c['no 20-session result']}" if c["no 20-session result"] else ""))
    tot.update(c)
P(f"   all sessions: agrees {tot['match']}, against {tot['against']}  (n = {tot['match'] + tot['against']}; the doc's 32 of 38)")
P(f"   verdicts that went AGAINST the later move: {mism}")
P()
P("   lean in standard errors, bad vs approved, all 45 (AUC - 0.5) / se:")
for fld in RS.AUC_FIELDS:
    bx = [(RS.read_for(t, d) or {}).get(fld) for t, d, *_ in RS.BAD]
    ax = [(RS.read_for(t, d) or {}).get(fld) for t, d, *_ in RS.APPROVED]
    A, se, n1, n2 = RS.auc(bx, ax)
    P(f"     {fld:20s} AUC {A:.3f}  se {se:.3f}  (AUC-0.5)/se = {(A - 0.5) / se:+.2f}   n_bad {n1} n_app {n2}")
