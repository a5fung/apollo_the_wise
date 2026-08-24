"""Render /scanned for 2026-08-24 + 2026-08-07 from the ONE prod capture
(_scanned_cmd_capture_out.tsv) through the REAL renderer. Read-only, $0."""
import csv, sys
from datetime import date, datetime, timezone
sys.path.insert(0, ".")
from agents.market_intelligence.scanned_report import render_scanned_day

def f(v):
    if v is None or v == "":
        return None
    return float(v)

def ts(v):
    if not v:
        return None
    if v.endswith("+00"):
        v += ":00"
    return datetime.fromisoformat(v)

days = {"2026-08-24": {"scan": [], "graded": [], "alerts": [], "trades": [], "outcomes": []},
        "2026-08-07": {"scan": [], "graded": [], "alerts": [], "trades": [], "outcomes": []}}

with open("scripts/probes/_scanned_cmd_capture_out.tsv") as fh:
    for row in csv.reader(fh, delimiter="\t"):
        q = row[0]
        if q in ("q",):  # repeated headers between COPY blocks
            continue
        d = row[1]
        if d not in days:
            continue
        if q == "scan":
            days[d]["scan"].append(dict(
                ticker=row[2], gap_pct=f(row[3]), prev_close=f(row[4]),
                rel_volume=f(row[5]), filter_reason=row[6] or None,
                ep_score=f(row[7]), score_tier=row[8] or None,
                catalyst_quality=row[9] or None, adv=f(row[10]),
                pm_rvol=f(row[11]), rank_by_gap=f(row[12])))
        elif q == "graded":
            days[d]["graded"].append(dict(
                ticker=row[2], live_tier=row[3] or None, live_ep_score=f(row[4]),
                live_quality_last=row[5] or None, gap_pct_last=f(row[6]),
                adv_dollar=f(row[7]), live_side=row[8] or None))
        elif q == "alert":
            days[d]["alerts"].append(dict(
                ticker=row[2], ep_score=f(row[3]), score_tier=row[4] or None,
                gap_pct=f(row[5]), catalyst_quality=row[6] or None))
        elif q == "trade":
            days[d]["trades"].append(dict(
                ticker=row[2], status=row[3] or None, skip_reason=row[4] or None,
                total_pnl=f(row[5]), account_mode=row[6] or None))
        elif q == "outcome":
            days[d]["outcomes"].append(dict(
                ticker=row[2], ret_1d=f(row[4]), ret_5d=f(row[5]),
                max_high_5d=f(row[6]), last_refreshed_at=ts(row[7])))

now = datetime(2026, 8, 24, 13, 0, tzinfo=timezone.utc)
for dstr in ("2026-08-24", "2026-08-07"):
    d = date.fromisoformat(dstr)
    print("=" * 64)
    print(render_scanned_day(d, days[dstr], now=now))
    print()
