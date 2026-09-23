#!/usr/bin/env python3
"""#490b — the 137 faded-then-crossed names: cross timing, reachability, separability.

READ-ONLY, $0. Consumes the #490 funnel captures (scripts/probes/_490cost_*.tsv, via
importing _490_delayed_cost_funnel.py's module state) plus a ONE-TIME capture of
mi_intraday_bars for the covered ticker-days (_490b_intraday_bars.tsv, 2026-08-18).
No DB connection at runtime, no writes outside scripts/probes/ + stdout.

QUESTION: of the 137 never-alerted names that opened <10% but crossed 10% intraday
(the class holding ALL of the crosser pool's >=8xADR winners so far, and the class the
operator's ARGX complaint points at), when did they cross, which subset could our
09:31-09:45 ORB machinery ever act on, and are the winners separable at ~09:45?

PRE-REGISTRATION (written 2026-08-18 BEFORE any subgroup outcome below was computed;
honesty note: the three winner identities + their open gaps were already published in
docs/analysis/490_delayed_screen_cost_2026-08-18.md, so full outcome-blindness is
impossible — every threshold's sensitivity is therefore reported, none silently chosen):

  PRIMARY RULE — "high-water floor": qualify if any minute-bar high in 09:30-09:45
  reaches >= prev_close * 1.10. Uses ONLY existing system constants (the 10% floor,
  the 09:45 ORB-submission-window end). ZERO free parameters. This is the exact
  replacement of the current point-read-at-~09:31 with a window-max read.

  SENSITIVITY (all reported, none primary):
    cross-by boundary in {09:35, 09:45*, 10:00, 10:30, 12:00, close}  (*=primary)
    open-gap sub-floor within qualifiers in {none*, >=0, >=3, >=5, >=8}
      anchors: 0 = no-gap-down (existing ep_rt_gap_down mechanism), 3 = the 9M
      directional-gap floor, 5 = half the EP floor, 8 = the operator's "near it"
      ARGX neighborhood. No other thresholds will be tested.

  SEPARABILITY FEATURES at ~09:45 (all knowable at decision time): open gap;
  position in 09:30-09:45 opening range at 09:45; cumulative volume 09:30-09:45 vs
  20-session mean daily volume (RVOL proxy); extension %; ADR%; prev close vs
  20-session max close (prior structure). Winner = tailx-so-far >= 8xADR (program
  constant). Mechanical gates (D-1 floors, extension, ADV$, ATR, mcap) are replayed
  on qualifiers — a qualifier failing them never alerts regardless of floor timing.

RIGHT-CENSORING: identical to the funnel — every forward window incomplete, all
shares are FLOORS; re-read clean after 2026-09-15.

Usage: python3 scripts/probes/_490b_faded_crossed_timing.py
"""
import csv
import importlib.util
import io
import contextlib
import statistics as st
from datetime import date, time, timedelta
from pathlib import Path

HERE = Path(__file__).resolve().parent

# ── reuse the funnel's cohort + daily-bar machinery (do NOT rebuild the funnel) ──
spec = importlib.util.spec_from_file_location("funnel", HERE / "_490_delayed_cost_funnel.py")
funnel = importlib.util.module_from_spec(spec)
with contextlib.redirect_stdout(io.StringIO()):
    spec.loader.exec_module(funnel)

fc = funnel.faded_crossed_na            # the 137
daily = funnel.daily
mcap = funnel.mcap

# ── load the one-time intraday capture ───────────────────────────────────────────
bars = {}
for r in csv.DictReader(open(HERE / "_490b_intraday_bars.tsv"), delimiter="\t"):
    if not r.get("t") or r["ticker"].startswith("("):
        continue
    k = (r["ticker"], r["d"])
    bars.setdefault(k, []).append((time.fromisoformat(r["t"]), float(r["open"]),
                                   float(r["high"]), float(r["low"]), float(r["close"]),
                                   int(r["volume"])))
for v in bars.values():
    v.sort()

T0945 = time(9, 45)
BOUNDS = [("09:35", time(9, 35)), ("09:45", T0945), ("10:00", time(10, 0)),
          ("10:30", time(10, 30)), ("12:00", time(12, 0)), ("close", time(16, 0))]
GAP_FLOORS = [("none", None), (">=0", 0.0), (">=3", 3.0), (">=5", 5.0), (">=8", 8.0)]

# ── per-name intraday features ───────────────────────────────────────────────────
def enrich(c):
    tk, dd = c["ticker"], c["d"].isoformat()
    x = c["ctx"]
    pc = x["pc"]
    lvl = pc * 1.10
    rows = bars.get((tk, dd))
    c["has_bars"] = rows is not None
    if rows is None:
        return
    # cross time: first bar whose high >= prev_close*1.10 (session bars only)
    c["cross_t"] = next((t for t, o, h, lo, cl, v in rows if h >= lvl), None)
    # 09:30-09:45 opening range + 09:45 snapshot
    orb = [r for r in rows if r[0] < T0945]
    c["orb_n"] = len(orb)
    if orb:
        c["orb_hi"] = max(r[2] for r in orb)
        c["orb_lo"] = min(r[3] for r in orb)
        c["p0945"] = orb[-1][4]
        c["vol0945"] = sum(r[5] for r in orb)
        rng = c["orb_hi"] - c["orb_lo"]
        c["pos_in_orb"] = (c["p0945"] - c["orb_lo"]) / rng if rng > 0 else None
    else:
        c["orb_hi"] = c["orb_lo"] = c["p0945"] = c["vol0945"] = c["pos_in_orb"] = None
    # RVOL proxy: cumvol by 09:45 vs mean daily volume over prior 20 sessions
    drows = daily.get(tk, [])
    idx = next((i for i, r in enumerate(drows) if r[0] == c["d"]), None)
    if idx and idx >= 10:
        adv = st.mean(r[5] for r in drows[max(0, idx - 20):idx])
        c["rvol0945"] = c["vol0945"] / adv if adv > 0 and c["vol0945"] is not None else None
        prior20 = [r[4] for r in drows[max(0, idx - 20):idx]]
        c["pc_vs_20dmax"] = pc / max(prior20) if prior20 else None  # 1.0 = at 20d closing high
    else:
        c["rvol0945"] = c["pc_vs_20dmax"] = None

for c in fc:
    enrich(c)

have = [c for c in fc if c["has_bars"]]
miss = [c for c in fc if not c["has_bars"]]
crossed = [c for c in have if c.get("cross_t")]

def is_win(c):
    tx = c["ctx"]["tailx"]
    return tx is not None and tx >= 8

def tail(rows, label):
    """Delegates to the funnel's own tail_stats (simplify 2026-08-18) — this file
    already holds a live handle on that module, so a second copy of the same
    n/>=8xADR/P90/median maths was pure duplication. The funnel version also
    reports the censored count, which this one silently dropped."""
    return funnel.tail_stats([c["ctx"] for c in rows], label)

P = print
P("=" * 104)
P("#490b — faded-then-crossed timing/reachability/separability (capture 2026-08-18; all shares FLOORS)")
P("=" * 104)

P(f"\nCohort: {len(fc)} faded-then-crossed never-alerted ticker-days; intraday bars for "
  f"{len(have)} (missing {len(miss)}: {sorted(set(c['ticker'] for c in miss))})")
P(f"Confirmed crossed >=10% on session bars: {len(crossed)} of {len(have)} "
  f"(the rest crossed only per the DAILY high — sparse minute prints; kept in outcome sets, "
  f"excluded from timing)")

# ── 1. characterise: cross times x open gap ──────────────────────────────────────
P("\n" + "-" * 104)
P("1. WHEN DID THEY CROSS (first minute bar high >= prev_close*1.10)?")
buckets = [("by 09:35", time(9, 35)), ("09:35-09:45", T0945), ("09:45-10:00", time(10, 0)),
           ("10:00-10:30", time(10, 30)), ("10:30-12:00", time(12, 0)), ("after 12:00", time(16, 0))]
prev = time(0, 0)
for label, ub in buckets:
    grp = [c for c in crossed if prev <= c["cross_t"] < ub]
    gaps = [c["ctx"]["open_gap"] for c in grp]
    w = sum(1 for c in grp if is_win(c))
    if grp:
        P(f"  {label:<12} n={len(grp):>3}  med open_gap {st.median(gaps):+5.1f}%  "
          f"winners(>=8xADR so far) {w}  {sorted((c['ticker']) for c in grp if is_win(c))}")
    else:
        P(f"  {label:<12} n=  0")
    prev = ub
og = sorted(c["ctx"]["open_gap"] for c in fc)
P(f"  open-gap distribution (all 137): P10 {og[int(.1*len(og))]:+.1f}%  P25 {og[int(.25*len(og))]:+.1f}%  "
  f"med {st.median(og):+.1f}%  P75 {og[int(.75*len(og))]:+.1f}%  P90 {og[int(.9*len(og))]:+.1f}%  "
  f"opened DOWN {sum(1 for g in og if g < 0)}/{len(og)}")

# ── 2+3. reachability + primary rule ─────────────────────────────────────────────
P("\n" + "-" * 104)
P("2/3. REACHABILITY — the PRIMARY pre-registered rule: high-water >= +10% inside 09:30-09:45")
qual = [c for c in crossed if c["cross_t"] < T0945]
unreach = [c for c in crossed if c["cross_t"] >= T0945]
P(f"  qualifiers (ORB-reachable): {len(qual)} of {len(crossed)} timed crossers; "
  f"unreachable (crossed after 09:45): {len(unreach)}")
tail(qual, "REACHABLE: crossed by 09:45 (primary rule, pre-gates)")
tail(unreach, "UNREACHABLE: crossed after 09:45")

# mechanical gates replayed on qualifiers (funnel's Stage-2 logic, same thresholds)
def gate_fails(c):
    x = c["ctx"]
    why = []
    if x["pc"] is None or x["pc"] < 5:
        why.append("prevclose<$5")
    if x["pv"] is None or x["pv"] < 50_000:
        why.append("prevvol<50k")
    if x["ext_pct"] is not None and x["ext_pct"] >= 50:
        why.append(f"extended+{x['ext_pct']:.0f}%")
    if x["adv_dollar"] is None:
        why.append("adv:no-data")
    elif x["adv_dollar"] < 1_000_000:
        why.append(f"adv${x['adv_dollar']/1e6:.2f}M")
    if x["atr_pct"] is not None and x["atr_pct"] > 15:
        why.append(f"atr{x['atr_pct']:.0f}%")
    mc = mcap.get(c["ticker"])
    if mc is not None and mc < 500e6:
        why.append(f"mcap${mc/1e6:.0f}M")
    return why

for c in qual:
    c["gate_fails"] = gate_fails(c)
gated = [c for c in qual if not c["gate_fails"]]
P(f"\n  qualifiers surviving the replayed mechanical gates (D-1/ext/ADV$/ATR/mcap): "
  f"{len(gated)} of {len(qual)}   (catalyst/RVOL/top-20 NOT replayed -> upper bound)")
tail(gated, "REACHABLE + passes mechanical gates")
P("  gate fates of the class's >=8xADR winners:")
for c in crossed:
    if is_win(c):
        reach = "cross %s -> %s" % (c["cross_t"].strftime("%H:%M"),
                                    "REACHABLE" if c["cross_t"] < T0945 else "unreachable")
        P(f"    {c['ticker']} {c['d']}  open_gap {c['ctx']['open_gap']:+.1f}%  {reach}  "
          f"gates-failed {gate_fails(c) or 'NONE'}  tailx-so-far {c['ctx']['tailx']:.1f}x  "
          f"fwd {c['ctx']['fwd_n']}/20")

P("\n  survivors (reachable + gates), by tailx-so-far:")
P(f"  {'ticker':<7}{'date':<12}{'cross':<7}{'open_gap':>9}{'pos_orb':>8}{'rvol45':>7}{'tailx':>7}{'fwd':>5}")
for c in sorted(gated, key=lambda c: -(c["ctx"]["tailx"] or -9)):
    x = c["ctx"]
    P(f"  {c['ticker']:<7}{c['d'].isoformat():<12}{c['cross_t'].strftime('%H:%M'):<7}"
      f"{x['open_gap']:>+9.1f}{(c['pos_in_orb'] if c['pos_in_orb'] is not None else float('nan')):>8.2f}"
      f"{(c['rvol0945'] if c['rvol0945'] is not None else float('nan')):>7.2f}"
      f"{(x['tailx'] if x['tailx'] is not None else float('nan')):>7.2f}{x['fwd_n']:>5}")

# ── 5. sensitivity: boundary x gap floor ─────────────────────────────────────────
P("\n" + "-" * 104)
P("5. SENSITIVITY (all pre-registered cells; PRIMARY = boundary 09:45, gap floor none)")
P(f"  {'boundary':<9}" + "".join(f"{g:>22}" for g, _ in GAP_FLOORS))
for blab, bt in BOUNDS:
    cells = []
    for glab, gf in GAP_FLOORS:
        grp = [c for c in crossed if c["cross_t"] < bt
               and (gf is None or c["ctx"]["open_gap"] >= gf)]
        w = sum(1 for c in grp if is_win(c))
        cells.append(f"{w}/{len(grp)}" + (f" ({100*w/len(grp):.0f}%)" if grp else ""))
    P(f"  {blab:<9}" + "".join(f"{s:>22}" for s in cells))

# ── 4. separability at ~09:45 ────────────────────────────────────────────────────
P("\n" + "-" * 104)
P("4. SEPARABILITY at ~09:45 — do decision-time features rank the eventual winners above the class?")
feats = [("open_gap", lambda c: c["ctx"]["open_gap"]),
         ("pos_in_orb", lambda c: c.get("pos_in_orb")),
         ("rvol0945", lambda c: c.get("rvol0945")),
         ("ext_pct", lambda c: c["ctx"]["ext_pct"]),
         ("adr_pct", lambda c: c["ctx"]["adr_pct"]),
         ("pc_vs_20dmax", lambda c: c.get("pc_vs_20dmax"))]
pool = [c for c in have if c["ctx"]["tailx"] is not None]
wins = [c for c in pool if is_win(c)]
P(f"  pool: {len(pool)} with bars+outcome; winners so far: {len(wins)} "
  f"({', '.join(c['ticker'] for c in wins)})")
for name, fn in feats:
    vals = [(fn(c), is_win(c)) for c in pool if fn(c) is not None]
    xs = sorted(v for v, _ in vals)
    n = len(xs)
    wvals = [v for v, w in vals if w]
    if not wvals:
        continue
    # each winner's percentile within the class
    pct = [100 * sum(1 for x in xs if x <= v) / n for v in wvals]
    npos, nneg = len(wvals), n - len(wvals)
    auc = sum(sum(1 for v2, w2 in vals if not w2 and v2 < v1) +
              0.5 * sum(1 for v2, w2 in vals if not w2 and v2 == v1)
              for v1 in wvals) / (npos * nneg) if npos and nneg else None
    P(f"  {name:<13} class med {st.median(xs):8.2f}   winners {['%.2f' % v for v in wvals]} "
      f"-> pctile {['%.0f' % p for p in pct]}   AUC {auc:.2f}  (n+={npos})")

# ── scan-log fates: was the floor even the binding constraint? ───────────────────
P("\n" + "-" * 104)
P("SCAN-LOG FATES — did the delayed screen see these names later the same day anyway?")
scan = funnel.scanlog
seen = [c for c in fc if int(scan.get((c["ticker"], c["d"].isoformat()), {}).get("scan_n", 0) or 0) > 0]
P(f"  {len(seen)}/{len(fc)} of the class appeared in the delayed scan log later that day "
  f"(evaluated + rejected on the merits — the floor was not the only barrier)")
P("  fates of the winners and the nearest sub-8x reachable survivors (from the captured scan log;")
P("  prior-alert dates from a one-time mi_ep_alerts read, 2026-08-18):")
FATES = [
    ("ALOY", "2026-07-29", "9.8x WINNER, reachable+gates", "EP cooldown — alerted 06-01, 58d prior"),
    ("BCAR", "2026-07-29", "14.7x WINNER, reachable", "never in scan log; fails mcap $227M<$500M"),
    ("AMRC", "2026-07-30", "8.8x WINNER, passes gates", "crossed 09:49 (post-ORB); never in scan log that day; alerted 08-04 on a later move"),
    ("EROC", "2026-07-30", "7.89x near-miss, reachable+gates", "IN scan log gap 11.1% -> outside top-20 gap cap"),
    ("EROC", "2026-07-31", "7.22x near-miss, reachable+gates", "IN scan log -> top-20 cap + routine catalyst"),
    ("QUAD", "2026-07-29", "6.50x, reachable+gates", "IN scan log gap 10.0% -> top-20 cap + mcap $487M"),
    ("IESC", "2026-07-31", "reachable+gates", "IN scan log -> session_rvol_too_low + pm volume < 25k"),
]
for tk, dd, what, fate in FATES:
    P(f"    {tk:<6} {dd}  {what:<34} -> {fate}")

# ── prize arithmetic ─────────────────────────────────────────────────────────────
P("\n" + "-" * 104)
tds = sorted({r[0] for rows in daily.values() for r in rows
              if funnel.WINDOW_START <= r[0] <= funnel.DATA_END})
months = len(tds) / 21
gw = [c for c in gated if is_win(c)]
P(f"PRIZE — window {funnel.WINDOW_START}..{funnel.DATA_END} = {len(tds)} trading days = {months:.2f} months")
P(f"  reachable-and-gate-passing >=8xADR tail winners (SO FAR): {len(gw)} "
  f"-> {len(gw)/months:.1f}/month additional (FLOOR: censored; UPPER: catalyst/RVOL/rank not replayed)")
P(f"  ... and after the scan-log fates (ALOY = 60d cooldown): 0 -> 0.0/month under the CURRENT selector")
P(f"  alerted population same window: 2 winners -> 2.6/month (funnel, computed fresh today)")
P(f"  winners in the class but NOT reachable-and-gated: "
  f"{[c['ticker'] for c in crossed if is_win(c) and c not in gw]}")
