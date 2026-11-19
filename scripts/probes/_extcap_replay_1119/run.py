"""Extension-cap band replay (review extension_cap_75_recheck, 2026-11-19). READ-ONLY, $0, offline.
Reads pull.out.gz here; reuses scripts/ep_replay.py (walk_campaign, ruleset_as_of 2026-11-19) and
the walk() pattern of ../_b6_backtest_1119/run_backtest.py. Edits nothing live.
    .venv/bin/python scripts/probes/_extcap_replay_1119/run.py > scripts/probes/_extcap_replay_1119/results.txt
The pull has NO stored ep_score on any extended-rejected tick (rejected before scoring), so every
campaign submits at 09:31 = an UPPER BOUND on admission (names that would never have scored HIGH are in).
"""
from __future__ import annotations
import gzip, statistics, sys, tempfile
from collections import Counter, defaultdict
from datetime import date, datetime, time
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[2]
sys.path.insert(0, str(REPO))
import scripts.ep_replay as ep  # noqa: E402
from agents.market_intelligence.backtester.filters import validate_orb_entry  # noqa: E402
from agents.market_intelligence.broker.order_manager import profit_target_r_per_share  # noqa: E402

_f = ep._f
RS = ep.ruleset_as_of(date(2026, 11, 19))
MIN_GAP, CHASE_CAP = 9.0, 1.5
P = print

tmp = Path(tempfile.mkdtemp()) / "pull.txt"
tmp.write_text(gzip.open(HERE / "pull.out.gz", "rt").read())
S = ep.read_sections(tmp)

minutes: dict = {}
for r in S["MIN"]:
    try:
        dt = datetime.strptime(r["et_min"], "%Y-%m-%d %H:%M").replace(tzinfo=ep._ET)
    except ValueError:
        continue
    minutes.setdefault((r["ticker"], dt.date()), []).append(
        {"m": dt, "o": float(r["open"]), "h": float(r["high"]), "l": float(r["low"]), "c": float(r["close"])})
for b in minutes.values():
    b.sort(key=lambda x: x["m"])
daily: dict = {}
for r in S["DAILY"]:
    d = date.fromisoformat(r["trade_date"])
    daily.setdefault(r["ticker"], {})[d] = {"o": _f(r["open_price"]), "h": _f(r["high_price"]),
                                            "l": _f(r["low_price"]), "c": _f(r["close"]), "v": _f(r["volume"])}
ep.LAST_SETTLED = max(d for v in daily.values() for d in v)

# population: one row per ticker-day, max pct seen
pct = {}
for r in S["POP"]:
    k = (r["ticker"], r["scan_date"])
    pct[k] = max(pct.get(k, 0), float(r["pct"]))
band = sorted(k for k, v in pct.items() if 50 <= v < 75)
high = sorted(k for k, v in pct.items() if v >= 75)
scored = sum(1 for r in S["SCAN"] if r["ep_score"])


def prev_close_of(t, d):
    p = [x for x in sorted(daily.get(t, {})) if x < d]
    return daily[t][p[-1]]["c"] if p else None


def price_at_submit(bars, submit):
    nxt = next((b for b in bars if b["m"].time() >= submit), None)
    if nxt and (datetime.combine(date.min, nxt["m"].time()) - datetime.combine(date.min, submit)).seconds <= 120:
        return nxt["o"]
    prv = [b for b in bars if b["m"].time() < submit]
    return prv[-1]["c"] if prv else None


def walk(key, submit=time(9, 31), gates=True):
    tkr, ds = key
    d = date.fromisoformat(ds)
    res = {"ticker": tkr, "alert_date": ds, "status": None, "reason": None, "entered": False,
           "entry_px": None, "stop": None, "realized_r": None, "mark_r": None, "final_reason": None,
           "entry_type": None}
    bars0 = minutes.get((tkr, d), [])
    orb = next((b for b in bars0 if b["m"].time() == time(9, 30)), None)
    if not orb:
        res.update(status="no_trade", reason="no_0930_bar")
        return res
    pc = prev_close_of(tkr, d)
    px = price_at_submit(bars0, submit)
    if gates and pc and px and px > 0 and (px - pc) / pc * 100 < MIN_GAP:
        res.update(status="no_trade", reason="gap_below_floor_at_submit")
        return res
    atr = ep.atr14_abs(daily.get(tkr, {}), d)
    if px is not None and px > orb["h"]:
        ok, skip = validate_orb_entry(orb["h"], orb["l"], atr)
        if not ok:
            res.update(status="no_trade", reason="orb_validation:" + (skip or "").split(":")[0][:40])
            return res
        adr_pct, _ = ep.adr20_pct(daily.get(tkr, {}), d)
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
        leg = ep._walk_leg(ticker=tkr, leg_date=d, entry_px=entry_px, stop=stop, target=target, target2=None,
                           bars=bars0, fill_idx=bars0.index(fb), rs=RS, daily=daily, shares=None,
                           integer_shares=False, adr_dollar=adr_dollar, minutes_extra={}, r_frame_ps=r_ps)
        res.update(entered=True, entry_px=entry_px,
                   **{k: leg[k] for k in ("status", "reason", "realized_r", "mark_r", "final_reason")})
        return res
    w = ep.walk_campaign(ticker=tkr, alert_date=d, rs=RS, minutes=minutes, daily=daily, submit=submit, atr_14=atr)
    res.update({k: w[k] for k in ("status", "reason", "entered", "entry_px", "stop", "realized_r", "mark_r", "final_reason")})
    res["entry_type"] = "stop_limit"
    return res


def r_of(c):
    return c["realized_r"] if c["status"] == "settled" else c.get("mark_r")


def degenerate(c):
    try:
        return abs(c["entry_px"] - c["stop"]) / c["entry_px"] * 100 < 0.5
    except (TypeError, ZeroDivisionError):
        return False


def week(ds):
    y, w, _ = date.fromisoformat(ds).isocalendar()
    return f"{y}-W{w:02d}"


def report(label, keys, gates):
    camps = [walk(k, gates=gates) for k in keys]
    ent = [c for c in camps if c["status"] in ("settled", "open_at_horizon") and r_of(c) is not None and not degenerate(c)]
    deg = [c for c in camps if c["status"] in ("settled", "open_at_horizon") and degenerate(c)]
    ab = [c for c in camps if c["status"] == "abstain"]
    nt = [c for c in camps if c["status"] in ("no_trade", "no_entry")]
    P(f"\n[{label}] gates={'LIVE(gap>=9% at submit)' if gates else 'OFF (upper bound)'}  n = {len(keys)} ticker-days")
    P(f"  funnel: entered {len(ent)}, abstain {len(ab)} ({len(ab)/len(keys)*100:.0f}%) "
      f"{dict(Counter((c['reason'] or '').split(':')[0] for c in ab))}, "
      f"no_trade/no_entry {len(nt)} {dict(Counter(c['reason'] for c in nt))}, near-zero-stop excluded {len(deg)}")
    rs_ = [r_of(c) for c in ent]
    if rs_:
        ge3 = [c for c in ent if r_of(c) >= 3]
        P(f"  TAIL: >=3R {len(ge3)} (open-mark incl. {sum(1 for c in ent if c['status']=='open_at_horizon' and r_of(c)>=3)}), "
          f"best {max(rs_):+.2f}R, full losers (<=-0.9R) {sum(1 for x in rs_ if x <= -0.9)} of {len(rs_)}, "
          f"total {sum(rs_):+.2f}R, mean {statistics.mean(rs_):+.2f}R, median {statistics.median(rs_):+.2f}R")
        P(f"  weeks with a >=3R campaign: {sorted({week(c['alert_date']) for c in ge3})}  (distinct {len({week(c['alert_date']) for c in ge3})})")
        wk = defaultdict(float)
        for c in ent:
            wk[week(c["alert_date"])] += r_of(c)
        bw = max(wk, key=wk.get)
        P(f"  total without best week ({bw}): {sum(rs_) - wk[bw]:+.2f}R")
    P("  per name:")
    for c in sorted(camps, key=lambda c: c["alert_date"]):
        rr = r_of(c)
        P(f"    {c['alert_date']} {c['ticker']:6} pct={pct[(c['ticker'], c['alert_date'])]:>6.0f} {c['status']:15} "
          f"{('%+.2fR' % rr) if rr is not None and c['entered'] else '   -  '} "
          f"{c['entry_type'] or ''} {c['final_reason'] or c['reason'] or ''}")
    return camps


P("Extension-cap band replay | rule-set", RS.name, "| settle horizon", ep.LAST_SETTLED)
P(f"POPULATION: ticker-days {len(pct)} (50-75% band n = {len(band)}, >=75% n = {len(high)}); "
  f"distinct names band {len({k[0] for k in band})}, >=75 {len({k[0] for k in high})}")
P(f"scan rows {len(S['SCAN'])}; rows with a stored ep_score: {scored} -> NO score on any extended-rejected tick; "
  f"submit 09:31 (upper bound on admission, flagged)")
P(f"ticker-days with no 09:30 minute bar: band {sum(1 for k in band if not any(b['m'].time()==time(9,30) for b in minutes.get((k[0], date.fromisoformat(k[1])), [])))}, "
  f">=75 {sum(1 for k in high if not any(b['m'].time()==time(9,30) for b in minutes.get((k[0], date.fromisoformat(k[1])), [])))}")
for g in (True, False):
    report("BAND 50-75%", band, g)
    report(">=75%", high, g)
