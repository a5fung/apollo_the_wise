#!/usr/bin/env python3
"""#684 ADDENDUM v2 (2026-09-28) — REPLACES the first ORB addendum, which used a 15-minute
(09:30-09:44) opening-range high. That range does not exist in the live code (see the v1 note
below); this file replays the ACTUAL live MAGNA53 entry mechanics bar-by-bar, mirroring
`entry_pipeline.py` / `order_manager.py` / `alpaca_client.get_first_bar` exactly, the same way
`sustain_reject_replay.entry_walk` already mirrors `scripts/ep_replay.entry_walk` (the precedent
this file follows, rather than reinventing the mechanics a third time — `entry_walk` below is
copied from `sustain_reject_replay.py` verbatim, adapted only to read plain dict bars instead of
asyncpg rows).

PRE-REGISTRATION (written before any frame-B outcome number was computed):

ORB = the single 09:30-09:31 ET one-minute bar's high/low (`alpaca_client.get_first_bar`,
`order_manager.py:564-565` `orb_high = orb_bar["high"]`). NOT a 09:30-09:44 aggregate — that was
this addendum's own earlier error (v1, retracted; see the one-line note at the end of this
docstring). Verified by reading `entry_pipeline.fetch_orb_bar_with_retry` -> `alpaca.get_first_bar`
(`agents/market_intelligence/broker/alpaca_client.py:839`, docstring "Get the first 1-minute bar").

SUBMIT TIME = the row's own scan time, mirroring `sustain_reject_replay.submit_time_and_window`
exactly: ALERTED rows use the FIRST-PASS tick (`pop.tsv: first_pass_time` — the earliest tick with
filter_reason NULL and score_tier set); REJECTED rows never passed, so there is no "first pass" —
they use the row's own CHOSEN tick (`pop.tsv: scan_time`, the same DISTINCT-ON tick that already
supplies every other feature for that row: highest ep_score among that ticker/day's ticks, ties ->
latest), applied as the hypothetical submit time (coordinator's instruction: "apply the same
mechanics at their scan time"). Floored UP to 09:31 (an order cannot submit before the open — a
pre-market or 09:30 tick still submits at 09:31, like every real MAGNA53 admission). A tick at or
after 09:45 ET is WINDOW_OUT_OF_ORB (CLAUDE.md's own submission-window rule, `scheduler.py:1119`,
`skip_reasons.WINDOW_OUT_OF_ORB`) -- the order is NEVER PLACED. Counted, not simulated.

ADMISSION (runs even for a submit inside the window, BEFORE any fill can happen):
  1. `validate_orb_entry(orb_high, orb_low, atr14)` (`backtester/filters.py:207`, the single
     authoritative rule `order_manager.py` calls before building a spec): orb_range <= 0 ->
     rejected (SETUP_ZERO_RANGE); orb_range > 1.5x ATR-14-prior -> rejected (SETUP_STOP_TOO_WIDE).
     ATR-14-prior mirrors `alert_rank_shadow.compute_atr14_prior` (simple mean of the last 14 true
     ranges over the PRIOR 40 calendar days, >= 10 prior daily rows required else the ATR check is
     skipped — "let it through", matching the real function's own fail-open on thin history).
  2. Real-time gap re-check (`entry_pipeline.check_rt_gap_floor`, wired for MAGNA53 via
     `live_tracker._MAGNA53_MIN_GAP_PCT`, step 4b of `submit_trade_entry` -- read directly in code,
     not assumed): toggle `ep_rt_entry_gap_recheck` went live 2026-08-02 (SSoT
     `docs/setups/magna53_ep.md:1127`) -- OFF (not modeled) before that date, ON from 2026-08-02
     onward; floor = `MIN_GAP_PCT` = 10.0% before 2026-08-19, 9.0% from 2026-08-19 (the SAME
     signed change `docs/setups/magna53_ep.md:1917` documents). Real-time price is
     `alpaca.get_latest_trade` (a tick); this replay approximates it with the SUBMIT-minute bar's
     OPEN (the finest granularity available from stored minute bars) -- flagged as an
     approximation, not exact tick data. Missing submit-minute price -> fails OPEN (matches the
     real function's own fail-open on a data miss).
  3. Fade guard (`check_fade_guard`, step 4 of `submit_trade_entry`) -- VERIFIED, not assumed: the
     real MAGNA53 call site (`live_tracker.py:603`) passes `fade_midpoint_ratio=None` explicitly
     ("Sonnet+Perplexity validation + ATR stop width + 10:00 ET cleanup already cover dead-cat
     fills. Midpoint check was over-strict; drop it.") -- the guard is a NO-OP for MAGNA53 HIGH and
     is not modeled (there is nothing to model).

FILL (only if admission passes): `entry_walk` below -- mirrors `sustain_reject_replay.entry_walk`
exactly (limit = `stop_limit_buy_price(orb_high)` = the 0.5%-or-$0.02 buffer above the trigger;
scans 1-minute bars from `submit` to `cancel`; a bar already trading above the trigger AT submission
fills immediately at that bar's own open-or-limit, same as any later bar -- the code does not treat
the first scanned bar specially, so neither does this replay). CANCEL = 10:00 ET for scan_date >=
2026-08-01 (`rule_eras.PARTIAL_LIVE_DATE`, when the +2R partial and the 10:00 cleanup went live
together); before that date there was NO cancel (`sustain_reject_replay.entry_cancel_asof`'s own
docstring: "era-A fills as late as 11:35 prove no cancel then") -- the order can fill any time
through the close. A row with too few minute bars in its own scan window to tell whether a cross
happened is ABSTAIN (unreadable), never guessed either way.

OUTCOME (RUN_B): (max high from the fill minute through session +15 - the ACTUAL FILL PRICE, not
the trigger) / adr_dollar_ep (frame A's own denominator, unchanged). Day 0's own contribution is
read from the SAME `mi_intraday_bars` pull used for the whole replay (fill minute through 16:00);
only sessions +1..+15 fall back to `mi_daily_closes`, as frame A already does.

NOT MODELED (portfolio-state gates -- flagged, not silently skipped): `_check_safeguards`
(LIVE_TRADING_ENABLED, /pause, max-concurrent-positions, daily-loss limit, the drawdown breaker) and
the per-strategy/composite sizing multiplier. These depend on the REST of the book at the exact
historical moment of each hypothetical entry, which this per-name replay does not reconstruct --
same scope boundary the original #684 study drew (a selection question, not a portfolio
simulation). A row marked FILLED here is "would have been submitted and would have triggered,"
never "would have been an executed live trade regardless of the rest of the book."

SPLIT / DRAWS / PERMUTATION / PASS BAR: unchanged from `study.py` -- same 63 features, same
DISCOVERY/HELD-OUT split, same week-block permutation (2,000 draws, seed 684), same four-condition
bar, same noise band.

v1 RETRACTED: an earlier version of this addendum measured FILLED against a 09:30-09:44 15-minute
"opening range" that does not exist in the live code (the live ORB is the single 09:30 bar). Its
numbers are NOT carried forward as findings -- see the one-line note in the replacement addendum.
"""
from __future__ import annotations

import random
from collections import Counter, defaultdict
from pathlib import Path

from study import (
    DRAWS,
    LABELLED,
    N_PERM,
    SEED,
    add_outcomes,
    auc,
    diff_stat,
    fav_mask,
    load_daily,
    load_features,
    perm_p,
    rate,
    tercile_cuts,
)
from study_orb import fmt_rate, per_feature, run_pass

HERE = Path(__file__).resolve().parent

PARTIAL_LIVE_DATE = "2026-08-01"        # cancel=10:00 from this date on; None before
RT_GAP_GATE_LIVE = "2026-08-02"         # ep_rt_entry_gap_recheck toggle went live
MIN_GAP_PCT_CHANGE = "2026-08-19"       # MIN_GAP_PCT 10.0 -> 9.0
ATR_LOOKBACK_DAYS = 40                  # calendar days, matches sustain_reject_replay.ATR_LOOKBACK_CAL_DAYS


def fnum(x):
    try:
        return float(x)
    except (TypeError, ValueError):
        return None


def load_psv(path: Path) -> list[dict]:
    rows: list[dict] = []
    header: list[str] | None = None
    with path.open() as fh:
        for line in fh:
            line = line.rstrip("\n")
            if not line or line.startswith("(") or line.startswith("Output format") or line.startswith("Field separator"):
                continue
            parts = line.split("|")
            if header is None:
                header = parts
                continue
            rows.append(dict(zip(header, parts)))
    return rows


def load_bars() -> dict[tuple[str, str], dict]:
    """(ticker, scan_date) -> {"list": [(hhmm,o,h,l), ...] sorted, "by_hhmm": {hhmm: (o,h,l)}}."""
    out: dict[tuple[str, str], dict] = defaultdict(lambda: {"list": [], "by_hhmm": {}})
    with (HERE / "live_entry_bars.tsv").open() as fh:
        header = None
        for line in fh:
            line = line.rstrip("\n")
            if not line or line.startswith("(") or line.startswith("Output format") or line.startswith("Field separator"):
                continue
            parts = line.split("|")
            if header is None:
                header = parts
                continue
            t, d, hhmm, o, h, l = parts
            if not (o and h and l):
                continue
            o, h, l = float(o), float(h), float(l)
            k = (t, d)
            out[k]["list"].append((hhmm, o, h, l))
            out[k]["by_hhmm"][hhmm] = (o, h, l)
    return out


def _mins(hhmm: str) -> int:
    hh, mm = hhmm.split(":")
    return int(hh) * 60 + int(mm)


def true_range(h: float, l: float, prev_close: float) -> float:
    return max(h - l, abs(h - prev_close), abs(l - prev_close))


def compute_atr14_prior(prior_hlc: list[tuple[float, float, float]]) -> float | None:
    """Mirrors alert_rank_shadow.compute_atr14_prior exactly."""
    if len(prior_hlc) < 10:
        return None
    trs = []
    for i in range(1, len(prior_hlc)):
        h, l, _ = prior_hlc[i]
        _, _, prev_close = prior_hlc[i - 1]
        trs.append(true_range(h, l, prev_close))
    if not trs:
        return None
    window = trs[-14:]
    return sum(window) / len(window)


def validate_orb_entry(orb_high: float, orb_low: float, atr_14: float | None) -> tuple[bool, str | None]:
    """Mirrors backtester.filters.validate_orb_entry exactly."""
    orb_range = orb_high - orb_low
    if orb_range <= 0:
        return False, "setup:zero_range"
    if atr_14 and atr_14 > 0 and orb_range > 1.5 * atr_14:
        return False, f"setup:stop_too_wide:{orb_range:.2f}>1.5x_ATR_{atr_14:.2f}"
    return True, None


def stop_limit_buy_price(stop_price: float) -> float:
    """Mirrors order_manager.stop_limit_buy_price / sustain_reject_replay._stop_limit_buy_price exactly."""
    return round(max(stop_price * 1.005, stop_price + 0.02), 2)


def submit_time_and_window(t_hhmm: str) -> tuple[str | None, bool]:
    """Mirrors sustain_reject_replay.submit_time_and_window exactly (string HH:MM arithmetic)."""
    if t_hhmm >= "09:45":
        return None, True
    return max(t_hhmm, "09:31"), False


def entry_cancel_asof(scan_date: str) -> str | None:
    return "10:00" if scan_date >= PARTIAL_LIVE_DATE else None


def entry_walk(bars: list[tuple[str, float, float, float]], orb_high: float, submit: str, cancel: str | None) -> dict:
    """Mirrors sustain_reject_replay.entry_walk exactly (dict-of-tuples instead of asyncpg rows)."""
    limit = stop_limit_buy_price(orb_high)
    limit_armed = False
    window = [b for b in bars if b[0] >= submit and (cancel is None or b[0] < cancel)]
    for hhmm, o, h, l in window:
        if limit_armed:
            if l <= limit:
                return {"status": "filled", "px": limit, "minute": hhmm}
            continue
        if o >= orb_high:
            if o <= limit:
                return {"status": "filled", "px": o, "minute": hhmm}
            limit_armed = True
            if l <= limit:
                return {"status": "filled", "px": limit, "minute": hhmm}
        elif h >= orb_high:
            return {"status": "filled", "px": orb_high, "minute": hhmm}
    if limit_armed:
        return {"status": "no_entry", "reason": "triggered_above_limit_never_filled"}
    end = cancel if cancel is not None else "16:00"
    expected = max(0, _mins(end) - _mins(max(submit, "09:30")))
    if len(window) < expected:
        return {"status": "abstain", "reason": f"entry_window_gaps:{expected-len(window)}_of_{expected}"}
    return {"status": "no_entry", "reason": "never_crossed_orb_high"}


def main() -> None:
    rows = load_features()
    daily = load_daily()
    add_outcomes(rows, daily)  # frame A, unchanged, reused for the labelled-EP / comparison columns
    for r in rows:
        if r.get("ALERT_expct_scheduled") in ("scheduled", "unscheduled"):
            r["ALERT_expct_unscheduled"] = 1.0 if r["ALERT_expct_scheduled"] == "unscheduled" else 0.0
        else:
            r["ALERT_expct_unscheduled"] = None

    pop = {(r["ticker"], r["scan_date"]): r for r in load_psv(HERE / "pop.tsv")}
    bars_by_key = load_bars()

    counters = Counter()
    for r in rows:
        t, d = r["ticker"], r["scan_date"]
        r["orb_status"] = None
        r["orb_readable"] = 0
        r["filled"] = None
        r["fill_minute"] = None
        r["entry_px"] = None
        r["run_xadr_B"] = None
        r["runnerB5"] = None
        r["runnerB8"] = None

        has_outcome_window = r.get("runner5") is not None
        if not has_outcome_window:
            r["orb_status"] = "no_15session_outcome"
            counters["unreadable_no_outcome"] += 1
            continue

        pr = pop.get((t, d), {})
        t_scan = pr.get("first_pass_time") if r["alerted"] else pr.get("scan_time")
        if not t_scan:
            r["orb_status"] = "no_scan_time"
            counters["unreadable_no_scan_time"] += 1
            continue

        submit, window_out = submit_time_and_window(t_scan)
        if window_out:
            r["orb_status"] = "window_out_of_orb"
            r["filled"] = 0
            r["runnerB5"], r["runnerB8"] = 0, 0
            r["orb_readable"] = 1
            counters["window_out_of_orb"] += 1
            continue

        bk = bars_by_key.get((t, d))
        orb_bar = bk["by_hhmm"].get("09:30") if bk else None
        if orb_bar is None:
            r["orb_status"] = "no_930_bar"
            counters["unreadable_no_930_bar"] += 1
            continue
        orb_open, orb_high, orb_low = orb_bar

        daily_bars = daily.get(t, [])
        dates = [b[0] for b in daily_bars]
        i0 = dates.index(d) if d in dates else None
        prior_cut = None
        prior_hlc: list[tuple[float, float, float]] = []
        if i0 is not None:
            # 40 calendar days back, prior sessions only (matches ATR_LOOKBACK_CAL_DAYS)
            import datetime as _dt
            cut = (_dt.date.fromisoformat(d) - _dt.timedelta(days=ATR_LOOKBACK_DAYS)).isoformat()
            prior_hlc = [(b[2], b[3], b[4]) for b in daily_bars[:i0] if b[0] >= cut]
        atr14 = compute_atr14_prior(prior_hlc)

        # Real pipeline order (entry_pipeline.submit_trade_entry): step 4b rt-gap-floor runs
        # BEFORE step 5's spec_builder (which is where validate_orb_entry lives, order_manager.py
        # ~L569) -- checked here in that order so the ATTRIBUTED reason for a never-placed row
        # matches which gate the real pipeline would have hit FIRST (does not change the
        # fill/no-fill bottom line, only which reason label a row failing BOTH gates gets).
        gap_blocked = False
        if d >= RT_GAP_GATE_LIVE:
            floor_pct = 9.0 if d >= MIN_GAP_PCT_CHANGE else 10.0
            prev_close = daily_bars[i0 - 1][4] if (i0 is not None and i0 >= 1) else None
            submit_bar = bk["by_hhmm"].get(submit) if bk else None
            if submit_bar is not None and prev_close:
                rt_price = submit_bar[0]
                rt_gap = (rt_price - prev_close) / prev_close * 100
                if rt_gap < floor_pct:
                    gap_blocked = True
        if gap_blocked:
            r["orb_status"] = "gap_below_floor"
            r["filled"] = 0
            r["runnerB5"], r["runnerB8"] = 0, 0
            r["orb_readable"] = 1
            counters["gap_below_floor"] += 1
            continue

        valid, skip_reason = validate_orb_entry(orb_high, orb_low, atr14)
        if not valid:
            r["orb_status"] = f"orb_invalid:{skip_reason}"
            r["filled"] = 0
            r["runnerB5"], r["runnerB8"] = 0, 0
            r["orb_readable"] = 1
            counters["orb_invalid"] += 1
            continue

        cancel = entry_cancel_asof(d)
        fill = entry_walk(bk["list"], orb_high, submit, cancel)
        r["orb_status"] = fill["status"] + (f":{fill.get('reason')}" if fill.get("reason") else "")
        r["orb_readable"] = 1

        if fill["status"] == "abstain":
            r["orb_readable"] = 0
            counters["unreadable_abstain"] += 1
            continue
        if fill["status"] != "filled":
            r["filled"] = 0
            r["runnerB5"], r["runnerB8"] = 0, 0
            counters["no_entry"] += 1
            continue

        # filled
        entry_px = fill["px"]
        fill_minute = fill["minute"]
        r["filled"] = 1
        r["entry_px"] = entry_px
        r["fill_minute"] = fill_minute
        counters["filled"] += 1
        post_fill_max = max((h for hhmm, o, h, l in bk["list"] if hhmm >= fill_minute), default=None)
        if i0 is None or post_fill_max is None or r.get("adr_dollar_ep") is None:
            counters["filled_incomplete"] += 1
            continue
        fwd = daily_bars[i0 + 1:i0 + 16]
        if len(fwd) < 15:
            counters["filled_incomplete"] += 1
            continue
        mx = max([post_fill_max] + [b[2] for b in fwd])
        run_b = (mx - entry_px) / r["adr_dollar_ep"]
        r["run_xadr_B"] = run_b
        r["runnerB5"] = int(run_b >= 5)
        r["runnerB8"] = int(run_b >= 8)

    scored_A = [r for r in rows if r["runner5"] is not None]
    readable = [r for r in scored_A if r["orb_readable"]]
    unreadable = [r for r in scored_A if not r["orb_readable"]]

    out: list[str] = []
    p = out.append
    p(f"#684 ADDENDUM v2 (faithful live-entry replay) RESULTS")
    p(f"population with a frame-A 15-session outcome: {len(scored_A)}; ORB-readable: {len(readable)}; unreadable: {len(unreadable)}")
    p(f"status counts: {dict(counters)}")
    p("")
    p("STATUS BREAKDOWN (readable rows):")
    st = Counter(r["orb_status"].split(":")[0] for r in readable)
    for k, v in st.most_common():
        p(f"  {k}: {v}")
    p("")
    filled = [r for r in readable if r["filled"] == 1]
    unfilled = [r for r in readable if r["filled"] == 0]
    p(f"FILL RATE (readable, n={len(readable)}): filled {len(filled)} ({100*len(filled)/len(readable):.1f}%), never placed/no-entry {len(unfilled)} ({100*len(unfilled)/len(readable):.1f}%)")
    p(f"  alerted readable: n {sum(1 for r in readable if r['alerted'])}, filled {sum(1 for r in readable if r['alerted'] and r['filled']==1)}")
    p(f"  rejected readable: n {sum(1 for r in readable if not r['alerted'])}, filled {sum(1 for r in readable if not r['alerted'] and r['filled']==1)}")
    p("  breakdown of the never-filled / never-placed reasons:")
    reasons = Counter(r["orb_status"].split(":")[0] for r in unfilled)
    for k, v in reasons.most_common():
        p(f"    {k}: {v}")
    p("")

    # frame-A runners and fillability
    a_runners_readable = [r for r in readable if r["runner5"]]
    never_filled_a = [r for r in a_runners_readable if r["filled"] == 0]
    a_runners_unreadable = [r for r in unreadable if r["runner5"]]
    p(f"FRAME-A RUNNERS AND LIVE FILLABILITY: {sum(r['runner5'] for r in scored_A)} frame-A runners total. "
      f"Of the {len(a_runners_readable)} ORB-readable, {len(never_filled_a)} were never placed/never filled. "
      f"{len(a_runners_unreadable)} are ORB-unreadable (fillability unknown): " +
      ", ".join(f"{r['ticker']} {r['scan_date']}" for r in a_runners_unreadable))
    p("")

    rb_ok = [r for r in readable if r["runnerB5"] is not None]
    p(f"RUNNER COMPOSITION: frame A (published, all 667) {sum(r['runner5'] for r in scored_A)} "
      f"({100*rate([r['runner5'] for r in scored_A]):.1f}%);  frame A on readable-B pop ({len(readable)}) "
      f"{sum(r['runner5'] for r in readable)} ({100*rate([r['runner5'] for r in readable]):.1f}%);  "
      f"frame B ({len(rb_ok)} with a computed RUN_B) {sum(r['runnerB5'] for r in rb_ok)} "
      f"({100*rate([r['runnerB5'] for r in rb_ok]):.1f}%)")
    bA = set((r["ticker"], r["scan_date"]) for r in readable if r["runner5"])
    bB = set((r["ticker"], r["scan_date"]) for r in rb_ok if r["runnerB5"])
    p(f"  overlap: {len(bA & bB)} runners in both; {len(bB - bA)} frame-B-only: " +
      ", ".join(f"{t} {d}" for t, d in sorted(bB - bA)) +
      f";  {len(bA - bB)} frame-A-only (never filled or filled short)")
    p("")

    results_Aprime, discA, heldA, bwA, btA = run_pass(readable, "runner5", "runner8", SEED)
    results_B, discB, heldB, bwB, btB = run_pass(rb_ok, "runnerB5", "runnerB8", SEED)
    p(f"frame A' (readable pop) best week = {bwA}, best two = {btA}")
    p(f"frame B best week = {bwB}, best two (by run_xadr_B) = {btB}")
    p(f"held-out runners: frame A' {sum(r['runner5'] for r in heldA)}, frame B {sum(r['runnerB5'] for r in heldB if r['runnerB5'] is not None)}")
    p("")

    published = {}
    with (HERE / "results.tsv").open() as fh:
        cols = fh.readline().rstrip("\n").split("\t")
        for line in fh:
            parts = line.rstrip("\n").split("\t")
            rr = dict(zip(cols, parts))
            published[rr["feature"]] = rr.get("verdict", "")

    p("PER-FEATURE (readable population; rates = share >= 5 ADR in each frame):")
    p("feature | when | n | frame A' fav vs rest | frame A' verdict | frame B fav vs rest | frame B verdict | published frame-A verdict (all 667) | CHANGED vs A'?")
    n_changed = 0
    change_rows = []
    for ra, rb in zip(results_Aprime, results_B):
        col = ra["feature"]
        va, vb = ra.get("verdict", "no data"), rb.get("verdict", "no data")
        va_s = va.split(",")[0].split(" (")[0].split(" ⚠")[0].strip()
        vb_s = vb.split(",")[0].split(" (")[0].split(" ⚠")[0].strip()
        changed = va_s != vb_s
        if changed:
            n_changed += 1
            change_rows.append((col, va, vb))
        p(f"{col} | {ra['when']} | {ra.get('n_disc','-')} | {fmt_rate(ra)} | {va} | {fmt_rate(rb)} | {vb} | {published.get(col,'?')} | {'CHANGED' if changed else ''}")
    p("")
    p(f"verdicts changed between frame A' and frame B: {n_changed} of {len(results_Aprime)}")
    for col, va, vb in change_rows:
        p(f"  CHANGED: {col} — frame A' [{va}] -> frame B [{vb}]")
    p("")

    # labelled EPs
    p("LABELLED EPs — status / fill / outcome:")
    idx = {(r["ticker"], r["scan_date"]): r for r in rows}
    for t, d in LABELLED:
        r = idx.get((t, d))
        if r is None:
            p(f"  {t} {d}: not in population")
            continue
        if not r["orb_readable"]:
            p(f"  {t} {d}: ORB-unreadable ({r['orb_status']})")
        elif r["filled"] != 1:
            p(f"  {t} {d}: {r['orb_status']} — never filled")
        else:
            rb = r["run_xadr_B"]
            rb_s = f"{rb:.2f}" if rb is not None else "incomplete"
            p(f"  {t} {d}: filled at {r['fill_minute']} px ${r['entry_px']:.2f}, run_xadr (frame A, from close) = {r['run_xadr']:.2f}, run_xadr_B (frame B, from fill) = {rb_s}")
    p("")

    text = "\n".join(out) + "\n"
    (HERE / "orb_live_status_out.txt").write_text(text)
    print(text)

    keys = ["feature", "when", "name", "n_disc", "n_fav", "rate_fav", "n_rest", "rate_rest", "diff", "auc", "p_disc",
            "held_n_fav", "held_rate_fav", "held_n_rest", "held_rate_rest", "held_sign", "held_ok",
            "drop_week_diff", "drop_week_p", "drop_two_diff", "drop_two_p", "labelled_in_fav", "labelled_n", "verdict"]
    for fname, res in (("orb_live_results.tsv", results_B), ("orb_live_results_A.tsv", results_Aprime)):
        with (HERE / fname).open("w") as fh:
            fh.write("\t".join(keys) + "\n")
            for r in res:
                fh.write("\t".join("" if r.get(k) is None else (f"{r[k]:.4f}" if isinstance(r.get(k), float) else str(r[k])) for k in keys) + "\n")

    with (HERE / "orb_live_outcomes.tsv").open("w") as fh:
        fh.write("ticker\tscan_date\tblock\talerted\torb_readable\torb_status\tfilled\tfill_minute\tentry_px\trun_xadr\trunner5\trun_xadr_B\trunnerB5\trunnerB8\n")
        for r in scored_A:
            rb_s = "" if r.get("run_xadr_B") is None else f"{r['run_xadr_B']:.3f}"
            fh.write(f"{r['ticker']}\t{r['scan_date']}\t{r['block']}\t{int(r['alerted'])}\t{r['orb_readable']}\t{r['orb_status']}\t"
                      f"{r.get('filled')}\t{r.get('fill_minute') or ''}\t{r.get('entry_px') or ''}\t{r['run_xadr']:.3f}\t{r['runner5']}\t"
                      f"{rb_s}\t{r.get('runnerB5')}\t{r.get('runnerB8')}\n")


if __name__ == "__main__":
    main()
