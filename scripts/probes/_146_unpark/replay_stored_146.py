"""#146 UNPARK (2026-10-11) - replay the TRIGGERED gate on prod's STORED rows since 2026-09-29. $0, read-only.

Question: on which past scan days would the new licence (any TIGHTENING / COILED / TRIGGERED stored label in the 5
calendar days before the breakout, held labels counting) have written a TRIGGERED read that the shipped rule did not?

Method. For every stored mi_flag_candidates row on a scan date >= 2026-09-29 (q1_stored_rows.out: the live board that
night, 09-29 .. 10-09) the REAL `flag_detector.compute_flag_metrics` is run twice on the SAME inputs:
    shipped   _TRIGGER_LICENCE = (("COILED", "coiled"),)       - the one-line revert state
    new       _TRIGGER_LICENCE as shipped in this change        - COILED, TIGHTENING, TRIGGERED
Inputs are threaded from prod's OWN stored rows, mirroring the live queries exactly (not from the replay's own chain, so
there is no cascade: this is "what the new gate would have changed on that night given what prod had stored"):
    history          the last 262 bars ending on the scan date (db.get_recent_daily_history); >= 60 rows required
    yesterday stage  the most recent prior stored row within 5 CALENDAR days, + whether it was a hold (get_yesterday_flag_state)
    recent_stages    every stored row's stage within 5 calendar days, ascending                   (get_recent_flag_stages)
    prior pivot      the most recent prior stored row with a pivot within _PIVOT_CARRY_DAYS          (get_yesterday_flag_pivots)
    prior_failure    None (telemetry, never reaches `stage`)
Bars: q3_bars.tsv.gz (mi_daily_closes, 2025-09-01 on). Stored labels before 10-11 are the OLD re-arming-hold kind.

Validity (two-sided): the SHIPPED-rule run must reproduce prod's stored RAW read (held_from_stage when the row is a hold,
else stage) on the rows both have; rows prod demoted to `unqualified` by the M&A / deal-pin layer (reason mna_filter:*)
cannot be reproduced from bars and are counted apart.

Run:  PYTHONPATH=. python scripts/probes/_146_unpark/replay_stored_146.py > scripts/probes/_146_unpark/replay_stored_146.out
"""
from __future__ import annotations

import gzip
import os
import sys
from collections import Counter, defaultdict
from datetime import date, timedelta

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "..")))

from agents.market_intelligence import flag_detector as fd  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
FIRST = date(2026, 9, 29)
HIST = fd._HISTORY_DAYS
PIVOT_DAYS = fd._PIVOT_CARRY_DAYS
STATE_DAYS = 5
SHIPPED = (("COILED", "coiled"),)
NEW = fd._TRIGGER_LICENCE
assert NEW == (("COILED", "coiled"), ("TIGHTENING", "tightening"), ("TRIGGERED", "retrigger")), NEW


def load_rows():
    by_t = defaultdict(list)
    with open(os.path.join(HERE, "q1_stored_rows.out")) as fh:
        hdr = fh.readline().rstrip("\n").split("\t")
        for ln in fh:
            if ln.startswith("("):
                continue
            p = ln.rstrip("\n").split("\t")
            r = dict(zip(hdr, p))
            r["scan_date"] = date.fromisoformat(r["scan_date"])
            r["pivot_high_date"] = date.fromisoformat(r["pivot_high_date"]) if r.get("pivot_high_date") else None
            r["pivot_high_price"] = float(r["pivot_high_price"]) if r.get("pivot_high_price") else None
            r["held_from_stage"] = r.get("held_from_stage") or None
            by_t[r["ticker"]].append(r)
    for t in by_t:
        by_t[t].sort(key=lambda r: r["scan_date"])
    return by_t


def load_bars(fname="q3_bars.tsv.gz"):
    bars = defaultdict(list)
    with gzip.open(os.path.join(HERE, fname), "rt") as fh:
        hdr = fh.readline().rstrip("\n").split("\t")
        for ln in fh:
            if ln.startswith("("):
                continue
            p = ln.rstrip("\n").split("\t")
            if len(p) != 7:
                continue
            t, d, o, h, l, c, v = p
            if "" in (o, h, l, c):
                continue
            bars[t].append({"trade_date": date.fromisoformat(d), "open_price": float(o), "high_price": float(h),
                            "low_price": float(l), "close": float(c), "volume": float(v) if v else 0.0})
    for t in bars:
        bars[t].sort(key=lambda r: r["trade_date"])
    return bars


def score(rows, ticker, window, prior_pivot, licence):
    fd._TRIGGER_LICENCE = licence
    y_stage = window[-1]["stage"] if window else None
    y_held = bool(window[-1]["held_from_stage"]) if window else False
    return fd.compute_flag_metrics(
        rows, ticker=ticker, yesterday_stage=y_stage, yesterday_was_held=y_held,
        recent_stages=[w["stage"] for w in window],
        prior_pivot_date=prior_pivot[0] if prior_pivot else None,
        prior_pivot_high=prior_pivot[1] if prior_pivot else None,
        prior_failure=None,
    )


def replay(stored, bars, first, only=None):
    n = Counter()
    mism = []
    gains = []
    per_date = defaultdict(Counter)
    for ticker, rows_t in sorted(stored.items()):
        if only is not None and ticker not in only:
            continue
        tb = bars.get(ticker)
        if not tb:
            n["no_bars"] += 1
            continue
        dates = [b["trade_date"] for b in tb]
        for r in rows_t:
            d = r["scan_date"]
            if d < first:
                continue
            n["stored_rows_replayed_scope"] += 1
            if d not in dates:
                n["no_bar_on_scan_date"] += 1
                continue
            hi = dates.index(d) + 1
            hist = tb[max(0, hi - HIST):hi]
            if len(hist) < 60:
                n["history_lt_60"] += 1
                continue
            cutoff = d - timedelta(days=STATE_DAYS)
            window = [x for x in rows_t if cutoff <= x["scan_date"] < d]
            pcut = d - timedelta(days=PIVOT_DAYS)
            ppiv = next(((x["pivot_high_date"], x["pivot_high_price"]) for x in reversed(rows_t)
                         if pcut <= x["scan_date"] < d and x["pivot_high_date"] is not None
                         and x["pivot_high_price"] is not None), None)
            old = score(hist, ticker, window, ppiv, SHIPPED)
            new = score(hist, ticker, window, ppiv, NEW)
            n["replayed"] += 1
            # validity: shipped rule vs the stored RAW read
            stored_raw = r["held_from_stage"] or r["stage"]
            old_raw = old["held_from_stage"] or old["stage"]
            if (r["reason"] or "").startswith("mna_filter:"):
                n["mna_demoted_not_comparable"] += 1
            else:
                n["comparable"] += 1
                if stored_raw == old_raw and r["stage"] == old["stage"]:
                    n["shipped_reproduces_stored_stage_and_raw"] += 1
                else:
                    # classify WHY the shipped-rule replay differs from prod's stored row: both causes are code eras that
                    # predate today's code, not the licence (which is the same in both runs). Target for OTHER: 0.
                    prev = window[-1] if window else None
                    if r["held_from_stage"] and prev and prev["held_from_stage"]:
                        cls = "old_rearming_hold(#697-item5)"
                    elif d < date(2026, 9, 8):
                        cls = "pre_592_anchor_era"
                    else:
                        cls = "OTHER"
                    n["mismatch_" + cls] += 1
                    mism.append((d, ticker, r["stage"], r["held_from_stage"], old["stage"], old["held_from_stage"], cls))
                if r["stage"] == "TRIGGERED" and r["held_from_stage"] is None:
                    n["stored_raw_triggered"] += 1
                    n["stored_raw_triggered_reproduced"] += int(old["stage"] == "TRIGGERED" and old["held_from_stage"] is None)
            # the diff
            old_trig = old["stage"] == "TRIGGERED" and old["held_from_stage"] is None
            new_trig = new["stage"] == "TRIGGERED" and new["held_from_stage"] is None
            if old_trig:
                n["shipped_raw_triggered"] += 1
                per_date[d]["shipped"] += 1
            if new_trig:
                n["new_raw_triggered"] += 1
                per_date[d]["new"] += 1
            if new_trig and not old_trig:
                gains.append({
                    "date": d, "ticker": ticker, "from": new["triggered_from"],
                    "vol_x": new["breakout_volume_ratio"], "close": new["breakout_close"],
                    "base_high": new["base_high"], "base_age": new["base_age"],
                    "stored_stage": r["stage"], "stored_held_from": r["held_from_stage"] or "",
                    "old_replayed_stage": f"{old['stage']}{'*' if old['held_from_stage'] else ''}",
                    "window": ",".join(f"{x['stage']}{'*' if x['held_from_stage'] else ''}" for x in window),
                    "mna": (r["reason"] or "").startswith("mna_filter:"),
                })
            # nothing else may differ between the two runs: the new licence touches only the TRIGGERED test
            if not new_trig and not old_trig:
                for k in ("stage", "held_from_stage", "reason", "triggered_from"):
                    if old[k] != new[k]:
                        n["UNEXPECTED_diff_outside_triggered"] += 1
            if old_trig and new_trig:
                for k in ("breakout_close", "breakout_volume_ratio", "reason", "base_high"):
                    if old[k] != new[k]:
                        n["UNEXPECTED_diff_on_shared_triggered"] += 1
                if old["triggered_from"] != new["triggered_from"]:
                    n["UNEXPECTED_bucket_diff_on_shared_triggered"] += 1

    return n, mism, gains, per_date


def main():
    stored = load_rows()
    bars = load_bars()
    n, mism, gains, per_date = replay(stored, bars, FIRST)
    print("# #146 unpark - gate replay on prod's stored rows, scan dates >= 2026-09-29")
    print(f"# scan dates covered: {sorted({d for d in per_date} | {r['scan_date'] for t in stored.values() for r in t if r['scan_date'] >= FIRST})[0]} .. "
          f"{max(r['scan_date'] for t in stored.values() for r in t)}")
    for k, v in sorted(n.items()):
        print(f"{k}\t{v}")
    print("\n# shipped rule vs stored: rows where the shipped-rule replay does NOT reproduce prod's stored stage + raw read")
    for m in mism[:40]:
        print("MISMATCH", *m)
    print(f"# mismatches: {len(mism)} of {n['comparable']} comparable rows")
    print("\n# GAINS: raw TRIGGERED reads the new licence adds on the stored rows (date, ticker, bucket, volume, ...)")
    print("date\tticker\ttriggered_from\tvol_x\tclose\tbase_high\tbase_age\tstored_stage\tstored_held_from\told_replayed\tstored_window\tmna_demoted")
    for g in sorted(gains, key=lambda g: (g["date"], g["ticker"])):
        print("\t".join(str(x) for x in (g["date"], g["ticker"], g["from"],
                                         f"{g['vol_x']:.2f}" if g["vol_x"] else "", f"{g['close']:.2f}" if g["close"] else "",
                                         f"{g['base_high']:.2f}" if g["base_high"] else "", g["base_age"], g["stored_stage"],
                                         g["stored_held_from"], g["old_replayed_stage"], g["window"], g["mna"])))
    print(f"# gains: {len(gains)}  by bucket: {dict(Counter(g['from'] for g in gains))}  "
          f"on {len({g['date'] for g in gains})} distinct scan dates")
    print("\n# per scan date: raw TRIGGERED reads (shipped -> new)")
    all_dates = sorted({r['scan_date'] for t in stored.values() for r in t if r['scan_date'] >= FIRST})
    for d in all_dates:
        print(f"{d}\t{per_date[d]['shipped']}\t{per_date[d]['new']}")

    # POSITIVE CONTROL: the 09-29 .. 10-09 scope stored NO raw TRIGGERED read, so on its own it cannot show that the
    # shipped path still reproduces one. These four names carry every raw TRIGGERED read stored since 08-14.
    bars_c = load_bars("q6_bars_triggered.tsv.gz")
    ctl = set(bars_c)
    n2, mism2, gains2, per_date2 = replay(stored, bars_c, date(2026, 8, 14), only=ctl)
    print("\n# POSITIVE CONTROL - " + ", ".join(sorted(ctl)) + ", every stored row from 2026-08-14 (q6_bars_triggered)")
    for k, v in sorted(n2.items()):
        print(f"{k}\t{v}")
    for m in mism2[:40]:
        print("MISMATCH", *m)
    print(f"# mismatches: {len(mism2)} of {n2['comparable']} comparable rows")
    reads = []
    for t in sorted(ctl):
        for r in stored[t]:
            if r["scan_date"] >= date(2026, 8, 14) and r["stage"] == "TRIGGERED" and r["held_from_stage"] is None:
                reads.append((r["scan_date"], t))
    print("# stored raw TRIGGERED reads: " + ", ".join(f"{t} {d}" for d, t in sorted(reads)))
    print(f"# shipped rule reproduces {n2['stored_raw_triggered_reproduced']} of {n2['stored_raw_triggered']} of them")
    print("# new-rule gains inside the control names:", [(str(g['date']), g['ticker'], g['from']) for g in gains2] or "none")


if __name__ == "__main__":
    main()
