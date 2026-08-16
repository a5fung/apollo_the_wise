"""Extension cohort under OUR ACTUAL exit — and what the SMA trail costs. (2026-08-16)

Operator: *"make sure the stop rule is accurate as that is what will potentially cut
off winners and one of the issue we're running into or needed to tune potentially."*

The previous replay used `anticipation.SETTLE_RULE` (half out at +1R, half at +3R)
— the CONSOLIDATION track's harvest rule, inherited from the harness, not ours. It
caps at +2R and therefore cannot answer a fat-tail question.

THE REAL RULES, read from `broker/exit_logic.py` + `order_manager.scan_profit_triggers`:
  * entry     = stop-limit BUY triggered at the ORB high (limit = max(hi*1.005, hi+0.02))
  * hard stop = ORB low, a BROKER stop → exits on an intraday TOUCH
  * +2R       = take 1/3 at entry + 2*risk (intraday), then breakeven_active
  * ladder    = effective_stop = MAX(hard_stop, active_sma, entry if breakeven_active)
                giveback floor DEFAULT-OFF — the operator's "we let winners run"
  * trail     = default mode "sma": active_sma = MAX(SMA10, SMA20) over
                prior_closes + running_closes
  * trail exit= first daily CLOSE BELOW the effective stop (NOT an intraday touch);
                the hard stop keeps its intraday-touch semantics
  * horizon   = 20 trading days here (the replay's own bound, stated as such)

THREE ARMS, so the trail's cost is isolated rather than assumed:
  A  LIVE       — 1/3 at +2R, breakeven, SMA trail  (what we actually run)
  B  NO TRAIL   — 1/3 at +2R, breakeven, NO SMA trail
  C  RAW        — no partial, hard stop only, 20-day time stop

⚠ READ-ONLY, no prod writes, no orders. Extension is entry discipline = THE LINE:
this MEASURES and proposes nothing.
⚠ Reconstructed, not lived: fills assumed at the trigger, no slippage model, and
these are names we never entered so there is no fill evidence. Submission assumed
09:31 ET — the cohort is filtered BEFORE it becomes an alert, so no detection
timestamp exists (only 3 of 159 have an alert row).
"""
from __future__ import annotations

from collections import defaultdict
from pathlib import Path

import _468_moderate_realized_r as M

HERE = Path(__file__).resolve().parent
OUT = HERE.parent.parent / "docs" / "analysis" / "extension_live_exit_replay_2026-08-16.txt"
M.COHORT, M.DAILY, M.MINUTE = HERE / "_ext_cohort.tsv", HERE / "_ext_daily.tsv", HERE / "_ext_minute.tsv"
HORIZON = 20
PROFIT_R = 2.0
PARTIAL_FRAC = 1.0 / 3.0


def sma(closes, n):
    return sum(closes[-n:]) / n if len(closes) >= n else None


def simulate(entry, hard_stop, day0_after_fill, fwd, prior_closes, *, use_partial, use_trail,
             be_delay_days=0, be_close_basis=False, hard_close_basis=False, trace=None):
    """be_delay_days   — wait N trading days AFTER the +2R partial before moving to breakeven
                         (operator 2026-08-16: "giving it some time before moving to breakeven").
       be_close_basis  — the breakeven stop exits only on a daily CLOSE below entry, not an
                         intraday touch ("requiring stops to be breached on closing basis…
                         to avoid intraday moves").
       hard_close_basis— the same, applied to the ORB-low hard stop. ⚠ That is a REAL risk
                         change, not a bookkeeping one: it holds through an intraday breach.
       trace           — list to append a per-bar audit to (hand-check support).
    Returns realized R. day0_after_fill = minute bars from the fill onward;
    fwd = daily bars from day 1; prior_closes = daily closes BEFORE the alert day."""
    risk = entry - hard_stop
    if risk <= 0:
        return None
    target = entry + PROFIT_R * risk
    held, banked, stop, be = 1.0, 0.0, hard_stop, False
    partial_day = None            # trading-day index the partial fired (0 = day 0)

    def _log(*a):
        if trace is not None:
            trace.append(" ".join(str(x) for x in a))

    # --- day 0, minute by minute: the hard stop is a BROKER stop (intraday touch) ---
    for b in day0_after_fill:
        if not hard_close_basis and b["l"] <= stop:
            _log(f"day0 m={b['m']} low {b['l']:.2f} <= stop {stop:.2f} -> EXIT")
            return banked + held * (stop - entry) / risk
        if use_partial and partial_day is None and b["h"] >= target:
            banked += PARTIAL_FRAC * PROFIT_R
            held -= PARTIAL_FRAC
            partial_day = 0
            if be_delay_days == 0:            # live: breakeven moves the same instant
                be = True
                stop = max(stop, entry)
            _log(f"day0 m={b['m']} high {b['h']:.2f} >= target {target:.2f} -> 1/3 out, banked {banked:.2f}R")
    closes = list(prior_closes) + [day0_after_fill[-1]["c"]] if day0_after_fill else list(prior_closes)

    # --- days 1..HORIZON, daily ---
    for di, d in enumerate(fwd[:HORIZON], start=1):
        # breakeven arms only AFTER the configured delay has elapsed
        if use_partial and partial_day is not None and not be and be_delay_days > 0 \
                and (di - partial_day) >= be_delay_days:
            be = True
            stop = max(stop, entry)
            _log(f"day{di} breakeven ARMED at {stop:.2f}")
        eff = stop
        if use_trail:
            s10, s20 = sma(closes, 10), sma(closes, 20)
            line = max([x for x in (s10, s20) if x is not None], default=None)
            if line is not None and line > eff:
                eff = line
        close_only = (be and be_close_basis) or hard_close_basis
        if not close_only and d["l"] <= stop:
            _log(f"day{di} low {d['l']:.2f} <= stop {stop:.2f} -> EXIT")
            return banked + held * (stop - entry) / risk
        if close_only and d["c"] < stop:
            _log(f"day{di} CLOSE {d['c']:.2f} < stop {stop:.2f} -> EXIT")
            return banked + held * (d["c"] - entry) / risk
        if use_partial and partial_day is None and d["h"] >= target:
            banked += PARTIAL_FRAC * PROFIT_R
            held -= PARTIAL_FRAC
            partial_day = di
            if be_delay_days == 0:
                be = True
                stop = max(stop, entry)
            _log(f"day{di} high {d['h']:.2f} >= target -> 1/3 out, banked {banked:.2f}R")
        if use_trail and d["c"] < eff:
            _log(f"day{di} close {d['c']:.2f} < trail {eff:.2f} -> EXIT")
            return banked + held * (d["c"] - entry) / risk
        closes.append(d["c"])
    last = (fwd[:HORIZON][-1]["c"] if fwd[:HORIZON] else entry)
    return banked + held * (last - entry) / risk


def main():
    rows, daily, minute = M.load_cohort(), M.load_daily(), M.load_minute()
    arms = {
        "A  LIVE — 1/3@2R, breakeven NOW, intraday touch, SMA trail": dict(use_partial=True, use_trail=True),
        "B  no SMA trail": dict(use_partial=True, use_trail=False),
        "C  RAW — no partial, hard stop only": dict(use_partial=False, use_trail=False),
        "D  breakeven DELAYED 1 day (his idea 1)": dict(use_partial=True, use_trail=True, be_delay_days=1),
        "E  breakeven DELAYED 3 days": dict(use_partial=True, use_trail=True, be_delay_days=3),
        "F  breakeven DELAYED 5 days": dict(use_partial=True, use_trail=True, be_delay_days=5),
        "G  breakeven on CLOSING basis (his idea 2)": dict(use_partial=True, use_trail=True, be_close_basis=True),
        "H  DELAYED 3d + CLOSING basis (both)": dict(use_partial=True, use_trail=True, be_delay_days=3, be_close_basis=True),
        "I  ALL stops closing-basis ⚠ real risk change": dict(use_partial=True, use_trail=True, be_close_basis=True, hard_close_basis=True),
    }
    res = {k: [] for k in arms}
    per_name, skipped = {}, defaultdict(int)

    for r in rows:
        why, sub = M.eligibility(r)
        if why != "ok":
            skipped[why] += 1
            continue
        db = daily.get(r["ticker"], [])
        i = M.idx_of_date(db, r["alert_date"])
        raw = minute.get((r["ticker"], r["alert_date"]), [])
        if i is None or not raw:
            skipped["no_bars"] += 1
            continue
        rth = M.de.polygon_to_rth_minutes(raw, r["alert_date"])
        if not rth:
            skipped["no_rth"] += 1
            continue
        rec = M.reconstruct(rth, sub, M.atr14_prior_close(db, i), db[i:])
        if rec.get("outcome") != "filled":
            skipped["outcome:" + str(rec.get("outcome"))] += 1
            continue
        fm = rec["fill_minute"]
        after = [b for b in rth if b["m"] >= fm]
        prior_closes = [b["c"] for b in db[:i]]
        for k, kw in arms.items():
            v = simulate(rec["entry"], rec["stop"], after, db[i + 1:], prior_closes, **kw)
            if v is not None:
                res[k].append(v)
                per_name.setdefault(r["ticker"] + " " + r["alert_date"], {})[k] = v

    L = []
    P = L.append
    P("=" * 96)
    P("EXTENSION COHORT — OUR ACTUAL EXIT, AND WHAT THE SMA TRAIL COSTS")
    P("=" * 96)
    P(f"cohort={len(rows)}  simulated={len(res[list(arms)[0]])}")
    P("not simulated: " + (", ".join(f"{k}={v}" for k, v in sorted(skipped.items())) or "none"))
    P("")
    P("⚠ THE LINE: extension and the stop are entry/exit discipline. Measurement only.")
    P("⚠ Reconstructed, not lived. Submission assumed 09:31 ET (cohort has no detected_at).")
    P("⚠ Horizon 20 trading days — a bound of this replay, not of the live rule.")
    P("")
    for k in arms:
        s = sorted(res[k])
        if not s:
            continue
        sh = lambda t: 100.0 * sum(1 for x in s if x >= t) / len(s)   # noqa: E731
        P(f"{k}")
        P(f"   n={len(s)}  median {M._median(s):+.2f}R  mean {sum(s)/len(s):+.2f}R  "
          f"max {s[-1]:+.2f}R  SUM {sum(s):+.1f}R")
        P(f"   >=2R {sh(2):.1f}%   >=5R {sh(5):.1f}%   >=10R {sh(10):.1f}%   "
          f"stopped(<=-0.99R) {100.0*sum(1 for x in s if x <= -0.99)/len(s):.1f}%")
        P("")
    a, b = list(arms)[0], list(arms)[1]
    if res[a] and res[b]:
        P(f"🔴 WHAT THE SMA TRAIL COSTS: {sum(res[b]) - sum(res[a]):+.1f}R across the cohort "
          f"({sum(res[a]):+.1f}R with it, {sum(res[b]):+.1f}R without).")
        cut = [(v[b] - v[a], n) for n, v in per_name.items() if a in v and b in v and v[b] - v[a] > 0.5]
        P(f"   names the trail cut short by >0.5R: {len(cut)}")
        for d, n in sorted(cut, reverse=True)[:10]:
            P(f"     {n:<20} trail cost {d:+.2f}R  (with {per_name[n][a]:+.2f}R, without {per_name[n][b]:+.2f}R)")
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text("\n".join(L) + "\n", encoding="utf-8")
    print("\n".join(L))
    print(f"\n-> {OUT}")


if __name__ == "__main__":
    main()
