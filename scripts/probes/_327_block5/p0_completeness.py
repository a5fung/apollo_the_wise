"""Block 5 / P0 — bar-completeness + abstain-rate + day-0 minute-hole read.

$0, read-only. Consumes the flat CSVs extract_p0.sh pulled from prod (trigger.csv,
daily_closes.csv, intraday_day0_coverage.csv). Uses the REAL `_trading_days` from
`agents.market_intelligence.delayed_entry_shadow` to enumerate each fire's forward
session calendar — never a re-derived trading-day rule.

Outputs scripts/probes/_327_block5/p0_summary.json (small, committed) and prints the
pass-bar verdict to stdout.
"""
import csv
import json
import sys
from collections import defaultdict
from datetime import date, datetime
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO_ROOT))
from agents.market_intelligence.delayed_entry_shadow import _trading_days  # real code, not re-derived

HERE = Path(__file__).parent
TODAY = date(2026, 9, 26)  # operator_now.py is PT-facing; this is the ET trading calendar's "today" for session enumeration


def _d(s):
    return date.fromisoformat(s) if s else None


def _f(s):
    if s is None or s == "":
        return None
    try:
        return float(s)
    except ValueError:
        return None


def load_triggers():
    rows = []
    with open(HERE / "trigger.csv", newline="") as fh:
        for r in csv.DictReader(fh):
            r["fire_date"] = _d(r["fire_date"])
            r["ep_date"] = _d(r["ep_date"])
            r["entry_price"] = _f(r["entry_price"])
            r["stop_price"] = _f(r["stop_price"])
            r["day_low"] = _f(r["day_low"])
            r["realized_r"] = _f(r["realized_r"])
            r["fire_minute_et"] = int(r["fire_minute_et"]) if r.get("fire_minute_et") else None
            rows.append(r)
    return rows


def load_daily_closes():
    by_ticker = defaultdict(dict)
    with open(HERE / "daily_closes.csv", newline="") as fh:
        for r in csv.DictReader(fh):
            d = _d(r["trade_date"])
            by_ticker[r["ticker"]][d] = {
                "high_price": _f(r["high_price"]),
                "low_price": _f(r["low_price"]),
                "close": _f(r["close"]),
            }
    return by_ticker


def load_intraday_coverage():
    cov = {}
    with open(HERE / "intraday_day0_coverage.csv", newline="") as fh:
        for r in csv.DictReader(fh):
            cov[(r["ticker"], _d(r["fire_date"]))] = int(r["n_bars"] or 0)
    return cov


def complete(bar):
    return bool(bar) and bar["high_price"] is not None and bar["low_price"] is not None and bar["close"] is not None


def day0_needs_minutes(fire_minute, day_low, stop):
    return fire_minute is not None and day_low is not None and stop is not None and day_low <= stop


def main():
    triggers = load_triggers()
    daily = load_daily_closes()
    cov = load_intraday_coverage()

    settled = [t for t in triggers if t["realized_r"] is not None]
    n_settled = len(settled)
    print(f"total trigger rows: {len(triggers)}  settled (realized_r not null): {n_settled}")

    # clock population: fires whose 20th forward session has already occurred (session
    # calendar computed from fire_date, independent of settle status) — the
    # non-survivorship comparison the P3 population trap names.
    clock_eligible = []
    for t in triggers:
        sessions = _trading_days(date.fromordinal(t["fire_date"].toordinal() + 1), TODAY)
        if len(sessions) >= 20:
            clock_eligible.append(t)
    print(f"clock-eligible (>=20 forward sessions elapsed by {TODAY}): {len(clock_eligible)}")

    def completeness_table(pop, label):
        """cumulative-complete %, marginal-missing %, first-hole hazard % per session
        1..20 — each denominated on fires whose session k has actually OCCURRED on the
        calendar by TODAY (`observable_n[k]`), never on the fixed population size. A
        fire fired 3 sessions ago has no session-20 bar to be missing yet — that is
        "not yet happened", not a hole, and must not deflate the s20 read."""
        n = len(pop)
        cum_complete_n = [0] * 21      # fires with sessions 1..k ALL complete, of those observable at k
        marginal_missing_n = [0] * 21  # fires missing exactly at session k, of those observable at k
        observable_n = [0] * 21        # fires whose session k has occurred by TODAY
        hazard_denom = [0] * 21        # fires clean through k-1 AND observable at k (at risk of a first hole at k)
        hazard_num = [0] * 21          # of those, missing at k
        for t in pop:
            sessions = _trading_days(date.fromordinal(t["fire_date"].toordinal() + 1), TODAY)[:20]
            bars = daily.get(t["ticker"], {})
            clean_so_far = True
            for k in range(1, 21):
                if k > len(sessions):
                    continue  # session k has not happened yet — unobservable, excluded at this k
                observable_n[k] += 1
                b = bars.get(sessions[k - 1])
                ok = complete(b)
                if not ok:
                    marginal_missing_n[k] += 1
                if clean_so_far:
                    hazard_denom[k] += 1
                    if not ok:
                        hazard_num[k] += 1
                        clean_so_far = False
                if clean_so_far:
                    cum_complete_n[k] += 1
        out = {}
        for k in range(1, 21):
            obs = observable_n[k]
            out[k] = {
                "observable_n": obs,
                "cum_complete_pct": round(100 * cum_complete_n[k] / obs, 2) if obs else None,
                "marginal_missing_pct": round(100 * marginal_missing_n[k] / obs, 2) if obs else None,
                "hazard_pct": round(100 * hazard_num[k] / hazard_denom[k], 2) if hazard_denom[k] else None,
                "hazard_denom": hazard_denom[k],
            }
        print(f"\n{label} (n={n}) — cum-complete% / marginal-missing% / first-hole-hazard%  "
              "(each %'s denominator = fires whose session k has occurred by today):")
        for k in (1, 2, 3, 5, 10, 15, 20):
            row = out[k]
            print(f"  s{k:>2}: cum={row['cum_complete_pct']:>6}%  marg_miss={row['marginal_missing_pct']:>6}%  "
                  f"hazard={row['hazard_pct']}%  (observable_n={row['observable_n']}, hazard_at_risk={row['hazard_denom']})")
        return out, n

    settled_table, n_settled_used = completeness_table(settled, "SETTLED fires")
    clock_table, n_clock_used = completeness_table(clock_eligible, "CLOCK-ELIGIBLE fires (>=20 sessions elapsed, any settle status)")

    # ── day-0 minute-bar hole count ──
    needs_min_settled = [t for t in settled if day0_needs_minutes(t["fire_minute_et"], t["day_low"], t["stop_price"])]
    needs_min_all = [t for t in triggers if day0_needs_minutes(t["fire_minute_et"], t["day_low"], t["stop_price"])]

    def hole_stats(pop, label):
        n = len(pop)
        n_hole = sum(1 for t in pop if cov.get((t["ticker"], t["fire_date"]), 0) == 0)
        pct = round(100 * n_hole / n, 2) if n else None
        print(f"{label}: n={n}, no day-0 minute bars in mi_intraday_bars: {n_hole} ({pct}%)")
        return {"n": n, "n_hole": n_hole, "pct_hole": pct}

    print()
    settled_min_holes = hole_stats(needs_min_settled, "SETTLED fires needing day-0 minutes")
    all_min_holes = hole_stats(needs_min_all, "ALL fires (settled+open) needing day-0 minutes")
    no_min_needed = len(settled) - len(needs_min_settled)
    print(f"SETTLED fires that never needed day-0 minutes (daily-grade fire, or day_low > stop): {no_min_needed}")

    # ── PASS BAR / KILL, applied exactly, on SETTLED fires (as the block text names) ──
    s10 = settled_table[10]["cum_complete_pct"]
    s20 = settled_table[20]["cum_complete_pct"]
    if s10 is None:
        verdict = "KILL"
        note = "no settled population to evaluate"
    elif s10 < 70:
        verdict = "KILL"
        note = f"s10 cum-complete {s10}% < 70% — daily grain cannot do this"
    elif s10 < 90:
        verdict = "MOVE_CHECKPOINT_S5"
        note = f"s10 cum-complete {s10}% in [70,90) — primary checkpoint moves to s5 per the pre-registered rule"
    elif s20 is not None and s20 >= 80:
        verdict = "PASS"
        note = f"s10={s10}% >=90 and s20={s20}% >=80 — bar clears, checkpoint stays s10"
    else:
        verdict = "PASS_S10_ONLY"
        note = (f"s10={s10}% >=90 but s20={s20}% <80 — the letter of the bar does not "
                "cover this combination; reporting both numbers rather than inventing a rule")

    print(f"\nP0 VERDICT: {verdict} — {note}")

    summary = {
        "generated": datetime.now().isoformat(),
        "today_used_for_session_calendar": TODAY.isoformat(),
        "n_trigger_rows_total": len(triggers),
        "n_settled": n_settled,
        "n_clock_eligible": len(clock_eligible),
        "settled_completeness": settled_table,
        "clock_eligible_completeness": clock_table,
        "day0_minute_holes": {
            "settled_needing_minutes": settled_min_holes,
            "all_needing_minutes": all_min_holes,
            "settled_never_needing_minutes": no_min_needed,
        },
        "pass_bar": {
            "s10_cum_complete_pct": s10,
            "s20_cum_complete_pct": s20,
            "verdict": verdict,
            "note": note,
        },
    }
    with open(HERE / "p0_summary.json", "w") as fh:
        json.dump(summary, fh, indent=2)
    print(f"\nwrote {HERE / 'p0_summary.json'}")


if __name__ == "__main__":
    main()
