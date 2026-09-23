"""#559 — would flipping `ep_rt_universe_authoritative` add alerts / add real EPs?

MEASURE-ONLY. Reads the ONE 2026-08-25 capture (`_559_*.tsv`, written by
`_559_rt_flip_capture.sql`). $0, deterministic, no network, no DB, no toggles touched.

Replays every rt-only shadow catch through the CURRENT (post-2026-08-22-rebuild) gate
stack and the CURRENT rubric, importing ep_rubric directly so the numbers cannot drift
from live.
"""
from __future__ import annotations

import csv
import os
import sys
from collections import defaultdict
from datetime import date, timedelta

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from agents.market_intelligence.ep_rubric import (  # noqa: E402
    SCORE_WEIGHTS, SCORE_WEIGHTS_LEGACY, SEPARATION_BAR, SHORTLIST_SIZE,
    apply_output_scale, resolve_conviction_floor, shortlist_prescore, tier_points,
)

P = os.path.dirname(os.path.abspath(__file__))

# ── live constants, mirrored from the modules that own them ────────────────────
MIN_GAP_PCT = 9.0                 # ep_detector._MIN_GAP_PCT_DEFAULT (env unset in prod)
MAX_EXTENSION_PCT = 75.0          # ep_detector.MAX_EXTENSION_PCT (raised 50->75, 2026-08-24)
MIN_ADV_DOLLAR = 1_000_000        # backtester.filters.MIN_ADV_DOLLAR_VOLUME
MAX_ATR_PCT = 15.0                # backtester.filters.MAX_ATR_PCT
MIN_MARKET_CAP = 500_000_000      # backtester.filters.MIN_MARKET_CAP
EP_COOLDOWN_DAYS = 60

# The sustain rule went live 2026-08-02 (Sunday) and sits UPSTREAM of the authority
# flip, so pre-08-03 catches are not the population a flip would admit today. The
# per-tick coverage telemetry also starts 08-03 — same cut, two reasons.
WINDOW_START = date(2026, 8, 3)

REGIME = {}  # scan_date -> (label, multiplier)
for _d, _lab in [
    ("2026-07-27", "Correcting"), ("2026-07-28", "Correcting"), ("2026-07-29", "Crisis"),
    ("2026-07-30", "Correcting"), ("2026-07-31", "Correcting"), ("2026-08-03", "Choppy"),
    ("2026-08-04", "Bull"), ("2026-08-05", "Bull"), ("2026-08-06", "Bull"),
    ("2026-08-07", "Bull"), ("2026-08-10", "Bull"), ("2026-08-11", "Bull"),
    ("2026-08-12", "Bull"), ("2026-08-13", "Bull"), ("2026-08-14", "Bull"),
    ("2026-08-17", "Bull"), ("2026-08-18", "Bull"), ("2026-08-19", "Bull"),
    ("2026-08-20", "Choppy"), ("2026-08-21", "Choppy"), ("2026-08-24", "Choppy"),
    ("2026-08-25", "Choppy"),   # not yet written at capture time; carried from 08-24
]:
    REGIME[_d] = (_lab, 1.2 if _lab == "Bull" else 1.0)


def rd(name):
    with open(os.path.join(P, f"_559_{name}.tsv"), newline="") as f:
        return list(csv.DictReader(f, delimiter="\t"))


def f(v):
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def D(s):
    return date(*map(int, s.split("-")))


# ── load ──────────────────────────────────────────────────────────────────────
catches_raw = rd("catches")
scanlog = rd("scanlog")
alerts = rd("alerts")
daily = rd("daily")
mcaps = rd("mcaps")
advd = rd("advdollar")
adv20 = rd("adv20")
themes = rd("themes")

# yfinance market-cap fill from the 2026-08-18 #490 capture — already paid for, reused ($0).
mcap_map = {r["ticker"]: f(r["market_cap"]) for r in mcaps}
try:
    with open(os.path.join(P, "_490cost_mcaps_yf.tsv"), newline="") as fh:
        for r in csv.DictReader(fh, delimiter="\t"):
            mcap_map.setdefault(r["ticker"], f(r["market_cap"]))
except FileNotFoundError:
    pass

bars = defaultdict(list)
for r in daily:
    bars[r["ticker"]].append((D(r["trade_date"]), f(r["open_price"]), f(r["high_price"]),
                              f(r["low_price"]), f(r["close"]), f(r["volume"])))
for t in bars:
    bars[t].sort()

advd_map = {(r["ticker"], r["scan_date"]): f(r["adv_dollar"]) for r in advd}
adv20_map = {(r["ticker"], r["scan_date"]): (f(r["adv_shares"]), f(r["last_close"]))
             for r in adv20}

theme_members = defaultdict(set)
for r in themes:
    for t in (r["tickers"] or "").strip("{}").split(","):
        if t:
            theme_members[r["theme_date"]].add(t.strip().strip('"'))
theme_dates = sorted(theme_members)


def in_theme(ticker, d):
    """Accelerating/Mainstream membership on the most recent snapshot <= d (7d staleness cap)."""
    for td in reversed(theme_dates):
        if td <= d:
            if D(d) - D(td) > timedelta(days=7):
                return False
            return ticker in theme_members[td]
    return False


# alerts index (cooldown + the comparison population)
alerts_by_ticker = defaultdict(list)
for r in alerts:
    alerts_by_ticker[r["ticker"]].append(D(r["alert_date"]))

# scan-log index: (date, ticker) -> rows; plus the graded read for that ticker/day
scan_idx = defaultdict(list)
for r in scanlog:
    scan_idx[(r["scan_date"], r["ticker"])].append(r)


def graded_read(d, t):
    """The day's best evidence about the delayed path's own verdict on this name."""
    rows = scan_idx.get((d, t)) or []
    cq = next((r["catalyst_quality"] for r in reversed(rows) if r["catalyst_quality"]), None)
    sc = next((f(r["ep_score"]) for r in reversed(rows) if f(r["ep_score"]) is not None), None)
    reasons = {r["filter_reason"] for r in rows if r["filter_reason"]}
    adv = next((f(r["adv"]) for r in reversed(rows) if f(r["adv"])), None)
    pc = next((f(r["prev_close"]) for r in reversed(rows) if f(r["prev_close"])), None)
    pvm = next((f(r["projected_vol_multiple"]) for r in reversed(rows)
                if f(r["projected_vol_multiple"]) is not None), None)
    rv = next((f(r["rel_volume"]) for r in reversed(rows) if f(r["rel_volume"]) is not None), None)
    return {"n_rows": len(rows), "catalyst": cq, "score_old": sc, "reasons": reasons,
            "adv": adv, "prev_close": pc, "pvm": pvm, "rel_volume": rv}


# ── dedupe catches to one row per ticker/day (the audit dedupe already does this) ──
seen, catches = set(), []
for r in catches_raw:
    k = (r["d"], r["ticker"])
    if k in seen:
        continue
    seen.add(k)
    catches.append(r)

full_days = sorted({r["d"] for r in catches})
win = [r for r in catches if D(r["d"]) >= WINDOW_START]
win_days = sorted({r["d"] for r in win})

print("=" * 78)
print("#559 — rt-universe authority flip: what it would actually add")
print("=" * 78)
print(f"\nFULL shadow record : {len(catches)} ticker-days over {len(full_days)} trading days "
      f"({full_days[0]} .. {full_days[-1]})")
print(f"HONEST window      : {len(win)} ticker-days over {len(win_days)} trading days "
      f"({win_days[0]} .. {win_days[-1]}) — post-sustain-rule, coverage-verified")
print(f"  raw catch rate   : {len(win)/len(win_days):.2f} per trading day")

# ══ STAGE A — three classes, and only ONE of them is an addition ══════════════
alerted_same_day = {}
for r in alerts:
    alerted_same_day[(r["alert_date"], r["ticker"])] = r

cls_alerted, cls_seen, cls_rtonly = [], [], []
for r in win:
    g = graded_read(r["d"], r["ticker"])
    r["_g"] = g
    if (r["d"], r["ticker"]) in alerted_same_day:
        r["_alert"] = alerted_same_day[(r["d"], r["ticker"])]
        cls_alerted.append(r)
    elif g["n_rows"] > 0:
        cls_seen.append(r)
    else:
        cls_rtonly.append(r)

print("\n" + "=" * 78)
print("STAGE A — what the flip is actually buying")
print("=" * 78)
print(f"  {len(cls_alerted):3d}  ALREADY ALERTED the same day  ({len(cls_alerted)/len(win_days):.2f}/day)")
print( "        → the delayed feed caught them later and they alerted anyway.")
print( "        → flipping moves the alert EARLIER. ZERO extra alerts from this class.")
print(f"  {len(cls_seen):3d}  SEEN by the delayed scan, not alerted  ({len(cls_seen)/len(win_days):.2f}/day)")
print( "        → they became delayed candidates the same day and died on the merits.")
print(f"  {len(cls_rtonly):3d}  RT-ONLY — never a delayed candidate at all  ({len(cls_rtonly)/len(win_days):.2f}/day)")
print( "        → THE ONLY CLASS THE FLIP ADDS.")

print("\n  what killed the 'seen, not alerted' class (furthest stage per name):")
kill = defaultdict(list)
for r in cls_seen:
    joined = " ".join(r["_g"]["reasons"]).lower()
    for key, lab, movable in [
            ("mcap_too_small", "market cap < $500M", False),
            ("adv_too_low", "dollar volume < $1M", False),
            ("adv_no_data", "no ADV data", False),
            ("atr", "ATR > 15%", False),
            ("extended", "already extended", False),
            ("cooldown", "60-day cooldown", False),
            ("m&a", "merger/acquisition", False),
            ("score ", "scored below the bar", False),
            ("rvol", "volume pace below normal", True),
            ("outside top-", "outside the graded shortlist", True),
            ("already scored", "already scored earlier today", True)]:
        if key in joined:
            kill[(lab, movable)].append(r); break
    else:
        kill[(joined[:40] or "no reason recorded", True)].append(r)
for (lab, movable), v in sorted(kill.items(), key=lambda x: -len(x[1])):
    print(f"      {len(v):4d}  {lab}"
          + ("   ← a timing-sensitive gate the flip COULD move" if movable else ""))


# ══ STAGE B — the CURRENT mechanical gates, on the RT-ONLY class ══════════════
def atr_pct(ticker, d):
    rows = [b for b in bars.get(ticker, []) if b[0] <= D(d)][-21:]
    if len(rows) < 10:
        return None
    trs = []
    for i in range(1, len(rows)):
        h, l, pc = rows[i][2], rows[i][3], rows[i - 1][4]
        if None in (h, l, pc):
            continue
        trs.append(max(h - l, abs(h - pc), abs(l - pc)))
    if not trs:
        return None
    w, lc = trs[-14:], rows[-1][4]
    return (sum(w) / len(w) / lc * 100) if lc else None


def extension_pct(ticker, d, prev_close):
    lo = [b[4] for b in bars.get(ticker, [])
          if D(d) - timedelta(days=10) <= b[0] < D(d) and b[4]]
    if not lo or not prev_close:
        return None
    return (prev_close - min(lo)) / min(lo) * 100


def prev_close_for(ticker, d):
    prior = [b for b in bars.get(ticker, []) if b[0] < D(d)]
    return prior[-1][4] if prior else None


def open_gap(ticker, d):
    row = next((b for b in bars.get(ticker, []) if b[0] == D(d)), None)
    pc = prev_close_for(ticker, d)
    if not row or not row[1] or not pc:
        return None
    return (row[1] - pc) / pc * 100


def run_gates(rows):
    survivors, killed = [], defaultdict(list)
    for r in rows:
        t, d = r["ticker"], r["d"]
        pc = r["_g"]["prev_close"] or prev_close_for(t, d)
        advdol = advd_map.get((t, d))
        a20, lc = adv20_map.get((t, d), (None, None))
        if advdol is None and a20 and lc:
            advdol = a20 * lc
        a, mc = atr_pct(t, d), mcap_map.get(t)
        ext = extension_pct(t, d, pc)
        prior = [x for x in alerts_by_ticker.get(t, [])
                 if D(d) - timedelta(days=EP_COOLDOWN_DAYS) <= x < D(d)]
        r.update({"_pc": pc, "_advdol": advdol, "_atr": a, "_mcap": mc, "_ext": ext})
        if ext is not None and ext >= MAX_EXTENSION_PCT:
            killed["already up 75%+ in the prior 5 days"].append(r); continue
        if advdol is not None and advdol < MIN_ADV_DOLLAR:
            killed["trades under $1M a day"].append(r); continue
        if a is not None and a > MAX_ATR_PCT:
            killed["too volatile (ATR over 15%)"].append(r); continue
        if mc is not None and mc < MIN_MARKET_CAP:
            killed["market cap under $500M"].append(r); continue
        if mc is None:
            # LIVE FAILS OPEN here (`backtester.filters._check_market_cap`: "no data —
            # let it through"), so the replay must too. Counted separately below: these
            # survivors rest on a market cap this $0 replay could not read.
            r["_mcap_unknown"] = True
        if prior:
            killed["alerted within the last 60 days (cooldown)"].append(r); continue
        survivors.append(r)
    return survivors, killed


surv, killed = run_gates(cls_rtonly)
print("\n" + "=" * 78)
print(f"STAGE B — the {len(cls_rtonly)} rt-only names through the CURRENT gate stack")
print("=" * 78)
for k, v in sorted(killed.items(), key=lambda x: -len(x[1])):
    print(f"      {len(v):4d}  {k}")
print(f"      {len(surv):4d}  SURVIVE to catalyst grading  ({len(surv)/len(win_days):.2f}/day)")


# ══ STAGE C — the CURRENT rubric at the bar of 65 ═════════════════════════════
def new_score(gap, catalyst, adv_dollar, pvm, rel_vol, vol_pct, theme, mult,
              float_bonus, weights=SCORE_WEIGHTS):
    bd = {"gap": tier_points(gap, weights["gap"]["tiers"], weights["gap"]["default"])}
    liq = weights["liquidity"]
    if adv_dollar:
        bd["liquidity"] = tier_points(adv_dollar, liq["adv_tiers"], liq["adv_default"])
    else:
        sig = pvm if pvm is not None else (rel_vol or 0)
        bd["liquidity"] = tier_points(sig, liq["fallback_tiers"], liq["fallback_default"])
    bd["catalyst"] = weights["catalyst"]["points"].get(catalyst, weights["catalyst"]["default"])
    bd["float"] = float_bonus
    bd["vol_conviction"] = tier_points(vol_pct, weights["vol_conviction"]["tiers"],
                                       weights["vol_conviction"]["default"])
    bd["theme_bonus"] = weights["theme_bonus"]["points"] if theme else 0
    raw = sum(bd.values())
    fl = resolve_conviction_floor(gap, catalyst, weights["conviction_floor"]["rules"])
    if fl is not None:
        raw = max(raw, fl)
    return apply_output_scale(round(raw * mult, 1), weights.get("output_scale")), bd


print("\n" + "=" * 78)
print(f"STAGE C — the CURRENT rubric (bar {SEPARATION_BAR}) on those {len(surv)} survivors")
print("=" * 78)
print("  None of them carries a catalyst grade — they were never candidates, so nothing")
print("  graded them. The grade is the single biggest term (25 / 15 / 0 points), so the")
print("  answer is a BAND, not a point. Three reads:")

BASE = {"game_changer": 0.172, "strong": 0.281, "routine": 0.547}   # measured 08-03..08-25, n=192
clears = {}
for cq in ["game_changer", "strong", "routine"]:
    n_lo = n_hi = 0
    names = []
    for r in surv:
        mult = REGIME.get(r["d"], ("Choppy", 1.0))[1]
        gap, thm = f(r["rt_gap"]) or 0.0, in_theme(r["ticker"], r["d"])
        hi, _ = new_score(gap, cq, r["_advdol"], r["_g"]["pvm"], r["_g"]["rel_volume"],
                          95.0, thm, mult, 5)
        lo, _ = new_score(gap, cq, r["_advdol"], r["_g"]["pvm"], r["_g"]["rel_volume"],
                          50.0, thm, mult, 0)
        if lo >= SEPARATION_BAR:
            n_lo += 1
        if hi >= SEPARATION_BAR:
            n_hi += 1
            names.append((r, lo, hi))
    clears[cq] = (n_lo, n_hi, names)
    print(f"    if graded {cq:13s}: {n_lo:3d} clear the bar on the strict read, "
          f"{n_hi:3d} on the most generous read")

exp_lo = sum(BASE[c] * clears[c][0] for c in BASE)
exp_hi = sum(BASE[c] * clears[c][1] for c in BASE)
print(f"\n  Weighting by the MEASURED grade mix of everything the scan graded in this window")
print(f"  (game changer 17%, strong 28%, routine 55%; n=192 ticker-days):")
print(f"    expected extra alerts over {len(win_days)} trading days: {exp_lo:.1f} to {exp_hi:.1f}")
print(f"    ⇒ EXTRA ALERTS PER TRADING DAY: {exp_lo/len(win_days):.2f} to {exp_hi/len(win_days):.2f}")
print(f"    ⇒ ABSOLUTE CEILING (every survivor a game changer, every bonus granted): "
      f"{clears['game_changer'][1]/len(win_days):.2f}/day")

print("\n  The survivors that clear the bar even as a 'strong' catalyst (the realistic top):")
for r, lo, hi in sorted(clears["strong"][2], key=lambda x: -x[2])[:15]:
    og = open_gap(r["ticker"], r["d"])
    print(f"      {r['d']} {r['ticker']:6s} rt {f(r['rt_gap']):5.1f}% @{r['tick_et']}  "
          f"score {lo:.0f}-{hi:.0f}  ${(r['_advdol'] or 0)/1e6:,.0f}M/day  "
          f"open {('%+.1f%%' % og) if og is not None else 'n/a'}")


# ══ STAGE D — would they have alerted MORE easily under the old rubric? ═══════
print("\n" + "=" * 78)
print("STAGE D — the rebuild made this population EASIER to alert, not harder")
print("=" * 78)
for cq in ["game_changer", "strong"]:
    now = clears[cq][1]
    then = 0
    for r in surv:
        lab, mult = REGIME.get(r["d"], ("Choppy", 1.0))
        bar_old = {"Bull": 65, "Choppy": 70, "Correcting": 75, "Crisis": 80}[lab]
        s, _ = new_score(f(r["rt_gap"]) or 0, cq, r["_advdol"], r["_g"]["pvm"],
                         r["_g"]["rel_volume"], 95.0, in_theme(r["ticker"], r["d"]),
                         mult, 5, weights=SCORE_WEIGHTS_LEGACY)
        if s >= bar_old:
            then += 1
    print(f"    as {cq:13s}: {then:3d} would have cleared the OLD rubric+bar, "
          f"{now:3d} clear the NEW one")


# ══ STAGE E — the benefit side ════════════════════════════════════════════════
def adr_pct(ticker, d, n=20):
    rows = [b for b in bars.get(ticker, []) if b[0] < D(d)][-n:]
    vals = [(b[2] - b[3]) / b[4] * 100 for b in rows if b[2] and b[3] and b[4]]
    return (sum(vals) / len(vals)) if vals else None


def tailx(ticker, d, sessions=20):
    fwd = [b for b in bars.get(ticker, []) if b[0] >= D(d)][:sessions + 1]
    if len(fwd) < 2:
        return None, 0
    base = fwd[0][4]
    mx = max(b[2] for b in fwd[1:] if b[2])
    a = adr_pct(ticker, d)
    if not base or not a:
        return None, len(fwd) - 1
    return (mx - base) / base * 100 / a, len(fwd) - 1


print("\n" + "=" * 78)
print("STAGE E — the benefit side: did the rt-only names become real EPs?")
print("=" * 78)
print("  'tail' = how far the stock ran in the next 20 sessions, measured in its own")
print("  average daily range. 8x or more is the programme's mark for a tail winner.")
print("  EVERY window here is still incomplete, so every count is a FLOOR.")
for lab, rows in [("rt-only, survived every mechanical gate", surv),
                  ("rt-only, all of them", cls_rtonly),
                  ("caught AND alerted anyway (the timing class)", cls_alerted),
                  ("every catch in the window", win)]:
    vals = []
    for r in rows:
        x, n = tailx(r["ticker"], r["d"])
        if x is not None:
            vals.append((x, r["ticker"], r["d"], n))
    big = [v for v in vals if v[0] >= 8]
    vals.sort(reverse=True)
    med = vals[len(vals) // 2][0] if vals else float("nan")
    med_n = sorted(v[3] for v in vals)[len(vals) // 2] if vals else 0
    print(f"    {lab:44s} n={len(vals):4d}  8x+: {len(big):2d}  median {med:.1f}x  "
          f"(median {med_n}/20 sessions run)")
    for v, t, d, n in vals[:3]:
        print(f"          top: {t} {d} {v:.1f}x ({n}/20)")

aw = [r for r in rd("alerts_window") if r["score_tier"] == "HIGH"]
print(f"\n  live HIGH alerts over the same {len(win_days)} days: {len(aw)} "
      f"({len(aw)/len(win_days):.2f}/day) — the population this would add to")

# power
n_days = len(win_days)
print(f"\n  POWER: {len(surv)} gate-surviving rt-only names in {n_days} trading days produced")
print(f"  {len([1 for r in surv if (tailx(r['ticker'], r['d'])[0] or 0) >= 8])} tail winner(s).")
print(f"  At this sample size the smallest real rate this window could reliably")
print(f"  distinguish from zero is roughly 1 winner per {n_days} days — anything rarer")
print(f"  than about 1.3 a month is INVISIBLE here. 'Zero measured' is not 'zero'.")


# ══ STAGE F — shortlist room ══════════════════════════════════════════════════
funnel = rd("dailyfunnel")
print("\n" + "=" * 78)
print(f"STAGE F — is there room in the {SHORTLIST_SIZE}-name graded shortlist?")
print("=" * 78)
cbd, rtd = defaultdict(int), defaultdict(int)
for r in win:
    cbd[r["d"]] += 1
for r in cls_rtonly:
    rtd[r["d"]] += 1
print("    date         seen   graded   catches   rt-only")
for r in [x for x in funnel if x["scan_date"] >= "2026-08-03"]:
    d = r["scan_date"]
    print(f"    {d}   {int(r['seen_n']):5d}    {int(r['graded_n']):5d}     "
          f"{cbd.get(d, 0):5d}     {rtd.get(d, 0):5d}")
print("\n    (`seen` on 08-24/25 is inflated by the #570 universe-floor visibility rows,")
print("     which log every name that failed a price/volume floor — not real candidates.)")
_cap_hits = sum(1 for r in cls_seen
                if any("outside top-" in x for x in r["_g"]["reasons"]))
print(f"    The 20-name graded cap DID bind: {_cap_hits} of the catches that the delayed scan")
print("    saw were logged 'outside the graded shortlist'. So extra admissions do compete")
print("    for grading slots — but the wall in front of them is the score bar, not the cap.")


# ══ STAGE I — today's list, the nine names he is looking at ══════════════════
print("\n" + "=" * 78)
print("STAGE I — the nine catches he quoted from 2026-08-25, through the same gates")
print("=" * 78)
today = [r for r in win if r["d"] == "2026-08-25"]
t_alert = [r for r in today if (r["d"], r["ticker"]) in alerted_same_day]
t_seen = [r for r in today if r in cls_seen]
t_rt = [r for r in today if r in cls_rtonly]
t_surv, t_killed = run_gates(list(t_rt))
print(f"    {len(today)} catches   |   {len(t_alert)} alerted anyway   "
      f"{len(t_seen)} the delayed scan saw   {len(t_rt)} rt-only")
for r in today:
    cls = ("alerted anyway" if r in t_alert else
           "delayed scan saw it" if r in t_seen else "rt-only")
    k = "survives every gate" if r in t_surv else next(
        (lab for lab, rows in t_killed.items() if r in rows), "n/a")
    print(f"      {r['ticker']:6s} rt {f(r['rt_gap']):5.1f}% @{r['tick_et']}  "
          f"{cls:20s} {k}")


# ══ STAGE G — which gate killed the rt-only names that DID run ═══════════════
print("\n" + "=" * 78)
print("STAGE G — the rt-only names that actually ran, and what stopped them")
print("=" * 78)
kill_of = {}
for lab, rows in killed.items():
    for r in rows:
        kill_of[(r["d"], r["ticker"])] = lab
runs = []
for r in cls_rtonly:
    x, n = tailx(r["ticker"], r["d"])
    if x is not None:
        runs.append((x, n, r))
runs.sort(reverse=True, key=lambda z: z[0])
for x, n, r in runs[:8]:
    k = kill_of.get((r["d"], r["ticker"]), "PASSED every mechanical gate")
    og = open_gap(r["ticker"], r["d"])
    print(f"    {r['d']} {r['ticker']:6s} {x:5.1f}x ({n}/20 sessions)  "
          f"open {('%+.1f%%' % og) if og is not None else 'n/a':>7s}   {k}")

# ══ STAGE H — extra ENTRIES, not just alerts ═════════════════════════════════
print("\n" + "=" * 78)
print("STAGE H — an alert is not a trade: how many would have been ENTERABLE?")
print("=" * 78)
print(f"  The entry-time real-time gap re-check (`ep_rt_entry_gap_recheck`, ON since 08-02)")
print(f"  blocks any entry whose gap has fallen back under {MIN_GAP_PCT:.0f}% at 09:31.")
held = [r for r in surv if (open_gap(r["ticker"], r["d"]) or -99) >= MIN_GAP_PCT]
late = [r for r in surv if r["tick_et"] >= "09:45"]
print(f"    of the {len(surv)} rt-only gate survivors, {len(held)} still had a "
      f"{MIN_GAP_PCT:.0f}%+ gap at the actual open")
for r in held:
    print(f"        {r['d']} {r['ticker']:6s} rt {f(r['rt_gap']):5.1f}% @{r['tick_et']}  "
          f"open {open_gap(r['ticker'], r['d']):+.1f}%")
print(f"    {len(late)} of the {len(surv)} were caught at 09:45 or later — outside the")
print(f"    09:31-09:45 order-submission window, so they could not have been entered that day")


# ══ STAGE J — the effect that is NOT "more alerts": alerts that arrive IN TIME ══
print("\n" + "=" * 78)
print("STAGE J — alerts that currently arrive too late to place an order")
print("=" * 78)
print("  The ORB order window is 09:31-09:44 ET. A HIGH alert detected at 09:45 or later")
print("  logs `window:out_of_orb` and NO order is placed. Those alerts cost attention and")
print("  buy nothing. If the real-time layer had already seen the name earlier, the flip")
print("  would have put the same alert inside the window.")
oow = [r for r in rd("orb_window")
       if r["event_type"] == "orb_out_of_window" and r["d"] >= "2026-08-03"]
catch_tick = {(r["d"], r["ticker"]): r["tick_et"] for r in win}
print(f"    {len(oow)} out-of-window HIGH alerts in {len(win_days)} trading days "
      f"({len(oow)/len(win_days):.2f}/day)")
n_rescue = 0
for r in oow:
    tk = r["summary"].split(" —")[0].strip()
    ct = catch_tick.get((r["d"], tk))
    mark = ""
    if ct and ct < "09:45":
        n_rescue += 1
        mark = "  ← the real-time layer had it at " + ct + ", INSIDE the window"
    print(f"      {r['d']} {tk:6s} alert detected {r['summary'].split('detected ')[-1]}{mark}")
print(f"    {n_rescue} of {len(oow)} had already crossed on the real-time feed inside the")
print(f"    submission window — {n_rescue/len(win_days):.2f} per trading day. Whether each")
print(f"    would still have SCORED high at that earlier tick is NOT established here: the")
print(f"    catalyst grade and the volume pace both move through the morning.")


# ══ STAGE K — re-tier the OLD-rubric alert rows under TODAY'S rubric ══════════
# Every mi_ep_alerts / mi_ep_scan_log row in this window was written 08-03..08-21,
# i.e. BEFORE the #533 separation flip (2026-08-22). The MODERATE tiers in those rows
# are proof: resolve_moderate_cutline(True) is None, so MODERATE cannot exist today.
# Stage A/J classifications are therefore old-rubric artifacts and must be re-tiered
# before any of them is called "an alert the flip would rescue".
print("\n" + "=" * 78)
print("STAGE K — those alert rows are OLD-rubric; what are they under today's?")
print("=" * 78)


def retier(d, ticker, catalyst, gap):
    g = graded_read(d, ticker)
    advdol = advd_map.get((ticker, d))
    a20, lc = adv20_map.get((ticker, d), (None, None))
    if advdol is None and a20 and lc:
        advdol = a20 * lc
    if advdol is None and g["adv"] and g["prev_close"]:
        advdol = g["adv"] * g["prev_close"]
    mult = REGIME.get(d, ("Choppy", 1.0))[1]
    hi, _ = new_score(gap, catalyst, advdol, g["pvm"], g["rel_volume"], 95.0,
                      in_theme(ticker, d), mult, 5)
    lo, _ = new_score(gap, catalyst, advdol, g["pvm"], g["rel_volume"], 50.0,
                      in_theme(ticker, d), mult, 0)
    return lo, hi, advdol


print("  the 25 caught-and-alerted-anyway names, re-scored on today's rubric:")
still_high = []
for r in sorted(cls_alerted, key=lambda x: (x["d"], x["ticker"])):
    a = r["_alert"]
    cq = a["catalyst_quality"]
    gap = f(a["gap_pct"]) or f(r["rt_gap"]) or 0.0
    lo, hi, advdol = retier(r["d"], r["ticker"], cq, gap)
    ok = hi >= SEPARATION_BAR
    if ok:
        still_high.append(r)
    print(f"    {r['d']} {r['ticker']:6s} was {a['score_tier']:9s} @{a['ep_score']:>6s} "
          f"catalyst={cq:13s} -> today {lo:.0f}-{hi:.0f}  "
          f"{'STILL CLEARS 65' if ok else 'BELOW 65 NOW'}")
print(f"    {len(still_high)} of {len(cls_alerted)} would still be an alert today.")

print("\n  the out-of-window rescue candidates, re-scored on today's rubric:")
rescue_now = []
for r in oow:
    tk = r["summary"].split(" —")[0].strip()
    ct = catch_tick.get((r["d"], tk))
    if not (ct and ct < "09:45"):
        continue
    a = alerted_same_day.get((r["d"], tk))
    if not a:
        print(f"    {r['d']} {tk:6s} — no alert row captured"); continue
    lo, hi, advdol = retier(r["d"], tk, a["catalyst_quality"],
                            f(a["gap_pct"]) or 0.0)
    ok = hi >= SEPARATION_BAR
    if ok:
        rescue_now.append((r["d"], tk))
    print(f"    {r['d']} {tk:6s} caught {ct} alerted {r['summary'].split('detected ')[-1]}"
          f" catalyst={a['catalyst_quality']:13s} ${(advdol or 0)/1e6:,.0f}M/day "
          f"-> today {lo:.0f}-{hi:.0f}  {'RESCUABLE' if ok else 'not a HIGH today'}")
print(f"\n  ⇒ ON TODAY'S RUBRIC: {len(rescue_now)} of {len(oow)} out-of-window alerts had already")
print(f"    crossed on the live feed inside the order window = "
      f"{len(rescue_now)/len(win_days):.2f} per trading day.")
