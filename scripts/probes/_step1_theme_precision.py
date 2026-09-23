#!/usr/bin/env python3
"""Step 1 (PRECISION) of the theme-correctness programme — when the engine names a
theme, is it real, judged ONLY on relative strength + price coherence (never returns)?

READ-ONLY, $0, idempotent. Runs entirely on frozen prod exports captured ONCE on
2026-09-07 (scripts/probes/_step1_*.tsv — psql unaligned, tab-separated, two preamble
lines before the header). Touches no strategy / entry / exit / sizing / safeguard /
grade / alert / trade code. Never calls an LLM or a paid API.

Plan: ~/.claude/plans/plan-this-out-with-hidden-bentley.md §1. Findings doc:
docs/analysis/step1_theme_precision_2026-09-07.md.

What it computes, in order:
  1. LINEAGES — dedupe the 513 mi_themes names into lineages using the ENGINE'S OWN
     identity rules only: mi_theme_renames (2 rows) + the tombstone "renamed to" note +
     theme_renamed_on_mass_flag audit rows + `_get_theme_history`'s Jaccard >= 0.4
     fallback (newborn founders vs any other name's most recent row in the prior 10 days).
     The #534 rebirth rule (>=50% of a newborn's founders came from a lineage that died
     <=14 days earlier) is kept as a DIRECTED LINK between lineages, not a union — merging
     it at dedup time would empty the "reborn" class by construction. Both counts reported.
  2. BIRTH CLASS — co-gap vs grind. Co-gap = >=2 founders gapped >= MIN_GAP_PCT in the
     20 sessions up to and including birth day; grind = 0 or 1. Primary source is
     mi_ep_scan_log where the whole window is covered (scan log starts 2026-04-13 and is
     floor-censored by era), otherwise the uniform open-gap from mi_daily_closes
     (open / prior close - 1). Agreement of the two classifiers is reported on the overlap.
  3. COHERENCE — mean pairwise SPY-residual correlation of the founders over the 20
     sessions ending birth-1 (pre) and the 20 sessions after birth (post), computed by
     correlation_engine._compute_residual_correlations (NO correlation maths written
     here). Bar = the engine's own _MEAN_CORR_MIN. The engine helper returns nothing
     below _MIN_CLUSTER_SIZE (4) founders; the NATIVE panel keeps that floor, the RELAXED
     panel lowers the instrument floor to 2 IN THIS PROCESS ONLY so 2-3 founder births can
     be read. The engine constant is never touched.
  4. SUBTLE RS (operator scope addition 2026-09-07) — per founder at birth: rising
     (mirror of db.get_rs_velocity), turning (mirror of db.get_rs_turners), holding up on
     SPY down days (NEW: median of (name - SPY) daily return on the SPY-down sessions in
     the 20 sessions before the date). Reported ALONGSIDE the plain RS >= 70 level cut.
  5. NON-MATURER SPLIT — absorbed / reborn / killed-healthy / dissolved (+ the buckets
     the task left undefined, reported rather than forced).
  6. OPERATOR-LABEL AGREEMENT — the 58 decided `themed` labels: cohort coherence and the
     ticker's own fit to its cohort, Y vs N. Reported, never tuned.
  7. FUNNEL CHECK — velocity/turner pool names with RS < ASSIGN_POOL_RS_FLOOR: do they
     ever reach a theme? Count only; no constant changed.

Run:  python3 scripts/probes/_step1_theme_precision.py
Out:  scripts/probes/_step1_theme_precision_out.txt (+ _lineages.tsv, _founders.tsv)
"""
from __future__ import annotations

import csv
import json
import os
import re
import statistics
import sys
from collections import Counter, defaultdict
from datetime import date, timedelta

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.join(HERE, "..", "..")
sys.path.insert(0, ROOT)

import agents.market_intelligence.correlation_engine as ce  # noqa: E402  (pure numpy at import)

OUT_TXT = os.path.join(HERE, "_step1_theme_precision_out.txt")
OUT_LIN = os.path.join(HERE, "_step1_theme_precision_lineages.tsv")
OUT_FND = os.path.join(HERE, "_step1_theme_precision_founders.tsv")

# ---------------------------------------------------------------------------------------
# Engine constants — read from the SOURCE FILES at runtime so nothing is hand-mirrored.
# theme_engine / ep_detector cannot be imported here (they drag DB + broker config).
# ---------------------------------------------------------------------------------------
def _const(path: str, name: str, default: float) -> float:
    try:
        src = open(os.path.join(ROOT, path)).read()
        m = re.search(rf"^{re.escape(name)}\s*=\s*([0-9.]+)", src, re.M)
        return float(m.group(1)) if m else default
    except OSError:
        return default


ASSIGN_POOL_RS_FLOOR = _const("agents/market_intelligence/theme_engine.py", "ASSIGN_POOL_RS_FLOOR", 70.0)
THEME_RS_MIN = _const("agents/market_intelligence/theme_engine.py", "THEME_RS_MIN", 50.0)
PROMOTE_MIN_MEMBERS = _const("agents/market_intelligence/theme_engine.py", "_PROMOTE_MIN_MEMBERS", 3)
MIN_GAP_PCT = _const("agents/market_intelligence/ep_detector.py", "_MIN_GAP_PCT_DEFAULT", 9.0)
MEAN_CORR_MIN = ce._MEAN_CORR_MIN            # 0.80 — the bar
NATIVE_MIN_CLUSTER = ce._MIN_CLUSTER_SIZE    # 4 — the instrument floor
RELAXED_MIN_CLUSTER = 2
DISSOLVED_RS = 50.0                          # task definition: "member RS fell under 50"
JACCARD_SAME_THEME = 0.4                     # _get_theme_history fallback
HISTORY_DAYS = 10                            # _get_theme_history default `days`
REBIRTH_OVERLAP = 0.5                        # #534 rebirth rule (share of newborn founders)
REBIRTH_DAYS = 14
ACTIVE_RECENCY_DAYS = 7                      # get_active_themes(stale_after_days=7)
SCAN_LOG_START = date(2026, 4, 13)           # first mi_ep_scan_log row (verified on prod)
WINDOW = 20                                  # sessions of returns (21 closes), as the engine
# mi_theme_renames — 2 rows on prod (_step1_theme_precision_shape_out.txt), both 2026-09-04.
RENAMES = [
    ("Pure-Play Agricultural Tractor & Farm Machinery Manufacturers", "Global Agriculture Value Chain Recovery"),
    ("U.S. Downstream Refining & Marketing", "Global Oil & Gas Upstream, Integrated & Transport Value Chain"),
]

LOG: list[str] = []


def say(s: str = "") -> None:
    LOG.append(s)
    print(s)


def pct(n: int, d: int) -> str:
    return f"{n}/{d} = {100.0 * n / d:.1f}%" if d else f"{n}/0 = n/a"


def med(xs) -> str:
    xs = [x for x in xs if x is not None and not (isinstance(x, float) and np.isnan(x))]
    return f"{statistics.median(xs):.3f}" if xs else "n/a"


# ---------------------------------------------------------------------------------------
# Loaders — psql unaligned output: 2 preamble lines, then a tab header. Footer disabled.
# ---------------------------------------------------------------------------------------
def load(name: str) -> list[dict]:
    with open(os.path.join(HERE, f"_step1_{name}.tsv")) as fh:
        lines = fh.read().splitlines()
    rows = list(csv.DictReader(lines[2:], delimiter="\t"))
    first = list(rows[0].keys())[0] if rows else None
    return [r for r in rows if not (first and r[first].startswith("("))]


def d_(s: str) -> date:
    return date.fromisoformat(s[:10])


def fl(s: str):
    return float(s) if s not in ("", None) else None


# ---------------------------------------------------------------------------------------
# Prices: calendar from SPY, per-ticker arrays aligned to the calendar.
# ---------------------------------------------------------------------------------------
class Prices:
    def __init__(self, rows: list[dict]):
        spy = sorted(d_(r["trade_date"]) for r in rows if r["ticker"] == "SPY")
        self.cal = spy
        self.idx = {d: i for i, d in enumerate(spy)}
        n = len(spy)
        self.close: dict[str, np.ndarray] = {}
        self.open: dict[str, np.ndarray] = {}
        for r in rows:
            t = r["ticker"]
            i = self.idx.get(d_(r["trade_date"]))
            if i is None:
                continue
            if t not in self.close:
                self.close[t] = np.full(n, np.nan)
                self.open[t] = np.full(n, np.nan)
            self.close[t][i] = float(r["close"])
            self.open[t][i] = fl(r["open_price"]) if r["open_price"] else np.nan

    def session_on_or_before(self, d: date) -> int | None:
        """Index of the latest session <= d (theme_date is an engine run date; holidays fall back)."""
        i = self.idx.get(d)
        if i is not None:
            return i
        lo = [j for j, dd in enumerate(self.cal) if dd <= d]
        return lo[-1] if lo else None

    def returns_block(self, tickers: list[str], start: int):
        """21 closes from `start` -> 20 returns per ticker, exactly as _compute_tight_clusters_sync.
        Drops tickers lacking any of the 21 closes (the engine's full-coverage rule)."""
        end = start + WINDOW + 1
        if start < 0 or end > len(self.cal):
            return None
        spy = self.close["SPY"][start:end]
        r_spy = spy[1:] / spy[:-1] - 1.0
        kept, mats = [], []
        for t in tickers:
            c = self.close.get(t)
            if c is None:
                continue
            seg = c[start:end]
            if np.isnan(seg).any():
                continue
            kept.append(t)
            mats.append(seg[1:] / seg[:-1] - 1.0)
        return (np.array(mats) if mats else np.empty((0, WINDOW))), r_spy, kept

    def open_gap_sessions(self, t: str, lo: int, hi: int, floor_pct: float) -> list[int]:
        """Sessions s in [lo, hi] where open(s)/close(s-1) - 1 >= floor (uniform gap read)."""
        c, o = self.close.get(t), self.open.get(t)
        if c is None or lo < 1:
            return []
        out = []
        for s in range(lo, hi + 1):
            if not np.isnan(o[s]) and not np.isnan(c[s - 1]) and c[s - 1] > 0:
                if (o[s] / c[s - 1] - 1.0) * 100.0 >= floor_pct:
                    out.append(s)
        return out

    def down_day_hold(self, t: str, i: int):
        """NEW measure (operator 2026-09-07): over the 20 sessions BEFORE session i, on the
        sessions SPY fell, median of (name's return - SPY's return). Positive = held up
        better. None if fewer than 3 SPY-down sessions or missing closes."""
        blk = self.returns_block([t], i - WINDOW - 1)
        if blk is None or not blk[2]:
            return None
        r, r_spy = blk[0][0], blk[1]
        down = r_spy < 0
        if down.sum() < 3:
            return None
        return float(np.median((r - r_spy)[down]))


def coherence(prices: Prices, tickers: list[str], start: int, relaxed: bool):
    """Mean pairwise SPY-residual correlation via the ENGINE'S helper. Returns
    (mean_corr, n_used, n_input, corr_matrix, kept_tickers) or None when the block is
    outside the data or the helper returns empty (below its cluster-size floor)."""
    blk = prices.returns_block(tickers, start)
    if blk is None:
        return None
    r_mat, r_spy, kept = blk
    if len(kept) < 2:
        return None
    saved = ce._MIN_CLUSTER_SIZE
    try:
        if relaxed:
            ce._MIN_CLUSTER_SIZE = RELAXED_MIN_CLUSTER   # instrument floor for THIS read only
        corr, used = ce._compute_residual_correlations(r_mat, r_spy, list(kept))
    finally:
        ce._MIN_CLUSTER_SIZE = saved
    if corr.size == 0 or len(used) < 2:
        return None
    iu = np.triu_indices(len(used), k=1)
    vals = corr[iu]
    if np.isnan(vals).all():
        return None
    return float(np.nanmean(vals)), len(used), len(tickers), corr, used


# ---------------------------------------------------------------------------------------
# RS: weekly-snapshot mirrors of db.get_rs_velocity / db.get_rs_turners (same SQL logic).
# ---------------------------------------------------------------------------------------
class Scores:
    def __init__(self, rows: list[dict]):
        self.rs: dict[date, dict[str, float]] = defaultdict(dict)
        self.sector: dict[date, dict[str, str]] = defaultdict(dict)
        for r in rows:
            if r["rs_composite"] == "":
                continue
            d = d_(r["score_date"])
            self.rs[d][r["ticker"]] = float(r["rs_composite"])
            if r["sector"]:
                self.sector[d][r["ticker"]] = r["sector"]
        self.all_dates = sorted(self.rs)
        self.counts = [(d, len(self.rs[d])) for d in self.all_dates]
        self._resolve_cache: dict[date, date | None] = {}

    def resolve(self, d: date) -> date | None:
        """db._resolve_score_date -> _pick_latest_complete_score_date: newest score_date <= d
        whose row count >= 50% of the median count over the 10 newest dates <= d (#554)."""
        if d in self._resolve_cache:
            return self._resolve_cache[d]
        counts = [(dd, n) for dd, n in reversed(self.counts) if dd <= d][:40]
        out = None
        if counts:
            recent = sorted(n for _, n in counts[:10]); mid = len(recent) // 2
            median = recent[mid] if len(recent) % 2 else (recent[mid - 1] + recent[mid]) / 2
            out = next((dd for dd, n in counts if n >= 0.5 * median), None)
        self._resolve_cache[d] = out
        return out

    def weekly(self, d0: date) -> list[date | None]:
        """db._resolve_weekly_snapshots: nearest score_date (ANY populated date, as the engine's
        DISTINCT query) within ±2 days of d0-7k; ties resolve to the earlier date here."""
        out = []
        for k in range(5):
            t = d0 - timedelta(days=7 * k)
            best, bd = None, 999
            for sd in self.all_dates:
                dist = abs((sd - t).days)
                if dist <= 2 and dist < bd:
                    best, bd = sd, dist
            out.append(best)
        return out

    def legs(self, t: str, d: date) -> dict:
        """Per-ticker subtle-RS legs as of d. Mirrors get_rs_velocity / get_rs_turners
        row-level predicates (pool LIMITs are applied separately in the funnel check)."""
        d0 = self.resolve(d)
        res = {"rs": None, "vel_q": False, "vel_score": None, "turn_q": False, "level": False}
        if d0 is None:
            return res
        w = self.weekly(d0)
        g = lambda dd: (self.rs[dd].get(t) if dd else None)  # noqa: E731
        now, r7, r14, r21, r28 = g(w[0]), g(w[1]), g(w[2]), g(w[3]), g(w[4])
        res["rs"] = now
        if now is None:
            return res
        res["level"] = now >= ASSIGN_POOL_RS_FLOOR
        if w[1] is None:            # _prepare_weekly_snapshots returns None without d7
            return res
        sub = lambda a, b: (a - b) if (a is not None and b is not None) else None  # noqa: E731
        v1, v2, v3, v4 = sub(now, r7), sub(r7, r14), sub(r14, r21), sub(r21, r28)
        weeks = sum(x is not None for x in (r7, r14, r21, r28))
        score = 0.40 * (v1 or 0) + 0.30 * (v2 or 0) + 0.20 * (v3 or 0) + 0.10 * (v4 or 0)
        bonus = (v1 is not None and v1 > 0
                 and (v2 is None or v2 > 0) and (v3 is None or v3 > 0) and (v4 is None or v4 > 0)
                 and sum(1 for x in (v2, v3, v4) if x is not None and x > 0) >= 1)
        score *= 1.2 if bonus else 1.0
        res["vel_score"] = score
        res["vel_q"] = (now >= THEME_RS_MIN and weeks >= 2 and score > 0 and v1 is not None and v1 > 0)
        # turners: sector required (only top-300-by-rank rows carry one — a real restriction)
        sector = self.sector[w[0]].get(t)
        earliest = next((x for x in (r28, r21, r14, r7) if x is not None), None)
        gt = lambda a, b: (a is not None and b is not None and a > b)  # noqa: E731
        c1 = gt(now, r7)
        c2 = c1 and gt(r7, r14)
        c3 = c2 and gt(r14, r21)
        c4 = c3 and gt(r21, r28)
        consec = int(c1) + int(c2) + int(c3) + int(c4)
        res["turn_q"] = (sector is not None and earliest is not None and earliest <= 30.0
                         and consec >= 3 and now > earliest + 10)
        res["consec"] = consec
        res["earliest"] = earliest
        return res

    def pools(self, d: date) -> tuple[list[tuple[str, float]], list[tuple[str, int, float]]]:
        """The engine's velocity (top 30 by velocity_score, min_rs=THEME_RS_MIN) and turner
        (top 30) pools for run date d — reconstructed from the universe export."""
        d0 = self.resolve(d)
        if d0 is None:
            return [], []
        vel, turn = [], []
        for t in self.rs[d0]:
            L = self.legs(t, d)
            if L["vel_q"]:
                vel.append((t, L["vel_score"], L["rs"]))
            if L["turn_q"]:
                turn.append((t, L["consec"], L["rs"] - L["earliest"], L["rs"]))
        vel.sort(key=lambda x: -x[1])
        turn.sort(key=lambda x: (-x[1], -x[2]))
        return vel[:30], turn[:30]


# ---------------------------------------------------------------------------------------
# Themes → names → lineages
# ---------------------------------------------------------------------------------------
class Name:
    def __init__(self, name: str):
        self.name = name
        self.rows: list[dict] = []

    def finalize(self):
        self.rows.sort(key=lambda r: (r["date"], r["id"]))
        member = [r for r in self.rows if r["tickers"]]
        self.first = member[0] if member else None
        self.first_is_retired = bool(self.first and self.first["stage"] == "Retired")
        live = [r for r in self.rows if r["tickers"] and r["stage"] != "Retired"]
        self.last_live = live[-1] if live else None
        self.stages = {r["stage"] for r in self.rows}
        self.tombs = [r for r in self.rows if r["stage"] == "Retired"]
        self.last_row = self.rows[-1]


class UF:
    def __init__(self):
        self.p: dict[str, str] = {}

    def find(self, x):
        self.p.setdefault(x, x)
        while self.p[x] != x:
            self.p[x] = self.p[self.p[x]]
            x = self.p[x]
        return x

    def union(self, a, b):
        ra, rb = self.find(a), self.find(b)
        if ra != rb:
            self.p[rb] = ra


def jaccard(a: set, b: set) -> float:
    return len(a & b) / len(a | b) if (a | b) else 0.0


def main() -> None:
    say("=== STEP 1 PRECISION probe — frozen prod exports of 2026-09-07 ===")
    say(f"constants read from source: ASSIGN_POOL_RS_FLOOR={ASSIGN_POOL_RS_FLOOR} THEME_RS_MIN={THEME_RS_MIN} "
        f"_PROMOTE_MIN_MEMBERS={PROMOTE_MIN_MEMBERS:g} MIN_GAP_PCT={MIN_GAP_PCT} _MEAN_CORR_MIN={MEAN_CORR_MIN} "
        f"_MIN_CLUSTER_SIZE={NATIVE_MIN_CLUSTER} (relaxed panel uses {RELAXED_MIN_CLUSTER})")

    themes_raw = load("themes")
    scan_raw = load("scan")
    closes_raw = load("closes")
    scores_raw = load("scores_all")
    audit = load("audit") + load("audit2") + load("audit3")
    cohort = load("cohort")
    prices = Prices(closes_raw)
    scores = Scores(scores_raw)
    max_date = max(d_(r["theme_date"]) for r in themes_raw)
    say(f"mi_themes rows={len(themes_raw)} names={len({r['name'] for r in themes_raw})} "
        f"span {min(d_(r['theme_date']) for r in themes_raw)}..{max_date}; "
        f"sessions in price calendar={len(prices.cal)} ({prices.cal[0]}..{prices.cal[-1]}); "
        f"score dates populated={len(scores.all_dates)}")

    # ---- names -------------------------------------------------------------------------
    names: dict[str, Name] = {}
    for r in themes_raw:
        n = names.setdefault(r["name"], Name(r["name"]))
        n.rows.append({
            "id": int(r["id"]), "date": d_(r["theme_date"]), "stage": r["stage"],
            "tickers": [t for t in r["tickers"].split(",") if t] if r["tickers"] else [],
            "rs_avg": fl(r["rs_avg"]), "parent": r["parent_theme"] or None,
            "note": r["retired_note"], "source": r["source"],
        })
    for n in names.values():
        n.finalize()
    tomb_first = [n.name for n in names.values() if n.first_is_retired]
    say(f"names whose FIRST member row is a Retired tombstone (not births): {len(tomb_first)}")

    # ---- lineage union (engine identity rules only) -------------------------------------
    uf = UF()
    e_rename = e_note = e_mass = e_jac = 0
    for old, new in RENAMES:
        if old in names and new in names:
            uf.union(old, new); e_rename += 1
    for n in names.values():
        for t in n.tombs:
            m = re.search(r"renamed to '([^']+)'", t["note"] or "")
            if m and m.group(1) in names:
                uf.union(n.name, m.group(1)); e_note += 1
    for r in audit:
        if r["event_type"] == "theme_renamed_on_mass_flag":
            m = re.search(r"^'([^']+)' renamed to '([^']+)'", r["summary"])
            if m and m.group(1) in names and m.group(2) in names:
                uf.union(m.group(1), m.group(2)); e_mass += 1
    # Jaccard >= 0.4 fallback — newborn founders vs other names' most recent row in prior 10 days
    by_date: dict[date, list[tuple[str, list[str]]]] = defaultdict(list)
    for n in names.values():
        for r in n.rows:
            if r["tickers"]:
                by_date[r["date"]].append((n.name, r["tickers"]))
    jac_links = []
    for n in names.values():
        if not n.first or n.first_is_retired:
            continue
        d0, F = n.first["date"], set(n.first["tickers"])
        recent: dict[str, list[str]] = {}
        for k in range(1, HISTORY_DAYS + 1):
            for nm, tk in by_date.get(d0 - timedelta(days=k), []):
                if nm != n.name and nm not in recent:
                    recent[nm] = tk           # most recent row wins (DESC order)
        best, bj = None, 0.0
        for nm, tk in recent.items():
            j = jaccard(F, set(tk))
            if j > bj:
                best, bj = nm, j
        if best and bj >= JACCARD_SAME_THEME:
            uf.union(best, n.name); e_jac += 1
            jac_links.append((n.name, best, bj, n.first["stage"]))
    born_non_nascent = [n.name for n in names.values() if n.first and not n.first_is_retired
                        and n.first["stage"] != "Nascent"]
    attached = sum(1 for nm in born_non_nascent if any(l[0] == nm for l in jac_links))
    say(f"lineage edges: rename-table={e_rename} tombstone-note={e_note} mass-flag-audit={e_mass} "
        f"jaccard>=0.4-in-10d={e_jac}")
    say(f"names born wearing a non-Nascent stage (inherited history): {len(born_non_nascent)}; "
        f"of which the Jaccard rule attaches to a prior name: {attached} — the rest are "
        f"same-name revivals or inherited from a name >10d back")

    groups: dict[str, list[str]] = defaultdict(list)
    for nm in names:
        groups[uf.find(nm)].append(nm)

    # ---- lineage objects ---------------------------------------------------------------
    lineages = []
    for root, members in groups.items():
        objs = [names[m] for m in members]
        births = [o for o in objs if o.first and not o.first_is_retired]
        if not births:
            continue
        b = min(births, key=lambda o: (o.first["date"], o.first["id"]))
        L = {
            "id": None, "root": root, "names": sorted(members), "birth_name": b.name,
            "birth": b.first["date"], "founders": list(b.first["tickers"]),
            "birth_source": b.first["source"], "birth_stage": b.first["stage"],
            "matured": any("Mainstream" in o.stages for o in objs),
            "accelerated": any("Accelerating" in o.stages for o in objs),
            "n_rows": sum(len(o.rows) for o in objs),
        }
        lives = [o for o in objs if o.last_live]
        if lives:
            last = max(lives, key=lambda o: (o.last_live["date"], o.last_live["id"]))
            L["death_name"], L["last_live"], L["last_members"] = last.name, last.last_live["date"], last.last_live["tickers"]
        else:
            L["death_name"], L["last_live"], L["last_members"] = b.name, b.first["date"], list(b.first["tickers"])
        last_any = max(objs, key=lambda o: (o.last_row["date"], o.last_row["id"])).last_row
        L["alive"] = (last_any["stage"] != "Retired" and (max_date - last_any["date"]).days <= ACTIVE_RECENCY_DAYS)
        L["life_days"] = (L["last_live"] - L["birth"]).days
        lineages.append(L)
    lineages.sort(key=lambda L: (L["birth"], L["birth_name"]))
    for i, L in enumerate(lineages, 1):
        L["id"] = i
    say(f"\n--- 1. LINEAGES: {len(lineages)} lineages from {len(names)} names "
        f"(engine identity rules; {sum(len(L['names']) > 1 for L in lineages)} lineages carry >1 name)")

    # ---- rebirth links (#534 rule, directed) --------------------------------------------
    by_id = {L["id"]: L for L in lineages}
    reborn_as: dict[int, int] = {}
    for L in lineages:
        if L["alive"]:
            continue
        dl, ML = L["last_live"], set(L["last_members"])
        if not ML:
            continue
        for K in lineages:
            if K["id"] == L["id"] or not (dl < K["birth"] <= dl + timedelta(days=REBIRTH_DAYS)):
                continue
            FK = set(K["founders"])
            if FK and len(FK & ML) / len(FK) >= REBIRTH_OVERLAP:
                reborn_as[L["id"]] = K["id"]
                break
    uf2 = UF()
    for a, b in reborn_as.items():
        uf2.union(a, b)
    n_collapsed = len({uf2.find(L["id"]) for L in lineages})
    say(f"rebirth links (#534: >={REBIRTH_OVERLAP:.0%} of a newborn's founders came from a lineage dead "
        f"<={REBIRTH_DAYS}d earlier): {len(reborn_as)}; lineages if those were ALSO collapsed: {n_collapsed}")

    # ---- 2. birth class ----------------------------------------------------------------
    scan_gap: dict[str, set[date]] = defaultdict(set)
    for r in scan_raw:
        g = fl(r["gap_pct"])
        if g is not None and g >= MIN_GAP_PCT:
            scan_gap[r["ticker"]].add(d_(r["scan_date"]))
    for L in lineages:
        i0 = prices.session_on_or_before(L["birth"])
        L["i0"] = i0
        lo = i0 - WINDOW
        L["scan_covered"] = lo >= 0 and prices.cal[lo] >= SCAN_LOG_START
        win_dates = set(prices.cal[max(lo, 0):i0 + 1])
        sg, og, latest_s, latest_o, same_s, same_o = [], [], None, None, 0, 0
        for t in L["founders"]:
            ds = scan_gap.get(t, set()) & win_dates
            if ds:
                sg.append(t)
                li = prices.idx[max(ds)]
                latest_s = li if latest_s is None else max(latest_s, li)
                same_s += max(ds) >= prices.cal[i0 - 1] if i0 >= 1 else False
            os_ = prices.open_gap_sessions(t, max(lo, 1), i0, MIN_GAP_PCT)
            if os_:
                og.append(t)
                latest_o = max(os_) if latest_o is None else max(latest_o, max(os_))
                same_o += max(os_) >= i0 - 1
        L["scan_gappers"], L["open_gappers"] = sg, og
        L["class_scan"] = ("cogap" if len(sg) >= 2 else "grind") if L["scan_covered"] else None
        L["class_open"] = "cogap" if len(og) >= 2 else "grind"
        L["class"] = L["class_scan"] or L["class_open"]
        L["class_src"] = "scan" if L["class_scan"] else "open"
        L["gap_recency"] = (i0 - (latest_s if L["class_src"] == "scan" else latest_o)) \
            if (latest_s if L["class_src"] == "scan" else latest_o) is not None else None
        L["same_day_gappers"] = same_s if L["class_src"] == "scan" else same_o
        L["n_gappers"] = len(sg) if L["class_src"] == "scan" else len(og)
    cov = [L for L in lineages if L["scan_covered"]]
    agree = sum(1 for L in cov if L["class_scan"] == L["class_open"])
    say(f"\n--- 2. BIRTH CLASS (co-gap = >=2 founders gapped >= {MIN_GAP_PCT:.0f}% in the {WINDOW} sessions "
        f"up to and incl. birth; grind = 0-1) ---")
    say(f"scan-log window fully covered: {pct(len(cov), len(lineages))} (scan log starts {SCAN_LOG_START}; "
        f"floors 8% Apr-May, 10% Jun-Jul, capture from 5% Aug+) — uncovered births use the open-gap read")
    say(f"scan-log vs open-gap classifier agreement on the covered subset: {pct(agree, len(cov))}")
    cc = Counter(L["class"] for L in lineages)
    say(f"PRIMARY class: grind={cc['grind']} co-gap={cc['cogap']} (of {len(lineages)})")
    cc2 = Counter(L["class_open"] for L in lineages)
    say(f"open-gap-only class (uniform, all births): grind={cc2['grind']} co-gap={cc2['cogap']}")
    say(f"grind births with EXACTLY 1 gapper (boundary): {sum(1 for L in lineages if L['class']=='grind' and L['n_gappers']==1)}")
    rec = Counter()
    for L in lineages:
        if L["class"] == "cogap":
            r = L["gap_recency"]
            rec["same day (0)" if r == 0 else "1-5 sessions" if r <= 5 else "6-10" if r <= 10 else "11-20"] += 1
    say(f"co-gap births by sessions from the LATEST founder gap to birth: {dict(rec)}")
    say(f"co-gap births with >=2 founders gapping on birth day or the day before: "
        f"{sum(1 for L in lineages if L['class']=='cogap' and L['same_day_gappers']>=2)}")
    bm = defaultdict(Counter)
    for L in lineages:
        bm[L["birth"].strftime("%Y-%m")][L["class"]] += 1
    say("by birth month (grind / co-gap): " + "  ".join(f"{m}: {c['grind']}/{c['cogap']}" for m, c in sorted(bm.items())))
    fs = Counter(min(len(L["founders"]), 8) for L in lineages)
    say(f"founder-count distribution (8=8+): {dict(sorted(fs.items()))}  — "
        f"{sum(v for k, v in fs.items() if k < NATIVE_MIN_CLUSTER)} lineages are born below the engine's "
        f"{NATIVE_MIN_CLUSTER}-member coherence-instrument floor")

    # ---- 3. coherence pre / post -------------------------------------------------------
    for L in lineages:
        i0 = L["i0"]
        for panel, relaxed in (("nat", False), ("rlx", True)):
            pre = coherence(prices, L["founders"], i0 - WINDOW - 1, relaxed)
            post = coherence(prices, L["founders"], i0, relaxed)
            L[f"pre_{panel}"] = pre[0] if pre else None
            L[f"post_{panel}"] = post[0] if post else None
            L[f"n_{panel}"] = pre[1] if pre else 0
        L["post_censored"] = i0 + WINDOW + 1 > len(prices.cal)

    def coh_table(rows, title):
        say(f"\n{title}")
        for panel, label in (("nat", f"NATIVE (>={NATIVE_MIN_CLUSTER} founders w/ full prices)"),
                             ("rlx", f"RELAXED (instrument floor {RELAXED_MIN_CLUSTER} in-process)")):
            for cls in ("grind", "cogap"):
                sub = [L for L in rows if L["class"] == cls and L[f"pre_{panel}"] is not None]
                pre_ok = sum(1 for L in sub if L[f"pre_{panel}"] >= MEAN_CORR_MIN)
                subp = [L for L in sub if L[f"post_{panel}"] is not None]
                post_ok = sum(1 for L in subp if L[f"post_{panel}"] >= MEAN_CORR_MIN)
                up = sum(1 for L in subp if L[f"post_{panel}"] > L[f"pre_{panel}"])
                say(f"  {label:48s} {cls:5s}: n={len(sub):3d}  pre median={med([L[f'pre_{panel}'] for L in sub])}  "
                    f"pre>={MEAN_CORR_MIN}: {pct(pre_ok, len(sub))}  |  post median={med([L[f'post_{panel}'] for L in subp])}  "
                    f"post>={MEAN_CORR_MIN}: {pct(post_ok, len(subp))}  post>pre: {pct(up, len(subp))}")
    coh_table(lineages, f"--- 3. COHERENCE of founders (mean pairwise SPY-residual corr, {WINDOW} sessions; bar = engine _MEAN_CORR_MIN {MEAN_CORR_MIN}) — ALL lineages ---")
    coh_table([L for L in lineages if L["matured"]], "    ...lineages that reached Mainstream")
    coh_table([L for L in lineages if not L["matured"]], "    ...lineages that never reached Mainstream")
    unread = sum(1 for L in lineages if L["pre_nat"] is None and L["pre_rlx"] is not None)
    say(f"  births the NATIVE instrument cannot read but the relaxed one can: {unread}; "
        f"unreadable in both (prices missing / window before data): {sum(1 for L in lineages if L['pre_rlx'] is None)}")
    # does the verdict differ between panels? (on births both can read)
    both = [L for L in lineages if L["pre_nat"] is not None and L["pre_rlx"] is not None]
    diff = sum(1 for L in both if (L["pre_nat"] >= MEAN_CORR_MIN) != (L["pre_rlx"] >= MEAN_CORR_MIN))
    say(f"  panels disagree on the pre-birth bar where both read: {pct(diff, len(both))} (expected 0 — same maths, floor only)")

    # ---- 4. subtle RS at birth ---------------------------------------------------------
    founder_rows = []
    for L in lineages:
        d0, i0 = L["birth"], L["i0"]
        legs = []
        for t in L["founders"]:
            Lg = scores.legs(t, d0)
            Lg["hold"] = prices.down_day_hold(t, i0)
            Lg["hold_q"] = Lg["hold"] is not None and Lg["hold"] > 0
            Lg["subtle"] = Lg["vel_q"] or Lg["turn_q"] or Lg["hold_q"]
            Lg["ticker"] = t
            legs.append(Lg)
            founder_rows.append({"lineage": L["id"], "birth": d0, "class": L["class"], "ticker": t,
                                 "rs": Lg["rs"], "level70": Lg["level"], "vel_q": Lg["vel_q"],
                                 "turn_q": Lg["turn_q"], "hold": Lg["hold"], "hold_q": Lg["hold_q"],
                                 "subtle": Lg["subtle"], "gapped": t in (L["scan_gappers"] if L["class_src"] == "scan" else L["open_gappers"])})
        n = len(legs)
        L["f_level"] = sum(x["level"] for x in legs) / n
        L["f_subtle"] = sum(x["subtle"] for x in legs) / n
        L["f_vel"] = sum(x["vel_q"] for x in legs) / n
        L["f_turn"] = sum(x["turn_q"] for x in legs) / n
        L["f_hold"] = sum(x["hold_q"] for x in legs) / n
        L["f_hold_med"] = med([x["hold"] for x in legs])
        L["rs_birth"] = med([x["rs"] for x in legs])
    say(f"\n--- 4. STRENGTH OF FOUNDERS AT BIRTH — RS level (>= {ASSIGN_POOL_RS_FLOOR:.0f}) vs SUBTLE RS "
        f"(rising = get_rs_velocity predicate · turning = get_rs_turners predicate · holding up = median (name-SPY) on SPY-down days > 0) ---")
    for cls in ("grind", "cogap"):
        fr = [f for f in founder_rows if f["class"] == cls and f["rs"] is not None]
        say(f"  {cls:5s} founders n={len(fr)}: RS>=70 {pct(sum(f['level70'] for f in fr), len(fr))} | "
            f"subtle(any leg) {pct(sum(f['subtle'] for f in fr), len(fr))} | rising {pct(sum(f['vel_q'] for f in fr), len(fr))} | "
            f"turning {pct(sum(f['turn_q'] for f in fr), len(fr))} | holding-up {pct(sum(f['hold_q'] for f in fr), len(fr))} "
            f"(median hold {med([f['hold'] for f in fr])}) | subtle but RS<70: {pct(sum(f['subtle'] and not f['level70'] for f in fr), len(fr))} "
            f"| RS>=70 but no subtle leg: {pct(sum(f['level70'] and not f['subtle'] for f in fr), len(fr))}")
        ls = [L for L in lineages if L["class"] == cls]
        say(f"  {cls:5s} lineages n={len(ls)}: >=half founders RS>=70 {pct(sum(L['f_level']>=0.5 for L in ls), len(ls))} | "
            f">=half founders subtle {pct(sum(L['f_subtle']>=0.5 for L in ls), len(ls))} | "
            f"subtle-majority but NOT level-majority: {sum(L['f_subtle']>=0.5 and L['f_level']<0.5 for L in ls)} | "
            f"level-majority but NOT subtle-majority: {sum(L['f_level']>=0.5 and L['f_subtle']<0.5 for L in ls)}")
        # gapped founders vs not, within class — the reflexivity check on the level gate
        g1 = [f for f in fr if f["gapped"]]
        g0 = [f for f in fr if not f["gapped"]]
        say(f"  {cls:5s} founders that GAPPED n={len(g1)}: RS>=70 {pct(sum(f['level70'] for f in g1), len(g1))}, "
            f"holding-up {pct(sum(f['hold_q'] for f in g1), len(g1))} · did NOT gap n={len(g0)}: RS>=70 "
            f"{pct(sum(f['level70'] for f in g0), len(g0))}, holding-up {pct(sum(f['hold_q'] for f in g0), len(g0))}")

    # ---- 5. non-maturer split ----------------------------------------------------------
    # absorption evidence from the audit log (name -> successor) — every mechanism the engine has
    lost_to: dict[str, str] = {}
    lost_mech: dict[str, str] = {}
    ps_n = ps_ok = ps_bad = 0
    for r in audit:
        ev, s, dtl = r["event_type"], r["summary"], r["detail"]
        if ev == "theme_pass1_5_absorption":
            m = re.search(r"'([^']+)' -> '([^']+)'", s)
            if m:
                lost_to.setdefault(m.group(1), m.group(2)); lost_mech.setdefault(m.group(1), ev)
        elif ev == "theme_pass1_protect_strip" and "EMPTY_AFTER_STRIP" in dtl:
            m = re.search(r"from '([^']+)' \(protect '([^']+)'\)", s)
            if m:
                stripped, kept = m.group(1), m.group(2)
                lost_to.setdefault(stripped, kept); lost_mech.setdefault(stripped, ev)
                # the engine-drop block seeds successor pointers from these rows as j=lost / i=successor
                # regardless of which side was stripped — check what tombstone was actually written that day
                D = d_(r["created_at"])
                sn, kn = names.get(stripped), names.get(kept)
                ps_n += 1
                ps_ok += bool(sn and any(t["parent"] == kept and t["date"] == D for t in sn.tombs))
                ps_bad += bool(kn and any(t["parent"] == stripped and t["date"] == D for t in kn.tombs))
        elif ev == "theme_thesis_merged":
            m = re.search(r"'([^']+)' merged into '([^']+)'", s)
            if m:
                lost_to.setdefault(m.group(1), m.group(2)); lost_mech.setdefault(m.group(1), ev)
        elif ev == "theme_auto_retired":
            for m in re.finditer(r"'([^']+)' -> parent='([^']+)'", dtl):
                if m.group(2) != "(unknown)":
                    lost_to.setdefault(m.group(1), m.group(2)); lost_mech.setdefault(m.group(1), ev)
    dissolve_audit = {re.search(r"'([^']+)'", r["summary"]).group(1) for r in audit
                      if r["event_type"] == "theme_dissolved_flagged_pair" and re.search(r"'([^']+)'", r["summary"])}
    cap_audit = set()
    for r in audit:
        if r["event_type"] == "theme_cap_drop":
            cap_audit |= set(re.findall(r"dropped '([^']+)'", r["detail"]))
        elif r["event_type"] == "theme_sector_cap_dropped":
            m = re.search(r"^'([^']+)'", r["summary"])
            if m:
                cap_audit.add(m.group(1))
    say(f"\n--- 5. NON-MATURER SPLIT ---")
    say(f"protect-strip events that emptied a theme: {ps_n}; same-day tombstone on the STRIPPED theme pointing at the kept one "
        f"(correct): {ps_ok}; same-day tombstone on the KEPT theme pointing at the stripped one (spurious): {ps_bad} — "
        f"the engine-drop block seeds successor pointers as j=lost/i=successor regardless of which side was stripped "
        f"(theme_engine.py ~7860); reported, not patched")

    for L in lineages:
        L["split"] = L["mech"] = None
        L["rs_death"] = L["subtle_death"] = L["post_death"] = None
        if L["matured"]:
            continue
        if L["alive"]:
            L["split"] = "still-live (censored)"; continue
        dn, lin_names = L["death_name"], set(L["names"])
        def _absorbed_by(nm):
            for t in names[nm].tombs:
                if t["parent"] and "absorbed/superseded" in (t["note"] or "") and t["parent"] not in lin_names:
                    return t["parent"], "tombstone:absorbed"
            if nm in lost_to and lost_to[nm] not in lin_names:
                return lost_to[nm], lost_mech[nm]
            return None, None
        succ, mech = _absorbed_by(dn)                       # the name that actually ended the lineage
        L["absorbed_other_name_only"] = (succ is None and any(_absorbed_by(nm)[0] for nm in L["names"] if nm != dn))
        if succ:
            L["split"] = "absorbed"; L["succ"], L["mech"] = succ, mech; continue
        if L["id"] in reborn_as:
            L["split"] = "reborn"; L["mech"] = f"reborn as lineage {reborn_as[L['id']]}"; continue
        if dn in dissolve_audit:
            L["mech"] = "validation-dissolve (Arm A)"
        elif dn in cap_audit:
            L["mech"] = "cap-drop"
        # health at death
        dl = L["last_live"]
        mem = L["last_members"] or L["founders"]
        legs = [scores.legs(t, dl) for t in mem]
        rs = [x["rs"] for x in legs if x["rs"] is not None]
        idl = prices.session_on_or_before(dl)
        for x, t in zip(legs, mem):
            h = prices.down_day_hold(t, idl)
            x["hold_q"] = h is not None and h > 0
            x["subtle"] = x["vel_q"] or x["turn_q"] or x["hold_q"]
        L["rs_death"] = float(np.mean(rs)) if rs else None
        L["subtle_death"] = sum(x["subtle"] for x in legs) / len(legs) if legs else None
        pd_ = coherence(prices, L["founders"], idl, True)
        L["post_death"] = pd_[0] if pd_ else None
        pre = L["pre_rlx"]
        if L["rs_death"] is None:
            L["split"] = "unreadable (no RS row at death)"; continue
        coh_fell = (pre is not None and L["post_death"] is not None and L["post_death"] < pre)
        coh_known = (pre is not None and L["post_death"] is not None)
        if L["rs_death"] < DISSOLVED_RS or coh_fell:
            L["split"] = "dissolved"
            L["diss_why"] = ("rs<50" if L["rs_death"] < DISSOLVED_RS else "") + ("+" if L["rs_death"] < DISSOLVED_RS and coh_fell else "") + ("coh-fell" if coh_fell else "")
        elif not coh_known:
            L["split"] = "post-death window incomplete (censored)"
        elif L["rs_death"] >= ASSIGN_POOL_RS_FLOOR:
            L["split"] = "killed-healthy"
        else:
            L["split"] = "rs 50-70, coherence held (undefined by task)"
        # subtle-RS variant of healthy: members subtly strong at death (>= half), level irrelevant
        L["healthy_subtle"] = (L["subtle_death"] is not None and L["subtle_death"] >= 0.5 and not coh_fell and coh_known)
        L["split_subtle"] = "killed-healthy" if L["healthy_subtle"] else L["split"]

    for L in lineages:
        L.setdefault("split_subtle", L.get("split"))
    nonmat = [L for L in lineages if not L["matured"]]
    say(f"absorption re-keyed on the lineage's DEATH name; lineages an any-name rule would have called absorbed but whose "
        f"ending name has no absorption record: {sum(1 for L in nonmat if L.get('absorbed_other_name_only'))}")
    say(f"lineages never reaching Mainstream: {pct(len(nonmat), len(lineages))} "
        f"(Mainstream is age-gated: age>=5 sessions in a 7-day window AND score>=50 — the stage clock is not earliness)")
    for cls in ("grind", "cogap"):
        sub = [L for L in nonmat if L["class"] == cls]
        c = Counter(L["split"] for L in sub)
        say(f"  {cls:5s} non-maturers n={len(sub)}: " + " · ".join(f"{k}={v}" for k, v in c.most_common()))
        classifiable = [L for L in sub if L["split"] in ("absorbed", "reborn", "killed-healthy", "dissolved", "rs 50-70, coherence held (undefined by task)")]
        n = len(classifiable)
        churn = sum(1 for L in classifiable if L["split"] in ("absorbed", "reborn", "killed-healthy"))
        diss = sum(1 for L in classifiable if L["split"] == "dissolved")
        undef = sum(1 for L in classifiable if L["split"].startswith("rs 50-70"))
        say(f"        classifiable n={n}: CHURN (absorbed+reborn+killed-healthy) {pct(churn, n)} · DISSOLVED {pct(diss, n)} · undefined-bucket {pct(undef, n)}")
        dw = Counter(L.get("diss_why") for L in classifiable if L["split"] == "dissolved")
        say(f"        dissolved by: {dict(dw)}  (rs<50 alone is the task's noise definition; 'coh-fell' with RS>=70 = healthy RS, coherence slipped)")
        # subtle-RS healthy variant
        hk = [L for L in classifiable if L["split"] in ("killed-healthy", "dissolved", "rs 50-70, coherence held (undefined by task)")]
        lvl = sum(1 for L in hk if L["split"] == "killed-healthy")
        sub_h = sum(1 for L in hk if L.get("healthy_subtle"))
        both_ = sum(1 for L in hk if L.get("healthy_subtle") and L["split"] == "killed-healthy")
        say(f"        healthy-at-death among the {len(hk)} health-split lineages: LEVEL (mean RS>=70 & coherence held) {lvl} · "
            f"SUBTLE (>=half members rising/turning/holding-up & coherence held) {sub_h} · both {both_} · subtle-only {sub_h - both_} · level-only {lvl - both_}")
        mech = Counter(L["mech"] for L in sub if L["mech"])
        say(f"        death mechanisms on record: {dict(mech)}")
        bm2 = defaultdict(Counter)
        for L in classifiable:
            bm2[L["birth"].strftime("%Y-%m")][L["split"]] += 1
        say("        by birth month: " + "  ".join(f"{m}: " + ",".join(f"{k[:9]}={v}" for k, v in c.items()) for m, c in sorted(bm2.items())))
    # sensitivity of the dissolved verdict to its two arms (task definition: RS<50 OR coherence fell below pre-birth)
    both_read = [L for L in lineages if L["pre_rlx"] is not None and L["post_rlx"] is not None]
    fell = sum(1 for L in both_read if L["post_rlx"] < L["pre_rlx"])
    say(f"\n  dissolved-definition check: post-birth coherence sits BELOW pre-birth in {pct(fell, len(both_read))} of ALL readable lineages "
        f"(maturers included: {pct(sum(1 for L in both_read if L['matured'] and L['post_rlx'] < L['pre_rlx']), sum(1 for L in both_read if L['matured']))}) — "
        f"a cohort selected for moving together regresses after naming, so the 'coherence fell' arm fires near-universally")
    for cls in ("grind", "cogap"):
        cl = [L for L in nonmat if L["class"] == cls and L["split"] in ("absorbed", "reborn", "killed-healthy", "dissolved", "rs 50-70, coherence held (undefined by task)")]
        d_rs = sum(1 for L in cl if L["split"] == "dissolved" and "rs<50" in (L.get("diss_why") or ""))
        d_coh_only = [L for L in cl if L["split"] == "dissolved" and L.get("diss_why") == "coh-fell"]
        say(f"  {cls:5s}: dissolved on the RS arm (members' mean RS < {DISSOLVED_RS:.0f} at death) {pct(d_rs, len(cl))}; "
            f"dissolved ONLY because coherence slipped {len(d_coh_only)}, of which {sum(1 for L in d_coh_only if L['rs_death'] >= ASSIGN_POOL_RS_FLOOR)} still had mean RS >= {ASSIGN_POOL_RS_FLOOR:.0f}")
    # scope item 3: the split with subtle-healthy folded in (operator 2026-09-07)
    CLS = ("absorbed", "reborn", "killed-healthy", "dissolved", "rs 50-70, coherence held (undefined by task)")
    say(f"\n  SUBTLE-HEALTHY FOLD-IN (killed-healthy also = coherence held AND >= half members rising/turning/holding-up at death, any RS level):")
    for cls in ("grind", "cogap"):
        cl = [L for L in nonmat if L["class"] == cls and L["split"] in CLS]
        moved = [L for L in cl if L["split_subtle"] != L["split"]]
        frm = Counter((L["split"][:9], L.get("diss_why") or "") for L in moved)
        c1, c2 = Counter(L["split"] for L in cl), Counter(L["split_subtle"] for L in cl)
        ch1 = sum(v for k, v in c1.items() if k in ("absorbed", "reborn", "killed-healthy")); ch2 = sum(v for k, v in c2.items() if k in ("absorbed", "reborn", "killed-healthy"))
        say(f"  {cls:5s} classifiable n={len(cl)}: LEVEL split churn {pct(ch1, len(cl))} dissolved {pct(c1['dissolved'], len(cl))} killed-healthy {c1['killed-healthy']} | "
            f"SUBTLE split churn {pct(ch2, len(cl))} dissolved {pct(c2['dissolved'], len(cl))} killed-healthy {c2['killed-healthy']} | moved {len(moved)} from {dict(frm)}")
    # bars
    g = [L for L in nonmat if L["class"] == "grind" and L["split"] in ("absorbed", "reborn", "killed-healthy", "dissolved", "rs 50-70, coherence held (undefined by task)")]
    gd = sum(1 for L in g if L["split"] == "dissolved")
    allc = [L for L in nonmat if L["split"] in ("absorbed", "reborn", "killed-healthy", "dissolved", "rs 50-70, coherence held (undefined by task)")]
    ch = sum(1 for L in allc if L["split"] in ("absorbed", "reborn", "killed-healthy"))
    gd_rs = sum(1 for L in g if L["split"] == "dissolved" and "rs<50" in (L.get("diss_why") or ""))
    say(f"\n  BAR A (dissolved >= 40% within GRIND): pre-declared definition (either arm) {pct(gd, len(g))} → {'CROSSED' if len(g) and gd/len(g) >= 0.40 else 'not crossed'}; "
        f"RS arm alone {pct(gd_rs, len(g))} → {'CROSSED' if len(g) and gd_rs/len(g) >= 0.40 else 'not crossed'}")
    say(f"  BAR B (churn >= 60% of classifiable non-maturers, both classes): {pct(ch, len(allc))} → {'CROSSED' if len(allc) and ch/len(allc) >= 0.60 else 'not crossed'}")
    gd2 = sum(1 for L in g if L["split_subtle"] == "dissolved"); ch2 = sum(1 for L in allc if L["split_subtle"] in ("absorbed", "reborn", "killed-healthy"))
    say(f"  under the SUBTLE-healthy definition: BAR A {pct(gd2, len(g))} → {'CROSSED' if len(g) and gd2/len(g) >= 0.40 else 'not crossed'}; "
        f"BAR B {pct(ch2, len(allc))} → {'CROSSED' if len(allc) and ch2/len(allc) >= 0.60 else 'not crossed'}")
    gcg = [L for L in allc if L["class"] == "cogap"]
    say(f"  (co-gap class, reported not judged: dissolved {pct(sum(L['split']=='dissolved' for L in gcg), len(gcg))}, "
        f"churn {pct(sum(L['split'] in ('absorbed','reborn','killed-healthy') for L in gcg), len(gcg))})")
    # maturity vs birth strength
    say("\n  maturity by founder strength at birth (Mainstream reached / lineages):")
    for cls in ("grind", "cogap"):
        ls = [L for L in lineages if L["class"] == cls]
        for lab, pred in (("level-majority", lambda L: L["f_level"] >= 0.5), ("subtle-majority", lambda L: L["f_subtle"] >= 0.5),
                          ("neither", lambda L: L["f_level"] < 0.5 and L["f_subtle"] < 0.5)):
            s = [L for L in ls if pred(L)]
            say(f"    {cls:5s} {lab:16s}: matured {pct(sum(L['matured'] for L in s), len(s))}")
        for lab, pred in (("pre-coh >= bar (rlx)", lambda L: L["pre_rlx"] is not None and L["pre_rlx"] >= MEAN_CORR_MIN),
                          ("pre-coh <  bar (rlx)", lambda L: L["pre_rlx"] is not None and L["pre_rlx"] < MEAN_CORR_MIN)):
            s = [L for L in ls if pred(L)]
            say(f"    {cls:5s} {lab:16s}: matured {pct(sum(L['matured'] for L in s), len(s))}")

    # ---- 6. operator labels ------------------------------------------------------------
    say(f"\n--- 6. AGREEMENT WITH THE OPERATOR'S LABELS (themed stratum; coherence over the {WINDOW} sessions ending alert_date-1) ---")
    sheet = list(csv.DictReader(open(os.path.join(ROOT, "docs/analysis/368_labeling_sheet.tsv")), delimiter="\t"))
    themed = [r for r in sheet if r["stratum"] == "themed"]
    prod_lbl = Counter((r["stratum"], r["operator_label"]) for r in cohort)
    say(f"sheet themed rows={len(themed)} labels={dict(Counter(r['LABEL'] for r in themed))}; prod themed labels: "
        f"y={prod_lbl[('themed','y')]} n={prod_lbl[('themed','n')]} ?={prod_lbl[('themed','?')]} — "
        f"{'MATCH' if prod_lbl[('themed','y')]==sum(r['LABEL']=='Y' for r in themed) and prod_lbl[('themed','n')]==sum(r['LABEL']=='N' for r in themed) else 'MISMATCH'}")
    say("detectable ceiling stated up front: 5 of the 9 N labels are ONE scope error (crypto miners converting to AI: "
        "HUT x2, WULF, CLSK, IREN) — a coherent cohort under the wrong name, invisible to price coherence by construction; "
        "2 are membership errors (BATL, KYTX), 2 near-misses (LUNR, CRCL). Price coherence can at most catch 4 of 9.")
    lab_rows = []
    for r in themed:
        if r["LABEL"] not in ("Y", "N"):
            continue
        ad, t, tn = d_(r["date"]), r["ticker"], r["theme"]
        pool_rows = list(names[tn].rows) if tn in names else []
        if not pool_rows:   # fall back to any lineage-mate name
            root = uf.find(tn) if tn in uf.p else None
            for nm in (groups.get(root, []) if root else []):
                pool_rows += names[nm].rows
        win = [x for x in pool_rows if x["tickers"] and ad - timedelta(days=10) <= x["date"] <= ad]
        with_t = [x for x in win if t in x["tickers"]]
        cand = with_t or [x for x in win if x["date"] <= ad - timedelta(days=1)]
        row = {"ticker": t, "date": ad, "theme": tn, "label": r["LABEL"], "note": r["NOTE"][:50],
               "coh": None, "fit": None, "n": None, "in_theme": None, "board": None}
        if cand:
            board = max(cand, key=lambda x: (x["date"], x["id"]))
            members = list(board["tickers"])
            row["in_theme"], row["board"] = t in members, board["date"]
            ia = prices.session_on_or_before(ad)
            res = coherence(prices, members + ([] if t in members else [t]), ia - WINDOW - 1, True)
            if res:
                corr, used = res[3], res[4]
                midx = [k for k, u in enumerate(used) if u in members]
                if len(midx) >= 2:
                    sub = corr[np.ix_(midx, midx)]
                    row["coh"], row["n"] = float(np.nanmean(sub[np.triu_indices(len(midx), k=1)])), len(midx)
                others = [k for k, u in enumerate(used) if u in members and u != t]
                if t in used and others:
                    rowv = corr[used.index(t), others]
                    row["fit"] = float(np.nanmean(rowv)) if not np.isnan(rowv).all() else None
        lab_rows.append(row)
    Y = [x for x in lab_rows if x["label"] == "Y"]
    N = [x for x in lab_rows if x["label"] == "N"]
    say(f"decided rows={len(lab_rows)} (Y={len(Y)} N={len(N)}); board row found within 10d: {sum(x['board'] is not None for x in lab_rows)}; "
        f"ticker a MEMBER of that row: {sum(bool(x['in_theme']) for x in lab_rows)} (the sheet's theme column is the shadow's "
        f"attribution, which can name a theme the ticker never joined — its fit is still read against that cohort)")
    for meas in ("coh", "fit"):
        yv = [x[meas] for x in Y if x[meas] is not None]
        nv = [x[meas] for x in N if x[meas] is not None]
        pairs = [(a, b) for a in yv for b in nv]
        auc = sum(a > b for a, b in pairs) / len(pairs) if pairs else None
        label = "cohort coherence" if meas == "coh" else "ticker's own fit to its cohort"
        say(f"  {label:32s}: Y median={med(yv)} (n={len(yv)})  N median={med(nv)} (n={len(nv)})  "
            f"share of (Y,N) pairs where Y scores higher = {auc:.2f}" + ("" if auc is None else "") +
            f"  |  at the fixed {MEAN_CORR_MIN} bar: Y>=bar {pct(sum(v >= MEAN_CORR_MIN for v in yv), len(yv))}, N>=bar {pct(sum(v >= MEAN_CORR_MIN for v in nv), len(nv))}")
    say("  the 9 N rows, ticker fit vs its cohort (lower = the name did not move with the group):")
    for x in sorted(N, key=lambda x: (x["fit"] is None, x["fit"] if x["fit"] is not None else 0)):
        say(f"    {x['ticker']:5s} {x['date']} fit={'n/a' if x['fit'] is None else f'{x['fit']:.2f}'} coh={'n/a' if x['coh'] is None else f'{x['coh']:.2f}'} "
            f"on-board={x['in_theme']} — {x['note']}")
    fits_y = sorted([x["fit"] for x in Y if x["fit"] is not None])
    say(f"  for scale, Y-row fit quartiles: {', '.join(f'{np.percentile(fits_y, q):.2f}' for q in (10, 25, 50, 75, 90))} (p10/p25/p50/p75/p90)")

    # ---- 7. funnel: subtle pool names dropped below the assignment floor -------------------
    say(f"\n--- 7. FUNNEL CHECK — velocity/turner pool names with RS < ASSIGN_POOL_RS_FLOOR ({ASSIGN_POOL_RS_FLOOR:.0f}): do they ever reach a theme? ---")
    say(f"(scope note said THEME_RS_MIN=40; source reads THEME_RS_MIN={THEME_RS_MIN:g} — flagged)")
    run_dates = sorted({d_(r["theme_date"]) for r in themes_raw})
    funnel = {d_(r["created_at"]): json.loads(r["detail"]) for r in audit if r["event_type"] == "theme_engine_funnel"}
    rows_by_date: dict[date, set] = defaultdict(set)
    cov_by_date: dict[date, set] = defaultdict(set)
    for n in names.values():
        for r in n.rows:
            if r["tickers"] and r["stage"] != "Retired":
                rows_by_date[r["date"]] |= set(r["tickers"])
                if r["stage"] != "Fading":          # engine: covered = active non-Fading members
                    cov_by_date[r["date"]] |= set(r["tickers"])
    fid_v = fid_t = fid_n = near_v = near_t = 0
    drop_v = drop_t = tot_v = tot_t = 0
    themed_later_v = themed_later_t = 0
    ctl_v = ctl_v_themed = ctl_t = ctl_t_themed = 0     # control: same pools, RS >= floor
    sample = []
    for D in run_dates:
        vel, turn = scores.pools(D)
        covered = set()
        for k in range(1, ACTIVE_RECENCY_DAYS + 1):
            covered |= cov_by_date.get(D - timedelta(days=k), set())
        uv = [x for x in vel if x[0] not in covered]
        ut = [x for x in turn if x[0] not in covered]
        if D in funnel:
            fid_n += 1
            fid_v += (len(uv) == funnel[D]["velocity"]); near_v += abs(len(uv) - funnel[D]["velocity"]) <= 3
            fid_t += (len(ut) == funnel[D]["turners"]); near_t += abs(len(ut) - funnel[D]["turners"]) <= 3
        later = set()
        for k in range(0, 15):
            later |= rows_by_date.get(D + timedelta(days=k), set())
        for t, _, rs in [(x[0], x[1], x[2]) for x in vel]:
            if rs >= ASSIGN_POOL_RS_FLOOR and t not in covered:
                ctl_v += 1; ctl_v_themed += (t in later)
            if rs < ASSIGN_POOL_RS_FLOOR and t not in covered:
                tot_v += 1
                if t in later:
                    themed_later_v += 1
                else:
                    drop_v += 1
                    if len(sample) < 8:
                        sample.append(f"{t}@{D} rs={rs:.0f} (velocity)")
        for t, _, _, rs in turn:
            if rs >= ASSIGN_POOL_RS_FLOOR and t not in covered:
                ctl_t += 1; ctl_t_themed += (t in later)
            if rs < ASSIGN_POOL_RS_FLOOR and t not in covered:
                tot_t += 1
                if t in later:
                    themed_later_t += 1
                else:
                    drop_t += 1
    say(f"pool-reconstruction fidelity vs the engine's own nightly funnel rows (n={fid_n} nights since 2026-06-18, uncovered counts): "
        f"velocity exact {pct(fid_v, fid_n)} / within 3 {pct(near_v, fid_n)}; turners exact {pct(fid_t, fid_n)} / within 3 {pct(near_t, fid_n)}")
    say(f"velocity-pool names below the assignment floor and not already in a theme: {tot_v} ticker-nights over {len(run_dates)} runs; "
        f"reached ANY theme within 14 days: {pct(themed_later_v, tot_v)}; never did: {pct(drop_v, tot_v)}")
    say(f"turner-pool names below the floor and uncovered: {tot_t}; reached a theme within 14d: {pct(themed_later_t, tot_t)}; never did: {pct(drop_t, tot_t)}")
    say(f"CONTROL — the same pools' names AT/ABOVE the floor and uncovered: velocity {ctl_v} ticker-nights, reached a theme within 14d "
        f"{pct(ctl_v_themed, ctl_v)}; turners {ctl_t}, reached {pct(ctl_t_themed, ctl_t)}")
    say(f"sample of dropped subtle names: {sample}")
    say(f"note: the turner predicate requires a sector, and only the top ~300 RS ranks carry one in mi_stock_scores — "
        f"a 'not highest RS but turning' name is excluded from that pool by construction unless it is already near the top")

    # ---- write ---------------------------------------------------------------------------
    with open(OUT_LIN, "w") as fh:
        w = csv.writer(fh, delimiter="\t")
        cols = ["id", "birth", "birth_name", "names", "founders", "class", "class_src", "n_gappers", "gap_recency",
                "pre_nat", "post_nat", "pre_rlx", "post_rlx", "matured", "alive", "last_live", "life_days",
                "rs_birth", "f_level", "f_subtle", "f_vel", "f_turn", "f_hold", "split", "mech", "rs_death",
                "subtle_death", "post_death", "diss_why", "succ", "split_subtle"]
        w.writerow(cols)
        for L in lineages:
            w.writerow([("|".join(L[c]) if isinstance(L.get(c), list) else
                         (f"{L[c]:.3f}" if isinstance(L.get(c), float) else L.get(c, ""))) for c in cols])
    with open(OUT_FND, "w") as fh:
        w = csv.writer(fh, delimiter="\t")
        cols = ["lineage", "birth", "class", "ticker", "rs", "level70", "vel_q", "turn_q", "hold", "hold_q", "subtle", "gapped"]
        w.writerow(cols)
        for f in founder_rows:
            w.writerow([(f"{f[c]:.4f}" if isinstance(f.get(c), float) else f.get(c, "")) for c in cols])
    with open(OUT_TXT, "w") as fh:
        fh.write("\n".join(LOG) + "\n")
    print(f"\nwrote {OUT_TXT}\n      {OUT_LIN}\n      {OUT_FND}")


if __name__ == "__main__":
    main()
