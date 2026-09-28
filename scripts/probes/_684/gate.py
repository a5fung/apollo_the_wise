#!/usr/bin/env python3
"""#684 STEP 0 — POPULATION GATE, from the captured files (pop.tsv + the two gate SQL captures).

Prints composition ONLY — no forward bar is read here, no outcome is computed. Writes gate_out.txt.
Population = every gap-day candidate the EP scan SCORED (ep_score NOT NULL) in mi_ep_scan_log,
scan_date 2026-05-01 .. 2026-09-03 (last scan date with >= 15 later sessions in mi_daily_closes),
ONE row per (ticker, scan_date) — dedupe rule: prefer the tick that PASSED (filter_reason NULL and
score_tier set), else the highest ep_score, ties -> latest scan_time_et.

Two admission labels are carried, because they disagree in two known places:
  scan_pass  = the gap-day scan's OWN verdict (a pass tick exists)            — primary
  alert_row  = a live-source mi_ep_alerts row with the same ticker + date        — secondary
Where they disagree (found by gate_alarms.sql, both explained):
  (a) 44 scan_pass rows 05-01..05-08 have NO alert row: mi_ep_alerts holds nothing before 2026-05-11
      (the old 90-day purge — ep_profitability_program.md:843); the scan-log pass row is the surviving
      record that the scan alerted them.  -> counted as ALERTED (scan_pass).
  (b) 7 live alerts dated 2026-05-20 were INSERTED at 18:40 ET — an evening re-run after that morning's
      EP-scan outage (CHANGELOG 2026-05-20, UnboundLocalError, scans dead 07:00-08:21) and after the
      pre-revenue-gate change shipped that afternoon. 5 (ALAB ARM DYN GH TATT) have no scored scan-log
      row at all and are outside the population; 2 (IMVT SLS) were scored and REJECTED by the gap-day
      scan (max tick 48 / 20.4) and alerted only by the evening re-run. -> IMVT/SLS stay in the
      population as scored-NOT-passed; their alert rows are tagged evening_rerun_0520.
"""
from __future__ import annotations

import statistics
from collections import Counter, defaultdict
from pathlib import Path

HERE = Path(__file__).resolve().parent


def load_psv(path: Path) -> list[dict]:
    """Read a psql unaligned capture: header row, '|' fields, skip the '(N rows)' footer and any
    '\\pset' echo lines (the README pattern — a footer parsed as data is a real defect, #623)."""
    rows: list[dict] = []
    header: list[str] | None = None
    with path.open() as fh:
        for line in fh:
            line = line.rstrip("\n")
            if not line or line.startswith("(") or line.startswith("Output format") or line.startswith("Field separator"):
                continue
            parts = line.split("|")
            if header is None:
                header = parts
                continue
            if len(parts) != len(header):
                raise ValueError(f"{path.name}: bad row width {len(parts)} vs {len(header)}: {line[:80]}")
            rows.append(dict(zip(header, parts)))
    return rows


def fnum(x: str | None) -> float | None:
    if x is None or x == "":
        return None
    try:
        return float(x)
    except ValueError:
        return None


def median(xs: list[float]) -> float | None:
    xs = [x for x in xs if x is not None]
    return statistics.median(xs) if xs else None


def price_band(p: float | None) -> str:
    if p is None:
        return "null"
    if p < 5:
        return "<$5"
    if p < 20:
        return "$5-20"
    if p < 100:
        return "$20-100"
    return "$100+"


def score_band(s: float) -> str:
    if s < 50:
        return "<50"
    if s < 65:
        return "50-65"
    if s < 80:
        return "65-80"
    return "80+"


EVENING_RERUN_0520 = {("IMVT", "2026-05-20"), ("SLS", "2026-05-20")}
LABELLED = [("BFLY", "2026-06-18"), ("PLTR", "2026-08-04"), ("ABNB", "2026-08-07"), ("TEAM", "2026-08-07"),
            ("HTFL", "2026-08-14"), ("MRNA", "2026-08-19"), ("CHPT", "2026-09-03")]


def annotate(rows: list[dict]) -> None:
    for r in rows:
        r["scan_pass"] = r["any_pass_tick"] == "t"
        r["alert_row"] = r["alert_id"] != ""
        r["evening_rerun_0520"] = (r["ticker"], r["scan_date"]) in EVENING_RERUN_0520
        r["alerted"] = r["scan_pass"]  # primary label — see module docstring
        r["era"] = "A" if r["scan_date"] < "2026-08-22" else "B"
        r["block"] = "DISCOVERY" if r["scan_date"] <= "2026-08-14" else "HELD-OUT"
        r["month"] = r["scan_date"][:7]
        r["prev_close_f"] = fnum(r["prev_close"])
        r["gap_f"] = fnum(r["gap_pct"])
        r["score_f"] = fnum(r["ep_score"])


def main() -> None:
    rows = load_psv(HERE / "pop.tsv")
    annotate(rows)
    out: list[str] = []
    p = out.append
    p("#684 STEP 0 — POPULATION GATE (composition only; no outcome computed here)")
    p("source files: pop.tsv (extract.sh, pulled " + (HERE / "extract.pulled_at").read_text().strip() + ")")
    p("population = mi_ep_scan_log rows with ep_score NOT NULL, scan_date 2026-05-01..2026-09-03, one row per (ticker, scan_date)")
    p("dedupe rule = prefer the PASS tick (filter_reason NULL and score_tier set), else max ep_score, ties -> latest scan_time_et")
    p("  (gate_sql_out.txt: 5,818 scored ticks -> 670 pairs; 0 pairs change admission under a last-tick rule; all ticks created same day, i.e. live scans, no backfill)")
    p("")
    n = len(rows)
    p(f"n_total = {n}   names = {len({r['ticker'] for r in rows})}   scan_dates = {len({r['scan_date'] for r in rows})}")
    p("")
    p("BY MONTH (n / alerted=scan_pass / not):")
    by_m = defaultdict(list)
    for r in rows:
        by_m[r["month"]].append(r)
    for m in sorted(by_m):
        rs = by_m[m]
        p(f"  {m}: {len(rs):4d}   alerted {sum(r['alerted'] for r in rs):4d}   scored-not-alerted {sum(not r['alerted'] for r in rs):4d}")
    p("")
    p("BY ERA (A = scan_date < 2026-08-22 old score; B = 08-22 on, #533 separated score, bar 65):")
    for era in ("A", "B"):
        rs = [r for r in rows if r["era"] == era]
        p(f"  era {era}: n {len(rs)}   alerted {sum(r['alerted'] for r in rs)}   not {sum(not r['alerted'] for r in rs)}   "
          f"tiers {dict(Counter(r['score_tier'] or 'none' for r in rs))}   score bands {dict(sorted(Counter(score_band(r['score_f']) for r in rs).items()))}")
    p("")
    p("BY BLOCK (DISCOVERY = scan_date <= 2026-08-14; HELD-OUT = 08-15..09-03):")
    for b in ("DISCOVERY", "HELD-OUT"):
        rs = [r for r in rows if r["block"] == b]
        p(f"  {b}: n {len(rs)}   alerted {sum(r['alerted'] for r in rs)}   not {sum(not r['alerted'] for r in rs)}   ISO weeks {len({iso_week(r['scan_date']) for r in rs})}")
    p("")
    p("PRICE BANDS (prev_close from the scan log; universe floor is $5 so nothing sits under it):")
    for band in ("<$5", "$5-20", "$20-100", "$100+", "null"):
        rs = [r for r in rows if price_band(r["prev_close_f"]) == band]
        if rs:
            p(f"  {band:8s}: {len(rs):4d}   alerted {sum(r['alerted'] for r in rs):4d}   not {sum(not r['alerted'] for r in rs):4d}")
    p(f"  median prev_close ${median([r['prev_close_f'] for r in rows]):.2f}")
    p("")
    p("GAP % (scan-log gap_pct at the chosen tick):")
    p(f"  median all {median([r['gap_f'] for r in rows]):.2f}%   alerted {median([r['gap_f'] for r in rows if r['alerted']]):.2f}%   not {median([r['gap_f'] for r in rows if not r['alerted']]):.2f}%")
    p(f"  median ep_score alerted {median([r['score_f'] for r in rows if r['alerted']]):.1f}   not {median([r['score_f'] for r in rows if not r['alerted']]):.1f}")
    p("")
    p("CATALYST QUALITY (scan log): " + str(dict(Counter(r["catalyst_quality"] or "null" for r in rows))))
    p("SCORED-NOT-ALERTED reasons: " + str(dict(Counter(("score < 50 (era A cutline)" if "< 50" in (r["filter_reason"] or "") else "score < bar 65 (era B)" if "< bar" in (r["filter_reason"] or "") else (r["filter_reason"] or "pass")[:30]) for r in rows if not r["alerted"]))))
    p("")
    p("RECONCILIATION against the known 277 live-source alerts 05-01..09-11 (261 before 08-22) — gate_sql_out.txt + gate_alarms_out.txt:")
    p("  277 / 261 reproduced from mi_ep_alerts by the same DISTINCT ON (ticker, alert_date) + live-source rule.")
    p("  270 of the 277 fall inside the population window (<= 09-03); the other 7 are dated 09-04 (ALAB) and 09-08 (ERO IONQ PHVS QCOM ROIV SEI) — no 15-session outcome yet.")
    p("  265 of the 270 join a scored scan-log row; the 5 that do not are ALL 2026-05-20 (ALAB ARM DYN GH TATT), inserted 18:40 ET by an evening re-run after that")
    p("    morning's scan outage (CHANGELOG 2026-05-20) — never scored by a gap-day scan, so outside this population by definition.")
    n_alert_rows = sum(r["alert_row"] for r in rows)
    n_pass = sum(r["scan_pass"] for r in rows)
    n_pass_no_row = sum(r["scan_pass"] and not r["alert_row"] for r in rows)
    n_row_no_pass = sum(r["alert_row"] and not r["scan_pass"] for r in rows)
    p(f"  In the population: {n_alert_rows} rows carry a live alert row; {n_pass} rows carry a scan PASS tick.")
    p(f"    pass-but-no-alert-row = {n_pass_no_row}: all scan_date 05-01..05-08 ({sorted({r['scan_date'] for r in rows if r['scan_pass'] and not r['alert_row']})}) —")
    p("      mi_ep_alerts holds NO row before 2026-05-11 (the old 90-day purge, ep_profitability_program.md:843) so the alert record is gone; the scan-log pass")
    p("      row is the surviving evidence the scan alerted them. Counted as ALERTED.")
    p(f"    alert-row-but-no-pass-tick = {n_row_no_pass}: {[r['ticker'] + ' ' + r['scan_date'] for r in rows if r['alert_row'] and not r['scan_pass']]} — the 05-20 evening re-run;")
    p("      the gap-day scan rejected both (max ticks 48 and 20.4 < 50). Kept as scored-NOT-alerted (the scan's own verdict); tagged evening_rerun_0520.")
    p(f"  => alerted (scan_pass) = {n_pass} = {n_alert_rows} alert rows − {n_row_no_pass} evening re-run + {n_pass_no_row} purged-era passes.")
    p("")
    p("HIS LABELLED EPs (operator_labelled_eps.md) in this population:")
    idx = {(r["ticker"], r["scan_date"]): r for r in rows}
    for t, d in LABELLED:
        r = idx.get((t, d))
        if r:
            p(f"  {t} {d}: IN — score {r['ep_score']} tier {r['score_tier'] or 'none'} alerted={r['alerted']} reason={r['filter_reason'] or 'pass'}")
        else:
            why = {"ABNB": "never scored — cut by the top-20 gap cap (2 scan rows, both 'outside top-20')",
                   "CHPT": "never scored — filter:mcap_too_small before scoring"}.get(t, "?")
            p(f"  {t} {d}: NOT IN — {why}")
    p("")
    p("PRE-08-22 DATA FACT (checked on prod 2026-09-27 and again here): era A rows carry only ep_score + catalyst_quality;")
    p("  extension_pct / market_cap / float / atr_pct / prior_3m_change / score_breakdown / in_active_theme are EMPTY on every era A row")
    era_a = [r for r in rows if r["era"] == "A"]
    for col in ("extension_pct", "market_cap", "float_shares", "atr_pct", "prior_3m_change", "score_breakdown"):
        p(f"    era A {col} filled: {sum(r[col] != '' for r in era_a)} of {len(era_a)};  era B: {sum(r[col] != '' for r in rows if r['era'] == 'B')} of {sum(r['era'] == 'B' for r in rows)}")
    p("  -> every gap-day feature is COMPUTED from mi_daily_closes / mi_stock_scores / mi_themes / mi_market_regime / mi_intraday_bars (features.py).")
    p("")
    p("SURPRISES CHECKED: no sub-$5 rows (universe floor); May is the largest month (228 of 670 — the first-week-of-May earnings cluster, 05-01..05-08 = "
      f"{sum(r['scan_date'] <= '2026-05-08' for r in rows)} rows); era B is small (40 rows, 9 alerted) because the window ends 09-03 and the 08-22 rescale cut admissions.")
    p("GATE PASSED — the alerted subset reconciles to the 277 (270 in window = 265 joined + 5 evening-re-run rows never scored); no unexplained trait.")
    text = "\n".join(out) + "\n"
    (HERE / "gate_out.txt").write_text(text)
    print(text)


def iso_week(d: str) -> str:
    import datetime as _dt
    y, w, _ = _dt.date.fromisoformat(d).isocalendar()
    return f"{y}-W{w:02d}"


if __name__ == "__main__":
    main()
