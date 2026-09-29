"""#687 — DOES THE DEPTH TRAIL BEAT TODAY'S STOP? A backfill on a REBUILT EP-like population, 2024-01 → 2026-04.

================================ PRE-REGISTRATION ==================================
Written 2026-09-29 BEFORE any outcome was computed: the entry-day minute bars were still being fetched when this
banner was written and no entry, day-0 or forward walk had run. Everything below it is fixed; the numbers in
docs/analysis/687_depth_trail_backfill_2026-09-29.md were produced by this file afterwards. $0 beyond Polygon
(subscription) calls; prod read-only, captured once; no live code, PLAN.md or prod state touched.

POPULATION (STEP 0, population.py, HALT-checked, composition in population_out.txt): a REBUILT EP-like list, NOT
  our live alerts — 2,607 gap-days on 1,571 tickers, every rule fixed before any outcome (gap >= 9% at the open,
  raw prior close >= $5 and raw prior-day volume >= 50k after split un-adjustment, 30-day median $volume >= $1M,
  ATR14% <= 15%, extension < 50% over the prior sessions, common stock/ADR only incl. names delisted since, one
  entry per ticker per 60 days, and a full-day volume >= 3x the prior-20-session mean as a LOOK-AHEAD PROXY for the
  live RVOL gate). No catalyst / score / regime / market-cap / pre-market-share gate exists for this history.
  DISCOVERY = entry day in 2024 (1,090). HELD-OUT = 2025-01-02 .. 2026-04-30 (1,517). Fixed now; nothing is tuned
  on either block.

DATA: daily bars from mi_daily_closes (pull_daily_out.txt, per-ticker windows [first entry − 70d, 2026-08-31]);
  minute bars RE-FETCHED from Polygon (adjusted=true, consolidated tape) inside the production container, one call
  per (ticker, day), paced, captured once: ROUND 1 = the entry day of every gap-day plus #685's 192 alert days (the
  anchor / feed check) = 2,799 pulls; ROUND 2 = every day a held position trades at/below its trail line, as the
  union over A0/A1/D10 from a DAILY-ONLY pass that emits (ticker, day) ONLY — no totals, no per-arm R — so the
  estimate (~3,300–3,800 pulls in all, under the ~6,000 cap; no sampling) is stated before the fetch. ET via
  ZoneInfo; RTH 09:30–15:59 kept. No 09:30 bar -> abstain (counted). FEED: prod runs ALPACA_DATA_FEED=sip on both
  containers, so Polygon's consolidated bars are the same feed class as the live ORB; the residual is measured on
  #685's alert days (anchor c). HORIZON = 2026-08-31 (last daily bar in the pull); open positions are marked at the
  last close. A ticker whose daily bars END before the horizon (delisted / acquired) is force-closed at its last
  close in EVERY arm (identical across arms, so the pairing is unmoved) and counted as 'delisted_forced_close'.

THE LIVE ORDER (entry_pipeline.submit_trade_entry -> order_manager.submit_entry, #500 ON since 08-07), mirrored:
  ORB = the 09:30 one-minute bar (high H, low L). validate_orb_entry(H, L, ATR14): zero range -> no trade; H − L >
  1.5 x ATR14 (Wilder TR, rows [D−35, D−1], last 14 TRs; < 10 rows -> no gate, as live) -> SETUP_STOP_TOO_WIDE.
  Stop = 2L − H (entry − 2 ORB-R). Submit 09:31 (a pre-open gap alerts before the open; the 09:45 window cut never
  binds here — stated). Latest trade at submit := the 09:31 bar's OPEN (the proxy; the 09:30 close is the
  alternative and the number of fills that flip under it is reported).
    px > H  -> marketable limit at round(px x 1.002, 2). CHASE CAP: (limit − stop) <= 1.5 x (H − stop), else SKIP
              (SETUP_CHASE_CAP_EXCEEDED, counted). Fill = min(open, limit) in the 09:31 bar when its low <= limit
              (fill_at_open); else the limit rests and fills AT the limit on the first later bar before 10:00 with
              low <= limit; else cancelled at 10:00 ('limit_not_reached', counted).
    px <= H -> stop-limit buy: stop H, limit stop_limit_buy_price(H) (max(0.5%, $0.02) above H), walked 09:31..09:59
              exactly as ep_replay.entry_walk (a bar opening < H with high >= H -> fill at H; opening in [H, limit]
              -> fill at the open; opening above the limit -> rests, fills at the limit on a later low <= limit);
              unfilled at 10:00 -> cancelled ('never_crossed', counted); a gap in the minute coverage over the window
              with no cross -> abstain (counted).
  NOT modelled (stated): portfolio safeguards (max positions, breakers, daily-loss), sizing / the notional cap, the
  fade guard (MAGNA53 HIGH passes None), the ask-aware branch (the same proxy price here), broker rejects, slippage.

DAY 0 = ep_replay._walk_leg under era_d with ep.LAST_SETTLED pinned to the entry day so it stops after day 0: hard
  stop touch -> fill at the stop (the open if gapped through); the +8 ORB-R partial (1/3) at the target on touch,
  R_orb = entry − L (profit_target_r_per_share); breakeven armed when a bar's high >= entry + 3 ORB-R; the
  unorderable same-bar cases abstain (day0_fill_bar_straddles_stop / day0_stop_and_target_same_bar /
  day0_stop_and_breakeven_same_bar) and are counted, never guessed. The day-0 end state is read by
  scripts/probes/_685/study.day0_state — the #685 function, unchanged.

FORWARD WALK from day 1 = scripts/probes/_685/study.walk_hybrid_arm, IMPORTED UNCHANGED (the same instrument as
  #685): the 16:45 ladder (apply_daily_exit_step, trail_mode 'sma' = max(SMA10, SMA20) of the stock's own closes
  with the entry day's close omitted, prior closes from the daily pull), a minute walk on days with bars and the
  daily fallback otherwise, gap-throughs charged at the open, ADR = adr20_pct over the 20 sessions BEFORE the entry
  day (ep.adr20_pct — the #685 fix). A trade with no ADR (< 10 prior sessions) cannot host D10 and is dropped from
  the pairing (counted).

ARMS on the SAME filled trades, paired vs A0:
  A0   today's stop: the line rests at the broker; touch -> fill at the line, gap-through at the open.  [= live]
  A1   close-only: the line never rests; sell at the close if the close is below max(floor, line); the floor (hard
       stop; entry once breakeven is armed) rests.
  D10  the depth rule (#685 follow-up), FIXED at 1.0 x ADR — NO re-tuning on this data: a stop rests at
       max(floor, line − 1.0 x ADR20% x line) on trail-governed days (touch -> fill there; gap -> the open); else A1's
       close test. = study.Arm(line_rests=False, k=None, grace=False, adr_stop=True) with study.ADR_MULT = 1.0.
  (Neither the slice signature nor the first-hour grace is re-run: #685's verified read left them behind D10.)

RUNNER-EXIT ARMS (a SEPARATE question with its own table — the 08-29 sweep's post-partial rules re-cut to era D).
  Under era D the partial is +8 ORB-R, so a runner rule engages on FEW trades: #685 saw 1 of 86 reach it; expect a
  few dozen here at most — stated before running. Pre-partial every runner arm IS A0 (the era-D stack governs until
  the partial fires, and the trail can stop the trade first). After the partial fires on day P:
    T20  hold 20 sessions after P and sell at the 20th session's close; a floor touch before that -> stop.
    S20  sell at the first close below the stock's SMA20 (the last 20 closes through that day); floor touch -> stop.
  Two floors, BOTH declared now, never chosen after: '_hs' = the sweep's literal (the hard stop entry − 2R stays as
  the touch floor — under era D the resting stop would step DOWN from entry after the partial, which live's
  raise-only stop cannot do; reported as the sweep's own definition); '_be' = the era-D-consistent floor (entry;
  breakeven is armed at +3 ORB-R before any +8 ORB-R partial). Daily grain after P: low <= floor -> fill at the
  floor (the open if it gapped under). On P itself: with minute bars, the post-partial bars are walked against the
  floor; without, the position holds through P (A0's own stop on P is >= the floor, and a P whose low reaches A0's
  stop is an A0 abstain, so the pair is unaffected). The 20th session's touch is checked before its close, as the
  sweep did. Control = A0. If no partial fires, every runner arm equals A0 by construction.

MEASURES (per arm; DISCOVERY / HELD-OUT / ALL; paired vs A0 on trades every arm settles): total and mean money-R
  (money-R = pnl per dollar of ACTUAL fill risk = entry − stop, #685's unit; 1 money-R = 2 ORB-R at a cross fill,
  less on a chase fill — the live R unit, stated) with ORB-R beside; paired difference; a week-block sign-flip
  permutation p (blocks = ISO week of the entry day, 5,000 draws, seed 687, two-sided); better / worse counts
  (|diff| > 0.005R); drop-the-best-two beside every total; winners kept (>= 3 ORB-R, >= 8 ORB-R); worst single
  trade; losses beyond −1.5 money-R; held longer than A0; open at horizon; delisted force-closes. Realised R vs the
  PLANNED risk (H − stop, what live sizes on) is also totalled, because a chase fill carries up to 1.5x planned risk.

LINE-TEST TABLE (descriptive; the A1 hold-through path): every trail-governed held day whose low <= the line: depth
  below the line in $ and in ADR multiples (the daily low), RECLAIM (close >= line) / SLICE (close below), and what
  A0 / A1 / D10 did on that day.

ANCHOR (STEP 2 — must pass BEFORE any population number is read, else HALT):
  (a) forward half: depth.py's fidelity-gate pattern — rebuild #685's population and day-0 states with study.py's
      own functions, walk A0 and A1 with THIS file's wrapper, and match arms_per_trade.tsv on the 79 paired trades:
      totals A0 −5.77 / A1 −9.85 money-R within 0.01R and every trade within 0.005R.
  (b) day-0 half: THIS file's day-0 builder (ep._walk_leg pinned to day 0 + study.day0_state) must reproduce
      study.day0_state on every #685 campaign that reaches day 1 (entry, hard, remaining, partial, breakeven).
  (c) entry half CANNOT match by design (#685 used entry_walk's stop-limit walk for every alert; the live path
      chases or skips when price is already above H at submit — the #684 late-alert CHECK): report the fill delta
      on #685's 192 admitted alerts with the STORED bars (fills / chase fills / chase-cap skips / unfilled), and the
      FEED delta: Polygon's 09:30 bar vs the stored bar on those days (how many H / L differ, by how much, how many
      entry verdicts flip).

ROUND-2 RULE: the daily-only pass emits the union of line-test days over A0 / A1 / D10 (the runner arms are daily
  grain after P by definition). If the re-walk with bars produces a line-test day not yet fetched, ONE more round;
  the residual is stated.
====================================================================================
"""
from __future__ import annotations

import collections
import csv
import gzip
import json
import random
import statistics
import sys
from dataclasses import replace
from datetime import date, datetime, time, timedelta
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[2]
sys.path.insert(0, str(HERE.parent / "_685"))
sys.path.insert(0, str(REPO / "scripts"))
sys.path.insert(0, str(REPO))
import study as ST  # noqa: E402  (the #685 machinery, imported unchanged)
import ep_replay as ep  # noqa: E402
from agents.market_intelligence.backtester.filters import validate_orb_entry  # noqa: E402
from agents.market_intelligence.broker.order_manager import (  # noqa: E402
    CHASE_RISK_INFLATION_CAP, profit_target_r_per_share, stop_limit_buy_price)

_ET = ep._ET
HORIZON = date(2026, 8, 31)
SUBMIT = time(9, 31)
CANCEL = time(10, 0)
SPLIT_END_DISC = date(2024, 12, 31)   # DISCOVERY <= this; HELD-OUT after
N_PERM = 5000
SEED = 687
RS_D = ep.RULESETS["era_d"]
MAIN_ARMS = ("A0", "A1", "D10")
RUNNER_ARMS = ("T20_hs", "S20_hs", "T20_be", "S20_be")
ARM_DEFS = {
    "A0": ST.ARM_DEFS["A0"],
    "A1": ST.ARM_DEFS["A1"],
    "D10": ST.Arm("D10", False, None, False, True),
}
MODE = "--pass1" if "--pass1" in sys.argv else "--anchor" if "--anchor" in sys.argv else "--final"
OUT = HERE


def fmt(x, nd=2):
    return "—" if x is None else f"{x:+.{nd}f}"


# ── data ──────────────────────────────────────────────────────────────────────────────

def load_population() -> list[dict]:
    rows = []
    with open(HERE / "population.tsv") as fh:
        for r in csv.DictReader(fh, delimiter="|"):
            r["d"] = date.fromisoformat(r["trade_date"])
            for k in ("o", "h", "l", "c", "v", "pc", "raw_pc", "gap_pct", "adv_dollar", "atr_pct", "vol_mult"):
                r[k] = ep._f(r.get(k))
            rows.append(r)
    return rows


def load_daily() -> dict[str, dict[date, dict]]:
    out: dict[str, dict[date, dict]] = {}
    with open(HERE / "pull_daily_out.txt") as fh:
        for line in fh:
            p = line.rstrip("\n").split("|")
            if len(p) != 7 or p[0] == "ticker" or p[0].startswith("==="):
                continue
            try:
                d = date.fromisoformat(p[1])
            except ValueError:
                continue
            out.setdefault(p[0], {})[d] = {"o": ep._f(p[2]), "h": ep._f(p[3]), "l": ep._f(p[4]), "c": ep._f(p[5]), "v": ep._f(p[6])}
    return out


def load_minutes(paths: list[Path]) -> dict[tuple[str, date], list[dict]]:
    by: dict[tuple[str, date], dict] = {}
    for path in paths:
        if not path.exists():
            continue
        op = gzip.open if str(path).endswith(".gz") else open
        with op(path, "rt") as fh:
            for line in fh:
                p = line.rstrip("\n").split("|")
                if len(p) != 7:
                    continue
                try:
                    dt = datetime.strptime(p[1], "%Y-%m-%d %H:%M").replace(tzinfo=_ET)
                    bar = {"m": dt, "o": float(p[2]), "h": float(p[3]), "l": float(p[4]), "c": float(p[5])}
                except ValueError:
                    continue
                by.setdefault((p[0], dt.date()), {})[dt] = bar
    return {k: [v[m] for m in sorted(v)] for k, v in by.items()}


def load_fetch_log(tag: str) -> dict[tuple[str, date], tuple[int, int, str]]:
    out = {}
    p = HERE / f"fetch_log_{tag}.txt"
    if p.exists():
        for line in open(p):
            q = line.rstrip("\n").split("|")
            if len(q) == 5:
                out[(q[0], date.fromisoformat(q[1]))] = (int(q[2]), int(q[3]), q[4])
    return out


# ── the live order path ───────────────────────────────────────────────────────────────

def atr14_live(dbars: dict[date, dict], d: date) -> float | None:
    """filters.compute_atr_14 at 09:31 on day d: rows in [d-35, d-1], Wilder TR, last 14 TRs; None below 10 rows."""
    rows = [dbars[x] for x in sorted(dbars) if d - timedelta(days=35) <= x < d
            and dbars[x]["h"] is not None and dbars[x]["l"] is not None and dbars[x]["c"] is not None]
    if len(rows) < 10:
        return None
    trs = [max(r["h"] - r["l"], abs(r["h"] - p["c"]), abs(r["l"] - p["c"])) for p, r in zip(rows, rows[1:])]
    w = trs[-14:]
    return sum(w) / len(w) if w else None


def live_entry(bars0: list[dict], H: float, L: float, px_mode: str = "open", submit: time = SUBMIT) -> dict:
    """order_manager.submit_entry as pre-registered. Returns status + fill (px, minute, fill_at_open, kind)."""
    stop = 2 * L - H
    b0 = next((b for b in bars0 if b["m"].time() >= submit), None)
    if b0 is None:
        return {"status": "abstain", "reason": "no_submit_bar"}
    if px_mode == "prevclose":
        prev = [b for b in bars0 if b["m"] < b0["m"]]
        px = prev[-1]["c"] if prev else b0["o"]
    else:
        px = b0["o"]
    if px > H:
        limit = round(px * 1.002, 2)
        planned = H - stop
        if not (planned > 0 and limit - stop <= CHASE_RISK_INFLATION_CAP * planned):
            return {"status": "chase_cap_skip", "reason": f"chase_cap:{(px - H) / (H - L):.2f}orb_above_H"}
        if b0["l"] <= limit:
            return {"status": "filled", "px": min(b0["o"], limit), "minute": b0["m"], "fill_at_open": True, "kind": "chase_open"}
        for b in bars0:
            if b["m"] <= b0["m"] or b["m"].time() >= CANCEL:
                continue
            if b["l"] <= limit:
                return {"status": "filled", "px": limit, "minute": b["m"], "fill_at_open": False, "kind": "chase_limit_later"}
        return {"status": "no_entry", "reason": "limit_not_reached"}
    f = ep.entry_walk(bars0, H, submit, CANCEL)
    if f["status"] == "filled":
        limit = stop_limit_buy_price(H)
        kind = "cross" if abs(f["px"] - H) < 1e-9 else ("limit_pullback" if abs(f["px"] - limit) < 1e-9 else "open_in_band")
        return {"status": "filled", "px": f["px"], "minute": f["minute"], "fill_at_open": kind == "open_in_band", "kind": kind}
    return {"status": f["status"], "reason": f["reason"]}


# ── day 0 ─────────────────────────────────────────────────────────────────────────────

def day0_from_fill(ticker: str, d: date, bars0: list[dict], H: float, L: float, fill: dict, daily: dict) -> tuple[dict | None, str]:
    """Walk day 0 with ep._walk_leg (era_d) pinned to the entry day, then read the state with study.day0_state.
    Returns (state or None, reason)."""
    entry_px, stop = fill["px"], 2 * L - H
    if entry_px - stop <= 0:
        return None, "nonpositive_risk_per_share"
    dbars = daily.get(ticker, {})
    adr_pct, adr_n = ep.adr20_pct(dbars, d)
    adr_dollar = adr_pct * H if adr_pct else None
    r_ps = profit_target_r_per_share("magna53", entry_px, stop, L)
    if r_ps is None:
        return None, "no_orb_r_frame"
    target = entry_px + RS_D.intraday_partial_r * r_ps
    fill_idx = next(i for i, b in enumerate(bars0) if b["m"] == fill["minute"])
    saved = ep.LAST_SETTLED
    ep.LAST_SETTLED = d
    try:
        leg = ep._walk_leg(ticker=ticker, leg_date=d, entry_px=entry_px, stop=stop, target=target, bars=bars0,
                           fill_idx=fill_idx, rs=RS_D, daily=daily, shares=None, integer_shares=False,
                           adr_dollar=adr_dollar, minutes_extra={}, fill_at_open=fill.get("fill_at_open", False),
                           r_frame_ps=r_ps)
    finally:
        ep.LAST_SETTLED = saved
    h = {"entered": True, "status": leg["status"], "reason": leg["reason"], "entry_px": entry_px, "stop": stop,
         "target": target, "alert_date": d, "exits": leg["exits"], "orb_low": L, "orb_high": H,
         "fill_minute": fill["minute"], "adr_pct": adr_pct, "realized_r": leg["realized_r"], "gap_through": leg["gap_through"]}
    st = ST.day0_state(h, bars0, RS_D)
    if st is None:
        return None, f"day0:{str(leg['reason']).split(':')[0]}"
    st["h"] = h
    return st, "ok"


# ── the forward walks ──────────────────────────────────────────────────────────────────

def walk_trail_arm(arm: str, ticker: str, d: date, st: dict, daily: dict, held: dict, horizon: date = HORIZON) -> dict:
    ST.ADR_MULT = 1.0
    return ST.walk_hybrid_arm(ticker=ticker, alert_date=d, st=st, arm=ARM_DEFS[arm], daily=daily, held=held,
                              horizon=horizon, mincov={})


def _exit_day(e) -> date:
    return date.fromisoformat(str(e["time"])[:10])


def walk_runner(rule: str, floor_mode: str, r0: dict, ticker: str, d: date, st: dict, daily: dict, held: dict) -> dict:
    """The runner arm: A0 until the partial fires on day P, then T20 / S20 with the declared floor."""
    exits0 = r0["exits"]
    partial = next((e for e in exits0 if e["reason"] == "partial_profit"), None)
    if r0["status"] not in ("settled", "open_at_horizon") or partial is None:
        out = dict(r0)
        out["runner_engaged"] = False
        return out
    P = _exit_day(partial)
    entry, hard = st["entry"], st["hard"]
    floor = entry if floor_mode == "be" else hard
    # keep every exit up to and including the partial (A0's own path until then)
    kept = []
    for e in exits0:
        kept.append(dict(e))
        if e is partial:
            break
    remaining = st["shares"] - sum(e["shares"] for e in kept)
    risk_denom = st["shares"] * (entry - hard)
    out = {"arm": f"{rule}_{floor_mode}", "status": None, "exits": kept, "final_reason": None, "realized_r": None,
           "mark_r": None, "exit_day": None, "gap_through": False, "runner_engaged": True, "partial_day": P,
           "post_sessions": 0, "held_sessions": r0.get("held_sessions", 0), "line_tests": [], "unreadable": False,
           "delisted_forced_close": False, "last_close": None}
    dbars = daily.get(ticker, {})

    def book(px, qty, reason, when):
        kept.append({"time": str(when), "price": px, "reason": reason, "shares": qty, "pnl": (px - entry) * qty})

    closed = False
    # day P after the partial minute: walk the remaining bars against the floor if bars exist
    pm = None
    if "T" in str(partial["time"]) or " " in str(partial["time"]):
        try:
            pm = datetime.fromisoformat(str(partial["time"]))
        except ValueError:
            pm = None
    if pm is not None and (ticker, P) in held:
        for b in held[(ticker, P)]:
            if b["m"] <= pm:
                continue
            if b["l"] <= floor:
                px = b["o"] if b["o"] < floor else floor
                out["gap_through"] = px != floor
                book(px, remaining, "stop_hit", b["m"])
                remaining = 0.0
                out.update(final_reason="stop_hit", exit_day=P)
                closed = True
                break
    last_close = dbars[P]["c"] if P in dbars and dbars[P]["c"] is not None else None
    dd = P
    last_bar_day = max(dbars) if dbars else None
    while not closed:
        dd += timedelta(days=1)
        if dd > HORIZON:
            out["status"] = "open_at_horizon"
            break
        if dd.weekday() >= 5:
            continue
        b = dbars.get(dd)
        if not b or b["c"] is None or b["l"] is None or b["h"] is None:
            if last_bar_day is not None and dd > last_bar_day:
                out["status"] = "open_at_horizon"
                out["delisted_forced_close"] = True
                break
            continue
        last_close = b["c"]
        out["post_sessions"] += 1
        if b["l"] <= floor:
            px = b["o"] if (b["o"] is not None and b["o"] < floor) else floor
            out["gap_through"] = px != floor
            book(px, remaining, "stop_hit", dd)
            remaining = 0.0
            out.update(final_reason="stop_hit", exit_day=dd)
            closed = True
            break
        exit_now = None
        if rule == "T20" and out["post_sessions"] >= 20:
            exit_now = "time_close"
        elif rule == "S20":
            closes = [dbars[x]["c"] for x in sorted(dbars) if x <= dd and dbars[x]["c"] is not None]
            if len(closes) >= 20 and b["c"] < sum(closes[-20:]) / 20:
                exit_now = "sma20_close"
        if exit_now:
            book(b["c"], remaining, exit_now, dd)
            remaining = 0.0
            out.update(final_reason=exit_now, exit_day=dd)
            closed = True
            break
    out["exits"] = kept
    out["last_close"] = last_close
    pnl = sum(e["pnl"] for e in kept)
    if closed:
        out["status"] = "settled"
        out["realized_r"] = pnl / risk_denom
    else:
        lc = last_close if last_close is not None else entry
        out["mark_r"] = (pnl + (lc - entry) * remaining) / risk_denom
    return out


def force_close_delisted(r: dict, ticker: str, daily: dict) -> dict:
    """A ticker whose daily bars end before the horizon: settle every arm at its last close (the mark)."""
    if r["status"] != "open_at_horizon":
        return r
    dbars = daily.get(ticker, {})
    if not dbars:
        return r
    last_bar_day = max(dbars)
    if last_bar_day < HORIZON - timedelta(days=14) and r.get("mark_r") is not None:
        r = dict(r)
        r.update(status="settled", realized_r=r["mark_r"], final_reason="delisted_forced_close",
                 exit_day=last_bar_day, delisted_forced_close=True)
    return r


# ── statistics ────────────────────────────────────────────────────────────────────────

def summarize(P, label, keys, results, base_arm, arms, H, blk_of):
    rows = []
    for blk in ("ALL", "DISC", "HELD"):
        ks = [k for k in keys if blk == "ALL" or blk_of(k) == blk]
        paired = [k for k in ks if all(results[a][k]["status"] == "settled" for a in (base_arm,) + tuple(arms))]
        openh = {a: sum(1 for k in ks if results[a][k]["status"] == "open_at_horizon") for a in (base_arm,) + tuple(arms)}
        abst = {a: sum(1 for k in ks if results[a][k]["status"] == "abstain") for a in (base_arm,) + tuple(arms)}
        forced = sum(1 for k in paired if any(results[a][k].get("delisted_forced_close") for a in (base_arm,) + tuple(arms)))
        P(f"## {label} BLOCK {blk}: campaigns {len(ks)}, paired (settled in every arm) {len(paired)}; open at horizon per arm {openh}; "
          f"abstain per arm {abst}; paired trades with a delisted force-close in any arm {forced}")
        base = {k: results[base_arm][k]["realized_r"] for k in paired}
        for a in (base_arm,) + tuple(arms):
            R = {k: results[a][k]["realized_r"] for k in paired}
            vals = list(R.values())
            diffs = [R[k] - base[k] for k in paired]
            weeks = [f"{k[1].isocalendar()[0]}-W{k[1].isocalendar()[1]:02d}" for k in paired]
            p = ST.block_signflip_p(diffs, weeks, random.Random(SEED * 10 + list(arms).index(a))) if a != base_arm and paired else None
            better = sum(1 for x in diffs if x > 0.005); worse = sum(1 for x in diffs if x < -0.005)
            orb_vals = [R[k] * H[k]["money_per_orb"] for k in paired]
            planned_vals = [R[k] * H[k]["actual_over_planned"] for k in paired]
            win3 = sum(1 for x in orb_vals if x >= 3); win8 = sum(1 for x in orb_vals if x >= 8)
            worst = min(vals) if vals else None
            worst_k = min(paired, key=lambda k: R[k]) if paired else None
            big_loss = sum(1 for x in vals if x < -1.5)
            longer = sum(1 for k in paired if (results[a][k]["exit_day"] or date.max) > (results[base_arm][k]["exit_day"] or date.max)) if a != base_arm else 0
            row = {"table": label, "block": blk, "arm": a, "n": len(paired), "sum": sum(vals), "mean": statistics.mean(vals) if vals else None,
                   "median": statistics.median(vals) if vals else None, "sum_orb": sum(orb_vals), "sum_vs_planned": sum(planned_vals),
                   "dbt": ST.drop_best_two(vals), "diff": sum(diffs), "diff_dbt": ST.drop_best_two(vals) - ST.drop_best_two(list(base.values())),
                   "p": p, "better": better, "worse": worse, "win3": win3, "win8": win8, "worst": worst,
                   "worst_k": f"{worst_k[0]} {worst_k[1]}" if worst_k else "", "big_loss": big_loss, "open": openh[a], "longer": longer}
            rows.append(row)
            P(f"   {a:7s} n={row['n']:4d} total {row['sum']:+8.2f} money-R ({row['sum_orb']:+8.2f} ORB-R; vs planned risk {row['sum_vs_planned']:+8.2f}) "
              f"mean {fmt(row['mean'], 3)} median {fmt(row['median'])} drop-best-2 {row['dbt']:+8.2f} | vs {base_arm} {row['diff']:+7.2f} "
              f"(dbt {row['diff_dbt']:+7.2f}) p={'—' if p is None else f'{p:.3f}'} better/worse {better}/{worse} | >=3ORB-R {win3} >=8ORB-R {win8} | "
              f"worst {fmt(worst)} ({row['worst_k']}) | losses<-1.5R {big_loss} | open@horizon {openh[a]} held-longer {longer}")
    return rows


# ── main ──────────────────────────────────────────────────────────────────────────────

def main():
    log = open(OUT / f"backfill_out{MODE.replace('--', '_')}.txt", "w")

    def P(*a):
        s = " ".join(str(x) for x in a)
        print(s); log.write(s + "\n")

    P(f"# #687 backfill {MODE} run {datetime.now(_ET).isoformat(timespec='seconds')} — a REBUILT EP-like population, not live alerts")

    # ── STEP 2 ANCHOR (runs in --anchor and --final; --pass1 skips it: it computes no population number) ──
    if MODE in ("--anchor", "--final"):
        import depth as DP  # noqa: E402  (the #685 follow-up's own population builder)
        stored, keys79 = DP.load_stored()
        daily685, held685, mincov685, H0m, states, day0_only = DP.build_states()
        # (a) forward half
        bad = []
        tot = {"A0": 0.0, "A1": 0.0}
        for k in sorted(keys79):
            for a in ("A0", "A1"):
                if k in day0_only:
                    r = {"status": "settled", "realized_r": day0_only[k]}
                else:
                    r = walk_trail_arm(a, k[0], k[1], states[k], daily685, held685, horizon=ST.HORIZON)   # #685's own horizon (09-25)
                want = DP.stored_r(stored[k], a)
                if r["status"] != "settled" or abs(r["realized_r"] - want) > 0.005:
                    bad.append(f"{a} {k}: {r['status']} {r.get('realized_r')} vs stored {want}")
                else:
                    tot[a] += r["realized_r"]
        ok_a = (not bad) and abs(tot["A0"] + 5.77) < 0.01 and abs(tot["A1"] + 9.85) < 0.01
        P(f"## ANCHOR (a) forward walk on #685's 79 paired trades: A0 {tot['A0']:+.2f} (expect −5.77) A1 {tot['A1']:+.2f} (expect −9.85); "
          f"per-trade mismatches {len(bad)} -> {'REPRODUCED' if ok_a else 'FAILED — HALT'}")
        for s in bad[:20]:
            P("    ", s)
        # (b) day-0 half: my builder vs study.day0_state on every #685 campaign that reaches day 1 or settles day 0
        bad_b = []; n_b = 0
        day0_bars = ST.load_all()[4]     # the #685 capture's entry-day bars (the same loader depth.py uses)
        for k, h in H0m.items():
            if k not in states and k not in day0_only:
                continue
            bars0 = day0_bars.get(k, [])
            if h.get("fill_minute") is None:
                continue
            n_b += 1
            fill = {"px": h["entry_px"], "minute": h["fill_minute"], "fill_at_open": False}
            st_mine, why = day0_from_fill(k[0], k[1], bars0, h["orb_high"], h["orb_low"], fill, daily685)
            if k in day0_only:
                if st_mine is None or not st_mine["settled_d0"] or abs((st_mine["h"]["realized_r"] or 0) - day0_only[k]) > 0.005:
                    bad_b.append(f"{k}: day0-settled mismatch mine={why if st_mine is None else st_mine['h']['realized_r']} stored={day0_only[k]}")
                continue
            s0 = states[k]
            if st_mine is None:
                bad_b.append(f"{k}: mine None ({why}) vs study state present"); continue
            for f in ("entry", "hard", "remaining", "partial_taken", "be_active", "settled_d0"):
                if abs(float(st_mine[f]) - float(s0[f])) > 1e-6:
                    bad_b.append(f"{k}: {f} mine={st_mine[f]} study={s0[f]}"); break
        ok_b = not bad_b
        P(f"## ANCHOR (b) day-0 state builder vs study.day0_state on {n_b} #685 campaigns: mismatches {len(bad_b)} -> {'REPRODUCED' if ok_b else 'FAILED — HALT'}")
        for s in bad_b[:20]:
            P("    ", s)
        if not (ok_a and ok_b):
            log.close(); raise SystemExit(2)
        # (c) entry half: on the #685 alerts the harness ORDERED (past validate_orb_entry and the 09:45 window, i.e. every
        # status except no_trade), the live order path with the harness's own submit time and the STORED bars vs the
        # harness's entry_walk verdict; then the FEED delta with Polygon's bars on the same days.
        poly = load_minutes(sorted(HERE.glob("minutes_entry*.tsv*")))
        ak = []
        with open(HERE / "anchor_keys.tsv") as fh:
            for r in csv.DictReader(fh, delimiter="|"):
                if r["status"] != "no_trade" and r["orb_high"]:
                    ak.append(r)
        delta = collections.Counter(); cnt_p = collections.Counter(); hl_diff = []; flips = 0; both = 0; feed_flip = []
        for r in ak:
            k = (r["ticker"], date.fromisoformat(r["alert_date"]))
            sub = time(int(r["submit"][:2]), int(r["submit"][3:5]))
            bars_s = day0_bars.get(k, [])
            bars_p = poly.get(k, [])
            orb_s = next((b for b in bars_s if b["m"].time() == time(9, 30)), None)
            orb_p = next((b for b in bars_p if b["m"].time() == time(9, 30)), None)
            if orb_s is None:
                delta["no_930_bar_stored"] += 1; continue
            f = live_entry(bars_s, orb_s["h"], orb_s["l"], submit=sub)
            h_ent = r["entered"] == "True"
            h_px = float(r["entry_px"]) if r["entry_px"] not in ("", "None") else None
            if f["status"] == "filled" and h_ent:
                delta["both_fill:" + ("same_px" if abs(f["px"] - h_px) < 0.01 else f"px_differs:{f['kind']}")] += 1
            elif f["status"] == "filled":
                delta[f"live_fills_harness_{r['status']}:{f['kind']}"] += 1
            elif h_ent:
                delta[f"live_{f['status']}_harness_filled"] += 1
            else:
                delta[f"neither:{f['status']}"] += 1
            if orb_p is not None:
                both += 1
                fp = live_entry(bars_p, orb_p["h"], orb_p["l"], submit=sub)
                cnt_p[fp["status"] + (":" + fp["kind"] if fp["status"] == "filled" else "")] += 1
                dh = orb_p["h"] - orb_s["h"]; dl = orb_p["l"] - orb_s["l"]
                if abs(dh) > 0.005 or abs(dl) > 0.005:
                    hl_diff.append((k, round(dh, 3), round(dl, 3), round(orb_s["h"], 2)))
                if f["status"] != fp["status"] or (f["status"] == "filled" and abs(f["px"] - fp["px"]) > 0.01):
                    flips += 1; feed_flip.append((k, f["status"], f.get("px"), fp["status"], fp.get("px")))
        cov_flips = sum(1 for x in feed_flip if x[1] == "abstain")
        real_flips = [x for x in feed_flip if x[1] != "abstain"]
        P(f"## ANCHOR (c) the live order path vs #685's entry_walk on the {len(ak)} alerts the harness ordered (stored bars, harness submit time): {dict(sorted(delta.items()))}")
        P(f"   FEED: Polygon 09:30 bar vs the stored (SIP-stream) bar on {both} days with both: H or L differ by > $0.005 on {len(hl_diff)}; "
          f"entry verdict/price flips {flips}, of which {cov_flips} are stored-coverage gaps (stored abstain, Polygon readable) and {len(real_flips)} are price/verdict disagreements; "
          f"the live path on Polygon bars gives {dict(sorted(cnt_p.items()))}")
        for x in real_flips[:12]:
            P(f"    REAL flip {x[0][0]} {x[0][1]}: stored {x[1]} {x[2]} vs polygon {x[3]} {x[4]}")
        for x in sorted(hl_diff, key=lambda x: -abs(x[1]) - abs(x[2]))[:12]:
            P(f"    {x[0][0]} {x[0][1]}: dH {x[1]:+.3f} dL {x[2]:+.3f} (stored H {x[3]})")
        if MODE == "--anchor":
            log.close(); return

    # ── the population run (--pass1: daily-only, emits line-test days only; --final: with round-2 bars) ──
    pop = load_population()
    daily = load_daily()
    entry_min = load_minutes(sorted(HERE.glob("minutes_entry*.tsv*")))
    held_min = load_minutes(sorted(HERE.glob("minutes_held*.tsv*"))) if MODE == "--final" else {}
    flog = load_fetch_log("entry")
    P(f"## DATA: population {len(pop)}; entry-day bars for {sum(1 for r in pop if (r['ticker'], r['d']) in entry_min)} of them "
      f"(fetch log rows {len(flog)}, errors {sum(1 for v in flog.values() if v[2] != 'ok')}); held-day bar sets {len(held_min)}")
    # JOIN CHECK (data, not an outcome): Polygon's adjusted minute bars vs mi_daily_closes on the same day — the 09:30
    # bar's open vs the daily open, and the RTH max/min vs the daily high/low; a split ticker is the case that bites.
    jc = collections.Counter(); worst = []
    for r in pop:
        k = (r["ticker"], r["d"])
        bars0 = entry_min.get(k)
        if not bars0 or r["o"] is None or r["h"] is None or r["l"] is None:
            continue
        orb = next((b for b in bars0 if b["m"].time() == time(9, 30)), None)
        if orb is None:
            continue
        rel_o = abs(orb["o"] - r["o"]) / r["o"]
        rel_h = abs(max(b["h"] for b in bars0) - r["h"]) / r["h"]
        rel_l = abs(min(b["l"] for b in bars0) - r["l"]) / r["l"]
        jc["days"] += 1
        jc["open_within_0.5%"] += rel_o <= 0.005
        jc["high_within_1%"] += rel_h <= 0.01
        jc["low_within_1%"] += rel_l <= 0.01
        if r.get("split_factor") not in (None, "", "1.0"):
            jc["split_days"] += 1
            jc["split_days_open_within_0.5%"] += rel_o <= 0.005
        if rel_o > 0.02:
            worst.append((k, round(rel_o * 100, 1), orb["o"], r["o"]))
    bad_join = {x[0] for x in worst}   # a day whose minute bars and daily bar disagree (a split adjusted on one side only) cannot be walked
    P(f"## JOIN CHECK (Polygon adjusted bars vs mi_daily_closes, same day): {dict(jc)}; days with the 09:30 open > 2% off the daily open "
      f"{len(worst)} (worst 5: {sorted(worst, key=lambda x: -x[1])[:5]})")

    def blk_of(k):
        return "DISC" if k[1] <= SPLIT_END_DISC else "HELD"

    # entries
    gate = collections.Counter(); fills = {}; H = {}
    px_flip = 0; px_flip_dir = collections.Counter()
    for r in pop:
        k = (r["ticker"], r["d"])
        bars0 = entry_min.get(k, [])
        orb = next((b for b in bars0 if b["m"].time() == time(9, 30)), None)
        if k in bad_join:
            gate["abstain:join_mismatch_minute_vs_daily"] += 1; continue
        if not bars0:
            gate["abstain:no_entry_day_bars"] += 1; continue
        if orb is None:
            gate["abstain:no_930_bar"] += 1; continue
        Hh, Ll = orb["h"], orb["l"]
        atr = atr14_live(daily.get(r["ticker"], {}), r["d"])
        ok, skip = validate_orb_entry(Hh, Ll, atr)
        if not ok:
            gate["no_trade:" + ":".join(str(skip).split(":")[:2])] += 1; continue
        if 2 * Ll - Hh <= 0:
            gate["no_trade:stop_at_or_below_zero"] += 1; continue
        f = live_entry(bars0, Hh, Ll)
        f2 = live_entry(bars0, Hh, Ll, px_mode="prevclose")
        if f["status"] != f2["status"] or (f["status"] == "filled" and abs(f["px"] - f2.get("px", 0)) > 0.01):
            px_flip += 1
            px_flip_dir[f"{f['status']}->{f2['status']}" if f["status"] != f2["status"] else ("px_lower_under_close_proxy" if f2["px"] < f["px"] else "px_higher_under_close_proxy")] += 1
        if f["status"] != "filled":
            gate[f["status"] + ":" + str(f.get("reason", "")).split(":")[0]] += 1; continue
        gate["filled:" + f["kind"]] += 1
        fills[k] = (f, Hh, Ll, atr)
    P(f"## ENTRY (the live order path, submit 09:31, cancel 10:00): {dict(sorted(gate.items()))}; filled {len(fills)} of {len(pop)}; "
      f"entries whose verdict/price flips under the 09:30-close proxy for the latest trade: {px_flip} ({dict(px_flip_dir)})")
    # day 0
    d0_excl = collections.Counter(); states = {}; day0_only = {}
    for k, (f, Hh, Ll, atr) in fills.items():
        st, why = day0_from_fill(k[0], k[1], entry_min[k], Hh, Ll, f, daily)
        if st is None:
            d0_excl[why] += 1; continue
        H[k] = {"entry": st["entry"], "hard": st["hard"], "orb_high": Hh, "orb_low": Ll, "kind": f["kind"],
                "money_per_orb": (st["entry"] - st["hard"]) / (st["entry"] - Ll),
                "actual_over_planned": (st["entry"] - st["hard"]) / (Hh - (2 * Ll - Hh)), "adr_pct": st["adr_pct"]}
        if st["settled_d0"]:
            day0_only[k] = st["h"]["realized_r"]
        else:
            states[k] = st
    P(f"## DAY 0: walked {len(fills)}; excluded {dict(d0_excl)}; settled on day 0 (identical in every arm) {len(day0_only)}; reached day 1 {len(states)}; "
      f"chase fills among those reaching day 1 {sum(1 for k in states if H[k]['kind'].startswith('chase'))}; no ADR (D10 unhostable) {sum(1 for k in states if not states[k]['adr_pct'])}")

    results: dict[str, dict] = {a: {} for a in MAIN_ARMS + RUNNER_ARMS}
    for k, r0 in day0_only.items():
        for a in results:
            results[a][k] = {"arm": a, "status": "settled", "realized_r": r0, "mark_r": None, "exits": [], "final_reason": "stop_hit",
                             "exit_day": k[1], "line_tests": [], "held_sessions": 0, "gap_through": False, "day0_settled": True,
                             "delisted_forced_close": False, "runner_engaged": False}
    for k, st in states.items():
        if not st["adr_pct"]:
            continue   # dropped from every pairing (counted above): D10 cannot be defined without an ADR
        for a in MAIN_ARMS:
            r = walk_trail_arm(a, k[0], k[1], st, daily, held_min)
            r["day0_settled"] = False
            results[a][k] = force_close_delisted(r, k[0], daily)
        r0 = results["A0"][k]
        for a in RUNNER_ARMS:
            rule, fm = a.split("_")
            rr = walk_runner(rule, fm, r0, k[0], k[1], st, daily, held_min)
            results[a][k] = force_close_delisted(rr, k[0], daily)

    keys = sorted(set(results["A0"]), key=lambda k: (k[1], k[0]))
    # line tests on the A1 path (+ the union over arms for the round-2 list)
    lt_union = set()
    for a in MAIN_ARMS:
        for k, r in results[a].items():
            for x in r.get("line_tests", []):
                lt_union.add((k[0], x["day"]))
    if MODE == "--pass1":
        missing = sorted(x for x in lt_union if x not in held_min)
        with open(HERE / "fetch_list_held.txt", "w") as fh:
            fh.write("\n".join(f"{t}|{d}" for t, d in sorted(missing, key=lambda x: (x[1], x[0]))) + "\n")
        P(f"## PASS 1 (daily-only; NO totals read): line-test days (union over A0/A1/D10) {len(lt_union)} on "
          f"{len({t for t, _ in lt_union})} trades; to fetch {len(missing)} -> fetch_list_held.txt")
        log.close(); return

    missing = sorted(x for x in lt_union if x not in held_min)
    P(f"## ROUND-2 COVERAGE: line-test days {len(lt_union)}; with minute bars {len(lt_union) - len(missing)}; without {len(missing)} "
      f"(walked on the daily bar: A0/A1/D10 are resting-stop / close rules, exact at daily grain except same-day ordering)")
    if missing:
        with open(HERE / "fetch_list_held2.txt", "w") as fh:
            fh.write("\n".join(f"{t}|{d}" for t, d in sorted(missing, key=lambda x: (x[1], x[0]))) + "\n")

    lt = []
    for k, r in results["A1"].items():
        adr = states[k]["adr_pct"] if k in states else None
        for x in r.get("line_tests", []):
            depth_d = x["line"] - x["low"]
            row = {"ticker": k[0], "entry_day": k[1].isoformat(), "block": blk_of(k), "day": x["day"].isoformat(), "line": x["line"],
                   "open": x["open"], "low": x["low"], "close": x["close"], "depth_$": round(depth_d, 4),
                   "depth_adr": round(depth_d / (adr * x["line"]), 3) if adr else None, "depth_pct": round(depth_d / x["line"] * 100, 2),
                   "cls": x["cls"], "n_bars": x["n_bars"]}
            for a in MAIN_ARMS:
                ra = results[a][k]; ed = ra["exit_day"]
                row[f"{a}_action"] = ra["final_reason"] if ed == x["day"] else ("exited_earlier" if (ed is not None and ed < x["day"]) else "HELD")
            lt.append(row)
    lt.sort(key=lambda r: (r["entry_day"], r["ticker"], r["day"]))
    with open(OUT / "line_tests.tsv", "w") as fh:
        cols = list(lt[0].keys()) if lt else []
        fh.write("|".join(cols) + "\n")
        for r in lt:
            fh.write("|".join("" if r[c] is None else str(r[c]) for c in cols) + "\n")
    for blk in ("ALL", "DISC", "HELD"):
        L_ = [r for r in lt if blk == "ALL" or r["block"] == blk]
        rec = [r for r in L_ if r["cls"] == "RECLAIM"]; sl = [r for r in L_ if r["cls"] == "SLICE"]
        deep = [r for r in L_ if r["depth_adr"] is not None and r["depth_adr"] >= 1.0]
        P(f"## LINE TESTS {blk} (A1 hold-through path): {len(L_)} days on {len({(r['ticker'], r['entry_day']) for r in L_})} trades; "
          f"RECLAIM {len(rec)} / SLICE {len(sl)}; with minute bars {sum(1 for r in L_ if r['n_bars'] > 0)}; "
          f"days >= 1.0 ADR below the line {len(deep)} (of which closed back above {sum(1 for r in deep if r['cls'] == 'RECLAIM')}); "
          f"D10 sold on a RECLAIM day {sum(1 for r in rec if r['D10_action'] == 'stop_hit')} of {len(rec)}; "
          f"A0 sold on a RECLAIM day {sum(1 for r in rec if r['A0_action'] == 'stop_hit')} of {len(rec)}; "
          f"median depth on SLICE days {fmt(statistics.median(r['depth_adr'] for r in sl if r['depth_adr'] is not None), 2) if sl else '—'} ADR, "
          f"on RECLAIM days {fmt(statistics.median(r['depth_adr'] for r in rec if r['depth_adr'] is not None), 2) if rec else '—'} ADR")

    # per-trade table
    with open(OUT / "arms_per_trade.tsv", "w") as fh:
        cols = ["ticker", "entry_day", "block", "kind", "entry", "hard", "orb_high", "orb_low", "adr_pct"] + \
               [f"{a}_{c}" for a in MAIN_ARMS + RUNNER_ARMS for c in ("status", "R", "markR", "final", "exit_day")]
        fh.write("|".join(cols) + "\n")
        for k in keys:
            h = H[k]
            row = [k[0], k[1].isoformat(), blk_of(k), h["kind"], f"{h['entry']:.4f}", f"{h['hard']:.4f}", f"{h['orb_high']:.4f}", f"{h['orb_low']:.4f}",
                   "" if not h["adr_pct"] else f"{h['adr_pct']:.4f}"]
            for a in MAIN_ARMS + RUNNER_ARMS:
                r = results[a][k]
                row += [r["status"], "" if r["realized_r"] is None else f"{r['realized_r']:.4f}", "" if r["mark_r"] is None else f"{r['mark_r']:.4f}",
                        str(r["final_reason"]), str(r["exit_day"])]
            fh.write("|".join(row) + "\n")

    # measures
    summary = summarize(P, "MAIN", keys, results, "A0", ("A1", "D10"), H, blk_of)
    engaged = [k for k in keys if results["T20_be"][k].get("runner_engaged")]
    P(f"## RUNNER-EXIT: trades where the +8 ORB-R partial fired (the rule engages) {len(engaged)} of {len(keys)} "
      f"(DISC {sum(1 for k in engaged if blk_of(k) == 'DISC')} / HELD {sum(1 for k in engaged if blk_of(k) == 'HELD')}); every other trade is A0 in every runner arm")
    summary += summarize(P, "RUNNER_ENGAGED", engaged, results, "A0", RUNNER_ARMS, H, blk_of)
    summary += summarize(P, "RUNNER_ALL", keys, results, "A0", RUNNER_ARMS, H, blk_of)
    with open(OUT / "arms_summary.tsv", "w") as fh:
        cols = list(summary[0].keys())
        fh.write("|".join(cols) + "\n")
        for r in summary:
            fh.write("|".join("" if r[c] is None else str(r[c]) for c in cols) + "\n")

    # where the arms differ
    P("## PER-TRADE (paired ALL): the trades where A1 or D10 differs from A0 by > 0.005R (largest 40 by |D10 − A0|)")
    diffs = []
    for k in keys:
        if all(results[a][k]["status"] == "settled" for a in MAIN_ARMS):
            r0 = results["A0"][k]["realized_r"]
            if any(abs(results[a][k]["realized_r"] - r0) > 0.005 for a in ("A1", "D10")):
                diffs.append(k)
    P(f"   differing trades {len(diffs)}")
    for k in sorted(diffs, key=lambda k: -abs(results["D10"][k]["realized_r"] - results["A0"][k]["realized_r"]))[:40]:
        P(f"    {k[0]:6s} {k[1]} {blk_of(k)} " + " ".join(f"{a}:{results[a][k]['realized_r']:+.2f}({str(results[a][k]['final_reason'])[:14]},{results[a][k]['exit_day']})" for a in MAIN_ARMS))
    json.dump({a: {f"{k[0]}|{k[1]}": {kk: (str(v) if not isinstance(v, (int, float, bool, type(None), list, dict)) else v)
                                        for kk, v in r.items() if kk not in ("exits",)}
                   for k, r in results[a].items()} for a in results},
              open(OUT / "arms_results.json", "w"), default=str, indent=0)
    log.close()


if __name__ == "__main__":
    main()
