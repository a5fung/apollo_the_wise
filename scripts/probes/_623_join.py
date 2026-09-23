"""#623 — master join: population + market-cap resolution + volume/regime enrichment +
catalyst grade + realized-R outcome, into one row-per-ticker-day dataset for the
pre-registered analysis (_623_PREREGISTERED.md). No new feature or cell is introduced here
that isn't already in that file.
"""
import csv
import json
import re
import statistics
import sys
from collections import Counter, defaultdict
from pathlib import Path

HERE = Path(__file__).resolve().parent
MCAP_RE = re.compile(r"\$(\d+(?:\.\d+)?)M\s*<\s*\$500M")
BANDS = [(0, 200e6, "<200M"), (200e6, 500e6, "200-500M"), (500e6, 2e9, "500M-2B"),
         (2e9, 10e9, "2-10B"), (10e9, float("inf"), ">10B")]


def band_of(mcap):
    if mcap is None:
        return None
    for lo, hi, label in BANDS:
        if lo <= mcap < hi:
            return label
    return None


def f(x):
    try:
        return float(x) if x not in (None, "") else None
    except (TypeError, ValueError):
        return None


def load_psv(path):
    with open(path) as fh:
        reader = csv.DictReader(fh, delimiter="|")
        return [r for r in reader if r.get("ticker") and not r["ticker"].startswith("(")]


def load_tsv(path):
    with open(path) as fh:
        reader = csv.DictReader(fh, delimiter="\t")
        return list(reader)


def main():
    pop = {(r["ticker"], r["scan_date"]): r for r in load_psv(HERE / "_623_population_raw.psv")}
    shares = {}
    with open(HERE / "_623_shares_out.jsonl") as fh:
        for line in fh:
            r = json.loads(line)
            shares[r["ticker"]] = r
    enrich = {}
    with open(HERE / "_623_enrich_out.jsonl") as fh:
        for line in fh:
            r = json.loads(line)
            enrich[(r["ticker"], r["scan_date"])] = r
    replay = {(r["ticker"], r["scan_date"]): r for r in load_tsv(HERE / "_623_replay_out.tsv")}

    # #622's already-graded catalyst set (mcap-rejected cohort) — reused, not re-graded
    cat622 = {}
    p622 = HERE / "_622sweep_catalyst_raw.jsonl"
    if p622.exists():
        with open(p622) as fh:
            for line in fh:
                try:
                    r = json.loads(line)
                    key = (r.get("ticker"), r.get("scan_date"))
                    cat622[key] = r
                except Exception:
                    pass

    master = []
    n_no_replay = 0
    for key, p in pop.items():
        ticker, scan_date = key
        row = {"ticker": ticker, "scan_date": scan_date}

        # ---- market cap: 3-tier resolution ----
        mcap_col = f(p.get("market_cap"))
        mcap_source = None
        mcap = None
        if mcap_col:
            mcap, mcap_source = mcap_col, "column"
        else:
            m = MCAP_RE.search(p.get("nearest_filter_reason") or "")
            if m:
                mcap, mcap_source = float(m.group(1)) * 1_000_000, "filter_reason_parse"
        if mcap is None:
            sh = shares.get(ticker, {}).get("shares_outstanding")
            prev_close = f(p.get("prev_close"))
            if sh and prev_close:
                mcap, mcap_source = sh * prev_close, "proxy_shares_x_price"
        row["market_cap"] = mcap
        row["market_cap_source"] = mcap_source
        row["cap_band"] = band_of(mcap)

        # ---- gap / price ----
        row["gap_pct"] = f(p.get("gap_pct"))
        row["prev_close"] = f(p.get("prev_close"))
        row["tick_dist_sec"] = f(p.get("tick_dist_sec"))

        # ---- tag ----
        row["ever_scored"] = p.get("ever_scored") == "t"
        row["best_score_tier"] = p.get("best_score_tier") or None
        row["nearest_filter_reason"] = p.get("nearest_filter_reason")
        row["reject_stage"] = p.get("reject_stage")
        row["admitted_today"] = row["ever_scored"] and row["best_score_tier"] == "HIGH"

        # ---- volume (enrichment) ----
        e = enrich.get(key, {})
        row["today_volume_0931"] = e.get("today_volume_0931")
        row["vol_pct_daily_bars"] = e.get("vol_pct_daily_bars")
        row["record_volume_400d_0931"] = e.get("record_volume_400d_0931")
        row["eod_volume_day0"] = e.get("eod_volume_day0")
        row["eod_vol_pctile_400d"] = e.get("eod_vol_pctile_400d")
        row["eod_record_400d"] = e.get("eod_record_400d")
        row["regime"] = e.get("regime")
        tv = e.get("today_volume_0931")
        row["dollar_volume_0931"] = (tv * row["prev_close"]) if (tv and row["prev_close"]) else None

        # ---- catalyst ----
        cat = p.get("any_llm_catalyst_quality") or p.get("any_catalyst_quality")
        if not cat:
            c622 = cat622.get(key)
            if c622:
                cat = c622.get("catalyst_quality") or c622.get("grade")
        row["catalyst_quality"] = cat
        row["catalyst_ord"] = {"routine": 0, "strong": 1, "game_changer": 2}.get(cat)

        row["in_active_theme"] = p.get("in_active_theme") if p.get("in_active_theme") in ("t", "f") else None

        # ---- outcome ----
        rp = replay.get(key)
        if rp is None:
            n_no_replay += 1
            row["status"] = None
            row["realized_r"] = None
        else:
            row["status"] = rp.get("status")
            row["realized_r"] = f(rp.get("realized_r"))
            row["mark_r"] = f(rp.get("mark_r"))
            row["artifact"] = rp.get("artifact")
            row["entered"] = rp.get("entered")
            entry_px, stop = f(rp.get("entry_px")), f(rp.get("stop"))
            row["entry_px"] = entry_px
            row["stop"] = stop
            # same guard as _622_replay.py: risk/share < 0.3% of entry -> R is noise-amplified
            # by the rule-set's own R-normalization when the ORB range happens to be near-zero
            # width (ATI 2026-08-06: entry 220.00 / stop 219.98 -> realized_r=+119.5). Flagged,
            # not silently excluded — every headline number in the deliverable is reported both
            # ways.
            row["degenerate_stop"] = (
                entry_px is not None and stop is not None and entry_px > 0
                and (entry_px - stop) / entry_px < 0.003
            )

        master.append(row)

    print(f"master rows: {len(master)}, no replay match: {n_no_replay}")
    with open(HERE / "_623_master.jsonl", "w") as fh:
        for r in master:
            fh.write(json.dumps(r) + "\n")

    # quick coverage report
    settled = [r for r in master if r["status"] == "settled" and r["realized_r"] is not None]
    print(f"settled with realized_r: {len(settled)}")
    print("cap_band coverage:", Counter(r["cap_band"] for r in master).most_common())
    print("mcap_source:", Counter(r["market_cap_source"] for r in master).most_common())
    print("vol_pct_daily_bars coverage (settled):", sum(1 for r in settled if r["vol_pct_daily_bars"] is not None))
    print("record_volume coverage (settled):", sum(1 for r in settled if r["record_volume_400d_0931"] is not None))
    print("catalyst coverage (settled):", sum(1 for r in settled if r["catalyst_quality"]))
    print("admitted_today count:", sum(1 for r in master if r["admitted_today"]))


if __name__ == "__main__":
    main()
