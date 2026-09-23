"""Backtest: catalyst-lattice trigger (b) as alerts-per-TRADING-DAY (current) vs
alerts-per-GAPPING-STOCK (supply-normalised).

READ-ONLY, $0 — replays the already-captured production series in
_alertdrop_capture_out.psv (Q5 tape breadth from mi_daily_closes, Q10 daily alert counts
from mi_ep_alerts). No prod access; prod ssh is not available from this session.

DATA HONESTY
  * alert counts: captured 2026-07-06 .. 2026-08-24.
  * 2026-08-25 = 0 alerts — NOT captured, but established: trigger (c) fired on the 25th,
    and it requires TWO consecutive zero-alert trading days (08-24 captured at 0).
  * 2026-08-26 = unknown. Not evaluated, and excluded from every window.
  * supply (stocks gapping >=10% past the D-1 universe floors): captured 07-06 .. 08-24.
    A day with no supply figure is dropped from BOTH numerator and denominator — never
    treated as zero supply.
"""
from __future__ import annotations
import collections
from datetime import date, timedelta

PSV = "_alertdrop_capture_out.psv"
GAP_MEASURES = ("gap10", "gap9", "gap9_liquid")


def _sections(path):
    cur, hdr, out = None, None, collections.defaultdict(list)
    for line in open(path):
        line = line.rstrip("\n")
        if line.startswith("==="):
            cur, hdr = line.strip("="), None
            continue
        if cur is None or not line.strip() or line.startswith("("):
            continue
        p = line.split("|~|")
        if hdr is None:
            hdr = p
            continue
        out[cur].append(dict(zip(hdr, p)))
    return out


S = _sections(PSV)
supply = {}
for r in S["Q5_TAPE_BREADTH"]:
    supply[date.fromisoformat(r["trade_date"])] = {k: int(r[k]) for k in GAP_MEASURES}

ALERTS_CAPTURED_FROM = date(2026, 7, 6)
ALERTS_CAPTURED_TO = date(2026, 8, 24)
high = collections.Counter()
allt = collections.Counter()
for r in S["Q10_ALERT_DAILY_TIER"]:
    if r["src"] != "live":
        continue
    d = date.fromisoformat(r["alert_date"])
    allt[d] += int(r["n"])
    if r["score_tier"] == "HIGH":
        high[d] += int(r["n"])

ESTABLISHED_ZERO = {date(2026, 8, 25)}     # see DATA HONESTY above
LAST_KNOWN_ALERT_DAY = date(2026, 8, 25)
HOLIDAYS = {date(2026, 7, 3)}


def is_td(d):
    return d.weekday() < 5 and d not in HOLIDAYS


def alerts_known(d):
    return (ALERTS_CAPTURED_FROM <= d <= ALERTS_CAPTURED_TO) or d in ESTABLISHED_ZERO


RECENT_DAYS, PRIOR_DAYS, FRAC = 7, 30, 0.5
FLIP = date(2026, 8, 22)
MIN_POST_FLIP = 5


def trading_days(end, n_cal):
    return [end - timedelta(days=i) for i in range(n_cal) if is_td(end - timedelta(days=i))]


def era_windows(day, flip):
    recent_all = trading_days(day, RECENT_DAYS)
    prior_all = [d for d in trading_days(day, RECENT_DAYS + PRIOR_DAYS)
                 if d not in set(recent_all)]
    ws = day - timedelta(days=RECENT_DAYS + PRIOR_DAYS - 1)
    if flip <= ws:
        return recent_all, prior_all, False
    return ([d for d in recent_all if d >= flip],
            [d for d in prior_all if d < flip], True)


def eval_day(day, measure, scoped_era, alert_override=None, supply_override=None):
    """measure=None -> the CURRENT per-trading-day form. Returns (fired, detail-dict)."""
    A = alert_override if alert_override is not None else high
    SUP = supply_override if supply_override is not None else supply
    flip = FLIP if scoped_era else date(1900, 1, 1)
    recent, prior, scoped = era_windows(day, flip)
    recent = [d for d in recent if alerts_known(d)]
    prior = [d for d in prior if alerts_known(d)]
    if scoped and len(recent) < MIN_POST_FLIP:
        return None, {"why": "suppressed: partial post-flip window"}
    if measure is not None:
        recent = [d for d in recent if d in SUP]
        prior = [d for d in prior if d in SUP]
    if not recent or not prior:
        return None, {"why": "suppressed: empty window"}
    ra = sum(A.get(d, 0) for d in recent)
    pa = sum(A.get(d, 0) for d in prior)
    rd = len(recent) if measure is None else sum(SUP[d][measure] for d in recent)
    pd_ = len(prior) if measure is None else sum(SUP[d][measure] for d in prior)
    if rd == 0 or pd_ == 0:
        return None, {"why": "suppressed: zero denominator"}
    rr, pr = ra / rd, pa / pd_
    fired = bool(pr > 0 and rr < FRAC * pr)
    # the margin that matters: how many HIGH alerts the recent window could have had and
    # still fired (strictly-less-than the bar).
    bar = FRAC * pr * rd
    import math
    max_firing_alerts = math.ceil(bar) - 1 if bar == int(bar) else math.floor(bar)
    return fired, {"ra": ra, "pa": pa, "rd": rd, "pd": pd_, "rr": rr, "pr": pr,
                   "drop": 0.0 if pr == 0 else 100 * (1 - rr / pr),
                   "n_rec": len(recent), "n_pri": len(prior),
                   "max_firing_alerts": max_firing_alerts,
                   "alerts_from_firing": ra - max_firing_alerts}


def run(label, measure, scoped_era, days, **kw):
    print(f"\n=== {label} ===")
    fires = []
    for d in days:
        fired, x = eval_day(d, measure, scoped_era, **kw)
        if fired is None:
            print(f"{d}  supp  {x['why']}")
            continue
        mark = "FIRE" if fired else "----"
        unit = "/td" if measure is None else "/gap"
        print(f"{d}  {mark}  recent {x['ra']}/{x['rd']}={x['rr']:.4f}{unit}  "
              f"prior {x['pa']}/{x['pd']}={x['pr']:.4f}{unit}  drop {x['drop']:.0f}%  "
              f"(fires at <= {x['max_firing_alerts']} alerts; had {x['ra']} — "
              f"{x['alerts_from_firing']} away)  td {x['n_rec']}/{x['n_pri']}")
        if fired:
            fires.append(d)
    print(f"  -> fired {len(fires)} day(s): {[str(x) for x in fires]}")
    return fires


days = [d for d in (date(2026, 7, 30) + timedelta(days=i) for i in range(30))
        if is_td(d) and d <= LAST_KNOWN_ALERT_DAY]
print("evaluation days (07-30 .. last day with known alert counts):", [str(d) for d in days])
print("2026-08-26 is NOT evaluated — alert count unknown, prod ssh unavailable.\n")

print("#" * 78)
print("# A. COUNTERFACTUAL REPLAY — era scoping OFF, so every day is actually judged.")
print("#    This is the test of the STATISTIC. (In prod, era scoping + the 5-post-flip-day")
print("#    floor keep trigger (b) suppressed until 2026-08-28 whichever statistic it uses.)")
print("#" * 78)
res = {}
res[None] = run("CURRENT — alerts per trading day", None, False, days)
for m in GAP_MEASURES:
    res[m] = run(f"CONVERSION — alerts per stock gapping ({m})", m, False, days)

print("\n" + "#" * 78)
print("# B. AS DEPLOYED — era-scoped (both statistics), for completeness.")
print("#" * 78)
run("CURRENT — era-scoped", None, True, days)
run("CONVERSION gap10 — era-scoped", "gap10", True, days)

print("\n" + "#" * 78)
print("# C. POSITIVE CONTROL — the REAL thin tape of 08-18..08-24, but our funnel breaks.")
print("#    Same supply, HIGH alerts cut to a third. Must FIRE, or the change is a mute.")
print("#" * 78)
broken = collections.Counter(high)
for d in (date(2026, 8, 18), date(2026, 8, 19), date(2026, 8, 20), date(2026, 8, 21)):
    broken[d] = 0
for m in GAP_MEASURES:
    f, x = eval_day(date(2026, 8, 24), m, False, alert_override=broken)
    print(f"  {m}: fired={f}  recent {x['ra']}/{x['rd']}  prior {x['pa']}/{x['pd']}  "
          f"drop {x['drop']:.0f}%")
f, x = eval_day(date(2026, 8, 24), None, False, alert_override=broken)
print(f"  CURRENT: fired={f}  drop {x['drop']:.0f}%  (fires too — but it also fires "
      f"on the untouched real series, which is the problem)")

print("\n" + "#" * 78)
print("# D. 08-24 SENSITIVITY — how close the conversion form came to firing.")
print("#" * 78)
for m in GAP_MEASURES:
    f, x = eval_day(date(2026, 8, 24), m, False)
    print(f"  {m}: ratio {x['rr']/x['pr']:.3f} vs the 0.500 bar; fires at "
          f"<= {x['max_firing_alerts']} HIGH alerts in the recent week, actual {x['ra']}")

print("\n=== daily series (HIGH alerts | all-tier alerts | supply measures) ===")
for d in sorted(set(list(supply) + [k for k in high]) | ESTABLISHED_ZERO):
    if d < date(2026, 7, 6):
        continue
    s = supply.get(d, {})
    print(f"{d}  high={high.get(d,0):2d} all={allt.get(d,0):2d} "
          f"gap10={s.get('gap10','?'):>4} gap9={s.get('gap9','?'):>4} "
          f"gap9liq={s.get('gap9_liquid','?'):>4}"
          + ("   [alerts established, not captured]" if d in ESTABLISHED_ZERO else ""))

print("\n" + "#" * 78)
print("# E. FORWARD LOOK — 2026-08-28 is the first day the DEPLOYED (era-scoped) trigger (b)")
print("#    can speak at all: 5 post-flip trading days. What would it need to stay silent?")
print("#" * 78)
_d28 = date(2026, 8, 28)
_recent28 = [d for d in trading_days(_d28, RECENT_DAYS) if d >= FLIP]
_prior28 = [d for d in trading_days(_d28, RECENT_DAYS + PRIOR_DAYS)
            if d not in set(trading_days(_d28, RECENT_DAYS)) and d < FLIP]
_pa = sum(high.get(d, 0) for d in _prior28)
_ps = sum(supply[d]["gap10"] for d in _prior28 if d in supply)
_prate = _pa / _ps
print(f"  prior window {_prior28[-1]}..{_prior28[0]}: {_pa} HIGH alerts / {_ps} gapping "
      f"stocks = {100*_prate:.1f} per 100")
print(f"  recent window (post-flip): {[str(d) for d in _recent28]}")
print(f"  08-24 = 0 alerts (captured), 08-25 = 0 alerts (established). 08-26/27/28 unknown.")
for assumed in (15, 20, 25, 30):
    rs = assumed * 5
    bar = FRAC * _prate * rs
    import math
    need = math.floor(bar) + 1
    print(f"    if the tape offers ~{assumed} gapping stocks/day ({rs} over the 5 days): "
          f"it FIRES unless we produce at least {need} HIGH alerts across 08-26..08-28")

print("\n" + "#" * 78)
print("# F. THE PRIOR WINDOW IS STILL SPIKE-INFLATED — on the CONVERSION axis this time.")
print("#    Supply-normalising removes the supply half of the early-August spike; the")
print("#    conversion half stays inside the 30-day baseline (collapse analysis Result 4:")
print("#    the burst weeks were elevated on BOTH supply and conversion).")
print("#" * 78)


def _rate(ds):
    a = sum(high.get(d, 0) for d in ds)
    s = sum(supply[d]["gap10"] for d in ds if d in supply)
    return a, s, (100.0 * a / s if s else 0.0)


_july = [d for d in sorted(supply) if date(2026, 7, 6) <= d <= date(2026, 7, 24)]
_ja, _js, _jr = _rate(_july)
_pa2, _ps2, _pr2 = _rate(_prior28)
print(f"  July baseline 07-06..07-24 : {_ja} HIGH / {_js} gapping = {_jr:.1f} per 100")
print(f"  prior window for 08-28     : {_pa2} HIGH / {_ps2} gapping = {_pr2:.1f} per 100")
print(f"  ratio july/prior = {_jr/_pr2:.3f} against the 0.500 bar -> a return to EXACTLY "
      f"July-normal conversion clears it by only {100*(_jr/_pr2-0.5):.1f} points")
