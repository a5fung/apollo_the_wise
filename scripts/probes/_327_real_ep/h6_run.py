"""#327 H6 — the lane's geometry blind spot (20-session cap, first fire per pattern, EP-day anchors only, 15-session
runner label). 2026-10-08. $0, worked ENTIRELY from this folder's captured files + two older local captures of
mi_flag_candidates (no prod access — a read-only pull was refused by the session's permission layer; see FAMILY A).
No prod write, no deploy, no toggle, no table, no PLAN.md line, no live code touched. MEASUREMENT ONLY — stops,
sizing and the live same-day re-entry ban (R3) are his (THE LINE).

THIS DOCSTRING IS THE PRE-REGISTRATION OF RECORD. It was written before any H6 result was computed.

═══════════════════════════ THE BAR (verbatim, docs/analysis/327_hypotheses_2026-09-27.md §2 H6) ═══════════════════════════
  "Pop: ERA A campaigns with 40 (May–Aug) or 60 (May–Jul) sessions. (a) Pass: geometry is the binding blind spot if
   ≥ 10 launches exist and ≥ half start outside every attempt window and Family A coverage; report each by name.
   (c) Pass: keeps ≥ 8 of 11 winner fires with winner mean ≥ +5.5R AND non-winner mean ≥ −0.14R; ERA B same sign,
   open marks separate. Slow-exit cells at s60 must beat the same cell at s20 and stay > 0 after drop-best-two."
  (The doc's VERIFIED section adds nothing that changes H6's bar.)

═══════════════════════════ DATA ═══════════════════════════
  sat_daily_long.tsv (prod mi_daily_closes 2024-01-02..2026-10-05, 256 tickers) is the ONLY daily source. Gate checks
  it equals daily.tsv on the overlap. Per ticker, rows BEFORE the last > 30-calendar-day gap are cut (AKTS, LIFE, FIG
  — a different security on the same symbol); all three gaps end in 2024-2025, before every EP, so the cut only
  touches moving-average warm-up. HORIZON = 2026-10-05 (last bar). fires.tsv (632 first fires), reentry_rows.tsv
  (attempt rows; the incumbent-stop chains are the lane's recorded re-entries), campaigns.tsv / alerts.tsv,
  minute.tsv.gz (fire-day 5-min bars for the day-0 stop test, through the rerun's loaders), summary.json (the 7
  big-runner EPs, read never hand-listed). sat_day0_minutes.tsv.gz is NOT loaded: it holds EP-DAY bars and every
  lane fire is session >= 1, so H6 never needs them.

═══════════════════════════ POPULATION ═══════════════════════════
  Sessions after the EP day are the trading days (production calendar) from ep_date+1 to 10-05. ARM40 = ERA A
  campaigns with >= 40 such sessions; ARM60 = >= 60. The cutoff EP dates are DERIVED from the calendar and printed
  (expected ~08-07 for 40, ~07-09 for 60). Missing bars inside a window are counted; a campaign with a hole inside
  its first 40 sessions is excluded from the census (counted). ERA B (alert >= 08-22): the max sessions available is
  printed; if < 40 every ERA B 40/60-session read is NOT_TESTABLE (said, never imputed). Eras are never pooled.

═══════════════════════════ (a) THE 40-SESSION LAUNCH CENSUS (ARM40) ═══════════════════════════
  Sessions 1..40 after the EP (the EP day itself is excluded: a move from the EP-day low is already lane geometry).
  gain_j = max(high_k, j < k <= 40) / low_j − 1 (the high must come in a LATER session — no intraday ordering
  guess). LAUNCH exists if max_j gain_j >= +50%. PRIMARY start = argmax_j gain_j (the deepest low before the
  biggest high); the earliest j with gain_j >= 50% is reported beside as a sensitivity, never substituted (if the
  primary count is < 10 the earliest-j count does not rescue it). One launch per campaign; unique (ticker, start)
  pairs counted beside (ARM 05-20 / 07-30 can share one).
  ATTEMPT WINDOWS (all "recorded" by the lane): (i) the campaign's own lane window = sessions 1..LANE_SESSIONS (20);
  (ii) the lane window of any OTHER campaign of the same ticker in the 277; (iii) every re-entry watch window of the
  lane's incumbent-stop chains in reentry_rows.tsv (both arms): the 20 sessions after each stop_day (nominal 20,
  not cut at the 09-25 replay horizon). OUTSIDE = the start date is in none of them.
  FAMILY A COVERAGE = a mi_flag_candidates row for the ticker with scan_date in [start − 30 calendar days, start]
  (the 08-16 overlap definition, ep_profitability_program.md). STRICT (primary) = stage in WATCH / TIGHTENING /
  COILED / TRIGGERED; LOOSE (beside) = any row incl. 'unqualified' / 'INVALIDATED'. Sources (local, read-only
  captures): ../_354_stage_history.tsv (ALL tickers, scan dates 05-04..07-24 — prod's own retention floor is 05-04)
  and ../_668_out/cohort_flag_rows.csv (HIGH alerts only, alert+1..+21 calendar days, to 09-23). A row found =
  COVERED. No row and start <= 07-24 = NOT COVERED (the all-ticker capture spans the lookback). No row and start
  > 07-24 = UNKNOWN (no all-ticker capture) — never read as uncovered. Sensitivity window [start − 30d, cross date].
  PASS (a) computed on bounds: LOW = unknowns counted as covered, HIGH = unknowns as uncovered. Launches >= 10 AND
  "outside every window AND not covered" >= half on BOTH bounds -> PASS; < half on both -> FAIL; split -> NOT_TESTABLE.
  Per launch also recorded (descriptive): start session / date, launch low vs EP low and EP close (% and ADR$),
  zone (below EP low / between / above EP close), peak and the session +50% was first reached, which of the four
  patterns had already used their first fire before the start, whether a lane attempt was open at the start or
  fired between start and the +50% cross, and his labelled EPs flagged.
  (b) — only the cheap column: post-EP base high = max high of sessions 1..start; the first later session whose
  CLOSE clears it, whether that is before the +50% cross, and the % left from that close to the peak. Not a scored
  entry, not a fire. That is all of (b).

═══════════════════════════ (c) THE HAND-OFF EXIT + THE SLOW-EXIT CELLS ═══════════════════════════
  Fires = fires.tsv first fires (ERA A 595, ERA B 37), entry and fire minute as recorded (fire minute from
  reentry_rows attempt 1 — the derived touch minute for level fires, so day 0 matches the re-entry study).
  Stops: 1xADR$ (PRIMARY — §D's 8-of-11 / +5.5R / −0.14R figures are 1xADR arms, and the lane's own stop cannot keep
  8 of 11 by §D), incumbent and 0.75xADR beside. Width floor 0.5% (counted, not scored).
  DAY 0 = the lane's own compute_settlement through reentry.settle_attempt with no forward sessions (real post-fire
  5-min bars -> lane-recorded cached excursion -> abstain when the day low reached the stop). One daily WALKER then
  runs sessions 1..K on sat_daily_long, pess per session: low <= stop -> stop (house −1.00R; JUDGED R charges a
  session that OPENED below the stop at the open), else close rules. The first missing daily bar before an exit
  ABSTAINS (never leap a gap). MA lines include the session's own close; trail = the lane's sma_trail_line
  (max SMA10/SMA20, checked from the day-0 close); sma21_2x = two running closes below SMA21 (from session 1);
  sma50_1x / ema65_1x = a close below the 50-SMA / 65-EMA (from day 0); EMA seeded with the SMA of its first 65
  closes of the gap-cut history.
  ARMS:  trail_K (the lane's arm, time-exit at K) · none_K (stop only) · slow_X_K (stop + X only) ·
         handoff_X_K: phase 1 = the lane's trail (stop live); HAND-OFF at the first session >= 1 whose HIGH reaches
         entry + 3R OR exceeds the post-EP high (max high from the EP day through the prior session); from that
         session's close phase 2 = runner exit X only (initial stop still live), no 20-session cap.
         X in {sma21_2x (PRIMARY), sma50_1x, ema65_1x}.
  K: 20, 40, 60, and HZ (no cap, to 10-05). Open at K -> marked at the K close ("open"); fewer than K sessions
  available -> marked at the 10-05 close ("open_short", counted separately).
  (c) PASS, judged on PRIMARY = handoff_sma21_2x, 1xADR stop, K = 60, ERA A, judged (gap-charged) R:
     winner fires = the 11 first fires on the 7 summary.json runners; KEPT = R >= +3R. Pass = kept >= 8 of 11 AND
     mean R over the 11 >= +5.5 AND mean R over every other readable ERA A first fire >= −0.14; AND ERA B's mean R
     has the SAME SIGN as ERA A's all-fire mean (the rerun's era rule), ERA B reported with every fire an open mark
     (<= 26 sessions) and counted as such. The other 5 hand-off cells (2 runner exits x 1xADR; 3 x incumbent) and
     0.75xADR are reported beside, never as the bar. House R beside judged R; if the verdict flips on convention it
     is said.
  SLOW-EXIT CELLS: slow_{sma21_2x, sma50_1x, ema65_1x} with the 1xADR stop (PRIMARY, the §B "what the exits do"
     stop; incumbent beside) on ERA A first fires with >= 60 sessions after the fire, SAME fires at s20 and s60.
     Per cell PASS = mean(s60) > mean(s20) AND mean(s60) after dropping the best TWO NAMES (by summed s60 R in that
     cell) > 0. The >= 40-session version (s40 vs s20) beside. The lane's own trail at s20 vs s60 beside (the lens
     said −1.4R on the total).

═══════════════════════════ (d) THE SLOW-LEADER LABEL ═══════════════════════════
  FAST (the rerun's RUNNER, reproduced as an anchor): max high over sessions 1..15 >= 1.5 x EP-day close AND the
  session-15 close >= 1.3 x it. SLOW: the session-40 close >= 1.25 x the EP-day close AND above the 50-day SMA at
  that close. Reported per campaign beside the fast one: n, names, overlap, his labelled EPs (read from
  shared.operator_labelled_eps), whether the lane fired, and each arm's kept-≥3R count on slow-leader fires.

═══════════════════════════ ANCHORS (phase `anchor`, before any result; a miss is a HALT) ═══════════════════════════
  (A1) the walker with K = 20, horizon 09-25 reproduces reentry_rows attempt 1 for the four stops x both arms on
       every fire (status/outcome/R/gap-charged R), 0 drift (differences classified if any).
  (A2) rerun §D's table (pooled eras, the "rest" = every non-runner fire, mark at s20 or the last close, horizon
       09-25): lane arm 4 / +2.7 / −0.32; 1xADR+trail 7 / +4.4 / −0.14; 1xADR+sma21_2x 8 / +5.5 / −0.26;
       1xADR+sma50_1x 5 / +3.8 / −0.18; 1xADR+none 8 / +5.8 / −0.37 — a check of the slow-exit lines.
  (A3) the FAST label on sat_daily_long reproduces summary.json's 11 ran +50% / 7 held.

═══════════════════════════ EXPECTED BEFORE RUNNING (so a surprise is visible) ═══════════════════════════
  (a) launches exist (~20–40 of ~200 ARM40 campaigns) but most start inside the 20-session lane window (the lows of
      a post-EP base sit in sessions 1–15) -> FAIL, with August starts UNKNOWN on Family A. (c) the hand-off keeps
      ~8 of 11 at a ~+6R winner mean, but the non-winner mean sits around −0.15 to −0.20 -> borderline FAIL on the
      cost leg. Slow exits at s60: winners get bigger, drop-best-two <= 0 -> FAIL. (d) the slow label adds TEAM and a
      few others; MRNA (32 sessions) unreadable at s40. ERA B: NOT_TESTABLE at 40+ sessions.

Usage:  python3 h6_run.py gate | anchor | run | report      (run ONCE; the report reads the row files)
Outputs: h6_gate_out.txt, h6_anchor_out.txt, h6_census.tsv, h6_fire_rows.tsv, h6_labels.tsv, h6_report.txt,
         h6_summary.json
"""
from __future__ import annotations

import csv
import json
import math
import statistics
import sys
from collections import Counter, defaultdict
from datetime import date, timedelta
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[2]
for p in (REPO, REPO / "scripts" / "probes", REPO / "scripts" / "probes" / "_327_block5", HERE):
    if str(p) not in sys.path:
        sys.path.insert(0, str(p))

import rerun                                      # noqa: E402  read_tsv, load_fires, load_daily, minutes
import reentry                                    # noqa: E402  settle_attempt, make_ctx, load_campaigns, load_runners
from agents.market_intelligence.delayed_entry_shadow import (   # noqa: E402  real code
    LANE_SESSIONS, SETTLE_HOLD_SESSIONS, _trading_days, sma_trail_line,
)
from shared.operator_labelled_eps import OPERATOR_LABELLED_EPS   # noqa: E402

H_END = date(2026, 10, 5)
H_RERUN = date(2026, 9, 25)
ERA_SPLIT = date(2026, 8, 22)
FLAG_ALL_END = date(2026, 7, 24)
FAMA_LOOKBACK = 30
LIVE_STAGES = {"WATCH", "TIGHTENING", "COILED", "TRIGGERED"}
LAUNCH_GAIN = 0.5
CENSUS_N = 40
REENTRY_WATCH = 20
GAP_CUT_DAYS = 30
WIDTH_FLOOR_PCT = 0.5
TAIL_R = 3.0
HANDOFF_R = 3.0
STOPS = (("adr_100", 1.0), ("incumbent", None), ("adr_075", 0.75))
ANCHOR_STOPS = (("incumbent", None), ("adr_075", 0.75), ("adr_100", 1.0), ("adr_150", 1.5))
RUNNER_EXITS = ("sma21_2x", "sma50_1x", "ema65_1x")
KS = (20, 40, 60, "HZ")
_EPS = 1e-9

OUT = {k: HERE / f"h6_{k}" for k in ("gate_out.txt", "anchor_out.txt", "census.tsv", "fire_rows.tsv", "labels.tsv",
                                       "report.txt", "summary.json")}


def _f(v):
    return rerun._f(v)


def mean(v):
    v = [x for x in v if x is not None]
    return statistics.mean(v) if v else None


def fmt(x, f="{:+.2f}"):
    return "—" if x is None else f.format(x)


# ── loaders ───────────────────────────────────────────────────────────────────────────────────────────

def load_daily_long():
    """{ticker: {date: bar}} from sat_daily_long.tsv, rows before the last > GAP_CUT_DAYS gap cut."""
    raw = defaultdict(dict)
    for r in rerun.read_tsv(HERE / "sat_daily_long.tsv"):
        d = date.fromisoformat(r["trade_date"])
        raw[r["ticker"]][d] = {"trade_date": d, "open_price": _f(r["open_price"]), "high_price": _f(r["high_price"]),
                               "low_price": _f(r["low_price"]), "close": _f(r["close"]), "volume": _f(r["volume"])}
    cuts = {}
    out = {}
    for t, bars in raw.items():
        ds = sorted(bars)
        cut = None
        for a, b in zip(ds, ds[1:]):
            if (b - a).days > GAP_CUT_DAYS:
                cut = b
        if cut is not None:
            cuts[t] = (cut, sum(1 for d in ds if d < cut))
            bars = {d: v for d, v in bars.items() if d >= cut}
        out[t] = bars
    return out, cuts


_TD = {}


def sessions_after(d, end=H_END):
    k = (d, end)
    if k not in _TD:
        _TD[k] = _trading_days(d + timedelta(days=1), end)
    return _TD[k]


def load_flags():
    """{ticker: [(scan_date, stage, source)]} from the two local mi_flag_candidates captures."""
    by = defaultdict(list)
    ext = {}
    p1 = REPO / "scripts" / "probes" / "_354_stage_history.tsv"
    with open(p1) as fh:
        rd = csv.DictReader(fh, delimiter="\t")
        ds = []
        for r in rd:
            d = date.fromisoformat(r["scan_date"])
            by[r["ticker"]].append((d, r["stage"], "354_all"))
            ds.append(d)
        ext["354_all"] = (min(ds), max(ds), len(ds))
    p2 = REPO / "scripts" / "probes" / "_668_out" / "cohort_flag_rows.csv"
    with open(p2) as fh:
        ds = []
        for r in csv.DictReader(fh):
            d = date.fromisoformat(r["scan_date"])
            by[r["ticker"]].append((d, r["stage"], "668_high"))
            ds.append(d)
        ext["668_high"] = (min(ds), max(ds), len(ds))
    return by, ext


def load_reentry_rows():
    return list(rerun.read_tsv(HERE / "reentry_rows.tsv"))


def runner_ids():
    return {(t, d) for (t, d) in reentry.load_runners()}


def labelled_keys():
    return {(e.ticker, e.alert_date) for e in OPERATOR_LABELLED_EPS}


# ── moving averages ─────────────────────────────────────────────────────────────────────────────────

def sma_series(vals, n):
    out = [None] * len(vals)
    s = 0.0
    for i, v in enumerate(vals):
        s += v
        if i >= n:
            s -= vals[i - n]
        if i >= n - 1:
            out[i] = s / n
    return out


def ema_series(vals, n):
    out = [None] * len(vals)
    if len(vals) < n:
        return out
    k = 2.0 / (n + 1)
    e = sum(vals[:n]) / n
    out[n - 1] = e
    for i in range(n, len(vals)):
        e = e + k * (vals[i] - e)
        out[i] = e
    return out


# ── the per-fire path ───────────────────────────────────────────────────────────────────────────────

def prep_path(f, daily, horizon):
    """Closes history + session bars for one fire, independent of the stop."""
    bars = daily[f["ticker"]]
    fd = f["fire_date"]
    fb = bars.get(fd)
    if not fb or fb["close"] is None:
        return None
    pre = [bars[d]["close"] for d in sorted(bars) if d < fd and bars[d]["close"] is not None]
    S = sessions_after(fd, horizon)
    sb, hole = [], None
    for i, d in enumerate(S, start=1):
        b = bars.get(d)
        if not b or None in (b["high_price"], b["low_price"], b["close"], b["open_price"]):
            hole = i
            break
        sb.append(b)
    allc = pre + [fb["close"]] + [b["close"] for b in sb]
    P = len(pre)
    # post-EP high known before each session i (EP day .. session i-1)
    ref0 = max(bars[d]["high_price"] for d in bars if f["ep_date"] <= d <= fd and bars[d]["high_price"] is not None)
    hi_ref = [ref0]
    for b in sb:
        hi_ref.append(max(hi_ref[-1], b["high_price"]))
    return {"fb": fb, "S": S, "sb": sb, "hole": hole, "n": len(sb), "allc": allc, "P": P, "hi_ref": hi_ref,
            "sma21": sma_series(allc, 21), "sma50": sma_series(allc, 50), "ema65": ema_series(allc, 65)}


def day0_status(f, ctx, minutes, fm, entry, stop):
    """The lane's compute_settlement on the fire day only (no forward sessions)."""
    d0 = (f["day0_resolved"], f["day0_post_low"], f["day0_post_high"]) if f["source"] == "lane_recorded" else None
    res = reentry.settle_attempt(ctx, minutes, entry, stop, f["fire_date"], fm, f["fire_date"], d0_cache=d0, mark=False)
    if res["status"] == "settled" and res.get("outcome") == "stop":
        return "stop"
    if res["status"] == "abstain" and res.get("reason") == "window_open":
        return "ok"
    return "abstain:" + str(res.get("reason") or res["status"])


def _close_rule(path, rule, s):
    """True when exit rule `rule` fires at session s's close (s = 0 is the fire day)."""
    allc, P = path["allc"], path["P"]
    i = P + s
    c = allc[i]
    if rule == "trail":
        line = sma_trail_line(allc[max(0, i - 19):i + 1])
        return line is not None and c < line
    if rule == "sma50_1x":
        ln = path["sma50"][i]
        return ln is not None and c < ln
    if rule == "ema65_1x":
        ln = path["ema65"][i]
        return ln is not None and c < ln
    if rule == "sma21_2x":
        if s == 0:
            return False
        ln, lp = path["sma21"][i], path["sma21"][i - 1]
        return ln is not None and lp is not None and c < ln and allc[i - 1] < lp
    raise ValueError(rule)


def walk(path, entry, stop, d0, arm, K, lane_time=False):
    """One arm. arm: 'trail' | 'none' | 'slow:<X>' | 'handoff:<X>'. K int or 'HZ'.
    Returns dict(kind, s, r, r_gap, handoff_s)."""
    risk = entry - stop
    if d0 == "stop":
        return {"kind": "stop", "s": 0, "r": -1.0, "r_gap": -1.0, "handoff_s": None}
    if d0 != "ok":
        return {"kind": "abstain", "s": None, "r": None, "r_gap": None, "handoff_s": None}
    n = path["n"]
    kmax = n if K == "HZ" else K
    phase = 1
    handoff_s = None
    kind_, x = arm.split(":") if ":" in arm else (arm, None)

    def rule_now():
        if kind_ == "trail":
            return "trail"
        if kind_ == "slow":
            return x
        if kind_ == "handoff":
            return "trail" if phase == 1 else x
        return None

    # day-0 close
    r0 = rule_now()
    if r0 is not None and _close_rule(path, r0, 0):
        c = path["allc"][path["P"]]
        v = (c - entry) / risk
        return {"kind": "exit", "s": 0, "r": v, "r_gap": v, "handoff_s": None}
    last = 0
    for i in range(1, min(n, kmax) + 1):
        b = path["sb"][i - 1]
        if b["low_price"] <= stop:
            o = b["open_price"]
            rg = (o - entry) / risk if (o is not None and o < stop) else -1.0
            return {"kind": "stop", "s": i, "r": -1.0, "r_gap": rg, "handoff_s": handoff_s}
        if kind_ == "handoff" and phase == 1:
            if b["high_price"] >= entry + HANDOFF_R * risk - _EPS or b["high_price"] > path["hi_ref"][i - 1] + _EPS:
                phase, handoff_s = 2, i
        rr = rule_now()
        if rr is not None and _close_rule(path, rr, i):
            v = (b["close"] - entry) / risk
            return {"kind": "exit", "s": i, "r": v, "r_gap": v, "handoff_s": handoff_s}
        if lane_time and i == K:
            v = (b["close"] - entry) / risk
            return {"kind": "time_exit", "s": i, "r": v, "r_gap": v, "handoff_s": handoff_s}
        last = i
    # no exit inside the walked sessions
    if K != "HZ" and path["hole"] is not None and path["hole"] <= K:
        return {"kind": "abstain", "s": None, "r": None, "r_gap": None, "handoff_s": handoff_s}
    c = path["allc"][path["P"] + last]
    v = (c - entry) / risk
    if K == "HZ":
        kind = "open"
    else:
        kind = "open" if last == K else "open_short"
    return {"kind": kind, "s": last, "r": v, "r_gap": v, "handoff_s": handoff_s}


def stop_level(f, mult):
    if mult is None:
        return f["stop"]
    if f["adr_dollar"] is None or f["adr_dollar"] <= 0:
        return None
    return f["entry"] - mult * f["adr_dollar"]


# ── shared setup ────────────────────────────────────────────────────────────────────────────────────

def setup(load_minutes=True):
    daily, cuts = load_daily_long()
    fires = rerun.load_fires()
    camps = reentry.load_campaigns()
    alerts = rerun.load_alerts()
    rr = load_reentry_rows()
    a1 = {}
    for r in rr:
        if r["attempt"] == "1":
            a1[(r["ticker"], r["ep_date"], r["rung"], r["stop"], r["arm"])] = r
    fm_of = {}
    for f in fires:
        r = a1[(f["ticker"], f["ep_date"].isoformat(), f["rung"], "incumbent", "trail")]
        fm_of[f["id"]] = int(float(r["fire_minute"])) if r["fire_minute"] not in ("", None) else None
    minutes = None
    if load_minutes:
        raw, _ = rerun.load_minutes_raw()
        minutes = rerun.minutes_to_5min(raw)
    return {"daily": daily, "cuts": cuts, "fires": fires, "camps": camps, "alerts": alerts, "rr": rr, "a1": a1,
            "fm_of": fm_of, "minutes": minutes}


# ── phase: gate ─────────────────────────────────────────────────────────────────────────────────────

def phase_gate():
    S = setup(load_minutes=False)
    daily, camps, fires, alerts = S["daily"], S["camps"], S["fires"], S["alerts"]
    L = []
    p = L.append
    p("H6 GATE — population and data, printed before any result")
    eraA = [a for a in alerts if a["ep_date"] < ERA_SPLIT]
    eraB = [a for a in alerts if a["ep_date"] >= ERA_SPLIT]
    for nm, grp in (("A", eraA), ("B", eraB)):
        tc = Counter(a["tier"] for a in grp)
        p(f"ERA {nm}: {len(grp)} campaigns / {len({a['ticker'] for a in grp})} names / tiers {dict(tc)}")
    p(f"campaigns.tsv rows {len(camps)}; fires.tsv {len(fires)} (ERA A {sum(f['era'] == 'A' for f in fires)}, "
      f"ERA B {sum(f['era'] == 'B' for f in fires)})")
    # equality vs daily.tsv
    short = rerun.load_daily()
    mism = miss_long = 0
    n_cmp = 0
    for t, bars in short.items():
        for d, b in bars.items():
            lb = daily.get(t, {}).get(d)
            if lb is None:
                miss_long += 1
                continue
            n_cmp += 1
            for k in ("open_price", "high_price", "low_price", "close", "volume"):
                x, y = b[k], lb[k]
                if (x is None) != (y is None) or (x is not None and abs(x - y) > 1e-6 * max(1.0, abs(x))):
                    mism += 1
                    break
    extra = 0
    for t, bars in daily.items():
        for d in bars:
            if date(2025, 12, 1) <= d <= H_RERUN and d not in short.get(t, {}):
                extra += 1
    p(f"sat_daily_long vs daily.tsv on overlap: {n_cmp} bars compared, {mism} differ, {miss_long} daily.tsv bars "
      f"absent from the long pull, {extra} long-pull bars in 2025-12-01..09-25 absent from daily.tsv")
    p(f"gap cuts (rows before the last > {GAP_CUT_DAYS}-day gap dropped): "
      + ", ".join(f"{t} from {c} ({n} rows dropped)" for t, (c, n) in sorted(S["cuts"].items())))
    p(f"last bar per ticker: {dict(Counter(max(b) for b in daily.values()))}")
    # sessions available
    cut40 = cut60 = None
    rows = []
    for (t, ep), c in sorted(camps.items(), key=lambda x: (x[0][1], x[0][0])):
        ss = sessions_after(ep)
        bars = daily.get(t, {})
        holes40 = sum(1 for d in ss[:40] if d not in bars)
        holes60 = sum(1 for d in ss[:60] if d not in bars)
        rows.append((t, ep, c["era"], len(ss), holes40, holes60))
    for t, ep, era, n, h40, h60 in rows:
        if n >= 40 and (cut40 is None or ep > cut40):
            cut40 = ep
        if n >= 60 and (cut60 is None or ep > cut60):
            cut60 = ep
    p(f"calendar: EP dates with >= 40 sessions by {H_END}: <= {cut40}; with >= 60: <= {cut60}")
    for era in ("A", "B"):
        rs = [r for r in rows if r[2] == era]
        n40 = [r for r in rs if r[3] >= 40]
        n60 = [r for r in rs if r[3] >= 60]
        p(f"ERA {era}: {len(rs)} campaigns; max sessions {max(r[3] for r in rs)}; ARM40 {len(n40)} "
          f"(holes inside 40: {sum(1 for r in n40 if r[4])}); ARM60 {len(n60)} (holes inside 60: "
          f"{sum(1 for r in n60 if r[5])})")
        bym = Counter(r[1].strftime("%m") for r in n40)
        p(f"   ARM40 by EP month {dict(sorted(bym.items()))}; ARM60 by month "
          f"{dict(sorted(Counter(r[1].strftime('%m') for r in n60).items()))}")
    holes = [(t, ep.isoformat(), h40) for t, ep, era, n, h40, h60 in rows if n >= 40 and h40]
    p(f"campaigns with a missing bar inside their first 40 sessions: {holes}")
    # fires by sessions available after the fire
    for era in ("A", "B"):
        fs = [f for f in fires if f["era"] == era]
        c = Counter()
        for f in fs:
            n = len(sessions_after(f["fire_date"]))
            for k in (20, 40, 60):
                if n >= k:
                    c[k] += 1
        p(f"ERA {era} first fires {len(fs)}: with >= 20 / 40 / 60 sessions after the fire by {H_END}: "
          f"{c[20]} / {c[40]} / {c[60]}")
    flags, ext = load_flags()
    p(f"Family A captures: " + "; ".join(f"{k} scan {a}..{b} ({n} rows)" for k, (a, b, n) in ext.items()))
    tk = {t for t, _ in camps}
    p(f"   tickers of the 277 with any captured flag row: {sum(1 for t in tk if t in flags)} of {len(tk)}")
    lab = labelled_keys()
    for (t, ep), c in sorted(camps.items()):
        if (t, ep.isoformat()) in lab:
            p(f"his labelled EP in the 277: {t} {ep} era {c['era']} sessions by {H_END}: {len(sessions_after(ep))}")
    p(f"runners (summary.json): {sorted(runner_ids())}")
    txt = "\n".join(L)
    OUT["gate_out.txt"].write_text(txt + "\n")
    print(txt)


# ── phase: anchor ───────────────────────────────────────────────────────────────────────────────────

def phase_anchor():
    S = setup()
    daily, fires, a1, minutes = S["daily"], S["fires"], S["a1"], S["minutes"]
    L = []
    p = L.append
    p("H6 ANCHORS — run before any result")
    ctxs = {}
    drift = Counter()
    n = Counter()
    examples = []
    for f in fires:
        k = (f["ticker"], f["ep_date"])
        if k not in ctxs:
            ctxs[k] = reentry.make_ctx(f, daily)
        ctx = ctxs[k]
        fm = S["fm_of"][f["id"]]
        path = prep_path(f, daily, H_RERUN)
        for lbl, mult in ANCHOR_STOPS:
            stop = stop_level(f, mult)
            for arm in ("trail", "none"):
                ref = a1[(f["ticker"], f["ep_date"].isoformat(), f["rung"], lbl, arm)]
                n[(lbl, arm)] += 1
                if stop is None or stop >= f["entry"]:
                    got = {"kind": "killed", "r": None, "r_gap": None}
                else:
                    d0 = day0_status(f, ctx, minutes, fm, f["entry"], stop)
                    got = walk(path, f["entry"], stop, d0, arm if arm == "trail" else "none", SETTLE_HOLD_SESSIONS,
                               lane_time=True)
                rs, ro = ref["status"], ref["outcome"]
                if rs == "abstain":
                    ok = got["kind"] == "abstain"
                else:
                    rr_, rg_ = _f(ref["r"]), _f(ref["r_gap"])
                    kmap = {"stop": "stop", "trail_exit": "exit", "time_exit": "time_exit", "open": "open_short"}
                    ok = (got["kind"] == kmap.get(ro, ro) and got["r"] is not None
                          and abs(got["r"] - rr_) < 1e-3 and abs(got["r_gap"] - rg_) < 1e-3)
                    if not ok and ro == "open" and got["kind"] == "open" and abs(got["r"] - rr_) < 1e-3:
                        ok = True
                if not ok:
                    drift[(lbl, arm)] += 1
                    if len(examples) < 12:
                        examples.append((f["id"], lbl, arm, rs, ro, ref["r"], ref["r_gap"], got))
    for key in sorted(n):
        p(f"(A1) {key[0]:9s} {key[1]:5s}: {n[key] - drift[key]} of {n[key]} reproduce reentry_rows attempt 1")
    for e in examples:
        p(f"     drift: {e}")
    # (A2) §D table
    run_ids = runner_ids()
    arms = (("lane arm (incumbent + trail)", None, "trail"), ("1xADR + trail", 1.0, "trail"),
            ("1xADR + sma21_2x", 1.0, "slow:sma21_2x"), ("1xADR + sma50_1x", 1.0, "slow:sma50_1x"),
            ("1xADR + none", 1.0, "none"))
    for nm, mult, arm in arms:
        win, rest, rest_g, win_g = [], [], [], []
        for f in fires:
            stop = stop_level(f, mult)
            if stop is None or stop >= f["entry"]:
                continue
            k = (f["ticker"], f["ep_date"])
            ctx = ctxs[k]
            d0 = day0_status(f, ctx, minutes, S["fm_of"][f["id"]], f["entry"], stop)
            path = prep_path(f, daily, H_RERUN)
            g = walk(path, f["entry"], stop, d0, arm, 20, lane_time=(arm in ("trail", "none")))
            if g["r"] is None:
                continue
            if (f["ticker"], f["ep_date"].isoformat()) in run_ids:
                win.append(g["r"]); win_g.append(g["r_gap"])
            else:
                rest.append(g["r"]); rest_g.append(g["r_gap"])
        p(f"(A2) {nm:30s} runner fires kept >= 3R {sum(1 for x in win if x >= TAIL_R - _EPS)} of {len(win)}, "
          f"runner mean {fmt(mean(win), '{:+.1f}')}, rest mean house {fmt(mean(rest))} / gap-charged "
          f"{fmt(mean(rest_g))} (n {len(rest)})")
    # (A3) fast label
    ran = held = 0
    for (t, ep), c in S["camps"].items():
        if ep > date(2026, 9, 4):
            continue
        lab = labels_for(t, ep, daily)
        if lab["n15"]:
            ran += lab["fast_ran"]
            held += lab["fast"]
    p(f"(A3) FAST label on sat_daily_long: {ran} ran +50% within 15 sessions, {held} held +30% at s15 "
      f"(summary.json: 11 / 7)")
    txt = "\n".join(L)
    OUT["anchor_out.txt"].write_text(txt + "\n")
    print(txt)


# ── labels ──────────────────────────────────────────────────────────────────────────────────────────

def labels_for(t, ep, daily):
    bars = daily[t]
    epb = bars.get(ep)
    ss = sessions_after(ep)
    out = {"ticker": t, "ep_date": ep, "n_sess": len(ss), "ep_close": epb["close"] if epb else None,
           "n15": False, "fast_ran": False, "fast": False, "n40": False, "slow": None, "s40_pct": None,
           "s40_above_sma50": None, "max40_pct": None, "max60_pct": None}
    if not epb:
        return out
    epc = epb["close"]
    if len(ss) >= 15 and all(d in bars for d in ss[:15]):
        out["n15"] = True
        mx = max(bars[d]["high_price"] for d in ss[:15])
        out["fast_ran"] = mx >= 1.5 * epc - _EPS
        out["fast"] = out["fast_ran"] and bars[ss[14]]["close"] >= 1.3 * epc - _EPS
    if len(ss) >= 40 and all(d in bars for d in ss[:40]):
        out["n40"] = True
        d40 = ss[39]
        closes = [bars[d]["close"] for d in sorted(bars) if d <= d40]
        sma50 = sum(closes[-50:]) / 50 if len(closes) >= 50 else None
        c40 = bars[d40]["close"]
        out["s40_pct"] = (c40 / epc - 1) * 100
        out["s40_above_sma50"] = sma50 is not None and c40 > sma50
        out["slow"] = c40 >= 1.25 * epc - _EPS and out["s40_above_sma50"]
        out["max40_pct"] = (max(bars[d]["high_price"] for d in ss[:40]) / epc - 1) * 100
    if len(ss) >= 60 and all(d in bars for d in ss[:60]):
        out["max60_pct"] = (max(bars[d]["high_price"] for d in ss[:60]) / epc - 1) * 100
    return out


# ── phase: run ──────────────────────────────────────────────────────────────────────────────────────

def census_for(t, ep, camp, daily, flags, windows_other, reentry_windows, fires_c, open_iv, lab_keys):
    bars = daily[t]
    ss = sessions_after(ep)[:CENSUS_N]
    if len(ss) < CENSUS_N:
        return None
    if any(d not in bars for d in ss):
        return {"ticker": t, "ep_date": ep.isoformat(), "status": "hole_in_40"}
    epb = bars[ep]
    lows = [bars[d]["low_price"] for d in ss]
    highs = [bars[d]["high_price"] for d in ss]
    closes = [bars[d]["close"] for d in ss]
    suf = [None] * CENSUS_N         # max high strictly after j
    m = -1.0
    for j in range(CENSUS_N - 1, -1, -1):
        suf[j] = m if j < CENSUS_N - 1 else None
        m = max(m, highs[j])
    gains = [(suf[j] / lows[j] - 1) if suf[j] is not None else None for j in range(CENSUS_N)]
    best = max((g for g in gains if g is not None), default=None)
    row = {"ticker": t, "ep_date": ep.isoformat(), "era": camp["era"], "tier": camp["tier"], "status": "ok",
           "best_gain_pct": round(best * 100, 1) if best is not None else None,
           "his_labelled": (t, ep.isoformat()) in lab_keys}
    if best is None or best < LAUNCH_GAIN - _EPS:
        row["launch"] = False
        return row
    row["launch"] = True
    j0 = gains.index(best)
    je = next(j for j, g in enumerate(gains) if g is not None and g >= LAUNCH_GAIN - _EPS)
    low = lows[j0]
    pk = max(range(j0 + 1, CENSUS_N), key=lambda k: (highs[k], -k))
    cross = next(k for k in range(j0 + 1, CENSUS_N) if highs[k] >= (1 + LAUNCH_GAIN) * low - _EPS)
    sd, cd = ss[j0], ss[cross]
    adr = camp["adr_dollar"]
    row.update({
        "start_s": j0 + 1, "start_date": sd.isoformat(), "launch_low": low, "peak_s": pk + 1,
        "peak_date": ss[pk].isoformat(), "peak_high": highs[pk], "cross_s": cross + 1, "cross_date": cd.isoformat(),
        "earliest_start_s": je + 1, "earliest_start_date": ss[je].isoformat(),
        "low_vs_ep_low_pct": round((low / epb["low_price"] - 1) * 100, 1),
        "low_vs_ep_close_pct": round((low / epb["close"] - 1) * 100, 1),
        "low_vs_ep_close_adr": round((low - epb["close"]) / adr, 2) if adr else None,
        "zone": ("below_ep_low" if low < epb["low_price"] else
                 "ep_low_to_close" if low < epb["close"] else "above_ep_close"),
    })
    # attempt windows
    in_own = (j0 + 1) <= LANE_SESSIONS
    in_other = sorted(f"{o_ep}" for o_ep, win in windows_other.get(t, []) if o_ep != ep and sd in win)
    in_re = sorted({lbl for lbl, win in reentry_windows.get((t, ep), []) if sd in win}
                   | {f"{o_ep}:{lbl}" for (tt, o_ep), lst in reentry_windows.items() if tt == t and o_ep != ep
                      for lbl, win in lst if sd in win})
    row.update({"in_own_window": in_own, "in_other_ep_window": ";".join(in_other), "in_reentry_window": ";".join(in_re)})
    row["outside_every_window"] = (not in_own) and not in_other and not in_re
    fired_before = sorted({f["rung"] for f in fires_c if f["fire_date"] < sd})
    row["patterns_fired_before_start"] = ";".join(fired_before)
    row["n_patterns_fired_before_start"] = len(fired_before)
    open_at = [lbl for (a, b, lbl) in open_iv.get((t, ep), []) if a <= sd <= b]
    fired_between = [lbl for (a, b, lbl) in open_iv.get((t, ep), []) if sd <= a <= cd]
    row["attempt_open_at_start"] = ";".join(open_at)
    row["attempt_fired_start_to_cross"] = ";".join(fired_between)
    # Family A
    rows_f = flags.get(t, [])
    lo = sd - timedelta(days=FAMA_LOOKBACK)
    w1 = [(d, st) for d, st, _ in rows_f if lo <= d <= sd]
    w2 = [(d, st) for d, st, _ in rows_f if lo <= d <= cd]
    strict = any(st in LIVE_STAGES for _, st in w1)
    loose = bool(w1)
    if strict:
        fam = "covered"
    elif sd <= FLAG_ALL_END:
        fam = "not_covered"
    else:
        fam = "unknown"
    row.update({"famA_strict": fam, "famA_loose": "covered" if loose else ("not_covered" if sd <= FLAG_ALL_END
                                                                         else "unknown"),
                "famA_strict_to_cross": "covered" if any(st in LIVE_STAGES for _, st in w2) else
                ("not_covered" if cd <= FLAG_ALL_END else "unknown"),
                "famA_stages_seen": ";".join(sorted({st for _, st in w1}))})
    # (b) cheap column: first close above the post-EP base high (sessions 1..start)
    base_hi = max(highs[:j0 + 1])
    bk = next((k for k in range(j0 + 1, CENSUS_N) if closes[k] > base_hi + _EPS), None)
    row["base_high"] = base_hi
    row["base_break_s"] = bk + 1 if bk is not None else None
    row["base_break_before_cross"] = (bk is not None and bk <= cross)
    row["base_break_to_peak_pct"] = round((highs[pk] / closes[bk] - 1) * 100, 1) if (bk is not None and bk < pk) else None
    return row


def phase_run():
    S = setup()
    daily, fires, camps, minutes, rr = S["daily"], S["fires"], S["camps"], S["minutes"], S["rr"]
    flags, _ = load_flags()
    lab_keys = labelled_keys()
    # --- the per-fire rows ---
    ctxs = {}
    fire_rows = []
    exit_iv = defaultdict(list)          # (t, ep) -> (fire_date, exit_date, label) for the lane's first fires
    for f in fires:
        k = (f["ticker"], f["ep_date"])
        if k not in ctxs:
            ctxs[k] = reentry.make_ctx(f, daily)
        ctx = ctxs[k]
        fm = S["fm_of"][f["id"]]
        path = prep_path(f, daily, H_END)
        for lbl, mult in STOPS:
            stop = stop_level(f, mult)
            base = {"ticker": f["ticker"], "ep_date": f["ep_date"].isoformat(), "era": f["era"], "rung": f["rung"],
                    "fire_date": f["fire_date"].isoformat(), "session_idx": f["session_idx"], "source": f["source"],
                    "stop": lbl, "entry": f["entry"], "stop_px": stop,
                    "n_after": path["n"] if path else None}
            if stop is None or stop >= f["entry"] or path is None:
                fire_rows.append({**base, "arm": "ALL", "K": "", "kind": "killed_or_no_path"})
                continue
            width = (f["entry"] - stop) / f["entry"] * 100
            floored = width < WIDTH_FLOOR_PCT - _EPS
            d0 = day0_status(f, ctx, minutes, fm, f["entry"], stop)
            base.update({"width_pct": round(width, 3), "floored": floored, "d0": d0})
            for arm, ks, lane_time in (("trail", KS, True), ("none", (20, 60), True),
                                       *[(f"slow:{x}", (20, 40, 60), False) for x in RUNNER_EXITS],
                                       *[(f"handoff:{x}", (40, 60, "HZ"), False) for x in RUNNER_EXITS]):
                for K in ks:
                    g = walk(path, f["entry"], stop, d0, arm, K, lane_time=(lane_time and K == 20))
                    exit_date = (f["fire_date"] if g["s"] == 0 else path["S"][g["s"] - 1]) if g["s"] is not None else None
                    fire_rows.append({**base, "arm": arm, "K": K, "kind": g["kind"], "exit_s": g["s"],
                                      "exit_date": exit_date.isoformat() if exit_date else "",
                                      "r": None if g["r"] is None else round(g["r"], 4),
                                      "r_gap": None if g["r_gap"] is None else round(g["r_gap"], 4),
                                      "handoff_s": g["handoff_s"]})
                    if lbl == "incumbent" and arm == "trail" and K == 20 and exit_date is not None:
                        exit_iv[k].append((f["fire_date"], exit_date, f"{f['rung']}#1"))
    cols = ["ticker", "ep_date", "era", "rung", "fire_date", "session_idx", "source", "stop", "entry", "stop_px",
            "width_pct", "floored", "d0", "n_after", "arm", "K", "kind", "exit_s", "exit_date", "r", "r_gap",
            "handoff_s"]
    with open(OUT["fire_rows.tsv"], "w") as fh:
        fh.write("|".join(cols) + "\n")
        for r in fire_rows:
            fh.write("|".join("" if r.get(c) is None else str(r.get(c)) for c in cols) + "\n")
    # --- attempt windows ---
    lane_win = defaultdict(list)          # ticker -> [(ep, set(dates))]
    for (t, ep) in camps:
        lane_win[t].append((ep, set(sessions_after(ep)[:LANE_SESSIONS])))
    re_win = defaultdict(list)            # (t, ep) -> [(label, set(dates))]
    for r in rr:
        if r["stop"] != "incumbent" or r["outcome"] != "stop" or not r["stop_day"]:
            continue
        sd = date.fromisoformat(r["stop_day"])
        w = set(sessions_after(sd)[:REENTRY_WATCH])
        re_win[(r["ticker"], date.fromisoformat(r["ep_date"]))].append(
            (f"{r['rung']}#{r['attempt']}stop{r['stop_day']}:{r['arm']}", w))
    # re-entry attempts' open intervals (stop day if stopped, else fire + 20 sessions — an upper bound)
    for r in rr:
        if r["stop"] != "incumbent" or r["arm"] != "trail" or r["attempt"] == "1" or not r["fire_date"]:
            continue
        fd = date.fromisoformat(r["fire_date"])
        if r["outcome"] == "stop" and r["stop_day"]:
            ed = date.fromisoformat(r["stop_day"])
        else:
            s = sessions_after(fd)
            ed = s[min(len(s), 20) - 1] if s else fd
        exit_iv[(r["ticker"], date.fromisoformat(r["ep_date"]))].append((fd, ed, f"{r['rung']}#{r['attempt']}"))
    fires_by_c = defaultdict(list)
    for f in fires:
        fires_by_c[(f["ticker"], f["ep_date"])].append(f)
    census = []
    for (t, ep), c in sorted(camps.items(), key=lambda x: (x[0][1], x[0][0])):
        row = census_for(t, ep, c, daily, flags, lane_win, re_win, fires_by_c[(t, ep)], exit_iv, lab_keys)
        if row is not None:
            census.append(row)
    ccols = ["ticker", "ep_date", "era", "tier", "status", "his_labelled", "best_gain_pct", "launch", "start_s",
             "start_date", "launch_low", "zone", "low_vs_ep_low_pct", "low_vs_ep_close_pct", "low_vs_ep_close_adr",
             "cross_s", "cross_date", "peak_s", "peak_date", "peak_high", "earliest_start_s", "earliest_start_date",
             "in_own_window", "in_other_ep_window", "in_reentry_window", "outside_every_window",
             "patterns_fired_before_start", "n_patterns_fired_before_start", "attempt_open_at_start",
             "attempt_fired_start_to_cross", "famA_strict", "famA_loose", "famA_strict_to_cross", "famA_stages_seen",
             "base_high", "base_break_s", "base_break_before_cross", "base_break_to_peak_pct"]
    with open(OUT["census.tsv"], "w") as fh:
        fh.write("|".join(ccols) + "\n")
        for r in census:
            fh.write("|".join("" if r.get(c) is None else str(r.get(c)) for c in ccols) + "\n")
    # --- labels ---
    lcols = ["ticker", "ep_date", "era", "tier", "n_sess", "ep_close", "n15", "fast_ran", "fast", "n40", "slow",
             "s40_pct", "s40_above_sma50", "max40_pct", "max60_pct", "his_labelled", "lane_fired"]
    with open(OUT["labels.tsv"], "w") as fh:
        fh.write("|".join(lcols) + "\n")
        for (t, ep), c in sorted(camps.items(), key=lambda x: (x[0][1], x[0][0])):
            lab = labels_for(t, ep, daily)
            lab.update({"era": c["era"], "tier": c["tier"], "his_labelled": (t, ep.isoformat()) in lab_keys,
                        "lane_fired": len(fires_by_c[(t, ep)])})
            for kk in ("s40_pct", "max40_pct", "max60_pct"):
                if lab[kk] is not None:
                    lab[kk] = round(lab[kk], 1)
            lab["ep_date"] = ep.isoformat()
            fh.write("|".join("" if lab.get(c) is None else str(lab.get(c)) for c in lcols) + "\n")
    print(f"fire rows {len(fire_rows)}; census rows {len(census)}; labels {len(camps)}")


if __name__ == "__main__":
    ph = sys.argv[1] if len(sys.argv) > 1 else ""
    if ph == "gate":
        phase_gate()
    elif ph == "anchor":
        phase_anchor()
    elif ph == "run":
        phase_run()
    elif ph == "report":
        import h6_report
        h6_report.main()
    else:
        print(__doc__)
