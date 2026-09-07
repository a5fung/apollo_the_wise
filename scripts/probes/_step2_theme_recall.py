#!/usr/bin/env python3
"""Step 2 (RECALL) of the theme-correctness programme — are the themeless EP alerts blind
spots of the theme engine, or was the market genuinely themeless around them?

READ-ONLY, $0, idempotent. Runs entirely on frozen prod exports captured ONCE on
2026-09-07 (scripts/probes/_step2_*.tsv + the step-1 exports it reuses — psql unaligned,
tab-separated, two preamble lines before the header). Touches no strategy / entry / exit /
sizing / safeguard / grade / alert / trade code. Never calls an LLM or a paid API. No engine
involvement anywhere: every read is as of alert_date - 1, from raw closes + RS snapshots.

Plan: ~/.claude/plans/plan-this-out-with-hidden-bentley.md §2 (+ §"HIS POINT — reflexive",
§"HIS SECOND POINT — SUBTLE RS"). Findings doc: docs/analysis/step2_theme_recall_2026-09-07.md.
Step-1 helpers are REUSED, not rewritten: Prices (calendar, open-gap read, the new down-day
hold leg), Scores (weekly-snapshot mirrors of db.get_rs_velocity / db.get_rs_turners), loaders
and the engine constants — all imported from scripts/probes/_step1_theme_precision.py.

The bar — RULED BY THE OPERATOR 2026-09-07, not re-opened here:
  G1 (subtle strength among industry peers) IS the recall bar. G2 (residual correlation
  >= 0.85) is NOT — it is retained ONLY as a membership check and is not computed here.

What it computes, per (ticker, date), as of date - 1:
  PEERS   = other names with the same mi_ticker_overrides.industry (sector fallback via
            mi_stock_scores.sector when the subject has no industry — reported on its own
            line, never blended; coverage stated before any cohort number).
  LEGS    = per peer: rising (get_rs_velocity row predicate), turning (get_rs_turners
            predicate), holding up (NEW leg: median of (name - SPY) daily return on the SPY-
            down sessions of the 20 sessions ending date - 1, > 0 = held up better).
  G1      = >= 3 peers with any subtle leg.        LEVEL = >= 3 peers with RS >= 70.
  GRIND   = >= 3 subtly-strong peers that did NOT gap (open/prev close - 1 >= MIN_GAP_PCT)
            in the 20 sessions ending date - 1.     CO-GAP = G1 but not GRIND.
  G3      = >= 2 other same-industry names in mi_ep_scan_log the SAME day (same-day co-gap).
  STRICT  = the engine's actual top-30 velocity / top-30 turner pools instead of the row
            predicate (the cap, not the criterion, may be the blind spot).
Grind and co-gap are reported SEPARATELY everywhere. A blended number is a failed analysis.

Populations:
  ALERTS   = mi_theme_axis_shadow (592 rows, 2026-03-24 -> 2026-09-04: every scored HIGH/
             MODERATE survivor the shadow captured; HIGH-only before 2026-07-13). Themeless
             is RECOMPUTED here from mi_themes with one uniform anchor (date - 1) and
             compared to the stored flag; four denominators are stated.
  CONTROLS = the sub-bar names — every mi_ep_scan_log (scan_date, ticker) whose LAST state
             that day is a reject stage past the gap floor (the same population step 4's
             recorder writes: db.UNSCORED_THEME_AXIS_REJECT_STAGES, legacy filter_reason
             mapped by theme_axis_shadow.effective_reject_stage; universe_floor / gap_floor /
             duplicate excluded). Derived here read-only from the raw log because the
             recorder + backfill await deploy. `--control-source shadow` reads the recorder's
             own rows once they exist and diffs them against this derivation.
  LABELS   = the operator's 31 labelled themeless-winner rows (22 yes / 9 no) — agreement is
             REPORTED, never tuned to.

Pre-declared bars (fixed in the plan before this ran):
  grind(themeless alerts) - grind(themeless controls) >= 15 pts AND grind >= 30%  -> BLIND
  grind < 10%                                                                    -> THEMELESS
  10-30%, or margin < 15 pts                                                     -> NO VERDICT
  co-gap large but grind small                              -> themes are DOWNSTREAM of EPs

Run:  python3 scripts/probes/_step2_theme_recall.py [--control-source scanlog|shadow]
Out:  scripts/probes/_step2_theme_recall_out.txt (+ _rows.tsv, one row per subject)
"""
from __future__ import annotations

import csv
import functools
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
from agents.market_intelligence.db import UNSCORED_THEME_AXIS_REJECT_STAGES  # noqa: E402
from agents.market_intelligence.theme_axis_shadow import effective_reject_stage  # noqa: E402

OUT_TXT = os.path.join(HERE, "_step2_theme_recall_out.txt")
OUT_ROWS = os.path.join(HERE, "_step2_theme_recall_rows.tsv")

MIN_PEERS = 3                   # G1: ">= 3 industry peers" (plan §2) — the operator's bar
LEVEL_RS = s1.ASSIGN_POOL_RS_FLOOR   # 70 — the plain level cut reported alongside G1
GAP_PCT = s1.MIN_GAP_PCT             # 9.0 — _MIN_GAP_PCT_DEFAULT, the uniform open-gap read
WINDOW = s1.WINDOW                   # 20 sessions
SAME_DAY_COGAP_MIN = 2               # G3: ">= 2 other scan-log names same day, same industry"
POOL_LIMIT = 30                      # theme_engine.py:1272 — both pools are top-30
SCAN_LOG_START = s1.SCAN_LOG_START   # 2026-04-13
CONTROL_EXPECTED = 2708              # the backfill's own ticker-day count (task brief)
LABEL_STRATUM = "themeless_winner"

LOG: list[str] = []


def say(s: str = "") -> None:
    LOG.append(s)
    print(s)


def pct(n: int, d: int) -> str:
    return s1.pct(n, d)


def rate(n: int, d: int) -> float:
    return 100.0 * n / d if d else float("nan")


def load2(name: str) -> list[dict]:
    """A _step2_<name>.tsv export (same psql shape as step 1's loader)."""
    with open(os.path.join(HERE, f"_step2_{name}.tsv")) as fh:
        lines = fh.read().splitlines()
    rows = list(csv.DictReader(lines[2:], delimiter="\t"))
    first = list(rows[0].keys())[0] if rows else None
    return [r for r in rows if not (first and r[first].startswith("("))]


def era(d: date) -> str:
    """Scan-log / cutline eras (plan §Known traps). Tags only — never a cut."""
    if d < SCAN_LOG_START:
        return "E0 <04-13 (no scan log)"
    if d <= date(2026, 5, 31):
        return "E1 04-13..05-31 (floor 8%)"
    if d <= date(2026, 7, 31):
        return "E2 06-01..07-31 (floor 10%)"
    if d <= date(2026, 8, 21):
        return "E3 08-01..08-21 (floor 9%, 5% capture)"
    return "E4 08-22+ (cutline change)"


# ---------------------------------------------------------------------------------------
# Themes — the as-of read, mirroring db.get_theme_heat_asof's predicate exactly:
#   ticker = ANY(tickers) AND stage != 'Retired' AND theme_date <= anchor
#   AND (recency IS NULL OR theme_date >= anchor - recency)
#   ORDER BY theme_date DESC, score DESC NULLS LAST LIMIT 1
# Anchor = date - 1 for EVERY subject (bounded_backfill_anchor(date, same_day_write=True)):
# the theme_date = D row is written ~17:07 ET on D, so on the morning of the alert the newest
# row that existed is date - 1. One anchor for alerts AND controls, so the two are like-for-like.
# ---------------------------------------------------------------------------------------
class Themes:
    def __init__(self, rows: list[dict]):
        self.by_ticker: dict[str, list] = defaultdict(list)
        self.first_row: dict[str, date] = {}       # name -> first snapshot date (birth)
        for r in rows:
            d = s1.d_(r["theme_date"])
            self.first_row[r["name"]] = min(self.first_row.get(r["name"], d), d)
            if r["stage"] == "Retired" or not r["tickers"]:
                continue
            sc = s1.fl(r["score"])
            key = (d, sc if sc is not None else -1.0)
            for t in r["tickers"].split(","):
                self.by_ticker[t].append((key, r["name"], r["stage"]))
        for t in self.by_ticker:
            self.by_ticker[t].sort(key=lambda x: x[0], reverse=True)

    def heat(self, ticker: str, anchor: date, recency: int | None = None):
        for (d, _sc), name, stage in self.by_ticker.get(ticker, []):
            if d > anchor:
                continue
            if recency is not None and d < anchor - timedelta(days=recency):
                return None
            return name, stage
        return None


# ---------------------------------------------------------------------------------------
# Scan log — dedup to the LAST state per (scan_date, ticker), the canonical collapse
# (ORDER BY scan_time_et DESC NULLS LAST, id DESC), then stage via the SHIPPED classifier.
# ---------------------------------------------------------------------------------------
def build_scan(rows: list[dict]):
    last: dict[tuple, tuple] = {}
    for r in rows:
        key = (s1.d_(r["scan_date"]), r["ticker"])
        st = r["scan_time_et"] or ""
        order = (st != "", st, int(r["id"]))        # non-NULL time first, latest, then id
        if key not in last or order > last[key][0]:
            last[key] = (order, r)
    final = {}
    for key, (_o, r) in last.items():
        stage = effective_reject_stage(r["reject_stage"] or None, r["filter_reason"] or None)
        final[key] = {"stage": stage, "filter_reason": r["filter_reason"],
                      "gap": s1.fl(r["gap_pct"]), "ep_score": s1.fl(r["ep_score"]),
                      "tier": r["score_tier"]}
    return final


# ---------------------------------------------------------------------------------------
# The measure — one (ticker, date) -> peer counts, as of date - 1. All caches keyed so a
# peer measured for many same-day subjects is computed once.
# ---------------------------------------------------------------------------------------
class Measurer:
    def __init__(self, prices: s1.Prices, scores: s1.Scores, overrides: list[dict],
                 scan_final: dict):
        self.p, self.s = prices, scores
        self.s.weekly = functools.lru_cache(maxsize=None)(self.s.weekly)  # memoize (hot path)
        self.industry: dict[str, str] = {}
        self.sector_ovr: dict[str, str] = {}
        self.ind_members: dict[str, set] = defaultdict(set)
        self.sec_members_ovr: dict[str, set] = defaultdict(set)
        for r in overrides:
            if r["industry"]:
                self.industry[r["ticker"]] = r["industry"]
                self.ind_members[r["industry"]].add(r["ticker"])
            if r["sector"]:
                self.sector_ovr[r["ticker"]] = r["sector"]
                self.sec_members_ovr[r["sector"]].add(r["ticker"])
        # same-day scan-log names past the gap floor (any stage except the pre-floor ones)
        self.scan_day: dict[date, set] = defaultdict(set)
        for (d, t), f in scan_final.items():
            if f["stage"] not in ("universe_floor", "gap_floor"):
                self.scan_day[d].add(t)
        self._legs: dict = {}
        self._hold: dict = {}
        self._gapw: dict = {}
        self._gapd: dict = {}
        self._pools: dict = {}
        self._sec_scores: dict = {}

    # -- per-peer primitives -------------------------------------------------------------
    def legs(self, t: str, asof: date) -> dict:
        k = (t, asof)
        if k not in self._legs:
            self._legs[k] = self.s.legs(t, asof)
        return self._legs[k]

    def hold(self, t: str, i_date: int):
        k = (t, i_date)
        if k not in self._hold:
            self._hold[k] = self.p.down_day_hold(t, i_date)
        return self._hold[k]

    def gapped_window(self, t: str, i_date: int) -> bool:
        k = (t, i_date)
        if k not in self._gapw:
            lo = max(1, i_date - WINDOW)
            self._gapw[k] = bool(self.p.open_gap_sessions(t, lo, i_date - 1, GAP_PCT))
        return self._gapw[k]

    def gapped_day(self, t: str, i_date: int) -> bool:
        k = (t, i_date)
        if k not in self._gapd:
            self._gapd[k] = bool(self.p.open_gap_sessions(t, i_date, i_date, GAP_PCT))
        return self._gapd[k]

    def pools(self, asof: date) -> tuple[set, set]:
        """The engine's ACTUAL nightly pools (top-30 velocity, top-30 turners) as of `asof`."""
        d0 = self.s.resolve(asof)
        if d0 not in self._pools:
            vel, turn = self.s.pools(asof)
            self._pools[d0] = ({x[0] for x in vel[:POOL_LIMIT]}, {x[0] for x in turn[:POOL_LIMIT]})
        return self._pools[d0]

    def sector_peers(self, t: str, asof: date):
        """Sector fallback: mi_stock_scores.sector as of `asof` (top-300-by-rank rows only),
        else the overrides sector. Peers = overrides names in that sector + scored names
        carrying it that day."""
        d0 = self.s.resolve(asof)
        sec = (self.s.sector[d0].get(t) if d0 else None) or self.sector_ovr.get(t)
        if not sec:
            return None, set()
        if d0 not in self._sec_scores:
            m = defaultdict(set)
            for tk, sc in self.s.sector[d0].items():
                m[sc].add(tk)
            self._sec_scores[d0] = m
        peers = (self.sec_members_ovr.get(sec, set()) | self._sec_scores[d0].get(sec, set())) - {t}
        return sec, peers

    # -- the measure -----------------------------------------------------------------------
    def measure(self, t: str, d: date) -> dict:
        i_date = self.p.session_on_or_before(d)
        asof = d - timedelta(days=1)
        out = {"ticker": t, "date": d, "asof": asof, "src": "none", "group": "",
               "n_peers": 0, "n_data": 0, "n_strong": 0, "n_strong_nogap": 0, "n_strong_gap": 0,
               "n_rt": 0, "n_rt_nogap": 0, "n_hold": 0, "n_hold_nogap": 0,
               "n_level": 0, "n_level_nogap": 0, "n_strict": 0, "n_strict_nogap": 0,
               "n_gap_day": 0, "n_scan_day": 0, "hold_med": None, "subject_rs": None,
               "sess_ok": i_date is not None and i_date >= WINDOW + 1}
        if not out["sess_ok"]:
            return out
        ind = self.industry.get(t)
        if ind:
            out["src"], out["group"] = "industry", ind
            peers = self.ind_members[ind] - {t}
        else:
            sec, peers = self.sector_peers(t, asof)
            if sec:
                out["src"], out["group"] = "sector", sec
        out["n_peers"] = len(peers)
        out["subject_rs"] = self.legs(t, asof)["rs"]
        vel_pool, turn_pool = self.pools(asof)
        scan_others = self.scan_day.get(d, set()) - {t}
        holds = []
        for p in sorted(peers):
            L = self.legs(p, asof)
            h = self.hold(p, i_date)
            has = L["rs"] is not None or h is not None
            if not has:
                continue
            out["n_data"] += 1
            if h is not None:
                holds.append(h)
            rt = L["vel_q"] or L["turn_q"]
            hq = h is not None and h > 0
            strong = rt or hq
            level = L["rs"] is not None and L["rs"] >= LEVEL_RS
            strict = p in vel_pool or p in turn_pool
            gw = self.gapped_window(p, i_date)
            out["n_strong"] += strong
            out["n_strong_nogap"] += strong and not gw
            out["n_strong_gap"] += strong and gw
            out["n_rt"] += rt
            out["n_rt_nogap"] += rt and not gw
            out["n_hold"] += hq
            out["n_hold_nogap"] += hq and not gw
            out["n_level"] += level
            out["n_level_nogap"] += level and not gw
            out["n_strict"] += strict
            out["n_strict_nogap"] += strict and not gw
            out["n_gap_day"] += self.gapped_day(p, i_date)
            if p in scan_others and (ind and self.industry.get(p) == ind):
                out["n_scan_day"] += 1
        out["hold_med"] = float(np.median(holds)) if holds else None
        return out


def flags(m: dict) -> dict:
    """The decisions, from the counts. Class order: grind > co-gap > none."""
    covered = m["src"] == "industry"
    computable = covered and m["n_data"] >= MIN_PEERS
    g1 = m["n_strong"] >= MIN_PEERS
    grind = m["n_strong_nogap"] >= MIN_PEERS
    g3 = m["n_scan_day"] >= SAME_DAY_COGAP_MIN
    cogap = (g1 and not grind) or (g3 and not grind)
    return {
        "covered": covered, "computable": computable,
        "g1": g1, "grind": grind, "cogap_w": g1 and not grind, "g3": g3, "cogap": cogap,
        "gapday": m["n_gap_day"] >= SAME_DAY_COGAP_MIN,
        "cls": "grind" if grind else ("co-gap" if cogap else "none"),
        "level": m["n_level"] >= MIN_PEERS, "level_grind": m["n_level_nogap"] >= MIN_PEERS,
        "rt": m["n_rt"] >= MIN_PEERS, "rt_grind": m["n_rt_nogap"] >= MIN_PEERS,
        "hold": m["n_hold"] >= MIN_PEERS,
        "strict": m["n_strict"] >= MIN_PEERS, "strict_grind": m["n_strict_nogap"] >= MIN_PEERS,
    }


def size_bucket(n: int) -> str:
    return "<10" if n < 10 else ("10-30" if n <= 30 else ">30")


# ---------------------------------------------------------------------------------------
# Aggregation / printing
# ---------------------------------------------------------------------------------------
def panel(label: str, subjects: list[dict], show_hidden: bool = True) -> dict:
    """One block of rates for a subject list. Denominator for the headline rates =
    INDUSTRY-COVERED subjects (uncomputable ones counted as 'no', and listed); a second
    line gives the same rates over computable subjects only."""
    n_all = len(subjects)
    cov = [s for s in subjects if s["f"]["covered"]]
    comp = [s for s in cov if s["f"]["computable"]]
    sec = [s for s in subjects if s["m"]["src"] == "sector"]
    none_ = [s for s in subjects if s["m"]["src"] == "none"]
    res = {"n": n_all, "covered": len(cov), "computable": len(comp)}

    def c(key, pool):
        return sum(1 for s in pool if s["f"][key])

    say(f"--- {label}: n={n_all} · industry-covered {pct(len(cov), n_all)} · "
        f"computable (>=3 data-bearing peers) {pct(len(comp), n_all)} · "
        f"sector-fallback-only {len(sec)} · no group {len(none_)}")
    if not cov:
        say("    (no covered subjects)")
        return res
    for key, name in (("g1", "G1 subtle >=3 peers"), ("grind", "  GRIND (>=3 strong, no gap in window)"),
                      ("cogap_w", "  CO-GAP via window-gapped peers"), ("g3", "  G3 same-day co-gap (scan log, >=2)"),
                      ("gapday", "  same-day co-gap, uniform open-gap read (>=2)"),
                      ("cogap", "  CO-GAP class (window or same-day, not grind)"),
                      ("level", "LEVEL RS>=70 >=3 peers"), ("level_grind", "  LEVEL-grind (no gap)"),
                      ("rt", "rising/turning only >=3"), ("rt_grind", "  rising/turning-grind"),
                      ("hold", "hold-up leg only >=3"),
                      ("strict", "STRICT: in engine top-30 pools >=3"), ("strict_grind", "  STRICT-grind")):
        res[key] = (c(key, cov), len(cov), c(key, comp), len(comp))
        say(f"    {name:<48} {pct(c(key, cov), len(cov)):>18}   | computable-only {pct(c(key, comp), len(comp))}")
    cls = Counter(s["f"]["cls"] for s in cov)
    say(f"    class (covered): grind {cls['grind']} · co-gap {cls['co-gap']} · none {cls['none']}")
    if sec:
        g1s = sum(1 for s in sec if s["f"]["g1"]); grs = sum(1 for s in sec if s["f"]["grind"])
        say(f"    sector-fallback line (NOT blended): n={len(sec)} · G1 {pct(g1s, len(sec))} · grind {pct(grs, len(sec))}")
    if show_hidden:
        by_b = defaultdict(list)
        for s in cov:
            by_b[size_bucket(s["m"]["n_data"])].append(s)
        say("    by peer-group size (data-bearing peers): " + " · ".join(
            f"{b}: n={len(v)} G1 {rate(c('g1', v), len(v)):.0f}% grind {rate(c('grind', v), len(v)):.0f}% "
            f"hold-only {rate(c('hold', v), len(v)):.0f}%" for b, v in sorted(by_b.items(), key=lambda kv: ("<10", "10-30", ">30").index(kv[0]))))
    return res


def two_by_two(label: str, rows: list[dict], key: str) -> None:
    yy = sum(1 for r in rows if r["label"] == "y" and r["f"][key])
    yn = sum(1 for r in rows if r["label"] == "y" and not r["f"][key])
    ny = sum(1 for r in rows if r["label"] == "n" and r["f"][key])
    nn = sum(1 for r in rows if r["label"] == "n" and not r["f"][key])
    agree = yy + nn
    say(f"    {label:<40} his Y: fires {yy} / silent {yn}   his N: fires {ny} / silent {nn}   "
        f"agreement {pct(agree, len(rows))}")


def main() -> None:
    control_source = "scanlog"
    if "--control-source" in sys.argv:
        control_source = sys.argv[sys.argv.index("--control-source") + 1]

    say("=== STEP 2 RECALL probe — frozen prod exports of 2026-09-07 (read-only, $0) ===")
    say(f"constants: MIN_PEERS={MIN_PEERS} LEVEL_RS={LEVEL_RS} GAP_PCT={GAP_PCT} WINDOW={WINDOW} "
        f"POOL_LIMIT={POOL_LIMIT} THEME_RS_MIN={s1.THEME_RS_MIN} "
        f"control stages={sorted(UNSCORED_THEME_AXIS_REJECT_STAGES)}")

    # ---- load ------------------------------------------------------------------------
    shadow = load2("shadow")
    alerts_tbl = load2("alerts")
    overrides = load2("overrides")
    scan_raw = load2("scan")
    closes = load2("closes")
    scores_rows = s1.load("scores_all")
    themes_rows = s1.load("themes")
    cohort = s1.load("cohort")
    say(f"loaded: shadow {len(shadow)} · mi_ep_alerts {len(alerts_tbl)} · overrides {len(overrides)} · "
        f"scan-log rows {len(scan_raw)} · closes {len(closes)} · scores {len(scores_rows)} · "
        f"themes {len(themes_rows)} · label cohort {len(cohort)}")

    prices = s1.Prices(closes)
    scores = s1.Scores(scores_rows)
    themes = Themes(themes_rows)
    scan_final = build_scan(scan_raw)
    M = Measurer(prices, scores, overrides, scan_final)
    say(f"calendar: {prices.cal[0]} -> {prices.cal[-1]} ({len(prices.cal)} sessions) · "
        f"tickers with closes {len(prices.close)} · RS snapshot dates {len(scores.all_dates)}")

    # ---- coverage, stated BEFORE any cohort number --------------------------------------
    say("\n## 0. Coverage (mi_ticker_overrides.industry) — stated before any cohort number")
    n_ovr = len(overrides); n_ind = sum(1 for r in overrides if r["industry"])
    say(f"  overrides rows {n_ovr}, with industry {pct(n_ind, n_ovr)}, industries {len(M.ind_members)}, "
        f"sectors {len(M.sec_members_ovr)}")
    sizes = sorted(len(v) for v in M.ind_members.values())
    say(f"  industry size (overrides members): median {statistics.median(sizes):.0f} · p90 "
        f"{sizes[int(0.9 * len(sizes)) - 1]} · max {max(sizes)}")
    sh_t = {r["ticker"] for r in shadow}
    ctl_t = {t for (d, t), f in scan_final.items() if f["stage"] in UNSCORED_THEME_AXIS_REJECT_STAGES}
    say(f"  alert tickers with industry: {pct(sum(1 for t in sh_t if t in M.industry), len(sh_t))}")
    say(f"  control tickers with industry: {pct(sum(1 for t in ctl_t if t in M.industry), len(ctl_t))}"
        "   <- NOT a random half: a name is in overrides because something looked it up")

    # ---- alerts: denominators ----------------------------------------------------------
    say("\n## 1. The alert population and its four themeless denominators")
    anchor = lambda d: d - timedelta(days=1)  # noqa: E731
    A = []
    for r in shadow:
        d = s1.d_(r["alert_date"]); t = r["ticker"]
        h = themes.heat(t, anchor(d)); h7 = themes.heat(t, anchor(d), recency=6)
        A.append({"ticker": t, "date": d, "grade": r["grade"], "stored_themeless": r["themeless_flag"] == "t",
                  "stored_theme": r["theme_name"], "stored_7d": r["theme_name_7d"],
                  "same_day_write": r["same_day_write"] == "t",
                  "themeless": h is None, "theme": h[0] if h else None,
                  "themeless_7d": h7 is None, "active_7d": bool(h7 and h7[1] in ("Accelerating", "Mainstream")),
                  "era": era(d), "pop": "alert"})
    n = len(A)
    stored_tl = sum(1 for a in A if a["stored_themeless"])
    rec_tl = sum(1 for a in A if a["themeless"])
    tl7 = sum(1 for a in A if a["themeless_7d"])
    nact = sum(1 for a in A if not a["active_7d"])
    say(f"  D1 stored themeless_flag (unbounded, as written): {pct(stored_tl, n)}")
    say(f"  D1' RECOMPUTED unbounded, anchor date-1 (used below): {pct(rec_tl, n)}")
    say(f"  D2 7d-bounded any-stage themeless (anchor date-1, recency 6): {pct(tl7, n)}")
    say(f"  D3 not in an Accelerating/Mainstream theme within 7d (= live in_active_theme definition): {pct(nact, n)}")
    ia_true = sum(1 for r in alerts_tbl if r["in_active_theme"] == "t")
    ia_nonnull = sum(1 for r in alerts_tbl if r["in_active_theme"] in ("t", "f"))
    say(f"  D4 mi_ep_alerts.in_active_theme = TRUE: {pct(ia_true, len(alerts_tbl))} of all rows; "
        f"{pct(ia_true, ia_nonnull)} of non-NULL rows -> live flag themeless {100 - rate(ia_true, len(alerts_tbl)):.1f}% / "
        f"{100 - rate(ia_true, ia_nonnull):.1f}%")
    dis = [a for a in A if a["stored_themeless"] != a["themeless"]]
    say(f"  stored vs recomputed disagree: {len(dis)} of {n}")
    for a in dis:
        born = themes.first_row.get(a["stored_theme"] or a["theme"] or "", None)
        say(f"    {a['ticker']} {a['date']} stored_themeless={a['stored_themeless']} recomputed={a['themeless']} "
            f"stored_theme={a['stored_theme']!r} recomputed_theme={a['theme']!r} same_day_write={a['same_day_write']} "
            f"theme_first_row={born}")
    sh_keys = {(a["ticker"], a["date"]) for a in A}
    al_keys = {(r["ticker"], s1.d_(r["alert_date"])) for r in alerts_tbl}
    say(f"  shadow rows not in mi_ep_alerts: {len(sh_keys - al_keys)} (of which before 2026-05-08: "
        f"{sum(1 for k in sh_keys - al_keys if k[1] < date(2026, 5, 8))}) · mi_ep_alerts rows not in shadow: {len(al_keys - sh_keys)}")
    say("  by era (alerts / recomputed themeless): " + " · ".join(
        f"{e}: {sum(1 for a in A if a['era'] == e)}/{sum(1 for a in A if a['era'] == e and a['themeless'])}"
        for e in sorted({a["era"] for a in A})))
    say("  by grade: " + " · ".join(f"{g}: {c}" for g, c in sorted(Counter(a["grade"] for a in A).items())))

    # ---- controls ------------------------------------------------------------------------
    say("\n## 2. The control population — sub-bar names from mi_ep_scan_log (probe's own derivation)")
    stage_counts = Counter(f["stage"] or ("ALERT-final" if not f["filter_reason"] else "UNMATCHED") for f in scan_final.values())
    say(f"  scan-log rows {len(scan_raw)} -> last state per (date, ticker) {len(scan_final)}; final stages: "
        + " · ".join(f"{k} {v}" for k, v in stage_counts.most_common()))
    unmatched = [k for k, f in scan_final.items() if f["stage"] is None and f["filter_reason"]]
    say(f"  UNMATCHED tail (filter_reason no pattern): {len(unmatched)}" + (f"  e.g. {unmatched[:3]}" if unmatched else ""))
    C = []
    for (d, t), f in sorted(scan_final.items()):
        if f["stage"] not in UNSCORED_THEME_AXIS_REJECT_STAGES:
            continue
        h = themes.heat(t, anchor(d)); h7 = themes.heat(t, anchor(d), recency=6)
        C.append({"ticker": t, "date": d, "grade": None, "stage": f["stage"], "gap": f["gap"],
                  "themeless": h is None, "theme": h[0] if h else None,
                  "themeless_7d": h7 is None, "active_7d": bool(h7 and h7[1] in ("Accelerating", "Mainstream")),
                  "era": era(d), "pop": "control"})
    say(f"  control ticker-days: {len(C)} (backfill's own count {CONTROL_EXPECTED}; "
        f"{'MATCH' if len(C) == CONTROL_EXPECTED else 'DIFFERS by ' + str(len(C) - CONTROL_EXPECTED)}) · "
        f"{C[0]['date'] if C else '-'} -> {C[-1]['date'] if C else '-'} · distinct tickers {len({c['ticker'] for c in C})}")
    say("  by stage: " + " · ".join(f"{k} {v}" for k, v in Counter(c["stage"] for c in C).most_common()))
    say(f"  control themeless (recomputed, anchor date-1): {pct(sum(1 for c in C if c['themeless']), len(C))}; "
        f"7d-themeless {pct(sum(1 for c in C if c['themeless_7d']), len(C))}")
    ovl = [c for c in C if (c["ticker"], c["date"]) in sh_keys or (c["ticker"], c["date"]) in al_keys]
    say(f"  control rows that are ALSO an alert row (shadow or mi_ep_alerts): {len(ovl)} — a name scored HIGH at one "
        f"scan whose LAST scan-log state that day is a reject; the recorder's ON CONFLICT DO NOTHING would skip these. "
        "By stage: " + " · ".join(f"{k} {v}" for k, v in Counter(c["stage"] for c in ovl).most_common()))
    C = [c for c in C if not ((c["ticker"], c["date"]) in sh_keys or (c["ticker"], c["date"]) in al_keys)]
    say(f"  PURE control (never alerted that day, used below): {len(C)} ticker-days · themeless "
        f"{pct(sum(1 for c in C if c['themeless']), len(C))}")
    # what the scan log's LAST state says about the alert rows themselves
    st_of_alert = Counter()
    for a in A:
        if a["date"] < SCAN_LOG_START:
            continue
        f = scan_final.get((a["date"], a["ticker"]))   # scan_final is keyed (date, ticker)
        st_of_alert[(f["stage"] or ("ALERT-final" if not f["filter_reason"] else "UNMATCHED")) if f else "not in scan log"] += 1
    say("  scan-log LAST state of the shadow alert rows (>=04-13): " + " · ".join(f"{k} {v}" for k, v in st_of_alert.most_common()))
    al_src = {(r["ticker"], s1.d_(r["alert_date"])): r["source"] for r in alerts_tbl}
    nolog = [a for a in A if a["date"] >= SCAN_LOG_START and (a["date"], a["ticker"]) not in scan_final]
    say(f"  the {len(nolog)} alert rows with NO scan-log row: mi_ep_alerts source = "
        + " · ".join(f"{k} {v}" for k, v in Counter(al_src.get((a["ticker"], a["date"]), "not in mi_ep_alerts") for a in nolog).most_common())
        + f" · dates {min(a['date'] for a in nolog) if nolog else '-'} -> {max(a['date'] for a in nolog) if nolog else '-'}"
        + " · by month " + " · ".join(f"{k} {v}" for k, v in sorted(Counter(a["date"].strftime("%Y-%m") for a in nolog).items())))

    if control_source == "shadow":
        say("\n  [--control-source shadow] diff the deployed recorder's rows against this derivation")
        path = os.path.join(HERE, "_step2_shadow_unscored.tsv")
        if not os.path.exists(path):
            say(f"  {path} missing. Produce it ONCE with:\n"
                "    ssh apollo@87.99.134.162 'docker exec -i apollo-postgres psql -U apollo -d apollo -f -' "
                "< scripts/probes/_step2_x_shadow_unscored.sql > scripts/probes/_step2_shadow_unscored.tsv")
        else:
            rec = load2("shadow_unscored")
            rk = {(r["ticker"], s1.d_(r["alert_date"])): r for r in rec}
            ck = {(c["ticker"], c["date"]): c for c in C}
            only_rec, only_der = set(rk) - set(ck), set(ck) - set(rk)
            both = set(rk) & set(ck)
            fl_dis = [k for k in both if (rk[k]["themeless_flag"] == "t") != ck[k]["themeless"]]
            st_dis = [k for k in both if rk[k]["reject_stage"] != ck[k]["stage"]]
            say(f"  recorder rows {len(rk)} · derived {len(ck)} · both {len(both)} · recorder-only {len(only_rec)} · "
                f"derived-only {len(only_der)} · themeless disagree {len(fl_dis)} · stage disagree {len(st_dis)}")
            for k in sorted(only_rec)[:10]:
                say(f"    recorder-only {k}")
            for k in sorted(only_der)[:10]:
                say(f"    derived-only {k}")
            for k in sorted(fl_dis)[:10]:
                say(f"    themeless disagree {k}: recorder {rk[k]['themeless_flag']} derived {ck[k]['themeless']}")

    # ---- measure everything ------------------------------------------------------------
    say("\n## 3. Measuring G1 as of date-1 for every subject (this takes a minute)")
    subjects = A + C
    for s in subjects:
        s["m"] = M.measure(s["ticker"], s["date"])
        s["f"] = flags(s["m"])
    say(f"  measured {len(subjects)} subjects · legs cache {len(M._legs)} · hold cache {len(M._hold)}")
    say("\n## 3b. Peer-level base rates — why an absolute '>= 3 peers' bar saturates (arithmetic, not market)")
    n_ev = has_rs = lvl = ris = tur = 0
    for (t, asof), L in M._legs.items():
        n_ev += 1
        if L["rs"] is not None:
            has_rs += 1; lvl += L["rs"] >= LEVEL_RS; ris += L["vel_q"]; tur += L["turn_q"]
    hp = [h for h in M._hold.values() if h is not None]
    say(f"  peer-evaluations {n_ev}: with an RS row {pct(has_rs, n_ev)} · RS>=70 | has RS {pct(lvl, has_rs)} · "
        f"rising {pct(ris, has_rs)} · turning {pct(tur, has_rs)} · hold computable {len(hp)} · hold>0 {pct(sum(1 for h in hp if h > 0), len(hp))}")
    rs_all = [float(r["rs_composite"]) for r in scores_rows if r["rs_composite"]]
    say(f"  mi_stock_scores keeps {len(rs_all) / max(1, len(scores.all_dates)):.0f} rows/day of a ~9,700 universe; "
        f"RS>=70 among KEPT rows {pct(sum(1 for x in rs_all if x >= LEVEL_RS), len(rs_all))} (a percentile that would read 30% "
        "on the full universe) -> every RS-based leg is measured on a pre-selected strong pool")
    say("  with ~30 data-bearing peers and ~40% of names 'holding up' on any given day, P(>=3 strong) is ~1 by arithmetic; "
        "the by-size buckets in §4 show it directly. The bar is NOT moved here — this is reported as the instrument's meaning.")

    # ---- the headline: themeless alerts vs themeless controls, era >= scan-log start ----
    say("\n## 4. THE HEADLINE — themeless alerts (D1', >= 2026-04-13) vs themeless controls")
    TA = [s for s in A if s["themeless"] and s["date"] >= SCAN_LOG_START]
    TC = [s for s in C if s["themeless"]]
    ra = panel("THEMELESS ALERTS (recomputed unbounded, >=04-13)", TA)
    rc = panel("THEMELESS CONTROLS (sub-bar, recomputed unbounded)", TC)
    rall = panel("ALL CONTROLS (themed + themeless)", C, show_hidden=False)
    say("")
    ga, gc = rate(*ra["grind"][:2]), rate(*rc["grind"][:2])
    ga_c, gc_c = rate(*ra["grind"][2:]), rate(*rc["grind"][2:])
    say(f"  grind rate, covered denominators: alerts {ga:.1f}% ({ra['grind'][0]} of {ra['grind'][1]}) vs controls "
        f"{gc:.1f}% ({rc['grind'][0]} of {rc['grind'][1]}) -> margin {ga - gc:+.1f} pts")
    say(f"  grind rate, computable-only:      alerts {ga_c:.1f}% ({ra['grind'][2]} of {ra['grind'][3]}) vs controls "
        f"{gc_c:.1f}% ({rc['grind'][2]} of {rc['grind'][3]}) -> margin {ga_c - gc_c:+.1f} pts")
    ca, cc = rate(*ra["cogap"][:2]), rate(*rc["cogap"][:2])
    say(f"  co-gap class: alerts {ca:.1f}% vs controls {cc:.1f}% -> margin {ca - cc:+.1f} pts")
    la, lc = rate(*ra["level"][:2]), rate(*rc["level"][:2])
    say(f"  LEVEL RS>=70 cut: alerts {la:.1f}% vs controls {lc:.1f}%; G1 - LEVEL gap on alerts "
        f"{rate(*ra['g1'][:2]) - la:+.1f} pts (what a level gate misses)")

    def verdict(g, margin):
        if g >= 30 and margin >= 15:
            return "BAR CROSSED: the engine is blind — fix recall"
        if g < 10:
            return "BAR CROSSED: the themeless names are genuinely themeless"
        return "NO VERDICT from the number alone (10-30%, or margin < 15 pts)"
    say(f"  PRE-DECLARED BAR (covered denominators): {verdict(ga, ga - gc)}")
    say(f"  PRE-DECLARED BAR (computable-only):      {verdict(ga_c, ga_c - gc_c)}")
    if ca > ga and ga < 30:
        say("  co-gap class larger than grind -> the reflexive reading (themes downstream of EPs) applies")

    # ---- variants of the alert denominator --------------------------------------------
    say("\n## 5. Same read on the other alert denominators (full window incl. pre-04-13)")
    panel("ALL 592 shadow alerts", A, show_hidden=False)
    panel("THEMED alerts (recomputed unbounded) — the engine DID name these", [s for s in A if not s["themeless"]], show_hidden=False)
    panel("7d-THEMELESS alerts (D2)", [s for s in A if s["themeless_7d"]], show_hidden=False)
    panel("NOT-ACTIVE alerts (D3, no Accelerating/Mainstream within 7d)", [s for s in A if not s["active_7d"]], show_hidden=False)

    # ---- era + stage cuts --------------------------------------------------------------
    say("\n## 6. Era and reject-stage cuts (tags, never cuts — the floors moved 8 -> 10 -> 9/5, cutline 08-22)")
    for e in sorted({s["era"] for s in subjects}):
        ea = [s for s in TA if s["era"] == e]; ec = [s for s in TC if s["era"] == e]
        ca_ = [s for s in ea if s["f"]["covered"]]; cc_ = [s for s in ec if s["f"]["covered"]]
        say(f"  {e:<40} themeless alerts n={len(ca_):>3} G1 {rate(sum(1 for s in ca_ if s['f']['g1']), len(ca_)):5.1f}% grind "
            f"{rate(sum(1 for s in ca_ if s['f']['grind']), len(ca_)):5.1f}%   | themeless controls n={len(cc_):>4} G1 "
            f"{rate(sum(1 for s in cc_ if s['f']['g1']), len(cc_)):5.1f}% grind {rate(sum(1 for s in cc_ if s['f']['grind']), len(cc_)):5.1f}%")
    say("  controls by reject stage (themeless, covered):")
    for st, _ in Counter(s["stage"] for s in TC).most_common():
        v = [s for s in TC if s["stage"] == st and s["f"]["covered"]]
        say(f"    {st:<18} n={len(v):>4} G1 {rate(sum(1 for s in v if s['f']['g1']), len(v)):5.1f}% grind "
            f"{rate(sum(1 for s in v if s['f']['grind']), len(v)):5.1f}% co-gap {rate(sum(1 for s in v if s['f']['cogap']), len(v)):5.1f}%")

    # ---- validation on the 31 labels -----------------------------------------------------
    say("\n## 7. Validation — the operator's 31 labelled themeless-winner rows (22 yes / 9 no). Reported, never tuned.")
    labels = [r for r in cohort if r["stratum"] == LABEL_STRATUM and r["operator_label"] in ("y", "n")]
    LR = []
    for r in labels:
        t, d = r["ticker"], s1.d_(r["alert_date"])
        m = M.measure(t, d)
        LR.append({"ticker": t, "date": d, "label": r["operator_label"], "note": r["operator_note"], "m": m, "f": flags(m)})
    cov_l = [x for x in LR if x["f"]["covered"]]
    say(f"  labelled rows {len(LR)} (y {sum(1 for x in LR if x['label'] == 'y')} / n {sum(1 for x in LR if x['label'] == 'n')}) · "
        f"industry-covered {len(cov_l)} · uncovered: {[x['ticker'] for x in LR if not x['f']['covered']]}")
    two_by_two("G1 subtle (any leg)", cov_l, "g1")
    two_by_two("G1 GRIND", cov_l, "grind")
    two_by_two("CO-GAP class", cov_l, "cogap")
    two_by_two("LEVEL RS>=70", cov_l, "level")
    two_by_two("rising/turning only", cov_l, "rt")
    two_by_two("STRICT top-30 pools", cov_l, "strict")
    say("  per row (ticker date label | industry | data peers | strong/nogap/gapped | level | same-day scan | class | his note):")
    for x in LR:
        m, f = x["m"], x["f"]
        say(f"    {x['ticker']:<5} {x['date']} {x['label']} | {m['group'][:34]:<34} | {m['n_data']:>3} | "
            f"{m['n_strong']:>2}/{m['n_strong_nogap']:>2}/{m['n_strong_gap']:>2} | {m['n_level']:>2} | {m['n_scan_day']:>2} | "
            f"{f['cls']:<6} | {x['note'][:40]}")
    say("  limits: those 31 were SELECTED on forward 5-day return >= +5% (an upper bound on a good day, not a recall "
        "rate; returns are ruled out of this work); his notes are SECTOR-level, G1 is peer-level.")

    # ---- what carries G1 ----------------------------------------------------------------
    say("\n## 8. What carries G1 — leg composition and the by-construction risk in big industries")
    for label, pool in (("themeless alerts", [s for s in TA if s["f"]["covered"]]),
                        ("themeless controls", [s for s in TC if s["f"]["covered"]])):
        g1 = [s for s in pool if s["f"]["g1"]]
        only_hold = sum(1 for s in g1 if not s["f"]["rt"])
        med_data = statistics.median(s["m"]["n_data"] for s in pool) if pool else float("nan")
        med_hold = statistics.median(s["m"]["hold_med"] for s in pool if s["m"]["hold_med"] is not None) if pool else float("nan")
        say(f"  {label}: G1 fires {len(g1)} of {len(pool)}; of those, {only_hold} fire ONLY through the hold-up leg "
            f"(rising/turning < 3); median data-bearing peers {med_data:.0f}; median peer hold-up {med_hold * 100:+.2f}%/down day")
        top = Counter(s["m"]["group"] for s in g1).most_common(6)
        say("    G1 industries: " + " · ".join(f"{g} {c}" for g, c in top))
        topg = Counter(s["m"]["group"] for s in pool if s["f"]["grind"]).most_common(6)
        say("    GRIND industries: " + " · ".join(f"{g} {c}" for g, c in topg))

    say("\n## 8b. Threshold-free read — SHARE of data-bearing peers that are subtly strong and did not gap (no bar invented)")
    def q(xs):
        xs = sorted(xs)
        if not xs:
            return "n/a"
        f = lambda p: xs[min(len(xs) - 1, int(p * len(xs)))]  # noqa: E731
        return f"p25 {100 * f(0.25):.0f}% · median {100 * f(0.5):.0f}% · p75 {100 * f(0.75):.0f}% (n={len(xs)})"
    for label, pool in (("themeless alerts (>=04-13)", TA), ("themeless PURE controls", TC),
                        ("THEMED alerts (engine named them)", [s for s in A if not s["themeless"]]),
                        ("his 22 YES labels", [x for x in LR if x["label"] == "y"]),
                        ("his 9 NO labels", [x for x in LR if x["label"] == "n"])):
        cov_ = [s for s in pool if s["f"]["computable"]]
        sh_strong = [s["m"]["n_strong_nogap"] / s["m"]["n_data"] for s in cov_]
        sh_rt = [s["m"]["n_rt_nogap"] / s["m"]["n_data"] for s in cov_]
        sh_lvl = [s["m"]["n_level_nogap"] / s["m"]["n_data"] for s in cov_]
        sh_gap_of_strong = [s["m"]["n_strong_gap"] / s["m"]["n_strong"] for s in cov_ if s["m"]["n_strong"] > 0]
        sh_gapday = [s["m"]["n_gap_day"] / s["m"]["n_data"] for s in cov_]
        say(f"  {label:<36} strong&no-gap share: {q(sh_strong)}")
        say(f"  {'':<36} rising/turning&no-gap: {q(sh_rt)}")
        say(f"  {'':<36} RS>=70&no-gap:         {q(sh_lvl)}")
        say(f"  {'':<36} REFLEXIVITY — share of STRONG peers that gapped >=9% in the window: {q(sh_gap_of_strong)}")
        say(f"  {'':<36} share of data-bearing peers gapping ON the day (open-gap): {q(sh_gapday)}")

    # ---- rows out ------------------------------------------------------------------------
    cols = ["pop", "ticker", "date", "grade", "stage", "era", "themeless", "themeless_7d", "active_7d", "theme",
            "src", "group", "n_peers", "n_data", "n_strong", "n_strong_nogap", "n_strong_gap", "n_rt", "n_hold",
            "n_level", "n_level_nogap", "n_strict", "n_strict_nogap", "n_gap_day", "n_scan_day", "hold_med",
            "subject_rs", "g1", "grind", "cogap", "g3", "cls", "level", "strict"]
    with open(OUT_ROWS, "w", newline="") as fh:
        w = csv.writer(fh, delimiter="\t")
        w.writerow(cols)
        for s in subjects + [{**x, "pop": "label:" + x["label"], "grade": None, "stage": None, "era": era(x["date"]),
                              "themeless": True, "themeless_7d": True, "active_7d": False, "theme": None} for x in LR]:
            row = []
            for c in cols:
                v = s.get(c, s["m"].get(c, s["f"].get(c, "")))
                row.append(f"{v:.4f}" if isinstance(v, float) else v)
            w.writerow(row)
    with open(OUT_TXT, "w") as fh:
        fh.write("\n".join(LOG) + "\n")
    print(f"\nwrote {OUT_TXT}\n      {OUT_ROWS}")


if __name__ == "__main__":
    main()
