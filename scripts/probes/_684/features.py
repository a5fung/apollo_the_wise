#!/usr/bin/env python3
"""#684 STEP 1 — FEATURES, one row per population member, each tagged by WHEN it is known.

Reads the captured files only (pop.tsv, daily.tsv.gz, hist.tsv, scores.tsv, themes.tsv, prior.tsv,
orb.tsv, regime.tsv, sector.tsv). Writes features.tsv. NO forward bar is read here: the only bar at or
after the gap day this file touches is the gap-day bar itself (index i0), and only for the CLOSE group.
`_guard_no_forward` asserts it.

WHEN-KNOWN TAGS (the live entry is a 09:31 ET opening-range buy):
  PRE   known before the open (prior closes, the scan's gap read, scores, themes, regime)
  0930  needs the gap-day OPEN print (an ORB buyer sees it at 09:30)
  0945  needs the first 15 minute bars (mi_intraday_bars; coverage counted)
  CLOSE needs the gap-day close — valid for a day-2+ entry only, never for the 09:31 entry
  ALERT known when the alert was written (judge / catalyst fields; alerted rows only)

Bars: mi_daily_closes is split-ADJUSTED (nightly re-fetch); the scan log's prev_close / gap_pct are raw
prints. `split_mismatch` flags rows where the two prev closes differ by > 3 % — their bar-based features
are on the adjusted basis and are still internally consistent; the flag is reported, not silently dropped.

ADR20 = the house definition: mean((h-l)/c) over the 20 sessions ending D-1 (alert_rank_shadow.
compute_adr20_frac); adr_dollar_prev = adr20_frac x prev_close (feature units); adr_dollar_ep =
adr20_frac x gap-day close (outcome units, = delayed_entry_shadow.compute_ep_adr_dollar).
"""
from __future__ import annotations

import datetime as dt
import gzip
import statistics
from collections import defaultdict
from pathlib import Path

from gate import EVENING_RERUN_0520, annotate, fnum, load_psv

HERE = Path(__file__).resolve().parent


def load_daily() -> dict[str, list[tuple[str, float, float, float, float, float]]]:
    out: dict[str, list] = defaultdict(list)
    with gzip.open(HERE / "daily.tsv.gz", "rt") as fh:
        header = None
        for line in fh:
            line = line.rstrip("\n")
            if not line or line.startswith("("):
                continue
            parts = line.split("|")
            if header is None:
                header = parts
                continue
            t, d, o, h, l, c, v = parts
            if not (o and h and l and c):
                continue
            out[t].append((d, float(o), float(h), float(l), float(c), float(v or 0)))
    for t in out:
        out[t].sort()
    return out


def sma(vals: list[float], n: int) -> float | None:
    if len(vals) < n:
        return None
    w = vals[-n:]
    return sum(w) / n


def days_between(a: str, b: str) -> int:
    return (dt.date.fromisoformat(a) - dt.date.fromisoformat(b)).days


def main() -> None:
    pop = load_psv(HERE / "pop.tsv")
    annotate(pop)
    daily = load_daily()
    hist = {(r["ticker"], r["scan_date"]): r for r in load_psv(HERE / "hist.tsv")}
    scores = {(r["ticker"], r["scan_date"]): r for r in load_psv(HERE / "scores.tsv")}
    themes = {(r["ticker"], r["scan_date"]): r for r in load_psv(HERE / "themes.tsv")}
    prior = {(r["ticker"], r["scan_date"]): r for r in load_psv(HERE / "prior.tsv")}
    orb = {(r["ticker"], r["scan_date"]): r for r in load_psv(HERE / "orb.tsv")}
    sector_ov = {r["ticker"]: r for r in load_psv(HERE / "sector.tsv")}
    regimes = sorted(load_psv(HERE / "regime.tsv"), key=lambda r: r["regime_date"])

    def regime_before(d: str) -> dict | None:
        best = None
        for r in regimes:
            if r["regime_date"] < d:
                best = r
            else:
                break
        return best

    feats: list[dict] = []
    for r in pop:
        t, d = r["ticker"], r["scan_date"]
        f: dict = {"ticker": t, "scan_date": d, "era": r["era"], "block": r["block"],
                   "alerted": int(r["alerted"]), "alert_row": int(r["alert_row"]),
                   "evening_rerun_0520": int(r["evening_rerun_0520"]),
                   "iso_week": iso_week(d), "ep_score": r["ep_score"], "score_tier": r["score_tier"],
                   "labelled": int((t, d) in {("BFLY", "2026-06-18"), ("PLTR", "2026-08-04"), ("TEAM", "2026-08-07"), ("HTFL", "2026-08-14"), ("MRNA", "2026-08-19")})}
        bars = daily.get(t, [])
        dates = [b[0] for b in bars]
        i0 = dates.index(d) if d in dates else None
        f["has_gap_bar"] = int(i0 is not None)
        f["n_pre_bars"] = i0 if i0 is not None else 0
        # ── scan-time / PRE features straight from the scan log ──────────────────────────
        f["PRE_gap_pct_scan"] = fnum(r["gap_pct"])
        f["PRE_prev_close"] = fnum(r["prev_close"])
        f["PRE_catalyst_quality"] = r["catalyst_quality"] or ""
        f["PRE_catalyst_ord"] = {"game_changer": 2, "strong": 1, "routine": 0}.get(r["catalyst_quality"] or "", None)
        f["PRE_rel_volume_scan"] = fnum(r["rel_volume"])
        f["PRE_pm_rvol"] = fnum(r["pm_rvol"])
        f["PRE_projected_vol_multiple"] = fnum(r["projected_vol_multiple"])
        f["PRE_rank_by_gap"] = fnum(r["rank_by_gap"])
        f["PRE_first_tick_hhmm"] = r["first_tick_time"]
        f["PRE_first_tick_preopen"] = int(r["first_tick_time"] < "09:30") if r["first_tick_time"] else None
        # ── ALERT-time fields (alerted rows only) ──────────────────────────────────────────
        f["ALERT_judge_tier"] = r["judge_tier"]
        f["ALERT_judge_grade"] = r["judge_grade"]
        f["ALERT_catalyst_type"] = r["catalyst_type"]
        f["ALERT_expct_scheduled"] = r["expct_scheduled"]
        f["ALERT_expct_beat"] = r["expct_beat"]
        f["ALERT_q_revenue_yoy_pct"] = fnum(r["q_revenue_yoy_pct"])
        f["ALERT_vol_alert_vs_max"] = fnum(r["vol_alert_vs_max"])
        f["RS_ext_xadr_eod"] = fnum(r["ext_xadr_eod"])          # rank-shadow copies, cross-check only
        f["RS_ext_xadr_pregap"] = fnum(r["ext_xadr_pregap"])
        f["RS_open_range_position"] = fnum(r["rs_open_range_position"])
        # ── scores / themes / regime / sector / repeat (PRE) ──────────────────────────────
        s = scores.get((t, d), {})
        age = days_between(d, s["score_date"]) if s.get("score_date") else None
        f["PRE_rs_score_age_days"] = age
        fresh = age is not None and age <= 7
        f["PRE_rs_rank"] = fnum(s.get("rs_rank")) if fresh else None
        pool = fnum(s.get("pool_size_that_day")) if fresh else None
        f["PRE_rs_rank_frac"] = (f["PRE_rs_rank"] / pool) if (f["PRE_rs_rank"] is not None and pool) else None
        f["PRE_rs_composite"] = fnum(s.get("rs_composite")) if fresh else None
        f["PRE_rs_3m"] = fnum(s.get("rs_3m")) if fresh else None
        f["PRE_rs_1m"] = fnum(s.get("rs_1m")) if fresh else None
        f["PRE_in_rs_pool"] = int(fresh)
        sec = (s.get("sector") or "") or (sector_ov.get(t, {}).get("sector") or "")
        f["PRE_sector"] = sec
        th = themes.get((t, d), {})
        f["PRE_themed"] = int(bool(th.get("theme_name")))
        f["PRE_theme_stage"] = th.get("theme_stage") or "none"
        f["PRE_theme_score"] = fnum(th.get("theme_score"))
        f["PRE_theme_days_active"] = fnum(th.get("days_active"))
        f["PRE_themed_7d"] = int(bool(th.get("theme_name_7d")))
        f["PRE_theme_stage_7d"] = th.get("theme_stage_7d") or "none"
        f["PRE_theme_early"] = int(f["PRE_theme_stage"] in ("Nascent", "Accelerating"))
        rg = regime_before(d) or {}
        f["PRE_regime"] = rg.get("regime") or ""
        f["PRE_regime_bull"] = int(rg.get("regime") == "Bull") if rg else None
        f["PRE_ep_threshold"] = fnum(rg.get("ep_threshold"))
        f["PRE_spy_vs_50ma"] = fnum(rg.get("spy_vs_50ma"))
        f["PRE_vix"] = fnum(rg.get("vix"))
        f["PRE_breadth_pct_above_40ma"] = fnum(rg.get("breadth_pct_above_40ma"))
        f["PRE_qqq_ema_bullish"] = {"t": 1, "f": 0}.get(rg.get("qqq_ema_bullish"), None)
        pr = prior.get((t, d), {})
        f["PRE_days_since_prev_scored"] = days_between(d, pr["prev_scored_date"]) if pr.get("prev_scored_date") else None
        f["PRE_days_since_prev_pass"] = days_between(d, pr["prev_pass_date"]) if pr.get("prev_pass_date") else None
        f["PRE_repeat_scored_90d"] = int(f["PRE_days_since_prev_scored"] is not None and f["PRE_days_since_prev_scored"] <= 90)
        f["PRE_repeat_pass_90d"] = int(f["PRE_days_since_prev_pass"] is not None and f["PRE_days_since_prev_pass"] <= 90)
        # ── bar-derived features ──────────────────────────────────────────────────────────
        if i0 is None or i0 < 21:
            feats.append(f)
            continue
        pre = bars[:i0]                       # strictly before the gap day
        _guard_no_forward(pre, d)
        o0, h0, l0, c0, v0 = bars[i0][1:]     # the gap-day bar — used ONLY by 0930 (open) and CLOSE groups
        closes = [b[4] for b in pre]
        highs = [b[2] for b in pre]
        lows = [b[3] for b in pre]
        vols = [b[5] for b in pre]
        prev_close = closes[-1]
        f["PRE_prev_close_bar"] = prev_close
        f["split_mismatch"] = int(abs((f["PRE_prev_close"] or prev_close) / prev_close - 1) > 0.03)
        adr_frac = statistics.mean((b[2] - b[3]) / b[4] for b in pre[-20:] if b[4] > 0)
        adr_prev = adr_frac * prev_close
        f["adr20_frac"] = adr_frac
        f["adr_dollar_prev"] = adr_prev
        f["adr_dollar_ep"] = adr_frac * c0            # outcome unit (study.py) — needs the gap-day close
        f["PRE_adr20_pct"] = adr_frac * 100
        f["PRE_dollar_vol_20d"] = statistics.mean(b[4] * b[5] for b in pre[-20:])
        f["PRE_vol_20d_shares"] = statistics.mean(vols[-20:])
        f["PRE_prev_day_dollar_vol"] = pre[-1][4] * pre[-1][5]
        s10, s20, s50 = sma(closes, 10), sma(closes, 20), sma(closes, 50)
        s200 = sma(closes, 200)
        s200_20ago = sma(closes[:-20], 200)
        f["PRE_ext_5d_pct"] = (prev_close / min(closes[-5:]) - 1) * 100            # the live gate's own definition
        f["PRE_ext_sma10_xadr"] = (prev_close - s10) / adr_prev if s10 else None
        f["PRE_ext_sma20_xadr"] = (prev_close - s20) / adr_prev if s20 else None
        f["PRE_ext_sma50_xadr"] = (prev_close - s50) / adr_prev if s50 else None
        f["PRE_ext_ma_mean_xadr"] = statistics.mean(x for x in (f["PRE_ext_sma10_xadr"], f["PRE_ext_sma20_xadr"], f["PRE_ext_sma50_xadr"]) if x is not None) if s50 else None
        f["PRE_ext_20d_low_pct"] = (prev_close / min(lows[-20:]) - 1) * 100
        f["PRE_chg_1m_pct"] = (prev_close / closes[-21] - 1) * 100
        f["PRE_chg_3m_pct"] = (prev_close / closes[-63] - 1) * 100 if len(closes) >= 63 else None
        f["PRE_chg_6m_pct"] = (prev_close / closes[-126] - 1) * 100 if len(closes) >= 126 else None
        f["PRE_above_sma10"] = int(prev_close > s10) if s10 else None
        f["PRE_above_sma20"] = int(prev_close > s20) if s20 else None
        f["PRE_above_sma50"] = int(prev_close > s50) if s50 else None
        f["PRE_n_ma_above"] = sum(x for x in (f["PRE_above_sma10"], f["PRE_above_sma20"], f["PRE_above_sma50"]) if x is not None) if s50 else None
        f["PRE_stage2"] = int(prev_close > s50 > s200 and s200 > s200_20ago) if (s50 and s200 and s200_20ago) else None
        f["PRE_above_sma200"] = int(prev_close > s200) if s200 else None
        # base / neglect
        w6 = pre[-126:] if len(pre) >= 126 else pre
        w52 = pre[-252:] if len(pre) >= 252 else None
        hi6 = max(b[2] for b in w6)
        i6 = max(range(len(w6)), key=lambda i: w6[i][2])
        f["PRE_high_6m"] = hi6
        f["PRE_days_since_6m_high"] = len(w6) - 1 - i6
        f["PRE_base_depth_6m_pct"] = (hi6 - prev_close) / hi6 * 100
        hr = hist.get((t, d), {})
        hi52 = max(b[2] for b in w52) if w52 else fnum(hr.get("high_52w"))
        f["PRE_high_52w"] = hi52
        if w52:
            i52 = max(range(len(w52)), key=lambda i: w52[i][2])
            f["PRE_days_since_52w_high"] = len(w52) - 1 - i52
        else:
            f["PRE_days_since_52w_high"] = None
        f["PRE_base_depth_52w_pct"] = (hi52 - prev_close) / hi52 * 100 if hi52 else None
        f["PRE_base_range40_pct"] = (max(closes[-40:]) - min(closes[-40:])) / prev_close * 100 if len(closes) >= 40 else None
        f["PRE_base_range20_pct"] = (max(closes[-20:]) - min(closes[-20:])) / prev_close * 100
        f["PRE_base_net_disp40_xadr"] = (prev_close - closes[-40]) / adr_prev if len(closes) >= 40 else None
        f["PRE_base_absdisp40_xadr"] = abs(f["PRE_base_net_disp40_xadr"]) if f["PRE_base_net_disp40_xadr"] is not None else None
        ath = fnum(hr.get("ath_high"))
        n_hist = fnum(hr.get("n_hist")) or 0
        f["PRE_ath_high"] = ath
        f["PRE_hist_years"] = n_hist / 252
        f["PRE_dist_52w_high_xadr"] = (hi52 - prev_close) / adr_prev if hi52 else None
        f["PRE_dist_ath_xadr"] = (ath - prev_close) / adr_prev if ath else None
        # supply cleared, PRE version = the scan's own gap read applied to the raw prev close
        gap_price = (f["PRE_prev_close"] or prev_close) * (1 + (f["PRE_gap_pct_scan"] or 0) / 100)
        raw_ratio = (f["PRE_prev_close"] or prev_close) / prev_close   # raw/adjusted basis bridge
        f["PRE_cleared_6m_scanprice"] = int(gap_price / raw_ratio > hi6)
        f["PRE_cleared_52w_scanprice"] = int(gap_price / raw_ratio > hi52) if hi52 else None
        f["PRE_cleared_ath_scanprice"] = int(gap_price / raw_ratio > ath) if (ath and n_hist >= 250) else None
        # ── 0930: the open print ──────────────────────────────────────────────────────────
        f["O930_gap_open_pct"] = (o0 / prev_close - 1) * 100
        f["O930_cleared_6m_open"] = int(o0 > hi6)
        f["O930_cleared_52w_open"] = int(o0 > hi52) if hi52 else None
        f["O930_cleared_ath_open"] = int(o0 > ath) if (ath and n_hist >= 250) else None
        f["O930_open_above_sma50"] = int(o0 > s50) if s50 else None
        f["O930_ext_open_sma50_xadr"] = (o0 - s50) / adr_prev if s50 else None
        f["O930_ext_open_sma20_xadr"] = (o0 - s20) / adr_prev if s20 else None
        f["O930_stage2_open"] = int(o0 > s50 > s200 and s200 > s200_20ago) if (s50 and s200 and s200_20ago) else None
        # ── 0945: opening range ──────────────────────────────────────────────────────────
        ob = orb.get((t, d), {})
        nb = fnum(ob.get("n_bars_0930_0944")) or 0
        f["O945_bars"] = nb
        f["O945_covered"] = int(nb >= 12)
        if nb >= 12:
            oh, ol, oc, oo, ov = (fnum(ob["orb_high"]), fnum(ob["orb_low"]), fnum(ob["orb_close_0944"]), fnum(ob["orb_open"]), fnum(ob["orb_vol"]))
            rng = oh - ol
            f["O945_orb_position"] = (oc - ol) / rng if rng > 0 else None
            f["O945_orb_range_xadr"] = rng / adr_prev
            f["O945_gap_0945_pct"] = (oc / prev_close - 1) * 100
            f["O945_close_vs_open_pct"] = (oc / oo - 1) * 100 if oo else None
            f["O945_orb_vol_vs_20d"] = ov / f["PRE_vol_20d_shares"] if f["PRE_vol_20d_shares"] else None
            f["O945_orb_high_above_6m"] = int(oh > hi6)
        # ── CLOSE: the gap-day bar ────────────────────────────────────────────────────────
        f["CLOSE_close_loc"] = (c0 - l0) / (h0 - l0) if h0 > l0 else None
        f["CLOSE_range_xadr"] = (h0 - l0) / adr_prev
        f["CLOSE_vol_vs_max250"] = v0 / max(vols[-250:]) if max(vols[-250:]) > 0 else None
        f["CLOSE_vol_vs_avg50"] = v0 / statistics.mean(vols[-50:]) if statistics.mean(vols[-50:]) > 0 else None
        f["CLOSE_close_vs_open_pct"] = (c0 / o0 - 1) * 100
        f["CLOSE_gap_close_pct"] = (c0 / prev_close - 1) * 100
        f["CLOSE_ext_sma50_xadr"] = (c0 - s50) / adr_prev if s50 else None
        f["CLOSE_ext_sma20_xadr"] = (c0 - s20) / adr_prev if s20 else None
        f["CLOSE_cleared_6m"] = int(c0 > hi6)
        f["CLOSE_cleared_52w"] = int(c0 > hi52) if hi52 else None
        f["CLOSE_cleared_ath"] = int(c0 > ath) if (ath and n_hist >= 250) else None
        feats.append(f)

    cols: list[str] = []
    for f in feats:
        for k in f:
            if k not in cols:
                cols.append(k)
    with (HERE / "features.tsv").open("w") as fh:
        fh.write("\t".join(cols) + "\n")
        for f in feats:
            fh.write("\t".join("" if f.get(c) is None else (f"{f[c]:.6g}" if isinstance(f[c], float) else str(f[c])) for c in cols) + "\n")
    # coverage summary
    n = len(feats)
    print(f"features.tsv: {n} rows, {len(cols)} columns")
    for k in ("has_gap_bar", "split_mismatch", "PRE_in_rs_pool", "PRE_themed", "PRE_themed_7d", "O945_covered", "PRE_stage2", "PRE_cleared_ath_scanprice"):
        vals = [f.get(k) for f in feats]
        print(f"  {k}: filled {sum(v is not None for v in vals)} / {n}; true {sum(1 for v in vals if v == 1)}")
    cov_al = sum(1 for f in feats if f.get("O945_covered") == 1 and f["alerted"])
    cov_na = sum(1 for f in feats if f.get("O945_covered") == 1 and not f["alerted"])
    print(f"  09:45 minute coverage: alerted {cov_al} of {sum(f['alerted'] for f in feats)}, not alerted {cov_na} of {sum(1 - f['alerted'] for f in feats)}")
    print(f"  n_pre_bars < 21 (no bar features): {sum(1 for f in feats if f['n_pre_bars'] < 21)}; < 200 (no SMA200): {sum(1 for f in feats if f['n_pre_bars'] < 200)}; < 252 (52w from server calendar window): {sum(1 for f in feats if f['n_pre_bars'] < 252)}")


def _guard_no_forward(pre: list, d: str) -> None:
    assert all(b[0] < d for b in pre), "forward bar leaked into the pre-gap window"


def iso_week(d: str) -> str:
    y, w, _ = dt.date.fromisoformat(d).isocalendar()
    return f"{y}-W{w:02d}"


if __name__ == "__main__":
    main()
