"""#655 step 1 — the GROUPING half of a theme correctness test: are the right stocks together?

Read-only, $0, no LLM. Inputs are captured ONCE to this folder (live_themes.psv, closes.psv,
scores_0925.psv, overrides.psv, theme_history.psv, closes_long_miners.psv); this script only reads them.

PRE-REGISTERED — definitions and PROPOSED pass bars written BEFORE the first number printed.
Bars are proposals for the operator; setting them is his (THE LINE covers any gate use).

Window: 60 sessions of market-adjusted (SPY-subtracted) daily log returns strictly before
2026-09-26, i.e. through Fri 2026-09-25. Maths imported from
agents/market_intelligence/market_adjusted_correlation.py — the engine's own definition, so every
number here is on the same scale as ASSIGN_COMOVE_BAR (0.35).

G1  MEMBER FIT. Each (member, theme): leave-one-out correlation of the member with the equal-weight
    basket of the theme's OTHER members (engine rule: >=3 other members with history, >=30 sessions).
    PASS BAR (proposed): >= 90% of judgeable member-pairs tie >= 0.35 (the signed admission bar).
    BROKEN SYSTEM reads: random membership -> ties ~0.05, pass rate ~10%.
    ERA CONFOUND: members that JOINED an existing theme on/after 2026-09-14 passed a 0.35 pair
    test to get in — for them G1 is the gate checking itself. Reported split: founder /
    joined-before-09-14 (never pair-tested) / joined-09-14+ (gated).

G2  MISFILED. Member m of theme T is MISFILED when (a) its own G1 tie < 0.35 AND (b) its best
    tie to any OTHER live theme is >= 0.35 AND >= own + 0.20. (a) is a single pre-specified test,
    so the flag does not rest on a best-of-many maximum; (b) only names the destination.
    PASS BAR (proposed): <= 5% of judgeable member-pairs misfiled.
    Best-of-many null reported alongside: share of matched random NON-board stocks whose best tie
    to any theme is >= 0.35 (how often (b) fires by chance).
    Split: destination theme a SHARD of the own theme (the two baskets correlate >= 0.70 —
    two pieces of one group, a fragmentation finding) vs a genuinely different group.

G3  COHESION vs MATCHED CONTROL. Theme cohesion = mean pairwise market-adjusted correlation among
    members with history (works from n = 2, so small themes are judged). Two controls, 500 draws
    each, member-for-member matched, drawn from the 09-25 scored universe excluding the theme:
      C1 = same RS-composite tercile x volatility tercile (any sector) — "is it a group at all?"
      C2 = C1 + same sector — "is it more than its sector?" (a sector basket beats C1, not C2)
    PASS BAR (proposed): theme cohesion > C1 p95 for >= 90% of themes; C2 reported, not barred
    (a theme can legitimately be sector-wide; it is the identity question, not grouping).
    BROKEN SYSTEM reads: arbitrary baskets sit at ~the 50th percentile of C1.

G4  SHAPE.
    - themes under 3 members (share of board); themes the engine's own instrument cannot judge
      (fewer than 4 members with history -> no member has a >=3-name LOO basket).
    - SHARD PAIRS: theme pairs whose baskets correlate >= 0.70; count of small (<=3) themes that
      are a shard of another live theme.
    - DUAL-HOMED: tickers in >= 2 live themes; which home ties tighter.
    - HOMELESS STRONG CO-MOVERS: scored stocks in NO live theme whose best theme tie is
      >= max(0.35, that theme's median member G1 tie) — it fits as well as the typical member.
      Run with the engine's own floor (rs_composite >= 70) AND without it.
    PASS BARS (proposed): themes under 3 members <= 10% of board; homeless strong co-movers
    (with the RS floor) reported as a count to trend, no bar until a baseline exists.

#491 readout: the miners theme, CIFR's two homes, APLD, CORZ/WULF; plus ONE identity number —
the miners basket's tie to IBIT (bitcoin) vs to a live AI-infra theme basket, over rolling windows.
"""
from __future__ import annotations

import os
import random
import statistics as st
import sys
from collections import defaultdict
from datetime import date

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.abspath(os.path.join(HERE, "..", "..", "..", "..")))
from agents.market_intelligence import market_adjusted_correlation as mac  # noqa: E402

BAR = 0.35
MISFILE_MARGIN = 0.20
SHARD_BAR = 0.70
RS_FLOOR = 70.0
N_DRAWS = 500
RUN_DATE = date(2026, 9, 26)
GATE_LIVE = date(2026, 9, 14)
random.seed(655)
np.random.seed(655)

OUT = []


def say(s=""):
    OUT.append(s)
    print(s)


def d(s):
    y, m, dd = s.split("-")
    return date(int(y), int(m), int(dd))


# ── load ────────────────────────────────────────────────────────────────────────────────────
themes = []
for l in open(os.path.join(HERE, "live_themes.psv")):
    p = l.rstrip("\n").split("|")
    themes.append(dict(name=p[0], stage=p[1], theme_date=p[2],
                       tickers=[t for t in p[4].split(",") if t], source=p[5]))

closes = defaultdict(dict)
for l in open(os.path.join(HERE, "closes.psv")):
    t, dt, c = l.rstrip("\n").split("|")
    if c:
        closes[t][d(dt)] = float(c)

scores = {}
for l in open(os.path.join(HERE, "scores_0925.psv")):
    t, rank, comp, sec, adv, mcap, cl = l.rstrip("\n").split("|")
    scores[t] = dict(rank=int(rank), rs=float(comp) if comp else None, sector=sec or None)

sector = {}
for l in open(os.path.join(HERE, "overrides.psv")):
    p = l.rstrip("\n").split("|")
    if len(p) >= 2 and p[1]:
        sector[p[0]] = p[1]
for t, s in scores.items():
    if s["sector"]:
        sector[t] = s["sector"]

hist = defaultdict(lambda: defaultdict(set))  # name -> date -> tickers
for l in open(os.path.join(HERE, "theme_history.psv")):
    dt, name, stage, tk = l.rstrip("\n").split("|")
    if stage == "Retired":
        continue
    hist[name][d(dt)] = set(t for t in tk.split(",") if t)

# ── returns ─────────────────────────────────────────────────────────────────────────────────
sessions = mac.session_index(closes["SPY"], RUN_DATE)
spy_r = mac.log_returns(closes["SPY"], sessions)
excess = mac.excess_returns({t: c for t, c in closes.items() if t != "SPY"}, sessions, spy_r)
usable = {t for t, v in excess.items() if mac.usable(v, mac.BELONGING_MIN_OVERLAP_SESSIONS)}


def pair_corr(a, b):
    va, vb = excess[a], excess[b]
    m = np.isfinite(va) & np.isfinite(vb)
    if m.sum() < mac.BELONGING_MIN_OVERLAP_SESSIONS:
        return None
    x, y = va[m], vb[m]
    if x.std() < 1e-12 or y.std() < 1e-12:
        return None
    return float(np.corrcoef(x, y)[0, 1])


def basket_for(th):
    b = mac.build_baskets([th], excess, stages=(th["stage"],))
    return b[0] if b else None


def tie(ticker, basket):
    if ticker not in usable or basket is None:
        return None
    c, n, k = mac.correlate(excess[ticker], basket, exclude=ticker)
    return c


def cohesion(members):
    ms = [m for m in members if m in usable]
    if len(ms) < 2:
        return None
    cs = [pair_corr(a, b) for i, a in enumerate(ms) for b in ms[i + 1:]]
    cs = [c for c in cs if c is not None]
    return float(np.mean(cs)) if cs else None


# ── population line ─────────────────────────────────────────────────────────────────────────
say("=" * 100)
say("#655 GROUPING TEST — live board of 2026-09-25 (latest row per name, theme_date >= CURRENT_DATE-7, stage <> Retired)")
say("=" * 100)
stage_ct = defaultdict(int)
for th in themes:
    stage_ct[th["stage"]] += 1
sizes = [len(th["tickers"]) for th in themes]
board = set(t for th in themes for t in th["tickers"])
say(f"POPULATION: n = {len(themes)} live themes ({', '.join(f'{k} {v}' for k, v in sorted(stage_ct.items()))}); "
    f"{sum(sizes)} member slots, {len(board)} distinct tickers; "
    f"{sum(1 for t in board if t in usable)} with >=30 of 60 sessions of history.")
say(f"  latest theme_date: {max(th['theme_date'] for th in themes)} (117 on 09-25, 1 carried from 09-24).")
say(f"  window: {len(sessions)-1} returns, {sessions[1]} -> {sessions[-1]}; SPY-subtracted; universe = "
    f"{len(scores)} scored stocks on 2026-09-25 ({sum(1 for t in scores if t in usable)} usable).")
say("  DELTA vs the brief's 09-11 board (127 themes, 9 empty, 20 at 2): today "
    f"{len(themes)} themes, {sum(1 for s in sizes if s == 0)} empty, {sum(1 for s in sizes if s == 2)} at 2, "
    f"{sum(1 for s in sizes if s == 3)} at 3.")
say("  REGIME: the 0.35 co-movement admission gate is live since 2026-09-14 (assignment); Shape A (the two strips "
    "judged by the tape) since 2026-09-25. Members admitted since 09-14 were pair-tested at 0.35 -> see G1 era split.")

# ── per-theme baskets and member ties ───────────────────────────────────────────────────────
baskets = {th["name"]: basket_for(th) for th in themes}
by_name = {th["name"]: th for th in themes}

# era of each (member, theme)
def era(ticker, name):
    h = hist.get(name)
    if not h:
        return "unknown"
    dates = sorted(h)
    first_theme = dates[0]
    first_tk = next((dt for dt in dates if ticker in h[dt]), None)
    if first_tk is None:
        return "unknown"
    if first_tk == first_theme:
        return "founder" if first_theme > date(2026, 5, 1) else "carried-pre-May"
    return "joined-09-14+" if first_tk >= GATE_LIVE else "joined-pre-09-14"


rows = []  # per member-pair
for th in themes:
    b = baskets[th["name"]]
    for m in th["tickers"]:
        own = tie(m, b)
        rows.append(dict(theme=th["name"], stage=th["stage"], size=len(th["tickers"]), ticker=m,
                         own=own, era=era(m, th["name"]), hist=m in usable))

# best OTHER theme tie for every board member (and every universe stock later)
names = [th["name"] for th in themes]


def best_other(ticker, exclude_names):
    best, bname = None, None
    for n in names:
        if n in exclude_names:
            continue
        b = baskets[n]
        if b is None:
            continue
        c = tie(ticker, b)
        if c is not None and (best is None or c > best):
            best, bname = c, n
    return best, bname


homes = defaultdict(list)
for th in themes:
    for m in th["tickers"]:
        homes[m].append(th["name"])

for r in rows:
    r["best_other"], r["best_other_name"] = best_other(r["ticker"], set(homes[r["ticker"]]))

# theme-theme basket correlation
def basket_corr(n1, n2):
    b1, b2 = baskets[n1], baskets[n2]
    if b1 is None or b2 is None:
        # fall back to all-member means for small themes
        pass
    v1 = mean_vec(n1)
    v2 = mean_vec(n2)
    if v1 is None or v2 is None:
        return None
    m = np.isfinite(v1) & np.isfinite(v2)
    if m.sum() < 30:
        return None
    return float(np.corrcoef(v1[m], v2[m])[0, 1])


_mv = {}


def mean_vec(n):
    if n in _mv:
        return _mv[n]
    ms = [t for t in by_name[n]["tickers"] if t in usable]
    if len(ms) < 2:
        _mv[n] = None
        return None
    mat = np.vstack([excess[t] for t in ms])
    fin = np.isfinite(mat)
    cnt = fin.sum(axis=0)
    with np.errstate(invalid="ignore"):
        v = np.where(cnt >= 2, np.nansum(np.where(fin, mat, 0), axis=0) / np.maximum(cnt, 1), np.nan)
    _mv[n] = v
    return v


# ── G1 ──────────────────────────────────────────────────────────────────────────────────────
say()
say("-" * 100)
say("G1  MEMBER FIT — leave-one-out tie of each member to its own theme (engine maths; bar 0.35)")
say("-" * 100)
judg = [r for r in rows if r["own"] is not None]
say(f"member-pairs on the board: n = {len(rows)}; judgeable by the engine's instrument: n = {len(judg)} "
    f"({len(judg)/len(rows):.0%}); unjudgeable n = {len(rows)-len(judg)}")
unj_themes = [th for th in themes if baskets[th['name']] is None or
              sum(1 for m in th['tickers'] if m in usable) < 4]
say(f"themes where NO member can be judged (fewer than 4 members with history): {len(unj_themes)} of {len(themes)} "
    f"({len(unj_themes)/len(themes):.0%})")
ties = [r["own"] for r in judg]
say(f"own-fit distribution (n = {len(ties)}): p10 {np.percentile(ties,10):.2f} · p25 {np.percentile(ties,25):.2f} · "
    f"median {np.median(ties):.2f} · p75 {np.percentile(ties,75):.2f}")
p = sum(1 for x in ties if x >= BAR)
say(f"PASS RATE: {p} of {len(ties)} judgeable member-pairs tie >= 0.35 = {p/len(ties):.1%}   [proposed bar >= 90%]")
say("by era (how the member got into the theme):")
for e in ["founder", "carried-pre-May", "joined-pre-09-14", "joined-09-14+", "unknown"]:
    xs = [r["own"] for r in judg if r["era"] == e]
    if xs:
        say(f"  {e:18s} n = {len(xs):4d}  median {np.median(xs):.2f}  >=0.35: {sum(1 for x in xs if x>=BAR)} ({sum(1 for x in xs if x>=BAR)/len(xs):.0%})")
say("by stage:")
for s in ["Nascent", "Accelerating", "Mainstream", "Fading"]:
    xs = [r["own"] for r in judg if r["stage"] == s]
    if xs:
        say(f"  {s:13s} n = {len(xs):4d}  median {np.median(xs):.2f}  >=0.35: {sum(1 for x in xs if x>=BAR)/len(xs):.0%}")

# ── G2 ──────────────────────────────────────────────────────────────────────────────────────
say()
say("-" * 100)
say(f"G2  MISFILED — own tie < 0.35 AND best other theme >= 0.35 AND >= own + {MISFILE_MARGIN}")
say("-" * 100)
mis = [r for r in judg if r["own"] < BAR and r["best_other"] is not None and r["best_other"] >= BAR
       and r["best_other"] - r["own"] >= MISFILE_MARGIN]
fails = [r for r in judg if r["own"] < BAR]
say(f"members failing their own theme (own < 0.35): {len(fails)} of {len(judg)}")
say(f"  of which MISFILED (a better home exists at >= 0.35, margin >= {MISFILE_MARGIN}): {len(mis)} = "
    f"{len(mis)/len(judg):.1%} of judgeable pairs   [proposed bar <= 5%]")
say(f"  of which fit NOWHERE (no theme >= 0.35): {sum(1 for r in fails if (r['best_other'] or -1) < BAR)}")
shard_mis, true_mis = [], []
for r in mis:
    bc = basket_corr(r["theme"], r["best_other_name"])
    r["dest_basket_corr"] = bc
    (shard_mis if (bc is not None and bc >= SHARD_BAR) else true_mis).append(r)
say(f"  split: destination is a SHARD of the own theme (baskets >= {SHARD_BAR}): {len(shard_mis)} · a DIFFERENT group: {len(true_mis)}")
sec_same = sum(1 for r in mis if sector.get(r['ticker']) and
               sector.get(r['ticker']) in {sector.get(t) for t in by_name[r['best_other_name']]['tickers']})
say(f"  (sector view: destination theme holds the member's own sector in {sec_same} of {len(mis)})")
closer = [r for r in judg if r["best_other"] is not None and r["best_other"] > r["own"]]
say(f"softer read, not barred: members tied MORE to some other theme than their own (any margin): {len(closer)} of {len(judg)} "
    f"({len(closer)/len(judg):.0%}) — best-of-117 maximum vs a single own tie, inflated by construction")
say("MISFILED list (ticker · own theme -> better home · own / best):")
for r in sorted(mis, key=lambda r: r["own"]):
    say(f"  {r['ticker']:6s} {r['theme'][:48]:48s} -> {r['best_other_name'][:48]:48s} {r['own']:+.2f} / {r['best_other']:+.2f}"
        f"{'  [shard]' if r in shard_mis else ''}")

# ── G3 ──────────────────────────────────────────────────────────────────────────────────────
say()
say("-" * 100)
say("G3  COHESION vs MATCHED RANDOM CONTROL (mean pairwise tie; 500 member-matched draws)")
say("-" * 100)
uni = [t for t in scores if t in usable and scores[t]["rs"] is not None]
vol = {t: float(np.nanstd(excess[t])) for t in uni}
rs_cut = np.percentile([scores[t]["rs"] for t in uni], [33.3, 66.7])
vol_cut = np.percentile([vol[t] for t in uni], [33.3, 66.7])


def tert(x, cuts):
    return 0 if x <= cuts[0] else (1 if x <= cuts[1] else 2)


def feats(t):
    rs = scores.get(t, {}).get("rs")
    v = float(np.nanstd(excess[t])) if t in usable else None
    return (tert(rs, rs_cut) if rs is not None else None, tert(v, vol_cut) if v is not None else None,
            sector.get(t))


cell1 = defaultdict(list)
cell2 = defaultdict(list)
for t in uni:
    a, b, s = feats(t)
    cell1[(a, b)].append(t)
    cell2[(a, b, s)].append(t)


def draw(members, with_sector):
    out = []
    excl = set(members)
    for m in members:
        a, b, s = feats(m)
        if a is None:
            a = 2  # unscored board member: treat as top RS tercile (board names are strength-selected)
        pool = []
        if with_sector and s:
            pool = [x for x in cell2.get((a, b, s), []) if x not in excl]
            if len(pool) < 5:  # relax volatility, keep sector + RS
                pool = [x for (aa, bb, ss), xs in cell2.items() if aa == a and ss == s for x in xs if x not in excl]
        if len(pool) < 5:
            pool = [x for x in cell1.get((a, b), []) if x not in excl]
        x = random.choice(pool)
        out.append(x)
        excl.add(x)
    return out


# precompute full pair matrix over universe+board for speed
allt = sorted(set(uni) | {t for t in board if t in usable})
idx = {t: i for i, t in enumerate(allt)}
M = np.vstack([excess[t] for t in allt])
fin = np.isfinite(M)
Mz = np.where(fin, M, 0.0)
# pairwise corr with pairwise-complete masks is expensive; windows are nearly complete, so use
# complete-case per pair only where needed: check completeness
complete = fin.all(axis=1)
say(f"(pair matrix: {len(allt)} tickers, {complete.sum()} with all {M.shape[1]} sessions)")
Mc = M.copy()
Mc[~fin] = np.nan
means = np.nanmean(Mc, axis=1, keepdims=True)
sds = np.nanstd(Mc, axis=1, keepdims=True)
Zs = np.where(fin, (Mc - means) / sds, 0.0)
C = (Zs @ Zs.T) / np.maximum(fin.astype(float) @ fin.T.astype(float), 1)  # approx pairwise corr


def coh_fast(ms):
    ii = [idx[m] for m in ms if m in idx]
    if len(ii) < 2:
        return None
    sub = C[np.ix_(ii, ii)]
    k = len(ii)
    return float((sub.sum() - np.trace(sub)) / (k * (k - 1)))


# sanity: fast vs exact on a few themes
chk = [(th["name"], cohesion(th["tickers"]), coh_fast(th["tickers"])) for th in themes[:8]]
say("fast-vs-exact cohesion check: " + "; ".join(f"{a:.3f}/{b:.3f}" for _, a, b in chk if a is not None))

trows = []
for th in themes:
    ms = [m for m in th["tickers"] if m in usable]
    c = coh_fast(ms)
    if c is None:
        trows.append(dict(name=th["name"], stage=th["stage"], size=len(th["tickers"]), coh=None))
        continue
    c1 = [coh_fast(draw(ms, False)) for _ in range(N_DRAWS)]
    c2 = [coh_fast(draw(ms, True)) for _ in range(N_DRAWS)]
    trows.append(dict(name=th["name"], stage=th["stage"], size=len(th["tickers"]), coh=c,
                      c1_med=float(np.median(c1)), c1_p95=float(np.percentile(c1, 95)),
                      c1_pct=float(np.mean([x < c for x in c1])),
                      c2_med=float(np.median(c2)), c2_p95=float(np.percentile(c2, 95)),
                      c2_pct=float(np.mean([x < c for x in c2]))))
jt = [r for r in trows if r["coh"] is not None]
say(f"themes judgeable (>= 2 members with history): n = {len(jt)} of {len(themes)}")
say(f"theme cohesion: median {np.median([r['coh'] for r in jt]):.2f} (p25 {np.percentile([r['coh'] for r in jt],25):.2f}, "
    f"p75 {np.percentile([r['coh'] for r in jt],75):.2f})")
say(f"C1 control (RS x vol matched) median cohesion: {np.median([r['c1_med'] for r in jt]):.2f}; "
    f"C2 (+ same sector): {np.median([r['c2_med'] for r in jt]):.2f}")
p1 = [r for r in jt if r["coh"] > r["c1_p95"]]
p2 = [r for r in jt if r["coh"] > r["c2_p95"]]
say(f"PASS C1 (beats a random matched basket at p95): {len(p1)} of {len(jt)} = {len(p1)/len(jt):.1%}   [proposed bar >= 90%]")
say(f"beats its OWN SECTOR (C2 p95) — not barred: {len(p2)} of {len(jt)} = {len(p2)/len(jt):.1%}")
for s in ["Nascent", "Accelerating", "Mainstream", "Fading"]:
    xs = [r for r in jt if r["stage"] == s]
    if xs:
        say(f"  {s:13s} n = {len(xs):3d}  pass C1 {sum(1 for r in xs if r['coh']>r['c1_p95'])}  beat sector {sum(1 for r in xs if r['coh']>r['c2_p95'])}")
by_size = defaultdict(list)
for r in jt:
    by_size["2" if r["size"] == 2 else "3" if r["size"] == 3 else "4-5" if r["size"] <= 5 else "6+"].append(r)
for k in ["2", "3", "4-5", "6+"]:
    xs = by_size[k]
    if xs:
        say(f"  size {k:4s} n = {len(xs):3d}  pass C1 {sum(1 for r in xs if r['coh']>r['c1_p95'])} ({sum(1 for r in xs if r['coh']>r['c1_p95'])/len(xs):.0%})")
say("FAIL C1 (not distinguishable from a random matched basket):")
for r in sorted([r for r in jt if r["coh"] <= r["c1_p95"]], key=lambda r: r["coh"]):
    say(f"  {r['name'][:60]:60s} [{r['stage']}, {r['size']}] cohesion {r['coh']:+.2f} vs control p95 {r['c1_p95']:+.2f}")

# ── G4 ──────────────────────────────────────────────────────────────────────────────────────
say()
say("-" * 100)
say("G4  SHAPE")
say("-" * 100)
small = [th for th in themes if len(th["tickers"]) < 3]
say(f"themes under 3 members: {len(small)} of {len(themes)} = {len(small)/len(themes):.1%}   [proposed bar <= 10%]")
say(f"themes of 3 members: {sum(1 for s in sizes if s == 3)}; <= 5 members: {sum(1 for s in sizes if s <= 5)} of {len(themes)} "
    f"({sum(1 for s in sizes if s <= 5)/len(themes):.0%})")
say(f"themes the engine's own co-movement test cannot judge ANY member of: {len(unj_themes)} of {len(themes)}")
# shard pairs
pairs = []
for i, a in enumerate(names):
    for b in names[i + 1:]:
        c = basket_corr(a, b)
        if c is not None and c >= SHARD_BAR:
            pairs.append((a, b, c))
say(f"SHARD PAIRS (two live themes whose baskets correlate >= {SHARD_BAR}): {len(pairs)}")
in_pair = defaultdict(list)
for a, b, c in pairs:
    in_pair[a].append((b, c))
    in_pair[b].append((a, c))
small_shards = [th for th in themes if len(th["tickers"]) <= 3 and th["name"] in in_pair]
say(f"  themes in >=1 shard pair: {len(in_pair)} of {len(themes)}; small themes (<=3) that are a shard of another: "
    f"{len(small_shards)} of {sum(1 for s in sizes if s <= 3)}")
for a, b, c in sorted(pairs, key=lambda x: -x[2])[:25]:
    say(f"  {c:.2f}  {a[:50]:50s} [{len(by_name[a]['tickers'])}] ~ {b[:50]:50s} [{len(by_name[b]['tickers'])}]")
# dual-homed
dual = {t: hs for t, hs in homes.items() if len(hs) >= 2}
say(f"DUAL-HOMED tickers (in >= 2 live themes): {len(dual)} of {len(board)} ({len(dual)/len(board):.1%})")
dh_rows = []
for t, hs in sorted(dual.items()):
    ts = [(h, tie(t, baskets[h]), None) for h in hs]
    dh_rows.append((t, ts))
for t, ts in dh_rows:
    say("  " + t + ": " + " | ".join(f"{h[:40]} {('%+.2f' % c) if c is not None else 'n/a'}" for h, c, _ in ts))
# homeless
say("HOMELESS STRONG CO-MOVERS (in no live theme; best theme tie >= max(0.35, that theme's median member tie)):")
med_tie = {}
for th in themes:
    xs = [r["own"] for r in judg if r["theme"] == th["name"]]
    med_tie[th["name"]] = float(np.median(xs)) if xs else None
homeless = []
for t in uni:
    if t in board:
        continue
    bt, bn = best_other(t, set())
    if bt is None or bn is None or med_tie.get(bn) is None:
        continue
    if bt >= max(BAR, med_tie[bn]):
        homeless.append((t, scores[t]["rs"], bn, bt, med_tie[bn]))
hf = [h for h in homeless if h[1] >= RS_FLOOR]
say(f"  universe checked: {sum(1 for t in uni if t not in board)} scored stocks in no theme "
    f"({sum(1 for t in uni if t not in board and scores[t]['rs'] >= RS_FLOOR)} of them at rs_composite >= 70)")
say(f"  WITH the engine's RS floor (rs_composite >= 70): {len(hf)}; WITHOUT the floor: {len(homeless)}")
dest = defaultdict(list)
for h in hf:
    dest[h[2]].append(h[0])
say(f"  (floor) they fit {len(dest)} distinct themes; top themes by homeless count:")
for n, ts in sorted(dest.items(), key=lambda x: -len(x[1]))[:10]:
    say(f"    {len(ts):3d}  {n[:60]}  e.g. {','.join(ts[:8])}")
# best-of-many null
nb = [t for t in uni if t not in board]
null_hits = 0
null_n = 0
for t in random.sample(nb, min(400, len(nb))):
    bt, bn = best_other(t, set())
    if bt is None:
        continue
    null_n += 1
    null_hits += bt >= BAR
say(f"  best-of-many NULL: {null_hits} of {null_n} random NON-board scored stocks have a best theme tie >= 0.35 "
    f"({null_hits/null_n:.0%}) — so '>= 0.35 to SOME theme' alone is not evidence of belonging")

# ── #491 ────────────────────────────────────────────────────────────────────────────────────
say()
say("-" * 100)
say("#491 — the ex-bitcoin miners that pivoted to AI data centres")
say("-" * 100)
MIN = "Bitcoin Mining Stocks Rotation Reversal"
PWR = "AI data-center power buildout"
CLD = "Cloud Data Storage & Analytics Infrastructure"
for n in [MIN, PWR, CLD]:
    th = by_name[n]
    tr = next(r for r in trows if r["name"] == n)
    say(f"{n} [{th['stage']}, {len(th['tickers'])}]: cohesion {tr['coh']:+.2f} vs matched p95 {tr['c1_p95']:+.2f} "
        f"-> {'PASS' if tr['coh'] > tr['c1_p95'] else 'FAIL'} G3; beats own sector: {'yes' if tr['coh'] > tr['c2_p95'] else 'no'}")
    for m in th["tickers"]:
        r = next(r for r in rows if r["theme"] == n and r["ticker"] == m)
        flag = ("MISFILED" if r in mis else ("fails own" if r["own"] is not None and r["own"] < BAR else "fits"))
        say(f"    {m:6s} own {('%+.2f' % r['own']) if r['own'] is not None else '  n/a'}  best other "
            f"{('%+.2f' % r['best_other']) if r['best_other'] is not None else 'n/a'} {str(r['best_other_name'])[:42]:42s} "
            f"era {r['era']:16s} {flag}")
for t in ["CORZ", "WULF", "APLD", "NBIS", "CRWV", "GLXY"]:
    say(f"  {t}: homes {homes.get(t, []) or 'NONE'}; rs_composite {scores.get(t, {}).get('rs')}; tie to miners basket "
        f"{('%+.2f' % tie(t, baskets[MIN])) if tie(t, baskets[MIN]) is not None else 'n/a'}; "
        f"homeless-flag {'with floor' if any(h[0]==t for h in hf) else ('without floor only' if any(h[0]==t for h in homeless) else 'no')}")
say(f"  miners basket ~ AI power basket (theme-theme): {basket_corr(MIN, PWR):+.2f}; ~ cloud-storage basket: {basket_corr(MIN, CLD):+.2f}")

# identity add-on: rolling tie of the miners basket to IBIT vs an AI-infra theme basket
say()
say("IDENTITY ADD-ON (one number, not part of the grouping test): does price still say 'bitcoin'?")
lc = defaultdict(dict)
for l in open(os.path.join(HERE, "closes_long_miners.psv")):
    t, dt, c = l.rstrip("\n").split("|")
    if c:
        lc[t][d(dt)] = float(c)
miners = ["HUT", "CIFR", "BTDR", "CLSK", "MARA", "RIOT", "IREN", "CORZ", "WULF"]  # ABTC/IOND lack a year of history
ai_ic = ["BDC", "COHR", "APH", "ALAB", "GLW", "LITE", "CRDO"]  # the live 'AI Data Center High-Speed Interconnect' theme
ai_pw = ["AGX", "SNOW", "ALAB", "GNRC", "VICR", "AKAM"]  # the live 'AI data-center power buildout' theme minus CIFR
spy_dates = sorted(lc["SPY"])


def basket_vec(tks, ss, mr):
    ex = mac.excess_returns({t: lc[t] for t in tks}, ss, mr)
    mat = np.vstack([ex[t] for t in tks if t in ex])
    return np.nanmean(mat, axis=0)


def cc(a, b):
    m = np.isfinite(a) & np.isfinite(b)
    return float(np.corrcoef(a[m], b[m])[0, 1]) if m.sum() >= 30 else None


say("  window ending   miners~IBIT   miners~AI-interconnect   miners~AI-power(ex-CIFR)")
for end in ["2025-09-30", "2025-12-31", "2026-03-31", "2026-06-30", "2026-09-25"]:
    ed = d(end)
    ss = mac.session_index(lc["SPY"], date.fromordinal(ed.toordinal() + 1))
    mr = mac.log_returns(lc["SPY"], ss)
    mv = basket_vec(miners, ss, mr)
    ib = mac.excess_returns({"IBIT": lc["IBIT"]}, ss, mr)["IBIT"]
    say(f"  {end}      {cc(mv, ib):+.2f}          {cc(mv, basket_vec(ai_ic, ss, mr)):+.2f}                   "
        f"{cc(mv, basket_vec(ai_pw, ss, mr)):+.2f}")

# ── POST-HOC (added AFTER the first run printed; NOT pre-registered — labelled as such) ─────────
say()
say("-" * 100)
say("POST-HOC READS (added after the first run; they explain the pre-registered numbers, they do not replace them)")
say("-" * 100)
# (1) best-of-many null distribution: how high does a typical UNTHEMED stock's best theme tie go?
nb_best = []
for t in nb:
    bt, bn = best_other(t, set())
    if bt is not None:
        nb_best.append(bt)
q = np.percentile(nb_best, [50, 75, 90, 95, 99])
say(f"(1) best-theme tie of ALL {len(nb_best)} unthemed scored stocks: p50 {q[0]:.2f} · p75 {q[1]:.2f} · p90 {q[2]:.2f} · "
    f"p95 {q[3]:.2f} · p99 {q[4]:.2f}  -> 0.35 is below the MEDIAN unthemed stock's best fit")
null95 = float(q[3])
# (2) homeless rule variants
v_a = [t for t in nb if (lambda bb: bb[0] is not None and bb[0] >= null95)(best_other(t, set()))]
v_a_f = [t for t in v_a if scores[t]["rs"] >= RS_FLOOR]
say(f"(2) homeless variant A — best tie >= unthemed p95 ({null95:.2f}): {len(v_a)} names; with RS floor {len(v_a_f)}")
say(f"    CORZ in A: {'CORZ' in v_a} · WULF in A: {'WULF' in v_a}  (the declared rule missed both: 0.85 vs the miners' "
    f"median member tie {med_tie[MIN]:.2f}; the RS floor also drops them at rs_composite 19)")
say(f"    declared-rule miss margin on the miners theme: CORZ {tie('CORZ', baskets[MIN]) - med_tie[MIN]:+.3f}, "
    f"WULF {tie('WULF', baskets[MIN]) - med_tie[MIN]:+.3f}")
dA = defaultdict(list)
for t in v_a:
    bt, bn = best_other(t, set())
    dA[bn].append(t)
say("    variant A destinations (top 8):")
for n, ts in sorted(dA.items(), key=lambda x: -len(x[1]))[:8]:
    say(f"      {len(ts):3d}  {n[:60]}  e.g. {','.join(ts[:10])}")
# (3) shard pairs: same members (a duplicate) vs different members (two slices of one co-moving block)
def overlap(a, b):
    A, B = set(by_name[a]["tickers"]), set(by_name[b]["tickers"])
    return len(A & B) / max(1, min(len(A), len(B)))
dup = [(a, b, c) for a, b, c in pairs if overlap(a, b) >= 0.5]
say(f"(3) of the {len(pairs)} shard pairs: {len(dup)} share >= half their members (duplicates); "
    f"{len(pairs)-len(dup)} hold different names that trade as one block")
allc = [basket_corr(a, b) for i, a in enumerate(names) for b in names[i+1:]]
allc = [c for c in allc if c is not None]
say(f"    basket-to-basket tie across all {len(allc)} theme pairs: p50 {np.median(allc):.2f} · p90 {np.percentile(allc,90):.2f} · "
    f"p95 {np.percentile(allc,95):.2f} · p99 {np.percentile(allc,99):.2f}")
for a, b, c in dup:
    say(f"      dup {c:.2f} overlap {overlap(a,b):.2f}  {a[:45]} [{by_name[a]['theme_date']}] ~ {b[:45]} [{by_name[b]['theme_date']}]")
# (4) G1 on never-pair-tested members only
ung = [r for r in judg if r["era"] in ("founder", "carried-pre-May", "joined-pre-09-14")]
say(f"(4) G1 pass rate on members NEVER pair-tested (founders + joined before 09-14): "
    f"{sum(1 for r in ung if r['own']>=BAR)} of {len(ung)} = {sum(1 for r in ung if r['own']>=BAR)/len(ung):.1%}")
# (5) control power by size
for k in ["2", "3", "4-5", "6+"]:
    xs = by_size[k]
    if xs:
        say(f"(5) size {k:4s}: median control p95 {np.median([r['c1_p95'] for r in xs]):.2f} (a theme this small must clear this to pass G3)")
# (6) the neocloud landing zone
NEO = "Emerging AI Compute & Cloud Infrastructure Platforms"
say(f"(6) '{NEO}' {by_name[NEO]['tickers']}: cohesion {coh_fast(by_name[NEO]['tickers']):+.2f}; "
    f"miners basket ~ it {basket_corr(MIN, NEO):+.2f}")
for t in ["HUT", "CIFR", "CLSK", "RIOT", "MARA", "IREN", "BTDR", "CORZ", "WULF", "APLD"]:
    say(f"      {t:5s} tie to miners {tie(t, baskets[MIN]):+.2f} · to AI-compute {tie(t, baskets[NEO]):+.2f} · to AI-power "
        f"{tie(t, baskets[PWR]):+.2f}")

# (7) homeless variant B: variant A restricted to destinations that are MORE than their sector (beat C2 p95)
beats_sector = {r["name"] for r in jt if r["coh"] > r["c2_p95"]}
v_b = [t for t in v_a if best_other(t, set())[1] in beats_sector]
say(f"(7) homeless variant B — A, restricted to themes that beat their own sector: {len(v_b)} names "
    f"(RS floor {sum(1 for t in v_b if scores[t]['rs'] >= RS_FLOOR)}); CORZ {'CORZ' in v_b} · WULF {'WULF' in v_b}")
dB = defaultdict(list)
for t in v_b:
    dB[best_other(t, set())[1]].append(t)
for n, ts in sorted(dB.items(), key=lambda x: -len(x[1])):
    say(f"      {len(ts):3d}  {n[:60]}  {','.join(ts)}")
fm = sum(1 for r in mis if r["best_other"] >= float(q[0]))
say(f"(8) misfiled destinations: {fm} of {len(mis)} tie above the unthemed MEDIAN best fit ({q[0]:.2f}); "
    f"{sum(1 for r in mis if r['best_other'] >= null95)} above its p95 ({null95:.2f})")

# ── outputs ─────────────────────────────────────────────────────────────────────────────────
with open(os.path.join(HERE, "grouping_members.tsv"), "w") as f:
    f.write("theme\tstage\tsize\tticker\tera\town_tie\tbest_other\tbest_other_theme\tmisfiled\n")
    for r in rows:
        f.write(f"{r['theme']}\t{r['stage']}\t{r['size']}\t{r['ticker']}\t{r['era']}\t"
                f"{'' if r['own'] is None else round(r['own'],4)}\t"
                f"{'' if r['best_other'] is None else round(r['best_other'],4)}\t{r['best_other_name'] or ''}\t"
                f"{int(r in mis)}\n")
with open(os.path.join(HERE, "grouping_themes.tsv"), "w") as f:
    f.write("theme\tstage\tsize\tcohesion\tc1_median\tc1_p95\tc1_pctile\tc2_median\tc2_p95\tc2_pctile\n")
    for r in trows:
        if r["coh"] is None:
            f.write(f"{r['name']}\t{r['stage']}\t{r['size']}\t\t\t\t\t\t\t\n")
        else:
            f.write(f"{r['name']}\t{r['stage']}\t{r['size']}\t{r['coh']:.4f}\t{r['c1_med']:.4f}\t{r['c1_p95']:.4f}\t"
                    f"{r['c1_pct']:.3f}\t{r['c2_med']:.4f}\t{r['c2_p95']:.4f}\t{r['c2_pct']:.3f}\n")
with open(os.path.join(HERE, "grouping_homeless.tsv"), "w") as f:
    f.write("ticker\trs_composite\tbest_theme\ttie\ttheme_median_member_tie\n")
    for h in sorted(homeless, key=lambda h: -h[3]):
        f.write(f"{h[0]}\t{h[1]}\t{h[2]}\t{h[3]:.4f}\t{h[4]:.4f}\n")
open(os.path.join(HERE, "grouping_test_out.txt"), "w").write("\n".join(OUT) + "\n")
