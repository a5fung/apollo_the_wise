"""#697 item 2, the DEEPER replay ($0, offline): what would the SHIPPED detector say about the names the new carry
ADDS to the scan?  Inputs are captured files only (q1_admit_replay.out extras, q6_extra_bars.out bars + stored rows).

For every (night D, ticker) the q1 replay lists as an extra (D >= 2026-08-04, the lookback sits wholly inside the
06-27 rule), run the real `compute_flag_metrics` over the ticker's bars up to D. Approximation, stated: no stored
prior pivot and no yesterday stage are available for a name that had no row, so the pivot is re-derived from the
lookback and the hysteresis is off (raw stage). VALIDATION first: the same call on (D, ticker) pairs that DO have a
stored, un-held row, compared with the stored stage - if the offline call does not reproduce the stored stage the
extras' numbers mean nothing.
Run from the repo root:  PYTHONPATH=. python scripts/probes/_697/replay_extras.py"""
import collections
import os
from datetime import date

from agents.market_intelligence import flag_detector as fd

HERE = os.path.dirname(os.path.abspath(__file__))
bars: dict[str, list[dict]] = collections.defaultdict(list)
stored: dict[tuple[str, str], tuple[str, str, str]] = {}
for ln in open(os.path.join(HERE, "q6_extra_bars.out")):
    p = ln.rstrip("\n").split("\t")
    if p[0] == "bar":
        _, t, d, o, h, lo, c, v = p
        bars[t].append({"trade_date": date.fromisoformat(d), "open_price": float(o), "high_price": float(h),
                        "low_price": float(lo), "close": float(c), "volume": float(v) if v else 0.0})
    elif p[0] == "row":
        _, t, d, stage, held, reason, *_ = p
        stored[(t, d)] = (stage, held, reason)

extras = []
for ln in open(os.path.join(HERE, "q1_admit_replay.out")):
    p = ln.rstrip("\n").split("\t")
    if p[0] == "extra" and p[1] >= "2026-08-04":
        extras.append((p[1], p[2], p[3]))                  # D, ticker, class


def raw(t: str, d: str):
    hist = [r for r in bars[t] if r["trade_date"] <= date.fromisoformat(d)][-fd._HISTORY_DAYS:]
    if len(hist) < 60 or hist[-1]["trade_date"] != date.fromisoformat(d):
        return None
    return fd.compute_flag_metrics(hist, ticker=t, yesterday_stage=None, recent_stages=[])


# ── 1. VALIDATION on pairs that have a stored, un-held row ──────────────────────────────────────
agree = tot = 0
mism = collections.Counter()
for (t, d), (stage, held, reason) in sorted(stored.items()):
    if d < "2026-08-04" or held:
        continue
    m = raw(t, d)
    if m is None:
        continue
    tot += 1
    if m["stage"] == stage:
        agree += 1
    else:
        mism[(stage, m["stage"])] += 1
print(f"VALIDATION: offline raw stage reproduces the stored un-held stage on {agree} of {tot} pairs "
      f"({100 * agree / max(tot, 1):.1f}%)")
for (a, b), n in mism.most_common(8):
    print(f"   stored {a} -> offline {b}: {n}")

# ── 2. the EXTRAS ───────────────────────────────────────────────────────────────────────────────
print()
by_stage = collections.Counter()
by_cls_stage: dict[str, collections.Counter] = collections.defaultdict(collections.Counter)
unq = collections.Counter()
pushable_nights: dict[str, list[str]] = collections.defaultdict(list)
skipped = 0
for d, t, cls in extras:
    m = raw(t, d)
    if m is None:
        skipped += 1
        continue
    st = m["stage"]
    by_stage[st] += 1
    by_cls_stage[cls][st] += 1
    if st == "unqualified":
        unq[(m.get("reason") or "?").split("_")[0].split(":")[0]] += 1
    if st in ("TIGHTENING", "COILED", "TRIGGERED"):
        pushable_nights[d].append(f"{t}:{st}")
n = sum(by_stage.values())
print(f"EXTRAS replayed: {n} name-nights ({skipped} skipped: <60 bars or no bar on D) over "
      f"{len({d for d, _, _ in extras})} nights")
for st in ("TRIGGERED", "COILED", "TIGHTENING", "WATCH", "INVALIDATED", "unqualified"):
    print(f"   {st:12s} {by_stage[st]:5d}  ({100 * by_stage[st] / max(n, 1):.1f}%)")
print("   by admit class:")
for cls in ("trig5", "tight5", "watch5", "tight25"):
    c = by_cls_stage[cls]
    print(f"     {cls:8s} " + "  ".join(f"{s}={c[s]}" for s in
                                        ("TRIGGERED", "COILED", "TIGHTENING", "WATCH", "INVALIDATED", "unqualified")))
print("   why 'unqualified':", dict(unq.most_common(8)))
nights = sorted({d for d, _, _ in extras})
watch_up = collections.Counter()
for d, t, cls in extras:
    m = raw(t, d)
    if m and m["stage"] in ("WATCH", "TIGHTENING", "COILED", "TRIGGERED"):
        watch_up[d] += 1
vals = sorted(watch_up.get(d, 0) for d in nights)
print(f"   extras reading WATCH-or-better per night: median={vals[len(vals) // 2]} max={vals[-1]} "
      f"(these are the rows that EXTEND the carry and appear on the board)")
print(f"   nights with >=1 extra reading TIGHTENING / COILED / TRIGGERED (raw): {len(pushable_nights)} of {len(nights)}")
for d in sorted(pushable_nights):
    print(f"     {d}: {' '.join(pushable_nights[d])}")
