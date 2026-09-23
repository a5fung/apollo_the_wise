#!/usr/bin/env python3
"""Step 3 (TIMELINESS / RUNWAY) of the theme-correctness programme — when the engine
named a theme, how much tradeable runway was left, and could naming have been earlier at
no extra cost?

READ-ONLY, $0, idempotent. Runs entirely on frozen prod exports captured ONCE on
2026-09-07 (step 1's _step1_*.tsv, step 2's _step2_*.tsv, plus ONE new pull —
_step3_clusters.tsv = mi_correlation_clusters). Touches no strategy / entry / exit /
sizing / safeguard / grade / alert / trade code. Never calls an LLM or a paid API.

Plan: ~/.claude/plans/plan-this-out-with-hidden-bentley.md §3 (+ §"HIS POINT — reflexive").
Findings doc: docs/analysis/step3_theme_runway_2026-09-07.md.
Step-1 helpers are REUSED, not rewritten (Prices, Scores, loaders, constants), and the
lineage table is step 1's own output (_step1_theme_precision_lineages.tsv) — the 398
lineages, their founders, birth class (grind / co-gap) and maturity are not re-derived.

THE OPERATOR'S FRAMING (plan §HIS POINT): a gap MANUFACTURES relative strength, so a theme
named after the first EP is NOT late — that is the normal causal order. The question is
how much runway was left: at naming, what share of the theme's eventual members had NOT
yet had their EP.

What it computes, per lineage:
  MEMBERS   = eventual members — every ticker in ANY non-Retired snapshot of ANY name in
              the lineage (NOT the birth row: using the birth row makes a co-gap-born
              theme's runway zero by construction). Per member, its FIRST-JOIN snapshot
              date. A theme_date = D row is written ~17:07 ET on D, so a member is on
              the list (tradeable from it) from D + 1.
  HAD AN EP = an alert row (mi_ep_alerts UNION mi_theme_axis_shadow — the shadow is the
              fuller record: mi_ep_alerts starts 05-11 and misses 254 shadow rows) OR a
              scan-log row at/above THAT DAY'S acting gap floor (floor derived per
              scan_date from the log itself; rows the log tags universe_floor /
              gap_floor — sub-floor capture from 08-24 — are excluded). Secondary leg
              (+O): the uniform open-gap read (open / prior close - 1 >= 9%) from
              closes, the only pre-birth EP read for births before the scan log.
  RUNWAY    = pre window = the 20 sessions before birth THROUGH birth day (the birth-day
              row is written after the close, so a birth-day EP happened before naming);
              post window = the 20 sessions after birth. EPers = members with an EP in
              either window. runway = post-only EPers / EPers. Undefined (its own class)
              when a lineage has no EPer at all. DELIVERED runway = post EPers whose
              first-join snapshot is STRICTLY BEFORE the EP date (the theme pointed at the
              name before it gapped); the rest are POST-HOC additions (joined on/after
              their gap — Lane-2 / reflexive membership, and exactly the class the
              theme_engine.py:4567 no-thesis validation bug can hold wrongly).
              Reported per lineage (p10..p90, share at exactly 0 / 1 — the coarseness
              check step 2 taught) AND pooled at member level (the continuous version),
              split grind / co-gap (step 1's class) and matured / not, eras apart,
              40/40-session windows as sensitivity on the uncensored subset.
  IGNITION  = earliest of, in [birth - 40, birth + 20] sessions: (RS) members' mean RS
              >= 70 on 3 consecutive score dates · (CL) >= half the members in ONE stored
              mi_correlation_clusters cluster · (EP) the first EP among members.
              lag = birth - ignition in sessions (negative = named before). Each leg's
              fire rate is reported BEFORE any "which fired first" tally (saturation
              check); founders variants and the continuous max cluster share alongside.
  CLUSTERS  = cluster -> theme conversion. Cluster-days are chained into cluster-lineages
              with the engine's own coverage convention (>= 0.5 of the later cluster
              inside the prior stored day's). A cluster converts if a theme lineage is
              born within 20 sessions whose FOUNDERS cover >= 50% of it (loose variant:
              eventual members). lead = birth - first cluster day; lead 0 is reported
              apart because the discovery prompt is handed the clusters THE SAME NIGHT
              ("propose it as a Nascent theme") — a same-night conversion is the engine
              naming its own seed, not a cluster that preceded a birth.
              ⚠ BIAS, stated everywhere it is used: _dedup_against_themes drops clusters
              >= 50% covered by an active theme BEFORE the write, so stored history is
              UNCOVERED clusters only. The conversion rate is a FLOOR, not a rate, and
              the cluster ignition leg can only fire pre-birth by construction.

Run:  python3 scripts/probes/_step3_theme_runway.py
Out:  scripts/probes/_step3_theme_runway_out.txt (+ _lineages.tsv, _members.tsv,
      _clusters.tsv)
"""
from __future__ import annotations

import csv
import os
import statistics
import sys
from collections import Counter, defaultdict
from datetime import date, timedelta

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, "..", ".."))
sys.path.insert(0, ROOT)
sys.path.insert(0, HERE)

import _step1_theme_precision as s1  # noqa: E402  — REUSE: Prices, Scores, loaders, constants

OUT_TXT = os.path.join(HERE, "_step3_theme_runway_out.txt")
OUT_LIN = os.path.join(HERE, "_step3_theme_runway_lineages.tsv")
OUT_MEM = os.path.join(HERE, "_step3_theme_runway_members.tsv")
OUT_CL = os.path.join(HERE, "_step3_theme_runway_clusters.tsv")

PRE, POST = 20, 20            # primary windows (sessions) — the engine's window everywhere
PRE_S, POST_S = 40, 40        # sensitivity windows on the uncensored subset
IGN_BACK, IGN_FWD = 40, 20    # ignition search window around birth (sessions)
RS_LEVEL = s1.ASSIGN_POOL_RS_FLOOR   # 70
RS_HOLD = 3                   # consecutive score dates the mean must hold >= RS_LEVEL
CLUSTER_COVER = 0.5           # _dedup_against_themes: ">= 50% of members" — the engine's convention
CONVERT_SESSIONS = 20         # a birth within this many sessions after a cluster day converts it
CHAIN_MAX_GAP_DAYS = 7        # cluster-day chaining only across a hole this short (calendar days)
OPEN_GAP_PCT = s1.MIN_GAP_PCT           # 9.0 — the uniform open-gap read step 1 validated (91.8%)
SUBFLOOR_STAGES = {"universe_floor", "gap_floor"}
SUBFLOOR_REASON = "universe_below_gap_floor"
# Universe-stage rejects (price < $5 / illiquid / below the acting gap floor) are logged only from
# the 08-24 capture change and mostly carry NO reject_stage — on 08-24..08-28 that is ~1,500 rows a
# day with 5-9% gaps. They never entered the EP funnel and are excluded from the scan leg entirely.
UNIVERSE_REJECT_PREFIX = "filter:universe_"
CLUSTER_LIVE_FROM = date(2026, 4, 17)   # commit f70bf9ab: clusters persisted + injected into discovery
SCAN_LOG_START = s1.SCAN_LOG_START      # 2026-04-13
SHADOW_START = date(2026, 3, 24)        # first mi_theme_axis_shadow row (census)

LOG: list[str] = []


def say(s: str = "") -> None:
    LOG.append(s)
    print(s)


def pct(n: int, d: int) -> str:
    return s1.pct(n, d)


def q(xs, ps=(10, 25, 50, 75, 90)) -> str:
    xs = [x for x in xs if x is not None]
    if not xs:
        return "n/a"
    return " / ".join(f"{np.percentile(xs, p):.0f}%" for p in ps) + f"  (n={len(xs)})"


def qn(xs, ps=(25, 50, 75), fmt="{:.0f}") -> str:
    xs = [x for x in xs if x is not None]
    if not xs:
        return "n/a"
    return " / ".join(fmt.format(np.percentile(xs, p)) for p in ps) + f"  (n={len(xs)})"


def load_tsv(path: str) -> list[dict]:
    """psql unaligned export: 2 preamble lines, then a tab header."""
    with open(path) as fh:
        lines = fh.read().splitlines()
    rows = list(csv.DictReader(lines[2:], delimiter="\t"))
    first = list(rows[0].keys())[0] if rows else None
    return [r for r in rows if not (first and r[first].startswith("("))]


def load2(name: str) -> list[dict]:
    return load_tsv(os.path.join(HERE, f"_step2_{name}.tsv"))


def d_(s: str) -> date:
    return date.fromisoformat(s[:10])


def main() -> None:
    say("=== STEP 3 TIMELINESS / RUNWAY probe — frozen prod exports of 2026-09-07 ===")
    say(f"windows: pre {PRE} / post {POST} sessions (sensitivity {PRE_S}/{POST_S}); ignition search "
        f"[-{IGN_BACK}, +{IGN_FWD}]; RS leg = mean RS >= {RS_LEVEL:.0f} held {RS_HOLD} score dates; cluster "
        f"leg = >= {CLUSTER_COVER:.0%} of members in one stored cluster; open-gap read >= {OPEN_GAP_PCT:.0f}%")

    themes_raw = s1.load("themes")
    prices = s1.Prices(s1.load("closes"))
    scores = s1.Scores(s1.load("scores_all"))
    cal, idx = prices.cal, prices.idx
    last_idx = len(cal) - 1
    say(f"price calendar {cal[0]}..{cal[-1]} ({len(cal)} sessions); score dates {len(scores.all_dates)}")

    # ---- lineages: step 1's own output --------------------------------------------------
    with open(os.path.join(HERE, "_step1_theme_precision_lineages.tsv")) as fh:
        lin_rows = list(csv.DictReader(fh, delimiter="\t"))
    lineages = []
    for r in lin_rows:
        lineages.append({
            "id": int(r["id"]), "birth": d_(r["birth"]), "birth_name": r["birth_name"],
            "names": r["names"].split("|"), "founders": [t for t in r["founders"].split("|") if t],
            "class": r["class"], "matured": r["matured"] == "True", "alive": r["alive"] == "True",
            "last_live": d_(r["last_live"]), "life_days": int(r["life_days"]),
        })
    say(f"lineages (step 1): {len(lineages)}; class {dict(Counter(L['class'] for L in lineages))}; "
        f"matured {sum(L['matured'] for L in lineages)}")

    # ---- eventual members + first-join snapshot per member --------------------------------
    rows_by_name: dict[str, list[dict]] = defaultdict(list)
    for r in themes_raw:
        if r["tickers"] and r["stage"] != "Retired":
            rows_by_name[r["name"]].append({"date": d_(r["theme_date"]), "tickers": r["tickers"].split(",")})
    for L in lineages:
        first_join: dict[str, date] = {}
        for nm in L["names"]:
            for row in rows_by_name.get(nm, []):
                for t in row["tickers"]:
                    if t not in first_join or row["date"] < first_join[t]:
                        first_join[t] = row["date"]
        L["members"] = sorted(first_join)
        L["first_join"] = first_join
        L["i0"] = prices.session_on_or_before(L["birth"])
        L["i_last"] = prices.session_on_or_before(L["last_live"])
    n_mem = [len(L["members"]) for L in lineages]
    n_fnd = [len(L["founders"]) for L in lineages]
    say(f"eventual members per lineage: p25/median/p75 = {qn(n_mem)}; founders {qn(n_fnd)}; "
        f"lineages whose eventual set exceeds the founders: {sum(1 for L in lineages if len(L['members']) > len(L['founders']))}")

    # ---- EP events per ticker ------------------------------------------------------------
    alerts = load2("alerts")
    shadow = load2("shadow")
    scan = load2("scan")
    ep_alert: dict[str, set[int]] = defaultdict(set)
    src = Counter()
    a_set = {(r["ticker"], d_(r["alert_date"])) for r in alerts}
    s_set = {(r["ticker"], d_(r["alert_date"])) for r in shadow}
    for t, d in a_set | s_set:
        i = idx.get(d)
        if i is None:
            i = prices.session_on_or_before(d)
        if i is not None:
            ep_alert[t].add(i)
    src["mi_ep_alerts rows"] = len(a_set); src["shadow rows"] = len(s_set)
    src["in both"] = len(a_set & s_set); src["shadow only"] = len(s_set - a_set); src["alerts only"] = len(a_set - s_set)
    say(f"\n--- EP EVENT LEGS ---\nalert leg (ticker, day): {dict(src)}")
    # scan leg: per-day acting floor derived from the log itself
    by_day: dict[date, list[dict]] = defaultdict(list)
    for r in scan:
        by_day[d_(r["scan_date"])].append(r)
    floor_by_day: dict[date, float] = {}
    sub_tagged = universe_rej = 0

    def _excluded(r: dict) -> bool:
        return (r["reject_stage"] in SUBFLOOR_STAGES or SUBFLOOR_REASON in r["filter_reason"]
                or r["filter_reason"].startswith(UNIVERSE_REJECT_PREFIX))

    for d, rs in by_day.items():
        gaps = []
        for r in rs:
            if _excluded(r):
                sub_tagged += r["reject_stage"] in SUBFLOOR_STAGES or SUBFLOOR_REASON in r["filter_reason"]
                universe_rej += r["filter_reason"].startswith(UNIVERSE_REJECT_PREFIX)
                continue
            if r["gap_pct"]:
                gaps.append(float(r["gap_pct"]))
        if gaps:
            floor_by_day[d] = min(gaps)
    breaks, prev = [], None
    for d in sorted(floor_by_day):
        f = round(floor_by_day[d], 0)
        if f != prev:
            breaks.append((d, floor_by_day[d]))
            prev = f
    say(f"scan leg: {len(scan)} rows over {len(by_day)} scan days; sub-floor-tagged rows excluded: {sub_tagged}; universe-stage "
        f"rejects excluded: {universe_rej} (first such row {min((d_(r['scan_date']) for r in scan if r['filter_reason'].startswith(UNIVERSE_REJECT_PREFIX)), default=None)}); "
        f"acting floor breaks (first day at each floor, with that day's row count): "
        + ", ".join(f"{d}={f:.2f}% ({sum(1 for r in by_day[d] if not _excluded(r))} rows)" for d, f in breaks))
    ep_scan: dict[str, set[int]] = defaultdict(set)
    scan_pairs = set()
    for r in scan:
        if _excluded(r) or not r["gap_pct"]:
            continue
        d = d_(r["scan_date"])
        if float(r["gap_pct"]) >= floor_by_day.get(d, 1e9):
            scan_pairs.add((r["ticker"], d))
    for t, d in scan_pairs:
        i = idx.get(d)
        if i is not None:
            ep_scan[t].add(i)
    ep_AS: dict[str, set[int]] = defaultdict(set)
    for t in set(ep_alert) | set(ep_scan):
        ep_AS[t] = ep_alert.get(t, set()) | ep_scan.get(t, set())
    alert_pairs = {(t, cal[i]) for t, s in ep_alert.items() for i in s}
    say(f"scan leg (ticker, day) at/above the day's floor: {len(scan_pairs)}; alert pairs not in the scan leg: "
        f"{len(alert_pairs - scan_pairs)} (of {len(alert_pairs)}; pre-04-13 alerts + the 84 backfilled rows step 2 found); "
        f"primary 'had an EP' = alert OR scan = {sum(len(s) for s in ep_AS.values())} ticker-days")

    def ep_hits(t: str, lo: int, hi: int, with_open, alerts_only: bool = False) -> list[int]:
        src_set = ep_alert if alerts_only else ep_AS
        hits = {i for i in src_set.get(t, ()) if lo <= i <= hi}
        if with_open:
            hits |= set(prices.open_gap_sessions(t, max(lo, 1), hi, OPEN_GAP_PCT))
        return sorted(hits)

    # ---- RUNWAY --------------------------------------------------------------------------
    member_rows = []

    def runway(L: dict, pre: int, post: int, with_open: bool, alerts_only: bool = False) -> dict:
        i0 = L["i0"]
        lo, hi = max(i0 - pre, 0), min(i0 + post, last_idx)
        out = {"censored": i0 + post > last_idx, "n_pre": 0, "n_post": 0, "n_cov": 0, "n_hoc": 0,
               "n_none": 0, "n_post_after_death": 0, "post_lags": [], "cov_lags": [], "rows": []}
        for m in L["members"]:
            hits = ep_hits(m, lo, hi, with_open, alerts_only)
            pre_hits = [h for h in hits if h <= i0]
            post_hits = [h for h in hits if h > i0]
            j = prices.session_on_or_before(L["first_join"][m])
            row = {"lineage": L["id"], "ticker": m, "class": L["class"], "first_join": L["first_join"][m],
                   "founder": m in L["founders"], "ep_class": "none", "ep_idx": None, "covered": None, "lag": None}
            if pre_hits:
                out["n_pre"] += 1; row["ep_class"] = "pre"; row["ep_idx"] = pre_hits[0]
                row["lag"] = i0 - pre_hits[0]
            elif post_hits:
                e = post_hits[0]
                cov = j is not None and j < e            # on the list strictly before the gap day
                out["n_post"] += 1; out["n_cov" if cov else "n_hoc"] += 1
                out["post_lags"].append(e - i0)
                if cov:
                    out["cov_lags"].append(e - i0)
                if e > L["i_last"]:
                    out["n_post_after_death"] += 1
                row.update({"ep_class": "post", "ep_idx": e, "covered": cov, "lag": e - i0})
            else:
                out["n_none"] += 1
            out["rows"].append(row)
        n_ep = out["n_pre"] + out["n_post"]
        out["n_ep"] = n_ep
        out["runway"] = out["n_post"] / n_ep if n_ep else None
        out["delivered"] = out["n_cov"] / n_ep if n_ep else None
        out["share_all"] = out["n_post"] / len(L["members"]) if L["members"] else None
        return out

    for L in lineages:
        L["rw"] = runway(L, PRE, POST, False)
        L["rwo"] = runway(L, PRE, POST, True)
        L["rw40"] = runway(L, PRE_S, POST_S, False)
        L["rwo40"] = runway(L, PRE_S, POST_S, True)
        L["rwa"] = runway(L, PRE, POST, False, alerts_only=True)
        member_rows.extend(L["rw"]["rows"])
        pre_start = cal[max(L["i0"] - PRE, 0)]
        L["era"] = ("E0 pre-window before the scan log" if pre_start < SCAN_LOG_START
                    else "E1+ pre-window scan-covered")

    def runway_block(title: str, key: str, rows: list[dict]) -> None:
        say(f"\n{title}")
        say(f"  {'population':44s} {'n':>4s} {'no EPer':>7s} {'runway p10/p25/p50/p75/p90':>40s}  {'=0':>5s} {'=1':>5s}  "
            f"{'pooled post/EPers':>18s} {'pooled DELIVERED':>16s} {'post-hoc':>9s}  {'>=1 post':>8s} {'>=1 deliv':>9s}")
        for lab, pred in (("all", lambda L: True),
                          ("grind-born", lambda L: L["class"] == "grind"),
                          ("co-gap-born", lambda L: L["class"] == "cogap"),
                          ("matured (Mainstream)", lambda L: L["matured"]),
                          ("never matured", lambda L: not L["matured"]),
                          ("grind & matured", lambda L: L["class"] == "grind" and L["matured"]),
                          ("grind & not", lambda L: L["class"] == "grind" and not L["matured"]),
                          ("co-gap & matured", lambda L: L["class"] == "cogap" and L["matured"]),
                          ("co-gap & not", lambda L: L["class"] == "cogap" and not L["matured"]),
                          ("E0 (pre-window before scan log)", lambda L: L["era"].startswith("E0")),
                          ("E1+ (scan-covered)", lambda L: L["era"].startswith("E1")),
                          ("UNCENSORED (post window inside data)", lambda L: not L[key]["censored"]),
                          ("E1+ & uncensored", lambda L: L["era"].startswith("E1") and not L[key]["censored"]),
                          ("E1+ & uncensored & grind", lambda L: L["era"].startswith("E1") and not L[key]["censored"] and L["class"] == "grind"),
                          ("E1+ & uncensored & co-gap", lambda L: L["era"].startswith("E1") and not L[key]["censored"] and L["class"] == "cogap"),
                          ("E1+ & uncensored & matured", lambda L: L["era"].startswith("E1") and not L[key]["censored"] and L["matured"]),
                          ("E1+ & uncensored & not matured", lambda L: L["era"].startswith("E1") and not L[key]["censored"] and not L["matured"])):
            sub = [L for L in rows if pred(L)]
            R = [L[key] for L in sub]
            defined = [r for r in R if r["runway"] is not None]
            rw = [100 * r["runway"] for r in defined]
            n_ep = sum(r["n_ep"] for r in R); n_post = sum(r["n_post"] for r in R); n_cov = sum(r["n_cov"] for r in R)
            z = sum(1 for r in defined if r["runway"] == 0); o = sum(1 for r in defined if r["runway"] == 1)
            say(f"  {lab:44s} {len(sub):4d} {len(R) - len(defined):7d} {q(rw):>40s}  {z:5d} {o:5d}  "
                f"{pct(n_post, n_ep):>18s} {pct(n_cov, n_ep):>16s} {n_post - n_cov:9d}  "
                f"{sum(1 for r in R if r['n_post'] > 0):8d} {sum(1 for r in R if r['n_cov'] > 0):9d}")

    say(f"\n--- 1. RUNWAY — at naming, what share of the members that EP'd (pre {PRE} sessions through birth day, "
        f"post {POST}) still had their EP AHEAD? ---")
    say("  'no EPer' = lineages with no member EP in either window (their own class, not 0). '=0'/'=1' = lineages at exactly "
        "0% / 100% (coarseness). 'pooled' = member-level across the population (the continuous read). DELIVERED = the post-EP "
        "name was on the theme's list on a snapshot strictly before its gap day; post-hoc = it joined on/after the gap.")
    runway_block(f"PRIMARY (alert OR scan-log >= day's floor), {PRE}/{POST}", "rw", lineages)
    runway_block(f"+OPEN-GAP leg (adds open/prev close - 1 >= {OPEN_GAP_PCT:.0f}% from closes — the only pre-birth EP read for E0), {PRE}/{POST}", "rwo", lineages)
    runway_block(f"ALERTS-ONLY leg (mi_ep_alerts UNION shadow — names the system actually ALERTED on; sub-bar scan gaps excluded), {PRE}/{POST}", "rwa", lineages)
    unc = [L for L in lineages if not L["rw40"]["censored"]]
    runway_block(f"SENSITIVITY {PRE_S}/{POST_S}, primary legs, uncensored births only (birth + {POST_S} sessions inside the data)", "rw40", unc)
    runway_block(f"SENSITIVITY {PRE_S}/{POST_S}, +open-gap, uncensored only", "rwo40", unc)

    # coarseness + timing detail
    R = [L["rw"] for L in lineages]
    say(f"\n  EPers per lineage (primary {PRE}/{POST}): {dict(sorted(Counter(min(r['n_ep'], 6) for r in R).items()))}  (6 = 6+); "
        f"lineages with exactly one EPer: {sum(1 for r in R if r['n_ep'] == 1)} — runway is 0% or 100% there by arithmetic")
    say(f"  post-window censored (birth + {POST} sessions beyond {cal[-1]}): {sum(1 for r in R if r['censored'])} of {len(R)}; "
        f"{PRE_S}/{POST_S} uncensored: {len(unc)}")
    post_lags = [x for r in R for x in r["post_lags"]]
    cov_lags = [x for r in R for x in r["cov_lags"]]
    say(f"  sessions from naming to the post-EP (all post EPers): p25/median/p75 = {qn(post_lags)}; delivered only: {qn(cov_lags)}")
    say(f"  post EPs that came AFTER the lineage's last live snapshot: {sum(r['n_post_after_death'] for r in R)} of {sum(r['n_post'] for r in R)}")
    mem_pre = [r for r in member_rows if r["ep_class"] == "pre"]
    say(f"  pre-EPers: {len(mem_pre)}, of which founders {sum(r['founder'] for r in mem_pre)}; sessions from their EP to birth "
        f"p25/median/p75 = {qn([r['lag'] for r in mem_pre])} (0 = gapped on birth day)")
    mem_post = [r for r in member_rows if r["ep_class"] == "post"]
    say(f"  post-EPers: {len(mem_post)}, founders among them {sum(r['founder'] for r in mem_post)}; delivered {sum(bool(r['covered']) for r in mem_post)} "
        f"(founders {sum(r['founder'] and r['covered'] for r in mem_post)}), post-hoc {sum(not r['covered'] for r in mem_post)}")
    hoc_same = sum(1 for r in mem_post if not r["covered"] and prices.session_on_or_before(r["first_join"]) == r["ep_idx"])
    say(f"  post-hoc joiners that joined ON their gap day (the same-night Lane-2 add): {hoc_same}; later: "
        f"{sum(1 for r in mem_post if not r['covered']) - hoc_same}")
    # by class, delivered per lineage with >=1 post EP
    for cls in ("grind", "cogap"):
        sub = [L for L in lineages if L["class"] == cls and L["rw"]["n_post"] > 0]
        say(f"  {cls:5s} lineages with >=1 post-EP: {len(sub)} of {sum(1 for L in lineages if L['class']==cls)}; "
            f"of those, at least one DELIVERED (on the list before the gap): {sum(1 for L in sub if L['rw']['n_cov'] > 0)}; "
            f"median members {statistics.median(len(L['members']) for L in sub) if sub else 'n/a'}")
    # continuous: share of ALL eventual members that EP'd after naming
    for cls in ("grind", "cogap"):
        sub = [L for L in lineages if L["class"] == cls]
        say(f"  {cls:5s} share of ALL eventual members with a post-naming EP: p25/median/p75 = "
            f"{qn([100 * L['rw']['share_all'] for L in sub], fmt='{:.0f}%')}; pooled "
            f"{pct(sum(L['rw']['n_post'] for L in sub), sum(len(L['members']) for L in sub))}")
    # by birth month
    bm = defaultdict(lambda: [0, 0, 0, 0])
    for L in lineages:
        r = L["rw"]; k = bm[L["birth"].strftime("%Y-%m")]
        k[0] += 1; k[1] += r["n_ep"]; k[2] += r["n_post"]; k[3] += r["n_cov"]
    say("  by birth month — lineages / EPers / post / delivered: " +
        "  ".join(f"{m}: {v[0]}/{v[1]}/{v[2]}/{v[3]}" for m, v in sorted(bm.items())))

    # ---- IGNITION ------------------------------------------------------------------------
    say(f"\n--- 2. IGNITION — earliest of RS-held / cluster / first-EP in [birth-{IGN_BACK}, birth+{IGN_FWD}] sessions; "
        f"lag = birth - ignition (sessions; negative = named before) ---")
    cl_rows = load_tsv(os.path.join(HERE, "_step3_clusters.tsv"))
    clusters_by_date: dict[date, dict[str, dict]] = defaultdict(dict)
    for r in cl_rows:
        d = d_(r["cluster_date"])
        c = clusters_by_date[d].setdefault(r["cluster_hash"], {"tickers": set(), "n": int(r["member_count"]),
                                                               "corr": float(r["mean_corr"]), "avg_rs": float(r["avg_rs"])})
        c["tickers"].add(r["ticker"])
    cl_dates = sorted(clusters_by_date)
    n_clusters = sum(len(v) for v in clusters_by_date.values())
    say(f"mi_correlation_clusters: {len(cl_rows)} ticker-rows = {n_clusters} clusters over {len(cl_dates)} dates "
        f"({cl_dates[0]}..{cl_dates[-1]}); size distribution: 4={sum(1 for v in clusters_by_date.values() for c in v.values() if c['n']==4)} "
        f"5-8={sum(1 for v in clusters_by_date.values() for c in v.values() if 5<=c['n']<=8)} 9+={sum(1 for v in clusters_by_date.values() for c in v.values() if c['n']>=9)}")
    holes = [(a, b) for a, b in zip(cl_dates, cl_dates[1:]) if (b - a).days > 4]
    say(f"stored-cluster holes > 4 calendar days: {', '.join(f'{a}->{b} ({(b-a).days}d)' for a, b in holes)}")
    cl_date_idx = {d: prices.session_on_or_before(d) for d in cl_dates}
    score_dates = [d for d in scores.all_dates if d >= cal[0]]

    def rs_ignition(members: list[str], lo: int, hi: int):
        """Earliest score date (as a session index) where the members' mean RS >= RS_LEVEL on RS_HOLD
        consecutive populated score dates. Requires >= min(2, |members|) members with a row."""
        need = min(2, len(members))
        ds = [d for d in score_dates if cal[lo] <= d <= cal[hi]]
        hot = []
        for d in ds:
            vals = [scores.rs[d][m] for m in members if m in scores.rs[d]]
            hot.append(len(vals) >= need and float(np.mean(vals)) >= RS_LEVEL)
        for k in range(len(ds) - RS_HOLD + 1):
            if all(hot[k:k + RS_HOLD]):
                return prices.session_on_or_before(ds[k])
        return None

    def cluster_ignition(members: list[str], lo: int, hi: int):
        """Earliest stored cluster day with >= CLUSTER_COVER of `members` in ONE cluster; also the max
        share seen in the window and the count of stored-cluster days inside it."""
        M = set(members)
        best, first, days = 0.0, None, 0
        for d in cl_dates:
            i = cl_date_idx[d]
            if i is None or not (lo <= i <= hi):
                continue
            days += 1
            for c in clusters_by_date[d].values():
                share = len(c["tickers"] & M) / len(M) if M else 0.0
                if share > best:
                    best = share
                if share >= CLUSTER_COVER and first is None:
                    first = i
        return first, best, days

    for L in lineages:
        i0 = L["i0"]
        lo, hi = max(i0 - IGN_BACK, 0), min(i0 + IGN_FWD, last_idx)
        M, F = L["members"], L["founders"]
        L["ign_rs"] = rs_ignition(M, lo, hi)
        L["ign_rs_f"] = rs_ignition(F, lo, hi)
        L["ign_rs20"] = rs_ignition(M, max(i0 - 20, 0), hi)
        L["ign_cl"], L["cl_max_share"], L["cl_days"] = cluster_ignition(M, lo, hi)
        L["ign_cl_f"], L["cl_max_share_f"], _ = cluster_ignition(F, lo, hi)
        eps = sorted(e for m in M for e in ep_AS.get(m, ()) if lo <= e <= hi)
        L["ign_ep"] = eps[0] if eps else None
        epso = sorted({e for m in M for e in ep_hits(m, lo, hi, True)})
        L["ign_epo"] = epso[0] if epso else None
        legs = {"RS": L["ign_rs"], "CL": L["ign_cl"], "EP": L["ign_ep"]}
        fired = {k: v for k, v in legs.items() if v is not None}
        L["n_legs"] = len(fired)
        if fired:
            m = min(fired.values())
            winners = sorted(k for k, v in fired.items() if v == m)
            L["ign"] = m; L["first_leg"] = "+".join(winners); L["lag"] = i0 - m
        else:
            L["ign"] = None; L["first_leg"] = "none"; L["lag"] = None

    def ign_block(rows: list[dict], title: str) -> None:
        say(f"\n  {title} (n={len(rows)})")
        for leg, key in (("RS: mean RS>=70 held 3 score dates (eventual members)", "ign_rs"),
                         ("RS: same, founders", "ign_rs_f"),
                         ("RS: eventual members, 20-session lookback only", "ign_rs20"),
                         ("CL: >=half of eventual members in one stored cluster", "ign_cl"),
                         ("CL: >=half of FOUNDERS in one stored cluster", "ign_cl_f"),
                         ("EP: first alert/scan EP among members", "ign_ep"),
                         ("EP: +open-gap leg", "ign_epo")):
            f = [L for L in rows if L[key] is not None]
            lags = [L["i0"] - L[key] for L in f]
            pre = sum(1 for x in lags if x > 0); same = sum(1 for x in lags if x == 0)
            say(f"    {leg:58s} fires {pct(len(f), len(rows)):>16s}; lag p25/med/p75 = {qn(lags):>22s}; before birth {pre}, "
                f"on birth day {same}, after {len(lags) - pre - same}; at the -{IGN_BACK} boundary {sum(1 for L in f if L['i0'] - L[key] >= IGN_BACK)}")
        say(f"    cluster-leg coverage: stored-cluster days inside the window p25/med/p75 = {qn([L['cl_days'] for L in rows])}; "
            f"lineages with ZERO stored-cluster days in their window: {sum(1 for L in rows if L['cl_days'] == 0)}")
        say(f"    continuous: max share of eventual members ever together in one stored cluster (window) p25/med/p75 = "
            f"{qn([100 * L['cl_max_share'] for L in rows], fmt='{:.0f}%')}; founders variant {qn([100 * L['cl_max_share_f'] for L in rows], fmt='{:.0f}%')}")
        fl = Counter(L["first_leg"] for L in rows)
        say(f"    WHICH FIRED FIRST (all lineages): {dict(fl.most_common())}")
        two = [L for L in rows if L["n_legs"] >= 2]
        say(f"    ...restricted to lineages where >=2 legs fired (n={len(two)}): {dict(Counter(L['first_leg'] for L in two).most_common())}")
        lg = [L["lag"] for L in rows if L["lag"] is not None]
        say(f"    lag = birth - earliest ignition: p10/p25/med/p75/p90 = {qn(lg, ps=(10, 25, 50, 75, 90))}; named BEFORE any ignition "
            f"(lag<0) {sum(1 for x in lg if x < 0)}; same day {sum(1 for x in lg if x == 0)}; after {sum(1 for x in lg if x > 0)}")
        # size dependence of the cluster leg (saturation in reverse)
        for lab, pred in (("<=4 members", lambda L: len(L["members"]) <= 4), ("5-8", lambda L: 5 <= len(L["members"]) <= 8),
                          ("9+", lambda L: len(L["members"]) >= 9)):
            s = [L for L in rows if pred(L)]
            say(f"    cluster leg by lineage size {lab:12s}: fires {pct(sum(L['ign_cl'] is not None for L in s), len(s))}; "
                f"RS leg fires {pct(sum(L['ign_rs'] is not None for L in s), len(s))}; EP leg fires {pct(sum(L['ign_ep'] is not None for L in s), len(s))}")

    ign_block(lineages, "ALL lineages")
    ign_block([L for L in lineages if L["class"] == "grind"], "GRIND-born")
    ign_block([L for L in lineages if L["class"] == "cogap"], "CO-GAP-born")
    ign_block([L for L in lineages if L["matured"]], "matured")
    ign_block([L for L in lineages if not L["matured"]], "never matured")
    ign_block([L for L in lineages if L["birth"] >= date(2026, 4, 13)], "births >= 2026-04-13 (stored clusters + scan log exist in the window)")

    # ---- CLUSTER -> THEME CONVERSION ---------------------------------------------------------
    say(f"\n--- 3. CLUSTER -> THEME CONVERSION (stored clusters are UNCOVERED-by-theme only — a FLOOR) ---")
    # chain cluster-days into cluster-lineages (engine convention: >= 50% of the later cluster inside the prior day's)
    clin: list[dict] = []
    prev_map: dict[str, int] = {}
    prev_date = None
    cluster_days = []
    for d in cl_dates:
        cur_map: dict[str, int] = {}
        chain_ok = prev_date is not None and (d - prev_date).days <= CHAIN_MAX_GAP_DAYS
        for h, c in clusters_by_date[d].items():
            best, bl = 0.0, None
            if chain_ok:
                for ph, li in prev_map.items():
                    P = clusters_by_date[prev_date][ph]["tickers"]
                    cov = len(P & c["tickers"]) / len(c["tickers"])
                    if cov > best:
                        best, bl = cov, li
            if bl is not None and best >= CLUSTER_COVER:
                li = bl
                clin[li]["days"].append(d); clin[li]["union"] |= c["tickers"]
            else:
                li = len(clin)
                clin.append({"id": li, "first": d, "days": [d], "first_tickers": set(c["tickers"]), "union": set(c["tickers"]),
                             "n": c["n"], "corr": c["corr"], "avg_rs": c["avg_rs"]})
            cur_map[h] = li
            cluster_days.append({"date": d, "hash": h, "lineage": li, "tickers": c["tickers"], "n": c["n"], "corr": c["corr"], "avg_rs": c["avg_rs"]})
        prev_map, prev_date = cur_map, d
    say(f"cluster-days {len(cluster_days)} -> cluster-lineages {len(clin)} (chained at >= {CLUSTER_COVER:.0%} coverage across "
        f"consecutive stored days <= {CHAIN_MAX_GAP_DAYS} calendar days apart); days per cluster-lineage p25/med/p75 = "
        f"{qn([len(c['days']) for c in clin])}; single-day cluster-lineages {sum(1 for c in clin if len(c['days']) == 1)}")

    births_by_idx: dict[int, list[dict]] = defaultdict(list)
    for L in lineages:
        births_by_idx[L["i0"]].append(L)

    def converts(tickers: set[str], d: date, loose: bool):
        """Earliest theme lineage born in [d, d + CONVERT_SESSIONS] sessions whose founders (or eventual
        members when loose) cover >= CLUSTER_COVER of the cluster. Returns (lineage, lead_sessions) or None."""
        i = cl_date_idx[d]
        if i is None:
            return None
        for k in range(0, CONVERT_SESSIONS + 1):
            for L in births_by_idx.get(i + k, []):
                S = set(L["members"] if loose else L["founders"])
                if len(S & tickers) / len(tickers) >= CLUSTER_COVER:
                    return L, k
        return None

    conv_day = conv_day_loose = 0
    for cd in cluster_days:
        r = converts(cd["tickers"], cd["date"], False)
        cd["conv"] = r[0]["id"] if r else None; cd["lead"] = r[1] if r else None
        rl = converts(cd["tickers"], cd["date"], True)
        cd["conv_loose"] = rl[0]["id"] if rl else None
        conv_day += r is not None; conv_day_loose += rl is not None
    say(f"per cluster-DAY: converts (founders cover >= {CLUSTER_COVER:.0%} of the cluster, birth within {CONVERT_SESSIONS} sessions) "
        f"{pct(conv_day, len(cluster_days))}; loose (eventual members) {pct(conv_day_loose, len(cluster_days))}")
    censored_cl = 0
    for c in clin:
        # the cluster-lineage converts if ANY of its days does; lead measured from its FIRST day
        hits = [(cd["conv"], cd["lead"], cd["date"]) for cd in cluster_days if cd["lineage"] == c["id"] and cd["conv"] is not None]
        c["conv"] = None; c["lead"] = None; c["lead0"] = False
        if hits:
            # the earliest birth among the hits
            Lid = min(hits, key=lambda h: (lineages[h[0] - 1]["i0"]))[0]
            L = lineages[Lid - 1]
            c["conv"] = Lid
            c["lead"] = L["i0"] - cl_date_idx[c["first"]]
            c["lead0"] = any(h[1] == 0 and h[0] == Lid for h in hits)
            c["conv_matured"] = L["matured"]; c["conv_class"] = L["class"]
        c["conv_loose"] = any(cd["conv_loose"] is not None for cd in cluster_days if cd["lineage"] == c["id"])
        ci = cl_date_idx[c["days"][-1]]
        c["censored"] = ci is not None and ci + CONVERT_SESSIONS > last_idx
        censored_cl += c["censored"]
    conv = [c for c in clin if c["conv"] is not None]
    unc_cl = [c for c in clin if not c["censored"]]
    matured_rate = sum(L["matured"] for L in lineages) / len(lineages)
    say(f"per cluster-LINEAGE: converts {pct(len(conv), len(clin))} (loose {pct(sum(c['conv_loose'] for c in clin), len(clin))}); "
        f"uncensored only (last day + {CONVERT_SESSIONS} sessions inside the data, n={len(unc_cl)}): "
        f"{pct(sum(c['conv'] is not None for c in unc_cl), len(unc_cl))} — vs themes maturing {pct(sum(L['matured'] for L in lineages), len(lineages))}")
    leads = [c["lead"] for c in conv]
    say(f"lead = birth - first cluster day (sessions): p25/med/p75 = {qn(leads)}; lead 0 (named the SAME NIGHT the cluster was "
        f"handed to the discovery prompt — the engine naming its own seed) {pct(sum(1 for c in conv if c['lead'] == 0), len(conv))}; "
        f"1-5 sessions {sum(1 for x in leads if 1 <= x <= 5)}; 6-20 {sum(1 for x in leads if 6 <= x <= 20)}; >20 {sum(1 for x in leads if x > 20)}")
    say(f"converted clusters' themes: matured {pct(sum(bool(c.get('conv_matured')) for c in conv), len(conv))}; grind-born "
        f"{sum(1 for c in conv if c.get('conv_class') == 'grind')} / co-gap-born {sum(1 for c in conv if c.get('conv_class') == 'cogap')}")
    for lab, pred in (("size 4", lambda c: c["n"] == 4), ("size 5-8", lambda c: 5 <= c["n"] <= 8), ("size 9+", lambda c: c["n"] >= 9)):
        s = [c for c in clin if pred(c)]
        say(f"  cluster-lineages {lab:9s}: n={len(s):4d} convert {pct(sum(c['conv'] is not None for c in s), len(s))}")
    say(f"  ERA (the live engine only consumed clusters from {CLUSTER_LIVE_FROM}, commit f70bf9ab; earlier rows are a backfill it never saw; "
        f"May 2026 had 3 theme births in total):")
    for lab, pred in (("backfill (first day < 04-17)", lambda c: c["first"] < CLUSTER_LIVE_FROM),
                      ("live, 04-17..05-31", lambda c: CLUSTER_LIVE_FROM <= c["first"] <= date(2026, 5, 31)),
                      ("live, 06-01 onward", lambda c: c["first"] >= date(2026, 6, 1)),
                      ("live, 06-01 onward, uncensored", lambda c: c["first"] >= date(2026, 6, 1) and not c["censored"])):
        s = [c for c in clin if pred(c)]
        cv = [c for c in s if c["conv"] is not None]
        say(f"    {lab:32s}: n={len(s):4d} convert {pct(len(cv), len(s)):>16s}; lead 0 {sum(1 for c in cv if c['lead'] == 0)}, "
            f"lead p25/med/p75 = {qn([c['lead'] for c in cv])}; converted themes matured {pct(sum(bool(c.get('conv_matured')) for c in cv), len(cv))}")
    live = [c for c in clin if c["first"] >= date(2026, 6, 1)]
    for lab, pred in (("avg RS unknown (0)", lambda c: c["avg_rs"] == 0), ("0 < avg RS < 70", lambda c: 0 < c["avg_rs"] < 70), ("avg RS >= 70", lambda c: c["avg_rs"] >= 70)):
        s = [c for c in live if pred(c)]
        say(f"  live 06-01+ cluster-lineages {lab:18s}: n={len(s):4d} convert {pct(sum(c['conv'] is not None for c in s), len(s))}")
    bm2 = defaultdict(lambda: [0, 0])
    for c in clin:
        k = bm2[c["first"].strftime("%Y-%m")]; k[0] += 1; k[1] += c["conv"] is not None
    say("  by first-day month — cluster-lineages / converted: " + "  ".join(f"{m}: {v[0]}/{v[1]}" for m, v in sorted(bm2.items())))
    # reverse view: births preceded by a stored cluster covering >= half their founders
    say(f"\n  reverse view (from the birth side): lineages whose founders were >= {CLUSTER_COVER:.0%} inside one stored cluster in the "
        f"{IGN_BACK} sessions before birth: {pct(sum(L['ign_cl_f'] is not None and L['ign_cl_f'] <= L['i0'] for L in lineages), len(lineages))}; "
        f"among births >= 04-13: {pct(sum(L['ign_cl_f'] is not None and L['ign_cl_f'] <= L['i0'] for L in lineages if L['birth'] >= date(2026,4,13)), sum(1 for L in lineages if L['birth'] >= date(2026,4,13)))}")
    pre_cl = [L for L in lineages if L["ign_cl_f"] is not None and L["ign_cl_f"] < L["i0"]]
    say(f"  ...of which the cluster was stored STRICTLY before the birth day (a cluster the engine had in hand on an earlier night): "
        f"{len(pre_cl)}; sessions early p25/med/p75 = {qn([L['i0'] - L['ign_cl_f'] for L in pre_cl])}; matured {pct(sum(L['matured'] for L in pre_cl), len(pre_cl))}")

    # ---- write ---------------------------------------------------------------------------
    with open(OUT_LIN, "w") as fh:
        w = csv.writer(fh, delimiter="\t")
        cols = ["id", "birth", "birth_name", "class", "matured", "era", "n_members", "n_founders", "n_ep", "n_pre", "n_post",
                "n_cov", "n_hoc", "runway", "delivered", "share_all", "censored", "rwo_runway", "rwo_delivered", "rw40_runway",
                "rw40_delivered", "rwa_n_ep", "rwa_runway", "rwa_delivered", "ign_rs", "ign_cl", "ign_ep", "ign_epo", "first_leg", "lag", "cl_max_share", "cl_days"]
        w.writerow(cols)
        for L in lineages:
            r = L["rw"]
            ses = lambda i: (cal[i].isoformat() if i is not None else "")  # noqa: E731
            f3 = lambda x: ("" if x is None else f"{x:.3f}")  # noqa: E731
            w.writerow([L["id"], L["birth"], L["birth_name"], L["class"], L["matured"], L["era"], len(L["members"]), len(L["founders"]),
                        r["n_ep"], r["n_pre"], r["n_post"], r["n_cov"], r["n_hoc"], f3(r["runway"]), f3(r["delivered"]), f3(r["share_all"]),
                        r["censored"], f3(L["rwo"]["runway"]), f3(L["rwo"]["delivered"]), f3(L["rw40"]["runway"]), f3(L["rw40"]["delivered"]),
                        L["rwa"]["n_ep"], f3(L["rwa"]["runway"]), f3(L["rwa"]["delivered"]),
                        ses(L["ign_rs"]), ses(L["ign_cl"]), ses(L["ign_ep"]), ses(L["ign_epo"]), L["first_leg"],
                        "" if L["lag"] is None else L["lag"], f3(L["cl_max_share"]), L["cl_days"]])
    with open(OUT_MEM, "w") as fh:
        w = csv.writer(fh, delimiter="\t")
        cols = ["lineage", "ticker", "class", "founder", "first_join", "ep_class", "ep_date", "covered", "lag"]
        w.writerow(cols)
        for r in member_rows:
            w.writerow([r["lineage"], r["ticker"], r["class"], r["founder"], r["first_join"], r["ep_class"],
                        cal[r["ep_idx"]] if r["ep_idx"] is not None else "", "" if r["covered"] is None else r["covered"],
                        "" if r["lag"] is None else r["lag"]])
    with open(OUT_CL, "w") as fh:
        w = csv.writer(fh, delimiter="\t")
        w.writerow(["cluster_lineage", "first_day", "n_days", "size", "mean_corr", "avg_rs", "first_tickers", "converted_to", "lead", "lead0", "conv_loose", "censored"])
        for c in clin:
            w.writerow([c["id"], c["first"], len(c["days"]), c["n"], c["corr"], c["avg_rs"], "|".join(sorted(c["first_tickers"])),
                        "" if c["conv"] is None else c["conv"], "" if c["lead"] is None else c["lead"], c["lead0"], c["conv_loose"], c["censored"]])
    with open(OUT_TXT, "w") as fh:
        fh.write("\n".join(LOG) + "\n")
    print(f"\nwrote {OUT_TXT}\n      {OUT_LIN}\n      {OUT_MEM}\n      {OUT_CL}")


if __name__ == "__main__":
    main()
