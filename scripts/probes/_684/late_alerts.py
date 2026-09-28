#!/usr/bin/env python3
"""#684 FOLLOW-UP (2026-09-28) — what should the live system do with EP alerts that first pass
09:45-09:59 ET? Today: WINDOW_OUT_OF_ORB, never ordered. PRE-REGISTRATION, written BEFORE any
outcome number was computed. $0, read-only, no live code / PLAN.md / prod writes.

POPULATION: live-source ALERTED rows only (the rule this asks about is a submission-window rule,
which only ever applies to an alert). From `orb_live_outcomes.tsv` (the existing frame-B replay):
  LATE    = alerted rows whose first-pass scan time is 09:45-09:59 ET (today's WINDOW_OUT_OF_ORB) —
            99 rows, verified all in [09:45,09:59] (58 at 09:50, 26 at 09:55, 15 at 09:45); holds
            14 of the 35 alerted frame-A (close-based) runners.
  CONTROL = alerted rows first-passing BEFORE 09:45, exactly frame B's own population and result
            (`study_orb_live.py`'s CONTROL treatment is UNCHANGED here — same entry, same fill) —
            164 rows (of 263 alerted-readable; the other 99 are LATE).
Both restricted to ORB-readable rows (has a 09:30 one-minute bar and a 15-session forward outcome);
a row is additionally excluded per-option if `entry_walk` returns `abstain` for THAT option's own
submit/cancel window (a scan-data gap can differ by cancel time, so exclusion is reported per option
where it differs, not assumed identical to frame B's readability).

DATA: reuses `live_entry_bars.tsv` (09:30-16:00 ET, 1-min o/h/l, already pulled) EXTENDED with CLOSE
(`live_entry_bars_full.sql/.tsv`, one new pull, same population, same window — `walk_arm`'s day-0
stop-check needs the bar's close, which `entry_walk` alone did not) — the additional column, not a
new population. Forward daily sessions and prior closes reuse `daily.tsv.gz` (already pulled,
through 2026-09-25) — HORIZON_SESSIONS=40 forward sessions is the ladder's own definition, but the
population's later rows (Aug-Sept scan dates) will run out of stored forward data before 40 sessions;
those settle as `pending` (open, insufficient forward data), reported and EXCLUDED from R-summary
stats, never guessed at.

THE EXIT LADDER — REUSED, not reimplemented. `agents.market_intelligence.live_fill_counterfactuals.
walk_arm` (harvest="live_ladder") + `stack_walk_inputs` + `rule_eras.exit_rules_as_of(TODAY,
signal_type="magna53")`, TODAY = 2026-09-28 (era D, confirmed live: stop_mode=entry_minus_2r,
intraday_partial_r=8.0, breakeven_at_r=3.0, trail_prior_closes=True, breakeven_at_partial=True —
matches the coordinator's own description of era D exactly). This is the SAME mechanism
`sustain_reject_replay.py` already uses for an identically-shaped question (a hypothetical entry,
walked through the live ladder) — its own docstring calls `walk_arm` "REUSED, not reimplemented ...
parity-tested against real fills." The ALTERNATIVE named, `delayed_entry_shadow.compute_settlement`,
implements a STRUCTURALLY DIFFERENT lane (a two-arm M-trail design with its own hold-session horizon,
no partial/breakeven-arm concept) that does not map onto era D's actual parameters — checked, not
assumed, by reading both docstrings; `walk_arm` was chosen because its keyword arguments
(`breakeven_at_partial`, `trail_prior_closes`, `breakeven_at_r`, `ladder_partial`) are a 1:1 mapping
of `rule_eras.exit_rules_as_of`'s era-D fields, `compute_settlement`'s are not.

Gap-throughs charged at the open: ALREADY how `entry_walk` (the fill) and `walk_arm` (the exit, both
day-0 and forward-session stop hits) work — confirmed by reading both, not assumed; no extra code.

THREE OPTIONS FOR LATE ROWS (CONTROL is unchanged — today's rule, already computed):
  Option 1 (move the cutoff): the SAME order as today — ORB = the 09:30 one-minute bar's high/low,
    the SAME admission gates (rt-gap-floor at the submit minute, `validate_orb_entry`'s ATR/
    zero-range check), the SAME stop (entry_minus_2r = 2*orb_low-orb_high, using the TRIGGER
    orb_high/orb_low, not the fill price — the codebase's own convention, `current_era_stop`), the
    SAME R-frame for the +8R target / +3R breakeven arm (entry - orb_low). ONLY the submit time
    (first-pass, 09:45-09:59) and the cancel time move: 10:30 ET primary, 10:00 and 11:00 reported
    beside it.
  Option 2 (fresh breakout): at the first-pass minute, ORB = the running HIGH and LOW from 09:30
    through that minute inclusive (NOT the 09:30 bar alone) + the SAME stop-limit buffer
    (`stop_limit_buy_price`). Protective stop = that running LOW directly (not the 2R formula);
    R = entry - that low (the coordinator's own definition), used for BOTH the stop AND the +8R
    target / +3R breakeven-arm frame (one R, not two). SAME admission gates, applied to this
    option's OWN high/low/ATR — an assumption (the coordinator did not name them for option 2), kept
    for symmetry with option 1 and because they are real infra/risk gates, not artifacts of the
    09:30-bar ORB definition specifically; stated here, not hidden. Cancel = 11:00 ET primary, 10:30
    reported beside it.
  Option 3 (today, skip): the zero line — LATE alerts are never ordered. n=99, 0 fills by
    construction.

OUTCOMES, per option: fills (n, %); runners caught (of the 14 LATE frame-A runners, filled=caught;
and a stop-independent RUN_option >= 5 ADR, same outcome definition as frame B — max high from the
fill through session +15, minus the ACTUAL fill price, over `adr_dollar_ep`); R per trade under era D
(mean realized_r over SETTLED rows only); loss rate (share of settled trades with realized_r < 0);
average loss (mean realized_r among losers); worst single loss (min realized_r); count of losses
beyond -1.5R. Every total is reported ALSO with the two best-R names dropped (a per-option
robustness check, mirroring the main study's own drop-best-two convention) — n this small can be
carried by 1-2 names, and this is flagged as a HINT, not proof, throughout (LATE n=99; a handful of
runners each option catches is not a stable base rate).

THE LINE: measurement only. No recommendation is made; no code, PLAN.md, or prod is touched. Every
number below is stop-independent RUN or R-multiple simulation, never a live order.
"""
from __future__ import annotations

import datetime as dt
import sys
from collections import Counter
from pathlib import Path

_REPO = Path(__file__).resolve().parents[3]
if str(_REPO) not in sys.path:
    sys.path.insert(0, str(_REPO))

from study import add_outcomes, load_daily, load_features

from study_orb_live import (
    ATR_LOOKBACK_DAYS,
    MIN_GAP_PCT_CHANGE,
    PARTIAL_LIVE_DATE,
    RT_GAP_GATE_LIVE,
    compute_atr14_prior,
    entry_walk,
    fnum,
    load_psv,
    stop_limit_buy_price,
    submit_time_and_window,
    true_range,
    validate_orb_entry,
)

from agents.market_intelligence import rule_eras
from agents.market_intelligence.live_fill_counterfactuals import (
    orb_r_frame,
    stack_walk_inputs,
    walk_arm,
)

HERE = Path(__file__).resolve().parent
TODAY = dt.date(2026, 9, 28)
HORIZON_SESSIONS = 40
PRIOR_CLOSES_CAL_DAYS = 40


def load_bars_full() -> dict[tuple[str, str], dict]:
    out: dict[tuple[str, str], dict] = {}
    with (HERE / "live_entry_bars_full.tsv").open() as fh:
        header = None
        for line in fh:
            line = line.rstrip("\n")
            if not line or line.startswith("(") or line.startswith("Output format") or line.startswith("Field separator"):
                continue
            parts = line.split("|")
            if header is None:
                header = parts
                continue
            t, d, hhmm, o, h, l, c = parts
            if not (o and h and l and c):
                continue
            k = (t, d)
            if k not in out:
                out[k] = {"list": [], "by_hhmm": {}}
            bar = {"m": hhmm, "o": float(o), "h": float(h), "l": float(l), "c": float(c)}
            out[k]["list"].append(bar)
            out[k]["by_hhmm"][hhmm] = bar
    return out


def sessions_for(daily_bars: list, i0: int) -> list[tuple[dt.date, dict | None]]:
    fwd = daily_bars[i0 + 1:i0 + 1 + HORIZON_SESSIONS]
    out = []
    for b in fwd:
        d = dt.date.fromisoformat(b[0])
        out.append((d, {"o": b[1], "h": b[2], "l": b[3], "c": b[4]}))
    return out


def prior_closes_for(daily_bars: list, i0: int, fill_date: str) -> list[float]:
    cut = (dt.date.fromisoformat(fill_date) - dt.timedelta(days=PRIOR_CLOSES_CAL_DAYS)).isoformat()
    return [b[4] for b in daily_bars[:i0] if b[0] >= cut]


def walk_one(entry_px: float, stop_px: float, orb_low_for_r: float, day0_bars: list,
             fill_hhmm: str, sessions: list, prior_closes: list, fill_day: dt.date) -> dict:
    fill_idx = next((i for i, b in enumerate(day0_bars) if b["m"] == fill_hhmm), None)
    if fill_idx is None:
        return {"status": "abstain", "reason": "fill_bar_not_in_day0_bars"}
    rules = rule_eras.exit_rules_as_of(TODAY, signal_type="magna53")
    target, walk_kw = stack_walk_inputs(rules, entry_px, orb_low_for_r)
    return walk_arm(entry=entry_px, stop=stop_px, target=target, day0_bars=day0_bars,
                     fill_idx=fill_idx, sessions=sessions, prior_closes=prior_closes,
                     harvest="live_ladder", fill_day=fill_day, **walk_kw)


def current_era_stop_2r(orb_high: float, orb_low: float) -> float:
    return 2 * orb_low - orb_high


def running_high_low(day0_bars: list, through_hhmm: str) -> tuple[float | None, float | None]:
    """The day's high/low SO FAR strictly BEFORE the submit minute — the submit minute's own bar
    is excluded on purpose (bug found by advisor review, 2026-09-28): including it made the
    trigger equal to that very bar's own high, so `entry_walk` scanning from `through_hhmm`
    (inclusive) triggered on it trivially — a look-ahead fill at a price the order could not have
    known before that bar printed. 3 of the original 15 option-2 fills were exactly this artifact
    (fill_minute == first_pass_time); re-verified 0 after this fix."""
    bars = [b for b in day0_bars if b["m"] >= "09:30" and b["m"] < through_hhmm]
    if not bars:
        return None, None
    return max(b["h"] for b in bars), min(b["l"] for b in bars)


def rt_gap_ok(d: str, submit_hhmm: str, bk: dict, prev_close: float | None) -> bool:
    if d < RT_GAP_GATE_LIVE:
        return True
    floor_pct = 9.0 if d >= MIN_GAP_PCT_CHANGE else 10.0
    b = bk["by_hhmm"].get(submit_hhmm)
    if b is None or not prev_close:
        return True  # fail open, matches check_rt_gap_floor
    rt_gap = (b["o"] - prev_close) / prev_close * 100
    return rt_gap >= floor_pct


def replay_option1(r: dict, bars_full: dict, daily: dict, cancel_hhmm: str) -> dict:
    t, d = r["ticker"], r["scan_date"]
    bk = bars_full.get((t, d))
    if bk is None:
        return {"status": "no_bars"}
    orb_bar = bk["by_hhmm"].get("09:30")
    if orb_bar is None:
        return {"status": "no_930_bar"}
    orb_high, orb_low = orb_bar["h"], orb_bar["l"]
    daily_bars = daily.get(t, [])
    dates = [b[0] for b in daily_bars]
    i0 = dates.index(d) if d in dates else None
    prior_hlc = []
    if i0 is not None:
        cut = (dt.date.fromisoformat(d) - dt.timedelta(days=ATR_LOOKBACK_DAYS)).isoformat()
        prior_hlc = [(b[2], b[3], b[4]) for b in daily_bars[:i0] if b[0] >= cut]
    atr14 = compute_atr14_prior(prior_hlc)
    submit = r["first_pass_time"]  # already >=09:45; no 09:31 floor needed
    prev_close = daily_bars[i0 - 1][4] if (i0 is not None and i0 >= 1) else None
    if not rt_gap_ok(d, submit, bk, prev_close):
        return {"status": "gap_below_floor"}
    valid, reason = validate_orb_entry(orb_high, orb_low, atr14)
    if not valid:
        return {"status": f"orb_invalid:{reason}"}
    fill = entry_walk([(b["m"], b["o"], b["h"], b["l"]) for b in bk["list"]], orb_high, submit, cancel_hhmm)
    if fill["status"] != "filled":
        return fill
    entry_px = fill["px"]
    stop = current_era_stop_2r(orb_high, orb_low)
    if entry_px - stop <= 0:
        return {"status": "abstain", "reason": "nonpositive_risk"}
    sessions = sessions_for(daily_bars, i0) if i0 is not None else []
    prior_closes = prior_closes_for(daily_bars, i0, d) if i0 is not None else []
    walk = walk_one(entry_px, stop, orb_low, bk["list"], fill["minute"], sessions, prior_closes,
                     dt.date.fromisoformat(d))
    res = {"status": "filled", "entry_px": entry_px, "stop": stop, "fill_minute": fill["minute"],
           "walk": walk, "adr_dollar_ep": r.get("adr_dollar_ep"), "daily_bars": daily_bars, "i0": i0}
    add_run_xadr(res, bk["list"])
    return res


def replay_option2(r: dict, bars_full: dict, daily: dict, cancel_hhmm: str) -> dict:
    t, d = r["ticker"], r["scan_date"]
    bk = bars_full.get((t, d))
    if bk is None:
        return {"status": "no_bars"}
    submit = r["first_pass_time"]
    high2, low2 = running_high_low(bk["list"], submit)
    if high2 is None:
        return {"status": "no_bars_through_submit"}
    daily_bars = daily.get(t, [])
    dates = [b[0] for b in daily_bars]
    i0 = dates.index(d) if d in dates else None
    prior_hlc = []
    if i0 is not None:
        cut = (dt.date.fromisoformat(d) - dt.timedelta(days=ATR_LOOKBACK_DAYS)).isoformat()
        prior_hlc = [(b[2], b[3], b[4]) for b in daily_bars[:i0] if b[0] >= cut]
    atr14 = compute_atr14_prior(prior_hlc)
    prev_close = daily_bars[i0 - 1][4] if (i0 is not None and i0 >= 1) else None
    if not rt_gap_ok(d, submit, bk, prev_close):
        return {"status": "gap_below_floor"}
    valid, reason = validate_orb_entry(high2, low2, atr14)
    if not valid:
        return {"status": f"orb_invalid:{reason}"}
    fill = entry_walk([(b["m"], b["o"], b["h"], b["l"]) for b in bk["list"]], high2, submit, cancel_hhmm)
    if fill["status"] != "filled":
        return fill
    entry_px = fill["px"]
    stop = low2
    if entry_px - stop <= 0:
        return {"status": "abstain", "reason": "nonpositive_risk"}
    sessions = sessions_for(daily_bars, i0) if i0 is not None else []
    prior_closes = prior_closes_for(daily_bars, i0, d) if i0 is not None else []
    walk = walk_one(entry_px, stop, low2, bk["list"], fill["minute"], sessions, prior_closes,
                     dt.date.fromisoformat(d))
    res = {"status": "filled", "entry_px": entry_px, "stop": stop, "fill_minute": fill["minute"],
           "walk": walk, "adr_dollar_ep": r.get("adr_dollar_ep"), "daily_bars": daily_bars, "i0": i0}
    add_run_xadr(res, bk["list"])
    return res


def replay_control(r: dict, bars_full: dict, daily: dict) -> dict:
    """CONTROL under today's rule, unchanged — mirrors study_orb_live.py's per-row logic exactly,
    just walked through the era-D exit ladder in addition (frame B only computed RUN_B, not R)."""
    t, d = r["ticker"], r["scan_date"]
    bk = bars_full.get((t, d))
    if bk is None:
        return {"status": "no_bars"}
    orb_bar = bk["by_hhmm"].get("09:30")
    if orb_bar is None:
        return {"status": "no_930_bar"}
    orb_high, orb_low = orb_bar["h"], orb_bar["l"]
    daily_bars = daily.get(t, [])
    dates = [b[0] for b in daily_bars]
    i0 = dates.index(d) if d in dates else None
    prior_hlc = []
    if i0 is not None:
        cut = (dt.date.fromisoformat(d) - dt.timedelta(days=ATR_LOOKBACK_DAYS)).isoformat()
        prior_hlc = [(b[2], b[3], b[4]) for b in daily_bars[:i0] if b[0] >= cut]
    atr14 = compute_atr14_prior(prior_hlc)
    submit, window_out = submit_time_and_window(r["first_pass_time"])
    if window_out:
        return {"status": "window_out_of_orb"}
    prev_close = daily_bars[i0 - 1][4] if (i0 is not None and i0 >= 1) else None
    if not rt_gap_ok(d, submit, bk, prev_close):
        return {"status": "gap_below_floor"}
    valid, reason = validate_orb_entry(orb_high, orb_low, atr14)
    if not valid:
        return {"status": f"orb_invalid:{reason}"}
    cancel = "10:00" if d >= PARTIAL_LIVE_DATE else None
    fill = entry_walk([(b["m"], b["o"], b["h"], b["l"]) for b in bk["list"]], orb_high, submit, cancel)
    if fill["status"] != "filled":
        return fill
    entry_px = fill["px"]
    stop = current_era_stop_2r(orb_high, orb_low)
    if entry_px - stop <= 0:
        return {"status": "abstain", "reason": "nonpositive_risk"}
    sessions = sessions_for(daily_bars, i0) if i0 is not None else []
    prior_closes = prior_closes_for(daily_bars, i0, d) if i0 is not None else []
    walk = walk_one(entry_px, stop, orb_low, bk["list"], fill["minute"], sessions, prior_closes,
                     dt.date.fromisoformat(d))
    res = {"status": "filled", "entry_px": entry_px, "stop": stop, "fill_minute": fill["minute"],
           "walk": walk, "adr_dollar_ep": r.get("adr_dollar_ep"), "daily_bars": daily_bars, "i0": i0}
    add_run_xadr(res, bk["list"])
    return res


def add_run_xadr(res: dict, day0_bars: list) -> None:
    """Stop-independent RUN, same methodology as frame B: max(post-fill day-0 high, sessions
    +1..+15 daily highs) - entry_px, over adr_dollar_ep. Mutates res in place."""
    res["run_xadr"] = None
    res["runner5"] = None
    if res.get("status") != "filled" or res.get("i0") is None or res.get("adr_dollar_ep") is None:
        return
    daily_bars = res["daily_bars"]
    i0 = res["i0"]
    fwd = daily_bars[i0 + 1:i0 + 16]
    if len(fwd) < 15:
        return
    fill_hhmm = res["fill_minute"]
    post_fill_max = max((b["h"] for b in day0_bars if b["m"] >= fill_hhmm), default=None)
    if post_fill_max is None:
        return
    mx = max([post_fill_max] + [b[2] for b in fwd])
    run = (mx - res["entry_px"]) / res["adr_dollar_ep"]
    res["run_xadr"] = run
    res["runner5"] = int(run >= 5)


def summarize(rows_res: list[tuple[dict, dict]], label: str, drop_names: set[tuple[str, str]] | None = None) -> dict:
    """rows_res: [(pop_row, replay_result), ...]"""
    if drop_names:
        rows_res = [(r, res) for r, res in rows_res if (r["ticker"], r["scan_date"]) not in drop_names]
    filled = [(r, res) for r, res in rows_res if res.get("status") == "filled"]
    n = len(rows_res)
    nf = len(filled)
    settled = [(r, res) for r, res in filled if res["walk"]["status"] == "settled"]
    rs = []
    for r, res in settled:
        risk = res["entry_px"] - res["stop"]
        pnl = res["walk"]["pnl_per_share"]
        if risk > 0 and pnl is not None:
            rs.append((r["ticker"], r["scan_date"], pnl / risk))
    losers = [x for x in rs if x[2] < 0]
    return {
        "label": label, "n": n, "n_filled": nf, "pct_filled": 100 * nf / n if n else 0.0,
        "n_settled": len(rs), "rs": rs,
        "mean_r": (sum(x[2] for x in rs) / len(rs)) if rs else None,
        "loss_rate": (len(losers) / len(rs)) if rs else None,
        "avg_loss": (sum(x[2] for x in losers) / len(losers)) if losers else None,
        "worst_loss": min((x[2] for x in rs), default=None),
        "n_beyond_neg1p5": sum(1 for x in rs if x[2] < -1.5),
    }


def fmt_summary(s: dict) -> str:
    mean_r = f"{s['mean_r']:+.2f}R" if s["mean_r"] is not None else "n/a"
    loss_rate = f"{100*s['loss_rate']:.0f}%" if s["loss_rate"] is not None else "n/a"
    avg_loss = f"{s['avg_loss']:+.2f}R" if s["avg_loss"] is not None else "n/a"
    worst = f"{s['worst_loss']:+.2f}R" if s["worst_loss"] is not None else "n/a"
    return (f"{s['label']}: n={s['n']} filled={s['n_filled']} ({s['pct_filled']:.0f}%) "
            f"settled={s['n_settled']} R/trade={mean_r} loss_rate={loss_rate} avg_loss={avg_loss} "
            f"worst={worst} beyond-1.5R={s['n_beyond_neg1p5']}")


def best_two(rs: list[tuple[str, str, float]]) -> set[tuple[str, str]]:
    top = sorted(rs, key=lambda x: -x[2])[:2]
    return {(t, d) for t, d, _ in top}


def main() -> None:
    rows = load_features()
    daily = load_daily()
    add_outcomes(rows, daily)
    pop = {(r["ticker"], r["scan_date"]): r for r in load_psv(HERE / "pop.tsv")}
    bars_full = load_bars_full()

    import csv as _csv
    with (HERE / "orb_live_outcomes.tsv").open() as fh:
        outc_rows = list(_csv.DictReader(fh, delimiter="\t"))
    outc_by_key = {(r["ticker"], r["scan_date"]): r for r in outc_rows}

    idx = {(r["ticker"], r["scan_date"]): r for r in rows}

    late_keys = [(r["ticker"], r["scan_date"]) for r in outc_rows
                 if r["alerted"] == "1" and r["orb_status"].startswith("window_out_of_orb")]
    control_keys = [(r["ticker"], r["scan_date"]) for r in outc_rows
                     if r["alerted"] == "1" and r["orb_readable"] == "1"
                     and not r["orb_status"].startswith("window_out_of_orb")]

    out: list[str] = []
    p = out.append
    p(f"#684 LATE-ALERTS FOLLOW-UP RESULTS — LATE n={len(late_keys)}, CONTROL n={len(control_keys)}")
    p(f"TODAY (era resolution) = {TODAY.isoformat()}, era D rules: {rule_eras.exit_rules_as_of(TODAY, signal_type='magna53')}")
    p("")

    late_pop = []
    for t, d in late_keys:
        r = dict(idx[(t, d)])
        r["first_pass_time"] = pop[(t, d)]["first_pass_time"]
        late_pop.append(r)
    control_pop = []
    for t, d in control_keys:
        r = dict(idx[(t, d)])
        r["first_pass_time"] = pop[(t, d)]["first_pass_time"]
        control_pop.append(r)

    late_runner_keys = {(r["ticker"], r["scan_date"]) for r in late_pop if r.get("runner5")}
    p(f"LATE frame-A runners (close-based, of 35 alerted total): {len(late_runner_keys)} — "
      + ", ".join(f"{t} {d}" for t, d in sorted(late_runner_keys)))
    p("")

    # ── CONTROL (today's rule, unchanged) ──────────────────────────────────────────
    control_res = [(r, replay_control(r, bars_full, daily)) for r in control_pop]
    status_ct = Counter(res["status"].split(":")[0] for _, res in control_res)
    p(f"CONTROL status breakdown: {dict(status_ct)}")
    s_control = summarize(control_res, "CONTROL (today's rule)")
    p(fmt_summary(s_control))
    filled_rs_control = [x for _, res in control_res if res.get("status") == "filled" for x in [None]]
    rs_control = s_control["rs"]
    bt2_control = best_two(rs_control) if len(rs_control) >= 3 else set()
    s_control_bt2 = summarize(control_res, "CONTROL, drop-best-two", bt2_control) if bt2_control else None
    if s_control_bt2:
        p(fmt_summary(s_control_bt2))
    runners_caught_control = sum(1 for r, res in control_res if res.get("runner5"))
    p(f"  CONTROL stop-independent runners (RUN>=5 ADR from fill): {runners_caught_control} of {s_control['n_filled']} filled")
    p("")

    # ── Option 3: skip (zero line) ──────────────────────────────────────────────────
    p(f"OPTION 3 (today, skip LATE alerts): n={len(late_pop)} filled=0 (0%) — the zero line.")
    p("")

    # ── Option 1: move the cutoff (10:30 primary; 10:00, 11:00 alongside) ───────────
    for cancel_hhmm, tag in (("10:30", "PRIMARY"), ("10:00", "alt"), ("11:00", "alt")):
        res1 = [(r, replay_option1(r, bars_full, daily, cancel_hhmm)) for r in late_pop]
        status_ct1 = Counter(res["status"].split(":")[0] for _, res in res1)
        p(f"OPTION 1, cancel {cancel_hhmm} ET [{tag}]: status {dict(status_ct1)}")
        s1 = summarize(res1, f"OPTION 1 cancel={cancel_hhmm}")
        p(fmt_summary(s1))
        rs1 = s1["rs"]
        bt2_1 = best_two(rs1) if len(rs1) >= 3 else set()
        if bt2_1:
            p(fmt_summary(summarize(res1, f"OPTION 1 cancel={cancel_hhmm}, drop-best-two", bt2_1)))
        runners_caught1 = sum(1 for r, res in res1 if res.get("runner5"))
        late_runners_caught1 = sum(1 for r, res in res1
                                    if (r["ticker"], r["scan_date"]) in late_runner_keys and res.get("status") == "filled")
        p(f"  OPTION 1 [{cancel_hhmm}]: LATE frame-A runners caught (filled) = {late_runners_caught1} of {len(late_runner_keys)}; "
          f"stop-independent runners (RUN>=5 ADR from fill) = {runners_caught1} of {s1['n_filled']} filled")
        p("")
        if cancel_hhmm == "10:30":
            primary1 = (res1, s1, bt2_1, late_runners_caught1, runners_caught1)

    # ── Option 2: fresh breakout (11:00 primary; 10:30 alongside) ───────────────────
    for cancel_hhmm, tag in (("11:00", "PRIMARY"), ("10:30", "alt")):
        res2 = [(r, replay_option2(r, bars_full, daily, cancel_hhmm)) for r in late_pop]
        status_ct2 = Counter(res["status"].split(":")[0] for _, res in res2)
        p(f"OPTION 2, cancel {cancel_hhmm} ET [{tag}]: status {dict(status_ct2)}")
        s2 = summarize(res2, f"OPTION 2 cancel={cancel_hhmm}")
        p(fmt_summary(s2))
        rs2 = s2["rs"]
        bt2_2 = best_two(rs2) if len(rs2) >= 3 else set()
        if bt2_2:
            p(fmt_summary(summarize(res2, f"OPTION 2 cancel={cancel_hhmm}, drop-best-two", bt2_2)))
        runners_caught2 = sum(1 for r, res in res2 if res.get("runner5"))
        late_runners_caught2 = sum(1 for r, res in res2
                                    if (r["ticker"], r["scan_date"]) in late_runner_keys and res.get("status") == "filled")
        p(f"  OPTION 2 [{cancel_hhmm}]: LATE frame-A runners caught (filled) = {late_runners_caught2} of {len(late_runner_keys)}; "
          f"stop-independent runners (RUN>=5 ADR from fill) = {runners_caught2} of {s2['n_filled']} filled")
        p("")
        if cancel_hhmm == "11:00":
            primary2 = (res2, s2, bt2_2, late_runners_caught2, runners_caught2)

    text = "\n".join(out) + "\n"
    (HERE / "late_alerts_out.txt").write_text(text)
    print(text)

    # per-row detail for audit
    with (HERE / "late_alerts_detail.tsv").open("w") as fh:
        fh.write("group\tticker\tscan_date\tstatus\tentry_px\tstop\tfill_minute\twalk_status\trealized_r\trun_xadr\trunner5\n")
        def dump(group, rows_res):
            for r, res in rows_res:
                risk = (res.get("entry_px", 0) - res.get("stop", 0)) if res.get("status") == "filled" else None
                walk_status = res.get("walk", {}).get("status", "") if res.get("status") == "filled" else ""
                pnl = res.get("walk", {}).get("pnl_per_share") if res.get("status") == "filled" else None
                rr = (pnl / risk) if (pnl is not None and risk not in (None, 0)) else None
                rr_s = "" if rr is None else f"{rr:.3f}"
                run_s = "" if res.get("run_xadr") is None else f"{res['run_xadr']:.3f}"
                fh.write(f"{group}\t{r['ticker']}\t{r['scan_date']}\t{res.get('status')}\t"
                         f"{res.get('entry_px','')}\t{res.get('stop','')}\t{res.get('fill_minute','')}\t"
                         f"{walk_status}\t{rr_s}\t{run_s}\t{res.get('runner5','')}\n")
        dump("CONTROL", control_res)
        dump("OPTION1_1030", primary1[0])
        dump("OPTION2_1100", primary2[0])


if __name__ == "__main__":
    main()
