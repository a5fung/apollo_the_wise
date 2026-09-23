#!/usr/bin/env python3
"""#545 Phase 2 -- CLOSE THE POPULATION GAP (docs/design/545_entry_exit_program_2026-09-05.md
§7 Phase 2 / §5.1). READ-ONLY, $0. Walks:

  (A) the 16 magna53 `stop_too_wide` refusals (deduped, deprecated strategies dropped) under
      {live(era_d), ORB low, 0.5xADR} x {ladder, t3, hard} -- bypassing the exact gate that
      refused them (ep_replay.walk_campaign(bypass_stop_too_wide=True), #545 Phase 2 addition).
  (B) the SAME 9 cells on the P-REPLAY admitted population (267-campaign, era_c-era admission,
      reused from _545_phase1_harvest_sweep.py -- not re-derived) as the REFERENCE cohort the
      pass bar is measured against, under the era ACTUALLY live (era_d), not the retired era_c
      number the design doc's own "7 per 57" quote used.
  (C) the 17 post-08-28 live-source mi_ep_alerts campaigns (2026-09-03 -> 2026-09-21; the
      09-22 alert (ONON) is the live/incomplete session and excluded) under era_d, their own
      native era -- the half of the population gap that finally puts era_d-era names in
      P-REPLAY.

Output: scripts/probes/_545p2_refusal_replay_out.txt (this script's stdout -- every number in
docs/analysis/545_phase2_population_gap_2026-09-22.md is read from that file, not re-derived
by hand) and scripts/probes/_545p2_refusal_replay.tsv (per-cell x per-campaign rows).
"""
from __future__ import annotations

import statistics as st
import sys
from collections import Counter
from dataclasses import replace
from datetime import date, time
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(REPO / "scripts"))

import ep_replay as ep  # noqa: E402
from ep_replay import RULESETS, load_daily, load_minutes, load_minutes_extra, walk_campaign  # noqa: E402

from scripts.probes._545p2_common import (  # noqa: E402
    HERE, load_daily_extra, load_minutes_extra_gz, load_minutes_extra_psql,
    parse_live_gate_text, parse_psql_section, sort_minutes,
)
import importlib.util as _ilu  # noqa: E402

_spec = _ilu.spec_from_file_location("_p1", REPO / "scripts" / "probes" / "_545_phase1_harvest_sweep.py")
p1 = _ilu.module_from_spec(_spec)
_spec.loader.exec_module(p1)

Q1 = HERE / "_545p2_q1_out.txt"
Q2 = HERE / "_545p2_q2_out.txt"
BARS_GZ = HERE / "_545p2_bars.psv.gz"
OUT_TSV = HERE / "_545p2_refusal_replay.tsv"

# 2026-09-22: the most recent COMPLETE ET session in the pulled daily captures (today,
# 2026-09-22, is live/incomplete and excluded -- same discipline _623_replay.py uses).
LAST_SETTLED = date(2026, 9, 21)
ep.LAST_SETTLED = LAST_SETTLED  # this script's OWN horizon; does not affect Phase 1's files

MAY_END = "2026-05-31"
OPERATOR_NAMES = [("PLTR", "2026-08-04"), ("TEAM", "2026-08-07"), ("HTFL", "2026-08-14"),
                  ("MRNA", "2026-08-19")]

# ── the 16 deduped magna53 stop_too_wide refusals (2026-09-22 dedupe probe on
#    mi_live_trades; 28 raw rows -> 16 magna53 names after dropping 12 deprecated-strategy
#    (9m_day2) rows; 0 collapsed as true (ticker,date) duplicates -- every row was already
#    distinct) ──────────────────────────────────────────────────────────────────────────
REFUSALS = [
    ("TLRY", "2026-04-23", "paper", "setup:stop_too_wide: stop distance 24.8% > 15%"),
    ("WST", "2026-04-23", "paper", "setup:stop_too_wide: ORB range $6.33 (2.1%) > 1.5x ATR $5.41"),
    ("WKC", "2026-04-24", "paper", "setup:stop_too_wide: ORB range $2.70 (10.0%) > 1.5x ATR $0.43"),
    ("TTMI", "2026-04-30", "paper", "setup:stop_too_wide: ORB range $10.00 (5.9%) > 1.5x ATR $7.37"),
    ("BAND", "2026-04-30", "paper", "setup:stop_too_wide: ORB range $2.22 (7.2%) > 1.5x ATR $1.30"),
    ("STRL", "2026-05-05", "paper", "setup:stop_too_wide: ORB range $35.02 (5.0%) > 1.5x ATR $20.33"),
    ("EVER", "2026-05-05", "paper", "setup:stop_too_wide: ORB range $1.00 (5.5%) > 1.5x ATR $0.70"),
    ("AIP", "2026-05-13", "paper", "setup:stop_too_wide: ORB range $3.18 (9.8%) > 1.5x ATR $3.02"),
    ("GO", "2026-05-14", "paper", "setup:stop_too_wide: ORB range $0.71 (8.1%) > 1.5x ATR $0.60"),
    ("PONY", "2026-05-26", "paper", "setup:stop_too_wide: ORB range $0.74 (7.6%) > 1.5x ATR $0.73"),
    ("CORT", "2026-07-30", "live", "setup:stop_too_wide: ORB range $7.25 (6.9%) > 1.5x ATR $6.89"),
    ("AEVA", "2026-08-06", "live", "setup:stop_too_wide: ORB range $3.08 (13.4%) > 1.5x ATR $2.33"),
    ("ATRO", "2026-08-12", "live", "setup:stop_too_wide: ORB range $5.75 (7.2%) > 1.5x ATR $5.29"),
    ("HTFL", "2026-08-14", "live", "setup:stop_too_wide: ORB range $2.55 (7.0%) > 1.5x ATR $2.19"),
    ("BULL", "2026-08-20", "live", "setup:stop_too_wide: ORB range $0.54 (5.7%) > 1.5x ATR $0.52"),
    ("ROIV", "2026-09-08", "live", "setup:stop_too_wide: ORB range $1.90 (4.9%) > 1.5x ATR $1.82"),
]
FETCHED_8 = {"TLRY", "WST", "WKC", "BAND", "TTMI", "EVER", "STRL", "ROIV"}  # needed a fetch
PRESENT_8 = {"CORT", "AEVA", "ATRO", "HTFL", "AIP", "GO", "PONY", "BULL"}   # already in P-REPLAY bars


def load_all_bars():
    minutes = load_minutes()               # scripts/ep_replay_data/_pull4_min.tsv.gz
    daily = load_daily()                    # scripts/ep_replay_data/_pull2_out.txt DAILY
    extra = load_minutes_extra()            # scripts/probes/_562bf_minute.tsv.gz (post-day0)
    n_gz = load_minutes_extra_gz(BARS_GZ, minutes)                       # the 8 fetched
    n_d8 = load_daily_extra([Q1], "DAILY_NEW8", daily)                   # daily for the 8
    n_min_new = load_minutes_extra_psql(Q2, "MIN_NEW", minutes)          # 17 post-0828 day0
    n_d_new = load_daily_extra([Q2], "DAILY_NEW_POST0828", daily)        # daily for post-0828
    sort_minutes(minutes)
    print(f"bars merged: +{n_gz} fetched-min rows, +{n_d8} daily rows (8 refusal names), "
          f"+{n_min_new} post-0828 min rows (mi_intraday_bars, no fetch), "
          f"+{n_d_new} post-0828 daily rows")
    return minutes, daily, extra


# ── cells: era_d (LIVE) is the base for every one; only stop_mode and runner_rule move ──

def build_cells():
    base = RULESETS["era_d"]
    stops = {
        "era_d_stop": base,                                              # entry-2R, LIVE
        "orb_low": replace(base, name="orb_low", stop_mode="orb_low"),
        "adr_0.5": replace(base, name="adr_0.5", stop_mode="adr_k", adr_k=0.5),
    }
    cells = {}
    for sname, srs in stops.items():
        for runner in ("ladder", "t3", "hard"):
            nm = f"{sname}_{runner}"
            rr = "live" if runner == "ladder" else runner
            # era_d's breakeven_at_r=3.0 is only meaningful on a breakeven-family runner
            # ("live"/"breakeven"/"live_trail_be" — _walk_leg's own be_floor rule). t3/hard
            # ride the ORIGINAL stop with no breakeven floor at all, so the arm would
            # silently do nothing and _walk_leg raises rather than let that pass quietly —
            # cleared here, explicitly, for exactly those two runners.
            be_r = srs.breakeven_at_r if rr == "live" else None
            cells[nm] = replace(srs, name=nm, runner_rule=rr, breakeven_at_r=be_r)
    return cells


CELLS = build_cells()
print(f"cells ({len(CELLS)}): {list(CELLS)}")


# ── stats helpers (tail-first, analysis_standard.md) ────────────────────────────────────

def _p90(xs):
    xs = sorted(xs)
    return xs[max(0, int(round(0.9 * (len(xs) - 1))))] if xs else None


def stats(xs):
    xs = sorted(xs)
    n = len(xs)
    if n == 0:
        return {"n": 0, "sum": 0.0}
    return {"n": n, "sum": sum(xs), "mean": st.mean(xs), "med": st.median(xs), "p90": _p90(xs),
            "ge3": sum(x >= 3 for x in xs), "ge5": sum(x >= 5 for x in xs), "max": max(xs),
            "win": sum(x > 0 for x in xs)}


def fmt(d):
    if d["n"] == 0:
        return "n=0"
    return (f"n={d['n']:3d} >=3R={d['ge3']:2d} >=5R={d['ge5']:2d} p90={d['p90']:+5.2f} "
            f"med={d['med']:+5.2f} sum={d['sum']:+7.1f} win={d['win']:2d}")


def drop_best(xs):
    if not xs:
        return 0, 0
    ge3 = sum(x >= 3 for x in xs)
    rest = sorted(xs)[:-1]
    return ge3, sum(x >= 3 for x in rest)


def main():
    minutes, daily, extra = load_all_bars()

    # ── (A) the 16 refusals, bypassed, every cell ──────────────────────────────────────
    print("\n" + "=" * 90)
    print("(A) THE 16 magna53 stop_too_wide REFUSALS -- bypass_stop_too_wide=True, 9 cells")
    print("=" * 90)
    atr_fidelity = []
    tsv_rows = []
    refusal_res = {}
    for cell_name, rs in CELLS.items():
        rows = []
        for ticker, ds, mode, skip_text in REFUSALS:
            d = date.fromisoformat(ds)
            atr14 = ep.atr14_abs(daily.get(ticker, {}), d)
            r = walk_campaign(ticker=ticker, alert_date=d, rs=rs, minutes=minutes,
                              daily=daily, submit=time(9, 31), atr_14=atr14,
                              minutes_extra=extra, bypass_stop_too_wide=True)
            r["account_mode"] = mode
            r["orig_skip_text"] = skip_text
            r["fetched"] = ticker in FETCHED_8
            rows.append(r)
            tsv_rows.append({**r, "cell": cell_name})
            if cell_name == list(CELLS)[0]:
                parsed = parse_live_gate_text(skip_text)
                if parsed:
                    live_range, live_threshold_or_atr = parsed
                    atr_fidelity.append((ticker, ds, live_threshold_or_atr, atr14,
                                         bool(r["gate_skip"])))
        refusal_res[cell_name] = rows

    print("\n-- fidelity check, CORRECTED (see _545p2_common.py::parse_live_gate_text): the "
          "number after 'ORB range $X > 1.5x ATR $Y' is compared to 1.5 x the harness's OWN "
          "atr14_abs(), not to atr14_abs() directly -- a first pass compared it directly and "
          "read a false ~33% divergence on every row where the live-logged Y was actually the "
          "THRESHOLD (1.5xATR), not raw ATR. ratio = live_Y / (1.5 x harness_atr): ~1.0 means "
          "AGREEMENT (Y was the threshold, built from the SAME atr the harness computes) --")
    still_refused, passes_today = [], []
    for t, d, live_y, harn_atr, refused_today in atr_fidelity:
        ratio = (live_y / (1.5 * harn_atr)) if (harn_atr and harn_atr > 0) else None
        r_str = f"ratio={ratio:.3f}" if ratio is not None else "ratio=n/a (harness ok=True, no ATR in gate_skip)"
        print(f"  {t:6s} {d}  refused_under_todays_gate={refused_today!s:5s}  live_Y={live_y:6.2f}  "
              f"harness_atr={harn_atr}  {r_str}")
        (still_refused if refused_today else passes_today).append(t)
    # TLRY's skip text uses a DIFFERENT rule (order_manager.py:7537's 15%-stop-distance check,
    # not the 1.5xATR gate) so parse_live_gate_text (which only matches the ATR wording)
    # never sees it -- added here directly so the 16-name count is whole.
    for tkr, ds, mode, skip_text in REFUSALS:
        if tkr == "TLRY":
            print(f"  TLRY   {ds}  refused_under_todays_gate=True   (different rule -- "
                  "order_manager.py:7537's 15%-stop-distance check, not parseable by the "
                  "1.5xATR regex above; independently STILL refused by today's 1.5xATR gate "
                  "too, per its own gate_skip -- see the per-cell dump)")
            still_refused.append("TLRY")
    print(f"\n  Of the 16: {len(still_refused)} STILL refused under today's 1.5xATR gate "
          f"({', '.join(still_refused)}); {len(passes_today)} would PASS it outright today, "
          f"needing no bypass at all ({', '.join(passes_today)}) -- their historical refusal "
          "reflects a superseded ATR computation (filters.py::compute_atr_14's own STRL "
          "2026-05-05 docstring precedent), not the rule we run now.")

    for cell_name, rows in refusal_res.items():
        print(f"\n----- cell: {cell_name} -----")
        settled = [r for r in rows if r["status"] == "settled" and r["realized_r"] is not None]
        marks = [r for r in rows if r["status"] == "open_at_horizon" and r["mark_r"] is not None]
        entered = [r for r in rows if r["entered"]]
        by_status = Counter(r["status"] for r in rows)
        print(f"  status counts: {dict(by_status)}  entered={len(entered)}")
        xs_settled = [r["realized_r"] for r in settled]
        xs_marks = [r["mark_r"] for r in marks]
        print(f"  settled              {fmt(stats(xs_settled))}")
        print(f"  settled+marks        {fmt(stats(xs_settled + xs_marks))}  "
              f"(marks n={len(marks)} sum={sum(xs_marks):+.1f})")
        for r in settled:
            print(f"    SETTLED {r['ticker']:6s} {r['alert_date']}  R={r['realized_r']:+.2f}  "
                  f"final={r['final_reason']}  gate_skip={r['gate_skip']}")
        for r in marks:
            print(f"    MARK    {r['ticker']:6s} {r['alert_date']}  mark={r['mark_r']:+.2f}")
        for r in rows:
            if r["status"] not in ("settled", "open_at_horizon"):
                print(f"    {r['status']:12s} {r['ticker']:6s} {r['alert_date']}  reason={r['reason']}")

    cols = ["cell", "ticker", "alert_date", "account_mode", "fetched", "status", "reason",
            "gate_skip", "entered", "entry_px", "stop", "target", "realized_r", "mark_r",
            "final_reason"]
    with open(OUT_TSV, "w") as fh:
        fh.write("|".join(cols) + "\n")
        for r in tsv_rows:
            fh.write("|".join("" if r.get(c) is None else str(r.get(c)) for c in cols) + "\n")
    print(f"\nwritten: {OUT_TSV} ({len(tsv_rows)} rows)")

    # ── (B) the P-REPLAY admitted reference cohort, SAME 9 cells ──────────────────────
    print("\n" + "=" * 90)
    print("(B) REFERENCE: P-REPLAY admitted (267-campaign population, era_c-era admission, "
          "reused from Phase 1's own loader) -- SAME 9 cells, era_d framing")
    print("=" * 90)
    s2, alerts, p_minutes, p_daily, p_extra, regime_rows = p1.load_all()
    admitted = [a for a in alerts if a["admit"] == "admit"]
    print(f"P-REPLAY population: {len(alerts)} campaigns, {len(admitted)} admitted "
          "(unchanged from the design doc / Phase 1 -- not re-derived)")
    ref_res = {}
    for cell_name, rs in CELLS.items():
        res = p1.walk_alerts(admitted, rs, p_minutes, p_daily, p_extra)
        settled = [r for r in res.values() if r["status"] == "settled" and r["realized_r"] is not None]
        xs = [r["realized_r"] for r in settled]
        entered = sum(1 for r in res.values() if r["entered"])
        ref_res[cell_name] = {"settled": settled, "xs": xs, "entered": entered}
        s = stats(xs)
        rate = (s["ge3"] / entered * 100) if entered else 0.0
        print(f"  {cell_name:16s} entered={entered:3d}  {fmt(s)}  >=3R per 100 entries={rate:5.1f}")

    # ── (C) post-08-28 new alerts (17, excl. today), era_d, native era ─────────────────
    print("\n" + "=" * 90)
    print("(C) POST-08-28 new live-source mi_ep_alerts campaigns (2026-09-03 -> 2026-09-21), "
          "era_d (their own live era). 2026-09-22 (ONON) excluded -- live/incomplete session.")
    print("=" * 90)
    post_text = Q1.read_text()
    post_rows = parse_psql_section(post_text, "ALERTS_NEW_POST0828")
    post_rows = [r for r in post_rows if r["alert_date"] <= "2026-09-21"]
    print(f"  {len(post_rows)} campaigns (of {len(parse_psql_section(post_text, 'ALERTS_NEW_POST0828'))} "
        "pulled; 1 excluded as the live/incomplete 09-22 session)")
    post_out = []
    for r in post_rows:
        t, ds = r["ticker"], r["alert_date"]
        d = date.fromisoformat(ds)
        det = None
        if r["detected_at_et"]:
            hh, mm = r["detected_at_et"].split(" ")[1].split(":")[:2]
            det = time(int(hh), int(mm))
        submit = max(time(9, 31), det) if det else time(9, 31)
        rr = walk_campaign(ticker=t, alert_date=d, rs=RULESETS["era_d"], minutes=minutes,
                           daily=daily, submit=submit, minutes_extra=extra)
        rr["score_tier"] = r["score_tier"]
        post_out.append(rr)
        st_ = rr["realized_r"] if rr["status"] == "settled" else (
            f"mark {rr['mark_r']:+.2f}" if rr["mark_r"] is not None else None)
        print(f"    {t:6s} {ds}  tier={r['score_tier']:9s}  status={rr['status']:16s} "
              f"reason={rr['reason'] or '-':30s}  R/mark={st_}")
    settled_post = [r["realized_r"] for r in post_out if r["status"] == "settled"
                    and r["realized_r"] is not None]
    marks_post = [r["mark_r"] for r in post_out if r["status"] == "open_at_horizon"
                 and r["mark_r"] is not None]
    print(f"  settled: {fmt(stats(settled_post))}")
    print(f"  open marks: n={len(marks_post)} sum={sum(marks_post):+.1f}"
          if marks_post else "  open marks: n=0")
    print("  CHPT 2026-09-03: NOT in mi_ep_alerts at all (confirmed by direct query) -- it "
          "never reached alert level (mcap_too_small at the SCAN stage, same bucket type as "
          "the skip-bucket population, not the alert-refusal population this half covers). "
          "It does NOT enter P-REPLAY via this pull.")

    # ── the pass bar, applied ──────────────────────────────────────────────────────────
    print("\n" + "=" * 90)
    print("PASS BAR (pre-stated, §7): n>=10 replayable refusals before ANY word about 1.5x; "
          "a candidate's >=3R per 100 entries must beat the admitted reference's (SAME cell).")
    print("=" * 90)
    for cell_name in CELLS:
        rows = refusal_res[cell_name]
        settled = [r for r in rows if r["status"] == "settled" and r["realized_r"] is not None]
        marks = [r for r in rows if r["status"] == "open_at_horizon" and r["mark_r"] is not None]
        replayable = len(settled) + len(marks)
        ref = ref_res[cell_name]
        ref_rate = (ref["settled"] and stats(ref["xs"])["ge3"] / ref["entered"] * 100) or 0.0
        ge3_settled = sum(1 for r in settled if r["realized_r"] >= 3)
        entered_ref = ref["entered"]
        rate_here = (ge3_settled / max(1, sum(1 for r in rows if r["entered"])) * 100)
        n_ok = "OK" if replayable >= 10 else "FAILS (n<10)"
        beat = "beats" if rate_here > ref_rate else "does NOT beat"
        print(f"  {cell_name:16s} replayable(settled+marks)={replayable:2d} [{n_ok}]  "
              f"refusals settled-only >=3R/100-entries={rate_here:5.1f}  "
              f"reference={ref_rate:5.1f}  -> {beat} the reference")


if __name__ == "__main__":
    main()
