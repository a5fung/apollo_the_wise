"""#687 part 3 — what the ORDER TIMING the live account can actually get costs the depth rule (2026-09-29).

================================ PRE-REGISTRATION ==================================
Written 2026-09-29 BEFORE any timing variant was scored. $0: no new data — the captures #687 (part 1) and #685 already
read (scripts/probes/_687/: pull_daily_out.txt, population.tsv, minutes_entry*.tsv.gz, minutes_held.tsv.gz; the #685
captures via depth.build_states). No prod read, no Polygon call, no live code, PLAN.md or prod state touched.

QUESTION. The #687 / #685 replays book every "close below the line" sale AT THE 16:00 CLOSE. Live cannot do that today:
  the 16:45 ET job (live_tracker.update_open_positions_live -> execute_full_exit -> alpaca close_position) sends a
  MARKET order after the close, which Alpaca queues for the next session's open ("Orders not eligible for extended hours
  submitted after 4:00pm ET will be queued up for release the next trading day"). A market-on-close order must be in
  by 15:50 ET ("CLS orders submitted after 3:50pm but before 7:00pm ET will be rejected"), so a same-day close sale needs
  the decision BEFORE the close, on a price that is not the close.

TIMINGS (applied to the close-below-line exit ONLY; the resting stop, breakeven, partial, entry and day 0 are unchanged):
  close    the replay's assumption — sell at the 16:00 close. MUST reproduce #687's / #685's per-trade R exactly
           (fidelity gate below, else HALT).
  open     sell at the NEXT session's open (the next daily bar's open) — what today's 16:45 job gets.
  1545     at 15:45 ET evaluate the SAME ladder (exit_logic.apply_daily_exit_step, the 16:45 job's call, with
           skip_hard_stop_close=True as run_partial_exits does at 15:45) on the 15:45 price as the provisional close:
           the verdict. Verdict SELL -> the resting stop is cancelled and a market-on-close order sells at the day's
           official close (the daily bar close); the resting stop is gone from 15:45, so a later touch of it no longer
           sells there. Verdict HOLD -> the stop keeps resting to 16:00; if the day then CLOSES below the line (a MISS)
           the 16:45 job still sells, at the next open (the backstop).
  1545mkt  the MOC-rejected fallback: the 15:45 verdict SELL sells at once, at the 15:45 minute bar's OPEN.
  15:45 PRICE CONVENTION: the close of the last minute bar stamped before 15:45 (the 15:44 bar); the low so far = the
  minimum low of those bars. The 1545mkt fill = the open of the first bar stamped >= 15:45.

ARMS: D10 (the depth rule: stop resting at max(floor, line - 1.0 x ADR20% x line), else the close test) and A0 (today's
  stop: the line rests). Both under every timing — A0 'open' IS today's live execution (the 16:45 job's close-below
  sale goes out after hours too). The two numbers that matter: D10 close - A0 close (the published +29.46R / -1.82R)
  and D10 1545 - A0 open (what would actually trade).

DAYS WITHOUT MINUTE BARS. Minute bars exist only on line-test days (#687 round 2; #685's stored bars). On a day without
  bars the 15:45 price is unknown. The verdict is monotone in the price: apply_daily_exit_step sells iff
  p < T* = max(mean of the prior 9 closes, mean of the prior 19 closes, entry if breakeven is armed) (p < SMA10(p) <=>
  p < S9/9; the same for SMA20), so: high < T* -> SELL for certain; low >= T* -> HOLD for certain; otherwise AMBIGUOUS.
  The T* identity is CHECKED against apply_daily_exit_step on every bar-day evaluation (mismatches printed, HALT if
  any). Ambiguous days are resolved three ways and all three are reported: 'asclose' (the 15:45 verdict = the close
  verdict; neutral), 'sell' and 'hold' (the bounds). A no-bar day whose low reaches the resting stop keeps the
  baseline's stop fill (order vs 15:45 unknowable; counted).

MEASURES per sample (1,505 rebuilt paired trades; 79 real EPs) per arm x timing: total money-R, drop-best-2, >=3 / >=8
  ORB-R winners kept, the difference vs A0-close and vs A0-open, better / worse (> 0.005R); a week-block sign-flip p
  (5,000 draws, seed 687) ONLY for D10-1545 vs A0-open and D10-open vs A0-open. On the D10 close-rule path (baseline),
  every held session open at 15:45 on which the trail governs: 15:45 verdict vs close verdict — agree-sell, FALSE SELL
  (15:45 below, closed back above), MISS (15:45 above, closed below), agree-hold; and the SWAP-WINDOW cost: days the
  15:45 verdict is SELL and the baseline's depth stop fires AFTER 15:45 (the MOC then sells at the close instead).
  The named runners (BE 2025-07-24, HL 2025-08-07, FCEL 2026-04-29, AXGN 2024-01-05, EPSM 2025-04-24, SEZL; FTK, INFQ on
  the 79) are printed per timing.

AMENDMENT, AFTER THE FIRST RUN (stated so; none of it changes a number above):
  - timing '1549' (decide at 15:49 on the 15:48 bar, sell at the close) — the latest decision minute before Alpaca's
    15:50 cutoff — added after the first run showed the 15:45 verdict selling BE and FCEL on days that closed back
    above the line. Descriptive only; no p is read off it.
  - the POST-HOC block (totals by block, without the named runners, the largest per-trade movers, and the overnight
    move on the close-below exits) — descriptive, written after the first run.
  - the doc's section 2 also cites ONE separate read-only prod capture (pull_mech.sql -> pull_mech_out.txt, READ ONLY
    transaction, rolled back): the full-exit order history and the open positions. This probe does not read it.
====================================================================================
"""
from __future__ import annotations

import collections
import random
import statistics
import sys
from datetime import date, datetime, time, timedelta
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parent / "_685"))
import backfill as BF  # noqa: E402  (imports study as ST, ep_replay as ep)
import depth as DP  # noqa: E402
ST = BF.ST
ep = BF.ep
from agents.market_intelligence.broker.exit_logic import apply_daily_exit_step, seed_exit_state  # noqa: E402

T1545 = time(15, 45)
TIMINGS = ("close", "open", "1545", "1545mkt", "1549")
DECIDE = {"1545": time(15, 45), "1545mkt": time(15, 45), "1549": time(15, 49)}
ARMS = ("A0", "D10")
AMBIG = ("asclose", "sell", "hold")
N_PERM = 5000
SEED = 687
OUT = HERE
LOG = open(OUT / "mechanics_out.txt", "w")
TMIS: list[str] = []          # T* identity mismatches


def P(*a):
    s = " ".join(str(x) for x in a)
    print(s)
    LOG.write(s + "\n")


def tstar(trail_closes: list[float], be_active: bool, entry: float) -> float | None:
    n = len(trail_closes) + 1
    cands = []
    if n >= 10:
        cands.append(sum(trail_closes[-9:]) / 9)
    if n >= 20:
        cands.append(sum(trail_closes[-19:]) / 19)
    if be_active:
        cands.append(entry)
    return max(cands) if cands else None


def verdict(state, prior, d, p, lo, rest, remaining, partial_taken, be_active, exits) -> bool:
    s = dict(state)
    s.update(remaining_shares=remaining, partial_taken=partial_taken, breakeven_active=be_active,
             exits=list(exits), hard_stop=rest)
    step = apply_daily_exit_step(s, {"l": lo, "c": p}, d, integer_partial_shares=False,
                                 skip_partial_decision=True, skip_hard_stop_close=True,
                                 trail_mode="sma", prior_closes=prior)
    return step.action == "sma_stopped"


def walk(arm: str, timing: str, ambig: str, *, ticker, alert_date, st, daily, held, horizon, diag=None) -> dict:
    """study.walk_hybrid_arm for k=None arms (A0 line rests / D10 adr stop), with the close-below sale's timing varied.
    With timing='close' it must equal study.walk_hybrid_arm exactly (gated)."""
    line_rests = arm == "A0"
    adr_stop = arm == "D10"
    entry, hard = st["entry"], st["hard"]
    shares, remaining = st["shares"], st["remaining"]
    partial_taken, be_active = st["partial_taken"], st["be_active"]
    target, be_trigger = st["target"], st["be_trigger"]
    adr_pct = st["adr_pct"]
    exits = [dict(e) for e in st["exits"]]
    risk_denom = shares * (entry - hard)
    out = {"status": None, "final_reason": None, "realized_r": None, "mark_r": None, "exit_day": None,
           "held_sessions": 0, "delisted_forced_close": False}
    dbars = daily.get(ticker, {})
    days_sorted = sorted(dbars)
    prior = [dbars[x]["c"] for x in days_sorted if x < alert_date and dbars[x]["c"] is not None]
    state = seed_exit_state(alert_date=alert_date, entry_price=entry, hard_stop=hard, remaining_shares=remaining,
                            partial_taken=partial_taken, breakeven_active=partial_taken, exits=list(exits))
    line = max(hard, entry if be_active else hard)
    closed = False
    d = alert_date
    last_close = None

    def book(px, qty, reason, when):
        exits.append({"time": str(when), "price": px, "reason": reason, "shares": qty, "pnl": (px - entry) * qty})

    def next_open(day):
        for x in days_sorted:
            if x > day and x <= horizon and dbars[x]["o"] is not None:
                return x, dbars[x]["o"]
        return None, None

    if remaining <= 0:
        closed = True
    while not closed:
        d += timedelta(days=1)
        if d > horizon:
            out["status"] = "open_at_horizon"
            break
        if d.weekday() >= 5:
            continue
        b = dbars.get(d)
        if not b or b["c"] is None or b["l"] is None or b["h"] is None:
            continue
        out["held_sessions"] += 1
        last_close = b["c"]
        floor = max(hard, entry) if be_active else hard
        line = max(line, floor)
        line_r = round(line, 2)
        trail_governed = line_r > round(floor, 2) + 1e-9
        if line_rests:
            rest = line_r
        elif adr_stop and trail_governed and adr_pct:
            rest = max(round(floor, 2), round(line_r - 1.0 * adr_pct * line_r, 2))
        else:
            rest = round(floor, 2)
        mb = held.get((ticker, d), [])
        n_bars = len(mb)
        v1545 = None            # the 15:45 verdict (True sell / False hold / None not evaluated)
        stopped_after_1545 = False
        sold_1545 = False
        pre = []
        t_dec = DECIDE.get(timing, T1545)
        for i, mbar in enumerate(mb):
            if v1545 is None and mbar["m"].time() >= t_dec:
                if pre:
                    p = pre[-1]["c"]; lo = min(x["l"] for x in pre)
                    v1545 = verdict(state, prior, d, p, lo, rest, remaining, partial_taken, be_active, exits)
                    ts = tstar(prior + state["running_closes"], be_active, entry)
                    if ts is not None and p > rest + 1e-9 and (p < ts - 1e-9) != v1545 and abs(p - ts) > 1e-6:
                        TMIS.append(f"{ticker} {d} p={p} T*={ts} verdict={v1545}")
                    if v1545 and timing in ("1545", "1545mkt", "1549"):
                        px = mbar["o"] if timing == "1545mkt" else b["c"]
                        book(px, remaining, "sell_1545" if timing == "1545mkt" else "moc_1545", mbar["m"])
                        remaining = 0.0
                        out["final_reason"] = "mkt_1545" if timing == "1545mkt" else "moc_1545"
                        out["exit_day"] = d
                        closed = True
                        sold_1545 = True
                        break
                else:
                    v1545 = False     # no bar before 15:45: nothing to decide on (counted as hold)
            pre.append(mbar)
            if (not be_active) and mbar["h"] >= be_trigger:
                if rest < entry and mbar["l"] <= entry:
                    out.update(status="abstain", reason=f"stop_and_breakeven_same_bar:{d}")
                    return out
                be_active = True
                floor = max(hard, entry)
                rest = max(rest, round(entry, 2))
                line = max(line, entry)
            hit_stop = mbar["l"] <= rest
            hit_tgt = (target is not None and not partial_taken and mbar["h"] >= target)
            if hit_stop and hit_tgt:
                out.update(status="abstain", reason=f"stop_and_target_same_bar:{d}")
                return out
            if hit_stop:
                px = mbar["o"] if mbar["o"] < rest else rest
                book(px, remaining, "stop_hit", mbar["m"])
                remaining = 0.0
                out["final_reason"] = "stop_hit"
                out["exit_day"] = d
                closed = True
                if mbar["m"].time() >= t_dec:
                    stopped_after_1545 = True
                break
            if hit_tgt:
                qty = remaining / 3
                book(target, qty, "partial_profit", mbar["m"])
                remaining -= qty
                partial_taken = True
                be_active = True
                floor = max(hard, entry)
                rest = max(rest, round(entry, 2))
                line = max(line, entry)
        if diag is not None and n_bars and trail_governed:
            diag["bar_eval_days"] += 1
        # bars that END before 15:45 (a coverage hole late in the session): decide on the last bar seen
        if not closed and v1545 is None and pre:
            p = pre[-1]["c"]; lo = min(x["l"] for x in pre)
            v1545 = verdict(state, prior, d, p, lo, rest, remaining, partial_taken, be_active, exits)
            if diag is not None:
                diag["bars_end_before_1545"] += 1
            if v1545 and timing in ("1545", "1545mkt", "1549"):
                book(b["c"], remaining, "moc_1545", d)     # no 15:45 bar: both fill at the close
                remaining = 0.0
                out["final_reason"] = "mkt_1545" if timing == "1545mkt" else "moc_1545"
                out["exit_day"] = d
                closed = True
                sold_1545 = True
        if closed and not sold_1545:
            if diag is not None and stopped_after_1545 and v1545:
                diag["swap_stop_after_1545"].append((ticker, alert_date, d))
            break
        if closed:
            if diag is not None:
                close_v = verdict(state, prior, d, b["c"], b["l"], rest, remaining if remaining else 1.0,
                                  partial_taken, be_active, exits)
                diag["sold_1545_close_above"] += (not close_v)
            break
        # ── no-bar day: daily-grain fallback (identical to study.py) ──
        if n_bars == 0:
            if (not be_active) and b["h"] >= be_trigger:
                if rest < entry and b["l"] <= entry:
                    out.update(status="abstain", reason=f"fwd_stop_and_breakeven_same_day:{d}")
                    return out
                be_active = True
                floor = max(hard, entry)
                rest = max(rest, round(entry, 2))
                line = max(line, entry)
            if target is not None and not partial_taken and b["h"] >= target:
                if b["l"] <= rest:
                    out.update(status="abstain", reason=f"fwd_stop_and_target_same_day:{d}")
                    return out
                qty = remaining / 3
                book(target, qty, "partial_profit", d)
                remaining -= qty
                partial_taken = True
                be_active = True
                floor = max(hard, entry)
                rest = max(rest, round(entry, 2))
                line = max(line, entry)
            # the 15:45 verdict on a no-bar day, by the monotone threshold
            if timing in ("1545", "1545mkt", "1549") and b["l"] > rest:
                hi_v = verdict(state, prior, d, b["h"], b["l"], rest, remaining, partial_taken, be_active, exits)
                lo_v = verdict(state, prior, d, b["l"], b["l"], rest, remaining, partial_taken, be_active, exits)
                if hi_v:
                    v1545 = True
                elif not lo_v:
                    v1545 = False
                else:
                    if diag is not None:
                        diag["ambiguous_days"].add((ticker, alert_date, d))
                    if ambig == "sell":
                        v1545 = True
                    elif ambig == "hold":
                        v1545 = False
                    else:
                        v1545 = verdict(state, prior, d, b["c"], b["l"], rest, remaining, partial_taken, be_active, exits)
                if v1545:
                    px = b["c"] if timing == "1545" else b["c"]   # no bars: the 15:45 open is unknown -> the close
                    if timing == "1545mkt" and diag is not None:
                        diag["mkt_nobar_at_close"] += 1
                    book(px, remaining, "moc_1545", d)
                    remaining = 0.0
                    out["final_reason"] = "mkt_1545" if timing == "1545mkt" else "moc_1545"
                    out["exit_day"] = d
                    closed = True
                    break
            elif timing in ("1545", "1545mkt", "1549") and b["l"] <= rest and diag is not None:
                diag["nobar_stop_day_order_unknown"] += 1
        # ── the 16:45 job ──
        state.update(remaining_shares=remaining, partial_taken=partial_taken, breakeven_active=be_active, exits=list(exits))
        state["hard_stop"] = rest
        step = apply_daily_exit_step(state, {"l": b["l"], "c": b["c"]}, d, integer_partial_shares=False,
                                     skip_partial_decision=True, trail_mode="sma", prior_closes=prior)
        state.update(running_closes=step.new_running_closes)
        if step.closed:
            px, reason = step.close_price, step.close_reason
            if reason == "stop_hit":
                if b["o"] is not None and b["o"] < px:
                    px = b["o"]
                book(px, remaining, reason, d)
                out["final_reason"] = "stop_hit"
                out["exit_day"] = d
            else:
                if diag is not None and timing in ("1545", "1545mkt", "1549"):
                    diag["miss_days"].append((ticker, alert_date, d))
                if timing == "close":
                    book(px, remaining, "close_below_line", d)
                    out["final_reason"] = "close_below_line"
                    out["exit_day"] = d
                else:
                    nd, no = next_open(d)
                    if nd is None:
                        if diag is not None:
                            diag["no_next_open"] += 1
                        book(b["c"], remaining, "close_below_line_no_next_open", d)
                        out["final_reason"] = "close_below_line"
                        out["exit_day"] = d
                    else:
                        book(no, remaining, "next_open", nd)
                        out["final_reason"] = "next_open" if timing == "open" else "miss_next_open"
                        out["exit_day"] = nd
            remaining = 0.0
            closed = True
            break
        line = max(line, step.effective_stop)
    pnl = sum(e["pnl"] for e in exits)
    out["last_close"] = last_close
    if closed:
        out["status"] = "settled"
        out["realized_r"] = pnl / risk_denom
    elif out["status"] == "open_at_horizon":
        lc = last_close if last_close is not None else entry
        out["mark_r"] = (pnl + (lc - entry) * remaining) / risk_denom
    return out


def verdict_matrix(ticker, alert_date, st, daily, held, horizon) -> collections.Counter:
    """On the D10 CLOSE-rule path: each held, trail-governed session still open at 15:45 WITH bars -> 15:45 verdict vs
    close verdict. Re-walks the baseline and evaluates both verdicts on each such day (no behaviour change)."""
    c = collections.Counter()
    entry, hard = st["entry"], st["hard"]
    remaining = st["remaining"]
    partial_taken, be_active = st["partial_taken"], st["be_active"]
    target, be_trigger = st["target"], st["be_trigger"]
    adr_pct = st["adr_pct"]
    exits = [dict(e) for e in st["exits"]]
    dbars = daily.get(ticker, {})
    prior = [dbars[x]["c"] for x in sorted(dbars) if x < alert_date and dbars[x]["c"] is not None]
    state = seed_exit_state(alert_date=alert_date, entry_price=entry, hard_stop=hard, remaining_shares=remaining,
                            partial_taken=partial_taken, breakeven_active=partial_taken, exits=list(exits))
    line = max(hard, entry if be_active else hard)
    d = alert_date
    if remaining <= 0:
        return c
    while True:
        d += timedelta(days=1)
        if d > horizon:
            return c
        if d.weekday() >= 5:
            continue
        b = dbars.get(d)
        if not b or b["c"] is None or b["l"] is None or b["h"] is None:
            continue
        floor = max(hard, entry) if be_active else hard
        line = max(line, floor)
        line_r = round(line, 2)
        trail_governed = line_r > round(floor, 2) + 1e-9
        rest = max(round(floor, 2), round(line_r - adr_pct * line_r, 2)) if (trail_governed and adr_pct) else round(floor, 2)
        mb = held.get((ticker, d), [])
        pre = []
        v = None
        closed = False
        for mbar in mb:
            if v is None and mbar["m"].time() >= T1545 and pre:
                v = verdict(state, prior, d, pre[-1]["c"], min(x["l"] for x in pre), rest, remaining, partial_taken, be_active, exits)
            pre.append(mbar)
            if (not be_active) and mbar["h"] >= be_trigger:
                if rest < entry and mbar["l"] <= entry:
                    return c
                be_active = True; floor = max(hard, entry); rest = max(rest, round(entry, 2)); line = max(line, entry)
            if mbar["l"] <= rest:
                if v:
                    c["stop_after_1545_on_a_sell_verdict"] += 1
                return c
            if target is not None and not partial_taken and mbar["h"] >= target:
                remaining -= remaining / 3; partial_taken = True; be_active = True
                floor = max(hard, entry); rest = max(rest, round(entry, 2)); line = max(line, entry)
        if not mb:
            if (not be_active) and b["h"] >= be_trigger:
                be_active = True; floor = max(hard, entry); rest = max(rest, round(entry, 2)); line = max(line, entry)
            if target is not None and not partial_taken and b["h"] >= target:
                remaining -= remaining / 3; partial_taken = True; be_active = True
                floor = max(hard, entry); rest = max(rest, round(entry, 2)); line = max(line, entry)
            if b["l"] <= rest:
                return c
            hi_v = verdict(state, prior, d, b["h"], b["l"], rest, remaining, partial_taken, be_active, exits)
            lo_v = verdict(state, prior, d, b["l"], b["l"], rest, remaining, partial_taken, be_active, exits)
            cv = verdict(state, prior, d, b["c"], b["l"], rest, remaining, partial_taken, be_active, exits)
            if hi_v or lo_v or cv:
                key = "nobar:" + ("sell_certain" if hi_v else ("hold_certain" if not lo_v else "ambiguous"))
                c[key + (":close_below" if cv else ":close_above")] += 1
        elif v is not None:
            cv = verdict(state, prior, d, b["c"], b["l"], rest, remaining, partial_taken, be_active, exits)
            if v or cv:
                c[("agree_sell" if (v and cv) else "FALSE_SELL" if v else "MISS")] += 1
            else:
                c["agree_hold"] += 1
        state.update(remaining_shares=remaining, partial_taken=partial_taken, breakeven_active=be_active, exits=list(exits))
        state["hard_stop"] = rest
        step = apply_daily_exit_step(state, {"l": b["l"], "c": b["c"]}, d, integer_partial_shares=False,
                                     skip_partial_decision=True, trail_mode="sma", prior_closes=prior)
        state.update(running_closes=step.new_running_closes)
        if step.closed:
            return c
        line = max(line, step.effective_stop)


# ── populations ─────────────────────────────────────────────────────────────────────

def build_1505():
    pop = BF.load_population()
    daily = BF.load_daily()
    entry_min = BF.load_minutes(sorted(HERE.glob("minutes_entry*.tsv*")))
    held_min = BF.load_minutes(sorted(HERE.glob("minutes_held*.tsv*")))
    # the same bad-join exclusion backfill.py applies (a day whose minute and daily bars disagree)
    bad_join = set()
    for r in pop:
        k = (r["ticker"], r["d"])
        bars0 = entry_min.get(k)
        if not bars0 or r["o"] is None:
            continue
        orb = next((b for b in bars0 if b["m"].time() == time(9, 30)), None)
        if orb and abs(orb["o"] - r["o"]) / r["o"] > 0.02:
            bad_join.add(k)
    states, day0_only, H = {}, {}, {}
    for r in pop:
        k = (r["ticker"], r["d"])
        bars0 = entry_min.get(k, [])
        orb = next((b for b in bars0 if b["m"].time() == time(9, 30)), None)
        if k in bad_join or not bars0 or orb is None:
            continue
        Hh, Ll = orb["h"], orb["l"]
        ok, _ = BF.validate_orb_entry(Hh, Ll, BF.atr14_live(daily.get(r["ticker"], {}), r["d"]))
        if not ok or 2 * Ll - Hh <= 0:
            continue
        f = BF.live_entry(bars0, Hh, Ll)
        if f["status"] != "filled":
            continue
        st, why = BF.day0_from_fill(k[0], k[1], bars0, Hh, Ll, f, daily)
        if st is None:
            continue
        H[k] = {"money_per_orb": (st["entry"] - st["hard"]) / (st["entry"] - Ll)}
        if st["settled_d0"]:
            day0_only[k] = st["h"]["realized_r"]
        else:
            states[k] = st
    return daily, held_min, states, day0_only, H


def load_stored_1505():
    import csv
    rows = {}
    with open(HERE / "arms_per_trade.tsv") as fh:
        for r in csv.DictReader(fh, delimiter="|"):
            rows[(r["ticker"], date.fromisoformat(r["entry_day"]))] = r
    return rows


# ── stats ───────────────────────────────────────────────────────────────────────────

def p_week(diffs, keys):
    weeks = [f"{k[1].isocalendar()[0]}-W{k[1].isocalendar()[1]:02d}" for k in keys]
    return ST.block_signflip_p(diffs, weeks, random.Random(SEED))


def report(label, keys, R, orb_mult, runners):
    """R[(arm, timing)][k] = realized money-R. keys = the paired set."""
    P(f"\n## {label}: paired n = {len(keys)}")
    base_c = R[("A0", "close")]; base_o = R[("A0", "open")]
    P("   arm/timing      total   drop-best-2  >=3ORB-R >=8ORB-R |  vs A0-close (better/worse) |  vs A0-open = TODAY LIVE (better/worse)")
    for arm in ARMS:
        for t in TIMINGS:
            Rv = R[(arm, t)]
            vals = [Rv[k] for k in keys]
            w3 = sum(1 for k in keys if Rv[k] * orb_mult[k] >= 3)
            w8 = sum(1 for k in keys if Rv[k] * orb_mult[k] >= 8)
            dc = [Rv[k] - base_c[k] for k in keys]
            do = [Rv[k] - base_o[k] for k in keys]
            P(f"   {arm:3s} {t:8s} {sum(vals):+9.2f} {ST.drop_best_two(vals):+10.2f} {w3:6d} {w8:7d}   | "
              f"{sum(dc):+8.2f} ({sum(1 for x in dc if x > 0.005)}/{sum(1 for x in dc if x < -0.005)})        | "
              f"{sum(do):+8.2f} ({sum(1 for x in do if x > 0.005)}/{sum(1 for x in do if x < -0.005)})")
    for a, b_ in ((("D10", "1545"), ("A0", "open")), (("D10", "open"), ("A0", "open")), (("D10", "close"), ("A0", "close")),
                  (("A0", "1545"), ("A0", "open"))):
        diffs = [R[a][k] - R[b_][k] for k in keys]
        srt = sorted(diffs)
        top2 = sum(srt[-2:]) if len(srt) >= 2 else 0
        P(f"   {a[0]}-{a[1]} vs {b_[0]}-{b_[1]}: {sum(diffs):+.2f}R  p={p_week(diffs, keys):.3f}  "
          f"without its top-2 contributors {sum(diffs) - top2:+.2f}R")
    P("   named trades (money-R): " + "; ".join(
        f"{k[0]} {k[1]}: " + " ".join(f"{a}-{t} {R[(a, t)][k]:+.2f}" for a in ARMS for t in TIMINGS)
        for k in runners if k in keys))


def main():
    P(f"# #687 part 3 — order-timing cost of the depth rule — run {datetime.now(ep._ET).isoformat(timespec='seconds')}")
    samples = {}
    # ── 1,505 rebuilt ──
    daily, held, states, day0_only, H = build_1505()
    stored = load_stored_1505()
    keys_all = sorted(set(states) | set(day0_only), key=lambda k: (k[1], k[0]))
    paired_stored = [k for k in keys_all if k in stored and all(stored[k][f"{a}_status"] == "settled" for a in ("A0", "A1", "D10"))]
    P(f"## 1,505 REBUILD: states reaching day 1 {len(states)}, settled day 0 {len(day0_only)}; stored paired {len(paired_stored)}")
    samples["rebuilt"] = (daily, held, states, day0_only, paired_stored, BF.HORIZON,
                          {k: H[k]["money_per_orb"] for k in H}, stored, "rebuilt")
    # ── 79 real EPs ──
    stored79, keys79 = DP.load_stored()
    daily685, held685, mincov685, H0m, states685, day0_685 = DP.build_states()
    import csv
    orbmul79 = {}
    with open(HERE.parent / "_685" / "depth_per_trade.tsv") as fh:
        dpt = {}
        for r in csv.DictReader(fh, delimiter="|"):
            k = (r["ticker"], date.fromisoformat(r["alert_date"]))
            dpt[k] = r
            orbmul79[k] = (float(r["entry"]) - float(r["hard"])) / float(r["orb_r_ps"])
    samples["real79"] = (daily685, held685, states685, day0_685, sorted(keys79, key=lambda k: (k[1], k[0])), ST.HORIZON,
                         orbmul79, dpt, "real79")

    for name, (daily_, held_, states_, day0_, keys_, horizon_, orbmul_, stored_, tag) in samples.items():
        P(f"\n# ======== SAMPLE {name} ========")
        results = {}
        diags = {}
        for arm in ARMS:
            for t in TIMINGS:
                for amb in (AMBIG if t in ("1545", "1545mkt", "1549") else ("asclose",)):
                    diag = {"bar_eval_days": 0, "swap_stop_after_1545": [], "sold_1545_close_above": 0,
                            "ambiguous_days": set(), "miss_days": [], "no_next_open": 0, "mkt_nobar_at_close": 0,
                            "nobar_stop_day_order_unknown": 0, "bars_end_before_1545": 0}
                    res = {}
                    for k in keys_:
                        if k in day0_:
                            res[k] = {"status": "settled", "realized_r": day0_[k], "final_reason": "day0"}
                            continue
                        st = states_[k]
                        r = walk(arm, t, amb, ticker=k[0], alert_date=k[1], st=st, daily=daily_, held=held_,
                                 horizon=horizon_, diag=diag)
                        if tag == "rebuilt":
                            r = BF.force_close_delisted(r, k[0], daily_)
                        res[k] = r
                    results[(arm, t, amb)] = res
                    diags[(arm, t, amb)] = diag
        # ── FIDELITY GATE: close timing reproduces the stored per-trade R ──
        bad = []
        for arm in ARMS:
            res = results[(arm, "close", "asclose")]
            for k in keys_:
                if tag == "rebuilt":
                    want = float(stored_[k][f"{arm}_R"])
                else:
                    want = float(stored_[k][f"{arm}_R"])
                got = res[k].get("realized_r")
                if res[k]["status"] != "settled" or got is None or abs(got - want) > 0.005:
                    bad.append(f"{arm} {k}: {res[k]['status']} {got} vs stored {want}")
        P(f"## FIDELITY ({name}): timing=close reproduces stored A0/D10 per-trade R on {len(keys_)} trades x 2 arms: "
          f"mismatches {len(bad)} -> {'REPRODUCED' if not bad else 'FAILED — HALT'}")
        for s in bad[:15]:
            P("    ", s)
        if bad:
            LOG.close(); raise SystemExit(2)
        P(f"## T* identity (apply_daily_exit_step verdict == p < T*) mismatches so far: {len(TMIS)}")
        for s in TMIS[:10]:
            P("    ", s)
        # paired over every variant
        keys_p = [k for k in keys_ if all(results[v][k]["status"] == "settled" for v in results)]
        P(f"## paired in every arm x timing x ambiguity: {len(keys_p)} of {len(keys_)} "
          f"(dropped: {[ (k, [v for v in results if results[v][k]['status'] != 'settled'][:2]) for k in keys_ if k not in keys_p][:5]})")
        # exit mix
        for arm in ARMS:
            for t in TIMINGS:
                cnt = collections.Counter(results[(arm, t, "asclose")][k].get("final_reason") for k in keys_p)
                P(f"   exits {arm}-{t}: {dict(sorted(cnt.items(), key=lambda x: -x[1]))}")
        runners = [("BE", date(2025, 7, 24)), ("HL", date(2025, 8, 7)), ("FCEL", date(2026, 4, 29)), ("AXGN", date(2024, 1, 5)),
                   ("EPSM", date(2025, 4, 24)), ("FTK", date(2026, 8, 3)), ("INFQ", date(2026, 5, 21)), ("TEAM", date(2026, 7, 31))]
        runners += [k for k in keys_p if k[0] == "SEZL"]
        for amb in AMBIG:
            R = {(arm, t): {k: results[(arm, t, amb if t in ("1545", "1545mkt", "1549") else "asclose")][k]["realized_r"] for k in keys_p}
                 for arm in ARMS for t in TIMINGS}
            report(f"{name} — ambiguous no-bar days resolved '{amb}'", keys_p, R, orbmul_, runners)
        # ── POST-HOC (added after the first run, descriptive): blocks, the named runners removed, the largest movers ──
        R = {(arm, t): {k: results[(arm, t, "asclose")][k]["realized_r"] for k in keys_p} for arm in ARMS for t in TIMINGS}
        blk = (lambda k: "DISC" if k[1] <= BF.SPLIT_END_DISC else "HELD") if tag == "rebuilt" else \
              (lambda k: "DISC" if k[1] <= ST.SPLIT_DATE else "HELD")
        excl = {("BE", date(2025, 7, 24)), ("HL", date(2025, 8, 7)), ("FCEL", date(2026, 4, 29))} if tag == "rebuilt" else \
               {("FTK", date(2026, 8, 3)), ("INFQ", date(2026, 5, 21))}
        P(f"## POST-HOC {name} ('asclose'): totals by block and without {sorted(k[0] for k in excl)}")
        for label, ks in (("DISC", [k for k in keys_p if blk(k) == "DISC"]), ("HELD", [k for k in keys_p if blk(k) == "HELD"]),
                          ("ALL w/o named", [k for k in keys_p if k not in excl])):
            P(f"   {label} (n {len(ks)}): " + " | ".join(
                f"{a}-{t} {sum(R[(a, t)][k] for k in ks):+.2f}" for a in ARMS for t in TIMINGS)
              + f" || D10-1545 − A0-open {sum(R[('D10', '1545')][k] - R[('A0', 'open')][k] for k in ks):+.2f}"
              + f" | D10-open − A0-open {sum(R[('D10', 'open')][k] - R[('A0', 'open')][k] for k in ks):+.2f}"
              + f" | D10-1549 − A0-open {sum(R[('D10', '1549')][k] - R[('A0', 'open')][k] for k in ks):+.2f}"
              + f" | D10-close − A0-close {sum(R[('D10', 'close')][k] - R[('A0', 'close')][k] for k in ks):+.2f}")
        for a, b_ in ((("D10", "1545"), ("D10", "close")), (("D10", "open"), ("D10", "close")), (("A0", "open"), ("A0", "close"))):
            mv = sorted(keys_p, key=lambda k: -abs(R[a][k] - R[b_][k]))[:8]
            P(f"   largest movers {a[0]}-{a[1]} vs {b_[0]}-{b_[1]}: " + "; ".join(
                f"{k[0]} {k[1]} {R[b_][k]:+.2f}->{R[a][k]:+.2f} ({results[(a[0], a[1], 'asclose')][k].get('final_reason')},"
                f"{results[(a[0], a[1], 'asclose')][k].get('exit_day')})" for k in mv if abs(R[a][k] - R[b_][k]) > 0.005))
        # the overnight move on the close-below exits: next open vs close, per exit (money-R)
        on = [R[("D10", "open")][k] - R[("D10", "close")][k] for k in keys_p
              if results[("D10", "close", "asclose")][k].get("final_reason") == "close_below_line"]
        if on:
            P(f"   D10 close-below exits {len(on)}: next open minus close, money-R — total {sum(on):+.2f}, median {statistics.median(on):+.3f}, "
              f"better at the open {sum(1 for x in on if x > 0.005)}, worse {sum(1 for x in on if x < -0.005)}")
        # diagnostics
        for arm in ARMS:
            for t in ("1545", "1545mkt", "1549", "open"):
                dg = diags[(arm, t, "asclose")]
                P(f"   diag {arm}-{t}: ambiguous no-bar days {len(dg['ambiguous_days'])}; misses sold next open {len(dg['miss_days'])}; "
                  f"15:45 sales on days that closed back above the line {dg['sold_1545_close_above']}; stop hit AFTER 15:45 on a SELL "
                  f"verdict (baseline sold at the stop) {len(dg['swap_stop_after_1545'])}; no next open {dg['no_next_open']}; "
                  f"no-bar stop days (order vs 15:45 unknown) {dg['nobar_stop_day_order_unknown']}; bars ending before 15:45 {dg['bars_end_before_1545']}")
        # verdict matrix on the D10 baseline path
        vm = collections.Counter()
        vm_a0 = collections.Counter()
        for k in keys_p:
            if k in day0_:
                continue
            vm += verdict_matrix(k[0], k[1], states_[k], daily_, held_, horizon_)
        P(f"## 15:45 VERDICT vs CLOSE VERDICT on the depth rule's own (close-timing) path, {name}: {dict(sorted(vm.items()))}")
    P(f"\n## T* identity mismatches total: {len(TMIS)}")
    LOG.close()


if __name__ == "__main__":
    main()
