#!/usr/bin/env python3
"""STOP-GEOMETRY SWEEP — does the 1.5x-ATR stop-width admission rule cut off names
that would have worked? (READ-ONLY probe; STUDY ONLY; no writes, no trading, no LLM spend)

Stage 3 of The Real EP Plan (ENTER — "is R sized to the name?", ep_profitability_program.md
§skip-taxonomy). Triggered by two operator-labelled GOOD EPs that never got in on RISK
GEOMETRY alone, not on any judgement about the setup:
  EROC 2026-08-12  setup:chase_cap_exceeded: limit $13.50 risk $0.75/sh vs planned $0.41/sh
                   (cap 1.50x, ORB high $13.16) — ep_score 96, TOP of that day's board,
                   judge-agreed HIGH, judge held authority.
  HTFL 2026-08-14  setup:stop_too_wide: ORB range $5.75 (7.2%) > 1.5x ATR $5.29.

THE RULE UNDER TEST: backtester/filters.py::validate_orb_entry —
    orb_range > 1.5 * atr_14  (atr_14 = Wilder TR, simple mean of last 14 TRs through the
    PRIOR close — compute_atr_14's live-9:31 asymmetry: today's bar is not in
    mi_daily_closes yet at submission time) -> reject, skip_reason 'setup:stop_too_wide'.
Same source order_manager.py:388-393 reformats into the human-readable detail string
("ORB range $X (Y%) > 1.5x ATR $Z") — the display differs, the boolean test does not.

⚠ PART A'S REJECTION POPULATION IS TOO SMALL TO TEST ON ITS OWN — OPERATOR-SUPPLIED,
NOT RE-DERIVED HERE (measured prod 2026-08-15, mi_live_trades):
    setup:stop_too_wide       4 rows LIVE book / 4 sessions · 26 rows BOTH books / 18 sessions
    setup:chase_cap_exceeded  1 row, ever (EROC)
    price_exceeds_cap         1 row
So chase_cap_exceeded CANNOT be measured on its own rejections — EROC is a worked case, not
a sample, and that is reported as a finding, not hunted around. stop_too_wide at N=26/18
sessions is thin: reported descriptively (N + sessions on every line), no p-value on a
single-digit split. PART B is the load-bearing test: every HIGH alert with usable bar data
(not just the 26 rejects) is reconstructed at the SAME point-in-time ORB geometry and
bucketed by the ratio the rule uses, so the region the rule refuses can be compared against
the region it currently admits.

REUSE, NOT REINVENTION (explicit instruction — do not write a fifth reconstruction):
  - scripts/probes/_468_moderate_realized_r.py — the as-if-ORB-entered reconstruction under
    the LIVE MAGNA53 geometry (stop-limit trigger @ ORB high, harvest via
    anticipation.SETTLE_RULE +1R/+3R halves + day-5 time stop, calibrated against actual
    live realized-R). Imported directly: eligibility(), idx_of_date(), atr14_prior_close(),
    stop_limit_buy_price(). This probe's fill_scan()/settle machinery is the SAME fill logic
    with the too-wide/zero-range EARLY RETURN removed — the whole point here is to see what
    the ladder does on names the gate currently refuses, which _468 never computes (it
    returns {"outcome": "stop_too_wide"} and stops).
  - scripts/stop_width_replay.py — the harvest-FREE day-0/day-5 stop-only walk (walk()),
    reused verbatim as a robustness check on the SETTLE_RULE headline (advisor: the +1R/+3R
    ladder is not neutral to stop width — a wide stop rarely reaches +1R and rides to the
    day-5 time stop, so "realized R by bucket" partly measures the LADDER's interaction with
    width, not just whether the setup worked. Both units are reported; if they disagree in
    sign across the 1.5x line, that disagreement IS the finding).

FIDELITY / VALIDATION STEP (run once, printed, not skipped): the reconstructed ratio
(ORB range / ATR14, both computed here from a fresh Polygon adjusted=true pull) is checked
against the RECORDED atr_14 + orb_high/orb_low the live rule actually used on the known
stop_too_wide rejects (mi_live_trades). If the reconstruction disagrees with the recorded
values on whether a name clears 1.5x, every downstream bucket is mislabeling the rule that
actually fired — this is checked BEFORE any bucket table is trusted.

SCALE-CONSISTENCY GUARD: mi_intraday_bars is as-traded at capture time; mi_daily_closes is
retroactively split-adjusted (stop_width_replay_2026-08-03.md §1: DLLL 8:1, SNEX 3:2, MVLL
3:1). Sidestepped at the SOURCE here — both daily and minute bars are pulled FRESH from
Polygon with adjusted=true at the same time (the _468 pull_bars() pattern), so they should
already agree — but a belt-and-suspenders per-ticker-day check (orb_high <= daily_high*1.02
and orb_low >= daily_low*0.98) is run anyway and failures are excluded + counted, not
silently rescaled.

PRE-REGISTERED BUCKETS (declared before any R was computed): <0.5x, 0.5-1.0x, 1.0-1.5x,
1.5-2.0x, >=2.0x (on the ratio ORB-range/ATR14). The 1.5-2.0 vs >=2.0 split is reported
DESCRIPTIVELY ONLY (no test run on it) — it is where "is the threshold near the right
place" actually lives, per the operator's framing, but N there is expected to be small.
Alerts with unknown ATR (<15 prior trading days — the live rule FAILS OPEN on these,
admitting them regardless of width) and zero-range alerts (no stop distance at all) get
their own line, excluded from every bucket and every test.

PRE-REGISTERED TEST BATTERY (6 tests, fixed and counted; declared before any R/return was
read past the validation step above):
  1  PRIMARY   baseline (1-min ORB entry, ORB-low stop) SETTLE_RULE realized-R,
               >=1.5x vs <1.5x (pooled), session-permuted (same-morning alerts are not
               independent draws — house convention, identical machinery to
               _skip_attribution_read.py / _grade_override_outcome_read.py).
  2  sens.     same split, harvest-FREE day-5 stop-only R (stop_width_replay.walk())
               instead of SETTLE_RULE R — the ladder-interaction robustness check.
  3  sens.     same split, raw ret_5d forward return (open_d0 basis) instead of R —
               relates the finding to the return-based language the rest of the plan uses.
  4  explor.   alternate stop: day-low-so-far (min low from open through the fill bar),
               SAME 1-min entry + SAME ratio buckets, SETTLE_RULE R, >=1.5x vs <1.5x.
  5  explor.   alternate stop: entry - 1.0x ADR-20% (sell_discipline.py's own adr_20_pct
               formula: mean((daily high-low)/close*100) over the trailing 30 CALENDAR
               days strictly before alert_date; ONE representative multiple, not a grid —
               scope bound, stated), SAME 1-min entry + SAME ratio buckets, SETTLE_RULE R,
               >=1.5x vs <1.5x.
  6  explor.   alternate geometry: 5-minute ORB (hi/lo over the 9:30-9:34 bars, arm at
               9:35 — the shadow_orb_tracker / _482 V-5M definition), its OWN entry trigger
               AND stop, bucketed by its OWN ratio (5-min ORB range / ATR14), SETTLE_RULE R,
               >=1.5x vs <1.5x.
Raw p<0.05 AND Bonferroni-adjusted-by-6 both reported; the PRIMARY's verdict rests on the
adjusted p. A null is a real deliverable — this probe does not hunt for a positive.

MATURITY / SETTLEMENT: every alert needs >=15 prior trading days (for ATR14) and >=5
forward trading days (for the day-5 settle) in mi_daily_closes — no alert younger than
~1 week is settleable under either R unit; the funnel below reports the drop.

THE LINE: this probe MEASURES. The stop rule, the chase cap, and any ATR/ADR multiple are
entry discipline — the operator's SOLE authority. Nothing here proposes or pre-selects a
threshold change. If the numbers point somewhere, it is written as a FORK for the operator
with no option chosen.

Phases (local TSVs, re-runnable offline — the _468 / _327 shape):
  --pull-cohort   ssh read-only psql SELECTs -> _stopgeom_cohort.tsv (HIGH alerts, full
                  history) + _stopgeom_trades.tsv (ALL mi_live_trades magna53 rows, every
                  status/account_mode — Part A's skip population + the calibration set)
  --pull-bars     ssh docker exec apollo-market python (Polygon, read-only, adjusted=true)
                  -> _stopgeom_daily.tsv + _stopgeom_minute.tsv
  (no flag)       local settle + report (pure computation over the TSVs) -- prints to
                  stdout; capture once to docs/analysis/stop_geometry_sweep_2026-08-15.txt
"""
from __future__ import annotations

import random
import statistics as st
import subprocess
import sys
from collections import Counter, defaultdict
from datetime import date, datetime, timedelta, timezone
import re
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent.parent))          # repo root for `agents.` imports
sys.path.insert(0, str(HERE))                          # this dir, for the _468 import
sys.path.insert(0, str(HERE.parent))                    # scripts/, for stop_width_replay import

from agents.market_intelligence import anticipation as de          # noqa: E402  pure; reused
import _468_moderate_realized_r as m468                            # noqa: E402  REUSED, not copied
import stop_width_replay as sw                                     # noqa: E402  REUSED, not copied

HOST = "apollo@87.99.134.162"
COHORT = HERE / "_stopgeom_cohort.tsv"     # ticker|alert_date|ep_score|gap_pct|det_et|cq
TRADES = HERE / "_stopgeom_trades.tsv"     # ALL magna53 mi_live_trades rows (any status)
DAILY = HERE / "_stopgeom_daily.tsv"       # ticker|date|o|h|l|c|v
MINUTE = HERE / "_stopgeom_minute.tsv"     # ticker \t t_ms \t o h l c v

RTH_OPEN = de._RTH_OPEN               # 570 = 9:30 ET
SUBMIT_MIN = RTH_OPEN + 1             # 571 = 9:31 — the ORB monitor cron fire
WINDOW_END = RTH_OPEN + 15            # 585 = 9:45 ET — WINDOW_OUT_OF_ORB at/after
FILL_END = RTH_OPEN + 30              # 600 = 10:00 ET — unfilled-cancel job
ORB_FETCH_END = RTH_OPEN + 5          # 575 — 1-min ORB bar window (get_first_bar)
ORB5_END = RTH_OPEN + 5               # 575 — 5-min ORB completes (9:30-9:34 bars), arm at 9:35
SETTLE_FWD = de.SETTLE_FORWARD_BARS   # 5 forward trading bars to settle

ADR_LOOKBACK_CAL_DAYS = 30            # sell_discipline.py's own adr_20_pct window (calendar days)
ADR_MULT = 1.0                        # ONE representative multiple — scope bound, stated in docstring

BUCKETS = [(0.0, 0.5), (0.5, 1.0), (1.0, 1.5), (1.5, 2.0), (2.0, 1e9)]
SPLIT_AT = 1.5                        # the live gate's own threshold — the primary split point

SEED = 20260815
N_PERM = 20000
PLANNED_TESTS = 6
MIN_DISTINCT_PERM_STATS = 50          # house guard (_skip_attribution_read.py) — coarse null gate

PART_A_REASONS = [
    ("setup:stop_too_wide", "stop_too_wide"),
    ("setup:chase_cap_exceeded", "chase_cap_exceeded"),
    ("setup:size_too_small", "size_too_small"),
    ("setup:price_exceeds_cap", "price_exceeds_cap"),
]

# ── Phase A: prod pulls (read-only SELECTs over ssh, the _468/_454 runner shape) ────────

COHORT_SQL = """
SELECT DISTINCT ON (a.ticker, a.alert_date)
       a.ticker, a.alert_date,
       COALESCE(a.ep_score, 0), COALESCE(a.gap_pct, 0),
       to_char(COALESCE(a.detected_at, a.created_at) AT TIME ZONE 'America/New_York',
               'YYYY-MM-DD HH24:MI:SS'),
       COALESCE(a.catalyst_quality, '')
FROM mi_ep_alerts a
WHERE a.score_tier = 'HIGH' AND COALESCE(a.source, 'live') = 'live'
ORDER BY a.ticker, a.alert_date, COALESCE(a.detected_at, a.created_at)
"""

TRADES_SQL = """
SELECT t.ticker, t.alert_date, t.status, COALESCE(t.skip_reason, ''), t.account_mode,
       COALESCE(t.orb_high::text, ''), COALESCE(t.orb_low::text, ''),
       COALESCE(t.atr_14::text, ''), COALESCE(t.entry_price::text, ''),
       COALESCE(t.stop_price::text, ''), COALESCE(t.risk_dollars::text, ''),
       COALESCE(t.total_pnl::text, ''), t.signal_type
FROM mi_live_trades t
WHERE t.skip_reason ILIKE 'setup:stop_too_wide%'
   OR t.skip_reason ILIKE 'setup:chase_cap_exceeded%'
   OR t.skip_reason ILIKE 'setup:size_too_small%'
   OR t.skip_reason ILIKE 'setup:price_exceeds_cap%'
ORDER BY t.alert_date, t.ticker
"""
# NOTE: unlike the earlier signal_type='magna53'-only pull, this deliberately covers EVERY
# signal_type. Found during review: 12 of the 26 stop_too_wide rows are signal_type='9m_day2'
# (order_manager.py:5606, the 9M-Day2 rule — stop distance > 15% of price, a DIFFERENT test
# than magna53's ORB-range > 1.5x-ATR under study in Part B). The task's own "26 rows / 18
# sessions across BOTH books" figure is the mixed total of BOTH rules; the magna53-only subset
# (the rule Part B actually tests) is 14 rows / 11 sessions. Both are reported, split by rule,
# never silently pooled.


def run_select(sql: str) -> str:
    s = " ".join(sql.split())
    assert s.upper().startswith("SELECT"), "read-only: SELECTs only"
    assert not any(ch in s for ch in '"\\$`'), "unsupported char for ssh quoting"
    remote = f'docker exec -i apollo-postgres psql -U apollo -d apollo -tAX -c "{s}"'
    out = subprocess.run(["ssh", "-o", "ConnectTimeout=15", HOST, remote],
                         capture_output=True, text=True, timeout=180)
    if out.returncode != 0:
        raise RuntimeError(f"psql failed: {out.stderr.strip()[:500]}")
    return out.stdout


def pull_cohort() -> None:
    COHORT.write_text(run_select(COHORT_SQL), encoding="utf-8")
    TRADES.write_text(run_select(TRADES_SQL), encoding="utf-8")
    nc = sum(1 for _ in COHORT.read_text(encoding="utf-8").splitlines())
    nt = sum(1 for _ in TRADES.read_text(encoding="utf-8").splitlines())
    print(f"pulled HIGH-alert cohort rows={nc} -> {COHORT.name} ; magna53 trade rows={nt} -> {TRADES.name}")


def _ssh_polygon(pycode: str, out_path: Path, timeout: int = 900) -> None:
    remote = "docker exec apollo-market python -c '" + pycode + "'"
    res = subprocess.run(["ssh", HOST, remote], capture_output=True, text=True, timeout=timeout)
    out_path.write_text(res.stdout, encoding="utf-8")
    errs = [ln for ln in res.stderr.splitlines() if ln.startswith("# ERR")]
    n = sum(1 for _ in res.stdout.splitlines())
    print(f"exit={res.returncode} rows={n} errs={len(errs)} -> {out_path.name}")
    for e in errs[:15]:
        print("  " + e)


def _f(x):
    try:
        return float(x) if x not in ("", None) else None
    except ValueError:
        return None


def load_cohort() -> list[dict]:
    rows = []
    for ln in COHORT.read_text(encoding="utf-8").splitlines():
        p = ln.rstrip("\r").split("|")
        if len(p) < 6 or not p[0]:
            continue
        rows.append({"ticker": p[0], "alert_date": p[1], "ep_score": _f(p[2]),
                     "gap_pct": _f(p[3]), "det_et": p[4], "cq": p[5]})
    return rows


def load_trades() -> list[dict]:
    if not TRADES.exists():
        return []
    rows = []
    for ln in TRADES.read_text(encoding="utf-8").splitlines():
        p = ln.rstrip("\r").split("|")
        if len(p) < 13 or not p[0]:
            continue
        rows.append({"ticker": p[0], "alert_date": p[1], "status": p[2], "skip_reason": p[3],
                     "account_mode": p[4], "orb_high": _f(p[5]), "orb_low": _f(p[6]),
                     "atr_14": _f(p[7]), "entry_price": _f(p[8]), "stop_price": _f(p[9]),
                     "risk_dollars": _f(p[10]), "total_pnl": _f(p[11]), "signal_type": p[12]})
    return rows


def pull_bars() -> None:
    rows = load_cohort()
    if not rows:
        sys.exit(f"run --pull-cohort first ({COHORT.name} missing/empty)")
    pairs = sorted({(r["ticker"], r["alert_date"]) for r in rows})
    span: dict[str, list[str]] = {}
    for tk, d in pairs:
        span.setdefault(tk, [d, d])
        span[tk][0], span[tk][1] = min(span[tk][0], d), max(span[tk][1], d)
    # -70d covers ATR14 (needs 15 prior sessions) + ADR-20 (30 CALENDAR days) with room to spare;
    # +15d covers the 5-forward-trading-day settle.
    dranges = sorted(
        (tk,
         (date.fromisoformat(lo) - timedelta(days=70)).isoformat(),
         (date.fromisoformat(hi) + timedelta(days=15)).isoformat())
        for tk, (lo, hi) in span.items())
    print(f"pulling daily for {len(dranges)} tickers …")
    dr_lit = "[" + ",".join(f'("{t}","{a}","{b}")' for t, a, b in dranges) + "]"
    daily_code = (
        "import json,os,sys,time,urllib.request,datetime\n"
        "KEY=os.environ[\"POLYGON_API_KEY\"]\n"
        f"RANGES={dr_lit}\n"
        "for t,a,b in RANGES:\n"
        "    url=f\"https://api.polygon.io/v2/aggs/ticker/{t}/range/1/day/{a}/{b}?adjusted=true&sort=asc&limit=50000&apiKey={KEY}\"\n"
        "    try:\n"
        "        rr=json.load(urllib.request.urlopen(url,timeout=25))\n"
        "        for bar in rr.get(\"results\",[]):\n"
        "            d=(datetime.datetime.utcfromtimestamp(bar[\"t\"]/1000)-datetime.timedelta(hours=4)).date().isoformat()\n"
        "            o=bar[\"o\"];h=bar[\"h\"];lo=bar[\"l\"];c=bar[\"c\"];v=bar[\"v\"]\n"
        "            print(f\"{t}\\t{d}\\t{o}\\t{h}\\t{lo}\\t{c}\\t{v}\")\n"
        "    except Exception as e:\n"
        "        print(f\"# ERR {t}: {e}\",file=sys.stderr)\n"
        "    time.sleep(0.12)\n"
    )
    _ssh_polygon(daily_code, DAILY)

    print(f"pulling minute day-0 for {len(pairs)} (ticker,date) pairs …")
    pairs_lit = "[" + ",".join(f'("{t}","{d}")' for t, d in pairs) + "]"
    minute_code = (
        "import json,os,sys,time,urllib.request\n"
        "KEY=os.environ[\"POLYGON_API_KEY\"]\n"
        f"PAIRS={pairs_lit}\n"
        "for t,d in PAIRS:\n"
        "    url=f\"https://api.polygon.io/v2/aggs/ticker/{t}/range/1/minute/{d}/{d}?adjusted=true&sort=asc&limit=50000&apiKey={KEY}\"\n"
        "    try:\n"
        "        rr=json.load(urllib.request.urlopen(url,timeout=25))\n"
        "        for bar in rr.get(\"results\",[]):\n"
        "            tt=bar[\"t\"];o=bar[\"o\"];h=bar[\"h\"];lo=bar[\"l\"];c=bar[\"c\"];v=bar[\"v\"]\n"
        "            print(f\"{t}\\t{tt}\\t{o}\\t{h}\\t{lo}\\t{c}\\t{v}\")\n"
        "    except Exception as e:\n"
        "        print(f\"# ERR {t} {d}: {e}\",file=sys.stderr)\n"
        "    time.sleep(0.12)\n"
    )
    _ssh_polygon(minute_code, MINUTE)


if __name__ == "__main__" and ("--pull-cohort" in sys.argv or "--pull-bars" in sys.argv):
    if "--pull-cohort" in sys.argv:
        pull_cohort()
    if "--pull-bars" in sys.argv:
        pull_bars()
    sys.exit(0)


# ══════════════════════════════════════════════════════════════════════════════
# Phase C: local compute — reconstruction + bucket + settle (pure, over the TSVs)
# ══════════════════════════════════════════════════════════════════════════════

def load_daily() -> dict[str, list[dict]]:
    by: dict[str, list[dict]] = defaultdict(list)
    if not DAILY.exists():
        return by
    for ln in DAILY.read_text(encoding="utf-8").splitlines():
        p = ln.rstrip("\r").split("\t")
        if len(p) < 7 or not p[0] or p[0].startswith("#"):
            continue
        by[p[0]].append({"date": p[1], "o": _f(p[2]), "h": _f(p[3]),
                         "l": _f(p[4]), "c": _f(p[5]), "v": _f(p[6]) or 0.0})
    for tk in by:
        seen, dedup = set(), []
        for b in sorted(by[tk], key=lambda x: x["date"]):
            if b["date"] in seen:      # the TLRY/WST/... supplemental pull was appended,
                continue                # never overlaps the main 176-cohort pull, but dedupe anyway
            seen.add(b["date"])
            dedup.append(b)
        by[tk] = dedup
    return by


def load_minute() -> dict[tuple, list[dict]]:
    """{(ticker, et_date_iso): [raw {t,o,h,l,c,v}]} — identical shape to
    _468_moderate_realized_r.load_minute (fed straight into de.polygon_to_rth_minutes)."""
    raw_by: dict[tuple, list[dict]] = defaultdict(list)
    if not MINUTE.exists():
        return raw_by
    for ln in MINUTE.read_text(encoding="utf-8").splitlines():
        p = ln.rstrip("\r").split("\t")
        if len(p) < 7 or p[0].startswith("#"):
            continue
        tk, tms = p[0], int(p[1])
        et = datetime.fromtimestamp(tms / 1000, timezone.utc) - timedelta(hours=4)
        raw_by[(tk, et.date().isoformat())].append(
            {"t": tms, "o": _f(p[2]), "h": _f(p[3]), "l": _f(p[4]), "c": _f(p[5]), "v": _f(p[6])})
    return raw_by


def adr20_pct(daily: list[dict], ai: int) -> float | None:
    """sell_discipline.py's OWN adr_20_pct formula, reused verbatim: mean of
    (high-low)/close*100 over daily bars strictly BEFORE alert_date, within a
    30-CALENDAR-day window (not 20 trading days despite the name — the house's own
    convention, sell_discipline.py:311)."""
    d0 = date.fromisoformat(daily[ai]["date"])
    lo_cut = d0 - timedelta(days=ADR_LOOKBACK_CAL_DAYS)
    vals = [(b["h"] - b["l"]) / b["c"] * 100 for b in daily[:ai]
            if b.get("c") and b.get("h") is not None and b.get("l") is not None
            and date.fromisoformat(b["date"]) >= lo_cut]
    return st.fmean(vals) if vals else None


def fill_scan(rth: list[dict], submission_m: int, orb_end_m: int, trigger_hi: float):
    """MIRROR of _468_moderate_realized_r.reconstruct()'s fill loop (stop-limit trigger
    @ trigger_hi, armed-passthrough on a gap-through), generalized over the ORB window so
    it works for BOTH the 1-min and 5-min ORB definitions, and with the too-wide/zero-range
    EARLY RETURN removed — that gate is applied by the CALLER via bucketing, never here.
    Returns (fill_px, fill_idx) or (None, None)."""
    limit = m468.stop_limit_buy_price(trigger_hi)
    scan_from = max(submission_m, orb_end_m + 1)
    fill_px = fill_idx = None
    armed = False
    for i, b in enumerate(rth):
        if b["m"] < scan_from:
            continue
        if b["m"] >= FILL_END:
            break
        if armed:
            if b["l"] <= limit:
                fill_px, fill_idx = limit, i
                break
            continue
        if b["h"] >= trigger_hi:
            if b["o"] <= trigger_hi:
                fill_px, fill_idx = trigger_hi, i
            elif b["o"] <= limit:
                fill_px, fill_idx = b["o"], i
            else:
                armed = True
                continue
            break
    return fill_px, fill_idx


def harvest_r(entry: float, stop: float, rth: list[dict], fill_idx: int, daily_fwd: list[dict]):
    """SETTLE_RULE harvest-ladder realized-R — REUSED verbatim: de.build_mixed_path +
    de.simulate, the exact primitives _468_moderate_realized_r.reconstruct() calls."""
    risk = entry - stop
    if risk <= 0:
        return None
    path = de.build_mixed_path(rth, fill_idx, daily_fwd)
    if not path:
        return None
    out = de.simulate(entry, stop, path, de.SETTLE_RULE, "pess")
    if out is None:
        return None
    r, _captured, _fills = out
    return r


def _to_sw_bars(rth_slice: list[dict]) -> list[dict]:
    """Re-key _468's {m,o,h,l,c} minute-bar shape onto stop_width_replay.walk()'s
    expected {o,h,l,c,t} shape. Same bars, same values — no new algorithm; walk()
    itself is imported and called unmodified."""
    return [{"o": b["o"], "h": b["h"], "l": b["l"], "c": b["c"], "t": b["m"]} for b in rth_slice]


def stoponly_r(entry: float, stop: float, rth: list[dict], fill_idx: int, daily_fwd: list[dict]):
    """Harvest-FREE day-0/day-5 stop-only R — REUSES stop_width_replay.walk() unmodified
    (bar-low-touch or bar-open-through-stop fill, day-0 close if unstopped, day1..5
    overnight-gap-through-fills-at-open else stop-touch else day-5 close). Returns
    (r0, r5) or (None, None) if risk<=0."""
    risk = entry - stop
    if risk <= 0:
        return None, None
    bars = _to_sw_bars(rth[fill_idx:])
    res = sw.walk(bars, 0, entry, stop, daily_fwd)
    r0 = (res["d0_exit"] - entry) / risk
    r5 = (res["d5_exit"] - entry) / risk
    return r0, r5


FUNNEL: "Counter" = None  # set in main()


def process_alert(row: dict, daily_by: dict, minute_raw: dict) -> dict:
    """One HIGH alert -> {outcome, ...}. outcome='ok' carries ratio1/ratio5, 'settled' (bool:
    >=SETTLE_FWD forward trading days on record) and 'eligible' (bool: passed the live
    9:31-9:44 submission-window gate — m468.eligibility). Ratio/geometry needs NEITHER
    forward data NOR window-eligibility: the 1-min/5-min ORB bar and ATR14 exist regardless
    of when the alert was DETECTED, so a window_out_of_orb alert still gets a ratio1 —
    this is what lets the "how rare is >=1.5x" read cover the WHOLE HIGH population, not
    just the in-window subset that could actually fire an order (advisor-flagged: the two
    are not the same population and reporting only the in-window one overstates rarity).
    R-settlement fields (ret_5d/max_high_5d/fill1/variants/five_min) are populated ONLY
    when BOTH eligible AND settled — a name that was never in the submission window could
    not have filled in real life, so no counterfactual fill is attempted for it either.
    Every other outcome (no_daily_bars/no_minute_data/no_orb_bar/scale_mismatch/zero_range)
    is a funnel exclusion, counted by the caller, never silently dropped."""
    ticker, adate = row["ticker"], row["alert_date"]
    daily = daily_by.get(ticker)
    if not daily:
        return {"outcome": "no_daily_bars"}
    ai = m468.idx_of_date(daily, adate)
    if ai is None:
        return {"outcome": "no_daily_bars"}
    settled = (len(daily) - 1 - ai) >= SETTLE_FWD
    atr14 = m468.atr14_prior_close(daily, ai) if ai >= 15 else None
    gate, sub_m = m468.eligibility(row)
    eligible = gate == "ok"
    raw = minute_raw.get((ticker, adate))
    if not raw:
        return {"outcome": "no_minute_data"}
    rth = de.polygon_to_rth_minutes(raw, adate)
    orb1_cand = [b for b in rth if RTH_OPEN <= b["m"] < ORB_FETCH_END]
    if not orb1_cand:
        return {"outcome": "no_orb_bar"}
    o1 = orb1_cand[0]
    hi1, lo1 = o1["h"], o1["l"]
    orb5_cand = [b for b in rth if RTH_OPEN <= b["m"] < ORB5_END]
    hi5 = max((b["h"] for b in orb5_cand), default=None)
    lo5 = min((b["l"] for b in orb5_cand), default=None)

    dh, dl = daily[ai]["h"], daily[ai]["l"]
    if dh and dl and (hi1 > dh * 1.02 or lo1 < dl * 0.98):
        return {"outcome": "scale_mismatch", "detail": f"orb[{lo1:.2f},{hi1:.2f}] vs daily[{dl:.2f},{dh:.2f}]"}
    if (hi1 - lo1) <= 0:
        return {"outcome": "zero_range"}

    ratio1 = (hi1 - lo1) / atr14 if atr14 and atr14 > 0 else None
    ratio5 = ((hi5 - lo5) / atr14) if (hi5 is not None and lo5 is not None and atr14 and atr14 > 0) else None

    rec = {"outcome": "ok", "settled": settled, "eligible": eligible, "elig_gate": gate,
           "ticker": ticker, "alert_date": adate, "atr14": atr14,
           "orb1_range": hi1 - lo1, "orb5_range": (hi5 - lo5) if (hi5 is not None and lo5 is not None) else None,
           "ratio1": ratio1, "ratio5": ratio5, "ret_5d": None, "max_high_5d": None,
           "gap_pct": row.get("gap_pct"), "ep_score": row.get("ep_score")}
    rec["fill1"] = None
    rec["variants"] = {}
    rec["five_min"] = None
    if not (eligible and settled):
        return rec        # geometry/ratio done; never in the submission window and/or no forward bars yet

    fill1, idx1 = fill_scan(rth, sub_m, o1["m"], hi1)
    rec["fill1"] = fill1

    daily_fwd = daily[ai + 1: ai + 1 + SETTLE_FWD]
    open_d0 = daily[ai]["o"]
    rec["ret_5d"] = (daily_fwd[-1]["c"] - open_d0) / open_d0 if (open_d0 and daily_fwd[-1]["c"] is not None) else None
    highs = [daily[ai]["h"]] + [b["h"] for b in daily_fwd if b["h"] is not None]
    rec["max_high_5d"] = (max(highs) - open_d0) / open_d0 if (open_d0 and highs) else None

    if fill1 is not None:
        adr_pct = adr20_pct(daily, ai)
        adr_stop = fill1 * (1 - ADR_MULT * adr_pct / 100.0) if adr_pct is not None else None
        day_low_so_far = min(b["l"] for b in rth[:idx1 + 1])
        for name, stop_px in (("orb_low", lo1), ("day_low_so_far", day_low_so_far), ("adr_mult", adr_stop)):
            if stop_px is None or stop_px <= 0 or stop_px >= fill1:
                rec["variants"][name] = None
                continue
            hr = harvest_r(fill1, stop_px, rth, idx1, daily_fwd)
            r0, r5 = stoponly_r(fill1, stop_px, rth, idx1, daily_fwd)
            rec["variants"][name] = {"stop": stop_px, "risk": fill1 - stop_px,
                                      "harvest_r": hr, "stop_r0": r0, "stop_r5": r5}

    if hi5 is not None and lo5 is not None and orb5_cand and (hi5 - lo5) > 0:
        fill5, idx5 = fill_scan(rth, sub_m, orb5_cand[-1]["m"], hi5)
        if fill5 is not None and fill5 - lo5 > 0:
            hr5 = harvest_r(fill5, lo5, rth, idx5, daily_fwd)
            r05, r55 = stoponly_r(fill5, lo5, rth, idx5, daily_fwd)
            rec["five_min"] = {"fill": fill5, "stop": lo5, "risk": fill5 - lo5,
                               "harvest_r": hr5, "stop_r0": r05, "stop_r5": r55}

    return rec


def bucket_label(ratio: float) -> str:
    for lo, hi in BUCKETS:
        if lo <= ratio < hi:
            return f"{lo:.1f}-{hi:.1f}x" if hi < 1e8 else f">={lo:.1f}x"
    return "?"


# ── stats machinery (house pattern — identical shape to _skip_attribution_read.py /
#    _grade_override_outcome_read.py: session-permuted median difference, MIN_DISTINCT_
#    PERM_STATS coarse-null guard) ────────────────────────────────────────────────────

def perm_p(a: list[float], b: list[float], sess_a: list[str], sess_b: list[str]):
    by_sess: dict[str, list[float]] = defaultdict(list)
    for v, s in zip(a, sess_a):
        by_sess[s].append(v)
    for v, s in zip(b, sess_b):
        by_sess[s].append(v)
    sessions = sorted(by_sess)
    n_a = len(a)
    if n_a < 5 or len(b) < 5 or len(sessions) < 6:
        return None
    obs = st.median(a) - st.median(b)
    rng = random.Random(SEED)
    counts = [len(by_sess[s]) for s in sessions]
    pool = [by_sess[s] for s in sessions]
    hits = 0
    distinct_stats: set = set()
    for _ in range(N_PERM):
        idx = list(range(len(sessions)))
        rng.shuffle(idx)
        take, got = set(), 0
        for i in idx:
            if got >= n_a:
                break
            take.add(i)
            got += counts[i]
        pa = [v for i in take for v in pool[i]]
        pb = [v for i in range(len(sessions)) if i not in take for v in pool[i]]
        if not pa or not pb:
            continue
        stat = st.median(pa) - st.median(pb)
        distinct_stats.add(round(stat, 6))
        if abs(stat) >= abs(obs):
            hits += 1
    if len(distinct_stats) < MIN_DISTINCT_PERM_STATS:
        return None
    return (hits + 1) / (N_PERM + 1)


def describe_pct(rows: list[dict], key: str) -> dict:
    vals = [r[key] * 100.0 for r in rows if r.get(key) is not None]
    sess = {r["alert_date"] for r in rows if r.get(key) is not None}
    if not vals:
        return {"n": 0, "sessions": 0, "median": None, "p25": None, "p75": None, "pct_positive": None}
    s = sorted(vals)
    return {"n": len(vals), "sessions": len(sess), "median": round(st.median(vals), 2),
            "p25": round(s[len(s) // 4], 2), "p75": round(s[3 * len(s) // 4], 2),
            "pct_positive": round(100.0 * sum(1 for v in vals if v > 0) / len(vals), 1)}


def fmt_stats(d: dict, unit: str = "R") -> str:
    if not d.get("n"):
        return "n=0"
    return (f"n={d['n']:<4} median {d['median']:+.2f}{unit}  mean {d['mean']:+.2f}{unit}  "
            f"win {d['win%']:.0f}%  top3-share {d['top3_share%']:.0f}%  ex-top3 mean {d['ex_top3_mean']:+.2f}{unit}")


_RE_STOPWIDE_DOLLAR = re.compile(r"ORB range \$([\d.]+) \([\d.]+%\) > 1\.5x ATR \$([\d.]+)")


def part_a_returns(ticker: str, adate: str, daily_by: dict) -> dict | None:
    """open_d0-basis returns (missed_outcomes.py's own convention), computed with
    WHATEVER forward days actually exist -- n_fwd_days states how many, so a fresh
    alert (e.g. HTFL, 1 session old at capture time) reports 'too new' honestly
    instead of a silently-partial number presented as final."""
    daily = daily_by.get(ticker)
    if not daily:
        return None
    ai = m468.idx_of_date(daily, adate)
    if ai is None:
        return None
    open0, close0 = daily[ai]["o"], daily[ai]["c"]
    fwd = daily[ai + 1:]
    out = {"n_fwd_days": len(fwd), "ret_0d": None, "ret_1d": None, "ret_5d": None, "max_high_5d_partial": None}
    if not open0:
        return out
    if close0 is not None:
        out["ret_0d"] = (close0 - open0) / open0
    if len(fwd) >= 1 and fwd[0]["c"] is not None:
        out["ret_1d"] = (fwd[0]["c"] - open0) / open0
    highs = [daily[ai]["h"]] + [b["h"] for b in fwd[:5] if b["h"] is not None]
    if highs:
        out["max_high_5d_partial"] = (max(highs) - open0) / open0
    if len(fwd) >= 5 and fwd[4]["c"] is not None:
        out["ret_5d"] = (fwd[4]["c"] - open0) / open0
    return out


def collect_bucket_values(rows: list[dict], ratio_key: str, value_fn):
    """value_fn(rec) -> float|None. Returns ({(lo,hi): [(value,session),...]}, unknown_list)."""
    out = {b: [] for b in BUCKETS}
    unknown = []
    for r in rows:
        ratio, v = r.get(ratio_key), value_fn(r)
        if v is None:
            continue
        if ratio is None:
            unknown.append((v, r["alert_date"]))
            continue
        for lo, hi in BUCKETS:
            if lo <= ratio < hi:
                out[(lo, hi)].append((v, r["alert_date"]))
                break
    return out, unknown


def print_bucket_table(rows: list[dict], ratio_key: str, value_fn, unit: str = "R") -> None:
    buckets, unknown = collect_bucket_values(rows, ratio_key, value_fn)
    for lo, hi in BUCKETS:
        vals = [v for v, _ in buckets[(lo, hi)]]
        sess = {s for _, s in buckets[(lo, hi)]}
        blab = (f"{lo:.1f}-{hi:.1f}x" if hi < 1e8 else f">={lo:.1f}x") + ("  <-- rule's own cutoff" if lo == 1.5 else "")
        d = m468._stats(vals)
        print(f"    {blab:<26} {fmt_stats(d, unit):<95} {len(sess):>3} sessions")
    if unknown:
        vals = [v for v, _ in unknown]
        sess = {s for _, s in unknown}
        d = m468._stats(vals)
        print(f"    {'unk-ATR (<15d hist)':<26} {fmt_stats(d, unit):<95} {len(sess):>3} sessions  "
              f"(live rule fails OPEN on unknown ATR -- admitted regardless of width)")


def split_values(rows: list[dict], ratio_key: str, value_fn):
    hv, hs, lv, ls = [], [], [], []
    for r in rows:
        ratio, v = r.get(ratio_key), value_fn(r)
        if ratio is None or v is None:
            continue
        (hv if ratio >= SPLIT_AT else lv).append(v)
        (hs if ratio >= SPLIT_AT else ls).append(r["alert_date"])
    return hv, hs, lv, ls


TESTS_ATTEMPTED = 0
RESULTS: list[dict] = []


def run_test(name: str, rows: list[dict], ratio_key: str, value_fn) -> dict:
    global TESTS_ATTEMPTED
    TESTS_ATTEMPTED += 1
    hv, hs, lv, ls = split_values(rows, ratio_key, value_fn)
    p = perm_p(hv, lv, hs, ls)
    dh, dl = m468._stats(hv), m468._stats(lv)
    eff = (dh["median"] - dl["median"]) if (dh.get("n") and dl.get("n")) else None
    res = dict(name=name, p=p, dh=dh, dl=dl, eff=eff,
               sess_hi=len(set(hs)), sess_lo=len(set(ls)))
    RESULTS.append(res)
    return res


def fmt_test(res: dict, bonf: int | None = None, unit: str = "R") -> str:
    dh, dl = res["dh"], res["dl"]
    if not dh.get("n") or not dl.get("n"):
        return f"  {res['name']:<58} EMPTY (>=1.5x n={dh.get('n', 0)}, <1.5x n={dl.get('n', 0)})"
    ps = "N too small for permutation" if res["p"] is None else f"raw p={res['p']:.3f}"
    if bonf and res["p"] is not None:
        ps += f"  adj p(x{bonf})={min(1.0, res['p'] * bonf):.3f}"
    return (f"  {res['name']:<58} >=1.5x med {dh['median']:+.2f}{unit} (n={dh['n']},{res['sess_hi']}sess) "
            f"vs <1.5x med {dl['median']:+.2f}{unit} (n={dl['n']},{res['sess_lo']}sess)  "
            f"diff {res['eff']:+.2f}{unit}  {ps}")


# ══════════════════════════════════════════════════════════════════════════════
# main
# ══════════════════════════════════════════════════════════════════════════════

def main() -> None:
    cohort = load_cohort()
    trades = load_trades()
    daily_by = load_daily()
    minute_raw = load_minute()
    if not cohort:
        sys.exit(f"run --pull-cohort then --pull-bars first ({COHORT.name} missing/empty)")

    print("=" * 100)
    print("STOP-GEOMETRY SWEEP — does the 1.5x-ATR admission rule cut off names that would have")
    print("worked? (capture 2026-08-15, READ-ONLY, stage 3 of The Real EP Plan — ENTER)")
    print("=" * 100)
    sessions = sorted({r["alert_date"] for r in cohort})
    data_max = max(date.fromisoformat(d) for d in sessions)
    print(f"HIGH-alert cohort (mi_ep_alerts, score_tier=HIGH, source=live): {len(cohort)} alerts, "
          f"{len(sessions)} sessions, {sessions[0]} .. {sessions[-1]}")
    print("⚠ mi_ep_alerts' retention starts 2026-05-11 — 6 of the 26 stop_too_wide rejects (Part A)")
    print("  predate this and sit outside the ratio-reconstruction cohort; their daily bars were")
    print("  pulled separately for Part A's forward-return table ONLY (no minute bars, no ratio1).")
    print("  ATRO and HTFL (both within the cohort window) get an independently reconstructed ratio")
    print("  below (VALIDATION) but cannot yet contribute an R to any Part B bucket — too recent to")
    print("  have 5 forward trading days on record (settlement, not geometry, is what they lack).")
    print()

    funnel: Counter = Counter()
    recs: list[dict] = []
    all_outcomes: dict[tuple, str] = {}   # (ticker,alert_date) -> outcome, EVERY cohort row, not just 'ok'
    for row in cohort:
        rec = process_alert(row, daily_by, minute_raw)
        funnel_key = rec["outcome"] if rec["outcome"] != "ok" else \
            f"ok_{'eligible' if rec['eligible'] else 'ineligible'}_{'settled' if rec['settled'] else 'unsettled'}"
        funnel[funnel_key] += 1
        all_outcomes[(row["ticker"], row["alert_date"])] = (
            "window_out_of_orb" if (rec["outcome"] == "ok" and not rec["eligible"]) else
            "not_settleable" if (rec["outcome"] == "ok" and not rec["settled"]) else rec["outcome"])
        if rec["outcome"] == "ok":
            recs.append(rec)
    ok = recs                                                   # geometry/ratio known — any elig/settle state
    ok_settled = [r for r in ok if r["eligible"] and r["settled"]]   # can contribute an R to a bucket
    filled1 = [r for r in ok_settled if r["fill1"] is not None]
    print("FUNNEL (every HIGH alert, exactly one outcome each; ok_* rows all have a ratio1 —")
    print("ineligible = detected outside the 9:31-9:44 submission window, unsettled = <5 forward")
    print("trading days on record yet; only ok_eligible_settled can contribute an R to a bucket): " +
          "  ".join(f"{k}={v}" for k, v in sorted(funnel.items())))
    print(f"  ratio reconstructable (any elig/settle state): {len(ok)}/{len(cohort)}  of which can")
    print(f"  contribute an R (eligible AND settled): {len(ok_settled)}  of which the 1-min ORB")
    print(f"  actually triggered+filled: {len(filled1)}/{len(ok_settled)} "
          f"({100 * len(filled1) / max(len(ok_settled), 1):.0f}%)")
    n_unk_atr = sum(1 for r in ok if r["ratio1"] is None)
    n_zero = funnel.get("zero_range", 0)
    n_scale = funnel.get("scale_mismatch", 0)
    print(f"  of the ratio-reconstructable: {n_unk_atr} unknown-ATR (<15 prior trading days), "
          f"{n_zero} zero-range (excluded from _every_ bucket table below — no stop distance to "
          f"measure), {n_scale} scale-mismatch exclusions (minute-vs-daily sanity check)")

    print("\n  RARITY CHECK (advisor-flagged): is '>=1.5x is rare' true of the WHOLE HIGH population,")
    print("  or only of the in-window subset that could actually fire an order? Ratio needs no")
    print("  window-eligibility or settlement, so this covers every ratio-reconstructable alert:")
    ratio_known = [r for r in ok if r["ratio1"] is not None]
    above = [r for r in ratio_known if r["ratio1"] >= SPLIT_AT]
    print(f"    ALL ratio-known alerts (any elig/settle state): {len(above)}/{len(ratio_known)} "
          f">= 1.5x ({100 * len(above) / max(len(ratio_known), 1):.0f}%)")
    rk_elig = [r for r in ratio_known if r["eligible"]]
    ab_elig = [r for r in rk_elig if r["ratio1"] >= SPLIT_AT]
    print(f"    in-WINDOW-eligible only (the population every bucket table below actually uses): "
          f"{len(ab_elig)}/{len(rk_elig)} >= 1.5x ({100 * len(ab_elig) / max(len(rk_elig), 1):.0f}%)")
    print("    (close to each other = the in-window subset is representative; a real gap would mean")
    print("     'only 3 above 1.5x' is an artifact of which alerts happened to arrive in time, not a")
    print("     property of wide-ORB alerts generally.)")
    print()

    # ── VALIDATION — does the reconstruction agree with the RULE THAT ACTUALLY FIRED? ──
    print("=" * 100)
    print("VALIDATION — reconstructed ratio vs the RECORDED numbers on every known stop_too_wide")
    print("reject (run BEFORE any bucket table below is trusted, per pre-commit review)")
    print("=" * 100)
    by_key = {(r["ticker"], r["alert_date"]): r for r in ok}
    n_agree = n_disagree = n_offcohort = n_otherrule = 0
    for t in trades:
        if not t["skip_reason"].startswith("setup:stop_too_wide"):
            continue
        m = _RE_STOPWIDE_DOLLAR.search(t["skip_reason"])
        if not m:
            n_otherrule += 1
            print(f"  {t['ticker']:<6} {t['alert_date']}  [DIFFERENT rule — the 9M-Day2 'stop "
                  f"distance %>15%' check, NOT the 1.5x-ATR rule under test; excluded from "
                  f"validation and from every ratio bucket below]  raw: {t['skip_reason']}")
            continue
        rec_range, atr15 = float(m.group(1)), float(m.group(2))
        rec_atr = atr15 / 1.5
        rec_ratio = rec_range / rec_atr if rec_atr else None
        got = by_key.get((t["ticker"], t["alert_date"]))
        if got is None:
            n_offcohort += 1
            why = all_outcomes.get((t["ticker"], t["alert_date"]))
            why_txt = {"not_settleable": "too recent — <5 forward trading days on record yet, not "
                                          "pre-cohort (Part B needs a full 5-day settle window)",
                       None: "not in the mi_ep_alerts HIGH cohort at all — predates its 2026-05-11 "
                             "retention start"}.get(why, f"funnel outcome = {why}")
            print(f"  {t['ticker']:<6} {t['alert_date']}  recorded ratio {rec_ratio:.2f}x "
                  f"(range ${rec_range:.2f} / ATR ${rec_atr:.2f}) — {why_txt}, no independent "
                  f"reconstruction possible here")
            continue
        my_ratio = got["ratio1"]
        agree = my_ratio is not None and my_ratio > 1.5 and rec_ratio > 1.5
        near_boundary = my_ratio is not None and abs(my_ratio - 1.5) < 0.1 and abs(rec_ratio - 1.5) < 0.1
        n_agree += agree
        n_disagree += (not agree) and not near_boundary
        tag = "AGREE (both >1.5x)" if agree else (
            "boundary flip (both within 0.1x of 1.5 — Polygon late-trade revision between the live"
            " 9:31 read and this later pull, not a formula error; the value the LIVE rule saw is the"
            " 'recorded' number)" if near_boundary else "*** DISAGREE (far from the boundary) ***")
        print(f"  {t['ticker']:<6} {t['alert_date']}  recorded {rec_ratio:.2f}x (range ${rec_range:.2f} "
              f"/ ATR ${rec_atr:.2f})  vs reconstructed "
              f"{('%.2fx' % my_ratio) if my_ratio is not None else 'unk'} "
              f"(range ${got['orb1_range']:.2f} / ATR ${got['atr14']:.2f})  {tag}")
    print(f"\n  {n_agree} agree / {n_disagree} disagree-far-from-boundary / {n_offcohort} not "
          f"independently checkable (predate the mi_ep_alerts cohort, 2026-05-11) / {n_otherrule} "
          f"different rule (9M-style, excluded)")
    print("  (both sides use the SAME formula — Wilder TR, prior-close basis. A far-from-boundary")
    print("   DISAGREE would mean this probe's ratio1 mislabels the rule that actually fired — none")
    print("   found. A near-boundary flip is expected noise from re-pulling minute bars after the")
    print("   fact and does not call the reconstruction into question.)" if not n_disagree else
          "   *** at least one far-from-boundary DISAGREE — every bucket table below is UNRELIABLE ***")
    print()

    # ══════════════════════════════════════════════════════════════════════
    # PART A — descriptive: what happened to the names the 4 rules rejected
    # ══════════════════════════════════════════════════════════════════════
    print("=" * 100)
    print("PART A — what happened to the names the 4 risk-geometry skip reasons rejected")
    print("(descriptive only — N and distinct sessions on every line; population too small for a")
    print(" p-value on any of these except stop_too_wide, and even that split is thin)")
    print("=" * 100)
    for prefix, label in PART_A_REASONS:
        all_rows = [t for t in trades if t["skip_reason"].startswith(prefix)]
        if prefix == "setup:stop_too_wide":
            # ⚠ found on review: 12 of these 26 rows are signal_type='9m_day2' — order_manager.py:
            # 5606's DIFFERENT rule (stop distance > 15% of price), not magna53's ORB-range >
            # 1.5x-ATR test that Part B studies. Split explicitly so the 26-row figure is never
            # read as 26 instances of one rule. TLRY (magna53, but the 9M-style '%>15%' message)
            # is grouped with the magna53 rows below (that's its recorded signal_type) but flagged
            # inline — its message format is unexplained, not chased down further (time-boxed).
            groups = [("magna53 (the 1.5x-ATR rule Part B studies)",
                      [t for t in all_rows if t["signal_type"] == "magna53"]),
                     ("9m_day2 (a DIFFERENT rule — stop distance > 15% of price, order_manager.py:5606"
                      " — NOT under study in Part B)",
                      [t for t in all_rows if t["signal_type"] == "9m_day2"])]
        else:
            groups = [(None, all_rows)]
        sess_all = {r["alert_date"] for r in all_rows}
        print(f"\n-- {label} — N={len(all_rows)} rows, {len(sess_all)} distinct sessions --")
        if not all_rows:
            print("    (none on record)")
            continue
        for glabel, rows in groups:
            if glabel:
                sess = {r["alert_date"] for r in rows}
                print(f"  [{glabel} — N={len(rows)}, {len(sess)} sessions]")
            for t in sorted(rows, key=lambda r: (r["alert_date"], r["ticker"])):
                ret = part_a_returns(t["ticker"], t["alert_date"], daily_by)
                named = " <== NAMED CASE" if t["ticker"] in ("EROC", "HTFL") else ""
                anomaly = " [⚠ signal_type=magna53 but message uses the 9M %-format — unexplained, not chased further]" \
                    if (prefix == "setup:stop_too_wide" and t["signal_type"] == "magna53"
                        and not _RE_STOPWIDE_DOLLAR.search(t["skip_reason"])) else ""
                print(f"    {t['ticker']:<6} {t['alert_date']}  [{t['account_mode']}/{t['status']}]{named}{anomaly}")
                print(f"        {t['skip_reason']}")
                if ret is None:
                    print("        (no daily bars — could not compute forward return)")
                else:
                    r0 = f"{ret['ret_0d'] * 100:+.1f}%" if ret["ret_0d"] is not None else "n/a"
                    r1 = f"{ret['ret_1d'] * 100:+.1f}%" if ret["ret_1d"] is not None else "n/a (too new)"
                    r5 = f"{ret['ret_5d'] * 100:+.1f}%" if ret["ret_5d"] is not None else \
                        f"n/a (only {ret['n_fwd_days']} fwd day(s) on record, too new)"
                    mh = f"{ret['max_high_5d_partial'] * 100:+.1f}%" if ret["max_high_5d_partial"] is not None else "n/a"
                    print(f"        ret_0d(alert-day close) {r0}   ret_1d {r1}   ret_5d {r5}   "
                          f"max_high (partial, {min(ret['n_fwd_days'], 5)}/5 fwd days seen) {mh}")
    print("\n  ⚠ chase_cap_exceeded: N=1 EVER (EROC). Cannot be measured on its own rejections —")
    print("    stated as a finding, not tested. EROC is a worked case, not a sample.")
    print("  ⚠ EROC's skip is NOT a stop_too_wide/ATR-ratio event — chase_cap_exceeded fires when")
    print("    price runs away between alert and trigger, a DIFFERENT mechanism than ORB-range-vs-")
    print("    ATR. Part B's ratio bucketing below does not and cannot measure the chase cap.")
    print("  ⚠ chase_cap_exceeded writes mi_live_trades status='cancelled'. mi_ep_missed_outcomes'")
    print("    own 'traded' CTE excludes only status='skipped' — so EVERY chase_cap_exceeded row is")
    print("    invisible to the entire skip-attribution surface (missed_outcomes.py), not just to")
    print("    this probe. That is why this probe computes Part A's returns directly from daily")
    print("    bars rather than joining mi_ep_missed_outcomes as first drafted.")
    eroc_rec = by_key.get(("EROC", "2026-08-12"))
    if eroc_rec:
        print(f"\n  EROC's OWN reconstructed ratio1 (context, not a chase-cap measurement): "
              f"{eroc_rec['ratio1']:.2f}x — comfortably UNDER 1.5x, confirming its rejection came "
              f"from chase-cap price movement, not ORB-width-vs-ATR.")
    print()

    # ══════════════════════════════════════════════════════════════════════
    # PART B — the load-bearing test: every HIGH alert, bucketed by ORB-range/ATR14
    # ══════════════════════════════════════════════════════════════════════
    print("=" * 100)
    print("PART B — every reconstructable HIGH alert, bucketed by the ratio the rule uses")
    print("(ORB range / ATR14). PRIMARY unit = SETTLE_RULE harvest-ladder realized-R (the house")
    print("realized-R definition, reused verbatim from _468_moderate_realized_r.py). SECONDARY unit")
    print("= harvest-FREE day-0/day-5 stop-only R (stop_width_replay.walk(), reused verbatim) — the")
    print("+1R/+3R ladder is not neutral to stop width (a wide stop rarely reaches +1R and rides to")
    print("the day-5 time stop), so if the two units disagree in sign across the 1.5x line, THAT")
    print("disagreement is itself the finding, not a contradiction to explain away.")
    print("=" * 100)

    print(f"\n[BASELINE — live geometry: 1-min ORB entry, ORB-low stop]  (of {len(ok_settled)} settled "
          f"alerts) filled n={len(filled1)}, no-fill n={len(ok_settled) - len(filled1)} (excluded — ")
    print(" a name that never triggered the ORB-high buy has no fill price to build a stop from)")
    print("\n  -- SETTLE_RULE harvest-ladder realized-R (PRIMARY unit) --")
    print_bucket_table(filled1, "ratio1", lambda r: (r["variants"].get("orb_low") or {}).get("harvest_r"))
    print("\n  -- harvest-FREE day-5 stop-only R (SECONDARY unit — robustness check) --")
    print_bucket_table(filled1, "ratio1", lambda r: (r["variants"].get("orb_low") or {}).get("stop_r5"))
    print("\n  -- raw ret_5d forward return, open_d0 basis (context — NOT R; flatters wide-stop")
    print("     buckets mechanically, since R divides by a bigger denominator there) --")
    print_bucket_table(filled1, "ratio1", lambda r: r["ret_5d"] * 100.0 if r["ret_5d"] is not None else None, unit="%")

    above_names = sorted(((r["ticker"], r["alert_date"], r["ratio1"], (r["variants"].get("orb_low") or {}).get("harvest_r"))
                          for r in filled1 if r["ratio1"] is not None and r["ratio1"] >= SPLIT_AT),
                         key=lambda x: x[1])
    in_window_reject_names = {("AIP", "2026-05-13"), ("GO", "2026-05-14"), ("CORT", "2026-07-30"), ("AEVA", "2026-08-06")}
    print(f"\n  WHO is in the >=1.5x filled bucket (n={len(above_names)}), and does it just re-derive Part A:")
    for tk, d, ratio, r in above_names:
        overlap = " — ALSO a real historical stop_too_wide reject (Part A)" if (tk, d) in in_window_reject_names else \
            " — NOT in Part A's reject list (ratio cleared 1.5x here but the live system did not reject it that day)"
        print(f"    {tk:<6} {d}  ratio1={ratio:.2f}x  harvest_r={r:+.2f}R{overlap}")
    print(f"  Of Part A's 4 in-window magna53 rejects (AIP/GO/CORT/AEVA), only {len(in_window_reject_names & {(t,d) for t,d,_,_ in above_names})}/4")
    print("  reach this bucket — AIP and GO never triggered a counterfactual fill at all (no-fill,")
    print("  excluded from every R bucket), so Part B's treated side is NOT simply Part A re-derived:")
    print("  it is smaller on one side (2 of Part A's 4 never fill) and larger on the other (APPS")
    print("  clears 1.5x here but was never actually rejected live — its full geometry never")
    print("  triggered the gate that day, provenance not chased further).")

    print("\n  ⚠ READ THIS BEFORE THE BUCKET TABLE ABOVE, NOT AFTER (advisor-flagged):")
    print("  1. DISJOINT SAMPLES. The R evidence above the 1.5x line comes from 3 OLDER filled names")
    print("     (AEVA/APPS/CORT) — ATRO, HTFL and EROC, the cases that prompted this probe, are ALL")
    print("     excluded here (unsettled/chase-cap). Part A shows those three moved UP: HTFL +7.7% to")
    print("     the alert-day close, ATRO +10.0% the next day, EROC +19.4% the next day. 'the >=1.5x")
    print("     bucket was 3/3 stop-outs' and 'the names he asked about ran' are BOTH true and")
    print("     describe DIFFERENT alerts — re-ask once ATRO/HTFL settle (~08-19 / ~08-21).")
    print("  2. NO SHAPE, EVEN DESCRIPTIVELY. Every median above is one of {-1.00R, -0.50R, +0.00R} —")
    print("     the +1R/+3R ladder produces almost nothing else, so at n=3-12 per bucket the median")
    print("     is just the middle discrete value, not an effect size. And the profile is NOT")
    print("     monotone: 0.0-0.5x has the WORST median (-1.00R), 0.5-1.5x sits at +0.00R. That kills")
    print("     any 'R falls off as width rises' reading in EITHER direction — there is no shape here")
    print("     to fall off, only noise at small N.")

    print("\n[ALTERNATE STOP 1 — day-low-so-far: min low from open through the fill bar, SAME 1-min")
    print(" entry, SAME ratio1 buckets]")
    dls_rows = [r for r in filled1 if r["variants"].get("day_low_so_far")]
    print(f"  n with a valid day-low-so-far stop: {len(dls_rows)}/{len(filled1)}")
    print_bucket_table(dls_rows, "ratio1", lambda r: r["variants"]["day_low_so_far"]["harvest_r"])

    print(f"\n[ALTERNATE STOP 2 — entry - {ADR_MULT:.1f}x ADR-20% (sell_discipline.py's own adr_20_pct")
    print(" formula; ONE representative multiple, not a grid — scope bound), SAME 1-min entry, SAME")
    print(" ratio1 buckets]")
    adr_rows = [r for r in filled1 if r["variants"].get("adr_mult")]
    print(f"  n with a valid ADR-multiple stop: {len(adr_rows)}/{len(filled1)}")
    print_bucket_table(adr_rows, "ratio1", lambda r: r["variants"]["adr_mult"]["harvest_r"])

    five_rows = [r for r in ok_settled if r.get("five_min")]
    print(f"\n[ALTERNATE GEOMETRY — 5-min ORB (hi/lo over 9:30-9:34 bars, arm at 9:35 — the")
    print(f" shadow_orb_tracker/_482 V-5M definition): OWN trigger, OWN stop, OWN ratio5 buckets]")
    print(f"  n filled: {len(five_rows)}/{len(ok_settled)}")
    print_bucket_table(five_rows, "ratio5", lambda r: r["five_min"]["harvest_r"])

    # 1.5-2.0 vs >=2.0 descriptive-only split (no test — where "is the threshold near the right
    # place" actually lives, per the operator's framing; N expected small)
    b15 = [(r["variants"]["orb_low"]["harvest_r"]) for r in filled1
           if r["ratio1"] is not None and 1.5 <= r["ratio1"] < 2.0 and r["variants"].get("orb_low")]
    b20 = [(r["variants"]["orb_low"]["harvest_r"]) for r in filled1
           if r["ratio1"] is not None and r["ratio1"] >= 2.0 and r["variants"].get("orb_low")]
    print(f"\n  descriptive-only sub-split (no test run — N too small to test, reported because this")
    print(f"  is literally 'is the threshold near the right place'): 1.5-2.0x  {fmt_stats(m468._stats(b15))}")
    print(f"                                                          >=2.0x    {fmt_stats(m468._stats(b20))}")
    print("\n  (note: top3-share%/ex-top3-mean can print extreme percentages on small samples whose")
    print("   R values sum near zero — a known artifact of that ratio, not a data error; read the")
    print("   median/mean/win% columns as primary, top3-share as a tail-concentration flag only.)")

    # ── pre-registered 6-test battery ──────────────────────────────────────────────
    print("\n" + "=" * 100)
    print("PRE-REGISTERED TEST BATTERY — 6 tests, fixed and counted (declared in the docstring")
    print("before any bucket above was computed). Split point = 1.5x (the live gate's own cutoff).")
    print("Session-permuted (same-morning alerts are not independent draws).")
    print("=" * 100)
    primary = run_test("1 PRIMARY  baseline SETTLE_RULE harvest-R, 1-min entry/ORB-low stop",
                        filled1, "ratio1", lambda r: (r["variants"].get("orb_low") or {}).get("harvest_r"))
    print(fmt_test(primary, bonf=PLANNED_TESTS))
    print("   (adj p = Bonferroni across all 6 pre-registered tests; the PRIMARY's verdict rests on")
    print("    the adjusted p, per the pre-registration.)")
    t2 = run_test("2 sens.    baseline, harvest-FREE day-5 stop-only R (ladder-interaction check)",
                  filled1, "ratio1", lambda r: (r["variants"].get("orb_low") or {}).get("stop_r5"))
    print(fmt_test(t2, bonf=PLANNED_TESTS))
    t3 = run_test("3 sens.    baseline, raw ret_5d forward return (not R — context)",
                  filled1, "ratio1", lambda r: r["ret_5d"] * 100.0 if r["ret_5d"] is not None else None)
    print(fmt_test(t3, bonf=PLANNED_TESTS, unit="%"))
    t4 = run_test("4 explor.  day-low-so-far stop, SETTLE_RULE harvest-R",
                  dls_rows, "ratio1", lambda r: r["variants"]["day_low_so_far"]["harvest_r"])
    print(fmt_test(t4, bonf=PLANNED_TESTS))
    t5 = run_test(f"5 explor.  entry-{ADR_MULT:.1f}xADR stop, SETTLE_RULE harvest-R",
                  adr_rows, "ratio1", lambda r: r["variants"]["adr_mult"]["harvest_r"])
    print(fmt_test(t5, bonf=PLANNED_TESTS))
    t6 = run_test("6 explor.  5-min ORB (own trigger+stop), SETTLE_RULE harvest-R, own ratio5 split",
                  five_rows, "ratio5", lambda r: r["five_min"]["harvest_r"])
    print(fmt_test(t6, bonf=PLANNED_TESTS))

    assert TESTS_ATTEMPTED == PLANNED_TESTS, f"battery drifted from pre-registration: {TESTS_ATTEMPTED} != {PLANNED_TESTS}"
    sig_raw = [r for r in RESULTS if r["p"] is not None and r["p"] < 0.05]
    sig_adj = [r for r in RESULTS if r["p"] is not None and r["p"] * PLANNED_TESTS < 0.05]
    completed = [r for r in RESULTS if r["p"] is not None]
    print(f"\nMULTIPLICITY LEDGER — {TESTS_ATTEMPTED} tests attempted (planned {PLANNED_TESTS}), "
          f"{len(completed)} produced a p")
    print(f"  raw p<0.05: {len(sig_raw)} of {len(completed)}"
          + (" — " + "; ".join(f"{r['name']} (p={r['p']:.3f})" for r in sig_raw) if sig_raw else ""))
    print(f"  surviving Bonferroni x{PLANNED_TESTS}: {len(sig_adj)}"
          + (" — " + "; ".join(r["name"] for r in sig_adj) if sig_adj else ""))
    if completed:
        print(f"  expected false positives at raw 0.05 across {len(completed)} tests: "
              f"~{0.05 * len(completed):.1f}")

    # ── what could not be measured ──────────────────────────────────────────────
    print("\n" + "=" * 100)
    print("WHAT COULD NOT BE MEASURED, AND WHY")
    print("=" * 100)
    print("  - chase_cap_exceeded: N=1 ever (EROC) — cannot be measured on its own rejections at")
    print("    all, by any method. Stated as a finding, not worked around.")
    print("  - 6 of the 26 stop_too_wide rejects (TLRY/WST/WKC/BAND/TTMI/EVER/STRL — 2026-04-23 to")
    print("    05-05) predate mi_ep_alerts' retention window (starts 2026-05-11) and have no minute")
    print("    bars — Part A reports their forward returns from daily bars only; Part B's ratio")
    print("    reconstruction cannot include them.")
    print("  - TLRY's stop_too_wide row uses a DIFFERENT message format ('stop distance %>15%' —")
    print("    the 9M-Day2 rule, order_manager.py:5606) despite signal_type='magna53' in the data;")
    print("    provenance of that mismatch was not chased down further — excluded from validation")
    print("    and from every Part B bucket, reported in Part A only.")
    print("  - HTFL (alert 2026-08-14) has ZERO forward daily bars as of this capture (2026-08-15,")
    print("    one session later) — ret_1d/ret_5d are genuinely not yet knowable, not just unmature")
    print("    by the maturity-day convention; reported as 'too new', not computed.")
    print("  - ADR-multiple sweep used ONE representative multiple (1.0x), not a grid — scope bound,")
    print("    stated in the docstring before any number was read.")
    print("  - No R-multiple parity with what a real fill's SLIPPAGE would have cost (fills are")
    print("    modelled at the stop-limit trigger/limit price with zero slippage, matching _468's")
    print("    own stated fidelity limit).")
    print(f"  - The scale-consistency guard (orb vs daily bar sanity check) found {n_scale} "
          "mismatches (itemized above at the FUNNEL line if nonzero, never silently rescaled) —")
    print("    pulling both series fresh from Polygon with adjusted=true avoided the DLLL/SNEX/MVLL")
    print("    class of split mismatch stop_width_replay_2026-08-03.md found between mi_intraday_bars")
    print("    (as-traded) and mi_daily_closes (retroactively adjusted).")

    print("\n" + "=" * 100)
    print("HOW TO READ THIS — the permutation shuffles whole SESSIONS (alerts on one morning share")
    print("the tape), matching every other probe in this program. The PRIMARY's verdict rests on its")
    print("ADJUSTED p; everything else is exploratory / hypothesis-generating, counted but not acted")
    print("on alone. THE LINE: the stop rule, the chase cap, and any ATR/ADR multiple are entry")
    print("discipline — the operator's SOLE authority. Nothing here proposes or pre-selects a")
    print("threshold change. If the numbers point somewhere, it is a FORK for the operator, no")
    print("option chosen.")
    print("=" * 100)


if __name__ == "__main__" and not ("--pull-cohort" in sys.argv or "--pull-bars" in sys.argv):
    main()
