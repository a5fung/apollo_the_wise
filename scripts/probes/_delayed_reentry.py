"""Next-day / N-day re-entry — the delayed-EP shapes, measured. (2026-08-16)

Operator: "There's a few ways to do next day(s) reentry, one of them is when it
undercuts and reclaims the low of EP day or EP's close price, and there may be more
you discover. One caveat is that we'll still run into the stop out problem here,
where we place stop and do we get stopped intraday."

TRIGGERS (all computed on DAILY bars, so 'undercut and reclaim' = a day whose LOW
pierces the level and whose CLOSE recovers above it):
  T1  reclaim the EP-day LOW          (his first)
  T2  reclaim the EP-day CLOSE        (his second)
  T3  reclaim the EP-day HIGH         (discovered: the strongest form — takes out
                                       the whole EP range after a pullback)
  T4  first close above the PRIOR day's high, after at least one down day
                                       (discovered: the classic 1-2-3 continuation)
  T5  undercut the 10-day MA and close back above it
                                       (discovered: the MA-reclaim shape)

STOPS x2 (his caveat, made an axis rather than an assumption):
  S1  the trigger day's LOW           S2  the EP-day LOW
SEMANTICS x2: intraday touch  vs  close-basis

SCORING (plan's pre-registered objective — NOT mean R):
  catch rate on names that PRODUCED a >=5R opportunity, then total R.
  A miss list is printed by name, because "which real EPs did this rule cut off"
  is the question that matters.

⚠ READ-ONLY, reconstructed, daily-bar resolution (a same-day undercut-and-reclaim
that also stopped us out intraday is NOT separable at this resolution — stated, not
hidden). Horizon 60 trading days. THE LINE: measured only.
"""
from collections import defaultdict
from pathlib import Path
import _468_moderate_realized_r as M

H = Path(".").resolve()
M.COHORT, M.DAILY = H / "_468_cohort.tsv", H / "_468_daily_full.tsv"
HORIZON, MAXWAIT, PROFIT_R, FRAC = 60, 10, 2.0, 1.0 / 3.0


def sma(c, n):
    return sum(c[-n:]) / n if len(c) >= n else None


def triggers(ep, fwd, closes):
    """{name: (entry_index_in_fwd, entry_price, trigger_day_low)} — first firing only."""
    out, seen_down = {}, False
    c10 = list(closes)
    for k, lvl in (("T1 reclaim EP low", ep["l"]), ("T2 reclaim EP close", ep["c"]),
                   ("T3 reclaim EP high", ep["h"])):
        for j, d in enumerate(fwd[:MAXWAIT]):
            if d["l"] < lvl <= d["c"]:
                out[k] = (j, lvl, d["l"])
                break
    for j, d in enumerate(fwd[:MAXWAIT]):
        prev = fwd[j - 1] if j else ep
        if d["c"] < prev["c"]:
            seen_down = True
        elif seen_down and d["c"] > prev["h"]:
            out["T4 close above prior high"] = (j, prev["h"], d["l"])
            break
    for j, d in enumerate(fwd[:MAXWAIT]):
        line = sma(c10 + [x["c"] for x in fwd[:j]], 10)
        if line and d["l"] < line <= d["c"]:
            out["T5 reclaim 10d MA"] = (j, line, d["l"])
            break
    return out


def run(entry, stop, bars, closing):
    """Daily walk: 1/3 at +2R then breakeven; exit on stop (touch or close) or horizon."""
    risk = entry - stop
    if risk <= 0:
        return None
    held, banked, be = 1.0, 0.0, False
    for d in bars[:HORIZON]:
        if closing:
            if d["c"] < stop:
                return banked + held * (d["c"] - entry) / risk
        elif d["l"] <= stop:
            return banked + held * (stop - entry) / risk
        if not be and d["h"] >= entry + PROFIT_R * risk:
            banked += FRAC * PROFIT_R
            held -= FRAC
            be = True
            stop = max(stop, entry)
    return banked + held * ((bars[:HORIZON][-1]["c"] if bars[:HORIZON] else entry) - entry) / risk


rows = [r for r in M.load_cohort() if r["tier"] == "HIGH"]
daily = M.load_daily()
arms = defaultdict(list)
opportunity = {}          # name -> best possible R (the outlier set)

for r in rows:
    db = daily.get(r["ticker"], [])
    i = M.idx_of_date(db, r["alert_date"])
    if i is None or len(db) - i - 1 < HORIZON:
        continue
    ep, fwd, closes = db[i], db[i + 1:], [b["c"] for b in db[:i]]
    nm = f"{r['ticker']} {r['alert_date']}"
    peak = max((b["h"] for b in fwd[:HORIZON]), default=ep["c"])
    risk0 = ep["c"] - ep["l"]
    if risk0 > 0:
        opportunity[nm] = (peak - ep["c"]) / risk0          # R available from the EP close
    for k, (j, px, tlow) in triggers(ep, fwd, closes).items():
        for sname, st in (("S1 trigger-day low", tlow), ("S2 EP-day low", ep["l"])):
            for cl in (False, True):
                v = run(px, st, fwd[j + 1:], cl)
                if v is not None:
                    arms[f"{k} | {sname} | {'close' if cl else 'touch'}"].append((nm, v))

BIG = {n for n, v in opportunity.items() if v >= 5}
print(f"cohort with {HORIZON}d forward history: {len(opportunity)} names · "
      f"{len(BIG)} produced a >=5R opportunity from the EP close")
print(f"{'arm':<52}{'fired':>6}{'caught>=5R':>12}{'catch%':>8}{'totalR':>9}{'maxR':>8}")
best = []
for k, vals in sorted(arms.items()):
    rs = [v for _, v in vals]
    caught = {n for n, v in vals if v >= 5}
    if len(rs) < 8:
        continue
    best.append((len(caught & BIG), sum(rs), k, len(rs), caught))
for c, tot, k, n, caught in sorted(best, reverse=True)[:14]:
    print(f"{k:<52}{n:>6}{c:>12}{100.0*c/max(len(BIG),1):>7.0f}%{tot:>9.1f}"
          f"{max(v for _, v in arms[k]):>8.1f}")
if best:
    top = sorted(best, reverse=True)[0]
    print(f"\nBEST ARM: {top[2]}")
    print(f"  MISSED these >=5R names: {sorted(BIG - top[4])}")
