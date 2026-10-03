"""#692 pin-check backtest ($0, offline) — which price measure, readable WHEN THE DETECTOR DECIDES,
carries his 2026-10-03 separation between "pinned to a buyout price" and "free to trade"?

Inputs (all exported before this script existed; nothing is fetched):
  replay_2026-10-02.jsonl      151 stock-days: the recorded deal answers (grader + headline), the
                               replay's decision under the 10-02 rule, the operator labels.
  pin/daily_bars.csv           daily OHLCV, each stock-day + the 70 calendar days before it.
  pin/minute_bars_to_1030.csv  minute bars 09:30-10:30 ET on each stock-day (EP days; some
                               flag / 9M days have none).

What it computes per stock-day — the CANDIDATE PIN MEASURES, grouped by when they can be read:
  EP path (decides pre-market, then every 5 min; the 9:31 ORB entry is the last useful tick):
    gap_open      (open - prior close) / prior close              readable pre-market (as a proxy)
    m1            09:30 one-minute bar (high - low) / open        readable from 09:31:00
    r0935         09:30-09:34 bars (max high - min low) / open    readable from 09:35 (after entry)
    r0945         09:30-09:44 bars                                 readable 09:45 = ORB cutoff
    day_range     own day (high - low) / close                     REFERENCE ONLY (never live)
  Evening / multi-day detectors (flag, anticipation; the low-cap lane after 09:45):
    day_range     own day (high - low) / close                     the scan date's bar is stored
    mature_pin    flag_detector._evaluate_deal_pin on the 10 sessions to the scan date
    fresh_pin     flag_detector._evaluate_fresh_pin (incl. sticky) on the 40 sessions

NOMINATION — the pin can only ACT on a name the news nominates. Derived from the recorded
answers exactly as the live rule orders them (grader first; a headline only when the grader found
no deal or did not answer — ruling 7): role 'target' with status 'signed' or 'proposed' and a
consideration that is not all-stock. A 'shell' (SUNE, CLRO) keeps blocking on the news alone —
a reverse-merger shell is not pinned, it is re-rated (his two TP rulings + the 10-03 approvals).

LABEL TIERS (stated, because the sample is small):
  tier 1  the 25 operator-labelled rows (07-04 / 07-12 / 08-08 / 10-01) + his five 10-03 calls
  tier 2  every other row of the 10-02 replay, which he approved AS DECIDED on 10-03 — a weaker
          tier: an approval of a list is not a label on each row.
A nominated row's truth is BLOCK (pinned) or PASS (free); a non-nominated row's truth never
involves the price, so it cannot score a measure — it is listed so the reader sees what the
measure WOULD say there.

Usage:  python scripts/probes/_692/pin_backtest.py            (prints the tables)
        python scripts/probes/_692/pin_backtest.py --json out  (also writes per-row measures)
ASCII-only output.
"""
from __future__ import annotations

import csv
import json
import sys
from collections import defaultdict
from datetime import date
from pathlib import Path
from typing import Optional

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[2]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

REPLAY = HERE / "replay_2026-10-02.jsonl"
DAILY = HERE / "pin" / "daily_bars.csv"
MINUTE = HERE / "pin" / "minute_bars_to_1030.csv"

# His 2026-10-03 sign-off (docs/analysis/mna_filter_operator_labels_2026-10-01.md, verbatim calls).
CALLS_2026_10_03 = {
    ("DSGN", "2026-05-18"): "PASS",   # "is not a buyout, release"
    ("THR", "2026-05-22"): "PASS",    # "is not a buyout, release"
    ("PD", "2026-05-29"): "PASS",     # "is not a buyout, release"
    ("HZO", "2026-08-10"): "BLOCK",   # "is a real buyout, keep blocked"
    ("RNW", "2026-08-11"): "BLOCK",   # "is a real buyout, keep blocked"
}

# The date split: discovery on the earlier half of the population, check on the later half.
SPLIT_DATE = date(2026, 7, 31)   # <= goes to DISCOVERY, > to CHECK


def _f(x) -> Optional[float]:
    try:
        return float(x)
    except (TypeError, ValueError):
        return None


def load_replay() -> list[dict]:
    rows = [json.loads(ln) for ln in REPLAY.read_text(encoding="utf-8").splitlines() if ln.strip()]
    return [r for r in rows if r.get("kind") == "ticker_day"]


def load_bars():
    daily: dict[tuple[str, str], list[dict]] = defaultdict(list)
    with DAILY.open(encoding="utf-8") as fh:
        for r in csv.DictReader(fh):
            daily[(r["t"], r["d"])].append(r)
    for k in daily:
        daily[k].sort(key=lambda r: r["trade_date"])
    minute: dict[tuple[str, str], list[dict]] = defaultdict(list)
    with MINUTE.open(encoding="utf-8") as fh:
        for r in csv.DictReader(fh):
            minute[(r["t"], r["d"])].append(r)
    for k in minute:
        minute[k].sort(key=lambda r: r["et"])
    return daily, minute


# ── nomination from the recorded answers (the live rule's order) ──────────────────────────────

def governing_answer(row: dict) -> tuple[Optional[tuple[str, str, str]], str]:
    """(role, status, consideration) that governs this row under ruling 7, and which path it
    came from: 'grader' / 'headline' / 'none'."""
    g = row.get("grader_parsed")
    if g and g[0] != "none":
        return tuple(g), "grader"
    for h in row.get("headline_asked") or []:
        p = h.get("parsed")
        if p and p[0] != "none":
            return tuple(p), "headline"
    return None, "none"


def nominated(ans: Optional[tuple[str, str, str]]) -> bool:
    if ans is None:
        return False
    role, status, cons = ans
    return role == "target" and status in ("signed", "proposed") and cons != "stock"


def shell_pin(ans: Optional[tuple[str, str, str]]) -> bool:
    return ans is not None and ans[0] == "shell" and ans[1] == "signed"


# ── the measures ──────────────────────────────────────────────────────────────────────────────

def measures(ticker: str, day: str, daily, minute) -> dict:
    out: dict = {"ticker": ticker, "date": day}
    ds = daily.get((ticker, day)) or []
    own = [r for r in ds if r["trade_date"] == day]
    prior = [r for r in ds if r["trade_date"] < day]
    pc = _f(prior[-1]["close"]) if prior else None
    if own:
        o = own[0]
        h, l, c, op = _f(o["high_price"]), _f(o["low_price"]), _f(o["close"]), _f(o["open_price"])
        if h and l and c:
            out["day_range"] = (h - l) / c * 100
        if pc and op:
            out["gap_open"] = (op - pc) / pc * 100
    ms = minute.get((ticker, day)) or []
    if ms:
        b0 = ms[0]
        out["first_bar_et"] = b0["et"][11:16]
        o0 = _f(b0["open"])
        if b0["et"][11:16] == "09:30" and o0:
            out["m1"] = (_f(b0["high"]) - _f(b0["low"])) / o0 * 100
            if pc:
                out["gap_0930"] = (o0 - pc) / pc * 100

            def rng(before: str) -> Optional[float]:
                w = [r for r in ms if r["et"][11:16] < before]
                if not w:
                    return None
                return (max(_f(r["high"]) for r in w) - min(_f(r["low"]) for r in w)) / o0 * 100
            out["r0935"] = rng("09:35")
            out["r0945"] = rng("09:45")
    # the evening detectors' existing verdicts, as of the scan date (newest first, 40 sessions)
    rows_desc = [r for r in reversed(ds) if r["trade_date"] <= day][:40]
    try:
        from agents.market_intelligence.flag_detector import (
            _evaluate_deal_pin, _evaluate_fresh_pin, _DEAL_PIN_LOOKBACK_DAYS)
        conv = [{"high_price": r["high_price"], "low_price": r["low_price"], "close": r["close"],
                 "volume": r["volume"]} for r in rows_desc]
        mp = _evaluate_deal_pin(conv[:_DEAL_PIN_LOOKBACK_DAYS]) or {}
        fp = _evaluate_fresh_pin(conv) or {}
        out["mature_pin"] = bool(mp.get("is_pin"))
        out["mature_median"] = mp.get("median_range_pct")
        out["fresh_pin"] = bool(fp.get("is_fresh_pin"))
        out["fresh_band"] = fp.get("band_pct")
    except Exception as e:  # the repo may be unimportable in a bare checkout — say so
        out["evaluators"] = f"unavailable: {e}"
    return out


# ── scoring ───────────────────────────────────────────────────────────────────────────────────

def truth_for(row: dict) -> tuple[Optional[str], int]:
    """(BLOCK|PASS, tier) — what he said the row should do; tier 1 = labelled, 2 = approved."""
    key = (row["ticker"], row["date"])
    if key in CALLS_2026_10_03:
        return CALLS_2026_10_03[key], 1
    lbl = row.get("label") or ""
    if lbl:
        return ("BLOCK" if ("TP" in lbl or "REAL buyout" in lbl) else "PASS"), 1
    nd = row.get("new_decision") or ""
    if nd.startswith("BLOCK"):
        return "BLOCK", 2
    if nd == "PASS":
        return "PASS", 2
    return None, 0


def separation(values: list[tuple[float, str]]) -> dict:
    """values: (measure, truth). The best single threshold (block when measure <= t), the margin
    between the highest BLOCK and the lowest PASS, and the rows inside +-25% of the midpoint."""
    blocks = sorted(v for v, t in values if t == "BLOCK")
    passes = sorted(v for v, t in values if t == "PASS")
    if not blocks or not passes:
        return {"n_block": len(blocks), "n_pass": len(passes), "clean": None}
    hi_block, lo_pass = blocks[-1], passes[0]
    clean = hi_block < lo_pass
    mid = (hi_block + lo_pass) / 2
    # best threshold by error count, ties -> the midpoint of the widest clean gap
    cands = sorted(set(blocks + passes))
    best = None
    for i in range(len(cands) + 1):
        t = (cands[i - 1] + cands[i]) / 2 if 0 < i < len(cands) else (cands[0] - 1e-9 if i == 0 else cands[-1] + 1e-9)
        err = sum(1 for v in blocks if v > t) + sum(1 for v in passes if v <= t)
        if best is None or err < best[1]:
            best = (t, err)
    near = [(v, t) for v, t in values if abs(v - mid) <= 0.25 * max(mid, 1e-9)]
    return {"n_block": len(blocks), "n_pass": len(passes), "clean": clean,
            "highest_block": hi_block, "lowest_pass": lo_pass, "margin_pp": lo_pass - hi_block,
            "midpoint": mid, "best_threshold": best[0], "best_errors": best[1],
            "near_midpoint": near}


def main(argv: list[str]) -> int:
    rows = load_replay()
    daily, minute = load_bars()
    table = []
    for r in rows:
        m = measures(r["ticker"], r["date"], daily, minute)
        ans, path = governing_answer(r)
        truth, tier = truth_for(r)
        m.update({"detectors": r.get("detectors") or [], "ep_day": bool(r.get("ep_day")),
                  "answer": ans, "answer_path": path, "nominated": nominated(ans),
                  "shell": shell_pin(ans), "truth": truth, "tier": tier,
                  "label": r.get("label"), "old_decision": r.get("old_decision"),
                  "replay_decision": r.get("new_decision"), "replay_why": r.get("new_why"),
                  "price_signature": (r.get("arm") == "price_signature")})
        table.append(m)

    def fmt(v, w=7):
        return f"{v:{w}.2f}" if isinstance(v, (int, float)) else f"{'-':>{w}}"

    print("=== NOMINATED rows (the pin decides here) — sorted by m1 then day_range ===")
    print(f"{'tkr':6}{'day':11}{'det':16}{'truth':6}{'tier':5}{'answer':24}{'gap':>7}{'m1':>7}"
          f"{'r0935':>7}{'r0945':>7}{'dayR':>8}{'mat':>5}{'frsh':>5}")
    nom = [m for m in table if m["nominated"]]
    nom.sort(key=lambda m: (m.get("m1") if m.get("m1") is not None else 1e9, m.get("day_range") or 0))
    for m in nom:
        a = "/".join(m["answer"]) + f"({m['answer_path'][0]})"
        print(f"{m['ticker']:6}{m['date']:11}{','.join(m['detectors'])[:15]:16}{m['truth'] or '-':6}"
              f"{m['tier']:<5}{a:24}{fmt(m.get('gap_open'))}{fmt(m.get('m1'))}{fmt(m.get('r0935'))}"
              f"{fmt(m.get('r0945'))}{fmt(m.get('day_range'), 8)}{'Y' if m.get('mature_pin') else '.':>5}"
              f"{'Y' if m.get('fresh_pin') else '.':>5}")

    print("\n=== SEPARATION on nominated rows, per measure (block when measure <= threshold) ===")
    for meas, readable in (("gap_open", "pre-market proxy"), ("m1", "09:31 (the ORB bar)"),
                           ("r0935", "09:35 (after the entry cron)"), ("r0945", "09:45 (ORB cutoff)"),
                           ("day_range", "REFERENCE ONLY - evening detectors can read it")):
        for tiers, name in (((1,), "tier 1 only"), ((1, 2), "tier 1 + 2")):
            vals = [(m[meas], m["truth"]) for m in nom
                    if m.get(meas) is not None and m["truth"] and m["tier"] in tiers]
            s = separation(vals)
            line = f"  {meas:10} [{readable}] {name:11} n_block={s['n_block']:2} n_pass={s['n_pass']:2}"
            if s.get("clean") is None:
                print(line + "  (one class empty)")
                continue
            line += (f"  clean={'YES' if s['clean'] else 'no '} highest_block={s['highest_block']:.2f} "
                     f"lowest_pass={s['lowest_pass']:.2f} margin={s['margin_pp']:+.2f}pp "
                     f"best_t={s['best_threshold']:.2f} errors={s['best_errors']} "
                     f"near_mid={len(s['near_midpoint'])}")
            print(line)

    print("\n=== DATE SPLIT on m1 (nominated, tier 1+2): discovery <= %s, check after ===" % SPLIT_DATE)
    disc = [(m["m1"], m["truth"]) for m in nom if m.get("m1") is not None and m["truth"]
            and date.fromisoformat(m["date"]) <= SPLIT_DATE]
    chk = [(m["m1"], m["truth"]) for m in nom if m.get("m1") is not None and m["truth"]
           and date.fromisoformat(m["date"]) > SPLIT_DATE]
    sd = separation(disc)
    print(f"  discovery: n_block={sd['n_block']} n_pass={sd['n_pass']} "
          + (f"highest_block={sd['highest_block']:.2f} lowest_pass={sd['lowest_pass']:.2f} "
             f"best_t={sd['best_threshold']:.2f} errors={sd['best_errors']}" if sd.get("clean") is not None else "(one class empty)"))
    if sd.get("clean") is not None:
        t = sd["best_threshold"]
        errs = [(v, tr) for v, tr in chk if (v <= t) != (tr == "BLOCK")]
        print(f"  check at discovery threshold {t:.2f}: n={len(chk)} errors={len(errs)} {errs}")
    sc = separation(chk)
    if sc.get("clean") is not None:
        print(f"  check alone: highest_block={sc['highest_block']:.2f} lowest_pass={sc['lowest_pass']:.2f}")

    print("\n=== what m1 / day_range would read on the NON-nominated labelled rows (never acts) ===")
    for m in sorted((m for m in table if not m["nominated"] and m["tier"] == 1), key=lambda m: m["date"]):
        a = ("/".join(m["answer"]) if m["answer"] else "none") + f"({m['answer_path'][0]})"
        print(f"  {m['ticker']:6}{m['date']:11}{m['truth']:6}{a:28}m1={fmt(m.get('m1'),6)} dayR={fmt(m.get('day_range'),7)}"
              f"  {(m['label'] or '')[:40]}")

    if "--json" in argv:
        out = HERE / "pin_backtest_measures.json"
        out.write_text(json.dumps(table, indent=1, default=str), encoding="utf-8")
        print(f"\nwrote {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
