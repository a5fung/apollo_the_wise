#!/usr/bin/env python3
"""Naming LATENCY — how many sessions after a group's move began did the engine name it?

READ-ONLY, $0. Runs on local captures only (scripts/probes/_step1_*.tsv frozen 2026-09-07 plus
the _lat_*.psv deltas captured ONCE on 2026-09-20 from prod). Touches no strategy / entry / exit /
sizing / safeguard / grade / alert / trade code. Nothing is tuned; every constant is the engine's.

Serves PLAN #655 step 2 ("do we discover them early enough") — the operator needs a distribution
to set a target against. Refines docs/analysis/step3_theme_runway_2026-09-07.md §2, which gave
earliest-signal-to-naming p50 = 30 sessions but was censored at a 40-session lookback and ended
at births of 2026-09-04.

What it computes:
  1. LINEAGES — same identity rules as step 1 (_step1_theme_precision.py): mi_theme_renames +
     tombstone "renamed to" notes + theme_renamed_on_mass_flag audit rows + Jaccard >= 0.4 vs any
     name's most recent row in the prior 10 days. Reproduction of step 1's 398 lineages on the
     <= 2026-09-04 births is asserted as the validation.
  2. BIRTH CLASS — ONE uniform rule for every birth (open-gap from mi_daily_closes, open / prior
     close - 1 >= MIN_GAP_PCT, the 20 sessions up to and including birth day):
        cogap_sameday : >= 2 founders gapped on birth day or the day before  (reflexive — the EP
                        made the theme; latency ~0 BY CONSTRUCTION, not lateness)
        cogap_window  : >= 2 founders gapped in the window but not same-day
        grind         : 0 or 1 founder gapped
  3. RS RUN START — founders' mean rs_composite (mi_stock_scores; a founder with no row that day is
     OUTSIDE THE SCORED UNIVERSE, not weak — mean over present founders, require >= half present,
     else that score date is unscored for the cohort). The run of mean >= ASSIGN_POOL_RS_FLOOR (70)
     in force AT BIRTH is walked back to its first date. STRICT: any score date < 70 ends the run.
     TOLERANT: three consecutive score dates < 70 end it. Latency = trading sessions (SPY calendar)
     from run start to birth. A run reaching the first score date is CENSORED (">= N"). Scores are
     WEEKLY before 2026-03-19 (one Friday a week) and daily after; a run reaching the weekly era is
     flagged. Mean RS < 70 at birth = NAMED BEFORE STRENGTH (the early-naming case, counted, not
     dropped) — its forward first crossing is reported as a negative latency where it exists.
     ⚠ RS composite is 40% 1M + 30% 3M + 30% 6M percentile: it LAGS price, so this latency is a
     FLOOR on true lateness.
  4. PRICE RUN START — founders' equal-weight index (mean daily return) above its 50-session
     average, run in force at birth, 3-session tolerance. Independent of RS percentiles; needs 50
     sessions of history so early births are censored.
  5. MOVE ALREADY MADE — cohort equal-weight % change from RS run start to birth, absolute and
     relative to SPY.
  6. READINESS — share of themes named within T sessions of RS run start, T in {5, 10, 20}, by
     class. Censored runs count as NOT within T (they are >= N with N > T for every era quoted).
  7. CO-GAP TIMING — sessions from the latest / first founder gap to birth.

Run:  python3 scripts/probes/_lat_theme_naming_latency.py
Out:  scripts/probes/_lat_theme_naming_latency_out.txt (+ _lineages.tsv)
"""
from __future__ import annotations

import csv
import math
import os
import re
import statistics
from collections import Counter, defaultdict
from datetime import date, timedelta

HERE = os.path.dirname(os.path.abspath(__file__))
_SFX = "" if os.environ.get("LAT_SMA_N", "50") == "50" else f"_sma{os.environ['LAT_SMA_N']}"
OUT = os.path.join(HERE, f"_lat_theme_naming_latency_out{_SFX}.txt")
OUT_LIN = os.path.join(HERE, f"_lat_theme_naming_latency_lineages{_SFX}.tsv")

RS_FLOOR = 70.0            # theme_engine.ASSIGN_POOL_RS_FLOOR
MIN_GAP_PCT = 9.0          # ep_detector._MIN_GAP_PCT_DEFAULT
WINDOW = 20                # step 1's birth-class window (sessions through birth day)
JACCARD_SAME_THEME = 0.4   # _get_theme_history fallback
HISTORY_DAYS = 10
TOL_BREAK = 3              # tolerant run: consecutive sub-floor dates that end it
SMA_N = int(os.environ.get("LAT_SMA_N", "50"))   # sensitivity: LAT_SMA_N=20
DAILY_ERA_START = date(2026, 3, 19)
HEADLINE_FROM = date(2026, 6, 1)   # >= 50 daily score sessions of lookback
STEP1_END = date(2026, 9, 4)

LOG: list[str] = []


def say(s: str = "") -> None:
    LOG.append(s)
    print(s)


def pct(n: int, d: int) -> str:
    return f"{n} of {d} ({100.0 * n / d:.0f}%)" if d else f"{n} of 0"


def qs(xs: list[float]) -> str:
    if not xs:
        return "n=0"
    xs = sorted(xs)

    def q(p: float) -> float:
        k = (len(xs) - 1) * p
        lo, hi = math.floor(k), math.ceil(k)
        return xs[lo] + (xs[hi] - xs[lo]) * (k - lo)

    return f"n={len(xs)} p10={q(.1):.0f} p25={q(.25):.0f} med={q(.5):.0f} p75={q(.75):.0f} p90={q(.9):.0f} max={xs[-1]:.0f}"


def d_(s: str) -> date:
    return date.fromisoformat(s[:10])


# ---------------------------------------------------------------------------------------
# Loaders
# ---------------------------------------------------------------------------------------
def load_tsv(name: str) -> list[dict]:
    with open(os.path.join(HERE, name)) as fh:
        lines = fh.read().splitlines()
    rows = list(csv.DictReader(lines[2:], delimiter="\t"))
    first = list(rows[0].keys())[0] if rows else None
    return [r for r in rows if not (first and r[first].startswith("("))]


def load_psv(name: str, n: int) -> list[list[str]]:
    out = []
    with open(os.path.join(HERE, name)) as fh:
        for line in fh:
            p = line.rstrip("\n").split("|")
            if len(p) >= n:
                out.append(p[:n])
    return out


def main() -> None:
    say("=== THEME NAMING LATENCY probe — captures of 2026-09-07 (frozen) + 2026-09-20 (deltas) ===")

    # ---- closes → calendar ------------------------------------------------------------
    closes: dict[str, dict[date, tuple[float, float | None]]] = defaultdict(dict)
    for src in ("_step1_closes.tsv", "_step2_closes.tsv"):
        for r in load_tsv(src):
            if r["close"]:
                closes[r["ticker"]][d_(r["trade_date"])] = (float(r["close"]), float(r["open_price"]) if r["open_price"] else None)
    for src in ("_lat_closes_delta.psv", "_lat_closes_missing15.psv"):
        for td, t, c, o in load_psv(src, 4):
            if c:
                closes[t][d_(td)] = (float(c), float(o) if o else None)
    cal = sorted(closes["SPY"].keys())
    idx = {d: i for i, d in enumerate(cal)}
    say(f"trading calendar (SPY closes): {len(cal)} sessions {cal[0]}..{cal[-1]}; tickers with closes={len(closes)}")

    def sess_on_or_before(d: date) -> int:
        i = len(cal) - 1
        while i >= 0 and cal[i] > d:
            i -= 1
        return i

    # ---- scores -----------------------------------------------------------------------
    scores: dict[date, dict[str, float]] = defaultdict(dict)
    for r in load_tsv("_step1_scores_all.tsv"):
        if r["rs_composite"]:
            scores[d_(r["score_date"])][r["ticker"]] = float(r["rs_composite"])
    for sd, t, rs, _rank in load_psv("_lat_scores_delta.psv", 4):
        if rs:
            scores[d_(sd)][t] = float(rs)
    score_dates = sorted(scores)
    weekly = [d for d in score_dates if d < DAILY_ERA_START]
    say(f"score dates={len(score_dates)} {score_dates[0]}..{score_dates[-1]}; weekly era (before {DAILY_ERA_START}): "
        f"{len(weekly)} dates; daily after")
    missing_daily = [d for d in cal if d >= DAILY_ERA_START and d not in scores]
    say(f"daily-era sessions with NO score date: {len(missing_daily)} {missing_daily[:12]}")

    # ---- themes → names ---------------------------------------------------------------
    themes = load_psv("_lat_themes_full.psv", 7)
    names: dict[str, dict] = {}
    for _id, td, name, stage, source, parent, tk in themes:
        n = names.setdefault(name, {"name": name, "rows": []})
        n["rows"].append({"id": int(_id), "date": d_(td), "stage": stage, "source": source,
                          "tickers": [t for t in tk.split(",") if t]})
    for n in names.values():
        n["rows"].sort(key=lambda r: (r["date"], r["id"]))
        member = [r for r in n["rows"] if r["tickers"]]
        n["first"] = member[0] if member else None
        n["first_is_retired"] = bool(n["first"] and n["first"]["stage"] == "Retired")
        n["stages"] = {r["stage"] for r in n["rows"]}
        n["last_row"] = n["rows"][-1]
    max_date = max(r["date"] for n in names.values() for r in n["rows"])
    say(f"mi_themes rows={len(themes)} names={len(names)} span ..{max_date}")

    # ---- lineage union (engine identity rules only, as step 1) --------------------------
    parent: dict[str, str] = {}

    def find(x: str) -> str:
        parent.setdefault(x, x)
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    def union(a: str, b: str) -> None:
        ra, rb = find(a), find(b)
        if ra != rb:
            parent[rb] = ra

    e = Counter()
    for old, new, _mech, _td in load_psv("_lat_renames.psv", 4):
        if old in names and new in names:
            union(old, new); e["rename_table"] += 1
    for _id, _td, name, note in load_psv("_lat_tombstones.psv", 4):
        m = re.search(r"renamed to '([^']+)'", note)
        if m and name in names and m.group(1) in names:
            union(name, m.group(1)); e["tombstone_note"] += 1
    for _d, ev, summary in load_psv("_lat_rename_audit.psv", 3):
        if ev == "theme_renamed_on_mass_flag":
            m = re.search(r"^'([^']+)' renamed to '([^']+)'", summary)
            if m and m.group(1) in names and m.group(2) in names:
                union(m.group(1), m.group(2)); e["mass_flag_audit"] += 1
    by_date: dict[date, list[tuple[str, list[str]]]] = defaultdict(list)
    for n in names.values():
        for r in n["rows"]:
            if r["tickers"]:
                by_date[r["date"]].append((n["name"], r["tickers"]))
    for n in names.values():
        if not n["first"] or n["first_is_retired"]:
            continue
        d0, F = n["first"]["date"], set(n["first"]["tickers"])
        recent: dict[str, list[str]] = {}
        for k in range(1, HISTORY_DAYS + 1):
            for nm, tk in by_date.get(d0 - timedelta(days=k), []):
                if nm != n["name"] and nm not in recent:
                    recent[nm] = tk
        best, bj = None, 0.0
        for nm, tk in recent.items():
            j = len(F & set(tk)) / len(F | set(tk))
            if j > bj:
                best, bj = nm, j
        if best and bj >= JACCARD_SAME_THEME:
            union(best, n["name"]); e["jaccard"] += 1
    say(f"lineage edges: {dict(e)}")

    groups: dict[str, list[str]] = defaultdict(list)
    for nm in names:
        groups[find(nm)].append(nm)
    lineages = []
    for root, members in groups.items():
        objs = [names[m] for m in members]
        births = [o for o in objs if o["first"] and not o["first_is_retired"]]
        if not births:
            continue
        b = min(births, key=lambda o: (o["first"]["date"], o["first"]["id"]))
        lineages.append({
            "names": sorted(members), "birth_name": b["name"], "birth": b["first"]["date"],
            "founders": list(b["first"]["tickers"]), "source": b["first"]["source"],
            "matured": any("Mainstream" in o["stages"] for o in objs),
            "alive": any(o["last_row"]["stage"] != "Retired" and (max_date - o["last_row"]["date"]).days <= 7 for o in objs),
        })
    lineages.sort(key=lambda L: (L["birth"], L["birth_name"]))
    for i, L in enumerate(lineages, 1):
        L["id"] = i
    old = [L for L in lineages if L["birth"] <= STEP1_END]
    new = [L for L in lineages if L["birth"] > STEP1_END]
    new_names = sum(1 for n in names.values() if n["first"] and not n["first_is_retired"] and n["first"]["date"] > STEP1_END)
    say(f"\n--- 1. LINEAGES: {len(lineages)} from {len(names)} names; births <= {STEP1_END}: {len(old)} "
        f"(step 1 had 398); births after: {len(new)} lineages from {new_names} newly-born names")

    # cross-check vs step 1's lineage table
    s1 = {(d_(r["birth"]), r["birth_name"]): r for r in load_tsv("_step1_theme_precision_lineages.tsv")} if False else {}
    with open(os.path.join(HERE, "_step1_theme_precision_lineages.tsv")) as fh:
        s1rows = list(csv.DictReader(fh, delimiter="\t"))
    s1 = {(d_(r["birth"]), r["birth_name"]): r for r in s1rows}
    matched = sum(1 for L in old if (L["birth"], L["birth_name"]) in s1)
    say(f"step-1 cross-check: {matched} of {len(old)} pre-09-04 lineages match step 1's (birth, birth_name) exactly; "
        f"step 1 table has {len(s1)}")

    # ---- helpers ----------------------------------------------------------------------
    def open_gap_sessions(t: str, lo: int, hi: int) -> list[int]:
        out = []
        c = closes.get(t, {})
        for i in range(max(lo, 1), hi + 1):
            cur, prev = c.get(cal[i]), c.get(cal[i - 1])
            if cur and prev and cur[1] and prev[0] and prev[0] > 0 and (cur[1] / prev[0] - 1) * 100 >= MIN_GAP_PCT:
                out.append(i)
        return out

    def cohort_rs(F: list[str], d: date) -> float | None:
        sc = scores.get(d)
        if not sc:
            return None
        present = [sc[t] for t in F if t in sc]
        need = max(1, math.ceil(len(F) / 2))
        return statistics.fmean(present) if len(present) >= need else None

    def ew_index(F: list[str]) -> list[float | None]:
        """Equal-weight index of the founders on the calendar (mean daily return, cumulative)."""
        out: list[float | None] = [None] * len(cal)
        lvl = None
        need = max(1, math.ceil(len(F) / 2))
        for i in range(1, len(cal)):
            rets = []
            for t in F:
                c = closes.get(t, {})
                a, b = c.get(cal[i - 1]), c.get(cal[i])
                if a and b and a[0] > 0:
                    rets.append(b[0] / a[0] - 1)
            if len(rets) >= need:
                lvl = (lvl if lvl is not None else 1.0) * (1 + statistics.fmean(rets))
                out[i] = lvl
            else:
                out[i] = None if lvl is None else lvl   # carry level; flat day (no data)
        return out

    spy_idx = ew_index(["SPY"])

    # ---- per lineage ------------------------------------------------------------------
    for L in lineages:
        F = L["founders"]
        b = sess_on_or_before(L["birth"])
        L["b_on_cal"] = cal[b] == L["birth"]
        L["b"] = b
        lo = max(b - WINDOW, 1)
        gap_by_founder = {t: open_gap_sessions(t, lo, b) for t in F}
        gappers = [t for t, g in gap_by_founder.items() if g]
        sameday = [t for t, g in gap_by_founder.items() if any(s >= b - 1 for s in g)]
        L["n_gappers"], L["n_sameday"] = len(gappers), len(sameday)
        L["n_sameday_strict"] = sum(1 for t, g in gap_by_founder.items() if b in g)
        L["cls"] = "cogap_sameday" if len(sameday) >= 2 else ("cogap_window" if len(gappers) >= 2 else "grind")
        allg = sorted(s for g in gap_by_founder.values() for s in g)
        L["gap_latest_lag"] = (b - allg[-1]) if allg else None
        L["gap_first_lag"] = (b - allg[0]) if allg else None
        L["n_closes_founders"] = sum(1 for t in F if closes.get(t))

        # RS at birth: score date on b, else latest score date within 3 sessions before
        sd_b = None
        for k in range(0, 4):
            if b - k >= 0 and cal[b - k] in scores:
                sd_b = cal[b - k]; break
        L["rs_b"] = cohort_rs(F, sd_b) if sd_b else None
        L["rs_state"] = "unscorable" if L["rs_b"] is None else ("strong" if L["rs_b"] >= RS_FLOOR else "named_before_strength")
        for mode in ("strict", "tolerant"):
            L[f"rs_start_{mode}"] = None; L[f"rs_lat_{mode}"] = None; L[f"rs_cens_{mode}"] = False; L[f"rs_weekly_{mode}"] = False
        if L["rs_state"] == "strong":
            prior = [d for d in score_dates if d <= sd_b]
            for mode in ("strict", "tolerant"):
                start, below, censored = sd_b, 0, True
                for d in reversed(prior):
                    v = cohort_rs(F, d)
                    if v is None:
                        continue
                    if v >= RS_FLOOR:
                        start, below = d, 0
                    else:
                        below += 1
                        if mode == "strict" or below >= TOL_BREAK:
                            censored = False
                            break
                L[f"rs_start_{mode}"] = start
                L[f"rs_lat_{mode}"] = b - sess_on_or_before(start)
                L[f"rs_lat_days_{mode}"] = (L["birth"] - start).days
                L[f"rs_cens_{mode}"] = censored
                L[f"rs_weekly_{mode}"] = start < DAILY_ERA_START
        elif L["rs_state"] == "named_before_strength":
            # forward: first score date after birth with mean >= 70 held on 3 consecutive score dates
            later = [d for d in score_dates if d > sd_b]
            run = 0; hit = None
            for d in later:
                v = cohort_rs(F, d)
                if v is None:
                    continue
                run = run + 1 if v >= RS_FLOOR else 0
                if run == 1:
                    cand = d
                if run >= 3:
                    hit = cand; break
            L["rs_fwd_lag"] = (sess_on_or_before(hit) - b) if hit else None

        # price run (EW index vs SMA50), tolerant
        ix = ew_index(F)
        sma = [None] * len(cal)
        for i in range(len(cal)):
            w = [x for x in ix[max(0, i - SMA_N + 1): i + 1] if x is not None]
            if i >= SMA_N - 1 and ix[i] is not None and len(w) == SMA_N:
                sma[i] = statistics.fmean(w)
        L["px_state"] = "na"; L["px_lat"] = None; L["px_cens"] = False
        if sma[b] is not None:
            if ix[b] > sma[b]:
                start, below, censored = b, 0, True
                for i in range(b, -1, -1):
                    if sma[i] is None:
                        break
                    if ix[i] > sma[i]:
                        start, below = i, 0
                    else:
                        below += 1
                        if below >= TOL_BREAK:
                            censored = False; break
                L["px_state"] = "above"; L["px_lat"] = b - start; L["px_cens"] = censored
                L["px_start"] = cal[start]
            else:
                L["px_state"] = "below"
        # BRIDGE to the 09-07 study: FIRST date in [b-40, b] where mean founder RS >= 70 held on 3
        # consecutive score dates (its RS leg, founders) — lag from that first crossing to birth
        L["rs_first40_lag"] = None
        lo40 = cal[max(b - 40, 0)]
        run = 0; cand = None
        for d in [d for d in score_dates if lo40 <= d <= cal[b]]:
            v = cohort_rs(F, d)
            if v is None:
                continue
            run = run + 1 if v >= RS_FLOOR else 0
            if run == 1:
                cand = d
            if run >= 3:
                L["rs_first40_lag"] = b - sess_on_or_before(cand); break
        # move already made from the PRICE run start to birth
        L["px_move_pct"] = L["px_move_rel_pct"] = None
        if L["px_state"] == "above" and not L["px_cens"]:
            s_ = idx[L["px_start"]]
            if ix[s_] and ix[b] and spy_idx[s_] and spy_idx[b]:
                L["px_move_pct"] = (ix[b] / ix[s_] - 1) * 100
                L["px_move_rel_pct"] = ((ix[b] / ix[s_]) / (spy_idx[b] / spy_idx[s_]) - 1) * 100
        # move already made from the tolerant RS run start to birth
        L["move_pct"] = L["move_rel_pct"] = None
        if L.get("rs_start_tolerant"):
            s = sess_on_or_before(L["rs_start_tolerant"])
            if ix[s] and ix[b] and spy_idx[s] and spy_idx[b]:
                L["move_pct"] = (ix[b] / ix[s] - 1) * 100
                L["move_rel_pct"] = ((ix[b] / ix[s]) / (spy_idx[b] / spy_idx[s]) - 1) * 100

    # ---- 2. population + class --------------------------------------------------------
    say(f"\n--- 2. POPULATION: {len(lineages)} lineages, births {lineages[0]['birth']}..{lineages[-1]['birth']}; "
        f"births not on a trading session: {sum(1 for L in lineages if not L['b_on_cal'])}; "
        f"founders per lineage median {statistics.median(len(L['founders']) for L in lineages):.0f}; "
        f"lineages with a founder lacking any closes: {sum(1 for L in lineages if L['n_closes_founders'] < len(L['founders']))}")
    bm = defaultdict(Counter)
    for L in lineages:
        bm[L["birth"].strftime("%Y-%m")][L["cls"]] += 1
    say("births by month (grind / cogap_window / cogap_sameday): " + "  ".join(
        f"{m}: {c['grind']}/{c['cogap_window']}/{c['cogap_sameday']}" for m, c in sorted(bm.items())))
    cc = Counter(L["cls"] for L in lineages)
    say(f"class, ALL: {dict(cc)}; strict same-day (>=2 founders gapped ON birth day): "
        f"{sum(1 for L in lineages if L['n_sameday_strict'] >= 2)}")
    # agreement with step 1's primary class on the overlap
    agree = tot = 0
    for L in old:
        r = s1.get((L["birth"], L["birth_name"]))
        if r:
            tot += 1
            mine = "grind" if L["cls"] == "grind" else "cogap"
            agree += (mine == r["class"])
    say(f"agreement with step 1's primary class (scan-log where covered, else open-gap): {pct(agree, tot)}")
    say("birth source lane by class: " + "; ".join(
        f"{src}: " + "/".join(str(Counter(L['cls'] for L in lineages if L['source'] == src)[k]) for k in ('grind', 'cogap_window', 'cogap_sameday'))
        for src, _ in Counter(L["source"] for L in lineages).most_common()))

    # ---- 3. RS latency ------------------------------------------------------------------
    def rs_block(title: str, S: list[dict]) -> None:
        say(f"\n{title}  (n={len(S)})")
        st = Counter(L["rs_state"] for L in S)
        say(f"  at birth: strong (mean founder RS >= {RS_FLOOR:.0f}) {st['strong']} · named BEFORE strength {st['named_before_strength']} · unscorable {st['unscorable']}")
        fwd = [L["rs_fwd_lag"] for L in S if L["rs_state"] == "named_before_strength"]
        if fwd:
            hit = [x for x in fwd if x is not None]
            say(f"  named-before-strength: reached 70 (held 3) later for {len(hit)} of {len(fwd)}; sessions after naming {qs(hit)}")
        for mode in ("strict", "tolerant"):
            R = [L for L in S if L["rs_state"] == "strong"]
            cens = [L for L in R if L[f"rs_cens_{mode}"]]
            wk = [L for L in R if L[f"rs_weekly_{mode}"]]
            unc = [L for L in R if not L[f"rs_cens_{mode}"]]
            say(f"  RS run start, {mode}: sessions from run start to naming, ALL strong {qs([L[f'rs_lat_{mode}'] for L in R])}")
            say(f"      censored at the data edge (>=): {len(cens)}; run reaches the weekly-score era: {len(wk)}")
            say(f"      UNCENSORED only: sessions {qs([L[f'rs_lat_{mode}'] for L in unc])}")
            say(f"      UNCENSORED only: calendar days {qs([L[f'rs_lat_days_{mode}'] for L in unc])}")
        R = [L for L in S if L["rs_state"] == "strong"]
        for T in (5, 10, 20):
            w = sum(1 for L in R if L["rs_lat_tolerant"] <= T and not L["rs_cens_tolerant"])
            say(f"  named within {T:>2} sessions of RS run start (tolerant): {pct(w, len(R))}")
        mv = [L["move_pct"] for L in S if L["move_pct"] is not None]
        mr = [L["move_rel_pct"] for L in S if L["move_rel_pct"] is not None]
        say(f"  cohort move ALREADY MADE from RS run start to naming: absolute % {qs(mv)}; vs SPY % {qs(mr)}")
        P = [L for L in S if L["px_state"] == "above"]
        say(f"  PRICE run (EW index above 50-session avg at birth): above {len(P)} · below {sum(1 for L in S if L['px_state']=='below')} · "
            f"no 50-session history {sum(1 for L in S if L['px_state']=='na')}; censored {sum(1 for L in P if L['px_cens'])}")
        say(f"      sessions from price-run start to naming, uncensored: {qs([L['px_lat'] for L in P if not L['px_cens']])}")
        for T in (5, 10, 20):
            w = sum(1 for L in P if L["px_lat"] <= T and not L["px_cens"])
            say(f"      named within {T:>2} sessions of PRICE run start: {pct(w, len(P))}  (of all births incl. below/na: {pct(w, len(S))})")
        pm = [L["px_move_pct"] for L in S if L["px_move_pct"] is not None]
        pr = [L["px_move_rel_pct"] for L in S if L["px_move_rel_pct"] is not None]
        say(f"      cohort move ALREADY MADE from PRICE run start to naming: absolute % {qs(pm)}; vs SPY % {qs(pr)}")
        nb = [L for L in S if L["rs_state"] == "named_before_strength"]
        say(f"      overlap: named-before-strength AND price below its 50-session avg: {sum(1 for L in nb if L['px_state']=='below')} of {len(nb)}; "
            f"strong-at-birth AND price below: {sum(1 for L in S if L['rs_state']=='strong' and L['px_state']=='below')} of {sum(1 for L in S if L['rs_state']=='strong')}")
        B = [L["rs_first40_lag"] for L in S if L["rs_first40_lag"] is not None]
        say(f"  BRIDGE to 09-07 §2 (first RS>=70 held-3 crossing in a 40-session lookback, founders): fires {pct(len(B), len(S))}; lag {qs(B)}")
        G = [L for L in S if L["gap_latest_lag"] is not None]
        say(f"  founder GAPS in the 20-session window: lineages with any {len(G)}; sessions from LATEST founder gap to naming {qs([L['gap_latest_lag'] for L in G])}; "
            f"from FIRST founder gap {qs([L['gap_first_lag'] for L in G])}")

    say("\n--- 3. LATENCY — headline population = births >= " + str(HEADLINE_FROM) + " (>= 50 daily score sessions of lookback) ---")
    H = [L for L in lineages if L["birth"] >= HEADLINE_FROM]
    rs_block("HEADLINE, all classes", H)
    for cls in ("grind", "cogap_window", "cogap_sameday"):
        rs_block(f"HEADLINE, {cls}", [L for L in H if L["cls"] == cls])
    say("\n--- 4. EARLIER ERAS (shorter lookback; read with the censoring line) ---")
    for lo_, hi_ in ((date(2026, 3, 1), date(2026, 4, 30)), (date(2026, 5, 1), date(2026, 5, 31))):
        S = [L for L in lineages if lo_ <= L["birth"] <= hi_]
        if S:
            rs_block(f"births {lo_}..{hi_}, all classes", S)
    say("\n--- 5. HEADLINE by birth month (tolerant RS, uncensored strong births): month: n strong / n uncensored / median sessions ---")
    for m in sorted({L["birth"].strftime("%Y-%m") for L in H}):
        S = [L for L in H if L["birth"].strftime("%Y-%m") == m and L["rs_state"] == "strong"]
        U = [L["rs_lat_tolerant"] for L in S if not L["rs_cens_tolerant"]]
        say(f"  {m}: {len(S)} / {len(U)} / {statistics.median(U) if U else float('nan'):.0f}   grind-only median: "
            f"{statistics.median([L['rs_lat_tolerant'] for L in S if not L['rs_cens_tolerant'] and L['cls']=='grind']) if any(not L['rs_cens_tolerant'] and L['cls']=='grind' for L in S) else float('nan'):.0f}")
    say("\n--- 6. HEADLINE by birth source lane (tolerant RS, uncensored strong): lane: n / median sessions / within 10 ---")
    for src, n in Counter(L["source"] for L in H).most_common():
        S = [L for L in H if L["source"] == src and L["rs_state"] == "strong"]
        U = [L["rs_lat_tolerant"] for L in S if not L["rs_cens_tolerant"]]
        say(f"  {src}: births {n}, strong {len(S)}, uncensored {len(U)}, median {statistics.median(U) if U else float('nan'):.0f}, "
            f"within 10 {pct(sum(1 for x in U if x <= 10), len(S))}")
    say("\n--- 7. MATURED vs NOT (headline, tolerant RS, uncensored strong) ---")
    for flag in (True, False):
        S = [L for L in H if L["matured"] == flag and L["rs_state"] == "strong"]
        U = [L["rs_lat_tolerant"] for L in S if not L["rs_cens_tolerant"]]
        say(f"  matured={flag}: strong {len(S)}, uncensored {qs(U)}")
    say("\n--- 8. STEP-1 POPULATION ONLY (births <= 2026-09-04, all eras) — comparable to the 09-07 doc's n=331 lag read ---")
    rs_block("births 03-19..09-04, all classes", old)

    # ---- 9. the themes that covered the operator-labelled EPs -----------------------------
    say("\n--- 9. LINEAGES that covered a labelled EP at/after its EP date (from the prod join of 2026-09-20) ---")
    want = {"PLTR": ["U.S. Government/Defense Contract Surge", "U.S. Government/Defense Spending Surge", "AI-Powered Enterprise Analytics & Intelligent Workflow SaaS"],
            "MRNA": ["mRNA Vaccine & Therapeutics Platforms", "mRNA & Next-Gen Vaccine Platform Resurgence", "Vaccine & Antiviral Therapeutics Rebound"],
            "TEAM": ["Software Development & DevOps Collaboration Platforms"],
            "HTFL": ["AI-Driven Diagnostics & Imaging Re-Rating", "Cardiac & Diagnostic Imaging Recovery", "AI-Native Diagnostics & Computational Medicine Re-Rating"]}
    for t, nms in want.items():
        for L in lineages:
            if any(n in L["names"] for n in nms):
                say(f"  {t}: lineage #{L['id']} born {L['birth']} '{L['birth_name'][:55]}' src={L['source']} cls={L['cls']} founders={L['founders']} "
                    f"founder? {t in L['founders']} rs_at_birth={L['rs_b'] if L['rs_b'] is None else round(L['rs_b'],1)} state={L['rs_state']} "
                    f"rs_lat_tol={L['rs_lat_tolerant']} px={L['px_state']}/{L['px_lat']} names={len(L['names'])}")

    # ---- per-lineage TSV ----------------------------------------------------------------
    cols = ["id", "birth", "birth_name", "source", "cls", "n_founders", "n_gappers", "n_sameday", "matured", "alive",
            "rs_b", "rs_state", "rs_start_strict", "rs_lat_strict", "rs_cens_strict", "rs_start_tolerant", "rs_lat_tolerant",
            "rs_lat_days_tolerant", "rs_cens_tolerant", "rs_weekly_tolerant", "rs_fwd_lag", "px_state", "px_start", "px_lat", "px_cens",
            "move_pct", "move_rel_pct", "px_move_pct", "px_move_rel_pct", "rs_first40_lag", "gap_latest_lag", "gap_first_lag", "founders"]
    with open(OUT_LIN, "w") as fh:
        fh.write("\t".join(cols) + "\n")
        for L in lineages:
            row = []
            for c in cols:
                v = L.get(c)
                if c == "n_founders":
                    v = len(L["founders"])
                elif c == "founders":
                    v = "|".join(L["founders"])
                elif isinstance(v, float):
                    v = f"{v:.2f}"
                row.append("" if v is None else str(v))
            fh.write("\t".join(row) + "\n")
    with open(OUT, "w") as fh:
        fh.write("\n".join(LOG) + "\n")
    say(f"\nwrote {OUT} and {OUT_LIN}")


if __name__ == "__main__":
    main()
