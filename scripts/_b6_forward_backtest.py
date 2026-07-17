"""#448 B6 — forward backtest: does the catalyst rubric (composite_min=22)
downgrade LOSERS more than WINNERS?

Re-scores the post-2026-05-19 EP cohort with the CURRENT rubric via the LIVE
code path — `build_rubric_inputs_hybrid` + `score_ticker` imported verbatim
(the exact two lines `score_ep_with_rubric` runs; inlined only to capture the
deltas for the Pradeep 39%-bar add-on). No LLM anywhere (PATH 1 per
docs/analysis/448_b6_rescore_scoping_2026-07-11.md).

No-lookahead: the live runtime assumes yfinance column 0 = q1 (true at alert
time only). We fetch each ticker's CURRENT quarterly_financials once, then for
each alert serve a COLUMN-SLICED copy through a sys.modules['yfinance'] shim:
drop q0's column and everything newer, so column 0 is again q1-as-of-alert.
q0's column is found by value-matching raw_json's q_revenue_usd.value against
the revenue row (±3%); rows that need the date heuristic instead are flagged
`align=date_heuristic` and counted in the report.

Fidelity gate: re-derived composites are compared against the LIVE composites
recorded in `catalyst_earnings_revenue_weak_downgrade` audit payloads (the
only DB surface that stores the live composite — PASS rows have no stored
anchor). Residual known drift: post-alert restatements in yfinance.

Inputs (pulled read-only from prod, see #448 session):
  cohort.jsonl          ticker/alert_date/raw_json  (mi_ep_catalyst_metrics)
  outcomes.jsonl        forward returns             (mi_ep_missed_outcomes)
  live_downgrades.jsonl live composite anchors      (mi_audit_log)

Usage:
  python scripts/_b6_forward_backtest.py <data_dir> [--out report.md]

Read-only analysis. The threshold decision (keep 22 / lower / raise) is the
OPERATOR's (THE LINE) — this script only produces the crosstab + evidence.
"""
from __future__ import annotations

import argparse
import json
import pickle
import re
import statistics
import sys
import time
import types
from collections import defaultdict
from datetime import date, timedelta
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))

THRESHOLD = 22.0  # CATALYST_RUBRIC_MIN_COMPOSITE under test
VALUE_MATCH_TOL = 0.03
Q0_MAX_LAG_DAYS = 100   # date heuristic: newest col within this window pre-alert = q0
Q0_MIN_LAG_DAYS = 15    # cols ending closer to the alert than this can't be announced yet
FIDELITY_TOL = 2.0      # |live - rederived| composite points

# The live augment's revenue-row lookup — imported so the q0 value-match can
# never drift from what live scoring reads (imported before the yfinance shim
# is installed; the helper has no yfinance dependency).
from agents.market_intelligence.catalyst_rubric_runtime import (  # noqa: E402
    find_revenue_row,
)


# ── yfinance shim ────────────────────────────────────────────────────────────
# The live augment does `import yfinance as yf` INSIDE the function, so a
# sys.modules swap redirects it. _CURRENT holds the sliced frame for the alert
# being scored.
_CURRENT: dict = {"qf": None}


class _FakeTicker:
    def __init__(self, ticker: str):
        self._t = ticker

    @property
    def quarterly_financials(self):
        return _CURRENT["qf"]


def _install_shim():
    shim = types.ModuleType("yfinance")
    shim.Ticker = _FakeTicker
    sys.modules["yfinance"] = shim


def _fetch_all_qf(tickers: list[str], cache_path: Path) -> dict:
    """One real yfinance pull per ticker, cached. The cache TOPS UP: tickers
    already present are served from disk, missing ones (a grown cohort on a
    re-run) are fetched and merged — a stale all-or-nothing cache would
    silently score every new ticker q0-only (align=no_data). NB: cached
    entries keep their pull-date's data; a re-run wanting fresh quarters for
    OLD tickers should use a fresh data_dir (see the review's action_when_ready)."""
    out: dict = {}
    if cache_path.exists():
        with open(cache_path, "rb") as f:
            out = pickle.load(f)
    missing = [t for t in tickers if t not in out]
    if not missing:
        return out
    import yfinance as yf  # the REAL module — before the shim is installed
    print(f"  cache has {len(out)}; fetching {len(missing)} missing ticker(s)")
    for i, t in enumerate(missing):
        try:
            qf = yf.Ticker(t).quarterly_financials
            out[t] = qf if qf is not None and not qf.empty else None
        except Exception as e:
            print(f"  yf fetch failed {t}: {e}")
            out[t] = None
        if i % 10 == 9:
            print(f"  fetched {i + 1}/{len(missing)}")
        time.sleep(0.25)
    with open(cache_path, "wb") as f:
        pickle.dump(out, f)
    return out


def _slice_asof(qf, extracted: dict, alert: date):
    """Drop q0's column + anything newer so column 0 = q1-as-of-alert.
    Returns (sliced_qf, method) — method in {value_match, date_heuristic,
    no_data}. Known residual (flagged bucket): a late announcer (>100d lag)
    with no value-match keeps q0 as 'q1' under the date heuristic — the
    Q0_MAX_LAG window trades that tail against dropping a real q1 for very
    recent alerts yfinance hasn't caught up on."""
    if qf is None or qf.empty:
        return None, "no_data"
    cols = list(qf.columns)
    rev_row = find_revenue_row(qf)

    q0_val = ((extracted.get("q_revenue_usd") or {}).get("value")
              if isinstance(extracted.get("q_revenue_usd"), dict) else None)
    if rev_row is not None and isinstance(q0_val, (int, float)) and q0_val > 0:
        for i in range(min(4, len(cols))):  # q0 must be near the front
            if cols[i].date() > alert:
                continue   # ended AFTER the alert — cannot be q0 (a post-alert
                           # quarter within ±3% of q0 must not steal the match)
            v = rev_row.iloc[i]
            try:
                if v and abs(float(v) - q0_val) / q0_val < VALUE_MATCH_TOL:
                    return qf[cols[i + 1:]], "value_match"
            except Exception:
                continue

    # Date heuristic: drop cols too new to have been announced, then treat the
    # newest remaining as q0 if it plausibly IS the announced quarter.
    cutoff = alert - timedelta(days=Q0_MIN_LAG_DAYS)
    keep = [c for c in cols if c.date() <= cutoff]
    if keep and (alert - keep[0].date()).days <= Q0_MAX_LAG_DAYS:
        keep = keep[1:]
    return qf[keep] if keep else None, "date_heuristic"


# ── stats helpers ────────────────────────────────────────────────────────────
def _agg(vals: list[float]) -> dict:
    vals = [v for v in vals if v is not None]
    if not vals:
        return {"n": 0}
    return {"n": len(vals), "mean": statistics.mean(vals),
            "median": statistics.median(vals),
            "win_rate": sum(1 for v in vals if v > 0) / len(vals)}


def _fmt(a: dict) -> str:
    if a["n"] == 0:
        return "n=0"
    return (f"n={a['n']:>3}  mean={a['mean']:+6.1f}%  med={a['median']:+6.1f}%  "
            f"win={a['win_rate'] * 100:4.0f}%")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("data_dir", type=Path)
    ap.add_argument("--out", type=Path, default=None)
    args = ap.parse_args()
    d = args.data_dir

    cohort = [json.loads(l) for l in open(d / "cohort.jsonl")]
    outcomes_raw = [json.loads(l) for l in open(d / "outcomes.jsonl")]
    downgrades = [json.loads(l) for l in open(d / "live_downgrades.jsonl")]

    # outcomes: dedupe per (ticker, alert_date), prefer a row with ret_5d.
    # DB stores returns as FRACTIONS (0.184 = +18.4%) — convert to percent
    # here so every downstream number reads naturally.
    outcomes: dict = {}
    for o in outcomes_raw:
        for f in ("ret_1d", "ret_5d", "ret_20d", "max_high_5d", "max_high_20d"):
            if o.get(f) is not None:
                o[f] = o[f] * 100.0
        k = (o["ticker"], o["alert_date"])
        if k not in outcomes or (outcomes[k].get("ret_5d") is None
                                 and o.get("ret_5d") is not None):
            outcomes[k] = o

    # live composite anchors from the downgrade audit payloads
    live_comp: dict = {}
    for ev in downgrades:
        det = ev.get("detail")
        if isinstance(det, str):
            try:
                det = json.loads(det)
            except Exception:
                continue
        if not isinstance(det, dict):
            continue
        m = re.match(r"rubric_composite_([\d.]+)_below_", det.get("reason") or "")
        if m:
            live_comp[(det["ticker"], det["alert_date"])] = float(m.group(1))

    # Phase A: real yfinance pull (before the shim replaces the module)
    tickers = sorted({r["ticker"] for r in cohort})
    print(f"cohort={len(cohort)} rows / {len(tickers)} tickers; fetching yfinance…")
    qf_all = _fetch_all_qf(tickers, d / "qf_cache.pkl")

    # Phase B: score through the LIVE path with the as-of slice
    _install_shim()
    from agents.market_intelligence.catalyst_rubric import score_ticker
    from agents.market_intelligence.catalyst_rubric_runtime import (
        build_rubric_inputs_hybrid,
    )

    rows = []
    for r in cohort:
        ticker = r["ticker"]
        alert = date.fromisoformat(r["alert_date"])
        extracted = r["raw_json"]
        if isinstance(extracted, str):
            extracted = json.loads(extracted)

        qr = extracted.get("q_revenue_usd")
        if not isinstance(qr, dict) or qr.get("yoy_pct") is None:
            rows.append({"ticker": ticker, "alert_date": r["alert_date"],
                         "verdict": "UNSCORED", "composite": None,
                         "align": "n/a", "deltas": {}})
            continue

        sliced, method = _slice_asof(qf_all.get(ticker), extracted, alert)
        _CURRENT["qf"] = sliced
        # the exact two lines score_ep_with_rubric runs (inlined for deltas)
        fund, beat, guidance = build_rubric_inputs_hybrid(ticker, extracted, alert)
        res = score_ticker(fund, beat=beat, guidance=guidance)
        comp = res.get("composite_scaled") if res else None
        rows.append({
            "ticker": ticker, "alert_date": r["alert_date"],
            "composite": comp,
            "label": res.get("label") if res else None,
            "verdict": ("UNSCORED" if comp is None
                        else "PASS" if comp >= THRESHOLD else "DOWNGRADE"),
            "align": method,
            "deltas": fund.get("deltas") or {},
            "guidance": guidance,
            # projected FY sales growth (PERCENT units) for the Pradeep bar
            "guid_midpoint_yoy_pct": (
                (extracted.get("guidance_fy_revenue_usd") or {}).get("midpoint_yoy_pct")
                if isinstance(extracted.get("guidance_fy_revenue_usd"), dict) else None
            ),
        })
    _CURRENT["qf"] = None

    # Phase C: fidelity vs live downgrade anchors
    fid = []
    for row in rows:
        k = (row["ticker"], row["alert_date"])
        if k in live_comp and row["composite"] is not None:
            fid.append((k, live_comp[k], row["composite"],
                        abs(live_comp[k] - row["composite"])))
    fid_ok = [f for f in fid if f[3] <= FIDELITY_TOL]

    # Phase D: outcomes join + crosstab
    for row in rows:
        o = outcomes.get((row["ticker"], row["alert_date"])) or {}
        for f in ("ret_1d", "ret_5d", "ret_20d", "max_high_5d", "max_high_20d"):
            row[f] = o.get(f)
        row["has_outcome"] = bool(o)

    def bucket(verdict):
        return [r for r in rows if r["verdict"] == verdict and r["ret_5d"] is not None]

    passed, downg = bucket("PASS"), bucket("DOWNGRADE")
    unscored = [r for r in rows if r["verdict"] == "UNSCORED"]

    # Pradeep explosive-growth bar (T6b): q0>=39% AND q1>=39% AND projected>=39%
    # (projected = FY-guidance midpoint YoY, PERCENT units, as the proxy for
    # 'projected sales' — flagged in the report)
    for row in rows:
        dl = row.get("deltas") or {}
        gm = row.get("guid_midpoint_yoy_pct")
        row["pradeep_explosive"] = bool(
            (dl.get("rev_yoy_q0") or 0) >= 0.39
            and (dl.get("rev_yoy_q1") or 0) >= 0.39
            and isinstance(gm, (int, float)) and gm >= 39.0
        )
    pra_t = [r for r in rows if r["pradeep_explosive"] and r["ret_5d"] is not None]
    pra_f = [r for r in rows if not r["pradeep_explosive"] and r["ret_5d"] is not None]

    # Threshold sensitivity sweep
    scored = [r for r in rows if r["composite"] is not None and r["ret_5d"] is not None]
    sweep = []
    for t in range(16, 31, 2):
        p = [r["ret_5d"] for r in scored if r["composite"] >= t]
        dn = [r["ret_5d"] for r in scored if r["composite"] < t]
        sweep.append((t, _agg(p), _agg(dn)))

    # ── report ──────────────────────────────────────────────────────────────
    L = []
    L.append("# #448 B6 forward backtest — rubric composite_min=22 vs forward outcomes")
    L.append(f"\nCohort: {len(cohort)} alerts (2026-05-19 → {max(r['alert_date'] for r in cohort)}), "
             f"re-scored with the CURRENT rubric via the live path (no LLM). "
             f"Outcome join coverage: {sum(1 for r in rows if r['has_outcome'])}/{len(rows)}.")
    align_counts = defaultdict(int)
    for r in rows:
        align_counts[r["align"]] += 1
    L.append(f"As-of alignment: {dict(align_counts)} (value_match = exact q0 column "
             f"identified; date_heuristic rows are the residual-risk subset).")
    L.append(f"\n## Fidelity gate (vs {len(live_comp)} live downgrade anchors)")
    L.append(f"- matched {len(fid)} anchors; {len(fid_ok)}/{len(fid)} within "
             f"±{FIDELITY_TOL} composite points")
    n_up = sum(1 for f in fid if f[2] > f[1] + FIDELITY_TOL)
    n_dn = sum(1 for f in fid if f[2] < f[1] - FIDELITY_TOL)
    L.append(f"- mismatch direction: rederived HIGHER than live in {n_up}, LOWER in "
             f"{n_dn} (HIGHER-skew ⇒ live-time yfinance fetch failures scored fewer "
             f"axes — live operational degradation, not replay error)")
    for k, lv, rv, dd in sorted(fid, key=lambda x: -x[3])[:8]:
        flag = "" if dd <= FIDELITY_TOL else "  ⚠"
        L.append(f"  - {k[0]} {k[1]}: live={lv:.1f} rederived={rv:.1f} Δ={dd:.1f}{flag}")

    # PRIMARY: live-verdict crosstab — uses the verdicts the gate ACTUALLY issued
    # (downgrade audit anchors = live DOWNGRADE; scorable-but-not-anchored = live
    # PASS). Zero replay error; the replay crosstab below adds threshold sweeps.
    l_pass = [r for r in rows if r["verdict"] != "UNSCORED" and r["ret_5d"] is not None
              and (r["ticker"], r["alert_date"]) not in live_comp]
    l_down = [r for r in rows if r["verdict"] != "UNSCORED" and r["ret_5d"] is not None
              and (r["ticker"], r["alert_date"]) in live_comp]
    L.append("\n## PRIMARY — crosstab on LIVE verdicts (replay-free)")
    for name, b in (("live PASS", l_pass), ("live DOWNGRADE", l_down)):
        L.append(f"- {name:<15} ret_5d: {_fmt(_agg([r['ret_5d'] for r in b]))}   "
                 f"maxhi5d: {_fmt(_agg([r['max_high_5d'] for r in b]))}")
    l_prec = (sum(1 for r in l_down if r["ret_5d"] <= 0) / len(l_down)) if l_down else float("nan")
    L.append(f"- live downgrade-precision (loser = ret_5d ≤ 0): {l_prec * 100:.0f}%")
    L.append("- REPLAY LIMITATION (why live-verdict is primary): the as-of column "
             "slice leaves ~4 historical quarters where live scoring saw ~5-6, so "
             "q1-YoY/accel axes are unavailable in replay more often than live — "
             "re-derived composites skew LOW (matches the 10-low/6-high fidelity "
             "skew). A full-parity replay needs deeper history (FMP quarterlies).")

    L.append(f"\n## Crosstab — REPLAYED verdict at composite_min={THRESHOLD:.0f} × forward returns")
    for name, b in (("PASS (≥22)", passed), ("DOWNGRADE (<22)", downg)):
        L.append(f"\n### {name}")
        for h in ("ret_1d", "ret_5d", "ret_20d", "max_high_5d", "max_high_20d"):
            L.append(f"- {h:<12} {_fmt(_agg([r[h] for r in b]))}")
    n_dn_losers = sum(1 for r in downg if r["ret_5d"] <= 0)
    prec = n_dn_losers / len(downg) if downg else float("nan")
    L.append(f"\n**Downgrade precision** (loser = ret_5d ≤ 0): "
             f"{n_dn_losers}/{len(downg)} = **{prec * 100:.0f}%**")
    pe, de = _agg([r["ret_5d"] for r in passed]), _agg([r["ret_5d"] for r in downg])
    if pe["n"] and de["n"]:
        L.append(f"**PASS − DOWNGRADE edge (ret_5d)**: mean {pe['mean'] - de['mean']:+.1f}pp · "
                 f"median {pe['median'] - de['median']:+.1f}pp "
                 f"(1R operationalized ≈ 5pp — a typical EP ORB stop; operator may re-cut)")
    uns_out = [r["ret_5d"] for r in unscored if r["ret_5d"] is not None]
    L.append(f"\nUNSCORED (rubric couldn't score — non-earnings catalysts, safety-net "
             f"path; NOT gated by the composite): {len(unscored)} rows. Reference "
             f"outcome: {_fmt(_agg(uns_out))}")
    L.append("First 12: " + ", ".join(f"{r['ticker']} {r['alert_date']}" for r in unscored[:12]))

    L.append("\n## Downgraded WINNERS (the cost side — what 22 threw away)")
    for r in sorted(downg, key=lambda x: -(x["ret_5d"] or 0))[:10]:
        if (r["ret_5d"] or 0) > 0:
            r20 = f"{r['ret_20d']:+.1f}%" if r["ret_20d"] is not None else "?"
            mh = f"{r['max_high_5d']:+.1f}%" if r["max_high_5d"] is not None else "?"
            L.append(f"- {r['ticker']} {r['alert_date']}: comp={r['composite']:.1f} "
                     f"ret_5d={r['ret_5d']:+.1f}% ret_20d={r20} maxhi5d={mh}")
    L.append("\n## Passed LOSERS (the leniency side)")
    for r in sorted(passed, key=lambda x: (x["ret_5d"] or 0))[:10]:
        if (r["ret_5d"] or 0) <= 0:
            L.append(f"- {r['ticker']} {r['alert_date']}: comp={r['composite']:.1f} "
                     f"ret_5d={r['ret_5d']:+.1f}%")

    L.append("\n## Threshold sensitivity (ret_5d by verdict at each cut)")
    L.append("| cut | PASS | DOWNGRADE |")
    L.append("|---|---|---|")
    for t, p, dn in sweep:
        L.append(f"| {t} | {_fmt(p)} | {_fmt(dn)} |")

    L.append("\n## Pradeep explosive-growth bar (T6b add-on: q0≥39% ∧ q1≥39% ∧ guidance≥39%)")
    L.append(f"- TRUE : {_fmt(_agg([r['ret_5d'] for r in pra_t]))}   "
             f"({', '.join(r['ticker'] for r in pra_t) or '—'})")
    L.append(f"- FALSE: {_fmt(_agg([r['ret_5d'] for r in pra_f]))}")
    L.append("- projected≥39% uses FY-guidance midpoint YoY as the proxy (the note's "
             "'projected sales'); rows lacking guidance default FALSE.")
    # which leg binds? (so a TRUE-n=0 result reads as data-sparsity vs genuinely-rare)
    leg_q0 = [r for r in rows if (r.get("deltas") or {}).get("rev_yoy_q0") is not None
              and r["deltas"]["rev_yoy_q0"] >= 0.39]
    leg_q0q1 = [r for r in leg_q0 if (r["deltas"].get("rev_yoy_q1") or 0) >= 0.39]
    leg_guid = [r for r in rows if isinstance(r.get("guid_midpoint_yoy_pct"), (int, float))]
    q0q1_out = [r["ret_5d"] for r in leg_q0q1 if r["ret_5d"] is not None]
    n_q1_known = sum(1 for r in leg_q0
                     if (r.get("deltas") or {}).get("rev_yoy_q1") is not None)
    L.append(f"- leg diagnostics: q0≥39% n={len(leg_q0)}; of those, q1-YoY KNOWN in "
             f"replay for {n_q1_known} (the as-of slice's history-depth gap — see "
             f"REPLAY LIMITATION above); rows with ANY FY guidance = "
             f"{len(leg_guid)}/{len(rows)}. q0∧q1≥39% n={len(leg_q0q1)} "
             f"({', '.join(r['ticker'] for r in leg_q0q1) or '—'}); outcome: "
             f"{_fmt(_agg(q0q1_out))}")
    L.append("- VERDICT ON THE BAR: NOT evaluable on this cohort — q1 unavailable in "
             "the as-of replay (needs the deeper FMP quarterly pull) and FY guidance "
             "is extracted for only a handful of rows. Checked-and-BLOCKED-ON-DATA, "
             "not checked-and-refuted.")

    L.append("\n## Decision matrix (from #448 — the call is the operator's)")
    L.append("- downgrade-precision >80% AND PASS-edge > DOWNGRADE-edge by ≥1R → rubric sound, keep 22")
    L.append("- downgrade-precision <60% → dropping winners, lower the threshold")
    L.append("- PASS-edge ≤ DOWNGRADE-edge → too lenient, raise to 25-28")

    report = "\n".join(L)
    # Date-stamped default so a re-run (the Sept recheck) never overwrites the
    # evidence doc a prior operator ruling cites.
    out = args.out or (REPO / "docs" / "analysis"
                       / f"448_b6_forward_backtest_{date.today().isoformat()}.md")
    out.write_text(report)
    print(report)
    print(f"\nreport → {out}")

    # per-row dump for auditability
    with open(d / "b6_rows.json", "w") as f:
        json.dump([{k: v for k, v in r.items() if k != "deltas"} for r in rows], f,
                  indent=1, default=str)


if __name__ == "__main__":
    main()
