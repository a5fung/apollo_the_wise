#!/usr/bin/env python3
"""STRUCTURE READ v3 — THE STUDY. Does adding "where in the move" let the read EXCLUDE the
operator's junk charts without excluding his real EPs?  ($0 · READ-ONLY · SHADOW ONLY.)

MEASUREMENT ONLY. Nothing is wired, no rule / threshold / toggle / trade state is touched,
and nothing here is a recommendation — every change this implies is the operator's fork
(THE LINE).

⚠ THE TEST IS NOT AUC. Operator, 2026-08-25: *"The first bar I want it to clear is to filter
out the bad charts, like CAPR. I want to make sure we don't trade these poor charts, that's
the first objective."* The v2 backtest already measured the winner-prediction question and
it is a null (0.496 at matched dollar volume, 2,787 name-days). His bar is a PRECISION
question on the reject side, and the answer is a PAIR OF COUNTS:

    (a) how many of the 11 BAD_CHART labels does it reject?
    (b) how many of the 26 must-not-miss real EPs does it WRONGLY reject?

⚠ DECLARED BEFORE ANY COUNT WAS COMPUTED — the pre-registration for this study:
  1. DIRECTION: more prior run-up = worse. Fixed from the mechanism in
     `structure_read_backtest_2026-08-25.md` §6 (four of six CLEAR_AIR collapses had already
     run 77-242%), never from a number seen here.
  2. NO CUTLINE IS PICKED TO FIT THE 11. Every metric is reported as a FULL SWEEP. Exactly
     two distinguished points are quoted, and both are declared here in advance:
       * ANCHOR-75 — the operator-signed `MAX_EXTENSION_PCT` (75.0) carried over unchanged
         to each percent-basis metric. Chosen by HIM, on other evidence, before this study.
         UNFITTED.
       * ANCHOR-EP — the maximum value observed across the 26 must-not-miss real EPs, plus
         epsilon. ⚠ FITTED TO THE MUST-NOT-REJECT SIDE BY CONSTRUCTION: its 0-of-26 count is
         arithmetically forced and is NOT a result. Only its of-11 count carries information.
         Leave-one-out sensitivity is reported so the reader can see how much of it rests on
         a single name.
  3. THE CONTROL IS EXTENSION ALONE. Every composed verdict is reported beside the identical
     cutline applied with NO chart read at all. If the two counts match, the supply read adds
     nothing and that is the finding.
  4. THE OVERLAP IS REPORTED FIRST, NOT LAST. `blocked_by_live_extension_rule` replicates
     `ep_detector.py`'s gate to the line. A new filter that only re-kills what the live gate
     already kills is worth nothing, and that has to be visible before any count is read.

Inputs — all captured ONCE from prod (read-only) by the 08-25 backtest and re-read here,
never re-pulled ($0): `_srbt_bars.psv.gz`, `_srbt_scanlog.psv`, `_srbt_outcomes.psv`,
`_srbt_alerts.psv`.  Output: `_srv3_out.txt` (captured once, read many).
"""
from __future__ import annotations

import gzip
import statistics as st
import sys
from collections import defaultdict
from datetime import date, datetime, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parents[1]))
sys.path.insert(0, str(HERE))

import _structure_read_v3 as V3  # noqa: E402

from tests.fixtures.must_not_miss_eps import MUST_NOT_MISS  # noqa: E402
from tests.fixtures.must_not_trade_charts import (  # noqa: E402
    CHART_RULINGS, MUST_NOT_REJECT_DATES, MUST_NOT_TRADE, POINTED_AT_DATES)

OUT: list[str] = []


def say(s: str = "") -> None:
    print(s)
    OUT.append(s)


def _d(s: str) -> date:
    y, m, dd = s.split("-")
    return date(int(y), int(m), int(dd))


def _f(x):
    try:
        return float(x)
    except (TypeError, ValueError):
        return None


# ══ LOAD ══════════════════════════════════════════════════════════════════════════════
BARS: dict[str, list[dict]] = defaultdict(list)
with gzip.open(HERE / "_srbt_bars.psv.gz", "rt") as fh:
    for ln in fh:
        p = ln.rstrip("\n").split("|")
        if len(p) < 7 or p[3] == "" or p[4] == "":
            continue
        BARS[p[0]].append({"trade_date": _d(p[1]), "open_price": _f(p[2]),
                           "high_price": _f(p[3]), "low_price": _f(p[4]),
                           "close": _f(p[5]), "volume": _f(p[6])})
for t in BARS:
    BARS[t].sort(key=lambda r: r["trade_date"])

SCAN: dict[tuple[str, date], dict] = {}
for ln in (HERE / "_srbt_scanlog.psv").read_text().splitlines():
    p = ln.split("|")
    if len(p) < 20:
        continue
    SCAN[(p[1], _d(p[0]))] = {"filter_reason": p[5], "ep_score": _f(p[6]),
                              "score_tier": p[7]}

OUTC: dict[tuple[str, date], dict] = {}
for ln in (HERE / "_srbt_outcomes.psv").read_text().splitlines():
    p = ln.split("|")
    if len(p) < 17:
        continue
    try:
        lrd = datetime.fromisoformat(p[16].strip())
    except ValueError:
        lrd = None
    o = {"ret_5d": _f(p[12]), "max_high_5d": _f(p[14]), "last_refreshed_at": lrd}
    k = (p[0], _d(p[1]))
    prev = OUTC.get(k)
    if prev is None or (lrd and prev["last_refreshed_at"] and lrd > prev["last_refreshed_at"]):
        OUTC[k] = o

ALERTS: dict[tuple[str, date], dict] = {}
for ln in (HERE / "_srbt_alerts.psv").read_text().splitlines():
    p = ln.split("|")
    if len(p) < 6:
        continue
    ALERTS[(p[0], _d(p[1]))] = {"ep_score": _f(p[2]), "tier": p[3]}


def read(ticker: str, ad: date) -> dict | None:
    bs = BARS.get(ticker, [])
    prior = [b for b in bs if b["trade_date"] < ad]
    same = [b for b in bs if b["trade_date"] == ad]
    if not prior or not same or not same[0]["open_price"]:
        return None
    try:
        r = V3.structure_read_v3(prior, ad, float(same[0]["open_price"]))
    except AssertionError:
        return None
    if r.get("reason"):
        return None
    r["ticker"], r["alert_date"] = ticker, ad
    b20 = prior[-20:]
    dv = [b["close"] * (b["volume"] or 0.0) for b in b20 if b["close"]]
    r["advd20"] = st.median(dv) if len(dv) >= 5 else None
    return r


# ══ THE POPULATIONS ═══════════════════════════════════════════════════════════════════
BAD = [(m.ticker, _d(m.alert_date)) for m in MUST_NOT_TRADE]
GOOD = [(m.ticker, _d(m.alert_date)) for m in MUST_NOT_MISS if not m.excluded]
# ⚠ TWO DIFFERENT THINGS, kept apart. STATED = he called the date good (CAR 04-01).
# POINTED_AT = he referred to it while explaining why the scanned date was wrong (MXL
# 04-24) and never ruled it tradeable. Rejecting a STATED date is a miss against his own
# words; rejecting a POINTED_AT date is a flag worth reporting, not a proven miss.
ANCHORS = ([(t, _d(ds), "STATED") for t, ds, _ in MUST_NOT_REJECT_DATES]
           + [(t, _d(ds), "POINTED_AT") for t, ds, v in POINTED_AT_DATES
              if v == "WRONG_DAY"])

R_BAD = {k: read(*k) for k in BAD}
R_GOOD = {k: read(*k) for k in GOOD}
R_ANCH = {(t, d): read(t, d) for t, d, _ in ANCHORS}

METRICS = ["ext_close_pct_5", "ext_close_pct_10", "ext_close_pct_20", "ext_close_pct_60",
           "runup_low_pct_5", "runup_low_pct_20",
           "runup_adr_5", "runup_adr_20", "pct_of_captured_range"]
PERCENT_BASIS = {"ext_close_pct_5", "ext_close_pct_10", "ext_close_pct_20",
                 "ext_close_pct_60", "runup_low_pct_5", "runup_low_pct_20"}

say("=" * 94)
say("STRUCTURE READ v3 — THE EXCLUSION TEST.  MEASUREMENT ONLY, WIRED INTO NOTHING.")
say(f"generated {datetime.now(timezone.utc).isoformat(timespec='seconds')}  ·  $0, re-read captures")
say("=" * 94)
say(f"populations: {sum(1 for v in R_BAD.values() if v)}/{len(BAD)} BAD_CHART readable · "
    f"{sum(1 for v in R_GOOD.values() if v)}/{len(GOOD)} must-not-miss readable · "
    f"{sum(1 for v in R_ANCH.values() if v)}/{len(ANCHORS)} extra must-not-reject anchors")

# ══ §1 — THE OVERLAP, FIRST ═══════════════════════════════════════════════════════════
say("")
say("§1  THE OVERLAP — what the LIVE stack already does with these 11")
say("-" * 94)
say(f"{'ticker':<7}{'date':<12}{'ext_live%':>10}{'>=75?':>7}  live-stack gate that actually rejected it")
n_ext_blocked = 0
for m in MUST_NOT_TRADE:
    r = R_BAD[(m.ticker, _d(m.alert_date))]
    e = r["extension_live_pct"] if r else None
    blk = bool(r and r["blocked_by_live_extension_rule"])
    n_ext_blocked += blk
    say(f"{m.ticker:<7}{m.alert_date:<12}{(f'{e:.1f}' if e is not None else '-'):>10}"
        f"{('YES' if blk else 'no'):>7}  {m.live_stack_exclusion}")
n_live_rejected = sum(1 for m in MUST_NOT_TRADE if m.live_stack_exclusion)
say("")
say(f"  the LIVE EXTENSION GATE alone (>= {V3.MAX_EXTENSION_PCT}%) already rejects "
    f"{n_ext_blocked} of {len(MUST_NOT_TRADE)}")
say(f"  the LIVE STACK as a whole already rejects {n_live_rejected} of {len(MUST_NOT_TRADE)} "
    f"— none of these 11 was ever admitted or traded")
gmax = max((r["extension_live_pct"] for r in R_GOOD.values()
            if r and r["extension_live_pct"] is not None), default=None)
n_good_blocked = sum(1 for r in R_GOOD.values() if r and r["blocked_by_live_extension_rule"])
say(f"  and it costs {n_good_blocked} of the 26 real EPs "
    f"(their highest extension reading is {gmax:.1f}%, against the {V3.MAX_EXTENSION_PCT}% cap)")


# ══ §2 — THE COUNT PAIR, SWEPT ════════════════════════════════════════════════════════
def counts(metric: str, cut: float, require_clear_air: bool) -> tuple[int, int, list, list]:
    rej_bad, rej_good = [], []
    for k, r in R_BAD.items():
        if r and V3.verdict(r, metric, cut, require_clear_air) == "EXHAUSTED_BLUE_SKY":
            rej_bad.append(k)
    for k, r in R_GOOD.items():
        if r and V3.verdict(r, metric, cut, require_clear_air) == "EXHAUSTED_BLUE_SKY":
            rej_good.append(k)
    return len(rej_bad), len(rej_good), rej_bad, rej_good


def anchor_ep(metric: str, require_clear_air: bool) -> float | None:
    """ANCHOR-EP — max over the must-not-miss arm, + epsilon. FITTED, by construction."""
    vals = [r[metric] for r in R_GOOD.values()
            if r and r.get(metric) is not None
            and (not require_clear_air or V3.is_clear_air(r))]
    if not vals:
        return None
    m = max(vals)
    return m * 1.0001 + 1e-9


say("")
say("§2  THE COUNT PAIR AT THE TWO PRE-DECLARED CUTLINES")
say("-" * 94)
say("    'of 11' = BAD_CHART labels rejected (higher is better).")
say("    'of 26' = must-not-miss real EPs WRONGLY rejected (must be 0 — under-admission is")
say("              invisible and fatal, P14).")
say("    'anchors' = CAR 2026-04-01 (he STATED it was ok'ish) and MXL 2026-04-24 (he only")
say("              POINTED AT it while saying 04-21 was the wrong date). Rejecting the first")
say("              contradicts his words; rejecting the second is a flag, not a proven miss.")
say("")
hdr = (f"{'metric':<22}{'cutline':>10}{'basis':<10}{'composed(of11/of26)':>21}"
       f"{'ext-alone(of11/of26)':>22}  anchors wrongly rejected")
say(hdr)
for metric in METRICS:
    rows = []
    if metric in PERCENT_BASIS:
        rows.append((V3.MAX_EXTENSION_PCT, "ANCHOR-75"))
    ae = anchor_ep(metric, True)
    if ae is not None:
        rows.append((ae, "ANCHOR-EP"))
    for cut, basis in rows:
        cb, cg, _, bad_g = counts(metric, cut, True)
        ab, ag, _, _ = counts(metric, cut, False)
        prov = {(t, d): pv for t, d, pv in ANCHORS}
        anch = [f"{t} {d}[{prov[(t, d)]}]" for (t, d), r in R_ANCH.items()
                if r and V3.verdict(r, metric, cut, True) == "EXHAUSTED_BLUE_SKY"]
        say(f"{metric:<22}{cut:>10.2f}{basis:<10}{f'{cb}/{cg}':>21}{f'{ab}/{ag}':>22}"
            f"  {', '.join(anch) if anch else '(none)'}")

say("")
say("  ⚠ every ANCHOR-EP row's 0-of-26 is ARITHMETICALLY FORCED — the cutline is the 26's own")
say("    maximum. Only its of-11 count is information.")

# the full sweep, so no cutline is hidden
say("")
say("§2b THE FULL SWEEP on the primary metric — the trade-off with nothing chosen")
say("-" * 94)
say(f"{'cutline %':>10}{'of 11':>8}{'of 26':>8}{'anchors lost':>14}   which of the 11")
prim = "ext_close_pct_5"
for cut in [0, 5, 10, 12, 15, 20, 25, 30, 35, 40, 45, 50, 60, 75, 100, 150, 250]:
    cb, cg, bad_k, _ = counts(prim, float(cut), True)
    anch = [t for (t, d), r in R_ANCH.items()
            if r and V3.verdict(r, prim, float(cut), True) == "EXHAUSTED_BLUE_SKY"]
    say(f"{cut:>10}{cb:>8}{cg:>8}{len(anch):>14}   {' '.join(sorted(t for t, _ in bad_k))}")

# leave-one-out on ANCHOR-EP
say("")
say("§2c HOW MUCH OF ANCHOR-EP RESTS ON ONE NAME (leave-one-out over the 26)")
say("-" * 94)
base = anchor_ep(prim, True)
vals = sorted(((r[prim], k) for k, r in R_GOOD.items()
               if r and r.get(prim) is not None and V3.is_clear_air(r)), reverse=True)
say(f"  ANCHOR-EP on {prim} = {base:.2f}% — set by {vals[0][1][0]} {vals[0][1][1]} "
    f"at {vals[0][0]:.2f}%")
say(f"  the clear-air real EPs, most-extended first: "
    f"{', '.join(f'{k[0]} {v:.1f}%' for v, k in vals[:6])}")
loo_b, loo_g, _, _ = counts(prim, vals[1][0] * 1.0001, True)
say(f"  drop that one name and the cutline falls to {vals[1][0]:.2f}% "
    f"-> counts become {loo_b}/11 and {loo_g}/26")

# ══ §3 — WHAT THE SUPPLY READ ADDS BEYOND EXTENSION ALONE ═════════════════════════════
say("")
say("§3  WHAT THE CHART READ ADDS BEYOND THE RUN-UP NUMBER ALONE")
say("-" * 94)
for metric in ("ext_close_pct_5", "ext_close_pct_20"):
    for cut, basis in ((V3.MAX_EXTENSION_PCT, "ANCHOR-75"), (anchor_ep(metric, True), "ANCHOR-EP")):
        cb, cg, kb, _ = counts(metric, cut, True)
        ab, ag, ka, _ = counts(metric, cut, False)
        say(f"  {metric} @ {basis} ({cut:.2f}): composed {cb}/{cg}  ·  extension-alone {ab}/{ag}"
            f"  ·  difference on the 11: {sorted(set(ka) - set(kb))}")
say("")
say("  ⚠ APPLES-TO-APPLES: above, extension-alone is judged at a cutline fitted to the")
say("    CLEAR-AIR real EPs only, which is not its own population. Refitted to all 26:")
for metric in ("ext_close_pct_5", "ext_close_pct_20"):
    cut_a = anchor_ep(metric, False)
    ab, ag, _, _ = counts(metric, cut_a, False)
    cb, cg, _, _ = counts(metric, cut_a, True)
    say(f"    {metric} @ its OWN ANCHOR-EP ({cut_a:.2f}): extension-alone {ab}/{ag}"
        f"  ·  composed at the same cutline {cb}/{cg}")
say("")
say("  the two must-not-reject anchors, both cutlines, composed vs extension-alone:")
for (t, d), r in R_ANCH.items():
    if not r:
        continue
    line = f"    {t} {d}  clear_air={int(bool(r['clear_air']))}  ext5={r['ext_close_pct_5']:.1f}%"
    for cut, basis in ((V3.MAX_EXTENSION_PCT, "75"), (anchor_ep("ext_close_pct_5", True), "EP")):
        c = V3.verdict(r, "ext_close_pct_5", cut, True) == "EXHAUSTED_BLUE_SKY"
        a = V3.verdict(r, "ext_close_pct_5", cut, False) == "EXHAUSTED_BLUE_SKY"
        line += f"  |@{basis}: composed={'REJECT' if c else 'pass'} alone={'REJECT' if a else 'pass'}"
    say(line)

# ══ §4 — THE NATURAL EXPERIMENTS ══════════════════════════════════════════════════════
say("")
say("§4  THE NATURAL EXPERIMENTS — same ticker, opposite operator verdicts")
say("-" * 94)
NAT = [("AEHR", "2026-03-31", "REAL EP (must_not_miss)"), ("AEHR", "2026-08-14", "BAD_CHART"),
       ("CAR", "2026-04-01", "OKISH_EARLIER (he says good)"), ("CAR", "2026-04-21", "BAD_CHART"),
       ("CAR", "2026-04-22", "BAD_CHART"),
       ("MXL", "2026-04-21", "WRONG_DAY (he says the setup is 4/24)"),
       ("MXL", "2026-04-24", "the date he named — MUST NOT REJECT")]
say(f"{'ticker':<6}{'date':<12}{'ext5%':>8}{'ext20%':>9}{'rADR20':>8}{'clear_air':>10}"
    f"{'overhead':>10}{'zones':>7}  operator verdict")
for t, ds, lab in NAT:
    r = read(t, _d(ds))
    if not r:
        say(f"{t:<6}{ds:<12}  unreadable")
        continue
    say(f"{t:<6}{ds:<12}{r['ext_close_pct_5']:>8.1f}{r['ext_close_pct_20']:>9.1f}"
        f"{r['runup_adr_20']:>8.2f}{int(bool(r['clear_air'])):>10}"
        f"{r['overhead_vol_frac']:>10.3f}{r['zones_remaining']:>7}  {lab}")

# ══ §5 — THE COST AT SCALE ════════════════════════════════════════════════════════════
say("")
say("§5  THE COST AT SCALE — what it would exclude across the whole scan cohort")
say("-" * 94)
COHORT: list[tuple[str, date]] = []
seen = set()
for ln in (HERE / "_srbt_scanlog.psv").read_text().splitlines():
    p = ln.split("|")
    if len(p) < 20 or p[5].startswith("filter:universe_"):
        continue
    k = (p[1], _d(p[0]))
    if k in seen:
        continue
    seen.add(k)
    COHORT.append(k)

C_READS = []
for t, ad in COHORT:
    r = read(t, ad)
    if r:
        C_READS.append(r)
days = sorted({r["alert_date"] for r in C_READS})
say(f"  cohort: {len(C_READS)} readable name-days over {len(days)} scan days "
    f"({days[0]} -> {days[-1]}), median {st.median([sum(1 for r in C_READS if r['alert_date'] == d) for d in days]):.0f} names/day")
say("")
say(f"{'metric':<22}{'cutline':>10}{'basis':<11}{'flagged':>9}{'% of cohort':>13}"
    f"{'NEW (not already ext-blocked)':>31}{'per day':>9}")
for metric in ("ext_close_pct_5", "ext_close_pct_20"):
    for cut, basis in ((V3.MAX_EXTENSION_PCT, "ANCHOR-75"),
                       (anchor_ep(metric, True), "ANCHOR-EP")):
        flag = [r for r in C_READS
                if V3.verdict(r, metric, cut, True) == "EXHAUSTED_BLUE_SKY"]
        new = [r for r in flag if not r["blocked_by_live_extension_rule"]]
        say(f"{metric:<22}{cut:>10.2f}{basis:<11}{len(flag):>9}"
            f"{100.0*len(flag)/len(C_READS):>12.1f}%{len(new):>31}{len(new)/len(days):>9.1f}")

# ══ §6 — ON THE NAMES WE ACTUALLY ALERTED ═════════════════════════════════════════════
say("")
say("§6  ON THE NAMES THE LIVE STACK ACTUALLY ADMITTED — where a new filter could bite")
say("-" * 94)
A_READS = []
for (t, ad), a in ALERTS.items():
    r = read(t, ad)
    if r:
        r["tier"] = a["tier"]
        o = OUTC.get((t, ad))
        r["ret_5d"] = o["ret_5d"] if o else None
        r["max_high_5d"] = o["max_high_5d"] if o else None
        A_READS.append(r)
HIGH = [r for r in A_READS if r["tier"] == "HIGH"]
say(f"  {len(A_READS)} alert name-days readable ({len(HIGH)} HIGH). These are the ONLY names")
say("  a new exclusion could actually change, because everything else was already rejected.")
say("")
say(f"{'metric':<22}{'cutline':>10}{'basis':<11}{'HIGH flagged':>14}{'their median 5d':>17}"
    f"{'unflagged median 5d':>21}")
for metric in ("ext_close_pct_5", "ext_close_pct_20"):
    for cut, basis in ((V3.MAX_EXTENSION_PCT, "ANCHOR-75"),
                       (anchor_ep(metric, True), "ANCHOR-EP")):
        fl = [r for r in HIGH
              if V3.verdict(r, metric, cut, True) == "EXHAUSTED_BLUE_SKY"]
        un = [r for r in HIGH if r not in fl]
        mf = [r["ret_5d"] for r in fl if r["ret_5d"] is not None]
        mu = [r["ret_5d"] for r in un if r["ret_5d"] is not None]
        say(f"{metric:<22}{cut:>10.2f}{basis:<11}{len(fl):>14}"
            f"{(f'{100*st.median(mf):+.1f}%' if mf else 'n/a'):>17}"
            f"{(f'{100*st.median(mu):+.1f}%' if mu else 'n/a'):>21}")
say("")
say("  the flagged HIGH alerts, name by name (ANCHOR-EP on ext_close_pct_5):")
cut = anchor_ep("ext_close_pct_5", True)
fl = sorted((r for r in HIGH
             if V3.verdict(r, "ext_close_pct_5", cut, True) == "EXHAUSTED_BLUE_SKY"),
            key=lambda r: (r["ret_5d"] if r["ret_5d"] is not None else 0))
for r in fl:
    say(f"    {r['ticker']:<6}{str(r['alert_date']):<12} ext5={r['ext_close_pct_5']:>7.1f}%  "
        f"5d={(f'{100*r['ret_5d']:+.1f}%' if r['ret_5d'] is not None else 'unsettled'):>10}  "
        f"best_high={(f'{100*r['max_high_5d']:+.1f}%' if r['max_high_5d'] is not None else '-'):>9}")

# ══ §6b — THE UNFITTED RESULT, NAMED ══════════════════════════════════════════════════
say("")
say("§6b THE UNFITTED RESULT — his own 75% cap, read over 20 sessions instead of 5")
say("-" * 94)
for metric in ("ext_close_pct_5", "ext_close_pct_20"):
    cb, cg, kb, _ = counts(metric, V3.MAX_EXTENSION_PCT, True)
    say(f"  {metric} @ {V3.MAX_EXTENSION_PCT}%: {cb}/11 and {cg}/26 -> "
        f"{' '.join(sorted(t for t, _ in kb))}")
b5 = {t for t, _ in counts("ext_close_pct_5", V3.MAX_EXTENSION_PCT, True)[2]}
b20 = counts("ext_close_pct_20", V3.MAX_EXTENSION_PCT, True)[2]
say(f"  the ones the 20-session window adds over the live 5-session gate:")
for t, d in sorted(b20):
    r = R_BAD[(t, d)]
    if r["blocked_by_live_extension_rule"]:
        continue
    say(f"    {t} {d}  5-session {r['ext_close_pct_5']:.1f}%  20-session {r['ext_close_pct_20']:.1f}%"
        f"  (live gate reads {r['extension_live_pct']:.1f}%, under the {V3.MAX_EXTENSION_PCT}% cap)")
g20 = [(r['ticker'], r['ext_close_pct_20']) for r in R_GOOD.values() if r]
g20.sort(key=lambda x: -x[1])
say(f"  headroom on the 26 real EPs: highest 20-session run-up is "
    f"{g20[0][0]} at {g20[0][1]:.1f}%, then {g20[1][0]} {g20[1][1]:.1f}%, {g20[2][0]} {g20[2][1]:.1f}%"
    f" — against the {V3.MAX_EXTENSION_PCT}% cap")
say("  sweep of the 20-session window (composed), so nothing is hidden:")
say(f"{'cutline %':>10}{'of 11':>8}{'of 26':>8}{'anchors lost':>14}")
for cut in [40, 50, 62, 75, 88, 100, 120, 150]:
    cb, cg, _, _ = counts("ext_close_pct_20", float(cut), True)
    na = sum(1 for (t, d), r in R_ANCH.items()
             if r and V3.verdict(r, "ext_close_pct_20", float(cut), True) == "EXHAUSTED_BLUE_SKY")
    say(f"{cut:>10}{cb:>8}{cg:>8}{na:>14}")

# settled-outcome accounting for §6
say("")
say("  SETTLED-OUTCOME ACCOUNTING for the flagged HIGH alerts (the medians above):")
for metric in ("ext_close_pct_5", "ext_close_pct_20"):
    for cut, basis in ((V3.MAX_EXTENSION_PCT, "ANCHOR-75"), (anchor_ep(metric, True), "ANCHOR-EP")):
        fl = [r for r in HIGH if V3.verdict(r, metric, cut, True) == "EXHAUSTED_BLUE_SKY"]
        st_n = sum(1 for r in fl if r["ret_5d"] is not None)
        say(f"    {metric} @ {basis}: {len(fl)} flagged, {st_n} with a settled 5-session outcome")
say(f"  denominator note: {len(HIGH)} HIGH alerts are READABLE here; the 08-25 backtest's 173 is")
say(f"  the count with a SETTLED outcome. Settled here: "
    f"{sum(1 for r in HIGH if r['ret_5d'] is not None)}.")

# ══ §7 — WHICH OF THE 11 THE MECHANISM ACTUALLY EXPLAINS ══════════════════════════════
say("")
say("§7  THE 11 ARE NOT ONE POPULATION — which does the run-up mechanism actually explain?")
say("-" * 94)
say(f"{'ticker':<7}{'date':<12}{'ext5%':>8}{'overhead':>10}{'zones':>7}{'advd20 $':>13}"
    f"  what makes this one junk")
for m in MUST_NOT_TRADE:
    r = R_BAD[(m.ticker, _d(m.alert_date))]
    if not r:
        continue
    e = r["ext_close_pct_5"]
    ov = r["overhead_vol_frac"]
    if r["blocked_by_live_extension_rule"]:
        why = "RUN-UP — and the LIVE 75% gate already rejects it. Nothing new here."
    elif e >= anchor_ep("ext_close_pct_5", True):
        why = "RUN-UP — milder, BELOW the live 75% cap. THIS is the new ground."
    elif ov is not None and ov >= 0.9:
        why = "NOT run-up — buried under its own volume; the v2 supply read sees this one"
    else:
        why = "NOT run-up and NOT buried — junk for reasons no chart read here encodes"
    say(f"{m.ticker:<7}{m.alert_date:<12}{e:>8.1f}{(ov if ov is not None else float('nan')):>10.3f}"
        f"{r['zones_remaining']:>7}{(r['advd20'] or 0):>13,.0f}  {why}")

(HERE / "_srv3_out.txt").write_text("\n".join(OUT) + "\n")
print(f"\nwrote {HERE / '_srv3_out.txt'}", file=sys.stderr)
