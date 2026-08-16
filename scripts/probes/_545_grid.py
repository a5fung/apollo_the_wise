"""#545 — the permutation grid, deliberately COARSE. (2026-08-16)

Operator: "we need to manage more and more variables to see what is the winning
combination without overfitting."

OBJECTIVE (plan §2026-08-16, pre-registered — NOT mean R):
    maximise  P(catch a >=5R move) x its size,  subject to bounded cost per attempt.
    Ranked on CATCH-RATE first, total R second. Mean-R rewards clipping winners.

5 binary axes = 32 cells, chosen coarse ON PURPOSE: ~1,000 cells against 75
reconstructed trades would fit noise. Each axis already has a single-variable result.

OVERFITTING DEFENCE: the cohort is split by TIME (earlier half = fit, later half =
verify). A cell that wins in-sample and dies out-of-sample is noise, and is labelled.

⚠ READ-ONLY, reconstructed not lived. THE LINE: measured only, nothing proposed.
"""
from collections import defaultdict
from pathlib import Path
import _468_moderate_realized_r as M
import _ext_live_exit_replay as X

H = Path(".").resolve()
M.COHORT, M.DAILY, M.MINUTE = H / "_468_cohort.tsv", H / "_468_daily.tsv", H / "_468_minute.tsv"
ORB5_END = M.RTH_OPEN + 5


def orb_levels(rth, five_min):
    """(high, low) of the entry range: first 1-min bar, or the 9:30-9:35 aggregate."""
    if five_min:
        bars = [b for b in rth if M.RTH_OPEN <= b["m"] < ORB5_END]
        return (max(b["h"] for b in bars), min(b["l"] for b in bars)) if bars else (None, None)
    bars = [b for b in rth if M.RTH_OPEN <= b["m"] < M.ORB_FETCH_END]
    return (bars[0]["h"], bars[0]["l"]) if bars else (None, None)


def one_attempt(rth, db, i, hi, lo, scan_from, **kw):
    """Fill at the trigger then hand off to the shared exit simulator. Returns (R, stop_m)."""
    limit = M.stop_limit_buy_price(hi)
    fill_px = fill_i = None
    for j, b in enumerate(rth):
        if b["m"] < max(scan_from, ORB5_END if kw.pop("_f5", False) else 0):
            continue
        if b["m"] >= M.FILL_END:
            break
        if b["h"] >= hi:
            fill_px, fill_i = (hi if b["o"] <= hi else b["o"] if b["o"] <= limit else None), j
            if fill_px is None:
                continue
            break
    if fill_px is None or fill_px - lo <= 0:
        return None, None
    after = [b for b in rth[fill_i:]]
    r = X.simulate(fill_px, lo, after, db[i + 1:], [b["c"] for b in db[:i]], **kw)
    stop_m = next((b["m"] for b in after if b["l"] <= lo), None)
    return r, stop_m


rows = [r for r in M.load_cohort() if r["tier"] == "HIGH"]
daily, minute = M.load_daily(), M.load_minute()
cells = {}
for five in (False, True):
    for retries in (1, 2):
        for be in (True, False):
            for closing in (False, True):
                for trail in (True, False):
                    cells[(five, retries, be, closing, trail)] = []

dates = sorted({r["alert_date"] for r in rows})
split = dates[len(dates) // 2] if dates else None

for r in rows:
    why, sub = M.eligibility(r)
    if why != "ok":
        continue
    db = daily.get(r["ticker"], [])
    i = M.idx_of_date(db, r["alert_date"])
    raw = minute.get((r["ticker"], r["alert_date"]), [])
    if i is None or not raw:
        continue
    rth = M.de.polygon_to_rth_minutes(raw, r["alert_date"])
    if not rth:
        continue
    atr = M.atr14_prior_close(db, i)
    for key in cells:
        five, retries, be, closing, trail = key
        hi, lo = orb_levels(rth, five)
        if hi is None or lo is None:
            continue
        ok, _ = M.validate_orb_entry(hi, lo, atr)
        if not ok:
            continue
        kw = dict(use_partial=True, use_trail=trail,
                  be_delay_days=0 if be else 9999,
                  be_close_basis=closing, hard_close_basis=closing)
        tot, scan, n = 0.0, sub, 0
        while n < retries:
            rr, stop_m = one_attempt(rth, db, i, hi, lo, scan, **dict(kw))
            if rr is None:
                break
            tot += rr
            n += 1
            if rr > -0.99 or stop_m is None:
                break
            scan = stop_m + 1
        if n:
            cells[key].append((r["alert_date"], tot))

def score(vals):
    rs = [v for _, v in vals]
    if not rs:
        return None
    catch5 = 100.0 * sum(1 for x in rs if x >= 5) / len(rs)
    return dict(n=len(rs), catch5=catch5, catch2=100.0 * sum(1 for x in rs if x >= 2) / len(rs),
                total=sum(rs), mx=max(rs), med=M._median(rs))

print(f"cohort HIGH={len(rows)}  cells={len(cells)}  time split at {split}")
print(f"{'entry':<6}{'try':<4}{'BE':<4}{'close':<6}{'trail':<6} | {'n':>3} {'catch5%':>8} {'catch2%':>8} "
      f"{'totalR':>8} {'maxR':>7} | OOS catch5% / totalR")
ranked = []
for key, vals in cells.items():
    s = score(vals)
    if not s or s["n"] < 30:
        continue
    oos = score([v for v in vals if v[0] >= split])
    ranked.append((s["catch5"], s["total"], key, s, oos))
for c5, tot, key, s, oos in sorted(ranked, reverse=True)[:12]:
    five, retries, be, closing, trail = key
    print(f"{'5min' if five else '1min':<6}{retries:<4}{'Y' if be else 'N':<4}"
          f"{'Y' if closing else 'N':<6}{'Y' if trail else 'N':<6} | {s['n']:>3} {s['catch5']:>8.1f} "
          f"{s['catch2']:>8.1f} {s['total']:>8.1f} {s['mx']:>7.2f} | "
          f"{(f'{oos['catch5']:.1f} / {oos['total']:+.1f}' if oos else 'n/a')}")
