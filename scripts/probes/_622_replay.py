#!/usr/bin/env python3
"""#622 — would the $500M market-cap floor's rejects have made or lost money through OUR OWN
bracket (realized R), vs the control cohort the stack actually scored, over the same trailing
90-day window?

Operator's own correction (2026-09-04, on top of #593's max-favourable-excursion measure I gave
him first): "shouldn't we measure against actual entry/exit, i.e. how much we make or lose with
them?" A price that touched 4R is not 4R realized. This is the realized-R version.

Follows the shape of yesterday's `_617_replay.py` (rejected 7-9% gap band) — same walker, same
rule-set, same abstain discipline — but a DIFFERENT bar source: #617 fetched Alpaca SIP bars for
names never admitted to any scan_log row. Every ticker-day here (both cohorts) already has a
mi_ep_scan_log row (mcap-rejected, or scored), so its minute/daily bars already live in our own
DB tables (mi_intraday_bars / mi_daily_closes) — no Alpaca fetch needed, $0, no external call.

THE WALKER IS NOT MINE: scripts.ep_replay.walk_campaign under rule-set "current" (era C:
entry-2R stop, +2R partial, breakeven at partial, 10:00 unfilled cancel) — validate_orb_entry,
stop_limit_buy_price, profit_target_r_per_share, apply_daily_exit_step, the live modules.
`python scripts/ep_replay.py validate` -> PASS captured in _622_validate_out.txt BEFORE any
number here was read (2026-09-04).

The measure is the operator's own (#593): realized R through our real entry/stop/exit. Primary
>= 4R, secondary any positive R. Detection assumed at 09:31 (most optimistic for every name); a
09:36 sensitivity reported beside it.

ARTIFACT GUARD — the RIGHT one for THIS data source (found by reading gap_near_miss_replay.py,
which replays the exact same two tables): mi_daily_closes is split-ADJUSTED and REWRITTEN after
a later reverse split (LGCL: $118.94 in the daily row, $0.95 on the actual day); mi_intraday_bars
is RAW and never rewritten. A name that splits AFTER its alert day but BEFORE this capture shows
an inflated daily open_price against the still-raw 09:30 minute open. Same guard, same threshold
(5%, SPLIT_DIVERGENCE_ABS_PCT in gap_near_miss_replay.py): |daily_open/raw_0930_open - 1| > 0.05
=> split_artifact, abstained, reported in coverage, never walked.

Usage: python scripts/probes/_622_replay.py   -> _622_replay_out.tsv + _622_replay_summary.txt
"""
from __future__ import annotations

import csv
import statistics
import sys
from collections import Counter, defaultdict
from datetime import date, datetime, time
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parent.parent
sys.path.insert(0, str(REPO))
import scripts.ep_replay as ep  # noqa: E402
from scripts.ep_replay import atr14_abs, get_ruleset, walk_campaign  # noqa: E402
from shared.dates import _ET  # noqa: E402

ep.LAST_SETTLED = date(2026, 9, 3)      # last COMPLETE daily session in the capture (09-04 is live)
SPLIT_DIVERGENCE_ABS_PCT = 0.05          # identical guard/threshold to gap_near_miss_replay.py:141


def load_pairs(path: Path) -> list[dict]:
    with open(path) as fh:
        return list(csv.DictReader(fh, delimiter="\t"))


def load_minutes(path: Path):
    minutes: dict[tuple[str, date], list[dict]] = defaultdict(list)
    with open(path) as fh:
        for line in fh:
            line = line.rstrip("\n")
            if not line or line.startswith("ticker|") or line.startswith("("):
                continue
            p = line.split("|")
            if len(p) != 7:
                continue
            dt = datetime.strptime(p[1], "%Y-%m-%d %H:%M").replace(tzinfo=_ET)
            minutes[(p[0], dt.date())].append(
                {"m": dt, "o": float(p[2]), "h": float(p[3]), "l": float(p[4]), "c": float(p[5])})
    for bars in minutes.values():
        bars.sort(key=lambda b: b["m"])
    return minutes


def load_daily(path: Path):
    daily: dict[str, dict[date, dict]] = defaultdict(dict)
    with open(path) as fh:
        for line in fh:
            line = line.rstrip("\n")
            if not line or line.startswith("trade_date|") or line.startswith("("):
                continue
            p = line.split("|")
            if len(p) != 7:
                continue
            d = date.fromisoformat(p[0])
            daily[p[1]][d] = {
                "o": float(p[2]) if p[2] else None, "h": float(p[3]) if p[3] else None,
                "l": float(p[4]) if p[4] else None, "c": float(p[5]) if p[5] else None,
                "v": float(p[6]) if p[6] else None}
    return daily


def main() -> None:
    pairs = load_pairs(HERE / "_622_all_pairs.tsv")
    minutes = load_minutes(HERE / "_622_minute_bars_out.txt")
    daily = load_daily(HERE / "_622_daily_bars_out.txt")
    print(f"loaded: {len(pairs)} pairs, minute pairs {len(minutes)}, daily tickers {len(daily)}")
    rs = get_ruleset("current")

    out_rows = []
    for r in pairs:
        t, d = r["ticker"], date.fromisoformat(r["scan_date"])
        bars0 = minutes.get((t, d), [])
        n_min = len(bars0)
        orb930 = next((b for b in bars0 if b["m"].time() == time(9, 30)), None)
        daily_open = (daily.get(t, {}).get(d) or {}).get("o")
        artifact, art_reason = False, ""
        if orb930 is not None and daily_open:
            div = abs(daily_open / orb930["o"] - 1)
            if div > SPLIT_DIVERGENCE_ABS_PCT:
                artifact, art_reason = True, f"daily_open {daily_open:.2f} vs raw_0930 {orb930['o']:.2f} ({div:.0%})"
        base = {"cohort": r["cohort"], "ticker": t, "scan_date": r["scan_date"],
                "max_gap": r["max_gap"], "prev_close": r["prev_close"],
                "n_min_bars": n_min, "has_930": orb930 is not None,
                "artifact": artifact, "art_reason": art_reason}
        atr_14 = atr14_abs(daily.get(t, {}), d)
        for label, submit in (("0931", time(9, 31)), ("0936", time(9, 36))):
            if artifact:
                res = {"status": "excluded_artifact", "reason": art_reason}
            elif n_min == 0:
                res = {"status": "abstain", "reason": "no_minute_bars_in_db"}
            else:
                res = walk_campaign(ticker=t, alert_date=d, rs=rs, minutes=minutes, daily=daily,
                                    submit=submit, atr_14=atr_14)
            base[f"status_{label}"] = res.get("status")
            base[f"reason_{label}"] = res.get("reason")
            base[f"entered_{label}"] = res.get("entered")
            base[f"entry_px_{label}"] = res.get("entry_px")
            base[f"stop_{label}"] = res.get("stop")
            base[f"target_{label}"] = res.get("target")
            base[f"realized_r_{label}"] = res.get("realized_r")
            base[f"mark_r_{label}"] = res.get("mark_r")
            base[f"final_{label}"] = res.get("final_reason")
            base[f"partial_{label}"] = res.get("partial_fired")
        out_rows.append(base)

    cols = list(out_rows[0].keys())
    with open(HERE / "_622_replay_out.tsv", "w") as fh:
        fh.write("\t".join(cols) + "\n")
        for x in out_rows:
            fh.write("\t".join("" if x[c] is None else str(x[c]) for c in cols) + "\n")

    # ── summary, side by side per cohort ────────────────────────────────────────────
    lines = []
    lines.append("cohort | n | artifact | no_bars | abstain(other) | no_trade(orb rule) | "
                 "no_entry | entered | settled | >=4R | >=2R | >0 | sumR | meanR | "
                 "open_at_horizon(mark>=4R) | >=4R @09:36 | full_session(>=300bars)")
    for coh in ("excluded", "control"):
        sub = [x for x in out_rows if x["cohort"] == coh]
        st = Counter(x["status_0931"] for x in sub)
        settled = [x for x in sub if x["status_0931"] == "settled"]
        R = [x["realized_r_0931"] for x in settled if x["realized_r_0931"] is not None]
        oah = [x for x in sub if x["status_0931"] == "open_at_horizon"]
        oah4 = sum(1 for x in oah if (x["mark_r_0931"] or 0) >= 4)
        ge4_36 = sum(1 for x in sub if x["status_0936"] == "settled" and (x["realized_r_0936"] or 0) >= 4)
        nobars = sum(1 for x in sub if x["status_0931"] == "abstain" and x["reason_0931"] == "no_minute_bars_in_db")
        full = sum(1 for x in sub if x["n_min_bars"] >= 300)
        lines.append(f"{coh:9s} | {len(sub)} | {st['excluded_artifact']} | {nobars} | {st['abstain'] - nobars} | "
                     f"{st['no_trade']} | {st['no_entry']} | {sum(1 for x in sub if x['entered_0931'])} | "
                     f"{len(R)} | {sum(1 for x in R if x >= 4)} | {sum(1 for x in R if x >= 2)} | "
                     f"{sum(1 for x in R if x > 0)} | {sum(R):+.1f} | "
                     f"{(statistics.mean(R) if R else 0):+.2f} | {len(oah)}({oah4}) | {ge4_36} | {full}")
        ab = Counter((x["reason_0931"] or "").split(":")[0] for x in sub if x["status_0931"] == "abstain")
        nt = Counter((x["reason_0931"] or "").split(":")[0] for x in sub if x["status_0931"] == "no_trade")
        lines.append(f"    abstain reasons: {dict(ab)}   no_trade reasons: {dict(nt)}")
        if R:
            lines.append(f"    R distribution: min {min(R):+.2f}  p25 {statistics.quantiles(R, n=4)[0] if len(R)>=4 else min(R):+.2f}  "
                         f"median {statistics.median(R):+.2f}  p75 {statistics.quantiles(R, n=4)[2] if len(R)>=4 else max(R):+.2f}  "
                         f"max {max(R):+.2f}  worst {min(R):+.2f}")
        top = sorted(settled, key=lambda x: -(x["realized_r_0931"] or -9))[:10]
        lines.append("    top settled: " + ", ".join(
            f"{x['ticker']} {x['scan_date']} {x['realized_r_0931']:+.2f}R" for x in top))
        worst = sorted(settled, key=lambda x: (x["realized_r_0931"] or 9))[:10]
        lines.append("    worst settled: " + ", ".join(
            f"{x['ticker']} {x['scan_date']} {x['realized_r_0931']:+.2f}R" for x in worst))
        if oah:
            lines.append("    open_at_horizon marks (unrealized, NOT counted in sumR/meanR): " + ", ".join(
                f"{x['ticker']} {x['scan_date']} mark {x['mark_r_0931']:+.2f}R" for x in
                sorted(oah, key=lambda x: -(x['mark_r_0931'] or -9))[:8]))
        art = [x for x in sub if x["artifact"]]
        if art:
            lines.append(f"    ARTIFACTS excluded: {len(art)} — " + ", ".join(
                f"{x['ticker']} {x['scan_date']} ({x['art_reason']})" for x in art))
        # degenerate-stop check: risk-per-share < 0.3% of entry (same threshold as this
        # harness's own _MIN_R_UNIT_FRAC re-entry guard) makes R blow up on noise, not edge
        degen = [x for x in settled if x["entry_px_0931"] and
                (float(x["entry_px_0931"]) - float(x["stop_0931"])) / float(x["entry_px_0931"]) < 0.003]
        if degen:
            lines.append(f"    DEGENERATE-STOP settled trades (risk/share <0.3% of entry — R is noise-amplified, "
                         f"flagged not excluded): " + ", ".join(
                f"{x['ticker']} {x['scan_date']} {x['realized_r_0931']:+.2f}R "
                f"(entry {float(x['entry_px_0931']):.2f} stop {float(x['stop_0931']):.4f})" for x in degen))
            settled_ex = [x for x in settled if x not in degen]
            R_ex = [x["realized_r_0931"] for x in settled_ex if x["realized_r_0931"] is not None]
            lines.append(f"    -> EXCLUDING those {len(degen)}: n={len(R_ex)} sumR={sum(R_ex):+.2f} "
                         f"meanR={(statistics.mean(R_ex) if R_ex else 0):+.3f} "
                         f">=4R:{sum(1 for x in R_ex if x >= 4)} >0:{sum(1 for x in R_ex if x > 0)}")
        # 09:36 sensitivity — the FULL picture (not just the >=4R count above)
        settled36 = [x for x in sub if x["status_0936"] == "settled"]
        R36 = [x["realized_r_0936"] for x in settled36 if x["realized_r_0936"] is not None]
        lines.append(f"    @09:36 (5-min-later detection): entered={sum(1 for x in sub if x['entered_0936'])} "
                     f"settled={len(R36)} sumR={sum(R36):+.2f} meanR={(statistics.mean(R36) if R36 else 0):+.3f} "
                     f"medianR={(statistics.median(R36) if R36 else 0):+.3f} "
                     f">=4R:{sum(1 for x in R36 if x >= 4)} >0:{sum(1 for x in R36 if x > 0)}"
                     f"({(sum(1 for x in R36 if x > 0)/len(R36)*100 if R36 else 0):.0f}%) "
                     f"worst={min(R36) if R36 else 0:+.2f}")

    # cross-cohort ticker-day overlap note (data-quality honesty, not a filter decision)
    exc_pairs = {(x["ticker"], x["scan_date"]) for x in out_rows if x["cohort"] == "excluded"}
    ctl_pairs = {(x["ticker"], x["scan_date"]) for x in out_rows if x["cohort"] == "control"}
    ov = exc_pairs & ctl_pairs
    lines.append(f"\nticker-days classified in BOTH cohorts (same day, different scan_log rows): "
                 f"{len(ov)} — {sorted(ov)}")

    txt = "\n".join(lines)
    (HERE / "_622_replay_summary.txt").write_text(txt + "\n")
    print(txt)


if __name__ == "__main__":
    main()
