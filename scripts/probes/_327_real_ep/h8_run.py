"""#327 H8 — an "EP-high reclaim after a dip" as a FIRST strength entry, on the 277 real EPs. $0, read-only, local
files only (this folder). No prod read, no DB write, no deploy, no commit. MEASUREMENT ONLY: stops, sizing and the
live same-day re-entry ban (R3) are the operator's (THE LINE); a new rung is his call.

H8 (verbatim, 327_hypotheses_2026-09-27.md §2):
  What may be wrong: "The strength side never gets a first entry after a shakeout. `ep_high_break` requires no dip
    below the EP close ever (`delayed_entry_shadow.py:429-431, 456-457`), so "shake out, then new high" is never a
    first attempt. 159 of 261 ERA A campaigns dipped below the EP close then traded at/above the EP high within 20
    sessions (median 1 session later); 30 already had a high-break fire, so up to ~129 have no strength entry."
  Fix: "Record a counterfactual "EP-high reclaim after a dip" (stop-buy at the EP high; entry = max(level, open);
    stop = dip low or 1x ADR) beside the incumbent; replay. A new rung is his call."
  Test: "Pop: ERA A 261 campaigns. Fire = first session after a dip below the EP close in which the high reaches the
    EP high, no other rung taken first. Measure: fillable-entry edge vs control, winner campaigns entered (of 7),
    mean R at s10 by stop. Pass: >= +5 pts · n >= 100 on >= 60 names · survives drop-best · ERA B same sign."
  The VERIFIED section of that doc adds (applies to every H): a held-out block (ERA A alerts after 08-14), week-block
  permutation, fill + slippage (next-bar / level entry + a few bps). Nothing in it amends H8's row.

═════════════════════ PRE-REGISTRATION (written BEFORE any outcome was computed) ═════════════════════
DATA. Daily = sat_daily_long.tsv (prod mi_daily_closes, pulled 10-06) restricted to trade_date >= 2025-12-01 (the
  same window as daily.tsv; identical rows on the overlap, checked: 51,274 of 51,274) and <= HORIZON 2026-10-05.
  AKTS/LIFE/FIG have multi-month gaps in the long file; all three gaps END before 2026-01-30 and every row kept here
  is after its gap, so no pre-gap (other-security) row enters an ADR, a dip or an SMA — stated, not imputed.
  Minutes = minute.tsv.gz via rerun.load_minutes_raw (the 100-bar rule) -> the lane's to_rth_5min. sat_day0_minutes
  is EP-DAY (day 0) only and H8 lives in sessions 1-20 -> UNUSED. ADR$ = campaigns.tsv adr_dollar (pre-EP 20
  sessions, the lane's compute_ep_adr_dollar). EP-day levels from the EP-day daily bar.
  HORIZON = 10-05 (extends ERA B readability vs the 09-27 program's 09-25); anchors run at 09-25 first.
ERAS. ERA A = alert_date < 2026-08-22 (DISC <= 08-14, HOA 08-15..08-21 shown); ERA B >= 08-22. NEVER pooled.
FIRE (the lane's state machine, its own fold order): walk post-EP sessions 1..20 (state clean at the EP day's end —
  an EP-day dip does not count, as in the lane). Per 5-min bar the bar's LOW folds first (undercut_seen /
  low_since_undercut / dipped_below_close_seen / low_of_dip, exactly the lane's evaluate_session_minute fold),
  then the H8 test: dipped_below_close_seen AND bar high >= EP-day high AND not yet fired -> FIRE at that bar.
  Grade per session:
    - not dipped at session start, day low >= EP close  -> no dip, no H8 fire possible; fold daily.
    - not dipped at start, day low < EP close, day high < EP high -> dip, no touch; fold daily.
    - not dipped at start, day low < EP close AND day high >= EP high (the ORDERING case) -> needs 5-min bars;
      missing -> the campaign ABSTAINS (counted, never guessed: the touch may have preceded the dip).
    - dipped at session start AND day high >= EP high -> the resting stop-buy fills this session, provable from the
      daily bar. With 5-min bars: the touch bar locates the fill (minute grade, the fill bar's own low folds first
      as in the lane). Without: DAILY grade (fire_minute None; stop = low_of_dip through the prior session; the
      lane's settlement then reads the whole fire day stop-first — pess, counted).
    - a missing daily bar: the lane's rule — know nothing, state carries (counted).
  Same-bar dip+touch (the first dip and the touch in ONE 5-min bar): lane convention (low first) is PRIMARY;
    counted; resolved on the 1-min bars as a sensitivity (excluded when the 1-min order puts the touch first or
    cannot order it).
ENTRIES. Recorded = the EP-day high (the level). FILLABLE (the bar's measure, primary) = max(EP high, the touch
  bar's open) x (1 + 5 bps) at minute grade; max(EP high, session open) x (1 + 5 bps) at daily grade (the 09-27
  harness's `level_open`); exits slipped 5 bps (hyptests.slip_r). At-the-close entry shown beside.
"NO OTHER RUNG TAKEN FIRST" — PRIMARY = VERBATIM/STRICT: the fire counts only if NONE of the lane's four rungs
  (fires.tsv first fires: ep_low_reclaim, ep_close_reclaim, ep_high_break, ep_close_620_prox) fired before the H8
  touch. Order key (fire_date, minute); a daily-grade rung fire sits at the session open (570). A rung firing in the
  SAME 5-min bucket as a minute-grade H8 touch fired at that bar's CLOSE -> after the touch -> H8 first. A
  daily-grade H8 fire with another rung on the same date at a minute -> ambiguous -> excluded from strict, counted.
  VARIANT (beside, never promoted): exclude only campaigns whose ep_high_break fired (the row's own "~129").
  ⚠ Expected: the strict n is small — a dip below the EP close followed by a rise to the EP high passes back over the
  EP close, which is exactly what arms ep_close_reclaim / ep_low_reclaim on the way up.
STOPS (two, as the row says): DIP = low_of_dip at the touch (the lane's fold); ADR = fill entry - 1 x ADR$.
EDGE (the 09-27 H2 instrument verbatim — p2_probe.first_passage / at_checkpoint): walk from the entry with a stop
  barrier at entry - 1 x ADR$ and a target at entry + 2 x ADR$ (ORIGINAL pre-EP-ADR barriers = primary), pess
  (stop first on a straddle), resolved by session 10; day-0 bars = the touch session's 5-min bars after the touch
  bar (minute grade) or the whole fire day (daily grade, H2's convention); rate = share of non-abstaining walks
  resolved TARGET (open counts as not-target). Fires need >= 10 sessions after the fire. CONTROLS = every session
  1..20 of the SAME campaigns that is not a fire date (H8's and the lane's four rungs', as H2 excluded all fire
  dates), with a close and >= 10 sessions after, entered at the close, same barriers. Edge = fire rate minus
  control rate, in points. Beside: recorded entry, at-the-close entry, scaled barriers (H2's trailing-3-session
  range over post-EP sessions max(1,s-2)..s), the -1-first rate (an artefact raises both), the incumbent
  ep_high_break's own edge from hyp_rows_h2.tsv.
R (the lane's compute_settlement via reentry.settle_attempt, gaps charged at the open via hyptests.gap_charge,
  5 bps exit slip on the fillable entry): TRAIL arm primary (close below max(SMA10, SMA20)), NONE arm beside; final
  R and R at session 10 (settled -> r_*_s10, a stop at <= s10 gap-charged; marked -> mark_at_horizon over the first
  10 sessions — exact, since window_open means no stop in any walked session; < 10 sessions walked -> unreadable).
TAIL (analysis_standard: the tail first): share of fires with final R >= 3R per stop x arm; the rerun's 7 big-winner
  EPs (reentry.load_runners, never hand-listed) and his 4 labelled EPs in the 277: fired on? ended >= 3R?; worst
  single loss; R after dropping the best two names. Stop width in ADR per stop. Split by dip type (EP low breached
  vs close-only dip) — the row's own proxy split — shown, not counted.
DRAWS (counted): edge x1 · mean R by stop x2 (DIP, ADR; trail arm) = 3. Noise: 0.05 x 3 = 0.15 expected clears.
BAR (verbatim, operationalised before running), on the STRICT primary, fillable entry, original barriers, pess:
  (1) ERA A edge >= +5.0 pts;
  (2) ERA A readable fires n >= 100 on >= 60 distinct names;
  (3) "survives drop-best": the edge after dropping the best name (most +2 hits, with its controls) stays >= +5.0;
      drop-best-TWO (the program standard / this task) shown beside — if the two disagree, said so;
  (4) ERA B edge > 0, readable only with >= 8 fires (MIN_HELDOUT), else "can't tell".
  PASS = (1)(2)(3)(4). (1)-(3) met with (4) unreadable -> NOT_TESTABLE. (2) unmet -> the bar is unreachable under
  the verbatim fire definition -> FAIL-on-n, the variant's reading given beside, never quietly promoted. (1) or
  (3) unmet -> FAIL. Beside (program standard, not the verbatim bar): week-shuffle permutation p on ERA A, DISC/HOA
  signs, ex-May, the variant population.
EXPECTED (stated so a surprise is visible): strict n well under 100; the edge small or negative (the lane already
  fires at the dip and H8 buys ~1 ADR higher, after the bounce); the 1xADR R near the row's lens proxy (-0.69R where
  the EP low held, -0.01R after an undercut); the DIP stop wide (1-3 ADR) so its R is compressed toward 0.

Usage: python3 h8_run.py pop     -> h8_pop_out.txt (population only; NO outcome read)
       python3 h8_run.py anchor  -> h8_anchor_out.txt (HALT on drift)
       python3 h8_run.py run     -> h8_rows.tsv (fires), h8_ctl.tsv (controls)
       python3 h8_report.py      -> h8_out.txt
"""
from __future__ import annotations

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

import hyptests as H                                  # noqa: E402
from hyptests import ERA_SPLIT, DISC_END, week_of, split_of, gap_charge, slip_r, BPS, load_reentry_attempt1  # noqa: E402
import rerun                                          # noqa: E402
import reentry                                        # noqa: E402
import p2_probe                                       # noqa: E402
from agents.market_intelligence.delayed_entry_shadow import (  # noqa: E402  real code
    _trading_days, new_state, to_rth_5min, evaluate_session_daily, evaluate_session_minute, session_needs_minutes,
)
from shared.operator_labelled_eps import OPERATOR_LABELLED_EPS  # noqa: E402

HORIZON = date(2026, 10, 5)
HORIZON_ANCHOR = date(2026, 9, 25)
DAILY_FROM = date(2025, 12, 1)
GAP_CUT = {"AKTS": date(2026, 1, 9), "LIFE": date(2026, 1, 29), "FIG": date(2025, 7, 31)}
N_SESS = 20
MIN_AFTER = 10
OPEN_MIN = 570
_TD = {}


def sessions_after(d, horizon, n=N_SESS):
    k = (d, horizon)
    if k not in _TD:
        _TD[k] = _trading_days(d + timedelta(days=1), horizon)
    return _TD[k][:n]


def load_daily_long(horizon=HORIZON):
    by = defaultdict(dict)
    for r in rerun.read_tsv(HERE / "sat_daily_long.tsv"):
        if not r.get("trade_date") or r["ticker"].startswith("("):
            continue
        d = date.fromisoformat(r["trade_date"])
        if d < DAILY_FROM or d > horizon:
            continue
        if r["ticker"] in GAP_CUT and d < GAP_CUT[r["ticker"]]:
            continue
        by[r["ticker"]][d] = {"trade_date": d, "open_price": rerun._f(r["open_price"]), "high_price": rerun._f(r["high_price"]),
                              "low_price": rerun._f(r["low_price"]), "close": rerun._f(r["close"]), "volume": rerun._f(r["volume"])}
    return by


def load():
    alerts = rerun.load_alerts()
    camps = reentry.load_campaigns()
    fires = rerun.load_fires()
    runners = reentry.load_runners()
    daily = load_daily_long()
    raw, dropped = rerun.load_minutes_raw()
    min5 = {k: to_rth_5min(v, k[1]) for k, v in raw.items()}
    keys = {(a["ticker"], a["ep_date"].isoformat()) for a in alerts}
    labelled = {(e.ticker, e.alert_date) for e in OPERATOR_LABELLED_EPS if (e.ticker, e.alert_date) in keys}
    return {"alerts": alerts, "camps": camps, "fires": fires, "runners": runners, "daily": daily, "raw": raw,
            "min5": min5, "labelled": labelled}


def ctx_for(a, camps, daily):
    bars = daily.get(a["ticker"], {})
    epb = bars.get(a["ep_date"]) or {}
    return {"tkr": a["ticker"], "ep": a["ep_date"], "bars": bars, "ordered": sorted(bars),
            "gl": epb.get("low_price"), "gc": epb.get("close"), "gh": epb.get("high_price"),
            "adr": camps[(a["ticker"], a["ep_date"])]["adr_dollar"]}


def _fold_bar(st, lo, gl, gc):
    """The lane's evaluate_session_minute stop-first fold, verbatim (anchored E)."""
    if lo < gl and not st["undercut_seen"]:
        st["undercut_seen"] = True
        st["low_since_undercut"] = lo
    if st["undercut_seen"]:
        st["low_since_undercut"] = lo if st["low_since_undercut"] is None else min(st["low_since_undercut"], lo)
    if lo < gc and not st["dipped_below_close_seen"]:
        st["dipped_below_close_seen"] = True
        st["low_of_dip"] = lo
    if st["dipped_below_close_seen"]:
        st["low_of_dip"] = lo if st["low_of_dip"] is None else min(st["low_of_dip"], lo)


def _fold_daily(st, hi, lo, gl, gc, gh):
    return evaluate_session_daily(hi, lo, gap_low=gl, gap_close=gc, gap_high=gh, prior_session_low=None, state=st)["state"]


def walk(ctx, min5, horizon, mode="h8"):
    """mode 'h8': the pre-registered H8 fire. mode 'hb': the lane's ep_high_break (no dip ever) through the SAME
    session loop and grading — anchor A (proves day ordering + loaders against fires.tsv)."""
    gl, gc, gh = ctx["gl"], ctx["gc"], ctx["gh"]
    out = {"status": None, "holes": 0, "first_dip_date": None, "first_dip_s": None, "touch_after_dip": False}
    if None in (gl, gc, gh):
        out["status"] = "no_ep_bar"
        return out
    st = new_state()
    sess = sessions_after(ctx["ep"], horizon)
    out["n_sess"] = len(sess)
    bars = ctx["bars"]
    for s_idx, d in enumerate(sess, start=1):
        b = bars.get(d)
        if not b or None in (b["high_price"], b["low_price"], b["close"]):
            out["holes"] += 1
            continue
        hi, lo, op = b["high_price"], b["low_price"], b["open_price"]
        b5 = min5.get((ctx["tkr"], d)) or []
        prior = [x for x in ctx["ordered"] if x < d]
        prior_low = bars[prior[-1]]["low_price"] if prior else None
        if mode == "hb":
            needs = session_needs_minutes(hi, lo, gap_low=gl, gap_close=gc, gap_high=gh, state=st)
            if needs and not b5:
                st = _fold_daily(st, hi, lo, gl, gc, gh)
                continue
            if needs:
                res = evaluate_session_minute(b5, gap_low=gl, gap_close=gc, gap_high=gh, prior_session_low=prior_low, state=st)
            else:
                res = evaluate_session_daily(hi, lo, gap_low=gl, gap_close=gc, gap_high=gh, prior_session_low=prior_low, state=st)
            st = res["state"]
            for f in res["fires"]:
                if f["rung"] == "ep_high_break":
                    out.update({"status": "fire", "fire_date": d, "s_idx": s_idx, "fire_minute": f["fire_minute"],
                                "entry": f["entry"], "stop": f["stop"]})
                    return out
            continue
        # ── mode h8 ──
        dipped0 = st["dipped_below_close_seen"]
        if not dipped0 and lo >= gc:
            st = _fold_daily(st, hi, lo, gl, gc, gh)
            continue
        if hi < gh:
            st = _fold_daily(st, hi, lo, gl, gc, gh)
            if out["first_dip_date"] is None and st["dipped_below_close_seen"]:
                out["first_dip_date"], out["first_dip_s"] = d, s_idx
            continue
        # a touch this session, and a dip before it or this session
        if not b5:
            if not dipped0:
                out["status"] = "abstain_ordering_no_minutes"
                out["abstain_date"] = d
                return out
            out.update({"status": "fire", "grade": "daily", "fire_date": d, "s_idx": s_idx, "fire_minute": None,
                        "touch_open": op, "stop_dip": st["low_of_dip"], "undercut": st["undercut_seen"],
                        "same_bar": False, "dip_in_session": False})
            return out
        dip_bar_m = None
        for bar in b5:
            was = st["dipped_below_close_seen"]
            _fold_bar(st, bar["l"], gl, gc)
            if not was and st["dipped_below_close_seen"]:
                dip_bar_m = bar["m"]
                if out["first_dip_date"] is None:
                    out["first_dip_date"], out["first_dip_s"] = d, s_idx
            if st["dipped_below_close_seen"] and bar["h"] >= gh:
                out.update({"status": "fire", "grade": "minute", "fire_date": d, "s_idx": s_idx, "fire_minute": bar["m"],
                            "touch_open": bar["o"], "stop_dip": st["low_of_dip"], "undercut": st["undercut_seen"],
                            "same_bar": dip_bar_m == bar["m"], "dip_in_session": not dipped0})
                return out
        if dipped0:
            out["minute_daily_high_mismatch"] = out.get("minute_daily_high_mismatch", 0) + 1   # daily high >= EP high, 5-min highs not
        # minutes walked, no touch after a dip (e.g. the touch preceded the dip in-session): continue the walk
        # (the session's 5-min lows already folded; the daily low may differ from the bucket lows only by data gaps)
        if out["first_dip_date"] is None and st["dipped_below_close_seen"]:
            out["first_dip_date"], out["first_dip_s"] = d, s_idx
    if out["status"] is None:
        out["status"] = "no_dip" if not st["dipped_below_close_seen"] else "dip_no_touch"
    return out


def same_bar_1min(raw, tkr, d, m5, gc, gh):
    """Resolve a same-5-min-bar dip+touch on the 1-min bars inside that bucket: 'dip_first' when the first 1-min
    low < EP close comes strictly before a 1-min high >= EP high (at or after it on a later minute), 'same_minute'
    when only the dip minute itself also touches, else 'touch_first'."""
    mins = [b for b in raw.get((tkr, d), []) if m5 <= b["m"] < m5 + 5]
    i0 = next((i for i, b in enumerate(mins) if b["l"] < gc), None)
    if i0 is None:
        return "no_1min_dip"
    if any(b["h"] >= gh for b in mins[i0 + 1:]):
        return "dip_first"
    if mins[i0]["h"] >= gh:
        return "same_minute"
    return "touch_first"


def classify(D, horizon=HORIZON):
    """One row per campaign: the H8 fire (or why none), strict/variant membership. NO outcome."""
    fires_by = defaultdict(list)
    for f in D["fires"]:
        fires_by[(f["ticker"], f["ep_date"])].append(f)
    rows = []
    for a in D["alerts"]:
        ctx = ctx_for(a, D["camps"], D["daily"])
        k = (a["ticker"], a["ep_date"])
        r = {"ticker": a["ticker"], "ep_date": a["ep_date"].isoformat(), "era": a["era"], "split": split_of(a["ep_date"], a["era"]),
             "month": a["ep_date"].isoformat()[:7], "tier": a["tier"], "adr": ctx["adr"], "ep_low": ctx["gl"],
             "ep_close": ctx["gc"], "ep_high": ctx["gh"],
             "runner": int((a["ticker"], a["ep_date"].isoformat()) in D["runners"]),
             "labelled": int((a["ticker"], a["ep_date"].isoformat()) in D["labelled"])}
        if ctx["adr"] is None or ctx["adr"] <= 0:
            r["status"] = "no_adr"
            rows.append(r)
            continue
        w = walk(ctx, D["min5"], horizon)
        r["status"] = w["status"]
        r["holes"] = w["holes"]
        r["mm_sessions"] = w.get("minute_daily_high_mismatch", 0)
        r["first_dip_date"] = w["first_dip_date"].isoformat() if w.get("first_dip_date") else None
        r["first_dip_s"] = w.get("first_dip_s")
        hb = [f for f in fires_by[k] if f["rung"] == "ep_high_break"]
        r["hb_fired"] = int(bool(hb))
        if w["status"] == "fire":
            fd, fm = w["fire_date"], w["fire_minute"]
            r.update({"fire_date": fd.isoformat(), "week": week_of(fd), "s_idx": w["s_idx"], "fire_minute": fm,
                      "grade": w["grade"], "touch_open": w["touch_open"], "stop_dip": w["stop_dip"],
                      "undercut": int(w["undercut"]), "same_bar": int(w["same_bar"]), "dip_in_session": int(w["dip_in_session"])})
            r["same_bar_1min"] = same_bar_1min(D["raw"], a["ticker"], fd, fm, ctx["gc"], ctx["gh"]) if w["same_bar"] else None
            before, amb = [], []
            for f in fires_by[k]:
                if f["fire_date"] < fd:
                    before.append(f["rung"])
                elif f["fire_date"] == fd:
                    if fm is None:
                        if f["fire_minute"] is None and f["rung"] == "ep_high_break":
                            before.append(f["rung"])
                        else:
                            amb.append(f["rung"])
                    else:
                        om = OPEN_MIN if f["fire_minute"] is None else f["fire_minute"]
                        if f["fire_minute"] is None or om < fm:
                            before.append(f["rung"])
            r["rungs_before"] = ",".join(sorted(before)) or None
            r["rungs_same_day_ambiguous"] = ",".join(sorted(amb)) or None
            r["strict"] = int(not before and not amb)
            r["variant"] = int(not hb)
            r["n_after"] = len(sessions_after(fd, horizon))
            r["readable"] = int(r["n_after"] >= MIN_AFTER)
            ep_s = sessions_after(a["ep_date"], horizon)
            r["lane_fire_dates"] = ",".join(sorted({f["fire_date"].isoformat() for f in fires_by[k]}))
            r["first_lane_fire"] = min(((f["fire_date"], OPEN_MIN if f["fire_minute"] is None else f["fire_minute"], f["rung"]) for f in fires_by[k]), default=None)
            r["first_lane_fire"] = f"{r['first_lane_fire'][0]} {r['first_lane_fire'][1]} {r['first_lane_fire'][2]}" if r["first_lane_fire"] else None
            r["entry_rec"] = ctx["gh"]
            to = w["touch_open"]
            r["entry_fill"] = max(ctx["gh"], to if to is not None else ctx["gh"]) * (1 + BPS)
            r["dip_w_adr"] = (r["entry_fill"] - w["stop_dip"]) / ctx["adr"] if w["stop_dip"] is not None else None
            r["n_ep_sess"] = len(ep_s)
        elif w["status"] == "abstain_ordering_no_minutes":
            r["abstain_date"] = w["abstain_date"].isoformat()
        rows.append(r)
    return rows


def phase_pop():
    D = load()
    rows = classify(D)
    L = ["#327 H8 — POPULATION (no outcome read). ERA A = alert < 2026-08-22 (DISC <= 08-14, HOA 08-15..08-21); ERA B >= 08-22. "
         f"Horizon {HORIZON}. Sessions 1-{N_SESS}.", ""]
    ea = Counter(a["era"] for a in D["alerts"])
    L.append(f"GATE: alerts {len(D['alerts'])} (ERA A {ea['A']}, ERA B {ea['B']}); first fires {len(D['fires'])}; runners {len(D['runners'])} "
             f"{sorted(D['runners'])}; labelled in the 277 {len(D['labelled'])} {sorted(D['labelled'])}")
    mism = sum(1 for f in D["fires"] if abs((f["ep_high"] or 0) - (D["daily"][f["ticker"]].get(f["ep_date"], {}).get("high_price") or -1)) > 1e-9
               or abs((f["ep_close"] or 0) - (D["daily"][f["ticker"]].get(f["ep_date"], {}).get("close") or -1)) > 1e-9)
    L.append(f"      fires.tsv EP high/close == the long-file EP-day bar on {len(D['fires']) - mism} of {len(D['fires'])}")
    L.append("")
    for era in ("A", "B"):
        rr = [r for r in rows if r["era"] == era]
        st = Counter(r["status"] for r in rr)
        fr = [r for r in rr if r["status"] == "fire"]
        L.append(f"ERA {era}: campaigns {len(rr)} — " + " · ".join(f"{k} {v}" for k, v in sorted(st.items())))
        L.append(f"   campaigns with a daily-bar hole inside sessions 1-20: {sum(1 for r in rr if r.get('holes'))}; "
                 f"sessions where the daily high reached the EP high after a dip but no 5-min bar did: {sum(r.get('mm_sessions') or 0 for r in rr)}")
        L.append(f"   H8 touches after a dip: {len(fr)} on {len({r['ticker'] for r in fr})} names | grade minute {sum(1 for r in fr if r['grade']=='minute')} · daily {sum(1 for r in fr if r['grade']=='daily')}"
                 f" | dip in the touch session {sum(r['dip_in_session'] for r in fr)} · same 5-min bar {sum(r['same_bar'] for r in fr)} "
                 f"(1-min: {dict(Counter(r['same_bar_1min'] for r in fr if r['same_bar']))}) | EP low undercut first {sum(r['undercut'] for r in fr)}")
        L.append(f"   ep_high_break already fired (variant exclusion): {sum(r['hb_fired'] for r in fr)} of the {len(fr)}; "
                 f"any lane rung before the touch: {sum(1 for r in fr if r['rungs_before'])} ({dict(Counter(x for r in fr if r['rungs_before'] for x in r['rungs_before'].split(',')))}); "
                 f"same-day ambiguous (daily-grade H8): {sum(1 for r in fr if r['rungs_same_day_ambiguous'])}")
        for lab in ("strict", "variant"):
            s = [r for r in fr if r[lab]]
            rd = [r for r in s if r["readable"]]
            L.append(f"   {lab.upper():7s} fires {len(s)} on {len({r['ticker'] for r in s})} names; readable (>= {MIN_AFTER} sessions after) {len(rd)} on {len({r['ticker'] for r in rd})} names"
                     f" | DISC {sum(1 for r in rd if r['split']=='DISC')} · HOA {sum(1 for r in rd if r['split']=='HOA')} · ex-May {sum(1 for r in rd if r['month']!='2026-05')}"
                     f" | runners fired {sum(r['runner'] for r in s)} of 7 · labelled fired {sum(r['labelled'] for r in s)} of {len(D['labelled'])}")
            if s:
                sb = Counter(("s01-02" if r["s_idx"] <= 2 else "s03-05" if r["s_idx"] <= 5 else "s06-10" if r["s_idx"] <= 10 else "s11+") for r in s)
                dw = sorted(r["dip_w_adr"] for r in s if r["dip_w_adr"] is not None)
                L.append(f"      session buckets {dict(sorted(sb.items()))} | DIP stop width in ADR median {statistics.median(dw):.2f} (p10 {dw[len(dw)//10]:.2f}, p90 {dw[9*len(dw)//10]:.2f})")
        # the row's lens count: dipped then traded at/above the EP high within 20 sessions
        L.append(f"   lens check (row: 159 of 261 ERA A dipped then reached the EP high; 30 had a high-break fire): touch-after-dip {len(fr)}"
                 f" + abstained-ordering {st.get('abstain_ordering_no_minutes', 0)}; with ep_high_break {sum(r['hb_fired'] for r in fr)}")
        L.append("")
    L.append("STRICT fires (ticker ep_date -> fire_date s_idx grade fm | rungs before / ambiguous):")
    for r in rows:
        if r["status"] == "fire" and r["strict"]:
            L.append(f"   {r['era']} {r['ticker']:6s} {r['ep_date']} -> {r['fire_date']} s{r['s_idx']} {r['grade']} {r['fire_minute']} | undercut {r['undercut']} same_bar {r['same_bar']} readable {r['readable']}")
    L.append("abstained campaigns (ordering, no minutes): " + ", ".join(f"{r['era']}:{r['ticker']} {r['ep_date']}@{r['abstain_date']}" for r in rows if r["status"] == "abstain_ordering_no_minutes"))
    L.append("runner / labelled campaigns: " + "; ".join(f"{r['ticker']} {r['ep_date']} {r['status']} strict={r.get('strict')} variant={r.get('variant')} before={r.get('rungs_before')}" for r in rows if r["runner"] or r["labelled"]))
    txt = "\n".join(L) + "\n"
    (HERE / "h8_pop_out.txt").write_text(txt)
    print(txt)


# ── anchors (before any outcome) ──────────────────────────────────────────────────────────────────────

def h2_walk(ctx, entry, y, d0, after, bound="pess"):
    """H2's walk VERBATIM (hyptests_run.h2_rows.walk): day-0 (h, l) bars then the sessions after."""
    bars = list(d0) + [((ctx["bars"][d]["high_price"], ctx["bars"][d]["low_price"]) if d in ctx["bars"] and ctx["bars"][d]["high_price"] is not None else None) for d in after]
    ev, idx = p2_probe.first_passage(bars, entry, entry - y, entry + 2 * y, bound)
    return p2_probe.at_checkpoint(ev, idx, 10, len(d0))


def yard(ctx, sess, s_idx):
    rng = []
    for j in range(max(1, s_idx - 2), s_idx + 1):
        b = ctx["bars"].get(sess[j - 1])
        if not b or b["high_price"] is None:
            return None
        rng.append(b["high_price"] - b["low_price"])
    return sum(rng) / len(rng) if rng else None


def phase_anchor():
    D = load()
    lines, ok = [], True
    # (A) ep_high_break through this file's session loop + grading == fires.tsv's replayed ep_high_break rows
    rec = {(f["ticker"], f["ep_date"]): f for f in D["fires"] if f["rung"] == "ep_high_break" and f["source"] == "replay"}
    lane_rec = {(f["ticker"], f["ep_date"]) for f in D["fires"] if f["rung"] == "ep_high_break" and f["source"] == "lane_recorded"}
    cnt, bad = Counter(), []
    for a in D["alerts"]:
        k = (a["ticker"], a["ep_date"])
        if k in lane_rec:
            cnt["lane_recorded_skipped"] += 1
            continue
        ctx = ctx_for(a, D["camps"], D["daily"])
        w = walk(ctx, D["min5"], HORIZON_ANCHOR, mode="hb")
        mine = w["status"] == "fire"
        if k in rec:
            f = rec[k]
            same = mine and w["fire_date"] == f["fire_date"] and w["fire_minute"] == f["fire_minute"] and abs(w["entry"] - f["entry"]) < 1e-9 and abs(w["stop"] - f["stop"]) < 1e-9
            cnt["match" if same else "MISMATCH"] += 1
            if not same:
                bad.append(f"  A {k}: mine {w} vs fires.tsv {f['fire_date']} {f['fire_minute']} {f['entry']} {f['stop']}")
        elif mine:
            cnt["EXTRA"] += 1
            bad.append(f"  A EXTRA {k}: {w}")
    lines.append(f"ANCHOR A — ep_high_break through h8's walker (mode hb) @ 09-25 vs fires.tsv replayed ep_high_break rows: {dict(cnt)}")
    lines.extend(bad[:20])
    ok &= cnt.get("MISMATCH", 0) == 0 and cnt.get("EXTRA", 0) == 0
    # (B) the H2 walk at the close on this file's loader @ 09-25 == hyp_rows_h2 entry_kind=close rows (all 632 first fires)
    h2 = {}
    for r in rerun.read_tsv(HERE / "hyp_rows_h2.tsv"):
        if r["is_fire"] == "1" and r["bound"] == "pess" and r["entry_kind"] == "close" and r["barrier"] in ("orig", "scaled"):
            h2[(r["ticker"], r["ep_date"], r["pattern"], r["barrier"])] = r["outcome"]
    n = drift = 0
    dl = []
    for f in D["fires"]:
        ctx = ctx_for({"ticker": f["ticker"], "ep_date": f["ep_date"]}, D["camps"], D["daily"])
        after = sessions_after(f["fire_date"], HORIZON_ANCHOR)
        fb = ctx["bars"].get(f["fire_date"]) or {}
        if len(after) < MIN_AFTER or fb.get("close") is None:
            continue
        sess = sessions_after(f["ep_date"], HORIZON_ANCHOR)
        s_idx = f["session_idx"] or next((i for i, d in enumerate(sess, start=1) if d == f["fire_date"]), None)
        for bk, y in (("orig", f["adr_dollar"]), ("scaled", yard(ctx, sess, s_idx) if s_idx else None)):
            if y is None or y <= 0:
                continue
            mine = h2_walk(ctx, fb["close"], y, [], after)
            ref = h2.get((f["ticker"], f["ep_date"].isoformat(), f["rung"], bk))
            n += 1
            if mine != ref:
                drift += 1
                if len(dl) < 10:
                    dl.append(f"  B DRIFT {f['ticker']} {f['ep_date']} {f['rung']} {bk}: mine {mine} ref {ref}")
    lines.append(f"ANCHOR B — H2 at-the-close walk on the long-file loader @ 09-25 vs hyp_rows_h2 close rows: {n - drift} of {n} identical, drift {drift}")
    lines.extend(dl)
    ok &= drift == 0 and n > 0
    # (C) settle_attempt @ 09-25 on this loader, 1xADR stop, both arms == reentry_rows attempt 1 adr_100 (all 632)
    a1 = load_reentry_attempt1()
    cC, lc = Counter(), []
    for f in D["fires"]:
        ctx = ctx_for({"ticker": f["ticker"], "ep_date": f["ep_date"]}, D["camps"], D["daily"])
        d0 = (f["day0_resolved"], f["day0_post_low"], f["day0_post_high"]) if f["source"] == "lane_recorded" else None
        stop = f["entry"] - f["adr_dollar"] if f["adr_dollar"] else None
        # the re-entry study's own fire-bar convention (reentry.run_chain -> rt._locate_first_fire): a daily-grade
        # ep_high_break derives its first-touch 5-min bar when the series is gap-free through it
        fm_ref, _ = reentry.rt._locate_first_fire(f, ctx, D["min5"])
        res = H.settle_first(ctx, D["min5"], f, f["entry"], stop, fm_ref, f["fire_date"], d0=d0) if stop else {"status": "killed"}
        for arm in ("none", "trail"):
            ref = a1.get((f["ticker"], f["ep_date"].isoformat(), f["rung"], "adr_100", arm))
            if ref is None:
                cC["no_ref"] += 1
                continue
            if res["status"] in ("settled", "marked"):
                oc, r, g = res[arm]
                good = ref["status"] == res["status"] and ref["outcome"] == oc and abs(ref["r_gap"] - r) < 1e-4
            else:
                good = ref["status"] not in ("settled", "marked")
            cC["match" if good else "MISMATCH"] += 1
            if not good and len(lc) < 10:
                lc.append(f"  C {f['ticker']} {f['ep_date']} {f['rung']} {arm}: mine {res.get('status')} {res.get(arm)} vs {ref}")
    lines.append(f"ANCHOR C — settle (lane compute_settlement) @ 09-25 on the long-file loader, 1xADR stop, vs reentry_rows attempt 1 adr_100: {dict(cC)}")
    lines.extend(lc)
    ok &= cC.get("MISMATCH", 0) == 0
    # (E) the per-bar fold == the lane's evaluate_session_minute state on every captured session (sessions 1-20 of the 277)
    cE = Counter()
    for a in D["alerts"]:
        ctx = ctx_for(a, D["camps"], D["daily"])
        if None in (ctx["gl"], ctx["gc"], ctx["gh"]):
            continue
        st_l = new_state()
        st_m = new_state()
        for d in sessions_after(a["ep_date"], HORIZON_ANCHOR):
            b5 = D["min5"].get((a["ticker"], d))
            if not b5:
                continue
            st_l = evaluate_session_minute(b5, gap_low=ctx["gl"], gap_close=ctx["gc"], gap_high=ctx["gh"], prior_session_low=1.0, state=st_l)["state"]
            for bar in b5:
                _fold_bar(st_m, bar["l"], ctx["gl"], ctx["gc"])
            same = all(st_l[k] == st_m[k] for k in ("undercut_seen", "low_since_undercut", "dipped_below_close_seen", "low_of_dip"))
            cE["match" if same else "MISMATCH"] += 1
    lines.append(f"ANCHOR E — h8's per-bar fold vs the lane's evaluate_session_minute state, session by session: {dict(cE)}")
    ok &= cE.get("MISMATCH", 0) == 0
    txt = "\n".join(lines) + f"\n\nANCHORS {'PASSED' if ok else 'FAILED — HALT'}\n"
    (HERE / "h8_anchor_out.txt").write_text(txt)
    print(txt)
    if not ok:
        sys.exit(1)


# ── run: outcomes (fires + controls) ─────────────────────────────────────────────────────────────────

def s10_value(res, entry, stop, arm, ctx, fire_date, sessions):
    """R at session 10 for one arm (gap-charged stop at <= s10; settled -> r_*_s10; marked -> mark over 10 sessions)."""
    oc, r_final, gap = gap_charge(ctx, res, entry, stop, arm)
    if res["status"] == "settled":
        if oc == "stop" and res.get("stop_session_idx") is not None and res["stop_session_idx"] <= 10:
            return r_final
        return res.get(f"r_{arm}_s10")
    if (res.get("marked_at") or 0) < 10:
        return None
    fb = ctx["bars"][fire_date]
    closes_before = [ctx["bars"][d]["close"] for d in ctx["ordered"] if d < fire_date and ctx["bars"][d]["close"] is not None]
    m = reentry.mark_at_horizon(entry, stop, {"h": fb["high_price"], "l": fb["low_price"], "c": fb["close"]}, sessions[:10], ctx["bars"], closes_before)
    return m["realized_r"] if arm == "none" else m["realized_r_trail"]


def phase_run():
    D = load()
    rows = classify(D)
    fires_by = defaultdict(list)
    for f in D["fires"]:
        fires_by[(f["ticker"], f["ep_date"])].append(f)
    a1 = load_reentry_attempt1()
    out, ctl = [], []
    for r in rows:
        if r["status"] != "fire":
            continue
        a = {"ticker": r["ticker"], "ep_date": date.fromisoformat(r["ep_date"])}
        ctx = ctx_for(a, D["camps"], D["daily"])
        fd = date.fromisoformat(r["fire_date"])
        fm = r["fire_minute"]
        adr = ctx["adr"]
        b5 = D["min5"].get((r["ticker"], fd)) or []
        fb = ctx["bars"][fd]
        after = sessions_after(fd, HORIZON)
        ep_sess = sessions_after(a["ep_date"], HORIZON)
        d0 = [(x["h"], x["l"]) for x in b5 if x["m"] > fm] if fm is not None else [(fb["high_price"], fb["low_price"])]
        # ── edge walks
        if r["readable"]:
            ys = yard(ctx, ep_sess, r["s_idx"])
            for ek, e, dd in (("fill", r["entry_fill"], d0), ("rec", r["entry_rec"], d0), ("close", fb["close"], [])):
                for bk, y in (("orig", adr), ("scaled", ys)):
                    if y is None or y <= 0:
                        continue
                    r[f"o_{ek}_{bk}"] = h2_walk(ctx, e, y, dd, after)
        # ── R per stop (fillable primary, recorded beside)
        for ek, e in (("fill", r["entry_fill"]), ("rec", r["entry_rec"])):
            for sk, stp in (("dip", r["stop_dip"]), ("adr", e - adr)):
                if stp is None or stp >= e or stp <= 0:
                    r[f"{ek}_{sk}_status"] = "killed"
                    continue
                res = reentry.settle_attempt(ctx, D["min5"], e, stp, fd, fm, HORIZON)
                r[f"{ek}_{sk}_status"] = res["status"]
                r[f"{ek}_{sk}_w_adr"] = (e - stp) / adr
                r[f"{ek}_{sk}_w_pct"] = (e - stp) / e * 100
                if res["status"] not in ("settled", "marked"):
                    r[f"{ek}_{sk}_why"] = res.get("reason")
                    continue
                for arm in ("trail", "none"):
                    oc, rr, gap = gap_charge(ctx, res, e, stp, arm)
                    v10 = s10_value(res, e, stp, arm, ctx, fd, res["_sessions"])
                    if ek == "fill":
                        rr = slip_r(e, stp, rr, gap)
                        v10 = slip_r(e, stp, v10, gap) if v10 is not None else None
                    r[f"{ek}_{sk}_{arm}_r"] = rr
                    r[f"{ek}_{sk}_{arm}_oc"] = oc
                    r[f"{ek}_{sk}_{arm}_s10"] = v10
                r[f"{ek}_{sk}_mfe"] = res.get("mfe_r")
                r[f"{ek}_{sk}_stop_idx"] = res.get("stop_session_idx")
        # ── context: the lane's own first fires on this campaign (reentry_rows attempt 1, trail, @ 09-25)
        for s, lab in (("incumbent", "lane"), ("adr_100", "lane_adr")):
            vals = [a1[(r["ticker"], r["ep_date"], f["rung"], s, "trail")] for f in fires_by[(a["ticker"], a["ep_date"])]
                    if (r["ticker"], r["ep_date"], f["rung"], s, "trail") in a1]
            vv = [v["r_gap"] for v in vals if v["status"] in ("settled", "marked") and v["r_gap"] is not None]
            r[f"{lab}_n"], r[f"{lab}_sum"], r[f"{lab}_max"] = len(vv), (sum(vv) if vv else None), (max(vv) if vv else None)
        out.append(r)
        # ── controls: every non-fire session 1..20 of this campaign, at the close
        if True:   # controls for every campaign with an H8 touch (H2: the same campaign windows)
            excl = {fd} | {f["fire_date"] for f in fires_by[(a["ticker"], a["ep_date"])]}
            for s_idx, sd in enumerate(ep_sess, start=1):
                b = ctx["bars"].get(sd)
                if not b or b["close"] is None or sd in excl:
                    continue
                aft = sessions_after(sd, HORIZON)
                if len(aft) < MIN_AFTER:
                    continue
                c = {"ticker": r["ticker"], "ep_date": r["ep_date"], "era": r["era"], "split": r["split"], "month": r["month"],
                     "week": week_of(sd), "s_idx": s_idx, "strict": r["strict"], "variant": r["variant"], "undercut": r["undercut"]}
                ys = yard(ctx, ep_sess, s_idx)
                for bk, y in (("orig", adr), ("scaled", ys)):
                    if y is None or y <= 0:
                        continue
                    c[f"o_{bk}"] = h2_walk(ctx, b["close"], y, [], aft)
                ctl.append(c)
    write("h8_rows.tsv", out)
    write("h8_ctl.tsv", ctl)


def write(path, rows):
    cols = []
    for r in rows:
        for c in r:
            if c not in cols:
                cols.append(c)
    with open(HERE / path, "w") as fh:
        fh.write("|".join(cols) + "\n")
        for r in rows:
            fh.write("|".join("" if r.get(c) is None else (f"{r[c]:.6g}" if isinstance(r[c], float) else str(r[c])) for c in cols) + "\n")
    print(f"wrote {path}: {len(rows)} rows")


if __name__ == "__main__":
    ph = sys.argv[1] if len(sys.argv) > 1 else "pop"
    {"pop": phase_pop, "anchor": phase_anchor, "run": phase_run}[ph]()
