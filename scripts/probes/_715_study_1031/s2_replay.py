"""#715 stage 2 — the $0 replay of the 51 flip-ups that became HIGH (2026-08-02..10-30) under the
CURRENT entry + exit rules, today's anchor vs three alternatives. BINDING PLAN: PLAN.md in this folder
(§1 population → §4 calibration → §2 rules → §3 outcome → §5 table → §6 rec). Reads ONLY the two
captured files (capture/c1_population.out, capture/c2_bars.out) — no DB, no network, no re-pull.

Output names follow the task card: s2_replay.txt (this printout; PLAN §0 called it
s2_replay_out.txt) + s2_rows.tsv (per-row detail) + RESULTS.md (written by hand from the printout).

Run from the repo root:  python scripts/probes/_715_study_1031/s2_replay.py > scripts/probes/_715_study_1031/s2_replay.txt

Reused, never copied (PLAN §2.1 / §3.1):
  * agents.market_intelligence.live_fill_counterfactuals.walk_arm — the #482 recorder's walker, depth_exit=True
  * agents.market_intelligence.broker.exit_logic.adr20_pct_from_bars — the live 16:45 job's ADR20
  * agents.market_intelligence.broker.hour_bar_walk.entry_walk / stop_limit_buy_price — the stop-limit walk
Everything printed BEFORE the line '=== OUTCOMES BELOW ===' is decided without reading an outcome bar.
"""
from __future__ import annotations

import json
import re
import statistics
import sys
from collections import defaultdict
from datetime import date, datetime, time, timedelta
from pathlib import Path
from typing import Optional
from zoneinfo import ZoneInfo

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[2]
sys.path.insert(0, str(REPO))

from agents.market_intelligence.broker.exit_logic import adr20_pct_from_bars  # noqa: E402
from agents.market_intelligence.broker.hour_bar_walk import entry_walk, stop_limit_buy_price  # noqa: E402
from agents.market_intelligence.live_fill_counterfactuals import walk_arm  # noqa: E402

_ET = ZoneInfo("America/New_York")
C1 = HERE / "capture" / "c1_population.out"
C2 = HERE / "capture" / "c2_bars.out"
ROWS_TSV = HERE / "s2_rows.tsv"

# ── constants fixed by the plan / the live code (PLAN §2) ──────────────────────────────────────
CHASE_CAP = 1.5                 # order_manager.CHASE_RISK_INFLATION_CAP
LIMIT_MULT = 1.002              # #500 limit = latest × 1.002
TARGET_R = 8.0                  # mi_strategies.profit_trigger_r (c1 STRATEGIES confirms)
BREAKEVEN_R = 3.0               # mi_strategies.breakeven_arm_r
ATR_MULT = 1.5                  # validate_orb_entry
ATR_LOOKBACK_CAL = 35           # compute_atr_14's window
ATR_MIN_ROWS = 10
PRIOR_CLOSES_CAL = 40           # the trail's prior closes
ADR_LOOKBACK_CAL = 60           # rows read for the ADR20 (last ≤20 used)
WINDOW_END = time(9, 45)        # ORB window: submit second < 09:45:00
CANCEL_AT = time(10, 0)         # unfilled → cancelled
H_DECISION = 20
H_RUNNER = 40
BORDERLINE_BAND = 0.002         # ±0.2% of the limit (PLAN §7)
AUTHORITY_DATE = date(2026, 8, 27)   # the admission-era split (PLAN §1)
FLOOR9_FIRST_SESSION = date(2026, 8, 20)   # rule_eras gap_floor_9 first acting session (fallback only)


# ── parsing ─────────────────────────────────────────────────────────────────────────────────────
def read_sections(path: Path) -> tuple[dict[str, list[dict]], dict[str, int]]:
    """'=== NAME ===' sections, first line = header, '|' separated. Lines before the first header
    and any row whose field count differs from the header are skipped and COUNTED (never parsed)."""
    out: dict[str, list[dict]] = {}
    skipped: dict[str, int] = defaultdict(int)
    cur, hdr = None, None
    with open(path, newline="", encoding="utf-8") as fh:
        for line in fh:
            line = line.rstrip("\n")
            if line.startswith("=== ") and line.endswith(" ==="):
                cur, hdr = line[4:-4], None
                out[cur] = []
                continue
            if cur is None or line == "":
                continue
            parts = line.split("|")
            if hdr is None:
                hdr = parts
                continue
            if len(parts) != len(hdr):
                skipped[cur] += 1
                continue
            out[cur].append(dict(zip(hdr, parts)))
    return out, dict(skipped)


def f(v) -> Optional[float]:
    try:
        return float(v) if v not in ("", None) else None
    except ValueError:
        return None


def d_(s: str) -> date:
    return date.fromisoformat(s)


def t_(s: str) -> Optional[time]:
    """'HH:MI:SS.MS' or 'HH:MI:SS' or 'HH:MI' → time."""
    if not s:
        return None
    try:
        return time.fromisoformat(s)
    except ValueError:
        return None


def hhmm_dt(d: date, hhmm: str) -> datetime:
    hh, mm = hhmm.split(":")
    return datetime(d.year, d.month, d.day, int(hh), int(mm), tzinfo=_ET)


def minute_after(t: time) -> time:
    dt = datetime.combine(date(2000, 1, 1), t.replace(second=0, microsecond=0)) + timedelta(minutes=1)
    return dt.time()


def tstr(t: Optional[time]) -> str:
    return t.strftime("%H:%M") if t else "-"


def r2(x: Optional[float], nd: int = 2) -> str:
    return "-" if x is None else f"{x:.{nd}f}"


# ── load ────────────────────────────────────────────────────────────────────────────────────────
c1, c1_skipped = read_sections(C1)
c2, c2_skipped = read_sections(C2)

print("=== #715 stage 2 replay — PLAN.md is binding; nothing below the OUTCOMES marker was seen before "
      "the sections above it were written ===")
print(f"run: {c1['RUN'][0]}")
print(f"c1 sections: {', '.join(f'{k}={len(v)}' for k, v in c1.items())}")
print(f"c2 sections: {', '.join(f'{k}={len(v)}' for k, v in c2.items())}")
print(f"skipped (field-count mismatch) lines: c1={c1_skipped or 'none'} c2={c2_skipped or 'none'}")

POP = c1["POP"]
assert c1["RUN"][0]["client_encoding"] == "UTF8", "the '≥' floor parse needs UTF8"

# ── §4 check 4 first half: population integrity (counts) ───────────────────────────────────────
checks = c1["CHECKS"][0]
mincount = c2["MINCOUNT"][0]
print("\n=== §4 CHECK 4 — population integrity ===")
print(f"POPCOUNT: {c1['POPCOUNT'][0]}  (10-30 reading was 871 / 51 / 3 / 10)")
print(f"CHECKS: {checks}")
n_min = len(c2["MIN"])
print(f"MINCOUNT.min_rows={mincount['min_rows']} ticker_days_with_bars={mincount['ticker_days_with_bars']}; "
      f"MIN lines parsed={n_min}")
assert int(checks["pop_rows"]) == 51 and len(POP) == 51, f"population is not 51 (CHECKS={checks['pop_rows']}, POP={len(POP)})"
assert int(checks["with_0930_bar"]) == 51, "a ticker-day has no 09:30 bar"
assert int(mincount["min_rows"]) == n_min, "MIN truncated in transfer"
assert int(c1["POPCOUNT"][0]["became_high"]) == 51
print("CHECK 4 (counts): PASS — 51 rows, 51 with the 09:30 bar, MIN complete")

# index the rest
MIN: dict[tuple[date, str], list[dict]] = defaultdict(list)
for r in c2["MIN"]:
    d = d_(r["d"])
    MIN[(d, r["ticker"])].append({"m": hhmm_dt(d, r["hhmm"]), "hhmm": r["hhmm"], "o": f(r["open"]),
                                  "h": f(r["high"]), "l": f(r["low"]), "c": f(r["close"]), "v": f(r["volume"])})
for k in MIN:
    MIN[k].sort(key=lambda b: b["m"])
DAILY: dict[str, list[dict]] = defaultdict(list)
for r in c2["DAILY"]:
    DAILY[r["ticker"]].append({"trade_date": d_(r["trade_date"]), "o": f(r["open_price"]), "h": f(r["high_price"]),
                               "l": f(r["low_price"]), "c": f(r["close"]), "v": f(r["volume"])})
for k in DAILY:
    DAILY[k].sort(key=lambda b: b["trade_date"])
SESSIONS = sorted(d_(r["trade_date"]) for r in c1["SESSIONS"])
LAST_SETTLED = SESSIONS[-1]
EVENTS: dict[tuple[date, str], list[dict]] = defaultdict(list)
for r in c1["EVENTS"]:
    EVENTS[(d_(r["d"]), r["t"])].append(r)
TRADES: dict[tuple[date, str], dict] = {}
for r in c1["TRADES"]:
    if r["signal_type"] == "magna53" and r["entry_attempt"] == "1":
        key = (d_(r["alert_date"]), r["ticker"])
        assert key not in TRADES, f"two magna53 attempt-1 rows for {key}"
        TRADES[key] = r
ORDERS: dict[str, list[dict]] = defaultdict(list)
for r in c1["ORDERS"]:
    ORDERS[r["trade_id"]].append(r)
ALERTS: dict[tuple[date, str], dict] = {}
for r in c1["ALERTS"]:
    ALERTS.setdefault((d_(r["alert_date"]), r["ticker"]), r)
SCAN: dict[tuple[date, str], list[dict]] = defaultdict(list)
for r in c1["SCANLOG"]:
    SCAN[(d_(r["scan_date"]), r["ticker"])].append(r)
COV: dict[tuple[date, str], dict] = {(d_(r["d"]), r["t"]): r for r in c1["COVERAGE"]}
CF_LIVE_REPLAY = [r for r in c1["CF"] if r["arm"] == "live_replay"]
toggles = {(r["safeguard"], r["account_mode"]): r["state"] for r in c1["TOGGLES"]}
assert toggles[("ep_rt_entry_gap_recheck", "global")] == "on"
strat = next(r for r in c1["STRATEGIES"] if r["strategy_id"] == "magna53")
assert f(strat["profit_trigger_r"]) == TARGET_R and f(strat["breakeven_arm_r"]) == BREAKEVEN_R
print(f"last settled session (c1 SESSIONS) = {LAST_SETTLED}; DAILY last date = "
      f"{max(b['trade_date'] for v in DAILY.values() for b in v)}; sessions listed = {len(SESSIONS)}")
print("gap re-check floor at submit: live_tracker.py:826 passes rt_gap_floor_pct=_MAGNA53_MIN_GAP_PCT = "
      "ep_detector.MIN_GAP_PCT (default 9.0; 10.0 before 2026-08-19) = the scan floor — the per-row floor "
      "parsed from the flip summary is used for both the scan floor and the submit re-check (PLAN §2.1.2).")
print("toggles confirmed: ep_rt_entry_gap_recheck=on, magna53 profit_trigger_r=8 breakeven_arm_r=3, "
      f"magna53_depth_exit live={toggles[('magna53_depth_exit', 'live')]}")

# ── per-row inputs (no outcome bar read here) ──────────────────────────────────────────────────
ORB_RE = re.compile(r"O=([\d.]+) H=([\d.]+) L=([\d.]+)")


def atr14_like_live(ticker: str, alert_day: date) -> tuple[Optional[float], int]:
    """compute_atr_14(ticker, today) as the 09:31 live path sees it: rows in [today−35d, today] with
    high/low present — today's own row is not stored yet at 09:31, so strictly before the day."""
    lo = alert_day - timedelta(days=ATR_LOOKBACK_CAL)
    rows = [b for b in DAILY[ticker] if lo <= b["trade_date"] < alert_day and b["h"] is not None and b["l"] is not None]
    if len(rows) < ATR_MIN_ROWS:
        return None, len(rows)
    trs = []
    for i in range(1, len(rows)):
        h, l, pc = rows[i]["h"], rows[i]["l"], rows[i - 1]["c"]
        trs.append(max(h - l, abs(h - pc), abs(l - pc)))
    if not trs:
        return None, len(rows)
    w = trs[-14:]
    return sum(w) / len(w), len(rows)


def pre_rows(ticker: str, alert_day: date, cal_days: int) -> list[dict]:
    lo = alert_day - timedelta(days=cal_days)
    return [b for b in DAILY[ticker] if lo <= b["trade_date"] < alert_day]


rows: list[dict] = []
for p in POP:
    d, t = d_(p["d"]), p["t"]
    row: dict = {"d": d, "t": t, "key": (d, t)}
    row["flip_t"] = t_(p["flip_et"])
    row["authoritative"] = p["authoritative"] == "true"
    row["era"] = "post" if row["authoritative"] else "pre"
    # floor: parsed from the summary, date fallback flagged
    fp = f(p["floor_pct_from_summary"])
    if fp is None:
        fp = 9.0 if d >= FLOOR9_FIRST_SESSION else 10.0
        row["floor_from_date"] = True
    else:
        row["floor_from_date"] = False
    row["floor_pct"] = fp
    # prev close: POP (get_prev_close's rule) cross-checked against every scan-log prev_close
    pc_pop = f(p["prev_close"])
    scan_pcs = sorted({f(s["prev_close"]) for s in SCAN[(d, t)] if f(s["prev_close"])})
    al = ALERTS.get((d, t))
    det_t = t_(al["detected_et"].split(" ")[1]) if al else None
    scan_at_det = [s for s in SCAN[(d, t)] if det_t and s["scan_et"] == det_t.strftime("%H:%M:%S") and f(s["prev_close"])]
    pc_scan = f(scan_at_det[0]["prev_close"]) if scan_at_det else (scan_pcs[0] if scan_pcs else None)
    row["prev_close_pop"], row["prev_close_scan"] = pc_pop, pc_scan
    row["prev_close_mismatch"] = (pc_pop is not None and pc_scan is not None and abs(pc_scan - pc_pop) / pc_pop > 0.005)
    row["prev_close"] = pc_scan if row["prev_close_mismatch"] else pc_pop
    row["floor_price"] = row["prev_close"] * (1 + fp / 100.0)
    # the stored 09:30 bar
    row["orb_o"], row["orb_h"], row["orb_l"], row["orb_c"] = f(p["orb_open"]), f(p["orb_high"]), f(p["orb_low"]), f(p["orb_close"])
    row["day0_open"], row["day0_high"], row["day0_low"], row["day0_close"] = f(p["day0_open"]), f(p["day0_high"]), f(p["day0_low"]), f(p["day0_close"])
    # events: submit second (orb_bar_fetched → orb_triggered → detected_at), the live ORB bar read
    ev = EVENTS[(d, t)]
    fetched = [e for e in ev if e["event_type"] == "orb_bar_fetched"]
    trig = [e for e in ev if e["event_type"] == "orb_triggered"]
    if fetched:
        row["submit_src"], row["submit_sec"] = "orb_bar_fetched", t_(fetched[0]["t_et"])
    elif trig:
        row["submit_src"], row["submit_sec"] = "orb_triggered", t_(trig[0]["t_et"])
    else:
        row["submit_src"], row["submit_sec"] = "detected_at", det_t
    row["detected_t"] = det_t
    row["alert_minute"] = max(time(9, 30), det_t.replace(second=0, microsecond=0)) if det_t else time(9, 30)
    ss = row["submit_sec"]
    row["submit_min"] = max(time(9, 31), minute_after(ss)) if ss else None
    row["in_window"] = bool(ss and (ss.hour == 9 and ss.minute < 45))
    row["live_orb"] = None
    if fetched:
        m = ORB_RE.search(fetched[0]["summary"])
        if m:
            row["live_orb"] = tuple(float(x) for x in m.groups())
    row["orb_mismatch"] = False
    if row["live_orb"]:
        lo_, lh_, ll_ = row["live_orb"]
        if any(abs(a - b) > 0.0051 for a, b in ((row["orb_o"], lo_), (row["orb_h"], lh_), (row["orb_l"], ll_))):
            row["orb_mismatch"] = True
            row["orb_o"], row["orb_h"], row["orb_l"] = lo_, lh_, ll_     # the live decision's bar wins
    # stored fate
    tr = TRADES.get((d, t))
    row["trade"] = tr
    if tr is None:
        row["fate"] = "no_trade_row"
    else:
        sr = tr["skip_reason"]
        st = tr["status"]
        if st in ("filled", "closed", "partial"):
            row["fate"] = "filled"
        elif sr.startswith("setup:chase_cap"):
            row["fate"] = "chase_cap_skip"
        elif sr.startswith("window:"):
            row["fate"] = "out_of_window"
        elif sr.startswith("setup:gap_below_floor"):
            row["fate"] = "gap_below_floor"
        elif sr.startswith("setup:"):
            row["fate"] = "other_setup_skip"
        elif sr.startswith("block:"):
            row["fate"] = "blocked"
        elif sr.startswith("infra:"):
            row["fate"] = "infra"
        elif sr.startswith("broker:"):
            row["fate"] = "broker_rejected"
        elif st == "cancelled":
            row["fate"] = "unfilled_cancel"
        else:
            row["fate"] = "other"
    # bars + coverage
    bars = MIN[(d, t)]
    row["bars"] = bars
    row["has_0930"] = bool(bars) and bars[0]["hhmm"] == "09:30"
    cov = COV[(d, t)]
    row["cov"] = (int(cov["rth_bars"]), int(cov["bars_0930_1000"]))
    # ATR14 (live rule) + cross-check against the stored trade row
    atr, n_atr = atr14_like_live(t, d)
    row["atr_calc"], row["atr_n"] = atr, n_atr
    row["atr_stored"] = f(tr["atr_14"]) if tr and tr.get("atr_14") else None
    row["atr_mismatch"] = (row["atr_stored"] is not None and atr is not None and abs(atr - row["atr_stored"]) > 1e-6 * max(1.0, row["atr_stored"]))
    row["atr"] = row["atr_stored"] if row["atr_mismatch"] else atr
    # exit inputs
    pre60 = pre_rows(t, d, ADR_LOOKBACK_CAL)
    row["adr20"] = adr20_pct_from_bars([{"h": b["h"], "l": b["l"], "c": b["c"]} for b in pre60])
    row["prior_closes"] = [b["c"] for b in pre_rows(t, d, PRIOR_CLOSES_CAL) if b["c"] is not None]
    # forward sessions (after the alert day = the fill day; first attempts only) through the last settled
    fwd_days = [s for s in SESSIONS if s > d][:H_RUNNER]
    by = {b["trade_date"]: b for b in DAILY[t]}
    sess = []
    for s in fwd_days:
        b = by.get(s)
        bar = None
        if b is not None and None not in (b["o"], b["h"], b["l"], b["c"]):
            bar = {"o": b["o"], "h": b["h"], "l": b["l"], "c": b["c"]}
        sess.append((s, bar))
    row["sessions"] = sess
    # geometry / crossing (bars only; the crossing is a definition, not an outcome)
    fpx = row["floor_price"]
    row["orb_ge_floor"] = row["orb_h"] >= fpx
    row["open_ge_floor"] = row["orb_o"] >= fpx
    cross_h = next((b for b in bars if b["h"] >= fpx), None)
    cross_c = next((b for b in bars if b["c"] >= fpx), None)
    row["cross_bar"], row["cross_bar_close"] = cross_h, cross_c
    rows.append(row)


def cross_class(b: Optional[dict]) -> str:
    if b is None:
        return "never"
    if b["hhmm"] == "09:30":
        return "09:30"
    return "09:31-09:44" if b["m"].time() < WINDOW_END else ">=09:45"


# ── §1 composition table (no outcome column) ───────────────────────────────────────────────────
print("\n=== §1 COMPOSITION — the 51, stated before any outcome ===")
print("split | count (n of 51)")


def count(pred) -> int:
    return sum(1 for r in rows if pred(r))


print(f"admission era (POP.authoritative flag; real-time gap authority first acting session 08-28): "
      f"pre={count(lambda r: r['era']=='pre')} post={count(lambda r: r['era']=='post')}  "
      f"[by flip date: before 08-27={count(lambda r: r['d'] < AUTHORITY_DATE)} on/after 08-27={count(lambda r: r['d'] >= AUTHORITY_DATE)}; "
      f"the four 08-27 rows (CHRN CRWD DG VEEV) carry authoritative=false — the toggle flipped 13:55 ET that day]")
print(f"floor on the day: 10%={count(lambda r: r['floor_pct']==10.0)} 9%={count(lambda r: r['floor_pct']==9.0)} "
      f"floor_from_date fallback fired={count(lambda r: r['floor_from_date'])}")
print(f"geometry: ORB high >= floor price={count(lambda r: r['orb_ge_floor'])} ORB high < floor price={count(lambda r: not r['orb_ge_floor'])}")
print(f"opening gap (09:30 bar open vs prev close): open >= floor={count(lambda r: r['open_ge_floor'])} below={count(lambda r: not r['open_ge_floor'])}")
cc = defaultdict(int)
for r in rows:
    cc[cross_class(r["cross_bar"])] += 1
print(f"first crossing minute (bar HIGH >= floor price): " + " ".join(f"{k}={v}" for k, v in sorted(cc.items())))
cc2 = defaultdict(int)
for r in rows:
    cc2[cross_class(r["cross_bar_close"])] += 1
print(f"  sensitivity (bar CLOSE >= floor price): " + " ".join(f"{k}={v}" for k, v in sorted(cc2.items())))
fc = defaultdict(int)
for r in rows:
    fc[r["fate"]] += 1
print("stored fate today: " + " ".join(f"{k}={v}" for k, v in sorted(fc.items())))
print(f"submit second source: " + " ".join(f"{k}={v}" for k, v in sorted(defaultdict(int, {s: count(lambda r, s=s: r['submit_src']==s) for s in ('orb_bar_fetched','orb_triggered','detected_at')}).items())))
print(f"in the ORB window (submit second < 09:45): {count(lambda r: r['in_window'])}; out: {count(lambda r: not r['in_window'])}")
print(f"minute-bar coverage: has 09:30 bar={count(lambda r: r['has_0930'])}; full 30 bars 09:30-10:00={count(lambda r: r['cov'][1]==30)}; "
      f"short (<30) in 09:30-10:00: " + ", ".join(f"{r['t']} {r['d']} {r['cov'][1]}/30" for r in rows if r['cov'][1] < 30))
print(f"prev_close POP vs scan log mismatch >0.5%: {count(lambda r: r['prev_close_mismatch'])}" +
      ("" if not count(lambda r: r['prev_close_mismatch']) else " — " + ", ".join(f"{r['t']} {r['d']} pop={r['prev_close_pop']} scan={r['prev_close_scan']}" for r in rows if r['prev_close_mismatch'])))
print(f"09:30 bar open vs official daily open (mi_daily_closes.open_price) >0.5% apart: " +
      (", ".join(f"{r['t']} {r['d']} bar={r['orb_o']} daily={r['day0_open']}" for r in rows if r['day0_open'] and abs(r['orb_o'] - r['day0_open']) / r['day0_open'] > 0.005) or "none"))
print("\nper-row composition (date ticker era floor% prevclose floorpx | ORB o/h/l | open>=floor orb_h>=floor | crossing(high) crossing(close) | submit src/sec/minute in_window | fate | bars 0930-1000)")
for r in rows:
    cb, cbc = r["cross_bar"], r["cross_bar_close"]
    print(f"{r['d']} {r['t']:5s} {r['era']:4s} {r['floor_pct']:.0f}% pc={r['prev_close']:.2f} floor={r['floor_price']:.2f} | "
          f"{r['orb_o']:.2f}/{r['orb_h']:.2f}/{r['orb_l']:.2f} | {int(r['open_ge_floor'])} {int(r['orb_ge_floor'])} | "
          f"{cb['hhmm'] if cb else 'never'} {cbc['hhmm'] if cbc else 'never'} | {r['submit_src']} {tstr(r['submit_sec'])} {tstr(r['submit_min'])} "
          f"{'IN' if r['in_window'] else 'OUT'} | {r['fate']} | {r['cov'][1]}/30")

# ── §4 check 3: stored 09:30 bar = the live ORB bar ───────────────────────────────────────────
print("\n=== §4 CHECK 3 — stored 09:30 bar vs the live orb_bar_fetched O/H/L ===")
n_live = count(lambda r: r["live_orb"] is not None)
mism = [r for r in rows if r["orb_mismatch"]]
print(f"ticker-days with an orb_bar_fetched row: {n_live}; mismatches (>0.005): {len(mism)}" +
      ("" if not mism else " — " + ", ".join(f"{r['t']} {r['d']} live={r['live_orb']}" for r in mism)))
print("CHECK 3: PASS" if not mism else "CHECK 3: mismatches listed; those rows use the audit row's O/H/L (plan §4.3)")

# ── §4 check 4 second half + ATR cross-check ───────────────────────────────────────────────────
print("\n=== §4 CHECK 4 — coverage per row (named above) + ATR14 cross-check ===")
atr_rows = [r for r in rows if r["atr_stored"] is not None]
atr_bad = [r for r in atr_rows if r["atr_mismatch"]]
print(f"rows with a stored atr_14: {len(atr_rows)}; replica mismatches: {len(atr_bad)}" +
      ("" if not atr_bad else " — " + ", ".join(f"{r['t']} calc={r['atr_calc']:.6f} stored={r['atr_stored']:.6f} n={r['atr_n']}" for r in atr_bad)))
atro = next(r for r in rows if r["t"] == "ATRO")
print(f"ATRO stop_too_wide text says 1.5x ATR $5.29 → ATR 3.527; replica ATR = {atro['atr']:.4f} (1.5x = {1.5*atro['atr']:.2f}); ORB range {atro['orb_h']-atro['orb_l']:.2f}")
print(f"rows with ATR unavailable (<10 daily rows): {count(lambda r: r['atr'] is None)}")
print(f"rows with no ADR20 (<10 pre sessions): {count(lambda r: r['adr20'] is None)}")
print("CHECK 4: PASS" if not atr_bad else "CHECK 4: ATR mismatches listed; the stored value wins on those rows")


# ── entry mechanics (PLAN §2.1 / §2.2) ─────────────────────────────────────────────────────────
def bar_at(bars: list[dict], t: time) -> Optional[dict]:
    return next((b for b in bars if b["m"].time() == t), None)


def bar_before(bars: list[dict], t: time) -> Optional[dict]:
    prev = [b for b in bars if b["m"].time() < t]
    return prev[-1] if prev else None


def proxies(row: dict, submit_min: time, alert_min: time) -> tuple[Optional[float], Optional[float]]:
    """(primary = OPEN of the submit-minute bar, sensitivity = CLOSE of the alert-minute bar)."""
    b = bar_at(row["bars"], submit_min)
    a = bar_at(row["bars"], alert_min)
    return (b["o"] if b else None), (a["c"] if a else None)


def limit_walk(bars: list[dict], limit: float, submit: time) -> dict:
    """#500 limit fallback: filled AT THE LIMIT on the first bar from the submit minute (before 10:00)
    whose low <= limit; never → no_entry on a fully covered window, else abstain (entry_walk's rule)."""
    window = [b for b in bars if submit <= b["m"].time() < CANCEL_AT]
    for b in window:
        if b["l"] <= limit:
            return {"status": "filled", "px": limit, "minute": b["m"]}
    expected = int((datetime.combine(date.min, CANCEL_AT) - datetime.combine(date.min, submit)).total_seconds() // 60)
    if len(window) < expected:
        return {"status": "abstain", "reason": f"entry_window_gaps:{expected-len(window)}_of_{expected}"}
    return {"status": "no_entry", "reason": "limit_never_reached"}


def replay_entry(row: dict, *, anchor_h: float, anchor_l: float, submit_min: Optional[time], in_window: bool,
                 proxy: Optional[float], planned: Optional[float] = None, stop_override: Optional[float] = None) -> dict:
    """One option's entry decision + fill for one row. Returns dict(path, reason, fill, minute, stop, limit, ...)."""
    out = {"path": None, "reason": None, "fill": None, "minute": None, "stop": None, "limit": None, "borderline": False}
    if not in_window or submit_min is None:
        out.update(path="out_of_window", reason=f"window:out_of_orb: submit {tstr(row['submit_sec'])}")
        return out
    if proxy is not None and proxy < row["floor_price"]:
        rt = (proxy - row["prev_close"]) / row["prev_close"] * 100
        out.update(path="gap_below_floor", reason=f"setup:gap_below_floor: rt {rt:.1f}% < {row['floor_pct']:.0f}% (proxy {proxy:.2f})")
        return out
    rng = anchor_h - anchor_l
    if rng <= 0:
        out.update(path="zero_range", reason="setup:zero_range")
        return out
    atr = row["atr"]
    if atr and atr > 0 and rng > ATR_MULT * atr:
        out.update(path="stop_too_wide", reason=f"setup:stop_too_wide: range {rng:.2f} > 1.5x ATR {atr:.2f}")
        return out
    stop = stop_override if stop_override is not None else (2 * anchor_l - anchor_h)
    if stop <= 0:
        out.update(path="stop_too_wide", reason="setup:stop_too_wide: 2R stop <= 0")
        return out
    out["stop"] = stop
    planned = planned if planned is not None else (anchor_h - stop)
    if proxy is not None and proxy > anchor_h:
        limit = round(proxy * LIMIT_MULT, 2)
        actual = limit - stop
        cap_limit = stop + CHASE_CAP * planned
        out["limit"] = limit
        out["borderline"] = abs(limit - cap_limit) <= BORDERLINE_BAND * limit
        out["cap_ratio"] = actual / planned if planned > 0 else None
        if planned <= 0 or actual > CHASE_CAP * planned:
            out.update(path="chase_cap_skip", reason=f"setup:chase_cap_exceeded: limit {limit:.2f} risk {actual:.2f}/sh vs planned {planned:.2f}/sh ({actual/planned if planned else float('inf'):.2f}x)")
            return out
        w = limit_walk(row["bars"], limit, submit_min)
        out["path"] = "limit"
        if w["status"] == "filled":
            out.update(fill=w["px"], minute=w["minute"], reason=f"limit fill {w['px']:.2f} @ {w['minute'].strftime('%H:%M')} ({actual/planned:.2f}x planned)")
        else:
            out.update(path="limit_" + w["status"], reason=w.get("reason"))
        return out
    w = entry_walk(row["bars"], anchor_h, submit_min, CANCEL_AT)
    out["path"] = "stop_limit"
    if w["status"] == "filled":
        out.update(fill=w["px"], minute=w["minute"], reason=f"stop-limit fill {w['px']:.2f} @ {w['minute'].strftime('%H:%M')}")
    else:
        out.update(path="stoplimit_" + w["status"], reason=w.get("reason"))
    return out


# ── §4 check 1: today's rule reproduces the stored SETUP fates ─────────────────────────────────
print("\n=== §4 CHECK 1 — today's rule vs the stored fates (mechanism first, then the proxy) ===")
# 1a. the proxy calibration: registered rows = limit fills (limit/1.002) + chase-cap skips (limit/1.002);
#     EXTRA (shown beside, not the deciding set): the gap_below_floor / broker skip texts' 'last $X'.
cal_reg, cal_extra = [], []
LAST_RE = re.compile(r"last \$([\d.]+)")
LIM_RE = re.compile(r"limit \$([\d.]+)")
for r in rows:
    tr = r["trade"]
    if tr is None:
        continue
    stored = src = None
    if r["fate"] == "chase_cap_skip":
        m = LIM_RE.search(tr["skip_reason"])
        stored, src = float(m.group(1)) / LIMIT_MULT, "cap-skip limit/1.002"
    elif r["fate"] == "filled":
        buys = [o for o in ORDERS[tr["id"]] if o["side"] == "buy" and o["order_type"] == "limit"]
        if buys:
            stored, src = float(buys[0]["limit_price"]) / LIMIT_MULT, "limit-fill limit/1.002"
    if stored is not None:
        cal_reg.append((r, stored, src))
        continue
    m = LAST_RE.search(tr["skip_reason"])
    if m:
        cal_extra.append((r, float(m.group(1)), "skip text 'last $'"))
    else:
        # the first gap_below_floor audit row on the day (CGEM / RARE / FTK: the retry's read)
        g = [e for e in EVENTS[r["key"]] if e["event_type"] == "orb_gap_below_floor"]
        if g:
            m = LAST_RE.search(g[0]["summary"])
            if m:
                cal_extra.append((r, float(m.group(1)), "audit gap_below_floor 'last $'"))


def cal_table(label: str, items: list) -> tuple[Optional[float], Optional[float]]:
    errs_p, errs_s = [], []
    print(f"{label} (n={len(items)}): ticker date | stored latest | primary(open of submit min) err% | sensitivity(close of alert min) err%")
    for r, stored, src in items:
        p, s = proxies(r, r["submit_min"], r["alert_minute"])
        ep = abs(p - stored) / stored * 100 if p is not None else None
        es = abs(s - stored) / stored * 100 if s is not None else None
        if ep is not None:
            errs_p.append(ep)
        if es is not None:
            errs_s.append(es)
        print(f"  {r['t']:5s} {r['d']} | {stored:.2f} ({src}) | {r2(p)} {r2(ep,3)}% | {r2(s)} {r2(es,3)}%  [submit {tstr(r['submit_min'])}, alert min {tstr(r['alert_minute'])}]")
    mp = statistics.median(errs_p) if errs_p else None
    ms = statistics.median(errs_s) if errs_s else None
    print(f"  median |error|: primary={r2(mp,3)}%  sensitivity={r2(ms,3)}%")
    return mp, ms


mp_reg, ms_reg = cal_table("1a. REGISTERED calibration rows (PLAN §2.1.3)", cal_reg)
mp_all, ms_all = cal_table("1a-extra. the same + every stored 'last $' read (information, not the deciding set)", cal_reg + cal_extra)
USE_SENS = mp_reg is not None and mp_reg > 0.3
print(f"PROXY DECISION (pre-registered: median |error| of the primary on the registered rows > 0.3% → the sensitivity becomes primary): "
      f"registered median primary={r2(mp_reg,3)}% → {'SENSITIVITY (close of the alert-minute bar) IS PRIMARY' if USE_SENS else 'PRIMARY (open of the submit-minute bar) STANDS'}")
if (mp_all is not None) and ((mp_all > 0.3) != USE_SENS):
    print("  NOTE: the wider set would have decided the other way — stated, not acted on (the registered rule is binding)")


def proxy_for(row: dict, submit_min: time, alert_min: time) -> Optional[float]:
    p, s = proxies(row, submit_min, alert_min)
    return s if USE_SENS else p


# 1b. per-row fate reproduction under TODAY's rule (the mechanism check uses the row's OWN stored
#     hard_stop for the cap verdict — pre-08-16 rows carried an ORB-low stop; today's stop is then run)
def today_entry(row: dict, stop_override: Optional[float] = None, proxy_override: Optional[float] = None) -> dict:
    proxy = proxy_override if proxy_override is not None else proxy_for(row, row["submit_min"], row["alert_minute"]) if row["submit_min"] else None
    return replay_entry(row, anchor_h=row["orb_h"], anchor_l=row["orb_l"], submit_min=row["submit_min"],
                        in_window=row["in_window"], proxy=proxy, stop_override=stop_override)


FATE_TO_PATH = {"filled": {"stop_limit", "limit"}, "chase_cap_skip": {"chase_cap_skip"}, "out_of_window": {"out_of_window"},
                "gap_below_floor": {"gap_below_floor"}, "other_setup_skip": {"stop_too_wide", "zero_range"},
                "unfilled_cancel": {"stoplimit_no_entry", "limit_no_entry"}}
print("\n1b. per-row: ticker date | stored fate (skip text) | replay path under today's rule | mechanism check with the row's own stored stop/latest | verdict")
match = mismatch = nonsetup = 0
mismatch_rows = []
for r in rows:
    tr = r["trade"]
    rep = today_entry(r)
    r["today"] = rep
    fate = r["fate"]
    verdict = ""
    mech = ""
    if fate in ("blocked", "infra", "broker_rejected", "no_trade_row"):
        nonsetup += 1
        verdict = f"non-setup live stop ({tr['skip_reason'][:40] if tr else 'no row'}) — replay {'enters' if rep['fill'] else rep['path']}; stays in every population"
    else:
        ok = rep["path"] in FATE_TO_PATH.get(fate, set())
        if fate == "filled" and ok:
            live_px = f(tr["entry_price"])
            ok = rep["fill"] is not None and abs(rep["fill"] - live_px) / live_px <= 0.005
            mech = f"fill {r2(rep['fill'])} vs live {live_px:.4f} ({abs(rep['fill']-live_px)/live_px*100 if rep['fill'] else float('nan'):.2f}%)"
        if fate == "chase_cap_skip":
            # mechanism: the row's own hard_stop + the stored latest reproduce the live verdict?
            stored_latest = next((s for rr, s, _ in cal_reg if rr is r), None)
            own = today_entry(r, stop_override=f(tr["hard_stop"]), proxy_override=stored_latest)
            mech = f"own stop {f(tr['hard_stop']):.2f} + stored latest {stored_latest:.2f} → {own['path']} ({own.get('cap_ratio') and round(own['cap_ratio'],2)}x)"
            if not ok and own["path"] == "chase_cap_skip":
                # today's stop (2·low−high) differs from the row's ORB-low stop → stop-era, not a mismatch
                today_stop = 2 * r["orb_l"] - r["orb_h"]
                if abs(today_stop - f(tr["hard_stop"])) > 0.005:
                    ok = True
                    verdict = "STOP ERA: live refused under the ORB-low stop; today's 2R stop admits the same limit — not a mismatch (listed)"
                elif rep["borderline"] or rep["path"] in ("limit", "limit_no_entry", "limit_abstain"):
                    ok = True
                    verdict = "BORDERLINE: the stored latest reproduces the live refusal; the minute proxy flips it (plan §7 band)"
        if fate == "gap_below_floor" and not ok:
            stored_latest = next((s for rr, s, _ in cal_extra if rr is r), None)
            if stored_latest is not None:
                own = today_entry(r, proxy_override=stored_latest)
                mech = f"stored latest {stored_latest:.2f} → {own['path']}"
                if own["path"] == "gap_below_floor":
                    ok = True
                    verdict = "BORDERLINE: the stored latest reproduces the live skip; the minute proxy reads above the floor"
        if fate == "filled" and not ok and rep["path"] in ("limit", "stop_limit") and rep["fill"] is not None:
            live_px = f(tr["entry_price"])
            buys = [o for o in ORDERS[tr["id"]] if o["side"] == "buy"]
            if buys and buys[0]["order_type"] == "limit":
                stored_latest = float(buys[0]["limit_price"]) / LIMIT_MULT
                own = today_entry(r, proxy_override=stored_latest)
                mech = f"stored latest {stored_latest:.2f} → {own['path']} fill {r2(own['fill'])} vs live {live_px:.4f}"
                if own["fill"] is not None and abs(own["fill"] - live_px) / live_px <= 0.005:
                    ok = True
                    verdict = "BORDERLINE/PROXY: the stored latest reproduces the live fill within 0.5%; the minute proxy does not"
        if ok:
            match += 1
            verdict = verdict or "match"
        else:
            mismatch += 1
            mismatch_rows.append(r)
            verdict = verdict or "MISMATCH"
    print(f"  {r['t']:5s} {r['d']} | {fate} ({(tr['skip_reason'] if tr else '')[:60]}) | {rep['path']} ({rep['reason']}) | {mech} | {verdict}")
regn = next(r for r in rows if r["t"] == "REGN")
regn_rep = regn["today"]
print(f"\nREGN acceptance: replay path={regn_rep['path']} reason={regn_rep['reason']} (plan: must refuse at planned $52.38 vs actual >= $78.57) → "
      f"{'PASS' if regn_rep['path']=='chase_cap_skip' and abs(2*regn['orb_l']-regn['orb_h']-817.5)<0.01 else 'FAIL'}")
print(f"CHECK 1 tally: setup/window fates matched={match} mismatched={mismatch} non-setup live stops (listed, replay enters them)={nonsetup}")
if mismatch:
    print("CHECK 1: FAIL — mismatches: " + ", ".join(f"{r['t']} {r['d']}" for r in mismatch_rows))
else:
    print("CHECK 1: PASS")

# ── §4 check 2: the depth walk reproduces the recorder (depth-era live_replay rows only) ────────
print("\n=== §4 CHECK 2 — offline depth walk vs the recorder's live_replay rows ===")
check2_fail = False
for c in CF_LIVE_REPLAY:
    key = (d_(c["alert_date"]), c["ticker"])
    r = next(x for x in rows if x["key"] == key)
    tr = r["trade"]
    is_depth = "depth" in (c["exit_rules_json"] or "")
    if not is_depth:
        print(f"  {c['ticker']} {c['alert_date']} live_replay {c['exit_era']} (pre-depth era) — listed, NOT compared: realized_r={c['realized_r']} {c['final_reason']} s{c['exit_session']}")
        continue
    entry = f(c["entry_price"]); stop = f(c["stop_price"]); orb_low = f(c["orb_low"])
    filled_t = t_(tr["filled_et"].split(" ")[1]).replace(second=0, microsecond=0)
    bars = [{"m": b["m"], "o": b["o"], "h": b["h"], "l": b["l"], "c": b["c"]} for b in r["bars"]]
    fill_idx = next(i for i, b in enumerate(bars) if b["m"].time() == filled_t)
    res = walk_arm(entry=entry, stop=stop, target=entry + TARGET_R * (entry - orb_low), day0_bars=bars, fill_idx=fill_idx,
                   sessions=r["sessions"], prior_closes=r["prior_closes"], harvest="live_ladder", fill_day=r["d"],
                   breakeven_at_partial=True, trail_prior_closes=True, ladder_partial=False, horizon=H_RUNNER,
                   breakeven_at_r=BREAKEVEN_R, r_frame_ps=entry - orb_low, trail_mode="sma", depth_exit=True,
                   depth_adr20_pct=r["adr20"])
    rr = (res["pnl_per_share"] / (entry - stop)) if res["status"] == "settled" else None
    ok = (res["status"] == "settled" and rr is not None and abs(rr - f(c["realized_r"])) <= 0.01
          and res["final_reason"] == c["final_reason"] and str(res["exit_session"]) == c["exit_session"])
    print(f"  {c['ticker']} {c['alert_date']} DEPTH era: offline status={res['status']} realized_r={r2(rr,4)} {res['final_reason']} s{res['exit_session']} "
          f"| stored realized_r={c['realized_r']} {c['final_reason']} s{c['exit_session']} | adr20={r2(r['adr20'],5)} stored {c['adr20_pct']}% | {'PASS' if ok else 'FAIL'}")
    if not ok:
        check2_fail = True
        print(f"    exits={json.dumps(res['exits'], default=str)}")
print("CHECK 2: " + ("FAIL" if check2_fail else "PASS") + " (c2 MIN stops at 15:59 — the recorder's day-0 list carries a 16:00 bar; a difference confined to that bar is a capture bound)")

if mismatch or check2_fail:
    print("\nA CALIBRATION CHECK FAILED — the option table is not read (PLAN §4). Stopping.")
    sys.exit(2)

# ── the options (PLAN §2.2) — decisions and fills, still no outcome bar ───────────────────────
print("\n=== §2.2 OPTION ENTRIES (fills only; outcomes are below the marker) ===")
OPTIONS = ["today", "a", "b", "c"]


def option_entry(row: dict, opt: str) -> dict:
    fpx = row["floor_price"]
    if opt == "today":
        e = dict(row["today"]); e.update(anchor_h=row["orb_h"], anchor_l=row["orb_l"], budget_den=None, note="")
    elif opt == "b":
        if not row["open_ge_floor"]:
            e = {"path": "b_open_below_floor", "reason": f"09:30 open {row['orb_o']:.2f} < floor {fpx:.2f}", "fill": None, "minute": None,
                 "stop": None, "limit": None, "borderline": False}
        else:
            e = dict(row["today"])
        e.update(anchor_h=row["orb_h"], anchor_l=row["orb_l"], note="")
    elif opt == "c":
        planned_c = max(row["orb_h"], fpx) - (2 * row["orb_l"] - row["orb_h"])
        proxy = proxy_for(row, row["submit_min"], row["alert_minute"]) if row["submit_min"] else None
        e = replay_entry(row, anchor_h=row["orb_h"], anchor_l=row["orb_l"], submit_min=row["submit_min"], in_window=row["in_window"],
                         proxy=proxy, planned=planned_c)
        e.update(anchor_h=row["orb_h"], anchor_l=row["orb_l"], planned_c=planned_c, note=("floor>ORB high" if fpx > row["orb_h"] else ""))
    elif opt == "a":
        cb = row["cross_bar"]
        if cb is None:
            e = {"path": "a_no_crossing_bar", "reason": "no RTH bar reached the floor price", "fill": None, "minute": None, "stop": None, "limit": None, "borderline": False}
            e.update(anchor_h=None, anchor_l=None, note="")
        elif cb["hhmm"] == "09:30":
            e = dict(row["today"]); e.update(anchor_h=row["orb_h"], anchor_l=row["orb_l"], note="crossing bar = 09:30 bar → identical to today")
        else:
            submit_a = max(row["submit_min"], minute_after(cb["m"].time())) if row["submit_min"] else None
            in_win = row["in_window"] and cb["m"].time() <= time(9, 43) and submit_a is not None and submit_a < WINDOW_END
            if not in_win:
                e = {"path": "out_of_window", "reason": f"crossing bar {cb['hhmm']} / submit {tstr(submit_a)} outside the window", "fill": None,
                     "minute": None, "stop": None, "limit": None, "borderline": False}
            else:
                pb = bar_at(row["bars"], submit_a)
                prev = bar_before(row["bars"], submit_a)
                proxy = (prev["c"] if prev else None) if USE_SENS else (pb["o"] if pb else None)
                e = replay_entry(row, anchor_h=cb["h"], anchor_l=cb["l"], submit_min=submit_a, in_window=True, proxy=proxy)
            e.update(anchor_h=cb["h"], anchor_l=cb["l"], note=f"crossing bar {cb['hhmm']} h={cb['h']:.2f} l={cb['l']:.2f} submit {tstr(submit_a)}")
    else:
        raise ValueError(opt)
    if e.get("fill") is not None:
        e["budget_den"] = e["anchor_h"] - e["stop"]
        e["own_den"] = e["fill"] - e["stop"]
        e["cprime_den"] = max(row["orb_h"], fpx) - e["stop"] if opt == "c" else None
    return e


for r in rows:
    r["opt"] = {o: option_entry(r, o) for o in OPTIONS}

print("ticker date | today | (a) | (b) | (c)   [path fill@minute stop | note]")
for r in rows:
    cells = []
    for o in OPTIONS:
        e = r["opt"][o]
        if e["fill"] is not None:
            cells.append(f"{e['path']} {e['fill']:.2f}@{e['minute'].strftime('%H:%M')} stop {e['stop']:.2f}" + (" BORDER" if e.get("borderline") else ""))
        else:
            cells.append(f"{e['path']}" + (" BORDER" if e.get("borderline") else ""))
    note = " | ".join(x for x in (r["opt"]["a"].get("note", ""), r["opt"]["c"].get("note", "")) if x)
    print(f"  {r['t']:5s} {r['d']} | " + " | ".join(cells) + (f"   [{note}]" if note else ""))
for o in OPTIONS:
    print(f"{o}: enters {sum(1 for r in rows if r['opt'][o]['fill'] is not None)} of 51; paths: " +
          " ".join(f"{k}={v}" for k, v in sorted(defaultdict(int, {p: sum(1 for r in rows if r['opt'][o]['path'] == p) for p in {r['opt'][o]['path'] for r in rows}}).items())))
def _outcome(e: dict) -> tuple:
    """entry outcome = (fill, stop) when entered, (None, None) when not — a stop computed on a row that
    never entered is not an outcome (REGN under (a)/(b) vs today's cap skip read as 'different' before)."""
    return (e["fill"], e["stop"]) if e["fill"] is not None else (None, None)


same = {o: sum(1 for r in rows if _outcome(r["opt"][o]) == _outcome(r["opt"]["today"])) for o in OPTIONS}
same_path = {o: sum(1 for r in rows if (r["opt"][o]["fill"], r["opt"][o]["stop"], r["opt"][o]["path"]) == (r["opt"]["today"]["fill"], r["opt"]["today"]["stop"], r["opt"]["today"]["path"])) for o in OPTIONS}
print("same OUTCOME as today (entered-or-not + fill + stop): " + " ".join(f"{o}={same[o]}" for o in OPTIONS) +
      "   [same path label too: " + " ".join(f"{o}={same_path[o]}" for o in OPTIONS) + "]")
cross_0930 = [r for r in rows if r["cross_bar"] is not None and r["cross_bar"]["hhmm"] == "09:30"]
assert all((r["opt"]["a"]["fill"], r["opt"]["a"]["stop"]) == (r["opt"]["today"]["fill"], r["opt"]["today"]["stop"]) for r in cross_0930), "(a) must equal today when the crossing bar is the 09:30 bar"
print(f"(a) ≡ today on the {len(cross_0930)} rows whose crossing bar is the 09:30 bar: asserted")
print("borderline cap verdicts (|limit − cap limit| <= 0.2% of the limit): " +
      (", ".join(f"{r['t']} {r['d']} [{o}]" for r in rows for o in OPTIONS if r["opt"][o].get("borderline")) or "none"))

print("\n=== OUTCOMES BELOW === (everything above was written without reading a bar after the entry)")


# ── §3 outcome walks ───────────────────────────────────────────────────────────────────────────
def walk(row: dict, e: dict, horizon: int) -> dict:
    bars = [{"m": b["m"], "o": b["o"], "h": b["h"], "l": b["l"], "c": b["c"]} for b in row["bars"]]
    fill_idx = next(i for i, b in enumerate(bars) if b["m"] == e["minute"])
    entry, stop = e["fill"], e["stop"]
    res = walk_arm(entry=entry, stop=stop, target=entry + TARGET_R * (entry - e["anchor_l"]), day0_bars=bars, fill_idx=fill_idx,
                   sessions=row["sessions"][:horizon], prior_closes=row["prior_closes"], harvest="live_ladder", fill_day=row["d"],
                   breakeven_at_partial=True, trail_prior_closes=True, ladder_partial=False, horizon=horizon,
                   breakeven_at_r=BREAKEVEN_R, r_frame_ps=entry - e["anchor_l"], trail_mode="sma", depth_exit=True,
                   depth_adr20_pct=row["adr20"])
    out = {"status": res["status"], "reason": res.get("reason") or res.get("final_reason"), "final": res.get("final_reason"),
           "exit_session": res.get("exit_session"), "gap_through": res.get("gap_through"), "partial": res.get("partial_fired"),
           "sessions_walked": res.get("sessions_walked"), "pnl": None, "mark": None}
    if res["status"] == "settled":
        out["pnl"] = res["pnl_per_share"]
    elif res["status"] == "horizon":
        out["mark"] = res["mark_pnl_per_share"]
    return out


def fixed_horizon(row: dict, e: dict, n_sessions: int = H_DECISION) -> dict:
    """§3.2 — from the fill: best high + the close over the next n sessions (day 0 after the fill
    minute included), and whether the placed stop was touched before +3 budget-R (same bar → ambiguous)."""
    entry, stop = e["fill"], e["stop"]
    lvl3 = entry + 3.0 * e["budget_den"]
    best_h, last_c = entry, None
    first = None
    after = [b for b in row["bars"] if b["m"] > e["minute"]]
    for b in after:
        best_h = max(best_h, b["h"])
        last_c = b["c"]
        if first is None:
            hs, ht = b["l"] <= stop, b["h"] >= lvl3
            first = "ambiguous" if (hs and ht) else ("stop_first" if hs else ("target_first" if ht else None))
    n = 0
    for s, b in row["sessions"][:n_sessions]:
        if b is None:
            break
        n += 1
        best_h = max(best_h, b["h"])
        last_c = b["c"]
        if first is None:
            hs, ht = b["l"] <= stop, b["h"] >= lvl3
            first = "ambiguous" if (hs and ht) else ("stop_first" if hs else ("target_first" if ht else None))
    return {"n": n, "best_r_budget": (best_h - entry) / e["budget_den"], "best_r_own": (best_h - entry) / e["own_den"],
            "close_r_budget": ((last_c - entry) / e["budget_den"]) if last_c is not None else None, "first": first or "neither"}


for r in rows:
    for o in OPTIONS:
        e = r["opt"][o]
        if e["fill"] is None:
            continue
        e["w20"] = walk(r, e, H_DECISION)
        e["w40"] = walk(r, e, H_RUNNER)
        e["fh"] = fixed_horizon(r, e)


def R(e: dict, w: dict, den_key: str = "budget_den") -> Optional[float]:
    den = e[den_key]
    if w["pnl"] is not None:
        return w["pnl"] / den
    return None


def MARK(e: dict, w: dict, den_key: str = "budget_den") -> Optional[float]:
    return (w["mark"] / e[den_key]) if w["mark"] is not None else None


def summarise(opt: str, den_key: str = "budget_den", subset=None) -> dict:
    sel = [r for r in rows if (subset is None or subset(r))]
    ents = [(r, r["opt"][opt]) for r in sel if r["opt"][opt]["fill"] is not None]
    st = defaultdict(int)
    rs, marks, worst, worst_gap = [], [], None, False
    for r, e in ents:
        w = e["w20"]
        st[w["status"]] += 1
        if w["status"] == "settled":
            x = R(e, w, den_key)
            rs.append((r["t"], x, w))
            if worst is None or x < worst:
                worst, worst_gap = x, bool(w["gap_through"])
        elif w["status"] == "horizon":
            marks.append((r["t"], MARK(e, w, den_key)))
    settled = [x for _, x, _ in rs]
    wins = sum(1 for x in settled if x > 0)
    big = [(t, x) for t, x, _ in rs if x >= 3.0]
    big_marked = [(t, x) for t, x in marks if x is not None and x >= 3.0]
    tail = sum(max(0.0, x - 3.0) for x in settled)
    r40 = [(r["t"], R(e, e["w40"], den_key)) for r, e in ents if e["w40"]["status"] == "settled"]
    big40 = [(t, x) for t, x in r40 if x is not None and x >= 3.0]
    big40_marked = [(r["t"], MARK(e, e["w40"], den_key)) for r, e in ents if e["w40"]["status"] == "horizon" and (MARK(e, e["w40"], den_key) or 0) >= 3.0]
    today_names = {r["t"] + " " + str(r["d"]) for r in sel if r["opt"]["today"]["fill"] is not None}
    names = {r["t"] + " " + str(r["d"]) for r, _ in ents}
    fh = [e["fh"] for _, e in ents]
    return {"opt": opt, "n": len(sel), "enter": len(ents), "settled": st["settled"], "horizon": st["horizon"], "pending": st["pending"], "abstain": st["abstain"],
            "wins": wins, "win_share": (wins / len(settled)) if settled else None, "big": big, "big_marked": big_marked, "tail": tail,
            "sum": sum(settled), "worst": worst, "worst_gap": worst_gap, "adds": sorted(names - today_names), "drops": sorted(today_names - names),
            "big40": big40, "big40_marked": big40_marked, "settled40": len(r40),
            "fh_reach3": sum(1 for x in fh if x["first"] == "target_first"), "fh_stop_first": sum(1 for x in fh if x["first"] == "stop_first"),
            "fh_ambig": sum(1 for x in fh if x["first"] == "ambiguous"), "fh_neither": sum(1 for x in fh if x["first"] == "neither"),
            "fh_best_med": statistics.median([x["best_r_budget"] for x in fh]) if fh else None,
            "fh_best_max": max((x["best_r_budget"] for x in fh), default=None),
            "settled_list": rs, "marks": marks}


def fmt_names(lst) -> str:
    return ", ".join(f"{t} {x:+.2f}" for t, x in lst) if lst else "none"


print("\n=== §5 THE TABLE — budget-R (pnl per share ÷ (anchor high − placed stop)), 20-session decision horizon ===")
HDR = ("option | enter (of n) | same as today | settled/horizon/pending/abstain | win share | big winners >=+3R settled | marked | "
       "tail R sum(R-3)+ | sum R (settled) | worst loss (gap-through?) | adds / drops vs today | >=+3R at 40 sessions settled | marked")
SUMS = {}


def print_table(subset=None, label=""):
    print(label)
    print(HDR)
    for opt, den in (("today", "budget_den"), ("a", "budget_den"), ("b", "budget_den"), ("c", "budget_den"), ("c'", "cprime_den")):
        base = "c" if opt == "c'" else opt
        s = summarise(base, den, subset)
        s["label"] = opt
        SUMS[(opt, label)] = s
        print(f"{opt} | {s['enter']} of {s['n']} | {'—' if opt=='today' else same[base] if subset is None else '-'} | "
              f"{s['settled']}/{s['horizon']}/{s['pending']}/{s['abstain']} | "
              f"{(f'{s['wins']} of {s['settled']} ({s['win_share']*100:.0f}%)') if s['settled'] else 'n/a'} | "
              f"{len(s['big'])} [{fmt_names(s['big'])}] | {len(s['big_marked'])} [{fmt_names(s['big_marked'])}] | "
              f"{s['tail']:+.2f} | {s['sum']:+.2f} (n={s['settled']}) | {r2(s['worst'])}{' gap-through' if s['worst_gap'] else ''} | "
              f"adds {s['adds'] or '-'} / drops {s['drops'] or '-'} | {len(s['big40'])} of {s['settled40']} [{fmt_names(s['big40'])}] | {len(s['big40_marked'])} [{fmt_names(s['big40_marked'])}]")
    print("§3.2 fixed 20-session horizon (harness-independent): option | reached +3 budget-R before the stop | stop first | ambiguous | neither | median best-high R | max best-high R")
    for opt, den in (("today", "budget_den"), ("a", "budget_den"), ("b", "budget_den"), ("c", "budget_den"), ("c'", "cprime_den")):
        s = SUMS[(opt, label)]
        print(f"{opt} | {s['fh_reach3']} | {s['fh_stop_first']} | {s['fh_ambig']} | {s['fh_neither']} | {r2(s['fh_best_med'])} | {r2(s['fh_best_max'])}  (n={s['enter']})")


print_table(None, "ALL 51")
print_table(lambda r: r["era"] == "post", "\nPOST-08-27 cohort (real-time gap authoritative; n=19)")
print_table(lambda r: r["era"] == "pre", "\nPRE-08-27 cohort (n=32)")

print("\nper-entry outcomes (option ticker date | fill stop budget-den | 20s: status R/mark final exit_session | 40s: status R/mark | fixed: first best_R)")
for o in ("today", "a", "b", "c"):
    for r in rows:
        e = r["opt"][o]
        if e["fill"] is None:
            continue
        w, w4, fh = e["w20"], e["w40"], e["fh"]
        x = R(e, w); m = MARK(e, w); x4 = R(e, w4); m4 = MARK(e, w4)
        print(f"  {o:5s} {r['t']:5s} {r['d']} | {e['fill']:.2f} {e['stop']:.2f} {e['budget_den']:.2f}" + (f" (c' den {e['cprime_den']:.2f})" if o == "c" and e.get("cprime_den") else "") +
              f" | {w['status']} {r2(x)}/{r2(m)} {w['final']} s{w['exit_session']}{' GAP' if w['gap_through'] else ''}{' partial' if w['partial'] else ''}"
              f" | {w4['status']} {r2(x4)}/{r2(m4)} | {fh['first']} {fh['best_r_budget']:.2f}")

# ── §6 the rule ────────────────────────────────────────────────────────────────────────────────
print("\n=== §6 RECOMMENDATION RULE (pre-registered; read at 20 sessions; baseline = today) ===")
base = SUMS[("today", "ALL 51")]


def evaluate(s: dict, opt: str) -> tuple[bool, list[str]]:
    why = []
    c1_ = s["enter"] >= 10 and s["settled"] >= 6
    why.append(f"1 sample: enters {s['enter']}>=10 and settled {s['settled']}>=6 → {'ok' if c1_ else 'FAIL'}")
    if opt == "b":
        dropped = [r for r in rows if r["opt"]["today"]["fill"] is not None and r["opt"]["b"]["fill"] is None]
        dr = []
        dbig = False
        for r in dropped:
            e = r["opt"]["today"]
            x = R(e, e["w20"]); m = MARK(e, e["w20"])
            if x is not None:
                dr.append(x)
                dbig |= x >= 3.0
            if m is not None:
                dbig |= m >= 3.0
        # POST-HOC GUARD (added after the OUTCOMES marker, advisor review 10-31): rule 2 is NOT evaluable
        # while a dropped name is still pending/abstain — an empty or partial settled sum must never read
        # as "negative". It is a correctness guard on the pre-registered rule, not a fit: on this run every
        # dropped name is settled, so it changes nothing.
        n_unknown = sum(1 for r in dropped if r["opt"]["today"]["w20"]["status"] not in ("settled", "horizon"))
        c2_ = bool(dropped) and n_unknown == 0 and sum(dr) < 0 and not dbig
        why.append(f"2 (b) drops {len(dropped)} names, their settled sum {sum(dr):+.2f} (n={len(dr)}) negative and no big winner settled/marked"
                   + (f" — NOT EVALUABLE: {n_unknown} dropped name(s) pending/abstain" if n_unknown else "") + f" → {'ok' if c2_ else 'FAIL'}")
    else:
        c2_ = s["enter"] >= base["enter"]
        why.append(f"2 access: enters {s['enter']} >= today's {base['enter']} → {'ok' if c2_ else 'FAIL'}")
    c3_ = len(s["big"]) >= len(base["big"]) and s["tail"] >= base["tail"] - 1e-9
    why.append(f"3 tail: big winners {len(s['big'])} >= {len(base['big'])} and tail {s['tail']:+.2f} >= {base['tail']:+.2f} → {'ok' if c3_ else 'FAIL'}")
    c4_ = s["sum"] >= base["sum"] + 2.0
    why.append(f"4 sum: {s['sum']:+.2f} >= today {base['sum']:+.2f} + 2.0 → {'ok' if c4_ else 'FAIL'}")
    c5_ = s["worst"] is None or s["worst"] >= -1.6
    why.append(f"5 worst loss {r2(s['worst'])} >= -1.6 → {'ok' if c5_ else 'FAIL'}")
    return all((c1_, c2_, c3_, c4_, c5_)), why


passed = []
for opt in ("a", "b", "c", "c'"):
    s = SUMS[(opt, "ALL 51")]
    ok, why = evaluate(s, "c" if opt == "c'" else opt)
    print(f"{opt}: {'CLEARS' if ok else 'does not clear'}\n   " + "\n   ".join(why))
    if ok:
        passed.append(opt)
if "c" in passed and "c'" in passed:
    passed.remove("c'")
if "c" not in passed and "c'" in passed:
    print("   (c) fails only on worst loss but (c') brings it inside → the rec names (c')")
order = {"b": 0, "c": 1, "c'": 1, "a": 2}
# §6 cohort clause: "if the pre-/post-08-27 cohorts disagree in direction, the post-08-27 cohort decides
# and the disagreement is stated". The clause is pre-registered; its IMPLEMENTATION here was written after
# the OUTCOMES marker (the first run only printed the directions) — stated for honesty.
post_today, post = SUMS[("today", "\nPOST-08-27 cohort (real-time gap authoritative; n=19)")], {}
for opt in ("a", "b", "c", "c'"):
    s = SUMS[(opt, "\nPOST-08-27 cohort (real-time gap authoritative; n=19)")]
    post[opt] = s["sum"] - post_today["sum"]
pre_today = SUMS[("today", "\nPRE-08-27 cohort (n=32)")]
pre = {opt: SUMS[(opt, "\nPRE-08-27 cohort (n=32)")]["sum"] - pre_today["sum"] for opt in ("a", "b", "c", "c'")}
print("cohort direction (sum R vs today's, same cohort): post-08-27 " + " ".join(f"{o}={v:+.2f}" for o, v in post.items()) +
      " | pre-08-27 " + " ".join(f"{o}={v:+.2f}" for o, v in pre.items()))
disagree = []
for opt in list(passed):
    if pre[opt] * post[opt] < 0:
        disagree.append(f"{opt}: pre {pre[opt]:+.2f} vs post {post[opt]:+.2f} → the post cohort decides → {'dropped from the rec' if post[opt] < 0 else 'kept'}")
        if post[opt] < 0:
            passed.remove(opt)
if disagree:
    print("cohort DISAGREEMENT: " + "; ".join(disagree))
if passed:
    passed.sort(key=lambda o: order[o])
    rec = f"REC: {passed[0]}" + (f" (also cleared: {', '.join(passed[1:])}; the one changing the fewest of today's trades wins)" if len(passed) > 1 else "")
else:
    rec = "REC: keep today's rule — no option clears all five; the REGN shape is filed as a watch item"
print(rec)

# ── POST-HOC (added after the OUTCOMES marker, advisor review 10-31): how close today's entries sit to
# (b)'s admission line, and what (b)'s verdict would be if its nearest dropped name were admitted. A
# sensitivity statement for the operator, NOT a rule change — the §6 verdict above stands as computed.
print("\n=== POST-HOC — (b)'s admission margin on today's entries (09:30 open vs floor price) ===")
b_rows = [r for r in rows if r["opt"]["today"]["fill"] is not None]
for r in sorted(b_rows, key=lambda r: (r["orb_o"] - r["floor_price"]) / r["floor_price"]):
    marg = (r["orb_o"] - r["floor_price"]) / r["floor_price"] * 100
    print(f"  {r['t']:5s} {r['d']} open {r['orb_o']:.2f} vs floor {r['floor_price']:.2f} → {marg:+.2f}% {'ADMITTED' if r['open_ge_floor'] else 'dropped'}"
          f"{'' if r['day0_open'] is None else f' (official daily open {r['day0_open']:.2f})'}")
b_all = SUMS[("b", "ALL 51")]
nearest = min((r for r in b_rows if not r["open_ge_floor"]), key=lambda r: abs(r["orb_o"] - r["floor_price"]) / r["floor_price"])
e_n = nearest["opt"]["today"]
r_n = R(e_n, e_n["w20"])
bar4 = base["sum"] + 2.0
print(f"  if {nearest['t']} ({(nearest['orb_o']-nearest['floor_price'])/nearest['floor_price']*100:+.2f}%) were admitted: (b) enters {b_all['enter']+1}, "
      f"sum R {b_all['sum']+r_n:+.2f} vs the rule-4 bar {bar4:+.2f} → rule 4 {'ok' if b_all['sum']+r_n >= bar4 else 'FAIL'}; "
      f"dropped sum {sum(R(r['opt']['today'], r['opt']['today']['w20']) for r in b_rows if not r['open_ge_floor'] and r is not nearest):+.2f} (n={sum(1 for r in b_rows if not r['open_ge_floor'])-1})")
affected = [r["t"] + " " + str(r["d"]) for r in rows if not r["orb_ge_floor"] and r["in_window"]]
print(f"REGN-shape rows (ORB high below the floor price AND inside the window): {len(affected)} — {', '.join(affected)}")

# ── per-row TSV ────────────────────────────────────────────────────────────────────────────────
with open(ROWS_TSV, "w") as fh:
    cols = ["d", "t", "era", "floor_pct", "prev_close", "floor_price", "orb_o", "orb_h", "orb_l", "open_ge_floor", "orb_ge_floor",
            "cross_bar", "submit_src", "submit_sec", "submit_min", "in_window", "fate", "atr", "adr20"]
    for o in OPTIONS:
        cols += [f"{o}_path", f"{o}_fill", f"{o}_minute", f"{o}_stop", f"{o}_borderline", f"{o}_s20", f"{o}_R20", f"{o}_mark20", f"{o}_final20", f"{o}_s40", f"{o}_R40", f"{o}_fh_first", f"{o}_fh_best"]
    fh.write("\t".join(cols) + "\n")
    for r in rows:
        v = [str(r["d"]), r["t"], r["era"], r["floor_pct"], r2(r["prev_close"], 4), r2(r["floor_price"], 4), r["orb_o"], r["orb_h"], r["orb_l"],
             int(r["open_ge_floor"]), int(r["orb_ge_floor"]), r["cross_bar"]["hhmm"] if r["cross_bar"] else "never", r["submit_src"],
             tstr(r["submit_sec"]), tstr(r["submit_min"]), int(r["in_window"]), r["fate"], r2(r["atr"], 4), r2(r["adr20"], 5)]
        for o in OPTIONS:
            e = r["opt"][o]
            if e["fill"] is None:
                v += [e["path"], "", "", "", int(bool(e.get("borderline"))), "", "", "", "", "", "", "", ""]
            else:
                w, w4 = e["w20"], e["w40"]
                v += [e["path"], e["fill"], e["minute"].strftime("%H:%M"), r2(e["stop"], 4), int(bool(e.get("borderline"))), w["status"], r2(R(e, w), 4),
                      r2(MARK(e, w), 4), w["final"], w4["status"], r2(R(e, w4), 4), e["fh"]["first"], r2(e["fh"]["best_r_budget"], 3)]
        fh.write("\t".join(str(x) for x in v) + "\n")
print(f"\nrows written: {ROWS_TSV}")
