"""#623 — realized-R replay for the FULL EP-candidate population (every scored + rejected
ticker-day in mi_ep_scan_log since minute-bar coverage begins, 2026-06-08), not just the
sub-$500M rejected cohort #622 covered. Same walker, same rule-set, same abstain discipline
as #617/#622: scripts.ep_replay.walk_campaign, rule-set "current" (era C).

`python scripts/ep_replay.py validate` -> PASS captured in _623_validate_out.txt (2026-09-04)
BEFORE any number here was read.

Bar sources (both real, no synthesis):
  - mi_intraday_bars directly for the 1059 ticker-days already stored (_623_have_minute_bars_out.txt)
  - Alpaca SIP day-0 RTH bars, $0 (Algo Trader Plus subscription), for the other 2399
    ticker-days mi_intraday_bars never captured (_623_bars.psv.gz, _623_fetch_bars.py)
  - mi_daily_closes for every session AFTER day 0 (the exit ladder walks off daily bars only,
    per ep_replay.walk_campaign's own contract) -- _623_daily_bars_out.txt

Same split-artifact guard as _622_replay.py (|daily_open/raw_0930_open - 1| > 5% -> excluded).

Usage: python scripts/probes/_623_replay.py -> _623_replay_out.tsv + _623_replay_summary.txt
"""
from __future__ import annotations

import csv
import gzip
import re
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

ep.LAST_SETTLED = date(2026, 9, 3)      # last COMPLETE daily session in the capture
SPLIT_DIVERGENCE_ABS_PCT = 0.05
DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


def load_population(path: Path) -> list[dict]:
    with open(path) as fh:
        reader = csv.DictReader(fh, delimiter="|")
        return [r for r in reader if r.get("ticker") and not r["ticker"].startswith("(")]


def load_minutes_from_psv(path: Path, minutes: dict) -> int:
    n = 0
    with open(path) as fh:
        for line in fh:
            line = line.rstrip("\n")
            if not line or line.startswith("ticker|") or line.startswith("("):
                continue
            p = line.split("|")
            if len(p) != 7:
                continue
            try:
                dt = datetime.strptime(p[1], "%Y-%m-%d %H:%M:%S").replace(tzinfo=_ET)
            except ValueError:
                dt = datetime.strptime(p[1], "%Y-%m-%d %H:%M").replace(tzinfo=_ET)
            minutes[(p[0], dt.date())].append(
                {"m": dt, "o": float(p[2]), "h": float(p[3]), "l": float(p[4]), "c": float(p[5])})
            n += 1
    return n


def load_minutes_from_gz(path: Path, minutes: dict) -> int:
    n = 0
    with gzip.open(path, "rt") as fh:
        section = None
        for line in fh:
            line = line.rstrip("\n")
            if line.startswith("==="):
                section = line
                continue
            if section != "=== MIN ===" or line.startswith("ticker|") or line.startswith("#FAILED"):
                continue
            p = line.split("|")
            if len(p) != 7:
                continue
            dt = datetime.strptime(p[1], "%Y-%m-%d %H:%M").replace(tzinfo=_ET)
            minutes[(p[0], dt.date())].append(
                {"m": dt, "o": float(p[2]), "h": float(p[3]), "l": float(p[4]), "c": float(p[5])})
            n += 1
    return n


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
    pop = load_population(HERE / "_623_population_raw.psv")
    minutes: dict = defaultdict(list)
    n1 = load_minutes_from_psv(HERE / "_623_have_minute_bars_out.txt", minutes)
    n2 = load_minutes_from_gz(HERE / "_623_bars.psv.gz", minutes)
    for bars in minutes.values():
        bars.sort(key=lambda b: b["m"])
    daily = load_daily(HERE / "_623_daily_bars_out.txt")
    print(f"loaded: {len(pop)} population rows, minute bars {n1}+{n2}={n1+n2} "
          f"({len(minutes)} ticker-days), daily tickers {len(daily)}")
    rs = get_ruleset("current")

    out_rows = []
    for r in pop:
        t, d = r["ticker"], date.fromisoformat(r["scan_date"])
        if d >= date(2026, 9, 4):
            continue  # live/incomplete session, excluded from R stats per pre-registration
        bars0 = minutes.get((t, d), [])
        n_min = len(bars0)
        orb930 = next((b for b in bars0 if b["m"].time() == time(9, 30)), None)
        daily_open = (daily.get(t, {}).get(d) or {}).get("o")
        artifact, art_reason = False, ""
        if orb930 is not None and daily_open:
            div = abs(daily_open / orb930["o"] - 1)
            if div > SPLIT_DIVERGENCE_ABS_PCT:
                artifact, art_reason = True, f"daily_open {daily_open:.2f} vs raw_0930 {orb930['o']:.2f} ({div:.0%})"
        base = {"ticker": t, "scan_date": r["scan_date"], "n_min_bars": n_min,
                "has_930": orb930 is not None, "artifact": artifact, "art_reason": art_reason,
                "gap_pct": r["gap_pct"], "prev_close": r["prev_close"], "tick_dist_sec": r["tick_dist_sec"],
                "ever_scored": r["ever_scored"], "best_score_tier": r["best_score_tier"],
                "nearest_filter_reason": r["nearest_filter_reason"], "reject_stage": r["reject_stage"]}
        atr_14 = atr14_abs(daily.get(t, {}), d)
        if artifact:
            res = {"status": "excluded_artifact", "reason": art_reason}
        elif n_min == 0:
            res = {"status": "abstain", "reason": "no_minute_bars_in_db"}
        else:
            res = walk_campaign(ticker=t, alert_date=d, rs=rs, minutes=minutes, daily=daily,
                                submit=time(9, 31), atr_14=atr_14)
        base["status"] = res.get("status")
        base["reason"] = res.get("reason")
        base["entered"] = res.get("entered")
        base["entry_px"] = res.get("entry_px")
        base["stop"] = res.get("stop")
        base["target"] = res.get("target")
        base["realized_r"] = res.get("realized_r")
        base["mark_r"] = res.get("mark_r")
        base["final_reason"] = res.get("final_reason")
        base["partial_fired"] = res.get("partial_fired")
        out_rows.append(base)

    cols = list(out_rows[0].keys())
    with open(HERE / "_623_replay_out.tsv", "w") as fh:
        fh.write("\t".join(cols) + "\n")
        for x in out_rows:
            fh.write("\t".join("" if x[c] is None else str(x[c]) for c in cols) + "\n")

    lines = []
    st = Counter(x["status"] for x in out_rows)
    lines.append(f"TOTAL: {len(out_rows)} ticker-days")
    lines.append(f"status counts: {dict(st)}")
    settled = [x for x in out_rows if x["status"] == "settled"]
    R = [x["realized_r"] for x in settled if x["realized_r"] is not None]
    lines.append(f"settled: {len(settled)}, realized-R available: {len(R)}")
    if R:
        lines.append(f"sumR={sum(R):+.2f} meanR={statistics.mean(R):+.3f} medianR={statistics.median(R):+.3f} "
                     f">=4R:{sum(1 for x in R if x>=4)} >0:{sum(1 for x in R if x>0)} "
                     f"win_rate:{sum(1 for x in R if x>0)/len(R)*100:.0f}%")
    oah = [x for x in out_rows if x["status"] == "open_at_horizon"]
    lines.append(f"open_at_horizon (unrealized, excluded from sumR/meanR): {len(oah)}")
    art = [x for x in out_rows if x["artifact"]]
    lines.append(f"split-artifacts excluded: {len(art)}")
    nobars = sum(1 for x in out_rows if x["status"] == "abstain" and x["reason"] == "no_minute_bars_in_db")
    lines.append(f"abstain (no minute bars found even after fetch): {nobars}")
    ab = Counter((x["reason"] or "").split(":")[0] for x in out_rows if x["status"] == "abstain")
    nt = Counter((x["reason"] or "").split(":")[0] for x in out_rows if x["status"] == "no_trade")
    lines.append(f"abstain reasons: {dict(ab)}")
    lines.append(f"no_trade reasons: {dict(nt)}")
    # by scored vs rejected
    for coh, pred in (("ever_scored", lambda x: x["ever_scored"] == "t"),
                      ("rejected", lambda x: x["ever_scored"] != "t")):
        sub = [x for x in out_rows if pred(x)]
        sub_settled = [x for x in sub if x["status"] == "settled" and x["realized_r"] is not None]
        Rs = [x["realized_r"] for x in sub_settled]
        lines.append(f"  [{coh}] n={len(sub)} settled={len(Rs)} "
                     f"meanR={(statistics.mean(Rs) if Rs else 0):+.3f} sumR={(sum(Rs) if Rs else 0):+.2f}")
    txt = "\n".join(lines)
    (HERE / "_623_replay_summary.txt").write_text(txt + "\n")
    print(txt)


if __name__ == "__main__":
    main()
