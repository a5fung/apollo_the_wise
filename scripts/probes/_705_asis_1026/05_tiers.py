#!/usr/bin/env python3
"""#711 step 7, part 1 — the confidence TIERS of his in-span positions, from SCREEN facts only.

His decision 2026-10-27 ("Go"): "sort out which trades we're confident are correct and which we aren't, then we can run next step with
these distinctions". Registered in docs/analysis/cb_asis_step7_grouping_prereg_2026-10-27.md (§1); steps 5-6 stay frozen in
docs/analysis/cb_asis_reconstruction_prereg_2026-10-26.md (never edited; its body is pinned here too).

WHAT IT DOES   every position whose BUY window ends in the primary span (2020-01-01..2022-06-30) on windows v2 gets ONE tier from the
               screen facts of ranges.tsv (step 5, re-run 2) and entries_v2.tsv (the panel) — the bracket type and resolution of each
               side, whether each side has a reachable range, whether the window is inverted, and the panel's `flicker` flag — plus a
               SUB-FLAG (not a tier), CONFIRMED-BY-HIS-WORDS, from step 6b's per-statement file (check_r1_r5.tsv). It prints the counts
               by tier x year x side-bracket and a composition table per tier (hold length, year, bracket pair, minute coverage, price
               band, streams seen on, pre-market-possible share, confirmed share), so the reader sees what each tier over- or
               under-represents. --run writes tiers.tsv.

THE TIERS (locked before any outcome of any trade is read; the text of the registration §2, verbatim in TIERS_TEXT):
  HIGH        buy AND sale side each in a bracket of at most one session (same_in_in, same_pre_in, next_in_pre, next_in_in), resolution
              minute on both, not inverted, seen on 2+ streams (not a flicker).
  MEDIUM      both sides within 2-5 sessions or better (the four brackets above or sessions_2_5), any resolution WITH a range on both
              sides, not inverted, not a flicker.
  ONE-STREAM  flickers (the panel's flag: seen on one stream only and gone within 5 sessions) whose two sides would otherwise read
              MEDIUM or better — a real quick trade or a misread ticker; the file cannot tell which.
  LOW         the rest: a wide window (6+ sessions) on either side, a `bracket_other` side (the clocks give no narrower rule), a side
              with no reachable range (no bars), an inverted window (extended hours), a missing sale row.
  "Seen on 2+ streams" is implemented as `not flicker` — the panel file's own flag (`flicker` = one stream AND gone within 5
  sessions). The literal `n_streams >= 2` differs on 3 positions (seen on one stream, held longer than 5 sessions, both windows within
  5 sessions): they are MEDIUM here, printed by eid and carried as `single_stream_nonflicker`. The registration (§2.2) discloses the fork;
  the counts he approved (398 / 279 / 510 / 401) are this reading's and are the dry run's claims.
  CONFIRMED   = r5: a statement of his joined uniquely to the position whose action agreed with the window's side (R5), OR r1: a stated
              FILL price (`fill == 'fill'`, never a stop LEVEL) inside the side's reachable range (R1, any day class); `confirmed_r1_primary`
              = the R1 primary line only (8 positions). From check_r1_r5.tsv, written by 03_check on windows v2.

WHAT IT NEVER READS  any outcome column — ONE input (check_r1_r5.tsv) carries his stated dollar result and a `stopped` action, and this
               module loads that file with `usecols` = STMT_COLS (six columns: eid, r5_agree, inside, fill, primary, join_status), so
               neither column is ever in memory; the dry run claims the loaded columns are exactly those six. `forbidden_outcomes.txt`
               (the outcome names of 04_band and 03_check included) is scanned against this module with the §3.1 names. Never read: the
               candidate points, the captions, the bars, anything dated after 2024-12-31, the seven outcome folders, any module of the
               rule folders (asis_common copies; the import belt checks sys.modules).

STEP-7 FEATURE REGISTRATION (part 2's input, registered HERE so it is pinned under the marker: STEP7_FEATURES / exit_lookbacks_defined).
               The exit side carries NO ret_N; an exit-side look-back over the prior N sessions is kept only when N < hold_sessions_min
               (or the trade is a same-session round trip, hold_sessions_max == 0, when every prior session precedes the entry) — otherwise
               it reaches back across the entry and carries the trade's result under another name (review F1). The primary feature set
               holds no `our_length` column (the frozen §3.4 flag); the sweep stands in their place (review F4).

STAGES  --dry-run     loads the three inputs, assigns every tier, asserts the CLAIMS (the approved counts, the population, the flag
                      agreement, the confirmed sets) and prints every table; writes 05_tiers_dryrun.txt; nothing else written.
        --print-pins  the sha256 pins (step 5's inputs and modules; the frozen steps-5/6 doc body; step 5's outputs; 6b's module, printout
                      and per-statement file; this module; the outcome-name list; the dry-run printout; the NEW doc's body) to stdout and
                      05_tiers_pins.txt.
        --run         writes tiers.tsv and 05_tiers.txt; refused unless the dry run completed with 0 MISMATCH and was made by the modules on
                      disk, every pin is pasted below the NEW doc's <!-- FREEZE --> marker (none ABSENT), the ledger verifies, and no
                      output exists. Ledger rows `step7_tiers_*`.

Guards: no network, no production server, no paid call. Run:
  python3 scripts/probes/_705_asis_1026/05_tiers.py --dry-run | --print-pins | --run
"""
from __future__ import annotations

import argparse
import collections
import importlib.util
import os
import sys
import time

import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))


def _load_common():
    name = "asis_common"
    if name in sys.modules and getattr(sys.modules[name], "__file__", "") == os.path.join(HERE, "asis_common.py"):
        return sys.modules[name]
    spec = importlib.util.spec_from_file_location(name, os.path.join(HERE, "asis_common.py"))
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


C = _load_common()
GuardStop = C.GuardStop

# ---- paths -------------------------------------------------------------------------------------------------------------------------------
DOC7 = os.path.join(C.REPO, "docs", "analysis", "cb_asis_step7_grouping_prereg_2026-10-27.md")
P05 = {"dry": os.path.join(HERE, "05_tiers_dryrun.txt"), "run": os.path.join(HERE, "05_tiers.txt"),
       "refused": os.path.join(HERE, "05_tiers.refused.txt"), "pins": os.path.join(HERE, "05_tiers_pins.txt")}
OUT_7 = {"tiers": os.path.join(C.OUT_DIR, "tiers.tsv")}
CHECK_R1_R5 = os.path.join(C.OUT_DIR, "check_r1_r5.tsv")              # 6b's per-statement file (asis_check_common.OUT_6B), read here by path
P03_RUN = os.path.join(HERE, "03_check.txt")
FORBIDDEN_OUTCOMES_FILE = os.path.join(HERE, "forbidden_outcomes.txt")
MODULE_FILES_7 = ("asis_common.py", "05_tiers.py", "forbidden_identifiers.txt", "forbidden_outcomes.txt")
SCAN_FILES_7 = ("asis_common.py", "05_tiers.py")
STAGE_7 = "step7_tiers_"
SPAN = ("2020-01-01", "2022-06-30")

# ---- the tiers ---------------------------------------------------------------------------------------------------------------------------
TIERS = ("HIGH", "MEDIUM", "ONE-STREAM", "LOW")
TIGHT = ("same_in_in", "same_pre_in", "next_in_pre", "next_in_in")     # a bracket of at most one session
NEAR = TIGHT + ("sessions_2_5",)                                       # "within 2-5 sessions or better"
PROPOSED = {"HIGH": 398, "MEDIUM": 279, "ONE-STREAM": 510, "LOW": 401}   # the counts he approved (2026-10-27); the dry run's claims
TIERS_TEXT = {
    "HIGH": "buy AND sale side each in a bracket of at most one session (same_in_in, same_pre_in, next_in_pre, next_in_in), resolution minute, "
            "not inverted, seen on 2+ streams (not a flicker)",
    "MEDIUM": "both sides within 2-5 sessions or better, any resolution with a range, seen on 2+ streams",
    "ONE-STREAM": "flickers (seen on one stream only): a real quick trade or a misread ticker",
    "LOW": "the rest (wide windows, missing data, inverted)",
}
TIER_COLS = ["eid", "sym", "year", "tier", "tier_reason", "confirmed", "confirmed_r5", "confirmed_r1", "confirmed_r1_primary", "flicker",
             "n_streams", "n_sightings", "single_stream_nonflicker", "buy_bracket", "sale_bracket", "bracket_pair", "buy_resolution",
             "sale_resolution", "minute_coverage", "buy_n_sessions", "sale_n_sessions", "hold_sessions_min", "hold_sessions_max", "hold_bucket",
             "buy_price_raw", "price_band", "buy_range_width_pct", "sale_range_width_pct", "pre_market_possible", "sale_in_span", "buy_flags",
             "sale_flags"]


# ---- step 7 part 2's feature registration (review F1 / F4; the doc §3.3) — pinned here, imported by 06_groups, never widened there ----------
DIST_N = (3, 5, 10, 20, 40, 60)          # 01_points.DIST_N: dist_hi_N / dist_lo_N (ret_N on the ENTRY side only)
SMA_N = (5, 8, 10, 13, 20, 30, 50)       # asis_common.SMA_SWEEP: dist_ma_N
SINCE_N = (5, 20, 60)                    # 01_points.SINCE_N: sessions_since_hi_N
RATIO_N = (5, 10, 20, 40, 60)            # the sweep computed in place of the two ratios whose only frozen length was 20 (range vs average range, volume vs average volume)
OUR_LENGTH = frozenset({"range_vs_avgrange_20", "dist_hi_20", "dist_hi_60", "dist_lo_20", "dist_lo_60", "dist_ma_10", "dist_ma_20",
                        "vol_day_vs_20", "vol_sofar_vs_20", "sessions_since_hi_20"})   # the frozen §3.4 `our_length` columns (20-session range / volume, 10- and 20-day averages, 20- and 60-session highs)
HELD_OUT = ("family", "direction", "k", "our_length", "dist_round", "dist_vwap", "pos_in_day_so_far", "vol_min_vs_median", "range_width_pct")
# never a feature: the family tags, the point-level columns, the band width — and every outcome column, whose names the identifier scan
# (forbidden_outcomes.txt) keeps out of the step-7 modules altogether, so they are not listed here
DAY_OWN = ("pos_in_day", "minute", "gap_pct", "range_pct") + tuple(f"range_vs_avgrange_{n}" for n in RATIO_N) + \
          tuple(f"vol_day_vs_{n}" for n in RATIO_N) + tuple(f"vol_sofar_vs_{n}" for n in RATIO_N)     # a side's OWN day; the ratios carry no sign
LOOKBACKS = {1: ("dist_prev_high", "dist_prev_low", "dist_prev_close")}                            # look-back length N -> columns reaching N prior sessions
for _n in DIST_N:
    LOOKBACKS.setdefault(_n, ()); LOOKBACKS[_n] += (f"dist_hi_{_n}", f"dist_lo_{_n}")
for _n in SMA_N:
    LOOKBACKS.setdefault(_n, ()); LOOKBACKS[_n] += (f"dist_ma_{_n}",)
for _n in SINCE_N:
    LOOKBACKS.setdefault(_n, ()); LOOKBACKS[_n] += (f"sessions_since_hi_{_n}",)
ENTRY_RET = tuple(f"ret_{n}" for n in DIST_N)                                                       # the run-up BEFORE the entry; entry side only
ENTRY_ALL = DAY_OWN + tuple(c for n in sorted(LOOKBACKS) for c in LOOKBACKS[n]) + ENTRY_RET
EXIT_ALL = DAY_OWN + tuple(c for n in sorted(LOOKBACKS) for c in LOOKBACKS[n])                      # NO ret_N on the exit side (review F1)
TRADE_LEVEL = ("hold_sessions_max",)
STEP7_FEATURES = {
    "primary": {"entry": tuple(c for c in ENTRY_ALL if c not in OUR_LENGTH), "exit": tuple(c for c in EXIT_ALL if c not in OUR_LENGTH),
                "trade": TRADE_LEVEL},                                                               # the sweep in the our_length columns' place
    "with_our_length": {"entry": ENTRY_ALL, "exit": EXIT_ALL, "trade": TRADE_LEVEL},                 # the sensitivity run (review F4)
}


def exit_lookbacks_defined(hold_min, hold_max) -> tuple:
    """The exit-side look-back lengths N that are DEFINED for a trade (review F1): kept when N < hold_sessions_min — the prior N sessions
    then end before the entry day — or when the trade is a same-session round trip (hold_sessions_max == 0: every prior session precedes
    the entry). A look-back whose N reaches the entry day or past it is left blank (a STRUCTURAL blank) and counted; it is never filled
    from the bars. hold_min is the test because N < hold_min implies N < the true hold."""
    try:
        hmin, hmax = int(float(hold_min)), int(float(hold_max))
    except (TypeError, ValueError):
        return ()
    if hmax == 0:
        return tuple(sorted(LOOKBACKS))
    return tuple(n for n in sorted(LOOKBACKS) if n < hmin)


def exit_features_defined(hold_min, hold_max, run: str = "primary") -> tuple:
    """The exit-side columns that are defined for a trade in `run`: the day-own columns always, the look-backs by exit_lookbacks_defined."""
    ok = set(exit_lookbacks_defined(hold_min, hold_max))
    cols = STEP7_FEATURES[run]["exit"]
    return tuple(c for c in cols if c in DAY_OWN or any(c in LOOKBACKS[n] for n in ok))


class Say:
    def __init__(self):
        self.lines = []

    def __call__(self, msg: str = "") -> None:
        print(msg, flush=True)
        self.lines.append(msg)

    def write(self, path: str) -> None:
        with open(path + ".partial", "w", encoding="utf-8") as fh:
            fh.write("\n".join(self.lines) + "\n")
        os.replace(path + ".partial", path)


class Claims:
    """The dry run's checks: every one printed; the RESULT line counts OK / MISMATCH (never tuned)."""

    def __init__(self, say):
        self.say, self.rows = say, []

    def __call__(self, label: str, expected, got) -> None:
        ok = expected == got
        self.rows.append((label, expected, got, ok))
        self.say(f"  [{'OK' if ok else 'MISMATCH'}] {label}: expected {expected}, got {got}")

    def result(self) -> str:
        n, k = len(self.rows), sum(1 for r in self.rows if r[3])
        return f"RESULT: {n} claims, {k} OK, {n - k} MISMATCH"


def pct(a, b) -> str:
    return f"{100.0 * a / b:.1f}%" if b else "n/a"


def table(say, hdr: list, rows: list) -> None:
    w = [max(len(str(x)) for x in col) for col in zip(hdr, *rows)] if rows else [len(h) for h in hdr]
    say("  " + "  ".join(str(h).ljust(w[k]) for k, h in enumerate(hdr)))
    for r in rows:
        say("  " + "  ".join(str(x).ljust(w[k]) for k, x in enumerate(r)))


# ---- the pure functions (tested on fixtures) -------------------------------------------------------------------------------------------
def _b(x) -> bool:
    return str(x).strip().lower() == "true"


def side_quality(row: dict | None) -> dict:
    """The screen facts of ONE side of a position (a ranges.tsv row): tight / near bracket, minute resolution, a reachable range, inverted."""
    if row is None:
        return {"present": False, "tight": False, "near": False, "minute": False, "has_range": False, "inverted": False, "bracket": "",
                "resolution": "", "n_sessions": ""}
    br = str(row.get("bracket", ""))
    return {"present": True, "tight": br in TIGHT, "near": br in NEAR, "minute": str(row.get("resolution", "")) == "minute",
            "has_range": str(row.get("range_lo", "")) != "" and str(row.get("range_hi", "")) != "", "inverted": _b(row.get("inverted", "")),
            "bracket": br, "resolution": str(row.get("resolution", "")), "n_sessions": str(row.get("n_sessions", ""))}


def tier_of(buy: dict | None, sale: dict | None, flicker: bool) -> tuple:
    """-> (tier, reason). Screen facts only. Order: HIGH, MEDIUM, ONE-STREAM, LOW — a flicker never reads HIGH or MEDIUM; a side that is
    wide / other / rangeless / inverted / missing reads LOW whatever the stream count."""
    b, s = side_quality(buy), side_quality(sale)
    if not b["present"] or not s["present"]:
        return "LOW", "sale_missing" if b["present"] else "buy_missing"
    if b["inverted"] or s["inverted"]:
        return "LOW", "inverted"
    if not (b["has_range"] and s["has_range"]):
        return "LOW", "no_range"
    if not (b["near"] and s["near"]):
        wide = any(q["bracket"] == "sessions_6plus" for q in (b, s))
        return "LOW", "wide_window" if wide else "bracket_other"
    if flicker:
        return "ONE-STREAM", "flicker"
    if b["tight"] and s["tight"] and b["minute"] and s["minute"]:
        return "HIGH", "tight_minute_both"
    return "MEDIUM", "near_with_range"


def hold_bucket(h) -> str:
    try:
        n = int(float(h))
    except (TypeError, ValueError):
        return "?"
    return "0" if n <= 0 else "1" if n == 1 else "2-5" if n <= 5 else "6-20" if n <= 20 else "21+"


def streams_bucket(n) -> str:
    try:
        k = int(float(n))
    except (TypeError, ValueError):
        return "?"
    return "1" if k <= 1 else "2" if k == 2 else "3-5" if k <= 5 else "6+"


def price_band(p) -> str:
    try:
        x = float(p)
    except (TypeError, ValueError):
        return "?"
    return "<$5" if x < 5 else "$5-20" if x < 20 else "$20-100" if x < 100 else "$100+"


def price_facet(price_raw, resolution) -> str:
    """The price-band facet keyed on the side's resolution (review F6): a blank average traded price is a daily-only side (no minute
    price) or a side with no bars — two different facts, never one 'no price' bucket."""
    band = price_band(price_raw)
    if band != "?":
        return band
    res = str(resolution or "")
    return "daily-only (no minute price)" if res == "daily_only" else "no bars" if res == "none" else "no range (inverted)" if res == "" \
        else f"{res}, no price"


def bracket_pair(b: dict, s: dict) -> str:
    def cls(q):
        return "tight" if q["tight"] else "near" if q["near"] else "other" if q["bracket"] in ("same_other", "next_other") else \
            "wide" if q["bracket"] == "sessions_6plus" else "inverted" if q["bracket"] == "inverted" else (q["bracket"] or "missing")
    return f"{cls(b)}/{cls(s)}"


def minute_coverage(b: dict, s: dict) -> str:
    return "both" if b["minute"] and s["minute"] else "one" if b["minute"] or s["minute"] else "none"


def confirmed_flags(stmts: list) -> dict:
    """eid -> {r5, r1, r1_primary} from 6b's per-statement rows. r5: `r5_agree == True` (set only on unique joins); r1: `inside == True`
    on a FILL (never a stop level); r1_primary: the R1 primary line's inside statements. Never reads a price or an outcome."""
    out = collections.defaultdict(lambda: {"r5": False, "r1": False, "r1_primary": False})
    for r in stmts:
        eid = str(r.get("eid", "")).strip()
        if not eid:
            continue
        if _b(r.get("r5_agree", "")):
            out[eid]["r5"] = True
        if _b(r.get("inside", "")) and str(r.get("fill", "")) == "fill":
            out[eid]["r1"] = True
            if _b(r.get("primary", "")):
                out[eid]["r1_primary"] = True
    return dict(out)


def population(ranges: list) -> dict:
    """eid -> {'buy': row, 'sale': row | None} for every position whose BUY window is in the primary span (ranges.tsv `in_span`)."""
    by = collections.defaultdict(dict)
    for r in ranges:
        by[str(r["eid"])][str(r["side"])] = r
    return {e: {"buy": v["buy"], "sale": v.get("sale")} for e, v in by.items() if "buy" in v and _b(v["buy"].get("in_span", ""))}


def assign_all(ranges: list, entries: dict, stmts: list) -> list:
    """One row per in-span position (TIER_COLS). `entries` = eid -> entries_v2 row (flicker, n_streams, n_sightings)."""
    pop = population(ranges)
    conf = confirmed_flags(stmts)
    rows = []
    for eid in sorted(pop, key=int):
        buy, sale = pop[eid]["buy"], pop[eid]["sale"]
        ent = entries.get(eid, {})
        flicker = _b(ent.get("flicker", buy.get("flicker", "")))
        tier, reason = tier_of(buy, sale, flicker)
        b, s = side_quality(buy), side_quality(sale)
        cf = conf.get(eid, {"r5": False, "r1": False, "r1_primary": False})
        ns = ent.get("n_streams", "")
        single_nonflicker = (not flicker) and str(ns) == "1"
        hold_min = buy.get("hold_sessions_min", "") or (sale or {}).get("hold_sessions_min", "")
        hold_max = buy.get("hold_sessions_max", "") or (sale or {}).get("hold_sessions_max", "")
        bflags, sflags = str(buy.get("flags", "")), str((sale or {}).get("flags", ""))
        rows.append({
            "eid": eid, "sym": buy.get("sym", ""), "year": buy.get("year", ""), "tier": tier, "tier_reason": reason,
            "confirmed": cf["r5"] or cf["r1"], "confirmed_r5": cf["r5"], "confirmed_r1": cf["r1"], "confirmed_r1_primary": cf["r1_primary"],
            "flicker": flicker, "n_streams": ns, "n_sightings": ent.get("n_sightings", ""), "single_stream_nonflicker": single_nonflicker,
            "buy_bracket": b["bracket"], "sale_bracket": s["bracket"], "bracket_pair": bracket_pair(b, s), "buy_resolution": b["resolution"],
            "sale_resolution": s["resolution"], "minute_coverage": minute_coverage(b, s), "buy_n_sessions": b["n_sessions"],
            "sale_n_sessions": s["n_sessions"], "hold_sessions_min": hold_min, "hold_sessions_max": hold_max, "hold_bucket": hold_bucket(hold_max),
            "buy_price_raw": buy.get("avg_traded_price_raw", ""), "price_band": price_facet(buy.get("avg_traded_price_raw", ""), b["resolution"]),
            "buy_range_width_pct": buy.get("range_width_pct", ""), "sale_range_width_pct": (sale or {}).get("range_width_pct", ""),
            "pre_market_possible": "pre_market_possible" in bflags.split("|"), "sale_in_span": _b((sale or {}).get("in_span", "")),
            "buy_flags": bflags, "sale_flags": sflags,
        })
    return rows


def counts_by(rows: list, key) -> collections.Counter:
    return collections.Counter(key(r) for r in rows)


def composition(rows: list, tier: str) -> list:
    """[(facet, value, n, share)] for one tier — screen facts only."""
    sub = [r for r in rows if r["tier"] == tier]
    n = len(sub)
    facets = [("hold length (sessions, max)", "hold_bucket", ("0", "1", "2-5", "6-20", "21+", "?")),
              ("year of the buy window", "year", ("2020", "2021", "2022")),
              ("bracket pair (buy/sale)", "bracket_pair", None),
              ("minute coverage", "minute_coverage", ("both", "one", "none")),
              ("average traded price, buy side (minute-resolved sides)", "price_band",
               ("<$5", "$5-20", "$20-100", "$100+", "daily-only (no minute price)", "no bars", "no range (inverted)", "minute, no price")),
              ("streams seen on", None, ("1", "2", "3-5", "6+", "?")),
              ("pre-market possible (buy side)", "pre_market_possible", (True, False)),
              ("confirmed by his words", "confirmed", (True, False))]
    out = []
    for label, col, order in facets:
        if col is None:
            cnt = collections.Counter(streams_bucket(r["n_streams"]) for r in sub)
        else:
            cnt = collections.Counter(r[col] for r in sub)
        keys = [k for k in order if k in cnt] if order else sorted(cnt, key=lambda k: -cnt[k])
        for k in keys:
            out.append((label, str(k), cnt[k], pct(cnt[k], n)))
    return out


# ---- inputs ------------------------------------------------------------------------------------------------------------------------------
STMT_COLS = ("eid", "r5_agree", "inside", "fill", "primary", "join_status")   # the ONLY columns of check_r1_r5.tsv ever loaded (review F2)


def read_tsv(path: str, usecols: tuple = None) -> list:
    return pd.read_csv(C.checked(path), sep="\t", dtype=str, keep_default_na=False, usecols=list(usecols) if usecols else None).to_dict("records")


def load_inputs(say) -> dict:
    ranges = read_tsv(C.OUTPUTS["ranges"])
    entries = {str(r["eid"]): r for r in read_tsv(C.FILES["entries_v2"])}
    stmts = read_tsv(CHECK_R1_R5, STMT_COLS)
    for r in ranges:                                                  # guard (1): nothing dated after the seal
        for col in ("lo", "hi"):
            if r.get(col):
                C.seal_date(r[col], f"ranges.tsv eid {r['eid']} {col}")
    say(f"- ranges.tsv: {len(ranges)} rows ({C.sha(C.OUTPUTS['ranges'])[:16]})")
    say(f"- entries_v2.tsv: {len(entries)} positions ({C.sha(C.FILES['entries_v2'])[:16]})")
    say(f"- check_r1_r5.tsv: {len(stmts)} statements ({C.sha(CHECK_R1_R5)[:16]}); columns loaded (usecols): {', '.join(STMT_COLS)} — "
        "its other columns (his stated dollar result among them) are never in memory")
    return {"ranges": ranges, "entries": entries, "stmts": stmts, "stmt_cols": tuple(stmts[0].keys()) if stmts else ()}


# ---- the printout ------------------------------------------------------------------------------------------------------------------------
def report(L: dict, rows: list, say, claims: Claims | None) -> None:
    pop = population(L["ranges"])
    n = len(rows)
    say("\n## The tiers (the registration §2, verbatim)")
    for t in TIERS:
        say(f"- {t}: {TIERS_TEXT[t]}")
    say("- 'seen on 2+ streams' = the panel's `flicker` flag is False (flicker = one stream AND gone within 5 sessions); the literal "
        "n_streams >= 2 reading differs on the positions listed under `single_stream_nonflicker` below")

    say(f"\n## Population: positions whose BUY window ends in {SPAN[0]}..{SPAN[1]} (ranges.tsv in_span, windows v2)")
    with_sale = sum(1 for e in pop if pop[e]["sale"] is not None)
    sale_in = sum(1 for r in rows if r["sale_in_span"])
    say(f"- positions {n}; with a sale row {with_sale}; sale window also in span {sale_in} (the rest kept: the position is in span by its buy)")
    cnt = counts_by(rows, lambda r: r["tier"])
    say("\n## Counts by tier")
    table(say, ["tier", "n", "share", "proposed"], [(t, cnt[t], pct(cnt[t], n), PROPOSED[t]) for t in TIERS])
    say("\n### LOW by reason")
    table(say, ["reason", "n"], sorted(counts_by([r for r in rows if r["tier"] == "LOW"], lambda r: r["tier_reason"]).items()))
    snf = [r for r in rows if r["single_stream_nonflicker"]]
    say(f"\n### single_stream_nonflicker: {len(snf)} positions seen on one stream but held longer than 5 sessions (not flickers)")
    table(say, ["tier", "n"], sorted(counts_by(snf, lambda r: r["tier"]).items()))
    say("- in MEDIUM: " + ", ".join(f"{r['eid']} {r['sym']} {r['year']}" for r in snf if r["tier"] == "MEDIUM"))

    say("\n## Counts by tier x year")
    years = sorted({r["year"] for r in rows})
    table(say, ["tier"] + years + ["all"], [[t] + [sum(1 for r in rows if r["tier"] == t and r["year"] == y) for y in years] + [cnt[t]] for t in TIERS])
    say("\n## Counts by tier x side bracket (buy side | sale side)")
    brs = [b for b in ("same_in_in", "same_pre_in", "next_in_pre", "next_in_in", "sessions_2_5", "sessions_6plus", "next_other", "same_other", "inverted", "")]
    for side in ("buy", "sale"):
        say(f"### {side} side")
        col = f"{side}_bracket"
        present = [b for b in brs if any(r[col] == b for r in rows)]
        table(say, ["tier"] + [b or "(missing)" for b in present],
              [[t] + [sum(1 for r in rows if r["tier"] == t and r[col] == b) for b in present] for t in TIERS])

    say("\n## Composition per tier (screen facts only; what each tier over- or under-represents)")
    for t in TIERS:
        say(f"### {t} (n = {cnt[t]})")
        table(say, ["facet", "value", "n", "share"], composition(rows, t))

    say("\n## Step-7 feature registration (part 2's input; the doc §3.3 — review F1 / F4)")
    for run in ("primary", "with_our_length"):
        f = STEP7_FEATURES[run]
        say(f"- {run}: entry {len(f['entry'])} columns, exit {len(f['exit'])} columns, trade-level {', '.join(f['trade'])}; "
            f"exit-side ret_N columns: {sum(1 for c in f['exit'] if c.startswith('ret_'))}; our_length columns in the set: "
            f"{sum(1 for c in f['entry'] + f['exit'] if c in OUR_LENGTH)}")
    say("- held out of every run: " + ", ".join(HELD_OUT) + " (and every outcome column, by the identifier scan)")
    say("- exit-side look-back rule: a look-back over the prior N sessions is defined only when N < hold_sessions_min, or the trade is a "
        "same-session round trip (hold_sessions_max = 0); otherwise a STRUCTURAL blank, counted, never filled from the bars")
    say("### exit-side look-back lengths defined, by hold (hold_sessions_min / max), per tier — share of the tier's positions")
    lb_rows = []
    for t in TIERS:
        sub = [r for r in rows if r["tier"] == t]
        pat = collections.Counter(",".join(str(n) for n in exit_lookbacks_defined(r["hold_sessions_min"], r["hold_sessions_max"])) or "(none)" for r in sub)
        for k_, v_ in sorted(pat.items(), key=lambda kv: -kv[1]):
            lb_rows.append((t, k_, v_, pct(v_, len(sub))))
    table(say, ["tier", "exit look-backs defined (N)", "n", "share"], lb_rows)
    prim = [r for r in rows if r["tier"] in ("HIGH", "MEDIUM")]
    none_lb = sum(1 for r in prim if not exit_lookbacks_defined(r["hold_sessions_min"], r["hold_sessions_max"]))
    say(f"- primary (HIGH + MEDIUM, n = {len(prim)}): {none_lb} positions ({pct(none_lb, len(prim))}) have NO exit look-back defined "
        f"(hold_sessions_min of 0 or 1: the prior session may be the entry day); same-session round trips in the primary: {sum(1 for r in prim if hold_bucket(r['hold_sessions_max']) == '0')}; "
        f"daily-only on one side {sum(1 for r in prim if r['minute_coverage'] == 'one')}, on both {sum(1 for r in prim if r['minute_coverage'] == 'none')}")

    say("\n## Confirmed by his words (a sub-flag, not a tier)")
    conf = confirmed_flags(L["stmts"])
    r5 = {e for e, v in conf.items() if v["r5"]}
    r1 = {e for e, v in conf.items() if v["r1"]}
    r1p = {e for e, v in conf.items() if v["r1_primary"]}
    say(f"- r5 (action agreed with the window's side): {len(r5)} positions; r1 (a stated fill inside the range): {len(r1)}; "
        f"of which the R1 primary line: {len(r1p)}; union {len(r5 | r1)}; overlap {len(r5 & r1)}")
    conf_rows = [r for r in rows if r["confirmed"]]
    assignable = [r for r in conf_rows if r["tier_reason"] not in ("no_range", "inverted", "sale_missing", "buy_missing")]
    say(f"- assignable to the groups (a reachable range on both sides, so features exist): {len(assignable)} of {len(conf_rows)} — "
        f"{sum(1 for r in assignable if r['tier'] in ('HIGH', 'MEDIUM'))} are rows of the primary fit (HIGH / MEDIUM), "
        f"{sum(1 for r in assignable if r['tier'] not in ('HIGH', 'MEDIUM'))} lie outside it (placed by nearest centroid); of those 47, "
        f"daily-only on a side: {sum(1 for r in assignable if r['minute_coverage'] != 'both')}; the rest have no bars on a side "
        f"({collections.Counter(r['tier_reason'] for r in conf_rows if r not in assignable)})")
    table(say, ["tier", "confirmed", "r5", "r1", "r1_primary", "share of tier"],
          [(t, sum(1 for r in rows if r["tier"] == t and r["confirmed"]), sum(1 for r in rows if r["tier"] == t and r["confirmed_r5"]),
            sum(1 for r in rows if r["tier"] == t and r["confirmed_r1"]), sum(1 for r in rows if r["tier"] == t and r["confirmed_r1_primary"]),
            pct(sum(1 for r in rows if r["tier"] == t and r["confirmed"]), cnt[t])) for t in TIERS])

    if claims is not None:
        say("\n## Claims")
        claims("in-span positions (the frozen doc's v2 count of in-span buy windows)", 1588, n)
        claims("every in-span position has a sale row", n, with_sale)
        claims("sale windows also in span", 1585, sale_in)
        for t in TIERS:
            claims(f"tier {t} = the approved count", PROPOSED[t], cnt[t])
        claims("the tiers sum to the population", n, sum(cnt[t] for t in TIERS))
        claims("single-stream non-flickers in MEDIUM (the disclosed fork)", 3, sum(1 for r in snf if r["tier"] == "MEDIUM"))
        claims("ONE-STREAM rows are all flickers", 0, sum(1 for r in rows if r["tier"] == "ONE-STREAM" and not r["flicker"]))
        claims("HIGH / MEDIUM rows are never flickers", 0, sum(1 for r in rows if r["tier"] in ("HIGH", "MEDIUM") and r["flicker"]))
        claims("HIGH rows have minute resolution on both sides", 0, sum(1 for r in rows if r["tier"] == "HIGH" and r["minute_coverage"] != "both"))
        disagree = sum(1 for r in L["ranges"] if str(r["eid"]) in L["entries"] and _b(r["flicker"]) != _b(L["entries"][str(r["eid"])]["flicker"]))
        claims("ranges.tsv `flicker` agrees with entries_v2.tsv row for row", 0, disagree)
        claims("r5_agree is set only on unique joins", 0, sum(1 for s in L["stmts"] if s.get("r5_agree", "") != "" and s.get("join_status") != "unique"))
        claims("confirmed r5 positions", 46, len(r5))
        claims("confirmed r1 (fill inside the range) positions", 19, len(r1))
        claims("confirmed r1 primary positions", 8, len(r1p))
        claims("confirmed union", 53, len(r5 | r1))
        eids = {r["eid"] for r in rows}
        claims("every confirmed position is in the population", 0, len((r5 | r1) - eids))
        claims("every statement with an eid lands in the population", 0, sum(1 for s in L["stmts"] if str(s.get("eid", "")).strip() and str(s["eid"]).strip() not in eids))
        claims("every position has exactly one tier", n, sum(1 for r in rows if r["tier"] in TIERS))
        claims("check_r1_r5.tsv columns loaded = STMT_COLS only (usecols; the stated-dollar column never in memory)", sorted(STMT_COLS), sorted(L["stmt_cols"]))
        claims("flickers reading LOW on their side facts (the third reading, §2.2)", 130, sum(1 for r in rows if r["flicker"] and r["tier"] == "LOW"))
        claims("same-session round trips in HIGH + MEDIUM (none: the primary holds no same-day trade)", 0, sum(1 for r in prim if hold_bucket(r["hold_sessions_max"]) == "0"))
        claims("primary positions with NO exit look-back defined (hold_sessions_min <= 1; pinned from the file, not an approved count)", 128, none_lb)
        claims("primary rows daily-only on one side / both", (22, 2), (sum(1 for r in prim if r["minute_coverage"] == "one"), sum(1 for r in prim if r["minute_coverage"] == "none")))
        claims("confirmed positions assignable to the groups (a range on both sides)", 47, len(assignable))
        claims("assignable confirmed positions inside the primary fit (HIGH / MEDIUM) / outside it", (33, 14),
               (sum(1 for r in assignable if r["tier"] in ("HIGH", "MEDIUM")), sum(1 for r in assignable if r["tier"] not in ("HIGH", "MEDIUM"))))
        claims("exit feature sets carry no ret_N (both runs)", 0, sum(1 for run in STEP7_FEATURES for c in STEP7_FEATURES[run]["exit"] if c.startswith("ret_")))
        claims("primary feature set carries no our_length column", 0, sum(1 for c in STEP7_FEATURES["primary"]["entry"] + STEP7_FEATURES["primary"]["exit"] if c in OUR_LENGTH))


# ---- pins, gates, main -------------------------------------------------------------------------------------------------------------------
def module_shas_line(files: tuple = MODULE_FILES_7) -> str:
    return " ".join(f"{n} {C.sha(os.path.join(HERE, n))[:16]}" for n in files)


def _sha_or_absent(path: str) -> str:
    return C.sha(path) if os.path.exists(path) else "ABSENT"


def pins_7(doc: str = None, dry_path: str = None) -> dict:
    """Every pin step 7's tiers rest on: step 5's inputs and modules (C.pins without its outputs; `doc_body` = the NEW doc's body), the
    FROZEN steps-5/6 doc body, step 5's three outputs, 6b's modules / printout / per-statement file, this module, the outcome-name list,
    and this stage's dry-run printout. The keys added after C.pins are the ones --run refuses at ABSENT."""
    p = C.pins(doc or DOC7, include_outputs=False)
    p["doc_body_steps56"] = C.doc_body_sha(C.DOC)
    for name, path in C.OUTPUTS.items():
        p[name] = _sha_or_absent(path)
    p["asis_check_common.py"] = _sha_or_absent(os.path.join(HERE, "asis_check_common.py"))
    p["03_check.py"] = _sha_or_absent(os.path.join(HERE, "03_check.py"))
    p["run6b_printout"] = _sha_or_absent(P03_RUN)
    p["check_r1_r5"] = _sha_or_absent(CHECK_R1_R5)
    p["05_tiers.py"] = C.sha(os.path.join(HERE, "05_tiers.py"))
    p["forbidden_outcomes.txt"] = _sha_or_absent(FORBIDDEN_OUTCOMES_FILE)
    p["dryrun7_printout"] = _sha_or_absent(dry_path or P05["dry"])
    return p


def stage_pin_keys(pins: dict, doc: str = None) -> list:
    base = set(C.pins(doc or DOC7, include_outputs=False))
    return [k for k in pins if k not in base]


def run_gate(doc: str = None, paths: dict = None) -> list:
    """The reasons a --run is refused (empty = go): the dry run complete with 0 MISMATCH and made by the modules on disk; every pin
    (incl. both doc bodies and the dry-run printout) below the NEW doc's freeze marker, none ABSENT; the ledger verifying; no output."""
    paths = paths or P05
    doc = doc or DOC7
    problems = []
    if not C.dry_run_complete(paths["dry"]):
        problems.append(f"the step-7 tiers dry run has not completed ({os.path.basename(paths['dry'])})")
    else:
        mm = C.printout_mismatches(paths["dry"])
        if mm is None:
            problems.append("the dry run's RESULT line is missing or unreadable")
        elif mm > 0:
            problems.append(f"the dry run ended with {mm} MISMATCH")
        ml = C.printout_line(paths["dry"], "- modules: ")
        if ml != module_shas_line():
            problems.append("the dry run was made by other code than the modules on disk (or carries no module line): rerun --dry-run first"
                            + (f" (dry run: {ml})" if ml else ""))
    if not os.path.exists(doc):
        problems.append(f"the step-7 registration is missing ({doc})")
        return problems
    pins = pins_7(doc, paths["dry"])
    miss = C.freeze_missing(doc, pins)
    if miss:
        problems.append("pins not below the step-7 doc's freeze marker (freeze first, --print-pins, paste): " + ", ".join(miss))
    absent = [k for k in stage_pin_keys(pins, doc) if pins[k] == "ABSENT"]
    if absent:
        problems.append("pins reading ABSENT (an ABSENT pin passes the freeze check trivially; the file must exist and be pinned): " + ", ".join(absent))
    bad = C.ledger_verify() if os.path.exists(C.LEDGER) else []
    if bad:
        problems.append("ledger: " + "; ".join(bad))
    existing = [q for q in list(OUT_7.values()) + [paths["run"]] if os.path.exists(q)]
    if existing:
        problems.append("outputs exist: " + ", ".join(existing))
    return problems


def forbidden_all() -> frozenset:
    return C.load_forbidden_names() | C.load_forbidden_names(FORBIDDEN_OUTCOMES_FILE)


def write_tsv(rows: list, cols: list, path: str) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    pd.DataFrame(rows, columns=cols).to_csv(path + ".partial", sep="\t", index=False)
    os.replace(path + ".partial", path)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--dry-run", action="store_true")
    g.add_argument("--print-pins", action="store_true")
    g.add_argument("--run", action="store_true")
    a = ap.parse_args(argv)
    if a.print_pins:
        lines = [f"{k}\t{v}" for k, v in pins_7().items()]
        print("\n".join(lines))
        with open(P05["pins"], "w", encoding="utf-8") as fh:
            fh.write("\n".join(lines) + "\n")
        print(f"(written to {P05['pins']})")
        return 0
    say = Say()
    stage = "DRY RUN" if a.dry_run else "RUN"
    say(f"# #711 as-is STEP 7 (part 1, the tiers) — {stage} ({time.strftime('%Y-%m-%d %H:%M')})")
    say("Guards: no network, no production server, no paid call, nothing after 2024-12-31, the seven outcome folders never opened, nothing "
        "imported from the rule folders. No outcome of any trade is read (the outcome-name list is scanned); no rule, setup name or "
        "pattern label enters; the tiers are screen facts only.")
    refused_to = P05["dry"] if a.dry_run else P05["refused"]
    hits = C.scan_identifiers([os.path.join(HERE, n) for n in SCAN_FILES_7], forbidden_all())
    if hits:
        say("IDENTIFIER SCAN FAILED: " + "; ".join(f"{os.path.basename(p)}:{ln} {t}" for p, ln, t in hits))
        say.write(refused_to)
        return 2
    say("- identifier scan: clean (the §3.1 names and the outcome names are absent from the step-7 modules)")
    loaded = C.rule_modules_loaded()
    if loaded:
        say("RULE MODULE LOADED (guard 3): " + ", ".join(loaded))
        say.write(refused_to)
        return 2
    say("- import belt: no rule module in sys.modules")
    say("- modules: " + module_shas_line())
    if a.run:
        problems = run_gate()
        if problems:
            for pr in problems:
                say("REFUSED: " + pr)
            say.write(P05["refused"])
            return 3
        say("- run gates: the dry run completed with 0 MISMATCH; every pin (inputs, modules, both doc bodies, the dry-run printout) is below "
            "the step-7 doc's freeze marker; the ledger verifies; no output exists")
    say("\n## Inputs")
    L = load_inputs(say)
    rows = assign_all(L["ranges"], L["entries"], L["stmts"])
    claims = Claims(say) if a.dry_run else None
    report(L, rows, say, claims)
    if a.dry_run:
        say("")
        say(claims.result())
        say("DRY RUN COMPLETE")
        say.write(P05["dry"])
        return 0
    write_tsv(rows, TIER_COLS, OUT_7["tiers"])
    say("\n## Outputs")
    for k, p in OUT_7.items():
        say(f"- {k}: {p} ({C.sha(p)[:16]})")
    say("RUN COMPLETE")
    say.write(P05["run"])
    C.ledger_append(STAGE_7 + "dry_run", P05["dry"])
    C.ledger_append(STAGE_7 + "tiers_printout", P05["run"])
    for k, p in OUT_7.items():
        C.ledger_append(STAGE_7 + k, p)
    return 0


if __name__ == "__main__":
    sys.exit(main())
