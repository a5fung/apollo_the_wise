#!/usr/bin/env python3
"""#490 delayed-screen-cost funnel — are the shadow universe catches real EPs or premarket noise?

READ-ONLY, $0. Consumes TSVs captured ONCE from prod on 2026-08-18 via
scripts/probes/_490_funnel_capture.sql (capture-once-read-many). One optional local
yfinance market-cap fill (free, no key) is itself captured once to _490cost_mcaps_yf.tsv.
No DB connection, no LLM spend, no writes outside scripts/probes/ + stdout.

QUESTION (operator, via #490 shadow): `ep_rt_universe_catch` = a real-time >=10% gap
crosser the ~15-min-delayed universe screen did NOT have as a candidate at that tick.
262-ish events since 2026-07-27, most never alerted. Real EPs lost to delayed data, or
premarket noise that faded by the open?

FUNNEL (pre-registered in the task, mirrors the 08-16 outside-winner machinery):
  Stage 1  still >= 10% at the ACTUAL OPEN (open vs prev close, mi_daily_closes) —
           the honest denominator; premarket prints that faded are arguably correctly ignored.
  Stage 2  our OTHER mechanical gates, replayed offline as-of the day:
           D-1 floors (prev close >=$5, prev vol >=50k — pre-cleared by rt_universe
           membership, re-verified), extension (prev_close vs MIN close over [d-10cal,d)
           >= +50% -> skip), ADV$ (median close*vol over [d-30cal,d) >= $1M, >=10 rows),
           ATR14 Wilder <= 15% of last close (rows < d, >=10 bars), mcap >= $500M
           (mi_market_caps cache + yfinance fill; missing -> flagged, not failed).
           NOT REPLAYABLE at $0 and therefore NOT applied (stated in the report):
           PM/session RVOL pace gates, the LLM catalyst grade + HIGH-tier score cut,
           top-20 gap-rank cap. Stage-2 survivors are an UPPER bound on would-have-alerted.
  Stage 3  what survivors DID, ADR-normalised, the program's own statistic:
           ADR% = mean (h-l)/c over <=20 sessions strictly before d (>=10 required);
           tailx = (max high over sessions d+1..d+20 - close(d)) / close(d) / ADR
           (identical to _552_missed_why_cohort.sql / the 08-16 outside-winner scan).
           RIGHT-CENSORING: the window is ~3 weeks old, so NO name has a full 20-session
           forward window. tailx here is tailx-SO-FAR (max-high only grows), so every
           ">=8xADR" share is a FLOOR. The alerted comparison uses the SAME dates and the
           SAME censoring, so the head-to-head is fair even though levels are floors.

COMPARISON SETS (same window, same machinery): (a) the alerted crossers (catch AND
mi_ep_alerts live row same day), (b) the full live alerted population 2026-07-27..08-18.

Usage: python3 scripts/probes/_490_delayed_cost_funnel.py
"""
import csv
import statistics as st
from datetime import date, timedelta
from pathlib import Path

HERE = Path(__file__).resolve().parent
WINDOW_START = date(2026, 7, 27)

def d(s): return date.fromisoformat(s)
def f(s):
    try: return float(s)
    except (TypeError, ValueError): return None

# ── load captures ────────────────────────────────────────────────────────────────
events = list(csv.DictReader(open(HERE / "_490cost_events.tsv"), delimiter="\t"))
alerts_rows = list(csv.DictReader(open(HERE / "_490cost_alerts.tsv"), delimiter="\t"))
scanlog = {(r["ticker"], r["d"]): r for r in csv.DictReader(open(HERE / "_490cost_scanlog.tsv"), delimiter="\t")}
mcap = {}
for r in csv.DictReader(open(HERE / "_490cost_mcaps.tsv"), delimiter="\t"):
    if r["market_cap"]:
        mcap[r["ticker"]] = float(r["market_cap"])

daily = {}
for r in csv.DictReader(open(HERE / "_490cost_daily.tsv"), delimiter="\t"):
    o, h, lo, c, v = f(r["open_price"]), f(r["high_price"]), f(r["low_price"]), f(r["close"]), f(r["volume"])
    if c is None:
        continue
    daily.setdefault(r["ticker"], []).append((d(r["trade_date"]), o, h, lo, c, v or 0.0))
for v in daily.values():
    v.sort()
DATA_END = max(rows[-1][0] for rows in daily.values())

# yfinance mcap fill — captured once; delete the file to refetch.
YF = HERE / "_490cost_mcaps_yf.tsv"
need = sorted({e["ticker"] for e in events} - set(mcap))
if not YF.exists() and need:
    import yfinance as yf
    with open(YF, "w") as fh:
        fh.write("ticker\tmarket_cap\n")
        for tk in need:
            mc = ""
            try:
                mc = yf.Ticker(tk).fast_info.get("marketCap") or ""
            except Exception:
                pass
            fh.write(f"{tk}\t{mc}\n")
if YF.exists():
    for r in csv.DictReader(open(YF), delimiter="\t"):
        if r["market_cap"] and r["ticker"] not in mcap:
            try: mcap[r["ticker"]] = float(r["market_cap"])
            except ValueError: pass

# ── dedupe events per (ticker, day); keep the FIRST tick ─────────────────────────
seen, catches, today_dropped = set(), [], 0
for e in events:
    k = (e["ticker"], e["d"])
    if k in seen:
        continue
    seen.add(k)
    if d(e["d"]) > DATA_END:      # catches from TODAY (no settled session yet) — excluded
        today_dropped += 1
        continue
    catches.append({"ticker": e["ticker"], "d": d(e["d"]), "tick": e["tick_et"],
                    "rt_gap": f(e["rt_gap"]), "delayed_gap": f(e["delayed_gap"])})

alerted_days = {}
for r in alerts_rows:
    alerted_days.setdefault((r["ticker"], r["alert_date"]), r)

for c in catches:
    c["alerted"] = (c["ticker"], c["d"].isoformat()) in alerted_days

# ── per-name-day machinery (shared by catches AND the alerted population) ────────
def bars_of(tk):  return daily.get(tk, [])

def context(tk, day):
    """Returns dict of everything derivable from daily bars as-of `day` for ticker."""
    rows = bars_of(tk)
    idx = next((i for i, r in enumerate(rows) if r[0] == day), None)
    if idx is None or idx == 0:
        return None
    prior = rows[:idx]
    dd, o, h, lo, c, v = rows[idx]
    pc, pv = prior[-1][4], prior[-1][5]
    out = {"o": o, "h": h, "c": c, "pc": pc, "pv": pv}
    out["open_gap"] = (o - pc) / pc * 100 if o and pc else None
    out["hi_gap"] = (h - pc) / pc * 100 if h and pc else None
    # extension: MIN close over [day-10cal, day)
    ext_win = [r[4] for r in prior if day - timedelta(days=10) <= r[0] < day]
    out["ext_pct"] = (pc - min(ext_win)) / min(ext_win) * 100 if ext_win and min(ext_win) > 0 else None
    # ADV$: median close*vol over [day-30cal, day), >=10 rows (live sees only settled rows)
    adv_win = [r[4] * r[5] for r in prior if day - timedelta(days=30) <= r[0] < day and r[5] > 0]
    out["adv_dollar"] = st.median(adv_win) if len(adv_win) >= 10 else None
    # ATR14 Wilder over rows < day (lookback 35 cal), >=10 bars
    atr_rows = [r for r in prior if r[0] >= day - timedelta(days=35) and r[2] is not None and r[3] is not None]
    if len(atr_rows) >= 10:
        trs = [max(atr_rows[i][2] - atr_rows[i][3], abs(atr_rows[i][2] - atr_rows[i-1][4]),
                   abs(atr_rows[i][3] - atr_rows[i-1][4])) for i in range(1, len(atr_rows))]
        atr = sum(trs[-14:]) / len(trs[-14:])
        out["atr_pct"] = atr / atr_rows[-1][4] * 100 if atr_rows[-1][4] > 0 else None
    else:
        out["atr_pct"] = None
    # ADR% over <=20 sessions strictly before day (>=10 required) — _552 definition
    adr_win = [(r[2] - r[3]) / r[4] for r in prior[-20:] if r[2] is not None and r[3] is not None and r[4] > 0]
    out["adr_pct"] = (sum(adr_win) / len(adr_win) * 100) if len(adr_win) >= 10 else None
    # forward: max high over sessions day+1..day+20 (whatever exists)
    fwd = rows[idx + 1: idx + 21]
    out["fwd_n"] = len(fwd)
    out["fwd_hi"] = max((r[2] for r in fwd if r[2] is not None), default=None)
    if out["fwd_hi"] and c and out["adr_pct"]:
        out["tailx"] = (out["fwd_hi"] - c) / c / (out["adr_pct"] / 100)
    else:
        out["tailx"] = None
    return out

def tail_stats(rows, label):
    xs = [r["tailx"] for r in rows if r.get("tailx") is not None]
    n = len(xs)
    win = sum(1 for x in xs if x >= 8)
    p90 = st.quantiles(xs, n=10)[-1] if n >= 10 else (max(xs) if xs else None)
    med = st.median(xs) if xs else None
    cen20 = sum(1 for r in rows if r.get("tailx") is not None and r["fwd_n"] < 20)
    fwd = [r["fwd_n"] for r in rows if r.get("tailx") is not None]
    print(f"  {label:<44} n={n:>3}  >=8xADR {win}/{n}"
          f" ({100*win/n:.1f}%)" if n else f"  {label:<44} n=0", end="")
    if n:
        print(f"  P90 {p90:.2f}x  med {med:.2f}x  censored(<20 fwd) {cen20}/{n}"
              f"  fwd_n med {st.median(fwd):.0f}")
    else:
        print()
    return {"n": n, "win": win, "p90": p90, "med": med, "cen": cen20}

P = print
P("=" * 100)
P("#490 delayed-screen-cost funnel — capture 2026-08-18, events 2026-07-27..{}".format(
    max(c["d"] for c in catches)))
P(f"data end (last settled session): {DATA_END}")
P("=" * 100)

# ── Stage 0: cohort ──────────────────────────────────────────────────────────────
n_ev = len(events)
al = [c for c in catches if c["alerted"]]
na = [c for c in catches if not c["alerted"]]
no_delay = [c for c in catches if c["delayed_gap"] is None]
P(f"\nSTAGE 0 — cohort: {n_ev} raw events -> {len(catches)} settled ticker-days "
  f"(+{today_dropped} from today {DATA_END + timedelta(days=1)}+, excluded: no settled session) "
  f"({len(al)} alerted same day, {len(na)} never alerted; "
  f"{len(no_delay)} had no delayed reading at the tick)")
rt = [c["rt_gap"] for c in catches if c["rt_gap"] is not None]
dl = [c["delayed_gap"] for c in catches if c["delayed_gap"] is not None]
P(f"mean rt_gap {st.mean(rt):.1f}%  vs mean delayed_gap {st.mean(dl):.1f}% (where present)")
ticks = sorted(c["tick"] for c in catches if c["tick"])
P(f"tick_et: min {ticks[0]}  median {ticks[len(ticks)//2]}  max {ticks[-1]}")

# ── Stage 1: still >=10% at the actual open ─────────────────────────────────────
P("\n" + "-" * 100)
P("STAGE 1 — did the gap HOLD to the actual open (open vs prev close, daily bars)?")
for c in catches:
    c["ctx"] = context(c["ticker"], c["d"])

def stage1(rows, label):
    nobar = [c for c in rows if c["ctx"] is None or c["ctx"]["open_gap"] is None]
    have = [c for c in rows if c["ctx"] is not None and c["ctx"]["open_gap"] is not None]
    held = [c for c in have if c["ctx"]["open_gap"] >= 10]
    faded_crossed = [c for c in have if c["ctx"]["open_gap"] < 10
                     and c["ctx"]["hi_gap"] is not None and c["ctx"]["hi_gap"] >= 10]
    faded_dead = [c for c in have if c["ctx"]["open_gap"] < 10
                  and (c["ctx"]["hi_gap"] is None or c["ctx"]["hi_gap"] < 10)]
    P(f"  {label}: {len(rows)} -> no daily bar {len(nobar)} | held >=10% at open {len(held)} "
      f"| faded <10% at open but crossed 10% intraday {len(faded_crossed)} "
      f"| never saw 10% again {len(faded_dead)}")
    if nobar:
        P(f"     no-daily-bar names: {sorted(set(c['ticker'] for c in nobar))}")
    return held, faded_crossed

held_na, faded_crossed_na = stage1(na, "never-alerted")
held_al, _ = stage1(al, "alerted crossers (context)")

# ── Stage 2: the other mechanical gates, replayed as-of the day ─────────────────
P("\n" + "-" * 100)
P("STAGE 2 — other mechanical gates on the never-alerted names that HELD at the open")
P("(gates replayed: D-1 floors, extension >=+50%/10cal-d, ADV$ median >=$1M, ATR14 <=15%, mcap >=$500M;")
P(" NOT replayed ($0 limit): PM/session RVOL pace, LLM catalyst grade + HIGH-tier cut, top-20 rank cap")
P(" -> survivors are an UPPER bound on would-have-alerted)")
surv, fails = [], {}
for c in held_na:
    x = c["ctx"]; tk = c["ticker"]
    why = []
    if x["pc"] is None or x["pc"] < 5:           why.append("prevclose<$5")
    if x["pv"] is None or x["pv"] < 50_000:      why.append("prevvol<50k")
    if x["ext_pct"] is not None and x["ext_pct"] >= 50:  why.append(f"extended+{x['ext_pct']:.0f}%")
    if x["adv_dollar"] is None:                  why.append("adv:no-data")
    elif x["adv_dollar"] < 1_000_000:            why.append(f"adv${x['adv_dollar']/1e6:.2f}M<1M")
    if x["atr_pct"] is not None and x["atr_pct"] > 15:   why.append(f"atr{x['atr_pct']:.0f}%>15")
    mc = mcap.get(tk)
    if mc is not None and mc < 500e6:            why.append(f"mcap${mc/1e6:.0f}M<500M")
    c["mcap_known"] = mc is not None
    c["fail"] = why
    if why:
        for w in why:
            fails[w.split("$")[0].split("+")[0].rstrip("0123456789.%")] = \
                fails.get(w.split("$")[0].split("+")[0].rstrip("0123456789.%"), 0) + 1
        continue
    surv.append(c)
P(f"  held-at-open never-alerted: {len(held_na)} -> SURVIVORS {len(surv)} "
  f"(mcap unknown on {sum(1 for c in surv if not c['mcap_known'])} of them)")
gate_counts = {}
for c in held_na:
    for w in c["fail"]:
        key = w.split("$")[0].split("+")[0]
        gate_counts[key] = gate_counts.get(key, 0) + 1
P(f"  gate hits (a name can hit several): {dict(sorted(gate_counts.items(), key=lambda kv: -kv[1]))}")
# scan-log attribution on the never-alerted held set
seen_scan = [c for c in held_na if int(scanlog.get((c["ticker"], c["d"].isoformat()), {}).get("scan_n", 0) or 0) > 0]
P(f"  delayed scan-log attribution (held set): {len(seen_scan)}/{len(held_na)} appeared in the "
  f"delayed scan log later that day (so the delay alone did not hide them); "
  f"{len(held_na) - len(seen_scan)} never appeared at all")
never_seen = [c for c in held_na if int(scanlog.get((c["ticker"], c["d"].isoformat()), {}).get("scan_n", 0) or 0) == 0]
P("  the pure delayed-invisibility class (held at open, NEVER in the delayed scan log):")
for c in never_seen:
    x = c["ctx"]
    P(f"    {c['ticker']} {c['d']} open_gap {x['open_gap']:.1f}%  gates-failed {c['fail'] or 'NONE'}  "
      f"tailx-so-far {x['tailx'] if x['tailx'] is not None else 'n/a'}")
P("  held-at-open names that failed my replayed gates AND were >=8xADR so far:")
for c in held_na:
    x = c["ctx"]
    if c["fail"] and x["tailx"] is not None and x["tailx"] >= 8:
        P(f"    {c['ticker']} {c['d']} gates-failed {c['fail']}  tailx-so-far {x['tailx']:.1f}")

# ── Stage 3: outcomes, ADR-normalised, same statistic as the outside-winner scan ─
P("\n" + "-" * 100)
P("STAGE 3 — what they DID (tailx = 20d-fwd max high vs EP-day close, in own-ADR units; >=8x = tail winner)")
P("ALL tailx are SO-FAR (right-censored) -> every share is a FLOOR; comparisons share dates+censoring\n")
s_surv = tail_stats([c["ctx"] for c in surv], "never-alerted, held open, passed gates")
s_heldall = tail_stats([c["ctx"] for c in held_na], "never-alerted, held open (pre-gates)")
s_faded = tail_stats([c["ctx"] for c in faded_crossed_na], "never-alerted, faded but crossed intraday")
s_alx = tail_stats([c["ctx"] for c in al if c["ctx"]], "alerted crossers (the 34)")

# full alerted population over the same window
pop = []
for (tk, ad), r in alerted_days.items():
    ctx = context(tk, d(ad))
    if ctx:
        pop.append(ctx)
s_pop = tail_stats(pop, f"ALL live alerts {WINDOW_START}..{DATA_END}")

P("\nSurvivor detail (never-alerted, held, passed mechanical gates):")
P(f"  {'ticker':<7}{'date':<12}{'tick':<7}{'rt_gap':>7}{'open_gap':>9}{'ADR%':>6}{'tailx':>7}{'fwd_n':>6}  mcap")
for c in sorted(surv, key=lambda c: -(c["ctx"]["tailx"] or -9)):
    x = c["ctx"]
    mc = mcap.get(c["ticker"])
    P(f"  {c['ticker']:<7}{c['d'].isoformat():<12}{c['tick']:<7}{c['rt_gap']:>7.1f}{x['open_gap']:>9.1f}"
      f"{x['adr_pct'] or 0:>6.1f}{(x['tailx'] if x['tailx'] is not None else float('nan')):>7.2f}{x['fwd_n']:>6}"
      f"  {'$%.1fB' % (mc/1e9) if mc else '?'}")

# ── prize arithmetic ────────────────────────────────────────────────────────────
P("\n" + "-" * 100)
tds = sorted({r[0] for rows in daily.values() for r in rows if WINDOW_START <= r[0] <= DATA_END})
months = len(tds) / 21
winners_new = [c for c in surv if c["ctx"]["tailx"] is not None and c["ctx"]["tailx"] >= 8]
P(f"PRIZE — window {WINDOW_START}..{DATA_END} = {len(tds)} trading days = {months:.2f} months")
P(f"  additional >=8xADR tail winners among gate-passing never-alerted survivors (SO FAR): "
  f"{len(winners_new)} -> {len(winners_new)/months:.1f}/month (a FLOOR: windows incomplete; "
  f"an UPPER-bounded pool: catalyst/RVOL/rank gates not replayed)")
P(f"  the alerted population produced {s_pop['win']} >=8xADR winners over the same window "
  f"({s_pop['win']/months:.1f}/month)")
for c in winners_new:
    P(f"    {c['ticker']} {c['d']} tailx-so-far {c['ctx']['tailx']:.1f}x (fwd {c['ctx']['fwd_n']}/20 sessions)")
