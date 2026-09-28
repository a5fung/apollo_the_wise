#!/usr/bin/env python3
"""#684 STEP 2 (PRE-REGISTRATION, written BEFORE any outcome-by-feature number was computed) and
STEP 3 (the one run). Reads features.tsv + daily.tsv.gz only. Writes results.tsv, results_out.txt,
runners_dropped.txt, summary.json.

QUESTION: what, known on the gap day, marks the EPs that run big?  Operator's goal: "any EP related
trades are low winrate by default, what we want is always to catch big winners while limiting losses".

POPULATION (gate.py / gate_out.txt, passed): 670 scored gap-day candidates, 05-01..09-03, one row per
(ticker, scan_date); alerted = the gap-day scan's own PASS verdict (307), scored-not-alerted 363.

OUTCOME (stop-independent, the same definition as the 09-27 H5 read):
  run_xadr = (max HIGH over sessions +1..+15 after the gap day − gap-day CLOSE) / ADR$,
  ADR$ = mean((h−l)/c) over the 20 sessions before the gap day × the gap-day close
         (delayed_entry_shadow.compute_ep_adr_dollar).
  RUNNER = run_xadr >= 5.  Also reported: run_xadr >= 8.  Rows without 15 forward sessions are
  excluded and counted. His labelled EPs in the population (BFLY 06-18, PLTR 08-04, TEAM 08-07,
  HTFL 08-14, MRNA 08-19) are a CO-PRIMARY check: for every feature, how many of them sit in the
  favourable group — a feature whose favourable group holds at most 1 of 5 is flagged as conflicting
  with his labels, whatever its p. (MRNA is not a 15-session runner by construction — its run began at
  session 22 — so the labelled check is "where do they sit", never "are they runners".)

SPLIT: DISCOVERY = scan_date <= 2026-08-14 (607 rows, 16 ISO weeks); HELD-OUT = 08-15..09-03 (63 rows,
3 ISO weeks). The extension lead (#327 tests, 09-27) was found on the alerts inside DISCOVERY — it is
in-sample there; ONLY the held-out read can confirm it. Tercile cut points come from DISCOVERY and are
applied unchanged to HELD-OUT.

PER-FEATURE TEST (one draw per feature, direction DECLARED below before running):
  continuous: favourable TERCILE (top or bottom third of the DISCOVERY distribution, by the declared
     direction) vs the rest — runner rate in each, the difference, and the AUC of the feature for
     runner-vs-not oriented so that > 0.5 agrees with the declared direction;
  boolean:    favourable VALUE vs the other value, same statistics (AUC = the group-rate AUC);
  ordinal 3-level (catalyst): favourable = game_changer + strong vs routine.
PERMUTATION: runner labels are shuffled WITHIN ISO WEEK of the scan date (week-block), 2,000 draws,
  seed 684; p = share of shuffles whose favourable-minus-rest difference >= the observed one
  (one-sided in the declared direction).
PASS BAR (all four): (1) DISCOVERY permutation p < 0.05; (2) the same sign on HELD-OUT, where a
  held-out read with fewer than 3 runners in total or fewer than 8 rows in the favourable group reads
  "can't tell" and cannot pass; (3) survives dropping the DISCOVERY ISO week holding the most runners
  (same sign AND p < 0.05 without it); (4) survives dropping the two names with the largest run_xadr
  (same sign AND p < 0.05 without them). Anything short of all four = "can't tell" (or "fail" if the
  discovery sign is against the declaration).

DRAWS AND NOISE BAND: the DRAWS list below has exactly the number of bar-tested features printed at
run time (target ~50). At p < 0.05, 0.05 × draws ≈ 2.5 features are expected to clear condition (1)
by chance alone, so UP TO 3 features clearing discovery only is noise; the four-condition bar is what a
finding must clear, and the expected number of chance four-condition passes is well under 1. Descriptive
tables (sector, theme stage, regime label, tier, catalyst type, judge fields, revenue growth) carry no
draw and no verdict.

DECLARED DIRECTIONS (favourable = predicted to hold MORE >= 5-ADR runners), each with its known-when
tag and its source hypothesis:
  PRE  ep_score HIGHER (the score itself — the baseline claim is that it is flat)
  PRE  gap_pct_scan HIGHER (his principle: the gap expresses the surprise; note §0d found smaller
       gaps ranked TRADEABLE winners — a tradeability confound, not this outcome)
  PRE  ext_5d_pct LOWER (the live gate's own extension), ext_sma10/20/50_xadr LOWER, ext_ma_mean_xadr
       LOWER, ext_20d_low_pct LOWER, chg_1m_pct LOWER, chg_3m_pct LOWER  (less extended before the gap
       — the 09-27 in-sample lead; his "quiet base" reference)
  PRE  base_range40_pct LOWER, base_range20_pct LOWER, base_absdisp40_xadr LOWER (a tight, flat base)
  PRE  days_since_6m_high HIGHER, base_depth_6m_pct HIGHER (neglect: MRNA's long depressed base)
  PRE  dist_52w_high_xadr LOWER, cleared_6m/52w/ath_scanprice TRUE (supply ladder: less overhead)
  PRE  above_sma50 TRUE, above_sma200 TRUE, n_ma_above HIGHER, stage2 TRUE (his SE conditions E1–E3)
  PRE  rs_composite HIGHER, in_rs_pool TRUE (leadership before the gap)
  PRE  catalyst_ord HIGHER (game_changer/strong vs routine)
  PRE  themed TRUE, themed_7d TRUE, theme_early TRUE (Nascent/Accelerating — the north star)
  PRE  regime_bull TRUE, spy_vs_50ma HIGHER (May's winners were all in Bull)
  PRE  prev_close LOWER, adr20_pct HIGHER, dollar_vol_20d LOWER (composition: smaller, wilder names)
  PRE  repeat_scored_90d FALSE (a first gap out of neglect vs a repeat)
  PRE  pm_rvol HIGHER, projected_vol_multiple HIGHER (pre-market conviction)
  PRE  first_tick_preopen TRUE (the gap was known pre-market — a news gap, not a 09:50 mover)
  0930 gap_open_pct HIGHER, cleared_6m/52w/ath_open TRUE, ext_open_sma50/20_xadr LOWER, stage2_open TRUE
  0945 orb_position HIGHER (§0e: closing near the ORB high = holding), orb_range_xadr LOWER,
       gap_0945_pct HIGHER, close_vs_open_pct HIGHER, orb_vol_vs_20d HIGHER, orb_high_above_6m TRUE
  CLOSE close_loc HIGHER, range_xadr HIGHER (the 09-27 tightness read went the wrong way, so wide is
       declared), vol_vs_max250 HIGHER, vol_vs_avg50 HIGHER, close_vs_open_pct HIGHER,
       gap_close_pct HIGHER, ext_sma50_xadr LOWER (the in-sample EOD lead), ext_sma20_xadr LOWER,
       cleared_6m/52w/ath TRUE
  ALERT expct_unscheduled TRUE (alerted rows only, rank-shadow class; §0d)

POST-RUN CORRECTION (2026-09-28, advisor review, added AFTER the run — the registration text above is
left as written): "well under 1" chance four-condition pass was too low. Conditions (3) and (4) rarely
move a p across 0.05 once (1) holds, and (2) is a coin flip under the null, so the expected number of
chance four-condition passes across 63 draws is about 3.2 x 0.4 = 1 to 1.5. One pass was observed.

ANCHOR (printed before the tables): on the rows that carry a live alert row and are era A, the share
>= 5 ADR must sit near the 09-27 read (25 of 261 = 9.6 %, 9–14 % in every score band) or the outcome
is not the same outcome.
"""
from __future__ import annotations

import gzip
import json
import random
import statistics
from collections import Counter, defaultdict
from pathlib import Path

HERE = Path(__file__).resolve().parent
SEED = 684
N_PERM = 2000
LABELLED = [("BFLY", "2026-06-18"), ("PLTR", "2026-08-04"), ("TEAM", "2026-08-07"), ("HTFL", "2026-08-14"), ("MRNA", "2026-08-19")]

# (column, kind, favourable, when, plain-words name)
DRAWS: list[tuple[str, str, str, str, str]] = [
    ("ep_score", "cont", "HIGHER", "PRE", "today's EP score"),
    ("PRE_gap_pct_scan", "cont", "HIGHER", "PRE", "gap % at the scan"),
    ("PRE_ext_5d_pct", "cont", "LOWER", "PRE", "prev close above its 5-day low close (live gate def)"),
    ("PRE_ext_sma10_xadr", "cont", "LOWER", "PRE", "prev close vs SMA10, in ADRs"),
    ("PRE_ext_sma20_xadr", "cont", "LOWER", "PRE", "prev close vs SMA20, in ADRs"),
    ("PRE_ext_sma50_xadr", "cont", "LOWER", "PRE", "prev close vs SMA50, in ADRs"),
    ("PRE_ext_ma_mean_xadr", "cont", "LOWER", "PRE", "mean distance to SMA10/20/50, in ADRs"),
    ("PRE_ext_20d_low_pct", "cont", "LOWER", "PRE", "prev close above its 20-day low"),
    ("PRE_chg_1m_pct", "cont", "LOWER", "PRE", "1-month change before the gap"),
    ("PRE_chg_3m_pct", "cont", "LOWER", "PRE", "3-month change before the gap"),
    ("PRE_base_range40_pct", "cont", "LOWER", "PRE", "40-day close range / price (base tightness)"),
    ("PRE_base_range20_pct", "cont", "LOWER", "PRE", "20-day close range / price"),
    ("PRE_base_absdisp40_xadr", "cont", "LOWER", "PRE", "net 40-day drift, in ADRs (flat base)"),
    ("PRE_days_since_6m_high", "cont", "HIGHER", "PRE", "sessions since the 6-month high (neglect)"),
    ("PRE_base_depth_6m_pct", "cont", "HIGHER", "PRE", "prev close below the 6-month high, % (depth)"),
    ("PRE_dist_52w_high_xadr", "cont", "LOWER", "PRE", "overhead to the 52-week high, in ADRs"),
    ("PRE_cleared_6m_scanprice", "bool", "1", "PRE", "scan price above the 6-month high"),
    ("PRE_cleared_52w_scanprice", "bool", "1", "PRE", "scan price above the 52-week high"),
    ("PRE_cleared_ath_scanprice", "bool", "1", "PRE", "scan price above the all-time high"),
    ("PRE_above_sma50", "bool", "1", "PRE", "prev close above SMA50"),
    ("PRE_above_sma200", "bool", "1", "PRE", "prev close above SMA200"),
    ("PRE_n_ma_above", "cont", "HIGHER", "PRE", "how many of SMA10/20/50 the prev close is above"),
    ("PRE_stage2", "bool", "1", "PRE", "Stage 2 (close > SMA50 > rising SMA200)"),
    ("PRE_rs_composite", "cont", "HIGHER", "PRE", "RS composite the prior day"),
    ("PRE_in_rs_pool", "bool", "1", "PRE", "in the RS pool the prior day"),
    ("PRE_catalyst_ord", "ord", "HIGHER", "PRE", "catalyst grade (game_changer/strong vs routine)"),
    ("PRE_themed", "bool", "1", "PRE", "in an active theme the prior night (any age)"),
    ("PRE_themed_7d", "bool", "1", "PRE", "in an active theme the prior night (7-day bounded)"),
    ("PRE_theme_early", "bool", "1", "PRE", "theme stage Nascent/Accelerating"),
    ("PRE_regime_bull", "bool", "1", "PRE", "market regime Bull"),
    ("PRE_spy_vs_50ma", "cont", "HIGHER", "PRE", "SPY vs its 50-day"),
    ("PRE_prev_close", "cont", "LOWER", "PRE", "share price"),
    ("PRE_adr20_pct", "cont", "HIGHER", "PRE", "ADR %"),
    ("PRE_dollar_vol_20d", "cont", "LOWER", "PRE", "20-day dollar volume"),
    ("PRE_repeat_scored_90d", "bool", "0", "PRE", "a scored gap on this name in the prior 90 days"),
    ("PRE_pm_rvol", "cont", "HIGHER", "PRE", "pre-market relative volume"),
    ("PRE_projected_vol_multiple", "cont", "HIGHER", "PRE", "projected volume multiple at the scan"),
    ("PRE_first_tick_preopen", "bool", "1", "PRE", "first scored tick before 09:30"),
    ("O930_gap_open_pct", "cont", "HIGHER", "0930", "gap % at the open print"),
    ("O930_cleared_6m_open", "bool", "1", "0930", "open above the 6-month high"),
    ("O930_cleared_52w_open", "bool", "1", "0930", "open above the 52-week high"),
    ("O930_cleared_ath_open", "bool", "1", "0930", "open above the all-time high"),
    ("O930_ext_open_sma50_xadr", "cont", "LOWER", "0930", "open vs SMA50, in ADRs"),
    ("O930_ext_open_sma20_xadr", "cont", "LOWER", "0930", "open vs SMA20, in ADRs"),
    ("O930_stage2_open", "bool", "1", "0930", "Stage 2 with the open"),
    ("O945_orb_position", "cont", "HIGHER", "0945", "where 09:44 sits in the opening range"),
    ("O945_orb_range_xadr", "cont", "LOWER", "0945", "opening range / ADR"),
    ("O945_gap_0945_pct", "cont", "HIGHER", "0945", "gap % at 09:44"),
    ("O945_close_vs_open_pct", "cont", "HIGHER", "0945", "09:44 vs the open"),
    ("O945_orb_vol_vs_20d", "cont", "HIGHER", "0945", "first-15-minute volume / 20-day avg daily volume"),
    ("O945_orb_high_above_6m", "bool", "1", "0945", "opening-range high above the 6-month high"),
    ("CLOSE_close_loc", "cont", "HIGHER", "CLOSE", "close location in the day's range"),
    ("CLOSE_range_xadr", "cont", "HIGHER", "CLOSE", "day range / ADR"),
    ("CLOSE_vol_vs_max250", "cont", "HIGHER", "CLOSE", "volume vs the biggest day in a year"),
    ("CLOSE_vol_vs_avg50", "cont", "HIGHER", "CLOSE", "volume vs 50-day average"),
    ("CLOSE_close_vs_open_pct", "cont", "HIGHER", "CLOSE", "close vs open"),
    ("CLOSE_gap_close_pct", "cont", "HIGHER", "CLOSE", "gap % at the close"),
    ("CLOSE_ext_sma50_xadr", "cont", "LOWER", "CLOSE", "close vs SMA50, in ADRs (the 09-27 EOD lead)"),
    ("CLOSE_ext_sma20_xadr", "cont", "LOWER", "CLOSE", "close vs SMA20, in ADRs"),
    ("CLOSE_cleared_6m", "bool", "1", "CLOSE", "close above the 6-month high"),
    ("CLOSE_cleared_52w", "bool", "1", "CLOSE", "close above the 52-week high"),
    ("CLOSE_cleared_ath", "bool", "1", "CLOSE", "close above the all-time high"),
    ("ALERT_expct_unscheduled", "bool", "1", "ALERT", "unscheduled catalyst (alerted rows only)"),
]
DESCRIPTIVE = ["PRE_sector", "PRE_theme_stage", "PRE_regime", "score_tier", "PRE_catalyst_quality", "era",
               "ALERT_judge_tier", "ALERT_judge_grade", "ALERT_catalyst_type", "ALERT_expct_scheduled", "ALERT_expct_beat"]


def load_features() -> list[dict]:
    rows = []
    with (HERE / "features.tsv").open() as fh:
        cols = fh.readline().rstrip("\n").split("\t")
        for line in fh:
            parts = line.rstrip("\n").split("\t")
            r = dict(zip(cols, parts))
            for k, v in r.items():
                if v == "":
                    r[k] = None
                else:
                    try:
                        r[k] = float(v)
                    except ValueError:
                        pass
            rows.append(r)
    return rows


def load_daily() -> dict[str, list[tuple[str, float, float, float, float, float]]]:
    out: dict[str, list] = defaultdict(list)
    with gzip.open(HERE / "daily.tsv.gz", "rt") as fh:
        header = None
        for line in fh:
            line = line.rstrip("\n")
            if not line or line.startswith("("):
                continue
            parts = line.split("|")
            if header is None:
                header = parts
                continue
            t, d, o, h, l, c, v = parts
            if not (o and h and l and c):
                continue
            out[t].append((d, float(o), float(h), float(l), float(c), float(v or 0)))
    for t in out:
        out[t].sort()
    return out


def add_outcomes(rows: list[dict], daily: dict) -> None:
    for r in rows:
        bars = daily.get(r["ticker"], [])
        dates = [b[0] for b in bars]
        d = r["scan_date"]
        r["run_xadr"] = r["runner5"] = r["runner8"] = r["run_pct"] = None
        if d not in dates or r.get("adr_dollar_ep") is None:
            continue
        i0 = dates.index(d)
        fwd = bars[i0 + 1:i0 + 16]
        if len(fwd) < 15:
            continue
        c0 = bars[i0][4]
        mx = max(b[2] for b in fwd)
        r["run_xadr"] = (mx - c0) / r["adr_dollar_ep"]
        r["run_pct"] = (mx / c0 - 1) * 100
        r["runner5"] = int(r["run_xadr"] >= 5)
        r["runner8"] = int(r["run_xadr"] >= 8)
        r["peak_session"] = max(range(len(fwd)), key=lambda i: fwd[i][2]) + 1


def fav_mask(rows: list[dict], col: str, kind: str, fav: str, cut: tuple[float, float] | None) -> list[bool | None]:
    out: list[bool | None] = []
    for r in rows:
        v = r.get(col)
        if v is None:
            out.append(None)
        elif kind == "bool":
            out.append(int(v) == int(fav))
        elif kind == "ord":
            out.append(v >= 1)
        else:
            lo, hi = cut
            out.append(v <= lo if fav == "LOWER" else v >= hi)
    return out


def tercile_cuts(vals: list[float]) -> tuple[float, float]:
    s = sorted(vals)
    n = len(s)
    return s[max(0, n // 3 - 1)], s[min(n - 1, (2 * n) // 3)]


def rate(xs: list[int]) -> float | None:
    return sum(xs) / len(xs) if xs else None


def diff_stat(labels: list[int], fav: list[bool]) -> float | None:
    a = [l for l, f in zip(labels, fav) if f]
    b = [l for l, f in zip(labels, fav) if not f]
    if not a or not b:
        return None
    return rate(a) - rate(b)


def perm_p(labels: list[int], fav: list[bool], weeks: list[str], observed: float, rng: random.Random) -> float:
    by_week: dict[str, list[int]] = defaultdict(list)
    for i, w in enumerate(weeks):
        by_week[w].append(i)
    idx_groups = list(by_week.values())
    hits = 0
    lab = list(labels)
    for _ in range(N_PERM):
        for g in idx_groups:
            vals = [lab[i] for i in g]
            rng.shuffle(vals)
            for i, v in zip(g, vals):
                lab[i] = v
        s = diff_stat(lab, fav)
        if s is not None and s >= observed - 1e-12:
            hits += 1
    return hits / N_PERM


def auc(feature: list[float], labels: list[int], fav: str) -> float | None:
    pos = [f for f, l in zip(feature, labels) if l == 1]
    neg = [f for f, l in zip(feature, labels) if l == 0]
    if not pos or not neg:
        return None
    wins = 0.0
    for p in pos:
        for q in neg:
            if p > q:
                wins += 1
            elif p == q:
                wins += 0.5
    a = wins / (len(pos) * len(neg))
    return a if fav in ("HIGHER", "1") else 1 - a


def main() -> None:
    rows = load_features()
    daily = load_daily()
    add_outcomes(rows, daily)
    for r in rows:
        if r.get("ALERT_expct_scheduled") in ("scheduled", "unscheduled"):
            r["ALERT_expct_unscheduled"] = 1.0 if r["ALERT_expct_scheduled"] == "unscheduled" else 0.0
        else:
            r["ALERT_expct_unscheduled"] = None
    out: list[str] = []
    p = out.append
    scored = [r for r in rows if r["runner5"] is not None]
    p(f"#684 RESULTS — {len(rows)} population rows; {len(scored)} with a 15-session outcome; {len(rows) - len(scored)} censored: "
      + ", ".join(f"{r['ticker']} {r['scan_date']}" for r in rows if r["runner5"] is None))
    p(f"draws declared: {len(DRAWS)}   permutation draws per test: {N_PERM}   seed {SEED}   expected chance clears of p<0.05 alone: {0.05 * len(DRAWS):.1f} -> up to 3 is noise")
    p("")
    # ── anchor ───────────────────────────────────────────────────────────────────────────
    anc = [r for r in scored if r["alert_row"] == 1 and r["era"] == "A" and r["evening_rerun_0520"] == 0]
    p(f"ANCHOR: rows with a live alert row, era A, gap-day scan pass: n {len(anc)}, >= 5 ADR {sum(r['runner5'] for r in anc)} ({100 * rate([r['runner5'] for r in anc]):.1f} %) — 09-27 read: 25 of 261 = 9.6 %")
    for lo, hi, name in ((0, 50, "<50"), (50, 65, "50-65"), (65, 80, "65-80"), (80, 999, "80+")):
        g = [r for r in anc if lo <= r["ep_score"] < hi]
        p(f"  score band {name}: n {len(g)}, >= 5 ADR {sum(r['runner5'] for r in g)} ({100 * rate([r['runner5'] for r in g]) if g else 0:.1f} %)")
    p("")
    # ── composition of runners ───────────────────────────────────────────────────────────
    for blk in ("DISCOVERY", "HELD-OUT"):
        g = [r for r in scored if r["block"] == blk]
        p(f"{blk}: n {len(g)}   runners>=5 {sum(r['runner5'] for r in g)} ({100 * rate([r['runner5'] for r in g]):.1f} %)   >=8 {sum(r['runner8'] for r in g)}   "
          f"alerted n {sum(r['alerted'] for r in g)} runners {sum(r['runner5'] for r in g if r['alerted'])}   not-alerted n {sum(1 for r in g if not r['alerted'])} runners {sum(r['runner5'] for r in g if not r['alerted'])}")
    disc = [r for r in scored if r["block"] == "DISCOVERY"]
    held = [r for r in scored if r["block"] == "HELD-OUT"]
    wk = Counter(r["iso_week"] for r in disc if r["runner5"])
    best_week = wk.most_common(1)[0][0] if wk else None
    best_two = [r["ticker"] for r in sorted(disc, key=lambda r: -r["run_xadr"])[:2]]
    p(f"runners by ISO week (discovery): {dict(sorted(wk.items()))}   best week = {best_week}   best two names = {best_two}")
    p(f"labelled EPs: " + "; ".join(f"{t} {d} run_xadr={next((r['run_xadr'] for r in scored if r['ticker'] == t and r['scan_date'] == d), None)}" for t, d in LABELLED))
    p("")
    # ── the draws ────────────────────────────────────────────────────────────────────────
    rng = random.Random(SEED)
    results: list[dict] = []
    header = "feature | when | n disc | fav n / rate | rest n / rate | diff | AUC | p disc | held-out fav n/rate vs rest n/rate (sign) | drop best week diff/p | drop best two diff/p | labelled in fav | verdict"
    p("PER-FEATURE (discovery cut points; rates = share >= 5 ADR):")
    p(header)
    for col, kind, fav, when, name in DRAWS:
        dr = [r for r in disc if r.get(col) is not None]
        hr = [r for r in held if r.get(col) is not None]
        if len(dr) < 30:
            results.append({"feature": col, "when": when, "name": name, "verdict": "no data"})
            p(f"{col} | {when} | {len(dr)} | — | — | — | — | — | — | — | — | — | no data")
            continue
        cut = tercile_cuts([r[col] for r in dr]) if kind == "cont" else None
        fm = fav_mask(dr, col, kind, fav, cut)
        labels = [int(r["runner5"]) for r in dr]
        weeks = [r["iso_week"] for r in dr]
        d_obs = diff_stat(labels, fm)
        n_fav = sum(fm)
        r_fav = rate([l for l, f in zip(labels, fm) if f])
        r_rest = rate([l for l, f in zip(labels, fm) if not f])
        pv = perm_p(labels, fm, weeks, d_obs, rng) if d_obs is not None else None
        a = auc([r[col] for r in dr], labels, fav if kind != "ord" else "HIGHER") if kind != "bool" else auc([float(f) for f in fm], labels, "HIGHER")
        # held-out
        hm = fav_mask(hr, col, kind, fav, cut)
        hl = [int(r["runner5"]) for r in hr]
        h_fav = [l for l, f in zip(hl, hm) if f]
        h_rest = [l for l, f in zip(hl, hm) if not f]
        h_d = diff_stat(hl, hm)
        h_ok = sum(hl) >= 3 and len(h_fav) >= 8 and len(h_rest) >= 8
        h_sign = ("+" if h_d > 0 else "-" if h_d < 0 else "0") if h_d is not None else "—"
        # drop best week
        dw = [i for i, r in enumerate(dr) if r["iso_week"] != best_week]
        d_w = diff_stat([labels[i] for i in dw], [fm[i] for i in dw])
        p_w = perm_p([labels[i] for i in dw], [fm[i] for i in dw], [weeks[i] for i in dw], d_w, rng) if d_w is not None else None
        # drop best two names
        dn = [i for i, r in enumerate(dr) if r["ticker"] not in best_two]
        d_n = diff_stat([labels[i] for i in dn], [fm[i] for i in dn])
        p_n = perm_p([labels[i] for i in dn], [fm[i] for i in dn], [weeks[i] for i in dn], d_n, rng) if d_n is not None else None
        # labelled
        lab_rows = [r for r in scored if (r["ticker"], r["scan_date"]) in LABELLED and r.get(col) is not None]
        lab_fav = sum(f for f in fav_mask(lab_rows, col, kind, fav, cut) if f)
        # verdict
        if d_obs is None or pv is None:
            verdict = "no data"
        elif d_obs < 0:
            verdict = "fail (wrong way)" + (f", p={1 - pv:.3f} the other way" if (1 - pv) < 0.05 else "")
        elif pv >= 0.05:
            verdict = "can't tell (discovery p >= 0.05)"
        elif not h_ok:
            verdict = "can't tell (held-out too thin)"
        elif h_d is None or h_d <= 0:
            verdict = "can't tell (held-out sign against)"
        elif not (d_w is not None and d_w > 0 and p_w is not None and p_w < 0.05):
            verdict = "can't tell (does not survive dropping the best week)"
        elif not (d_n is not None and d_n > 0 and p_n is not None and p_n < 0.05):
            verdict = "can't tell (does not survive dropping the best two names)"
        else:
            verdict = "PASS"
        if lab_rows and lab_fav <= 1 and verdict == "PASS":
            verdict += " ⚠ labelled-EP conflict"
        res = {"feature": col, "when": when, "name": name, "kind": kind, "fav": fav, "cut": cut, "n_disc": len(dr),
               "n_fav": n_fav, "rate_fav": r_fav, "n_rest": len(dr) - n_fav, "rate_rest": r_rest, "diff": d_obs, "auc": a, "p_disc": pv,
               "held_n_fav": len(h_fav), "held_rate_fav": rate(h_fav), "held_n_rest": len(h_rest), "held_rate_rest": rate(h_rest), "held_diff": h_d, "held_sign": h_sign, "held_ok": h_ok,
               "drop_week_diff": d_w, "drop_week_p": p_w, "drop_two_diff": d_n, "drop_two_p": p_n,
               "labelled_in_fav": lab_fav, "labelled_n": len(lab_rows), "verdict": verdict,
               "rate8_fav": rate([int(r["runner8"]) for r, f in zip(dr, fm) if f]), "rate8_rest": rate([int(r["runner8"]) for r, f in zip(dr, fm) if not f])}
        results.append(res)
        p(f"{col} | {when} | {len(dr)} | {n_fav} / {100 * r_fav:.1f}% | {len(dr) - n_fav} / {100 * r_rest:.1f}% | {100 * d_obs:+.1f}pp | {a:.3f} | {pv:.3f} | "
          f"{len(h_fav)}/{100 * rate(h_fav) if h_fav else 0:.0f}% vs {len(h_rest)}/{100 * rate(h_rest) if h_rest else 0:.0f}% ({h_sign}{'' if h_ok else ' thin'}) | "
          f"{100 * d_w:+.1f}pp/{p_w:.3f} | {100 * d_n:+.1f}pp/{p_n:.3f} | {lab_fav} of {len(lab_rows)} | {verdict}")
    p("")
    # ── descriptive tables ───────────────────────────────────────────────────────────────
    p("DESCRIPTIVE (no draw, no verdict) — discovery + held-out pooled, share >= 5 ADR by level (n):")
    for col in DESCRIPTIVE:
        levels = defaultdict(list)
        for r in scored:
            v = r.get(col)
            levels[str(v) if v is not None else "null"].append(int(r["runner5"]))
        items = sorted(levels.items(), key=lambda kv: -len(kv[1]))
        p(f"  {col}: " + "; ".join(f"{k} {100 * rate(v):.0f}% ({sum(v)}/{len(v)})" for k, v in items if len(v) >= 5))
    q = [r for r in scored if r.get("ALERT_q_revenue_yoy_pct") is not None]
    p(f"  ALERT_q_revenue_yoy_pct: filled {len(q)} of {sum(r['alerted'] for r in scored)} alerted — too thin for a draw; runners among filled {sum(r['runner5'] for r in q)}")
    p("")
    # ── runners the score / filters dropped ───────────────────────────────────────────────
    dropped = sorted([r for r in scored if r["runner5"] and not r["alerted"]], key=lambda r: -r["run_xadr"])
    kept = sorted([r for r in scored if r["runner5"] and r["alerted"]], key=lambda r: -r["run_xadr"])
    lines = [f"RUNNERS (>= 5 ADR within 15 sessions) the gap-day scan scored but did NOT alert: {len(dropped)} of {sum(r['runner5'] for r in scored)} runners; "
             f"alerted runners {len(kept)} of {sum(r['alerted'] for r in scored)} alerted rows ({100 * len(kept) / sum(r['alerted'] for r in scored):.1f} %); "
             f"not-alerted runners {len(dropped)} of {sum(1 for r in scored if not r['alerted'])} ({100 * len(dropped) / sum(1 for r in scored if not r['alerted']):.1f} %)",
             "ticker | scan_date | block | ep_score | catalyst | scan verdict | gap % scan | prev close | run ADRs | run % | peak session | ext_5d % | close loc | orb pos"]
    for r in dropped:
        lines.append(f"{r['ticker']} | {r['scan_date']} | {r['block']} | {r['ep_score']:.0f} | {r['PRE_catalyst_quality']} | {'evening re-run alert' if r['evening_rerun_0520'] else 'rejected: score below bar'} | {r['PRE_gap_pct_scan']:.1f} | {r['PRE_prev_close']:.2f} | {r['run_xadr']:.1f} | {r['run_pct']:.0f} | {r.get('peak_session')} | "
                     f"{r.get('PRE_ext_5d_pct') if r.get('PRE_ext_5d_pct') is None else round(r['PRE_ext_5d_pct'], 1)} | {r.get('CLOSE_close_loc') if r.get('CLOSE_close_loc') is None else round(r['CLOSE_close_loc'], 2)} | {r.get('O945_orb_position') if r.get('O945_orb_position') is None else round(r['O945_orb_position'], 2)}")
    lines.append("")
    lines.append("ALERTED runners, for comparison:")
    for r in kept:
        lines.append(f"{r['ticker']} | {r['scan_date']} | {r['block']} | {r['ep_score']:.0f} | {r['PRE_catalyst_quality']} | alerted {r['score_tier']} | {r['PRE_gap_pct_scan']:.1f} | {r['PRE_prev_close']:.2f} | {r['run_xadr']:.1f} | {r['run_pct']:.0f} | {r.get('peak_session')}")
    (HERE / "runners_dropped.txt").write_text("\n".join(lines) + "\n")
    p("\n".join(lines[:1]))
    text = "\n".join(out) + "\n"
    (HERE / "results_out.txt").write_text(text)
    with (HERE / "results.tsv").open("w") as fh:
        keys = ["feature", "when", "name", "kind", "fav", "n_disc", "n_fav", "rate_fav", "n_rest", "rate_rest", "diff", "auc", "p_disc", "held_n_fav", "held_rate_fav", "held_n_rest", "held_rate_rest", "held_diff", "held_sign", "held_ok", "drop_week_diff", "drop_week_p", "drop_two_diff", "drop_two_p", "labelled_in_fav", "labelled_n", "rate8_fav", "rate8_rest", "verdict"]
        fh.write("\t".join(keys) + "\n")
        for res in results:
            fh.write("\t".join("" if res.get(k) is None else (f"{res[k]:.4f}" if isinstance(res[k], float) else str(res[k])) for k in keys) + "\n")
    (HERE / "summary.json").write_text(json.dumps({"n_pop": len(rows), "n_scored": len(scored), "draws": len(DRAWS), "best_week": best_week, "best_two": best_two,
                                                    "runners5": sum(r["runner5"] for r in scored), "runners8": sum(r["runner8"] for r in scored),
                                                    "pass": [r["feature"] for r in results if r.get("verdict", "").startswith("PASS")]}, indent=1))
    with (HERE / "outcomes.tsv").open("w") as fh:
        fh.write("ticker\tscan_date\tblock\talerted\trun_xadr\trun_pct\trunner5\trunner8\tpeak_session\n")
        for r in scored:
            fh.write(f"{r['ticker']}\t{r['scan_date']}\t{r['block']}\t{int(r['alerted'])}\t{r['run_xadr']:.3f}\t{r['run_pct']:.1f}\t{r['runner5']}\t{r['runner8']}\t{r.get('peak_session')}\n")
    print(text)


if __name__ == "__main__":
    main()
