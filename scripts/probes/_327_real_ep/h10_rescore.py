"""#327 H10 — re-score the rerun's 654 cells and the re-entry study's 128 cells in CAPPED DOLLARS beside R.
2026-10-06. $0, MEASUREMENT ONLY: sizing and stops are the operator's (THE LINE) — nothing here changes, proposes
or ranks a live rule. Works from this folder's captured files + ONE read-only SELECT of mi_market_regime
(h10_regime_pull.py -> h10_regime.tsv, captured once). No prod write, no deploy, no commit.

H10 (327_hypotheses_2026-09-27.md, verbatim): "Every study scores in R at equal risk; live sizing does not.
RISK_PCT 1% with a 20% notional cap (constants.py:8-9) binds below a 5% stop ... ERA B's stop ranking flips
(lens, unregistered; assumes the MAGNA53 sizing path and ignores the regime multiplier)."
Test as specified: "Re-score the rerun's 654 cells and the re-entry study's 128 with dollar risk = equity x
RISK_PCT x the regime multiplier known the day before the fire, capped at 20% notional."
Rule from the doc: "carry a stop forward only if it wins on both" (R and capped dollars).

DEFINITIONS (written before any dollar number was read):
- SIZING = the MAGNA53 path, broker/order_manager.py::prepare_orb_order: risk$ = equity x risk_pct_eff,
  shares = risk$ / (entry - stop), then shares capped at MAX_POSITION_PCT x equity / entry. Equity cancels:
  the dollar risk actually placed, in units of ONE FULL R (= equity x RISK_PCT), is
      frac = min(mult, MAX_POSITION_PCT x w / RISK_PCT),  w = (entry - stop) / entry.
  R-equivalent (R-eq) of a fire = its R x frac. Integer-share flooring and the zero-share reject are ignored.
- mult = REGIME_RISK_MULTIPLIER[label] of the regime KNOWN the morning of the fire: the latest mi_market_regime
  row with regime_date < fire_date AND created_at before 09:30 ET on the fire date. If that row is older than the
  prior trading day (stale), or its label is unrecognised, the live resolver floors to
  REGIME_SIZING_FALLBACK_MULTIPLIER (0.25) — done the same here and COUNTED. Every attempt of a re-entry chain uses
  its OWN fire date.
- VARIANTS: lens1 = RISK_PCT 1%, mult 1 (the H10 lens as stated, to reproduce it) · r1 = 1% x regime ·
  r2 = 2% x regime (RISK_PCT since #688, 2026-10-05) · lens2 = 2%, mult 1 (reference).
- R used: the rerun's grid/mgmt cells -> the R its cells.tsv mean_A is computed on (house R for grid; gap-charged
  for mgmt, as published), gap-charged R kept beside for the grid; the re-entry cells -> gap-charged per-campaign
  totals (its judged R). Rerun cells are the RECORDED entry at K = 10 (its primary); fillable / K = 20 are not
  per-fire on disk and are not re-scored.
- POPULATION per cell = exactly the study's own scored set (rerun: width >= 0.5%, not killed / abstained,
  >= 10 sessions elapsed; re-entry: readable campaigns). ANCHORS before any dollar figure: every rerun cell's
  n / mean (ERA A and ERA B) must equal cells.tsv (recorded, K = 10) and every re-entry cell's n / sum / drop-2
  must equal reentry_cells.tsv. HALT on drift.
- ERA A = alert_date < 2026-08-22, ERA B = on/after (the data's era column; every #327 doc's split). ERA A's
  in-sample part (alerts <= 08-14, DISCOVERY) is reported beside ERA A; never pooled with ERA B.
- RANKING = pairwise: within a group of cells that differ only by stop (rerun grid: same target x exit; rerun mgmt:
  same arm; re-entry: same pattern x tries x exit), on the units scored under EVERY stop of the group, per era.
  A flip = the order by R differs from the order by R-eq. "Wins on both" = beats the incumbent stop on R AND on R-eq
  over that pairwise set.
- TAIL first: kept >= 3R count, the R-eq those winners bring, worst single unit; then sums / means / drop-best-2
  (names dropped by the column's OWN metric).

Usage: python3 h10_rescore.py  ->  h10_cells.tsv, h10_groups.tsv, h10_lane_rows.tsv, h10_report.txt
"""
from __future__ import annotations

import csv
import sys
from collections import Counter, defaultdict
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import rerun          # noqa: E402  (inserts REPO, probes, _327_block5 on sys.path)
import reentry        # noqa: E402
import p3_grid        # noqa: E402
import p6_leaders_mgmt as p6   # noqa: E402
from agents.market_intelligence.delayed_entry_shadow import _trading_days   # noqa: E402
from agents.market_intelligence.constants import (   # noqa: E402
    MAX_POSITION_PCT, REGIME_RISK_MULTIPLIER, REGIME_SIZING_FALLBACK_MULTIPLIER,
)

K = 10
DISC_END = date(2026, 8, 14)
VARIANTS = {"lens1": (0.01, False), "r1": (0.01, True), "r2": (0.02, True), "lens2": (0.02, False)}
OUT = []
H2H = []


def say(s=""):
    print(s)
    OUT.append(s)


# ── regime known the morning of a date ─────────────────────────────────────────────────────────
def load_regime():
    rows = []
    with open(HERE / "h10_regime.tsv") as fh:
        for r in csv.DictReader(fh, delimiter="|"):
            rows.append((date.fromisoformat(r["regime_date"]), r["regime"],
                         datetime.fromisoformat(r["created_at"])))
    return sorted(rows)


REG = None
_RC = {}


def regime_for(F):
    if F in _RC:
        return _RC[F]
    prior = _trading_days(F - timedelta(days=12), F - timedelta(days=1))[-1]
    cutoff = datetime(F.year, F.month, F.day, 13, 30, tzinfo=timezone.utc)   # 09:30 EDT (every fire is Apr-Sep)
    cands = [r for r in REG if r[0] < F and r[2] < cutoff]
    if not cands:
        res = (REGIME_SIZING_FALLBACK_MULTIPLIER, "stale", None, None)
    else:
        d, lab, _ = cands[-1]
        if d < prior:
            res = (REGIME_SIZING_FALLBACK_MULTIPLIER, "stale", lab, d)
        elif lab not in REGIME_RISK_MULTIPLIER:
            res = (REGIME_SIZING_FALLBACK_MULTIPLIER, "unrecognised", lab, d)
        else:
            res = (REGIME_RISK_MULTIPLIER[lab], "known", lab, d)
    _RC[F] = res
    return res


def frac(w_pct, rp, m):
    return min(m, MAX_POSITION_PCT * (w_pct / 100.0) / rp)


def req(parts, v):
    rp, use_reg = VARIANTS[v]
    return sum(R * frac(w, rp, m if use_reg else 1.0) for R, w, m in parts)


# ── metrics ────────────────────────────────────────────────────────────────────────────────────
def _drop2(items, val):
    by = defaultdict(float)
    for it in items:
        by[it["ticker"]] += val(it)
    top = sorted(by.items(), key=lambda kv: -kv[1])[:2]
    return sum(by.values()) - sum(v for _, v in top), [f"{t} {v:+.1f}" for t, v in top]


def metrics(items):
    if not items:
        return None
    m = {"n": len(items), "names": len({i["ticker"] for i in items})}
    R = [i["R"] for i in items]
    m["sum_R"], m["mean_R"] = sum(R), sum(R) / len(R)
    m["drop2_R"], m["drop2_R_names"] = _drop2(items, lambda i: i["R"])
    m["ge3"] = sum(1 for r in R if r >= 3.0 - 1e-9)
    m["tail_R"] = sum(r for r in R if r >= 3.0 - 1e-9)
    m["worst_R"] = min(R)
    for v in VARIANTS:
        e = [req(i["parts"], v) for i in items]
        m[f"sum_{v}"], m[f"mean_{v}"] = sum(e), sum(e) / len(e)
        m[f"drop2_{v}"], m[f"drop2_{v}_names"] = _drop2(items, lambda i, v=v: req(i["parts"], v))
        m[f"tail_{v}"] = sum(x for x, r in zip(e, R) if r >= 3.0 - 1e-9)
        m[f"worst_{v}"] = min(e)
    if "R_gap" in items[0]:
        m["sum_Rgap"] = sum(i["R_gap"] for i in items)
    return m


def eras(items):
    return {"A": [i for i in items if i["era"] == "A"], "A_disc": [i for i in items if i["era"] == "A" and i["ep_date"] <= DISC_END],
            "B": [i for i in items if i["era"] == "B"]}


# ── build the rerun's per-fire rows (recorded convention) through its own code ────────────────────
def build_rerun_rows():
    fires = rerun.load_fires()
    daily = rerun.load_daily()
    raw1, _ = rerun.load_minutes_raw()
    m5 = rerun.minutes_to_5min(raw1)
    rows = []
    for t in fires:
        row, why = rerun.build_row(t, "recorded", daily, m5, raw1)
        if row is not None:
            rows.append(row)
    return fires, rows


def main():
    global REG
    REG = load_regime()
    fires, rows = build_rerun_rows()
    by_id = {r["id"]: r for r in rows}
    say(f"H10 re-score — rows built (recorded) {len(rows)} of {len(fires)} fires")

    # ═══ POPULATION ═══
    fire_dates = Counter()
    for f in fires:
        fire_dates[(f["era"], regime_for(f["fire_date"])[1])] += 1
    say("\n== POPULATION ==")
    for e in ("A", "B"):
        nf = sum(1 for f in fires if f["era"] == e)
        say(f"ERA {e}: first fires {nf}; regime known the morning of the fire: {fire_dates[(e, 'known')]}; "
            f"stale->0.25 floor: {fire_dates[(e, 'stale')]}; unrecognised: {fire_dates[(e, 'unrecognised')]}")
        labs = Counter(regime_for(f["fire_date"])[2] for f in fires if f["era"] == e)
        say(f"   regime label on those fires: {dict(labs)}")
    pre726 = sum(1 for f in fires if f["fire_date"] < date(2026, 7, 26))
    say(f"fires before the regime multiplier went live (2026-07-26): {pre726} of {len(fires)} "
        f"(those were sized live by the VIX formula + QQQ-EMA halve; re-scored here under the regime rule as specified)")
    for v, (rp, use) in VARIANTS.items():
        for lab, mm in list(REGIME_RISK_MULTIPLIER.items()) + [("fallback", REGIME_SIZING_FALLBACK_MULTIPLIER)]:
            if not use and lab != "Bull":
                continue
            m_ = mm if use else 1.0
            say(f"   {v}: cap binds below a {100 * rp * m_ / MAX_POSITION_PCT:.2f}% stop" + (f" ({lab})" if use else ""))

    # ═══ RERUN GRID (588) from events.csv ═══
    pub = {}
    with open(HERE / "cells.tsv") as fh:
        for c in csv.DictReader(fh, delimiter="\t"):
            if c["convention"] == "recorded" and c["K"] == str(K):
                pub[(c["kind"], c["stop"], c["target_or_arm"], c["exit"])] = c
    grid = defaultdict(list)
    wflag_bad = 0
    with open(HERE / "events.csv") as fh:
        for e in csv.DictReader(fh):
            row = by_id[e["id"]]
            st = row["stops"][e["stop"]]
            w_ok = e["width_ok"] == "True"
            if w_ok != (st["width_pct"] >= rerun.WIDTH_FLOOR_PCT):
                wflag_bad += 1
            if not w_ok:
                continue
            m = regime_for(row["fire_date"])[0]
            grid[(e["stop"], e["target"], e["exit"])].append(
                {"key": e["id"], "ticker": row["ticker"], "era": row["era"], "ep_date": row["ep_date"], "rung": row["rung"],
                 "fire_date": row["fire_date"], "R": float(e["R"]), "R_gap": float(e["R_gap"]), "w": st["width_pct"],
                 "m": m, "parts": [(float(e["R"]), st["width_pct"], m)]})
    say(f"\n== ANCHORS ==\nwidth flag vs rebuilt stop width: {wflag_bad} disagreements")
    drift = 0
    for (s, tg, ex), items in grid.items():
        c = pub[("grid", s, tg, ex)]
        for e, nk, mk in (("A", "n_A", "mean_A"), ("B", "n_B", "mean_B")):
            xs = [i["R"] for i in items if i["era"] == e]
            n_ok = len(xs) == int(c[nk])
            mean_ok = (not xs and c[mk] in ("None", "")) or (xs and abs(sum(xs) / len(xs) - float(c[mk])) <= 1.5e-4)   # events.csv R is rounded to 4 dp
            if not (n_ok and mean_ok):
                drift += 1
                if drift <= 5:
                    say(f"  GRID DRIFT {s}/{tg}/{ex} {e}: n {len(xs)} vs {c[nk]}, mean {sum(xs)/len(xs) if xs else None} vs {c[mk]}")
    say(f"rerun grid: {len(grid)} cells from events.csv; n/mean drift vs cells.tsv (ERA A + ERA B): {drift}")
    if drift or len(grid) != 588:
        say("HALT: grid anchor failed"); _write(); sys.exit(1)

    # ═══ RERUN MANAGEMENT ARMS (66) re-walked through the rerun's own code ═══
    mg = defaultdict(list)
    for row in rows:
        if row["elapsed"] < K:
            continue
        sw = p6.walk_arm_sessions(row)
        m = regime_for(row["fire_date"])[0]
        for s in rerun.MGMT_STOPS:
            st = row["stops"][s]
            if st["killed"] or st["d0_abstain"] or st["width_pct"] < rerun.WIDTH_FLOOR_PCT:
                continue
            for arm in rerun.MGMT_ARMS:
                R = None
                if arm in rerun.M1_ARMS:
                    stt, r, meta = rerun.run_m1_arm(row, st, "recorded", arm, K, sw)
                    if stt == "scored":
                        R = r
                else:
                    p_r, be_r, remn = p6.grid_params(arm)
                    ex_, remn_, cs, pt, be = p6.walk_mgmt(row["entry"], st["level"], st["d0_bars"], row["sess"], row["allc"],
                                                          row["P"], p_r, be_r, remn)
                    r, k = p6.r_at(ex_, cs, row["entry"], st["risk"], row["allc"], row["P"], row["n_avail"], K, gap=True)
                    R = r
                if R is None:
                    continue
                mg[(s, arm)].append({"key": row["id"], "ticker": row["ticker"], "era": row["era"], "ep_date": row["ep_date"],
                                     "rung": row["rung"], "fire_date": row["fire_date"], "R": R, "w": st["width_pct"], "m": m,
                                     "parts": [(R, st["width_pct"], m)]})
    drift = 0
    for (s, arm), items in mg.items():
        c = pub[("mgmt", s, arm, "")]
        for e, nk, mk in (("A", "n_A", "mean_A"), ("B", "n_B", "mean_B")):
            xs = [i["R"] for i in items if i["era"] == e]
            n_ok = len(xs) == int(c[nk])
            mean_ok = (not xs and c[mk] in ("None", "")) or (xs and abs(round(sum(xs) / len(xs), 4) - float(c[mk])) <= 1e-4)
            if not (n_ok and mean_ok):
                drift += 1
                if drift <= 5:
                    say(f"  MGMT DRIFT {s}/{arm} {e}: n {len(xs)} vs {c[nk]}, mean {sum(xs)/len(xs) if xs else None} vs {c[mk]}")
    say(f"rerun mgmt: {len(mg)} cells re-walked; n/mean drift vs cells.tsv: {drift}")
    if drift or len(mg) != 66:
        say("HALT: mgmt anchor failed"); _write(); sys.exit(1)

    # ═══ RE-ENTRY (128) ═══
    by, cend = reentry._load_rows()
    era_of = {(k[0], k[1]): v[0]["era"] for k, v in by.items()}
    pub_re = {}
    with open(HERE / "reentry_cells.tsv") as fh:
        for c in csv.DictReader(fh, delimiter="\t"):
            pub_re[(c["pattern"], c["stop"], int(c["tries"]), c["exit"])] = c
    re_cells = {}
    for p in reentry.PATTERNS:
        camp_keys = sorted({(k[0], k[1]) for k in by if k[2] == p})
        for s in reentry.STOPS:
            for arm in reentry.ARMS:
                for cap in reentry.CAPS:
                    items = []
                    for ck in camp_keys:
                        k = (ck[0], ck[1], p, s, arm)
                        if k not in by:
                            continue
                        res = reentry.campaign_cell(by[k], cend[k]["end"], cap)
                        if not res["readable"]:
                            continue
                        parts = []
                        for r in res["rows"]:
                            fd = date.fromisoformat(r["fire_date"])
                            parts.append((r["r_gap"], r["stop_w"], regime_for(fd)[0]))
                        items.append({"key": f"{ck[0]}|{ck[1]}", "ticker": ck[0], "era": era_of[ck],
                                      "ep_date": date.fromisoformat(ck[1]), "rung": p, "R": res["total"], "parts": parts,
                                      "n_att": len(res["rows"])})
                    re_cells[(p, s, cap, arm)] = items
    drift = 0
    for key, items in re_cells.items():
        c = pub_re[key]
        A = [i for i in items if i["era"] == "A"]
        mA = metrics(A)
        ok = (len(A) == int(c["n_A"]) and abs(mA["sum_R"] - float(c["sum_A"])) < 1e-6 and abs(mA["drop2_R"] - float(c["drop2_A"])) < 1e-6)
        B = [i for i in items if i["era"] == "B"]
        okb = len(B) == int(c["n_B"]) and (not B or abs(sum(i["R"] for i in B) - float(c["sum_B"])) < 1e-6)
        if not (ok and okb):
            drift += 1
            if drift <= 5:
                say(f"  RE DRIFT {key}: n {len(A)} vs {c['n_A']} sum {mA['sum_R']} vs {c['sum_A']} drop2 {mA['drop2_R']} vs {c['drop2_A']}")
    say(f"re-entry: {len(re_cells)} cells; n/sum/drop-2 drift vs reentry_cells.tsv: {drift}")
    if drift or len(re_cells) != 128:
        say("HALT: re-entry anchor failed"); _write(); sys.exit(1)

    # lens reproduction: attempt-1, trail, ALL rows with r_gap (the lens's own cut, floored rows included)
    say("\nH10 lens reproduction (attempt 1 x trail, all four patterns pooled, every row with an R — the lens's own cut):")
    lens = defaultdict(lambda: [0.0, 0.0, 0.0, 0])
    for k, att in by.items():
        r = att[0]
        if r["arm"] != "trail" or r["r_gap"] is None:
            continue
        L = lens[(r["era"], r["stop"])]
        L[0] += r["r_gap"]; L[1] += r["r_gap"] * frac(r["stop_w"], 0.01, 1.0); L[3] += 1
        L[2] += r["r_gap"] * frac(r["stop_w"], 0.01, regime_for(date.fromisoformat(r["fire_date"]))[0])
    for (e, s), L in sorted(lens.items()):
        say(f"   ERA {e} {s:10s} n {L[3]:3d}  R {L[0]:+7.1f}  -> capped 1% (no regime) {L[1]:+6.1f}  | 1% x regime {L[2]:+6.1f}")

    # ═══ CELLS TABLE ═══
    cells = []
    for (s, tg, ex), items in grid.items():
        cells.append(("rerun_grid", "ALL", s, f"{tg}|{ex}", items))
    for (s, arm), items in mg.items():
        cells.append(("rerun_mgmt", "ALL", s, arm, items))
    for (p, s, cap, arm), items in re_cells.items():
        cells.append(("reentry", p, s, f"x{cap}|{arm}", items))
    cols = ["study", "pattern", "stop", "arm", "era", "n", "names", "ge3", "tail_R"] + [f"tail_{v}" for v in VARIANTS] + \
           ["worst_R"] + [f"worst_{v}" for v in VARIANTS] + ["sum_R", "mean_R", "drop2_R"] + \
           [f"{a}_{v}" for v in VARIANTS for a in ("sum", "mean", "drop2")] + ["sum_Rgap", "drop2_R_names", "drop2_r2_names"]
    with open(HERE / "h10_cells.tsv", "w") as fh:
        fh.write("\t".join(cols) + "\n")
        for study, p, s, arm, items in cells:
            for e, xs in eras(items).items():
                m = metrics(xs)
                if m is None:
                    continue
                vals = {"study": study, "pattern": p, "stop": s, "arm": arm, "era": e, **m}
                vals["drop2_R_names"] = ";".join(m["drop2_R_names"]); vals["drop2_r2_names"] = ";".join(m["drop2_r2_names"])
                fh.write("\t".join(_fmt(vals.get(c)) for c in cols) + "\n")

    # ═══ PAIRWISE GROUPS + FLIPS ═══
    groups = []
    for tg in rerun.TARGETS:
        for ex in rerun.EXITS:
            groups.append(("rerun_grid", "ALL", f"{tg}|{ex}", {s: grid[(s, tg, ex)] for s in rerun.STOPS}))
    for arm in rerun.MGMT_ARMS:
        groups.append(("rerun_mgmt", "ALL", arm, {s: mg[(s, arm)] for s in rerun.MGMT_STOPS}))
    for p in reentry.PATTERNS:
        for cap in reentry.CAPS:
            for arm in reentry.ARMS:
                groups.append(("reentry", p, f"x{cap}|{arm}", {s: re_cells[(p, s, cap, arm)] for s in reentry.STOPS}))
    gcols = ["study", "pattern", "arm", "era", "n_pair", "order_R", "order_lens1", "order_r1", "order_r2",
             "flip_lens1", "flip_r1", "flip_r2", "top_R", "top_r1", "top_r2",
             "inc_vs_adr100_R", "inc_vs_adr100_r1", "inc_vs_adr100_r2", "beats_inc_R", "beats_inc_r1_both", "beats_inc_r2_both",
             "sums"]
    flips = Counter()
    lane_groups = {}
    with open(HERE / "h10_groups.tsv", "w") as fh:
        fh.write("\t".join(gcols) + "\n")
        for study, p, arm, members in groups:
            for e in ("A", "A_disc", "B"):
                sets = []
                for s, items in members.items():
                    sets.append({i["key"] for i in eras(items)[e]})
                common = set.intersection(*sets) if sets else set()
                if not common:
                    continue
                sums = {}
                for s, items in members.items():
                    xs = [i for i in eras(items)[e] if i["key"] in common]
                    sums[s] = {"R": sum(i["R"] for i in xs), **{v: sum(req(i["parts"], v) for i in xs) for v in VARIANTS}}
                order = {mv: sorted(sums, key=lambda s: -sums[s][mv]) for mv in ("R", "lens1", "r1", "r2")}
                rec = {"study": study, "pattern": p, "arm": arm, "era": e, "n_pair": len(common)}
                for mv in ("R", "lens1", "r1", "r2"):
                    rec[f"order_{mv}"] = ">".join(order[mv])
                for v in ("lens1", "r1", "r2"):
                    rec[f"flip_{v}"] = order[v] != order["R"]
                    flips[(study, e, v, "any")] += rec[f"flip_{v}"]
                    flips[(study, e, v, "top")] += order[v][0] != order["R"][0]
                flips[(study, e, "groups")] += 1
                rec["top_R"], rec["top_r1"], rec["top_r2"] = order["R"][0], order["r1"][0], order["r2"][0]
                if "adr_100" in sums:
                    for mv in ("R", "lens1", "r1", "r2"):
                        rec[f"inc_vs_adr100_{mv}"] = "inc" if sums["incumbent"][mv] > sums["adr_100"][mv] else "adr_100"
                    for v in ("lens1", "r1", "r2"):
                        flips[(study, e, v, "inc_vs_adr100")] += rec[f"inc_vs_adr100_{v}"] != rec["inc_vs_adr100_R"]
                rec["beats_inc_R"] = ",".join(s for s in sums if s != "incumbent" and sums[s]["R"] > sums["incumbent"]["R"])
                for v in ("r1", "r2"):
                    rec[f"beats_inc_{v}_both"] = ",".join(s for s in sums if s != "incumbent" and sums[s]["R"] > sums["incumbent"]["R"]
                                                         and sums[s][v] > sums["incumbent"][v])
                rec["sums"] = ";".join(f"{s}:{sums[s]['R']:+.1f}/{sums[s]['lens1']:+.1f}/{sums[s]['r1']:+.1f}/{sums[s]['r2']:+.1f}" for s in sums)
                fh.write("\t".join(_fmt(rec.get(c)) for c in gcols) + "\n")
                # head-to-head vs the incumbent ONLY (larger pairwise set than the all-stops intersection)
                inc = {i["key"]: i for i in eras(members["incumbent"])[e]}
                for s2, items in members.items():
                    if s2 == "incumbent":
                        continue
                    xs = [i for i in eras(items)[e] if i["key"] in inc]
                    if not xs:
                        continue
                    dR = sum(i["R"] - inc[i["key"]]["R"] for i in xs)
                    dv = {v: sum(req(i["parts"], v) - req(inc[i["key"]]["parts"], v) for i in xs) for v in VARIANTS}
                    H2H.append((study, e, p, arm, s2, len(xs), dR, dv))
                if (study == "rerun_grid" and arm == "none|trail_max10_20") or (study == "reentry" and arm in ("x1|trail", "x4|trail")):
                    lane_groups[(study, p, arm, e)] = (len(common), sums, order)

    say("\n== WINS ON BOTH — every (cell group x non-incumbent stop), head-to-head vs the incumbent stop on the same units ==")
    say("   pairs | beat incumbent in R | of those, ALSO beat it in R-eq: lens1 / 1%xregime / 2%xregime | lost in R but won in R-eq (2%xregime)")
    for study in ("rerun_grid", "rerun_mgmt", "reentry"):
        for e in ("A", "A_disc", "B"):
            hs = [h for h in H2H if h[0] == study and h[1] == e]
            if not hs:
                continue
            winR = [h for h in hs if h[6] > 0]
            say(f"   {study:11s} ERA {e:6s} {len(hs):4d} | {len(winR):4d} | " +
                " / ".join(str(sum(1 for h in winR if h[7][v] > 0)) for v in ("lens1", "r1", "r2")) +
                f" | {sum(1 for h in hs if h[6] <= 0 and h[7]['r2'] > 0)}")
            for st in sorted({h[4] for h in hs}):
                hh = [h for h in hs if h[4] == st]
                wr = [h for h in hh if h[6] > 0]
                say(f"        {st:10s} {len(hh):4d} | {len(wr):4d} | " + " / ".join(str(sum(1 for h in wr if h[7][v] > 0)) for v in ("lens1", "r1", "r2")))
    with open(HERE / "h10_h2h.tsv", "w") as fh:
        fh.write("study\tera\tpattern\tarm\tstop\tn\tdR\t" + "\t".join(f"d_{v}" for v in VARIANTS) + "\n")
        for h in H2H:
            fh.write("\t".join(str(x) for x in h[:5]) + f"\t{h[5]}\t{h[6]:.4f}\t" + "\t".join(f"{h[7][v]:.4f}" for v in VARIANTS) + "\n")

    say("\n== FLIP COUNTS (pairwise, groups that differ only by stop) ==")
    for study in ("rerun_grid", "rerun_mgmt", "reentry"):
        for e in ("A", "A_disc", "B"):
            g = flips[(study, e, "groups")]
            if not g:
                continue
            parts = []
            for v in ("lens1", "r1", "r2"):
                parts.append(f"{v}: order flips {flips[(study, e, v, 'any')]}/{g}, best-stop flips {flips[(study, e, v, 'top')]}/{g}, "
                             f"incumbent-vs-1xADR flips {flips[(study, e, v, 'inc_vs_adr100')]}")
            say(f"{study:11s} ERA {e:6s} groups {g}: " + " | ".join(parts))

    say("\n== THE LANE'S ARM, pairwise sums (R / lens1 / 1%xregime / 2%xregime) ==")
    for key in sorted(lane_groups):
        n, sums, order = lane_groups[key]
        study, p, arm, e = key
        say(f"{study:10s} {p:18s} {arm:20s} ERA {e:6s} n {n:3d} | " +
            "  ".join(f"{s}: {sums[s]['R']:+.1f}/{sums[s]['lens1']:+.1f}/{sums[s]['r1']:+.1f}/{sums[s]['r2']:+.1f}" for s in sums))
        say(f"{'':60s} order R {'>'.join(order['R'])} | r1 {'>'.join(order['r1'])} | r2 {'>'.join(order['r2'])}")

    # per-fire audit rows for the lane's arm
    with open(HERE / "h10_lane_rows.tsv", "w") as fh:
        fh.write("study\tkey\tera\tstop\tfire_date\tregime\tregime_status\tmult\tR\tw_pct\tf_lens1\tf_r1\tf_r2\n")
        for s in rerun.STOPS:
            for i in grid[(s, "none", "trail_max10_20")]:
                st = regime_for(i["fire_date"])
                fh.write(f"rerun_grid\t{i['key']}\t{i['era']}\t{s}\t{i['fire_date']}\t{st[2]}\t{st[1]}\t{i['m']}\t{i['R']:.4f}\t{i['w']:.3f}\t"
                         f"{frac(i['w'], .01, 1):.3f}\t{frac(i['w'], .01, i['m']):.3f}\t{frac(i['w'], .02, i['m']):.3f}\n")
        for p in reentry.PATTERNS:
            for s in reentry.STOPS:
                for i in re_cells[(p, s, 1, "trail")]:
                    R, w, m = i["parts"][0]
                    fh.write(f"reentry_x1\t{i['key']}|{p}\t{i['era']}\t{s}\t\t\t\t{m}\t{R:.4f}\t{w:.3f}\t"
                             f"{frac(w, .01, 1):.3f}\t{frac(w, .01, m):.3f}\t{frac(w, .02, m):.3f}\n")
    lane_tables(grid, re_cells)
    _write()


def _pooled_re(re_cells, cap, arm):
    out = {}
    for s in reentry.STOPS:
        xs = []
        for p in reentry.PATTERNS:
            for i in re_cells[(p, s, cap, arm)]:
                j = dict(i); j["key"] = f"{i['key']}|{p}"
                xs.append(j)
        out[s] = xs
    return out


def lane_tables(grid, re_cells):
    """The lane's own arm, per stop: unpaired (each stop's own scored set, as published) and head-to-head vs the
    incumbent stop on the units scored under both. Tail first."""
    studies = [("rerun grid, lane arm (no target, trail max(SMA10,SMA20), marked at session 10; per first fire)",
                {s: grid[(s, "none", "trail_max10_20")] for s in rerun.STOPS}),
               ("re-entry study, no re-entry (x1, trail; per campaign-pattern, gap-charged, 4 patterns pooled)",
                _pooled_re(re_cells, 1, "trail")),
               ("re-entry study, up to 3 re-entries (x4, trail; per campaign-pattern, gap-charged, 4 patterns pooled)",
                _pooled_re(re_cells, 4, "trail"))]
    for title, members in studies:
        say(f"\n== {title} ==")
        for e in ("A", "A_disc", "B"):
            say(f"-- ERA {e} -- unpaired: n | >=3R count, their R -> R-eq 1%xreg / 2%xreg | worst R | sum R -> lens1 / 1%xreg / 2%xreg "
                f"| drop-best-2 R / 1%xreg / 2%xreg | median stop width %, share capped at 1%xreg / 2%xreg")
            for s, items in members.items():
                xs = eras(items)[e]
                m = metrics(xs)
                if m is None:
                    say(f"   {s:10s} n 0"); continue
                ws = sorted(w for i in xs for (_, w, _) in i["parts"][:1])
                cap1 = sum(1 for i in xs for (_, w, mm) in i["parts"][:1] if frac(w, .01, mm) < mm - 1e-12)
                cap2 = sum(1 for i in xs for (_, w, mm) in i["parts"][:1] if frac(w, .02, mm) < mm - 1e-12)
                say(f"   {s:10s} n {m['n']:3d} | {m['ge3']:2d}: {m['tail_R']:+6.1f} -> {m['tail_r1']:+6.1f} / {m['tail_r2']:+6.1f} "
                    f"| {m['worst_R']:+6.1f} | {m['sum_R']:+7.1f} -> {m['sum_lens1']:+6.1f} / {m['sum_r1']:+6.1f} / {m['sum_r2']:+6.1f} "
                    f"| {m['drop2_R']:+7.1f} / {m['drop2_r1']:+6.1f} / {m['drop2_r2']:+6.1f} "
                    f"| {ws[len(ws)//2]:.2f}%, {100*cap1/len(xs):.0f}% / {100*cap2/len(xs):.0f}%")
            inc = {i["key"]: i for i in eras(members["incumbent"])[e]}
            say(f"   head-to-head vs incumbent (same units): n | delta R / lens1 / 1%xreg / 2%xreg | delta after dropping the "
                f"best-2 names (by that column's delta) R / 1%xreg / 2%xreg | wins on both at 1% / 2%")
            for s, items in members.items():
                if s == "incumbent":
                    continue
                xs = [i for i in eras(items)[e] if i["key"] in inc]
                if not xs:
                    say(f"   {s:10s} n 0"); continue
                d = {}
                dn = {}
                for mv in ("R", "lens1", "r1", "r2"):
                    def val(i, mv=mv):
                        return i["R"] if mv == "R" else req(i["parts"], mv)
                    per = defaultdict(float)
                    for i in xs:
                        per[i["ticker"]] += val(i) - val(inc[i["key"]])
                    d[mv] = sum(per.values())
                    dn[mv] = d[mv] - sum(v for _, v in sorted(per.items(), key=lambda kv: -kv[1])[:2])
                both1 = d["R"] > 0 and d["r1"] > 0
                both2 = d["R"] > 0 and d["r2"] > 0
                say(f"   {s:10s} n {len(xs):3d} | {d['R']:+6.1f} / {d['lens1']:+6.1f} / {d['r1']:+6.1f} / {d['r2']:+6.1f} "
                    f"| {dn['R']:+6.1f} / {dn['r1']:+6.1f} / {dn['r2']:+6.1f} | {'YES' if both1 else 'no '} / {'YES' if both2 else 'no'}")


def _fmt(v):
    if v is None:
        return ""
    if isinstance(v, float):
        return f"{v:.4f}"
    return str(v)


def _write():
    (HERE / "h10_report.txt").write_text("\n".join(OUT) + "\n")


if __name__ == "__main__":
    main()
