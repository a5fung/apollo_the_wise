"""The operator's fork, measured: RE-ENTRY (many small cuts) vs NO INTRADAY STOP.

Operator 2026-08-16: "the alternative and maybe safer route is the reentry we've
tested… we want to latch on to the real winners but how to prevent being shaken out.
You're saying don't have intraday stops; the reentry is to keep the stops but just
reenter multiple times. The trade off is obvious: potentially many smaller cuts to
catch a winner but prevent disastrous downside in one swoop, vs no stop and take the
downside but avoid the paper cuts. We tried 2 tries; i often see ppl max out at 3."

RULES HELD IDENTICAL ACROSS ARMS so only the retry count varies:
  entry   = stop-limit buy triggered at the ORB high (the live trigger)
  stop    = ORB low, intraday touch (the live hard stop) — EXCEPT the no-stop arm
  +2R     = 1/3 out, then breakeven; SMA trail as live
  re-entry= after a stop-out, re-arm the SAME trigger; each attempt risks a fresh 1R
  horizon = 20 trading days

⚠ READ-ONLY. Reconstructed, not lived. Exit/entry discipline = THE LINE: measured only.
"""
from collections import defaultdict
from pathlib import Path
import _468_moderate_realized_r as M
import _ext_live_exit_replay as X

H = Path(".").resolve()
M.COHORT, M.DAILY, M.MINUTE = H / "_468_cohort.tsv", H / "_468_daily.tsv", H / "_468_minute.tsv"


def with_reentries(rth, sub, atr, db, i, max_attempts):
    """Total R across up to `max_attempts` sequential attempts on the same name/day."""
    total, scan_from, attempts = 0.0, sub, 0
    while attempts < max_attempts:
        rec = M.reconstruct(rth, scan_from, atr, db[i:])
        if rec.get("outcome") != "filled":
            break
        after = [b for b in rth if b["m"] >= rec["fill_minute"]]
        pc = [b["c"] for b in db[:i]]
        r = X.simulate(rec["entry"], rec["stop"], after, db[i + 1:], pc,
                       use_partial=True, use_trail=True)
        if r is None:
            break
        total += r
        attempts += 1
        if r > -0.99:                      # not stopped -> the attempt survived, stop here
            break
        # stopped: re-arm from the bar after the stop-out (same trigger, same stop)
        stopped_at = next((b["m"] for b in after if b["l"] <= rec["stop"]), None)
        if stopped_at is None:
            break
        scan_from = stopped_at + 1
    return total, attempts


rows = [r for r in M.load_cohort() if r["tier"] == "HIGH"]
daily, minute = M.load_daily(), M.load_minute()
arms = {"1 attempt (LIVE)": 1, "2 attempts": 2, "3 attempts": 3, "4 attempts": 4}
res, natt, sk = {k: [] for k in arms}, defaultdict(list), defaultdict(int)
nostop = []

for r in rows:
    why, sub = M.eligibility(r)
    if why != "ok":
        sk[why] += 1
        continue
    db = daily.get(r["ticker"], [])
    i = M.idx_of_date(db, r["alert_date"])
    raw = minute.get((r["ticker"], r["alert_date"]), [])
    if i is None or not raw:
        sk["no_bars"] += 1
        continue
    rth = M.de.polygon_to_rth_minutes(raw, r["alert_date"])
    if not rth:
        sk["no_rth"] += 1
        continue
    atr = M.atr14_prior_close(db, i)
    rec = M.reconstruct(rth, sub, atr, db[i:])
    if rec.get("outcome") != "filled":
        sk["outcome:" + str(rec.get("outcome"))] += 1
        continue
    for k, n in arms.items():
        tot, a = with_reentries(rth, sub, atr, db, i, n)
        res[k].append(tot)
        natt[k].append(a)
    after = [b for b in rth if b["m"] >= rec["fill_minute"]]
    v = X.simulate(rec["entry"], rec["stop"], after, db[i + 1:], [b["c"] for b in db[:i]],
                   use_partial=True, use_trail=True, be_close_basis=True, hard_close_basis=True)
    if v is not None:
        nostop.append(v)

print(f"HIGH cohort={len(rows)}  simulated={len(res['1 attempt (LIVE)'])}")
print("not simulated: " + ", ".join(f"{k}={v}" for k, v in sorted(sk.items())))


def line(label, s, att=None):
    s = sorted(s)
    if not s:
        return
    sh = lambda t: 100.0 * sum(1 for x in s if x >= t) / len(s)   # noqa: E731
    extra = f"  avg attempts {sum(att)/len(att):.2f}" if att else ""
    print(f"{label:<22} median {M._median(s):+.2f}R  mean {sum(s)/len(s):+.2f}R  "
          f"max {s[-1]:+.2f}R  min {s[0]:+.2f}R  SUM {sum(s):+.1f}R  |  "
          f">=2R {sh(2):.0f}%  >=5R {sh(5):.0f}%{extra}")


for k in arms:
    line(k, res[k], natt[k])
line("NO INTRADAY STOP", nostop)
