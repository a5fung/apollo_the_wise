#!/usr/bin/env python
"""#655 step 1 + step 2 — THE FUNNEL TEST, measured on today's board. $0, read-only, local compute.

Inputs (each captured ONCE from prod, 2026-09-27, read-only SELECTs, files in this directory):
  funnel_live_board.psv        live board: latest row per name within 7 days, stage <> Retired (118 themes, 09-25)
  funnel_themes_hist.psv       every mi_themes row since 2026-05-01 (lineages, births, identity history)
  funnel_clusters.psv          mi_correlation_clusters since 2026-04-01 (stored = UNCOVERED by construction)
  funnel_closes.psv            mi_daily_closes close, 2026-02-01 -> 09-25, 2,500 tickers (themed since 03-01 + 09-25 score board + ETFs)
  funnel_btc.psv               crypto_daily_closes coin_id='bitcoin'
  funnel_scores_0925.psv       mi_stock_scores 2026-09-25 (rs_rank, rs_composite, sector)
  funnel_churn_events.psv      mi_audit_log theme churn event rows since 2026-07-20
  funnel_shadow_candidates.psv mi_theme_candidates_shadow since 2026-06-01 (the engine's OWN proposed names)
  funnel_labels.psv            mi_theme_relevance_cohort stratum='themed' + credited theme (cross-check ONLY)
Co-movement maths is IMPORTED from agents/market_intelligence/market_adjusted_correlation.py (never re-derived):
SPY-subtracted daily log returns, 60 sessions strictly before the date, Pearson vs equal-weight basket mean,
leave-one-out for members, >=3 basket members and >=30 overlapping sessions.
THE RULES BELOW WERE WRITTEN BEFORE THE LABELS WERE READ; the labels section runs last and changes nothing.
"""
from __future__ import annotations

import random
import re
import statistics
import sys
from collections import Counter, defaultdict
from datetime import date, timedelta
from pathlib import Path

import numpy as np

REPO = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO))
from agents.market_intelligence import market_adjusted_correlation as mac  # noqa: E402

HERE = Path(__file__).resolve().parent
OUT = open(HERE / "funnel_probe_out.txt", "w")


def say(s: str = "") -> None:
    print(s)
    OUT.write(s + "\n")


def d_(s: str) -> date:
    return date.fromisoformat(s)


def pct(a: int, b: int) -> str:
    return f"{a} of {b} ({100 * a / b:.0f}%)" if b else f"{a} of 0"


def med(xs):
    xs = [x for x in xs if x is not None]
    return statistics.median(xs) if xs else None


def q(xs, p):
    xs = sorted(x for x in xs if x is not None)
    if not xs:
        return None
    k = (len(xs) - 1) * p
    lo, hi = int(k), min(int(k) + 1, len(xs) - 1)
    return xs[lo] + (xs[hi] - xs[lo]) * (k - lo)


# THE BAR — read from source so a later change to the constant cannot silently desync this probe
_src = (REPO / "agents/market_intelligence/theme_engine.py").read_text()
BAR = float(re.search(r"^ASSIGN_COMOVE_BAR = ([0-9.]+)", _src, re.M).group(1))
STAGES = ("Nascent", "Accelerating", "Mainstream", "Fading")
RUN_DATE = date(2026, 9, 26)   # the next engine run after the 09-25 board; the window is strictly before it
random.seed(655)

# ── load ─────────────────────────────────────────────────────────────────────────────────────────
closes: dict[str, dict[date, float]] = defaultdict(dict)
for ln in open(HERE / "funnel_closes.psv"):
    t, d, c = ln.rstrip("\n").split("|")
    if c:
        closes[t][d_(d)] = float(c)
for ln in open(HERE / "funnel_btc.psv"):
    d, c = ln.rstrip("\n").split("|")
    closes["BTC"][d_(d)] = float(c)          # loaded for the record only — its dates run one day off the equity sessions; IBIT is the proxy

board = []
for ln in open(HERE / "funnel_live_board.psv"):
    p = ln.rstrip("\n").split("|")
    board.append({"date": d_(p[0]), "name": p[1], "stage": p[2],
                  "tickers": [t for t in p[4].split(",") if t]})

hist = []   # every mi_themes row since 05-01
for ln in open(HERE / "funnel_themes_hist.psv"):
    p = ln.rstrip("\n").split("|")
    hist.append({"id": int(p[0]), "date": d_(p[1]), "name": p[2], "stage": p[3],
                 "tickers": [t for t in p[4].split(",") if t], "source": p[5]})

scores = {}
for ln in open(HERE / "funnel_scores_0925.psv"):
    t, rk, rs, sec, adv, cl = ln.rstrip("\n").split("|")
    scores[t] = {"rank": int(rk) if rk else None, "rs": float(rs) if rs else None, "sector": sec or "?",
                 "adv": float(adv) if adv else 0.0, "close": float(cl) if cl else 0.0}

shadow = []
for ln in open(HERE / "funnel_shadow_candidates.psv"):
    p = ln.rstrip("\n").split("|")
    shadow.append({"date": d_(p[0]), "name": p[1], "tickers": [t for t in p[2].split(",") if t], "source": p[3]})

_EX_CACHE: dict[date, dict[str, np.ndarray]] = {}


def excess_at(before: date) -> dict[str, np.ndarray]:
    if before not in _EX_CACHE:
        sessions = mac.session_index(closes["SPY"], before, mac.BELONGING_LOOKBACK_SESSIONS)
        market = mac.log_returns(closes["SPY"], sessions)
        _EX_CACHE[before] = mac.excess_returns(closes, sessions, market)
    return _EX_CACHE[before]


def basket_of(name: str, tickers, ex, min_members: int = mac.BELONGING_MIN_BASKET_MEMBERS):
    b = mac.build_baskets([{"name": name, "stage": "X", "tickers": tickers}], ex, ("X",), min_members=min_members)
    return b[0] if b else None


def fit(t: str, basket, ex, min_members: int = mac.BELONGING_MIN_BASKET_MEMBERS):
    v = ex.get(t)
    if v is None or basket is None or not mac.usable(v, mac.BELONGING_MIN_OVERLAP_SESSIONS):
        return None
    c, _, _ = mac.correlate(v, basket, exclude=t, min_members=min_members)
    return c


def vec_corr(a: np.ndarray, b: np.ndarray):
    m = np.isfinite(a) & np.isfinite(b)
    if m.sum() < mac.BELONGING_MIN_OVERLAP_SESSIONS or a[m].std() < 1e-12 or b[m].std() < 1e-12:
        return None
    return float(np.corrcoef(a[m], b[m])[0, 1])


def member_fits(th, ex):
    """Leave-one-out fit of every member to its OWN theme: the engine's exact per-pair statistic."""
    b = basket_of(th["name"], th["tickers"], ex)
    if b is None:
        return None, {}
    out = {m: fit(m, b, ex) for m in b.members}
    return b, out


ex = excess_at(RUN_DATE)
say(f"=== #655 FUNNEL TEST probe — board of {max(t['date'] for t in board)}, co-movement window = 60 sessions strictly before {RUN_DATE} ===")
say(f"BAR (ASSIGN_COMOVE_BAR, read from theme_engine.py) = {BAR}; tickers with a usable 60-session vector: "
    f"{sum(1 for v in ex.values() if mac.usable(v, 30))}")

# ═══════════════════════════════════════════════════════════════════════════════════════════════
# STAGE C — CRITERIA -> NEW THEMES:  SHAPE + GROUPING (does each live theme hold together?)
# ═══════════════════════════════════════════════════════════════════════════════════════════════
say("\n## C1 SHAPE — live board")
sizes = Counter(len(t["tickers"]) for t in board)
n_b = len(board)
say(f"live themes n={n_b}; stages {dict(Counter(t['stage'] for t in board))}")
say(f"members: 0 -> {sizes.get(0, 0)}, 2 -> {sizes.get(2, 0)}, 3 -> {sizes.get(3, 0)}, <=5 -> "
    f"{pct(sum(v for k, v in sizes.items() if k <= 5), n_b)}, >=4 (judgeable by the engine's own leave-one-out) -> "
    f"{pct(sum(v for k, v in sizes.items() if k >= 4), n_b)}")

say("\n## C2 GROUPING — median leave-one-out member fit >= BAR, themes with >=4 usable members")
theme_fit = {}
baskets = {}
for th in board:
    b, fits = member_fits(th, ex)
    baskets[th["name"]] = b
    vals = [v for v in fits.values() if v is not None]
    th["n_usable"] = len(b.members) if b else sum(1 for m in th["tickers"] if m in ex and mac.usable(ex[m], 30))
    th["fits"] = fits
    th["med_fit"] = med(vals) if len(vals) >= 1 else None
    th["share_ok"] = (sum(v >= BAR for v in vals) / len(vals)) if vals else None
judged = [th for th in board if th["med_fit"] is not None]
passed = [th for th in judged if th["med_fit"] >= BAR]
say(f"judgeable {pct(len(judged), n_b)}; PASS {pct(len(passed), len(judged))} of judgeable; "
    f"= {pct(len(passed), n_b)} of the whole board")
say(f"median of theme median-fits = {med([t['med_fit'] for t in judged]):.2f} (p25 {q([t['med_fit'] for t in judged], .25):.2f}, "
    f"p75 {q([t['med_fit'] for t in judged], .75):.2f})")
for th in sorted(judged, key=lambda t: t["med_fit"])[:8]:
    say(f"   weakest: {th['med_fit']:.2f}  {th['name']} [{th['stage']}] n={th['n_usable']}")

# thin themes: pairwise median as a secondary read (NOT the engine's statistic) so they are not a black hole
thin = [th for th in board if th["med_fit"] is None]
pw_ok = pw_n = 0
for th in thin:
    ms = [m for m in th["tickers"] if m in ex and mac.usable(ex[m], 30)]
    if len(ms) < 2:
        continue
    prs = [vec_corr(ex[a], ex[b]) for i, a in enumerate(ms) for b in ms[i + 1:]]
    prs = [x for x in prs if x is not None]
    if prs:
        pw_n += 1
        pw_ok += med(prs) >= BAR
        th["pw_med"] = med(prs)
say(f"thin themes (2-3 members; the engine's own test cannot judge them): n={len(thin)}; "
    f"median PAIRWISE corr >= {BAR}: {pct(pw_ok, pw_n)}  (secondary read — pairwise runs lower than member-to-basket)")

# CONTROLS — what a BROKEN grouping would read on the same statistic
universe = [t for t in scores if t in ex and mac.usable(ex[t], 30)]
by_sector = defaultdict(list)
for t in universe:
    by_sector[scores[t]["sector"]].append(t)
ctrl_rand = ctrl_sec = ctrl_n = 0
for th in judged:
    k = th["n_usable"]
    secs = Counter(scores.get(m, {}).get("sector", "?") for m in th["tickers"])
    modal = secs.most_common(1)[0][0]
    for _ in range(20):
        rb = random.sample(universe, k)
        b = basket_of("r", rb, ex)
        v = [fit(m, b, ex) for m in b.members] if b else []
        v = [x for x in v if x is not None]
        pool = by_sector.get(modal) or universe
        sb = random.sample(pool, min(k, len(pool)))
        b2 = basket_of("s", sb, ex)
        v2 = [fit(m, b2, ex) for m in b2.members] if b2 else []
        v2 = [x for x in v2 if x is not None]
        if v and v2:
            ctrl_n += 1
            ctrl_rand += med(v) >= BAR
            ctrl_sec += med(v2) >= BAR
say(f"CONTROL random baskets (same sizes, 20 draws per judged theme): PASS {pct(ctrl_rand, ctrl_n)}")
say(f"CONTROL same-SECTOR random baskets (modal sector of each theme): PASS {pct(ctrl_sec, ctrl_n)}  "
    f"<- a sector bucket passes grouping this often: grouping CANNOT tell a theme from a sector")

# ═══════════════════════════════════════════════════════════════════════════════════════════════
# STAGE M — MEMBERSHIP HOMES: misfiled members + homeless co-movers (best-of-many needs a margin)
# ═══════════════════════════════════════════════════════════════════════════════════════════════
say("\n## M1 MISFILED — a member that fails its own theme but fits another")
live_b = {n: b for n, b in baskets.items() if b is not None}
themed = defaultdict(set)
for th in board:
    for m in th["tickers"]:
        themed[m].add(th["name"])


def best_two(t: str, skip: set):
    res = []
    for n, b in live_b.items():
        if n in skip:
            continue
        v = fit(t, b, ex)
        if v is not None:
            res.append((v, n))
    res.sort(reverse=True)
    return res[:2]


mis_rows = []
for th in judged:
    for m, own in th["fits"].items():
        if own is None:
            continue
        top = best_two(m, themed[m])
        if top:
            mis_rows.append((m, th["name"], own, top[0][0], top[0][1], top[1][0] if len(top) > 1 else None))
say(f"themed member-slots judged n={len(mis_rows)}; own fit < {BAR}: {pct(sum(r[2] < BAR for r in mis_rows), len(mis_rows))}")
for lab, fn in ((f"own<{BAR} & other>={BAR}", lambda r: r[2] < BAR and r[3] >= BAR),
                (f"own<{BAR} & other>=0.50 & margin>=0.15 (PROPOSED)", lambda r: r[2] < BAR and r[3] >= 0.50 and r[3] - r[2] >= 0.15)):
    hits = [r for r in mis_rows if fn(r)]
    say(f"  {lab}: {pct(len(hits), len(mis_rows))}")
    for r in sorted(hits, key=lambda r: r[2] - r[3])[:12]:
        say(f"     {r[0]:6s} own {r[2]:.2f} in '{r[1]}'  -> best other {r[3]:.2f} '{r[4]}'")

say("\n## M2 HOMELESS CO-MOVERS — strong or recently-themed names in NO live theme that fit one")
recent_themed = set()
for r in hist:
    if r["date"] >= date(2026, 8, 26) and r["stage"] != "Retired":
        recent_themed.update(r["tickers"])
pop = [t for t in universe if not themed.get(t) and ((scores[t]["rs"] or 0) >= 70 or t in recent_themed)]
say(f"population = un-themed AND (RS composite >= 70 OR in a live-board theme row since 08-26): n={len(pop)} "
    f"({sum((scores[t]['rs'] or 0) >= 70 for t in pop)} by RS, {sum(t in recent_themed for t in pop)} recently themed)")
homeless = []
for t in pop:
    top = best_two(t, set())
    if top:
        homeless.append((t, top[0][0], top[0][1], top[1][0] if len(top) > 1 else -1, scores[t]["rs"]))
grid = [(BAR, 0.0), (BAR, 0.15), (0.50, 0.0), (0.50, 0.15)]
for bar, mg in grid:
    hits = [h for h in homeless if h[1] >= bar and h[1] - h[3] >= mg]
    say(f"  best fit >= {bar:.2f} & margin over runner-up >= {mg:.2f}: {pct(len(hits), len(homeless))}")
hits = sorted([h for h in homeless if h[1] >= 0.50 and h[1] - h[3] >= 0.15], key=lambda h: -h[1])
for lab, sub in (("RS>=70", [h for h in hits if (h[4] or 0) >= 70]), ("recently themed, RS<70", [h for h in hits if (h[4] or 0) < 70])):
    say(f"   of the {len(hits)} flagged: {lab} -> {len(sub)}")
rs_pop = [h for h in homeless if (h[4] or 0) >= 70]
for bar, mg in grid:
    say(f"  RS>=70 only (n={len(rs_pop)}): best >= {bar:.2f} & margin >= {mg:.2f}: "
        f"{pct(sum(1 for h in rs_pop if h[1] >= bar and h[1] - h[3] >= mg), len(rs_pop))}")
for h in hits[:25]:
    say(f"     {h[0]:6s} RS {h[4]:5.1f}  fit {h[1]:.2f} '{h[2]}' (runner-up {h[3]:.2f})")
for t in ("CORZ", "WULF", "APLD", "IREN", "CIFR", "HUT"):
    top = best_two(t, set())
    say(f"   #491 name {t}: themes {sorted(themed.get(t, []))}; best {top[0][0]:.2f} '{top[0][1]}', runner-up {top[1][0]:.2f} '{top[1][1]}'")
# control: the same best-of-many statistic on RANDOM un-themed low-RS names (what noise reads)
ctrl_pool = [t for t in universe if not themed.get(t) and (scores[t]["rs"] or 0) < 50 and t not in recent_themed]
ctrl = random.sample(ctrl_pool, min(300, len(ctrl_pool)))
cres = []
for t in ctrl:
    top = best_two(t, set())
    if top:
        cres.append((top[0][0], top[1][0] if len(top) > 1 else -1))
for bar, mg in grid:
    say(f"  CONTROL random un-themed RS<50 names (n={len(cres)}): best >= {bar:.2f} & margin >= {mg:.2f}: "
        f"{pct(sum(1 for a, b in cres if a >= bar and a - b >= mg), len(cres))}")

# ═══════════════════════════════════════════════════════════════════════════════════════════════
# STAGE I — IDENTITY: is the DRIVER the name claims the one the tape shows, and is the name settled?
# ═══════════════════════════════════════════════════════════════════════════════════════════════
say("\n## I1 PRICED-DRIVER LEG — a theme whose NAME claims a priced driver must co-move with that driver")
DRIVERS = [  # stated in advance; a name matching none of these is out of this leg's reach (said below)
    (r"bitcoin|crypto|\bbtc\b|digital asset", "IBIT"),   # IBIT, not crypto_daily_closes: that table's date D is ~20:00 ET of D-1's
                                                           # equity session (IBIT vs BTC = 0.26 aligned by date, 0.96 shifted one day)
    (r"gold|precious", "GLD"),
    (r"silver", "SLV"),
    (r"uranium", "URA"),
    (r"copper", "COPX"),
    (r"crude|\boil\b|tanker|petroleum", "USO"),
]


def driver_for(name: str):
    for rx, px in DRIVERS:
        if re.search(rx, name, re.I):
            return px
    return None


def basket_mean(tickers, exd, min_members=2):
    b = basket_of("x", tickers, exd, min_members=min_members)
    return (b, b.mean_all) if b else (None, None)


drv_rows = []
for th in board:
    px = driver_for(th["name"])
    if not px:
        continue
    b, mean = basket_mean(th["tickers"], ex, 2)
    if b is None or px not in ex:
        drv_rows.append((th["name"], px, None, None, None)); continue
    dfit = vec_corr(mean, ex[px])
    # the strongest competing live theme (basket-to-basket), excluding themes sharing a member
    comp = []
    for n2, b2 in live_b.items():
        if n2 == th["name"] or set(b2.members) & set(th["tickers"]):
            continue
        c = vec_corr(mean, b2.mean_all)
        if c is not None:
            comp.append((c, n2))
    comp.sort(reverse=True)
    drv_rows.append((th["name"], px, dfit, comp[0] if comp else None, len(b.members)))
say(f"live themes whose name names a priced driver: {len(drv_rows)} of {n_b} (the rest are OUT OF REACH of this leg)")
for n, px, dfit, comp, k in drv_rows:
    flag = "FAIL" if dfit is not None and dfit < BAR else ("pass" if dfit is not None else "n/a")
    cs = f"best competing theme {comp[0]:.2f} '{comp[1]}'" if comp else ""
    say(f"   {flag:4s} driver {px:4s} fit {dfit if dfit is None else round(dfit, 2)}  n={k}  '{n}'  | {cs}")

say("\n## I1r RELATIVE IDENTITY RULE — the named driver must explain the group at least as well as any live theme with a DIFFERENT driver")
say("   theme flag: best different-driver theme fit >= named-driver fit + 0.15; member flag: member's other-theme fit >= 0.50 and >= its driver fit + 0.15")


def identity_rows(board_, exd, live_baskets):
    out = []
    for th in board_:
        px = driver_for(th["name"])
        if not px or px not in exd:
            continue
        b, mean = basket_mean(th["tickers"], exd, 2)
        if b is None:
            continue
        dfit = vec_corr(mean, exd[px])
        comp = []
        for n2, b2 in live_baskets.items():
            if n2 == th["name"] or driver_for(n2) == px or set(b2.members) & set(th["tickers"]):
                continue
            c = vec_corr(mean, b2.mean_all)
            if c is not None:
                comp.append((c, n2, b2))
        comp.sort(key=lambda x: -x[0])
        top = comp[0] if comp else None
        mflags = []
        for m in b.members:
            dm = vec_corr(exd[m], exd[px])
            best_m = None
            for c, n2, b2 in comp:
                v = fit(m, b2, exd)
                if v is not None and (best_m is None or v > best_m[0]):
                    best_m = (v, n2)
            if dm is not None and best_m and best_m[0] >= 0.50 and best_m[0] - dm >= 0.15:
                mflags.append((m, dm, best_m[0], best_m[1]))
        out.append({"name": th["name"], "px": px, "dfit": dfit, "top": (top[0], top[1]) if top else None,
                    "flag": bool(top and dfit is not None and top[0] - dfit >= 0.15), "n": len(b.members), "mflags": mflags})
    return out


idr = identity_rows(board, ex, live_b)
say(f"   themes in reach: {len(idr)}; theme-level FLAG: {pct(sum(r['flag'] for r in idr), len(idr))}")
for r in idr:
    t = f"{r['top'][0]:.2f} '{r['top'][1]}'" if r["top"] else "-"
    say(f"   {'FLAG' if r['flag'] else 'ok  '} {r['px']:4s} driver {r['dfit']:.2f} vs {t}  | members flagged {len(r['mflags'])} of {r['n']}: "
        + ", ".join(f"{m}({d:.2f}->{o:.2f})" for m, d, o, _ in r["mflags"]) + f"  '{r['name']}'")

say("\n## I1b THE #491 CASE, member by member — fit to BTC vs fit to the live AI-compute theme vs the pure-bitcoin proxies")
MINERS = ["HUT", "IREN", "CIFR", "CORZ", "WULF", "CLSK", "BTDR", "APLD", "RIOT", "MARA", "IOND", "ABTC"]
AI_TH = "Emerging AI Compute & Cloud Infrastructure Platforms"
BTC_TH = "Bitcoin Balance Sheet Proxies"
MIN_TH = "Bitcoin Mining Stocks Rotation Reversal"
for when in (date(2026, 5, 1), date(2026, 6, 1), date(2026, 7, 1), date(2026, 8, 1), date(2026, 9, 1), RUN_DATE):
    exw = excess_at(when)
    ai_b = basket_of(AI_TH, next(t for t in board if t["name"] == AI_TH)["tickers"], exw)
    bt_b = basket_of(BTC_TH, next(t for t in board if t["name"] == BTC_TH)["tickers"], exw)
    mb, mmean = basket_mean([m for m in MINERS if m not in ("APLD",)], exw, 3)
    row = []
    for m in MINERS:
        a = fit(m, ai_b, exw); btc = vec_corr(exw[m], exw["IBIT"]) if m in exw and "IBIT" in exw else None
        pb = fit(m, bt_b, exw)
        row.append(f"{m}:btc {btc if btc is None else f'{btc:.2f}'}/ai {a if a is None else f'{a:.2f}'}/mstr {pb if pb is None else f'{pb:.2f}'}")
    gb = vec_corr(mmean, exw["IBIT"]) if mmean is not None else None
    ga = vec_corr(mmean, ai_b.mean_all) if (mmean is not None and ai_b) else None
    gp = vec_corr(mmean, bt_b.mean_all) if (mmean is not None and bt_b) else None
    say(f"  window before {when}: MINERS BASKET (11 ex-APLD) vs bitcoin (IBIT) {gb if gb is None else f'{gb:.2f}'} | vs AI-compute theme {ga if ga is None else f'{ga:.2f}'} "
        f"| vs bitcoin-proxy theme (MSTR/COIN/..) {gp if gp is None else f'{gp:.2f}'}")
    if when in (date(2026, 6, 1), RUN_DATE):
        say("      " + "  ".join(row))

say("\n## I1h WHEN WOULD THE RELATIVE IDENTITY RULE HAVE FIRED ON THE #491 COHORT? (board as of each date, window strictly before it)")


def board_at(d: date):
    latest = {}
    for r in hist:
        if d - timedelta(days=7) <= r["date"] <= d:
            if r["name"] not in latest or r["date"] > latest[r["name"]]["date"]:
                latest[r["name"]] = r
    return [r for r in latest.values() if r["stage"] != "Retired" and r["tickers"]]


def identity_on(d: date, pred):
    b_ = board_at(d)
    exd = excess_at(d + timedelta(days=1))
    lb = {}
    for r in b_:
        bb = basket_of(r["name"], r["tickers"], exd)
        if bb is not None:
            lb[r["name"]] = bb
    return [x for x in identity_rows([r for r in b_ if pred(r)], exd, lb)]


hist_dates = sorted({r["date"] for r in hist if r["date"] >= date(2026, 5, 4)})
fires = []
for d in hist_dates:
    rows = identity_on(d, lambda r: len(set(r["tickers"]) & set(MINERS)) >= 3)
    if rows:
        fires.append((d, any(x["flag"] for x in rows), rows))
first_fire = next((d for d, f, _ in fires if f), None)
say(f"   board dates with a priced-driver-named theme holding >=3 of the cohort: {len(fires)}; FLAGGED on {pct(sum(f for _, f, _ in fires), len(fires))}; first flag {first_fire}")
by_month = defaultdict(lambda: [0, 0])
for d, f, _ in fires:
    by_month[d.strftime("%Y-%m")][0] += f
    by_month[d.strftime("%Y-%m")][1] += 1
say("   by month (flagged / nights in reach): " + ", ".join(f"{m} {a}/{b}" for m, (a, b) in sorted(by_month.items())))
for d, f, rows in fires[::max(1, len(fires) // 12)]:
    for x in rows:
        t = f"{x['top'][0]:.2f} '{x['top'][1][:45]}'" if x["top"] else "-"
        say(f"      {d} {'FLAG' if x['flag'] else 'ok  '} driver {x['dfit'] if x['dfit'] is None else round(x['dfit'], 2)} vs {t} | '{x['name'][:55]}' members flagged {len(x['mflags'])} of {x['n']}")
# false-flag scan: every priced-driver theme on every board date since 05-04
allflags = Counter(); alln = Counter()
for d in hist_dates[::5]:
    for x in identity_on(d, lambda r: driver_for(r["name"]) is not None):
        key = "491 cohort" if len(set(next(r for r in board_at(d) if r["name"] == x["name"])["tickers"]) & set(MINERS)) >= 3 else x["px"]
        allflags[key] += x["flag"]; alln[key] += 1
say("   every priced-driver theme, every 5th board date since 05-04 (flagged / theme-nights): "
    + ", ".join(f"{k} {allflags[k]}/{alln[k]}" for k in sorted(alln)))

say("\n## I2 IDENTITY SETTLED? — distinct names the SYSTEM gave one cohort in the last 30 days (live rows + its own shadow proposals)")


def cohort_names(tickers, until: date, days: int = 30):
    T = set(tickers)
    names_live, names_sh = set(), set()
    for r in hist:
        if until - timedelta(days=days) <= r["date"] <= until and r["stage"] != "Retired" and r["tickers"]:
            S = set(r["tickers"]); sh = len(S & T)
            if sh >= 2 and sh / min(len(S), len(T)) >= 0.5:
                names_live.add(r["name"])
    for r in shadow:
        if until - timedelta(days=days) <= r["date"] <= until and r["tickers"]:
            S = set(r["tickers"]); sh = len(S & T)
            if sh >= 2 and sh / min(len(S), len(T)) >= 0.5:
                names_sh.add(r["name"])
    return names_live, names_sh


dist = []
for th in board:
    nl, ns = cohort_names(th["tickers"], date(2026, 9, 25))
    th["n_names"] = len(nl | ns)
    th["n_names_live"] = len(nl)
    dist.append((len(nl | ns), len(nl), th["name"], len(th["tickers"])))
dist.sort(reverse=True)
say(f"per live theme, distinct names (live+shadow) for its cohort over 30d: median {med([d[0] for d in dist])}, "
    f"p90 {q([d[0] for d in dist], .9):.0f}, max {dist[0][0]} (n={len(dist)})")
for k in (3, 4, 5, 6):
    say(f"   >= {k} names: {pct(sum(d[0] >= k for d in dist), len(dist))}")
for d in dist[:14]:
    say(f"   {d[0]:2d} names ({d[1]} live) — '{d[2]}' ({d[3]} members)")
nl, ns = cohort_names(next(t for t in board if t["name"] == MIN_TH)["tickers"], date(2026, 9, 25))
say(f"#491 cohort '{MIN_TH}': {len(nl)} live names + {len(ns - nl)} other shadow names in 30d:")
for n in sorted(nl | ns):
    say(f"      {'L' if n in nl else 'S'}  {n}")

say("\n## I3 SPLIT CLAIM — a ticker held by two live themes whose baskets do NOT move together")
multi = [(t, sorted(ns_)) for t, ns_ in themed.items() if len(ns_) >= 2]
split = []
for t, ns_ in multi:
    for i, a in enumerate(ns_):
        for b in ns_[i + 1:]:
            ba = basket_of(a, [m for m in next(x for x in board if x["name"] == a)["tickers"] if m != t], ex, 2)
            bb = basket_of(b, [m for m in next(x for x in board if x["name"] == b)["tickers"] if m != t], ex, 2)
            c = vec_corr(ba.mean_all, bb.mean_all) if ba and bb else None
            fa = vec_corr(ex[t], ba.mean_all) if (ba and t in ex) else None
            fb = vec_corr(ex[t], bb.mean_all) if (bb and t in ex) else None
            split.append((t, a, b, c, fa, fb))
say(f"tickers in >=2 live themes: {len(multi)}; theme-pairs they bridge: {len(split)}")
bad = [s for s in split if s[3] is not None and s[3] < BAR]
say(f"bridged pairs whose two baskets (ticker left out) correlate < {BAR}: {pct(len(bad), sum(1 for s in split if s[3] is not None))}")
for s in sorted(bad, key=lambda s: s[3]):
    say(f"   {s[0]:6s} baskets {s[3]:.2f} | fits {s[4] if s[4] is None else round(s[4],2)} '{s[1]}' / {s[5] if s[5] is None else round(s[5],2)} '{s[2]}'")

# ═══════════════════════════════════════════════════════════════════════════════════════════════
# STAGE S — SOURCES -> BIRTH: strong groups the tape shows that NO theme covers
# ═══════════════════════════════════════════════════════════════════════════════════════════════
say("\n## S1 UNNAMED PERSISTENT GROUPS — stored clusters (uncovered by construction) chained day to day")
cl_by_date: dict[date, dict[str, set]] = defaultdict(lambda: defaultdict(set))
for ln in open(HERE / "funnel_clusters.psv"):
    p = ln.rstrip("\n").split("|")
    cl_by_date[d_(p[0])][p[1]].add(p[2])
spy_sessions = sorted(closes["SPY"])
sidx = {d: i for i, d in enumerate(spy_sessions)}
cdates = sorted(cl_by_date)
lin_of: dict[tuple, int] = {}
lins: list[dict] = []
prev = None
for d in cdates:
    for h, tk in cl_by_date[d].items():
        link = None
        if prev and (d - prev).days <= 7:
            best = 0
            for h0, tk0 in cl_by_date[prev].items():
                s = len(tk & tk0) / len(tk)
                if s >= 0.5 and s > best:
                    best, link = s, lin_of[(prev, h0)]
        if link is None:
            lins.append({"first": d, "last": d, "days": 1, "tickers": set(tk), "last_tk": set(tk)})
            link = len(lins) - 1
        else:
            L = lins[link]; L["last"] = d; L["days"] += 1; L["tickers"] |= tk; L["last_tk"] = set(tk)
        lin_of[(d, h)] = link
    prev = d
board_on = defaultdict(list)
for r in hist:
    if r["stage"] != "Retired" and r["tickers"]:
        board_on[r["date"]].append(set(r["tickers"]))


def covered_that_night(tk: set, d: date) -> bool:
    return any(len(tk & T) / len(tk) >= 0.5 for T in board_on.get(d, []))


last_cd = cdates[-1]
alive_all = [L for L in lins if L["last"] == last_cd]
alive = [L for L in alive_all if not covered_that_night(L["last_tk"], last_cd)]
say(f"   (stored clusters are deduped against the board BEFORE that night's births; {len(alive_all) - len(alive)} of "
    f"{len(alive_all)} alive on {last_cd} were named the same night and are excluded)")
say(f"cluster days {cdates[0]}..{last_cd}; cluster-lineages {len(lins)}; alive on {last_cd}: {len(alive)}")
for L in sorted(alive, key=lambda L: L["first"]):
    age = sidx[last_cd] - sidx[L["first"]]
    say(f"   age {age:3d} sessions ({L['days']} stored days), {len(L['last_tk'])} names: {','.join(sorted(L['last_tk']))}")
for k in (5, 10, 20):
    say(f"   alive on {last_cd} and aged >= {k} sessions: {sum(1 for L in alive if sidx[last_cd] - sidx[L['first']] >= k)}")
# nightly history of the same read, last 20 cluster days
say("   same read per night (alive & aged >= 5 sessions):")
row = []
for d in cdates[-15:]:
    al = [L for L in lins if L["first"] <= d and L["last"] >= d and any(dd == d for dd in [d])]
    # a lineage is alive on d if it has a stored cluster ON d
    al = [lins[lin_of[(d, h)]] for h in cl_by_date[d] if not covered_that_night(cl_by_date[d][h], d)]
    row.append(f"{d.strftime('%m-%d')}:{sum(1 for L in {id(x): x for x in al}.values() if sidx[d] - sidx[L['first']] >= 5)}/{len(cl_by_date[d])}")
say("   " + " ".join(row))

# ═══════════════════════════════════════════════════════════════════════════════════════════════
# STAGE R — MATURING / RETIRING: churn
# ═══════════════════════════════════════════════════════════════════════════════════════════════
say("\n## R1 CHURN per ISO week (mi_audit_log rows; one row = one theme event)")
GROUPS = {
    "absorb": ("theme_pass1_5_absorption", "theme_sector_cap_dropped"),
    "merge": ("theme_thesis_merged", "theme_subtheme_route_merge"),
    "rename": ("theme_renamed_for_continuity", "theme_renamed_on_mass_flag"),
    "born": ("theme_discovered", "shadow_themes_promoted"),
    "retired": ("theme_retired", "theme_auto_retired"),
}
wk = defaultdict(Counter)
for ln in open(HERE / "funnel_churn_events.psv"):
    p = ln.rstrip("\n").split("|", 2)
    d = d_(p[0]); iso = d.isocalendar()
    for g, evs in GROUPS.items():
        if p[1] in evs:
            wk[f"{iso[0]}-W{iso[1]:02d}"][g] += 1
say("   week      absorb merge rename | absorb+merge+rename | born retired")
for w in sorted(wk):
    c = wk[w]
    say(f"   {w}   {c['absorb']:5d} {c['merge']:5d} {c['rename']:6d} | {c['absorb'] + c['merge'] + c['rename']:19d} | {c['born']:4d} {c['retired']:7d}")
last6 = sorted(wk)[-7:-1]   # complete weeks only (the current week is partial)
say(f"   complete weeks {last6[0]}..{last6[-1]}: identity-churn (absorb+merge+rename) mean "
    f"{statistics.mean(wk[w]['absorb'] + wk[w]['merge'] + wk[w]['rename'] for w in last6):.1f}/week")

# ═══════════════════════════════════════════════════════════════════════════════════════════════
# STEP 2 — NAMING LATENCY: a stored cluster holding >= half the founders, how long before birth?
# ═══════════════════════════════════════════════════════════════════════════════════════════════
say("\n## L1 NAMING LATENCY — births since 2026-06-01 (lineage = rename table + Jaccard >= 0.4 vs names alive in the prior 10 days)")
names = defaultdict(list)
for r in hist:
    names[r["name"]].append(r)
for n in names:
    names[n].sort(key=lambda r: r["date"])
parent = {}


def find(x):
    while parent.get(x, x) != x:
        x = parent[x]
    return x


for ln in open(HERE / "funnel_renames.psv"):
    o, nw, *_ = ln.rstrip("\n").split("|")
    if o in names and nw in names:
        parent[find(nw)] = find(o)
# rename edges from the audit log too (advisor 2026-09-27): continuity renames ('A' → 'B' in detail) and #214 mass-flag
# renames ('A' renamed to 'B' in summary) — a rename whose member set drifted past Jaccard 0.4 would otherwise read as a death
n_edge = 0
for ln in open(HERE / "funnel_rename_events.psv"):
    txt = ln.rstrip("\n")
    for o, nw in re.findall(r"'([^']+)' → '([^']+)'", txt) + re.findall(r"'([^']+)' renamed to '([^']+)'", txt):
        if o in names and nw in names:
            parent[find(nw)] = find(o); n_edge += 1
say(f"rename edges unioned: mi_theme_renames + {n_edge} from audit (continuity + mass-flag renames, names present since 05-01)")
by_date = defaultdict(list)
for n, rs in names.items():
    for r in rs:
        if r["tickers"] and r["stage"] != "Retired":
            by_date[r["date"]].append((n, r["tickers"]))
first_row = {}
for n, rs in names.items():
    live = [r for r in rs if r["stage"] != "Retired" and r["tickers"]]
    if live:
        first_row[n] = live[0]
for n, fr in first_row.items():
    d0, F = fr["date"], set(fr["tickers"])
    recent = {}
    for k in range(1, 11):
        for nm, tk in by_date.get(d0 - timedelta(days=k), []):
            if nm != n and nm not in recent:
                recent[nm] = tk
    best, bj = None, 0.0
    for nm, tk in recent.items():
        S = set(tk); j = len(F & S) / len(F | S)
        if j > bj:
            best, bj = nm, j
    if best and bj >= 0.4:
        parent[find(n)] = find(best)
groups = defaultdict(list)
for n in first_row:
    groups[find(n)].append(n)
births = []
for root, ns_ in groups.items():
    fr = min((first_row[n] for n in ns_), key=lambda r: (r["date"], r["id"]))
    if fr["date"] >= date(2026, 6, 1) and len(fr["tickers"]) >= 2 and fr["date"] in sidx:
        births.append(fr)
say(f"lineages with a first live row since 06-01: {len(births)} (names since 05-01 used for the 10-day look-back)")


def cluster_leads(F: set, bd: date):
    i0 = sidx[bd]
    hits = []
    for d in cdates:
        if d not in sidx or not (i0 - 40 <= sidx[d] < i0):
            continue
        for tk in cl_by_date[d].values():
            if len(tk & F) / len(F) >= 0.5:
                hits.append(i0 - sidx[d]); break
    same = any(len(tk & F) / len(F) >= 0.5 for tk in cl_by_date.get(bd, {}).values())
    return (max(hits) if hits else None, min(hits) if hits else None, same)


for b in births:
    b["lead_first"], b["lead_last"], b["same_night"] = cluster_leads(set(b["tickers"]), b["date"])


def lat_block(sub, lab):
    pre = [b for b in sub if b["lead_first"] is not None]
    lf = [b["lead_first"] for b in pre]; ll = [b["lead_last"] for b in pre]
    say(f"  {lab}: births n={len(sub)}; had a stored cluster holding >= half the founders BEFORE the birth day: "
        f"{pct(len(pre), len(sub))}; same-night only: {sum(1 for b in sub if b['lead_first'] is None and b['same_night'])}")
    if pre:
        say(f"     sessions from FIRST such cluster to birth: median {med(lf)}, p25 {q(lf, .25):.0f}, p75 {q(lf, .75):.0f}; "
            f"from the LAST one: median {med(ll)}; first-lead > 10 sessions: {pct(sum(x > 10 for x in lf), len(pre))}; "
            f"> 5: {pct(sum(x > 5 for x in lf), len(pre))}")


lat_block(births, "all births 06-01..09-25")
lat_block([b for b in births if b["date"] < date(2026, 8, 1)], "births Jun-Jul")
lat_block([b for b in births if date(2026, 8, 1) <= b["date"] < date(2026, 9, 1)], "births Aug")
lat_block([b for b in births if b["date"] >= date(2026, 8, 26)], "births last 30 days (08-26..09-25) = TODAY'S VALUE")
lat_block([b for b in births if b["date"] <= date(2026, 9, 4)], "births 06-01..09-04 (overlap with the 09-07 study)")
m491 = [b for b in births if len(set(b["tickers"]) & set(MINERS)) >= 2]
say(f"  #491 cohort births since 06-01 (>=2 miners among founders): n={len(m491)}")
for b in sorted(m491, key=lambda b: b["date"]):
    say(f"     {b['date']} lead_first={b['lead_first']} lead_last={b['lead_last']} same_night={b['same_night']} '{b['name']}' {','.join(b['tickers'])}")

# short-lived births: lineage has no live row >= 5 sessions after its birth (uncensored = born <= 5 sessions before the last board)
last_live = {}
for root, ns_ in groups.items():
    ds = [r["date"] for n in ns_ for r in names[n] if r["stage"] != "Retired" and r["tickers"]]
    last_live[root] = max(ds) if ds else None
root_of_birth = {}
for root, ns_ in groups.items():
    fr = min((first_row[n] for n in ns_), key=lambda r: (r["date"], r["id"]))
    root_of_birth[(fr["date"], fr["name"])] = root
last_board = max(r["date"] for r in hist)
unc = [b for b in births if sidx.get(last_board, 0) - sidx[b["date"]] >= 5]
for b in unc:
    ll = last_live[root_of_birth[(b["date"], b["name"])]]
    b["lived"] = sidx.get(ll, sidx[b["date"]]) - sidx[b["date"]] if ll in sidx else 0
for lab, sub in (("births 06-01..09-18", unc), ("births 08-26..09-18 (TODAY'S VALUE)", [b for b in unc if b["date"] >= date(2026, 8, 26)]),
                 ("births Jun-Jul", [b for b in unc if b["date"] < date(2026, 8, 1)])):
    say(f"  SHORT-LIVED — {lab}: lineage gone within 5 sessions of birth: {pct(sum(b['lived'] < 5 for b in sub), len(sub))}; "
        f"within 2: {pct(sum(b['lived'] < 2 for b in sub), len(sub))}")

# cross-validate against the 09-07 study's per-lineage table on overlapping births
try:
    import csv
    s3 = {}
    with open(REPO / "scripts/probes/_step3_theme_runway_lineages.tsv") as f:
        for r in csv.DictReader(f, delimiter="\t"):
            s3[(r["birth"], r["birth_name"])] = r
    agree = tot = 0
    for b in births:
        r = s3.get((str(b["date"]), b["name"]))
        if r is None:
            continue
        tot += 1
        theirs = r.get("ign_cl") or ""
        agree += (b["lead_first"] is not None) == (theirs not in ("", "None"))
    say(f"  cross-check vs the 09-07 study's lineage table (same birth date+name): matched {tot}; "
        f"'had a pre-birth cluster' agrees on {pct(agree, tot)} (theirs = eventual-member leg, mine = founders; expect <100%)")
except FileNotFoundError:
    say("  (09-07 lineage table not found)")

# ═══════════════════════════════════════════════════════════════════════════════════════════════
# CROSS-CHECK — his labels, read AFTER the rules above were fixed (they change nothing)
# ═══════════════════════════════════════════════════════════════════════════════════════════════
say("\n## X LABEL CROSS-CHECK — themed alert labels since 2026-05-01 against the rules above")
rows_by_name = names
xl = []
for ln in open(HERE / "funnel_labels.psv"):
    p = ln.rstrip("\n").split("|")
    t, ad, lab, note, tn, tn7 = p[0], d_(p[1]), p[3], p[4], p[5], p[6]
    if ad < date(2026, 5, 1) or lab not in ("y", "n"):
        continue
    T = tn7 or tn
    rs = [r for r in rows_by_name.get(T, []) if r["date"] <= ad and r["tickers"]]
    if not rs:
        xl.append((t, ad, lab, note, T, None, None, None, None)); continue
    mem = rs[-1]["tickers"]
    exd = excess_at(ad)
    b = basket_of(T, mem, exd)
    grp = None
    if b is not None:
        v = [fit(m, b, exd) for m in b.members]
        v = [x for x in v if x is not None]
        grp = med(v) if v else None
    tf = fit(t, b, exd) if b is not None else None
    drv = driver_for(T)
    dfit = None
    if drv:
        bb, mean = basket_mean(mem, exd, 2)
        dfit = vec_corr(mean, exd[drv]) if (mean is not None and drv in exd) else None
    nl, ns = cohort_names(mem, ad)
    xl.append((t, ad, lab, note, T, grp, tf, dfit, len(nl | ns)))
for lab in ("y", "n"):
    sub = [r for r in xl if r[2] == lab]
    g = [r for r in sub if r[5] is not None]
    f_ = [r for r in sub if r[6] is not None]
    say(f"  label {lab}: n={len(sub)}; theme judgeable {len(g)} -> grouping PASS {pct(sum(r[5] >= BAR for r in g), len(g))}; "
        f"ticker fit judgeable {len(f_)} -> ticker fit >= {BAR} {pct(sum(r[6] >= BAR for r in f_), len(f_))}; "
        f"identity-unsettled (>=4 names) {pct(sum((r[8] or 0) >= 4 for r in sub), len(sub))}")
say("  the #491 rows (his notes: 'crypto to AI'):")
for r in xl:
    if r[0] in MINERS:
        say(f"     {r[0]:5s} {r[1]} label={r[2]} theme='{r[4]}' grouping={r[5] if r[5] is None else round(r[5],2)} "
            f"ticker_fit={r[6] if r[6] is None else round(r[6],2)} driver_fit={r[7] if r[7] is None else round(r[7],2)} "
            f"names30d={r[8]} note='{r[3][:40]}'")
OUT.close()

# ── appendix: the non-#491 priced-driver flags, listed so each can be judged (every 5th board date) ──
OUT = open(HERE / "funnel_probe_out.txt", "a")
say("\n## I1f APPENDIX — every non-#491 priced-driver FLAG on every 5th board date since 05-04")
for d in hist_dates[::5]:
    b_ = board_at(d)
    for x in identity_on(d, lambda r: driver_for(r["name"]) is not None):
        mem = next(r for r in b_ if r["name"] == x["name"])["tickers"]
        if x["flag"] and len(set(mem) & set(MINERS)) < 3:
            say(f"   {d} {x['px']:4s} driver {x['dfit']:.2f} vs {x['top'][0]:.2f} '{x['top'][1][:40]}' | '{x['name'][:60]}' {','.join(mem[:10])}")
OUT.close()

# ── v2 of the named-driver lexicon: three fixes to the FALSE flags above, none touching the #491 bar ──
# (1) gold/silver/precious are ONE driver family (miners of either co-move at 0.9+), proxy = the better of GLD/SLV;
# (2) "tanker" dropped — freight rates, not the crude price, drive tankers; (3) a name that already names the move
# (pivot/convert/diversif/transition) is not claiming the old driver alone — it is skipped, never flagged.
OUT = open(HERE / "funnel_probe_out.txt", "a")
DRIVERS_V2 = [
    (r"bitcoin|crypto|\bbtc\b|digital asset", "IBIT"),
    (r"gold|silver|precious", "GLD|SLV"),
    (r"uranium", "URA"),
    (r"copper", "COPX"),
    (r"crude|\boil\b|petroleum", "USO"),
]
PIVOT = r"pivot|conver|diversif|transition"


def driver_v2(name):
    if re.search(PIVOT, name, re.I):
        return None
    for rx, px in DRIVERS_V2:
        if re.search(rx, name, re.I):
            return px
    return None


def dfit_v2(mean, exd, px):
    vals = [vec_corr(mean, exd[p]) for p in px.split("|") if p in exd]
    vals = [v for v in vals if v is not None]
    return max(vals) if vals else None


def identity_v2(board_, exd, live_baskets):
    out = []
    for th in board_:
        px = driver_v2(th["name"])
        if not px:
            continue
        b, mean = basket_mean(th["tickers"], exd, 2)
        if b is None:
            continue
        dfit = dfit_v2(mean, exd, px)
        comp = []
        for n2, b2 in live_baskets.items():
            if n2 == th["name"] or driver_v2(n2) == px or driver_for(n2) == (px if "|" not in px else "GLD") \
                    or (px == "GLD|SLV" and driver_for(n2) == "SLV") or set(b2.members) & set(th["tickers"]):
                continue
            c = vec_corr(mean, b2.mean_all)
            if c is not None:
                comp.append((c, n2, b2))
        comp.sort(key=lambda x: -x[0])
        top = comp[0] if comp else None
        mflags = []
        for m in b.members:
            dm = dfit_v2(exd[m], exd, px)
            best_m = None
            for c, n2, b2 in comp:
                v = fit(m, b2, exd)
                if v is not None and (best_m is None or v > best_m[0]):
                    best_m = (v, n2)
            if dm is not None and best_m and best_m[0] >= 0.50 and best_m[0] - dm >= 0.15:
                mflags.append((m, dm, best_m[0], best_m[1]))
        out.append({"name": th["name"], "px": px, "dfit": dfit, "top": (top[0], top[1]) if top else None,
                    "flag": bool(top and dfit is not None and top[0] - dfit >= 0.15), "n": len(b.members),
                    "mflags": mflags, "tickers": th["tickers"]})
    return out


say("\n## I1v2 NAMED-DRIVER CHECK, v2 lexicon — today's board")
v2 = identity_v2(board, ex, live_b)
say(f"   themes in reach: {len(v2)} of {n_b}; FLAG {pct(sum(x['flag'] for x in v2), len(v2))}")
for x in v2:
    t = f"{x['top'][0]:.2f} '{x['top'][1][:45]}'" if x["top"] else "-"
    say(f"   {'FLAG' if x['flag'] else 'ok  '} {x['px']:7s} driver {x['dfit']:.2f} vs {t} | members moving with another driver {len(x['mflags'])} of {x['n']}"
        + (": " + ", ".join(m for m, *_ in x["mflags"]) if x["mflags"] else "") + f"  '{x['name'][:60]}'")
cohort_n = Counter(); cohort_f = Counter()
for d in hist_dates:
    b_ = board_at(d)
    exd = excess_at(d + timedelta(days=1))
    lb = {r["name"]: bb for r in b_ for bb in [basket_of(r["name"], r["tickers"], exd)] if bb is not None}
    for x in identity_v2(b_, exd, lb):
        key = "491 cohort (>=2 of the miners)" if len(set(x["tickers"]) & set(MINERS)) >= 2 else "every other priced-driver theme"
        cohort_n[key] += 1; cohort_f[key] += x["flag"]
        if x["flag"] and key.startswith("every") and d.day % 3 == 0:
            say(f"      other-theme flag {d} {x['px']} {x['dfit']:.2f} vs {x['top'][0]:.2f} '{x['top'][1][:35]}' | '{x['name'][:50]}'")
say("   EVERY board date since 05-04: " + "; ".join(f"{k}: flagged {pct(cohort_f[k], cohort_n[k])} theme-nights" for k in sorted(cohort_n)))
OUT.close()

# ── labels vs the v2 named-driver check (cross-check only; run after the rule was fixed above) ──
OUT = open(HERE / "funnel_probe_out.txt", "a")
say("\n## X2 LABELS vs the NAMED-DRIVER CHECK (v2) — themed rows since 05-01 whose credited theme is in the check's reach")
for r in xl:
    t, ad, lab, note, T = r[0], r[1], r[2], r[3], r[4]
    if not driver_v2(T or ""):
        continue
    b_ = board_at(ad)
    exd = excess_at(ad)
    lb = {x["name"]: bb for x in b_ for bb in [basket_of(x["name"], x["tickers"], exd)] if bb is not None}
    row = [x for x in b_ if x["name"] == T]
    if not row:   # absorbed/retired by alert day: judge its latest LIVE row within 10 days (the credited membership)
        cand = [h for h in hist if h["name"] == T and h["stage"] != "Retired" and h["tickers"] and ad - timedelta(days=10) <= h["date"] <= ad]
        if not cand:
            say(f"   {t:5s} {ad} label={lab} theme '{T}' no live row within 10 days"); continue
        row = [max(cand, key=lambda h: h["date"])]
        lb.setdefault(T, basket_of(T, row[0]["tickers"], exd))
    res = identity_v2(row, exd, lb)
    if not res:
        say(f"   {t:5s} {ad} label={lab} theme '{T}' basket too thin"); continue
    x = res[0]
    mf = [m for m, *_ in x["mflags"]]
    say(f"   {t:5s} {ad} label={lab} {'FLAG' if x['flag'] else 'ok  '} driver {x['dfit']:.2f} vs "
        f"{x['top'][0]:.2f} '{x['top'][1][:35]}' | this ticker moving with another driver: {t in mf} | '{T[:45]}' note='{note[:30]}'")
OUT.close()

# ── robustness of the latency read: how many separate pre-birth sighting days sit behind each "first sighting"? ──
OUT = open(HERE / "funnel_probe_out.txt", "a")
say("\n## L2 LATENCY ROBUSTNESS — pre-birth sighting days per birth (40 sessions back, >= half the founders in one stored cluster)")


def sighting_days(F, bd):
    i0 = sidx[bd]; n = 0; lags = []
    for d in cdates:
        if d in sidx and i0 - 40 <= sidx[d] < i0 and any(len(tk & F) / len(F) >= 0.5 for tk in cl_by_date[d].values()):
            n += 1; lags.append(i0 - sidx[d])
    return n, lags


for lab, sub in (("births 08-26..09-25", [b for b in births if b["date"] >= date(2026, 8, 26)]), ("births 06-01..09-25", births)):
    pre = [b for b in sub if b["lead_first"] is not None]
    sd = [sighting_days(set(b["tickers"]), b["date"]) for b in pre]
    ns = [x[0] for x in sd]
    # the earliest sighting that has at least one more sighting within 10 sessions after it (not a lone early coincidence)
    firm = []
    for n, lags in sd:
        lags = sorted(lags, reverse=True)
        f = next((l for l in lags if any(0 < l - l2 <= 10 for l2 in lags)), None)
        firm.append(f if f is not None else min(lags))
    say(f"  {lab}: births with a pre-birth sighting n={len(pre)}; sighting days per birth median {med(ns)}, "
        f"1 only {sum(1 for x in ns if x == 1)}, >=3 {sum(1 for x in ns if x >= 3)}; "
        f"'firm' first sighting (followed by another within 10 sessions) -> naming: median {med(firm)}, >10: {pct(sum(1 for x in firm if x > 10), len(firm))}")
OUT.close()
