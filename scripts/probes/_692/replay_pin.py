"""#692 offline replay ($0) — every one of the 151 replayed stock-days re-decided under the
2026-10-03 rule (the news nominates, the PRICE decides), from the RECORDED answers of the 10-02
replay and the EXPORTED bars. No model call, no network, no DB.

Inputs
  replay_2026-10-02.jsonl       the recorded grader + headline answers, the 10-02 decision, labels
  pin/daily_bars.csv            daily OHLCV per stock-day (+70 calendar days before)
  pin/minute_bars_to_1030.csv   09:30-10:30 ET minute bars (EP days; some other days have none)

Mechanism — the PRODUCTION function, not a lookalike: each row is rebuilt as a harness Case
(scripts/probes/_284_mna_acquirer_backtest.py — Polygon and the model replaced by the recorded
articles / answers) and run through the real `ma_filter.is_likely_ma` with a `pin_reader` that
returns the exported reading for the detector's window:
  * EP day (`ep_day`)            the OPEN WINDOW — 09:30-09:34 bars via `open_window_pin_from_bars`
  * every other detector         the DAY WINDOW — the own-day bar via `day_window_pin`
  * an EP day with no exported minute bars reads the day window instead and says so (`note`)
  * the price-signature rows (flag deal_pin_*) are out of #692 scope and carried unchanged.

Outputs (next to this file)
  replay_pin_2026-10-03.jsonl           one line per stock-day: both decisions, the answer that
                                        governed, the reading, `changed`, `why`
  replay_pin_2026-10-03_summary.txt     counts + every row whose decision changed vs 10-02 and the
                                        reading that changed it
ASCII-only output.
"""
from __future__ import annotations

import asyncio
import csv
import importlib.util
import json
import sys
from collections import Counter, defaultdict
from datetime import date, datetime
from pathlib import Path
from zoneinfo import ZoneInfo

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[2]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

_ET = ZoneInfo("America/New_York")
REPLAY_IN = HERE / "replay_2026-10-02.jsonl"
OUT_JSONL = HERE / "replay_pin_2026-10-03.jsonl"
OUT_SUMMARY = HERE / "replay_pin_2026-10-03_summary.txt"
DAILY = HERE / "pin" / "daily_bars.csv"
MINUTE = HERE / "pin" / "minute_bars_to_1030.csv"

CALLS_2026_10_03 = {("DSGN", "2026-05-18"): "PASS", ("THR", "2026-05-22"): "PASS",
                    ("PD", "2026-05-29"): "PASS", ("HZO", "2026-08-10"): "BLOCK",
                    ("RNW", "2026-08-11"): "BLOCK"}


def _harness():
    spec = importlib.util.spec_from_file_location(
        "mna_harness_692_replay_pin", HERE.parent / "_284_mna_acquirer_backtest.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def load_bars():
    daily = defaultdict(list)
    with DAILY.open(encoding="utf-8") as fh:
        for r in csv.DictReader(fh):
            daily[(r["t"], r["d"])].append({
                "trade_date": r["trade_date"], "open_price": r["open_price"],
                "high_price": r["high_price"], "low_price": r["low_price"],
                "close": r["close"], "volume": r["volume"]})
    minute = defaultdict(list)
    with MINUTE.open(encoding="utf-8") as fh:
        for r in csv.DictReader(fh):
            ts = datetime.strptime(r["et"], "%Y-%m-%d %H:%M:%S").replace(tzinfo=_ET)
            minute[(r["t"], r["d"])].append({
                "ts": ts, "open": float(r["open"]), "high": float(r["high"]),
                "low": float(r["low"]), "close": float(r["close"]), "volume": float(r["volume"])})
    return daily, minute


def reading_for(row: dict, daily, minute):
    """(PinReading, note) — the detector's own window from the exports."""
    from agents.market_intelligence import ma_filter as mf
    key = (row["ticker"], row["date"])
    day = date.fromisoformat(row["date"])
    if row.get("ep_day"):
        bars = minute.get(key) or []
        if bars:
            return mf.open_window_pin_from_bars(bars, day, as_of="export"), ""
        return mf.day_window_pin(daily.get(key) or [], day), "EP day without exported minute bars: day window used"
    return mf.day_window_pin(daily.get(key) or [], day), ""


def case_for(row: dict, H):
    """Rebuild the 10-02 replay row as a harness Case: the recorded grader answer + grade, and
    the asked articles with their recorded answers (an unanswered article has no fixture, so the
    fake model raises = unanswered, exactly as recorded)."""
    g = row.get("grader_parsed")
    ga = row.get("grader_answer") or {}
    grader = H.Ans(*g, (ga.get("deal_counterparty") or "")) if g else None
    articles, answers = [], {}
    for h in row.get("headline_asked") or []:
        title = h.get("title") or ""
        mp = h.get("match_path") or "title"
        reasoning = h.get("reasoning") if mp == "description+insights" else None
        item = H._item(title, description=h.get("description") or "", ticker=row["ticker"],
                       reasoning=reasoning, published=h.get("published_utc") or "2026-01-01T00:00:00Z")
        if reasoning is None:
            item["insights"] = []
        articles.append(item)
        p = h.get("parsed")
        if p:
            answers[title] = H.Ans(*p, ((h.get("answer") or {}).get("deal_counterparty") or ""))
    for h in row.get("headline_article_cap") or []:   # recorded unanswered (beyond the 3 newest)
        if isinstance(h, str):                          # the 10-02 replay stored bare titles
            h = {"title": h}
        title = h.get("title") or ""
        articles.append(H._item(title, description=h.get("description") or "",
                                published=h.get("published_utc") or "2026-01-01T00:00:00Z"))
    return H.Case(row["ticker"], row["date"], row.get("label") or "", bool(row.get("label")),
                  "replay", row.get("new_decision") or "", row.get("grader_grade"),
                  (row.get("corpus") or "",), grader, tuple(articles), tuple(answers.items()),
                  None)


async def decide(row: dict, H, daily, minute) -> dict:
    out = {"ticker": row["ticker"], "date": row["date"], "detectors": row.get("detectors") or [],
           "ep_day": bool(row.get("ep_day")), "label": row.get("label"),
           "call_2026_10_03": CALLS_2026_10_03.get((row["ticker"], row["date"])),
           "old_decision": row.get("old_decision"), "decision_2026_10_02": row.get("new_decision"),
           "why_2026_10_02": row.get("new_why")}
    if row.get("arm") == "price_signature":
        out.update({"decision_2026_10_03": row.get("new_decision"), "why_2026_10_03": "price_signature_unchanged",
                    "nominated": False, "reading": None, "changed": False, "note": "out of #692 scope"})
        return out
    reading, note = reading_for(row, daily, minute)
    case = case_for(row, H)

    async def _reader():
        return reading
    res = await H.run_new(case, pin_reader=_reader)
    meta = res.meta or {}
    pending = bool(meta.get("pending"))
    decision = "BLOCK" if res.blocked else "PASS"
    why = meta.get("why") if res.blocked else "no_pin"
    released = [a for a in res.audits if a[0] == "mna_filter_released"]
    if not res.blocked and released and "pin_free" in released[0][2].get("old_reasons", []):
        why = "pin_free"
    source = meta.get("source") if res.blocked else (released[0][2]["pin_release"]["source"]
                                                     if why == "pin_free" else None)
    asked_titles = sorted(h.get("title") or "" for h in row.get("headline_asked") or [])
    asked_mismatch = sorted(res.calls) != asked_titles
    out.update({
        "decision_2026_10_03": decision + (" (held: window unreadable)" if pending else ""),
        "why_2026_10_03": why, "source": source, "pending": pending,
        "nominated": why in ("pinned", "pin_free", "pin_pending"),
        "answer": meta.get("role") and {"role": meta.get("role"), "status": meta.get("status"),
                                        "consideration": meta.get("consideration")}
        or (released[0][2]["pin_release"]["answer"] if why == "pin_free" else None),
        "reading": reading.as_dict() if reading is not None else None,
        "changed": (decision != (row.get("new_decision") or "")),
        "note": note + ("; asked-article set differs from the 10-02 run" if asked_mismatch else ""),
        "unplanned": res.unplanned,
    })
    return out


async def main() -> int:
    H = _harness()
    daily, minute = load_bars()
    rows = [json.loads(ln) for ln in REPLAY_IN.read_text(encoding="utf-8").splitlines() if ln.strip()]
    rows = [r for r in rows if r.get("kind") == "ticker_day"]
    results = [await decide(r, H, daily, minute) for r in rows]
    with OUT_JSONL.open("w", encoding="utf-8") as fh:
        for r in results:
            fh.write(json.dumps(r, default=str) + "\n")

    lines = []
    n = len(results)
    c10_02 = Counter(r["decision_2026_10_02"] for r in results)
    c10_03 = Counter(r["decision_2026_10_03"].split(" ")[0] for r in results)
    lines.append(f"#692 offline replay under the 2026-10-03 rule (the news nominates, the price decides)")
    lines.append(f"n = {n} stock-days; 10-02 rule: {dict(c10_02)}; 10-03 rule: {dict(c10_03)}")
    nominated = [r for r in results if r.get("nominated")]
    lines.append(f"nominated (the price decided): {len(nominated)} — pinned {sum(r['why_2026_10_03']=='pinned' for r in nominated)}, "
                 f"free {sum(r['why_2026_10_03']=='pin_free' for r in nominated)}, "
                 f"held {sum(r['why_2026_10_03']=='pin_pending' for r in nominated)}")
    changed = [r for r in results if r["changed"]]
    lines.append(f"\nCHANGED vs the 10-02 replay: {len(changed)} row(s)")
    lines.append(f"  {'ticker':6} {'day':10} {'detectors':18} {'10-02':6} -> {'10-03':6}  reading / why / his call")
    for r in changed:
        rd = r["reading"] or {}
        reading = (f"{rd.get('window')} {rd.get('range_pct')}% vs {rd.get('threshold_pct')}%"
                   if rd.get("readable") else f"{rd.get('window')} unreadable ({rd.get('why')})")
        ans = r.get("answer") or {}
        lines.append(f"  {r['ticker']:6} {r['date']:10} {','.join(r['detectors'])[:18]:18} "
                     f"{r['decision_2026_10_02']:6} -> {r['decision_2026_10_03']:6}  {reading}; "
                     f"{ans.get('role')}/{ans.get('status')}/{ans.get('consideration')} via {r.get('source')}; "
                     f"{r['why_2026_10_03']}"
                     + (f"; HIS CALL {r['call_2026_10_03']}" if r.get("call_2026_10_03") else "")
                     + (f"; {r['label']}" if r.get("label") else ""))
    wrong = [r for r in results if r.get("call_2026_10_03") and
             r["decision_2026_10_03"].split(" ")[0] != r["call_2026_10_03"]]
    lines.append(f"\nhis five 2026-10-03 calls honoured: {5 - len(wrong)} of 5" +
                 (f"  MISSED: {[(r['ticker'], r['date']) for r in wrong]}" if wrong else ""))
    lab = [r for r in results if r.get("label")]
    lab_wrong = [r for r in lab if r["decision_2026_10_03"].split(" ")[0] !=
                 ("BLOCK" if ("TP" in r["label"] or "REAL buyout" in r["label"]) else "PASS")]
    lines.append(f"the 25 earlier labels honoured: {len(lab) - len(lab_wrong)} of {len(lab)}" +
                 (f"  MISSED: {[(r['ticker'], r['date']) for r in lab_wrong]}" if lab_wrong else ""))
    held = [r for r in results if r.get("pending")]
    if held:
        lines.append(f"\nheld (window unreadable in the export): {[(r['ticker'], r['date'], (r['reading'] or {}).get('why')) for r in held]}")
    notes = [r for r in results if r.get("note") and r["note"] != "out of #692 scope"]
    if notes:
        lines.append(f"\nnotes: {[(r['ticker'], r['date'], r['note']) for r in notes]}")
    unplanned = [r for r in results if r.get("unplanned")]
    if unplanned:
        lines.append(f"\nUNPLANNED questions (an asked article had no recorded answer): {[(r['ticker'], r['date'], r['unplanned']) for r in unplanned]}")
    text = "\n".join(lines)
    OUT_SUMMARY.write_text(text + "\n", encoding="utf-8")
    print(text)
    print(f"\nwrote {OUT_JSONL.name} and {OUT_SUMMARY.name}")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
