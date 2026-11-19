"""B6 fork-B backtest driver — executes docs/analysis/b6_forkB_backtest_prereg_2026-11-19.md.

READ-ONLY: reads the pull_* captures in this folder, imports the live scorer / filters and the
ep_replay harness, edits nothing, writes results.txt + campaigns.tsv here. $0, offline.
    python scripts/probes/_b6_backtest_1119/run_backtest.py > results.txt
"""
from __future__ import annotations

import gzip
import json
import re
import statistics
import sys
from collections import Counter, defaultdict
from datetime import date, datetime, time, timedelta
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[2]
sys.path.insert(0, str(REPO))

import scripts.ep_replay as ep  # noqa: E402
from agents.market_intelligence.ep_detector import _grade_floor_filters, _score_ep  # noqa: E402
from agents.market_intelligence.ep_rubric import (  # noqa: E402
    SCORE_WEIGHTS, apply_output_scale, resolve_conviction_floor,
)

PULL_DAY = date(2026, 11, 19)
ep.LAST_SETTLED = date(2026, 11, 18)          # last daily bar strictly before the pull day
RS = ep.ruleset_as_of(PULL_DAY)               # today's stack, applied to every campaign
POST = "2026-08-22"
SCALE = SCORE_WEIGHTS["output_scale"]
PTS = SCORE_WEIGHTS["catalyst"]["points"]
FLOOR_RULES = SCORE_WEIGHTS["conviction_floor"]["rules"]
MIN_GAP = 9.0
_f = ep._f


def P(*a):
    print(*a)


# ── loaders ──────────────────────────────────────────────────────────────────────────
s1 = ep.read_sections(HERE / "pull_1.out")
s2 = ep.read_sections(HERE / "pull_2_scanlog.out")
s3 = ep.read_sections(HERE / "pull_3_alerts_trades.out")


def load_min(name):
    by = {}
    with gzip.open(HERE / name, "rt") as fh:
        for line in fh:
            p = line.rstrip("\n").split("|")
            if len(p) != 7 or p[0] == "ticker":
                continue
            try:
                dt = datetime.strptime(p[1], "%Y-%m-%d %H:%M").replace(tzinfo=ep._ET)
            except ValueError:
                continue
            by.setdefault((p[0], dt.date()), []).append(
                {"m": dt, "o": float(p[2]), "h": float(p[3]), "l": float(p[4]), "c": float(p[5])})
    for b in by.values():
        b.sort(key=lambda x: x["m"])
    return by


minutes = load_min("pull_5_minutes_day0_post.out.gz")
minutes.update(load_min("pull_5_minutes_day0_pre.out.gz"))
daily: dict = {}
with gzip.open(HERE / "pull_4_daily.out.gz", "rt") as fh:
    for line in fh:
        p = line.rstrip("\n").split("|")
        if len(p) != 7 or p[0] == "ticker":
            continue
        try:
            d = date.fromisoformat(p[1])
        except ValueError:
            continue
        daily.setdefault(p[0], {})[d] = {"o": _f(p[2]), "h": _f(p[3]), "l": _f(p[4]),
                                         "c": _f(p[5]), "v": _f(p[6])}

# pull_6 (2026-11-19 follow-up): the scan ticks + flip events of real post-rescale alerts OUTSIDE
# the earnings population — same columns, same section names.
_p6 = HERE / "_pull_6.out"
_p6.write_text(gzip.open(HERE / "pull_6.out.gz", "rt").read())
s6 = ep.read_sections(_p6)
_p6.unlink()
s2["SCANLOG"] = s2["SCANLOG"] + s6["SCANLOG"]
s3["EVENTS"] = s3["EVENTS"] + s6["EVENTS"]
N_P6 = (len(s6["SCANLOG"]), len(s6["EVENTS"]))

regime = {r["regime_date"]: r for r in s1["REGIME"]}
ticks = defaultdict(list)
for r in s2["SCANLOG"]:
    ticks[(r["ticker"], r["scan_date"])].append(r)
for v in ticks.values():
    v.sort(key=lambda r: (r["scan_et"], int(r["id"])))

dg_first = {}       # (ticker, date) -> first composite downgrade event
for r in sorted(s1["DOWNGRADES"], key=lambda r: r["created_et"]):
    if r["reason"].startswith("rubric_composite_"):
        dg_first.setdefault((r["ticker"], r["alert_date"]), r)
other_dg = {(r["ticker"], r["alert_date"]) for r in s1["DOWNGRADES"]
            if not r["reason"].startswith("rubric_composite_")}
pop = {(r["ticker"], r["alert_date"]): r for r in s1["POP"]}
alerts = defaultdict(list)
for a in s3["ALERTS"]:
    alerts[(a["ticker"], a["alert_date"])].append(a)
trades = defaultdict(list)
for t in s3["TRADES"]:
    trades[(t["ticker"], t["alert_date"])].append(t)
events = defaultdict(list)
for e in s3["EVENTS"]:
    events[(e["ticker"], e["et_date"])].append(e)
rsadv = {(r["ticker"], r["alert_date"]): r for r in s3["RSADV"]}


def era(d):
    return "post" if d >= POST else "pre"


def regime_mult(d: str, prior=True):
    keys = sorted(k for k in regime if (k < d if prior else k <= d))
    return 1.2 if keys and regime[keys[-1]]["regime"] == "Bull" else 1.0


# ── re-scorer ────────────────────────────────────────────────────────────────────────
def worked_back(row):
    """(raw_sum_without_floor, multiplier, reproduces_stored) from a tick with a breakdown."""
    bd = json.loads(row["score_breakdown"])
    raw = sum(v for k, v in bd.items() if k != "conviction_floor")
    eff = raw + (bd.get("conviction_floor") or 0)
    stored = _f(row["ep_score"])
    best = None
    for m in (1.0, 1.2):
        got = apply_output_scale(round(eff * m, 1), SCALE)
        if best is None or abs(got - stored) < abs(best[1] - stored):
            best = (m, got)
    return bd, raw, best[0], abs(best[1] - stored) <= 0.1


def cf_score_from_tick(row, fq):
    """Counterfactual score for a scored tick whose stored acting grade is routine."""
    gap = _f(row["gap_pct"]) or 0.0
    if row["score_breakdown"]:
        bd, raw, m, ok = worked_back(row)
        cf_raw = raw - (bd.get("catalyst") or 0) + PTS.get(fq, 0)
        fl = resolve_conviction_floor(gap, fq, FLOOR_RULES)
        if fl is not None:
            cf_raw = max(cf_raw, fl)
        return apply_output_scale(round(cf_raw * m, 1), SCALE), ("exact" if ok else "exact_unreproduced")
    # no breakdown (08-22..08-28): additive on the stored score; multiplier from the regime table
    m = regime_mult(row["scan_date"])
    stored = _f(row["ep_score"])
    raw_m = (stored - SCALE["offset"]) / SCALE["mult"]          # = round(raw*m,1)
    cf_raw = raw_m / m + PTS.get(fq, 0)
    fl = resolve_conviction_floor(gap, fq, FLOOR_RULES)
    if fl is not None:
        cf_raw = max(cf_raw, fl)
    return apply_output_scale(round(cf_raw * m, 1), SCALE), "additive_no_breakdown"


def day_static(tk):
    """float / theme points from any scored tick of the same ticker-day (None = unknown)."""
    for r in tk:
        if r["score_breakdown"]:
            bd = json.loads(r["score_breakdown"])
            return bd.get("float", 0) > 0, bd.get("theme_bonus", 0) > 0, worked_back(r)[2]
    return None, None, None


def score_unscored_tick(row, fq, tk):
    """A post_grade_filter tick has no stored score: live _score_ep on stored inputs (band)."""
    fl, th, m = day_static(tk)
    if m is None:
        m = regime_mult(row["scan_date"])
    adv, pc = _f(row["adv"]), _f(row["prev_close"])
    out = []
    for flo in ([fl] if fl is not None else [False, True]):
        for the in ([th] if th is not None else [False, True]):
            s, _ = _score_ep(
                gap_pct=_f(row["gap_pct"]) or 0.0, rel_volume=_f(row["rel_volume"]) or 0.0,
                catalyst_quality=fq, profile={"floatShares": 1 if flo else 10**12},
                regime_multiplier=m,
                vol_percentile=_f(row["vol_percentile"]) if _f(row["vol_percentile"]) is not None else 50.0,
                projected_vol_multiple=_f(row["projected_vol_multiple"]),
                in_active_theme=the, adv_dollar=(adv * pc) if adv and pc else None,
                weights=SCORE_WEIGHTS)
            out.append(s)
    return min(out), max(out)


def tick_time(row):
    return datetime.strptime(row["scan_et"], "%Y-%m-%d %H:%M:%S")


def reconstruct(key, restore: str | None, from_et: str | None):
    """First HIGH tick for one ticker-day. restore=None -> factual (PASS arm).
    Returns dict(first_high: datetime|None, method, why, n_ticks, band_abstain)."""
    tk = ticks.get(key, [])
    out = {"first_high": None, "method": None, "why": Counter(), "n_ticks": len(tk),
           "band_abstain": False, "affected": 0, "cf_max": None}
    i0 = None
    if restore:
        ev_t = datetime.strptime(from_et, "%Y-%m-%d %H:%M:%S")
        prior = [i for i, r in enumerate(tk) if tick_time(r) <= ev_t]
        i0 = prior[-1] if prior else 0
    for i, r in enumerate(tk):
        bar = _f(r["ep_bar"]) or 65.0
        stage = r["reject_stage"]
        sc = _f(r["ep_score"])
        affected = restore is not None and i >= i0
        if affected:
            out["affected"] += 1
        if not affected or (r["catalyst_quality"] and r["catalyst_quality"] != "routine"):
            if sc is not None and sc >= bar:
                out.update(first_high=tick_time(r), method="factual")
                return out
            out["why"][stage or "scored_below_bar"] += 1
            continue
        # affected tick, stored acting grade routine (or ungraded)
        if sc is not None and r["catalyst_quality"] == "routine":
            cf, how = cf_score_from_tick(r, restore)
            out["cf_max"] = max(out["cf_max"] or -1e9, cf)
            if cf >= bar:
                out.update(first_high=tick_time(r), method=how)
                return out
            out["why"]["cf_below_bar"] += 1
            continue
        if stage == "post_grade_filter" and (r["filter_reason"].startswith("routine catalyst")
                                             or r["filter_reason"].startswith("pre-mkt volume")):
            skip = _grade_floor_filters(
                r["ticker"], restore, _f(r["gap_pct"]) or 0.0, int(_f(r["today_volume"]) or 0),
                _f(r["pm_rvol"]), lattice_acting=True)
            if skip is not None:
                out["why"]["post_grade_filter_still_fails"] += 1
                continue
            lo, hi = score_unscored_tick(r, restore, tk)
            out["cf_max"] = max(out["cf_max"] or -1e9, hi)
            if lo >= bar:
                out.update(first_high=tick_time(r), method="rescored_unscored_tick")
                return out
            if hi >= bar:
                out["band_abstain"] = True
                out["why"]["band_straddles_bar"] += 1
            else:
                out["why"]["cf_below_bar"] += 1
            continue
        out["why"][stage or "other"] += 1
    return out


OPEN_FLOOR_LIVE_FROM = date(2026, 11, 3)     # #715 toggle ON (magna53_ep.md change log 2026-11-03)
RT_GAP_RECHECK_FROM = date(2026, 8, 2)       # ep_rt_entry_gap_recheck went live (magna53_ep.md l.2516)
CHASE_CAP = 1.5                              # order_manager.CHASE_RISK_INFLATION_CAP default
from agents.market_intelligence.backtester.filters import validate_orb_entry  # noqa: E402
from agents.market_intelligence.broker.order_manager import profit_target_r_per_share  # noqa: E402


def prev_close_of(tkr, d):
    prior = [x for x in sorted(daily.get(tkr, {})) if x < d]
    return daily[tkr][prior[-1]]["c"] if prior else None


def open_below_floor(key):
    """entry_pipeline.check_flip_up_open_floor (#715): a flip-up admit whose 09:30 bar OPENED
    strictly below prev close x 1.09 (floor rounded to 6 dp, as live)."""
    if not any(e["event_type"] == "ep_rt_floor_flip_up" for e in events.get(key, [])):
        return False
    d = date.fromisoformat(key[1])
    b930 = next((b for b in minutes.get((key[0], d), []) if b["m"].time() == time(9, 30)), None)
    pc = prev_close_of(key[0], d)
    if not b930 or not pc or pc <= 0:
        return False            # live: unreadable -> proceeds
    return b930["o"] < round(pc * (1 + MIN_GAP / 100), 6)


def price_at_submit(bars, submit: time):
    """The latest trade at the submission moment, from stored minute bars: the OPEN of the first
    bar at or after the submit minute (within 2 minutes), else the close of the bar before it.
    None -> the live checks fail open."""
    nxt = next((b for b in bars if b["m"].time() >= submit), None)
    if nxt and (datetime.combine(date.min, nxt["m"].time()) - datetime.combine(date.min, submit)).seconds <= 120:
        return nxt["o"]
    prv = [b for b in bars if b["m"].time() < submit]
    return prv[-1]["c"] if prv else None


def walk(key, submit: time, era_correct=False, gates=True):
    """One campaign through the LIVE submission order (entry_pipeline.submit_trade_entry):
    window -> 4a open-below-floor (#715) -> 4b real-time gap re-check (#490) -> ORB validation ->
    order pick (order_manager._pick_entry: last trade over the ORB high = the #500 limit-buy at
    price x 1.002 under the 1.5x chase cap; else the stop-limit bracket = harness walk_campaign).
    era_correct=True applies 4a / 4b only from the date each went live (check 4, vs real rows);
    False applies today's rules to every date (the arms — prereg). gates=False = upper bound."""
    tkr, ds = key
    d = date.fromisoformat(ds)
    res = {"ticker": tkr, "alert_date": ds, "submit": submit.strftime("%H:%M"), "entry_type": None,
           "entered": False, "entry_px": None, "stop": None, "realized_r": None, "mark_r": None,
           "final_reason": None, "partial_fired": None}
    if submit >= time(9, 45):
        res.update(status="no_trade", reason="window_out_of_orb")
        return res
    bars0 = minutes.get((tkr, d), [])
    pc = prev_close_of(tkr, d)
    px = price_at_submit(bars0, submit)
    if gates:
        if (not era_correct or d >= OPEN_FLOOR_LIVE_FROM) and open_below_floor(key):
            res.update(status="no_trade", reason="open_below_gap_floor")
            return res
        if (not era_correct or d >= RT_GAP_RECHECK_FROM) and pc and px and px > 0 \
                and (px - pc) / pc * 100 < MIN_GAP:
            res.update(status="no_trade", reason="gap_below_floor_at_submit")
            return res
    atr = ep.atr14_abs(daily.get(tkr, {}), d)
    orb = next((b for b in bars0 if b["m"].time() == time(9, 30)), None)
    if orb and px is not None and px > orb["h"]:
        # ── #500 price-aware entry ──
        ok, skip = validate_orb_entry(orb["h"], orb["l"], atr)
        if not ok:
            res.update(status="no_trade", reason=(skip or "").split(":")[0] + ":" + (skip or "").split(":")[1].strip().split(" ")[0] if skip and ":" in skip else skip)
            return res
        dbars = daily.get(tkr, {})
        adr_pct, _n = ep.adr20_pct(dbars, d)
        adr_dollar = adr_pct * orb["h"] if adr_pct else None
        stop = RS.stop_price(orb["h"], orb["l"], adr_dollar)
        limit = round(px * 1.002, 2)
        planned, actual = orb["h"] - stop, limit - stop
        res.update(entry_type="limit_fallback", stop=stop)
        if not (planned > 0 and actual <= CHASE_CAP * planned):
            res.update(status="no_trade", reason="chase_cap_exceeded")
            return res
        window = [b for b in bars0 if submit <= b["m"].time() < time(10, 0)]
        fb = next((b for b in window if b["l"] <= limit), None)
        if fb is None:
            res.update(status="no_entry", reason="fallback_limit_never_filled")
            return res
        entry_px = min(limit, fb["o"])
        r_ps = profit_target_r_per_share("magna53", entry_px, stop, orb["l"])
        target = entry_px + RS.intraday_partial_r * r_ps if (RS.intraday_partial_r and r_ps is not None) else None
        leg = ep._walk_leg(ticker=tkr, leg_date=d, entry_px=entry_px, stop=stop, target=target,
                           target2=None, bars=bars0, fill_idx=bars0.index(fb), rs=RS, daily=daily,
                           shares=None, integer_shares=False, adr_dollar=adr_dollar,
                           minutes_extra={}, r_frame_ps=r_ps)
        res.update(entered=True, entry_px=entry_px,
                   **{k: leg[k] for k in ("status", "reason", "realized_r", "mark_r", "final_reason", "partial_fired")})
        return res
    w = ep.walk_campaign(ticker=tkr, alert_date=d, rs=RS, minutes=minutes, daily=daily,
                         submit=submit, atr_14=atr)
    res.update({k: w[k] for k in ("status", "reason", "entered", "entry_px", "stop",
                                  "realized_r", "mark_r", "final_reason", "partial_fired")})
    res["entry_type"] = "stop_limit"
    if w["status"] == "no_trade" and w["reason"] and ":" in w["reason"]:
        res["reason"] = w["reason"].split(":")[0] + ":" + w["reason"].split(":")[1].strip().split(" ")[0]
    return res


def submit_of(first_high: datetime) -> time:
    t = time(first_high.hour, first_high.minute)
    return max(time(9, 31), t)


def r_of(c):
    return c["realized_r"] if c["status"] == "settled" else c.get("mark_r")


def degenerate(c):
    try:
        return abs(c["entry_px"] - c["stop"]) / c["entry_px"] * 100 < 0.5
    except (TypeError, KeyError, ZeroDivisionError):
        return False


def week(ds):
    y, w, _ = date.fromisoformat(ds).isocalendar()
    return f"{y}-W{w:02d}"


def summarize(label, camps, names_n=None, verbose=True):
    n = len(camps)
    st = Counter(c["status"] for c in camps)
    ent = [c for c in camps if c["status"] in ("settled", "open_at_horizon") and not degenerate(c)]
    deg = [c for c in camps if c["status"] in ("settled", "open_at_horizon") and degenerate(c)]
    settled = [c for c in ent if c["status"] == "settled"]
    opn = [c for c in ent if c["status"] == "open_at_horizon"]
    ab = st.get("abstain", 0)
    P(f"\n[{label}] campaigns walked {n}" + (f" (of {names_n} names)" if names_n is not None else ""))
    P(f"  ABSTAIN {ab} of {n} ({(ab / n * 100) if n else 0:.0f}%)  "
      f"reasons {dict(Counter((c['reason'] or '').split(':')[0] for c in camps if c['status'] == 'abstain'))}")
    P(f"  funnel: entered {len(ent)} (settled {len(settled)}, open {len(opn)}), "
      f"no_entry {st.get('no_entry', 0)}, no_trade {st.get('no_trade', 0)} "
      f"{dict(Counter(c['reason'] for c in camps if c['status'] == 'no_trade'))}"
      + (f", near-zero-stop excluded {len(deg)}" if deg else ""))
    rs_ = [c["realized_r"] for c in settled]
    allr = [r_of(c) for c in ent if r_of(c) is not None]
    out = {"n_entered": len(ent), "n_settled": len(settled), "ge3": 0, "ge3_open": 0,
           "sum": 0.0, "mean": None, "share3": None, "abstain_rate": (ab / n) if n else 0.0,
           "weeks3": set(), "sum_ex_best_week": None}
    if not ent:
        return out
    ge3 = sum(1 for x in rs_ if x >= 3)
    ge3o = sum(1 for x in allr if x >= 3)
    out.update(ge3=ge3, ge3_open=ge3o, sum=sum(allr), mean=statistics.mean(allr),
               share3=ge3o / len(ent))
    P(f"  TAIL (settled): >=3R {ge3}  >=5R {sum(1 for x in rs_ if x >= 5)}  "
      f"best {max(rs_) if rs_ else float('nan'):+.2f}R  share>=3R {ge3 / len(settled) * 100 if settled else 0:.0f}%"
      f"   | incl. open marks: >=3R {ge3o} of {len(ent)} ({ge3o / len(ent) * 100:.0f}%)")
    P(f"  BOTH WAYS (entered, open at mark): losers<=-0.9R {sum(1 for x in allr if x <= -0.9)}  "
      f"negative {sum(1 for x in allr if x < 0)}  positive {sum(1 for x in allr if x > 0)}  "
      f"total {sum(allr):+.2f}R  mean {statistics.mean(allr):+.2f}R  median {statistics.median(allr):+.2f}R")
    if opn:
        P("  still open: " + ", ".join(f"{c['ticker']} {c['alert_date']} mark {c['mark_r']:+.2f}R" for c in opn))
    wk = defaultdict(list)
    for c in ent:
        if r_of(c) is not None:
            wk[week(c["alert_date"])].append(r_of(c))
    out["weeks3"] = {w for w, v in wk.items() if any(x >= 3 for x in v)}
    if wk:
        best = max(wk, key=lambda w: sum(wk[w]))
        out["sum_ex_best_week"] = sum(allr) - sum(wk[best])
        if verbose:
            P("  per alert week: " + "  ".join(
                f"{w}: n{len(v)} >=3R {sum(1 for x in v if x >= 3)} {sum(v):+.1f}R" for w, v in sorted(wk.items())))
            P(f"  total without best week ({best}): {out['sum_ex_best_week']:+.2f}R; "
              f">=3R campaigns sit in {len(out['weeks3'])} week(s)")
    return out


# ════════════════════════════════════════════════════════════════════════════════════
P("B6 fork-B backtest — run", PULL_DAY, "| rule-set", RS.name, "| settle horizon", ep.LAST_SETTLED)
P("\n══ POPULATION (printed first) ══")
cnt = Counter()
for k, r in pop.items():
    v = "DOWNGRADE" if k in dg_first else ("OTHER_DOWNGRADE" if k in other_dg else "PASS")
    cnt[(era(k[1]), v, "alerted" if r["has_alert"] == "t" else "no_alert")] += 1
for k in sorted(cnt):
    P(f"  {k[0]:4} {k[1]:16} {k[2]:9} {cnt[k]}")
P("  from_quality (post composite downgrades):",
  dict(Counter(v["from_quality"] for k, v in dg_first.items() if era(k[1]) == "post")))
P("  ticker-days with NO scan tick at all:",
  dict(Counter((era(k[1]), "DOWN" if k in dg_first else "PASS") for k in pop if k not in ticks)))
P("  ticker-days with no 09:30 minute bar:",
  dict(Counter((era(k[1]), "DOWN" if k in dg_first else "PASS") for k in pop
               if not any(b["m"].time() == time(9, 30) for b in minutes.get((k[0], date.fromisoformat(k[1])), [])))))

D_post = sorted(k for k in dg_first if era(k[1]) == "post" and k in pop or (k in dg_first and era(k[1]) == "post"))
D_pre = sorted(k for k in dg_first if era(k[1]) == "pre")
PASS_post = sorted(k for k in pop if era(k[1]) == "post" and k not in dg_first and k not in other_dg)
PASS_pre = sorted(k for k in pop if era(k[1]) == "pre" and k not in dg_first and k not in other_dg)
P(f"  arms: post DOWNGRADE {len(D_post)}  post PASS {len(PASS_post)}  pre DOWNGRADE {len(D_pre)}  pre PASS {len(PASS_pre)}")

# ══ FIDELITY CHECKS ═════════════════════════════════════════════════════════════════
P("\n══ FIDELITY CHECKS (before any return) ══")
checks = {}
# 1. re-scorer
tot = ok = 0
miss = Counter()
mult_vs_regime = Counter()
for r in s2["SCANLOG"]:
    if r["score_breakdown"] and r["ep_score"]:
        tot += 1
        bd, raw, m, good = worked_back(r)
        ok += good
        if not good:
            miss[(r["catalyst_quality"], r["scan_date"][:7])] += 1
        else:
            mult_vs_regime[(m == regime_mult(r["scan_date"], True), m == regime_mult(r["scan_date"], False))] += 1
checks[1] = tot > 0 and ok / tot >= 0.98
P(f"  1 re-scorer: stored breakdown x multiplier reproduces the stored score on {ok} of {tot} "
  f"scored ticks ({ok / tot * 100:.1f}%; bar 98%) -> {'PASS' if checks[1] else 'FAIL'}; misses {dict(miss)}")
P(f"    multiplier vs regime table (prior-day match, same-day match): {dict(mult_vs_regime)}")

# 2. alert reconstruction on PASS (post)
tp = fp = fn = tn = 0
c2miss = []
for k in PASS_post:
    rec = reconstruct(k, None, None)
    pred = rec["first_high"] is not None
    real = any((a["baseline_floor_tier"] or a["score_tier"]) == "HIGH" for a in alerts.get(k, []))
    if pred and real:
        tp += 1
    elif pred and not real:
        fp += 1
        c2miss.append((k, "predicted_no_alert"))
    elif real and not pred:
        fn += 1
        c2miss.append((k, f"alert_not_predicted ticks={rec['n_ticks']} why={dict(rec['why'])}"))
    else:
        tn += 1
agree = (tp + tn) / max(1, tp + tn + fp + fn)
recall = tp / max(1, tp + fn)
checks[2] = recall >= 0.90 and agree >= 0.90
P(f"  2 alert reconstruction (post PASS, n={len(PASS_post)}): real floor-HIGH alerts rebuilt {tp} of {tp + fn} "
  f"({recall * 100:.0f}%; bar 90%); predicted-but-no-alert {fp}; overall agreement {agree * 100:.0f}% "
  f"-> {'PASS' if checks[2] else 'FAIL'}")
for k, why in c2miss:
    P(f"      miss {k[0]} {k[1]}: {why}")

# 3. harness validate is run separately (ep_replay.py validate) — recorded by the caller.
# 4. entered / not entered vs real trade rows (real post HIGH alerts)
ALLHIGH = sorted({k for k, v in alerts.items() if era(k[1]) == "post" and k[1] <= ep.LAST_SETTLED.isoformat()
                  and any(a["score_tier"] == "HIGH" for a in v)})


def alert_submit(k):
    dets = [a["detected_at_et"] for a in alerts[k] if a["detected_at_et"]]
    if not dets:
        return time(9, 31)
    t = datetime.strptime(min(dets), "%Y-%m-%d %H:%M:%S")
    return max(time(9, 31), time(t.hour, t.minute)) if t.date().isoformat() == k[1] else time(9, 31)


allhigh_camps = {k: walk(k, alert_submit(k)) for k in ALLHIGH}                      # today's rules (the arm)
allhigh_era = {k: walk(k, alert_submit(k), era_correct=True) for k in ALLHIGH}      # era-correct (check 4)
n4 = ok4 = ok4nb = 0
n4p = ok4p = 0     # names INSIDE the earnings population — the only ones with scan ticks + flip events pulled
m4 = []
excl4 = Counter()
for k in ALLHIGH:
    tr = [t for t in trades.get(k, []) if t["signal_type"] == "magna53" and t["entry_attempt"] in ("1", "")]
    if not tr:
        excl4["no_trade_row"] += 1
        continue
    # a CANCELLED row carries the planned entry price — only a fill time / filled status is an entry
    real_ent = any(t["status"] in ("closed", "filled") or t["filled_at_et"] for t in tr)
    reasons = {(t["skip_reason"] or t["status"]).split(":")[0] + ":" + ((t["skip_reason"].split(":") + [""])[1].strip().split(" ")[0] if ":" in t["skip_reason"] else "") for t in tr}
    if not real_ent and any(t["skip_reason"].startswith(("block:", "infra:", "setup:size_too_small"))
                            for t in tr):
        excl4["not_replayable_skip(" + ",".join(sorted(reasons)) + ")"] += 1
        continue
    c = allhigh_era[k]
    if c["status"] == "abstain":
        excl4["replay_abstain"] += 1
        continue
    rep_ent = c["status"] in ("settled", "open_at_horizon")
    n4 += 1
    ok4 += (rep_ent == real_ent)
    if k in ticks:
        n4p += 1
        ok4p += (rep_ent == real_ent)
    ok4nb += ((allhigh_camps[k]["status"] in ("settled", "open_at_horizon")) == real_ent)
    if rep_ent != real_ent:
        m4.append(f"{k[0]} {k[1]}: real {'entered' if real_ent else 'not:' + ','.join(sorted(reasons))} "
                  f"vs replay {c['status']}/{c.get('reason')}")
checks[4] = n4 > 0 and ok4 / n4 >= 0.95
P(f"  4 entered/not-entered vs real trade rows (real post HIGH alerts): {ok4} of {n4} agree "
  f"({ok4 / max(1, n4) * 100:.0f}%; bar 95%) -> {'PASS' if checks[4] else 'FAIL'}; "
  f"with today's rules on every date instead {ok4nb} of {n4}; excluded {dict(excl4)}")
P(f"    era-correct gates (4a from {OPEN_FLOOR_LIVE_FROM}, 4b from {RT_GAP_RECHECK_FROM}); pull_6 wired "
  f"({N_P6[0]} ticks, {N_P6[1]} events); names with flip events/ticks available: "
  f"{sum(1 for k in ALLHIGH if k in ticks)} of {len(ALLHIGH)}")
P(f"    replay entry types among real-HIGH alerts: {dict(Counter(c['entry_type'] for c in allhigh_era.values()))}")
for m in m4:
    P("      miss " + m)

# ══ COUNTERFACTUAL ══════════════════════════════════════════════════════════════════
P("\n══ COUNTERFACTUAL FUNNEL — post-rescale composite downgrades ══")
recs = {}
for k in D_post:
    ev = dg_first[k]
    recs[k] = reconstruct(k, ev["from_quality"], ev["created_et"])
cfh = [k for k in D_post if recs[k]["first_high"] is not None]
already = [k for k in cfh if recs[k]["method"] == "factual"]
added_high = [k for k in cfh if recs[k]["method"] != "factual"]
P(f"  downgraded names {len(D_post)} -> counterfactual HIGH {len(cfh)} "
  f"(of which {len(already)} were HIGH anyway — the downgrade did not act; ADDED {len(added_high)})")
P(f"  methods: {dict(Counter(recs[k]['method'] for k in cfh))}; band-straddle abstains: "
  f"{sum(1 for k in D_post if recs[k]['first_high'] is None and recs[k]['band_abstain'])}")
why = Counter()
for k in D_post:
    if recs[k]["first_high"] is None:
        w = recs[k]["why"]
        if not recs[k]["n_ticks"]:
            why["no_scan_ticks"] += 1
        elif w.get("cf_below_bar"):
            why["restored grade still under the bar"] += 1
        else:
            top = w.most_common(1)[0][0] if w else "none"
            why["grade already restored by the corrector, still under the bar" if top == "score_bar"
                else "killed by a grade-blind gate: " + top] += 1
P(f"  why the other {len(D_post) - len(cfh)} never reach HIGH: {dict(why)}")
mx = sorted((recs[k]["cf_max"] for k in D_post if recs[k]["first_high"] is None and recs[k]["cf_max"] is not None))
if mx:
    P(f"  best counterfactual score of the names that stay under 65: n={len(mx)} median {statistics.median(mx):.1f} "
      f"max {mx[-1]:.1f}; within 5 points of the bar: {sum(1 for x in mx if x >= 60)}")

# cooldown: a later row of the same ticker within 60 days of an earlier counterfactual alert
seen_last = {}
cool = set()
for k in sorted(added_high, key=lambda k: k[1]):
    d = date.fromisoformat(k[1])
    if k[0] in seen_last and (d - seen_last[k[0]]).days <= 60:
        cool.add(k)
    else:
        seen_last[k[0]] = d
A_keys = [k for k in added_high if k not in cool]
P(f"  cooldown_ambiguous (left out of primary): {sorted(cool)}")


def b2_still_down(k):
    q = _f(dg_first[k]["q_revenue_yoy_pct"])
    if q is None:
        q = _f(pop.get(k, {}).get("q_revenue_yoy_pct"))
    return q is None or q < 5.0


A = {k: walk(k, submit_of(recs[k]["first_high"])) for k in A_keys}
A_nb = {k: walk(k, submit_of(recs[k]["first_high"]), era_correct=True) for k in A_keys}
A_b2 = {k: v for k, v in A.items() if not b2_still_down(k)}
P(f"  submit times of the ADDED set: {dict(Counter(c['submit'] for c in A.values()))}")

Pf_keys = [k for k in PASS_post if reconstruct(k, None, None)["first_high"] is not None]
Pf = {k: walk(k, submit_of(reconstruct(k, None, None)["first_high"])) for k in Pf_keys}
Pa_keys = [k for k in PASS_post if any(a["score_tier"] == "HIGH" for a in alerts.get(k, []))]
Pa = {k: walk(k, alert_submit(k)) for k in Pa_keys}
UB = {k: walk(k, time(9, 31), gates=False) for k in D_post}
UB_pre = {k: walk(k, time(9, 31), gates=False) for k in D_pre}

P("\n══ RESULTS (post-rescale; R per campaign, one risk unit; rule-set = today's) ══")
sA = summarize("A — ADDED by fork B, mechanism B1 (primary)", list(A.values()), len(D_post))
sAnb = summarize("A with era-correct gates (sensitivity only)", list(A_nb.values()), verbose=False)
sB2 = summarize("A-B2 — rubric gate off, 5% revenue net takes over", list(A_b2.values()), verbose=False)
sP = summarize("P-floor — PASS names rebuilt the same way", list(Pf.values()), len(PASS_post))
sPa = summarize("P-actual — PASS names that really alerted HIGH after the judge", list(Pa.values()), verbose=False)
sH = summarize("ALL-HIGH — every real post-rescale HIGH alert", list(allhigh_camps.values()))
sU = summarize("UPPER BOUND — every post downgraded name walked as if admitted at 09:31, submission gates off", list(UB.values()))
sUp = summarize("PRE-RESCALE upper bound (separate column, never pooled)", list(UB_pre.values()), verbose=False)

P("\n── the ADDED names, each (operator reviews the list; not classified here) ──")
for k in sorted(A, key=lambda k: k[1]):
    c = A[k]
    ev = dg_first[k]
    r = r_of(c) if c["status"] in ("settled", "open_at_horizon") else None
    P(f"  {k[0]:6} {k[1]} composite {ev['composite_scaled']:>5} {ev['from_quality']:12} gap {ev['gap_pct']:>6} "
      f"first HIGH {recs[k]['first_high'].strftime('%H:%M')} ({recs[k]['method']}) -> {c['status']}"
      f"{'/' + str(c.get('reason')) if c['status'] not in ('settled', 'open_at_horizon') else ''}"
      f"{f' {r:+.2f}R ' + str(c.get('final_reason')) if r is not None else ''}"
      f"{' [B2: still downgraded]' if b2_still_down(k) else ''}")

# ── slot cap / breakers: separate column ──
P("\n── slot cap / breakers (separate column — never drops a row above) ──")
entered_A = [k for k, c in A.items() if c["status"] in ("settled", "open_at_horizon")]
for k in sorted(entered_A, key=lambda k: k[1]):
    d = k[1]
    openpos = Counter()
    for t in s3["TRADES"]:
        if t["filled_at_et"] and t["filled_at_et"] < d + " 09:31" and (not t["closed_at_et"] or t["closed_at_et"] > d + " 09:31"):
            openpos[t["account_mode"]] += 1
    blocks = sorted({t["skip_reason"].split(" ")[0] for t in s3["TRADES"]
                     if t["alert_date"] == d and t["skip_reason"].startswith("block:")
                     and "reentry" not in t["skip_reason"]})   # a per-ticker re-entry refusal is not an account block
    my_rs = _f(rsadv.get(k, {}).get("rs_composite"))
    ahead = sum(1 for kk in ALLHIGH if kk[1] == d and (_f(rsadv.get(kk, {}).get("rs_composite")) or -1) > (my_rs if my_rs is not None else -1))
    same_day_high = sum(1 for kk in ALLHIGH if kk[1] == d)
    likely = max(openpos.values(), default=0) >= 5 or bool(blocks) or ahead >= 5
    P(f"  {k[0]:6} {d}: open positions {dict(openpos)}; block reasons that day {blocks}; "
      f"real HIGH alerts that day {same_day_high}, ranked ahead on RS {ahead} -> "
      f"{'LIKELY BLOCKED' if likely else 'room'}")

# ── judge bound ──
fl = [a for v in alerts.values() for a in v if a["alert_date"] >= POST and a["baseline_floor_tier"] == "HIGH"]
kept = sum(1 for a in fl if a["score_tier"] == "HIGH")
P(f"\n── judge bound: of {len(fl)} real post-rescale floor-HIGH alerts the judge kept {kept} HIGH "
  f"({kept / max(1, len(fl)) * 100:.0f}%); A entered x that rate = {sA['n_entered'] * kept / max(1, len(fl)):.1f} expected post-judge entries")
flp = [a for k in PASS_post for a in alerts.get(k, []) if a["baseline_floor_tier"] == "HIGH"]
P(f"   earnings PASS names only: judge kept {sum(1 for a in flp if a['score_tier'] == 'HIGH')} of {len(flp)}")

# ── decision rule ──
P("\n══ DECISION RULE (frozen 2026-11-19, before the data) ══")
C, Cname = (sP, "P-floor") if sP["n_entered"] >= 15 else (sH, "ALL-HIGH (fallback — P-floor under 15 entered)")
P(f"  comparator C = {Cname}: entered {C['n_entered']}; A entered {sA['n_entered']}; "
  f"counterfactual HIGH added {len(added_high)}")
P(f"  checks: 1 {'PASS' if checks[1] else 'FAIL'}, 2 {'PASS' if checks[2] else 'FAIL'}, 4 {'PASS' if checks[4] else 'FAIL'}; "
  f"abstain A {sA['abstain_rate'] * 100:.0f}% C {C['abstain_rate'] * 100:.0f}% (ceiling 30%)")
if len(added_high) <= 5:
    branch = "INERT — five or fewer counterfactual HIGHs: other rules drop these names anyway"
elif not all(checks.values()) or sA["n_entered"] < 15 or C["n_entered"] < 15 or sA["abstain_rate"] > 0.30 or C["abstain_rate"] > 0.30:
    branch = "NOT READABLE at this n — gate stays 22, nothing closes"
else:
    bring = (sA["ge3_open"] >= 2 and sA["share3"] >= C["share3"] and sA["sum"] > 0 and sA["mean"] >= C["mean"]
             and len(sA["weeks3"]) >= 2 and (sA["sum_ex_best_week"] or 0) > 0)
    close = sA["sum"] <= 0 and sA["share3"] <= C["share3"]
    branch = "BRING fork B to the operator" if bring else ("CLOSE fork B — gate stays 22" if close else "IN BETWEEN — keep 22, one re-read at 30 entered")
P(f"  BRANCH FIRED: {branch}")
first, last = min(k[1] for k in D_post), max(k[1] for k in D_post)
wks = max(1, (date.fromisoformat(last) - date.fromisoformat(first)).days / 7)
P(f"  rate: {sA['n_entered']} added entries in {wks:.1f} weeks ({first}..{last}) = {sA['n_entered'] / wks * 13:.1f} per quarter; "
  f"counterfactual HIGHs {len(added_high) / wks * 13:.1f} per quarter")

cols = ["arm", "ticker", "alert_date", "submit", "entry_type", "status", "reason", "entry_px", "stop", "realized_r", "mark_r", "final_reason"]
with open(HERE / "campaigns.tsv", "w") as fh:
    fh.write("|".join(cols) + "\n")
    for arm, dd in (("A", A), ("P_floor", Pf), ("P_actual", Pa), ("ALL_HIGH", allhigh_camps), ("UPPER", UB), ("UPPER_PRE", UB_pre)):
        for k, c in sorted(dd.items()):
            fh.write("|".join(str({**c, "arm": arm}.get(x, "")) for x in cols) + "\n")

# ══ SENSITIVITIES added after the second run (2026-11-19) — the frozen rule is NOT re-read on them ══
P("\n══ SENSITIVITIES (not part of the frozen rule) ══")
FLOORHIGH = sorted({k for k, v in alerts.items() if era(k[1]) == "post" and k[1] <= ep.LAST_SETTLED.isoformat()
                    and any(a["baseline_floor_tier"] == "HIGH" or a["score_tier"] == "HIGH" for a in v)})
fh_camps = {k: walk(k, alert_submit(k)) for k in FLOORHIGH}
sF = summarize("PRE-JUDGE comparator — every real post-rescale alert with floor tier HIGH (judge demotions kept in)",
               list(fh_camps.values()))
P(f"  missing minute bars among floor-HIGH names: {sum(1 for k in FLOORHIGH if (k[0], date.fromisoformat(k[1])) not in minutes)} of {len(FLOORHIGH)}")
if sF["n_entered"] >= 15:
    bring = (sA["ge3_open"] >= 2 and sA["share3"] >= sF["share3"] and sA["sum"] > 0 and sA["mean"] >= sF["mean"]
             and len(sA["weeks3"]) >= 2 and (sA["sum_ex_best_week"] or 0) > 0)
    close = sA["sum"] <= 0 and sA["share3"] <= sF["share3"]
    P(f"  frozen tests against the PRE-JUDGE comparator: A share {sA['share3']:.3f} vs {sF['share3']:.3f}; "
      f"-> {'BRING' if bring else ('CLOSE' if close else 'IN BETWEEN — keep 22')}")
else:
    P("  pre-judge comparator under 15 entered")

P("\n── where the upper bound's R sits (post downgraded names entered with gates off, split by why fork B does NOT add them) ──")
grp = defaultdict(list)
for k, c in UB.items():
    if c["status"] not in ("settled", "open_at_horizon") or degenerate(c) or r_of(c) is None:
        continue
    if k in A:
        a = A[k]
        why_ = "ADDED and entered" if a["status"] in ("settled", "open_at_horizon") else "would alert, refused at submission: " + str(a.get("reason"))
    elif recs[k]["first_high"] is not None:
        why_ = "alerted anyway"
    else:
        w = recs[k]["why"]
        why_ = "restored grade still under the bar" if w.get("cf_below_bar") else "grade-blind gate / other"
    grp[why_].append(r_of(c))
for g, v in sorted(grp.items(), key=lambda x: -len(x[1])):
    P(f"  {g:62} n{len(v):3}  >=3R {sum(1 for x in v if x >= 3):2}  total {sum(v):+6.1f}R  mean {statistics.mean(v):+.2f}R")
