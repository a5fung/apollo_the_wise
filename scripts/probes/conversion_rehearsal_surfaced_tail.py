#!/usr/bin/env python3
"""Conversion rehearsal — replay the SURFACED tail winners (and surfaced losers)
through TODAY'S full stack and record where each dies.

The question (ep_synthesis_2026-08-18 §4.4, operator-approved): "when next month's
tail winner alerts, does TODAY'S system convert it?" — asked directly, per name.

READ-ONLY, $0. Consumes files captured ONCE from prod (capture-once-read-many) +
the repo's #552 cohort capture. No DB connection, no API calls, no LLM. MEASURE
ONLY: nothing here proposes a rule change (THE LINE).

COHORT (denominator, stated):
  the #552 tier-A gap-day cohort (real stocks, close>=$10, $vol>=$50M, open gap>=8%,
  2026-03-01..2026-07-15; tail winner = 20d max excursion >= 8x own ADR20):
  749 gap days, 78 winners, 671 non-winners — rebuilt by _552_missed_why_cohort.sql.
  SURFACED = live-alerted at the time (HIGH or MODERATE), per the 08-16 attribution
  read's own evidence rules:
    - winners: the 15 the attribution read identified (11 bucket-C + HLIT/VPG/ABVX/NRIX).
    - losers: (a) surviving live mi_ep_alerts rows (post-purge era, 2026-05-11+);
      (b) any magna53 mi_live_trades row (any status, any era);
      (c) pre-05-11 mi_ep_missed_outcomes pipeline/tier evidence
          (high_unentered pre-scan-log or corroborated by a passed scan tick;
          moderate_alert; infra/setup/breaker/cap categories) — the same
          replay-contamination guard the 08-16 read applied to HPE/QURE.

TODAY'S STACK (verified against code + prod state 2026-08-18):
  gates: MIN_GAP_PCT=10 hard (ep_detector.py:97-98; EP_RT_PASS2_ENABLED=true in prod
  .env, floor re-applied on the REAL-TIME gap) · 60d cooldown, carve-out gap>=15 AND
  earnings (magna53_ep.md) · extension cap 50% over MIN(close) of prior ~5 sessions ·
  top-20 gap-rank cap (ep_detector.py:2794-96) · quality floors mcap>=$500M,
  ADV>=$1M, ATR<=15% (backtester/filters.py:21-23) · session/pm RVOL >= 1.0
  (minute_volume.py:75-76) · score>=50 MODERATE, >=regime ep_threshold HIGH;
  earnings MODERATE->HIGH override kept · ORB submission 09:31-09:44, 10:00 cleanup ·
  safeguards: max 5 positions, count circuit breaker = last TEN closed all losses
  (was 3 in April), tiered drawdown = sizing only · spec: stop_too_wide ORB range >
  1.5x ATR14 · fade guard for MAGNA53 HIGH = ratio None, SKIPPED (entry_pipeline
  check_fade_guard docstring) · rt gap re-check at submission: mi_safeguard_state
  ep_rt_entry_gap_recheck = ON since 08-02 (the ARGX 08-17 killer) ·
  ERA-C BRACKET (operator-signed 08-16, first live fill AMLX 08-18): stop =
  2*orb_low - orb_high at half size via the sizing formula; +2R partial pinned to
  the ORIGINAL entry + 2*(entry - orb_low); breakeven after partial; SMA10/20-max
  daily-close trail; order_manager.py:436 zero-stop guard.

SIM ENGINE: adapted from geometry_sweep_572.simulate (same uniform policy: day-0
minute resolution, dailies with gap-at-open realism, half off at target ->
breakeven -> SMA trail seeded from a 40-day window -> 20-trading-day time stop;
ambiguous daily both-touched days bracket [cons, opt]) with ONE change: the
profit target is PINNED to entry + 2*(entry - orb_low) instead of being derived
from the placed stop — the era-C frame (order_manager.profit_target_r_per_share).
sma_trail / prior-close seeding imported from geometry_sweep_572, not re-implemented.
Partial fraction here is HALF (uniform with every 08-18 program read); live takes
1/3 — stated divergence, direction: live keeps MORE in a runner past the partial.

WHAT IS RECONSTRUCTED VS LIVED — stated per name in output:
  lived: INTC 04-24, SMCI 05-06, NRIX 06-08 (real fills; their era-C leg is still
  a simulated exit from the real entry). Everything else is reconstruction: entries
  AND exits simulated; for no-bars names (March/April purged era) the fill stage is
  UNKNOWABLE and the sim, where run, is daily-resolution [cons,opt].
  Catalyst grade / score / tier are the RECORDED values — today's grounded-Sonnet
  grader + the holistic judge (paper toggle ON since 06-10) cannot be re-run at $0,
  so the tier stage is replay-of-record, not replay-of-model.

Usage:
  python3 scripts/probes/conversion_rehearsal_surfaced_tail.py --data-dir <capture dir>
Capture files expected in --data-dir (SQL: cr_capture.sql, run 2026-08-18):
  cr_alerts_win.psv cr_alert_dates.psv cr_daily.psv cr_minute.psv cr_missed.psv
  live_all.csv losers_all.psv
"""

import argparse
import csv
import sys
from datetime import date, datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

sys.path.insert(0, str(Path(__file__).resolve().parent))
from geometry_sweep_572 import sma_trail  # noqa: E402

_ET = ZoneInfo("America/New_York")
_UTC = ZoneInfo("UTC")
MAX_HOLD = 20
RISK_DOLLARS = 1000.0          # equal-dollar-risk normalisation unit

# ── the 15 surfaced tail winners (08-16 attribution read + this probe's NRIX correction) ──
# (ticker, date, tier_then, lived_status, then_killer)
WINNERS15 = [
    ("FLY",  "2026-03-12", "HIGH",     "no_trade", "no pipeline row (March era)"),
    ("FLY",  "2026-03-20", "HIGH",     "no_trade", "no pipeline row (March era)"),
    ("YSS",  "2026-03-20", "HIGH",     "no_trade", "no pipeline row (March era)"),
    ("INTC", "2026-04-24", "HIGH",     "TRADED",   "filled; -$477.34 (ORB-low stop, day 0)"),
    ("STX",  "2026-04-29", "HIGH",     "no_trade", "block:circuit_breaker (3-loss rule of the day)"),
    ("BAND", "2026-04-30", "HIGH",     "no_trade", "setup:stop_too_wide ORB $2.22 7.2% > 1.5xATR"),
    ("GTX",  "2026-04-30", "MODERATE", "no_trade", "MODERATE tier (briefing only)"),
    ("QCOM", "2026-04-30", "MODERATE", "no_trade", "MODERATE tier; the fade-skipped entry attempt was the 9M Day 2 leg (retired 08-02 #515)"),
    ("SMCI", "2026-05-06", "HIGH",     "TRADED",   "filled; -$639.34 net incl. re-entry"),
    ("FLNC", "2026-05-07", "HIGH",     "no_trade", "block:max_positions 5/5"),
    ("FTNT", "2026-05-07", "HIGH",     "no_trade", "block:max_positions 5/5"),
    ("HLIT", "2026-05-12", "HIGH",     "no_trade", "infra: account_fetch_failed (05-13 outage class)"),
    ("VPG",  "2026-05-12", "HIGH",     "no_trade", "infra: account_fetch_failed (05-13 outage class)"),
    ("ABVX", "2026-06-03", "MODERATE", "no_trade", "MODERATE tier (briefing only)"),
    ("NRIX", "2026-06-08", "HIGH",     "TRADED",   "filled; -$378.24 (ORB-low stop, 10 min)"),
]

PROBE_DIR = Path(__file__).resolve().parent


def d(s):
    return date.fromisoformat(s[:10])


def f(s):
    try:
        return float(s)
    except (TypeError, ValueError):
        return None


# ── loading ──────────────────────────────────────────────────────────────────────

def load(data_dir: Path):
    cohort = {}
    for row in csv.reader(open(PROBE_DIR / "_552_cohort.psv"), delimiter="|"):
        if len(row) < 19:
            continue
        cohort[(row[0], row[1])] = dict(
            gap=f(row[2]), o=f(row[3]), hi=f(row[4]), pc=f(row[5]), c=f(row[6]),
            adr=f(row[7]), dvol=f(row[8]), tailx=f(row[9]), winner=row[10] == "1",
            alert_n=int(row[11] or 0), tiers=row[12], scan_reasons=row[14],
            scan_max=row[15], mo_srcs=row[16], mo_cats=row[17], mo_reasons=row[18])

    daily = {}
    for row in csv.reader(open(data_dir / "cr_daily.psv"), delimiter="|"):
        if len(row) != 7 or f(row[5]) is None:
            continue
        daily.setdefault(row[1], []).append(
            (d(row[0]), f(row[2]), f(row[3]), f(row[4]), f(row[5]), f(row[6]) or 0))
    for v in daily.values():
        v.sort()

    minute = {}
    for row in csv.reader(open(data_dir / "cr_minute.psv"), delimiter="|"):
        if len(row) != 7:
            continue
        day, tm = row[1].split(" ")
        minute.setdefault((row[0], day), []).append(
            (tm, float(row[2]), float(row[3]), float(row[4]), float(row[5])))
    for v in minute.values():
        v.sort()

    alerts = {}
    for row in csv.reader(open(data_dir / "cr_alerts_win.psv"), delimiter="|"):
        alerts.setdefault((row[0], row[1]), []).append(dict(
            t=row[2][11:16], tier=row[3], score=f(row[4]), gap=f(row[5]), cq=row[6]))

    surfaced_days = {}          # ticker -> set of dates with ANY live-surfacing evidence
    for row in csv.reader(open(data_dir / "cr_alert_dates.psv"), delimiter="|"):
        surfaced_days.setdefault(row[0], set()).add(d(row[1]))

    missed = {}
    for row in csv.reader(open(data_dir / "cr_missed.psv"), delimiter="|"):
        missed.setdefault((row[0], row[1]), []).append(dict(
            src=row[2], cat=row[3], reason=row[4], score=f(row[5]),
            gap=f(row[6]), cq=row[7]))

    trades = {}
    for r in csv.DictReader(open(data_dir / "live_all.csv")):
        if r["signal_type"] == "magna53":
            trades.setdefault((r["ticker"], r["alert_date"]), []).append(r)
        # pre-05-11 cooldown lookback also needs trade-evidenced surfaced days
        if r["signal_type"] == "magna53":
            surfaced_days.setdefault(r["ticker"], set()).add(d(r["alert_date"]))

    # mo tier evidence also counts as a surfaced day (purged-alert era)
    for (t, ad), rows in missed.items():
        if any(r["cat"] in ("high_unentered", "moderate_tier") or
               r["src"] in ("high_unentered", "moderate_alert") for r in rows):
            surfaced_days.setdefault(t, set()).add(d(ad))

    losers = []
    lf = data_dir / "losers_all.psv"
    if not lf.exists():
        lf = PROBE_DIR / "_rehearsal_losers.psv"   # checked-in copy of the derived set
    for row in csv.reader(open(lf), delimiter="|"):
        losers.append((row[0], row[1]))

    return cohort, daily, minute, alerts, surfaced_days, missed, trades, losers


# ── helpers ──────────────────────────────────────────────────────────────────────

def day_row(daily, t, ad):
    for r in daily.get(t, []):
        if r[0] == ad:
            return r
    return None


def prev_rows(daily, t, ad, n):
    rows = [r for r in daily.get(t, []) if r[0] < ad]
    return rows[-n:] if rows else []


def min5_close(daily, t, ad):
    rows = prev_rows(daily, t, ad, 5)
    closes = [r[4] for r in rows if r[4]]
    return min(closes) if closes else None


def adr20(daily, t, ad):
    rows = prev_rows(daily, t, ad, 20)
    vals = [(r[2] - r[3]) / r[4] for r in rows if r[2] and r[3] and r[4]]
    return sum(vals) / len(vals) if len(vals) >= 10 else None


def atr14(daily, t, ad):
    rows = prev_rows(daily, t, ad, 15)
    if len(rows) < 11:
        return None
    trs = []
    for i in range(1, len(rows)):
        pc = rows[i - 1][4]
        h, low = rows[i][2], rows[i][3]
        if h is None or low is None or pc is None:
            continue
        trs.append(max(h - low, abs(h - pc), abs(low - pc)))
    return sum(trs[-14:]) / len(trs[-14:]) if trs else None


def prior_closes_40d(daily, t, entry_day):
    lo = entry_day - timedelta(days=40)
    return [r[4] for r in daily.get(t, []) if lo <= r[0] < entry_day]


def stop_limit_buy_price(orb_high):
    return round(max(orb_high * 1.005, orb_high + 0.02), 2)


# ── the era-C engine (adapted from geometry_sweep_572.simulate; target PINNED) ──

def simulate_era_c(entry_px, entry_tm, orb_high, orb_low, ticker, alert_date,
                   minute, daily, *, seq="cons", skip_day0_minutes=False):
    """Era-C bracket: stop = 2*orb_low - orb_high (fixed off the ORB), target
    PINNED to entry + 2*(entry - orb_low) (the ORB R frame), half off at target,
    breakeven, SMA10/20-max close trail, 20-td time stop, gap-at-open realism.
    Returns None if the geometry is unusable."""
    stop_px = 2 * orb_low - orb_high
    if stop_px <= 0 or stop_px >= entry_px:
        return None
    r_unit = entry_px - stop_px                       # the placed-stop R (era-C unit)
    target = entry_px + 2 * (entry_px - orb_low)      # PINNED original frame
    stop, partial, pnl, size = stop_px, False, 0.0, 1.0

    def done(fill, day, reason, tm=None, horizon=False):
        return dict(pnl_ps=pnl + size * (fill - entry_px), r_unit=r_unit,
                    exit_day=day, exit_reason=reason, partial_taken=partial,
                    stop_time=tm, horizon=horizon)

    day0 = (not skip_day0_minutes and
            (ticker, alert_date.isoformat()) in minute)
    if day0:
        for (tm, o, h, l, _c) in minute[(ticker, alert_date.isoformat())]:
            if tm < entry_tm:
                continue
            if l <= stop:
                fill = o if o < stop else stop
                return done(fill, alert_date,
                            "breakeven_stop" if partial else "hard_stop", tm=tm)
            if not partial and h >= target:
                fill = max(o, target)
                pnl += 0.5 * (fill - entry_px)
                size, partial, stop = 0.5, True, entry_px

    closes = prior_closes_40d(daily, ticker, alert_date)
    held = 0
    for (day, o, h, l, c, _v) in daily.get(ticker, []):
        if day < alert_date:
            continue
        if day == alert_date and day0:
            closes.append(c)
            continue
        first = (day == alert_date)
        if not first and o is not None and o <= stop:
            return done(o, day, "gap_open_be" if partial else "gap_open_stop")
        if h is None or l is None or c is None:
            continue
        both = (not partial and l <= stop and h >= target)
        if both and seq == "cons":
            return done(stop, day, "hard_stop")
        if not partial and h >= target:
            fill = max(o or target, target) if first else max(o, target)
            pnl += 0.5 * (fill - entry_px)
            size, partial, stop = 0.5, True, entry_px
            if l <= stop:
                return done(stop, day, "breakeven_stop")
        elif l <= stop:
            return done(stop, day, "breakeven_stop" if partial else "hard_stop")
        closes.append(c)
        trail = sma_trail(closes)
        if not first and trail is not None and c < trail:
            return done(c, day, "sma_trail")
        held += 1
        if held >= MAX_HOLD:
            return done(c, day, "time_stop", horizon=True)
    series = daily.get(ticker, [])
    if series:
        return done(series[-1][4], series[-1][0], "data_end", horizon=True)
    return None


def simulate_fill(minute_bars, orb_high):
    """Stop-limit buy at ORB high, limit = round(max(H*1.005, H+.02),2), armed
    09:31, cancelled 10:00. Returns (fill_px, fill_tm) or None."""
    limit = stop_limit_buy_price(orb_high)
    for (tm, o, h, _l, _c) in minute_bars:
        if tm < "09:31":
            continue
        if tm >= "10:00":
            break
        if h >= orb_high:
            if o > limit:
                continue          # gapped through the limit this bar; keep scanning
            return min(max(o, orb_high), limit), tm
    return None


# ── the funnel ───────────────────────────────────────────────────────────────────

STAGES = ["universe", "gap_floor", "cooldown", "extension", "top20", "quality",
          "tier", "timing", "safeguards", "spec", "rt_gap_0931", "fill_cancelled",
          "fill_unknowable"]


def replay(t, ad_s, ctx, tier_then=None, lived=None):
    """Walk one surfaced name-day through today's stack. Returns a record with
    died (stage or None), detail, flags, sim results."""
    cohort, daily, minute, alerts, surfaced_days, missed, trades, _ = ctx
    ad = d(ad_s)
    co = cohort.get((t, ad_s), {})
    rec = dict(ticker=t, date=ad_s, died=None, detail="", flags=[], sim=None,
               tier_then=tier_then, lived=lived, tailx=co.get("tailx"),
               adr=co.get("adr"))
    mrows = missed.get((t, ad_s), [])
    arows = alerts.get((t, ad_s), [])
    trows = trades.get((t, ad_s), [])

    def die(stage, detail):
        rec["died"], rec["detail"] = stage, detail
        return rec

    # G1 universe — prev close >= $5, prev-day volume >= 50k
    pv = prev_rows(daily, t, ad, 1)
    pc = co.get("pc") or (pv[0][4] if pv else None)
    if pc is not None and pc < 5:
        return die("universe", f"prev_close ${pc:.2f} < $5")
    if pv and pv[0][5] is not None and pv[0][5] < 50_000:
        return die("universe", f"prev_day_volume {pv[0][5]:,.0f} < 50k")

    # G2 gap floor 10% (authoritative rt floor; open gap is the proxy)
    gap = co.get("gap")
    if gap is not None and gap < 10.0:
        drow = day_row(daily, t, ad)
        crossed = drow and pc and (drow[2] - pc) / pc * 100 >= 10.0
        return die("gap_floor", f"open gap {gap:.1f}% < 10%"
                   + (" (crossed 10% intraday — zone question)" if crossed else ""))

    # G3 cooldown — any surfaced day in [D-60, D-1]; carve-out gap>=15 + earnings
    prior = [x for x in surfaced_days.get(t, set()) if ad - timedelta(days=60) <= x < ad]
    if prior:
        if gap is not None and gap >= 15.0:
            rec["flags"].append(f"cooldown carve-out needs earnings-day (prior alert {max(prior)})")
        else:
            return die("cooldown", f"surfaced {max(prior)} within 60d, gap {gap:.1f}% < 15%")

    # G4 extension — prev_close >= 50% above min5
    m5 = min5_close(daily, t, ad)
    if m5 and pc and (pc - m5) / m5 * 100 >= 50.0:
        return die("extension", f"prev_close {(pc - m5) / m5 * 100:.0f}% above 5d min close")

    # G5 top-20 gap rank (proxy: rank among same-day cohort rows with gap >= 10)
    same_day = [v["gap"] for (tk, dt), v in cohort.items()
                if dt == ad_s and v["gap"] is not None and v["gap"] >= 10.0]
    rank = 1 + sum(1 for g in same_day if g > (gap or 0))
    if rank > 20:
        return die("top20", f"gap rank ~{rank} (cohort proxy, floor) > 20")
    if rank > 15:
        rec["flags"].append(f"gap rank ~{rank} (proxy) — near the cap")

    # G6 quality floors — recorded evidence only (values unchanged since)
    qual = [r for r in mrows if r["cat"] in ("mcap_low", "adv_low", "atr_high")]
    if qual:
        return die("quality", qual[0]["reason"])
    if ad < date(2026, 3, 30):
        rec["flags"].append("quality floors unverifiable (pre-gate era) — assumed pass")

    # G7 tier — recorded score/tier (grade replay impossible at $0; judge toggle ON)
    tier, score, cq = None, None, None
    if arows:
        best = max(arows, key=lambda r: (r["tier"] == "HIGH", r["score"] or 0))
        tier, score, cq = best["tier"], best["score"], best["cq"]
    elif tier_then:
        tier = "HIGH" if "HIGH" in tier_then else "MODERATE"
        sc = [r["score"] for r in mrows if r["score"] is not None]
        score = max(sc) if sc else None
        cqs = [r["cq"] for r in mrows if r["cq"]]
        cq = cqs[0] if cqs else None
    else:
        pipe_cats = ("high_unentered", "infra_skip", "stop_too_wide", "window",
                     "cap_blocked", "breaker_blocked", "faded", "setup_other",
                     "zero_range", "duplicate_scan")
        hu = (any(r["cat"] in pipe_cats or r["src"] == "high_unentered" for r in mrows)
              or bool(trows))     # a magna53 pipeline attempt only happens for HIGH
        mo = any(r["cat"] == "moderate_tier" or r["src"] == "moderate_alert" for r in mrows)
        tier = "HIGH" if hu else ("MODERATE" if mo else None)
        sc = [r["score"] for r in mrows if r["score"] is not None]
        score = max(sc) if sc else None
        cqs = [r["cq"] for r in mrows if r["cq"]]
        cq = cqs[0] if cqs else None
    rec["tier_rec"], rec["score_rec"], rec["cq_rec"] = tier, score, cq
    if cq == "routine" and gap is not None and gap < 12.0:
        return die("tier", f"routine catalyst + gap {gap:.1f}% < 12% (post-grade filter)")
    if tier != "HIGH":
        if tier_then and "->HIGH" in tier_then:
            rec["flags"].append("earnings override promoted MODERATE->HIGH (kept today)")
        else:
            return die("tier", f"{tier or 'unknown'} (score {score}) — briefing only, no ORB")

    # G8 timing — HIGH must exist by 09:44 ET
    if arows:
        first_high = min((r["t"] for r in arows if r["tier"] == "HIGH"), default=None)
        if first_high and first_high > "09:44":
            return die("timing", f"first HIGH at {first_high} ET — WINDOW_OUT_OF_ORB")
    elif trows:
        pass                                    # a pipeline attempt proves in-window
    else:
        rec["flags"].append("alert time unknown (purged era) — assumed in-window")

    # G9 safeguards — breaker recomputed for TODAY'S 10-loss rule; slot cap as-lived
    blocked = [r for r in trows if "max_positions" in (r["skip_reason"] or "")]
    if blocked:
        return die("safeguards", "slot cap 5/5 (as-lived book; cap unchanged today)")
    # 04-29-class 3-loss breaker blocks: today's threshold is 10 — recompute
    if any("circuit_breaker" in (r["skip_reason"] or "") for r in trows):
        rec["flags"].append("3-loss breaker block then; today's 10-loss rule would NOT trip (book had <10 closed trades)")

    # G10 spec — stop_too_wide (ORB range > 1.5x ATR14) + era-C zero-stop guard
    bars = minute.get((t, ad_s), [])
    orb = bars[0] if bars and bars[0][0] in ("09:30", "09:31") else None
    orb_high = orb_low = None
    if orb:
        orb_high, orb_low = orb[2], orb[3]
    elif trows and trows[0].get("orb_high"):
        orb_high, orb_low = f(trows[0]["orb_high"]), f(trows[0]["orb_low"])
    stw = [r for r in trows if "stop_too_wide" in (r["skip_reason"] or "")]
    if stw:
        # gate unchanged today; the recorded live ATR is the better witness than a re-derived one
        return die("spec", stw[0]["skip_reason"][:90] + " (recorded live ATR; gate unchanged)")
    if orb_high and orb_low:
        a = atr14(daily, t, ad)
        if a and (orb_high - orb_low) > 1.5 * a:
            return die("spec", f"stop_too_wide: ORB range {orb_high - orb_low:.2f} > 1.5x ATR {1.5 * a:.2f}")
        if 2 * orb_low - orb_high <= 0:
            return die("spec", "era-C stop <= $0 (ORB range >= orb_low)")
    if any("zero_range" in (r["skip_reason"] or "") for r in trows):
        return die("spec", "zero ORB range (locked opening minute)")

    # G11 rt gap re-check at 09:31 (toggle ON since 08-02)
    b931 = next((b for b in reversed(bars) if b[0] <= "09:31"), None)
    if b931 and pc:
        rt_gap = (b931[4] - pc) / pc * 100
        if rt_gap < 10.0:
            return die("rt_gap_0931", f"rt gap {rt_gap:.1f}% at 09:31 < 10% (ARGX-class)")
    elif not b931:
        # recorded fade-guard skip carries the 09:31 last price for purged-bars names
        fg = next((r for r in trows if "faded_from_orb" in (r["skip_reason"] or "")), None)
        if fg and pc:
            try:
                last = float(fg["skip_reason"].split("last $")[1].split(" ")[0])
                rt_gap = (last - pc) / pc * 100
                if rt_gap < 10.0:
                    return die("rt_gap_0931",
                               f"rt gap {rt_gap:.1f}% at 09:31 < 10% (from recorded fade-skip price; "
                               "NB fade guard itself no longer applies to MAGNA53 HIGH)")
            except (IndexError, ValueError):
                pass
        else:
            rec["flags"].append("09:31 rt gap unverifiable (no bars) — assumed pass")

    # G12 fill — real fill if lived, else simulate from minute bars
    entry_px = entry_tm = None
    real = next((r for r in trows if r["status"] in ("closed", "filled")
                 and r.get("entry_price")), None)
    if real:
        entry_px = f(real["entry_price"])
        fa = (real.get("filled_at") or "")[:19]
        entry_tm = (datetime.fromisoformat(fa).replace(tzinfo=_UTC)
                    .astimezone(_ET).strftime("%H:%M")) if fa else "09:31"
        orb_high = orb_high or f(real["orb_high"])
        orb_low = orb_low or f(real["orb_low"])
        rec["flags"].append("LIVED entry (real fill)")
    elif bars and orb_high:
        got = simulate_fill(bars, orb_high)
        if not got:
            return die("fill_cancelled", f"never touched ORB high {orb_high:.2f} within limit before 10:00 — 10:00 cleanup cancels")
        entry_px, entry_tm = got
    elif orb_high and orb_low:
        drow = day_row(daily, t, ad)
        if drow and drow[2] is not None and drow[2] < orb_high:
            return die("fill_cancelled", f"day high {drow[2]:.2f} < ORB high {orb_high:.2f} — no fill possible")
        rec["flags"].append("fill timing unknowable (no minute bars) — sim daily-res, fill ASSUMED")
        entry_px, entry_tm = orb_high, "09:31"
    else:
        return die("fill_unknowable", "CENSORED — no ORB, no bars (purged era); fill and outcome unmeasurable")

    # G13 era-C outcome
    if orb_high is None or orb_low is None:
        return die("fill_unknowable", "CENSORED — no ORB geometry")
    skip0 = not bars or len(bars) < 100
    sims = {}
    for seq in ("cons", "opt"):
        s = simulate_era_c(entry_px, entry_tm, orb_high, orb_low, t, ad,
                           minute, daily, seq=seq, skip_day0_minutes=skip0)
        sims[seq] = s
        if skip0 is False:
            sims["opt"] = s
            break
    rec["sim"] = sims
    rec["entry_px"], rec["orb_high"], rec["orb_low"] = entry_px, orb_high, orb_low
    return rec


def r_of(sim):
    return sim["pnl_ps"] / sim["r_unit"] if sim and sim["r_unit"] else None


def fmt_sim(rec):
    s = rec["sim"]
    if not s or not s.get("cons"):
        return "sim n/a"
    rc = r_of(s["cons"])
    ro = r_of(s.get("opt") or s["cons"])
    adr_mult = None
    if rec.get("adr") and rec.get("entry_px"):
        adr_d = rec["entry_px"] * rec["adr"] / 100
        adr_mult = s["cons"]["pnl_ps"] / adr_d
    band = f"{rc:+.2f}R" if abs((rc or 0) - (ro or 0)) < 1e-9 else f"[{rc:+.2f},{ro:+.2f}]R"
    usd = rc * RISK_DOLLARS if rc is not None else None
    return (f"{band} eraC ({s['cons']['exit_reason']} d{(s['cons']['exit_day'] - d(rec['date'])).days}"
            + (f", {adr_mult:+.1f}xADR" if adr_mult is not None else "")
            + (f", ${usd:+,.0f}/1k-risk" if usd is not None else "") + ")")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--data-dir", required=True)
    args = ap.parse_args()
    data_dir = Path(args.data_dir)
    cohort, daily, minute, alerts, surfaced_days, missed, trades, losers = load(data_dir)
    ctx = (cohort, daily, minute, alerts, surfaced_days, missed, trades, losers)

    print("=" * 100)
    print("WINNERS — the 15 surfaced tail winners through TODAY'S stack")
    print("=" * 100)
    win_recs = []
    for (t, ad, tier_then, lived, killer) in WINNERS15:
        rec = replay(t, ad, ctx, tier_then=tier_then, lived=lived)
        win_recs.append(rec)
        status = f"DIES @ {rec['died']}: {rec['detail']}" if rec["died"] else \
                 f"FILLS -> {fmt_sim(rec)}"
        print(f"\n{t:5s} {ad}  tail {rec['tailx']:.1f}x ADR | then: {tier_then}, {lived} ({killer})")
        print(f"      today: {status}")
        for fl in rec["flags"]:
            print(f"      ⚑ {fl}")

    print("\n" + "=" * 100)
    print("LOSERS — the surfaced non-winners through the SAME stack")
    print("=" * 100)
    lose_recs = []
    for (t, ad) in losers:
        rec = replay(t, ad, ctx)
        lose_recs.append(rec)

    def stage_counts(recs):
        cnt = {}
        for r in recs:
            cnt[r["died"] or "CONVERTS"] = cnt.get(r["died"] or "CONVERTS", 0) + 1
        return cnt

    wc, lc = stage_counts(win_recs), stage_counts(lose_recs)
    print(f"\n{'stage':15s} {'winners die':>12s} {'losers die':>12s}")
    for st in STAGES + ["CONVERTS"]:
        if wc.get(st) or lc.get(st):
            label = "FILLED" if st == "CONVERTS" else st
            print(f"{label:15s} {wc.get(st, 0):12d} {lc.get(st, 0):12d}")

    # pool reaching the SUBMISSION stage (= died at fill_* or filled)
    def submitted(recs):
        return [r for r in recs
                if r["died"] in (None, "fill_cancelled", "fill_unknowable")]

    sw, sl = submitted(win_recs), submitted(lose_recs)
    print(f"\nSUBMISSION pool (reach the broker): {len(sw)} winners, {len(sl)} losers"
          f" -> winner density {len(sw) / max(1, len(sw) + len(sl)) * 100:.0f}%")

    # survivor pools
    def survivors(recs):
        return [r for r in recs if not r["died"]]

    ws, ls = survivors(win_recs), survivors(lose_recs)
    print(f"\nSUBMIT+FILL pool: {len(ws)} winners, {len(ls)} losers "
          f"-> winner density {len(ws) / max(1, len(ws) + len(ls)) * 100:.0f}%")
    lr = [r_of(r["sim"]["cons"]) for r in ls if r["sim"] and r["sim"].get("cons")]
    wr = [r_of(r["sim"]["cons"]) for r in ws if r["sim"] and r["sim"].get("cons")]
    if lr:
        print(f"loser fills era-C (cons): n={len(lr)} sum {sum(lr):+.1f}R "
              f"median {sorted(lr)[len(lr) // 2]:+.2f}R "
              f"stopped-full {sum(1 for r in ls if r['sim'] and r['sim']['cons']['exit_reason'] in ('hard_stop', 'gap_open_stop')) }")
    if wr:
        print(f"winner fills era-C (cons): n={len(wr)} sum {sum(wr):+.1f}R")
    kept_w = [r for r in ws if r["sim"] and r["sim"].get("cons")
              and r["sim"]["cons"]["pnl_ps"] > 0]
    kept_l = [r for r in ls if r["sim"] and r["sim"].get("cons")
              and r["sim"]["cons"]["pnl_ps"] > 0]
    print(f"KEPT A GAIN (era-C cons > 0): winners {len(kept_w)}/{len(ws)}"
          f" ({', '.join(r['ticker'] for r in kept_w) or '-'}) | losers {len(kept_l)}/{len(ls)}")
    assumed = [r for r in ls if any("ASSUMED" in fl for fl in r["flags"])]
    print(f"loser fills that are daily-res ASSUMED fills (no bars): {len(assumed)}")
    print("\nLoser deaths by (stage, detail-prefix), top 15:")
    agg = {}
    for r in lose_recs:
        if r["died"]:
            key = (r["died"], r["detail"].split("(")[0][:44])
            agg[key] = agg.get(key, 0) + 1
    for (st, det), n in sorted(agg.items(), key=lambda kv: -kv[1])[:15]:
        print(f"  {n:3d}  {st:12s} {det}")
    print("\nLoser survivors (name / era-C cons):")
    for r in ls:
        print(f"  {r['ticker']:5s} {r['date']}  {fmt_sim(r)}  flags={';'.join(r['flags']) or '-'}")


if __name__ == "__main__":
    main()
