#!/usr/bin/env python3
"""#617 STEP 1 — walk every never-admitted Jun-Aug 2026 gapper through OUR OWN bracket.

$0, offline, reads two captures:  `_617_replay_sets.tsv` (from `_617_classify.py --write-sets`)
and `_617_bars.psv.gz` (from `_617_fetch_bars.py`, Alpaca SIP raw minute + daily bars, plus a
split-adjusted daily pass used ONLY to detect phantom gaps).

THE WALKER IS NOT MINE: `scripts/ep_replay.walk_campaign` — validate_orb_entry, stop_limit_buy_price,
profit_target_r_per_share, apply_daily_exit_step, the live modules — under rule-set "current"
(era C: entry−2R stop, +2R partial, breakeven at partial, 10:00 unfilled cancel).
`python scripts/ep_replay.py validate` = PASS on 2026-09-03 before any number here was read.

The measure is the operator's (2026-09-03, #593): realized R through our real entry/stop/exit —
NOT a price move. Primary >= 4R, secondary any positive R. A name that ran and gave it back is not
a miss. Detection is assumed at 09:31 (the most optimistic case for every excluded name); a 09:36
sensitivity is reported beside it.

ARTIFACT GUARD (advisor 2026-09-03): a reverse split whose D-1 row mi_daily_closes never rewrote
reads as a +100..+400% 'gap' on the capture AND on raw bars alike. The split-adjusted Alpaca daily
open gap is the tell: |split_gap - capture_gap| > 2pp => gap_artifact, excluded from every recall
count and reported in coverage.

Usage: python scripts/probes/_617_replay.py   -> _617_replay_out.tsv + _617_replay_summary.txt
"""
from __future__ import annotations

import csv
import gzip
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

ep.LAST_SETTLED = date(2026, 9, 2)      # the capture's last daily session
SETS_SKIP = {"gap_floor_<5"}           # open <5% / high >=9%: intraday runs, not gaps (context only)
ARTIFACT_PP = 2.0


def load_bars(path: Path):
    minutes: dict[tuple[str, date], list[dict]] = defaultdict(list)
    daily_raw: dict[str, dict[date, dict]] = defaultdict(dict)
    daily_split: dict[str, dict[date, dict]] = defaultdict(dict)
    failed: list[str] = []
    sec = None
    with gzip.open(path, "rt") as fh:
        for line in fh:
            line = line.rstrip("\n")
            if line.startswith("==="):
                sec = line.strip("= ")
                continue
            if not line or line.startswith("ticker|"):
                continue
            if line.startswith("#FAILED_CHUNK"):
                failed.append(line)
                continue
            p = line.split("|")
            if sec == "MIN":
                dt = datetime.strptime(p[1], "%Y-%m-%d %H:%M").replace(tzinfo=_ET)
                minutes[(p[0], dt.date())].append(
                    {"m": dt, "o": float(p[2]), "h": float(p[3]), "l": float(p[4]), "c": float(p[5])})
            elif sec in ("DAILY_RAW", "DAILY_SPLIT"):
                d = date.fromisoformat(p[1])
                tgt = daily_raw if sec == "DAILY_RAW" else daily_split
                tgt[p[0]][d] = {"o": float(p[2]), "h": float(p[3]), "l": float(p[4]),
                                "c": float(p[5]), "v": float(p[6])}
    for bars in minutes.values():
        bars.sort(key=lambda b: b["m"])
    return minutes, daily_raw, daily_split, failed


def open_gap(dbars: dict[date, dict], d: date) -> float | None:
    prior = [x for x in dbars if x < d]
    if d not in dbars or not prior:
        return None
    pc = dbars[max(prior)]["c"]
    return (dbars[d]["o"] - pc) / pc * 100 if pc else None


def main() -> None:
    sets = [r for r in csv.DictReader(open(HERE / "_617_replay_sets.tsv"), delimiter="\t")
            if r["set"] not in SETS_SKIP]
    minutes, daily, dsplit, failed = load_bars(HERE / "_617_bars.psv.gz")
    print(f"loaded: {len(sets)} pairs, minute pairs {len(minutes)}, daily tickers {len(daily)}, "
          f"split tickers {len(dsplit)}, failed chunks {len(failed)}")
    rs = get_ruleset("current")
    out_rows = []
    for r in sets:
        t, d = r["ticker"], date.fromisoformat(r["trade_date"])
        cap_gap = float(r["open_gap_pct"])
        sg, rg = open_gap(dsplit.get(t, {}), d), open_gap(daily.get(t, {}), d)
        artifact = (sg is None) or abs(sg - cap_gap) > ARTIFACT_PP
        art_reason = ("no_daily" if sg is None else
                      f"split_gap {sg:.1f} vs capture {cap_gap:.1f}" if artifact else "")
        n_min = len(minutes.get((t, d), []))
        base = {"set": r["set"], "ticker": t, "trade_date": r["trade_date"], "cap_gap": cap_gap,
                "split_gap": None if sg is None else round(sg, 2),
                "raw_gap": None if rg is None else round(rg, 2),
                "artifact": artifact, "art_reason": art_reason, "n_min_bars": n_min,
                "prev_close": r["prev_close"], "prev_volume": r["prev_volume"]}
        for label, submit in (("0931", time(9, 31)), ("0936", time(9, 36))):
            if artifact:
                res = {"status": "excluded_artifact", "reason": art_reason}
            elif n_min == 0:
                res = {"status": "abstain", "reason": "no_minute_bars_fetched"}
            else:
                res = walk_campaign(ticker=t, alert_date=d, rs=rs, minutes=minutes, daily=daily,
                                    submit=submit, atr_14=atr14_abs(daily.get(t, {}), d))
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
            base[f"sess_abst_{label}"] = res.get("sessions_abstained")
        out_rows.append(base)

    cols = list(out_rows[0].keys())
    with open(HERE / "_617_replay_out.tsv", "w") as fh:
        fh.write("\t".join(cols) + "\n")
        for x in out_rows:
            fh.write("\t".join("" if x[c] is None else str(x[c]) for c in cols) + "\n")

    # ── summary per set ──────────────────────────────────────────────────────────
    lines = []
    order = ["gap_floor_8_9", "gap_floor_7_8", "gap_floor_6_7", "gap_floor_5_6",
             "gap_floor_9to10_admitted_now", "silent_no_row", "MIN_PREV_CLOSE",
             "MIN_PREV_DAY_VOLUME", "unclassified_security_type"]
    lines.append("set | n | artifact | no_bars | abstain | no_trade(orb rule) | no_entry | entered | settled | "
                 ">=4R | >=2R | >0 | sumR | meanR | open_at_horizon(mark>=4R) | >=4R @09:36")
    for s in order:
        sub = [x for x in out_rows if x["set"] == s]
        if not sub:
            continue
        st = Counter(x["status_0931"] for x in sub)
        settled = [x for x in sub if x["status_0931"] == "settled"]
        R = [x["realized_r_0931"] for x in settled if x["realized_r_0931"] is not None]
        oah = [x for x in sub if x["status_0931"] == "open_at_horizon"]
        oah4 = sum(1 for x in oah if (x["mark_r_0931"] or 0) >= 4)
        ge4_36 = sum(1 for x in sub if x["status_0936"] == "settled" and (x["realized_r_0936"] or 0) >= 4)
        nobars = sum(1 for x in sub if x["status_0931"] == "abstain" and x["reason_0931"] == "no_minute_bars_fetched")
        lines.append(f"{s} | {len(sub)} | {st['excluded_artifact']} | {nobars} | {st['abstain'] - nobars} | "
                     f"{st['no_trade']} | {st['no_entry']} | {sum(1 for x in sub if x['entered_0931'])} | "
                     f"{len(R)} | {sum(1 for x in R if x >= 4)} | {sum(1 for x in R if x >= 2)} | "
                     f"{sum(1 for x in R if x > 0)} | {sum(R):+.1f} | "
                     f"{(statistics.mean(R) if R else 0):+.2f} | {len(oah)}({oah4}) | {ge4_36}")
        ab = Counter((x["reason_0931"] or "").split(":")[0] for x in sub if x["status_0931"] == "abstain")
        nt = Counter((x["reason_0931"] or "").split(":")[0] for x in sub if x["status_0931"] == "no_trade")
        lines.append(f"    abstain reasons: {dict(ab)}   no_trade reasons: {dict(nt)}")
        top = sorted(settled, key=lambda x: -(x["realized_r_0931"] or -9))[:8]
        lines.append("    top settled: " + ", ".join(
            f"{x['ticker']} {x['trade_date']} {x['realized_r_0931']:+.2f}R(gap {x['cap_gap']:.1f})" for x in top))
        if oah:
            lines.append("    open_at_horizon marks: " + ", ".join(
                f"{x['ticker']} {x['trade_date']} mark {x['mark_r_0931']:+.2f}R" for x in
                sorted(oah, key=lambda x: -(x['mark_r_0931'] or -9))[:6]))
    # every >=4R or >=2R settled winner anywhere, with its set
    win = [x for x in out_rows if x["status_0931"] == "settled" and (x["realized_r_0931"] or 0) >= 2]
    lines.append("\nALL settled >=2R winners (set, ticker, date, capture gap, entry, stop, R, final):")
    for x in sorted(win, key=lambda x: -x["realized_r_0931"]):
        lines.append(f"  {x['set']:28s} {x['ticker']:6s} {x['trade_date']} gap {x['cap_gap']:6.1f}  "
                     f"entry {x['entry_px_0931']:.2f} stop {x['stop_0931']:.2f}  {x['realized_r_0931']:+.2f}R  {x['final_0931']}")
    art = [x for x in out_rows if x["artifact"]]
    lines.append(f"\nARTIFACTS excluded: {len(art)} — " + ", ".join(
        f"{x['ticker']} {x['trade_date']} ({x['art_reason']})" for x in art[:25]) + (" ..." if len(art) > 25 else ""))
    lines.append(f"failed fetch chunks: {failed[:5]}")
    txt = "\n".join(lines)
    (HERE / "_617_replay_summary.txt").write_text(txt + "\n")
    print(txt)


if __name__ == "__main__":
    main()
