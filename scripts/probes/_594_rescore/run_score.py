#!/usr/bin/env python3
"""#594 re-score — STEP 2: score the structure read against ALL of his chart rulings.

LOCAL · $0 · NO NETWORK. Reads `bars.tsv` (written once by `fetch_bars.py`) and the two fixtures;
prints a text report and writes `results.json`. Re-runnable at will.

    python scripts/probes/_594_rescore/run_score.py > scripts/probes/_594_rescore/score_out.txt

MEASUREMENT ONLY. Nothing here changes a rule, threshold, filter or trade behaviour, and nothing
here may be read as a proposal to — any change to admission is his (THE LINE).

PRE-DECLARED BEFORE ANY NUMBER WAS SEEN (2026-10-10), so the 45 labels cannot be used to pick
what to report:

  ARMS (each a rule that REJECTS a name-day; each applied with ONE parameter that already
  existed before this study — no cutline is searched, tuned or added here):
    EXT50     the live extension gate exactly as it runs today: `MAX_EXTENSION_PCT` (50.0,
              imported from the live module) on MIN(close) over the prior 10 calendar days.
    EXT75     the same gate at 75.0 — the value live from 2026-08-22 to 2026-08-28 and the value
              the 2026-08-25 study measured its "extension alone" control under. Shown so that
              study's bar is compared like for like.
    ANCHOR75  the rule the 09-21 and 09-23 re-scores used: `runup_low_pct_20 >= 75.0`
              (his signed 75%, applied to a 20-session run-up). Scored through the COMMITTED
              `score_against_operator_rulings`, unchanged. NB it is an extension-shaped measure:
              it contains none of the supply-ladder read.
    V3READ    the actual chart read: `EXHAUSTED_BLUE_SKY` = supply ladder says nothing overhead
              AND the same 20-session run-up >= 75.0. The only arm that uses the supply read.

  CUTLINE-FREE SEPARATION (so "does the read separate his labels at all" has an answer that is
  not a cutline): the rank statistic AUC = P(a random BAD chart reads worse than a random
  APPROVED chart), ties 0.5, for EXACTLY these four fields, each with "bigger = worse":
  runup_low_pct_20, extension_live_pct, overhead_vol_frac, zones_remaining. 0.50 = no
  separation; below 0.50 = inverted. Hanley-McNeil standard error is printed beside each.
  No other field was looked at.

  THE 35-vs-45 SPLIT uses `ruling_date`: sessions 08-25, 09-06, 09-23 are the 35 that the
  2026-09-23 re-score had; session 10-05 is the 10 new ones. Both are scored off the SAME bars,
  so any difference between them is the rulings and nothing else.
"""
from __future__ import annotations

import importlib.util
import json
import math
import re
import statistics
import sys
from collections import Counter, defaultdict
from datetime import date
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[2]
PROBES = HERE.parent
for p in (str(REPO), str(PROBES)):
    if p not in sys.path:
        sys.path.insert(0, p)

_spec = importlib.util.spec_from_file_location("_structure_read_v3", PROBES / "_structure_read_v3.py")
V3 = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(V3)

from agents.market_intelligence.ep_detector import MAX_EXTENSION_PCT  # noqa: E402
from agents.market_intelligence.rule_eras import admission_era_as_of  # noqa: E402
from tests.fixtures.must_not_miss_eps import MUST_NOT_MISS  # noqa: E402
from tests.fixtures.must_not_trade_charts import (  # noqa: E402
    BAD_CHART, CHART_RULINGS, MUST_NOT_REJECT_DATES, MUST_NOT_TRADE, POINTED_AT_DATES)

BARS = HERE / "bars.tsv"
OLD_SESSIONS = frozenset({"2026-08-25", "2026-09-06", "2026-09-23"})   # the 35
NEW_SESSIONS = frozenset({"2026-10-05"})                                # the 10
EXT_CAP_75_FROM, EXT_CAP_75_TO = date(2026, 8, 22), date(2026, 8, 29)   # live at 75: [from, to)
THIRTEEN_MONTH_FLOOR = date(2025, 8, 1)   # what the 09-23 pull reached — for the parity table only
AUC_FIELDS = ("runup_low_pct_20", "extension_live_pct", "overhead_vol_frac", "zones_remaining")


# ── bars ──────────────────────────────────────────────────────────────────────────────
def load_bars() -> tuple[dict[str, list[dict]], dict]:
    by: dict[str, list[dict]] = defaultdict(list)
    dropped_null = 0
    total = 0
    for line in BARS.read_text().splitlines()[1:]:
        if not line or line.startswith("("):
            continue
        t, d, o, h, l, c, v = line.split("\t")
        total += 1
        if not (o and h and l and c):
            dropped_null += 1      # a bar with a null OHLC cannot enter the read; counted, not hidden
            continue
        by[t].append({"trade_date": date.fromisoformat(d), "open_price": float(o),
                      "high_price": float(h), "low_price": float(l), "close": float(c),
                      "volume": float(v) if v else 0.0})
    for t in by:
        by[t].sort(key=lambda r: r["trade_date"])
    return by, {"rows": total, "dropped_null_ohlc": dropped_null, "tickers": len(by)}


BAR_DATA, BAR_META = load_bars()


def load_alert_state() -> dict[tuple[str, str], str]:
    """(ticker, date) -> 'HIGH' | 'MODERATE' (any HIGH row wins). Absent = no alert row at all."""
    f = HERE / "alerts.tsv"
    st: dict[tuple[str, str], str] = {}
    for line in f.read_text().splitlines()[1:]:
        if not line or line.startswith("("):
            continue
        t, d, tier, *_ = line.split("\t")
        if st.get((t, d)) != "HIGH":
            st[(t, d)] = "HIGH" if tier == "HIGH" else "MODERATE"
    return st


def _alert_row(tk: str, d: date) -> dict | None:
    for b in BAR_DATA.get(tk, ()):
        if b["trade_date"] == d:
            return b
    return None


_cache: dict[tuple[str, str, str], dict | None] = {}


def make_read_for(since: date | None = None):
    """read_for(ticker, iso) -> the v3 read, or None when the alert-day row is missing.

    Prior bars are STRICTLY before the alert date (v2 asserts it); the alert-day OPEN is the only
    thing read from the alert day — known at 09:30, which is when admission decides."""
    def read_for(tk: str, iso: str) -> dict | None:
        key = (tk, iso, str(since))
        if key in _cache:
            return _cache[key]
        d = date.fromisoformat(iso)
        row = _alert_row(tk, d)
        if row is None:
            _cache[key] = None
            return None
        prior = [b for b in BAR_DATA[tk] if b["trade_date"] < d and (since is None or b["trade_date"] >= since)]
        out = V3.structure_read_v3(prior, d, row["open_price"])
        _cache[key] = out
        return out
    return read_for


read_for = make_read_for()
read_for_13m = make_read_for(THIRTEEN_MONTH_FLOOR)


# ── arms ──────────────────────────────────────────────────────────────────────────────
def arm_ext50(r):
    e = (r or {}).get("extension_live_pct")
    return None if e is None else bool(e >= MAX_EXTENSION_PCT)


def arm_ext75(r):
    e = (r or {}).get("extension_live_pct")
    return None if e is None else bool(e >= 75.0)


def arm_anchor75(r):
    return V3.anchor75_rejects(r)


def arm_v3read(r):
    if not r:
        return None
    v = V3.verdict(r, V3.ANCHOR_75_METRIC, V3.ANCHOR_75_CUTLINE)   # require_clear_air=True
    return None if v == "UNREADABLE" else (v == "EXHAUSTED_BLUE_SKY")


ARMS = {"EXT50": arm_ext50, "EXT75": arm_ext75, "ANCHOR75": arm_anchor75, "V3READ": arm_v3read}


def tally(pairs, arm, rf=read_for):
    """pairs: [(ticker, iso, *tag)] -> (rejected, kept, unreadable) lists of the same tuples."""
    rej, kept, unread = [], [], []
    for tk, d, *rest in pairs:
        got = arm(rf(tk, d))
        (unread if got is None else rej if got else kept).append((tk, d, *rest))
    return rej, kept, unread


def fmt(lst):
    return ", ".join(f"{t} {d[5:]}" for t, d, *_ in lst) or "none"


# ── populations (all DERIVED from the fixtures) ───────────────────────────────────────
ALL45 = [(r.ticker, r.alert_date, r.verdict, r.ruling_date) for r in CHART_RULINGS]
BAD = [(r.ticker, r.alert_date, r.verdict, r.ruling_date) for r in MUST_NOT_TRADE]
APPROVED = [(t, d, v, rd) for (t, d, v), rd in
            ((x, next(r.ruling_date for r in CHART_RULINGS if (r.ticker, r.alert_date) == (x[0], x[1])))
             for x in MUST_NOT_REJECT_DATES)]
OTHER = [(r.ticker, r.alert_date, r.verdict, r.ruling_date) for r in CHART_RULINGS
         if r.verdict != BAD_CHART and (r.ticker, r.alert_date) not in {(a, b) for a, b, *_ in APPROVED}]
POINTED = [(t, d, v) for t, d, v in POINTED_AT_DATES]
EPS = [(m.ticker, m.alert_date) for m in MUST_NOT_MISS if not getattr(m, "excluded", False)]
EPS_EXCL = [(m.ticker, m.alert_date) for m in MUST_NOT_MISS if getattr(m, "excluded", False)]


def sub(lst, sessions):
    return [x for x in lst if x[3] in sessions]


def fwd_ret_20(tk: str, iso: str) -> float | None:
    """20th session AFTER the alert day: close / alert-day open - 1. From stored bars, $0."""
    d = date.fromisoformat(iso)
    rows = BAR_DATA.get(tk, [])
    idx = next((i for i, b in enumerate(rows) if b["trade_date"] == d), None)
    if idx is None or idx + 20 >= len(rows):
        return None
    return rows[idx + 20]["close"] / rows[idx]["open_price"] - 1.0


def auc(bad_x, app_x):
    pairs = [(b, a) for b in bad_x if b is not None for a in app_x if a is not None]
    n1 = sum(1 for b in bad_x if b is not None)
    n2 = sum(1 for a in app_x if a is not None)
    if not pairs:
        return None, None, n1, n2
    s = sum(1.0 if b > a else 0.5 if b == a else 0.0 for b, a in pairs)
    A = s / len(pairs)
    q1, q2 = A / (2 - A), 2 * A * A / (1 + A)
    var = (A * (1 - A) + (n1 - 1) * (q1 - A * A) + (n2 - 1) * (q2 - A * A)) / (n1 * n2)
    return A, math.sqrt(max(var, 0.0)), n1, n2


def med(xs):
    xs = [x for x in xs if x is not None]
    return statistics.median(xs) if xs else None


def main() -> None:
    R: dict = {}
    P = print

    # ── 0. POPULATION — composition first ─────────────────────────────────────────────
    P("=" * 100)
    P("0. POPULATION (derived from the fixtures)")
    P("=" * 100)
    by_v = Counter(r.verdict for r in CHART_RULINGS)
    by_s = Counter(r.ruling_date for r in CHART_RULINGS)
    P(f"rulings: {len(CHART_RULINGS)}  by verdict: {dict(by_v)}")
    P(f"by session: {dict(sorted(by_s.items()))}")
    P(f"ruled-date range: {min(r.alert_date for r in CHART_RULINGS)} -> {max(r.alert_date for r in CHART_RULINGS)}")
    P(f"  bad {len(BAD)} | approved {len(APPROVED)} | other {len(OTHER)} | pointed-at {len(POINTED)}"
      f"  (sum of first three = {len(BAD) + len(APPROVED) + len(OTHER)})")
    P(f"  approved split: {dict(Counter(v for _, _, v, _ in APPROVED))}")
    P(f"  other: {[(t, d[5:], v) for t, d, v, _ in OTHER]}")
    P(f"  pointed-at: {[(t, d[5:], v) for t, d, v in POINTED]}")
    P(f"  OLD (35): {len(sub(ALL45, OLD_SESSIONS))}  bad {len(sub(BAD, OLD_SESSIONS))} approved {len(sub(APPROVED, OLD_SESSIONS))}"
      f"   NEW (10): {len(sub(ALL45, NEW_SESSIONS))}  bad {len(sub(BAD, NEW_SESSIONS))} approved {len(sub(APPROVED, NEW_SESSIONS))}"
      f" other {len(sub(OTHER, NEW_SESSIONS))}")
    lab = Counter(("operator" if m.label_source == "operator" else "evidence-selected") for m in MUST_NOT_MISS if not m.excluded)
    P(f"real EPs (RULE 0 bar): {len(EPS)} assertable + {len(EPS_EXCL)} excluded {EPS_EXCL};"
      f" dates {min(d for _, d in EPS)} -> {max(d for _, d in EPS)}; label source {dict(lab)}")
    P(f"bars: {BAR_META}; tickers in populations: "
      f"{len({t for t, *_ in ALL45} | {t for t, _ in EPS + EPS_EXCL} | {t for t, *_ in POINTED})}")
    first_bar = min(b['trade_date'] for r in BAR_DATA.values() for b in r[:1])
    last_bar = max(b['trade_date'] for r in BAR_DATA.values() for b in r[-1:])
    P(f"bar date range: {first_bar} -> {last_bar}")
    prior_counts = []
    for tk, d, *_ in ALL45:
        rd = read_for(tk, d)
        prior_counts.append(None if rd is None else rd["n_bars"])
    P(f"prior bars per ruled date: min {min(c for c in prior_counts if c is not None)}, "
      f"median {med(prior_counts)}, thin(<30): {sum(1 for c in prior_counts if c is not None and c < 30)}, "
      f"no alert-day row: {sum(1 for c in prior_counts if c is None)}")

    # era stamps
    eras = Counter(admission_era_as_of(date.fromisoformat(d)) for _, d, *_ in ALL45)
    P(f"admission era of the 45 ruled dates: {dict(eras)}")
    in75 = [(t, d) for t, d, *_ in ALL45 + [(t, d) for t, d in EPS] if EXT_CAP_75_FROM <= date.fromisoformat(d) < EXT_CAP_75_TO]
    P(f"dates (rulings + real EPs) inside the cap-75 window [{EXT_CAP_75_FROM}, {EXT_CAP_75_TO}): {in75 or 'none'}")
    P("exit eras: NOT APPLICABLE — no trade row, fill or exit is read anywhere in this run (bars only).")
    R["population"] = {"rulings": len(CHART_RULINGS), "bad": len(BAD), "approved": len(APPROVED),
                       "other": len(OTHER), "pointed": len(POINTED), "real_eps": len(EPS),
                       "excluded": len(EPS_EXCL), "bars": BAR_META}

    # outcome composition — is the verdict confounded with what happened next?
    P()
    P("0b. WHAT HAPPENED NEXT (20 sessions after the day, close vs the day's open; from stored bars)")
    outs = {"bad": [fwd_ret_20(t, d) for t, d, *_ in BAD], "approved": [fwd_ret_20(t, d) for t, d, *_ in APPROVED],
            "real_eps": [fwd_ret_20(t, d) for t, d in EPS]}
    for k, xs in outs.items():
        ok = [x for x in xs if x is not None]
        P(f"  {k:9s} n={len(ok):2d}/{len(xs):2d}  median {med(ok) * 100:+.0f}%  fell>20%: {sum(1 for x in ok if x <= -0.20)}"
          f"  rose>20%: {sum(1 for x in ok if x >= 0.20)}")
    R["outcomes"] = {k: {"n": sum(1 for x in v if x is not None), "median": med(v)} for k, v in outs.items()}

    # ── 1. HEADLINE through the committed scorer, unchanged ───────────────────────────
    P()
    P("=" * 100)
    P("1. HEADLINE — committed `score_against_operator_rulings` (ANCHOR75), all rulings")
    P("=" * 100)
    S = V3.score_against_operator_rulings(read_for)
    for k, v in S.items():
        P(f"  {k}: {v}")
    R["scorer"] = S

    # ── 2. All four arms on every population ──────────────────────────────────────────
    P()
    P("=" * 100)
    P("2. FOUR ARMS x EVERY POPULATION (rejected / n; unreadable in its own column)")
    P("=" * 100)
    pops = {"real_eps(31)": EPS, "approved(14)": APPROVED, "bad(25)": BAD}
    R["arms"] = {}
    for an, af in ARMS.items():
        row = {}
        for pn, pl in pops.items():
            rej, kept, un = tally(pl, af)
            row[pn] = {"rejected": len(rej), "n": len(pl), "unreadable": len(un),
                       "rejected_names": [f"{t} {d}" for t, d, *_ in rej]}
        R["arms"][an] = row
        P(f"[{an}]")
        for pn, pl in pops.items():
            rej, kept, un = tally(pl, af)
            P(f"   {pn:14s} rejected {len(rej):2d} of {len(pl):2d}   unreadable {len(un)}   -> {fmt(rej)}")
        # the excluded three + the 'other' six + pointed-at, as flags only
        rej, kept, un = tally(EPS_EXCL, af)
        P(f"   excluded EPs   rejected {len(rej)} of {len(EPS_EXCL)} (not part of the bar)  -> {fmt(rej)}")
        rej, kept, un = tally(OTHER, af)
        P(f"   other rulings  rejected {len(rej)} of {len(OTHER)} (scanned date; neutral)  -> {fmt(rej)}")
        rej, kept, un = tally(POINTED, af)
        P(f"   pointed-at     rejected {len(rej)} of {len(POINTED)} (a flag, not a label)  -> {fmt(rej)}")

    # The supply read (and so V3READ) changes with history length — see section 7. Both windows are
    # reported and NEITHER is chosen: the 13-month window is what every earlier #594 number used.
    P()
    P("[V3READ on the 13-month window (2025-08 ->), reported beside the full-history row above]")
    R["v3read_13m"] = {}
    for pn, pl in pops.items():
        rej, kept, un = tally(pl, arm_v3read, rf=read_for_13m)
        R["v3read_13m"][pn] = {"rejected": len(rej), "n": len(pl), "unreadable": len(un)}
        P(f"   {pn:14s} rejected {len(rej):2d} of {len(pl):2d}   unreadable {len(un)}   -> {fmt(rej)}")
    for lab_, sess in (("35 (old)", OLD_SESSIONS), ("10 (new)", NEW_SESSIONS)):
        rej, kept, un = tally(sub(BAD, sess), arm_v3read, rf=read_for_13m)
        P(f"   bad {lab_}: caught {len(rej)} of {len(sub(BAD, sess))}")
    for f in ("overhead_vol_frac", "zones_remaining"):
        bx = [(read_for_13m(t, d) or {}).get(f) for t, d, *_ in BAD]
        ax = [(read_for_13m(t, d) or {}).get(f) for t, d, *_ in APPROVED]
        A, se, n1, n2 = auc(bx, ax)
        P(f"   AUC (45, 13-month window) {f:20s} {A:.2f} (se {se:.2f})")

    # approved split by label under each arm
    P()
    P("   approved dates lost, by his label:")
    for an, af in ARMS.items():
        lost = [x for x in APPROVED if af(read_for(x[0], x[1])) is True]
        P(f"     {an:9s} " + (", ".join(f"{t} {d[5:]} ({v})" for t, d, v, _ in lost) or "none"))

    # ── 3. 35 vs 45 ───────────────────────────────────────────────────────────────────
    P()
    P("=" * 100)
    P("3. THE 35-vs-45 CHANGE — same bars, same rule; only the label set differs")
    P("=" * 100)
    R["split"] = {}
    for an in ("ANCHOR75", "EXT50", "V3READ"):
        af = ARMS[an]
        for lab_, sess in (("35 (old)", OLD_SESSIONS), ("10 (new)", NEW_SESSIONS), ("45 (all)", OLD_SESSIONS | NEW_SESSIONS)):
            b = sub(BAD, sess); a = sub(APPROVED, sess)
            br, _, bu = tally(b, af); ar, _, au = tally(a, af)
            R["split"][f"{an}|{lab_}"] = {"bad_caught": len(br), "bad_n": len(b),
                                          "approved_lost": len(ar), "approved_n": len(a)}
            P(f"  {an:9s} {lab_:9s} bad caught {len(br):2d}/{len(b):2d}"
              f" ({(100 * len(br) / len(b)) if b else 0:3.0f}%)   approved lost {len(ar)}/{len(a)}"
              f"   unreadable {len(bu) + len(au)}   caught: {fmt(br)}   lost: {fmt(ar)}")
    # regression check against the 09-23 doc (reconstructed driver must reproduce it)
    P()
    P("  REGRESSION vs docs/analysis/594_rulings_encoded_2026-09-23.md (ANCHOR75 on the 35, real EPs w/o PENG):")
    b35 = sub(BAD, OLD_SESSIONS); a35 = sub(APPROVED, OLD_SESSIONS)
    br, _, _ = tally(b35, arm_anchor75); ar, _, _ = tally(a35, arm_anchor75)
    pt, _, _ = tally([x for x in POINTED if x[0] != "RXT"], arm_anchor75)   # RXT 05-07 is a session-4 pointer
    eps30 = [e for e in EPS if e != ("PENG", "2026-10-07")]
    er, _, _ = tally(eps30, arm_anchor75)
    checks = [("bad caught", f"{len(br)}/{len(b35)}", "9/21"), ("approved lost", f"{len(ar)}/{len(a35)}", "0/9"),
              ("real EPs lost (30, ex-PENG)", f"{len(er)}/{len(eps30)}", "0/30"),
              ("pointed-at rejected (ex-RXT)", f"{len(pt)}/3", "1/3")]
    for name, got, want in checks:
        P(f"    {name:32s} got {got:6s} expected {want:6s} {'MATCH' if got == want else '*** MISMATCH — ALARM ***'}")
    R["regression"] = [(n, g, w, g == w) for n, g, w in checks]

    # ── 4. cutline-free separation ────────────────────────────────────────────────────
    P()
    P("=" * 100)
    P("4. CUTLINE-FREE SEPARATION — AUC, bad vs approved, 4 pre-declared fields, bigger = worse")
    P("=" * 100)
    R["auc"] = {}
    for lab_, sess in (("35 (old)", OLD_SESSIONS), ("10 (new)", NEW_SESSIONS), ("45 (all)", OLD_SESSIONS | NEW_SESSIONS)):
        b = sub(BAD, sess); a = sub(APPROVED, sess)
        for f in AUC_FIELDS:
            bx = [(read_for(t, d) or {}).get(f) for t, d, *_ in b]
            ax = [(read_for(t, d) or {}).get(f) for t, d, *_ in a]
            A, se, n1, n2 = auc(bx, ax)
            R["auc"][f"{f}|{lab_}"] = {"auc": A, "se": se, "n_bad": n1, "n_app": n2,
                                       "median_bad": med(bx), "median_app": med(ax)}
            P(f"  {lab_:9s} {f:20s} AUC {A:.2f} (se {se:.2f})  n_bad {n1} n_app {n2}"
              f"  median bad {med(bx):.3g} vs approved {med(ax):.3g}")

    # v2 label cross-tab (descriptive)
    P()
    P("  v2 supply label x verdict (descriptive, no threshold):")
    ct: dict[str, Counter] = defaultdict(Counter)
    for grp, pl in (("bad", BAD), ("approved", APPROVED)):
        for t, d, *_ in pl:
            ct[(read_for(t, d) or {}).get("label", "UNREADABLE")][grp] += 1
    for lbl, c in sorted(ct.items()):
        P(f"    {lbl:20s} bad {c['bad']:2d}   approved {c['approved']:2d}")
    R["label_xtab"] = {k: dict(v) for k, v in ct.items()}
    # base rate for context ONLY — a label pattern seen in the table above was found by looking,
    # so it cannot be tested on this table; the real-EP spread says what any future rule built
    # on a label would be standing next to (RULE 0).
    for name, rf in (("13-month window", read_for_13m),):
        ct13: dict[str, Counter] = defaultdict(Counter)
        for grp, pl in (("bad", BAD), ("approved", APPROVED), ("real_eps", EPS)):
            for t, d, *_ in pl:
                ct13[(rf(t, d) or {}).get("label", "UNREADABLE")][grp] += 1
        P(f"  same cross-tab on the {name}, with the 31 real EPs alongside:")
        for lbl, c in sorted(ct13.items()):
            P(f"    {lbl:20s} bad {c['bad']:2d}   approved {c['approved']:2d}   real_eps {c['real_eps']:2d}")
    ct_full: dict[str, Counter] = defaultdict(Counter)
    for t, d in EPS:
        ct_full[(read_for(t, d) or {}).get("label", "UNREADABLE")]["real_eps"] += 1
    P("  real-EP label spread on the FULL history: " + ", ".join(f"{k} {v['real_eps']}" for k, v in sorted(ct_full.items())))

    # ── 5. unique saves / losses of the read beyond the extension gate ────────────────
    P()
    P("=" * 100)
    P("5. WHAT THE READ ADDS BEYOND THE EXTENSION GATE (per-date)")
    P("=" * 100)
    for an in ("ANCHOR75", "V3READ"):
        af = ARMS[an]
        both = [x for x in BAD if arm_ext50(read_for(x[0], x[1])) is True and af(read_for(x[0], x[1])) is True]
        only_read = [x for x in BAD if arm_ext50(read_for(x[0], x[1])) is not True and af(read_for(x[0], x[1])) is True]
        only_ext = [x for x in BAD if arm_ext50(read_for(x[0], x[1])) is True and af(read_for(x[0], x[1])) is not True]
        neither = [x for x in BAD if arm_ext50(read_for(x[0], x[1])) is not True and af(read_for(x[0], x[1])) is not True]
        P(f"  bad charts, EXT50 vs {an}: both {len(both)} | only {an} {len(only_read)} [{fmt(only_read)}]"
          f" | only EXT50 {len(only_ext)} [{fmt(only_ext)}] | neither {len(neither)}")
        R.setdefault("beyond_ext50", {})[an] = {"both": len(both), "only_read": [f"{t} {d}" for t, d, *_ in only_read],
                                                "only_ext": [f"{t} {d}" for t, d, *_ in only_ext], "neither": len(neither)}
    P("  bad charts neither extension arm touches: "
      + fmt([x for x in BAD if arm_ext50(read_for(x[0], x[1])) is not True and arm_anchor75(read_for(x[0], x[1])) is not True]))

    # ── 5b. against what the live system ALREADY did ──────────────────────────────────
    P()
    P("=" * 100)
    P("5b. AGAINST WHAT THE LIVE SYSTEM ALREADY DID — mi_ep_alerts rows on the ruled dates (alerts.tsv)")
    P("=" * 100)
    A_STATE = load_alert_state()
    R["alert_state"] = {}
    for grp, pl in (("bad(25)", BAD), ("approved(14)", APPROVED), ("real_eps(31)", EPS)):
        by_state: dict[str, list] = defaultdict(list)
        for t, d, *_ in pl:
            by_state[A_STATE.get((t, d), "none")].append((t, d))
        P(f"  {grp}: " + "  ".join(f"{s} {len(by_state[s])}" for s in ("HIGH", "MODERATE", "none")))
        for s in ("HIGH", "MODERATE", "none"):
            if not by_state[s]:
                continue
            line = f"    {s:9s} n={len(by_state[s]):2d}  "
            for an in ("EXT50", "ANCHOR75", "V3READ"):
                rej, _, _ = tally(by_state[s], ARMS[an])
                line += f"{an} rejects {len(rej):2d}   "
            P(line + "| " + fmt(by_state[s]))
        R["alert_state"][grp] = {s: [f"{t} {d}" for t, d in v] for s, v in by_state.items()}
    P("  HIGH-tier bad charts and which arm catches each:")
    for t, d, *_ in BAD:
        if A_STATE.get((t, d)) == "HIGH":
            r = read_for(t, d)
            P(f"    {t:5s} {d}  EXT50 {arm_ext50(r)!s:5s} ANCHOR75 {arm_anchor75(r)!s:5s} V3READ {arm_v3read(r)!s:5s}")
    # notes-vs-table disagreement, so the free-text in the fixture is not silently trusted
    note_alerted = re.compile(r"ALERTED HIGH|HIGH-tier alert|score: [\d.]+ HIGH|\d HIGH, catalyst")
    dis = []
    for r in CHART_RULINGS:
        said = bool(note_alerted.search(r.prior_runup_note or ""))
        has_high = A_STATE.get((r.ticker, r.alert_date)) == "HIGH"
        if said != has_high:
            dis.append(f"{r.ticker} {r.alert_date}: note says {'HIGH' if said else 'not HIGH'}, table says {A_STATE.get((r.ticker, r.alert_date), 'no row')}")
    P(f"  fixture free-text vs the table disagree on {len(dis)} of {len(CHART_RULINGS)} rulings: {dis}")

    # ── 6. per-ruling table ───────────────────────────────────────────────────────────
    P()
    P("=" * 100)
    P("6. PER-RULING TABLE (all 45)")
    P("=" * 100)
    P(f"{'ticker':6s} {'date':10s} {'verdict':14s} {'sess':10s} {'ext%':>6s} {'run20%':>7s} {'EXT50':>5s} {'A75':>4s} {'V3':>4s}"
      f" {'label':20s} {'ovhd%':>6s} {'zones':>5s} {'fwd20':>6s} {'era'}")
    rows = []
    for t, d, v, rd in sorted(ALL45, key=lambda x: (x[3], x[2], x[0])):
        r = read_for(t, d) or {}
        fw = fwd_ret_20(t, d)
        flag = lambda b: "-" if b is None else ("REJ" if b else "keep")
        P(f"{t:6s} {d:10s} {v:14s} {rd:10s} {r.get('extension_live_pct') if r.get('extension_live_pct') is None else round(r['extension_live_pct'],1)!s:>6s}"
          f" {r.get('runup_low_pct_20') if r.get('runup_low_pct_20') is None else round(r['runup_low_pct_20'],1)!s:>7s}"
          f" {flag(arm_ext50(r)):>5s} {flag(arm_anchor75(r)):>4s} {flag(arm_v3read(r)):>4s}"
          f" {r.get('label', '-'):20s} {(r.get('overhead_vol_frac') or 0) * 100:6.0f} {r.get('zones_remaining', '-')!s:>5s}"
          f" {('n/a' if fw is None else f'{fw * 100:+.0f}%'):>6s} {admission_era_as_of(date.fromisoformat(d))}")
        rows.append({"ticker": t, "date": d, "verdict": v, "session": rd, "ext": r.get("extension_live_pct"),
                     "run20": r.get("runup_low_pct_20"), "label": r.get("label"), "fwd20": fw})
    R["rows"] = rows

    # pointed-at dates: the values behind the flag
    P()
    P("  POINTED-AT dates (flags, not labels) — the values behind them:")
    for t, d, v in POINTED:
        r = read_for(t, d) or {}
        P(f"    {t:5s} {d} ({v}) ext {r.get('extension_live_pct')!s:.6s}%  run20 {r.get('runup_low_pct_20')!s:.6s}%"
          f"  EXT50 {arm_ext50(r)}  EXT75 {arm_ext75(r)}  ANCHOR75 {arm_anchor75(r)}  V3READ {arm_v3read(r)}  label {r.get('label')}")

    # ── 6b. does his verdict track what happened next? (descriptive; ONE 2x2) ─────────
    P()
    P("=" * 100)
    P("6b. HIS VERDICT vs THE NEXT 20 SESSIONS (bad -> fell? approved -> rose?) — descriptive, selected sample")
    P("=" * 100)
    cells = Counter()
    for grp, pl in (("bad", BAD), ("approved", APPROVED)):
        for t, d, *_ in pl:
            fw = fwd_ret_20(t, d)
            if fw is not None:
                cells[(grp, "fell" if fw < 0 else "rose")] += 1
    a_, b_, c_, d_ = cells[("bad", "fell")], cells[("bad", "rose")], cells[("approved", "fell")], cells[("approved", "rose")]
    n_ = a_ + b_ + c_ + d_
    P(f"  bad: fell {a_}, rose {b_}   approved: fell {c_}, rose {d_}   -> verdict direction matches outcome in {a_ + d_} of {n_}")

    def _hyper(k, K, N, n):   # P(X = k), hypergeometric
        return math.comb(K, k) * math.comb(N - K, n - k) / math.comb(N, n)
    K_, n1_ = a_ + c_, a_ + b_
    p_one = sum(_hyper(k, K_, n_, n1_) for k in range(a_, min(K_, n1_) + 1))
    P(f"  Fisher exact, one-sided P(>= {a_} bad-and-fell | margins) = {p_one:.5f}")
    P("  NB the samples were built from names that collapsed or ran, so labelling at random would match about half;")
    P("  this is NOT a hit rate in the wild.")
    R["verdict_vs_outcome"] = {"bad_fell": a_, "bad_rose": b_, "app_fell": c_, "app_rose": d_, "fisher_p": p_one}
    for an in ("EXT50", "ANCHOR75", "V3READ"):
        af = ARMS[an]
        rej_fell = rej_rose = 0
        for t, d, *_ in BAD + APPROVED:
            fw = fwd_ret_20(t, d)
            if fw is not None and af(read_for(t, d)) is True:
                rej_fell += fw < 0
                rej_rose += fw >= 0
        P(f"  {an:9s} rejects among the labelled: names that fell {rej_fell}, names that rose {rej_rose}")

    # ── 7. parity of the rebuilt driver against numbers stored in the fixture ─────────
    P()
    P("=" * 100)
    P("7. PARITY — this driver against v2_* / extension_live_pct stored in the fixture at label time")
    P("=" * 100)
    stored = [r for r in CHART_RULINGS if r.v2_label is not None]
    P(f"  members carrying stored values: {len(stored)}")
    for name, rf in (("full history (2021-09 ->)", read_for), ("13-month window (2025-08 ->, what 09-23 had)", read_for_13m)):
        m_label = m_ext = m_ovh = m_zon = 0
        drift = []
        for r in stored:
            x = rf(r.ticker, r.alert_date) or {}
            m_label += x.get("label") == r.v2_label
            if x.get("label") != r.v2_label:
                drift.append(f"{r.ticker} {r.alert_date[5:]} LABEL {x.get('label')} vs stored {r.v2_label}")
            if r.extension_live_pct is not None:
                xe = x.get("extension_live_pct")
                m_ext += xe is not None and abs(xe - r.extension_live_pct) < 0.1
            if r.v2_overhead_vol_frac is not None:
                xo = x.get("overhead_vol_frac")
                ok = xo is not None and abs(xo - r.v2_overhead_vol_frac) < 0.005
                m_ovh += ok
                if not ok:
                    drift.append(f"{r.ticker} {r.alert_date[5:]} ovh {xo if xo is None else round(xo, 3)} vs {r.v2_overhead_vol_frac:.3f}")
            if r.v2_zones_remaining is not None:
                ok = x.get("zones_remaining") == r.v2_zones_remaining
                m_zon += ok
                if not ok:
                    drift.append(f"{r.ticker} {r.alert_date[5:]} zones {x.get('zones_remaining')} vs {r.v2_zones_remaining}")
        n_ext = sum(1 for r in stored if r.extension_live_pct is not None)
        n_ovh = sum(1 for r in stored if r.v2_overhead_vol_frac is not None)
        n_zon = sum(1 for r in stored if r.v2_zones_remaining is not None)
        P(f"  [{name}] label {m_label}/{len(stored)} | extension {m_ext}/{n_ext} | overhead_vol_frac {m_ovh}/{n_ovh} | zones {m_zon}/{n_zon}")
        for dline in drift:
            P(f"      drift: {dline}")
        R.setdefault("parity", {})[name] = {"label": [m_label, len(stored)], "ext": [m_ext, n_ext],
                                            "ovh": [m_ovh, n_ovh], "zones": [m_zon, n_zon]}
    # headline invariance across windows
    inv = all(arm(read_for(t, d)) == arm(read_for_13m(t, d)) for arm in (arm_ext50, arm_ext75, arm_anchor75)
              for t, d, *_ in ALL45 + [(t, d) for t, d in EPS])
    P(f"  EXT50/EXT75/ANCHOR75 verdicts identical on full vs 13-month history for every ruled date and real EP: {inv}")
    R["headline_window_invariant"] = inv

    (HERE / "results.json").write_text(json.dumps(R, indent=1, default=str))


if __name__ == "__main__":
    main()
