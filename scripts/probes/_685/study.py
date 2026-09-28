"""#685 — his hybrid trail (close-based line, sell at once on a hard slice) replayed on real EPs.

================================ PRE-REGISTRATION ==================================
Written 2026-09-28 BEFORE any arm was scored. Everything below this banner was fixed first; the
numbers in docs/analysis/685_hybrid_trail_2026-09-28.md were produced by this file afterwards.

WHAT LIVE DOES TODAY (verified in code + on OKTA trade 382, the trigger case):
  16:45 ET job (live_tracker.update_open_positions_live -> exit_logic.apply_daily_exit_step):
  effective_stop = max(hard stop, max(SMA10, SMA20) of the stock's closes INCLUDING today's, entry
  once breakeven armed). If that exceeds the broker stop by > $0.01 the GTC stop is replaced at
  round(effective_stop, 2) — RAISE-ONLY; if the close is below effective_stop the position is sold
  at the close. The stop rests at the broker overnight; a gap below it fills at the open. The SMA
  window omits the entry day's own close (the job skips day 0; prior_closes ends the day before
  alert_date) — the harness reproduces this and so does this walker. OKTA: SMA10 at the 09-25 close
  = $193.25 = the broker stop; 09-28 opened $192.02 under it, filled $191.50.

POPULATION (operator 2026-09-28: real EPs regardless of safeguards):
  Every live MAGNA53 alert (mi_ep_alerts, source live) 2026-05-11 .. 2026-09-25, one per ticker-day
  (earliest detection), re-scored and re-admitted under the CURRENT stack (era D) by the harness'
  own _score_one, then walked from raw bars by scripts/ep_replay.walk_campaign (entry, day-0). Nothing
  comes from recorded exits; account safeguards never enter. Horizon = last complete daily bar
  (2026-09-25). DISCOVERY = alert_date <= 2026-08-31 (the 09-06 population); HELD-OUT = alert_date
  >= 2026-09-01. Fixed now. Nothing is tuned on either half (k and the ADR multiple are fixed here).

ANCHOR (must reproduce before anything is varied, else HALT):
  The 09-06 close-only read: rulesets era_c_rec_intraday_uc0 vs era_c_rec_closeonly_uc0, horizon
  2026-08-31, paired on the trades both settle: n=62, +3.91R vs -1.40R (-5.30R), close-only worse on
  13 of the 18 that differ; marked +15.04 vs +13.63 over 67; FTK 6.28->3.22, INFQ 3.98->2.26.
  Reproduced (a) from the 09-01 capture with today's code (anchor_*_run.txt) and (b) again here on
  the MERGED capture at the same horizon, before the horizon is extended.

R UNIT: money-R = the dollars risked on the trade (entry - placed stop; the placed stop sits 2 ORB-R
  below entry, so 1 money-R = 2 ORB-R). It is the harness' unit and the anchor's unit. ORB-R
  (entry - ORB low, the frame the +3R arm and +8R partial use) is printed beside it; the tail counts
  are stated in ORB-R (>= 3 ORB-R = >= 1.5 money-R; >= 8 ORB-R = >= 4 money-R) and "losses beyond
  -1.5R" is in money-R (an ordinary stop-out is -1.0 money-R).

ARMS (same trades, same entry, same day 0 — the line cannot engage before the first 16:45 job):
  A0  today: the line is the resting broker stop (touch -> fill at the stop; a bar opening below it
      -> fill at that open). Resting stop level = the ratchet line. [= live]
  A1  close-only: the line never rests at the broker; sell at the close if the close is below
      max(floor, today's line, breakeven). Resting stop level = floor = max(hard stop, entry once
      breakeven is armed). [= the harness' trail_intraday=False arm, the 09-06 loser]
  A2  his slice signature (k = 2 and k = 3, both fixed): resting stop = floor (as A1). After the
      first minute bar that trades at/below the line, watch aligned 5-minute windows (09:30, 09:35,
      ...). A SLICE BAR is a completed window whose low is strictly below the previous window's low
      AND whose close is in the bottom third of its own range (close <= low + range/3; a zero-range
      window is not a slice bar). The window containing the breach cannot count (its lower-low
      test needs a prior window); the count resets on any window that fails; the k-th bar must close
      below the line (a lower-low run that stays above the line is not a slice through it). Sell at
      the NEXT minute bar's open (a signal seen at a bar close executes on the next tick); at the
      close of the k-th bar if no bar follows. If nothing fires, the close test of A1 applies.
  A3  first-hour grace: A2 with k = 2, but windows starting before 10:30 ET are never evaluated
      (the breach itself may occur earlier); a catastrophic stop ALWAYS rests at the broker at
      max(floor, line - 1.0 x ADR), ADR = ADR20% over the 20 sessions before the alert day (the
      harness' adr20_pct) x the line price. Touch -> fill at the stop / the open on a gap.
  Every arm: the hard stop (entry - 2 ORB-R) and the breakeven floor (entry, armed when price trades
  entry + 3 ORB-R, or by an +8 ORB-R partial) rest at the broker intraday, exactly as today.
  The "line" for A1-A3 on day d = A0's resting stop that day (round(ratchet, 2), the number the
  broker holds) — so the arms differ ONLY on days the trail governs the stop.

MEASURES (per arm, DISCOVERY / HELD-OUT / ALL; paired vs A0 on trades every arm settles and reads):
  total and mean money-R (ORB-R beside); paired difference vs A0 with a week-block sign-flip
  permutation p (blocks = ISO week of alert_date, 5000 draws, seed 685, two-sided); trades better /
  worse than A0; winners kept (>= 3 ORB-R and >= 8 ORB-R); worst single trade; losses beyond -1.5
  money-R; trades still open at the horizon (marked at the last close) and trades held longer than
  A0; drop-the-best-two beside every total. Signature accuracy at the moment it fires: of A2's
  fires, how many were on days that closed back above the line (false sells); of the SLICE days on
  the hold-through (A1) path while A2 still held, how many A2 exited on (recall).

LINE TESTS (descriptive, Step 0): on the A1 path, every held session the trail governed the stop and
  the day's low was at/below the line, classified by that day's close only: UNDERCUT-AND-RECLAIM
  (closed at/above the line) or SLICE (closed below).

DATA (all captured once, read-only, $0): scripts/ep_replay_data/ (09-01 capture: alerts, day-0
  minute bars, ADV, CONF), scripts/probes/_562bf_minute.tsv.gz (held-session minute bars to 08-31),
  scripts/probes/_685/pull_main_out.txt + pull_min_out.tsv.gz (2026-09-28 16:57Z: alerts and day-0
  bars since 09-01, every stored September minute bar for the cohort, fresh daily bars 2026-01-01..
  09-25 — 0 of 41,396 common rows drift vs the old capture). A held session with NO stored minute
  bars: A0/A1 fall back to the daily bar exactly as the harness does; A2/A3 are UNREADABLE on that
  trade if the day is trail-governed and the low is at/below the line (counted, never guessed).
  Stored bars exist only for names the system tracked (positions open or closed that day, alert-day
  names, the #562 backfill), so the hole is not random — stated in the doc.

AMENDMENT 2026-09-28, AFTER THE FIRST RUN (stated so, because it is not pre-registered):
  The first run used the population rule above verbatim (re-admit == 'admit'; n = 69 paired). It
  excluded VICR (09-17), a real live trade and the only +8 ORB-R partial of the live era, because the
  harness cannot see the float bonus and its re-score straddles the bar ('abstain_float_band_straddles_bar')
  — a harness limitation, not a rejection by the rule. The population was then WIDENED to also include
  the 33 live-admitted HIGH alerts whose re-score straddles the bar (11 entered: TE, VPG, VSTS, CRMD x2,
  KLAR, AGYS, APPS, TATT, TH, VICR). This was decided after the first run's paired differences had been
  seen (A1 -4.74 / p 0.014 on n = 69 -> A1 -4.08 / p 0.064 on n = 79). BOTH populations are reported in
  the doc; the widened one is the headline because it is the operator's "real EPs" rule, the
  pre-registered one is run with `--prereg` (outputs suffixed _prereg). The order of the arms and the
  conclusion are the same under both.
  A SECOND read-only prod read was taken at 17:08Z (pull_audit_0911.sql: mi_audit_log rows for OKTA and
  SEI around 09-11) after the first run showed every arm selling OKTA at the 09-11 close while live held it.

WALKER FIDELITY (checked before the arms are read): the minute walker with the line as the resting
  stop must reproduce the harness' A0 (era_d) on every trade both settle, and with the signature
  off it must reproduce the harness' close-only arm; disagreements are listed, not averaged away.
  The one harness-side re-derivation: the day-0 end state (partial fired / breakeven armed on day 0)
  is read off the harness' exits and the day-0 bars with the harness' own predicates.
====================================================================================
"""
from __future__ import annotations

import gzip
import json
import random
import statistics
import sys
from collections import Counter, defaultdict
from dataclasses import dataclass, replace
from datetime import date, datetime, time, timedelta
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[2]
sys.path.insert(0, str(REPO / "scripts"))
sys.path.insert(0, str(REPO))
import ep_replay as ep  # noqa: E402
from agents.market_intelligence.broker.exit_logic import apply_daily_exit_step, seed_exit_state  # noqa: E402
from agents.market_intelligence.broker.order_manager import profit_target_r_per_share  # noqa: E402

_ET = ep._ET
HORIZON = date(2026, 9, 25)
ANCHOR_HORIZON = date(2026, 8, 31)
SPLIT_DATE = date(2026, 8, 31)          # DISCOVERY <= this, HELD-OUT after
GRACE_END = time(10, 30)
ADR_MULT = 1.0
N_PERM = 5000
SEED = 685
ARMS = ("A0", "A1", "A2k2", "A2k3", "A3")
# --prereg: the population rule exactly as pre-registered (re-admit == 'admit' only; see AMENDMENT).
INCLUDE_LIVE_HIGH_ABSTAIN = "--prereg" not in sys.argv
SUFFIX = "" if INCLUDE_LIVE_HIGH_ABSTAIN else "_prereg"

OUT = HERE


# ── data ──────────────────────────────────────────────────────────────────────────────

def _rth(bars):
    return [b for b in bars if time(9, 30) <= b["m"].time() < time(16, 0)]


def load_new_minutes() -> dict[tuple[str, date], list[dict]]:
    by: dict[tuple[str, date], list[dict]] = {}
    with gzip.open(HERE / "pull_min_out.tsv.gz", "rt") as fh:
        for line in fh:
            p = line.rstrip("\n").split("|")
            if len(p) != 7 or p[0] in ("ticker",) or p[0].startswith("==="):
                continue
            try:
                dt = datetime.strptime(p[1], "%Y-%m-%d %H:%M").replace(tzinfo=_ET)
                bar = {"m": dt, "o": float(p[2]), "h": float(p[3]), "l": float(p[4]), "c": float(p[5])}
            except ValueError:
                continue
            by.setdefault((p[0], dt.date()), []).append(bar)
    out = {}
    for k, bars in by.items():
        seen = {}
        for b in bars:
            seen[b["m"]] = b
        out[k] = sorted(seen.values(), key=lambda b: b["m"])
    return out


def load_all():
    S = ep.read_sections(HERE / "pull_main_out.txt")
    old2 = ep.read_sections(ep.DATA / "_pull2_out.txt")
    old3 = ep.read_sections(ep.DATA / "_pull3_out.txt")
    old5 = ep.read_sections(ep.DATA / "_pull5_out.txt")
    conf = {r["id"]: r["confidence_multiplier"] for r in old5["CONF"]}
    alerts = [{**a, "confidence_multiplier": conf.get(a["id"])} for a in old2["ALERTS"]]
    alerts += list(S["ALERTS"])
    # one ORB entry per ticker-day, earliest detection (phase_replay's rule)
    seen: dict[tuple, dict] = {}
    for a in alerts:
        k = (a["ticker"], a["alert_date"])
        if k not in seen or (a.get("detected_at_et") or "") < (seen[k].get("detected_at_et") or ""):
            seen[k] = a
    alerts = sorted((a for a in seen.values() if date.fromisoformat(a["alert_date"]) <= HORIZON),
                    key=lambda a: (a["alert_date"], a["ticker"]))
    regime = {r["regime_date"]: r for r in old2["REGIME"]}
    regime.update({r["regime_date"]: r for r in S["REGIME"]})
    regime_rows = sorted(regime.values(), key=lambda r: r["regime_date"])
    adv = {(r["ticker"], r["score_date"]): ep._f(r["adv_20"]) for r in old3["ADV"]}
    adv.update({(r["ticker"], r["score_date"]): ep._f(r["adv_20"]) for r in S["ADV"]})
    daily: dict[str, dict[date, dict]] = {}
    for r in S["DAILY"]:
        d = date.fromisoformat(r["trade_date"])
        daily.setdefault(r["ticker"], {})[d] = {
            "o": ep._f(r["open_price"]), "h": ep._f(r["high_price"]),
            "l": ep._f(r["low_price"]), "c": ep._f(r["close"]), "v": ep._f(r["volume"])}
    day0 = ep.load_minutes()                      # 09-01 capture, alert-day bars
    newmin = load_new_minutes()
    for k, bars in newmin.items():
        day0.setdefault(k, _rth(bars))
    held = ep.load_minutes_extra()                # #562 backfill to 08-31
    for k, bars in newmin.items():
        if k not in held:
            held[k] = _rth(bars)
    mincov = {(r["ticker"], date.fromisoformat(r["d"])): int(r["n"]) for r in S["MINCOV"]}
    trades = S["TRADES"]
    return alerts, regime_rows, adv, daily, day0, held, mincov, trades, S


# ── harness population walk ────────────────────────────────────────────────────────

def harness_walk(alerts, regime_rows, adv, daily, day0, rs, horizon):
    ep.LAST_SETTLED = horizon
    rows = []
    for a in alerts:
        ad, sc = ep._score_one(a, rs, daily, adv, regime_rows)
        submit = time(9, 31)
        if a.get("detected_at_et"):
            det = datetime.fromisoformat(a["detected_at_et"]).time()
            submit = max(submit, time(det.hour, det.minute))
        res = ep.walk_campaign(ticker=a["ticker"], alert_date=ad, rs=rs, minutes=day0,
                               daily=daily, submit=submit)
        res.update(admit=sc["admit"], score_lo=sc["score_lo"], score_hi=sc["score_hi"],
                   submit=submit, alert=a)
        rows.append(res)
    return rows


def paired_summary(a_rows, b_rows):
    A = {(r["ticker"], r["alert_date"]): r for r in a_rows if r["admit"] == "admit"}
    B = {(r["ticker"], r["alert_date"]): r for r in b_rows if r["admit"] == "admit"}
    both = [k for k in A if A[k]["status"] == "settled" and B[k]["status"] == "settled"]
    sa = sum(A[k]["realized_r"] for k in both)
    sb = sum(B[k]["realized_r"] for k in both)
    diff = [k for k in both if abs(A[k]["realized_r"] - B[k]["realized_r"]) > 1e-9]
    worse = sum(1 for k in diff if B[k]["realized_r"] < A[k]["realized_r"])

    def marked(D):
        s = n = 0
        for k, x in D.items():
            if x["status"] == "settled":
                s += x["realized_r"]; n += 1
            elif x["status"] == "open_at_horizon" and x["mark_r"] is not None:
                s += x["mark_r"]; n += 1
        return s, n
    return {"admitted": len(A), "settled_a": sum(1 for k in A if A[k]["status"] == "settled"),
            "settled_b": sum(1 for k in B if B[k]["status"] == "settled"),
            "paired_n": len(both), "sum_a": sa, "sum_b": sb, "differ": len(diff), "b_worse": worse,
            "marked_a": marked(A), "marked_b": marked(B),
            "FTK": (A.get(("FTK", date(2026, 8, 3)), {}).get("realized_r"), B.get(("FTK", date(2026, 8, 3)), {}).get("realized_r")),
            "INFQ": (A.get(("INFQ", date(2026, 5, 21)), {}).get("realized_r"), B.get(("INFQ", date(2026, 5, 21)), {}).get("realized_r"))}


# ── the minute-grain forward walker ─────────────────────────────────────────────────

@dataclass
class Arm:
    name: str
    line_rests: bool          # A0: the line is the resting stop
    k: int | None             # slice signature k (None = off)
    grace: bool               # A3: no signature before 10:30, catastrophic at line - ADR
    adr_stop: bool


ARM_DEFS = {
    "A0": Arm("A0", True, None, False, False),
    "A1": Arm("A1", False, None, False, False),
    "A2k2": Arm("A2k2", False, 2, False, False),
    "A2k3": Arm("A2k3", False, 3, False, False),
    "A3": Arm("A3", False, 2, True, True),
}


def _w5(m: datetime) -> int:
    return ((m.hour * 60 + m.minute) - 570) // 5


def _w5_start(w: int) -> time:
    mins = 570 + 5 * w
    return time(mins // 60, mins % 60)


def day0_state(h: dict, day0_bars: list[dict], rs) -> dict | None:
    """The end-of-day-0 state, read off the harness result + its own predicates."""
    if not h["entered"] or h["status"] in ("no_trade", "no_entry"):
        return None
    if h["status"] == "abstain" and not str(h["reason"]).startswith("fwd_"):
        return None
    entry, stop, target = h["entry_px"], h["stop"], h["target"]
    ad = h["alert_date"]
    ex0 = [e for e in h["exits"] if "T" in str(e["time"]) or " " in str(e["time"])]
    ex0 = [e for e in ex0 if str(e["time"])[:10] == ad.isoformat()]
    settled_d0 = any(e["reason"] == "stop_hit" for e in ex0)
    partial_d0 = any(e["reason"] == "partial_profit" for e in ex0)
    r_ps = profit_target_r_per_share("magna53", entry, stop, h["orb_low"])
    be_trigger = entry + rs.breakeven_at_r * r_ps
    # breakeven armed on day 0: any bar from the fill bar onward traded >= the arm level
    fill_minute = h.get("fill_minute")
    armed = partial_d0 and rs.breakeven_at_partial
    if fill_minute is not None:
        for b in day0_bars:
            if b["m"] >= fill_minute and b["h"] >= be_trigger:
                armed = True
                break
    shares = 1.0 / (entry - stop)
    remaining = shares - sum(e["shares"] for e in ex0)
    return {"entry": entry, "hard": stop, "target": target, "r_ps": r_ps, "be_trigger": be_trigger,
            "shares": shares, "remaining": remaining, "partial_taken": partial_d0,
            "be_active": armed, "exits": [dict(e) for e in ex0], "settled_d0": settled_d0,
            "adr_pct": h["adr_pct"]}


def walk_hybrid_arm(*, ticker, alert_date, st, arm: Arm, daily, held, horizon, mincov, line0=None) -> dict:
    """Forward walk from day 1 under one arm. Returns status/exits/R/diagnostics."""
    entry, hard = st["entry"], st["hard"]
    shares, remaining = st["shares"], st["remaining"]
    partial_taken, be_active = st["partial_taken"], st["be_active"]
    target, be_trigger = st["target"], st["be_trigger"]
    adr_pct = st["adr_pct"]
    exits = [dict(e) for e in st["exits"]]
    risk_denom = shares * (entry - hard)
    out = {"arm": arm.name, "status": None, "reason": None, "exits": exits, "final_reason": None,
           "realized_r": None, "mark_r": None, "exit_day": None, "gap_through": False,
           "sessions_abstained": 0, "line_tests": [], "sig_fires": [], "unreadable": False,
           "unreadable_days": [], "daily_fallback_days": [], "held_sessions": 0,
           "last_close": None}
    dbars = daily.get(ticker, {})
    prior = [dbars[d]["c"] for d in sorted(dbars) if d < alert_date and dbars[d]["c"] is not None]
    state = seed_exit_state(alert_date=alert_date, entry_price=entry, hard_stop=hard,
                            remaining_shares=remaining, partial_taken=partial_taken,
                            breakeven_active=partial_taken, exits=list(exits))
    line = max(hard, entry if be_active else hard)   # ratchet (A0's resting stop); starts at the floor
    if line0 is not None:
        line = max(line, line0)
    closed = False
    d = alert_date
    last_close = None

    def book(px, qty, reason, when):
        exits.append({"time": str(when), "price": px, "reason": reason, "shares": qty,
                      "pnl": (px - entry) * qty})

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
            out["sessions_abstained"] += 1
            continue
        out["held_sessions"] += 1
        last_close = b["c"]
        floor = max(hard, entry) if be_active else hard
        line = max(line, floor)
        line_r = round(line, 2)
        trail_governed = line_r > round(floor, 2) + 1e-9
        if arm.line_rests:
            rest = line_r
        elif arm.adr_stop and trail_governed and adr_pct:
            rest = max(round(floor, 2), round(line_r - ADR_MULT * adr_pct * line_r, 2))
        else:
            rest = round(floor, 2)
        mb = held.get((ticker, d), [])
        n_bars = len(mb)
        day_low_test = trail_governed and b["l"] <= line_r
        if day_low_test:
            out["line_tests"].append({"day": d, "line": line_r, "low": b["l"], "close": b["c"],
                                      "cls": "RECLAIM" if b["c"] >= line_r else "SLICE",
                                      "open": b["o"], "n_bars": n_bars})
        if n_bars == 0 and arm.k is not None and day_low_test:
            out["unreadable"] = True
            out["unreadable_days"].append(d)
        # ── intraday minute walk ──
        breached = False
        win: dict[int, dict] = {}
        win_order: list[int] = []
        prev_low = None
        run = 0
        breach_w = None
        for i, mbar in enumerate(mb):
            # breakeven arm on price (live: 5-min poll on the bar high; here: the bar itself)
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
                if px != rest:
                    out["gap_through"] = True
                book(px, remaining, "stop_hit", mbar["m"])
                remaining = 0.0
                out["final_reason"] = "stop_hit"
                out["exit_day"] = d
                closed = True
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
            # ── slice signature ──
            if arm.k is not None and trail_governed:
                if not breached and mbar["l"] <= line_r:
                    breached = True
                    breach_w = _w5(mbar["m"])
                w = _w5(mbar["m"])
                if w not in win:
                    win[w] = {"h": mbar["h"], "l": mbar["l"], "c": mbar["c"], "o": mbar["o"]}
                    win_order.append(w)
                    # the previous window just completed -> evaluate it
                    if len(win_order) >= 2:
                        pw = win_order[-2]
                        ppw = win_order[-3] if len(win_order) >= 3 else None
                        W = win[pw]
                        eligible = breached and breach_w is not None and pw > breach_w
                        if arm.grace and _w5_start(pw) < GRACE_END:
                            eligible = False
                        if eligible and ppw is not None and pw - ppw == 1:
                            rng_ = W["h"] - W["l"]
                            slice_bar = (W["l"] < win[ppw]["l"]) and rng_ > 0 and (W["c"] <= W["l"] + rng_ / 3)
                        else:
                            slice_bar = False
                        run = run + 1 if slice_bar else 0
                        if run >= arm.k and W["c"] < line_r:
                            reason_ = f"slice_k{arm.k}"
                            # executes at THIS bar's open (the first minute after the k-th window closed)
                            px = mbar["o"]
                            book(px, remaining, reason_, mbar["m"])
                            out["sig_fires"].append({"day": d, "minute": mbar["m"].time().isoformat(),
                                                     "px": px, "line": line_r, "close": b["c"],
                                                     "false_sell": b["c"] >= line_r})
                            remaining = 0.0
                            out["final_reason"] = reason_
                            out["exit_day"] = d
                            closed = True
                            break
                else:
                    W = win[w]
                    W["h"] = max(W["h"], mbar["h"]); W["l"] = min(W["l"], mbar["l"]); W["c"] = mbar["c"]
        if closed:
            break
        # signature pending at the last window of the day (no bar followed): evaluate the final window
        if arm.k is not None and trail_governed and win_order and not closed:
            pw = win_order[-1]
            ppw = win_order[-2] if len(win_order) >= 2 else None
            W = win[pw]
            eligible = breached and breach_w is not None and pw > breach_w
            if arm.grace and _w5_start(pw) < GRACE_END:
                eligible = False
            if eligible and ppw is not None and pw - ppw == 1:
                rng_ = W["h"] - W["l"]
                slice_bar = (W["l"] < win[ppw]["l"]) and rng_ > 0 and (W["c"] <= W["l"] + rng_ / 3)
            else:
                slice_bar = False
            run = run + 1 if slice_bar else 0
            if run >= arm.k and W["c"] < line_r:
                px = W["c"]
                book(px, remaining, f"slice_k{arm.k}", datetime.combine(d, time(15, 59)))
                out["sig_fires"].append({"day": d, "minute": "15:59:00", "px": px, "line": line_r,
                                         "close": b["c"], "false_sell": b["c"] >= line_r})
                remaining = 0.0
                out["final_reason"] = f"slice_k{arm.k}"
                out["exit_day"] = d
                closed = True
                break
        # ── daily-grain fallback for what the minute walk could not see (no/partial bars) ──
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
        # ── the 16:45 job: the live ladder on the daily bar ──
        state.update(remaining_shares=remaining, partial_taken=partial_taken,
                     breakeven_active=be_active, exits=list(exits))
        state["hard_stop"] = rest
        step = apply_daily_exit_step(state, {"l": b["l"], "c": b["c"]}, d,
                                     integer_partial_shares=False, skip_partial_decision=True,
                                     trail_mode="sma", prior_closes=prior)
        state.update(running_closes=step.new_running_closes)
        if step.closed:
            px, reason = step.close_price, step.close_reason
            if reason == "stop_hit":
                if b["o"] is not None and b["o"] < px:
                    px = b["o"]
                    out["gap_through"] = True
                out["daily_fallback_days"].append(d)
            book(px, remaining, reason if reason != "sma_trail_stop" else "close_below_line", d)
            remaining = 0.0
            out["final_reason"] = "stop_hit" if reason == "stop_hit" else "close_below_line"
            out["exit_day"] = d
            closed = True
            break
        line = max(line, step.effective_stop)
    out["exits"] = exits
    out["last_close"] = last_close
    pnl = sum(e["pnl"] for e in exits)
    if closed:
        out["status"] = "settled"
        out["realized_r"] = pnl / risk_denom
    elif out["status"] == "open_at_horizon":
        lc = last_close if last_close is not None else entry
        out["mark_r"] = (pnl + (lc - entry) * remaining) / risk_denom
    return out


# ── statistics ────────────────────────────────────────────────────────────────────

def block_signflip_p(diffs: list[float], weeks: list[str], rng: random.Random) -> float:
    obs = abs(sum(diffs))
    if obs == 0:
        return 1.0
    groups = defaultdict(list)
    for i, w in enumerate(weeks):
        groups[w].append(i)
    idx = list(groups.values())
    hits = 0
    for _ in range(N_PERM):
        s = 0.0
        for g in idx:
            sign = 1 if rng.random() < 0.5 else -1
            s += sign * sum(diffs[i] for i in g)
        if abs(s) >= obs - 1e-12:
            hits += 1
    return hits / N_PERM


def drop_best_two(vals: list[float]) -> float:
    return sum(sorted(vals)[:-2]) if len(vals) > 2 else 0.0


def fmt(x, nd=2):
    return "—" if x is None else f"{x:+.{nd}f}"


# ── main ──────────────────────────────────────────────────────────────────────────

def main():
    alerts, regime_rows, adv, daily, day0, held, mincov, trades, S = load_all()
    log = open(OUT / f"study_out{SUFFIX}.txt", "w")

    def P(*a):
        s = " ".join(str(x) for x in a)
        print(s); log.write(s + "\n")

    P(f"# #685 study run {datetime.now(_ET).isoformat(timespec='seconds')} — alerts {len(alerts)} "
      f"({min(a['alert_date'] for a in alerts)} .. {max(a['alert_date'] for a in alerts)})")

    # ── STEP 0a: the anchor on the merged capture, 08-31 horizon ──
    old_alerts = [a for a in alerts if date.fromisoformat(a["alert_date"]) <= SPLIT_DATE]
    ra = harness_walk(old_alerts, regime_rows, adv, daily, day0, ep.RULESETS["era_c_rec_intraday_uc0"], ANCHOR_HORIZON)
    rb = harness_walk(old_alerts, regime_rows, adv, daily, day0, ep.RULESETS["era_c_rec_closeonly_uc0"], ANCHOR_HORIZON)
    anc = paired_summary(ra, rb)
    P("## ANCHOR (merged capture, horizon 08-31): intraday vs close-only —", json.dumps(anc, default=str))
    ok = (anc["paired_n"] == 62 and abs(anc["sum_a"] - 3.91) < 0.02 and abs(anc["sum_b"] + 1.40) < 0.02
          and anc["differ"] == 18 and anc["b_worse"] == 13 and anc["settled_a"] == 65)
    P("## ANCHOR REPRODUCED" if ok else "## ANCHOR FAILED — HALT")
    if not ok:
        log.close()
        raise SystemExit(2)
    # era_d vs era_c_rec_intraday_uc0 (breakeven_at_partial flag): must be identical on this population
    rd = harness_walk(old_alerts, regime_rows, adv, daily, day0, ep.RULESETS["era_d"], ANCHOR_HORIZON)
    A_ = {(r["ticker"], r["alert_date"]): r for r in ra}
    nd = sum(1 for r in rd if (r["status"] != A_[(r["ticker"], r["alert_date"])]["status"]) or
             ((r["realized_r"] or 0) - (A_[(r["ticker"], r["alert_date"])]["realized_r"] or 0)) > 1e-9)
    P(f"## era_d vs era_c_rec_intraday_uc0 on the same population: {nd} rows differ (expect 0)")

    # ── STEP 0b: the population under era D, horizon 09-25 (harness A0 and harness close-only) ──
    rs_d = ep.RULESETS["era_d"]
    rs_d_close = replace(rs_d, name="era_d_closeonly", trail_intraday=False)
    H0 = harness_walk(alerts, regime_rows, adv, daily, day0, rs_d, HORIZON)
    H1 = harness_walk(alerts, regime_rows, adv, daily, day0, rs_d_close, HORIZON)
    key = lambda r: (r["ticker"], r["alert_date"])
    H0m = {key(r): r for r in H0}; H1m = {key(r): r for r in H1}
    live_high_abstain = [r for r in H0 if INCLUDE_LIVE_HIGH_ABSTAIN and str(r["admit"]).startswith("abstain") and r["alert"].get("score_tier") == "HIGH"]
    P(f"## POPULATION RULE: {'WIDENED (re-admitted + live-admitted HIGH straddling the bar)' if INCLUDE_LIVE_HIGH_ABSTAIN else 'PRE-REGISTERED (re-admitted only)'}")
    adm = [r for r in H0 if r["admit"] == "admit"] + live_high_abstain
    adm.sort(key=lambda r: (r["alert_date"], r["ticker"]))
    P(f"## POPULATION under era D, horizon {HORIZON}: alerts {len(H0)}, re-admitted {len(adm) - len(live_high_abstain)} "
      f"+ {len(live_high_abstain)} live-admitted HIGH whose re-score straddles the bar on the unknown float bonus "
      f"({', '.join(r['ticker'] + ' ' + r['alert_date'].isoformat() for r in live_high_abstain if r['entered'])} entered) = {len(adm)}, "
      f"statuses {dict(Counter(r['status'] for r in adm))}, "
      f"discovery {sum(1 for r in adm if r['alert_date'] <= SPLIT_DATE)} / held-out {sum(1 for r in adm if r['alert_date'] > SPLIT_DATE)}")
    adm_keys = {key(r) for r in adm}
    P(f"   harness A0 (era_d) settled {sum(1 for r in adm if r['status']=='settled')} "
      f"sum {sum(r['realized_r'] for r in adm if r['status']=='settled'):+.2f}R; "
      f"harness close-only settled {sum(1 for r in H1 if key(r) in adm_keys and r['status']=='settled')} "
      f"sum {sum(r['realized_r'] for r in H1 if key(r) in adm_keys and r['status']=='settled'):+.2f}R")
    P(f"   abstain reasons: {dict(Counter(str(r['reason']).split(':')[0] for r in adm if r['status']=='abstain'))}")

    # ── the arms ──
    results: dict[str, dict[tuple, dict]] = {a: {} for a in ARMS}
    day0_only = {}
    excluded = Counter()
    for h in adm:
        k = key(h)
        bars0 = day0.get(k, [])
        orb = next((b for b in bars0 if b["m"].time() == time(9, 30)), None)
        h["orb_low"] = orb["l"] if orb else None
        h["orb_high"] = orb["h"] if orb else None
        if h["entered"] and orb:
            f = ep.entry_walk(bars0, orb["h"], h["submit"], rs_d.entry_cancel)
            h["fill_minute"] = f.get("minute") if f["status"] == "filled" else None
        else:
            h["fill_minute"] = None
        st = day0_state(h, bars0, rs_d)
        if st is None:
            excluded[h["status"] + ":" + str(h["reason"]).split(":")[0]] += 1
            continue
        if st["settled_d0"]:
            day0_only[k] = h["realized_r"]
            for a in ARMS:
                results[a][k] = {"arm": a, "status": "settled", "realized_r": h["realized_r"], "mark_r": None,
                                 "exits": h["exits"], "final_reason": "stop_hit", "exit_day": h["alert_date"],
                                 "line_tests": [], "sig_fires": [], "unreadable": False, "unreadable_days": [],
                                 "daily_fallback_days": [], "held_sessions": 0, "day0_settled": True,
                                 "gap_through": h["gap_through"]}
            continue
        for a in ARMS:
            r = walk_hybrid_arm(ticker=h["ticker"], alert_date=h["alert_date"], st=st, arm=ARM_DEFS[a],
                         daily=daily, held=held, horizon=HORIZON, mincov=mincov)
            r["day0_settled"] = False
            results[a][k] = r
    P(f"## ARMS: campaigns walked {len(results['A0'])} (settled on day 0 in every arm: {len(day0_only)}); "
      f"excluded before day 1: {dict(excluded)}")

    # ── walker fidelity vs the harness ──
    for arm, Hm, label in (("A0", H0m, "harness A0 (era_d)"), ("A1", H1m, "harness close-only")):
        agree = disagree = 0; dis = []
        for k, r in results[arm].items():
            hh = Hm[k]
            if r["status"] == "settled" and hh["status"] == "settled":
                if abs(r["realized_r"] - hh["realized_r"]) < 0.005:
                    agree += 1
                else:
                    disagree += 1
                    dis.append(f"{k[0]} {k[1]}: walker {r['realized_r']:+.3f} ({r['final_reason']} {r['exit_day']}) vs harness {hh['realized_r']:+.3f} ({hh['final_reason']})")
        P(f"## FIDELITY {arm} vs {label}: settled-both {agree+disagree}, within 0.005R {agree}, differ {disagree}")
        for s in dis:
            P("    ", s)
        st_ = Counter((r["status"], Hm[k]["status"]) for k, r in results[arm].items())
        P(f"    status pairs (walker, harness): {dict(st_)}")

    # ── LINE TESTS on the A1 path ──
    lt = [dict(x, ticker=k[0], alert_date=k[1]) for k, r in results["A1"].items() for x in r["line_tests"]]
    P(f"## LINE TESTS (A1 hold-through path): {len(lt)} trail-test days on {len({(x['ticker'], x['alert_date']) for x in lt})} trades; "
      f"RECLAIM {sum(1 for x in lt if x['cls']=='RECLAIM')} / SLICE {sum(1 for x in lt if x['cls']=='SLICE')}; "
      f"with minute bars {sum(1 for x in lt if x['n_bars']>0)}, without {sum(1 for x in lt if x['n_bars']==0)}")
    with open(OUT / f"line_tests{SUFFIX}.tsv", "w") as fh:
        fh.write("ticker|alert_date|day|line|open|low|close|class|n_bars\n")
        for x in sorted(lt, key=lambda x: (x["alert_date"], x["ticker"], x["day"])):
            fh.write(f"{x['ticker']}|{x['alert_date']}|{x['day']}|{x['line']}|{x['open']}|{x['low']}|{x['close']}|{x['cls']}|{x['n_bars']}\n")

    # ── per-trade table ──
    keys = sorted(results["A0"], key=lambda k: (k[1], k[0]))
    with open(OUT / f"arms_per_trade{SUFFIX}.tsv", "w") as fh:
        cols = ["ticker", "alert_date", "block", "entry", "hard", "orb_r_ps"] + \
               [f"{a}_{c}" for a in ARMS for c in ("status", "R", "markR", "final", "exit_day", "unreadable")]
        fh.write("|".join(cols) + "\n")
        for k in keys:
            h = H0m[k]
            row = [k[0], k[1].isoformat(), "DISC" if k[1] <= SPLIT_DATE else "HELD",
                   f"{h['entry_px']:.4f}", f"{h['stop']:.4f}",
                   f"{(h['entry_px'] - h['orb_low']):.4f}" if h.get("orb_low") else ""]
            for a in ARMS:
                r = results[a][k]
                row += [r["status"], "" if r["realized_r"] is None else f"{r['realized_r']:.4f}",
                        "" if r["mark_r"] is None else f"{r['mark_r']:.4f}", str(r["final_reason"]),
                        str(r["exit_day"]), str(r["unreadable"])]
            fh.write("|".join(row) + "\n")

    # ── MEASURES ──
    rng = random.Random(SEED)
    orb_r_ps = {k: (H0m[k]["entry_px"] - H0m[k]["orb_low"]) for k in keys if H0m[k].get("orb_low")}
    money_per_orb = {k: (H0m[k]["entry_px"] - H0m[k]["stop"]) / orb_r_ps[k] for k in orb_r_ps}  # ~2.0

    def to_orb(k, r_money):
        return r_money * money_per_orb[k]

    def block_of(k):
        return "DISC" if k[1] <= SPLIT_DATE else "HELD"

    table_rows = []
    for blk in ("ALL", "DISC", "HELD"):
        ks = [k for k in keys if blk == "ALL" or block_of(k) == blk]
        paired = [k for k in ks if all(results[a][k]["status"] == "settled" and not results[a][k]["unreadable"] for a in ARMS)]
        unread = {a: sum(1 for k in ks if results[a][k]["unreadable"]) for a in ARMS}
        openh = {a: sum(1 for k in ks if results[a][k]["status"] == "open_at_horizon") for a in ARMS}
        abst = {a: sum(1 for k in ks if results[a][k]["status"] == "abstain") for a in ARMS}
        common = [k for k in ks if all(not results[a][k]["unreadable"] and results[a][k]["status"] in ("settled", "open_at_horizon") for a in ARMS)]
        P(f"## BLOCK {blk}: campaigns {len(ks)}, paired (settled+readable in every arm) {len(paired)}; "
          f"unreadable per arm {unread}; open at horizon per arm {openh}; abstain per arm {abst}; "
          f"common marked set (settled or open, readable in every arm) {len(common)}")
        P(f"   names: unreadable {sorted({k[0] for k in ks if any(results[a][k]['unreadable'] for a in ARMS)})}; "
          f"open at horizon {sorted({k[0] for k in ks if any(results[a][k]['status']=='open_at_horizon' for a in ARMS)})}"
          + (f"; held-out campaigns {[k[0] + ' ' + k[1].isoformat() for k in ks]}" if blk == "HELD" else ""))
        base = {k: results["A0"][k]["realized_r"] for k in paired}
        for a in ARMS:
            R = {k: results[a][k]["realized_r"] for k in paired}
            vals = list(R.values())
            diffs = [R[k] - base[k] for k in paired]
            weeks = [f"{k[1].isocalendar()[0]}-W{k[1].isocalendar()[1]:02d}" for k in paired]
            p = block_signflip_p(diffs, weeks, random.Random(SEED * 10 + ARMS.index(a))) if a != "A0" else None
            better = sum(1 for x in diffs if x > 1e-9); worse = sum(1 for x in diffs if x < -1e-9)
            orb_vals = [to_orb(k, R[k]) for k in paired]
            win3 = sum(1 for x in orb_vals if x >= 3); win8 = sum(1 for x in orb_vals if x >= 8)
            worst = min(vals) if vals else None
            worst_k = min(paired, key=lambda k: R[k]) if paired else None
            big_loss = sum(1 for x in vals if x < -1.5)
            longer = sum(1 for k in paired if (results[a][k]["exit_day"] or date.max) > (results["A0"][k]["exit_day"] or date.max)) if a != "A0" else 0
            # marked (settled + open at horizon), all readable campaigns in the block
            marked = [(results[a][k]["realized_r"] if results[a][k]["status"] == "settled" else results[a][k]["mark_r"])
                      for k in common]
            marked = [x for x in marked if x is not None]
            row = {"block": blk, "arm": a, "n": len(paired), "sum": sum(vals), "mean": statistics.mean(vals) if vals else None,
                   "sum_orb": sum(orb_vals), "dbt": drop_best_two(vals), "diff": sum(diffs), "diff_dbt": drop_best_two(vals) - drop_best_two(list(base.values())),
                   "p": p, "better": better, "worse": worse, "win3": win3, "win8": win8,
                   "worst": worst, "worst_k": worst_k, "big_loss": big_loss, "open": openh[a], "longer": longer,
                   "unreadable": unread[a], "marked_sum": sum(marked), "marked_n": len(marked), "marked_dbt": drop_best_two(marked),
                   "median": statistics.median(vals) if vals else None}
            table_rows.append(row)
            P(f"   {a:5s} n={row['n']:3d} total {row['sum']:+7.2f} money-R ({row['sum_orb']:+7.2f} ORB-R) drop-best-2 {row['dbt']:+7.2f} | "
              f"vs A0 {row['diff']:+6.2f} p={'—' if p is None else f'{p:.3f}'} better/worse {better}/{worse} | "
              f">=3ORB-R {win3} >=8ORB-R {win8} | worst {fmt(worst)} ({worst_k[0] if worst_k else ''}) | losses<-1.5R {big_loss} | "
              f"open@horizon {openh[a]} held-longer-than-A0 {longer} | marked {row['marked_sum']:+.2f} over {row['marked_n']} (dbt {row['marked_dbt']:+.2f}) | median {fmt(row['median'])}")
    for blk in ("ALL", "DISC", "HELD"):
        ks = [k for k in keys if blk == "ALL" or block_of(k) == blk]
        p01 = [k for k in ks if results["A0"][k]["status"] == "settled" and results["A1"][k]["status"] == "settled"]
        d01 = [results["A1"][k]["realized_r"] - results["A0"][k]["realized_r"] for k in p01]
        w01 = [f"{k[1].isocalendar()[0]}-W{k[1].isocalendar()[1]:02d}" for k in p01]
        P(f"## A0 vs A1 ONLY ({blk}, the 09-06 question with the horizon at {HORIZON}): n={len(p01)} "
          f"A0 {sum(results['A0'][k]['realized_r'] for k in p01):+.2f} A1 {sum(results['A1'][k]['realized_r'] for k in p01):+.2f} "
          f"diff {sum(d01):+.2f} p={block_signflip_p(d01, w01, random.Random(SEED * 10 + 7)):.3f} better/worse {sum(1 for x in d01 if x > 1e-9)}/{sum(1 for x in d01 if x < -1e-9)}")
        for k in p01:
            if abs(results['A1'][k]['realized_r'] - results['A0'][k]['realized_r']) > 1e-9 and k[0] in ("HTFL", "ARGX", "THC", "U", "ROIV", "TEAM"):
                P(f"    {k[0]} {k[1]}: A0 {results['A0'][k]['realized_r']:+.2f} ({results['A0'][k]['exit_day']}) A1 {results['A1'][k]['realized_r']:+.2f} ({results['A1'][k]['final_reason']} {results['A1'][k]['exit_day']})")

    with open(OUT / f"arms_summary{SUFFIX}.tsv", "w") as fh:
        cols = list(table_rows[0].keys())
        fh.write("|".join(cols) + "\n")
        for r in table_rows:
            fh.write("|".join("" if r[c] is None else str(r[c]) for c in cols) + "\n")

    # ── signature accuracy ──
    for a in ("A2k2", "A2k3", "A3"):
        fires = [(k, f) for k, r in results[a].items() for f in r["sig_fires"]]
        false_sells = sum(1 for _, f in fires if f["false_sell"])
        # recall: SLICE days on the A1 path while this arm still held at the start of that day
        slice_days = [(k, x) for k, r in results["A1"].items() for x in r["line_tests"] if x["cls"] == "SLICE"]
        held_slice = [(k, x) for k, x in slice_days
                      if results[a][k]["exit_day"] is None or results[a][k]["exit_day"] >= x["day"]]
        caught = sum(1 for k, x in held_slice if any(f["day"] == x["day"] for f in results[a][k]["sig_fires"]))
        readable_slice = sum(1 for k, x in held_slice if x["n_bars"] > 0)
        P(f"## SIGNATURE {a}: fires {len(fires)}, on days that closed back above the line (false sells) {false_sells}; "
          f"SLICE days while still held {len(held_slice)} (readable {readable_slice}), exited by the signature on the day {caught}")
        for k, f in fires:
            P(f"    fire {k[0]} {k[1]} on {f['day']} {f['minute']} at {f['px']:.2f} line {f['line']:.2f} close {f['close']:.2f} {'FALSE' if f['false_sell'] else 'slice'}")

    # ── trade-by-trade differences vs A0 ──
    P("## PER-TRADE (paired ALL): where any arm differs from A0")
    ks_all = [k for k in keys if all(results[a][k]["status"] == "settled" and not results[a][k]["unreadable"] for a in ARMS)]
    for k in ks_all:
        r0 = results["A0"][k]["realized_r"]
        if any(abs(results[a][k]["realized_r"] - r0) > 1e-9 for a in ARMS):
            P(f"    {k[0]:6s} {k[1]} " + " ".join(f"{a}:{results[a][k]['realized_r']:+.2f}({str(results[a][k]['final_reason'])[:12]},{results[a][k]['exit_day']})" for a in ARMS))

    # ── THE OKTA CASE ──
    k_ok = ("OKTA", date(2026, 8, 27))
    if k_ok in results["A0"]:
        P("## OKTA (trade 382) IN THE REPLAY (alert 08-27, entry 167.88, hard stop 150.52, +3 ORB-R arm 193.92): "
          + "; ".join(f"{a}: {results[a][k_ok]['realized_r']:+.2f}R {results[a][k_ok]['final_reason']} {results[a][k_ok]['exit_day']}" for a in ARMS))
        for x in results["A1"][k_ok]["line_tests"]:
            P(f"    OKTA line test {x['day']}: line {x['line']:.2f} open {x['open']} low {x['low']} close {x['close']} -> {x['cls']}")
    try:
        aud = ep.read_sections(HERE / "pull_audit_0911_out.txt")
        fails = [r for r in aud["OKTA_0911"] if "Full exit FAILED" in (r.get("detail") or "") or "Full exit FAILED" in (r.get("summary") or "")]
        for r in fails:
            P(f"## OKTA 09-11 LIVE: {r['created_et'][:19]} {r['event_type']}: {(r.get('detail') or '')[:260]}")
    except Exception as e:
        P(f"## OKTA 09-11 audit read failed: {e}")
    bars_ok = held.get(("OKTA", date(2026, 9, 28)), [])
    if bars_ok:
        adr_ok = H0m[k_ok]["adr_pct"] if k_ok in H0m else None
        syn = {"o": bars_ok[0]["o"], "h": max(b["h"] for b in bars_ok), "l": min(b["l"] for b in bars_ok),
               "c": bars_ok[-1]["c"], "v": None}
        daily_ok = dict(daily); daily_ok["OKTA"] = {**daily["OKTA"], date(2026, 9, 28): syn}
        r_ps = 167.879 - 159.20
        st_ok = {"entry": 167.879, "hard": 150.52, "target": 167.879 + 8 * r_ps, "r_ps": r_ps,
                 "be_trigger": 167.879 + 3 * r_ps, "shares": 1 / (167.879 - 150.52), "remaining": 1 / (167.879 - 150.52),
                 "partial_taken": False, "be_active": True, "exits": [], "settled_d0": False, "adr_pct": adr_ok}
        P(f"## OKTA 2026-09-28 WALK (partial day: {len(bars_ok)} bars {bars_ok[0]['m'].time()}..{bars_ok[-1]['m'].time()} ET; "
          f"line 193.25 = the broker stop; floor = entry 167.88 (breakeven armed 09-22); ADR20% at entry {adr_ok:.3f} -> "
          f"A3 catastrophic {max(167.88, round(193.25 - ADR_MULT * adr_ok * 193.25, 2)):.2f}; open {syn['o']} low {syn['l']} high {syn['h']} last {syn['c']})")
        for a in ARMS:
            r = walk_hybrid_arm(ticker="OKTA", alert_date=date(2026, 9, 25), st=st_ok, arm=ARM_DEFS[a], daily=daily_ok,
                         held=held, horizon=date(2026, 9, 28), mincov=mincov, line0=193.25)
            intraday = [e for e in r["exits"] if e["reason"] != "close_below_line"]
            if intraday:
                e = intraday[-1]
                P(f"    {a}: SOLD intraday at {e['price']:.2f} ({e['reason']}, {str(e['time'])[11:16]} ET) = {(e['price'] - 167.879) / (167.879 - 150.52):+.2f} money-R")
            else:
                P(f"    {a}: still holding through {bars_ok[-1]['m'].time()} ET (last {syn['c']:.2f} = {(syn['c'] - 167.879) / (167.879 - 150.52):+.2f} money-R); the close test is unknowable until 16:00")
        # the 5-minute windows he would have watched
        win = {}
        order = []
        for b in bars_ok:
            w = _w5(b["m"])
            if w not in win:
                win[w] = {"o": b["o"], "h": b["h"], "l": b["l"], "c": b["c"]}; order.append(w)
            else:
                W = win[w]; W["h"] = max(W["h"], b["h"]); W["l"] = min(W["l"], b["l"]); W["c"] = b["c"]
        P("    5-min windows (start ET, o/h/l/c, lower-low vs prior, close in bottom third, close below 193.25):")
        for i, w in enumerate(order[:18]):
            W = win[w]; pv = win[order[i - 1]] if i else None
            ll = pv is not None and W["l"] < pv["l"]
            bt = (W["h"] > W["l"]) and W["c"] <= W["l"] + (W["h"] - W["l"]) / 3
            P(f"      {_w5_start(w).strftime('%H:%M')} {W['o']:.2f}/{W['h']:.2f}/{W['l']:.2f}/{W['c']:.2f}  lower-low={'Y' if ll else 'n'} bottom-third={'Y' if bt else 'n'} below-line={'Y' if W['c'] < 193.25 else 'n'}")

    # ── the live-era real trades, for composition ──
    P("## LIVE-ERA REAL MAGNA53 TRADES since 09-01 (mi_live_trades, composition only):")
    for t in trades:
        if t["alert_date"] >= "2026-09-01" and t["status"] in ("closed", "filled"):
            P(f"    {t['ticker']} {t['alert_date']} {t['status']} entry {t['entry_price']} stop {t['stop_price']} pnl {t['total_pnl']} risk {t['risk_dollars_actual']}")

    json.dump({a: {f"{k[0]}|{k[1]}": {kk: (str(v) if not isinstance(v, (int, float, bool, type(None), list, dict)) else v)
                                        for kk, v in r.items() if kk != "exits"}
                   for k, r in results[a].items()} for a in ARMS},
              open(OUT / f"arms_results{SUFFIX}.json", "w"), default=str, indent=0)
    log.close()
    return results, H0m, daily, held, adm


if __name__ == "__main__":
    main()
