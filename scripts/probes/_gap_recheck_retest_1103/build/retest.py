"""STUDY 1 — the 09:31 gap re-check, retested on the live cohort since 2026-08-28 (his "Yes", 2026-11-03).

Research only, $0, OFFLINE: reads ONE captured file (../capture/c1_c2.out) — no DB, no network, no re-pull.
Changes nothing (THE LINE: entry/exit rules are the operator's; this is evidence only).

Question: the live MAGNA53 path skips an entry when, at the 09:31 decision, the live price is under
prev close x 1.09 ('setup:gap_below_floor'). On the HIGH ticker-days since 08-28 that this check refused,
what would today's entry mechanics + the current depth exit have done had the check been absent?

Method fixed BEFORE any outcome bar is read; everything printed above '=== OUTCOMES BELOW ===' is
decided without a bar after an entry minute of a population name.

REUSE (never copied): the 10-31 study's own function bodies are loaded from
scripts/probes/_715_study_1031/s2_replay.py by AST (its module cannot be imported — its top level
asserts on its own capture), and its sha256 is printed. Loaded: the parser helpers, the ATR14 replica,
pre_rows, bar_at / bar_before, limit_walk (the #500 limit fallback), replay_entry (today's entry
mechanics) and fixed_horizon (the harness-independent +3R-first check), plus its constants.
Library: walk_arm (the #482 recorder's walker, depth_exit=True), entry_walk (the stop-limit walk),
adr20_pct_from_bars (the live 16:45 job's ADR20).

"Minus the re-check": replay_entry reads row['floor_price'] in exactly one place — the gap re-check
(asserted below from its source). The main arm calls it on a copy of the row whose floor_price is 0.0,
so the check can never fire; every other gate (zero range, stop too wide, the 2R stop, the chase cap,
the limit-vs-stop-limit branch, the 10:00 cancel) runs untouched.

ONE deliberate departure from s2_replay's walk(): the depth exit is walked with the 10-28 trail-arming
fix (live since 2026-10-29; commit 769f3dae taught walk_arm it) applied on EVERY session — today's exit
rule throughout, exactly as s2 applied the depth exit to sessions before it went live. s2's exact call
(no trail arming) is printed beside it as a sensitivity.

Run history (stated for honesty): the method half was debugged with STOP_AT_MARKER=1 (exits at the marker)
before the first full run. Added after reading output: the CLS mechanism line under C8 (pre-marker, a
non-population calibration name) and the POST-HOC BRACKET for the one abstaining walk (MANE) + its
addendum to the verdict (after the marker; the pre-registered rule had left an abstain unscored).

Run from the repo root:
  python3 scripts/probes/_gap_recheck_retest_1103/build/retest.py > scripts/probes/_gap_recheck_retest_1103/build/retest.txt
"""
from __future__ import annotations

import ast
import hashlib
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
REPO = HERE.parents[3]
sys.path.insert(0, str(REPO))

from agents.market_intelligence.broker.exit_logic import TRAIL_ARM_LIVE_FROM, adr20_pct_from_bars  # noqa: E402
from agents.market_intelligence.broker.hour_bar_walk import entry_walk, stop_limit_buy_price  # noqa: E402,F401
from agents.market_intelligence.live_fill_counterfactuals import walk_arm  # noqa: E402

_ET = ZoneInfo("America/New_York")
CAP = HERE.parent / "capture" / "c1_c2.out"
S2 = REPO / "scripts" / "probes" / "_715_study_1031" / "s2_replay.py"

# ── reuse s2_replay's function bodies + constants by AST (no copy drift) ───────────────────────
REUSED_FUNCS = ["read_sections", "f", "d_", "t_", "hhmm_dt", "minute_after", "tstr", "r2", "atr14_like_live",
                "pre_rows", "bar_at", "bar_before", "limit_walk", "replay_entry", "fixed_horizon"]
REUSED_CONSTS = ["CHASE_CAP", "LIMIT_MULT", "TARGET_R", "BREAKEVEN_R", "ATR_MULT", "ATR_LOOKBACK_CAL", "ATR_MIN_ROWS",
                 "PRIOR_CLOSES_CAL", "ADR_LOOKBACK_CAL", "WINDOW_END", "CANCEL_AT", "H_DECISION", "H_RUNNER",
                 "BORDERLINE_BAND"]
_src = S2.read_text(encoding="utf-8")
_sha = hashlib.sha256(_src.encode("utf-8")).hexdigest()
_tree = ast.parse(_src)
_loaded: list[str] = []
_replay_entry_src = None
for _node in _tree.body:
    name = None
    if isinstance(_node, ast.FunctionDef) and _node.name in REUSED_FUNCS:
        name = _node.name
        if name == "replay_entry":
            _replay_entry_src = ast.get_source_segment(_src, _node)
    elif (isinstance(_node, ast.Assign) and len(_node.targets) == 1 and isinstance(_node.targets[0], ast.Name)
          and _node.targets[0].id in REUSED_CONSTS):
        name = _node.targets[0].id
    if name:
        exec(compile(ast.Module(body=[_node], type_ignores=[]), str(S2), "exec"), globals())
        _loaded.append(name)
assert sorted(_loaded) == sorted(REUSED_FUNCS + REUSED_CONSTS), f"reuse incomplete: {sorted(set(REUSED_FUNCS + REUSED_CONSTS) - set(_loaded))}"
assert _replay_entry_src is not None and _replay_entry_src.count('row["floor_price"]') == 1, \
    "replay_entry must read floor_price in exactly one place (the gap re-check) for the floor=0 bypass to be exact"

FLOOR_PCT = 9.0                     # ep_detector.MIN_GAP_PCT since 2026-08-19 (every row here is >= 08-28)
SKIP_PREFIX = "setup:gap_below_floor"
LAST_RE = re.compile(r"last \$([\d.]+)")
PC_RE = re.compile(r"prev close \$([\d.]+)")
RT_RE = re.compile(r"rt ([\d.]+)%")

print("=== STUDY 1 — the 09:31 gap re-check retested on the live cohort since 2026-08-28 — method fixed before the "
      "OUTCOMES marker ===")
print(f"reused from {S2.relative_to(REPO)} (sha256 {_sha[:16]}…): {', '.join(REUSED_FUNCS)} + constants "
      f"{', '.join(f'{c}={globals()[c]}' for c in REUSED_CONSTS)}")
print("replay_entry reads row['floor_price'] once (the gap re-check, asserted) → the main arm passes floor_price=0.0")
print(f"TRAIL_ARM_LIVE_FROM (exit_logic) = {TRAIL_ARM_LIVE_FROM}")

# ── load ────────────────────────────────────────────────────────────────────────────────────────
sec, skipped = read_sections(CAP)  # noqa: F821 (loaded by AST)
print(f"capture sections: {', '.join(f'{k}={len(v)}' for k, v in sec.items())}; field-count mismatches skipped: {skipped or 'none'}")
POP = sec["POP"]
counts = sec["COUNTS"][0]
assert int(counts["pop_ticker_days"]) == 39 and len(POP) == 39, "population is not 39 ticker-days"
assert len({(p["ticker"], p["d"]) for p in POP}) == 39, "a ticker-day carries two trade rows"
assert int(counts["min_rows"]) == len(sec["MIN"]), "MIN truncated in transfer"

MIN: dict[tuple[date, str], list[dict]] = defaultdict(list)
for r in sec["MIN"]:
    d = d_(r["d"])  # noqa: F821
    MIN[(d, r["ticker"])].append({"m": hhmm_dt(d, r["hhmm"]), "hhmm": r["hhmm"], "o": f(r["open"]), "h": f(r["high"]),  # noqa: F821
                                  "l": f(r["low"]), "c": f(r["close"]), "v": f(r["volume"])})
for k in MIN:
    MIN[k].sort(key=lambda b: b["m"])
DAILY: dict[str, list[dict]] = defaultdict(list)
for r in sec["DAILY"]:
    DAILY[r["ticker"]].append({"trade_date": d_(r["trade_date"]), "o": f(r["open_price"]), "h": f(r["high_price"]),
                               "l": f(r["low_price"]), "c": f(r["close"]), "v": f(r["volume"])})
for k in DAILY:
    DAILY[k].sort(key=lambda b: b["trade_date"])
SESSIONS = sorted({b["trade_date"] for v in DAILY.values() for b in v})
LAST_SETTLED = SESSIONS[-1]
print(f"MIN rows {len(sec['MIN'])} (= COUNTS) over {len(MIN)} ticker-days; DAILY {len(sec['DAILY'])} rows, "
      f"{len(SESSIONS)} sessions {SESSIONS[0]}..{LAST_SETTLED} (session calendar = union of DAILY dates; "
      "06-15..11-02 has 98 NYSE sessions → complete)")
assert len(SESSIONS) == 98
print(f"last settled session = {LAST_SETTLED}; the 11-03 minute bars stop where the capture ran (~11:03 ET)")


def classify(status: str, sr: str) -> str:
    if status in ("filled", "closed", "partial"):
        return "filled"
    for pre, lab in (("setup:chase_cap", "chase_cap_skip"), ("window:", "out_of_window"), (SKIP_PREFIX, "gap_below_floor"),
                     ("setup:stop_too_wide", "stop_too_wide"), ("setup:size_too_small", "size_too_small"),
                     ("setup:", "other_setup_skip"), ("block:", "blocked"), ("infra:", "infra"), ("broker:", "broker_rejected")):
        if sr.startswith(pre):
            return lab
    if status == "cancelled":
        return "unfilled_cancel"
    return "other"


def prev_session_close(t: str, d: date) -> Optional[float]:
    rows = [b for b in DAILY[t] if b["trade_date"] < d and b["c"] is not None]
    return rows[-1]["c"] if rows else None


rows: list[dict] = []
for p in POP:
    d, t = d_(p["d"]), p["ticker"]
    row: dict = {"d": d, "t": t, "key": (d, t), "p": p}
    row["flip_up"] = int(p["flip_up_rows"] or 0) > 0
    row["status"], row["skip_reason"] = p["status"], p["skip_reason"]
    row["fate"] = classify(p["status"], p["skip_reason"])
    row["floor_pct"] = FLOOR_PCT
    row["prev_close"] = f(p["scan_prev_close"])
    row["prev_close_daily"] = prev_session_close(t, d)
    row["floor_price"] = row["prev_close"] * (1 + FLOOR_PCT / 100.0)
    m = LAST_RE.search(p["skip_reason"])
    row["stored_last"] = float(m.group(1)) if m else None
    m = PC_RE.search(p["skip_reason"])
    row["text_pc"] = float(m.group(1)) if m else None
    m = RT_RE.search(p["skip_reason"])
    row["text_rt"] = float(m.group(1)) if m else None
    bars = MIN[(d, t)]
    row["bars"] = bars
    row["has_0930"] = bool(bars) and bars[0]["hhmm"] == "09:30"
    row["n_0930_1000"] = sum(1 for b in bars if time(9, 30) <= b["m"].time() < time(10, 0))
    if row["has_0930"]:
        b0 = bars[0]
        row["orb_o"], row["orb_h"], row["orb_l"], row["orb_c"] = b0["o"], b0["h"], b0["l"], b0["c"]
    else:
        row["orb_o"] = row["orb_h"] = row["orb_l"] = row["orb_c"] = None
    # alert / submit timing: no EVENTS in this capture → from the first alert minute (HH:MM).
    # Pre-open HIGH → the ORB trigger at 09:31 off the 09:30 bar → submit second 09:31:00 → submit minute 09:32
    # (= s2's 'orb_bar_fetched 09:31 → 09:32' on the 5 names the two captures share); alert minute 09:30.
    det = t_(p["first_alert_et"])  # noqa: F821
    row["detected_t"] = det
    if det is None or det < time(9, 30):
        row["submit_sec"] = time(9, 31)
        row["alert_minute"] = time(9, 30)
    else:
        row["submit_sec"] = det
        row["alert_minute"] = det
    row["submit_min"] = max(time(9, 31), minute_after(row["submit_sec"]))  # noqa: F821
    row["in_window"] = row["submit_sec"].hour == 9 and row["submit_sec"].minute < 45
    atr, n_atr = atr14_like_live(t, d)  # noqa: F821
    row["atr"], row["atr_n"] = atr, n_atr
    pre60 = pre_rows(t, d, ADR_LOOKBACK_CAL)  # noqa: F821
    row["adr20"] = adr20_pct_from_bars([{"h": b["h"], "l": b["l"], "c": b["c"]} for b in pre60])
    row["prior_closes"] = [b["c"] for b in pre_rows(t, d, PRIOR_CLOSES_CAL) if b["c"] is not None]  # noqa: F821
    by = {b["trade_date"]: b for b in DAILY[t]}
    row["entry_day_close"] = by[d]["c"] if d in by else None
    sess = []
    for s in [s for s in SESSIONS if s > d][:H_RUNNER]:  # noqa: F821
        b = by.get(s)
        bar = {"o": b["o"], "h": b["h"], "l": b["l"], "c": b["c"]} if (b is not None and None not in (b["o"], b["h"], b["l"], b["c"])) else None
        sess.append((s, bar))
    row["sessions"] = sess
    row["n_fwd"] = min(len(sess), H_DECISION)  # noqa: F821
    if row["has_0930"]:
        fpx = row["floor_price"]
        row["open_ge_floor"] = row["orb_o"] >= fpx
        row["orb_ge_floor"] = row["orb_h"] >= fpx
        row["cross_bar"] = next((b for b in bars if b["h"] >= fpx), None)
    else:
        row["open_ge_floor"] = row["orb_ge_floor"] = None
        row["cross_bar"] = None
    rows.append(row)

POPN = [r for r in rows if r["skip_reason"].startswith(SKIP_PREFIX)]
POPN.sort(key=lambda r: (r["d"], r["t"]))

# ── §1 composition ──────────────────────────────────────────────────────────────────────────────
print("\n=== §1 COMPOSITION (no outcome) ===")
fc = defaultdict(int)
for r in rows:
    fc[r["fate"]] += 1
print("the 39 HIGH ticker-days since 08-28, stored fate: " + " ".join(f"{k}={v}" for k, v in sorted(fc.items())))
print(f"POPULATION = stored skip_reason starts '{SKIP_PREFIX}': n={len(POPN)} — " + ", ".join(f"{r['t']} {r['d']}" for r in POPN))
print(f"  flip-up admits (an ep_rt_floor_flip_up row that day): {sum(r['flip_up'] for r in POPN)} — "
      + ", ".join(r["t"] for r in POPN if r["flip_up"]) + f"; not flip-ups (delayed read crossed, faded by 09:31): "
      + (", ".join(r["t"] for r in POPN if not r["flip_up"]) or "none"))
print(f"  overlap with the 10-31 study's 51: " + ", ".join(r["t"] for r in POPN if r["flip_up"] and r["d"] <= date(2026, 10, 30)))
print(f"  every population alert is pre-open (first alert before 09:30): {all(r['detected_t'] < time(9, 30) for r in POPN)} → submit 09:31, walk from 09:32, alert-minute 09:30")
print("\nper name: ticker date | flip-up | prev close (scan / skip text / prior DAILY close) | floor px | 09:30 bar O/H/L/C | "
      "open>=floor | ORB high>=floor | stored live read at 09:31 (rt% text vs recomputed) | first RTH bar whose high reached the floor | "
      "ATR14 (n rows) | ORB range vs 1.5xATR | bars 09:30-10:00 | forward sessions to 11-02 (cap 20)")
for r in POPN:
    rt = (r["stored_last"] - r["prev_close"]) / r["prev_close"] * 100 if r["stored_last"] else None
    cb = r["cross_bar"]
    orb = (f"{r['orb_o']:.2f}/{r['orb_h']:.2f}/{r['orb_l']:.2f}/{r['orb_c']:.2f}" if r["has_0930"] else "no 09:30 bar")
    rng = (r["orb_h"] - r["orb_l"]) if r["has_0930"] else None
    print(f"  {r['t']:5s} {r['d']} | {'yes' if r['flip_up'] else 'no '} | {r['prev_close']:.2f} / {r2(r['text_pc'])} / {r2(r['prev_close_daily'])} | "  # noqa: F821
          f"{r['floor_price']:.2f} | {orb} | {int(bool(r['open_ge_floor']))} | {int(bool(r['orb_ge_floor']))} | "
          f"${r2(r['stored_last'])} (text {r2(r['text_rt'],1)}% / calc {r2(rt,2)}%) | {cb['hhmm'] if cb else 'never in RTH'} | "  # noqa: F821
          f"{r2(r['atr'],3)} ({r['atr_n']}) | {r2(rng)} vs {r2(ATR_MULT*r['atr'] if r['atr'] else None)} | {r['n_0930_1000']}/30 | {r['n_fwd']}")  # noqa: F821
print("  4a context (option (b) of the 10-31 study, built 10-31 and running in SHADOW — not acting): the flip-up names whose 09:30 OPEN was "
      "below the floor would ALSO be refused by 4a if it were switched on: "
      + ", ".join(r["t"] for r in POPN if r["flip_up"] and r["has_0930"] and not r["open_ge_floor"]))
unwalk = [r for r in POPN if r["n_0930_1000"] < 5]
print(f"  NOT EVALUABLE (minute bars stop at 09:30 — the capture stored one bar for the day): " +
      (", ".join(f"{r['t']} {r['d']} ({len(r['bars'])} bar)" for r in unwalk) or "none") +
      " → entered = unknown; kept in the count, out of every sum")
print("  orientation disclosure: the POP section prints the ENTERED names' stored exits (exits_json); they were seen while "
      "orienting. Nothing in the capture discloses the population's counterfactual, which the marker protects.")

# ── §2 calibration (all before the marker) ──────────────────────────────────────────────────────
print("\n=== §2 CALIBRATION (decided before any population outcome) ===")
cal_fail = []
# C1 prev close
bad = [r for r in POPN if (r["text_pc"] is not None and abs(r["text_pc"] - r["prev_close"]) > 0.005)
       or (r["prev_close_daily"] is not None and abs(r["prev_close_daily"] - r["prev_close"]) / r["prev_close"] > 0.005)]
print(f"C1 prev close: scan-log = skip text = prior DAILY close on {len(POPN) - len(bad)} of {len(POPN)}"
      + ("" if not bad else " — differ: " + ", ".join(f"{r['t']} scan {r['prev_close']} text {r['text_pc']} daily {r['prev_close_daily']}" for r in bad)))
if bad:
    cal_fail.append("C1")
# C2 rt%
bad = [r for r in POPN if r["stored_last"] is None or abs(round((r["stored_last"] - r["prev_close"]) / r["prev_close"] * 100, 1) - r["text_rt"]) > 0.051]
print(f"C2 the skip text's 'rt X%' = (live read − prev close)/prev close on {len(POPN) - len(bad)} of {len(POPN)}"
      + ("" if not bad else " — off: " + ", ".join(r["t"] for r in bad)))
if bad:
    cal_fail.append("C2")


def nore(row: dict) -> dict:
    """The row with the gap re-check disabled (replay_entry's only floor_price read)."""
    return {**row, "floor_price": 0.0}


# C3 today's rule WITH the re-check reproduces the skip
c3 = []
for r in POPN:
    if not r["has_0930"]:
        continue
    a = replay_entry(r, anchor_h=r["orb_h"], anchor_l=r["orb_l"], submit_min=r["submit_min"], in_window=r["in_window"], proxy=r["stored_last"])  # noqa: F821
    b = replay_entry(r, anchor_h=r["orb_h"], anchor_l=r["orb_l"], submit_min=r["submit_min"], in_window=r["in_window"], proxy=r["orb_c"])  # noqa: F821
    c3.append((r, a["path"], b["path"]))
ok3 = sum(1 for _, a, _ in c3 if a == "gap_below_floor")
okp = sum(1 for _, _, b in c3 if b == "gap_below_floor")
print(f"C3 today's rule WITH the re-check refuses the name: on the stored live read {ok3} of {len(c3)}; on the 09:30-close proxy {okp} of {len(c3)}"
      + "".join(f"  [{r['t']}: proxy path {b}]" for r, _, b in c3 if b != "gap_below_floor"))
if ok3 != len(c3):
    cal_fail.append("C3")
# C4 proxy error (the stored live read vs the 09:30 close)
errs = [(r, abs(r["orb_c"] - r["stored_last"]) / r["stored_last"] * 100) for r in POPN if r["has_0930"] and r["stored_last"]]
print("C4 live read at 09:31 vs the 09:30-bar close (the 10-31 study's calibrated proxy): " +
      ", ".join(f"{r['t']} {e:.2f}%" for r, e in errs) + f" | median {statistics.median([e for _, e in errs]):.3f}%")
print("   PRIMARY proxy = the stored live read (it IS the 09:31 price the live decision used); SENSITIVITY = the 09:30 close")
# C5 the stored 09:30 bar vs the trade row's ORB levels (rows that reached the ORB fetch)
c5 = [(r, f(r["p"]["orb_high"]), f(r["p"]["orb_low"])) for r in rows if r["has_0930"] and f(r["p"]["orb_high"]) is not None]  # noqa: F821
c5bad = [(r, h, l) for r, h, l in c5 if abs(h - r["orb_h"]) > 0.0051 or abs(l - r["orb_l"]) > 0.0051]
print(f"C5 stored 09:30 bar = the trade row's orb_high/orb_low on {len(c5) - len(c5bad)} of {len(c5)} trade rows carrying them"
      + ("" if not c5bad else " — differ: " + ", ".join(f"{r['t']} {r['d']} bar {r['orb_h']}/{r['orb_l']} row {h}/{l}" for r, h, l in c5bad)))
# C6 ATR replica vs the ROIV stop_too_wide text
roiv = next(r for r in rows if r["t"] == "ROIV")
roiv_rep = replay_entry(roiv, anchor_h=roiv["orb_h"], anchor_l=roiv["orb_l"], submit_min=roiv["submit_min"], in_window=roiv["in_window"], proxy=roiv["orb_c"])  # noqa: F821
c6 = abs(round(ATR_MULT * roiv["atr"], 2) - 1.82) < 0.006 and abs(round(roiv["orb_h"] - roiv["orb_l"], 2) - 1.90) < 0.006  # noqa: F821
print(f"C6 ATR14 replica: ROIV 09-08 text 'ORB range $1.90 > 1.5x ATR $1.82' → replica range {roiv['orb_h']-roiv['orb_l']:.2f}, "
      f"1.5xATR {ATR_MULT*roiv['atr']:.2f}; replay path {roiv_rep['path']} → {'PASS' if c6 and roiv_rep['path']=='stop_too_wide' else 'FAIL'}")  # noqa: F821
if not (c6 and roiv_rep["path"] == "stop_too_wide"):
    cal_fail.append("C6")
gn = next(r for r in rows if r["t"] == "GNRC")
print(f"   GNRC 09-17 'size_too_small: $12 risk / $17.77 per-share' → 2R planned risk from the bar = {gn['orb_h'] - (2*gn['orb_l']-gn['orb_h']):.2f}/sh "
      "(sizing reads the planned 2R risk; the day's risk budget was $12) — the size gate is NOT modelled (no budget in the capture); per-share risk is shown per name")

# C7 today's rule (WITH re-check, alert-minute-close proxy) vs the stored fate on the other 30
FATE_TO_PATH = {"filled": {"stop_limit", "limit"}, "chase_cap_skip": {"chase_cap_skip"}, "out_of_window": {"out_of_window"},
                "gap_below_floor": {"gap_below_floor"}, "stop_too_wide": {"stop_too_wide"},
                "unfilled_cancel": {"stoplimit_no_entry", "limit_no_entry"}}
print("C7 today's rule (WITH the re-check, 09:30/alert-minute close proxy) vs the stored fate, the 30 non-population rows:")
m7 = mm7 = ns7 = 0
for r in sorted(rows, key=lambda x: (x["d"], x["t"])):
    if r in POPN:
        continue
    if not r["has_0930"]:
        r["today"] = {"path": "no_bars", "fill": None}
        ns7 += 1
        print(f"  {r['t']:5s} {r['d']} | {r['fate']} | no minute bars stored → not replayed (listed)")
        continue
    a = bar_at(r["bars"], r["alert_minute"])  # noqa: F821
    proxy = a["c"] if a else None
    rep = replay_entry(r, anchor_h=r["orb_h"], anchor_l=r["orb_l"], submit_min=r["submit_min"], in_window=r["in_window"], proxy=proxy)  # noqa: F821
    r["today"] = rep
    if r["fate"] in FATE_TO_PATH:
        ok = rep["path"] in FATE_TO_PATH[r["fate"]]
        note = ""
        if r["fate"] == "filled" and ok:
            live_px = f(r["p"]["entry_price"])  # noqa: F821
            ok = abs(rep["fill"] - live_px) / live_px <= 0.005
            note = f"fill {rep['fill']:.2f} vs live {live_px:.4f} ({abs(rep['fill']-live_px)/live_px*100:.2f}%)"
        if ok:
            m7 += 1
        else:
            mm7 += 1
        print(f"  {r['t']:5s} {r['d']} | {r['fate']} | replay {rep['path']} ({rep['reason']}) {note} | {'match' if ok else 'MISMATCH'}")
    else:
        ns7 += 1
        print(f"  {r['t']:5s} {r['d']} | {r['fate']} ({r['skip_reason'][:45]}) | replay {rep['path']} | non-modelled live stop (listed)")
print(f"C7 tally: matched {m7}, mismatched {mm7}, non-modelled / no bars {ns7}  (information for the scale column; the population's verdict "
      "rests on C1-C3 + C6 + C8, which are pass/fail)")

# C8 the depth walk vs the live depth-era trades (entered names, not the population)


def walk(row: dict, e: dict, horizon: int, mode: str) -> dict:
    """s2_replay.walk's walk_arm call (lines 772-788), every kwarg identical; mode adds the trail arming:
    'today' = on every session (today's exit rule throughout — PRIMARY); 's2' = none (s2's exact call);
    'live' = from TRAIL_ARM_LIVE_FROM (what live ran, session by session — calibration only)."""
    bars = [{"m": b["m"], "o": b["o"], "h": b["h"], "l": b["l"], "c": b["c"]} for b in row["bars"]]
    fill_idx = next(i for i, b in enumerate(bars) if b["m"] == e["minute"])
    entry, stop = e["fill"], e["stop"]
    kw = {}
    if mode == "today":
        kw = {"trail_arm_from": row["d"], "entry_day_close": row["entry_day_close"]}
    elif mode == "live":
        kw = {"trail_arm_from": TRAIL_ARM_LIVE_FROM, "entry_day_close": row["entry_day_close"]}
    sess = row["sessions"][:horizon]
    res = walk_arm(entry=entry, stop=stop, target=entry + TARGET_R * (entry - e["anchor_l"]), day0_bars=bars, fill_idx=fill_idx,  # noqa: F821
                   sessions=sess, prior_closes=row["prior_closes"], harvest="live_ladder", fill_day=row["d"],
                   breakeven_at_partial=True, trail_prior_closes=True, ladder_partial=False, horizon=horizon,
                   breakeven_at_r=BREAKEVEN_R, r_frame_ps=entry - e["anchor_l"], trail_mode="sma", depth_exit=True,  # noqa: F821
                   depth_adr20_pct=row["adr20"], **kw)
    out = {"status": res["status"], "reason": res.get("reason"), "final": res.get("final_reason"), "exit_session": res.get("exit_session"),
           "gap_through": res.get("gap_through"), "sessions_walked": res.get("sessions_walked"), "exits": res.get("exits"),
           "pnl": None, "mark": None, "mark_at": None}
    if res["status"] == "settled":
        out["pnl"] = res["pnl_per_share"]
    elif res["status"] == "horizon":
        out["mark"] = res["mark_pnl_per_share"]
        out["mark_at"] = sess[-1][0]
    elif res["status"] == "pending" and res.get("exits") is not None and res.get("remaining") is not None:
        # walk_arm marks only AT the horizon; an open walk short of it is marked here the same way
        # (booked legs + the rest at the last walked close).
        n = res.get("sessions_walked") or 0
        last_c, at = (sess[n - 1][1]["c"], sess[n - 1][0]) if n > 0 else (bars[-1]["c"], f"{row['d']} {bars[-1]['m'].strftime('%H:%M')}")
        out["mark"] = sum(x["pnl"] for x in res["exits"]) + (last_c - entry) * res["remaining"]
        out["mark_at"] = at
    return out


def fill_minute_for(row: dict, px: float) -> Optional[datetime]:
    """The first bar from the submit minute whose range holds the stored fill price."""
    for b in row["bars"]:
        if b["m"].time() >= row["submit_min"] and b["l"] - 1e-9 <= px <= b["h"] + 1e-9:
            return b["m"]
    return None


print("C8 the depth walk vs the three depth-era live trades that settled or are deciding (stored fill, placed stop 2·ORB low − ORB high):")
C8_EXPECT = {"SMCI": "live: stop_hit day 0 (10-21 11:32 ET) at $35.272 vs stop $35.28",
             "CLS": "live: stop_hit at the 10-30 open, $265.635 (gap-through); the 10-28 depth sale the old code marked was cleared by hand",
             "IRON": "live: sma_trail_stop decided on the 11-02 close, sold 3 sh at the 11-03 open $79.41"}
c8 = {}
for tk in ("SMCI", "CLS", "IRON"):
    r = next(x for x in rows if x["t"] == tk)
    entry = f(r["p"]["entry_price"])  # noqa: F821
    e = {"fill": entry, "stop": 2 * r["orb_l"] - r["orb_h"], "anchor_l": r["orb_l"], "minute": fill_minute_for(r, entry)}
    res = {mode: walk(r, e, H_DECISION, mode) for mode in ("today", "live", "s2")}  # noqa: F821
    c8[tk] = res
    def _fmt(w):
        x = w["exits"][-1] if w["exits"] else None
        return (f"{w['status']} {w['final'] or w['reason']} s{w['exit_session'] if w['exit_session'] is not None else w['sessions_walked']}"
                + (f" last leg {x['price']:.3f} @ {x['time'][:16]}" if x else "") + (" GAP" if w["gap_through"] else ""))
    print(f"  {tk} {r['d']} fill {entry} @ {e['minute'].strftime('%H:%M') if e['minute'] else '?'} stop {e['stop']:.2f} | "
          f"today-rule: {_fmt(res['today'])} | as-live (arm from 10-29): {_fmt(res['live'])} | s2 exact: {_fmt(res['s2'])}")
    print(f"      {C8_EXPECT[tk]}")
smci_ok = c8["SMCI"]["today"]["status"] == "settled" and c8["SMCI"]["today"]["exit_session"] == 0 and c8["SMCI"]["today"]["final"] == "stop_hit"
cls_w = c8["CLS"]["today"]
cls_ok = cls_w["status"] == "settled" and cls_w["final"] == "stop_hit" and cls_w["exits"] and abs(cls_w["exits"][-1]["price"] - 265.635) / 265.635 <= 0.005
iron_w = c8["IRON"]["today"]
iron_ok = iron_w["status"] == "pending" and iron_w["reason"] == "depth_next_open_not_yet_settled"
print(f"C8 pre-set bars (today-rule walk): SMCI day-0 stop → {'PASS' if smci_ok else 'FAIL'}; CLS stop at the 10-30 open within 0.5% of $265.635 → "
      f"{'PASS' if cls_ok else 'FAIL'}; IRON depth sale decided on the last stored close, fill at the 11-03 open not stored → {'PASS' if iron_ok else 'FAIL'}")
if not (smci_ok and iron_ok):
    cal_fail.append("C8")
if not cls_ok:
    cls_r = next(x for x in rows if x["t"] == "CLS")
    o1030 = next(b["o"] for b in DAILY["CLS"] if b["trade_date"] == date(2026, 10, 30))
    print(f"   CLS price bar FAILS as pre-set; the MECHANISM matches (added after reading C8, non-population): the today-rule walk stops at the "
          f"10-30 open with a gap-through, at the stored daily open ${o1030:.2f} — live's market fill was $265.635 ({abs(o1030-265.635)/265.635*100:.2f}% apart). "
          "The two old-code walks (as-live / s2 exact) instead sell at the 10-29 open on the 10-28 depth sale he cleared by hand. "
          "Caveat carried: an at-the-open stop is booked at the daily open print, not the live fill")

if cal_fail:
    print(f"\nA PASS/FAIL CALIBRATION CHECK FAILED ({', '.join(cal_fail)}) — the outcome table is not read. Stopping.")
    sys.exit(2)
print("calibration: C1, C2, C3, C6, C8 (SMCI, IRON) pass")

# ── §3 the population's entries with the re-check absent (fills only) ──────────────────────────
print("\n=== §3 ENTRIES WITH THE RE-CHECK ABSENT (fills only; no bar after an entry minute read) ===")


def main_entry(r: dict, proxy: Optional[float]) -> dict:
    if not r["has_0930"]:
        return {"path": "no_bars", "reason": "no 09:30 bar", "fill": None, "minute": None, "stop": None}
    e = replay_entry(nore(r), anchor_h=r["orb_h"], anchor_l=r["orb_l"], submit_min=r["submit_min"], in_window=r["in_window"], proxy=proxy)  # noqa: F821
    e["anchor_h"], e["anchor_l"] = r["orb_h"], r["orb_l"]
    return e


def a_entry(r: dict, recheck: bool) -> dict:
    """The 10-31 study's (a) arm (s2_replay.option_entry lines 707-725, reimplemented because that body
    reads s2's USE_SENS / row['today']): anchor on the first RTH bar whose HIGH reached the floor price;
    submit the minute after it; proxy = the close of the bar before the submit minute (s2's calibrated
    proxy); window = crossing bar <= 09:43 and submit < 09:45. recheck=False = the study premise (PRIMARY
    sensitivity row); recheck=True = s2's exact (a), which re-runs the re-check at its own submit minute."""
    cb = r["cross_bar"]
    rr = r if recheck else nore(r)
    if not r["has_0930"]:
        return {"path": "no_bars", "reason": "no bars", "fill": None, "minute": None, "stop": None}
    if cb is None:
        return {"path": "a_no_crossing_bar", "reason": "no RTH bar reached the floor price", "fill": None, "minute": None, "stop": None}
    if cb["hhmm"] == "09:30":
        e = replay_entry(rr, anchor_h=r["orb_h"], anchor_l=r["orb_l"], submit_min=r["submit_min"], in_window=r["in_window"], proxy=r["stored_last"])  # noqa: F821
        e.update(anchor_h=r["orb_h"], anchor_l=r["orb_l"], note="crossing bar = 09:30 bar → identical to the main arm")
        return e
    submit_a = max(r["submit_min"], minute_after(cb["m"].time()))  # noqa: F821
    in_win = r["in_window"] and cb["m"].time() <= time(9, 43) and submit_a < WINDOW_END  # noqa: F821
    if not in_win:
        e = {"path": "out_of_window", "reason": f"crossing bar {cb['hhmm']} / submit {tstr(submit_a)} outside the window",  # noqa: F821
             "fill": None, "minute": None, "stop": None}
    else:
        prev = bar_before(r["bars"], submit_a)  # noqa: F821
        e = replay_entry(rr, anchor_h=cb["h"], anchor_l=cb["l"], submit_min=submit_a, in_window=True, proxy=(prev["c"] if prev else None))  # noqa: F821
    e.update(anchor_h=cb["h"], anchor_l=cb["l"], note=f"crossing bar {cb['hhmm']} h={cb['h']:.2f} l={cb['l']:.2f} submit {tstr(submit_a)}")  # noqa: F821
    return e


for r in POPN:
    r["arm"] = {"main": main_entry(r, r["stored_last"]),
                "proxy": main_entry(r, r["orb_c"]),
                "a": a_entry(r, recheck=False),
                "a_s2": a_entry(r, recheck=True)}
    for e in r["arm"].values():
        if e.get("fill") is not None:
            e["budget_den"] = e["anchor_h"] - e["stop"]
            e["own_den"] = e["fill"] - e["stop"]


def cell(e: dict) -> str:
    if e.get("fill") is not None:
        return f"{e['path']} {e['fill']:.2f}@{e['minute'].strftime('%H:%M')} stop {e['stop']:.2f} (risk {e['budget_den']:.2f}/sh)"
    return f"{e['path']} — {e.get('reason')}"


print("ticker date | MAIN (live read proxy) | sensitivity: 09:30-close proxy | (a) crossing-bar anchor, re-check absent | (a) as s2 (re-check at its own submit)")
for r in POPN:
    A = r["arm"]
    print(f"  {r['t']:5s} {r['d']} | {cell(A['main'])} | {cell(A['proxy'])} | {cell(A['a'])} | {cell(A['a_s2'])}")
    if A["main"].get("limit") is not None:
        print(f"        main: limit {A['main']['limit']:.2f} (live read {r['stored_last']:.2f} > ORB high {r['orb_h']:.2f}), cap ratio {A['main'].get('cap_ratio') and round(A['main']['cap_ratio'], 2)}x"
              + (" BORDERLINE" if A["main"].get("borderline") else ""))
    if A["a"].get("note"):
        print(f"        (a): {A['a']['note']}")
for k in ("main", "proxy", "a", "a_s2"):
    print(f"{k}: enters {sum(1 for r in POPN if r['arm'][k].get('fill') is not None)} of {len(POPN)}")
# cross-check: s2's exact (a) here vs the 10-31 run's own (a) on the shared names (s2_rows.tsv)
_s2rows = {}
with open(S2.parent / "s2_rows.tsv", encoding="utf-8") as _fh:
    _h = _fh.readline().rstrip("\n").split("\t")
    for _ln in _fh:
        _v = dict(zip(_h, _ln.rstrip("\n").split("\t")))
        _s2rows[(_v["t"], _v["d"])] = _v
_xc = []
for r in POPN:
    v = _s2rows.get((r["t"], str(r["d"])))
    if v is None:
        continue
    mine = r["arm"]["a_s2"]
    same = (v["a_fill"] == "" and mine.get("fill") is None) or (mine.get("fill") is not None and v["a_fill"] != "" and abs(float(v["a_fill"]) - mine["fill"]) < 0.006
                                                             and abs(float(v["a_stop"]) - mine["stop"]) < 0.006)
    _xc.append(f"{r['t']} 10-31 {v['a_path']} {v['a_fill'] or '-'} / here {mine['path']} {r2(mine.get('fill'))} → {'same' if same else 'DIFFERENT'}")  # noqa: F821
print("cross-check vs the 10-31 run's (a) on the shared names: " + "; ".join(_xc))
print("size gate (not modelled): per-share planned risk of every entry above — "
      + ", ".join(f"{r['t']} {r['arm']['main']['budget_den']:.2f}" for r in POPN if r['arm']['main'].get('fill') is not None)
      + " — each under the $12 budget GNRC shows on 09-17, the smallest budget visible in the capture → none would be size-refused at that budget")

import os
if os.environ.get("STOP_AT_MARKER"):
    print("[STOP_AT_MARKER set — pre-marker dry run]"); sys.exit(0)
print("\n=== OUTCOMES BELOW === (everything above was written without reading a population bar after an entry minute)")

# ── §4 outcomes ─────────────────────────────────────────────────────────────────────────────────
for r in POPN:
    for k, e in r["arm"].items():
        if e.get("fill") is None:
            continue
        e["w"] = walk(r, e, H_DECISION, "today")  # noqa: F821
        e["w_s2"] = walk(r, e, H_DECISION, "s2")  # noqa: F821
        e["w40"] = walk(r, e, H_RUNNER, "today")  # noqa: F821
        e["fh"] = fixed_horizon(r, e)  # noqa: F821


def rv(e: dict, w: dict) -> tuple[Optional[float], Optional[float]]:
    den = e["budget_den"]
    return ((w["pnl"] / den) if w["pnl"] is not None else None), ((w["mark"] / den) if w["mark"] is not None else None)


def outcome_str(e: dict, w: dict) -> str:
    x, mk = rv(e, w)
    if x is not None:
        return f"settled {x:+.2f}R ({w['final']} s{w['exit_session']}{' GAP' if w['gap_through'] else ''})"
    if mk is not None:
        why = {"horizon": "open at 20 sessions", "pending": f"still open ({w['reason']})"}.get(w["status"], w["status"])
        return f"{why}, marked {mk:+.2f}R at {w['mark_at']}"
    return f"{w['status']} ({w['reason']})"


print("\n=== §4 PER NAME — MAIN ARM (re-check absent; live read at 09:31; today's entry + depth exit with trail arming; 20 sessions; "
      "budget-R = profit per share ÷ (ORB high − placed stop)) ===")
print("ticker date | entered? why | 20-session result | s2-exact exit (no trail arming) | 40 sessions | fixed check: +3R before the stop? best high R")
for r in POPN:
    e = r["arm"]["main"]
    if e.get("fill") is None:
        why = e.get("reason")
        if r in unwalk:
            why = "UNKNOWN — only the 09:30 bar is stored for the day (and no forward session: alert day is today)"
        print(f"  {r['t']:5s} {r['d']} | not entered: {why}")
        continue
    print(f"  {r['t']:5s} {r['d']} | entered {e['reason']} stop {e['stop']:.2f} | {outcome_str(e, e['w'])} | {outcome_str(e, e['w_s2'])} | "
          f"{outcome_str(e, e['w40'])} | {e['fh']['first']} {e['fh']['best_r_budget']:+.2f} (n={e['fh']['n']} sessions)")


def summarise(arm: str, wkey: str = "w") -> dict:
    ents = [(r, r["arm"][arm]) for r in POPN if r["arm"][arm].get("fill") is not None]
    settled, marked, other = [], [], []
    for r, e in ents:
        x, mk = rv(e, e[wkey])
        if x is not None:
            settled.append((r["t"], x))
        elif mk is not None:
            marked.append((r["t"], mk, e[wkey]["mark_at"]))
        else:
            other.append((r["t"], e[wkey]["status"]))
    s = [x for _, x in settled]
    return {"arm": arm, "enter": len(ents), "settled": settled, "marked": marked, "other": other,
            "sum": sum(s), "wins": sum(1 for x in s if x > 0), "losses": sum(1 for x in s if x < 0), "flat": sum(1 for x in s if x == 0),
            "big": [(t, x) for t, x in settled if x >= 3.0], "worst": min(settled, key=lambda z: z[1]) if settled else None,
            "m_up": sum(1 for _, m, _ in marked if m > 0), "m_dn": sum(1 for _, m, _ in marked if m < 0),
            "m_big": [(t, m) for t, m, _ in marked if m >= 3.0], "m_sum": sum(m for _, m, _ in marked)}


def fmt_sum(s: dict, label: str) -> str:
    w = s["worst"]
    return (f"{label}: entered {s['enter']} of {len(POPN)} | settled {len(s['settled'])}: sum {s['sum']:+.2f}R, wins {s['wins']}, losses {s['losses']}, "
            f"flat {s['flat']}, big winners >=+3R {len(s['big'])} [{', '.join(f'{t} {x:+.2f}' for t, x in s['big']) or 'none'}], worst "
            f"{(f'{w[0]} {w[1]:+.2f}') if w else '-'} | still open, marked: {len(s['marked'])} "
            f"[{', '.join(f'{t} {m:+.2f} at {a}' for t, m, a in s['marked']) or 'none'}] (up {s['m_up']}, down {s['m_dn']}, marked >=+3R {len(s['m_big'])}, "
            f"marked sum {s['m_sum']:+.2f}) | other {s['other'] or 'none'}")


print("\n=== §5 SUMMARY (the 9 names the re-check refused) ===")
S = {}
for arm, lab in (("main", "MAIN — re-check absent, live read proxy"), ("proxy", "sensitivity — 09:30-close proxy"),
                 ("a", "sensitivity (a) — crossing-bar anchor, re-check absent"), ("a_s2", "s2's exact (a) — re-check at its own submit")):
    S[arm] = summarise(arm)
    print(fmt_sum(S[arm], lab))
S["main_s2"] = summarise("main", "w_s2")
print(fmt_sum(S["main_s2"], "MAIN with s2's exact exit (no trail arming)"))
for arm in ("main", "proxy", "a"):
    for r in POPN:
        e = r["arm"][arm]
        if e.get("fill") is not None and e["w"]["status"] not in ("settled", "horizon", "pending"):
            print(f"  note: {arm} {r['t']} walk {e['w']['status']} ({e['w']['reason']}) — not scored")

# ── §6 scale: the same-period ENTERED names ────────────────────────────────────────────────────
# ── POST-HOC (added AFTER the OUTCOMES marker; the pre-registered rule left an abstain unscored) ──────────
# A walk that abstains on 'fwd_stop_and_breakeven_same_day:<d>' cannot order one daily bar: it reached the
# +3 ORB-R breakeven trigger AND traded at/below entry while the stop still sat under entry. The two
# orderings bound the outcome: (worst) armed first, then the dip stops the trade AT ENTRY that day → the
# booked legs + 0 on the rest; (best) the dip came first (it must stay above the resting stop, checked),
# the rally armed breakeven, no second dip → walk_arm re-run with that one bar's low lifted to entry + 0.01
# (nothing else changes). A bracket, never a pick.
print("\n=== POST-HOC BRACKET for unresolved walks (added after the marker; stated for honesty) ===")
BRACKET = {}
for r in POPN:
    e = r["arm"]["main"]
    if e.get("fill") is None or e["w"]["status"] != "abstain" or not str(e["w"]["reason"]).startswith("fwd_stop_and_breakeven_same_day:"):
        continue
    dd = date.fromisoformat(e["w"]["reason"].split(":", 1)[1])
    entry = e["fill"]
    be_trig = entry + BREAKEVEN_R * (entry - e["anchor_l"])  # noqa: F821
    bar = next(b for s_, b in r["sessions"] if s_ == dd)
    resting_ok = bar["l"] > e["stop"]
    worst = 0.0
    lifted = [(s_, ({**b, "l": max(b["l"], entry + 0.01)} if s_ == dd else b)) for s_, b in r["sessions"]]
    rb = {**r, "sessions": lifted}
    wb = walk(rb, e, H_DECISION, "today")  # noqa: F821
    xb, mb = rv(e, wb)
    best = xb if xb is not None else mb
    BRACKET[r["t"]] = (worst, best, wb)
    print(f"  {r['t']} {r['d']} fill {entry:.2f} stop {e['stop']:.2f} breakeven trigger {be_trig:.2f} | {dd} bar o/h/l/c "
          f"{bar['o']}/{bar['h']}/{bar['l']}/{bar['c']} — low above the stop {e['stop']:.2f}: {resting_ok}")
    print(f"    worst ordering (armed, then stopped at entry on {dd}): {worst:+.2f}R | best ordering (dip first, then armed): "
          f"{outcome_str(e, wb)} | fixed check (harness-free): {e['fh']['first']} best high {e['fh']['best_r_budget']:+.2f}R")

print("\n=== §6 SCALE — the same-period ENTERED names (the 39's filled rows) ===")
print("STORED R = the live trade's realised P&L ÷ (shares × (ORB high − (2·ORB low − ORB high))) from exits_json — each trade's OWN era's live exit "
      "(the depth exit only from 10-13); REPLAYED R = the same harness as the main arm (today's rule WITH the re-check, the 09:30/alert-minute "
      "close proxy, today's depth exit with trail arming), shown only where the replay reproduces the live fill within 0.5%")
ent = sorted([r for r in rows if r["fate"] == "filled"], key=lambda x: (x["d"], x["t"]))
st_list, rp_list, rp_marks = [], [], []
for r in ent:
    p = r["p"]
    ex = json.loads(p["exits_json"] or "[]")
    sh = sum(x["shares"] for x in ex)
    den = 2 * (f(p["orb_high"]) - f(p["orb_low"]))  # noqa: F821
    stored = (sum(x["pnl"] for x in ex) / (sh * den)) if (p["status"] == "closed" and sh) else None
    if stored is not None:
        st_list.append((r["t"], stored))
    rep = r.get("today", {})
    rp = "-"
    if rep.get("fill") is not None:
        live_px = f(p["entry_price"])  # noqa: F821
        if abs(rep["fill"] - live_px) / live_px <= 0.005:
            rep["anchor_h"], rep["anchor_l"] = r["orb_h"], r["orb_l"]
            rep["budget_den"] = r["orb_h"] - rep["stop"]
            w = walk(r, rep, H_DECISION, "today")  # noqa: F821
            x, mk = rv(rep, w)
            rp = outcome_str(rep, w)
            if x is not None:
                rp_list.append((r["t"], x))
            elif mk is not None:
                rp_marks.append((r["t"], mk))
        else:
            rp = f"fill not reproduced ({rep['fill']:.2f} vs {live_px:.2f})"
    else:
        rp = f"replay {rep.get('path')} (not reproduced)"
    print(f"  {r['t']:5s} {r['d']} | stored {('%+.2fR' % stored) if stored is not None else 'OPEN (no stored exit)'} ({p['exit_rule'] or 'pre-depth'} exit, "
          f"{sh} sh) | replayed {rp}")
s_vals = [x for _, x in st_list]
r_vals = [x for _, x in rp_list]
print(f"STORED: {len(s_vals)} closed — sum {sum(s_vals):+.2f}R, wins {sum(1 for x in s_vals if x > 0)}, losses {sum(1 for x in s_vals if x < 0)}, "
      f"big >=+3R {sum(1 for x in s_vals if x >= 3)} [{', '.join(f'{t} {x:+.2f}' for t, x in st_list if x >= 3) or 'none'}], worst {'%s %+.2f' % min(st_list, key=lambda z: z[1])}")
print(f"REPLAYED: {len(r_vals)} settled — sum {sum(r_vals):+.2f}R, wins {sum(1 for x in r_vals if x > 0)}, losses {sum(1 for x in r_vals if x < 0)}, "
      f"big >=+3R {sum(1 for x in r_vals if x >= 3)} [{', '.join(f'{t} {x:+.2f}' for t, x in rp_list if x >= 3) or 'none'}]"
      + (f", worst {'%s %+.2f' % min(rp_list, key=lambda z: z[1])}" if rp_list else "") + "; marked open " + (', '.join(f'{t} {x:+.2f}' for t, x in rp_marks) or 'none'))

# ── §7 verdict (pre-set wording rule) ──────────────────────────────────────────────────────────
m = S["main"]
print("\n=== §7 VERDICT (rule fixed before the run: winners vs losers among the MAIN arm's SETTLED rows decide; marked-open rows are "
      "stated beside, not counted; n is stated) ===")
direction = ("MORE WINNERS than losers" if m["wins"] > m["losses"] else "MORE LOSERS than winners" if m["losses"] > m["wins"]
             else "as many winners as losers")
print(f"On this live cohort the re-check removed {m['enter']} entries (of {len(POPN)} refused names; {len(unwalk)} not evaluable): "
      f"settled {len(m['settled'])} → {m['wins']} winners / {m['losses']} losers / {m['flat']} flat, sum {m['sum']:+.2f}R, "
      f"{len(m['big'])} big winner(s) — i.e. it removed {direction} on the settled rows; "
      f"{len(m['marked'])} still open (marked {m['m_up']} up / {m['m_dn']} down, {m['m_sum']:+.2f}R). "
      f"n is tiny ({len(m['settled'])} settled) — a direction, not a finding. No rule recommendation (his call).")
if BRACKET:
    lo = m["sum"] + sum(v[0] for v in BRACKET.values())
    hi = m["sum"] + sum(v[1] for v in BRACKET.values())
    print("POST-HOC addendum (the bracket above): unresolved " + ", ".join(f"{t} {v[0]:+.2f}R to {v[1]:+.2f}R" for t, v in BRACKET.items())
          + f" → the removed entries sum {lo:+.2f}R to {hi:+.2f}R; winners {m['wins']} to {m['wins'] + sum(1 for v in BRACKET.values() if v[1] > 0)}, "
          f"losers {m['losses']}; big winners {len(m['big'])} to {len(m['big']) + sum(1 for v in BRACKET.values() if v[1] >= 3)}")
