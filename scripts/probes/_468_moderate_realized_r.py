#!/usr/bin/env python3
"""#468 — MODERATE-vs-HIGH EP realized-R study (READ-ONLY probe; STUDY ONLY).

Q4 of docs/analysis/ep_theme_coverage_loop_design_2026-07-13.md §5 found MODERATE ≈ HIGH
on RAW 5-day forward return (avg +13.2% vs +10.4%, n=63/129 settled). But MODERATE gets a
briefing, NOT an ORB entry — raw return ≠ realized-R. This probe reconstructs realized-R
for MODERATE alerts AS-IF they'd been ORB-entered under the LIVE MAGNA53 geometry, runs
the IDENTICAL reconstruction on HIGH alerts (apples-to-apples), and calibrates the
reconstruction against HIGH's ACTUAL realized-R from mi_live_trades.

THE LINE: changes NO entry/sizing/detection logic. Read-only prod SELECTs + Polygon
market-data pulls + local simulation. Whether MODERATE→ORB-entry ships is the OPERATOR's
call, informed by this evidence (then a full backtest + CHANGE_PROCESS).

Live geometry faithfully applied (sources cited per rule):
  * ORB bar     = earliest 1-min bar in 9:30–9:35 ET (alpaca_client.get_first_bar).
  * Entry       = stop-limit BUY, trigger @ ORB-high, limit = max(hi*1.005, hi+0.02)
                  (order_manager.stop_limit_buy_price).
  * Stop        = ORB-low (prepare_orb_order).
  * Validation  = zero-range skip + ORB range > 1.5×ATR14 → setup:stop_too_wide
                  (backtester.filters.validate_orb_entry). ATR14 = Wilder TR, simple
                  mean of last 14 TRs through the PRIOR close (the 9:31 live path has
                  no today bar — compute_atr_14 docstring). Unknown ATR passes (live).
  * Fade guard  = SKIPPED — MAGNA53 passes ratio=None (entry_pipeline.check_fade_guard).
  * Window      = detection ≥ 9:45 ET → WINDOW_OUT_OF_ORB, never submitted
                  (ep scan window rule; shadow_orb_tracker._fetch_magna53_high_pre_open).
                  Submission minute = max(detection minute, 9:31) (the 9:31 cron).
  * Fill window = trigger bar must be < 10:00 ET (the 10:00 unfilled-cancel job).
                  No trigger by 10:00 = clean miss (0R in the full-universe view).
  * Exit        = anticipation.SETTLE_RULE (+1R/+3R ½/½, day-5 time stop), 'pess'
                  intrabar bound, harvested over the faithful mixed minute+daily path
                  (anticipation.simulate / build_mixed_path — the #327 primitives,
                  REUSED not reinvented). NOT the live exit engine — see the doc's
                  fidelity-limits section; the HIGH-actual arm carries the live exits.

Phases (like scripts/_327_replay.py — local TSVs, re-runnable offline):
  --pull-cohort  ssh read-only psql SELECTs → _468_cohort.tsv + _468_trades.tsv
  --pull-bars    ssh docker exec apollo-market python (Polygon, read-only market data)
                 → _468_daily.tsv + _468_minute.tsv
  (no flag)      local settle + report (pure computation over the TSVs)

Findings doc: docs/analysis/468_moderate_vs_high_realized_r_2026-07-18.md
"""
from __future__ import annotations

import subprocess
import sys
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent.parent))               # repo root for `agents.` imports

from agents.market_intelligence import anticipation as de  # noqa: E402 (pure; reused atoms)

HOST = "apollo@87.99.134.162"
COHORT = HERE / "_468_cohort.tsv"    # ticker|alert_date|tier|ep_score|gap_pct|det_et|cq|authority|floor_tier|fwd_5d_pct
TRADES = HERE / "_468_trades.tsv"    # magna53 mi_live_trades dump
DAILY = HERE / "_468_daily.tsv"      # ticker|date|o|h|l|c|v
MINUTE = HERE / "_468_minute.tsv"    # ticker \t t_ms \t o h l c v

SETTLE_FWD = de.SETTLE_FORWARD_BARS  # 5 forward trading bars to settle
RTH_OPEN = de._RTH_OPEN              # 570 = 9:30 ET
SUBMIT_MIN = RTH_OPEN + 1            # 9:31 — the ORB monitor cron fire
WINDOW_END = RTH_OPEN + 15           # 585 = 9:45 ET — WINDOW_OUT_OF_ORB at/after
FILL_END = RTH_OPEN + 30             # 600 = 10:00 ET — unfilled-cancel job
ORB_FETCH_END = RTH_OPEN + 5         # get_first_bar looks in 9:30–9:35
CLEAN_LO, CLEAN_HI = "2026-05-11", "2026-06-24"   # §5: outside = clean, inside = polluted


# ── live-geometry pure helpers (values mirrored from the cited live functions) ──

def stop_limit_buy_price(stop_price: float) -> float:
    """MIRROR of order_manager.stop_limit_buy_price (two-floor buffer)."""
    return round(max(stop_price * 1.005, stop_price + 0.02), 2)


def validate_orb_entry(orb_high: float, orb_low: float, atr_14: float | None):
    """MIRROR of backtester.filters.validate_orb_entry (single authoritative rule)."""
    orb_range = orb_high - orb_low
    if orb_range <= 0:
        return False, "setup:zero_range"
    if atr_14 and atr_14 > 0 and orb_range > 1.5 * atr_14:
        return False, "setup:stop_too_wide"
    return True, None


def atr14_prior_close(bars: list[dict], alert_idx: int) -> float | None:
    """Wilder TR, simple mean of the last 14 TRs ending at the PRIOR trading day
    (live 9:31 parity: today's bar is not in mi_daily_closes yet — compute_atr_14
    docstring). Needs 15 bars before the alert day; else None (gate passes, as live)."""
    if alert_idx < 15:
        return None
    trs = []
    for i in range(alert_idx - 14, alert_idx):
        b, prev_c = bars[i], bars[i - 1]["c"]
        trs.append(max(b["h"] - b["l"], abs(b["h"] - prev_c), abs(b["l"] - prev_c)))
    return sum(trs) / len(trs)


# ── loaders ──────────────────────────────────────────────────────────────────

def _f(x):
    try:
        return float(x) if x not in ("", None) else None
    except ValueError:
        return None


def load_cohort() -> list[dict]:
    rows = []
    for ln in COHORT.read_text(encoding="utf-8").splitlines():
        p = ln.rstrip("\r").split("|")
        if len(p) < 10 or not p[0]:
            continue
        rows.append({"ticker": p[0], "alert_date": p[1], "tier": p[2],
                     "ep_score": _f(p[3]), "gap_pct": _f(p[4]), "det_et": p[5],
                     "cq": p[6], "authority": p[7], "floor_tier": p[8],
                     "fwd_5d": _f(p[9])})
    return rows


def load_trades() -> list[dict]:
    if not TRADES.exists():
        return []
    rows = []
    for ln in TRADES.read_text(encoding="utf-8").splitlines():
        p = ln.rstrip("\r").split("|")
        if len(p) < 14 or not p[0]:
            continue
        rows.append({"ticker": p[0], "alert_date": p[1], "status": p[2],
                     "skip_reason": p[3], "orb_high": _f(p[4]), "orb_low": _f(p[5]),
                     "atr_14": _f(p[6]), "entry_price": _f(p[7]), "stop_price": _f(p[8]),
                     "risk_dollars": _f(p[9]), "total_pnl": _f(p[10]),
                     "remaining_shares": _f(p[11]), "filled_at": p[12],
                     "closed_at": p[13],
                     "account_mode": p[14] if len(p) > 14 else ""})
    return rows


def load_daily() -> dict[str, list[dict]]:
    by = defaultdict(list)
    if not DAILY.exists():
        return by
    for ln in DAILY.read_text(encoding="utf-8").splitlines():
        p = ln.rstrip("\r").split("\t")
        if len(p) < 7 or not p[0] or p[0].startswith("#"):
            continue
        by[p[0]].append({"date": p[1], "o": _f(p[2]), "h": _f(p[3]),
                         "l": _f(p[4]), "c": _f(p[5]), "v": _f(p[6]) or 0.0})
    for tk in by:
        by[tk].sort(key=lambda b: b["date"])
    return by


def load_minute() -> dict[tuple, list[dict]]:
    """{(ticker, et_date_iso): [raw {t,o,h,l,c,v}]} — same shape _327_replay feeds
    anticipation.polygon_to_rth_minutes (UTC→ET−4 inside the helper)."""
    raw_by = defaultdict(list)
    if not MINUTE.exists():
        return raw_by
    for ln in MINUTE.read_text(encoding="utf-8").splitlines():
        p = ln.rstrip("\r").split("\t")
        if len(p) < 7 or p[0].startswith("#"):
            continue
        tk, tms = p[0], int(p[1])
        et = datetime.fromtimestamp(tms / 1000, timezone.utc) - timedelta(hours=4)
        raw_by[(tk, et.date().isoformat())].append(
            {"t": tms, "o": _f(p[2]), "h": _f(p[3]), "l": _f(p[4]),
             "c": _f(p[5]), "v": _f(p[6])})
    return raw_by


# ── Phase A: cohort pull (read-only psql SELECTs over ssh, _454 runner shape) ──

COHORT_SQL = """
SELECT DISTINCT ON (a.ticker, a.alert_date, a.score_tier)
       a.ticker, a.alert_date, a.score_tier,
       COALESCE(a.ep_score, 0), COALESCE(a.gap_pct, 0),
       to_char(COALESCE(a.detected_at, a.created_at) AT TIME ZONE 'America/New_York',
               'YYYY-MM-DD HH24:MI:SS'),
       COALESCE(a.catalyst_quality, ''),
       COALESCE(a.grade_engine_authority, ''),
       COALESCE(a.baseline_floor_tier, ''),
       COALESCE(o.fwd_5d_pct::text, '')
FROM mi_ep_alerts a
LEFT JOIN mi_ep_scan_outcomes o
       ON o.ticker = a.ticker AND o.scan_date = a.alert_date
WHERE a.score_tier IN ('MODERATE', 'HIGH') AND a.source = 'live'
ORDER BY a.ticker, a.alert_date, a.score_tier, COALESCE(a.detected_at, a.created_at)
"""

TRADES_SQL = """
SELECT t.ticker, t.alert_date, t.status, COALESCE(t.skip_reason, ''),
       COALESCE(t.orb_high::text, ''), COALESCE(t.orb_low::text, ''),
       COALESCE(t.atr_14::text, ''), COALESCE(t.entry_price::text, ''),
       COALESCE(t.stop_price::text, ''), COALESCE(t.risk_dollars::text, ''),
       COALESCE(t.total_pnl::text, ''), COALESCE(t.remaining_shares::text, ''),
       COALESCE(to_char(t.filled_at AT TIME ZONE 'America/New_York',
                        'YYYY-MM-DD HH24:MI:SS'), ''),
       COALESCE(to_char(t.closed_at AT TIME ZONE 'America/New_York',
                        'YYYY-MM-DD HH24:MI:SS'), ''),
       COALESCE(t.account_mode, '')
FROM mi_live_trades t
WHERE t.signal_type = 'magna53'
ORDER BY t.alert_date, t.ticker
"""


def run_select(sql: str) -> str:
    """SELECT-only runner over ssh → docker exec psql -tAX (the _454 read path)."""
    s = " ".join(sql.split())
    assert s.upper().startswith("SELECT"), "read-only: SELECTs only"
    assert not any(ch in s for ch in '"\\$`'), "unsupported char for ssh quoting"
    remote = f'docker exec -i apollo-postgres psql -U apollo -d apollo -tAX -c "{s}"'
    out = subprocess.run(["ssh", "-o", "ConnectTimeout=15", HOST, remote],
                         capture_output=True, text=True, timeout=180)
    if out.returncode != 0:
        raise RuntimeError(f"psql failed: {out.stderr.strip()[:500]}")
    return out.stdout


def pull_cohort() -> None:
    COHORT.write_text(run_select(COHORT_SQL), encoding="utf-8")
    TRADES.write_text(run_select(TRADES_SQL), encoding="utf-8")
    nc = sum(1 for _ in COHORT.read_text(encoding="utf-8").splitlines())
    nt = sum(1 for _ in TRADES.read_text(encoding="utf-8").splitlines())
    print(f"pulled cohort rows={nc} -> {COHORT.name} ; magna53 trade rows={nt} -> {TRADES.name}")


# ── Phase B: Polygon bars via the in-container read path (_327_pull_minute shape) ──

def _ssh_polygon(pycode: str, out_path: Path, timeout: int = 900) -> None:
    remote = "docker exec apollo-market python -c '" + pycode + "'"
    res = subprocess.run(["ssh", HOST, remote], capture_output=True, text=True,
                         timeout=timeout)
    out_path.write_text(res.stdout, encoding="utf-8")
    errs = [ln for ln in res.stderr.splitlines() if ln.startswith("# ERR")]
    n = sum(1 for _ in res.stdout.splitlines())
    print(f"exit={res.returncode} rows={n} errs={len(errs)} -> {out_path.name}")
    for e in errs[:10]:
        print("  " + e)


def pull_bars() -> None:
    rows = load_cohort()
    if not rows:
        sys.exit(f"run --pull-cohort first ({COHORT.name} missing/empty)")
    pairs = sorted({(r["ticker"], r["alert_date"]) for r in rows})
    # daily: one range call per ticker spanning all its alerts (+ATR lookback +forward)
    span: dict[str, list[str]] = {}
    for tk, d in pairs:
        span.setdefault(tk, [d, d])
        span[tk][0], span[tk][1] = min(span[tk][0], d), max(span[tk][1], d)
    dranges = sorted(
        (tk,
         (datetime.fromisoformat(lo) - timedelta(days=70)).date().isoformat(),
         (datetime.fromisoformat(hi) + timedelta(days=15)).date().isoformat())
        for tk, (lo, hi) in span.items())
    print(f"pulling daily for {len(dranges)} tickers …")
    dr_lit = "[" + ",".join(f'("{t}","{a}","{b}")' for t, a, b in dranges) + "]"
    # remote code uses ONLY double-quoted strings (nests inside the single-quoted -c '…')
    daily_code = (
        "import json,os,sys,time,urllib.request,datetime\n"
        "KEY=os.environ[\"POLYGON_API_KEY\"]\n"
        f"RANGES={dr_lit}\n"
        "for t,a,b in RANGES:\n"
        "    url=f\"https://api.polygon.io/v2/aggs/ticker/{t}/range/1/day/{a}/{b}?adjusted=true&sort=asc&limit=50000&apiKey={KEY}\"\n"
        "    try:\n"
        "        rr=json.load(urllib.request.urlopen(url,timeout=25))\n"
        "        for bar in rr.get(\"results\",[]):\n"
        "            d=(datetime.datetime.utcfromtimestamp(bar[\"t\"]/1000)-datetime.timedelta(hours=4)).date().isoformat()\n"
        "            o=bar[\"o\"];h=bar[\"h\"];lo=bar[\"l\"];c=bar[\"c\"];v=bar[\"v\"]\n"
        "            print(f\"{t}\\t{d}\\t{o}\\t{h}\\t{lo}\\t{c}\\t{v}\")\n"
        "    except Exception as e:\n"
        "        print(f\"# ERR {t}: {e}\",file=sys.stderr)\n"
        "    time.sleep(0.12)\n"
    )
    _ssh_polygon(daily_code, DAILY)

    print(f"pulling minute day-0 for {len(pairs)} (ticker,date) pairs …")
    pairs_lit = "[" + ",".join(f'("{t}","{d}")' for t, d in pairs) + "]"
    minute_code = (
        "import json,os,sys,time,urllib.request\n"
        "KEY=os.environ[\"POLYGON_API_KEY\"]\n"
        f"PAIRS={pairs_lit}\n"
        "for t,d in PAIRS:\n"
        "    url=f\"https://api.polygon.io/v2/aggs/ticker/{t}/range/1/minute/{d}/{d}?adjusted=true&sort=asc&limit=50000&apiKey={KEY}\"\n"
        "    try:\n"
        "        rr=json.load(urllib.request.urlopen(url,timeout=25))\n"
        "        for bar in rr.get(\"results\",[]):\n"
        "            tt=bar[\"t\"];o=bar[\"o\"];h=bar[\"h\"];lo=bar[\"l\"];c=bar[\"c\"];v=bar[\"v\"]\n"
        "            print(f\"{t}\\t{tt}\\t{o}\\t{h}\\t{lo}\\t{c}\\t{v}\")\n"
        "    except Exception as e:\n"
        "        print(f\"# ERR {t} {d}: {e}\",file=sys.stderr)\n"
        "    time.sleep(0.12)\n"
    )
    _ssh_polygon(minute_code, MINUTE)


# ── Phase C: reconstruction + settle ─────────────────────────────────────────

def idx_of_date(bars, d):
    for i, b in enumerate(bars):
        if b["date"] == d:
            return i
    return None


def eligibility(r) -> tuple[str, int | None]:
    """('ok', submission_minute) or (reason, None). Detection timestamp → the live
    submission rule: <9:31 → 9:31 cron; 9:31–9:44 → at detection; ≥9:45 → out-of-ORB.
    Poisoned timestamps (migration artifact: created_at date ≠ alert_date) → excluded
    from the primary universe (counted; sensitivity view assumes 9:31)."""
    try:
        dt = datetime.fromisoformat(r["det_et"])
    except ValueError:
        return "ts_missing", None
    if dt.date().isoformat() != r["alert_date"]:
        return "ts_poisoned", None
    m = dt.hour * 60 + dt.minute
    if m >= WINDOW_END:
        return "window_out_of_orb", None
    return "ok", max(m, SUBMIT_MIN)


def reconstruct(minute_rth: list[dict], submission_m: int, atr_14: float | None,
                daily_forward: list[dict]) -> dict:
    """As-if ORB bracket under the live MAGNA53 geometry. Returns
    {outcome, r, entry, stop, orb_high, orb_low, fill_minute, stop_day} where outcome ∈
    {no_orb_bar, zero_range, stop_too_wide, invalid_risk, no_fill, filled}."""
    orb_candidates = [b for b in minute_rth if RTH_OPEN <= b["m"] < ORB_FETCH_END]
    if not orb_candidates:
        return {"outcome": "no_orb_bar"}
    orb = orb_candidates[0]                       # earliest bar (get_first_bar)
    hi, lo = orb["h"], orb["l"]
    ok, reason = validate_orb_entry(hi, lo, atr_14)
    if not ok:
        return {"outcome": reason.split(":")[1]}
    limit = stop_limit_buy_price(hi)
    scan_from = max(submission_m, orb["m"] + 1)

    fill_px = fill_idx = None
    armed_passthrough = False                     # triggered but limit not marketable
    for i, b in enumerate(minute_rth):
        if b["m"] < scan_from:
            continue
        if b["m"] >= FILL_END:
            break                                 # 10:00 ET unfilled-cancel
        if armed_passthrough:
            if b["l"] <= limit:                   # price came back into the limit
                fill_px, fill_idx = limit, i
                break
            continue
        if b["h"] >= hi:                          # stop trigger: last >= stop price
            if b["o"] <= hi:
                fill_px, fill_idx = hi, i         # crossed within the bar → ~trigger px
            elif b["o"] <= limit:
                fill_px, fill_idx = b["o"], i     # opened between trigger and limit
            else:
                armed_passthrough = True          # gap-through: wait for limit touch
                continue
            break
    if fill_px is None:
        return {"outcome": "no_fill", "orb_high": hi, "orb_low": lo}

    risk = fill_px - lo
    if risk <= 0:
        return {"outcome": "invalid_risk", "orb_high": hi, "orb_low": lo}
    path = de.build_mixed_path(minute_rth, fill_idx, daily_forward)
    if not path:
        return {"outcome": "invalid_risk", "orb_high": hi, "orb_low": lo}
    out = de.simulate(fill_px, lo, path, de.SETTLE_RULE, "pess")
    if out is None:
        return {"outcome": "invalid_risk", "orb_high": hi, "orb_low": lo}
    realized, _captured, fills = out
    return {"outcome": "filled", "r": realized, "entry": fill_px, "stop": lo,
            "orb_high": hi, "orb_low": lo,
            "fill_minute": minute_rth[fill_idx]["m"],
            "stop_day": fills[-1][0] if fills else None}


# ── aggregation (the #327 shapes) ────────────────────────────────────────────

def _median(xs):
    s = sorted(xs)
    if not s:
        return float("nan")
    m = len(s) // 2
    return s[m] if len(s) % 2 else (s[m - 1] + s[m]) / 2


def _stats(rs):
    if not rs:
        return {"n": 0}
    s = sorted(rs, reverse=True)
    tot = sum(s)
    ext = sum(s[3:])
    return {"n": len(s), "median": _median(s), "mean": tot / len(s), "total": tot,
            "win%": 100 * sum(1 for r in s if r > 0) / len(s),
            "top3_share%": (100 * (tot - ext) / tot) if tot else float("nan"),
            "ex_top3_mean": (ext / max(len(s) - 3, 1))}


def _fmt(d):
    if d.get("n", 0) == 0:
        return "n=0"
    return (f"n={d['n']}  median {d['median']:+.2f}R  mean {d['mean']:+.2f}R  "
            f"win {d['win%']:.0f}%  total {d['total']:+.1f}R  "
            f"top3 {d['top3_share%']:.0f}%  ex-top3 mean {d['ex_top3_mean']:+.2f}R")


def period_of(alert_date: str) -> str:
    return "clean" if (alert_date < CLEAN_LO or alert_date > CLEAN_HI) else "polluted"


def main() -> None:
    if "--pull-cohort" in sys.argv:
        pull_cohort()
        return
    if "--pull-bars" in sys.argv:
        pull_bars()
        return

    cohort = load_cohort()
    if not cohort:
        sys.exit(f"no cohort — run --pull-cohort then --pull-bars first")
    daily = load_daily()
    minute = load_minute()
    trades = load_trades()

    # dedupe to one row per (ticker, alert_date, tier) — earliest detection kept by the
    # SQL DISTINCT ON; drop MODERATEs that ALSO fired HIGH the same day (live already
    # entered them as HIGH; promotion wouldn't change them).
    high_days = {(r["ticker"], r["alert_date"]) for r in cohort if r["tier"] == "HIGH"}
    mods = [r for r in cohort if r["tier"] == "MODERATE"
            and (r["ticker"], r["alert_date"]) not in high_days]
    highs = [r for r in cohort if r["tier"] == "HIGH"]
    n_mod_shadowed = sum(1 for r in cohort if r["tier"] == "MODERATE"
                         and (r["ticker"], r["alert_date"]) in high_days)

    print("#468 — MODERATE-vs-HIGH realized-R (as-if ORB geometry, SETTLE_RULE, pess)")
    print(f"cohort: {len(mods)} MODERATE (excl {n_mod_shadowed} same-day-HIGH) "
          f"+ {len(highs)} HIGH  ·  minute-days {len(minute)}  ·  daily tickers {len(daily)}\n")

    def settle_tier(rows, assume_931_for_unknown_ts=False):
        res, funnel = [], defaultdict(int)
        for r in rows:
            funnel["alerts"] += 1
            gate, sub_m = eligibility(r)
            if gate != "ok":
                if gate in ("ts_missing", "ts_poisoned") and assume_931_for_unknown_ts:
                    sub_m = SUBMIT_MIN
                else:
                    funnel[gate] += 1
                    continue
            bars = daily.get(r["ticker"])
            ai = idx_of_date(bars, r["alert_date"]) if bars else None
            if ai is None:
                funnel["no_daily_bars"] += 1
                continue
            if len(bars) - 1 - ai < SETTLE_FWD:
                funnel["not_settleable"] += 1
                continue
            raw = minute.get((r["ticker"], r["alert_date"]))
            if not raw:
                funnel["no_minute_data"] += 1
                continue
            rth = de.polygon_to_rth_minutes(raw, r["alert_date"])
            rec = reconstruct(rth, sub_m, atr14_prior_close(bars, ai),
                              bars[ai + 1: ai + 1 + SETTLE_FWD])
            funnel[rec["outcome"]] += 1
            rec.update(ticker=r["ticker"], alert_date=r["alert_date"],
                       period=period_of(r["alert_date"]), fwd_5d=r["fwd_5d"],
                       ep_score=r["ep_score"])
            res.append(rec)
        return res, funnel

    def report_tier(label, res, funnel):
        fills = [x for x in res if x["outcome"] == "filled"]
        evaluable = fills + [x for x in res if x["outcome"] == "no_fill"]
        print(f"── {label} ──")
        print("  funnel: " + "  ".join(f"{k}={v}" for k, v in sorted(funnel.items())))
        if evaluable:
            print(f"  fill rate: {len(fills)}/{len(evaluable)} "
                  f"({100 * len(fills) / len(evaluable):.0f}%)")
        print(f"  filled-only     : {_fmt(_stats([x['r'] for x in fills]))}")
        print(f"  full universe   : "
              f"{_fmt(_stats([x.get('r', 0.0) if x['outcome'] == 'filled' else 0.0 for x in evaluable]))}"
              f"   (no-fill = 0R clean miss)")
        for per in ("clean", "polluted"):
            sub = [x["r"] for x in fills if x["period"] == per]
            print(f"    {per:<9}filled: {_fmt(_stats(sub))}")
        day0 = [x for x in fills if x.get("stop_day") == 0]
        stopped0 = [x for x in day0 if x["r"] < 0]
        if fills:
            print(f"  day-0 full exits: {len(day0)}/{len(fills)} "
                  f"(of which negative {len(stopped0)}) — the ORB-stop chop metric")
            spct = [100 * (x["entry"] - x["stop"]) / x["entry"] for x in fills]
            print(f"  stop distance   : median {_median(spct):.1f}% of entry "
                  f"(1-min ORB geometry)")
        raw = [x["fwd_5d"] for x in fills if x["fwd_5d"] is not None]
        if raw:
            print(f"  raw fwd_5d on the SAME filled names: avg {sum(raw)/len(raw):+.1f}% "
                  f"med {_median(raw):+.1f}% (n={len(raw)}) — the Q4 parity recheck")
        print()
        return fills

    mod_res, mod_funnel = settle_tier(mods)
    high_res, high_funnel = settle_tier(highs)
    mod_fills = report_tier("MODERATE — as-if ORB-entered (reconstructed)", mod_res, mod_funnel)
    high_fills = report_tier("HIGH — identical reconstruction (apples-to-apples)", high_res, high_funnel)

    if mod_fills and high_fills:
        dm, dh = _stats([x["r"] for x in mod_fills]), _stats([x["r"] for x in high_fills])
        print(f"HEAD-TO-HEAD (filled-only)  delta (MOD − HIGH): "
              f"median {dm['median'] - dh['median']:+.2f}R  mean {dm['mean'] - dh['mean']:+.2f}R\n")

    # sensitivity: unknown-timestamp rows assumed submitted at 9:31
    mod_res_s, _ = settle_tier(mods, assume_931_for_unknown_ts=True)
    s_fills = [x["r"] for x in mod_res_s if x["outcome"] == "filled"]
    print(f"sensitivity (MODERATE, ts-unknown assumed 9:31): filled {_fmt(_stats(s_fills))}\n")

    # ── HIGH actual (mi_live_trades, live exit engine) + calibration ─────────
    closed = [t for t in trades
              if t["status"] == "closed" and t["total_pnl"] is not None
              and (t["risk_dollars"] or 0) > 0]
    actual_r = {(t["ticker"], t["alert_date"]): t["total_pnl"] / t["risk_dollars"]
                for t in closed}
    print(f"── HIGH — ACTUAL (mi_live_trades magna53, closed n={len(closed)}; "
          f"live exit engine, R = total_pnl / risk_dollars) ──")
    print(f"  actual realized : {_fmt(_stats(list(actual_r.values())))}")
    by_status = defaultdict(int)
    for t in trades:
        by_status[t["status"]] += 1
    print("  all trade rows  : " + "  ".join(f"{k}={v}" for k, v in sorted(by_status.items())))
    paired = [(actual_r[(x['ticker'], x['alert_date'])], x["r"]) for x in high_fills
              if (x["ticker"], x["alert_date"]) in actual_r]
    if paired:
        da = [a - b for a, b in paired]
        print(f"  calibration     : n={len(paired)} names both actual+reconstructed → "
              f"actual−recon median {_median(da):+.2f}R mean {sum(da)/len(da):+.2f}R")
        print("    (the SETTLE_RULE↔live-exit-engine delta + any fill-model error; "
              "apply this sign when reading the MODERATE arm)")
    print("\n(MFE-free: anticipation.simulate over the faithful mixed minute+daily path, "
          "pess bound, +1R/+3R halves + day-5 time stop. Study only — THE LINE holds.)")


if __name__ == "__main__":
    main()
