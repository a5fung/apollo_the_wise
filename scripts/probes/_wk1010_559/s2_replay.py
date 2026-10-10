"""#559 era-D re-cut — step 2: replay every population from STORED bars under the CURRENT exit
stack (ep_replay RULESETS['current'] = era D: entry−2R stop, +8R partial, breakeven armed at
+3R, max(SMA10,SMA20) trail), plus the real era-D trade rows, the +8R firings, the entry-gate
blocks and the tail. $0, no network, no DB: reads c1_scope.out + c2_bars.out only.

R FRAMES (stated once, used everywhere):
  stop-R  = pnl / (shares × (entry − placed stop)). Every "mean R" below is stop-R.
            REAL trades: the placed stop is mi_live_trades.hard_stop (the stop at entry).
            `stop_price` is the LIVE, TRAILED stop for names that armed breakeven or trailed
            (SEI 64.95, VICR 292.83, KOD 88.25 vs hard_stop 57.82 / 201.13 / 58.08), so it is
            NOT the placed stop. ⚠ `risk_dollars` is NOT shares × (entry − placed stop): it is the
            sizing-time plan and differs from it (PHVS: planned 12.35 vs 3 × (42 − 38.5) = 10.50;
            VICR: 12.26 vs 10.37). The first cut of this script divided by risk_dollars and
            called that stop-R; it is a different R (it read PHVS/DFTX/CEG as −0.87/−0.97/−0.76
            and VICR as +6.18; stop-R is −1.02/−1.01/−1.00 and +7.30). Corrected 2026-10-10.
            REPLAYS: the replay's own entry and stop (`realized_r` / `mark_r`).
  ORB-R   = (price − entry) / (entry − orb_low) — the frame the +8R partial and +3R breakeven are
            set in (order_manager.profit_target_r_per_share). Tail counts are given in BOTH.
FATE (live scan) is classified by mi_ep_scan_log.reject_stage, never by filter_reason text:
  gap_floor            -> the real-time cross never held at a scan tick (floor only)
  quality_filter / cooldown / extension / rvol_gate / shortlist_cap
                       -> turned away BEFORE the grade (mechanical)
  score_bar / post_grade_filter / duplicate / ''
                       -> reached the grade (post_grade_filter covers 'M&A/buyout', 'pre-mkt
                          volume', 'routine catalyst'; duplicate = scored earlier the same day)
  a row in mi_ep_alerts -> alerted
MFE (tail) is bounded to the exit: highs after the final exit do not count.
Run: python3 scripts/probes/_wk1010_559/s2_replay.py > scripts/probes/_wk1010_559/s2_replay_out.txt
"""
from __future__ import annotations

import os
import re
import sys
from collections import Counter, defaultdict
from datetime import date, datetime, time, timedelta

P = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.abspath(os.path.join(P, "..", "..", ".."))
sys.path.insert(0, REPO)
sys.path.insert(0, P)

from readcap import read_sections, f  # noqa: E402
import scripts.ep_replay as ep  # noqa: E402
from agents.market_intelligence.rule_eras import exit_era_label, admission_era_as_of  # noqa: E402

# The harness pins its own capture's last settled day (2026-08-31). Ours ends 2026-10-09 (Fri),
# the last settled session before Monday's depth-exit go-live. Override, never edit the harness.
LAST_SETTLED = date(2026, 10, 9)
ep.LAST_SETTLED = LAST_SETTLED
RS = ep.RULESETS["current"]
WIN_START, WIN_END = date(2026, 9, 8), date(2026, 10, 9)
FLOOR = 9.0
CLS = ["ep_rt_universe_catch", "ep_rt_floor_flip_up", "ep_rt_admit", "ep_rt_live_miss"]
ET = ep._ET

S1 = read_sections("c1_scope.out")
S2 = read_sections("c2_bars.out")


def D(s):
    return date.fromisoformat(s)


# ── bars ─────────────────────────────────────────────────────────────────────────────
minutes: dict[tuple[str, date], list[dict]] = defaultdict(list)
for r in S2["MIN"]:
    dt = datetime.strptime(r["et_min"], "%Y-%m-%d %H:%M").replace(tzinfo=ET)
    minutes[(r["ticker"], dt.date())].append(
        {"m": dt, "o": f(r["open"]), "h": f(r["high"]), "l": f(r["low"]), "c": f(r["close"])})
for v in minutes.values():
    v.sort(key=lambda b: b["m"])
daily: dict[str, dict[date, dict]] = defaultdict(dict)
for r in S2["DAILY"]:
    daily[r["ticker"]][D(r["trade_date"])] = {"o": f(r["open_price"]), "h": f(r["high_price"]),
                                             "l": f(r["low_price"]), "c": f(r["close"]),
                                             "v": f(r["volume"])}
print(f"bars loaded: minute pairs {len(minutes)}, daily tickers {len(daily)}, "
      f"last settled {LAST_SETTLED}, rule-set {RS.name} "
      f"(stop {RS.stop_mode}, partial +{RS.intraday_partial_r:.0f}R, breakeven +{RS.breakeven_at_r:.0f}R, "
      f"trail {RS.trail_mode})")


# ── populations ──────────────────────────────────────────────────────────────────────
def win(t: str) -> str:
    """Class of a ticker-day by the time of its first real-time >=9% read. The 09:30 tick is
    FOLDED INTO the in-window class (it can only be entered from 09:31, exactly like 09:31-09:44).
    The first cut sent it to a '0930' bucket that no table read, so 5 ticker-days (TANH 09-11,
    OESX 09-15, PUBM 09-17, CADL 09-21, BETR 10-02) fell out of every class (424 = 255 + 70 + 94 + 5)."""
    if "09:30" <= t <= "09:44":
        return "inwin"
    return "preopen" if t < "09:30" else "late"


first: dict[tuple, dict] = {}
for r in S1["EVENTS"]:
    if r["event_type"] not in CLS:
        continue
    k = (r["d"], r["ticker"])
    if k not in first or r["tick_et"] < first[k]["tick_et"]:
        first[k] = r
alerts = {(r["alert_date"], r["ticker"]): r for r in S1["ALERTS"]}
trades = S1["TRADES"]
sl = defaultdict(list)
for r in S1["SCANLOG"]:
    sl[(r["scan_date"], r["ticker"])].append(r)

PRE_GRADE = {"quality_filter", "cooldown", "extension", "rvol_gate", "shortlist_cap"}
GRADE = {"score_bar", "post_grade_filter", "duplicate", ""}
MECH = ("quality filter", "EP cooldown", "M&A/buyout", "already up", "pre-mkt volume", "outside top-")


def fate_old(k) -> str:
    """FIRST-CUT classifier (filter_reason text), kept ONLY to print which names flipped.
    It counted 'M&A/buyout' and 'pre-mkt volume' as mechanical kills, but mi_ep_scan_log stamps
    both reject_stage = post_grade_filter (they are applied AFTER the grade), and it let
    'filter:pm_rvol_too_low' / 'filter:session_rvol_too_low' (reject_stage rvol_gate) fall
    through to 'floor_only'."""
    if k in alerts:
        return "alerted"
    rows = sl.get(k, [])
    rs = [(r["filter_reason"] or "").strip() for r in rows]
    if any(r.startswith("score ") or r.startswith("routine catalyst") or r == ""
           or r.startswith("already scored") for r in rs):
        return "graded_below_bar"
    if any(any(r.startswith(m) for m in MECH) for r in rs):
        return "mechanical_kill"
    return "floor_only" if rows else "no_scan_row"


def fate(k) -> str:
    """The live scan's recorded fate for a ticker-day, from mi_ep_scan_log.reject_stage — the
    furthest stage any of its rows reached. 'alerted' (a mi_ep_alerts row) > 'graded_below_bar'
    (reached the LLM grade: reject_stage score_bar / post_grade_filter / duplicate-of-a-scored-
    name) > 'mechanical_kill' (turned away BEFORE the grade: quality_filter / cooldown /
    extension / rvol_gate / shortlist_cap) > 'floor_only' (every row is gap_floor: the real-time
    floor cross never held at a scan tick)."""
    if k in alerts:
        return "alerted"
    rows = sl.get(k, [])
    stages = {r["reject_stage"] for r in rows}
    unknown = stages - GRADE - PRE_GRADE - {"gap_floor"}
    assert not unknown, f"unclassified reject_stage {unknown} for {k}"
    if stages & GRADE:
        return "graded_below_bar"
    if stages & PRE_GRADE:
        return "mechanical_kill"
    return "floor_only" if rows else "no_scan_row"


# era check on every row we will quote (both axes)
eras = Counter((exit_era_label(D(d), "magna53"), admission_era_as_of(D(d))) for d, _ in first)
print("rule eras over the event population (exit, admission):", dict(eras))
sig = Counter((t["signal_type"], t["account_mode"]) for t in trades)
print("trade rows by (signal_type, account_mode):", dict(sig))


# ── replay helpers ───────────────────────────────────────────────────────────────────
def exit_bound(res: dict):
    """(cut_minute, until_date) bounding the MFE window to the EXIT. An open campaign runs to the
    last settled session. A settled one stops at its FINAL exit: a day-0 exit carries a minute
    timestamp (bars after it are dropped), a forward-day exit carries a date (daily highs through
    that session). The first cut let a day-0 stop-out keep counting the rest of the day's highs,
    and a forward stop-out keep counting highs after the exit."""
    if res["status"] != "settled" or not res["exits"]:
        return None, LAST_SETTLED
    t = res["exits"][-1]["time"]
    if len(t) > 10:
        cut = datetime.fromisoformat(t)
        if cut.tzinfo is not None:      # a day-0 minute-walk exit: str(aware minute bar)
            return cut, cut.date()
        return None, cut.date()          # a forward-day EOD stamp (naive T16:00:00)
    return None, date.fromisoformat(t)


def mfe_orb_r(ticker: str, d: date, entry: float, orb_low: float, fill_minute, cut, until: date):
    """Max favourable excursion in ORB-R from the fill minute (day-0 bars after the fill, up to the
    exit minute `cut` when the exit was on day 0) plus forward daily highs through `until`."""
    r_orb = entry - orb_low
    if r_orb <= 0:
        return None
    hi = entry
    for b in minutes.get((ticker, d), []):
        if fill_minute is not None and b["m"] < fill_minute:
            continue            # the FILL bar's own high counts: a stop-buy fills at/after the cross
        if cut is not None and b["m"] > cut:
            continue            # bars after the day-0 exit minute do not
        hi = max(hi, b["h"])
    dd = d
    while dd < until:
        dd += timedelta(days=1)
        b = daily.get(ticker, {}).get(dd)
        if b and b["h"] is not None:
            hi = max(hi, b["h"])
    return (hi - entry) / r_orb


def replay(ticker: str, d: date, submit: time, *, orb_high=None, orb_low=None, atr=None,
           shares=None) -> dict:
    dbars = daily.get(ticker, {})
    if atr is None:
        atr = ep.atr14_abs(dbars, d)
    res = ep.walk_campaign(ticker=ticker, alert_date=d, rs=RS, minutes=minutes, daily=daily,
                           submit=submit, orb_high=orb_high, orb_low=orb_low, atr_14=atr,
                           shares=shares, integer_shares=shares is not None)
    res["atr_used"] = atr
    # ORB low for the ORB-R frame: from the stored row when given, else the 09:30 bar
    ol = orb_low
    if ol is None:
        orb = next((b for b in minutes.get((ticker, d), []) if b["m"].time() == time(9, 30)), None)
        ol = orb["l"] if orb else None
    res["mfe_orb_r"] = None
    if res["entered"] and ol is not None:
        fill_min = None
        try:
            # entry_walk's fill minute is not returned by walk_campaign; recover it from exits
            # when settled on day 0 is not needed — use the first bar >= submit with h >= orb_high
            bars = [b for b in minutes.get((ticker, d), []) if b["m"].time() >= submit]
            oh = orb_high if orb_high is not None else next(
                b for b in minutes[(ticker, d)] if b["m"].time() == time(9, 30))["h"]
            fill_min = next((b["m"] for b in bars if b["h"] >= oh), None)
        except StopIteration:
            fill_min = None
        cut, until = exit_bound(res)
        res["mfe_orb_r"] = mfe_orb_r(ticker, d, res["entry_px"], ol, fill_min, cut, until)
        res["r_orb_per_stop_r"] = (res["entry_px"] - res["stop"]) / (res["entry_px"] - ol) if ol else None
    return res


def summarize(label: str, rows: list[dict]) -> dict:
    n = len(rows)
    ent = [r for r in rows if r["entered"]]
    settled = [r for r in ent if r["status"] == "settled"]
    openh = [r for r in ent if r["status"] == "open_at_horizon"]
    abst = [r for r in rows if r["status"] == "abstain"]
    noent = [r for r in rows if r["status"] == "no_entry"]
    notrade = [r for r in rows if r["status"] == "no_trade"]
    rs = [r["realized_r"] for r in settled]
    marks = [r["mark_r"] for r in openh if r["mark_r"] is not None]
    mean = sum(rs) / len(rs) if rs else None
    win_n = sum(1 for x in rs if x > 0)
    day0_stop = sum(1 for r in settled if r["final_reason"] == "stop_hit" and r["exits"]
                    and r["exits"][-1]["time"][:10] == str(r["alert_date"]))
    partial = sum(1 for r in ent if r["partial_fired"])
    t3 = sum(1 for r in ent if (r.get("mfe_orb_r") or 0) >= 3)
    t8 = sum(1 for r in ent if (r.get("mfe_orb_r") or 0) >= 8)
    # stop-R tail: ORB-R / (stop distance in ORB-R units)
    t3s = sum(1 for r in ent if r.get("r_orb_per_stop_r") and (r.get("mfe_orb_r") or 0) / r["r_orb_per_stop_r"] >= 3)
    t8s = sum(1 for r in ent if r.get("r_orb_per_stop_r") and (r.get("mfe_orb_r") or 0) / r["r_orb_per_stop_r"] >= 8)
    out = dict(label=label, n=n, entered=len(ent), settled=len(settled), open=len(openh),
               abstain=len(abst), no_entry=len(noent), no_trade=len(notrade),
               mean_r=mean, sum_r=sum(rs) if rs else None, winners=win_n, day0_stop=day0_stop,
               partial_8r=partial, tail3_orb=t3, tail8_orb=t8, tail3_stop=t3s, tail8_stop=t8s,
               marks=marks)
    print(f"\n[{label}] n={n}: entered {len(ent)} (settled {len(settled)}, open {len(openh)}), "
          f"no-entry {len(noent)}, not-tradeable {len(notrade)}, abstain {len(abst)}")
    if rs:
        print(f"   settled mean {mean:+.2f} stop-R over n={len(rs)} (sum {sum(rs):+.1f}R; "
              f"{win_n} winners; {day0_stop} stopped day-0)")
        if len(rs) > 1:
            print(f"   without the single best settled trade ({max(rs):+.2f}): "
                  f"{(sum(rs) - max(rs)) / (len(rs) - 1):+.2f} over n={len(rs) - 1} (sum {sum(rs) - max(rs):+.1f}R)")
    if marks:
        print(f"   open marks (not returns): {[round(m, 2) for m in marks]}")
    print(f"   +8R partial fired: {partial} of {len(ent)} entered | tail reached: "
          f">=3 ORB-R {t3}, >=8 ORB-R {t8} | >=3 stop-R {t3s}, >=8 stop-R {t8s}")
    for st_, lab_ in (("no_entry", "no entry"), ("no_trade", "not tradeable"), ("abstain", "abstain")):
        rs_ = Counter(":".join((r["reason"] or "").split(":")[:2 if (r["reason"] or "").startswith("setup") else 1])
                       for r in rows if r["status"] == st_)
        if rs_:
            print(f"   {lab_} ({sum(rs_.values())}):", dict(rs_.most_common()))
    return out


def tick_submit(t: str) -> time:
    hh, mm = int(t[:2]), int(t[3:5])
    return max(time(9, 31), time(hh, mm))


# ── (V) VALIDATE: the real era-D trades, replayed with their own stored ORB/ATR/shares ──
print("\n" + "=" * 90)
print("V. VALIDATE — real magna53 live trades in the window, replayed under `current` with the")
print("   stored ORB / ATR / shares (harness contract: no quoted number without this)")
print("=" * 90)
real = []
for t in trades:
    if t["signal_type"] != "magna53" or t["account_mode"] != "live":
        continue
    d = D(t["alert_date"])
    al = alerts.get((t["alert_date"], t["ticker"]))
    submit = time(9, 31)
    if al and al["detected_et"] >= "09:31:00":
        submit = tick_submit(al["detected_et"])
    if not f(t["orb_high"]):
        real.append({**t, "_rep": None, "_submit": submit})
        continue
    res = replay(t["ticker"], d, submit, orb_high=f(t["orb_high"]), orb_low=f(t["orb_low"]),
                 atr=f(t["atr_14"]), shares=f(t["entry_shares"]))
    real.append({**t, "_rep": res, "_submit": submit})


def live_risk(t) -> float | None:
    """Dollars at risk at the PLACED stop: shares × (entry − hard_stop). `hard_stop` is the stop
    the position was opened with; `stop_price` is the trailed live stop and `risk_dollars` the
    sizing-time plan — neither is this (see the docstring)."""
    sh, e, hs = f(t["entry_shares"]), f(t["entry_price"]), f(t["hard_stop"])
    return sh * (e - hs) if (sh and e and hs) else None


def live_stop_r(t) -> float | None:
    """stop-R of a CLOSED real trade."""
    rk = live_risk(t)
    return f(t["total_pnl"]) / rk if (t["status"] == "closed" and rk) else None


agree = 0
for t in real:
    res = t["_rep"]
    live_r = live_stop_r(t)
    live_partial = "partial_profit" in (t["exits_json"] or "")
    rr = res["realized_r"] if (res and res["status"] == "settled") else None
    line = (f"  {t['alert_date']} {t['ticker']:5s} live={t['status']:9s} entry={t['entry_price'] or '-':>8s} "
            f"stop-R={'%+.2f' % live_r if live_r is not None else '  open ' if t['status']=='filled' else '   -  '} "
            f"partial={'Y' if live_partial else 'n'} | replay={res['status'] if res else 'n/a':15s} "
            f"entry={('%.2f' % res['entry_px']) if res and res['entry_px'] else '-':>8s} "
            f"R={('%+.2f' % rr) if rr is not None else ('mark %+.2f' % (res['mark_r'] / 1.0) if res and res.get('mark_r') is not None else '-')} "
            f"partial={'Y' if res and res['partial_fired'] else 'n'} final={res['final_reason'] if res else ''} "
            f"{res['reason'] or '' if res else ''}")
    if live_r is not None and rr is not None:
        line += f"  dR={rr - live_r:+.2f}"
        if abs(rr - live_r) <= 0.25:
            agree += 1
    print(line)
closed_live = [t for t in real if t["status"] == "closed"]
print(f"  closed live trades: {len(closed_live)}; replay within 0.25R on {agree} of "
      f"{sum(1 for t in real if t['status']=='closed' and t['_rep'] and t['_rep']['status']=='settled')} settled replays")

# ── (R) the REAL era-D book (what actually happened; stop-R on the PLACED stop) ──
print("\n" + "=" * 90)
print("R. THE REAL ERA-D BOOK — magna53 live rows, alert days 09-08..10-09")
print("=" * 90)
st = Counter(t["status"] for t in real)
print("  rows by status:", dict(st))
skips = Counter((t["skip_reason"] or "").split(":")[0] + ":" + ((t["skip_reason"] or "").split(":")[1].strip() if ":" in (t["skip_reason"] or "") else "")
                for t in real if t["status"] == "skipped")
print("  skip reasons:", dict(skips))
rs_live = []
for t in closed_live:
    r = live_stop_r(t)
    rs_live.append(r)
    print(f"    closed {t['ticker']:5s} {t['alert_date']} pnl ${f(t['total_pnl']):+.2f} on placed-stop risk ${live_risk(t):.2f} "
          f"= {r:+.2f} stop-R  [old frame: planned risk_dollars ${f(t['risk_dollars']):.2f} -> "
          f"{f(t['total_pnl'])/f(t['risk_dollars']):+.2f}]; exit {t['closed_et'][:10]}")
print(f"  closed: n={len(rs_live)} mean {sum(rs_live)/len(rs_live):+.2f} stop-R, sum {sum(rs_live):+.1f}R, "
      f"winners {sum(1 for x in rs_live if x>0)}; without the best: {sum(rs_live) - max(rs_live):+.1f}R over {len(rs_live)-1}")
openrows = [t for t in real if t["status"] == "filled"]
for t in openrows:
    last = daily.get(t["ticker"], {}).get(LAST_SETTLED, {}).get("c")
    e, risk, sh, rem = f(t["entry_price"]), live_risk(t), f(t["entry_shares"]), f(t["remaining_shares"])
    booked = f(t["total_pnl"]) or 0.0
    mark = (booked + (last - e) * rem) / risk if (last and risk) else None
    hi = f(t["highest_price_seen"]); ol = f(t["orb_low"])
    mfe_orb = (hi - e) / (e - ol) if (hi and ol) else None
    print(f"    open   {t['ticker']:5s} {t['alert_date']} entry {e:.2f} remaining {rem:.0f}/{sh:.0f} "
          f"booked ${booked:+.2f} last {last} -> mark {mark:+.2f} stop-R (not a return) "
          f"[old frame: {(booked + (last - e) * rem) / f(t['risk_dollars']):+.2f}]; "
          f"highest seen {hi} = +{mfe_orb:.1f} ORB-R; partial={'Y' if t['partial_taken']=='t' else 'n'} "
          f"breakeven={'armed' if t['breakeven_active']=='t' else 'no'}")
n8 = sum(1 for t in real if "partial_profit" in (t["exits_json"] or ""))
print(f"  +8R PARTIAL FILLS in the window: {n8} of {len(closed_live)+len(openrows)} filled trades "
      f"({[t['ticker'] for t in real if 'partial_profit' in (t['exits_json'] or '')]})")
# the real fills' tail: peak (highest_price_seen) in BOTH frames, from the placed stop
print("  REAL FILLS' TAIL (peak highest_price_seen; stop-R from the placed stop):")
tail3o = tail8o = tail3s = tail8s = 0
for t in closed_live + openrows:
    e, hi, ol = f(t["entry_price"]), f(t["highest_price_seen"]), f(t["orb_low"])
    rk_ps = e - f(t["hard_stop"])
    o_r = (hi - e) / (e - ol)
    s_r = (hi - e) / rk_ps
    tail3o += o_r >= 3; tail8o += o_r >= 8; tail3s += s_r >= 3; tail8s += s_r >= 8
    print(f"    {t['ticker']:5s} peak {hi:.2f}: +{o_r:.1f} ORB-R, +{s_r:.1f} stop-R")
print(f"  real fills (n={len(closed_live)+len(openrows)}) reaching >=3 ORB-R {tail3o}, >=8 ORB-R {tail8o}, "
      f">=3 stop-R {tail3s}, >=8 stop-R {tail8s}")
# breakeven arms from the audit trail
be = [r for r in S1["ORBEVENTS"] if r["event_type"] == "breakeven_armed"]
print(f"  breakeven ARMED (+3R) events in the window: {len(be)} -> {[r['summary'].split(':')[0] for r in be]}")

# ── (A) in-window crossers, (B) gate-passing subset, (P) pre-open crossers ──
print("\n" + "=" * 90)
print("A/B. IN-WINDOW REAL-TIME CROSSERS (first rt read >= 9% at 09:31-09:44 ET), replayed under")
print("     `current` from the tick they crossed (ORB = the 09:30 bar; stop-buy at ORB high)")
print("=" * 90)
inwin = {k: r for k, r in first.items() if win(r["tick_et"]) == "inwin"}
days = sorted({d for d, _ in first})
print(f"  n={len(inwin)} ticker-days over {len(days)} trading days ({days[0]}..{days[-1]}) = "
      f"{len(inwin)/len(days):.1f}/day | by first event: "
      f"{dict(Counter(r['event_type'] for r in inwin.values()))}")
fates = Counter(fate(k) for k in inwin)
print(f"  live scan fate (by reject_stage): {dict(fates)}")
at0930 = sorted(k for k, r in inwin.items() if r["tick_et"] == "09:30")
in3144 = [k for k in inwin if k not in set(at0930)]
print(f"  of which first read at the 09:30 tick (folded in; entered from 09:31): n={len(at0930)} "
      f"{[(d, t, inwin[(d, t)]['event_type'][6:], inwin[(d, t)]['rt_gap'] + '%') for d, t in at0930]}")
print(f"  FATE TABLE by reject_stage — 09:31-09:44 (n={len(in3144)}): {dict(Counter(fate(k) for k in in3144))} | "
      f"09:30 (n={len(at0930)}): {dict(Counter(fate(k) for k in at0930))} | all (n={len(inwin)}): {dict(fates)}")
print(f"  first-cut classifier (filter_reason text) on the same 09:31-09:44 {len(in3144)}: "
      f"{dict(Counter(fate_old(k) for k in in3144))}")
flips = sorted((k, fate_old(k), fate(k)) for k in inwin if fate_old(k) != fate(k))
print(f"  names whose fate changed vs the first-cut classifier: {len(flips)}")
for k, o, n_ in flips:
    reasons = sorted({(r['reject_stage'] + ':' + (r['filter_reason'] or '')[:34]) for r in sl.get(k, []) if r['reject_stage'] != 'gap_floor'})
    print(f"     {k[0]} {k[1]:5s} {o:17s} -> {n_:17s} {reasons}")
cov = {(r["ticker"], r["d"]): r for r in S1["COVERAGE"]}
thin = [k for k in inwin if int(cov.get((k[1], k[0]), {}).get("rth_bars", 0) or 0) < 300]
print(f"  minute-bar coverage: {len(thin)} of {len(inwin)} in-window names are missing >= 90 of the 390 RTH minute "
      f"bars (rth_bars < 300); no 09:30 bar: {sum(1 for k in inwin if cov.get((k[1], k[0]), {}).get('has_930') != 't')}")
rt_only = {k: r for k, r in inwin.items() if r["event_type"] != "ep_rt_admit"}
print(f"  rt-only admits (the class the switches ADD; delayed feed had not cleared the floor): "
      f"{len(rt_only)} | delayed-agreed (ep_rt_admit first): {len(inwin) - len(rt_only)}")

rows_a = []
for (d, t), r in sorted(inwin.items()):
    res = replay(t, D(d), tick_submit(r["tick_et"]))
    res.update(cls=r["event_type"], tick=r["tick_et"], fate=fate((d, t)), rt_only=r["event_type"] != "ep_rt_admit")
    rows_a.append(res)
A = summarize("(a) ALL in-window crossers", rows_a)
A_rt = summarize("(a') rt-only subset of (a)", [r for r in rows_a if r["rt_only"]])
B = summarize("(b) gate-passing subset of (a): reached grading or alerted", [r for r in rows_a if r["fate"] in ("graded_below_bar", "alerted")])
B2 = summarize("(b') alerted subset of (a)", [r for r in rows_a if r["fate"] == "alerted"])
print("\n  (a) entered campaigns, one line each (stop-R; MFE in ORB-R):")
for r in sorted(rows_a, key=lambda x: (x["realized_r"] if x["realized_r"] is not None else (x["mark_r"] or 0))):
    if r["entered"]:
        rr = (f"{r['realized_r']:+.2f}" if r["realized_r"] is not None
              else (f"mark {r['mark_r']:+.2f}" if r.get("mark_r") is not None else f"abstain"))
        mfe = f"{r['mfe_orb_r']:+.1f}" if r.get("mfe_orb_r") is not None else "-"
        print(f"     {r['alert_date']} {r['ticker']:5s} @{r['tick']} {r['cls'][6:]:14s} fate={r['fate']:17s} "
              f"entry {r['entry_px']:.2f} stop {r['stop']:.2f} -> {rr:>11s} {(r['final_reason'] or r['reason'] or r['status']):32s} "
              f"MFE {mfe:>5s} ORB-R partial={'Y' if r['partial_fired'] else 'n'}")

print("\n" + "=" * 90)
print("P. PRE-OPEN CROSSERS (first rt read >= 9% before 09:30), replayed from 09:31 — the 08-10")
print("   doc's 'pre-open catches' class, for continuity only")
print("=" * 90)
pre = {k: r for k, r in first.items() if win(r["tick_et"]) == "preopen"}
print(f"  n={len(pre)} | fates (by reject_stage) {dict(Counter(fate(k) for k in pre))} | "
      f"first-cut classifier {dict(Counter(fate_old(k) for k in pre))}")
rows_p = []
for (d, t), r in sorted(pre.items()):
    res = replay(t, D(d), time(9, 31))
    res.update(cls=r["event_type"], tick=r["tick_et"], fate=fate((d, t)))
    rows_p.append(res)
Pz = summarize("(p) ALL pre-open crossers", rows_p)
Pg = summarize("(p') pre-open crossers that reached grading or alerted", [r for r in rows_p if r["fate"] in ("graded_below_bar", "alerted")])
late = {k: r for k, r in first.items() if win(r["tick_et"]) == "late"}
print(f"\n  (late) crossers first seen at/after 09:45: n={len(late)} — cannot be entered under the ORB window; not replayed")

# ── (C) pre-open HIGH alerts ──
print("\n" + "=" * 90)
print("C. PRE-OPEN HIGH ALERTS (score_tier HIGH, detected before 09:30 ET) — real rows + replay")
print("=" * 90)
pre_high = [a for a in alerts.values() if a["score_tier"] == "HIGH" and a["detected_et"] < "09:30:00"]
inwin_high = [a for a in alerts.values() if a["score_tier"] == "HIGH" and "09:31:00" <= a["detected_et"] <= "09:44:59"]
late_high = [a for a in alerts.values() if a["score_tier"] == "HIGH" and a["detected_et"] >= "09:45:00"]
print(f"  HIGH alerts: {len(pre_high)} pre-open, {len(inwin_high)} in-window (09:31-09:44), {len(late_high)} at/after 09:45 "
      f"({[a['ticker'] for a in late_high]} -> window:out_of_orb)")
rows_c = []
trade_by = defaultdict(list)
for t in real:
    trade_by[(t["alert_date"], t["ticker"])].append(t)
for a in sorted(pre_high, key=lambda x: (x["alert_date"], x["ticker"])):
    k = (a["alert_date"], a["ticker"])
    tr = trade_by.get(k, [])
    t0 = tr[0] if tr else None
    res = replay(a["ticker"], D(a["alert_date"]), time(9, 31),
                 orb_high=f(t0["orb_high"]) if t0 and f(t0["orb_high"]) else None,
                 orb_low=f(t0["orb_low"]) if t0 and f(t0["orb_low"]) else None,
                 atr=f(t0["atr_14"]) if t0 and f(t0["atr_14"]) else None)
    res.update(fate="alerted", live_status=t0["status"] if t0 else "no_row",
               live_skip=(t0["skip_reason"] or "")[:60] if t0 else "")
    rows_c.append(res)
    lr = live_stop_r(t0) if t0 else None
    rr = f"{res['realized_r']:+.2f}" if res["realized_r"] is not None else (f"mark {res['mark_r']:+.2f}" if res.get("mark_r") is not None else "-")
    print(f"    {a['alert_date']} {a['ticker']:5s} det {a['detected_et']} live={res['live_status']:9s} "
          f"{('stop-R %+.2f' % lr) if lr is not None else '':12s} {res['live_skip'][:45]:45s} | replay {res['status']:15s} R {rr:>11s} "
          f"MFE {('%+.1f' % res['mfe_orb_r']) if res.get('mfe_orb_r') is not None else '-':>6s} ORB-R")
C = summarize("(c) pre-open HIGH, replayed under current", rows_c)
print("  FIRST real-time event of each HIGH alert's ticker-day (ep_rt_admit = the delayed feed AGREED, i.e. it")
print("  would have been admitted with both switches OFF; anything else = real-time-only first read):")
for grp, lst in (("pre-open", pre_high), ("in-window", inwin_high), ("at/after 09:45", late_high)):
    firsts = []
    for a in sorted(lst, key=lambda x: (x["alert_date"], x["ticker"])):
        fr = first.get((a["alert_date"], a["ticker"]))
        firsts.append((a["ticker"], a["alert_date"][5:], fr["event_type"][6:] if fr else "NO-EVENT", fr["tick_et"] if fr else "-",
                       (fr["rt_gap"] + "/" + fr["delayed_gap"]) if fr else "-"))
    adm = [x[0] for x in firsts if x[2] == "admit"]
    rto = [x[0] for x in firsts if x[2] != "admit"]
    print(f"   {grp} HIGH n={len(lst)}: first event ep_rt_admit {len(adm)} {adm} | real-time-only {len(rto)} {rto}")
    for x in firsts:
        print(f"      {x[0]:5s} {x[1]} first={x[2]:15s} @{x[3]} rt/delayed gap {x[4]}")
pre_high_closed = [t for t in closed_live if (t["alert_date"], t["ticker"]) in {(a["alert_date"], a["ticker"]) for a in pre_high}]
if pre_high_closed:
    rr = [live_stop_r(t) for t in pre_high_closed]
    print(f"   REAL closed trades from pre-open HIGH: n={len(rr)} mean {sum(rr)/len(rr):+.2f} stop-R, "
          f"winners {sum(1 for x in rr if x > 0)}, best {max(rr):+.2f}, without the best {sum(rr) - max(rr):+.1f}R over {len(rr)-1}")

# ── (G) entry-time gap-floor blocks: correct save vs blocked-then-reclaimed ──
print("\n" + "=" * 90)
print("G. ENTRY-TIME REAL-TIME GAP-FLOOR BLOCKS (setup:gap_below_floor) — correct save vs")
print("   blocked-then-reclaimed (any 09:31-09:44 minute high back at/above the 9% floor price)")
print("=" * 90)
blocks = [t for t in real if (t["skip_reason"] or "").startswith("setup:gap_below_floor")]
rx = re.compile(r"rt ([\-\d.]+)% < ([\d.]+)% floor \(alert said ([\d.]+)%, last \$([\d.]+) vs prev close \$([\d.]+)\)")
for t in blocks:
    m = rx.search(t["skip_reason"])
    rt_gap, floor, alert_gap, last, pc = (float(x) for x in m.groups())
    d = D(t["alert_date"])
    pc_daily = None
    prior = [dd for dd in sorted(daily.get(t["ticker"], {})) if dd < d]
    if prior:
        pc_daily = daily[t["ticker"]][prior[-1]]["c"]
    floor_px = pc * (1 + floor / 100)
    bars = [b for b in minutes.get((t["ticker"], d), []) if time(9, 31) <= b["m"].time() <= time(9, 44)]
    hi = max((b["h"] for b in bars), default=None)
    reclaim = next((b for b in bars if b["h"] >= floor_px), None)
    d0 = daily.get(t["ticker"], {}).get(d, {})
    close_gap = ((d0.get("c") - pc) / pc * 100) if d0.get("c") else None
    fwd = [daily[t["ticker"]][dd] for dd in sorted(daily.get(t["ticker"], {})) if d < dd <= d + timedelta(days=8)][:5]
    max5 = max((b["h"] for b in fwd if b["h"]), default=None)
    verdict = "BLOCKED-THEN-RECLAIMED (candidate false block)" if reclaim else "CORRECT SAVE (never regained the floor in the window)"
    print(f"  {t['alert_date']} {t['ticker']:5s} blocked at 09:31 rt {rt_gap:.1f}% (alert {alert_gap:.1f}%, prev close ${pc:.2f}"
          f"{'' if pc_daily is None or abs(pc_daily-pc)<0.011 else ' ⚠ daily says %.2f' % pc_daily}); floor px ${floor_px:.2f}; "
          f"window high ${hi if hi is not None else 'n/a'} ({((hi-pc)/pc*100) if hi else float('nan'):+.1f}%) -> {verdict}")
    b931 = next((b for b in bars if b["m"].time() == time(9, 31)), None)
    hb = max(bars, key=lambda b: b["h"]) if bars else None
    if b931 and hb:
        print(f"      09:31 bar high ${b931['h']} = {((b931['h']-pc)/pc*100):+.1f}% vs prev close (floor px ${floor_px:.2f}: "
              f"{'AT/ABOVE' if b931['h'] >= floor_px else 'below'}); window high ${hb['h']} = {((hb['h']-pc)/pc*100):+.1f}% "
              f"at {hb['m'].time()}")
    print(f"      after: day-0 close {('%+.1f%%' % close_gap) if close_gap is not None else 'n/a'} vs prev close; "
          f"5-session max high {('%+.1f%%' % ((max5-pc)/pc*100)) if max5 else 'n/a'} vs prev close")
    if reclaim:
        res = replay(t["ticker"], d, max(time(9, 31), reclaim["m"].time()))
        rr = f"{res['realized_r']:+.2f}" if res["realized_r"] is not None else (f"mark {res['mark_r']:+.2f}" if res.get("mark_r") is not None else "-")
        print(f"      as-if entered at the reclaim minute {reclaim['m'].time()}: replay {res['status']} R {rr} {res['final_reason'] or res['reason'] or ''} "
              f"MFE {('%+.1f' % res['mfe_orb_r']) if res.get('mfe_orb_r') is not None else '-'} ORB-R")
print(f"  total blocks {len(blocks)}: "
      f"{sum(1 for t in blocks if next((b for b in [bb for bb in minutes.get((t['ticker'], D(t['alert_date'])), []) if time(9,31) <= bb['m'].time() <= time(9,44)] if b['h'] >= float(rx.search(t['skip_reason']).group(5)) * (1 + float(rx.search(t['skip_reason']).group(2))/100)), None))} reclaimed")

# ── (L) the LIVE in-window entry mechanic (#500): at submission, if the last trade is already
#     above the ORB high the order is a LIMIT at last×1.002, allowed only while
#     (limit − stop) <= 1.5 × (orb_high − stop) (the chase cap); else the stop-limit at ORB high.
#     The harness's entry_walk models only the stop-limit leg, which is why IONQ/PENG disagree in V.
#     Here the submit-minute OPEN stands in for "last trade at submission". ──
from agents.market_intelligence.backtester.filters import validate_orb_entry  # noqa: E402
CHASE_CAP = 1.5


def replay_live_inwin(ticker: str, d: date, submit: time) -> dict:
    bars0 = minutes.get((ticker, d), [])
    orb = next((b for b in bars0 if b["m"].time() == time(9, 30)), None)
    out = {"ticker": ticker, "alert_date": d, "status": None, "reason": None, "entered": False,
           "entry_px": None, "stop": None, "realized_r": None, "mark_r": None, "partial_fired": False,
           "final_reason": None, "exits": [], "mfe_orb_r": None, "r_orb_per_stop_r": None, "path": None}
    if not orb:
        out.update(status="abstain", reason="no_930_bar_for_orb")
        return out
    oh, ol = orb["h"], orb["l"]
    atr = ep.atr14_abs(daily.get(ticker, {}), d)
    ok, skip = validate_orb_entry(oh, ol, atr)
    if not ok:
        out.update(status="no_trade", reason=skip)
        return out
    stop = RS.stop_price(oh, ol)
    sb_idx = next((i for i, b in enumerate(bars0) if b["m"].time() >= submit), None)
    if sb_idx is None:
        out.update(status="abstain", reason="no_bar_at_submit")
        return out
    sb = bars0[sb_idx]
    if sb["o"] <= oh:
        res = replay(ticker, d, submit)
        res["path"] = "stop_limit"
        return res
    limit = round(sb["o"] * 1.002, 2)
    if (limit - stop) > CHASE_CAP * (oh - stop):
        out.update(status="no_trade", reason="setup:chase_cap_exceeded", path="limit_capped")
        return out
    entry = sb["o"]
    r_ps = entry - ol
    adr_pct, _ = ep.adr20_pct(daily.get(ticker, {}), d)
    leg = ep._walk_leg(ticker=ticker, leg_date=d, entry_px=entry, stop=stop,
                       target=entry + RS.intraday_partial_r * r_ps, bars=bars0, fill_idx=sb_idx,
                       rs=RS, daily=daily, shares=None, integer_shares=False,
                       adr_dollar=(adr_pct * oh) if adr_pct else None, minutes_extra={},
                       fill_at_open=True, r_frame_ps=r_ps)
    out.update(entered=True, entry_px=entry, stop=stop, path="limit_chase", status=leg["status"],
               reason=leg["reason"], exits=leg["exits"], final_reason=leg["final_reason"],
               partial_fired=leg["partial_fired"], realized_r=leg["realized_r"], mark_r=leg["mark_r"])
    cut, until = exit_bound(leg)
    out["mfe_orb_r"] = mfe_orb_r(ticker, d, entry, ol, sb["m"], cut, until)
    out["r_orb_per_stop_r"] = (entry - stop) / r_ps
    return out


print("\n" + "=" * 90)
print("L. (a) AGAIN under the LIVE in-window mechanic (#500 limit-chase with the 1.5x cap) —")
print("   the path IONQ (cancelled) and PENG (filled) actually took")
print("=" * 90)
rows_l = []
for (d, t), r in sorted(inwin.items()):
    res = replay_live_inwin(t, D(d), tick_submit(r["tick_et"]))
    res.update(cls=r["event_type"], tick=r["tick_et"], fate=fate((d, t)), rt_only=True)
    rows_l.append(res)
print("  entry path taken:", dict(Counter(r.get("path") for r in rows_l)))
L = summarize("(a-live) ALL in-window crossers, live mechanic", rows_l)
Lb = summarize("(b-live) gate-passing subset, live mechanic", [r for r in rows_l if r["fate"] in ("graded_below_bar", "alerted")])
Lc = summarize("(b'-live) alerted subset, live mechanic", [r for r in rows_l if r["fate"] == "alerted"])
print("\n  (a-live) limit-chase entries (the ones the stop-limit replay could not fill):")
for r in rows_l:
    if r.get("path") == "limit_chase":
        rr = (f"{r['realized_r']:+.2f}" if r["realized_r"] is not None
              else (f"mark {r['mark_r']:+.2f}" if r.get("mark_r") is not None else "abstain"))
        print(f"     {r['alert_date']} {r['ticker']:5s} @{r['tick']} fate={r['fate']:17s} entry {r['entry_px']:.2f} "
              f"stop {r['stop']:.2f} -> {rr:>11s} {(r['final_reason'] or r['reason'] or r['status']):30s} "
              f"MFE {('%+.1f' % r['mfe_orb_r']) if r.get('mfe_orb_r') is not None else '-':>5s} ORB-R")

# ── write the per-row TSV once ──
cols = ["pop", "alert_date", "ticker", "cls", "tick", "fate", "status", "reason", "entered", "entry_px", "stop",
        "realized_r", "mark_r", "partial_fired", "final_reason", "mfe_orb_r", "r_orb_per_stop_r"]
with open(os.path.join(P, "s2_rows.tsv"), "w") as fh:
    fh.write("\t".join(cols) + "\n")
    for pop, rows in (("a_inwin", rows_a), ("a_inwin_live", rows_l), ("p_preopen", rows_p),
                      ("c_preopen_high", rows_c)):
        for r in rows:
            fh.write("\t".join(str(r.get(c, "") if c != "pop" else pop) for c in cols) + "\n")
print("\nrows written: s2_rows.tsv")
