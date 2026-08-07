#!/usr/bin/env python3
"""#545 Phase 1 — Day-1 stop-out RE-ENTRY sweep (EVIDENCE ONLY, READ-ONLY).

Spec: docs/design/545_entry_exit_program_2026-08-07.md §C3.1 / §D Phase 1.
Population: all 15 live stop-outs (14 closed live MAGNA53 trades 07-06..08-04 + TEAM 08-07).

THE LINE: evidence and a ranked read only. No live parameter, entry rule, stop basis or
threshold is changed or proposed here. Any live change is CHANGE_PROCESS + operator sign-off.

MECHANISM — a SECOND LEG in the existing `_stop_floor_forward_replay` walk (NOT a fourth
minute-bar replayer): each variant produces (entry_px, fill_time, stop) after the trade's
ACTUAL stop-out moment (mi_live_trades.closed_at); the leg is then handed VERBATIM to
`_stop_floor_forward_replay.replay()` — the frozen fill contract (pessimistic low-before-high;
fill-bar stop-outs need a close at/below the stop; partial scan starts strictly after the fill
bar; +2R partial 1/3 AT the level then breakeven; stop fills AT the stop, gap-throughs counted
with a gap-aware sensitivity line; time-stop at the close of session 10 counted from the
ORIGINAL alert day so every variant shares one absolute horizon; unsettled → mark-to-last,
flagged). k=0 of that harness reconciles to reality within 0.07R/trade — that reconciliation
is inherited, not re-derived.

SCORING (operator reframe 2026-08-07 — replaces average return): the pond contains the fish.
Score each variant on how many of the BIG WINNERS it HOLDS and how many of the BIG LOSERS it
AVOIDS — never on mean return. Classes are computed from the bars, per trade, POST-stop-out:
  BIG WINNER  = post-stop-out 5-session peak >= +2R (in the ORIGINAL trade's r-unit vs the
                ORIGINAL entry — same basis as §B of the 08-06 doc).
  NEVER-GREEN = post-stop-out price never traded above the ORIGINAL entry inside the horizon.
Peaks are session HIGHS, not closes — the report's realized column is what the live exit
ruleset actually BANKS, never the peak.

VARIANTS (each = one signal function; scan windows stated per variant, chosen per spec):
  NDO-pdl    next-day 09:30 open, unconditional; stop = stop-out day's low (prior-day low).
  NDO-o5l    next-day 09:35 entry (first bar after the opening 5-min range completes);
             stop = that first-5-min low — the honest, placeable form of the
             "re-entry-day low" stop (a day's own low is unknowable at its open).
  SD-5mclear same-day: first COMPLETE aligned 5-min window strictly after the stop-out
             defines a range; re-enter AT the range high when a later same-session bar
             clears it; stop = range low. (This is `orb_5m_reentry_hybrid_replay`,
             registered 2026-05-30, run here for the first time.)
  HL2/HL3    base-then-turn proxy A: N consecutive higher LOWS on post-stop 5-min bars,
             same session; entry at the Nth bar's close; stop = session low-so-far.
  HC2/HC3    base-then-turn proxy B: N consecutive higher CLOSES, same rules.
  BASE20/30/45  base-then-turn proxy C: rolling M-minute window of fully-post-stop bars
             whose total range <= 0.25 x ADR20; entry AT the basing high on a later 1-min
             break, stop = basing low, same session.
  620-6/20, 620-8/24, 620-12/26  the 620 family (docs/methodology/620_chart.md): MACD
             (fast/slow EMA on 5-min closes, 9-EMA signal) bullish cross strictly after the
             stop-out, warm-up >= slow-period bars, scanned on the stop-out session AND the
             next session (EMAs continuous across the boundary — a cross needs runway a
             15:50 stop-out day cannot give); entry at the cross bar's close; stop = the
             entry session's low-so-far (the basing low; the operator's TEAM fill used
             low-of-day-so-far). Periods are the author's own sensitivity axis.

MODELLING GUARDS (counted + reported, never silent):
  * degenerate legs (entry <= stop, or r-unit < 0.3% of entry) are SKIPPED — a near-zero
    r-unit makes the +2R partial fire on noise;
  * next-day variants on TEAM are N/A (no next session exists yet), excluded from that
    variant's denominator;
  * TEAM's 08-07 session was INCOMPLETE at capture (bars through ~15:36 ET) — every TEAM
    result is flagged unsettled.

INPUTS (capture once, read many): the frozen `_stop_floor_*.tsv` caches (14 trades, minute
bars alert..+16d, pulled 08-06/07) + `_545_team_{trade,daily,minute}.tsv` (pulled once
2026-08-07 ~15:45 ET via the same read-only ssh psql / in-container Polygon paths).

RUN:  python3 scripts/probes/_545_reentry_sweep.py        # pure local computation
"""
from __future__ import annotations

import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import _stop_floor_forward_replay as sfr  # noqa: E402  (the frozen contract — reused)

ET = sfr.ET

TEAM_TRADE = HERE / "_545_team_trade.tsv"
TEAM_DAILY = HERE / "_545_team_daily.tsv"
TEAM_MINUTE = HERE / "_545_team_minute.tsv"

MIN_R_UNIT_FRAC = 0.003          # degenerate-leg guard: r-unit must be >= 0.3% of entry
BASE_BAND_ADR = 0.25             # basing window range ceiling, x ADR20
WINNER_PEAK_R = 2.0              # big-winner class: post-stop 5-session peak >= +2R
HELD_R = 0.5                     # "held a winner" = leg realized >= +0.5R
LOSER_LEG_R = -0.5               # "paid a second stop" = leg realized <= -0.5R


# ── loading (reuse sfr parsers by pointing their module paths at each file) ──

def load_all():
    trades = sfr.load_trades()
    old = sfr.TRADES
    sfr.TRADES = TEAM_TRADE
    trades += sfr.load_trades()
    sfr.TRADES = old

    minute = sfr.load_minute()
    old = sfr.MINUTE
    sfr.MINUTE = TEAM_MINUTE
    team_minute = sfr.load_minute()
    sfr.MINUTE = old
    for tk, bars in team_minute.items():
        minute.setdefault(tk, []).extend(bars)
        minute[tk].sort(key=lambda b: b["t"])

    daily = sfr.load_daily()
    for tk, rows in sfr.load_daily(TEAM_DAILY).items():
        daily.setdefault(tk, []).extend(rows)
        daily[tk].sort(key=lambda d: d["date"])
    fwd_daily = sfr.load_daily(sfr.FWD_DAILY)      # corroboration only; no TEAM (day open)
    return trades, minute, daily, fwd_daily


# ── per-trade context ────────────────────────────────────────────────────────

def build_ctx(t: dict, bars: list[dict]) -> dict | None:
    """Sessions, stop-out anchor, and post-stop reference stats for one trade."""
    sessions = sorted({b["d"] for b in bars if b["d"] >= t["alert_date"]})
    if not sessions or sessions[0] != t["alert_date"]:
        return None
    day_of = {d: i for i, d in enumerate(sessions)}
    stop_dt = t["closed_at"].astimezone(ET)
    stop_day = stop_dt.date().isoformat()
    stop_ms = int(stop_dt.timestamp() * 1000)
    stop_di = day_of.get(stop_day)
    nxt = [d for d in sessions if d > stop_day]
    next_day = nxt[0] if nxt else None

    r0 = t["entry"] - t["hard_stop"]
    horizon = [b for b in bars if b["d"] in day_of
               and day_of[b["d"]] <= sfr.TIME_STOP_SESSION]
    post = [b for b in horizon if b["t"] + 60_000 > stop_ms]
    post5 = [b for b in post if stop_di is not None
             and day_of[b["d"]] <= stop_di + 5]
    peak5 = max((b["h"] for b in post5), default=None)
    return {
        "sessions": sessions, "day_of": day_of, "next_day": next_day,
        "stop_dt": stop_dt, "stop_day": stop_day, "stop_ms": stop_ms,
        "stop_di": stop_di,
        "peak5_r": (peak5 - t["entry"]) / r0 if peak5 else None,
        "green": any(b["h"] > t["entry"] for b in post),
        "sess_have_10": len(sessions) > sfr.TIME_STOP_SESSION,
    }


def resample_5m(bars: list[dict]) -> list[dict]:
    """1-min → aligned 5-min bars (window index from 09:30). Keeps the last 1-min bar's
    dt as `end_bar_dt` so close-based entries can hand replay() a real 1-min fill bar."""
    out: list[dict] = []
    for b in bars:
        w = ((b["dt"].hour * 60 + b["dt"].minute) - 570) // 5
        key = (b["d"], w)
        if out and out[-1]["key"] == key:
            f = out[-1]
            f["h"] = max(f["h"], b["h"])
            f["l"] = min(f["l"], b["l"])
            f["c"] = b["c"]
            f["end_bar"] = b
        else:
            out.append({"key": key, "d": b["d"], "w": w, "t": b["t"],
                        "o": b["o"], "h": b["h"], "l": b["l"], "c": b["c"],
                        "start_dt": b["dt"], "end_bar": b})
    return out


# ── variant signal functions: (trade, bars, ctx) → leg dict | (None, reason) ─

def _leg(entry_px, fill_bar, stop_px, ctx, note=""):
    if entry_px is None or stop_px is None:
        return None, "no_signal"
    if entry_px <= stop_px:
        return None, "degenerate:entry<=stop"
    if (entry_px - stop_px) / entry_px < MIN_R_UNIT_FRAC:
        return None, "degenerate:r_unit<0.3%"
    return {"entry": entry_px, "fill_dt": fill_bar["dt"], "stop": stop_px,
            "fire_day": ctx["day_of"][fill_bar["d"]], "note": note}, None


def sig_nextopen_pdl(t, bars, ctx):
    if ctx["next_day"] is None:
        return None, "n/a:no_next_session_data"
    pdl = min((b["l"] for b in bars if b["d"] == ctx["stop_day"]), default=None)
    nd = [b for b in bars if b["d"] == ctx["next_day"]]
    return _leg(nd[0]["o"], nd[0], pdl, ctx, "stop=stop-day low")


def sig_nextopen_o5l(t, bars, ctx):
    if ctx["next_day"] is None:
        return None, "n/a:no_next_session_data"
    nd = [b for b in bars if b["d"] == ctx["next_day"]]
    first5 = [b for b in nd if (b["dt"].hour, b["dt"].minute) < (9, 35)]
    after = [b for b in nd if (b["dt"].hour, b["dt"].minute) >= (9, 35)]
    if not first5 or not after:
        return None, "no_signal:thin_open"
    return _leg(after[0]["o"], after[0], min(b["l"] for b in first5), ctx,
                "stop=first-5m low")


def sig_5m_clear(t, bars, ctx):
    """Same-day: first complete aligned 5-min window strictly after the stop-out;
    re-enter AT its high on a later same-session clear; stop = its low."""
    day = [b for b in bars if b["d"] == ctx["stop_day"]]
    stop_w = None
    for b in day:
        if b["t"] <= ctx["stop_ms"]:
            stop_w = ((b["dt"].hour * 60 + b["dt"].minute) - 570) // 5
    if stop_w is None:
        return None, "no_signal:no_pre_stop_bars"
    fives = resample_5m(day)
    rng = next((f for f in fives if f["w"] > stop_w), None)
    if rng is None:
        return None, "no_signal:no_post_stop_window"
    for b in day:
        w = ((b["dt"].hour * 60 + b["dt"].minute) - 570) // 5
        if w > rng["w"] and b["h"] >= rng["h"]:
            return _leg(rng["h"], b, rng["l"], ctx,
                        f"range {rng['l']:.2f}-{rng['h']:.2f}")
    return None, "no_signal:never_cleared"


def _post_stop_5m(bars, ctx):
    day = [b for b in bars if b["d"] == ctx["stop_day"]]
    fives = resample_5m(day)
    post = [f for f in fives if f["t"] > ctx["stop_ms"]]        # fully post-stop windows
    return day, fives, post


def make_sig_run(n: int, field: str):
    """N consecutive higher lows ('l') or higher closes ('c') on post-stop 5-min bars;
    entry at the Nth bar's close; stop = session low-so-far."""
    def sig(t, bars, ctx):
        day, fives, post = _post_stop_5m(bars, ctx)
        if len(post) < n:
            return None, "no_signal:too_few_post_stop_bars"
        run = 0
        for f in post:
            i = fives.index(f)
            prev = fives[i - 1] if i > 0 else None
            run = run + 1 if (prev and f[field] > prev[field]) else 0
            if run >= n:
                ses_low = min(x["l"] for x in fives[:i + 1])
                return _leg(f["c"], f["end_bar"], ses_low, ctx,
                            f"run of {n} higher {field}")
        return None, "no_signal:no_run"
    return sig


def make_sig_base(m_min: int):
    """Rolling m-minute window of fully-post-stop 5m bars with total range
    <= BASE_BAND_ADR x ADR20; entry AT the basing high on a later 1-min break."""
    k = m_min // 5

    def sig(t, bars, ctx):
        day, fives, post = _post_stop_5m(bars, ctx)
        if t.get("adr20") is None:
            return None, "n/a:no_adr20"
        if len(post) < k:
            return None, "no_signal:too_few_post_stop_bars"
        for i in range(k - 1, len(post)):
            win = post[i - k + 1:i + 1]
            hi, lo = max(f["h"] for f in win), min(f["l"] for f in win)
            mid = win[-1]["c"]
            if (hi - lo) / mid * 100 <= BASE_BAND_ADR * t["adr20"]:
                end_t = win[-1]["end_bar"]["t"]
                for b in day:
                    if b["t"] > end_t and b["h"] >= hi:
                        return _leg(hi, b, lo, ctx,
                                    f"base {m_min}m {lo:.2f}-{hi:.2f}")
                return None, "no_signal:base_never_broke"
        return None, "no_signal:no_base"
    return sig


def _ema(vals, n):
    a, out, e = 2.0 / (n + 1), [], None
    for v in vals:
        e = v if e is None else e + a * (v - e)
        out.append(e)
    return out


def make_sig_620(fast: int, slow: int, sig_n: int = 9):
    """First bullish MACD(fast,slow) cross on 5-min bars strictly after the stop-out,
    scanned over the stop-out session + the next session (continuous EMAs), warm-up >=
    slow bars; entry at the cross bar's close; stop = entry session low-so-far."""
    def sig(t, bars, ctx):
        days = [ctx["stop_day"]] + ([ctx["next_day"]] if ctx["next_day"] else [])
        series = resample_5m([b for b in bars if b["d"] in days])
        closes = [f["c"] for f in series]
        macd = [f - s for f, s in zip(_ema(closes, fast), _ema(closes, slow))]
        sigl = _ema(macd, sig_n)
        for i in range(1, len(series)):
            f = series[i]
            end_ms = f["end_bar"]["t"] + 60_000
            if i < slow or end_ms <= ctx["stop_ms"]:
                continue
            if macd[i - 1] - sigl[i - 1] <= 0 and macd[i] - sigl[i] > 0:
                ses = [x for x in series[:i + 1] if x["d"] == f["d"]]
                return _leg(f["c"], f["end_bar"], min(x["l"] for x in ses), ctx,
                            f"cross {f['start_dt'].strftime('%H:%M')} d{ctx['day_of'][f['d']]}")
        return None, "no_signal:no_cross"
    return sig


VARIANTS: list[tuple[str, object]] = [
    ("NDO-pdl", sig_nextopen_pdl),
    ("NDO-o5l", sig_nextopen_o5l),
    ("SD-5mclear", sig_5m_clear),
    ("HL2", make_sig_run(2, "l")),
    ("HL3", make_sig_run(3, "l")),
    ("HC2", make_sig_run(2, "c")),
    ("HC3", make_sig_run(3, "c")),
    ("BASE20", make_sig_base(20)),
    ("BASE30", make_sig_base(30)),
    ("BASE45", make_sig_base(45)),
    ("620-6/20", make_sig_620(6, 20)),
    ("620-8/24", make_sig_620(8, 24)),
    ("620-12/26", make_sig_620(12, 26)),
]


# ── run one leg through the FROZEN walk ──────────────────────────────────────

def run_leg(t, bars, leg, gap_aware=False):
    synth = {"ticker": t["ticker"], "alert_date": t["alert_date"],
             "entry": leg["entry"], "filled_at": leg["fill_dt"]}
    return sfr.replay(synth, bars, leg["stop"], partial_on=True, gap_aware=gap_aware)


# ── verification fixture: the TEAM 620 worked example ────────────────────────

def verify_team_620(trades, minute):
    """docs/methodology/620_chart.md computed (from mi_intraday_bars): MACD(6,20,sig 9)
    bullish cross on the 11:40 ET bar, close 143.68; operator entry ~12:05 at 144.39.
    Recompute from the Polygon bars UNDER THE SWEEP'S OWN GATES (warm-up >= slow bars —
    without it the seeded EMAs emit a garbage cross in the first half hour)."""
    t = next((x for x in trades if x["ticker"] == "TEAM"), None)
    if t is None:
        print("⚠ TEAM missing — fixture skipped")
        return
    day = [b for b in minute["TEAM"] if b["d"] == "2026-08-07"]
    series = resample_5m(day)
    closes = [f["c"] for f in series]
    macd = [f - s for f, s in zip(_ema(closes, 6), _ema(closes, 20))]
    sigl = _ema(macd, 9)
    hit = next(((series[i]["start_dt"].strftime("%H:%M"), series[i]["c"])
                for i in range(20, len(series))
                if macd[i - 1] - sigl[i - 1] <= 0 and macd[i] - sigl[i] > 0), (None, None))
    ok = hit[0] in ("11:35", "11:40", "11:45")
    print(f"620 fixture — TEAM first warm-up-gated bullish MACD(6,20) cross at {hit[0]} ET "
          f"close {hit[1]} (methodology doc, from mi_intraday_bars: 11:40 close 143.68) → "
          f"{'AGREES' if ok else '⚠ DISAGREES — 620 rows suspect'}")


# ── report ───────────────────────────────────────────────────────────────────

def main():
    trades, minute, daily, fwd_daily = load_all()
    for t in trades:
        t["adr20"] = sfr.adr20_pct(daily.get(t["ticker"], []), t["alert_date"])
        t["ctx"] = build_ctx(t, minute.get(t["ticker"], []))
        if t["ctx"] is None:
            sys.exit(f"{t['ticker']}: no entry-day bars — cache broken")

    print(f"#545 Phase 1 — re-entry sweep over {len(trades)} live stop-outs "
          f"(READ-ONLY EVIDENCE; THE LINE: nothing changed, nothing proposed)")

    # inherited-contract spot check: leg-1 stop-only replay still reconciles
    tot_sim = tot_act = 0.0
    for t in trades:
        r = sfr.replay(t, minute[t["ticker"]], t["hard_stop"], partial_on=False)
        if not r.get("error"):
            tot_sim += r["r"]
        tot_act += t["pnl"] / (t["shares"] * (t["entry"] - t["hard_stop"]))
    print(f"contract check — leg-1 stop-only sim {tot_sim:+.2f}R vs actual "
          f"{tot_act:+.2f}R on n={len(trades)} (divergence = slippage + the two "
          f"live raised-stop exits; full recon lives in _stop_floor_replay_output.txt)")
    verify_team_620(trades, minute)

    # reference classes (post-stop-out, computed not recalled)
    print("\n== population reference (POST-stop-out, in the ORIGINAL trade's r-unit) ==")
    print(f"{'tkr':<5} {'stop@ET':>16} {'d':>2} {'peak5R':>7} {'green':>6}  class")
    winners, nevergreen = set(), set()
    for t in sorted(trades, key=lambda x: -(x["ctx"]["peak5_r"] or -9)):
        c = t["ctx"]
        cls = ""
        if c["peak5_r"] is not None and c["peak5_r"] >= WINNER_PEAK_R:
            winners.add(t["ticker"])
            cls = "BIG WINNER (peak, not close)"
        if not c["green"]:
            nevergreen.add(t["ticker"])
            cls = "NEVER GREEN"
        team_flag = "  ⚠ session incomplete at capture" if t["ticker"] == "TEAM" else ""
        print(f"{t['ticker']:<5} {c['stop_dt'].strftime('%m-%d %H:%M'):>16} "
              f"{c['stop_di']:>2} {c['peak5_r']:>+7.2f} {str(c['green']):>6}  {cls}{team_flag}")
    print(f"big winners (peak5 >= +{WINNER_PEAK_R:.0f}R): {sorted(winners)}")
    print(f"never green: {sorted(nevergreen)}")

    # the sweep
    matrix: dict[str, dict[str, dict]] = {}
    for name, fn in VARIANTS:
        rows = {}
        for t in trades:
            bars = minute[t["ticker"]]
            leg, reason = fn(t, bars, t["ctx"])
            if leg is None:
                rows[t["ticker"]] = {"skip": reason}
                continue
            r = run_leg(t, bars, leg)
            rg = run_leg(t, bars, leg, gap_aware=True)
            rows[t["ticker"]] = {"leg": leg, "r": r, "r_gap": rg}
        matrix[name] = rows

    # per-trade matrix
    print("\n== per-trade realized R by variant (live exit ruleset on the re-entry leg; "
          "· = no fire, n/a = window absent, ! = unsettled at data end) ==")
    hdr = f"{'tkr':<6}" + "".join(f"{n:>11}" for n, _ in VARIANTS)
    print(hdr)
    for t in trades:
        row = f"{t['ticker']:<6}"
        for name, _ in VARIANTS:
            cell = matrix[name][t["ticker"]]
            if "skip" in cell:
                row += f"{'n/a' if cell['skip'].startswith('n/a') else '·':>11}"
            else:
                r = cell["r"]
                if r.get("error"):
                    row += f"{'ERR':>11}"
                else:
                    row += f"{r['r']:>+10.2f}{'!' if not r['settled'] else ' '}"
        print(row)

    # scoring table — the operator's yardstick first
    print("\n== SCORING (the reframed yardstick: winners HELD and losers AVOIDED, "
          "then realized R, then the cost) ==")
    print(f"{'variant':<11} {'fires':>6} {'winHeld':>8} {'QBTS':>6} {'HUT':>6} "
          f"{'lossAvoid':>9} {'2ndStops':>8} {'costR':>7} {'netR':>7} {'net$':>8} "
          f"{'exBest':>7} {'gapAw':>7} {'uns':>4}")
    for name, _ in VARIANTS:
        rows = matrix[name]
        fired = {tk: c for tk, c in rows.items()
                 if "leg" in c and not c["r"].get("error")}
        na = sum(1 for c in rows.values()
                 if "skip" in c and c["skip"].startswith("n/a"))
        rs = {tk: c["r"]["r"] for tk, c in fired.items()}
        held = sum(1 for tk in winners if rs.get(tk, 0) >= HELD_R)
        avoided = sum(1 for tk in nevergreen if rs.get(tk, 0) > LOSER_LEG_R)
        second = sum(1 for v in rs.values() if v <= LOSER_LEG_R)
        cost = sum(v for v in rs.values() if v < 0)
        net = sum(rs.values())
        net_d = sum(rs[tk] * next(t for t in trades if t["ticker"] == tk)["risk_dollars"]
                    for tk in rs)
        ex_best = net - max(rs.values(), default=0)
        gap = sum(c["r_gap"]["r"] for c in fired.values()
                  if not c["r_gap"].get("error"))
        uns = sum(1 for c in fired.values() if not c["r"]["settled"])
        denom = len(rows) - na
        print(f"{name:<11} {len(fired):>3}/{denom:<2} {held:>4}/{len(winners):<3} "
              f"{rs.get('QBTS', 0):>+6.2f} {rs.get('HUT', 0):>+6.2f} "
              f"{avoided:>5}/{len(nevergreen):<3} {second:>8} {cost:>+7.2f} {net:>+7.2f} "
              f"{net_d:>+8.2f} {ex_best:>+7.2f} {gap:>+7.2f} {uns:>4}")

    # fire detail (times + notes) for eyeball verification
    print("\n== fire detail (entry time/px/stop; verify against the tape, not trusted "
          "blind) ==")
    for name, _ in VARIANTS:
        parts = []
        for tk, c in matrix[name].items():
            if "leg" in c:
                lg = c["leg"]
                parts.append(f"{tk} d{lg['fire_day']} "
                             f"{lg['fill_dt'].strftime('%H:%M')} @{lg['entry']:.2f} "
                             f"stp {lg['stop']:.2f}")
        print(f"{name:<11} {' | '.join(parts) if parts else '(no fires)'}")
        skips = [f"{tk}:{c['skip']}" for tk, c in matrix[name].items()
                 if "skip" in c and c["skip"].startswith("degenerate")]
        if skips:
            print(f"{'':<11} degenerate-guard skips: {', '.join(skips)}")

    print("\n(EVIDENCE ONLY — no change made or proposed; entry/exit/stop discipline is "
          "the operator's sole authority. THE LINE.)")


if __name__ == "__main__":
    main()
