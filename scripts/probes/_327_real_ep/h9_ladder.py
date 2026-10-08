"""#327 H9 — stops and targets placed on the SUPPLY LADDER, on the 632 first fires of the 277 real EPs.
2026-10-08. $0, MEASUREMENT ONLY: stops, sizing and the live same-day re-entry ban (R3) are the operator's (THE LINE)
— nothing here proposes, ranks for adoption or changes a live rule. Worked entirely from this folder's captured files:
fires.tsv, alerts.tsv, daily.tsv, minute.tsv.gz (the rerun's loaders), sat_daily_long.tsv (prod mi_daily_closes
2024-01-02..2026-10-05, captured 10-06), summary.json (the rerun's §D runner set + arms), h10_regime.tsv (H10's
regime capture). No prod access, no write outside this folder, no deploy, no commit.

H9 (327_hypotheses_2026-09-27.md §2, VERBATIM):
  What may be wrong: "No stop or target has ever been placed against the supply ladder (his structure model: a cleared
    zone becomes support; "held, not touched" is the strength signal)."
  Fix: "Stop = just below the nearest level the gap cleared (or the gap-fill), target = the next overhead zone; smaller
    size to match. Measurement only."
  Test: "Pop: 632 first fires. Run `_533_nbis_structure_encoder.py` on daily history as of each EP date. Report width
    distribution, fires killed, winner fires kept ≥ 3R (of 11), non-winner mean R, next-zone target hit rate, in R and
    capped dollars. Pass: keeps ≥ 9 of 11 · non-winner mean ≥ −0.14R · ERA B same sign."

═══════════════════════════ PRE-REGISTRATION (written BEFORE any H9 number was computed) ═══════════════════════════
POPULATION: the rerun's 632 first-attempt fires (fires.tsv) on the 277 live EP alerts 2026-05-01..09-11; ERA A =
  alert_date < 2026-08-22 (595 fires / 261 campaigns), ERA B = from 08-22 (37 / 16). NEVER POOLED. ERA A is also shown
  as DISC (alerts <= 08-14) and HOA (08-15..08-21, one week) beside, as the 09-27 harness does. Winner fires = the
  rerun's §D 11 first fires on its 7 big-winner EPs (summary.json D_big_winners, read, never hand-listed); every other
  scored fire is a NON-WINNER.
LADDER (the encoder's logic, imported from scripts/probes/_533_nbis_structure_encoder.py, frozen AS OF THE EP DATE —
  only daily bars strictly before the EP day; no look-ahead):
  * history = sat_daily_long.tsv (encoder's own row filter); a ticker whose rows have a >30-calendar-day hole is CUT
    there (rows before the hole = likely another security on the same ticker: AKTS, LIFE, FIG — counted).
  * ADR for level qualification = the encoder's adr20_pct (pre-EP, %).
  * LADDER Q (PRIMARY — the encoder's congestion ladder): the encoder's QUALIFIED levels (merged daily pivot highs with
    >= 2 failed-test episodes; the 50-day SMA when it acted as resistance) + the available-history high.
  * LADDER P (SECONDARY — the 2026-10-07 pivot-lines note): a line at EVERY prior swing high still alive at the EP
    (encoder pivot definition +-2 days; no daily close above it since; merged within the encoder's 0.3%) + the
    history high; each labelled "N days · X%" (sessions from the swing high to the EP day · depth of the pullback from
    it to the lowest low before the EP).
STOP (per fire, at its recorded entry): support = the highest ladder level L with prior_close < L <= entry (a zone the
  EP move cleared and price still sits on), else the GAP-FILL (prior close) when prior_close <= entry; stop = support −
  0.1 × ADR$ ("just below"; ADR$ = the lane's EP-anchored compute_ep_adr_dollar from fires.tsv). Entry below the
  prior close (gap filled) -> KILLED, counted; a killed winner fire = NOT kept. House width floor 0.5%: a stop
  narrower than that is counted, not scored. Sensitivity (descriptive, never judged): buffer 0.0 and 0.25 × ADR$.
TARGET: the lowest ladder level above the entry ("the next overhead zone"); full exit at that price on the first
  session whose high reaches it; a bar holding both stop and target = STOP (pess). None above -> no target (counted as
  blue sky above the entry; the trail carries it).
INSTRUMENT (the measure the bar's −0.14R was computed on — rerun §D `grid:adr_100/none/trail_max10_20`): rerun.build_row
  (recorded entry) -> p3_grid.first_passages / exit_sessions / cell_r -> rerun.gap_charged, at the FINAL MARK
  Kf = min(20, sessions available to 09-25); the target walk is a price-target copy of first_passages, anchored
  equal to its 1×ADR target on every row before use.
ARMS (4 draws — 2 ladders × 2 arms; the row's instrument is stop + target):
  Q_ST (PRIMARY) ladder-Q stop + next-zone target + the lane's trail (close below max(SMA10, SMA20))
  Q_S            ladder-Q stop + the lane's trail (no target) — the decomposition: what the stop alone does
  P_ST / P_S     the same on the 10-07 pivot-lines ladder
  comparators on the same fires: the lane's own stop + trail; 1×ADR stop + trail.
THE BAR, applied per arm: (1) keeps >= 9 of the 11 winner fires at >= 3R; (2) ERA A non-winner mean R >= −0.14
  (the verbatim number, which the rerun computed on a POOLED A+B rest set — the 1×ADR trail non-winner mean on ERA A
  alone and on ERA B alone is printed beside it as the like-for-like comparator); (3) ERA B SAME SIGN = the sign of
  (arm − 1×ADR trail) non-winner mean R on the same ERA B fires equals that sign in ERA A (ERA B has no winners, so
  the keeps leg is unreadable there); the raw ERA B mean is printed beside. VERDICT = Q_ST (the hypothesis as written);
  Q_S / P_* reported with their own leg results. PASS only if all three legs hold.
BESIDE (never instead): drop-best-two names (by summed R over the non-winner fires) · the >= 3R share · worst loss ·
  a 5 bps-per-side slippage haircut · CAPPED DOLLARS at TODAY's sizing (H10 r2: dollar-R = R × min(regime mult known
  the morning of the fire, 0.20 × stop width ÷ 0.02)) · a week-block sign-flip permutation (seed 327, 2000 draws) on
  the paired non-winner difference vs 1×ADR trail.
EXPECTED BEFORE RUNNING (so a surprise shows): most Q stops sit at the GAP-FILL (few qualified levels lie between the
  prior close and a fire near the EP-day anchors), so stops are WIDE (median ~1.5-3 × ADR) — wider stops keep the
  winners' paths alive but shrink their R, so Q_S keeps <= 7 of 11 and the target arm keeps fewer (a nearby zone caps
  the run); a minority of fires (entries back below the prior close) are killed; non-winner mean near the 1×ADR
  cell; ERA B negative. P has more levels -> tighter stops, more kills by nothing, more nearby targets.

Usage: python3 h9_ladder.py   ->  h9_out.txt, h9_rows.tsv, h9_levels.tsv   (run ONCE; capture once, read many)
"""
from __future__ import annotations

import bisect
import importlib.util
import json
import random
import statistics
import sys
from collections import Counter, defaultdict
from datetime import date
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[2]
sys.path.insert(0, str(HERE))
import rerun                    # noqa: E402  loaders, build_row, gap_charged (inserts REPO / probes / block5 paths)
import p3_grid                  # noqa: E402  first_passages, exit_sessions, cell_r, first_idx
import h10_rescore as h10       # noqa: E402  load_regime, regime_for, frac (today's sizing)
from shared.operator_labelled_eps import OPERATOR_LABELLED_EPS   # noqa: E402

_spec = importlib.util.spec_from_file_location("enc533", REPO / "scripts" / "probes" / "_533_nbis_structure_encoder.py")
enc = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(enc)

ERA_SPLIT = date(2026, 8, 22)
DISC_END = date(2026, 8, 14)
WINDOW = 20
TAIL_R = 3.0
EPS = 1e-9
BUF_ADR = 0.10
BUF_SENS = (0.0, 0.25)
WIDTH_FLOOR_PCT = 0.5
GAP_CUT_DAYS = 30
BAR_KEEP, BAR_NONWIN = 9, -0.14
RISK_PCT_TODAY = 0.02
SLIP_BPS = 0.0005
SEED, N_PERM = 327, 2000
OUT = []


def say(s=""):
    print(s)
    OUT.append(s)


def mean(v):
    return sum(v) / len(v) if v else None


def fm(x, f="{:+.2f}"):
    return "—" if x is None else f.format(x)


def pctl(v, q):
    return float(np.percentile(v, q)) if v else None


def week_of(d):
    y, w, _ = d.isocalendar()
    return f"{y}-W{w:02d}"


# ── long daily history (the encoder's row format) ─────────────────────────────────────────────────────

def load_long():
    by = defaultdict(list)
    for r in rerun.read_tsv(HERE / "sat_daily_long.tsv"):
        o, h, l, c, v = (rerun._f(r[k]) for k in ("open_price", "high_price", "low_price", "close", "volume"))
        if None in (o, h, l, c) or c <= 0 or h <= 0:      # the encoder's own load_daily filter
            continue
        by[r["ticker"]].append((r["trade_date"], o, h, l, c, v or 0.0))
    cuts = {}
    for t in by:
        by[t].sort()
        rows = by[t]
        last_hole = None
        for i in range(1, len(rows)):
            if (date.fromisoformat(rows[i][0]) - date.fromisoformat(rows[i - 1][0])).days > GAP_CUT_DAYS:
                last_hole = i
        if last_hole is not None:
            cuts[t] = (rows[last_hole - 1][0], rows[last_hole][0], last_hole)
            by[t] = rows[last_hole:]
    return dict(by), cuts


# ── the two ladders, frozen as of the EP date ─────────────────────────────────────────────────────────

def _label(days, ia, j, L):
    """'N days · X%' — sessions from the anchor day j to the EP day, depth of the pullback from L to the lowest low
    on days j..ia-1."""
    lo = min(days[k][3] for k in range(j, ia))
    return ia - j, round(100.0 * (1.0 - lo / L), 1)


def ladder_q(days, ia, adr_pct, hist_max):
    levels = enc.pivot_levels(days, ia, adr_pct)
    s50 = enc.sma50_level(days, ia, adr_pct)
    if s50:
        levels.append(s50)
    q = [L for L in levels if L["n_episodes"] >= 2 or L["kind"] == "sma50"]   # the encoder's `qualified`
    out = []
    for L in q:
        lab = (None, None)
        if L["kind"] == "pivot":
            js = [j for j in range(ia) if abs(days[j][2] / L["price"] - 1.0) <= enc.MERGE_PCT / 100.0]
            if js:
                lab = _label(days, ia, js[-1], L["price"])
        out.append({"price": L["price"], "kind": "q_" + L["kind"], "episodes": L["n_episodes"],
                    "days": lab[0], "depth": lab[1]})
    jh = max(range(ia), key=lambda j: (days[j][2], j))
    dh = _label(days, ia, jh, hist_max)
    out.append({"price": hist_max, "kind": "hist_high", "episodes": None, "days": dh[0], "depth": dh[1]})
    return sorted(out, key=lambda x: x["price"])


def ladder_p(days, ia, hist_max):
    W = enc.PIVOT_WING
    highs = [d[2] for d in days[:ia]]
    closes = [d[4] for d in days[:ia]]
    suf = [float("-inf")] * (ia + 1)            # suffix max of closes: suf[i] = max(closes[i:ia])
    for i in range(ia - 1, -1, -1):
        suf[i] = max(closes[i], suf[i + 1])
    piv = []
    for i in range(W, ia - W):
        if highs[i] >= max(highs[i - W:i]) and highs[i] > max(highs[i + 1:i + 1 + W]):
            if suf[i + 1] <= highs[i] * enc.CLOSE_TOL:      # still alive: no daily close above it since
                piv.append(i)
    clusters = []
    for i in sorted(piv, key=lambda i: highs[i]):
        if clusters and highs[i] <= max(highs[j] for j in clusters[-1]) * (1 + enc.MERGE_PCT / 100.0):
            clusters[-1].append(i)
        else:
            clusters.append([i])
    out = []
    for cl in clusters:
        L = max(highs[j] for j in cl)
        lab = _label(days, ia, max(cl), L)
        out.append({"price": L, "kind": "pivot_line", "episodes": len(cl), "days": lab[0], "depth": lab[1]})
    jh = max(range(ia), key=lambda j: (days[j][2], j))
    if not any(abs(x["price"] / hist_max - 1.0) <= enc.MERGE_PCT / 100.0 for x in out):
        dh = _label(days, ia, jh, hist_max)
        out.append({"price": hist_max, "kind": "hist_high", "episodes": None, "days": dh[0], "depth": dh[1]})
    return sorted(out, key=lambda x: x["price"])


def place(ladder, prior_close, entry, adr_dollar, buf):
    """-> dict(stop, support, kind, label, target, target_kind, target_label, killed_why)."""
    if adr_dollar is None or adr_dollar <= 0:
        return {"killed_why": "no_adr"}
    cands = [x for x in ladder if prior_close < x["price"] <= entry]
    if cands:
        sup = max(cands, key=lambda x: x["price"])
        support, kind, lab = sup["price"], sup["kind"], (sup["days"], sup["depth"])
    elif prior_close <= entry:
        support, kind, lab = prior_close, "gap_fill", (None, None)
    else:
        return {"killed_why": "entry_below_gap_fill"}
    stop = support - buf * adr_dollar
    if stop <= 0 or stop >= entry:
        return {"killed_why": "stop_ge_entry_or_le_0"}
    above = [x for x in ladder if x["price"] > entry]
    tg = min(above, key=lambda x: x["price"]) if above else None
    return {"killed_why": None, "stop": stop, "support": support, "kind": kind, "label": lab,
            "n_cleared_below_entry": len(cands),
            "target": tg["price"] if tg else None, "target_kind": tg["kind"] if tg else None,
            "target_label": (tg["days"], tg["depth"]) if tg else (None, None)}


# ── the grid instrument with a ladder stop and a price target ─────────────────────────────────────────

def d0_for(t, row, minutes5):
    """build_row's day-0 source order, reproduced (asserted equal to row['d0_kind'])."""
    if row["level_priced"]:
        return "daily_fold", [(row["day_high"], row["day_low"])]
    bars5 = minutes5.get((t["ticker"], t["fire_date"])) or []
    post5 = [b for b in bars5 if b["m"] > t["fire_minute"]]
    if bars5:
        return "real_intraday_bars", [(b["h"], b["l"]) for b in post5]
    pb = p3_grid.day0_pseudo_bars(t.get("day0_resolved"), t.get("day0_post_low"), t.get("day0_post_high")) \
        if t.get("source") == "lane_recorded" else None
    return ("cached_pseudo_bars", [(b["h"], b["l"]) for b in pb]) if pb is not None else ("no_source", None)


def add_stop(row, name, lvl, d0_kind, d0_bars):
    """The same stop record build_row writes."""
    entry = row["entry"]
    if lvl is None or lvl >= entry or lvl <= 0:
        row["stops"][name] = {"level": lvl, "killed": True, "why": "stop_ge_entry"}
        return
    if d0_kind == "no_source":
        d0_abstain = row["day_low"] is not None and row["day_low"] <= lvl
        d0 = [] if not d0_abstain else None
    else:
        d0_abstain, d0 = False, d0_bars
    row["stops"][name] = {"level": lvl, "killed": False, "risk": entry - lvl,
                          "width_pct": (entry - lvl) / entry * 100.0, "d0_abstain": d0_abstain, "d0_bars": d0}


def fp_price(row, st, tgt):
    """p3_grid.first_passages for ONE stop with a PRICE target (None = no target) — a structural copy."""
    d0 = st["d0_bars"]
    H = np.asarray([h for h, _ in d0] + list(row["_sh"]), dtype=float)
    L = np.asarray([l for _, l in d0] + list(row["_sl"]), dtype=float)
    sessnum = np.asarray([0] * len(d0) + list(range(1, row["n_avail"] + 1)), dtype=int)
    stop_i = p3_grid.first_idx(L <= st["level"]) if len(L) else None
    entry, risk = row["entry"], st["risk"]
    lvl, tR = (None, None) if tgt is None else (tgt, (tgt - entry) / risk)
    tgt_i = p3_grid.first_idx(H >= lvl) if (lvl is not None and len(H)) else None
    if stop_i is None and tgt_i is None:
        pess = opt = (None, None)
        straddle = False
    else:
        if stop_i is not None and (tgt_i is None or stop_i <= tgt_i):
            pess = (int(sessnum[stop_i]), p3_grid.STOP)
        else:
            pess = (int(sessnum[tgt_i]), p3_grid.TARGET)
        if tgt_i is not None and (stop_i is None or tgt_i <= stop_i):
            opt = (int(sessnum[tgt_i]), p3_grid.TARGET)
        else:
            opt = (int(sessnum[stop_i]), p3_grid.STOP)
        straddle = stop_i is not None and tgt_i is not None and stop_i == tgt_i
    return {"pess": pess, "opt": opt, "straddle": straddle, "target_r": tR,
            "tail_eligible": (tR is None) or (tR >= TAIL_R - EPS)}


def score(row, sname, fp, ex):
    """Final-mark R (rerun §D measure). -> dict or None (not scored, with why)."""
    st = row["stops"][sname]
    if st["killed"]:
        return {"status": "killed"}
    if st["d0_abstain"]:
        return {"status": "d0_abstain"}
    Kf = min(WINDOW, row["n_avail"])
    if Kf <= 0:
        return {"status": "no_sessions"}
    stt, R, kind, ev = p3_grid.cell_r(row, st, fp, row["ex"][ex], Kf)
    if stt != "scored":
        return {"status": stt}
    Rg = rerun.gap_charged(row, st, kind, ev, R)
    return {"status": "scored", "R": R, "Rg": Rg, "kind": kind, "ev": ev, "Kf": Kf, "w": st["width_pct"],
            "risk": st["risk"]}


# ── stats ─────────────────────────────────────────────────────────────────────────────────────────────

def drop2_mean(items, key):
    by = defaultdict(float)
    for it in items:
        by[it["ticker"]] += it[key]
    top = sorted(by.items(), key=lambda kv: -kv[1])[:2]
    keep = [it[key] for it in items if it["ticker"] not in {t for t, _ in top}]
    return mean(keep), [f"{t} {v:+.1f}" for t, v in top]


def perm_paired(diffs, weeks):
    if len(diffs) < 2:
        return None
    obs = sum(diffs) / len(diffs)
    blocks = defaultdict(float)
    for d, w in zip(diffs, weeks):
        blocks[w] += d
    sums = list(blocks.values())
    rng = random.Random(SEED)
    n = len(diffs)
    cnt = 0
    for _ in range(N_PERM):
        s = sum(x if rng.random() < 0.5 else -x for x in sums) / n
        if (obs >= 0 and s >= obs - 1e-12) or (obs < 0 and s <= obs + 1e-12):
            cnt += 1
    return (cnt + 1) / (N_PERM + 1)


def main():
    say("#327 H9 — stops and targets on the supply ladder (h9_ladder.py, run 2026-10-08; pre-registration = docstring)")
    say("=" * 118)
    # ── load ──
    fires = rerun.load_fires()
    alerts = rerun.load_alerts()
    daily = rerun.load_daily()
    raw1, dropped = rerun.load_minutes_raw()
    minutes5 = rerun.minutes_to_5min(raw1)
    longd, cuts = load_long()
    summ = json.loads((HERE / "summary.json").read_text())
    runners = set(summ["D_big_winners"]["runners"])               # "TKR|YYYY-MM-DD"
    runner_ids = {f"{k}|{p}" for k in runners for p in rerun.PATTERNS}
    h10.REG = h10.load_regime()
    alert_of = {(a["ticker"], a["ep_date"]): a for a in alerts}
    keys277 = set(alert_of)
    labelled = {(e.ticker, date.fromisoformat(e.alert_date) if isinstance(e.alert_date, str) else e.alert_date)
                for e in OPERATOR_LABELLED_EPS}
    labelled = {k for k in labelled if k in keys277}

    # ── gate ──
    say("GATE / POPULATION")
    nA = sum(1 for f in fires if f["era"] == "A")
    nB = sum(1 for f in fires if f["era"] == "B")
    cA = sum(1 for a in alerts if a["era"] == "A")
    cB = sum(1 for a in alerts if a["era"] == "B")
    ok = (len(fires) == 632 and nA == 595 and nB == 37 and cA == 261 and cB == 16
          and all((f["ticker"], f["ep_date"]) in keys277 for f in fires)
          and all((f["ep_date"] < ERA_SPLIT) == (f["era"] == "A") for f in fires))
    say(f"  fires.tsv {len(fires)} first fires (ERA A {nA}, ERA B {nB}) on {len({(f['ticker'], f['ep_date']) for f in fires})} campaigns; "
        f"alerts ERA A {cA} / ERA B {cB}; era label == alert-date rule: {ok}")
    winner_fires = [f for f in fires if f["id"] in runner_ids]
    say(f"  winner fires (rerun §D runners x patterns, read from summary.json): {len(winner_fires)} on {len(runners)} EPs: "
        + ", ".join(sorted(f"{f['ticker']} {f['rung'].replace('ep_', '')}" for f in winner_fires)))
    say(f"  labelled EPs in the 277: {sorted(f'{t} {d}' for t, d in labelled)}")
    say(f"  long-history holes cut (> {GAP_CUT_DAYS} calendar days; rows before dropped): "
        + "; ".join(f"{t} {a}->{b} ({n} rows dropped)" for t, (a, b, n) in sorted(cuts.items())))
    if not ok or len(winner_fires) != 11:
        say("GATE FAILED — HALT")
        (HERE / "h9_out.txt").write_text("\n".join(OUT) + "\n")
        sys.exit(1)

    # overlap check sat_daily_long vs daily.tsv (the split-adjustment guard)
    mism = tot = 0
    for t, rows in longd.items():
        dd = daily.get(t, {})
        for (ds, o, h, l, c, v) in rows:
            b = dd.get(date.fromisoformat(ds))
            if not b:
                continue
            tot += 1
            if any(x is None or abs(x - y) > 1e-6 for x, y in ((b["open_price"], o), (b["high_price"], h), (b["low_price"], l), (b["close"], c))):
                mism += 1
    say(f"  sat_daily_long vs daily.tsv on overlap: {tot} rows, {mism} mismatches (0 = same scale; the split-adjust guard)")

    # ── ladders per campaign ──
    lad = {}
    lad_err = Counter()
    lev_rows = []
    for a in alerts:
        t, ep = a["ticker"], a["ep_date"]
        days = longd.get(t)
        if not days:
            lad_err["no_long_history"] += 1
            continue
        idx = {r[0]: i for i, r in enumerate(days)}
        ia = idx.get(ep.isoformat())
        if ia is None:
            lad_err["ep_day_not_in_history"] += 1
            continue
        if ia < 10:
            lad_err["history_lt_10"] += 1
            continue
        adr_pct = enc.adr20_pct(days, ia)
        if adr_pct is None or adr_pct <= 0:
            lad_err["no_adr20"] += 1
            continue
        pc = days[ia - 1][4]
        hist_max = max(days[j][2] for j in range(ia))
        Q = ladder_q(days, ia, adr_pct, hist_max)
        P = ladder_p(days, ia, hist_max)
        lad[(t, ep)] = {"ia": ia, "adr_pct": adr_pct, "pc": pc, "pc_alert": a["prior_close"], "hist_max": hist_max,
                        "Q": Q, "P": P, "first_day": days[0][0], "open": days[ia][1], "thin": ia < enc.MIN_HISTORY}
        for name, L in (("Q", Q), ("P", P)):
            for x in L:
                lev_rows.append((t, ep.isoformat(), a["era"], name, round(x["price"], 4), x["kind"], x["episodes"],
                                 x["days"], x["depth"],
                                 "below_prior_close" if x["price"] <= pc else ("cleared_at_open" if x["price"] < days[ia][1] else "above_ep_open")))
    pc_mis = sum(1 for v in lad.values() if v["pc_alert"] is not None and abs(v["pc"] / v["pc_alert"] - 1) > 0.02)
    say(f"  ladders built: {len(lad)} of {len(alerts)} campaigns; errors {dict(lad_err) or 'none'}; "
        f"history < {enc.MIN_HISTORY} sessions (encoder 'insufficient_history' flag, still used): "
        f"{sorted(f'{k[0]} {k[1]} ({v['ia']}d)' for k, v in lad.items() if v['thin'])}")
    say(f"  pre-EP sessions: median {statistics.median(v['ia'] for v in lad.values()):.0f}, "
        f"< 120: {sum(1 for v in lad.values() if v['ia'] < 120)}; prior close (history) vs alerts.tsv prior_close off by > 2%: {pc_mis}")
    for name in ("Q", "P"):
        nlev = [sum(1 for x in v[name] if x["kind"] != "hist_high") for v in lad.values()]
        nbtw = [sum(1 for x in v[name] if v["pc"] < x["price"] < v["open"]) for v in lad.values()]
        say(f"  ladder {name}: levels per campaign (excl. history high) median {statistics.median(nlev):.0f} "
            f"(0 levels: {sum(1 for n in nlev if n == 0)}); levels the EP OPEN gapped over (prior close < L < open): "
            f"median {statistics.median(nbtw):.0f}, campaigns with >= 1: {sum(1 for n in nbtw if n >= 1)} of {len(nbtw)}")

    # ── rows ──
    rows, excl = [], Counter()
    per_fire = []
    d0_mis = 0
    for f in fires:
        k = (f["ticker"], f["ep_date"])
        row, why = rerun.build_row(f, "recorded", daily, minutes5, raw1)
        rec = {"f": f, "row": row, "L": lad.get(k), "place": {}}
        per_fire.append(rec)
        if row is None:
            excl[f"row_not_built:{why}"] += 1
            continue
        if rec["L"] is None:
            excl["no_ladder"] += 1
        d0k, d0b = d0_for(f, row, minutes5)
        if d0k != row["d0_kind"]:
            d0_mis += 1
        if rec["L"] is not None:
            for name in ("Q", "P"):
                for buf in (BUF_ADR,) + BUF_SENS:
                    pl = place(rec["L"][name], rec["L"]["pc"], row["entry"], f["adr_dollar"], buf)
                    sk = f"{name}_{int(round(buf * 100)):03d}"
                    rec["place"][sk] = pl
                    add_stop(row, sk, pl.get("stop") if pl["killed_why"] is None else None, d0k, d0b)
                    if pl["killed_why"] is not None:
                        row["stops"][sk]["why"] = pl["killed_why"]
        row["fp"] = p3_grid.first_passages(row)
        row["ex"] = p3_grid.exit_sessions(row)
        rows.append(rec)
    say(f"  grid rows built {len(rows)} of {len(fires)}; excluded {dict(excl) or 'none'}; day-0 source re-derivation "
        f"mismatches {d0_mis}; d0 kinds {dict(Counter(r['row']['d0_kind'] for r in rows))}")

    # ── ANCHORS ──
    say("")
    say("ANCHORS (HALT on drift)")
    halt = False
    # (1) the price-target walk == first_passages' 1xADR target and its no-target fp, every row x stop
    a1 = Counter()
    for rec in rows:
        row = rec["row"]
        for s, st in row["stops"].items():
            if st["killed"] or st["d0_abstain"]:
                continue
            for tg, px in (("1ADR", row["entry"] + 1.0 * row["adr"]), ("none", None)):
                mine, ref = fp_price(row, st, px), row["fp"][(s, tg)]
                same = (mine["pess"] == ref["pess"] and mine["opt"] == ref["opt"] and mine["straddle"] == ref["straddle"]
                        and ((mine["target_r"] is None and ref["target_r"] is None)
                             or abs(mine["target_r"] - ref["target_r"]) < 1e-9))
                a1["match" if same else "MISMATCH"] += 1
    say(f"  (1) price-target first passage vs p3_grid.first_passages (1xADR target + no target, every row x stop): {dict(a1)}")
    halt |= a1.get("MISMATCH", 0) > 0
    # (2) the §D arms the bar comes from
    def d_arm(sname):
        run_r, rest_r = [], []
        for rec in rows:
            row = rec["row"]
            st = row["stops"][sname]
            if st["killed"] or st["d0_abstain"] or min(WINDOW, row["n_avail"]) <= 0:
                continue
            sc = score(row, sname, row["fp"][(sname, "none")], "trail_max10_20")
            if sc["status"] != "scored":
                continue
            (run_r if row["id"] in runner_ids else rest_r).append(sc["Rg"])
        return {"runner_fires": len(run_r), "runner_kept3": sum(1 for r in run_r if r >= TAIL_R - EPS),
                "runner_mean": round(mean(run_r), 4), "rest_n": len(rest_r), "rest_mean": round(mean(rest_r), 4)}
    for sname, key in (("adr_100", "grid:adr_100/none/trail_max10_20"), ("incumbent", "grid:incumbent/none/trail_max10_20")):
        got, ref = d_arm(sname), summ["D_big_winners"]["arms"][key]
        same = all(abs(got[k] - ref[k]) < 1e-3 for k in got)
        say(f"  (2) {key}: mine {got} | summary.json {ref} -> {'MATCH' if same else 'DRIFT'}")
        halt |= not same
    if halt:
        say("ANCHOR DRIFT — HALT")
        (HERE / "h9_out.txt").write_text("\n".join(OUT) + "\n")
        sys.exit(1)

    # ── score every arm on every fire ──
    ARMS = {  # name -> (stop key, target?: ladder name or None)
        "inc_trail": ("incumbent", None), "adr100_trail": ("adr_100", None),
        "Q_S": ("Q_010", None), "Q_ST": ("Q_010", "Q"), "P_S": ("P_010", None), "P_ST": ("P_010", "P"),
        "Q_ST_b000": ("Q_000", "Q"), "Q_ST_b025": ("Q_025", "Q"), "Q_S_b000": ("Q_000", None), "Q_S_b025": ("Q_025", None),
    }
    res = defaultdict(dict)      # arm -> fire id -> result
    tgt_fp = {}                  # (arm, id) -> fp with the ladder target (for the hit rate)
    for rec in rows:
        row, f = rec["row"], rec["f"]
        for arm, (sk, tl) in ARMS.items():
            if sk not in row["stops"]:
                res[arm][row["id"]] = {"status": "no_ladder"}
                continue
            st = row["stops"][sk]
            if st["killed"]:
                res[arm][row["id"]] = {"status": "killed", "why": st.get("why")}
                continue
            if st["d0_abstain"]:
                res[arm][row["id"]] = {"status": "d0_abstain"}
                continue
            if tl is None:
                fp = row["fp"][(sk, "none")]
            else:
                pl = rec["place"][sk]
                fp = fp_price(row, st, pl["target"])
                tgt_fp[(arm, row["id"])] = fp
            sc = score(row, sk, fp, "trail_max10_20")
            if sc["status"] == "scored":
                if st["width_pct"] < WIDTH_FLOOR_PCT - EPS and arm not in ("inc_trail", "adr100_trail"):
                    sc = {"status": "below_floor", "w": st["width_pct"]}
                else:
                    mult, rstat, _, _ = h10.regime_for(f["fire_date"])
                    fr = h10.frac(st["width_pct"], RISK_PCT_TODAY, mult)
                    sc["mult"], sc["frac"], sc["regime_status"] = mult, fr, rstat
                    sc["D"] = sc["Rg"] * fr
                    sc["Rslip"] = sc["Rg"] - 2 * SLIP_BPS * row["entry"] / sc["risk"]
            res[arm][row["id"]] = sc

    fire_of = {rec["row"]["id"]: rec for rec in rows}
    all_ids = [rec["row"]["id"] for rec in rows]
    era_sets = {
        "ERA A": [i for i in all_ids if fire_of[i]["f"]["era"] == "A"],
        "  A-DISC (<=08-14)": [i for i in all_ids if fire_of[i]["f"]["era"] == "A" and fire_of[i]["f"]["ep_date"] <= DISC_END],
        "  A-HOA (08-15..21)": [i for i in all_ids if fire_of[i]["f"]["era"] == "A" and fire_of[i]["f"]["ep_date"] > DISC_END],
        "ERA B": [i for i in all_ids if fire_of[i]["f"]["era"] == "B"],
    }

    # ── (1) population statement ──
    say("")
    say("(1) POPULATION — per arm, per era: fires · killed (entry below the gap fill) · below the 0.5% floor · day-0 abstain · scored")
    for arm in ("inc_trail", "adr100_trail", "Q_ST", "Q_S", "P_ST", "P_S"):
        parts = []
        for era in ("ERA A", "ERA B"):
            ids = era_sets[era]
            c = Counter(res[arm][i]["status"] for i in ids)
            parts.append(f"{era}: {len(ids)} fires · killed {c.get('killed', 0)} · floor {c.get('below_floor', 0)} · "
                         f"d0-abstain {c.get('d0_abstain', 0)} · other {sum(v for k, v in c.items() if k not in ('scored', 'killed', 'below_floor', 'd0_abstain'))} "
                         f"· SCORED {c.get('scored', 0)}")
        say(f"  {arm:13s} " + " | ".join(parts))
    for arm in ("Q_ST", "P_ST"):
        kw = Counter(res[arm][i].get("why") for i in all_ids if res[arm][i]["status"] == "killed")
        say(f"  {arm} kill reasons: {dict(kw)}")

    # ── width distribution ──
    say("")
    say("WIDTH DISTRIBUTION — stop distance below the recorded entry (all fires with a placeable stop), p10 / p25 / MEDIAN / p75 / p90")
    for era in ("ERA A", "ERA B"):
        ids = era_sets[era]
        for sk, lab in (("incumbent", "lane's own stop"), ("adr_100", "1xADR"), ("Q_010", "ladder Q"), ("P_010", "ladder P (10-07)")):
            ws, wa = [], []
            for i in ids:
                st = fire_of[i]["row"]["stops"].get(sk)
                if st is None or st["killed"]:
                    continue
                ws.append(st["width_pct"])
                wa.append(st["risk"] / fire_of[i]["row"]["adr"])
            say(f"  {era} {lab:17s} n {len(ws):3d} | % of entry {pctl(ws, 10):5.1f} {pctl(ws, 25):5.1f} {pctl(ws, 50):5.1f} {pctl(ws, 75):5.1f} {pctl(ws, 90):5.1f}"
                f" | x ADR {pctl(wa, 10):4.2f} {pctl(wa, 25):4.2f} {pctl(wa, 50):4.2f} {pctl(wa, 75):4.2f} {pctl(wa, 90):4.2f}"
                f" | stops > 10% wide (cap not binding at 2%): {sum(1 for w in ws if w > 10)}")
        for name in ("Q", "P"):
            kinds = Counter(fire_of[i]["place"][f"{name}_010"].get("kind") for i in ids
                            if f"{name}_010" in fire_of[i]["place"] and fire_of[i]["place"][f"{name}_010"]["killed_why"] is None)
            say(f"  {era} ladder {name} stop anchored on: {dict(kinds)}")

    # ── target geometry + hit rate ──
    say("")
    say("NEXT-ZONE TARGET — distance above the entry and HIT RATE (high reaches the zone before the stop, pess, by the final mark)")
    for name in ("Q", "P"):
        arm = f"{name}_ST"
        for era in ("ERA A", "ERA B"):
            ids = [i for i in era_sets[era] if res[arm][i]["status"] == "scored"]
            with_t = [i for i in ids if fire_of[i]["place"][f"{name}_010"]["target"] is not None]
            tr = [tgt_fp[(arm, i)]["target_r"] for i in with_t]
            ta = [(fire_of[i]["place"][f"{name}_010"]["target"] - fire_of[i]["row"]["entry"]) / fire_of[i]["row"]["adr"] for i in with_t]
            hit = [i for i in with_t if tgt_fp[(arm, i)]["pess"][1] == p3_grid.TARGET
                   and tgt_fp[(arm, i)]["pess"][0] <= res[arm][i]["Kf"]]
            ex_t = sum(1 for i in ids if res[arm][i]["kind"] == p3_grid.TARGET)
            ex_s = sum(1 for i in ids if res[arm][i]["kind"] == p3_grid.STOP)
            say(f"  {arm} {era}: scored {len(ids)}; with a zone overhead {len(with_t)} (blue sky above the entry {len(ids) - len(with_t)}); "
                f"target distance median {fm(pctl(tr, 50), '{:.2f}')}R (p25 {fm(pctl(tr, 25), '{:.2f}')}, p75 {fm(pctl(tr, 75), '{:.2f}')}) = "
                f"{fm(pctl(ta, 50), '{:.2f}')} x ADR; zones <= 3R away {sum(1 for r in tr if r < TAIL_R - EPS)} of {len(tr)}")
            say(f"      HIT RATE {len(hit)} of {len(with_t)} = {100 * len(hit) / len(with_t) if with_t else 0:.1f}% before the stop; "
                f"arm exits: target {ex_t} · stop {ex_s} · trail {sum(1 for i in ids if res[arm][i]['kind'] == p3_grid.EXIT)} · open at mark "
                f"{sum(1 for i in ids if res[arm][i]['kind'] == p3_grid.OPEN)}")

    # ── (2) results against the bar ──
    say("")
    say("(2) RESULTS AGAINST THE BAR — final mark (session 20 or 09-25), gap-charged R; $ = capped dollars at today's 2% risk x regime, 20% notional cap")
    nonwin = {era: [i for i in era_sets[era] if i not in runner_ids] for era in era_sets}
    base = {}
    for era in ("ERA A", "ERA B"):
        v = [res["adr100_trail"][i]["Rg"] for i in nonwin[era] if res["adr100_trail"][i]["status"] == "scored"]
        base[era] = mean(v)
    say(f"  bar's −0.14R = rerun §D grid:adr_100/none/trail_max10_20 rest mean −0.1395 on a POOLED A+B set (n 620). "
        f"Like-for-like 1xADR trail non-winner mean: ERA A {fm(base['ERA A'])} · ERA B {fm(base['ERA B'])}")
    verdicts = {}
    rows_out_arms = ("inc_trail", "adr100_trail", "Q_ST", "Q_S", "P_ST", "P_S")
    for arm in rows_out_arms:
        say("")
        say(f"  ── {arm} ──")
        wf = sorted(runner_ids & set(all_ids))
        kept = [i for i in wf if res[arm][i]["status"] == "scored" and res[arm][i]["Rg"] >= TAIL_R - EPS]
        wr = [res[arm][i]["Rg"] for i in wf if res[arm][i]["status"] == "scored"]
        wd = [res[arm][i]["D"] for i in wf if res[arm][i]["status"] == "scored"]
        say(f"   winner fires kept >= 3R: {len(kept)} of 11  (scored {len(wr)}; winner mean {fm(mean(wr))}R / {fm(mean(wd))} $-R; "
            f"winner $-R total {fm(sum(wd) if wd else None, '{:+.1f}')})")
        leg = {}
        for era in ("ERA A", "  A-DISC (<=08-14)", "  A-HOA (08-15..21)", "ERA B"):
            items = []
            for i in nonwin[era]:
                r = res[arm][i]
                if r["status"] == "scored":
                    items.append({"ticker": fire_of[i]["f"]["ticker"], "R": r["Rg"], "D": r["D"], "S": r["Rslip"], "id": i})
            if not items:
                say(f"   {era:20s} non-winner: none scored")
                continue
            R = [x["R"] for x in items]
            d2, d2n = drop2_mean(items, "R")
            D = [x["D"] for x in items]
            dd2, dd2n = drop2_mean(items, "D")
            allsc = [res[arm][i]["Rg"] for i in era_sets[era] if res[arm][i]["status"] == "scored"]
            # paired vs 1xADR trail on the same non-winner fires
            pr = [(x["R"] - res["adr100_trail"][x["id"]]["Rg"], fire_of[x["id"]]["f"]["fire_date"]) for x in items
                  if res["adr100_trail"][x["id"]]["status"] == "scored"]
            pdiff = mean([p[0] for p in pr]) if pr else None
            pp = perm_paired([p[0] for p in pr], [week_of(p[1]) for p in pr]) if len(pr) >= 2 and era in ("ERA A", "  A-DISC (<=08-14)") else None
            pdD = mean([x["D"] - res["adr100_trail"][x["id"]]["D"] for x in items if res["adr100_trail"][x["id"]]["status"] == "scored"]) if pr else None
            say(f"   {era:20s} non-winner n {len(R):3d} on {len({x['ticker'] for x in items}):3d} names | mean {fm(mean(R))}R (drop-best-2 {fm(d2)}: {', '.join(d2n)}) "
                f"| >=3R {sum(1 for r in R if r >= TAIL_R - EPS)} ({100 * sum(1 for r in R if r >= TAIL_R - EPS) / len(R):.1f}%) | worst {min(R):+.2f} "
                f"| slip {fm(mean([x['S'] for x in items]))}")
            say(f"   {'':20s} $-R mean {fm(mean(D), '{:+.3f}')} (drop-best-2 {fm(dd2, '{:+.3f}')}) sum {sum(D):+.1f} | ALL scored fires >=3R share "
                f"{100 * sum(1 for r in allsc if r >= TAIL_R - EPS) / len(allsc):.1f}% (n {len(allsc)}) | vs 1xADR trail same fires: "
                f"{fm(pdiff, '{:+.3f}')}R (n {len(pr)}{'' if pp is None else f', week-block p {pp:.3f}'}), {fm(pdD, '{:+.3f}')} $-R")
            leg[era] = {"mean": mean(R), "pdiff": pdiff, "drop2": d2, "D": mean(D), "pdD": pdD}
        if arm in ("Q_ST", "Q_S", "P_ST", "P_S"):
            l1 = len(kept) >= BAR_KEEP
            l2 = leg.get("ERA A", {}).get("mean") is not None and leg["ERA A"]["mean"] >= BAR_NONWIN - EPS
            sa, sb = leg.get("ERA A", {}).get("pdiff"), leg.get("ERA B", {}).get("pdiff")
            l3 = sa is not None and sb is not None and ((sa > 0) == (sb > 0)) and sa != 0 and sb != 0
            verdicts[arm] = (l1, l2, l3)
            say(f"   BAR: keeps >= 9 of 11: {'YES' if l1 else 'NO'} ({len(kept)}) · ERA A non-winner mean >= −0.14: {'YES' if l2 else 'NO'} "
                f"({fm(leg.get('ERA A', {}).get('mean'), '{:+.3f}')}) · ERA B same sign (vs 1xADR, A {fm(sa, '{:+.3f}')} / B {fm(sb, '{:+.3f}')}): "
                f"{'YES' if l3 else 'NO'}  ->  {'PASS' if (l1 and l2 and l3) else 'FAIL'}")

    # ── the 11 winner fires + his labelled EPs, by name ──
    say("")
    say("WINNER FIRES AND HIS LABELLED EPs, BY NAME — ladder Q: stop anchor · width · target distance · R under each arm")
    named = [i for i in all_ids if i in runner_ids] + \
            [i for i in all_ids if (fire_of[i]["f"]["ticker"], fire_of[i]["f"]["ep_date"]) in labelled]
    for i in named:
        rec = fire_of[i]
        f, row = rec["f"], rec["row"]
        pq = rec["place"].get("Q_010", {})
        pp_ = rec["place"].get("P_010", {})
        tag = "WIN" if i in runner_ids else "LAB"

        def rr(arm):
            r = res[arm][i]
            return f"{r['Rg']:+.2f}" if r["status"] == "scored" else r["status"]
        if pq.get("killed_why"):
            qtxt = f"Q KILLED ({pq['killed_why']})"
        else:
            st = row["stops"]["Q_010"]
            tR = (pq["target"] - row["entry"]) / st["risk"] if pq.get("target") else None
            qtxt = (f"Q stop {pq['stop']:.2f} on {pq['kind']} {pq['support']:.2f} (lbl {pq['label'][0]}d·{pq['label'][1]}%) "
                    f"w {st['width_pct']:.1f}% = {st['risk'] / row['adr']:.2f}xADR · tgt {fm(pq.get('target'), '{:.2f}')} ({fm(tR, '{:.2f}')}R)")
        ptxt = "P KILLED" if pp_.get("killed_why") else f"P w {row['stops']['P_010']['width_pct']:.1f}% on {pp_['kind']}"
        say(f"  {tag} {f['ticker']:5s} {f['ep_date']} {f['rung']:18s} s{f['session_idx']} entry {row['entry']:.2f} pc {rec['L']['pc']:.2f} | {qtxt} | {ptxt}")
        say(f"      R: lane {rr('inc_trail')} · 1xADR {rr('adr100_trail')} · Q_S {rr('Q_S')} · Q_ST {rr('Q_ST')} · P_S {rr('P_S')} · P_ST {rr('P_ST')}")

    # ── sensitivity (descriptive) ──
    say("")
    say("SENSITIVITY (descriptive, not judged) — the 'just below' buffer")
    for arm in ("Q_ST_b000", "Q_ST", "Q_ST_b025", "Q_S_b000", "Q_S", "Q_S_b025"):
        kept = sum(1 for i in runner_ids & set(all_ids) if res[arm][i]["status"] == "scored" and res[arm][i]["Rg"] >= TAIL_R - EPS)
        mA = mean([res[arm][i]["Rg"] for i in nonwin["ERA A"] if res[arm][i]["status"] == "scored"])
        mB = mean([res[arm][i]["Rg"] for i in nonwin["ERA B"] if res[arm][i]["status"] == "scored"])
        say(f"  {arm:10s} keeps {kept} of 11 · ERA A non-winner {fm(mA, '{:+.3f}')} · ERA B {fm(mB, '{:+.3f}')}")

    # ── verdict ──
    say("")
    say("(3) VERDICT against the verbatim bar (keeps >= 9 of 11 · non-winner mean >= −0.14R · ERA B same sign)")
    for arm, (l1, l2, l3) in verdicts.items():
        say(f"  {arm:5s} {'PASS' if (l1 and l2 and l3) else 'FAIL'}  (keeps {'Y' if l1 else 'N'} · mean {'Y' if l2 else 'N'} · ERA B {'Y' if l3 else 'N'})"
            + ("   <- PRIMARY (the hypothesis as written)" if arm == "Q_ST" else ""))
    say("  4 draws (2 ladders x 2 arms); the regime multiplier is live only from 2026-07-26 — earlier fires are sized as if it were.")

    # ── write ──
    (HERE / "h9_out.txt").write_text("\n".join(OUT) + "\n")
    with open(HERE / "h9_levels.tsv", "w") as fh:
        fh.write("ticker|ep_date|era|ladder|price|kind|episodes|days_since|depth_pct|position\n")
        for r in lev_rows:
            fh.write("|".join("" if x is None else str(x) for x in r) + "\n")
    cols = ["id", "ticker", "ep_date", "era", "rung", "fire_date", "session_idx", "winner", "entry", "prior_close",
            "adr_dollar", "pre_ep_sessions"]
    for name in ("Q", "P"):
        cols += [f"{name}_killed", f"{name}_support", f"{name}_kind", f"{name}_lbl_days", f"{name}_lbl_depth", f"{name}_stop",
                 f"{name}_w_pct", f"{name}_w_adr", f"{name}_target", f"{name}_target_kind", f"{name}_target_R"]
    for arm in rows_out_arms:
        cols += [f"{arm}_status", f"{arm}_R", f"{arm}_kind", f"{arm}_frac", f"{arm}_D"]
    with open(HERE / "h9_rows.tsv", "w") as fh:
        fh.write("|".join(cols) + "\n")
        for rec in per_fire:
            f, row = rec["f"], rec["row"]
            i = f["id"]
            v = [i.replace("|", ":"), f["ticker"], f["ep_date"], f["era"], f["rung"], f["fire_date"], f["session_idx"], i in runner_ids,
                 f["entry"], rec["L"]["pc"] if rec["L"] else None, f["adr_dollar"], rec["L"]["ia"] if rec["L"] else None]
            for name in ("Q", "P"):
                pl = rec["place"].get(f"{name}_010") or {}
                st = (row or {}).get("stops", {}).get(f"{name}_010") if row else None
                live = st is not None and not st["killed"]
                v += [pl.get("killed_why"), pl.get("support"), pl.get("kind"), (pl.get("label") or (None, None))[0],
                      (pl.get("label") or (None, None))[1], pl.get("stop"),
                      round(st["width_pct"], 3) if live else None, round(st["risk"] / row["adr"], 3) if live else None,
                      pl.get("target"), pl.get("target_kind"),
                      round((pl["target"] - row["entry"]) / st["risk"], 3) if live and pl.get("target") else None]
            for arm in rows_out_arms:
                r = res[arm].get(i, {"status": "row_not_built"})
                v += [r["status"], round(r["Rg"], 4) if "Rg" in r and r["status"] == "scored" else None, r.get("kind"),
                      round(r["frac"], 4) if r.get("frac") is not None else None, round(r["D"], 4) if r.get("D") is not None else None]
            fh.write("|".join("" if x is None else str(x) for x in v) + "\n")
    say("")
    say("wrote h9_out.txt, h9_rows.tsv, h9_levels.tsv")


if __name__ == "__main__":
    main()
